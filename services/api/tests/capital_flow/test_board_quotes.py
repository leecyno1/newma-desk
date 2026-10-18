import pytest

from vibe_visualization_api.capital_flow.board_quotes import verify_cohort


DAY = "2026-10-16"


def check(price=None, bound=None, outcome="absent", daily_status="ready", limit_status="ready"):
    return verify_cohort([{"code": "000001.SZ", "outcome": outcome}], DAY,
                         {"status": daily_status, "rows": price or []}, {"status": limit_status, "rows": bound or []})


def price(**kwargs):
    return {"ts_code": "000001.SZ", "trade_date": "20261016", "close": 10.5, "pct_chg": 5, "amount": 200000, **kwargs}


def bound(**kwargs):
    return {"ts_code": "000001.SZ", "trade_date": "20261016", "up_limit": 11, "down_limit": 9, **kwargs}


def test_absent_with_positive_return_can_be_verified_below_limit():
    result = check([price()], [bound()])
    assert result["rows"][0]["status"] == "below_limit"
    assert result["rows"][0]["amountYi"] == 2
    assert result["summary"]["medianPct"] == 5
    assert result["summary"]["belowLimit"] == 1


@pytest.mark.parametrize("outcome,close", [("absent", 11), ("absent", 9), ("Z", 11), ("U", 10.5), ("D", 10.5), ("U", 12)])
def test_pool_price_conflicts_are_not_silently_corrected(outcome, close):
    result = check([price(close=close)], [bound()], outcome=outcome)
    assert result["rows"][0]["status"] == "conflict"
    assert result["summary"]["conflicts"] == 1
    assert result["summary"]["medianPct"] is None


@pytest.mark.parametrize("outcome,close,status", [("U", 11, "at_limit"), ("D", 9, "below_limit"), ("Z", 10, "below_limit")])
def test_matching_prices_preserve_classification(outcome, close, status):
    assert check([price(close=close)], [bound()], outcome)["rows"][0]["status"] == status


def test_missing_or_failed_prices_never_confirm_suspension_or_reuse_data():
    assert check([], [bound()])["rows"][0]["status"] == "unavailable"
    result = check([price()], [bound()], daily_status="unavailable")
    assert result["rows"][0]["close"] is None and result["summary"]["medianPct"] is None
    assert check([price(amount=0)], [bound()])["rows"][0]["status"] == "no_trade"
    assert check([price(amount=None)], [bound()])["rows"][0]["status"] == "unavailable"


def test_missing_limits_keeps_daily_evidence_but_not_board_verdict():
    result = check([price(pct_chg=None)], [bound()], limit_status="unavailable")
    assert result["rows"][0]["status"] == "traded"
    assert result["rows"][0]["upLimit"] is None
    assert result["summary"]["priced"] == 1 and result["summary"]["returnCount"] == 0
    assert result["summary"]["medianPct"] is None


def test_wrong_day_or_duplicate_conflict_disqualifies_only_affected_code():
    assert check([price(trade_date="20261015")], [bound()])["rows"][0]["status"] == "conflict"
    assert check([price(), price(close=10)], [bound()])["rows"][0]["close"] is None
    assert check([price(), price()], [bound()])["rows"][0]["status"] == "below_limit"
    result = check([price()], [bound(), bound(up_limit=12)])
    assert result["rows"][0]["status"] == "conflict" and result["rows"][0]["upLimit"] is None
