from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .models import (
    DecisionEvent,
    EvidenceRecord,
    Portfolio,
    PortfolioNavSnapshot,
    PortfolioTransaction,
    RunSnapshot,
    RunSummary,
    SecretMetadata,
    UserProfile,
    utc_now,
)


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    role TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolios (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    base_currency TEXT NOT NULL DEFAULT 'CNY',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_portfolios_owner ON portfolios(owner_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS user_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    last_used_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_user_tokens_user ON user_tokens(user_id);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    last_used_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id, expires_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS portfolio_transactions (
    id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    trade_date TEXT NOT NULL,
    transaction_type TEXT NOT NULL,
    asset_code TEXT NOT NULL DEFAULT '',
    asset_name TEXT NOT NULL DEFAULT '',
    asset_class TEXT NOT NULL DEFAULT 'other',
    quantity TEXT NOT NULL DEFAULT '0',
    price TEXT NOT NULL DEFAULT '0',
    amount TEXT NOT NULL DEFAULT '0',
    fees TEXT NOT NULL DEFAULT '0',
    currency TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_portfolio_transactions_date
    ON portfolio_transactions(portfolio_id, trade_date, created_at);
CREATE INDEX IF NOT EXISTS idx_portfolio_transactions_asset
    ON portfolio_transactions(portfolio_id, asset_code, trade_date);

CREATE TABLE IF NOT EXISTS portfolio_marks (
    id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    asset_code TEXT NOT NULL,
    as_of TEXT NOT NULL,
    price TEXT NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(portfolio_id, asset_code, as_of)
);
CREATE INDEX IF NOT EXISTS idx_portfolio_marks_latest
    ON portfolio_marks(portfolio_id, asset_code, as_of DESC);

CREATE TABLE IF NOT EXISTS portfolio_nav_snapshots (
    id TEXT PRIMARY KEY,
    portfolio_id TEXT NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
    as_of TEXT NOT NULL,
    cash_balance TEXT NOT NULL,
    market_value TEXT NOT NULL,
    net_asset_value TEXT NOT NULL,
    unit_count TEXT,
    unit_nav TEXT,
    total_cost TEXT NOT NULL,
    unrealized_pnl TEXT NOT NULL,
    realized_pnl TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    UNIQUE(portfolio_id, as_of)
);
CREATE INDEX IF NOT EXISTS idx_portfolio_nav_latest
    ON portfolio_nav_snapshots(portfolio_id, as_of DESC);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES users(id),
    portfolio_id TEXT REFERENCES portfolios(id),
    parent_run_id TEXT REFERENCES runs(id),
    revision INTEGER NOT NULL DEFAULT 1,
    topic TEXT NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    phase TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_event_seq INTEGER NOT NULL DEFAULT 0,
    evidence_count INTEGER NOT NULL DEFAULT 0,
    error TEXT,
    snapshot_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_runs_owner_updated ON runs(owner_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_runs_parent_revision ON runs(parent_run_id, revision);

CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    seq INTEGER NOT NULL,
    type TEXT NOT NULL,
    created_at TEXT NOT NULL,
    phase TEXT,
    agent_id TEXT,
    payload_json TEXT NOT NULL,
    UNIQUE(run_id, seq)
);
CREATE INDEX IF NOT EXISTS idx_events_run_seq ON events(run_id, seq);

CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    agent_id TEXT,
    kind TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    UNIQUE(run_id, agent_id, kind, version)
);
CREATE INDEX IF NOT EXISTS idx_artifacts_run ON artifacts(run_id, created_at);

CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    agent_id TEXT,
    source_name TEXT NOT NULL,
    source_url TEXT,
    observed_at TEXT,
    retrieved_at TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    interface_name TEXT,
    params_json TEXT NOT NULL,
    status TEXT NOT NULL,
    excerpt TEXT NOT NULL,
    content_hash TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_evidence_run_agent ON evidence(run_id, agent_id, retrieved_at);

CREATE TABLE IF NOT EXISTS secrets (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL REFERENCES users(id),
    provider TEXT NOT NULL,
    label TEXT NOT NULL,
    ciphertext TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_secrets_owner ON secrets(owner_id, provider);

CREATE TABLE IF NOT EXISTS jobs (
    run_id TEXT PRIMARY KEY REFERENCES runs(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TEXT NOT NULL,
    lease_owner TEXT,
    lease_expires_at TEXT,
    last_error TEXT,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_status_available ON jobs(status, available_at);
"""

MIGRATIONS: tuple[tuple[int, str, str], ...] = (
    (1, "persistent-runs-and-evidence", "SELECT 1;"),
    (2, "sessions-and-portfolio-ledger", "SELECT 1;"),
    (
        3,
        "durable-job-leases",
        "CREATE INDEX IF NOT EXISTS idx_jobs_active_lease ON jobs(status, lease_expires_at);",
    ),
)


class SQLiteStore:
    backend_name = "sqlite"

    def __init__(self, path: str | Path = ":memory:", default_user_id: str = "local-user") -> None:
        self.path = str(path)
        if self.path != ":memory:":
            Path(self.path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        with self._lock:
            self._connection.executescript(SCHEMA)
            self._apply_migrations()
            self._connection.execute(
                """
                INSERT INTO users(id, name, role, created_at) VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO NOTHING
                """,
                (default_user_id, "本地管理员", "owner", utc_now()),
            )
            self._connection.commit()

    @property
    def location(self) -> str:
        return self.path

    def _apply_migrations(self) -> None:
        applied = {
            int(row["version"])
            for row in self._connection.execute("SELECT version FROM schema_migrations").fetchall()
        }
        for version, name, sql in MIGRATIONS:
            if version in applied:
                continue
            self._connection.executescript(sql)
            self._connection.execute(
                "INSERT INTO schema_migrations(version, name, applied_at) VALUES (?, ?, ?)",
                (version, name, utc_now()),
            )

    def schema_version(self) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT COALESCE(MAX(version), 0) AS version FROM schema_migrations",
            ).fetchone()
        return int(row["version"])

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def save_run(self, snapshot: RunSnapshot) -> None:
        evidence_count = sum(len(runtime.evidence) for runtime in snapshot.agents.values())
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO runs(
                    id, owner_id, portfolio_id, parent_run_id, revision, topic, mode,
                    status, phase, created_at, updated_at, last_event_seq,
                    evidence_count, error, snapshot_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    owner_id=excluded.owner_id,
                    portfolio_id=excluded.portfolio_id,
                    parent_run_id=excluded.parent_run_id,
                    revision=excluded.revision,
                    topic=excluded.topic,
                    mode=excluded.mode,
                    status=excluded.status,
                    phase=excluded.phase,
                    updated_at=excluded.updated_at,
                    last_event_seq=excluded.last_event_seq,
                    evidence_count=excluded.evidence_count,
                    error=excluded.error,
                    snapshot_json=excluded.snapshot_json
                """,
                (
                    snapshot.id,
                    snapshot.owner_id,
                    snapshot.portfolio_id,
                    snapshot.parent_run_id,
                    snapshot.revision,
                    snapshot.topic,
                    snapshot.mode,
                    snapshot.status,
                    snapshot.phase,
                    snapshot.created_at,
                    snapshot.updated_at,
                    snapshot.last_event_seq,
                    evidence_count,
                    snapshot.error,
                    snapshot.model_dump_json(),
                ),
            )
            self._connection.commit()

    def load_run(self, run_id: str, owner_id: str | None = None) -> RunSnapshot | None:
        query = "SELECT snapshot_json FROM runs WHERE id=?"
        params: tuple[Any, ...] = (run_id,)
        if owner_id is not None:
            query += " AND owner_id=?"
            params = (run_id, owner_id)
        with self._lock:
            row = self._connection.execute(query, params).fetchone()
        return RunSnapshot.model_validate_json(row["snapshot_json"]) if row else None

    def load_runs(self, limit: int = 100) -> list[RunSnapshot]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT snapshot_json FROM runs ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [RunSnapshot.model_validate_json(row["snapshot_json"]) for row in rows]

    def recoverable_runs(self) -> list[RunSnapshot]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT snapshot_json FROM runs WHERE status IN ('queued', 'running') ORDER BY created_at",
            ).fetchall()
        return [RunSnapshot.model_validate_json(row["snapshot_json"]) for row in rows]

    def list_runs(self, owner_id: str, limit: int) -> list[RunSummary]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT snapshot_json, evidence_count
                FROM runs WHERE owner_id=? ORDER BY updated_at DESC LIMIT ?
                """,
                (owner_id, limit),
            ).fetchall()
        summaries = []
        for row in rows:
            snapshot = RunSnapshot.model_validate_json(row["snapshot_json"])
            summaries.append(
                RunSummary(
                    id=snapshot.id,
                    topic=snapshot.topic,
                    mode=snapshot.mode,
                    status=snapshot.status,
                    phase=snapshot.phase,
                    created_at=snapshot.created_at,
                    updated_at=snapshot.updated_at,
                    completed_agents=sum(
                        runtime.status == "completed" for runtime in snapshot.agents.values()
                    ),
                    total_agents=len(snapshot.agents),
                    error=snapshot.error,
                    owner_id=snapshot.owner_id,
                    portfolio_id=snapshot.portfolio_id,
                    parent_run_id=snapshot.parent_run_id,
                    revision=snapshot.revision,
                    evidence_count=int(row["evidence_count"]),
                ),
            )
        return summaries

    def metrics(self, owner_id: str | None = None) -> dict[str, int]:
        where = " WHERE owner_id=?" if owner_id else ""
        params = (owner_id,) if owner_id else ()
        with self._lock:
            row = self._connection.execute(
                f"""SELECT COUNT(*) AS total,
                SUM(CASE WHEN status NOT IN ('completed','failed','cancelled') THEN 1 ELSE 0 END) AS active
                FROM runs{where}""",
                params,
            ).fetchone()
        return {"total": int(row["total"] or 0), "active": int(row["active"] or 0)}

    def append_event(self, event: DecisionEvent, snapshot: RunSnapshot) -> None:
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO events(id, run_id, seq, type, created_at, phase, agent_id, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, seq) DO NOTHING
                """,
                (
                    event.id,
                    event.run_id,
                    event.seq,
                    event.type,
                    event.created_at,
                    event.phase,
                    event.agent_id,
                    json.dumps(event.payload, ensure_ascii=False, default=str),
                ),
            )
            self._connection.commit()
        self.save_run(snapshot)

    def list_events(self, run_id: str, after: int = 0) -> list[DecisionEvent]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM events WHERE run_id=? AND seq>? ORDER BY seq",
                (run_id, after),
            ).fetchall()
        return [
            DecisionEvent(
                id=row["id"],
                run_id=row["run_id"],
                seq=row["seq"],
                type=row["type"],
                created_at=row["created_at"],
                phase=row["phase"],
                agent_id=row["agent_id"],
                payload=json.loads(row["payload_json"]),
            )
            for row in rows
        ]

    def save_artifact(
        self,
        run_id: str,
        kind: str,
        title: str,
        content: str,
        version: int,
        agent_id: str | None = None,
    ) -> None:
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO artifacts(id, run_id, agent_id, kind, title, content, version, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, agent_id, kind, version) DO UPDATE SET
                    title=excluded.title, content=excluded.content
                """,
                (uuid.uuid4().hex, run_id, agent_id, kind, title, content, version, utc_now()),
            )
            self._connection.commit()

    def list_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM artifacts WHERE run_id=? ORDER BY created_at",
                (run_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_evidence(self, run_id: str, agent_id: str | None, evidence: EvidenceRecord) -> None:
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO evidence(
                    id, run_id, agent_id, source_name, source_url, observed_at,
                    retrieved_at, tool_name, interface_name, params_json, status,
                    excerpt, content_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    run_id=excluded.run_id,
                    agent_id=excluded.agent_id,
                    source_name=excluded.source_name,
                    source_url=excluded.source_url,
                    observed_at=excluded.observed_at,
                    retrieved_at=excluded.retrieved_at,
                    tool_name=excluded.tool_name,
                    interface_name=excluded.interface_name,
                    params_json=excluded.params_json,
                    status=excluded.status,
                    excerpt=excluded.excerpt,
                    content_hash=excluded.content_hash
                """,
                (
                    evidence.id,
                    run_id,
                    agent_id,
                    evidence.source_name,
                    evidence.source_url,
                    evidence.observed_at,
                    evidence.retrieved_at,
                    evidence.tool_name,
                    evidence.interface_name,
                    json.dumps(evidence.params, ensure_ascii=False, default=str),
                    evidence.status,
                    evidence.excerpt,
                    evidence.content_hash,
                ),
            )
            self._connection.commit()

    def list_evidence(self, run_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM evidence WHERE run_id=? ORDER BY retrieved_at",
                (run_id,),
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["params"] = json.loads(item.pop("params_json"))
            items.append(item)
        return items

    def enqueue_job(self, run_id: str) -> None:
        now = utc_now()
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO jobs(run_id, status, available_at, updated_at)
                VALUES (?, 'queued', ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET status='queued', available_at=excluded.available_at,
                    lease_owner=NULL, lease_expires_at=NULL, updated_at=excluded.updated_at
                """,
                (run_id, now, now),
            )
            self._connection.commit()

    def update_job(self, run_id: str, status: str, error: str | None = None) -> None:
        with self._lock:
            self._connection.execute(
                """
                UPDATE jobs SET status=?, attempts=attempts + CASE WHEN ?='running' THEN 1 ELSE 0 END,
                    last_error=?, updated_at=? WHERE run_id=?
                """,
                (status, status, error, utc_now(), run_id),
            )
            self._connection.commit()

    def ensure_job(self, run_id: str) -> None:
        now = utc_now()
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO jobs(run_id, status, available_at, updated_at)
                VALUES (?, 'queued', ?, ?)
                ON CONFLICT(run_id) DO NOTHING
                """,
                (run_id, now, now),
            )
            self._connection.commit()

    def claim_job(self, worker_id: str, lease_seconds: int) -> dict[str, Any] | None:
        now = utc_now()
        lease_expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)
        ).isoformat()
        with self._lock:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
                self._connection.execute(
                    """
                    UPDATE jobs SET status='queued', lease_owner=NULL, lease_expires_at=NULL,
                        available_at=?, updated_at=?
                    WHERE status='running' AND lease_expires_at IS NOT NULL AND lease_expires_at<=?
                    """,
                    (now, now, now),
                )
                row = self._connection.execute(
                    """
                    SELECT * FROM jobs
                    WHERE status='queued' AND available_at<=?
                    ORDER BY available_at, updated_at LIMIT 1
                    """,
                    (now,),
                ).fetchone()
                if row is None:
                    self._connection.commit()
                    return None
                self._connection.execute(
                    """
                    UPDATE jobs SET status='running', attempts=attempts+1,
                        lease_owner=?, lease_expires_at=?, updated_at=?
                    WHERE run_id=? AND status='queued'
                    """,
                    (worker_id, lease_expires_at, now, row["run_id"]),
                )
                claimed = self._connection.execute(
                    "SELECT * FROM jobs WHERE run_id=?",
                    (row["run_id"],),
                ).fetchone()
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
        return dict(claimed) if claimed else None

    def renew_job(self, run_id: str, worker_id: str, lease_seconds: int) -> bool:
        lease_expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)
        ).isoformat()
        with self._lock:
            cursor = self._connection.execute(
                """
                UPDATE jobs SET lease_expires_at=?, updated_at=?
                WHERE run_id=? AND status='running' AND lease_owner=?
                """,
                (lease_expires_at, utc_now(), run_id, worker_id),
            )
            self._connection.commit()
        return cursor.rowcount > 0

    def complete_job(self, run_id: str, worker_id: str) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                """
                UPDATE jobs SET status='completed', lease_owner=NULL, lease_expires_at=NULL,
                    last_error=NULL, updated_at=?
                WHERE run_id=? AND lease_owner=?
                """,
                (utc_now(), run_id, worker_id),
            )
            self._connection.commit()
        return cursor.rowcount > 0

    def release_job(self, run_id: str, worker_id: str, delay_seconds: float = 0) -> bool:
        available_at = (
            datetime.now(timezone.utc) + timedelta(seconds=max(0, delay_seconds))
        ).isoformat()
        with self._lock:
            cursor = self._connection.execute(
                """
                UPDATE jobs SET status='queued', available_at=?, lease_owner=NULL,
                    lease_expires_at=NULL, updated_at=?
                WHERE run_id=? AND lease_owner=?
                """,
                (available_at, utc_now(), run_id, worker_id),
            )
            self._connection.commit()
        return cursor.rowcount > 0

    def fail_job(
        self,
        run_id: str,
        worker_id: str,
        error: str,
        max_attempts: int,
        retry_delay_seconds: float,
    ) -> str:
        with self._lock:
            row = self._connection.execute(
                "SELECT attempts FROM jobs WHERE run_id=? AND lease_owner=?",
                (run_id, worker_id),
            ).fetchone()
            if row is None:
                return "missing"
            attempts = int(row["attempts"])
            status = "queued" if attempts < max_attempts else "failed"
            available_at = (
                datetime.now(timezone.utc)
                + timedelta(seconds=retry_delay_seconds if status == "queued" else 0)
            ).isoformat()
            self._connection.execute(
                """
                UPDATE jobs SET status=?, available_at=?, lease_owner=NULL,
                    lease_expires_at=NULL, last_error=?, updated_at=? WHERE run_id=?
                """,
                (status, available_at, error, utc_now(), run_id),
            )
            self._connection.commit()
        return status

    def cancel_job(self, run_id: str) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                """
                UPDATE jobs SET status='cancelled', lease_owner=NULL,
                    lease_expires_at=NULL, updated_at=?
                WHERE run_id=? AND status NOT IN ('completed','failed','cancelled')
                """,
                (utc_now(), run_id),
            )
            self._connection.commit()
        return cursor.rowcount > 0

    def job_stats(self) -> dict[str, Any]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT status, COUNT(*) AS count FROM jobs GROUP BY status",
            ).fetchall()
            oldest = self._connection.execute(
                "SELECT available_at FROM jobs WHERE status='queued' ORDER BY available_at LIMIT 1",
            ).fetchone()
            attempts = self._connection.execute(
                "SELECT COALESCE(MAX(attempts), 0) AS value FROM jobs",
            ).fetchone()
        counts = {row["status"]: int(row["count"]) for row in rows}
        return {
            "total": sum(counts.values()),
            "queued": counts.get("queued", 0),
            "running": counts.get("running", 0),
            "completed": counts.get("completed", 0),
            "failed": counts.get("failed", 0),
            "cancelled": counts.get("cancelled", 0),
            "oldest_queued_at": oldest["available_at"] if oldest else None,
            "max_attempts_seen": int(attempts["value"]),
        }

    def list_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM jobs ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_user(self, user_id: str) -> UserProfile | None:
        with self._lock:
            row = self._connection.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return UserProfile.model_validate(dict(row)) if row else None

    def list_users(self) -> list[UserProfile]:
        with self._lock:
            rows = self._connection.execute("SELECT * FROM users ORDER BY created_at").fetchall()
        return [UserProfile.model_validate(dict(row)) for row in rows]

    def create_user(self, name: str, role: str, token_hash: str) -> UserProfile:
        user = UserProfile(id=uuid.uuid4().hex, name=name, role=role, created_at=utc_now())
        with self._lock:
            self._connection.execute(
                "INSERT INTO users(id, name, role, created_at) VALUES (?, ?, ?, ?)",
                (user.id, user.name, user.role, user.created_at),
            )
            self._connection.execute(
                "INSERT INTO user_tokens(id, user_id, token_hash, created_at) VALUES (?, ?, ?, ?)",
                (uuid.uuid4().hex, user.id, token_hash, user.created_at),
            )
            self._connection.commit()
        return user

    def verify_user_token(self, user_id: str, token_hash: str) -> bool:
        with self._lock:
            row = self._connection.execute(
                "SELECT id FROM user_tokens WHERE user_id=? AND token_hash=?",
                (user_id, token_hash),
            ).fetchone()
            if row:
                self._connection.execute(
                    "UPDATE user_tokens SET last_used_at=? WHERE id=?",
                    (utc_now(), row["id"]),
                )
                self._connection.commit()
        return row is not None

    def create_session(self, user_id: str, token_hash: str, expires_at: str) -> None:
        now = utc_now()
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO sessions(id, user_id, token_hash, created_at, expires_at, last_used_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (uuid.uuid4().hex, user_id, token_hash, now, expires_at, now),
            )
            self._connection.commit()

    def get_session_user(self, token_hash: str) -> UserProfile | None:
        now = utc_now()
        with self._lock:
            self._connection.execute("DELETE FROM sessions WHERE expires_at<=?", (now,))
            row = self._connection.execute(
                """
                SELECT users.*, sessions.id AS session_id
                FROM sessions JOIN users ON users.id=sessions.user_id
                WHERE sessions.token_hash=? AND sessions.expires_at>?
                """,
                (token_hash, now),
            ).fetchone()
            if row:
                self._connection.execute(
                    "UPDATE sessions SET last_used_at=? WHERE id=?",
                    (now, row["session_id"]),
                )
            self._connection.commit()
        if row is None:
            return None
        return UserProfile.model_validate(
            {key: row[key] for key in ("id", "name", "role", "created_at")},
        )

    def delete_session(self, token_hash: str) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM sessions WHERE token_hash=?",
                (token_hash,),
            )
            self._connection.commit()
        return cursor.rowcount > 0

    def create_portfolio(
        self,
        owner_id: str,
        name: str,
        description: str,
        base_currency: str,
    ) -> Portfolio:
        now = utc_now()
        portfolio = Portfolio(
            id=uuid.uuid4().hex,
            owner_id=owner_id,
            name=name,
            description=description,
            base_currency=base_currency.upper(),
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO portfolios(id, owner_id, name, description, base_currency, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    portfolio.id,
                    portfolio.owner_id,
                    portfolio.name,
                    portfolio.description,
                    portfolio.base_currency,
                    portfolio.created_at,
                    portfolio.updated_at,
                ),
            )
            self._connection.commit()
        return portfolio

    def list_portfolios(self, owner_id: str) -> list[Portfolio]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM portfolios WHERE owner_id=? ORDER BY updated_at DESC",
                (owner_id,),
            ).fetchall()
        return [Portfolio.model_validate(dict(row)) for row in rows]

    def get_portfolio(self, portfolio_id: str, owner_id: str) -> Portfolio | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM portfolios WHERE id=? AND owner_id=?",
                (portfolio_id, owner_id),
            ).fetchone()
        return Portfolio.model_validate(dict(row)) if row else None

    def create_portfolio_transaction(
        self,
        transaction: PortfolioTransaction,
    ) -> PortfolioTransaction:
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO portfolio_transactions(
                    id, portfolio_id, trade_date, transaction_type, asset_code,
                    asset_name, asset_class, quantity, price, amount, fees,
                    currency, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transaction.id,
                    transaction.portfolio_id,
                    transaction.trade_date.isoformat(),
                    transaction.transaction_type,
                    transaction.asset_code,
                    transaction.asset_name,
                    transaction.asset_class,
                    str(transaction.quantity),
                    str(transaction.price),
                    str(transaction.amount),
                    str(transaction.fees),
                    transaction.currency,
                    transaction.notes,
                    transaction.created_at,
                ),
            )
            self._connection.execute(
                "UPDATE portfolios SET updated_at=? WHERE id=?",
                (transaction.created_at, transaction.portfolio_id),
            )
            self._connection.commit()
        return transaction

    def list_portfolio_transactions(self, portfolio_id: str) -> list[PortfolioTransaction]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM portfolio_transactions
                WHERE portfolio_id=? ORDER BY trade_date, created_at, id
                """,
                (portfolio_id,),
            ).fetchall()
        return [PortfolioTransaction.model_validate(dict(row)) for row in rows]

    def save_portfolio_marks(
        self,
        portfolio_id: str,
        as_of: str,
        marks: list[tuple[str, str, str]],
    ) -> None:
        now = utc_now()
        with self._lock:
            for asset_code, price, source in marks:
                self._connection.execute(
                    """
                    INSERT INTO portfolio_marks(
                        id, portfolio_id, asset_code, as_of, price, source, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(portfolio_id, asset_code, as_of) DO UPDATE SET
                        price=excluded.price,
                        source=excluded.source,
                        created_at=excluded.created_at
                    """,
                    (uuid.uuid4().hex, portfolio_id, asset_code, as_of, price, source, now),
                )
            self._connection.commit()

    def list_portfolio_marks(self, portfolio_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM portfolio_marks
                WHERE portfolio_id=? ORDER BY as_of DESC, created_at DESC
                """,
                (portfolio_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_nav_snapshot(self, snapshot: PortfolioNavSnapshot) -> PortfolioNavSnapshot:
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO portfolio_nav_snapshots(
                    id, portfolio_id, as_of, cash_balance, market_value,
                    net_asset_value, unit_count, unit_nav, total_cost,
                    unrealized_pnl, realized_pnl, note, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(portfolio_id, as_of) DO UPDATE SET
                    cash_balance=excluded.cash_balance,
                    market_value=excluded.market_value,
                    net_asset_value=excluded.net_asset_value,
                    unit_count=excluded.unit_count,
                    unit_nav=excluded.unit_nav,
                    total_cost=excluded.total_cost,
                    unrealized_pnl=excluded.unrealized_pnl,
                    realized_pnl=excluded.realized_pnl,
                    note=excluded.note,
                    created_at=excluded.created_at
                """,
                (
                    snapshot.id,
                    snapshot.portfolio_id,
                    snapshot.as_of.isoformat(),
                    str(snapshot.cash_balance),
                    str(snapshot.market_value),
                    str(snapshot.net_asset_value),
                    str(snapshot.unit_count) if snapshot.unit_count is not None else None,
                    str(snapshot.unit_nav) if snapshot.unit_nav is not None else None,
                    str(snapshot.total_cost),
                    str(snapshot.unrealized_pnl),
                    str(snapshot.realized_pnl),
                    snapshot.note,
                    snapshot.created_at,
                ),
            )
            self._connection.execute(
                "UPDATE portfolios SET updated_at=? WHERE id=?",
                (snapshot.created_at, snapshot.portfolio_id),
            )
            self._connection.commit()
        return snapshot

    def list_nav_snapshots(self, portfolio_id: str, limit: int = 90) -> list[PortfolioNavSnapshot]:
        with self._lock:
            rows = self._connection.execute(
                """
                SELECT * FROM portfolio_nav_snapshots
                WHERE portfolio_id=? ORDER BY as_of DESC LIMIT ?
                """,
                (portfolio_id, limit),
            ).fetchall()
        return [PortfolioNavSnapshot.model_validate(dict(row)) for row in rows]

    def create_secret(
        self,
        owner_id: str,
        provider: str,
        label: str,
        ciphertext: str,
    ) -> SecretMetadata:
        now = utc_now()
        secret = SecretMetadata(
            id=uuid.uuid4().hex,
            owner_id=owner_id,
            provider=provider,
            label=label,
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._connection.execute(
                """
                INSERT INTO secrets(id, owner_id, provider, label, ciphertext, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (secret.id, owner_id, provider, label, ciphertext, now, now),
            )
            self._connection.commit()
        return secret

    def list_secrets(self, owner_id: str) -> list[SecretMetadata]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT id, owner_id, provider, label, created_at, updated_at FROM secrets WHERE owner_id=? ORDER BY updated_at DESC",
                (owner_id,),
            ).fetchall()
        return [SecretMetadata.model_validate(dict(row)) for row in rows]

    def get_secret_ciphertext(self, secret_id: str, owner_id: str) -> tuple[str, str] | None:
        with self._lock:
            row = self._connection.execute(
                "SELECT provider, ciphertext FROM secrets WHERE id=? AND owner_id=?",
                (secret_id, owner_id),
            ).fetchone()
        return (row["provider"], row["ciphertext"]) if row else None

    def delete_secret(self, secret_id: str, owner_id: str) -> bool:
        with self._lock:
            cursor = self._connection.execute(
                "DELETE FROM secrets WHERE id=? AND owner_id=?",
                (secret_id, owner_id),
            )
            self._connection.commit()
        return cursor.rowcount > 0


class _PostgresConnection:
    def __init__(self, dsn: str) -> None:
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as error:
            raise RuntimeError(
                "PostgreSQL存储需要安装 agentscope[orchestra] 或 psycopg[binary]。",
            ) from error
        self._connection = psycopg.connect(dsn, autocommit=True, row_factory=dict_row)

    @staticmethod
    def _convert_query(sql: str) -> str:
        if sql.strip().upper() == "BEGIN IMMEDIATE":
            return "BEGIN"
        return sql.replace("?", "%s")

    def execute(self, sql: str, params: tuple[Any, ...] = ()):
        return self._connection.execute(self._convert_query(sql), params)

    def executescript(self, script: str) -> None:
        for statement in script.split(";"):
            sql = statement.strip()
            if not sql or sql.upper().startswith("PRAGMA "):
                continue
            self._connection.execute(sql)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()


class PostgresStore(SQLiteStore):
    backend_name = "postgresql"

    def __init__(self, dsn: str, default_user_id: str = "local-user") -> None:
        self.path = dsn
        self._lock = threading.RLock()
        self._connection = _PostgresConnection(dsn)
        with self._lock:
            self._connection.executescript(SCHEMA)
            self._apply_migrations()
            self._connection.execute(
                """
                INSERT INTO users(id, name, role, created_at) VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO NOTHING
                """,
                (default_user_id, "本地管理员", "owner", utc_now()),
            )
            self._connection.commit()

    @property
    def location(self) -> str:
        return re.sub(r"(://[^:/@]+:)[^@]+(@)", r"\1***\2", self.path)

    def claim_job(self, worker_id: str, lease_seconds: int) -> dict[str, Any] | None:
        now = utc_now()
        lease_expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=lease_seconds)
        ).isoformat()
        with self._lock:
            try:
                self._connection.execute("BEGIN")
                self._connection.execute(
                    """
                    UPDATE jobs SET status='queued', lease_owner=NULL, lease_expires_at=NULL,
                        available_at=?, updated_at=?
                    WHERE status='running' AND lease_expires_at IS NOT NULL AND lease_expires_at<=?
                    """,
                    (now, now, now),
                )
                row = self._connection.execute(
                    """
                    SELECT * FROM jobs
                    WHERE status='queued' AND available_at<=?
                    ORDER BY available_at, updated_at
                    FOR UPDATE SKIP LOCKED LIMIT 1
                    """,
                    (now,),
                ).fetchone()
                if row is None:
                    self._connection.commit()
                    return None
                self._connection.execute(
                    """
                    UPDATE jobs SET status='running', attempts=attempts+1,
                        lease_owner=?, lease_expires_at=?, updated_at=?
                    WHERE run_id=? AND status='queued'
                    """,
                    (worker_id, lease_expires_at, now, row["run_id"]),
                )
                claimed = self._connection.execute(
                    "SELECT * FROM jobs WHERE run_id=?",
                    (row["run_id"],),
                ).fetchone()
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
        return dict(claimed) if claimed else None


def create_store(
    database_url: str | None,
    database_path: str | Path,
    default_user_id: str = "local-user",
) -> SQLiteStore:
    if not database_url:
        return SQLiteStore(database_path, default_user_id)
    if database_url.startswith(("postgresql://", "postgres://")):
        return PostgresStore(database_url, default_user_id)
    if database_url.startswith("sqlite:///"):
        return SQLiteStore(database_url.removeprefix("sqlite:///"), default_user_id)
    raise ValueError("ORCHESTRA_DATABASE_URL仅支持postgresql://或sqlite:///。")
