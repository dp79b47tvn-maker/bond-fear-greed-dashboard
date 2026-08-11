#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
視窗長度的 walk-forward 驗證——回答「事後掃出來的最佳參數，換到真實情境還站得住嗎」。

【為什麼需要這支】
scripts/sweep_window_sensitivity.py 一次比較7個窗口再挑最好的，那是事後諸葛：
用同一份資料試了很多組再選一個，選出來的必然好看，但不代表未來也好。
這支腳本改成模擬真實決策流程：

    站在時間點 T，只用 T 之前的資料選出當時看起來最好的窗口，
    然後把那個選擇套到 T 之後的一年，看實際表現如何。
    每年重新選一次，滾動走完整段歷史。

每一段的績效都是「用當時選的參數、在還沒發生的資料上」跑出來的，沒有引用未來資料。

【要看什麼】
1. 每次選出來的窗口穩不穩定？
   一直選到同一個 → 那個值是這個因子的真實性質。
   每年跳來跳去 → 這個因子對窗口長度根本不穩定，選哪個都是運氣，
   這種情況下「最佳參數」這個概念本身就不成立。
2. Walk-forward 有沒有贏過「從頭到尾固定用某個窗口」？
   沒贏 → 動態選參數只是增加複雜度，不如固定一個簡單值。

用法：
    python3 scripts/walkforward_window_selection.py
    python3 scripts/walkforward_window_selection.py --train-years 5 --step-months 12
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

BASE_CONFIG = {
    "key": "cg", "label": "銅金比 (HG=F vs GC=F)", "mode": "return_spread",
    "sources": {"a": {"yahoo": "HG=F", "name": "HG_futures"},
                "b": {"yahoo": "GC=F", "name": "GC_futures"}},
    "invert": False,
}
WINDOWS = [5, 10, 20, 40, 60, 125, 250]


def daily_pnl(score, yields):
    """逐日損益(bp價格報酬)，部位規則與平台一致。只用工作日，理由見
    factor_screening.backtest_strategy() 的說明。"""
    sub = pd.concat([score.rename("s"), yields.rename("y")], axis=1).dropna()
    sub = sub[sub.index.dayofweek < 5]
    price_ret = -(sub["y"].shift(-1) - sub["y"]) * 100
    return (fs.score_to_position(sub["s"]) * price_ret).dropna()


def sharpe(series):
    if len(series) < 20 or series.std() == 0:
        return np.nan
    return float(series.mean() / series.std() * np.sqrt(252))


def main():
    p = argparse.ArgumentParser(description="視窗長度 walk-forward 驗證")
    p.add_argument("--train-years", type=int, default=5, help="每次選參數時往回看幾年")
    p.add_argument("--step-months", type=int, default=12, help="多久重新選一次參數")
    args = p.parse_args()

    df, _ = fva.fetch_extended_history(years=fva._V["vigintile_years"])
    yields = df[fva.TARGET]

    # 先把所有候選窗口的分數算好——滾動百分位本身就是只看過去的因果計算，
    # 事先算好不會造成未來資料洩漏。
    print(f"\n計算 {len(WINDOWS)} 個候選窗口的分數 ...")
    pnl_by_w, score_by_w = {}, {}
    for w in WINDOWS:
        cfg = {**BASE_CONFIG, "key": f"cg_{w}", "params": {"window": w}}
        score, _, df = build_candidate_score(cfg, df, ud.fetch_yahoo_close, ud.fetch_fred_series)
        score_by_w[w] = score
        pnl_by_w[w] = daily_pnl(score, yields)

    valid_start = min(s.dropna().index.min() for s in score_by_w.values())
    end = max(p_.index.max() for p_ in pnl_by_w.values())
    first_test = valid_start + pd.DateOffset(years=args.train_years)
    print(f"分數起始 {valid_start.date()}，訓練期 {args.train_years} 年，"
          f"第一段樣本外從 {first_test.date()} 開始，資料到 {end.date()}")

    folds = []
    t = first_test
    while t < end:
        t_next = min(t + pd.DateOffset(months=args.step_months), end)
        train_lo = t - pd.DateOffset(years=args.train_years)

        # ---- 只用 t 之前的資料選窗口 ----
        train_sharpe = {w: sharpe(pnl_by_w[w].loc[train_lo:t - pd.Timedelta(days=1)])
                        for w in WINDOWS}
        usable = {w: v for w, v in train_sharpe.items() if not np.isnan(v)}
        if not usable:
            t = t_next
            continue
        picked = max(usable, key=usable.get)

        # ---- 套到 t 之後這一段（樣本外）----
        row = {"樣本外期間": f"{t.date()} ~ {t_next.date()}", "選中窗口": picked,
               "訓練期Sharpe": usable[picked]}
        for w in WINDOWS:
            row[f"OOS_{w}"] = sharpe(pnl_by_w[w].loc[t:t_next])
        row["OOS_選中"] = row[f"OOS_{picked}"]
        folds.append(row)
        t = t_next

    res = pd.DataFrame(folds)
    if res.empty:
        print("資料不足，無法產生任何樣本外區段")
        return

    pd.set_option("display.width", 240, "display.max_columns", 40)
    print("\n" + "=" * 104)
    print(f"{BASE_CONFIG['label']}：walk-forward 每段選擇與樣本外表現（Sharpe）")
    print("=" * 104)
    show = ["樣本外期間", "選中窗口", "訓練期Sharpe", "OOS_選中"] + [f"OOS_{w}" for w in WINDOWS]
    print(res[show].round(2).to_string(index=False))

    # ---- 選擇穩定性 ----
    counts = res["選中窗口"].value_counts().sort_index()
    print("\n" + "-" * 104)
    print("選中窗口的分布（穩定性）：")
    for w, c in counts.items():
        print(f"  {w:>4} 日：被選中 {c} 次 ({c / len(res):.0%})  {'█' * c}")
    print(f"  共 {len(res)} 段，選出 {res['選中窗口'].nunique()} 種不同窗口")

    # ---- 動態選參數 vs 固定參數 ----
    print("\n" + "-" * 104)
    print("累積樣本外表現：walk-forward 動態選 vs 從頭到尾固定")
    wf_pnl = pd.concat([
        pnl_by_w[r["選中窗口"]].loc[
            pd.Timestamp(r["樣本外期間"].split(" ~ ")[0]):pd.Timestamp(r["樣本外期間"].split(" ~ ")[1])]
        for _, r in res.iterrows()
    ])
    oos_lo, oos_hi = wf_pnl.index.min(), wf_pnl.index.max()
    print(f"  比較區間 {oos_lo.date()} ~ {oos_hi.date()}（僅樣本外）")
    rows = [("walk-forward 動態選", sharpe(wf_pnl), float(wf_pnl.sum()))]
    for w in WINDOWS:
        seg = pnl_by_w[w].loc[oos_lo:oos_hi]
        rows.append((f"固定 {w} 日", sharpe(seg), float(seg.sum())))
    print(f"\n  {'策略':<24}{'Sharpe':>10}{'累積報酬(bp)':>16}")
    for name, sh, tot in rows:
        star = "  ←現行" if name == "固定 40 日" else ""
        print(f"  {name:<24}{sh:>10.2f}{tot:>16.0f}{star}")

    best_fixed = max(rows[1:], key=lambda r: (r[1] if not np.isnan(r[1]) else -9e9))
    wf_sh = rows[0][1]
    print(f"""
判讀：
  · walk-forward Sharpe {wf_sh:.2f} vs 最好的固定窗口({best_fixed[0]}) {best_fixed[1]:.2f}
    → {"動態選參數有加值" if wf_sh > best_fixed[1] else "動態選參數沒有贏過固定值，徒增複雜度"}
  · 每段選中的窗口若跳來跳去，代表這個因子對窗口長度不穩定，
    「最佳參數」這個概念本身就不成立，此時該質疑的是因子本身而不是參數。""")


if __name__ == "__main__":
    main()
