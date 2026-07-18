"""
把「Fed循環動態權重」凍結成一個版本快照（regime_weights_v1.json）。

這個腳本【只在你想要重新校準權重時手動執行】，不是每天自動跑的——
重點就是要讓權重「凍結」在某個時間點，之後累積的新資料才能拿來做真正的
樣本外驗證（out-of-sample），如果每天都重新derive一次權重，就永遠沒有
「還沒被權重看過的資料」可以驗證了。

用法：
    python3 derive_regime_weights.py
會輸出 regime_weights_v1.json，記錄：
  - 凍結日期 (freeze_date)
  - 用來推導權重的資料範圍
  - 各Fed循環階段的權重表
  - 使用的方法與參數（地板值、預測目標、時間窗口）
"""
import json
from datetime import date

import pandas as pd
from scipy import stats

import regime_lib

FLOOR = 0.05
HORIZON = 40
OUT_PATH = "regime_weights_v1.json"

df = pd.read_csv("bond_fear_greed_v2.csv", index_col=0, parse_dates=True).sort_index()
df["regime_fed"] = df.index.map(regime_lib.fed_cycle_label)


def forward_return(price, horizon):
    return (price.shift(-horizon) / price - 1) * 100


fwd = forward_return(df["ZN_futures"], HORIZON)

weight_table = {}
rho_table = {}
for start, end, regime_val in regime_lib.FED_CYCLE_BOUNDARIES:
    mask = df["regime_fed"] == regime_val
    if mask.sum() < 30:
        continue
    rhos = {}
    for score_col, score_label in regime_lib.FACTOR_SCORE_COLS.items():
        sub = pd.concat([df.loc[mask, score_col], fwd.loc[mask]], axis=1).dropna()
        sub.columns = ["score", "fwd"]
        if len(sub) < 30:
            rhos[score_label] = 0.0
            continue
        rho, _ = stats.spearmanr(sub["score"], sub["fwd"])
        rhos[score_label] = float(rho) if pd.notna(rho) else 0.0

    floored = {k: max(v, FLOOR) for k, v in rhos.items()}
    total = sum(floored.values())
    weights = {k: v / total for k, v in floored.items()}
    weight_table[regime_val] = weights
    rho_table[regime_val] = rhos

snapshot = {
    "version": "v1",
    "freeze_date": date.today().isoformat(),
    "derived_from_data_range": [df.index.min().strftime("%Y-%m-%d"), df.index.max().strftime("%Y-%m-%d")],
    "method": {
        "target": "ZN_futures forward return",
        "horizon_trading_days": HORIZON,
        "floor": FLOOR,
        "description": (
            "每個Fed循環階段下，取各因子分數對未來N日ZN期貨報酬的Spearman rho；"
            "負值或極弱相關（低於地板值）一律設為地板值（不完全歸零，避免樣本不足造成的誤判）；"
            "再依rho大小等比例分配權重。Put/Call因無歷史資料，暫不納入。"
        ),
    },
    "fed_cycle_boundaries": [
        {"start": s, "end": e, "label": lbl} for s, e, lbl in regime_lib.FED_CYCLE_BOUNDARIES
    ],
    "rho_by_regime": rho_table,
    "weight_by_regime": weight_table,
}

with open(OUT_PATH, "w", encoding="utf-8") as f:
    json.dump(snapshot, f, ensure_ascii=False, indent=2)

print(f"已凍結權重快照：{OUT_PATH}")
print(f"凍結日期：{snapshot['freeze_date']}")
print(f"推導資料範圍：{snapshot['derived_from_data_range'][0]} ~ {snapshot['derived_from_data_range'][1]}")
print("\n權重表：")
for regime_val, weights in weight_table.items():
    print(f"  {regime_val}: " + "  ".join(f"{k}={v*100:.1f}%" for k, v in weights.items()))
print(f"\n從{snapshot['freeze_date']}之後累積的新資料，才是這組權重的真正樣本外驗證區間。")
print("往後執行 python3 validate_regime_weights.py 可以檢查目前累積了多少樣本外資料、表現如何。")
