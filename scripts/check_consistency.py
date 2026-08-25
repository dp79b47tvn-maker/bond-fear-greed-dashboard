#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
專案一致性自我檢查——在「上線之前」抓出因子清單／資料管線互相脫鉤的問題。

【為什麼需要這支】
這個專案的因子定義散在好幾個地方：factor_definitions.json(唯一事實來源)、
update_dashboard.compute_scores()、兩支各自獨立的資料抓取函式、儀表板模板裡手刻的
JS 陣列、還有一堆說明文案。2026-08-11 官方因子從七項改成兩項時，一連串東西沒同步：

  - factor_validation_analysis.fetch_extended_history() 沒補抓 HG=F/GC=F
    → 整個因子篩選平台 KeyError: 'HG_futures'，跑不動
  - factor_validation_analysis.FACTOR_COLS 還寫著七個舊 score 欄位
    → 第四關「跟現有因子的相關係數」拿不存在的因子當基準
  - factor_screening._corr_factor_options() 只剩兩個選項
    → 相關係數矩陣功能實質報廢
  - 各頁面文案還寫著「七項」

以上每一項都是靜態就能檢查出來的，但當時沒有任何測試會失敗，全都是上線後才發現。
這支腳本把那些檢查補起來，接進 CI(update-and-deploy.yml)在部署前擋下來。

用法：
    python3 scripts/check_consistency.py          # 全部檢查，有問題回傳非0
    python3 scripts/check_consistency.py --list    # 只列出目前的因子/欄位盤點

不做網路請求、不改任何檔案，純靜態分析，一秒內跑完。
"""
import argparse
import ast
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from factor_defs_schema import FactorDefinitionsError, validate_and_load  # noqa: E402

DEFS_PATH = os.path.join(ROOT, "factor_definitions.json")
UPDATE_DASHBOARD = os.path.join(ROOT, "update_dashboard.py")
FVA = os.path.join(ROOT, "factor_validation_analysis.py")
TEMPLATE = os.path.join(ROOT, "chart", "dashboard_template.html")

failures = []
notes = []


def fail(check, msg):
    failures.append((check, msg))


def note(msg):
    notes.append(msg)


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _func_source(src, name):
    """從原始碼裡取出某個 top-level 函式的原始碼字串（用 AST 定位，不用脆弱的正則）。"""
    tree = ast.parse(src)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node) or ""
    return ""


def _df_columns(func_src):
    """回傳 (讀取的欄位, 寫入的欄位)。寫入＝出現在 df["x"] = 左側的。"""
    written = set(re.findall(r'df\[[\'"]([A-Za-z_0-9]+)[\'"]\]\s*=', func_src))
    allrefs = set(re.findall(r'df\[[\'"]([A-Za-z_0-9]+)[\'"]\]', func_src))
    return allrefs - written, written


def _fetched_columns(func_src):
    """一支函式裡「自己直接發網路請求抓資料」的欄位。

    只認 *fetch_yahoo*("TICKER", "COL") / *fetch_fred*("ID", "COL") 這類呼叫
    （寬鬆前後綴比對，因為有的地方會包一層 wrapper），外加固定回傳兩欄的
    fetch_treasury_yield_curve()。

    刻意不把 df["COL"] = ... 算進來——那可能只是型別轉換或補 NA 佔位
    （例如 put_call_ratio 的 to_numeric 轉換），不是抓資料。這個函式的用途是
    偵測「有沒有人繞過 factor_definitions.json 自己手列 ticker」，不是盤點欄位。
    """
    pat = r'\w*fetch_(?:yahoo|fred)\w*\(\s*[\'"][^\'"]+[\'"]\s*,\s*[\'"]([A-Za-z_0-9]+)[\'"]'
    cols = set(re.findall(pat, func_src))
    if "fetch_treasury_yield_curve()" in func_src:
        cols |= {"UST_10Yr", "UST_2Yr"}
    return cols


# ================================================================ 檢查項目
def check_scores_match_definitions(defs, ud_src):
    """factor_definitions.json 宣告的每個 score_col，compute_scores() 都要真的產出；
    反過來 compute_scores() 也不該產出 JSON 沒宣告的分數欄位(會變成孤兒欄位)。"""
    declared = {f["score_col"] for f in defs["factors"]}
    cs = _func_source(ud_src, "compute_scores")
    _, written = _df_columns(cs)
    produced = {c for c in written if c.endswith("_score")}

    missing = declared - produced
    if missing:
        fail("分數欄位", f"factor_definitions.json 宣告了 {sorted(missing)}，"
                        f"但 update_dashboard.compute_scores() 沒有產出——儀表板會拿到空白分數")
    # composite_score 是所有因子的等權重平均(規則在 global.composite_method)，
    # 本身不是一個因子、不該出現在 factors 陣列裡，所以不算孤兒欄位。
    orphan = produced - declared - {"composite_score"}
    if orphan:
        fail("分數欄位", f"compute_scores() 產出 {sorted(orphan)}，"
                        f"但 factor_definitions.json 沒宣告——不會有卡片、也不會進綜合分數")

    # SCORE_COLS 常數也要一致
    m = re.search(r'^SCORE_COLS\s*=\s*(\[[^\]]*\])', ud_src, re.M)
    if m:
        try:
            score_cols = set(ast.literal_eval(m.group(1)))
            if score_cols != declared:
                fail("分數欄位", f"update_dashboard.SCORE_COLS={sorted(score_cols)} 跟 "
                                f"factor_definitions.json 的 {sorted(declared)} 不一致——綜合分數會算錯")
        except (ValueError, SyntaxError):
            note("SCORE_COLS 不是字面值清單，略過比對")
    note(f"官方因子 {len(declared)} 項：{sorted(declared)}")


def check_both_fetchers_cover_inputs(defs, ud_src, fva_src):
    """【今天出包的那個】compute_scores() 需要的每個輸入欄位，都必須有人負責抓回來。

    2026-08-11 之後兩條路徑改成共用 ud.fetch_declared_sources()、由
    factor_definitions.json 的 data_sources 決定抓什麼，所以這裡檢查兩件事：
      1. data_sources 有涵蓋 compute_scores() 需要的所有欄位
      2. 兩支抓取函式都還在走共用那條路（沒有人偷偷改回自己手列 ticker）
    """
    cs = _func_source(ud_src, "compute_scores")
    needed, _ = _df_columns(cs)

    declared = {s["column"] for s in defs["data_sources"]}
    miss = needed - declared
    if miss:
        fail("資料管線", f"compute_scores() 需要 {sorted(miss)}，但 factor_definitions.json "
                        f"的 data_sources 沒宣告——沒人會去抓，執行時直接 KeyError")

    valid_kinds = {"yahoo", "fred", "treasury"}
    for s in defs["data_sources"]:
        if s.get("fetch") not in valid_kinds:
            fail("資料管線", f"data_sources「{s['column']}」的 fetch={s.get('fetch')!r} 不合法"
                            f"（可用值：{sorted(valid_kinds)}）——fetch_declared_sources() 會拋錯")

    for name, src, fn in (("update_dashboard.fetch_all_raw_data()", ud_src, "fetch_all_raw_data"),
                          ("factor_validation_analysis.fetch_extended_history()", fva_src,
                           "fetch_extended_history")):
        body = _func_source(src, fn)
        if "fetch_declared_sources" not in body:
            fail("資料管線", f"{name} 沒有呼叫共用的 fetch_declared_sources()，"
                            f"看起來又改回自己手列 ticker 了——兩條路徑遲早會脫鉤，"
                            f"這正是 2026-08-11 讓篩選平台整個掛掉的原因")
        stray = _fetched_columns(body)
        if stray:
            fail("資料管線", f"{name} 裡還有自己直接抓的欄位 {sorted(stray)}——"
                            f"請改成在 factor_definitions.json 的 data_sources 宣告")

    note(f"compute_scores() 需要的輸入欄位：{sorted(needed)}")
    note(f"data_sources 宣告 {len(declared)} 個資料欄，兩條路徑共用同一份")


def check_definitions_inputs_declared(defs, ud_src):
    """factor_definitions.json 每個因子宣告的 inputs，要跟 compute_scores() 實際讀的一致，
    而且都要出現在 data_sources 裡(那是給使用者看的資料來源表)。"""
    cs = _func_source(ud_src, "compute_scores")
    needed, _ = _df_columns(cs)
    declared_inputs = {i for f in defs["factors"] for i in f["inputs"] if "(" not in i}

    if declared_inputs != needed:
        only_json = declared_inputs - needed
        only_code = needed - declared_inputs
        detail = []
        if only_json:
            detail.append(f"JSON 宣告但程式沒用：{sorted(only_json)}")
        if only_code:
            detail.append(f"程式有用但 JSON 沒宣告：{sorted(only_code)}")
        fail("因子 inputs", "；".join(detail))

    ds_cols = {s["column"] for s in defs["data_sources"]}
    undocumented = needed - ds_cols
    if undocumented:
        fail("資料來源表", f"{sorted(undocumented)} 有被 compute_scores() 用到，"
                          f"但沒列在 factor_definitions.json 的 data_sources——頁面上的資料來源表會漏掉")


def check_factor_cols_derived(fva_src):
    """fva.FACTOR_COLS 必須從 factor_definitions.json 衍生，不可以手寫死。
    寫死過一次(七項)，因子改成兩項時沒同步，第四關就拿了不存在的因子當比較基準。"""
    m = re.search(r'^FACTOR_COLS\s*=\s*\{(.*?)^\}', fva_src, re.M | re.S)
    if not m:
        note("找不到 FACTOR_COLS 定義，略過")
        return
    body = m.group(1)
    if "DEFS" not in body and "for f in" not in body:
        fail("因子清單", "factor_validation_analysis.FACTOR_COLS 是手寫死的字典，"
                        "必須改成從 factor_definitions.json 衍生，否則改因子時一定會脫鉤")


def check_dashboard_template(defs, template_src):
    """儀表板模板裡兩個手刻的 JS 陣列(COMPONENTS / CUSTOM_WEIGHT_FACTORS)，
    key 集合必須跟 factor_definitions.json 完全一致。"""
    declared = {f["key"] for f in defs["factors"]}

    # 只抓最外層物件的 key（4個空白縮排）——rawChart.series 裡面也有 key: 欄位，
    # 那是原始資料欄名不是因子key，縮排比較深，不能一起抓進來。
    top_level_key = r'^    key:\s*"([A-Za-z_0-9]+)"'

    m = re.search(r'const COMPONENTS = \[(.*?)^\];', template_src, re.M | re.S)
    if m:
        keys = set(re.findall(top_level_key, m.group(1), re.M))
        if keys != declared:
            fail("儀表板模板", f"COMPONENTS 的 key {sorted(keys)} 跟 factor_definitions.json "
                              f"的 {sorted(declared)} 不一致——會多出/少掉分項卡片")
    else:
        note("找不到 COMPONENTS 陣列，略過")

    m = re.search(r'const CUSTOM_WEIGHT_FACTORS = \[(.*?)^\];', template_src, re.M | re.S)
    if m:
        keys = set(re.findall(r'key:\s*"([A-Za-z_0-9]+)"', m.group(1)))
        if keys != declared:  # 這個陣列是扁平的，不用限縮排
            fail("儀表板模板", f"CUSTOM_WEIGHT_FACTORS 的 key {sorted(keys)} 跟 "
                              f"factor_definitions.json 的 {sorted(declared)} 不一致——自訂權重清單會對不上")
    else:
        note("找不到 CUSTOM_WEIGHT_FACTORS 陣列，略過")


COUNT_WORDS = {2: "兩", 3: "三", 4: "四", 5: "五", 6: "六", 7: "七", 8: "八", 9: "九", 10: "十"}


def check_stale_count_prose(defs):
    """頁面文案裡「七項因子」「七因子」這種寫死的數量字眼，改因子數之後會變成錯的。
    只檢查對外頁面會用到的檔案，不檢查註解/docstring(那些講的是歷史沿革，是對的)。"""
    n = len(defs["factors"])
    correct = COUNT_WORDS.get(n, str(n))
    wrong = [w for k, w in COUNT_WORDS.items() if k != n]
    pattern = re.compile(r"(" + "|".join(wrong) + r")(項因子|因子|項分數|個分項|項等權重)")

    targets = [
        os.path.join(ROOT, "chart", "dashboard_template.html"),
        os.path.join(ROOT, "generate_hub.py"),
        os.path.join(ROOT, "factor_definitions.json"),
    ]
    # 明確標示是在講歷史的字眼——「舊版七項分數」是正確的歷史描述，不是過期文案
    historical_marker = re.compile(r"(舊版|原本|先前|以前|過去|曾經|之前|歷史|2026-\d\d-\d\d)")

    for path in targets:
        if not os.path.exists(path):
            continue
        rel = os.path.relpath(path, ROOT)
        for i, line in enumerate(_read(path).splitlines(), 1):
            stripped = line.strip()
            # 跳過純註解行(講歷史沿革的說明不算過期文案)
            if stripped.startswith(("#", "//", "*", "<!--")):
                continue
            hit = pattern.search(line)
            if not hit:
                continue
            # 命中處往前看 12 個字，有歷史字眼就當成正確的歷史描述
            before = line[max(0, hit.start() - 12):hit.start()]
            if historical_marker.search(before):
                continue
            fail("過期文案", f"{rel}:{i} 出現「{hit.group(0)}」，但目前是 {n} 項因子"
                            f"（應為「{correct}{hit.group(2)}」）")


def check_registry_not_overwritten():
    """登記簿是 append-only 的歷史紀錄。任何腳本用 'w' 模式寫它之前，
    都必須先把既有內容讀進來合併——直接覆寫會把別人的歷史整批清掉(2026-08-04 發生過)。"""
    for dirpath, _, filenames in os.walk(os.path.join(ROOT, "scripts")):
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(dirpath, fn)
            src = _read(path)
            if "factor_screening_registry.json" not in src:
                continue
            writes = re.search(r'open\(\s*[^)]*factor_screening_registry\.json[^)]*,\s*["\']w["\']', src)
            if writes and not re.search(r"_load_registry\(\)|json\.load", src):
                fail("登記簿", f"scripts/{fn} 用 'w' 覆寫 factor_screening_registry.json "
                              f"但沒有先讀取合併——會清掉所有歷史測試紀錄")


def check_no_orphan_modules():
    """沒有任何人 import、CI 也不跑的模組＝孤兒檔，容易腐爛成壞掉的程式碼。

    判定時「自己的檔案內容不算數」——不然每個模組都會因為自己 import 別人而被誤判成
    有人用。另外只有被『還活著的』模組 import 才算數：一堆孤兒檔互相 import 的話，
    整團都是死的，不能因為彼此有引用就當成活的。
    """
    sources = {}
    for d in (ROOT, os.path.join(ROOT, "scripts"), os.path.join(ROOT, ".github", "workflows")):
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            if fn.endswith((".py", ".yml")):
                rel = os.path.relpath(os.path.join(d, fn), ROOT)
                sources[rel] = _read(os.path.join(d, fn))

    root_mods = [f for f in os.listdir(ROOT) if f.endswith(".py")]

    def referenced_by(mod, pool):
        """mod 有沒有被 pool 這些檔案(排除 mod 自己)真的 import。

        只認 import 敘述，不認註解裡提到的「見 xxx.py」——那種只是文件交叉引用，
        不代表程式真的會走到那支模組(不然一堆死檔會因為被註解提到而被誤判成活的)。
        """
        pat = re.compile(rf"^\s*(?:import\s+{re.escape(mod)}\b|from\s+{re.escape(mod)}\s+import)", re.M)
        return any(pat.search(src) for rel, src in sources.items()
                   if rel in pool and os.path.basename(rel) != f"{mod}.py")

    # 種子＝CI 直接執行的檔案，從那裡沿著 import 關係做可達性分析
    ci_src = "".join(s for rel, s in sources.items() if rel.startswith(".github"))
    alive = {rel for rel in sources
             if not rel.startswith(".github") and os.path.basename(rel) in ci_src}
    changed = True
    while changed:  # 反覆擴散直到收斂
        changed = False
        for rel in sources:
            if rel in alive or rel.startswith(".github") or not rel.endswith(".py"):
                continue
            if referenced_by(os.path.basename(rel)[:-3], alive):
                alive.add(rel)
                changed = True

    orphans = sorted(f for f in root_mods if f not in alive)
    if orphans:
        fail("孤兒模組", f"以下模組從 CI 進入點完全走不到：{orphans}——"
                        f"建議刪除(git 有歷史可還原)，留著容易腐爛成壞掉的程式碼")
    note(f"從 CI 進入點可達的模組 {len(alive)} 支")


def check_main_guard():
    """import 就直接執行的模組很危險：可能意外發網路請求、印一堆東西、甚至覆寫檔案。"""
    bad = []
    for f in sorted(os.listdir(ROOT)):
        if not f.endswith(".py"):
            continue
        src = _read(os.path.join(ROOT, f))
        try:
            tree = ast.parse(src)
        except SyntaxError:
            fail("語法", f"{f} 無法解析")
            continue
        has_guard = "__main__" in src
        # 只算「呼叫本檔自己定義的函式」——那才是該被 __main__ 包起來的執行邏輯。
        # 頂層呼叫函式庫(matplotlib.use("Agg")、warnings.filterwarnings(...)、
        # pd.set_option(...))是模組設定，import時執行本來就是對的，不該被判為問題。
        local_fns = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}

        def _calls_local(node):
            fn = node.value.func
            name = fn.id if isinstance(fn, ast.Name) else None
            return name in local_fns

        auto = any(isinstance(n, ast.Expr) and isinstance(n.value, ast.Call) and _calls_local(n)
                   for n in tree.body)
        if auto and not has_guard:
            bad.append(f)
    if bad:
        fail("__main__ 保護", f"以下模組 import 時就會直接執行：{bad}——"
                             f"請把執行邏輯包進 if __name__ == \"__main__\":")


def main():
    parser = argparse.ArgumentParser(description="專案一致性自我檢查（純靜態，不發網路請求）")
    parser.add_argument("--list", action="store_true", help="只列出盤點結果，不判定成敗")
    args = parser.parse_args()

    # 格式檢查放第一步：檔案本身結構就有問題的話，應該第一個講清楚，
    # 不要拖到後面的AST掃描裡因為缺欄位而報一個看不懂的錯誤。
    try:
        defs = validate_and_load(DEFS_PATH)
    except FactorDefinitionsError as e:
        fail("factor_definitions.json 格式", str(e))
        print("=" * 72)
        print("專案一致性檢查")
        print("=" * 72)
        print(f"\n✗ 發現 {len(failures)} 個問題：\n")
        for check, msg in failures:
            print(f"  [{check}] {msg}\n")
        return 1

    ud_src = _read(UPDATE_DASHBOARD)
    fva_src = _read(FVA)
    template_src = _read(TEMPLATE) if os.path.exists(TEMPLATE) else ""

    check_scores_match_definitions(defs, ud_src)
    check_both_fetchers_cover_inputs(defs, ud_src, fva_src)
    check_definitions_inputs_declared(defs, ud_src)
    check_factor_cols_derived(fva_src)
    if template_src:
        check_dashboard_template(defs, template_src)
    check_stale_count_prose(defs)
    check_registry_not_overwritten()
    check_no_orphan_modules()
    check_main_guard()

    print("=" * 72)
    print("專案一致性檢查")
    print("=" * 72)
    for n in notes:
        print(f"  · {n}")

    if args.list:
        print("\n(--list 模式，不判定成敗)")
        return 0

    if failures:
        print(f"\n✗ 發現 {len(failures)} 個問題：\n")
        for check, msg in failures:
            print(f"  [{check}] {msg}\n")
        return 1

    print("\n✓ 全部通過")
    return 0


if __name__ == "__main__":
    sys.exit(main())
