import pandas as pd
import pytest

from instock.core.rotation.execution_audit import RotationExecutionAudit, execution_summary
from instock.core.rotation.rotation_experiment import RotationExperiment, _metrics
from instock.core.rotation.rotation_risk import daily_rotation_risk


def setup(symbols=("A", "A", "B", "CASH", "CASH", "A")):
    dates = pd.bdate_range("2026-01-05", periods=len(symbols) + 1)
    frames = {code: pd.DataFrame({"date": dates, "open": 100., "close": 100., "volume": 1000.}) for code in ("A", "B")}
    rows, previous = [], "CASH"
    for index, code in enumerate(symbols):
        switched = code != previous
        rows.append(dict(signal_date=dates[index].strftime("%Y-%m-%d"), entry_date=dates[index].strftime("%Y-%m-%d"),
            exit_date=dates[index + 1].strftime("%Y-%m-%d"), symbol=code, switched=switched,
            gross_return=0., transaction_cost=.005 if switched else 0., net_return=-.005 if switched else 0.,
            benchmark_return=0., equal_weight_return=0.))
        previous = code
    class Provider:
        def __init__(self):
            self.calls = []
            self.feeds = {code: {"status": "ready", "rows": [dict(date=day.strftime("%Y-%m-%d"),
                status="paired", priceBasis="unadjusted", rawOpen=10., upperLimit=11., lowerLimit=9.)
                for day in dates]} for code in frames}

        def get_execution_prices(self, symbol, start, end):
            self.calls.append(symbol)
            return self.feeds[symbol]
    provider = Provider()
    audit = RotationExecutionAudit(provider, frames, rows[0]["entry_date"], rows[-1]["exit_date"])
    return audit, provider, rows, frames, dates


def test_audits_only_initial_and_switch_legs_not_holds_cash_or_terminal_marks():
    audit, provider, rows, _, dates = setup()
    # No new buy at continuing-hold date; final price only marks value.
    provider.feeds["A"]["rows"][1]["rawOpen"] = 11
    provider.feeds["A"]["rows"][-1]["rawOpen"] = 9
    output = audit.apply(rows)
    assert [[(c["symbol"], c["side"]) for c in row["execution_checks"]] for row in output] == [
        [("A", "buy")], [], [("A", "sell"), ("B", "buy")], [("B", "sell")], [], [("A", "buy")]]
    assert execution_summary(output)["planned_legs"] == 5
    assert all(row["execution_evidence_state"] == "checked" for row in output)
    assert [row["net_return"] for row in output] == [row["net_return"] for row in rows]
    assert sorted(provider.calls) == ["A", "B"]  # shared across nine plans, one fetch per code
    assert all("execution_checks" not in row for row in rows)
    audit.apply(rows)
    assert len(provider.calls) == 2


@pytest.mark.parametrize("code,opening,reason", [("A", 9., "sell_at_lower_limit"), ("B", 11., "buy_at_upper_limit")])
def test_either_switch_leg_breaks_current_and_future_returns_without_replacement(code, opening, reason):
    audit, provider, rows, frames, dates = setup()
    provider.feeds[code]["rows"][2]["rawOpen"] = opening
    output = audit.apply(rows)
    assert [row["symbol"] for row in output] == [row["symbol"] for row in rows]
    assert [row["net_return"] for row in output[:2]] == [row["net_return"] for row in rows[:2]]
    assert output[2]["decision_issue"] == reason
    assert all(row["net_return"] is None and row["gross_return"] is None for row in output[2:])
    assert output[3]["decision_issue"] == "prior_execution_unresolved"
    assert _metrics(output, 5)["total_return_pct"] is None
    assert RotationExperiment._stress_metrics(output, rebalance_days=5, cost_bps=50)["total_return_pct"] is None
    risk = daily_rotation_risk(output, trade_frames=frames, benchmark_frame=frames["A"],
        expected_periods=[(r["entry_date"], r["exit_date"]) for r in output], sessions=dates)
    assert risk["strategy"]["max_drawdown_pct"] is None
    assert risk["strategy"]["ending_nav"] is None


@pytest.mark.parametrize("value,reason", [(0., "zero_volume"), (None, "missing_volume")])
def test_volume_is_checked_on_actual_transition_not_every_mark(value, reason):
    audit, _, rows, _, _ = setup(("A", "A", "B"))
    audit.bars["A"][rows[1]["entry_date"]]["volume"] = value
    assert audit.apply(rows)[1]["net_return"] == 0
    audit.bars["A"][rows[2]["entry_date"]]["volume"] = value
    result = audit.apply(rows)
    assert result[2]["decision_issue"] == reason
    assert result[2]["net_return"] is None


@pytest.mark.parametrize("fault", ["missing", "unavailable_saved"])
def test_missing_limits_keep_theoretical_returns_and_propagate_evidence_status(fault):
    audit, provider, rows, _, _ = setup(("A", "A", "B"))
    if fault == "missing": provider.feeds["A"]["rows"] = []
    else: provider.feeds["A"]["status"] = "unavailable"
    result = audit.apply(rows)
    assert all(row["execution_evidence_state"] == "theoretical" for row in result)
    assert [row["net_return"] for row in result] == [row["net_return"] for row in rows]
    # A held position inherits the initial evidence gap despite no new order.
    assert execution_summary(result[1:2])["planned_legs"] == 0
    assert execution_summary(result[1:2])["state"] == "theoretical"
    assert RotationExperiment._training_qualification(_metrics(result, 5))["checks"]["price_volume_limit_evidence"] is False


def test_missing_decision_never_recovers_capital_from_a_later_unambiguous_target():
    audit, _, rows, _, _ = setup(("A", None, "A"))
    rows[1].update(switched=None, decision_issue="insufficient_signal_coverage")
    result = audit.apply(rows)
    assert result[1]["symbol"] is None
    assert result[1]["decision_issue"] == "insufficient_signal_coverage"
    assert result[2]["net_return"] is None


def test_ensemble_plan_is_audited_from_its_own_previous_holding():
    audit, provider, source, _, _ = setup(("A", "A", "A"))
    provider.feeds["B"]["rows"][1]["rawOpen"] = 11
    original = audit.apply(source)
    ensemble = [dict(row) for row in source]
    ensemble[1].update(symbol="B", switched=True)
    ensemble[2].update(switched=True)
    actual = audit.apply(ensemble)
    assert original[1]["execution_checks"] == []
    assert actual[1]["decision_issue"] == "buy_at_upper_limit"
    assert actual[2]["net_return"] is None
