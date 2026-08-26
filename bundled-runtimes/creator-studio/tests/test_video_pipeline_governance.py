import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from video_pipeline_governance import (  # noqa: E402
    ARTIFACT_SCHEMAS,
    build_checkpoint,
    load_pipeline,
    validate_artifact,
    validate_pipeline_manifest,
)
from video_tool_registry import (  # noqa: E402
    load_tool_registry,
    tool_index,
    tools_for_capability,
    unresolved_script_paths,
    unresolved_skill_paths,
    unresolved_project_paths,
)


def test_all_video_pipeline_manifests_validate():
    registry = load_tool_registry()
    for pipeline_path in sorted((PROJECT_ROOT / "configs" / "video" / "pipelines").glob("*.yaml")):
        report = validate_pipeline_manifest(load_pipeline(pipeline_path), registry=registry, project_root=PROJECT_ROOT)
        assert report["status"] == "pass", json.dumps(report, ensure_ascii=False, indent=2)
        assert report["stage_count"] >= 2
        assert report["stages"]


def test_tool_registry_resolves_script_paths_and_capabilities():
    registry = load_tool_registry()
    tools = tool_index(registry)

    assert "render_html_anything_scene_pack_animated" in tools
    assert "dasheng_video_director" in tools
    assert tools["dasheng_video_director"]["type"] == "script"
    assert "mmx_cli" in tools
    assert "jianying_cloud_draft" in tools
    assert tools_for_capability(registry, "live_html_animation_recording")
    assert tools_for_capability(registry, "director_scene_plan")
    assert tools_for_capability(registry, "claim_evidence_ledger")
    assert tools_for_capability(registry, "remotion_renderer_families")
    assert unresolved_script_paths(registry, project_root=PROJECT_ROOT) == []
    assert unresolved_skill_paths(registry, skills_dir=PROJECT_ROOT / "skills") == []
    assert unresolved_project_paths(registry, project_root=PROJECT_ROOT) == []
    assert len(registry["skills"]) >= 45


def test_pipeline_artifacts_have_schema_files():
    for artifact_type, schema_name in ARTIFACT_SCHEMAS.items():
        schema_path = PROJECT_ROOT / "configs" / "video" / "artifact_schemas" / schema_name
        assert schema_path.exists(), artifact_type
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        assert schema["title"]


def test_scene_plan_schema_accepts_director_scene_plan():
    artifact = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "explainer_html_video",
        "aspect": "16:9",
        "scenes": [
            {
                "id": "scene_001",
                "title": "开场反问",
                "start_sec": 0,
                "end_sec": 6,
                "duration_sec": 6,
                "beat_class": "hook",
                "template_id": "frame-glitch-title",
                "html_animation_behavior": "kinetic_title_reveal_then_exit",
                "transition_to_next": "impact_cut",
            }
        ],
    }

    assert validate_artifact("scene_plan", artifact) == []


def test_scene_plan_schema_rejects_missing_scene_timing():
    artifact = {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": "explainer_html_video",
        "scenes": [{"id": "scene_001", "title": "缺时间", "beat_class": "hook"}],
    }

    errors = validate_artifact("scene_plan", artifact)
    assert errors
    assert any("start_sec" in item["message"] for item in errors)


def test_commercial_script_schema_requires_commercial_contract():
    artifact = {
        "schema_version": "dasheng.video.script.v1",
        "title": "产品宣传片",
        "lane": "commercial_promo_video",
        "commercial": {
            "mode": "product_promo",
            "brand": "大圣",
            "product": "AI 内容生产系统",
            "audience": "财经内容创作者",
            "objective": "预约演示",
            "duration_sec": 30,
            "aspect": "9:16",
            "cta": "立即预约演示",
        },
        "core_claims": ["一份内容进入完整媒体流水线"],
        "retention_plan": {"hook_deadline_sec": 3},
        "segments": [{"id": "seg_01", "text": "先看结果。", "beat_class": "hook"}],
    }

    assert validate_artifact("script", artifact) == []
    del artifact["commercial"]
    assert validate_artifact("script", artifact)


def test_claim_evidence_ledger_schema_accepts_core_claim_contract():
    artifact = {
        "schema_version": "dasheng.video.claim_evidence_ledger.v1",
        "lane": "talking_head_video",
        "source_scene_plan": "/tmp/scene_plan.json",
        "target_claim_range": {"minimum": 1, "maximum": 12},
        "claims": [
            {
                "id": "claim_valuation",
                "order": 1,
                "title": "估值折价",
                "claim_text": "腾讯相对 Meta 存在可比估值折价。",
                "claim_type": "comparison",
                "scene_ids": ["s1", "s2"],
                "time_range": {"start_sec": 0, "end_sec": 6},
                "evidence_requirements": [
                    {"id": "pe", "description": "同口径 forward PE", "required": True}
                ],
                "evidence_items": [],
                "evidence_status": "missing_evidence",
                "disclosure_label": "",
                "evidence_gaps": ["缺少同口径估值数据"],
            }
        ],
    }

    assert validate_artifact("claim_evidence_ledger", artifact) == []


def test_renderer_asset_gate_schema_accepts_production_failure_report():
    artifact = {
        "schema_version": "dasheng.video.renderer_asset_gate.v1",
        "status": "fail",
        "render_mode": "production",
        "allow_placeholders": False,
        "failure_count": 1,
        "warning_count": 0,
        "failures": [
            {
                "code": "chart_data_missing",
                "scene_id": "scene_014",
                "message": "Production chart scene requires visual.series.",
            }
        ],
        "warnings": [],
    }

    assert validate_artifact("renderer_asset_gate", artifact) == []


def test_renderer_asset_gate_schema_rejects_pass_with_failures():
    artifact = {
        "schema_version": "dasheng.video.renderer_asset_gate.v1",
        "status": "pass",
        "render_mode": "production",
        "allow_placeholders": False,
        "failure_count": 1,
        "warning_count": 0,
        "failures": [{"code": "missing", "message": "Still missing."}],
        "warnings": [],
    }

    assert validate_artifact("renderer_asset_gate", artifact)


def test_checkpoint_exposes_review_gate_fields():
    pipeline = load_pipeline("explainer_html")
    checkpoint = build_checkpoint(
        pipeline,
        "scene_plan",
        artifact_paths={"script": "/tmp/script.json", "scene_plan": "/tmp/storyboard.json"},
        status="pending_review",
        notes="wait for user approval",
    )

    assert checkpoint["schema_version"] == "dasheng.video.pipeline_checkpoint.v1"
    assert checkpoint["pipeline_id"] == "explainer_html"
    assert checkpoint["checkpoint_required"] is True
    assert checkpoint["human_approval_default"] is True
    assert "review_focus" in checkpoint
    assert checkpoint["artifact_paths"]["scene_plan"] == "/tmp/storyboard.json"


def test_video_pipelines_keep_media_outputs_outside_repo_skills():
    for pipeline_id in ["talking_head", "explainer_html", "vox_explainer", "digital_human", "commercial_promo", "cinematic_short_drama", "style_training"]:
        pipeline = load_pipeline(pipeline_id)
        policy = pipeline["external_output_policy"]
        assert "自媒体创作" in policy["required_root"]
        assert any("skills" in item for item in policy["forbid_paths"])
        assert pipeline["fail_conditions"]


def test_scene_plan_stages_use_director_skill():
    talking_head = load_pipeline("talking_head")
    explainer = load_pipeline("explainer_html")
    vox = load_pipeline("vox_explainer")
    digital = load_pipeline("digital_human")
    cinematic = load_pipeline("cinematic_short_drama")
    talking_head_stages = {stage["name"]: stage for stage in talking_head["stages"]}
    explainer_stages = {stage["name"]: stage for stage in explainer["stages"]}
    vox_stages = {stage["name"]: stage for stage in vox["stages"]}
    digital_stages = {stage["name"]: stage for stage in digital["stages"]}
    cinematic_stages = {stage["name"]: stage for stage in cinematic["stages"]}

    assert talking_head_stages["scene_plan"]["skill"] == "dasheng-video-director"
    assert talking_head_stages["edit_decisions"]["skill"] == "dasheng-video-director"
    assert explainer_stages["scene_plan"]["skill"] == "dasheng-video-director"
    assert vox_stages["scene_plan"]["skill"] == "dasheng-video-director"
    assert digital_stages["scene_plan"]["skill"] == "dasheng-video-director"
    assert cinematic_stages["scene_plan"]["skill"] == "dasheng-video-director"


def test_talking_head_pipeline_gates_assets_on_claim_evidence_ledger():
    pipeline = load_pipeline("talking_head")
    stage_names = [stage["name"] for stage in pipeline["stages"]]
    stages = {stage["name"]: stage for stage in pipeline["stages"]}

    assert stage_names.index("scene_plan") < stage_names.index("claim_evidence") < stage_names.index("asset_build")
    assert stages["claim_evidence"]["produces"] == ["claim_evidence_ledger", "spoken_revision_sheet", "review"]
    assert "claim_evidence_ledger" in stages["asset_build"]["required_artifacts_in"]
    assert "build_remotion_renderer_pack" in stages["render_qc"]["tools_available"]
    assert "renderer_asset_gate" in stages["asset_build"]["produces"]
    assert "renderer_asset_gate" in stages["render_qc"]["required_artifacts_in"]
    assert any("placeholder" in item for item in pipeline["fail_conditions"])


def test_explainer_pipeline_uses_horizontal_default_and_full_gate_chain():
    pipeline = load_pipeline("explainer_html")
    stage_names = [stage["name"] for stage in pipeline["stages"]]
    stages = {stage["name"]: stage for stage in pipeline["stages"]}

    assert pipeline["default_format"]["aspect_ratio"] == "16:9"
    assert pipeline["default_format"]["width"] == 1920
    assert stage_names.index("scene_plan") < stage_names.index("claim_evidence") < stage_names.index("asset_build")
    assert "claim_evidence_ledger" in stages["asset_build"]["required_artifacts_in"]
    assert "renderer_asset_gate" in stages["render_qc"]["required_artifacts_in"]
    assert "build_remotion_renderer_pack" in stages["render_qc"]["tools_available"]
    assert any("final delivery manifest" in item for item in pipeline["fail_conditions"])


def test_vox_pipeline_is_independent_and_requires_counterargument():
    pipeline = load_pipeline("vox_explainer")
    stage_names = [stage["name"] for stage in pipeline["stages"]]
    stages = {stage["name"]: stage for stage in pipeline["stages"]}

    assert pipeline["lane"] == "vox_explainer_video"
    assert pipeline["default_format"]["aspect_ratio"] == "16:9"
    assert stage_names.index("scene_plan") < stage_names.index("claim_evidence") < stage_names.index("asset_build")
    assert stages["investigation_intake"]["skill"] == "dasheng-video-vox"
    assert stages["asset_build"]["skill"] == "dasheng-video-vox"
    assert any("counterargument" in item for item in pipeline["fail_conditions"])
    assert any("generated footage" in item for item in pipeline["fail_conditions"])


def test_new_video_pipelines_are_registered_with_correct_activation():
    digital = load_pipeline("digital_human")
    commercial = load_pipeline("commercial_promo")
    cinematic = load_pipeline("cinematic_short_drama")

    assert digital["lane"] == "digital_human_video"
    assert digital["director_id"] == "digital_human_director"
    assert set(digital["supported_modes"]) == {"single_presenter", "dual_interview"}
    assert commercial["lane"] == "commercial_promo_video"
    assert commercial["director_id"] == "commercial_promo_director"
    assert commercial["default_format"]["aspect_ratio"] == "9:16"
    assert commercial["default_format"]["width"] == 1080
    assert commercial["default_format"]["height"] == 1920
    assert set(commercial["supported_modes"]) == {"brand_film", "product_promo", "launch_trailer", "performance_ad"}
    assert cinematic["lane"] == "cinematic_short_drama_video"
    assert cinematic["director_id"] == "cinematic_short_drama_director"
    assert cinematic["execution_enabled"] is False


def test_director_registry_has_one_director_for_each_video_lane():
    payload = json.loads((PROJECT_ROOT / "configs/video/director_registry.json").read_text(encoding="utf-8"))
    directors = payload["directors"]
    assert len(directors) == 6
    assert {row["lane"] for row in directors} == {
        "talking_head_video",
        "explainer_html_video",
        "vox_explainer_video",
        "digital_human_video",
        "commercial_promo_video",
        "cinematic_short_drama_video",
    }
    assert len({row["id"] for row in directors}) == 6
    assert {row["lane"]: row["order"] for row in directors} == {
        "talking_head_video": 1,
        "vox_explainer_video": 2,
        "explainer_html_video": 3,
        "digital_human_video": 4,
        "cinematic_short_drama_video": 5,
        "commercial_promo_video": 6,
    }
    assert all(row["stage_capabilities"] and row["core_tools"] and row["hard_gates"] for row in directors)
