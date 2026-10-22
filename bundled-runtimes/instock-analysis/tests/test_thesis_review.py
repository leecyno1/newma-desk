from copy import deepcopy

import pytest

from instock.core.research.thesis_review import review_thesis, summarize_reviews
from instock.core.research.research_book import ResearchBookEngine
from test_research_book import _packet, _register_fixture_snapshot


def observation():
    return {"symbol": "300502", "target_weight_pct": 25, "thesis": "交付改善，继续观察", "invalidation": ["订单持续下降"],
            "snapshot_references": [{"snapshot_id": "dossier:old", "state": "resolved", "as_of": "2026-01-01",
                "analysis": {"name": "instock-stock-research-dossier"}, "source_coverage": "complete",
                "research_details_complete": True,
                "research": {"conclusion": "交付改善，继续观察", "invalidation_conditions": ["订单持续下降"], "gaps": []}}]}


def test_text_alignment_does_not_certify_thesis_or_evaluate_conditions():
    item = observation()
    item["thesis"] = "  交付改善，继续观察\n"
    output = review_thesis(item, "2026-01-01")
    assert output["state"] == "text_aligned"
    assert output["reasons"] == []
    assert output["condition_evaluation"] == "not_evaluated"
    assert output["comparisons"][0]["calendar_age_days"] == 0


def test_changed_thesis_and_missing_conditions_keep_exact_source_and_do_not_mutate_input():
    item = observation()
    item["thesis"] = "订单可能转弱"
    item["invalidation"] = ["订单下滑"]  # Could mean the same thing; never claim semantic conflict.
    before = deepcopy(item)
    output = review_thesis(item, "2026-01-02")
    assert [r["code"] for r in output["reasons"]] == ["thesis_text_differs", "invalidation_not_carried"]
    assert output["reasons"][1]["conditions"] == ["订单持续下降"]
    assert output["comparisons"][0]["source_conclusion"] == before["snapshot_references"][0]["research"]["conclusion"]
    assert item == before


@pytest.mark.parametrize("cutoff,due", [("2026-03-31", False), ("2026-04-01", True)])
def test_quarterly_reminder_is_anchored_to_book_cutoff_not_today(cutoff, due):
    output = review_thesis(observation(), cutoff)
    assert any(r["code"] == "periodic_review_due" for r in output["reasons"]) is due
    assert output["condition_evaluation"] == "not_evaluated"


@pytest.mark.parametrize("state", ["missing", "after_cutoff", "security_mismatch", "market_mismatch", "scope_ambiguous"])
def test_unmatched_sources_never_enter_thesis_comparison(state):
    item = observation()
    item["snapshot_references"][0]["state"] = state
    output = review_thesis(item, "2026-01-02")
    assert output["comparisons"] == []
    assert [r["code"] for r in output["reasons"]] == ["reference_unavailable", "no_comparable_dossier"]


def test_incomplete_legacy_research_and_empty_conditions_are_not_certified():
    for change in (False, True):
        item = observation()
        ref = item["snapshot_references"][0]
        ref["research_details_complete"] = change
        if change: ref["research"]["invalidation_conditions"] = []
        output = review_thesis(item, "2026-01-02")
        assert output["comparisons"] == []
        assert output["reasons"][0]["code"] == "research_details_incomplete"


def test_two_explicit_source_versions_are_not_silently_overwritten_or_blended():
    item = observation()
    newer = deepcopy(item["snapshot_references"][0])
    newer.update(snapshot_id="dossier:new", as_of="2026-01-02")
    newer["research"]["conclusion"] = "交付暂缓，待核对订单"
    item["snapshot_references"].append(newer)
    output = review_thesis(item, "2026-01-03")
    assert [c["snapshot_id"] for c in output["comparisons"]] == ["dossier:old", "dossier:new"]
    assert [c["thesis_text_differs"] for c in output["comparisons"]] == [False, True]
    assert output["reasons"][0]["snapshot_id"] == "dossier:new"


def test_review_exposure_counts_each_observation_once_and_keeps_zero_weight_watchlist():
    item = observation()
    item["thesis"] = "不同的观察理由"
    item["invalidation"] = ["其他条件"]
    item["thesis_review"] = review_thesis(item, "2026-04-01")
    watch = {**observation(), "target_weight_pct": 0, "snapshot_references": []}
    watch["thesis_review"] = review_thesis(watch, "2026-04-01")
    result = summarize_reviews([item, watch])
    assert result["items_to_review"] == 2
    assert result["review_target_weight_pct"] == 25
    assert result["without_comparable_dossier"] == 1
    assert result["uncompared_target_weight_pct"] == 0


def test_engine_preserves_reference_match_but_distinguishes_needed_research_review():
    _register_fixture_snapshot()
    packet = _packet()
    packet["items"] = packet["items"][:1]
    result = ResearchBookEngine().analyze(packet)
    assert result["items"][0]["snapshot_coverage"] == "complete"
    assert result["data_state"] == "complete"
    assert result["items"][0]["thesis_review"]["state"] == "needs_review"
    assert result["review_summary"]["review_target_weight_pct"] == 25
    assert result["engine"]["version"] == "1.6.0"
