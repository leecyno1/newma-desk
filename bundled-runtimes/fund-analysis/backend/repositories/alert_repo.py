"""
预警 Repository
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


class AlertRepo:
    def __init__(self):
        self._engine = None

    @property
    def engine(self):
        if self._engine is None:
            self._engine = _get_engine()
        return self._engine

    def create_rule(
        self,
        name: str,
        rule_type: str,
        scope_type: str,
        scope_id: Optional[str] = None,
        threshold: Optional[Dict[str, Any]] = None,
        enabled: bool = True,
        created_by: Optional[str] = None,
    ) -> Dict[str, Any]:
        from sqlalchemy import text
        from database import init_database

        init_database()
        sql = """
            INSERT INTO alert_rules (name, rule_type, scope_type, scope_id, threshold, enabled, created_by)
            VALUES (:name, :rule_type, :scope_type, :scope_id, CAST(:threshold AS JSONB), :enabled, :created_by)
            RETURNING *
        """
        with self.engine.connect() as conn:
            row = conn.execute(text(sql), {
                "name": name,
                "rule_type": rule_type,
                "scope_type": scope_type,
                "scope_id": scope_id,
                "threshold": _json(threshold),
                "enabled": enabled,
                "created_by": created_by,
            }).fetchone()
            conn.commit()
        return _row_to_dict(row)

    def list_rules(self, enabled: Optional[bool] = None) -> List[Dict[str, Any]]:
        from sqlalchemy import text

        clauses = ["1=1"]
        params: Dict[str, Any] = {}
        if enabled is not None:
            clauses.append("enabled = :enabled")
            params["enabled"] = enabled
        sql = f"SELECT * FROM alert_rules WHERE {' AND '.join(clauses)} ORDER BY updated_at DESC, created_at DESC"
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [_row_to_dict(row) for row in rows]

    def update_rule(
        self,
        rule_id: str,
        enabled: Optional[bool] = None,
        threshold: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        from sqlalchemy import text

        assignments = ["updated_at = NOW()"]
        params: Dict[str, Any] = {"rule_id": rule_id}
        if enabled is not None:
            assignments.append("enabled = :enabled")
            params["enabled"] = enabled
        if threshold is not None:
            assignments.append("threshold = CAST(:threshold AS JSONB)")
            params["threshold"] = _json(threshold)

        sql = f"""
            UPDATE alert_rules
            SET {', '.join(assignments)}
            WHERE id = CAST(:rule_id AS UUID)
            RETURNING *
        """
        with self.engine.connect() as conn:
            row = conn.execute(text(sql), params).fetchone()
            conn.commit()
        if not row:
            return None
        return _row_to_dict(row)

    def delete_rule(self, rule_id: str) -> bool:
        from sqlalchemy import text

        sql = "DELETE FROM alert_rules WHERE id = CAST(:rule_id AS UUID)"
        with self.engine.connect() as conn:
            result = conn.execute(text(sql), {"rule_id": rule_id})
            conn.commit()
        return result.rowcount > 0

    def create_event(
        self,
        rule_id: Optional[str],
        fund_id: Optional[str],
        pool_member_id: Optional[str],
        event_type: str,
        severity: str,
        title: str,
        message: str,
        status: str = "new",
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        from sqlalchemy import text
        from database import init_database

        init_database()
        sql = """
            INSERT INTO alert_events (
                rule_id, fund_id, pool_member_id, event_type, severity, title, message, status, details
            ) VALUES (
                CASE WHEN :rule_id IS NULL THEN NULL ELSE CAST(:rule_id AS UUID) END,
                :fund_id, :pool_member_id, :event_type, :severity, :title, :message, :status,
                CAST(:details AS JSONB)
            )
            RETURNING *
        """
        with self.engine.connect() as conn:
            row = conn.execute(text(sql), {
                "rule_id": rule_id,
                "fund_id": fund_id,
                "pool_member_id": pool_member_id,
                "event_type": event_type,
                "severity": severity,
                "title": title,
                "message": message,
                "status": status,
                "details": _json(details),
            }).fetchone()
            conn.commit()
        return _row_to_dict(row)

    def list_events(self, status: Optional[str] = None, severity: Optional[str] = None) -> List[Dict[str, Any]]:
        from sqlalchemy import text

        clauses = ["1=1"]
        params: Dict[str, Any] = {}
        if status:
            clauses.append("status = :status")
            params["status"] = status
        if severity:
            clauses.append("severity = :severity")
            params["severity"] = severity
        sql = f"""
            SELECT * FROM alert_events
            WHERE {' AND '.join(clauses)}
            ORDER BY triggered_at DESC, created_at DESC
        """
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [_row_to_dict(row) for row in rows]

    def update_event_status(self, event_id: str, status: str) -> Dict[str, Any]:
        from sqlalchemy import text

        sql = """
            UPDATE alert_events
            SET status = :status,
                resolved_at = CASE WHEN :status = 'resolved' THEN NOW() ELSE resolved_at END
            WHERE id = CAST(:event_id AS UUID)
            RETURNING *
        """
        with self.engine.connect() as conn:
            row = conn.execute(text(sql), {"event_id": event_id, "status": status}).fetchone()
            conn.commit()
        return _row_to_dict(row)
