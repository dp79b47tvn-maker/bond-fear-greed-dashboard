"""把 bond_fear_greed_index.csv 轉成儀表板用的 JSON，含6個分量分數。"""
import json
import pandas as pd

df = pd.read_csv("bond_fear_greed_index.csv", index_col=0, parse_dates=True).sort_index()

COMPONENT_LABELS = {
    "ZN_futures_component": "ZN期貨",
    "TLT_component": "TLT",
    "SHY_component": "SHY",
    "BIL_component": "BIL",
    "MOVE_index_component": "MOVE指數(已反轉)",
    "UST_10Yr_component": "10年期殖利率",
}

records = []
for d, row in df.iterrows():
    records.append({
        "date": d.strftime("%Y-%m-%d"),
        "score": round(float(row["composite_score"]), 2),
        "label": row["label"],
        "components": {
            COMPONENT_LABELS[c]: round(float(row[c]), 2) for c in COMPONENT_LABELS
        },
    })

with open("chart/dashboard_data.json", "w") as f:
    json.dump(records, f)

print(f"共 {len(records)} 筆資料寫入 chart/dashboard_data.json")
print("最新一筆:", records[-1])
