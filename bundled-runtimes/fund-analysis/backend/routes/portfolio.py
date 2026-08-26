"""基金组合构建 (Portfolio Construction) API — 研究型组合管理。

边界：组合为研究工具，不执行交易、不做适当性判断、不生成销售规则。
"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from services.portfolio_service import PortfolioService

router = APIRouter(prefix="/api/portfolios", tags=["基金组合"])


def _svc() -> PortfolioService:
    return PortfolioService()


class PortfolioTargetInput(BaseModel):
    peer_group_key: str = Field(min_length=1, max_length=120)
    peer_group_name: Optional[str] = None
    target_weight: float = Field(gt=0, le=1)
    note: Optional[str] = None


class PortfolioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    objective: Optional[str] = None
    targets: List[PortfolioTargetInput] = Field(default_factory=list)


class PortfolioUpdate(BaseModel):
    name: Optional[str] = None
    objective: Optional[str] = None
    status: Optional[str] = None
    targets: Optional[List[PortfolioTargetInput]] = None


class HoldingAdd(BaseModel):
    wind_code: str = Field(min_length=1, max_length=24)
    note: Optional[str] = None


class WeightItem(BaseModel):
    wind_code: str = Field(min_length=1, max_length=24)
    weight: float = Field(gt=0, le=1)


class WeightsSet(BaseModel):
    items: List[WeightItem] = Field(min_length=1)
    source: str = Field(default="custom")


class TradeListRequest(BaseModel):
    current_positions: List[Dict[str, Any]] = Field(default_factory=list)
    total_amount: Optional[float] = None


class TargetsUpdateRequest(BaseModel):
    targets: List[Dict[str, Any]] = Field(default_factory=list)


@router.get("")
def list_portfolios(status: Optional[str] = Query(None)) -> Dict[str, Any]:
    try:
        return _svc().list_portfolios(status=status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("")
def create_portfolio(payload: PortfolioCreate) -> Dict[str, Any]:
    try:
        return _svc().create_portfolio(
            name=payload.name,
            objective=payload.objective,
            targets=[item.dict() for item in payload.targets] or None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/admission")
def check_admission(wind_code: str = Query(..., min_length=1, max_length=24)) -> Dict[str, Any]:
    return _svc().check_admission(wind_code)


@router.get("/{portfolio_id}")
def get_portfolio(portfolio_id: str) -> Dict[str, Any]:
    try:
        return _svc().get_portfolio(portfolio_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/{portfolio_id}")
def update_portfolio(portfolio_id: str, payload: PortfolioUpdate) -> Dict[str, Any]:
    try:
        return _svc().update_portfolio(
            portfolio_id,
            name=payload.name,
            objective=payload.objective,
            status=payload.status,
            targets=[item.dict() for item in payload.targets] if payload.targets is not None else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{portfolio_id}/holdings")
def add_holding(portfolio_id: str, payload: HoldingAdd) -> Dict[str, Any]:
    try:
        return _svc().add_holding(portfolio_id, payload.wind_code, payload.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{portfolio_id}/holdings/{wind_code}")
def remove_holding(portfolio_id: str, wind_code: str) -> Dict[str, Any]:
    try:
        return _svc().remove_holding(portfolio_id, wind_code)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{portfolio_id}/weights")
def set_weights(portfolio_id: str, payload: WeightsSet) -> Dict[str, Any]:
    try:
        return _svc().set_weights(
            portfolio_id,
            [item.dict() for item in payload.items],
            source=payload.source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{portfolio_id}/weights/equal")
def equal_weights(portfolio_id: str) -> Dict[str, Any]:
    try:
        return _svc().equal_weights(portfolio_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{portfolio_id}/analysis")
def analyze_portfolio(portfolio_id: str) -> Dict[str, Any]:
    try:
        return _svc().analyze(portfolio_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{portfolio_id}/backtest")
def backtest_portfolio(
    portfolio_id: str,
    lookback_days: int = Query(365, ge=60, le=1500),
    benchmark_wind_code: Optional[str] = Query(None, max_length=24),
    save_snapshot: bool = Query(False),
) -> Dict[str, Any]:
    try:
        return _svc().backtest(
            portfolio_id,
            lookback_days=lookback_days,
            benchmark_wind_code=benchmark_wind_code,
            save_snapshot=save_snapshot,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{portfolio_id}/monitor")
def monitor_portfolio(portfolio_id: str) -> Dict[str, Any]:
    try:
        return _svc().monitor(portfolio_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/{portfolio_id}/targets")
def update_portfolio_targets(portfolio_id: str, payload: TargetsUpdateRequest) -> Dict[str, Any]:
    """配置目标同类组权重（监控偏离判定与再平衡提示依赖此配置）"""
    try:
        return _svc().update_portfolio(portfolio_id, targets=payload.targets)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{portfolio_id}/trade-list")
def build_trade_list(portfolio_id: str, payload: TradeListRequest) -> Dict[str, Any]:
    try:
        return _svc().trade_list(
            portfolio_id,
            current_positions=payload.current_positions,
            total_amount=payload.total_amount,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
