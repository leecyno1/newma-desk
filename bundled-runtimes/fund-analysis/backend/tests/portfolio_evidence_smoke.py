"""Pure portfolio evidence checks; no database reads or writes."""
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from services.portfolio_service import PortfolioService


holdings = [{"wind_code": "A", "weight": 0.6}, {"wind_code": "B", "weight": 0.4}]
partial = [{"wind_code": "A", "weight": 1}, {"wind_code": "B", "weight": None}]
assert not PortfolioService._weight_summary(partial)["is_complete"]
assert PortfolioService._effective_weights(partial) == {"A": 0.5, "B": 0.5}
assert PortfolioService._effective_weights(holdings) == {"A": 0.6, "B": 0.4}

snapshots = {
    "A": {"quarter": "2026Q2", "descriptors": [{"factor": "BETA", "unit": "ratio", "exposure": 0}, {"factor": "SIZE", "unit": "log", "exposure": 2}]},
    "B": {"quarter": "2026Q1", "descriptors": [{"factor": "SIZE", "unit": "log", "exposure": 4}, {"factor": "BETA", "exposure": None}]},
    "C": {"quarter": "2026Q2", "descriptors": []},
}
service = PortfolioService(repo=object(), similarity_service=object(), style_repo=SimpleNamespace(get_latest_map=lambda codes: snapshots))
result = service._style_aggregate(["A", "B", "C"], {"A": 0.3, "B": 0.3, "C": 0.4})
assert result["coverage"] == 0.6  # An empty snapshot does not count as evidence.
beta, size = result["factors"]
assert beta["weighted_exposure"] == 0 and beta["coverage"] == 0.3
assert size["weighted_exposure"] == 1.8 and size["coverage"] == 0.6
assert size["quarters"] == ["2026Q1", "2026Q2"]
snapshots["B"]["descriptors"][0]["unit"] = "percent"
assert service._style_aggregate(["A", "B"], {"A": 0.6, "B": 0.4})["factors"][1]["weighted_exposure"] is None

portfolio = {"name": "isolated", "holdings": holdings, "targets": [{"peer_group_key": "group", "target_weight": 1}]}
service.get_portfolio = lambda _: portfolio
service._holding_peer_group = lambda _: "group"
service._peer_group_name = lambda _: "group"
drifts = {"A": {"status": "available", "level": "low", "previous_quarter": "2026Q1", "latest_quarter": "2026Q2"}, "B": {"status": "insufficient_evidence", "level": "unavailable"}}
with patch("services.holding_style_drift_service.HoldingStyleDriftService.get", side_effect=lambda code: drifts[code]):
    result = service.monitor("isolated")
    assert result["status"] == "partial" and result["rebalance_needed"] is False
    assert result["drift_coverage"] == {"assessed_count": 1, "total_count": 2, "missing_count": 1, "assessed_weight": 0.6}
    assert "不能判断为稳定" in result["summary"]
    assert result["style_drifts"][0]["latest_quarter"] == "2026Q2"
    portfolio["holdings"] = partial
    result = service.monitor("isolated")
    assert result["rebalance_needed"] is None and result["weights_basis"] == "equal_weight_assumption"
    portfolio["holdings"] = holdings
    service._holding_peer_group = lambda _: "unclassified"
    assert service.monitor("isolated")["rebalance_needed"] is None
    portfolio["targets"] = []
    assert service.monitor("isolated")["rebalance_needed"] is None

print("PASS portfolio weights, factor coverage/units, and incomplete monitoring evidence (isolated, no DB)")
