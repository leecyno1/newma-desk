import json
import re
import sqlite3
from collections.abc import Callable, Iterator
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
        connection = connect(self._database_path, initialize=True)
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
        with self._transaction() as connection:
            stored_row = self._create_draft_row(
                connection,
                manifest,
                event_type="create_draft",
            )
        return _stored_module(stored_row)

    def import_draft(
        self,
        manifest: dict[str, object],
        install_package: Callable[[int], Callable[[], None]],
    ) -> StoredModule:
        undo_install: Callable[[], None] | None = None
        try:
            with self._transaction() as connection:
                stored_row = self._create_draft_row(
                    connection,
                    manifest,
                    event_type="import",
                )
                undo_install = install_package(cast(int, stored_row["revision"]))
        except BaseException:
            if undo_install is not None:
                undo_install()
            raise
        return _stored_module(stored_row)

    def record_export(self, module_id: str, revision: int) -> StoredModule:
        with self._transaction() as connection:
            stored_row = self._get_revision_row(
                connection,
                module_id,
                revision,
            )
            _append_audit(
                connection,
                event_type="export",
                module_id=module_id,
                revision=revision,
            )
        return _stored_module(stored_row)

    def _create_draft_row(
        self,
        connection: sqlite3.Connection,
        manifest: dict[str, object],
        *,
        event_type: str,
    ) -> sqlite3.Row:
        module_id = manifest.get("id")
        if (
            not isinstance(module_id, str)
            or MODULE_ID_PATTERN.fullmatch(module_id) is None
        ):
            raise ValueError("manifest['id'] must match ^[a-z][a-z0-9-]{2,63}$")

        manifest_json = _json_dumps(manifest)
        created_at = _utc_now()
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
            event_type=event_type,
            module_id=module_id,
            revision=revision,
        )
        return self._get_revision_row(connection, module_id, revision)

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

    def list_installed(self) -> list[StoredModule]:
        """Return the active published revision or latest disabled revision."""

        connection = connect(self._database_path)
        try:
            rows = connection.execute(
                """
                WITH ranked AS (
                  SELECT
                    module_id,
                    revision,
                    status,
                    manifest_json,
                    created_at,
                    ROW_NUMBER() OVER (
                      PARTITION BY module_id
                      ORDER BY
                        CASE status WHEN 'published' THEN 0 ELSE 1 END,
                        revision DESC
                    ) AS position
                  FROM module_revisions
                  WHERE status IN ('published', 'disabled')
                )
                SELECT module_id, revision, status, manifest_json, created_at
                FROM ranked
                WHERE position = 1
                ORDER BY module_id
                """
            ).fetchall()
            return [_stored_module(row) for row in rows]
        finally:
            connection.close()

    def install_batch(
        self,
        manifests: list[dict[str, object]],
    ) -> list[StoredModule]:
        """Install and publish a group of manifests in one transaction."""

        module_ids = [manifest.get("id") for manifest in manifests]
        if len(module_ids) != len(set(module_ids)):
            raise ValueError("batch manifests must contain unique module IDs")

        stored_rows: list[sqlite3.Row] = []
        with self._transaction() as connection:
            for manifest in manifests:
                module_id = manifest.get("id")
                if (
                    not isinstance(module_id, str)
                    or MODULE_ID_PATTERN.fullmatch(module_id) is None
                ):
                    raise ValueError("manifest['id'] must match ^[a-z][a-z0-9-]{2,63}$")

                current = self._get_installed_row(connection, module_id)
                if current is not None and current["manifest_json"] == _json_dumps(
                    manifest
                ):
                    if current["status"] == "disabled":
                        connection.execute(
                            """
                            UPDATE module_revisions
                            SET status = 'published'
                            WHERE module_id = ? AND revision = ?
                            """,
                            (module_id, current["revision"]),
                        )
                        _append_audit(
                            connection,
                            event_type="enable",
                            module_id=module_id,
                            revision=cast(int, current["revision"]),
                        )
                        current = self._get_revision_row(
                            connection,
                            module_id,
                            cast(int, current["revision"]),
                        )
                    stored_rows.append(current)
                    continue

                draft = self._create_draft_row(
                    connection,
                    manifest,
                    event_type="store_install",
                )
                revision = cast(int, draft["revision"])
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
                stored_rows.append(
                    self._get_revision_row(connection, module_id, revision)
                )
        return [_stored_module(row) for row in stored_rows]

    def get_revision(self, module_id: str, revision: int) -> StoredModule:
        connection = connect(self._database_path)
        try:
            row = self._get_revision_row(connection, module_id, revision)
            return _stored_module(row)
        finally:
            connection.close()

    def get_published(self, module_id: str) -> StoredModule:
        connection = connect(self._database_path)
        try:
            row = self._get_published_row(connection, module_id)
            if row is None:
                exists = connection.execute(
                    "SELECT 1 FROM module_revisions WHERE module_id = ? LIMIT 1",
                    (module_id,),
                ).fetchone()
                if exists is None:
                    raise ModuleNotFoundError(f"module {module_id!r} was not found")
                raise InvalidModuleStateError(
                    f"module {module_id!r} has no published revision"
                )
            return _stored_module(row)
        finally:
            connection.close()

    def record_action_audit(
        self,
        module_id: str,
        revision: int,
        detail: dict[str, object],
    ) -> None:
        with self._transaction() as connection:
            self._get_revision_row(connection, module_id, revision)
            _append_audit(
                connection,
                event_type="module_action",
                module_id=module_id,
                revision=revision,
                detail=detail,
            )

    def disable(self, module_id: str) -> StoredModule:
        with self._transaction() as connection:
            current = self._get_published_row(connection, module_id)
            if current is None:
                exists = connection.execute(
                    """
                    SELECT 1
                    FROM module_revisions
                    WHERE module_id = ?
                    LIMIT 1
                    """,
                    (module_id,),
                ).fetchone()
                if exists is None:
                    raise ModuleNotFoundError(f"module {module_id!r} was not found")
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
            source_revision: int | None = None
            if current is not None:
                source_revision = cast(int, current["revision"])
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

    @staticmethod
    def _get_installed_row(
        connection: sqlite3.Connection, module_id: str
    ) -> sqlite3.Row | None:
        return connection.execute(
            """
            SELECT module_id, revision, status, manifest_json, created_at
            FROM module_revisions
            WHERE module_id = ? AND status IN ('published', 'disabled')
            ORDER BY
              CASE status WHEN 'published' THEN 0 ELSE 1 END,
              revision DESC
            LIMIT 1
            """,
            (module_id,),
        ).fetchone()
