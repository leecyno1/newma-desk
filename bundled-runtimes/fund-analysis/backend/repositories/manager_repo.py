"""
基金经理 Repository - PostgreSQL 数据访问层
"""
import os
import json
import math
import numbers
from datetime import date, datetime
from decimal import Decimal
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


def _json_ser(obj):
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if hasattr(obj, "tolist"):
        return _clean_json_value(obj.tolist())
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _clean_json_value(obj):
    """递归清理 Tushare/Pandas 数据中的 NaN 和 Infinity。"""
    if isinstance(obj, dict):
        return {str(key): _clean_json_value(value) for key, value in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_clean_json_value(item) for item in obj]
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, numbers.Real) and not isinstance(obj, bool):
        value = float(obj)
        if math.isnan(value) or math.isinf(value):
            return None
        if isinstance(obj, numbers.Integral):
            return int(obj)
        return value
    return obj


class ManagerRepo:
    """基金经理数据访问层"""

    def __init__(self):
        self._engine = None

    @property
    def engine(self):
        if self._engine is None:
            self._engine = _get_engine()
        return self._engine

    def upsert_manager(self, manager_id: str, data: Dict[str, Any]) -> bool:
        """Upsert 基金经理数据"""
        try:
            from sqlalchemy import text

            sql = """
            INSERT INTO managers (wind_code, name, company, education, work_years,
                               management_years, current_funds, historical_performance, raw_data, updated_at)
            VALUES (:manager_id, :name, :company, :education, :work_years,
                    :mgmt_years, :current_funds, CAST(:hist_perf AS jsonb), CAST(:raw_data AS jsonb), NOW())
            ON CONFLICT (wind_code) DO UPDATE SET
                name = EXCLUDED.name,
                company = CASE
                    WHEN NULLIF(EXCLUDED.company, '') IS NULL THEN managers.company
                    ELSE EXCLUDED.company
                END,
                education = EXCLUDED.education,
                work_years = EXCLUDED.work_years,
                management_years = EXCLUDED.management_years,
                current_funds = CASE
                    WHEN COALESCE(cardinality(EXCLUDED.current_funds), 0) = 0 THEN managers.current_funds
                    ELSE ARRAY(
                        SELECT DISTINCT fund_code
                        FROM unnest(COALESCE(managers.current_funds, '{}'::text[]) || EXCLUDED.current_funds) AS fund_code
                    )
                END,
                historical_performance = EXCLUDED.historical_performance,
                raw_data = EXCLUDED.raw_data,
                updated_at = NOW()
            """
            params = {
                "manager_id": manager_id,
                "name": data.get("name", ""),
                "company": data.get("company", ""),
                "education": data.get("education", ""),
                "work_years": data.get("experience_years", 0),
                "mgmt_years": data.get("management_years", 0),
                "current_funds": data.get("current_funds", []),
                "hist_perf": json.dumps(
                    _clean_json_value(data.get("historical_performance", {})),
                    default=_json_ser,
                    ensure_ascii=False,
                    allow_nan=False,
                ),
                "raw_data": json.dumps(
                    _clean_json_value(data.get("raw_data", {})),
                    default=_json_ser,
                    ensure_ascii=False,
                    allow_nan=False,
                ),
            }

            with self.engine.connect() as conn:
                conn.execute(text(sql), params)
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"upsert_manager error for {manager_id}: {e}")
            return False

    def upsert_manager_universe(self, records: List[Dict[str, Any]]) -> Dict[str, int]:
        """批量写入权威基金经理目录和完整任职关系。"""
        if not records:
            return {"manager_count": 0, "tenure_count": 0}

        from sqlalchemy import text

        manager_rows = []
        tenure_rows = []
        manager_ids = []
        for record in records:
            manager_id = str(record.get("manager_id") or "").strip()
            if not manager_id:
                continue
            manager_ids.append(manager_id)
            manager_rows.append({
                "manager_id": manager_id,
                "name": str(record.get("name") or manager_id.split("|")[0]).strip(),
                "company": str(record.get("company") or "").strip(),
                "education": str(record.get("education") or "").strip(),
                "work_years": record.get("work_years"),
                "management_years": record.get("management_years"),
                "current_funds": list(dict.fromkeys(record.get("current_funds") or [])),
                "historical_performance": json.dumps(
                    _clean_json_value(record.get("historical_performance") or {}),
                    default=_json_ser,
                    ensure_ascii=False,
                    allow_nan=False,
                ),
                "raw_data": json.dumps(
                    _clean_json_value(record.get("raw_data") or {}),
                    default=_json_ser,
                    ensure_ascii=False,
                    allow_nan=False,
                ),
            })
            for tenure in record.get("tenures") or []:
                fund_code = str(tenure.get("fund_code") or "").strip().upper()
                start_date = str(tenure.get("start_date") or "")[:10]
                if not fund_code or not start_date:
                    continue
                tenure_rows.append({
                    "manager_id": manager_id,
                    "fund_code": fund_code,
                    "fund_name": tenure.get("fund_name"),
                    "start_date": start_date,
                    "end_date": str(tenure.get("end_date") or "")[:10] or None,
                    "is_current": bool(tenure.get("is_current")),
                    "raw_data": json.dumps(
                        _clean_json_value(tenure.get("raw_data") or {}),
                        default=_json_ser,
                        ensure_ascii=False,
                        allow_nan=False,
                    ),
                })

        if not manager_rows:
            return {"manager_count": 0, "tenure_count": 0}

        manager_sql = text("""
            INSERT INTO managers (
                wind_code, name, company, education, work_years, management_years,
                current_funds, historical_performance, raw_data, updated_at
            ) VALUES (
                :manager_id, :name, :company, :education, :work_years, :management_years,
                :current_funds, CAST(:historical_performance AS JSONB), CAST(:raw_data AS JSONB), NOW()
            )
            ON CONFLICT (wind_code) DO UPDATE SET
                name = EXCLUDED.name,
                company = CASE WHEN EXCLUDED.company = '' THEN managers.company ELSE EXCLUDED.company END,
                education = CASE WHEN EXCLUDED.education = '' THEN managers.education ELSE EXCLUDED.education END,
                work_years = EXCLUDED.work_years,
                management_years = EXCLUDED.management_years,
                current_funds = EXCLUDED.current_funds,
                historical_performance = EXCLUDED.historical_performance,
                raw_data = COALESCE(managers.raw_data, '{}'::JSONB) || EXCLUDED.raw_data,
                updated_at = NOW()
        """)
        tenure_sql = text("""
            INSERT INTO manager_fund_tenures (
                manager_id, fund_code, fund_name, start_date, end_date,
                is_current, source, raw_data, updated_at
            ) VALUES (
                :manager_id, :fund_code, :fund_name, :start_date, :end_date,
                :is_current, 'tushare.fund_manager', CAST(:raw_data AS JSONB), NOW()
            )
            ON CONFLICT (manager_id, fund_code, start_date) DO UPDATE SET
                fund_name = EXCLUDED.fund_name,
                end_date = EXCLUDED.end_date,
                is_current = EXCLUDED.is_current,
                source = EXCLUDED.source,
                raw_data = EXCLUDED.raw_data,
                updated_at = NOW()
        """)

        unique_manager_ids = list(dict.fromkeys(manager_ids))
        with self.engine.begin() as conn:
            conn.execute(manager_sql, manager_rows)
            conn.execute(text("""
                UPDATE manager_fund_tenures
                SET is_current = FALSE, updated_at = NOW()
                WHERE manager_id = ANY(:manager_ids)
                  AND source = 'tushare.fund_manager'
            """), {"manager_ids": unique_manager_ids})
            if tenure_rows:
                conn.execute(tenure_sql, tenure_rows)

        return {
            "manager_count": len(manager_rows),
            "tenure_count": len(tenure_rows),
        }

    def get_manager(self, manager_id: str) -> Optional[Dict[str, Any]]:
        """获取基金经理"""
        try:
            from sqlalchemy import text
            sql = "SELECT * FROM managers WHERE wind_code = :manager_id OR name = :manager_id LIMIT 1"
            with self.engine.connect() as conn:
                result = conn.execute(text(sql), {"manager_id": manager_id})
                row = result.fetchone()
                if row:
                    return dict(row._mapping)
                return None
        except Exception as e:
            logger.error(f"get_manager error: {e}")
            return None

    def get_managers_by_ids(self, manager_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """按 manager_id 批量获取经理。"""
        if not manager_ids:
            return {}
        try:
            from sqlalchemy import bindparam, text

            unique_ids = list(dict.fromkeys([manager_id for manager_id in manager_ids if manager_id]))
            if not unique_ids:
                return {}
            sql = text("SELECT * FROM managers WHERE wind_code IN :manager_ids OR name IN :manager_ids")
            sql = sql.bindparams(bindparam("manager_ids", expanding=True))
            with self.engine.connect() as conn:
                rows = conn.execute(sql, {"manager_ids": unique_ids}).fetchall()
            return {
                row._mapping.get("wind_code"): dict(row._mapping)
                for row in rows
                if row._mapping.get("wind_code")
            }
        except Exception as e:
            logger.error(f"get_managers_by_ids error: {e}")
            return {}

    def replace_fund_tenures(self, manager_id: str, tenures: List[Dict[str, Any]]) -> bool:
        """用权威 fund_manager 结果替换一个经理的完整任职关系。"""
        try:
            from sqlalchemy import text

            cleaned = []
            for tenure in tenures:
                fund_code = str(tenure.get("fund_code") or "").strip().upper()
                start_date = str(tenure.get("start_date") or "")[:10]
                if not fund_code or not start_date:
                    continue
                cleaned.append({
                    "manager_id": manager_id,
                    "fund_code": fund_code,
                    "fund_name": tenure.get("fund_name"),
                    "start_date": start_date,
                    "end_date": str(tenure.get("end_date") or "")[:10] or None,
                    "is_current": bool(tenure.get("is_current")),
                    "performance_snapshot": json.dumps(
                        _clean_json_value(tenure.get("performance_snapshot") or {}),
                        default=_json_ser,
                        ensure_ascii=False,
                        allow_nan=False,
                    ),
                    "source": tenure.get("source") or "tushare.fund_manager",
                    "raw_data": json.dumps(
                        _clean_json_value(tenure.get("raw_data") or {}),
                        default=_json_ser,
                        ensure_ascii=False,
                        allow_nan=False,
                    ),
                })

            with self.engine.begin() as conn:
                conn.execute(text("DELETE FROM manager_fund_tenures WHERE manager_id = :manager_id"), {
                    "manager_id": manager_id,
                })
                for item in cleaned:
                    conn.execute(text("""
                        INSERT INTO manager_fund_tenures (
                            manager_id, fund_code, fund_name, start_date, end_date,
                            is_current, performance_snapshot, source, raw_data, updated_at
                        ) VALUES (
                            :manager_id, :fund_code, :fund_name, :start_date, :end_date,
                            :is_current, CAST(:performance_snapshot AS JSONB), :source,
                            CAST(:raw_data AS JSONB), NOW()
                        )
                        ON CONFLICT (manager_id, fund_code, start_date) DO UPDATE SET
                            fund_name = EXCLUDED.fund_name,
                            end_date = EXCLUDED.end_date,
                            is_current = EXCLUDED.is_current,
                            performance_snapshot = EXCLUDED.performance_snapshot,
                            source = EXCLUDED.source,
                            raw_data = EXCLUDED.raw_data,
                            updated_at = NOW()
                    """), item)

                current_codes = [item["fund_code"] for item in cleaned if item["is_current"]]
                conn.execute(text("""
                    UPDATE managers
                    SET current_funds = :current_funds,
                        historical_performance = jsonb_build_object(
                            'tenure_count', :tenure_count,
                            'current_tenure_count', :current_tenure_count,
                            'source', 'manager_fund_tenures'
                        ),
                        updated_at = NOW()
                    WHERE wind_code = :manager_id
                """), {
                    "manager_id": manager_id,
                    "current_funds": list(dict.fromkeys(current_codes)),
                    "tenure_count": len(cleaned),
                    "current_tenure_count": len(current_codes),
                })
            return True
        except Exception as e:
            logger.error(f"replace_fund_tenures error for {manager_id}: {e}")
            return False

    def upsert_fund_tenures(self, manager_id: str, tenures: List[Dict[str, Any]]) -> int:
        """增量写入经理任职记录，不删除该经理已有的其他产品历史。"""
        try:
            from sqlalchemy import text

            saved = 0
            with self.engine.begin() as conn:
                for tenure in tenures:
                    fund_code = str(tenure.get("fund_code") or "").strip().upper()
                    start_date = str(tenure.get("start_date") or "")[:10]
                    if not fund_code or not start_date:
                        continue
                    conn.execute(text("""
                        INSERT INTO manager_fund_tenures (
                            manager_id, fund_code, fund_name, start_date, end_date,
                            is_current, performance_snapshot, source, raw_data, updated_at
                        ) VALUES (
                            :manager_id, :fund_code, :fund_name, :start_date, :end_date,
                            :is_current, CAST(:performance_snapshot AS JSONB), :source,
                            CAST(:raw_data AS JSONB), NOW()
                        )
                        ON CONFLICT (manager_id, fund_code, start_date) DO UPDATE SET
                            fund_name = EXCLUDED.fund_name,
                            end_date = EXCLUDED.end_date,
                            is_current = EXCLUDED.is_current,
                            source = EXCLUDED.source,
                            raw_data = EXCLUDED.raw_data,
                            updated_at = NOW()
                    """), {
                        "manager_id": manager_id,
                        "fund_code": fund_code,
                        "fund_name": tenure.get("fund_name"),
                        "start_date": start_date,
                        "end_date": str(tenure.get("end_date") or "")[:10] or None,
                        "is_current": bool(tenure.get("is_current")),
                        "performance_snapshot": json.dumps(
                            _clean_json_value(tenure.get("performance_snapshot") or {}),
                            default=_json_ser,
                            ensure_ascii=False,
                            allow_nan=False,
                        ),
                        "source": tenure.get("source") or "tushare.fund_manager",
                        "raw_data": json.dumps(
                            _clean_json_value(tenure.get("raw_data") or {}),
                            default=_json_ser,
                            ensure_ascii=False,
                            allow_nan=False,
                        ),
                    })
                    saved += 1
            return saved
        except Exception as e:
            logger.error(f"upsert_fund_tenures error for {manager_id}: {e}")
            return 0

    def list_fund_tenures(self, manager_id: str) -> List[Dict[str, Any]]:
        """返回经理全部现任和历史产品，并合并本地基金与任期指标。"""
        try:
            from sqlalchemy import text

            sql = """
                SELECT
                    tenure.fund_code,
                    COALESCE(fund.name, tenure.fund_name, tenure.fund_code) AS fund_name,
                    fund.type,
                    fund.total_asset,
                    fund.nav_date,
                    tenure.start_date,
                    tenure.end_date,
                    tenure.is_current,
                    tenure.performance_snapshot,
                    tenure.source,
                    tenure.raw_data,
                    share.entity_id,
                    share.is_primary,
                    entity.canonical_name,
                    family.key AS strategy_key,
                    family.name AS strategy_name,
                    peer.peer_group_name,
                    benchmark.benchmark_code,
                    benchmark.benchmark_name,
                    benchmark.benchmark_type,
                    COALESCE(nav_evidence.benchmark_nav_observations, 0) AS benchmark_nav_observations,
                    metrics.manager_tenure,
                    metrics.one_year
                FROM manager_fund_tenures tenure
                LEFT JOIN funds fund ON fund.wind_code = tenure.fund_code
                LEFT JOIN fund_share_classes share ON share.wind_code = tenure.fund_code
                LEFT JOIN fund_entities entity ON entity.id = share.entity_id
                LEFT JOIN strategy_families family ON family.id = entity.strategy_family_id
                LEFT JOIN LATERAL (
                    SELECT group_row.name AS peer_group_name
                    FROM peer_group_members membership
                    JOIN peer_groups group_row ON group_row.id = membership.peer_group_id
                    WHERE membership.entity_id = share.entity_id
                      AND membership.role <> 'excluded'
                    ORDER BY
                        CASE membership.role WHEN 'primary' THEN 0 WHEN 'target' THEN 1 ELSE 2 END,
                        membership.confidence DESC NULLS LAST
                    LIMIT 1
                ) peer ON TRUE
                LEFT JOIN LATERAL (
                    SELECT
                        mapping.benchmark_code,
                        mapping.benchmark_name,
                        mapping.benchmark_type
                    FROM benchmark_mappings mapping
                    WHERE mapping.entity_id = share.entity_id
                      AND mapping.status = 'active'
                      AND (
                          mapping.effective_from IS NULL
                          OR mapping.effective_from <= COALESCE(tenure.end_date, CURRENT_DATE)
                      )
                      AND (
                          mapping.effective_to IS NULL
                          OR mapping.effective_to >= tenure.start_date
                      )
                    ORDER BY
                        mapping.confidence DESC NULLS LAST,
                        mapping.effective_from DESC NULLS LAST,
                        mapping.updated_at DESC
                    LIMIT 1
                ) benchmark ON TRUE
                LEFT JOIN LATERAL (
                    SELECT COUNT(*) FILTER (
                        WHERE nav.benchmark_nav IS NOT NULL
                    ) AS benchmark_nav_observations
                    FROM fund_nav nav
                    WHERE nav.wind_code = tenure.fund_code
                      AND nav.trade_date >= tenure.start_date
                      AND nav.trade_date <= COALESCE(tenure.end_date, CURRENT_DATE)
                ) nav_evidence ON TRUE
                LEFT JOIN LATERAL (
                    SELECT
                        jsonb_object_agg(metric_name, metric_value)
                            FILTER (WHERE metric_window = 'manager_tenure') AS manager_tenure,
                        jsonb_object_agg(metric_name, metric_value)
                            FILTER (WHERE metric_window = '1y') AS one_year
                    FROM (
                        SELECT DISTINCT ON (metric_window, metric_name)
                            metric_window, metric_name, metric_value
                        FROM metric_snapshots
                        WHERE target_type = 'fund'
                          AND target_id = tenure.fund_code
                          AND metric_window IN ('manager_tenure', '1y')
                        ORDER BY metric_window, metric_name, as_of_date DESC, updated_at DESC
                    ) latest_metric
                ) metrics ON TRUE
                WHERE tenure.manager_id = :manager_id
                ORDER BY tenure.is_current DESC, tenure.start_date DESC, tenure.fund_code
            """
            with self.engine.connect() as conn:
                rows = conn.execute(text(sql), {"manager_id": manager_id}).fetchall()
            return [dict(row._mapping) for row in rows]
        except Exception as e:
            logger.error(f"list_fund_tenures error for {manager_id}: {e}")
            return []

    def get_current_fund_tenure_context(self, fund_code: str) -> Dict[str, Any]:
        """返回基金现任管理团队的共同评价起点。多人共管时取最晚上任日。"""
        try:
            from sqlalchemy import text

            with self.engine.connect() as conn:
                row = conn.execute(text("""
                    SELECT
                        MAX(start_date) AS start_date,
                        MIN(start_date) AS earliest_start_date,
                        ARRAY_AGG(DISTINCT manager_id ORDER BY manager_id) AS manager_ids,
                        ARRAY_AGG(DISTINCT source ORDER BY source) AS record_sources
                    FROM manager_fund_tenures
                    WHERE fund_code = :fund_code
                      AND is_current = TRUE
                """), {"fund_code": str(fund_code or "").strip().upper()}).fetchone()
            if not row or not row._mapping.get("start_date"):
                return {}
            values = dict(row._mapping)
            return {
                "start_date": values["start_date"].isoformat(),
                "earliest_start_date": values["earliest_start_date"].isoformat(),
                "manager_ids": list(values.get("manager_ids") or []),
                "record_sources": list(values.get("record_sources") or []),
                "source": "manager_fund_tenures",
            }
        except Exception as e:
            logger.error(f"get_current_fund_tenure_context error for {fund_code}: {e}")
            return {}

    def list_current_fund_tenure_contexts(self, fund_codes: List[str]) -> Dict[str, Dict[str, Any]]:
        """批量返回基金现任管理团队起点，供同类基金评价复用。"""
        normalized_codes = list(dict.fromkeys(
            str(code or "").strip().upper()
            for code in fund_codes
            if str(code or "").strip()
        ))
        if not normalized_codes:
            return {}
        try:
            from sqlalchemy import text

            with self.engine.connect() as conn:
                rows = conn.execute(text("""
                    SELECT
                        fund_code,
                        MAX(start_date) AS start_date,
                        MIN(start_date) AS earliest_start_date,
                        ARRAY_AGG(DISTINCT manager_id ORDER BY manager_id) AS manager_ids,
                        ARRAY_AGG(DISTINCT source ORDER BY source) AS record_sources
                    FROM manager_fund_tenures
                    WHERE fund_code = ANY(:fund_codes)
                      AND is_current = TRUE
                    GROUP BY fund_code
                """), {"fund_codes": normalized_codes}).fetchall()
            return {
                str(row._mapping["fund_code"]): {
                    "start_date": row._mapping["start_date"].isoformat(),
                    "earliest_start_date": row._mapping["earliest_start_date"].isoformat(),
                    "manager_ids": list(row._mapping.get("manager_ids") or []),
                    "record_sources": list(row._mapping.get("record_sources") or []),
                    "source": "manager_fund_tenures",
                }
                for row in rows
                if row._mapping.get("start_date")
            }
        except Exception as e:
            logger.error(f"list_current_fund_tenure_contexts error: {e}")
            return {}

    def list_fund_manager_history(self, fund_code: str) -> List[Dict[str, Any]]:
        """返回基金实体下全部份额的真实经理任职记录。"""
        try:
            from sqlalchemy import text

            code = str(fund_code or "").strip().upper()
            sql = """
                WITH target_share AS (
                    SELECT entity_id
                    FROM fund_share_classes
                    WHERE wind_code = :fund_code
                    LIMIT 1
                ), target_codes AS (
                    SELECT share.wind_code
                    FROM fund_share_classes share
                    WHERE share.entity_id = (SELECT entity_id FROM target_share)
                    UNION
                    SELECT :fund_code
                )
                SELECT
                    tenure.manager_id,
                    COALESCE(NULLIF(manager.name, ''), tenure.manager_id) AS manager_name,
                    manager.company,
                    tenure.fund_code,
                    tenure.start_date,
                    tenure.end_date,
                    tenure.is_current,
                    tenure.source,
                    tenure.updated_at AS record_updated_at,
                    share.entity_id,
                    share.share_class,
                    share.is_primary,
                    entity.canonical_code,
                    entity.canonical_name
                FROM manager_fund_tenures tenure
                JOIN target_codes target ON target.wind_code = tenure.fund_code
                LEFT JOIN managers manager ON manager.wind_code = tenure.manager_id
                LEFT JOIN fund_share_classes share ON share.wind_code = tenure.fund_code
                LEFT JOIN fund_entities entity ON entity.id = share.entity_id
                ORDER BY tenure.start_date DESC, tenure.manager_id, tenure.fund_code
            """
            with self.engine.connect() as conn:
                rows = conn.execute(text(sql), {"fund_code": code}).fetchall()
            return [dict(row._mapping) for row in rows]
        except Exception as e:
            logger.error(f"list_fund_manager_history error for {fund_code}: {e}")
            return []

    def list_identity_catalog(self) -> List[Dict[str, Any]]:
        """Return the small manager identity catalog used by memo matching."""
        try:
            from sqlalchemy import text

            with self.engine.connect() as conn:
                rows = conn.execute(text("""
                    SELECT
                        manager.wind_code,
                        manager.name,
                        COALESCE(
                            NULLIF(manager.company, ''),
                            (ARRAY_AGG(DISTINCT COALESCE(
                                NULLIF(fund.raw_data#>>'{universe,company}', ''),
                                NULLIF(fund.raw_data#>>'{info,company}', '')
                            )) FILTER (WHERE fund.wind_code IS NOT NULL))[1],
                            ''
                        ) AS company
                    FROM managers manager
                    LEFT JOIN LATERAL unnest(COALESCE(manager.current_funds, ARRAY[]::TEXT[])) code ON TRUE
                    LEFT JOIN funds fund ON fund.wind_code = code
                    WHERE NULLIF(manager.name, '') IS NOT NULL
                    GROUP BY manager.wind_code, manager.name, manager.company
                    ORDER BY LENGTH(manager.name) DESC, manager.name
                """)).fetchall()
            return [dict(row._mapping) for row in rows]
        except Exception as e:
            logger.error(f"list_identity_catalog error: {e}")
            return []

    def list_fund_company_catalog(self) -> List[str]:
        """Return authoritative fund-company names used to strip filename prefixes."""
        try:
            from sqlalchemy import text

            with self.engine.connect() as conn:
                rows = conn.execute(text("""
                    SELECT DISTINCT COALESCE(
                        NULLIF(raw_data#>>'{universe,company}', ''),
                        NULLIF(raw_data#>>'{info,company}', ''),
                        NULLIF(raw_data->>'company', '')
                    ) AS company
                    FROM funds
                    WHERE COALESCE(
                        NULLIF(raw_data#>>'{universe,company}', ''),
                        NULLIF(raw_data#>>'{info,company}', ''),
                        NULLIF(raw_data->>'company', '')
                    ) IS NOT NULL
                    ORDER BY company
                """)).fetchall()
            return [str(row[0]).strip() for row in rows if str(row[0] or "").strip()]
        except Exception as e:
            logger.error(f"list_fund_company_catalog error: {e}")
            return []

    def list_managers(
        self,
        keyword: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> Dict[str, Any]:
        """列表查询基金经理"""
        try:
            from sqlalchemy import text

            where_clauses = []
            params = {}

            if keyword:
                where_clauses.append("(name ILIKE :keyword OR company ILIKE :keyword)")
                params["keyword"] = f"%{keyword}%"

            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
            offset = (page - 1) * page_size

            count_sql = f"SELECT COUNT(*) as total FROM managers WHERE {where_sql}"
            data_sql = f"""
                SELECT * FROM managers
                WHERE {where_sql}
                ORDER BY updated_at DESC
                LIMIT :limit OFFSET :offset
            """

            with self.engine.connect() as conn:
                count_result = conn.execute(text(count_sql), params)
                total = count_result.fetchone()[0]

                params["limit"] = page_size
                params["offset"] = offset
                data_result = conn.execute(text(data_sql), params)
                rows = data_result.fetchall()

            return {
                "total": total,
                "managers": [dict(r._mapping) for r in rows]
            }
        except Exception as e:
            logger.error(f"list_managers error: {e}")
            return {"total": 0, "managers": []}

    def browse_managers(
        self,
        keyword: Optional[str] = None,
        category: Optional[str] = None,
        evidence: Optional[str] = None,
        page: int = 1,
        page_size: int = 24,
    ) -> Dict[str, Any]:
        """一次返回基金经理浏览器需要的研究事实。"""
        from sqlalchemy import text

        normalized_keyword = str(keyword or "").strip()
        normalized_category = str(category or "all").strip().lower() or "all"
        allowed_categories = {
            "all", "fixed_income", "fixed_income_plus", "active_equity",
            "passive_equity", "qdii", "fof", "money_market", "other",
        }
        if normalized_category not in allowed_categories:
            normalized_category = "all"
        normalized_evidence = str(evidence or "all").strip().lower() or "all"
        allowed_evidence = {"all", "with_memo", "with_metrics", "research_ready"}
        if normalized_evidence not in allowed_evidence:
            normalized_evidence = "all"
        limit = max(1, min(int(page_size), 100))
        params = {
            "keyword": normalized_keyword,
            "keyword_pattern": f"%{normalized_keyword}%",
            "category": normalized_category,
            "evidence": normalized_evidence,
            "limit": limit,
            "offset": max(0, int(page) - 1) * limit,
        }
        cte = f"""
            WITH manager_funds AS (
                SELECT DISTINCT
                    manager.wind_code AS manager_id,
                    fund.wind_code AS fund_code,
                    fund.name AS fund_name,
                    fund.type AS fund_type,
                    fund.total_asset,
                    fund.nav_date,
                    fund.updated_at AS fund_updated_at,
                    'name:' || LOWER(
                        CASE
                            WHEN UPPER(REGEXP_REPLACE(fund.name, '[[:space:]]+', '', 'g')) ~ '(ETF|LOF|QDII)$'
                            THEN REGEXP_REPLACE(fund.name, '[[:space:]]+', '', 'g')
                            ELSE REGEXP_REPLACE(
                                REGEXP_REPLACE(fund.name, '[[:space:]]+', '', 'g'),
                                '[-_ /]?[A-Z](类|份额)?([-_ /]?(CNY|RMB|USD|HKD)([-_ /]?(现汇|现钞))?)?$',
                                '',
                                'i'
                            )
                        END
                    ) AS product_key,
                    COALESCE(
                        NULLIF(fund.raw_data#>>'{{universe,company}}', ''),
                        NULLIF(fund.raw_data#>>'{{info,company}}', '')
                    ) AS fund_company,
                    share.entity_id,
                    share.is_primary,
                    family.key AS strategy_key,
                    family.name AS strategy_name,
                    family.asset_class,
                    family.active_passive,
                    peer.peer_group_id,
                    peer.peer_group_name,
                    CASE
                        WHEN family.key = 'fixed_income_equity_allocation'
                          OR family.key = 'mixed_bond_allocation'
                          OR family.key = 'mixed_balanced_allocation'
                        THEN 'fixed_income_plus'
                        WHEN family.asset_class = 'fixed_income'
                        THEN 'fixed_income'
                        WHEN family.asset_class IN ('equity', 'multi_asset') AND family.active_passive = 'active'
                        THEN 'active_equity'
                        WHEN family.active_passive = 'passive'
                          AND family.asset_class IN ('index', 'equity')
                        THEN 'passive_equity'
                        WHEN family.asset_class = 'global' OR family.key LIKE 'qdii%'
                        THEN 'qdii'
                        WHEN family.key LIKE 'fof%' OR family.asset_class = 'fof'
                        THEN 'fof'
                        WHEN family.asset_class = 'money_market'
                        THEN 'money_market'
                        ELSE 'other'
                    END AS category_key,
                    CASE WHEN share.entity_id IS NOT NULL AND peer.peer_group_id IS NOT NULL THEN 1 ELSE 0 END AS classified,
                    CASE WHEN metric.metric_count > 0 THEN 1 ELSE 0 END AS evaluated,
                    CASE WHEN metric.has_manager_tenure THEN 1 ELSE 0 END AS has_manager_tenure,
                    COALESCE(metric.metric_count, 0) AS metric_count,
                    metric.latest_metric_date,
                    metric.metric_window,
                    metric.annualized_return,
                    metric.max_drawdown,
                    metric.sharpe_ratio,
                    metric.annualized_volatility
                FROM managers manager
                CROSS JOIN LATERAL unnest(COALESCE(manager.current_funds, ARRAY[]::TEXT[])) AS current_fund(fund_code)
                JOIN funds fund ON fund.wind_code = current_fund.fund_code
                LEFT JOIN fund_share_classes share
                  ON share.wind_code = fund.wind_code AND share.status = 'active'
                LEFT JOIN fund_entities entity ON entity.id = share.entity_id
                LEFT JOIN strategy_families family ON family.id = entity.strategy_family_id
                LEFT JOIN LATERAL (
                    SELECT
                        group_row.id AS peer_group_id,
                        group_row.name AS peer_group_name
                    FROM peer_group_members membership
                    JOIN peer_groups group_row ON group_row.id = membership.peer_group_id
                    WHERE membership.entity_id = share.entity_id
                      AND membership.role <> 'excluded'
                    ORDER BY
                        CASE membership.role WHEN 'primary' THEN 0 WHEN 'target' THEN 1 ELSE 2 END,
                        membership.confidence DESC NULLS LAST,
                        membership.updated_at DESC
                    LIMIT 1
                ) peer ON TRUE
                LEFT JOIN LATERAL (
                    WITH latest_by_window AS (
                        SELECT
                            snapshot.metric_window,
                            MAX(snapshot.as_of_date) AS as_of_date
                        FROM metric_snapshots snapshot
                        WHERE snapshot.target_type = 'fund'
                          AND snapshot.target_id = fund.wind_code
                          AND snapshot.metric_window IN ('manager_tenure', '1y')
                        GROUP BY snapshot.metric_window
                    ), preferred_window AS (
                        SELECT metric_window, as_of_date
                        FROM latest_by_window
                        ORDER BY CASE metric_window WHEN 'manager_tenure' THEN 0 ELSE 1 END
                        LIMIT 1
                    )
                    SELECT
                        COUNT(DISTINCT snapshot.metric_name) FILTER (
                            WHERE snapshot.metric_name IN (
                                'annualized_return', 'max_drawdown', 'sharpe_ratio',
                                'annualized_volatility', 'expense_ratio'
                            )
                        )::int AS metric_count,
                        BOOL_OR(snapshot.metric_window = 'manager_tenure') AS has_manager_tenure,
                        preferred_window.as_of_date AS latest_metric_date,
                        preferred_window.metric_window,
                        MAX(snapshot.metric_value) FILTER (WHERE snapshot.metric_name = 'annualized_return') AS annualized_return,
                        MAX(snapshot.metric_value) FILTER (WHERE snapshot.metric_name = 'max_drawdown') AS max_drawdown,
                        MAX(snapshot.metric_value) FILTER (WHERE snapshot.metric_name = 'sharpe_ratio') AS sharpe_ratio,
                        MAX(snapshot.metric_value) FILTER (WHERE snapshot.metric_name = 'annualized_volatility') AS annualized_volatility
                    FROM preferred_window
                    JOIN metric_snapshots snapshot
                      ON snapshot.target_type = 'fund'
                     AND snapshot.target_id = fund.wind_code
                     AND snapshot.metric_window = preferred_window.metric_window
                     AND snapshot.as_of_date = preferred_window.as_of_date
                    GROUP BY preferred_window.metric_window, preferred_window.as_of_date
                ) metric ON TRUE
            ),
            classified AS (
                SELECT * FROM manager_funds
            ),
            report_coverage AS (
                SELECT
                    manager.wind_code AS manager_id,
                    COUNT(DISTINCT report.id)::int AS memo_count,
                    MAX(report.report_date) AS latest_memo_date,
                    ARRAY_REMOVE(ARRAY_AGG(DISTINCT CASE
                        WHEN proposal->>'kind' = 'style_label'
                         AND proposal->>'scope' = 'manager'
                         AND proposal->>'review_status' = 'confirmed'
                         AND proposal->>'value' = ANY(COALESCE(report.style_labels, ARRAY[]::TEXT[]))
                        THEN proposal->>'value'
                    END), NULL) AS memo_style_labels
                FROM managers manager
                LEFT JOIN research_report_managers report_link
                  ON report_link.manager_id = manager.wind_code
                LEFT JOIN research_reports report ON report.id = report_link.report_id
                LEFT JOIN LATERAL jsonb_array_elements(
                    COALESCE(report.review_proposals, '[]'::jsonb)
                ) proposal ON TRUE
                GROUP BY manager.wind_code
            ),
            latest_report AS (
                SELECT DISTINCT ON (report_link.manager_id)
                    report_link.manager_id,
                    report.id AS latest_memo_id,
                    report.title AS latest_memo_title,
                    report.summary AS latest_memo_summary,
                    report.report_date AS latest_memo_date,
                    report.report_date_source AS latest_memo_date_source,
                    report.report_date_precision AS latest_memo_date_precision,
                    COALESCE(report.viewpoint_topics, ARRAY[]::TEXT[]) AS latest_memo_topics,
                    COALESCE(report.research_domains, ARRAY[]::TEXT[]) AS latest_memo_domains
                FROM research_report_managers report_link
                JOIN research_reports report ON report.id = report_link.report_id
                ORDER BY
                    report_link.manager_id,
                    report.report_date DESC NULLS LAST,
                    report.updated_at DESC NULLS LAST,
                    report.id DESC
            ),
            manager_rows AS (
                SELECT
                    manager.wind_code AS id,
                    manager.name,
                    COALESCE(
                        NULLIF(manager.company, ''),
                        (ARRAY_AGG(classified.fund_company ORDER BY classified.fund_code)
                            FILTER (WHERE NULLIF(classified.fund_company, '') IS NOT NULL))[1]
                    ) AS company,
                    manager.education,
                    manager.work_years,
                    manager.management_years,
                    COALESCE(manager.current_funds, ARRAY[]::TEXT[]) AS current_fund_codes,
                    COUNT(DISTINCT classified.product_key)::int AS current_fund_count,
                    COUNT(DISTINCT classified.product_key)
                      FILTER (WHERE classified.classified = 1)::int AS classified_fund_count,
                    COUNT(DISTINCT classified.product_key)
                      FILTER (WHERE classified.evaluated = 1)::int AS evaluated_fund_count,
                    COUNT(DISTINCT classified.product_key)
                      FILTER (WHERE classified.has_manager_tenure = 1)::int AS tenure_metric_fund_count,
                    COALESCE(report_coverage.memo_count, 0)::int AS memo_count,
                    report_coverage.latest_memo_date,
                    latest_report.latest_memo_id,
                    latest_report.latest_memo_title,
                    latest_report.latest_memo_summary,
                    latest_report.latest_memo_date_source,
                    latest_report.latest_memo_date_precision,
                    latest_report.latest_memo_topics,
                    latest_report.latest_memo_domains,
                    ARRAY_REMOVE(ARRAY_AGG(DISTINCT classified.category_key), NULL) AS category_keys,
                    ARRAY_REMOVE(ARRAY_AGG(DISTINCT classified.strategy_name), NULL) AS strategy_names,
                    ARRAY_REMOVE(ARRAY_AGG(DISTINCT classified.peer_group_name), NULL) AS peer_groups,
                    ARRAY_REMOVE(ARRAY[manager_profile.style_label]::TEXT[], NULL)
                      || COALESCE(report_coverage.memo_style_labels, ARRAY[]::TEXT[]) AS style_labels,
                    COALESCE(manager_profile.focus_industries, ARRAY[]::TEXT[]) AS focus_industries,
                    (ARRAY_AGG(classified.fund_code ORDER BY
                        CASE WHEN :category = 'all' OR classified.category_key = :category THEN 0 ELSE 1 END,
                        CASE classified.metric_window WHEN 'manager_tenure' THEN 0 WHEN '1y' THEN 1 ELSE 2 END,
                        classified.metric_count DESC,
                        classified.total_asset DESC NULLS LAST,
                        classified.is_primary DESC NULLS LAST,
                        classified.fund_code
                    ) FILTER (WHERE classified.fund_code IS NOT NULL))[1] AS representative_fund_code,
                    (ARRAY_AGG(classified.fund_name ORDER BY
                        CASE WHEN :category = 'all' OR classified.category_key = :category THEN 0 ELSE 1 END,
                        CASE classified.metric_window WHEN 'manager_tenure' THEN 0 WHEN '1y' THEN 1 ELSE 2 END,
                        classified.metric_count DESC,
                        classified.total_asset DESC NULLS LAST,
                        classified.is_primary DESC NULLS LAST,
                        classified.fund_code
                    ) FILTER (WHERE classified.fund_code IS NOT NULL))[1] AS representative_fund_name,
                    (ARRAY_AGG(classified.metric_window ORDER BY
                        CASE WHEN :category = 'all' OR classified.category_key = :category THEN 0 ELSE 1 END,
                        CASE classified.metric_window WHEN 'manager_tenure' THEN 0 WHEN '1y' THEN 1 ELSE 2 END,
                        classified.metric_count DESC,
                        classified.total_asset DESC NULLS LAST,
                        classified.is_primary DESC NULLS LAST,
                        classified.fund_code
                    ) FILTER (WHERE classified.fund_code IS NOT NULL))[1] AS representative_metric_window,
                    (ARRAY_AGG(classified.latest_metric_date ORDER BY
                        CASE WHEN :category = 'all' OR classified.category_key = :category THEN 0 ELSE 1 END,
                        CASE classified.metric_window WHEN 'manager_tenure' THEN 0 WHEN '1y' THEN 1 ELSE 2 END,
                        classified.metric_count DESC,
                        classified.total_asset DESC NULLS LAST,
                        classified.is_primary DESC NULLS LAST,
                        classified.fund_code
                    ) FILTER (WHERE classified.fund_code IS NOT NULL))[1] AS representative_metric_date,
                    (ARRAY_AGG(classified.annualized_return ORDER BY
                        CASE WHEN :category = 'all' OR classified.category_key = :category THEN 0 ELSE 1 END,
                        CASE classified.metric_window WHEN 'manager_tenure' THEN 0 WHEN '1y' THEN 1 ELSE 2 END,
                        classified.metric_count DESC,
                        classified.total_asset DESC NULLS LAST,
                        classified.is_primary DESC NULLS LAST,
                        classified.fund_code
                    ) FILTER (WHERE classified.fund_code IS NOT NULL))[1] AS representative_annualized_return,
                    (ARRAY_AGG(classified.max_drawdown ORDER BY
                        CASE WHEN :category = 'all' OR classified.category_key = :category THEN 0 ELSE 1 END,
                        CASE classified.metric_window WHEN 'manager_tenure' THEN 0 WHEN '1y' THEN 1 ELSE 2 END,
                        classified.metric_count DESC,
                        classified.total_asset DESC NULLS LAST,
                        classified.is_primary DESC NULLS LAST,
                        classified.fund_code
                    ) FILTER (WHERE classified.fund_code IS NOT NULL))[1] AS representative_max_drawdown,
                    (ARRAY_AGG(classified.sharpe_ratio ORDER BY
                        CASE WHEN :category = 'all' OR classified.category_key = :category THEN 0 ELSE 1 END,
                        CASE classified.metric_window WHEN 'manager_tenure' THEN 0 WHEN '1y' THEN 1 ELSE 2 END,
                        classified.metric_count DESC,
                        classified.total_asset DESC NULLS LAST,
                        classified.is_primary DESC NULLS LAST,
                        classified.fund_code
                    ) FILTER (WHERE classified.fund_code IS NOT NULL))[1] AS representative_sharpe_ratio,
                    (ARRAY_AGG(classified.annualized_volatility ORDER BY
                        CASE WHEN :category = 'all' OR classified.category_key = :category THEN 0 ELSE 1 END,
                        CASE classified.metric_window WHEN 'manager_tenure' THEN 0 WHEN '1y' THEN 1 ELSE 2 END,
                        classified.metric_count DESC,
                        classified.total_asset DESC NULLS LAST,
                        classified.is_primary DESC NULLS LAST,
                        classified.fund_code
                    ) FILTER (WHERE classified.fund_code IS NOT NULL))[1] AS representative_annualized_volatility,
                    MAX(classified.latest_metric_date) AS latest_metric_date,
                    manager.updated_at
                FROM managers manager
                LEFT JOIN classified ON classified.manager_id = manager.wind_code
                LEFT JOIN report_coverage ON report_coverage.manager_id = manager.wind_code
                LEFT JOIN latest_report ON latest_report.manager_id = manager.wind_code
                LEFT JOIN manager_profiles manager_profile ON manager_profile.manager_id = manager.wind_code
                WHERE (
                    classified.manager_id IS NOT NULL
                    OR COALESCE(report_coverage.memo_count, 0) > 0
                )
                  AND (
                    :category = 'all'
                    OR EXISTS (
                        SELECT 1
                        FROM classified category_match
                        WHERE category_match.manager_id = manager.wind_code
                          AND category_match.category_key = :category
                    )
                  )
                GROUP BY manager.wind_code, manager.name, manager.company, manager.education,
                    manager.work_years, manager.management_years, manager.current_funds,
                    report_coverage.memo_count, report_coverage.latest_memo_date,
                    latest_report.latest_memo_id, latest_report.latest_memo_title,
                    latest_report.latest_memo_summary, latest_report.latest_memo_date_source,
                    latest_report.latest_memo_date_precision, latest_report.latest_memo_topics,
                    latest_report.latest_memo_domains, report_coverage.memo_style_labels,
                    manager_profile.style_label, manager_profile.focus_industries, manager.updated_at
            )
        """
        where_sql = """
            (
                :keyword = ''
                OR name ILIKE :keyword_pattern
                OR COALESCE(company, '') ILIKE :keyword_pattern
                OR COALESCE(representative_fund_name, '') ILIKE :keyword_pattern
            )
            AND (
                :evidence = 'all'
                OR (:evidence = 'with_memo' AND memo_count > 0)
                OR (:evidence = 'with_metrics' AND representative_metric_window IS NOT NULL)
                OR (:evidence = 'research_ready' AND memo_count > 0 AND representative_metric_window IS NOT NULL)
            )
        """
        data_sql = text(cte + f"""
            SELECT manager_rows.*, COUNT(*) OVER()::int AS total_count
            FROM manager_rows
            WHERE {where_sql}
            ORDER BY
                memo_count DESC,
                classified_fund_count DESC,
                evaluated_fund_count DESC,
                tenure_metric_fund_count DESC,
                management_years DESC NULLS LAST,
                name ASC
            LIMIT :limit OFFSET :offset
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(data_sql, params).fetchall()
        total = int(rows[0]._mapping.get("total_count") or 0) if rows else 0
        return {
            "total": total,
            "managers": [
                {key: value for key, value in row._mapping.items() if key != "total_count"}
                for row in rows
            ],
        }

    def upsert_profile(self, manager_id: str, profile: Dict[str, Any]) -> bool:
        """Upsert 基金经理画像"""
        try:
            from sqlalchemy import text

            sql = """
            INSERT INTO manager_profiles (
                manager_id, product_positioning, investment_objective, investment_method,
                core_philosophy, stock_selection_logic, risk_philosophy,
                focus_industries, competence_advantages, competence_boundaries,
                style_label, concentration, turnover, excess_return_source, holding_style, style_stability,
                philosophy_score, competence_score, style_score, overall_quality_score,
                philosophy_behavior_consistency, valuation_consistency, quality_consistency,
                industry_consistency, key_insights, red_flags, interviews_analyzed, last_interview_date,
                evidence, updated_by
            )
            VALUES (
                :manager_id, :product_positioning, :investment_objective, :investment_method,
                :philosophy, :stock_logic, :risk_philosophy,
                :focus_industries, :advantages, :boundaries,
                :style_label, :concentration, :turnover, :excess_return_source, :holding_style, :style_stability,
                :phil_score, :comp_score, :style_score, :overall_score,
                :phil_consistency, :val_consistency, :qual_consistency, :ind_consistency,
                :key_insights, :red_flags, :interviews, :last_interview,
                CAST(:evidence AS jsonb), :updated_by
            )
            ON CONFLICT (manager_id) DO UPDATE SET
                product_positioning = EXCLUDED.product_positioning,
                investment_objective = EXCLUDED.investment_objective,
                investment_method = EXCLUDED.investment_method,
                core_philosophy = EXCLUDED.core_philosophy,
                stock_selection_logic = EXCLUDED.stock_selection_logic,
                risk_philosophy = EXCLUDED.risk_philosophy,
                focus_industries = EXCLUDED.focus_industries,
                competence_advantages = EXCLUDED.competence_advantages,
                competence_boundaries = EXCLUDED.competence_boundaries,
                style_label = EXCLUDED.style_label,
                concentration = EXCLUDED.concentration,
                turnover = EXCLUDED.turnover,
                excess_return_source = EXCLUDED.excess_return_source,
                holding_style = EXCLUDED.holding_style,
                style_stability = EXCLUDED.style_stability,
                philosophy_score = EXCLUDED.philosophy_score,
                competence_score = EXCLUDED.competence_score,
                style_score = EXCLUDED.style_score,
                overall_quality_score = EXCLUDED.overall_quality_score,
                philosophy_behavior_consistency = EXCLUDED.philosophy_behavior_consistency,
                valuation_consistency = EXCLUDED.valuation_consistency,
                quality_consistency = EXCLUDED.quality_consistency,
                industry_consistency = EXCLUDED.industry_consistency,
                key_insights = EXCLUDED.key_insights,
                red_flags = EXCLUDED.red_flags,
                interviews_analyzed = EXCLUDED.interviews_analyzed,
                last_interview_date = EXCLUDED.last_interview_date,
                evidence = EXCLUDED.evidence,
                updated_by = EXCLUDED.updated_by,
                last_updated = NOW()
            """
            params = {
                "manager_id": manager_id,
                "product_positioning": profile.get("product_positioning"),
                "investment_objective": profile.get("investment_objective"),
                "investment_method": profile.get("investment_method"),
                "philosophy": profile.get("core_philosophy"),
                "stock_logic": profile.get("stock_selection_logic"),
                "risk_philosophy": profile.get("risk_philosophy"),
                "focus_industries": profile.get("focus_industries", []),
                "advantages": profile.get("competence_advantages"),
                "boundaries": profile.get("competence_boundaries"),
                "style_label": profile.get("style_label"),
                "concentration": profile.get("concentration"),
                "turnover": profile.get("turnover"),
                "excess_return_source": profile.get("excess_return_source"),
                "holding_style": profile.get("holding_style"),
                "style_stability": profile.get("style_stability"),
                "phil_score": profile.get("philosophy_score"),
                "comp_score": profile.get("competence_score"),
                "style_score": profile.get("style_score"),
                "overall_score": profile.get("overall_quality_score"),
                "phil_consistency": profile.get("philosophy_behavior_consistency"),
                "val_consistency": profile.get("valuation_consistency"),
                "qual_consistency": profile.get("quality_consistency"),
                "ind_consistency": profile.get("industry_consistency"),
                "key_insights": profile.get("key_insights", []),
                "red_flags": profile.get("red_flags", []),
                "interviews": profile.get("interviews_analyzed", 0),
                "last_interview": profile.get("last_interview_date"),
                "evidence": json.dumps(
                    _clean_json_value(profile.get("evidence", {})),
                    default=_json_ser,
                    ensure_ascii=False,
                    allow_nan=False,
                ),
                "updated_by": profile.get("updated_by"),
            }

            with self.engine.connect() as conn:
                conn.execute(text(sql), params)
                conn.commit()
            return True
        except Exception as e:
            logger.error(f"upsert_profile error for {manager_id}: {e}")
            return False

    def delete_projected_profile(self, manager_id: str, updated_by: str) -> bool:
        """Delete only profiles owned by one deterministic projection module."""
        try:
            from sqlalchemy import text

            with self.engine.begin() as conn:
                result = conn.execute(text("""
                    DELETE FROM manager_profiles
                    WHERE manager_id = :manager_id AND updated_by = :updated_by
                """), {"manager_id": manager_id, "updated_by": updated_by})
            return bool(result.rowcount)
        except Exception as e:
            logger.error(f"delete_projected_profile error for {manager_id}: {e}")
            return False

    def delete_orphaned_projected_profiles(self, updated_by: str) -> int:
        """Delete projected manager profiles that no longer have any confirmed memo."""
        try:
            from sqlalchemy import text

            with self.engine.begin() as conn:
                result = conn.execute(text("""
                    DELETE FROM manager_profiles profile
                    WHERE profile.updated_by = :updated_by
                      AND NOT EXISTS (
                        SELECT 1
                        FROM research_report_managers report_link
                        WHERE report_link.manager_id = profile.manager_id
                      )
                """), {"updated_by": updated_by})
            return int(result.rowcount or 0)
        except Exception as e:
            logger.error(f"delete_orphaned_projected_profiles error: {e}")
            return 0

    def get_profile(self, manager_id: str) -> Optional[Dict[str, Any]]:
        """获取基金经理画像"""
        try:
            from sqlalchemy import text
            sql = "SELECT * FROM manager_profiles WHERE manager_id = :manager_id"
            with self.engine.connect() as conn:
                result = conn.execute(text(sql), {"manager_id": manager_id})
                row = result.fetchone()
                if row:
                    return dict(row._mapping)
                return None
        except Exception as e:
            logger.error(f"get_profile error: {e}")
            return None
