from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
import os

from ..services.meeting_recorder import get_meeting_recorder


router = APIRouter(prefix="/api/recorder", tags=["recorder"])


@router.get("/devices")
def list_devices():
    rec = get_meeting_recorder()
    return rec.list_devices()


@router.get("/status")
def status():
    rec = get_meeting_recorder()
    s = rec.status()
    # surface a stable flag for UI
    s["supported"] = bool(s.get("supported", True))
    return s


@router.post("/start")
def start(payload: dict = Body(default={})):
    try:
        mic_index = int(payload.get("mic_index"))
    except Exception:
        raise HTTPException(400, "mic_index required")
    system_index = payload.get("system_index")
    try:
        system_index_int = int(system_index) if system_index is not None and str(system_index).strip() != "" else None
    except Exception:
        system_index_int = None
    try:
        threshold_db = float(payload.get("threshold_db", -45.0))
    except Exception:
        threshold_db = -45.0
    try:
        silence_stop_seconds = int(payload.get("silence_stop_seconds", 60))
    except Exception:
        silence_stop_seconds = 60
    fmt = str(payload.get("format") or "ogg")

    rec = get_meeting_recorder()
    return rec.start(
        mic_index=mic_index,
        system_index=system_index_int,
        threshold_db=threshold_db,
        silence_stop_seconds=silence_stop_seconds,
        fmt=fmt,
    )


@router.post("/stop")
def stop(payload: dict = Body(default={})):
    reason = str(payload.get("reason") or "manual")
    rec = get_meeting_recorder()
    return rec.stop(reason=reason)


@router.get("/files")
def list_files():
    base = Path(os.getcwd()).resolve() / "data" / "recordings"
    if not base.exists():
        return {"files": []}
    exts = {".ogg", ".opus", ".flac", ".wav", ".m4a", ".mp3", ".aac"}
    files = []
    for p in sorted(base.glob("*")):
        if p.is_file() and p.suffix.lower() in exts:
            files.append({"name": p.name, "size": p.stat().st_size, "mtime": int(p.stat().st_mtime)})
    return {"files": files}


@router.get("/files/{name}")
def get_file(name: str):
    base = Path(os.getcwd()).resolve() / "data" / "recordings"
    p = (base / name).resolve()
    if not str(p).startswith(str(base.resolve())):
        raise HTTPException(400, "invalid path")
    if not p.exists() or not p.is_file():
        raise HTTPException(404, "file not found")
    # infer media type roughly
    mt = "application/octet-stream"
    if p.suffix.lower() in {".ogg", ".opus"}:
        mt = "audio/ogg"
    elif p.suffix.lower() == ".flac":
        mt = "audio/flac"
    elif p.suffix.lower() == ".wav":
        mt = "audio/wav"
    elif p.suffix.lower() == ".m4a":
        mt = "audio/mp4"
    elif p.suffix.lower() == ".mp3":
        mt = "audio/mpeg"
    elif p.suffix.lower() == ".aac":
        mt = "audio/aac"
    return FileResponse(str(p), media_type=mt, filename=p.name)

