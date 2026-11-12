# -*- coding: utf-8 -*-
"""
三個對外頁面(首頁/儀表板/因子篩選平台，含各因子報告頁)共用的設計基準：字型、色彩、
間距與字級。各頁的選擇器名稱不用一致(DOM 結構本來就不同)，但同一個概念一律用這裡的
同一個值，不在各頁寫死 hex。

2026-11-12 視覺改版：路線是業界標準的金融資料工具(標竿 FRED、Koyfin、CNN Fear & Greed)。
白底、細線分區、不用卡片陰影；字型自架 Public Sans(美國聯邦網站設計系統 USWDS 的標準字，
數字等寬且齊高)＋Noto Sans TC 子集。設計紀錄見 DESIGN.md。

色彩規則：
- 台灣慣例：紅＝貪婪、綠＝恐懼。--tier-* 依「意義」命名，不依色相。
- 紅綠色盲看不出紅綠差異，兩端用明度拉開(淺色模式：極度恐懼最深、極度貪婪較亮；
  深色模式反過來)，而且每個分數旁邊都保留文字標籤。
- --tier-* 會直接當文字顏色用(分數、分級標籤)，所以每一級都要對底色有 4.5:1 以上的對比。
- 參考線(殖利率、均線、高低點)用 --series-*，不用 tier 色，因為它們本身不代表恐懼或貪婪。
"""

# ---------------------------------------------------------------- 間距與字級
CONTENT_MAX_WIDTH = "1120px"   # 內容欄寬度
BASE_LINE_HEIGHT = "1.6"       # 本文行高
H1_SIZE = "30px"               # 主標題字級
LEDE_MAX_WIDTH = "68ch"        # 說明段落可讀寬度(每行約 65–75 字元)

# ---------------------------------------------------------------- 字型
# 拉丁字與數字用 Public Sans，漢字落到 Noto Sans TC 子集(只含專案用到的字，
# 見 scripts/build_fonts.py)；子集沒收錄的字再落到系統黑體。
FONT_FAMILY = (
    '"Public Sans", "Noto Sans TC Subset", "PingFang TC", "Microsoft JhengHei", '
    '"Noto Sans TC", sans-serif'
)
FONT_MONO = 'ui-monospace, "SFMono-Regular", Menlo, Consolas, monospace'  # 只給程式代號用

_LATIN_RANGE = ("U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, "
                "U+2000-206F, U+2074, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD")
_CJK_RANGE = "U+2010-2027, U+2030-205E, U+3000-303F, U+4E00-9FFF, U+FF00-FFEF"

FONT_FACE_CSS = "".join(
    f'  @font-face {{ font-family: "Public Sans"; font-style: normal; font-weight: {w}; font-display: swap; '
    f'src: url("fonts/public-sans-latin-{w}.woff2") format("woff2"); unicode-range: {_LATIN_RANGE}; }}\n'
    for w in (400, 600, 700)
) + "".join(
    f'  @font-face {{ font-family: "Noto Sans TC Subset"; font-style: normal; font-weight: {w}; font-display: swap; '
    f'src: url("fonts/noto-sans-tc-subset-{w}.woff2") format("woff2"); unicode-range: {_CJK_RANGE}; }}\n'
    for w in (400, 700)
)

# ---------------------------------------------------------------- 色彩 token
# 淺色：白底、暖中性灰的線與次要文字；主色是資料站常見的深藍(FRED 系)。
LIGHT = {
    "page": "#ffffff",
    "surface-1": "#ffffff",
    "surface-2": "#f4f4f1",       # 表頭、輸入框、選取列的淡底
    "surface-3": "#e9eae6",       # 按下、hover
    "text-primary": "#1b1d1f",
    "text-secondary": "#45494d",
    "text-muted": "#62676c",
    "border": "#d5d7d2",          # 元件外框
    "rule": "#e3e4e0",            # 區塊分隔線
    "grid": "#ebece8",            # 圖表格線
    "axis": "#8c9195",
    "accent": "#1d5a96",          # 連結、目前頁、焦點、主要按鈕
    "accent-ink": "#ffffff",      # 主要按鈕上的字
    "series-1": "#1d5a96",        # 綜合分數線、各因子分數線
    "series-2": "#9c5a0c",        # 10 年期殖利率參考線
    "series-3": "#56606a",        # 原始資料圖的第二條參考線
    "series-4": "#2b3136",        # 自訂權重虛線
    "tier-extreme-fear": "#174f33",
    "tier-fear": "#3b7654",
    "tier-neutral": "#5c6166",
    "tier-greed": "#b9452f",
    "tier-extreme-greed": "#d1281c",
    "gauge-inactive": "#e6e7e3",
    "warn": "#8a5a00",            # 未發布、待確認之類的狀態字
    "danger": "#b42318",          # 錯誤訊息
    "selection": "#cfe0f2",
    "focus": "#1d5a96",
}
DARK = {
    "page": "#121416",
    "surface-1": "#171a1d",
    "surface-2": "#1d2124",
    "surface-3": "#262b2f",
    "text-primary": "#ecedea",
    "text-secondary": "#c0c4c7",
    "text-muted": "#969ca1",
    "border": "#353b40",
    "rule": "#2a2f33",
    "grid": "#23282c",
    "axis": "#6b7379",
    "accent": "#8db8e8",
    "accent-ink": "#0f1820",
    "series-1": "#8db8e8",
    "series-2": "#e3a35a",
    "series-3": "#a9b2ba",
    "series-4": "#e1e4e6",
    "tier-extreme-fear": "#a3dcb8",
    "tier-fear": "#6fb88d",
    "tier-neutral": "#a6acb0",
    "tier-greed": "#f19583",
    "tier-extreme-greed": "#ff5e4a",
    "gauge-inactive": "#272c30",
    "warn": "#e3b45a",
    "danger": "#ff8a7a",
    "selection": "#28456a",
    "focus": "#8db8e8",
}


def _decls(tokens):
    return " ".join(f"--{k}: {v};" for k, v in tokens.items())


# 深色模式跟著系統設定；:root[data-theme] 留給之後若加手動切換時覆寫用。
ROOT_TOKENS_CSS = f"""
  :root {{ color-scheme: light; {_decls(LIGHT)} }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{ color-scheme: dark; {_decls(DARK)} }}
  }}
  :root[data-theme="dark"] {{ color-scheme: dark; {_decls(DARK)} }}
"""

# 各頁共用的基礎規則：字型、選取文字、焦點框、捲軸、數字對齊、減少動態。
BASE_CSS = f"""
  html {{ -webkit-text-size-adjust: 100%; scrollbar-color: var(--border) transparent; }}
  body {{ font-family: {FONT_FAMILY}; font-variant-numeric: lining-nums tabular-nums;
    background: var(--page); color: var(--text-primary); }}
  ::selection {{ background: var(--selection); color: var(--text-primary); }}
  :focus-visible {{ outline: 2px solid var(--focus); outline-offset: 2px; }}
  a {{ color: var(--accent); }}
  .mono, code {{ font-family: {FONT_MONO}; font-size: 0.92em; }}
  @media (prefers-reduced-motion: reduce) {{
    *, *::before, *::after {{ transition: none !important; animation: none !important; scroll-behavior: auto !important; }}
  }}
"""

# 沿用舊名稱：dashboard_template.html、generate_hub.py 等以這個名字注入。
# 內容包含字型宣告、色彩 token 跟基礎規則。
ROOT_COLORS_CSS = FONT_FACE_CSS + ROOT_TOKENS_CSS + BASE_CSS

# ---------------------------------------------------------------- matplotlib 用的同一套顏色
# 報告頁的圖是 PNG，沒辦法跟著深色模式換色，所以只用淺色版本，圖底維持白色。
MPL = {
    "ink": LIGHT["text-primary"],
    "muted": LIGHT["text-muted"],
    "grid": LIGHT["grid"],
    "rule": LIGHT["rule"],
    "axis": LIGHT["axis"],
    "accent": LIGHT["accent"],
    "series": [LIGHT["series-1"], LIGHT["series-2"], LIGHT["series-3"], LIGHT["series-4"]],
    "fear": LIGHT["tier-extreme-fear"],
    "fear_light": LIGHT["tier-fear"],
    "neutral": LIGHT["tier-neutral"],
    "greed_light": LIGHT["tier-greed"],
    "greed": LIGHT["tier-extreme-greed"],
    "fear_deep": "#0d3622",     # 七色分桶圖兩端加深用
    "greed_deep": "#8f1a12",
    "danger": LIGHT["danger"],  # 樣本數不足之類的警示
    "white": "#ffffff",
}

# 分頁圖示。檔案是 chart/favicon.svg，產出頁面都在 chart/ 這層，用相對路徑即可。
FAVICON_TAG = '<link rel="icon" type="image/svg+xml" href="favicon.svg">'
