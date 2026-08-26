import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from build_video_technical_site import build_html
from video_director_tool_router import (
    apply_routes_to_scene_plan,
    availability,
    build_stage_routes,
    load_director_registry,
    load_unified_registry,
    route_capability,
)
from video_pipeline_governance import validate_artifact


def sample_scene_plan(lane="explainer_html_video"):
    return {
        "schema_version": "dasheng.video.scene_plan.v1",
        "lane": lane,
        "aspect": "1:1",
        "scenes": [
            {
                "id": "scene_001",
                "title": "估值数据图表开场",
                "start_sec": 0,
                "end_sec": 6,
                "duration_sec": 6,
                "beat_class": "evidence_data",
                "template_id": "frame-data-chart-nyt",
                "html_animation_behavior": "animated chart and kinetic title",
            }
        ],
    }


def test_unified_registry_covers_all_reserved_projects_and_installed_skills():
    registry = load_unified_registry()
    expected_installed = {
        "video-use", "freecut", "video-wrapper", "claude-shorts",
        "remotion-video-skill", "remotion-video-toolkit", "cut-talking-head", "finish-talking-head",
        "gif-sticker-maker", "ian-xiaohei-illustrations", "video-frames", "reusable-footage-material",
        "remotion-best-practices", "animated-financial-display", "canvas-design", "algorithmic-art",
        "brand-guidelines", "animation-vocabulary", "apple-design", "emil-design-eng",
        "find-animation-opportunities", "improve-animations", "review-animations", "pick-ui-library",
        "seedance2-skill", "brandkit", "high-end-visual-design", "image-to-code", "minimalist-ui",
        "baoyu-imagine", "baoyu-cover-image", "baoyu-article-illustrator", "baoyu-infographic", "design-taste-frontend",
        "web-animation-design", "guizang-social-card-skill",
    }
    reserved = json.loads((PROJECT_ROOT / "configs/external/reserved_projects.json").read_text(encoding="utf-8"))
    assert len(registry["projects"]) == len(reserved["projects"])
    assert len(registry["reserve_candidates"]) == 4
    tool_registry = json.loads((PROJECT_ROOT / "configs/video/tool_registry.json").read_text(encoding="utf-8"))
    assert len(registry["skills"]) == len(tool_registry["skills"])
    assert len(registry["tools"]) == len(tool_registry["tools"])
    assert expected_installed <= {skill["name"] for skill in registry["skills"]}
    upstream = json.loads((PROJECT_ROOT / "configs/video/upstream_video_skills.json").read_text(encoding="utf-8"))
    assert len(registry["upstream_records"]) == len(upstream["repositories"])
    assert all(project["capabilities"] for project in registry["projects"])
    assert all(skill["capabilities"] for skill in registry["skills"])


def test_official_model_projects_are_retained_and_app_or_third_party_projects_are_absent():
    registry = load_unified_registry()
    removed = {
        "voicebox",
        "vox-director",
        "palmier-pro",
        "scroll-world",
        "scientific-illustrator",
    }
    active_names = {entry["name"] for entry in registry["entries"]}
    retained = {
        "seedance2-skill",
        "claude-code-video-toolkit",
        "brandkit",
        "image-to-code",
        "baoyu-imagine",
        "baoyu-cover-image",
        "baoyu-article-illustrator",
        "baoyu-infographic",
    }

    assert removed.isdisjoint(active_names)
    assert retained <= active_names
    assert "needs_provider_keys" not in registry["routing_policy"]["blocked_status_tokens"]
    assert "needs_model_access" not in registry["routing_policy"]["blocked_status_tokens"]


def test_provider_policy_allows_first_party_model_keys_and_blocks_third_party_services():
    registry = load_unified_registry()
    policy = registry["routing_policy"]

    official = {
        "name": "gemini-visuals",
        "kind": "skill",
        "scope": "execution",
        "status": "needs_provider_keys",
        "provider_class": "first_party_model",
        "provider_family": "google",
        "allowed_providers": ["gemini"],
    }
    third_party = {
        "name": "openrouter-visuals",
        "kind": "skill",
        "scope": "execution",
        "status": "ready",
        "provider_class": "third_party_service",
        "provider_family": "openrouter",
    }
    desktop = {
        "name": "desktop-editor",
        "kind": "project",
        "scope": "execution",
        "status": "ready",
        "requires_desktop_app": True,
    }

    assert availability(official, policy)["state"] == "ready"
    assert availability(third_party, policy) == {"state": "blocked", "reason": "third_party_service_provider"}
    assert availability(desktop, policy) == {"state": "blocked", "reason": "additional_app_required"}


def test_allowlisted_generation_skills_do_not_advertise_blocked_providers():
    registry = load_unified_registry()
    policy = registry["routing_policy"]["provider_policy"]
    blocked = set(policy["blocked_third_party_service_providers"])
    generation_skills = [
        row
        for row in registry["skills"]
        if row.get("provider_class") == "first_party_model"
    ]

    assert generation_skills
    assert all(not (set(row.get("allowed_providers") or []) & blocked) for row in generation_skills)


def test_explainer_scene_gets_primary_and_fallback_tool_stacks():
    routed, routing_plan = apply_routes_to_scene_plan(sample_scene_plan())
    route = routed["scenes"][0]["tool_routing"]

    assert "dynamic_chart" in route["required_capabilities"]
    assert "html_video" in route["required_capabilities"]
    assert route["primary_stack"]
    assert route["fallback_stack"]
    assert route["unresolved_capabilities"] == []
    assert routing_plan["registry_summary"]["tools"] == len(load_unified_registry()["tools"])
    assert routing_plan["registry_summary"]["skills"] == len(load_unified_registry()["skills"])
    assert routing_plan["registry_summary"]["projects"] == len(load_unified_registry()["projects"])
    assert routing_plan["registry_summary"]["reserve_candidates"] == 4
    assert routing_plan["registry_summary"]["rejected_projects"] == 13
    assert routing_plan["registry_summary"]["upstream_records"] == len(load_unified_registry()["upstream_records"])
    assert validate_artifact("scene_plan", routed) == []
    assert validate_artifact("tool_routing_plan", routing_plan) == []


def test_lane_stage_routes_do_not_force_talking_head_roughcut_on_explainer():
    registry = load_unified_registry()
    explainer = build_stage_routes(registry, lane="explainer_html_video")
    vox = build_stage_routes(registry, lane="vox_explainer_video")
    talking_head = build_stage_routes(registry, lane="talking_head_video")

    assert "roughcut" not in explainer
    assert "roughcut" not in vox
    assert vox["scene_design"]["primary_stack"]
    assert "roughcut" in talking_head
    assert talking_head["roughcut"]["primary_stack"]


def test_all_directors_route_active_capabilities_and_defer_only_cinematic_generation():
    registry = load_unified_registry()
    director_registry = json.loads((PROJECT_ROOT / "configs/video/director_registry.json").read_text(encoding="utf-8"))
    profiles = {row["lane"]: row for row in director_registry["directors"]}

    for lane in ["talking_head_video", "explainer_html_video", "vox_explainer_video", "digital_human_video", "commercial_promo_video"]:
        stages = build_stage_routes(registry, lane=lane, director_profile=profiles[lane])
        assert not {cap for stage in stages.values() for cap in stage["unresolved_capabilities"]}
        assert not {cap for stage in stages.values() for cap in stage["blocked_capabilities"]}

    cinematic = build_stage_routes(
        registry,
        lane="cinematic_short_drama_video",
        director_profile=profiles["cinematic_short_drama_video"],
    )
    blocked = {cap for stage in cinematic.values() for cap in stage["blocked_capabilities"]}
    assert blocked == {"external_video_generation"}
    assert cinematic["script_rewrite"]["primary_stack"]
    assert cinematic["scene_plan"]["primary_stack"]


def test_director_registry_loads_in_canonical_six_pipeline_order():
    assert [row["lane"] for row in load_director_registry()["directors"]] == [
        "talking_head_video",
        "vox_explainer_video",
        "explainer_html_video",
        "digital_human_video",
        "cinematic_short_drama_video",
        "commercial_promo_video",
    ]


def test_removed_external_entries_and_reference_only_entries_cannot_route():
    registry = load_unified_registry()

    collage = route_capability(registry, "editorial_collage", lane="explainer_html_video")
    assert collage["primary"]
    assert all(item["name"] != "vox-director" for item in [collage["primary"], *collage["fallbacks"], *collage["blocked"]])

    audio = route_capability(registry, "audio_mastering", lane="talking_head_video")
    assert audio["primary"]
    assert audio["primary"]["name"] == "dasheng_ffmpeg_toolkit"
    assert all(item["name"] != "talking-head-editor" for item in [audio["primary"], *audio["fallbacks"]])


def test_technical_site_contains_all_catalog_kinds_and_route_sections():
    registry = load_unified_registry()
    output = build_html(registry)

    assert "视频导演技术注册站" in output
    assert f"{len(registry['projects'])}</b>项目" in output
    assert 'data-kind="tool"' in output
    assert 'data-kind="skill"' in output
    assert 'data-kind="project"' in output
    assert 'data-kind="reserve"' in output
    assert 'data-kind="candidate"' in output
    assert "高分自媒体创作备选" in output
    assert "scientific-illustrator" not in output
    assert "humanizer-zh" in output
    assert "无头口播 / HTML 科普路由" in output
    assert "VOX 调查解释路由" in output
    assert "真人口播路由" in output
    assert "AI 数字人口播 / 双人访谈路由" in output
    assert "广告宣传片路由" in output
    assert "广告宣传片导演" in output
    assert output.index("电影短剧路由（Deferred）") < output.index("广告宣传片路由")


def test_voicebox_is_not_registered_as_a_tts_fallback():
    registry = load_unified_registry()
    route = route_capability(registry, "tts", lane="explainer_html_video")

    assert route["primary"]
    assert all(item["name"] != "voicebox" for item in [route["primary"], *route["fallbacks"], *route["blocked"]])


def test_project_capability_index_exactly_matches_project_registry():
    payload = json.loads((PROJECT_ROOT / "configs" / "external" / "reserved_projects.json").read_text(encoding="utf-8"))
    projects = {project["name"] for project in payload["projects"]}
    assert set(payload["project_capability_index"]) == projects


def test_reserve_candidates_are_visible_but_never_primary():
    registry = load_unified_registry()
    reserve_names = {item["name"] for item in registry["reserve_candidates"]}
    assert reserve_names == {"video-shotcraft", "gsap-skills", "impeccable", "video-autopilot-kit"}

    route = route_capability(registry, "gsap_motion", lane="explainer_html_video")
    assert route["primary"]
    assert route["primary"]["name"] != "gsap-skills"
    gsap_reserve = next(item for item in registry["reserve_candidates"] if item["name"] == "gsap-skills")
    assert availability(gsap_reserve)["state"] == "fallback"

    batch_route = route_capability(registry, "batch_video_production", lane="talking_head_video")
    assert any(item["name"] == "video-autopilot-kit" for item in batch_route["blocked"])
