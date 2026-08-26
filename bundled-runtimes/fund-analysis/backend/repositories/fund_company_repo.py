"""基金公司聚合查询。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

try:
    from backend.database import get_engine
except ModuleNotFoundError:
    from database import get_engine


COMPANY_EXPR = """
COALESCE(
    NULLIF(f.raw_data #>> '{universe,company}', ''),
    NULLIF(f.raw_data #>> '{info,company}', ''),
    NULLIF(f.raw_data ->> 'company', '')
)
"""


BASE_CTES = f"""
WITH base_funds AS NOT MATERIALIZED (
    SELECT
        f.id,
        f.wind_code,
        f.name,
        f.type,
        f.manager_ids,
        f.total_asset,
        f.nav,
        f.nav_date,
        f.establishment_date,
        f.performance_data,
        f.risk_metrics,
        f.updated_at,
        f.raw_data,
        {COMPANY_EXPR} AS company
    FROM funds f
    WHERE {COMPANY_EXPR} IS NOT NULL
),
latest_metrics AS (
    SELECT DISTINCT ON (target_id, metric_window, metric_name)
        target_id,
        metric_window,
        metric_name,
        metric_value,
        as_of_date
    FROM metric_snapshots
    WHERE target_type = 'fund'
      AND metric_window IN ('3m', '6m', '1y', '3y')
      AND metric_name IN ('total_return', 'annualized_return', 'max_drawdown', 'sharpe_ratio')
    ORDER BY target_id, metric_window, metric_name, as_of_date DESC, updated_at DESC
),
fund_window_metrics AS (
    SELECT
        target_id,
        metric_window,
        MAX(metric_value) FILTER (WHERE metric_name = 'total_return') AS total_return,
        MAX(metric_value) FILTER (WHERE metric_name = 'annualized_return') AS annualized_return,
        MAX(metric_value) FILTER (WHERE metric_name = 'max_drawdown') AS max_drawdown,
        MAX(metric_value) FILTER (WHERE metric_name = 'sharpe_ratio') AS sharpe_ratio,
        MAX(as_of_date) AS as_of_date
    FROM latest_metrics
    GROUP BY target_id, metric_window
),
fund_metrics_1y AS (
    SELECT * FROM fund_window_metrics WHERE metric_window = '1y'
),
manager_links AS (
    SELECT bf.company, bf.wind_code, manager_id
    FROM base_funds bf
    CROSS JOIN LATERAL unnest(COALESCE(bf.manager_ids, ARRAY[]::TEXT[])) AS manager_id
    UNION
    SELECT bf.company, bf.wind_code, m.wind_code AS manager_id
    FROM managers m
    CROSS JOIN LATERAL unnest(COALESCE(m.current_funds, ARRAY[]::TEXT[])) AS fund_code
    JOIN base_funds bf ON bf.wind_code = fund_code
    WHERE m.wind_code IS NOT NULL
),
manager_counts AS (
    SELECT company, COUNT(DISTINCT manager_id) AS manager_count
    FROM manager_links
    GROUP BY company
),
standardized_funds AS (
    SELECT DISTINCT fsc.wind_code
    FROM fund_share_classes fsc
    JOIN peer_group_members pgm ON pgm.entity_id = fsc.entity_id
),
standardized_fund_groups AS (
    SELECT DISTINCT fsc.wind_code, pgm.peer_group_id
    FROM fund_share_classes fsc
    JOIN peer_group_members pgm
      ON pgm.entity_id = fsc.entity_id
     AND pgm.role <> 'excluded'
)
"""


class FundCompanyRepo:
    def __init__(self, engine: Any = None):
        self._engine = engine

    @property
    def engine(self):
        if self._engine is None:
            self._engine = get_engine()
        return self._engine

    def list_companies(
        self,
        keyword: Optional[str] = None,
        page: int = 1,
        page_size: int = 30,
        sort_by: str = "fund_count",
    ) -> Tuple[List[Dict[str, Any]], int]:
        from sqlalchemy import text

        normalized_keyword = str(keyword or "").strip()
        limit = max(1, min(int(page_size), 100))
        sort_sql = {
            "fund_count": "fund_count DESC, company ASC",
            "asset": "synced_total_asset DESC NULLS LAST, fund_count DESC, company ASC",
            "coverage": "metric_ready_count DESC, fund_count DESC, company ASC",
            "category_coverage": "evaluated_peer_group_count DESC, peer_group_count DESC, fund_count DESC, company ASC",
        }.get(sort_by, "fund_count DESC, company ASC")
        params = {
            "keyword": normalized_keyword,
            "keyword_pattern": f"%{normalized_keyword}%",
            "limit": limit,
            "offset": max(0, int(page) - 1) * limit,
        }
        aggregate_sql = f"""
        company_stats AS (
            SELECT
                bf.company,
                COUNT(*) AS fund_count,
                COUNT(bf.total_asset) AS asset_sample_count,
                SUM(bf.total_asset) AS synced_total_asset,
                COUNT(sf.wind_code) AS classified_count,
                COUNT(fm.target_id) FILTER (WHERE fm.annualized_return IS NOT NULL) AS metric_ready_count,
                percentile_cont(0.5) WITHIN GROUP (ORDER BY fm.annualized_return)
                    FILTER (WHERE bf.type IN ('股票型', '混合型', '指数型') AND fm.annualized_return IS NOT NULL)
                    AS equity_return_1y,
                COUNT(fm.target_id)
                    FILTER (WHERE bf.type IN ('股票型', '混合型', '指数型') AND fm.annualized_return IS NOT NULL)
                    AS equity_sample_count,
                percentile_cont(0.5) WITHIN GROUP (ORDER BY fm.annualized_return)
                    FILTER (WHERE bf.type = '债券型' AND fm.annualized_return IS NOT NULL)
                    AS bond_return_1y,
                COUNT(fm.target_id)
                    FILTER (WHERE bf.type = '债券型' AND fm.annualized_return IS NOT NULL)
                    AS bond_sample_count,
                MAX(fm.as_of_date) AS metric_as_of,
                MAX(bf.updated_at) AS fund_data_updated_at
            FROM base_funds bf
            LEFT JOIN fund_metrics_1y fm ON fm.target_id = bf.wind_code
            LEFT JOIN standardized_funds sf ON sf.wind_code = bf.wind_code
            WHERE (:keyword = '' OR bf.company ILIKE :keyword_pattern)
            GROUP BY bf.company
        ),
        company_peer_group_stats AS (
            SELECT
                bf.company,
                COUNT(DISTINCT sfg.peer_group_id) AS peer_group_count,
                COUNT(DISTINCT sfg.peer_group_id)
                    FILTER (WHERE fm.annualized_return IS NOT NULL) AS evaluated_peer_group_count
            FROM base_funds bf
            JOIN standardized_fund_groups sfg ON sfg.wind_code = bf.wind_code
            LEFT JOIN fund_metrics_1y fm ON fm.target_id = bf.wind_code
            WHERE (:keyword = '' OR bf.company ILIKE :keyword_pattern)
            GROUP BY bf.company
        )
        """
        data_sql = text(f"""
            {BASE_CTES},
            {aggregate_sql}
            SELECT
                cs.*,
                COALESCE(mc.manager_count, 0) AS manager_count,
                COALESCE(cpg.peer_group_count, 0) AS peer_group_count,
                COALESCE(cpg.evaluated_peer_group_count, 0) AS evaluated_peer_group_count
            FROM company_stats cs
            LEFT JOIN manager_counts mc ON mc.company = cs.company
            LEFT JOIN company_peer_group_stats cpg ON cpg.company = cs.company
            ORDER BY {sort_sql}
            LIMIT :limit OFFSET :offset
        """)
        count_sql = text(f"""
            WITH base_funds AS (
                SELECT {COMPANY_EXPR} AS company
                FROM funds f
                WHERE {COMPANY_EXPR} IS NOT NULL
            )
            SELECT COUNT(DISTINCT company)
            FROM base_funds
            WHERE (:keyword = '' OR company ILIKE :keyword_pattern)
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(data_sql, params).fetchall()
            total = int(conn.execute(count_sql, params).scalar() or 0)
        return [dict(row._mapping) for row in rows], total

    def get_market_summary(self) -> Dict[str, Any]:
        from sqlalchemy import text

        sql = text(f"""
            {BASE_CTES}
            SELECT
                (SELECT COUNT(DISTINCT company) FROM base_funds) AS company_count,
                (SELECT COUNT(*) FROM base_funds) AS fund_count,
                (SELECT COUNT(total_asset) FROM base_funds) AS asset_sample_count,
                (SELECT COUNT(*) FROM standardized_funds sf JOIN base_funds bf ON bf.wind_code = sf.wind_code) AS classified_count,
                (SELECT COUNT(DISTINCT peer_group_id) FROM standardized_fund_groups) AS peer_group_count,
                (
                    SELECT COUNT(DISTINCT sfg.peer_group_id)
                    FROM standardized_fund_groups sfg
                    JOIN fund_metrics_1y fm ON fm.target_id = sfg.wind_code
                    WHERE fm.annualized_return IS NOT NULL
                ) AS evaluated_peer_group_count,
                (SELECT COUNT(*) FROM fund_metrics_1y fm JOIN base_funds bf ON bf.wind_code = fm.target_id WHERE fm.annualized_return IS NOT NULL) AS metric_ready_count,
                (SELECT COUNT(DISTINCT manager_id) FROM manager_links) AS manager_count,
                (SELECT MAX(as_of_date) FROM fund_metrics_1y) AS metric_as_of,
                (SELECT MAX(updated_at) FROM base_funds) AS fund_data_updated_at
        """)
        with self.engine.connect() as conn:
            row = conn.execute(sql).fetchone()
        return dict(row._mapping) if row else {}

    def get_company(self, company: str) -> Optional[Dict[str, Any]]:
        from sqlalchemy import text

        sql = text(f"""
            {BASE_CTES}
            SELECT
                bf.company,
                COUNT(*) AS fund_count,
                COUNT(bf.total_asset) AS asset_sample_count,
                SUM(bf.total_asset) AS synced_total_asset,
                COUNT(sf.wind_code) AS classified_count,
                COUNT(fm.target_id) FILTER (WHERE fm.annualized_return IS NOT NULL) AS metric_ready_count,
                COALESCE(MAX(mc.manager_count), 0) AS manager_count,
                MIN(bf.establishment_date) AS earliest_fund_date,
                MAX(fm.as_of_date) AS metric_as_of,
                MAX(bf.updated_at) AS fund_data_updated_at
            FROM base_funds bf
            LEFT JOIN fund_metrics_1y fm ON fm.target_id = bf.wind_code
            LEFT JOIN standardized_funds sf ON sf.wind_code = bf.wind_code
            LEFT JOIN manager_counts mc ON mc.company = bf.company
            WHERE bf.company = :company
            GROUP BY bf.company
        """)
        with self.engine.connect() as conn:
            row = conn.execute(sql, {"company": company}).fetchone()
        return dict(row._mapping) if row else None

    def get_category_breakdown(self, company: str) -> List[Dict[str, Any]]:
        from sqlalchemy import text

        sql = text(f"""
            {BASE_CTES},
            company_entity_funds AS (
                SELECT DISTINCT ON (fe.id)
                    fe.id AS entity_id,
                    bf.wind_code,
                    bf.total_asset,
                    bf.establishment_date,
                    pg.id AS peer_group_id,
                    pg.key AS peer_group_key,
                    pg.name AS peer_group_name,
                    pg.asset_class,
                    pg.active_passive
                FROM base_funds bf
                JOIN fund_share_classes fsc
                  ON fsc.wind_code = bf.wind_code
                 AND fsc.status = 'active'
                JOIN fund_entities fe ON fe.id = fsc.entity_id
                JOIN peer_group_members pgm
                  ON pgm.entity_id = fe.id
                 AND pgm.role <> 'excluded'
                JOIN peer_groups pg ON pg.id = pgm.peer_group_id
                LEFT JOIN fund_metrics_1y fm ON fm.target_id = bf.wind_code
                WHERE bf.company = :company
                ORDER BY
                    fe.id,
                    fsc.is_primary DESC,
                    CASE WHEN fm.annualized_return IS NULL THEN 1 ELSE 0 END,
                    bf.total_asset DESC NULLS LAST,
                    bf.wind_code ASC
            ),
            category_share_counts AS (
                SELECT
                    pg.id AS peer_group_id,
                    COUNT(DISTINCT bf.wind_code) AS share_count
                FROM base_funds bf
                JOIN fund_share_classes fsc
                  ON fsc.wind_code = bf.wind_code
                 AND fsc.status = 'active'
                JOIN peer_group_members pgm
                  ON pgm.entity_id = fsc.entity_id
                 AND pgm.role <> 'excluded'
                JOIN peer_groups pg ON pg.id = pgm.peer_group_id
                WHERE bf.company = :company
                GROUP BY pg.id
            )
            SELECT
                cef.peer_group_id,
                cef.peer_group_key,
                cef.peer_group_name,
                cef.asset_class,
                cef.active_passive,
                COUNT(*) AS fund_count,
                COUNT(*) FILTER (
                    WHERE cef.establishment_date IS NOT NULL
                      AND cef.establishment_date <= CURRENT_DATE - INTERVAL '430 days'
                ) AS mature_fund_count,
                MAX(csc.share_count) AS share_count,
                COUNT(cef.total_asset) AS asset_sample_count,
                SUM(cef.total_asset) AS synced_total_asset,
                COUNT(fm.target_id) FILTER (WHERE fm.annualized_return IS NOT NULL) AS return_sample_count,
                percentile_cont(0.5) WITHIN GROUP (ORDER BY fm.annualized_return)
                    FILTER (WHERE fm.annualized_return IS NOT NULL) AS return_1y,
                percentile_cont(0.5) WITHIN GROUP (ORDER BY fm.max_drawdown)
                    FILTER (WHERE fm.max_drawdown IS NOT NULL) AS max_drawdown_1y,
                percentile_cont(0.5) WITHIN GROUP (ORDER BY fm.sharpe_ratio)
                    FILTER (WHERE fm.sharpe_ratio IS NOT NULL) AS sharpe_1y,
                MAX(fm.as_of_date) AS metric_as_of
            FROM company_entity_funds cef
            LEFT JOIN category_share_counts csc ON csc.peer_group_id = cef.peer_group_id
            LEFT JOIN fund_metrics_1y fm ON fm.target_id = cef.wind_code
            GROUP BY
                cef.peer_group_id,
                cef.peer_group_key,
                cef.peer_group_name,
                cef.asset_class,
                cef.active_passive
            ORDER BY fund_count DESC, cef.peer_group_name ASC
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {"company": company}).fetchall()
        return [dict(row._mapping) for row in rows]

    def get_company_representative_funds(
        self,
        company: str,
        per_category: int = 3,
        limit: int = 60,
    ) -> List[Dict[str, Any]]:
        """按标准化同类组挑选少量评价候选，再交由服务层执行专业评分。"""
        from sqlalchemy import text

        sql = text(f"""
            {BASE_CTES},
            entity_candidates AS (
                SELECT DISTINCT ON (fe.id)
                    bf.*,
                    fe.id AS entity_id,
                    pg.id AS standardized_peer_group_id,
                    pg.key AS standardized_peer_group_key,
                    pg.name AS standardized_peer_group_name,
                    pg.asset_class AS standardized_asset_class,
                    pg.active_passive AS standardized_active_passive,
                    (
                        (fm.annualized_return IS NOT NULL)::int
                        + (fm.max_drawdown IS NOT NULL)::int
                        + (fm.sharpe_ratio IS NOT NULL)::int
                    ) AS metric_evidence_count,
                    fm.annualized_return AS annualized_return_1y,
                    fm.max_drawdown AS max_drawdown_1y,
                    fm.sharpe_ratio AS sharpe_1y,
                    fm.as_of_date AS metric_as_of
                FROM base_funds bf
                JOIN fund_share_classes fsc
                  ON fsc.wind_code = bf.wind_code
                 AND fsc.status = 'active'
                JOIN fund_entities fe ON fe.id = fsc.entity_id
                JOIN peer_group_members pgm
                  ON pgm.entity_id = fe.id
                 AND pgm.role <> 'excluded'
                JOIN peer_groups pg ON pg.id = pgm.peer_group_id
                LEFT JOIN fund_metrics_1y fm ON fm.target_id = bf.wind_code
                WHERE bf.company = :company
                  AND fe.lifecycle_stage = 'active'
                ORDER BY
                    fe.id,
                    fsc.is_primary DESC,
                    (
                        (fm.annualized_return IS NOT NULL)::int
                        + (fm.max_drawdown IS NOT NULL)::int
                        + (fm.sharpe_ratio IS NOT NULL)::int
                    ) DESC,
                    bf.total_asset DESC NULLS LAST,
                    bf.wind_code ASC
            ),
            ranked AS (
                SELECT
                    entity_candidates.*,
                    COUNT(*) OVER (PARTITION BY standardized_peer_group_id) AS category_fund_count,
                    ROW_NUMBER() OVER (
                        PARTITION BY standardized_peer_group_id
                        ORDER BY
                            metric_evidence_count DESC,
                            sharpe_1y DESC NULLS LAST,
                            max_drawdown_1y DESC NULLS LAST,
                            total_asset DESC NULLS LAST,
                            wind_code ASC
                    ) AS category_rank
                FROM entity_candidates
            )
            SELECT *
            FROM ranked
            WHERE category_rank <= :per_category
            ORDER BY category_rank ASC, category_fund_count DESC, standardized_peer_group_name ASC
            LIMIT :limit
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {
                "company": company,
                "per_category": max(1, min(int(per_category), 5)),
                "limit": max(1, min(int(limit), 100)),
            }).fetchall()
        return [dict(row._mapping) for row in rows]

    def get_category_window_performance(self, company: str) -> List[Dict[str, Any]]:
        from sqlalchemy import text

        sql = text(f"""
            {BASE_CTES},
            fund_metric_coverage AS (
                SELECT
                    target_id,
                    COUNT(*) FILTER (WHERE total_return IS NOT NULL) AS return_window_count
                FROM fund_window_metrics
                GROUP BY target_id
            ),
            company_entity_funds AS (
                SELECT DISTINCT ON (fe.id)
                    fe.id AS entity_id,
                    bf.wind_code,
                    pg.id AS peer_group_id,
                    pg.key AS peer_group_key,
                    pg.name AS peer_group_name,
                    pg.asset_class,
                    pg.active_passive
                FROM base_funds bf
                JOIN fund_share_classes fsc
                  ON fsc.wind_code = bf.wind_code
                 AND fsc.status = 'active'
                JOIN fund_entities fe ON fe.id = fsc.entity_id
                JOIN peer_group_members pgm
                  ON pgm.entity_id = fe.id
                 AND pgm.role <> 'excluded'
                JOIN peer_groups pg ON pg.id = pgm.peer_group_id
                LEFT JOIN fund_metric_coverage fmc ON fmc.target_id = bf.wind_code
                WHERE bf.company = :company
                ORDER BY
                    fe.id,
                    COALESCE(fmc.return_window_count, 0) DESC,
                    fsc.is_primary DESC,
                    pgm.sample_as_of_date DESC NULLS LAST,
                    pgm.confidence DESC NULLS LAST,
                    bf.wind_code ASC
            ),
            company_group_sizes AS (
                SELECT peer_group_id, COUNT(*) AS fund_count
                FROM company_entity_funds
                GROUP BY peer_group_id
            )
            SELECT
                cef.peer_group_id,
                cef.peer_group_key,
                cef.peer_group_name,
                cef.asset_class,
                cef.active_passive,
                MAX(cgs.fund_count) AS fund_count,
                fwm.metric_window,
                COUNT(fwm.target_id) FILTER (WHERE fwm.total_return IS NOT NULL) AS return_sample_count,
                COUNT(fwm.target_id) FILTER (WHERE fwm.max_drawdown IS NOT NULL) AS drawdown_sample_count,
                COUNT(fwm.target_id) FILTER (WHERE fwm.sharpe_ratio IS NOT NULL) AS sharpe_sample_count,
                percentile_cont(0.5) WITHIN GROUP (ORDER BY fwm.total_return)
                    FILTER (WHERE fwm.total_return IS NOT NULL) AS total_return,
                percentile_cont(0.5) WITHIN GROUP (ORDER BY fwm.max_drawdown)
                    FILTER (WHERE fwm.max_drawdown IS NOT NULL) AS max_drawdown,
                percentile_cont(0.5) WITHIN GROUP (ORDER BY fwm.sharpe_ratio)
                    FILTER (WHERE fwm.sharpe_ratio IS NOT NULL) AS sharpe_ratio,
                MAX(fwm.as_of_date) AS metric_as_of
            FROM company_entity_funds cef
            JOIN company_group_sizes cgs ON cgs.peer_group_id = cef.peer_group_id
            JOIN fund_window_metrics fwm ON fwm.target_id = cef.wind_code
            GROUP BY
                cef.peer_group_id,
                cef.peer_group_key,
                cef.peer_group_name,
                cef.asset_class,
                cef.active_passive,
                fwm.metric_window
            HAVING
                COUNT(fwm.target_id) FILTER (WHERE fwm.total_return IS NOT NULL) > 0
                OR COUNT(fwm.target_id) FILTER (WHERE fwm.max_drawdown IS NOT NULL) > 0
                OR COUNT(fwm.target_id) FILTER (WHERE fwm.sharpe_ratio IS NOT NULL) > 0
            ORDER BY
                MAX(cgs.fund_count) DESC,
                cef.peer_group_name ASC,
                CASE fwm.metric_window
                    WHEN '3m' THEN 1 WHEN '6m' THEN 2 WHEN '1y' THEN 3 WHEN '3y' THEN 4 ELSE 5
                END
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {"company": company}).fetchall()
        return [dict(row._mapping) for row in rows]

    def get_company_funds(self, company: str, limit: int = 30) -> List[Dict[str, Any]]:
        from sqlalchemy import text

        sql = text(f"""
            {BASE_CTES}
            SELECT
                bf.wind_code,
                bf.name,
                bf.type,
                bf.manager_ids,
                bf.total_asset,
                bf.nav,
                bf.nav_date,
                bf.establishment_date,
                fm.annualized_return AS annualized_return_1y,
                fm.max_drawdown AS max_drawdown_1y,
                fm.sharpe_ratio AS sharpe_1y,
                fm.as_of_date AS metric_as_of
            FROM base_funds bf
            LEFT JOIN fund_metrics_1y fm ON fm.target_id = bf.wind_code
            WHERE bf.company = :company
            ORDER BY
                CASE WHEN fm.sharpe_ratio IS NULL THEN 1 ELSE 0 END,
                fm.sharpe_ratio DESC NULLS LAST,
                fm.max_drawdown DESC NULLS LAST,
                fm.annualized_return DESC NULLS LAST,
                bf.total_asset DESC NULLS LAST,
                bf.wind_code ASC
            LIMIT :limit
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {"company": company, "limit": max(1, min(limit, 100))}).fetchall()
        return [dict(row._mapping) for row in rows]

    def get_company_managers(self, company: str, limit: int = 20) -> List[Dict[str, Any]]:
        from sqlalchemy import text

        sql = text(f"""
            {BASE_CTES},
            manager_fund_rows AS (
                SELECT
                    ml.manager_id,
                    bf.wind_code,
                    bf.name AS fund_name,
                    bf.total_asset,
                    fm.annualized_return AS annualized_return_1y,
                    fm.max_drawdown AS max_drawdown_1y,
                    fm.sharpe_ratio AS sharpe_1y,
                    peer.peer_group_name
                FROM manager_links ml
                JOIN base_funds bf
                  ON bf.company = ml.company
                 AND bf.wind_code = ml.wind_code
                LEFT JOIN fund_metrics_1y fm ON fm.target_id = bf.wind_code
                LEFT JOIN LATERAL (
                    SELECT pg.name AS peer_group_name
                    FROM fund_share_classes fsc
                    JOIN peer_group_members pgm
                      ON pgm.entity_id = fsc.entity_id
                     AND pgm.role <> 'excluded'
                    JOIN peer_groups pg ON pg.id = pgm.peer_group_id
                    WHERE fsc.wind_code = bf.wind_code
                      AND fsc.status = 'active'
                    ORDER BY pgm.sample_as_of_date DESC NULLS LAST, pgm.confidence DESC NULLS LAST
                    LIMIT 1
                ) peer ON TRUE
                WHERE ml.company = :company
            ),
            manager_summary AS (
                SELECT
                    manager_id,
                    COUNT(DISTINCT wind_code) AS current_fund_count,
                    MAX(total_asset) AS largest_fund_asset
                FROM manager_fund_rows
                GROUP BY manager_id
            ),
            manager_representatives AS (
                SELECT
                    manager_fund_rows.*,
                    ROW_NUMBER() OVER (
                        PARTITION BY manager_id
                        ORDER BY
                            CASE WHEN sharpe_1y IS NULL THEN 1 ELSE 0 END,
                            sharpe_1y DESC NULLS LAST,
                            max_drawdown_1y DESC NULLS LAST,
                            total_asset DESC NULLS LAST,
                            wind_code ASC
                    ) AS representative_rank
                FROM manager_fund_rows
            )
            SELECT
                ms.manager_id AS wind_code,
                COALESCE(NULLIF(m.name, ''), NULLIF(split_part(ms.manager_id, '|', 1), ''), ms.manager_id) AS name,
                m.education,
                m.work_years,
                m.management_years,
                ms.current_fund_count,
                ms.largest_fund_asset,
                representative.wind_code AS representative_fund_code,
                representative.fund_name AS representative_fund_name,
                representative.peer_group_name AS representative_peer_group,
                representative.annualized_return_1y AS representative_return_1y,
                representative.max_drawdown_1y AS representative_max_drawdown_1y,
                representative.sharpe_1y AS representative_sharpe_1y
            FROM manager_summary ms
            LEFT JOIN LATERAL (
                SELECT manager.*
                FROM managers manager
                WHERE manager.wind_code = ms.manager_id
                   OR manager.name = ms.manager_id
                   OR manager.name = split_part(ms.manager_id, '|', 1)
                ORDER BY (manager.wind_code = ms.manager_id) DESC, manager.updated_at DESC
                LIMIT 1
            ) m ON TRUE
            LEFT JOIN manager_representatives representative
              ON representative.manager_id = ms.manager_id
             AND representative.representative_rank = 1
            ORDER BY
                CASE WHEN m.management_years IS NULL THEN 1 ELSE 0 END,
                m.management_years DESC NULLS LAST,
                ms.largest_fund_asset DESC NULLS LAST,
                ms.current_fund_count DESC,
                name ASC
            LIMIT :limit
        """)
        with self.engine.connect() as conn:
            rows = conn.execute(sql, {"company": company, "limit": max(1, min(limit, 100))}).fetchall()
        return [dict(row._mapping) for row in rows]
