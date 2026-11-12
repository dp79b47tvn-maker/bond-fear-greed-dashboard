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
from factor_defs_schema import validate_and_load

BASE = __file__.rsplit("/", 1)[0]

DEFS = validate_and_load()
with open(f"{BASE}/artifact_urls.json", encoding="utf-8") as f:
    URLS = json.load(f)

link_dashboard = URLS.get("dashboard") or "dashboard.html"

factor_count = len(DEFS["factors"])

# ---- 今日分數：讀儀表板已產生的 dashboard_data.json(CI 先跑 update_dashboard.py 再跑這支)。
# 首頁第一屏直接給訪客看今天的分數跟近一年走勢，而不是只有文字介紹。檔案不存在就整段不顯示。
TIER_KEYS = {"極度恐懼": ("tier_extreme_fear", "tier-extreme-fear"), "恐懼": ("tier_fear", "tier-fear"),
             "中性": ("tier_neutral", "tier-neutral"), "貪婪": ("tier_greed", "tier-greed"),
             "極度貪婪": ("tier_extreme_greed", "tier-extreme-greed")}


def _tier_of(score):
    if score < 25:
        return "極度恐懼"
    if score < 45:
        return "恐懼"
    if score < 56:
        return "中性"
    if score < 76:
        return "貪婪"
    return "極度貪婪"


def _today_block():
    try:
        with open(f"{BASE}/chart/dashboard_data.json", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return ""
    pts = [d for d in data if d.get("score") is not None]
    if not pts:
        return ""
    last = pts[-1]
    tier = last.get("label") or _tier_of(last["score"])
    i18n_key, tier_var = TIER_KEYS.get(tier, ("tier_neutral", "tier-neutral"))
    # 近一年(約 252 個交易日)的分數走勢小圖；y 軸固定 0–100，畫 50 分中線。
    recent = pts[-252:]
    W, H = 320, 72
    n = len(recent)
    xs = [i * W / max(1, n - 1) for i in range(n)]
    ys = [H - d["score"] / 100 * H for d in recent]
    path = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    first_date, last_date = recent[0]["date"], recent[-1]["date"]
    return f"""
  <section class="today" aria-labelledby="todayTitle">
    <div class="today-score">
      <h2 id="todayTitle" class="today-label" data-i18n="dash_latest_label">最新收盤日綜合分數</h2>
      <div class="today-num" style="color:var(--{tier_var})">{last["score"]:.1f}</div>
      <div class="today-tier" style="color:var(--{tier_var})" data-i18n="{i18n_key}">{tier}</div>
      <div class="today-date">{last["date"]}</div>
    </div>
    <figure class="today-spark">
      <svg viewBox="0 0 {W} {H}" preserveAspectRatio="none" role="img" aria-label="近一年綜合分數走勢，{first_date} 到 {last_date}">
        <line x1="0" x2="{W}" y1="{H / 2}" y2="{H / 2}" class="spark-mid"/>
        <path d="{path}" class="spark-line" vector-effect="non-scaling-stroke"/>
      </svg>
      <figcaption><span>{first_date}</span><span data-i18n="hub_spark_caption">0–100，虛線為 50 分</span><span>{last_date}</span></figcaption>
    </figure>
    <a class="today-link" href="{link_dashboard}"><span data-i18n="hub_live_title">即時儀表板</span> →</a>
  </section>"""


hub_html = f"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{page_style.FAVICON_TAG}
<title>債券市場恐懼貪婪指數</title>
<style>
  {page_style.ROOT_COLORS_CSS}
  {nav_bar.NAV_BAR_CSS}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; line-height:{page_style.BASE_LINE_HEIGHT}; }}
  .wrap {{ max-width:{page_style.CONTENT_MAX_WIDTH}; margin:0 auto; padding:36px 24px 64px; }}
  .site-topnav {{ max-width:{page_style.CONTENT_MAX_WIDTH}; }}
  h1 {{ font-size:{page_style.H1_SIZE}; font-weight:700; margin:0 0 8px; letter-spacing:-.015em; line-height:1.25; }}
  .lede {{ color:var(--text-secondary); max-width:{page_style.LEDE_MAX_WIDTH}; margin:0 0 28px; font-size:16px; }}

  .today {{ display:grid; grid-template-columns:auto 1fr; grid-template-rows:auto auto; gap:8px 32px; align-items:end;
    padding:20px 0 18px; border-top:2px solid var(--text-primary); border-bottom:1px solid var(--rule); margin-bottom:36px; }}
  .today-score {{ grid-row:1 / span 2; }}
  .today-label {{ font-size:13px; font-weight:600; color:var(--text-secondary); margin:0 0 2px; }}
  .today-num {{ font-size:56px; font-weight:700; line-height:1; letter-spacing:-.02em; }}
  .today-tier {{ font-size:17px; font-weight:700; margin-top:4px; }}
  .today-date {{ font-size:12.5px; color:var(--text-muted); margin-top:2px; }}
  .today-spark {{ margin:0; min-width:0; }}
  .today-spark svg {{ width:100%; height:72px; display:block; overflow:visible; }}
  .spark-line {{ fill:none; stroke:var(--series-1); stroke-width:1.6; stroke-linejoin:round; }}
  .spark-mid {{ stroke:var(--axis); stroke-width:1; stroke-dasharray:3 3; vector-effect:non-scaling-stroke; }}
  .today-spark figcaption {{ display:flex; justify-content:space-between; gap:8px; font-size:11.5px; color:var(--text-muted); margin-top:4px; }}
  .today-link {{ justify-self:end; font-size:14px; font-weight:700; text-decoration:none; }}
  .today-link:hover {{ text-decoration:underline; text-underline-offset:3px; }}

  .intro {{ margin-bottom:32px; max-width:{page_style.LEDE_MAX_WIDTH}; }}
  .intro h2 {{ font-size:19px; font-weight:700; margin:0 0 10px; }}
  .intro p {{ font-size:15px; color:var(--text-secondary); line-height:1.8; margin:0 0 12px; }}
  .intro p:last-child {{ margin-bottom:0; }}
  .intro b {{ color:var(--text-primary); }}

  .entries {{ display:grid; grid-template-columns:1fr 1fr; border-top:1px solid var(--rule); border-bottom:1px solid var(--rule); }}
  a.entry {{ display:block; padding:18px 20px 18px 0; text-decoration:none; color:var(--text-primary); }}
  a.entry + a.entry {{ padding-left:20px; border-left:1px solid var(--rule); }}
  a.entry h2 {{ font-size:18px; margin:0 0 6px; color:var(--accent); }}
  a.entry h2::after {{ content:" →"; }}
  a.entry p {{ font-size:14px; color:var(--text-secondary); margin:0; }}
  a.entry:hover h2 {{ text-decoration:underline; text-underline-offset:3px; }}
  .foot {{ font-size:12.5px; color:var(--text-muted); margin-top:28px; }}

  @media (max-width: 640px) {{
    .wrap {{ padding:24px 16px 48px; }}
    h1 {{ font-size:25px; }}
    .today {{ grid-template-columns:1fr; }}
    .today-score {{ grid-row:auto; }}
    .today-num {{ font-size:48px; }}
    .today-link {{ justify-self:start; }}
    .entries {{ grid-template-columns:1fr; }}
    a.entry {{ padding:16px 0; }}
    a.entry + a.entry {{ padding-left:0; border-left:none; border-top:1px solid var(--rule); }}
  }}
</style>
{nav_bar.render_nav_bar("hub")}
<div class="wrap">
  <h1 data-i18n="hub_title">債券市場恐懼貪婪指數</h1>
  <p class="lede" data-i18n="hub_lede">把美國公債市場的指標換算成每天 0 到 100 的恐懼貪婪分數，每個交易日收盤後更新。公式跟資料來源都寫在儀表板上，可以自己驗算。</p>
  {_today_block()}
  <section class="intro">
    <h2 data-i18n="hub_intro_title">這是什麼</h2>
    <p data-i18n="hub_intro_p1" data-i18n-html>恐懼貪婪指數的概念來自 CNN 的股市版：用一組市場指標算出 0 到 100 的分數。分數越低，市場越偏向避險；越高，越願意承擔風險。這裡把同一套做法用在<b>美國公債市場</b>，目前採用殖利率動能跟銅金比，每個交易日收盤後重算。</p>
    <p data-i18n="hub_intro_p2" data-i18n-html>每項指標先換算成它在過去 5 年裡的百分位（0 到 100），再取平均。分數說的是跟近 5 年比，現在的情緒偏向哪一端。<b>它不是預測模型，也不是投資建議。</b></p>
    <p data-i18n="hub_intro_p3" data-i18n-html>想看今天的分數跟歷史走勢，到「即時儀表板」。想測試某個新指標加進來對綜合分數有沒有幫助，到「因子開發與篩選平台」。</p>
  </section>
  <nav class="entries" aria-label="主要頁面">
    <a class="entry" href="{link_dashboard}">
      <h2 data-i18n="hub_live_title">即時儀表板</h2>
      <p data-i18n="hub_live_desc">今天的綜合分數、各因子走勢跟可以拖曳的時間軸，每個交易日收盤後更新。</p>
    </a>
    <a class="entry" href="screening_index.html">
      <h2 data-i18n="hub_platform_title">因子開發與篩選平台</h2>
      <p data-i18n="hub_platform_desc">輸入新因子跑關卡檢驗跟回測，每次結果都留在登記簿；也可以產生因子之間的相關係數矩陣。</p>
    </a>
  </nav>
  <p class="foot">頁面更新於 {date.today().isoformat()}</p>
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
