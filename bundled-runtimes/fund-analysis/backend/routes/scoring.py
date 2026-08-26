"""
评分路由 - 评分查询、打分、重算
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional
from datetime import datetime
import logging
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/scoring", tags=["评分系统"])


def _get_services():
    from service_registry import get_data_service, get_scoring_engine, get_db
    return get_data_service(), get_scoring_engine(), get_db()


def _score_to_grade(score: float) -> str:
    if score >= 90:
        return "A+"
    if score >= 80:
        return "A"
    if score >= 70:
        return "B"
    if score >= 60:
        return "C"
    return "D"


def _to_float(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ranked_fund_payload(row: dict, rank: int, dimension: Optional[str]) -> dict:
    perf = row.get("performance_data") or {}
    risk = row.get("risk_metrics") or {}
    screening_score = _to_float(row.get("screening_score"))
    return_1y = _to_float(perf.get("annualized_return_1y"))
    sharpe = _to_float(perf.get("sharpe_ratio"))
    max_drawdown = _to_float(
        risk.get("max_drawdown_1y")
        if risk.get("max_drawdown_1y") is not None
        else risk.get("max_drawdown")
        if risk.get("max_drawdown") is not None
        else perf.get("max_drawdown")
    )
    score = screening_score if screening_score is not None else 0
    return {
        "rank": rank,
        "wind_code": row.get("wind_code"),
        "name": row.get("name") or row.get("wind_code"),
        "type": row.get("type") or "",
        "overall_score": score,
        "grade": _score_to_grade(score),
        "return_1y": return_1y,
        "sharpe": sharpe,
        "max_drawdown": max_drawdown,
        "screening_score": screening_score,
        "scoring_source": "database_screening_score_v1",
        "ranking_basis": dimension or "screening_score",
        "data_source": "database",
        "source": "database",
    }


@router.get("/fund/{wind_code}")
async def get_fund_scoring(
    wind_code: str,
    use_metric_snapshots: bool = Query(True, description="优先使用 MetricSnapshot 权威指标评分"),
):
    """获取基金评分详情"""
    data_svc, scoring_engine, db = _get_services()

    try:
        scoring_source = "legacy_data_service"
        if use_metric_snapshots:
            try:
                scoring = scoring_engine.score_fund_from_metric_snapshots(wind_code)
                scoring_source = "metric_snapshot"
            except SQLAlchemyError as exc:
                logger.warning(f"Metric snapshot scoring unavailable for {wind_code}: {exc}")
                perf = data_svc.get_fund_performance(wind_code)
                risk = data_svc.get_fund_risk_metrics(wind_code)
                style = data_svc.get_fund_style(wind_code)
                scoring = scoring_engine.score_fund(perf, risk, style)
        else:
            perf = data_svc.get_fund_performance(wind_code)
            risk = data_svc.get_fund_risk_metrics(wind_code)
            style = data_svc.get_fund_style(wind_code)
            scoring = scoring_engine.score_fund(perf, risk, style)

        # 从数据库获取历史评分
        history = []
        if db is not None:
            try:
                cursor = db.scores.find({"target_type": "fund", "target_id": wind_code}).sort("scored_at", -1).limit(30)
                for doc in cursor:
                    history.append({
                        "dimension": doc.get("dimension"),
                        "score": doc.get("score"),
                        "scored_at": doc.get("scored_at"),
                    })
            except Exception:
                pass

        return {
            "target_type": "fund",
            "target_id": wind_code,
            "scoring_source": scoring_source,
            "scoring": scoring,
            "scoring_history": history,
            "dimensions": [
                {"name": "收益能力", "key": "return", "weight": 0.30, "score": scoring["dimension_scores"].get("return", {}).get("score", 0)},
                {"name": "风险控制", "key": "risk", "weight": 0.25, "score": scoring["dimension_scores"].get("risk", {}).get("score", 0)},
                {"name": "风险调整收益", "key": "risk_adjusted", "weight": 0.35, "score": scoring["dimension_scores"].get("risk_adjusted", {}).get("score", 0)},
                {"name": "风格稳定性", "key": "style", "weight": 0.10, "score": scoring["dimension_scores"].get("style", {}).get("score", 0)},
            ],
            "metric_details": scoring.get("metric_scores", {}),
        }
    except Exception as e:
        logger.error(f"Get fund scoring error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/fund/{wind_code}/professional")
async def get_fund_professional_scoring(wind_code: str):
    """获取专业评分：按基金类型、滚动窗口、任期切片和数据质量综合评分。"""
    try:
        from services.professional_scoring_service import ProfessionalScoringService

        scoring = ProfessionalScoringService().score_fund(wind_code)
        return {
            "target_type": "fund",
            "target_id": wind_code,
            "scoring_source": "professional_metric_snapshot_v1",
            "scoring": scoring,
        }
    except Exception as e:
        logger.error(f"Get professional scoring error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fund/{wind_code}/recalculate")
async def recalculate_fund_scoring(
    wind_code: str,
    save_to_db: bool = True,
    use_metric_snapshots: bool = Query(True, description="优先使用 MetricSnapshot 权威指标评分"),
):
    """重新计算基金评分并保存"""
    data_svc, scoring_engine, db = _get_services()

    try:
        scoring_source = "legacy_data_service"
        if use_metric_snapshots:
            try:
                scoring = scoring_engine.score_fund_from_metric_snapshots(wind_code)
                scoring_source = "metric_snapshot"
            except SQLAlchemyError as exc:
                logger.warning(f"Metric snapshot scoring unavailable for {wind_code}: {exc}")
                perf = data_svc.get_fund_performance(wind_code)
                risk = data_svc.get_fund_risk_metrics(wind_code)
                style = data_svc.get_fund_style(wind_code)
                scoring = scoring_engine.score_fund(perf, risk, style)
        else:
            perf = data_svc.get_fund_performance(wind_code)
            risk = data_svc.get_fund_risk_metrics(wind_code)
            style = data_svc.get_fund_style(wind_code)
            scoring = scoring_engine.score_fund(perf, risk, style)

        if save_to_db and db is not None:
            scored_at = datetime.utcnow()
            try:
                for dim_key, dim_data in scoring["dimension_scores"].items():
                    db.scores.insert_one({
                        "target_type": "fund",
                        "target_id": wind_code,
                        "dimension": dim_key,
                        "score": dim_data.get("score", 50),
                        "calculation_method": "quantitative",
                        "scored_at": scored_at,
                    })
            except Exception as db_err:
                logger.warning(f"Failed to save scoring to DB: {db_err}")

        return {
            "status": "success",
            "target_type": "fund",
            "target_id": wind_code,
            "scoring_source": scoring_source,
            "scoring": scoring,
            "saved": save_to_db,
        }
    except Exception as e:
        logger.error(f"Recalculate scoring error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/manager/{manager_id}")
async def get_manager_scoring(manager_id: str):
    """获取基金经理评分详情"""
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

        avg_perf = {
            "overall_score": sum(f["scoring"]["overall_score"] for f in fund_scores) / len(fund_scores)
            if fund_scores
            else None
        }
        manager_score = scoring_engine.score_manager(info, avg_perf, {}, [])

        return {
            "target_type": "manager",
            "target_id": manager_id,
            "manager": info,
            "scoring": manager_score,
            "fund_scores": fund_scores,
        }
    except Exception as e:
        logger.error(f"Get manager scoring error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch")
async def batch_score_funds(
    wind_codes: List[str],
    save_to_db: bool = True,
):
    """批量评分基金"""
    data_svc, scoring_engine, db = _get_services()

    results = []
    for code in wind_codes:
        try:
            perf = data_svc.get_fund_performance(code)
            risk = data_svc.get_fund_risk_metrics(code)
            style = data_svc.get_fund_style(code)
            scoring = scoring_engine.score_fund(perf, risk, style)
            results.append({**scoring, "wind_code": code})
        except Exception as e:
            logger.error(f"Batch score error for {code}: {e}")
            results.append({"wind_code": code, "error": str(e)})

    return {"total": len(wind_codes), "results": results}


@router.get("/leaderboard")
async def get_leaderboard(
    target_type: str = Query("fund", description="fund/manager"),
    dimension: Optional[str] = Query(None, description="评分维度"),
    limit: int = Query(20, ge=1, le=100),
):
    """排行榜"""
    if target_type != "fund":
        raise HTTPException(status_code=400, detail="当前排行榜仅支持基金研究范围内的 fund")

    try:
        from repositories import get_fund_repo

        dim_map = {
            "return": ("return", "desc"),
            "risk": ("risk", "asc"),
            "sharpe": ("sharpe", "desc"),
            "overall": ("screening_score", "desc"),
            "screening_score": ("screening_score", "desc"),
        }
        sort_by, sort_order = dim_map.get(dimension or "screening_score", ("screening_score", "desc"))
        list_result = get_fund_repo().list_funds(
            page=1,
            page_size=limit,
            sort_by=sort_by,
            sort_order=sort_order,
            tradable_only=True,
        )

        rankings = [
            _ranked_fund_payload(row, index + 1, dimension)
            for index, row in enumerate(list_result.get("funds", []))
        ]

        return {
            "rankings": rankings,
            "total": list_result.get("total", len(rankings)),
            "ranking_source": "database",
            "scoring_source": "database_screening_score_v1",
            "data_source": "database",
            "ranking_basis": dimension or "screening_score",
        }
    except Exception as e:
        logger.error(f"Leaderboard error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/rules")
async def get_scoring_rules():
    """获取评分规则说明"""
    from service_registry import get_scoring_engine
    scoring_engine = get_scoring_engine()
    rules = scoring_engine.get_scoring_rules()
    return {
        "rules": [
            {
                "dimension": r.dimension.value,
                "metric_name": r.metric_name,
                "min_val": r.min_val,
                "max_val": r.max_val,
                "weight": r.weight,
                "higher_is_better": r.higher_is_better,
            }
            for r in rules
        ],
        "dimension_weights": {
            "return": 0.30,
            "risk": 0.25,
            "risk_adjusted": 0.35,
            "style": 0.10,
        },
    }
