"""Robinhood remote MCP generic-operation mapping."""

from __future__ import annotations

from typing import Any

_REMOTE_TOOL_NAMES = {
    "account": "get_portfolio",
    "positions": "get_equity_positions",
    "orders": "get_equity_orders",
    "quote": "get_equity_quotes",
}

_RUNNER_TOOL_NAMES = {
    "account": "get_portfolio",
    "positions": "get_equity_positions",
    "orders": "get_equity_orders",
    "quote": "get_equity_quotes",
    "submit_order": "place_equity_order",
    "cancel_order": "cancel_equity_order",
}


def remote_tool_name(operation: str) -> str | None:
    """Return the Robinhood remote tool name for a generic operation."""
    return _REMOTE_TOOL_NAMES.get(operation)


def runner_tool_name(operation: str) -> str | None:
    """Return the Robinhood remote tool name used by live runner plumbing."""
    return _RUNNER_TOOL_NAMES.get(operation)


def remote_arguments(operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Normalize generic arguments for a Robinhood remote MCP operation."""
    if operation == "quote":
        symbol = arguments.get("symbol")
        symbols = arguments.get("symbols")
        return {"symbols": symbols or ([symbol] if symbol else [])}
    return {}
