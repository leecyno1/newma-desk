"""
因子暴露 Repository
"""
import os
from typing import List, Dict, Any, Optional
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


class FactorRepo:
    """因子暴露数据访问层"""

    def __init__(self):
        self._engine = None

    @property
    def engine(self):
        if self._engine is None:
            self._engine = _get_engine()
        return self._engine

    def save_exposures(
        self,
        wind_code: str,
        quarter: str,
        exposures: Dict[str, float],
        risk_contributions: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """保存 Barra 因子暴露，并兼容旧路由传入的风险贡献列表。"""
        try:
            from sqlalchemy import text

            insert_sql = """
            INSERT INTO factor_exposures (
                fund_id, wind_code, quarter, factor_name, exposure, risk_contribution
            ) VALUES (
                (SELECT id::text FROM funds WHERE wind_code = :wind_code),
                :wind_code, :quarter, :factor_name, :exposure, :risk_contribution
            )
            ON CONFLICT (wind_code, quarter, factor_name) DO UPDATE SET
                fund_id = EXCLUDED.fund_id,
                exposure = EXCLUDED.exposure,
                risk_contribution = EXCLUDED.risk_contribution
            """

            with self.engine.connect() as conn:
                for factor_name, exposure in exposures.items():
                    risk_contribution = None
                    if risk_contributions:
                        for item in risk_contributions:
                            if item.get("factor") == factor_name:
                                risk_contribution = item.get("risk_contribution")
                                break
                    params = {
                        "wind_code": wind_code,
                        "quarter": quarter,
                        "factor_name": factor_name,
                        "exposure": exposure,
                        "risk_contribution": risk_contribution,
                    }
                    try:
                        conn.execute(text(insert_sql), params)
                    except Exception:
                        continue
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"save_exposures error for {wind_code}: {e}")
            return False

    def upsert_exposures(self, wind_code: str, quarter: str, exposures: Dict[str, float]) -> bool:
        """兼容较新的调用方：无风险贡献时复用 save_exposures。"""
        return self.save_exposures(wind_code, quarter, exposures)

    def get_exposures(self, wind_code: str, quarter: str = None) -> List[Dict[str, Any]]:
        """获取因子暴露"""
        try:
            from sqlalchemy import text

            if quarter:
                sql = """
                    SELECT * FROM factor_exposures
                    WHERE wind_code = :wind_code AND quarter = :quarter
                    ORDER BY risk_contribution DESC NULLS LAST
                """
                params = {"wind_code": wind_code, "quarter": quarter}
            else:
                sql = """
                    SELECT * FROM factor_exposures
                    WHERE wind_code = :wind_code
                    ORDER BY quarter DESC, risk_contribution DESC NULLS LAST
                    LIMIT 10
                """
                params = {"wind_code": wind_code}

            with self.engine.connect() as conn:
                result = conn.execute(text(sql), params)
                return [dict(r._mapping) for r in result.fetchall()]
        except Exception as e:
            logger.error(f"get_exposures error: {e}")
            return []

    def upsert_factor_return(self, factor_name: str, date: str, return_value: float) -> bool:
        """Upsert 因子收益"""
        try:
            from sqlalchemy import text
            sql = """
            INSERT INTO factor_returns (factor_name, date, return_value)
            VALUES (:factor, :date, :return)
            ON CONFLICT (factor_name, date) DO UPDATE SET return_value = EXCLUDED.return_value
            """
            with self.engine.connect() as conn:
                conn.execute(text(sql), {"factor": factor_name, "date": date, "return": return_value})
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"upsert_factor_return error: {e}")
            return False
