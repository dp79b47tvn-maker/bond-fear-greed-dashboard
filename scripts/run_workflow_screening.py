import argparse
import json
import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import factor_screening as fs


def parse_source(source_type, source_id):
    if source_type == "yahoo":
        return {"yahoo": source_id}
    elif source_type == "fred":
        return {"fred": source_id}
    else:
        return source_id


def main():
    parser = argparse.ArgumentParser(description="Run Factor Screening from GitHub Actions Workflow inputs")
    parser.add_argument("--key", type=str, default="")
    parser.add_argument("--label", type=str, default="")
    parser.add_argument("--mode", type=str, default="ma_deviation")
    parser.add_argument("--source-type", type=str, choices=["yahoo", "fred", "existing"], default="yahoo")
    parser.add_argument("--source-id", type=str, default="")
    parser.add_argument("--source-b-type", type=str, choices=["none", "yahoo", "fred", "existing"], default="none")
    parser.add_argument("--source-b-id", type=str, default="")
    parser.add_argument("--window", type=int, default=125)
    parser.add_argument("--stat", type=str, default="skew")
    parser.add_argument("--invert", action="store_true")
    parser.add_argument("--raw-json", type=str, default="")

    args = parser.parse_args()

    raw_json_str = args.raw_json.strip() if args.raw_json else ""
    if raw_json_str:
        print("檢測到自訂 raw_json 輸入，解析自訂 JSON...")
        cfg = json.loads(raw_json_str)
    else:
        if not args.key:
            raise ValueError("必須提供 --key 因子代號")

        cfg = {
            "key": args.key,
            "label": args.label or args.key,
            "mode": args.mode,
            "invert": args.invert,
            "params": {"window": args.window}
        }
        if args.mode == "rolling_stat":
            cfg["params"]["stat"] = args.stat

        mode_info = fs.TRANSFORM_MODES.get(args.mode)
        if not mode_info:
            raise ValueError(f"不合法的 mode: {args.mode}")

        if mode_info["n_sources"] == 1:
            if not args.source_id:
                raise ValueError("單資料來源模式必須指定 --source-id")
            cfg["sources"] = {"series": parse_source(args.source_type, args.source_id)}
        else:
            if not args.source_id or not args.source_b_id:
                raise ValueError("雙資料來源模式必須同時指定 --source-id 與 --source-b-id")
            cfg["sources"] = {
                "a": parse_source(args.source_type, args.source_id),
                "b": parse_source(args.source_b_type, args.source_b_id)
            }

    print("===== 因子篩選設定檔 (Candidate Config) =====")
    print(json.dumps(cfg, ensure_ascii=False, indent=2))
    print("============================================\n")

    fs.screen_and_save(cfg)


if __name__ == "__main__":
    main()
