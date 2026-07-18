"""
抓取 ZN期貨、TLT、SHY、BIL、MOVE指數 的每日歷史價格 (Yahoo Finance)
以及每日美國公債殖利率曲線 (Treasury.gov)，對齊日期、前向補值，輸出乾淨表格。
"""

import io
import time
from datetime import date

import pandas as pd
import requests
import yfinance as yf

FETCH_START_DATE = "2015-01-01"  # 多抓5年，讓2020年起的滾動5年百分位有完整窗口
OUTPUT_START_DATE = "2020-01-01"  # 最終表格只呈現這個日期之後
END_DATE = date.today().isoformat()

YAHOO_TICKERS = {
    "ZN=F": "ZN_futures",   # 10年期美債期貨 (continuous front month)
    "TLT": "TLT",
    "SHY": "SHY",
    "BIL": "BIL",
    "^MOVE": "MOVE_index",
}

TREASURY_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve"
    "&field_tdr_date_value={year}&page&_format=csv"
)


def fetch_yahoo_prices() -> pd.DataFrame:
    """抓取 Yahoo Finance 每檔標的的每日收盤價 (Close)，合併成一張寬表。"""
    frames = []
    for ticker, name in YAHOO_TICKERS.items():
        print(f"下載 {ticker} ...")
        for attempt in range(3):
            try:
                df = yf.download(
                    ticker,
                    start=FETCH_START_DATE,
                    end=END_DATE,
                    progress=False,
                    auto_adjust=False,
                )
                break
            except Exception as e:
                print(f"  重試 {attempt + 1}/3: {e}")
                time.sleep(2)
        else:
            print(f"  無法下載 {ticker}，略過")
            continue

        if df.empty:
            print(f"  {ticker} 沒有資料")
            continue

        # yfinance 有時回傳 MultiIndex 欄位，統一攤平
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close = df[["Close"]].rename(columns={"Close": name})
        close.index.name = "Date"
        frames.append(close)

    merged = pd.concat(frames, axis=1)
    merged.index = pd.to_datetime(merged.index).tz_localize(None)
    return merged


def fetch_treasury_yield_curve() -> pd.DataFrame:
    """抓取 Treasury.gov 每日殖利率曲線資料，逐年下載後合併。"""
    start_year = int(FETCH_START_DATE[:4])
    end_year = date.today().year

    frames = []
    for year in range(start_year, end_year + 1):
        url = TREASURY_URL.format(year=year)
        print(f"下載 Treasury 殖利率曲線 {year} ...")
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        df = pd.read_csv(io.StringIO(resp.text))
        frames.append(df)

    combined = pd.concat(frames, ignore_index=True)
    combined["Date"] = pd.to_datetime(combined["Date"], format="%m/%d/%Y")
    combined = combined.set_index("Date").sort_index()

    # 欄名加上前綴避免跟其他資料混淆，例如 "1 Mo" -> "UST_1Mo"
    combined.columns = [
        "UST_" + c.strip().replace(" ", "").replace("Yr", "Yr").replace("Mo", "Mo")
        for c in combined.columns
    ]
    return combined


def build_clean_table() -> pd.DataFrame:
    prices = fetch_yahoo_prices()
    yields = fetch_treasury_yield_curve()

    # 以完整日曆日期範圍為主軸，之後統一前向補值
    full_index = pd.date_range(FETCH_START_DATE, END_DATE, freq="D")

    combined = pd.concat([prices, yields], axis=1)
    combined = combined.reindex(full_index)
    combined.index.name = "Date"

    # 只保留兩邊資料涵蓋範圍內、且該天至少有一筆資料曾出現過的日期（去掉全空的週末/假日前段）
    combined = combined.sort_index()
    combined = combined.ffill()

    # 開頭若還是有 NaN（因為在任何資料開始之前），直接砍掉這些列
    combined = combined.dropna(how="all")
    first_valid = combined.apply(lambda col: col.first_valid_index()).min()
    combined = combined.loc[first_valid:]

    return combined


ROLLING_WINDOW_DAYS = 5 * 365  # 滾動5年窗口（以完整日曆天數計算，已無週末缺口）


def compute_rolling_percentile(combined: pd.DataFrame) -> pd.DataFrame:
    """對每個欄位，計算「當天數值」在「過去5年」窗口中的百分位排名 (0-100)。"""

    def pct_rank_of_last(window):
        current = window[-1]
        return (window <= current).mean() * 100

    scores = combined.rolling(
        window=ROLLING_WINDOW_DAYS, min_periods=ROLLING_WINDOW_DAYS
    ).apply(pct_rank_of_last, raw=True)

    return scores


COMPOSITE_COMPONENTS = ["ZN_futures", "TLT", "SHY", "BIL", "MOVE_index", "UST_10Yr"]

FEAR_GREED_LABELS = [
    (0, 25, "極度恐懼"),
    (25, 45, "恐懼"),
    (45, 56, "中性"),
    (56, 76, "貪婪"),
    (76, 101, "極度貪婪"),
]


def label_fear_greed(score: float) -> str:
    if pd.isna(score):
        return None
    for lo, hi, label in FEAR_GREED_LABELS:
        if lo <= score < hi:
            return label
    return None


def compute_composite_index(score_table: pd.DataFrame) -> pd.DataFrame:
    """把6個分數等權重平均成一個綜合指數，並套用CNN式5級標籤。
    MOVE_index 是波動度指標（分數越高=越恐慌），方向與其他指標相反，
    加總前先反轉 (100 - 原始分數) 讓「分數越高=越貪婪」的方向一致。
    """
    components = score_table[COMPOSITE_COMPONENTS].copy()
    components["MOVE_index"] = 100 - components["MOVE_index"]

    composite = components.mean(axis=1, skipna=False)
    labels = composite.apply(label_fear_greed)

    result = components.add_suffix("_component")
    result["composite_score"] = composite
    result["label"] = labels
    return result


def main():
    full_table = build_clean_table()

    scores = compute_rolling_percentile(full_table)
    composite = compute_composite_index(scores)

    # 最終只呈現 2020 年起的資料（前面的2015~2019只是拿來墊滾動窗口用）
    # 依日期由新到舊排序：現在 -> 2020
    price_table = full_table.loc[OUTPUT_START_DATE:].sort_index(ascending=False)
    score_table = scores.loc[OUTPUT_START_DATE:].sort_index(ascending=False)
    composite_table = composite.loc[OUTPUT_START_DATE:].sort_index(ascending=False)

    price_out = "bond_yield_data.csv"
    score_out = "bond_yield_percentile_scores.csv"
    composite_out = "bond_fear_greed_index.csv"
    price_table.to_csv(price_out)
    score_table.to_csv(score_out)
    composite_table.to_csv(composite_out)

    print(f"\n完成！")
    print(f"原始數據：共 {len(price_table)} 列，已存成 {price_out}")
    print(f"滾動5年百分位分數：共 {len(score_table)} 列，已存成 {score_out}")
    print(f"綜合恐懼貪婪指數：共 {len(composite_table)} 列，已存成 {composite_out}")
    print("\n綜合指數最新幾列：")
    print(composite_table[["composite_score", "label"]].head(10))
    print("\n各標籤天數分佈：")
    print(composite_table["label"].value_counts())


if __name__ == "__main__":
    main()
