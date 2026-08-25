# 交接文件 — 債券市場恐懼貪婪儀表板

給接手這個專案的人。目標是讓你在**一小時內**知道：這是什麼、怎麼跑、改東西要注意什麼、
以及前人踩過哪些坑。

最後更新：2026-08-13

---

## 1. 一句話說明

用美國公債市場的資料算出一個 0–100 的「恐懼貪婪分數」，每個交易日自動更新，
外加一個可以測試新因子值不值得加進來的研究平台。

**正式站**：https://dp79b47tvn-maker.github.io/bond-fear-greed-dashboard/

三個對外頁面（首頁是入口）：

| 頁面 | 檔案 | 內容 |
|---|---|---|
| 首頁 | `chart/index.html` | 專案簡介與兩張入口卡片 |
| 儀表板 | `chart/dashboard.html` | 今日分數、歷史走勢、各因子拆解 |
| 因子開發與篩選平台 | `chart/screening_index.html` | 測新因子、歷史測試登記簿、相關係數矩陣 |

---

## 2. 分數是怎麼算出來的

### 目前只有兩個因子（不是七個）

**這點很重要**：2026-08-05 之前是七項因子（動能、強度、存續期間避險、Put/Call、
波動度、殖利率曲線、通膨意外）。現在只剩兩項。repo 裡有些舊文件還寫著七項，
看到請以 `factor_definitions.json` 為準。

| 因子 | 算法 | 方向 |
|---|---|---|
| **動能** `momentum` | US 10Y 殖利率 − 其 125 日均線 → 5年百分位 → **反轉** | 殖利率高於均線＝價格跌破均線＝恐懼 |
| **銅金比** `copper_gold` | 銅期貨 60 日報酬 − 金期貨 60 日報酬 → 5年百分位 | 銅相對金走強＝景氣/風險偏好回升＝貪婪 |

**綜合分數 = 兩項等權重平均**（某項當天沒資料就自動排除，不填假值）。

分級：0–24 極度恐懼／25–44 恐懼／45–55 中性／56–75 貪婪／76–100 極度貪婪。

### 核心機制：滾動百分位

每個因子的原始數值（單位可能是 %、點數、比值）都會丟進**過去 5 年（1825 天）的分佈**
取百分位，變成 0–100。這樣單位完全不同的指標才能放在一起平均，而且比的是相對位置、
不受市場整體水位漂移影響。

公式：`分數 = (視窗內「數值 ≤ 今天」的天數) ÷ 1825 × 100`

### 資料來源

| 欄位 | 代號 | 來源 | 用途 |
|---|---|---|---|
| `UST_10Yr` | 10 Yr | Treasury.gov | 動能因子；也是所有驗證的**標的** |
| `UST_2Yr` | 2 Yr | Treasury.gov | 跟 10Yr 同一支 API 一起拿，目前不參與計算 |
| `HG_futures` | HG=F | Yahoo Finance | 銅金比 |
| `GC_futures` | GC=F | Yahoo Finance | 銅金比 |
| `ZN_futures` | ZN=F | Yahoo Finance | 目前不參與計算，保留供圖表/回測對照 |

抓什麼**完全由 `factor_definitions.json` 的 `data_sources` 決定**，程式裡沒有寫死的 ticker。

---

## 3. 怎麼跑

```bash
pip install -r requirements.txt

python3 scripts/check_consistency.py   # 靜態一致性檢查(不發網路請求，一秒跑完)
python3 update_dashboard.py            # 抓資料、算分數、產生 chart/dashboard.html
python3 generate_hub.py                # 產生 chart/index.html
python3 scripts/verify_dashboard.py    # 發布前檢查(JS語法/JSON合法性/關鍵HTML id)
```

`chart/` 底下的 HTML 是**產物**，本機重跑後 commit 回 repo 即可；也可以完全不管本機、
直接 push 到 `main`，GitHub Actions 會在雲端重跑整套流程並部署。

### 自動化（GitHub Actions）

| Workflow | 觸發 | 做什麼 |
|---|---|---|
| `update-and-deploy.yml` | 每交易日收盤後 cron | 一致性檢查 → 重算 → 驗證 → commit → 部署 Pages |
| `factor-screening.yml` | 網頁表單觸發 | 跑新候選因子的五道關卡 |
| `correlation-matrix.yml` | 網頁表單觸發 | 產生因子相關係數矩陣 |
| `promote-factor.yml` | 網頁按鈕觸發 | 把候選因子升等成儀表板可選因子 |

---

## 4. 檔案地圖

### 核心（動它們要小心）

```
factor_definitions.json        ★ 唯一事實來源：因子定義、計算參數、資料來源、說明文字
factor_defs_schema.py          factor_definitions.json 的 Pydantic 格式驗證(載入前先過這關)
update_dashboard.py            抓資料 → compute_scores() → 產生 dashboard.html + dashboard_data.json
transform_modes.py             8 種因子轉換模式，儀表板與篩選平台共用同一份實作
factor_validation_analysis.py  IC/分桶/統計分布等計算函式庫(factor_screening 的依賴)
```

**因子篩選平台**(2026-08-25拆成四支，各自單一職責，`factor_screening.py`是薄的
orchestrator，其餘三支的函式會重新匯入它的命名空間，所以`import factor_screening as fs`
之後`fs.score_to_position()`這種既有呼叫方式不用改)：

```
factor_screening.py    orchestrator：run_screening()串起下面三支、登記簿讀寫、對外入口
screening_gates.py     五道關卡、回測(backtest_strategy)、部位規則(score_to_position)——
                        純計算，不碰HTML/matplotlib，可獨立測試(tests/test_factor_screening.py)
screening_charts.py    matplotlib畫圖轉base64
screening_render.py    HTML字串模板(單一因子報告 + 登記簿一覽頁)
```

### 共用模組

```
nav_bar.py       三個頁面共用的導覽列 + 中英文切換
page_style.py    共用的顏色/字級/間距 CSS 變數
regime_lib.py    Fed 利率循環階段分類
```

### 腳本

```
scripts/check_consistency.py            ★ 一致性自我檢查(已接進 CI)
scripts/verify_dashboard.py             發布前檢查
scripts/generate_correlation_matrix.py  相關係數矩陣
scripts/promote_factor.py               候選因子升等
scripts/run_workflow_screening.py       CI 用的篩選進入點
scripts/build_direct_parta_html.py      只產 Part A 統計分布(不跑五關，用前務必看檔頭說明)
scripts/screen_composite_2factor.py     把「因子組合」當成一個因子跑完整五關
scripts/sweep_window_sensitivity.py     視窗長度敏感度掃描
scripts/walkforward_window_selection.py walk-forward 參數驗證
scripts/run_partb_combination_backtest.py  Part B 組合爆破回測(產出 partb_combination_results.csv)
```

### 資料檔

```
chart/dashboard_data.json       儀表板歷史資料(2026-08-25起，從dashboard.html內嵌搬出來，
                                 頁面執行期用fetch()載入，見下方「架構檢討第4項」)
factor_screening_registry.json  歷史測試登記簿(append-only，23 筆)
promoted_candidate_factors.json 已升等的候選因子
event_calendar.json             FOMC/CPI/NFP 事件行事曆
factor_scores_matrix.csv        11 因子分數快照(2026-08-05，靜態，見下方「已知限制」)
partb_combination_results.csv   Part B 2047 種組合的回測結果
data_input.xlsx                 使用者手動輸入/覆蓋原始資料，優先於自動抓取
regime_weights_v1.json          情境加權權重快照(目前停用)
```

---

## 5. 因子篩選平台怎麼用

想到新因子時，填一張設定表跑五道關卡：

```python
import factor_screening as fs
fs.screen_and_save({
    "key": "my_factor",
    "label": "【候選】我的新因子",
    "mode": "return_spread",              # 見 transform_modes.TRANSFORM_MODES
    "sources": {"a": {"yahoo": "XXX"}, "b": {"fred": "YYY"}},
    "params": {"window": 60},
    "invert": False,
})
```

**八種轉換模式**（`transform_modes.py`）：`ma_deviation`／`ma_spread`／`range_position`／
`return_spread`／`value_spread`／`moving_average`／`rolling_stat`／`composite_mean`。

最後那個 `composite_mean` 是把**幾個既有分數平均**當成一個新因子，用來測「因子組合」——
mentor 要求的「N 個因子各種排列組合回測」直接改 config 就能跑，不用每次寫一次性腳本。

**五道關卡**：資料健檢／單獨效力／穩定性／增量價值／可實作性。跑完會自動產出報告
（含 Part A 統計分布圖與回測分析），並**append** 一筆到登記簿。

### 登記簿是防自欺的機制，不要覆寫它

`factor_screening_registry.json` **刻意記錄每一次測試，不只是成功的**。測了 20 次
只記得成功那 1 次，會嚴重高估命中率（多重比較偏誤）。

> ⚠️ 曾經有腳本用 `json.dump()` 直接覆寫這個檔，一次弄丟 5 個因子共 10 筆歷史紀錄
> （commit `014f6c0`）。任何要寫入登記簿的程式都必須**讀取 → 合併 → 寫回**。
> `scripts/check_consistency.py` 現在會檢查這件事。

---

## 6. 改東西要注意什麼

### 改因子組成 → 只動 `factor_definitions.json`

新增/移除因子、改參數、改資料來源，原則上只需要改這一個檔。之後跑：

```bash
python3 scripts/check_consistency.py
```

它會告訴你還有哪裡沒跟上。目前的檢查項目：

- JSON 宣告的 `score_col` vs `compute_scores()` 實際產出 vs `SCORE_COLS` 三者一致
- `compute_scores()` 需要的輸入欄位都有在 `data_sources` 宣告
- 兩支資料抓取函式都還走共用的 `fetch_declared_sources()`（沒人偷改回手列 ticker）
- `fva.FACTOR_COLS` 仍是動態衍生（不可寫死）
- 儀表板模板的 `COMPONENTS` / `CUSTOM_WEIGHT_FACTORS` key 跟 JSON 一致
- 過期文案（例如因子只剩兩項卻還寫「七項」）
- 登記簿沒有被腳本直接覆寫
- 孤兒模組、`__main__` 保護

### 有些東西還是手刻的，改因子時要一起改

`chart/dashboard_template.html` 裡兩個 JS 陣列不是從 JSON 動態生成的：

- `COMPONENTS` — 每張分項卡片的即時數值文字與原始走勢圖設定
- `CUSTOM_WEIGHT_FACTORS` — 自訂權重面板的勾選清單

一致性檢查會抓到不同步，但**內容還是要你自己寫**。

---

## 7. 前人踩過的坑（照時間倒序）

### 模板註解裡不能出現佔位符的字面字串

`update_dashboard.py` 用 Python 的 `str.replace("__XXX__", ...)` 把資料填進
`dashboard_template.html`——這是**全域替換**，不是只換第一個。2026-08-25 曾經在模板
新加的說明註解裡剛好打到 `__NAV_BAR_JS__` 這個字面字串(單純想指稱它，不是要當佔位符)，
結果被連著替換掉，把整段 `LANG_TOGGLE_JS` 硬塞進一行註解中間，直接把 `<script>` 語法
弄壞(多宣告了一次 `I18N_DICT`)。

是靠 `scripts/verify_dashboard.py` 的 `node --check` 這一關擋下來的——這正是這支腳本
存在的目的。**現在**額外加了 `scripts/check_consistency.py` 裡的
`check_template_placeholder_counts()`：檢查每個佔位符在模板裡剛好出現 1 次，
多於 1 次就直接 fail，不用等到語法真的爆炸才發現。以後在模板的註解/文案裡要提到
某個佔位符名稱，寫成不含雙底線相連的形式(例如拆開描述)，避開這個地雷。

### 資料管線曾經有兩份、互相不同步

`update_dashboard.fetch_all_raw_data()` 和 `factor_validation_analysis.fetch_extended_history()`
以前各自手列一份要抓的 ticker，卻都呼叫同一支 `compute_scores()`。因子從七項改兩項時
只改了前者，導致整個因子篩選平台 `KeyError: 'HG_futures'` 跑不動。

**現在**兩支都呼叫共用的 `ud.fetch_declared_sources()`，由 JSON 驅動。
一致性檢查會確認沒人改回去。

### 曾經有腳本寫死假的驗證數字

`scripts/build_direct_parta_html.py` 原本把五道關卡結果全部寫死成假值
（IC=0.12、單調性=0.85、`gates_passed="5/5"`、`final_verdict="採用(Keep)"`），
11 個因子的報告與登記簿條目因此長得一模一樣，而且是憑空捏造的——實測動能因子真正的
20 日重疊 IC 是 **−0.046**，跟寫死的 +0.120 方向相反。這些假數字上過正式站。

**現在**那支腳本的五關一律標記「未執行」，只呈現真實計算的 Part A 統計分布。
教訓：**寧可標示「未執行」，也不要填佔位數字**。

### CSV 自我汙染

有測試腳本把 `bond_fear_greed_v2.csv` 同時當「假資料來源」讀、又把真實輸出寫回同一個檔。
因為該 CSV 沒有 5 年百分位暖身資料（只從 2020 開始），反覆執行會讓每個因子的有效日期
範圍逐次縮短，而 `composite_score`（skipna 平均）會把這種劣化蓋掉、看不出來。

**規則**：一律用真正的 `update_dashboard.py`（實際抓網路）重新產生，
絕不讓測試輸出覆寫當作測試輸入的 CSV。

### 沒有 `__main__` 保護的模組

專案裡曾有多支模組 import 時就直接執行。有一次 import `derive_regime_signal` 導致它
覆寫了 `regime_signal_v1.json` 這個**凍結的權重快照**，把 freeze_date 從 2026-07-17
改成當天。那些模組已刪除，一致性檢查現在也會擋。

### 本機 repo 落後而不自知

因為本機常有未 commit 的測試產物（`chart/dashboard.html`），每次 pull 前都要 stash，
容易忘記同步，曾經落後遠端 10 個 commit。**開始任何工作前先 `git fetch` 確認。**

### 多 session 並行

這個專案常有多個 AI session 同時在改。動手前務必：

```bash
git fetch origin main && git rev-list --left-right --count origin/main...HEAD
```

產生出來的 HTML 衝突時，**取遠端版本再重新產生**，不要手動合併。

---

## 8. 目前的研究結論（重要，別重複踩）

### 兩個因子方向相反，合成後會互相抵銷

| | 20年 IC | 回測 Sharpe |
|---|---|---|
| 銅金比單獨 | +0.126 | 0.44 |
| 動能單獨 | −0.046 | — |
| **兩者等權重平均** | **+0.021** | — |

兩者相關係數 −0.30（方向相反），平均後 IC 比銅金比自己一個人還差。
**這是已知問題，不是 bug。**

### 合成分數摸不到極端值

等權重平均會把分數往中間壓。合成分數的歷史區間只有 **5.3–92.3**，
從未落入 0–5% 或 95–100% 的極端尾端。
所以「極度恐懼/極度貪婪是否出現反轉」這個問題，在合成分數上**問不出來**。

### 參數選不出「最佳值」

銅金比的視窗長度做過完整驗證（`scripts/sweep_window_sensitivity.py` 與
`scripts/walkforward_window_selection.py`）：

- 固定 10/20/40/60 日的樣本外 Sharpe 是 0.32／0.33／0.32／0.38，**分不出高下**
- 60 日 vs 40 日的差距，區塊自助法 95% 信賴區間 [−0.08, +0.47]，**含 0、不顯著**
- walk-forward 每年重選一次窗口，16 個樣本外區段選出 **6 種不同窗口**，完全沒收斂；
  而且動態選參數的樣本外 Sharpe 只有 0.12，**輸給任何一個固定窗口**

目前固定用 60 日。**不要再試圖從資料裡挑最佳參數**，證據顯示挑不出來、挑了還更差。

### 原始「銅價÷金價」比值不能用

教科書定義的銅金比是價格比值，但實測**沒有鑑別力**：
恐懼端 +3.4bp、貪婪端也是 +3.6bp，兩邊同方向。

原因是價格比值是**非平穩序列**（會走多年趨勢），丟進 5 年滾動百分位後分數會長時間
黏在極端值不動——60 日自相關高達 0.847，最長連續 148 天黏在 ≤5 分。
所謂「極度恐懼那一桶」其實不是 148 個獨立事件，而是一段連續低檔期。

要用比值的話**必須先去趨勢**（例如對自己的均線取乖離）。

### 樣本數要打折看

分桶統計用的是**重疊取樣**（逐日滾動 20 日窗口）。「178 個交易日」換算成互不重疊的
獨立事件可能只剩 6 筆。看到大 n 不要直接當成統計基礎穩固。

---

## 9. 已知限制與待辦

| 項目 | 說明 |
|---|---|
| `factor_scores_matrix.csv` 是靜態快照 | 2026-08-05 產生，含 11 個因子。它的產生腳本依賴已刪除的舊七因子，**目前無法重新產生**。相關係數矩陣的「歷史因子」選項用的就是這份。 |
| 候選因子設定散在多支腳本 | 同一個候選因子的 config 在 2–3 個檔案各有一份，改一個因子要改多處。尚未集中。 |
| `regime_lib.FACTOR_SCORE_COLS` 仍是舊七因子 | 情境加權分數已停用（`REGIME_SCORE_ENABLED = False`），不影響執行；要恢復該功能須先重新校準權重。 |
| Part B 回測結果是靜態 CSV | `partb_combination_results.csv` 同樣是 2026-08-05 快照，反映的是舊七因子時代的組合。 |
| 回測未計交易成本 | 報告有明確揭露，並給出扣除方式（每日部位變動量 × 單邊成本bp × 252）。 |
| Put/Call 因子已移除 | 原因是沒有免費的歷史資料來源（CBOE 公開資料只到 2019-10）。 |

---

## 10. 相關文件

| 檔案 | 內容 |
|---|---|
| `README.md` | 專案簡介與快速上手 |
| `AGENTS.md` | AI agent 協作規範（git 工作流 + 本專案具體操作方式）。**不是給人讀的專案文件**，是給 Claude Code / Cursor / Copilot 等工具讀的。 |
| `資料來源與計算邏輯說明.md` | 每個資料來源的可信度、每個因子的計算細節（白話版） |
| `完整計算流程逐步講解.md` | 從原始數據到分數的逐步計算示範（帶實際數字） |
| `專案目標與下一階段指引.md` | mentor 討論的專案目標（兩端反轉框架）與下一階段規劃 |
| `ZN期貨轉倉問題查證.md` | 為什麼驗證標的從 ZN 期貨改成 UST_10Yr 殖利率 |

---

## 11. 最快的上手路徑

1. 打開[正式站](https://dp79b47tvn-maker.github.io/bond-fear-greed-dashboard/)，把三個頁面點過一遍
2. 讀 `factor_definitions.json`（不長，但它是整個系統的中心）
3. 讀 `update_dashboard.py` 的 `compute_scores()`（分數怎麼算，30 行）
4. 跑一次 `python3 scripts/check_consistency.py`，看它檢查哪些東西
5. 跑一次 `python3 update_dashboard.py`，對照產出的 `chart/dashboard.html`
6. 回來讀本文件第 7、8 節（坑與結論），可以少走很多冤枉路
