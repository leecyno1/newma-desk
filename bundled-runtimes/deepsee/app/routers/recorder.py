from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import FileResponse
from pathlib import Path
import os
import uuid
from datetime import datetime
from ..services import meeting_capture

from ..services.meeting_recorder import get_meeting_recorder


router = APIRouter(prefix="/api/recorder", tags=["recorder"])


@router.get("/capture/capabilities")
def capture_capabilities():
    return meeting_capture.capabilities()


@router.post("/capture")
async def upload_capture(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in meeting_capture.AUDIO_TYPES:
        raise HTTPException(415, "请上传 WebM、MP4/M4A、WAV、MP3、OGG 或 FLAC 音频")
    filename = datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + "_" + uuid.uuid4().hex[:8] + suffix
    path = meeting_capture.recording_dir() / filename
    size = 0
    try:
        with path.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > 128 * 1024 * 1024:
                    raise HTTPException(413, "录音超过 128 MB，请分段上传")
                output.write(chunk)
        if size == 0:
            raise HTTPException(400, "录音文件为空")
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    state = meeting_capture.update_state(path, status="queued", filename=filename,
        audio_url=f"/api/recorder/files/{filename}", original_name=Path(file.filename or "录音").name)
    background_tasks.add_task(meeting_capture.process_recording, path)
    return state


def _capture_path(name: str) -> Path:
    if Path(name).name != name or Path(name).suffix.lower() not in meeting_capture.AUDIO_TYPES:
        raise HTTPException(400, "录音文件名不合法")
    path = meeting_capture.recording_dir() / name
    if not path.is_file():
        raise HTTPException(404, "未找到录音")
    return path


@router.get("/capture/{name}")
def capture_status(name: str):
    path = _capture_path(name)
    state = meeting_capture.read_state(path)
    transcript = path.with_suffix(".txt")
    return {**state, "transcript": transcript.read_text() if transcript.exists() else ""}


@router.post("/capture/{name}/retry")
def retry_capture(name: str, background_tasks: BackgroundTasks):
    path = _capture_path(name)
    if meeting_capture.read_state(path).get("status") in {"queued", "transcribing", "summarizing"}:
        raise HTTPException(409, "当前录音正在处理")
    state = meeting_capture.update_state(path, status="queued", error="")
    background_tasks.add_task(meeting_capture.process_recording, path)
    return state


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
    exts = meeting_capture.AUDIO_TYPES
    files = []
    for p in sorted(base.glob("*")):
        if p.is_file() and p.suffix.lower() in exts:
            files.append({"name": p.name, "size": p.stat().st_size, "mtime": int(p.stat().st_mtime)})
    return {"files": files}


@router.get("/files/{name}")
def get_file(name: str):
    base = Path(os.getcwd()).resolve() / "data" / "recordings"
    p = (base / name).resolve()
    if not p.is_relative_to(base.resolve()):
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
    elif p.suffix.lower() == ".webm":
        mt = "audio/webm"
    elif p.suffix.lower() == ".mp4":
        mt = "audio/mp4"
    return FileResponse(str(p), media_type=mt, filename=p.name)

