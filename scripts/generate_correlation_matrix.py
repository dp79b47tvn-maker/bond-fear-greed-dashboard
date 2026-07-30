"""
因子相關係數矩陣——取代原本每日自動產生、範圍固定的驗證報告版本，改成因子篩選平台裡
的隨選功能：使用者勾選想比較的因子（官方七項＋目前已升等的候選因子），透過GitHub
Actions(.github/workflows/correlation-matrix.yml)在後台用pandas/matplotlib算出來，
不在前端即時運算。

直接重用factor_validation_analysis.py既有的correlation_heatmap_base64()——那個函式
本來就是通用的(吃任意DataFrame + {欄位名:顯示label}字典)，只是原本唯一的呼叫處固定
傳官方七因子；這裡改成依使用者勾選的清單動態組factor_cols_map。

用法：
    python3 scripts/generate_correlation_matrix.py --factor-keys momentum_score,strength_score,promoted_us10y_score
"""
import argparse
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import factor_validation_analysis as fva
import nav_bar
import page_style
import update_dashboard as ud

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bond_fear_greed_v2.csv")
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "chart", "correlation_matrix.html")


def _official_labels():
    return {fx["score_col"]: fx["name_tpl"].split(" ")[0] for fx in ud.DEFS["factors"]}


def _promoted_labels():
    promoted_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "promoted_candidate_factors.json")
    if not os.path.exists(promoted_path):
        return {}
    import json
    with open(promoted_path, encoding="utf-8") as f:
        staged = json.load(f)
    return {f"promoted_{pf['key']}_score": f"{pf['label']}（候選）" for pf in staged.get("factors", [])}


def build_factor_cols_map(selected_keys):
    all_labels = {**_official_labels(), **_promoted_labels()}
    factor_cols_map = {}
    skipped = []
    for key in selected_keys:
        if key in all_labels:
            factor_cols_map[key] = all_labels[key]
        else:
            skipped.append(key)
    if skipped:
        print(f"警告：以下因子key無法識別、已略過：{skipped}")
    return factor_cols_map


def render_corr_table(corr):
    header = "<tr><th></th>" + "".join(f"<th>{c}</th>" for c in corr.columns) + "</tr>"
    rows = ""
    for idx, row in corr.iterrows():
        cells = "".join(f"<td>{row[c]:.2f}</td>" for c in corr.columns)
        rows += f"<tr><td class=\"fname\">{idx}</td>{cells}</tr>"
    return f'<table class="data-table">{header}{rows}</table>'


def render_page(heatmap_b64, corr, factor_cols_map):
    labels = "、".join(factor_cols_map.values())
    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>因子相關係數矩陣 · 債券市場恐懼貪婪</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ margin:0; background:#f4f5f7; color:#161a23; font-family:-apple-system,BlinkMacSystemFont,"PingFang TC","Noto Sans TC","Segoe UI",Roboto,sans-serif; line-height:{page_style.BASE_LINE_HEIGHT}; }}
  .wrap {{ max-width:{page_style.CONTENT_MAX_WIDTH}; margin:0 auto; padding:44px 24px 80px; }}
  h1 {{ font-size:{page_style.H1_SIZE}; font-weight:700; margin:0 0 12px; letter-spacing:-0.02em; }}
  .kicker {{ font-family:ui-monospace,"SF Mono",Menlo,monospace; font-size:11px; letter-spacing:0.12em; color:#a6742a; font-weight:700; margin-bottom:10px; }}
  .meta {{ font-size:13px; color:#4a5568; margin:0 0 20px; max-width:{page_style.LEDE_MAX_WIDTH}; line-height:1.7; }}
  .card {{ background:#fff; border:1px solid #dfe2e8; border-radius:14px; padding:24px 28px; margin-bottom:22px; box-shadow:0 1px 2px rgba(22,26,35,0.04); }}
  .card.center {{ text-align:center; }}
  .card h2 {{ font-size:16px; font-weight:700; margin:0 0 14px; }}
  img {{ max-width:100%; height:auto; }}
  .data-table {{ width:100%; border-collapse:collapse; font-size:12.5px; }}
  .data-table th, .data-table td {{ text-align:right; padding:7px 10px; border-bottom:1px solid #e5e7eb; font-variant-numeric:tabular-nums; }}
  .data-table th:first-child, .data-table td:first-child {{ text-align:left; }}
  .data-table th {{ color:#667085; font-weight:600; font-size:11px; }}
  .data-table td.fname {{ font-weight:600; text-align:left; white-space:nowrap; }}
  .back-link {{ font-size:13px; color:#1e3a5f; text-decoration:none; font-weight:600; }}
  .back-link:hover {{ text-decoration:underline; }}
  {nav_bar.NAV_BAR_CSS}
</style>
</head>
<body>
<div class="wrap">
  {nav_bar.render_nav_bar("screening")}
  <div class="kicker">FACTOR CORRELATION MATRIX</div>
  <h1>因子相關係數矩陣</h1>
  <p class="meta">
    比較因子：{labels}。相關係數越接近±1代表兩個因子在講同一件事(訊息重複)，越接近0代表提供的是不同角度的資訊。
    這是隨選產生的一次性快照，不會每天自動更新——想比較不同的因子組合，回<a class="back-link" href="screening_index.html">因子篩選平台</a>重新勾選再產生一次。
  </p>
  <div class="card center">
    <img src="data:image/png;base64,{heatmap_b64}" alt="因子相關係數熱力圖">
  </div>
  <div class="card">
    <h2>完整數值(熱力圖標註只到小數點後2位，這裡是同一份數字，供精確比對)</h2>
    {render_corr_table(corr)}
  </div>
</div>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="產生因子相關係數矩陣熱力圖頁面")
    parser.add_argument("--factor-keys", type=str, required=True, help="逗號分隔的因子score_col清單，至少2個")
    args = parser.parse_args()

    selected_keys = [k.strip() for k in args.factor_keys.split(",") if k.strip()]
    if len(selected_keys) < 2:
        raise ValueError("至少需要2個因子才能算相關係數矩陣")

    factor_cols_map = build_factor_cols_map(selected_keys)
    if len(factor_cols_map) < 2:
        raise ValueError(f"可識別的因子不足2個(收到{selected_keys}，識別出{list(factor_cols_map.keys())})")

    df = pd.read_csv(CSV_PATH, index_col=0, parse_dates=True).sort_index()
    heatmap_b64, corr = fva.correlation_heatmap_base64(df, factor_cols_map)

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(render_page(heatmap_b64, corr, factor_cols_map))
    print(f"已產生：{OUT_PATH}")
    print(f"比較因子：{list(factor_cols_map.values())}")


if __name__ == "__main__":
    main()
