"""
發布 chart/dashboard.html 之前的自動檢查——目的是攔下「JS語法錯誤導致整頁空白」
這一類的錯誤（2026-07-18發生過一次：說明文字裡誤用了markdown反引號，
剛好落在JS模板字串裡面，提前把字串截斷，導致整個<script>區塊直接語法錯誤，
整頁沒有任何一個功能能跑，卻沒有任何機制擋下來）。

檢查項目：
  1. 用 node --check 驗證抽出來的<script>內容語法正確（會抓到今天這種bug）。
  2. DATA / REGIME_META 這兩個注入的JSON區塊本身是合法JSON（不是語法正確但資料是空的）。
  3. HTML裡出現的關鍵id（gaugeSvg、mainChart、componentCards等）都存在，
     避免「JS引用了一個已經被刪掉的HTML元素」這類啞巴錯誤。

用法：
    python3 scripts/verify_dashboard.py
成功回傳 exit code 0，失敗印出具體原因並回傳非0，發布前應該先跑這個腳本。
"""
import json
import re
import subprocess
import sys
from pathlib import Path

DASHBOARD_PATH = Path(__file__).resolve().parent.parent / "chart" / "dashboard.html"

REQUIRED_IDS = [
    "gaugeSvg", "gaugeScore", "gaugeTag", "gaugeDate", "compareRow",
    "mainChart", "mainReadout", "timelineSlider", "dateJump", "jumpToday",
    "componentCards",
]


def fail(msg):
    print(f"✗ {msg}")
    return False


def main():
    ok = True
    html = DASHBOARD_PATH.read_text()

    # ---- 1. JS 語法檢查 ----
    m = re.search(r"<script>(.*)</script>", html, re.S)
    if not m:
        return fail("找不到 <script> 區塊，檔案可能沒有正確產生")
    script_path = Path("/tmp/_verify_dashboard_script.js")
    script_path.write_text(m.group(1))
    result = subprocess.run(["node", "--check", str(script_path)], capture_output=True, text=True)
    if result.returncode != 0:
        ok = fail(f"JS語法錯誤（node --check 沒過）：\n{result.stderr.strip()}")
    else:
        print("✓ JS語法檢查通過")

    # ---- 2. DATA / REGIME_META 是合法JSON ----
    for var_name in ["DATA", "REGIME_META"]:
        vm = re.search(rf"const {var_name} = (.*?);\n", html, re.S)
        if not vm:
            ok = fail(f"找不到 const {var_name} = ... 這一行")
            continue
        try:
            parsed = json.loads(vm.group(1))
        except json.JSONDecodeError as e:
            ok = fail(f"{var_name} 不是合法JSON：{e}")
            continue
        if var_name == "DATA":
            if not isinstance(parsed, list) or len(parsed) < 100:
                ok = fail(f"DATA 筆數異常少（{len(parsed) if isinstance(parsed, list) else 'N/A'}筆），可能資料沒注入成功")
            else:
                print(f"✓ DATA 是合法JSON，共{len(parsed)}筆")
        else:
            print(f"✓ {var_name} 是合法JSON（{'null' if parsed is None else '有內容'}）")

    # ---- 3. 關鍵HTML id都存在 ----
    missing = [i for i in REQUIRED_IDS if f'id="{i}"' not in html]
    if missing:
        ok = fail(f"HTML缺少關鍵id：{missing}")
    else:
        print(f"✓ 關鍵HTML id齊全（{len(REQUIRED_IDS)}個）")

    print()
    if ok:
        print("全部檢查通過，可以發布。")
    else:
        print("有檢查沒過，不建議發布——先修好上面列出的問題再重跑這支腳本。")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
