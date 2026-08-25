# -*- coding: utf-8 -*-
"""
factor_validation_analysis.py 的單元測試——IC/分桶分析是因子篩選平台判斷「這個因子有沒有用」
的核心依據，算錯了會讓平台的採用/淘汰建議整個失去意義。
"""
import numpy as np
import pandas as pd
import pytest
from scipy import stats as scipy_stats

import factor_validation_analysis as fva


def _idx(n, start="2020-01-01"):
    return pd.date_range(start, periods=n, freq="D")


def _perfect_monotonic_df(n=200):
    """建構一份『分數跟隔天殖利率變動存在精確函數關係』的資料，用來確認IC計算方向/大小
    沒被寫反。注意：不能只是讓score跟yield都各自隨時間線性成長就以為關係夠強——那樣的話
    yield的『隔N天變動量』其實是常數(斜率不變)，反而跟score完全沒有相關性可言。
    這裡改成直接建構 yield[t+1]-yield[t] == score[t]（用cumsum反推），
    讓 forward_return(horizon=1) 精確等於 score 本身，Spearman rho 必然是 1.0。"""
    idx = _idx(n)
    score = pd.Series(np.arange(n, dtype=float), index=idx)
    increments = np.concatenate([[0.0], score.values[:-1] / 100.0])
    yields = pd.Series(4.0 + np.cumsum(increments), index=idx)
    return pd.DataFrame({"my_score": score, "UST_10Yr": yields})


class TestForwardReturn:
    def test_ust_10yr_uses_bp_difference_not_percent_return(self):
        """驗證標的是UST_10Yr時，單位必須是bp變動(差值×100)，不是報酬率——
        這正是2026-08-03『改用殖利率消除期貨轉倉誤差』那次改動的核心，
        用錯公式會讓所有IC數字失去意義。見 ZN期貨轉倉問題查證.md。"""
        s = pd.Series([4.00, 4.10, 4.20, 4.30], index=_idx(4), name="UST_10Yr")
        out = fva.forward_return(s, horizon=2, target="UST_10Yr")
        # t=0: (4.20-4.00)*100 = 20bp
        assert out.iloc[0] == pytest.approx(20.0)
        # t=1: (4.30-4.10)*100 = 20bp
        assert out.iloc[1] == pytest.approx(20.0)

    def test_non_yield_target_uses_percent_return(self):
        s = pd.Series([100.0, 102.0, 105.0, 110.0], index=_idx(4), name="ZN_futures")
        out = fva.forward_return(s, horizon=2, target="ZN_futures")
        # t=0: (105/100 - 1)*100 = 5%
        assert out.iloc[0] == pytest.approx(5.0)

    def test_last_horizon_rows_are_nan_not_zero(self):
        """視窗尾端沒有『未來』資料可用，必須是NaN、不能悄悄補0——補0會在後續
        dropna()時被誤刪或更糟被誤當成『未來報酬剛好是0』的真實觀測值。"""
        s = pd.Series(np.arange(10, dtype=float), index=_idx(10), name="UST_10Yr")
        out = fva.forward_return(s, horizon=3, target="UST_10Yr")
        assert out.iloc[-3:].isna().all()
        assert out.iloc[:-3].notna().all()


class TestICFunctions:
    def test_overlapping_ic_direction_and_magnitude(self):
        df = _perfect_monotonic_df()
        result = fva.overlapping_ic(df, "my_score", horizon=1, target="UST_10Yr")
        assert result["rho"] == pytest.approx(1.0, abs=1e-6)
        assert result["n"] > 0

    def test_non_overlapping_ic_matches_independent_spearman_calc(self):
        """不重新實作演算法，而是拿scipy直接算一次『每隔N天取樣』的資料，
        兩邊数字必須完全吻合——這樣就算日後有人重構了取樣邏輯，這個測試依然有效。"""
        df = _perfect_monotonic_df(n=300)
        horizon = 20
        result = fva.non_overlapping_ic(df, "my_score", horizon=horizon, target="UST_10Yr")

        sub = df[["my_score"]].copy()
        sub["fwd"] = fva.forward_return(df["UST_10Yr"], horizon, target="UST_10Yr")
        sub = sub.dropna().iloc[::horizon]
        expected_rho, expected_pval = scipy_stats.spearmanr(sub["my_score"], sub["fwd"])

        assert result["rho"] == pytest.approx(expected_rho)
        assert result["pval"] == pytest.approx(expected_pval)
        assert result["n"] == len(sub)

    def test_non_overlapping_actually_skips_rows(self):
        """驗證『非重疊』真的有隔N天才取一筆，不是跟重疊版本一樣逐日取樣——
        這是兩個函式存在的唯一區別，如果被誤改成一樣，篩選平台『重疊vs非重疊並列
        對照』的功能就名不符實了。"""
        df = _perfect_monotonic_df(n=300)
        horizon = 20
        overlap = fva.overlapping_ic(df, "my_score", horizon=horizon, target="UST_10Yr")
        non_overlap = fva.non_overlapping_ic(df, "my_score", horizon=horizon, target="UST_10Yr")
        assert non_overlap["n"] < overlap["n"]
        # 非重疊大約是重疊的 1/horizon
        assert non_overlap["n"] == pytest.approx(overlap["n"] / horizon, rel=0.15)

    def test_too_few_samples_returns_none_not_a_fake_number(self):
        idx = _idx(5)
        df = pd.DataFrame({"my_score": [1, 2, 3, 4, 5], "UST_10Yr": [4.0, 4.1, 4.2, 4.3, 4.4]}, index=idx)
        result = fva.overlapping_ic(df, "my_score", horizon=20, target="UST_10Yr")
        assert result["rho"] is None


class TestBucketAnalysis:
    def test_monotonic_relationship_scores_high_monotonicity(self):
        df = _perfect_monotonic_df(n=500)
        result = fva.bucket_analysis(df, "my_score", horizon=1, buckets=5, target="UST_10Yr")
        assert result is not None
        assert result["monotonicity"] == pytest.approx(1.0, abs=1e-6)
        assert len(result["table"]) == 5

    def test_insufficient_data_returns_none(self):
        idx = _idx(10)
        df = pd.DataFrame({"my_score": range(10), "UST_10Yr": [4.0] * 10}, index=idx)
        result = fva.bucket_analysis(df, "my_score", horizon=5, buckets=5, target="UST_10Yr")
        assert result is None
