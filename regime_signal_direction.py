"""
情境條件式訊號方向分析：檢驗「恐懼買入/貪婪賣出」這套均值回歸假設，
在不同Fed循環階段下到底成不成立——如果某個階段是正相關（動能延續），
套用反向的「動能順勢」訊號才對，而不是照搬CNN原版的均值回歸邏輯。

方法：
  對綜合分數（composite_score）以及情境加權分數（regime_score，若有），
  在每個Fed循環階段內，計算對「未來N日ZN期貨報酬」的Spearman rho。
    rho < 0（顯著）→ 均值回歸成立：分數越高，未來報酬越低 → 高分＝賣出訊號、低分＝買入訊號
    rho > 0（顯著）→ 動能延續：分數越高，未來報酬越高 → 高分＝偏多（續抱/加碼）、低分＝偏空
    |rho| 很小 → 沒有方向性訊號，分數在這個階段不具參考價值

再用TLT做交叉驗證，避免ZN單一標的的雜訊。

誠實揭露：分Fed階段後，每格的獨立樣本數更少（見輸出），只能當方向性參考。
"""
import numpy as np
import pandas as pd
from scipy import stats

import regime_lib

df = pd.read_csv("bond_fear_greed_v2.csv", index_col=0, parse_dates=True).sort_index()
df["regime_fed"] = df.index.map(regime_lib.fed_cycle_label)

HORIZONS = [20, 40]
TARGETS = {"ZN_futures": "ZN期貨", "TLT": "TLT"}
SCORE_COLS = {"composite_score": "綜合分數（等權重）", "regime_score": "情境加權分數（實驗性）"}


def forward_return(price, horizon):
    return (price.shift(-horizon) / price - 1) * 100


results = {}  # results[score_col][regime][horizon] = (rho, n, indep_n)

for score_col, score_label in SCORE_COLS.items():
    if score_col not in df.columns:
        continue
    results[score_col] = {}
    print(f"\n{'='*78}\n分數：{score_label} ({score_col})\n{'='*78}")
    for start, end, regime_val in regime_lib.FED_CYCLE_BOUNDARIES:
        mask = df["regime_fed"] == regime_val
        n_days = mask.sum()
        if n_days < 30:
            continue
        print(f"\n  【{regime_val}】（{n_days}個交易日）")
        results[score_col][regime_val] = {}
        for h in HORIZONS:
            rhos_by_target = {}
            for price_col, price_label in TARGETS.items():
                fwd = forward_return(df[price_col], h)
                sub = pd.concat([df.loc[mask, score_col], fwd.loc[mask]], axis=1).dropna()
                sub.columns = ["score", "fwd"]
                if len(sub) < 30:
                    continue
                rho, pval = stats.spearmanr(sub["score"], sub["fwd"])
                indep_n = max(1, len(sub) // h)
                rhos_by_target[price_label] = (rho, len(sub), indep_n)
                print(f"    未來{h:>2}日 vs {price_label:>4}: rho={rho:+.3f}  (n={len(sub)}, ~{indep_n}個獨立區塊)")
            if "ZN期貨" in rhos_by_target:
                results[score_col][regime_val][h] = rhos_by_target

# ---------------------------------------------------------------- 方向判定與訊號表
DIRECTION_THRESHOLD = 0.05  # |rho|低於此視為「無方向性」，不是嚴格顯著性檢定，只是實務上的雜訊地板


def classify_direction(rho):
    if rho is None or abs(rho) < DIRECTION_THRESHOLD:
        return "無明顯方向"
    return "均值回歸（恐懼買/貪婪賣）" if rho < 0 else "動能延續（順勢操作）"


print(f"\n{'#'*78}\n情境條件式訊號方向表（以40日ZN期貨為主要判準）\n{'#'*78}")
signal_table = {}
for regime_val in [lbl for _, _, lbl in regime_lib.FED_CYCLE_BOUNDARIES]:
    comp = results.get("composite_score", {}).get(regime_val, {}).get(40, {}).get("ZN期貨")
    if comp is None:
        continue
    rho, n, indep_n = comp
    direction = classify_direction(rho)
    signal_table[regime_val] = {"rho": rho, "direction": direction, "n": n, "indep_n": indep_n}
    print(f"  {regime_val:>10}: rho={rho:+.3f} → {direction}  (獨立樣本約{indep_n}個)")

print("""
【解讀規則草案】
  若該階段判定為「均值回歸」：
    分數離50越遠（無論高低），訊號強度越強，方向與CNN原版一致
      0–24 極度恐懼 → 強力買入訊號 / 76–100 極度貪婪 → 強力賣出訊號
      25–44 恐懼 → 弱買入傾向 / 56–75 貪婪 → 弱賣出傾向
      45–55 中性 → 無方向性，維持既有部位

  若該階段判定為「動能延續」：
    訊號方向整個相反——分數高代表順勢做多、分數低代表順勢做空
      76–100 極度貪婪 → 強力做多（順勢） / 0–24 極度恐懼 → 強力做空（順勢）
      45–55 中性 → 無方向性，維持既有部位（這一點不受動能/回歸假設影響，兩種情境下都一樣）

  若該階段判定為「無明顯方向」（|rho|<0.05）：
    不管分數落在哪一段，都不建議把分數當成獨立的交易訊號來源，
    這個階段下分數本身的歷史關係太弱、太不穩定。
""")
