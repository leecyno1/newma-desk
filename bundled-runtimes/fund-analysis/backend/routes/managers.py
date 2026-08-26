"""
基金经理路由 - 经理搜索、详情、评分
"""
import math
from fastapi import APIRouter, HTTPException, Query
from typing import Optional
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/managers", tags=["基金经理"])


def _clean_nan(obj):
    """递归清理 NaN/Inf 值"""
    if isinstance(obj, dict):
        return {k: _clean_nan(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_clean_nan(item) for item in obj]
    elif isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
    return obj


def _get_services():
    from service_registry import get_data_service, get_scoring_engine, get_db
    return get_data_service(), get_scoring_engine(), get_db()


@router.get("/browser")
async def browse_managers(
    keyword: Optional[str] = Query(None, description="经理、公司或代表基金"),
    category: str = Query("all", description="标准基金大类"),
    evidence: str = Query("all", description="all / with_memo / with_metrics / research_ready"),
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
):
    """普通用户基金经理浏览器。"""
    from services.fund_manager_browser_service import FundManagerBrowserService

    try:
        return FundManagerBrowserService().browse(
            keyword=keyword,
            category=category,
            evidence=evidence,
            page=page,
            page_size=page_size,
        )
    except Exception as e:
        logger.error(f"Browse managers error: {e}")
        raise HTTPException(status_code=500, detail="基金经理浏览器暂时不可用")


@router.get("/")
async def list_managers(
    company: Optional[str] = Query(None, description="管理公司"),
    keyword: Optional[str] = Query(None, description="搜索关键词（经理名/ID）"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, le=100),
    sort_by: str = Query("score", description="排序: score/experience/aum"),
    sort_order: str = Query("desc"),
):
    """获取基金经理列表（优化版：跳过昂贵的 fund performance/risk/style 调用）"""
    from services.cache_service import get_cache, TTL

    data_svc, _, db = _get_services()
    cache = get_cache()

    try:
        # 尝试从缓存获取经理列表
        cache_key = f"manager:list:{company or ''}:{keyword or ''}:{page}:{page_size}:{sort_by}:{sort_order}"
        cached = cache.get(cache_key)
        if cached is not None:
            return _clean_nan(cached)

        # 直接从 Tushare 获取经理列表（使用新的缓存机制）
        managers_data = data_svc.get_manager_list(page=page, page_size=page_size, keyword=keyword, company=company)
        managers = managers_data.get("managers", [])
        total = managers_data.get("total", 0)

        # 如果有缓存的评分，获取平均评分
        for m in managers:
            manager_id = m.get("manager_id", "")
            funds = m.get("funds", [])[:3]

            cached_scores = []
            for fund in funds:
                code = fund.get("wind_code", "")
                if code:
                    score_cache = cache.get(f"fund:score:{code}")
                    if score_cache is not None:
                        cached_scores.append(score_cache)

            if cached_scores:
                avg_score = sum(cached_scores) / len(cached_scores)
                m["avg_score"] = round(avg_score, 2)
                m["score_evidence"] = "cached_fund_scores"
            else:
                m["avg_score"] = None
                m["score_evidence"] = "insufficient_evidence"

        # 排序
        sort_keys = {
            "score": lambda x: x.get("avg_score") if x.get("avg_score") is not None else -1,
            "experience": lambda x: x.get("tenure_years", 0),
            "aum": lambda x: x.get("fund_count", 0),
        }
        if sort_by in sort_keys:
            managers.sort(key=sort_keys[sort_by], reverse=(sort_order == "desc"))

        result = {"total": total, "page": page, "page_size": page_size, "managers": managers}
        cache.set(cache_key, result, TTL.SHORT)
        return _clean_nan(result)
    except Exception as e:
        logger.error(f"List managers error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/compare")
async def compare_managers(
    manager_id: list[str] = Query(..., description="重复传入 2-4 个规范经理 ID"),
    category: Optional[str] = Query(None, description="精确专业同类组"),
    product_code: Optional[list[str]] = Query(None, description="按经理顺序指定代表产品"),
):
    """同类、同区间基金经理对比。"""
    from services.fund_manager_comparison_service import FundManagerComparisonService

    try:
        return FundManagerComparisonService().build(
            manager_ids=manager_id,
            category=category,
            product_codes=product_code,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        logger.error(f"Compare managers error: {error}")
        raise HTTPException(status_code=500, detail="基金经理对比暂时不可用")


@router.get("/{manager_id}")
async def get_manager_detail(manager_id: str):
    """输出基金经理研究快照。"""
    try:
        from services.fund_manager_research_service import FundManagerResearchService
        return FundManagerResearchService().build(manager_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"经理不存在: {manager_id}")
    except Exception as e:
        logger.error(f"Get manager detail error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{manager_id}/career")
async def get_manager_career(
    manager_id: str,
    fund_code: Optional[str] = Query(None),
    tenure_start_date: Optional[str] = Query(None),
    period: str = Query("tenure"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    """读取经理在具体产品上的真实任职曲线。"""
    from services.fund_manager_career_service import FundManagerCareerService

    try:
        return FundManagerCareerService().build(
            manager_id=manager_id,
            fund_code=fund_code,
            tenure_start_date=tenure_start_date,
            period=period,
            start_date=start_date,
            end_date=end_date,
        )
    except ValueError as error:
        message = str(error)
        status = 404 if message.startswith("Manager not found") else 400
        raise HTTPException(status_code=status, detail=message)
    except Exception as error:
        logger.error(f"Get manager career error: {error}")
        raise HTTPException(status_code=500, detail="基金经理生涯曲线暂时不可用")


@router.get("/{manager_id}/reports")
async def get_manager_reports(
    manager_id: str,
    keyword: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
):
    """读取规范经理 ID 已确认的调研报告。"""
    from repositories.local_research_folder_repo import PostgresLocalResearchFolderRepo
    from repositories.manager_repo import ManagerRepo

    try:
        manager = ManagerRepo().get_manager(manager_id)
        if not manager:
            raise HTTPException(status_code=404, detail=f"经理不存在: {manager_id}")
        resolved_id = str(manager.get("wind_code") or manager_id)
        rows = PostgresLocalResearchFolderRepo().list_reports_for_manager_exact(resolved_id, limit=200)
        normalized_keyword = str(keyword or "").strip().lower()
        if normalized_keyword:
            rows = [row for row in rows if normalized_keyword in " ".join([
                str(row.get("title") or ""),
                str(row.get("summary") or ""),
                str(row.get("content") or ""),
                " ".join(str(tag) for tag in row.get("tags") or []),
            ]).lower()]
        start = (page - 1) * page_size
        reports = [{
            "id": str(row.get("id") or ""),
            "title": row.get("title"),
            "report_date": row.get("report_date"),
            "source": row.get("source"),
            "summary": str(row.get("summary") or "")[:200],
            "tags": row.get("tags") or [],
            "key_points": (row.get("key_points") or [])[:5],
            "local_relative_path": row.get("local_relative_path"),
            "review_status": row.get("review_status"),
        } for row in rows[start:start + page_size]]
        return {"total": len(rows), "page": page, "page_size": page_size, "reports": reports}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get manager reports error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{manager_id}/profile")
async def get_manager_profile(manager_id: str):
    """读取 PostgreSQL 中的正式经理画像。"""
    from repositories.manager_repo import ManagerRepo

    try:
        repo = ManagerRepo()
        manager = repo.get_manager(manager_id)
        if not manager:
            raise HTTPException(status_code=404, detail=f"经理不存在: {manager_id}")
        return repo.get_profile(str(manager.get("wind_code") or manager_id))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get manager profile error: {e}")
        raise HTTPException(status_code=500, detail="基金经理画像暂时不可用")


@router.post("/{manager_id}/profile/generate")
async def generate_manager_profile(manager_id: str):
    """按已确认纪要重建经理画像，不生成默认分数或模板化理念。"""
    from repositories.local_research_folder_repo import PostgresLocalResearchFolderRepo
    from repositories.manager_repo import ManagerRepo
    from services.research_memo_manager_profile_projection_service import ResearchMemoManagerProfileProjectionService

    try:
        manager_repo = ManagerRepo()
        manager = manager_repo.get_manager(manager_id)
        if not manager:
            raise HTTPException(status_code=404, detail=f"经理不存在: {manager_id}")
        resolved_id = str(manager.get("wind_code") or manager_id)
        report_repo = PostgresLocalResearchFolderRepo()
        result = ResearchMemoManagerProfileProjectionService(
            report_repo=report_repo,
            manager_repo=manager_repo,
        ).project_report({}, [resolved_id])
        profile = manager_repo.get_profile(resolved_id)
        return {
            "success": bool(profile),
            "projection": result,
            "profile": profile,
            "message": "画像仅使用规范经理 ID 已确认纪要中的原文证据。",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Generate manager profile error: {e}")
        raise HTTPException(status_code=500, detail=f"画像重建失败: {str(e)}")


@router.get("/{manager_id}/score")
async def get_manager_score(manager_id: str):
    """获取经理评分（兼容前端）"""
    data_svc, scoring_engine, db = _get_services()

    try:
        info = data_svc.get_manager_info(manager_id)
        funds = data_svc.get_manager_funds(manager_id)

        fund_scores = []
        for fund in funds[:5]:
            code = fund.get("wind_code", "")
            if not code:
                continue
            perf = data_svc.get_fund_performance(code)
            risk = data_svc.get_fund_risk_metrics(code)
            style = data_svc.get_fund_style(code)
            score = scoring_engine.score_fund(perf, risk, style)
            fund_scores.append({**fund, "scoring": score})

        if not fund_scores:
            return {
                "overall_score": None,
                "overall_grade": None,
                "scoring_source": "insufficient_evidence",
                "message": "缺少可验证的管理基金评分，不输出默认基金经理分。",
                "dimension_scores": {},
            }

        avg_perf = {"overall_score": sum(f["scoring"]["overall_score"] for f in fund_scores) / len(fund_scores)}
        manager_score = scoring_engine.score_manager(info, avg_perf, {}, [])

        return manager_score
    except Exception as e:
        logger.error(f"Get manager score error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{manager_id}/morningstar")
async def get_morningstar_rating(manager_id: str):
    """获取晨星风格评价 - 5星评级系统

    Returns:
        {
            "overall_score": 0-100,
            "star_rating": 1-5,
            "dimension_scores": {
                "return": 0-100,
                "risk_adjusted": 0-100,
                "stability": 0-100,
                "experience": 0-100
            },
            "grade": "S/A/B/C/D/E",
            "percentile_rank": 0-100
        }
    """
    from services.scoring_engine import ManagerScoringEngine
    from services.cache_service import get_cache, TTL

    cache = get_cache()
    cache_key = f"manager:morningstar:{manager_id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return _clean_nan(cached)

    data_svc, _, db = _get_services()

    try:
        # 获取经理基础信息
        info = data_svc.get_manager_info(manager_id)
        if not info:
            raise HTTPException(status_code=404, detail=f"经理不存在: {manager_id}")

        # 获取管理的所有基金业绩
        funds = data_svc.get_manager_funds(manager_id)
        funds_performance = []

        for fund in funds[:10]:  # 最多取10只基金
            code = fund.get("wind_code", "")
            if not code:
                continue

            try:
                perf = data_svc.get_fund_performance(code)
                if perf:
                    funds_performance.append(perf)
            except Exception as e:
                logger.warning(f"Failed to get performance for {code}: {e}")
                continue

        # 使用晨星评分引擎
        morningstar_engine = ManagerScoringEngine()
        rating = morningstar_engine.score_manager(info, funds_performance)

        # 添加同类排名（简化版：基于评分百分位）
        rating["percentile_rank"] = round(rating["overall_score"], 1)

        result = _clean_nan(rating)
        cache.set(cache_key, result, TTL.MEDIUM)
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get morningstar rating error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
