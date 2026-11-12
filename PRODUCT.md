# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

主要使用者是作者本人：大學四年級、產經系，用這個專案做財務研究與交易分析。這個專案也會放進履歷與申請文件，所以第二群讀者是面試官與教授。他們通常是第一次來，要在十秒內看懂三件事：這是什麼、分數怎麼算、能不能信。

## Product Purpose

用美國公債市場資料算出 0 到 100 的恐懼貪婪分數，每個交易日美股收盤後由 GitHub Actions 自動重算並發布到 GitHub Pages。附一個因子開發與篩選平台，用來測試新候選因子能不能加進綜合分數。

成功的樣子：看起來像一個有判斷力的人做的研究工具，而不是範本套出來的儀表板；資訊誠實，不誇大分數的預測力。專案自己的研究結論是它不是預測模型。

## Positioning

公開所有計算方式、資料來源跟失敗的測試。登記簿是 append-only，每一次因子測試都留下紀錄，不只留成功的，用來避免多重比較偏誤。研究結論（兩個因子方向相反、合成後摸不到極端值、參數選不出最佳值）直接寫在頁面上，而不是藏起來。

## Operating Context

- 三個公開頁面：首頁（`chart/index.html`）、儀表板（`chart/dashboard.html`）、因子開發與篩選平台（`chart/screening_index.html` 加上各因子報告頁 `chart/screening_<key>.html`）。
- 主要在筆電螢幕、白天使用；偶爾用手機拿給別人看。
- 任務：看今天的分數與歷史走勢；拆解各因子；測試新因子。
- 頁面是 Python 產生的靜態 HTML（`update_dashboard.py`、`generate_hub.py`、`factor_screening.py`），GitHub Pages 託管。篩選平台的提交、升等、相關係數矩陣是用瀏覽器 localStorage 裡的 GitHub PAT 觸發 workflow_dispatch。
- 介面有中英文切換（`nav_bar.py` 的字典）與淺深色模式（儀表板、首頁）。

## Capabilities and Constraints

- 因子數量會變，以 `factor_definitions.json` 為準，文案不寫死數量（目前兩項：動能、銅金比）。
- 不能動：分數的算法與研究結論；台灣紅綠慣例（紅＝貪婪、綠＝恐懼）；導覽列決定（非 sticky、置中固定寬度、四角圓角）；驗證標的是 UST_10Yr 殖利率變動，ZN 只當參考；登記簿 append-only。
- `chart/*.html` 是產物，只改產生它們的原始檔。模板文字不能出現雙底線包起來的佔位符字面字串。

## Brand Commitments

- 名稱：債券市場恐懼貪婪（英文 U.S. Bond Fear & Greed）。專案在其他文件中也稱 Treasury Pulse。
- 語氣：繁體中文、台灣用語、全形標點；說明文字直接講事實與限制，不寫成產品文案，不對訪客顯示開發者資訊。
- 「不是預測模型、也不是投資建議」這類聲明的意思要保留。
- 視覺路線（2026-11-12 作者選定）：業界標準的金融資料工具，不走主題式世界。做工標竿是 FRED（聖路易聯準銀行）、Koyfin、CNN Fear & Greed；在這個標竿下仍不用 AI 慣用字體與配色（Inter、DM Sans、Space Grotesk、IBM Plex 等，紫靛色強調、冷灰底加白卡、漸層、發光），不用大寫小標籤、藥丸形按鈕、emoji 圖示、卡片套卡片、每個區塊同樣的進場動畫。
- 三個公開頁面都有淺色與深色模式（篩選平台的深色模式於 2026-11-12 決定補上）。

## Evidence on Hand

- 每日分數歷史（`chart/dashboard_data.json`）、事件行事曆（`event_calendar.json`）、因子測試登記簿（`factor_screening_registry.json`，24 筆）、研究結論（`HANDOVER.md` 第 8 節）。
- 沒有使用者見證、沒有績效宣稱可用；回測數字只能引用登記簿與報告裡實際算出來的。

## Product Principles

1. 誠實優先：頁面講清楚分數能做什麼、不能做什麼，失敗的測試也看得到。
2. 可驗算：每個分數都能追到原始數值、公式與資料來源。
3. 第一次來的人十秒內看懂，熟悉的人每天掃一眼就夠。
4. 一份定義驅動全部頁面，數量與參數不寫死在文案。

## Accessibility & Inclusion

紅綠色盲看不出紅綠差異，所以恐懼與貪婪兩端要用明度拉開，而且每個分數旁邊都保留文字標籤。正文對比 4.5:1、大字 3:1。
