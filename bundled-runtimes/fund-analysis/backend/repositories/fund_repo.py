"""
基金 Repository - PostgreSQL 数据访问层
"""
import os
import math
import json
import numbers
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, date
import logging

try:
    from backend.lib.fund_status import active_fund_sql
except ModuleNotFoundError:
    from lib.fund_status import active_fund_sql

try:
    from backend.database import get_database_url
except ModuleNotFoundError:
    from database import get_database_url

logger = logging.getLogger(__name__)

# Lazy init
_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        from sqlalchemy import create_engine
        pg_url = get_database_url()
        _engine = create_engine(pg_url, pool_pre_ping=True, pool_size=20, max_overflow=30, pool_recycle=3600)
    return _engine


def _clean_value(v):
    """清理 NaN/Inf 值"""
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return v


def _json_serializer(obj):
    """JSON 序列化器"""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _clean_json_value(obj):
    """递归清理 JSONB 入库值，避免 NaN/Inf 写成 PostgreSQL 非法 JSON。"""
    if isinstance(obj, dict):
        return {str(key): _clean_json_value(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_clean_json_value(item) for item in obj]
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, numbers.Real) and not isinstance(obj, bool):
        number_value = float(obj)
        if math.isnan(number_value) or math.isinf(number_value):
            return None
        if isinstance(obj, int):
            return obj
        return number_value
    return obj


def _parse_date(value) -> Optional[str]:
    """解析日期值，返回 YYYY-MM-DD 格式或 None"""
    if not value:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()[:10]
    # 字符串处理
    s = str(value).strip()
    if s in ("", "None", "null", "nan"):
        return None
    # 尝试解析常见格式
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    # 无法解析，返回 None
    logger.warning(f"无法解析日期: {value}")
    return None


def _table_exists(conn, table_name: str) -> bool:
    from sqlalchemy import text
    result = conn.execute(text("""
        SELECT to_regclass(:table_name) IS NOT NULL AS exists
    """), {"table_name": f"public.{table_name}"})
    row = result.fetchone()
    return bool(row and row[0])


def _column_exists(conn, table_name: str, column_name: str) -> bool:
    from sqlalchemy import text
    result = conn.execute(text("""
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
              AND column_name = :column_name
        ) AS exists
    """), {"table_name": table_name, "column_name": column_name})
    row = result.fetchone()
    return bool(row and row[0])


class FundRepo:
    """基金数据访问层"""

    def __init__(self):
        self._engine = None

    @property
    def engine(self):
        if self._engine is None:
            self._engine = _get_engine()
        return self._engine

    def upsert_fund(self, wind_code: str, data: Dict[str, Any]) -> bool:
        """Upsert 基金数据"""
        try:
            from sqlalchemy import text

            # 序列化 JSON 字段
            perf_data = data.get("performance_data") or data.get("performance") or {}
            risk_data = data.get("risk_metrics") or {}
            raw_data = data.get("raw_data") or {}

            sql = """
            INSERT INTO funds (wind_code, name, type, manager_ids, nav, nav_date, total_asset, establishment_date,
                              performance_data, risk_metrics, raw_data, updated_at)
            VALUES (:wind_code, :name, :type, :manager_ids, :nav, :nav_date, :total_asset, :est_date,
                    :perf_data, :risk_data, :raw_data, NOW())
            ON CONFLICT (wind_code) DO UPDATE SET
                name = EXCLUDED.name,
                type = EXCLUDED.type,
                manager_ids = CASE
                    WHEN COALESCE(cardinality(EXCLUDED.manager_ids), 0) = 0 THEN funds.manager_ids
                    ELSE EXCLUDED.manager_ids
                END,
                nav = COALESCE(EXCLUDED.nav, funds.nav),
                nav_date = COALESCE(EXCLUDED.nav_date, funds.nav_date),
                total_asset = COALESCE(EXCLUDED.total_asset, funds.total_asset),
                establishment_date = COALESCE(EXCLUDED.establishment_date, funds.establishment_date),
                performance_data = COALESCE(funds.performance_data, '{}'::jsonb) || EXCLUDED.performance_data,
                risk_metrics = COALESCE(funds.risk_metrics, '{}'::jsonb) || EXCLUDED.risk_metrics,
                raw_data = CASE
                    WHEN EXCLUDED.raw_data = '{}'::jsonb THEN funds.raw_data
                    ELSE COALESCE(funds.raw_data, '{}'::jsonb) || EXCLUDED.raw_data
                END,
                updated_at = NOW()
            """
            params = {
                "wind_code": wind_code,
                "name": data.get("name", ""),
                "type": data.get("type", ""),
                "manager_ids": data.get("manager_ids") or [],
                "nav": _clean_value(data.get("nav")),
                "nav_date": data.get("nav_date"),
                "total_asset": _clean_value(data.get("total_asset")),
                "est_date": _parse_date(data.get("establishment_date")),
                "perf_data": json.dumps(_clean_json_value(perf_data), default=_json_serializer, allow_nan=False),
                "risk_data": json.dumps(_clean_json_value(risk_data), default=_json_serializer, allow_nan=False),
                "raw_data": json.dumps(_clean_json_value(raw_data), default=_json_serializer, allow_nan=False),
            }

            with self.engine.connect() as conn:
                conn.execute(text(sql), params)
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"upsert_fund error for {wind_code}: {e}")
            return False

    def get_fund(self, wind_code: str) -> Optional[Dict[str, Any]]:
        """获取单个基金"""
        try:
            from sqlalchemy import text
            sql = "SELECT * FROM funds WHERE wind_code = :wind_code"
            with self.engine.connect() as conn:
                result = conn.execute(text(sql), {"wind_code": wind_code})
                row = result.fetchone()
                if row:
                    return dict(row._mapping)
                return None
        except Exception as e:
            logger.error(f"get_fund error: {e}")
            return None

    def update_product_profile(self, wind_code: str, profile: Dict[str, Any]) -> bool:
        """将公开基金档案写入 raw_data，保留已有净值、分类和经理数据。"""
        try:
            from sqlalchemy import text

            with self.engine.begin() as conn:
                result = conn.execute(text("""
                    UPDATE funds
                    SET raw_data = COALESCE(raw_data, '{}'::jsonb)
                        || jsonb_build_object('product_profile', CAST(:profile AS jsonb)),
                        updated_at = NOW()
                    WHERE wind_code = :wind_code
                """), {
                    "wind_code": wind_code,
                    "profile": json.dumps(_clean_json_value(profile), ensure_ascii=False, default=_json_serializer),
                })
            return result.rowcount > 0
        except Exception as e:
            logger.error(f"update_product_profile error for {wind_code}: {e}")
            return False

    def update_manager_assignments(
        self,
        wind_code: str,
        manager_ids: List[str],
        manager_sync: Dict[str, Any],
    ) -> bool:
        """只更新真实经理任职关系，不改写基金行情和分类事实。"""
        try:
            from sqlalchemy import text

            with self.engine.begin() as conn:
                result = conn.execute(text("""
                    UPDATE funds
                    SET manager_ids = :manager_ids,
                        raw_data = COALESCE(raw_data, '{}'::jsonb)
                            || jsonb_build_object('manager_sync', CAST(:manager_sync AS jsonb)),
                        updated_at = NOW()
                    WHERE wind_code = :wind_code
                """), {
                    "wind_code": wind_code,
                    "manager_ids": list(dict.fromkeys(manager_ids)),
                    "manager_sync": json.dumps(
                        _clean_json_value(manager_sync),
                        default=_json_serializer,
                        ensure_ascii=False,
                        allow_nan=False,
                    ),
                })
            return bool(result.rowcount)
        except Exception as e:
            logger.error(f"update_manager_assignments error for {wind_code}: {e}")
            return False

    def get_fund_by_identifier(self, identifier: str) -> Optional[Dict[str, Any]]:
        """按 UUID 或 wind_code 获取单个基金"""
        try:
            from sqlalchemy import text
            sql = """
                SELECT * FROM funds
                WHERE id::text = :identifier OR wind_code = :identifier
                LIMIT 1
            """
            with self.engine.connect() as conn:
                result = conn.execute(text(sql), {"identifier": identifier})
                row = result.fetchone()
                if row:
                    return dict(row._mapping)
                return None
        except Exception as e:
            logger.error(f"get_fund_by_identifier error: {e}")
            return None

    def browse_funds(
        self,
        keyword: Optional[str] = None,
        page: int = 1,
        page_size: int = 30,
        availability: str = "all",
    ) -> Tuple[List[Dict[str, Any]], int]:
        """基金浏览器只读取基金研究基础事实，不连接销售规则或投资处置表。"""
        from sqlalchemy import text

        normalized_availability = str(availability or "all").strip().lower()
        if normalized_availability not in {"evaluated", "classified", "all"}:
            normalized_availability = "all"
        if normalized_availability != "all":
            return self._browse_standardized_funds(
                keyword=keyword,
                page=page,
                page_size=page_size,
                availability=normalized_availability,
            )

        normalized_keyword = str(keyword or "").strip()
        params = {
            "keyword": normalized_keyword,
            "keyword_pattern": f"%{normalized_keyword}%",
            "limit": max(1, min(int(page_size), 100)),
            "offset": max(0, int(page) - 1) * max(1, min(int(page_size), 100)),
        }
        where_sql = """
            ({active_clause})
            AND (
                :keyword = ''
                OR name ILIKE :keyword_pattern
                OR wind_code ILIKE :keyword_pattern
            )
        """
        where_sql = where_sql.format(active_clause=active_fund_sql())
        data_sql = text(f"""
            SELECT
                funds.id, funds.wind_code, funds.name, funds.type, funds.manager_ids,
                funds.total_asset, funds.nav, funds.nav_date, funds.establishment_date,
                funds.performance_data, funds.risk_metrics, funds.raw_data, funds.updated_at,
                COALESCE(metric_quality.quality_metric_count, 0) AS quality_metric_count
            FROM funds
            LEFT JOIN (
                SELECT
                    target_id,
                    COUNT(DISTINCT metric_name) FILTER (
                        WHERE metric_window = '1y'
                          AND metric_name IN ('annualized_return', 'max_drawdown', 'sharpe_ratio', 'annualized_volatility')
                    ) AS quality_metric_count,
                    MAX(as_of_date) AS latest_metric_date
                FROM metric_snapshots
                WHERE target_type = 'fund'
                GROUP BY target_id
            ) metric_quality ON metric_quality.target_id = funds.wind_code
            WHERE {where_sql}
            ORDER BY
                COALESCE(metric_quality.quality_metric_count, 0) DESC,
                metric_quality.latest_metric_date DESC NULLS LAST,
                CASE WHEN COALESCE(cardinality(funds.manager_ids), 0) > 0 THEN 0 ELSE 1 END,
                funds.nav_date DESC NULLS LAST,
                funds.updated_at DESC NULLS LAST,
                funds.wind_code ASC
            LIMIT :limit OFFSET :offset
        """)
        count_sql = text(f"SELECT COUNT(*) FROM funds WHERE {where_sql}")
        with self.engine.connect() as conn:
            rows = conn.execute(data_sql, params).fetchall()
            total = int(conn.execute(count_sql, params).scalar() or 0)
        return [dict(row._mapping) for row in rows], total

    def _browse_standardized_funds(
        self,
        keyword: Optional[str],
        page: int,
        page_size: int,
        availability: str,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """按基金实体展示已分类或真正可评价的代表份额。"""
        from sqlalchemy import text

        required_tables = (
            "fund_entities",
            "fund_share_classes",
            "strategy_families",
            "peer_groups",
            "peer_group_members",
            "benchmark_mappings",
            "metric_snapshots",
        )
        with self.engine.connect() as conn:
            if not all(_table_exists(conn, table_name) for table_name in required_tables):
                return [], 0

        normalized_keyword = str(keyword or "").strip()
        limit = max(1, min(int(page_size), 100))
        params = {
            "keyword": normalized_keyword,
            "keyword_pattern": f"%{normalized_keyword}%",
            "availability": availability,
            "limit": limit,
            "offset": max(0, int(page) - 1) * limit,
        }
        number_pattern = "'^-?[0-9]+(\\.[0-9]+)?$'"

        def numeric_json(expression: str) -> str:
            return (
                f"CASE WHEN NULLIF({expression}, '') ~ {number_pattern} "
                f"THEN NULLIF({expression}, '')::numeric END"
            )

        return_fallback = numeric_json(
            "COALESCE(fund.performance_data->>'annualized_return_1y', "
            "fund.performance_data->>'return_1y', fund.performance_data->>'annual_return')"
        )
        drawdown_fallback = numeric_json(
            "COALESCE(fund.risk_metrics->>'max_drawdown_1y', "
            "fund.risk_metrics->>'max_drawdown', fund.performance_data->>'max_drawdown_1y', "
            "fund.performance_data->>'max_drawdown')"
        )
        sharpe_fallback = numeric_json(
            "COALESCE(fund.performance_data->>'sharpe_ratio', "
            "fund.performance_data->>'sharpe', fund.risk_metrics->>'sharpe_ratio')"
        )
        tracking_error_fallback = numeric_json("fund.risk_metrics->>'tracking_error'")
        tracking_difference_fallback = numeric_json(
            "COALESCE(fund.performance_data->>'tracking_difference', "
            "fund.performance_data->>'excess_return')"
        )
        seven_day_yield_fallback = numeric_json(
            "COALESCE(fund.performance_data->>'seven_day_annualized_yield', "
            "fund.performance_data->>'yield_7d', fund.performance_data->>'seven_day_yield')"
        )
        management_fee_raw = numeric_json(
            "COALESCE(fund.raw_data#>>'{info,management_fee}', fund.raw_data#>>'{info,m_fee}', "
            "fund.raw_data#>>'{universe,management_fee}', fund.raw_data#>>'{universe,m_fee}')"
        )
        custodian_fee_raw = numeric_json(
            "COALESCE(fund.raw_data#>>'{info,custodian_fee}', fund.raw_data#>>'{info,c_fee}', "
            "fund.raw_data#>>'{universe,custodian_fee}', fund.raw_data#>>'{universe,c_fee}')"
        )
        fee_fallback = f"""
            CASE
                WHEN ({management_fee_raw}) IS NOT NULL OR ({custodian_fee_raw}) IS NOT NULL
                THEN
                    COALESCE(CASE WHEN ABS({management_fee_raw}) >= 0.05 THEN ({management_fee_raw}) / 100 ELSE ({management_fee_raw}) END, 0)
                    + COALESCE(CASE WHEN ABS({custodian_fee_raw}) >= 0.05 THEN ({custodian_fee_raw}) / 100 ELSE ({custodian_fee_raw}) END, 0)
            END
        """

        common_sql = f"""
            WITH candidate_funds AS (
                SELECT
                    fund.*,
                    entity.id AS entity_id,
                    entity.canonical_code,
                    entity.canonical_name,
                    share.is_primary,
                    family.key AS strategy_family_key,
                    family.name AS strategy_family_name,
                    COALESCE(entity.asset_class, family.asset_class) AS asset_class,
                    COALESCE(entity.active_passive, family.active_passive) AS active_passive,
                    peer.peer_group_id AS standardized_peer_group_id,
                    peer.peer_group_key AS standardized_peer_group_key,
                    peer.peer_group_name AS standardized_peer_group_name,
                    peer.minimum_peer_count,
                    peer.benchmark_code,
                    peer.benchmark_name,
                    {return_fallback} AS annualized_return_input,
                    {drawdown_fallback} AS max_drawdown_input,
                    {sharpe_fallback} AS sharpe_ratio_input,
                    {tracking_error_fallback} AS tracking_error_input,
                    {tracking_difference_fallback} AS tracking_difference_input,
                    {fee_fallback} AS expense_ratio_input,
                    fund.total_asset AS aum_input,
                    {seven_day_yield_fallback} AS seven_day_yield_input,
                    CASE
                        WHEN {return_fallback} IS NOT NULL THEN 1 ELSE 0
                    END
                    + CASE WHEN {drawdown_fallback} IS NOT NULL THEN 1 ELSE 0 END
                    + CASE WHEN {sharpe_fallback} IS NOT NULL THEN 1 ELSE 0 END
                    + CASE WHEN NULLIF(fund.risk_metrics->>'annualized_volatility_1y', '') ~ {number_pattern} THEN 1 ELSE 0 END
                    AS quality_metric_count,
                    CASE
                        WHEN NULLIF(fund.performance_data->>'updated_at', '') ~ '^\\d{{4}}-\\d{{2}}-\\d{{2}}'
                        THEN LEFT(fund.performance_data->>'updated_at', 10)::date
                        ELSE fund.nav_date
                    END AS latest_metric_date
                FROM fund_entities entity
                JOIN strategy_families family ON family.id = entity.strategy_family_id
                JOIN fund_share_classes share ON share.entity_id = entity.id AND share.status = 'active'
                JOIN funds fund ON fund.wind_code = share.wind_code
                JOIN LATERAL (
                    SELECT
                        group_row.id AS peer_group_id,
                        group_row.key AS peer_group_key,
                        group_row.name AS peer_group_name,
                        group_row.minimum_peer_count,
                        group_row.benchmark_code,
                        group_row.benchmark_name
                    FROM peer_group_members membership
                    JOIN peer_groups group_row ON group_row.id = membership.peer_group_id
                    WHERE membership.entity_id = entity.id
                      AND membership.role <> 'excluded'
                    ORDER BY
                        CASE membership.role WHEN 'primary' THEN 0 WHEN 'target' THEN 1 ELSE 2 END,
                        membership.sample_as_of_date DESC NULLS LAST,
                        membership.confidence DESC NULLS LAST,
                        group_row.updated_at DESC NULLS LAST
                    LIMIT 1
                ) peer ON TRUE
                JOIN LATERAL (
                    SELECT 1
                    FROM benchmark_mappings mapping
                    WHERE mapping.entity_id = entity.id
                      AND mapping.status = 'active'
                      AND (mapping.effective_from IS NULL OR mapping.effective_from <= CURRENT_DATE)
                      AND (mapping.effective_to IS NULL OR mapping.effective_to >= CURRENT_DATE)
                    ORDER BY mapping.confidence DESC NULLS LAST, mapping.updated_at DESC NULLS LAST
                    LIMIT 1
                ) benchmark_gate ON TRUE
                WHERE entity.lifecycle_stage = 'active'
                  AND ({active_fund_sql('fund')})
                  AND (
                      :keyword = ''
                      OR fund.name ILIKE :keyword_pattern
                      OR fund.wind_code ILIKE :keyword_pattern
                  )
            ),
            evaluated_candidates AS (
                SELECT
                    candidate_funds.*,
                    CASE
                        WHEN strategy_family_key IN (
                            'active_equity_core', 'active_equity_sector',
                            'fixed_income_general', 'fixed_income_credit', 'fixed_income_equity_allocation',
                            'mixed_equity_allocation', 'mixed_balanced_allocation', 'mixed_bond_allocation'
                        ) THEN
                            annualized_return_input IS NOT NULL
                            AND max_drawdown_input IS NOT NULL
                            AND sharpe_ratio_input IS NOT NULL
                        WHEN strategy_family_key IN ('index_broad', 'index_fixed_income') THEN
                            tracking_error_input BETWEEN 0 AND 0.10
                            AND ABS(tracking_difference_input) <= 0.25
                            AND expense_ratio_input BETWEEN 0 AND 0.05
                            AND aum_input > 0
                        WHEN strategy_family_key = 'cash_management' THEN
                            (CASE WHEN ABS(seven_day_yield_input) > 0.20 THEN seven_day_yield_input / 100 ELSE seven_day_yield_input END) BETWEEN 0 AND 0.20
                            AND (CASE WHEN ABS(annualized_return_input) > 0.20 THEN annualized_return_input / 100 ELSE annualized_return_input END) BETWEEN -0.05 AND 0.20
                            AND ABS(max_drawdown_input) <= 0.20
                            AND aum_input > 0
                        ELSE FALSE
                    END AS evaluation_ready
                FROM candidate_funds
            ),
            eligible_candidates AS (
                SELECT *
                FROM evaluated_candidates
                WHERE :availability = 'classified' OR evaluation_ready
            ),
            representative_funds AS (
                SELECT DISTINCT ON (entity_id) *
                FROM eligible_candidates
                ORDER BY
                    entity_id,
                    evaluation_ready DESC NULLS LAST,
                    is_primary DESC,
                    quality_metric_count DESC,
                    latest_metric_date DESC NULLS LAST,
                    nav_date DESC NULLS LAST,
                    wind_code ASC
            )
        """
        data_sql = text(common_sql + f"""
            SELECT
                id, wind_code, name, type, manager_ids, total_asset, nav, nav_date,
                establishment_date, performance_data, risk_metrics, raw_data, updated_at,
                strategy_family_key, strategy_family_name,
                entity_id, canonical_code, canonical_name, asset_class, active_passive,
                standardized_peer_group_id, standardized_peer_group_key,
                standardized_peer_group_name, minimum_peer_count,
                benchmark_code, benchmark_name,
                evaluation_ready, quality_metric_count,
                COUNT(*) OVER () AS full_count
            FROM representative_funds
            ORDER BY
                evaluation_ready DESC,
                quality_metric_count DESC,
                latest_metric_date DESC NULLS LAST,
                nav_date DESC NULLS LAST,
                wind_code ASC
            LIMIT :limit OFFSET :offset
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(data_sql, params).fetchall()
        records = [dict(row._mapping) for row in rows]
        total = int(records[0].pop("full_count", 0) if records else 0)
        return records, total

    def list_funds(
        self,
        fund_type: Optional[str] = None,
        keyword: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
        asset_min: Optional[float] = None,
        asset_max: Optional[float] = None,
        established_from: Optional[str] = None,
        established_to: Optional[str] = None,
        evidence_status: Optional[str] = None,
        has_manager: Optional[bool] = None,
        min_manager_years: Optional[float] = None,
        has_fee: Optional[bool] = None,
        fee_max: Optional[float] = None,
        tradable_only: Optional[bool] = None,
        return_1y_min: Optional[float] = None,
        return_1y_max: Optional[float] = None,
        return_3y_min: Optional[float] = None,
        return_3y_max: Optional[float] = None,
        max_drawdown_1y_max: Optional[float] = None,
        volatility_1y_max: Optional[float] = None,
        sharpe_1y_min: Optional[float] = None,
        screening_score_min: Optional[float] = None,
        screening_score_max: Optional[float] = None,
        evidence_coverage_min: Optional[float] = None,
        research_checklist_status: Optional[str] = None,
        research_checklist_gap: Optional[str] = None,
        sales_rule_complete: Optional[bool] = None,
        purchase_plan: str = "sip",
        planned_amount: Optional[float] = None,
        max_sales_risk_level: Optional[int] = None,
        sales_risk_filter: Optional[str] = None,
        has_nav: Optional[bool] = None,
        has_performance: Optional[bool] = None,
        has_holdings: Optional[bool] = None,
        sort_by: str = "updated_at",
        sort_order: str = "desc",
    ) -> Dict[str, Any]:
        """列表查询基金"""
        try:
            from sqlalchemy import text

            where_clauses = []
            params = {}
            safe_purchase_plan = "lump_sum" if purchase_plan == "lump_sum" else "sip"
            try:
                planned_amount_value = float(planned_amount) if planned_amount is not None else None
            except (TypeError, ValueError):
                planned_amount_value = None
            safe_planned_amount = planned_amount_value if planned_amount_value is not None and planned_amount_value > 0 else None
            params["planned_amount"] = safe_planned_amount

            if fund_type:
                where_clauses.append("type = :fund_type")
                params["fund_type"] = fund_type

            if keyword:
                where_clauses.append("(name ILIKE :keyword OR wind_code ILIKE :keyword)")
                params["keyword"] = f"%{keyword}%"

            if asset_min is not None:
                where_clauses.append("COALESCE(total_asset, 0) >= :asset_min")
                params["asset_min"] = asset_min

            if asset_max is not None:
                where_clauses.append("COALESCE(total_asset, 0) <= :asset_max")
                params["asset_max"] = asset_max

            if established_from:
                where_clauses.append("establishment_date >= :established_from")
                params["established_from"] = established_from

            if established_to:
                where_clauses.append("establishment_date <= :established_to")
                params["established_to"] = established_to

            blocked_clause = f"NOT ({active_fund_sql()})"

            # 普通基金浏览和筛选默认只展示真实存续基金。
            where_clauses.append(active_fund_sql())
            purchase_start_expr = "NULLIF(COALESCE(raw_data#>>'{info,purchase_start_date}', raw_data#>>'{universe,purchase_start_date}'), '')"
            future_purchase_clause = f"""
                COALESCE((
                    {purchase_start_expr} ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$'
                    AND {purchase_start_expr}::date > CURRENT_DATE
                ), false)
            """
            manager_clause = "COALESCE(cardinality(manager_ids), 0) > 0"
            fee_clause = """
                (
                    NULLIF(raw_data#>>'{info,management_fee}', '') IS NOT NULL
                    OR NULLIF(raw_data#>>'{info,custodian_fee}', '') IS NOT NULL
                )
            """
            numeric_fee_clause = """
                (
                    NULLIF(raw_data#>>'{info,management_fee}', '') ~ '^[0-9]+(\\.[0-9]+)?$'
                    AND NULLIF(raw_data#>>'{info,custodian_fee}', '') ~ '^[0-9]+(\\.[0-9]+)?$'
                )
            """
            total_fee_expr = """
                (
                    NULLIF(raw_data#>>'{info,management_fee}', '')::numeric
                    + NULLIF(raw_data#>>'{info,custodian_fee}', '')::numeric
                )
            """
            nav_clause = "nav IS NOT NULL AND nav_date IS NOT NULL"
            numeric_pattern = "'^-?[0-9]+(\\.[0-9]+)?$'"
            return_1y_raw = "NULLIF(performance_data->>'annualized_return_1y', '')"
            return_3y_raw = "NULLIF(performance_data->>'annualized_return_3y', '')"
            sharpe_1y_raw = "NULLIF(performance_data->>'sharpe_ratio', '')"
            volatility_1y_raw = "NULLIF(COALESCE(risk_metrics->>'annualized_volatility_1y', risk_metrics->>'volatility_1y', performance_data->>'volatility'), '')"
            drawdown_1y_raw = "NULLIF(risk_metrics->>'max_drawdown_1y', '')"
            drawdown_raw = "NULLIF(risk_metrics->>'max_drawdown', '')"
            performance_drawdown_raw = "NULLIF(performance_data->>'max_drawdown', '')"
            return_1y_clause = f"{return_1y_raw} ~ {numeric_pattern}"
            return_3y_clause = f"{return_3y_raw} ~ {numeric_pattern}"
            sharpe_1y_clause = f"{sharpe_1y_raw} ~ {numeric_pattern}"
            volatility_1y_clause = f"{volatility_1y_raw} ~ {numeric_pattern}"
            drawdown_available_clause = f"({drawdown_1y_raw} ~ {numeric_pattern} OR {drawdown_raw} ~ {numeric_pattern} OR {performance_drawdown_raw} ~ {numeric_pattern})"
            drawdown_expr = f"""
                ABS(COALESCE(
                    CASE WHEN {drawdown_1y_raw} ~ {numeric_pattern} THEN {drawdown_1y_raw}::numeric END,
                    CASE WHEN {drawdown_raw} ~ {numeric_pattern} THEN {drawdown_raw}::numeric END,
                    CASE WHEN {performance_drawdown_raw} ~ {numeric_pattern} THEN {performance_drawdown_raw}::numeric END
                ))
            """
            performance_clause = """
                (
                    performance_data IS NOT NULL
                    AND performance_data <> '{}'::jsonb
                    AND (
                        NULLIF(performance_data->>'annualized_return_1y', '') IS NOT NULL
                        OR NULLIF(performance_data->>'sharpe_ratio', '') IS NOT NULL
                    )
                )
            """
            holdings_clause = "false"
            holding_count_expr = "0"
            with self.engine.connect() as conn:
                has_holdings_table = _table_exists(conn, "holdings")
                holdings_has_wind_code = has_holdings_table and _column_exists(conn, "holdings", "wind_code")
                holdings_has_fund_id = has_holdings_table and _column_exists(conn, "holdings", "fund_id")

            holding_predicates = []
            if holdings_has_wind_code:
                holding_predicates.append("h.wind_code = funds.wind_code")
            if holdings_has_fund_id:
                holding_predicates.append("h.fund_id = funds.id::text")

            if has_holdings_table and holding_predicates:
                holding_count_expr = f"""
                    (
                        SELECT COUNT(*)
                        FROM holdings h
                        WHERE ({' OR '.join(holding_predicates)})
                          AND NULLIF(h.quarter, '') IS NOT NULL
                          AND NULLIF(h.stock_code, '') IS NOT NULL
                          AND h.weight IS NOT NULL
                          AND h.weight > 0
                    )
                """
                holdings_clause = f"({holding_count_expr}) >= 5"
            sales_risk_level_expr = "NULLIF(UPPER(fsr.risk_level), '')"
            source_identity_clause = """
                (
                    (
                        NULLIF(fsr.source_url, '') IS NOT NULL
                        AND LOWER(TRIM(fsr.source_url)) NOT IN (
                            '-', '--', 'na', 'n/a', 'none', 'null', 'unknown', 'tbd', 'todo',
                            'placeholder', 'sample', 'example', 'demo', 'mock', 'test',
                            '待补', '待核', '待确认', '暂无', '无', '示例', '样例', '测试',
                            '占位', '来源待补', '待补来源', '链接待补', '待补链接',
                            '示例链接', '样例链接', '测试链接', '占位链接'
                        )
                        AND LOWER(TRIM(fsr.source_url)) NOT LIKE 'https://example.%'
                        AND LOWER(TRIM(fsr.source_url)) NOT LIKE 'http://example.%'
                    )
                    OR (
                        NULLIF(fsr.notes, '') IS NOT NULL
                        AND LOWER(TRIM(fsr.notes)) NOT IN (
                            '-', '--', 'na', 'n/a', 'none', 'null', 'unknown', 'tbd', 'todo',
                            'placeholder', 'sample', 'example', 'demo', 'mock', 'test',
                            '待补', '待核', '待确认', '暂无', '无', '示例', '样例', '测试',
                            '占位', '来源待补', '待补来源', '备注待补', '待补备注'
                        )
                    )
                )
            """
            source_backed_sales_risk_clause = f"""
                (
                    {sales_risk_level_expr} ~ '^R[1-5]$'
                    AND COALESCE(fsr.source_updated_at::text, '') <> ''
                    AND fsr.source_updated_at >= CURRENT_DATE - INTERVAL '30 days'
                    AND fsr.source_updated_at <= CURRENT_DATE
                    AND COALESCE(LOWER(fsr.platform), '') NOT LIKE '%tushare%'
                    AND COALESCE(LOWER(fsr.source_url), '') NOT LIKE '%tushare.fund_basic%'
                    AND {source_identity_clause}
                )
            """
            source_backed_redemption_clause = f"""
                (
                    jsonb_array_length(COALESCE(fsr.redemption_fee_rules, '[]'::jsonb)) > 0
                    AND COALESCE(fsr.source_updated_at::text, '') <> ''
                    AND fsr.source_updated_at >= CURRENT_DATE - INTERVAL '30 days'
                    AND fsr.source_updated_at <= CURRENT_DATE
                    AND COALESCE(LOWER(fsr.platform), '') NOT LIKE '%tushare%'
                    AND COALESCE(LOWER(fsr.source_url), '') NOT LIKE '%tushare.fund_basic%'
                    AND {source_identity_clause}
                )
            """
            source_backed_sales_rule_clause = f"""
                (
                    COALESCE(fsr.source_updated_at::text, '') <> ''
                    AND fsr.source_updated_at >= CURRENT_DATE - INTERVAL '30 days'
                    AND fsr.source_updated_at <= CURRENT_DATE
                    AND COALESCE(LOWER(fsr.platform), '') NOT LIKE '%tushare%'
                    AND COALESCE(LOWER(fsr.source_url), '') NOT LIKE '%tushare.fund_basic%'
                    AND {source_identity_clause}
                )
            """
            sip_complete_requirements = f"""
                        AND BOOL_OR(fsr.supports_sip IS TRUE AND {source_backed_sales_rule_clause})
                        AND BOOL_OR(
                            fsr.min_sip_amount IS NOT NULL
                            AND {source_backed_sales_rule_clause}
                            AND (:planned_amount IS NULL OR fsr.min_sip_amount <= :planned_amount)
                        )
            """ if safe_purchase_plan == "sip" else ""
            sales_rule_complete_clause = f"""
                EXISTS (
                    SELECT 1
                    FROM fund_sales_rules fsr
                    WHERE fsr.wind_code = funds.wind_code
                    GROUP BY fsr.wind_code
                    HAVING
                        BOOL_OR(COALESCE(fsr.purchase_status, 'unknown') <> 'unknown' AND {source_backed_sales_rule_clause})
                        AND BOOL_OR(fsr.purchase_fee_rate IS NOT NULL AND {source_backed_sales_rule_clause})
                        AND BOOL_OR({source_backed_redemption_clause})
                        AND BOOL_OR(
                            fsr.min_purchase_amount IS NOT NULL
                            AND {source_backed_sales_rule_clause}
                            AND (:planned_amount IS NULL OR fsr.min_purchase_amount <= :planned_amount)
                        )
                        {sip_complete_requirements}
                        AND BOOL_OR(
                            fsr.daily_limit_amount IS NOT NULL
                            AND {source_backed_sales_rule_clause}
                            AND (
                                :planned_amount IS NULL
                                OR fsr.daily_limit_amount <= 0
                                OR fsr.daily_limit_amount >= :planned_amount
                            )
                        )
                        AND BOOL_OR(fsr.sales_service_fee_rate IS NOT NULL AND {source_backed_sales_rule_clause})
                        AND BOOL_OR({source_backed_sales_risk_clause})
                )
            """
            sales_risk_known_clause = f"""
                EXISTS (
                    SELECT 1
                    FROM fund_sales_rules fsr
                    WHERE fsr.wind_code = funds.wind_code
                      AND {source_backed_sales_risk_clause}
                )
            """
            sales_risk_unknown_clause = f"NOT ({sales_risk_known_clause})"
            sales_risk_matched_clause = f"""
                EXISTS (
                    SELECT 1
                    FROM fund_sales_rules fsr
                    WHERE fsr.wind_code = funds.wind_code
                      AND {source_backed_sales_risk_clause}
                      AND SUBSTRING({sales_risk_level_expr} FROM 2)::int <= :max_sales_risk_level
                )
            """
            sales_risk_mismatch_clause = f"""
                EXISTS (
                    SELECT 1
                    FROM fund_sales_rules fsr
                    WHERE fsr.wind_code = funds.wind_code
                      AND {source_backed_sales_risk_clause}
                      AND SUBSTRING({sales_risk_level_expr} FROM 2)::int > :max_sales_risk_level
                )
            """
            evidence_gap_count_expr = f"""
                (
                    CASE WHEN NOT ({nav_clause}) THEN 1 ELSE 0 END
                    + CASE WHEN total_asset IS NULL THEN 1 ELSE 0 END
                    + CASE
                        WHEN COALESCE(cardinality(manager_ids), 0) = 0 THEN 1
                        WHEN NOT EXISTS (
                            SELECT 1 FROM managers m
                            WHERE m.wind_code = ANY(funds.manager_ids)
                              AND COALESCE(m.management_years, 0) >= 1
                        ) THEN 1
                        ELSE 0
                      END
                    + CASE WHEN {purchase_start_expr} IS NULL THEN 1 ELSE 0 END
                    + CASE WHEN NOT ({fee_clause}) THEN 1 ELSE 0 END
                )
            """
            return_score_expr = f"""
                CASE
                    WHEN {return_1y_clause} THEN GREATEST(0, LEAST(30, ({return_1y_raw}::numeric / 0.5) * 30))
                    ELSE 0
                END
            """
            drawdown_score_expr = f"""
                CASE
                    WHEN NOT {drawdown_available_clause} THEN 0
                    WHEN {drawdown_expr} <= 0.05 THEN 20
                    WHEN {drawdown_expr} <= 0.15 THEN 16
                    WHEN {drawdown_expr} <= 0.25 THEN 10
                    WHEN {drawdown_expr} <= 0.35 THEN 5
                    ELSE 0
                END
            """
            sharpe_score_expr = f"""
                CASE
                    WHEN NOT {sharpe_1y_clause} THEN 0
                    WHEN {sharpe_1y_raw}::numeric >= 0.8 THEN 20
                    WHEN {sharpe_1y_raw}::numeric >= 0.5 THEN 15
                    WHEN {sharpe_1y_raw}::numeric >= 0.3 THEN 10
                    WHEN {sharpe_1y_raw}::numeric > 0 THEN 5
                    ELSE 0
                END
            """
            evidence_score_expr = f"GREATEST(0, 20 - ({evidence_gap_count_expr}) * 3)"
            fee_score_expr = f"""
                CASE
                    WHEN NOT ({numeric_fee_clause}) THEN 0
                    WHEN {total_fee_expr} <= 1.2 THEN 10
                    WHEN {total_fee_expr} <= 1.8 THEN 6
                    ELSE 3
                END
            """
            screening_score_expr = f"""
                CASE
                    WHEN {blocked_clause} THEN 0
                    ELSE ROUND(({return_score_expr}) + ({drawdown_score_expr}) + ({sharpe_score_expr}) + ({evidence_score_expr}) + ({fee_score_expr}))
                END
            """
            evidence_coverage_score_expr = f"""
                (
                    CASE WHEN {nav_clause} THEN 10 ELSE 0 END
                    + CASE WHEN {performance_clause} THEN 15 ELSE 0 END
                    + CASE WHEN ({drawdown_available_clause} OR {volatility_1y_clause}) THEN 15 ELSE 0 END
                    + CASE WHEN {manager_clause} THEN 10 ELSE 0 END
                    + CASE WHEN {numeric_fee_clause} THEN 10 ELSE 0 END
                    + CASE WHEN {holdings_clause} THEN 10 ELSE 0 END
                    + CASE WHEN ({sales_rule_complete_clause}) THEN 20 ELSE 0 END
                    + CASE WHEN ({sales_risk_known_clause}) THEN 10 ELSE 0 END
                )
            """
            research_identity_check_clause = f"({nav_clause} AND total_asset IS NOT NULL AND NULLIF(type, '') IS NOT NULL)"
            research_risk_check_clause = f"({drawdown_available_clause} OR {volatility_1y_clause})"
            research_sales_rule_check_clause = f"(({sales_rule_complete_clause}) AND ({sales_risk_known_clause}))"
            research_checklist_pass_count_expr = f"""
                (
                    CASE WHEN {research_identity_check_clause} THEN 1 ELSE 0 END
                    + CASE WHEN {performance_clause} THEN 1 ELSE 0 END
                    + CASE WHEN {research_risk_check_clause} THEN 1 ELSE 0 END
                    + CASE WHEN {manager_clause} THEN 1 ELSE 0 END
                    + CASE WHEN {holdings_clause} THEN 1 ELSE 0 END
                    + CASE WHEN {research_sales_rule_check_clause} THEN 1 ELSE 0 END
                )
            """
            research_checklist_status_expr = f"""
                CASE
                    WHEN ({blocked_clause}) OR ({future_purchase_clause}) THEN 'blocked'
                    WHEN ({research_checklist_pass_count_expr}) >= 6 THEN 'complete'
                    ELSE 'repair'
                END
            """
            research_checklist_primary_gap_expr = f"""
                CASE
                    WHEN ({blocked_clause}) OR ({future_purchase_clause}) THEN '存续/申购状态阻断'
                    WHEN NOT ({research_identity_check_clause}) THEN '基础数据'
                    WHEN NOT ({performance_clause}) THEN '绩效指标'
                    WHEN NOT ({research_risk_check_clause}) THEN '风险指标'
                    WHEN NOT ({manager_clause}) THEN '经理证据'
                    WHEN NOT ({holdings_clause}) THEN '持仓明细'
                    WHEN NOT ({research_sales_rule_check_clause}) THEN '销售规则/R1-R5'
                    ELSE ''
                END
            """

            if evidence_status == "blocked":
                where_clauses.append(blocked_clause)
            elif evidence_status == "ready":
                where_clauses.extend([
                    f"NOT {blocked_clause}",
                    nav_clause,
                    "total_asset IS NOT NULL",
                    manager_clause,
                    fee_clause,
                    performance_clause,
                ])
            elif evidence_status == "verify":
                ready_clause = f"({nav_clause} AND total_asset IS NOT NULL AND {manager_clause} AND {fee_clause} AND {performance_clause})"
                where_clauses.append(f"NOT {blocked_clause}")
                where_clauses.append(f"NOT {ready_clause}")

            if has_manager is not None:
                where_clauses.append(manager_clause if has_manager else f"NOT {manager_clause}")

            if min_manager_years is not None:
                where_clauses.append("""
                    EXISTS (
                        SELECT 1
                        FROM managers m
                        WHERE m.wind_code = ANY(funds.manager_ids)
                          AND COALESCE(m.management_years, 0) >= :min_manager_years
                    )
                """)
                params["min_manager_years"] = min_manager_years

            if has_fee is not None:
                where_clauses.append(fee_clause if has_fee else f"NOT {fee_clause}")

            if fee_max is not None:
                where_clauses.append(numeric_fee_clause)
                where_clauses.append(f"{total_fee_expr} <= :fee_max")
                params["fee_max"] = fee_max

            if tradable_only:
                where_clauses.append(f"NOT {blocked_clause}")
                where_clauses.append(f"NOT {future_purchase_clause}")

            if return_1y_min is not None:
                where_clauses.append(return_1y_clause)
                where_clauses.append(f"{return_1y_raw}::numeric >= :return_1y_min")
                params["return_1y_min"] = return_1y_min

            if return_1y_max is not None:
                where_clauses.append(return_1y_clause)
                where_clauses.append(f"{return_1y_raw}::numeric <= :return_1y_max")
                params["return_1y_max"] = return_1y_max

            if return_3y_min is not None:
                where_clauses.append(return_3y_clause)
                where_clauses.append(f"{return_3y_raw}::numeric >= :return_3y_min")
                params["return_3y_min"] = return_3y_min

            if return_3y_max is not None:
                where_clauses.append(return_3y_clause)
                where_clauses.append(f"{return_3y_raw}::numeric <= :return_3y_max")
                params["return_3y_max"] = return_3y_max

            if max_drawdown_1y_max is not None:
                where_clauses.append(drawdown_available_clause)
                where_clauses.append(f"{drawdown_expr} <= :max_drawdown_1y_max")
                params["max_drawdown_1y_max"] = max_drawdown_1y_max

            if volatility_1y_max is not None:
                where_clauses.append(volatility_1y_clause)
                where_clauses.append(f"{volatility_1y_raw}::numeric <= :volatility_1y_max")
                params["volatility_1y_max"] = volatility_1y_max

            if sharpe_1y_min is not None:
                where_clauses.append(sharpe_1y_clause)
                where_clauses.append(f"{sharpe_1y_raw}::numeric >= :sharpe_1y_min")
                params["sharpe_1y_min"] = sharpe_1y_min

            if screening_score_min is not None:
                where_clauses.append(f"({screening_score_expr}) >= :screening_score_min")
                params["screening_score_min"] = screening_score_min

            if screening_score_max is not None:
                where_clauses.append(f"({screening_score_expr}) <= :screening_score_max")
                params["screening_score_max"] = screening_score_max

            if evidence_coverage_min is not None:
                where_clauses.append(f"({evidence_coverage_score_expr}) >= :evidence_coverage_min")
                params["evidence_coverage_min"] = evidence_coverage_min

            normalized_research_checklist_status = research_checklist_status if research_checklist_status in ("complete", "repair", "blocked") else None
            if normalized_research_checklist_status is not None:
                where_clauses.append(f"({research_checklist_status_expr}) = :research_checklist_status")
                params["research_checklist_status"] = normalized_research_checklist_status

            normalized_research_checklist_gap = research_checklist_gap.strip() if research_checklist_gap else None
            if normalized_research_checklist_gap:
                where_clauses.append(f"({research_checklist_primary_gap_expr}) = :research_checklist_gap")
                params["research_checklist_gap"] = normalized_research_checklist_gap

            if sales_rule_complete is not None:
                where_clauses.append(sales_rule_complete_clause if sales_rule_complete else f"NOT ({sales_rule_complete_clause})")

            normalized_sales_risk_filter = sales_risk_filter if sales_risk_filter in ("matched", "mismatch", "missing", "known") else None
            if max_sales_risk_level is not None and normalized_sales_risk_filter in ("matched", "mismatch"):
                params["max_sales_risk_level"] = max_sales_risk_level
                where_clauses.append(sales_risk_matched_clause if normalized_sales_risk_filter == "matched" else sales_risk_mismatch_clause)
            elif normalized_sales_risk_filter == "missing":
                where_clauses.append(sales_risk_unknown_clause)
            elif normalized_sales_risk_filter == "known":
                where_clauses.append(sales_risk_known_clause)

            if has_nav is not None:
                where_clauses.append(nav_clause if has_nav else f"NOT ({nav_clause})")

            if has_performance is not None:
                where_clauses.append(performance_clause if has_performance else f"NOT {performance_clause}")

            if has_holdings is not None:
                where_clauses.append(holdings_clause if has_holdings else f"NOT ({holdings_clause})")

            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
            offset = (page - 1) * page_size

            sort_map = {
                "updated_at": "updated_at",
                "name": "name",
                "wind_code": "wind_code",
                "nav": "nav",
                "total_asset": "total_asset",
                "establishment_date": "establishment_date",
                "return": "NULLIF(performance_data->>'annualized_return_1y', '')::numeric",
                "risk": "ABS(COALESCE(NULLIF(risk_metrics->>'max_drawdown_1y', '')::numeric, NULLIF(risk_metrics->>'max_drawdown', '')::numeric, NULLIF(performance_data->>'max_drawdown', '')::numeric))",
                "sharpe": "NULLIF(performance_data->>'sharpe_ratio', '')::numeric",
                "fee": f"CASE WHEN {numeric_fee_clause} THEN {total_fee_expr} ELSE NULL END",
                "screening_score": screening_score_expr,
                "evidence_coverage": evidence_coverage_score_expr,
                "research_checklist": research_checklist_pass_count_expr,
            }
            order_column = sort_map.get(sort_by, "updated_at")
            order_direction = "ASC" if str(sort_order).lower() == "asc" else "DESC"

            count_sql = f"SELECT COUNT(*) as total FROM funds WHERE {where_sql}"
            research_checklist_aggregate_sql = f"""
                SELECT
                    checklist_status,
                    NULLIF(checklist_primary_gap, '') AS checklist_primary_gap,
                    COUNT(*)::int AS count
                FROM (
                    SELECT
                        ({research_checklist_status_expr}) AS checklist_status,
                        ({research_checklist_primary_gap_expr}) AS checklist_primary_gap
                    FROM funds
                    WHERE {where_sql}
                ) checklist_universe
                GROUP BY checklist_status, NULLIF(checklist_primary_gap, '')
                ORDER BY count DESC
            """
            data_sql = f"""
                SELECT funds.*,
                       ({screening_score_expr})::int AS screening_score,
                       ({evidence_coverage_score_expr})::int AS evidence_coverage_score,
                       ({holding_count_expr})::int AS holding_count,
                       ({research_checklist_pass_count_expr})::int AS research_checklist_pass_count,
                       6::int AS research_checklist_total_count,
                       ({research_checklist_status_expr}) AS research_checklist_status,
                       ({research_checklist_primary_gap_expr}) AS research_checklist_primary_gap
                FROM funds
                WHERE {where_sql}
                ORDER BY {order_column} {order_direction} NULLS LAST
                LIMIT :limit OFFSET :offset
            """

            with self.engine.connect() as conn:
                count_result = conn.execute(text(count_sql), params)
                total = count_result.fetchone()[0]
                aggregate_result = conn.execute(text(research_checklist_aggregate_sql), params)
                aggregate_rows = aggregate_result.fetchall()

                params["limit"] = page_size
                params["offset"] = offset
                data_result = conn.execute(text(data_sql), params)
                rows = data_result.fetchall()

            status_buckets: Dict[str, int] = {}
            primary_gap_buckets: Dict[str, int] = {}
            for row in aggregate_rows:
                row_map = row._mapping
                status = row_map.get("checklist_status") or "unknown"
                count = int(row_map.get("count") or 0)
                status_buckets[status] = status_buckets.get(status, 0) + count
                primary_gap = row_map.get("checklist_primary_gap")
                if primary_gap:
                    primary_gap_buckets[primary_gap] = primary_gap_buckets.get(primary_gap, 0) + count

            return {
                "total": total,
                "funds": [dict(r._mapping) for r in rows],
                "summary": {
                    "market_research_checklist": {
                        "status_buckets": status_buckets,
                        "primary_gap_buckets": dict(sorted(primary_gap_buckets.items(), key=lambda item: item[1], reverse=True)[:8]),
                        "source": "local.postgres.full_market_research_checklist.aggregate",
                    }
                },
            }
        except Exception as e:
            logger.error(f"list_funds error: {e}")
            raise

    def upsert_scores(self, wind_code: str, scores: List[Dict[str, Any]]) -> bool:
        """Upsert 评分记录"""
        try:
            from sqlalchemy import text

            with self.engine.connect() as conn:
                for score in scores:
                    sql = """
                    INSERT INTO scores (target_type, target_id, dimension, score, weight,
                                       calculation_method, details)
                    VALUES ('fund', :target_id, :dimension, :score, :weight, :method, :details)
                    """
                    conn.execute(text(sql), {
                        "target_id": wind_code,
                        "dimension": score.get("dimension", ""),
                        "score": score.get("score", 0),
                        "weight": score.get("weight", 1),
                        "method": score.get("method", ""),
                        "details": score.get("details", {}),
                    })
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"upsert_scores error: {e}")
            return False

    def get_scores(self, wind_code: str) -> List[Dict[str, Any]]:
        """获取基金评分历史"""
        try:
            from sqlalchemy import text
            sql = """
                SELECT * FROM scores
                WHERE target_type = 'fund' AND target_id = :wind_code
                ORDER BY scored_at DESC
                LIMIT 100
            """
            with self.engine.connect() as conn:
                result = conn.execute(text(sql), {"wind_code": wind_code})
                return [dict(r._mapping) for r in result.fetchall()]
        except Exception as e:
            logger.error(f"get_scores error: {e}")
            return []

    def get_ai_reports(self, fund_id: str, wind_code: str, limit: int = 10) -> List[Dict[str, Any]]:
        """获取基金 AI 分析报告摘要"""
        try:
            from sqlalchemy import text
            sql = """
                SELECT id, target_type, target_id, report_type, content, data_sources,
                       research_reports_used, generation_params, created_at
                FROM ai_analysis_reports
                WHERE target_type = 'fund'
                  AND (target_id = :fund_id OR target_id = :wind_code)
                ORDER BY created_at DESC
                LIMIT :limit
            """
            with self.engine.connect() as conn:
                result = conn.execute(text(sql), {
                    "fund_id": str(fund_id),
                    "wind_code": wind_code,
                    "limit": limit,
                })
                return [dict(r._mapping) for r in result.fetchall()]
        except Exception as e:
            logger.error(f"get_ai_reports error: {e}")
            return []

    def delete_fund(self, wind_code: str) -> bool:
        """删除基金（软删除或硬删除）"""
        try:
            from sqlalchemy import text
            sql = "DELETE FROM funds WHERE wind_code = :wind_code"
            with self.engine.connect() as conn:
                conn.execute(text(sql), {"wind_code": wind_code})
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"delete_fund error: {e}")
            return False
