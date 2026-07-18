"""
第二版債券市場恐懼貪婪指數：
  1) 動能 (Momentum)   — ZN期貨對125日均線的乖離率，滾動5年百分位
  2) 強度 (Strength)   — ZN期貨在過去252交易日(52週)高低區間的相對位置 (0-100，本身就是比例)
  3) Put/Call          — 選擇權買賣權比率5日均值 (使用者自行提供歷史資料，暫缺則留空)
  4) MOVE指數          — 美債隱含波動度，反轉後滾動5年百分位

綜合分數 = 當天「有資料」的分量等權重平均（Put/Call尚無資料時，用其餘3項平均）。
同時輸出10年期公債殖利率序列，供時間軸圖表疊加使用。
"""
import io
import os
import time
from datetime import date

import pandas as pd
import requests
import yfinance as yf

FETCH_START_DATE = "2014-06-01"  # 留足夠緩衝算252日/125日滾動窗
OUTPUT_START_DATE = "2020-01-01"
END_DATE = date.today().isoformat()

TREASURY_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve"
    "&field_tdr_date_value={year}&page&_format=csv"
)

PUT_CALL_INPUT_PATH = "put_call_input.csv"  # 使用者自備歷史資料：欄位 Date, put_call_ratio


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


def fetch_treasury_10yr():
    start_year = int(FETCH_START_DATE[:4])
    end_year = date.today().year
    frames = []
    for year in range(start_year, end_year + 1):
        url = TREASURY_URL.format(year=year)
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        frames.append(df)
    combined = pd.concat(frames, ignore_index=True)
    combined["Date"] = pd.to_datetime(combined["Date"], format="%m/%d/%Y")
    combined = combined.set_index("Date").sort_index()
    col10 = [c for c in combined.columns if c.strip() == "10 Yr"][0]
    return combined[col10].rename("UST_10Yr")


def rolling_percentile_score(series, window_days=5 * 365):
    def pct_rank_of_last(window):
        current = window[-1]
        return (window <= current).mean() * 100
    return series.rolling(window=window_days, min_periods=window_days).apply(pct_rank_of_last, raw=True)


def load_put_call_input():
    if not os.path.exists(PUT_CALL_INPUT_PATH):
        print(f"（找不到 {PUT_CALL_INPUT_PATH}，Put/Call 欄位先留空，之後補上歷史資料再重跑即可）")
        return None
    df = pd.read_csv(PUT_CALL_INPUT_PATH, parse_dates=["Date"])
    df = df.set_index("Date").sort_index()
    return df["put_call_ratio"]


def main():
    print("下載 ZN=F ...")
    zn = fetch_yahoo_close("ZN=F", "ZN_futures")
    print("下載 ^MOVE ...")
    move = fetch_yahoo_close("^MOVE", "MOVE_index")
    print("下載 Treasury 10年期殖利率 ...")
    ust10 = fetch_treasury_10yr()

    full_index = pd.date_range(FETCH_START_DATE, END_DATE, freq="D")
    df = pd.concat([zn, move, ust10], axis=1).reindex(full_index)
    df.index.name = "Date"
    df = df.sort_index().ffill()
    df = df.dropna(how="all")
    first_valid = df.apply(lambda c: c.first_valid_index()).min()
    df = df.loc[first_valid:]

    # ---------- 1) 動能 Momentum：ZN對125日均線乖離率 ----------
    df["ZN_SMA125"] = df["ZN_futures"].rolling(125, min_periods=125).mean()
    df["momentum_bias_pct"] = (df["ZN_futures"] - df["ZN_SMA125"]) / df["ZN_SMA125"] * 100
    df["momentum_score"] = rolling_percentile_score(df["momentum_bias_pct"])

    # ---------- 2) 強度 Strength：ZN在252日高低區間的位置 ----------
    roll_max = df["ZN_futures"].rolling(252, min_periods=252).max()
    roll_min = df["ZN_futures"].rolling(252, min_periods=252).min()
    df["zn_252d_high"] = roll_max
    df["zn_252d_low"] = roll_min
    df["strength_score"] = (df["ZN_futures"] - roll_min) / (roll_max - roll_min) * 100

    # ---------- 3) Put/Call：使用者提供歷史資料則計算，否則留空 ----------
    put_call_raw = load_put_call_input()
    if put_call_raw is not None:
        df["put_call_ratio"] = put_call_raw.reindex(df.index).ffill()
        df["put_call_5d_avg"] = df["put_call_ratio"].rolling(5, min_periods=5).mean()
        pc_percentile = rolling_percentile_score(df["put_call_5d_avg"])
        df["putcall_score"] = 100 - pc_percentile  # 反轉：比率越高(越多put)=越恐懼，分數應越低
    else:
        df["put_call_ratio"] = pd.NA
        df["put_call_5d_avg"] = pd.NA
        df["putcall_score"] = pd.NA

    # ---------- 4) MOVE：反轉後滾動5年百分位 ----------
    df["move_score"] = 100 - rolling_percentile_score(df["MOVE_index"])

    # ---------- 綜合分數：當天有資料的分量等權重平均 ----------
    score_cols = ["momentum_score", "strength_score", "putcall_score", "move_score"]
    df["composite_score"] = df[score_cols].mean(axis=1, skipna=True)
    df["composite_score"] = df["composite_score"].where(df[score_cols].notna().any(axis=1))

    def label_fn(s):
        if pd.isna(s):
            return None
        if s < 25:
            return "極度恐懼"
        if s < 45:
            return "恐懼"
        if s < 56:
            return "中性"
        if s < 76:
            return "貪婪"
        return "極度貪婪"

    df["label"] = df["composite_score"].apply(label_fn)

    out = df.loc[OUTPUT_START_DATE:].sort_index(ascending=False)

    csv_path = "bond_fear_greed_v2.csv"
    out.to_csv(csv_path)
    print(f"\n完成，共 {len(out)} 列，已存成 {csv_path}")
    print(out[["composite_score", "label", "momentum_score", "strength_score", "putcall_score", "move_score"]].head(8))

    # ---------- Excel 資料輸入/審閱檔 ----------
    excel_path = "bond_dashboard_data_input.xlsx"
    with pd.ExcelWriter(excel_path, engine="openpyxl") as writer:
        raw_cols = ["ZN_futures", "ZN_SMA125", "momentum_bias_pct", "zn_252d_high", "zn_252d_low",
                    "MOVE_index", "UST_10Yr", "put_call_ratio", "put_call_5d_avg"]
        df.loc[OUTPUT_START_DATE:].sort_index()[raw_cols].to_excel(writer, sheet_name="RawData")
        df.loc[OUTPUT_START_DATE:].sort_index()[score_cols + ["composite_score", "label"]].to_excel(writer, sheet_name="Scores")
    print(f"已輸出 Excel 資料輸入檔：{excel_path}（在 RawData 分頁的 put_call_ratio 欄填入歷史資料後，"
          f"另存成 {PUT_CALL_INPUT_PATH}（欄位需為 Date, put_call_ratio）再重跑本腳本即可自動納入計算）")


if __name__ == "__main__":
    main()
