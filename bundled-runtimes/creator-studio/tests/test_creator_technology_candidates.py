from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "configs/workflow/creator_technology_candidates.json"
PROJECT_REGISTRY = ROOT / "configs/external/reserved_projects.json"
MODULE_REGISTRY = ROOT / "configs/workflow/module_registry.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_creator_candidates_are_high_scoring_unique_project_entries():
    payload = load(REGISTRY)
    rows = payload["candidates"]
    names = [row["name"] for row in rows]

    assert payload["summary"]["candidates"] == len(rows)
    assert len(names) == len(set(names))
    assert all(row["score"] >= payload["selection_policy"]["minimum_score"] for row in rows)
    assert all(row["route_stages"] for row in rows)
    assert all(row["capabilities"] for row in rows)


def test_rejected_creator_projects_are_not_registered():
    names = {row["name"] for row in load(REGISTRY)["candidates"]}

    assert "dbskill" not in names
    assert "workbuddy-xhs-skills" not in names
    assert "scientific-illustrator" not in names
    assert "scroll-world" not in names
    assert "baoyu-skills" in names


def test_baoyu_candidate_uses_only_approved_provider_routes():
    rows = {row["name"]: row for row in load(REGISTRY)["candidates"]}
    baoyu = rows["baoyu-skills"]

    assert {"openai", "google", "gemini", "minimax", "jimeng", "seedream"} <= set(baoyu["allowed_providers"])
    assert {"openrouter", "replicate"} <= set(baoyu["blocked_providers"])


def test_existing_candidate_paths_match_project_or_reserve_registry():
    candidates = load(REGISTRY)["candidates"]
    project_registry = load(PROJECT_REGISTRY)
    retained = {
        row["name"]: row
        for row in [
            *(project_registry.get("projects") or []),
            *(project_registry.get("reserve_candidates") or []),
        ]
    }

    for row in candidates:
        local_path = row.get("local_path")
        if not local_path:
            continue
        assert row["name"] in retained
        assert retained[row["name"]]["local_path"] == local_path


def test_module_registry_exposes_creator_candidate_registry():
    module_registry = load(MODULE_REGISTRY)
    assert module_registry["workflow_registries"]["creator_technology_candidates"] == (
        "configs/workflow/creator_technology_candidates.json"
    )
