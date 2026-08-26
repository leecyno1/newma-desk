"""
预警中心 API
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from repositories import get_alert_repo

router = APIRouter(prefix="/api/alerts", tags=["预警中心"])


class CreateAlertRuleRequest(BaseModel):
    name: str
    ruleType: str
    scopeType: str
    scopeId: Optional[str] = None
    threshold: Optional[Dict[str, Any]] = None
    enabled: bool = True
    createdBy: Optional[str] = None


class UpdateAlertEventRequest(BaseModel):
    status: str


class UpdateAlertRuleRequest(BaseModel):
    enabled: Optional[bool] = None
    threshold: Optional[Dict[str, Any]] = None


@router.get("")
def list_alerts(
    status: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
) -> Dict[str, Any]:
    repo = get_alert_repo()
    try:
        events = repo.list_events(status=status, severity=severity)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Alert store unavailable: {exc.__class__.__name__}") from exc
    return {"events": events, "count": len(events)}


@router.get("/rules")
def list_alert_rules(enabled: Optional[bool] = Query(None)) -> Dict[str, Any]:
    repo = get_alert_repo()
    try:
        rules = repo.list_rules(enabled=enabled)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Alert store unavailable: {exc.__class__.__name__}") from exc
    return {"rules": rules, "count": len(rules)}


@router.post("/rules")
def create_alert_rule(payload: CreateAlertRuleRequest) -> Dict[str, Any]:
    repo = get_alert_repo()
    try:
        rule = repo.create_rule(
            name=payload.name,
            rule_type=payload.ruleType,
            scope_type=payload.scopeType,
            scope_id=payload.scopeId,
            threshold=payload.threshold,
            enabled=payload.enabled,
            created_by=payload.createdBy,
        )
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Alert store unavailable: {exc.__class__.__name__}") from exc
    return rule


@router.patch('/rules/{rule_id}')
def update_alert_rule(rule_id: str, payload: UpdateAlertRuleRequest) -> Dict[str, Any]:
    repo = get_alert_repo()
    try:
        rule = repo.update_rule(rule_id=rule_id, enabled=payload.enabled, threshold=payload.threshold)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Alert store unavailable: {exc.__class__.__name__}") from exc
    if not rule:
        raise HTTPException(status_code=404, detail='Alert rule not found')
    return rule


@router.delete('/rules/{rule_id}')
def delete_alert_rule(rule_id: str) -> Dict[str, Any]:
    repo = get_alert_repo()
    try:
        deleted = repo.delete_rule(rule_id=rule_id)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Alert store unavailable: {exc.__class__.__name__}") from exc
    if not deleted:
        raise HTTPException(status_code=404, detail='Alert rule not found')
    return {'ok': True, 'id': rule_id}


@router.patch("/events/{event_id}")
def update_alert_event(event_id: str, payload: UpdateAlertEventRequest) -> Dict[str, Any]:
    repo = get_alert_repo()
    try:
        event = repo.update_event_status(event_id=event_id, status=payload.status)
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Alert store unavailable: {exc.__class__.__name__}") from exc
    if not event:
        raise HTTPException(status_code=404, detail="Alert event not found")
    return event


@router.post("/scan")
def scan_alerts(
    max_members_per_status: int = Query(20, ge=1, le=200),
    include_peer_metrics: bool = Query(False),
) -> Dict[str, Any]:
    from services.alert_scan import AlertScanService

    service = AlertScanService(
        max_members_per_status=max_members_per_status,
        include_peer_metrics=include_peer_metrics,
    )
    try:
        return service.scan()
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail=f"Alert store unavailable: {exc.__class__.__name__}") from exc
