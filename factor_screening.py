"""
因子篩選框架 —— 第四個獨立功能，跟儀表板/驗證報告/定義手冊並列。

目的：之後想到新的候選因子，填一張設定表餵進來，自動跑五道關卡判定該不該
加入正式的七因子綜合分數，不用每次重新手動分析一遍。

用法：
    from factor_screening import run_screening
    result = run_screening(CANDIDATE_CONFIG)   # 見下方 CANDIDATE_CONFIG 範例

    或命令列：
    python3 factor_screening.py my_candidate.json

輸出：
    chart/screening_<key>.html          單一因子的完整體檢報告
    chart/screening_index.html          所有測試過的因子登記簿（一覽表）
    factor_screening_registry.json      登記簿的資料來源（append-only）

五道關卡（任一關沒過就停在那關、標示原因，不繼續往下跑）：
    1. 資料健檢：歷史長度、look-ahead檢查、缺值比例、分數分佈鑑別力
    2. 單獨效力：IC(5/10/20/60/120/250日，非重疊+重疊並列)、10年/20年分桶、
       雙版本熱力圖(原始報酬 vs 超額報酬)、動能延續/長期反轉描述性標記
    3. 穩定性：前後半段IC必須同號(硬性)；跨Fed循環同號檢查(僅供參考，不擋關)
    4. 增量價值：跟現有七因子的相關係數上限0.6；加入後對綜合分數的LOO ΔIC方向
       必須是「拿掉候選因子IC會變差」
    5. 可實作性：換手率(成本門檻尚待使用者提供bps假設，目前只回報數字不擋關)

方法論說明（跟現有驗證報告一致，不重複發明另一套規則）：
    - 所有IC一律非重疊+重疊並列，判斷/門檻只看非重疊版本，重疊版本純供參考。
    - 驗證標的維持ZN期貨，跟現有正式報告一致，不換成IEF等含息ETF。
    - 每次測試都寫進 factor_screening_registry.json，防止「試了很多次、
      只記得成功那幾次」的自欺——這份登記簿本身就是防禦多重比較偏誤的機制。
"""
import json
import os
from datetime import date

import numpy as np
import pandas as pd

import factor_validation_analysis as fva
import regime_lib
import update_dashboard as ud

plt = fva.plt

# ================================================================ 設定
HORIZONS = [5, 10, 20, 60, 120, 250]
MAIN_HORIZON = 20  # 判定門檻用哪個horizon的IC，跟現有正式報告一致
HEATMAP_HOLD_DAYS = [1, 5, 10, 20, 30, 40, 50, 60, 90, 120, 180, 250]
HEATMAP_BUCKETS = 10

THRESHOLDS = {
    "min_abs_ic": 0.03,
    "min_abs_monotonicity": 0.6,
    "max_correlation": 0.6,
    # 至少要有：5年百分位暖身期 + 1年份的分析資料，才勉強夠做基本驗證
    "min_history_days": ud._G["percentile_window_days"] + 365,
}

REGISTRY_PATH = "factor_screening_registry.json"
CHART_DIR = "chart"

# fva.FACTOR_COLS 是 {score_col: 中文名} 例如 {"momentum_score": "動能", ...}，
# 直接沿用它的順序與對照，不要另外重建一份、容易對錯 key/value。


# ================================================================ 六種轉換模式（原始指標，尚未轉百分位）
def _ma_deviation(series, window):
    """均線乖離百分比：(現值 − N日均線) / N日均線 × 100"""
    ma = series.rolling(window, min_periods=window).mean()
    return (series - ma) / ma * 100


def _range_position(series, window):
    """區間位置：現值在過去N日高低點之間的位置，0–100，本身已經是0–100不需要再轉百分位"""
    lo = series.rolling(window, min_periods=window).min()
    hi = series.rolling(window, min_periods=window).max()
    return (series - lo) / (hi - lo) * 100


def _return_spread(series_a, series_b, window):
    """兩序列報酬差：series_a的N日報酬 − series_b的N日報酬"""
    ret_a = (series_a / series_a.shift(window) - 1) * 100
    ret_b = (series_b / series_b.shift(window) - 1) * 100
    return ret_a - ret_b


def _value_spread(series_a, series_b):
    """兩序列差值：series_a − series_b（例如利差、意外值）"""
    return series_a - series_b


def _moving_average(series, window):
    """移動平均：N日簡單移動平均"""
    return series.rolling(window, min_periods=window).mean()


def _rolling_stat(series, window, stat):
    """滾動統計量：N日窗口的偏態(skew)、標準差(std)，或對N日中位數的乖離百分比(median_dev)"""
    if stat == "median_dev":
        med = series.rolling(window, min_periods=window).median()
        return (series - med) / med * 100
    return series.rolling(window, min_periods=window).apply(
        lambda w: pd.Series(w).skew() if stat == "skew" else pd.Series(w).std(), raw=False
    )


TRANSFORM_MODES = {
    "ma_deviation": {"fn": _ma_deviation, "n_sources": 1, "uses_percentile_default": True,
                      "label": "均線乖離百分位"},
    "range_position": {"fn": _range_position, "n_sources": 1, "uses_percentile_default": False,
                        "label": "區間位置"},
    "return_spread": {"fn": _return_spread, "n_sources": 2, "uses_percentile_default": True,
                       "label": "兩序列報酬差百分位"},
    "value_spread": {"fn": _value_spread, "n_sources": 2, "uses_percentile_default": True,
                      "label": "兩序列差值百分位"},
    "moving_average": {"fn": _moving_average, "n_sources": 1, "uses_percentile_default": True,
                        "label": "移動平均百分位"},
    "rolling_stat": {"fn": _rolling_stat, "n_sources": 1, "uses_percentile_default": True,
                      "label": "滾動統計量百分位"},
}


# ================================================================ 資料來源解析
def _resolve_source(spec, df):
    """spec可以是: 字串(df裡已經有的欄位名稱)、{"yahoo": ticker}、{"fred": series_id}。
    回傳 (series, updated_df)——如果是新抓的資料，順便併回df讓後續步驟(例如look-ahead檢查)可以用。"""
    if isinstance(spec, str):
        if spec not in df.columns:
            raise ValueError(f"df裡沒有欄位 '{spec}'，如果是新資料來源請用 {{'yahoo': ticker}} 或 {{'fred': series_id}} 指定")
        return df[spec], df
    if isinstance(spec, dict):
        if "yahoo" in spec:
            name = spec.get("name", spec["yahoo"])
            if name in df.columns:
                return df[name], df
            s = ud.fetch_yahoo_close(spec["yahoo"], name)
            df = df.copy()
            df[name] = s.reindex(df.index).ffill()
            return df[name], df
        if "fred" in spec:
            name = spec.get("name", spec["fred"])
            if name in df.columns:
                return df[name], df
            s = ud.fetch_fred_series(spec["fred"], name)
            df = df.copy()
            df[name] = s.reindex(df.index).ffill()
            return df[name], df
    raise ValueError(f"看不懂的資料來源設定：{spec}")


def build_candidate_score(config, df):
    """照 config 指定的轉換模式，把原始資料變成0–100分數，回傳 (score_series, raw_metric_series, df)。"""
    mode = TRANSFORM_MODES[config["mode"]]
    params = config.get("params", {})
    sources = config["sources"]

    if mode["n_sources"] == 1:
        series, df = _resolve_source(sources["series"], df)
        if config["mode"] == "rolling_stat":
            raw_metric = mode["fn"](series, params["window"], params.get("stat", "skew"))
        elif config["mode"] == "value_spread":
            raw_metric = mode["fn"](series)  # 理論上不會走到這，value_spread是2-source模式
        else:
            raw_metric = mode["fn"](series, params.get("window"))
    else:
        series_a, df = _resolve_source(sources["a"], df)
        series_b, df = _resolve_source(sources["b"], df)
        if config["mode"] == "return_spread":
            raw_metric = mode["fn"](series_a, series_b, params["window"])
        else:
            raw_metric = mode["fn"](series_a, series_b)

    uses_percentile = config.get("uses_percentile", mode["uses_percentile_default"])
    if uses_percentile:
        score = ud.rolling_percentile_score(raw_metric)
    else:
        score = raw_metric.clip(0, 100)

    if config.get("invert", False):
        score = 100 - score

    return score, raw_metric, df


# ================================================================ 第一關：資料健檢
def _check_lookahead(config, df_full, score, n_samples=5):
    """df_full必須是含完整暖身期的資料(例如ext_df_20y)，不能是已經裁切過的6年主範圍——
    裁切過的話,早期日期本身就沒有完整5年百分位窗口，會被誤判成look-ahead問題，
    這是先前測試時真的踩到的一個bug，這裡刻意留這段註解避免以後重犯。"""
    valid_dates = score.dropna().index
    if len(valid_dates) < 20:
        return True, "資料太少，略過"
    sample_idx = sorted(set(
        valid_dates[int(q * (len(valid_dates) - 1))]
        for q in [i / (n_samples - 1) for i in range(n_samples)]
    ))
    mismatches = []
    for d in sample_idx:
        truncated_df = df_full.loc[:d]
        truncated_score, _, _ = build_candidate_score(config, truncated_df)
        a = truncated_score.iloc[-1] if len(truncated_score) else None
        b = score.loc[d]
        both_nan = pd.isna(a) and pd.isna(b)
        if not both_nan and not (pd.notna(a) and pd.notna(b) and abs(a - b) < 1e-6):
            mismatches.append((d.date(), a, b))
    if mismatches:
        detail = "; ".join(f"{d}: 截斷重算={a} vs 正式={b}" for d, a, b in mismatches)
        return False, detail
    return True, f"抽樣{len(sample_idx)}個日期通過"


def gate1_data_health(config, score, raw_metric, df_full):
    reasons = []
    passed = True

    history_days = int(raw_metric.dropna().shape[0])
    if history_days < THRESHOLDS["min_history_days"]:
        passed = False
        reasons.append(
            f"歷史長度不足：只有{history_days}天有效資料（含暖身期），"
            f"至少需要{THRESHOLDS['min_history_days']}天"
        )

    missing_pct = float(raw_metric.isna().mean() * 100)

    lookahead_ok, lookahead_detail = _check_lookahead(config, df_full, score)
    if not lookahead_ok:
        passed = False
        reasons.append(f"look-ahead檢查沒過：{lookahead_detail}")

    valid_score = score.dropna()
    top_share = float((valid_score >= 90).mean()) if len(valid_score) else None
    bottom_share = float((valid_score <= 10).mean()) if len(valid_score) else None
    if top_share is not None and (top_share > 0.5 or bottom_share > 0.5):
        which = "頂端" if top_share > 0.5 else "底端"
        reasons.append(
            f"分數分佈集中：{which}10分位佔了{max(top_share, bottom_share) * 100:.0f}%的天數，"
            "鑑別力可能偏弱（僅警示，不擋關）"
        )

    return {
        "passed": passed, "reasons": reasons, "history_days": history_days,
        "missing_pct": missing_pct, "lookahead_ok": lookahead_ok, "lookahead_detail": lookahead_detail,
        "top_decile_share": top_share, "bottom_decile_share": bottom_share,
    }


# ================================================================ 第二關：單獨效力
def _tag_pattern(ic_by_horizon):
    short_rho = ic_by_horizon[HORIZONS[0]]["overlap"]["rho"]
    mid_rho = ic_by_horizon[HORIZONS[-2]]["overlap"]["rho"]
    long_rho = ic_by_horizon[HORIZONS[-1]]["overlap"]["rho"]
    if long_rho is None:
        return "資料不足無法判斷"
    if long_rho < -0.02 and (mid_rho is None or mid_rho <= 0.02):
        return "長期反轉型（隨持有天數拉長，訊號轉為「恐懼買、貪婪賣」方向且加深）"
    if long_rho > 0.02:
        return "動能延續型（隨持有天數拉長，訊號仍是「貪婪續漲、恐懼續跌」方向）"
    return "型態不明顯"


def _build_dual_heatmap(df, key, buckets=HEATMAP_BUCKETS, hold_days=None, target=None):
    hold_days = hold_days or HEATMAP_HOLD_DAYS
    target = target or fva.TARGET
    sub = df[[key]].dropna()
    if len(sub) < buckets * 5:
        return None, None
    try:
        sub["bucket"] = pd.qcut(sub[key], buckets, labels=False, duplicates="drop")
    except ValueError:
        return None, None
    n_buckets_actual = int(sub["bucket"].nunique())

    price = df[target]
    raw_grid = np.full((n_buckets_actual, len(hold_days)), np.nan)
    excess_grid = np.full((n_buckets_actual, len(hold_days)), np.nan)
    n_grid = np.zeros((n_buckets_actual, len(hold_days)), dtype=int)

    for j, h in enumerate(hold_days):
        fwd = fva.forward_return(price, h)
        baseline = fwd.mean()
        tmp = sub[["bucket"]].copy()
        tmp["fwd"] = fwd.reindex(tmp.index)
        tmp = tmp.dropna(subset=["fwd"])
        if tmp.empty:
            continue
        grp = tmp.groupby("bucket")["fwd"].agg(["mean", "count"])
        for b in range(n_buckets_actual):
            if b in grp.index:
                raw_grid[b, j] = grp.loc[b, "mean"]
                excess_grid[b, j] = grp.loc[b, "mean"] - baseline
                n_grid[b, j] = int(grp.loc[b, "count"])

    meta = {"buckets": n_buckets_actual, "hold_days": hold_days, "n": n_grid}
    return {**meta, "grid": raw_grid}, {**meta, "grid": excess_grid}


def heatmap_chart_base64(heatmap_data, title, cmap="RdBu_r"):
    if heatmap_data is None:
        return None
    grid = heatmap_data["grid"]
    hold_days = heatmap_data["hold_days"]
    buckets = heatmap_data["buckets"]
    fig, ax = plt.subplots(figsize=(7.6, 4.0), dpi=140)
    finite = grid[np.isfinite(grid)]
    vmax = float(np.percentile(np.abs(finite), 98)) if finite.size else 1.0
    vmax = vmax if vmax > 0 else 1.0
    im = ax.imshow(grid, cmap=cmap, vmin=-vmax, vmax=vmax, aspect="auto")
    ax.set_xticks(range(len(hold_days)))
    ax.set_xticklabels(hold_days, fontsize=8)
    ax.set_yticks(range(buckets))
    ax.set_yticklabels([f"D{i + 1}" for i in range(buckets)], fontsize=8)
    ax.set_xlabel("持有天數", fontsize=9)
    ax.set_ylabel(f"分數分組（D1恐懼 → D{buckets}貪婪）", fontsize=9)
    ax.set_title(title, fontsize=10)
    for i in range(grid.shape[0]):
        for j in range(grid.shape[1]):
            if np.isfinite(grid[i, j]):
                ax.text(j, i, f"{grid[i, j]:.1f}", ha="center", va="center", fontsize=6, color="#1a1a1a")
    fig.colorbar(im, ax=ax, shrink=0.8, label="報酬 (%)")
    fig.tight_layout()
    return fva.fig_to_base64(fig)


def gate2_efficacy(key, score_full, ext_df_20y):
    out_start = pd.Timestamp(ud._G["output_start_date"])
    main_df = ext_df_20y.loc[ext_df_20y.index >= out_start].copy()
    main_df[key] = score_full.reindex(main_df.index)

    ten_year_cutoff = pd.Timestamp(date.today()) - pd.Timedelta(days=fva.DECILE_YEARS * 365)
    df_10y = ext_df_20y.loc[ext_df_20y.index >= ten_year_cutoff].copy()
    df_10y[key] = score_full.reindex(df_10y.index)

    df_20y = ext_df_20y.copy()
    df_20y[key] = score_full.reindex(df_20y.index)

    ic_by_horizon = {}
    for h in HORIZONS:
        ic_by_horizon[h] = {
            "non_overlap": fva.non_overlapping_ic(main_df, key, h),
            "overlap": fva.overlapping_ic(main_df, key, h),
        }
    main_ic = ic_by_horizon[MAIN_HORIZON]["non_overlap"]

    decile_10 = fva.decile_bucket_analysis(df_10y, key, horizon=fva.DECILE_HORIZON, buckets=fva.DECILE_N_BUCKETS)
    vigintile_buckets = fva._V["vigintile_n_buckets"]
    decile_20 = fva.decile_bucket_analysis(df_20y, key, horizon=fva.DECILE_HORIZON, buckets=vigintile_buckets)
    # decile_bucket_analysis()不回傳monotonicity(那是5組版本bucket_analysis()才有的欄位)，
    # 這裡跟現有正式報告一致，用主6年範圍的5組分析取單調性，不是10年分桶版本。
    bucket_5 = fva.bucket_analysis(main_df, key)
    monotonicity = bucket_5["monotonicity"] if bucket_5 else None

    heatmap_raw, heatmap_excess = _build_dual_heatmap(main_df, key)
    pattern_tag = _tag_pattern(ic_by_horizon)

    passed = True
    reasons = []
    ic_val = main_ic["rho"]
    if ic_val is None or abs(ic_val) < THRESHOLDS["min_abs_ic"]:
        passed = False
        shown = f"{abs(ic_val):.3f}" if ic_val is not None else "無資料"
        reasons.append(f"IC({MAIN_HORIZON}日，非重疊)絕對值{shown}，低於門檻{THRESHOLDS['min_abs_ic']}")
    if monotonicity is None or abs(monotonicity) < THRESHOLDS["min_abs_monotonicity"]:
        passed = False
        shown = f"{monotonicity:.3f}" if monotonicity is not None else "無資料"
        reasons.append(f"分桶單調性{shown}，低於門檻{THRESHOLDS['min_abs_monotonicity']}")

    return {
        "passed": passed, "reasons": reasons,
        "ic_by_horizon": ic_by_horizon, "main_ic": main_ic, "monotonicity": monotonicity,
        "decile_10": decile_10, "decile_20": decile_20,
        "heatmap_raw": heatmap_raw, "heatmap_excess": heatmap_excess,
        "pattern_tag": pattern_tag,
        "main_df": main_df, "df_10y": df_10y, "df_20y": df_20y,
    }


# ================================================================ 第三關：穩定性
def gate3_stability(key, main_df):
    h1, h2, split_date = fva.split_halves(main_df)
    ic_full = fva.non_overlapping_ic(main_df, key, MAIN_HORIZON)
    ic_h1 = fva.non_overlapping_ic(h1, key, MAIN_HORIZON)
    ic_h2 = fva.non_overlapping_ic(h2, key, MAIN_HORIZON)

    same_sign = None
    if ic_h1["rho"] is not None and ic_h2["rho"] is not None:
        same_sign = (ic_h1["rho"] > 0) == (ic_h2["rho"] > 0)

    passed = True
    reasons = []
    if same_sign is False:
        passed = False
        reasons.append(f"前後半段IC翻號：前半{ic_h1['rho']:+.3f} vs 後半{ic_h2['rho']:+.3f}")
    elif same_sign is None:
        passed = False
        reasons.append("前後半段其中一段資料不足，無法判斷是否同號")

    tmp = main_df.copy()
    tmp["regime_fed"] = [regime_lib.fed_cycle_label(d) for d in tmp.index]
    regime_ic = {}
    for regime_label in sorted(set(tmp["regime_fed"].dropna())):
        seg = tmp[tmp["regime_fed"] == regime_label]
        if len(seg) >= 60:
            regime_ic[regime_label] = fva.non_overlapping_ic(seg, key, MAIN_HORIZON)
    signs = [v["rho"] > 0 for v in regime_ic.values() if v["rho"] is not None]
    regime_same_sign = (len(set(signs)) <= 1) if signs else None

    return {
        "passed": passed, "reasons": reasons,
        "ic_full": ic_full, "ic_h1": ic_h1, "ic_h2": ic_h2, "same_sign": same_sign,
        "regime_ic": regime_ic, "regime_same_sign": regime_same_sign,
        "split_date": split_date,
    }


# ================================================================ 第四關：增量價值
def gate4_incremental(key, main_score, main_df):
    corrs = {}
    for fcol, flabel in fva.FACTOR_COLS.items():
        if fcol in main_df.columns:
            c = main_score.corr(main_df[fcol])
            if pd.notna(c):
                corrs[flabel] = float(c)
    max_corr_key = max(corrs, key=lambda k: abs(corrs[k])) if corrs else None
    max_corr = corrs.get(max_corr_key) if max_corr_key else None

    existing_cols = [c for c in fva.FACTOR_COLS.keys() if c in main_df.columns]
    tmp = main_df.copy()
    tmp["_with_candidate"] = tmp[existing_cols + [key]].mean(axis=1, skipna=True)
    ic_without = fva.non_overlapping_ic(tmp, fva.COMPOSITE_COL, MAIN_HORIZON)
    ic_with = fva.non_overlapping_ic(tmp, "_with_candidate", MAIN_HORIZON)
    delta = None
    if ic_with["rho"] is not None and ic_without["rho"] is not None:
        delta = ic_without["rho"] - ic_with["rho"]

    passed = True
    reasons = []
    if max_corr is not None and abs(max_corr) > THRESHOLDS["max_correlation"]:
        passed = False
        reasons.append(f"跟現有因子「{max_corr_key}」的相關係數{max_corr:+.2f}，超過門檻±{THRESHOLDS['max_correlation']}")
    if delta is not None and delta > 0:
        passed = False
        reasons.append(f"拿掉候選因子後綜合分數IC反而變好（Δ={delta:+.3f}），代表候選因子目前是負貢獻")

    return {
        "passed": passed, "reasons": reasons,
        "correlations": corrs, "max_corr_key": max_corr_key, "max_corr": max_corr,
        "ic_with": ic_with, "ic_without": ic_without, "delta": delta,
    }


# ================================================================ 第五關：可實作性
def gate5_implementability(score):
    pos = (50 - score) / 50
    pos = pos.where((score < 48) | (score > 52), 0.0)
    pos = pos.clip(-1, 1)
    changes = pos.diff().abs()
    turnover_daily_avg = float(changes.mean(skipna=True))
    n_flips = int((changes > 0.05).sum())

    return {
        "passed": None,
        "reasons": ["成本門檻尚待提供bps假設，此關目前只回報數字、不判定通過與否"],
        "turnover_daily_avg": turnover_daily_avg, "n_position_changes": n_flips,
    }


# ================================================================ 主流程
def run_screening(config):
    key = config["key"]
    label = config.get("label", key)
    print(f"[{label}] 抓取延伸歷史資料（20年＋暖身期）...")
    ext_df_20y, raw_ranges = fva.fetch_extended_history(years=fva._V["vigintile_years"])

    score_full, raw_metric_full, ext_df_20y = build_candidate_score(config, ext_df_20y)

    out_start = pd.Timestamp(ud._G["output_start_date"])
    main_df_pre = ext_df_20y.loc[ext_df_20y.index >= out_start].copy()
    main_score_pre = score_full.reindex(main_df_pre.index)
    main_raw_pre = raw_metric_full.reindex(main_df_pre.index)

    result = {"key": key, "label": label, "config": config, "test_date": date.today().isoformat(),
              "raw_ranges": {k: (str(v[0].date()), str(v[1].date()), v[2]) for k, v in raw_ranges.items()}}

    print(f"[{label}] 第一關：資料健檢 ...")
    g1 = gate1_data_health(config, main_score_pre, main_raw_pre, ext_df_20y)
    result["gate1"] = g1
    if not g1["passed"]:
        result["final_verdict"] = "第一關（資料健檢）未通過"
        result["stopped_at"] = 1
        return result

    print(f"[{label}] 第二關：單獨效力 ...")
    g2 = gate2_efficacy(key, score_full, ext_df_20y)
    result["gate2"] = g2
    if not g2["passed"]:
        result["final_verdict"] = "第二關（單獨效力）未通過"
        result["stopped_at"] = 2
        return result

    print(f"[{label}] 第三關：穩定性 ...")
    g3 = gate3_stability(key, g2["main_df"])
    result["gate3"] = g3
    if not g3["passed"]:
        result["final_verdict"] = "第三關（穩定性）未通過"
        result["stopped_at"] = 3
        return result

    print(f"[{label}] 第四關：增量價值 ...")
    g4 = gate4_incremental(key, g2["main_df"][key], g2["main_df"])
    result["gate4"] = g4
    if not g4["passed"]:
        result["final_verdict"] = "第四關（增量價值）未通過"
        result["stopped_at"] = 4
        return result

    print(f"[{label}] 第五關：可實作性 ...")
    g5 = gate5_implementability(g2["main_df"][key])
    result["gate5"] = g5
    result["final_verdict"] = "通過全部五關，建議納入正式綜合分數（可實作性門檻尚待補上成本假設，目前只供參考）"
    result["stopped_at"] = 5
    return result


# ================================================================ 登記簿（防止多重比較自欺）
def _load_registry():
    if os.path.exists(REGISTRY_PATH):
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            return json.load(f)
    return []


def _registry_summary(result):
    """把完整result濃縮成登記簿要存的精簡版本，不存熱力圖矩陣等大型資料，
    避免registry檔案隨測試次數無限膨脹。"""
    entry = {
        "key": result["key"], "label": result["label"], "test_date": result["test_date"],
        "mode": result["config"]["mode"], "final_verdict": result["final_verdict"],
        "stopped_at": result["stopped_at"],
    }
    if "gate2" in result:
        entry["main_ic"] = result["gate2"]["main_ic"]["rho"]
        entry["monotonicity"] = result["gate2"]["monotonicity"]
        entry["pattern_tag"] = result["gate2"]["pattern_tag"]
    if "gate4" in result:
        entry["max_corr"] = result["gate4"]["max_corr"]
        entry["max_corr_key"] = result["gate4"]["max_corr_key"]
        entry["loo_delta"] = result["gate4"]["delta"]
    return entry


def append_to_registry(result):
    registry = _load_registry()
    registry.append(_registry_summary(result))
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)
    return registry


# ================================================================ 單一因子體檢報告
def _gate_badge(passed):
    if passed is True:
        return '<span class="verdict-keep">通過</span>'
    if passed is False:
        return '<span class="verdict-cut">未通過</span>'
    return '<span class="verdict-watch">僅供參考（未設門檻）</span>'


def render_screening_report(result):
    key, label = result["key"], result["label"]
    mode_label = TRANSFORM_MODES[result["config"]["mode"]]["label"]

    sections = []

    g1 = result.get("gate1")
    if g1:
        sections.append(f"""
    <section class="card">
      <h2><span class="bar"></span>第一關：資料健檢 {_gate_badge(g1["passed"])}</h2>
      <table class="data-table mini">
        <tr><th>有效資料天數</th><th>缺值比例</th><th>look-ahead檢查</th></tr>
        <tr><td>{g1["history_days"]}</td><td>{g1["missing_pct"]:.1f}%</td>
            <td>{"通過" if g1["lookahead_ok"] else "未通過"}（{g1["lookahead_detail"]}）</td></tr>
      </table>
      {"<ul>" + "".join(f"<li>{r}</li>" for r in g1["reasons"]) + "</ul>" if g1["reasons"] else ""}
    </section>""")

    g2 = result.get("gate2")
    if g2:
        ic_rows = ""
        for h in HORIZONS:
            non_ov = fva.fmt_rho(g2["ic_by_horizon"][h]["non_overlap"])
            ov = fva.fmt_rho(g2["ic_by_horizon"][h]["overlap"])
            ic_rows += f"<tr><td>{h}日</td><td>{non_ov}</td><td>{ov}</td></tr>"
        decile10_chart = fva.decile_chart_base64(
            g2["decile_10"], f"{label}：未來{fva.DECILE_HORIZON}日平均報酬（10分組，非重疊取樣）",
            fva.DECILE_N_BUCKETS, fva.DECILE_HORIZON
        ) if g2["decile_10"] else None
        vigintile_buckets = fva._V["vigintile_n_buckets"]
        decile20_chart = fva.decile_chart_base64(
            g2["decile_20"], f"{label}：未來{fva.DECILE_HORIZON}日平均報酬（{vigintile_buckets}分組，非重疊取樣）",
            vigintile_buckets, fva.DECILE_HORIZON
        ) if g2["decile_20"] else None
        heatmap_raw_chart = heatmap_chart_base64(g2["heatmap_raw"], f"{label}：原始報酬熱力圖（分桶×持有天數）")
        heatmap_excess_chart = heatmap_chart_base64(
            g2["heatmap_excess"], f"{label}：超額報酬熱力圖（扣除同期無條件平均買進持有）"
        )
        sections.append(f"""
    <section class="card">
      <h2><span class="bar"></span>第二關：單獨效力 {_gate_badge(g2["passed"])}</h2>
      <p class="hint">型態標記：<b>{g2["pattern_tag"]}</b>（描述性標記，不當作及格條件——現有七因子裡多數呈現動能延續型，
        不是長期反轉型，這個標記純粹讓你知道候選因子屬於哪一種，不會因為不是反轉型就被判定不及格）</p>
      <h3>IC（vs 未來N日ZN報酬）</h3>
      <table class="data-table mini">
        <tr><th>持有天數</th><th>非重疊</th><th>重疊（僅供參考）</th></tr>
        {ic_rows}
      </table>
      <p class="hint">分桶單調性（10年版本）：{fva.fmt_num(g2["monotonicity"], 3) if g2["monotonicity"] is not None else "無資料"}</p>
      {"<img class='chart' src='data:image/png;base64," + decile10_chart + "'/>" if decile10_chart else "<p class='na'>10年分桶資料不足</p>"}
      {"<img class='chart' src='data:image/png;base64," + decile20_chart + "'/>" if decile20_chart else "<p class='na'>20年分桶資料不足</p>"}
      {"<img class='chart' src='data:image/png;base64," + heatmap_raw_chart + "'/>" if heatmap_raw_chart else "<p class='na'>熱力圖資料不足</p>"}
      {"<img class='chart' src='data:image/png;base64," + heatmap_excess_chart + "'/>" if heatmap_excess_chart else ""}
      {"<ul>" + "".join(f"<li>{r}</li>" for r in g2["reasons"]) + "</ul>" if g2["reasons"] else ""}
    </section>""")

    g3 = result.get("gate3")
    if g3:
        regime_rows = "".join(
            f"<tr><td>{label_}</td><td>{fva.fmt_rho(ic)}</td></tr>"
            for label_, ic in g3["regime_ic"].items()
        )
        sections.append(f"""
    <section class="card">
      <h2><span class="bar"></span>第三關：穩定性 {_gate_badge(g3["passed"])}</h2>
      <table class="data-table mini">
        <tr><th>全樣本</th><th>前半段</th><th>後半段</th><th>前後半段同號？</th></tr>
        <tr><td>{fva.fmt_rho(g3["ic_full"])}</td><td>{fva.fmt_rho(g3["ic_h1"])}</td>
            <td>{fva.fmt_rho(g3["ic_h2"])}</td><td>{"是" if g3["same_sign"] else "否"}</td></tr>
      </table>
      <h3>跨Fed循環IC（僅供參考，不擋關）</h3>
      <table class="data-table mini"><tr><th>循環階段</th><th>IC</th></tr>{regime_rows}</table>
      <p class="hint">跨循環同號：{"是" if g3["regime_same_sign"] else ("否" if g3["regime_same_sign"] is False else "資料不足無法判斷")}</p>
      {"<ul>" + "".join(f"<li>{r}</li>" for r in g3["reasons"]) + "</ul>" if g3["reasons"] else ""}
    </section>""")

    g4 = result.get("gate4")
    if g4:
        corr_rows = "".join(
            f"<tr><td>{k}</td><td>{v:+.2f}</td></tr>"
            for k, v in g4["correlations"].items()
        )
        sections.append(f"""
    <section class="card">
      <h2><span class="bar"></span>第四關：增量價值 {_gate_badge(g4["passed"])}</h2>
      <h3>跟現有七因子的相關係數</h3>
      <table class="data-table mini"><tr><th>因子</th><th>相關係數</th></tr>{corr_rows}</table>
      <p class="hint">最高相關：{g4["max_corr_key"]}（{g4["max_corr"]:+.2f}），門檻±{THRESHOLDS['max_correlation']}</p>
      <h3>Leave-one-out：加入候選因子對綜合分數IC的影響</h3>
      <p>不含候選：{fva.fmt_rho(g4["ic_without"])}　→　含候選：{fva.fmt_rho(g4["ic_with"])}
        （Δ = {f"{g4['delta']:+.3f}" if g4["delta"] is not None else "無資料"}，負值代表候選因子有正貢獻）</p>
      {"<ul>" + "".join(f"<li>{r}</li>" for r in g4["reasons"]) + "</ul>" if g4["reasons"] else ""}
    </section>""")

    g5 = result.get("gate5")
    if g5:
        sections.append(f"""
    <section class="card">
      <h2><span class="bar"></span>第五關：可實作性 {_gate_badge(g5["passed"])}</h2>
      <p>平均每日部位變動量：{g5["turnover_daily_avg"]:.3f}（0=完全不動，2=從滿多轉滿空）　·　
         部位方向改變次數：{g5["n_position_changes"]}</p>
      {"<ul>" + "".join(f"<li>{r}</li>" for r in g5["reasons"]) + "</ul>" if g5["reasons"] else ""}
    </section>""")

    verdict_class = "verdict-keep" if result["stopped_at"] == 5 else "verdict-cut"
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>因子篩選：{label}</title>
<style>{fva.REPORT_CSS}</style>
</head>
<body>
<div class="wrap">
  <header>
    <nav style="display:flex;gap:16px;flex-wrap:wrap;font-size:13px;margin-bottom:18px;">
      <a href="index.html" style="color:#1e3a5f;text-decoration:none;font-weight:600;padding:10px 6px;margin:-10px -6px;border-radius:6px;display:inline-block;">← 專案首頁</a>
      <a href="screening_index.html" style="color:#1e3a5f;text-decoration:none;font-weight:600;padding:10px 6px;margin:-10px -6px;border-radius:6px;display:inline-block;">← 因子篩選登記簿</a>
    </nav>
    <div class="kicker">FACTOR SCREENING</div>
    <h1>因子篩選：{label}</h1>
    <p class="meta">key：{key}　·　轉換模式：{mode_label}　·　測試日期：{result["test_date"]}</p>
    <p class="disclaimer {verdict_class}">{result["final_verdict"]}</p>
  </header>
  {"".join(sections)}
</div>
</body>
</html>"""



def render_registry_index(registry):
    rows = ""
    for e in reversed(registry):
        verdict_cls = "verdict-keep" if e["stopped_at"] == 5 else "verdict-cut"
        rows += f"""<tr>
          <td>{e["test_date"]}</td>
          <td><a class="factor-link" href="screening_{e['key']}.html" onclick="loadReport('screening_{e['key']}.html', '{e['label']}'); return false;">{e['label']}</a></td>
          <td>{TRANSFORM_MODES[e['mode']]['label']}</td>
          <td>{fva.fmt_num(e.get('main_ic'), 3) if e.get('main_ic') is not None else '—'}</td>
          <td>{e.get('pattern_tag', '—')}</td>
          <td class="{verdict_cls}">{e['final_verdict']}</td>
        </tr>"""

    n_total = len(registry)
    n_passed = sum(1 for e in registry if e["stopped_at"] == 5)
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>因子篩選登記簿與實驗室 · 債券市場恐懼貪婪</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:#f4f5f7; color:#161a23; font-family:-apple-system,BlinkMacSystemFont,"PingFang TC","Noto Sans TC","Segoe UI",Roboto,sans-serif; line-height:1.6; }}
  .wrap {{ max-width:980px; margin:0 auto; padding:44px 24px 80px; }}
  header {{ margin-bottom:28px; }}
  .kicker {{ font-family:ui-monospace,"SF Mono",Menlo,monospace; font-size:11px; letter-spacing:0.12em; color:#a6742a; font-weight:700; margin-bottom:10px; }}
  h1 {{ font-size:30px; font-weight:700; margin:0 0 12px; letter-spacing:-0.02em; }}
  .meta {{ font-size:13px; color:#4a5568; margin:0 0 14px; }}
  .disclaimer {{ font-size:12.5px; color:#667085; background:#fff; border:1px solid #dfe2e8; border-radius:10px; padding:14px 16px; line-height:1.7; }}
  .card {{ background:#fff; border:1px solid #dfe2e8; border-radius:14px; padding:24px 28px; margin-bottom:22px; box-shadow:0 1px 2px rgba(22,26,35,0.04); }}
  .card h2 {{ font-size:18px; font-weight:700; margin:0 0 16px; display:flex; align-items:center; gap:8px; }}
  .bar {{ width:4px; height:18px; background:#1e3a5f; border-radius:2px; display:inline-block; }}
  .data-table {{ width:100%; border-collapse:collapse; font-size:13px; margin:8px 0 4px; }}
  .data-table th, .data-table td {{ text-align:left; padding:8px 12px; border-bottom:1px solid #e5e7eb; font-variant-numeric:tabular-nums; }}
  .data-table th {{ color:#667085; font-weight:600; font-size:11.5px; text-transform:uppercase; letter-spacing:0.03em; }}
  .data-table td.fname {{ font-weight:600; white-space:nowrap; }}
  .verdict-keep {{ color:#2f6b4f; font-weight:700; }}
  .verdict-watch {{ color:#a6742a; font-weight:700; }}
  .verdict-cut {{ color:#a6362f; font-weight:700; }}
  .na {{ color:#a7adb9; font-style:italic; }}

  .form-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
  .form-group {{ display:flex; flex-direction:column; gap:6px; }}
  .form-group.full {{ grid-column:1 / -1; }}
  label {{ font-size:13px; font-weight:600; color:#161a23; }}
  .hint {{ font-size:12px; color:#667085; }}
  input[type="text"], input[type="number"], input[type="password"], select {{
    width:100%; padding:9px 12px; border:1px solid #dfe2e8; border-radius:8px; background:#f4f5f7; color:#161a23; font-size:13.5px; outline:none;
  }}
  input:focus, select:focus {{ border-color:#1e3a5f; }}
  .checkbox-group {{ display:flex; align-items:center; gap:8px; margin-top:4px; }}
  .checkbox-group input {{ width:16px; height:16px; cursor:pointer; }}
  .btn-submit {{
    display:inline-flex; align-items:center; justify-content:center; gap:8px; width:100%; padding:13px; background:#1e3a5f; color:#fff; border:none; border-radius:10px; font-size:14.5px; font-weight:700; cursor:pointer;
  }}
  .btn-submit:hover {{ opacity:.92; }}
  .token-box {{ background:rgba(166,116,42,0.08); border:1px dashed #a6742a; border-radius:10px; padding:14px 16px; margin-bottom:18px; font-size:12.5px; }}
  .token-box summary {{ font-weight:700; color:#a6742a; cursor:pointer; }}
  .status-card {{ display:none; background:#fff; border:1px solid #dfe2e8; border-radius:14px; padding:20px; text-align:center; margin-bottom:22px; }}
  .spinner {{ width:32px; height:32px; border:3px solid #dfe2e8; border-top-color:#1e3a5f; border-radius:50%; animation:spin 1s linear infinite; margin:0 auto 12px; }}
  @keyframes spin {{ to {{ transform:rotate(360deg); }} }}
  .status-title {{ font-size:16px; font-weight:700; margin-bottom:6px; }}
  .status-desc {{ font-size:12.5px; color:#4a5568; margin-bottom:14px; }}
  .progress-steps {{ display:flex; justify-content:space-around; font-size:11.5px; color:#667085; border-top:1px solid #e5e7eb; padding-top:12px; }}
  .step.active {{ color:#1e3a5f; font-weight:700; }}
  .step.done {{ color:#2f6b4f; font-weight:700; }}
  .report-viewer {{ display:none; background:#fff; border:1px solid #dfe2e8; border-radius:14px; padding:16px; margin-bottom:22px; }}
  iframe.report-frame {{ width:100%; height:1300px; border:none; display:block; }}
  .factor-link {{ color:#1e3a5f; text-decoration:none; font-weight:600; cursor:pointer; }}
  .factor-link:hover {{ text-decoration:underline; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <nav style="display:flex;gap:16px;flex-wrap:wrap;font-size:13px;margin-bottom:18px;">
      <a href="index.html" style="color:#1e3a5f;text-decoration:none;font-weight:600;padding:10px 6px;margin:-10px -6px;border-radius:6px;display:inline-block;">← 專案首頁</a>
    </nav>
    <div class="kicker">FACTOR SCREENING REGISTRY &amp; LAB</div>
    <h1>因子篩選登記簿與實驗室</h1>
    <p class="meta">累計測試 {n_total} 個因子，通過全部五關 {n_passed} 個。</p>
    <p class="disclaimer">
      這份登記簿記錄「每一次」測試過的因子。您可以在下方<b>輸入新因子進行線上驗證</b>，運算完成後，分析圖表與 5 道關卡報告會<b>直接在此頁面上展示出來</b>。
    </p>
  </header>

  <!-- 線上驗證輸入表單 -->
  <section class="card">
    <h2><span class="bar"></span>➕ 輸入新因子進行驗證</h2>
    
    <details class="token-box" id="tokenDetails">
      <summary>🔑 設定 GitHub Personal Access Token (第一次使用必填)</summary>
      <p style="margin:6px 0 10px;color:#4a5568;">填入授權 Token (具備 repo/workflow 權限)，安全儲存於本機瀏覽器 (localStorage)。</p>
      <div class="form-group">
        <input type="password" id="ghToken" placeholder="ghp_xxxxxxxxxxxxxxxxx" autocomplete="off">
      </div>
    </details>

    <form id="screeningForm">
      <div class="form-grid">
        <div class="form-group">
          <label for="key">因子英文代號 (Key)</label>
          <input type="text" id="key" placeholder="例: vix_ma_dev" required pattern="[a-zA-Z0-9_]+" title="英文字母、數字與底線">
        </div>
        <div class="form-group">
          <label for="label">因子中文名稱 (Label)</label>
          <input type="text" id="label" placeholder="例: VIX 125日均線乖離率" required>
        </div>
        <div class="form-group full">
          <label for="mode">轉換模式 (Transformation Mode)</label>
          <select id="mode" required onchange="handleModeChange()">
            <option value="ma_deviation">均線乖離百分位 (Single Series vs N-day SMA)</option>
            <option value="range_position">區間位置 (N-day High/Low Range Position 0-100)</option>
            <option value="return_spread">兩序列報酬差百分位 (Series A N-day Ret - Series B N-day Ret)</option>
            <option value="value_spread">兩序列差值百分位 (Series A - Series B)</option>
            <option value="moving_average">移動平均百分位 (N-day SMA)</option>
            <option value="rolling_stat">滾動統計量百分位 (N-day Skew / StdDev)</option>
          </select>
        </div>
        <div class="form-group">
          <label for="sourceType">資料來源 A 類型</label>
          <select id="sourceType" required>
            <option value="yahoo">Yahoo Finance (代號如 ^VIX)</option>
            <option value="fred">FRED 經濟數據 (代號如 DGS10)</option>
            <option value="existing">儀表板既有欄位 (UST_10Yr 等)</option>
          </select>
        </div>
        <div class="form-group">
          <label for="sourceId">資料來源 A 識別碼</label>
          <input type="text" id="sourceId" placeholder="例: ^VIX / DGS10 / UST_10Yr" required>
        </div>
        <div class="form-group source-b-group" style="display:none;">
          <label for="sourceBType">資料來源 B 類型</label>
          <select id="sourceBType">
            <option value="yahoo">Yahoo Finance</option>
            <option value="fred">FRED</option>
            <option value="existing">儀表板既有欄位</option>
          </select>
        </div>
        <div class="form-group source-b-group" style="display:none;">
          <label for="sourceBId">資料來源 B 識別碼</label>
          <input type="text" id="sourceBId" placeholder="例: SHY / DGS2">
        </div>
        <div class="form-group">
          <label for="window">滾動視窗 (Window Days)</label>
          <input type="number" id="window" value="125" min="5" max="500" required>
        </div>
        <div class="form-group">
          <label>分數反轉</label>
          <div class="checkbox-group">
            <input type="checkbox" id="invert">
            <label for="invert" style="font-weight:normal;">數值越高代表「恐懼」時請勾選 (將分數反轉)</label>
          </div>
        </div>
        <div class="form-group full" style="margin-top:8px;">
          <button type="submit" class="btn-submit" id="btnSubmit">
            🚀 提交驗證並即時呈現分析報告圖表
          </button>
        </div>
      </div>
    </form>
  </section>

  <!-- 運算進度狀態卡片 -->
  <div class="status-card" id="statusCard">
    <div class="spinner" id="statusSpinner"></div>
    <div class="status-title" id="statusTitle">已提交分析請求</div>
    <div class="status-desc" id="statusDesc">GitHub Actions 正在啟動 20 年數據運算與圖表繪製引擎...</div>
    <div class="progress-steps">
      <div class="step active" id="step1">1. 提交請求</div>
      <div class="step" id="step2">2. 執行 20 年運算</div>
      <div class="step" id="step3">3. 產生報告圖表</div>
      <div class="step" id="step4">4. 呈現分析報告</div>
    </div>
  </div>

  <!-- 報告圖表內嵌呈現區 (直接在登記簿頁面上展示) -->
  <div class="report-viewer" id="reportViewer">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;padding-bottom:10px;border-bottom:1px solid #e5e7eb;">
      <h3 style="margin:0;font-size:16px;" id="reportViewerTitle">📊 因子分析報告與視覺化圖表</h3>
      <button onclick="closeReportViewer()" style="background:none;border:1px solid #dfe2e8;border-radius:6px;padding:4px 10px;cursor:pointer;font-size:12px;">關閉報告</button>
    </div>
    <iframe class="report-frame" id="reportFrame"></iframe>
  </div>

  <!-- 歷史紀錄表格卡片 -->
  <section class="card">
    <h2><span class="bar"></span>歷史測試紀錄登記簿 (點擊名稱可直接在下方展開報告圖表)</h2>
    <table class="data-table">
      <tr><th>測試日期</th><th>因子</th><th>轉換模式</th><th>IC(20日,非重疊)</th><th>型態標記</th><th>結果</th></tr>
      {rows if rows else "<tr><td colspan='6' class='na'>尚無測試記錄</td></tr>"}
    </table>
  </section>
</div>

<script>
  const REPO_OWNER = "dp79b47tvn-maker";
  const REPO_NAME = "bond-fear-greed-dashboard";

  const savedToken = localStorage.getItem("gh_pat_token");
  if (savedToken) {{
    document.getElementById("ghToken").value = savedToken;
  }} else {{
    document.getElementById("tokenDetails").open = true;
  }}

  function handleModeChange() {{
    const mode = document.getElementById("mode").value;
    const isTwoSources = (mode === "return_spread" || mode === "value_spread");
    document.querySelectorAll(".source-b-group").forEach(el => {{
      el.style.display = isTwoSources ? "flex" : "none";
    }});
  }}

  function loadReport(reportUrl, label) {{
    const viewer = document.getElementById("reportViewer");
    const frame = document.getElementById("reportFrame");
    const title = document.getElementById("reportViewerTitle");
    title.innerText = "📊 因子分析報告與圖表：" + (label || "");
    frame.src = reportUrl;
    viewer.style.display = "block";
    viewer.scrollIntoView({{ behavior: "smooth" }});
  }}

  function closeReportViewer() {{
    document.getElementById("reportViewer").style.display = "none";
  }}

  document.getElementById("screeningForm").addEventListener("submit", async (e) => {{
    e.preventDefault();

    const token = document.getElementById("ghToken").value.trim();
    if (!token) {{
      alert("請先填寫 GitHub Personal Access Token (PAT)！");
      document.getElementById("tokenDetails").open = true;
      document.getElementById("ghToken").focus();
      return;
    }}
    localStorage.setItem("gh_pat_token", token);

    const key = document.getElementById("key").value.trim();
    const label = document.getElementById("label").value.trim();
    const mode = document.getElementById("mode").value;
    const sourceType = document.getElementById("sourceType").value;
    const sourceId = document.getElementById("sourceId").value.trim();
    const sourceBType = document.getElementById("sourceBType").value;
    const sourceBId = document.getElementById("sourceBId").value.trim();
    const windowVal = document.getElementById("window").value;
    const invert = document.getElementById("invert").checked;

    const btnSubmit = document.getElementById("btnSubmit");
    const statusCard = document.getElementById("statusCard");

    btnSubmit.disabled = true;
    statusCard.style.display = "block";
    closeReportViewer();
    
    updateStatus(1, "已提交分析請求", "GitHub Actions 正在啟動 20 年數據運算與圖表繪製引擎...");

    try {{
      const resp = await fetch(`https://api.github.com/repos/${{REPO_OWNER}}/${{REPO_NAME}}/actions/workflows/factor-screening.yml/dispatches`, {{
        method: "POST",
        headers: {{
          "Accept": "application/vnd.github+json",
          "Authorization": `Bearer ${{token}}`,
          "Content-Type": "application/json"
        }},
        body: JSON.stringify({{
          ref: "main",
          inputs: {{
            key: key,
            label: label,
            mode: mode,
            source_type: sourceType,
            source_id: sourceId,
            source_b_type: sourceBType || "none",
            source_b_id: sourceBId || "",
            window: String(windowVal),
            invert: invert
          }}
        }})
      }});

      if (!resp.ok) {{
        const errText = await resp.text();
        throw new Error(`GitHub API 錯誤 (${{resp.status}}): ${{errText}}`);
      }}

      updateStatus(2, "正在執行 20 年驗證與熱力圖分析", "運算約需要 2~3 分鐘，請保持此頁面開啟...");
      pollForReport(key, label);

    }} catch (err) {{
      alert("提交失敗：" + err.message);
      btnSubmit.disabled = false;
      statusCard.style.display = "none";
    }}
  }});

  function updateStatus(stepNum, title, desc) {{
    document.getElementById("statusTitle").innerText = title;
    document.getElementById("statusDesc").innerText = desc;
    for (let i = 1; i <= 4; i++) {{
      const el = document.getElementById(`step${{i}}`);
      el.className = "step";
      if (i < stepNum) el.classList.add("done");
      if (i === stepNum) el.classList.add("active");
    }}
  }}

  function pollForReport(key, label) {{
    const reportUrl = `screening_${{key}}.html?t=${{Date.now()}}`;
    let attempts = 0;
    const maxAttempts = 40;

    const interval = setInterval(async () => {{
      attempts++;
      if (attempts > 15) {{
        updateStatus(3, "正在生成圖表並部署報告...", "已完成資料運算，正在把報告與圖表發布至網頁...");
      }}

      try {{
        const resp = await fetch(reportUrl, {{ method: "HEAD", cache: "no-store" }});
        if (resp.status === 200) {{
          clearInterval(interval);
          updateStatus(4, "🎉 分析完成！報告與圖表已呈現在下方", "已成功產出該因子的完整 5 道關卡評估與視覺化圖表：");
          document.getElementById("statusSpinner").style.display = "none";
          document.getElementById("btnSubmit").disabled = false;
          
          loadReport(reportUrl, label);
        }}
      }} catch (e) {{}}

      if (attempts >= maxAttempts) {{
        clearInterval(interval);
        alert("等待逾時：請重新整理頁面查看表格內的最新結果。");
        document.getElementById("btnSubmit").disabled = false;
      }}
    }}, 10000);
  }}
</script>
</body>
</html>"""


def screen_and_save(config):
    """跑完整流程、產生報告、更新登記簿——這是命令列/一般使用的主要入口。"""
    result = run_screening(config)
    os.makedirs(CHART_DIR, exist_ok=True)
    report_html = render_screening_report(result)
    report_path = os.path.join(CHART_DIR, f"screening_{result['key']}.html")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_html)
    registry = append_to_registry(result)
    index_html = render_registry_index(registry)
    with open(os.path.join(CHART_DIR, "screening_index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)
    print(f"\n完成！{result['final_verdict']}")
    print(f"報告：{report_path}")
    print(f"登記簿：{CHART_DIR}/screening_index.html")
    return result


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("用法：python3 factor_screening.py <candidate_config.json>")
        sys.exit(1)
    with open(sys.argv[1], encoding="utf-8") as f:
        cfg = json.load(f)
    screen_and_save(cfg)
