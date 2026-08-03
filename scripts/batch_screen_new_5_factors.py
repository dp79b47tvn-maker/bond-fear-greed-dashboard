#!/usr/bin/env python3
"""
批次驗證使用者提出的五個全新候選因子：
1. 銅金比 (HG=F vs GC=F 報酬差)
2. 投資級企業債信用利差 (FRED: BAA10Y)
3. 美債 Swap Spread (FRED: DSWP10 vs DGS10)
4. SOFR 與 3M 美債利差 (FRED: SOFR vs DTB3) —— TED Spread 替代方案
5. 1年期通膨預期 (FRED: EXPINF1YR)

用法：python3 scripts/batch_screen_new_5_factors.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import factor_screening as fs

NEW_5_FACTORS = [
    {
        "key": "cand_copper_gold",
        "label": "【候選】銅金比 40日報酬差 (HG=F vs GC=F)",
        "mode": "return_spread",
        "sources": {
            "a": {"yahoo": "HG=F"},
            "b": {"yahoo": "GC=F"},
        },
        "params": {"window": 40},
        "invert": False,
    },
    {
        "key": "cand_credit_spread",
        "label": "【候選】投資級企業債信用利差 (FRED: BAA10Y)",
        "mode": "ma_spread",
        "sources": {"series": {"fred": "BAA10Y"}},
        "params": {"window": 125},
        "invert": True,
    },
    {
        "key": "cand_swap_spread",
        "label": "【候選】10年期美債 Swap Spread (DSWP10 vs DGS10)",
        "mode": "value_spread",
        "sources": {
            "a": {"fred": "DSWP10"},
            "b": {"fred": "DGS10"},
        },
        "params": {},
        "invert": True,
    },
    {
        "key": "cand_sofr_ted_spread",
        "label": "【候選】SOFR與3M美債利差 (SOFR vs DTB3)",
        "mode": "value_spread",
        "sources": {
            "a": {"fred": "SOFR"},
            "b": {"fred": "DTB3"},
        },
        "params": {},
        "invert": True,
    },
    {
        "key": "cand_inflation_1y",
        "label": "【候選】1年期通膨預期 125日均線價差 (FRED: EXPINF1YR)",
        "mode": "ma_spread",
        "sources": {"series": {"fred": "EXPINF1YR"}},
        "params": {"window": 125},
        "invert": True,
    },
]


def main():
    results = []
    for i, cfg in enumerate(NEW_5_FACTORS, 1):
        print(f"\n{'='*60}")
        print(f"[{i}/5] 開始驗證候選因子：{cfg['label']}")
        print(f"{'='*60}")

        try:
            result = fs.screen_and_save(cfg)
            results.append((cfg["key"], cfg["label"], result.get("final_verdict", "未知")))
            print(f"  ✅ 完成：{result.get('final_verdict', '未知')}")
        except Exception as e:
            results.append((cfg["key"], cfg["label"], f"❌ 失敗：{e}"))
            print(f"  ❌ 驗證失敗：{e}")

    print(f"\n{'='*60}")
    print("📊 五大全新候選因子驗證總結")
    print(f"{'='*60}")
    for key, label, verdict in results:
        short_label = label.replace("【候選】", "")
        print(f"  {short_label}")
        print(f"    → {verdict}")
    print(f"{'='*60}")
    print(f"共 {len(results)} 個候選因子驗證完畢，報告與登記簿已更新。")


if __name__ == "__main__":
    main()
