from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS global_topic_observations (
  topic_id TEXT NOT NULL,
  series_id TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  value REAL NOT NULL,
  unit TEXT NOT NULL,
  source TEXT NOT NULL,
  PRIMARY KEY (topic_id, series_id, observed_at)
);
CREATE INDEX IF NOT EXISTS idx_global_topic_observations
ON global_topic_observations(topic_id, series_id, observed_at);

CREATE TABLE IF NOT EXISTS global_topic_events (
  id TEXT PRIMARY KEY,
  topic_id TEXT NOT NULL,
  event_date TEXT NOT NULL,
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  source TEXT NOT NULL,
  source_url TEXT NOT NULL,
  impact TEXT NOT NULL,
  confidence REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_global_topic_events
ON global_topic_events(topic_id, event_date DESC);

CREATE TABLE IF NOT EXISTS global_topic_forecasts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  topic_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  factors_json TEXT NOT NULL,
  result_json TEXT NOT NULL
);
"""


class GlobalTopicStore:
    def __init__(self, database_path: Path):
        self._database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.executescript(SCHEMA)
        return connection

    def seed(self, observations: list[dict[str, Any]], events: list[dict[str, Any]]) -> None:
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT OR IGNORE INTO global_topic_observations
                  (topic_id, series_id, observed_at, value, unit, source)
                VALUES (:topicId, :seriesId, :date, :value, :unit, :source)
                """,
                observations,
            )
            connection.executemany(
                """
                INSERT OR IGNORE INTO global_topic_events
                  (id, topic_id, event_date, title, summary, source, source_url, impact, confidence)
                VALUES (:id, :topicId, :date, :title, :summary, :source, :sourceUrl, :impact, :confidence)
                """,
                events,
            )

    def observations(self, topic_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM global_topic_observations WHERE topic_id = ? ORDER BY observed_at",
                (topic_id,),
            ).fetchall()
        return [
            {
                "seriesId": row["series_id"],
                "date": row["observed_at"],
                "value": row["value"],
                "unit": row["unit"],
                "source": row["source"],
            }
            for row in rows
        ]

    def events(self, topic_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM global_topic_events WHERE topic_id = ? ORDER BY event_date DESC",
                (topic_id,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "date": row["event_date"],
                "title": row["title"],
                "summary": row["summary"],
                "source": row["source"],
                "sourceUrl": row["source_url"],
                "impact": row["impact"],
                "confidence": row["confidence"],
            }
            for row in rows
        ]

    def save_forecast(self, topic_id: str, created_at: str, factors: dict[str, float], result: dict[str, Any]) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT INTO global_topic_forecasts (topic_id, created_at, factors_json, result_json) VALUES (?, ?, ?, ?)",
                (topic_id, created_at, json.dumps(factors), json.dumps(result, ensure_ascii=False)),
            )
