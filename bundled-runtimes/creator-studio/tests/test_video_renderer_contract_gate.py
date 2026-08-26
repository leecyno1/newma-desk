import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from video_renderer_contract_gate import audit_renderer_contract


REQUIRED_FIELDS = [
    "template_id",
    "speaker_state",
    "material_state",
    "pip_shape",
    "transition_in",
    "transition_out",
    "html_animation_behavior",
    "audio",
]


def plan(*templates: str) -> dict:
    scenes = []
    for index, template in enumerate(templates):
        scenes.append(
            {
                "id": f"s{index}",
                "template_id": template,
                "speaker_state": "hidden",
                "material_state": "chart_fullscreen",
                "pip_shape": "none",
                "transition_in": "data_reveal",
                "transition_out": "hard_cut",
                "html_animation_behavior": "axis_draw_then_series_reveal",
                "audio": {"duck_bgm": True},
            }
        )
    return {"lane": "talking_head_video", "scenes": scenes}


def test_renderer_contract_rejects_missing_template_implementation():
    contract = {"consumed_scene_fields": REQUIRED_FIELDS, "templates": {}}

    report = audit_renderer_contract(plan("frame-a"), contract)

    assert report["status"] == "fail"
    assert "template_renderer_missing" in {item["code"] for item in report["failures"]}


def test_renderer_contract_rejects_many_template_names_collapsed_to_one_variant():
    template_contract = {
        name: {
            "status": "implemented",
            "component": "GenericCard",
            "variant": "default",
            "motion_signature": "fade-rise",
        }
        for name in ["frame-a", "frame-b", "frame-c", "frame-d"]
    }
    contract = {"consumed_scene_fields": REQUIRED_FIELDS, "templates": template_contract}

    report = audit_renderer_contract(plan("frame-a", "frame-b", "frame-c", "frame-d"), contract)

    assert report["status"] == "fail"
    assert "template_alias_collapse" in {item["code"] for item in report["failures"]}


def test_renderer_contract_requires_director_fields_to_be_consumed():
    contract = {
        "consumed_scene_fields": ["template_id", "speaker_state"],
        "templates": {
            "frame-a": {
                "status": "implemented",
                "component": "Chart",
                "variant": "a",
                "motion_signature": "axis-series",
            }
        },
    }

    report = audit_renderer_contract(plan("frame-a"), contract)

    assert report["status"] == "fail"
    assert "director_fields_not_consumed" in {item["code"] for item in report["failures"]}


def test_renderer_contract_passes_with_real_variants_and_all_fields_consumed():
    contract = {
        "consumed_scene_fields": REQUIRED_FIELDS,
        "templates": {
            "frame-a": {
                "status": "implemented",
                "component": "Chart",
                "variant": "nyt-line",
                "motion_signature": "axis-series-annotation",
            },
            "frame-b": {
                "status": "implemented",
                "component": "Document",
                "variant": "source-crop",
                "motion_signature": "crop-marker-paragraph",
            },
        },
    }

    report = audit_renderer_contract(plan("frame-a", "frame-b"), contract)

    assert report["status"] == "pass"
