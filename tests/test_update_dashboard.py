# -*- coding: utf-8 -*-
"""
update_dashboard.compute_scores() 的單元測試——這是整個儀表板唯一算分數的地方，
main() 跟 assert_no_lookahead_bias() 都呼叫同一份函式。

用合成資料而非真實抓取，測試不碰網路、可重複執行、幾秒內跑完。
"""
import numpy as np
import pandas as pd
import pytest

import update_dashboard as ud


def _make_raw_df(n=2200, seed=0):
    """造一份 compute_scores() 需要的最小欄位集合。n 預設2200天，
    要蓋過5年百分位暖身期(1825天)+動能均線暖身期(125天)，讓分數在尾端真的有值可測，
    不然全部都會卡在NaN、什麼都測不出來。"""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2018-01-01", periods=n, freq="D")
    # 用隨機漫步模擬價格/殖利率序列，比常數序列更接近真實資料的統計性質
    ust10 = pd.Series(4.0 + np.cumsum(rng.normal(0, 0.01, n)), index=idx)
    hg = pd.Series(4.0 + np.cumsum(rng.normal(0, 0.02, n)), index=idx).clip(lower=0.5)
    gc = pd.Series(1800 + np.cumsum(rng.normal(0, 5, n)), index=idx).clip(lower=500)
    return pd.DataFrame({"UST_10Yr": ust10, "HG_futures": hg, "GC_futures": gc})


class TestLabelFn:
    @pytest.mark.parametrize("score,expected", [
        (0, "極度恐懼"), (24.9, "極度恐懼"),
        (25, "恐懼"), (44.9, "恐懼"),
        (45, "中性"), (55.9, "中性"),
        (56, "貪婪"), (75.9, "貪婪"),
        (76, "極度貪婪"), (100, "極度貪婪"),
    ])
    def test_thresholds_match_factor_definitions(self, score, expected):
        assert ud.label_fn(score) == expected

    def test_nan_score_gives_no_label(self):
        assert ud.label_fn(float("nan")) is None


class TestComputeScores:
    def test_scores_within_0_to_100(self):
        df = ud.compute_scores(_make_raw_df())
        for col in ud.SCORE_COLS:
            valid = df[col].dropna()
            assert len(valid) > 0, f"{col} 完全沒有算出任何有效分數，暖身期設定可能有誤"
            assert valid.between(0, 100).all(), f"{col} 出現超出0-100範圍的分數"

    def test_composite_score_is_mean_of_score_cols(self):
        df = ud.compute_scores(_make_raw_df())
        last = df.dropna(subset=ud.SCORE_COLS).iloc[-1]
        expected = last[ud.SCORE_COLS].mean()
        assert last["composite_score"] == pytest.approx(expected)

    def test_missing_one_factor_excludes_it_without_faking_a_value(self):
        """核心規則：某項因子當天缺值，自動排除、由其餘項平均，不能拿假數字去湊。"""
        raw = _make_raw_df()
        # 讓最後一天的銅期貨缺值，逼copper_gold_score當天變NaN
        raw.iloc[-1, raw.columns.get_loc("HG_futures")] = np.nan
        df = ud.compute_scores(raw)
        last = df.iloc[-1]
        assert pd.isna(last["copper_gold_score"])
        assert not pd.isna(last["momentum_score"])
        # composite只剩momentum一項，必須直接等於momentum_score，不是兩項平均出來的怪數字
        assert last["composite_score"] == pytest.approx(last["momentum_score"])

    def test_all_factors_missing_composite_is_nan_not_zero(self):
        raw = _make_raw_df()
        raw.iloc[-1, raw.columns.get_loc("HG_futures")] = np.nan
        raw.iloc[-1, raw.columns.get_loc("UST_10Yr")] = np.nan
        df = ud.compute_scores(raw)
        assert pd.isna(df.iloc[-1]["composite_score"])

    def test_composite_score_matches_dynamic_factor_count(self):
        """SCORE_COLS 必須跟 factor_definitions.json 的因子清單一致——這正是
        check_consistency.py 在CI裡靜態掃描檢查的同一件事，這裡用執行期斷言再鎖一次。"""
        assert set(ud.SCORE_COLS) == {f["score_col"] for f in ud.DEFS["factors"]}

    def test_never_uses_future_data(self):
        """禁止引用未來資料：只給『前半段』資料算出來的分數，跟用『全部資料』算出來、
        再切到同一段的分數，逐日必須完全一致——換句話說，把資料尾巴換掉，不該改變
        任何更早日期的分數。這是 assert_no_lookahead_bias() 在正式流程裡做的同一件事，
        這裡把它變成一個不需要真實資料就能跑的單元測試。"""
        raw = _make_raw_df(n=2200)
        cutoff = 2000

        full = ud.compute_scores(raw)
        truncated = ud.compute_scores(raw.iloc[:cutoff])

        for col in ud.SCORE_COLS + ["composite_score"]:
            pd.testing.assert_series_equal(
                full[col].iloc[:cutoff], truncated[col], check_names=False,
            )

    def test_score_cols_are_numeric(self):
        """SCORE_COLS 在 compute_scores() 裡有一段強制 to_numeric——防的是使用者
        Excel輸入把數字存成文字格式，這裡驗證這段防呆真的有作用。"""
        df = ud.compute_scores(_make_raw_df())
        for col in ud.SCORE_COLS:
            assert pd.api.types.is_numeric_dtype(df[col])
