import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "configs" / "video" / "reference_video_dna_registry.json"


def load_registry():
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def test_reference_video_dna_registry_has_unique_profiles():
    registry = load_registry()
    profiles = registry["profiles"]
    ids = [profile["id"] for profile in profiles]

    assert registry["schema_version"] == "dasheng.reference_video_dna_registry.v1"
    assert len(ids) == len(set(ids))
    assert "xhs_realestate_explainer_standard_20260712" in ids
    assert "xiaolin_latest_interview_20260703" in ids
    assert "wushi_finance_latest_20260701" in ids


def test_rolling_profiles_are_dated_and_scope_limited():
    registry = load_registry()
    rolling = [
        profile
        for profile in registry["profiles"]
        if profile.get("source_mode") == "creator_homepage_latest_at_checked_at"
    ]

    assert rolling
    for profile in rolling:
        assert profile["checked_at"]
        assert profile["creator_homepage"].startswith("https://")
        assert profile["scope"]
        assert profile["do_not_copy"]


def test_curated_profiles_stay_outside_repo():
    registry = load_registry()
    curated = [profile for profile in registry["profiles"] if profile.get("profile")]

    assert curated
    for profile in curated:
        assert profile["profile"].startswith("~/Desktop/自媒体创作/")
        assert "/skills/" not in profile["profile"]
        assert profile["training_dir"].startswith("~/Desktop/自媒体创作/")
