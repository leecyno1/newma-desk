import pandas as pd
import pytest

from instock.core.rotation.rotation_risk import daily_rotation_risk


DATES = pd.bdate_range("2026-01-05", periods=6).strftime("%Y-%m-%d").tolist()


def bars(closes, opens=None):
    return pd.DataFrame({"date": DATES[:len(closes)], "open": opens or [100] * len(closes), "close": closes})


def trade(start=0, end=3, symbol="A", cost=0, net=0):
    return {"entry_date": DATES[start], "exit_date": DATES[end], "symbol": symbol,
            "transaction_cost": cost, "net_return": net, "benchmark_return": 0}


def run(trades, frames, periods=None, benchmark=None):
    return daily_rotation_risk(trades, trade_frames=frames,
                               sessions=DATES,
                               benchmark_frame=benchmark if benchmark is not None else bars([100] * 6),
                               expected_periods=periods or [(row["entry_date"], row["exit_date"]) for row in trades])


def test_mid_period_dip_is_visible_even_when_exit_recovers():
    result = run([trade()], {"A": bars([100, 60, 100, 1])})
    risk = result["strategy"]
    assert risk["state"] == "complete"
    assert risk["max_drawdown_pct"] == pytest.approx(40)
    assert risk["ending_nav"] == 1
    assert risk["start_date"] == DATES[0]
    assert risk["end_date"] == DATES[3]
    assert risk["peak_date"] == DATES[0]
    assert risk["trough_date"] == DATES[1]
    assert risk["recovery_date"] == DATES[2]
    assert result["curve"][-1]["phase"] == "exit_open"
    assert result["curve"][-1]["date"] == DATES[3]


def test_cost_path_reconciles_to_additive_period_returns():
    result = run([trade(cost=.01, net=.19)], {"A": bars([110, 90, 100, 500], [100, 100, 100, 120])})
    assert result["strategy"]["state"] == "complete"
    assert result["strategy"]["ending_nav"] == pytest.approx(1.19)
    assert result["curve"][1]["strategy"] == pytest.approx(.99)
    assert result["strategy"]["max_drawdown_pct"] == pytest.approx((1 - .89 / 1.09) * 100)


def test_switch_open_marks_are_not_collapsed_and_use_new_asset():
    result = run([trade(0, 2, net=.2), trade(2, 4, "B", .02, -.02)],
                 {"A": bars([100, 100, 1, 1, 1], [100, 100, 120, 100, 100]),
                  "B": bars([100, 100, 100, 80, 100])})
    boundary = [point for point in result["curve"] if point["date"] == DATES[2]]
    assert [point["phase"] for point in boundary] == ["exit_open", "entry_open", "close"]
    assert [point["strategy"] for point in boundary] == pytest.approx([1.2, 1.176, 1.176])
    assert result["strategy"]["ending_nav"] == pytest.approx(1.2 * .98)
    assert result["strategy"]["max_drawdown_pct"] == pytest.approx(22)


@pytest.mark.parametrize("missing", [None, 0, float("nan")])
def test_missing_close_is_a_gap_not_zero_risk(missing):
    result = run([trade()], {"A": bars([100, missing, 90, 100])})
    assert result["strategy"]["state"] == "incomplete"
    assert result["strategy"]["max_drawdown_pct"] is None
    assert result["strategy"]["observed_max_drawdown_pct"] == pytest.approx(10)
    assert result["strategy"]["coverage"]["observed_closes"] == 2
    assert next(row for row in result["curve"] if row["date"] == DATES[1])["strategy"] is None
    assert result["strategy"]["ending_nav"] == 1
    assert result["benchmark"]["state"] == "complete"


@pytest.mark.parametrize("missing_index", [0, 1, 2])
def test_skipped_period_including_start_or_end_is_not_assumed_cash(missing_index):
    periods = [(DATES[0], DATES[1]), (DATES[1], DATES[2]), (DATES[2], DATES[3])]
    trades = [trade(i, i + 1) for i in range(3) if i != missing_index]
    result = run(trades, {"A": bars([100] * 6)}, periods)
    assert result["strategy"]["state"] == "incomplete"
    assert result["strategy"]["max_drawdown_pct"] is None
    assert result["strategy"]["ending_nav"] is None
    assert result["strategy"]["coverage"]["observed_periods"] == 2
    assert result["strategy"]["coverage"]["expected_closes"] == 3
    assert result["curve"][-1]["strategy"] is None


def test_missing_open_and_changed_execution_prices_fail_reconciliation():
    for opens in ([None, 100, 100, 100], [100, 100, 100, 110]):
        result = run([trade()], {"A": bars([100] * 4, opens)})
        assert result["strategy"]["state"] == "incomplete"
        assert result["strategy"]["ending_nav"] is None
        assert result["strategy"]["max_drawdown_pct"] is None
        assert result["strategy"]["issues"]
        assert all(point["strategy"] is None for point in result["curve"][1:])


def test_initial_fee_drawdown_and_true_flat_zero():
    for cost in (0, .01):
        result = run([trade(cost=cost, net=-cost)], {"A": bars([100] * 4)})
        assert result["strategy"]["max_drawdown_pct"] == pytest.approx(cost * 100)
        assert result["strategy"]["current_drawdown_pct"] == pytest.approx(cost * 100)


def test_benchmark_missing_row_does_not_hide_asset_drawdown_day():
    result = run([trade()], {"A": bars([100, 60, 100, 100])},
                 benchmark=bars([100] * 6).drop(index=1))
    assert result["strategy"]["max_drawdown_pct"] == pytest.approx(40)
    assert result["strategy"]["coverage"]["expected_closes"] == 3
    assert result["benchmark"]["coverage"]["expected_closes"] == 3
    assert result["benchmark"]["coverage"]["observed_closes"] == 2
    assert result["benchmark"]["max_drawdown_pct"] is None


def test_empty_history_has_no_risk_claim_and_no_future_prices_are_used():
    assert run([], {}, [])["strategy"]["max_drawdown_pct"] is None
    first = run([trade()], {"A": bars([100, 90, 110, 100, 100, 100])})
    second = run([trade()], {"A": bars([100, 90, 110, 1, 10000, 1])})
    assert first == second
