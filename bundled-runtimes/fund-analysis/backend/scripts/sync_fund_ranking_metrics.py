#!/usr/bin/env python3
"""
同步基金筛选榜单所需的真实净值与滚动指标。

只做基金研究筛选数据底座：
- 拉取 Tushare fund_nav
- 写入 fund_nav
- 计算 3M/6M/1Y/3Y 滚动指标
- 回写 funds.performance_data / funds.risk_metrics / 最新净值

不生成报告，不输出申赎建议，不改变销售规则/R1-R5 门禁。
"""
import argparse
import json
import os
import sys
import time
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy import text

BASE_DIR = Path(__file__).resolve().parents[1]
ROOT_DIR = BASE_DIR.parent
sys.path.insert(0, str(BASE_DIR))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT_DIR / ".env.local")
    load_dotenv(ROOT_DIR / ".env")
    load_dotenv(BASE_DIR / ".env")
except Exception:
    pass

from database import get_engine, init_database
from lib.fund_status import active_fund_sql
from repositories import (
    get_fund_classification_repo,
    get_fund_repo,
    get_metric_snapshot_repo,
    get_nav_repo,
)
from services.fund_classification_catalog import FundClassificationCatalog
from services.fund_classification_service import FundClassificationService
from services.fund_classification_ingestion_service import FundClassificationIngestionService
from services.fund_nav_evidence_service import FundNavDataEnrichmentService
from services.fund_manager_research_service import FundManagerResearchService
from services.fund_manager_tenure_sync_service import FundManagerTenureSyncService
from services.manager_tenure_peer_ranking_service import ManagerTenurePeerRankingService
from services.peer_comparison_service import PeerComparisonService
from services.professional_scoring_service import ProfessionalScoringService
from services.rolling_metric_service import RollingMetricService
from services.tushare_service import TushareDataService


DEFAULT_PEER_COVERAGE_GROUPS = tuple(
    group["key"] for group in FundClassificationCatalog.peer_groups()
)

BROWSER_CORE_PEER_GROUPS = (
    "peer-index-hs300",
    "peer-index-csi-a500",
    "peer-index-csi500",
    "peer-active-equity-stock-hs300",
    "peer-mixed-equity-allocation",
    "peer-fixed-income-csi-total-bond",
    "peer-money-cash-management",
    "peer-active-equity-sector-consumption",
    "peer-index-enhanced-hs300",
    "peer-index-chinext",
    "peer-qdii-index-ndx-cny",
)
BROWSER_CORE_TARGET_PER_GROUP = 10
COMPANY_EVALUATION_TARGET_PER_GROUP = 3
MANAGER_TENURE_EXCLUDED_FAMILIES = {
    "cash_management",
    "index_broad",
    "index_fixed_income",
}
FOF_EVALUATION_PROFILES = {"fof_equity", "fof_balanced", "fof_bond"}
FOF_PEER_GROUP_KEYS = (
    "peer-fof-equity-allocation",
    "peer-fof-balanced-allocation",
    "peer-fof-bond-allocation",
)


def log(message: str) -> None:
    print(message, flush=True)


def fund_company_sql(alias: str = "fund") -> str:
    return f"""
        COALESCE(
            NULLIF({alias}.raw_data #>> '{{universe,company}}', ''),
            NULLIF({alias}.raw_data #>> '{{info,company}}', ''),
            NULLIF({alias}.raw_data ->> 'company', '')
        )
    """.strip()


def number_or_none(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        number_value = float(value)
    except (TypeError, ValueError):
        return None
    if number_value != number_value or number_value in (float("inf"), float("-inf")):
        return None
    return number_value


def manager_tenure_required(classification_context: Dict[str, Any]) -> bool:
    """只为主动管理类别同步经理任期。

    被动指数、固收指数和货币基金的类别评价不依赖经理任期。
    """
    if classification_context.get("status") != "resolved":
        return False
    family_key = str(classification_context.get("strategy_family_key") or "").strip()
    if not family_key or family_key in MANAGER_TENURE_EXCLUDED_FAMILIES:
        return False
    return str(classification_context.get("active_passive") or "").strip() != "passive"


def sync_fof_lookthrough(
    wind_code: str,
    classification_context: Dict[str, Any],
    fof_holding_service: Optional[Any] = None,
) -> Dict[str, Any]:
    """FOF 评价补数时同步公开底层基金持仓，普通基金直接跳过。"""
    family_key = str(classification_context.get("strategy_family_key") or "").strip()
    profile_key = str(
        classification_context.get("evaluation_profile_key")
        or (FundClassificationService.FAMILY_META.get(family_key) or {}).get("evaluation_profile_key")
        or ""
    ).strip()
    if profile_key not in FOF_EVALUATION_PROFILES:
        return {"status": "not_applicable"}
    if fof_holding_service is None:
        from services.fund_fof_holding_service import FundFofHoldingService

        fof_holding_service = FundFofHoldingService()
    result = fof_holding_service.get(wind_code, limit=20, refresh=True)
    gate = result.get("evidence_gate") or {}
    profile = result.get("professional_profile") or {}
    return {
        "status": result.get("status") or "unavailable",
        "evidence_gate_status": gate.get("status") or "insufficient_evidence",
        "report_date": (result.get("latest") or {}).get("report_date"),
        "disclosed_fund_count": int(profile.get("disclosed_fund_count") or 0),
        "disclosed_nav_ratio": number_or_none(profile.get("disclosed_nav_ratio")) or 0.0,
        "source": result.get("source"),
        "missing_items": gate.get("missing_items") or result.get("missing_items") or [],
    }


def metric_by_window(panel: Iterable[Dict[str, Any]], window: str) -> Dict[str, float]:
    result: Dict[str, float] = {}
    for row in panel:
        if row.get("metric_window") != window:
            continue
        metric_name = str(row.get("metric_name") or "")
        metric_value = number_or_none(row.get("metric_value"))
        if metric_name and metric_value is not None:
            result[metric_name] = metric_value
    return result


def latest_nav_payload(nav_series: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not nav_series:
        return {}
    latest = nav_series[-1]
    latest_asset_row = next(
        (
            item
            for item in reversed(nav_series)
            if number_or_none(item.get("total_netasset") or item.get("net_asset")) is not None
        ),
        {},
    )
    return {
        "nav": number_or_none(latest.get("unit_nav") or latest.get("nav")),
        "nav_date": latest.get("date"),
        "total_asset": asset_to_yi(
            latest_asset_row.get("total_netasset") or latest_asset_row.get("net_asset")
        ),
        "total_asset_as_of": latest_asset_row.get("date"),
        "total_asset_source": "tushare.fund_nav.latest_reported_net_asset" if latest_asset_row else None,
    }


def asset_to_yi(value: Any) -> Optional[float]:
    parsed = number_or_none(value)
    if parsed is None or parsed <= 0:
        return None
    if parsed >= 1_000_000:
        return round(parsed / 100_000_000, 4)
    if parsed >= 100:
        return round(parsed / 10_000, 4)
    return round(parsed, 4)


def build_fund_metric_payload(panel: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    one_year = metric_by_window(panel, "1y")
    three_year = metric_by_window(panel, "3y")
    six_month = metric_by_window(panel, "6m")

    performance_data = {
        "source": "metric_snapshots.tushare_fund_nav",
        "annualized_return_1y": one_year.get("annualized_return"),
        "return_1y": one_year.get("total_return"),
        "total_return": one_year.get("total_return"),
        "annualized_return_3y": three_year.get("annualized_return"),
        "return_3y": three_year.get("total_return"),
        "return_6m": six_month.get("total_return"),
        "sharpe_ratio": one_year.get("sharpe_ratio"),
        "positive_return_ratio": one_year.get("positive_return_ratio"),
        "benchmark_return_1y": one_year.get("benchmark_return"),
        "excess_return": one_year.get("excess_return"),
        "tracking_difference": one_year.get("excess_return"),
        "observations_1y": one_year.get("observations"),
        "updated_at": datetime.now(UTC).isoformat(),
    }
    risk_metrics = {
        "source": "metric_snapshots.tushare_fund_nav",
        "max_drawdown_1y": one_year.get("max_drawdown"),
        "max_drawdown": one_year.get("max_drawdown"),
        "annualized_volatility_1y": one_year.get("annualized_volatility"),
        "volatility_1y": one_year.get("annualized_volatility"),
        "sortino_ratio_1y": one_year.get("sortino_ratio"),
        "calmar_ratio_1y": one_year.get("calmar_ratio"),
        "tracking_error": one_year.get("tracking_error"),
        "information_ratio": one_year.get("information_ratio"),
        "max_drawdown_3y": three_year.get("max_drawdown"),
        "annualized_volatility_3y": three_year.get("annualized_volatility"),
        "updated_at": datetime.now(UTC).isoformat(),
    }

    clean_performance = {key: value for key, value in performance_data.items() if value is not None}
    clean_risk = {key: value for key, value in risk_metrics.items() if value is not None}
    return {"performance_data": clean_performance, "risk_metrics": clean_risk}


def save_latest_fund_facts(
    metric_repo: Any,
    wind_code: str,
    fund: Dict[str, Any],
    as_of_date: date,
) -> int:
    """把真实规模和费率写入权威指标快照，供类别专属评价使用。"""
    latest = ProfessionalScoringService().metric_facts_from_fund(fund).get("latest") or {}
    saved = 0
    for metric_name, metric_unit in (("expense_ratio", "ratio"), ("aum", "cny_100m")):
        metric_value = number_or_none(latest.get(metric_name))
        if metric_value is None:
            continue
        metric_repo.upsert_metric(
            target_type="fund",
            target_id=wind_code,
            as_of_date=as_of_date,
            metric_name=metric_name,
            metric_value=Decimal(str(metric_value)),
            metric_unit=metric_unit,
            window="latest",
            details={
                "source": "funds.total_asset+funds.raw_data.tushare",
                "calculation_engine": "ProfessionalScoringService.metric_facts_from_fund",
            },
        )
        saved += 1
    return saved


def save_enrichment_metric_facts(
    metric_repo: Any,
    wind_code: str,
    enrichment: Dict[str, Any],
    as_of_date: date,
) -> int:
    """把货币基金和基准对齐的真实派生事实写入统一指标表。"""
    facts = enrichment.get("performance_facts") or {}
    metric_units = {
        "seven_day_annualized_yield": "ratio",
        "income_per_10000": "cny_per_10000",
        "benchmark_annualized_rate": "ratio",
        "benchmark_yield_spread": "ratio",
    }
    saved = 0
    for metric_name, metric_unit in metric_units.items():
        metric_value = number_or_none(facts.get(metric_name))
        if metric_value is None:
            continue
        metric_repo.upsert_metric(
            target_type="fund",
            target_id=wind_code,
            as_of_date=as_of_date,
            metric_name=metric_name,
            metric_value=Decimal(str(metric_value)),
            metric_unit=metric_unit,
            window="latest",
            details={
                "source": facts.get(f"{metric_name}_source")
                or facts.get("seven_day_yield_source")
                or "fund_nav_evidence_service",
                "calculation_engine": "FundNavDataEnrichmentService",
            },
        )
        saved += 1
    return saved


def invalidate_nav_derived_evaluation_facts(wind_code: str, validation: Dict[str, Any]) -> None:
    """移除已被净值质量门禁否定的派生指标，避免旧快照继续参与评分。"""
    performance_keys = [
        "annualized_return_1y", "return_1y", "total_return", "annualized_return_3y",
        "return_3y", "return_6m", "sharpe_ratio", "positive_return_ratio",
        "benchmark_return_1y", "excess_return", "tracking_difference", "observations_1y",
        "seven_day_annualized_yield", "income_per_10000", "benchmark_yield_spread",
    ]
    risk_keys = [
        "max_drawdown_1y", "max_drawdown", "annualized_volatility_1y", "volatility_1y",
        "sortino_ratio_1y", "calmar_ratio_1y", "tracking_error", "information_ratio",
        "max_drawdown_3y", "annualized_volatility_3y",
    ]
    marker = {
        "ranking_metrics": {
            "status": "invalid_nav",
            "validation": validation,
            "invalidated_at": datetime.now(UTC).isoformat(),
        }
    }
    with get_engine().begin() as conn:
        conn.execute(text("""
            DELETE FROM metric_snapshots
            WHERE target_type = 'fund'
              AND target_id = :wind_code
              AND metric_window IN ('3m', '6m', '1y', '3y')
        """), {"wind_code": wind_code})
        conn.execute(text("""
            UPDATE funds
            SET performance_data = COALESCE(performance_data, '{}'::jsonb) - CAST(:performance_keys AS text[]),
                risk_metrics = COALESCE(risk_metrics, '{}'::jsonb) - CAST(:risk_keys AS text[]),
                raw_data = COALESCE(raw_data, '{}'::jsonb) || CAST(:marker AS jsonb),
                updated_at = NOW()
            WHERE wind_code = :wind_code
        """), {
            "wind_code": wind_code,
            "performance_keys": performance_keys,
            "risk_keys": risk_keys,
            "marker": json.dumps(marker, ensure_ascii=False),
        })


def mark_ranking_sync_unavailable(wind_code: str, reason: str) -> None:
    marker = {
        "ranking_metrics": {
            "status": "nav_unavailable",
            "reason": str(reason),
            "attempted_at": datetime.now(UTC).isoformat(),
        }
    }
    with get_engine().begin() as conn:
        conn.execute(text("""
            UPDATE funds
            SET raw_data = COALESCE(raw_data, '{}'::jsonb) || CAST(:marker AS jsonb),
                updated_at = NOW()
            WHERE wind_code = :wind_code
        """), {
            "wind_code": wind_code,
            "marker": json.dumps(marker, ensure_ascii=False),
        })


def select_target_codes(
    limit: int,
    fund_type: str,
    missing_only: bool,
    min_age_days: int,
    include_exchange_funds: bool,
) -> List[str]:
    where = [
        "raw_data->>'source' = 'tushare'",
        active_fund_sql(),
    ]
    if not include_exchange_funds:
        where.append("wind_code LIKE '%.OF'")
    params: Dict[str, Any] = {"limit": limit}
    if min_age_days > 0:
        where.append("establishment_date <= CURRENT_DATE - (:min_age_days * INTERVAL '1 day')")
        params["min_age_days"] = min_age_days
    if fund_type:
        where.append("type = :fund_type")
        params["fund_type"] = fund_type
    if missing_only:
        where.append("""
            NOT EXISTS (
              SELECT 1 FROM metric_snapshots ms
              WHERE ms.target_type = 'fund'
                AND ms.target_id = funds.wind_code
                AND ms.metric_window = '1y'
                AND ms.metric_name IN ('annualized_return', 'max_drawdown', 'sharpe_ratio')
            )
        """)

    sql = text(f"""
        SELECT wind_code
        FROM funds
        WHERE {" AND ".join(where)}
        ORDER BY
          CASE
            WHEN type IN ('股票型', '混合型', '债券型', '指数型', '货币型') THEN 0
            ELSE 1
          END,
          establishment_date ASC NULLS LAST,
          wind_code ASC
        LIMIT :limit
    """)
    with get_engine().connect() as conn:
        return [row.wind_code for row in conn.execute(sql, params).fetchall()]


def select_research_linked_codes(limit: int, missing_only: bool) -> List[str]:
    """只选择本地调研纪要关联且已完成标准分类的基金。"""
    missing_sql = ""
    if missing_only:
        missing_sql = """
          AND NOT EXISTS (
            SELECT 1 FROM metric_snapshots ms
            WHERE ms.target_type = 'fund'
              AND ms.target_id = linked.wind_code
              AND ms.metric_window = '1y'
              AND ms.metric_name = 'annualized_return'
          )
        """
    sql = text(f"""
        WITH linked AS (
          SELECT DISTINCT proposal->>'value' AS wind_code
          FROM research_reports report
          CROSS JOIN LATERAL jsonb_array_elements(COALESCE(report.review_proposals, '[]')) proposal
          WHERE proposal->>'kind' = 'fund'
            AND proposal->>'extraction_source' = 'tushare.fund_manager'
        )
        SELECT linked.wind_code
        FROM linked
        JOIN fund_share_classes share
          ON share.wind_code = linked.wind_code
         AND share.status = 'active'
        JOIN funds fund ON fund.wind_code = linked.wind_code
        WHERE linked.wind_code LIKE '%.OF'
          AND ({active_fund_sql('fund')})
          {missing_sql}
        ORDER BY linked.wind_code
        LIMIT :limit
    """)
    with get_engine().connect() as conn:
        return [row.wind_code for row in conn.execute(sql, {"limit": limit}).fetchall()]


def manager_tenure_peer_gap_states(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    """汇总经理现任产品中仍缺同任期可比样本的专业同类组。"""
    grouped: Dict[str, Dict[str, Any]] = {}
    items = (snapshot.get("product_tenures") or {}).get("items") or []
    for item in items:
        if not isinstance(item, dict) or not item.get("is_current"):
            continue
        ranking = item.get("peer_ranking") if isinstance(item.get("peer_ranking"), dict) else {}
        if ranking.get("status") != "insufficient_peer_sample":
            continue
        peer_group_id = str(ranking.get("peer_group_id") or "").strip()
        period_start = _date_or_none(ranking.get("period_start"))
        period_end = _date_or_none(ranking.get("period_end"))
        minimum_peer_count = max(2, int(ranking.get("minimum_peer_count") or 5))
        valid_peer_count = max(0, int(ranking.get("valid_peer_count") or 0))
        if not peer_group_id or not period_start or not period_end or valid_peer_count >= minimum_peer_count:
            continue

        state = grouped.setdefault(peer_group_id, {
            "peer_group_id": peer_group_id,
            "peer_group_name": ranking.get("peer_group_name"),
            "period_start": period_start,
            "period_end": period_end,
            "minimum_peer_count": minimum_peer_count,
            "valid_peer_count": valid_peer_count,
            "needed_count": minimum_peer_count - valid_peer_count,
            "target_entity_ids": set(),
            "target_codes": [],
        })
        state["period_start"] = min(state["period_start"], period_start)
        state["period_end"] = max(state["period_end"], period_end)
        state["minimum_peer_count"] = max(state["minimum_peer_count"], minimum_peer_count)
        state["valid_peer_count"] = min(state["valid_peer_count"], valid_peer_count)
        state["needed_count"] = max(state["needed_count"], minimum_peer_count - valid_peer_count)
        entity_id = str(item.get("entity_id") or "").strip()
        if entity_id:
            state["target_entity_ids"].add(entity_id)
        target_code = str(item.get("fund_code") or "").strip().upper()
        if target_code and target_code not in state["target_codes"]:
            state["target_codes"].append(target_code)
    return list(grouped.values())


def _date_or_none(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def _tenure_nav_coverage_is_valid(
    summary: Dict[str, Any],
    period_start: date,
    period_end: date,
) -> bool:
    first_date = _date_or_none(summary.get("first_date"))
    last_date = _date_or_none(summary.get("last_date"))
    observations = int(summary.get("observations") or 0)
    if not first_date or not last_date:
        return False
    requested_days = max(1, (period_end - period_start).days)
    expected_observations = max(2, round(requested_days / 365.25 * 252) + 1)
    return (
        observations >= ManagerTenurePeerRankingService.MIN_OBSERVATIONS
        and (last_date - first_date).days / requested_days
        >= ManagerTenurePeerRankingService.MIN_PERIOD_COVERAGE
        and observations / expected_observations
        >= ManagerTenurePeerRankingService.MIN_OBSERVATION_COVERAGE
    )


def select_tenure_peer_missing_nav_codes(
    peer_group_id: str,
    period_start: date,
    period_end: date,
    target_entity_ids: Iterable[str],
    limit: int,
    include_exchange_funds: bool = False,
) -> List[str]:
    """选择成立时间足够且尚未覆盖完整任期的同类代表份额。"""
    if not peer_group_id or limit <= 0:
        return []
    sql = text(f"""
        WITH representative_shares AS (
          SELECT DISTINCT ON (entity.id)
            entity.id AS entity_id,
            share.wind_code,
            fund.establishment_date,
            fund.total_asset
          FROM peer_group_members membership
          JOIN fund_entities entity ON entity.id = membership.entity_id
          JOIN fund_share_classes share
            ON share.entity_id = entity.id
           AND share.status = 'active'
          JOIN funds fund ON fund.wind_code = share.wind_code
          WHERE membership.peer_group_id = :peer_group_id
            AND membership.role <> 'excluded'
            AND entity.lifecycle_stage = 'active'
            AND ({active_fund_sql('fund')})
            AND (:include_exchange_funds OR share.wind_code LIKE '%.OF')
            AND fund.establishment_date <= :period_start
            AND NOT (entity.id = ANY(:target_entity_ids))
            AND COALESCE(fund.raw_data->'ranking_metrics'->>'status', '') NOT IN (
              'nav_unavailable', 'invalid_nav'
            )
          ORDER BY
            entity.id,
            share.is_primary DESC,
            fund.total_asset DESC NULLS LAST,
            share.wind_code
        )
        SELECT
          representative.entity_id,
          representative.wind_code,
          representative.total_asset,
          MIN(nav.trade_date) AS first_date,
          MAX(nav.trade_date) AS last_date,
          COUNT(nav.id)::int AS observations
        FROM representative_shares representative
        LEFT JOIN fund_nav nav
          ON nav.wind_code = representative.wind_code
         AND nav.trade_date BETWEEN :period_start AND :period_end
         AND COALESCE(nav.accum_nav, nav.unit_nav, nav.nav) > 0
        GROUP BY representative.entity_id, representative.wind_code, representative.total_asset
        ORDER BY representative.total_asset DESC NULLS LAST, representative.wind_code
    """)
    excluded = [str(item) for item in target_entity_ids if str(item or "").strip()]
    with get_engine().connect() as conn:
        rows = [dict(row._mapping) for row in conn.execute(sql, {
            "peer_group_id": peer_group_id,
            "period_start": period_start,
            "period_end": period_end,
            "target_entity_ids": excluded or ["__none__"],
            "include_exchange_funds": bool(include_exchange_funds),
        }).fetchall()]
    return [
        str(row["wind_code"])
        for row in rows
        if row.get("wind_code") and not _tenure_nav_coverage_is_valid(row, period_start, period_end)
    ][:limit]


def select_manager_tenure_peer_coverage(
    manager_id: str,
    limit: int,
    include_exchange_funds: bool = False,
    as_of_date: Optional[date] = None,
) -> Dict[str, Any]:
    """为指定经理生成现任产品同类任期样本补数计划。"""
    snapshot = FundManagerResearchService().build(manager_id)
    states = manager_tenure_peer_gap_states(snapshot)
    candidate_states: List[Dict[str, Any]] = []
    for state in states:
        candidates = select_tenure_peer_missing_nav_codes(
            peer_group_id=state["peer_group_id"],
            period_start=state["period_start"],
            period_end=state["period_end"],
            target_entity_ids=state["target_entity_ids"],
            limit=state["needed_count"],
            include_exchange_funds=include_exchange_funds,
        )
        candidate_states.append({**state, "candidates": candidates, "selected_count": 0})

    codes = round_robin_peer_candidates(candidate_states, limit)
    earliest_start = min((state["period_start"] for state in states), default=None)
    effective_as_of = as_of_date or date.today()
    required_days = max(30, (effective_as_of - earliest_start).days + 7) if earliest_start else 30
    for state in candidate_states:
        log(
            f"[manager-peer-coverage] {state.get('peer_group_name') or state['peer_group_id']}："
            f"有效样本 {state['valid_peer_count']} / {state['minimum_peer_count']}，"
            f"目标产品 {','.join(state['target_codes'])}，本次待补 {state['selected_count']}"
        )
    return {
        "manager_id": manager_id,
        "codes": codes,
        "required_days": required_days,
        "groups": candidate_states,
    }


def manager_evaluation_gap_codes(
    snapshot: Dict[str, Any],
    limit: int,
    as_of_date: Optional[date] = None,
) -> List[str]:
    """选择已成立满一年、尚无完整分类内评价的现任产品。"""
    effective_as_of = as_of_date or date.today()
    selected: List[str] = []
    for fund in snapshot.get("current_funds") or []:
        if not isinstance(fund, dict):
            continue
        missing_items = {
            str(item or "").strip()
            for item in (fund.get("evaluation_missing_data") or [])
            if str(item or "").strip()
        }
        score_missing = number_or_none(fund.get("professional_score")) is None
        tenure_missing = "metric_window:manager_tenure" in missing_items
        if not score_missing and not tenure_missing:
            continue
        code = str(fund.get("wind_code") or "").strip().upper()
        if not code:
            continue
        established = _date_or_none(fund.get("establishment_date"))
        if established and (effective_as_of - established).days < 365:
            continue
        selected.append(code)
        if len(selected) >= max(1, limit):
            break
    return selected


def manager_evaluation_required_days(
    snapshot: Dict[str, Any],
    codes: Iterable[str],
    as_of_date: Optional[date] = None,
) -> int:
    """按待补产品最早现任起点确定净值回溯长度。"""
    selected_codes = {
        str(code or "").strip().upper()
        for code in codes
        if str(code or "").strip()
    }
    starts = [
        parsed
        for item in ((snapshot.get("product_tenures") or {}).get("items") or [])
        if item.get("is_current")
        and str(item.get("fund_code") or "").strip().upper() in selected_codes
        if (parsed := _date_or_none(item.get("start_date") or item.get("requested_start_date")))
    ]
    if not starts:
        return 0
    effective_as_of = as_of_date or date.today()
    return max(30, (effective_as_of - min(starts)).days + 7)


def select_manager_evaluation_coverage(manager_id: str, limit: int) -> Dict[str, Any]:
    snapshot = FundManagerResearchService().build(manager_id)
    codes = manager_evaluation_gap_codes(snapshot, limit)
    required_days = manager_evaluation_required_days(snapshot, codes)
    coverage = snapshot.get("coverage") or {}
    log(
        f"[manager-evaluation] 当前产品 {coverage.get('current_fund_count', 0)}，"
        f"已有评价 {coverage.get('evaluated_fund_count', 0)}，本次待补 {len(codes)}"
    )
    return {"manager_id": manager_id, "codes": codes, "required_days": required_days}


def select_peer_evaluation_coverage_codes(
    limit: int,
    peer_group_keys: List[str],
    target_per_group: int = 0,
    min_age_days: int = 430,
    include_exchange_funds: bool = False,
) -> List[str]:
    """按同类组轮询选择缺指标基金，0 表示在总 limit 内持续扩大覆盖。"""
    normalized_keys = list(dict.fromkeys(
        str(key).strip() for key in peer_group_keys if str(key or "").strip()
    ))
    if not normalized_keys:
        return []

    sql = text(f"""
        SELECT
          pg.key AS peer_group_key,
          candidate.wind_code AS target_wind_code
        FROM peer_groups pg
        LEFT JOIN LATERAL (
          SELECT fsc.wind_code
          FROM peer_group_members pgm
          JOIN fund_entities fe ON fe.id = pgm.entity_id
          JOIN fund_share_classes fsc
            ON fsc.entity_id = fe.id
           AND fsc.status = 'active'
          LEFT JOIN funds f ON f.wind_code = fsc.wind_code
          WHERE pgm.peer_group_id = pg.id
            AND pgm.role <> 'excluded'
            AND fe.lifecycle_stage = 'active'
            AND f.wind_code IS NOT NULL
            AND ({active_fund_sql('f')})
            AND (:include_exchange_funds OR fsc.wind_code LIKE '%.OF')
            AND (
              :min_age_days <= 0
              OR f.establishment_date <= CURRENT_DATE - (:min_age_days * INTERVAL '1 day')
            )
          ORDER BY
            fsc.is_primary DESC,
            CASE WHEN EXISTS (
              SELECT 1
              FROM metric_snapshots ms
              WHERE ms.target_type = 'fund'
                AND ms.target_id = fsc.wind_code
                AND ms.metric_window = '1y'
                AND ms.metric_name = 'annualized_return'
            ) THEN 0 ELSE 1 END,
            f.total_asset DESC NULLS LAST,
            fsc.wind_code ASC
          LIMIT 1
        ) candidate ON TRUE
        WHERE pg.key = ANY(:peer_group_keys)
        ORDER BY pg.key
    """)
    with get_engine().connect() as conn:
        groups = [dict(row._mapping) for row in conn.execute(
            sql,
            {
                "peer_group_keys": normalized_keys,
                "min_age_days": max(0, int(min_age_days)),
                "include_exchange_funds": bool(include_exchange_funds),
            },
        ).fetchall()]

    service = PeerComparisonService()
    selected: List[str] = []
    group_states: List[Dict[str, Any]] = []
    for group in groups:
        target_code = group.get("target_wind_code")
        if not target_code:
            log(f"[peer-coverage] {group.get('peer_group_key')} 无可用代表份额")
            continue
        result = service.build_peer_percentiles(str(target_code), window="1y")
        valid_count = int(result.get("valid_metric_peer_count") or 0)
        classified_count = int(result.get("classified_peer_count") or 0)
        configured_target = int(target_per_group or 0)
        desired_count = max(
            int(result.get("minimum_valid_peer_count") or 0),
            min(configured_target, classified_count) if configured_target > 0 else classified_count,
        )
        if valid_count >= desired_count:
            log(
                f"[peer-coverage] {group.get('peer_group_key')} 已满足："
                f"有效样本 {valid_count} / 目标 {desired_count}"
            )
            continue

        needed_count = max(0, desired_count - valid_count)
        candidates = select_peer_group_missing_metric_codes(
            str(group.get("peer_group_key") or ""),
            limit=min(max(needed_count, 1), max(1, limit)),
            min_age_days=min_age_days,
            include_exchange_funds=include_exchange_funds,
        )
        normalized_candidates: List[str] = []
        for code in candidates:
            normalized_code = str(code).strip().upper()
            if normalized_code and normalized_code not in normalized_candidates:
                normalized_candidates.append(normalized_code)
        group_states.append({
            "peer_group_key": group.get("peer_group_key"),
            "valid_count": valid_count,
            "desired_count": desired_count,
            "classified_count": classified_count,
            "candidates": normalized_candidates[:needed_count],
            "selected_count": 0,
        })

    selected = round_robin_peer_candidates(group_states, limit)

    for state in group_states:
        log(
            f"[peer-coverage] {state.get('peer_group_key')}："
            f"已分类 {state.get('classified_count')}，"
            f"有效样本 {state.get('valid_count')} / 目标 {state.get('desired_count')}，"
            f"本次待补 {state.get('selected_count')}"
        )
    return selected


def round_robin_peer_candidates(group_states: List[Dict[str, Any]], limit: int) -> List[str]:
    """每轮每类取一只，避免大类别吃光本次总额度。"""
    selected: List[str] = []
    selected_set = set()
    while len(selected) < max(1, limit):
        added_this_round = 0
        for state in group_states:
            candidates = state.get("candidates") or []
            while candidates and candidates[0] in selected_set:
                candidates.pop(0)
            if not candidates:
                continue
            code = str(candidates.pop(0)).strip().upper()
            if not code or code in selected_set:
                continue
            selected.append(code)
            selected_set.add(code)
            state["selected_count"] = int(state.get("selected_count") or 0) + 1
            added_this_round += 1
            if len(selected) >= max(1, limit):
                break
        if added_this_round == 0:
            break
    return selected


def build_fof_lookthrough_coverage_states(
    rows: List[Dict[str, Any]],
    panels: Dict[str, List[Dict[str, Any]]],
    lookthrough_ready: Dict[str, bool],
    target_per_group: int,
) -> List[Dict[str, Any]]:
    """只把“类别指标齐全 + FOF 穿透门槛通过”计为可评价。"""
    methodology = ProfessionalScoringService().methodology
    grouped: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        peer_group_key = str(row.get("peer_group_key") or "").strip()
        wind_code = str(row.get("wind_code") or "").strip().upper()
        family_key = str(row.get("strategy_family_key") or "").strip()
        profile_key = str(
            (FundClassificationService.FAMILY_META.get(family_key) or {}).get("evaluation_profile_key")
            or ""
        )
        metric_configs = methodology.peer_metric_configs(profile_key)
        if not peer_group_key or not wind_code or profile_key not in FOF_EVALUATION_PROFILES:
            continue
        if not metric_configs or not _panel_has_required_category_metrics(
            panels.get(wind_code) or [],
            metric_configs,
        ):
            continue
        state = grouped.setdefault(peer_group_key, {
            "peer_group_key": peer_group_key,
            "peer_group_name": row.get("peer_group_name") or peer_group_key,
            "eligible_count": 0,
            "valid_count": 0,
            "candidates": [],
            "selected_count": 0,
        })
        state["eligible_count"] += 1
        if lookthrough_ready.get(wind_code):
            state["valid_count"] += 1
        else:
            state["candidates"].append(wind_code)

    states = []
    for state in grouped.values():
        eligible_count = int(state.get("eligible_count") or 0)
        configured_target = max(0, int(target_per_group or 0))
        desired_count = min(configured_target, eligible_count) if configured_target else eligible_count
        state["desired_count"] = desired_count
        needed_count = max(0, desired_count - int(state.get("valid_count") or 0))
        state["candidates"] = (state.get("candidates") or [])[:needed_count]
        states.append(state)
    return states


def select_fof_lookthrough_coverage_codes(
    limit: int,
    target_per_group: int = 5,
    min_age_days: int = 430,
) -> List[str]:
    """从已有类别指标的 FOF 中，轮询选择缺少底层基金穿透的代表份额。"""
    sql = text(f"""
        WITH representative_shares AS (
          SELECT DISTINCT ON (pg.id, entity.id)
            pg.key AS peer_group_key,
            pg.name AS peer_group_name,
            family.key AS strategy_family_key,
            share.wind_code,
            fund.total_asset
          FROM peer_groups pg
          JOIN peer_group_members membership
            ON membership.peer_group_id = pg.id
           AND membership.role <> 'excluded'
          JOIN fund_entities entity ON entity.id = membership.entity_id
          JOIN strategy_families family ON family.id = entity.strategy_family_id
          JOIN fund_share_classes share
            ON share.entity_id = entity.id
           AND share.status = 'active'
          JOIN funds fund ON fund.wind_code = share.wind_code
          WHERE pg.key = ANY(:peer_group_keys)
            AND entity.lifecycle_stage = 'active'
            AND ({active_fund_sql('fund')})
            AND (
              :min_age_days <= 0
              OR fund.establishment_date <= CURRENT_DATE - (:min_age_days * INTERVAL '1 day')
            )
          ORDER BY
            pg.id,
            entity.id,
            share.is_primary DESC,
            fund.total_asset DESC NULLS LAST,
            share.wind_code
        )
        SELECT *
        FROM representative_shares
        ORDER BY peer_group_key, total_asset DESC NULLS LAST, wind_code
    """)
    with get_engine().connect() as conn:
        rows = [dict(row._mapping) for row in conn.execute(sql, {
            "peer_group_keys": list(FOF_PEER_GROUP_KEYS),
            "min_age_days": max(0, int(min_age_days)),
        }).fetchall()]
    codes = [str(row.get("wind_code") or "") for row in rows if row.get("wind_code")]
    panels = get_metric_snapshot_repo().get_latest_panels("fund", codes)
    lookthrough_ready = fof_lookthrough_ready_map(codes)
    states = build_fof_lookthrough_coverage_states(
        rows,
        panels,
        lookthrough_ready,
        target_per_group,
    )
    selected = round_robin_peer_candidates(states, limit)
    for state in states:
        log(
            f"[fof-lookthrough] {state['peer_group_name']}："
            f"已有类别指标 {state['eligible_count']}，"
            f"穿透可评价 {state['valid_count']} / 目标 {state['desired_count']}，"
            f"本次待补 {state['selected_count']}"
        )
    return selected


def fof_lookthrough_ready_map(codes: List[str]) -> Dict[str, bool]:
    normalized_codes = list(dict.fromkeys(
        str(code or "").strip().upper() for code in codes if str(code or "").strip()
    ))
    if not normalized_codes:
        return {}
    sql = text("""
        WITH latest_periods AS (
          SELECT wind_code, MAX(report_date) AS report_date
          FROM fund_underlying_holdings
          WHERE wind_code = ANY(:codes)
          GROUP BY wind_code
        )
        SELECT holding.wind_code,
               COUNT(*) AS disclosed_fund_count,
               COALESCE(SUM(holding.nav_ratio), 0) AS disclosed_nav_ratio
        FROM fund_underlying_holdings holding
        JOIN latest_periods latest
          ON latest.wind_code = holding.wind_code
         AND latest.report_date = holding.report_date
        GROUP BY holding.wind_code
    """)
    with get_engine().connect() as conn:
        rows = conn.execute(sql, {"codes": normalized_codes}).fetchall()
    return {
        str(row.wind_code): (
            int(row.disclosed_fund_count or 0) >= 5
            and float(row.disclosed_nav_ratio or 0) >= 20.0
        )
        for row in rows
    }


def build_company_evaluation_group_states(
    rows: List[Dict[str, Any]],
    panels: Dict[str, List[Dict[str, Any]]],
    target_per_group: int,
) -> List[Dict[str, Any]]:
    """按公司内标准同类组组装待补评价样本。"""
    methodology = ProfessionalScoringService().methodology
    grouped: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        peer_group_key = str(row.get("peer_group_key") or "").strip()
        family_key = str(row.get("strategy_family_key") or "").strip()
        code = str(row.get("wind_code") or "").strip().upper()
        profile_key = str(
            (FundClassificationService.FAMILY_META.get(family_key) or {}).get("evaluation_profile_key") or ""
        )
        metric_configs = methodology.peer_metric_configs(profile_key)
        if not peer_group_key or not code or not metric_configs:
            continue

        state = grouped.setdefault(peer_group_key, {
            "peer_group_key": peer_group_key,
            "peer_group_name": row.get("peer_group_name") or peer_group_key,
            "classified_count": 0,
            "valid_count": 0,
            "desired_count": 0,
            "candidates": [],
            "selected_count": 0,
        })
        state["classified_count"] += 1
        if _panel_has_required_category_metrics(panels.get(code) or [], metric_configs):
            state["valid_count"] += 1
        else:
            state["candidates"].append(code)

    states: List[Dict[str, Any]] = []
    configured_target = max(0, int(target_per_group))
    for state in grouped.values():
        desired_count = (
            state["classified_count"]
            if configured_target == 0
            else min(configured_target, state["classified_count"])
        )
        state["desired_count"] = desired_count
        needed_count = max(0, desired_count - state["valid_count"])
        if needed_count <= 0:
            continue
        state["candidates"] = state["candidates"][:needed_count]
        if state["candidates"]:
            states.append(state)

    states.sort(key=lambda state: (
        state["valid_count"] > 0,
        -int(state["classified_count"]),
        str(state["peer_group_name"]),
    ))
    return states


def resolve_fund_company_name(keyword: str) -> str:
    normalized = str(keyword or "").strip()
    if not normalized:
        raise ValueError("基金公司名称不能为空")
    company_expr = fund_company_sql("fund")
    sql = text(f"""
        WITH companies AS (
          SELECT DISTINCT {company_expr} AS company
          FROM funds fund
          WHERE {company_expr} IS NOT NULL
        )
        SELECT company
        FROM companies
        WHERE company = :keyword OR company ILIKE :pattern
        ORDER BY (company = :keyword) DESC, LENGTH(company), company
        LIMIT 10
    """)
    with get_engine().connect() as conn:
        matches = [str(row.company) for row in conn.execute(sql, {
            "keyword": normalized,
            "pattern": f"%{normalized}%",
        }).fetchall()]
    if not matches:
        raise ValueError(f"未找到基金公司：{normalized}")
    exact = next((company for company in matches if company == normalized), None)
    if exact:
        return exact
    if len(matches) > 1:
        raise ValueError(f"基金公司名称不唯一：{', '.join(matches[:5])}")
    return matches[0]


def select_company_evaluation_coverage(
    company: str,
    limit: int,
    target_per_group: int = COMPANY_EVALUATION_TARGET_PER_GROUP,
    min_age_days: int = 430,
    include_exchange_funds: bool = True,
) -> Dict[str, Any]:
    """在指定基金公司内按同类组轮询补齐类别专属评价样本。"""
    resolved_company = resolve_fund_company_name(company)
    company_expr = fund_company_sql("fund")
    sql = text(f"""
        WITH representative_shares AS (
          SELECT DISTINCT ON (entity.id)
            entity.id AS entity_id,
            peer.key AS peer_group_key,
            peer.name AS peer_group_name,
            family.key AS strategy_family_key,
            share.wind_code,
            fund.total_asset,
            CARDINALITY(COALESCE(fund.manager_ids, ARRAY[]::TEXT[])) AS manager_count
          FROM funds fund
          JOIN fund_share_classes share
            ON share.wind_code = fund.wind_code
           AND share.status = 'active'
          JOIN fund_entities entity ON entity.id = share.entity_id
          JOIN peer_group_members membership
            ON membership.entity_id = entity.id
           AND membership.role <> 'excluded'
          JOIN peer_groups peer ON peer.id = membership.peer_group_id
          LEFT JOIN strategy_families family ON family.id = entity.strategy_family_id
          WHERE {company_expr} = :company
            AND entity.lifecycle_stage = 'active'
            AND ({active_fund_sql('fund')})
            AND (:include_exchange_funds OR share.wind_code LIKE '%.OF')
            AND (
              :min_age_days <= 0
              OR fund.establishment_date <= CURRENT_DATE - (:min_age_days * INTERVAL '1 day')
            )
            AND COALESCE(fund.raw_data->'ranking_metrics'->>'status', '') NOT IN (
              'nav_unavailable', 'invalid_nav'
            )
          ORDER BY
            entity.id,
            share.is_primary DESC,
            fund.total_asset DESC NULLS LAST,
            manager_count DESC,
            share.wind_code
        )
        SELECT *
        FROM representative_shares
        ORDER BY peer_group_name, total_asset DESC NULLS LAST, manager_count DESC, wind_code
    """)
    with get_engine().connect() as conn:
        rows = [dict(row._mapping) for row in conn.execute(sql, {
            "company": resolved_company,
            "min_age_days": max(0, int(min_age_days)),
            "include_exchange_funds": bool(include_exchange_funds),
        }).fetchall()]

    codes = [str(row.get("wind_code") or "") for row in rows if row.get("wind_code")]
    panels = get_metric_snapshot_repo().get_latest_panels("fund", codes)
    states = build_company_evaluation_group_states(rows, panels, target_per_group)
    selected = round_robin_peer_candidates(states, limit)
    for state in states:
        log(
            f"[company-coverage] {state['peer_group_name']}："
            f"可用样本 {state['valid_count']} / 目标 {state['desired_count']}，"
            f"本次待补 {state['selected_count']}"
        )
    return {
        "company": resolved_company,
        "codes": selected,
        "groups": states,
    }


def _panel_has_required_category_metrics(
    panel: List[Dict[str, Any]],
    metric_configs: List[Dict[str, Any]],
) -> bool:
    metrics: Dict[str, Dict[str, float]] = {}
    for row in panel:
        metric_name = str(row.get("metric_name") or "")
        metric_value = number_or_none(row.get("metric_value"))
        if metric_name and metric_value is not None:
            metrics.setdefault(str(row.get("metric_window") or "latest"), {})[metric_name] = metric_value

    for config in metric_configs:
        if not config.get("required_for_sample", True):
            continue
        value = None
        for window, metric_name in config.get("paths") or []:
            effective_window = "1y" if window == "selected" else str(window)
            value = metrics.get(effective_window, {}).get(str(metric_name))
            if value is not None:
                break
        if value is not None and config.get("transform") == "absolute":
            value = abs(value)
        valid_range = config.get("valid_range")
        if value is None or (valid_range and not (valid_range[0] <= value <= valid_range[1])):
            return False
    return True


def select_peer_group_missing_metric_codes(
    peer_group_key: str,
    limit: int,
    min_age_days: int = 430,
    include_exchange_funds: bool = False,
) -> List[str]:
    """按该类别专属评价方法选择仍缺核心指标的主要份额。"""
    if not peer_group_key or limit <= 0:
        return []
    sql = text(f"""
        WITH representative_shares AS (
          SELECT DISTINCT ON (fe.id)
            fsc.wind_code,
            sf.key AS strategy_family_key,
            fund.total_asset
          FROM peer_groups pg
          JOIN peer_group_members pgm
            ON pgm.peer_group_id = pg.id
           AND pgm.role <> 'excluded'
          JOIN fund_entities fe ON fe.id = pgm.entity_id
          LEFT JOIN strategy_families sf ON sf.id = fe.strategy_family_id
          JOIN fund_share_classes fsc
            ON fsc.entity_id = fe.id
           AND fsc.status = 'active'
          JOIN funds fund ON fund.wind_code = fsc.wind_code
          WHERE pg.key = :peer_group_key
            AND (:include_exchange_funds OR fsc.wind_code LIKE '%.OF')
            AND fe.lifecycle_stage = 'active'
            AND ({active_fund_sql('fund')})
            AND (
              :min_age_days <= 0
              OR fund.establishment_date <= CURRENT_DATE - (:min_age_days * INTERVAL '1 day')
            )
            AND COALESCE(fund.raw_data->'ranking_metrics'->>'status', '') NOT IN (
              'nav_unavailable', 'invalid_nav'
            )
          ORDER BY
            fe.id,
            fsc.is_primary DESC,
            fund.total_asset DESC NULLS LAST,
            fsc.wind_code
        )
        SELECT wind_code, strategy_family_key
        FROM representative_shares
        ORDER BY total_asset DESC NULLS LAST, wind_code
    """)
    with get_engine().connect() as conn:
        rows = [dict(row._mapping) for row in conn.execute(
            sql,
            {
                "peer_group_key": peer_group_key,
                "min_age_days": max(0, int(min_age_days)),
                "include_exchange_funds": bool(include_exchange_funds),
            },
        ).fetchall()]

    codes = [str(row.get("wind_code") or "") for row in rows if row.get("wind_code")]
    panels = get_metric_snapshot_repo().get_latest_panels("fund", codes)
    methodology = ProfessionalScoringService().methodology
    selected: List[str] = []
    for row in rows:
        family_key = str(row.get("strategy_family_key") or "")
        profile_key = str(
            (FundClassificationService.FAMILY_META.get(family_key) or {}).get("evaluation_profile_key") or ""
        )
        metric_configs = methodology.peer_metric_configs(profile_key)
        code = str(row.get("wind_code") or "")
        if metric_configs and not _panel_has_required_category_metrics(panels.get(code) or [], metric_configs):
            selected.append(code)
            if len(selected) >= limit:
                break
    return selected


def sync_one_fund(
    data_service: TushareDataService,
    rolling_service: RollingMetricService,
    wind_code: str,
    start_date: date,
    end_date: date,
) -> Dict[str, Any]:
    fund_repo = get_fund_repo()
    nav_repo = get_nav_repo()
    metric_repo = get_metric_snapshot_repo()
    existing = fund_repo.get_fund(wind_code) or {}
    classification_context = get_fund_classification_repo().get_classification_context(wind_code) or {}
    if classification_context.get("status") != "resolved":
        ingestion_service = FundClassificationIngestionService()
        ingestion_plan = ingestion_service.build_plan([existing])
        if ingestion_plan.get("groups"):
            ingestion_service.apply_plan(ingestion_plan)
            classification_context = get_fund_classification_repo().get_classification_context(wind_code) or {}

    try:
        nav_series = data_service.get_fund_nav(
            wind_code,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
        )
    except Exception as error:
        reason = f"净值不可用：{error}"
        mark_ranking_sync_unavailable(wind_code, reason)
        return {"wind_code": wind_code, "status": "skipped", "reason": reason}
    if len(nav_series) < 20:
        reason = f"净值点不足 {len(nav_series)}"
        mark_ranking_sync_unavailable(wind_code, reason)
        return {"wind_code": wind_code, "status": "skipped", "reason": reason}

    enrichment = FundNavDataEnrichmentService(data_service).enrich(
        wind_code=wind_code,
        fund_type=existing.get("type"),
        nav_series=nav_series,
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
    )
    nav_series = enrichment["nav_series"]
    if enrichment.get("nav_data_status") != "valid":
        nav_repo.upsert_nav_series(wind_code, nav_series, replace_range=True)
        invalidate_nav_derived_evaluation_facts(
            wind_code,
            enrichment.get("nav_validation") or {"status": "invalid"},
        )
        return {
            "wind_code": wind_code,
            "status": "skipped",
            "reason": f"净值质量门禁：{enrichment.get('nav_validation')}",
        }
    nav_repo.upsert_nav_series(wind_code, nav_series, replace_range=True)
    rolling_result = rolling_service.calculate_and_save_for_fund(
        wind_code,
        benchmark_code=enrichment.get("benchmark_code"),
    )
    latest_payload = latest_nav_payload(nav_series)
    static_metric_count = save_latest_fund_facts(
        metric_repo=metric_repo,
        wind_code=wind_code,
        fund={
            **existing,
            "total_asset": latest_payload.get("total_asset") or existing.get("total_asset"),
        },
        as_of_date=date.fromisoformat(str(latest_payload.get("nav_date") or end_date.isoformat())[:10]),
    )
    enrichment_metric_count = save_enrichment_metric_facts(
        metric_repo=metric_repo,
        wind_code=wind_code,
        enrichment=enrichment,
        as_of_date=date.fromisoformat(str(latest_payload.get("nav_date") or end_date.isoformat())[:10]),
    )
    panel = metric_repo.get_latest_panel("fund", wind_code)
    metric_payload = build_fund_metric_payload(panel)
    metric_payload["performance_data"].update(enrichment.get("performance_facts") or {})
    fof_lookthrough = sync_fof_lookthrough(wind_code, classification_context)
    saved_metric_count = rolling_result.get("saved", 0) + static_metric_count + enrichment_metric_count
    one_year_ready = all(
        metric_payload[section].get(metric_name) is not None
        for section, metric_name in (
            ("performance_data", "annualized_return_1y"),
            ("risk_metrics", "max_drawdown_1y"),
            ("performance_data", "sharpe_ratio"),
        )
    )
    ranking_status = "synced" if one_year_ready else "insufficient_metric_history"

    ok = fund_repo.upsert_fund(
        wind_code,
        {
            "name": existing.get("name") or wind_code,
            "type": existing.get("type") or "",
            "manager_ids": existing.get("manager_ids") or [],
            "nav": latest_payload.get("nav"),
            "nav_date": latest_payload.get("nav_date"),
            "total_asset": latest_payload.get("total_asset"),
            "establishment_date": existing.get("establishment_date"),
            "performance_data": metric_payload["performance_data"],
            "risk_metrics": metric_payload["risk_metrics"],
            "raw_data": {
                "source": "tushare",
                "ranking_metrics": {
                    "status": ranking_status,
                    "source": "tushare.fund_nav",
                    "synced_at": datetime.now(UTC).isoformat(),
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "nav_points": len(nav_series),
                    "total_asset_as_of": latest_payload.get("total_asset_as_of"),
                    "total_asset_source": latest_payload.get("total_asset_source"),
                    "saved_metric_snapshots": saved_metric_count,
                    "saved_static_metric_snapshots": static_metric_count,
                    "saved_enrichment_metric_snapshots": enrichment_metric_count,
                    "benchmark_code": enrichment.get("benchmark_code"),
                    "benchmark_source": enrichment.get("benchmark_source"),
                    "benchmark_data_status": enrichment.get("benchmark_data_status"),
                    "benchmark_data_kind": enrichment.get("benchmark_data_kind"),
                    "benchmark_observations": enrichment.get("benchmark_observations", 0),
                    "benchmark_nav_observations": enrichment.get("benchmark_nav_observations", 0),
                    "benchmark_rate_observations": enrichment.get("benchmark_rate_observations", 0),
                    "money_market_metric_status": enrichment.get("money_market_metric_status"),
                    "nav_data_status": enrichment.get("nav_data_status"),
                    "nav_validation": enrichment.get("nav_validation"),
                },
            },
        },
    )

    result = {
        "wind_code": wind_code,
        "status": "synced" if ok and one_year_ready else "skipped" if ok else "failed",
        "nav_points": len(nav_series),
        "saved_metric_snapshots": saved_metric_count,
        "saved_static_metric_snapshots": static_metric_count,
        "latest_nav_date": latest_payload.get("nav_date"),
        "return_1y": metric_payload["performance_data"].get("return_1y"),
        "max_drawdown_1y": metric_payload["risk_metrics"].get("max_drawdown_1y"),
        "sharpe_1y": metric_payload["performance_data"].get("sharpe_ratio"),
        "manager_tenure_required": manager_tenure_required(classification_context),
        "fof_lookthrough": fof_lookthrough,
    }
    if ok and not one_year_ready:
        result["reason"] = f"1Y 滚动指标观察不足，当前净值点 {len(nav_series)}"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="同步基金排行所需净值和滚动指标")
    parser.add_argument("--codes", default="", help="逗号分隔基金代码；为空则从本地库选择缺指标基金")
    parser.add_argument("--limit", type=int, default=100, help="本次最多同步数量")
    parser.add_argument("--fund-type", default="", help="可选：股票型/混合型/债券型/指数型/货币型/QDII")
    parser.add_argument("--days", type=int, default=365 * 3 + 20, help="净值回看天数")
    parser.add_argument("--min-age-days", type=int, default=430, help="自动选样时要求基金至少成立天数")
    parser.add_argument("--throttle", type=float, default=0.2, help="每只基金之间的等待秒数")
    parser.add_argument("--include-existing", action="store_true", help="不跳过已有 1Y 指标基金")
    parser.add_argument("--research-linked", action="store_true", help="只同步调研纪要关联且已分类的基金")
    parser.add_argument("--include-exchange-funds", action="store_true", help="自动选样时包含 .SH/.SZ 交易所代码")
    parser.add_argument("--company", default="", help="指定基金公司全称或唯一关键词")
    parser.add_argument(
        "--company-evaluation-coverage",
        action="store_true",
        help="按指定基金公司的标准同类组轮询补齐评价样本",
    )
    parser.add_argument(
        "--company-target-per-group",
        type=int,
        default=COMPANY_EVALUATION_TARGET_PER_GROUP,
        help="公司内每个同类组期望可评价样本数；0 表示补齐全部代表份额",
    )
    parser.add_argument("--manager-id", default="", help="规范基金经理 ID")
    parser.add_argument(
        "--manager-evaluation-coverage",
        action="store_true",
        help="补齐指定经理现任产品的基金级分类内评价数据",
    )
    parser.add_argument(
        "--manager-tenure-peer-coverage",
        action="store_true",
        help="补齐指定经理现任产品的同类同任期净值样本",
    )
    parser.add_argument(
        "--peer-evaluation-coverage",
        action="store_true",
        help="按标准化同类组和类别专属指标缺口补足评价样本（默认包含交易所 ETF）",
    )
    parser.add_argument(
        "--browser-core-coverage",
        action="store_true",
        help="把基金浏览器 7 个推荐类别补至每类至少 10 只真实可评价基金",
    )
    parser.add_argument(
        "--fof-lookthrough-coverage",
        action="store_true",
        help="按偏股、平衡、偏债 FOF 轮询补齐底层基金穿透证据",
    )
    parser.add_argument(
        "--peer-group-keys",
        default=",".join(DEFAULT_PEER_COVERAGE_GROUPS),
        help="同类组补证范围，逗号分隔 peer_group key",
    )
    parser.add_argument(
        "--peer-target-per-group",
        type=int,
        default=0,
        help="每个同类组期望覆盖数；0 表示在本次总 limit 内按类别轮询持续补齐",
    )
    parser.add_argument("--max-errors", type=int, default=10, help="连续或累计错误上限")
    args = parser.parse_args()

    init_database()
    data_service = TushareDataService(strict_no_mock=True)
    if data_service.mock_mode:
        raise RuntimeError("Tushare 未连接真实 API。请配置 TUSHARE_TOKEN 后重试。")

    codes = [code.strip().upper() for code in args.codes.split(",") if code.strip()]
    sync_days = max(30, args.days)
    manager_evaluation_mode = bool(args.manager_evaluation_coverage)
    company_evaluation_mode = bool(args.company_evaluation_coverage)
    fof_lookthrough_mode = bool(args.fof_lookthrough_coverage)
    if fof_lookthrough_mode:
        if codes:
            parser.error("--fof-lookthrough-coverage 不能与 --codes 同时使用")
        codes = select_fof_lookthrough_coverage_codes(
            limit=max(1, args.limit),
            target_per_group=max(0, args.peer_target_per_group) or 5,
            min_age_days=max(0, args.min_age_days),
        )
    elif company_evaluation_mode:
        if codes:
            parser.error("--company-evaluation-coverage 不能与 --codes 同时使用")
        if not args.company.strip():
            parser.error("--company-evaluation-coverage 必须提供 --company")
        company_plan = select_company_evaluation_coverage(
            company=args.company.strip(),
            limit=max(1, args.limit),
            target_per_group=max(0, args.company_target_per_group),
            min_age_days=max(0, args.min_age_days),
            include_exchange_funds=True,
        )
        codes = company_plan["codes"]
    elif manager_evaluation_mode:
        if codes:
            parser.error("--manager-evaluation-coverage 不能与 --codes 同时使用")
        if not args.manager_id.strip():
            parser.error("--manager-evaluation-coverage 必须提供 --manager-id")
        evaluation_plan = select_manager_evaluation_coverage(
            manager_id=args.manager_id.strip(),
            limit=max(1, args.limit),
        )
        codes = evaluation_plan["codes"]
        sync_days = max(sync_days, int(evaluation_plan.get("required_days") or 0))
    elif args.manager_tenure_peer_coverage:
        if codes:
            parser.error("--manager-tenure-peer-coverage 不能与 --codes 同时使用")
        if not args.manager_id.strip():
            parser.error("--manager-tenure-peer-coverage 必须提供 --manager-id")
        coverage_plan = select_manager_tenure_peer_coverage(
            manager_id=args.manager_id.strip(),
            limit=max(1, args.limit),
            include_exchange_funds=args.include_exchange_funds,
        )
        codes = coverage_plan["codes"]
        sync_days = max(sync_days, int(coverage_plan["required_days"]))
    elif not codes and args.research_linked:
        codes = select_research_linked_codes(
            limit=max(1, args.limit),
            missing_only=not args.include_existing,
        )
    elif not codes and (args.peer_evaluation_coverage or args.browser_core_coverage):
        peer_group_keys = (
            list(BROWSER_CORE_PEER_GROUPS)
            if args.browser_core_coverage
            else [key for key in args.peer_group_keys.split(",") if key.strip()]
        )
        target_per_group = (
            BROWSER_CORE_TARGET_PER_GROUP
            if args.browser_core_coverage
            else max(0, args.peer_target_per_group)
        )
        codes = select_peer_evaluation_coverage_codes(
            limit=max(1, args.limit),
            peer_group_keys=peer_group_keys,
            target_per_group=target_per_group,
            min_age_days=max(0, args.min_age_days),
            include_exchange_funds=True,
        )
    elif not codes:
        codes = select_target_codes(
            limit=max(1, args.limit),
            fund_type=args.fund_type.strip(),
            missing_only=not args.include_existing,
            min_age_days=args.min_age_days,
            include_exchange_funds=args.include_exchange_funds,
        )
    else:
        codes = codes[: max(1, args.limit)]

    if not codes:
        log("没有需要同步的基金。")
        return 0

    if fof_lookthrough_mode:
        from services.fund_fof_holding_service import FundFofHoldingService

        service = FundFofHoldingService()
        synced = 0
        insufficient = 0
        failed = 0
        log(f"开始同步 FOF 底层基金穿透：{len(codes)} 只")
        for index, wind_code in enumerate(codes, start=1):
            try:
                classification = get_fund_classification_repo().get_classification_context(wind_code) or {}
                result = sync_fof_lookthrough(wind_code, classification, service)
                if result.get("evidence_gate_status") == "sufficient":
                    synced += 1
                    log(
                        f"[{index}/{len(codes)}] OK {wind_code} "
                        f"底层基金={result.get('disclosed_fund_count', 0)} "
                        f"公开净值覆盖={result.get('disclosed_nav_ratio', 0):.2f}%"
                    )
                else:
                    insufficient += 1
                    log(f"[{index}/{len(codes)}] SKIP {wind_code}: {'；'.join(result.get('missing_items') or [])}")
            except Exception as error:
                failed += 1
                log(f"[{index}/{len(codes)}] FAIL {wind_code}: {error}")
            if args.throttle > 0:
                time.sleep(args.throttle)
        log(f"FOF 穿透同步完成：可评价 {synced}，证据不足 {insufficient}，失败 {failed}")
        return 0 if failed == 0 else 1

    end_date = date.today()
    start_date = end_date - timedelta(days=sync_days)
    rolling_service = RollingMetricService()
    synced = 0
    skipped = 0
    failed = 0
    tenure_synced = 0
    tenure_skipped = 0
    tenure_failed = 0
    evaluation_coverage_mode = bool(
        manager_evaluation_mode
        or company_evaluation_mode
        or args.peer_evaluation_coverage
        or args.browser_core_coverage
        or args.research_linked
    )
    tenure_sync_service = FundManagerTenureSyncService(data_service) if evaluation_coverage_mode else None

    log(f"开始同步基金排行指标：{len(codes)} 只，窗口 {start_date.isoformat()} ~ {end_date.isoformat()}")
    for index, wind_code in enumerate(codes, start=1):
        try:
            result = sync_one_fund(data_service, rolling_service, wind_code, start_date, end_date)
            if result["status"] == "synced":
                synced += 1
                if tenure_sync_service is not None and result.get("manager_tenure_required"):
                    tenure_result = tenure_sync_service.sync_fund(wind_code)
                    if tenure_result.get("status") == "synced":
                        tenure_synced += 1
                    elif tenure_result.get("status") == "failed":
                        tenure_failed += 1
                    else:
                        tenure_skipped += 1
                log(
                    f"[{index}/{len(codes)}] OK {wind_code} "
                    f"NAV={result['nav_points']} 1Y={result.get('return_1y')} "
                    f"DD={result.get('max_drawdown_1y')} Sharpe={result.get('sharpe_1y')}"
                    + (
                        f" FOF穿透={result['fof_lookthrough'].get('evidence_gate_status')}"
                        if (result.get("fof_lookthrough") or {}).get("status") != "not_applicable"
                        else ""
                    )
                )
            else:
                skipped += 1
                log(f"[{index}/{len(codes)}] SKIP {wind_code}: {result.get('reason')}")
        except Exception as error:
            failed += 1
            log(f"[{index}/{len(codes)}] FAIL {wind_code}: {error}")
            if failed >= args.max_errors:
                raise RuntimeError(f"错误数达到上限 {args.max_errors}") from error
        if args.throttle > 0:
            time.sleep(args.throttle)

    summary = {
        "requested": len(codes),
        "synced": synced,
        "skipped": skipped,
        "failed": failed,
        "tenure_synced": tenure_synced,
        "tenure_skipped": tenure_skipped,
        "tenure_failed": tenure_failed,
    }
    if manager_evaluation_mode:
        history_result = tenure_sync_service.sync_manager(args.manager_id.strip())
        summary["manager_tenure_history_status"] = history_result.get("status")
        summary["manager_tenure_count"] = int(history_result.get("tenure_count") or 0)
        refreshed = FundManagerResearchService().build(args.manager_id.strip())
        refreshed_coverage = refreshed.get("coverage") or {}
        summary["evaluated_fund_count"] = int(refreshed_coverage.get("evaluated_fund_count") or 0)
        summary["current_fund_count"] = int(refreshed_coverage.get("current_fund_count") or 0)
    log(f"同步完成：{json.dumps(summary, ensure_ascii=False)}")
    return 0 if failed == 0 and tenure_failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
