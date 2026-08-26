#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class DeliveryError(RuntimeError):
    pass


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise DeliveryError(f"JSON 顶层必须是对象：{path}")
    return payload


def gate_passed(payload: dict[str, Any]) -> bool:
    status = str(payload.get("status") or "").lower()
    return bool(
        payload.get("passed") is True
        or payload.get("render_allowed") is True
        or status in {"pass", "passed", "approved", "ready"}
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe_video(path: Path) -> dict[str, Any]:
    output = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration:stream=codec_name,codec_type,width,height,r_frame_rate",
            "-of",
            "json",
            str(path),
        ],
        text=True,
    )
    payload = json.loads(output)
    streams = payload.get("streams") or []
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    if not video:
        raise DeliveryError(f"终片缺少视频流：{path}")
    rate = str(video.get("r_frame_rate") or "0/1")
    numerator, denominator = rate.split("/", 1)
    fps = float(numerator) / float(denominator)
    return {
        "duration_sec": round(float(payload["format"]["duration"]), 3),
        "width": int(video["width"]),
        "height": int(video["height"]),
        "fps": round(fps, 3),
        "video_codec": video.get("codec_name"),
        "audio_codec": audio.get("codec_name") if audio else None,
    }


def build_manifest(
    *,
    lane: str,
    video_path: Path,
    qc_path: Path,
    gate_paths: dict[str, Path],
    subtitle_path: Path | None = None,
) -> dict[str, Any]:
    if lane == "commercial_promo_video" and "brand_brief_gate" not in gate_paths:
        raise DeliveryError("广告宣传片交付缺少 brand_brief_gate")
    video = video_path.resolve()
    qc = qc_path.resolve()
    if not video.exists():
        raise DeliveryError(f"终片不存在：{video}")
    qc_payload = read_json(qc)
    if str(qc_payload.get("status") or "").lower() != "pass":
        raise DeliveryError(f"完整视频 QC 未通过：{qc}")
    qc_video = Path(str(qc_payload.get("video") or "")).expanduser().resolve()
    if qc_video != video:
        raise DeliveryError(f"QC 检查文件与交付文件不一致：{qc_video} != {video}")

    gates: dict[str, str] = {}
    for name, path in gate_paths.items():
        resolved = path.resolve()
        if not resolved.exists() or not gate_passed(read_json(resolved)):
            raise DeliveryError(f"门禁未通过：{name} -> {resolved}")
        gates[name] = str(resolved)

    media = probe_video(video)
    subtitle = subtitle_path.resolve() if subtitle_path else None
    if subtitle and not subtitle.exists():
        raise DeliveryError(f"字幕不存在：{subtitle}")
    return {
        "schema_version": "dasheng.video.final_delivery_manifest.v1",
        "status": "ready_for_publish",
        "created_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "lane": lane,
        "video": str(video),
        "subtitle": str(subtitle) if subtitle else None,
        "qc_report": str(qc),
        "gates": gates,
        "sha256": sha256(video),
        **media,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Create the final video delivery manifest after all gates pass.")
    parser.add_argument("--lane", choices=["explainer_html_video", "vox_explainer_video", "talking_head_video", "digital_human_video", "commercial_promo_video", "cinematic_short_drama_video"], required=True)
    parser.add_argument("--video", required=True)
    parser.add_argument("--qc-report", required=True)
    parser.add_argument("--storyboard-gate", required=True)
    parser.add_argument("--brand-brief-gate")
    parser.add_argument("--claim-evidence-gate", required=True)
    parser.add_argument("--renderer-asset-gate", required=True)
    parser.add_argument("--renderer-contract-gate", required=True)
    parser.add_argument("--subtitle")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    payload = build_manifest(
        lane=args.lane,
        video_path=Path(args.video).expanduser(),
        qc_path=Path(args.qc_report).expanduser(),
        subtitle_path=Path(args.subtitle).expanduser() if args.subtitle else None,
        gate_paths={
            **({"brand_brief_gate": Path(args.brand_brief_gate).expanduser()} if args.brand_brief_gate else {}),
            "storyboard_review_gate": Path(args.storyboard_gate).expanduser(),
            "claim_evidence_gate": Path(args.claim_evidence_gate).expanduser(),
            "renderer_asset_gate": Path(args.renderer_asset_gate).expanduser(),
            "renderer_contract_gate": Path(args.renderer_contract_gate).expanduser(),
        },
    )
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
