# 美債市場恐懼貪婪儀表板

用美國公債市場資料建構的「美債版恐懼貪婪指數」（0–100 分），含儀表板與因子開發／篩選平台
兩個對外功能，首頁是入口。全站支援中英文切換。

🌐 **上線網址**：https://dp79b47tvn-maker.github.io/bond-fear-greed-dashboard/

透過 GitHub Actions **每個交易日美股收盤後自動重新抓資料、重算、部署**（cron 排程，見
`.github/workflows/update-and-deploy.yml`），不需要手動更新。

> 📖 **第一次接觸這個專案？** 請先讀 **[`HANDOVER.md`](./HANDOVER.md)** ——
> 那份寫給接手的人，涵蓋分數怎麼算、怎麼跑、改東西要注意什麼、前人踩過哪些坑，
> 以及目前的研究結論。

跟同一位使用者的另一個專案 [`fg-nq-analysis`](https://github.com/dp79b47tvn-maker/fg-nq-analysis)
（CNN 股市版恐懼貪婪指數對 ^NDX/SP500 的驗證）方法論同源，但兩者完全獨立，不共用資料或程式碼。

## 目前的因子組成（兩項）

| 因子 | 算法 | 方向 |
|---|---|---|
| **動能** | US 10Y 殖利率 − 其 125 日均線 → 5年滾動百分位 → 反轉 | 殖利率高於均線＝價格跌破均線＝恐懼 |
| **銅金比** | 銅期貨(HG=F) 60 日報酬 − 金期貨(GC=F) 60 日報酬 → 5年滾動百分位 | 銅相對金走強＝風險偏好回升＝貪婪 |

**綜合分數 = 兩項等權重平均**（某項當天無資料自動排除，不填假值）。
分級：0–24 極度恐懼／25–44 恐懼／45–55 中性／56–75 貪婪／76–100 極度貪婪。

> **2026-08-05 起因子從七項縮減為兩項**（原本還有強度、存續期間避險、Put/Call、波動度、
> 殖利率曲線、通膨意外）。repo 裡部分歷史文件仍描述七因子版本，一律以
> `factor_definitions.json` 為準。

## 專案結構

```
factor_definitions.json        ★ 唯一事實來源：因子定義、計算參數、資料來源、說明文字
update_dashboard.py            抓資料 → 算分數 → 產生 chart/dashboard.html
generate_hub.py                產生 chart/index.html(首頁)
transform_modes.py             8 種因子轉換模式，儀表板與篩選平台共用同一份實作
factor_screening.py            因子篩選平台：五道關卡、回測分析、報告產生、登記簿
factor_validation_analysis.py  IC/分桶/統計分布等計算函式庫(factor_screening 的依賴)
nav_bar.py / page_style.py     三個頁面共用的導覽列(含中英文切換)與樣式
regime_lib.py                  Fed 利率循環階段分類

scripts/check_consistency.py   ★ 靜態一致性檢查(已接進 CI，改因子後務必跑)
scripts/verify_dashboard.py    發布前檢查(JS語法/JSON合法性/關鍵HTML id)
scripts/…                      其餘腳本說明見 HANDOVER.md 第 4 節

chart/                         前端頁面，這個資料夾整個部署到 GitHub Pages
data_input.xlsx                使用者手動輸入/覆蓋的原始資料，優先於自動抓取
```

## 本機開發

```bash
pip install -r requirements.txt

python3 scripts/check_consistency.py   # 一致性檢查(純靜態，一秒跑完)
python3 update_dashboard.py            # 重新產生 chart/dashboard.html
python3 generate_hub.py                # 重新產生 chart/index.html
python3 scripts/verify_dashboard.py    # 發布前一定要過這個檢查
```

`chart/*.html` 是產物，本機重新產生後 commit 回 repo，GitHub Actions 會自動部署；
也可以完全不管本機、直接 push 到 `main`，Actions 會在雲端重跑整套流程。

### 改因子只要動一個檔

新增/移除因子、改參數、改資料來源，原則上只需要改 `factor_definitions.json`，
兩支資料抓取函式都由它驅動。改完跑 `scripts/check_consistency.py`，
它會告訴你還有哪裡沒跟上（儀表板模板裡有兩個手刻的 JS 陣列需要一起改）。

## 因子篩選平台

想到新的候選因子時，填一張設定表餵給 `factor_screening.py`，自動跑五道關卡
（資料健檢／單獨效力／穩定性／增量價值／可實作性），並產出含統計分布與回測分析的報告：

```python
import factor_screening as fs
fs.screen_and_save({
    "key": "my_factor", "label": "【候選】我的新因子",
    "mode": "return_spread",
    "sources": {"a": {"yahoo": "XXX"}, "b": {"fred": "YYY"}},
    "params": {"window": 60}, "invert": False,
})
```

也可以用 `composite_mean` 模式把**因子組合**當成一個因子來測，不用為每種組合寫一次性腳本。

每次測試都會 **append** 一筆到 `factor_screening_registry.json`，
累積結果看 `chart/screening_index.html`（首頁第二張卡片連過去）。
這份登記簿刻意記錄「每一次」測試、不只是成功的——測了 20 次只記得成功那 1 次會嚴重高估
命中率，這是防多重比較偏誤的機制，**任何寫入都必須讀取→合併→寫回，絕不可覆寫**。

同一頁也能勾選因子隨選產生相關係數矩陣。

## 給 AI Agent 的說明

完整的開發/發布規則、單一事實來源架構、常見的坑，請讀 [`AGENTS.md`](./AGENTS.md)——
這是跨平台通用版本，不限 Claude Code，Cursor/Windsurf/Copilot 等工具也讀得到（各自有對應的
薄指標檔 `.cursorrules`／`.windsurfrules`／`.github/copilot-instructions.md` 指回這裡）。
`CLAUDE.md` 也只是指回 `AGENTS.md` 的指標檔，內容不重複維護。

**注意**：`AGENTS.md` 是給工具讀的協作規範，不是專案說明文件。
想了解專案本身請看 [`HANDOVER.md`](./HANDOVER.md)。
