"""
因子驗證分析 —— 一次性（但可重複執行）的完整報告，產出給主管看的「哪些因子該留、
哪些訊號品質不夠好」的判斷依據。不整合進儀表板即時顯示，資料更新後可直接重跑：

    python3 factor_validation_analysis.py

輸出：factor_validation_report.html（單一自包含檔案，圖表以base64內嵌，瀏覽器直接開）

八大模組（對應需求書的一到八）：
  1. IC分析：每個因子 + 綜合分數，對未來5/10/20/60日ZN報酬的Spearman等級相關係數
  3. （方法內建）IC一律用「非重疊取樣」：每隔N天才取一個樣本點，N=驗證的報酬期間，
     避免相鄰樣本因報酬窗口重疊而互相高度相關、把統計顯著性灌水
  2. 分位數分桶：qcut切5等分，看未來20日平均報酬是否隨分數單調遞減
  4. Leave-one-out：輪流拿掉一項因子重算綜合分數，比較IC變化
  5. 因子相關係數矩陣 + seaborn熱力圖
  6. 策略回測：部位大小 = (50-分數)/50，48-52死區，quantstats出績效，
     綜合分數 + 每個因子單獨各跑一次
  7. 樣本穩定性：全樣本 / 前半段 / 後半段，1-6項都各跑一次
  8. 全部整合成一份HTML報告，含摘要頁、各因子詳細頁、熱力圖、完整回測報告、
     穩定性比較、自動產生的建議頁

方法論注意事項（誠實揭露，report本身也會重複這些話）：
  - 部位方向假設「恐懼買入」（分數低→未來報酬應該高→IC應該是負的）。這是使用者的
    操作邏輯，但本專案先前的回測已經發現，多數因子在多數時期實際上是動能延續
    （分數高、未來報酬也高，IC是正的）。這份報告如實呈現算出來的正負號與數值，
    不會為了迎合「應該是負相關」的假設而扭曲呈現方式——這正是这份報告存在的目的。
  - 部位在t日收盤用當天分數決定，套用在t+1日的報酬上（position.shift(1)），
    不使用未來資料。
  - IC全部用非重疊取樣，樣本數天生就少，報告會明確列出每組實際樣本數。
"""
import base64
import io
import warnings
from datetime import date

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
matplotlib.rcParams["font.sans-serif"] = ["PingFang TC", "Heiti TC", "Arial Unicode MS", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False
import pandas as pd
import seaborn as sns
from scipy import stats

warnings.filterwarnings("ignore")

import quantstats as qs

# ---------------------------------------------------------------- 設定
TARGET = "ZN_futures"
HORIZONS = [5, 10, 20, 60]
LOO_HORIZON = 20
BUCKET_HORIZON = 20
N_BUCKETS = 5
DEAD_ZONE = (48, 52)

FACTOR_COLS = {
    "momentum_score": "動能",
    "strength_score": "強度",
    "duration_score": "存續期間避險",
    "putcall_score": "Put/Call",
    "move_score": "波動度",
    "curve_score": "殖利率曲線形狀",
    "inflation_score": "通膨意外",
}
COMPOSITE_COL = "composite_score"
COMPOSITE_LABEL = "綜合分數"

BUCKET_LABELS = ["極度恐懼", "恐懼", "中性", "貪婪", "極度貪婪"]


# ================================================================ 資料
def load_data():
    df = pd.read_csv("bond_fear_greed_v2.csv", index_col=0, parse_dates=True).sort_index()
    return df


def split_halves(df):
    mid = df.index[len(df) // 2]
    h1 = df.loc[df.index < mid].copy()
    h2 = df.loc[df.index >= mid].copy()
    return h1, h2, mid


def forward_return(price, horizon):
    return (price.shift(-horizon) / price - 1) * 100


# ================================================================ 1+3. IC分析（非重疊取樣）
def non_overlapping_ic(df, score_col, horizon, target=TARGET):
    sub = df[[score_col]].copy()
    sub["fwd"] = forward_return(df[target], horizon)
    sub = sub.dropna()
    if len(sub) < 10:
        return {"rho": None, "pval": None, "n": len(sub)}
    sampled = sub.iloc[::horizon]
    if len(sampled) < 8:
        return {"rho": None, "pval": None, "n": len(sampled)}
    rho, pval = stats.spearmanr(sampled[score_col], sampled["fwd"])
    return {"rho": float(rho) if pd.notna(rho) else None, "pval": float(pval) if pd.notna(pval) else None, "n": len(sampled)}


def ic_table(df, score_cols_map, horizons=HORIZONS):
    rows = []
    for col, label in score_cols_map.items():
        if col not in df.columns:
            continue
        row = {"factor": label, "col": col}
        for h in horizons:
            row[f"h{h}"] = non_overlapping_ic(df, col, h)
        rows.append(row)
    return rows


# ================================================================ 2. 分位數分桶分析
def bucket_analysis(df, score_col, horizon=BUCKET_HORIZON, buckets=N_BUCKETS, target=TARGET):
    sub = df[[score_col]].copy()
    sub["fwd"] = forward_return(df[target], horizon)
    sub = sub.dropna()
    if len(sub) < buckets * 8:
        return None
    try:
        sub["bucket"] = pd.qcut(sub[score_col], buckets, labels=False, duplicates="drop")
    except ValueError:
        return None
    n_actual = sub["bucket"].nunique()
    grp = sub.groupby("bucket").agg(
        mean_score=(score_col, "mean"), mean_fwd_ret=("fwd", "mean"),
        median_fwd_ret=("fwd", "median"), n=("fwd", "count"),
    ).reset_index()
    if n_actual == buckets:
        grp["label"] = BUCKET_LABELS
    else:
        grp["label"] = [f"第{i+1}組" for i in range(len(grp))]
    mono_rho, _ = stats.spearmanr(grp["bucket"], grp["mean_fwd_ret"]) if len(grp) >= 3 else (None, None)
    return {"table": grp, "monotonicity": float(mono_rho) if pd.notna(mono_rho) else None}


def bucket_chart_base64(bucket_result, title):
    if bucket_result is None:
        return None
    grp = bucket_result["table"]
    fig, ax = plt.subplots(figsize=(5.2, 3.1), dpi=140)
    colors = ["#2f6b4f", "#5c8a6e", "#6b7280", "#b1592f", "#a6362f"][: len(grp)]
    bars = ax.bar(grp["label"], grp["mean_fwd_ret"], color=colors, width=0.62)
    ax.axhline(0, color="#888", linewidth=0.8)
    ax.set_ylabel(f"未來{BUCKET_HORIZON}日平均報酬 (%)", fontsize=9)
    ax.set_title(title, fontsize=10)
    ax.tick_params(axis="x", labelsize=8.5)
    ax.tick_params(axis="y", labelsize=8)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    for bar, v in zip(bars, grp["mean_fwd_ret"]):
        ax.annotate(f"{v:+.2f}", (bar.get_x() + bar.get_width() / 2, v),
                    textcoords="offset points", xytext=(0, 4 if v >= 0 else -12), ha="center", fontsize=7.5)
    fig.tight_layout()
    return fig_to_base64(fig)


def fig_to_base64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


# ================================================================ 4. Leave-one-out
def composite_loo(df, exclude_col, factor_cols):
    cols = [c for c in factor_cols if c != exclude_col]
    return df[cols].mean(axis=1, skipna=True)


def leave_one_out_table(df, factor_cols_map, horizon=LOO_HORIZON):
    full_ic = non_overlapping_ic(df, COMPOSITE_COL, horizon)
    rows = []
    for col, label in factor_cols_map.items():
        alt_score = composite_loo(df, col, list(factor_cols_map.keys()))
        tmp = df.copy()
        tmp["_loo"] = alt_score
        loo_ic = non_overlapping_ic(tmp, "_loo", horizon)
        delta = None
        if full_ic["rho"] is not None and loo_ic["rho"] is not None:
            delta = loo_ic["rho"] - full_ic["rho"]
        rows.append({"factor": label, "col": col, "full_ic": full_ic, "loo_ic": loo_ic, "delta": delta})
    return full_ic, rows


# ================================================================ 5. 因子相關係數矩陣
def correlation_heatmap_base64(df, factor_cols_map):
    cols = [c for c in factor_cols_map if c in df.columns and df[c].notna().sum() > 30]
    labels = [factor_cols_map[c] for c in cols]
    corr = df[cols].corr()
    corr.index = labels
    corr.columns = labels
    fig, ax = plt.subplots(figsize=(6, 5), dpi=140)
    sns.heatmap(corr, annot=True, fmt=".2f", cmap="RdBu_r", center=0, vmin=-1, vmax=1,
                square=True, ax=ax, cbar_kws={"shrink": 0.8}, annot_kws={"fontsize": 8.5})
    ax.set_title("因子分數兩兩相關係數（Pearson）", fontsize=11)
    plt.xticks(rotation=40, ha="right", fontsize=8.5)
    plt.yticks(rotation=0, fontsize=8.5)
    fig.tight_layout()
    return fig_to_base64(fig), corr


# ================================================================ 6. 策略回測
def position_size(score):
    pos = (50 - score) / 50
    dead = score.between(DEAD_ZONE[0], DEAD_ZONE[1])
    return pos.where(~dead, 0.0)


def build_strategy_returns(df, score_col, target=TARGET):
    sub = df[[score_col, target]].copy().dropna()
    if len(sub) < 60:
        return None, None
    sub["pos"] = position_size(sub[score_col])
    sub["daily_ret"] = sub[target].pct_change()
    sub["strategy_ret"] = sub["pos"].shift(1) * sub["daily_ret"]
    strat = sub["strategy_ret"].dropna()
    bench = sub["daily_ret"].reindex(strat.index)
    return strat, bench


def qs_metrics_row(strat, bench, label):
    if strat is None or len(strat) < 60:
        return {"label": label, "ok": False}
    try:
        m = qs.reports.metrics(strat, benchmark=bench, mode="full", display=False)
        # quantstats returns a DataFrame with columns ['Benchmark', 'Strategy'] (string-formatted
        # values, not floats) — must select the 'Strategy' column by NAME, not positionally
        # (.iloc[0] silently grabs the benchmark column, which was a real bug caught here).
        strategy_col = m["Strategy"] if "Strategy" in m.columns else m.iloc[:, -1]
        def get(name):
            if name not in strategy_col.index:
                return None
            try:
                return float(strategy_col.loc[name])
            except (TypeError, ValueError):
                return None
        return {
            "label": label, "ok": True,
            "sharpe": get("Sharpe"), "sortino": get("Sortino"),
            "max_dd": get("Max Drawdown"), "cagr": get("CAGR﹪") or get("CAGR"),
            "win_rate": get("Win Days"), "vol": get("Volatility (ann.)"),
            "n": len(strat),
        }
    except Exception as e:
        return {"label": label, "ok": False, "error": str(e)}


def full_tearsheet_html(strat, bench, title):
    import os
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".html")
    import os as _os
    _os.close(fd)
    try:
        qs.reports.html(strat, benchmark=bench, output=path, title=title, download_filename=path)
        with open(path, encoding="utf-8") as f:
            html = f.read()
        return html
    except Exception as e:
        return f"<p>quantstats完整報告產生失敗：{e}</p>"
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# ================================================================ HTML 組裝
def fmt_rho(d):
    if d is None or d.get("rho") is None:
        return f'<span class="na">無資料</span>'
    rho = d["rho"]
    cls = "neg" if rho < 0 else "pos"
    return f'<span class="{cls}">{rho:+.3f}</span> <span class="n">(n={d["n"]})</span>'


def fmt_pct(v):
    if v is None or pd.isna(v):
        return "—"
    return f"{v*100:.1f}%" if abs(v) < 3 else f"{v:.1f}%"


def fmt_num(v, nd=2):
    if v is None or pd.isna(v):
        return "—"
    return f"{v:.{nd}f}"


def build_recommendation(factor_label, ic20, loo_delta, bucket_mono, is_composite=False):
    """規則透明、可稽核：不是黑箱標籤，數字都攤開在旁邊。"""
    reasons = []
    score = 0
    if ic20 and ic20.get("rho") is not None:
        rho = ic20["rho"]
        if rho < -0.15:
            score += 2; reasons.append(f"IC={rho:+.3f}，符合「恐懼買入」假設方向且強度足夠")
        elif rho < -0.05:
            score += 1; reasons.append(f"IC={rho:+.3f}，方向符合假設但強度偏弱")
        elif rho > 0.15:
            score -= 1; reasons.append(f"IC={rho:+.3f}，方向與「恐懼買入」假設相反且強度不小（動能延續訊號）")
        elif rho > 0.05:
            reasons.append(f"IC={rho:+.3f}，方向與假設相反但強度不大")
        else:
            reasons.append(f"IC={rho:+.3f}，接近0，訊號很弱")
    else:
        reasons.append("此期間無足夠資料計算IC")
    if bucket_mono is not None:
        if bucket_mono < -0.8:
            score += 1; reasons.append("分桶報酬隨分數遞減，單調性良好")
        elif bucket_mono > 0.8:
            reasons.append("分桶報酬隨分數遞增（動能延續型態），單調性良好但方向與假設相反")
        else:
            reasons.append("分桶報酬不單調，恐懼/貪婪五分組區辨力有限")
    if not is_composite and loo_delta is not None:
        if abs(loo_delta) < 0.01:
            reasons.append(f"拿掉此因子後綜合分數IC幾乎不變（Δ={loo_delta:+.3f}），邊際貢獻小")
        else:
            reasons.append(f"拿掉此因子後綜合分數IC變化Δ={loo_delta:+.3f}")
    if score >= 2:
        verdict = "建議保留"
    elif score >= 0:
        verdict = "建議觀察／可考慮重新設計"
    else:
        verdict = "建議考慮剔除或重新定義"
    return verdict, reasons


def render_sample_section(df, sample_label):
    """對單一樣本（全樣本／前半／後半）跑1,2,4,5,6，回傳一個dict結果，供後續組HTML與跨樣本比較。"""
    all_cols = dict(FACTOR_COLS)
    all_cols_with_composite = dict(FACTOR_COLS); all_cols_with_composite[COMPOSITE_COL] = COMPOSITE_LABEL

    ic_rows = ic_table(df, all_cols_with_composite)
    buckets = {col: bucket_analysis(df, col) for col in all_cols_with_composite}
    full_loo_ic, loo_rows = leave_one_out_table(df, FACTOR_COLS)
    heatmap_b64, corr_matrix = correlation_heatmap_base64(df, FACTOR_COLS)

    backtests = {}
    for col, label in all_cols_with_composite.items():
        strat, bench = build_strategy_returns(df, col)
        backtests[col] = qs_metrics_row(strat, bench, label)

    return {
        "label": sample_label, "n_days": len(df),
        "date_range": (df.index.min().strftime("%Y-%m-%d"), df.index.max().strftime("%Y-%m-%d")),
        "ic_rows": ic_rows, "buckets": buckets,
        "full_loo_ic": full_loo_ic, "loo_rows": loo_rows,
        "heatmap_b64": heatmap_b64, "corr_matrix": corr_matrix,
        "backtests": backtests,
    }


def main():
    print("讀取資料 ...")
    df = load_data()
    h1, h2, split_date = split_halves(df)
    print(f"全樣本：{df.index.min().date()} ~ {df.index.max().date()}（{len(df)}天）")
    print(f"切點：{split_date.date()}　前半段{len(h1)}天／後半段{len(h2)}天")

    print("跑全樣本分析 ...")
    full = render_sample_section(df, "全樣本")
    print("跑前半段分析 ...")
    half1 = render_sample_section(h1, "前半段")
    print("跑後半段分析 ...")
    half2 = render_sample_section(h2, "後半段")

    print("產生綜合分數完整回測報告（quantstats tearsheet）...")
    comp_strat, comp_bench = build_strategy_returns(df, COMPOSITE_COL)
    tearsheet_html = full_tearsheet_html(comp_strat, comp_bench, "綜合分數策略 vs 買進持有ZN") if comp_strat is not None else "<p>資料不足</p>"

    print("產生因子相關係數熱力圖 ...")
    print("組裝HTML報告 ...")
    html = render_report(df, full, half1, half2, tearsheet_html, split_date)
    with open("factor_validation_report.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"完成！已輸出 factor_validation_report.html（{len(html)/1024:.0f} KB）")


# ---------------------------------------------------------------- HTML 模板
def render_report(df, full, half1, half2, tearsheet_html, split_date):
    all_labels = dict(FACTOR_COLS); all_labels[COMPOSITE_COL] = COMPOSITE_LABEL

    # ---- 摘要頁 ----
    summary_rows = []
    for col, label in all_labels.items():
        ic_row = next((r for r in full["ic_rows"] if r["col"] == col), None)
        ic20 = ic_row["h20"] if ic_row else None
        bucket = full["buckets"].get(col)
        mono = bucket["monotonicity"] if bucket else None
        loo_delta = None
        if col != COMPOSITE_COL:
            loo_row = next((r for r in full["loo_rows"] if r["col"] == col), None)
            loo_delta = loo_row["delta"] if loo_row else None
        verdict, reasons = build_recommendation(label, ic20, loo_delta, mono, is_composite=(col == COMPOSITE_COL))
        summary_rows.append({
            "label": label, "col": col, "ic20": ic20, "mono": mono, "loo_delta": loo_delta,
            "verdict": verdict, "reasons": reasons,
        })

    summary_table_html = "".join(f"""
      <tr>
        <td class="fname">{r['label']}</td>
        <td>{fmt_rho(r['ic20'])}</td>
        <td>{fmt_num(r['mono'], 2) if r['mono'] is not None else '—'}</td>
        <td>{(f"{r['loo_delta']:+.3f}" if r['loo_delta'] is not None else '—')}</td>
        <td class="verdict-{'keep' if '保留' in r['verdict'] else ('cut' if '剔除' in r['verdict'] else 'watch')}">{r['verdict']}</td>
      </tr>""" for r in summary_rows)

    # ---- IC比較表（跨樣本） ----
    def ic_compare_row(label, col):
        def cell(sample):
            row = next((r for r in sample["ic_rows"] if r["col"] == col), None)
            return row
        f_row, h1_row, h2_row = cell(full), cell(half1), cell(half2)
        cells = ""
        for r in (f_row, h1_row, h2_row):
            d = r["h20"] if r else None
            cells += f"<td>{fmt_rho(d)}</td>"
        return f"<tr><td class='fname'>{label}</td>{cells}</tr>"

    ic_compare_html = "".join(ic_compare_row(label, col) for col, label in all_labels.items())

    # ---- 回測穩定性比較表 ----
    def backtest_compare_row(label, col):
        cells = ""
        for sample in (full, half1, half2):
            bt = sample["backtests"].get(col, {})
            if not bt.get("ok"):
                cells += "<td class='na'>資料不足</td>"
            else:
                cells += f"<td>Sharpe {fmt_num(bt.get('sharpe'))}　MaxDD {fmt_pct(bt.get('max_dd'))}　勝率 {fmt_pct(bt.get('win_rate'))}</td>"
        return f"<tr><td class='fname'>{label}</td>{cells}</tr>"

    backtest_compare_html = "".join(backtest_compare_row(label, col) for col, label in all_labels.items())

    # ---- 各因子詳細頁 ----
    factor_sections = []
    for col, label in FACTOR_COLS.items():
        ic_row = next((r for r in full["ic_rows"] if r["col"] == col), None)
        ic_cells = "".join(f"<td>{fmt_rho(ic_row[f'h{h}'])}</td>" for h in HORIZONS) if ic_row else ""
        bucket = full["buckets"].get(col)
        chart_b64 = bucket_chart_base64(bucket, f"{label}：未來{BUCKET_HORIZON}日平均報酬（依分數五分組）") if bucket else None
        bucket_table_html = ""
        if bucket:
            bucket_table_html = "".join(
                f"<tr><td>{row.label}</td><td>{fmt_num(row.mean_score,1)}</td><td>{fmt_num(row.mean_fwd_ret,2)}%</td>"
                f"<td>{fmt_num(row.median_fwd_ret,2)}%</td><td>{int(row.n)}</td></tr>"
                for row in bucket["table"].itertuples()
            )
        bt = full["backtests"].get(col, {})
        loo_row = next((r for r in full["loo_rows"] if r["col"] == col), None)
        factor_sections.append(f"""
        <section class="card">
          <h2>{label}</h2>
          <h3>資訊係數（IC，非重疊取樣，vs 未來N日ZN報酬）</h3>
          <table class="data-table">
            <tr><th>5日</th><th>10日</th><th>20日</th><th>60日</th></tr>
            <tr>{ic_cells}</tr>
          </table>
          <p class="hint">負值＝符合「恐懼買入」假設方向；正值＝與假設相反（動能延續）。括號內n為非重疊樣本數。</p>

          <h3>分位數分桶：未來{BUCKET_HORIZON}日平均報酬</h3>
          {"<img class='chart' src='data:image/png;base64," + chart_b64 + "'/>" if chart_b64 else "<p class='na'>資料不足，無法分桶</p>"}
          {"<table class='data-table'><tr><th>分組</th><th>平均分數</th><th>平均未來報酬</th><th>中位數未來報酬</th><th>樣本數</th></tr>" + bucket_table_html + "</table>" if bucket else ""}
          <p class="hint">單調性係數（分組序 vs 平均報酬的Spearman rho）：{fmt_num(bucket['monotonicity'],3) if bucket else '—'}（接近-1代表報酬隨分數遞減、符合假設；接近+1代表遞增、動能延續）</p>

          <h3>Leave-one-out：拿掉此因子後對綜合分數IC（20日）的影響</h3>
          <p>完整七項IC：{fmt_rho(loo_row['full_ic']) if loo_row else '—'}　→　拿掉此因子後：{fmt_rho(loo_row['loo_ic']) if loo_row else '—'}
          （Δ = {f"{loo_row['delta']:+.3f}" if loo_row and loo_row['delta'] is not None else '—'}）</p>

          <h3>單因子回測績效（此因子分數單獨當訊號來源）</h3>
          {render_backtest_mini_table(bt)}
        </section>""")

    recommendation_rows = "".join(f"""
      <div class="rec-item">
        <div class="rec-head verdict-{'keep' if '保留' in r['verdict'] else ('cut' if '剔除' in r['verdict'] else 'watch')}">{r['label']} — {r['verdict']}</div>
        <ul>{''.join(f'<li>{reason}</li>' for reason in r['reasons'])}</ul>
      </div>""" for r in summary_rows)

    composite_bt = full["backtests"].get(COMPOSITE_COL, {})

    return f"""<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>因子驗證分析報告</title>
<style>
{REPORT_CSS}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="kicker">FACTOR VALIDATION REPORT</div>
    <h1>因子驗證分析報告</h1>
    <p class="meta">
      資料範圍：{full['date_range'][0]} ~ {full['date_range'][1]}（共{full['n_days']}天）　·
      前後半分割點：{split_date.date()}（前半段{half1['n_days']}天／後半段{half2['n_days']}天）　·
      產生日期：{date.today().isoformat()}
    </p>
    <p class="disclaimer">
      方法論：所有IC一律用「非重疊取樣」（每隔N天取一次樣本，N=驗證的報酬期間）計算Spearman等級相關係數，避免相鄰樣本因報酬窗口重疊而互相高度相關、把統計顯著性灌水。
      策略回測的部位在t日收盤用當天分數決定、套用在t+1日報酬（不使用未來資料）。「恐懼買入」是使用者設定的操作假設（分數低→未來報酬應該高→IC應為負），
      本報告如實呈現每個因子算出來的正負號與數值，不會為了迎合假設而扭曲呈現——這正是這份報告存在的目的。
    </p>
  </header>

  <!-- ===== 1. 摘要頁 ===== -->
  <section class="card">
    <h2><span class="bar"></span>摘要：七項因子總覽</h2>
    <table class="data-table summary-table">
      <tr><th>因子</th><th>IC（20日，非重疊）</th><th>分桶單調性</th><th>Leave-one-out ΔIC</th><th>建議</th></tr>
      {summary_table_html}
    </table>
    <p class="hint">分桶單調性：-1到+1之間，越接近-1代表報酬隨分數（恐懼→貪婪）單調遞減，符合「恐懼買入」假設；越接近+1代表單調遞增（動能延續，與假設相反）。</p>
  </section>

  <!-- ===== 2. 各因子詳細頁 ===== -->
  <h2 class="section-heading"><span class="bar"></span>各因子詳細分析（全樣本）</h2>
  {"".join(factor_sections)}

  <!-- ===== 3. 因子相關係數熱力圖 ===== -->
  <section class="card">
    <h2><span class="bar"></span>因子相關係數矩陣</h2>
    <img class="chart" src="data:image/png;base64,{full['heatmap_b64']}"/>
    <p class="hint">顏色越深（紅或藍）代表兩個因子的歷史分數相關性越高——高度相關的因子可能在講重複的事，可以考慮是否有精簡空間。</p>
  </section>

  <!-- ===== 4. 綜合分數完整回測報告 ===== -->
  <section class="card">
    <h2><span class="bar"></span>綜合分數完整回測報告（quantstats）</h2>
    <p class="hint">部位規則：部位大小 = (50 − 當日綜合分數) / 50，48–52分死區強制空手；t日分數決定的部位套用在t+1日報酬。基準為買進持有ZN期貨不動。</p>
    {render_backtest_mini_table(composite_bt)}
    <div class="tearsheet-wrap">
      <iframe class="tearsheet" srcdoc="{tearsheet_html.replace('"', '&quot;')}"></iframe>
    </div>
  </section>

  <!-- ===== 5. 前後半樣本穩定性比較 ===== -->
  <section class="card">
    <h2><span class="bar"></span>樣本穩定性：全樣本 / 前半段 / 後半段</h2>
    <p class="hint">前半段：{half1['date_range'][0]} ~ {half1['date_range'][1]}（{half1['n_days']}天）　·
      後半段：{half2['date_range'][0]} ~ {half2['date_range'][1]}（{half2['n_days']}天）</p>
    <h3>IC（20日）比較</h3>
    <table class="data-table">
      <tr><th>因子</th><th>全樣本</th><th>前半段</th><th>後半段</th></tr>
      {ic_compare_html}
    </table>
    <h3>回測績效比較</h3>
    <table class="data-table">
      <tr><th>因子</th><th>全樣本</th><th>前半段</th><th>後半段</th></tr>
      {backtest_compare_html}
    </table>
    <p class="hint">如果同一個因子在前後半段的IC正負號都不一樣，代表這個訊號不穩定，可能是被某一段特別的時期（例如2020年疫情、2022年升息）主導，不宜直接套用到現在的市況。</p>
  </section>

  <!-- ===== 6. 建議 ===== -->
  <section class="card">
    <h2><span class="bar"></span>建議</h2>
    <p class="hint">以下判斷規則透明可稽核：綜合考量IC方向與強度、分桶單調性、leave-one-out邊際貢獻。不是自動下定論，帶去跟主管討論時可以直接檢查每一條理由背後的數字。</p>
    {recommendation_rows}
  </section>

</div>
</body>
</html>"""


def render_backtest_mini_table(bt):
    if not bt or not bt.get("ok"):
        return "<p class='na'>資料不足，無法回測</p>"
    return f"""<table class="data-table mini">
      <tr><th>Sharpe</th><th>Sortino</th><th>最大回撤</th><th>年化報酬</th><th>勝率</th><th>年化波動</th><th>樣本天數</th></tr>
      <tr>
        <td>{fmt_num(bt.get('sharpe'))}</td>
        <td>{fmt_num(bt.get('sortino'))}</td>
        <td>{fmt_pct(bt.get('max_dd'))}</td>
        <td>{fmt_pct(bt.get('cagr'))}</td>
        <td>{fmt_pct(bt.get('win_rate'))}</td>
        <td>{fmt_pct(bt.get('vol'))}</td>
        <td>{bt.get('n','—')}</td>
      </tr>
    </table>"""


REPORT_CSS = """
  * { box-sizing: border-box; }
  body { margin:0; background:#f4f5f7; color:#161a23; font-family:-apple-system,BlinkMacSystemFont,"PingFang TC","Noto Sans TC","Segoe UI",Roboto,sans-serif; line-height:1.6; }
  .wrap { max-width:980px; margin:0 auto; padding:44px 24px 80px; }
  header { margin-bottom:36px; }
  .kicker { font-family:ui-monospace,"SF Mono",Menlo,monospace; font-size:11px; letter-spacing:0.12em; color:#a6742a; font-weight:700; margin-bottom:10px; }
  h1 { font-size:30px; font-weight:700; margin:0 0 12px; letter-spacing:-0.02em; }
  .meta { font-size:13px; color:#4a5568; margin:0 0 14px; }
  .disclaimer { font-size:12.5px; color:#667085; background:#fff; border:1px solid #dfe2e8; border-radius:10px; padding:14px 16px; line-height:1.7; }
  .section-heading { font-size:20px; font-weight:700; margin:44px 0 18px; display:flex; align-items:center; gap:10px; }
  .card { background:#fff; border:1px solid #dfe2e8; border-radius:14px; padding:26px 28px; margin-bottom:22px; box-shadow:0 1px 2px rgba(22,26,35,0.04); }
  .card h2 { font-size:19px; font-weight:700; margin:0 0 16px; display:flex; align-items:center; gap:10px; }
  .card h3 { font-size:14px; font-weight:700; margin:22px 0 8px; color:#2d3440; }
  .bar { width:5px; height:20px; background:#1e3a5f; border-radius:2px; display:inline-block; }
  .data-table { width:100%; border-collapse:collapse; font-size:13px; margin:8px 0 4px; }
  .data-table th, .data-table td { text-align:left; padding:7px 10px; border-bottom:1px solid #e5e7eb; font-variant-numeric:tabular-nums; }
  .data-table th { color:#667085; font-weight:600; font-size:11.5px; text-transform:uppercase; letter-spacing:0.03em; }
  .data-table td.fname { font-weight:600; white-space:nowrap; }
  .data-table.mini { max-width:760px; }
  .hint { font-size:12px; color:#667085; margin:6px 0 4px; line-height:1.6; }
  .chart { max-width:100%; display:block; margin:10px 0; border-radius:8px; }
  .na { color:#a7adb9; font-style:italic; }
  .pos { color:#b1592f; font-weight:700; }
  .neg { color:#2f6b4f; font-weight:700; }
  .n { color:#a7adb9; font-size:11px; }
  .verdict-keep { color:#2f6b4f; font-weight:700; }
  .verdict-watch { color:#a6742a; font-weight:700; }
  .verdict-cut { color:#a6362f; font-weight:700; }
  .rec-item { margin-bottom:18px; padding-bottom:16px; border-bottom:1px solid #e5e7eb; }
  .rec-item:last-child { border-bottom:none; margin-bottom:0; padding-bottom:0; }
  .rec-head { font-size:15px; font-weight:700; margin-bottom:6px; }
  .rec-item ul { margin:4px 0 0; padding-left:20px; font-size:13px; color:#4a5568; }
  .rec-item li { margin-bottom:3px; }
  .tearsheet-wrap { margin-top:14px; border:1px solid #dfe2e8; border-radius:10px; overflow:hidden; }
  iframe.tearsheet { width:100%; height:2600px; border:none; display:block; }
"""


if __name__ == "__main__":
    main()
