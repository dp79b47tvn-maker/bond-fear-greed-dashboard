# -*- coding: utf-8 -*-
"""
精確計算 12 大因子在 Mentor 的四大核心評估標準下的數據（為產出詳細 Markdown 分析報告做準備）
評估四大標準：
1. 極端反轉勾回性 (0-24 恐懼端與 76-100 貪婪端之超額 bp 方向)
2. 極端樣本天數 n (恐懼端與貪婪端樣本數是否 >= 30)
3. 20日勝率 % 與平均超額 bp 顯著度
4. 因子獨立性 (對其他因子的最高相關係數是否 < 0.60)
"""

import os
import sys
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

def main():
    matrix_file = "factor_scores_matrix.csv"
    if not os.path.exists(matrix_file):
        print(f"錯誤：找不到 {matrix_file}")
        return

    df = pd.read_csv(matrix_file)
    df["Date"] = pd.to_datetime(df["date"])
    df = df.set_index("Date").sort_index()

    factors_info = [
        {"key": "momentum", "label": "動能 — US 10Y 125日均線價差", "type": "官方"},
        {"key": "strength", "label": "強度 — NQ期貨52週高低區間位置", "type": "官方"},
        {"key": "duration", "label": "存續期間避險 — TLT vs SHY 40日報酬差", "type": "官方"},
        {"key": "move", "label": "波動度 — MOVE指數90日偏態係數", "type": "官方"},
        {"key": "curve", "label": "殖利率曲線形狀 — 10Y減2Y利差", "type": "官方"},
        {"key": "inflation", "label": "通膨意外 — CPI年增率減損益兩平通膨率", "type": "官方"},
        {"key": "putcall", "label": "Put/Call 選擇權比率 — 5日移動平均", "type": "官方(缺失)"},
        {"key": "cand_copper_gold", "label": "銅金比 40日報酬差 (HG=F vs GC=F)", "type": "候選"},
        {"key": "cand_credit_spread", "label": "投資級企業債信用利差 (BAA10Y)", "type": "候選"},
        {"key": "cand_swap_spread", "label": "10年期美債 Swap Spread (DSWP10 vs DGS10)", "type": "候選"},
        {"key": "cand_sofr_ted_spread", "label": "SOFR與3M美債利差 (SOFR vs DTB3)", "type": "候選"},
        {"key": "cand_inflation_1y", "label": "1年期通膨預期 125日均線價差 (EXPINF1YR)", "type": "候選"},
    ]

    # 計算相關係數矩陣
    avail_cols = [f["key"] for f in factors_info if f["key"] in df.columns]
    corr_df = df[avail_cols].corr()

    print("=== 12 因子 Mentor 標準數據檢驗 ===")
    for f in factors_info:
        k = f["key"]
        lbl = f["label"]
        ftype = f["type"]
        
        if k not in df.columns:
            print(f"\n[{ftype}] {lbl} ({k}): ⚠️ 資料缺失（Put/Call 尚待使用者提供數據，無歷史分數）")
            continue

        valid = df[[k, "fwd_20d_excess_bp"]].dropna()
        scores = valid[k]
        excess = valid["fwd_20d_excess_bp"]

        fear_mask = scores < 25
        greed_mask = scores > 75

        fear_n = int(fear_mask.sum())
        greed_n = int(greed_mask.sum())

        fear_excess = excess[fear_mask].mean() if fear_n > 0 else 0.0
        greed_excess = excess[greed_mask].mean() if greed_n > 0 else 0.0

        # 勝率 (恐懼端超額 < 0 %，貪婪端超額 > 0 %)
        fear_win_rate = (np.sum(excess[fear_mask] < 0) / fear_n * 100) if fear_n > 0 else 0.0
        greed_win_rate = (np.sum(excess[greed_mask] > 0) / greed_n * 100) if greed_n > 0 else 0.0

        # 最高相關係數
        other_cols = [c for c in avail_cols if c != k]
        max_corr_val = corr_df.loc[k, other_cols].abs().max() if other_cols else 0.0
        max_corr_key = corr_df.loc[k, other_cols].abs().idxmax() if other_cols else "無"

        # 評估 Mentor 4 大標準
        # 1. 極端反轉勾回性：恐懼端 excess < 0 且 貪婪端 excess > 0
        reversion_ok = (fear_excess < 0) and (greed_excess > 0)
        reversion_partial = (fear_excess < 0) or (greed_excess > 0)
        
        # 2. 樣本數 n
        n_ok = (fear_n >= 30)

        # 3. 獨立性
        corr_ok = (max_corr_val < 0.60)

        print(f"\n[{ftype}] {lbl} ({k})")
        print(f"  - 恐懼端 (0-24)  : 天數 n={fear_n:<4} | 平均超額 = {fear_excess:+.2f} bp | 反轉勝率 = {fear_win_rate:.1f}%")
        print(f"  - 貪婪端 (76-100): 天數 n={greed_n:<4} | 平均超額 = {greed_excess:+.2f} bp | 反轉勝率 = {greed_win_rate:.1f}%")
        print(f"  - 最高相關係數   : {max_corr_key} ({max_corr_val:.2f})")
        print(f"  - 綜合判定       : 極端反轉={reversion_ok} (部分={reversion_partial}), 樣本數n>30={n_ok}, 獨立性={corr_ok}")

if __name__ == "__main__":
    main()
