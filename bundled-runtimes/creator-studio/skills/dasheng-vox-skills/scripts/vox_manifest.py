#!/usr/bin/env python3
"""Build and update the unified VOX shot manifest."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "dasheng.video.omni_shot_manifest.v1"
REFERENCE_PROVIDER = "codex_builtin_imagegen"
DEFAULT_PROVIDER_ORDER = [
    "gemini_api_omni",
    "gemini_api_veo",
    "gemini_browser_omni",
    "remotion_local_motion",
]
VALID_PROVIDERS = set(DEFAULT_PROVIDER_ORDER) | {"minimax_mmx", "seedance"}
FINAL_STATUSES = {"approved", "fallback_ready"}
PROGRAMMATIC_ROUTES = {"shotcraft_remotion", "real_evidence_remotion"}


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def is_programmatic_shot(shot: dict[str, Any]) -> bool:
    motion = shot.get("motion") or {}
    return str(shot.get("production_route") or "") in PROGRAMMATIC_ROUTES or (
        isinstance(motion, dict) and bool(motion.get("shotcraft_card"))
    )


def shot_status(reference: Path | None, clip: Path, production_route: str) -> str:
    if clip.exists():
        return "clip_ready"
    if production_route in PROGRAMMATIC_ROUTES:
        return "ready_for_remotion"
    if reference is None:
        return "pending_reference"
    if reference.exists():
        return "ready_for_generation"
    return "pending_reference"


def ordered_providers(raw: dict[str, Any], default_order: list[str]) -> list[str]:
    providers = raw.get("provider_order") or default_order
    if not isinstance(providers, list) or not providers:
        raise ValueError("provider_order must be a non-empty array")
    unknown = [item for item in providers if item not in VALID_PROVIDERS]
    if unknown:
        raise ValueError(f"unsupported providers: {', '.join(unknown)}")
    return providers


def build_manifest(source: Path, output_dir: Path) -> Path:
    payload = read_json(source)
    shots = payload.get("shots") if isinstance(payload.get("shots"), list) else payload.get("scenes")
    if not isinstance(shots, list) or not shots:
        raise ValueError("input must contain a non-empty shots[] or scenes[] array")

    default_order = ordered_providers(payload, DEFAULT_PROVIDER_ORDER)
    reference_dir = output_dir / "reference-images"
    prompt_dir = output_dir / "prompts"
    clip_dir = output_dir / "clips"
    for directory in (reference_dir, prompt_dir, clip_dir):
        directory.mkdir(parents=True, exist_ok=True)

    jobs: list[dict[str, Any]] = []
    for index, raw in enumerate(shots, 1):
        shot = dict(raw)
        shot_id = str(shot.get("id") or f"shot-{index:02d}")
        start = float(shot["start_sec"])
        end = float(shot["end_sec"])
        if end <= start:
            raise ValueError(f"{shot_id}: end_sec must be greater than start_sec")

        programmatic = is_programmatic_shot(shot)
        production_route = str(shot.get("production_route") or ("shotcraft_remotion" if programmatic else "gemini_video"))

        prompt_text = str(shot.get("video_prompt") or shot.get("omni_prompt") or "").strip()
        prompt_path = prompt_dir / f"{shot_id}.video.txt"
        if prompt_text and not programmatic:
            prompt_path.write_text(prompt_text + "\n", encoding="utf-8")

        reference = None if programmatic else reference_dir / f"{shot_id}.png"
        clip = clip_dir / f"{shot_id}.mp4"
        provider_order = ["remotion_local_motion"] if programmatic else ordered_providers(shot, default_order)
        motion_mode = str(shot.get("motion_mode") or "assemble")
        if motion_mode not in {"assemble", "in_place"}:
            raise ValueError(f"{shot_id}: motion_mode must be assemble or in_place")

        jobs.append(
            {
                **shot,
                "id": shot_id,
                "timeline_duration_sec": round(end - start, 3),
                "generation_duration_sec": int(shot.get("generation_duration_sec") or 10),
                "production_route": production_route,
                "motion_mode": motion_mode,
                "reference_image_required": not programmatic,
                "reference_image": str(reference) if reference else None,
                "reference_image_provider": REFERENCE_PROVIDER if reference else None,
                "video_prompt_file": str(prompt_path) if not programmatic else None,
                "clip_path": str(clip),
                "provider_order": provider_order,
                "selected_provider": None,
                "attempts": [],
                "status": shot_status(reference, clip, production_route),
            }
        )

    has_programmatic = any(job["production_route"] in PROGRAMMATIC_ROUTES for job in jobs)
    workflow = (
        [
            "director_shots",
            "shotcraft_binding",
            "conditional_codex_reference_images",
            "provider_or_local_motion",
            "remotion_edit",
            "automated_qc",
        ]
        if has_programmatic
        else [
            "director_shots",
            "codex_reference_images",
            "provider_routed_video_generation",
            "remotion_edit",
            "automated_qc",
        ]
    )
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "provider": "routed_official_google_or_signed_in_chrome",
        "created_at": now(),
        "aspect_ratio": str(payload.get("aspect_ratio") or "16:9"),
        "reference_image_provider": REFERENCE_PROVIDER,
        "video_provider": "provider_router",
        "provider_order": default_order,
        "workflow": workflow,
        "jobs": jobs,
    }
    manifest_path = output_dir / "vox_manifest.json"
    write_json(manifest_path, manifest)
    return manifest_path


def find_job(manifest: dict[str, Any], shot_id: str) -> dict[str, Any]:
    for job in manifest.get("jobs", []):
        if job.get("id") == shot_id:
            return job
    raise ValueError(f"shot not found: {shot_id}")


def record_attempt(
    manifest_path: Path,
    shot_id: str,
    provider: str,
    status: str,
    *,
    error: str | None = None,
    operation_id: str | None = None,
    output: str | None = None,
) -> None:
    if provider not in VALID_PROVIDERS:
        raise ValueError(f"unsupported provider: {provider}")
    if status not in {"started", "succeeded", "failed", "rejected"}:
        raise ValueError("attempt status must be started, succeeded, failed or rejected")

    manifest = read_json(manifest_path)
    job = find_job(manifest, shot_id)
    attempt = {
        "provider": provider,
        "status": status,
        "at": now(),
    }
    if error:
        attempt["error"] = error
    if operation_id:
        attempt["operation_id"] = operation_id
    if output:
        attempt["output"] = output
    job.setdefault("attempts", []).append(attempt)

    if status == "started":
        job["selected_provider"] = provider
        job["status"] = "generating"
    elif status == "succeeded":
        job["selected_provider"] = provider
        if output:
            job["clip_path"] = output
        job["status"] = "clip_ready"
    elif status == "rejected":
        job["status"] = "rejected"
    else:
        job["status"] = "ready_for_remotion" if is_programmatic_shot(job) else "ready_for_generation"

    manifest["updated_at"] = now()
    write_json(manifest_path, manifest)


def set_status(manifest_path: Path, shot_id: str, status: str) -> None:
    allowed = {
        "pending_reference",
        "ready_for_remotion",
        "ready_for_generation",
        "generating",
        "clip_ready",
        "rejected",
        "approved",
        "fallback_ready",
    }
    if status not in allowed:
        raise ValueError(f"unsupported status: {status}")
    manifest = read_json(manifest_path)
    find_job(manifest, shot_id)["status"] = status
    manifest["updated_at"] = now()
    write_json(manifest_path, manifest)


def refresh(manifest_path: Path) -> None:
    manifest = read_json(manifest_path)
    for job in manifest.get("jobs", []):
        if job.get("status") in FINAL_STATUSES or job.get("status") == "rejected":
            continue
        reference_value = job.get("reference_image")
        reference = Path(reference_value) if reference_value else None
        job["status"] = shot_status(reference, Path(job["clip_path"]), str(job.get("production_route") or "gemini_video"))
    manifest["updated_at"] = now()
    write_json(manifest_path, manifest)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build")
    build.add_argument("--shots", type=Path, required=True)
    build.add_argument("--output-dir", type=Path, required=True)

    update = sub.add_parser("refresh")
    update.add_argument("--manifest", type=Path, required=True)

    record = sub.add_parser("record-attempt")
    record.add_argument("--manifest", type=Path, required=True)
    record.add_argument("--shot", required=True)
    record.add_argument("--provider", required=True)
    record.add_argument("--status", required=True)
    record.add_argument("--error")
    record.add_argument("--operation-id")
    record.add_argument("--output")

    status = sub.add_parser("set-status")
    status.add_argument("--manifest", type=Path, required=True)
    status.add_argument("--shot", required=True)
    status.add_argument("--status", required=True)

    args = parser.parse_args()
    if args.command == "build":
        path = build_manifest(args.shots.expanduser().resolve(), args.output_dir.expanduser().resolve())
        print(path)
    elif args.command == "refresh":
        refresh(args.manifest.expanduser().resolve())
        print(args.manifest.expanduser().resolve())
    elif args.command == "record-attempt":
        record_attempt(
            args.manifest.expanduser().resolve(),
            args.shot,
            args.provider,
            args.status,
            error=args.error,
            operation_id=args.operation_id,
            output=args.output,
        )
    else:
        set_status(args.manifest.expanduser().resolve(), args.shot, args.status)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
