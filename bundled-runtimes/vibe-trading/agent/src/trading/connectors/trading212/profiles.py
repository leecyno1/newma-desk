"""Built-in Trading 212 connector profiles.

Trading 212's public REST API is registered here as read-only only. The API key
selects whatever account Trading 212 has bound to it; this connector has no
runtime paper/live discriminator it can independently verify, so order
placement is not exposed by any built-in profile.
"""

from __future__ import annotations

from src.trading.types import TradingProfile

TRADING212_READ_CAPABILITIES = (
    "account.read",
    "positions.read",
    "orders.read",
    "order_history.read",
    "instruments.read",
)

TRADING212_PROFILES: tuple[TradingProfile, ...] = (
    TradingProfile(
        id="trading212-paper-sdk",
        connector="trading212",
        label="Trading 212 Practice · REST Read-Only",
        environment="paper",
        transport="broker_sdk",
        capabilities=TRADING212_READ_CAPABILITIES,
        readonly=True,
        config={"profile": "paper", "base_url": "https://demo.trading212.com"},
        notes=(
            "Reads a Trading 212 account through the public REST API. Paper vs "
            "live is operator-declared from the configured API key; order "
            "placement is disabled because the API response does not provide a "
            "runtime discriminator this connector can verify."
        ),
    ),
    TradingProfile(
        id="trading212-live-sdk-readonly",
        connector="trading212",
        label="Trading 212 Live · REST Read-Only",
        environment="live",
        transport="broker_sdk",
        capabilities=TRADING212_READ_CAPABILITIES,
        readonly=True,
        config={"profile": "live-readonly", "base_url": "https://live.trading212.com"},
        notes=(
            "Reads a Trading 212 live account through the public REST API. "
            "Order placement is not exposed in this profile."
        ),
    ),
)
