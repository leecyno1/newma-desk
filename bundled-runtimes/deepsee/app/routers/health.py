from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Request

from ..config import settings
from ..db import SessionLocal
from ..schemas import Health, ReadyOut, HealthCheckItem
from ..background import get_background_runtime_snapshot
from ..services.deployment_status import build_readiness_checks

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health", response_model=Health)
async def health():
    return Health(status="ok", chatlog_http_base=settings.CHATLOG_HTTP_BASE, chatlog_dir=settings.CHATLOG_DIR)


def _extract_token_from_request(request: Request) -> str:
    auth = str(request.headers.get("authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return str(request.headers.get("x-api-token") or "").strip()


@router.get("/access/verify")
async def verify_access_token(request: Request):
    configured = str(getattr(settings, "API_TOKEN", "") or "").strip()
    if not configured:
        return {"status": "ok", "configured": False}
    provided = _extract_token_from_request(request)
    if provided != configured:
        raise HTTPException(status_code=401, detail="unauthorized")
    return {"status": "ok", "configured": True}


@router.get("/background/runtime")
async def background_runtime():
    runtime = get_background_runtime_snapshot()
    enabled = {k: v for k, v in runtime.items() if bool(v.get("enabled"))}
    return {
        "status": "ok",
        "total": len(runtime),
        "enabled": len(enabled),
        "runtime": runtime,
    }


@router.get("/ready", response_model=ReadyOut)
def ready():
    db = SessionLocal()
    try:
        checks = [HealthCheckItem(**item.as_dict()) for item in build_readiness_checks(db)]
    finally:
        db.close()

    failed = [c for c in checks if c.status == "fail"]
    error_code = failed[0].error_code if failed else None
    return ReadyOut(
        status="ok" if not failed else "degraded",
        healthy=not failed,
        error_code=error_code,
        checks=checks,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
