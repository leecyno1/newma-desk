import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_conversation_turns (
  user_id TEXT NOT NULL,
  agent_id TEXT NOT NULL,
  module_id TEXT NOT NULL,
  sequence INTEGER NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
  content TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (user_id, agent_id, module_id, sequence)
);
CREATE INDEX IF NOT EXISTS idx_agent_conversation_recent
  ON agent_conversation_turns(user_id, agent_id, module_id, sequence DESC);
"""


class AgentConversationStore:
    def __init__(self, database_path: Path):
        self._database_path = database_path
        self._initialized = False
        self._initialize_lock = threading.Lock()

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        with self._initialize_lock:
            if self._initialized:
                return
            self._database_path.parent.mkdir(parents=True, exist_ok=True)
            with sqlite3.connect(self._database_path, timeout=10) as connection:
                connection.executescript(SCHEMA)
            self._initialized = True

    def _connect(self) -> sqlite3.Connection:
        self._ensure_initialized()
        connection = sqlite3.connect(self._database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def recent(
        self,
        user_id: str,
        agent_id: str,
        module_id: str,
        limit: int = 12,
    ) -> list[dict[str, str]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT role, content
                FROM agent_conversation_turns
                WHERE user_id = ? AND agent_id = ? AND module_id = ?
                ORDER BY sequence DESC
                LIMIT ?
                """,
                (user_id, agent_id, module_id, limit),
            ).fetchall()
        return [
            {"role": row["role"], "content": row["content"]}
            for row in reversed(rows)
        ]

    def append_exchange(
        self,
        user_id: str,
        agent_id: str,
        module_id: str,
        prompt: str,
        answer: str,
    ) -> None:
        created_at = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT COALESCE(MAX(sequence), 0) AS last_sequence
                FROM agent_conversation_turns
                WHERE user_id = ? AND agent_id = ? AND module_id = ?
                """,
                (user_id, agent_id, module_id),
            ).fetchone()
            next_sequence = int(row["last_sequence"]) + 1
            connection.executemany(
                """
                INSERT INTO agent_conversation_turns (
                  user_id, agent_id, module_id, sequence, role, content, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        user_id,
                        agent_id,
                        module_id,
                        next_sequence,
                        "user",
                        prompt,
                        created_at,
                    ),
                    (
                        user_id,
                        agent_id,
                        module_id,
                        next_sequence + 1,
                        "assistant",
                        answer,
                        created_at,
                    ),
                ],
            )
