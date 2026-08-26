import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from video_pipeline_governance import validate_artifact  # noqa: E402
from video_vox_omni_pack import build_packet, refresh  # noqa: E402


def test_builds_one_ten_second_omni_job_per_director_shot(tmp_path):
    source = tmp_path / "shots.json"
    source.write_text(
        json.dumps(
            {
                "shots": [
                    {
                        "id": "shot-01",
                        "start_sec": 0,
                        "end_sec": 9.5,
                        "narration": "黄金定价权正在换手。",
                        "visual_thesis": "旧定价框架裂开",
                        "composition": "黄金在中央，美元旋钮与三类买家环绕",
                        "assembly_order": ["美元旋钮滑入左侧", "黄金底座落到中央", "三类买家从右侧展开"],
                        "motion_beats": ["美元旋钮轻微转动", "黄金底座短促上弹", "三类买家依次轻微前探"],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    manifest_path = build_packet(source, tmp_path / "omni")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    job = manifest["jobs"][0]

    assert manifest["provider"] == "google_gemini_omni_signed_in_chrome"
    assert manifest["reference_image_provider"] == "codex_builtin_imagegen"
    assert manifest["video_provider"] == "google_gemini_omni_signed_in_chrome"
    assert manifest["workflow"] == [
        "director_shot",
        "codex_builtin_imagegen_reference",
        "gemini_omni_browser_video",
        "download",
        "remotion_edit",
    ]
    assert manifest["reference_contract"]["major_group_range"] == [4, 6]
    assert manifest["reference_contract"]["first_frame_policy"] == "assemble_to_reference"
    assert manifest["reference_contract"]["motion_policy"] == "named_groups_appear_once"
    assert job["reference_image_provider"] == "codex_builtin_imagegen"
    assert job["video_provider"] == "google_gemini_omni_signed_in_chrome"
    assert job["generation_duration_sec"] == 10
    assert job["status"] == "pending_reference"
    assert validate_artifact("omni_shot_manifest", manifest) == []
    omni_text = Path(job["omni_prompt_file"]).read_text(encoding="utf-8")
    image_text = Path(job["image_prompt_file"]).read_text(encoding="utf-8")
    assert "camera completely locked" in omni_text
    assert "exact target composition" in omni_text
    assert "appear exactly once" in omni_text
    assert "美元旋钮滑入左侧" in omni_text
    assert "no ticks, glyphs, signatures or fake markings" in omni_text
    assert "final second" in omni_text
    assert "four to six major movable groups" in image_text
    assert "No photorealistic 3D" in image_text

    Path(job["reference_image"]).write_bytes(b"png")
    refresh(manifest_path)
    refreshed = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert refreshed["jobs"][0]["status"] == "ready_for_omni"
