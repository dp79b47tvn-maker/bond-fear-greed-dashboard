# -*- coding: utf-8 -*-
"""從 factor_definitions.json 自動生成定義手冊 chart/manual.html。

單一事實來源架構的一環:手冊內容(參數、公式、說明文字)全部來自定義檔,
改了定義檔重跑這支就同步;不存在「文件跟程式講不同數字」的可能。

用法:
    python3 generate_manual.py

跨頁連結:讀 artifact_urls.json 取得儀表板/驗證報告的發布網址;
本機瀏覽時也可以直接用相對路徑開啟 chart/ 下的其他頁面。
"""
import json
import re
from datetime import date

BASE = __file__.rsplit("/", 1)[0]

with open(f"{BASE}/factor_definitions.json", encoding="utf-8") as f:
    DEFS = json.load(f)
with open(f"{BASE}/artifact_urls.json", encoding="utf-8") as f:
    URLS = json.load(f)

G = DEFS["global"]
V = DEFS["validation"]


def sub_tokens(text, params):
    """把 {token} 換成 params/global 的同名值。用regex避免str.format被文字裡的大括號干擾。"""
    merged = {**G, **params}
    return re.sub(r"\{(\w+)\}", lambda m: str(merged.get(m.group(1), m.group(0))), text)


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


link_dashboard = URLS.get("dashboard") or "dashboard.html"
link_report = URLS.get("report") or "factor_validation_report.html"
link_hub = URLS.get("hub") or "index.html"

# ---------------- 因子區塊 ----------------
factor_sections = []
toc_items = []
for fx in DEFS["factors"]:
    p = fx["params"]
    name = sub_tokens(fx["name_tpl"], p)
    formula = sub_tokens(fx["formula_tpl"], p)
    explain = sub_tokens(fx["explain_tpl"], p)
    tuning = sub_tokens(fx.get("tuning_note", ""), p)
    toc_items.append(f'<a href="#factor-{fx["key"]}">{name.split(" — ")[0]}</a>')
    param_rows = "".join(
        f"<tr><td class='mono'>{k}</td><td class='num'>{v}</td></tr>" for k, v in p.items()
    ) or "<tr><td colspan='2' class='muted'>無數值參數</td></tr>"
    factor_sections.append(f"""
  <section class="card" id="factor-{fx['key']}">
    <div class="kicker">{fx['kicker']}</div>
    <h2>{name}</h2>
    <div class="grid2">
      <div>
        <h3>公式</h3>
        <p class="formula">{formula}</p>
        <h3>可調參數 <span class="tag">改這裡=改行為</span></h3>
        <table class="ptable"><tr><th>參數</th><th>現值</th></tr>{param_rows}</table>
        <p class="hint">{tuning}</p>
        <h3>屬性</h3>
        <p class="hint">走百分位:{'是' if fx['uses_percentile'] else '否(直接算區間位置)'}　·　反轉(100−):{'是' if fx['invert'] else '否'}<br>
        原始輸入:{', '.join(fx['inputs'])}<br>
        程式位置:<span class="mono">{fx['code_location']}</span></p>
      </div>
      <div>
        <h3>完整說明(與儀表板同步)</h3>
        <div class="explain">{explain}</div>
      </div>
    </div>
    <p class="crosslink">
      <a href="{link_dashboard}">→ 在儀表板看此因子的即時分數與走勢</a>　·
      <a href="{link_report}">→ 在驗證報告看此因子的IC/分桶/回測</a>
    </p>
  </section>""")

# ---------------- 資料來源表 ----------------
src_rows = "".join(
    f"<tr><td class='mono'>{s['column']}</td><td class='mono'>{s['ticker']}</td>"
    f"<td>{s['source']}</td><td>{s['earliest']}</td><td>{s['note']}</td></tr>"
    for s in DEFS["data_sources"]
)

# ---------------- 分級門檻表 ----------------
prev = 0
th_rows = ""
for th in G["label_thresholds"]:
    hi = min(th["lt"] - 1, 100)
    th_rows += f"<tr><td class='num'>{prev} – {hi}</td><td>{th['label']}</td></tr>"
    prev = th["lt"]

# ---------------- 可調參數總覽 ----------------
tune_rows = ""
for fx in DEFS["factors"]:
    for k, v in fx["params"].items():
        tune_rows += (f"<tr><td>{sub_tokens(fx['name_tpl'], fx['params']).split(' — ')[0]}</td>"
                      f"<td class='mono'>{k}</td><td class='num'>{v}</td>"
                      f"<td>{sub_tokens(fx.get('tuning_note',''), fx['params'])}</td></tr>")
tune_rows += (f"<tr><td>全域</td><td class='mono'>percentile_window_days</td><td class='num'>{G['percentile_window_days']}</td>"
              f"<td>百分位比較基準期間。改小→更敏感;改大→更平滑。</td></tr>")
tune_rows += (f"<tr><td>驗證</td><td class='mono'>horizons</td><td class='num'>{V['horizons']}</td>"
              f"<td>IC看未來幾天報酬。</td></tr>")
tune_rows += (f"<tr><td>驗證</td><td class='mono'>dead_zone</td><td class='num'>{tuple(V['dead_zone'])}</td>"
              f"<td>回測中性死區,區間內強制空手。</td></tr>")

html = f"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>因子定義手冊 · 債券市場恐懼貪婪</title>
<style>
  :root {{
    --page:#f4f5f7; --surface-1:#ffffff; --surface-2:#f8f9fb;
    --text-primary:#161a23; --text-secondary:#4a5568; --text-muted:#667085;
    --grid:#e5e7eb; --axis:#a7adb9; --accent:#1e3a5f; --accent2:#a6742a;
    --border:#dfe2e8; --shadow:0 1px 2px rgba(22,26,35,0.04);
    --input:#dbeafe; --result:#dcfce7;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --page:#0f1218; --surface-1:#171b24; --surface-2:#1e232d;
      --text-primary:#f1f3f6; --text-secondary:#b8c0cc; --text-muted:#8b93a3;
      --grid:#262b36; --axis:#4a5164; --accent:#7ea3cf; --accent2:#d9a860;
      --border:#2c313d; --shadow:0 1px 2px rgba(0,0,0,0.35);
      --input:#1e3a5f; --result:#1e3a2b; }}
  }}
  :root[data-theme="dark"] {{ --page:#0f1218; --surface-1:#171b24; --surface-2:#1e232d;
    --text-primary:#f1f3f6; --text-secondary:#b8c0cc; --text-muted:#8b93a3;
    --grid:#262b36; --axis:#4a5164; --accent:#7ea3cf; --accent2:#d9a860;
    --border:#2c313d; --shadow:0 1px 2px rgba(0,0,0,0.35);
    --input:#1e3a5f; --result:#1e3a2b; }}
  :root[data-theme="light"] {{ --page:#f4f5f7; --surface-1:#ffffff; --surface-2:#f8f9fb;
    --text-primary:#161a23; --text-secondary:#4a5568; --text-muted:#667085;
    --grid:#e5e7eb; --axis:#a7adb9; --accent:#1e3a5f; --accent2:#a6742a;
    --border:#dfe2e8; --shadow:0 1px 2px rgba(22,26,35,0.04);
    --input:#dbeafe; --result:#dcfce7; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--page); color:var(--text-primary); line-height:1.7;
    font-family:-apple-system,BlinkMacSystemFont,"PingFang TC","Noto Sans TC","Segoe UI",Roboto,sans-serif; }}
  .wrap {{ max-width:1080px; margin:0 auto; padding:40px 24px 70px; }}
  .topnav {{ display:flex; gap:16px; flex-wrap:wrap; font-size:13px; margin-bottom:26px; }}
  .topnav a {{ color:var(--accent); text-decoration:none; font-weight:600; border-bottom:1px solid transparent;
    padding:10px 6px; margin:-10px -6px; border-radius:6px; }}
  .topnav a:hover {{ border-bottom-color:currentColor; }}
  .kickertop {{ font-family:ui-monospace,"SF Mono",Menlo,monospace; font-size:11px; letter-spacing:.12em; color:var(--accent2); font-weight:700; margin-bottom:8px; }}
  h1 {{ font-size:30px; font-weight:700; margin:0 0 10px; letter-spacing:-.02em; }}
  .lede {{ color:var(--text-secondary); max-width:70ch; margin:0 0 8px; }}
  .meta {{ font-size:12px; color:var(--text-muted); margin-bottom:24px; }}
  .toc {{ display:flex; gap:10px 18px; flex-wrap:wrap; font-size:13px; background:var(--surface-1);
    border:1px solid var(--border); border-radius:12px; padding:12px 16px; margin-bottom:26px; }}
  .toc a {{ color:var(--accent); text-decoration:none; }}
  .toc a:hover {{ text-decoration:underline; }}
  .card {{ background:var(--surface-1); border:1px solid var(--border); border-radius:14px;
    padding:26px 28px; margin-bottom:20px; box-shadow:var(--shadow); }}
  .kicker {{ font-family:ui-monospace,"SF Mono",Menlo,monospace; font-size:11px; letter-spacing:.1em; color:var(--accent); font-weight:700; }}
  h2 {{ font-size:19px; font-weight:700; margin:4px 0 14px; }}
  h3 {{ font-size:13px; font-weight:700; margin:16px 0 6px; color:var(--text-secondary); text-transform:none; }}
  .grid2 {{ display:grid; grid-template-columns:minmax(260px,1fr) minmax(300px,1.4fr); gap:10px 28px; }}
  @media (max-width:760px) {{ .grid2 {{ grid-template-columns:1fr; }} }}
  .formula {{ font-family:ui-monospace,"SF Mono",Menlo,monospace; font-size:12.5px; background:var(--surface-2);
    border:1px solid var(--border); border-radius:8px; padding:10px 12px; margin:4px 0; }}
  .ptable, .dtable {{ border-collapse:collapse; font-size:12.5px; width:100%; }}
  .ptable th,.ptable td,.dtable th,.dtable td {{ text-align:left; padding:6px 10px; border-bottom:1px solid var(--grid); }}
  .ptable th,.dtable th {{ color:var(--text-muted); font-size:11px; text-transform:uppercase; letter-spacing:.04em; }}
  .mono {{ font-family:ui-monospace,"SF Mono",Menlo,monospace; font-size:12px; }}
  .num {{ font-variant-numeric:tabular-nums; }}
  .muted {{ color:var(--text-muted); }}
  .tag {{ font-size:10px; background:var(--accent2); color:#fff; border-radius:999px; padding:2px 8px; font-weight:600; vertical-align:middle; }}
  .hint {{ font-size:12px; color:var(--text-muted); line-height:1.65; margin:4px 0; }}
  .explain {{ font-size:13px; color:var(--text-secondary); line-height:1.8; }}
  .explain b {{ color:var(--text-primary); }}
  .crosslink {{ font-size:12.5px; margin:16px 0 0; padding-top:12px; border-top:1px solid var(--grid); }}
  .crosslink a {{ color:var(--accent); text-decoration:none; font-weight:600; }}
  .crosslink a:hover {{ text-decoration:underline; }}
  .calc {{ display:grid; grid-template-columns:auto 130px; gap:6px 14px; align-items:center; max-width:560px; font-size:13px; }}
  .calc label {{ color:var(--text-secondary); }}
  .calc input {{ font:inherit; padding:5px 8px; border:1px solid var(--border); border-radius:6px;
    background:var(--input); color:var(--text-primary); text-align:right; width:130px; }}
  .calc output {{ background:var(--result); border-radius:6px; padding:5px 10px; text-align:right;
    font-variant-numeric:tabular-nums; font-weight:700; }}
  .calc .sep {{ grid-column:1/3; border-top:1px dashed var(--grid); margin:6px 0; }}
</style>
<div class="wrap">
  <nav class="topnav">
    <a href="{link_hub}">← 專案首頁</a>
    <a href="{link_dashboard}">即時儀表板</a>
    <a href="{link_report}">因子驗證報告</a>
  </nav>
  <div class="kickertop">FACTOR DEFINITIONS MANUAL</div>
  <h1>因子定義手冊</h1>
  <p class="lede">債券市場恐懼貪婪指數的唯一定義來源。本頁由 <span class="mono">factor_definitions.json</span> 自動生成——想修改任何因子的參數或定義,改那個檔案後重跑 <span class="mono">python3 update_dashboard.py && python3 generate_manual.py</span>,儀表板、驗證報告與本頁會全部同步。</p>
  <p class="meta">生成日期 {date.today().isoformat()}　·　定義檔版本 v{DEFS['version']}</p>

  <div class="toc">
    <a href="#sources">資料來源</a>
    <a href="#percentile">百分位機制</a>
    <a href="#params">可調參數總覽</a>
    {''.join(toc_items)}
    <a href="#composite">綜合分數</a>
    <a href="#validation">驗證方法</a>
    <a href="#calculator">互動試算</a>
  </div>

  <section class="card" id="sources">
    <h2>資料來源</h2>
    <table class="dtable">
      <tr><th>欄位</th><th>代號</th><th>來源</th><th>可回溯到</th><th>說明</th></tr>
      {src_rows}
    </table>
  </section>

  <section class="card" id="percentile">
    <h2>核心機制:滾動百分位</h2>
    <p class="explain">六個因子(強度除外)都用同一個機制把原始數字變成0~100分:<b>拿今天的數值,跟過去{G['percentile_window_days']}天({G['percentile_years_label']})每一天比,看今天贏過其中百分之多少天</b>。</p>
    <p class="formula">分數 = (視窗內「數值 ≤ 今天」的天數) ÷ {G['percentile_window_days']} × 100</p>
    <p class="explain">好處:單位完全不同的指標(%、點數、指數)統一成0~100可平均;比「相對位置」不比絕對值,市場整體水位漂移不影響。<br>
    <b>禁止偷看未來:</b>視窗只往過去看(trailing);每次執行自動抽8個歷史日期用截斷資料重算比對(assert_no_lookahead_bias),不一致直接報錯中止。</p>
  </section>

  <section class="card" id="params">
    <h2>可調參數總覽 <span class="tag">改因子先看這裡</span></h2>
    <table class="dtable">
      <tr><th>所屬</th><th>參數</th><th>現值</th><th>改了會怎樣</th></tr>
      {tune_rows}
    </table>
    <p class="hint">改法:編輯 factor_definitions.json 對應數值 → 重跑 update_dashboard.py(儀表板+CSV) 與 generate_manual.py(本頁) 與 factor_validation_analysis.py(驗證報告)。文字說明中的數字用token連動,會自動跟著變。</p>
  </section>

  {''.join(factor_sections)}

  <section class="card" id="composite">
    <h2>綜合分數與分級</h2>
    <p class="explain"><b>綜合分數</b> = {G['composite_note']}</p>
    <h3>分級門檻(與CNN原版一致)</h3>
    <table class="ptable" style="max-width:360px">
      <tr><th>分數區間</th><th>標籤</th></tr>
      {th_rows}
    </table>
    <p class="hint">{G['color_convention']}。</p>
  </section>

  <section class="card" id="validation">
    <h2>驗證方法(對應因子驗證報告)</h2>
    <table class="dtable">
      <tr><th>模組</th><th>方法與參數</th></tr>
      <tr><td>IC(資訊係數)</td><td>Spearman等級相關,分數 vs 未來{'/'.join(str(h) for h in V['horizons'])}日{V['target_label']}報酬。{V['sampling_note']}</td></tr>
      <tr><td>分位數分桶</td><td>{V['n_buckets']}組(全樣本) / {V['decile_n_buckets']}組(目標{V['decile_years']}年) / {V['vigintile_n_buckets']}組(目標{V['vigintile_years']}年);每組樣本數低於{V['decile_min_n_warn']}筆標警示。</td></tr>
      <tr><td>Leave-one-out</td><td>輪流拿掉一因子重算綜合分數,比較{V['loo_horizon']}日IC變化(ΔIC)。</td></tr>
      <tr><td>相關係數矩陣</td><td>七因子分數兩兩Pearson相關,熱力圖呈現。</td></tr>
      <tr><td>策略回測</td><td>{V['position_rule_note']} quantstats產出夏普/回撤/勝率,與買進持有比較。</td></tr>
      <tr><td>前後半穩定性</td><td>資料切兩半各重跑,檢查訊號是否被單一時期主導。</td></tr>
    </table>
    <p class="crosslink"><a href="{link_report}">→ 打開完整因子驗證報告</a></p>
  </section>

  <section class="card" id="calculator">
    <h2>互動試算 <span class="tag">改輸入即時重算</span></h2>
    <p class="hint">預設值為2026-07-19實際資料。百分位步驟需要完整5年分佈無法單格重現,故以「視窗內≤今天的天數」當輸入;其餘皆為即時計算。</p>
    <div class="calc" id="calcRoot">
      <label>ZN期貨</label><input type="number" step="0.001" id="i_zn" value="109.265625">
      <label>ZN {DEFS['factors'][0]['params']['sma_window']}日均線</label><input type="number" step="0.001" id="i_sma" value="110.197">
      <label>乖離率%</label><output id="o_bias"></output>
      <label>百分位:視窗內≤今天的天數</label><input type="number" id="i_nle" value="828">
      <label>百分位:視窗總天數</label><input type="number" id="i_ntot" value="{G['percentile_window_days']}">
      <label><b>動能分數</b></label><output id="o_mom"></output>
      <div class="sep"></div>
      <label>NQ期貨</label><input type="number" step="0.01" id="i_nq" value="28773.25">
      <label>{DEFS['factors'][1]['params']['range_window']}日最高</label><input type="number" step="0.01" id="i_hi" value="30712.75">
      <label>{DEFS['factors'][1]['params']['range_window']}日最低</label><input type="number" step="0.01" id="i_lo" value="23139.75">
      <label><b>強度分數</b></label><output id="o_str"></output>
      <div class="sep"></div>
      <label>TLT {DEFS['factors'][2]['params']['return_window']}日報酬%</label><input type="number" step="0.001" id="i_tlt" value="-0.7049">
      <label>SHY {DEFS['factors'][2]['params']['return_window']}日報酬%</label><input type="number" step="0.001" id="i_shy" value="0.0610">
      <label><b>存續期間利差%</b>(再丟百分位)</label><output id="o_dur"></output>
      <div class="sep"></div>
      <label>10年期殖利率%</label><input type="number" step="0.01" id="i_u10" value="4.55">
      <label>2年期殖利率%</label><input type="number" step="0.01" id="i_u2" value="4.18">
      <label><b>2s10s利差%</b>(再丟百分位)</label><output id="o_cur"></output>
      <div class="sep"></div>
      <label>CPI 今年</label><input type="number" step="0.001" id="i_cpi" value="332.568">
      <label>CPI 去年同期</label><input type="number" step="0.001" id="i_cpil" value="322.169">
      <label>市場通膨定價%</label><input type="number" step="0.01" id="i_be" value="2.24">
      <label>CPI年增%</label><output id="o_yoy"></output>
      <label><b>通膨意外%</b>(再丟百分位反轉)</label><output id="o_inf"></output>
      <div class="sep"></div>
      <label>六項分數(逗號分隔,缺項留空)</label><input type="text" id="i_scores" value="45.37, 74.39, 50.85, 11.73, 62.79, 51.07" style="width:230px; text-align:left">
      <label><b>綜合分數</b></label><output id="o_comp"></output>
      <label>分級標籤</label><output id="o_label"></output>
    </div>
  </section>
</div>
<script>
const TH = {json.dumps(G["label_thresholds"], ensure_ascii=False)};
function labelOf(s) {{
  for (const t of TH) if (s < t.lt) return t.label;
  return TH[TH.length - 1].label;
}}
function recalc() {{
  const v = id => parseFloat(document.getElementById(id).value);
  const set = (id, val, nd=2) => document.getElementById(id).textContent = isFinite(val) ? val.toFixed(nd) : "—";
  set("o_bias", (v("i_zn") - v("i_sma")) / v("i_sma") * 100, 3);
  set("o_mom", v("i_nle") / v("i_ntot") * 100);
  set("o_str", (v("i_nq") - v("i_lo")) / (v("i_hi") - v("i_lo")) * 100);
  set("o_dur", v("i_tlt") - v("i_shy"), 3);
  set("o_cur", v("i_u10") - v("i_u2"), 2);
  const yoy = (v("i_cpi") / v("i_cpil") - 1) * 100;
  set("o_yoy", yoy, 3);
  set("o_inf", yoy - v("i_be"), 3);
  const scores = document.getElementById("i_scores").value.split(",").map(s => parseFloat(s.trim())).filter(x => isFinite(x));
  const comp = scores.length ? scores.reduce((a,b)=>a+b,0)/scores.length : NaN;
  set("o_comp", comp);
  document.getElementById("o_label").textContent = isFinite(comp) ? labelOf(comp) : "—";
}}
document.querySelectorAll("#calcRoot input").forEach(el => el.addEventListener("input", recalc));
recalc();
</script>
"""

with open(f"{BASE}/chart/manual.html", "w", encoding="utf-8") as f:
    f.write(html)
print(f"已生成 chart/manual.html（{len(html)/1024:.0f} KB）")

# ================================================================ 入口頁 index.html
factor_count = len(DEFS["factors"])
hub_html = f"""<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>債券市場恐懼貪婪 · 專案首頁</title>
<style>
  :root {{
    --page:#f4f5f7; --surface:#ffffff; --text:#161a23; --text2:#4a5568; --muted:#667085;
    --accent:#1e3a5f; --accent2:#a6742a; --border:#dfe2e8; --shadow:0 1px 2px rgba(22,26,35,0.04);
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --page:#0f1218; --surface:#171b24; --text:#f1f3f6; --text2:#b8c0cc; --muted:#8b93a3;
      --accent:#7ea3cf; --accent2:#d9a860; --border:#2c313d; --shadow:0 1px 2px rgba(0,0,0,0.35); }}
  }}
  :root[data-theme="dark"] {{ --page:#0f1218; --surface:#171b24; --text:#f1f3f6; --text2:#b8c0cc; --muted:#8b93a3;
    --accent:#7ea3cf; --accent2:#d9a860; --border:#2c313d; --shadow:0 1px 2px rgba(0,0,0,0.35); }}
  :root[data-theme="light"] {{ --page:#f4f5f7; --surface:#ffffff; --text:#161a23; --text2:#4a5568; --muted:#667085;
    --accent:#1e3a5f; --accent2:#a6742a; --border:#dfe2e8; --shadow:0 1px 2px rgba(22,26,35,0.04); }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--page); color:var(--text); line-height:1.7;
    font-family:-apple-system,BlinkMacSystemFont,"PingFang TC","Noto Sans TC","Segoe UI",Roboto,sans-serif; }}
  .wrap {{ max-width:880px; margin:0 auto; padding:60px 24px 70px; }}
  .kicker {{ font-family:ui-monospace,"SF Mono",Menlo,monospace; font-size:11px; letter-spacing:.12em; color:var(--accent2); font-weight:700; margin-bottom:10px; }}
  h1 {{ font-size:32px; font-weight:700; margin:0 0 10px; letter-spacing:-.02em; }}
  .lede {{ color:var(--text2); max-width:64ch; margin:0 0 34px; }}
  .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:16px; }}
  a.card {{ display:block; background:var(--surface); border:1px solid var(--border); border-radius:14px;
    padding:24px 24px 20px; text-decoration:none; color:var(--text); box-shadow:var(--shadow);
    transition:transform .15s ease, box-shadow .2s ease; }}
  a.card:hover {{ transform:translateY(-2px); box-shadow:0 6px 18px rgba(22,26,35,0.10); }}
  .card .ck {{ font-family:ui-monospace,"SF Mono",Menlo,monospace; font-size:10.5px; letter-spacing:.1em; color:var(--accent); font-weight:700; }}
  .card h2 {{ font-size:18px; margin:6px 0 8px; }}
  .card p {{ font-size:13px; color:var(--text2); margin:0; }}
  .foot {{ font-size:12px; color:var(--muted); margin-top:34px; line-height:1.7; }}
  .mono {{ font-family:ui-monospace,"SF Mono",Menlo,monospace; }}
</style>
<div class="wrap">
  <div class="kicker">BOND MARKET FEAR &amp; GREED</div>
  <h1>債券市場恐懼貪婪 · 專案首頁</h1>
  <p class="lede">{factor_count}項美債市場指標彙整成每日恐懼貪婪分數,配套完整的統計驗證與定義文件。三個分類互相連結,同一份定義來源(factor_definitions.json)驅動。</p>
  <div class="cards">
    <a class="card" href="{link_dashboard}">
      <div class="ck">LIVE DASHBOARD</div>
      <h2>即時儀表板</h2>
      <p>今日綜合分數與{factor_count}項因子走勢,互動時間軸,每日收盤後更新。</p>
    </a>
    <a class="card" href="{link_report}">
      <div class="ck">VALIDATION REPORT</div>
      <h2>因子驗證報告</h2>
      <p>IC分析、分桶檢定、Leave-one-out、相關矩陣、回測、穩定性——分數到底準不準。</p>
    </a>
    <a class="card" href="{URLS.get('manual') or 'manual.html'}">
      <div class="ck">DEFINITIONS MANUAL</div>
      <h2>因子定義手冊</h2>
      <p>每個因子的公式、參數、設計理由、限制,含互動試算。改因子前必看。</p>
    </a>
    <a class="card" href="screening_form.html">
      <div class="ck">FACTOR SCREENER APP</div>
      <h2>線上驗證新因子</h2>
      <p>直接在網頁上填寫參數提交驗證，自動跑20年資料與5道關卡，即時呈現所有分析圖表。</p>
    </a>
    <a class="card" href="screening_index.html">
      <div class="ck">FACTOR SCREENING REGISTRY</div>
      <h2>因子篩選登記簿</h2>
      <p>五道關卡自動判定新因子該不該加入正式分數,每次測試都留紀錄,防止多重比較自欺。</p>
    </a>
  </div>
  <p class="foot">更新方式:<span class="mono">python3 update_dashboard.py</span>(儀表板) · <span class="mono">python3 factor_validation_analysis.py</span>(驗證報告) · <span class="mono">python3 generate_manual.py</span>(手冊+本頁)。<br>生成日期 {date.today().isoformat()}。</p>
</div>
"""
with open(f"{BASE}/chart/index.html", "w", encoding="utf-8") as f:
    f.write(hub_html)
print(f"已生成 chart/index.html（{len(hub_html)/1024:.0f} KB）")
