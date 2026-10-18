"""Loopback-only administration; never publish this route through a proxy."""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from ..models import DataApiProject, DataApiRequest
from ..services.data_api_access import SCOPES, get_db, configured_clients
from ..services.data_api_projects import create_project, project_view, issue_key


def local_admin(request: Request, response: Response):
    loopback = {"127.0.0.1", "::1", "localhost"}
    origin = request.headers.get("origin")
    if (not request.client or request.client.host not in loopback
            or request.url.hostname not in loopback
            or request.headers.get("x-forwarded-for") or request.headers.get("forwarded")
            or request.headers.get("x-deepsee-admin") != "1"):
        raise HTTPException(403, "developer_center_local_only")
    if origin and origin != f"{request.url.scheme}://{request.url.netloc}":
        raise HTTPException(403, "cross_origin_admin_denied")
    if request.headers.get("sec-fetch-site") not in {None, "same-origin", "none"}:
        raise HTTPException(403, "cross_origin_admin_denied")
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(prefix="/api/developer", tags=["developer-local-admin"], dependencies=[Depends(local_admin)])


class ProjectInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=80)
    scopes: list[str] = Field(min_length=1, max_length=20)
    requests_per_minute: int = Field(default=120, ge=1, le=10000)

    @field_validator("scopes")
    @classmethod
    def valid_scopes(cls, value):
        if not set(value) <= SCOPES:
            raise ValueError("unknown scope")
        return sorted(set(value))


class ProjectUpdate(ProjectInput):
    enabled: bool = True


def find_project(db, project_id):
    row = db.get(DataApiProject, project_id)
    if row is None:
        raise HTTPException(404, "project_not_found")
    return row


@router.get("/projects")
def projects(db: Session = Depends(get_db)):
    items = [project_view(row) for row in db.query(DataApiProject).order_by(DataApiProject.created_at.desc())]
    for name, client in configured_clients(allow_empty=True).items():
        items.append({"id": f"env:{name}", "name": name, "source": "environment", "enabled": True,
                      "scopes": client.scopes, "requests_per_minute": client.requests_per_minute})
    return {"data": items, "scopes": sorted(SCOPES)}


@router.post("/projects", status_code=201)
def create(payload: ProjectInput, response: Response, db: Session = Depends(get_db)):
    row, token = create_project(db, payload.model_dump())
    response.headers["Location"] = f"/api/developer/projects/{row.id}"
    return {"data": project_view(row), "token": token, "notice": "密钥仅显示一次，请保存到调用项目的密钥管理器。"}


@router.put("/projects/{project_id}")
def update(project_id: str, payload: ProjectUpdate, db: Session = Depends(get_db)):
    row = find_project(db, project_id)
    for key, value in payload.model_dump().items():
        setattr(row, key, value)
    db.commit()
    return {"data": project_view(row)}


@router.delete("/projects/{project_id}", status_code=204)
def revoke(project_id: str, db: Session = Depends(get_db)):
    row = find_project(db, project_id)
    row.enabled = False
    db.commit()


@router.post("/projects/{project_id}/rotate")
def rotate(project_id: str, db: Session = Depends(get_db)):
    row = find_project(db, project_id)
    token = issue_key(row)
    row.rotated_at = datetime.utcnow()
    db.commit()
    return {"data": project_view(row), "token": token}


@router.get("/requests")
def requests(project_id: str | None = None, limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)):
    query = db.query(DataApiRequest)
    if project_id:
        query = query.filter(DataApiRequest.project_id == project_id)
    rows = query.order_by(DataApiRequest.id.desc()).limit(limit).all()
    return {"data": [{"project_id": row.project_id, "route": row.route,
                       "status": row.status_code, "request_id": row.request_id,
                       "at": row.created_at.isoformat() + "Z"} for row in rows]}
