import json
import subprocess
from pathlib import Path

import pytest

from scripts.video_final_delivery import DeliveryError, build_manifest


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def make_video(path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x180:d=0.2:r=30",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        check=True,
    )


def test_final_delivery_requires_qc_for_exact_video(tmp_path: Path) -> None:
    video = tmp_path / "final.mp4"
    make_video(video)
    qc = tmp_path / "qc.json"
    write_json(qc, {"status": "pass", "video": str(video)})
    gates = {}
    for name in ["storyboard", "claim", "asset", "renderer"]:
        path = tmp_path / f"{name}.json"
        write_json(path, {"status": "pass"})
        gates[name] = path

    manifest = build_manifest(
        lane="explainer_html_video",
        video_path=video,
        qc_path=qc,
        gate_paths=gates,
    )

    assert manifest["status"] == "ready_for_publish"
    assert manifest["width"] == 320
    assert manifest["height"] == 180
    assert len(manifest["sha256"]) == 64


def test_final_delivery_rejects_qc_for_old_video(tmp_path: Path) -> None:
    video = tmp_path / "final.mp4"
    old_video = tmp_path / "old.mp4"
    make_video(video)
    make_video(old_video)
    qc = tmp_path / "qc.json"
    write_json(qc, {"status": "pass", "video": str(old_video)})
    gate = tmp_path / "gate.json"
    write_json(gate, {"status": "pass"})

    with pytest.raises(DeliveryError, match="QC 检查文件与交付文件不一致"):
        build_manifest(
            lane="explainer_html_video",
            video_path=video,
            qc_path=qc,
            gate_paths={"storyboard": gate, "claim": gate, "asset": gate, "renderer": gate},
        )


def test_commercial_delivery_requires_brand_brief_gate(tmp_path: Path) -> None:
    with pytest.raises(DeliveryError, match="brand_brief_gate"):
        build_manifest(
            lane="commercial_promo_video",
            video_path=tmp_path / "final.mp4",
            qc_path=tmp_path / "qc.json",
            gate_paths={},
        )
