"""
驗證「情境加權分數」的樣本外表現。

只看 regime_weights_v1.json 的 freeze_date 之後才發生的資料——這段是權重
推導時完全沒看過的資料，才是誠實的樣本外驗證。freeze_date之前的資料
不列入這裡的驗證（那是拿來推導權重用的，本來就會偏樂觀）。

用法：
    python3 validate_regime_weights.py
建議每隔一段時間（例如每季）執行一次，看樣本外天數累積得夠不夠、
表現有沒有跟推導時的預期一致。
"""
import json

import pandas as pd
from scipy import stats

import regime_lib

with open("regime_weights_v1.json", encoding="utf-8") as f:
    snapshot = json.load(f)

freeze_date = pd.Timestamp(snapshot["freeze_date"])
weight_table = snapshot["weight_by_regime"]
horizon = snapshot["method"]["horizon_trading_days"]

df = pd.read_csv("bond_fear_greed_v2.csv", index_col=0, parse_dates=True).sort_index()
df["regime_fed"] = df.index.map(regime_lib.fed_cycle_label)


def forward_return(price, h):
    return (price.shift(-h) / price - 1) * 100


fwd = forward_return(df["ZN_futures"], horizon)


def regime_weighted_score(row):
    regime = row["regime_fed"]
    if regime not in weight_table:
        return None
    w = weight_table[regime]
    total_w, total_score = 0.0, 0.0
    for score_col, score_label in regime_lib.FACTOR_SCORE_COLS.items():
        v = row[score_col]
        if pd.isna(v):
            continue
        total_score += v * w[score_label]
        total_w += w[score_label]
    if total_w == 0:
        return None
    return total_score / total_w


df["regime_score"] = df.apply(regime_weighted_score, axis=1)

# 只留下 freeze_date 之後、且 forward return 已經有結果（不是還在等資料）的天數
oos = df.loc[df.index > freeze_date].copy()
oos["fwd"] = fwd.loc[oos.index]
oos = oos.dropna(subset=["composite_score", "regime_score", "fwd"])

print(f"權重凍結日期：{snapshot['freeze_date']}")
print(f"今天日期：{df.index.max().strftime('%Y-%m-%d')}")
print(f"樣本外可用天數（已經有未來{horizon}日報酬結果的）：{len(oos)} 天")
print(f"（約 {len(oos) // horizon if horizon else 0} 個獨立不重疊區塊——這才是真正的統計把握程度）")

MIN_USABLE = 60  # 至少要有這麼多天，比較才有一點點意義（就算如此仍然很少）
if len(oos) < MIN_USABLE:
    print(f"\n樣本外資料還太少（少於{MIN_USABLE}天），現在下任何結論都不可靠。")
    print("建議先不要看這份報告的數字，過一段時間累積更多資料再重跑。")
else:
    rho_eq, _ = stats.spearmanr(oos["composite_score"], oos["fwd"])
    rho_rw, _ = stats.spearmanr(oos["regime_score"], oos["fwd"])
    print(f"\n樣本外表現比較（未來{horizon}日ZN報酬）：")
    print(f"  等權重綜合分數　　：rho={rho_eq:+.3f}")
    print(f"  情境加權分數（v1）：rho={rho_rw:+.3f}")
    if rho_rw > rho_eq:
        print("  → 目前樣本外資料顯示情境加權版略優，但樣本仍然很少，僅供參考。")
    else:
        print("  → 目前樣本外資料顯示情境加權版沒有優於等權重版，需要留意、不宜貿然採用。")

print("\n各Fed階段目前的樣本外天數分布：")
print(oos["regime_fed"].value_counts())
