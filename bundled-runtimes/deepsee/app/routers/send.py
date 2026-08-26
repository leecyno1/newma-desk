from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import SendCampaign, SendDelivery, Task
from ..schemas import (
    SendCampaignCreateRequest,
    SendCampaignDetailOut,
    SendCampaignOut,
    SendCapabilityOut,
    SendRequest,
    SendRetryRequest,
    SendUploadOut,
    TaskOut,
)
from ..services.link_preview import fetch_link_preview
from ..services.send_dispatcher import (
    build_item_payload,
    dispatch_send_item,
    dispatch_send_items,
    get_send_upload_meta,
    get_send_upload_path,
    provider_capabilities,
    render_text_fallback,
    save_send_upload,
)


router = APIRouter(prefix="/api", tags=["send"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _merge_campaign_meta(campaign: SendCampaign, patch: dict) -> None:
    current = campaign.meta if isinstance(campaign.meta, dict) else {}
    campaign.meta = {**current, **patch}


def _refresh_campaign_stats(campaign: SendCampaign) -> None:
    deliveries = list(campaign.deliveries or [])
    campaign.target_count = len(deliveries)
    campaign.success_count = sum(1 for row in deliveries if str(row.status or "") == "sent")
    campaign.failed_count = sum(1 for row in deliveries if str(row.status or "") == "failed")
    if campaign.target_count <= 0:
        campaign.status = "draft"
    elif campaign.success_count == campaign.target_count:
        campaign.status = "sent"
    elif campaign.success_count > 0 and campaign.failed_count > 0:
        campaign.status = "partial"
    elif campaign.failed_count == campaign.target_count:
        campaign.status = "failed"
    else:
        campaign.status = "sending"
    campaign.updated_at = datetime.utcnow()


def _campaign_detail(db: Session, campaign_id: int) -> SendCampaign:
    row = db.get(SendCampaign, int(campaign_id))
    if not row:
        raise HTTPException(status_code=404, detail="campaign not found")
    return row


def _ensure_delivery_rows(
    db: Session,
    campaign: SendCampaign,
    items: list,
    request: Request | None = None,
) -> list[SendDelivery]:
    rows: list[SendDelivery] = []
    seen_targets: set[str] = set()
    deduped_targets: list[str] = []
    for item in items:
        payload = build_item_payload(item, request)
        target = str(payload.get("target") or "").strip()
        if not target:
            continue
        if target in seen_targets:
            if target not in deduped_targets:
                deduped_targets.append(target)
            continue
        seen_targets.add(target)
        delivery = SendDelivery(
            campaign_id=campaign.id,
            target_id=target,
            target_name=payload.get("target_name") or None,
            rendered_text=render_text_fallback(payload["content_parts"], payload["attachments"]),
            content_parts=payload["content_parts"],
            attachment_snapshot=payload["attachments"],
            provider=payload.get("provider_override") or campaign.provider,
            channel=payload.get("channel") or campaign.channel,
            status="pending",
        )
        db.add(delivery)
        rows.append(delivery)
    if deduped_targets:
        _merge_campaign_meta(campaign, {"deduped_targets": deduped_targets})
        db.add(campaign)
    db.flush()
    return rows


def _send_deliveries(
    db: Session,
    campaign: SendCampaign,
    deliveries: list[SendDelivery],
) -> SendCampaign:
    for delivery in deliveries:
        item = {
            "target": delivery.target_id,
            "target_name": delivery.target_name,
            "content_parts": delivery.content_parts or [],
            "attachments": delivery.attachment_snapshot or [],
            "provider_override": delivery.provider or campaign.provider,
            "channel": delivery.channel or campaign.channel,
            "campaign_id": campaign.id,
            "delivery_id": delivery.id,
        }
        result = dispatch_send_item(item)
        delivery.provider = str(result.get("provider") or delivery.provider or campaign.provider or "").strip() or None
        delivery.provider_result = result
        delivery.rendered_text = str(result.get("rendered_text") or delivery.rendered_text or "").strip() or None
        if result.get("ok"):
            delivery.status = "sent"
            delivery.error = None
            delivery.sent_at = datetime.utcnow()
        else:
            delivery.status = "failed"
            delivery.error = str(result.get("error") or result.get("fallback_error") or "send failed").strip()
        delivery.updated_at = datetime.utcnow()
        db.add(delivery)
    _refresh_campaign_stats(campaign)
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


@router.post("/send", response_model=TaskOut)
def send(body: SendRequest, db: Session = Depends(get_db)):
    ctx = {
        "request_id": "send-task",
        "items": [i.model_dump() for i in body.items],
    }
    task = Task(type="send", payload=ctx, status="pending")
    db.add(task)
    db.commit()
    db.refresh(task)

    try:
        result = dispatch_send_items(body.items)
        rows = result.get("results") if isinstance(result, dict) else []
        failed = [row for row in (rows or []) if isinstance(row, dict) and not row.get("ok")]
        task.status = "failed" if failed else "done"
        task.result = result
        db.add(task)
        db.commit()
        db.refresh(task)
    except Exception as e:
        task.status = "failed"
        task.result = {"error": str(e)}
        db.add(task)
        db.commit()
        db.refresh(task)

    return TaskOut(id=task.id, type=task.type, status=task.status, result=task.result)


@router.post("/send/uploads", response_model=SendUploadOut)
def upload_send_asset(request: Request, file: UploadFile = File(...)):
    try:
        return save_send_upload(file, request)
    except ValueError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/send/uploads/{file_id}")
def get_send_upload(file_id: str):
    meta = get_send_upload_meta(file_id)
    path = get_send_upload_path(file_id)
    if not meta or not path:
        raise HTTPException(status_code=404, detail="upload not found")
    return FileResponse(str(path), media_type=str(meta.get("mime") or "application/octet-stream"), filename=str(meta.get("name") or path.name))


@router.get("/send/capabilities")
def get_send_capabilities():
    current = provider_capabilities()
    return {
        "current": SendCapabilityOut(**current),
        "providers": [
            SendCapabilityOut(**provider_capabilities("wechatapi_gateway")),
        ],
    }


@router.get("/send/link-preview")
def get_send_link_preview(url: str = Query(..., min_length=8, max_length=4096)):
    try:
        return fetch_link_preview(url)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"链接解析失败：{exc}") from exc


@router.post("/send/out")
def send_out(body: SendRequest, request: Request):
    """Dispatch all WeChat sends through the configured WeChatAPI account."""
    return dispatch_send_items(body.items, request=request)


@router.post("/send/campaigns", response_model=SendCampaignDetailOut)
def create_send_campaign(body: SendCampaignCreateRequest, request: Request, db: Session = Depends(get_db)):
    provider = str(body.provider_override or provider_capabilities().get("provider") or "").strip() or None
    campaign = SendCampaign(
        title=str(body.title or "").strip() or None,
        body_text=str(body.body_text or "").strip() or None,
        content_parts=body.content_parts,
        attachments=body.attachments,
        provider=provider,
        channel=str(body.channel or "").strip() or None,
        created_by=str(body.created_by or "").strip() or None,
        status="draft",
        meta={"save_only": bool(body.save_only)},
    )
    db.add(campaign)
    db.flush()
    rows = _ensure_delivery_rows(db, campaign, body.items, request=request)
    _refresh_campaign_stats(campaign)
    if body.save_only or not body.send_now:
        campaign.status = "draft"
        db.add(campaign)
        db.commit()
        db.refresh(campaign)
        return campaign
    return _send_deliveries(db, campaign, rows)


@router.get("/send/campaigns", response_model=list[SendCampaignOut])
def list_send_campaigns(limit: int = 30, db: Session = Depends(get_db)):
    stmt = select(SendCampaign).order_by(SendCampaign.id.desc()).limit(max(1, min(int(limit or 30), 200)))
    return list(db.scalars(stmt).all())


@router.get("/send/campaigns/{campaign_id}", response_model=SendCampaignDetailOut)
def get_send_campaign(campaign_id: int, db: Session = Depends(get_db)):
    return _campaign_detail(db, campaign_id)


@router.post("/send/campaigns/{campaign_id}/retry", response_model=SendCampaignDetailOut)
def retry_send_campaign(campaign_id: int, body: SendRetryRequest, db: Session = Depends(get_db)):
    campaign = _campaign_detail(db, campaign_id)
    requested = list(campaign.deliveries or [])
    if body.delivery_ids:
        wanted = {int(v) for v in body.delivery_ids}
        requested = [row for row in requested if int(row.id) in wanted]
    elif body.target_ids:
        wanted = {str(v).strip() for v in body.target_ids if str(v).strip()}
        requested = [row for row in requested if str(row.target_id or "").strip() in wanted]
    else:
        requested = [row for row in requested if str(row.status or "") == "failed"]

    skipped_already_sent = [int(row.id) for row in requested if str(row.status or "") == "sent"]
    selected = [row for row in requested if str(row.status or "") != "sent"]
    _merge_campaign_meta(
        campaign,
        {
            "last_retry": {
                "requested_delivery_ids": [int(row.id) for row in requested],
                "selected_delivery_ids": [int(row.id) for row in selected],
                "skipped_already_sent": skipped_already_sent,
                "started_at": datetime.utcnow().isoformat(),
            }
        },
    )
    db.add(campaign)
    if not selected:
        db.commit()
        db.refresh(campaign)
        return campaign
    for row in selected:
        row.status = "pending"
        row.error = None
        row.provider_result = None
        row.updated_at = datetime.utcnow()
        db.add(row)
    db.commit()
    db.refresh(campaign)
    return _send_deliveries(db, campaign, selected)
