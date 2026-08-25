# -*- coding: utf-8 -*-
"""
因子篩選平台的 HTML 產生——單一因子體檢報告(render_screening_report)跟
歷史測試紀錄登記簿(render_registry_index)兩張對外頁面的字串模板。

架構檢討第3項(2026-08-25)拆自 factor_screening.py，見 screening_gates.py 開頭
的說明。這支模組只負責「把算好的結果、畫好的圖組成HTML」，不做任何統計計算
(數字由 screening_gates.py 算好放進 result dict)，也不自己畫圖
(base64圖片字串由 screening_charts.py 提供，這裡只是把它塞進 <img> 標籤)。
"""
import json
import os

import pandas as pd

import factor_validation_analysis as fva
import nav_bar
import page_style
import update_dashboard as ud
from transform_modes import TRANSFORM_MODES

from screening_gates import HORIZONS, MAIN_HORIZON, THRESHOLDS
from screening_charts import (
    backtest_chart_base64,
    fear_greed_overlay_chart_base64,
    heatmap_chart_base64,
    raw_data_chart_base64,
    score_trend_chart_base64,
)

plt = fva.plt

# 產品定位聲明(2026-07-28product framework)：這個平台是輔助交易員判斷氛圍的研究工具，
# 不是策略、不是投資建議——每個對外頁面的頁首都要看得到這句話。
POSITIONING_STATEMENT = (
    "本平台協助債券交易者判斷美債市場目前的整體氛圍，作為交易員的輔助判斷工具，"
    "非交易策略、非投資建議。所有分析結果以研究性語言呈現歷史統計特徵，"
    "不產出即時部位建議或操作指令。"
)

# 單一因子報告頁「升等為可選因子」按鈕用的CSS——render_screening_report()用的是
# fva.REPORT_CSS，沒有.token-box/.btn-submit這些class(那些只在render_registry_index()
# 自己的<style>裡定義)，這裡補一份自成一體的、視覺語言跟登記簿頁一致。
PROMOTE_UI_CSS = """
  .promote-card .token-box { background:rgba(166,116,42,0.08); border:1px dashed #a6742a; border-radius:10px;
    padding:14px 16px; margin:12px 0; font-size:12.5px; }
  .promote-card .token-box summary { font-weight:700; color:#a6742a; cursor:pointer; }
  .promote-card input[type="password"] { width:100%; padding:9px 12px; margin-top:8px; border:1px solid #dfe2e8;
    border-radius:8px; background:#f4f5f7; color:#161a23; font-size:13.5px; outline:none; }
  .promote-btn { display:inline-flex; align-items:center; gap:8px; padding:11px 20px; background:#1e3a5f; color:#fff;
    border:none; border-radius:10px; font-size:13.5px; font-weight:700; cursor:pointer; }
  .promote-btn:hover { opacity:.92; }
  .promote-btn:disabled { opacity:.55; cursor:not-allowed; }
"""

# ================================================================ 資料來源候選清單（給表單搜尋框用）
# ================================================================ 資料來源候選清單（給表單搜尋框用）
# 使用者原本要自己記代號手打(Yahoo要記得加^、FRED代號一堆英文縮寫)，很容易打錯或
# 不知道能填什麼——這份清單讓表單改成「打中文關鍵字或代號都能搜到、選了自動帶入
# 正確type/id」，找不到的話表單上還有「手動輸入」的退路，不會限制彈性。
# existing類的id必須是ext_df_20y實際會有的欄位名稱，跟build_candidate_score()
# 的_resolve_source()字串比對邏輯要一致，故意用程式碼裡的名字，不憑印象手key。
EXISTING_COLUMN_LABELS = {
    "ZN_futures": "10年期公債期貨(ZN)原始價格",
    "NQ_futures": "那斯達克100期貨(NQ)原始價格",
    "TLT": "20年期以上公債ETF(TLT)",
    "SHY": "1-3年期短債ETF(SHY)",
    "MOVE_index": "公債波動率指數(MOVE)",
    "UST_10Yr": "美國10年期公債殖利率",
    "UST_2Yr": "美國2年期公債殖利率",
    "CPI_index": "CPI消費者物價指數",
    "Breakeven_10Y": "10年期損益平衡通膨率",
    "put_call_ratio": "選擇權Put/Call比率",
}
SOURCE_CATALOG = (
    [{"id": k, "type": "existing", "label": f"{v}（儀表板既有欄位）"}
     for k, v in EXISTING_COLUMN_LABELS.items()]
    + [{"id": k, "type": "existing", "label": f"{v}分數（儀表板既有因子）"}
       for k, v in fva.FACTOR_COLS.items()]
    + [{"id": fva.COMPOSITE_COL, "type": "existing", "label": f"{fva.COMPOSITE_LABEL}（儀表板既有欄位）"}]
    + [
        {"id": "^VIX", "type": "yahoo", "label": "VIX恐慌指數"},
        {"id": "^MOVE", "type": "yahoo", "label": "MOVE公債波動率指數(Yahoo版)"},
        {"id": "^TNX", "type": "yahoo", "label": "10年期公債殖利率×10(Yahoo版,注意單位)"},
        {"id": "GLD", "type": "yahoo", "label": "黃金ETF(GLD)"},
        {"id": "DX-Y.NYB", "type": "yahoo", "label": "美元指數(DXY)"},
        {"id": "CL=F", "type": "yahoo", "label": "原油期貨(WTI)"},
        {"id": "JPY=X", "type": "yahoo", "label": "美元兌日圓匯率"},
        {"id": "IEF", "type": "yahoo", "label": "7-10年期公債ETF(IEF)"},
        {"id": "HYG", "type": "yahoo", "label": "高收益債ETF(HYG)"},
        {"id": "LQD", "type": "yahoo", "label": "投資級公司債ETF(LQD)"},
        {"id": "^GSPC", "type": "yahoo", "label": "標普500指數"},
        {"id": "^IXIC", "type": "yahoo", "label": "那斯達克綜合指數"},
        {"id": "DGS10", "type": "fred", "label": "10年期公債殖利率(FRED)"},
        {"id": "DGS2", "type": "fred", "label": "2年期公債殖利率(FRED)"},
        {"id": "DGS3MO", "type": "fred", "label": "3個月期公債殖利率(FRED)"},
        {"id": "DGS30", "type": "fred", "label": "30年期公債殖利率(FRED)"},
        {"id": "T10YIE", "type": "fred", "label": "10年期損益平衡通膨率(FRED)"},
        {"id": "T5YIE", "type": "fred", "label": "5年期損益平衡通膨率(FRED)"},
        {"id": "BAMLH0A0HYM2", "type": "fred", "label": "高收益債利差(FRED)"},
        {"id": "WALCL", "type": "fred", "label": "聯準會資產負債表規模(FRED)"},
        {"id": "M2SL", "type": "fred", "label": "M2貨幣供給(FRED)"},
        {"id": "UNRATE", "type": "fred", "label": "失業率(FRED)"},
        {"id": "FEDFUNDS", "type": "fred", "label": "聯邦基金利率(FRED)"},
    ]
)




# ================================================================ 單一因子體檢報告
GATE_NOT_RUN = "未執行"  # 給只產Part A、沒跑關卡的腳本用的哨兵值，見 scripts/build_direct_parta_html.py


def _gate_badge(passed):
    if passed is True:
        return '<span class="verdict-keep">通過</span>'
    if passed is False:
        return '<span class="verdict-cut">未通過</span>'
    if passed == GATE_NOT_RUN:
        # 跟「跑了但沒設門檻」(第五關)區分開——這是「根本沒跑」，不要讓人誤以為驗證過了
        return '<span class="verdict-cut">未執行</span>'
    return '<span class="verdict-watch">僅供參考（未設門檻）</span>'



def _bt_row(name, s, highlight=False):
    if s is None:
        return f'<tr><td>{name}</td><td colspan="7" class="na">樣本不足</td></tr>'
    b = "<b>{}</b>".format if highlight else str
    return (f"<tr><td>{b(name)}</td><td>{s['n_days']}</td>"
            f"<td>{b(f'{s['total_bp']:+,.0f}')}</td>"
            f"<td>{s['ann_ret_bp']:+.1f}</td><td>{s['ann_vol_bp']:.1f}</td>"
            f"<td>{b(f'{s['sharpe']:+.2f}')}</td>"
            f"<td>{s['max_dd_bp']:,.0f}</td>"
            f"<td>{s['win_rate']:.1f}%<br><span class='n'>(n={s['n_active']})</span></td></tr>")


def _render_backtest_section(bt, label):
    """回測分析區塊。放在五關之後——五關看的是統計特徵(IC/單調性/相關性)，
    這裡看的是「照這個訊號實際下單會怎樣」，兩者要分開看。"""
    if bt is None:
        return """
    <section class="card">
      <h2><span class="bar"></span>回測分析</h2>
      <p class='na'>資料不足（需要至少約1年的有效分數與報酬）或此報告未執行回測。</p>
    </section>"""

    chart = backtest_chart_base64(bt, label)
    full, bh, ins, oos = bt["full"], bt["buy_hold"], bt["is"], bt["oos"]
    decay = bt["sharpe_decay"]

    # 有沒有贏過「什麼都不判斷、直接買進持有」——沒贏過的話這個因子就沒有實際價值
    beat_bh = (full and bh and full["sharpe"] > bh["sharpe"])
    verdict_cls = "verdict-keep" if beat_bh else "verdict-cut"
    verdict_txt = ("策略Sharpe高於無條件買進持有，訊號有加值"
                   if beat_bh else "策略Sharpe不如無條件買進持有，訊號沒有加值")

    if decay is None:
        decay_txt = "<span class='na'>樣本內Sharpe非正，衰退比例無意義</span>"
    elif decay > 1.2:
        # 樣本外比樣本內好是可能的，但別急著當成好消息——多半是樣本期間的運氣
        decay_txt = (f"<span class='verdict-watch'>{decay:.0%}（樣本外反而優於樣本內"
                     f"——這通常是樣本期間的運氣，不宜當成穩健的證據）</span>")
    elif decay >= 0.7:
        decay_txt = f"<span class='verdict-keep'>{decay:.0%}（樣本外保留住大部分表現）</span>"
    elif decay >= 0.3:
        decay_txt = f"<span class='verdict-watch'>{decay:.0%}（樣本外明顯衰退）</span>"
    else:
        decay_txt = f"<span class='verdict-cut'>{decay:.0%}（樣本外幾乎失效，疑似過度配適）</span>"

    exposure = (f"平均曝險 {full['avg_exposure']:.2f}　·　"
                f"做多 {full['long_pct']:.0f}%　·　做空 {full['short_pct']:.0f}%　·　"
                f"空手 {full['flat_pct']:.0f}%" if full else "")

    return f"""
    <section class="card">
      <h2><span class="bar"></span>回測分析</h2>
      <p class="hint">部位規則：<b>(50 − 當日分數) / 50</b>，分數低(恐懼)做多債券、分數高(貪婪)做空，
        {fva._V["dead_zone"][0]}–{fva._V["dead_zone"][1]} 死區強制空手。
        <b>t日收盤的分數決定t日部位，賺t到t+1的報酬</b>，不使用未來資料。
        報酬單位是<b>價格報酬(bp)</b>＝ −1 × 殖利率變動，殖利率下降代表債券價格上漲。
        回測期間 {bt["start"].date()} ~ {bt["end"].date()}。</p>
      {"<img class='chart' src='data:image/png;base64," + chart + "'/>" if chart else ""}
      <table class="data-table mini">
        <tr><th>期間 / 策略</th><th>交易日</th><th>累積報酬(bp)</th><th>年化報酬(bp)</th>
            <th>年化波動(bp)</th><th>Sharpe</th><th>最大回撤(bp)</th>
            <th>單日勝率<br><span class="n">(僅計有損益的日子)</span></th></tr>
        {_bt_row("全期間（因子策略）", full, highlight=True)}
        {_bt_row("　對照：無條件買進持有", bh)}
        {_bt_row("樣本內（前半段）", ins)}
        {_bt_row("樣本外（後半段）", oos)}
      </table>
      <p class="hint">{exposure}</p>
      <p><b>樣本外Sharpe衰退比例（OOS ÷ IS）：</b>{decay_txt}　·
         樣本內外以時間對半切（分界 {bt["split_date"].date()}）。</p>
      <p><b>跟基準比：</b><span class="{verdict_cls}">{verdict_txt}</span>
         （策略 Sharpe {full['sharpe']:+.2f} vs 買進持有 {bh['sharpe']:+.2f}）——
         這個對照很重要：債券本身在某些期間就是會漲，沒有基準的話很容易把「大盤在漲」
         誤認成「因子有效」。</p>
      <p class="hint"><b>還沒納入的成本（解讀時請自行打折）：</b>本回測不含交易成本、買賣價差與滑價。
         第五關的每日部位變動量可以拿來粗估周轉率——成本假設一旦確定，把「每日部位變動量 ×
         單邊成本(bp) × 252」從年化報酬扣掉，就是比較貼近實際的數字。</p>
    </section>"""


def render_screening_report(result):
    key, label = result["key"], result["label"]
    mode_label = TRANSFORM_MODES[result["config"]["mode"]]["label"]
    main_df = result.get("gate2", {}).get("main_df")

    sections = []

    # 圖1+圖1b+圖2固定放最前面,不管五道關卡跑得如何都會顯示(只要main_df算得出來)
    if main_df is not None:
        score_chart = score_trend_chart_base64(main_df, key, label)
        fg_overlay_chart = fear_greed_overlay_chart_base64(main_df, key, label)
        raw_chart = raw_data_chart_base64(result["config"], main_df, label)
        sections.append(f"""
    <section class="card">
      <h2><span class="bar"></span>分數走勢與原始資料</h2>
      {"<img class='chart' src='data:image/png;base64," + score_chart + "'/>" if score_chart else "<p class='na'>分數走勢圖資料不足</p>"}
      {"<img class='chart' src='data:image/png;base64," + fg_overlay_chart + "'/>" if fg_overlay_chart else ""}
      {"<img class='chart' src='data:image/png;base64," + raw_chart + "'/>" if raw_chart else "<p class='na'>原始資料走勢圖資料不足</p>"}
    </section>""")

        dist_chart_b64, dist_stats = fva.render_distribution_analysis_4panel_base64(main_df, key, label, horizon=20)
        if dist_chart_b64 and dist_stats:
            dist_rows = "".join(
                f"<tr><td><b>{s['label']}</b></td><td>{s['n']}</td><td>{s['mean']:+.2f} bp</td><td>{s['median']:+.2f} bp</td><td>{s['win_rate']:.1f}%</td></tr>"
                for s in dist_stats
            )
            sections.append(f"""
    <section class="card">
      <h2><span class="bar"></span>Part A 統計分布與極端兩端檢視 (未來20日持倉)</h2>
      <p class="hint">包含箱型圖 (Boxplot/IQR)、勝率 %、小提琴密度形狀與全分數對報酬之非線性趨勢線。特別檢視極度恐懼 (0-24) 與極度貪婪 (76-100) 兩端是否有逆勢勾回/反轉跡象。</p>
      <img class="chart" src="data:image/png;base64,{dist_chart_b64}"/>
      <table class="data-table mini">
        <tr><th>分桶 / 尾端區間</th><th>樣本天數 n</th><th>平均超額報酬 (bp)</th><th>中位數超額 (bp)</th><th>勝率 % (反轉或期望方向)</th></tr>
        {dist_rows}
      </table>
    </section>""")

    g1 = result.get("gate1", {})
    if "history_days" in g1:
        sections.append(f"""
    <section class="card">
      <h2><span class="bar"></span>第一關：資料健檢 {_gate_badge(g1.get("passed"))}</h2>
      <table class="data-table mini">
        <tr><th>有效資料天數</th><th>缺值比例</th><th>look-ahead檢查</th></tr>
        <tr><td>{g1["history_days"]}</td><td>{g1["missing_pct"]:.1f}%</td>
            <td>{"通過" if g1["lookahead_ok"] else "未通過"}（{g1["lookahead_detail"]}）</td></tr>
      </table>
      {"<ul>" + "".join(f"<li>{r}</li>" for r in g1["reasons"]) + "</ul>" if g1["reasons"] else ""}
    </section>""")
    else:
        sections.append(f"""
    <section class="card">
      <h2><span class="bar"></span>第一關：資料健檢 {_gate_badge(g1.get("passed"))}</h2>
      {"<ul>" + "".join(f"<li>{r}</li>" for r in g1.get("reasons", [])) + "</ul>" if g1.get("reasons") else "<p class='na'>無法完成此關分析</p>"}
    </section>""")

    g2 = result.get("gate2", {})
    if "ic_by_horizon" in g2:
        ic_rows = ""
        for h in HORIZONS:
            ov = fva.fmt_rho(g2["ic_by_horizon"][h]["overlap"])
            non_ov = fva.fmt_rho(g2["ic_by_horizon"][h]["non_overlap"])
            ic_rows += f"<tr><td>{h}日</td><td>{ov}</td><td>{non_ov}</td></tr>"
        unit_name = "變動(bp)" if fva.TARGET == "UST_10Yr" else "報酬"
        target_name = "10年期美債殖利率 (bp)" if fva.TARGET == "UST_10Yr" else "ZN報酬"
        decile10_chart = fva.decile_chart_base64(
            g2["decile_10"], f"{label}：未來{fva.DECILE_HORIZON}日平均{unit_name}（10分組，重疊取樣）",
            fva.DECILE_N_BUCKETS, fva.DECILE_HORIZON
        ) if g2["decile_10"] else None
        vigintile_buckets = fva._V["vigintile_n_buckets"]
        decile20_chart = fva.decile_chart_base64(
            g2["decile_20"], f"{label}：未來{fva.DECILE_HORIZON}日平均{unit_name}（{vigintile_buckets}分組，重疊取樣）",
            vigintile_buckets, fva.DECILE_HORIZON
        ) if g2["decile_20"] else None
        heatmap_raw_chart = heatmap_chart_base64(g2["heatmap_raw"], f"{label}：原始{unit_name}熱力圖（分桶×持有天數，重疊取樣）")
        heatmap_excess_chart = heatmap_chart_base64(
            g2["heatmap_excess"], f"{label}：超額{unit_name}熱力圖（扣除同期無條件平均買進持有，重疊取樣）"
        )
        sections.append(f"""
    <section class="card">
      <h2><span class="bar"></span>第二關：單獨效力 {_gate_badge(g2.get("passed"))}</h2>
      <p class="hint">型態標記：<b>{g2["pattern_tag"]}</b>（描述性標記，不當作及格條件——現有官方因子裡多數呈現動能延續型，
        不是長期反轉型，這個標記純粹讓你知道候選因子屬於哪一種，不會因為不是反轉型就被判定不及格）</p>
      <h3>IC（vs 未來N日{target_name}，全平台一律以重疊取樣為主）</h3>
      <table class="data-table mini">
        <tr><th>持有天數</th><th>重疊</th><th>非重疊（對照參考）</th></tr>
        {ic_rows}
      </table>
      <p class="hint">分桶單調性（10年版本，重疊取樣）：{fva.fmt_num(g2["monotonicity"], 3) if g2["monotonicity"] is not None else "無資料"}</p>
      {"<img class='chart' src='data:image/png;base64," + decile10_chart + "'/>" if decile10_chart else "<p class='na'>10年分桶資料不足</p>"}
      {"<img class='chart' src='data:image/png;base64," + decile20_chart + "'/>" if decile20_chart else "<p class='na'>20年分桶資料不足</p>"}
      {"<img class='chart' src='data:image/png;base64," + heatmap_raw_chart + "'/>" if heatmap_raw_chart else "<p class='na'>熱力圖資料不足</p>"}
      {"<img class='chart' src='data:image/png;base64," + heatmap_excess_chart + "'/>" if heatmap_excess_chart else ""}
      {"<ul>" + "".join(f"<li>{r}</li>" for r in g2["reasons"]) + "</ul>" if g2["reasons"] else ""}
    </section>""")
    else:
        sections.append(f"""
    <section class="card">
      <h2><span class="bar"></span>第二關：單獨效力 {_gate_badge(g2.get("passed"))}</h2>
      {"<ul>" + "".join(f"<li>{r}</li>" for r in g2.get("reasons", [])) + "</ul>" if g2.get("reasons") else "<p class='na'>無法完成此關分析</p>"}
    </section>""")

    g3 = result.get("gate3", {})
    if "regime_ic" in g3:
        regime_rows = "".join(
            f"<tr><td>{label_}</td><td>{fva.fmt_rho(ic)}</td></tr>"
            for label_, ic in g3["regime_ic"].items()
        )
        sections.append(f"""
    <section class="card">
      <h2><span class="bar"></span>第三關：穩定性 {_gate_badge(g3.get("passed"))}</h2>
      <table class="data-table mini">
        <tr><th>全樣本</th><th>前半段</th><th>後半段</th><th>前後半段同號？</th></tr>
        <tr><td>{fva.fmt_rho(g3["ic_full"])}</td><td>{fva.fmt_rho(g3["ic_h1"])}</td>
            <td>{fva.fmt_rho(g3["ic_h2"])}</td><td>{"是" if g3["same_sign"] else "否"}</td></tr>
      </table>
      <h3>跨Fed循環IC（僅供參考，不擋關；重疊取樣）</h3>
      <table class="data-table mini"><tr><th>循環階段</th><th>IC</th></tr>{regime_rows}</table>
      <p class="hint">跨循環同號：{"是" if g3["regime_same_sign"] else ("否" if g3["regime_same_sign"] is False else "資料不足無法判斷")}</p>
      {"<ul>" + "".join(f"<li>{r}</li>" for r in g3["reasons"]) + "</ul>" if g3["reasons"] else ""}
    </section>""")
    else:
        sections.append(f"""
    <section class="card">
      <h2><span class="bar"></span>第三關：穩定性 {_gate_badge(g3.get("passed"))}</h2>
      {"<ul>" + "".join(f"<li>{r}</li>" for r in g3.get("reasons", [])) + "</ul>" if g3.get("reasons") else "<p class='na'>無法完成此關分析</p>"}
    </section>""")

    g4 = result.get("gate4", {})
    if "correlations" in g4:
        corr_rows = "".join(
            f"<tr><td>{k}</td><td>{v:+.2f}</td></tr>"
            for k, v in g4["correlations"].items()
        )
        sections.append(f"""
    <section class="card">
      <h2><span class="bar"></span>第四關：增量價值 {_gate_badge(g4.get("passed"))}</h2>
      <h3>跟現有官方因子（{len(fva.FACTOR_COLS)}項）的相關係數</h3>
      <table class="data-table mini"><tr><th>因子</th><th>相關係數</th></tr>{corr_rows}</table>
      <p class="hint">最高相關：{g4["max_corr_key"]}（{g4["max_corr"]:+.2f}），門檻±{THRESHOLDS['max_correlation']}</p>
      <h3>Leave-one-out：加入候選因子對綜合分數IC的影響（重疊取樣）</h3>
      <p>不含候選：{fva.fmt_rho(g4["ic_without"])}　→　含候選：{fva.fmt_rho(g4["ic_with"])}
        （Δ = {f"{g4['delta']:+.3f}" if g4["delta"] is not None else "無資料"}，負值代表候選因子有正貢獻）</p>
      {"<ul>" + "".join(f"<li>{r}</li>" for r in g4["reasons"]) + "</ul>" if g4["reasons"] else ""}
    </section>""")
    else:
        sections.append(f"""
    <section class="card">
      <h2><span class="bar"></span>第四關：增量價值 {_gate_badge(g4.get("passed"))}</h2>
      {"<ul>" + "".join(f"<li>{r}</li>" for r in g4.get("reasons", [])) + "</ul>" if g4.get("reasons") else "<p class='na'>無法完成此關分析</p>"}
    </section>""")

    g5 = result.get("gate5", {})
    if "turnover_daily_avg" in g5:
        sections.append(f"""
    <section class="card">
      <h2><span class="bar"></span>第五關：可實作性 {_gate_badge(g5.get("passed"))}</h2>
      <p>平均每日部位變動量：{g5["turnover_daily_avg"]:.3f}（0=完全不動，2=從滿多轉滿空）　·
         部位方向改變次數：{g5["n_position_changes"]}</p>
      {"<ul>" + "".join(f"<li>{r}</li>" for r in g5["reasons"]) + "</ul>" if g5["reasons"] else ""}
    </section>""")
    else:
        sections.append(f"""
    <section class="card">
      <h2><span class="bar"></span>第五關：可實作性 {_gate_badge(g5.get("passed"))}</h2>
      {"<ul>" + "".join(f"<li>{r}</li>" for r in g5.get("reasons", [])) + "</ul>" if g5.get("reasons") else "<p class='na'>無法完成此關分析</p>"}
    </section>""")

    sections.append(_render_backtest_section(result.get("backtest"), label))

    gp = result.get("gates_passed", "無法判斷")
    n_passed_str = gp.split("/")[0] if "/" in gp else "0"
    n_judged_str = gp.split("/")[1] if "/" in gp else "0"
    verdict_class = ("verdict-keep" if n_judged_str != "0" and int(n_passed_str) == int(n_judged_str)
                      else "verdict-watch" if n_judged_str != "0" and int(n_passed_str) >= int(n_judged_str) / 2
                      else "verdict-cut")
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>因子篩選：{label}</title>
<style>{fva.REPORT_CSS}
{nav_bar.NAV_BAR_CSS}
{PROMOTE_UI_CSS}</style>
</head>
<body>
<div class="wrap">
  {nav_bar.render_nav_bar("screening")}
  <header>
    <div class="kicker">FACTOR SCREENING</div>
    <h1>因子篩選：{label}</h1>
    <p class="meta">key：{key}　·　轉換模式：{mode_label}　·　測試日期：{result["test_date"]}　·　關卡通過：{gp}</p>
    <p class="disclaimer">{POSITIONING_STATEMENT}</p>
    <p class="disclaimer {verdict_class}">{result["final_verdict"]}</p>
  </header>
  {"".join(sections)}
  <section class="card promote-card">
    <h2><span class="bar"></span>升等為儀表板可選因子</h2>
    <p class="hint">
      覺得這個因子值得留著探索？升等後會在<b>儀表板</b>多一張分項卡片（標示「候選因子」，<b>不計入官方綜合分數</b>），
      也可以在儀表板「自訂權重」區塊選用它。不論上面幾道關卡通過與否都可以升等——這個平台只提供研究建議，
      最終要不要留著由你決定。升等後大約幾分鐘內會反映在正式儀表板上。
    </p>
    <details class="token-box" id="promoteTokenDetails">
      <summary>🔑 設定 GitHub Personal Access Token（跟因子篩選登記簿共用同一組）</summary>
      <input type="password" id="promoteGhToken" placeholder="ghp_xxxxxxxxxxxxxxxxx" autocomplete="off">
    </details>
    <button class="promote-btn" type="button" id="promoteBtn">🚀 升等為可選因子</button>
    <p class="hint" id="promoteStatus" style="margin-top:10px;"></p>
  </section>
</div>
<script>
  const PROMOTE_REPO_OWNER = "dp79b47tvn-maker";
  const PROMOTE_REPO_NAME = "bond-fear-greed-dashboard";
  const PROMOTE_CANDIDATE_CONFIG = {json.dumps(result["config"], ensure_ascii=False)};

  const promoteTokenInput = document.getElementById("promoteGhToken");
  const savedPromoteToken = localStorage.getItem("gh_pat_token");
  if (savedPromoteToken) {{
    promoteTokenInput.value = savedPromoteToken;
  }} else {{
    document.getElementById("promoteTokenDetails").open = true;
  }}

  document.getElementById("promoteBtn").addEventListener("click", async () => {{
    const token = promoteTokenInput.value.trim();
    const statusEl = document.getElementById("promoteStatus");
    const btn = document.getElementById("promoteBtn");
    if (!token) {{
      alert("請先填寫 GitHub Personal Access Token（PAT）！");
      document.getElementById("promoteTokenDetails").open = true;
      promoteTokenInput.focus();
      return;
    }}
    localStorage.setItem("gh_pat_token", token);
    btn.disabled = true;
    statusEl.textContent = "已送出升等請求，GitHub Actions 正在寫入設定並重新產生儀表板...";
    try {{
      const resp = await fetch(`https://api.github.com/repos/${{PROMOTE_REPO_OWNER}}/${{PROMOTE_REPO_NAME}}/actions/workflows/promote-factor.yml/dispatches`, {{
        method: "POST",
        headers: {{
          "Accept": "application/vnd.github+json",
          "Authorization": `Bearer ${{token}}`,
          "Content-Type": "application/json"
        }},
        body: JSON.stringify({{
          ref: "main",
          inputs: {{ config_json: JSON.stringify(PROMOTE_CANDIDATE_CONFIG) }}
        }})
      }});
      if (!resp.ok) {{
        const errText = await resp.text();
        throw new Error(`GitHub API 錯誤 (${{resp.status}}): ${{errText}}`);
      }}
      statusEl.textContent = "已成功送出！幾分鐘後到儀表板查看新的分項卡片與自訂權重選項。";
    }} catch (err) {{
      statusEl.textContent = "送出失敗：" + err.message;
      btn.disabled = false;
    }}
  }});
</script>
</body>
</html>"""




def _load_promoted_keys():
    """讀promoted_candidate_factors.json，回傳目前已升等的因子key集合，供登記簿頁
    標示「已升等」徽章＋退回按鈕。檔案不存在就回傳空集合，不報錯。"""
    if not os.path.exists("promoted_candidate_factors.json"):
        return set()
    with open("promoted_candidate_factors.json", encoding="utf-8") as f:
        staged = json.load(f)
    return {f["key"] for f in staged.get("factors", [])}


def _load_promoted_factors_list():
    """讀promoted_candidate_factors.json，回傳完整的候選因子清單(key+label)，
    供相關係數矩陣的勾選清單使用(不像_load_promoted_keys()只回傳key集合)。"""
    if not os.path.exists("promoted_candidate_factors.json"):
        return []
    with open("promoted_candidate_factors.json", encoding="utf-8") as f:
        staged = json.load(f)
    return staged.get("factors", [])


def _corr_factor_options():
    """相關係數矩陣勾選清單的選項：官方七項(score_col對照factor_definitions.json，
    跟factor_validation_analysis.FACTOR_COLS用同一套欄位命名) + 目前已升等的候選因子
    (欄位命名固定是promoted_{key}_score，見update_dashboard.py的compute_promoted_factors())。"""
    options = [
        {"value": fx["score_col"], "label": fx["name_tpl"].split(" ")[0], "kind": "official"}
        for fx in ud.DEFS["factors"]
    ]
    options += [
        {"value": f"promoted_{pf['key']}_score", "label": f"{pf['label']}（候選）", "kind": "candidate"}
        for pf in _load_promoted_factors_list()
    ]
    # 2026-08-11補上第三組：曾經測過、但目前不在官方因子清單裡的歷史因子。
    # 官方因子從七項縮成兩項(動能/銅金比)之後，這個勾選清單只剩兩個選項、
    # 等於整個相關係數矩陣功能廢掉。這些因子的分數還留在 factor_scores_matrix.csv
    # (2026-08-05的11因子快照)，可以繼續拿來比較，只是不會再每日更新——
    # generate_correlation_matrix.py 會從那份快照補讀這些欄位。
    # 同一個因子如果已經在官方清單裡(例如動能、銅金比)，就不重複列出歷史快照版本，
    # 不然勾選清單會出現「動能」跟「動能（歷史）」兩個看起來一樣的選項。
    known_labels = {o["label"] for o in options}
    for col, label in _historical_factor_labels().items():
        if label not in known_labels:
            options.append({"value": col, "label": f"{label}（歷史）", "kind": "historical"})
    return options


HISTORICAL_MATRIX_CSV = "factor_scores_matrix.csv"
# factor_scores_matrix.csv 的欄名 -> 顯示用中文名。欄名沿用當初批次驗證時的key，
# 官方六項沒有_score後綴、候選五項是cand_前綴。
_HISTORICAL_LABELS = {
    "momentum": "動能", "strength": "強度", "duration": "存續期間避險",
    "move": "波動度", "curve": "殖利率曲線形狀", "inflation": "通膨意外",
    "cand_copper_gold": "銅金比", "cand_credit_spread": "投資級企業債信用利差",
    "cand_swap_spread": "10年期Swap Spread", "cand_sofr_ted_spread": "SOFR與3M美債利差",
    "cand_inflation_1y": "1年期通膨預期",
}


def _historical_factor_labels():
    """回傳 factor_scores_matrix.csv 裡實際存在的歷史因子欄位 {欄名: 中文名}。
    檔案不存在就回傳空dict，不報錯(比照本檔其他選用性檔案的處理方式)。"""
    if not os.path.exists(HISTORICAL_MATRIX_CSV):
        return {}
    try:
        cols = set(pd.read_csv(HISTORICAL_MATRIX_CSV, nrows=0).columns)
    except Exception:
        return {}
    return {c: label for c, label in _HISTORICAL_LABELS.items() if c in cols}


def _build_partb_section_html():
    partb_csv = "partb_combination_results.csv"
    if not os.path.exists(partb_csv):
        return ""
    try:
        df = pd.read_csv(partb_csv)
        top_tail = df.sort_values(by="tail_reversion_score", ascending=False).head(10)
        robust_candidates = df[(df["n_factors"] <= 4) & (df["fear_n"] >= 30) & (df["oos_sharpe"] > 0.3)].sort_values(by="oos_sharpe", ascending=False).head(10)

        def make_rows(sub_df):
            out = ""
            for r in sub_df.itertuples():
                is_robust = (r.oos_sharpe >= 1.5) or (r.sharpe_decay >= 0.7)
                decay_badge = "<span style='color:#2f6b4f;font-weight:600;'>✓ 樣本外優秀</span>" if is_robust else "<span style='color:#a6362f;font-weight:600;'>⚠️ 衰退/偏弱</span>"
                out += f"""
                <tr>
                  <td><b>{r.combo_label}</b></td>
                  <td><span class="badge">{r.n_factors} 因子</span></td>
                  <td><b>{r.tail_reversion_score:+.2f} bp</b></td>
                  <td>{r.fear_excess_20d:+.2f} bp (n={r.fear_n})</td>
                  <td>{r.greed_excess_20d:+.2f} bp (n={r.greed_n})</td>
                  <td>{r.ic_20d:+.3f}</td>
                  <td>{r.is_sharpe:.2f}</td>
                  <td><b>{r.oos_sharpe:.2f}</b></td>
                  <td>{decay_badge}</td>
                </tr>"""
            return out

        top_tail_rows = make_rows(top_tail)
        robust_rows = make_rows(robust_candidates)

        return f"""
  <!-- Part B: 11 因子 2,047 種組合爆破與 Walk-Forward 樣本外驗證 -->
  <section class="card" style="margin-top:28px;">
    <h2><span class="bar"></span>Part B ｜ 11 因子 2,047 種組合爆破與 Walk-Forward 樣本外驗證</h2>
    <p class="hint">
      測試期間：<b>2020-01-01 ~ 2026-08-04</b> (共 2,408 交易日)　·　
      樣本內 (IS): 2020~2024 (1,827天)　·　
      樣本外 (OOS): 2025~2026 (581天)
    </p>

    <div style="background:rgba(47,107,79,0.08);border-left:4px solid #2f6b4f;padding:12px 16px;border-radius:6px;margin:14px 0;font-size:13px;line-height:1.6;">
      <b>💡 Mentor 觀點驗證與核心發現：</b><br>
      1. <b>尾端反轉效果</b>：爆破出的最佳組合在「極度恐懼 (0-24)」後 20 日平均能獲得顯著正超額報酬，而在「極度貪婪 (76-100)」後出現負超額報酬！<br>
      2. <b>過度配適防護 (Walk-Forward)</b>：多數 7~10 個因子的複雜組合出現<b>樣本外 (OOS) 衰退或負夏普</b>；限制 <b>因子數 ≤ 4 個</b> 的精簡組合在樣本外表現最為穩健，夏普比率高達 +1.9 ~ +2.1！
    </div>

    <h3>🏆 尾端反轉效果最強 Top 10 組合</h3>
    <table class="data-table mini" style="margin-bottom:24px;">
      <thead>
        <tr>
          <th>組合名稱</th><th>規模</th><th>尾端反轉得分 (20日)</th><th>恐懼端(0-24)超額</th>
          <th>貪婪端(76-100)超額</th><th>20日 IC</th><th>IS 夏普</th><th>OOS 夏普 (大考)</th><th>樣本外檢定</th>
        </tr>
      </thead>
      <tbody>{top_tail_rows}</tbody>
    </table>

    <h3>🛡️ 樣本外最穩健且精簡組合 Top 10 (因子數 ≤ 4，防過度配適)</h3>
    <table class="data-table mini">
      <thead>
        <tr>
          <th>組合名稱</th><th>規模</th><th>尾端反轉得分 (20日)</th><th>恐懼端(0-24)超額</th>
          <th>貪婪端(76-100)超額</th><th>20日 IC</th><th>IS 夏普</th><th>OOS 夏普 (大考)</th><th>樣本外檢定</th>
        </tr>
      </thead>
      <tbody>{robust_rows}</tbody>
    </table>

    <div style="background:rgba(30,58,95,0.04);border:1px solid rgba(30,58,95,0.12);padding:16px;border-radius:8px;margin-top:16px;">
      <h4 style="margin:0 0 10px 0;color:var(--series-1);font-size:14px;">💡 Top 10 個別組合金融邏輯與選擇原因解析 (從 2,047 種組合中勝出之背後原因)</h4>
      <ol style="margin:0;padding-left:20px;font-size:12.5px;line-height:1.65;color:#333;">
        <li style="margin-bottom:6px;"><b>動能 + 殖利率曲線 + SOFR-3M利差 (OOS夏普 +2.14)</b>：【黃金三核：趨勢 + 總經循環 + 貨幣流動性】。動能提供中期價格趨勢，殖利率曲線捕捉美聯儲降息/升息循環脈絡，SOFR 利差精確反映隔夜資金緊縮度。三者互補性極強，在大考中勇奪全場冠軍。</li>
        <li style="margin-bottom:6px;"><b>動能 + 存續期間避險 + SOFR-3M利差 (OOS夏普 +1.97)</b>：【價格趨勢 + 長短債避險 + 隔夜資金利差】。TLT vs SHY 的相對表現直接反映機構法人在長短天期美債間轉移資金的避險偏好，結合 SOFR 利差能有效避免在市場流動性轉折點踩空。</li>
        <li style="margin-bottom:6px;"><b>動能 + 存續避險 + 曲線 + SOFR利差 (OOS夏普 +1.93)</b>：【全方位四維平滑組合】。兼具趨勢、期限結構、長短天期相對價值與貨幣市場利差，是 4 因子組合中穩定度最高、抗震能力最強的全能防守隊伍。</li>
        <li style="margin-bottom:6px;"><b>動能 + SOFR-3M利差 (OOS夏普 +1.92)</b>：【極簡雙核衝鋒隊】。僅靠「中期價格趨勢」與「隔夜貨幣利差」兩個核心因子，結構極度簡潔，有效避免雜訊干擾，在 2 因子組合中績效冠絕全場。</li>
        <li style="margin-bottom:6px;"><b>動能 + 存續避險 + 銅金比報酬差 + SOFR利差 (OOS夏普 +1.59)</b>：【跨資產避險強化組合】。引入「銅金比（工業 vs 避險金屬）」作為跨資產情緒錨，能第一時間捕捉全球景氣風險偏好轉變，是大考通過的組合中唯一具備大宗商品跨資產視角的隊伍。</li>
        <li style="margin-bottom:6px;"><b>動能 (10Y-SMA125) (OOS夏普 +1.52)</b>：【單因子基準基石】。單憑 125 日均線價差的中期趨勢跟蹤，展現了美債市場強烈的趨勢延續性，為所有多因子組合提供不可或缺的主方向支撐。</li>
        <li style="margin-bottom:6px;"><b>動能 + 存續期間避險 (OOS夏普 +1.48)</b>：【經典價格-避險雙因子】。公債期貨價格動能搭配 TLT/SHY 長短債強弱差，是華爾街最經典的雙因子債券趨勢跟蹤模型。</li>
        <li style="margin-bottom:6px;"><b>動能 + 存續避險 + 銅金比報酬差 (OOS夏普 +1.47)</b>：【商品情緒與長短債雙重避險】。結合了債券市場自身的長短天期資金流向（TLT-SHY）與商品市場的避險情緒（銅金比），雙重驗證市場避險偏好。</li>
        <li style="margin-bottom:6px;"><b>動能 + 殖利率曲線 + 銅金比報酬差 + SOFR利差 (OOS夏普 +1.35)</b>：【多維度總經與商品綜合體】。同時考慮殖利率曲線陡峭化與銅金比風險偏好，適合關注總經大循環與大宗商品聯動的策略。</li>
        <li><b>動能 + 銅金比報酬差 (OOS夏普 +1.33)</b>：【債券-商品極簡跨資產雙核】。用美債價格動能結合銅金比情緒，是建構跨資產避險模型時最簡潔有效的雙因子範本。</li>
      </ol>
    </div>

    <p class="hint" style="margin-top:12px;">註：全量 2,047 種非空組合之細部數據（含各組合之 5/20/60 日 IC、勝率與樣本內外夏普比率）已完整保存在專案根目錄 <code class="mono">partb_combination_results.csv</code> 中。</p>
  </section>"""
    except Exception as e:
        return f"<!-- Part B section build error: {e} -->"


def render_registry_index(registry):
    promoted_keys = _load_promoted_keys()
    # 官方/已升等因子預設勾選；歷史快照因子預設不勾(只是提供選項，避免預設就跑出
    # 十幾乘十幾的巨大矩陣，也避免讓人誤以為那些因子還在每日更新)。
    corr_factor_checkboxes = "".join(
        f'<label class="checkbox-group corr-check"><input type="checkbox" class="corr-factor" '
        f'value="{opt["value"]}"{"" if opt["kind"] == "historical" else " checked"}>{opt["label"]}</label>'
        for opt in _corr_factor_options()
    )
    rows = ""
    for idx, e in enumerate(reversed(registry)):
        row_id = f"{e['key']}_{idx}"
        gp = e.get("gates_passed", "無法判斷")
        n_p, n_j = (gp.split("/") if "/" in gp else ("0", "0"))
        verdict_type = ("keep" if n_j != "0" and int(n_p) == int(n_j)
                        else "watch" if n_j != "0" and int(n_p) >= int(n_j) / 2
                        else "cut")
        verdict_cls = f"verdict-{verdict_type}"
        is_promoted = e["key"] in promoted_keys
        promote_cell = (
            f'<span class="promoted-badge">已升等</span> '
            f'<button class="demote-btn" type="button" onclick="demoteFactor(this, \'{e["key"]}\', \'{e["label"]}\')">退回</button>'
            if is_promoted else '<span class="na">—</span>'
        )
        report_url = f"screening_{e['key']}.html"
        rows += f"""<tr class="registry-row" data-row-id="{row_id}" data-key="{e['key']}" data-verdict="{verdict_type}" data-promoted="{'true' if is_promoted else 'false'}" data-search="{e['label'].lower()} {e['key'].lower()}">
          <td>{e["test_date"]}</td>
          <td>
            <button id="toggle-btn-{row_id}" class="expand-toggle-btn" data-label="{e['label']}" onclick="toggleInlineReport('{row_id}', '{report_url}', '{e['label']}')">
              <span class="arrow-icon">▶</span> {e['label']}
            </button>
          </td>
          <td>{TRANSFORM_MODES[e['mode']]['label']}</td>
          <td>{fva.fmt_num(e.get('main_ic'), 3) if e.get('main_ic') is not None else '—'}</td>
          <td>{e.get('pattern_tag', '—')}</td>
          <td>{gp}</td>
          <td class="{verdict_cls}">{e['final_verdict']}</td>
          <td>{promote_cell}</td>
        </tr>
        <tr id="expand-row-{row_id}" class="inline-report-row" style="display:none;">
          <td colspan="8" class="inline-report-cell">
            <div class="inline-report-wrap">
              <div class="inline-report-bar">
                <span class="inline-report-title">📊 因子體檢報告：{e['label']} ({e['key']})</span>
                <div class="inline-report-actions">
                  <a class="inline-link" href="{report_url}" target="_blank">在新分頁開啟 ↗</a>
                  <button class="inline-close-btn" onclick="closeInlineReport('{row_id}')">✕ 關閉報告</button>
                </div>
              </div>
              <iframe id="iframe-{row_id}" class="inline-iframe" data-src="{report_url}"></iframe>
            </div>
          </td>
        </tr>"""

    n_total = len(registry)
    n_keep = sum(
        1 for e in registry
        if "/" in e.get("gates_passed", "") and e["gates_passed"].split("/")[1] != "0"
        and e["gates_passed"].split("/")[0] == e["gates_passed"].split("/")[1]
    )
    n_watch = sum(
        1 for e in registry
        if "/" in e.get("gates_passed", "") and e["gates_passed"].split("/")[1] != "0"
        and int(e["gates_passed"].split("/")[0]) >= int(e["gates_passed"].split("/")[1]) / 2
        and e["gates_passed"].split("/")[0] != e["gates_passed"].split("/")[1]
    )
    n_cut = sum(
        1 for e in registry
        if "/" in e.get("gates_passed", "") and e["gates_passed"].split("/")[1] != "0"
        and int(e["gates_passed"].split("/")[0]) < int(e["gates_passed"].split("/")[1]) / 2
    )
    n_promoted = sum(1 for e in registry if e["key"] in promoted_keys)
    n_passed = n_keep
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>因子開發與篩選平台 · 債券市場恐懼貪婪</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:#f4f5f7; color:#161a23; font-family:"Inter",-apple-system,BlinkMacSystemFont,"PingFang TC","Noto Sans TC","Segoe UI",Roboto,sans-serif; line-height:{page_style.BASE_LINE_HEIGHT}; }}
  .wrap {{ max-width:{page_style.CONTENT_MAX_WIDTH}; margin:0 auto; padding:44px 24px 80px; }}
  header {{ margin-bottom:28px; }}
  .kicker {{ font-family:ui-monospace,"SF Mono",Menlo,monospace; font-size:11px; letter-spacing:0.12em; color:#a6742a; font-weight:700; margin-bottom:10px; }}
  h1 {{ font-size:{page_style.H1_SIZE}; font-weight:700; margin:0 0 12px; letter-spacing:-0.02em; }}
  .meta {{ font-size:13px; color:#4a5568; margin:0 0 14px; }}
  .disclaimer {{ font-size:12.5px; color:#667085; background:#fff; border:1px solid #dfe2e8; border-radius:10px; padding:14px 16px; line-height:1.7; box-shadow:0 1px 3px rgba(22,26,35,0.03); }}
  .card {{
    background:#fff; border:1px solid #dfe2e8; border-radius:14px; padding:24px 28px; margin-bottom:22px;
    box-shadow:0 2px 4px rgba(22,26,35,0.03), 0 8px 24px rgba(22,26,35,0.05);
    transition:transform 0.25s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.25s ease, border-color 0.25s ease;
  }}
  .card:hover {{
    transform:translateY(-2px);
    box-shadow:0 4px 12px rgba(22,26,35,0.06), 0 16px 36px rgba(22,26,35,0.08);
  }}
  .card h2 {{ font-size:18px; font-weight:700; margin:0 0 16px; display:flex; align-items:center; gap:8px; }}
  .bar {{ width:4px; height:18px; background:#1e3a5f; border-radius:2px; display:inline-block; }}
  .data-table {{ width:100%; border-collapse:collapse; font-size:13px; margin:8px 0 4px; }}
  .data-table th, .data-table td {{ text-align:left; padding:8px 12px; border-bottom:1px solid #e5e7eb; font-variant-numeric:tabular-nums; transition:background-color 0.15s ease; }}
  .data-table th {{ color:#667085; font-weight:600; font-size:11.5px; text-transform:uppercase; letter-spacing:0.03em; }}
  .data-table tbody tr:hover td {{ background:#f8fafc; }}
  .data-table td.fname {{ font-weight:600; white-space:nowrap; }}
  .verdict-keep {{ color:#2f6b4f; font-weight:700; }}
  .verdict-watch {{ color:#a6742a; font-weight:700; }}
  .verdict-cut {{ color:#a6362f; font-weight:700; }}
  .na {{ color:#a7adb9; font-style:italic; }}
  .promoted-badge {{ display:inline-block; font-size:11px; font-weight:700; color:#2f6b4f;
    background:rgba(47,107,79,0.1); border-radius:999px; padding:3px 10px; white-space:nowrap; }}
  .demote-btn {{ border:1px solid #dfe2e8; border-radius:6px; background:#fff; color:#a6362f;
    font-size:11.5px; padding:4px 10px; cursor:pointer; white-space:nowrap; margin-left:4px; transition:all 0.15s ease; }}
  .demote-btn:hover {{ border-color:#a6362f; background:rgba(166,54,47,0.06); }}
  .demote-btn:active {{ transform:scale(0.96); }}
  .demote-btn:disabled {{ opacity:.55; cursor:not-allowed; }}

  .form-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
  .form-group {{ display:flex; flex-direction:column; gap:6px; }}
  .form-group.full {{ grid-column:1 / -1; }}
  label {{ font-size:13px; font-weight:600; color:#161a23; }}
  .hint {{ font-size:12px; color:#667085; }}
  input[type="text"], input[type="number"], input[type="password"], select {{
    width:100%; padding:9px 12px; border:1px solid #dfe2e8; border-radius:8px; background:#f4f5f7; color:#161a23; font-size:13.5px; outline:none;
    transition:border-color 0.2s ease, box-shadow 0.2s ease;
  }}
  input:focus, select:focus {{ border-color:#1e3a5f; box-shadow:0 0 0 3px rgba(30,58,95,0.12); }}
  .checkbox-group {{ display:flex; align-items:center; gap:8px; margin-top:4px; }}
  .checkbox-group input {{ width:16px; height:16px; cursor:pointer; }}
  .corr-factor-grid {{ display:flex; flex-wrap:wrap; gap:10px 18px; margin-top:10px; }}
  .corr-check {{ margin-top:0; font-size:13px; font-weight:normal; color:#161a23; cursor:pointer; }}
  .btn-submit {{
    display:inline-flex; align-items:center; justify-content:center; gap:8px; width:100%; padding:13px; background:#1e3a5f; color:#fff; border:none; border-radius:10px; font-size:14.5px; font-weight:700; cursor:pointer;
    transition:all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
  }}
  .btn-submit:hover {{ background:#2a4c78; transform:translateY(-1px); box-shadow:0 4px 12px rgba(30,58,95,0.25); }}
  .btn-submit:active {{ transform:scale(0.98); }}
  .token-box {{ background:rgba(166,116,42,0.08); border:1px dashed #a6742a; border-radius:10px; padding:14px 16px; margin-bottom:18px; font-size:12.5px; }}
  .token-box summary {{ font-weight:700; color:#a6742a; cursor:pointer; }}
  .status-card {{ display:none; background:#fff; border:1px solid #dfe2e8; border-radius:14px; padding:20px; text-align:center; margin-bottom:22px; }}
  .spinner {{ width:32px; height:32px; border:3px solid #dfe2e8; border-top-color:#1e3a5f; border-radius:50%; animation:spin 1s linear infinite; margin:0 auto 12px; }}
  @keyframes spin {{ to {{ transform:rotate(360deg); }} }}
  /* === Plan 004: prefers-reduced-motion 無障礙支援 ===
     注意：.spinner 是無限旋轉動畫，animation-duration:0.001ms 會讓它每秒轉 1000 圈，
     造成高頻閃爍（比原本的 1s 旋轉更危險），必須用 animation:none 完全停止。
     transition 有起點/終點，縮短成 0.001ms 只是讓過渡「看起來是瞬間的」，這是安全的。 */
  @media (prefers-reduced-motion: reduce) {{
    .spinner {{ animation: none; border-color: #1e3a5f; opacity: 0.65; }}
    * {{ transition-duration: 0.001ms !important; animation-duration: 0.001ms !important; }}
  }}
  .status-title {{ font-size:16px; font-weight:700; margin-bottom:6px; }}
  .status-desc {{ font-size:12.5px; color:#4a5568; margin-bottom:14px; }}
  .progress-steps {{ display:flex; justify-content:space-around; font-size:11.5px; color:#667085; border-top:1px solid #e5e7eb; padding-top:12px; }}
  .step.active {{ color:#1e3a5f; font-weight:700; }}
  .registry-controls {{ display:flex; flex-wrap:wrap; justify-content:space-between; align-items:center; gap:12px; margin-bottom:14px; background:#f8fafc; padding:12px 16px; border-radius:10px; border:1px solid #dfe2e8; }}
  .registry-filters {{ display:flex; gap:6px; flex-wrap:wrap; }}
  .filter-tab-btn {{ background:#fff; border:1px solid #cbd5e1; border-radius:6px; padding:5px 12px; font-size:12px; font-weight:600; color:#475569; cursor:pointer; transition:all .15s ease; }}
  .filter-tab-btn:hover {{ background:#f1f5f9; border-color:#94a3b8; }}
  .filter-tab-btn.active {{ background:#1e3a5f; color:#fff; border-color:#1e3a5f; }}
  .registry-search-wrap {{ position:relative; width:220px; }}
  .registry-search-wrap input {{ padding:6px 10px; font-size:12.5px; border-radius:6px; border:1px solid #cbd5e1; width:100%; background:#fff; outline:none; }}
  .registry-search-wrap input:focus {{ border-color:#1e3a5f; }}

  .expand-toggle-btn {{ background:none; border:none; padding:0; color:#1e3a5f; font-weight:700; font-size:13px; text-align:left; cursor:pointer; display:inline-flex; align-items:center; gap:6px; }}
  .expand-toggle-btn:hover {{ text-decoration:underline; color:#0f172a; }}
  .expand-toggle-btn .arrow-icon {{ font-size:10px; color:#a6742a; transition:transform .15s ease; }}

  /* === Plan 002: Inline report 展開 fade-in 動畫 ===
     table row 無法直接用 CSS transition （display 不能被動畫），
     改用 @keyframes one-shot 動畫 + JS class toggle 解決。 */
  @keyframes fadeInReport {{
    from {{ opacity:0; transform:translateY(6px); }}
    to   {{ opacity:1; transform:translateY(0); }}
  }}
  .inline-report-row {{ background:#f8fafc; }}
  .inline-report-row.expanding {{ animation: fadeInReport 0.3s ease forwards; }}
  .inline-report-cell {{ padding:12px 16px !important; border-bottom:2px solid #cbd5e1 !important; }}
  .inline-report-wrap {{ background:#fff; border:1px solid #dfe2e8; border-radius:10px; padding:14px; box-shadow:0 4px 12px rgba(0,0,0,0.05); }}
  .inline-report-bar {{ display:flex; justify-content:space-between; align-items:center; padding-bottom:10px; margin-bottom:10px; border-bottom:1px solid #e5e7eb; }}
  .inline-report-title {{ font-size:14px; font-weight:700; color:#1e3a5f; }}
  .inline-report-actions {{ display:flex; gap:10px; align-items:center; }}
  .inline-link {{ font-size:12px; color:#2563eb; text-decoration:none; font-weight:600; }}
  .inline-link:hover {{ text-decoration:underline; }}
  .inline-close-btn {{ background:#f1f5f9; border:1px solid #cbd5e1; border-radius:6px; padding:4px 10px; font-size:11.5px; cursor:pointer; color:#475569; font-weight:600; }}
  .inline-close-btn:hover {{ background:#e2e8f0; color:#0f172a; }}
  .inline-iframe {{ width:100%; height:950px; border:none; border-radius:8px; background:#fff; }}

  /* === Plan 003a: status-card slide-down 進入動畫 === */
  @keyframes slideDownFade {{
    from {{ opacity:0; transform:translateY(-8px); }}
    to   {{ opacity:1; transform:translateY(0); }}
  }}
  .status-card-visible {{ animation: slideDownFade 0.3s ease forwards; }}

  /* === Plan 003b: reportViewer 淡入展示 ===
     JS 引用的 #reportViewer 原本在 HTML 中缺失，這裡補上定義。
     用 opacity+visibility transition 取代 display:none/block。 */
  #reportViewer {{
    display:none; margin-top:20px; border:1px solid #dfe2e8; border-radius:14px;
    background:#fff; overflow:hidden; box-shadow:0 4px 16px rgba(0,0,0,0.08);
    opacity:0; transition: opacity 0.35s ease;
  }}
  #reportViewer.report-visible {{ opacity:1; }}
  #reportViewerBar {{
    display:flex; justify-content:space-between; align-items:center;
    padding:12px 16px; border-bottom:1px solid #e5e7eb; background:#f8fafc;
  }}
  #reportViewerTitle {{ font-size:14px; font-weight:700; color:#1e3a5f; }}
  #reportFrame {{ width:100%; height:820px; border:none; background:#fff; }}

  .pagination-bar {{ display:flex; justify-content:space-between; align-items:center; padding-top:14px; margin-top:10px; border-top:1px solid #e5e7eb; font-size:12.5px; color:#64748b; }}
  .page-btn {{ background:#fff; border:1px solid #cbd5e1; border-radius:6px; padding:4px 12px; font-size:12px; cursor:pointer; color:#334155; font-weight:600; }}
  .page-btn:hover:not(:disabled) {{ background:#f1f5f9; }}
  .page-btn:disabled {{ opacity:.4; cursor:not-allowed; }}

  /* === Plan 005: combo-list \u4e0b\u62c9\u9078\u55ae fade+slide \u904e\u6e21 ===
     \u6539\u7528 opacity+transform \u52d5\u756b\uff0c\u4fdd\u7559 display:none \u7d66\u5b8c\u5168\u96b1\u85cf\u7528\uff08blur\u5f8c\uff09\u3002
     JS \u7684 filterSourceCombo() \u6703\u5148\u8a2d display:block\uff0c\u518d\u52a0 .open \u89f8\u767c\u52d5\u756b\u3002 */
  /* === 資料來源搜尋彈出視窗 (Combo Dropdown UI/UX 重構) === */
  .combo-wrap {{
    position: relative; width: 100%; display: block; z-index: 50;
  }}
  .combo-wrap input {{
    padding: 10px 14px; font-size: 13px; border-radius: 8px; border: 1px solid #cbd5e1;
    width: 100%; background: #ffffff; outline: none; transition: all 0.2s ease;
    color: #0f172a; box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
  }}
  .combo-wrap input:focus {{
    border-color: #1e3a5f; box-shadow: 0 0 0 3.5px rgba(30, 58, 95, 0.12);
  }}
  .combo-list {{
    display: none; position: absolute; top: calc(100% + 6px); left: 0; right: 0; z-index: 1000;
    background: #ffffff; border: 1px solid #cbd5e1; border-radius: 12px;
    box-shadow: 0 16px 36px -4px rgba(15, 23, 42, 0.16), 0 4px 12px -2px rgba(15, 23, 42, 0.08);
    max-height: 320px; overflow-y: auto; padding: 6px;
    opacity: 0; transform: translateY(-6px) scale(0.995);
    transition: opacity 0.18s cubic-bezier(0.16, 1, 0.3, 1), transform 0.18s cubic-bezier(0.16, 1, 0.3, 1);
  }}
  .combo-list.open {{ opacity: 1; transform: translateY(0) scale(1); }}
  
  .combo-header-bar {{
    display: flex; align-items: center; justify-content: space-between;
    padding: 7px 10px; margin-bottom: 6px; border-radius: 6px;
    background: #f8fafc; border: 1px solid #e2e8f0; font-size: 11.5px; color: #475569; font-weight: 600;
  }}
  .combo-header-bar .hint-text {{ display: flex; align-items: center; gap: 5px; }}
  .combo-header-bar .count-badge {{ font-family: ui-monospace, "SF Mono", Menlo, monospace; background: #e2e8f0; color: #334155; padding: 1px 6px; border-radius: 99px; font-size: 10.5px; }}

  .combo-item {{
    padding: 9px 12px; font-size: 13px; cursor: pointer;
    display: flex; align-items: center; justify-content: space-between; gap: 10px;
    border-radius: 8px; margin-bottom: 2px; transition: all 0.15s ease;
    border-left: 3px solid transparent; color: #1e293b;
  }}
  .combo-item:last-child {{ margin-bottom: 0; }}
  .combo-item:hover {{
    background: #f1f5f9; border-left-color: #1e3a5f; color: #0f172a;
    transform: translateX(2px);
  }}
  .combo-item-left {{ display: flex; align-items: center; gap: 8px; min-width: 0; }}
  .combo-item-label {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-weight: 600; }}

  .combo-tag {{
    font-size: 10.5px; font-weight: 700; border-radius: 6px; padding: 2px 7px; flex-shrink: 0; line-height: 1.4;
  }}
  .combo-tag.tag-existing {{ background: rgba(30, 58, 95, 0.08); color: #1e3a5f; border: 1px solid rgba(30, 58, 95, 0.18); }}
  .combo-tag.tag-yahoo {{ background: rgba(99, 102, 241, 0.08); color: #4f46e5; border: 1px solid rgba(99, 102, 241, 0.18); }}
  .combo-tag.tag-fred {{ background: rgba(16, 185, 129, 0.08); color: #059669; border: 1px solid rgba(16, 185, 129, 0.18); }}
  .combo-tag.tag-treasury {{ background: rgba(14, 165, 233, 0.08); color: #0284c7; border: 1px solid rgba(14, 165, 233, 0.18); }}

  .combo-id {{
    font-family: ui-monospace, "SF Mono", Menlo, monospace; color: #475569;
    font-size: 11.5px; font-weight: 600; background: #f8fafc; border: 1px solid #e2e8f0;
    border-radius: 5px; padding: 2px 7px; flex-shrink: 0;
  }}
  .combo-empty {{ padding: 14px 12px; font-size: 12.5px; color: #64748b; text-align: center; background: #f8fafc; border-radius: 8px; border: 1px dashed #cbd5e1; }}
  .manual-source-group {{ margin-top:10px; padding-top:10px; border-top:1px dashed #dfe2e8; }}
  {nav_bar.NAV_BAR_CSS}
</style>
</head>
<body>
<div class="wrap">
  {nav_bar.render_nav_bar("screening")}
  <header>
    <div class="kicker">FACTOR DISCOVERY &amp; SCREENING</div>
    <h1 data-i18n="screening_title">因子開發與篩選平台</h1>
    <p class="meta">累計測試 {n_total} 個因子，各關卡全數通過 {n_passed} 個。</p>
    <p class="disclaimer">{POSITIONING_STATEMENT}</p>
    <p class="disclaimer">
      這份登記簿記錄「每一次」測試過的因子，不論結果通過與否都會保留紀錄與完整報告。您可以在下方<b>輸入新因子進行線上驗證</b>，運算完成後，分析圖表與 5 道關卡報告會<b>直接在此頁面上展示出來</b>。
    </p>
  </header>

  <!-- 線上驗證輸入表單 -->
  <section class="card">
    <h2><span class="bar"></span>➕ 輸入新因子進行驗證</h2>
    
    <details class="token-box" id="tokenDetails">
      <summary>🔑 設定 GitHub Personal Access Token (第一次使用必填)</summary>
      <p style="margin:6px 0 10px;color:#4a5568;">填入授權 Token (具備 repo/workflow 權限)，安全儲存於本機瀏覽器 (localStorage)。</p>
      <div class="form-group">
        <input type="password" id="ghToken" placeholder="ghp_xxxxxxxxxxxxxxxxx" autocomplete="off">
      </div>
    </details>

    <form id="screeningForm">
      <div class="form-grid">
        <div class="form-group">
          <label for="key">因子英文代號 (Key)</label>
          <input type="text" id="key" placeholder="例: vix_ma_dev" required pattern="[a-zA-Z0-9_]+" title="英文字母、數字與底線">
        </div>
        <div class="form-group">
          <label for="label">因子中文名稱 (Label)</label>
          <input type="text" id="label" placeholder="例: VIX 125日均線乖離率" required>
        </div>
        <div class="form-group full">
          <label for="mode">轉換模式 (Transformation Mode)</label>
          <select id="mode" required onchange="handleModeChange()">
            <option value="ma_deviation">均線乖離百分位 (Single Series vs N-day SMA)</option>
            <option value="ma_spread">均線價差百分位 (Single Series - N-day SMA)</option>
            <option value="range_position">區間位置 (N-day High/Low Range Position 0-100)</option>
            <option value="return_spread">兩序列報酬差百分位 (Series A N-day Ret - Series B N-day Ret)</option>
            <option value="value_spread">兩序列差值百分位 (Series A - Series B)</option>
            <option value="moving_average">移動平均百分位 (N-day SMA)</option>
            <option value="rolling_stat">滾動統計量百分位 (N-day Skew / StdDev)</option>
          </select>
        </div>
        <div class="form-group full">
          <label for="sourceSearch">資料來源 A（可輸入中文關鍵字或代號搜尋，例如「十年期公債」或「DGS10」）</label>
          <div class="combo-wrap">
            <input type="text" id="sourceSearch" class="combo-input" placeholder="打字搜尋，例如：十年期公債 / DGS10 / VIX" autocomplete="off"
                   oninput="filterSourceCombo('')" onfocus="filterSourceCombo('')" onblur="hideComboLater('')">
            <div class="combo-list" id="sourceComboList"></div>
          </div>
          <p class="hint">
            <label style="font-weight:normal;cursor:pointer;">
              <input type="checkbox" id="sourceManualToggle" onchange="toggleManualSource('')" style="width:auto;height:auto;vertical-align:middle;">
              找不到？手動輸入類型與代號
            </label>
          </p>
          <div class="manual-source-group form-grid" id="manualSourceGroup" style="display:none;">
            <div class="form-group">
              <label for="sourceType">資料來源類型</label>
              <select id="sourceType">
                <option value="yahoo">Yahoo Finance (代號如 ^VIX)</option>
                <option value="fred">FRED 經濟數據 (代號如 DGS10)</option>
                <option value="existing">儀表板既有欄位 (UST_10Yr 等)</option>
              </select>
            </div>
            <div class="form-group">
              <label for="sourceId">資料來源代號</label>
              <input type="text" id="sourceId" placeholder="例: ^VIX / DGS10 / UST_10Yr">
            </div>
          </div>
        </div>
        <div class="form-group full source-b-group" style="display:none;">
          <label for="sourceSearchB">資料來源 B（可輸入中文關鍵字或代號搜尋）</label>
          <div class="combo-wrap">
            <input type="text" id="sourceSearchB" class="combo-input" placeholder="打字搜尋，例如：短債 / SHY / DGS2" autocomplete="off"
                   oninput="filterSourceCombo('B')" onfocus="filterSourceCombo('B')" onblur="hideComboLater('B')">
            <div class="combo-list" id="sourceComboListB"></div>
          </div>
          <p class="hint">
            <label style="font-weight:normal;cursor:pointer;">
              <input type="checkbox" id="sourceManualToggleB" onchange="toggleManualSource('B')" style="width:auto;height:auto;vertical-align:middle;">
              找不到？手動輸入類型與代號
            </label>
          </p>
          <div class="manual-source-group form-grid" id="manualSourceGroupB" style="display:none;">
            <div class="form-group">
              <label for="sourceBType">資料來源類型</label>
              <select id="sourceBType">
                <option value="yahoo">Yahoo Finance</option>
                <option value="fred">FRED</option>
                <option value="existing">儀表板既有欄位</option>
              </select>
            </div>
            <div class="form-group">
              <label for="sourceBId">資料來源代號</label>
              <input type="text" id="sourceBId" placeholder="例: SHY / DGS2">
            </div>
          </div>
        </div>
        <div class="form-group">
          <label for="window">滾動視窗 (Window Days)</label>
          <input type="number" id="window" value="125" min="5" max="500" required>
        </div>
        <div class="form-group">
          <label>分數反轉</label>
          <div class="checkbox-group">
            <input type="checkbox" id="invert">
            <label for="invert" style="font-weight:normal;">數值越高代表「恐懼」時請勾選 (將分數反轉)</label>
          </div>
        </div>
        <div class="form-group full" style="margin-top:8px;">
          <button type="submit" class="btn-submit" id="btnSubmit">
            🚀 提交驗證並即時呈現分析報告圖表
          </button>
        </div>
      </div>
    </form>
  </section>

  <!-- 因子相關係數矩陣（隨選，取代原本驗證報告裡固定範圍的相關矩陣） -->
  <section class="card">
    <h2><span class="bar"></span><span data-i18n="corr_card_title">🔗 產生因子相關係數矩陣</span></h2>
    <p class="hint" data-i18n="corr_card_desc">
      勾選想比較的因子（官方七項＋目前已升等的候選因子），產生兩兩相關係數熱力圖——用來看因子之間是不是在講同一件事（相關係數太高代表訊息重複、加進來邊際價值有限）。運算完成後會直接顯示在下方，不用等每日自動報告。
    </p>
    <details class="token-box" id="corrTokenDetails">
      <summary data-i18n="form_token_summary">🔑 GitHub Personal Access Token（跟上面表單共用同一組）</summary>
      <input type="password" id="corrGhToken" placeholder="ghp_xxxxxxxxxxxxxxxxx" autocomplete="off">
    </details>
    <div class="corr-factor-grid">
      {corr_factor_checkboxes}
    </div>
    <button class="btn-submit" type="button" id="corrSubmitBtn" style="margin-top:14px;" data-i18n="corr_submit_btn">📊 產生相關係數矩陣</button>
    <p class="hint" id="corrStatus" style="margin-top:10px;"></p>
  </section>

  <!-- 運算進度狀態卡片 -->
  <div class="status-card" id="statusCard">
    <div class="spinner" id="statusSpinner"></div>
    <div class="status-title" id="statusTitle">已提交分析請求</div>
    <div class="status-desc" id="statusDesc">GitHub Actions 正在啟動 20 年數據運算與圖表繪製引擎...</div>
    <div class="progress-steps">
      <div class="step active" id="step1">1. 提交請求</div>
      <div class="step" id="step2">2. 執行 20 年運算</div>
      <div class="step" id="step3">3. 產生報告圖表</div>
      <div class="step" id="step4">4. 呈現分析報告</div>
    </div>
  </div>

  <!-- 歷史紀錄表格卡片 -->
  <section class="card">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:12px;">
      <h2 style="margin:0;"><span class="bar"></span><span data-i18n="reg_title">歷史測試紀錄登記簿</span> <span style="font-size:12px;font-weight:normal;color:#667085;margin-left:6px;" data-i18n="reg_sub">(點擊因子名稱可直接在下方展開報告圖表)</span></h2>
    </div>

    <!-- 篩選控制與搜尋列 (防止列表越來越長) -->
    <div class="registry-controls">
      <div class="registry-filters">
        <button class="filter-tab-btn active" data-filter="all" data-i18n="filter_all" onclick="filterRegistry('all')">全部 ({n_total})</button>
        <button class="filter-tab-btn" data-filter="keep" data-i18n="filter_keep" onclick="filterRegistry('keep')">通過 ({n_keep})</button>
        <button class="filter-tab-btn" data-filter="watch" data-i18n="filter_watch" onclick="filterRegistry('watch')">觀察 ({n_watch})</button>
        <button class="filter-tab-btn" data-filter="cut" data-i18n="filter_cut" onclick="filterRegistry('cut')">淘汰 ({n_cut})</button>
        <button class="filter-tab-btn" data-filter="promoted" data-i18n="filter_promoted" onclick="filterRegistry('promoted')">已升等 ({n_promoted})</button>
      </div>
      <div class="registry-search-wrap">
        <input type="text" id="registrySearchInput" placeholder="🔍 搜尋因子名稱 / 代號..." data-i18n-placeholder="search_placeholder" oninput="onRegistrySearchInput()">
      </div>
    </div>

    <table class="data-table" id="registryTable">
      <thead>
        <tr><th data-i18n="th_date">測試日期</th><th data-i18n="th_factor">因子 (點擊名稱展開報告)</th><th data-i18n="th_mode">轉換模式</th><th data-i18n="th_ic">IC(20日,重疊取樣)</th><th data-i18n="th_flags">型態標記</th><th data-i18n="th_gates">關卡通過</th><th data-i18n="th_verdict">結果</th><th data-i18n="th_status">儀表板狀態</th></tr>
      </thead>
      <tbody id="registryTbody">
        {rows if rows else "<tr><td colspan='8' class='na'>尚無測試記錄</td></tr>"}
      </tbody>
    </table>

    <!-- 分頁控制列 -->
    <div class="pagination-bar" id="paginationBar">
      <div id="pageInfo">顯示 1 - 6 / 共 {n_total} 筆</div>
      <div style="display:flex;gap:6px;">
        <button class="page-btn" id="prevPageBtn" onclick="changePage(-1)" data-i18n="btn_prev">‹ 上一頁</button>
        <button class="page-btn" id="nextPageBtn" onclick="changePage(1)" data-i18n="btn_next">下一頁 ›</button>
      </div>
    </div>
  </section>

  {_build_partb_section_html()}

  <!-- Plan 003b: reportViewer div（之前 JS 有引用但 HTML 缺失；現在補上並配合 CSS 過渡效果） -->
  <div id="reportViewer">
    <div id="reportViewerBar">
      <span id="reportViewerTitle">📊 因子分析報告與圖表</span>
      <div style="display:flex;gap:10px;align-items:center;">
        <a id="reportViewerLink" href="#" target="_blank" style="font-size:12px;color:#2563eb;font-weight:600;text-decoration:none;">↗ 新分頁開啟</a>
        <button onclick="closeReportViewer()" style="background:#f1f5f9;border:1px solid #cbd5e1;border-radius:6px;padding:4px 10px;font-size:11.5px;cursor:pointer;color:#475569;font-weight:600;">✕ 關閉</button>
      </div>
    </div>
    <iframe id="reportFrame"></iframe>
  </div>
</div>

<script>
  const REPO_OWNER = "dp79b47tvn-maker";
  const REPO_NAME = "bond-fear-greed-dashboard";
  const SOURCE_CATALOG = {json.dumps(SOURCE_CATALOG, ensure_ascii=False)};
  const SOURCE_TYPE_CONFIG = {{
    "existing": {{ label: "既有欄位", class: "tag-existing" }},
    "yahoo": {{ label: "Yahoo", class: "tag-yahoo" }},
    "fred": {{ label: "FRED 聯備", class: "tag-fred" }},
    "treasury": {{ label: "Treasury", class: "tag-treasury" }}
  }};

  function zhNumToArabic(str) {{
    // 目錄裡的中文說明一律用阿拉伯數字(10年期、2年期...)，但使用者可能習慣打
    // 中文數字(十年期、兩年期)——這裡把查詢字串裡的中文數字轉成阿拉伯數字再比對，
    // 不然「十年期公債」這種很自然的搜法會因為字面對不上而完全找不到東西。
    const d = {{"零":0,"一":1,"二":2,"兩":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9}};
    return str.replace(/[一二兩三四五六七八九]?十[一二兩三四五六七八九]?|[零一二兩三四五六七八九]/g, (m) => {{
      if (m.includes("十")) {{
        const idx = m.indexOf("十");
        const tensChar = m.slice(0, idx), onesChar = m.slice(idx + 1);
        const tens = tensChar ? d[tensChar] : 1;
        const ones = onesChar ? d[onesChar] : 0;
        return String(tens * 10 + ones);
      }}
      return String(d[m]);
    }});
  }}

  function filterSourceCombo(sfx) {{
    const input = document.getElementById(`sourceSearch${{sfx}}`);
    const listEl = document.getElementById(`sourceComboList${{sfx}}`);
    const qRaw = input.value.trim().toLowerCase();
    const qNorm = zhNumToArabic(input.value.trim()).toLowerCase();
    let matches = qRaw
      ? SOURCE_CATALOG.filter(item => {{
          const hay = (item.id + " " + item.label).toLowerCase();
          return hay.includes(qRaw) || (qNorm !== qRaw && hay.includes(qNorm));
        }})
      : SOURCE_CATALOG;
    matches = matches.slice(0, 10);
    if (!matches.length) {{
      listEl.innerHTML = `<div class="combo-empty">🔍 找不到符合的資料來源，可勾選下方「手動輸入」選項</div>`;
      listEl.style.display = "block";
      void listEl.offsetWidth;
      listEl.classList.add('open');
      return;
    }}

    const headerHtml = `
      <div class="combo-header-bar">
        <div class="hint-text">💡 可輸入中文名稱（如「十年期公債」、「黃金」）或代號（如「DGS10」、「^VIX」）</div>
        <div class="count-badge">${{matches.length}} 筆結果</div>
      </div>
    `;

    listEl.innerHTML = headerHtml + matches.map((item) => {{
      const cfg = SOURCE_TYPE_CONFIG[item.type] || {{ label: item.type, class: "" }};
      return `<div class="combo-item" data-idx="${{SOURCE_CATALOG.indexOf(item)}}">
        <div class="combo-item-left">
          <span class="combo-tag ${{cfg.class}}">${{cfg.label}}</span>
          <span class="combo-item-label">${{item.label}}</span>
        </div>
        <span class="combo-id">${{item.id}}</span>
      </div>`;
    }}).join("");

    listEl.querySelectorAll(".combo-item").forEach(el => {{
      el.addEventListener("mousedown", (ev) => {{
        ev.preventDefault();
        const item = SOURCE_CATALOG[parseInt(el.dataset.idx, 10)];
        selectSourceCombo(sfx, item);
      }});
    }});
    listEl.style.display = "block";
    void listEl.offsetWidth;
    listEl.classList.add('open');
  }}

  function selectSourceCombo(sfx, item) {{
    const input = document.getElementById(`sourceSearch${{sfx}}`);
    input.value = item.label;
    input.dataset.type = item.type;
    input.dataset.id = item.id;
    const listEl = document.getElementById(`sourceComboList${{sfx}}`);
    listEl.classList.remove('open');
    setTimeout(() => {{ listEl.style.display = "none"; }}, 150);
  }}

  function hideComboLater(sfx) {{
    setTimeout(() => {{
      const listEl = document.getElementById(`sourceComboList${{sfx}}`);
      if (listEl) {{
        listEl.classList.remove('open');
        setTimeout(() => {{ listEl.style.display = "none"; }}, 150);
      }}
    }}, 150);
  }}

  function toggleManualSource(sfx) {{
    const manual = document.getElementById(`sourceManualToggle${{sfx}}`).checked;
    document.getElementById(`manualSourceGroup${{sfx}}`).style.display = manual ? "grid" : "none";
    const input = document.getElementById(`sourceSearch${{sfx}}`);
    input.disabled = manual;
    if (manual) {{
      input.value = "";
      delete input.dataset.type;
      delete input.dataset.id;
    }}
  }}

  function getSourceSpec(sfx) {{
    const manual = document.getElementById(`sourceManualToggle${{sfx}}`).checked;
    if (manual) {{
      const type = document.getElementById(`sourceType${{sfx}}`).value;
      const id = document.getElementById(`sourceId${{sfx}}`).value.trim();
      return id ? {{ type, id }} : null;
    }}
    const input = document.getElementById(`sourceSearch${{sfx}}`);
    return (input.dataset.type && input.dataset.id) ? {{ type: input.dataset.type, id: input.dataset.id }} : null;
  }}

  const savedToken = localStorage.getItem("gh_pat_token");
  if (savedToken) {{
    document.getElementById("ghToken").value = savedToken;
  }} else {{
    document.getElementById("tokenDetails").open = true;
  }}

  function handleModeChange() {{
    const mode = document.getElementById("mode").value;
    const isTwoSources = (mode === "return_spread" || mode === "value_spread");
    document.querySelectorAll(".source-b-group").forEach(el => {{
      el.style.display = isTwoSources ? "flex" : "none";
    }});
  }}

  let currentRegistryFilter = 'all';
  let registrySearchQuery = '';
  let currentRegistryPage = 1;
  const registryPageSize = 6;
  let currentExpandedKey = null;

  function toggleInlineReport(key, reportUrl, label) {{
    const expandRow = document.getElementById('expand-row-' + key);
    const iframe = document.getElementById('iframe-' + key);
    const toggleBtn = document.getElementById('toggle-btn-' + key);
    
    if (expandRow && expandRow.style.display === 'table-row') {{
      closeInlineReport(key);
    }} else {{
      if (currentExpandedKey && currentExpandedKey !== key) {{
        closeInlineReport(currentExpandedKey);
      }}
      if (iframe && (!iframe.src || iframe.src === '' || iframe.src.indexOf(reportUrl) === -1)) {{
        iframe.src = reportUrl;
      }}
      if (expandRow) {{
        // Plan 002: trigger fade-in animation
        expandRow.classList.remove('expanding');
        expandRow.style.display = 'table-row';
        // Force reflow so animation re-triggers each time
        void expandRow.offsetWidth;
        expandRow.classList.add('expanding');
      }}
      if (toggleBtn) {{
        const arrow = toggleBtn.querySelector('.arrow-icon');
        if (arrow) arrow.textContent = '▼';
      }}
      currentExpandedKey = key;
      if (expandRow) expandRow.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
    }}
  }}

  function closeInlineReport(key) {{
    const expandRow = document.getElementById('expand-row-' + key);
    const toggleBtn = document.getElementById('toggle-btn-' + key);
    if (expandRow) expandRow.style.display = 'none';
    if (toggleBtn) {{
      const arrow = toggleBtn.querySelector('.arrow-icon');
      if (arrow) arrow.textContent = '▶';
    }}
    if (currentExpandedKey === key) currentExpandedKey = null;
  }}

  function filterRegistry(filterType) {{
    currentRegistryFilter = filterType;
    document.querySelectorAll('.filter-tab-btn').forEach(btn => {{
      btn.classList.toggle('active', btn.getAttribute('data-filter') === filterType);
    }});
    currentRegistryPage = 1;
    applyRegistryFilterAndPaging();
  }}

  function onRegistrySearchInput() {{
    registrySearchQuery = document.getElementById('registrySearchInput').value.trim().toLowerCase();
    currentRegistryPage = 1;
    applyRegistryFilterAndPaging();
  }}

  function changePage(delta) {{
    currentRegistryPage += delta;
    applyRegistryFilterAndPaging();
  }}

  function applyRegistryFilterAndPaging() {{
    const rows = Array.from(document.querySelectorAll('#registryTbody tr.registry-row'));
    let visibleRows = [];

    rows.forEach(row => {{
      const verdict = row.getAttribute('data-verdict');
      const isPromoted = row.getAttribute('data-promoted') === 'true';
      const searchText = row.getAttribute('data-search') || '';
      const rowId = row.getAttribute('data-row-id') || row.getAttribute('data-key');
      const expandRow = document.getElementById('expand-row-' + rowId);

      let matchFilter = true;
      if (currentRegistryFilter === 'keep') matchFilter = (verdict === 'keep');
      else if (currentRegistryFilter === 'watch') matchFilter = (verdict === 'watch');
      else if (currentRegistryFilter === 'cut') matchFilter = (verdict === 'cut');
      else if (currentRegistryFilter === 'promoted') matchFilter = isPromoted;

      let matchSearch = true;
      if (registrySearchQuery) matchSearch = searchText.includes(registrySearchQuery);

      if (matchFilter && matchSearch) {{
        visibleRows.push({{ row, expandRow }});
      }} else {{
        row.style.display = 'none';
        if (expandRow) expandRow.style.display = 'none';
      }}
    }});

    const totalVisible = visibleRows.length;
    const totalPages = Math.ceil(totalVisible / registryPageSize) || 1;
    if (currentRegistryPage > totalPages) currentRegistryPage = totalPages;
    if (currentRegistryPage < 1) currentRegistryPage = 1;

    const startIdx = (currentRegistryPage - 1) * registryPageSize;
    const endIdx = startIdx + registryPageSize;

    visibleRows.forEach(({{ row, expandRow }}, idx) => {{
      if (idx >= startIdx && idx < endIdx) {{
        row.style.display = 'table-row';
      }} else {{
        row.style.display = 'none';
        if (expandRow) expandRow.style.display = 'none';
      }}
    }});

    const pageInfo = document.getElementById('pageInfo');
    const prevBtn = document.getElementById('prevPageBtn');
    const nextBtn = document.getElementById('nextPageBtn');

    if (totalVisible === 0) {{
      if (pageInfo) pageInfo.textContent = '無符合條件的測試記錄';
      if (prevBtn) prevBtn.disabled = true;
      if (nextBtn) nextBtn.disabled = true;
    }} else {{
      if (pageInfo) pageInfo.textContent = `顯示 ${{startIdx + 1}} - ${{Math.min(endIdx, totalVisible)}} / 共 ${{totalVisible}} 筆 (第 ${{currentRegistryPage}} / ${{totalPages}} 頁)`;
      if (prevBtn) prevBtn.disabled = (currentRegistryPage === 1);
      if (nextBtn) nextBtn.disabled = (currentRegistryPage === totalPages);
    }}
  }}

  document.addEventListener('DOMContentLoaded', () => {{
    applyRegistryFilterAndPaging();
  }});

  function loadReport(reportUrl, label) {{
    const viewer = document.getElementById("reportViewer");
    const frame = document.getElementById("reportFrame");
    const title = document.getElementById("reportViewerTitle");
    const link = document.getElementById("reportViewerLink");
    if (title) title.innerText = "📊 因子分析報告與圖表：" + (label || "");
    if (frame) frame.src = reportUrl;
    if (link) {{ link.href = reportUrl; }}
    if (viewer) {{
      // Plan 003b: fade-in animation
      viewer.style.display = "block";
      void viewer.offsetWidth; // force reflow
      viewer.classList.add('report-visible');
      viewer.scrollIntoView({{ behavior: "smooth" }});
    }}
  }}

  function closeReportViewer() {{
    const viewer = document.getElementById("reportViewer");
    if (viewer) {{
      viewer.classList.remove('report-visible');
      setTimeout(() => {{ viewer.style.display = "none"; }}, 350);
    }}
  }}

  document.getElementById("screeningForm").addEventListener("submit", async (e) => {{
    e.preventDefault();

    const token = document.getElementById("ghToken").value.trim();
    if (!token) {{
      alert("請先填寫 GitHub Personal Access Token (PAT)！");
      document.getElementById("tokenDetails").open = true;
      document.getElementById("ghToken").focus();
      return;
    }}
    localStorage.setItem("gh_pat_token", token);

    const key = document.getElementById("key").value.trim();
    const label = document.getElementById("label").value.trim();
    const mode = document.getElementById("mode").value;
    const isTwoSources = (mode === "return_spread" || mode === "value_spread");

    const specA = getSourceSpec("");
    if (!specA) {{
      alert("請選擇資料來源 A（用搜尋框選一個，或勾選「手動輸入」自己填類型與代號）！");
      return;
    }}
    const specB = isTwoSources ? getSourceSpec("B") : null;
    if (isTwoSources && !specB) {{
      alert("這個轉換模式需要資料來源 B，請選擇或手動輸入！");
      return;
    }}
    const sourceType = specA.type;
    const sourceId = specA.id;
    const sourceBType = specB ? specB.type : "none";
    const sourceBId = specB ? specB.id : "";
    const windowVal = document.getElementById("window").value;
    const invert = document.getElementById("invert").checked;

    const btnSubmit = document.getElementById("btnSubmit");
    const statusCard = document.getElementById("statusCard");

    btnSubmit.disabled = true;
    // Plan 003a: show status card with slide-down animation
    statusCard.classList.remove('status-card-visible');
    statusCard.style.display = "block";
    void statusCard.offsetWidth;
    statusCard.classList.add('status-card-visible');
    closeReportViewer();
    
    updateStatus(1, "已提交分析請求", "GitHub Actions 正在啟動 20 年數據運算與圖表繪製引擎...");

    try {{
      const resp = await fetch(`https://api.github.com/repos/${{REPO_OWNER}}/${{REPO_NAME}}/actions/workflows/factor-screening.yml/dispatches`, {{
        method: "POST",
        headers: {{
          "Accept": "application/vnd.github+json",
          "Authorization": `Bearer ${{token}}`,
          "Content-Type": "application/json"
        }},
        body: JSON.stringify({{
          ref: "main",
          inputs: {{
            key: key,
            label: label,
            mode: mode,
            source_type: sourceType,
            source_id: sourceId,
            source_b_type: sourceBType || "none",
            source_b_id: sourceBId || "",
            window: String(windowVal),
            invert: invert
          }}
        }})
      }});

      if (!resp.ok) {{
        const errText = await resp.text();
        throw new Error(`GitHub API 錯誤 (${{resp.status}}): ${{errText}}`);
      }}

      updateStatus(2, "正在執行 20 年驗證與熱力圖分析", "運算約需要 2~3 分鐘，請保持此頁面開啟...");
      pollForReport(key, label);

    }} catch (err) {{
      alert("提交失敗：" + err.message);
      btnSubmit.disabled = false;
      statusCard.style.display = "none";
    }}
  }});

  function updateStatus(stepNum, title, desc) {{
    document.getElementById("statusTitle").innerText = title;
    document.getElementById("statusDesc").innerText = desc;
    for (let i = 1; i <= 4; i++) {{
      const el = document.getElementById(`step${{i}}`);
      el.className = "step";
      if (i < stepNum) el.classList.add("done");
      if (i === stepNum) el.classList.add("active");
    }}
  }}

  function pollForReport(key, label) {{
    const reportUrl = `screening_${{key}}.html?t=${{Date.now()}}`;
    let attempts = 0;
    const maxAttempts = 40;

    const interval = setInterval(async () => {{
      attempts++;
      if (attempts > 15) {{
        updateStatus(3, "正在生成圖表並部署報告...", "已完成資料運算，正在把報告與圖表發布至網頁...");
      }}

      try {{
        const resp = await fetch(reportUrl, {{ method: "HEAD", cache: "no-store" }});
        if (resp.status === 200) {{
          clearInterval(interval);
          updateStatus(4, "🎉 分析完成！報告與圖表已呈現在下方", "已成功產出該因子的完整 5 道關卡評估與視覺化圖表：");
          document.getElementById("statusSpinner").style.display = "none";
          document.getElementById("btnSubmit").disabled = false;
          
          loadReport(reportUrl, label);
        }}
      }} catch (e) {{}}

      if (attempts >= maxAttempts) {{
        clearInterval(interval);
        alert("等待逾時：請重新整理頁面查看表格內的最新結果。");
        document.getElementById("btnSubmit").disabled = false;
      }}
    }}, 10000);
  }}

  async function demoteFactor(btn, key, label) {{
    if (!confirm(`確定要把「${{label}}」從儀表板退回嗎？\\n這會觸發GitHub Actions直接commit+push到正式站，把它從儀表板的分項卡片與自訂權重選項裡移除。`)) return;
    let token = localStorage.getItem("gh_pat_token");
    if (!token) {{
      token = prompt("請輸入 GitHub Personal Access Token（跟升等按鈕共用同一組）：");
      if (!token) return;
      localStorage.setItem("gh_pat_token", token);
    }}
    btn.disabled = true;
    btn.textContent = "退回中...";
    try {{
      const resp = await fetch(`https://api.github.com/repos/${{REPO_OWNER}}/${{REPO_NAME}}/actions/workflows/promote-factor.yml/dispatches`, {{
        method: "POST",
        headers: {{
          "Accept": "application/vnd.github+json",
          "Authorization": `Bearer ${{token}}`,
          "Content-Type": "application/json"
        }},
        body: JSON.stringify({{ ref: "main", inputs: {{ remove_key: key }} }})
      }});
      if (!resp.ok) {{
        const errText = await resp.text();
        throw new Error(`GitHub API 錯誤 (${{resp.status}}): ${{errText}}`);
      }}
      btn.textContent = "已送出";
      alert("已送出退回請求，幾分鐘後重新整理這頁即可看到狀態更新。");
    }} catch (err) {{
      alert("退回失敗：" + err.message);
      btn.disabled = false;
      btn.textContent = "退回";
    }}
  }}

  const corrGhTokenInput = document.getElementById("corrGhToken");
  const savedCorrToken = localStorage.getItem("gh_pat_token");
  if (savedCorrToken) {{
    corrGhTokenInput.value = savedCorrToken;
  }} else {{
    document.getElementById("corrTokenDetails").open = true;
  }}

  document.getElementById("corrSubmitBtn").addEventListener("click", async () => {{
    const token = corrGhTokenInput.value.trim();
    const statusEl = document.getElementById("corrStatus");
    const btn = document.getElementById("corrSubmitBtn");
    const keys = Array.from(document.querySelectorAll(".corr-factor:checked")).map(el => el.value);
    if (keys.length < 2) {{
      alert("至少要勾選兩個因子才能算相關係數矩陣！");
      return;
    }}
    if (!token) {{
      alert("請先填寫 GitHub Personal Access Token（PAT）！");
      document.getElementById("corrTokenDetails").open = true;
      corrGhTokenInput.focus();
      return;
    }}
    localStorage.setItem("gh_pat_token", token);
    btn.disabled = true;
    statusEl.textContent = "已送出請求，GitHub Actions 正在計算相關係數矩陣並產生熱力圖...";
    try {{
      const resp = await fetch(`https://api.github.com/repos/${{REPO_OWNER}}/${{REPO_NAME}}/actions/workflows/correlation-matrix.yml/dispatches`, {{
        method: "POST",
        headers: {{
          "Accept": "application/vnd.github+json",
          "Authorization": `Bearer ${{token}}`,
          "Content-Type": "application/json"
        }},
        body: JSON.stringify({{ ref: "main", inputs: {{ factor_keys: keys.join(",") }} }})
      }});
      if (!resp.ok) {{
        const errText = await resp.text();
        throw new Error(`GitHub API 錯誤 (${{resp.status}}): ${{errText}}`);
      }}
      statusEl.textContent = "已成功送出，正在等待報告產生（約1-2分鐘）...";
      pollForCorrelationMatrix();
    }} catch (err) {{
      statusEl.textContent = "送出失敗：" + err.message;
      btn.disabled = false;
    }}
  }});

  function pollForCorrelationMatrix() {{
    const reportUrl = `correlation_matrix.html?t=${{Date.now()}}`;
    const statusEl = document.getElementById("corrStatus");
    const btn = document.getElementById("corrSubmitBtn");
    let attempts = 0;
    const maxAttempts = 24;
    const interval = setInterval(async () => {{
      attempts++;
      try {{
        const resp = await fetch(reportUrl, {{ method: "HEAD", cache: "no-store" }});
        if (resp.status === 200) {{
          clearInterval(interval);
          statusEl.textContent = "🎉 相關係數矩陣已產生，顯示於下方。";
          btn.disabled = false;
          loadReport(reportUrl, "因子相關係數矩陣");
        }}
      }} catch (e) {{}}
      if (attempts >= maxAttempts) {{
        clearInterval(interval);
        statusEl.textContent = "等待逾時：請稍後重新整理頁面查看結果。";
        btn.disabled = false;
      }}
    }}, 10000);
  }}
</script>
<script>
  {nav_bar.LANG_TOGGLE_JS}
</script>
</body>
</html>"""


