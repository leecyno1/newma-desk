import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from vibe_visualization_api.wiki.models import (
    WikiHandoff,
    WikiSubjectMatch,
    WikiSubjectRef,
)


DDL = """
CREATE TABLE IF NOT EXISTS wiki_handoffs (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  workspace_id TEXT NOT NULL,
  target_mod_id TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  expires_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wiki_handoffs_scope
ON wiki_handoffs(user_id, workspace_id, target_mod_id, expires_at);
CREATE TABLE IF NOT EXISTS wiki_subjects (
  canonical_id TEXT PRIMARY KEY,
  subject_type TEXT NOT NULL,
  display_name TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  market TEXT,
  symbol TEXT,
  asset_type TEXT,
  source TEXT NOT NULL,
  confidence REAL NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_wiki_subjects_identity
ON wiki_subjects(subject_type, market, symbol);
CREATE INDEX IF NOT EXISTS idx_wiki_subjects_name
ON wiki_subjects(normalized_name);
CREATE TABLE IF NOT EXISTS wiki_subject_aliases (
  canonical_id TEXT NOT NULL,
  alias TEXT NOT NULL,
  normalized_alias TEXT NOT NULL,
  source TEXT NOT NULL,
  confidence REAL NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (canonical_id, normalized_alias),
  FOREIGN KEY (canonical_id) REFERENCES wiki_subjects(canonical_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_wiki_subject_aliases_lookup
ON wiki_subject_aliases(normalized_alias);
CREATE TABLE IF NOT EXISTS wiki_subject_concepts (
  canonical_id TEXT NOT NULL,
  concept_id TEXT NOT NULL,
  source TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (canonical_id, concept_id),
  FOREIGN KEY (canonical_id) REFERENCES wiki_subjects(canonical_id) ON DELETE CASCADE
);
"""


class WikiHandoffNotFoundError(KeyError):
    pass


class WikiHandoffStore:
    def __init__(self, database_path: Path):
        self._database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.executescript(DDL)
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

    def put(
        self,
        *,
        user_id: str,
        workspace_id: str,
        handoff: WikiHandoff,
    ) -> WikiHandoff:
        payload = handoff.model_dump(by_alias=True, mode="json")
        with self._transaction() as connection:
            self._delete_expired(connection)
            connection.execute(
                """
                INSERT INTO wiki_handoffs (
                  id, user_id, workspace_id, target_mod_id,
                  payload_json, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    handoff.id,
                    user_id,
                    workspace_id,
                    handoff.target_mod_id,
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    handoff.expires_at.isoformat(),
                ),
            )
        return handoff

    def get(
        self,
        *,
        handoff_id: str,
        user_id: str,
        workspace_id: str,
    ) -> WikiHandoff:
        with self._transaction() as connection:
            self._delete_expired(connection)
            row = connection.execute(
                """
                SELECT payload_json
                FROM wiki_handoffs
                WHERE id = ? AND user_id = ? AND workspace_id = ?
                """,
                (handoff_id, user_id, workspace_id),
            ).fetchone()
        if row is None:
            raise WikiHandoffNotFoundError(handoff_id)
        return WikiHandoff.model_validate(json.loads(row["payload_json"]))

    def delete(
        self,
        *,
        handoff_id: str,
        user_id: str,
        workspace_id: str,
    ) -> None:
        with self._transaction() as connection:
            result = connection.execute(
                """
                DELETE FROM wiki_handoffs
                WHERE id = ? AND user_id = ? AND workspace_id = ?
                """,
                (handoff_id, user_id, workspace_id),
            )
        if result.rowcount != 1:
            raise WikiHandoffNotFoundError(handoff_id)

    @staticmethod
    def _delete_expired(connection: sqlite3.Connection) -> None:
        connection.execute(
            "DELETE FROM wiki_handoffs WHERE expires_at <= ?",
            (datetime.now(timezone.utc).isoformat(),),
        )


def normalize_wiki_alias(value: str) -> str:
    return re.sub(r"[\s·/_\-.]+", "", value.casefold()).strip()


class WikiSubjectStore:
    def __init__(self, database_path: Path):
        self._database_path = database_path

    def _connect(self) -> sqlite3.Connection:
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._database_path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(DDL)
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

    def upsert(
        self,
        subject: WikiSubjectRef,
        *,
        aliases: list[str] | None = None,
        concept_ids: list[str] | None = None,
        source: str,
        confidence: float = 1.0,
    ) -> None:
        updated_at = datetime.now(timezone.utc).isoformat()
        normalized_name = normalize_wiki_alias(subject.display_name)
        clean_aliases = {
            alias.strip()
            for alias in [subject.display_name, subject.symbol or "", *(aliases or [])]
            if alias.strip()
        }
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO wiki_subjects (
                  canonical_id, subject_type, display_name, normalized_name,
                  market, symbol, asset_type, source, confidence, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(canonical_id) DO UPDATE SET
                  display_name = excluded.display_name,
                  normalized_name = excluded.normalized_name,
                  market = excluded.market,
                  symbol = excluded.symbol,
                  asset_type = excluded.asset_type,
                  source = excluded.source,
                  confidence = MAX(wiki_subjects.confidence, excluded.confidence),
                  updated_at = excluded.updated_at
                """,
                (
                    subject.canonical_id,
                    subject.type,
                    subject.display_name,
                    normalized_name,
                    subject.market,
                    subject.symbol,
                    subject.asset_type,
                    source,
                    confidence,
                    updated_at,
                ),
            )
            for alias in clean_aliases:
                normalized_alias = normalize_wiki_alias(alias)
                if not normalized_alias:
                    continue
                connection.execute(
                    """
                    INSERT INTO wiki_subject_aliases (
                      canonical_id, alias, normalized_alias, source,
                      confidence, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(canonical_id, normalized_alias) DO UPDATE SET
                      alias = excluded.alias,
                      source = excluded.source,
                      confidence = MAX(wiki_subject_aliases.confidence, excluded.confidence),
                      updated_at = excluded.updated_at
                    """,
                    (
                        subject.canonical_id,
                        alias,
                        normalized_alias,
                        source,
                        confidence,
                        updated_at,
                    ),
                )
            for concept_id in dict.fromkeys(concept_ids or []):
                connection.execute(
                    """
                    INSERT INTO wiki_subject_concepts (
                      canonical_id, concept_id, source, updated_at
                    ) VALUES (?, ?, ?, ?)
                    ON CONFLICT(canonical_id, concept_id) DO UPDATE SET
                      source = excluded.source,
                      updated_at = excluded.updated_at
                    """,
                    (subject.canonical_id, concept_id, source, updated_at),
                )

    def search(
        self,
        query: str,
        *,
        subject_type: str | None = None,
        market: str | None = None,
        limit: int = 12,
    ) -> list[WikiSubjectMatch]:
        normalized = normalize_wiki_alias(query)
        if not normalized:
            return []
        escaped = normalized.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        filters = [
            "(s.canonical_id = ? OR lower(COALESCE(s.symbol, '')) = ? "
            "OR s.normalized_name = ? OR s.normalized_name LIKE ? ESCAPE '\\' "
            "OR EXISTS (SELECT 1 FROM wiki_subject_aliases a "
            "WHERE a.canonical_id = s.canonical_id "
            "AND (a.normalized_alias = ? OR a.normalized_alias LIKE ? ESCAPE '\\')))"
        ]
        parameters: list[object] = [
            query,
            query.casefold(),
            normalized,
            f"%{escaped}%",
            normalized,
            f"%{escaped}%",
        ]
        if subject_type:
            filters.append("s.subject_type = ?")
            parameters.append(subject_type)
        if market:
            filters.append("s.market = ?")
            parameters.append(market)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT s.*,
                  CASE
                    WHEN s.canonical_id = ? THEN 0
                    WHEN lower(COALESCE(s.symbol, '')) = ? THEN 1
                    WHEN s.normalized_name = ? THEN 2
                    WHEN EXISTS (
                      SELECT 1 FROM wiki_subject_aliases exact_alias
                      WHERE exact_alias.canonical_id = s.canonical_id
                      AND exact_alias.normalized_alias = ?
                    ) THEN 3
                    ELSE 4
                  END AS match_rank
                FROM wiki_subjects s
                WHERE {' AND '.join(filters)}
                ORDER BY match_rank, s.confidence DESC, s.display_name
                LIMIT ?
                """,
                [query, query.casefold(), normalized, normalized, *parameters, limit],
            ).fetchall()
            matches: list[WikiSubjectMatch] = []
            matched_by_values = ["canonical", "symbol", "name", "alias", "upstream"]
            for row in rows:
                aliases = [
                    item["alias"]
                    for item in connection.execute(
                        """
                        SELECT alias FROM wiki_subject_aliases
                        WHERE canonical_id = ? ORDER BY confidence DESC, alias LIMIT 20
                        """,
                        (row["canonical_id"],),
                    ).fetchall()
                ]
                concept_ids = [
                    item["concept_id"]
                    for item in connection.execute(
                        """
                        SELECT concept_id FROM wiki_subject_concepts
                        WHERE canonical_id = ? ORDER BY concept_id LIMIT 50
                        """,
                        (row["canonical_id"],),
                    ).fetchall()
                ]
                matches.append(
                    WikiSubjectMatch(
                        subject=WikiSubjectRef(
                            type=row["subject_type"],
                            canonicalId=row["canonical_id"],
                            displayName=row["display_name"],
                            market=row["market"],
                            symbol=row["symbol"],
                            assetType=row["asset_type"],
                        ),
                        aliases=aliases,
                        conceptIds=concept_ids,
                        source=row["source"],
                        matchedBy=matched_by_values[min(int(row["match_rank"]), 4)],
                        confidence=float(row["confidence"]),
                    )
                )
        return matches
