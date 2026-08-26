#!/usr/bin/env python3
"""Govern Newma video pipelines with manifests, artifact schemas, and review gates."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from video_tool_registry import DEFAULT_REGISTRY_PATH, load_tool_registry, tool_index, unresolved_project_paths, unresolved_script_paths, unresolved_skill_paths


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PIPELINE_DIR = PROJECT_ROOT / "configs" / "video" / "pipelines"
SCHEMA_DIR = PROJECT_ROOT / "configs" / "video" / "artifact_schemas"
LOCAL_SKILLS_DIR = PROJECT_ROOT / "skills"
DIRECTOR_REGISTRY_PATH = PROJECT_ROOT / "configs" / "video" / "director_registry.json"
PRODUCTION_LANES = {
    "talking_head_video",
    "explainer_html_video",
    "vox_explainer_video",
    "digital_human_video",
    "commercial_promo_video",
    "cinematic_short_drama_video",
}
VALID_LANES = {*PRODUCTION_LANES, "style_training"}

ARTIFACT_SCHEMAS = {
    "brief": "brief.schema.json",
    "script": "script.schema.json",
    "scene_plan": "scene_plan.schema.json",
    "presenter_source_manifest": "presenter_source_manifest.schema.json",
    "digital_human_job": "digital_human_job.schema.json",
    "visual_bible": "visual_bible.schema.json",
    "image2_shot_manifest": "image2_shot_manifest.schema.json",
    "omni_shot_manifest": "omni_shot_manifest.schema.json",
    "tool_routing_plan": "tool_routing_plan.schema.json",
    "claim_evidence_ledger": "claim_evidence_ledger.schema.json",
    "spoken_revision_sheet": "spoken_revision_sheet.schema.json",
    "asset_manifest": "asset_manifest.schema.json",
    "renderer_asset_gate": "renderer_asset_gate.schema.json",
    "edit_decisions": "edit_decisions.schema.json",
    "render_report": "render_report.schema.json",
    "review": "review.schema.json",
}


def load_pipeline(path_or_id: str | Path) -> dict[str, Any]:
    candidate = Path(path_or_id)
    if not candidate.exists():
        candidate = PIPELINE_DIR / f"{path_or_id}.yaml"
    return yaml.safe_load(candidate.read_text(encoding="utf-8"))


def load_artifact_schema(artifact_type: str) -> dict[str, Any]:
    schema_name = ARTIFACT_SCHEMAS.get(artifact_type)
    if not schema_name:
        raise KeyError(f"Unknown artifact type: {artifact_type}")
    return json.loads((SCHEMA_DIR / schema_name).read_text(encoding="utf-8"))


def load_director_registry(path: Path = DIRECTOR_REGISTRY_PATH) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_artifact(artifact_type: str, artifact: dict[str, Any]) -> list[dict[str, str]]:
    schema = load_artifact_schema(artifact_type)
    validator = jsonschema.Draft202012Validator(schema)
    errors: list[dict[str, str]] = []
    for error in sorted(validator.iter_errors(artifact), key=lambda item: list(item.path)):
        errors.append(
            {
                "code": "schema_invalid",
                "path": ".".join(str(part) for part in error.path),
                "message": error.message,
            }
        )
    return errors


def validate_artifact_file(artifact_type: str, path: Path) -> dict[str, Any]:
    artifact = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_artifact(artifact_type, artifact)
    return {
        "artifact_type": artifact_type,
        "path": str(path),
        "status": "pass" if not errors else "fail",
        "errors": errors,
    }


def pipeline_stage_names(pipeline: dict[str, Any]) -> list[str]:
    return [str(stage.get("name")) for stage in pipeline.get("stages", [])]


def validate_pipeline_manifest(
    pipeline: dict[str, Any],
    *,
    registry: dict[str, Any] | None = None,
    project_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    registry = registry or load_tool_registry(DEFAULT_REGISTRY_PATH)
    tools = tool_index(registry)
    directors = load_director_registry().get("directors") or []
    director_index = {str(row.get("id")): row for row in directors}
    registered_entry_names = {
        *tools,
        *(str(row.get("name")) for row in registry.get("skills", [])),
    }
    failures: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    if pipeline.get("schema_version") != "dasheng.video.pipeline.v1":
        failures.append({"code": "bad_schema_version", "message": "Pipeline schema_version must be dasheng.video.pipeline.v1."})
    if not pipeline.get("id"):
        failures.append({"code": "missing_id", "message": "Pipeline id is required."})
    if pipeline.get("lane") not in VALID_LANES:
        failures.append({"code": "bad_lane", "message": "Pipeline lane is not recognized."})
    if not pipeline.get("fail_conditions"):
        failures.append({"code": "missing_fail_conditions", "message": "Pipeline must define fail_conditions."})

    lane = str(pipeline.get("lane") or "")
    director_id = str(pipeline.get("director_id") or "")
    if lane in PRODUCTION_LANES:
        if not director_id:
            failures.append({"code": "missing_director_id", "message": "Production pipeline must declare director_id."})
        elif director_id not in director_index:
            failures.append({"code": "unknown_director_id", "message": f"Director is not registered: {director_id}."})
        else:
            director = director_index[director_id]
            if director.get("lane") != lane or director.get("pipeline_id") != pipeline.get("id"):
                failures.append(
                    {
                        "code": "director_pipeline_mismatch",
                        "message": f"Director {director_id} does not match pipeline {pipeline.get('id')} / lane {lane}.",
                    }
                )
            for tool_name in [*(director.get("core_tools") or []), *(director.get("reserve_tools") or [])]:
                if tool_name not in registered_entry_names:
                    failures.append(
                        {
                            "code": "unknown_director_tool",
                            "message": f"Director {director_id} references an unregistered tool or skill: {tool_name}.",
                        }
                    )
    if lane == "cinematic_short_drama_video":
        director = director_index.get(director_id) or {}
        if pipeline.get("execution_enabled") is not False or director.get("execution_enabled") is not False:
            failures.append(
                {
                    "code": "deferred_pipeline_enabled",
                    "message": "Cinematic short-drama pipeline and director must remain execution_enabled=false.",
                }
            )

    output_policy = pipeline.get("external_output_policy") or {}
    required_root = str(output_policy.get("required_root") or "")
    if "自媒体创作" not in required_root:
        warnings.append(
            {
                "code": "output_root_not_creator_desktop",
                "message": "Pipeline should default generated media to ~/Desktop/自媒体创作.",
            }
        )

    stage_names = pipeline_stage_names(pipeline)
    if len(stage_names) != len(set(stage_names)):
        failures.append({"code": "duplicate_stage_name", "message": "Stage names must be unique."})

    for stage in pipeline.get("stages", []):
        stage_name = str(stage.get("name") or "unknown")
        for field in ["skill", "produces", "tools_available", "success_criteria"]:
            if not stage.get(field):
                failures.append({"code": "stage_missing_field", "stage": stage_name, "message": f"Stage missing {field}."})
        for artifact_type in [*stage.get("required_artifacts_in", []), *stage.get("produces", [])]:
            if artifact_type not in ARTIFACT_SCHEMAS:
                failures.append(
                    {
                        "code": "unknown_artifact_type",
                        "stage": stage_name,
                        "message": f"Unknown artifact type: {artifact_type}.",
                    }
                )
                continue
            schema_path = SCHEMA_DIR / ARTIFACT_SCHEMAS[artifact_type]
            if not schema_path.exists():
                failures.append(
                    {
                        "code": "missing_artifact_schema",
                        "stage": stage_name,
                        "message": f"Missing schema for artifact type {artifact_type}.",
                    }
                )
        for tool_name in stage.get("tools_available", []):
            if tool_name not in tools:
                failures.append(
                    {
                        "code": "unknown_tool",
                        "stage": stage_name,
                        "message": f"Tool {tool_name} is not registered.",
                    }
                )
        skill_name = str(stage.get("skill") or "")
        if skill_name.startswith("dasheng-") and not (LOCAL_SKILLS_DIR / skill_name / "SKILL.md").exists():
            failures.append(
                {
                    "code": "missing_stage_skill",
                    "stage": stage_name,
                    "message": f"Stage skill does not exist: {skill_name}.",
                }
            )

    for missing in unresolved_script_paths(registry, project_root=project_root):
        failures.append(
            {
                "code": "missing_tool_script",
                "tool": missing["name"],
                "message": f"Registered script does not exist: {missing['path']}",
            }
        )
    for missing in unresolved_skill_paths(registry, skills_dir=LOCAL_SKILLS_DIR):
        failures.append(
            {
                "code": "missing_tool_skill",
                "tool": missing["name"],
                "message": f"Registered skill does not exist: {missing['skill']}",
            }
        )
    for missing in unresolved_project_paths(registry, project_root=project_root):
        failures.append(
            {
                "code": "missing_registered_project",
                "tool": missing["name"],
                "message": f"Registered project does not exist: {missing['path']}",
            }
        )

    return {
        "schema_version": "dasheng.video.pipeline_validation_report.v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "pipeline_id": pipeline.get("id"),
        "lane": pipeline.get("lane"),
        "stage_count": len(pipeline.get("stages", [])),
        "stages": stage_names,
        "status": "pass" if not failures else "fail",
        "failures": failures,
        "warnings": warnings,
    }


def build_checkpoint(
    pipeline: dict[str, Any],
    stage_name: str,
    *,
    artifact_paths: dict[str, str] | None = None,
    status: str = "pending_review",
    notes: str = "",
) -> dict[str, Any]:
    stage = next((item for item in pipeline.get("stages", []) if item.get("name") == stage_name), None)
    if not stage:
        raise KeyError(f"Unknown stage: {stage_name}")
    return {
        "schema_version": "dasheng.video.pipeline_checkpoint.v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "pipeline_id": pipeline.get("id"),
        "lane": pipeline.get("lane"),
        "stage": stage_name,
        "status": status,
        "checkpoint_required": bool(stage.get("checkpoint_required")),
        "human_approval_default": bool(stage.get("human_approval_default", pipeline.get("human_approval_default", False))),
        "required_artifacts_in": stage.get("required_artifacts_in", []),
        "produces": stage.get("produces", []),
        "review_focus": stage.get("review_focus", []),
        "success_criteria": stage.get("success_criteria", []),
        "artifact_paths": artifact_paths or {},
        "notes": notes,
    }


def parse_artifact_pairs(values: list[str]) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"Artifact path must use type=path format: {value}")
        artifact_type, path = value.split("=", 1)
        pairs[artifact_type.strip()] = path.strip()
    return pairs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Newma video pipeline manifests and artifacts.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List available pipeline ids.")
    list_parser.add_argument("--dir", default=str(PIPELINE_DIR))

    validate_parser = subparsers.add_parser("validate-pipeline", help="Validate a pipeline manifest.")
    validate_parser.add_argument("pipeline")

    artifact_parser = subparsers.add_parser("validate-artifact", help="Validate an artifact JSON file.")
    artifact_parser.add_argument("artifact_type", choices=sorted(ARTIFACT_SCHEMAS))
    artifact_parser.add_argument("path")

    checkpoint_parser = subparsers.add_parser("checkpoint", help="Emit a stage checkpoint JSON.")
    checkpoint_parser.add_argument("pipeline")
    checkpoint_parser.add_argument("stage")
    checkpoint_parser.add_argument("--artifact", action="append", default=[], help="Artifact path in type=path form.")
    checkpoint_parser.add_argument("--status", default="pending_review")
    checkpoint_parser.add_argument("--notes", default="")
    checkpoint_parser.add_argument("--output", default="")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "list":
        pipeline_dir = Path(args.dir).expanduser().resolve()
        ids = [load_pipeline(path).get("id") for path in sorted(pipeline_dir.glob("*.yaml"))]
        print(json.dumps({"pipelines": ids}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "validate-pipeline":
        report = validate_pipeline_manifest(load_pipeline(args.pipeline))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "pass" else 1

    if args.command == "validate-artifact":
        report = validate_artifact_file(args.artifact_type, Path(args.path).expanduser().resolve())
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["status"] == "pass" else 1

    if args.command == "checkpoint":
        checkpoint = build_checkpoint(
            load_pipeline(args.pipeline),
            args.stage,
            artifact_paths=parse_artifact_pairs(args.artifact),
            status=args.status,
            notes=args.notes,
        )
        if args.output:
            output = Path(args.output).expanduser().resolve()
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(checkpoint, ensure_ascii=False, indent=2))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
