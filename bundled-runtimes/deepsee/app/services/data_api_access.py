"""Independent, fail-closed access for read-only integration clients."""
from __future__ import annotations

import json
import hashlib
import secrets
import threading
import time
from collections import deque

from fastapi import Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..config import settings
from ..db import SessionLocal
from ..models import DataApiProject

SCOPES = frozenset({"messages:read", "contacts:read", "chats:read", "emails:read",
                    "news:read", "media:read", "mp:read", "meetings:read", "scores:read", "attachments:read"})
bearer = HTTPBearer(auto_error=False, scheme_name="ProjectApiKey")


class ProjectClient(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=24)
    scopes: list[str]
    requests_per_minute: int = Field(default=120, ge=1, le=10000)


class ProjectAccess(BaseModel):
    project: str
    scopes: list[str]
    requests_per_minute: int
    client_id: str | None = None


def get_db():
    with SessionLocal() as db:
        yield db


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def configured_clients(*, allow_empty: bool = False) -> dict[str, ProjectClient]:
    raw = str(settings.DATA_API_CLIENTS or "").strip()
    if not raw:
        if allow_empty:
            return {}
        raise HTTPException(503, "data_api_not_configured")
    try:
        config = json.loads(raw)
        if not isinstance(config, dict) or not config:
            raise ValueError()
        clients = {name: ProjectClient.model_validate(value) for name, value in config.items()}
        if any(not name.strip() or not set(client.scopes) <= SCOPES for name, client in clients.items()):
            raise ValueError()
        if len({c.token for c in clients.values()}) != len(clients):
            raise ValueError()
        return clients
    except (ValueError, TypeError, ValidationError):
        raise HTTPException(503, "data_api_configuration_invalid") from None


class ProjectRateLimiter:
    def __init__(self):
        self.windows: dict[str, deque] = {}
        self.lock = threading.Lock()

    def take(self, project: str, limit: int) -> tuple[int, int]:
        now = time.monotonic()
        with self.lock:
            hits = self.windows.setdefault(project, deque())
            while hits and hits[0] <= now - 60:
                hits.popleft()
            retry = max(1, int(60 - (now - hits[0])) + 1) if hits else 60
            if len(hits) >= limit:
                raise HTTPException(429, "rate_limit_exceeded", headers={"Retry-After": str(retry)})
            hits.append(now)
            return limit - len(hits), retry


def require_project(
    request: Request,
    response: Response,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> ProjectAccess:
    clients = configured_clients(allow_empty=True)
    token = credentials.credentials if credentials else ""
    managed = db.query(DataApiProject).filter_by(token_digest=token_digest(token), enabled=True).first() if token else None
    access = None
    if managed:
        access = ProjectAccess(project=managed.name, scopes=managed.scopes,
                               requests_per_minute=managed.requests_per_minute, client_id=managed.id)
    for name, client in clients.items():
        if secrets.compare_digest(token.encode(), client.token.encode()):
            access = ProjectAccess(project=name, scopes=client.scopes,
                                   requests_per_minute=client.requests_per_minute, client_id=f"env:{name}")
            break
    if access:
        request.state.data_api_access = access
        request.state.data_api_db = db
        remaining, reset = request.app.state.data_api_limiter.take(access.client_id, access.requests_per_minute)
        response.headers["X-RateLimit-Limit"] = str(access.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset-After"] = str(reset)
        request.state.data_api_rate_headers = {
            "X-RateLimit-Limit": str(access.requests_per_minute),
            "X-RateLimit-Remaining": str(remaining), "X-RateLimit-Reset-After": str(reset)}
        return access
    if not clients and db.query(DataApiProject.id).first() is None:
        raise HTTPException(503, "data_api_not_configured")
    raise HTTPException(401, "invalid_api_key", headers={"WWW-Authenticate": "Bearer"})


def require_scope(access: ProjectAccess, scope: str) -> None:
    if scope not in access.scopes:
        raise HTTPException(403, "insufficient_scope")
