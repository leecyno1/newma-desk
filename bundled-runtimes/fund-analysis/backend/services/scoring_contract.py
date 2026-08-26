"""
评分输出契约

统一基金/经理评分输出结构，保证前端、报告和后续基金池工作流可以依赖稳定字段。
"""
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional


def grade_for_score(score: float) -> str:
    """将 0-100 分映射为等级。"""
    if score >= 90:
        return "S"
    if score >= 80:
        return "A"
    if score >= 70:
        return "B"
    if score >= 60:
        return "C"
    if score >= 50:
        return "D"
    return "E"


def build_scoring_output(
    target_type: str,
    target_id: str,
    total_score: float,
    dimensions: Dict[str, Any],
    metric_scores: Optional[Dict[str, Any]] = None,
    positive_factors: Optional[List[str]] = None,
    negative_factors: Optional[List[str]] = None,
    missing_data: Optional[List[str]] = None,
    source_snapshot_ids: Optional[List[str]] = None,
    as_of_date: Optional[Any] = None,
    calculation_method: str = "metric_snapshot",
) -> Dict[str, Any]:
    """构建稳定评分输出。"""
    missing = missing_data or []
    score = float(Decimal(str(total_score)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    return serialize_scoring_output({
        "target_type": target_type,
        "target_id": target_id,
        "overall_score": score,
        "overall_grade": grade_for_score(score),
        "dimension_scores": dimensions,
        "metric_scores": metric_scores or {},
        "positive_factors": positive_factors or [],
        "negative_factors": negative_factors or [],
        "missing_data": missing,
        "data_quality": {
            "missing_count": len(missing),
            "status": "partial" if missing else "complete",
        },
        "source_snapshot_ids": source_snapshot_ids or [],
        "as_of_date": as_of_date,
        "calculation_method": calculation_method,
        "scoring_time": datetime.utcnow().isoformat(),
    })


def serialize_scoring_output(value: Any) -> Any:
    """递归转换评分输出中的 Decimal、date 和 enum-like key。"""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key.value if hasattr(key, "value") else key): serialize_scoring_output(item) for key, item in value.items()}
    if isinstance(value, list):
        return [serialize_scoring_output(item) for item in value]
    if isinstance(value, tuple):
        return [serialize_scoring_output(item) for item in value]
    return value
