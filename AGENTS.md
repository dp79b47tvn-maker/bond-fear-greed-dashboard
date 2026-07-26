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
  如果你push時遇到`chart/dashboard.html`或`chart/factor_validation_report.html`衝突，
  這是預期中的——用 `git checkout --theirs <file>`（rebase情境下"theirs"＝你正在重放的本機commit）
  保留本機剛重新產生的版本，用`git diff <你的原始commit> -- <file>`確認兩者內容一致再push。

### 7. 災難復原協議（Restore vs. Revert）
- **未 commit 的壞程式碼**：`git restore .` 立刻回到上一個乾淨的 commit。
- **已 commit 的壞程式碼**：`git revert <commit-hash>` 建立反向 commit 安全撤銷，保留完整稽核歷史。
- **不要**只靠某個平台自己的「版本歷史」UI 回溯（例如Claude Artifact右上角的版本選單）——
  那些平台專屬的歷史，換了agent或平台就讀不到。git是所有agent都能讀取比對的共同依據。

---

## Part 2｜這個專案的具體操作方式

### 這是什麼
債券市場恐懼貪婪儀表板：7項美債市場指標彙整成每日恐懼貪婪分數，含儀表板、因子驗證分析報告、
因子定義手冊三個頁面，全部由 `factor_definitions.json` 這份單一定義檔驅動。

### 正式發布管道（目前唯一的正式管道，不是Claude Artifact）
專案已經上架在GitHub Pages公開發布，跟任何特定AI工具無關：
- 正式網址：`https://dp79b47tvn-maker.github.io/bond-fear-greed-dashboard/`
- GitHub repo：`git@github.com:dp79b47tvn-maker/bond-fear-greed-dashboard.git`
- `.github/workflows/update-and-deploy.yml`：GitHub Actions排程，每個交易日美股收盤後
  （22:00 UTC）自動重跑三支腳本、驗證、commit回repo、部署——**不需要任何AI agent介入**，
  純粹是GitHub自己的排程機器人在跑。也可以手動觸發（repo的Actions頁面 → workflow_dispatch）。
- Claude Artifact發布（`chart/dashboard.html`等）是**次要/預覽用途**，不是正式管道，
  現在也不是每次修改都需要同步做。

### 本機開發迴圈
1. 改 `chart/dashboard_template.html`、`factor_definitions.json`、或任何一支 `*.py` 之後：
   ```
   python3 update_dashboard.py          # 重新產生 chart/dashboard.html
   python3 generate_manual.py           # 重新產生 chart/manual.html、chart/index.html
   python3 factor_validation_analysis.py  # 重新產生 chart/factor_validation_report.html（較慢，~4分鐘，會重抓20年歷史資料）
   ```
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
`factor_definitions.json` 放所有計算參數、因子名稱/說明文字（含`{token}`佔位符）、
分級門檻、驗證參數。`update_dashboard.py`、`factor_validation_analysis.py`從這裡讀參數；
`generate_manual.py`從這裡產生`chart/manual.html`（定義手冊，含互動試算器）跟`chart/index.html`
（專案首頁）。要改因子：編輯這份JSON，重跑上面三支腳本，儀表板/報告/手冊會自動同步更新，
不用分別去改三個地方的文字。

`artifact_urls.json`：跨頁連結設定。目前留空，四個頁面（chart/底下）互為同資料夾的相對路徑連結
（GitHub Pages同站託管的緣故）。只有想改回發布到Claude Artifact（各頁各自獨立網址）時才需要填值。

### 其他檔案說明
- `regime_lib.py`：情境（Fed利率循環）分類共用邏輯。
- `regime_weights_v1.json`：情境加權分數（實驗性）的凍結權重快照，只在手動執行
  `derive_regime_weights.py` 時才會重新產生——不是每天自動算，不會被daily workflow動到。
- `data_input.xlsx`：使用者手動輸入/覆蓋的原始資料（例如Put/Call），填的值優先於自動抓取。

### 不是正式pipeline的一部分、但保留在repo裡的探索性工具
- `decile_overlap_comparison.py`：獨立腳本，比較10年/20年分桶分析在「非重疊」vs「重疊」
  取樣下的差異，純粹給使用者自己評估、決定要不要換正式報告的取樣方式用，
  輸出`chart/decile_overlap_comparison.html`不連結進首頁/導覽列，也不是每次pipeline都要重跑。

### 不要納入版本控制的東西（已寫進 .gitignore）
`venv/`、每次重跑會重新產生的CSV/xlsx資料檔——這些是從Yahoo/Treasury/FRED重新抓來的，
每天都會變，追蹤它們的歷史只會製造雜訊。
