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

nav本身固定own max-width、置中、四角全圓角、非sticky(跟著頁面內容捲動，不吸在頂端)——
故意不吃各頁面`.wrap`/`.viz-root`自己的max-width，不然同一份nav在不同頁面上會看起來
寬度不一致。

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
.site-topnav {
  display: flex; justify-content: center; gap: 6px; flex-wrap: wrap; align-items: center;
  width: fit-content; margin: 0 auto 28px; padding: 6px 10px; border-radius: 999px;
  background: rgba(255, 255, 255, 0.92); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px);
  border: 1px solid #dfe2e8; box-shadow: 0 2px 8px rgba(22,26,35,0.05), 0 1px 2px rgba(22,26,35,0.03);
  transition: transform 0.25s ease, box-shadow 0.25s ease;
}
.site-topnav a, .site-topnav span.active {
  color: #4a5568; text-decoration: none; font-weight: 600; font-size: 13px;
  padding: 7px 18px; border-radius: 999px; white-space: nowrap;
  transition: all 0.22s cubic-bezier(0.16, 1, 0.3, 1);
  display: inline-flex; align-items: center; justify-content: center;
}
.site-topnav a:hover {
  background: rgba(30,58,95,0.08); color: #1e3a5f;
  transform: translateY(-1px) scale(1.02);
}
.site-topnav a:active { transform: scale(0.97); }
.site-topnav span.active { color: #1e3a5f; background: rgba(30,58,95,0.12); font-weight: 700; }

.lang-toggle-btn {
  display: inline-flex; align-items: center; gap: 4px;
  background: var(--surface-2, #f8f9fb); border: 1px solid var(--border, #dfe2e8);
  color: var(--text-secondary, #4a5568); font-size: 12px; font-weight: 700;
  padding: 5px 12px; border-radius: 999px; cursor: pointer;
  margin-left: 6px; transition: all 0.22s cubic-bezier(0.16, 1, 0.3, 1);
  outline: none;
}
.lang-toggle-btn:hover {
  background: var(--surface-1, #ffffff); color: var(--series-1, #1e3a5f); border-color: var(--axis, #a7adb9);
  transform: translateY(-1px) scale(1.03); box-shadow: 0 2px 6px rgba(22,26,35,0.06);
}
.lang-toggle-btn:active { transform: scale(0.96); }
.lang-icon { font-size: 12px; }

@media (prefers-color-scheme: dark) {
  .site-topnav { background: rgba(23, 27, 36, 0.92); border-color: #2c313d; box-shadow: 0 4px 16px rgba(0,0,0,0.30); }
  .site-topnav a, .site-topnav span.active { color: #b8c0cc; }
  .site-topnav a:hover { background: rgba(126,163,207,0.12); color: #7ea3cf; transform: translateY(-1px) scale(1.02); }
  .site-topnav span.active { color: #7ea3cf; background: rgba(126,163,207,0.18); }
  .lang-toggle-btn { background: #1e232d; border-color: #2c313d; color: #b8c0cc; }
  .lang-toggle-btn:hover { background: #171b24; color: #7ea3cf; border-color: #4a5164; }
}
:root[data-theme="dark"] .site-topnav { background: rgba(23, 27, 36, 0.92); border-color: #2c313d; box-shadow: 0 4px 16px rgba(0,0,0,0.30); }
:root[data-theme="dark"] .site-topnav a, :root[data-theme="dark"] .site-topnav span.active { color: #b8c0cc; }
:root[data-theme="dark"] .site-topnav a:hover { background: rgba(126,163,207,0.12); color: #7ea3cf; transform: translateY(-1px) scale(1.02); }
:root[data-theme="dark"] .site-topnav span.active { color: #7ea3cf; background: rgba(126,163,207,0.18); }
:root[data-theme="dark"] .lang-toggle-btn { background: #1e232d; border-color: #2c313d; color: #b8c0cc; }
:root[data-theme="dark"] .lang-toggle-btn:hover { background: #171b24; color: #7ea3cf; border-color: #4a5164; }

:root[data-theme="light"] .site-topnav { background: rgba(255, 255, 255, 0.92); border-color: #dfe2e8; box-shadow: 0 2px 8px rgba(22,26,35,0.05); }
:root[data-theme="light"] .site-topnav a, :root[data-theme="light"] .site-topnav span.active { color: #4a5568; }
:root[data-theme="light"] .site-topnav a:hover { background: rgba(30,58,95,0.08); color: #1e3a5f; transform: translateY(-1px) scale(1.02); }
:root[data-theme="light"] .site-topnav span.active { color: #1e3a5f; background: rgba(30,58,95,0.12); }
:root[data-theme="light"] .lang-toggle-btn { background: #f8f9fb; border-color: #dfe2e8; color: #4a5568; }
:root[data-theme="light"] .lang-toggle-btn:hover { background: #ffffff; color: #1e3a5f; border-color: #a7adb9; }
"""

LANG_TOGGLE_JS = """
const I18N_DICT = {
  zh: {
    nav_hub: "首頁",
    nav_dashboard: "儀表板",
    nav_screening: "因子開發與篩選平台",
    lang_btn: "EN",
    
    // Dashboard
    dash_title: "債券市場恐懼貪婪儀表板",
    dash_subtitle: "A Quantitative Sentiment Framework for U.S. Treasury Markets",
    dash_latest_label: "最新收盤日綜合分數",
    dash_logic_btn: "ⓘ 綜合分數的計算邏輯與可信度",
    dash_custom_weight_title: "自訂權重",
    dash_custom_weight_tag: "研究用",
    dash_custom_weight_explain: "ⓘ 這是什麼",
    dash_custom_mode_label: "啟用自訂模式（在下方走勢圖疊加一條虛線）",
    dash_history_title: "綜合指數歷史時間軸",
    dash_history_explain: "ⓘ 這張圖怎麼讀",
    dash_components_title: "分項拆解",
    
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
    
    // Hub
    hub_title: "債券市場恐懼貪婪 · 專案首頁",
    hub_lede: "項美債市場指標彙整成每日恐懼貪婪分數，配套因子開發與篩選平台可持續擴充。同一份定義來源(factor_definitions.json)驅動儀表板與各項計算。",
    hub_intro_title: "這是什麼",
    hub_live_title: "即時儀表板",
    hub_platform_title: "因子開發與篩選平台",

    // Screening
    screening_title: "因子開發與篩選平台 · 債券市場恐懼貪婪",
    reg_title: "歷史測試紀錄登記簿",
    filter_all: "全部",
    filter_keep: "通過",
    filter_watch: "觀察",
    filter_cut: "淘汰",
    filter_promoted: "已升等"
  },
  en: {
    nav_hub: "Home",
    nav_dashboard: "Dashboard",
    nav_screening: "Factor Platform",
    lang_btn: "繁中",
    
    // Dashboard
    dash_title: "U.S. Bond Fear & Greed Dashboard",
    dash_subtitle: "A Quantitative Sentiment Framework for U.S. Treasury Markets",
    dash_latest_label: "Latest Composite Sentiment Score",
    dash_logic_btn: "ⓘ Calculation Methodology & Credibility",
    dash_custom_weight_title: "Custom Weights",
    dash_custom_weight_tag: "Research Mode",
    dash_custom_weight_explain: "ⓘ What is this",
    dash_custom_mode_label: "Enable Custom Overlay (Overlays dashed line on chart)",
    dash_history_title: "Composite Index Historical Timeline",
    dash_history_explain: "ⓘ How to read this chart",
    dash_components_title: "Factor Component Breakdown",
    
    // Emotion Tiers
    tier_extreme_fear: "Extreme Fear",
    tier_fear: "Fear",
    tier_neutral: "Neutral",
    tier_greed: "Greed",
    tier_extreme_greed: "Extreme Greed",
    
    // Event Rail
    event_rail_title: "📅 Macro Event Calendar",
    event_rail_hint: "FOMC, CPI, NFP & major economic dates. Click to sync timeline chart.",
    tab_all: "ALL",
    
    // Hub
    hub_title: "U.S. Bond Fear & Greed · Home",
    hub_lede: "Quantifying U.S. Treasury market sentiment into daily 0-100 scores with continuous factor discovery.",
    hub_intro_title: "About This Project",
    hub_live_title: "Live Dashboard",
    hub_platform_title: "Factor Discovery Platform",

    // Screening
    screening_title: "Factor Discovery & Screening Platform",
    reg_title: "Historical Factor Test Registry",
    filter_all: "ALL",
    filter_keep: "PASS",
    filter_watch: "WATCH",
    filter_cut: "CUT",
    filter_promoted: "PROMOTED"
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
      el.textContent = dict[key];
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
    """active_key: 'hub' | 'dashboard' | 'report' | 'manual' | 'screening'"""
    links = _load_link_overrides(base_dir)
    items = []
    for key, label, _ in PAGES:
        if key == active_key:
            items.append(f'<span class="active" aria-current="page" data-i18n="nav_{key}">{label}</span>')
        else:
            items.append(f'<a href="{links[key]}" data-i18n="nav_{key}">{label}</a>')
    
    # 加入中英切換按鈕
    lang_btn = (
        '<button class="lang-toggle-btn" id="langToggleBtn" type="button" onclick="toggleLanguage()">'
        '<span class="lang-icon">🌐</span>'
        '<span class="lang-text" id="langToggleText">EN</span>'
        '</button>'
    )
    items.append(lang_btn)
    return f'<nav class="site-topnav">{"".join(items)}</nav>'

