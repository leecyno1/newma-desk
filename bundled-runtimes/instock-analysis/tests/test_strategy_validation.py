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

    def get_trading_calendar(self, start, end):
        return {"status": "ready", "exchange": "SSE", "start": start, "end": end,
                "source": "independent-fixture", "receivedAt": "fixture",
                "sessions": pd.bdate_range(start, end).strftime("%Y-%m-%d").tolist()}


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
        "split_method": "original_signals_65_35_with_label_purge",
        "execution_calendar": "independent_exchange_calendar_exact_dates",
        "overlap_policy": "signal_diagnostics_only_no_portfolio_compounding",
        "idle_cash_return": 0.0,
    }
    assert result["trades"][0]["entry_date"] == "2026-01-05"
    assert result["trades"][0]["exit_date"] == "2026-01-07"
    assert result["trades"][0]["gross_return_pct"] == 10.0
    assert result["trades"][0]["net_return_pct"] == 9.5
    assert result["train"]["trades"] == 1
    assert result["out_of_sample"]["trades"] == 2
    assert result["validation_audit"]["split_decision_date"] == "2026-01-08"
    assert result["validation_audit"]["purged_decision_dates"] == ["2026-01-06"]
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


def test_saved_input_retains_failed_and_purged_signals_and_can_be_rerun():
    provider = ValidationFixtureProvider()
    provider.frames["000001"].loc[1, "open"] = None
    engine = StrategyValidationEngine(provider)
    packet = _packet()
    result = engine.validate(packet)
    assert result["coverage"]["failed_signals"] == 1
    assert result["input_packet"] == packet
    rerun = engine.validate(result["input_packet"])
    assert rerun["trades"] == result["trades"]
    assert rerun["validation_audit"] == result["validation_audit"]
    packet["signals"][0]["symbols"].append("000002")
    assert result["input_packet"]["signals"][0]["symbols"] == ["000001"]


@pytest.mark.parametrize("index,side,volume,reason", [
    (1, "buy", 0, "zero_volume"), (3, "sell", 0, "zero_volume"),
    (1, "buy", None, "missing_volume"), (3, "sell", float("inf"), "missing_volume"),
])
def test_price_without_volume_evidence_cannot_certify_trade(index, side, volume, reason):
    provider = ValidationFixtureProvider()
    provider.frames["000001"]["volume"] = provider.frames["000001"]["volume"].astype(float)
    provider.frames["000001"].loc[index, "volume"] = volume
    result = StrategyValidationEngine(provider).validate(_packet())
    first = result["trades"][0]
    assert first["execution_state"] == "unresolved"
    assert first["reason"] == "unverified_asset_volume"
    assert first["net_return_pct"] is None
    assert first["execution_issues"] == [{"symbol": "000001", "date": first["entry_date" if side == "buy" else "exit_date"],
                                          "side": side, "reason": reason}]
    audit = result["validation_audit"]["execution_evidence"]
    assert audit["planned_legs"] == audit["dated_legs"] == 10
    assert audit["price_volume_verified_legs"] + audit["zero_volume_legs"] + audit["missing_evidence_legs"] == 10
    assert audit["fill_guaranteed"] is False
    assert "historical_price_limits" in audit["unverified_checks"]
    assert result["validation_audit"]["split_decision_date"] == "2026-01-08"
    assert result["input_packet"] == _packet()
    json.dumps(result, allow_nan=False)


def test_unexpired_signal_still_audits_known_entry_without_future_volume():
    packet = _packet()
    packet["signals"][-1]["decision_date"] = "2026-01-16"
    result = StrategyValidationEngine(ValidationFixtureProvider()).validate(packet)
    audit = result["validation_audit"]["execution_evidence"]
    assert audit["planned_legs"] == 10
    assert audit["dated_legs"] == audit["price_volume_verified_legs"] == 9
    assert audit["pending_legs"] == 1
    assert result["trades"][-1]["reason"] == "holding_window_incomplete"


def test_strategy_validation_empty_oos_is_null_in_result_and_snapshot():
    packet = _packet()
    packet["signals"] = [
        {"decision_date": "2026-01-16", "symbols": ["000001"]},
        {"decision_date": "2026-01-19", "symbols": ["000001"]},
    ]
    result = StrategyValidationEngine(ValidationFixtureProvider()).validate(packet)
    assert result["coverage"]["executed_signals"] == 0
    assert result["out_of_sample"]["trades"] == 0
    assert result["out_of_sample"]["total_return_pct"] is None
    assert result["out_of_sample"]["max_drawdown_pct"] is None
    assert result["snapshot"]["result"]["summary"]["out_of_sample"]["total_return_pct"] is None
    assert result["verdict"] == "insufficient_evidence"
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("missing_date", ["2026-01-05", "2026-01-09", "2026-01-15"])
def test_missing_execution_retains_ledger_and_does_not_move_split(missing_date):
    provider = ValidationFixtureProvider()
    before = StrategyValidationEngine(provider).validate(_packet())
    for code in ("000001", "000002"):
        provider.frames[code].loc[provider.frames[code]["date"] == missing_date, "open"] = float("nan")
    result = StrategyValidationEngine(provider).validate(_packet())
    assert {k: v for k, v in result["validation_audit"].items() if k != "execution_evidence"} == {
        k: v for k, v in before["validation_audit"].items() if k != "execution_evidence"}
    assert result["validation_audit"]["execution_evidence"]["missing_evidence_legs"] > 0
    assert len(result["trades"]) == len(_packet()["signals"])
    assert result["coverage"]["failed_signals"] > 0
    assert result["verdict"] == "insufficient_evidence"
    for row, original in zip(result["trades"], before["trades"]):
        assert (row["entry_date"], row["exit_date"], row["partition"]) == (original["entry_date"], original["exit_date"], original["partition"])
    segment = result["train"] if missing_date == "2026-01-05" else result["out_of_sample"]
    assert segment["portfolio_state"] == "incomplete"
    assert segment["total_return_pct"] is None
    assert segment["max_drawdown_pct"] is None
    json.dumps(result, allow_nan=False)


def test_missing_interior_asset_bar_does_not_shift_exit_date():
    provider = ValidationFixtureProvider()
    frame = provider.frames["000001"]
    provider.frames["000001"] = frame[frame["date"] != "2026-01-06"]
    result = StrategyValidationEngine(provider).validate(_packet())
    first = result["trades"][0]
    assert first["entry_date"] == "2026-01-05"
    assert first["exit_date"] == "2026-01-07"
    assert first["net_return_pct"] == 9.5
    assert first["execution_state"] == "resolved"


def test_missing_entry_row_is_not_delayed_to_next_available_open():
    provider = ValidationFixtureProvider()
    frame = provider.frames["000001"]
    provider.frames["000001"] = frame[frame["date"] != "2026-01-05"]
    result = StrategyValidationEngine(provider).validate(_packet())
    assert result["trades"][0]["entry_date"] == "2026-01-05"
    assert result["trades"][0]["execution_state"] == "unresolved"
    assert result["trades"][0]["net_return_pct"] is None


def test_overlapping_signals_keep_individual_outcomes_but_no_portfolio_compound():
    packet = _packet()
    packet["holding_period_sessions"] = 4
    result = StrategyValidationEngine(ValidationFixtureProvider()).validate(packet)
    oos = result["out_of_sample"]
    assert oos["trades"] == 2
    assert oos["portfolio_state"] == "overlapping"
    assert oos["overlap_decision_dates"] == ["2026-01-12"]
    assert oos["total_return_pct"] is None
    assert oos["annualized_return_pct"] is None
    assert oos["max_drawdown_pct"] is None
    assert oos["signal_diagnostics"]["mean_return_pct"] is not None
    assert all(row["partition"] != "train" for row in result["trades"])


def test_unavailable_constituent_does_not_renormalize_basket_or_abort_other_signals():
    provider = ValidationFixtureProvider()
    del provider.frames["000002"]
    result = StrategyValidationEngine(provider).validate(_packet())
    assert result["coverage"]["executed_signals"] == 2
    assert result["coverage"]["failed_signals"] == 2
    assert len(result["trades"]) == 4
    assert result["trades"][1]["net_return_pct"] is None
    assert result["trades"][1]["missing_symbols"] == ["000002"]


def test_idle_sessions_are_included_in_annualized_return_not_invented_ratio():
    packet = _packet()
    packet["holding_period_sessions"] = 1
    result = StrategyValidationEngine(ValidationFixtureProvider()).validate(packet)
    oos = result["out_of_sample"]
    assert oos["portfolio_state"] == "complete"
    assert oos["idle_sessions"] == 1
    # Exact fixture opens: Jan 9->12 and Jan 13->14, with one idle session.
    total = ((21.5 / 21 - 1 - .005) + 1) * ((13.5 / 13 - 1 - .005) + 1) - 1
    assert oos["annualized_return_pct"] == pytest.approx(((1 + total) ** (252 / 3) - 1) * 100, abs=.0001)
    assert oos["sharpe"] is None
    assert oos["information_ratio"] is None


@pytest.mark.parametrize("missing_date", ["2026-01-05", "2026-01-07", "2026-01-09"])
def test_missing_benchmark_row_does_not_move_execution_or_split(missing_date):
    provider = ValidationFixtureProvider()
    before = StrategyValidationEngine(provider).validate(_packet())
    provider.frames["510300"] = provider.frames["510300"].loc[lambda x: x.date != pd.Timestamp(missing_date)]
    after = StrategyValidationEngine(provider).validate(_packet())
    assert after["validation_audit"] == before["validation_audit"]
    assert [(r["entry_date"], r["exit_date"]) for r in after["trades"]] == [(r["entry_date"], r["exit_date"]) for r in before["trades"]]
    affected = [r for r in after["trades"] if missing_date in (r["entry_date"], r["exit_date"])]
    assert affected
    assert all(r["reason"] == "missing_benchmark_open" and r["benchmark_return_pct"] is None for r in affected)


def test_calendar_holiday_is_independent_of_extra_weekday_quote():
    provider = ValidationFixtureProvider()
    original = provider.get_trading_calendar
    def calendar(start, end):
        data = original(start, end)
        data["sessions"].remove("2026-01-05")
        return data
    provider.get_trading_calendar = calendar
    result = StrategyValidationEngine(provider).validate(_packet())
    assert result["trades"][0]["entry_date"] == "2026-01-06"
    assert result["trades"][0]["exit_date"] == "2026-01-08"


def test_calendar_failure_never_falls_back_to_ohlcv_dates():
    from instock.core.market_data_provider import MarketDataError
    provider = ValidationFixtureProvider()
    provider.get_trading_calendar = lambda start, end: {"status": "unavailable"}
    with pytest.raises(MarketDataError, match="独立交易日历"):
        StrategyValidationEngine(provider).validate(_packet())


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
