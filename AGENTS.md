# AGENTS.md — 這個專案的AI agent協作規範（跨平台通用）

> 這份檔案是給**任何**AI coding agent看的（Claude Code、Cursor、Windsurf、GitHub Copilot、
> Codex CLI……不限工具）。不管你今天用哪個平台接手這個專案，先讀這份檔案。
> `CLAUDE.md`、`.cursorrules`、`.windsurfrules`、`.github/copilot-instructions.md`
> 這幾個檔案都只是指到這裡的指標，內容不重複維護，避免多份文件各自過期、互相矛盾。

---

## Part 1｜通用 Git 工作流規則

### 1. 安全與機密優先（.gitignore 與密鑰管理）
- **零機密外洩**：絕不 commit `.env`、API 金鑰、token、資料庫憑證，或任何敏感設定檔。
- **push 前檢查**：執行 `git push` 或初始化 repo 前，確認所有敏感檔案與憑證模式都列在 `.gitignore`。
- **自動防護**：新建立機密或環境變數檔案時，主動把它們（或對應的檔案模式）加進 `.gitignore`。

### 2. 環境設定與同步
- **初始化（`git init`）**：任何要 push 到 GitHub 的本機專案，先確保有 git 追蹤。
- **Clone 而非 ZIP**：優先用 `git clone`，保留完整版本歷史與遠端追蹤能力。
- **開始新工作前先同步（`git pull`）**：開新分支或開始新功能前，先 `git pull origin main`，避免在過期的程式碼上工作。

### 3. 檢查點與存檔（`git commit`）
- **細粒度安全檢查點**：一個功能、子任務或 bug 修好並驗證過，就commit。
- **訊息要清楚**：commit 訊息用繁體中文或英文說明「改了什麼」跟「為什麼」。
- **不留壞掉的 main**：不留未 commit 的壞狀態；實驗失敗就還原或恢復。
- 只有使用者明確要求才 commit——不要自作主張幫使用者commit他沒同意的改動。

### 4. 分支隔離與多 agent worktree
- **不要直接在 `main` 上開發**：非小改動、新功能、大重構都要開專屬 feature 分支。
- **多 agent 並行（`git worktree`）**：多個 AI 任務／agent 同時跑時，不要共用同一個工作目錄；
  用 `git worktree add <path> <branch>` 為不同分支建立獨立實體目錄。

### 5. Review 與整合流程（PR 與 Merge）
- **建立 PR**：功能開發完成後，準備／草擬 PR，內容包含：(1) 高層次的改動摘要
  (2) 修改到的關鍵檔案清單 (3) 測試步驟與驗證清單。
- **merge 後本機同步**：PR merge 進遠端 main 後：切回本機 `main` → `git pull` → 清掉已完成的 feature 分支。

### 6. 衝突處理協議（`git conflict`）
- 遇到 merge conflict 時，分析兩邊的衝突標記（`<<<<<<<`、`=======`、`>>>>>>>`）。
- **解法策略**：A. 二選一（一邊明顯取代另一邊時）／B. 聯集合併（保留兩邊不衝突的新增內容）／
  C. 重構整合（重新組織、乾淨合併兩邊意圖）。
- 衝突牽涉產品邏輯或商業取捨時，先問使用者怎麼決定，再合併。
- **這個專案的已知衝突模式**：GitHub Actions每天會自動commit重新產生的資料（見Part 2），
  如果你push時遇到`chart/dashboard.html`、`chart/index.html`衝突，這是預期中的——用
  `git checkout --theirs <file>`（rebase情境下"theirs"＝你正在重放的本機commit）保留本機
  剛重新產生的版本，用`git diff <你的原始commit> -- <file>`確認兩者內容一致再push。
  因子篩選平台、升等/退回功能、相關係數矩陣也會被各自獨立的workflow自動commit（見上方
  workflow說明），`chart/screening_*.html`、`chart/correlation_matrix.html`、
  `factor_screening_registry.json`、`promoted_candidate_factors.json`也可能遇到同樣狀況，
  處理方式一樣。**這個repo常常有
  多個agent/session並行改動**，push前務必先`git fetch`確認落後狀態，落後就先
  `git stash push -u` → `git pull --rebase` → `git stash pop`，不要直接硬push。

### 7. 災難復原協議（Restore vs. Revert）
- **未 commit 的壞程式碼**：`git restore .` 立刻回到上一個乾淨的 commit。
- **已 commit 的壞程式碼**：`git revert <commit-hash>` 建立反向 commit 安全撤銷，保留完整稽核歷史。
- **不要**只靠某個平台自己的「版本歷史」UI 回溯（例如Claude Artifact右上角的版本選單）——
  那些平台專屬的歷史，換了agent或平台就讀不到。git是所有agent都能讀取比對的共同依據。

---

## Part 2｜這個專案的具體操作方式

### 這是什麼
債券市場恐懼貪婪儀表板：美債市場指標彙整成每日恐懼貪婪分數。**三個對外頁面**——首頁、
即時儀表板、因子開發與篩選平台——全部由`factor_definitions.json`這份單一定義檔驅動，
共用同一份頂部導覽列（`nav_bar.py`，含中英文切換）跟同一套排版基準數值（`page_style.py`）。

**因子數量會變，不要在任何地方寫死**：2026-08-05起從七項縮減為兩項（動能、銅金比），
一律以`factor_definitions.json`的`factors`陣列為準。`scripts/check_consistency.py`會
檢查各處是否同步，包括文案裡寫死的「七項」這種過期字眼。

**專案本身的說明文件是`HANDOVER.md`**（給接手的人讀：分數怎麼算、怎麼跑、踩過的坑、
研究結論）。本檔`AGENTS.md`只負責AI agent的協作規範。

### 正式發布管道（目前唯一的正式管道，不是Claude Artifact）
專案已經上架在GitHub Pages公開發布，跟任何特定AI工具無關：
- 正式網址：`https://dp79b47tvn-maker.github.io/bond-fear-greed-dashboard/`
- GitHub repo：`git@github.com:dp79b47tvn-maker/bond-fear-greed-dashboard.git`
- `.github/workflows/update-and-deploy.yml`：GitHub Actions排程，每個交易日美股收盤後
  （22:00 UTC）自動重跑`update_dashboard.py`/`generate_hub.py`兩支腳本、驗證、commit回repo、
  部署——**不需要任何AI agent介入**，純粹是GitHub自己的排程機器人在跑。也可以手動觸發
  （repo的Actions頁面 → workflow_dispatch）。**不再**跑`factor_validation_analysis.py`
  （驗證報告頁已從導覽列移除，見下方）。
- `.github/workflows/factor-screening.yml`：手動觸發（`workflow_dispatch`），因子篩選平台
  網頁表單（`chart/screening_index.html`）提交新候選因子時打這個——跑`scripts/run_workflow_screening.py`
  → `factor_screening.screen_and_save()` → 產生`chart/screening_<key>.html`跟更新登記簿 → commit+push。
- `.github/workflows/promote-factor.yml`：手動觸發，登記簿頁的「升等」/「退回」按鈕都打這個
  （依`config_json`或`remove_key`哪個有值分流）——跑`scripts/promote_factor.py`寫入/移除
  `promoted_candidate_factors.json`裡的條目 → 重跑`update_dashboard.py` → 驗證 →
  `factor_screening.py --rebuild-index`重新產生登記簿頁（刷新「已升等」徽章狀態）→ commit+push。
- `.github/workflows/correlation-matrix.yml`：手動觸發，因子篩選平台頁裡「產生相關係數矩陣」
  按鈕打這個——跑`scripts/generate_correlation_matrix.py`（吃勾選的因子清單，直接重用
  `factor_validation_analysis.correlation_heatmap_base64()`）→ 產生`chart/correlation_matrix.html`
  → commit+push。取代原本驗證報告裡固定範圍、每天自動產生的相關矩陣。
- 以上三個手動觸發的workflow都是用GitHub PAT存在瀏覽器localStorage、直接呼叫GitHub API
  dispatch，不是走一般的push流程，PAT不會進git。
- Claude Artifact發布（`chart/dashboard.html`等）是**次要/預覽用途**，不是正式管道，
  現在也不是每次修改都需要同步做。

### 本機開發迴圈
1. 改 `chart/dashboard_template.html`、`factor_definitions.json`、或任何一支 `*.py` 之後：
   ```
   python3 update_dashboard.py          # 重新產生 chart/dashboard.html
   python3 generate_hub.py              # 重新產生 chart/index.html（首頁）
   ```
   `factor_validation_analysis.py`現在**純粹是函式庫**（給`factor_screening.py`用），
   沒有進入點、不會單獨執行——它的`main()`(產生已刪除的factor_validation_report.html)
   已於2026-08-13連同5個只有它在用的render函式一併移除。
   本機用 `venv/bin/python3`（repo內有現成的venv，裝好所有套件），不要用系統python3，
   否則會缺套件（例如`seaborn`）。
2. 檢查：
   ```
   python3 scripts/verify_dashboard.py
   ```
   沒過（exit code非0）就不要往下發布——先照印出來的訊息修好。這支腳本抓：
   JS語法錯誤（`node --check`）、DATA/REGIME_META是否為合法JSON、關鍵HTML id是否還在。
   **2026-07-18發生過一次事故**：說明文字裡誤用markdown反引號，剛好包在JS模板字串裡面，
   提前截斷字串，整個`<script>`區塊語法錯誤、整頁空白，卻沒有機制擋下來——這支腳本就是為了
   不要再發生這種事。
3. 檢查通過後，**先commit再push**（commit前先確認使用者同意）。
4. `git push origin main`——如果遇到conflict，見Part 1第6條的「已知衝突模式」。

### 已知的「本機能跑、CI跑不動」環境差異（踩過的坑）
GitHub Actions用的是全新的Ubuntu runner，跟本機Mac環境不一樣，這幾個問題都已修好，
但如果之後又遇到類似情況、或換平台的agent在別的CI環境上重新踩到，這裡記錄根本原因：
- **`requirements.txt`必須完整**：本機venv裝的套件不會自動反映到`requirements.txt`裡，
  隱含依賴（例如`pandas.ExcelWriter(engine="openpyxl")`這種沒有top-level `import openpyxl`
  的用法）很容易漏掉，只有靠實際在乾淨環境跑一次才會發現。
- **中文字型在Linux上要手動註冊**：`matplotlib`預設字型在Ubuntu上沒有中文字，即使裝了
  `fonts-noto-cjk`，matplotlib的字型掃描常常抓不到`.ttc`合集檔裡的個別語系名稱——
  要用`matplotlib.font_manager.addfont()`手動註冊實際檔案路徑。另外`seaborn`跟`quantstats`
  的import過程會重設`rcParams`裡的字型設定，字型設定程式碼必須放在所有import**之後**才會生效
  （這個順序問題本機Mac因為PingFang TC是系統內建字型，就算被重設也還找得到中文字，才沒發現，
  但Linux CI沒有這層安全網）。見`factor_validation_analysis.py`頂部的CJK字型註冊區塊。

### 單一事實來源架構
`factor_definitions.json` 放所有計算參數、因子名稱/說明文字（含`{token}`佔位符）、公式、
可調參數筆記、程式位置、分級門檻、驗證參數。`update_dashboard.py`、`factor_validation_analysis.py`
從這裡讀參數；`generate_hub.py`從這裡產生`chart/index.html`（專案首頁）。要改因子：編輯這份
JSON，重跑`update_dashboard.py`，儀表板會自動同步更新（含各分項卡片「計算邏輯與資料來源」
面板裡的公式/參數/程式位置，2026-07-30起這幾項也注入到儀表板了，見下方遷移說明）。

`artifact_urls.json`：跨頁連結設定（`nav_bar.py`也讀這份）。目前留空，三個頁面（chart/底下）
互為同資料夾的相對路徑連結（GitHub Pages同站託管的緣故）。只有想改回發布到Claude Artifact
（各頁各自獨立網址）時才需要填值。

### 驗證報告與定義手冊：先遷移(2026-07-30)、後刪除(2026-08-13)
兩頁在2026-07-30從導覽列拿掉、內容遷移，檔案當時保留在`chart/`裡當備份；
2026-08-13清理repo時確認它們已無人可達（只剩5份舊格式報告的殘留舊導覽列連著），
連同產生它們的程式碼一併刪除：

- **`chart/factor_validation_report.html`（2.8MB）已刪**。它的產生者
  `factor_validation_analysis.main()`與只有它在用的5個render函式（共364行）也一併移除，
  該檔1074→708行。`factor_validation_analysis.py`本身**繼續當函式庫用**——`factor_screening.py`
  對它有大量依賴（`FACTOR_COLS`/`correlation_heatmap_base64`/`non_overlapping_ic`等）。
  原本報告裡的「因子相關係數矩陣」早已改造成因子篩選平台的隨選功能（見`correlation-matrix.yml`）。
- **`chart/manual.html`已刪**。手冊獨有的公式(`formula_tpl`)/參數筆記(`tuning_note`)/
  程式位置(`code_location`)三項，2026-07-30起已注入儀表板每張分項卡片的「計算邏輯與資料來源」
  面板；跨因子的「資料來源明細」「為何用百分位」折進gauge卡片的說明面板。
  互動試算器當時就直接移除、沒有搬到別的地方。
- 刪除前已先把5份舊格式報告（`screening_jpy/gold/vix_test/us10y/NQ_F`）殘留的舊導覽列
  換成現行版本，不留404。

需要看歷史版本請查git。


### 因子篩選框架（factor_screening.py）
跟儀表板並列的獨立功能（首頁是入口，不算功能本身），2026-07-28新增。除了測試新候選因子，
2026-07-30起也承接了原本驗證報告頁「因子相關係數矩陣」的隨選版本（見上方
`correlation-matrix.yml`說明）。
目的：之後想到新的候選因子，
填一張設定表餵進去，自動跑五道關卡判定該不該加入正式的綜合分數，不用每次重新手動分析。

**用法**：
```python
from factor_screening import screen_and_save
config = {
    "key": "my_candidate",             # 英文、當檔名跟欄位名用
    "label": "我的候選因子中文名",
    "mode": "return_spread",           # 六種模式之一，見下方
    "sources": {"a": "TLT", "b": "SHY"},   # 依mode不同,見TRANSFORM_MODES
    "params": {"window": 40},
    "invert": False,
}
screen_and_save(config)
```
或命令列：`python3 factor_screening.py my_candidate.json`（把上面的config存成json檔）。

**六種轉換模式**（`TRANSFORM_MODES`）：均線乖離百分位(`ma_deviation`)、區間位置(`range_position`，
本身已經是0-100不轉百分位)、兩序列報酬差百分位(`return_spread`)、兩序列差值百分位(`value_spread`)、
移動平均百分位(`moving_average`)、滾動統計量百分位(`rolling_stat`，`params.stat`可選`skew`/`std`/`median_dev`)。
既有七個因子全部落在這六種模式裡（可以直接讀`factor_screening.py`頂部的docstring對照）。
`sources`裡的值可以是df裡已有的欄位名稱字串，也可以是`{"yahoo": "TICKER"}`或`{"fred": "SERIES_ID"}`
指定全新資料來源（會自動抓取）。

**五道關卡**（2026-07-29起改成**永遠全部跑完、只給建議、不硬性擋關**——最終要不要採用交由
使用者自己判斷；門檻寫在`THRESHOLDS`常數裡，只用來生成建議文字，不會讓報告提前中止或消失。
單一關卡計算失敗只會讓那一關顯示「無法完成此關分析」，不影響其他關卡跟報告整體產生）：
1. 資料健檢：歷史長度、look-ahead檢查（抽樣日期截斷重算比對）、缺值比例、分數分佈鑑別力
2. 單獨效力：IC(5/10/20/60/120/250日，**重疊取樣為主**、非重疊取樣列為對照參考——
   跟`factor_validation_analysis.py`正式報告「非重疊為準」的方法論刻意不同，因為這個工具
   是永遠輸出、不做顯著性判斷的探索工具，重疊取樣的樣本量對初步篩選更有參考價值)、
   10年/20年分桶、雙版本熱力圖(原始報酬vs超額報酬,分桶×持有天數)、動能延續/長期反轉描述性
   標記(不當及格條件)
3. 穩定性：前後半段IC是否同號；跨Fed循環IC(用`regime_lib.py`,僅供參考)
4. 增量價值：跟現有官方因子相關係數上限0.6；加入候選後對綜合分數的LOO ΔIC方向是否為
   「拿掉候選IC會變差」
5. 可實作性：換手率(成本門檻尚待補上bps假設，目前只回報數字)

報告最上方固定顯示分數走勢圖(疊美國10年期公債殖利率參考線)跟原始資料走勢圖(依轉換模式
自動選擇對照方式，例如均線乖離秀原始序列+均線)，比照儀表板分項拆解卡片的呈現方式。
統計驗證標的維持ZN期貨不變；UST_10Yr殖利率只在圖表當視覺參考疊圖，不參與任何IC/統計計算
——這兩點是使用者明確要求過、容易被誤改的地方，改之前先確認需求。

**輸出**：`chart/screening_<key>.html`（單一因子完整體檢報告）、`chart/screening_index.html`
（登記簿一覽表，首頁第四張卡片連過去）、`factor_screening_registry.json`（登記簿資料來源，
append-only，**每次測試都會寫進去，不只是成功的**——這是刻意設計，用來防止多重比較偏誤造成的
自欺：測了很多次只記得成功那幾次，會誤判實際命中率）。

**重要的資料處理細節**（踩過的坑，換人接手時容易重犯）：
- 內部所有計算都用`fva.fetch_extended_history()`抓完整20年+5年暖身期的資料，
  絕對不要用`fva.load_data()`讀的已裁切6年CSV去算候選因子的分數——CSV已經裁掉暖身期，
  拿它算滾動百分位會在早期日期整段失真（實測過，直接用CSV算會跟正確答案的相關係數只有負值）。
- Look-ahead檢查(`_check_lookahead`)的截斷來源也必須是完整20年版本，不能是裁切過的6年版本，
  理由同上。
- `decile_bucket_analysis()`（10年/20年分桶用的函式）不會回傳`monotonicity`欄位，那個欄位
  只存在於5組版本`bucket_analysis()`裡——單獨效力關的分桶單調性是用主6年範圍跑`bucket_analysis()`
  另外算的，不是從10年分桶結果裡拿。
- `fva.FACTOR_COLS`是`{score_col: 中文名}`（例如`{"momentum_score": "動能"}`），key是欄位名
  不是短代號——不要誤用成`{短代號: score_col}`去查表，兩個方向搞反會讓相關係數關卡整個失效
  卻不會報錯（比對到不存在的欄位名，迴圈直接空跑過去）。

### 共用模組（避免各頁面各自維護一份、互相漂移）
- `nav_bar.py`：三個頁面共用的頂部導覽列（`render_nav_bar(active_key)` + `NAV_BAR_CSS`）。
  **非sticky**——原本做成sticky+吸附頂端，使用者實際用過後反而要求拿掉、改成跟著頁面內容
  一起捲動，四角全圓角、固定寬度置中——改動前先確認這個決定沒有被推翻。CSS自己帶一份
  獨立淺色/深色配色，不依賴各頁面自己的CSS變數系統。`PAGES`清單2026-07-30從5筆縮成3筆
  （拿掉report/manual），改動時注意這是全站唯一的nav來源，改一次全站生效。
- `page_style.py`：各頁面共用的排版基準數值（2026-07-29統一）——內容欄寬度`1120px`、
  body行高`1.6`、h1字級`32px`、說明段落可讀寬度`68ch`，加上儀表板/首頁有深色模式頁面共用
  的`:root`色彩變數(`ROOT_COLORS_CSS`)。**這不是要各頁共用同一份CSS選擇器**——各頁DOM結構
  本來就不同，選擇器名稱不用強求一致，這支模組解決的是「同一個概念要用同一個數字」。
  `factor_validation_analysis.py`的`REPORT_CSS`跟`factor_screening.py`的
  `render_registry_index()`各自有獨立的`<style>`區塊（後者**沒有**共用`REPORT_CSS`，
  是這次踩到的一個坑：一開始以為改`REPORT_CSS`會連動過去，實測才發現沒有，兩處都要記得改）。
  因子篩選平台目前沒有深色模式，這是刻意的，還沒補（使用者2026-07-29明確說先不補）。
- `transform_modes.py`：六種因子轉換模式、資料來源解析(`_resolve_source`)、候選分數計算
  (`build_candidate_score`)——原本定義在`factor_screening.py`裡，2026-07-29抽出來獨立成模組。
  **原因**：`update_dashboard.py`要用同一套邏輯重算「升等候選因子」的分數（見下方），但
  `factor_screening.py`本身已經`import update_dashboard as ud`，如果`update_dashboard.py`
  反過來`import factor_screening`會形成循環依賴。這支模組是最底層、不import另外兩支的共用
  邏輯，兩邊都能安全import。抓新資料(yahoo/fred)的能力故意用依賴注入(`fetch_yahoo`/`fetch_fred`
  參數)而不是直接import`update_dashboard`裡的抓取函式，避免二次循環依賴。

### 因子升等/退回路徑：篩選平台 ↔ 儀表板（2026-07-29新增升等，2026-07-30補上退回）
因子篩選平台驗證過的候選因子，可以在報告頁點「升等為可選因子」按鈕，讓它同時出現在
(a) 儀表板一張獨立分項卡片（標示「候選因子」，**不計入官方綜合分數**）跟
(b) 儀表板「自訂權重」區塊的可選清單裡。登記簿頁（`screening_index.html`）已升等的因子
那一列會顯示「已升等」徽章＋「退回」按鈕，可以把因子從儀表板整個移除（雙向、不是單向）。
- `promoted_candidate_factors.json`：升等暫存清單，跟`factor_definitions.json`（官方因子
  唯一事實來源）**刻意分開存放**，不會污染到官方定義。格式(`key`/`label`/`mode`/`sources`/
  `params`/`invert`)跟因子篩選平台的candidate config一致。
- `scripts/promote_factor.py`：`--config-json`寫入/更新這份清單裡對應`key`的條目（升等），
  `--remove KEY`移除對應條目（退回，Phase 6新增，跟`--config-json`互斥、擇一必填）。由
  `promote-factor.yml`依`workflow_dispatch`傳入`config_json`或`remove_key`哪個有值分流呼叫，
  也可以本機手動測試。
- `factor_screening.py`的`--rebuild-index`模式（Phase 6新增）：只重新產生`screening_index.html`、
  不重跑任何因子測試，用來刷新「已升等」徽章狀態。`promote-factor.yml`的升等跟退回兩條路徑
  跑完`update_dashboard.py`之後都會呼叫這個——**這是補上的一個既有缺口**：原本升等流程完全
  不會刷新登記簿頁，導致這頁的nav bar/樣式修正沒跟上過好幾次，2026-07-30起兩條路徑都會
  自動刷新，不會再脫節。
- `update_dashboard.py`的`compute_promoted_factors(df, out)`：讀這份清單，對每個因子用
  **完整歷史**(含5年百分位暖身期，理由同因子篩選平台的坑——不能用裁切過的`out`去算)重算
  分數與原始資料序列，注入前端`DATA`。單一因子算失敗只跳過那個因子、印警告，不會讓整個
  儀表板產生失敗（`try/except`包住每個因子）。刪除清單裡的條目、重新產生一次，該因子就會
  乾淨地從儀表板整個消失，不會有殘留狀態（`factor_definitions.json`、
  `factor_screening_registry.json`都不受影響，見上方遷移說明的驗證方式）。

### 儀表板進階互動功能（`chart/dashboard_template.html`）
- **自訂權重**（Phase 2/3，2026-07-29）：七個官方因子（加上任何已升等的候選因子）各自
  勾選+權重滑桿，純前端即時重算每日綜合分數（只對勾選且當天有資料的因子加權平均，權重依
  當天實際可用項目自動重新正規化），在主圖疊加一條虛線做歷史對照，不覆蓋、不影響上方官方
  gauge/比較列（這是刻意的設計決策——避免使用者以為多了一組「官方」數字）。可以用
  localStorage命名儲存/套用/刪除自己的權重組合（`bond_fg_custom_weight_presets_v1`），
  固定顯示「僅存於本裝置瀏覽器」提示。
- **情境動態權重併入自訂權重**（Phase 6，2026-07-30）：原本「情境加權分數」是主圖上獨立
  的紫色虛線+自己的checkbox，跟自訂權重是兩套互不相干的東西。使用者要求合併：自訂權重
  面板新增「套用目前情境動態權重」按鈕，點下去把`REGIME_META.weight_by_regime[今天所屬
  的Fed循環階段]`的權重值當作**起始值**帶入滑桿（候選因子跟Put/Call不在情境權重表裡，
  給該情境當下最低權重同等的保守值），套用後使用者仍可自行拖曳任何滑桿繼續微調——這不是
  再做一條獨立的動態線，是把情境權重表當成自訂權重的一個「智慧預設」。主圖現在只剩一條
  自訂/情境共用的疊加線，原本寫死`series[1]`的`#regimeToggle`已移除。
- **全面線條開關**（Phase 6，2026-07-30）：`buildChart()`新增`setEventsVisible(v)`方法，
  主圖新增「顯示事件標記線」整體開關；每張分項卡片的分數線本身、以及多線原始數據圖（例如
  強度卡的NQ期貨/252日高點/252日低點三條線）都補上各自的checkbox（沿用既有的
  `.overlay-toggle`樣式），維持預設全部可見。已經有開關的線（UST10Y疊加線、自訂/情境
  疊加線）維持原樣沒動。
- **事件行事曆**（Phase 5，2026-07-29）：`event_calendar.json`（FOMC/CPI/NFP等總經事件，
  手動維護的靜態清單，欄位跟資料來源無關，方便以後換成串接外部API）。主圖表疊加事件垂直
  標記線；頁面右側新增可獨立捲動的事件時間軸side rail（`.page-shell`兩欄式版面）。
  雙向同步：點主圖表任一天會捲動並高亮事件欄最近的事件，點事件欄任一事件會讓主圖表跳到
  對應日期——共用既有的`setSelectedIndex()`分派機制。**`event_calendar.json`裡2026年的
  FOMC/CPI日期是推估值、不是逐一核對過的官方日期**，NFP(每月第一個週五)是精確計算，
  可信度較高，2025年FOMC是官方公告的實際日期。上線後要記得定期對照Fed/BLS官方行事曆校正。
  **踩過的坑**：右側事件欄一開始用`scrollIntoView()`+`behavior:"smooth"`捲動，但
  `.event-rail`是`position:sticky`容器，某些瀏覽器/自動化環境下這個組合完全不會動——
  改成直接算座標用`scrollTo()`+`behavior:"auto"`（無動畫，即時跳轉）解決。

### 其他檔案說明
- `regime_lib.py`：情境（Fed利率循環）分類共用邏輯。
- `regime_weights_v1.json`：情境動態權重的凍結權重快照，只在手動執行
  `derive_regime_weights.py` 時才會重新產生——不是每天自動算，不會被daily workflow動到。
  2026-07-30起這份權重表用途改成「套用進自訂權重面板的滑桿起始值」，不再是獨立的一條線
  （見上方「儀表板進階互動功能」）。
- `scripts/generate_correlation_matrix.py`：因子相關係數矩陣的隨選產生腳本（Phase 7新增），
  由`correlation-matrix.yml`呼叫，直接重用`factor_validation_analysis.correlation_heatmap_base64()`。
- `data_input.xlsx`：使用者手動輸入/覆蓋的原始資料，填的值優先於自動抓取。
- `scripts/check_consistency.py`：**靜態一致性檢查，已接進`update-and-deploy.yml`最前面**。
  純靜態不發網路請求、一秒跑完。檢查因子清單/資料管線/儀表板模板/文案/登記簿寫入方式
  是否互相脫鉤——過去這類問題全都是上線後才發現，現在部署前就會擋下來。改因子後務必跑。
- `factor_scores_matrix.csv` / `partb_combination_results.csv`：2026-08-05的靜態快照
  （11因子）。產生前者的腳本依賴已刪除的舊七因子，**目前無法重新產生**；
  相關係數矩陣的「歷史因子」選項用的就是這份。

### 不是正式pipeline的一部分、但保留在repo裡的研究工具
不進導覽列、不在CI跑，本機手動執行用來回答特定問題：
- `scripts/sweep_window_sensitivity.py`：因子視窗長度敏感度掃描（同時看完整歷史與2020+
  兩個期間，避免只看單一期間就下結論）。
- `scripts/walkforward_window_selection.py`：walk-forward參數驗證——每年只用當時之前的
  資料重選參數再套到下一年，判斷「最佳參數」到底挑不挑得出來。
- `scripts/screen_composite_2factor.py`：把因子組合當成一個因子跑完整五關（用`composite_mean`模式）。
- `scripts/build_direct_parta_html.py`：只產Part A統計分布、**不跑五關**。用前務必看檔頭
  說明——它曾經把五關結果寫死成假值上過正式站。
- `scripts/run_partb_combination_backtest.py`：Part B組合爆破回測，產出`partb_combination_results.csv`。

### 不要納入版本控制的東西（已寫進 .gitignore）
`venv/`、每次重跑會重新產生的CSV/xlsx資料檔——這些是從Yahoo/Treasury/FRED重新抓來的，
每天都會變，追蹤它們的歷史只會製造雜訊。
