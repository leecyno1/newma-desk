"""基金资产配置历史 Repository。"""

from typing import Any, Dict, List

try:
    from backend.database import get_engine
except ModuleNotFoundError:
    from database import get_engine


class FundAssetAllocationRepo:
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
            INSERT INTO fund_asset_allocations (
                wind_code, report_date, stock_ratio, bond_ratio, cash_ratio,
                net_asset_yi, source, source_url, fetched_at
            ) VALUES (
                :wind_code, :report_date, :stock_ratio, :bond_ratio, :cash_ratio,
                :net_asset_yi, :source, :source_url, NOW()
            )
            ON CONFLICT (wind_code, report_date) DO UPDATE SET
                stock_ratio = EXCLUDED.stock_ratio,
                bond_ratio = EXCLUDED.bond_ratio,
                cash_ratio = EXCLUDED.cash_ratio,
                net_asset_yi = EXCLUDED.net_asset_yi,
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
            SELECT wind_code, report_date, stock_ratio, bond_ratio, cash_ratio,
                   net_asset_yi, source, source_url, fetched_at
            FROM fund_asset_allocations
            WHERE wind_code = :wind_code
            ORDER BY report_date DESC
            LIMIT :limit
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {"wind_code": wind_code, "limit": max(1, min(limit, 100))}).fetchall()
        return [self._serialize(dict(row._mapping)) for row in rows]

    @staticmethod
    def _serialize(row: Dict[str, Any]) -> Dict[str, Any]:
        for key in ("stock_ratio", "bond_ratio", "cash_ratio", "net_asset_yi"):
            if row.get(key) is not None:
                row[key] = float(row[key])
        for key in ("report_date", "fetched_at"):
            if row.get(key) is not None:
                row[key] = row[key].isoformat()
        return row
