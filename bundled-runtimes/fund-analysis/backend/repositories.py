"""
基金数据仓储层 - PostgreSQL 实现
将 Tushare 数据持久化到 PostgreSQL
"""
import os
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from decimal import Decimal
import json

logger = logging.getLogger(__name__)


def _json_serializer(obj):
    """JSON 序列化器，处理 Decimal 和 date 类型"""
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def _to_dict(row) -> Dict[str, Any]:
    """将数据库行转为字典"""
    if row is None:
        return {}
    result = {}
    for key, value in row._asdict().items():
        if isinstance(value, (datetime, date)):
            result[key] = value.isoformat()
        elif isinstance(value, Decimal):
            result[key] = float(value)
        elif isinstance(value, list):
            result[key] = value
        elif isinstance(value, dict):
            result[key] = value
        else:
            result[key] = value
    return result


def _from_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    """将字典转为数据库格式"""
    result = {}
    for k, v in data.items():
        if isinstance(v, (int, float, str, bool, type(None))):
            result[k] = v
        elif isinstance(v, (datetime, date)):
            result[k] = v.isoformat()
        elif isinstance(v, dict):
            result[k] = json.dumps(v, default=_json_serializer)
        elif isinstance(v, list):
            result[k] = json.dumps(v, default=_json_serializer)
    return result


class FundRepository:
    """基金数据仓储"""

    def __init__(self):
        self._engine = None

    @property
    def engine(self):
        if self._engine is None:
            from database import get_engine
            self._engine = get_engine()
        return self._engine

    def get_fund(self, wind_code: str) -> Optional[Dict[str, Any]]:
        """获取基金详情"""
        from sqlalchemy import text
        with self.engine.connect() as conn:
            row = conn.execute(
                text("SELECT * FROM funds WHERE wind_code = :code"),
                {"code": wind_code}
            ).fetchone()
            if row:
                d = _to_dict(row)
                # 反序列化 JSON 字段
                for field in ["performance_data", "risk_metrics", "raw_data"]:
                    if d.get(field) and isinstance(d[field], str):
                        try:
                            d[field] = json.loads(d[field])
                        except:
                            pass
                return d
            return None

    def upsert_fund(self, wind_code: str, data: Dict[str, Any]) -> bool:
        """插入或更新基金数据"""
        from sqlalchemy import text

        row = {
            "wind_code": wind_code,
            "name": data.get("name", wind_code),
            "type": data.get("type"),
            "manager_ids": data.get("manager_ids", []),
            "nav": data.get("nav"),
            "nav_date": data.get("nav_date"),
            "total_asset": data.get("total_asset"),
            "establishment_date": data.get("establishment_date"),
            "performance_data": json.dumps(data.get("performance_data", data.get("performance", {})), default=_json_serializer),
            "risk_metrics": json.dumps(data.get("risk_metrics", {}), default=_json_serializer),
            "raw_data": json.dumps(data.get("raw_data", {}), default=_json_serializer),
            "updated_at": datetime.now().isoformat(),
        }

        sql = text("""
            INSERT INTO funds (
                wind_code, name, type, manager_ids, nav, nav_date, total_asset,
                establishment_date, performance_data, risk_metrics, raw_data, updated_at
            ) VALUES (
                :wind_code, :name, :type, :manager_ids, :nav, :nav_date, :total_asset,
                :establishment_date, :performance_data::jsonb, :risk_metrics::jsonb,
                :raw_data::jsonb, :updated_at::timestamp
            )
            ON CONFLICT (wind_code) DO UPDATE SET
                name = EXCLUDED.name,
                type = EXCLUDED.type,
                nav = EXCLUDED.nav,
                nav_date = EXCLUDED.nav_date,
                total_asset = EXCLUDED.total_asset,
                performance_data = EXCLUDED.performance_data,
                risk_metrics = EXCLUDED.risk_metrics,
                raw_data = EXCLUDED.raw_data,
                updated_at = EXCLUDED.updated_at
        """)

        try:
            with self.engine.connect() as conn:
                conn.execute(sql, row)
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Upsert fund error for {wind_code}: {e}")
            return False

    def list_funds(
        self,
        fund_type: Optional[str] = None,
        keyword: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
        sort_by: str = "wind_code",
        sort_order: str = "asc",
    ) -> Dict[str, Any]:
        """分页查询基金列表"""
        from sqlalchemy import text

        conditions = []
        params = {}

        if fund_type:
            conditions.append("type = :fund_type")
            params["fund_type"] = fund_type

        if keyword:
            conditions.append("(name ILIKE :keyword OR wind_code ILIKE :keyword)")
            params["keyword"] = f"%{keyword}%"

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        # 排序
        allowed_sort = {"wind_code", "name", "nav", "total_asset", "created_at"}
        sort_col = sort_by if sort_by in allowed_sort else "wind_code"
        sort_dir = "DESC" if sort_order == "desc" else "ASC"

        # 总数
        count_sql = text(f"SELECT COUNT(*) FROM funds {where_clause}")
        with self.engine.connect() as conn:
            total = conn.execute(count_sql, params).scalar()

        # 分页数据
        offset = (page - 1) * page_size
        params["offset"] = offset
        params["limit"] = page_size

        data_sql = text(f"""
            SELECT * FROM funds
            {where_clause}
            ORDER BY {sort_col} {sort_dir}
            LIMIT :limit OFFSET :offset
        """)

        with self.engine.connect() as conn:
            rows = conn.execute(data_sql, params).fetchall()
            funds = [_to_dict(r) for r in rows]

        return {"total": total, "page": page, "page_size": page_size, "funds": funds}

    def save_score(self, wind_code: str, scoring: Dict[str, Any]) -> bool:
        """保存基金评分"""
        from sqlalchemy import text
        from datetime import datetime

        scored_at = datetime.now()

        # 插入总评分
        sql = text("""
            INSERT INTO scores (
                target_type, target_id, dimension, score, calculation_method, scored_at
            ) VALUES (:type, :id, :dim, :score, :method, :scored_at)
        """)

        try:
            with self.engine.connect() as conn:
                # 保存综合评分
                conn.execute(sql, {
                    "type": "fund",
                    "id": wind_code,
                    "dim": "overall",
                    "score": scoring.get("overall_score", 50),
                    "method": "quantitative",
                    "scored_at": scored_at,
                })

                # 保存维度评分
                for dim_key, dim_data in scoring.get("dimension_scores", {}).items():
                    if isinstance(dim_data, dict):
                        score_val = dim_data.get("score", dim_data.get("weighted_score", 50))
                    else:
                        score_val = dim_data
                    conn.execute(sql, {
                        "type": "fund",
                        "id": wind_code,
                        "dim": dim_key,
                        "score": score_val,
                        "method": "quantitative",
                        "scored_at": scored_at,
                    })

                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Save score error for {wind_code}: {e}")
            return False

    def get_scores(self, wind_code: str, limit: int = 30) -> List[Dict[str, Any]]:
        """获取评分历史"""
        from sqlalchemy import text
        sql = text("""
            SELECT * FROM scores
            WHERE target_type = 'fund' AND target_id = :code
            ORDER BY scored_at DESC
            LIMIT :limit
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {"code": wind_code, "limit": limit}).fetchall()
            return [_to_dict(r) for r in rows]


class HoldingRepository:
    """持仓数据仓储"""

    def __init__(self):
        self._engine = None

    @property
    def engine(self):
        if self._engine is None:
            from database import get_engine
            self._engine = get_engine()
        return self._engine

    def upsert_holdings(self, wind_code: str, quarter: str, holdings: List[Dict]) -> bool:
        """批量插入持仓数据"""
        from sqlalchemy import text

        if not holdings:
            return True

        sql = text("""
            INSERT INTO holdings (
                wind_code, quarter, stock_code, stock_name, industry,
                weight, market_cap, pe_ratio, pb_ratio, roe,
                revenue_growth, dividend_yield, market_cap_value
            ) VALUES (
                :wind_code, :quarter, :stock_code, :stock_name, :industry,
                :weight, :market_cap, :pe_ratio, :pb_ratio, :roe,
                :revenue_growth, :dividend_yield, :market_cap_value
            )
            ON CONFLICT (wind_code, quarter, stock_code) DO UPDATE SET
                stock_name = EXCLUDED.stock_name,
                industry = EXCLUDED.industry,
                weight = EXCLUDED.weight
        """)

        try:
            with self.engine.connect() as conn:
                for h in holdings:
                    conn.execute(sql, {
                        "wind_code": wind_code,
                        "quarter": quarter,
                        "stock_code": h.get("stock_code", ""),
                        "stock_name": h.get("stock_name", ""),
                        "industry": h.get("industry", ""),
                        "weight": h.get("weight"),
                        "market_cap": h.get("market_cap"),
                        "pe_ratio": h.get("pe_ratio"),
                        "pb_ratio": h.get("pb_ratio"),
                        "roe": h.get("roe"),
                        "revenue_growth": h.get("revenue_growth"),
                        "dividend_yield": h.get("dividend_yield"),
                        "market_cap_value": h.get("market_cap_value"),
                    })
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Upsert holdings error for {wind_code} {quarter}: {e}")
            return False

    def get_holdings(self, wind_code: str, quarter: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取持仓数据"""
        from sqlalchemy import text

        if quarter:
            sql = text("""
                SELECT * FROM holdings
                WHERE wind_code = :code AND quarter = :quarter
                ORDER BY weight DESC
            """)
            params = {"code": wind_code, "quarter": quarter}
        else:
            sql = text("""
                SELECT * FROM holdings
                WHERE wind_code = :code
                ORDER BY quarter DESC, weight DESC
            """)
            params = {"code": wind_code}

        with self.engine.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [_to_dict(r) for r in rows]


class FactorExposureRepository:
    """因子暴露度仓储"""

    def __init__(self):
        self._engine = None

    @property
    def engine(self):
        if self._engine is None:
            from database import get_engine
            self._engine = get_engine()
        return self._engine

    def save_exposures(self, wind_code: str, quarter: str, exposures: Dict[str, float],
                       risk_contributions: Optional[List[Dict]] = None) -> bool:
        """保存 Barra 因子暴露度"""
        from sqlalchemy import text

        sql = text("""
            INSERT INTO factor_exposures (
                wind_code, quarter, factor_name, exposure, risk_contribution
            ) VALUES (
                :wind_code, :quarter, :factor_name, :exposure, :risk_contribution
            )
            ON CONFLICT (wind_code, quarter, factor_name) DO UPDATE SET
                exposure = EXCLUDED.exposure,
                risk_contribution = EXCLUDED.risk_contribution
        """)

        try:
            with self.engine.connect() as conn:
                for factor, exposure in exposures.items():
                    rc = None
                    if risk_contributions:
                        for rc_item in risk_contributions:
                            if rc_item.get("factor") == factor:
                                rc = rc_item.get("risk_contribution")
                                break
                    conn.execute(sql, {
                        "wind_code": wind_code,
                        "quarter": quarter,
                        "factor_name": factor,
                        "exposure": exposure,
                        "risk_contribution": rc,
                    })
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Save exposures error for {wind_code}: {e}")
            return False

    def get_exposures(self, wind_code: str, quarter: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取因子暴露度"""
        from sqlalchemy import text

        if quarter:
            sql = text("""
                SELECT * FROM factor_exposures
                WHERE wind_code = :code AND quarter = :quarter
                ORDER BY risk_contribution DESC NULLS LAST
            """)
            params = {"code": wind_code, "quarter": quarter}
        else:
            sql = text("""
                SELECT * FROM factor_exposures
                WHERE wind_code = :code
                ORDER BY quarter DESC, risk_contribution DESC NULLS LAST
            """)
            params = {"code": wind_code}

        with self.engine.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [_to_dict(r) for r in rows]


class AttributionRepository:
    """业绩归因仓储"""

    def __init__(self):
        self._engine = None

    @property
    def engine(self):
        if self._engine is None:
            from database import get_engine
            self._engine = get_engine()
        return self._engine

    def save_attribution(self, wind_code: str, quarter: str, benchmark_id: str,
                         data: Dict[str, Any]) -> bool:
        """保存 Brinson 归因结果"""
        from sqlalchemy import text

        sql = text("""
            INSERT INTO performance_attributions (
                wind_code, benchmark_id, quarter, total_return, benchmark_return,
                active_return, allocation_effect, selection_effect, interaction_effect
            ) VALUES (
                :wind_code, :benchmark_id, :quarter, :total_return, :benchmark_return,
                :active_return, :allocation_effect, :selection_effect, :interaction_effect
            )
            ON CONFLICT (wind_code, quarter) DO UPDATE SET
                total_return = EXCLUDED.total_return,
                active_return = EXCLUDED.active_return,
                allocation_effect = EXCLUDED.allocation_effect,
                selection_effect = EXCLUDED.selection_effect,
                interaction_effect = EXCLUDED.interaction_effect
        """)

        try:
            with self.engine.connect() as conn:
                conn.execute(sql, {
                    "wind_code": wind_code,
                    "benchmark_id": benchmark_id,
                    "quarter": quarter,
                    "total_return": data.get("returns", {}).get("fund") or data.get("returns", {}).get("portfolio"),
                    "benchmark_return": data.get("returns", {}).get("benchmark"),
                    "active_return": data.get("returns", {}).get("active"),
                    "allocation_effect": data.get("attribution", {}).get("allocation_effect"),
                    "selection_effect": data.get("attribution", {}).get("selection_effect"),
                    "interaction_effect": data.get("attribution", {}).get("interaction_effect"),
                })
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Save attribution error for {wind_code}: {e}")
            return False


class ManagerRepository:
    """基金经理仓储"""

    def __init__(self):
        self._engine = None

    @property
    def engine(self):
        if self._engine is None:
            from database import get_engine
            self._engine = get_engine()
        return self._engine

    def upsert_manager(self, manager_id: str, data: Dict[str, Any]) -> bool:
        """插入或更新经理数据"""
        from sqlalchemy import text

        sql = text("""
            INSERT INTO managers (
                wind_code, name, company, education, work_years,
                management_years, historical_performance, style_analysis, raw_data
            ) VALUES (
                :manager_id, :name, :company, :education, :work_years,
                :management_years, :historical_performance::jsonb, :style_analysis::jsonb,
                :raw_data::jsonb
            )
            ON CONFLICT (wind_code) DO UPDATE SET
                name = EXCLUDED.name,
                company = EXCLUDED.company,
                education = EXCLUDED.education,
                work_years = EXCLUDED.work_years,
                management_years = EXCLUDED.management_years,
                historical_performance = EXCLUDED.historical_performance,
                style_analysis = EXCLUDED.style_analysis,
                raw_data = EXCLUDED.raw_data
        """)

        try:
            with self.engine.connect() as conn:
                conn.execute(sql, {
                    "manager_id": manager_id,
                    "name": data.get("name", manager_id),
                    "company": data.get("company"),
                    "education": data.get("education"),
                    "work_years": data.get("experience_years") or data.get("work_years"),
                    "management_years": data.get("management_years"),
                    "historical_performance": json.dumps(data.get("historical_performance", {}), default=_json_serializer),
                    "style_analysis": json.dumps(data.get("style_analysis", {}), default=_json_serializer),
                    "raw_data": json.dumps(data.get("raw_data", {}), default=_json_serializer),
                })
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"Upsert manager error for {manager_id}: {e}")
            return False

    def get_manager(self, manager_id: str) -> Optional[Dict[str, Any]]:
        """获取经理详情"""
        from sqlalchemy import text
        sql = text("SELECT * FROM managers WHERE wind_code = :code OR name = :code LIMIT 1")
        with self.engine.connect() as conn:
            row = conn.execute(sql, {"code": manager_id}).fetchone()
            return _to_dict(row) if row else None

    def list_managers(self, company: Optional[str] = None, keyword: Optional[str] = None,
                      page: int = 1, page_size: int = 50) -> Dict[str, Any]:
        """分页查询经理列表"""
        from sqlalchemy import text

        conditions = []
        params = {}

        if company:
            conditions.append("company ILIKE :company")
            params["company"] = f"%{company}%"
        if keyword:
            conditions.append("name ILIKE :keyword")
            params["keyword"] = f"%{keyword}%"

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""

        count_sql = text(f"SELECT COUNT(*) FROM managers {where_clause}")
        with self.engine.connect() as conn:
            total = conn.execute(count_sql, params).scalar()

        offset = (page - 1) * page_size
        params["offset"] = offset
        params["limit"] = page_size

        sql = text(f"""
            SELECT * FROM managers
            {where_clause}
            ORDER BY name ASC
            LIMIT :limit OFFSET :offset
        """)

        with self.engine.connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            managers = [_to_dict(r) for r in rows]

        return {"total": total, "page": page, "page_size": page_size, "managers": managers}


# 全局实例
_fund_repo = None
_holding_repo = None
_factor_repo = None
_attr_repo = None
_manager_repo = None


def get_fund_repo() -> FundRepository:
    global _fund_repo
    if _fund_repo is None:
        _fund_repo = FundRepository()
    return _fund_repo


def get_holding_repo() -> HoldingRepository:
    global _holding_repo
    if _holding_repo is None:
        _holding_repo = HoldingRepository()
    return _holding_repo


def get_factor_repo() -> FactorExposureRepository:
    global _factor_repo
    if _factor_repo is None:
        _factor_repo = FactorExposureRepository()
    return _factor_repo


def get_attribution_repo() -> AttributionRepository:
    global _attr_repo
    if _attr_repo is None:
        _attr_repo = AttributionRepository()
    return _attr_repo


def get_manager_repo() -> ManagerRepository:
    global _manager_repo
    if _manager_repo is None:
        _manager_repo = ManagerRepository()
    return _manager_repo
