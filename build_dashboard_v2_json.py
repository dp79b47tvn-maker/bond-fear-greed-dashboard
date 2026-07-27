"""把 bond_fear_greed_v2.csv 轉成儀表板用的 JSON（扁平結構，對應 dashboard.html）。"""
import json
import math
import pandas as pd

df = pd.read_csv("bond_fear_greed_v2.csv", index_col=0, parse_dates=True).sort_index()


def safe(v, nd=3):
    if v is None:
        return None
    try:
        if isinstance(v, float) and math.isnan(v):
            return None
    except TypeError:
        pass
    if pd.isna(v):
        return None
    return round(float(v), nd)


records = []
for d, row in df.iterrows():
    records.append({
        "date": d.strftime("%Y-%m-%d"),
        "score": safe(row["composite_score"], 2),
        "label": None if pd.isna(row["label"]) else row["label"],
        "ust10yr": safe(row["UST_10Yr"], 2),
        "momentum": safe(row["momentum_score"], 2),
        "strength": safe(row["strength_score"], 2),
        "putcall": safe(row["putcall_score"], 2),
        "move": safe(row["move_score"], 2),
        "raw": {
            "us10y": safe(row["UST_10Yr"]),
            "sma125": safe(row["UST10Y_SMA125"]),
            "spread": safe(row["momentum_spread"], 2),
            "hi252": safe(row["zn_252d_high"]),
            "lo252": safe(row["zn_252d_low"]),
            "move": safe(row["MOVE_index"], 2),
            "pc5d": safe(row["put_call_5d_avg"], 2),
        },
    })

with open("chart/dashboard_v2_data.json", "w") as f:
    json.dump(records, f, ensure_ascii=False)

print(f"共 {len(records)} 筆資料寫入 chart/dashboard_v2_data.json")
print("最新一筆:", json.dumps(records[-1], ensure_ascii=False))
