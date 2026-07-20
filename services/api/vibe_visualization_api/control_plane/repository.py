import json
import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from vibe_visualization_api.control_plane.database import connect
from vibe_visualization_api.control_plane.models import ModuleStatus, StoredModule


MODULE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]{2,63}$")


class ModuleRepositoryError(Exception):
    """Base error for module registry operations."""


class ModuleNotFoundError(ModuleRepositoryError):
    """Raised when a requested module revision does not exist."""


class InvalidModuleStateError(ModuleRepositoryError):
    """Raised when a module cannot perform the requested transition."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _append_audit(
    connection: sqlite3.Connection,
    *,
    event_type: str,
    module_id: str | None,
    revision: int | None,
    detail: dict[str, object] | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO audit_events (
          event_type, module_id, revision, detail_json, created_at
        ) VALUES (?, ?, ?, ?, ?)
        """,
        (event_type, module_id, revision, _json_dumps(detail or {}), _utc_now()),
    )


def _stored_module(row: sqlite3.Row) -> StoredModule:
    manifest = json.loads(row["manifest_json"])
    if not isinstance(manifest, dict):
        raise ValueError("stored module manifest must be a JSON object")
    return StoredModule(
        module_id=row["module_id"],
        revision=row["revision"],
        status=cast(ModuleStatus, row["status"]),
        manifest=cast(dict[str, Any], manifest),
        created_at=row["created_at"],
    )


class ModuleRepository:
    def __init__(self, database_path: Path):
        self._database_path = database_path
        connection = connect(self._database_path)
        connection.close()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = connect(self._database_path)
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
        except BaseException:
            connection.rollback()
            raise
        else:
            connection.commit()
        finally:
            connection.close()

    def create_draft(self, manifest: dict[str, object]) -> StoredModule:
        module_id = manifest.get("id")
        if (
            not isinstance(module_id, str)
            or MODULE_ID_PATTERN.fullmatch(module_id) is None
        ):
            raise ValueError("manifest['id'] must match ^[a-z][a-z0-9-]{2,63}$")

        manifest_json = _json_dumps(manifest)
        created_at = _utc_now()
        with self._transaction() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(MAX(revision), 0) + 1 AS next_revision
                FROM module_revisions
                WHERE module_id = ?
                """,
                (module_id,),
            ).fetchone()
            revision = cast(int, row["next_revision"])
            connection.execute(
                """
                INSERT INTO module_revisions (
                  module_id, revision, status, manifest_json, created_at
                ) VALUES (?, ?, 'draft', ?, ?)
                """,
                (module_id, revision, manifest_json, created_at),
            )
            _append_audit(
                connection,
                event_type="create_draft",
                module_id=module_id,
                revision=revision,
            )
            stored_row = self._get_revision_row(connection, module_id, revision)
        return _stored_module(stored_row)

    def publish(self, module_id: str, revision: int) -> StoredModule:
        with self._transaction() as connection:
            target = self._get_revision_row(connection, module_id, revision)
            if target["status"] != "draft":
                raise InvalidModuleStateError(
                    f"module {module_id!r} revision {revision} must be draft "
                    "before publishing"
                )
            connection.execute(
                """
                UPDATE module_revisions
                SET status = 'disabled'
                WHERE module_id = ? AND status = 'published'
                """,
                (module_id,),
            )
            connection.execute(
                """
                UPDATE module_revisions
                SET status = 'published'
                WHERE module_id = ? AND revision = ?
                """,
                (module_id, revision),
            )
            _append_audit(
                connection,
                event_type="publish",
                module_id=module_id,
                revision=revision,
            )
            stored_row = self._get_revision_row(connection, module_id, revision)
        return _stored_module(stored_row)

    def list_published(self) -> list[StoredModule]:
        connection = connect(self._database_path)
        try:
            rows = connection.execute(
                """
                SELECT module_id, revision, status, manifest_json, created_at
                FROM module_revisions
                WHERE status = 'published'
                ORDER BY module_id, revision
                """
            ).fetchall()
            return [_stored_module(row) for row in rows]
        finally:
            connection.close()

    def disable(self, module_id: str) -> StoredModule:
        with self._transaction() as connection:
            current = self._get_published_row(connection, module_id)
            if current is None:
                raise InvalidModuleStateError(
                    f"module {module_id!r} has no published revision to disable"
                )
            revision = cast(int, current["revision"])
            connection.execute(
                """
                UPDATE module_revisions
                SET status = 'disabled'
                WHERE module_id = ? AND revision = ?
                """,
                (module_id, revision),
            )
            _append_audit(
                connection,
                event_type="disable",
                module_id=module_id,
                revision=revision,
            )
            stored_row = self._get_revision_row(connection, module_id, revision)
        return _stored_module(stored_row)

    def rollback(self, module_id: str, revision: int) -> StoredModule:
        with self._transaction() as connection:
            target = self._get_revision_row(connection, module_id, revision)
            if target["status"] != "disabled":
                raise InvalidModuleStateError(
                    f"module {module_id!r} revision {revision} must be disabled "
                    "before rollback"
                )
            current = self._get_published_row(connection, module_id)
            if current is None:
                raise InvalidModuleStateError(
                    f"module {module_id!r} has no published revision to roll back"
                )
            source_revision = cast(int, current["revision"])
            if source_revision == revision:
                raise InvalidModuleStateError(
                    f"module {module_id!r} revision {revision} is already published"
                )

            connection.execute(
                """
                UPDATE module_revisions
                SET status = 'disabled'
                WHERE module_id = ? AND revision = ?
                """,
                (module_id, source_revision),
            )
            connection.execute(
                """
                UPDATE module_revisions
                SET status = 'published'
                WHERE module_id = ? AND revision = ?
                """,
                (module_id, revision),
            )
            _append_audit(
                connection,
                event_type="rollback",
                module_id=module_id,
                revision=revision,
                detail={"source_revision": source_revision},
            )
            stored_row = self._get_revision_row(connection, module_id, revision)
        return _stored_module(stored_row)

    @staticmethod
    def _get_revision_row(
        connection: sqlite3.Connection, module_id: str, revision: int
    ) -> sqlite3.Row:
        row = connection.execute(
            """
            SELECT module_id, revision, status, manifest_json, created_at
            FROM module_revisions
            WHERE module_id = ? AND revision = ?
            """,
            (module_id, revision),
        ).fetchone()
        if row is None:
            raise ModuleNotFoundError(
                f"module {module_id!r} revision {revision} was not found"
            )
        return row

    @staticmethod
    def _get_published_row(
        connection: sqlite3.Connection, module_id: str
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT module_id, revision, status, manifest_json, created_at
            FROM module_revisions
            WHERE module_id = ? AND status = 'published'
            ORDER BY revision DESC
            LIMIT 1
            """,
            (module_id,),
        ).fetchone()
