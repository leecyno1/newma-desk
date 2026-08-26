from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.research_c5_c7_asset_association import build_payload


def test_c5_c7_asset_association_is_research_only_and_objective() -> None:
    payload = build_payload()

    assert payload["meta"]["notCausalAttribution"] is True
    assert payload["meta"]["notAssetForecast"] is True
    assert set(payload["cycles"]) == {"C5", "C7"}
    for cycle_id, mapping in payload["cycles"].items():
        assert mapping["status"] == "research_association_only"
        assert mapping["summary"]["eligibleAssets"] >= 70
        assert mapping["summary"]["positiveOosR2"] > 0
        assert mapping["currentState"]["assetForecastStatus"] == "blocked"
        assert len(mapping["assets"]) == 98
        assert all("phaseStats" in asset for asset in mapping["assets"])
        assert "不是因果归因" in mapping["caveat"]
        if cycle_id == "C7":
            assert mapping["summary"]["positiveOosR2"] < 30
