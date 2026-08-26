import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import jsonschema
import pytest
from PIL import Image


PROJECT_ROOT = Path(__file__).parent.parent
SKILL_ROOT = PROJECT_ROOT / "skills" / "dasheng-digital-human-talking-head"
PYTHON = sys.executable


def load_module(relative_path: str, name: str):
    path = SKILL_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def make_inputs(tmp_path: Path, duration: float = 3.0) -> tuple[Path, Path, Path]:
    image = tmp_path / "portrait.png"
    audio = tmp_path / "narration.wav"
    srt = tmp_path / "captions.srt"
    Image.new("RGB", (768, 1024), (190, 170, 150)).save(image)
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=24000:cl=mono",
            "-t",
            str(duration),
            str(audio),
        ],
        check=True,
    )
    srt.write_text(
        "1\n00:00:00,000 --> 00:00:01,000\n第一句。\n\n"
        "2\n00:00:01,400 --> 00:00:02,600\n第二句。\n",
        encoding="utf-8",
    )
    return image, audio, srt


def test_job_builder_writes_schema_valid_governed_package(tmp_path):
    image, audio, srt = make_inputs(tmp_path)
    output_dir = tmp_path / "job"
    proc = subprocess.run(
        [
            PYTHON,
            str(SKILL_ROOT / "scripts/build_digital_human_job.py"),
            "--image",
            str(image),
            "--audio",
            str(audio),
            "--subtitle",
            str(srt),
            "--output-dir",
            str(output_dir),
            "--consent",
            "confirmed",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    job = json.loads((output_dir / "digital_human_job.json").read_text(encoding="utf-8"))
    manifest = json.loads((output_dir / "presenter_source_manifest.json").read_text(encoding="utf-8"))
    job_schema = json.loads((PROJECT_ROOT / "configs/video/artifact_schemas/digital_human_job.schema.json").read_text())
    manifest_schema = json.loads((PROJECT_ROOT / "configs/video/artifact_schemas/presenter_source_manifest.schema.json").read_text())
    jsonschema.validate(job, job_schema)
    jsonschema.validate(manifest, manifest_schema)
    assert job["voice"]["mount_policy"] == "exactly_once_at_remotion_root"
    assert job["presenter_source"]["engine"] == "luma_dream_machine"
    assert job["generation"]["profile"] == "animal_presenter"
    assert job["generation"]["source_image_policy"] == "codex_imagegen_head_replacement"
    assert job["generation"]["api_video_generation"] is True
    assert manifest["presenter_video_audio_policy"] == "silent_visual_layer"
    assert Path(job["inputs"]["portrait"]).is_file()
    assert Path(job["inputs"]["audio"]).is_file()


def test_job_builder_blocks_missing_consent(tmp_path):
    image, audio, _ = make_inputs(tmp_path)
    proc = subprocess.run(
        [
            PYTHON,
            str(SKILL_ROOT / "scripts/build_digital_human_job.py"),
            "--image",
            str(image),
            "--audio",
            str(audio),
            "--output-dir",
            str(tmp_path / "job"),
            "--consent",
            "not_confirmed",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "consent" in proc.stderr


def test_job_builder_retains_joyvasa_as_explicit_fallback(tmp_path):
    image, audio, _ = make_inputs(tmp_path)
    builder = load_module("scripts/build_digital_human_job.py", "dasheng_job_builder_fallback")
    job_path = builder.build_job(
        image=image,
        audio=audio,
        output_dir=tmp_path / "job",
        consent="confirmed",
        engine="joyvasa_liveportrait",
        profile="calm_presenter",
    )
    job = json.loads(job_path.read_text(encoding="utf-8"))
    assert job["presenter_source"]["engine"] == "joyvasa_liveportrait"
    assert job["generation"]["api_video_generation"] is False


def test_segment_planner_prefers_srt_pauses(tmp_path):
    _, _, srt = make_inputs(tmp_path, duration=40)
    renderer = load_module("scripts/render_joyvasa.py", "dasheng_render_joyvasa")
    segments = renderer.build_segments(40.0, 20.0, srt, min_segment_sec=0.5)
    assert segments[0].source == "subtitle_pause"
    assert segments[0].end_sec == pytest.approx(1.2)
    assert segments[-1].end_sec == pytest.approx(40.0)


def test_qc_passes_silent_presenter_and_fails_audio_bearing_presenter(tmp_path):
    image, audio, _ = make_inputs(tmp_path, duration=2.0)
    builder = load_module("scripts/build_digital_human_job.py", "dasheng_job_builder")
    output_dir = tmp_path / "job"
    job_path = builder.build_job(image=image, audio=audio, output_dir=output_dir, consent="confirmed")
    silent_video = output_dir / "digital_human_source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x240:r=25",
            "-t",
            "2",
            "-an",
            str(silent_video),
        ],
        check=True,
    )
    qc_script = SKILL_ROOT / "scripts/digital_human_qc.py"
    passed = subprocess.run([PYTHON, str(qc_script), "--job", str(job_path)], capture_output=True, text=True, check=False)
    assert passed.returncode == 0, passed.stderr

    audio_video = output_dir / "with_audio.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(silent_video),
            "-i",
            str(audio),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-shortest",
            str(audio_video),
        ],
        check=True,
    )
    failed = subprocess.run(
        [PYTHON, str(qc_script), "--job", str(job_path), "--video", str(audio_video), "--output", str(tmp_path / "failed_qc.json")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert failed.returncode != 0
    report = json.loads((tmp_path / "failed_qc.json").read_text(encoding="utf-8"))
    assert any(item["code"] == "presenter_video_contains_audio" for item in report["failures"])


def test_preflight_reports_external_default_runtime():
    proc = subprocess.run(
        [PYTHON, str(SKILL_ROOT / "scripts/digital_human_preflight.py"), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(proc.stdout)
    assert payload["runtime"]["root"] == str(Path.home() / "AI_MODELS" / "digital-human")
    assert "weights_ready" in payload["runtime"]
