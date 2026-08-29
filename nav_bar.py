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
/* 三段式(左logo / 中導覽 / 右設定)、長方形、鎖在頂端：position:fixed，捲頁完全不會跑掉。

   為什麼不是 sticky：sticky 只能在「自己的父容器範圍內」吸附，而儀表板的 nav
   包在 .nav-wrap 裡、那個 div 只有 90px 高——捲過去之後 nav 就跟著父容器一起
   離開畫面了(實測捲到 900px 時 nav 已經在 -870px)。fixed 是相對視窗定位，沒有
   這個限制。

   fixed 用 left:0/right:0 撐滿，不用 100vw——vw 會把捲軸寬度算進去，導致多出
   一條水平捲軸(這個坑先前用 -50vw 做滿版背景時踩過)。

   fixed 會脫離文件流不佔位，所以下面補 body padding-top 把高度還回去，不然
   內容會被蓋住。注意：任何祖先只要有 transform 就會讓 fixed 改成相對它定位，
   所以 dashboard_template.html 的 .nav-wrap 已經拿掉 animate-in(那個動畫的
   fill-mode:both 會留下 transform:translateY(0))。 */
body { padding-top: 79px; }
.site-topnav {
  position: fixed; top: 0; left: 0; right: 0; z-index: 200;
  display: flex; align-items: center; justify-content: space-between; gap: 14px;
  margin: 0; padding: 0 34px; min-height: 78px;
  background: rgba(255, 255, 255, 0.88);
  backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
  border: none; border-bottom: 1px solid #dfe2e8; border-radius: 0; box-shadow: none;
}
.nav-brand {
  display: inline-flex; align-items: center; gap: 9px; flex-shrink: 0;
  text-decoration: none; padding: 5px 12px 5px 7px; border-radius: 999px;
  transition: background-color 0.22s ease;
}
.nav-brand:hover { background: rgba(30,58,95,0.06); }
.nav-logo { width: 34px; height: 34px; display: block; flex-shrink: 0; }
.nav-brand-text {
  font-size: 17px; font-weight: 700; color: #1e3a5f;
  white-space: nowrap; letter-spacing: -0.01em;
}
/* 兩側各佔等寬(flex:1)，中間那段才會真的對在容器正中央。
   只用 justify-content:space-between 的話，中段位置會被左右兩側的實際寬度
   推著跑——左邊品牌比右邊設定寬，中段就會偏右(實測偏了72px)。 */
.nav-side { flex: 1 1 0; display: flex; align-items: center; min-width: 0; }
.nav-side-end { justify-content: flex-end; }
.nav-links { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; justify-content: center; }
.nav-actions { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }

.nav-links a, .nav-links span.active {
  color: #4a5568; text-decoration: none; font-weight: 600; font-size: 16px;
  padding: 10px 19px; border-radius: 999px; white-space: nowrap;
  transition: all 0.22s cubic-bezier(0.16, 1, 0.3, 1);
  display: inline-flex; align-items: center; justify-content: center;
}
.nav-links a:hover {
  background: rgba(30,58,95,0.08); color: #1e3a5f;
  transform: translateY(-1px) scale(1.02);
}
.nav-links a:active { transform: scale(0.97); }
.nav-links span.active { color: #1e3a5f; background: rgba(30,58,95,0.12); font-weight: 700; }

.lang-toggle-btn {
  display: inline-flex; align-items: center; gap: 4px;
  background: var(--surface-2, #f8f9fb); border: 1px solid var(--border, #dfe2e8);
  color: var(--text-secondary, #4a5568); font-size: 14px; font-weight: 700;
  padding: 8px 16px; border-radius: 999px; cursor: pointer;
  transition: all 0.22s cubic-bezier(0.16, 1, 0.3, 1);
  outline: none;
}
.lang-toggle-btn:hover {
  background: var(--surface-1, #ffffff); color: var(--series-1, #1e3a5f); border-color: var(--axis, #a7adb9);
  transform: translateY(-1px) scale(1.03); box-shadow: 0 2px 6px rgba(22,26,35,0.06);
}
.lang-toggle-btn:active { transform: scale(0.96); }
.lang-icon { font-size: 14px; }

/* 窄螢幕：三段擠一行放不下(「因子開發與篩選平台」9個字就吃掉整排)，
   改成兩行——第一行左logo右設定，導覽整條掉到第二行置中。
   單純縮字級是不夠的，實測375px下會直接溢出被設定鈕蓋住。 */
@media (max-width: 780px) {
  body { padding-top: 120px; }  /* 兩行版實測 118px，多留 2px */
  .site-topnav { flex-wrap: wrap; row-gap: 8px; gap: 8px; padding: 11px 16px; min-height: 0; }
  .nav-brand-text { display: none; }
  .nav-side { flex: 0 0 auto; }
  .nav-side-end { margin-left: auto; }
  .nav-links { order: 3; flex-basis: 100%; min-width: 0; }
  .nav-links a, .nav-links span.active { padding: 8px 14px; font-size: 14.5px; }
}

@media (prefers-color-scheme: dark) {
  .site-topnav { background: rgba(23, 27, 36, 0.90); border-bottom-color: #2c313d; }
  .nav-links a, .nav-links span.active { color: #b8c0cc; }
  .nav-links a:hover { background: rgba(126,163,207,0.12); color: #7ea3cf; transform: translateY(-1px) scale(1.02); }
  .nav-links span.active { color: #7ea3cf; background: rgba(126,163,207,0.18); }
  .nav-brand-text { color: #e4e8ee; }
  .nav-brand:hover { background: rgba(126,163,207,0.10); }
  .lang-toggle-btn { background: #1e232d; border-color: #2c313d; color: #b8c0cc; }
  .lang-toggle-btn:hover { background: #171b24; color: #7ea3cf; border-color: #4a5164; }
}
:root[data-theme="dark"] .site-topnav { background: rgba(23, 27, 36, 0.90); border-bottom-color: #2c313d; }
:root[data-theme="dark"] .nav-links a, :root[data-theme="dark"] .nav-links span.active { color: #b8c0cc; }
:root[data-theme="dark"] .nav-links a:hover { background: rgba(126,163,207,0.12); color: #7ea3cf; transform: translateY(-1px) scale(1.02); }
:root[data-theme="dark"] .nav-links span.active { color: #7ea3cf; background: rgba(126,163,207,0.18); }
:root[data-theme="dark"] .nav-brand-text { color: #e4e8ee; }
:root[data-theme="dark"] .nav-brand:hover { background: rgba(126,163,207,0.10); }
:root[data-theme="dark"] .lang-toggle-btn { background: #1e232d; border-color: #2c313d; color: #b8c0cc; }
:root[data-theme="dark"] .lang-toggle-btn:hover { background: #171b24; color: #7ea3cf; border-color: #4a5164; }

:root[data-theme="light"] .site-topnav { background: rgba(255, 255, 255, 0.88); border-bottom-color: #dfe2e8; }
:root[data-theme="light"] .nav-links a, :root[data-theme="light"] .nav-links span.active { color: #4a5568; }
:root[data-theme="light"] .nav-links a:hover { background: rgba(30,58,95,0.08); color: #1e3a5f; transform: translateY(-1px) scale(1.02); }
:root[data-theme="light"] .nav-links span.active { color: #1e3a5f; background: rgba(30,58,95,0.12); }
:root[data-theme="light"] .nav-brand-text { color: #1e3a5f; }
:root[data-theme="light"] .lang-toggle-btn { background: #f8f9fb; border-color: #dfe2e8; color: #4a5568; }
:root[data-theme="light"] .lang-toggle-btn:hover { background: #ffffff; color: #1e3a5f; border-color: #a7adb9; }
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
    dash_subtitle: "A Quantitative Sentiment Framework for U.S. Treasury Markets",
    dash_caption: "動能、銅金比 — 各項0–100分等權重平均（尚無資料的項目自動排除），由上而下：先看總體指數，再往下拆解各分項的計算邏輯",
    dash_latest_label: "最新收盤日綜合分數",
    dash_logic_btn: "綜合分數的計算邏輯與可信度",
    dash_method_how: "<b>怎麼算：</b>綜合分數 = 兩個分項（動能、銅金比）各自0–100分的<b>等權重算術平均</b>；某分項當天沒有資料時自動排除、由其餘分項平均（不會用假數字填充）。分級標籤：0–24 極度恐懼／25–44 恐懼／45–55 中性／56–75 貪婪／76–100 極度貪婪，區間定義與CNN Fear &amp; Greed Index一致。",
    dash_method_percentile: "<b>各分項為何是0–100（核心機制：滾動百分位）：</b>把當天原始數值放進<b>過去5年（1825天）的分佈</b>裡取百分位——分數98代表比過去5年98%的交易日都高。公式：分數 = (視窗內「數值 ≤ 今天」的天數) ÷ 1825 × 100。好處：單位完全不同的指標（%、點數、指數）統一成0–100可平均；比「相對位置」不比絕對值，市場整體水位漂移不影響。",
    dash_method_sources_title: "<b>資料來源明細：</b>",
    dash_method_th_field: "欄位",
    dash_method_th_code: "代號",
    dash_method_th_source: "來源",
    dash_method_th_history: "可回溯到",
    dash_method_th_desc: "說明",
    dash_method_no_future: "<b>禁止引用未來資料：</b>所有滾動計算（125日均線、40日報酬、5年百分位）都是嚴格「向後看」的移動視窗，只用當天（含）以前的歷史資料，絕不使用未來才發生的價格。",
    dash_method_limits: "<b>限制（請一併考量）：</b>這是「相對過去5年」的位置指標，不是預測模型；極端事件剛滿5年滾出窗口時，同樣的原始數值算出的分數會改變；週末假日沿用前一交易日數值。",
    dash_custom_weight_title: "自訂權重",
    dash_custom_weight_tag: "研究用",
    dash_custom_weight_explain: "這是什麼",
    dash_custom_weight_desc: "給你自己探索用的研究工具：勾選想納入的因子、拖曳調整權重，即時看看不同組合方式會怎麼改變歷史走勢與今天的分數。<b>不會取代、也不會覆蓋上方的官方等權重分數</b>——那個永遠是兩項等權重平均；這裡算出來的只會在下方走勢圖疊加一條虛線做對照。",
    dash_custom_mode_label: "啟用自訂模式（在下方走勢圖疊加一條虛線）",
    dash_history_title: "綜合指數歷史時間軸",
    dash_history_sub: "· 觀察2020年至今美債情緒高低點變化，點圖表可切換各收盤日細節",
    dash_history_hint: "分數為每日收盤資料計算，非盤中即時。點擊任何圖表（含下方各分項小圖）會連動整頁的選定日期；縮放與平移所有圖表同步聯動，也可用 1M/3M/6M/1Y/2Y/ALL 按鈕快速切換時間範圍。殖利率線只是價格參考疊圖，不參與分數計算。",
    dash_legend_score: "綜合分數 (等權重)",
    dash_legend_neutral: "50分中性基準線",
    dash_legend_ust10: "10年期公債殖利率 (%)",
    dash_legend_custom: "自訂組合分數",
    dash_components_title: "分項拆解",
    dash_components_sub: "· 每項各自的計算方式與歷史時間軸",
    dash_footnote: "資料來源：Yahoo Finance（ZN=F、HG=F、GC=F 每日收盤）、Treasury.gov（10年期殖利率）。缺值以前一交易日補齊；百分位計算的抓取範圍往前拉到2014年中，確保2020年起每天都有滿5年視窗，且所有計算僅使用當天以前的歷史資料，不引用未來資料。",

    // Dashboard Controls & Badges
    ctrl_drag_slider: "拖曳時間軸選日期",
    ctrl_jump_date: "跳至日期",
    ctrl_jump_latest: "回到最新",
    ctrl_reset_zoom: "回到全部時間範圍",
    ctrl_zoom_hint: "滾輪縮放／Shift+拖曳框選放大／拖曳平移／雙擊重置",
    ctrl_show_events: "顯示事件標記線（FOMC／CPI／NFP）",
    comp_prev_day: "前一交易日",
    comp_1w: "一週前",
    comp_1m: "一個月前",
    comp_1y: "一年前",

    // Custom Weights
    cw_preset_placeholder: "幫這組設定取個名字，例如「重視銅金比」",
    cw_preset_save: "儲存目前設定",
    cw_preset_hint: "設定僅存於<b>目前這台裝置的這個瀏覽器</b>（localStorage）——換裝置、換瀏覽器、清瀏覽器資料、或用無痕視窗，都不會看到已儲存的設定；不會上傳到任何伺服器。",
    cw_apply_regime: "套用目前情境動態權重",

    // Emotion Tiers
    tier_extreme_fear: "極度恐懼",
    tier_fear: "恐懼",
    tier_neutral: "中性",
    tier_greed: "貪婪",
    tier_extreme_greed: "極度貪婪",
    
    // Event Rail
    event_rail_title: "📅 總經事件行事曆",
    event_rail_hint: "FOMC／CPI／NFP 等重大數據發布日。點擊可切換至當日，圖表連動捲動。",
    tab_all: "全部",
    
    // Hub Page
    hub_title: "債券市場恐懼貪婪 · 專案首頁",
    hub_lede: "美債市場指標彙整成每日恐懼貪婪分數，配套因子開發與篩選平台可持續擴充。同一份定義來源(factor_definitions.json)驅動儀表板與各項計算。",
    hub_intro_title: "這是什麼",
    hub_intro_p1: "「恐懼貪婪指數」的概念來自CNN的股市版——用一組市場指標算出0到100的分數，越低代表市場情緒越「恐懼」（避險為主、風險偏好降低），越高代表越「貪婪」（風險偏好升溫）。這個專案把同樣的方法論套用在<b>美國公債市場</b>上：整合殖利率動能、銅金比這2項反映景氣循環與風險偏好的指標，每個交易日收盤後重新計算一次。",
    hub_intro_p2: "每項指標都換算成「跟過去5年比起來排第幾百分位」的0–100分數，再取平均——這是「相對於近期歷史，市場現在情緒偏向哪一端」的參考尺，<b>不是預測模型、也不是投資建議</b>。",
    hub_intro_p3: "<b>怎麼開始：</b>想看今天的分數跟歷史走勢，進「即時儀表板」；想測試自己的想法、看看某個新指標加進來對綜合分數有沒有增量價值，進「因子開發與篩選平台」。",
    hub_live_title: "即時儀表板",
    hub_live_desc: "今日綜合分數與因子走勢，互動時間軸，每日收盤後更新。",
    hub_platform_title: "因子開發與篩選平台",
    hub_platform_desc: "整合線上回測與歷史測試登記，快速驗證新因子的增量價值與可行性。",

    // Screening Page
    screening_title: "因子開發與篩選平台 · 債券市場恐懼貪婪",
    screening_card1_title: "➕ 輸入新因子進行驗證",
    form_token_summary: "🔑 設定 GitHub Personal Access Token (第一次使用必填)",
    form_token_hint: "填入授權 Token (具備 repo/workflow 權限)，安全儲存於本機瀏覽器 (localStorage)。",
    form_key_label: "因子英文代號 (Key)",
    form_key_placeholder: "例: vix_ma_dev",
    form_label_label: "因子中文名稱 (Label)",
    form_label_placeholder: "例: VIX 125日均線乖離率",
    form_mode_label: "轉換模式 (Mode)",
    form_window_label: "滾動視窗 (Window 天數)",
    form_source_a_label: "資料來源 (Source A)",
    form_source_placeholder: "打字搜尋，例如：十年期公債 / DGS10 / VIX",
    form_manual_toggle: "找不到？手動輸入類型與代號",
    form_invert_label: "數值反轉 (Invert Score) —— 勾選時數值越高得分越低（反向指標）",
    form_submit_btn: "🚀 提交驗證並即時呈現分析報告圖表",
    corr_card_title: "🔗 產生因子相關係數矩陣",
    corr_card_desc: "勾選想比較的因子（官方七項＋目前已升等的候選因子），產生兩兩相關係數熱力圖——用來看因子之間是不是在講同一件事（相關係數太高代表訊息重複、加進來邊際價值有限）。",
    corr_submit_btn: "📊 產生相關係數矩陣",
    reg_title: "歷史測試紀錄登記簿",
    reg_sub: "(點擊因子名稱可直接在下方展開報告圖表)",
    th_date: "測試日期",
    th_factor: "因子 (點擊名稱展開報告)",
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
    dash_subtitle: "A Quantitative Sentiment Framework for U.S. Treasury Markets",
    dash_caption: "Momentum, Copper/Gold — Equal-weighted average of 0–100 scores. View composite index first, then break down individual factor components below.",
    dash_latest_label: "Latest Composite Sentiment Score",
    dash_logic_btn: "Calculation Methodology & Credibility",
    dash_method_how: "<b>Calculation Methodology:</b> Composite Score = <b>equal-weighted arithmetic mean</b> of individual 0–100 factor scores. Missing items are automatically excluded. Sentiment Tiers: 0–24 Extreme Fear / 25–44 Fear / 45–55 Neutral / 56–75 Greed / 76–100 Extreme Greed.",
    dash_method_percentile: "<b>Rolling Percentiles (0–100 Scale):</b> Scores place today's raw value into a <b>rolling 5-year (1825-day) distribution</b>. A score of 98 indicates higher than 98% of trading days in the past 5 years. Formula: Score = (Days with Value ≤ Today) ÷ 1825 × 100.",
    dash_method_sources_title: "<b>Data Sources Detail:</b>",
    dash_method_th_field: "Field",
    dash_method_th_code: "Ticker",
    dash_method_th_source: "Source",
    dash_method_th_history: "History",
    dash_method_th_desc: "Description",
    dash_method_no_future: "<b>No Look-Ahead Bias:</b> All rolling calculations (125D MA, 40D Return, 5Y Percentile) strictly rely on historical data up to today.",
    dash_method_limits: "<b>Limitations:</b> This is a relative 5-year positioning index, not a predictive model. Extreme historical events rolling out after 5 years will shift percentile scores.",
    dash_custom_weight_title: "Custom Weights",
    dash_custom_weight_tag: "Research Mode",
    dash_custom_weight_explain: "What is this",
    dash_custom_weight_desc: "An interactive research tool: check factors & adjust sliders to explore custom weight combinations. <b>Does not override official equal-weighted scores</b>.",
    dash_custom_mode_label: "Enable Custom Mode (Overlays dashed line on timeline chart)",
    dash_history_title: "Composite Index Historical Timeline",
    dash_history_sub: "· Track U.S. Treasury sentiment peaks & troughs from 2020 to present. Click chart to inspect daily details.",
    dash_history_hint: "Daily closing calculations (not intraday). Click any chart to sync date across all components. Panning & zooming syncs synchronously across all charts.",
    dash_legend_score: "Composite Score (Equal-Weighted)",
    dash_legend_neutral: "50 Neutral Baseline",
    dash_legend_ust10: "10-Year Treasury Yield (%)",
    dash_legend_custom: "Custom Weight Composite Score",
    dash_components_title: "Factor Component Breakdown",
    dash_components_sub: "· Detailed calculation methodology & individual timeline charts",
    dash_footnote: "Data sources: Yahoo Finance (ZN=F, HG=F, GC=F daily closes), Treasury.gov (10Y Yield). Values strictly backward-looking without look-ahead bias.",

    // Dashboard Controls & Badges
    ctrl_drag_slider: "Drag timeline to select date",
    ctrl_jump_date: "Jump to date",
    ctrl_jump_latest: "Jump to Latest",
    ctrl_reset_zoom: "Reset Time Range",
    ctrl_zoom_hint: "Scroll to zoom / Shift+drag to box-select / Drag to pan / Double-click to reset",
    ctrl_show_events: "Show Event Lines (FOMC / CPI / NFP)",
    comp_prev_day: "1 Day Ago",
    comp_1w: "1 Week Ago",
    comp_1m: "1 Month Ago",
    comp_1y: "1 Year Ago",

    // Custom Weights
    cw_preset_placeholder: "Preset name, e.g. 'Copper-Gold Focus'",
    cw_preset_save: "Save Preset",
    cw_preset_hint: "Presets are saved locally in your browser storage (localStorage).",
    cw_apply_regime: "Apply Current Regime Weights",

    // Emotion Tiers
    tier_extreme_fear: "Extreme Fear",
    tier_fear: "Fear",
    tier_neutral: "Neutral",
    tier_greed: "Greed",
    tier_extreme_greed: "Extreme Greed",
    
    // Event Rail
    event_rail_title: "📅 Macro Event Calendar",
    event_rail_hint: "FOMC, CPI, NFP & major release dates. Click to sync timeline chart.",
    tab_all: "ALL",
    
    // Hub Page
    hub_title: "U.S. Bond Fear & Greed · Home",
    hub_lede: "Quantifying U.S. Treasury market sentiment into daily 0–100 scores with continuous factor discovery.",
    hub_intro_title: "About This Project",
    hub_intro_p1: "Inspired by CNN's stock market Fear & Greed Index, this quantitative framework applies sentiment analysis to the <b>U.S. Treasury Market</b>. Integrating Treasury yield momentum and Copper/Gold ratios, daily scores range from 0 (Extreme Fear / Risk-Off) to 100 (Extreme Greed / Risk-On).",
    hub_intro_p2: "Indicators are normalized to rolling 5-year percentiles (0–100) and averaged. This provides a historical sentiment baseline rather than a predictive trading model.",
    hub_intro_p3: "<b>Getting Started:</b> Explore live sentiment trends on the <b>Live Dashboard</b>, or test new quant factors on the <b>Factor Discovery Platform</b>.",
    hub_live_title: "Live Dashboard",
    hub_live_desc: "Daily composite score, factor component trends & interactive timeline.",
    hub_platform_title: "Factor Discovery Platform",
    hub_platform_desc: "Backtesting & registry framework for verifying incremental factor value.",

    // Screening Page
    screening_title: "Factor Discovery & Screening Platform",
    screening_card1_title: "➕ Submit New Candidate Factor for Verification",
    form_token_summary: "🔑 Set GitHub Personal Access Token (PAT Required)",
    form_token_hint: "Enter authorized PAT (repo/workflow permissions). Saved securely in local browser storage.",
    form_key_label: "Factor Key (English)",
    form_key_placeholder: "e.g. vix_ma_dev",
    form_label_label: "Factor Name (Display Label)",
    form_label_placeholder: "e.g. VIX 125D MA Deviation",
    form_mode_label: "Transformation Mode",
    form_window_label: "Rolling Window (Days)",
    form_source_a_label: "Data Source A",
    form_source_placeholder: "Search name or symbol, e.g. 10Y Treasury / DGS10 / VIX",
    form_manual_toggle: "Can't find? Enter type & symbol manually",
    form_invert_label: "Invert Score (Check when higher raw value indicates Fear)",
    form_submit_btn: "🚀 Submit Factor Verification & Render Report",
    corr_card_title: "🔗 Generate Factor Correlation Matrix",
    corr_card_desc: "Select factors to calculate pairwise correlation heatmaps and evaluate information overlap.",
    corr_submit_btn: "📊 Generate Correlation Matrix",
    reg_title: "Historical Factor Test Registry",
    reg_sub: "(Click factor name to expand analysis report below)",
    th_date: "Test Date",
    th_factor: "Factor (Click to Expand)",
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
    if (dict[key]) {
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
        '<button class="lang-toggle-btn" id="langToggleBtn" type="button" onclick="toggleLanguage()">'
        '<span class="lang-icon">🌐</span>'
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
