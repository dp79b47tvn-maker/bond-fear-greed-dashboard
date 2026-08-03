#!/usr/bin/env python3
"""
批次驗證儀表板上的七大因子——把每個因子用因子篩選平台的五關框架重新驗證，
結果全部寫進登記簿。

用法：python3 scripts/batch_screen_dashboard_factors.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pandas as pd
import factor_screening as fs
import update_dashboard as ud
from transform_modes import build_candidate_score, _resolve_source

# ================================================================
# 七個因子的設定檔，完全對應 factor_definitions.json 中的計算邏輯
# ================================================================

DASHBOARD_FACTORS = [
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
        "key": "dashboard_putcall",
        "label": "【儀表板驗證】Put/Call 選擇權比率 — 5日移動平均",
        "mode": "moving_average",
        "sources": {"series": "put_call_ratio"},
        "params": {"window": 5},
        "invert": True,
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
        "params": {},
        "invert": False,
    },
    {
        "key": "dashboard_inflation",
        "label": "【儀表板驗證】通膨意外 — CPI年增率減損益兩平通膨率",
        "mode": "value_spread",
        "sources": {"a": "CPI_YoY", "b": "Breakeven_10Y"},
        "params": {},
        "invert": True,
    },
]


def main():
    results = []
    for i, cfg in enumerate(DASHBOARD_FACTORS, 1):
        print(f"\n{'='*60}")
        print(f"[{i}/7] 開始驗證：{cfg['label']}")
        print(f"{'='*60}")

        # 特殊處理：通膨意外需要先算 CPI_YoY
        if cfg["key"] == "dashboard_inflation":
            import factor_validation_analysis as fva
            _original_fetch = fva.fetch_extended_history

            def _patched_fetch(*args, **kwargs):
                df, ranges = _original_fetch(*args, **kwargs)
                if "CPI_index" in df.columns and "CPI_YoY" not in df.columns:
                    yoy_shift = 365
                    df["CPI_YoY"] = (df["CPI_index"] / df["CPI_index"].shift(yoy_shift) - 1) * 100
                    print("  → 已注入 CPI_YoY 欄位（CPI指數年增率）")
                return df, ranges

            fva.fetch_extended_history = _patched_fetch

        # 特殊處理：Put/Call 沒有資料，預期會失敗
        if cfg["key"] == "dashboard_putcall":
            print("  ⚠️ Put/Call 目前無歷史資料，預期此因子將無法通過驗證...")

        try:
            result = fs.screen_and_save(cfg)
            results.append((cfg["key"], cfg["label"], result.get("final_verdict", "未知")))
            print(f"  ✅ 完成：{result.get('final_verdict', '未知')}")
        except Exception as e:
            results.append((cfg["key"], cfg["label"], f"❌ 失敗：{e}"))
            print(f"  ❌ 驗證失敗：{e}")

        # 還原 monkey-patch
        if cfg["key"] == "dashboard_inflation":
            fva.fetch_extended_history = _original_fetch

    # 印出總結
    print(f"\n{'='*60}")
    print("📊 七大因子驗證總結")
    print(f"{'='*60}")
    for key, label, verdict in results:
        short_label = label.replace("【儀表板驗證】", "")
        print(f"  {short_label}")
        print(f"    → {verdict}")
    print(f"{'='*60}")
    print(f"共 {len(results)} 個因子已驗證完畢，結果已寫入登記簿。")


if __name__ == "__main__":
    main()
