#!/usr/bin/env python3
"""Create and update a Newma project run manifest."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import jsonschema

from path_config import get_desktop_root, get_project_root
from video_pipeline_governance import load_pipeline


PROJECT_ROOT = get_project_root()
SCHEMA_PATH = PROJECT_ROOT / "configs" / "workflow" / "project_run_manifest.schema.json"
CREATOR_ROOT_NAME = "自媒体创作"
FORBIDDEN_OUTPUT_PARTS = {"skills", ".codex", "node_modules"}
MAINLINE_PIPELINE_ID = "mainline"
MAINLINE_STAGES = ["intake", "brief", "draft", "transwrite", "publish", "postmortem"]


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def slugify_title(title: str) -> str:
    normalized = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", title.strip(), flags=re.UNICODE)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized[:48] or "untitled"


def default_run_id(title: str) -> str:
    return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{slugify_title(title)}"


def expand_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def is_safe_output_root(path: str | Path, *, project_root: Path = PROJECT_ROOT) -> bool:
    output_root = expand_path(path)
    parts = set(output_root.parts)
    if CREATOR_ROOT_NAME not in output_root.parts:
        return False
    if FORBIDDEN_OUTPUT_PARTS & parts:
        return False
    try:
        output_root.relative_to(project_root)
        return False
    except ValueError:
        return True


def parse_key_value_items(items: list[str]) -> list[dict[str, str]]:
    parsed: list[dict[str, str]] = []
    for item in items:
        if "=" not in item:
            raise ValueError(f"Expected type=path format: {item}")
        item_type, path = item.split("=", 1)
        parsed.append({"type": item_type.strip(), "path": path.strip()})
    return parsed


def resolve_pipeline_definition(pipeline_id: str) -> dict[str, Any]:
    if pipeline_id == MAINLINE_PIPELINE_ID:
        return {
            "id": MAINLINE_PIPELINE_ID,
            "lane": "article",
            "stages": [{"name": name} for name in MAINLINE_STAGES],
        }
    return load_pipeline(pipeline_id)


def pipeline_stage_names_for_run(pipeline: dict[str, Any]) -> list[str]:
    return [str(stage.get("name")) for stage in pipeline.get("stages", []) if stage.get("name")]


def build_manifest(
    *,
    title: str,
    pipeline_id: str,
    lane: str | None = None,
    output_root: str | Path | None = None,
    source_materials: list[dict[str, str]] | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    pipeline = resolve_pipeline_definition(pipeline_id)
    resolved_lane = lane or str(pipeline.get("lane") or "")
    resolved_run_id = run_id or default_run_id(title)
    resolved_output_root = expand_path(output_root or (get_desktop_root() / resolved_run_id))
    if not is_safe_output_root(resolved_output_root):
        raise ValueError(f"Unsafe output_root: {resolved_output_root}")
    timestamp = now_iso()
    return {
        "schema_version": "newma.project_run_manifest.v2",
        "run_id": resolved_run_id,
        "title": title,
        "created_at": timestamp,
        "updated_at": timestamp,
        "pipeline_id": pipeline_id,
        "lane": resolved_lane,
        "project_root": str(PROJECT_ROOT),
        "output_root": str(resolved_output_root),
        "source_materials": source_materials or [],
        "stages": [{"name": name, "status": "pending"} for name in pipeline_stage_names_for_run(pipeline)],
        "artifacts": [],
        "approvals": [],
        "retries": [],
        "publish_targets": [],
    }


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_manifest(manifest: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_manifest(manifest: dict[str, Any]) -> list[dict[str, str]]:
    validator = jsonschema.Draft202012Validator(load_schema())
    errors: list[dict[str, str]] = []
    for error in sorted(validator.iter_errors(manifest), key=lambda item: list(item.path)):
        errors.append(
            {
                "code": "schema_invalid",
                "path": ".".join(str(part) for part in error.path),
                "message": error.message,
            }
        )
    if not is_safe_output_root(manifest.get("output_root", "")):
        errors.append(
            {
                "code": "unsafe_output_root",
                "path": "output_root",
                "message": "output_root must be outside the repo and under ~/Desktop/自媒体创作.",
            }
        )
    return errors


def find_stage(manifest: dict[str, Any], stage_name: str) -> dict[str, Any]:
    for stage in manifest.get("stages", []):
        if stage.get("name") == stage_name:
            return stage
    raise KeyError(f"Unknown stage: {stage_name}")


def set_stage_status(
    manifest: dict[str, Any],
    *,
    stage_name: str,
    status: str,
    checkpoint_path: str = "",
    review_path: str = "",
    notes: str = "",
) -> dict[str, Any]:
    stage = find_stage(manifest, stage_name)
    stage["status"] = status
    if status == "running" and not stage.get("started_at"):
        stage["started_at"] = now_iso()
    if status in {"approved", "blocked", "complete", "needs_revision"}:
        stage["completed_at"] = now_iso()
    if checkpoint_path:
        stage["checkpoint_path"] = checkpoint_path
    if review_path:
        stage["review_path"] = review_path
    if notes:
        stage["notes"] = notes
    manifest["updated_at"] = now_iso()
    return manifest


def add_artifact(
    manifest: dict[str, Any],
    *,
    stage_name: str,
    artifact_type: str,
    path: str,
    status: str = "created",
    notes: str = "",
) -> dict[str, Any]:
    find_stage(manifest, stage_name)
    index = len(manifest.get("artifacts", [])) + 1
    artifact = {
        "id": f"{stage_name}_{artifact_type}_{index:03d}",
        "stage": stage_name,
        "type": artifact_type,
        "path": path,
        "status": status,
        "created_at": now_iso(),
    }
    if notes:
        artifact["notes"] = notes
    manifest.setdefault("artifacts", []).append(artifact)
    manifest["updated_at"] = now_iso()
    return manifest


def build_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    stage_counts: dict[str, int] = {}
    for stage in manifest.get("stages", []):
        status = str(stage.get("status"))
        stage_counts[status] = stage_counts.get(status, 0) + 1
    return {
        "run_id": manifest.get("run_id"),
        "title": manifest.get("title"),
        "pipeline_id": manifest.get("pipeline_id"),
        "lane": manifest.get("lane"),
        "output_root": manifest.get("output_root"),
        "stage_status_counts": stage_counts,
        "artifact_count": len(manifest.get("artifacts", [])),
        "latest_artifacts": manifest.get("artifacts", [])[-5:],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create and update Newma project run manifests.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a new run manifest.")
    init_parser.add_argument("--title", required=True)
    init_parser.add_argument("--pipeline", required=True)
    init_parser.add_argument("--lane", default="")
    init_parser.add_argument("--run-id", default="")
    init_parser.add_argument("--output-root", default="")
    init_parser.add_argument("--source", action="append", default=[], help="Source material in type=path form.")
    init_parser.add_argument("--output", default="")

    validate_parser = subparsers.add_parser("validate", help="Validate a run manifest.")
    validate_parser.add_argument("manifest")

    artifact_parser = subparsers.add_parser("add-artifact", help="Append an artifact record.")
    artifact_parser.add_argument("manifest")
    artifact_parser.add_argument("--stage", required=True)
    artifact_parser.add_argument("--type", required=True)
    artifact_parser.add_argument("--path", required=True)
    artifact_parser.add_argument("--status", default="created")
    artifact_parser.add_argument("--notes", default="")

    stage_parser = subparsers.add_parser("set-stage", help="Update a stage status.")
    stage_parser.add_argument("manifest")
    stage_parser.add_argument("--stage", required=True)
    stage_parser.add_argument("--status", required=True)
    stage_parser.add_argument("--checkpoint", default="")
    stage_parser.add_argument("--review", default="")
    stage_parser.add_argument("--notes", default="")

    summary_parser = subparsers.add_parser("summary", help="Summarize a run manifest.")
    summary_parser.add_argument("manifest")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "init":
        manifest = build_manifest(
            title=args.title,
            pipeline_id=args.pipeline,
            lane=args.lane or None,
            output_root=args.output_root or None,
            source_materials=parse_key_value_items(args.source),
            run_id=args.run_id or None,
        )
        errors = validate_manifest(manifest)
        if errors:
            print(json.dumps({"status": "fail", "errors": errors}, ensure_ascii=False, indent=2))
            return 1
        output = expand_path(args.output or (Path(manifest["output_root"]) / "project_run_manifest.json"))
        save_manifest(manifest, output)
        print(json.dumps({"status": "pass", "manifest": str(output), "summary": build_summary(manifest)}, ensure_ascii=False, indent=2))
        return 0

    manifest_path = expand_path(args.manifest)
    manifest = load_manifest(manifest_path)

    if args.command == "validate":
        errors = validate_manifest(manifest)
        print(json.dumps({"status": "pass" if not errors else "fail", "errors": errors}, ensure_ascii=False, indent=2))
        return 0 if not errors else 1

    if args.command == "add-artifact":
        add_artifact(
            manifest,
            stage_name=args.stage,
            artifact_type=args.type,
            path=args.path,
            status=args.status,
            notes=args.notes,
        )
        errors = validate_manifest(manifest)
        if errors:
            print(json.dumps({"status": "fail", "errors": errors}, ensure_ascii=False, indent=2))
            return 1
        save_manifest(manifest, manifest_path)
        print(json.dumps({"status": "pass", "summary": build_summary(manifest)}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "set-stage":
        set_stage_status(
            manifest,
            stage_name=args.stage,
            status=args.status,
            checkpoint_path=args.checkpoint,
            review_path=args.review,
            notes=args.notes,
        )
        errors = validate_manifest(manifest)
        if errors:
            print(json.dumps({"status": "fail", "errors": errors}, ensure_ascii=False, indent=2))
            return 1
        save_manifest(manifest, manifest_path)
        print(json.dumps({"status": "pass", "summary": build_summary(manifest)}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "summary":
        print(json.dumps(build_summary(manifest), ensure_ascii=False, indent=2))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
