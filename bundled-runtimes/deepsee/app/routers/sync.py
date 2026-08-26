from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime
from ..db import SessionLocal
from ..services.sync_service import sync_from_chatlog, sync_full, sync_from_wx_cli, compare_with_chatlog
from ..services.snapshot_service import refresh_default_snapshots
from ..services import sync_runtime
from ..models import SyncState


router = APIRouter(prefix="/api/sync", tags=["sync"])
VALID_WECHAT_TRACKS = sync_runtime.VALID_WECHAT_TRACKS


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _load_chatlog_sync_policy(db: Session) -> dict[str, float | int]:
    return sync_runtime.get_chatlog_sync_policy(db, model_cls=SyncState)


def _wechatapi_track_state(db: Session) -> dict:
    return sync_runtime.get_wechatapi_track_state(db)


def _chatlog_track_state() -> dict:
    return sync_runtime.get_chatlog_track_state()


def _wx_cli_track_state() -> dict:
    return sync_runtime.get_wx_cli_track_state()


def _normalize_track_list(value, *, default: list[str]) -> list[str]:
    return sync_runtime.normalize_track_list(value, default=default)


def _legacy_dual_track_selection(mode: str) -> tuple[list[str], list[str]]:
    return sync_runtime.legacy_dual_track_selection(mode)


def _dual_track_policy(db: Session) -> dict:
    return sync_runtime.get_dual_track_policy(db, model_cls=SyncState)


def _save_dual_track_policy(db: Session, payload: dict | None) -> dict:
    return sync_runtime.save_dual_track_policy(
        db,
        model_cls=SyncState,
        payload=payload or {},
    )


@router.post("/chatlog")
def sync_chatlog(since: str | None = None, db: Session = Depends(get_db)):
    # Accept ISO strings with/without timezone and trailing Z; normalize to naive local time
    parsed_since = None
    if since:
        try:
            s = since.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is not None:
                dt = dt.astimezone().replace(tzinfo=None)
            parsed_since = dt
        except Exception:
            parsed_since = None
    adapters = sync_runtime.ChatlogSyncRunAdapters(
        sync_from_chatlog=lambda run_db, run_since: sync_from_chatlog(run_db, run_since),
        load_policy=lambda run_db: _load_chatlog_sync_policy(run_db),
        refresh_snapshots=lambda run_db: refresh_default_snapshots(run_db),
        persist_run=lambda run_db, payload: sync_runtime.persist_sync_run(run_db, SyncState, payload),
    )
    return sync_runtime.execute_chatlog_sync_run(
        db,
        since=parsed_since,
        adapters=adapters,
        model_cls=SyncState,
    )


@router.get("/state")
def sync_state(db: Session = Depends(get_db)):
    return sync_runtime.build_sync_state_payload(db, _model_cls=SyncState)


@router.get("/policy")
def get_sync_policy(db: Session = Depends(get_db)):
    return sync_runtime.get_chatlog_sync_policy(db, model_cls=SyncState)


@router.post("/policy")
def set_sync_policy(body: dict, db: Session = Depends(get_db)):
    policy = sync_runtime.save_chatlog_sync_policy(db, model_cls=SyncState, payload=body or {})
    db.commit()
    return {"status": "ok", "policy": policy}


@router.post("/chatlog/full")
def sync_chatlog_full(days: int = 30, db: Session = Depends(get_db)):
    try:
        res = sync_full(db, days=days)
        refresh_default_snapshots(db)
        db.commit()
        return res
    except Exception:
        db.rollback()
        raise


@router.post("/wx-cli/full")
def sync_wx_cli_full(days: int = 1, db: Session = Depends(get_db)):
    try:
        res = sync_from_wx_cli(db, days=days)
        refresh_default_snapshots(db)
        db.commit()
        return res
    except Exception:
        db.rollback()
        raise


@router.get("/wechat/dual-track/state")
def wechat_dual_track_state(db: Session = Depends(get_db)):
    policy = _dual_track_policy(db)
    wechatapi = _wechatapi_track_state(db)
    chatlog = _chatlog_track_state()
    wx_cli = _wx_cli_track_state()
    track_states = {"wechatapi": wechatapi, "chatlog": chatlog, "wx_cli": wx_cli}
    enabled_order = [track for track in policy["track_order"] if track in set(policy["enabled_tracks"])]
    active_track = enabled_order[0] if enabled_order else "none"
    healthy_active_track = next((track for track in enabled_order if track_states.get(track, {}).get("healthy")), None)
    return {
        "status": "ok",
        "policy": policy,
        "active_track": active_track,
        "healthy_active_track": healthy_active_track,
        "enabled_order": enabled_order,
        "available_tracks": list(VALID_WECHAT_TRACKS),
        "tracks": {"wechatapi": wechatapi, "chatlog": chatlog, "wx_cli": wx_cli},
    }


@router.post("/wechat/dual-track/policy")
def save_wechat_dual_track_policy(body: dict, db: Session = Depends(get_db)):
    policy = _save_dual_track_policy(db, body or {})
    db.commit()
    return {"status": "ok", "policy": policy}


@router.post("/wechat/dual-track")
def sync_wechat_dual_track(days: int | None = None, db: Session = Depends(get_db)):
    adapters = sync_runtime.DualTrackSyncAdapters(
        load_policy=lambda run_db: _dual_track_policy(run_db),
        get_wechatapi_state=lambda run_db: _wechatapi_track_state(run_db),
        get_chatlog_state=lambda _run_db: _chatlog_track_state(),
        get_wx_cli_state=lambda _run_db: _wx_cli_track_state(),
        sync_full=lambda run_db, requested_days: sync_full(run_db, days=requested_days),
        sync_from_wx_cli=lambda run_db, requested_days: sync_from_wx_cli(
            run_db,
            days=requested_days,
        ),
        refresh_snapshots=lambda run_db: refresh_default_snapshots(run_db),
        persist_run=lambda run_db, payload: sync_runtime.persist_sync_run(run_db, SyncState, payload),
    )
    return sync_runtime.execute_dual_track_sync_run(
        db,
        days=days,
        adapters=adapters,
        model_cls=SyncState,
    )


@router.get("/compare")
def sync_compare(days: int | None = 1, date: str | None = None, fix: bool | None = False, db: Session = Depends(get_db)):
    """Compare DB with chatlog for a date range or a specific day.

    - days: compare [now-days+1 .. now]; ignored if `date` is provided
    - date: YYYY-MM-DD for single day
    - fix: when true, insert missing chatlog messages into DB
    """
    # Run compare; when fix=True internal engine-level transaction is used, so no session commit here
    res = compare_with_chatlog(db, days=days, date=date, fix=bool(fix))
    return res
