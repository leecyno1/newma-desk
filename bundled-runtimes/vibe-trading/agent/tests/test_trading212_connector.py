"""Tests for the read-only Trading 212 connector."""

from __future__ import annotations

import pytest

from src.live import registry
from src.live.classification import ToolClass, classify_tool
from src.trading import profiles, service
from src.trading.connectors.trading212 import sdk as t212
from src.trading.connectors.trading212.classification import TRADING212_TOOL_CLASS

pytestmark = pytest.mark.unit


def test_trading212_profiles_registered_readonly() -> None:
    ids = {profile.id for profile in profiles.list_profiles()}
    assert {"trading212-paper-sdk", "trading212-live-sdk-readonly"} <= ids

    for profile_id, environment in (
        ("trading212-paper-sdk", "paper"),
        ("trading212-live-sdk-readonly", "live"),
    ):
        profile = profiles.profile_by_id(profile_id)
        assert profile.connector == "trading212"
        assert profile.environment == environment
        assert profile.transport == "broker_sdk"
        assert profile.readonly is True
        assert "orders.place" not in profile.capabilities
        assert "orders.place.requires_mandate" not in profile.capabilities
        assert "instruments.read" in profile.capabilities
        assert "order_history.read" in profile.capabilities


def test_trading212_profiles_use_official_hosts() -> None:
    paper = profiles.profile_by_id("trading212-paper-sdk")
    live = profiles.profile_by_id("trading212-live-sdk-readonly")

    paper_cfg = t212.build_config(paper.config, {"api_key": "key"})
    live_cfg = t212.build_config(live.config, {"api_key": "key"})

    assert paper_cfg.base_url == "https://demo.trading212.com"
    assert live_cfg.base_url == "https://live.trading212.com"


def test_trading212_read_write_classification_registered() -> None:
    curated = registry._BROKER_CURATED_MAPS["trading212"]

    for name in (
        "get_account_cash",
        "get_positions",
        "get_open_orders",
        "get_order_history",
        "get_instrument_metadata",
        "equity_metadata_instruments",
    ):
        assert TRADING212_TOOL_CLASS[name] is ToolClass.READ
        assert classify_tool(name, None, curated) is ToolClass.READ

    for name in ("place_order", "cancel_order", "equity_order_market", "equity_order_cancel"):
        assert TRADING212_TOOL_CLASS[name] is ToolClass.WRITE
        assert classify_tool(name, None, curated) is ToolClass.WRITE

    assert classify_tool("brand_new_trading212_operation", None, curated) is ToolClass.UNKNOWN


def test_trading212_service_dispatches_positions(monkeypatch) -> None:
    def fake_request(config, method, path, *, params=None):
        assert method == "GET"
        assert path == "/api/v0/equity/portfolio"
        assert config.api_key == "key"
        return [
            {
                "ticker": "AAPL_US_EQ",
                "quantity": 2,
                "averagePrice": 150.0,
                "currentPrice": 151.25,
                "currencyCode": "USD",
            }
        ]

    monkeypatch.setattr(t212, "_request", fake_request)

    result = service.get_positions("trading212-live-sdk-readonly", api_key="key")
    assert result["status"] == "ok"
    assert result["connector"] == "trading212"
    assert result["environment"] == "live"
    assert result["positions"] == [
        {
            "symbol": "AAPL_US_EQ",
            "ticker": "AAPL_US_EQ",
            "quantity": 2,
            "average_price": 150.0,
            "current_price": 151.25,
            "pnl": None,
            "fx_pnl": None,
            "currency": "USD",
            "initial_fill_date": None,
            "max_buy": None,
            "max_sell": None,
            "cash_invested": None,
        }
    ]


def test_trading212_check_connection_missing_api_key(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(t212, "get_runtime_root", lambda: tmp_path)
    result = service.check_connection("trading212-live-sdk-readonly")
    assert result["status"] == "error"
    assert "missing api_key" in result["error"]
    assert result["connector"] == "trading212"
    assert result["transport"] == "broker_sdk"


def test_trading212_check_connection_invalid_api_key_surfaces_clean_error(monkeypatch) -> None:
    def invalid_auth(config, method, path, *, params=None):
        raise t212.Trading212APIError("Trading 212 API authentication failed: check api_key.")

    monkeypatch.setattr(t212, "_request", invalid_auth)

    result = service.check_connection("trading212-live-sdk-readonly", api_key="bad")
    assert result["status"] == "error"
    assert "authentication failed" in result["error"]
    assert result["connector"] == "trading212"


class _FakeResponse:
    status_code = 200
    content = b"{}"
    text = ""
    reason = "OK"

    def json(self):
        return {}


def test_trading212_request_uses_basic_auth_when_api_secret_is_present(monkeypatch) -> None:
    seen = {}

    def fake_request(method, url, *, headers, auth, params, timeout):
        seen.update(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "auth": auth,
                "params": params,
                "timeout": timeout,
            }
        )
        return _FakeResponse()

    monkeypatch.setattr(t212.requests, "request", fake_request)

    t212._request(
        t212.Trading212Config(api_key="key", api_secret="secret"),
        "GET",
        "/api/v0/equity/account/cash",
        params={"limit": 1},
    )

    assert seen == {
        "method": "GET",
        "url": "https://live.trading212.com/api/v0/equity/account/cash",
        "headers": {"Accept": "application/json"},
        "auth": ("key", "secret"),
        "params": {"limit": 1},
        "timeout": 15.0,
    }


def test_trading212_request_uses_legacy_authorization_without_api_secret(monkeypatch) -> None:
    seen = {}

    def fake_request(method, url, *, headers, auth, params, timeout):
        seen.update({"headers": headers, "auth": auth})
        return _FakeResponse()

    monkeypatch.setattr(t212.requests, "request", fake_request)

    t212._request(t212.Trading212Config(api_key="legacy-key"), "GET", "/api/v0/equity/account/cash")

    assert seen["headers"] == {"Accept": "application/json", "Authorization": "legacy-key"}
    assert seen["auth"] is None


def test_trading212_public_config_redacts_api_secret() -> None:
    pub = t212._public_config(t212.Trading212Config(api_key="KEY12345", api_secret="SECRET"))
    assert pub["api_key"] == "KEY1***"
    assert pub["api_secret"] == "***redacted***"
    assert "SECRET" not in str(pub)


def test_trading212_nonpaper_order_attempts_refused_before_config_checks() -> None:
    cfg = t212.Trading212Config(profile="live-readonly")

    placed = t212.place_order(cfg, symbol="AAPL_US_EQ", side="buy", quantity=1)
    cancelled = t212.cancel_order(cfg, "order-1", symbol="AAPL_US_EQ")

    assert placed["status"] == "error"
    assert cancelled["status"] == "error"
    assert "not supported for live/read-only profiles" in placed["error"]
    assert "not supported for live/read-only profiles" in cancelled["error"]
    assert "not configured" not in placed["error"]
    assert "not configured" not in cancelled["error"]


def test_trading212_service_order_attempts_refuse_readonly_profile() -> None:
    placed = service.place_order("AAPL_US_EQ", "trading212-live-sdk-readonly", side="buy", quantity=1)
    cancelled = service.cancel_order("order-1", "trading212-live-sdk-readonly", symbol="AAPL_US_EQ")

    assert placed["status"] == "error"
    assert cancelled["status"] == "error"
    assert "does not support orders.place" in placed["error"]
    assert "does not support orders.cancel" in cancelled["error"]


def test_trading212_paper_order_attempts_still_readonly() -> None:
    cfg = t212.Trading212Config(profile="paper", api_key="practice-key")
    result = t212.place_order(cfg, symbol="AAPL_US_EQ", side="buy", quantity=1)
    assert result["status"] == "error"
    assert "read-only" in result["error"]


def test_trading212_instrument_metadata_filter(monkeypatch) -> None:
    def fake_request(config, method, path, *, params=None):
        assert path == "/api/v0/equity/metadata/instruments"
        return [
            {"ticker": "AAPL_US_EQ", "name": "Apple", "currencyCode": "USD", "isin": "US0378331005"},
            {"ticker": "VODl_EQ", "name": "Vodafone", "currencyCode": "GBP", "isin": "GB00BH4HKS39"},
        ]

    monkeypatch.setattr(t212, "_request", fake_request)

    result = t212.get_instrument_metadata(t212.Trading212Config(api_key="key"), ticker="aapl_us_eq")
    assert result["status"] == "ok"
    assert result["instruments"] == [
        {
            "ticker": "AAPL_US_EQ",
            "name": "Apple",
            "short_name": None,
            "isin": "US0378331005",
            "type": None,
            "currency": "USD",
            "exchange": None,
            "working_schedule_id": None,
            "max_open_quantity": None,
            "min_trade_quantity": None,
            "added_on": None,
        }
    ]
