#!/usr/bin/env python3
"""Validate that a renderer actually implements the director scene contract."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any


REQUIRED_CONSUMED_FIELDS = {
    "template_id",
    "speaker_state",
    "material_state",
    "pip_shape",
    "transition_in",
    "transition_out",
    "html_animation_behavior",
    "audio",
}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def implementation_signature(item: dict[str, Any]) -> tuple[str, str, str]:
    return (
        str(item.get("component") or ""),
        str(item.get("variant") or ""),
        str(item.get("motion_signature") or ""),
    )


def audit_renderer_contract(scene_plan: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    scenes = scene_plan.get("scenes") or scene_plan.get("segments") or []
    templates = contract.get("templates") or {}
    consumed_fields = {str(item) for item in contract.get("consumed_scene_fields") or []}
    failures: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    missing_fields = sorted(REQUIRED_CONSUMED_FIELDS - consumed_fields)
    if missing_fields:
        failures.append(
            {
                "code": "director_fields_not_consumed",
                "message": "渲染器没有声明消费完整导演字段，分镜策略可能在渲染阶段丢失。",
                "missing_fields": missing_fields,
            }
        )

    used_template_ids = sorted({str(scene.get("template_id") or "") for scene in scenes if scene.get("template_id")})
    missing_templates = [
        template_id
        for template_id in used_template_ids
        if template_id not in templates or str((templates.get(template_id) or {}).get("status")) != "implemented"
    ]
    if missing_templates:
        failures.append(
            {
                "code": "template_renderer_missing",
                "message": "分镜引用了没有生产级渲染实现的模板。",
                "template_ids": missing_templates,
            }
        )

    implemented = [templates[template_id] for template_id in used_template_ids if template_id in templates]
    signatures = {implementation_signature(item) for item in implemented if implementation_signature(item) != ("", "", "")}
    if len(used_template_ids) >= 3:
        minimum_signatures = max(2, math.ceil(len(used_template_ids) * 0.5))
        if len(signatures) < minimum_signatures:
            failures.append(
                {
                    "code": "template_alias_collapse",
                    "message": "多个模板名坍缩成少量相同组件/变体/动效签名，属于假模板多样性。",
                    "template_count": len(used_template_ids),
                    "implementation_signature_count": len(signatures),
                    "minimum_signature_count": minimum_signatures,
                }
            )

    return {
        "schema_version": "dasheng.video.renderer_contract_gate.v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": "pass" if not failures else "fail",
        "metrics": {
            "scene_count": len(scenes),
            "used_template_count": len(used_template_ids),
            "implemented_template_count": len(used_template_ids) - len(missing_templates),
            "implementation_signature_count": len(signatures),
            "consumed_scene_field_count": len(consumed_fields),
        },
        "failures": failures,
        "warnings": warnings,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate scene-plan templates against a concrete renderer contract.")
    parser.add_argument("--scene-plan", required=True)
    parser.add_argument("--renderer-contract", required=True)
    parser.add_argument("--output", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = audit_renderer_contract(
        read_json(Path(args.scene_plan).expanduser().resolve()),
        read_json(Path(args.renderer_contract).expanduser().resolve()),
    )
    if args.output:
        write_json(Path(args.output).expanduser().resolve(), report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
