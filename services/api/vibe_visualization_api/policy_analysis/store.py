from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS policy_events (
  id TEXT PRIMARY KEY,
  source_url TEXT NOT NULL,
  title TEXT NOT NULL,
  event_date TEXT NOT NULL,
  institution TEXT NOT NULL,
  category TEXT NOT NULL,
  level INTEGER NOT NULL CHECK(level IN (1, 2, 3)),
  status TEXT NOT NULL,
  certainty TEXT NOT NULL,
  summary TEXT NOT NULL,
  rationale_json TEXT NOT NULL,
  market_scope_json TEXT NOT NULL,
  discovered_by TEXT,
  assessment_confidence REAL NOT NULL DEFAULT 0,
  assessment_status TEXT NOT NULL DEFAULT 'machine',
  document_type TEXT NOT NULL DEFAULT 'formal-policy',
  lifecycle_stage TEXT NOT NULL DEFAULT 'published',
  policy_series_key TEXT NOT NULL DEFAULT '',
  entities_json TEXT NOT NULL DEFAULT '[]',
  content_hash TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_policy_events_date
ON policy_events(event_date DESC);
CREATE INDEX IF NOT EXISTS idx_policy_events_status_level
ON policy_events(status, level);
CREATE INDEX IF NOT EXISTS idx_policy_events_source_url
ON policy_events(source_url);

CREATE TABLE IF NOT EXISTS policy_source_runs (
  source_id TEXT PRIMARY KEY,
  status TEXT NOT NULL,
  items INTEGER NOT NULL DEFAULT 0,
  last_attempt_at TEXT NOT NULL,
  last_success_at TEXT,
  last_error TEXT
);

CREATE TABLE IF NOT EXISTS policy_assessment_reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  policy_id TEXT NOT NULL,
  previous_level INTEGER NOT NULL,
  level INTEGER NOT NULL,
  note TEXT NOT NULL,
  reviewed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_policy_assessment_reviews_policy
ON policy_assessment_reviews(policy_id, reviewed_at DESC);
"""


class PolicyStore:
    def __init__(self, database_path: Path):
        self._database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.executescript(SCHEMA)
        columns = {row["name"] for row in connection.execute("PRAGMA table_info(policy_events)")}
        if "document_type" not in columns:
            connection.execute(
                "ALTER TABLE policy_events ADD COLUMN document_type TEXT NOT NULL DEFAULT 'formal-policy'"
            )
            columns.add("document_type")
        if "lifecycle_stage" not in columns:
            connection.execute("ALTER TABLE policy_events ADD COLUMN lifecycle_stage TEXT NOT NULL DEFAULT 'published'")
        if "policy_series_key" not in columns:
            connection.execute("ALTER TABLE policy_events ADD COLUMN policy_series_key TEXT NOT NULL DEFAULT ''")
        if "entities_json" not in columns:
            connection.execute("ALTER TABLE policy_events ADD COLUMN entities_json TEXT NOT NULL DEFAULT '[]'")
        return connection

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _event(row: sqlite3.Row) -> dict[str, Any]:
        event = {
            "id": row["id"],
            "title": row["title"],
            "date": row["event_date"],
            "institution": row["institution"],
            "category": row["category"],
            "level": row["level"],
            "status": row["status"],
            "certainty": row["certainty"],
            "summary": row["summary"],
            "rationale": json.loads(row["rationale_json"]),
            "sourceUrl": row["source_url"],
            "marketScope": json.loads(row["market_scope_json"]),
            "assessmentConfidence": row["assessment_confidence"],
            "assessmentStatus": row["assessment_status"],
            "documentType": row["document_type"],
            "lifecycleStage": row["lifecycle_stage"],
            "policySeriesKey": row["policy_series_key"] or row["id"],
            "entities": json.loads(row["entities_json"]),
            "firstSeenAt": row["first_seen_at"],
            "lastSeenAt": row["last_seen_at"],
        }
        if row["discovered_by"]:
            event["discoveredBy"] = row["discovered_by"]
        return event

    def upsert_events(self, events: list[dict[str, Any]]) -> None:
        if not events:
            return
        now = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for event in events:
                content_hash = str(event.get("contentHash") or event["id"])
                connection.execute(
                    """
                    INSERT INTO policy_events (
                      id, source_url, title, event_date, institution, category,
                      level, status, certainty, summary, rationale_json,
                      market_scope_json, discovered_by, assessment_confidence,
                      assessment_status, document_type, lifecycle_stage, policy_series_key, entities_json,
                      content_hash, first_seen_at, last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                      title = excluded.title,
                      event_date = excluded.event_date,
                      institution = excluded.institution,
                      category = excluded.category,
                      level = CASE
                        WHEN policy_events.assessment_status = 'reviewed'
                        THEN policy_events.level ELSE excluded.level END,
                      status = excluded.status,
                      certainty = excluded.certainty,
                      summary = excluded.summary,
                      rationale_json = CASE
                        WHEN policy_events.assessment_status = 'reviewed'
                        THEN policy_events.rationale_json ELSE excluded.rationale_json END,
                      market_scope_json = excluded.market_scope_json,
                      discovered_by = excluded.discovered_by,
                      assessment_confidence = CASE
                        WHEN policy_events.assessment_status = 'reviewed'
                        THEN policy_events.assessment_confidence
                        ELSE excluded.assessment_confidence END,
                      assessment_status = CASE
                        WHEN policy_events.assessment_status = 'reviewed'
                        THEN policy_events.assessment_status
                        ELSE excluded.assessment_status END,
                      document_type = excluded.document_type,
                      lifecycle_stage = excluded.lifecycle_stage,
                      policy_series_key = excluded.policy_series_key,
                      entities_json = excluded.entities_json,
                      content_hash = excluded.content_hash,
                      last_seen_at = excluded.last_seen_at
                    """,
                    (
                        event["id"], event["sourceUrl"], event["title"],
                        event["date"], event["institution"], event["category"],
                        event["level"], event["status"], event["certainty"],
                        event["summary"], self._json(event["rationale"]),
                        self._json(event["marketScope"]), event.get("discoveredBy"),
                        float(event.get("assessmentConfidence", 1)),
                        event.get("assessmentStatus", "machine"),
                        event.get("documentType", "formal-policy"),
                        event.get("lifecycleStage", "published"),
                        event.get("policySeriesKey", event["id"]),
                        self._json(event.get("entities", [])),
                        content_hash, now, now,
                    ),
                )

    def list_events(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM policy_events ORDER BY event_date DESC, last_seen_at DESC"
            ).fetchall()
        return [self._event(row) for row in rows]

    def review_assessment(self, event_id: str, level: int, note: str) -> dict[str, Any] | None:
        now = datetime.now(UTC).isoformat()
        review_note = note.strip() or "研究员人工确认量级"
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM policy_events WHERE id = ?", (event_id,)
            ).fetchone()
            if row is None:
                return None
            rationale = json.loads(row["rationale_json"])
            rationale = [item for item in rationale if not item.startswith("人工复核：")]
            rationale.append(f"人工复核：{review_note}")
            connection.execute(
                """
                UPDATE policy_events SET level = ?, rationale_json = ?,
                  assessment_confidence = 1, assessment_status = 'reviewed',
                  last_seen_at = ? WHERE id = ?
                """,
                (level, self._json(rationale), now, event_id),
            )
            connection.execute(
                """
                INSERT INTO policy_assessment_reviews
                  (policy_id, previous_level, level, note, reviewed_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (event_id, row["level"], level, review_note, now),
            )
            updated = connection.execute(
                "SELECT * FROM policy_events WHERE id = ?", (event_id,)
            ).fetchone()
        return self._event(updated) if updated else None

    def record_source_runs(self, feeds: list[dict[str, Any]], attempted_at: str) -> None:
        if not feeds:
            return
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            for feed in feeds:
                succeeded = feed["status"] == "ok"
                connection.execute(
                    """
                    INSERT INTO policy_source_runs (
                      source_id, status, items, last_attempt_at, last_success_at, last_error
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source_id) DO UPDATE SET
                      status = excluded.status,
                      items = excluded.items,
                      last_attempt_at = excluded.last_attempt_at,
                      last_success_at = CASE WHEN excluded.status = 'ok'
                        THEN excluded.last_attempt_at ELSE policy_source_runs.last_success_at END,
                      last_error = excluded.last_error
                    """,
                    (
                        feed["sourceId"], feed["status"], feed["items"], attempted_at,
                        attempted_at if succeeded else None, feed.get("reason"),
                    ),
                )

    def source_runs(self) -> dict[str, dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM policy_source_runs").fetchall()
        return {
            row["source_id"]: {
                "sourceId": row["source_id"],
                "status": row["status"],
                "items": row["items"],
                "lastAttemptAt": row["last_attempt_at"],
                "lastSuccessAt": row["last_success_at"],
                **({"reason": row["last_error"]} if row["last_error"] else {}),
            }
            for row in rows
        }
