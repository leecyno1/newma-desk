from __future__ import annotations

from typing import Any


TERMINAL_NODE_STATUSES = {"completed", "cancelled", "skipped"}


def recalculate_run_status(document: dict[str, Any]) -> None:
    statuses = {node["status"] for node in document["nodes"]}
    if statuses and statuses <= TERMINAL_NODE_STATUSES:
        document["status"] = "completed"
    elif "stale" in statuses:
        document["status"] = "needs_rework"
    elif "failed" in statuses:
        document["status"] = "failed"
    elif "blocked" in statuses:
        document["status"] = "blocked"
    else:
        document["status"] = "active"
