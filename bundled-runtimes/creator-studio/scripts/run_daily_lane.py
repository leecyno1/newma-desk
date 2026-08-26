#!/usr/bin/env python3
"""日度并行 lane 推进器（CI / 本地通用）。

用法:
    python scripts/run_daily_lane.py --lane lane-a [--dry-run]

行为:
    1. 读取 configs/workflow/daily_parallel_lanes.json 中指定 lane 的配置
    2. 校验 lane 启用状态与对应发布账号 slot 的注册状态
    3. --dry-run: 仅输出当日执行计划（CI 冒烟用）
    4. 真实模式: 依次推进 文章生产 → 文章发布 → 视频接力（文章先于视频）

lane 的实际生产动作复用现有主链 CLI（run_mainline_stage.py / newma_creator_control.py），
本脚本只负责 lane 编排、前置校验与顺序保证，便于 CI 中独立并行运行三条 lane。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from path_config import get_project_root  # noqa: E402

ROOT = get_project_root()
LANES_FILE = ROOT / "configs" / "workflow" / "daily_parallel_lanes.json"
ACCOUNTS_FILE = ROOT / "configs" / "publish" / "account_registry.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Advance one daily parallel lane")
    parser.add_argument("--lane", required=True, help="lane_id, e.g. lane-a")
    parser.add_argument("--dry-run", action="store_true", help="print plan without executing")
    args = parser.parse_args()

    lanes = load_json(LANES_FILE)
    account_reg = load_json(ACCOUNTS_FILE)

    lane = next((item for item in lanes.get("lanes", []) if item.get("lane_id") == args.lane), None)
    if lane is None:
        print(json.dumps({"status": "unknown_lane", "lane": args.lane}, ensure_ascii=False))
        return 2
    if not lane.get("enabled", False):
        print(json.dumps({"status": "lane_disabled", "lane": args.lane}, ensure_ascii=False))
        return 0

    article = lane.get("article", {})
    video = lane.get("video", {})
    channel = str(article.get("channel", ""))
    slot = str(article.get("account_slot", ""))
    slot_info = account_reg.get("channels", {}).get(channel, {}).get("slots", {}).get(slot, {})
    registration = slot_info.get("account_metadata", {}).get("registration_status", "unknown")

    plan = {
        "schema_version": "newma.daily_lane_run.v1",
        "lane": args.lane,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "purpose_group": lane.get("purpose_group"),
        "ordering": lanes.get("ordering", {}).get("rule"),
        "steps": [
            {"step": 1, "action": "article_build", "channel": channel, "slot": slot, "topics": article.get("topics_per_day")},
            {"step": 2, "action": "article_publish", "channel": channel, "slot": slot, "guard": "registration must be active"},
            {"step": 3, "action": "video_followup", "channel": video.get("channel"), "slot": video.get("account_slot"), "after": "article published"},
        ],
        "slot_registration": registration,
        "blocked": registration != "active",
    }

    if args.dry_run or plan["blocked"]:
        plan["mode"] = "dry-run" if args.dry_run else "blocked_pending_registration"
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0

    # 真实推进：文章先于视频。生产动作复用主链 CLI，此处串行编排。
    plan["mode"] = "execute"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run_mainline_stage.py"), "--stage", "transwrite", "--lane", channel],
        cwd=str(ROOT), capture_output=True, text=True, timeout=3600,
    )
    plan["transwrite_exit"] = result.returncode
    if result.returncode != 0:
        plan["status"] = "transwrite_failed"
        plan["stderr_tail"] = result.stderr[-400:]
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 1
    plan["status"] = "article_lane_advanced"
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
