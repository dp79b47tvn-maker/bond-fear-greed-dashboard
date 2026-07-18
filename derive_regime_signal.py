"""
把「情境條件式訊號方向」凍結成一個版本快照（regime_signal_v1.json）。

背景：CNN原版邏輯預設「恐懼買入、貪婪賣出」（均值回歸假設）放諸四海皆準，
但 regime_signal_direction.py 的分析顯示，這個假設只在「升息循環」階段
成立，其餘三個Fed循環階段（暫停零利率／暫停高原期／降息循環）歷史上
反而是「動能延續」（分數越高，未來報酬越高，不是越低）。

跟 derive_regime_weights.py 用同樣的「凍結快照」精神：這個方向判定
【只在你想重新校準時手動執行】，不是每天自動跑。凍結之後累積的新資料，
才是這組方向判定的真正樣本外驗證。

用法：
    python3 derive_regime_signal.py
會輸出 regime_signal_v1.json。
"""
import json
from datetime import date

import pandas as pd
from scipy import stats

import regime_lib

DIRECTION_THRESHOLD = 0.05  # |rho|低於此視為「無方向性」，非嚴格顯著性門檻，只是實務雜訊地板
HORIZON = 40
TARGET_COL = "ZN_futures"
OUT_PATH = "regime_signal_v1.json"

df = pd.read_csv("bond_fear_greed_v2.csv", index_col=0, parse_dates=True).sort_index()
df["regime_fed"] = df.index.map(regime_lib.fed_cycle_label)


def forward_return(price, horizon):
    return (price.shift(-horizon) / price - 1) * 100


fwd = forward_return(df[TARGET_COL], HORIZON)


def classify_direction(rho):
    if abs(rho) < DIRECTION_THRESHOLD:
        return "無明顯方向"
    return "均值回歸" if rho < 0 else "動能延續"


direction_table = {}
for start, end, regime_val in regime_lib.FED_CYCLE_BOUNDARIES:
    mask = df["regime_fed"] == regime_val
    sub = pd.concat([df.loc[mask, "composite_score"], fwd.loc[mask]], axis=1).dropna()
    sub.columns = ["score", "fwd"]
    if len(sub) < 30:
        continue
    rho, _ = stats.spearmanr(sub["score"], sub["fwd"])
    rho = float(rho) if pd.notna(rho) else 0.0
    direction_table[regime_val] = {
        "rho": round(rho, 3),
        "direction": classify_direction(rho),
        "n": int(len(sub)),
        "indep_n": int(len(sub) // HORIZON),
    }

snapshot = {
    "version": "v1",
    "freeze_date": date.today().isoformat(),
    "derived_from_data_range": [df.index.min().strftime("%Y-%m-%d"), df.index.max().strftime("%Y-%m-%d")],
    "method": {
        "target": f"{TARGET_COL} forward return",
        "horizon_trading_days": HORIZON,
        "direction_threshold": DIRECTION_THRESHOLD,
        "description": (
            "每個Fed循環階段下，取綜合分數(composite_score)對未來40日ZN期貨報酬的"
            "Spearman rho；rho<-0.05判定為「均值回歸」（恐懼買/貪婪賣，CNN原版邏輯成立）；"
            "rho>+0.05判定為「動能延續」（高分反而傾向續漲，訊號方向與CNN原版相反）；"
            "|rho|<=0.05判定為「無明顯方向」（此階段分數不建議當獨立訊號）。"
            "45-55中性帶不受方向判定影響，任何情境下都視為無方向性。"
        ),
    },
    "fed_cycle_boundaries": [
        {"start": s, "end": e, "label": lbl} for s, e, lbl in regime_lib.FED_CYCLE_BOUNDARIES
    ],
    "direction_by_regime": direction_table,
}

with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(snapshot, f, ensure_ascii=False, indent=2)

print(f"已凍結訊號方向快照：{OUT_PATH}")
print(f"凍結日期：{snapshot['freeze_date']}")
for regime_val, info in direction_table.items():
    print(f"  {regime_val}: rho={info['rho']:+.3f} → {info['direction']}（約{info['indep_n']}個獨立區塊）")
print(f"\n從{snapshot['freeze_date']}之後累積的新資料，才是這組方向判定的真正樣本外驗證區間。")
