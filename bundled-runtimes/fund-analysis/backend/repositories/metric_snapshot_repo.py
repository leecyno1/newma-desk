"""
指标快照 Repository
"""
import json
import logging
import os
from datetime import date, datetime
from decimal import Decimal
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
        elif isinstance(value, Decimal):
            data[key] = str(value)
    return data


class MetricSnapshotRepo:
    """指标快照访问层。"""

    def __init__(self):
        self._engine = None

    @property
    def engine(self):
        if self._engine is None:
            self._engine = _get_engine()
        return self._engine

    def upsert_metric(
        self,
        target_type: str,
        target_id: str,
        as_of_date: date,
        metric_name: str,
        metric_value: Decimal,
        metric_unit: Optional[str] = None,
        window: Optional[str] = None,
        benchmark_code: Optional[str] = None,
        peer_group_key: Optional[str] = None,
        source_snapshot_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        from sqlalchemy import text
        from database import init_database

        init_database()
        sql = """
            INSERT INTO metric_snapshots (
                target_type, target_id, as_of_date, metric_name, metric_value,
                metric_unit, metric_window, benchmark_code, peer_group_key,
                source_snapshot_id, details
            ) VALUES (
                :target_type, :target_id, :as_of_date, :metric_name, :metric_value,
                :metric_unit, :window, :benchmark_code, :peer_group_key,
                CASE WHEN :source_snapshot_id IS NULL THEN NULL ELSE CAST(:source_snapshot_id AS UUID) END,
                CAST(:details AS JSONB)
            )
            ON CONFLICT (
                target_type, target_id, as_of_date, metric_name, metric_window, benchmark_code, peer_group_key
            ) DO UPDATE SET
                metric_value = EXCLUDED.metric_value,
                metric_unit = EXCLUDED.metric_unit,
                source_snapshot_id = EXCLUDED.source_snapshot_id,
                details = COALESCE(EXCLUDED.details, metric_snapshots.details),
                updated_at = NOW()
            RETURNING *
        """
        with self.engine.connect() as conn:
            row = conn.execute(text(sql), {
                "target_type": target_type,
                "target_id": target_id,
                "as_of_date": as_of_date,
                "metric_name": metric_name,
                "metric_value": metric_value,
                "metric_unit": metric_unit,
                "window": window,
                "benchmark_code": benchmark_code,
                "peer_group_key": peer_group_key,
                "source_snapshot_id": source_snapshot_id,
                "details": _json(details),
            }).fetchone()
            conn.commit()
        return _row_to_dict(row)

    def get_latest_panel(self, target_type: str, target_id: str) -> List[Dict[str, Any]]:
        from sqlalchemy import text

        sql = """
            SELECT DISTINCT ON (metric_name, metric_window, benchmark_code, peer_group_key) *
            FROM metric_snapshots
            WHERE target_type = :target_type AND target_id = :target_id
            ORDER BY metric_name, metric_window, benchmark_code, peer_group_key, as_of_date DESC, updated_at DESC
        """
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), {
                "target_type": target_type,
                "target_id": target_id,
            }).fetchall()
        return [_row_to_dict(row) for row in rows]

    def get_latest_panels(self, target_type: str, target_ids: List[str]) -> Dict[str, List[Dict[str, Any]]]:
        from sqlalchemy import text

        safe_target_ids = [str(target_id).strip() for target_id in target_ids if str(target_id or "").strip()]
        if not safe_target_ids:
            return {}

        sql = """
            SELECT DISTINCT ON (target_id, metric_name, metric_window, benchmark_code, peer_group_key) *
            FROM metric_snapshots
            WHERE target_type = :target_type AND target_id = ANY(:target_ids)
            ORDER BY target_id, metric_name, metric_window, benchmark_code, peer_group_key, as_of_date DESC, updated_at DESC
        """
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), {
                "target_type": target_type,
                "target_ids": safe_target_ids,
            }).fetchall()
        result: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            item = _row_to_dict(row)
            result.setdefault(str(item.get("target_id")), []).append(item)
        return result

    def get_metrics_as_of(
        self,
        target_type: str,
        target_id: str,
        as_of_date: date,
    ) -> List[Dict[str, Any]]:
        from sqlalchemy import text

        sql = """
            SELECT * FROM metric_snapshots
            WHERE target_type = :target_type
              AND target_id = :target_id
              AND as_of_date = :as_of_date
            ORDER BY metric_name, metric_window NULLS FIRST
        """
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), {
                "target_type": target_type,
                "target_id": target_id,
                "as_of_date": as_of_date,
            }).fetchall()
        return [_row_to_dict(row) for row in rows]
