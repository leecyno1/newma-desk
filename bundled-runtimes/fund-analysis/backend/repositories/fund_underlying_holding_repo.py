"""FOF 公开底层基金持仓 Repository。"""

from typing import Any, Dict, List

try:
    from backend.database import get_engine
except ModuleNotFoundError:
    from database import get_engine


class FundUnderlyingHoldingRepo:
    def __init__(self):
        self._engine = None

    @property
    def engine(self):
        if self._engine is None:
            self._engine = get_engine()
        return self._engine

    def replace_period(self, wind_code: str, rows: List[Dict[str, Any]]) -> int:
        if not rows:
            return 0
        from sqlalchemy import text

        report_date = rows[0]["report_date"]
        delete_sql = text("""
            DELETE FROM fund_underlying_holdings
            WHERE wind_code = :wind_code AND report_date = :report_date
        """)
        insert_sql = text("""
            INSERT INTO fund_underlying_holdings (
                wind_code, report_date, sequence, underlying_fund_code,
                underlying_fund_name, nav_ratio, daily_return, source,
                source_url, fetched_at
            ) VALUES (
                :wind_code, :report_date, :sequence, :underlying_fund_code,
                :underlying_fund_name, :nav_ratio, :daily_return, :source,
                :source_url, NOW()
            )
        """)
        with self.engine.begin() as conn:
            conn.execute(delete_sql, {"wind_code": wind_code, "report_date": report_date})
            for row in rows:
                conn.execute(insert_sql, {"wind_code": wind_code, **row})
        return len(rows)

    def list_latest_periods(self, wind_code: str, limit: int = 8) -> List[Dict[str, Any]]:
        from sqlalchemy import text

        sql = text("""
            WITH latest_periods AS (
                SELECT DISTINCT report_date
                FROM fund_underlying_holdings
                WHERE wind_code = :wind_code
                ORDER BY report_date DESC
                LIMIT :limit
            )
            SELECT holding.wind_code, holding.report_date, holding.sequence,
                   holding.underlying_fund_code, holding.underlying_fund_name,
                   holding.nav_ratio, holding.daily_return, holding.source,
                   holding.source_url, holding.fetched_at
            FROM fund_underlying_holdings holding
            JOIN latest_periods period ON period.report_date = holding.report_date
            WHERE holding.wind_code = :wind_code
            ORDER BY holding.report_date DESC, holding.sequence,
                     holding.underlying_fund_code
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {
                "wind_code": wind_code,
                "limit": max(1, min(limit, 20)),
            }).fetchall()
        return [self._serialize(dict(row._mapping)) for row in rows]

    def list_latest_periods_map(self, wind_codes: List[str], limit: int = 1) -> Dict[str, List[Dict[str, Any]]]:
        codes = list(dict.fromkeys(str(code or "").strip() for code in wind_codes if str(code or "").strip()))
        if not codes:
            return {}
        from sqlalchemy import text

        sql = text("""
            WITH ranked_periods AS (
                SELECT holding.*,
                       DENSE_RANK() OVER (
                           PARTITION BY holding.wind_code
                           ORDER BY holding.report_date DESC
                       ) AS period_rank
                FROM fund_underlying_holdings holding
                WHERE holding.wind_code = ANY(:wind_codes)
            )
            SELECT wind_code, report_date, sequence, underlying_fund_code,
                   underlying_fund_name, nav_ratio, daily_return, source,
                   source_url, fetched_at
            FROM ranked_periods
            WHERE period_rank <= :limit
            ORDER BY wind_code, report_date DESC, sequence, underlying_fund_code
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {
                "wind_codes": codes,
                "limit": max(1, min(int(limit), 20)),
            }).fetchall()
        result: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            item = self._serialize(dict(row._mapping))
            result.setdefault(str(item.get("wind_code") or ""), []).append(item)
        return result

    @staticmethod
    def _serialize(row: Dict[str, Any]) -> Dict[str, Any]:
        for key in ("nav_ratio", "daily_return"):
            if row.get(key) is not None:
                row[key] = float(row[key])
        for key in ("report_date", "fetched_at"):
            if row.get(key) is not None:
                row[key] = row[key].isoformat()
        return row
