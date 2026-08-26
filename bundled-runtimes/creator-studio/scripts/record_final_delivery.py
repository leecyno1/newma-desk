#!/usr/bin/env python3
"""记录终稿交付：AI 终稿回写完成后翻转 transwrite_manifest 的 lane 状态。

背景（0818 E2E 台账 F8）：script_rewrite 产出 transwrite_manifest 后，
lane status 停在 ready_for_agent_execution；AI 终稿（wechat_article.final.md 等）
回写磁盘后没有工具翻转状态，导致 build_stage5_publish 被
lane_status_not_publish_ready 阻塞，此前只能人工改 JSON。

用法：
    python3 scripts/record_final_delivery.py --run-id creator-xxx [--topic T01] [--lane wechat_article]
    python3 scripts/record_final_delivery.py --transwrite-manifest <path> ...
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from canonical_workflow import canonical_stage_dir  # noqa: E402

PUBLISH_READY_LANES = {"completed", "packageable", "ready_base_package"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> None:
    parser = argparse.ArgumentParser(description="记录终稿交付并翻转 lane 状态为 completed")
    parser.add_argument("--transwrite-manifest", help="transwrite_manifest.json 路径（默认按 run_id 走 canonical 路径）")
    parser.add_argument("--run-id", help="run_id（未指定 --transwrite-manifest 时必需）")
    parser.add_argument("--topic", help="topic_id（默认全部 topic）")
    parser.add_argument("--lane", help="lane 名（默认全部非 completed lane）")
    args = parser.parse_args()

    if args.transwrite_manifest:
        manifest_path = Path(args.transwrite_manifest).expanduser().resolve()
    elif args.run_id:
        manifest_path = canonical_stage_dir("transwrite", args.run_id) / "transwrite_manifest.json"
    else:
        parser.error("需要 --run-id 或 --transwrite-manifest")

    if not manifest_path.is_file():
        raise SystemExit(f"缺少 transwrite_manifest.json：{manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    results: list[dict] = []
    changed = False
    for topic in manifest.get("topics", []):
        if args.topic and topic.get("topic_id") != args.topic:
            continue
        for lane_id, lane in (topic.get("lanes") or {}).items():
            if args.lane and lane_id != args.lane:
                continue
            status = str(lane.get("status") or "")
            if status in PUBLISH_READY_LANES:
                results.append({"topic": topic.get("topic_id"), "lane": lane_id, "status": status, "action": "already_ready"})
                continue
            missing = [
                key
                for key in ("final_markdown", "final_html")
                if not Path(str(lane.get(key) or "")).expanduser().is_file()
            ]
            if missing:
                results.append({"topic": topic.get("topic_id"), "lane": lane_id, "status": status, "action": "blocked", "missing": missing})
                continue
            lane["status"] = "completed"
            lane["completed_at"] = now_iso()
            changed = True
            results.append({"topic": topic.get("topic_id"), "lane": lane_id, "status": "completed", "action": "flipped"})

    if changed:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    payload = {
        "status": "succeeded" if all(r.get("action") != "blocked" for r in results) else "blocked",
        "manifest": str(manifest_path),
        "changed": changed,
        "lanes": results,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if payload["status"] != "succeeded":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
