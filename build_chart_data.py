"""把 bond_fear_greed_index.csv 轉成畫圖用的 JSON，供 chart.html 內嵌使用。"""
import json
import pandas as pd

df = pd.read_csv("bond_fear_greed_index.csv", index_col=0, parse_dates=True).sort_index()

records = [
    {"date": d.strftime("%Y-%m-%d"), "score": round(float(s), 2), "label": lbl}
    for d, s, lbl in zip(df.index, df["composite_score"], df["label"])
]

with open("chart/data.json", "w") as f:
    json.dump(records, f)

print(f"共 {len(records)} 筆資料寫入 chart/data.json")
print("首筆:", records[0])
print("末筆:", records[-1])
