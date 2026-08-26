import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from video_scene_plan_quality_gate import audit_scene_plan


def test_explainer_timeline_is_audited_instead_of_passing_empty():
    timeline = {
        "schema_version": "dasheng.html_anything_video_timeline.v1",
        "timeline": [
            {
                "id": "scene_001",
                "start_sec": 0,
                "end_sec": 8,
                "duration_sec": 8,
                "beat_class": "evidence_data",
                "content_part": "data_chart",
                "motion_policy": {"animation": "gsap_chart_reveal"},
            },
            {
                "id": "scene_002",
                "start_sec": 8,
                "end_sec": 16,
                "duration_sec": 8,
                "beat_class": "claim",
                "content_part": "chapter_divider",
                "motion_policy": {"animation": "gsap_title_reveal"},
            },
        ],
    }

    report = audit_scene_plan(timeline)

    assert report["lane"] == "explainer_html_video"
    assert report["metrics"]["scene_count"] == 2
    assert report["metrics"]["duration_sec"] == 16


def test_explainer_v2_counts_internal_micro_shots_for_visual_density():
    timeline = {
        "schema_version": "dasheng.html_anything_video_timeline.v2",
        "timeline": [
            {
                "id": f"scene_{index:03d}",
                "start_sec": index * 12,
                "end_sec": (index + 1) * 12,
                "duration_sec": 12,
                "beat_class": "evidence_data",
                "motion_policy": {"animation": "one_time_chart_reveal"},
                "variables": {
                    "micro_shots": [
                        {"kind": "source_hold"},
                        {"kind": "dynamic_redraw"},
                        {"kind": "reading_hold"},
                    ]
                },
            }
            for index in range(4)
        ],
    }

    report = audit_scene_plan(timeline)

    assert report["status"] == "pass"
    assert report["lane"] == "explainer_html_video"
    assert report["metrics"]["scene_count"] == 4
    assert report["metrics"]["effective_visual_count"] == 12
    assert report["metrics"]["effective_visual_changes_per_min"] == 15.0


def test_explainer_rejects_third_party_rewrite_framing() -> None:
    timeline = {
        "schema_version": "dasheng.html_anything_video_timeline.v2",
        "timeline": [
            {
                "id": "scene_001",
                "start_sec": 0,
                "end_sec": 8,
                "duration_sec": 8,
                "beat_class": "evidence_data",
                "narration_tts": "原文提到，韩国股市已经多次熔断。",
                "motion_policy": {"animation": "one_time_chart_reveal"},
                "micro_shots": [{"kind": "axis"}, {"kind": "series"}],
            }
        ],
    }

    report = audit_scene_plan(timeline)

    assert "third_party_rewrite_framing" in {item["code"] for item in report["failures"]}


def test_explainer_rejects_original_chart_repeated_after_dynamic_reconstruction() -> None:
    timeline = {
        "schema_version": "dasheng.html_anything_video_timeline.v2",
        "timeline": [
            {
                "id": "scene_001",
                "start_sec": 0,
                "end_sec": 8,
                "duration_sec": 8,
                "beat_class": "evidence_data",
                "chart_render_mode": "dynamic_reconstruction",
                "source_chart_image_visible": True,
                "motion_policy": {"animation": "one_time_chart_reveal"},
                "micro_shots": [{"kind": "axis"}, {"kind": "series"}],
            }
        ],
    }

    report = audit_scene_plan(timeline)

    assert "duplicate_source_chart_after_reconstruction" in {item["code"] for item in report["failures"]}


def base_scene(scene_id: str, start: float, *, asset_id: str | None = None) -> dict:
    scene = {
        "id": scene_id,
        "title": scene_id,
        "start_sec": start,
        "end_sec": start + 3,
        "duration_sec": 3,
        "beat_class": "evidence_data",
        "speaker_state": "hidden",
        "material_state": "chart_fullscreen",
        "pip_shape": "none",
        "evidence_authenticity": "real_data",
        "html_animation_behavior": "axis_draw_then_series_reveal_with_key_annotation",
        "template_id": "frame-data-chart-nyt",
    }
    if asset_id:
        scene["evidence_asset_ids"] = [asset_id]
    return scene


def test_gate_rejects_global_time_scaling_after_discrete_roughcut():
    plan = {
        "schema_version": "dasheng.video.scene_plan.real_evidence_review.v1",
        "lane": "talking_head_video",
        "timeline_alignment": {"mode": "global_scale", "time_scale": 0.91},
        "scenes": [base_scene("s1", 0, asset_id="chart-a")],
    }

    report = audit_scene_plan(plan)

    assert report["status"] == "fail"
    assert "global_time_scale_after_roughcut" in {item["code"] for item in report["failures"]}


def test_bound_evidence_plan_requires_claim_relation_and_source_locator():
    plan = {
        "schema_version": "dasheng.video.scene_plan.real_evidence_review.v1",
        "lane": "talking_head_video",
        "timeline_alignment": {"mode": "roughcut_edl", "dropped_scene_count": 0},
        "scenes": [base_scene("s1", 0, asset_id="chart-a")],
    }

    report = audit_scene_plan(plan)

    assert report["status"] == "fail"
    assert "evidence_binding_incomplete" in {item["code"] for item in report["failures"]}


def test_bound_evidence_plan_rejects_one_asset_used_as_many_distinct_claims():
    scenes = []
    for index in range(5):
        scene = base_scene(f"s{index}", index * 3, asset_id="same-chart")
        scene["evidence_binding"] = {
            "claim_id": f"claim-{index}",
            "relation": "direct",
            "source_locator": {"kind": "data_series", "value": f"series-{index}"},
        }
        scenes.append(scene)
    plan = {
        "schema_version": "dasheng.video.scene_plan.real_evidence_review.v1",
        "lane": "talking_head_video",
        "timeline_alignment": {"mode": "roughcut_edl", "dropped_scene_count": 0},
        "scenes": scenes,
    }

    report = audit_scene_plan(plan)

    assert report["status"] == "fail"
    assert "evidence_asset_overused" in {item["code"] for item in report["failures"]}
