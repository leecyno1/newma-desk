import json
from pathlib import Path

import pytest

from vibe_visualization_api.schema_validation import JsonContractError, validate_json_contract


ROOT = Path(__file__).resolve().parents[4]


@pytest.mark.parametrize("path", [
    "integrations/instock-analysis/data-service.json",
    "bundled-runtimes/instock-analysis/integrations/newma-desk/data-service.json",
    "bundled-runtimes/instock-analysis/integrations/vibedesk/data-service.json",
])
def test_sleeve_input_and_diagnostic_ready_output_cross_registered_contract(path):
    capability = json.loads((ROOT / path).read_text())["capabilities"]["analysis.strategy-validation"]
    packet = {"schema_version": "instock-strategy-validation-packet-v1",
              "strategy": {"id": "test", "source_module": "rotation"},
              "as_of": "2026-01-19", "benchmark": "510300", "holding_period_sessions": 2,
              "cost_bps_per_side": 25, "capital_model": {"mode": "fixed_sleeves", "slots": 2},
              "signals": [{"decision_date": "2026-01-02", "symbols": ["000001"]},
                          {"decision_date": "2026-01-06", "symbols": ["000002"]}]}
    validate_json_contract(capability["inputSchema"], packet, direction="input")
    with pytest.raises(JsonContractError):
        validate_json_contract(capability["inputSchema"], {**packet, "capital_model": {"mode": "fixed_sleeves", "slots": 0}}, direction="input")
    result = {"ok": True, "data": {"engine": {}, "strategy": packet["strategy"],
              "as_of": packet["as_of"], "benchmark": "510300", "rules": {}, "coverage": {},
              "train": {}, "out_of_sample": {}, "trades": [], "failures": [], "limitations": [],
              "verdict": "diagnostic_ready", "data_source": "fixture",
              "capital_backtest": {"mode": "fixed_sleeves", "slots": 2},
              "snapshot": {"schema_version": "test", "snapshot_id": "test", "analysis": {},
                           "data_window": {}, "provenance": {}, "freshness": {}, "input": {}, "result": {}}},
              "meta": {"api_version": "1.0", "request_id": "test"}}
    validate_json_contract(capability["outputSchema"], result, direction="output")
