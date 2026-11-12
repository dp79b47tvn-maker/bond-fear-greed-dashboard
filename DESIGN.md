---
name: 債券市場恐懼貪婪（Treasury Pulse）
description: 美國公債市場的每日 0–100 恐懼貪婪分數與因子篩選平台；業界標準的金融資料工具，標竿 FRED、Koyfin、CNN Fear & Greed。
colors:
  page: "#ffffff"
  surface-2: "#f4f4f1"
  surface-3: "#e9eae6"
  text-primary: "#1b1d1f"
  text-secondary: "#45494d"
  text-muted: "#62676c"
  border: "#d5d7d2"
  rule: "#e3e4e0"
  grid: "#ebece8"
  axis: "#8c9195"
  accent: "#1d5a96"
  series-yield: "#9c5a0c"
  series-ref: "#56606a"
  series-custom: "#2b3136"
  tier-extreme-fear: "#174f33"
  tier-fear: "#3b7654"
  tier-neutral: "#5c6166"
  tier-greed: "#b9452f"
  tier-extreme-greed: "#d1281c"
  warn: "#8a5a00"
  danger: "#b42318"
  selection: "#cfe0f2"
  dark-page: "#121416"
  dark-text-primary: "#ecedea"
  dark-accent: "#8db8e8"
typography:
  h1:
    fontFamily: "Public Sans, Noto Sans TC Subset, PingFang TC, Microsoft JhengHei, sans-serif"
    fontSize: "30px"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.015em"
  section:
    fontFamily: "Public Sans, Noto Sans TC Subset, sans-serif"
    fontSize: "19px"
    fontWeight: 700
  card-title:
    fontFamily: "Public Sans, Noto Sans TC Subset, sans-serif"
    fontSize: "17px"
    fontWeight: 700
  body:
    fontFamily: "Public Sans, Noto Sans TC Subset, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.6
  small:
    fontFamily: "Public Sans, Noto Sans TC Subset, sans-serif"
    fontSize: "12.5px"
    fontWeight: 400
  score-hero:
    fontFamily: "Public Sans, sans-serif"
    fontSize: "56px"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "-0.02em"
rounded:
  control: "4px"
  panel: "8px"
  nav: "10px"
spacing:
  gutter: "24px"
  gutter-mobile: "16px"
  section: "36px"
  block: "24px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.page}"
    rounded: "{rounded.control}"
    padding: "9px 18px"
  button-secondary:
    backgroundColor: "{colors.page}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.control}"
    padding: "5px 12px"
  segmented-active:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.page}"
  input:
    backgroundColor: "{colors.page}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.control}"
    height: "36px"
  nav-bar:
    backgroundColor: "{colors.page}"
    rounded: "{rounded.nav}"
    height: "56px"
---

# Design System: 債券市場恐懼貪婪

## Overview

業界標準的金融資料工具，不走主題式視覺世界。做工標竿是 FRED（聖路易聯準銀行）、Koyfin、CNN Fear & Greed：白底、細線分區、數字對齊、圖表優先。風格只出現在細節上：Public Sans（美國聯邦網站設計系統 USWDS 的標準字）帶來的政府資料站語感、深藍主色、台灣紅綠慣例的分級色。

三個頁面的模式不同：儀表板與因子篩選平台是操作型頁面，掃讀速度與一致性優先；首頁是說服型頁面，第一屏直接放今天的分數與近一年走勢，讓第一次來的人十秒內看懂這是什麼。

所有 token 定義在 `page_style.py`，由各產生腳本注入 `ROOT_COLORS_CSS`（字型宣告＋色彩 token＋基礎規則）。各頁不寫死 hex。

## Colors

淺色模式是白底加暖中性灰的線；深色模式（跟著系統設定）是近黑暖灰底。兩套都定義在 `page_style.LIGHT` / `page_style.DARK`。

### Primary
- **accent `#1d5a96`**（深色 `#8db8e8`）：連結、目前頁面、焦點框、主要按鈕、綜合分數線。這是頁面上唯一的品牌色。

### Secondary
- **series-yield `#9c5a0c`**：10 年期殖利率參考線、CPI 事件標籤。
- **series-ref `#56606a`**、**series-custom `#2b3136`**：原始資料圖的第二條線、自訂權重虛線。

### Neutral
- page `#ffffff`、surface-2 `#f4f4f1`（表頭、輸入框、說明面板）、rule `#e3e4e0`（分區線）、border `#d5d7d2`（元件外框）、text 三階 `#1b1d1f` / `#45494d` / `#62676c`。

### Named Rules
- **台灣紅綠規則**：紅＝貪婪、綠＝恐懼。`--tier-*` 依意義命名，不依色相。
- **明度分開規則**：紅綠色盲分不出色相，所以恐懼與貪婪兩端用明度拉開（淺色：極度恐懼最深 `#174f33`、極度貪婪較亮 `#d1281c`；深色反過來），每個分數旁一定有文字標籤。
- **tier 色即文字色**：五級分級色會直接當分數與標籤的文字色，每一級對底色都要 ≥ 4.5:1。
- **參考線不用 tier 色**：殖利率、均線、高低點不代表恐懼或貪婪，一律用 series 色。

## Typography

拉丁字與數字用 Public Sans（400/600/700，自架 woff2，各約 14.6 KB），漢字用 Noto Sans TC 子集（400/700，只收專案用到的 1,225 字，各約 260 KB），子集外的字落到系統黑體。字型總計 576 KB。全站 `font-variant-numeric: lining-nums tabular-nums`，分數、殖利率、日期上下對齊。程式代號（`UST_10Yr` 等）才用等寬字。

### Hierarchy
- h1 30px/700（手機 24–25px）；區段標題 19px/700，上方 2px 墨色粗線；卡片標題 17px/700；本文 15px/1.6；說明與註腳 12.5–13px。
- 分數：首頁與儀表板主分數 56px/700；分項分數 30px/700；比較列 22px/700。

### Named Rules
- **不用大寫小標籤**：沒有 kicker/eyebrow，英文因子名不放在標題上方。
- **新增中文字要重建子集**：頁面出現新字時跑 `python3 scripts/build_fonts.py <Regular.otf> <Bold.otf>`。

## Layout

- 內容欄最大寬 1120px；儀表板外殼 1400px，右側 290px 事件行事曆（sticky）。≤ 900px 事件欄移到內容下方，主圖工具列出現「事件行事曆 ↓」跳轉連結。
- 區塊用細線分隔，不用卡片；說明段落最寬 68ch。
- 導覽列：不吸頂、置中、最大寬度與頁面內容一致、四角圓角（作者明確要求）；≤ 780px 改兩行，品牌文字保留。

## Elevation & Depth

扁平。沒有卡片陰影、沒有 hover 上浮。唯一的陰影是浮動元素（資料來源下拉選單）。層次靠細線、surface-2 淡底與字重。

## Shapes

控制項 4px 圓角、事件欄 8px、導覽列 10px。按鈕是長方形，不用藥丸形；分頁籤與範圍鈕是共用外框的分段控制。

## Components

### Buttons
- 主要按鈕：accent 底、白字、4px 圓角、最小高 40px（表單）或 32px（工具列）。
- 次要按鈕：白底、1px border、深色字；hover 換 surface-2。
- 分段控制（1M–ALL、事件類別、登記簿篩選）：外框包住一排按鈕，作用中那格 accent 底白字。

### Inputs / Fields
白底、1px border、4px 圓角、最小高 36px；焦點用 2px accent 外框。

### Navigation
白底細框圓角列，目前頁面用 accent 文字加底部 2px 線標示。語言切換是文字按鈕「EN／繁中」。

### 回饋訊息
不用 `alert()`／`confirm()`／`prompt()`。提示用行內訊息（`.inline-msg`，錯誤時 danger 色），需要確認的動作用行內確認列（`.inline-confirm`，確認鈕取得焦點）。

### 儀表（signature）
半圓五段分級，段間留間隙、方頭；只有分數所在那一段上色，其餘為 gauge-inactive。指針細線加小圓心。下方四格比較列（前一交易日、一週前、一個月前、一年前）用細線格分隔。

### 事件行事曆
清單列，每列左側日期與類別、右側事件名；未發布的事件文字變淡並標「未發布」。主圖在範圍超過約一年時只在日期軸畫事件短刻度，一年內才畫整條垂直線。

## Do's and Don'ts

### Do:
- 新顏色先加進 `page_style.LIGHT` 與 `DARK`，再用 `var(--…)` 引用。
- matplotlib 圖表顏色用 `page_style.MPL`。
- 每個分數都配文字分級標籤。
- 圖表提供鍵盤操作（←→、PageUp/PageDown、＋−、Esc）與範圍按鈕，不只靠滾輪與拖曳。

### Don't:
- 不用 Inter、DM Sans、Space Grotesk、IBM Plex、Playfair、Fraunces 等 AI 慣用字體，也不把系統字體 stack 當設計。
- 不用紫靛色、漸層、發光、冷灰底加白卡、卡片陰影。
- 不用 kicker、emoji 圖示、藥丸按鈕、`border-left` 色條強調、每個區塊同樣的進場動畫。
- 不在頁面寫死 hex 或寫死因子數量。
