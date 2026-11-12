"""子集化中文字型(Noto Sans TC)，輸出到 chart/fonts/。

公開頁面只自架字型、不載入外部字型服務。中文字型完整檔約 5.6MB，這裡只保留
專案原始檔裡實際出現的漢字與全形標點，外加常用字表(scripts/common_tc_chars.txt，
若存在)。頁面新增文字後若出現系統字型備援的字，重跑本腳本即可：

    python3 scripts/build_fonts.py <NotoSansTC-Regular.otf> <NotoSansTC-Bold.otf>

原始 OTF 不進 repo（從 https://github.com/notofonts/noto-cjk 的 Sans/SubsetOTF/TC 取得）。
"""
import os
import re
import sys
from fontTools import subset

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, "chart", "fonts")
SOURCES_EXT = (".py", ".html", ".json", ".md")
SKIP_DIRS = {".git", "venv", "node_modules", "fonts", ".impeccable", "tests"}
# 只收「中日韓」範圍：漢字、全形標點、注音不需要。拉丁字由 Public Sans 負責。
CJK = re.compile(r"[　-〿一-鿿＀-￯‐-‧‰-⁞]")


def collect_chars():
    chars = set()
    for root, dirs, files in os.walk(BASE):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            if not fn.endswith(SOURCES_EXT):
                continue
            try:
                with open(os.path.join(root, fn), encoding="utf-8") as f:
                    chars.update(CJK.findall(f.read()))
            except (UnicodeDecodeError, OSError):
                continue
    extra = os.path.join(BASE, "scripts", "common_tc_chars.txt")
    if os.path.exists(extra):
        with open(extra, encoding="utf-8") as f:
            chars.update(CJK.findall(f.read()))
    return chars


def main(regular, bold):
    chars = collect_chars()
    text = "".join(sorted(chars))
    os.makedirs(OUT, exist_ok=True)
    for src, name in ((regular, "noto-sans-tc-subset-400.woff2"), (bold, "noto-sans-tc-subset-700.woff2")):
        opts = subset.Options()
        opts.flavor = "woff2"
        opts.layout_features = ["ccmp", "locl", "fwid", "hwid"]
        opts.name_IDs = ["*"]
        opts.notdef_outline = True
        font = subset.load_font(src, opts)
        sub = subset.Subsetter(opts)
        sub.populate(text=text)
        sub.subset(font)
        out = os.path.join(OUT, name)
        subset.save_font(font, out, opts)
        print(f"{name}: {len(chars)} 字，{os.path.getsize(out) / 1024:.0f} KB")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
