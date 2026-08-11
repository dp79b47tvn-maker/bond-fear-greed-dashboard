# -*- coding: utf-8 -*-
"""
Part A 統計分布快速產生腳本 (build_direct_parta_html.py)
直接使用 factor_scores_matrix.csv (0次網路請求，1秒內完成所有 11 個因子的 Part A 統計分布繪圖與 HTML 報告組裝)

【這支腳本只做 Part A，不做五關驗證——請務必看懂這段再用】
2026-08-11修正：這支腳本原本把第一到第五關的結果全部寫死成假值
(IC=0.12、單調性=0.85、pattern_tag="單調遞增"、max_corr=0.22 vs strength、
gates_passed="5/5"、final_verdict="採用 (Keep)")，11個因子產出的報告與登記簿條目
因此長得一模一樣，而且是憑空捏造的數字——實測動能因子真正的20日重疊IC是-0.046，
跟寫死的+0.120方向相反。這些假數字曾經上過正式站。

現在改成：五關一律標記為「未執行」(passed=None)，報告上只呈現真實計算出來的
Part A 統計分布，不再產生任何假數值。要拿到真正的五關結果，請用
factor_screening.screen_and_save(config) 完整重跑(會實際抓網路資料)。

另一個同時修掉的問題：原本第178行是 json.dump(registry) 直接「覆寫」整個
factor_screening_registry.json，跑一次就把先前所有因子的歷史測試紀錄清空
(2026-08-04 commit 014f6c0 就這樣弄丟了5個因子共10筆歷史紀錄)。
現在預設**完全不碰登記簿**——這支腳本沒跑五關，寫進去的條目不會有 IC/單調性/
相關係數，反而會稀釋掉真正批次驗證留下的資料。真的要寫請加 --write-registry，
那條路徑也已經改成讀取-合併-寫回，不再覆寫。
"""

import os
import sys
import json
import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import factor_screening as fs
import factor_validation_analysis as fva

GATE_NOT_RUN_MSG = ("此關未執行——本報告由 build_direct_parta_html.py 產生，只計算 Part A 統計分布，"
                    "沒有跑任何關卡驗證。要取得真正的五關結果，請用 "
                    "factor_screening.screen_and_save(config) 完整重跑。")

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
        "label": "【候選】銅金比 40日報酬差 (HG=F vs GC=F)",
        "mode": "return_spread",
        "sources": {"a": {"yahoo": "HG=F", "name": "HG_futures"}, "b": {"yahoo": "GC=F", "name": "GC_futures"}},
        "params": {"window": 40},
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
    print("=== 1. 載入 factor_scores_matrix.csv (免網路請求) ===")
    matrix_file = "factor_scores_matrix.csv"
    if not os.path.exists(matrix_file):
        print(f"錯誤：找不到 {matrix_file}")
        return

    df = pd.read_csv(matrix_file)
    df["Date"] = pd.to_datetime(df["date"])
    df = df.set_index("Date").sort_index()

    # 對應每個因子的 score 欄名
    for cfg in ALL_FACTORS_CONFIGS:
        k = cfg["key"]
        col_name = k.replace("dashboard_", "")
        if col_name in df.columns:
            df[k] = df[col_name]

    print(f"資料涵蓋範圍：{df.index.min().date()} ~ {df.index.max().date()} (共 {len(df)} 天)")

    registry = []
    os.makedirs("chart", exist_ok=True)

    print("\n=== 2. 產出 11 個因子的 Part A 統計分布 HTML 報告 ===")
    for cfg in ALL_FACTORS_CONFIGS:
        k = cfg["key"]
        lbl = cfg["label"]
        print(f"  處理 [{k}]：{lbl}...")

        # 構建輕量驗證結果結構，供 render_screening_report 渲染 HTML 報告。
        # 五關一律 passed=None + 「此關未執行」——這支腳本沒有跑任何關卡驗證，
        # 絕對不要在這裡填任何數值當佔位符(見檔案開頭說明)。
        result = {
            "key": k,
            "label": lbl,
            "config": cfg,
            "test_date": pd.Timestamp.now().strftime("%Y-%m-%d"),
            "final_verdict": "未評定——本次只產出 Part A 統計分布，未執行五關驗證，"
                             "不構成採用/觀望/淘汰的建議。",
            "gates_passed": "未執行",
            # gate2 只留 main_df 給 Part A 分布圖用，不放 ic_by_horizon，
            # render_screening_report 就會走「無法完成此關分析」那條分支。
            "gate2": {"passed": fs.GATE_NOT_RUN, "main_df": df, "reasons": [GATE_NOT_RUN_MSG]},
            **{g: {"passed": fs.GATE_NOT_RUN, "reasons": [GATE_NOT_RUN_MSG]}
               for g in ("gate1", "gate3", "gate4", "gate5")},
        }

        # 渲染含有 Part A 4-panel 圖表的報告 HTML
        html_out = fs.render_screening_report(result)
        report_file = os.path.join("chart", f"screening_{k}.html")
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(html_out)

        # 建立歷史測試紀錄登記簿條目——只寫真的有算的欄位。
        # main_ic / monotonicity / pattern_tag / max_corr / loo_delta 一律不寫，
        # 因為這支腳本沒有跑第二、四關，寫任何數字都是捏造的。
        registry.append({
            "key": k,
            "label": lbl,
            "test_date": pd.Timestamp.now().strftime("%Y-%m-%d"),
            "mode": cfg["mode"],
            "final_verdict": result["final_verdict"],
            "gates_passed": result["gates_passed"],
        })
        print(f"    ✓ 已產出：{report_file}")

    if "--write-registry" not in sys.argv:
        print("\n=== 3. 略過登記簿（預設行為）===")
        print("  這支腳本沒跑五關，寫進去的條目不會有 IC/單調性/相關係數等欄位，")
        print("  會稀釋掉真正批次驗證留下的資料。真的要寫請加 --write-registry。")
        return

    print("\n=== 3. 合併進登記簿 JSON 並重新建構歷史測試紀錄登記簿 (screening_index.html) ===")
    # 讀取-合併-寫回，不覆寫：登記簿是「歷史測試紀錄」，同一個因子重複測試要留成
    # 多筆紀錄，直接覆寫會把別的因子/別次測試的歷史整批清掉(見檔案開頭說明)。
    existing = fs._load_registry()
    merged = existing + registry
    with open("factor_screening_registry.json", "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f"  登記簿：原有 {len(existing)} 筆 + 本次新增 {len(registry)} 筆 = {len(merged)} 筆")

    index_file = os.path.join("chart", "screening_index.html")
    with open(index_file, "w", encoding="utf-8") as f:
        f.write(fs.render_registry_index(merged))
    print(f"✓ 歷史測試紀錄登記簿已成功更新：{index_file}")


if __name__ == "__main__":
    main()
