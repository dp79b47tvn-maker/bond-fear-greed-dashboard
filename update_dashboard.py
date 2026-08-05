"""
債券恐懼貪婪儀表板 — 一條龍更新腳本

用法：
    python3 update_dashboard.py

流程：
  1. 自動從 Yahoo Finance 抓 ZN=F、HG=F（銅期貨）、GC=F（金期貨），
     從 Treasury.gov 抓10年期殖利率
  2. 讀取 data_input.xlsx（DataInput 分頁）——你手動填的歷史數據「優先」於自動抓取值：
       - Date          日期（必填，格式 2021-01-04 或 2021/1/4 皆可）
       - ZN_futures    ZN期貨收盤價（可留空，自動抓）
       - UST_10Yr      10年期殖利率（可留空，自動抓）
     （欄位表裡另外還有 NQ_futures/TLT/SHY/MOVE_index/UST_2Yr/put_call_ratio——這些是
     2026-08-05之前七項分數版本留下的欄位，保留只是為了向下相容既有的 data_input.xlsx
     結構，目前的兩項分數計算完全不會讀它們。）
     檔案不存在時會自動建立空白模板。
  3. 計算兩項分數（動能/銅金比）與綜合分數
       - 動能：ZN期貨對125日均線乖離率
       - 銅金比：HG=F（銅期貨）對GC=F（金期貨）40日報酬差，銅相對金走強＝風險偏好回升
  4. 【禁止引用未來資料】所有滾動計算（125日均線、40日報酬、5年百分位）都只用
     「當天以前（含當天）」的資料，是嚴格的向後看窗口（trailing window），絕不使用未來才發生
     的價格。每次執行都會自動跑 assert_no_lookahead_bias() 驗證：用「只給到某一天為止」的
     截斷資料重算該天分數，比對跟正式輸出是否一致，不一致就直接報錯中止，不會悄悄產出有問題
     的分數。
  5. 輸出 bond_fear_greed_v2.csv、bond_dashboard_data_input.xlsx（審閱用）
  6.【實驗性，已停用】regime_score「情境加權分數」的權重快照(regime_weights_v1.json)是
     依照舊版七項分數校準的，2026-08-05改成兩項分數後權重對不上，程式碼保留但不執行
     （見 REGIME_SCORE_ENABLED），之後要恢復需要用 derive_regime_weights.py 重新校準。
  7. 自動把最新資料注入 chart/dashboard.html（用 chart/dashboard_template.html 當模板）
"""
import io
import json
import math
import os
import time
from datetime import date

import nav_bar
import page_style
import regime_lib
from transform_modes import rolling_percentile_score, _resolve_source, build_candidate_score

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
    if "Close" not in df.columns:
        if isinstance(df.columns, pd.MultiIndex) and "Close" in df.columns.get_level_values(0):
            s = df["Close"]
        else:
            s = pd.Series(dtype=float)
    else:
        s = df["Close"]

    if isinstance(s, pd.DataFrame):
        s = s.iloc[:, 0]

    s = s.rename(name)
    s.index = pd.to_datetime(s.index).tz_localize(None)
    return s


def fetch_treasury_yield_curve():
    """回傳 (UST_10Yr, UST_2Yr) 兩條 Series。"""
    frames = []
    import time
    for year in range(int(FETCH_START_DATE[:4]), date.today().year + 1):
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        resp = requests.get(TREASURY_URL.format(year=year), timeout=30, headers=headers)
        resp.raise_for_status()
        frames.append(pd.read_csv(io.StringIO(resp.text)))
        time.sleep(0.5)
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
# rolling_percentile_score 定義在 transform_modes.py 共用(跟factor_screening.py的
# 候選因子分數計算共用同一份邏輯，避免兩邊各自維護一份、改一邊忘了改另一邊)。


def label_fn(s):
    if pd.isna(s):
        return None
    for th in _G["label_thresholds"]:
        if s < th["lt"]:
            return th["label"]
    return _G["label_thresholds"][-1]["label"]


SCORE_COLS = ["momentum_score", "copper_gold_score"]


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

    # ---- 2) 銅金比：HG=F（銅期貨）對GC=F（金期貨）40日報酬差 ----
    _cg_w = _FP["copper_gold"]["window"]
    df["HG_ret40"] = (df["HG_futures"] / df["HG_futures"].shift(_cg_w) - 1) * 100
    df["GC_ret40"] = (df["GC_futures"] / df["GC_futures"].shift(_cg_w) - 1) * 100
    df["copper_gold_spread"] = df["HG_ret40"] - df["GC_ret40"]
    # 利差越高＝銅相對金走強＝景氣/風險偏好回升＝貪婪，不用反轉，直接用百分位
    df["copper_gold_score"] = rolling_percentile_score(df["copper_gold_spread"])

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


# ---------------------------------------------------------------- 升等候選因子(Phase 4)
PROMOTED_FACTORS_PATH = "promoted_candidate_factors.json"


def _promoted_factor_raw_series(config, df):
    """依候選因子的轉換模式，回傳(aux_series, chart_series_spec, df)——
    aux_series是{欄位後綴: pd.Series}，chart_series_spec是給前端畫「原始資料走勢圖」用的
    [{key, label, color}]列表。跟factor_screening.py的raw_data_chart_base64()是同一套
    per-mode邏輯，只是這裡回傳原始數列給互動圖表用，不是matplotlib靜態圖。"""
    mode = config["mode"]
    sources = config["sources"]
    params = config.get("params", {})
    window = params.get("window")

    if mode in ("ma_deviation", "moving_average"):
        series, df = _resolve_source(sources["series"], df, fetch_yahoo_close, fetch_fred_series)
        aux = {"raw": series}
        spec = [{"key": "raw", "label": "原始序列", "color": "var(--series-1)"}]
        if window:
            aux["ma"] = series.rolling(window, min_periods=window).mean()
            spec.append({"key": "ma", "label": f"{window}日移動平均", "color": "var(--series-2)"})
    elif mode == "range_position":
        series, df = _resolve_source(sources["series"], df, fetch_yahoo_close, fetch_fred_series)
        aux = {"raw": series}
        spec = [{"key": "raw", "label": "原始序列", "color": "var(--series-1)"}]
        if window:
            aux["hi"] = series.rolling(window, min_periods=window).max()
            aux["lo"] = series.rolling(window, min_periods=window).min()
            spec.append({"key": "hi", "label": f"{window}日滾動高點", "color": "var(--series-2)"})
            spec.append({"key": "lo", "label": f"{window}日滾動低點", "color": "var(--series-4)"})
    elif mode == "return_spread":
        series_a, df = _resolve_source(sources["a"], df, fetch_yahoo_close, fetch_fred_series)
        series_b, df = _resolve_source(sources["b"], df, fetch_yahoo_close, fetch_fred_series)
        base_a = series_a.dropna().iloc[0] if series_a.dropna().size else None
        base_b = series_b.dropna().iloc[0] if series_b.dropna().size else None
        aux = {
            "a": series_a / base_a * 100 if base_a else series_a,
            "b": series_b / base_b * 100 if base_b else series_b,
        }
        spec = [
            {"key": "a", "label": "數列A（指數化，起點=100）", "color": "var(--series-1)"},
            {"key": "b", "label": "數列B（指數化，起點=100）", "color": "var(--series-2)"},
        ]
    elif mode == "value_spread":
        series_a, df = _resolve_source(sources["a"], df, fetch_yahoo_close, fetch_fred_series)
        series_b, df = _resolve_source(sources["b"], df, fetch_yahoo_close, fetch_fred_series)
        aux = {"a": series_a, "b": series_b}
        spec = [
            {"key": "a", "label": "數列A", "color": "var(--series-1)"},
            {"key": "b", "label": "數列B", "color": "var(--series-2)"},
        ]
    elif mode == "rolling_stat":
        series, df = _resolve_source(sources["series"], df, fetch_yahoo_close, fetch_fred_series)
        aux = {"raw": series}
        spec = [{"key": "raw", "label": "原始序列", "color": "var(--series-1)"}]
        if window and params.get("stat", "skew") == "median_dev":
            aux["med"] = series.rolling(window, min_periods=window).median()
            spec.append({"key": "med", "label": f"{window}日滾動中位數", "color": "var(--series-2)"})
    else:
        aux, spec = {}, []
    return aux, spec, df


def compute_promoted_factors(df, out):
    """讀 promoted_candidate_factors.json(因子篩選平台「升等為可選因子」寫入的暫存清單)，
    對每個因子重算完整歷史分數＋原始資料走勢，回傳(out含新欄位, promoted_defs給前端用)。

    務必用還沒裁切過的df(含5年百分位暖身期)算分數，理由跟官方七因子一模一樣：
    百分位是trailing window，裁切過的df會讓早期日期誤判成look-ahead問題。算完才
    reindex進out(裁切過的6年輸出範圍)。單一因子算失敗不該讓整個儀表板產生失敗，
    所以逐一包try/except，失敗只跳過那個因子、印警告。"""
    if not os.path.exists(PROMOTED_FACTORS_PATH):
        return out, []
    with open(PROMOTED_FACTORS_PATH, encoding="utf-8") as f:
        promoted_raw = json.load(f).get("factors", [])

    promoted_defs = []
    for config in promoted_raw:
        pf_key = config.get("key", "?")
        try:
            score, _, df = build_candidate_score(config, df, fetch_yahoo_close, fetch_fred_series)
            aux, chart_spec, df = _promoted_factor_raw_series(config, df)

            score_col = f"promoted_{pf_key}_score"
            out[score_col] = score.reindex(out.index)
            aux_cols = {}
            for aux_key, aux_series in aux.items():
                col = f"promoted_{pf_key}_{aux_key}"
                out[col] = aux_series.reindex(out.index)
                aux_cols[aux_key] = col

            promoted_defs.append({
                "key": pf_key, "label": config.get("label", pf_key),
                "score_col": score_col, "aux_cols": aux_cols, "chart_series": chart_spec,
            })
            print(f"  升等候選因子已納入儀表板：{config.get('label', pf_key)}")
        except Exception as e:
            print(f"  升等候選因子「{config.get('label', pf_key)}」計算失敗，略過此因子：{e}")
    return out, promoted_defs


# ---------------------------------------------------------------- 事件行事曆(Phase 5)
EVENT_CALENDAR_PATH = "event_calendar.json"


def load_event_calendar(out):
    """讀event_calendar.json(FOMC/CPI/NFP等總經事件的靜態清單)，只丟掉早於out資料範圍
    起點的古老事件；未來事件(超過最新一天，例如還沒發生的下一次FOMC)刻意保留——
    右側事件欄要能看到「現在之後」的事件，只是圖表沒有對應的分數可以畫線，
    前端會用idx=null標示、只在圖表端過濾掉，不影響事件欄顯示。
    日期→資料索引的轉換刻意不在這裡做，直接把ISO日期字串傳給前端，用跟dateJump
    現有邏輯一樣的方式(找第一個>=該日期的交易日)在JS端就地解析，避免兩邊各自維護
    一套交易日對齊邏輯。檔案不存在就回傳空清單，不報錯(比照regime_weights_v1.json
    的容錯慣例)。"""
    if not os.path.exists(EVENT_CALENDAR_PATH):
        return []
    with open(EVENT_CALENDAR_PATH, encoding="utf-8") as f:
        raw_events = json.load(f).get("events", [])
    start = out.index.min().strftime("%Y-%m-%d")
    return [e for e in raw_events if e["date"] >= start]


def fetch_all_raw_data():
    """下載並整合所有原始數據（包含 2014 起之暖身期）。"""
    print("下載 ZN=F ...")
    zn = fetch_yahoo_close("ZN=F", "ZN_futures")
    print("下載 HG=F (銅期貨) ...")
    hg = fetch_yahoo_close("HG=F", "HG_futures")
    print("下載 GC=F (金期貨) ...")
    gc = fetch_yahoo_close("GC=F", "GC_futures")
    print("下載 Treasury 10年期殖利率 ...")
    ust10, ust2 = fetch_treasury_yield_curve()

    end_d = date.today().strftime("%Y-%m-%d")
    full_index = pd.date_range(FETCH_START_DATE, end_d, freq="D")
    df = pd.concat([zn, hg, gc, ust10, ust2], axis=1, sort=True).reindex(full_index)
    df.index.name = "Date"
    # INPUT_COLS 裡有幾個舊分數版本用的欄位(NQ_futures/TLT/SHY/MOVE_index)已經不抓了，
    # 這裡先補成全NA，只是為了讓下面的使用者Excel覆蓋迴圈不會因為欄位不存在而 KeyError
    # (data_input.xlsx 目前是空模板，但保留這個防呆避免以後有人真的填了那些舊欄位)。
    for col in INPUT_COLS:
        if col not in df.columns:
            df[col] = pd.NA

    # ---- 使用者 Excel 數據覆蓋/補充 ----
    if os.path.exists(INPUT_XLSX):
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
    return df


def main():
    ensure_input_template()
    df = fetch_all_raw_data()

    # 禁止引用未來資料：資料只保留到今天為止，絕不含未來日期
    assert df.index.max() <= pd.Timestamp(date.today()), "偵測到未來日期的資料列，中止執行"

    raw_df = df  # 保留合併後、算分數前的原始資料，供未來資料檢查重算使用
    df = compute_scores(df)
    score_cols = SCORE_COLS

    print("執行未來資料檢查 ...")
    assert_no_lookahead_bias(raw_df, df)

    out = df.loc[OUTPUT_START_DATE:]
    out = out.copy()

    # 銅金比原始走勢圖用的指數化序列：以圖表可視範圍的第一天為基準=100
    # (銅~$4-5、金~$2000+，原始價格差500倍以上，不指數化的話同一張圖裡銅的線會貼底看不到)
    hg_base = out["HG_futures"].iloc[0]
    gc_base = out["GC_futures"].iloc[0]
    out["HG_indexed"] = out["HG_futures"] / hg_base * 100
    out["GC_indexed"] = out["GC_futures"] / gc_base * 100

    # ---- 【實驗性，已停用】情境加權分數：用凍結的權重快照，不會每天重新校準 ----
    # 2026-08-05：權重快照(regime_weights_v1.json)是照舊版七項分數校準的，現在只剩
    # 動能/銅金比兩項分數，權重對不上，程式碼保留但停用執行，之後要恢復需要重新校準
    # (見 derive_regime_weights.py)。
    out["regime_fed"] = out.index.map(regime_lib.fed_cycle_label)

    REGIME_SCORE_ENABLED = False
    regime_meta = None
    if REGIME_SCORE_ENABLED and os.path.exists("regime_weights_v1.json"):
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
    elif not REGIME_SCORE_ENABLED:
        print("情境加權分數：已停用（權重快照對不上目前的兩項分數，見上方註解）")
    else:
        print("找不到 regime_weights_v1.json，略過情境加權分數（先執行 derive_regime_weights.py 產生權重快照）")

    # ---- 【Phase 4】升等候選因子：因子篩選平台驗證過、使用者選擇升等的候選因子 ----
    print("檢查升等候選因子 ...")
    out, promoted_defs = compute_promoted_factors(df, out)

    # ---- 【Phase 5】事件行事曆：FOMC/CPI/NFP等總經事件標註 ----
    event_calendar = load_event_calendar(out)
    print(f"事件行事曆：{len(event_calendar)} 筆事件落在輸出範圍內")

    # ---- 輸出 CSV / 審閱 Excel ----
    out.sort_index(ascending=False).to_csv("bond_fear_greed_v2.csv")
    with pd.ExcelWriter("bond_dashboard_data_input.xlsx", engine="openpyxl") as writer:
        raw_cols = ["UST_10Yr", "UST10Y_SMA125", "momentum_spread",
                    "HG_futures", "GC_futures", "HG_ret40", "GC_ret40", "copper_gold_spread"]
        out[raw_cols].to_excel(writer, sheet_name="RawData")
        out[score_cols + ["composite_score", "label"]].to_excel(writer, sheet_name="Scores")

    # ---- 產生 JSON 並注入 HTML ----
    def safe(v, nd=3):
        if v is None or pd.isna(v):
            return None
        return round(float(v), nd)

    records = []
    for d, row in out.iterrows():
        rec = {
            "date": d.strftime("%Y-%m-%d"),
            "score": safe(row["composite_score"], 2),
            "label": row["label"] if isinstance(row["label"], str) else None,
            "ust10yr": safe(row["UST_10Yr"], 2),
            "momentum": safe(row["momentum_score"], 2),
            "copper_gold": safe(row["copper_gold_score"], 2),
            "regimeScore": safe(row["regime_score"], 2) if regime_meta else None,
            "regimeFed": row["regime_fed"] if isinstance(row["regime_fed"], str) else None,
            "raw": {
                "us10y": safe(row["UST_10Yr"]),
                "sma125": safe(row["UST10Y_SMA125"]),
                "spread": safe(row["momentum_spread"], 2),
                "hg_idx": safe(row["HG_indexed"], 2),
                "gc_idx": safe(row["GC_indexed"], 2),
                "hg_ret40": safe(row["HG_ret40"], 2),
                "gc_ret40": safe(row["GC_ret40"], 2),
                "cg_spread": safe(row["copper_gold_spread"], 2),
            },
        }
        for pf in promoted_defs:
            rec[pf["key"]] = safe(row[pf["score_col"]], 2)
            for aux_key, col in pf["aux_cols"].items():
                rec["raw"][f"{pf['key']}_{aux_key}"] = safe(row[col])
        records.append(rec)
    data_json = json.dumps(records, ensure_ascii=False)
    # 這裡曾經也把同一份data_json寫進chart/dashboard_v2_data.json,那是舊版
    # (build_dashboard_v2.py/dashboard_v2.html)的殘留輸出,現在沒有任何被連結、
    # 可觸及的頁面會讀它——但這個檔案是git追蹤的,每次CI跑完都留下一筆未加入
    # git add清單的異動,擋住了update-and-deploy.yml裡的`git pull --rebase`步驟
    # (2026-07-28發生過一次:CI連續跑失敗、正式站卡在舊版本沒更新)。
    # 移除這行寫入,連同下面git rm掉這個檔案,徹底解決,不要只在CI腳本裡補git add。

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
            # 2026-07-30起補上這三項——原本只有定義手冊(已移除)才顯示，內容折回
            # 儀表板「計算邏輯與資料來源」說明面板，見dashboard_template.html。
            "formula": _sub_tokens(fx["formula_tpl"], fx["params"]),
            "tuningNote": _sub_tokens(fx.get("tuning_note", ""), fx["params"]),
            "codeLocation": fx["code_location"],
        }
        for fx in DEFS["factors"]
    }
    factor_defs_json = json.dumps(factor_defs_out, ensure_ascii=False)

    # ---- 升等候選因子定義注入(只給前端需要的欄位，score_col/aux_cols是Python內部用的
    # DataFrame欄名，不用給前端) ----
    promoted_factors_json = json.dumps(
        [{"key": pf["key"], "label": pf["label"], "chartSeries": pf["chart_series"]} for pf in promoted_defs],
        ensure_ascii=False,
    )

    # ---- 事件行事曆注入 ----
    event_calendar_json = json.dumps(event_calendar, ensure_ascii=False)

    with open("chart/dashboard_template.html") as f:
        template = f.read()
    for ph in ["__DATA_JSON__", "__REGIME_META_JSON__", "__FACTOR_DEFS_JSON__",
               "__PROMOTED_FACTORS_JSON__", "__EVENT_CALENDAR_JSON__",
               "__NAV_BAR_CSS__", "__NAV_BAR_HTML__",
               "__ROOT_COLORS_CSS__", "__CONTENT_MAX_WIDTH__", "__BASE_LINE_HEIGHT__",
               "__H1_SIZE__", "__LEDE_MAX_WIDTH__"]:
        assert ph in template, f"模板缺少 {ph} 佔位符"
    out_html = (template
                .replace("__DATA_JSON__", data_json)
                .replace("__REGIME_META_JSON__", regime_meta_json)
                .replace("__FACTOR_DEFS_JSON__", factor_defs_json)
                .replace("__PROMOTED_FACTORS_JSON__", promoted_factors_json)
                .replace("__EVENT_CALENDAR_JSON__", event_calendar_json)
                .replace("__NAV_BAR_CSS__", nav_bar.NAV_BAR_CSS)
                .replace("__NAV_BAR_HTML__", nav_bar.render_nav_bar("dashboard"))
                .replace("__ROOT_COLORS_CSS__", page_style.ROOT_COLORS_CSS)
                .replace("__CONTENT_MAX_WIDTH__", page_style.CONTENT_MAX_WIDTH)
                .replace("__BASE_LINE_HEIGHT__", page_style.BASE_LINE_HEIGHT)
                .replace("__H1_SIZE__", page_style.H1_SIZE)
                .replace("__LEDE_MAX_WIDTH__", page_style.LEDE_MAX_WIDTH))
    with open("chart/dashboard.html", "w") as f:
        f.write(out_html)

    latest = records[-1]
    print(f"\n完成！共 {len(records)} 天（{records[0]['date']} ~ {latest['date']}）")
    print(f"最新綜合分數：{latest['score']}（{latest['label']}）  "
          f"動能 {latest['momentum']} / 銅金比 {latest['copper_gold']}")
    print("chart/dashboard.html 已更新")


if __name__ == "__main__":
    main()
