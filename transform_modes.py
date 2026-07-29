# -*- coding: utf-8 -*-
"""
六種因子轉換模式 + 資料來源解析 + 候選分數計算——原本各自定義在 update_dashboard.py
(rolling_percentile_score) 跟 factor_screening.py(其餘)裡。

抽成獨立模組的原因：update_dashboard.py要能對「升等候選因子」(promoted_candidate_factors.json)
重算每日分數，才能把它們的走勢注入儀表板；但這個運算邏輯原本定義在factor_screening.py，
而factor_screening.py本身又import update_dashboard(拿_G、DEFS等設定)——兩邊互相import
會循環依賴。這支模組不import update_dashboard、也不import factor_screening，是最底層的
共用邏輯，兩邊都能安全地各自import它。

抓新資料(yahoo/fred)的能力用依賴注入(fetch_yahoo/fetch_fred參數)而不是直接import
update_dashboard.fetch_yahoo_close/fetch_fred_series，同樣是為了避免循環依賴——
呼叫端(factor_screening.py或update_dashboard.py)各自把自己既有的抓取函式傳進來即可。
"""
import json

import pandas as pd

with open("factor_definitions.json", encoding="utf-8") as _f:
    _DEFS = json.load(_f)
_PERCENTILE_WINDOW_DAYS = _DEFS["global"]["percentile_window_days"]


def rolling_percentile_score(series, window_days=None, min_periods=None):
    if window_days is None:
        window_days = _PERCENTILE_WINDOW_DAYS
    if min_periods is None:
        min_periods = window_days

    def pct_rank_of_last(window):
        return (window <= window[-1]).mean() * 100

    return series.rolling(window=window_days, min_periods=min_periods).apply(pct_rank_of_last, raw=True)


# ================================================================ 六種轉換模式（原始指標，尚未轉百分位）
def _ma_deviation(series, window):
    """均線乖離百分比：(現值 − N日均線) / N日均線 × 100"""
    ma = series.rolling(window, min_periods=window).mean()
    return (series - ma) / ma * 100


def _ma_spread(series, window):
    """均線價差：現值 − N日均線"""
    ma = series.rolling(window, min_periods=window).mean()
    return series - ma


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
    "ma_spread": {"fn": _ma_spread, "n_sources": 1, "uses_percentile_default": True,
                   "label": "均線價差百分位"},
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
def _resolve_source(spec, df, fetch_yahoo=None, fetch_fred=None):
    """spec可以是: 字串(df裡已經有的欄位名稱)、{"yahoo": ticker}、{"fred": series_id}。
    回傳 (series, updated_df)——如果是新抓的資料，順便併回df讓後續步驟(例如look-ahead檢查)可以用。
    fetch_yahoo/fetch_fred由呼叫端注入(update_dashboard.fetch_yahoo_close等)，
    這支模組本身不知道、也不需要知道抓取細節。"""
    if isinstance(spec, str):
        if spec not in df.columns:
            raise ValueError(f"df裡沒有欄位 '{spec}'，如果是新資料來源請用 {{'yahoo': ticker}} 或 {{'fred': series_id}} 指定")
        return df[spec], df
    if isinstance(spec, dict):
        if "yahoo" in spec:
            name = spec.get("name", spec["yahoo"])
            if name in df.columns:
                return df[name], df
            if fetch_yahoo is None:
                raise ValueError(f"資料來源 '{name}' 不在df裡，且沒有提供fetch_yahoo抓取函式")
            s = fetch_yahoo(spec["yahoo"], name)
            df = df.copy()
            df[name] = s.reindex(df.index).ffill()
            return df[name], df
        if "fred" in spec:
            name = spec.get("name", spec["fred"])
            if name in df.columns:
                return df[name], df
            if fetch_fred is None:
                raise ValueError(f"資料來源 '{name}' 不在df裡，且沒有提供fetch_fred抓取函式")
            s = fetch_fred(spec["fred"], name)
            df = df.copy()
            df[name] = s.reindex(df.index).ffill()
            return df[name], df
    raise ValueError(f"看不懂的資料來源設定：{spec}")


def build_candidate_score(config, df, fetch_yahoo=None, fetch_fred=None):
    """照 config 指定的轉換模式，把原始資料變成0–100分數，回傳 (score_series, raw_metric_series, df)。"""
    mode = TRANSFORM_MODES[config["mode"]]
    params = config.get("params", {})
    sources = config["sources"]

    if mode["n_sources"] == 1:
        series, df = _resolve_source(sources["series"], df, fetch_yahoo, fetch_fred)
        if config["mode"] == "rolling_stat":
            raw_metric = mode["fn"](series, params["window"], params.get("stat", "skew"))
        elif config["mode"] == "value_spread":
            raw_metric = mode["fn"](series)  # 理論上不會走到這，value_spread是2-source模式
        else:
            raw_metric = mode["fn"](series, params.get("window"))
    else:
        series_a, df = _resolve_source(sources["a"], df, fetch_yahoo, fetch_fred)
        series_b, df = _resolve_source(sources["b"], df, fetch_yahoo, fetch_fred)
        if config["mode"] == "return_spread":
            raw_metric = mode["fn"](series_a, series_b, params["window"])
        else:
            raw_metric = mode["fn"](series_a, series_b)

    uses_percentile = config.get("uses_percentile", mode["uses_percentile_default"])
    if uses_percentile:
        score = rolling_percentile_score(raw_metric)
    else:
        score = raw_metric.clip(0, 100)

    if config.get("invert", False):
        score = 100 - score

    return score, raw_metric, df
