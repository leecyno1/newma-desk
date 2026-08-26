"""
证据型研究备忘录路由
"""
from fastapi import APIRouter, HTTPException
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/research-memos", tags=["证据研究备忘录"])


@router.get("/fund/{wind_code}")
async def get_fund_research_memo(wind_code: str):
    """生成基金研究备忘录。"""
    try:
        from services.research_memo_service import ResearchMemoService

        return ResearchMemoService().build_fund_memo(wind_code)
    except Exception as exc:
        logger.error(f"Build fund research memo error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))
