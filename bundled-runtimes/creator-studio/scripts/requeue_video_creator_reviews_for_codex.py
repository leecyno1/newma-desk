#!/usr/bin/env python3
"""Archive external-model analyses and rebuild the direct Codex review queue."""

from __future__ import annotations

import argparse
from pathlib import Path

from run_video_creator_self_learning import (
    DEFAULT_CONFIG,
    DEFAULT_OUTPUT_ROOT,
    build_paths,
    load_config,
    load_json,
    now_iso,
    prepare_codex_review_packet,
    write_json,
)


def archive_legacy(path: Path, suffix: str) -> Path | None:
    if not path.is_file():
        return None
    target = path.with_name(f"{path.stem}.minimax_legacy_{suffix}{path.suffix}")
    counter = 2
    while target.exists():
        target = path.with_name(f"{path.stem}.minimax_legacy_{suffix}_{counter}{path.suffix}")
        counter += 1
    path.replace(target)
    return target


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Requeue CRV evidence for direct Codex review.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--output-root", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(Path(args.config).expanduser().resolve())
    root = Path(args.output_root or config.get("output_root") or DEFAULT_OUTPUT_ROOT).expanduser().resolve()
    paths = build_paths(root)
    state = load_json(paths["state"], {})
    suffix = now_iso().replace(":", "").replace("+", "_").replace("-", "")
    requeued = 0
    skipped_without_crv = 0

    for creator_id, creator in (state.get("creators") or {}).items():
        profile = paths["profiles"] / creator_id / "style_profile.rolling.json"
        for video_id, record in (creator.get("videos") or {}).items():
            metadata = record.get("metadata") or {}
            upload_date = str(metadata.get("upload_date") or "")
            note_dir = paths["notes"] / creator_id / f"{upload_date}_{video_id}"
            if not note_dir.is_dir():
                matches = list(paths["notes"].glob(f"*/{upload_date}_{video_id}"))
                if matches:
                    note_dir = matches[0]
            crv_result = load_json(note_dir / "crv_result.json", None)
            if not isinstance(crv_result, dict):
                skipped_without_crv += 1
                continue
            if (note_dir / "analysis_provider_response.json").is_file():
                archive_legacy(note_dir / "analysis.json", suffix)
                archive_legacy(note_dir / "analysis.md", suffix)
            packet = prepare_codex_review_packet(config, paths, metadata, crv_result, note_dir, profile)
            record.update(
                {
                    "status": "awaiting_codex_analysis",
                    "codex_review_packet": str(note_dir / "codex_review_packet.json"),
                    "updated_at": now_iso(),
                    "last_error": None,
                }
            )
            record.pop("analysis_json", None)
            record.pop("analysis_note", None)
            record.pop("completed_at", None)
            requeued += 1

    state["updated_at"] = now_iso()
    write_json(paths["state"], state)
    print(
        {
            "status": "completed",
            "requeued_for_codex": requeued,
            "skipped_without_crv": skipped_without_crv,
            "queue": str(paths["codex_queue"]),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
