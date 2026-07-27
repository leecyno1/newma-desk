import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vibe_visualization_api.watchlists.models import SecurityRef, WatchGroup


SCHEMA = """
CREATE TABLE IF NOT EXISTS watchlist_documents (
  user_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  revision INTEGER NOT NULL,
  groups_json TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (user_id, workspace_id)
);
"""


DEFAULT_GROUPS = [
    {
        "id": "sample",
        "name": "示例组合",
        "symbols": [
            {"symbol": "600519", "name": "贵州茅台", "market": "CN", "exchange": "SH", "currency": "CNY"},
            {"symbol": "688981", "name": "中芯国际", "market": "CN", "exchange": "SH", "currency": "CNY"},
            {"symbol": "300308", "name": "中际旭创", "market": "CN", "exchange": "SZ", "currency": "CNY"},
            {"symbol": "002463", "name": "沪电股份", "market": "CN", "exchange": "SZ", "currency": "CNY"},
            {"symbol": "300750", "name": "宁德时代", "market": "CN", "exchange": "SZ", "currency": "CNY"},
            {"symbol": "600406", "name": "国电南瑞", "market": "CN", "exchange": "SH", "currency": "CNY"},
            {"symbol": "00700", "name": "腾讯控股", "market": "HK", "exchange": "HKEX", "currency": "HKD"},
            {"symbol": "AAPL", "name": "Apple", "market": "US", "exchange": "NASDAQ", "currency": "USD"},
            {"symbol": "NVDA", "name": "NVIDIA", "market": "US", "exchange": "NASDAQ", "currency": "USD"},
            {"symbol": "TSLA", "name": "Tesla", "market": "US", "exchange": "NASDAQ", "currency": "USD"},
        ],
    }
]


class WatchlistStoreError(Exception):
    """Base error for shared watchlist persistence."""


class WatchlistConflictError(WatchlistStoreError):
    """Raised when a requested mutation conflicts with current state."""


class WatchlistNotFoundError(WatchlistStoreError):
    """Raised when a requested group is unavailable."""


class WatchlistStore:
    def __init__(self, database_path: Path):
        self._database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _default_groups() -> list[dict[str, Any]]:
        return json.loads(json.dumps(DEFAULT_GROUPS, ensure_ascii=False))

    @staticmethod
    def _serialize(groups: list[dict[str, Any]]) -> str:
        return json.dumps(
            groups,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _document(
        *,
        user_id: str,
        workspace_id: str,
        revision: int,
        groups: list[dict[str, Any]],
        updated_at: str | None,
    ) -> dict[str, Any]:
        return {
            "userId": user_id,
            "workspaceId": workspace_id,
            "revision": revision,
            "groups": groups,
            "updatedAt": updated_at,
        }

    def _read_current(
        self,
        connection: sqlite3.Connection,
        user_id: str,
        workspace_id: str,
    ) -> tuple[int, list[dict[str, Any]], str | None]:
        row = connection.execute(
            """
            SELECT revision, groups_json, updated_at
            FROM watchlist_documents
            WHERE user_id = ? AND workspace_id = ?
            """,
            (user_id, workspace_id),
        ).fetchone()
        if row is None:
            return 0, self._default_groups(), None
        groups = json.loads(row["groups_json"])
        if not isinstance(groups, list):
            raise ValueError("stored watchlist groups must be an array")
        return int(row["revision"]), groups, str(row["updated_at"])

    def get(self, *, user_id: str, workspace_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            revision, groups, updated_at = self._read_current(
                connection,
                user_id,
                workspace_id,
            )
        return self._document(
            user_id=user_id,
            workspace_id=workspace_id,
            revision=revision,
            groups=groups,
            updated_at=updated_at,
        )

    def _write(
        self,
        connection: sqlite3.Connection,
        *,
        user_id: str,
        workspace_id: str,
        revision: int,
        groups: list[dict[str, Any]],
    ) -> dict[str, Any]:
        updated_at = datetime.now(UTC).isoformat()
        connection.execute(
            """
            INSERT INTO watchlist_documents (
              user_id, workspace_id, revision, groups_json, updated_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, workspace_id) DO UPDATE SET
              revision = excluded.revision,
              groups_json = excluded.groups_json,
              updated_at = excluded.updated_at
            """,
            (
                user_id,
                workspace_id,
                revision,
                self._serialize(groups),
                updated_at,
            ),
        )
        return self._document(
            user_id=user_id,
            workspace_id=workspace_id,
            revision=revision,
            groups=groups,
            updated_at=updated_at,
        )

    def replace(
        self,
        *,
        user_id: str,
        workspace_id: str,
        expected_revision: int,
        groups: list[WatchGroup],
    ) -> dict[str, Any]:
        payload = [group.model_dump(mode="json", by_alias=True) for group in groups]
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            connection.execute("BEGIN IMMEDIATE")
            current_revision, _, _ = self._read_current(
                connection,
                user_id,
                workspace_id,
            )
            if expected_revision != current_revision:
                raise WatchlistConflictError("watchlist revision is stale")
            result = self._write(
                connection,
                user_id=user_id,
                workspace_id=workspace_id,
                revision=current_revision + 1,
                groups=payload,
            )
        return result

    def _mutate(
        self,
        *,
        user_id: str,
        workspace_id: str,
        mutation: Callable[[list[dict[str, Any]]], bool],
    ) -> dict[str, Any]:
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            connection.execute("BEGIN IMMEDIATE")
            revision, groups, updated_at = self._read_current(
                connection,
                user_id,
                workspace_id,
            )
            changed = mutation(groups)
            if not changed:
                return self._document(
                    user_id=user_id,
                    workspace_id=workspace_id,
                    revision=revision,
                    groups=groups,
                    updated_at=updated_at,
                )
            return self._write(
                connection,
                user_id=user_id,
                workspace_id=workspace_id,
                revision=revision + 1,
                groups=groups,
            )

    def create_group(
        self,
        *,
        user_id: str,
        workspace_id: str,
        group_id: str,
        name: str,
    ) -> dict[str, Any]:
        def mutation(groups: list[dict[str, Any]]) -> bool:
            if any(group.get("id") == group_id for group in groups):
                raise WatchlistConflictError("watchlist group already exists")
            if len(groups) >= 50:
                raise WatchlistConflictError("watchlist group limit reached")
            groups.append({"id": group_id, "name": name, "symbols": []})
            return True

        return self._mutate(
            user_id=user_id,
            workspace_id=workspace_id,
            mutation=mutation,
        )

    def rename_group(
        self,
        *,
        user_id: str,
        workspace_id: str,
        group_id: str,
        name: str,
    ) -> dict[str, Any]:
        def mutation(groups: list[dict[str, Any]]) -> bool:
            group = next((item for item in groups if item.get("id") == group_id), None)
            if group is None:
                raise WatchlistNotFoundError("watchlist group was not found")
            if group.get("name") == name:
                return False
            group["name"] = name
            return True

        return self._mutate(
            user_id=user_id,
            workspace_id=workspace_id,
            mutation=mutation,
        )

    def delete_group(
        self,
        *,
        user_id: str,
        workspace_id: str,
        group_id: str,
    ) -> dict[str, Any]:
        def mutation(groups: list[dict[str, Any]]) -> bool:
            if len(groups) <= 1:
                raise WatchlistConflictError("at least one watchlist group is required")
            remaining = [group for group in groups if group.get("id") != group_id]
            if len(remaining) == len(groups):
                raise WatchlistNotFoundError("watchlist group was not found")
            groups[:] = remaining
            return True

        return self._mutate(
            user_id=user_id,
            workspace_id=workspace_id,
            mutation=mutation,
        )

    def put_security(
        self,
        *,
        user_id: str,
        workspace_id: str,
        group_id: str,
        security: SecurityRef,
    ) -> dict[str, Any]:
        payload = security.model_dump(mode="json", by_alias=True)

        def mutation(groups: list[dict[str, Any]]) -> bool:
            group = next((item for item in groups if item.get("id") == group_id), None)
            if group is None:
                raise WatchlistNotFoundError("watchlist group was not found")
            symbols = group.setdefault("symbols", [])
            identity = (security.market, security.symbol)
            for index, item in enumerate(symbols):
                if (item.get("market"), item.get("symbol")) == identity:
                    if item == payload:
                        return False
                    symbols[index] = payload
                    return True
            if len(symbols) >= 500:
                raise WatchlistConflictError("watchlist security limit reached")
            symbols.append(payload)
            return True

        return self._mutate(
            user_id=user_id,
            workspace_id=workspace_id,
            mutation=mutation,
        )

    def delete_security(
        self,
        *,
        user_id: str,
        workspace_id: str,
        group_id: str,
        market: str,
        symbol: str,
    ) -> dict[str, Any]:
        def mutation(groups: list[dict[str, Any]]) -> bool:
            group = next((item for item in groups if item.get("id") == group_id), None)
            if group is None:
                raise WatchlistNotFoundError("watchlist group was not found")
            symbols = group.setdefault("symbols", [])
            remaining = [
                item
                for item in symbols
                if (item.get("market"), item.get("symbol")) != (market, symbol)
            ]
            if len(remaining) == len(symbols):
                return False
            group["symbols"] = remaining
            return True

        return self._mutate(
            user_id=user_id,
            workspace_id=workspace_id,
            mutation=mutation,
        )
