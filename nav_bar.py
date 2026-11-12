# -*- coding: utf-8 -*-
"""
三個對外頁面(首頁/儀表板/因子篩選平台)共用的頂部導覽列。

背景：這三個頁面由兩支各自獨立的腳本產生(update_dashboard.py、factor_screening.py，
首頁則由generate_hub.py產生)，先前各自手刻了一份不一致、也不完整的nav，而且都不是
sticky、捲動就不見了。這支模組讓所有頁面共用同一份HTML/CSS，不會再各自漂移。

2026-07-30：原本的「驗證報告」「定義手冊」兩頁從導覽列拿掉(內容遷移，見AGENTS.md)——
驗證報告的相關係數矩陣改成因子篩選平台裡的隨選功能；定義手冊裡跟儀表板重複/該屬於
儀表板的內容折回儀表板各分項卡片的說明面板，互動試算器直接移除。
factor_validation_analysis.py本身沒刪，繼續當factor_screening.py的函式庫用；
factor_validation_report.html也還在chart/裡，只是不再進導覽列、不再每日自動重新產生。

CSS故意不吃各頁面自己的CSS變數——儀表板的變數命名(--series-1)跟factor_screening.py
完全沒有CSS變數、沒有深色模式支援。這裡自己帶一份獨立的淺色/深色配色(取自儀表板既有
色票)，不管插進哪個頁面都長一樣、都能正常運作，不需要先把所有頁面的變數系統統一。

2026-08-28：改成三段式排版(左logo＋品牌 / 中頁面導覽 / 右設定)，同時把原本的
width:fit-content 置中膠囊改成 width:100%——三段要分得開就需要寬度。這等於推翻了
先前「固定own max-width、不吃各頁面容器寬度」的決定：現在nav會跟著所在頁面的容器
寬度走，所以在儀表板(1400px)跟首頁(1120px)上寬度不同，但各自都跟該頁內容切齊。
同日稍後再改成長方形滿版吸頂列(position:fixed)，圓角與「不吸頂」都不再成立，
尺寸比照 MacroMicro 的比例(列高約為導覽字級的5倍、logo約佔列高45%)。
2026-11-12：作者重申導覽列要「不吸頂、置中固定寬度、四角圓角」，改回這個做法，
顏色改用 page_style.py 的共用 token。
左側logo直接引用 chart/favicon.svg，產出頁面都在 chart/ 這層，相對路徑就到得了。

用法：
    from nav_bar import render_nav_bar, NAV_BAR_CSS
    html = f"<style>{NAV_BAR_CSS}</style>...{render_nav_bar('dashboard')}..."
"""
import json
import os

# (key, 顯示文字, 本機相對路徑預設值)——順序就是導覽列顯示順序
PAGES = [
    ("hub", "首頁", "index.html"),
    ("dashboard", "儀表板", "dashboard.html"),
    ("screening", "因子開發與篩選平台", "screening_index.html"),
]

NAV_BAR_CSS = """
/* 2026-11-12：照作者明確要求改回「不吸頂、置中、固定最大寬度、四角圓角」。
   (2026-08-28 曾改成 position:fixed 的滿版長方形列，與作者的要求不符。)
   顏色全部用 page_style.py 的 token，各頁都有注入 ROOT_COLORS_CSS。 */
.site-topnav {
  position: static; box-sizing: border-box;
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  width: calc(100% - 48px); max-width: 1400px; margin: 16px auto 0; padding: 8px 12px 8px 14px; min-height: 56px;
  background: var(--surface-1); border: 1px solid var(--rule); border-radius: 10px;
}
.nav-brand {
  display: inline-flex; align-items: center; gap: 9px; flex-shrink: 0;
  text-decoration: none; padding: 4px 6px; border-radius: 6px;
}
.nav-brand:hover { background: var(--surface-2); }
.nav-logo { width: 28px; height: 28px; display: block; flex-shrink: 0; }
.nav-brand-text { font-size: 16px; font-weight: 700; color: var(--text-primary); white-space: nowrap; }
/* 兩側各佔等寬(flex:1)，中間那段才會真的對在容器正中央。 */
.nav-side { flex: 1 1 0; display: flex; align-items: center; min-width: 0; }
.nav-side-end { justify-content: flex-end; }
.nav-links { display: flex; align-items: stretch; gap: 2px; flex-wrap: wrap; justify-content: center; }
.nav-actions { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.nav-links a, .nav-links span.active {
  color: var(--text-secondary); text-decoration: none; font-weight: 600; font-size: 15px;
  padding: 8px 14px; border-radius: 6px; white-space: nowrap;
  display: inline-flex; align-items: center; justify-content: center;
  box-shadow: inset 0 -2px 0 transparent;
}
.nav-links a:hover { color: var(--text-primary); background: var(--surface-2); }
.nav-links span.active { color: var(--accent); box-shadow: inset 0 -2px 0 var(--accent); border-radius: 6px 6px 0 0; }
.lang-toggle-btn {
  display: inline-flex; align-items: center; min-height: 36px;
  background: var(--surface-1); border: 1px solid var(--border); color: var(--text-secondary);
  font: inherit; font-size: 13.5px; font-weight: 600;
  padding: 6px 12px; border-radius: 6px; cursor: pointer;
}
.lang-toggle-btn:hover { background: var(--surface-2); color: var(--text-primary); }
/* 窄螢幕：三段擠一行放不下，改兩行——第一行品牌＋語言，第二行頁面導覽。
   品牌文字保留(之前在手機上被隱藏，只剩 logo，訪客看不出這是什麼網站)。 */
@media (max-width: 780px) {
  .site-topnav { flex-wrap: wrap; row-gap: 4px; width: calc(100% - 32px); margin: 10px auto 0; padding: 8px 10px; }
  .nav-side { flex: 1 1 auto; }
  .nav-side-end { flex: 0 0 auto; }
  .nav-brand-text { font-size: 15px; }
  .nav-links { order: 3; flex-basis: 100%; min-width: 0; justify-content: flex-start; border-top: 1px solid var(--rule); padding-top: 4px; }
  .nav-links a, .nav-links span.active { padding: 8px 10px; font-size: 14px; min-height: 40px; }
}
"""

LANG_TOGGLE_JS = """
const I18N_DICT = {
  zh: {
    nav_brand: "債券恐懼貪婪",
    nav_hub: "首頁",
    nav_dashboard: "儀表板",
    nav_screening: "因子開發與篩選平台",
    lang_btn: "EN",
    
    // Dashboard Page
    dash_title: "債券市場恐懼貪婪儀表板",
    dash_subtitle: "",
    dash_caption: "綜合分數是各因子 0 到 100 分的等權重平均，當天缺資料的因子不列入。往下依序是總分、歷史走勢跟各因子拆解。",
    dash_latest_label: "最新收盤日綜合分數",
    dash_logic_btn: "計算方式與限制",
    dash_method_how: "<b>怎麼算：</b>綜合分數是各分項 0 到 100 分的等權重算術平均。某個分項當天沒有資料就不列入，由其餘分項平均，不用假數字填補。分級：0–24 極度恐懼、25–44 恐懼、45–55 中性、56–75 貪婪、76–100 極度貪婪，區間跟 CNN Fear &amp; Greed Index 相同。",
    dash_method_percentile: "<b>為什麼每項都是 0 到 100：</b>把當天的原始數值放進過去 5 年（1825 天）的分佈取百分位，分數 98 代表比過去 5 年 98% 的日子都高。公式：分數 =（視窗內數值 ≤ 今天的天數）÷ 1825 × 100。這樣單位不同的指標（%、點數、指數）可以直接平均，比的是相對位置，市場整體水位改變也不影響。",
    dash_method_sources_title: "<b>資料來源明細：</b>",
    dash_method_th_field: "欄位",
    dash_method_th_code: "代號",
    dash_method_th_source: "來源",
    dash_method_th_history: "可回溯到",
    dash_method_th_desc: "說明",
    dash_method_no_future: "<b>不使用未來資料：</b>所有滾動計算（移動平均、區間報酬、5 年百分位）都只用當天和以前的資料。",
    dash_method_limits: "<b>限制：</b>這是跟過去 5 年比的位置指標，不是預測模型。極端事件滿 5 年移出視窗後，同樣的原始數值會算出不同分數。週末跟假日沿用前一個交易日的數值。",
    dash_custom_weight_title: "自訂權重",
    dash_custom_weight_tag: "研究用",
    dash_custom_weight_explain: "這是什麼",
    dash_custom_weight_desc: "勾選要納入的因子、拖曳權重，看看不同組合下的歷史走勢跟今天的分數。結果只會在下方走勢圖多畫一條虛線，上方的官方分數維持等權重平均，不受影響。",
    dash_custom_mode_label: "在走勢圖加上自訂權重的虛線",
    dash_history_title: "綜合指數歷史時間軸",
    dash_history_sub: "2020 年至今。點圖表可以看那一天的細節。",
    dash_history_hint: "分數用每日收盤資料計算，不是盤中即時。點任一張圖，整頁會跳到同一天；縮放跟平移會同步到所有圖表，也可以用 1M／3M／6M／1Y／2Y／ALL 切換範圍。殖利率線只是參考，不參與分數計算。",
    dash_legend_score: "綜合分數 (等權重)",
    dash_legend_neutral: "50分中性基準線",
    dash_legend_ust10: "10年期公債殖利率 (%)",
    dash_legend_custom: "自訂組合分數",
    dash_components_title: "分項拆解",
    dash_components_sub: "· 每項各自的計算方式與歷史時間軸",
    dash_footnote: "資料來源：Yahoo Finance（HG=F、GC=F 每日收盤）、Treasury.gov（10年期殖利率）。缺值以前一交易日補齊；百分位計算的抓取範圍往前拉到2014年中，確保2020年起每天都有滿5年視窗，且所有計算僅使用當天以前的歷史資料，不引用未來資料。",

    // Dashboard Controls & Badges
    ctrl_drag_slider: "拖曳時間軸選日期",
    ctrl_jump_date: "跳至日期",
    ctrl_jump_latest: "回到最新",
    ctrl_reset_zoom: "回到全部時間範圍",
    ctrl_zoom_hint: "滾輪縮放／Shift＋拖曳框選放大／拖曳平移／雙擊重置；鍵盤：←→ 移動、＋− 縮放、Esc 重置",
    ctrl_show_events: "顯示事件標記線（FOMC／CPI／NFP）",
    ctrl_rail_jump: "事件行事曆 ↓",
    comp_prev_day: "前一交易日",
    comp_1w: "一週前",
    comp_1m: "一個月前",
    comp_1y: "一年前",

    // Custom Weights
    cw_preset_placeholder: "幫這組設定取個名字，例如「重視銅金比」",
    cw_preset_save: "儲存目前設定",
    cw_preset_hint: "設定只存在這台裝置的這個瀏覽器（localStorage），不會上傳。換裝置、換瀏覽器、清除瀏覽資料或用無痕視窗都看不到。",
    cw_apply_regime: "套用目前情境動態權重",

    // Emotion Tiers
    tier_extreme_fear: "極度恐懼",
    tier_fear: "恐懼",
    tier_neutral: "中性",
    tier_greed: "貪婪",
    tier_extreme_greed: "極度貪婪",
    
    // Event Rail
    event_rail_title: "總經事件行事曆",
    event_rail_hint: "FOMC 決議、CPI 跟非農的公布日。點一筆事件，圖表會跳到那一天。",
    tab_all: "全部",
    
    // Hub Page
    hub_title: "債券市場恐懼貪婪指數",
    hub_lede: "把美國公債市場的指標換算成每天 0 到 100 的恐懼貪婪分數，每個交易日收盤後更新。公式跟資料來源都寫在儀表板上，可以自己驗算。",
    hub_intro_title: "這是什麼",
    hub_spark_caption: "0–100，虛線為 50 分",
    hub_intro_p1: "恐懼貪婪指數的概念來自 CNN 的股市版：用一組市場指標算出 0 到 100 的分數。分數越低，市場越偏向避險；越高，越願意承擔風險。這裡把同一套做法用在<b>美國公債市場</b>，目前採用殖利率動能跟銅金比，每個交易日收盤後重算。",
    hub_intro_p2: "每項指標先換算成它在過去 5 年裡的百分位（0 到 100），再取平均。分數說的是跟近 5 年比，現在的情緒偏向哪一端。<b>它不是預測模型，也不是投資建議。</b>",
    hub_intro_p3: "想看今天的分數跟歷史走勢，到「即時儀表板」。想測試某個新指標加進來對綜合分數有沒有幫助，到「因子開發與篩選平台」。",
    hub_live_title: "即時儀表板",
    hub_live_desc: "今天的綜合分數、各因子走勢跟可以拖曳的時間軸，每個交易日收盤後更新。",
    hub_platform_title: "因子開發與篩選平台",
    hub_platform_desc: "輸入新因子跑關卡檢驗跟回測，每次結果都留在登記簿；也可以產生因子之間的相關係數矩陣。",

    // Screening Page
    screening_title: "因子開發與篩選平台",
    screening_card1_title: "測試新因子",
    form_token_summary: "GitHub Personal Access Token（第一次使用要填）",
    form_token_hint: "需要 repo 跟 workflow 權限。Token 只存在這個瀏覽器的 localStorage，不會進 git。",
    form_key_label: "因子代號（英文，會當檔名）",
    form_key_placeholder: "例: vix_ma_dev",
    form_label_label: "因子名稱",
    form_label_placeholder: "例: VIX 125日均線乖離率",
    form_mode_label: "轉換模式",
    form_window_label: "滾動視窗（天）",
    form_source_a_label: "資料來源 (Source A)",
    form_source_placeholder: "打字搜尋，例如：十年期公債 / DGS10 / VIX",
    form_manual_toggle: "找不到？手動輸入類型與代號",
    form_invert_label: "數值越高代表越恐懼時勾選，分數會反轉。",
    form_submit_btn: "送出並產生報告",
    corr_card_title: "產生因子相關係數矩陣",
    corr_card_desc: "勾選要比較的因子，產生兩兩相關係數熱力圖。相關係數太高，代表兩個因子在講同一件事，加進來的幫助有限。算完會顯示在下方。",
    corr_submit_btn: "產生相關係數矩陣",
    corr_token_summary: "GitHub Personal Access Token（跟上面表單共用同一組）",
    reg_title: "歷史測試紀錄登記簿",
    reg_sub: "點因子名稱可以展開報告",
    th_date: "測試日期",
    th_factor: "因子",
    th_mode: "轉換模式",
    th_ic: "IC(20日,重疊取樣)",
    th_flags: "型態標記",
    th_gates: "關卡通過",
    th_verdict: "結果",
    th_status: "儀表板狀態",
    filter_all: "全部",
    filter_keep: "通過",
    filter_watch: "觀察",
    filter_cut: "淘汰",
    filter_promoted: "已升等",
    verdict_keep: "通過",
    verdict_watch: "觀察",
    verdict_cut: "淘汰",
    promoted_badge: "已升等",
    demote_btn: "退回"
  },
  en: {
    nav_brand: "Bond Fear & Greed",
    nav_hub: "Home",
    nav_dashboard: "Dashboard",
    nav_screening: "Factor Platform",
    lang_btn: "繁中",
    
    // Dashboard Page
    dash_title: "U.S. Bond Fear & Greed Dashboard",
    dash_subtitle: "Daily sentiment score for the U.S. Treasury market",
    dash_caption: "The composite score is the equal-weighted average of each factor's 0–100 score; factors with no data that day are left out. Below: the total, its history, then each factor.",
    dash_latest_label: "Latest Composite Sentiment Score",
    dash_logic_btn: "How it's calculated & limits",
    dash_method_how: "<b>How it's calculated:</b> the composite is the equal-weighted mean of each factor's 0–100 score. A factor with no data that day is left out rather than filled in. Tiers: 0–24 Extreme Fear, 25–44 Fear, 45–55 Neutral, 56–75 Greed, 76–100 Extreme Greed, the same ranges as CNN's Fear &amp; Greed Index.",
    dash_method_percentile: "<b>Why every factor is 0–100:</b> today's raw value is ranked within the past 5 years (1825 days); a score of 98 means it is higher than 98% of those days. Formula: Score = (days in window with value ≤ today) ÷ 1825 × 100. Indicators in different units (%, points, index levels) can then be averaged, and a shift in the overall level of the market does not distort the score.",
    dash_method_sources_title: "<b>Data Sources Detail:</b>",
    dash_method_th_field: "Field",
    dash_method_th_code: "Ticker",
    dash_method_th_source: "Source",
    dash_method_th_history: "History",
    dash_method_th_desc: "Description",
    dash_method_no_future: "<b>No look-ahead:</b> every rolling calculation (moving averages, period returns, 5-year percentiles) uses only data up to that day.",
    dash_method_limits: "<b>Limits:</b> this measures position relative to the past 5 years; it is not a forecasting model. When an extreme event rolls out of the 5-year window, the same raw value produces a different score. Weekends and holidays carry the previous trading day's value.",
    dash_custom_weight_title: "Custom Weights",
    dash_custom_weight_tag: "Research Mode",
    dash_custom_weight_explain: "What is this",
    dash_custom_weight_desc: "Choose factors and drag their weights to see how a different mix changes the history and today's score. The result only adds a dashed line to the chart below; the official equal-weighted score above stays unchanged.",
    dash_custom_mode_label: "Show custom-weight line on the chart",
    dash_history_title: "Composite Index Historical Timeline",
    dash_history_sub: "2020 to today. Click the chart to see that day's details.",
    dash_history_hint: "Scores use daily closes, not intraday data. Click any chart to move the whole page to that day. Zoom and pan apply to every chart; the 1M–ALL buttons switch the range. The yield line is for reference only and is not part of the score.",
    dash_legend_score: "Composite Score (Equal-Weighted)",
    dash_legend_neutral: "50 Neutral Baseline",
    dash_legend_ust10: "10-Year Treasury Yield (%)",
    dash_legend_custom: "Custom Weight Composite Score",
    dash_components_title: "Factor Component Breakdown",
    dash_components_sub: "· Detailed calculation methodology & individual timeline charts",
    dash_footnote: "Data sources: Yahoo Finance (HG=F, GC=F daily closes), Treasury.gov (10Y Yield). Values strictly backward-looking without look-ahead bias.",

    // Dashboard Controls & Badges
    ctrl_drag_slider: "Drag timeline to select date",
    ctrl_jump_date: "Jump to date",
    ctrl_jump_latest: "Jump to Latest",
    ctrl_reset_zoom: "Reset Time Range",
    ctrl_zoom_hint: "Scroll to zoom / Shift+drag to box-select / Drag to pan / Double-click to reset; keyboard: ←→ move, +− zoom, Esc reset",
    ctrl_show_events: "Show Event Lines (FOMC / CPI / NFP)",
    ctrl_rail_jump: "Event calendar ↓",
    comp_prev_day: "1 Day Ago",
    comp_1w: "1 Week Ago",
    comp_1m: "1 Month Ago",
    comp_1y: "1 Year Ago",

    // Custom Weights
    cw_preset_placeholder: "Preset name, e.g. 'Copper-Gold Focus'",
    cw_preset_save: "Save Preset",
    cw_preset_hint: "Presets are kept only in this browser on this device (localStorage) and are never uploaded. They won't appear on another device or browser, after clearing site data, or in a private window.",
    cw_apply_regime: "Apply Current Regime Weights",

    // Emotion Tiers
    tier_extreme_fear: "Extreme Fear",
    tier_fear: "Fear",
    tier_neutral: "Neutral",
    tier_greed: "Greed",
    tier_extreme_greed: "Extreme Greed",
    
    // Event Rail
    event_rail_title: "Macro Event Calendar",
    event_rail_hint: "FOMC decisions and CPI and payroll release dates. Click an event to jump the chart to that day.",
    tab_all: "ALL",
    
    // Hub Page
    hub_title: "U.S. Treasury Fear & Greed Index",
    hub_lede: "Daily 0–100 fear & greed score for the U.S. Treasury market, updated after each close. Every formula and data source is on the dashboard.",
    hub_intro_title: "About This Project",
    hub_spark_caption: "0–100, dashed line at 50",
    hub_intro_p1: "The idea comes from CNN's stock-market Fear & Greed Index: a set of market indicators turned into a 0–100 score. Lower means the market leans risk-off; higher means it is more willing to take risk. This project applies the same approach to the <b>U.S. Treasury market</b>, currently using yield momentum and the copper/gold spread, recalculated after each trading day.",
    hub_intro_p2: "Each indicator is converted to its percentile over the past 5 years (0–100), then averaged. The score tells you which way sentiment leans compared with the last 5 years. <b>It is not a forecasting model and not investment advice.</b>",
    hub_intro_p3: "For today's score and its history, go to the Live Dashboard. To test whether a new indicator would help the composite score, go to the Factor Platform.",
    hub_live_title: "Live Dashboard",
    hub_live_desc: "Today's composite score, each factor's history and a draggable timeline, updated after each trading day.",
    hub_platform_title: "Factor Discovery Platform",
    hub_platform_desc: "Run a new factor through the screening gates and a backtest; every result stays in the registry. You can also generate a correlation matrix between factors.",

    // Screening Page
    screening_title: "Factor Discovery & Screening Platform",
    screening_card1_title: "Test a new factor",
    form_token_summary: "GitHub Personal Access Token (required the first time)",
    form_token_hint: "Needs repo and workflow scopes. The token is kept only in this browser's localStorage and never goes into git.",
    form_key_label: "Factor key (English, used as the file name)",
    form_key_placeholder: "e.g. vix_ma_dev",
    form_label_label: "Factor name",
    form_label_placeholder: "e.g. VIX 125D MA Deviation",
    form_mode_label: "Transformation mode",
    form_window_label: "Rolling window (days)",
    form_source_a_label: "Data Source A",
    form_source_placeholder: "Search name or symbol, e.g. 10Y Treasury / DGS10 / VIX",
    form_manual_toggle: "Can't find? Enter type & symbol manually",
    form_invert_label: "Check this if higher values mean more fear; the score will be inverted.",
    form_submit_btn: "Submit and build report",
    corr_card_title: "Generate Factor Correlation Matrix",
    corr_card_desc: "Select factors to build a pairwise correlation heatmap. A high correlation means two factors say the same thing, so adding both helps little. The result appears below.",
    corr_submit_btn: "Generate Correlation Matrix",
    corr_token_summary: "GitHub Personal Access Token (shared with the form above)",
    reg_title: "Historical Factor Test Registry",
    reg_sub: "Click a factor name to open its report",
    th_date: "Test Date",
    th_factor: "Factor",
    th_mode: "Mode",
    th_ic: "IC (20D Rolling)",
    th_flags: "Pattern Tags",
    th_gates: "Gates Passed",
    th_verdict: "Verdict",
    th_status: "Dashboard Status",
    filter_all: "ALL",
    filter_keep: "PASS",
    filter_watch: "WATCH",
    filter_cut: "CUT",
    filter_promoted: "PROMOTED",
    verdict_keep: "PASS",
    verdict_watch: "WATCH",
    verdict_cut: "CUT",
    promoted_badge: "PROMOTED",
    demote_btn: "Demote"
  }
};

let currentLang = localStorage.getItem("user_lang") || "zh";

function updatePageLanguage(lang) {
  currentLang = lang;
  localStorage.setItem("user_lang", lang);
  const dict = I18N_DICT[lang] || I18N_DICT.zh;
  
  const btnTextEl = document.getElementById("langToggleText");
  if (btnTextEl) btnTextEl.textContent = dict.lang_btn;

  document.querySelectorAll("[data-i18n]").forEach(el => {
    const key = el.dataset.i18n;
    if (key in dict) {
      // data-i18n-html：字典值本身帶<b>等標籤(粗體強調)，要當HTML插入，
      // 不能用textContent——那樣會把<b>字面印出來，不會真的變粗體
      // (2026-08-25發現：EN切換這幾格一直是壞的，因為原本只有textContent這條路)。
      if (el.hasAttribute("data-i18n-html")) {
        el.innerHTML = dict[key];
      } else {
        el.textContent = dict[key];
      }
    }
  });

  document.documentElement.lang = lang === "en" ? "en" : "zh-TW";
}

function toggleLanguage() {
  const nextLang = currentLang === "zh" ? "en" : "zh";
  updatePageLanguage(nextLang);
  if (typeof onLanguageChanged === "function") {
    onLanguageChanged(nextLang);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  if (currentLang && currentLang !== "zh") {
    updatePageLanguage(currentLang);
  }
});
"""


def _load_link_overrides(base_dir="."):
    """讀 artifact_urls.json 取得跨頁連結覆寫。"""
    try:
        with open(os.path.join(base_dir, "artifact_urls.json"), encoding="utf-8") as f:
            urls = json.load(f)
    except FileNotFoundError:
        urls = {}
    return {key: urls.get(key) or default_href for key, _, default_href in PAGES}


def render_nav_bar(active_key, base_dir="."):
    """active_key: 'hub' | 'dashboard' | 'report' | 'manual' | 'screening'

    三段式排版：左邊品牌(logo+名稱，點了回首頁)、中間頁面導覽、右邊設定區。
    logo 直接用 chart/favicon.svg——產出頁面都在 chart/ 這層，相對路徑就到得了，
    不需要另外再放一份。
    """
    links = _load_link_overrides(base_dir)

    items = []
    for key, label, _ in PAGES:
        if key == active_key:
            items.append(f'<span class="active" aria-current="page" data-i18n="nav_{key}">{label}</span>')
        else:
            items.append(f'<a href="{links[key]}" data-i18n="nav_{key}">{label}</a>')

    brand = (
        f'<a class="nav-brand" href="{links["hub"]}">'
        '<img class="nav-logo" src="favicon.svg" alt="" aria-hidden="true">'
        '<span class="nav-brand-text" data-i18n="nav_brand">債券恐懼貪婪</span>'
        '</a>'
    )
    lang_btn = (
        '<button class="lang-toggle-btn" id="langToggleBtn" type="button" onclick="toggleLanguage()" aria-label="切換語言 / Switch language">'
        '<span class="lang-text" id="langToggleText">EN</span>'
        '</button>'
    )

    return (
        '<nav class="site-topnav">'
        f'<div class="nav-side">{brand}</div>'
        f'<div class="nav-links">{"".join(items)}</div>'
        f'<div class="nav-side nav-side-end"><div class="nav-actions">{lang_btn}</div></div>'
        '</nav>'
    )
