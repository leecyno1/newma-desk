"""标准化基金分类数据库 Adapter。"""
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

try:
    from backend.database import get_engine
    from backend.lib.fund_status import active_fund_sql
except ModuleNotFoundError:
    from database import get_engine
    from lib.fund_status import active_fund_sql


REQUIRED_TABLES = (
    "fund_entities",
    "fund_share_classes",
    "strategy_families",
    "peer_group_members",
    "peer_groups",
    "benchmark_mappings",
)
FOF_LOOKTHROUGH_MIN_FUNDS = 5
FOF_LOOKTHROUGH_MIN_NAV_RATIO = 20.0


def _serialize(value: Any) -> Any:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    return value


def _row_to_dict(row: Any) -> Dict[str, Any]:
    return {str(key): _serialize(value) for key, value in dict(row._mapping).items()}


class FundClassificationRepo:
    """从标准化实体、族谱、同类组和基准表解析基金分类上下文。"""

    def __init__(self, engine: Optional[Any] = None):
        self._engine = engine
        self._schema_ready_cache = False

    @property
    def engine(self):
        if self._engine is None:
            self._engine = get_engine()
        return self._engine

    def get_classification_context(
        self,
        fund_code: str,
        as_of_date: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """解析一个基金份额对应的基金实体、分类、同类组与有效基准。"""
        normalized_code = str(fund_code or "").strip()
        if not normalized_code:
            return self._unavailable("invalid_identifier", normalized_code, ["基金代码为空"])
        if not self._schema_ready():
            return self._unavailable(
                "schema_unavailable",
                normalized_code,
                ["标准化基金分类表尚未完整部署"],
            )

        from sqlalchemy import text

        evaluation_date = as_of_date or date.today()
        sql = f"""
            WITH selected_share AS (
                SELECT
                    fsc.wind_code AS fund_code,
                    fsc.share_class,
                    fsc.source AS share_class_source,
                    fsc.entity_id,
                    fe.canonical_code,
                    fe.canonical_name,
                    fe.strategy_family_id,
                    fe.asset_class AS entity_asset_class,
                    fe.active_passive AS entity_active_passive,
                    fe.source AS entity_source,
                    fe.source_updated_at AS entity_source_updated_at
                FROM fund_share_classes fsc
                JOIN fund_entities fe ON fe.id = fsc.entity_id
                JOIN funds fund_status ON fund_status.wind_code = fsc.wind_code
                WHERE (fsc.wind_code = :fund_code OR fe.canonical_code = :fund_code)
                  AND fsc.status = 'active'
                  AND fe.lifecycle_stage = 'active'
                  AND ({active_fund_sql('fund_status')})
                ORDER BY
                    CASE WHEN fsc.wind_code = :fund_code THEN 0 ELSE 1 END,
                    fsc.is_primary DESC,
                    fsc.wind_code ASC
                LIMIT 1
            )
            SELECT
                ss.fund_code,
                ss.entity_id,
                ss.canonical_code,
                ss.canonical_name,
                ss.entity_source,
                ss.entity_source_updated_at,
                ss.share_class,
                ss.share_class_source,
                sf.key AS strategy_family_key,
                sf.name AS strategy_family_name,
                COALESCE(ss.entity_asset_class, sf.asset_class) AS asset_class,
                COALESCE(ss.entity_active_passive, sf.active_passive) AS active_passive,
                sf.source AS strategy_family_source,
                peer.peer_group_id,
                peer.peer_group_key,
                peer.peer_group_name,
                peer.minimum_peer_count,
                peer.peer_group_source,
                peer.membership_role,
                peer.matched_rules,
                peer.excluded_rules,
                peer.sample_as_of_date,
                peer.membership_confidence,
                peer.membership_source,
                peer.peer_group_membership_count,
                benchmark.benchmark_code,
                benchmark.benchmark_name,
                benchmark.benchmark_type,
                benchmark.mapping_method,
                benchmark.benchmark_confidence,
                benchmark.benchmark_rationale,
                benchmark.benchmark_evidence_refs,
                benchmark.effective_from,
                benchmark.effective_to,
                benchmark.benchmark_source
            FROM selected_share ss
            LEFT JOIN strategy_families sf ON sf.id = ss.strategy_family_id
            LEFT JOIN LATERAL (
                SELECT
                    pg.id AS peer_group_id,
                    pg.key AS peer_group_key,
                    pg.name AS peer_group_name,
                    pg.minimum_peer_count,
                    pg.source AS peer_group_source,
                    pgm.role AS membership_role,
                    pgm.matched_rules,
                    pgm.excluded_rules,
                    pgm.sample_as_of_date,
                    pgm.confidence AS membership_confidence,
                    pgm.source AS membership_source,
                    (
                        SELECT COUNT(DISTINCT group_member.entity_id)
                        FROM peer_group_members group_member
                        JOIN fund_entities member_entity
                          ON member_entity.id = group_member.entity_id
                        WHERE group_member.peer_group_id = pg.id
                          AND group_member.role <> 'excluded'
                          AND member_entity.lifecycle_stage = 'active'
                          AND EXISTS (
                            SELECT 1
                            FROM fund_share_classes member_share
                            JOIN funds member_fund
                              ON member_fund.wind_code = member_share.wind_code
                            WHERE member_share.entity_id = member_entity.id
                              AND member_share.status = 'active'
                              AND ({active_fund_sql('member_fund')})
                          )
                    ) AS peer_group_membership_count
                FROM peer_group_members pgm
                JOIN peer_groups pg ON pg.id = pgm.peer_group_id
                WHERE pgm.entity_id = ss.entity_id
                  AND (pgm.sample_as_of_date IS NULL OR pgm.sample_as_of_date <= :as_of_date)
                ORDER BY
                    CASE pgm.role WHEN 'primary' THEN 0 WHEN 'target' THEN 1 ELSE 2 END,
                    pgm.sample_as_of_date DESC NULLS LAST,
                    pgm.confidence DESC NULLS LAST,
                    pg.updated_at DESC
                LIMIT 1
            ) peer ON TRUE
            LEFT JOIN LATERAL (
                SELECT
                    bm.benchmark_code,
                    bm.benchmark_name,
                    bm.benchmark_type,
                    bm.mapping_method,
                    bm.confidence AS benchmark_confidence,
                    bm.rationale AS benchmark_rationale,
                    bm.evidence_refs AS benchmark_evidence_refs,
                    bm.effective_from,
                    bm.effective_to,
                    bm.source AS benchmark_source
                FROM benchmark_mappings bm
                WHERE bm.entity_id = ss.entity_id
                  AND bm.status = 'active'
                  AND (bm.effective_from IS NULL OR bm.effective_from <= :as_of_date)
                  AND (bm.effective_to IS NULL OR bm.effective_to >= :as_of_date)
                ORDER BY
                    (bm.peer_group_id = peer.peer_group_id) DESC NULLS LAST,
                    bm.updated_at DESC,
                    bm.confidence DESC NULLS LAST,
                    bm.effective_from DESC NULLS LAST
                LIMIT 1
            ) benchmark ON TRUE
        """
        with self.engine.connect() as conn:
            row = conn.execute(
                text(sql),
                {"fund_code": normalized_code, "as_of_date": evaluation_date},
            ).fetchone()
        if not row:
            return self._unavailable(
                "not_found",
                normalized_code,
                ["基金代码尚未归一到 fund_entities / fund_share_classes"],
            )
        return self._build_context(_row_to_dict(row))

    def list_entity_share_codes(self, fund_code: str) -> List[str]:
        """Return every active share code for the fund entity containing this code."""
        normalized_code = str(fund_code or "").strip()
        if not normalized_code or not self._schema_ready():
            return []

        from sqlalchemy import text

        sql = f"""
            WITH selected_entity AS (
                SELECT selected.entity_id
                FROM fund_share_classes selected
                JOIN fund_entities entity ON entity.id = selected.entity_id
                JOIN funds selected_fund ON selected_fund.wind_code = selected.wind_code
                WHERE (selected.wind_code = :fund_code OR entity.canonical_code = :fund_code)
                  AND selected.status = 'active'
                  AND entity.lifecycle_stage = 'active'
                  AND ({active_fund_sql('selected_fund')})
                ORDER BY selected.is_primary DESC, selected.wind_code ASC
                LIMIT 1
            )
            SELECT shares.wind_code
            FROM selected_entity entity
            JOIN fund_share_classes shares ON shares.entity_id = entity.entity_id
            JOIN funds share_fund ON share_fund.wind_code = shares.wind_code
            WHERE shares.status = 'active'
              AND ({active_fund_sql('share_fund')})
            ORDER BY shares.is_primary DESC, shares.wind_code ASC
        """
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), {"fund_code": normalized_code}).fetchall()
        return [str(row.wind_code) for row in rows]

    def list_entity_share_classes(self, fund_code: str) -> List[Dict[str, Any]]:
        """Return active share classes and their local fund facts for one fund entity."""
        normalized_code = str(fund_code or "").strip().upper()
        if not normalized_code or not self._schema_ready():
            return []

        from sqlalchemy import text

        sql = f"""
            WITH selected_entity AS (
                SELECT selected.entity_id
                FROM fund_share_classes selected
                JOIN fund_entities entity ON entity.id = selected.entity_id
                JOIN funds selected_fund ON selected_fund.wind_code = selected.wind_code
                WHERE (selected.wind_code = :fund_code OR entity.canonical_code = :fund_code)
                  AND selected.status = 'active'
                  AND entity.lifecycle_stage = 'active'
                  AND ({active_fund_sql('selected_fund')})
                ORDER BY selected.is_primary DESC, selected.wind_code ASC
                LIMIT 1
            )
            SELECT
                entity.id AS entity_id,
                entity.canonical_code,
                entity.canonical_name,
                shares.wind_code,
                shares.share_class,
                shares.fee_class,
                shares.currency,
                shares.is_primary,
                shares.source AS share_source,
                shares.source_updated_at,
                fund.id AS fund_id,
                fund.name,
                fund.type,
                fund.nav,
                fund.nav_date,
                fund.total_asset,
                fund.establishment_date,
                fund.raw_data,
                fund.updated_at
            FROM selected_entity selected
            JOIN fund_entities entity ON entity.id = selected.entity_id
            JOIN fund_share_classes shares ON shares.entity_id = entity.id
            JOIN funds fund ON fund.wind_code = shares.wind_code
            WHERE shares.status = 'active'
              AND ({active_fund_sql('fund')})
            ORDER BY shares.is_primary DESC, shares.share_class NULLS LAST, shares.wind_code ASC
        """
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), {"fund_code": normalized_code}).fetchall()
        return [_row_to_dict(row) for row in rows]

    def list_peer_funds(
        self,
        peer_group_id: str,
        target_wind_code: Optional[str] = None,
        limit: int = 10000,
    ) -> List[Dict[str, Any]]:
        """按显式同类组成员关系返回每个基金实体的代表份额。"""
        normalized_group = str(peer_group_id or "").strip()
        if not normalized_group or not self._schema_ready():
            return []

        from sqlalchemy import text

        sql = f"""
            SELECT *
            FROM (
                SELECT DISTINCT ON (fe.id)
                    COALESCE(f.wind_code, fsc.wind_code) AS wind_code,
                    COALESCE(f.name, fe.canonical_name) AS name,
                    COALESCE(f.type, fe.asset_class) AS type,
                    f.total_asset,
                    f.establishment_date,
                    f.performance_data,
                    f.risk_metrics,
                    f.raw_data,
                    fe.id AS entity_id,
                    fe.canonical_code,
                    fsc.share_class
                FROM peer_group_members pgm
                JOIN peer_groups pg ON pg.id = pgm.peer_group_id
                JOIN fund_entities fe ON fe.id = pgm.entity_id
                JOIN fund_share_classes fsc ON fsc.entity_id = fe.id AND fsc.status = 'active'
                JOIN funds f ON f.wind_code = fsc.wind_code
                WHERE pgm.peer_group_id = :peer_group_id
                  AND pgm.role <> 'excluded'
                  AND fe.lifecycle_stage = 'active'
                  AND ({active_fund_sql('f')})
                ORDER BY
                    fe.id,
                    CASE WHEN fsc.wind_code = :target_wind_code THEN 0 ELSE 1 END,
                    fsc.is_primary DESC,
                    fsc.wind_code ASC
            ) peer_funds
            ORDER BY wind_code ASC
            LIMIT :limit
        """
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(sql),
                {
                    "peer_group_id": normalized_group,
                    "target_wind_code": str(target_wind_code or "").strip(),
                    "limit": max(1, min(int(limit), 10000)),
                },
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def list_peer_period_nav_summaries(
        self,
        peer_group_id: str,
        start_date: Any,
        end_date: Any,
    ) -> List[Dict[str, Any]]:
        """返回同类基金实体在指定区间内净值覆盖最完整的代表份额。"""
        normalized_group = str(peer_group_id or "").strip()
        if not normalized_group or not start_date or not end_date or not self._schema_ready():
            return []

        from sqlalchemy import text

        sql = f"""
            WITH eligible_shares AS (
                SELECT
                    fe.id AS entity_id,
                    fsc.wind_code,
                    fsc.is_primary
                FROM peer_group_members pgm
                JOIN fund_entities fe ON fe.id = pgm.entity_id
                JOIN fund_share_classes fsc
                  ON fsc.entity_id = fe.id
                 AND fsc.status = 'active'
                JOIN funds fund_status ON fund_status.wind_code = fsc.wind_code
                WHERE pgm.peer_group_id = :peer_group_id
                  AND pgm.role <> 'excluded'
                  AND fe.lifecycle_stage = 'active'
                  AND ({active_fund_sql('fund_status')})
            ),
            share_nav AS (
                SELECT
                    share.entity_id,
                    share.wind_code,
                    share.is_primary,
                    nav.trade_date,
                    COALESCE(nav.accum_nav, nav.unit_nav, nav.nav) AS nav_value
                FROM eligible_shares share
                JOIN fund_nav nav ON nav.wind_code = share.wind_code
                WHERE nav.trade_date BETWEEN :start_date AND :end_date
                  AND COALESCE(nav.accum_nav, nav.unit_nav, nav.nav) > 0
            ),
            share_path AS (
                SELECT
                    share_nav.*,
                    LAG(nav_value) OVER (
                        PARTITION BY entity_id, wind_code
                        ORDER BY trade_date
                    ) AS previous_nav,
                    MAX(nav_value) OVER (
                        PARTITION BY entity_id, wind_code
                        ORDER BY trade_date
                        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                    ) AS running_peak,
                    MAX(nav_value) OVER (
                        PARTITION BY entity_id, wind_code
                        ORDER BY trade_date
                        ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                    ) AS previous_peak
                FROM share_nav
            ),
            share_period AS (
                SELECT
                    entity_id,
                    wind_code,
                    is_primary,
                    MIN(trade_date) AS first_date,
                    MAX(trade_date) AS last_date,
                    COUNT(*)::int AS observations,
                    (ARRAY_AGG(nav_value ORDER BY trade_date ASC))[1] AS first_nav,
                    (ARRAY_AGG(nav_value ORDER BY trade_date DESC))[1] AS last_nav,
                    AVG(
                        CASE WHEN previous_peak IS NULL OR nav_value > previous_peak THEN 1.0 ELSE 0.0 END
                    ) AS record_breaking_days_ratio,
                    MIN(nav_value / NULLIF(running_peak, 0) - 1) AS max_drawdown,
                    STDDEV_SAMP(
                        CASE WHEN previous_nav > 0 THEN nav_value / previous_nav - 1 END
                    ) * SQRT(252.0) AS annualized_volatility,
                    CASE
                        WHEN STDDEV_SAMP(
                            CASE WHEN previous_nav > 0 THEN nav_value / previous_nav - 1 END
                        ) > 0
                        THEN (
                            AVG(CASE WHEN previous_nav > 0 THEN nav_value / previous_nav - 1 END) * 252.0 - 0.02
                        ) / (
                            STDDEV_SAMP(CASE WHEN previous_nav > 0 THEN nav_value / previous_nav - 1 END) * SQRT(252.0)
                        )
                    END AS sharpe_ratio
                FROM share_path
                GROUP BY entity_id, wind_code, is_primary
            ),
            ranked_share AS (
                SELECT
                    share_period.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY entity_id
                        ORDER BY
                            (last_date - first_date) DESC,
                            observations DESC,
                            is_primary DESC,
                            wind_code ASC
                    ) AS share_rank
                FROM share_period
            )
            SELECT
                entity_id,
                wind_code,
                first_date,
                last_date,
                observations,
                first_nav,
                last_nav,
                record_breaking_days_ratio,
                max_drawdown,
                annualized_volatility,
                sharpe_ratio
            FROM ranked_share
            WHERE share_rank = 1
            ORDER BY wind_code ASC
        """
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), {
                "peer_group_id": normalized_group,
                "start_date": start_date,
                "end_date": end_date,
            }).fetchall()
        return [_row_to_dict(row) for row in rows]

    def list_peer_calendar_period_summaries(
        self,
        peer_group_id: str,
        start_date: Any,
        end_date: Any,
        baseline_start_date: Any,
    ) -> List[Dict[str, Any]]:
        """返回同类基金自然年度区间的期初、期末净值和覆盖证据。"""
        normalized_group = str(peer_group_id or "").strip()
        if (
            not normalized_group
            or not start_date
            or not end_date
            or not baseline_start_date
            or not self._schema_ready()
        ):
            return []

        from sqlalchemy import text

        sql = f"""
            WITH eligible_shares AS (
                SELECT
                    fe.id AS entity_id,
                    fsc.wind_code,
                    fsc.is_primary
                FROM peer_group_members pgm
                JOIN fund_entities fe ON fe.id = pgm.entity_id
                JOIN fund_share_classes fsc
                  ON fsc.entity_id = fe.id
                 AND fsc.status = 'active'
                JOIN funds fund_status ON fund_status.wind_code = fsc.wind_code
                WHERE pgm.peer_group_id = :peer_group_id
                  AND pgm.role <> 'excluded'
                  AND fe.lifecycle_stage = 'active'
                  AND ({active_fund_sql('fund_status')})
            ),
            share_coverage AS (
                SELECT
                    share.entity_id,
                    share.wind_code,
                    share.is_primary,
                    COUNT(*) FILTER (
                        WHERE nav.trade_date BETWEEN :start_date AND :end_date
                    )::int AS period_observations,
                    COUNT(*)::int AS total_observations,
                    COUNT(nav.accum_nav)::int AS accum_observations
                FROM eligible_shares share
                JOIN fund_nav nav ON nav.wind_code = share.wind_code
                WHERE nav.trade_date BETWEEN :baseline_start_date AND :end_date
                  AND COALESCE(nav.accum_nav, nav.unit_nav, nav.nav) > 0
                GROUP BY share.entity_id, share.wind_code, share.is_primary
                HAVING COUNT(*) FILTER (
                    WHERE nav.trade_date BETWEEN :start_date AND :end_date
                ) >= 2
            ),
            selected_shares AS (
                SELECT
                    entity_id,
                    wind_code,
                    CASE
                        WHEN accum_observations >= GREATEST(2, CEIL(total_observations * 0.9))
                        THEN 'accum_nav'
                        ELSE 'unit_nav'
                    END AS nav_basis
                FROM (
                    SELECT
                        share_coverage.*,
                        ROW_NUMBER() OVER (
                            PARTITION BY entity_id
                            ORDER BY
                                period_observations DESC,
                                total_observations DESC,
                                is_primary DESC,
                                wind_code ASC
                        ) AS share_rank
                    FROM share_coverage
                ) ranked
                WHERE share_rank = 1
            ),
            nav_points AS (
                SELECT
                    selected.entity_id,
                    selected.wind_code,
                    selected.nav_basis,
                    nav.trade_date,
                    CASE
                        WHEN selected.nav_basis = 'accum_nav' THEN nav.accum_nav
                        ELSE COALESCE(nav.unit_nav, nav.nav)
                    END AS nav_value
                FROM selected_shares selected
                JOIN fund_nav nav ON nav.wind_code = selected.wind_code
                WHERE nav.trade_date BETWEEN :baseline_start_date AND :end_date
            )
            SELECT
                entity_id,
                wind_code,
                nav_basis,
                (ARRAY_AGG(trade_date ORDER BY trade_date DESC)
                    FILTER (WHERE trade_date < :start_date AND nav_value > 0))[1] AS baseline_date,
                (ARRAY_AGG(nav_value ORDER BY trade_date DESC)
                    FILTER (WHERE trade_date < :start_date AND nav_value > 0))[1] AS baseline_nav,
                (ARRAY_AGG(trade_date ORDER BY trade_date ASC)
                    FILTER (WHERE trade_date BETWEEN :start_date AND :end_date AND nav_value > 0))[1] AS first_date,
                (ARRAY_AGG(nav_value ORDER BY trade_date ASC)
                    FILTER (WHERE trade_date BETWEEN :start_date AND :end_date AND nav_value > 0))[1] AS first_nav,
                (ARRAY_AGG(trade_date ORDER BY trade_date DESC)
                    FILTER (WHERE trade_date BETWEEN :start_date AND :end_date AND nav_value > 0))[1] AS last_date,
                (ARRAY_AGG(nav_value ORDER BY trade_date DESC)
                    FILTER (WHERE trade_date BETWEEN :start_date AND :end_date AND nav_value > 0))[1] AS last_nav,
                COUNT(*) FILTER (
                    WHERE trade_date BETWEEN :start_date AND :end_date AND nav_value > 0
                )::int AS observations
            FROM nav_points
            GROUP BY entity_id, wind_code, nav_basis
            ORDER BY wind_code ASC
        """
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), {
                "peer_group_id": normalized_group,
                "start_date": start_date,
                "end_date": end_date,
                "baseline_start_date": baseline_start_date,
            }).fetchall()
        return [_row_to_dict(row) for row in rows]

    def list_peer_nav_series(
        self,
        peer_group_id: str,
        start_date: Any,
        end_date: Any,
    ) -> List[Dict[str, Any]]:
        """返回同类组每个基金实体净值覆盖最完整的代表份额日序列。"""
        normalized_group = str(peer_group_id or "").strip()
        if not normalized_group or not start_date or not end_date or not self._schema_ready():
            return []

        from sqlalchemy import text

        sql = f"""
            WITH eligible_shares AS (
                SELECT
                    fe.id AS entity_id,
                    fsc.wind_code,
                    fsc.is_primary
                FROM peer_group_members pgm
                JOIN fund_entities fe ON fe.id = pgm.entity_id
                JOIN fund_share_classes fsc
                  ON fsc.entity_id = fe.id
                 AND fsc.status = 'active'
                JOIN funds fund_status ON fund_status.wind_code = fsc.wind_code
                WHERE pgm.peer_group_id = :peer_group_id
                  AND pgm.role <> 'excluded'
                  AND fe.lifecycle_stage = 'active'
                  AND ({active_fund_sql('fund_status')})
            ),
            share_coverage AS (
                SELECT
                    share.entity_id,
                    share.wind_code,
                    share.is_primary,
                    COUNT(nav.*)::int AS observations,
                    MIN(nav.trade_date) AS first_date,
                    MAX(nav.trade_date) AS last_date
                FROM eligible_shares share
                JOIN fund_nav nav ON nav.wind_code = share.wind_code
                WHERE nav.trade_date BETWEEN :start_date AND :end_date
                  AND COALESCE(nav.accum_nav, nav.unit_nav, nav.nav) > 0
                GROUP BY share.entity_id, share.wind_code, share.is_primary
            ),
            selected_shares AS (
                SELECT entity_id, wind_code
                FROM (
                    SELECT
                        share_coverage.*,
                        ROW_NUMBER() OVER (
                            PARTITION BY entity_id
                            ORDER BY observations DESC, is_primary DESC, wind_code ASC
                        ) AS share_rank
                    FROM share_coverage
                ) ranked
                WHERE share_rank = 1
            )
            SELECT
                selected.entity_id,
                selected.wind_code,
                nav.trade_date,
                nav.unit_nav,
                nav.nav,
                nav.accum_nav
            FROM selected_shares selected
            JOIN fund_nav nav ON nav.wind_code = selected.wind_code
            WHERE nav.trade_date BETWEEN :start_date AND :end_date
              AND COALESCE(nav.accum_nav, nav.unit_nav, nav.nav) > 0
            ORDER BY selected.wind_code, nav.trade_date
        """
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), {
                "peer_group_id": normalized_group,
                "start_date": start_date,
                "end_date": end_date,
            }).fetchall()
        return [_row_to_dict(row) for row in rows]

    def list_peer_group_inventory(self, limit: int = 100) -> List[Dict[str, Any]]:
        """返回标准化同类组及可评价覆盖，供普通用户选择类别。"""
        if not self._schema_ready():
            return []

        from sqlalchemy import text

        evaluation_ready_sql = self._recommendation_evaluation_ready_sql(
            "f",
            "sf.key",
            "evaluation_metrics",
        )
        sql = f"""
            WITH latest_metric_values AS (
                SELECT DISTINCT ON (target_id, metric_window, metric_name)
                    target_id,
                    metric_window,
                    metric_name,
                    metric_value,
                    as_of_date
                FROM metric_snapshots
                WHERE target_type = 'fund'
                ORDER BY
                    target_id,
                    metric_window,
                    metric_name,
                    as_of_date DESC,
                    updated_at DESC
            ),
            evaluation_metrics AS (
                SELECT
                    target_id,
                    MAX(metric_value) FILTER (
                        WHERE metric_window = '1y' AND metric_name = 'annualized_return'
                    ) AS annualized_return_1y,
                    MAX(metric_value) FILTER (
                        WHERE metric_window = '1y' AND metric_name = 'max_drawdown'
                    ) AS max_drawdown_1y,
                    MAX(metric_value) FILTER (
                        WHERE metric_window = '1y' AND metric_name = 'sharpe_ratio'
                    ) AS sharpe_ratio_1y,
                    MAX(metric_value) FILTER (
                        WHERE metric_window = '1y' AND metric_name = 'tracking_error'
                    ) AS tracking_error_1y,
                    MAX(metric_value) FILTER (
                        WHERE metric_window = '1y' AND metric_name = 'tracking_difference'
                    ) AS tracking_difference_1y,
                    MAX(metric_value) FILTER (
                        WHERE metric_window = '1y' AND metric_name = 'excess_return'
                    ) AS excess_return_1y,
                    MAX(metric_value) FILTER (
                        WHERE metric_window = '1y' AND metric_name = 'information_ratio'
                    ) AS information_ratio_1y,
                    MAX(metric_value) FILTER (
                        WHERE metric_window = 'latest' AND metric_name = 'expense_ratio'
                    ) AS expense_ratio,
                    MAX(metric_value) FILTER (
                        WHERE metric_window = 'latest' AND metric_name = 'aum'
                    ) AS aum,
                    MAX(metric_value) FILTER (
                        WHERE metric_window = 'latest' AND metric_name = 'seven_day_annualized_yield'
                    ) AS seven_day_annualized_yield,
                    MAX(as_of_date) AS evaluation_as_of_date
                FROM latest_metric_values
                GROUP BY target_id
            ),
            candidate_funds AS (
                SELECT
                    pg.id AS peer_group_id,
                    pg.key AS peer_group_key,
                    pg.name AS peer_group_name,
                    pg.asset_class,
                    pg.active_passive,
                    pg.benchmark_code,
                    pg.benchmark_name,
                    pg.inclusion_rules,
                    pg.minimum_peer_count,
                    sf.key AS strategy_family_key,
                    sf.name AS strategy_family_name,
                    fe.id AS entity_id,
                    f.wind_code,
                    fsc.is_primary,
                    f.nav_date,
                    COALESCE(evaluation_metrics.evaluation_as_of_date, f.nav_date) AS evaluation_as_of_date,
                    ({evaluation_ready_sql}) AS evaluation_ready
                FROM peer_groups pg
                JOIN peer_group_members pgm
                  ON pgm.peer_group_id = pg.id
                 AND pgm.role <> 'excluded'
                JOIN fund_entities fe
                  ON fe.id = pgm.entity_id
                 AND fe.lifecycle_stage = 'active'
                LEFT JOIN strategy_families sf ON sf.id = fe.strategy_family_id
                JOIN fund_share_classes fsc
                  ON fsc.entity_id = fe.id
                 AND fsc.status = 'active'
                JOIN funds f ON f.wind_code = fsc.wind_code
                LEFT JOIN evaluation_metrics ON evaluation_metrics.target_id = f.wind_code
                WHERE {active_fund_sql('f')}
            ),
            representative_funds AS (
                SELECT DISTINCT ON (peer_group_id, entity_id)
                    *
                FROM candidate_funds
                ORDER BY
                    peer_group_id,
                    entity_id,
                    evaluation_ready DESC NULLS LAST,
                    is_primary DESC,
                    evaluation_as_of_date DESC NULLS LAST,
                    nav_date DESC NULLS LAST,
                    wind_code ASC
            )
            SELECT
                peer_group_id AS id,
                peer_group_key AS key,
                peer_group_name AS name,
                asset_class,
                active_passive,
                benchmark_code,
                benchmark_name,
                inclusion_rules,
                inclusion_rules -> 'contractDimensions' AS contract_dimensions,
                strategy_family_key,
                strategy_family_name,
                minimum_peer_count,
                COUNT(*)::int AS fund_count,
                COUNT(*) FILTER (WHERE evaluation_ready)::int AS evaluated_fund_count,
                COUNT(*) FILTER (WHERE evaluation_ready IS NOT TRUE)::int AS evaluation_pending_count,
                ROUND(
                    COUNT(*) FILTER (WHERE evaluation_ready)::numeric / NULLIF(COUNT(*), 0),
                    4
                ) AS evaluation_coverage,
                MAX(evaluation_as_of_date) FILTER (WHERE evaluation_ready) AS evaluation_as_of_date
            FROM representative_funds
            GROUP BY
                peer_group_id,
                peer_group_key,
                peer_group_name,
                asset_class,
                active_passive,
                benchmark_code,
                benchmark_name,
                inclusion_rules,
                strategy_family_key,
                strategy_family_name,
                minimum_peer_count
            HAVING COUNT(*) >= minimum_peer_count
            ORDER BY fund_count DESC, peer_group_name ASC
            LIMIT :limit
        """
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), {"limit": max(1, min(int(limit), 200))}).fetchall()
        return [_row_to_dict(row) for row in rows]

    def list_peer_group_coverage_inventory(self, limit: int = 100) -> List[Dict[str, Any]]:
        """返回全部标准同类组及真实入库覆盖，不过滤未达最小样本的类别。"""
        if not self._schema_ready():
            return []

        from sqlalchemy import text

        sql = f"""
            SELECT
                pg.id,
                pg.key,
                pg.name,
                pg.minimum_peer_count,
                COUNT(DISTINCT fe.id) FILTER (
                    WHERE pgm.role <> 'excluded'
                      AND fe.lifecycle_stage = 'active'
                      AND fsc.status = 'active'
                      AND f.wind_code IS NOT NULL
                      AND ({active_fund_sql('f')})
                )::int AS classified_count,
                COUNT(DISTINCT fe.id) FILTER (
                    WHERE pgm.role <> 'excluded'
                      AND fe.lifecycle_stage = 'active'
                      AND fsc.status = 'active'
                      AND f.wind_code IS NOT NULL
                      AND ({active_fund_sql('f')})
                )::int AS database_fund_count
            FROM peer_groups pg
            LEFT JOIN peer_group_members pgm ON pgm.peer_group_id = pg.id
            LEFT JOIN fund_entities fe ON fe.id = pgm.entity_id
            LEFT JOIN fund_share_classes fsc ON fsc.entity_id = fe.id
            LEFT JOIN funds f ON f.wind_code = fsc.wind_code
            GROUP BY pg.id, pg.key, pg.name, pg.minimum_peer_count
            ORDER BY classified_count DESC, pg.name ASC
            LIMIT :limit
        """
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), {"limit": max(1, min(int(limit), 200))}).fetchall()
        return [_row_to_dict(row) for row in rows]

    def list_recommendation_coverage_summary(self, limit: int = 100) -> List[Dict[str, Any]]:
        """一次聚合同类组评价与真实持仓风格覆盖，供首页和覆盖审计使用。"""
        if not self._schema_ready():
            return []

        from sqlalchemy import text

        evaluation_ready_sql = self._recommendation_evaluation_ready_sql(
            "f",
            "sf.key",
            "evaluation_metrics",
        )
        sql = f"""
            WITH latest_metric_values AS (
                SELECT DISTINCT ON (target_id, metric_window, metric_name)
                    target_id, metric_window, metric_name, metric_value, as_of_date
                FROM metric_snapshots
                WHERE target_type = 'fund'
                ORDER BY target_id, metric_window, metric_name, as_of_date DESC, updated_at DESC
            ),
            evaluation_metrics AS (
                SELECT
                    target_id,
                    MAX(metric_value) FILTER (WHERE metric_window = '1y' AND metric_name = 'annualized_return') AS annualized_return_1y,
                    MAX(metric_value) FILTER (WHERE metric_window = '1y' AND metric_name = 'max_drawdown') AS max_drawdown_1y,
                    MAX(metric_value) FILTER (WHERE metric_window = '1y' AND metric_name = 'sharpe_ratio') AS sharpe_ratio_1y,
                    MAX(metric_value) FILTER (WHERE metric_window = '1y' AND metric_name = 'tracking_error') AS tracking_error_1y,
                    MAX(metric_value) FILTER (WHERE metric_window = '1y' AND metric_name = 'tracking_difference') AS tracking_difference_1y,
                    MAX(metric_value) FILTER (WHERE metric_window = '1y' AND metric_name = 'excess_return') AS excess_return_1y,
                    MAX(metric_value) FILTER (WHERE metric_window = '1y' AND metric_name = 'information_ratio') AS information_ratio_1y,
                    MAX(metric_value) FILTER (WHERE metric_window = 'latest' AND metric_name = 'expense_ratio') AS expense_ratio,
                    MAX(metric_value) FILTER (WHERE metric_window = 'latest' AND metric_name = 'aum') AS aum,
                    MAX(metric_value) FILTER (WHERE metric_window = 'latest' AND metric_name = 'seven_day_annualized_yield') AS seven_day_annualized_yield
                FROM latest_metric_values
                GROUP BY target_id
            ),
            holding_style_entities AS (
                SELECT DISTINCT fsc.entity_id
                FROM holding_style_snapshots snapshot
                JOIN fund_share_classes fsc ON fsc.wind_code = snapshot.wind_code
                WHERE fsc.status = 'active'
                  AND snapshot.status = 'peer_percentile_ready'
                  AND COALESCE(cardinality(snapshot.style_labels), 0) > 0
            ),
            bond_style_funds AS (
                SELECT wind_code
                FROM fund_bond_holdings
                GROUP BY wind_code
                HAVING COUNT(DISTINCT report_date) >= 4
                   AND COALESCE(
                        SUM(nav_ratio) FILTER (WHERE bond_type <> 'other')
                        / NULLIF(SUM(nav_ratio), 0),
                        0
                   ) >= 0.8
            ),
            fof_latest_period AS (
                SELECT DISTINCT ON (wind_code)
                    wind_code, report_date
                FROM fund_underlying_holdings
                ORDER BY wind_code, report_date DESC
            ),
            fof_style_funds AS (
                SELECT holding.wind_code
                FROM fund_underlying_holdings holding
                JOIN fof_latest_period latest
                  ON latest.wind_code = holding.wind_code
                 AND latest.report_date = holding.report_date
                GROUP BY holding.wind_code
                HAVING COUNT(*) >= 5 AND COALESCE(SUM(holding.nav_ratio), 0) >= 20
            ),
            style_ready_entities AS (
                SELECT entity_id FROM holding_style_entities
                UNION
                SELECT fsc.entity_id
                FROM fund_share_classes fsc
                JOIN bond_style_funds bond ON bond.wind_code = fsc.wind_code
                WHERE fsc.status = 'active'
                UNION
                SELECT fsc.entity_id
                FROM fund_share_classes fsc
                JOIN fof_style_funds fof ON fof.wind_code = fsc.wind_code
                WHERE fsc.status = 'active'
            ),
            candidate_funds AS (
                SELECT
                    pg.id AS peer_group_id,
                    pg.key AS peer_group_key,
                    pg.name AS peer_group_name,
                    pg.minimum_peer_count,
                    fe.id AS entity_id,
                    f.wind_code,
                    fsc.is_primary,
                    f.nav_date,
                    ({evaluation_ready_sql}) AS evaluation_ready,
                    (holding_style.entity_id IS NOT NULL) AS style_ready
                FROM peer_groups pg
                JOIN peer_group_members pgm
                  ON pgm.peer_group_id = pg.id
                 AND pgm.role <> 'excluded'
                JOIN fund_entities fe
                  ON fe.id = pgm.entity_id
                 AND fe.lifecycle_stage = 'active'
                LEFT JOIN strategy_families sf ON sf.id = fe.strategy_family_id
                JOIN fund_share_classes fsc
                  ON fsc.entity_id = fe.id
                 AND fsc.status = 'active'
                JOIN funds f ON f.wind_code = fsc.wind_code
                LEFT JOIN evaluation_metrics ON evaluation_metrics.target_id = f.wind_code
                LEFT JOIN style_ready_entities holding_style ON holding_style.entity_id = fe.id
                WHERE {active_fund_sql('f')}
            ),
            representative_funds AS (
                SELECT DISTINCT ON (peer_group_id, entity_id) *
                FROM candidate_funds
                ORDER BY
                    peer_group_id,
                    entity_id,
                    evaluation_ready DESC NULLS LAST,
                    is_primary DESC,
                    nav_date DESC NULLS LAST,
                    wind_code ASC
            )
            SELECT
                peer_group_id AS id,
                peer_group_key AS key,
                peer_group_name AS name,
                minimum_peer_count,
                COUNT(*)::int AS database_fund_count,
                COUNT(*) FILTER (WHERE evaluation_ready)::int AS evaluated_fund_count,
                COUNT(*) FILTER (WHERE style_ready)::int AS style_ready_count
            FROM representative_funds
            GROUP BY peer_group_id, peer_group_key, peer_group_name, minimum_peer_count
            ORDER BY database_fund_count DESC, peer_group_name ASC
            LIMIT :limit
        """
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), {"limit": max(1, min(int(limit), 200))}).fetchall()
        return [_row_to_dict(row) for row in rows]

    def list_fund_peer_group_map(self, wind_codes: List[str]) -> Dict[str, Dict[str, Any]]:
        """批量返回基金份额的标准同类组，避免列表页逐只查询分类上下文。"""
        normalized_codes = list(dict.fromkeys(
            str(code or "").strip() for code in wind_codes if str(code or "").strip()
        ))
        if not normalized_codes or not self._schema_ready():
            return {}

        from sqlalchemy import text

        sql = f"""
            WITH requested_codes AS (
                SELECT UNNEST(CAST(:wind_codes AS TEXT[])) AS requested_code
            )
            SELECT DISTINCT ON (requested.requested_code)
                requested.requested_code AS lookup_code,
                fsc.wind_code,
                pg.id AS peer_group_id,
                pg.key AS peer_group_key,
                pg.name AS peer_group_name,
                pg.minimum_peer_count,
                pgm.confidence,
                pgm.source,
                pgm.sample_as_of_date,
                sf.key AS strategy_family_key,
                sf.name AS strategy_family_name,
                COALESCE(fe.asset_class, sf.asset_class) AS asset_class,
                COALESCE(fe.active_passive, sf.active_passive) AS active_passive
            FROM requested_codes requested
            JOIN fund_share_classes fsc
              ON fsc.wind_code = requested.requested_code
              OR SPLIT_PART(fsc.wind_code, '.', 1) = SPLIT_PART(requested.requested_code, '.', 1)
            JOIN fund_entities fe ON fe.id = fsc.entity_id
            JOIN funds fund_status ON fund_status.wind_code = fsc.wind_code
            LEFT JOIN strategy_families sf ON sf.id = fe.strategy_family_id
            LEFT JOIN peer_group_members pgm
              ON pgm.entity_id = fe.id
             AND pgm.role <> 'excluded'
            LEFT JOIN peer_groups pg ON pg.id = pgm.peer_group_id
            WHERE fsc.status = 'active'
              AND fe.lifecycle_stage = 'active'
              AND ({active_fund_sql('fund_status')})
            ORDER BY
                requested.requested_code,
                CASE WHEN fsc.wind_code = requested.requested_code THEN 0 ELSE 1 END,
                fsc.is_primary DESC,
                CASE pgm.role WHEN 'primary' THEN 0 WHEN 'target' THEN 1 ELSE 2 END,
                pgm.sample_as_of_date DESC NULLS LAST,
                pgm.confidence DESC NULLS LAST,
                pg.updated_at DESC NULLS LAST
        """
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), {"wind_codes": normalized_codes}).fetchall()
        return {
            row["lookup_code"]: row
            for item in rows
            if (row := _row_to_dict(item)).get("lookup_code") and row.get("peer_group_id")
        }

    def list_fund_identity_map(self, wind_codes: List[str]) -> Dict[str, Dict[str, Any]]:
        """按完整代码或六位代码返回基金登记类型，兼容交易所基金代码后缀。"""
        normalized_codes = list(dict.fromkeys(
            str(code or "").strip().upper()
            for code in wind_codes
            if str(code or "").strip()
        ))
        if not normalized_codes:
            return {}

        from sqlalchemy import text

        sql = """
            WITH requested_codes AS (
                SELECT UNNEST(CAST(:wind_codes AS TEXT[])) AS requested_code
            )
            SELECT
                requested.requested_code AS lookup_code,
                matched.wind_code,
                matched.fund_name,
                matched.registered_fund_type,
                matched.contract_type,
                matched.invest_type,
                matched.raw_fund_type,
                matched.identity_source
            FROM requested_codes requested
            JOIN LATERAL (
                SELECT
                    fund.wind_code,
                    fund.name AS fund_name,
                    fund.type AS registered_fund_type,
                    COALESCE(
                        NULLIF(fund.raw_data #>> '{universe,contract_type}', ''),
                        NULLIF(fund.raw_data #>> '{info,contract_type}', ''),
                        NULLIF(fund.raw_data ->> 'contract_type', '')
                    ) AS contract_type,
                    COALESCE(
                        NULLIF(fund.raw_data #>> '{universe,invest_type}', ''),
                        NULLIF(fund.raw_data #>> '{info,invest_type}', ''),
                        NULLIF(fund.raw_data ->> 'invest_type', '')
                    ) AS invest_type,
                    COALESCE(
                        NULLIF(fund.raw_data #>> '{universe,fund_type_raw}', ''),
                        NULLIF(fund.raw_data #>> '{info,fund_type_raw}', ''),
                        NULLIF(fund.raw_data ->> 'fund_type_raw', '')
                    ) AS raw_fund_type,
                    COALESCE(NULLIF(fund.raw_data ->> 'source', ''), 'funds') AS identity_source
                FROM funds fund
                WHERE UPPER(fund.wind_code) = requested.requested_code
                   OR SPLIT_PART(UPPER(fund.wind_code), '.', 1)
                      = SPLIT_PART(requested.requested_code, '.', 1)
                ORDER BY
                    CASE WHEN UPPER(fund.wind_code) = requested.requested_code THEN 0 ELSE 1 END,
                    fund.updated_at DESC NULLS LAST,
                    fund.wind_code ASC
                LIMIT 1
            ) matched ON TRUE
        """
        with self.engine.connect() as conn:
            rows = conn.execute(text(sql), {"wind_codes": normalized_codes}).fetchall()
        return {
            row["lookup_code"]: row
            for item in rows
            if (row := _row_to_dict(item)).get("lookup_code")
        }

    def list_recommendation_funds(
        self,
        peer_group: str,
        limit: int = 50,
        keyword: Optional[str] = None,
        offset: int = 0,
        asset_min: Optional[float] = None,
        min_age_years: Optional[int] = None,
        min_manager_years: Optional[float] = None,
        return_6m_min: Optional[float] = None,
        return_1y_min: Optional[float] = None,
        return_3y_min: Optional[float] = None,
        max_drawdown_1y_max: Optional[float] = None,
        sharpe_1y_min: Optional[float] = None,
        style_tags: Optional[List[str]] = None,
        style_match: str = "any",
        sort_by: str = "quality",
        availability: str = "classified",
    ) -> List[Dict[str, Any]]:
        """按标准化同类组返回每个基金实体的代表份额及完整基础数据。"""
        normalized_group = str(peer_group or "").strip()
        if not normalized_group or not self._schema_ready():
            return []

        from sqlalchemy import text

        filter_sql, filter_params = self._recommendation_filter_sql(
            keyword=keyword,
            asset_min=asset_min,
            min_age_years=min_age_years,
            min_manager_years=min_manager_years,
            return_6m_min=return_6m_min,
            return_1y_min=return_1y_min,
            return_3y_min=return_3y_min,
            max_drawdown_1y_max=max_drawdown_1y_max,
            sharpe_1y_min=sharpe_1y_min,
            style_tags=style_tags,
            style_match=style_match,
            availability=availability,
        )
        sort_sql = self._recommendation_sort_sql(sort_by)
        ranked_metrics = self._recommendation_metric_expressions("representative_funds")
        evaluation_ready_sql = self._recommendation_evaluation_ready_sql("f", "sf.key", "evaluation_metrics")
        sql = f"""
            WITH representative_funds AS (
                SELECT DISTINCT ON (fe.id)
                    f.*,
                    fe.id AS entity_id,
                    fe.canonical_code,
                    fe.canonical_name,
                    sf.key AS strategy_family_key,
                    sf.name AS strategy_family_name,
                    COALESCE(fe.asset_class, sf.asset_class) AS asset_class,
                    COALESCE(fe.active_passive, sf.active_passive) AS active_passive,
                    pg.id AS standardized_peer_group_id,
                    pg.key AS standardized_peer_group_key,
                    pg.name AS standardized_peer_group_name,
                    pg.minimum_peer_count,
                    pg.benchmark_code,
                    pg.benchmark_name,
                    sf.style_tags AS classification_style_tags,
                    {self._memo_style_tags_sql()} AS memo_style_tags,
                    {self._holding_style_tags_sql()} AS holding_style_tags,
                    {self._verified_style_tags_sql()} AS verified_style_tags,
                    research_profile.updated_at AS memo_style_as_of,
                    holding_style.quarter AS holding_style_as_of,
                    holding_style.source AS holding_style_source,
                    ({evaluation_ready_sql}) AS evaluation_ready
                FROM peer_groups pg
                JOIN peer_group_members pgm ON pgm.peer_group_id = pg.id
                JOIN fund_entities fe ON fe.id = pgm.entity_id
                LEFT JOIN strategy_families sf ON sf.id = fe.strategy_family_id
                JOIN fund_share_classes fsc ON fsc.entity_id = fe.id AND fsc.status = 'active'
                JOIN funds f ON f.wind_code = fsc.wind_code
                {self._style_evidence_join_sql()}
                LEFT JOIN LATERAL (
                    SELECT
                        MAX(metric_value) FILTER (WHERE metric_window = '1y' AND metric_name = 'annualized_return') AS annualized_return_1y,
                        MAX(metric_value) FILTER (WHERE metric_window = '1y' AND metric_name = 'max_drawdown') AS max_drawdown_1y,
                        MAX(metric_value) FILTER (WHERE metric_window = '1y' AND metric_name = 'sharpe_ratio') AS sharpe_ratio_1y,
                        MAX(metric_value) FILTER (WHERE metric_window = '1y' AND metric_name = 'tracking_error') AS tracking_error_1y,
                        MAX(metric_value) FILTER (WHERE metric_window = '1y' AND metric_name = 'tracking_difference') AS tracking_difference_1y,
                        MAX(metric_value) FILTER (WHERE metric_window = '1y' AND metric_name = 'excess_return') AS excess_return_1y,
                        MAX(metric_value) FILTER (WHERE metric_window = '1y' AND metric_name = 'information_ratio') AS information_ratio_1y,
                        MAX(metric_value) FILTER (WHERE metric_window = 'latest' AND metric_name = 'expense_ratio') AS expense_ratio,
                        MAX(metric_value) FILTER (WHERE metric_window = 'latest' AND metric_name = 'aum') AS aum,
                        MAX(metric_value) FILTER (WHERE metric_window = 'latest' AND metric_name = 'seven_day_annualized_yield') AS seven_day_annualized_yield
                    FROM (
                        SELECT DISTINCT ON (metric_window, metric_name)
                            metric_window, metric_name, metric_value
                        FROM metric_snapshots
                        WHERE target_type = 'fund'
                          AND target_id = f.wind_code
                        ORDER BY metric_window, metric_name, as_of_date DESC, updated_at DESC
                    ) latest_metrics
                ) evaluation_metrics ON TRUE
                WHERE (pg.name = :peer_group OR pg.key = :peer_group)
                  AND pgm.role <> 'excluded'
                  AND fe.lifecycle_stage = 'active'
                  AND ({active_fund_sql('f')})
                ORDER BY
                    fe.id,
                    evaluation_ready DESC NULLS LAST,
                    fsc.is_primary DESC,
                    CASE WHEN f.performance_data IS NULL OR f.performance_data = '{{}}'::jsonb THEN 1 ELSE 0 END,
                    CASE WHEN f.risk_metrics IS NULL OR f.risk_metrics = '{{}}'::jsonb THEN 1 ELSE 0 END,
                    f.nav_date DESC NULLS LAST,
                    fsc.wind_code ASC
            ),
            metric_funds AS (
                SELECT
                    representative_funds.*,
                    {ranked_metrics['return_6m']} AS return_6m_metric,
                    {ranked_metrics['return_1y']} AS return_1y_metric,
                    {ranked_metrics['return_3y']} AS return_3y_metric
                FROM representative_funds
            ),
            ranked_funds AS (
                SELECT
                    metric_funds.*,
                    {self._peer_return_rank_sql('return_6m_metric', '6m')},
                    {self._peer_return_rank_sql('return_1y_metric', '1y')},
                    {self._peer_return_rank_sql('return_3y_metric', '3y')}
                FROM metric_funds
            )
            SELECT *
            FROM ranked_funds peer_funds
            WHERE {filter_sql}
            ORDER BY
                {sort_sql},
                peer_funds.wind_code ASC
            LIMIT :limit OFFSET :offset
        """
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(sql),
                {
                    "peer_group": normalized_group,
                    "limit": max(1, min(int(limit), 10000)),
                    "offset": max(0, int(offset)),
                    **filter_params,
                },
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    def count_recommendation_funds(
        self,
        peer_group: str,
        keyword: Optional[str] = None,
        asset_min: Optional[float] = None,
        min_age_years: Optional[int] = None,
        min_manager_years: Optional[float] = None,
        return_6m_min: Optional[float] = None,
        return_1y_min: Optional[float] = None,
        return_3y_min: Optional[float] = None,
        max_drawdown_1y_max: Optional[float] = None,
        sharpe_1y_min: Optional[float] = None,
        style_tags: Optional[List[str]] = None,
        style_match: str = "any",
        availability: str = "classified",
    ) -> int:
        """统计同类组可浏览的基金实体数，与候选列表使用相同过滤口径。"""
        normalized_group = str(peer_group or "").strip()
        if not normalized_group or not self._schema_ready():
            return 0

        from sqlalchemy import text

        filter_sql, filter_params = self._recommendation_filter_sql(
            keyword=keyword,
            asset_min=asset_min,
            min_age_years=min_age_years,
            min_manager_years=min_manager_years,
            return_6m_min=return_6m_min,
            return_1y_min=return_1y_min,
            return_3y_min=return_3y_min,
            max_drawdown_1y_max=max_drawdown_1y_max,
            sharpe_1y_min=sharpe_1y_min,
            style_tags=style_tags,
            style_match=style_match,
            availability=availability,
        )
        evaluation_ready_sql = self._recommendation_evaluation_ready_sql("f", "sf.key", "evaluation_metrics")
        sql = f"""
            WITH representative_funds AS (
                SELECT DISTINCT ON (fe.id)
                    f.*,
                    sf.key AS strategy_family_key,
                    {self._verified_style_tags_sql()} AS verified_style_tags,
                    ({evaluation_ready_sql}) AS evaluation_ready
                FROM peer_groups pg
                JOIN peer_group_members pgm ON pgm.peer_group_id = pg.id
                JOIN fund_entities fe ON fe.id = pgm.entity_id
                LEFT JOIN strategy_families sf ON sf.id = fe.strategy_family_id
                JOIN fund_share_classes fsc ON fsc.entity_id = fe.id AND fsc.status = 'active'
                JOIN funds f ON f.wind_code = fsc.wind_code
                {self._style_evidence_join_sql()}
                LEFT JOIN LATERAL (
                    SELECT
                        MAX(metric_value) FILTER (WHERE metric_window = '1y' AND metric_name = 'annualized_return') AS annualized_return_1y,
                        MAX(metric_value) FILTER (WHERE metric_window = '1y' AND metric_name = 'max_drawdown') AS max_drawdown_1y,
                        MAX(metric_value) FILTER (WHERE metric_window = '1y' AND metric_name = 'sharpe_ratio') AS sharpe_ratio_1y,
                        MAX(metric_value) FILTER (WHERE metric_window = '1y' AND metric_name = 'tracking_error') AS tracking_error_1y,
                        MAX(metric_value) FILTER (WHERE metric_window = '1y' AND metric_name = 'tracking_difference') AS tracking_difference_1y,
                        MAX(metric_value) FILTER (WHERE metric_window = '1y' AND metric_name = 'excess_return') AS excess_return_1y,
                        MAX(metric_value) FILTER (WHERE metric_window = '1y' AND metric_name = 'information_ratio') AS information_ratio_1y,
                        MAX(metric_value) FILTER (WHERE metric_window = 'latest' AND metric_name = 'expense_ratio') AS expense_ratio,
                        MAX(metric_value) FILTER (WHERE metric_window = 'latest' AND metric_name = 'aum') AS aum,
                        MAX(metric_value) FILTER (WHERE metric_window = 'latest' AND metric_name = 'seven_day_annualized_yield') AS seven_day_annualized_yield
                    FROM (
                        SELECT DISTINCT ON (metric_window, metric_name)
                            metric_window, metric_name, metric_value
                        FROM metric_snapshots
                        WHERE target_type = 'fund'
                          AND target_id = f.wind_code
                        ORDER BY metric_window, metric_name, as_of_date DESC, updated_at DESC
                    ) latest_metrics
                ) evaluation_metrics ON TRUE
                WHERE (pg.name = :peer_group OR pg.key = :peer_group)
                  AND pgm.role <> 'excluded'
                  AND fe.lifecycle_stage = 'active'
                  AND ({active_fund_sql('f')})
                ORDER BY
                    fe.id,
                    evaluation_ready DESC NULLS LAST,
                    fsc.is_primary DESC,
                    CASE WHEN f.performance_data IS NULL OR f.performance_data = '{{}}'::jsonb THEN 1 ELSE 0 END,
                    CASE WHEN f.risk_metrics IS NULL OR f.risk_metrics = '{{}}'::jsonb THEN 1 ELSE 0 END,
                    f.nav_date DESC NULLS LAST,
                    fsc.wind_code ASC
            )
            SELECT COUNT(*)::int AS fund_count
            FROM representative_funds peer_funds
            WHERE {filter_sql}
        """
        with self.engine.connect() as conn:
            value = conn.execute(text(sql), {
                "peer_group": normalized_group,
                **filter_params,
            }).scalar()
        return int(value or 0)

    def get_style_tag_catalog(
        self,
        peer_group: str,
        availability: str = "classified",
    ) -> Dict[str, Any]:
        """返回同类组内可筛选标签、基金数量和证据来源覆盖。"""
        normalized_group = str(peer_group or "").strip()
        if not normalized_group or not self._schema_ready():
            return self.empty_style_tag_catalog(normalized_group)

        from sqlalchemy import text

        normalized_availability = str(availability or "classified").strip().lower()
        if normalized_availability not in {"evaluated", "classified", "all"}:
            normalized_availability = "classified"
        evaluation_ready_sql = self._recommendation_evaluation_ready_sql("f", "sf.key", "evaluation_metrics")
        sql = f"""
            WITH representative_funds AS (
                SELECT DISTINCT ON (fe.id)
                    fe.id AS entity_id,
                    f.wind_code,
                    COALESCE(sf.style_tags, ARRAY[]::TEXT[]) AS classification_style_tags,
                    {self._memo_style_tags_sql()} AS memo_style_tags,
                    {self._holding_style_tags_sql()} AS holding_style_tags,
                    ({evaluation_ready_sql}) AS evaluation_ready
                FROM peer_groups pg
                JOIN peer_group_members pgm ON pgm.peer_group_id = pg.id
                JOIN fund_entities fe ON fe.id = pgm.entity_id
                LEFT JOIN strategy_families sf ON sf.id = fe.strategy_family_id
                JOIN fund_share_classes fsc ON fsc.entity_id = fe.id AND fsc.status = 'active'
                JOIN funds f ON f.wind_code = fsc.wind_code
                {self._style_evidence_join_sql()}
                LEFT JOIN LATERAL (
                    SELECT
                        MAX(metric_value) FILTER (WHERE metric_window = '1y' AND metric_name = 'annualized_return') AS annualized_return_1y,
                        MAX(metric_value) FILTER (WHERE metric_window = '1y' AND metric_name = 'max_drawdown') AS max_drawdown_1y,
                        MAX(metric_value) FILTER (WHERE metric_window = '1y' AND metric_name = 'sharpe_ratio') AS sharpe_ratio_1y,
                        MAX(metric_value) FILTER (WHERE metric_window = '1y' AND metric_name = 'tracking_error') AS tracking_error_1y,
                        MAX(metric_value) FILTER (WHERE metric_window = '1y' AND metric_name = 'tracking_difference') AS tracking_difference_1y,
                        MAX(metric_value) FILTER (WHERE metric_window = '1y' AND metric_name = 'excess_return') AS excess_return_1y,
                        MAX(metric_value) FILTER (WHERE metric_window = '1y' AND metric_name = 'information_ratio') AS information_ratio_1y,
                        MAX(metric_value) FILTER (WHERE metric_window = 'latest' AND metric_name = 'expense_ratio') AS expense_ratio,
                        MAX(metric_value) FILTER (WHERE metric_window = 'latest' AND metric_name = 'aum') AS aum,
                        MAX(metric_value) FILTER (WHERE metric_window = 'latest' AND metric_name = 'seven_day_annualized_yield') AS seven_day_annualized_yield
                    FROM (
                        SELECT DISTINCT ON (metric_window, metric_name)
                            metric_window, metric_name, metric_value
                        FROM metric_snapshots
                        WHERE target_type = 'fund'
                          AND target_id = f.wind_code
                        ORDER BY metric_window, metric_name, as_of_date DESC, updated_at DESC
                    ) latest_metrics
                ) evaluation_metrics ON TRUE
                WHERE (pg.name = :peer_group OR pg.key = :peer_group)
                  AND pgm.role <> 'excluded'
                  AND fe.lifecycle_stage = 'active'
                  AND ({active_fund_sql('f')})
                ORDER BY
                    fe.id,
                    evaluation_ready DESC NULLS LAST,
                    fsc.is_primary DESC,
                    f.nav_date DESC NULLS LAST,
                    fsc.wind_code ASC
            )
            SELECT entity_id, wind_code, classification_style_tags, memo_style_tags, holding_style_tags
            FROM representative_funds
            WHERE :availability <> 'evaluated' OR evaluation_ready
        """
        with self.engine.connect() as conn:
            rows = [
                _row_to_dict(row)
                for row in conn.execute(text(sql), {
                    "peer_group": normalized_group,
                    "availability": normalized_availability,
                }).fetchall()
            ]
        return self._build_style_tag_catalog(normalized_group, normalized_availability, rows)

    @staticmethod
    def empty_style_tag_catalog(peer_group: str) -> Dict[str, Any]:
        return {
            "peer_group": peer_group or None,
            "availability": "classified",
            "tags": [],
            "coverage": {
                "fund_count": 0,
                "tagged_fund_count": 0,
                "coverage_rate": 0.0,
                "holding_quantitative_fund_count": 0,
                "memo_confirmed_fund_count": 0,
                "product_positioning_fund_count": 0,
            },
            "match_modes": ["any", "all"],
        }

    @classmethod
    def _build_style_tag_catalog(
        cls,
        peer_group: str,
        availability: str,
        rows: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        source_meta = {
            "holding": ("公开持仓同类分位", "strong"),
            "memo": ("产品纪要人工确认", "context"),
            "positioning": ("标准分类产品定位", "classification"),
        }
        tag_funds: Dict[str, set[str]] = {}
        tag_sources: Dict[str, Dict[str, set[str]]] = {}
        source_funds: Dict[str, set[str]] = {key: set() for key in source_meta}
        tagged_funds: set[str] = set()

        for row in rows:
            fund_id = str(row.get("entity_id") or row.get("wind_code") or "")
            source_values = {
                "holding": row.get("holding_style_tags") or [],
                "memo": row.get("memo_style_tags") or [],
                "positioning": row.get("classification_style_tags") or [],
            }
            for source, values in source_values.items():
                tags = list(dict.fromkeys(
                    str(value or "").strip() for value in values if str(value or "").strip()
                ))
                if tags:
                    source_funds[source].add(fund_id)
                    tagged_funds.add(fund_id)
                for tag in tags:
                    tag_funds.setdefault(tag, set()).add(fund_id)
                    tag_sources.setdefault(tag, {}).setdefault(source, set()).add(fund_id)

        tags = []
        for value, fund_ids in tag_funds.items():
            sources = [
                {
                    "key": source,
                    "label": source_meta[source][0],
                    "evidence_level": source_meta[source][1],
                    "fund_count": len(source_ids),
                }
                for source, source_ids in tag_sources.get(value, {}).items()
            ]
            evidence_level = (
                "strong" if "holding" in tag_sources.get(value, {})
                else "context" if "memo" in tag_sources.get(value, {})
                else "classification"
            )
            tags.append({
                "value": value,
                "fund_count": len(fund_ids),
                "evidence_level": evidence_level,
                "sources": sources,
            })
        tags.sort(key=lambda item: (
            {"strong": 0, "context": 1, "classification": 2}.get(item["evidence_level"], 9),
            -item["fund_count"],
            item["value"],
        ))
        fund_count = len(rows)
        return {
            "peer_group": peer_group,
            "availability": availability,
            "tags": tags,
            "coverage": {
                "fund_count": fund_count,
                "tagged_fund_count": len(tagged_funds),
                "coverage_rate": round(len(tagged_funds) / fund_count, 4) if fund_count else 0.0,
                "holding_quantitative_fund_count": len(source_funds["holding"]),
                "memo_confirmed_fund_count": len(source_funds["memo"]),
                "product_positioning_fund_count": len(source_funds["positioning"]),
            },
            "match_modes": ["any", "all"],
            "boundary": "只使用公开持仓同类分位、明确指向该产品且人工确认的纪要标签、标准分类产品定位；经理层纪要不会直接变成基金持仓标签。",
        }

    @staticmethod
    def _recommendation_metric_expressions(alias: str = "peer_funds") -> Dict[str, str]:
        number_pattern = "'^-?[0-9]+(\\.[0-9]+)?$'"
        return_6m_raw = f"NULLIF({alias}.performance_data->>'return_6m', '')"
        return_1y_raw = f"NULLIF(COALESCE({alias}.performance_data->>'return_1y', {alias}.performance_data->>'total_return'), '')"
        return_3y_raw = f"NULLIF({alias}.performance_data->>'return_3y', '')"
        drawdown_raw = f"NULLIF(COALESCE({alias}.risk_metrics->>'max_drawdown_1y', {alias}.risk_metrics->>'max_drawdown', {alias}.performance_data->>'max_drawdown'), '')"
        sharpe_raw = f"NULLIF(COALESCE({alias}.performance_data->>'sharpe_ratio', {alias}.risk_metrics->>'sharpe_ratio'), '')"
        return {
            "return_6m": f"CASE WHEN {return_6m_raw} ~ {number_pattern} THEN {return_6m_raw}::numeric END",
            "return_1y": f"CASE WHEN {return_1y_raw} ~ {number_pattern} THEN {return_1y_raw}::numeric END",
            "return_3y": f"CASE WHEN {return_3y_raw} ~ {number_pattern} THEN {return_3y_raw}::numeric END",
            "drawdown": f"CASE WHEN {drawdown_raw} ~ {number_pattern} THEN {drawdown_raw}::numeric END",
            "sharpe": f"CASE WHEN {sharpe_raw} ~ {number_pattern} THEN {sharpe_raw}::numeric END",
        }

    @staticmethod
    def _peer_return_rank_sql(metric_column: str, window: str) -> str:
        count_sql = f"COUNT({metric_column}) OVER ()"
        rank_sql = f"RANK() OVER (PARTITION BY ({metric_column} IS NULL) ORDER BY {metric_column} DESC)"
        return f"""
            CASE WHEN {metric_column} IS NULL THEN NULL ELSE ({rank_sql})::int END AS return_{window}_peer_rank,
            ({count_sql})::int AS return_{window}_peer_count,
            CASE
                WHEN {metric_column} IS NULL THEN NULL
                WHEN {count_sql} <= 1 THEN 100::numeric
                ELSE ROUND((({count_sql} - {rank_sql})::numeric / ({count_sql} - 1)) * 100, 2)
            END AS return_{window}_peer_percentile
        """.strip()

    @classmethod
    def _recommendation_filter_sql(
        cls,
        keyword: Optional[str],
        asset_min: Optional[float],
        min_age_years: Optional[int],
        min_manager_years: Optional[float],
        return_6m_min: Optional[float],
        return_1y_min: Optional[float],
        return_3y_min: Optional[float],
        max_drawdown_1y_max: Optional[float],
        sharpe_1y_min: Optional[float],
        style_tags: Optional[List[str]] = None,
        style_match: str = "any",
        availability: str = "classified",
    ) -> tuple[str, Dict[str, Any]]:
        metrics = cls._recommendation_metric_expressions()
        clauses: List[str] = ["TRUE"]
        params: Dict[str, Any] = {}
        if str(availability or "classified").strip().lower() == "evaluated":
            clauses.append("peer_funds.evaluation_ready")
        normalized_keyword = str(keyword or "").strip()
        if normalized_keyword:
            clauses.append("(peer_funds.name ILIKE :keyword_pattern OR peer_funds.wind_code ILIKE :keyword_pattern)")
            params["keyword_pattern"] = f"%{normalized_keyword}%"
        if asset_min is not None:
            clauses.append("peer_funds.total_asset >= :asset_min")
            params["asset_min"] = max(0.0, float(asset_min))
        if min_age_years is not None:
            clauses.append("peer_funds.establishment_date <= CURRENT_DATE - (:min_age_years * INTERVAL '1 year')")
            params["min_age_years"] = max(0, int(min_age_years))
        if min_manager_years is not None:
            clauses.append("""
                EXISTS (
                    SELECT 1
                    FROM managers manager
                    WHERE (
                        manager.wind_code = ANY(COALESCE(peer_funds.manager_ids, ARRAY[]::TEXT[]))
                        OR manager.name = ANY(COALESCE(peer_funds.manager_ids, ARRAY[]::TEXT[]))
                    )
                      AND COALESCE(manager.management_years, 0) >= :min_manager_years
                )
            """)
            params["min_manager_years"] = max(0.0, float(min_manager_years))
        if return_6m_min is not None:
            clauses.append(f"({metrics['return_6m']}) >= :return_6m_min")
            params["return_6m_min"] = float(return_6m_min)
        if return_1y_min is not None:
            clauses.append(f"({metrics['return_1y']}) >= :return_1y_min")
            params["return_1y_min"] = float(return_1y_min)
        if return_3y_min is not None:
            clauses.append(f"({metrics['return_3y']}) >= :return_3y_min")
            params["return_3y_min"] = float(return_3y_min)
        if max_drawdown_1y_max is not None:
            clauses.append(f"ABS({metrics['drawdown']}) <= :max_drawdown_1y_max")
            params["max_drawdown_1y_max"] = max(0.0, float(max_drawdown_1y_max))
        if sharpe_1y_min is not None:
            clauses.append(f"({metrics['sharpe']}) >= :sharpe_1y_min")
            params["sharpe_1y_min"] = float(sharpe_1y_min)
        normalized_style_tags = list(dict.fromkeys(
            str(tag or "").strip() for tag in (style_tags or []) if str(tag or "").strip()
        ))
        if normalized_style_tags:
            normalized_style_match = "all" if str(style_match or "any").strip().lower() == "all" else "any"
            operator = "<@" if normalized_style_match == "all" else "&&"
            clauses.append(
                f"CAST(:style_tags AS TEXT[]) {operator} COALESCE(peer_funds.verified_style_tags, ARRAY[]::TEXT[])"
            )
            params["style_tags"] = normalized_style_tags
        return " AND ".join(f"({clause.strip()})" for clause in clauses), params

    @staticmethod
    def _memo_style_tags_sql() -> str:
        return """
            CASE
                WHEN COALESCE(research_profile.updated_by, '') = 'research_memo_profile_projection'
                THEN array_remove(
                    ARRAY[NULLIF(research_profile.style_label, '')]::TEXT[]
                    || COALESCE(research_profile.strategy_tags, ARRAY[]::TEXT[]),
                    NULL
                )
                ELSE ARRAY[]::TEXT[]
            END
        """.strip()

    @staticmethod
    def _holding_style_tags_sql() -> str:
        return """
            CASE
                WHEN holding_style.status = 'peer_percentile_ready'
                THEN COALESCE(holding_style.style_labels, ARRAY[]::TEXT[])
                ELSE ARRAY[]::TEXT[]
            END
        """.strip()

    @classmethod
    def _verified_style_tags_sql(cls) -> str:
        return f"""
            ARRAY(
                SELECT DISTINCT tag
                FROM unnest(
                    COALESCE(sf.style_tags, ARRAY[]::TEXT[])
                    || ({cls._memo_style_tags_sql()})
                    || ({cls._holding_style_tags_sql()})
                ) tag
                WHERE COALESCE(tag, '') <> ''
                ORDER BY tag
            )
        """.strip()

    @staticmethod
    def _style_evidence_join_sql() -> str:
        return """
            LEFT JOIN LATERAL (
                SELECT profile.*
                FROM fund_research_profiles profile
                WHERE profile.wind_code = fe.canonical_code
                   OR EXISTS (
                        SELECT 1
                        FROM fund_share_classes profile_share
                        WHERE profile_share.entity_id = fe.id
                          AND profile_share.wind_code = profile.wind_code
                   )
                ORDER BY
                    CASE WHEN profile.updated_by = 'research_memo_profile_projection' THEN 0 ELSE 1 END,
                    CASE WHEN profile.wind_code = fe.canonical_code THEN 0 ELSE 1 END,
                    profile.updated_at DESC
                LIMIT 1
            ) research_profile ON TRUE
            LEFT JOIN LATERAL (
                SELECT snapshot.*
                FROM holding_style_snapshots snapshot
                JOIN fund_share_classes style_share
                  ON style_share.wind_code = snapshot.wind_code
                 AND style_share.entity_id = fe.id
                WHERE style_share.status = 'active'
                ORDER BY
                    snapshot.quarter DESC,
                    CASE WHEN snapshot.status = 'peer_percentile_ready' THEN 0 ELSE 1 END,
                    snapshot.calculated_at DESC
                LIMIT 1
            ) holding_style ON TRUE
        """.strip()

    @staticmethod
    def _recommendation_evaluation_ready_sql(
        fund_alias: str,
        family_expression: str,
        metric_alias: Optional[str] = None,
    ) -> str:
        """与类别评分方法一致的轻量门禁，用于列表分页前筛选。"""
        number_pattern = "'^-?[0-9]+(\\.[0-9]+)?$'"

        def numeric(expression: str) -> str:
            return (
                f"CASE WHEN NULLIF({expression}, '') ~ {number_pattern} "
                f"THEN NULLIF({expression}, '')::numeric END"
            )

        annualized_return_fallback = numeric(
            f"COALESCE({fund_alias}.performance_data->>'annualized_return_1y', "
            f"{fund_alias}.performance_data->>'return_1y', {fund_alias}.performance_data->>'annual_return')"
        )
        drawdown_fallback = numeric(
            f"COALESCE({fund_alias}.risk_metrics->>'max_drawdown_1y', "
            f"{fund_alias}.risk_metrics->>'max_drawdown', {fund_alias}.performance_data->>'max_drawdown')"
        )
        sharpe_fallback = numeric(
            f"COALESCE({fund_alias}.performance_data->>'sharpe_ratio', "
            f"{fund_alias}.performance_data->>'sharpe', {fund_alias}.risk_metrics->>'sharpe_ratio')"
        )
        tracking_error_fallback = numeric(f"{fund_alias}.risk_metrics->>'tracking_error'")
        tracking_difference_fallback = numeric(
            f"COALESCE({fund_alias}.performance_data->>'tracking_difference', "
            f"{fund_alias}.performance_data->>'excess_return')"
        )
        information_ratio_fallback = numeric(f"{fund_alias}.risk_metrics->>'information_ratio'")
        seven_day_yield_fallback = numeric(
            f"COALESCE({fund_alias}.performance_data->>'seven_day_annualized_yield', "
            f"{fund_alias}.performance_data->>'yield_7d', {fund_alias}.performance_data->>'seven_day_yield')"
        )
        management_fee = numeric(
            f"COALESCE({fund_alias}.raw_data#>>'{{info,management_fee}}', {fund_alias}.raw_data#>>'{{info,m_fee}}', "
            f"{fund_alias}.raw_data#>>'{{universe,management_fee}}', {fund_alias}.raw_data#>>'{{universe,m_fee}}')"
        )
        custodian_fee = numeric(
            f"COALESCE({fund_alias}.raw_data#>>'{{info,custodian_fee}}', {fund_alias}.raw_data#>>'{{info,c_fee}}', "
            f"{fund_alias}.raw_data#>>'{{universe,custodian_fee}}', {fund_alias}.raw_data#>>'{{universe,c_fee}}')"
        )
        expense_ratio_fallback = f"""
            CASE
                WHEN ({management_fee}) IS NOT NULL OR ({custodian_fee}) IS NOT NULL
                THEN
                    COALESCE(CASE WHEN ABS({management_fee}) >= 0.05 THEN ({management_fee}) / 100 ELSE ({management_fee}) END, 0)
                    + COALESCE(CASE WHEN ABS({custodian_fee}) >= 0.05 THEN ({custodian_fee}) / 100 ELSE ({custodian_fee}) END, 0)
            END
        """
        annualized_return = f"COALESCE({metric_alias}.annualized_return_1y, {annualized_return_fallback})" if metric_alias else annualized_return_fallback
        drawdown = f"COALESCE({metric_alias}.max_drawdown_1y, {drawdown_fallback})" if metric_alias else drawdown_fallback
        sharpe = f"COALESCE({metric_alias}.sharpe_ratio_1y, {sharpe_fallback})" if metric_alias else sharpe_fallback
        tracking_error = f"COALESCE({metric_alias}.tracking_error_1y, {tracking_error_fallback})" if metric_alias else tracking_error_fallback
        tracking_difference = (
            f"COALESCE({metric_alias}.tracking_difference_1y, {metric_alias}.excess_return_1y, {tracking_difference_fallback})"
            if metric_alias else tracking_difference_fallback
        )
        information_ratio = (
            f"COALESCE({metric_alias}.information_ratio_1y, {information_ratio_fallback})"
            if metric_alias else information_ratio_fallback
        )
        expense_ratio = f"COALESCE({metric_alias}.expense_ratio, {expense_ratio_fallback})" if metric_alias else expense_ratio_fallback
        aum = f"COALESCE({metric_alias}.aum, {fund_alias}.total_asset)" if metric_alias else f"{fund_alias}.total_asset"
        seven_day_yield = f"COALESCE({metric_alias}.seven_day_annualized_yield, {seven_day_yield_fallback})" if metric_alias else seven_day_yield_fallback
        normalized_yield = f"CASE WHEN ABS({seven_day_yield}) > 0.20 THEN ({seven_day_yield}) / 100 ELSE ({seven_day_yield}) END"
        normalized_return = f"CASE WHEN ABS({annualized_return}) > 0.20 THEN ({annualized_return}) / 100 ELSE ({annualized_return}) END"
        fof_lookthrough_ready = f"""
            EXISTS (
                SELECT 1
                FROM fund_underlying_holdings fof_holding
                WHERE fof_holding.wind_code = {fund_alias}.wind_code
                  AND fof_holding.report_date = (
                      SELECT MAX(latest_fof_holding.report_date)
                      FROM fund_underlying_holdings latest_fof_holding
                      WHERE latest_fof_holding.wind_code = {fund_alias}.wind_code
                  )
                GROUP BY fof_holding.wind_code, fof_holding.report_date
                HAVING COUNT(*) >= {FOF_LOOKTHROUGH_MIN_FUNDS}
                   AND COALESCE(SUM(fof_holding.nav_ratio), 0) >= {FOF_LOOKTHROUGH_MIN_NAV_RATIO}
            )
        """
        return f"""
            (
            {fund_alias}.establishment_date IS NULL
            OR {fund_alias}.establishment_date <= CURRENT_DATE - INTERVAL '365 days'
            )
            AND CASE
                WHEN {family_expression} IN (
                    'active_equity_core', 'active_equity_sector', 'active_equity_cross_market',
                    'fixed_income_general', 'fixed_income_credit', 'fixed_income_equity_allocation',
                    'mixed_equity_allocation', 'mixed_balanced_allocation', 'mixed_bond_allocation',
                    'qdii_equity', 'qdii_bond', 'qdii_multi_asset'
                ) THEN ({annualized_return}) IS NOT NULL AND ({drawdown}) IS NOT NULL AND ({sharpe}) IS NOT NULL
                WHEN {family_expression} IN (
                    'fof_equity_allocation', 'fof_balanced_allocation', 'fof_bond_allocation'
                ) THEN
                    ({annualized_return}) IS NOT NULL
                    AND ({drawdown}) IS NOT NULL
                    AND ({sharpe}) IS NOT NULL
                    AND ({fof_lookthrough_ready})
                WHEN {family_expression} IN ('index_broad', 'index_sector', 'index_fixed_income') THEN
                    ({tracking_error}) BETWEEN 0 AND 0.10
                    AND ABS({tracking_difference}) <= 0.25
                    AND ({expense_ratio}) BETWEEN 0 AND 0.05
                    AND ({aum}) > 0
                WHEN {family_expression} = 'qdii_index' THEN
                    ({tracking_error}) BETWEEN 0 AND 0.15
                    AND ABS({tracking_difference}) <= 0.25
                    AND ({expense_ratio}) BETWEEN 0 AND 0.05
                    AND ({aum}) > 0
                WHEN {family_expression} = 'index_enhanced' THEN
                    ({tracking_difference}) BETWEEN -0.50 AND 0.50
                    AND ({information_ratio}) BETWEEN -10 AND 10
                    AND ({tracking_error}) BETWEEN 0 AND 0.35
                    AND ({drawdown}) BETWEEN -0.80 AND 0.01
                    AND ({expense_ratio}) BETWEEN 0 AND 0.05
                    AND ({aum}) > 0
                WHEN {family_expression} = 'cash_management' THEN
                    ({normalized_yield}) BETWEEN 0 AND 0.20
                    AND ({normalized_return}) BETWEEN -0.05 AND 0.20
                    AND ABS({drawdown}) <= 0.20
                    AND ({aum}) > 0
                ELSE FALSE
            END
        """

    @classmethod
    def _recommendation_sort_sql(cls, sort_by: str) -> str:
        metrics = cls._recommendation_metric_expressions()
        quality = """
            (
                SELECT COUNT(DISTINCT ms.metric_name)
                FROM metric_snapshots ms
                WHERE ms.target_type = 'fund'
                  AND ms.target_id = peer_funds.wind_code
                  AND ms.metric_window = '1y'
                  AND ms.metric_name IN ('annualized_return', 'max_drawdown', 'sharpe_ratio', 'annualized_volatility')
            ) DESC,
            CASE WHEN peer_funds.performance_data IS NULL OR peer_funds.performance_data = '{}'::jsonb THEN 1 ELSE 0 END,
            CASE WHEN peer_funds.risk_metrics IS NULL OR peer_funds.risk_metrics = '{}'::jsonb THEN 1 ELSE 0 END,
            peer_funds.nav_date DESC NULLS LAST
        """.strip()
        return {
            "return": f"({metrics['return_1y']}) DESC NULLS LAST",
            "return_6m": f"({metrics['return_6m']}) DESC NULLS LAST",
            "return_1y": f"({metrics['return_1y']}) DESC NULLS LAST",
            "return_3y": f"({metrics['return_3y']}) DESC NULLS LAST",
            "multi_period": """
                (
                    (CASE WHEN peer_funds.return_6m_peer_percentile IS NOT NULL THEN 1 ELSE 0 END) +
                    (CASE WHEN peer_funds.return_1y_peer_percentile IS NOT NULL THEN 1 ELSE 0 END) +
                    (CASE WHEN peer_funds.return_3y_peer_percentile IS NOT NULL THEN 1 ELSE 0 END)
                ) DESC,
                (
                    COALESCE(peer_funds.return_6m_peer_percentile, 0) +
                    COALESCE(peer_funds.return_1y_peer_percentile, 0) +
                    COALESCE(peer_funds.return_3y_peer_percentile, 0)
                ) DESC
            """.strip(),
            "drawdown": f"ABS({metrics['drawdown']}) ASC NULLS LAST",
            "sharpe": f"({metrics['sharpe']}) DESC NULLS LAST",
            "asset": "peer_funds.total_asset DESC NULLS LAST",
            "history": "peer_funds.establishment_date ASC NULLS LAST",
        }.get(str(sort_by or "").strip().lower(), quality)

    def ensure_catalog(
        self,
        strategy_families: List[Dict[str, Any]],
        peer_groups: List[Dict[str, Any]],
        source: str,
    ) -> Dict[str, Any]:
        """幂等初始化正式分类目录，不写入演示基金。"""
        if not self._schema_ready():
            raise RuntimeError("标准化基金分类表尚未完整部署")

        from sqlalchemy import text

        with self.engine.begin() as conn:
            for family in strategy_families:
                benchmark_policy = family.get("benchmark_policy") or {
                    "catalogVersion": source,
                    "rule": "explicit_benchmark_mapping_required",
                }
                peer_policy = family.get("peer_policy") or {
                    "catalogVersion": source,
                    "rule": "same_strategy_and_benchmark_only",
                }
                conn.execute(text("""
                    INSERT INTO strategy_families (
                        id, key, name, asset_class, active_passive, style_tags,
                        benchmark_policy, peer_policy, source, updated_at
                    ) VALUES (
                        :id, :key, :name, :asset_class, :active_passive, :style_tags,
                        CAST(:benchmark_policy AS jsonb), CAST(:peer_policy AS jsonb), :source, NOW()
                    )
                    ON CONFLICT (key) DO UPDATE SET
                        name = EXCLUDED.name,
                        asset_class = EXCLUDED.asset_class,
                        active_passive = EXCLUDED.active_passive,
                        style_tags = EXCLUDED.style_tags,
                        benchmark_policy = EXCLUDED.benchmark_policy,
                        peer_policy = EXCLUDED.peer_policy,
                        source = EXCLUDED.source,
                        updated_at = NOW()
                """), {
                    "id": family.get("id"),
                    "key": family.get("key"),
                    "name": family.get("name"),
                    "asset_class": family.get("asset_class"),
                    "active_passive": family.get("active_passive"),
                    "style_tags": family.get("style_tags") or [],
                    "benchmark_policy": json.dumps(benchmark_policy, ensure_ascii=False),
                    "peer_policy": json.dumps(peer_policy, ensure_ascii=False),
                    "source": source,
                })

            for peer_group in peer_groups:
                strategy = conn.execute(text("""
                    SELECT id, asset_class, active_passive
                    FROM strategy_families
                    WHERE key = :strategy_family_key
                    LIMIT 1
                """), {
                    "strategy_family_key": peer_group.get("strategy_family_key"),
                }).fetchone()
                if not strategy:
                    raise ValueError("catalog_strategy_family_missing")
                strategy_row = dict(strategy._mapping)
                if strategy_row.get("asset_class") != peer_group.get("asset_class"):
                    raise ValueError("catalog_peer_asset_class_conflict")
                if strategy_row.get("active_passive") != peer_group.get("active_passive"):
                    raise ValueError("catalog_peer_active_passive_conflict")

                conn.execute(text("""
                    INSERT INTO peer_groups (
                        id, key, name, strategy_family_id, asset_class, active_passive,
                        benchmark_code, benchmark_name, inclusion_rules, exclusion_rules,
                        minimum_peer_count, source, source_updated_at, updated_at
                    ) VALUES (
                        :id, :key, :name, :strategy_family_id, :asset_class, :active_passive,
                        :benchmark_code, :benchmark_name, CAST(:inclusion_rules AS jsonb),
                        CAST(:exclusion_rules AS jsonb), :minimum_peer_count, :source,
                        :source_updated_at, NOW()
                    )
                    ON CONFLICT (key) DO UPDATE SET
                        name = EXCLUDED.name,
                        strategy_family_id = EXCLUDED.strategy_family_id,
                        asset_class = EXCLUDED.asset_class,
                        active_passive = EXCLUDED.active_passive,
                        benchmark_code = EXCLUDED.benchmark_code,
                        benchmark_name = EXCLUDED.benchmark_name,
                        inclusion_rules = EXCLUDED.inclusion_rules,
                        exclusion_rules = EXCLUDED.exclusion_rules,
                        minimum_peer_count = EXCLUDED.minimum_peer_count,
                        source = EXCLUDED.source,
                        source_updated_at = EXCLUDED.source_updated_at,
                        updated_at = NOW()
                """), {
                    "id": peer_group.get("id"),
                    "key": peer_group.get("key"),
                    "name": peer_group.get("name"),
                    "strategy_family_id": strategy_row["id"],
                    "asset_class": peer_group.get("asset_class"),
                    "active_passive": peer_group.get("active_passive"),
                    "benchmark_code": peer_group.get("benchmark_code"),
                    "benchmark_name": peer_group.get("benchmark_name"),
                    "inclusion_rules": json.dumps(peer_group.get("inclusion_rules") or {}, ensure_ascii=False),
                    "exclusion_rules": json.dumps(peer_group.get("exclusion_rules") or {}, ensure_ascii=False),
                    "minimum_peer_count": peer_group.get("minimum_peer_count") or 5,
                    "source": source,
                    "source_updated_at": date.today(),
                })

        self._schema_ready_cache = True
        return {
            "catalog_strategy_families": len(strategy_families),
            "catalog_peer_groups": len(peer_groups),
            "catalog_version": source,
        }

    def apply_ingestion_plan(
        self,
        groups: List[Dict[str, Any]],
        source: str = "tushare_classification_ingestion",
        reconcile: bool = False,
    ) -> Dict[str, Any]:
        """幂等写入高置信度实体、份额、同类组成员关系与基准映射。"""
        if not groups and not reconcile:
            return {
                "applied_groups": 0,
                "applied_shares": 0,
                "created_entities": 0,
                "reused_entities": 0,
                "deactivated_shares": 0,
                "deactivated_entities": 0,
                "conflicts": [],
            }
        if not self._schema_ready():
            raise RuntimeError("标准化基金分类表尚未完整部署")

        from sqlalchemy import text

        applied_groups = 0
        applied_shares = 0
        created_entities = 0
        reused_entities = 0
        deactivated_shares = 0
        deactivated_entities = 0
        conflicts: List[Dict[str, Any]] = []
        active_share_codes = [
            str(share.get("wind_code"))
            for group in groups
            for share in group.get("shares") or []
            if share.get("wind_code")
        ]

        with self.engine.begin() as conn:
            for group in groups:
                try:
                    with conn.begin_nested():
                        strategy = conn.execute(text("""
                            SELECT id, key, asset_class, active_passive
                            FROM strategy_families
                            WHERE key = :strategy_family_key
                            LIMIT 1
                        """), {"strategy_family_key": group.get("strategy_family_key")}).fetchone()
                        peer_group = conn.execute(text("""
                            SELECT id, key, benchmark_code
                            FROM peer_groups
                            WHERE key = :peer_group_key
                            LIMIT 1
                        """), {"peer_group_key": group.get("peer_group_key")}).fetchone()
                        if not strategy or not peer_group:
                            raise ValueError("strategy_family_or_peer_group_missing")

                        strategy_row = dict(strategy._mapping)
                        peer_row = dict(peer_group._mapping)
                        if strategy_row.get("asset_class") != group.get("asset_class"):
                            raise ValueError("strategy_family_asset_class_conflict")
                        if strategy_row.get("active_passive") != group.get("active_passive"):
                            raise ValueError("strategy_family_active_passive_conflict")
                        peer_group_benchmark_code = (
                            group.get("peer_group_benchmark_code") or group.get("benchmark_code")
                        )
                        if peer_row.get("benchmark_code") != peer_group_benchmark_code:
                            raise ValueError("peer_group_benchmark_conflict")

                        share_codes = [str(share.get("wind_code")) for share in group.get("shares") or []]
                        existing_rows = conn.execute(text("""
                            SELECT DISTINCT
                                fe.id,
                                fe.source,
                                fe.strategy_family_id,
                                fe.normalized_name
                            FROM fund_share_classes fsc
                            JOIN fund_entities fe ON fe.id = fsc.entity_id
                            WHERE fsc.wind_code = ANY(:share_codes)
                        """), {"share_codes": share_codes}).fetchall()
                        if len(existing_rows) > 1:
                            raise ValueError("share_codes_resolve_to_multiple_entities")

                        existing = existing_rows[0] if existing_rows else conn.execute(text("""
                            SELECT id, source, strategy_family_id, normalized_name
                            FROM fund_entities
                            WHERE canonical_code = :canonical_code
                               OR (
                                    normalized_name = :normalized_name
                                    AND strategy_family_id = :strategy_family_id
                               )
                            ORDER BY CASE WHEN canonical_code = :canonical_code THEN 0 ELSE 1 END
                            LIMIT 1
                        """), {
                            "canonical_code": group.get("canonical_code"),
                            "normalized_name": group.get("normalized_name"),
                            "strategy_family_id": strategy_row["id"],
                        }).fetchone()

                        entity_id = str(existing.id) if existing else str(group.get("entity_id"))
                        if existing and existing.strategy_family_id not in {None, strategy_row["id"]}:
                            curated_classification = conn.execute(text("""
                                SELECT 1
                                FROM peer_group_members
                                WHERE entity_id = :entity_id
                                  AND source <> :source
                                UNION ALL
                                SELECT 1
                                FROM benchmark_mappings
                                WHERE entity_id = :entity_id
                                  AND status = 'active'
                                  AND source <> :source
                                LIMIT 1
                            """), {
                                "entity_id": str(existing.id),
                                "source": source,
                            }).fetchone()
                            if existing.source != source or curated_classification:
                                raise ValueError("existing_entity_strategy_family_conflict")
                        entity_created = not bool(existing)

                        entity_payload = {
                            "source": source,
                            "classificationRule": group.get("mapping_method"),
                            "classificationConfidence": group.get("classification_confidence"),
                            "benchmarkConfidence": group.get("benchmark_confidence"),
                            "evidenceRefs": group.get("evidence_refs") or {},
                        }
                        if existing:
                            if existing.source == source:
                                conn.execute(text("""
                                    UPDATE fund_entities
                                    SET canonical_code = :canonical_code,
                                        canonical_name = :canonical_name,
                                        normalized_name = :normalized_name,
                                        strategy_family_id = :strategy_family_id,
                                        asset_class = :asset_class,
                                        active_passive = :active_passive,
                                        lifecycle_stage = 'active',
                                        established_at = COALESCE(:established_at, established_at),
                                        source_updated_at = :source_updated_at,
                                        raw_data = COALESCE(raw_data, '{}'::jsonb) || CAST(:raw_data AS jsonb),
                                        updated_at = NOW()
                                    WHERE id = :entity_id
                                """), {
                                    "entity_id": entity_id,
                                    "canonical_code": group.get("canonical_code"),
                                    "canonical_name": group.get("canonical_name"),
                                    "normalized_name": group.get("normalized_name"),
                                    "strategy_family_id": strategy_row["id"],
                                    "asset_class": group.get("asset_class"),
                                    "active_passive": group.get("active_passive"),
                                    "established_at": group.get("established_at"),
                                    "source_updated_at": group.get("source_updated_at"),
                                    "raw_data": json.dumps(entity_payload, ensure_ascii=False),
                                })
                        else:
                            conn.execute(text("""
                                INSERT INTO fund_entities (
                                    id, canonical_code, canonical_name, normalized_name,
                                    strategy_family_id, asset_class, active_passive,
                                    lifecycle_stage, established_at, source, source_updated_at,
                                    raw_data, updated_at
                                ) VALUES (
                                    :entity_id, :canonical_code, :canonical_name, :normalized_name,
                                    :strategy_family_id, :asset_class, :active_passive,
                                    'active', :established_at, :source, :source_updated_at,
                                    CAST(:raw_data AS jsonb), NOW()
                                )
                            """), {
                                "entity_id": entity_id,
                                "canonical_code": group.get("canonical_code"),
                                "canonical_name": group.get("canonical_name"),
                                "normalized_name": group.get("normalized_name"),
                                "strategy_family_id": strategy_row["id"],
                                "asset_class": group.get("asset_class"),
                                "active_passive": group.get("active_passive"),
                                "established_at": group.get("established_at"),
                                "source": source,
                                "source_updated_at": group.get("source_updated_at"),
                                "raw_data": json.dumps(entity_payload, ensure_ascii=False),
                            })

                        group_share_count = 0
                        for share in group.get("shares") or []:
                            share_payload = {
                                "source": "funds",
                                "fundType": share.get("fund_type"),
                                "investType": share.get("invest_type"),
                                "contractType": share.get("contract_type"),
                                "declaredBenchmark": share.get("declared_benchmark"),
                                "normalizationRule": "trailing_share_class_suffix",
                            }
                            share_id = "share-auto-" + hashlib.sha1(
                                str(share.get("wind_code")).encode("utf-8")
                            ).hexdigest()[:20]
                            conn.execute(text("""
                                INSERT INTO fund_share_classes (
                                    id, entity_id, fund_id, wind_code, share_class, fee_class,
                                    currency, is_primary, status, source, source_updated_at,
                                    raw_data, updated_at
                                ) VALUES (
                                    :id, :entity_id, :fund_id, :wind_code, :share_class, NULL,
                                    :currency, :is_primary, 'active', :source, :source_updated_at,
                                    CAST(:raw_data AS jsonb), NOW()
                                )
                                ON CONFLICT (wind_code) DO UPDATE SET
                                    entity_id = CASE
                                        WHEN fund_share_classes.source = :source THEN EXCLUDED.entity_id
                                        ELSE fund_share_classes.entity_id
                                    END,
                                    fund_id = COALESCE(fund_share_classes.fund_id, EXCLUDED.fund_id),
                                    share_class = COALESCE(fund_share_classes.share_class, EXCLUDED.share_class),
                                    currency = COALESCE(fund_share_classes.currency, EXCLUDED.currency),
                                    is_primary = CASE
                                        WHEN fund_share_classes.source = :source THEN EXCLUDED.is_primary
                                        ELSE fund_share_classes.is_primary
                                    END,
                                    status = CASE
                                        WHEN fund_share_classes.source = :source THEN 'active'
                                        ELSE fund_share_classes.status
                                    END,
                                    source_updated_at = GREATEST(fund_share_classes.source_updated_at, EXCLUDED.source_updated_at),
                                    raw_data = COALESCE(fund_share_classes.raw_data, '{}'::jsonb) || EXCLUDED.raw_data,
                                    updated_at = NOW()
                            """), {
                                "id": share_id,
                                "entity_id": entity_id,
                                "fund_id": share.get("fund_id"),
                                "wind_code": share.get("wind_code"),
                                "share_class": share.get("share_class"),
                                "currency": share.get("currency") or "CNY",
                                "is_primary": bool(share.get("is_primary")),
                                "source": source,
                                "source_updated_at": share.get("source_updated_at"),
                                "raw_data": json.dumps(share_payload, ensure_ascii=False),
                            })
                            group_share_count += 1

                        curated_membership = conn.execute(text("""
                            SELECT 1
                            FROM peer_group_members
                            WHERE entity_id = :entity_id
                              AND source <> :source
                            LIMIT 1
                        """), {"entity_id": entity_id, "source": source}).fetchone()
                        if not curated_membership:
                            if reconcile:
                                conn.execute(text("""
                                    DELETE FROM peer_group_members
                                    WHERE entity_id = :entity_id
                                      AND source = :source
                                      AND peer_group_id <> :peer_group_id
                                """), {
                                    "entity_id": entity_id,
                                    "source": source,
                                    "peer_group_id": peer_row["id"],
                                })
                            member_id = "peer-member-auto-" + hashlib.sha1(
                                f"{peer_row['id']}|{entity_id}".encode("utf-8")
                            ).hexdigest()[:20]
                            matched_rules = {
                                "strategyFamily": group.get("strategy_family_key"),
                                "peerGroupBenchmarkCode": peer_group_benchmark_code,
                                "contractBenchmarkCode": group.get("benchmark_code"),
                                "normalization": "high_confidence_ingestion",
                                "shareCodes": share_codes,
                            }
                            conn.execute(text("""
                                INSERT INTO peer_group_members (
                                    id, peer_group_id, entity_id, role, matched_rules,
                                    excluded_rules, sample_as_of_date, confidence, source, updated_at
                                ) VALUES (
                                    :id, :peer_group_id, :entity_id, 'member', CAST(:matched_rules AS jsonb),
                                    NULL, :sample_as_of_date, :confidence, :source, NOW()
                                )
                                ON CONFLICT (peer_group_id, entity_id) DO UPDATE SET
                                    matched_rules = EXCLUDED.matched_rules,
                                    sample_as_of_date = EXCLUDED.sample_as_of_date,
                                    confidence = EXCLUDED.confidence,
                                    updated_at = NOW()
                                WHERE peer_group_members.source = :source
                            """), {
                                "id": member_id,
                                "peer_group_id": peer_row["id"],
                                "entity_id": entity_id,
                                "matched_rules": json.dumps(matched_rules, ensure_ascii=False),
                                "sample_as_of_date": group.get("source_updated_at"),
                                "confidence": group.get("classification_confidence"),
                                "source": source,
                            })

                        effective_from = group.get("established_at") or "1900-01-01"
                        curated_mapping = conn.execute(text("""
                            SELECT 1
                            FROM benchmark_mappings
                            WHERE entity_id = :entity_id
                              AND status = 'active'
                              AND source <> :source
                            LIMIT 1
                        """), {"entity_id": entity_id, "source": source}).fetchone()
                        if not curated_mapping:
                            if reconcile:
                                conn.execute(text("""
                                    UPDATE benchmark_mappings
                                    SET status = 'inactive', updated_at = NOW()
                                    WHERE entity_id = :entity_id
                                      AND source = :source
                                      AND benchmark_code <> :benchmark_code
                                      AND status = 'active'
                                """), {
                                    "entity_id": entity_id,
                                    "source": source,
                                    "benchmark_code": group.get("benchmark_code"),
                                })
                            mapping_id = "benchmark-auto-" + hashlib.sha1(
                                f"{entity_id}|{group.get('benchmark_code')}|{effective_from}".encode("utf-8")
                            ).hexdigest()[:20]
                            conn.execute(text("""
                                INSERT INTO benchmark_mappings (
                                    id, entity_id, peer_group_id, benchmark_code, benchmark_name,
                                    benchmark_type, mapping_method, confidence, rationale,
                                    evidence_refs, effective_from, effective_to, status, source, updated_at
                                ) VALUES (
                                    :id, :entity_id, :peer_group_id, :benchmark_code, :benchmark_name,
                                    :benchmark_type, :mapping_method, :confidence, :rationale,
                                    CAST(:evidence_refs AS jsonb), :effective_from, NULL, 'active', :source, NOW()
                                )
                                ON CONFLICT (entity_id, benchmark_code, effective_from) DO UPDATE SET
                                    peer_group_id = EXCLUDED.peer_group_id,
                                    benchmark_name = EXCLUDED.benchmark_name,
                                    benchmark_type = EXCLUDED.benchmark_type,
                                    mapping_method = EXCLUDED.mapping_method,
                                    confidence = EXCLUDED.confidence,
                                    rationale = EXCLUDED.rationale,
                                    evidence_refs = EXCLUDED.evidence_refs,
                                    status = 'active',
                                    updated_at = NOW()
                                WHERE benchmark_mappings.source = :source
                            """), {
                                "id": mapping_id,
                                "entity_id": entity_id,
                                "peer_group_id": peer_row["id"],
                                "benchmark_code": group.get("benchmark_code"),
                                "benchmark_name": group.get("benchmark_name"),
                                "benchmark_type": group.get("benchmark_type"),
                                "mapping_method": group.get("mapping_method"),
                                "confidence": group.get("benchmark_confidence"),
                                "rationale": group.get("rationale"),
                                "evidence_refs": json.dumps(group.get("evidence_refs") or {}, ensure_ascii=False),
                                "effective_from": effective_from,
                                "source": source,
                            })
                        if entity_created:
                            created_entities += 1
                        else:
                            reused_entities += 1
                        applied_shares += group_share_count
                        applied_groups += 1
                except Exception as error:
                    conflicts.append({
                        "canonical_code": group.get("canonical_code"),
                        "normalized_name": group.get("normalized_name"),
                        "reason": str(error),
                    })

            if reconcile:
                deactivated_shares = conn.execute(text("""
                    UPDATE fund_share_classes
                    SET status = 'inactive', updated_at = NOW()
                    WHERE source = :source
                      AND status = 'active'
                      AND wind_code <> ALL(:active_share_codes)
                """), {
                    "source": source,
                    "active_share_codes": active_share_codes,
                }).rowcount
                deactivated_entities = conn.execute(text("""
                    UPDATE fund_entities fe
                    SET lifecycle_stage = 'inactive', updated_at = NOW()
                    WHERE fe.source = :source
                      AND fe.lifecycle_stage = 'active'
                      AND NOT EXISTS (
                          SELECT 1
                          FROM fund_share_classes fsc
                          WHERE fsc.entity_id = fe.id
                            AND fsc.status = 'active'
                      )
                """), {"source": source}).rowcount
                conn.execute(text("""
                    DELETE FROM peer_group_members pgm
                    USING fund_entities fe
                    WHERE pgm.entity_id = fe.id
                      AND pgm.source = :source
                      AND fe.source = :source
                      AND fe.lifecycle_stage = 'inactive'
                """), {"source": source})
                conn.execute(text("""
                    UPDATE benchmark_mappings bm
                    SET status = 'inactive', updated_at = NOW()
                    FROM fund_entities fe
                    WHERE bm.entity_id = fe.id
                      AND bm.source = :source
                      AND fe.source = :source
                      AND fe.lifecycle_stage = 'inactive'
                      AND bm.status = 'active'
                """), {"source": source})

        self._schema_ready_cache = True
        return {
            "applied_groups": applied_groups,
            "applied_shares": applied_shares,
            "created_entities": created_entities,
            "reused_entities": reused_entities,
            "deactivated_shares": deactivated_shares,
            "deactivated_entities": deactivated_entities,
            "conflicts": conflicts,
        }

    def _schema_ready(self) -> bool:
        if self._schema_ready_cache:
            return True

        from sqlalchemy import text

        checks = " AND ".join(
            f"to_regclass('public.{table_name}') IS NOT NULL"
            for table_name in REQUIRED_TABLES
        )
        with self.engine.connect() as conn:
            row = conn.execute(text(f"SELECT ({checks}) AS schema_ready")).fetchone()
        ready = bool(row and dict(row._mapping).get("schema_ready"))
        self._schema_ready_cache = ready
        return ready

    def _build_context(self, row: Dict[str, Any]) -> Dict[str, Any]:
        benchmark_mapping = None
        if row.get("benchmark_code"):
            benchmark_mapping = {
                "benchmark_code": row.get("benchmark_code"),
                "benchmark_name": row.get("benchmark_name"),
                "benchmark_type": row.get("benchmark_type"),
                "mapping_method": row.get("mapping_method"),
                "confidence": row.get("benchmark_confidence"),
                "rationale": row.get("benchmark_rationale"),
                "evidence_refs": row.get("benchmark_evidence_refs"),
                "effective_from": row.get("effective_from"),
                "effective_to": row.get("effective_to"),
                "source": row.get("benchmark_source"),
            }

        missing_items = []
        if not row.get("strategy_family_key"):
            missing_items.append("基金实体缺少有效策略族谱")
        if not row.get("peer_group_id"):
            missing_items.append("基金实体缺少显式同类组成员关系")
        if not benchmark_mapping:
            missing_items.append("基金实体缺少评价时点有效的基准映射")

        evidence = [
            {
                "field": "fund_entity",
                "value": row.get("canonical_code"),
                "source": "fund_entities",
                "reason": "基金实体归一结果",
                "source_record": row.get("entity_source"),
                "source_updated_at": row.get("entity_source_updated_at"),
            },
            {
                "field": "fund_share_class.wind_code",
                "value": row.get("fund_code"),
                "source": "fund_share_classes",
                "reason": "基金份额到基金实体映射",
                "source_record": row.get("share_class_source"),
            },
        ]
        if row.get("strategy_family_key"):
            evidence.append({
                "field": "strategy_family.key",
                "value": row.get("strategy_family_key"),
                "source": "strategy_families",
                "reason": "标准化策略族谱",
                "source_record": row.get("strategy_family_source"),
            })
        if row.get("peer_group_id"):
            evidence.append({
                "field": "peer_group_members.peer_group_id",
                "value": row.get("peer_group_id"),
                "source": "peer_group_members",
                "reason": "显式同类组成员关系",
                "role": row.get("membership_role"),
                "matched_rules": row.get("matched_rules"),
                "excluded_rules": row.get("excluded_rules"),
                "sample_as_of_date": row.get("sample_as_of_date"),
                "confidence": row.get("membership_confidence"),
                "source_record": row.get("membership_source"),
            })
        if benchmark_mapping:
            evidence.append({
                "field": "benchmark_mappings.benchmark_code",
                "value": benchmark_mapping.get("benchmark_code"),
                "source": "benchmark_mappings",
                "reason": benchmark_mapping.get("rationale"),
                "mapping_method": benchmark_mapping.get("mapping_method"),
                "confidence": benchmark_mapping.get("confidence"),
                "effective_from": benchmark_mapping.get("effective_from"),
                "effective_to": benchmark_mapping.get("effective_to"),
                "source_record": benchmark_mapping.get("source"),
            })

        membership_confidence = row.get("membership_confidence")
        classification_confidence = membership_confidence if membership_confidence is not None else 0.95
        return {
            "status": "resolved",
            "fund_code": row.get("fund_code"),
            "entity_id": row.get("entity_id"),
            "canonical_code": row.get("canonical_code"),
            "canonical_name": row.get("canonical_name"),
            "share_class": row.get("share_class"),
            "strategy_family_key": row.get("strategy_family_key"),
            "strategy_family_name": row.get("strategy_family_name"),
            "asset_class": row.get("asset_class"),
            "active_passive": row.get("active_passive"),
            "peer_group_id": row.get("peer_group_id"),
            "peer_group_key": row.get("peer_group_key"),
            "peer_group_name": row.get("peer_group_name"),
            "minimum_peer_count": row.get("minimum_peer_count"),
            "peer_group_membership_count": row.get("peer_group_membership_count") or 0,
            "benchmark_mapping": benchmark_mapping,
            "classification_confidence": classification_confidence,
            "classification_evidence": evidence,
            "missing_items": missing_items,
        }

    def _unavailable(self, status: str, fund_code: str, missing_items: List[str]) -> Dict[str, Any]:
        return {
            "status": status,
            "fund_code": fund_code or None,
            "classification_evidence": [],
            "missing_items": missing_items,
        }
