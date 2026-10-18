"""Local project administration. Raw project credentials are never persisted."""
from datetime import datetime, timedelta
import secrets
from uuid import uuid4

from sqlalchemy.orm import Session

from ..models import DataApiProject, DataApiRequest
from .data_api_access import token_digest


def project_view(row: DataApiProject) -> dict:
    return {"id": row.id, "name": row.name, "token_prefix": row.token_prefix,
            "scopes": row.scopes, "requests_per_minute": row.requests_per_minute,
            "enabled": row.enabled, "created_at": row.created_at.isoformat() + "Z",
            "rotated_at": row.rotated_at.isoformat() + "Z" if row.rotated_at else None,
            "source": "managed"}


def issue_key(row: DataApiProject) -> str:
    token = "dsee_" + secrets.token_urlsafe(32)
    row.token_digest = token_digest(token)
    row.token_prefix = token[:12]
    return token


def create_project(db: Session, payload: dict) -> tuple[DataApiProject, str]:
    row = DataApiProject(id=str(uuid4()), **payload)
    token = issue_key(row)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row, token


def record_request(db: Session, project_id: str, route: str, status: int, request_id: str):
    db.add(DataApiRequest(project_id=project_id, route=route,
                         status_code=status, request_id=request_id))
    # Keep thirty days; never log query strings, credentials, message text or response bodies.
    db.query(DataApiRequest).filter(DataApiRequest.created_at < datetime.utcnow() - timedelta(days=30)).delete()
    db.commit()
