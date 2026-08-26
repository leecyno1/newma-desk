"""
基金路由 - 基金搜索、详情、净值、持仓
数据源: Tushare (通过 service_registry.get_data_service())
数据持久化: PostgreSQL (通过 repositories)
缓存: Redis/内存 (通过 services.cache_service)
"""
import math
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Any, List, Optional
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID
import logging

from lib.holding_weight_validation import fund_nav_weight, validate_fund_nav_weights
from services.fund_manager_tenure_context import (
    enrich_profile_with_manager_tenure,
    resolve_manager_tenure_context,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/funds", tags=["基金"])


FUND_TYPE_FILTER_MAP = {
    "stock": "股票型",
    "hybrid": "混合型",
    "bond": "债券型",
    "index": "指数型",
    "money": "货币型",
    "qdii": "QDII",
}


class CompareMatrixRequest(BaseModel):
    windCodes: List[str]
    window: str = "1y"


class AlignedCompareRequest(BaseModel):
    windCodes: List[str]


class HoldingSimilarityRequest(BaseModel):
    windCodes: List[str]


def _clean_nan(obj):
    """递归清理 NaN/Inf 值"""
    if isinstance(obj, dict):
        return {k: _clean_nan(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_clean_nan(item) for item in obj]
    elif isinstance(obj, (datetime, date)):
        return obj.isoformat()
    elif isinstance(obj, UUID):
        return str(obj)
    elif isinstance(obj, Decimal):
        return float(obj)
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
    return obj


def _normalize_fund_type_filter(fund_type: Optional[str]) -> Optional[str]:
    if not fund_type:
        return None
    value = fund_type.strip()
    return FUND_TYPE_FILTER_MAP.get(value.lower(), value)


def _as_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
        return parsed if math.isfinite(parsed) else None
    except (TypeError, ValueError):
        return None


def _cache_value(value: Any) -> str:
    return "" if value is None else str(value)


def _sales_status(info: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": info.get("status") or info.get("state") or None,
        "market": info.get("market") or None,
        "purchase_start_date": info.get("purchase_start_date") or None,
        "redeem_start_date": info.get("redeem_start_date") or None,
        "source": "tushare.fund_basic",
    }


def _fee_info(info: dict[str, Any]) -> dict[str, Any]:
    return {
        "management_fee": _as_float(info.get("management_fee")),
        "custodian_fee": _as_float(info.get("custodian_fee")),
        "source": "tushare.fund_basic",
        "missing": [
            item for item, value in {
                "申购费": None,
                "赎回费": None,
                "销售服务费": None,
                "限购信息": None,
            }.items() if value is None
        ],
    }


def _api_fund_from_row(row: dict[str, Any], scoring_engine=None) -> dict[str, Any]:
    perf = row.get("performance_data", {}) or {}
    risk = row.get("risk_metrics", {}) or {}
    raw_data = row.get("raw_data") or {}
    info = raw_data.get("info") if isinstance(raw_data, dict) else {}
    universe = raw_data.get("universe") if isinstance(raw_data, dict) else {}
    if not isinstance(info, dict):
        info = {}
    if not isinstance(universe, dict):
        universe = {}
    base_info = {**universe, **info}
    sales_status = _sales_status(base_info)
    fee_info = _fee_info(base_info)
    raw_state = sales_status.get("status") or (raw_data.get("status") if isinstance(raw_data, dict) else None)
    operation_status = _operation_status(row.get("name") or "", raw_state, sales_status)
    scoring = None
    if scoring_engine is not None:
        scoring_result = scoring_engine.score_fund(perf, risk, {})
        scoring = {
            "overall_score": scoring_result["overall_score"],
            "overall_grade": scoring_result["overall_grade"],
        }

    payload = {
        "id": row.get("id"),
        "wind_code": row.get("wind_code"),
        "name": row.get("name"),
        "type": row.get("type", ""),
        "manager_ids": row.get("manager_ids") or [],
        "total_asset": row.get("total_asset"),
        "nav": row.get("nav"),
        "nav_date": row.get("nav_date"),
        "establishment_date": row.get("establishment_date") or base_info.get("establishment_date"),
        "updated_at": row.get("updated_at"),
        "operation_status": operation_status,
        "sales_status": sales_status,
        "fee_info": fee_info,
        "benchmark": base_info.get("benchmark") or row.get("benchmark") or None,
        "contract_benchmark": base_info.get("benchmark") or row.get("benchmark") or None,
        "company": row.get("company") or base_info.get("company") or raw_data.get("company"),
        "custodian": row.get("custodian") or base_info.get("custodian"),
        "invest_type": row.get("invest_type") or base_info.get("invest_type"),
        "contract_type": row.get("contract_type") or base_info.get("contract_type"),
        "management_fee": row.get("management_fee") or base_info.get("management_fee"),
        "custodian_fee": row.get("custodian_fee") or base_info.get("custodian_fee"),
        "performance": perf,
        "performance_data": perf,
        "risk_metrics": risk,
        "holding_count": row.get("holding_count"),
    }
    if row.get("screening_score") is not None:
        payload["screening_score"] = row.get("screening_score")
    if row.get("evidence_coverage_score") is not None:
        payload["evidence_coverage_score"] = row.get("evidence_coverage_score")
    if row.get("research_checklist_status") is not None:
        payload["market_research_checklist"] = {
            "status": row.get("research_checklist_status"),
            "label": {
                "complete": "体检通过",
                "repair": "待补证",
                "blocked": "阻断",
            }.get(row.get("research_checklist_status"), "待核"),
            "pass_count": row.get("research_checklist_pass_count"),
            "total_count": row.get("research_checklist_total_count") or 6,
            "primary_gap": row.get("research_checklist_primary_gap") or None,
            "source": "local.postgres.full_market_research_checklist",
        }
    if scoring is not None:
        payload["scoring"] = scoring
    return _clean_nan(payload)


def _api_manager_from_row(row: dict[str, Any]) -> dict[str, Any]:
    raw_data = row.get("raw_data") if isinstance(row.get("raw_data"), dict) else {}
    return _clean_nan({
        "manager_id": row.get("wind_code"),
        "wind_code": row.get("wind_code"),
        "name": row.get("name"),
        "company": row.get("company"),
        "education": row.get("education"),
        "work_years": row.get("work_years"),
        "management_years": row.get("management_years"),
        "current_funds": row.get("current_funds") or [],
        "begin_date": raw_data.get("begin_date"),
        "end_date": raw_data.get("end_date"),
        "source": "tushare.fund_manager",
    })


def _attach_manager_summaries(funds: list[dict[str, Any]], manager_repo) -> None:
    manager_ids = [
        manager_id
        for fund in funds
        for manager_id in (fund.get("manager_ids") or [])
        if manager_id
    ]
    if not manager_ids:
        for fund in funds:
            fund["managers"] = []
        return
    manager_map = manager_repo.get_managers_by_ids(manager_ids)
    for fund in funds:
        fund["managers"] = [
            _api_manager_from_row(manager_map[manager_id])
            for manager_id in (fund.get("manager_ids") or [])
            if manager_id in manager_map
        ]


def _operation_status(name: str, raw_state: Any, sales_status: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """面向买前核查的可购买性状态。"""
    normalized_name = str(name or "")
    state = str(raw_state or "").strip()
    purchase_start = (sales_status or {}).get("purchase_start_date")
    redeem_start = (sales_status or {}).get("redeem_start_date")
    if any(token in normalized_name for token in ("退市", "清算", "终止", "摘牌")):
        return {
            "status": "blocked",
            "label": "不可申购",
            "reason": "基金名称或状态含退市/清算/终止信号，不能作为买入候选。",
            "raw_state": state or None,
            "purchase_start_date": purchase_start,
            "redeem_start_date": redeem_start,
        }
    blocked_states = {"D", "DELIST", "TERMINATED", "LIQUIDATED", "清算", "终止", "退市", "摘牌"}
    if state.upper() in blocked_states or state in blocked_states:
        return {
            "status": "blocked",
            "label": "非在运作",
            "reason": f"Tushare 返回状态 {state}，存在退市/清算/终止信号，不能作为购买候选。",
            "raw_state": state,
            "purchase_start_date": purchase_start,
            "redeem_start_date": redeem_start,
        }
    if purchase_start:
        try:
            start_date = datetime.fromisoformat(purchase_start).date()
            if start_date > date.today():
                return {
                    "status": "blocked",
                    "label": "申购未开放",
                    "reason": f"Tushare 显示申购起始日为 {purchase_start}，未到开放日，不能作为当前购买候选。",
                    "raw_state": state or None,
                    "purchase_start_date": purchase_start,
                    "redeem_start_date": redeem_start,
                }
        except ValueError:
            pass
        return {
            "status": "watch",
            "label": "Tushare开放",
            "reason": f"Tushare fund_basic 显示申购起始日 {purchase_start}、赎回起始日 {redeem_start or '待补'}；买前仍需销售平台确认实时开放和限购。",
            "raw_state": state or None,
            "purchase_start_date": purchase_start,
            "redeem_start_date": redeem_start,
        }
    return {
        "status": "unknown",
        "label": "申购待核",
        "reason": "Tushare 未返回明确申购/赎回开放状态，买前需补充销售端状态与费率。",
        "raw_state": None,
        "purchase_start_date": purchase_start,
        "redeem_start_date": redeem_start,
    }


def _rolling_metric_panel(panel: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    fields = {
        "total_return",
        "annualized_return",
        "max_drawdown",
        "annualized_volatility",
        "positive_return_ratio",
        "sharpe_ratio",
        "sortino_ratio",
        "calmar_ratio",
        "excess_return",
        "information_ratio",
        "observations",
        "tenure_days",
    }
    result: dict[str, dict[str, Any]] = {}
    for item in panel:
        window = item.get("metric_window")
        metric_name = item.get("metric_name")
        if not window or metric_name not in fields:
            continue
        result.setdefault(window, {})[metric_name] = item.get("metric_value")
        result[window]["as_of_date"] = item.get("as_of_date")
        if item.get("benchmark_code"):
            result[window]["benchmark_code"] = item.get("benchmark_code")
        if item.get("peer_group_key"):
            result[window]["peer_group_key"] = item.get("peer_group_key")
    return result


def _quarter_before(quarter: str) -> str:
    year = int(quarter[:4])
    number = int(quarter[-1])
    return f"{year - 1}Q4" if number == 1 else f"{year}Q{number - 1}"


def _latest_holding_quarter_candidates(limit: int = 6) -> list[str]:
    current = f"{datetime.now().year}Q{(datetime.now().month - 1) // 3 + 1}"
    current = _quarter_before(current)
    result = []
    for _ in range(limit):
        result.append(current)
        current = _quarter_before(current)
    return result


def _holding_market(stock_code: Any) -> str:
    code = str(stock_code or "").upper()
    if code.endswith(".HK"):
        return "港股"
    if code.endswith(".SH"):
        return "沪市"
    if code.endswith(".SZ"):
        return "深市"
    if code.endswith(".BJ"):
        return "北交所"
    return "其他"


def _enrich_holding_industry_evidence(holdings: list[dict[str, Any]]) -> dict[str, Any]:
    hong_kong_holdings = []
    for holding in holdings:
        holding["market"] = _holding_market(holding.get("stock_code"))
        if holding["market"] == "港股":
            hong_kong_holdings.append(holding)

    if not hong_kong_holdings:
        return {
            "status": "not_applicable",
            "hong_kong_holding_count": 0,
            "matched_holding_count": 0,
        }

    try:
        from repositories import get_market_index_constituent_repo

        snapshot = get_market_index_constituent_repo().get_latest("HSCI-INDUSTRY")
    except Exception as exc:
        logger.warning("Holding industry evidence unavailable: %s", exc)
        snapshot = None

    if not snapshot:
        return {
            "status": "unavailable",
            "hong_kong_holding_count": len(hong_kong_holdings),
            "matched_holding_count": 0,
            "note": "尚无恒生指数公司行业分类快照。",
        }

    constituent_map = {
        str(item.get("constituent_code") or "").upper(): item
        for item in snapshot.get("constituents") or []
    }
    matched = 0
    evidence_url = None
    for holding in hong_kong_holdings:
        evidence = constituent_map.get(str(holding.get("stock_code") or "").upper())
        if not evidence or not evidence.get("industry"):
            continue
        matched += 1
        evidence_url = evidence_url or evidence.get("evidence_url")
        holding["industry"] = evidence.get("industry")
        holding["industry_source"] = snapshot.get("source")
        holding["industry_as_of_date"] = snapshot.get("as_of_date")
        holding["industry_evidence_url"] = evidence.get("evidence_url")

    return {
        "status": "available" if matched == len(hong_kong_holdings) else "partial_evidence",
        "hong_kong_holding_count": len(hong_kong_holdings),
        "matched_holding_count": matched,
        "as_of_date": snapshot.get("as_of_date"),
        "source": snapshot.get("source"),
        "evidence_url": evidence_url,
        "note": "港股行业名称采用最新恒生行业分类，仅用于持仓展示；历史 Brinson 仍只使用区间开始日前快照。",
    }


def _holding_summary(holdings: list[dict[str, Any]]) -> dict[str, Any]:
    weight_validation = validate_fund_nav_weights(holdings)
    fund_nav_weights = [fund_nav_weight(item) for item in holdings]
    equity_weights = [_as_float(item.get("equity_portfolio_weight")) for item in holdings]
    has_fund_nav_weights = bool(holdings) and all(value is not None and value >= 0 for value in fund_nav_weights)
    has_equity_weights = bool(holdings) and any(value is not None and value >= 0 for value in equity_weights)
    selected_weights = fund_nav_weights if has_fund_nav_weights else equity_weights
    industry_buckets: dict[str, float] = {}
    market_buckets: dict[str, float] = {}
    holding_sources = list(dict.fromkeys(
        str(item.get("source") or "") for item in holdings if item.get("source")
    ))
    weight_sources = list(dict.fromkeys(
        str(item.get("weight_source") or "") for item in holdings if item.get("weight_source")
    ))
    fund_net_asset_bases = list(dict.fromkeys(
        str(item.get("fund_net_asset_basis") or "")
        for item in holdings
        if item.get("fund_net_asset_basis")
    ))
    for item, weight in zip(holdings, selected_weights):
        if weight is None:
            continue
        industry = str(item.get("industry") or "未知")
        market = str(item.get("market") or _holding_market(item.get("stock_code")))
        industry_buckets[industry] = industry_buckets.get(industry, 0.0) + weight
        market_buckets[market] = market_buckets.get(market, 0.0) + weight
    return {
        "holding_count": len(holdings),
        "weight_basis": "fund_nav" if has_fund_nav_weights else "equity_portfolio",
        "weight_validation": weight_validation.as_dict(),
        "report_date": max((str(item.get("report_date") or "") for item in holdings), default="") or None,
        "announcement_date": max((str(item.get("announcement_date") or "") for item in holdings), default="") or None,
        "synced_at": max((str(item.get("synced_at") or "") for item in holdings), default="") or None,
        "holding_sources": holding_sources,
        "weight_sources": weight_sources,
        "weight_source_urls": list(dict.fromkeys(
            str(item.get("weight_source_url") or "")
            for item in holdings
            if item.get("weight_source_url")
        )),
        "fund_net_asset_bases": fund_net_asset_bases,
        "fund_net_asset_date": max((str(item.get("fund_net_asset_date") or "") for item in holdings), default="") or None,
        "top_three_weight": round(sum(value for value in fund_nav_weights[:3] if value is not None), 6) if has_fund_nav_weights else None,
        "top_ten_weight": round(sum(value for value in fund_nav_weights[:10] if value is not None), 6) if has_fund_nav_weights else None,
        "top_three_equity_weight": round(sum(value for value in equity_weights[:3] if value is not None), 6) if has_equity_weights else None,
        "top_ten_equity_weight": round(sum(value for value in equity_weights[:10] if value is not None), 6) if has_equity_weights else None,
        "industry_buckets": [
            {"industry": industry, "weight": round(weight, 6)}
            for industry, weight in sorted(industry_buckets.items(), key=lambda item: item[1], reverse=True)
        ],
        "market_buckets": [
            {"market": market, "weight": round(weight, 6)}
            for market, weight in sorted(market_buckets.items(), key=lambda item: item[1], reverse=True)
        ],
        "industry_weight_basis": "fund_nav" if has_fund_nav_weights else "equity_portfolio",
    }


@router.get("/")
async def list_funds(
    fund_type: Optional[str] = Query(None, description="基金类型: stock/hybrid/bond/index/..."),
    keyword: Optional[str] = Query(None, description="搜索关键词（基金名称/代码）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    asset_min: Optional[float] = Query(None, description="最小基金规模（亿）"),
    asset_max: Optional[float] = Query(None, description="最大基金规模（亿）"),
    established_from: Optional[str] = Query(None, description="成立日期起点"),
    established_to: Optional[str] = Query(None, description="成立日期终点"),
    evidence_status: Optional[str] = Query(None, description="买前证据状态: ready/verify/blocked"),
    has_manager: Optional[bool] = Query(None, description="是否要求基金经理证据"),
    min_manager_years: Optional[float] = Query(None, ge=0, description="最低现任经理管理年限"),
    has_fee: Optional[bool] = Query(None, description="是否要求管理费/托管费证据"),
    fee_max: Optional[float] = Query(None, ge=0, description="管理费+托管费上限（%）"),
    tradable_only: Optional[bool] = Query(None, description="是否排除退市/清算/未到申购开放日基金"),
    return_1y_min: Optional[float] = Query(None, description="近1年收益下限（小数，如 0.2 表示 20%）"),
    return_1y_max: Optional[float] = Query(None, description="近1年收益上限（小数，如 0.2 表示 20%）"),
    return_3y_min: Optional[float] = Query(None, description="近3年收益下限（小数，如 0.2 表示 20%）"),
    return_3y_max: Optional[float] = Query(None, description="近3年收益上限（小数，如 0.2 表示 20%）"),
    max_drawdown_1y_max: Optional[float] = Query(None, ge=0, description="近1年最大回撤上限（绝对值小数，如 0.2 表示 20%）"),
    volatility_1y_max: Optional[float] = Query(None, ge=0, description="近1年波动率上限（小数，如 0.2 表示 20%）"),
    sharpe_1y_min: Optional[float] = Query(None, description="近1年夏普比率下限"),
    screening_score_min: Optional[float] = Query(None, ge=0, le=100, description="全市场初筛分下限（0-100）"),
    screening_score_max: Optional[float] = Query(None, ge=0, le=100, description="全市场初筛分上限（0-100）"),
    evidence_coverage_min: Optional[float] = Query(None, ge=0, le=100, description="真实证据覆盖分下限（0-100）"),
    research_checklist_status: Optional[str] = Query(None, description="全市场买前研究体检状态: complete/repair/blocked"),
    research_checklist_gap: Optional[str] = Query(None, description="全市场买前研究体检首要缺口"),
    sales_rule_complete: Optional[bool] = Query(None, description="是否要求销售规则硬缺口清零"),
    purchase_plan: str = Query("sip", description="买入方式口径: sip/lump_sum，用于销售规则完整性判断"),
    planned_amount: Optional[float] = Query(None, ge=0, description="本次买前计划金额，用于起购/定投起点/限购门禁"),
    max_sales_risk_level: Optional[int] = Query(None, ge=1, le=5, description="投资者可承受的最高销售风险等级 R1-R5"),
    sales_risk_filter: Optional[str] = Query(None, description="销售风险适当性筛选: matched/mismatch/missing/known"),
    has_nav: Optional[bool] = Query(None, description="是否要求净值和净值日期"),
    has_performance: Optional[bool] = Query(None, description="是否要求收益或夏普证据"),
    has_holdings: Optional[bool] = Query(None, description="是否要求可用于持仓/行业暴露判断的持仓明细"),
    sort_by: str = Query("updated_at", description="排序字段: rank/return/risk/sharpe/screening_score/evidence_coverage/research_checklist/name/updated_at/nav/total_asset"),
    sort_order: str = Query("desc", description="排序方向: asc/desc"),
):
    """获取基金列表（优先从 PostgreSQL 获取，无数据则从 Tushare 查询并缓存）"""
    from services.cache_service import get_cache, CacheKey, TTL
    from service_registry import get_data_service, get_scoring_engine
    from repositories import get_fund_classification_repo, get_fund_repo, get_manager_repo, get_metric_snapshot_repo, get_research_profile_repo

    cache = get_cache()
    safe_purchase_plan = "lump_sum" if purchase_plan == "lump_sum" else "sip"
    safe_planned_amount = planned_amount if planned_amount is not None and planned_amount > 0 else None

    # 尝试从缓存获取
    normalized_fund_type = _normalize_fund_type_filter(fund_type)
    has_sales_context = any(value is not None and value != "" for value in [
        sales_rule_complete,
        safe_planned_amount,
        max_sales_risk_level,
        sales_risk_filter,
    ])
    has_explicit_filters = any(value is not None and value != "" for value in [
        normalized_fund_type,
        keyword,
        asset_min,
        asset_max,
        established_from,
        established_to,
        evidence_status,
        has_manager,
        min_manager_years,
        has_fee,
        fee_max,
        tradable_only,
        return_1y_min,
        return_1y_max,
        return_3y_min,
        return_3y_max,
        max_drawdown_1y_max,
        volatility_1y_max,
        sharpe_1y_min,
        screening_score_min,
        screening_score_max,
        evidence_coverage_min,
        research_checklist_status,
        research_checklist_gap,
        sales_rule_complete,
        has_sales_context,
        has_nav,
        has_performance,
        has_holdings,
    ])

    cache_key = (
        f"fund:list:v9:{normalized_fund_type or ''}:{keyword or ''}:{page}:{page_size}:"
        f"{_cache_value(asset_min)}:{_cache_value(asset_max)}:{established_from or ''}:{established_to or ''}:"
        f"{evidence_status or ''}:{_cache_value(has_manager)}:{_cache_value(min_manager_years)}:{_cache_value(has_fee)}:{_cache_value(fee_max)}:{_cache_value(tradable_only)}:"
        f"{_cache_value(return_1y_min)}:{_cache_value(return_1y_max)}:{_cache_value(return_3y_min)}:{_cache_value(return_3y_max)}:"
        f"{_cache_value(max_drawdown_1y_max)}:{_cache_value(volatility_1y_max)}:{_cache_value(sharpe_1y_min)}:{_cache_value(screening_score_min)}:{_cache_value(screening_score_max)}:{_cache_value(evidence_coverage_min)}:{research_checklist_status or ''}:{research_checklist_gap or ''}:{_cache_value(sales_rule_complete)}:"
        f"{safe_purchase_plan}:{_cache_value(safe_planned_amount)}:{_cache_value(max_sales_risk_level)}:{sales_risk_filter or ''}:"
        f"{_cache_value(has_nav)}:{_cache_value(has_performance)}:{_cache_value(has_holdings)}:{sort_by}:{sort_order}:v17"
    )
    cached = cache.get(cache_key)
    if cached is not None:
        logger.debug(f"[CACHE HIT] {cache_key}")
        return _clean_nan(cached)

    data_svc = get_data_service()
    scoring_engine = get_scoring_engine()
    fund_repo = get_fund_repo()
    manager_repo = get_manager_repo()
    research_profile_repo = get_research_profile_repo()
    metric_snapshot_repo = get_metric_snapshot_repo()
    classification_repo = get_fund_classification_repo()

    # 尝试从数据库获取
    db_result = None
    try:
        db_result = fund_repo.list_funds(
            fund_type=normalized_fund_type,
            keyword=keyword,
            page=page,
            page_size=page_size,
            asset_min=asset_min,
            asset_max=asset_max,
            established_from=established_from,
            established_to=established_to,
            evidence_status=evidence_status,
            has_manager=has_manager,
            min_manager_years=min_manager_years,
            has_fee=has_fee,
            fee_max=fee_max,
            tradable_only=tradable_only,
            return_1y_min=return_1y_min,
            return_1y_max=return_1y_max,
            return_3y_min=return_3y_min,
            return_3y_max=return_3y_max,
            max_drawdown_1y_max=max_drawdown_1y_max,
            volatility_1y_max=volatility_1y_max,
            sharpe_1y_min=sharpe_1y_min,
            screening_score_min=screening_score_min,
            screening_score_max=screening_score_max,
            evidence_coverage_min=evidence_coverage_min,
            research_checklist_status=research_checklist_status,
            research_checklist_gap=research_checklist_gap,
            sales_rule_complete=sales_rule_complete,
            purchase_plan=safe_purchase_plan,
            planned_amount=safe_planned_amount,
            max_sales_risk_level=max_sales_risk_level,
            sales_risk_filter=sales_risk_filter,
            has_nav=has_nav,
            has_performance=has_performance,
            has_holdings=has_holdings,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except Exception as e:
        logger.error(f"DB query failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "code": "database_unavailable",
                "message": "基金研究数据库不可用，请先启动 PostgreSQL 并确认本地基金库已导入。",
                "error": e.__class__.__name__,
            },
        ) from e

    if db_result is not None and (db_result.get("total", 0) > 0 or has_explicit_filters):
        funds = [_api_fund_from_row(f, scoring_engine) for f in db_result.get("funds", [])]
        _attach_manager_summaries(funds, manager_repo)
        fund_codes = [fund.get("wind_code") for fund in funds if fund.get("wind_code")]
        profile_map = research_profile_repo.list_profiles(fund_codes)
        peer_group_map = classification_repo.list_fund_peer_group_map(fund_codes)
        for fund in funds:
            code = fund.get("wind_code")
            profile = profile_map.get(code) or {}
            peer_group = peer_group_map.get(code) or {}
            fund["research_profile"] = {
                **profile,
                "peer_group": peer_group.get("peer_group_name") or profile.get("peer_group"),
                "peer_group_id": peer_group.get("peer_group_id"),
                "peer_group_key": peer_group.get("peer_group_key"),
                "classification_confidence": peer_group.get("confidence"),
                "classification_source": peer_group.get("source"),
            }
            try:
                fund["rolling_metrics"] = _rolling_metric_panel(
                    metric_snapshot_repo.get_latest_panel("fund", fund.get("wind_code"))
                )
            except Exception as exc:
                logger.warning(f"Rolling metrics unavailable for {fund.get('wind_code')}: {exc}")
                fund["rolling_metrics"] = {}

        sort_keys = {
            "return": lambda x: x.get("performance", {}).get("annualized_return_1y") or 0,
            "risk": lambda x: abs(x.get("risk_metrics", {}).get("max_drawdown_1y") or x.get("risk_metrics", {}).get("max_drawdown") or x.get("performance", {}).get("max_drawdown") or 0),
            "sharpe": lambda x: x.get("performance", {}).get("sharpe_ratio") or 0,
            "name": lambda x: x.get("name", ""),
            "rank": lambda x: x.get("scoring", {}).get("overall_score", 0),
            "screening_score": lambda x: x.get("screening_score") or 0,
            "evidence_coverage": lambda x: x.get("evidence_coverage_score") or 0,
        }
        if sort_by in sort_keys:
            funds.sort(key=sort_keys[sort_by], reverse=(sort_order == "desc"))

        result = _clean_nan({
            "total": db_result.get("total", 0),
            "page": page,
            "page_size": page_size,
            "funds": funds,
            "source": "database",
            "summary": db_result.get("summary") or {},
        })
        cache.set(cache_key, result, TTL.MEDIUM)
        return result
    else:
        # 无数据，从 Tushare 查询
        list_result = data_svc.get_fund_list(fund_type=normalized_fund_type, page=page, page_size=page_size)
        wind_codes = list_result.get("list", [])
        funds = []

        for code in wind_codes:
            try:
                info = data_svc.get_fund_info(code)
                perf = data_svc.get_fund_performance(code)
                risk = data_svc.get_fund_risk_metrics(code)
                style = data_svc.get_fund_style(code)
                scoring = scoring_engine.score_fund(perf, risk, style)

                if keyword:
                    name = info.get("name", "")
                    if keyword.lower() not in name.lower() and keyword.upper() not in code.upper():
                        continue

                try:
                    fund_repo.upsert_fund(code, {**info, "performance": perf, "risk_metrics": risk})
                except Exception as db_err:
                    logger.warning(f"DB save failed for {code}: {db_err}")

                funds.append({
                    **info, "performance": perf, "risk_metrics": risk,
                    "scoring": {"overall_score": scoring["overall_score"], "overall_grade": scoring["overall_grade"]},
                })
            except Exception as e:
                logger.error(f"Error processing fund {code}: {e}")

        sort_keys = {
            "return": lambda x: x.get("performance", {}).get("annualized_return_1y") or 0,
            "risk": lambda x: abs(x.get("risk_metrics", {}).get("max_drawdown_1y") or x.get("risk_metrics", {}).get("max_drawdown") or x.get("performance", {}).get("max_drawdown") or 0),
            "sharpe": lambda x: x.get("performance", {}).get("sharpe_ratio") or 0,
            "name": lambda x: x.get("name", ""),
        }
        if sort_by in sort_keys:
            funds.sort(key=sort_keys[sort_by], reverse=(sort_order == "desc"))

        result = _clean_nan({"total": list_result.get("total", 0), "page": page, "page_size": page_size, "funds": funds, "source": "tushare"})
        cache.set(cache_key, result, TTL.SHORT)
        return result


@router.post("/compare-matrix")
async def compare_fund_matrix(payload: CompareMatrixRequest):
    """结构化基金对比矩阵：指标、同类分位、最佳项和建议。"""
    try:
        from services.peer_comparison_service import PeerComparisonService

        result = PeerComparisonService().build_comparison_matrix(payload.windCodes, window=payload.window)
        return _clean_nan(result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error(f"Compare fund matrix error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/compare-aligned")
async def compare_fund_aligned(payload: AlignedCompareRequest):
    """仅使用共同净值日期计算同区间曲线和风险收益指标。"""
    try:
        from services.fund_aligned_comparison_service import FundAlignedComparisonService

        return _clean_nan(FundAlignedComparisonService().build(payload.windCodes))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error(f"Aligned fund comparison error: {exc}")
        raise HTTPException(status_code=500, detail="基金同区间比较暂时不可用")


@router.post("/holding-similarity")
async def compare_fund_holding_similarity(payload: HoldingSimilarityRequest):
    """比较同一报告期前十大公开重仓股的重合度。"""
    try:
        from services.fund_holding_similarity_service import FundHoldingSimilarityService

        return _clean_nan(FundHoldingSimilarityService().build(payload.windCodes))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error(f"Fund holding similarity error: {exc}")
        raise HTTPException(status_code=500, detail="基金重仓相似度暂时不可用")


@router.get("/{wind_code}/peer-percentiles")
async def get_fund_peer_percentiles(wind_code: str, window: str = Query("1y")):
    """获取单只基金在同类池中的指标分位。"""
    try:
        from services.peer_comparison_service import PeerComparisonService

        result = PeerComparisonService().build_peer_percentiles(wind_code, window=window)
        return _clean_nan(result)
    except Exception as exc:
        logger.error(f"Get peer percentiles error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/recommendation-categories")
async def get_recommendation_categories(limit: int = Query(100, ge=1, le=200)):
    """返回标准化专业同类组，不使用宽泛基金法律类型作为排名池。"""
    from repositories import get_fund_classification_repo

    categories = get_fund_classification_repo().list_peer_group_inventory(limit=limit)
    return {"categories": categories, "total": len(categories), "source": "standardized_peer_group_inventory"}


@router.get("/recommendation-universe")
async def get_recommendation_universe(
    peer_group: str = Query(..., min_length=1),
    limit: int = Query(30, ge=1, le=50),
    keyword: Optional[str] = Query(None),
):
    """按同类组返回用于现场评价的候选集，不在此接口跨类排序。"""
    from repositories import get_fund_classification_repo, get_manager_repo, get_metric_snapshot_repo, get_research_profile_repo

    profile_repo = get_research_profile_repo()
    classification_repo = get_fund_classification_repo()
    manager_repo = get_manager_repo()
    metric_repo = get_metric_snapshot_repo()
    rows = classification_repo.list_recommendation_funds(peer_group, limit=limit, keyword=keyword)
    total = classification_repo.count_recommendation_funds(peer_group, keyword=keyword)
    funds = [_api_fund_from_row(row) for row in rows]
    _attach_manager_summaries(funds, manager_repo)
    profile_map = profile_repo.list_profiles([fund.get("wind_code") for fund in funds if fund.get("wind_code")])
    for fund in funds:
        code = fund.get("wind_code")
        profile = profile_map.get(code) or {}
        matching_row = next((row for row in rows if row.get("wind_code") == code), {})
        fund["research_profile"] = {
            **profile,
            "peer_group": matching_row.get("standardized_peer_group_name") or peer_group,
            "peer_group_id": matching_row.get("standardized_peer_group_id"),
            "peer_group_key": matching_row.get("standardized_peer_group_key"),
        }
        try:
            fund["rolling_metrics"] = _rolling_metric_panel(metric_repo.get_latest_panel("fund", code))
        except Exception:
            fund["rolling_metrics"] = {}
    return _clean_nan({
        "peer_group": peer_group,
        "total": total,
        "returned": len(funds),
        "limit": limit,
        "funds": funds,
        "source": "database_peer_group_universe",
    })


@router.get("/recommendation-candidates")
async def get_recommendation_candidates(
    peer_group: str = Query(..., min_length=1),
    style: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=10),
):
    """基于完整标准同类组返回证据充分的基金候选组。"""
    from repositories import get_manager_repo
    from services.fund_recommendation_service import FundRecommendationService
    from services.fund_research_snapshot_service import FundResearchSnapshotService

    try:
        result = FundRecommendationService().build_candidate_group(
            peer_group=peer_group,
            style=style,
            limit=limit,
        )
        _attach_manager_summaries(result.get("candidates") or [], get_manager_repo())
        result["candidates"] = [
            FundResearchSnapshotService.candidate_snapshot(candidate)
            for candidate in result.get("candidates") or []
        ]
        return _clean_nan(result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error(f"Get recommendation candidates error: {exc}")
        raise HTTPException(status_code=500, detail="基金候选组暂时不可用")


@router.get("/recommendation-coverage")
async def get_recommendation_coverage(limit: int = Query(100, ge=1, le=200)):
    """返回每个标准同类组的分类、评价指标、风格和推荐覆盖。"""
    from services.fund_recommendation_service import FundRecommendationService

    try:
        return _clean_nan(FundRecommendationService().build_coverage_report(limit=limit))
    except Exception as exc:
        logger.error(f"Get recommendation coverage error: {exc}")
        raise HTTPException(status_code=500, detail="基金评价覆盖暂时不可用")


@router.get("/peer-group-universe")
async def get_peer_group_universe(
    peer_group: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=100),
    keyword: Optional[str] = Query(None),
):
    """按标准同类组返回基金浏览器候选集，不执行评分或跨类排序。"""
    return await get_recommendation_universe(peer_group=peer_group, limit=limit, keyword=keyword)


@router.get("/evaluation-history/recent")
async def get_recent_fund_evaluation_history(
    window: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(30, ge=1, le=100),
):
    """读取最近的基金评价结果，供评价中心统一回看。"""
    try:
        from services.fund_evaluation_history_service import FundEvaluationHistoryService

        result = FundEvaluationHistoryService().list_recent(
            evaluation_window=window,
            status=status,
            limit=limit,
        )
        return _clean_nan(result)
    except Exception as exc:
        logger.error(f"Get recent fund evaluation history error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{wind_code}/evaluation")
async def get_fund_evaluation(wind_code: str, window: str = Query("1y")):
    """获取分类、同类组、基准、专业评分和同类分位组成的基金评价快照。"""
    try:
        from services.fund_evaluation_service import FundEvaluationService

        result = FundEvaluationService().evaluate_fund(wind_code, window=window)
        return _clean_nan(result)
    except Exception as exc:
        logger.error(f"Get fund evaluation error for {wind_code}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{wind_code}/evaluation-statistics")
async def get_fund_evaluation_statistics(wind_code: str, window: str = Query("1y")):
    """获取同类可比评分的分布、统计和当前基金位置。"""
    try:
        from services.fund_evaluation_service import FundEvaluationService

        evaluation_service = FundEvaluationService()
        context = evaluation_service.load_context(wind_code)
        if not context.get("found"):
            raise HTTPException(status_code=404, detail=f"基金不存在: {wind_code}")
        result = evaluation_service.peer_comparison_service.build_peer_statistics(
            wind_code,
            window=window,
            target_context=context,
        )
        return _clean_nan(result)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Get fund evaluation statistics error for {wind_code}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{wind_code}/evaluation-history")
async def get_fund_evaluation_history(
    wind_code: str,
    window: Optional[str] = Query(None),
    limit: int = Query(30, ge=1, le=100),
):
    """读取用户主动保存的专业评价历史。"""
    try:
        from services.fund_evaluation_history_service import FundEvaluationHistoryService

        result = FundEvaluationHistoryService().list_history(
            wind_code,
            evaluation_window=window,
            limit=limit,
        )
        return _clean_nan(result)
    except Exception as exc:
        logger.error(f"Get fund evaluation history error for {wind_code}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{wind_code}/evaluation-history")
async def save_fund_evaluation_history(
    wind_code: str,
    window: str = Query("1y"),
):
    """现场计算并保存一次专业评价；页面刷新不会自动新增记录。"""
    try:
        from services.fund_evaluation_history_service import FundEvaluationHistoryService

        result = FundEvaluationHistoryService().save_current(wind_code, window=window)
        return _clean_nan(result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(f"Save fund evaluation history error for {wind_code}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{wind_code}/evaluation-history/{snapshot_id}")
async def get_fund_evaluation_history_snapshot(wind_code: str, snapshot_id: str):
    """读取一条已保存评价，供用户复核当时的完整结果。"""
    try:
        from services.fund_evaluation_history_service import FundEvaluationHistoryService

        result = FundEvaluationHistoryService().get_snapshot(wind_code, snapshot_id)
        return _clean_nan(result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(f"Get fund evaluation history snapshot error for {wind_code}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{wind_code}/research-snapshot")
async def get_fund_research_snapshot(
    wind_code: str,
    window: str = Query("1y"),
    include_research: bool = Query(True),
    include_attribution: bool = Query(False),
    live_attribution: bool = Query(True),
):
    """详情、推荐和 AI 共用的统一基金研究快照。"""
    from services.fund_research_snapshot_service import FundResearchSnapshotService

    try:
        result = FundResearchSnapshotService().build(
            wind_code,
            window=window,
            include_research=include_research,
            include_attribution=include_attribution,
            live_attribution=live_attribution,
        )
        return _clean_nan(result)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(f"Get fund research snapshot error for {wind_code}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{wind_code}/product-profile")
async def get_fund_product_profile(wind_code: str, refresh: bool = Query(False)):
    """读取本地产品介绍与费率档案；仅在明确 refresh 时更新外部公开数据。"""
    from services.fund_product_profile_service import FundProductProfileService

    try:
        service = FundProductProfileService()
        return _clean_nan(service.sync(wind_code) if refresh else service.get(wind_code))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(f"Get fund product profile error for {wind_code}: {exc}")
        raise HTTPException(status_code=500, detail="基金产品档案暂时不可用")


@router.get("/{wind_code}/asset-allocation")
async def get_fund_asset_allocation(
    wind_code: str,
    limit: int = Query(20, ge=1, le=100),
    refresh: bool = Query(False),
):
    """获取基金定期报告披露的股票、债券、现金和净资产历史。"""
    from services.fund_asset_allocation_service import FundAssetAllocationService

    return _clean_nan(FundAssetAllocationService().get(wind_code, limit=limit, refresh=refresh))


@router.get("/{wind_code}/share-classes")
async def get_fund_share_classes(wind_code: str):
    """获取同一基金实体的 A/C/Y 等份额及可核验费率事实。"""
    from services.fund_share_class_service import FundShareClassService

    try:
        return _clean_nan(FundShareClassService().get(wind_code))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(f"Get fund share classes error for {wind_code}: {exc}")
        raise HTTPException(status_code=500, detail="基金份额比较暂时不可用")


@router.get("/{wind_code}/manager-history")
async def get_fund_manager_history(wind_code: str):
    """获取基金实体的历任经理记录；同一基金的不同份额会合并。"""
    from services.fund_manager_history_service import FundManagerHistoryService

    try:
        return _clean_nan(FundManagerHistoryService().get(wind_code))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(f"Get fund manager history error for {wind_code}: {exc}")
        raise HTTPException(status_code=500, detail="基金经理历史暂时不可用")


@router.get("/{wind_code}/drawdown-recovery")
async def get_fund_drawdown_recovery(wind_code: str):
    """获取本地真实净值的回撤事件、持续时间和修复时间。"""
    from services.fund_drawdown_recovery_service import FundDrawdownRecoveryService

    try:
        return _clean_nan(FundDrawdownRecoveryService().get(wind_code))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(f"Get fund drawdown recovery error for {wind_code}: {exc}")
        raise HTTPException(status_code=500, detail="基金回撤修复分析暂时不可用")


@router.get("/{wind_code}/period-performance")
async def get_fund_period_performance(
    wind_code: str,
    years: int = Query(5, ge=1, le=8),
):
    """获取自然年度收益及严格同类年度排名。"""
    from services.fund_period_performance_service import FundPeriodPerformanceService

    try:
        return _clean_nan(FundPeriodPerformanceService().get(wind_code, years=years))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(f"Get fund period performance error for {wind_code}: {exc}")
        raise HTTPException(status_code=500, detail="基金年度业绩暂时不可用")


@router.post("/{wind_code}/manager-history/sync")
async def sync_fund_manager_history(wind_code: str):
    """从 Tushare 现场补齐一只基金的经理任职历史。"""
    from service_registry import get_strict_tushare_service
    from services.fund_manager_history_service import FundManagerHistoryService
    from services.fund_manager_tenure_sync_service import FundManagerTenureSyncService

    try:
        sync_result = FundManagerTenureSyncService(get_strict_tushare_service()).sync_fund_history(wind_code)
        if sync_result.get("status") != "synced":
            raise HTTPException(status_code=422, detail=sync_result.get("reason") or "经理任职数据同步失败")
        return _clean_nan({
            "sync": sync_result,
            "history": FundManagerHistoryService().get(wind_code),
        })
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Sync fund manager history error for {wind_code}: {exc}")
        raise HTTPException(status_code=500, detail="基金经理历史同步失败")


@router.get("/{wind_code}/bond-holdings")
async def get_fund_bond_holdings(
    wind_code: str,
    limit: int = Query(8, ge=1, le=20),
    refresh: bool = Query(False),
):
    """获取本地公开重仓债券明细及券种结构；refresh=true 时同步公开披露。"""
    from services.fund_bond_holding_service import FundBondHoldingService

    return _clean_nan(FundBondHoldingService().get(wind_code, limit=limit, refresh=refresh))


@router.get("/{wind_code}/fof-holdings")
async def get_fund_fof_holdings(
    wind_code: str,
    limit: int = Query(8, ge=1, le=20),
    refresh: bool = Query(False),
):
    """获取 FOF 公开底层基金持仓、集中度和评价证据门槛。"""
    from services.fund_fof_holding_service import FundFofHoldingService

    return _clean_nan(FundFofHoldingService().get(wind_code, limit=limit, refresh=refresh))


@router.get("/{wind_code}/bond-duration")
async def get_fund_bond_duration(
    wind_code: str,
    window_weeks: int = Query(104, ge=52, le=156),
):
    """读取最近一次债基净值回归久期；不会自动触发外部数据同步。"""
    from services.fund_bond_duration_service import FundBondDurationService

    try:
        return _clean_nan(FundBondDurationService().get(wind_code, window_weeks=window_weeks))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{wind_code}/bond-duration/calculate")
async def calculate_fund_bond_duration(
    wind_code: str,
    window_weeks: int = Query(104, ge=52, le=156),
    refresh_indices: bool = Query(False),
):
    """现场运行中债分期限指数 + Sharpe 收益率风格回归久期。"""
    from services.fund_bond_duration_service import FundBondDurationService

    try:
        return _clean_nan(FundBondDurationService().calculate(
            wind_code,
            window_weeks=window_weeks,
            refresh_indices=refresh_indices,
        ))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.error(f"Calculate bond duration error for {wind_code}: {exc}")
        raise HTTPException(status_code=500, detail="债基久期现场测算失败")


@router.get("/{wind_code}/bond-anomaly")
async def get_fund_bond_anomaly(
    wind_code: str,
    window_days: int = Query(252, ge=126, le=756),
):
    """按26日布林带和标准化同类收益门槛监控债基异常波动。"""
    from services.fund_bond_anomaly_service import FundBondAnomalyService

    try:
        return _clean_nan(FundBondAnomalyService().analyze(wind_code, window_days=window_days))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.error(f"Get bond anomaly monitor error for {wind_code}: {exc}")
        raise HTTPException(status_code=500, detail="债基异常监控暂时不可用")


@router.get("/{wind_code}/holding-changes")
async def get_fund_holding_changes(wind_code: str):
    """对比最近两期公开披露的前十大重仓股。"""
    from services.fund_holding_change_service import FundHoldingChangeService

    return _clean_nan(FundHoldingChangeService().analyze(wind_code))


@router.get("/{wind_code}/holder-structure")
async def get_fund_holder_structure(
    wind_code: str,
    limit: int = Query(20, ge=1, le=100),
    refresh: bool = Query(False),
):
    """获取基金半年报、年报披露的机构、个人和内部持有比例。"""
    from services.fund_holder_structure_service import FundHolderStructureService

    return _clean_nan(FundHolderStructureService().get(wind_code, limit=limit, refresh=refresh))


@router.get("/{wind_code}")
async def get_fund_detail(wind_code: str):
    """获取基金详细信息"""
    from services.cache_service import get_cache, CacheKey, TTL
    from services.data_quality_service import DataQualityService
    from services.professional_scoring_service import ProfessionalScoringService
    from service_registry import get_data_service, get_scoring_engine
    from repositories import get_fund_repo, get_factor_repo, get_manager_repo, get_metric_snapshot_repo, get_research_profile_repo

    cache = get_cache()
    cache_key = f"fund:detail:v10:{wind_code}"

    # 尝试从缓存获取
    cached = cache.get(cache_key)
    if cached is not None:
        logger.debug(f"[CACHE HIT] {cache_key}")
        return _clean_nan(cached)

    data_svc = get_data_service()
    scoring_engine = get_scoring_engine()
    fund_repo = get_fund_repo()
    factor_repo = get_factor_repo()
    manager_repo = get_manager_repo()
    research_profile_repo = get_research_profile_repo()
    metric_snapshot_repo = get_metric_snapshot_repo()
    data_quality_service = DataQualityService()
    professional_scoring_service = ProfessionalScoringService(data_quality_service=data_quality_service)

    try:
        db_fund = fund_repo.get_fund_by_identifier(wind_code)
        if db_fund:
            payload = _api_fund_from_row(db_fund, scoring_engine)
            _attach_manager_summaries([payload], manager_repo)
            scores = fund_repo.get_scores(payload.get("wind_code"))
            ai_reports = fund_repo.get_ai_reports(
                fund_id=str(payload.get("id")),
                wind_code=payload.get("wind_code"),
            )
            stored_profile = research_profile_repo.get_profile(payload.get("wind_code")) or {}
            manager_tenure_context = resolve_manager_tenure_context(
                db_fund,
                stored_profile,
                manager_repo.get_current_fund_tenure_context(payload.get("wind_code")),
            )
            payload["research_profile"] = enrich_profile_with_manager_tenure(
                stored_profile,
                manager_tenure_context,
            )
            try:
                payload["rolling_metrics"] = _rolling_metric_panel(
                    metric_snapshot_repo.get_latest_panel("fund", payload.get("wind_code"))
                )
            except Exception as exc:
                logger.warning(f"Rolling metrics unavailable for {payload.get('wind_code')}: {exc}")
                payload["rolling_metrics"] = {}
            try:
                payload["data_quality"] = data_quality_service.evaluate_fund(payload.get("wind_code"))
            except Exception as exc:
                logger.warning(f"Data quality unavailable for {payload.get('wind_code')}: {exc}")
                payload["data_quality"] = {"status": "unknown", "score": 0, "issues": ["数据质量评估暂不可用"]}
            try:
                payload["professional_scoring"] = professional_scoring_service.score_fund(payload.get("wind_code"))
                professional = payload["professional_scoring"] or {}
                payload["scoring"] = {
                    "overall_score": professional.get("overall_score"),
                    "overall_grade": professional.get("overall_grade"),
                    "status": professional.get("status"),
                    "calculation_method": professional.get("calculation_method"),
                }
            except Exception as exc:
                logger.warning(f"Professional scoring unavailable for {payload.get('wind_code')}: {exc}")
                payload["professional_scoring"] = None
            payload["scores"] = scores
            payload["ai_reports"] = ai_reports
            payload["trust"] = {
                "data_as_of": payload.get("nav_date") or payload.get("updated_at"),
                "synced_at": payload.get("updated_at"),
                "score_as_of": scores[0].get("scored_at") if scores else None,
                "score_count": len(scores),
                "report_count": len(ai_reports),
                "data_quality_status": payload["data_quality"].get("status", "unknown"),
                "data_quality_score": payload["data_quality"].get("score", 0),
                "data_quality_issues": payload["data_quality"].get("issues", []),
            }
            cache.set(cache_key, payload, TTL.MEDIUM)
            return _clean_nan(payload)

        info = data_svc.get_fund_info(wind_code)
        perf = data_svc.get_fund_performance(wind_code)
        risk = data_svc.get_fund_risk_metrics(wind_code)
        style = data_svc.get_fund_style(wind_code)
        scoring = scoring_engine.score_fund(perf, risk, style)

        # 获取数据库评分历史
        db_scores = []
        try:
            db_scores = fund_repo.get_scores(wind_code)
        except:
            pass

        # 获取因子暴露
        barra_exposure = {}
        try:
            exposures = factor_repo.get_exposures(wind_code)
            for e in exposures:
                barra_exposure[e["factor_name"]] = e["exposure"]
        except:
            pass

        result = _clean_nan({
            "fund": info, "performance": perf, "risk_metrics": risk,
            "style": style, "scoring": scoring, "scoring_history": db_scores,
            "barra_exposure": barra_exposure,
        })
        cache.set(cache_key, result, TTL.MEDIUM)
        return result
    except Exception as e:
        logger.error(f"Get fund detail error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{wind_code}/nav")
async def get_fund_nav(
    wind_code: str,
    start_date: str = Query("2024-01-01"),
    end_date: str = Query("2025-04-21"),
    freq: str = Query("daily", description="频率: daily/weekly/monthly"),
):
    """获取基金净值序列"""
    from services.cache_service import get_cache, CacheKey, TTL
    from repositories import get_nav_repo
    from service_registry import get_data_service

    cache = get_cache()
    cache_key = f"fund:nav:v2:{wind_code}:{start_date}:{end_date}:{freq}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    data = get_nav_repo().get_nav_series(wind_code, start_date, end_date)
    source = "local.postgres.fund_nav"
    if not data:
        data_svc = get_data_service()
        data = data_svc.get_fund_nav(wind_code, start_date, end_date)
        source = "market_data.fund_nav"

    if freq == "monthly":
        monthly = {}
        for d in data:
            month_key = d["date"][:7]
            if month_key not in monthly:
                monthly[month_key] = d["nav"]
        data = [{"date": k, "nav": v} for k, v in monthly.items()]

    result = {
        "wind_code": wind_code,
        "start_date": start_date,
        "end_date": end_date,
        "count": len(data),
        "source": source,
        "benchmark_count": sum(1 for item in data if item.get("benchmark_nav") is not None),
        "data": data,
    }
    cache.set(cache_key, result, TTL.LONG)
    return _clean_nan(result)


@router.get("/{wind_code}/holding-experience")
async def get_fund_holding_experience(wind_code: str):
    """回放历史买入日下的 1/3/6/12 个月持有体验。"""
    from services.fund_holding_experience_service import FundHoldingExperienceService

    return _clean_nan(FundHoldingExperienceService().analyze(wind_code))


@router.get("/{wind_code}/holdings")
async def get_fund_holdings(
    wind_code: str,
    quarter: Optional[str] = Query(None, description="季度, 如: 2024Q3, 2024Q4"),
    local_only: bool = Query(False, description="仅读取本地持仓库，不触发外部数据同步"),
):
    """获取基金持仓"""
    from service_registry import get_data_service
    from repositories import get_holding_repo

    data_svc = get_data_service()
    holding_repo = get_holding_repo()

    requested_quarters = [quarter] if quarter else _latest_holding_quarter_candidates()
    holdings: list[dict[str, Any]] = []
    latest_quarter = None
    source = None
    weight_evidence: dict[str, Any] = {}
    for candidate in requested_quarters:
        local_holdings = holding_repo.get_holdings(wind_code, candidate)
        if local_holdings:
            candidate_holdings = local_holdings
            source = "local.postgres.holdings"
        elif not local_only:
            candidate_holdings = data_svc.get_fund_holdings(wind_code, candidate)
            source = "tushare.fund_portfolio" if candidate_holdings else None
        else:
            candidate_holdings = []
        if not candidate_holdings:
            continue
        from services.fund_holding_weight_service import FundHoldingWeightService

        enrichment = FundHoldingWeightService().enrich(
            wind_code,
            candidate,
            candidate_holdings,
            refresh_allocation=not local_only,
        )
        holdings = enrichment["holdings"]
        industry_evidence = _enrich_holding_industry_evidence(holdings)
        weight_evidence = {
            key: value
            for key, value in enrichment.items()
            if key not in {"holdings", "allocation"}
        }
        latest_quarter = candidate
        try:
            holding_repo.upsert_holdings(wind_code, candidate, holdings)
        except Exception:
            pass
        break

    result = {
        "wind_code": wind_code,
        "requested_quarter": quarter,
        "latest_quarter": latest_quarter,
        "source": source,
        "holdings": holdings,
        "summary": _holding_summary(holdings),
        "weight_evidence": weight_evidence,
        "industry_evidence": industry_evidence if holdings else {
            "status": "not_applicable",
            "hong_kong_holding_count": 0,
            "matched_holding_count": 0,
        },
    }

    return _clean_nan(result)


@router.get("/{wind_code}/nav-chart")
async def get_nav_chart_data(
    wind_code: str,
    periods: str = Query("1y,3y", description="对比时间段"),
):
    """获取净值图表数据"""
    from services.cache_service import get_cache, CacheKey, TTL
    from service_registry import get_data_service

    cache = get_cache()
    cache_key = f"fund:nav-chart:{wind_code}:{periods}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    data_svc = get_data_service()
    period_map = {"1m": 30, "3m": 90, "6m": 180, "1y": 365, "3y": 1095, "5y": 1825}
    end_date = datetime.now().strftime("%Y-%m-%d")
    periods_list = [p.strip() for p in periods.split(",")]
    results = {}

    for period in periods_list:
        days = period_map.get(period, 365)
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        nav_data = data_svc.get_fund_nav(wind_code, start_date, end_date)
        if nav_data:
            base_nav = nav_data[0]["nav"]
            nav_data = [{**d, "nav_normalized": round(d["nav"] / base_nav, 6)} for d in nav_data]
        results[period] = nav_data

    result = {"wind_code": wind_code, "periods": results}
    cache.set(cache_key, result, TTL.MEDIUM)
    return _clean_nan(result)
