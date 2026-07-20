import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from vibe_visualization_api.agent_gateway.models import AgentModuleSession


DDL = """
CREATE TABLE IF NOT EXISTS agent_module_sessions (
  user_id TEXT NOT NULL,
  agent_id TEXT NOT NULL,
  module_id TEXT NOT NULL,
  upstream_session_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (user_id, agent_id, module_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_module_upstream_session
  ON agent_module_sessions(agent_id, upstream_session_id);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AgentModuleSessionStore:
    def __init__(self, database_path: Path):
        self._database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._database_path, timeout=5.0)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.executescript(DDL)
        except BaseException:
            connection.close()
            raise
        return connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
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

    def get(
        self,
        user_id: str,
        agent_id: str,
        module_id: str,
    ) -> AgentModuleSession | None:
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT user_id, agent_id, module_id, upstream_session_id,
                       created_at, updated_at
                FROM agent_module_sessions
                WHERE user_id = ? AND agent_id = ? AND module_id = ?
                """,
                (user_id, agent_id, module_id),
            ).fetchone()
        finally:
            connection.close()
        return AgentModuleSession(**dict(row)) if row is not None else None

    def set(
        self,
        user_id: str,
        agent_id: str,
        module_id: str,
        upstream_session_id: str,
    ) -> AgentModuleSession:
        now = _utc_now()
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO agent_module_sessions (
                  user_id, agent_id, module_id, upstream_session_id,
                  created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, agent_id, module_id) DO UPDATE SET
                  upstream_session_id = excluded.upstream_session_id,
                  updated_at = excluded.updated_at
                """,
                (
                    user_id,
                    agent_id,
                    module_id,
                    upstream_session_id,
                    now,
                    now,
                ),
            )
        stored = self.get(user_id, agent_id, module_id)
        if stored is None:
            raise sqlite3.DatabaseError("failed to persist Agent session mapping")
        return stored

    def delete(self, user_id: str, agent_id: str, module_id: str) -> bool:
        with self._transaction() as connection:
            cursor = connection.execute(
                """
                DELETE FROM agent_module_sessions
                WHERE user_id = ? AND agent_id = ? AND module_id = ?
                """,
                (user_id, agent_id, module_id),
            )
        return cursor.rowcount > 0
