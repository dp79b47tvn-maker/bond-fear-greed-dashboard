# 債券市場恐懼貪婪儀表板 — 開發與發布流程

## 發布到 Artifact 前，一律照這個順序做

1. 改完 `chart/dashboard_template.html` 或 `update_dashboard.py` 之後，執行：
   ```
   python3 update_dashboard.py
   ```
   重新產生 `chart/dashboard.html`。

2. 跑自動檢查：
   ```
   python3 scripts/verify_dashboard.py
   ```
   沒過（exit code非0）就不要往下發布——先照印出來的訊息修好。
   這支腳本會抓：JS語法錯誤（`node --check`）、DATA/REGIME_META是否為合法JSON、
   關鍵HTML id是否還在。**2026-07-18發生過一次事故**：說明文字裡誤用了
   markdown反引號（`` `xxx.py` ``），剛好包在JS模板字串裡面，提前把字串截斷，
   導致整個`<script>`區塊語法錯誤、整頁空白，卻沒有任何機制擋下來——這支腳本
   就是為了不要再發生這種事。

3. 檢查通過後，**先commit再發布**：
   ```
   git add -A
   git commit -m "說明這次改了什麼"
   ```
   commit訊息要講清楚做了什麼改動，之後才能靠 `git log` 找回對應版本。

4. 用 `Artifact` 工具發布 `chart/dashboard.html`，**沿用同一個 file_path 和 url**
   （不要開新連結），這樣才會更新到同一個Artifact，而不是產生新的。

## 如果對某個版本不滿意，想回到上一版

```
git log --oneline                      # 看歷史，找到想回去的那個commit
git diff <commit>                      # 先看看那個commit跟現在差在哪，別瞎猜
git checkout <commit> -- .             # 把檔案還原成那個commit的狀態
python3 update_dashboard.py            # 重新產生 dashboard.html（規則1一定要跑）
python3 scripts/verify_dashboard.py    # 驗證一定要過
# 通過後用 Artifact 工具重新發布同一個連結
```

**不要**只靠Artifact網頁右上角的版本選單回溯——那是Artifact平台自己的歷史，
不透過API開放讀取，Claude沒辦法直接查到某個舊版本的內容，只能看到最新發布版本。
git是本機、Claude隨時可以讀取比對的版本歷史，才是實際可回溯的依據。

## 檔案說明

- `chart/dashboard_template.html`：畫面/邏輯的原始碼，含 `__DATA_JSON__`、
  `__REGIME_META_JSON__` 兩個佔位符。
- `chart/dashboard.html`：`update_dashboard.py` 注入資料後產生的最終檔案，
  **就是實際發布到Artifact的那個檔案**。
- `regime_lib.py`：情境（Fed利率循環）分類共用邏輯。
- `regime_weights_v1.json`：情境加權分數的凍結權重快照，只在手動執行
  `derive_regime_weights.py` 時才會重新產生——不是每天自動算。
- `data_input.xlsx`：使用者手動輸入/覆蓋的原始資料（例如Put/Call），
  填的值優先於自動抓取。

## 不要納入版本控制的東西（已寫進 .gitignore）

`venv/`、每次重跑會重新產生的CSV/xlsx資料檔（`bond_fear_greed_v2.csv`等）——
這些是從Yahoo/Treasury/FRED重新抓來的，每天都會變，追蹤它們的歷史只會製造雜訊。
