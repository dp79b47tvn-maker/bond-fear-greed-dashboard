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
    ("screening", "因子篩選平台", "screening_index.html"),
]

NAV_BAR_CSS = """
.site-topnav {
  display: flex; justify-content: space-between; gap: 2px; flex-wrap: wrap; align-items: center;
  max-width: 920px; margin: 0 auto 28px; padding: 10px 18px; border-radius: 14px;
  background: #ffffff; border: 1px solid #dfe2e8; box-shadow: 0 1px 2px rgba(22,26,35,0.06);
}
.site-topnav a, .site-topnav span.active {
  color: #4a5568; text-decoration: none; font-weight: 600; font-size: 13px;
  padding: 8px 12px; border-radius: 8px; white-space: nowrap;
}
.site-topnav a:hover { background: rgba(30,58,95,0.08); color: #1e3a5f; }
.site-topnav span.active { color: #1e3a5f; background: rgba(30,58,95,0.1); }
@media (prefers-color-scheme: dark) {
  .site-topnav { background: #171b24; border-color: #2c313d; box-shadow: 0 1px 2px rgba(0,0,0,0.35); }
  .site-topnav a, .site-topnav span.active { color: #b8c0cc; }
  .site-topnav a:hover { background: rgba(126,163,207,0.12); color: #7ea3cf; }
  .site-topnav span.active { color: #7ea3cf; background: rgba(126,163,207,0.16); }
}
:root[data-theme="dark"] .site-topnav { background: #171b24; border-color: #2c313d; box-shadow: 0 1px 2px rgba(0,0,0,0.35); }
:root[data-theme="dark"] .site-topnav a, :root[data-theme="dark"] .site-topnav span.active { color: #b8c0cc; }
:root[data-theme="dark"] .site-topnav a:hover { background: rgba(126,163,207,0.12); color: #7ea3cf; }
:root[data-theme="dark"] .site-topnav span.active { color: #7ea3cf; background: rgba(126,163,207,0.16); }
:root[data-theme="light"] .site-topnav { background: #ffffff; border-color: #dfe2e8; box-shadow: 0 1px 2px rgba(22,26,35,0.06); }
:root[data-theme="light"] .site-topnav a, :root[data-theme="light"] .site-topnav span.active { color: #4a5568; }
:root[data-theme="light"] .site-topnav a:hover { background: rgba(30,58,95,0.08); color: #1e3a5f; }
:root[data-theme="light"] .site-topnav span.active { color: #1e3a5f; background: rgba(30,58,95,0.1); }
"""


def _load_link_overrides(base_dir="."):
    """讀 artifact_urls.json 取得跨頁連結覆寫(目前全部留空、一律退回同資料夾相對路徑，
    這是GitHub Pages正式站的運作方式；保留這個機制只是跟現有四支腳本的既有慣例一致)。"""
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
            items.append(f'<span class="active" aria-current="page">{label}</span>')
        else:
            items.append(f'<a href="{links[key]}">{label}</a>')
    return f'<nav class="site-topnav">{"".join(items)}</nav>'
