# -*- coding: utf-8 -*-
"""從 factor_definitions.json 自動生成專案首頁 chart/index.html。

2026-07-30前叫generate_manual.py，同時也產生chart/manual.html(定義手冊)；手冊頁
已經拿掉(內容折回儀表板各分項卡片的說明面板，互動試算器直接移除，見AGENTS.md)，
這支現在只剩首頁職責，改名反映實際用途。

用法:
    python3 generate_hub.py

跨頁連結:讀 artifact_urls.json 取得儀表板的發布網址;
本機瀏覽時也可以直接用相對路徑開啟 chart/ 下的其他頁面。
"""
import json
from datetime import date

import nav_bar
import page_style

BASE = __file__.rsplit("/", 1)[0]

with open(f"{BASE}/factor_definitions.json", encoding="utf-8") as f:
    DEFS = json.load(f)
with open(f"{BASE}/artifact_urls.json", encoding="utf-8") as f:
    URLS = json.load(f)

link_dashboard = URLS.get("dashboard") or "dashboard.html"

factor_count = len(DEFS["factors"])
hub_html = f"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>債券市場恐懼貪婪 · 專案首頁</title>
<style>
  {page_style.ROOT_COLORS_CSS}
  {nav_bar.NAV_BAR_CSS}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--page); color:var(--text-primary); line-height:{page_style.BASE_LINE_HEIGHT};
    font-family:{page_style.FONT_FAMILY}; }}
  .wrap {{ max-width:{page_style.CONTENT_MAX_WIDTH}; margin:0 auto; padding:44px 24px 70px; }}
  .kicker {{ font-family:ui-monospace,"SF Mono",Menlo,monospace; font-size:11px; letter-spacing:.12em; color:var(--series-2); font-weight:700; margin-bottom:10px; }}
  h1 {{ font-size:{page_style.H1_SIZE}; font-weight:700; margin:0 0 10px; letter-spacing:-.02em; }}
  .lede {{ color:var(--text-secondary); max-width:{page_style.LEDE_MAX_WIDTH}; margin:0 0 30px; }}
  .intro {{ margin-bottom:36px; padding-bottom:32px; border-bottom:1px solid var(--border); }}
  .intro h2 {{ font-size:15px; font-weight:700; margin:0 0 12px; color:var(--text-primary); }}
  .intro p {{ font-size:14px; color:var(--text-secondary); line-height:1.8; margin:0 0 12px; }}
  .intro p:last-child {{ margin-bottom:0; }}
  .intro b {{ color:var(--text-primary); }}
  .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:16px; }}
  a.card {{ display:block; background:var(--surface-1); border:1px solid var(--border); border-radius:16px;
    padding:24px 24px 20px; text-decoration:none; color:var(--text-primary); box-shadow:var(--shadow);
    transition:transform .25s cubic-bezier(0.16, 1, 0.3, 1), box-shadow .25s ease, border-color .25s ease; }}
  a.card:hover {{ transform:translateY(-3px) scale(1.005); box-shadow:var(--shadow-hover); border-color:var(--series-1); }}
  a.card:active {{ transform:scale(0.98); }}
  .card .ck {{ font-family:ui-monospace,"SF Mono",Menlo,monospace; font-size:10.5px; letter-spacing:.1em; color:var(--series-1); font-weight:700; }}
  .card h2 {{ font-size:18px; margin:6px 0 8px; }}
  .card p {{ font-size:13px; color:var(--text-secondary); margin:0; }}
  .foot {{ font-size:12px; color:var(--text-muted); margin-top:34px; line-height:1.7; }}
  .mono {{ font-family:ui-monospace,"SF Mono",Menlo,monospace; }}

  /* 區塊漸進式入場動畫 */
  @keyframes fadeUp {{
    from {{ opacity: 0; transform: translateY(12px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
  }}
  .animate-in {{ animation: fadeUp 0.45s cubic-bezier(0.16, 1, 0.3, 1) both; }}
  .animate-delay-1 {{ animation-delay: 0.08s; }}
  .animate-delay-2 {{ animation-delay: 0.16s; }}
  @media (prefers-reduced-motion: reduce) {{
    * {{ transition-duration: 0.001ms !important; animation-duration: 0.001ms !important; }}
  }}
</style>
<div class="wrap">
  {nav_bar.render_nav_bar("hub")}
  <div class="kicker animate-in">BOND MARKET FEAR &amp; GREED</div>
  <h1 class="animate-in animate-delay-1" data-i18n="hub_title">債券市場恐懼貪婪 · 專案首頁</h1>
  <p class="lede animate-in animate-delay-1">{factor_count}項美債市場指標彙整成每日恐懼貪婪分數,配套因子開發與篩選平台可持續擴充。同一份定義來源(factor_definitions.json)驅動儀表板與各項計算。</p>
  <section class="intro animate-in animate-delay-2">
    <h2 data-i18n="hub_intro_title">這是什麼</h2>
    <p>「恐懼貪婪指數」的概念來自CNN的股市版——用一組市場指標算出0到100的分數，越低代表市場情緒越「恐懼」（避險為主、風險偏好降低），越高代表越「貪婪」（風險偏好升溫）。這個專案把同樣的方法論套用在<b>美國公債市場</b>上：整合殖利率動能、銅金比反映的景氣/風險偏好等{factor_count}項指標，每個交易日收盤後重新計算一次。</p>
    <p>每項指標都換算成「跟過去5年比起來排第幾百分位」的0–100分數，再取平均——這是「相對於近期歷史，市場現在情緒偏向哪一端」的參考尺，<b>不是預測模型、也不是投資建議</b>。</p>
    <p><b>怎麼開始：</b>想看今天的分數跟歷史走勢，進「即時儀表板」；想測試自己的想法、看看某個新指標加進來對綜合分數有沒有增量價值，進「因子開發與篩選平台」。</p>
  </section>
  <div class="cards animate-in animate-delay-2">
    <a class="card" href="{link_dashboard}">
      <div class="ck">LIVE DASHBOARD</div>
      <h2 data-i18n="hub_live_title">即時儀表板</h2>
      <p>今日綜合分數與{factor_count}項因子走勢,互動時間軸,每日收盤後更新。</p>
    </a>
    <a class="card" href="screening_index.html">
      <div class="ck">FACTOR DISCOVERY &amp; SCREENING</div>
      <h2 data-i18n="hub_platform_title">因子開發與篩選平台</h2>
      <p>整合線上回測與歷史測試登記，快速驗證新因子的增量價值與可行性，也能隨選產生因子相關係數矩陣。</p>
    </a>
  </div>
  <p class="foot">更新方式:<span class="mono">python3 update_dashboard.py</span>(儀表板) · <span class="mono">python3 generate_hub.py</span>(本頁)。<br>生成日期 {date.today().isoformat()}。</p>
</div>
<script>
  {nav_bar.LANG_TOGGLE_JS}
</script>
"""
def main():
    with open(f"{BASE}/chart/index.html", "w", encoding="utf-8") as f:
        f.write(hub_html)
    print(f"已生成 chart/index.html（{len(hub_html)/1024:.0f} KB）")


if __name__ == "__main__":
    main()
