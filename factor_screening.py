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

五道關卡（不論成功失敗都會全部跑完，只提供建議、不硬性擋關，最終是否採用
交由使用者自行判斷）：
    1. 資料健檢：歷史長度、look-ahead檢查、缺值比例、分數分佈鑑別力
    2. 單獨效力：IC(5/10/20/60/120/250日，重疊+非重疊並列)、10年/20年分桶、
       雙版本熱力圖(原始報酬 vs 超額報酬)、動能延續/長期反轉描述性標記
    3. 穩定性：前後半段IC是否同號；跨Fed循環同號檢查(僅供參考)
    4. 增量價值：跟現有七因子的相關係數上限0.6；加入後對綜合分數的LOO ΔIC方向
       是否為「拿掉候選因子IC會變差」
    5. 可實作性：換手率(成本門檻尚待使用者提供bps假設，目前只回報數字)

方法論說明（跟現有驗證報告一致，不重複發明另一套規則）：
    - 所有IC一律重疊+非重疊並列，判斷/門檻以重疊取樣為主，非重疊版本純供對照。
    - 統計驗證標的維持ZN期貨，跟現有正式報告一致；UST_10Yr殖利率只在報告圖1
      當視覺參考疊圖，不參與任何IC/統計計算。
    - 每次測試都寫進 factor_screening_registry.json，防止「試了很多次、
      只記得成功那幾次」的自欺——這份登記簿本身就是防禦多重比較偏誤的機制。
"""
import json
import os
from datetime import date

import numpy as np
import pandas as pd
from scipy import stats

import factor_validation_analysis as fva
import nav_bar
import page_style
import regime_lib
import update_dashboard as ud
from transform_modes import TRANSFORM_MODES, _resolve_source, build_candidate_score

plt = fva.plt

# ================================================================ 設定
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

REGISTRY_PATH = "factor_screening_registry.json"
CHART_DIR = "chart"

# 產品定位聲明(2026-07-28product framework)：這個平台是輔助交易員判斷氛圍的研究工具，
# 不是策略、不是投資建議——每個對外頁面的頁首都要看得到這句話。
POSITIONING_STATEMENT = (
    "本平台協助債券交易者判斷美債市場目前的整體氛圍，作為交易員的輔助判斷工具，"
    "非交易策略、非投資建議。所有分析結果以研究性語言呈現歷史統計特徵，"
    "不產出即時部位建議或操作指令。"
)

# 跟儀表板一致的情緒分級色階(淺色模式)，用在分數走勢圖的背景色帶
TIER_COLORS = ["#2f6b4f", "#5c8a6e", "#6b7280", "#b1592f", "#a6362f"]

# 單一因子報告頁「升等為可選因子」按鈕用的CSS——render_screening_report()用的是
# fva.REPORT_CSS，沒有.token-box/.btn-submit這些class(那些只在render_registry_index()
# 自己的<style>裡定義)，這裡補一份自成一體的、視覺語言跟登記簿頁一致。
PROMOTE_UI_CSS = """
  .promote-card .token-box { background:rgba(166,116,42,0.08); border:1px dashed #a6742a; border-radius:10px;
    padding:14px 16px; margin:12px 0; font-size:12.5px; }
  .promote-card .token-box summary { font-weight:700; color:#a6742a; cursor:pointer; }
  .promote-card input[type="password"] { width:100%; padding:9px 12px; margin-top:8px; border:1px solid #dfe2e8;
    border-radius:8px; background:#f4f5f7; color:#161a23; font-size:13.5px; outline:none; }
  .promote-btn { display:inline-flex; align-items:center; gap:8px; padding:11px 20px; background:#1e3a5f; color:#fff;
    border:none; border-radius:10px; font-size:13.5px; font-weight:700; cursor:pointer; }
  .promote-btn:hover { opacity:.92; }
  .promote-btn:disabled { opacity:.55; cursor:not-allowed; }
"""

# fva.FACTOR_COLS 是 {score_col: 中文名} 例如 {"momentum_score": "動能", ...}，
# 直接沿用它的順序與對照，不要另外重建一份、容易對錯 key/value。

# ================================================================ 資料來源候選清單（給表單搜尋框用）
# 使用者原本要自己記代號手打(Yahoo要記得加^、FRED代號一堆英文縮寫)，很容易打錯或
# 不知道能填什麼——這份清單讓表單改成「打中文關鍵字或代號都能搜到、選了自動帶入
# 正確type/id」，找不到的話表單上還有「手動輸入」的退路，不會限制彈性。
# existing類的id必須是ext_df_20y實際會有的欄位名稱，跟build_candidate_score()
# 的_resolve_source()字串比對邏輯要一致，故意用程式碼裡的名字，不憑印象手key。
EXISTING_COLUMN_LABELS = {
    "ZN_futures": "10年期公債期貨(ZN)原始價格",
    "NQ_futures": "那斯達克100期貨(NQ)原始價格",
    "TLT": "20年期以上公債ETF(TLT)",
    "SHY": "1-3年期短債ETF(SHY)",
    "MOVE_index": "公債波動率指數(MOVE)",
    "UST_10Yr": "美國10年期公債殖利率",
    "UST_2Yr": "美國2年期公債殖利率",
    "CPI_index": "CPI消費者物價指數",
    "Breakeven_10Y": "10年期損益平衡通膨率",
    "put_call_ratio": "選擇權Put/Call比率",
}
SOURCE_CATALOG = (
    [{"id": k, "type": "existing", "label": f"{v}（儀表板既有欄位）"}
     for k, v in EXISTING_COLUMN_LABELS.items()]
    + [{"id": k, "type": "existing", "label": f"{v}分數（儀表板既有因子）"}
       for k, v in fva.FACTOR_COLS.items()]
    + [{"id": fva.COMPOSITE_COL, "type": "existing", "label": f"{fva.COMPOSITE_LABEL}（儀表板既有欄位）"}]
    + [
        {"id": "^VIX", "type": "yahoo", "label": "VIX恐慌指數"},
        {"id": "^MOVE", "type": "yahoo", "label": "MOVE公債波動率指數(Yahoo版)"},
        {"id": "^TNX", "type": "yahoo", "label": "10年期公債殖利率×10(Yahoo版,注意單位)"},
        {"id": "GLD", "type": "yahoo", "label": "黃金ETF(GLD)"},
        {"id": "DX-Y.NYB", "type": "yahoo", "label": "美元指數(DXY)"},
        {"id": "CL=F", "type": "yahoo", "label": "原油期貨(WTI)"},
        {"id": "JPY=X", "type": "yahoo", "label": "美元兌日圓匯率"},
        {"id": "IEF", "type": "yahoo", "label": "7-10年期公債ETF(IEF)"},
        {"id": "HYG", "type": "yahoo", "label": "高收益債ETF(HYG)"},
        {"id": "LQD", "type": "yahoo", "label": "投資級公司債ETF(LQD)"},
        {"id": "^GSPC", "type": "yahoo", "label": "標普500指數"},
        {"id": "^IXIC", "type": "yahoo", "label": "那斯達克綜合指數"},
        {"id": "DGS10", "type": "fred", "label": "10年期公債殖利率(FRED)"},
        {"id": "DGS2", "type": "fred", "label": "2年期公債殖利率(FRED)"},
        {"id": "DGS3MO", "type": "fred", "label": "3個月期公債殖利率(FRED)"},
        {"id": "DGS30", "type": "fred", "label": "30年期公債殖利率(FRED)"},
        {"id": "T10YIE", "type": "fred", "label": "10年期損益平衡通膨率(FRED)"},
        {"id": "T5YIE", "type": "fred", "label": "5年期損益平衡通膨率(FRED)"},
        {"id": "BAMLH0A0HYM2", "type": "fred", "label": "高收益債利差(FRED)"},
        {"id": "WALCL", "type": "fred", "label": "聯準會資產負債表規模(FRED)"},
        {"id": "M2SL", "type": "fred", "label": "M2貨幣供給(FRED)"},
        {"id": "UNRATE", "type": "fred", "label": "失業率(FRED)"},
        {"id": "FEDFUNDS", "type": "fred", "label": "聯邦基金利率(FRED)"},
    ]
)



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
    unit_str = "殖利率變動 (bp)" if fva.TARGET == "UST_10Yr" else "報酬 (%)"
    fig.colorbar(im, ax=ax, shrink=0.8, label=unit_str)
    fig.tight_layout()
    return fva.fig_to_base64(fig)


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


# ================================================================ 第三關：穩定性
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

    score_full, raw_metric_full, ext_df_20y = build_candidate_score(config, ext_df_20y, ud.fetch_yahoo_close, ud.fetch_fred_series)

    out_start = pd.Timestamp(ud._G["output_start_date"])
    main_df_pre = ext_df_20y.loc[ext_df_20y.index >= out_start].copy()
    main_score_pre = score_full.reindex(main_df_pre.index)
    main_raw_pre = raw_metric_full.reindex(main_df_pre.index)

    result = {"key": key, "label": label, "config": config, "test_date": date.today().isoformat(),
              "raw_ranges": {k: (str(v[0].date()), str(v[1].date()), v[2]) for k, v in raw_ranges.items()}}

    # 五關固定全部跑完，不再因為某一關沒過就提早停止——這個平台的定位是研究輔助工具，
    # 只提供判斷建議，不擋結果，最終是否採用交給使用者自行判斷。任一關萬一因為資料
    # 太極端而算不出來，用try/except接住、記成「此關無法完成分析」，不讓整次測試中斷。
    print(f"[{label}] 第一關：資料健檢 ...")
    try:
        g1 = gate1_data_health(config, main_score_pre, main_raw_pre, ext_df_20y)
    except Exception as e:
        g1 = {"passed": None, "reasons": [f"此關計算失敗：{e}"]}
    result["gate1"] = g1

    print(f"[{label}] 第二關：單獨效力 ...")
    try:
        g2 = gate2_efficacy(key, score_full, ext_df_20y)
    except Exception as e:
        g2 = {"passed": None, "reasons": [f"此關計算失敗：{e}"], "main_df": main_df_pre}
    result["gate2"] = g2
    main_df = g2.get("main_df", main_df_pre)

    print(f"[{label}] 第三關：穩定性 ...")
    try:
        g3 = gate3_stability(key, main_df)
    except Exception as e:
        g3 = {"passed": None, "reasons": [f"此關計算失敗：{e}"]}
    result["gate3"] = g3

    print(f"[{label}] 第四關：增量價值 ...")
    try:
        g4 = gate4_incremental(key, main_df[key], main_df)
    except Exception as e:
        g4 = {"passed": None, "reasons": [f"此關計算失敗：{e}"]}
    result["gate4"] = g4

    print(f"[{label}] 第五關：可實作性 ...")
    try:
        g5 = gate5_implementability(main_df[key])
    except Exception as e:
        g5 = {"passed": None, "reasons": [f"此關計算失敗：{e}"]}
    result["gate5"] = g5

    # 整體建議：只統計「真的判斷出及格/不及格」的關卡(第一到四關；第五關换手率
    # 本身就沒有及格線，永遠不計入分母)，第五關永遠是資訊性質。
    judged = [g1, g2, g3, g4]
    n_judged = sum(1 for g in judged if g.get("passed") is not None)
    n_passed = sum(1 for g in judged if g.get("passed") is True)
    result["gates_passed"] = f"{n_passed}/{n_judged}" if n_judged else "無法判斷"

    if n_judged == 0:
        headline = "資料不足，無法完成關卡判斷"
    elif n_passed == n_judged:
        headline = f"{n_passed}/{n_judged}項關卡通過，初步判斷具備統計相關性，建議可以考慮"
    elif n_passed >= n_judged / 2:
        headline = f"{n_passed}/{n_judged}項關卡通過，部分指標有疑慮，建議謹慎評估後再決定"
    else:
        headline = f"{n_passed}/{n_judged}項關卡通過，多項指標不理想，建議不採用"
    result["final_verdict"] = f"{headline}——本工具僅提供研究建議，最終是否採用由使用者自行判斷。"
    result["stopped_at"] = None  # 不再有「停在哪一關」這件事，保留欄位是為了跟舊登記簿資料相容
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
        "gates_passed": result["gates_passed"],
    }
    g2 = result.get("gate2", {})
    if "main_ic" in g2:
        entry["main_ic"] = g2["main_ic"]["rho"]
        entry["monotonicity"] = g2["monotonicity"]
        entry["pattern_tag"] = g2["pattern_tag"]
    g4 = result.get("gate4", {})
    if "max_corr" in g4:
        entry["max_corr"] = g4["max_corr"]
        entry["max_corr_key"] = g4["max_corr_key"]
        entry["loo_delta"] = g4["delta"]
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


def score_trend_chart_base64(main_df, key, label):
    """圖1:分數走勢圖。背景疊五色情緒分級色帶(跟儀表板一致)，右軸疊美國10年期
    公債殖利率(UST_10Yr)當視覺參考——殖利率純粹對照用，不參與任何統計計算，
    這點也跟儀表板現有每個因子卡片的第一張圖完全一致的做法。"""
    if key not in main_df.columns:
        return None
    score = main_df[key].dropna()
    if score.empty:
        return None
    fig, ax = plt.subplots(figsize=(7.6, 3.6), dpi=140)
    prev = 0
    for i, th in enumerate(ud._G["label_thresholds"]):
        hi = min(th["lt"], 100)
        ax.axhspan(prev, hi, color=TIER_COLORS[i % len(TIER_COLORS)], alpha=0.10, zorder=0)
        prev = th["lt"]
    ax.plot(main_df.index, main_df[key], color="#1e3a5f", linewidth=1.2, label=label, zorder=3)
    ax.set_ylim(0, 100)
    ax.set_ylabel("分數 (0–100)", fontsize=9)
    ax.tick_params(labelsize=8)
    if "UST_10Yr" in main_df.columns:
        ax2 = ax.twinx()
        ax2.plot(main_df.index, main_df["UST_10Yr"], color="#a6742a", linewidth=1.0,
                  linestyle="--", alpha=0.75, zorder=2)
        ax2.set_ylabel("10年期公債殖利率 (%，僅供對照)", fontsize=9, color="#a6742a")
        ax2.tick_params(labelsize=8, colors="#a6742a")
    ax.set_title(f"{label}：分數走勢（疊加美國10年期公債殖利率，僅供對照）", fontsize=10)
    for spine in ["top"]:
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    return fva.fig_to_base64(fig)


def fear_greed_overlay_chart_base64(main_df, key, label, fear_threshold=25, greed_threshold=75):
    """圖1b：ZN期貨價格走勢 + 恐懼/貪婪散點疊圖。
    在ZN期貨的時間軸上，用綠點標出因子分數<25（極度恐懼）的日子，
    用紅點標出分數>75（極度貪婪）的日子，讓使用者直觀看到
    「恐懼/貪婪分別發生在哪個價位、哪個時間點」。"""
    target = fva.TARGET  # ZN_futures
    if target not in main_df.columns or key not in main_df.columns:
        return None
    price = main_df[target].dropna()
    score = main_df[key].reindex(price.index)
    if price.empty or score.dropna().empty:
        return None

    fear_mask = score < fear_threshold
    greed_mask = score > greed_threshold
    n_fear = int(fear_mask.sum())
    n_greed = int(greed_mask.sum())

    fig, ax = plt.subplots(figsize=(7.6, 3.6), dpi=140)

    # 底層：ZN期貨價格線
    ax.plot(price.index, price.values, color="#888888", linewidth=0.9, alpha=0.6, zorder=1)

    # 恐懼散點（綠色）
    if n_fear > 0:
        fear_dates = price.index[fear_mask.reindex(price.index, fill_value=False)]
        ax.scatter(fear_dates, price.loc[fear_dates], color="#2f6b4f", s=12, alpha=0.7,
                   edgecolors="none", zorder=3, label=f"分數<{fear_threshold} 極度恐懼（{n_fear}天）")

    # 貪婪散點（紅色）
    if n_greed > 0:
        greed_dates = price.index[greed_mask.reindex(price.index, fill_value=False)]
        ax.scatter(greed_dates, price.loc[greed_dates], color="#a6362f", s=12, alpha=0.7,
                   edgecolors="none", zorder=3, label=f"分數>{greed_threshold} 極度貪婪（{n_greed}天）")

    y_label = "10年期美債殖利率 (%)" if target == "UST_10Yr" else "ZN期貨價格"
    chart_title = f"{label}：恐懼與貪婪在10年期美債殖利率時間軸上的分布" if target == "UST_10Yr" else f"{label}：恐懼與貪婪在ZN期貨時間軸上的分布"
    ax.set_ylabel(y_label, fontsize=9)
    ax.set_title(chart_title, fontsize=10)
    ax.legend(fontsize=8, loc="upper left", frameon=False)
    ax.tick_params(labelsize=8)
    ax.spines["top"].set_visible(False)
    fig.tight_layout()
    return fva.fig_to_base64(fig)


def raw_data_chart_base64(config, main_df, label):
    """圖2:原始資料走勢圖。依候選因子選的轉換模式，對應現有七個因子在儀表板上
    各自第二張圖的呈現邏輯(例如動能秀ZN期貨+125日均線、殖利率曲線形狀秀
    10年期+2年期殖利率原始數值)。"""
    mode = config["mode"]
    sources = config["sources"]
    params = config.get("params", {})
    window = params.get("window")

    try:
        if mode in ("ma_deviation", "moving_average"):
            series, _ = _resolve_source(sources["series"], main_df)
            series = series.reindex(main_df.index)
            ma = series.rolling(window, min_periods=window).mean() if window else None
            fig, ax = plt.subplots(figsize=(7.6, 3.2), dpi=140)
            ax.plot(main_df.index, series, color="#1e3a5f", linewidth=1.1, label="原始數列")
            if ma is not None:
                ax.plot(main_df.index, ma, color="#a6742a", linewidth=1.1, label=f"{window}日移動平均")
        elif mode == "range_position":
            series, _ = _resolve_source(sources["series"], main_df)
            series = series.reindex(main_df.index)
            hi = series.rolling(window, min_periods=window).max() if window else None
            lo = series.rolling(window, min_periods=window).min() if window else None
            fig, ax = plt.subplots(figsize=(7.6, 3.2), dpi=140)
            ax.plot(main_df.index, series, color="#1e3a5f", linewidth=1.1, label="原始數列")
            if hi is not None:
                ax.plot(main_df.index, hi, color="#a6362f", linewidth=0.9, alpha=0.75, label=f"{window}日滾動高點")
                ax.plot(main_df.index, lo, color="#2f6b4f", linewidth=0.9, alpha=0.75, label=f"{window}日滾動低點")
        elif mode == "return_spread":
            series_a, _ = _resolve_source(sources["a"], main_df)
            series_b, _ = _resolve_source(sources["b"], main_df)
            series_a, series_b = series_a.reindex(main_df.index), series_b.reindex(main_df.index)
            base_a, base_b = series_a.dropna().iloc[0] if series_a.dropna().size else None, \
                series_b.dropna().iloc[0] if series_b.dropna().size else None
            fig, ax = plt.subplots(figsize=(7.6, 3.2), dpi=140)
            if base_a:
                ax.plot(main_df.index, series_a / base_a * 100, color="#1e3a5f", linewidth=1.1,
                        label="數列A（指數化，起點=100）")
            if base_b:
                ax.plot(main_df.index, series_b / base_b * 100, color="#a6742a", linewidth=1.1,
                        label="數列B（指數化，起點=100）")
        elif mode == "value_spread":
            series_a, _ = _resolve_source(sources["a"], main_df)
            series_b, _ = _resolve_source(sources["b"], main_df)
            series_a, series_b = series_a.reindex(main_df.index), series_b.reindex(main_df.index)
            fig, ax = plt.subplots(figsize=(7.6, 3.2), dpi=140)
            ax.plot(main_df.index, series_a, color="#1e3a5f", linewidth=1.1, label="數列A")
            ax.plot(main_df.index, series_b, color="#a6742a", linewidth=1.1, label="數列B")
        elif mode == "rolling_stat":
            series, _ = _resolve_source(sources["series"], main_df)
            series = series.reindex(main_df.index)
            med = series.rolling(window, min_periods=window).median() if window else None
            fig, ax = plt.subplots(figsize=(7.6, 3.2), dpi=140)
            ax.plot(main_df.index, series, color="#1e3a5f", linewidth=1.1, label="原始數列")
            if med is not None:
                ax.plot(main_df.index, med, color="#a6742a", linewidth=1.1, label=f"{window}日滾動中位數")
        else:
            return None
    except Exception:
        return None

    ax.legend(fontsize=8, loc="upper left", frameon=False)
    ax.tick_params(labelsize=8)
    ax.set_title(f"{label}：原始資料走勢", fontsize=10)
    ax.spines["top"].set_visible(False)
    fig.tight_layout()
    return fva.fig_to_base64(fig)


def render_screening_report(result):
    key, label = result["key"], result["label"]
    mode_label = TRANSFORM_MODES[result["config"]["mode"]]["label"]
    main_df = result.get("gate2", {}).get("main_df")

    sections = []

    # 圖1+圖1b+圖2固定放最前面,不管五道關卡跑得如何都會顯示(只要main_df算得出來)
    if main_df is not None:
        score_chart = score_trend_chart_base64(main_df, key, label)
        fg_overlay_chart = fear_greed_overlay_chart_base64(main_df, key, label)
        raw_chart = raw_data_chart_base64(result["config"], main_df, label)
        sections.append(f"""
    <section class="card">
      <h2><span class="bar"></span>分數走勢與原始資料</h2>
      {"<img class='chart' src='data:image/png;base64," + score_chart + "'/>" if score_chart else "<p class='na'>分數走勢圖資料不足</p>"}
      {"<img class='chart' src='data:image/png;base64," + fg_overlay_chart + "'/>" if fg_overlay_chart else ""}
      {"<img class='chart' src='data:image/png;base64," + raw_chart + "'/>" if raw_chart else "<p class='na'>原始資料走勢圖資料不足</p>"}
    </section>""")

    g1 = result.get("gate1", {})
    if "history_days" in g1:
        sections.append(f"""
    <section class="card">
      <h2><span class="bar"></span>第一關：資料健檢 {_gate_badge(g1.get("passed"))}</h2>
      <table class="data-table mini">
        <tr><th>有效資料天數</th><th>缺值比例</th><th>look-ahead檢查</th></tr>
        <tr><td>{g1["history_days"]}</td><td>{g1["missing_pct"]:.1f}%</td>
            <td>{"通過" if g1["lookahead_ok"] else "未通過"}（{g1["lookahead_detail"]}）</td></tr>
      </table>
      {"<ul>" + "".join(f"<li>{r}</li>" for r in g1["reasons"]) + "</ul>" if g1["reasons"] else ""}
    </section>""")
    else:
        sections.append(f"""
    <section class="card">
      <h2><span class="bar"></span>第一關：資料健檢 {_gate_badge(g1.get("passed"))}</h2>
      {"<ul>" + "".join(f"<li>{r}</li>" for r in g1.get("reasons", [])) + "</ul>" if g1.get("reasons") else "<p class='na'>無法完成此關分析</p>"}
    </section>""")

    g2 = result.get("gate2", {})
    if "ic_by_horizon" in g2:
        ic_rows = ""
        for h in HORIZONS:
            ov = fva.fmt_rho(g2["ic_by_horizon"][h]["overlap"])
            non_ov = fva.fmt_rho(g2["ic_by_horizon"][h]["non_overlap"])
            ic_rows += f"<tr><td>{h}日</td><td>{ov}</td><td>{non_ov}</td></tr>"
        unit_name = "變動(bp)" if fva.TARGET == "UST_10Yr" else "報酬"
        target_name = "10年期美債殖利率 (bp)" if fva.TARGET == "UST_10Yr" else "ZN報酬"
        decile10_chart = fva.decile_chart_base64(
            g2["decile_10"], f"{label}：未來{fva.DECILE_HORIZON}日平均{unit_name}（10分組，重疊取樣）",
            fva.DECILE_N_BUCKETS, fva.DECILE_HORIZON
        ) if g2["decile_10"] else None
        vigintile_buckets = fva._V["vigintile_n_buckets"]
        decile20_chart = fva.decile_chart_base64(
            g2["decile_20"], f"{label}：未來{fva.DECILE_HORIZON}日平均{unit_name}（{vigintile_buckets}分組，重疊取樣）",
            vigintile_buckets, fva.DECILE_HORIZON
        ) if g2["decile_20"] else None
        heatmap_raw_chart = heatmap_chart_base64(g2["heatmap_raw"], f"{label}：原始{unit_name}熱力圖（分桶×持有天數，重疊取樣）")
        heatmap_excess_chart = heatmap_chart_base64(
            g2["heatmap_excess"], f"{label}：超額{unit_name}熱力圖（扣除同期無條件平均買進持有，重疊取樣）"
        )
        sections.append(f"""
    <section class="card">
      <h2><span class="bar"></span>第二關：單獨效力 {_gate_badge(g2.get("passed"))}</h2>
      <p class="hint">型態標記：<b>{g2["pattern_tag"]}</b>（描述性標記，不當作及格條件——現有七因子裡多數呈現動能延續型，
        不是長期反轉型，這個標記純粹讓你知道候選因子屬於哪一種，不會因為不是反轉型就被判定不及格）</p>
      <h3>IC（vs 未來N日{target_name}，全平台一律以重疊取樣為主）</h3>
      <table class="data-table mini">
        <tr><th>持有天數</th><th>重疊</th><th>非重疊（對照參考）</th></tr>
        {ic_rows}
      </table>
      <p class="hint">分桶單調性（10年版本，重疊取樣）：{fva.fmt_num(g2["monotonicity"], 3) if g2["monotonicity"] is not None else "無資料"}</p>
      {"<img class='chart' src='data:image/png;base64," + decile10_chart + "'/>" if decile10_chart else "<p class='na'>10年分桶資料不足</p>"}
      {"<img class='chart' src='data:image/png;base64," + decile20_chart + "'/>" if decile20_chart else "<p class='na'>20年分桶資料不足</p>"}
      {"<img class='chart' src='data:image/png;base64," + heatmap_raw_chart + "'/>" if heatmap_raw_chart else "<p class='na'>熱力圖資料不足</p>"}
      {"<img class='chart' src='data:image/png;base64," + heatmap_excess_chart + "'/>" if heatmap_excess_chart else ""}
      {"<ul>" + "".join(f"<li>{r}</li>" for r in g2["reasons"]) + "</ul>" if g2["reasons"] else ""}
    </section>""")
    else:
        sections.append(f"""
    <section class="card">
      <h2><span class="bar"></span>第二關：單獨效力 {_gate_badge(g2.get("passed"))}</h2>
      {"<ul>" + "".join(f"<li>{r}</li>" for r in g2.get("reasons", [])) + "</ul>" if g2.get("reasons") else "<p class='na'>無法完成此關分析</p>"}
    </section>""")

    g3 = result.get("gate3", {})
    if "regime_ic" in g3:
        regime_rows = "".join(
            f"<tr><td>{label_}</td><td>{fva.fmt_rho(ic)}</td></tr>"
            for label_, ic in g3["regime_ic"].items()
        )
        sections.append(f"""
    <section class="card">
      <h2><span class="bar"></span>第三關：穩定性 {_gate_badge(g3.get("passed"))}</h2>
      <table class="data-table mini">
        <tr><th>全樣本</th><th>前半段</th><th>後半段</th><th>前後半段同號？</th></tr>
        <tr><td>{fva.fmt_rho(g3["ic_full"])}</td><td>{fva.fmt_rho(g3["ic_h1"])}</td>
            <td>{fva.fmt_rho(g3["ic_h2"])}</td><td>{"是" if g3["same_sign"] else "否"}</td></tr>
      </table>
      <h3>跨Fed循環IC（僅供參考，不擋關；重疊取樣）</h3>
      <table class="data-table mini"><tr><th>循環階段</th><th>IC</th></tr>{regime_rows}</table>
      <p class="hint">跨循環同號：{"是" if g3["regime_same_sign"] else ("否" if g3["regime_same_sign"] is False else "資料不足無法判斷")}</p>
      {"<ul>" + "".join(f"<li>{r}</li>" for r in g3["reasons"]) + "</ul>" if g3["reasons"] else ""}
    </section>""")
    else:
        sections.append(f"""
    <section class="card">
      <h2><span class="bar"></span>第三關：穩定性 {_gate_badge(g3.get("passed"))}</h2>
      {"<ul>" + "".join(f"<li>{r}</li>" for r in g3.get("reasons", [])) + "</ul>" if g3.get("reasons") else "<p class='na'>無法完成此關分析</p>"}
    </section>""")

    g4 = result.get("gate4", {})
    if "correlations" in g4:
        corr_rows = "".join(
            f"<tr><td>{k}</td><td>{v:+.2f}</td></tr>"
            for k, v in g4["correlations"].items()
        )
        sections.append(f"""
    <section class="card">
      <h2><span class="bar"></span>第四關：增量價值 {_gate_badge(g4.get("passed"))}</h2>
      <h3>跟現有七因子的相關係數</h3>
      <table class="data-table mini"><tr><th>因子</th><th>相關係數</th></tr>{corr_rows}</table>
      <p class="hint">最高相關：{g4["max_corr_key"]}（{g4["max_corr"]:+.2f}），門檻±{THRESHOLDS['max_correlation']}</p>
      <h3>Leave-one-out：加入候選因子對綜合分數IC的影響（重疊取樣）</h3>
      <p>不含候選：{fva.fmt_rho(g4["ic_without"])}　→　含候選：{fva.fmt_rho(g4["ic_with"])}
        （Δ = {f"{g4['delta']:+.3f}" if g4["delta"] is not None else "無資料"}，負值代表候選因子有正貢獻）</p>
      {"<ul>" + "".join(f"<li>{r}</li>" for r in g4["reasons"]) + "</ul>" if g4["reasons"] else ""}
    </section>""")
    else:
        sections.append(f"""
    <section class="card">
      <h2><span class="bar"></span>第四關：增量價值 {_gate_badge(g4.get("passed"))}</h2>
      {"<ul>" + "".join(f"<li>{r}</li>" for r in g4.get("reasons", [])) + "</ul>" if g4.get("reasons") else "<p class='na'>無法完成此關分析</p>"}
    </section>""")

    g5 = result.get("gate5", {})
    if "turnover_daily_avg" in g5:
        sections.append(f"""
    <section class="card">
      <h2><span class="bar"></span>第五關：可實作性 {_gate_badge(g5.get("passed"))}</h2>
      <p>平均每日部位變動量：{g5["turnover_daily_avg"]:.3f}（0=完全不動，2=從滿多轉滿空）　·
         部位方向改變次數：{g5["n_position_changes"]}</p>
      {"<ul>" + "".join(f"<li>{r}</li>" for r in g5["reasons"]) + "</ul>" if g5["reasons"] else ""}
    </section>""")
    else:
        sections.append(f"""
    <section class="card">
      <h2><span class="bar"></span>第五關：可實作性 {_gate_badge(g5.get("passed"))}</h2>
      {"<ul>" + "".join(f"<li>{r}</li>" for r in g5.get("reasons", [])) + "</ul>" if g5.get("reasons") else "<p class='na'>無法完成此關分析</p>"}
    </section>""")

    gp = result.get("gates_passed", "無法判斷")
    n_passed_str = gp.split("/")[0] if "/" in gp else "0"
    n_judged_str = gp.split("/")[1] if "/" in gp else "0"
    verdict_class = ("verdict-keep" if n_judged_str != "0" and int(n_passed_str) == int(n_judged_str)
                      else "verdict-watch" if n_judged_str != "0" and int(n_passed_str) >= int(n_judged_str) / 2
                      else "verdict-cut")
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>因子篩選：{label}</title>
<style>{fva.REPORT_CSS}
{nav_bar.NAV_BAR_CSS}
{PROMOTE_UI_CSS}</style>
</head>
<body>
<div class="wrap">
  {nav_bar.render_nav_bar("screening")}
  <header>
    <div class="kicker">FACTOR SCREENING</div>
    <h1>因子篩選：{label}</h1>
    <p class="meta">key：{key}　·　轉換模式：{mode_label}　·　測試日期：{result["test_date"]}　·　關卡通過：{gp}</p>
    <p class="disclaimer">{POSITIONING_STATEMENT}</p>
    <p class="disclaimer {verdict_class}">{result["final_verdict"]}</p>
  </header>
  {"".join(sections)}
  <section class="card promote-card">
    <h2><span class="bar"></span>升等為儀表板可選因子</h2>
    <p class="hint">
      覺得這個因子值得留著探索？升等後會在<b>儀表板</b>多一張分項卡片（標示「候選因子」，<b>不計入官方綜合分數</b>），
      也可以在儀表板「自訂權重」區塊選用它。不論上面幾道關卡通過與否都可以升等——這個平台只提供研究建議，
      最終要不要留著由你決定。升等後大約幾分鐘內會反映在正式儀表板上。
    </p>
    <details class="token-box" id="promoteTokenDetails">
      <summary>🔑 設定 GitHub Personal Access Token（跟因子篩選登記簿共用同一組）</summary>
      <input type="password" id="promoteGhToken" placeholder="ghp_xxxxxxxxxxxxxxxxx" autocomplete="off">
    </details>
    <button class="promote-btn" type="button" id="promoteBtn">🚀 升等為可選因子</button>
    <p class="hint" id="promoteStatus" style="margin-top:10px;"></p>
  </section>
</div>
<script>
  const PROMOTE_REPO_OWNER = "dp79b47tvn-maker";
  const PROMOTE_REPO_NAME = "bond-fear-greed-dashboard";
  const PROMOTE_CANDIDATE_CONFIG = {json.dumps(result["config"], ensure_ascii=False)};

  const promoteTokenInput = document.getElementById("promoteGhToken");
  const savedPromoteToken = localStorage.getItem("gh_pat_token");
  if (savedPromoteToken) {{
    promoteTokenInput.value = savedPromoteToken;
  }} else {{
    document.getElementById("promoteTokenDetails").open = true;
  }}

  document.getElementById("promoteBtn").addEventListener("click", async () => {{
    const token = promoteTokenInput.value.trim();
    const statusEl = document.getElementById("promoteStatus");
    const btn = document.getElementById("promoteBtn");
    if (!token) {{
      alert("請先填寫 GitHub Personal Access Token（PAT）！");
      document.getElementById("promoteTokenDetails").open = true;
      promoteTokenInput.focus();
      return;
    }}
    localStorage.setItem("gh_pat_token", token);
    btn.disabled = true;
    statusEl.textContent = "已送出升等請求，GitHub Actions 正在寫入設定並重新產生儀表板...";
    try {{
      const resp = await fetch(`https://api.github.com/repos/${{PROMOTE_REPO_OWNER}}/${{PROMOTE_REPO_NAME}}/actions/workflows/promote-factor.yml/dispatches`, {{
        method: "POST",
        headers: {{
          "Accept": "application/vnd.github+json",
          "Authorization": `Bearer ${{token}}`,
          "Content-Type": "application/json"
        }},
        body: JSON.stringify({{
          ref: "main",
          inputs: {{ config_json: JSON.stringify(PROMOTE_CANDIDATE_CONFIG) }}
        }})
      }});
      if (!resp.ok) {{
        const errText = await resp.text();
        throw new Error(`GitHub API 錯誤 (${{resp.status}}): ${{errText}}`);
      }}
      statusEl.textContent = "已成功送出！幾分鐘後到儀表板查看新的分項卡片與自訂權重選項。";
    }} catch (err) {{
      statusEl.textContent = "送出失敗：" + err.message;
      btn.disabled = false;
    }}
  }});
</script>
</body>
</html>"""



def _load_promoted_keys():
    """讀promoted_candidate_factors.json，回傳目前已升等的因子key集合，供登記簿頁
    標示「已升等」徽章＋退回按鈕。檔案不存在就回傳空集合，不報錯。"""
    if not os.path.exists("promoted_candidate_factors.json"):
        return set()
    with open("promoted_candidate_factors.json", encoding="utf-8") as f:
        staged = json.load(f)
    return {f["key"] for f in staged.get("factors", [])}


def _load_promoted_factors_list():
    """讀promoted_candidate_factors.json，回傳完整的候選因子清單(key+label)，
    供相關係數矩陣的勾選清單使用(不像_load_promoted_keys()只回傳key集合)。"""
    if not os.path.exists("promoted_candidate_factors.json"):
        return []
    with open("promoted_candidate_factors.json", encoding="utf-8") as f:
        staged = json.load(f)
    return staged.get("factors", [])


def _corr_factor_options():
    """相關係數矩陣勾選清單的選項：官方七項(score_col對照factor_definitions.json，
    跟factor_validation_analysis.FACTOR_COLS用同一套欄位命名) + 目前已升等的候選因子
    (欄位命名固定是promoted_{key}_score，見update_dashboard.py的compute_promoted_factors())。"""
    options = [
        {"value": fx["score_col"], "label": fx["name_tpl"].split(" ")[0], "kind": "official"}
        for fx in ud.DEFS["factors"]
    ]
    options += [
        {"value": f"promoted_{pf['key']}_score", "label": f"{pf['label']}（候選）", "kind": "candidate"}
        for pf in _load_promoted_factors_list()
    ]
    return options


def render_registry_index(registry):
    promoted_keys = _load_promoted_keys()
    corr_factor_checkboxes = "".join(
        f'<label class="checkbox-group corr-check"><input type="checkbox" class="corr-factor" value="{opt["value"]}" checked>{opt["label"]}</label>'
        for opt in _corr_factor_options()
    )
    rows = ""
    for idx, e in enumerate(reversed(registry)):
        row_id = f"{e['key']}_{idx}"
        gp = e.get("gates_passed", "無法判斷")
        n_p, n_j = (gp.split("/") if "/" in gp else ("0", "0"))
        verdict_type = ("keep" if n_j != "0" and int(n_p) == int(n_j)
                        else "watch" if n_j != "0" and int(n_p) >= int(n_j) / 2
                        else "cut")
        verdict_cls = f"verdict-{verdict_type}"
        is_promoted = e["key"] in promoted_keys
        promote_cell = (
            f'<span class="promoted-badge">已升等</span> '
            f'<button class="demote-btn" type="button" onclick="demoteFactor(this, \'{e["key"]}\', \'{e["label"]}\')">退回</button>'
            if is_promoted else '<span class="na">—</span>'
        )
        report_url = f"screening_{e['key']}.html"
        rows += f"""<tr class="registry-row" data-row-id="{row_id}" data-key="{e['key']}" data-verdict="{verdict_type}" data-promoted="{'true' if is_promoted else 'false'}" data-search="{e['label'].lower()} {e['key'].lower()}">
          <td>{e["test_date"]}</td>
          <td>
            <button id="toggle-btn-{row_id}" class="expand-toggle-btn" data-label="{e['label']}" onclick="toggleInlineReport('{row_id}', '{report_url}', '{e['label']}')">
              <span class="arrow-icon">▶</span> {e['label']}
            </button>
          </td>
          <td>{TRANSFORM_MODES[e['mode']]['label']}</td>
          <td>{fva.fmt_num(e.get('main_ic'), 3) if e.get('main_ic') is not None else '—'}</td>
          <td>{e.get('pattern_tag', '—')}</td>
          <td>{gp}</td>
          <td class="{verdict_cls}">{e['final_verdict']}</td>
          <td>{promote_cell}</td>
        </tr>
        <tr id="expand-row-{row_id}" class="inline-report-row" style="display:none;">
          <td colspan="8" class="inline-report-cell">
            <div class="inline-report-wrap">
              <div class="inline-report-bar">
                <span class="inline-report-title">📊 因子體檢報告：{e['label']} ({e['key']})</span>
                <div class="inline-report-actions">
                  <a class="inline-link" href="{report_url}" target="_blank">在新分頁開啟 ↗</a>
                  <button class="inline-close-btn" onclick="closeInlineReport('{row_id}')">✕ 關閉報告</button>
                </div>
              </div>
              <iframe id="iframe-{row_id}" class="inline-iframe" data-src="{report_url}"></iframe>
            </div>
          </td>
        </tr>"""

    n_total = len(registry)
    n_keep = sum(
        1 for e in registry
        if "/" in e.get("gates_passed", "") and e["gates_passed"].split("/")[1] != "0"
        and e["gates_passed"].split("/")[0] == e["gates_passed"].split("/")[1]
    )
    n_watch = sum(
        1 for e in registry
        if "/" in e.get("gates_passed", "") and e["gates_passed"].split("/")[1] != "0"
        and int(e["gates_passed"].split("/")[0]) >= int(e["gates_passed"].split("/")[1]) / 2
        and e["gates_passed"].split("/")[0] != e["gates_passed"].split("/")[1]
    )
    n_cut = sum(
        1 for e in registry
        if "/" in e.get("gates_passed", "") and e["gates_passed"].split("/")[1] != "0"
        and int(e["gates_passed"].split("/")[0]) < int(e["gates_passed"].split("/")[1]) / 2
    )
    n_promoted = sum(1 for e in registry if e["key"] in promoted_keys)
    n_passed = n_keep
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>因子開發與篩選平台 · 債券市場恐懼貪婪</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:#f4f5f7; color:#161a23; font-family:-apple-system,BlinkMacSystemFont,"PingFang TC","Noto Sans TC","Segoe UI",Roboto,sans-serif; line-height:{page_style.BASE_LINE_HEIGHT}; }}
  .wrap {{ max-width:{page_style.CONTENT_MAX_WIDTH}; margin:0 auto; padding:44px 24px 80px; }}
  header {{ margin-bottom:28px; }}
  .kicker {{ font-family:ui-monospace,"SF Mono",Menlo,monospace; font-size:11px; letter-spacing:0.12em; color:#a6742a; font-weight:700; margin-bottom:10px; }}
  h1 {{ font-size:{page_style.H1_SIZE}; font-weight:700; margin:0 0 12px; letter-spacing:-0.02em; }}
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
  .promoted-badge {{ display:inline-block; font-size:11px; font-weight:700; color:#2f6b4f;
    background:rgba(47,107,79,0.1); border-radius:999px; padding:3px 10px; white-space:nowrap; }}
  .demote-btn {{ border:1px solid #dfe2e8; border-radius:6px; background:#fff; color:#a6362f;
    font-size:11.5px; padding:4px 10px; cursor:pointer; white-space:nowrap; margin-left:4px; }}
  .demote-btn:hover {{ border-color:#a6362f; background:rgba(166,54,47,0.06); }}
  .demote-btn:disabled {{ opacity:.55; cursor:not-allowed; }}

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
  .corr-factor-grid {{ display:flex; flex-wrap:wrap; gap:10px 18px; margin-top:10px; }}
  .corr-check {{ margin-top:0; font-size:13px; font-weight:normal; color:#161a23; cursor:pointer; }}
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
  .registry-controls {{ display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:12px; margin-bottom:14px; background:#f8fafc; padding:12px 16px; border-radius:10px; border:1px solid #dfe2e8; }}
  .registry-filters {{ display:flex; gap:6px; flex-wrap:wrap; }}
  .filter-tab-btn {{ background:#fff; border:1px solid #cbd5e1; border-radius:6px; padding:5px 12px; font-size:12px; font-weight:600; color:#475569; cursor:pointer; transition:all .15s ease; }}
  .filter-tab-btn:hover {{ background:#f1f5f9; border-color:#94a3b8; }}
  .filter-tab-btn.active {{ background:#1e3a5f; color:#fff; border-color:#1e3a5f; }}
  .registry-search-wrap {{ position:relative; width:220px; }}
  .registry-search-wrap input {{ padding:6px 10px; font-size:12.5px; border-radius:6px; border:1px solid #cbd5e1; width:100%; background:#fff; outline:none; }}
  .registry-search-wrap input:focus {{ border-color:#1e3a5f; }}

  .expand-toggle-btn {{ background:none; border:none; padding:0; color:#1e3a5f; font-weight:700; font-size:13px; text-align:left; cursor:pointer; display:inline-flex; align-items:center; gap:6px; }}
  .expand-toggle-btn:hover {{ text-decoration:underline; color:#0f172a; }}
  .expand-toggle-btn .arrow-icon {{ font-size:10px; color:#a6742a; transition:transform .15s ease; }}

  .inline-report-row {{ background:#f8fafc; }}
  .inline-report-cell {{ padding:12px 16px !important; border-bottom:2px solid #cbd5e1 !important; }}
  .inline-report-wrap {{ background:#fff; border:1px solid #dfe2e8; border-radius:10px; padding:14px; box-shadow:0 4px 12px rgba(0,0,0,0.05); }}
  .inline-report-bar {{ display:flex; justify-content:space-between; align-items:center; padding-bottom:10px; margin-bottom:10px; border-bottom:1px solid #e5e7eb; }}
  .inline-report-title {{ font-size:14px; font-weight:700; color:#1e3a5f; }}
  .inline-report-actions {{ display:flex; gap:10px; align-items:center; }}
  .inline-link {{ font-size:12px; color:#2563eb; text-decoration:none; font-weight:600; }}
  .inline-link:hover {{ text-decoration:underline; }}
  .inline-close-btn {{ background:#f1f5f9; border:1px solid #cbd5e1; border-radius:6px; padding:4px 10px; font-size:11.5px; cursor:pointer; color:#475569; font-weight:600; }}
  .inline-close-btn:hover {{ background:#e2e8f0; color:#0f172a; }}
  .inline-iframe {{ width:100%; height:950px; border:none; border-radius:8px; background:#fff; }}

  .pagination-bar {{ display:flex; justify-content:space-between; align-items:center; padding-top:14px; margin-top:10px; border-top:1px solid #e5e7eb; font-size:12.5px; color:#64748b; }}
  .page-btn {{ background:#fff; border:1px solid #cbd5e1; border-radius:6px; padding:4px 12px; font-size:12px; cursor:pointer; color:#334155; font-weight:600; }}
  .page-btn:hover:not(:disabled) {{ background:#f1f5f9; }}
  .page-btn:disabled {{ opacity:.4; cursor:not-allowed; }}

  .combo-wrap {{ position:relative; }}
  .combo-list {{
    display:none; position:absolute; top:calc(100% + 4px); left:0; right:0; z-index:20;
    background:#fff; border:1px solid #dfe2e8; border-radius:10px; box-shadow:0 8px 24px rgba(22,26,35,0.12);
    max-height:280px; overflow-y:auto;
  }}
  .combo-item {{ padding:9px 12px; font-size:13px; cursor:pointer; display:flex; align-items:center; gap:8px; border-bottom:1px solid #f0f1f3; }}
  .combo-item:last-child {{ border-bottom:none; }}
  .combo-item:hover {{ background:#f4f5f7; }}
  .combo-tag {{
    font-size:10.5px; font-weight:700; color:#a6742a; background:rgba(166,116,42,0.1);
    border-radius:5px; padding:2px 6px; flex-shrink:0;
  }}
  .combo-id {{ margin-left:auto; color:#a7adb9; font-size:11.5px; font-variant-numeric:tabular-nums; flex-shrink:0; }}
  .combo-empty {{ padding:12px; font-size:12.5px; color:#a7adb9; font-style:italic; }}
  .manual-source-group {{ margin-top:10px; padding-top:10px; border-top:1px dashed #dfe2e8; }}
  {nav_bar.NAV_BAR_CSS}
</style>
</head>
<body>
<div class="wrap">
  {nav_bar.render_nav_bar("screening")}
  <header>
    <div class="kicker">FACTOR DISCOVERY &amp; SCREENING</div>
    <h1>因子開發與篩選平台</h1>
    <p class="meta">累計測試 {n_total} 個因子，各關卡全數通過 {n_passed} 個。</p>
    <p class="disclaimer">{POSITIONING_STATEMENT}</p>
    <p class="disclaimer">
      這份登記簿記錄「每一次」測試過的因子，不論結果通過與否都會保留紀錄與完整報告。您可以在下方<b>輸入新因子進行線上驗證</b>，運算完成後，分析圖表與 5 道關卡報告會<b>直接在此頁面上展示出來</b>。
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
            <option value="ma_spread">均線價差百分位 (Single Series - N-day SMA)</option>
            <option value="range_position">區間位置 (N-day High/Low Range Position 0-100)</option>
            <option value="return_spread">兩序列報酬差百分位 (Series A N-day Ret - Series B N-day Ret)</option>
            <option value="value_spread">兩序列差值百分位 (Series A - Series B)</option>
            <option value="moving_average">移動平均百分位 (N-day SMA)</option>
            <option value="rolling_stat">滾動統計量百分位 (N-day Skew / StdDev)</option>
          </select>
        </div>
        <div class="form-group full">
          <label for="sourceSearch">資料來源 A（可輸入中文關鍵字或代號搜尋，例如「十年期公債」或「DGS10」）</label>
          <div class="combo-wrap">
            <input type="text" id="sourceSearch" class="combo-input" placeholder="打字搜尋，例如：十年期公債 / DGS10 / VIX" autocomplete="off"
                   oninput="filterSourceCombo('')" onfocus="filterSourceCombo('')" onblur="hideComboLater('')">
            <div class="combo-list" id="sourceComboList"></div>
          </div>
          <p class="hint">
            <label style="font-weight:normal;cursor:pointer;">
              <input type="checkbox" id="sourceManualToggle" onchange="toggleManualSource('')" style="width:auto;height:auto;vertical-align:middle;">
              找不到？手動輸入類型與代號
            </label>
          </p>
          <div class="manual-source-group form-grid" id="manualSourceGroup" style="display:none;">
            <div class="form-group">
              <label for="sourceType">資料來源類型</label>
              <select id="sourceType">
                <option value="yahoo">Yahoo Finance (代號如 ^VIX)</option>
                <option value="fred">FRED 經濟數據 (代號如 DGS10)</option>
                <option value="existing">儀表板既有欄位 (UST_10Yr 等)</option>
              </select>
            </div>
            <div class="form-group">
              <label for="sourceId">資料來源代號</label>
              <input type="text" id="sourceId" placeholder="例: ^VIX / DGS10 / UST_10Yr">
            </div>
          </div>
        </div>
        <div class="form-group full source-b-group" style="display:none;">
          <label for="sourceSearchB">資料來源 B（可輸入中文關鍵字或代號搜尋）</label>
          <div class="combo-wrap">
            <input type="text" id="sourceSearchB" class="combo-input" placeholder="打字搜尋，例如：短債 / SHY / DGS2" autocomplete="off"
                   oninput="filterSourceCombo('B')" onfocus="filterSourceCombo('B')" onblur="hideComboLater('B')">
            <div class="combo-list" id="sourceComboListB"></div>
          </div>
          <p class="hint">
            <label style="font-weight:normal;cursor:pointer;">
              <input type="checkbox" id="sourceManualToggleB" onchange="toggleManualSource('B')" style="width:auto;height:auto;vertical-align:middle;">
              找不到？手動輸入類型與代號
            </label>
          </p>
          <div class="manual-source-group form-grid" id="manualSourceGroupB" style="display:none;">
            <div class="form-group">
              <label for="sourceBType">資料來源類型</label>
              <select id="sourceBType">
                <option value="yahoo">Yahoo Finance</option>
                <option value="fred">FRED</option>
                <option value="existing">儀表板既有欄位</option>
              </select>
            </div>
            <div class="form-group">
              <label for="sourceBId">資料來源代號</label>
              <input type="text" id="sourceBId" placeholder="例: SHY / DGS2">
            </div>
          </div>
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

  <!-- 因子相關係數矩陣（隨選，取代原本驗證報告裡固定範圍的相關矩陣） -->
  <section class="card">
    <h2><span class="bar"></span>🔗 產生因子相關係數矩陣</h2>
    <p class="hint">
      勾選想比較的因子（官方七項＋目前已升等的候選因子），產生兩兩相關係數熱力圖——用來看因子之間是不是在講同一件事（相關係數太高代表訊息重複、加進來邊際價值有限）。運算完成後會直接顯示在下方，不用等每日自動報告。
    </p>
    <details class="token-box" id="corrTokenDetails">
      <summary>🔑 GitHub Personal Access Token（跟上面表單共用同一組）</summary>
      <input type="password" id="corrGhToken" placeholder="ghp_xxxxxxxxxxxxxxxxx" autocomplete="off">
    </details>
    <div class="corr-factor-grid">
      {corr_factor_checkboxes}
    </div>
    <button class="btn-submit" type="button" id="corrSubmitBtn" style="margin-top:14px;">📊 產生相關係數矩陣</button>
    <p class="hint" id="corrStatus" style="margin-top:10px;"></p>
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

  <!-- 歷史紀錄表格卡片 -->
  <section class="card">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:12px;">
      <h2 style="margin:0;"><span class="bar"></span>歷史測試紀錄登記簿 <span style="font-size:12px;font-weight:normal;color:#667085;margin-left:6px;">(點擊因子名稱可直接在下方展開報告圖表)</span></h2>
    </div>

    <!-- 篩選控制與搜尋列 (防止列表越來越長) -->
    <div class="registry-controls">
      <div class="registry-filters">
        <button class="filter-tab-btn active" data-filter="all" onclick="filterRegistry('all')">全部 ({n_total})</button>
        <button class="filter-tab-btn" data-filter="keep" onclick="filterRegistry('keep')">通過 ({n_keep})</button>
        <button class="filter-tab-btn" data-filter="watch" onclick="filterRegistry('watch')">觀察 ({n_watch})</button>
        <button class="filter-tab-btn" data-filter="cut" onclick="filterRegistry('cut')">淘汰 ({n_cut})</button>
        <button class="filter-tab-btn" data-filter="promoted" onclick="filterRegistry('promoted')">已升等 ({n_promoted})</button>
      </div>
      <div class="registry-search-wrap">
        <input type="text" id="registrySearchInput" placeholder="🔍 搜尋因子名稱 / 代號..." oninput="onRegistrySearchInput()">
      </div>
    </div>

    <table class="data-table" id="registryTable">
      <thead>
        <tr><th>測試日期</th><th>因子 (點擊名稱展開報告)</th><th>轉換模式</th><th>IC(20日,重疊取樣)</th><th>型態標記</th><th>關卡通過</th><th>結果</th><th>儀表板狀態</th></tr>
      </thead>
      <tbody id="registryTbody">
        {rows if rows else "<tr><td colspan='8' class='na'>尚無測試記錄</td></tr>"}
      </tbody>
    </table>

    <!-- 分頁控制列 -->
    <div class="pagination-bar" id="paginationBar">
      <div id="pageInfo">顯示 1 - 6 / 共 {n_total} 筆</div>
      <div style="display:flex;gap:6px;">
        <button class="page-btn" id="prevPageBtn" onclick="changePage(-1)">‹ 上一頁</button>
        <button class="page-btn" id="nextPageBtn" onclick="changePage(1)">下一頁 ›</button>
      </div>
    </div>
  </section>
</div>

<script>
  const REPO_OWNER = "dp79b47tvn-maker";
  const REPO_NAME = "bond-fear-greed-dashboard";
  const SOURCE_CATALOG = {json.dumps(SOURCE_CATALOG, ensure_ascii=False)};
  const SOURCE_TYPE_LABEL = {{ yahoo: "Yahoo", fred: "FRED", existing: "既有" }};

  function zhNumToArabic(str) {{
    // 目錄裡的中文說明一律用阿拉伯數字(10年期、2年期...)，但使用者可能習慣打
    // 中文數字(十年期、兩年期)——這裡把查詢字串裡的中文數字轉成阿拉伯數字再比對，
    // 不然「十年期公債」這種很自然的搜法會因為字面對不上而完全找不到東西。
    const d = {{"零":0,"一":1,"二":2,"兩":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9}};
    return str.replace(/[一二兩三四五六七八九]?十[一二兩三四五六七八九]?|[零一二兩三四五六七八九]/g, (m) => {{
      if (m.includes("十")) {{
        const idx = m.indexOf("十");
        const tensChar = m.slice(0, idx), onesChar = m.slice(idx + 1);
        const tens = tensChar ? d[tensChar] : 1;
        const ones = onesChar ? d[onesChar] : 0;
        return String(tens * 10 + ones);
      }}
      return String(d[m]);
    }});
  }}

  function filterSourceCombo(sfx) {{
    const input = document.getElementById(`sourceSearch${{sfx}}`);
    const listEl = document.getElementById(`sourceComboList${{sfx}}`);
    const qRaw = input.value.trim().toLowerCase();
    const qNorm = zhNumToArabic(input.value.trim()).toLowerCase();
    let matches = qRaw
      ? SOURCE_CATALOG.filter(item => {{
          const hay = (item.id + " " + item.label).toLowerCase();
          return hay.includes(qRaw) || (qNorm !== qRaw && hay.includes(qNorm));
        }})
      : SOURCE_CATALOG;
    matches = matches.slice(0, 8);
    if (!matches.length) {{
      listEl.innerHTML = `<div class="combo-empty">找不到符合的資料來源，可勾選下方「手動輸入」</div>`;
      listEl.style.display = "block";
      return;
    }}
    listEl.innerHTML = matches.map((item, i) =>
      `<div class="combo-item" data-idx="${{SOURCE_CATALOG.indexOf(item)}}">
        <span class="combo-tag">${{SOURCE_TYPE_LABEL[item.type]}}</span>${{item.label}}
        <span class="combo-id">${{item.id}}</span>
      </div>`
    ).join("");
    listEl.querySelectorAll(".combo-item").forEach(el => {{
      el.addEventListener("mousedown", (ev) => {{
        ev.preventDefault();
        const item = SOURCE_CATALOG[parseInt(el.dataset.idx, 10)];
        selectSourceCombo(sfx, item);
      }});
    }});
    listEl.style.display = "block";
  }}

  function selectSourceCombo(sfx, item) {{
    const input = document.getElementById(`sourceSearch${{sfx}}`);
    input.value = item.label;
    input.dataset.type = item.type;
    input.dataset.id = item.id;
    document.getElementById(`sourceComboList${{sfx}}`).style.display = "none";
  }}

  function hideComboLater(sfx) {{
    setTimeout(() => {{
      const listEl = document.getElementById(`sourceComboList${{sfx}}`);
      if (listEl) listEl.style.display = "none";
    }}, 150);
  }}

  function toggleManualSource(sfx) {{
    const manual = document.getElementById(`sourceManualToggle${{sfx}}`).checked;
    document.getElementById(`manualSourceGroup${{sfx}}`).style.display = manual ? "grid" : "none";
    const input = document.getElementById(`sourceSearch${{sfx}}`);
    input.disabled = manual;
    if (manual) {{
      input.value = "";
      delete input.dataset.type;
      delete input.dataset.id;
    }}
  }}

  function getSourceSpec(sfx) {{
    const manual = document.getElementById(`sourceManualToggle${{sfx}}`).checked;
    if (manual) {{
      const type = document.getElementById(`sourceType${{sfx}}`).value;
      const id = document.getElementById(`sourceId${{sfx}}`).value.trim();
      return id ? {{ type, id }} : null;
    }}
    const input = document.getElementById(`sourceSearch${{sfx}}`);
    return (input.dataset.type && input.dataset.id) ? {{ type: input.dataset.type, id: input.dataset.id }} : null;
  }}

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

  let currentRegistryFilter = 'all';
  let registrySearchQuery = '';
  let currentRegistryPage = 1;
  const registryPageSize = 6;
  let currentExpandedKey = null;

  let currentRegistryFilter = 'all';
  let registrySearchQuery = '';
  let currentRegistryPage = 1;
  const registryPageSize = 6;
  let currentExpandedKey = null;

  function toggleInlineReport(key, reportUrl, label) {{
    const expandRow = document.getElementById('expand-row-' + key);
    const iframe = document.getElementById('iframe-' + key);
    const toggleBtn = document.getElementById('toggle-btn-' + key);
    
    if (expandRow && expandRow.style.display === 'table-row') {{
      closeInlineReport(key);
    }} else {{
      if (currentExpandedKey && currentExpandedKey !== key) {{
        closeInlineReport(currentExpandedKey);
      }}
      if (iframe && (!iframe.src || iframe.src === '' || iframe.src.indexOf(reportUrl) === -1)) {{
        iframe.src = reportUrl;
      }}
      if (expandRow) expandRow.style.display = 'table-row';
      if (toggleBtn) {{
        const arrow = toggleBtn.querySelector('.arrow-icon');
        if (arrow) arrow.textContent = '▼';
      }}
      currentExpandedKey = key;
      if (expandRow) expandRow.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
    }}
  }}

  function closeInlineReport(key) {{
    const expandRow = document.getElementById('expand-row-' + key);
    const toggleBtn = document.getElementById('toggle-btn-' + key);
    if (expandRow) expandRow.style.display = 'none';
    if (toggleBtn) {{
      const arrow = toggleBtn.querySelector('.arrow-icon');
      if (arrow) arrow.textContent = '▶';
    }}
    if (currentExpandedKey === key) currentExpandedKey = null;
  }}

  function filterRegistry(filterType) {{
    currentRegistryFilter = filterType;
    document.querySelectorAll('.filter-tab-btn').forEach(btn => {{
      btn.classList.toggle('active', btn.getAttribute('data-filter') === filterType);
    }});
    currentRegistryPage = 1;
    applyRegistryFilterAndPaging();
  }}

  function onRegistrySearchInput() {{
    registrySearchQuery = document.getElementById('registrySearchInput').value.trim().toLowerCase();
    currentRegistryPage = 1;
    applyRegistryFilterAndPaging();
  }}

  function changePage(delta) {{
    currentRegistryPage += delta;
    applyRegistryFilterAndPaging();
  }}

  function applyRegistryFilterAndPaging() {{
    const rows = Array.from(document.querySelectorAll('#registryTbody tr.registry-row'));
    let visibleRows = [];

    rows.forEach(row => {{
      const verdict = row.getAttribute('data-verdict');
      const isPromoted = row.getAttribute('data-promoted') === 'true';
      const searchText = row.getAttribute('data-search') || '';
      const rowId = row.getAttribute('data-row-id') || row.getAttribute('data-key');
      const expandRow = document.getElementById('expand-row-' + rowId);

      let matchFilter = true;
      if (currentRegistryFilter === 'keep') matchFilter = (verdict === 'keep');
      else if (currentRegistryFilter === 'watch') matchFilter = (verdict === 'watch');
      else if (currentRegistryFilter === 'cut') matchFilter = (verdict === 'cut');
      else if (currentRegistryFilter === 'promoted') matchFilter = isPromoted;

      let matchSearch = true;
      if (registrySearchQuery) matchSearch = searchText.includes(registrySearchQuery);

      if (matchFilter && matchSearch) {{
        visibleRows.push({{ row, expandRow }});
      }} else {{
        row.style.display = 'none';
        if (expandRow) expandRow.style.display = 'none';
      }}
    }});

    const totalVisible = visibleRows.length;
    const totalPages = Math.ceil(totalVisible / registryPageSize) || 1;
    if (currentRegistryPage > totalPages) currentRegistryPage = totalPages;
    if (currentRegistryPage < 1) currentRegistryPage = 1;

    const startIdx = (currentRegistryPage - 1) * registryPageSize;
    const endIdx = startIdx + registryPageSize;

    visibleRows.forEach(({{ row, expandRow }}, idx) => {{
      if (idx >= startIdx && idx < endIdx) {{
        row.style.display = 'table-row';
      }} else {{
        row.style.display = 'none';
        if (expandRow) expandRow.style.display = 'none';
      }}
    }});

    const pageInfo = document.getElementById('pageInfo');
    const prevBtn = document.getElementById('prevPageBtn');
    const nextBtn = document.getElementById('nextPageBtn');

    if (totalVisible === 0) {{
      if (pageInfo) pageInfo.textContent = '無符合條件的測試記錄';
      if (prevBtn) prevBtn.disabled = true;
      if (nextBtn) nextBtn.disabled = true;
    }} else {{
      if (pageInfo) pageInfo.textContent = `顯示 ${{startIdx + 1}} - ${{Math.min(endIdx, totalVisible)}} / 共 ${{totalVisible}} 筆 (第 ${{currentRegistryPage}} / ${{totalPages}} 頁)`;
      if (prevBtn) prevBtn.disabled = (currentRegistryPage === 1);
      if (nextBtn) nextBtn.disabled = (currentRegistryPage === totalPages);
    }}
  }}

  document.addEventListener('DOMContentLoaded', () => {{
    applyRegistryFilterAndPaging();
  }});

  function loadReport(reportUrl, label) {{
    const viewer = document.getElementById("reportViewer");
    const frame = document.getElementById("reportFrame");
    const title = document.getElementById("reportViewerTitle");
    if (title) title.innerText = "📊 因子分析報告與圖表：" + (label || "");
    if (frame) frame.src = reportUrl;
    if (viewer) {{
      viewer.style.display = "block";
      viewer.scrollIntoView({{ behavior: "smooth" }});
    }}
  }}

  function closeReportViewer() {{
    const viewer = document.getElementById("reportViewer");
    if (viewer) viewer.style.display = "none";
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
    const isTwoSources = (mode === "return_spread" || mode === "value_spread");

    const specA = getSourceSpec("");
    if (!specA) {{
      alert("請選擇資料來源 A（用搜尋框選一個，或勾選「手動輸入」自己填類型與代號）！");
      return;
    }}
    const specB = isTwoSources ? getSourceSpec("B") : null;
    if (isTwoSources && !specB) {{
      alert("這個轉換模式需要資料來源 B，請選擇或手動輸入！");
      return;
    }}
    const sourceType = specA.type;
    const sourceId = specA.id;
    const sourceBType = specB ? specB.type : "none";
    const sourceBId = specB ? specB.id : "";
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

  async function demoteFactor(btn, key, label) {{
    if (!confirm(`確定要把「${{label}}」從儀表板退回嗎？\\n這會觸發GitHub Actions直接commit+push到正式站，把它從儀表板的分項卡片與自訂權重選項裡移除。`)) return;
    let token = localStorage.getItem("gh_pat_token");
    if (!token) {{
      token = prompt("請輸入 GitHub Personal Access Token（跟升等按鈕共用同一組）：");
      if (!token) return;
      localStorage.setItem("gh_pat_token", token);
    }}
    btn.disabled = true;
    btn.textContent = "退回中...";
    try {{
      const resp = await fetch(`https://api.github.com/repos/${{REPO_OWNER}}/${{REPO_NAME}}/actions/workflows/promote-factor.yml/dispatches`, {{
        method: "POST",
        headers: {{
          "Accept": "application/vnd.github+json",
          "Authorization": `Bearer ${{token}}`,
          "Content-Type": "application/json"
        }},
        body: JSON.stringify({{ ref: "main", inputs: {{ remove_key: key }} }})
      }});
      if (!resp.ok) {{
        const errText = await resp.text();
        throw new Error(`GitHub API 錯誤 (${{resp.status}}): ${{errText}}`);
      }}
      btn.textContent = "已送出";
      alert("已送出退回請求，幾分鐘後重新整理這頁即可看到狀態更新。");
    }} catch (err) {{
      alert("退回失敗：" + err.message);
      btn.disabled = false;
      btn.textContent = "退回";
    }}
  }}

  const corrGhTokenInput = document.getElementById("corrGhToken");
  const savedCorrToken = localStorage.getItem("gh_pat_token");
  if (savedCorrToken) {{
    corrGhTokenInput.value = savedCorrToken;
  }} else {{
    document.getElementById("corrTokenDetails").open = true;
  }}

  document.getElementById("corrSubmitBtn").addEventListener("click", async () => {{
    const token = corrGhTokenInput.value.trim();
    const statusEl = document.getElementById("corrStatus");
    const btn = document.getElementById("corrSubmitBtn");
    const keys = Array.from(document.querySelectorAll(".corr-factor:checked")).map(el => el.value);
    if (keys.length < 2) {{
      alert("至少要勾選兩個因子才能算相關係數矩陣！");
      return;
    }}
    if (!token) {{
      alert("請先填寫 GitHub Personal Access Token（PAT）！");
      document.getElementById("corrTokenDetails").open = true;
      corrGhTokenInput.focus();
      return;
    }}
    localStorage.setItem("gh_pat_token", token);
    btn.disabled = true;
    statusEl.textContent = "已送出請求，GitHub Actions 正在計算相關係數矩陣並產生熱力圖...";
    try {{
      const resp = await fetch(`https://api.github.com/repos/${{REPO_OWNER}}/${{REPO_NAME}}/actions/workflows/correlation-matrix.yml/dispatches`, {{
        method: "POST",
        headers: {{
          "Accept": "application/vnd.github+json",
          "Authorization": `Bearer ${{token}}`,
          "Content-Type": "application/json"
        }},
        body: JSON.stringify({{ ref: "main", inputs: {{ factor_keys: keys.join(",") }} }})
      }});
      if (!resp.ok) {{
        const errText = await resp.text();
        throw new Error(`GitHub API 錯誤 (${{resp.status}}): ${{errText}}`);
      }}
      statusEl.textContent = "已成功送出，正在等待報告產生（約1-2分鐘）...";
      pollForCorrelationMatrix();
    }} catch (err) {{
      statusEl.textContent = "送出失敗：" + err.message;
      btn.disabled = false;
    }}
  }});

  function pollForCorrelationMatrix() {{
    const reportUrl = `correlation_matrix.html?t=${{Date.now()}}`;
    const statusEl = document.getElementById("corrStatus");
    const btn = document.getElementById("corrSubmitBtn");
    let attempts = 0;
    const maxAttempts = 24;
    const interval = setInterval(async () => {{
      attempts++;
      try {{
        const resp = await fetch(reportUrl, {{ method: "HEAD", cache: "no-store" }});
        if (resp.status === 200) {{
          clearInterval(interval);
          statusEl.textContent = "🎉 相關係數矩陣已產生，顯示於下方。";
          btn.disabled = false;
          loadReport(reportUrl, "因子相關係數矩陣");
        }}
      }} catch (e) {{}}
      if (attempts >= maxAttempts) {{
        clearInterval(interval);
        statusEl.textContent = "等待逾時：請稍後重新整理頁面查看結果。";
        btn.disabled = false;
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
    rebuild_index()
    print(f"\n完成！{result['final_verdict']}")
    print(f"報告：{report_path}")
    print(f"登記簿：{CHART_DIR}/screening_index.html")
    return result


def rebuild_index():
    """只重新產生screening_index.html，不重跑任何因子測試——升等/退回候選因子後
    用這個刷新登記簿頁的「已升等」徽章跟按鈕狀態，不需要知道任何因子的原始config。"""
    os.makedirs(CHART_DIR, exist_ok=True)
    registry = _load_registry()
    index_html = render_registry_index(registry)
    with open(os.path.join(CHART_DIR, "screening_index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)
    print(f"登記簿已重新產生：{CHART_DIR}/screening_index.html")


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2 and sys.argv[1] == "--rebuild-index":
        rebuild_index()
    elif len(sys.argv) < 2:
        print("用法：python3 factor_screening.py <candidate_config.json>")
        print("      python3 factor_screening.py --rebuild-index")
        sys.exit(1)
    else:
        with open(sys.argv[1], encoding="utf-8") as f:
            cfg = json.load(f)
        screen_and_save(cfg)
