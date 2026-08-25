# -*- coding: utf-8 -*-
"""
factor_screening.py 裡 score_to_position() 與 backtest_strategy() 的單元測試——
這是因子篩選平台「回測分析」區塊的全部核心邏輯，錯了會讓 Sharpe/回撤等數字失真，
卻不會有任何程式錯誤跳出來提醒。
"""
import numpy as np
import pandas as pd
import pytest

import factor_screening as fs


class TestScoreToPosition:
    def test_extreme_fear_is_full_long(self):
        assert fs.score_to_position(pd.Series([0.0])).iloc[0] == pytest.approx(1.0)

    def test_extreme_greed_is_full_short(self):
        assert fs.score_to_position(pd.Series([100.0])).iloc[0] == pytest.approx(-1.0)

    def test_dead_zone_forces_flat(self):
        """48-52死區(見factor_definitions.json validation.dead_zone)必須強制空手，
        不管公式算出來的原始部位是多少，都要被蓋成0。"""
        lo, hi = fs.fva._V["dead_zone"]
        for s in (lo, (lo + hi) / 2, hi):
            pos = fs.score_to_position(pd.Series([float(s)]))
            assert pos.iloc[0] == pytest.approx(0.0), f"分數{s}在死區內，部位應強制為0"

    def test_just_outside_dead_zone_is_not_flat(self):
        lo, hi = fs.fva._V["dead_zone"]
        below = fs.score_to_position(pd.Series([lo - 0.1]))
        above = fs.score_to_position(pd.Series([hi + 0.1]))
        assert below.iloc[0] != 0.0
        assert above.iloc[0] != 0.0
        assert below.iloc[0] > 0  # 死區以下(偏恐懼)應該是正部位(做多)
        assert above.iloc[0] < 0  # 死區以上(偏貪婪)應該是負部位(做空)

    def test_output_is_clipped_to_unit_range(self):
        # 即使輸入超出0-100的合理範圍，部位也不該超過±1
        pos = fs.score_to_position(pd.Series([-50.0, 300.0]))
        assert pos.between(-1, 1).all()


class TestBacktestStrategy:
    def _weekday_index(self, n, start="2018-01-02"):
        return pd.bdate_range(start, periods=n)

    def test_matches_independently_computed_pnl_for_full_long(self):
        """建構一個永遠處於極度恐懼(score=0，恆為滿倉做多)的情境，讓策略部位=+1不變，
        獨立(不呼叫任何被測函式)算一次期望損益序列，拿數字互相核對——
        這樣就算日後有人重構了_stats()內部實作，這個測試依然抓得到年化公式/正負號被改錯。"""
        n = 260
        idx = self._weekday_index(n)
        score = pd.Series(0.0, index=idx)
        # 殖利率交替下降0.01/0.02個百分點：要有變化(不能是常數)損益才有變異數可算Sharpe
        decrements = np.tile([0.01, 0.02], n // 2 + 1)[:n]
        yields = pd.Series(4.0 - np.cumsum(decrements), index=idx, name="UST_10Yr")
        main_df = pd.DataFrame({"UST_10Yr": yields})

        bt = fs.backtest_strategy(score, main_df, target="UST_10Yr")
        assert bt is not None

        expected_price_ret = -(yields.shift(-1) - yields) * 100
        expected_pnl = expected_price_ret.dropna()  # pos恆為+1，pnl=price_ret

        full = bt["full"]
        assert full is not None
        assert full["ann_ret_bp"] == pytest.approx(expected_pnl.mean() * 252)
        assert full["ann_vol_bp"] == pytest.approx(expected_pnl.std() * np.sqrt(252))
        assert full["sharpe"] == pytest.approx(
            (expected_pnl.mean() * 252) / (expected_pnl.std() * np.sqrt(252))
        )
        assert full["total_bp"] == pytest.approx(expected_pnl.sum())
        assert full["avg_exposure"] == pytest.approx(1.0)
        assert full["long_pct"] == pytest.approx(100.0)
        assert full["short_pct"] == pytest.approx(0.0)
        assert full["flat_pct"] == pytest.approx(0.0)
        # 殖利率單調下降(債券單調上漲)、部位單調做多 → 每天都賺，勝率必須是100%
        assert full["win_rate"] == pytest.approx(100.0)

    def test_buy_hold_benchmark_ignores_strategy_position(self):
        """對照組『無條件買進持有』必須是price_ret本身的統計量，不能被策略的部位
        (這裡故意設成恆為做空)污染——否則報告裡『策略 vs 買進持有』的比較就沒有意義了。"""
        n = 260
        idx = self._weekday_index(n)
        score = pd.Series(100.0, index=idx)  # 恆為極度貪婪 → 策略恆為做空
        decrements = np.tile([0.01, 0.02], n // 2 + 1)[:n]
        yields = pd.Series(4.0 - np.cumsum(decrements), index=idx, name="UST_10Yr")
        main_df = pd.DataFrame({"UST_10Yr": yields})

        bt = fs.backtest_strategy(score, main_df, target="UST_10Yr")
        assert bt is not None

        expected_price_ret = (-(yields.shift(-1) - yields) * 100).dropna()
        bh = bt["buy_hold"]
        assert bh["ann_ret_bp"] == pytest.approx(expected_price_ret.mean() * 252)
        # 買進持有恆為多方，策略卻恆為做空，兩者報酬方向必須相反
        assert bt["full"]["ann_ret_bp"] == pytest.approx(-bh["ann_ret_bp"])

    def test_insufficient_history_returns_none(self):
        idx = self._weekday_index(50)
        score = pd.Series(0.0, index=idx)
        main_df = pd.DataFrame({"UST_10Yr": pd.Series(np.linspace(4.0, 3.5, 50), index=idx)})
        assert fs.backtest_strategy(score, main_df, target="UST_10Yr") is None

    def test_always_flat_position_gives_no_full_stats(self):
        """全程卡在死區(恆為空手)時，逐日損益是常數0、標準差為0，_stats()依規則回傳None
        （不能硬算出一個Sharpe=0/0的假數字）——這裡把這個邊界行為明確鎖住，避免日後
        有人『順手』把它改成塞0，讓報告誤以為這是一個真的算出來、波動為0的策略。"""
        n = 260
        idx = self._weekday_index(n)
        lo, hi = fs.fva._V["dead_zone"]
        score = pd.Series((lo + hi) / 2, index=idx)
        yields = pd.Series(np.linspace(4.0, 3.5, n), index=idx, name="UST_10Yr")
        main_df = pd.DataFrame({"UST_10Yr": yields})

        bt = fs.backtest_strategy(score, main_df, target="UST_10Yr")
        assert bt is not None
        assert bt["full"] is None
