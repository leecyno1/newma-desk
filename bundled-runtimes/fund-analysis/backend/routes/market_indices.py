"""市场指数成分与权重快照。"""

from datetime import date
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/api/market-indices", tags=["市场指数"])


def _get_repo():
    from repositories import get_market_index_constituent_repo

    return get_market_index_constituent_repo()


@router.get("/{index_code}/constituents")
def get_index_constituents(
    index_code: str,
    as_of_date: Optional[str] = Query(None, description="只读取该日期及以前的最近快照，格式 YYYY-MM-DD"),
    industry: Optional[str] = Query(None, description="按行业筛选"),
) -> Dict[str, Any]:
    """读取可审计的指数点时成分；不会用未来快照倒推历史。"""
    normalized_code = str(index_code or "").strip().upper()
    snapshot = _get_repo().get_latest_on_or_before(
        normalized_code,
        as_of_date or date.today().isoformat(),
    )
    if not snapshot:
        raise HTTPException(status_code=404, detail=f"未找到 {normalized_code} 在指定日期前的成分快照")

    all_rows = list(snapshot.get("constituents") or [])
    rows = [row for row in all_rows if not industry or str(row.get("industry") or "") == industry]
    published_weight = sum(float(row.get("weight") or 0) for row in all_rows)
    weighted_count = sum(1 for row in all_rows if row.get("weight") is not None)
    industries: Dict[str, Dict[str, Any]] = {}
    for row in all_rows:
        name = str(row.get("industry") or "行业待补")
        bucket = industries.setdefault(name, {"industry": name, "constituent_count": 0, "published_weight": 0.0})
        bucket["constituent_count"] += 1
        bucket["published_weight"] += float(row.get("weight") or 0)

    index_names = {
        "HSI": "恒生指数",
        "HSCI-INDUSTRY": "恒生行业分类",
    }
    evidence_urls = sorted({
        str(row.get("evidence_url"))
        for row in all_rows
        if row.get("evidence_url")
    })
    return {
        "status": "available",
        "index_code": normalized_code,
        "index_name": index_names.get(normalized_code, normalized_code),
        "requested_as_of_date": as_of_date,
        "snapshot_as_of_date": snapshot.get("as_of_date"),
        "point_in_time_rule": "snapshot_as_of_date <= requested_as_of_date",
        "source": snapshot.get("source"),
        "evidence_urls": evidence_urls,
        "coverage": {
            "constituent_count": len(all_rows),
            "weighted_constituent_count": weighted_count,
            "published_weight": round(published_weight, 8),
            "industry_count": len(industries),
        },
        "industry_breakdown": sorted(
            (
                {
                    **bucket,
                    "published_weight": round(float(bucket["published_weight"]), 8),
                }
                for bucket in industries.values()
            ),
            key=lambda item: (-float(item["published_weight"]), item["industry"]),
        ),
        "constituents": rows,
    }
