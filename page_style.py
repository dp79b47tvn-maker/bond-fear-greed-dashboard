# -*- coding: utf-8 -*-
"""
五個對外頁面(首頁/儀表板/驗證報告/定義手冊/因子篩選平台)共用的排版基準數值。

背景：這五個頁面各自獨立寫了一份<style>，同一個概念(內容欄寬度、標題字級、
本文行高、說明段落的可讀寬度)在五頁上長期各自漂移成五種不同數字，切頁面時
畫面明顯不連貫；顏色更誇張——儀表板/手冊/首頁三頁其實是同一套品牌色，卻各自
取了三種不同的CSS變數名稱(--series-1 vs --accent、--text-primary vs --text)。

這支模組不是要五頁共用同一份CSS選擇器——各頁DOM結構本來就不同，選擇器名稱
不用強求一致。它解決的是「同一個概念要用同一個數字」，比照nav_bar.py已經
驗證過的做法：色彩變數(ROOT_COLORS_CSS)是真的共用同一份定義(有dark mode的
儀表板/手冊/首頁三頁一起用)；間距/字級/行高這些純量值，用同一個常數在四支
產生腳本裡各自的CSS規則中插入，維持各頁選擇器名稱不變、只統一數字。

範圍刻意限定：這次不幫驗證報告(factor_validation_analysis.py)、因子篩選平台
(factor_screening.py)補上深色模式——它們目前完全沒有(純hex、無CSS變數)，
維持現狀，這次只統一它們在亮色模式下的間距/字級/行高數字。

依可讀性準則(每行65-75字元、行高1.5-1.75)校準的四個基準：
"""

# 內容欄寬度：儀表板原1180px / 手冊原1080px / 首頁原880px / 驗證報告&篩選平台原980px
# → 統一取儀表板與手冊之間的數字
CONTENT_MAX_WIDTH = "1120px"

# body基礎行高：儀表板原1.5 / 手冊&首頁原1.7 / 驗證報告&篩選平台原1.6 → 統一取中間值
BASE_LINE_HEIGHT = "1.6"

# 主標題字級：儀表板原34px / 手冊原30px / 首頁原32px / 驗證報告&篩選平台原30px → 統一
H1_SIZE = "32px"

# 說明段落/長句文字的可讀寬度(65-75字元準則)：手冊原70ch / 首頁原64ch /
# 儀表板原860px(固定值，字級一變寬度就不對) / 驗證報告&篩選平台原本沒限制 → 統一成ch單位
LEDE_MAX_WIDTH = "68ch"

FONT_FAMILY = (
    '-apple-system, BlinkMacSystemFont, "PingFang TC", "Noto Sans TC", '
    '"Microsoft JhengHei", "Segoe UI", Roboto, Helvetica, Arial, sans-serif'
)

# 儀表板/手冊/首頁三頁共用同一份色彩變數——這三頁都有深色模式支援，數值取自
# 原本儀表板的版本(三頁裡最完整的一份)，手冊/首頁原本各自的--accent/--text等
# 命名全部改叫這份的名稱，不再各自維護一套指向同樣顏色的不同變數名。
ROOT_COLORS_CSS = """
  :root {
    --page: #f4f5f7; --surface-1: #ffffff; --surface-2: #f8f9fb;
    --text-primary: #161a23; --text-secondary: #4a5568; --text-muted: #667085;
    --grid: #e5e7eb; --axis: #a7adb9;
    --series-1: #1e3a5f; --series-2: #a6742a; --series-3: #5b4f8a; --series-4: #1f7a7a;
    --border: #dfe2e8; --shadow: 0 1px 2px rgba(22,26,35,0.04);
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --page: #0f1218; --surface-1: #171b24; --surface-2: #1e232d;
      --text-primary: #f1f3f6; --text-secondary: #b8c0cc; --text-muted: #8b93a3;
      --grid: #262b36; --axis: #4a5164;
      --series-1: #7ea3cf; --series-2: #d9a860; --series-3: #a698d4; --series-4: #5fb8b8;
      --border: #2c313d; --shadow: 0 1px 2px rgba(0,0,0,0.35);
    }
  }
  :root[data-theme="dark"] {
    --page: #0f1218; --surface-1: #171b24; --surface-2: #1e232d;
    --text-primary: #f1f3f6; --text-secondary: #b8c0cc; --text-muted: #8b93a3;
    --grid: #262b36; --axis: #4a5164;
    --series-1: #7ea3cf; --series-2: #d9a860; --series-3: #a698d4; --series-4: #5fb8b8;
    --border: #2c313d; --shadow: 0 1px 2px rgba(0,0,0,0.35);
  }
  :root[data-theme="light"] {
    --page: #f4f5f7; --surface-1: #ffffff; --surface-2: #f8f9fb;
    --text-primary: #161a23; --text-secondary: #4a5568; --text-muted: #667085;
    --grid: #e5e7eb; --axis: #a7adb9;
    --series-1: #1e3a5f; --series-2: #a6742a; --series-3: #5b4f8a; --series-4: #1f7a7a;
    --border: #dfe2e8; --shadow: 0 1px 2px rgba(22,26,35,0.04);
  }
"""
