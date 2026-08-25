# -*- coding: utf-8 -*-
"""
transform_modes.py 的單元測試——這是全平台唯一一份「原始資料 → 0-100分數」的轉換邏輯，
儀表板跟因子篩選平台都靠它，錯了會兩邊一起錯。

每個測試都用手算過的小樣本斷言精確數字，不是只測「跑不跑得動」。
"""
import numpy as np
import pandas as pd
import pytest

from transform_modes import (
    _composite_mean,
    _ma_deviation,
    _ma_spread,
    _moving_average,
    _range_position,
    _resolve_source,
    _return_spread,
    _rolling_stat,
    _value_spread,
    build_candidate_score,
    rolling_percentile_score,
)


def _series(values, start="2020-01-01"):
    idx = pd.date_range(start, periods=len(values), freq="D")
    return pd.Series(values, index=idx, dtype=float)


# ================================================================ rolling_percentile_score
class TestRollingPercentileScore:
    def test_last_value_is_max_in_window_scores_100(self):
        s = _series([10, 20, 30, 40, 50])
        out = rolling_percentile_score(s, window_days=5, min_periods=5)
        # 第5天(index 4)的視窗是[10,20,30,40,50]，最後一天50是視窗裡的最大值
        # → 5/5個數值 <= 50 → 100分
        assert out.iloc[4] == pytest.approx(100.0)

    def test_last_value_is_min_scores_low(self):
        s = _series([10, 20, 30, 40, 50, 5])
        out = rolling_percentile_score(s, window_days=5, min_periods=5)
        # 第6天(index 5)視窗是[20,30,40,50,5]，最後一天5是視窗裡的最小值
        # → 只有1/5個數值(自己) <= 5 → 20分
        assert out.iloc[5] == pytest.approx(20.0)

    def test_before_warmup_period_is_nan(self):
        s = _series([1, 2, 3, 4, 5])
        out = rolling_percentile_score(s, window_days=5, min_periods=5)
        # 暖身期未滿(min_periods=5)之前，分數必須是NaN，不能填假值
        assert out.iloc[:4].isna().all()

    def test_uses_global_default_window_when_not_specified(self):
        # 不帶window_days時要吃factor_definitions.json的global.percentile_window_days，
        # 這是「唯一事實來源」架構是否真的被遵守的關鍵斷言。
        import json
        with open("factor_definitions.json", encoding="utf-8") as f:
            expected_window = json.load(f)["global"]["percentile_window_days"]
        s = _series(np.arange(expected_window + 10))
        out = rolling_percentile_score(s)
        assert out.iloc[: expected_window - 2].isna().all()
        assert not pd.isna(out.iloc[expected_window - 1])

    def test_never_uses_future_data(self):
        """禁止引用未來資料：把序列尾巴換成任意值，不該影響任何『尾巴之前』算出的分數。"""
        base = list(np.random.default_rng(0).normal(size=60))
        s1 = _series(base + [999.0] * 5)  # 尾巴接一段誇張的未來值
        s2 = _series(base + [-999.0] * 5)  # 換成另一種誇張未來值
        out1 = rolling_percentile_score(s1, window_days=20, min_periods=20)
        out2 = rolling_percentile_score(s2, window_days=20, min_periods=20)
        pd.testing.assert_series_equal(out1.iloc[:60], out2.iloc[:60])


# ================================================================ 六種轉換模式
class TestTransformFunctions:
    def test_ma_deviation(self):
        s = _series([10, 10, 10, 40])
        out = _ma_deviation(s, window=3)
        # pandas rolling是「含當天」的視窗：第4天(index3)視窗=[10,10,40]，均線=20，
        # 乖離=(40-20)/20*100=100%
        assert out.iloc[3] == pytest.approx(100.0)

    def test_ma_spread(self):
        s = _series([10, 10, 10, 40])
        out = _ma_spread(s, window=3)
        assert out.iloc[3] == pytest.approx(20.0)

    def test_range_position_at_high_and_low(self):
        s = _series([10, 20, 30, 40, 50])
        out = _range_position(s, window=5)
        # 現值50是視窗[10..50]裡的最高點 → 100
        assert out.iloc[4] == pytest.approx(100.0)
        s2 = _series([50, 40, 30, 20, 10])
        out2 = _range_position(s2, window=5)
        # 現值10是視窗裡的最低點 → 0
        assert out2.iloc[4] == pytest.approx(0.0)

    def test_return_spread(self):
        a = _series([100, 100, 100, 100, 100, 110])  # 5日報酬 = +10%
        b = _series([100, 100, 100, 100, 100, 95])   # 5日報酬 = -5%
        out = _return_spread(a, b, window=5)
        assert out.iloc[5] == pytest.approx(10.0 - (-5.0))

    def test_value_spread(self):
        a = _series([5.0, 5.5, 6.0])
        b = _series([2.0, 2.5, 3.0])
        out = _value_spread(a, b)
        pd.testing.assert_series_equal(out, a - b)

    def test_moving_average(self):
        s = _series([10, 20, 30])
        out = _moving_average(s, window=3)
        assert out.iloc[2] == pytest.approx(20.0)

    def test_rolling_stat_median_dev(self):
        s = _series([10, 10, 10, 10, 15])
        out = _rolling_stat(s, window=4, stat="median_dev")
        # 第5天視窗[10,10,10,10]中位數=10，現值15 → (15-10)/10*100=50%
        assert out.iloc[4] == pytest.approx(50.0)

    def test_rolling_stat_std(self):
        s = _series([1, 2, 3, 4, 5])
        out = _rolling_stat(s, window=5, stat="std")
        assert out.iloc[4] == pytest.approx(s.iloc[:5].std())


# ================================================================ _composite_mean
class TestCompositeMean:
    def test_equal_weight_average(self):
        a = _series([40.0, 50.0, 60.0])
        b = _series([60.0, 50.0, 40.0])
        out = _composite_mean(a, b)
        assert out.iloc[0] == pytest.approx(50.0)
        assert out.iloc[1] == pytest.approx(50.0)

    def test_skips_missing_factor_without_faking_a_value(self):
        """某項當天無資料時自動排除、由其餘項平均——這是儀表板composite_score的核心規則，
        兩邊(update_dashboard.compute_scores 與這裡)必須一致，不能有一邊偷填假值。"""
        a = _series([40.0, np.nan, 60.0])
        b = _series([60.0, 50.0, np.nan])
        out = _composite_mean(a, b)
        assert out.iloc[0] == pytest.approx(50.0)
        assert out.iloc[1] == pytest.approx(50.0)  # 只剩b，不是NaN
        assert out.iloc[2] == pytest.approx(60.0)  # 只剩a

    def test_all_missing_stays_missing(self):
        """兩項都缺值的那天，絕對不能填出一個假分數。"""
        a = _series([np.nan])
        b = _series([np.nan])
        out = _composite_mean(a, b)
        assert out.isna().all()


# ================================================================ _resolve_source
class TestResolveSource:
    def test_existing_column_returned_directly(self):
        df = pd.DataFrame({"foo": [1, 2, 3]})
        series, out_df = _resolve_source("foo", df)
        pd.testing.assert_series_equal(series, df["foo"])
        assert out_df is df

    def test_missing_column_raises_with_actionable_message(self):
        df = pd.DataFrame({"foo": [1, 2, 3]})
        with pytest.raises(ValueError, match="沒有欄位"):
            _resolve_source("bar", df)

    def test_yahoo_spec_calls_injected_fetcher(self):
        """驗證依賴注入設計：這支模組本身不該知道怎麼抓資料，呼叫端傳什麼函式就該用什麼函式。"""
        df = pd.DataFrame(index=pd.date_range("2020-01-01", periods=3))
        calls = []

        def fake_fetch_yahoo(ticker, name):
            calls.append((ticker, name))
            return pd.Series([1.0, 2.0, 3.0], index=df.index, name=name)

        series, out_df = _resolve_source({"yahoo": "HG=F", "name": "HG_futures"}, df, fetch_yahoo=fake_fetch_yahoo)
        assert calls == [("HG=F", "HG_futures")]
        assert "HG_futures" in out_df.columns


# ================================================================ build_candidate_score
class TestBuildCandidateScore:
    def test_invert_flips_score(self):
        # 用 range_position(uses_percentile預設False)而不是moving_average：後者要吃
        # 5年滾動百分位暖身期(1825天)，100列的測試資料永遠是NaN，測不到invert的效果。
        df = pd.DataFrame({"x": np.linspace(1, 100, 100)}, index=pd.date_range("2020-01-01", periods=100))
        cfg_normal = {"mode": "range_position", "sources": {"series": "x"}, "params": {"window": 5}, "invert": False}
        cfg_inverted = {**cfg_normal, "invert": True}
        score_n, _, _ = build_candidate_score(cfg_normal, df.copy())
        score_i, _, _ = build_candidate_score(cfg_inverted, df.copy())
        valid = score_n.notna() & score_i.notna()
        # invert就是100-分數，兩者相加必須處處等於100
        assert ((score_n[valid] + score_i[valid]) - 100).abs().max() < 1e-9

    def test_uses_percentile_false_skips_percentile_transform(self):
        """range_position本身就是0-100，uses_percentile理應預設False——
        如果被誤改成True，分數形狀會被百分位轉換再扭曲一次，這裡鎖住這個行為。"""
        df = pd.DataFrame({"x": [10, 20, 30, 40, 50]}, index=pd.date_range("2020-01-01", periods=5))
        cfg = {"mode": "range_position", "sources": {"series": "x"}, "params": {"window": 5}}
        score, raw_metric, _ = build_candidate_score(cfg, df)
        # 不轉百分位的話，score應該就等於raw_metric本身(clip到0-100)
        pd.testing.assert_series_equal(score, raw_metric.clip(0, 100), check_names=False)

    def test_composite_mean_end_to_end(self):
        """實際場景：把 momentum_score + copper_gold_score 兩個既有分數欄位合成一個新因子，
        對照 update_dashboard.SCORE_COLS 目前的官方組成。"""
        idx = pd.date_range("2020-01-01", periods=3)
        df = pd.DataFrame({
            "momentum_score": [30.0, 40.0, np.nan],
            "copper_gold_score": [70.0, 60.0, 50.0],
        }, index=idx)
        cfg = {
            "mode": "composite_mean",
            "sources": {"cols": ["momentum_score", "copper_gold_score"]},
            "uses_percentile": False,
        }
        score, _, _ = build_candidate_score(cfg, df)
        assert score.iloc[0] == pytest.approx(50.0)
        assert score.iloc[1] == pytest.approx(50.0)
        assert score.iloc[2] == pytest.approx(50.0)  # 只剩copper_gold_score
