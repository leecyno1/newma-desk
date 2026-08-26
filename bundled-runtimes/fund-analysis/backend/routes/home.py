"""普通用户选基首页 API。"""

from fastapi import APIRouter

from services.fund_home_service import FundHomeService


router = APIRouter(prefix="/api/home", tags=["选基首页"])


@router.get("")
async def get_home():
    return FundHomeService().build()
