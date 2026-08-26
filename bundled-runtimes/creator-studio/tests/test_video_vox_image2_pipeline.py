import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from video_pipeline_governance import load_pipeline, validate_artifact  # noqa: E402
from video_vox_image2_pipeline import build_manifest, contact_sheet, crop_box, crop_existing, storyboard_review  # noqa: E402


def sample_plan() -> dict:
    return {
        "lane": "vox_explainer_video",
        "visual_bible": {
            "world": "a tactile paper evidence desk about gold repricing",
            "materials": ["torn newsprint", "cardboard", "red thread", "brushed gold"],
            "palette": {"ink": "#171411", "paper": "#E8D9BD", "signal": "#B9322A"},
        },
        "scenes": [
            {
                "id": "scene_001",
                "type": "cold_open",
                "title": "黄金定价权换手",
                "narration": "黄金冲过四千三百美元。央行、ETF和实物买家正在改变定价结构。",
                "start_sec": 0,
                "duration_sec": 9,
                "micro_shots": [
                    {"id": "scene_001_a", "action": "金库与金条建立空间", "shot_size": "EST_WIDE", "focus": {"x": 0.5, "y": 0.5}},
                    {"id": "scene_001_b", "action": "央行与ETF证据被红线连接", "shot_size": "MEDIUM", "subject_position": "left"},
                    {"id": "scene_001_c", "action": "实物需求落到金条细节", "shot_size": "DETAIL", "subject_position": "right"},
                ],
            }
        ],
    }


def test_manifest_builds_one_image2_job_per_micro_shot(tmp_path):
    manifest = build_manifest(sample_plan(), tmp_path)

    assert manifest["workflow"] == ["image2_prompt", "scene_still", "crop", "storyboard_review", "layer_decomposition", "layer_motion_design", "image_to_video", "remotion_composite"]
    assert manifest["reference_strategy"] == "generate_first_shot_then_lock_world"
    assert len(manifest["jobs"]) == 3
    assert manifest["jobs"][0]["style_reference_role"] == "creates_master"
    assert manifest["jobs"][1]["style_reference_role"] == "generated_master"
    assert manifest["jobs"][1]["depends_on"] == ["scene_001_a"]
    assert all(job["image_prompt"] and job["video_prompt"] and job["sound_cue"] for job in manifest["jobs"])
    assert all("exact text will be added in Remotion" in job["image_prompt"] for job in manifest["jobs"])
    assert all(job["layer_decomposition"]["minimum_layer_count"] >= 8 for job in manifest["jobs"])
    assert all(job["layer_decomposition"]["whole_scene_plate_role"] == "layout_reference_only" for job in manifest["jobs"])
    assert all(len(job["camera_keyframes"]) >= 2 for job in manifest["jobs"])
    assert validate_artifact("image2_shot_manifest", manifest) == []


def test_manifest_prefers_approved_director_shots(tmp_path):
    plan = sample_plan()
    plan["scenes"][0]["director_shots"] = [
        {
            "id": "scene_001_shot_01",
            "start_ratio": 0,
            "end_ratio": 1,
            "shot_size": "MEDIUM",
            "focus": {"x": 0.5, "y": 0.5},
            "visual_mechanism": "gold bars arrive, then evidence arrows connect",
            "assembly_order": ["gold bars arrive", "evidence arrows connect"],
            "camera_move": "slow push in",
        }
    ]

    manifest = build_manifest(plan, tmp_path)

    assert len(manifest["jobs"]) == 1
    assert manifest["jobs"][0]["shot_id"] == "scene_001_shot_01"
    assert "exact target composition" in manifest["jobs"][0]["video_prompt"]
    assert "Generated camera: locked" in manifest["jobs"][0]["video_prompt"]


def test_crop_outputs_all_aspects_and_real_shot_sizes(tmp_path):
    manifest = build_manifest(sample_plan(), tmp_path)
    first_job = manifest["jobs"][0]
    source_path = Path(first_job["source_image"])
    source_path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (2048, 1152), "#d6c29f")
    draw = ImageDraw.Draw(image)
    draw.rectangle((750, 260, 1298, 900), fill="#b28a2e")
    image.save(source_path)

    assert crop_existing(manifest) == 1
    assert Image.open(first_job["crop_outputs"]["16:9"]).size == (1920, 1080)
    assert Image.open(first_job["crop_outputs"]["1:1"]).size == (1080, 1080)
    assert Image.open(first_job["crop_outputs"]["9:16"]).size == (1080, 1920)

    wide_box = crop_box(2048, 1152, 16 / 9, 0.5, 0.5, 1.0)
    detail_box = crop_box(2048, 1152, 16 / 9, 0.5, 0.5, 0.5)
    assert detail_box[2] - detail_box[0] < wide_box[2] - wide_box[0]

    sheet = contact_sheet(manifest, tmp_path / "storyboard_contact_sheet.jpg")
    assert sheet and sheet.exists()
    assert manifest["review_assets"]["columns"] == ["SOURCE", "16:9", "1:1", "9:16"]
    review = storyboard_review(manifest, tmp_path / "storyboard_review.json")
    assert review.exists()
    assert manifest["review_assets"]["storyboard_review"] == str(review)
    assert validate_artifact("review", json.loads(review.read_text(encoding="utf-8"))) == []


def test_vox_pipeline_enforces_reference_frames_before_omni_generation():
    pipeline = load_pipeline("vox_explainer")
    stages = [stage["name"] for stage in pipeline["stages"]]

    assert stages.index("omni_reference_frames") < stages.index("reference_storyboard_review") < stages.index("shot_video_generation") < stages.index("edit_decisions")
    reference_stage = next(stage for stage in pipeline["stages"] if stage["name"] == "omni_reference_frames")
    generation_stage = next(stage for stage in pipeline["stages"] if stage["name"] == "shot_video_generation")
    assert "image2" in reference_stage["tools_available"]
    assert generation_stage["tools_available"][:2] == ["video_vox_omni_pack", "gemini_omni_browser"]
