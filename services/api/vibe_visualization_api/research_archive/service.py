from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from vibe_visualization_api.mod_storage.store import (
    ModStorageCorruptError,
    ModStorageNotFoundError,
    ModStorageStore,
)


SourceParser = Callable[[dict[str, Any], int, str], list[dict[str, Any]]]


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _rows(value: Any, key: str) -> list[dict[str, Any]]:
    rows = _record(value).get(key)
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _text(value: Any, fallback: str = "", limit: int = 320) -> str:
    return value[:limit].strip() if isinstance(value, str) else fallback


def _iso(value: Any, fallback: str) -> str:
    candidate = _text(value, "", 80)
    if not candidate:
        return fallback
    try:
        datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except (OverflowError, ValueError):
        return fallback
    return candidate


def _security(value: Any) -> dict[str, str] | None:
    row = _record(value)
    market = _text(row.get("market"), "", 24)
    symbol = _text(row.get("symbol"), "", 32)
    name = _text(row.get("name"), "", 160)
    if not market or not symbol or not name:
        return None
    return {"market": market, "symbol": symbol, "name": name}


def _entry(
    *,
    kind: str,
    source_mod_id: str,
    artifact_id: Any,
    title: Any,
    status: str,
    updated_at: Any,
    fallback_updated_at: str,
    source_revision: int,
    security: Any = None,
    as_of: Any = None,
    tags: list[Any] | None = None,
) -> dict[str, Any] | None:
    normalized_id = _text(artifact_id, "", 240)
    normalized_title = _text(title, "", 320)
    if not normalized_id or not normalized_title:
        return None
    normalized_tags = []
    for tag in tags or []:
        value = _text(tag, "", 80)
        if value and value not in normalized_tags:
            normalized_tags.append(value)
    normalized_security = _security(security)
    normalized_as_of = _text(as_of, "", 80)
    return {
        "id": f"archive:{source_mod_id}:{normalized_id}"[:320],
        "kind": kind,
        "sourceModId": source_mod_id,
        "artifactId": normalized_id,
        "title": normalized_title,
        "status": status,
        **({"security": normalized_security} if normalized_security else {}),
        **({"asOf": normalized_as_of} if normalized_as_of else {}),
        "updatedAt": _iso(updated_at, fallback_updated_at),
        "tags": normalized_tags[:16],
        "sourceRevision": source_revision,
    }


def _research_records(value: dict[str, Any], revision: int, updated_at: str):
    entries = []
    for row in _rows(value, "records"):
        timestamp = row.get("ts")
        source_updated_at = updated_at
        if isinstance(timestamp, (int, float)) and timestamp >= 0:
            try:
                source_updated_at = datetime.fromtimestamp(
                    timestamp / 1000,
                    tz=UTC,
                ).isoformat()
            except (OSError, OverflowError, ValueError):
                source_updated_at = updated_at
        entry = _entry(
            kind="research-record",
            source_mod_id="research-notes",
            artifact_id=row.get("id"),
            title=row.get("title"),
            status="active",
            updated_at=source_updated_at,
            fallback_updated_at=updated_at,
            source_revision=revision,
            tags=[row.get("kind")],
        )
        if entry:
            entries.append(entry)
    return entries


def _theses(value: dict[str, Any], revision: int, updated_at: str):
    status_map = {
        "draft": "draft",
        "archived": "archived",
        "invalidated": "invalidated",
    }
    entries = []
    for row in _rows(value, "theses"):
        status = _text(row.get("status"), "unknown", 32)
        entry = _entry(
            kind="thesis",
            source_mod_id="thesis-tracker",
            artifact_id=row.get("id"),
            title=row.get("title"),
            status=status_map.get(status, "active" if status in {"active", "watch"} else "unknown"),
            security=row.get("security"),
            as_of=row.get("nextReviewAt"),
            updated_at=row.get("updatedAt"),
            fallback_updated_at=updated_at,
            source_revision=revision,
            tags=[status, row.get("conviction")],
        )
        if entry:
            entries.append(entry)
    return entries


def _earnings(value: dict[str, Any], revision: int, updated_at: str):
    entries = []
    for row in _rows(value, "workbooks"):
        security = _record(row.get("security"))
        period = _record(row.get("fiscalPeriod"))
        verification = _record(row.get("verification"))
        title = f"{_text(security.get('name'), '证券', 160)} · {_text(period.get('label'), '财报研究', 120)}"
        entry = _entry(
            kind="earnings",
            source_mod_id="earnings-workbench",
            artifact_id=row.get("id"),
            title=title,
            status="active",
            security=security,
            as_of=period.get("reportingDate") or period.get("periodEnd"),
            updated_at=row.get("updatedAt"),
            fallback_updated_at=updated_at,
            source_revision=revision,
            tags=[row.get("mode"), verification.get("status")],
        )
        if entry:
            entries.append(entry)
    return entries


def _peer_cases(value: dict[str, Any], revision: int, updated_at: str):
    entries = []
    for row in _rows(value, "cases"):
        period = _record(row.get("period"))
        entry = _entry(
            kind="peer-comparison",
            source_mod_id="peer-comparison",
            artifact_id=row.get("id"),
            title=row.get("name"),
            status="active",
            security=row.get("target"),
            as_of=period.get("asOf"),
            updated_at=row.get("updatedAt"),
            fallback_updated_at=updated_at,
            source_revision=revision,
            tags=[row.get("researchQuestion")],
        )
        if entry:
            entries.append(entry)
    return entries


def _valuations(value: dict[str, Any], revision: int, updated_at: str):
    entries = []
    for row in _rows(value, "models"):
        entry = _entry(
            kind="valuation",
            source_mod_id="valuation-workbench",
            artifact_id=row.get("id"),
            title=row.get("name"),
            status="active",
            security=row.get("security"),
            as_of=row.get("asOf"),
            updated_at=row.get("updatedAt"),
            fallback_updated_at=updated_at,
            source_revision=revision,
            tags=[row.get("modelScope"), row.get("selectedScenario")],
        )
        if entry:
            entries.append(entry)
    return entries


def _memos(value: dict[str, Any], revision: int, updated_at: str):
    status_map = {
        "draft": "draft",
        "archived": "archived",
        "superseded": "stale",
        "current": "active",
    }
    entries = []
    for row in _rows(value, "memos"):
        boundary = _record(row.get("boundary"))
        executive_view = _record(row.get("executiveView"))
        status = _text(row.get("status"), "unknown", 32)
        entry = _entry(
            kind="research-memo",
            source_mod_id="research-memo",
            artifact_id=row.get("id"),
            title=row.get("title"),
            status=status_map.get(status, "unknown"),
            security=row.get("security"),
            as_of=boundary.get("asOf"),
            updated_at=row.get("updatedAt"),
            fallback_updated_at=updated_at,
            source_revision=revision,
            tags=[status, executive_view.get("bias"), executive_view.get("conviction")],
        )
        if entry:
            entries.append(entry)
    return entries


SOURCES: tuple[tuple[str, str, str, SourceParser], ...] = (
    ("research-notes", "research-notes", "records", _research_records),
    ("thesis-tracker", "thesis-tracker", "portfolio", _theses),
    ("earnings-workbench", "earnings-workbench", "workbooks", _earnings),
    ("peer-comparison", "peer-comparison", "cases", _peer_cases),
    ("valuation-workbench", "valuation-workbench", "models", _valuations),
    ("research-memo", "research-memo", "memos", _memos),
)


class ResearchArchiveService:
    def __init__(self, storage: ModStorageStore):
        self._storage = storage

    def list(self, *, user_id: str, workspace_id: str) -> dict[str, Any]:
        entries: list[dict[str, Any]] = []
        for module_id, namespace, key, parser in SOURCES:
            try:
                document = self._storage.get(
                    user_id=user_id,
                    workspace_id=workspace_id,
                    module_id=module_id,
                    namespace=namespace,
                    key=key,
                )
            except (ModStorageNotFoundError, ModStorageCorruptError):
                continue
            try:
                entries.extend(
                    parser(
                        _record(document.get("value")),
                        int(document["revision"]),
                        _iso(document.get("updatedAt"), _now()),
                    )
                )
            except (OSError, OverflowError, TypeError, ValueError):
                continue
        entries.sort(key=lambda entry: entry["updatedAt"], reverse=True)
        return {
            "schemaVersion": "newma-desk.research-archive.v1",
            "userId": user_id,
            "workspaceId": workspace_id,
            "generatedAt": _now(),
            "entries": entries[:1000],
        }
