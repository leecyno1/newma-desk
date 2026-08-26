"""公开持仓风格描述子与同类分位快照。"""
import json
from typing import Any, Dict, List, Optional

try:
    from backend.database import get_engine
except ModuleNotFoundError:
    from database import get_engine


class HoldingStyleSnapshotRepo:
    def __init__(self, engine: Optional[Any] = None):
        self._engine = engine

    @property
    def engine(self):
        if self._engine is None:
            self._engine = get_engine()
        return self._engine

    def upsert(self, snapshot: Dict[str, Any]) -> bool:
        from sqlalchemy import text

        with self.engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO holding_style_snapshots (
                    wind_code, quarter, peer_group_id, peer_group_key, peer_group_name,
                    descriptors, peer_percentiles, style_labels, peer_sample_size,
                    minimum_peer_count, holdings_disclosed_weight, source, status,
                    missing_items, calculated_at
                ) VALUES (
                    :wind_code, :quarter, :peer_group_id, :peer_group_key, :peer_group_name,
                    CAST(:descriptors AS jsonb), CAST(:peer_percentiles AS jsonb), :style_labels,
                    :peer_sample_size, :minimum_peer_count, :holdings_disclosed_weight,
                    :source, :status, CAST(:missing_items AS jsonb), CURRENT_TIMESTAMP
                )
                ON CONFLICT (wind_code, quarter) DO UPDATE SET
                    peer_group_id = EXCLUDED.peer_group_id,
                    peer_group_key = EXCLUDED.peer_group_key,
                    peer_group_name = EXCLUDED.peer_group_name,
                    descriptors = EXCLUDED.descriptors,
                    peer_percentiles = EXCLUDED.peer_percentiles,
                    style_labels = EXCLUDED.style_labels,
                    peer_sample_size = EXCLUDED.peer_sample_size,
                    minimum_peer_count = EXCLUDED.minimum_peer_count,
                    holdings_disclosed_weight = EXCLUDED.holdings_disclosed_weight,
                    source = EXCLUDED.source,
                    status = EXCLUDED.status,
                    missing_items = EXCLUDED.missing_items,
                    calculated_at = CURRENT_TIMESTAMP
            """), {
                "wind_code": snapshot["wind_code"],
                "quarter": snapshot["quarter"],
                "peer_group_id": snapshot.get("peer_group_id"),
                "peer_group_key": snapshot.get("peer_group_key"),
                "peer_group_name": snapshot.get("peer_group_name"),
                "descriptors": json.dumps(snapshot.get("descriptors") or [], ensure_ascii=False),
                "peer_percentiles": json.dumps(snapshot.get("peer_percentiles") or [], ensure_ascii=False),
                "style_labels": snapshot.get("style_labels") or [],
                "peer_sample_size": int(snapshot.get("peer_sample_size") or 0),
                "minimum_peer_count": int(snapshot.get("minimum_peer_count") or 5),
                "holdings_disclosed_weight": snapshot.get("holdings_disclosed_weight"),
                "source": snapshot.get("source") or "holding_style_descriptor_v1",
                "status": snapshot.get("status") or "insufficient_evidence",
                "missing_items": json.dumps(snapshot.get("missing_items") or [], ensure_ascii=False),
            })
        return True

    def get(self, wind_code: str, quarter: str) -> Optional[Dict[str, Any]]:
        from sqlalchemy import text

        with self.engine.connect() as conn:
            row = conn.execute(text("""
                SELECT * FROM holding_style_snapshots
                WHERE wind_code = :wind_code AND quarter = :quarter
                LIMIT 1
            """), {"wind_code": wind_code, "quarter": quarter}).fetchone()
        return dict(row._mapping) if row else None

    def list_peer(self, peer_group_id: str, quarter: str) -> List[Dict[str, Any]]:
        from sqlalchemy import text

        with self.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT * FROM holding_style_snapshots
                WHERE peer_group_id = :peer_group_id AND quarter = :quarter
                  AND status IN ('descriptor_ready', 'peer_percentile_ready', 'peer_percentile_neutral')
                ORDER BY wind_code
            """), {"peer_group_id": peer_group_id, "quarter": quarter}).fetchall()
        return [dict(row._mapping) for row in rows]

    def get_latest_map(self, wind_codes: List[str]) -> Dict[str, Dict[str, Any]]:
        from sqlalchemy import text

        normalized = list(dict.fromkeys(
            str(code or "").strip() for code in wind_codes if str(code or "").strip()
        ))
        if not normalized:
            return {}
        with self.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT DISTINCT ON (wind_code) *
                FROM holding_style_snapshots
                WHERE wind_code = ANY(:wind_codes)
                ORDER BY wind_code, quarter DESC, calculated_at DESC
            """), {"wind_codes": normalized}).fetchall()
        return {str(row.wind_code): dict(row._mapping) for row in rows}

    def list_history(self, wind_code: str, limit: int = 6) -> List[Dict[str, Any]]:
        from sqlalchemy import text

        with self.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT *
                FROM holding_style_snapshots
                WHERE wind_code = :wind_code
                ORDER BY quarter DESC, calculated_at DESC
                LIMIT :limit
            """), {
                "wind_code": str(wind_code or "").strip().upper(),
                "limit": max(2, min(int(limit), 20)),
            }).fetchall()
        return [dict(row._mapping) for row in rows]
