#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
因子視窗長度敏感度掃描——回答「這個參數為什麼是這個數字」。

【為什麼需要這支】
2026-08-11 追查「銅金比為什麼用40日報酬差」時發現：那個40是 2026-08-03 批次引進
5個候選因子時，直接抄自存續期間避險因子(TLT vs SHY 40日報酬差)的預設值，
commit訊息沒說明、登記簿只有一筆window=40的紀錄、全專案找不到任何參數測試。
換句話說那是個沒有依據的沿用值。

這支腳本把「換不同窗口會怎樣」變成可重跑的證據，而不是憑印象。

【使用時務必記得多重比較偏誤】
掃7個參數再挑最好的那個 = 曲線配適。這支腳本的用途是「了解參數敏感度」，
不是「找出最佳參數」。判讀重點應該放在：
  - 不同期間的排名一不一致？不一致代表最佳值是跟著期間走的，不是因子本質
  - 樣本內外(IS/OOS)差多少？IS遠優於OOS代表那個組態只是剛好配適到那段歷史
真的要換參數，請做 walk-forward(每段只用該段之前的資料選參數，看下一段表現)。

用法：
    python3 scripts/sweep_window_sensitivity.py                 # 預設掃銅金比
    python3 scripts/sweep_window_sensitivity.py --windows 5,20,60
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

import factor_screening as fs
import factor_validation_analysis as fva
import update_dashboard as ud
from transform_modes import build_candidate_score

# 預設掃描對象：銅金比。要掃別的因子改這裡的 sources/mode 即可。
BASE_CONFIG = {
    "key": "cg", "label": "銅金比 (HG=F vs GC=F)", "mode": "return_spread",
    "sources": {"a": {"yahoo": "HG=F", "name": "HG_futures"},
                "b": {"yahoo": "GC=F", "name": "GC_futures"}},
    "invert": False,
}
DEFAULT_WINDOWS = [5, 10, 20, 40, 60, 125, 250]
HORIZON = 20  # 跟平台主要評估期間一致


def evaluate(score, df, label):
    """單一期間的評估：IC、回測Sharpe、樣本內/外。"""
    s = score.reindex(df.index)
    sub = pd.concat([s.rename("s"), df[fva.TARGET].rename("y")], axis=1).dropna()
    sub["fwd"] = (sub["y"].shift(-HORIZON) - sub["y"]) * 100
    sub = sub.dropna()
    out = {f"IC[{label}]": spearmanr(sub["s"], sub["fwd"]).statistic if len(sub) > 20 else np.nan}
    bt = fs.backtest_strategy(s, df)
    out[f"Sharpe[{label}]"] = bt["full"]["sharpe"] if bt else np.nan
    out[f"IS[{label}]"] = bt["is"]["sharpe"] if bt and bt["is"] else np.nan
    out[f"OOS[{label}]"] = bt["oos"]["sharpe"] if bt and bt["oos"] else np.nan
    return out


def main():
    p = argparse.ArgumentParser(description="因子視窗長度敏感度掃描")
    p.add_argument("--windows", type=str, default=",".join(map(str, DEFAULT_WINDOWS)),
                   help="逗號分隔的視窗天數清單")
    args = p.parse_args()
    windows = [int(w) for w in args.windows.split(",") if w.strip()]

    df, _ = fva.fetch_extended_history(years=fva._V["vigintile_years"])
    out_start = ud._G["output_start_date"]

    rows = []
    for w in windows:
        cfg = {**BASE_CONFIG, "key": f"cg_{w}", "params": {"window": w}}
        score, _, df = build_candidate_score(cfg, df, ud.fetch_yahoo_close, ud.fetch_fred_series)
        row = {"window": w}
        # 兩個期間並列：完整歷史 vs 儀表板實際輸出期間
        row.update(evaluate(score, df, "全歷史"))
        row.update(evaluate(score, df.loc[out_start:], f"{out_start[:4]}+"))
        row["換手"] = float(fs.score_to_position(score.reindex(df.index)).diff().abs().mean())
        rows.append(row)

    res = pd.DataFrame(rows).set_index("window")
    pd.set_option("display.width", 220, "display.max_columns", 30)
    print("\n" + "=" * 100)
    print(f"{BASE_CONFIG['label']}：視窗長度敏感度（IC以未來{HORIZON}日殖利率變動bp為標的，重疊取樣）")
    print("=" * 100)
    print(res.round(3).to_string())
    print(f"""
判讀提醒：
  · 兩個期間的排名如果不一致，代表「最佳窗口」是跟著期間走的，不是因子本質，
    此時挑分數最高的那個就是曲線配適。
  · IS 遠優於 OOS 的組態代表只是剛好配適到那段歷史，不要採用。
  · 這裡一次比較了 {len(windows)} 個參數，存在多重比較偏誤；要換參數請做 walk-forward。""")


if __name__ == "__main__":
    main()
