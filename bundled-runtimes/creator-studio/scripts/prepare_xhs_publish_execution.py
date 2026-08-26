#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from prepare_publish_execution import build_plan, read_json, write_json


def ensure_xhs_request(path: Path) -> dict[str, Any]:
    request = read_json(path)
    if request.get("platform") != "xiaohongshu":
        raise SystemExit("execution_request 不是小红书请求，拒绝使用小红书执行准备脚本。")
    return request


def main() -> None:
    parser = argparse.ArgumentParser(description="Compatibility wrapper for Xiaohongshu publish execution preparation.")
    parser.add_argument("--execution-request", required=True)
    parser.add_argument("--output", help="Optional path for xhs_execution_plan.json")
    args = parser.parse_args()

    execution_request = Path(args.execution_request).expanduser().resolve()
    ensure_xhs_request(execution_request)
    plan = build_plan(execution_request)
    if args.output:
        write_json(Path(args.output).expanduser().resolve(), plan)
    print(json.dumps(plan, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
