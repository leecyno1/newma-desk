import pytest

from instock.core.market_data_provider import MarketDataError
from instock.core.validation.execution import check_open_limit
from instock.core.validation.strategy_validation import StrategyValidationEngine
from instock.core.validation.capital_book import simulate_sleeves
from test_strategy_validation import ValidationFixtureProvider, _packet
from test_validation_capital_book import scenario


def pair(opening=100, upper=110, lower=90):
    return dict(status="paired", priceBasis="unadjusted", rawOpen=opening, upperLimit=upper, lowerLimit=lower)


class LimitProvider(ValidationFixtureProvider):
    def __init__(self):
        super().__init__()
        self.feeds = {code: dict(status="ready", rows=[dict(date=day.strftime("%Y-%m-%d"), **pair())
                      for day in frame.date]) for code, frame in self.frames.items()}

    def get_execution_prices(self, symbol, start, end):
        return self.feeds[symbol]


@pytest.mark.parametrize("opening,side,state", [(110, "buy", "adverse"), (90, "sell", "adverse"),
    (110, "sell", "checked"), (90, "buy", "checked"), (100, "buy", "checked")])
def test_directional_price_limits(opening, side, state):
    assert check_open_limit(pair(opening), side)["state"] == state


@pytest.mark.parametrize("evidence", [None, dict(pair(), priceBasis="qfq"), pair(111), pair(0), pair(100, 0)])
def test_missing_adjusted_or_invalid_pairs_never_certify_limits(evidence):
    assert check_open_limit(evidence, "buy")["state"] == "unverified"


def test_separate_raw_price_evidence_does_not_reprice_adjusted_returns():
    provider = LimitProvider()
    result = StrategyValidationEngine(provider).validate(_packet())
    assert result["trades"][0]["gross_return_pct"] == 10
    checks = result["trades"][0]["price_limit_checks"]
    assert all(row["rawOpen"] == 100 for row in checks)  # qfq opens are 10 and 11
    summary = result["validation_audit"]["execution_evidence"]["price_limits"]
    assert summary["paired_legs"] == summary["dated_legs"] == 10
    assert summary["unverified_legs"] == summary["adverse_legs"] == 0


@pytest.mark.parametrize("day,opening,reason", [("2026-01-05", 110, "buy_at_upper_limit"),
                                               ("2026-01-07", 90, "sell_at_lower_limit")])
def test_adverse_limit_removes_return_but_preserves_signal_and_positive_volume(day, opening, reason):
    provider = LimitProvider()
    for row in provider.feeds["000001"]["rows"]:
        if row["date"] == day: row.update(rawOpen=opening)
    result = StrategyValidationEngine(provider).validate(_packet())
    assert len(result["trades"]) == 4
    trade = result["trades"][0]
    assert trade["reason"] == "adverse_price_limit"
    assert trade["net_return_pct"] is None
    assert trade["execution_issues"][0]["reason"] == reason
    evidence = result["validation_audit"]["execution_evidence"]
    assert evidence["price_limits"]["adverse_legs"] == 1
    assert evidence["price_volume_verified_legs"] == 10
    assert result["coverage"]["evidence_sufficient"] is False


@pytest.mark.parametrize("fault", ["missing_day", "unavailable_saved", "error"])
def test_missing_limit_evidence_keeps_theoretical_diagnostics_but_not_readiness(fault):
    provider = LimitProvider()
    if fault == "missing_day": provider.feeds["000001"]["rows"] = []
    elif fault == "unavailable_saved": provider.feeds["000001"]["status"] = "unavailable"
    else:
        def fail(*args): raise MarketDataError("unavailable")
        provider.get_execution_prices = fail
    result = StrategyValidationEngine(provider).validate(_packet())
    assert result["trades"][0]["net_return_pct"] == 9.5
    assert result["validation_audit"]["execution_evidence"]["price_limits"]["unverified_legs"] > 0
    assert "historical_price_limit_pairs_incomplete_returns_are_theoretical" in result["limitations"]
    assert result["coverage"]["evidence_sufficient"] is False


@pytest.mark.parametrize("index,opening", [(1, 110), (4, 90)])
def test_adverse_limits_preserve_sleeve_allocation_and_propagate_unknown_cash(index, opening):
    case = scenario()
    original = simulate_sleeves(*case, slots=2, cost_bps=25)
    evidence = {"000001": {day: pair() for day in case[3]}}
    evidence["000001"][case[3][index]] = pair(opening)
    result = simulate_sleeves(*case, slots=2, cost_bps=25, execution_limits=evidence)
    assert [(row["slot"], row["entry_date"]) for row in result["ledger"]] == [(row["slot"], row["entry_date"]) for row in original["ledger"]]
    assert result["ledger"][2]["state"] == "skipped_capacity"
    assert result["ledger"][3]["entry_budget"] is None
    assert result["ending_cash"] is None and result["ending_nav"] is None
    assert result["total_return_pct"] is None and result["max_drawdown_pct"] is None
