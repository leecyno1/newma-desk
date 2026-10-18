"""Versioned read-only API for external projects."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.routing import APIRoute
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..data_api_schemas import (CapabilitiesData, ChatData, ContactData, ContentData, DataItem,
                                DataPage, EmailData, ErrorData, LabelsData, MessageData,
                                ResourceCapability)
from ..models import Chat, Contact, EmailMessage, Message
from ..services.data_api_access import ProjectAccess, require_project, require_scope, get_db
from ..services import public_data as data
from ..data_api_schemas import SearchResponse, ScorecardData

logger = logging.getLogger(__name__)


class DataApiRoute(APIRoute):
    def get_route_handler(self):
        original = super().get_route_handler()

        async def handle(request: Request):
            request_id = uuid4().hex
            try:
                response = await original(request)
            except RequestValidationError:
                response = JSONResponse({"error": {"code": "validation_error",
                    "message": "Invalid query parameters; see the OpenAPI schema.", "request_id": request_id}}, status_code=422)
            except HTTPException as exc:
                code = str(exc.detail)
                response = JSONResponse({"error": {"code": code, "message": code.replace("_", " "),
                    "request_id": request_id}}, status_code=exc.status_code, headers=exc.headers)
            except Exception:
                logger.exception("Data API request failed: %s", request_id)
                response = JSONResponse({"error": {"code": "internal_error",
                    "message": "Unable to read this data source.", "request_id": request_id}}, status_code=500)
            response.headers["X-Request-ID"] = request_id
            response.headers["Cache-Control"] = "no-store"
            response.headers.update(getattr(request.state, "data_api_rate_headers", {}))
            access = getattr(request.state, "data_api_access", None)
            if access:
                from ..services.data_api_projects import record_request
                try:
                    await run_in_threadpool(record_request, request.state.data_api_db, access.client_id,
                                            self.path, response.status_code, request_id)
                except Exception:
                    request.state.data_api_db.rollback()
                    logger.warning("Unable to record data API audit: %s", request_id)
            return response
        return handle


router = APIRouter(prefix="/api/v1", tags=["project-data-api"], route_class=DataApiRoute,
                   responses={status: {"model": ErrorData} for status in (401, 403, 404, 422, 429, 500, 502, 503)})

RESOURCES = [
    ResourceCapability(resource="messages", path="/api/v1/messages", scope="messages:read", pagination="cursor", incremental="new_records_by_id"),
    ResourceCapability(resource="contacts", path="/api/v1/contacts", scope="contacts:read", pagination="cursor"),
    ResourceCapability(resource="labels", path="/api/v1/labels", scope="contacts:read", pagination="none"),
    ResourceCapability(resource="chats", path="/api/v1/chats", scope="chats:read", pagination="cursor"),
    ResourceCapability(resource="emails", path="/api/v1/emails", scope="emails:read", pagination="cursor", incremental="new_records_by_id"),
    *[ResourceCapability(resource=name, path=f"/api/v1/articles?source={name}", scope=f"{name}:read", pagination="offset") for name in ("news", "media", "mp")],
    ResourceCapability(resource="meetings", path="/api/v1/meetings", scope="meetings:read", pagination="offset"),
    ResourceCapability(resource="scores", path="/api/v1/contacts/{contact_id}/scorecard", scope="scores:read", pagination="offset"),
    ResourceCapability(resource="attachments", path="/api/v1/messages/{message_id}/attachment", scope="attachments:read", pagination="none"),
]


@router.get("/capabilities", response_model=DataItem[CapabilitiesData])
def capabilities(access: ProjectAccess = Depends(require_project)):
    return DataItem(data=CapabilitiesData(project=access.project,
        resources=[r for r in RESOURCES if r.scope in access.scopes],
        rate_limit_per_minute=access.requests_per_minute))


@router.get("/openapi.json", include_in_schema=False)
def project_openapi(access: ProjectAccess = Depends(require_project)):
    return get_openapi(title="Deepsee Project Data API", version="1.1.0", routes=router.routes,
        description="Read-only access to persisted data. Each project uses an independent Bearer API key.")


@router.get("/messages", response_model=DataPage[MessageData])
def messages(
    limit: int = Query(100, ge=1, le=200), cursor: str | None = Query(None, max_length=4096),
    after_id: int | None = Query(None, ge=0), q: str | None = Query(None, max_length=200),
    chat_id: str | None = Query(None, max_length=255), sender_id: str | None = Query(None, max_length=255),
    since: datetime | None = None, until: datetime | None = None,
    access: ProjectAccess = Depends(require_project), db: Session = Depends(get_db),
):
    """Read by ascending storage ID. after_id discovers newly inserted records, including late arrivals."""
    require_scope(access, "messages:read")
    conditions = data.text_search(q, Message.content_text, Message.sender_name, Message.talker_name)
    for value, column in [(chat_id, Message.chat_id), (sender_id, Message.sender_id)]:
        if value is not None:
            conditions.append(column == value)
    start, end = data.local_time(since), data.local_time(until)
    if start and end and start >= end:
        raise HTTPException(422, "invalid_time_range")
    if start:
        conditions.append(Message.timestamp >= start)
    if end:
        conditions.append(Message.timestamp < end)
    filters = {"q": q, "chat_id": chat_id, "sender_id": sender_id,
               "since": since.isoformat() if since else None, "until": until.isoformat() if until else None}
    rows, meta = data.database_page(db, Message, "messages", filters, conditions, limit, cursor, after_id)
    return DataPage(data=data.message_data(db, rows), meta=meta)


@router.get("/messages/{message_id}", response_model=DataItem[MessageData])
def message(message_id: int, access: ProjectAccess = Depends(require_project), db: Session = Depends(get_db)):
    require_scope(access, "messages:read")
    row = db.get(Message, message_id)
    if row is None:
        raise HTTPException(404, "not_found")
    return DataItem(data=data.message_data(db, [row])[0])


@router.get("/contacts", response_model=DataPage[ContactData])
def contacts(limit: int = Query(100, ge=1, le=200), cursor: str | None = Query(None, max_length=4096),
             q: str | None = Query(None, max_length=200),
             access: ProjectAccess = Depends(require_project), db: Session = Depends(get_db)):
    require_scope(access, "contacts:read")
    rows, meta = data.database_page(db, Contact, "contacts", {"q": q},
        data.text_search(q, Contact.id, Contact.alias, Contact.name), limit, cursor)
    return DataPage(data=[data.contact_data(row) for row in rows], meta=meta)


@router.get("/contacts/{contact_id}", response_model=DataItem[ContactData])
def contact(contact_id: str, access: ProjectAccess = Depends(require_project), db: Session = Depends(get_db)):
    require_scope(access, "contacts:read")
    row = db.get(Contact, contact_id)
    if row is None:
        raise HTTPException(404, "not_found")
    return DataItem(data=data.contact_data(row))


@router.get("/labels", response_model=LabelsData)
def labels(access: ProjectAccess = Depends(require_project), db: Session = Depends(get_db)):
    require_scope(access, "contacts:read")
    return data.labels_data(db)


@router.get("/chats", response_model=DataPage[ChatData])
def chats(limit: int = Query(100, ge=1, le=200), cursor: str | None = Query(None, max_length=4096),
          q: str | None = Query(None, max_length=200),
          access: ProjectAccess = Depends(require_project), db: Session = Depends(get_db)):
    require_scope(access, "chats:read")
    rows, meta = data.database_page(db, Chat, "chats", {"q": q},
        data.text_search(q, Chat.id, Chat.title), limit, cursor)
    return DataPage(data=[data.chat_data(row) for row in rows], meta=meta)


@router.get("/emails", response_model=DataPage[EmailData])
def emails(limit: int = Query(100, ge=1, le=200), cursor: str | None = Query(None, max_length=4096),
           after_id: int | None = Query(None, ge=0), q: str | None = Query(None, max_length=200),
           access: ProjectAccess = Depends(require_project), db: Session = Depends(get_db)):
    require_scope(access, "emails:read")
    rows, meta = data.database_page(db, EmailMessage, "emails", {"q": q},
        data.text_search(q, EmailMessage.subject, EmailMessage.body_text, EmailMessage.from_addr), limit, cursor, after_id)
    return DataPage(data=[data.email_data(row) for row in rows], meta=meta)


@router.get("/emails/{email_id}", response_model=DataItem[EmailData])
def email(email_id: int, access: ProjectAccess = Depends(require_project), db: Session = Depends(get_db)):
    require_scope(access, "emails:read")
    row = db.get(EmailMessage, email_id)
    if row is None:
        raise HTTPException(404, "not_found")
    return DataItem(data=data.email_data(row))


@router.get("/articles", response_model=DataPage[ContentData])
def articles(source: Literal["news", "media", "mp"], limit: int = Query(100, ge=1, le=200),
             offset: int = Query(0, ge=0, le=1000), q: str | None = Query(None, max_length=200),
             access: ProjectAccess = Depends(require_project), db: Session = Depends(get_db)):
    """Read retained local snapshots. Does not fetch remote sites or invoke AI."""
    require_scope(access, f"{source}:read")
    return data.snapshot_page(db, source, limit, offset, q)


@router.get("/meetings", response_model=DataPage[ContentData])
def meetings(limit: int = Query(100, ge=1, le=200), offset: int = Query(0, ge=0, le=1000),
             q: str | None = Query(None, max_length=200),
             access: ProjectAccess = Depends(require_project), db: Session = Depends(get_db)):
    require_scope(access, "meetings:read")
    return data.snapshot_page(db, "meetings", limit, offset, q)


@router.get("/search", response_model=SearchResponse)
def search(q: str = Query(min_length=1, max_length=200), sources: str | None = Query(None, max_length=200),
           limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0, le=1000),
           access: ProjectAccess = Depends(require_project), db: Session = Depends(get_db)):
    """Literal search grouped by source. Each group has independent pagination and coverage."""
    from ..services.public_data_extensions import search_groups, SEARCH_SOURCES
    selected = list(dict.fromkeys(sources.split(","))) if sources else [
        source for source in SEARCH_SOURCES if f"{source}:read" in access.scopes]
    if not set(selected) <= set(SEARCH_SOURCES):
        raise HTTPException(422, "unsupported_source")
    for source in selected:
        require_scope(access, f"{source}:read")
    return SearchResponse(data=search_groups(db, selected, q, limit, offset))


@router.get("/contacts/{contact_id}/scorecard", response_model=DataItem[ScorecardData])
def scorecard(contact_id: str, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0, le=10000),
              access: ProjectAccess = Depends(require_project), db: Session = Depends(get_db)):
    """Persisted evidence only; does not run scoring, market downloads or AI."""
    require_scope(access, "scores:read")
    from ..services.public_data_extensions import scorecard_data
    return DataItem(data=scorecard_data(db, contact_id, limit, offset))


@router.get("/messages/{message_id}/attachment", response_class=StreamingResponse,
            responses={200: {"description": "Retained binary media download",
                             "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}}}})
def attachment(message_id: int, access: ProjectAccess = Depends(require_project), db: Session = Depends(get_db)):
    """Download retained local Chatlog media. Requires messages AND attachments read scopes."""
    require_scope(access, "messages:read")
    require_scope(access, "attachments:read")
    from ..services.public_data_media import attachment_response
    row = db.get(Message, message_id)
    if row is None:
        raise HTTPException(404, "not_found")
    return attachment_response(row)
