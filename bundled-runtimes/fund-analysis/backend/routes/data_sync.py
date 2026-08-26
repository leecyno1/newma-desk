"""
数据同步路由 - 批量从 Tushare 拉取数据并持久化到 PostgreSQL
支持增量同步和全量同步
"""
import logging
from datetime import datetime, timedelta, UTC
from typing import Optional, Any

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

from services.tushare_service import TushareDataService
from services.cache_service import (
    get_cache, CacheKey, TTL, invalidate_fund_cache,
    invalidate_manager_cache, batch_cache_set, batch_cache_get,
)
from services.manager_tenure_metric_service import ManagerTenureMetricService
from services.fund_classification_ingestion_service import FundClassificationIngestionService
from services.fund_nav_evidence_service import FundNavDataEnrichmentService
from services.rolling_metric_service import RollingMetricService
from repositories import (
    get_fund_repo, get_manager_repo, get_holding_repo, get_nav_repo, get_research_profile_repo,
    get_fund_classification_repo,
)
from service_registry import get_strict_tushare_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/data-sync", tags=["数据同步"])

# 最长评价窗口为 3 年（756 个交易日）。按 4 个自然年抓取，给节假日和停牌留出余量，
# 避免只同步近一年后却生成缺少历史基准的 3 年指标。
ROLLING_NAV_HISTORY_DAYS = 365 * 4


# ─────────────────────────────────────────────
# 请求/响应模型
# ─────────────────────────────────────────────


class SyncFundRequest(BaseModel):
    """同步基金请求"""
    wind_code: str
    include_performance: bool = True
    include_holdings: bool = False
    include_nav: bool = True
    include_risk: bool = True


class SyncManagerRequest(BaseModel):
    """同步经理请求"""
    manager_id: str
    include_profile: bool = True
    include_funds: bool = True


class SyncBatchRequest(BaseModel):
    """批量同步请求"""
    fund_codes: list[str] = []
    manager_ids: list[str] = []
    sync_type: str = "incremental"  # "incremental" | "full"
    # 增量同步时的时间范围
    date_from: Optional[str] = None
    date_to: Optional[str] = None


class SyncProgress(BaseModel):
    """同步进度"""
    task_id: str
    status: str  # "running" | "completed" | "failed"
    progress: float  # 0.0 - 1.0
    total: int
    processed: int
    failed: int
    errors: list[str] = []
    started_at: str
    finished_at: Optional[str] = None


# 全局同步任务状态
_sync_tasks: dict[str, dict] = {}


def _years_since(date_text: Optional[str]) -> float:
    if not date_text:
        return 0.0
    try:
        return round(max(0, (datetime.now(UTC).date() - datetime.fromisoformat(date_text).date()).days) / 365.25, 2)
    except ValueError:
        return 0.0


def _quarter_before(quarter: str) -> str:
    year = int(quarter[:4])
    number = int(quarter[-1])
    return f"{year - 1}Q4" if number == 1 else f"{year}Q{number - 1}"


def _recent_completed_quarters(limit: int = 4, now: Optional[datetime] = None) -> list[str]:
    reference = now or datetime.now()
    current = f"{reference.year}Q{(reference.month - 1) // 3 + 1}"
    quarter = _quarter_before(current)
    result = []
    for _ in range(max(0, limit)):
        result.append(quarter)
        quarter = _quarter_before(quarter)
    return result


def _sync_fund_managers(data_svc: Any, wind_code: str) -> tuple[list[str], list[str], Optional[str]]:
    """同步基金对应的经理任职关系，返回现任经理 ID 和非致命告警。"""
    manager_repo = get_manager_repo()
    warnings = []

    try:
        manager_rows = data_svc.get_fund_managers(wind_code)
    except Exception as e:
        logger.warning(f"[SYNC] Fund manager relation unavailable for {wind_code}: {e}")
        return [], [f"[{wind_code}] 基金经理关系获取失败: {e}"], None

    if not manager_rows:
        return [], [f"[{wind_code}] Tushare 未返回基金经理关系"], None

    active_manager_ids = []
    active_begin_dates = []
    for manager in manager_rows:
        manager_id = manager.get("manager_id", "")
        if not manager_id:
            continue

        is_current_manager = bool(manager.get("is_current_manager"))
        if is_current_manager and manager_id not in active_manager_ids:
            active_manager_ids.append(manager_id)
            if manager.get("begin_date"):
                active_begin_dates.append(str(manager.get("begin_date"))[:10])

        ok = manager_repo.upsert_manager(
            manager_id,
            {
                "name": manager.get("name") or manager_id.split("|")[0],
                "company": "",
                "education": manager.get("education") or "",
                "experience_years": _years_since(manager.get("begin_date")),
                "management_years": _years_since(manager.get("begin_date")),
                "current_funds": [wind_code] if is_current_manager else [],
                "historical_performance": {
                    "fund_code": wind_code,
                    "fund_tenure_start": manager.get("begin_date"),
                    "fund_tenure_end": manager.get("end_date"),
                    "is_current_manager": is_current_manager,
                },
                "raw_data": {
                    "source": "tushare.fund_manager",
                    "synced_at": datetime.now(UTC).isoformat(),
                    "fund_code": wind_code,
                    "manager_id": manager_id,
                    "begin_date": manager.get("begin_date"),
                    "end_date": manager.get("end_date"),
                    "fund_manager_row": manager.get("raw_data") or manager,
                },
            },
        )
        if not ok:
            warnings.append(f"[{wind_code}] 经理 {manager_id} 写入 PostgreSQL 失败")
        else:
            invalidate_manager_cache(manager_id)

    if manager_rows and not active_manager_ids:
        warnings.append(f"[{wind_code}] 有历史经理记录，但未识别出现任经理")

    manager_tenure_start = max(active_begin_dates) if active_begin_dates else None
    return active_manager_ids, warnings, manager_tenure_start


def _upsert_research_profile_from_sync(wind_code: str, fund_payload: dict, manager_tenure_start: Optional[str]) -> None:
    if not manager_tenure_start:
        return
    profile_repo = get_research_profile_repo()
    classification = get_fund_classification_repo().get_classification_context(wind_code) or {}
    benchmark = classification.get("benchmark_mapping") or {}
    profile_repo.upsert_manager_tenure(
        wind_code=wind_code,
        manager_tenure_start=manager_tenure_start,
        primary_benchmark=str(benchmark.get("benchmark_code") or benchmark.get("benchmark_name") or ""),
        peer_group=str(classification.get("peer_group_name") or classification.get("peer_group_key") or ""),
        evidence={
            "manager_tenure": {
                "source": "tushare.fund_manager",
                "current_team_latest_begin_date": manager_tenure_start,
                "synced_at": datetime.now(UTC).isoformat(),
            }
        },
    )


# ─────────────────────────────────────────────
# 同步服务
# ─────────────────────────────────────────────


def _sync_fund(
    wind_code: str,
    include_performance: bool = True,
    include_holdings: bool = False,
    include_nav: bool = True,
    include_risk: bool = True,
) -> dict:
    """
    同步单个基金数据到 PostgreSQL
    整合数据服务 + Repository 层
    """
    errors = []
    warnings = []
    rolling_metrics = None
    tenure_metrics = None
    classification_ingestion = None
    holdings_sync = []
    asset_allocation_sync = None
    holder_structure_sync = None
    nav_enrichment = {
        "benchmark_data_status": "not_checked",
        "benchmark_observations": 0,
        "money_market_metric_status": "not_checked",
    }
    fund_repo = get_fund_repo()
    holding_repo = get_holding_repo()
    nav_repo = get_nav_repo()

    # Step 1: 基金基本信息
    try:
        data_svc = get_strict_tushare_service()
        fund_info = data_svc.get_fund_info(wind_code)

        if not fund_info or not fund_info.get("name"):
            errors.append(f"[{wind_code}] 基金基本信息获取失败或为空")
            return {"success": False, "errors": errors}

        fund_payload = fund_info.copy()
        fund_payload["raw_data"] = {
            "source": "tushare",
            "synced_at": datetime.now(UTC).isoformat(),
            "info": fund_info,
        }
        try:
            ingestion_service = FundClassificationIngestionService()
            ingestion_plan = ingestion_service.build_plan([{**fund_info, "wind_code": wind_code}])
            if ingestion_plan.get("groups"):
                classification_ingestion = ingestion_service.apply_plan(ingestion_plan)
            else:
                classification_ingestion = {
                    "applied_groups": 0,
                    "skipped": ingestion_plan.get("skipped") or [],
                }
        except Exception as ingestion_error:
            warnings.append(f"[{wind_code}] 标准化分类写入失败: {ingestion_error}")
    except Exception as e:
        errors.append(f"[{wind_code}] 基金基本信息错误: {e}")
        logger.error(f"Sync fund basic error for {wind_code}: {e}")
        return {"success": False, "errors": errors}

    # Step 2: 业绩数据
    if include_performance:
        try:
            perf = data_svc.get_fund_performance(wind_code)
            if perf:
                fund_payload["performance_data"] = perf
        except Exception as e:
            errors.append(f"[{wind_code}] 业绩数据错误: {e}")

    # Step 3: 净值序列（覆盖最长滚动评价窗口）
    if include_nav:
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=ROLLING_NAV_HISTORY_DAYS)
            nav_data = data_svc.get_fund_nav(
                wind_code,
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"),
            )
            if nav_data:
                nav_enrichment = FundNavDataEnrichmentService(data_svc).enrich(
                    wind_code=wind_code,
                    fund_type=fund_info.get("type"),
                    nav_series=nav_data,
                    start_date=start_date.strftime("%Y-%m-%d"),
                    end_date=end_date.strftime("%Y-%m-%d"),
                )
                nav_data = nav_enrichment["nav_series"]
                if nav_enrichment.get("nav_data_status") != "valid":
                    raise ValueError(f"净值质量门禁未通过：{nav_enrichment.get('nav_validation')}")
                performance_data = fund_payload.get("performance_data") or {}
                performance_data.update(nav_enrichment.get("performance_facts") or {})
                fund_payload["performance_data"] = performance_data
                nav_repo.upsert_nav_series(wind_code, nav_data, replace_range=True)
        except Exception as e:
            errors.append(f"[{wind_code}] 净值数据错误: {e}")

    # Step 4: 持仓数据（最近 4 个季度）
    if include_holdings:
        try:
            for quarter in _recent_completed_quarters(4):
                holdings_list = data_svc.get_fund_holdings(wind_code, quarter=quarter)
                if not holdings_list:
                    continue
                if holding_repo.upsert_holdings(wind_code, quarter, holdings_list):
                    holdings_sync.append({"quarter": quarter, "holding_count": len(holdings_list)})
            if not holdings_sync:
                warnings.append(f"[{wind_code}] 最近 4 个完整季度均未取得持仓")
        except Exception as e:
            errors.append(f"[{wind_code}] 持仓数据错误: {e}")

    # Step 5: 风险指标
    if include_risk:
        try:
            risk = data_svc.get_fund_risk_metrics(wind_code)
            if risk:
                fund_payload["risk_metrics"] = risk
        except Exception as e:
            errors.append(f"[{wind_code}] 风险指标错误: {e}")

    # Step 6: 基金经理任职关系
    manager_ids, manager_warnings, manager_tenure_start = _sync_fund_managers(data_svc, wind_code)
    if manager_ids:
        fund_payload["manager_ids"] = manager_ids
    warnings.extend(manager_warnings)

    raw_data = fund_payload.get("raw_data") or {}
    if nav_enrichment.get("benchmark_data_status") != "not_checked":
        raw_data["nav_evidence"] = {
            "benchmark_code": nav_enrichment.get("benchmark_code"),
            "benchmark_source": nav_enrichment.get("benchmark_source"),
            "benchmark_data_status": nav_enrichment.get("benchmark_data_status"),
            "benchmark_data_kind": nav_enrichment.get("benchmark_data_kind"),
            "benchmark_observations": nav_enrichment.get("benchmark_observations", 0),
            "benchmark_nav_observations": nav_enrichment.get("benchmark_nav_observations", 0),
            "benchmark_rate_observations": nav_enrichment.get("benchmark_rate_observations", 0),
            "money_market_metric_status": nav_enrichment.get("money_market_metric_status"),
            "nav_data_status": nav_enrichment.get("nav_data_status"),
            "nav_validation": nav_enrichment.get("nav_validation"),
        }
    raw_data["manager_sync"] = {
        "source": "tushare.fund_manager",
        "synced_at": datetime.now(UTC).isoformat(),
        "manager_ids": manager_ids,
        "warnings": manager_warnings,
    }
    fund_payload["raw_data"] = raw_data

    if not fund_repo.upsert_fund(wind_code, fund_payload):
        errors.append(f"[{wind_code}] 写入 PostgreSQL 失败")
    else:
        try:
            from services.fund_asset_allocation_service import FundAssetAllocationService

            asset_allocation_sync = FundAssetAllocationService().sync(wind_code)
            if asset_allocation_sync.get("status") != "synced":
                warnings.append(f"[{wind_code}] 资产配置同步失败: {'；'.join(asset_allocation_sync.get('missing_items') or [])}")
        except Exception as e:
            warnings.append(f"[{wind_code}] 资产配置同步失败: {e}")
        try:
            from services.fund_holder_structure_service import FundHolderStructureService

            holder_structure_sync = FundHolderStructureService().sync(wind_code)
            if holder_structure_sync.get("status") != "synced":
                warnings.append(f"[{wind_code}] 持有人结构同步失败: {'；'.join(holder_structure_sync.get('missing_items') or [])}")
        except Exception as e:
            warnings.append(f"[{wind_code}] 持有人结构同步失败: {e}")
        try:
            _upsert_research_profile_from_sync(wind_code, fund_payload, manager_tenure_start)
        except Exception as e:
            warnings.append(f"[{wind_code}] 研究画像/经理任期起点维护失败: {e}")
        if include_nav:
            try:
                rolling_metrics = RollingMetricService().calculate_and_save_for_fund(
                    wind_code,
                    benchmark_code=nav_enrichment.get("benchmark_code"),
                )
                if rolling_metrics.get("saved", 0) == 0:
                    warnings.append(f"[{wind_code}] 净值已同步，但滚动指标样本不足")
            except Exception as e:
                warnings.append(f"[{wind_code}] 滚动指标计算失败: {e}")
            try:
                tenure_metrics = ManagerTenureMetricService().calculate_and_save_for_fund(wind_code)
                if tenure_metrics.get("saved", 0) == 0:
                    warnings.append(f"[{wind_code}] 经理任期切片指标未生成: {tenure_metrics.get('reason', 'unknown')}")
            except Exception as e:
                warnings.append(f"[{wind_code}] 经理任期切片指标计算失败: {e}")
        invalidate_fund_cache(wind_code)
        logger.info(f"[SYNC] Fund persisted: {wind_code} - {fund_payload.get('name')}")

    return {
        "success": len(errors) == 0,
        "wind_code": wind_code,
        "manager_ids": manager_ids,
        "manager_count": len(manager_ids),
        "manager_tenure_start": manager_tenure_start,
        "classification_ingestion": classification_ingestion,
        "holdings_sync": holdings_sync,
        "asset_allocation_sync": asset_allocation_sync,
        "holder_structure_sync": holder_structure_sync,
        "rolling_metrics": rolling_metrics,
        "tenure_metrics": tenure_metrics,
        "errors": errors,
        "warnings": warnings,
    }


def _sync_manager(
    manager_id: str,
    include_profile: bool = True,
    include_funds: bool = True,
) -> dict:
    """同步单个基金经理数据"""
    errors = []
    manager_repo = get_manager_repo()

    try:
        data_svc = get_strict_tushare_service()
        manager_info = data_svc.get_manager_info(manager_id)

        if not manager_info or not manager_info.get("name"):
            errors.append(f"[{manager_id}] 经理基本信息获取失败")
            return {"success": False, "errors": errors}

        manager_repo.upsert_manager(manager_id, manager_info)
        invalidate_manager_cache(manager_id)
        logger.info(f"[SYNC] Manager: {manager_id} - {manager_info.get('name')}")

        if include_funds:
            funds = manager_info.get("current_funds", [])
            if funds:
                fund_repo = get_fund_repo()
                for fund in funds:
                    fund_code = fund if isinstance(fund, str) else fund.get("wind_code", "")
                    if fund_code:
                        fund_data = data_svc.get_fund_info(fund_code)
                        if fund_data:
                            fund_repo.upsert_fund(fund_code, fund_data)

    except Exception as e:
        errors.append(f"[{manager_id}] 经理同步错误: {e}")
        logger.error(f"Sync manager error for {manager_id}: {e}")

    return {
        "success": len(errors) == 0,
        "manager_id": manager_id,
        "errors": errors,
    }


def _run_batch_sync(task_id: str, params: dict):
    """后台批量同步任务"""
    sync_tasks = _sync_tasks
    task = sync_tasks.get(task_id)
    if not task:
        return

    task["status"] = "running"
    task["started_at"] = datetime.now().isoformat()

    fund_codes = params.get("fund_codes", [])
    manager_ids = params.get("manager_ids", [])
    sync_type = params.get("sync_type", "incremental")

    all_items = fund_codes + manager_ids
    total = len(all_items)
    task["total"] = total

    results = {"succeeded": [], "failed": []}

    for i, item in enumerate(all_items):
        try:
            if item in fund_codes:
                result = _sync_fund(item)
            else:
                result = _sync_manager(item)

            if result.get("success"):
                results["succeeded"].append(item)
            else:
                results["failed"].append(item)
                task["errors"].extend(result.get("errors", []))
        except Exception as e:
            results["failed"].append(item)
            task["errors"].append(f"[{item}] {e}")

        task["processed"] = i + 1
        task["progress"] = round((i + 1) / total, 4) if total > 0 else 1.0

    task["status"] = "completed"
    task["finished_at"] = datetime.now().isoformat()
    task["results"] = results

    logger.info(f"[SYNC] Batch completed: {task_id}, success={len(results['succeeded'])}, failed={len(results['failed'])}")


# ─────────────────────────────────────────────
# API 端点
# ─────────────────────────────────────────────


@router.get("/funds/{wind_code}")
def sync_single_fund(wind_code: str):
    """手动同步单个基金数据"""
    result = _sync_fund(wind_code)
    if not result["success"]:
        raise HTTPException(422, detail=result["errors"])
    return {
        "message": f"基金 {wind_code} 同步完成",
        "manager_ids": result.get("manager_ids", []),
        "manager_count": result.get("manager_count", 0),
        "manager_tenure_start": result.get("manager_tenure_start"),
        "asset_allocation_sync": result.get("asset_allocation_sync"),
        "holder_structure_sync": result.get("holder_structure_sync"),
        "rolling_metrics": result.get("rolling_metrics"),
        "tenure_metrics": result.get("tenure_metrics"),
        "errors": result["errors"],
        "warnings": result.get("warnings", []),
    }


@router.get("/managers/{manager_id}")
def sync_single_manager(manager_id: str):
    """手动同步单个基金经理数据"""
    result = _sync_manager(manager_id)
    if not result["success"]:
        raise HTTPException(422, detail=result["errors"])
    return {"message": f"经理 {manager_id} 同步完成", "errors": result["errors"]}


@router.post("/batch")
def sync_batch(
    request: SyncBatchRequest,
    background_tasks: BackgroundTasks,
):
    """
    批量同步基金和经理数据
    使用 BackgroundTasks 在后台运行
    """
    if not request.fund_codes and not request.manager_ids:
        raise HTTPException(400, "fund_codes 和 manager_ids 不能同时为空")

    task_id = f"sync_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    task_info = {
        "task_id": task_id,
        "status": "pending",
        "progress": 0.0,
        "total": len(request.fund_codes) + len(request.manager_ids),
        "processed": 0,
        "failed": 0,
        "errors": [],
        "started_at": None,
        "finished_at": None,
        "results": None,
    }
    _sync_tasks[task_id] = task_info

    params = request.model_dump()
    background_tasks.add_task(_run_batch_sync, task_id, params)

    return {
        "message": "批量同步任务已提交",
        "task_id": task_id,
        "total_items": task_info["total"],
    }


@router.get("/batch/{task_id}")
def get_sync_progress(task_id: str):
    """查询批量同步进度"""
    task = _sync_tasks.get(task_id)
    if not task:
        raise HTTPException(404, "任务不存在或已过期")
    return SyncProgress(**task)


@router.delete("/batch/{task_id}")
def cancel_sync_task(task_id: str):
    """取消批量同步任务（仅标记，实际取消依赖任务内部检查）"""
    task = _sync_tasks.get(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    if task["status"] in ("completed", "failed"):
        raise HTTPException(400, "任务已完成，无法取消")
    task["status"] = "cancelled"
    return {"message": "任务已标记取消"}


@router.post("/funds/full")
def sync_all_funds_batch(fund_type: str = None):
    """
    全量同步基金数据（自动获取列表后批量同步）
    警告: 大批量同步可能耗时较长
    """
    data_svc = get_strict_tushare_service()
    try:
        result = data_svc.get_fund_list(fund_type=fund_type, page=1, page_size=1000)
        fund_list = result.get("items") or result.get("list") or []
        total = len(fund_list)

        if not fund_list:
            raise HTTPException(404, "未找到基金数据")

        task_id = f"sync_full_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        task_info = {
            "task_id": task_id,
            "status": "pending",
            "progress": 0.0,
            "total": total,
            "processed": 0,
            "failed": 0,
            "errors": [],
            "started_at": None,
            "finished_at": None,
        }
        _sync_tasks[task_id] = task_info

        return {
            "message": f"全量同步已提交，共 {total} 个基金",
            "task_id": task_id,
            "total": total,
        }
    except Exception as e:
        logger.error(f"sync_all_funds_batch error: {e}")
        raise HTTPException(500, str(e))


@router.get("/stats")
def sync_stats():
    """获取同步统计信息"""
    cache = get_cache()
    return {
        "cache_stats": cache.stats() if hasattr(cache, "stats") else {},
        "active_tasks": [
            t for t in _sync_tasks.values()
            if t["status"] in ("pending", "running")
        ],
        "completed_tasks_count": sum(
            1 for t in _sync_tasks.values() if t["status"] == "completed"
        ),
    }
