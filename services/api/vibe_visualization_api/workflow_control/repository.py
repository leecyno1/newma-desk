from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from vibe_visualization_api.workflow_control.definition import normalize_workflow_matrix
from vibe_visualization_api.workflow_control.state import recalculate_run_status


SCHEMA = """
CREATE TABLE IF NOT EXISTS workflow_organizations (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workflow_principals (
  organization_id TEXT NOT NULL,
  id TEXT NOT NULL,
  kind TEXT NOT NULL,
  name TEXT NOT NULL,
  role TEXT NOT NULL,
  status TEXT NOT NULL,
  external_ref TEXT,
  endpoint TEXT,
  capabilities_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (organization_id, id)
);

CREATE INDEX IF NOT EXISTS workflow_principals_org_kind
ON workflow_principals(organization_id, kind, name);

CREATE TABLE IF NOT EXISTS workflow_templates (
  organization_id TEXT NOT NULL,
  id TEXT NOT NULL,
  name TEXT NOT NULL,
  description TEXT NOT NULL,
  owner_principal_id TEXT NOT NULL,
  current_version INTEGER NOT NULL,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (organization_id, id)
);

CREATE TABLE IF NOT EXISTS workflow_template_versions (
  organization_id TEXT NOT NULL,
  template_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  definition_json TEXT NOT NULL,
  change_note TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (organization_id, template_id, version)
);

CREATE TABLE IF NOT EXISTS workflow_runs (
  organization_id TEXT NOT NULL,
  id TEXT NOT NULL,
  template_id TEXT NOT NULL,
  template_version INTEGER NOT NULL,
  title TEXT NOT NULL,
  status TEXT NOT NULL,
  owner_principal_id TEXT NOT NULL,
  revision INTEGER NOT NULL,
  document_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (organization_id, id)
);

CREATE INDEX IF NOT EXISTS workflow_runs_org_updated
ON workflow_runs(organization_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS workflow_delegation_grants (
  organization_id TEXT NOT NULL,
  id TEXT NOT NULL,
  delegator_principal_id TEXT NOT NULL,
  delegate_principal_id TEXT NOT NULL,
  scope_type TEXT NOT NULL,
  template_id TEXT,
  run_id TEXT,
  node_id TEXT,
  role_key TEXT,
  actions_json TEXT NOT NULL,
  starts_at TEXT NOT NULL,
  expires_at TEXT,
  allow_redelegate INTEGER NOT NULL,
  max_redelegation_depth INTEGER NOT NULL,
  parent_grant_id TEXT,
  status TEXT NOT NULL,
  revoked_at TEXT,
  revoked_by TEXT,
  created_at TEXT NOT NULL,
  PRIMARY KEY (organization_id, id)
);

CREATE INDEX IF NOT EXISTS workflow_grants_delegate
ON workflow_delegation_grants(organization_id, delegate_principal_id, status);

CREATE INDEX IF NOT EXISTS workflow_grants_parent
ON workflow_delegation_grants(organization_id, parent_grant_id);

CREATE TABLE IF NOT EXISTS workflow_node_data (
  organization_id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  node_id TEXT NOT NULL,
  slot_key TEXT NOT NULL,
  version INTEGER NOT NULL,
  payload_json TEXT NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (organization_id, run_id, node_id, slot_key, version)
);

CREATE INDEX IF NOT EXISTS workflow_node_data_current
ON workflow_node_data(organization_id, run_id, node_id, slot_key, version DESC);

CREATE TABLE IF NOT EXISTS workflow_artifacts (
  organization_id TEXT NOT NULL,
  id TEXT NOT NULL,
  run_id TEXT NOT NULL,
  node_id TEXT NOT NULL,
  artifact_key TEXT NOT NULL,
  version INTEGER NOT NULL,
  label TEXT NOT NULL,
  kind TEXT NOT NULL,
  uri TEXT,
  content_json TEXT,
  metadata_json TEXT NOT NULL,
  input_artifact_ids_json TEXT NOT NULL,
  is_current INTEGER NOT NULL,
  stale INTEGER NOT NULL,
  created_by TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (organization_id, id),
  UNIQUE (organization_id, run_id, node_id, artifact_key, version)
);

CREATE INDEX IF NOT EXISTS workflow_artifacts_run_current
ON workflow_artifacts(organization_id, run_id, is_current, created_at DESC);

CREATE TABLE IF NOT EXISTS workflow_events (
  sequence INTEGER PRIMARY KEY AUTOINCREMENT,
  organization_id TEXT NOT NULL,
  run_id TEXT,
  event_type TEXT NOT NULL,
  actor_principal_id TEXT NOT NULL,
  accountable_principal_id TEXT,
  delegation_grant_id TEXT,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS workflow_events_org_sequence
ON workflow_events(organization_id, sequence DESC);

CREATE INDEX IF NOT EXISTS workflow_events_run_sequence
ON workflow_events(organization_id, run_id, sequence DESC);
"""


class WorkflowNotFoundError(Exception):
    """Raised when a scoped workflow entity does not exist."""


class WorkflowConflictError(Exception):
    """Raised when a workflow mutation targets stale state."""


class WorkflowClaimConflictError(Exception):
    """Raised when another principal owns an active node lease."""


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class WorkflowRepository:
    def __init__(self, database_path: Path):
        self._database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @staticmethod
    def _prepare(connection: sqlite3.Connection) -> None:
        connection.executescript(SCHEMA)

    @staticmethod
    def _decode(value: str | None, default: Any = None) -> Any:
        if value is None:
            return default
        return json.loads(value)

    @staticmethod
    def _event(
        connection: sqlite3.Connection,
        *,
        organization_id: str,
        event_type: str,
        actor_principal_id: str,
        payload: dict[str, Any],
        run_id: str | None = None,
        accountable_principal_id: str | None = None,
        delegation_grant_id: str | None = None,
    ) -> int:
        cursor = connection.execute(
            """
            INSERT INTO workflow_events (
              organization_id, run_id, event_type, actor_principal_id,
              accountable_principal_id, delegation_grant_id,
              payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                organization_id,
                run_id,
                event_type,
                actor_principal_id,
                accountable_principal_id,
                delegation_grant_id,
                json.dumps(payload, ensure_ascii=False),
                now_iso(),
            ),
        )
        return int(cursor.lastrowid)

    @staticmethod
    def _principal(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "organizationId": row["organization_id"],
            "kind": row["kind"],
            "name": row["name"],
            "role": row["role"],
            "status": row["status"],
            "externalRef": row["external_ref"],
            "endpoint": row["endpoint"],
            "capabilities": json.loads(row["capabilities_json"]),
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    @staticmethod
    def _grant(row: sqlite3.Row) -> dict[str, Any]:
        scope = {"type": row["scope_type"]}
        for database_name, field_name in (
            ("template_id", "templateId"),
            ("run_id", "runId"),
            ("node_id", "nodeId"),
            ("role_key", "roleKey"),
        ):
            if row[database_name]:
                scope[field_name] = row[database_name]
        return {
            "id": row["id"],
            "organizationId": row["organization_id"],
            "delegatorPrincipalId": row["delegator_principal_id"],
            "delegatePrincipalId": row["delegate_principal_id"],
            "scope": scope,
            "actions": json.loads(row["actions_json"]),
            "startsAt": row["starts_at"],
            "expiresAt": row["expires_at"],
            "allowRedelegate": bool(row["allow_redelegate"]),
            "maxRedelegationDepth": row["max_redelegation_depth"],
            "parentGrantId": row["parent_grant_id"],
            "status": row["status"],
            "revokedAt": row["revoked_at"],
            "revokedBy": row["revoked_by"],
            "createdAt": row["created_at"],
        }

    def ensure_identity(self, *, organization_id: str, user_id: str) -> dict[str, Any]:
        principal_id = f"human:{user_id}"
        timestamp = now_iso()
        with self._connect() as connection:
            self._prepare(connection)
            connection.execute(
                """
                INSERT OR IGNORE INTO workflow_organizations (
                  id, name, created_at, updated_at
                ) VALUES (?, ?, ?, ?)
                """,
                (organization_id, organization_id, timestamp, timestamp),
            )
            existing = connection.execute(
                """
                SELECT * FROM workflow_principals
                WHERE organization_id = ? AND id = ?
                """,
                (organization_id, principal_id),
            ).fetchone()
            if existing is None:
                count = int(
                    connection.execute(
                        """
                        SELECT COUNT(*) FROM workflow_principals
                        WHERE organization_id = ?
                        """,
                        (organization_id,),
                    ).fetchone()[0]
                )
                role = "owner" if count == 0 else "member"
                connection.execute(
                    """
                    INSERT INTO workflow_principals (
                      organization_id, id, kind, name, role, status,
                      external_ref, endpoint, capabilities_json,
                      created_at, updated_at
                    ) VALUES (?, ?, 'human', ?, ?, 'active', ?, NULL, '[]', ?, ?)
                    """,
                    (
                        organization_id,
                        principal_id,
                        user_id,
                        role,
                        user_id,
                        timestamp,
                        timestamp,
                    ),
                )
                existing = connection.execute(
                    """
                    SELECT * FROM workflow_principals
                    WHERE organization_id = ? AND id = ?
                    """,
                    (organization_id, principal_id),
                ).fetchone()
        assert existing is not None
        return self._principal(existing)

    def get_organization(self, organization_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            self._prepare(connection)
            row = connection.execute(
                "SELECT * FROM workflow_organizations WHERE id = ?",
                (organization_id,),
            ).fetchone()
        if row is None:
            raise WorkflowNotFoundError(organization_id)
        return {
            "id": row["id"],
            "name": row["name"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def list_principals(self, organization_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            self._prepare(connection)
            rows = connection.execute(
                """
                SELECT * FROM workflow_principals
                WHERE organization_id = ?
                ORDER BY CASE role WHEN 'owner' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END,
                         kind, name, id
                """,
                (organization_id,),
            ).fetchall()
        return [self._principal(row) for row in rows]

    def get_principal(self, organization_id: str, principal_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            self._prepare(connection)
            row = connection.execute(
                """
                SELECT * FROM workflow_principals
                WHERE organization_id = ? AND id = ?
                """,
                (organization_id, principal_id),
            ).fetchone()
        if row is None:
            raise WorkflowNotFoundError(principal_id)
        return self._principal(row)

    def create_principal(
        self,
        *,
        organization_id: str,
        principal: dict[str, Any],
        actor_principal_id: str,
    ) -> dict[str, Any]:
        timestamp = now_iso()
        principal_id = principal.get("principalId") or (
            ("agent:" if principal["kind"] == "server_agent" else "human:")
            + uuid4().hex[:12]
        )
        with self._connect() as connection:
            self._prepare(connection)
            try:
                connection.execute(
                    """
                    INSERT INTO workflow_principals (
                      organization_id, id, kind, name, role, status,
                      external_ref, endpoint, capabilities_json,
                      created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?)
                    """,
                    (
                        organization_id,
                        principal_id,
                        principal["kind"],
                        principal["name"],
                        principal["role"],
                        principal.get("externalRef"),
                        principal.get("endpoint"),
                        json.dumps(principal.get("capabilities", []), ensure_ascii=False),
                        timestamp,
                        timestamp,
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise WorkflowConflictError(principal_id) from error
            self._event(
                connection,
                organization_id=organization_id,
                event_type="principal.created",
                actor_principal_id=actor_principal_id,
                payload={"principalId": principal_id, "kind": principal["kind"]},
            )
            row = connection.execute(
                """
                SELECT * FROM workflow_principals
                WHERE organization_id = ? AND id = ?
                """,
                (organization_id, principal_id),
            ).fetchone()
        assert row is not None
        return self._principal(row)

    def list_templates(self, organization_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            self._prepare(connection)
            rows = connection.execute(
                """
                SELECT * FROM workflow_templates
                WHERE organization_id = ?
                ORDER BY updated_at DESC, id
                """,
                (organization_id,),
            ).fetchall()
            return [self._template_with_definition(connection, row) for row in rows]

    def get_template(self, organization_id: str, template_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            self._prepare(connection)
            row = connection.execute(
                """
                SELECT * FROM workflow_templates
                WHERE organization_id = ? AND id = ?
                """,
                (organization_id, template_id),
            ).fetchone()
            if row is None:
                raise WorkflowNotFoundError(template_id)
            return self._template_with_definition(connection, row)

    def list_template_versions(
        self,
        organization_id: str,
        template_id: str,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            self._prepare(connection)
            exists = connection.execute(
                """
                SELECT 1 FROM workflow_templates
                WHERE organization_id = ? AND id = ?
                """,
                (organization_id, template_id),
            ).fetchone()
            if exists is None:
                raise WorkflowNotFoundError(template_id)
            rows = connection.execute(
                """
                SELECT * FROM workflow_template_versions
                WHERE organization_id = ? AND template_id = ?
                ORDER BY version DESC
                """,
                (organization_id, template_id),
            ).fetchall()
        return [
            {
                **normalize_workflow_matrix(json.loads(row["definition_json"])),
                "templateId": template_id,
                "version": row["version"],
                "changeNote": row["change_note"],
                "createdBy": row["created_by"],
                "createdAt": row["created_at"],
            }
            for row in rows
        ]

    def get_template_version(
        self,
        organization_id: str,
        template_id: str,
        version: int,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            self._prepare(connection)
            row = connection.execute(
                """
                SELECT * FROM workflow_template_versions
                WHERE organization_id = ? AND template_id = ? AND version = ?
                """,
                (organization_id, template_id, version),
            ).fetchone()
        if row is None:
            raise WorkflowNotFoundError(f"{template_id}@{version}")
        definition = normalize_workflow_matrix(json.loads(row["definition_json"]))
        return {
            **definition,
            "templateId": template_id,
            "version": version,
            "changeNote": row["change_note"],
            "createdBy": row["created_by"],
            "createdAt": row["created_at"],
        }

    @staticmethod
    def _template_with_definition(
        connection: sqlite3.Connection,
        row: sqlite3.Row,
    ) -> dict[str, Any]:
        version = connection.execute(
            """
            SELECT * FROM workflow_template_versions
            WHERE organization_id = ? AND template_id = ? AND version = ?
            """,
            (row["organization_id"], row["id"], row["current_version"]),
        ).fetchone()
        assert version is not None
        definition = normalize_workflow_matrix(json.loads(version["definition_json"]))
        return {
            "id": row["id"],
            "organizationId": row["organization_id"],
            "name": row["name"],
            "description": row["description"],
            "ownerPrincipalId": row["owner_principal_id"],
            "currentVersion": row["current_version"],
            "status": row["status"],
            "nodes": definition["nodes"],
            "edges": definition["edges"],
            "lanes": definition["lanes"],
            "stages": definition["stages"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def create_template(
        self,
        *,
        organization_id: str,
        template_id: str,
        definition: dict[str, Any],
        actor_principal_id: str,
        change_note: str = "Initial version",
    ) -> dict[str, Any]:
        timestamp = now_iso()
        with self._connect() as connection:
            self._prepare(connection)
            try:
                connection.execute(
                    """
                    INSERT INTO workflow_templates (
                      organization_id, id, name, description, owner_principal_id,
                      current_version, status, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 1, 'active', ?, ?)
                    """,
                    (
                        organization_id,
                        template_id,
                        definition["name"],
                        definition.get("description", ""),
                        actor_principal_id,
                        timestamp,
                        timestamp,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO workflow_template_versions (
                      organization_id, template_id, version, definition_json,
                      change_note, created_by, created_at
                    ) VALUES (?, ?, 1, ?, ?, ?, ?)
                    """,
                    (
                        organization_id,
                        template_id,
                        json.dumps(definition, ensure_ascii=False),
                        change_note,
                        actor_principal_id,
                        timestamp,
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise WorkflowConflictError(template_id) from error
            self._event(
                connection,
                organization_id=organization_id,
                event_type="template.created",
                actor_principal_id=actor_principal_id,
                payload={"templateId": template_id, "version": 1},
            )
            row = connection.execute(
                """
                SELECT * FROM workflow_templates
                WHERE organization_id = ? AND id = ?
                """,
                (organization_id, template_id),
            ).fetchone()
            assert row is not None
            return self._template_with_definition(connection, row)

    def add_template_version(
        self,
        *,
        organization_id: str,
        template_id: str,
        definition: dict[str, Any],
        expected_version: int,
        change_note: str,
        actor_principal_id: str,
    ) -> dict[str, Any]:
        timestamp = now_iso()
        with self._connect() as connection:
            self._prepare(connection)
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT * FROM workflow_templates
                WHERE organization_id = ? AND id = ?
                """,
                (organization_id, template_id),
            ).fetchone()
            if row is None:
                raise WorkflowNotFoundError(template_id)
            if row["current_version"] != expected_version:
                raise WorkflowConflictError(template_id)
            next_version = expected_version + 1
            connection.execute(
                """
                INSERT INTO workflow_template_versions (
                  organization_id, template_id, version, definition_json,
                  change_note, created_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    organization_id,
                    template_id,
                    next_version,
                    json.dumps(definition, ensure_ascii=False),
                    change_note,
                    actor_principal_id,
                    timestamp,
                ),
            )
            connection.execute(
                """
                UPDATE workflow_templates
                SET name = ?, description = ?, current_version = ?, updated_at = ?
                WHERE organization_id = ? AND id = ?
                """,
                (
                    definition["name"],
                    definition.get("description", ""),
                    next_version,
                    timestamp,
                    organization_id,
                    template_id,
                ),
            )
            self._event(
                connection,
                organization_id=organization_id,
                event_type="template.version.created",
                actor_principal_id=actor_principal_id,
                payload={"templateId": template_id, "version": next_version},
            )
            updated = connection.execute(
                """
                SELECT * FROM workflow_templates
                WHERE organization_id = ? AND id = ?
                """,
                (organization_id, template_id),
            ).fetchone()
            assert updated is not None
            return self._template_with_definition(connection, updated)

    def list_runs(self, organization_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            self._prepare(connection)
            rows = connection.execute(
                """
                SELECT document_json FROM workflow_runs
                WHERE organization_id = ?
                ORDER BY updated_at DESC, id
                """,
                (organization_id,),
            ).fetchall()
        return [normalize_workflow_matrix(json.loads(row["document_json"])) for row in rows]

    def get_run(self, organization_id: str, run_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            self._prepare(connection)
            row = connection.execute(
                """
                SELECT document_json FROM workflow_runs
                WHERE organization_id = ? AND id = ?
                """,
                (organization_id, run_id),
            ).fetchone()
        if row is None:
            raise WorkflowNotFoundError(run_id)
        return normalize_workflow_matrix(json.loads(row["document_json"]))

    def create_run(
        self,
        *,
        organization_id: str,
        document: dict[str, Any],
        actor_principal_id: str,
    ) -> dict[str, Any]:
        with self._connect() as connection:
            self._prepare(connection)
            try:
                connection.execute(
                    """
                    INSERT INTO workflow_runs (
                      organization_id, id, template_id, template_version, title,
                      status, owner_principal_id, revision, document_json,
                      created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        organization_id,
                        document["id"],
                        document["templateId"],
                        document["templateVersion"],
                        document["title"],
                        document["status"],
                        document["ownerPrincipalId"],
                        document["revision"],
                        json.dumps(document, ensure_ascii=False),
                        document["createdAt"],
                        document["updatedAt"],
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise WorkflowConflictError(document["id"]) from error
            self._event(
                connection,
                organization_id=organization_id,
                run_id=document["id"],
                event_type="run.created",
                actor_principal_id=actor_principal_id,
                accountable_principal_id=actor_principal_id,
                payload={
                    "runId": document["id"],
                    "templateId": document["templateId"],
                    "templateVersion": document["templateVersion"],
                },
            )
        return document

    @staticmethod
    def _write_run(
        connection: sqlite3.Connection,
        *,
        organization_id: str,
        document: dict[str, Any],
        expected_revision: int,
    ) -> dict[str, Any]:
        row = connection.execute(
            """
            SELECT revision FROM workflow_runs
            WHERE organization_id = ? AND id = ?
            """,
            (organization_id, document["id"]),
        ).fetchone()
        if row is None:
            raise WorkflowNotFoundError(document["id"])
        if row["revision"] != expected_revision:
            raise WorkflowConflictError(document["id"])
        updated = dict(document)
        updated["revision"] = expected_revision + 1
        updated["updatedAt"] = now_iso()
        cursor = connection.execute(
            """
            UPDATE workflow_runs
            SET title = ?, status = ?, revision = ?, document_json = ?, updated_at = ?
            WHERE organization_id = ? AND id = ? AND revision = ?
            """,
            (
                updated["title"],
                updated["status"],
                updated["revision"],
                json.dumps(updated, ensure_ascii=False),
                updated["updatedAt"],
                organization_id,
                updated["id"],
                expected_revision,
            ),
        )
        if cursor.rowcount != 1:
            raise WorkflowConflictError(document["id"])
        return updated

    def mutate_run(
        self,
        *,
        organization_id: str,
        run_id: str,
        expected_revision: int,
        mutate: Callable[[dict[str, Any]], dict[str, Any]],
        event_type: str,
        actor_principal_id: str,
        accountable_principal_id: str | None,
        delegation_grant_id: str | None,
        event_payload: dict[str, Any],
    ) -> dict[str, Any]:
        with self._connect() as connection:
            self._prepare(connection)
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT document_json FROM workflow_runs
                WHERE organization_id = ? AND id = ?
                """,
                (organization_id, run_id),
            ).fetchone()
            if row is None:
                raise WorkflowNotFoundError(run_id)
            document = mutate(json.loads(row["document_json"]))
            updated = self._write_run(
                connection,
                organization_id=organization_id,
                document=document,
                expected_revision=expected_revision,
            )
            self._event(
                connection,
                organization_id=organization_id,
                run_id=run_id,
                event_type=event_type,
                actor_principal_id=actor_principal_id,
                accountable_principal_id=accountable_principal_id,
                delegation_grant_id=delegation_grant_id,
                payload=event_payload,
            )
            return updated

    def add_node_data(
        self,
        *,
        organization_id: str,
        run_id: str,
        node_id: str,
        slot_key: str,
        payload: Any,
        document: dict[str, Any],
        expected_revision: int,
        actor_principal_id: str,
        accountable_principal_id: str | None,
        delegation_grant_id: str | None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        timestamp = now_iso()
        with self._connect() as connection:
            self._prepare(connection)
            connection.execute("BEGIN IMMEDIATE")
            version = int(
                connection.execute(
                    """
                    SELECT COALESCE(MAX(version), 0) + 1
                    FROM workflow_node_data
                    WHERE organization_id = ? AND run_id = ? AND node_id = ? AND slot_key = ?
                    """,
                    (organization_id, run_id, node_id, slot_key),
                ).fetchone()[0]
            )
            connection.execute(
                """
                INSERT INTO workflow_node_data (
                  organization_id, run_id, node_id, slot_key, version,
                  payload_json, created_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    organization_id,
                    run_id,
                    node_id,
                    slot_key,
                    version,
                    json.dumps(payload, ensure_ascii=False),
                    actor_principal_id,
                    timestamp,
                ),
            )
            updated = self._write_run(
                connection,
                organization_id=organization_id,
                document=document,
                expected_revision=expected_revision,
            )
            record = {
                "runId": run_id,
                "nodeId": node_id,
                "slotKey": slot_key,
                "version": version,
                "payload": payload,
                "createdBy": actor_principal_id,
                "createdAt": timestamp,
            }
            self._event(
                connection,
                organization_id=organization_id,
                run_id=run_id,
                event_type="node.data.saved",
                actor_principal_id=actor_principal_id,
                accountable_principal_id=accountable_principal_id,
                delegation_grant_id=delegation_grant_id,
                payload={"nodeId": node_id, "slotKey": slot_key, "version": version},
            )
            return updated, record

    def list_node_data(
        self,
        organization_id: str,
        run_id: str,
        node_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT * FROM workflow_node_data
            WHERE organization_id = ? AND run_id = ?
        """
        parameters: list[Any] = [organization_id, run_id]
        if node_id:
            query += " AND node_id = ?"
            parameters.append(node_id)
        query += " ORDER BY node_id, slot_key, version DESC"
        with self._connect() as connection:
            self._prepare(connection)
            rows = connection.execute(query, parameters).fetchall()
        return [
            {
                "runId": row["run_id"],
                "nodeId": row["node_id"],
                "slotKey": row["slot_key"],
                "version": row["version"],
                "payload": json.loads(row["payload_json"]),
                "createdBy": row["created_by"],
                "createdAt": row["created_at"],
            }
            for row in rows
        ]

    def add_artifact(
        self,
        *,
        organization_id: str,
        run_id: str,
        node_id: str,
        artifact: dict[str, Any],
        document: dict[str, Any],
        expected_revision: int,
        actor_principal_id: str,
        accountable_principal_id: str | None,
        delegation_grant_id: str | None,
    ) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
        timestamp = now_iso()
        artifact_id = f"artifact-{uuid4().hex}"
        stale_nodes: set[str] = set()
        with self._connect() as connection:
            self._prepare(connection)
            connection.execute("BEGIN IMMEDIATE")
            previous = connection.execute(
                """
                SELECT * FROM workflow_artifacts
                WHERE organization_id = ? AND run_id = ? AND node_id = ?
                  AND artifact_key = ? AND is_current = 1
                """,
                (organization_id, run_id, node_id, artifact["artifactKey"]),
            ).fetchone()
            version = 1 if previous is None else int(previous["version"]) + 1
            if previous is not None:
                connection.execute(
                    """
                    UPDATE workflow_artifacts SET is_current = 0
                    WHERE organization_id = ? AND id = ?
                    """,
                    (organization_id, previous["id"]),
                )
            input_ids = artifact.get("inputArtifactIds", [])
            for input_id in input_ids:
                exists = connection.execute(
                    """
                    SELECT 1 FROM workflow_artifacts
                    WHERE organization_id = ? AND id = ? AND run_id = ?
                    """,
                    (organization_id, input_id, run_id),
                ).fetchone()
                if exists is None:
                    raise WorkflowNotFoundError(input_id)
            connection.execute(
                """
                INSERT INTO workflow_artifacts (
                  organization_id, id, run_id, node_id, artifact_key, version,
                  label, kind, uri, content_json, metadata_json,
                  input_artifact_ids_json, is_current, stale, created_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?)
                """,
                (
                    organization_id,
                    artifact_id,
                    run_id,
                    node_id,
                    artifact["artifactKey"],
                    version,
                    artifact["label"],
                    artifact["kind"],
                    artifact.get("uri"),
                    (
                        json.dumps(artifact.get("content"), ensure_ascii=False)
                        if artifact.get("content") is not None
                        else None
                    ),
                    json.dumps(artifact.get("metadata", {}), ensure_ascii=False),
                    json.dumps(input_ids, ensure_ascii=False),
                    actor_principal_id,
                    timestamp,
                ),
            )
            if previous is not None:
                frontier = {previous["id"]}
                visited: set[str] = set()
                rows = connection.execute(
                    """
                    SELECT * FROM workflow_artifacts
                    WHERE organization_id = ? AND run_id = ? AND is_current = 1 AND stale = 0
                    """,
                    (organization_id, run_id),
                ).fetchall()
                while frontier:
                    next_frontier: set[str] = set()
                    for row in rows:
                        if row["id"] in visited:
                            continue
                        parents = set(json.loads(row["input_artifact_ids_json"]))
                        if parents.intersection(frontier):
                            visited.add(row["id"])
                            next_frontier.add(row["id"])
                            stale_nodes.add(row["node_id"])
                    frontier = next_frontier
                if visited:
                    placeholders = ",".join("?" for _ in visited)
                    connection.execute(
                        f"""
                        UPDATE workflow_artifacts SET stale = 1
                        WHERE organization_id = ? AND id IN ({placeholders})
                        """,
                        [organization_id, *sorted(visited)],
                    )
            if stale_nodes:
                for node in document["nodes"]:
                    if node["id"] in stale_nodes and node["status"] not in {
                        "cancelled",
                        "skipped",
                    }:
                        node["status"] = "stale"
                        node["updatedAt"] = timestamp
                recalculate_run_status(document)
            updated = self._write_run(
                connection,
                organization_id=organization_id,
                document=document,
                expected_revision=expected_revision,
            )
            record = {
                "id": artifact_id,
                "runId": run_id,
                "nodeId": node_id,
                "artifactKey": artifact["artifactKey"],
                "version": version,
                "label": artifact["label"],
                "kind": artifact["kind"],
                "uri": artifact.get("uri"),
                "content": artifact.get("content"),
                "metadata": artifact.get("metadata", {}),
                "inputArtifactIds": input_ids,
                "isCurrent": True,
                "stale": False,
                "createdBy": actor_principal_id,
                "createdAt": timestamp,
            }
            self._event(
                connection,
                organization_id=organization_id,
                run_id=run_id,
                event_type="artifact.version.created",
                actor_principal_id=actor_principal_id,
                accountable_principal_id=accountable_principal_id,
                delegation_grant_id=delegation_grant_id,
                payload={
                    "nodeId": node_id,
                    "artifactId": artifact_id,
                    "artifactKey": artifact["artifactKey"],
                    "version": version,
                    "staleNodeIds": sorted(stale_nodes),
                },
            )
            return updated, record, sorted(stale_nodes)

    def list_artifacts(
        self,
        organization_id: str,
        run_id: str | None = None,
        *,
        current_only: bool = False,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM workflow_artifacts WHERE organization_id = ?"
        parameters: list[Any] = [organization_id]
        if run_id:
            query += " AND run_id = ?"
            parameters.append(run_id)
        if current_only:
            query += " AND is_current = 1"
        query += " ORDER BY created_at DESC, id"
        with self._connect() as connection:
            self._prepare(connection)
            rows = connection.execute(query, parameters).fetchall()
        return [
            {
                "id": row["id"],
                "runId": row["run_id"],
                "nodeId": row["node_id"],
                "artifactKey": row["artifact_key"],
                "version": row["version"],
                "label": row["label"],
                "kind": row["kind"],
                "uri": row["uri"],
                "content": self._decode(row["content_json"]),
                "metadata": json.loads(row["metadata_json"]),
                "inputArtifactIds": json.loads(row["input_artifact_ids_json"]),
                "isCurrent": bool(row["is_current"]),
                "stale": bool(row["stale"]),
                "createdBy": row["created_by"],
                "createdAt": row["created_at"],
            }
            for row in rows
        ]

    def create_grant(
        self,
        *,
        organization_id: str,
        grant: dict[str, Any],
    ) -> dict[str, Any]:
        scope = grant["scope"]
        with self._connect() as connection:
            self._prepare(connection)
            connection.execute(
                """
                INSERT INTO workflow_delegation_grants (
                  organization_id, id, delegator_principal_id, delegate_principal_id,
                  scope_type, template_id, run_id, node_id, role_key,
                  actions_json, starts_at, expires_at, allow_redelegate,
                  max_redelegation_depth, parent_grant_id, status,
                  revoked_at, revoked_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', NULL, NULL, ?)
                """,
                (
                    organization_id,
                    grant["id"],
                    grant["delegatorPrincipalId"],
                    grant["delegatePrincipalId"],
                    scope["type"],
                    scope.get("templateId"),
                    scope.get("runId"),
                    scope.get("nodeId"),
                    scope.get("roleKey"),
                    json.dumps(grant["actions"], ensure_ascii=False),
                    grant["startsAt"],
                    grant.get("expiresAt"),
                    int(grant["allowRedelegate"]),
                    grant["maxRedelegationDepth"],
                    grant.get("parentGrantId"),
                    grant["createdAt"],
                ),
            )
            self._event(
                connection,
                organization_id=organization_id,
                event_type="delegation.granted",
                actor_principal_id=grant["delegatorPrincipalId"],
                delegation_grant_id=grant["id"],
                payload={
                    "grantId": grant["id"],
                    "delegatePrincipalId": grant["delegatePrincipalId"],
                    "scope": scope,
                    "actions": grant["actions"],
                },
            )
            row = connection.execute(
                """
                SELECT * FROM workflow_delegation_grants
                WHERE organization_id = ? AND id = ?
                """,
                (organization_id, grant["id"]),
            ).fetchone()
        assert row is not None
        return self._grant(row)

    def get_grant(self, organization_id: str, grant_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            self._prepare(connection)
            row = connection.execute(
                """
                SELECT * FROM workflow_delegation_grants
                WHERE organization_id = ? AND id = ?
                """,
                (organization_id, grant_id),
            ).fetchone()
        if row is None:
            raise WorkflowNotFoundError(grant_id)
        return self._grant(row)

    def list_grants(
        self,
        organization_id: str,
        principal_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT * FROM workflow_delegation_grants
            WHERE organization_id = ?
        """
        parameters: list[Any] = [organization_id]
        if principal_id:
            query += " AND (delegator_principal_id = ? OR delegate_principal_id = ?)"
            parameters.extend((principal_id, principal_id))
        query += " ORDER BY created_at DESC, id"
        with self._connect() as connection:
            self._prepare(connection)
            rows = connection.execute(query, parameters).fetchall()
        return [self._grant(row) for row in rows]

    def revoke_grant(
        self,
        *,
        organization_id: str,
        grant_id: str,
        actor_principal_id: str,
    ) -> list[str]:
        timestamp = now_iso()
        with self._connect() as connection:
            self._prepare(connection)
            connection.execute("BEGIN IMMEDIATE")
            root = connection.execute(
                """
                SELECT * FROM workflow_delegation_grants
                WHERE organization_id = ? AND id = ?
                """,
                (organization_id, grant_id),
            ).fetchone()
            if root is None:
                raise WorkflowNotFoundError(grant_id)
            revoked: list[str] = []
            frontier = [grant_id]
            while frontier:
                current = frontier.pop(0)
                if current in revoked:
                    continue
                revoked.append(current)
                children = connection.execute(
                    """
                    SELECT id FROM workflow_delegation_grants
                    WHERE organization_id = ? AND parent_grant_id = ?
                    """,
                    (organization_id, current),
                ).fetchall()
                frontier.extend(row["id"] for row in children)
            placeholders = ",".join("?" for _ in revoked)
            connection.execute(
                f"""
                UPDATE workflow_delegation_grants
                SET status = 'revoked', revoked_at = ?, revoked_by = ?
                WHERE organization_id = ? AND id IN ({placeholders})
                """,
                [timestamp, actor_principal_id, organization_id, *revoked],
            )
            self._event(
                connection,
                organization_id=organization_id,
                event_type="delegation.revoked",
                actor_principal_id=actor_principal_id,
                delegation_grant_id=grant_id,
                payload={"grantId": grant_id, "cascadeGrantIds": revoked},
            )
        return revoked

    def list_events(
        self,
        organization_id: str,
        *,
        run_id: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM workflow_events WHERE organization_id = ?"
        parameters: list[Any] = [organization_id]
        if run_id:
            query += " AND run_id = ?"
            parameters.append(run_id)
        query += " ORDER BY sequence DESC LIMIT ?"
        parameters.append(limit)
        with self._connect() as connection:
            self._prepare(connection)
            rows = connection.execute(query, parameters).fetchall()
        return [
            {
                "sequence": row["sequence"],
                "organizationId": row["organization_id"],
                "runId": row["run_id"],
                "type": row["event_type"],
                "actorPrincipalId": row["actor_principal_id"],
                "accountablePrincipalId": row["accountable_principal_id"],
                "delegationGrantId": row["delegation_grant_id"],
                "payload": json.loads(row["payload_json"]),
                "createdAt": row["created_at"],
            }
            for row in rows
        ]
