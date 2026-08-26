"""Curated read/write classification map for Robinhood Agentic Trading.

Tier 2 of the classification ladder (:mod:`src.live.classification`): an
explicit, version-controlled map keyed by the broker's remote tool name. Map
entries are authoritative and override Tier-1 ``annotations`` when they
disagree (a deceptive ``readOnlyHint=True`` on ``place_equity_order`` cannot demote a
curated WRITE). A tool absent from this map and not annotated read-only is
UNKNOWN and treated as WRITE (fail-closed).

This map is the FROZEN canonical Robinhood catalog (SPEC §7.5):
``READ = {get_accounts, get_portfolio, get_equity_positions,
get_equity_quotes, get_equity_orders}`` and
``WRITE = {place_equity_order, cancel_equity_order}``. Any tool the broker
reports that is not in this map and not annotated read-only resolves to UNKNOWN
→ treated as WRITE (fail-closed), so an unrecognized new broker tool can never
slip through as a plain read. Adding a tool here is a localized edit to this one
dict plus the classification test parametrize list.
"""

from __future__ import annotations

from src.live.classification import ToolClass

#: Frozen canonical Robinhood read/write catalog.
ROBINHOOD_TOOL_CLASS: dict[str, ToolClass] = {
    # READ
    "get_accounts": ToolClass.READ,
    "get_portfolio": ToolClass.READ,
    "get_equity_positions": ToolClass.READ,
    "get_equity_quotes": ToolClass.READ,
    "get_equity_orders": ToolClass.READ,
    # WRITE
    "place_equity_order": ToolClass.WRITE,
    "cancel_equity_order": ToolClass.WRITE,
}
