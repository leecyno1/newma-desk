"""
数据源快照 Repository
"""
import json
import logging
import os
from datetime import date, datetime
from typing import Any, Dict, List, Optional

try:
    from backend.database import get_database_url
except ModuleNotFoundError:
    from database import get_database_url

logger = logging.getLogger(__name__)

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        from sqlalchemy import create_engine
        pg_url = get_database_url()
        _engine = create_engine(pg_url, pool_pre_ping=True, pool_size=20, max_overflow=30, pool_recycle=3600)
    return _engine


def _json(value: Optional[Dict[str, Any]]) -> Optional[str]:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, default=str)


def _row_to_dict(row) -> Dict[str, Any]:
    data = dict(row._mapping)
    for key, value in list(data.items()):
        if isinstance(value, (datetime, date)):
            data[key] = value.isoformat()
    return data


class DataSourceSnapshotRepo:
    """数据同步血缘记录访问层。"""

    def __init__(self):
        self._engine = None

    @property
    def engine(self):
        if self._engine is None:
            self._engine = _get_engine()
        return self._engine

    def create_snapshot(
        self,
        source: str,
        dataset: str,
        coverage_start: Optional[date] = None,
        coverage_end: Optional[date] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        from sqlalchemy import text
        from database import init_database

        init_database()
        sql = """
            INSERT INTO data_source_snapshots (
                source, dataset, status, coverage_start, coverage_end, metadata
            ) VALUES (
                :source, :dataset, 'running', :coverage_start, :coverage_end, CAST(:metadata AS JSONB)
            )
            RETURNING *
        """
        with self.engine.connect() as conn:
            row = conn.execute(text(sql), {
                "source": source,
                "dataset": dataset,
                "coverage_start": coverage_start,
                "coverage_end": coverage_end,
                "metadata": _json(metadata),
            }).fetchone()
            conn.commit()
        return _row_to_dict(row)

    def mark_success(
        self,
        snapshot_id: str,
        record_count: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        from sqlalchemy import text

        sql = """
            UPDATE data_source_snapshots
            SET status = 'success', finished_at = NOW(), record_count = :record_count,
                metadata = COALESCE(CAST(:metadata AS JSONB), metadata), error_message = NULL
            WHERE id = CAST(:snapshot_id AS UUID)
            RETURNING *
        """
        with self.engine.connect() as conn:
            row = conn.execute(text(sql), {
                "snapshot_id": snapshot_id,
                "record_count": record_count,
                "metadata": _json(metadata),
            }).fetchone()
            conn.commit()
        return _row_to_dict(row)

    def mark_failure(self, snapshot_id: str, error_message: str) -> Dict[str, Any]:
        from sqlalchemy import text

        sql = """
            UPDATE data_source_snapshots
            SET status = 'failed', finished_at = NOW(), error_message = :error_message
            WHERE id = CAST(:snapshot_id AS UUID)
            RETURNING *
        """
        with self.engine.connect() as conn:
            row = conn.execute(text(sql), {
                "snapshot_id": snapshot_id,
                "error_message": error_message,
            }).fetchone()
            conn.commit()
        return _row_to_dict(row)

    def get_latest_by_dataset(self, dataset: str, source: Optional[str] = None) -> Optional[Dict[str, Any]]:
        from sqlalchemy import text

        clauses = ["dataset = :dataset"]
        params = {"dataset": dataset}
        if source:
            clauses.append("source = :source")
            params["source"] = source
        sql = f"""
            SELECT * FROM data_source_snapshots
            WHERE {' AND '.join(clauses)}
            ORDER BY started_at DESC, created_at DESC
            LIMIT 1
        """
        with self.engine.connect() as conn:
            row = conn.execute(text(sql), params).fetchone()
        return _row_to_dict(row) if row else None

    def list_latest_by_dataset(self) -> List[Dict[str, Any]]:
        from sqlalchemy import text

        sql = """
            SELECT DISTINCT ON (dataset) *
            FROM data_source_snapshots
            ORDER BY dataset, started_at DESC, created_at DESC
        """
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql)).fetchall()
        return [_row_to_dict(row) for row in rows]

    def count_recent_failures(self, hours: int = 24) -> int:
        from sqlalchemy import text

        sql = """
            SELECT COUNT(*)
            FROM data_source_snapshots
            WHERE status = 'failed'
              AND started_at >= NOW() - (:hours * INTERVAL '1 hour')
        """
        with self.engine.connect() as conn:
            return int(conn.execute(text(sql), {"hours": hours}).scalar() or 0)
