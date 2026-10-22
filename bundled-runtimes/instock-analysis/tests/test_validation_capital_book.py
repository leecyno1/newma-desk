import json

import pandas as pd
import pytest

from instock.core.validation.capital_book import simulate_sleeves
from instock.core.validation.strategy_validation import StrategyValidationEngine, StrategyValidationError
from test_strategy_validation import ValidationFixtureProvider, _packet


def scenario(entries=(1, 2, 3, 4), holding=3, size=9):
    dates = pd.bdate_range("2026-01-02", periods=size)
    frame = pd.DataFrame({"date": dates, "open": 100.0, "close": 100.0, "volume": 1000000.0})
    rows = [{"decision_date": dates[entry - 1].strftime("%Y-%m-%d"),
             "entry_date": dates[entry].strftime("%Y-%m-%d"), "entry_index": entry,
             "exit_date": dates[entry + holding].strftime("%Y-%m-%d") if entry + holding < size else None,
             "exit_index": entry + holding if entry + holding < size else None,
             "symbols": ["000001"]} for entry in entries]
    return rows, {"000001": frame.copy(), "000002": frame.copy()}, frame.copy(), dates


def run(case, slots=2, cost=0):
    return simulate_sleeves(*case, slots=slots, cost_bps=cost)


def test_finite_capital_skips_full_book_and_releases_exit_before_new_entry():
    result = run(scenario())
    assert [row["state"] for row in result["ledger"]] == ["closed", "closed", "skipped_capacity", "closed"]
    assert [row["slot"] for row in result["ledger"]] == [1, 2, None, 1]
    assert result["max_active_sleeves"] == 2
    assert result["allocated_signals"] == 3
    assert result["skipped_signals"] == 1
    assert result["ending_nav"] == result["ending_cash"] == 1
    assert result["total_return_pct"] == result["max_drawdown_pct"] == 0
    assert result["sharpe"] is None
    assert all(0 <= row["cash"] <= row["nav"] for row in result["curve"])


def test_cost_is_debited_from_funded_notional_and_sleeve_reinvests_own_proceeds():
    result = run(scenario(entries=(1, 4)), cost=100)
    first, second = result["ledger"]
    proceeds = .5 * .99 / 1.01
    assert first["exit_proceeds"] == pytest.approx(proceeds)
    assert second["entry_budget"] == pytest.approx(proceeds)
    assert result["ending_nav"] == pytest.approx(.5 + .5 * (.99 / 1.01) ** 2)
    assert result["cost_pct_initial_capital"] == pytest.approx((1 - result["ending_nav"]) * 100, abs=1e-4)


def test_missing_future_exit_never_promotes_skipped_signal_or_changes_sleeves():
    case = scenario()
    original = run(case)
    case[1]["000001"].loc[4, "open"] = None
    result = run(case)
    assert [(r["slot"], r["entry_date"]) for r in result["ledger"]] == [(r["slot"], r["entry_date"]) for r in original["ledger"]]
    assert result["ledger"][2]["state"] == "skipped_capacity"
    assert result["ledger"][3]["entry_budget"] is None
    assert result["ending_nav"] is None
    assert result["max_drawdown_pct"] is None
    assert result["cost_pct_initial_capital"] is None
    json.dumps(result, allow_nan=False)


def test_missing_basket_entry_does_not_drop_member_or_reweight_survivor():
    case = scenario(entries=(1, 2))
    case[0][0]["symbols"] = ["000001", "000002"]
    case[1]["000002"].loc[1, "open"] = None
    result = run(case)
    assert result["ledger"][0]["state"] == "unresolved"
    assert result["ledger"][0]["issues"][0] == "missing_entry_open"
    assert result["ledger"][1]["entry_budget"] == .5
    assert result["ending_nav"] is None


def test_missing_interior_mark_breaks_risk_path_not_known_final_cash():
    case = scenario(entries=(1,), holding=5)
    case[1]["000001"].loc[3, "close"] = None
    result = run(case)
    assert result["state"] == "incomplete"
    assert result["ending_nav"] == 1
    assert result["total_return_pct"] == 0
    assert result["max_drawdown_pct"] is None
    assert result["sharpe"] is None
    assert result["daily_return_observations"] == 0
    assert any(row["nav"] is None for row in result["curve"])


def test_benchmark_gap_does_not_hide_strategy_risk():
    case = scenario(entries=(1,), holding=5)
    case[1]["000001"].loc[3, "close"] = 50
    case[2].loc[3, "close"] = None
    result = run(case)
    assert result["state"] == "complete"
    assert result["benchmark_state"] == "incomplete"
    assert result["max_drawdown_pct"] == 25
    assert result["annualized_volatility_pct"] > 0
    assert result["sharpe"] is not None
    assert result["information_ratio"] is None


def test_unexpired_positions_mark_to_market_without_inventing_sale():
    case = scenario(entries=(6, 7), holding=4)
    case[1]["000001"].loc[8, "close"] = 120
    result = run(case)
    assert result["state"] == "complete"
    assert result["open_sleeves"] == 2
    assert result["ending_cash"] == 0
    assert result["ending_nav"] == pytest.approx(1.2)
    assert all(row["state"] == "open" and row["exit_proceeds"] is None for row in result["ledger"])


@pytest.mark.parametrize("volume,reason", [(0, "zero_volume"), (None, "missing_volume"), (-1, "missing_volume")])
def test_unverified_entry_volume_preserves_capacity_and_unknown_cash(volume, reason):
    case = scenario(entries=(1, 2), holding=4)
    case[1]["000001"].loc[1, "volume"] = volume
    result = run(case, slots=1)
    first, second = result["ledger"]
    assert first["execution_issues"] == [{"symbol": "000001", "date": first["entry_date"], "side": "buy", "reason": reason}]
    assert first["state"] == "unresolved"
    assert second["state"] == "skipped_capacity"
    assert result["total_return_pct"] is None
    assert result["ending_cash"] is None
    assert result["curve"][2]["cash"] is None
    assert result["cost_pct_initial_capital"] is None
    json.dumps(result, allow_nan=False)


def test_zero_volume_exit_cannot_free_known_cash_or_change_prior_allocations():
    case = scenario()
    original = run(case)
    case[1]["000001"].loc[4, "volume"] = 0
    result = run(case)
    assert [(row["slot"], row["entry_date"]) for row in result["ledger"]] == [(row["slot"], row["entry_date"]) for row in original["ledger"]]
    assert result["ledger"][0]["exit_proceeds"] is None
    assert result["ledger"][0]["execution_issues"][0]["side"] == "sell"
    assert result["ledger"][2]["state"] == "skipped_capacity"
    assert result["ledger"][3]["entry_budget"] is None
    assert result["max_drawdown_pct"] is None


def test_volume_gap_on_capacity_skipped_signal_does_not_poison_actual_book():
    case = scenario(entries=(1, 2), holding=3)
    case[0][1]["symbols"] = ["000002"]
    case[1]["000002"].loc[2, "volume"] = 0
    result = run(case, slots=1)
    assert result["state"] == "complete"
    assert result["total_return_pct"] == 0
    assert result["ledger"][1]["state"] == "skipped_capacity"
    assert result["ledger"][1]["execution_issues"] == []


def test_slots_capital_integrates_without_changing_signal_diagnostics_or_split():
    packet = _packet()
    packet["holding_period_sessions"] = 4
    engine = StrategyValidationEngine(ValidationFixtureProvider())
    before = engine.validate(packet)
    packet["capital_model"] = {"mode": "fixed_sleeves", "slots": 2}
    result = engine.validate(packet)
    assert result["input_packet"] == packet
    assert result["trades"] == before["trades"]
    assert result["out_of_sample"] == before["out_of_sample"]
    assert result["validation_audit"] == before["validation_audit"]
    book = result["capital_backtest"]["out_of_sample"]
    assert book["allocated_signals"] == 2
    assert book["max_active_sleeves"] == 2
    assert book["state"] == "complete"
    assert book["ledger"][0]["entry_budget"] == .5
    assert result["capital_backtest"]["train"]["state"] == "unavailable"
    assert "curve" not in result["snapshot"]["result"]["summary"]["capital_backtest"]["out_of_sample"]
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("model", [None, {}, {"mode": "fixed_sleeves", "slots": True},
                                    {"mode": "fixed_sleeves", "slots": 2.5},
                                    {"mode": "fixed_sleeves", "slots": 0},
                                    {"mode": "fixed_sleeves", "slots": 21}])
def test_invalid_allocation_is_rejected_before_loading_data(model):
    packet = {**_packet(), "capital_model": model}
    with pytest.raises(StrategyValidationError, match="capital_model"):
        StrategyValidationEngine(ValidationFixtureProvider()).validate(packet)
