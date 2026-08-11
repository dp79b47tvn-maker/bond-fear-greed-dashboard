# -*- coding: utf-8 -*-
"""
建立 11 個有效因子的每日分數矩陣中繼檔 (factor_scores_matrix.csv)
包含：
1. 官方 6 個有效因子 (momentum, strength, duration, move, curve, inflation) [已暫時排除 putcall]
2. 候選 5 個因子 (cand_copper_gold, cand_credit_spread, cand_swap_spread, cand_sofr_ted_spread, cand_inflation_1y)
3. 標的 10年期美債殖利率 (UST_10Yr) 與 未來 5/20/60 日變動 (bp) 及基準超額報酬

注意：從 2014-06-01 開始抓取資料，確保 5 年滾動百分位有足夠暖身期，輸出自 2020-01-01 起算。
"""

import os
import sys
import pandas as pd
import numpy as np

# 新增根目錄到 import 路徑
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import update_dashboard as ud
import transform_modes as tm

# 候選 5 因子設定
CANDIDATE_CONFIGS = [
    {
        "key": "cand_copper_gold",
        "label": "銅金比 60日報酬差 (HG=F vs GC=F)",
        "mode": "return_spread",
        "sources": {"a": {"yahoo": "HG=F", "name": "HG_futures"}, "b": {"yahoo": "GC=F", "name": "GC_futures"}},
        "params": {"window": 60},
        "invert": False
    },
    {
        "key": "cand_credit_spread",
        "label": "投資級企業債信用利差 (BAA10Y)",
        "mode": "ma_spread",
        "sources": {"series": {"fred": "BAA10Y", "name": "BAA10Y"}},
        "params": {"window": 125},
        "invert": True
    },
    {
        "key": "cand_swap_spread",
        "label": "10年期美債 Swap Spread (DSWP10 vs DGS10)",
        "mode": "value_spread",
        "sources": {"a": {"fred": "DSWP10", "name": "DSWP10"}, "b": {"fred": "DGS10", "name": "DGS10"}},
        "invert": True
    },
    {
        "key": "cand_sofr_ted_spread",
        "label": "SOFR與3M美債利差 (SOFR vs DTB3)",
        "mode": "value_spread",
        "sources": {"a": {"fred": "SOFR", "name": "SOFR"}, "b": {"fred": "DTB3", "name": "DTB3"}},
        "invert": True
    },
    {
        "key": "cand_inflation_1y",
        "label": "1年期通膨預期 125日均線價差 (EXPINF1YR)",
        "mode": "ma_spread",
        "sources": {"series": {"fred": "EXPINF1YR", "name": "EXPINF1YR"}},
        "params": {"window": 125},
        "invert": True
    }
]

def main():
    print("=== 步驟 1/3：抓取與合併 2014 起之完整原始資料 ===")
    # 讀取 update_dashboard 既有資料邏輯
    raw_df = ud.fetch_all_raw_data()
    print(f"原始資料範圍：{raw_df.index.min().date()} ~ {raw_df.index.max().date()} (共 {len(raw_df)} 天)")

    print("\n=== 步驟 2/3：計算官方 6 因子與候選 5 因子分數 ===")
    # 計算官方因子分數
    scored_df = ud.compute_scores(raw_df)
    
    # 計算候選 5 因子分數
    candidate_scores = {}
    curr_df = scored_df.copy()
    for config in CANDIDATE_CONFIGS:
        key = config["key"]
        print(f"  計算候選因子 [{key}]：{config['label']}...")
        score, raw_m, curr_df = tm.build_candidate_score(
            config, curr_df, fetch_yahoo=ud.fetch_yahoo_close, fetch_fred=ud.fetch_fred_series
        )
        candidate_scores[key] = score

    # 組合欄位
    matrix_df = pd.DataFrame(index=curr_df.index)
    matrix_df["date"] = matrix_df.index.strftime("%Y-%m-%d")
    
    # 1. 標的殖利率與未來變動 (bp)
    matrix_df["UST_10Yr"] = curr_df["UST_10Yr"]
    matrix_df["fwd_5d_bp"] = (curr_df["UST_10Yr"].shift(-5) - curr_df["UST_10Yr"]) * 100
    matrix_df["fwd_20d_bp"] = (curr_df["UST_10Yr"].shift(-20) - curr_df["UST_10Yr"]) * 100
    matrix_df["fwd_60d_bp"] = (curr_df["UST_10Yr"].shift(-60) - curr_df["UST_10Yr"]) * 100

    # 2. 官方 6 因子分數 (已排除 putcall)
    official_keys = ["momentum", "strength", "duration", "move", "curve", "inflation"]
    for k in official_keys:
        matrix_df[k] = curr_df[f"{k}_score"]

    # 3. 候選 5 因子分數
    for k in candidate_scores:
        matrix_df[k] = candidate_scores[k]

    # 計算整體基準 (Baseline mean) 與 超額報酬 (Excess return)
    # 過濾出 2020-01-01 起算之正式樣本
    matrix_out = matrix_df[matrix_df.index >= pd.Timestamp(ud.OUTPUT_START_DATE)].copy()

    # 計算超額 (Excess bp = 實際 bp - 基準平均 bp)
    matrix_out["fwd_5d_excess_bp"] = matrix_out["fwd_5d_bp"] - matrix_out["fwd_5d_bp"].mean()
    matrix_out["fwd_20d_excess_bp"] = matrix_out["fwd_20d_bp"] - matrix_out["fwd_20d_bp"].mean()
    matrix_out["fwd_60d_excess_bp"] = matrix_out["fwd_60d_bp"] - matrix_out["fwd_60d_bp"].mean()

    # 重排欄位
    cols_order = [
        "date", "UST_10Yr",
        "fwd_5d_bp", "fwd_20d_bp", "fwd_60d_bp",
        "fwd_5d_excess_bp", "fwd_20d_excess_bp", "fwd_60d_excess_bp",
        "momentum", "strength", "duration", "move", "curve", "inflation",
        "cand_copper_gold", "cand_credit_spread", "cand_swap_spread", "cand_sofr_ted_spread", "cand_inflation_1y"
    ]
    matrix_out = matrix_out[cols_order]

    print("\n=== 步驟 3/3：檢查與輸出因子分數矩陣 ===")
    print(f"輸出資料區間：{matrix_out['date'].min()} ~ {matrix_out['date'].max()} (共 {len(matrix_out)} 個交易日)")
    print("\n11 因子資料完整度（非空筆數）：")
    for k in official_keys + list(candidate_scores.keys()):
        valid_cnt = matrix_out[k].notna().sum()
        pct = (valid_cnt / len(matrix_out)) * 100
        print(f"  - {k:<20}: {valid_cnt}/{len(matrix_out)} ({pct:.1f}%)")

    out_csv = "factor_scores_matrix.csv"
    matrix_out.to_csv(out_csv, index=False, encoding="utf-8")
    print(f"\n✓ 成功建立 11 因子分數矩陣中繼檔：{out_csv} (檔案大小: {os.path.getsize(out_csv)/1024:.1f} KB)")

if __name__ == "__main__":
    main()
