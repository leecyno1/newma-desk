from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "configs/workflow/stage_reserve_registry.json"
PROJECT_REGISTRY_PATH = ROOT / "configs/external/reserved_projects.json"
MODULE_REGISTRY_PATH = ROOT / "configs/workflow/module_registry.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def rows_by_project(registry: dict) -> dict[str, list[tuple[str, dict]]]:
    result: dict[str, list[tuple[str, dict]]] = {}
    for stage, rows in registry["stages"].items():
        for row in rows:
            result.setdefault(row["project"], []).append((stage, row))
    return result


def test_all_requested_and_restored_projects_are_registered_against_valid_mainline_stages():
    registry = load(REGISTRY_PATH)
    module_registry = load(MODULE_REGISTRY_PATH)
    valid_stages = {stage["id"] for stage in module_registry["stages"]}
    requested = {
        "taste-skill",
        "impeccable",
        "video-shotcraft",
        "governed-dcf-skill",
        "video-autopilot-kit",
        "gsap-skills",
        "baoyu-skills",
        "minimax-skills",
        "seedance2-skill",
        "claude-code-video-toolkit",
    }

    assert set(registry["valid_stages"]) == valid_stages
    assert set(registry["stages"]) == valid_stages
    assert requested <= set(rows_by_project(registry))
    assert module_registry["workflow_registries"]["stage_reserves"] == "configs/workflow/stage_reserve_registry.json"


def test_stage_reserve_statuses_preserve_promotion_and_license_guards():
    registry = load(REGISTRY_PATH)
    projects = rows_by_project(registry)

    assert {row["availability"] for _, row in projects["taste-skill"]} == {"ready"}
    assert {row["availability"] for _, row in projects["video-autopilot-kit"]} == {"blocked"}
    assert all(row["execution_mode"] == "reference_only" for _, row in projects["governed-dcf-skill"])
    assert all(row["clone_allowed"] is False for _, row in projects["governed-dcf-skill"])
    assert all(row["license_status"] == "missing" for _, row in projects["governed-dcf-skill"])


def test_gsap_uses_one_suite_entry_with_eight_subskills():
    registry = load(REGISTRY_PATH)
    gsap_rows = rows_by_project(registry)["gsap-skills"]
    assert len(gsap_rows) == 1
    assert gsap_rows[0][1]["execution_mode"] == "suite_router"
    assert gsap_rows[0][1]["suite_skills"] == [
        "gsap-core",
        "gsap-frameworks",
        "gsap-performance",
        "gsap-plugins",
        "gsap-react",
        "gsap-scrolltrigger",
        "gsap-timeline",
        "gsap-utils",
    ]


def test_transwrite_keeps_official_model_routes_and_excludes_third_party_services():
    registry = load(REGISTRY_PATH)
    rows = {row["project"]: row for row in registry["stages"]["transwrite"]}

    assert {"baoyu-skills", "minimax-skills", "seedance2-skill", "claude-code-video-toolkit"} <= set(rows)
    assert rows["baoyu-skills"]["availability"] == "ready"
    assert {"openai", "gemini", "minimax", "jimeng", "seedream"} <= set(rows["baoyu-skills"]["allowed_providers"])
    assert {"openrouter", "replicate"} <= set(rows["baoyu-skills"]["blocked_providers"])
    assert rows["seedance2-skill"]["availability"] == "ready"
    assert set(rows["claude-code-video-toolkit"]["excluded_routes"]) == {
        "modal",
        "runpod",
        "elevenlabs",
        "cloudflare_r2",
    }


def test_local_clone_state_matches_registry_policy():
    stage_registry = load(REGISTRY_PATH)
    project_registry = load(PROJECT_REGISTRY_PATH)
    retained = {row["name"]: row for row in project_registry["projects"]}
    candidates = {row["name"]: row for row in project_registry["reserve_candidates"]}

    assert (ROOT / retained["taste-skill"]["local_path"]).is_dir()
    for name in ("impeccable", "video-shotcraft", "video-autopilot-kit", "gsap-skills"):
        assert (ROOT / candidates[name]["local_path"]).is_dir()
    for name in ("baoyu-skills", "minimax-skills", "seedance2-skill", "claude-code-video-toolkit"):
        assert (ROOT / retained[name]["local_path"]).is_dir()

    governed_rows = rows_by_project(stage_registry)["governed-dcf-skill"]
    assert not (ROOT / "vendor/reserved/finance/governed-dcf-skill").exists()
    assert all(row["clone_allowed"] is False for _, row in governed_rows)


def test_postmortem_reserves_cover_metrics_competitors_and_comment_analysis():
    registry = load(REGISTRY_PATH)
    rows = {row["project"]: row for row in registry["stages"]["postmortem"]}

    assert {
        "opencli",
        "postiz",
        "mixpost",
        "xhs-downloader",
        "4cat",
        "minet",
        "tiktok-api",
        "twscrape",
        "youtube-operational-api",
        "bertopic",
        "wechatpy",
        "mediacrawler",
        "yt-dlp",
        "pyabsa",
        "dowhy",
    } <= set(rows)
    assert rows["opencli"]["availability"] == "ready"
    assert rows["4cat"]["target_node"] == "postmortem.competitor_benchmark"
    assert rows["bertopic"]["target_node"] == "postmortem.performance_analysis"
    assert rows["wechatpy"]["target_node"] == "postmortem.metrics_collect"
    assert rows["mediacrawler"]["target_node"] == "postmortem.competitor_benchmark"
    assert rows["dowhy"]["availability"] == "blocked"
