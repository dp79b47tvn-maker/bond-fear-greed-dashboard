# -*- coding: utf-8 -*-
"""
因子篩選平台的計算邏輯——五道關卡、回測策略、輔助統計函式。純計算，不碰
HTML 或 matplotlib，這樣才能像 tests/test_factor_screening.py 現在做的那樣獨立測試，
不用為了測一個公式對不對，連帶把整套HTML/圖表產生邏輯也import進來。

架構檢討第3項(2026-08-25)拆自原本2390行、計算/渲染/圖表混在一起的
factor_screening.py。三支模組的分工：
    screening_gates.py    (這支) 拿資料算出結果——五關、回測、部位規則
    screening_charts.py   matplotlib畫圖轉base64
    screening_render.py   組HTML字串模板
factor_screening.py 本身變成薄的orchestrator：run_screening()依序呼叫這裡的
五個gate函式、registry讀寫、screen_and_save()/rebuild_index()兩個對外入口。
它會把這三支模組的函式重新import進自己的命名空間，所以 fs.score_to_position()、
fs.backtest_strategy() 這種既有呼叫方式完全不用改，外部呼叫者(scripts/*.py、
tests/test_factor_screening.py)一行都不用動。
"""
from datetime import date

import numpy as np
import pandas as pd
from scipy import stats

import factor_validation_analysis as fva
import update_dashboard as ud

HORIZONS = [5, 10, 20, 60, 120, 250]
MAIN_HORIZON = 20  # 判定門檻用哪個horizon的IC，跟現有正式報告一致
# product framework要求「持有期間從10天到90天」，跟現有分桶用的10天間距對齊
HEATMAP_HOLD_DAYS = [10, 20, 30, 40, 50, 60, 70, 80, 90]
HEATMAP_BUCKETS = 10

# 2026-07-28根據現有七因子重疊取樣版本的實測分布重新校準(舊門檻是照非重疊版本
# 訂的,直接套用會誤判掉原本表現不錯的因子——實測後單調性普遍降到0.47~0.75，
# IC普遍降到0.04~0.12，殖利率曲線形狀維持墊底(接近零/負值))。
# 這些門檻現在只用來生成「建議」文字,不再擋關——五道關卡一律全部跑完、
# 報告一律完整輸出,最終是否採用交給使用者自行判斷。
THRESHOLDS = {
    "min_abs_ic": 0.02,
    "min_abs_monotonicity": 0.4,
    "max_correlation": 0.6,
    # 至少要有：5年百分位暖身期 + 1年份的分析資料，才勉強夠做基本驗證
    "min_history_days": ud._G["percentile_window_days"] + 365,
}


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
        truncated_score, _, _ = build_candidate_score(config, truncated_df, ud.fetch_yahoo_close, ud.fetch_fred_series)
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



def decile_bucket_analysis_overlap(df, score_col, horizon, buckets, target=None):
    """跟fva.decile_bucket_analysis()邏輯相同(qcut等分＋看未來N日平均報酬)，
    唯一差別:不做.iloc[::horizon]跳過，每天都取樣——這個平台全面改用重疊取樣，
    理由是避免非重疊取樣固定間隔取點、漏看區間內真正發生過的漲跌波動。"""
    target = target or fva.TARGET
    sub = df[[score_col]].copy()
    sub["fwd"] = fva.forward_return(df[target], horizon)
    sub = sub.dropna()
    if len(sub) < buckets * 3:
        return None
    actual_start, actual_end = sub.index.min(), sub.index.max()
    if len(sub) < buckets:
        return None
    try:
        sub["bucket"] = pd.qcut(sub[score_col], buckets, labels=False, duplicates="drop")
    except ValueError:
        return None
    grp = sub.groupby("bucket").agg(
        mean_score=(score_col, "mean"), mean_fwd_ret=("fwd", "mean"),
        median_fwd_ret=("fwd", "median"), n=("fwd", "count"),
    ).reset_index()
    grp["label"] = [f"D{i + 1}" for i in range(len(grp))]
    mono_rho, _ = stats.spearmanr(grp["bucket"], grp["mean_fwd_ret"]) if len(grp) >= 3 else (None, None)
    return {
        "table": grp, "date_range": (actual_start, actual_end),
        "n_sampled_total": len(sub), "n_daily_total": len(sub),
        "monotonicity": float(mono_rho) if pd.notna(mono_rho) else None,
    }


def gate2_efficacy(key, score_full, ext_df_20y):
    out_start = pd.Timestamp(ud._G["output_start_date"])
    main_df = ext_df_20y.loc[ext_df_20y.index >= out_start].copy()
    main_df[key] = score_full.reindex(main_df.index)

    ten_year_cutoff = pd.Timestamp(date.today()) - pd.Timedelta(days=fva.DECILE_YEARS * 365)
    df_10y = ext_df_20y.loc[ext_df_20y.index >= ten_year_cutoff].copy()
    df_10y[key] = score_full.reindex(df_10y.index)

    df_20y = ext_df_20y.copy()
    df_20y[key] = score_full.reindex(df_20y.index)

    # 全平台一律採重疊取樣(product framework 2026-07-28決定):非重疊版本還是算,
    # 附在報告裡當對照參考,但門檻判斷、主要陳述一律看重疊版本。
    ic_by_horizon = {}
    for h in HORIZONS:
        ic_by_horizon[h] = {
            "non_overlap": fva.non_overlapping_ic(main_df, key, h),
            "overlap": fva.overlapping_ic(main_df, key, h),
        }
    main_ic = ic_by_horizon[MAIN_HORIZON]["overlap"]

    decile_10 = decile_bucket_analysis_overlap(df_10y, key, horizon=fva.DECILE_HORIZON, buckets=fva.DECILE_N_BUCKETS)
    vigintile_buckets = fva._V["vigintile_n_buckets"]
    decile_20 = decile_bucket_analysis_overlap(df_20y, key, horizon=fva.DECILE_HORIZON, buckets=vigintile_buckets)
    # 單調性改用10年分桶(重疊)版本算出來的monotonicity,跟決定IC用哪個版本的邏輯一致，
    # 不再用主6年範圍的5組非重疊前身版本。
    monotonicity = decile_10["monotonicity"] if decile_10 else None

    heatmap_raw, heatmap_excess = _build_dual_heatmap(main_df, key)
    pattern_tag = _tag_pattern(ic_by_horizon)

    passed = True
    reasons = []
    ic_val = main_ic["rho"]
    if ic_val is None or abs(ic_val) < THRESHOLDS["min_abs_ic"]:
        passed = False
        shown = f"{abs(ic_val):.3f}" if ic_val is not None else "無資料"
        reasons.append(f"IC({MAIN_HORIZON}日，重疊)絕對值{shown}，低於參考門檻{THRESHOLDS['min_abs_ic']}")
    if monotonicity is None or abs(monotonicity) < THRESHOLDS["min_abs_monotonicity"]:
        passed = False
        shown = f"{monotonicity:.3f}" if monotonicity is not None else "無資料"
        reasons.append(f"分桶單調性(重疊){shown}，低於參考門檻{THRESHOLDS['min_abs_monotonicity']}")

    return {
        "passed": passed, "reasons": reasons,
        "ic_by_horizon": ic_by_horizon, "main_ic": main_ic, "monotonicity": monotonicity,
        "decile_10": decile_10, "decile_20": decile_20,
        "heatmap_raw": heatmap_raw, "heatmap_excess": heatmap_excess,
        "pattern_tag": pattern_tag,
        "main_df": main_df, "df_10y": df_10y, "df_20y": df_20y,
    }



def gate3_stability(key, main_df):
    h1, h2, split_date = fva.split_halves(main_df)
    ic_full = fva.overlapping_ic(main_df, key, MAIN_HORIZON)
    ic_h1 = fva.overlapping_ic(h1, key, MAIN_HORIZON)
    ic_h2 = fva.overlapping_ic(h2, key, MAIN_HORIZON)

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
            regime_ic[regime_label] = fva.overlapping_ic(seg, key, MAIN_HORIZON)
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
    ic_without = fva.overlapping_ic(tmp, fva.COMPOSITE_COL, MAIN_HORIZON)
    ic_with = fva.overlapping_ic(tmp, "_with_candidate", MAIN_HORIZON)
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



# ================================================================ 部位規則（回測與第五關共用）
def score_to_position(score):
    """把0–100分數轉成 −1~+1 的部位，規則來自 factor_definitions.json 的
    validation.position_rule_note / dead_zone，全專案只有這一份實作。

    部位 = (50 − 分數) / 50：分數低(恐懼)→做多債券，分數高(貪婪)→做空。
    死區(預設48–52)強制空手，避免在中性區被雜訊來回洗。
    """
    lo, hi = fva._V["dead_zone"]
    pos = (50 - score) / 50
    pos = pos.where((score < lo) | (score > hi), 0.0)
    return pos.clip(-1, 1)



# ================================================================ 第五關：可實作性
def gate5_implementability(score):
    pos = score_to_position(score)
    changes = pos.diff().abs()
    turnover_daily_avg = float(changes.mean(skipna=True))
    n_flips = int((changes > 0.05).sum())

    return {
        "passed": None,
        "reasons": ["成本門檻尚待提供bps假設，此關目前只回報數字、不判定通過與否"],
        "turnover_daily_avg": turnover_daily_avg, "n_position_changes": n_flips,
    }


# ================================================================ 回測分析
def backtest_strategy(score, main_df, target=None):
    """依 factor_definitions.json 宣告的部位規則做逐日回測。

    【禁止引用未來資料】t日收盤知道當天分數 → 決定t日部位 → 賺t到t+1的報酬。
    pnl(t) = pos(t) × 報酬(t→t+1)，pos 用的是當天(含)以前的資料算出來的分數，
    絕不會用到 t+1 才知道的資訊。

    單位是「bp的價格報酬」：目標欄位是10年期殖利率，殖利率下降代表債券價格上漲，
    所以報酬 = −1 × 殖利率變動(bp)。做多部位遇到殖利率下降就賺錢。

    對照組刻意放「無條件買進持有」(部位恆為+1)——沒有這個基準的話，看到正報酬
    很容易誤以為是因子有效，其實只是這段期間債券本來就在漲。

    樣本內/外用時間前後對半切：後半段是因子參數決定之後才發生的資料，
    Sharpe衰退比例(OOS/IS)是判斷有沒有過度配適最直接的指標。
    """
    target = target or fva.TARGET
    sub = pd.concat([score.rename("score"), main_df[target].rename("y")], axis=1).dropna()
    # 上游的 df 是日曆日索引(週末假日由 ffill 補值)，直接拿來回測會有兩個問題：
    #   1. 一年變成365筆，卻用 √252 年化，Sharpe/波動度全部算錯
    #   2. 週末那些「殖利率沒動」的假交易日會灌水交易日數、壓低勝率
    # 這裡先濾成工作日(週一~週五)。國定假日仍會殘留成零變動日，但影響遠小於週末，
    # 且這是業界標準做法。
    sub = sub[sub.index.dayofweek < 5]
    if len(sub) < 250:
        return None

    # 未來1日殖利率變動(bp)；最後一天沒有隔天資料，dropna掉
    d_bp = (sub["y"].shift(-1) - sub["y"]) * 100
    price_ret = -d_bp                      # 價格報酬 ≈ −1 × 殖利率變動
    pos = score_to_position(sub["score"])

    pnl = (pos * price_ret).dropna()
    bh = price_ret.reindex(pnl.index)      # 對照組：無條件買進持有
    if len(pnl) < 250:
        return None

    def _stats(series, positions=None):
        if len(series) < 20 or series.std() == 0:
            return None
        ann_ret = float(series.mean() * 252)
        ann_vol = float(series.std() * np.sqrt(252))
        curve = series.cumsum()
        drawdown = float((curve - curve.cummax()).min())
        # 勝率只看「有下注而且真的有損益」的日子——死區空手日跟殖利率沒動的日子
        # 損益是0，算進分母會讓勝率看起來莫名其妙地低(明明累積報酬是正的)
        active = series[series != 0]
        out = {
            "ann_ret_bp": ann_ret, "ann_vol_bp": ann_vol,
            "sharpe": ann_ret / ann_vol if ann_vol else 0.0,
            "max_dd_bp": drawdown,
            "total_bp": float(curve.iloc[-1]),
            "win_rate": float((active > 0).mean() * 100) if len(active) else 0.0,
            "n_active": len(active),
            "n_days": len(series),
        }
        if positions is not None:
            p = positions.reindex(series.index)
            out["avg_exposure"] = float(p.abs().mean())
            out["long_pct"] = float((p > 0).mean() * 100)
            out["short_pct"] = float((p < 0).mean() * 100)
            out["flat_pct"] = float((p == 0).mean() * 100)
        return out

    split = len(pnl) // 2
    split_date = pnl.index[split]
    is_stats = _stats(pnl.iloc[:split], pos)
    oos_stats = _stats(pnl.iloc[split:], pos)
    decay = (oos_stats["sharpe"] / is_stats["sharpe"]
             if is_stats and oos_stats and is_stats["sharpe"] > 0 else None)

    return {
        "full": _stats(pnl, pos),
        "buy_hold": _stats(bh),
        "is": is_stats,
        "oos": oos_stats,
        "sharpe_decay": decay,
        "split_date": split_date,
        "curve": pnl.cumsum(),
        "curve_bh": bh.cumsum(),
        "start": pnl.index.min(),
        "end": pnl.index.max(),
    }


