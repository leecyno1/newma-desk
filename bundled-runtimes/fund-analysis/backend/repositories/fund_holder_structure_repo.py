"""基金持有人结构历史 Repository。"""

from typing import Any, Dict, List

try:
    from backend.database import get_engine
except ModuleNotFoundError:
    from database import get_engine


class FundHolderStructureRepo:
    def __init__(self):
        self._engine = None

    @property
    def engine(self):
        if self._engine is None:
            self._engine = get_engine()
        return self._engine

    def upsert_many(self, wind_code: str, rows: List[Dict[str, Any]]) -> int:
        if not rows:
            return 0
        from sqlalchemy import text

        sql = text("""
            INSERT INTO fund_holder_structures (
                wind_code, report_date, institution_ratio, individual_ratio,
                internal_ratio, total_shares_yi, source, source_url, fetched_at
            ) VALUES (
                :wind_code, :report_date, :institution_ratio, :individual_ratio,
                :internal_ratio, :total_shares_yi, :source, :source_url, NOW()
            )
            ON CONFLICT (wind_code, report_date) DO UPDATE SET
                institution_ratio = EXCLUDED.institution_ratio,
                individual_ratio = EXCLUDED.individual_ratio,
                internal_ratio = EXCLUDED.internal_ratio,
                total_shares_yi = EXCLUDED.total_shares_yi,
                source = EXCLUDED.source,
                source_url = EXCLUDED.source_url,
                fetched_at = NOW()
        """)
        with self.engine.begin() as conn:
            for row in rows:
                conn.execute(sql, {"wind_code": wind_code, **row})
        return len(rows)

    def list_history(self, wind_code: str, limit: int = 20) -> List[Dict[str, Any]]:
        from sqlalchemy import text

        sql = text("""
            SELECT wind_code, report_date, institution_ratio, individual_ratio,
                   internal_ratio, total_shares_yi, source, source_url, fetched_at
            FROM fund_holder_structures
            WHERE wind_code = :wind_code
            ORDER BY report_date DESC
            LIMIT :limit
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {"wind_code": wind_code, "limit": max(1, min(limit, 100))}).fetchall()
        return [self._serialize(dict(row._mapping)) for row in rows]

    @staticmethod
    def _serialize(row: Dict[str, Any]) -> Dict[str, Any]:
        for key in ("institution_ratio", "individual_ratio", "internal_ratio", "total_shares_yi"):
            if row.get(key) is not None:
                row[key] = float(row[key])
        for key in ("report_date", "fetched_at"):
            if row.get(key) is not None:
                row[key] = row[key].isoformat()
        return row
