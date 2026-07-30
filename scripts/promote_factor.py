"""
把因子篩選平台驗證過的候選因子「升等」為儀表板可選因子——寫進
promoted_candidate_factors.json(跟factor_definitions.json官方七因子唯一事實來源
刻意分開存放，不會污染到官方定義)。由GitHub Actions
(.github/workflows/promote-factor.yml)的workflow_dispatch觸發，也可以本機手動執行測試。

用法：
    python3 scripts/promote_factor.py --config-json '{"key":"...","label":"...","mode":"...","sources":{...},"params":{...},"invert":false}'
    python3 scripts/promote_factor.py --remove KEY
"""
import argparse
import json
import os
from datetime import date

PROMOTED_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "promoted_candidate_factors.json")
DEFAULT_README = (
    "因子篩選平台「升等為可選因子」寫入的暫存清單——跟factor_definitions.json"
    "(官方七因子唯一事實來源)刻意分開存放，不會污染到官方定義。這裡的因子只會："
    "1) 在儀表板多一張分項卡片（標示「候選因子」，不計入官方綜合分數）"
    "2) 在儀表板「自訂權重」區塊多一個可勾選的選項。"
    "每筆因子的格式(key/label/mode/sources/params/invert)跟factor_screening.py的候選因子設定檔一致。"
)


def main():
    parser = argparse.ArgumentParser(description="升等/退回因子篩選候選因子（儀表板可選因子）")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--config-json", type=str, help="升等：新增或覆蓋一筆候選因子設定")
    group.add_argument("--remove", type=str, metavar="KEY", help="退回：依key移除一筆已升等的候選因子")
    args = parser.parse_args()

    if os.path.exists(PROMOTED_PATH):
        with open(PROMOTED_PATH, encoding="utf-8") as f:
            staged = json.load(f)
    else:
        staged = {"_readme": DEFAULT_README, "factors": []}
    factors = staged.get("factors", [])

    if args.remove:
        existing_idx = next((i for i, f in enumerate(factors) if f.get("key") == args.remove), None)
        if existing_idx is None:
            print(f"因子代號 '{args.remove}' 不在目前的候選因子清單裡，無需移除")
            return
        removed = factors.pop(existing_idx)
        staged["factors"] = factors
        with open(PROMOTED_PATH, "w", encoding="utf-8") as f:
            json.dump(staged, f, ensure_ascii=False, indent=2)
        print(f"已將「{removed.get('label', args.remove)}」({args.remove}) 從 {PROMOTED_PATH} 移除")
        return

    config = json.loads(args.config_json)
    for required_key in ("key", "label", "mode", "sources"):
        if required_key not in config:
            raise ValueError(f"config缺少必要欄位：{required_key}")

    entry = {
        "key": config["key"],
        "label": config["label"],
        "mode": config["mode"],
        "sources": config["sources"],
        "params": config.get("params", {}),
        "invert": bool(config.get("invert", False)),
        "promoted_at": date.today().isoformat(),
    }

    existing_idx = next((i for i, f in enumerate(factors) if f.get("key") == entry["key"]), None)
    if existing_idx is not None:
        print(f"因子代號 '{entry['key']}' 已存在於暫存清單，用最新設定覆蓋")
        factors[existing_idx] = entry
    else:
        factors.append(entry)
    staged["factors"] = factors

    with open(PROMOTED_PATH, "w", encoding="utf-8") as f:
        json.dump(staged, f, ensure_ascii=False, indent=2)

    print(f"已將「{entry['label']}」({entry['key']}) 寫入 {PROMOTED_PATH}")


if __name__ == "__main__":
    main()
