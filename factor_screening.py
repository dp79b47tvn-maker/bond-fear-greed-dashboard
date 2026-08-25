"""
因子篩選框架 —— 第四個獨立功能，跟儀表板/驗證報告/定義手冊並列。

目的：之後想到新的候選因子，填一張設定表餵進來，自動跑五道關卡判定該不該
加入正式的七因子綜合分數，不用每次重新手動分析一遍。

用法：
    from factor_screening import run_screening
    result = run_screening(CANDIDATE_CONFIG)   # 見下方 CANDIDATE_CONFIG 範例

    或命令列：
    python3 factor_screening.py my_candidate.json

輸出：
    chart/screening_<key>.html          單一因子的完整體檢報告
    chart/screening_index.html          所有測試過的因子登記簿（一覽表）
    factor_screening_registry.json      登記簿的資料來源（append-only）

五道關卡（不論成功失敗都會全部跑完，只提供建議、不硬性擋關，最終是否採用
交由使用者自行判斷）：
    1. 資料健檢：歷史長度、look-ahead檢查、缺值比例、分數分佈鑑別力
    2. 單獨效力：IC(5/10/20/60/120/250日，重疊+非重疊並列)、10年/20年分桶、
       雙版本熱力圖(原始報酬 vs 超額報酬)、動能延續/長期反轉描述性標記
    3. 穩定性：前後半段IC是否同號；跨Fed循環同號檢查(僅供參考)
    4. 增量價值：跟現有七因子的相關係數上限0.6；加入後對綜合分數的LOO ΔIC方向
       是否為「拿掉候選因子IC會變差」
    5. 可實作性：換手率(成本門檻尚待使用者提供bps假設，目前只回報數字)

方法論說明（跟現有驗證報告一致，不重複發明另一套規則）：
    - 所有IC一律重疊+非重疊並列，判斷/門檻以重疊取樣為主，非重疊版本純供對照。
    - 統計驗證標的維持ZN期貨，跟現有正式報告一致；UST_10Yr殖利率只在報告圖1
      當視覺參考疊圖，不參與任何IC/統計計算。
    - 每次測試都寫進 factor_screening_registry.json，防止「試了很多次、
      只記得成功那幾次」的自欺——這份登記簿本身就是防禦多重比較偏誤的機制。

【架構檢討第3項(2026-08-25)：這支檔案原本2390行，計算/渲染/圖表全部混在一起】
現在拆成三支模組，這支檔案本身變成薄的orchestrator：
    screening_gates.py    五道關卡、回測、部位規則——純計算，可獨立測試
    screening_charts.py   matplotlib畫圖轉base64
    screening_render.py   組HTML字串模板(單一因子報告 + 登記簿一覽頁)
這支檔案只留：把三支模組串起來的 run_screening()、登記簿讀寫、
screen_and_save()/rebuild_index() 兩個對外入口。從那三支模組 import 進來的名字
會留在這裡的命名空間裡，所以 `import factor_screening as fs` 之後
fs.score_to_position()、fs.backtest_strategy()、fs.render_screening_report()、
fs.GATE_NOT_RUN 這些既有呼叫方式完全不用改，外部呼叫者(scripts/*.py、
tests/test_factor_screening.py)一行都不用動。
拆分前後用同一份 result/registry 資料重新產生報告，逐位元組diff確認完全一致，
沒有任何行為變化。
"""
import json
import os
from datetime import date

import pandas as pd

import factor_validation_analysis as fva
import update_dashboard as ud
from transform_modes import TRANSFORM_MODES, build_candidate_score

from screening_gates import (
    HORIZONS,
    MAIN_HORIZON,
    THRESHOLDS,
    backtest_strategy,
    gate1_data_health,
    gate2_efficacy,
    gate3_stability,
    gate4_incremental,
    gate5_implementability,
    score_to_position,
)
from screening_charts import (
    backtest_chart_base64,
    fear_greed_overlay_chart_base64,
    heatmap_chart_base64,
    raw_data_chart_base64,
    score_trend_chart_base64,
)
from screening_render import (
    EXISTING_COLUMN_LABELS,
    GATE_NOT_RUN,
    POSITIONING_STATEMENT,
    PROMOTE_UI_CSS,
    SOURCE_CATALOG,
    _corr_factor_options,
    _historical_factor_labels,
    render_registry_index,
    render_screening_report,
)

REGISTRY_PATH = "factor_screening_registry.json"
CHART_DIR = "chart"


# ================================================================ 主流程
def run_screening(config):
    key = config["key"]
    label = config.get("label", key)
    print(f"[{label}] 抓取延伸歷史資料（20年＋暖身期）...")
    ext_df_20y, raw_ranges = fva.fetch_extended_history(years=fva._V["vigintile_years"])

    score_full, raw_metric_full, ext_df_20y = build_candidate_score(config, ext_df_20y, ud.fetch_yahoo_close, ud.fetch_fred_series)

    out_start = pd.Timestamp(ud._G["output_start_date"])
    main_df_pre = ext_df_20y.loc[ext_df_20y.index >= out_start].copy()
    main_score_pre = score_full.reindex(main_df_pre.index)
    main_raw_pre = raw_metric_full.reindex(main_df_pre.index)

    result = {"key": key, "label": label, "config": config, "test_date": date.today().isoformat(),
              "raw_ranges": {k: (str(v[0].date()), str(v[1].date()), v[2]) for k, v in raw_ranges.items()}}

    # 五關固定全部跑完，不再因為某一關沒過就提早停止——這個平台的定位是研究輔助工具，
    # 只提供判斷建議，不擋結果，最終是否採用交給使用者自行判斷。任一關萬一因為資料
    # 太極端而算不出來，用try/except接住、記成「此關無法完成分析」，不讓整次測試中斷。
    print(f"[{label}] 第一關：資料健檢 ...")
    try:
        g1 = gate1_data_health(config, main_score_pre, main_raw_pre, ext_df_20y)
    except Exception as e:
        g1 = {"passed": None, "reasons": [f"此關計算失敗：{e}"]}
    result["gate1"] = g1

    print(f"[{label}] 第二關：單獨效力 ...")
    try:
        g2 = gate2_efficacy(key, score_full, ext_df_20y)
    except Exception as e:
        g2 = {"passed": None, "reasons": [f"此關計算失敗：{e}"], "main_df": main_df_pre}
    result["gate2"] = g2
    main_df = g2.get("main_df", main_df_pre)

    print(f"[{label}] 第三關：穩定性 ...")
    try:
        g3 = gate3_stability(key, main_df)
    except Exception as e:
        g3 = {"passed": None, "reasons": [f"此關計算失敗：{e}"]}
    result["gate3"] = g3

    print(f"[{label}] 第四關：增量價值 ...")
    try:
        g4 = gate4_incremental(key, main_df[key], main_df)
    except Exception as e:
        g4 = {"passed": None, "reasons": [f"此關計算失敗：{e}"]}
    result["gate4"] = g4

    print(f"[{label}] 第五關：可實作性 ...")
    try:
        g5 = gate5_implementability(main_df[key])
    except Exception as e:
        g5 = {"passed": None, "reasons": [f"此關計算失敗：{e}"]}
    result["gate5"] = g5

    print(f"[{label}] 回測分析 ...")
    try:
        # 刻意用完整的20年延伸歷史，不是五道關卡用的2020+主範圍——回測要拆樣本內/外，
        # 6年半的資料切一半只剩3年多，Sharpe衰退比例會被雜訊主導、看不出真正的過度配適。
        # 這跟平台既有的10年/20年分桶分析用更長窗口是同一個道理。
        df_bt = ext_df_20y.copy()
        df_bt[key] = score_full.reindex(df_bt.index)
        result["backtest"] = backtest_strategy(df_bt[key], df_bt)
    except Exception as e:
        print(f"  回測計算失敗（不影響其他關卡）：{e}")
        result["backtest"] = None

    # 整體建議：只統計「真的判斷出及格/不及格」的關卡(第一到四關；第五關换手率
    # 本身就沒有及格線，永遠不計入分母)，第五關永遠是資訊性質。
    judged = [g1, g2, g3, g4]
    n_judged = sum(1 for g in judged if g.get("passed") is not None)
    n_passed = sum(1 for g in judged if g.get("passed") is True)
    result["gates_passed"] = f"{n_passed}/{n_judged}" if n_judged else "無法判斷"

    if n_judged == 0:
        headline = "資料不足，無法完成關卡判斷"
    elif n_passed == n_judged:
        headline = f"{n_passed}/{n_judged}項關卡通過，初步判斷具備統計相關性，建議可以考慮"
    elif n_passed >= n_judged / 2:
        headline = f"{n_passed}/{n_judged}項關卡通過，部分指標有疑慮，建議謹慎評估後再決定"
    else:
        headline = f"{n_passed}/{n_judged}項關卡通過，多項指標不理想，建議不採用"
    result["final_verdict"] = f"{headline}——本工具僅提供研究建議，最終是否採用由使用者自行判斷。"
    result["stopped_at"] = None  # 不再有「停在哪一關」這件事，保留欄位是為了跟舊登記簿資料相容
    return result


# ================================================================ 登記簿（防止多重比較自欺）
def _load_registry():
    if os.path.exists(REGISTRY_PATH):
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            return json.load(f)
    return []


def _registry_summary(result):
    """把完整result濃縮成登記簿要存的精簡版本，不存熱力圖矩陣等大型資料，
    避免registry檔案隨測試次數無限膨脹。"""
    entry = {
        "key": result["key"], "label": result["label"], "test_date": result["test_date"],
        "mode": result["config"]["mode"], "final_verdict": result["final_verdict"],
        "gates_passed": result["gates_passed"],
    }
    g2 = result.get("gate2", {})
    if "main_ic" in g2:
        entry["main_ic"] = g2["main_ic"]["rho"]
        entry["monotonicity"] = g2["monotonicity"]
        entry["pattern_tag"] = g2["pattern_tag"]
    g4 = result.get("gate4", {})
    if "max_corr" in g4:
        entry["max_corr"] = g4["max_corr"]
        entry["max_corr_key"] = g4["max_corr_key"]
        entry["loo_delta"] = g4["delta"]
    return entry


def append_to_registry(result):
    registry = _load_registry()
    registry.append(_registry_summary(result))
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)
    return registry


def screen_and_save(config):
    """跑完整流程、產生報告、更新登記簿——這是命令列/一般使用的主要入口。"""
    result = run_screening(config)
    os.makedirs(CHART_DIR, exist_ok=True)
    report_html = render_screening_report(result)
    report_path = os.path.join(CHART_DIR, f"screening_{result['key']}.html")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_html)
    registry = append_to_registry(result)
    rebuild_index()
    print(f"\n完成！{result['final_verdict']}")
    print(f"報告：{report_path}")
    print(f"登記簿：{CHART_DIR}/screening_index.html")
    return result


def rebuild_index():
    """只重新產生screening_index.html，不重跑任何因子測試——升等/退回候選因子後
    用這個刷新登記簿頁的「已升等」徽章跟按鈕狀態，不需要知道任何因子的原始config。"""
    os.makedirs(CHART_DIR, exist_ok=True)
    registry = _load_registry()
    index_html = render_registry_index(registry)
    with open(os.path.join(CHART_DIR, "screening_index.html"), "w", encoding="utf-8") as f:
        f.write(index_html)
    print(f"登記簿已重新產生：{CHART_DIR}/screening_index.html")


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2 and sys.argv[1] == "--rebuild-index":
        rebuild_index()
    elif len(sys.argv) < 2:
        print("用法：python3 factor_screening.py <candidate_config.json>")
        print("      python3 factor_screening.py --rebuild-index")
        sys.exit(1)
    else:
        with open(sys.argv[1], encoding="utf-8") as f:
            cfg = json.load(f)
        screen_and_save(cfg)
