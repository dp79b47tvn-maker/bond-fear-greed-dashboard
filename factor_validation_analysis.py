"""
因子驗證分析函式庫 —— IC、分桶、單調性、相關矩陣、統計分布等共用計算。

這個模組是 factor_screening.py（因子開發與篩選平台）的函式庫，本身沒有進入點、
不會單獨執行。所有對外頁面都由 factor_screening.py 產生。

2026-08-11：原本這裡還有一個 main()，會產生 chart/factor_validation_report.html
（獨立的「因子驗證報告」頁）。那一頁 2026-07-30 就從導覽列移除、內容遷移到儀表板
與因子篩選平台，之後也不再每日重新產生；報告內容停留在舊七因子時代，跟現行的兩因子
組成已經對不上，因此連同 main() 與只有它在用的 5 個 render 函式（共364行）一起移除。
需要看歷史版本請查 git。

方法論注意事項（各報告頁面也會重複這些話）：
  - 部位方向假設「恐懼買入」（分數低→未來報酬應該高）。這是使用者的操作邏輯，
    但實測發現多數因子在多數時期是動能延續。這裡如實呈現算出來的正負號與數值，
    不會為了迎合假設而扭曲呈現方式。
  - 部位在t日收盤用當天分數決定，套用在t+1日的報酬上，不使用未來資料。
  - IC同時提供非重疊與重疊取樣兩個版本。非重疊避免相鄰樣本報酬窗口重疊灌水統計
    顯著性，但樣本數天生就少；重疊版本樣本間高度自相關，只看數值、不附顯著性檢定。
"""
import base64
import io
import json
import warnings
from datetime import date

import glob as _glob

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as _fm
import matplotlib.pyplot as plt
import nav_bar
import page_style
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats

warnings.filterwarnings("ignore")

import quantstats as qs

import update_dashboard as ud

# 中文字型設定必須放在所有import之後才會生效:seaborn/quantstats的import過程
# 會各自套用自己的預設樣式,連帶把font.sans-serif重設回matplotlib預設值
# (實測過,import quantstats會把上面設的字型整個蓋掉)。
# Linux CI runner裝的是fonts-noto-cjk這種.ttc合集檔,matplotlib自動掃描常常抓不到
# 裡面的個別語系名稱(例如"Noto Sans CJK TC"),所以直接找檔案路徑手動註冊、
# 用註冊後回傳的實際名稱,而不是猜測字型名稱字串。Mac本機沒有這些路徑,
# glob抓不到東西,就照舊退回PingFang TC,行為不變。
_cjk_font_names = []
for _p in (_glob.glob("/usr/share/fonts/**/*CJK*", recursive=True)
           + _glob.glob("/usr/share/fonts/**/*NotoSansCJK*", recursive=True)):
    try:
        _fm.fontManager.addfont(_p)
        _cjk_font_names.append(_fm.FontProperties(fname=_p).get_name())
    except Exception:
        pass
matplotlib.rcParams["font.sans-serif"] = (
    ["PingFang TC", "Heiti TC", "Arial Unicode MS"]
    + list(dict.fromkeys(_cjk_font_names))
    + ["Noto Sans CJK TC", "Noto Sans CJK JP", "WenQuanYi Zen Hei", "DejaVu Sans"]
)
matplotlib.rcParams["axes.unicode_minus"] = False

# ---------------------------------------------------------------- 設定
# 唯一事實來源:參數來自 factor_definitions.json(經由 update_dashboard.DEFS 共用同一份)
_V = ud.DEFS["validation"]
TARGET = _V["target"]
HORIZONS = _V["horizons"]
LOO_HORIZON = _V["loo_horizon"]
BUCKET_HORIZON = _V["bucket_horizon"]
N_BUCKETS = _V["n_buckets"]
DEAD_ZONE = tuple(_V["dead_zone"])

# ---- 10年期／10分組分位數分桶分析（附加模組，不取代上面5組版本） ----
DECILE_YEARS = _V["decile_years"]
DECILE_N_BUCKETS = _V["decile_n_buckets"]
DECILE_HORIZON = _V["decile_horizon"]
DECILE_MIN_N_WARN = _V["decile_min_n_warn"]
# 滾動百分位需要暖身期，往前多抓視窗長度+margin原始資料，才能讓分數本身有滿N年可用
PERCENTILE_LOOKBACK_DAYS = ud.DEFS["global"]["percentile_window_days"] + 30

# 2026-08-11：改成從 factor_definitions.json 動態衍生，不再手寫死一份。
# 原因：官方因子從七項改成兩項(動能/銅金比)時，這裡忘了同步，gate4_incremental()
# 會拿已經不存在的因子當「現有因子」比較基準。名稱取 name_tpl 破折號前的短名
# （例："動能 — US 10Y {sma_window}日均線價差" → "動能"）。
FACTOR_COLS = {
    f["score_col"]: f["name_tpl"].split("—")[0].strip()
    for f in ud.DEFS["factors"]
}
COMPOSITE_COL = "composite_score"
COMPOSITE_LABEL = "綜合分數"

BUCKET_LABELS = ["極度恐懼", "恐懼", "中性", "貪婪", "極度貪婪"]


# ================================================================ 資料


def split_halves(df):
    mid = df.index[len(df) // 2]
    h1 = df.loc[df.index < mid].copy()
    h2 = df.loc[df.index >= mid].copy()
    return h1, h2, mid


def forward_return(price_or_yield, horizon, target=TARGET):
    # 若標的為 UST_10Yr 殖利率，計算單位為基點變動 (bp) = (t+h 殖利率 - t 殖利率) * 100
    if target == "UST_10Yr" or getattr(price_or_yield, "name", "") == "UST_10Yr":
        return (price_or_yield.shift(-horizon) - price_or_yield) * 100
    return (price_or_yield.shift(-horizon) / price_or_yield - 1) * 100


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


def overlapping_ic(df, score_col, horizon, target=TARGET):
    """重疊取樣版本:每天都取樣、不像non_overlapping_ic那樣每隔horizon天才取一筆。
    相鄰樣本的報酬窗口高度重疊、彼此高度自相關,樣本數雖然遠大於非重疊版本,
    但「有效」樣本數並沒有真的變多——所以這裡不算、不回傳pval,report端也不會
    顯示顯著性字樣,只把rho數值當非重疊版本的參考對照，不能拿來判斷統計顯著性。"""
    sub = df[[score_col]].copy()
    sub["fwd"] = forward_return(df[target], horizon)
    sub = sub.dropna()
    if len(sub) < 10:
        return {"rho": None, "n": len(sub)}
    rho, _ = stats.spearmanr(sub[score_col], sub["fwd"])
    return {"rho": float(rho) if pd.notna(rho) else None, "n": len(sub)}


def ic_table(df, score_cols_map, horizons=HORIZONS):
    rows = []
    for col, label in score_cols_map.items():
        if col not in df.columns:
            continue
        row = {"factor": label, "col": col}
        for h in horizons:
            row[f"h{h}"] = non_overlapping_ic(df, col, h)
            row[f"h{h}_overlap"] = overlapping_ic(df, col, h)
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
    unit_label = "bp" if TARGET == "UST_10Yr" else "%"
    ax.set_ylabel(f"未來{BUCKET_HORIZON}日平均變動 ({unit_label})", fontsize=9)
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


def render_distribution_analysis_4panel_base64(df, score_col, label, horizon=20, target=TARGET):
    """
    Part A: 為因子產出 4-panel 完整統計分布與極端兩端檢視圖 (Base64 PNG):
    1. 箱型圖 (Boxplot) 按固定門檻與極端尾端分桶
    2. 勝率 % 與平均超額 (bp) 長條圖
    3. 小提琴分佈密度圖 (Violin Plot)
    4. 全數據散佈圖 + 非線性平滑回歸線 (Scatter & Rolling Trend Line)
    """
    if score_col not in df.columns or target not in df.columns:
        return None, None

    sub = df[[score_col, target]].copy().dropna()
    if len(sub) < 50:
        return None, None

    # 計算未來 N 日報酬 (bp)
    if target == "UST_10Yr" or "UST_10Yr" in str(target):
        sub["fwd_bp"] = (sub[target].shift(-horizon) - sub[target]) * 100
    else:
        sub["fwd_bp"] = (sub[target].shift(-horizon) / sub[target] - 1) * 100

    sub = sub.dropna(subset=["fwd_bp"])
    if len(sub) < 50:
        return None, None

    # 超額報酬 (減去全樣本平均)
    mean_baseline = sub["fwd_bp"].mean()
    sub["excess_bp"] = sub["fwd_bp"] - mean_baseline

    # 分桶定義
    buckets_def = [
        ("0-5% 尾端", sub[score_col] <= 5),
        ("0-24 極度恐懼", (sub[score_col] >= 0) & (sub[score_col] < 25)),
        ("25-44 恐懼", (sub[score_col] >= 25) & (sub[score_col] < 45)),
        ("45-55 中性", (sub[score_col] >= 45) & (sub[score_col] < 56)),
        ("56-75 貪婪", (sub[score_col] >= 56) & (sub[score_col] < 76)),
        ("76-100 極度貪婪", (sub[score_col] >= 76) & (sub[score_col] <= 100)),
        ("95-100% 尾端", sub[score_col] >= 95),
    ]

    bucket_data = []
    bucket_stats = []
    colors = ["#1b4332", "#2f6b4f", "#5c8a6e", "#6b7280", "#b1592f", "#a6362f", "#661111"]

    for b_label, mask in buckets_def:
        vals = sub.loc[mask, "excess_bp"].values
        n_cnt = len(vals)
        if n_cnt > 0:
            m_val = np.mean(vals)
            med_val = np.median(vals)
            # 勝率: 恐懼端期待殖利率下降(價格上漲, excess_bp < 0)，貪婪端期待殖利率上升(excess_bp > 0)
            win_cnt = np.sum(vals < 0) if ("恐懼" in b_label or "0-5%" in b_label) else np.sum(vals > 0)
            win_rate = (win_cnt / n_cnt) * 100
        else:
            m_val, med_val, win_rate = 0, 0, 0
        bucket_data.append(vals if n_cnt > 0 else np.array([0]))
        bucket_stats.append({
            "label": b_label, "n": n_cnt, "mean": m_val, "median": med_val, "win_rate": win_rate
        })

    # 繪製 4-panel 2x2 網格圖
    fig, axes = plt.subplots(2, 2, figsize=(13, 9.5), dpi=140)
    fig.suptitle(f"{label} · 未來{horizon}日報酬統計分布與極端檢視 (基準平均={mean_baseline:+.2f}bp)", fontsize=13, fontweight="bold", y=0.98)

    labels = [b["label"] for b in bucket_stats]

    # 1. 箱型圖 Boxplot
    ax1 = axes[0, 0]
    bp = ax1.boxplot(bucket_data, tick_labels=labels, patch_artist=True, showfliers=True,
                     flierprops=dict(marker='o', markersize=3, alpha=0.4))
    for patch, color in zip(bp['boxes'], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.6)
    ax1.axhline(0, color="#888", linestyle="--", linewidth=0.8)
    ax1.set_title("1. 各分桶超額報酬箱型圖 (中位數/IQR/離群值/樣本數n)", fontsize=10.5, fontweight="bold")
    ax1.set_ylabel(f"未來{horizon}日超額變動 (bp)", fontsize=9)
    ax1.tick_params(axis='x', rotation=25, labelsize=8)
    # 標註 n 樣本數
    for i, s in enumerate(bucket_stats):
        ax1.text(i + 1, ax1.get_ylim()[1] * 0.88, f"n={s['n']}", ha="center", fontsize=7.5, fontweight="bold", color="#333")

    # 2. 勝率 % 與平均超額 bp
    ax2 = axes[0, 1]
    bars = ax2.bar(labels, [s["mean"] for s in bucket_stats], color=colors, alpha=0.7, width=0.55)
    ax2.axhline(0, color="#888", linestyle="--", linewidth=0.8)
    ax2.set_title(f"2. 各分桶平均超額報酬 (bp) 與 勝率 (%)", fontsize=10.5, fontweight="bold")
    ax2.set_ylabel(f"平均超額變動 (bp)", fontsize=9)
    ax2.tick_params(axis='x', rotation=25, labelsize=8)
    for bar, s in zip(bars, bucket_stats):
        v = s["mean"]
        ax2.annotate(f"{v:+.2f}bp\n(勝率{s['win_rate']:.0f}%)",
                     (bar.get_x() + bar.get_width() / 2, v),
                     textcoords="offset points", xytext=(0, 5 if v >= 0 else -18),
                     ha="center", fontsize=7.5, fontweight="bold")

    # 3. 小提琴圖 Violin Plot
    ax3 = axes[1, 0]
    try:
        parts = ax3.violinplot(bucket_data, showmeans=True, showmedians=True)
        for pc, color in zip(parts['bodies'], colors):
            pc.set_facecolor(color)
            pc.set_alpha(0.5)
    except Exception:
        pass
    ax3.axhline(0, color="#888", linestyle="--", linewidth=0.8)
    ax3.set_xticks(range(1, len(labels) + 1))
    ax3.set_xticklabels(labels, rotation=25, fontsize=8)
    ax3.set_title("3. 各分桶報酬小提琴密度圖 (檢視單峰/雙峰/偏態)", fontsize=10.5, fontweight="bold")
    ax3.set_ylabel(f"未來{horizon}日超額變動 (bp)", fontsize=9)

    # 4. 全數據散佈圖 + 滾動平滑趨勢線
    ax4 = axes[1, 1]
    ax4.scatter(sub[score_col], sub["excess_bp"], alpha=0.25, color="#1e3a5f", s=10, label="每日樣本點")
    ax4.axhline(0, color="#888", linestyle="--", linewidth=0.8)
    ax4.axvline(25, color="#2f6b4f", linestyle=":", alpha=0.7, label="恐懼門檻 25")
    ax4.axvline(75, color="#a6362f", linestyle=":", alpha=0.7, label="貪婪門檻 75")

    # 計算滾動中位數 trend
    sub_sorted = sub.sort_values(score_col)
    roll_trend = sub_sorted["excess_bp"].rolling(window=150, min_periods=30, center=True).mean()
    ax4.plot(sub_sorted[score_col], roll_trend, color="#d97706", linewidth=2.5, label="非線性趨勢線 (Rolling Mean)")

    ax4.set_title("4. 全分數對報酬散佈圖 (檢視極端兩端是否勾回反轉)", fontsize=10.5, fontweight="bold")
    ax4.set_xlabel("當日因子分數 (0-100)", fontsize=9)
    ax4.set_ylabel(f"未來{horizon}日超額變動 (bp)", fontsize=9)
    ax4.legend(fontsize=7.5, loc="upper right")

    fig.tight_layout()
    b64_str = fig_to_base64(fig)
    return b64_str, bucket_stats


# ================================================================ 附加：10年期／10分組分位數分桶分析
def fetch_extended_history(years):
    """為了讓分桶分析能涵蓋足足N年的『有效分數』，往前多抓5年當作5年滾動
    百分位的暖身資料——這跟 update_dashboard.py 對 FETCH_START_DATE 的處理邏輯一致
    （它自己是往前抓到2014-06給5年百分位暖身，這裡同樣的道理，只是抓更早）。

    直接重用 update_dashboard.py 既有的抓取／計分函式（fetch_yahoo_close /
    fetch_treasury_yield_curve / fetch_fred_series / compute_scores），暫時覆寫它的
    FETCH_START_DATE / END_DATE 這兩個模組全域變數——不會影響正式儀表板，那是
    另一個獨立執行的程序（python3 update_dashboard.py），彼此不共用執行狀態。

    這裡刻意不快取成CSV：抓取只需要約10-20秒，直接每次重跑都拿最新資料，
    跟專案「資料更新後可重複執行」的原則一致，不會有快取跟正式資料兜不起來的風險。
    """
    target_start = pd.Timestamp(date.today()) - pd.Timedelta(days=years * 365 + PERCENTILE_LOOKBACK_DAYS)
    start_str = target_start.strftime("%Y-%m-01")
    print(f"\n[{years}年分桶分析] 抓取延伸歷史資料（{years}年分析期間 + 5年百分位暖身期），"
          f"起始日設為 {start_str} ...")

    ud.FETCH_START_DATE = start_str
    ud.END_DATE = date.today().isoformat()

    raw_ranges = {}

    # 抓什麼由 factor_definitions.json 的 data_sources 決定，跟 update_dashboard 共用
    # 同一支 fetch_declared_sources()——兩條路徑不可能再各抓各的而不同步。
    # (2026-08-11 因子從七項改兩項時，這裡曾經因為沒跟著改而 KeyError: 'HG_futures'，
    #  整個篩選平台跑不動；改成共用之後這種脫鉤在結構上就不可能發生了。)
    def _record(name, s):
        if len(s):
            raw_ranges[name] = (s.index.min(), s.index.max(), len(s))

    series_list = ud.fetch_declared_sources(on_fetched=_record)

    print(f"[{years}年分桶分析] 各原始資料來源實際可回溯範圍：")
    for name, (lo, hi, n) in raw_ranges.items():
        print(f"    {name}: {lo.date()} ~ {hi.date()}（{n}筆），"
              f"{f'足夠支撐{years}年分析' if lo <= target_start + pd.Timedelta(days=31) else f'⚠️ 不足{years}年+暖身期，將如實反映在分數的實際起始日'}")

    full_index = pd.date_range(ud.FETCH_START_DATE, ud.END_DATE, freq="D")
    df = pd.concat(series_list, axis=1, sort=True).reindex(full_index)
    df.index.name = "Date"
    df = df.sort_index().ffill().dropna(how="all")
    df = ud.compute_scores(df)
    return df, raw_ranges


def score_actual_range(df, col):
    """回傳這個分數欄位『實際』(而非假設) 有值的第一天／最後一天／筆數。"""
    valid = df[col].dropna()
    if len(valid) == 0:
        return None
    return {"start": valid.index.min(), "end": valid.index.max(), "n": len(valid)}


def decile_bucket_analysis(df, score_col, horizon=DECILE_HORIZON, buckets=DECILE_N_BUCKETS, target=TARGET):
    """跟 bucket_analysis() 邏輯相同（qcut等分＋看未來N日平均報酬），但兩個關鍵差異：
    (1) 分10組不是5組；(2) 用非重疊取樣（每隔horizon筆才取一次樣本），不是每天滾動——
    避免相鄰樣本點因報酬窗口重疊而互相高度相關，讓10組情況下樣本本來就少的分組平均值
    更容易失真的問題不要雪上加霜。
    """
    sub = df[[score_col]].copy()
    sub["fwd"] = forward_return(df[target], horizon)
    sub = sub.dropna()
    if len(sub) < buckets * 3:
        return None
    actual_start, actual_end = sub.index.min(), sub.index.max()
    sampled = sub.iloc[::horizon].copy()
    if len(sampled) < buckets:
        return None
    try:
        sampled["bucket"] = pd.qcut(sampled[score_col], buckets, labels=False, duplicates="drop")
    except ValueError:
        return None
    grp = sampled.groupby("bucket").agg(
        mean_score=(score_col, "mean"), mean_fwd_ret=("fwd", "mean"),
        median_fwd_ret=("fwd", "median"), n=("fwd", "count"),
    ).reset_index()
    grp["label"] = [f"D{i+1}" for i in range(len(grp))]
    return {
        "table": grp, "date_range": (actual_start, actual_end),
        "n_sampled_total": len(sampled), "n_daily_total": len(sub),
    }


def decile_chart_base64(result, title, buckets, horizon, warn_n=DECILE_MIN_N_WARN):
    if result is None:
        return None
    grp = result["table"]
    n_bars = len(grp)
    cmap = plt.get_cmap("RdYlGn_r")  # D1(恐懼)偏綠、D{n}(貪婪)偏紅，跟儀表板色彩語意一致的方向
    colors = [cmap(i / max(1, n_bars - 1)) for i in range(n_bars)]
    fig, ax = plt.subplots(figsize=(max(7.6, n_bars * 0.55), 3.7), dpi=140)
    bars = ax.bar(grp["label"], grp["mean_fwd_ret"], color=colors, width=0.7)
    ax.axhline(0, color="#888", linewidth=0.8)
    for bar, row in zip(bars, grp.itertuples()):
        low_n = row.n < warn_n
        if low_n:
            bar.set_hatch("///")
            bar.set_edgecolor("#a6362f")
            bar.set_linewidth(1.2)
        v = row.mean_fwd_ret
        label = f"n={row.n}" + ("*" if low_n else "")
        ax.annotate(label, (bar.get_x() + bar.get_width() / 2, v),
                    textcoords="offset points", xytext=(0, 4 if v >= 0 else -13), ha="center",
                    fontsize=6.5 if n_bars > 12 else 7, color="#a6362f" if low_n else "#444",
                    fontweight=("bold" if low_n else "normal"), rotation=90 if n_bars > 12 else 0)
    unit_label = "bp" if TARGET == "UST_10Yr" else "%"
    ax.set_ylabel(f"Mean fwd {horizon}-day change ({unit_label})", fontsize=9)
    ax.set_xlabel(f"D1 (Most Fear)  →  D{buckets} (Most Greed)", fontsize=8.5, color="#667085")
    ax.set_title(title, fontsize=10)
    ax.tick_params(labelsize=7.5 if n_bars > 12 else 8)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    fig.tight_layout()
    return fig_to_base64(fig)




# ================================================================ 4. Leave-one-out
def composite_loo(df, exclude_col, factor_cols):
    cols = [c for c in factor_cols if c != exclude_col]
    return df[cols].mean(axis=1, skipna=True)


def leave_one_out_table(df, factor_cols_map, horizon=LOO_HORIZON):
    full_ic = non_overlapping_ic(df, COMPOSITE_COL, horizon)
    full_ic_overlap = overlapping_ic(df, COMPOSITE_COL, horizon)
    rows = []
    for col, label in factor_cols_map.items():
        alt_score = composite_loo(df, col, list(factor_cols_map.keys()))
        tmp = df.copy()
        tmp["_loo"] = alt_score
        loo_ic = non_overlapping_ic(tmp, "_loo", horizon)
        loo_ic_overlap = overlapping_ic(tmp, "_loo", horizon)
        delta = None
        if full_ic["rho"] is not None and loo_ic["rho"] is not None:
            delta = loo_ic["rho"] - full_ic["rho"]
        delta_overlap = None
        if full_ic_overlap["rho"] is not None and loo_ic_overlap["rho"] is not None:
            delta_overlap = loo_ic_overlap["rho"] - full_ic_overlap["rho"]
        rows.append({
            "factor": label, "col": col, "full_ic": full_ic, "loo_ic": loo_ic, "delta": delta,
            "full_ic_overlap": full_ic_overlap, "loo_ic_overlap": loo_ic_overlap, "delta_overlap": delta_overlap,
        })
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




# ================================================================ HTML 組裝
def fmt_rho(d):
    if d is None:
        return f'<span class="na">無資料</span>'
    if isinstance(d, (int, float)):
        cls = "neg" if d < 0 else "pos"
        return f'<span class="{cls}">{d:+.3f}</span>'
    if d.get("rho") is None:
        return f'<span class="na">無資料</span>'
    rho = d["rho"]
    cls = "neg" if rho < 0 else "pos"
    return f'<span class="{cls}">{rho:+.3f}</span> <span class="n">(n={d.get("n", "")})</span>'


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






# ---------------------------------------------------------------- HTML 模板


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
  body { margin:0; background:#f4f5f7; color:#161a23; font-family:-apple-system,BlinkMacSystemFont,"PingFang TC","Noto Sans TC","Segoe UI",Roboto,sans-serif; line-height:__BASE_LINE_HEIGHT__; }
  .wrap { max-width:__CONTENT_MAX_WIDTH__; margin:0 auto; padding:44px 24px 80px; }
  header { margin-bottom:36px; }
  .kicker { font-family:ui-monospace,"SF Mono",Menlo,monospace; font-size:11px; letter-spacing:0.12em; color:#a6742a; font-weight:700; margin-bottom:10px; }
  h1 { font-size:__H1_SIZE__; font-weight:700; margin:0 0 12px; letter-spacing:-0.02em; }
  .meta { font-size:13px; color:#4a5568; margin:0 0 14px; }
  .disclaimer { font-size:12.5px; color:#667085; background:#fff; border:1px solid #dfe2e8; border-radius:10px; padding:14px 16px; line-height:1.7; max-width:__LEDE_MAX_WIDTH__; }
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
  .decile-block { margin-bottom:32px; padding-bottom:26px; border-bottom:1px solid #e5e7eb; }
  .decile-block:last-child { border-bottom:none; margin-bottom:0; padding-bottom:0; }
  .decile-block h3 { font-size:15px; font-weight:700; margin:0 0 6px; color:#2d3440; }
  .data-table tr.low-n td { color:#a6362f; }
  .warn-hint { color:#a6362f; }
"""
# 統一間距/字級/行高數字(page_style.py)——這裡沒有CSS變數/深色模式(維持現狀，
# 這次不補)，只是把.wrap寬度/h1字級/行高/說明段落可讀寬度這幾個純量值換成跟
# 其他四頁一致的數字，用字串取代而不是f-string插值，避免整份CSS(41行、
# 每行都有花括號)要逐一跳脫的風險。
REPORT_CSS = (REPORT_CSS
              .replace("__BASE_LINE_HEIGHT__", page_style.BASE_LINE_HEIGHT)
              .replace("__CONTENT_MAX_WIDTH__", page_style.CONTENT_MAX_WIDTH)
              .replace("__H1_SIZE__", page_style.H1_SIZE)
              .replace("__LEDE_MAX_WIDTH__", page_style.LEDE_MAX_WIDTH))


