"""
債券恐懼貪婪儀表板 — 一條龍更新腳本

用法：
    python3 update_dashboard.py

流程：
  1. 自動從 Yahoo Finance 抓 ZN=F、NQ=F（那斯達克100期貨）、TLT、SHY、^MOVE，
     從 Treasury.gov 抓10年期＋2年期殖利率，從 FRED 抓 CPI（CPIAUCSL）與
     10年期損益兩平通膨率（T10YIE）
  2. 讀取 data_input.xlsx（DataInput 分頁）——你手動填的歷史數據「優先」於自動抓取值：
       - Date          日期（必填，格式 2021-01-04 或 2021/1/4 皆可）
       - ZN_futures    ZN期貨收盤價（可留空，自動抓）
       - NQ_futures    NQ期貨（那斯達克100）收盤價（可留空，自動抓）
       - TLT           TLT（20年期以上美債ETF）收盤價（可留空，自動抓）
       - SHY           SHY（1-3年期美債ETF）收盤價（可留空，自動抓）
       - MOVE_index    MOVE指數（可留空，自動抓）
       - UST_10Yr      10年期殖利率（可留空，自動抓）
       - UST_2Yr       2年期殖利率（可留空，自動抓）
       - put_call_ratio  Put/Call比率（唯一沒有自動來源的欄位，要靠你填）
     檔案不存在時會自動建立空白模板。
  3. 計算七項分數（動能/強度/存續期間避險/PutCall/波動度/殖利率曲線/通膨意外）與綜合分數
       - 動能：ZN期貨對125日均線乖離率
       - 強度：NQ期貨在過去252個交易日高低區間的相對位置
       - 存續期間避險：TLT對SHY的40日報酬差，反映債券市場內部風險偏好
       - Put/Call：使用者提供的put/call比率5日均值
       - 波動度：MOVE指數90日滾動偏態係數（反轉）；50日中位數乖離率降為輔助欄位
       - 殖利率曲線形狀：10年期減2年期利差（2s10s），越陡峭分數越高
       - 通膨意外：CPI年增率減10年期損益兩平通膨率（市場隱含通膨預期），越意外走高分數越低（反轉）
         【資料限制】拿不到「經濟學家共識預期」的歷史資料（免費來源只有即時snapshot，
         沒有回溯到2020年的歷史深度），改用「債券市場自己的通膨定價」當基準，
         概念上更接近「通膨市場定價是否落後於實際數據」而非「單次公布的驚喜/失望」。
  4. 【禁止引用未來資料】所有滾動計算（125日均線、252日高低、40日報酬、5年百分位）都只用
     「當天以前（含當天）」的資料，是嚴格的向後看窗口（trailing window），絕不使用未來才發生
     的價格。每次執行都會自動跑 assert_no_lookahead_bias() 驗證：用「只給到某一天為止」的
     截斷資料重算該天分數，比對跟正式輸出是否一致，不一致就直接報錯中止，不會悄悄產出有問題
     的分數。
  5. 輸出 bond_fear_greed_v2.csv、bond_dashboard_data_input.xlsx（審閱用）
  6.【實驗性】如果 regime_weights_v1.json 存在，額外算一版「情境加權分數」——
     用Fed利率循環階段動態調整原始四個分項的權重（權重是凍結在某個時間點推導出來的，
     不會每天重新校準，這樣未來累積的新資料才能拿來做真正的樣本外驗證；新增的殖利率曲線
     與通膨意外這兩項因子目前還沒納入這個實驗性權重，見 derive_regime_weights.py）。
  7. 自動把最新資料注入 chart/dashboard.html（用 chart/dashboard_template.html 當模板）
"""
import io
import json
import math
import os
import time
from datetime import date

import regime_lib

import numpy as np
import pandas as pd
import requests
import yfinance as yf

# ---- 唯一事實來源:所有計算參數與因子定義都在 factor_definitions.json ----
# 想改因子的視窗天數、門檻等,改那個檔就好,這裡不再寫死任何參數。
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "factor_definitions.json"), encoding="utf-8") as _f:
    DEFS = json.load(_f)
_G = DEFS["global"]
_FP = {f["key"]: f["params"] for f in DEFS["factors"]}

FETCH_START_DATE = _G["fetch_start_date"]
OUTPUT_START_DATE = _G["output_start_date"]
END_DATE = date.today().isoformat()

INPUT_XLSX = "data_input.xlsx"
INPUT_COLS = ["ZN_futures", "NQ_futures", "TLT", "SHY", "MOVE_index", "UST_10Yr", "UST_2Yr", "put_call_ratio"]

TREASURY_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve"
    "&field_tdr_date_value={year}&page&_format=csv"
)
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"


# ---------------------------------------------------------------- fetch
def fetch_yahoo_close(ticker, name):
    for attempt in range(3):
        try:
            df = yf.download(ticker, start=FETCH_START_DATE, end=END_DATE, progress=False, auto_adjust=False)
            break
        except Exception as e:
            print(f"  重試 {attempt + 1}/3 ({ticker}): {e}")
            time.sleep(2)
    else:
        raise RuntimeError(f"無法下載 {ticker}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    s = df["Close"].rename(name)
    s.index = pd.to_datetime(s.index).tz_localize(None)
    return s


def fetch_treasury_yield_curve():
    """回傳 (UST_10Yr, UST_2Yr) 兩條 Series。"""
    frames = []
    for year in range(int(FETCH_START_DATE[:4]), date.today().year + 1):
        resp = requests.get(TREASURY_URL.format(year=year), timeout=30)
        resp.raise_for_status()
        frames.append(pd.read_csv(io.StringIO(resp.text)))
    combined = pd.concat(frames, ignore_index=True)
    combined["Date"] = pd.to_datetime(combined["Date"], format="%m/%d/%Y")
    combined = combined.set_index("Date").sort_index()
    col10 = [c for c in combined.columns if c.strip() == "10 Yr"][0]
    col2 = [c for c in combined.columns if c.strip() == "2 Yr"][0]
    return combined[col10].rename("UST_10Yr"), combined[col2].rename("UST_2Yr")


def fetch_fred_series(series_id, name):
    """FRED 的 fredgraph.csv 端點不需要 API 金鑰，直接回傳單一序列的 CSV。"""
    resp = requests.get(FRED_CSV_URL.format(series_id=series_id), timeout=30)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text))
    df.columns = ["Date", name]
    df["Date"] = pd.to_datetime(df["Date"])
    s = pd.to_numeric(df.set_index("Date")[name], errors="coerce").dropna()
    return s[s.index >= pd.Timestamp(FETCH_START_DATE)]


# ---------------------------------------------------------------- Excel input
def ensure_input_template():
    """data_input.xlsx 不存在時建立空白模板（絕不覆蓋既有檔案）。"""
    if os.path.exists(INPUT_XLSX):
        return
    instructions = pd.DataFrame({
        "說明": [
            "在 DataInput 分頁填入你手上的歷史數據，填哪一欄就導入哪一欄。",
            "欄位：Date、ZN_futures、NQ_futures、TLT、SHY、MOVE_index、UST_10Yr、UST_2Yr、put_call_ratio。",
            "Date 欄必填；其他欄位留空的日期會自動用 Yahoo/Treasury/FRED 抓的值。",
            "你填的數字「優先」於自動抓取值（可用來修正錯誤報價）。",
            "put_call_ratio 是唯一沒有自動來源的欄位，Put/Call 分項要靠這欄。",
            "填完存檔後執行：python3 update_dashboard.py，全部重算並更新儀表板。",
            "日期格式 2021-01-04 或 2021/1/4 皆可；不需要按順序排。",
        ]
    })
    template = pd.DataFrame(columns=["Date"] + INPUT_COLS)
    with pd.ExcelWriter(INPUT_XLSX, engine="openpyxl") as writer:
        instructions.to_excel(writer, sheet_name="使用說明", index=False)
        template.to_excel(writer, sheet_name="DataInput", index=False)
    print(f"已建立空白輸入模板：{INPUT_XLSX}")


def load_user_input():
    """讀取使用者填的 Excel；回傳 {欄名: Series}，沒填的欄不回傳。"""
    if not os.path.exists(INPUT_XLSX):
        return {}
    try:
        df = pd.read_excel(INPUT_XLSX, sheet_name="DataInput")
    except Exception as e:
        print(f"讀取 {INPUT_XLSX} 失敗（{e}），忽略使用者輸入")
        return {}
    if "Date" not in df.columns or df.empty:
        return {}
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"]).set_index("Date").sort_index()
    out = {}
    for col in INPUT_COLS:
        if col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(s):
                out[col] = s
                print(f"  導入使用者數據 {col}：{len(s)} 筆（{s.index.min().date()} ~ {s.index.max().date()}）")
    return out


# ---------------------------------------------------------------- scoring
def rolling_percentile_score(series, window_days=None, min_periods=None):
    if window_days is None:
        window_days = _G["percentile_window_days"]
    if min_periods is None:
        min_periods = window_days

    def pct_rank_of_last(window):
        return (window <= window[-1]).mean() * 100

    return series.rolling(window=window_days, min_periods=min_periods).apply(pct_rank_of_last, raw=True)


def label_fn(s):
    if pd.isna(s):
        return None
    for th in _G["label_thresholds"]:
        if s < th["lt"]:
            return th["label"]
    return _G["label_thresholds"][-1]["label"]


SCORE_COLS = [
    "momentum_score", "strength_score", "duration_score", "putcall_score",
    "move_score", "curve_score", "inflation_score",
]


def compute_scores(df):
    """在合併好的原始資料(df)上算出所有衍生分數欄位。

    【禁止引用未來資料規則】這裡的每一步都只用 pandas .rolling()（預設向後看的
    trailing window，絕不是 center=True），所以任何一天的分數只可能用到「當天以前
    （含當天）」的資料。main() 跟 assert_no_lookahead_bias() 都呼叫同一份函式，
    確保驗證邏輯跟正式輸出邏輯完全一致，不會各算各的。
    """
    df = df.copy()

    # ---- 1) 動能：US 10Y對均線價差（視窗天數見 factor_definitions.json）----
    _sma_w = _FP["momentum"]["sma_window"]
    df["UST10Y_SMA125"] = df["UST_10Yr"].rolling(_sma_w, min_periods=_sma_w).mean()
    df["momentum_spread"] = df["UST_10Yr"] - df["UST10Y_SMA125"]
    df["momentum_score"] = 100 - rolling_percentile_score(df["momentum_spread"])

    # ---- 2) 強度：NQ期貨（那斯達克100期貨）在高低區間位置 ----
    _rng_w = _FP["strength"]["range_window"]
    roll_max = df["NQ_futures"].rolling(_rng_w, min_periods=_rng_w).max()
    roll_min = df["NQ_futures"].rolling(_rng_w, min_periods=_rng_w).min()
    df["nq_252d_high"] = roll_max
    df["nq_252d_low"] = roll_min
    df["strength_score"] = (df["NQ_futures"] - roll_min) / (roll_max - roll_min) * 100

    # ---- 3) 存續期間避險：TLT對SHY的報酬差 ----
    _ret_w = _FP["duration"]["return_window"]
    df["TLT_ret40"] = (df["TLT"] / df["TLT"].shift(_ret_w) - 1) * 100
    df["SHY_ret40"] = (df["SHY"] / df["SHY"].shift(_ret_w) - 1) * 100
    df["duration_spread"] = df["TLT_ret40"] - df["SHY_ret40"]
    # 利差越高＝長天期跑贏＝願意冒存續期間風險追價＝貪婪，不用反轉，直接用百分位
    df["duration_score"] = rolling_percentile_score(df["duration_spread"])

    # ---- 4) Put/Call：均值 → 百分位反轉 ----
    _pc_w = _FP["putcall"]["avg_window"]
    _pc_min = _FP["putcall"]["min_periods"]
    df["put_call_ratio"] = pd.to_numeric(df["put_call_ratio"], errors="coerce")
    if df["put_call_ratio"].notna().any():
        df["put_call_5d_avg"] = df["put_call_ratio"].rolling(_pc_w, min_periods=_pc_w).mean()
        pc_pct = rolling_percentile_score(df["put_call_5d_avg"], min_periods=_pc_min)
        df["putcall_score"] = 100 - pc_pct
    else:
        df["put_call_5d_avg"] = pd.NA
        df["putcall_score"] = pd.NA

    # ---- 5) 波動度：MOVE指數滾動偏態係數（主要評分依據，反轉百分位） ----
    _skew_w = _FP["move"]["skew_window"]
    _med_w = _FP["move"]["median_window"]
    df["move_skew_90d"] = df["MOVE_index"].rolling(_skew_w, min_periods=_skew_w).skew()
    # 偏態係數越高（正偏態＝近期MOVE常急速飆高、右尾拉長）＝恐懼，分數應偏低，所以用 100−百分位反轉
    df["move_score"] = 100 - rolling_percentile_score(df["move_skew_90d"])

    # 輔助欄位：對滾動中位數的乖離率（不參與任何分數計算，僅供圖表旁補充參考）
    df["move_50d_median"] = df["MOVE_index"].rolling(_med_w, min_periods=_med_w).median()
    df["move_deviation_pct"] = (df["MOVE_index"] - df["move_50d_median"]) / df["move_50d_median"] * 100

    # ---- 6) 殖利率曲線形狀：10年期減2年期利差（2s10s） ----
    df["curve_spread"] = df["UST_10Yr"] - df["UST_2Yr"]
    # 利差越高（越陡峭）＝經濟循環相對正常＝貪婪；利差越負（倒掛越深）＝衰退疑慮＝恐懼，不用反轉
    df["curve_score"] = rolling_percentile_score(df["curve_spread"])

    # ---- 7) 通膨意外：CPI年增率 減 10年期損益兩平通膨率（市場隱含通膨預期） ----
    _yoy_d = _FP["inflation"]["yoy_shift_days"]
    df["CPI_YoY"] = (df["CPI_index"] / df["CPI_index"].shift(_yoy_d) - 1) * 100
    df["inflation_surprise"] = df["CPI_YoY"] - df["Breakeven_10Y"]
    # 意外越高（實際通膨遠高於市場定價）＝恐慌訊號，分數應偏低，所以用 100−百分位反轉
    df["inflation_score"] = 100 - rolling_percentile_score(df["inflation_surprise"])

    for c in SCORE_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["composite_score"] = df[SCORE_COLS].mean(axis=1, skipna=True)
    df["composite_score"] = df["composite_score"].where(df[SCORE_COLS].notna().any(axis=1))
    df["label"] = df["composite_score"].apply(label_fn)
    return df


def assert_no_lookahead_bias(raw_df, full_scored_df, n_samples=8):
    """驗證『禁止引用未來資料』規則：抽樣幾個歷史日期，只給該日期以前的資料重算一次分數，
    結果必須跟正式輸出（用完整資料算出來的）逐項相同——如果不同，代表某個計算偷看了未來資料，
    直接中止程式，不會讓有問題的分數流入儀表板。
    """
    valid_dates = full_scored_df.dropna(subset=SCORE_COLS, how="all").index
    if len(valid_dates) < 10:
        print("（資料太少，略過未來資料檢查）")
        return
    sample_idx = pd.Index(sorted(set(
        valid_dates[int(q * (len(valid_dates) - 1))] for q in
        [i / (n_samples - 1) for i in range(n_samples)]
    )))

    mismatches = []
    for d in sample_idx:
        truncated_raw = raw_df.loc[:d]
        recomputed = compute_scores(truncated_raw)
        recomputed_row = recomputed.iloc[-1]
        official_row = full_scored_df.loc[d]
        for col in SCORE_COLS + ["composite_score"]:
            a, b = recomputed_row[col], official_row[col]
            both_nan = pd.isna(a) and pd.isna(b)
            if not both_nan and not (pd.notna(a) and pd.notna(b) and abs(a - b) < 1e-6):
                mismatches.append((d.date(), col, a, b))

    if mismatches:
        detail = "\n".join(f"  {d} {col}: 截斷重算={a} vs 正式輸出={b}" for d, col, a, b in mismatches)
        raise RuntimeError(
            "未來資料檢查失敗！以下日期的分數在「只給過去資料」重算時對不上正式輸出，"
            f"代表計算邏輯可能引用了未來資料：\n{detail}"
        )
    print(f"✓ 未來資料檢查通過（抽樣 {len(sample_idx)} 個日期，無look-ahead bias）")


def main():
    ensure_input_template()

    print("下載 ZN=F ...")
    zn = fetch_yahoo_close("ZN=F", "ZN_futures")
    print("下載 NQ=F (那斯達克100期貨) ...")
    nq = fetch_yahoo_close("NQ=F", "NQ_futures")
    print("下載 TLT ...")
    tlt = fetch_yahoo_close("TLT", "TLT")
    print("下載 SHY ...")
    shy = fetch_yahoo_close("SHY", "SHY")
    print("下載 ^MOVE ...")
    move = fetch_yahoo_close("^MOVE", "MOVE_index")
    print("下載 Treasury 10年期＋2年期殖利率 ...")
    ust10, ust2 = fetch_treasury_yield_curve()
    print("下載 FRED CPI (CPIAUCSL) ...")
    cpi = fetch_fred_series("CPIAUCSL", "CPI_index")
    print("下載 FRED 10年期損益兩平通膨率 (T10YIE) ...")
    breakeven = fetch_fred_series("T10YIE", "Breakeven_10Y")

    full_index = pd.date_range(FETCH_START_DATE, END_DATE, freq="D")
    df = pd.concat([zn, nq, tlt, shy, move, ust10, ust2, cpi, breakeven], axis=1, sort=True).reindex(full_index)
    df.index.name = "Date"
    df["put_call_ratio"] = pd.NA

    # ---- 使用者 Excel 數據覆蓋/補充 ----
    print(f"讀取 {INPUT_XLSX} ...")
    user = load_user_input()
    for col, s in user.items():
        s = s[~s.index.duplicated(keep="last")].reindex(full_index)
        df[col] = s.combine_first(pd.to_numeric(df[col], errors="coerce"))

    df = df.sort_index().ffill()
    df = df.dropna(how="all")
    first_valid = df.apply(lambda c: c.first_valid_index()).min()
    df = df.loc[first_valid:]
    df["put_call_ratio"] = pd.to_numeric(df["put_call_ratio"], errors="coerce")

    # 禁止引用未來資料：資料只保留到今天為止，絕不含未來日期
    assert df.index.max() <= pd.Timestamp(date.today()), "偵測到未來日期的資料列，中止執行"

    raw_df = df  # 保留合併後、算分數前的原始資料，供未來資料檢查重算使用
    df = compute_scores(df)
    score_cols = SCORE_COLS

    if df["putcall_score"].notna().any():
        print("Put/Call 分項：已納入計算")
    else:
        print("Put/Call 分項：尚無數據（在 data_input.xlsx 填入 put_call_ratio 後重跑即可）")

    print("執行未來資料檢查 ...")
    assert_no_lookahead_bias(raw_df, df)

    out = df.loc[OUTPUT_START_DATE:]

    # 存續期間避險原始走勢圖用的指數化序列：以圖表可視範圍的第一天為基準=100
    tlt_base = out["TLT"].iloc[0]
    shy_base = out["SHY"].iloc[0]
    out = out.copy()
    out["TLT_indexed"] = out["TLT"] / tlt_base * 100
    out["SHY_indexed"] = out["SHY"] / shy_base * 100

    # ---- 【實驗性】情境加權分數：用凍結的權重快照，不會每天重新校準 ----
    # 注意：這個實驗性權重目前只涵蓋原始四項（動能/強度/存續期間避險/波動度），
    # 新增的殖利率曲線與通膨意外還沒納入，見 derive_regime_weights.py。
    out["regime_fed"] = out.index.map(regime_lib.fed_cycle_label)

    regime_meta = None
    if os.path.exists("regime_weights_v1.json"):
        with open("regime_weights_v1.json", encoding="utf-8") as f:
            regime_meta = json.load(f)
        weight_table = regime_meta["weight_by_regime"]

        def _regime_weighted_score(row):
            regime = row["regime_fed"]
            if regime not in weight_table:
                return np.nan
            w = weight_table[regime]
            total_w, total_score = 0.0, 0.0
            for score_col, score_label in regime_lib.FACTOR_SCORE_COLS.items():
                v = row[score_col]
                if pd.isna(v):
                    continue
                total_score += v * w[score_label]
                total_w += w[score_label]
            return total_score / total_w if total_w else np.nan

        out["regime_score"] = out.apply(_regime_weighted_score, axis=1)
        print(f"情境加權分數（實驗性）：已套用凍結於 {regime_meta['freeze_date']} 的權重快照 v1")
    else:
        print("找不到 regime_weights_v1.json，略過情境加權分數（先執行 derive_regime_weights.py 產生權重快照）")

    # ---- 輸出 CSV / 審閱 Excel ----
    out.sort_index(ascending=False).to_csv("bond_fear_greed_v2.csv")
    with pd.ExcelWriter("bond_dashboard_data_input.xlsx", engine="openpyxl") as writer:
        raw_cols = ["UST_10Yr", "UST10Y_SMA125", "momentum_spread", "NQ_futures", "nq_252d_high", "nq_252d_low",
                    "TLT", "SHY", "TLT_ret40", "SHY_ret40", "duration_spread",
                    "MOVE_index", "move_skew_90d", "move_50d_median", "move_deviation_pct",
                    "UST_10Yr", "UST_2Yr", "curve_spread", "CPI_index", "CPI_YoY", "Breakeven_10Y",
                    "inflation_surprise", "put_call_ratio", "put_call_5d_avg"]
        out[raw_cols].to_excel(writer, sheet_name="RawData")
        out[score_cols + ["composite_score", "label"]].to_excel(writer, sheet_name="Scores")

    # ---- 產生 JSON 並注入 HTML ----
    def safe(v, nd=3):
        if v is None or pd.isna(v):
            return None
        return round(float(v), nd)

    records = []
    for d, row in out.iterrows():
        records.append({
            "date": d.strftime("%Y-%m-%d"),
            "score": safe(row["composite_score"], 2),
            "label": row["label"] if isinstance(row["label"], str) else None,
            "ust10yr": safe(row["UST_10Yr"], 2),
            "momentum": safe(row["momentum_score"], 2),
            "strength": safe(row["strength_score"], 2),
            "duration": safe(row["duration_score"], 2),
            "putcall": safe(row["putcall_score"], 2),
            "move": safe(row["move_score"], 2),
            "curve": safe(row["curve_score"], 2),
            "inflation": safe(row["inflation_score"], 2),
            "regimeScore": safe(row["regime_score"], 2) if regime_meta else None,
            "regimeFed": row["regime_fed"] if isinstance(row["regime_fed"], str) else None,
            "raw": {
                "us10y": safe(row["UST_10Yr"]),
                "sma125": safe(row["UST10Y_SMA125"]),
                "spread": safe(row["momentum_spread"], 2),
                "nq": safe(row["NQ_futures"]),
                "hi252": safe(row["nq_252d_high"]),
                "lo252": safe(row["nq_252d_low"]),
                "tlt": safe(row["TLT"]),
                "shy": safe(row["SHY"]),
                "tlt_ret40": safe(row["TLT_ret40"], 2),
                "shy_ret40": safe(row["SHY_ret40"], 2),
                "spread": safe(row["duration_spread"], 2),
                "tlt_idx": safe(row["TLT_indexed"], 2),
                "shy_idx": safe(row["SHY_indexed"], 2),
                "move": safe(row["MOVE_index"], 2),
                "move_median50": safe(row["move_50d_median"], 2),
                "move_dev_pct": safe(row["move_deviation_pct"], 2),
                "move_skew90": safe(row["move_skew_90d"], 3),
                "pc5d": safe(row["put_call_5d_avg"], 2),
                "pc_raw": safe(row["put_call_ratio"], 3),
                "ust10": safe(row["UST_10Yr"], 2),
                "ust2": safe(row["UST_2Yr"], 2),
                "curve_spread": safe(row["curve_spread"], 2),
                "cpi_yoy": safe(row["CPI_YoY"], 2),
                "breakeven": safe(row["Breakeven_10Y"], 2),
                "inflation_surprise": safe(row["inflation_surprise"], 2),
            },
        })
    data_json = json.dumps(records, ensure_ascii=False)
    with open("chart/dashboard_v2_data.json", "w") as f:
        f.write(data_json)

    if regime_meta:
        regime_meta_out = {
            "freeze_date": regime_meta["freeze_date"],
            "derived_from_data_range": regime_meta["derived_from_data_range"],
            "method_description": regime_meta["method"]["description"],
            "horizon_trading_days": regime_meta["method"]["horizon_trading_days"],
            "weight_by_regime": regime_meta["weight_by_regime"],
        }
    else:
        regime_meta_out = None
    regime_meta_json = json.dumps(regime_meta_out, ensure_ascii=False)

    # ---- 因子定義注入(唯一事實來源):名稱/kicker/說明文字經token替換後給前端 ----
    import re as _re

    def _sub_tokens(text, params):
        merged = {**_G, **params}
        return _re.sub(r"\{(\w+)\}", lambda m: str(merged.get(m.group(1), m.group(0))), text)

    factor_defs_out = {
        fx["key"]: {
            "kicker": fx["kicker"],
            "name": _sub_tokens(fx["name_tpl"], fx["params"]),
            "explain": _sub_tokens(fx["explain_tpl"], fx["params"]),
        }
        for fx in DEFS["factors"]
    }
    factor_defs_json = json.dumps(factor_defs_out, ensure_ascii=False)

    # ---- 跨頁連結(artifact_urls.json;空值退回本機相對路徑) ----
    try:
        with open("artifact_urls.json", encoding="utf-8") as f:
            urls = json.load(f)
    except FileNotFoundError:
        urls = {}
    link_manual = urls.get("manual") or "manual.html"
    link_report = urls.get("report") or "factor_validation_report.html"
    link_hub = urls.get("hub") or "index.html"

    with open("chart/dashboard_template.html") as f:
        template = f.read()
    for ph in ["__DATA_JSON__", "__REGIME_META_JSON__", "__FACTOR_DEFS_JSON__",
               "__LINK_MANUAL__", "__LINK_REPORT__", "__LINK_HUB__"]:
        assert ph in template, f"模板缺少 {ph} 佔位符"
    out_html = (template
                .replace("__DATA_JSON__", data_json)
                .replace("__REGIME_META_JSON__", regime_meta_json)
                .replace("__FACTOR_DEFS_JSON__", factor_defs_json)
                .replace("__LINK_MANUAL__", link_manual)
                .replace("__LINK_REPORT__", link_report)
                .replace("__LINK_HUB__", link_hub))
    with open("chart/dashboard.html", "w") as f:
        f.write(out_html)

    latest = records[-1]
    print(f"\n完成！共 {len(records)} 天（{records[0]['date']} ~ {latest['date']}）")
    print(f"最新綜合分數：{latest['score']}（{latest['label']}）  "
          f"動能 {latest['momentum']} / 強度 {latest['strength']} / 存續期間避險 {latest['duration']} / "
          f"PutCall {latest['putcall']} / 波動度 {latest['move']} / 殖利率曲線 {latest['curve']} / 通膨意外 {latest['inflation']}")
    print("chart/dashboard.html 已更新")


if __name__ == "__main__":
    main()
