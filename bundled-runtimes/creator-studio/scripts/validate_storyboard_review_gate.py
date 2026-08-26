#!/usr/bin/env python3
"""Validate pre-render storyboard review decisions."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


APPROVED = "approved"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def scene_id(scene: dict[str, Any], index: int) -> str:
    return str(scene.get("scene_id") or scene.get("id") or f"scene_{index:03d}")


def scene_template(scene: dict[str, Any]) -> str:
    return str(scene.get("template_id") or scene.get("template") or scene.get("templateId") or "")


def validate(storyboard: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    scenes = storyboard.get("scenes") or storyboard.get("timeline") or []
    scene_map = {scene_id(scene, index): scene for index, scene in enumerate(scenes, 1)}
    decisions = decision.get("decisions") or []
    decision_map = {str(item.get("scene_id")): item for item in decisions}

    missing_decisions: list[str] = []
    blocking_decisions: list[dict[str, Any]] = []
    template_overrides: list[dict[str, str]] = []

    for scene_key, scene in scene_map.items():
        item = decision_map.get(scene_key)
        if not item:
            missing_decisions.append(scene_key)
            continue
        if item.get("decision") != APPROVED or item.get("approved") is not True:
            blocking_decisions.append(
                {
                    "scene_id": scene_key,
                    "decision": item.get("decision") or "pending",
                    "notes": item.get("notes") or "",
                }
            )
        override = str(item.get("template_override") or "").strip()
        original = scene_template(scene)
        if override and override != original:
            template_overrides.append({"scene_id": scene_key, "from": original, "to": override})

    extra_decisions = sorted(key for key in decision_map if key not in scene_map)
    status = "approved" if not missing_decisions and not blocking_decisions else "blocked"
    return {
        "schema_version": "dasheng.storyboard_review_gate_report.v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": status,
        "source_storyboard_status": storyboard.get("status"),
        "decision_status": decision.get("status"),
        "scene_count": len(scenes),
        "decision_count": len(decisions),
        "approved_count": sum(1 for item in decisions if item.get("decision") == APPROVED and item.get("approved") is True),
        "missing_decisions": missing_decisions,
        "blocking_decisions": blocking_decisions,
        "extra_decisions": extra_decisions,
        "template_overrides": template_overrides,
        "render_allowed": status == "approved",
        "next_step": "render_materials" if status == "approved" else "revise_storyboard_or_review_decisions",
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate storyboard review decision JSON before video material/render.")
    parser.add_argument("--storyboard", required=True)
    parser.add_argument("--decision", required=True)
    parser.add_argument("--output", default="")
    parser.add_argument("--no-fail", action="store_true", help="Return exit code 0 even when blocked.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    storyboard_path = Path(args.storyboard).expanduser().resolve()
    decision_path = Path(args.decision).expanduser().resolve()
    report = validate(load_json(storyboard_path), load_json(decision_path))
    report["paths"] = {"storyboard": str(storyboard_path), "decision": str(decision_path)}
    if args.output:
        output = Path(args.output).expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["status"] != "approved" and not args.no_fail:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
