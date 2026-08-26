"""Curated read/write classification for Trading 212 REST operations.

Keys are the connector's public operation names and the Trading 212 REST
operation names they wrap. Mutating order operations are pinned WRITE even
though this read-only connector refuses them at runtime, so the live gate never
treats a future Trading 212 order surface as a plain read.
"""

from __future__ import annotations

from src.live.classification import ToolClass

TRADING212_TOOL_CLASS: dict[str, ToolClass] = {
    # READ
    "get_account_snapshot": ToolClass.READ,
    "get_account_cash": ToolClass.READ,
    "get_account_metadata": ToolClass.READ,
    "get_positions": ToolClass.READ,
    "get_open_orders": ToolClass.READ,
    "get_order_history": ToolClass.READ,
    "get_instrument_metadata": ToolClass.READ,
    "get_exchanges": ToolClass.READ,
    "get_quote": ToolClass.READ,
    "get_historical_bars": ToolClass.READ,
    "equity_account_cash": ToolClass.READ,
    "equity_account_info": ToolClass.READ,
    "equity_portfolio": ToolClass.READ,
    "equity_orders": ToolClass.READ,
    "equity_history_orders": ToolClass.READ,
    "equity_metadata_instruments": ToolClass.READ,
    "equity_metadata_exchanges": ToolClass.READ,
    # WRITE
    "place_order": ToolClass.WRITE,
    "cancel_order": ToolClass.WRITE,
    "equity_order_market": ToolClass.WRITE,
    "equity_order_limit": ToolClass.WRITE,
    "equity_order_stop": ToolClass.WRITE,
    "equity_order_stop_limit": ToolClass.WRITE,
    "equity_order_cancel": ToolClass.WRITE,
}
