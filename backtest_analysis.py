"""
回測分析：檢驗恐懼貪婪指數（綜合分數＋各分項分數）對未來報酬有沒有實際的預測力。

方法：
  1. 對每個分數欄位（綜合分數 + 動能/強度/存續期間避險/波動度，Put/Call因無資料跳過），
     計算「當天分數」跟「未來N個交易日ZN期貨報酬率」的順位相關係數（Spearman）。
  2. 用CNN原版的5級分類（極度恐懼/恐懼/中性/貪婪/極度貪婪）把樣本分桶，
     看每一桶未來報酬的平均值、中位數、正報酬比例（勝率）。
  3. 額外用TLT（對利率最敏感的長天期ETF）做交叉驗證，看結論是否穩健。

誠實揭露：未來報酬窗口彼此重疊（overlapping windows），不是獨立樣本，
所以這裡不做嚴謹的統計顯著性檢定（p-value 會被高估），只呈現效果量大小，
並在報告最後說明有效樣本數遠小於天數。
"""
import numpy as np
import pandas as pd
from scipy import stats

df = pd.read_csv("bond_fear_greed_v2.csv", index_col=0, parse_dates=True).sort_index()

HORIZONS = [5, 10, 20, 40, 60]
SCORE_COLS = {
    "composite_score": "綜合分數",
    "momentum_score": "動能",
    "strength_score": "強度",
    "duration_score": "存續期間避險",
    "move_score": "波動度",
    "curve_score": "殖利率曲線形狀",
    "inflation_score": "通膨意外",
    "regime_score": "情境加權分數(實驗性)",
}
BINS = [
    (0, 25, "極度恐懼"),
    (25, 45, "恐懼"),
    (45, 56, "中性"),
    (56, 76, "貪婪"),
    (76, 101, "極度貪婪"),
]


def label_bin(s):
    if pd.isna(s):
        return None
    for lo, hi, name in BINS:
        if lo <= s < hi:
            return name
    return None


def forward_return(price, horizon):
    return (price.shift(-horizon) / price - 1) * 100


def run_target(price_col, price_label):
    print(f"\n{'='*70}\n目標資產：{price_label}（{price_col}）\n{'='*70}")
    price = df[price_col]
    fwd = {h: forward_return(price, h) for h in HORIZONS}

    for score_col, score_label in SCORE_COLS.items():
        score = df[score_col]
        valid_n = score.notna().sum()
        if valid_n < 100:
            print(f"\n--- {score_label} ({score_col}) --- 資料量太少（{valid_n}天），跳過")
            continue
        print(f"\n--- {score_label} ({score_col}) --- 有效天數: {valid_n}")

        # 1) Spearman correlation at each horizon
        print("  順位相關係數 (Spearman, 分數 vs 未來N日報酬):")
        for h in HORIZONS:
            sub = pd.concat([score, fwd[h]], axis=1).dropna()
            if len(sub) < 60:
                continue
            rho, pval = stats.spearmanr(sub.iloc[:, 0], sub.iloc[:, 1])
            print(f"    {h:>3}日: rho={rho:+.3f}  (n={len(sub)}, 重疊樣本，p值僅供參考: {pval:.4f})")

        # 2) bucket analysis at horizon=20 as representative
        h = 20
        sub = pd.concat([score, fwd[h]], axis=1).dropna()
        sub.columns = ["score", "fwd_ret"]
        sub["bucket"] = sub["score"].apply(label_bin)
        print(f"  分桶分析 (未來{h}日報酬，依CNN 5級分類):")
        order = ["極度恐懼", "恐懼", "中性", "貪婪", "極度貪婪"]
        bucket_stats = sub.groupby("bucket")["fwd_ret"].agg(["count", "mean", "median"])
        hit_rate = sub.groupby("bucket")["fwd_ret"].apply(lambda x: (x > 0).mean() * 100)
        for b in order:
            if b not in bucket_stats.index:
                continue
            row = bucket_stats.loc[b]
            hr = hit_rate.loc[b]
            print(f"    {b:>6}: n={int(row['count']):>4}  平均={row['mean']:+6.2f}%  中位數={row['median']:+6.2f}%  正報酬比例={hr:5.1f}%")

        if "極度恐懼" in bucket_stats.index and "極度貪婪" in bucket_stats.index:
            fear_mean = bucket_stats.loc["極度恐懼", "mean"]
            greed_mean = bucket_stats.loc["極度貪婪", "mean"]
            print(f"    極度恐懼 vs 極度貪婪 平均報酬差: {fear_mean - greed_mean:+.2f} 個百分點")


run_target("ZN_futures", "ZN期貨（10年期公債期貨，主標的）")
run_target("TLT", "TLT（長天期公債ETF，交叉驗證）")

print(f"\n{'='*70}\n樣本獨立性提醒\n{'='*70}")
n_days = df["composite_score"].notna().sum()
for h in HORIZONS:
    print(f"  {h}日窗口：{n_days}個重疊樣本 ≈ 約{n_days // h}個真正獨立的不重疊區塊")
