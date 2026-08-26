"""基金专业评价历史快照。"""
import json
from typing import Any, Dict, List, Optional

try:
    from backend.database import get_engine
except ModuleNotFoundError:
    from database import get_engine


class FundEvaluationSnapshotRepo:
    def __init__(self, engine: Optional[Any] = None):
        self._engine = engine

    @property
    def engine(self):
        if self._engine is None:
            self._engine = get_engine()
        return self._engine

    def create(self, snapshot: Dict[str, Any]) -> Dict[str, Any]:
        from sqlalchemy import text

        with self.engine.begin() as conn:
            row = conn.execute(text("""
                INSERT INTO fund_evaluation_snapshots (
                    wind_code, evaluation_window, as_of_date, status,
                    methodology_version, calculation_method,
                    peer_group_id, peer_group_name,
                    overall_score, overall_grade,
                    peer_rank, peer_count, peer_percentile,
                    dimension_scores, peer_metrics, data_quality,
                    missing_items, source_snapshot_ids, snapshot
                ) VALUES (
                    :wind_code, :evaluation_window, :as_of_date, :status,
                    :methodology_version, :calculation_method,
                    :peer_group_id, :peer_group_name,
                    :overall_score, :overall_grade,
                    :peer_rank, :peer_count, :peer_percentile,
                    CAST(:dimension_scores AS jsonb), CAST(:peer_metrics AS jsonb),
                    CAST(:data_quality AS jsonb), CAST(:missing_items AS jsonb),
                    :source_snapshot_ids, CAST(:snapshot AS jsonb)
                )
                RETURNING *
            """), {
                **snapshot,
                "dimension_scores": json.dumps(snapshot.get("dimension_scores") or {}, ensure_ascii=False, default=str),
                "peer_metrics": json.dumps(snapshot.get("peer_metrics") or {}, ensure_ascii=False, default=str),
                "data_quality": json.dumps(snapshot.get("data_quality") or {}, ensure_ascii=False, default=str),
                "missing_items": json.dumps(snapshot.get("missing_items") or [], ensure_ascii=False, default=str),
                "snapshot": json.dumps(snapshot.get("snapshot") or {}, ensure_ascii=False, default=str),
                "source_snapshot_ids": snapshot.get("source_snapshot_ids") or [],
            }).fetchone()
        return dict(row._mapping)

    def list_history(
        self,
        wind_code: str,
        evaluation_window: Optional[str] = None,
        limit: int = 30,
    ) -> List[Dict[str, Any]]:
        from sqlalchemy import text

        sql = """
            SELECT snapshots.*, funds.name AS fund_name, funds.type AS fund_type
            FROM fund_evaluation_snapshots snapshots
            LEFT JOIN funds ON funds.wind_code = snapshots.wind_code
            WHERE snapshots.wind_code = :wind_code
        """
        params: Dict[str, Any] = {
            "wind_code": str(wind_code or "").strip().upper(),
            "limit": max(1, min(int(limit), 100)),
        }
        if evaluation_window:
            sql += " AND snapshots.evaluation_window = :evaluation_window"
            params["evaluation_window"] = evaluation_window
        sql += " ORDER BY snapshots.created_at DESC, snapshots.id DESC LIMIT :limit"

        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [dict(row._mapping) for row in rows]

    def list_recent(
        self,
        evaluation_window: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 30,
    ) -> List[Dict[str, Any]]:
        from sqlalchemy import text

        sql = """
            SELECT snapshots.*, funds.name AS fund_name, funds.type AS fund_type
            FROM fund_evaluation_snapshots snapshots
            JOIN funds ON funds.wind_code = snapshots.wind_code
            WHERE 1 = 1
        """
        params: Dict[str, Any] = {"limit": max(1, min(int(limit), 100))}
        if evaluation_window:
            sql += " AND snapshots.evaluation_window = :evaluation_window"
            params["evaluation_window"] = evaluation_window
        if status:
            sql += " AND snapshots.status = :status"
            params["status"] = status
        sql += " ORDER BY snapshots.created_at DESC, snapshots.id DESC LIMIT :limit"

        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), params).fetchall()
        return [dict(row._mapping) for row in rows]

    def get(self, snapshot_id: str, wind_code: str) -> Optional[Dict[str, Any]]:
        from sqlalchemy import text

        with self.engine.connect() as conn:
            row = conn.execute(text("""
                SELECT *
                FROM fund_evaluation_snapshots
                WHERE id = :snapshot_id AND wind_code = :wind_code
                LIMIT 1
            """), {
                "snapshot_id": snapshot_id,
                "wind_code": str(wind_code or "").strip().upper(),
            }).fetchone()
        return dict(row._mapping) if row else None
