"""
情境（市場環境）拆解分析：檢驗每個因子在不同市場環境下，預測力是否不一樣。

三種情境維度（各自獨立切分，不做三維交叉，避免樣本數碎片化到失去意義）：
  1. Fed利率循環方向：升息 / 暫停 / 降息
     — 用公開報導的FOMC決議日期手動標註，2025年後的日期若需要精確引用請自行核對
       federalreserve.gov 官方紀錄。
  2. 波動度高低：用MOVE指數自己的滾動5年百分位分三檔（低/中/高）
     — 完全用數據客觀切分，不需要人工判斷。
  3. 殖利率曲線形狀：用10年期減2年期利差（2s10s spread）
     — 利差<0 = 倒置；利差上升 = 陡峭化；利差下降 = 平坦化

誠實揭露：原本全樣本的「有效獨立樣本數」就已經只有39~119個，再依情境切分後，
每一格的獨立樣本數會更少（可能只有個位數到十幾個），這裡的結果只能當作
「方向性參考」，不能當作嚴謹的統計推論。報告最後會列出每一格實際的樣本數，
讓你自己判斷可信度。
"""
import io
import numpy as np
import pandas as pd
import requests
from scipy import stats

TREASURY_URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve"
    "&field_tdr_date_value={year}&page&_format=csv"
)


def fetch_treasury_2yr(start_year, end_year):
    frames = []
    for year in range(start_year, end_year + 1):
        resp = requests.get(TREASURY_URL.format(year=year), timeout=30)
        resp.raise_for_status()
        frames.append(pd.read_csv(io.StringIO(resp.text)))
    combined = pd.concat(frames, ignore_index=True)
    combined["Date"] = pd.to_datetime(combined["Date"], format="%m/%d/%Y")
    combined = combined.set_index("Date").sort_index()
    col2 = [c for c in combined.columns if c.strip() == "2 Yr"][0]
    return combined[col2].rename("UST_2Yr")


df = pd.read_csv("bond_fear_greed_v2.csv", index_col=0, parse_dates=True).sort_index()

print("下載 Treasury 2年期殖利率 ...")
ust2 = fetch_treasury_2yr(df.index.min().year, df.index.max().year)
df["UST_2Yr"] = ust2.reindex(df.index).ffill()
df["curve_spread"] = df["UST_10Yr"] - df["UST_2Yr"]

# ---------------------------------------------------------------- 情境1：Fed利率循環方向
# 公開報導的FOMC決議日期（2025年後若需精確引用請自行核對 federalreserve.gov）
FED_CYCLE_BOUNDARIES = [
    ("2020-01-01", "2022-03-16", "暫停(零利率)"),
    ("2022-03-17", "2023-07-26", "升息循環"),
    ("2023-07-27", "2024-09-17", "暫停(高原期)"),
    ("2024-09-18", "2026-12-31", "降息循環"),
]


def fed_cycle_label(d):
    for start, end, label in FED_CYCLE_BOUNDARIES:
        if pd.Timestamp(start) <= d <= pd.Timestamp(end):
            return label
    return None


df["regime_fed"] = df.index.map(fed_cycle_label)

# ---------------------------------------------------------------- 情境2：波動度高低（MOVE絕對水位門檻）
# 改版：原本用「MOVE自身滾動5年百分位」切分，因5年窗口內含2020年COVID的MOVE歷史新高，
# 把「高波動」的門檻拉得太高，導致近幾年幾乎沒有一天達標（高波動桶只有26天，樣本量不可用）。
# 改用固定絕對水位門檻（債券波動度評論常見的參考區間：<70平靜、70-100正常、>=100緊張），
# 不隨時間窗口變動，三個桶的天數更平衡。
def vol_regime_label(move_value):
    if pd.isna(move_value):
        return None
    if move_value < 70:
        return "低波動"
    if move_value < 100:
        return "中波動"
    return "高波動"


df["regime_vol"] = df["MOVE_index"].apply(vol_regime_label)

# ---------------------------------------------------------------- 情境3：殖利率曲線形狀
spread_chg = df["curve_spread"].diff(20)  # 過去20日利差變化，判斷陡峭化/平坦化方向


def curve_regime_label(row_spread, row_chg):
    if pd.isna(row_spread):
        return None
    if row_spread < 0:
        return "倒置"
    if pd.isna(row_chg):
        return None
    return "陡峭化" if row_chg > 0 else "平坦化"


df["regime_curve"] = [curve_regime_label(s, c) for s, c in zip(df["curve_spread"], spread_chg)]

# ---------------------------------------------------------------- 分析主體
SCORE_COLS = {
    "composite_score": "綜合分數",
    "momentum_score": "動能",
    "strength_score": "強度",
    "duration_score": "存續期間避險",
    "move_score": "波動度",
}
HORIZONS = [20, 40]


def forward_return(price, horizon):
    return (price.shift(-horizon) / price - 1) * 100


fwd_zn = {h: forward_return(df["ZN_futures"], h) for h in HORIZONS}


def analyze_regime_dim(regime_col, regime_name, order):
    print(f"\n{'#'*76}\n情境維度：{regime_name}\n{'#'*76}")
    for h in HORIZONS:
        print(f"\n----- 未來{h}日ZN期貨報酬，依「{regime_name}」分組 -----")
        for regime_val in order:
            mask = df[regime_col] == regime_val
            n_days = mask.sum()
            if n_days < 30:
                print(f"\n  【{regime_val}】天數過少（{n_days}天），跳過")
                continue
            print(f"\n  【{regime_val}】（{n_days}個交易日）")
            for score_col, score_label in SCORE_COLS.items():
                sub = pd.concat([df.loc[mask, score_col], fwd_zn[h].loc[mask]], axis=1).dropna()
                sub.columns = ["score", "fwd"]
                if len(sub) < 30:
                    print(f"    {score_label:>6}: 樣本太少（{len(sub)}），跳過")
                    continue
                rho, pval = stats.spearmanr(sub["score"], sub["fwd"])
                indep_n = max(1, len(sub) // h)
                print(f"    {score_label:>6}: rho={rho:+.3f}  (重疊樣本n={len(sub)}, 約{indep_n}個獨立區塊)")


analyze_regime_dim("regime_fed", "Fed利率循環方向", ["升息循環", "暫停(高原期)", "暫停(零利率)", "降息循環"])
analyze_regime_dim("regime_vol", "波動度高低（MOVE絕對水位）", ["低波動", "中波動", "高波動"])
analyze_regime_dim("regime_curve", "殖利率曲線形狀", ["倒置", "陡峭化", "平坦化"])

# ---------------------------------------------------------------- 情境涵蓋天數總覽
print(f"\n{'#'*76}\n情境分佈總覽（天數）\n{'#'*76}")
print("\nFed循環：")
print(df["regime_fed"].value_counts())
print("\n波動度：")
print(df["regime_vol"].value_counts())
print("\n殖利率曲線：")
print(df["regime_curve"].value_counts())

df.to_csv("bond_regime_tagged.csv")
print("\n已輸出含情境標籤的完整資料：bond_regime_tagged.csv")

# ================================================================
# 第一版動態權重草案：以Fed循環為主軸（樣本數最大、規律最清楚的情境維度）
# ================================================================
print(f"\n{'#'*76}\nFed循環動態權重草案\n{'#'*76}")
print("""
方法（透明、可重現，不是拍腦袋）：
  1. 取每個Fed循環階段下，各因子對「未來40日ZN期貨報酬」的Spearman rho
  2. 負相關或極弱相關（|rho|<0.05）的因子，權重設一個小地板值（5%），
     不要完全歸零——因為樣本數不足以完全確定「真的沒用」，歸零風險太高
  3. 其餘因子的權重 = rho值 / 該情境下所有因子rho值的加總，等比例分配
  4. 目前Put/Call因為沒有歷史資料，先不納入權重草案，等資料補齊後要重跑
""")

FLOOR = 0.05
h_weight = 40
FACTOR_COLS = {k: v for k, v in SCORE_COLS.items() if k != "composite_score"}
weight_table = {}
for regime_val in ["升息循環", "暫停(高原期)", "暫停(零利率)", "降息循環"]:
    mask = df["regime_fed"] == regime_val
    rhos = {}
    for score_col, score_label in FACTOR_COLS.items():
        sub = pd.concat([df.loc[mask, score_col], fwd_zn[h_weight].loc[mask]], axis=1).dropna()
        sub.columns = ["score", "fwd"]
        if len(sub) < 30:
            rhos[score_label] = 0.0
            continue
        rho, _ = stats.spearmanr(sub["score"], sub["fwd"])
        rhos[score_label] = rho if pd.notna(rho) else 0.0

    floored = {k: max(v, FLOOR) for k, v in rhos.items()}
    total = sum(floored.values())
    weights = {k: v / total for k, v in floored.items()}
    weight_table[regime_val] = weights

    print(f"\n【{regime_val}】原始rho → 權重：")
    for k in FACTOR_COLS.values():
        print(f"    {k:>6}: rho={rhos[k]:+.3f}  →  權重 {weights[k]*100:5.1f}%")

print("\n（等權重版本作為對照：四項因子每項一律25%，Put/Call有資料後加入會變20%）")


# ---- 用草案權重組一版「情境加權綜合分數」，跟現行等權重版本比較預測力 ----
def regime_weighted_score(row):
    regime = row["regime_fed"]
    if regime not in weight_table:
        return np.nan
    w = weight_table[regime]
    total_w, total_score = 0.0, 0.0
    for score_col, score_label in FACTOR_COLS.items():
        v = row[score_col]
        if pd.isna(v):
            continue
        total_score += v * w[score_label]
        total_w += w[score_label]
    if total_w == 0:
        return np.nan
    return total_score / total_w


df["regime_weighted_score"] = df.apply(regime_weighted_score, axis=1)

print(f"\n{'#'*76}\n情境加權分數 vs 等權重分數：預測力比較（全樣本，未來{h_weight}日ZN報酬）\n{'#'*76}")
for label, col in [("現行等權重綜合分數", "composite_score"), ("情境加權綜合分數（草案）", "regime_weighted_score")]:
    sub = pd.concat([df[col], fwd_zn[h_weight]], axis=1).dropna()
    sub.columns = ["score", "fwd"]
    rho, pval = stats.spearmanr(sub["score"], sub["fwd"])
    print(f"  {label}: rho={rho:+.3f}  (n={len(sub)})")

print("""
【重要警告】這個比較是「用同一份資料先找規律、再用規律去驗證規律」（in-sample），
本來就會比等權重版本表現好看，不能當作「情境加權真的比較準」的證據。
真正有意義的驗證，必須是：拿這套權重規則去測「還沒用來推導權重的另一段時間」的資料
（out-of-sample），但我們目前只有約6年資料，扣掉拿來找規律的部分，剩下可獨立驗證的
時間already不夠長。這份草案的定位是「有數據支持的起點」，不是「已驗證的最終方案」。
""")

