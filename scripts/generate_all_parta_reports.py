# -*- coding: utf-8 -*-
"""
快速批次產生 11 個有效因子的 Part A 統計分布分析報告與歷史測試紀錄登記簿。
使用 fs.screen_and_save(config) 跑完整 5 關驗證框架，包含新增的 Part A 4-panel 統計分布圖，
並將結果寫入歷史測試紀錄登記簿 (chart/screening_index.html)。
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import factor_screening as fs

ALL_FACTORS_CONFIGS = [
    # 官方 6 因子
    {
        "key": "dashboard_momentum",
        "label": "【儀表板驗證】動能 — US 10Y 125日均線價差",
        "mode": "ma_spread",
        "sources": {"series": "UST_10Yr"},
        "params": {"window": 125},
        "invert": True,
    },
    {
        "key": "dashboard_strength",
        "label": "【儀表板驗證】強度 — NQ期貨52週高低區間位置",
        "mode": "range_position",
        "sources": {"series": "NQ_futures"},
        "params": {"window": 252},
        "invert": False,
    },
    {
        "key": "dashboard_duration",
        "label": "【儀表板驗證】存續期間避險 — TLT vs SHY 40日報酬差",
        "mode": "return_spread",
        "sources": {"a": "TLT", "b": "SHY"},
        "params": {"window": 40},
        "invert": False,
    },
    {
        "key": "dashboard_move",
        "label": "【儀表板驗證】波動度 — MOVE指數90日偏態係數",
        "mode": "rolling_stat",
        "sources": {"series": "MOVE_index"},
        "params": {"window": 90, "stat": "skew"},
        "invert": True,
    },
    {
        "key": "dashboard_curve",
        "label": "【儀表板驗證】殖利率曲線形狀 — 10Y減2Y利差",
        "mode": "value_spread",
        "sources": {"a": "UST_10Yr", "b": "UST_2Yr"},
        "invert": False,
    },
    {
        "key": "dashboard_inflation",
        "label": "【儀表板驗證】通膨意外 — CPI年增率減損益兩平通膨率",
        "mode": "value_spread",
        "sources": {"a": "CPI_index", "b": "Breakeven_10Y"},
        "invert": True,
    },
    # 候選 5 因子
    {
        "key": "cand_copper_gold",
        "label": "【候選】銅金比 60日報酬差 (HG=F vs GC=F)",
        "mode": "return_spread",
        "sources": {"a": {"yahoo": "HG=F", "name": "HG_futures"}, "b": {"yahoo": "GC=F", "name": "GC_futures"}},
        "params": {"window": 60},
        "invert": False
    },
    {
        "key": "cand_credit_spread",
        "label": "【候選】投資級企業債信用利差 (FRED: BAA10Y)",
        "mode": "ma_spread",
        "sources": {"series": {"fred": "BAA10Y", "name": "BAA10Y"}},
        "params": {"window": 125},
        "invert": True
    },
    {
        "key": "cand_swap_spread",
        "label": "【候選】10年期美債 Swap Spread (DSWP10 vs DGS10)",
        "mode": "value_spread",
        "sources": {"a": {"fred": "DSWP10", "name": "DSWP10"}, "b": {"fred": "DGS10", "name": "DGS10"}},
        "invert": True
    },
    {
        "key": "cand_sofr_ted_spread",
        "label": "【候選】SOFR與3M美債利差 (SOFR vs DTB3)",
        "mode": "value_spread",
        "sources": {"a": {"fred": "SOFR", "name": "SOFR"}, "b": {"fred": "DTB3", "name": "DTB3"}},
        "invert": True
    },
    {
        "key": "cand_inflation_1y",
        "label": "【候選】1年期通膨預期 125日均線價差 (FRED: EXPINF1YR)",
        "mode": "ma_spread",
        "sources": {"series": {"fred": "EXPINF1YR", "name": "EXPINF1YR"}},
        "params": {"window": 125},
        "invert": True
    }
]

def main():
    print("=== 開始批次執行 11 個有效因子驗證與 Part A 統計分布分析 ===")
    for i, cfg in enumerate(ALL_FACTORS_CONFIGS, 1):
        print(f"\n[{i}/11] 處理因子 [{cfg['key']}]：{cfg['label']}...")
        try:
            res = fs.screen_and_save(cfg)
            print(f"  ✓ [{cfg['key']}] 判定：{res.get('final_verdict')}")
        except Exception as e:
            print(f"  ❌ [{cfg['key']}] 執行失敗：{e}")

    print("\n✓ 批次分析完成！已刷新歷史測試紀錄登記簿 (chart/screening_index.html)")

if __name__ == "__main__":
    main()
