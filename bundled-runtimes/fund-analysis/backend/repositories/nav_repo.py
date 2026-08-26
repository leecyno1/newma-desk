"""
基金净值 Repository
"""
import os
import math
from typing import List, Dict, Any
import logging

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


def _clean(v):
    """清理 NaN/Inf"""
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


class NavRepo:
    """基金净值数据访问层"""

    def __init__(self):
        self._engine = None

    @property
    def engine(self):
        if self._engine is None:
            self._engine = _get_engine()
        return self._engine

    def upsert_nav_series(
        self,
        wind_code: str,
        nav_data: List[Dict[str, Any]],
        replace_range: bool = False,
    ) -> bool:
        """Upsert 基金净值序列；权威源同步可先替换本次覆盖日期范围。"""
        try:
            from sqlalchemy import text

            insert_sql = """
            INSERT INTO fund_nav (
                wind_code, trade_date, nav, unit_nav, accum_nav,
                daily_return, benchmark_nav, discount_rate
            ) VALUES (
                :wind_code, :trade_date, :nav, :unit_nav, :accum_nav,
                :daily_return, :benchmark_nav, :discount_rate
            )
            ON CONFLICT (wind_code, trade_date) DO UPDATE SET
                nav = EXCLUDED.nav,
                unit_nav = EXCLUDED.unit_nav,
                accum_nav = EXCLUDED.accum_nav,
                daily_return = EXCLUDED.daily_return,
                benchmark_nav = COALESCE(EXCLUDED.benchmark_nav, fund_nav.benchmark_nav),
                discount_rate = EXCLUDED.discount_rate
            """

            valid_dates = sorted(
                str(nav.get("date") or "").strip()
                for nav in nav_data
                if str(nav.get("date") or "").strip()
            )
            with self.engine.begin() as conn:
                if replace_range and valid_dates:
                    conn.execute(text("""
                        DELETE FROM fund_nav
                        WHERE wind_code = :wind_code
                          AND trade_date BETWEEN :start_date AND :end_date
                    """), {
                        "wind_code": wind_code,
                        "start_date": valid_dates[0],
                        "end_date": valid_dates[-1],
                    })
                for nav in nav_data:
                    try:
                        nav_value = _clean(nav.get("nav") or nav.get("unit_nav"))
                        params = {
                            "wind_code": wind_code,
                            "trade_date": nav.get("date", ""),
                            "nav": nav_value,
                            "unit_nav": nav_value,
                            "accum_nav": _clean(nav.get("accum_nav")),
                            "daily_return": _clean(nav.get("daily_return")),
                            "benchmark_nav": _clean(nav.get("benchmark_nav")),
                            "discount_rate": _clean(nav.get("discount_rate")),
                        }
                        conn.execute(text(insert_sql), params)
                    except Exception:
                        continue
            return True
        except Exception as e:
            logger.error(f"upsert_nav_series error for {wind_code}: {e}")
            return False

    def get_nav_series(
        self,
        wind_code: str,
        start_date: str = None,
        end_date: str = None,
    ) -> List[Dict[str, Any]]:
        """获取净值序列"""
        try:
            from sqlalchemy import text

            where_clauses = ["wind_code = :wind_code"]
            params = {"wind_code": wind_code}

            if start_date:
                where_clauses.append("trade_date >= :start_date")
                params["start_date"] = start_date
            if end_date:
                where_clauses.append("trade_date <= :end_date")
                params["end_date"] = end_date

            where_sql = " AND ".join(where_clauses)

            sql = f"""
                SELECT trade_date, COALESCE(unit_nav, nav) AS unit_nav, accum_nav, daily_return, benchmark_nav
                FROM fund_nav
                WHERE {where_sql}
                ORDER BY trade_date ASC
            """

            with self.engine.connect() as conn:
                result = conn.execute(text(sql), params)
                return [
                    {
                        "date": r.trade_date,
                        "nav": r.unit_nav,
                        "accum_nav": r.accum_nav,
                        "daily_return": r.daily_return,
                        "benchmark_nav": r.benchmark_nav,
                    }
                    for r in result.fetchall()
                ]
        except Exception as e:
            logger.error(f"get_nav_series error for {wind_code}: {e}")
            return []

    def delete_nav(self, wind_code: str) -> bool:
        """删除净值数据"""
        try:
            from sqlalchemy import text
            sql = "DELETE FROM fund_nav WHERE wind_code = :wind_code"
            with self.engine.connect() as conn:
                conn.execute(text(sql), {"wind_code": wind_code})
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"delete_nav error: {e}")
            return False
