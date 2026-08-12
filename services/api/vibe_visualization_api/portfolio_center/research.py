from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from vibe_visualization_api.portfolio_center.models import PortfolioPosition


CORE_KINDS = ("thesis", "research-memo")
SUPPORTING_KINDS = ("earnings", "peer-comparison", "valuation")


def _now() -> datetime:
    return datetime.now(UTC)


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    try:
        parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except (OverflowError, ValueError):
        try:
            parsed = datetime.fromisoformat(f"{candidate}T00:00:00+00:00")
        except (OverflowError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _security_key(market: Any, symbol: Any) -> tuple[str, str] | None:
    if not isinstance(market, str) or not isinstance(symbol, str):
        return None
    normalized_market = market.strip().upper()
    normalized_symbol = symbol.strip().upper()
    if not normalized_market or not normalized_symbol:
        return None
    return normalized_market, normalized_symbol


def compile_portfolio_research_coverage(
    *,
    user_id: str,
    workspace_id: str,
    positions: list[PortfolioPosition],
    archive: dict[str, Any],
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    now = generated_at or _now()
    securities: dict[tuple[str, str], dict[str, Any]] = {}
    for position in positions:
        key = _security_key(position.market, position.symbol)
        if key is None:
            continue
        current = securities.setdefault(
            key,
            {
                "market": key[0],
                "symbol": key[1],
                "name": position.name or position.symbol,
                "accountIds": [],
            },
        )
        if position.account_id not in current["accountIds"]:
            current["accountIds"].append(position.account_id)

    references_by_security: dict[tuple[str, str], list[dict[str, Any]]] = {}
    entries = archive.get("entries") if isinstance(archive, dict) else []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        security = entry.get("security")
        if not isinstance(security, dict):
            continue
        key = _security_key(security.get("market"), security.get("symbol"))
        if key not in securities:
            continue
        references_by_security.setdefault(key, []).append(entry)

    compiled: list[dict[str, Any]] = []
    for key, security in securities.items():
        references = sorted(
            references_by_security.get(key, []),
            key=lambda entry: str(entry.get("updatedAt") or ""),
            reverse=True,
        )[:50]
        active = [entry for entry in references if entry.get("status") == "active"]
        core_kinds = [
            kind for kind in CORE_KINDS
            if any(entry.get("kind") == kind for entry in active)
        ]
        supporting_kinds = [
            kind for kind in SUPPORTING_KINDS
            if any(entry.get("kind") == kind for entry in active)
        ]
        missing_groups = []
        if not core_kinds:
            missing_groups.append("core-thesis-or-memo")
        if not supporting_kinds:
            missing_groups.append("supporting-analysis")
        if core_kinds and supporting_kinds:
            status = "complete"
        elif references:
            status = "partial"
        else:
            status = "missing"

        attention_reasons = []
        if any(
            entry.get("kind") == "thesis"
            and entry.get("status") == "active"
            and (review_at := _parse_datetime(entry.get("asOf"))) is not None
            and review_at < now
            for entry in references
        ):
            attention_reasons.append("review-overdue")
        if any(
            entry.get("kind") == "research-memo"
            and entry.get("status") == "stale"
            for entry in references
        ):
            attention_reasons.append("stale-core-research")
        if any(
            entry.get("kind") == "thesis"
            and entry.get("status") == "invalidated"
            for entry in references
        ):
            attention_reasons.append("invalidated-thesis")

        latest_updated_at = next(
            (
                entry.get("updatedAt")
                for entry in references
                if _parse_datetime(entry.get("updatedAt")) is not None
            ),
            None,
        )
        compiled.append(
            {
                **security,
                "status": status,
                "referenceCount": len(references),
                "activeReferenceCount": len(active),
                "coreKinds": core_kinds,
                "supportingKinds": supporting_kinds,
                "missingGroups": missing_groups,
                "attentionReasons": attention_reasons,
                **(
                    {"latestUpdatedAt": latest_updated_at}
                    if latest_updated_at
                    else {}
                ),
                "references": references,
            }
        )

    compiled.sort(
        key=lambda item: (
            0 if item["attentionReasons"] else 1,
            {"missing": 0, "partial": 1, "complete": 2}[item["status"]],
            item["market"],
            item["symbol"],
        )
    )
    return {
        "schemaVersion": "newma-desk.portfolio-research-coverage.v1",
        "userId": user_id,
        "workspaceId": workspace_id,
        "generatedAt": now.isoformat(),
        "summary": {
            "positionCount": len(compiled),
            "completeCount": sum(item["status"] == "complete" for item in compiled),
            "partialCount": sum(item["status"] == "partial" for item in compiled),
            "missingCount": sum(item["status"] == "missing" for item in compiled),
            "attentionCount": sum(bool(item["attentionReasons"]) for item in compiled),
            "activeReferenceCount": sum(item["activeReferenceCount"] for item in compiled),
        },
        "positions": compiled,
    }
