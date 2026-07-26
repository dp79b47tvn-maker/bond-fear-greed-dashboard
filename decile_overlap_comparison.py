"""
分桶分析：非重疊 vs 重疊取樣對照（獨立產出，不影響正式因子驗證報告）

背景：10年期/20年期的十分位、二十分位分桶分析（decile_bucket_analysis）目前用
「非重疊取樣」（每隔horizon個交易日才取一筆樣本），原因是分組本來就多、樣本天生
就少，怕重疊取樣的自相關問題讓分組平均值失真更嚴重。但非重疊取樣的代價是：
被跳過的那些天發生的漲跌幅，完全不會被納入任何一筆樣本——如果一段夠短的
劇烈波動剛好落在被跳過的區間，分桶分析會完全看不到它。

（每個因子詳細頁裡分5組的「分位數分桶」不受影響——那個本來就是每天都取樣，
沒有做非重疊取樣，只有10年/20年這兩個十分位/二十分位分析才有這個問題。）

這支腳本產生一份獨立的HTML，把「非重疊 vs 重疊」兩種取樣方式的10年/20年分桶結果
並排放在一起，純粹給使用者自己比較用，不會連結進首頁/導覽列，也不會取代或修改
正式發布的 factor_validation_report.html。使用者看過比較結果後，再決定要不要
把正式報告的分桶分析換成重疊取樣。

執行：
    python3 decile_overlap_comparison.py

輸出：
    chart/decile_overlap_comparison.html
"""
import pandas as pd

import factor_validation_analysis as fva

FACTOR_COLS = fva.FACTOR_COLS
COMPOSITE_COL = fva.COMPOSITE_COL
COMPOSITE_LABEL = fva.COMPOSITE_LABEL
DECILE_YEARS = fva.DECILE_YEARS
DECILE_N_BUCKETS = fva.DECILE_N_BUCKETS
DECILE_HORIZON = fva.DECILE_HORIZON
DECILE_MIN_N_WARN = fva.DECILE_MIN_N_WARN
_V = fva._V


def decile_bucket_analysis_overlap(df, score_col, horizon=DECILE_HORIZON, buckets=DECILE_N_BUCKETS, target=fva.TARGET):
    """跟 decile_bucket_analysis() 邏輯完全相同（qcut等分＋看未來N日平均報酬、
    一樣分10組/20組），唯一差別：不做 .iloc[::horizon] 跳過，每天都取樣。
    用意是拿來跟非重疊版本並排比較，不是要取代它——樣本間高度自相關，
    這裡不做任何顯著性宣稱，只看分組平均報酬的數值本身差多少。"""
    sub = df[[score_col]].copy()
    sub["fwd"] = fva.forward_return(df[target], horizon)
    sub = sub.dropna()
    if len(sub) < buckets * 3:
        return None
    actual_start, actual_end = sub.index.min(), sub.index.max()
    if len(sub) < buckets:
        return None
    try:
        sub["bucket"] = pd.qcut(sub[score_col], buckets, labels=False, duplicates="drop")
    except ValueError:
        return None
    grp = sub.groupby("bucket").agg(
        mean_score=(score_col, "mean"), mean_fwd_ret=("fwd", "mean"),
        median_fwd_ret=("fwd", "median"), n=("fwd", "count"),
    ).reset_index()
    grp["label"] = [f"D{i+1}" for i in range(len(grp))]
    return {
        "table": grp, "date_range": (actual_start, actual_end),
        "n_sampled_total": len(sub), "n_daily_total": len(sub),
    }


def render_compare_block(label, non_overlap_result, overlap_result, buckets, horizon):
    chart_non = fva.decile_chart_base64(
        non_overlap_result, f"{label}：未來{horizon}日平均報酬（{buckets}分組，非重疊取樣）", buckets, horizon
    )
    chart_overlap = fva.decile_chart_base64(
        overlap_result, f"{label}：未來{horizon}日平均報酬（{buckets}分組，重疊取樣）", buckets, horizon
    )

    def table_html(result):
        if not result:
            return "<p class='na'>資料不足，無法分桶</p>"
        rows = "".join(
            f"<tr class=\"{'low-n' if row.n < DECILE_MIN_N_WARN else ''}\">"
            f"<td>{row.label}</td><td>{row.mean_score:.1f}</td>"
            f"<td>{row.mean_fwd_ret:+.2f}%</td><td>{row.median_fwd_ret:+.2f}%</td>"
            f"<td>{int(row.n)}{' ⚠️' if row.n < DECILE_MIN_N_WARN else ''}</td></tr>"
            for row in result["table"].itertuples()
        )
        return (f"<table class='data-table'><tr><th>分組</th><th>平均分數</th>"
                f"<th>平均未來報酬</th><th>中位數未來報酬</th><th>樣本數</th></tr>{rows}</table>")

    n_non = non_overlap_result["n_sampled_total"] if non_overlap_result else 0
    n_overlap = overlap_result["n_sampled_total"] if overlap_result else 0

    return f"""
    <div class="decile-block">
      <h3>{label}</h3>
      <p class="hint">非重疊取樣樣本點：{n_non}　·　重疊取樣樣本點：{n_overlap}</p>
      <div class="compare-grid">
        <div>
          <h4>非重疊取樣（正式報告目前用的方法）</h4>
          {"<img class='chart' src='data:image/png;base64," + chart_non + "'/>" if chart_non else ""}
          {table_html(non_overlap_result)}
        </div>
        <div>
          <h4>重疊取樣（僅供比較參考）</h4>
          {"<img class='chart' src='data:image/png;base64," + chart_overlap + "'/>" if chart_overlap else ""}
          {table_html(overlap_result)}
        </div>
      </div>
    </div>"""


def render_years_section(ext_df, all_labels_map, buckets, horizon):
    blocks = []
    for col, label in all_labels_map.items():
        if col not in ext_df.columns:
            blocks.append(f"<div class='decile-block'><h3>{label}</h3><p class='na'>此因子目前沒有歷史資料。</p></div>")
            continue
        rng = fva.score_actual_range(ext_df, col)
        if rng is None:
            blocks.append(f"<div class='decile-block'><h3>{label}</h3><p class='na'>此因子目前沒有歷史資料。</p></div>")
            continue
        non_overlap = fva.decile_bucket_analysis(ext_df, col, horizon=horizon, buckets=buckets)
        overlap = decile_bucket_analysis_overlap(ext_df, col, horizon=horizon, buckets=buckets)
        blocks.append(render_compare_block(label, non_overlap, overlap, buckets, horizon))
    return "".join(blocks)


def main():
    print("抓取延伸歷史資料（沿用factor_validation_analysis.py的抓取邏輯）...")
    all_labels_map = dict(FACTOR_COLS)
    all_labels_map[COMPOSITE_COL] = COMPOSITE_LABEL

    _vy, _vb = _V["vigintile_years"], _V["vigintile_n_buckets"]
    ext_df_20y, _ = fva.fetch_extended_history(years=_vy)
    section_20y = render_years_section(ext_df_20y, all_labels_map, buckets=_vb, horizon=DECILE_HORIZON)

    ten_year_cutoff = pd.Timestamp(fva.date.today()) - pd.Timedelta(days=DECILE_YEARS * 365)
    ext_df_10y = ext_df_20y.loc[ext_df_20y.index >= ten_year_cutoff]
    section_10y = render_years_section(ext_df_10y, all_labels_map, buckets=DECILE_N_BUCKETS, horizon=DECILE_HORIZON)

    html = f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>分桶分析：非重疊 vs 重疊取樣對照</title>
<style>
{fva.REPORT_CSS}
.compare-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-top:10px; }}
.compare-grid h4 {{ font-size:12.5px; font-weight:700; color:#667085; margin:0 0 6px; text-transform:uppercase; letter-spacing:0.03em; }}
@media (max-width:720px) {{ .compare-grid {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="kicker">DECILE SAMPLING COMPARISON — 內部比較用，非正式報告</div>
    <h1>分桶分析：非重疊 vs 重疊取樣對照</h1>
    <p class="meta">產生日期：{fva.date.today().isoformat()}</p>
    <p class="disclaimer">
      這份頁面是獨立比較用的產出，不是正式的因子驗證報告，也沒有連結進首頁/導覽列。
      目的：10年期/20年期的分桶分析目前用非重疊取樣（每隔{DECILE_HORIZON}個交易日才取一筆樣本），
      被跳過的區間發生的漲跌幅完全不會反映在任何一筆樣本裡；這裡額外做了「重疊取樣」版本
      （每天都取樣）並排比較，看兩者的分組平均報酬差多少。重疊版本樣本間高度自相關，
      不能拿來判斷統計顯著性，純粹看數值本身的差異，看完再決定要不要把正式報告換成這個做法。
    </p>
  </header>

  <section class="card">
    <h2><span class="bar"></span>10年期／{DECILE_N_BUCKETS}分組</h2>
    {section_10y}
  </section>

  <section class="card">
    <h2><span class="bar"></span>{_vy}年期／{_vb}分組</h2>
    {section_20y}
  </section>
</div>
</body>
</html>"""

    with open("chart/decile_overlap_comparison.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"完成！已輸出 chart/decile_overlap_comparison.html（{len(html)/1024:.0f} KB）")


if __name__ == "__main__":
    main()
