from __future__ import annotations

import json
from unittest.mock import patch

import pandas as pd
import pytest
import tornado.web
from tornado.testing import AsyncHTTPTestCase

from instock.core.analysis_snapshot import get_analysis_snapshot_registry
from instock.core.validation.strategy_validation import (
    StrategyValidationEngine,
    StrategyValidationError,
)
from instock.web import strategy_validation_handler
from instock.web.strategy_validation_handler import StrategyValidationHandler


def _frame(symbol: str, opens: list[float]) -> pd.DataFrame:
    dates = pd.bdate_range("2026-01-02", periods=len(opens))
    frame = pd.DataFrame({
        "date": dates,
        "open": opens,
        "high": [value * 1.02 for value in opens],
        "low": [value * 0.98 for value in opens],
        "close": [value * 1.01 for value in opens],
        "volume": [1_000_000] * len(opens),
        "amount": [10_000_000] * len(opens),
        "symbol": [symbol] * len(opens),
    })
    frame.attrs.update({"data_source": "fixture-desk", "adjust": "qfq"})
    return frame


class ValidationFixtureProvider:
    name = "fixture-desk"

    def __init__(self):
        self.frames = {
            "000001": _frame("000001", [10, 10, 10.5, 11, 11.5, 12, 12.5, 13, 13.5, 14, 14.5, 15]),
            "000002": _frame("000002", [20, 20, 19.5, 20, 20.5, 21, 21.5, 22, 22.5, 23, 23.5, 24]),
            "510300": _frame("510300", [4, 4, 4.04, 4.08, 4.12, 4.16, 4.20, 4.24, 4.28, 4.32, 4.36, 4.40]),
        }

    def get_kline(self, symbol, period="daily", limit=800, as_of=None):
        frame = self.frames[symbol].copy()
        if as_of:
            frame = frame[frame["date"] <= pd.Timestamp(as_of)].copy()
        return frame.tail(limit).reset_index(drop=True)


def _packet():
    return {
        "schema_version": "instock-strategy-validation-packet-v1",
        "strategy": {"id": "candidate-demo", "name": "候选验证", "source_module": "stock-candidates"},
        "as_of": "2026-01-19",
        "benchmark": "510300",
        "holding_period_sessions": 2,
        "cost_bps_per_side": 25,
        "signals": [
            {"decision_date": "2026-01-02", "symbols": ["000001"]},
            {"decision_date": "2026-01-06", "symbols": ["000001", "000002"]},
            {"decision_date": "2026-01-08", "symbols": ["000002"]},
            {"decision_date": "2026-01-12", "symbols": ["000001"]},
        ],
    }


def test_strategy_validation_uses_next_session_open_costs_and_time_split():
    get_analysis_snapshot_registry().clear()
    result = StrategyValidationEngine(ValidationFixtureProvider()).validate(_packet())

    assert result["engine"]["name"] == "instock-strategy-validation"
    assert result["rules"] == {
        "signal_timing": "decision_date_close",
        "execution_timing": "next_trading_session_open",
        "holding_period_sessions": 2,
        "cost_bps_per_side": 25,
        "portfolio_weighting": "equal_weight",
        "split_method": "chronological_65_35",
    }
    assert result["trades"][0]["entry_date"] == "2026-01-05"
    assert result["trades"][0]["exit_date"] == "2026-01-07"
    assert result["trades"][0]["gross_return_pct"] == 10.0
    assert result["trades"][0]["net_return_pct"] == 9.5
    assert result["train"]["trades"] == 2
    assert result["out_of_sample"]["trades"] == 2
    assert result["coverage"]["executed_signals"] == 4
    assert result["snapshot"]["snapshot_id"].startswith("instock-strategy-validation:")
    assert get_analysis_snapshot_registry().get(result["snapshot"]["snapshot_id"]) is not None


def test_strategy_validation_rejects_non_point_in_time_or_duplicate_signals():
    packet = _packet()
    packet["signals"][1]["decision_date"] = packet["signals"][0]["decision_date"]
    with pytest.raises(StrategyValidationError, match="决策日期必须严格递增"):
        StrategyValidationEngine(ValidationFixtureProvider()).validate(packet)

    packet = _packet()
    packet["signals"][-1]["decision_date"] = "2026-01-20"
    with pytest.raises(StrategyValidationError, match="不能晚于 as_of"):
        StrategyValidationEngine(ValidationFixtureProvider()).validate(packet)


class StrategyValidationHandlerTest(AsyncHTTPTestCase):
    def get_app(self):
        return tornado.web.Application([
            (r"/api/v1/strategy-validations", StrategyValidationHandler),
        ])

    def setUp(self):
        self.provider_patch = patch.object(
            strategy_validation_handler,
            "get_market_data_provider",
            return_value=ValidationFixtureProvider(),
        )
        self.provider_patch.start()
        super().setUp()

    def tearDown(self):
        super().tearDown()
        self.provider_patch.stop()

    def test_post_returns_validation_result(self):
        response = self.fetch(
            "/api/v1/strategy-validations",
            method="POST",
            headers={"Content-Type": "application/json"},
            body=json.dumps(_packet()),
        )
        payload = json.loads(response.body)

        assert response.code == 200
        assert payload["ok"] is True
        assert payload["data"]["strategy"]["source_module"] == "stock-candidates"

    def test_post_rejects_invalid_json(self):
        response = self.fetch(
            "/api/v1/strategy-validations",
            method="POST",
            body="{broken",
            raise_error=False,
        )
        assert response.code == 400
        assert json.loads(response.body)["error"]["code"] == "invalid_json"
