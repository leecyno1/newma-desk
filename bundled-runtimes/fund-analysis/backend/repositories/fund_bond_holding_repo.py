"""基金公开债券持仓 Repository。"""

from typing import Any, Dict, List

try:
    from backend.database import get_engine
except ModuleNotFoundError:
    from database import get_engine


class FundBondHoldingRepo:
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
            INSERT INTO fund_bond_holdings (
                wind_code, report_date, sequence, bond_code, bond_name,
                bond_type, nav_ratio, market_value_wan, classification_basis,
                issuer, security_bond_type, credit_rating, rating_type,
                maturity_date, coupon_rate, metadata_source, metadata_url,
                metadata_status, source, source_url, fetched_at
            ) VALUES (
                :wind_code, :report_date, :sequence, :bond_code, :bond_name,
                :bond_type, :nav_ratio, :market_value_wan, :classification_basis,
                :issuer, :security_bond_type, :credit_rating, :rating_type,
                :maturity_date, :coupon_rate, :metadata_source, :metadata_url,
                :metadata_status, :source, :source_url, NOW()
            )
            ON CONFLICT (wind_code, report_date, bond_code) DO UPDATE SET
                sequence = EXCLUDED.sequence,
                bond_name = EXCLUDED.bond_name,
                bond_type = EXCLUDED.bond_type,
                nav_ratio = EXCLUDED.nav_ratio,
                market_value_wan = EXCLUDED.market_value_wan,
                classification_basis = EXCLUDED.classification_basis,
                issuer = EXCLUDED.issuer,
                security_bond_type = EXCLUDED.security_bond_type,
                credit_rating = EXCLUDED.credit_rating,
                rating_type = EXCLUDED.rating_type,
                maturity_date = EXCLUDED.maturity_date,
                coupon_rate = EXCLUDED.coupon_rate,
                metadata_source = EXCLUDED.metadata_source,
                metadata_url = EXCLUDED.metadata_url,
                metadata_status = EXCLUDED.metadata_status,
                source = EXCLUDED.source,
                source_url = EXCLUDED.source_url,
                fetched_at = NOW()
        """)
        with self.engine.begin() as conn:
            for row in rows:
                conn.execute(sql, {"wind_code": wind_code, **row})
        return len(rows)

    def metadata_by_codes(self, bond_codes: List[str]) -> Dict[str, Dict[str, Any]]:
        if not bond_codes:
            return {}
        from sqlalchemy import text

        sql = text("""
            SELECT DISTINCT ON (bond_code)
                   bond_code, issuer, security_bond_type, credit_rating,
                   rating_type, maturity_date, coupon_rate, metadata_source,
                   metadata_url, metadata_status
            FROM fund_bond_holdings
            WHERE bond_code = ANY(:bond_codes)
              AND metadata_status = 'available'
            ORDER BY bond_code, fetched_at DESC
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {"bond_codes": bond_codes}).fetchall()
        return {
            str(row.bond_code): self._serialize(dict(row._mapping))
            for row in rows
        }

    def update_metadata_many(self, rows: List[Dict[str, Any]]) -> int:
        if not rows:
            return 0
        from sqlalchemy import text

        sql = text("""
            UPDATE fund_bond_holdings SET
                bond_type = :bond_type,
                classification_basis = :classification_basis,
                issuer = :issuer,
                security_bond_type = :security_bond_type,
                credit_rating = :credit_rating,
                rating_type = :rating_type,
                maturity_date = :maturity_date,
                coupon_rate = :coupon_rate,
                metadata_source = :metadata_source,
                metadata_url = :metadata_url,
                metadata_status = :metadata_status
            WHERE split_part(bond_code, '.', 1) = :normalized_bond_code
        """)
        with self.engine.begin() as conn:
            for row in rows:
                conn.execute(sql, row)
        return len(rows)

    def list_latest_periods(self, wind_code: str, limit: int = 8) -> List[Dict[str, Any]]:
        from sqlalchemy import text

        sql = text("""
            WITH latest_periods AS (
                SELECT DISTINCT report_date
                FROM fund_bond_holdings
                WHERE wind_code = :wind_code
                ORDER BY report_date DESC
                LIMIT :limit
            )
            SELECT holding.wind_code, holding.report_date, holding.sequence,
                   holding.bond_code, holding.bond_name, holding.bond_type,
                   holding.nav_ratio, holding.market_value_wan,
                   holding.classification_basis, holding.issuer,
                   holding.security_bond_type, holding.credit_rating,
                   holding.rating_type, holding.maturity_date,
                   holding.coupon_rate, holding.metadata_source,
                   holding.metadata_url, holding.metadata_status, holding.source,
                   holding.source_url, holding.fetched_at
            FROM fund_bond_holdings holding
            JOIN latest_periods period ON period.report_date = holding.report_date
            WHERE holding.wind_code = :wind_code
            ORDER BY holding.report_date DESC, holding.sequence, holding.bond_code
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {
                "wind_code": wind_code,
                "limit": max(1, min(limit, 20)),
            }).fetchall()
        return [self._serialize(dict(row._mapping)) for row in rows]

    def list_latest_periods_map(self, wind_codes: List[str], limit: int = 4) -> Dict[str, List[Dict[str, Any]]]:
        if not wind_codes:
            return {}
        from sqlalchemy import text

        sql = text("""
            WITH distinct_periods AS (
                SELECT DISTINCT wind_code, report_date
                FROM fund_bond_holdings
                WHERE wind_code = ANY(:wind_codes)
            ), ranked_periods AS (
                SELECT wind_code, report_date,
                       DENSE_RANK() OVER (PARTITION BY wind_code ORDER BY report_date DESC) AS period_rank
                FROM distinct_periods
            )
            SELECT holding.wind_code, holding.report_date, holding.sequence,
                   holding.bond_code, holding.bond_name, holding.bond_type,
                   holding.nav_ratio, holding.market_value_wan,
                   holding.classification_basis, holding.issuer,
                   holding.security_bond_type, holding.credit_rating,
                   holding.rating_type, holding.maturity_date,
                   holding.coupon_rate, holding.metadata_source,
                   holding.metadata_url, holding.metadata_status, holding.source,
                   holding.source_url, holding.fetched_at
            FROM fund_bond_holdings holding
            JOIN ranked_periods period
              ON period.wind_code = holding.wind_code
             AND period.report_date = holding.report_date
            WHERE period.period_rank <= :limit
            ORDER BY holding.wind_code, holding.report_date DESC, holding.sequence, holding.bond_code
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {
                "wind_codes": list(dict.fromkeys(wind_codes)),
                "limit": max(1, min(limit, 8)),
            }).fetchall()
        result: Dict[str, List[Dict[str, Any]]] = {}
        for row in rows:
            item = self._serialize(dict(row._mapping))
            result.setdefault(str(item.get("wind_code") or ""), []).append(item)
        return result

    @staticmethod
    def _serialize(row: Dict[str, Any]) -> Dict[str, Any]:
        for key in ("nav_ratio", "market_value_wan", "coupon_rate"):
            if row.get(key) is not None:
                row[key] = float(row[key])
        for key in ("report_date", "maturity_date", "fetched_at"):
            if row.get(key) is not None:
                row[key] = row[key].isoformat()
        return row
