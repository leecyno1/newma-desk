import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "dasheng-vox-skills"
sys.path.insert(0, str(ROOT / "scripts"))
from video_pipeline_governance import validate_artifact  # noqa: E402


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


manifest_module = load_module("vox_manifest", SKILL / "scripts" / "vox_manifest.py")
api_module = load_module("gemini_video_api", SKILL / "scripts" / "gemini_video_api.py")


def test_unified_manifest_tracks_provider_attempts_and_resume(tmp_path):
    shots = tmp_path / "shots.json"
    shots.write_text(
        json.dumps(
            {
                "shots": [
                    {
                        "id": "shot-01",
                        "start_sec": 0,
                        "end_sec": 9.5,
                        "video_prompt": "Assemble four paper groups and hold the final frame.",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    manifest_path = manifest_module.build_manifest(shots, tmp_path / "run")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    job = manifest["jobs"][0]
    assert manifest["schema_version"] == "dasheng.video.omni_shot_manifest.v1"
    assert validate_artifact("omni_shot_manifest", manifest) == []
    assert job["provider_order"][:3] == [
        "gemini_api_omni",
        "gemini_api_veo",
        "gemini_browser_omni",
    ]
    assert job["status"] == "pending_reference"

    Path(job["reference_image"]).write_bytes(b"png")
    manifest_module.refresh(manifest_path)
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["jobs"][0]["status"] == "ready_for_generation"

    manifest_module.record_attempt(
        manifest_path,
        "shot-01",
        "gemini_api_veo",
        "failed",
        error="timeout",
        operation_id="operations/123",
    )
    updated = json.loads(manifest_path.read_text(encoding="utf-8"))["jobs"][0]
    assert updated["attempts"][0]["error"] == "timeout"
    assert updated["attempts"][0]["operation_id"] == "operations/123"
    assert updated["status"] == "ready_for_generation"

    clip = tmp_path / "run" / "clips" / "shot-01.mp4"
    clip.write_bytes(b"video")
    manifest_module.record_attempt(
        manifest_path,
        "shot-01",
        "gemini_browser_omni",
        "succeeded",
        output=str(clip),
    )
    manifest_module.set_status(manifest_path, "shot-01", "approved")
    manifest_module.refresh(manifest_path)
    approved = json.loads(manifest_path.read_text(encoding="utf-8"))["jobs"][0]
    assert approved["status"] == "approved"
    assert approved["selected_provider"] == "gemini_browser_omni"


def test_gemini_api_dry_run_does_not_require_credentials(tmp_path):
    reference = tmp_path / "reference.png"
    output = tmp_path / "shot.mp4"
    result = api_module.generate(
        prompt="Locked paper collage shot",
        reference=reference,
        output=output,
        model="veo-3.1-generate-preview",
        duration=8,
        aspect_ratio="16:9",
        resolution="720p",
        poll_seconds=1,
        timeout_seconds=10,
        dry_run=True,
        final_duration=10,
        first_frame=tmp_path / "empty.png",
        last_frame=tmp_path / "reference.png",
    )
    assert result["duration_seconds"] == 8
    assert result["generate_audio"] is False
    assert result["final_duration_seconds"] == 10
    assert result["first_frame"].endswith("empty.png")
    assert result["last_frame"].endswith("reference.png")
    assert output.with_suffix(".request.json").exists()


def test_gemini_api_routes_omni_model_to_interactions(tmp_path):
    result = api_module.generate(
        prompt="Locked paper collage shot",
        reference=tmp_path / "reference.png",
        output=tmp_path / "shot.mp4",
        model="gemini-omni-flash-preview",
        duration=8,
        aspect_ratio="16:9",
        resolution="720p",
        poll_seconds=1,
        timeout_seconds=10,
        dry_run=True,
    )
    assert result["backend"] == "omni_interactions"
    assert result["duration_seconds"] == 8


def test_omni_accepts_ten_seconds_but_veo_does_not(tmp_path):
    omni = api_module.generate(
        prompt="Locked paper collage shot",
        reference=tmp_path / "reference.png",
        output=tmp_path / "omni.mp4",
        model="gemini-omni-flash-preview",
        duration=10,
        aspect_ratio="16:9",
        resolution="720p",
        poll_seconds=1,
        timeout_seconds=10,
        dry_run=True,
    )
    assert omni["duration_seconds"] == 10

    try:
        api_module.generate(
            prompt="Locked paper collage shot",
            reference=tmp_path / "reference.png",
            output=tmp_path / "veo.mp4",
            model="veo-3.1-generate-preview",
            duration=10,
            aspect_ratio="16:9",
            resolution="720p",
            poll_seconds=1,
            timeout_seconds=10,
            dry_run=True,
        )
    except ValueError as exc:
        assert "Veo duration" in str(exc)
    else:
        raise AssertionError("Veo duration validation should reject 10 seconds")
