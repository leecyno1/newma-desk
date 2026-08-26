from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..services.market_data import (
    fetch_market_series,
    load_market_data_config,
    market_provider_health,
    normalize_asset_identity,
    search_asset_in_text,
)


router = APIRouter(prefix="/api/market", tags=["market"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/health")
def market_health(db: Session = Depends(get_db)):
    return market_provider_health(load_market_data_config(db))


@router.get("/series")
def get_market_series(
    asset_type: str = "index",
    symbol: str = "sh000001",
    days: int = 60,
    db: Session = Depends(get_db),
):
    history_days = max(5, min(1500, int(days)))
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=history_days + 20)
    cfg = load_market_data_config(db)
    normalized = normalize_asset_identity(asset_type, symbol)
    items = fetch_market_series(asset_type, symbol, start_date, end_date, config=cfg)
    if not items:
        raise HTTPException(status_code=502, detail=f"未获取到 {asset_type}:{symbol} 的行情数据")
    return {
        "asset_type": normalized["asset_type"],
        "symbol": symbol,
        "normalized": normalized,
        "count": len(items[-history_days:]),
        "items": items[-history_days:],
        "provider_health": market_provider_health(cfg),
    }


@router.get("/lookup")
def lookup_market_asset(q: str, db: Session = Depends(get_db)):
    query = str(q or "").strip()
    if len(query) < 2:
        raise HTTPException(status_code=400, detail="q too short")
    cfg = load_market_data_config(db)
    item = search_asset_in_text(query, cfg)
    return {
        "query": query,
        "item": item,
        "provider_health": market_provider_health(cfg),
    }


@router.get("/index")
def get_index_series(symbol: str = "sh000001", days: int = 60, db: Session = Depends(get_db)):
    return get_market_series(asset_type="index", symbol=symbol, days=days, db=db)
