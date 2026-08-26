"""
基金持仓 Repository
"""
import os
import math
from typing import List, Dict, Any, Optional
import logging

from lib.holding_weight_validation import normalize_holding_weights

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


class HoldingRepo:
    """基金持仓数据访问层"""

    def __init__(self):
        self._engine = None

    @property
    def engine(self):
        if self._engine is None:
            self._engine = _get_engine()
        return self._engine

    def upsert_holdings(self, wind_code: str, quarter: str, holdings: List[Dict[str, Any]]) -> bool:
        """Upsert 基金持仓"""
        try:
            from sqlalchemy import text

            holdings, validation = normalize_holding_weights(holdings)
            if validation.is_invalid:
                logger.warning(
                    "Rejected invalid fund NAV holding weights for %s %s: %s (sum=%.6f)",
                    wind_code,
                    quarter,
                    validation.reason,
                    validation.total_weight,
                )

            delete_sql = "DELETE FROM holdings WHERE wind_code = :wind_code AND quarter = :quarter"
            with self.engine.connect() as conn:
                conn.execute(text(delete_sql), {"wind_code": wind_code, "quarter": quarter})

                insert_sql = """
                INSERT INTO holdings (
                    fund_id, wind_code, quarter, stock_code, stock_name, industry, sub_industry,
                    weight, equity_portfolio_weight, weight_basis, weight_validation_status, announcement_date, report_date,
                    source, weight_source, weight_source_url, fund_net_asset, fund_net_asset_basis, fund_net_asset_date, synced_at,
                    updated_at, shares, market_cap, pe_ratio, pb_ratio, roe,
                    revenue_growth, dividend_yield, market_cap_value
                ) VALUES (
                    (SELECT id::text FROM funds WHERE wind_code = :wind_code),
                    :wind_code, :quarter, :stock_code, :stock_name, :industry, :sub_industry,
                    :weight, :equity_portfolio_weight, :weight_basis, :weight_validation_status, :announcement_date, :report_date,
                    :source, :weight_source, :weight_source_url, :fund_net_asset, :fund_net_asset_basis, :fund_net_asset_date, NOW(),
                    NOW(), :shares, :market_cap, :pe_ratio, :pb_ratio, :roe,
                    :revenue_growth, :dividend_yield, :market_cap_value
                )
                ON CONFLICT (wind_code, quarter, stock_code) DO UPDATE SET
                    fund_id = EXCLUDED.fund_id,
                    stock_name = EXCLUDED.stock_name,
                    industry = EXCLUDED.industry,
                    weight = EXCLUDED.weight,
                    equity_portfolio_weight = EXCLUDED.equity_portfolio_weight,
                    weight_basis = EXCLUDED.weight_basis,
                    weight_validation_status = EXCLUDED.weight_validation_status,
                    source = EXCLUDED.source,
                    weight_source = EXCLUDED.weight_source,
                    weight_source_url = EXCLUDED.weight_source_url,
                    fund_net_asset = EXCLUDED.fund_net_asset,
                    fund_net_asset_basis = EXCLUDED.fund_net_asset_basis,
                    fund_net_asset_date = EXCLUDED.fund_net_asset_date,
                    announcement_date = EXCLUDED.announcement_date,
                    report_date = EXCLUDED.report_date,
                    synced_at = NOW(),
                    updated_at = NOW(),
                    shares = EXCLUDED.shares
                """

                for h in holdings:
                    params = {
                        "wind_code": wind_code,
                        "quarter": quarter,
                        "stock_code": h.get("stock_code", ""),
                        "stock_name": h.get("stock_name", ""),
                        "industry": h.get("industry", ""),
                        "sub_industry": h.get("sub_industry"),
                        "weight": _clean(h.get("fund_nav_weight", h.get("weight"))),
                        "equity_portfolio_weight": _clean(h.get("equity_portfolio_weight")),
                        "weight_basis": h.get("weight_basis") or "unknown",
                        "weight_validation_status": h.get("weight_validation_status") or validation.status,
                        "source": h.get("source"),
                        "weight_source": h.get("weight_source"),
                        "weight_source_url": h.get("weight_source_url"),
                        "fund_net_asset": _clean(h.get("fund_net_asset")),
                        "fund_net_asset_basis": h.get("fund_net_asset_basis"),
                        "fund_net_asset_date": h.get("fund_net_asset_date"),
                        "announcement_date": h.get("announcement_date"),
                        "report_date": h.get("report_date"),
                        "shares": h.get("shares"),
                        "market_cap": h.get("market_cap"),
                        "pe_ratio": _clean(h.get("pe_ratio")),
                        "pb_ratio": _clean(h.get("pb_ratio")),
                        "roe": _clean(h.get("roe")),
                        "revenue_growth": _clean(h.get("revenue_growth")),
                        "dividend_yield": _clean(h.get("dividend_yield")),
                        "market_cap_value": _clean(h.get("market_cap_value")),
                    }
                    try:
                        conn.execute(text(insert_sql), params)
                    except Exception as e:
                        logger.warning(f"Insert holding error: {e}")
                        continue
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"upsert_holdings error for {wind_code} {quarter}: {e}")
            return False

    def get_holdings(self, wind_code: str, quarter: str) -> List[Dict[str, Any]]:
        """获取基金持仓"""
        try:
            from sqlalchemy import text
            sql = """
                SELECT * FROM holdings
                WHERE wind_code = :wind_code AND quarter = :quarter
                ORDER BY COALESCE(weight, equity_portfolio_weight) DESC NULLS LAST
            """
            with self.engine.connect() as conn:
                result = conn.execute(text(sql), {"wind_code": wind_code, "quarter": quarter})
                return [dict(r._mapping) for r in result.fetchall()]
        except Exception as e:
            logger.error(f"get_holdings error: {e}")
            return []

    def get_holdings_history(self, wind_code: str) -> List[Dict[str, Any]]:
        """获取基金历史持仓"""
        try:
            from sqlalchemy import text
            sql = """
                SELECT * FROM holdings
                WHERE wind_code = :wind_code
                ORDER BY quarter DESC, COALESCE(weight, equity_portfolio_weight) DESC NULLS LAST
            """
            with self.engine.connect() as conn:
                result = conn.execute(text(sql), {"wind_code": wind_code})
                return [dict(r._mapping) for r in result.fetchall()]
        except Exception as e:
            logger.error(f"get_holdings_history error: {e}")
            return []

    def get_latest_weighted_quarter(self, wind_code: str) -> Optional[str]:
        """返回最近一个具备基金净值权重的公开持仓季度。"""
        try:
            from sqlalchemy import text

            sql = """
                SELECT quarter
                FROM holdings
                WHERE wind_code = :wind_code
                  AND weight IS NOT NULL
                  AND weight > 0
                GROUP BY quarter
                ORDER BY quarter DESC
                LIMIT 1
            """
            with self.engine.connect() as conn:
                row = conn.execute(text(sql), {"wind_code": wind_code}).fetchone()
            return str(row.quarter) if row else None
        except Exception as e:
            logger.error(f"get_latest_weighted_quarter error: {e}")
            return None

    def get_holdings_map(self, wind_codes: List[str], quarter: str) -> Dict[str, List[Dict[str, Any]]]:
        """批量读取同一季度持仓，供同类横截面比较。"""
        normalized_codes = list(dict.fromkeys(
            str(code or "").strip().upper()
            for code in wind_codes
            if str(code or "").strip()
        ))
        if not normalized_codes or not quarter:
            return {}
        try:
            from sqlalchemy import text

            sql = """
                SELECT *
                FROM holdings
                WHERE wind_code = ANY(:wind_codes)
                  AND quarter = :quarter
                ORDER BY wind_code, COALESCE(weight, equity_portfolio_weight) DESC NULLS LAST
            """
            with self.engine.connect() as conn:
                rows = conn.execute(
                    text(sql),
                    {"wind_codes": normalized_codes, "quarter": quarter},
                ).fetchall()
            result: Dict[str, List[Dict[str, Any]]] = {}
            for row in rows:
                item = dict(row._mapping)
                result.setdefault(str(item.get("wind_code") or ""), []).append(item)
            return result
        except Exception as e:
            logger.error(f"get_holdings_map error: {e}")
            return {}
