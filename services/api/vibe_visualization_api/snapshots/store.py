import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from vibe_visualization_api.snapshots.models import Snapshot


MODULE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{2,63}$")
SNAPSHOT_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
AUDIT_DDL = """
CREATE TABLE IF NOT EXISTS snapshot_refresh_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  module_id TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('success','failed')),
  snapshot_id TEXT,
  error TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_snapshot_refresh_module
ON snapshot_refresh_events(module_id, id);
"""


class SnapshotStoreError(Exception):
    """Base error for module snapshot operations."""


class SnapshotNotFoundError(SnapshotStoreError):
    """Raised when a successful snapshot does not exist."""


class CorruptSnapshotError(SnapshotStoreError):
    """Raised when persisted snapshot metadata cannot be trusted."""


class SnapshotStore:
    def __init__(self, runtime_dir: Path, database_path: Path | None = None):
        self._snapshot_root = runtime_dir / "snapshots"
        self._database_path = database_path or runtime_dir / "vibe-visualization.db"
        self._snapshot_root.mkdir(parents=True, exist_ok=True)
        self._initialize_audit_store()

    def write_success(self, module_id: str, data: dict[str, Any]) -> Snapshot:
        module_dir = self._module_dir(module_id)
        module_dir.mkdir(parents=True, exist_ok=True)
        created_at = datetime.now(timezone.utc)
        snapshot = Snapshot(
            id=uuid4().hex,
            module_id=module_id,
            created_at=created_at,
            data=data,
        )
        timestamp = created_at.strftime("%Y%m%dT%H%M%S%fZ")
        filename = f"{timestamp}-{snapshot.id}.json"
        self._atomic_write_json(
            module_dir / filename,
            snapshot.model_dump(mode="json", by_alias=True),
        )
        self._atomic_write_json(
            module_dir / "latest.json",
            {
                "id": snapshot.id,
                "createdAt": created_at.isoformat(),
                "snapshotFile": filename,
            },
        )
        self._record_outcome(
            module_id=module_id,
            status="success",
            snapshot_id=snapshot.id,
            error=None,
        )
        return snapshot

    def write_failure(self, module_id: str, error: str) -> None:
        self._module_dir(module_id)
        self._record_outcome(
            module_id=module_id,
            status="failed",
            snapshot_id=None,
            error=error[:4000],
        )

    def latest_success(self, module_id: str) -> Snapshot:
        module_dir = self._module_dir(module_id)
        pointer_path = module_dir / "latest.json"
        if not pointer_path.is_file():
            raise SnapshotNotFoundError(
                f"module {module_id!r} has no successful snapshot"
            )

        try:
            pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
            filename = pointer["snapshotFile"]
            snapshot_id = pointer["id"]
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as error:
            raise CorruptSnapshotError("latest snapshot pointer is invalid") from error
        if (
            not isinstance(filename, str)
            or Path(filename).name != filename
            or not isinstance(snapshot_id, str)
            or SNAPSHOT_ID_PATTERN.fullmatch(snapshot_id) is None
            or not filename.endswith(f"-{snapshot_id}.json")
        ):
            raise CorruptSnapshotError("latest snapshot pointer is unsafe")

        return self._read_snapshot(module_dir / filename, module_id, snapshot_id)

    def list_success(self, module_id: str) -> list[Snapshot]:
        module_dir = self._module_dir(module_id)
        if not module_dir.is_dir():
            return []

        snapshots: list[Snapshot] = []
        for path in sorted(module_dir.glob("*.json"), reverse=True):
            if path.name == "latest.json":
                continue
            match = re.search(r"-([0-9a-f]{32})\.json$", path.name)
            if match is None:
                continue
            snapshots.append(self._read_snapshot(path, module_id, match.group(1)))
        return snapshots

    def get_success(self, module_id: str, snapshot_id: str) -> Snapshot:
        module_dir = self._module_dir(module_id)
        if SNAPSHOT_ID_PATTERN.fullmatch(snapshot_id) is None:
            raise SnapshotNotFoundError("snapshot was not found")

        paths = list(module_dir.glob(f"*-{snapshot_id}.json"))
        if len(paths) != 1:
            raise SnapshotNotFoundError("snapshot was not found")
        return self._read_snapshot(paths[0], module_id, snapshot_id)

    def _module_dir(self, module_id: str) -> Path:
        if MODULE_ID_PATTERN.fullmatch(module_id) is None:
            raise SnapshotNotFoundError("module snapshot was not found")
        return self._snapshot_root / module_id

    def _read_snapshot(
        self,
        path: Path,
        expected_module_id: str,
        expected_snapshot_id: str,
    ) -> Snapshot:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            snapshot = Snapshot.model_validate(payload)
        except FileNotFoundError as error:
            raise SnapshotNotFoundError("snapshot was not found") from error
        except (OSError, json.JSONDecodeError, ValidationError) as error:
            raise CorruptSnapshotError("snapshot file is invalid") from error
        if (
            snapshot.module_id != expected_module_id
            or snapshot.id != expected_snapshot_id
        ):
            raise CorruptSnapshotError("snapshot identity does not match its path")
        return snapshot

    @staticmethod
    def _atomic_write_json(path: Path, payload: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        temporary = path.parent / f".{path.name}.{uuid4().hex}.tmp"
        try:
            with temporary.open("x", encoding="utf-8") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            directory_fd = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            temporary.unlink(missing_ok=True)

    def _initialize_audit_store(self) -> None:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._database_path, timeout=5.0)
        try:
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.executescript(AUDIT_DDL)
        finally:
            connection.close()

    def _record_outcome(
        self,
        *,
        module_id: str,
        status: str,
        snapshot_id: str | None,
        error: str | None,
    ) -> None:
        connection = sqlite3.connect(self._database_path, timeout=5.0)
        try:
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute(
                """
                INSERT INTO snapshot_refresh_events (
                  module_id, status, snapshot_id, error, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    module_id,
                    status,
                    snapshot_id,
                    error,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            connection.commit()
        finally:
            connection.close()
