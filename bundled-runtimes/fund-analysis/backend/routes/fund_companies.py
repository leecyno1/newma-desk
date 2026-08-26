"""基金公司浏览器路由。"""

from fastapi import APIRouter, HTTPException, Query

from services.fund_company_service import FundCompanyService


router = APIRouter(prefix="/api/fund-companies", tags=["基金公司"])


@router.get("")
async def list_fund_companies(
    keyword: str = Query(""),
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    sort_by: str = Query("fund_count"),
):
    return FundCompanyService().list_companies(
        keyword=keyword,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
    )


@router.get("/{company}")
async def get_fund_company(company: str):
    try:
        return FundCompanyService().get_company(company)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
