# 美債市場恐懼貪婪儀表板

用美國公債市場相關資料（殖利率曲線、MOVE 波動指數、避險需求、Put/Call 等）建構的
「美債版恐懼貪婪指數」，含儀表板、指標定義手冊、因子驗證分析報告。

🌐 **上線網址**：https://dp79b47tvn-maker.github.io/bond-fear-greed-dashboard/

透過 GitHub Actions **每個交易日美股收盤後自動重新抓資料、重算、部署**（cron 排程，見
`.github/workflows/update-and-deploy.yml`），不需要手動更新。

跟同一位使用者的另一個專案 [`fg-nq-analysis`](https://github.com/dp79b47tvn-maker/fg-nq-analysis)
（CNN 股市版恐懼貪婪指數對 ^NDX/SP500 的驗證）方法論同源，但兩者完全獨立，不共用資料或程式碼。

## 專案結構

```
update_dashboard.py           # 抓資料、算分數、重新產生 chart/dashboard.html
generate_manual.py            # 產生 chart/manual.html(指標定義手冊) 與 chart/index.html(首頁)
factor_validation_analysis.py # 因子驗證分析(IC/分桶/回測)，產生 chart/factor_validation_report.html
factor_definitions.json       # 單一事實來源：所有因子的計算參數、標籤門檻、說明文字
regime_lib.py                 # 情境(Fed利率循環)分類共用邏輯
scripts/verify_dashboard.py   # 發布前自動檢查(JS語法/JSON合法性/關鍵HTML id)
chart/                        # 前端頁面，這個資料夾整個部署到 GitHub Pages
data_input.xlsx               # 使用者手動輸入/覆蓋的原始資料(例如Put/Call)，優先於自動抓取
```

## 本機開發

```bash
pip install -r requirements.txt
python3 update_dashboard.py            # 重新產生 chart/dashboard.html
python3 generate_manual.py             # 重新產生 chart/manual.html + chart/index.html
python3 factor_validation_analysis.py  # 重新產生 chart/factor_validation_report.html
python3 scripts/verify_dashboard.py    # 發布前一定要過這個檢查
```

`chart/*.html` 這幾個是產物，本機重新產生後 commit 回 repo，GitHub Actions 會自動部署；
也可以完全不管本機、直接 push 到 `main`，Actions 會在雲端重跑整套流程。

## 給 AI Agent 的說明

完整的開發/發布規則、單一事實來源的因子設定架構、常見的坑，請讀 [`AGENTS.md`](./AGENTS.md)——
這是跨平台通用版本，不限 Claude Code，Cursor/Windsurf/Copilot 等工具也讀得到（各自有對應的
薄指標檔 `.cursorrules`／`.windsurfrules`／`.github/copilot-instructions.md` 指回這裡）。
`CLAUDE.md` 現在也只是指回 `AGENTS.md` 的指標檔，內容不重複維護。
