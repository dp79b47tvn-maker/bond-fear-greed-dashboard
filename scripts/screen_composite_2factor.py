#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把目前儀表板的官方綜合分數（動能 + 銅金比 等權重平均）本身，
當成一個因子丟進因子篩選平台跑完整五關，結果寫進歷史測試紀錄登記簿。

為什麼要測「合成分數本身」而不是只測組成因子：
mentor 想看的是「極度恐懼有沒有正報酬、極度貪婪有沒有負報酬」這種兩端反轉訊號，
但兩個因子各自的分桶結果不會自動等於合成後的分桶結果——平均會把分數往中間壓，
極端尾端的樣本數可能整個消失。要回答 mentor 的問題，只能直接測合成分數本身。

用法：python3 scripts/screen_composite_2factor.py
（會實際抓 Yahoo/Treasury 網路資料，約 10–30 秒）
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import factor_screening as fs
import factor_validation_analysis as fva

CONFIG = {
    "key": "composite_momentum_coppergold",
    "label": "【合成】官方綜合分數 — 動能 + 銅金比 等權重平均",
    "mode": "composite_mean",
    # 欄名對應 factor_definitions.json 的 score_col
    "sources": {"cols": ["momentum_score", "copper_gold_score"]},
    # 輸入已經是0–100分數，不能再轉一次百分位
    "uses_percentile": False,
    "invert": False,
}


def main():
    print(f"官方因子（gate4 相關係數比較基準）：{fva.FACTOR_COLS}")
    fs.screen_and_save(CONFIG)
    print("\n完成。報告：chart/screening_composite_momentum_coppergold.html")


if __name__ == "__main__":
    main()
