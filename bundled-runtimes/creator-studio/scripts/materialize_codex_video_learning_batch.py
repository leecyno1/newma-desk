#!/usr/bin/env python3
"""Materialize direct Codex video reviews from a human-readable batch spec."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any


MERGED_ARRAY_FIELDS = [
    "director_analysis",
    "design_analysis",
    "storyboard_analysis",
    "transition_analysis",
    "production_analysis",
    "chart_analysis",
    "aesthetic_profile",
    "reproduction_stack",
    "reusable_rules",
    "anti_patterns",
    "confidence_notes",
]


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def merge_unique(shared: list[Any], specific: list[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for item in [*shared, *specific]:
        key = json.dumps(item, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def normalize_video(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "platform": str(metadata["platform"]),
        "creator_id": str(metadata["creator_id"]),
        "creator_name": str(metadata.get("creator_name") or metadata["creator_id"]),
        "video_id": str(metadata["video_id"]),
        "title": str(metadata["title"]),
        "url": str(metadata["url"]),
        "duration_sec": float(metadata.get("duration_sec") or 0),
        "upload_date": str(metadata.get("upload_date") or ""),
    }


def validate_schema(payload: dict[str, Any], schema_path: Path) -> None:
    try:
        from jsonschema import validate
    except ImportError:
        return
    validate(payload, load_json(schema_path))


def materialize(spec_path: Path, schema_path: Path) -> list[Path]:
    spec = load_json(spec_path)
    if spec.get("schema_version") != "dasheng.codex_video_learning_batch.v1":
        raise ValueError("unsupported batch spec schema")
    shared = spec.get("shared") or {}
    outputs: list[Path] = []
    for item in spec.get("videos") or []:
        packet_path = Path(item["packet"]).expanduser().resolve()
        packet = load_json(packet_path)
        note_dir = packet_path.parent
        analysis = {
            "schema_version": "dasheng.video_creator_learning_analysis.v1",
            "analyzed_at": now_iso(),
            "video": normalize_video(packet["video"]),
            "content_architecture": list(item.get("content_architecture") or []),
        }
        for field in MERGED_ARRAY_FIELDS:
            analysis[field] = merge_unique(list(shared.get(field) or []), list(item.get(field) or []))
        evidence = packet.get("evidence") or {}
        analysis["confidence_notes"] = merge_unique(
            analysis["confidence_notes"],
            [
                "本分析由 Codex 直接读取 claude-real-video 本地证据完成，未调用外部视频分析模型。",
                f"已检查联系表 {len(evidence.get('contact_sheets') or [])} 张；CRV 清单：{evidence.get('llm_manifest')}",
            ],
        )
        validate_schema(analysis, schema_path)
        output = note_dir / "analysis.json"
        write_json(output, analysis)
        outputs.append(output)
    return outputs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Materialize a direct Codex video-learning batch.")
    parser.add_argument("spec")
    parser.add_argument(
        "--schema",
        default="configs/video/artifact_schemas/creator_learning_analysis.schema.json",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    outputs = materialize(Path(args.spec).expanduser().resolve(), Path(args.schema).expanduser().resolve())
    print(json.dumps({"status": "completed", "count": len(outputs), "outputs": [str(path) for path in outputs]}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
