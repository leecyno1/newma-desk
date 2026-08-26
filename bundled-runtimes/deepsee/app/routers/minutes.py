from __future__ import annotations

from fastapi import APIRouter, File, Form, Query, UploadFile
from typing import List, Dict, Any
import os
import re
import json
import hashlib
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select

from ..db import SessionLocal
from ..models import SyncState
from ..services.llm_client import load_ai_config, DEFAULT_TOOL_PROMPTS
from ..services.ai_tools import extract_message_features
router = APIRouter(prefix="/api/minutes", tags=["minutes"])


TEXT_EXTS = {".txt", ".md", ".markdown"}
AUDIO_EXTS = {".mp3", ".m4a", ".wav", ".aac", ".ogg", ".opus", ".flac"}


def _default_minutes_dirs() -> list[str]:
    # 允许通过环境变量 MINUTES_DIRS 配置多个目录，逗号分隔
    env = os.getenv("MINUTES_DIRS", "")
    if env.strip():
        return [os.path.abspath(p.strip()) for p in env.split(",") if p.strip()]
    # 默认目录
    base = os.path.abspath(os.path.join(os.getcwd(), "data"))
    return [
        os.path.join(base, "minutes"),
        os.path.join(base, "recordings"),
    ]

def _manual_minutes_dir() -> str:
    # Prefer data/minutes as the canonical folder for manual minutes.
    base = os.path.abspath(os.path.join(os.getcwd(), "data", "minutes", "manual"))
    os.makedirs(base, exist_ok=True)
    return base


def _read_text_file(path: str, limit: int = 200_000) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read(limit)
    except Exception:
        return ""


def _hash_id(path: str, mtime: float) -> str:
    h = hashlib.sha1()
    h.update(path.encode("utf-8"))
    h.update(str(int(mtime)).encode("utf-8"))
    return h.hexdigest()[:16]


def _extract_time_from_name(name: str) -> str | None:
    # 支持 2025-11-10_14-30 或 2025_11_10 10:30 等
    m = re.search(r"(20\d{2})[-_]?(\d{1,2})[-_]?(\d{1,2})(?:[ _-](\d{1,2})[:._-]?(\d{1,2}))?", name)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    hh = int(m.group(4) or 9)
    mm = int(m.group(5) or 0)
    try:
        dt = datetime(y, mo, d, hh, mm)
        return dt.isoformat()
    except Exception:
        return None


def _safe_filename(name: str, *, fallback: str = "minutes") -> str:
    s = (name or "").strip()
    if not s:
        s = fallback
    # Keep Chinese/letters/numbers/_- and collapse others to _
    s = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", s, flags=re.UNICODE)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        s = fallback
    return s[:80]


def _parse_dt_str(v: str | None) -> datetime | None:
    if not v:
        return None
    s = v.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is not None:
            dt = dt.astimezone().replace(tzinfo=None)
        return dt
    except Exception:
        return None


def _guess_speaker(text: str, fallback: str) -> str:
    # 从正文首段猜测主讲人
    head = (text or "")[:1000]
    m = re.search(r"(主讲|主持|讲者|发言|分析师|嘉宾)[:：]\s*([^\n，,。:：]{2,20})", head)
    if m:
        return m.group(2).strip()
    # 从文件名猜测
    fb = fallback.replace("_", " ").replace("-", " ")
    m2 = re.search(r"(?:会议|纪要|路演)\s*([^\s]{2,20})", fb)
    if m2:
        return m2.group(1).strip()
    return fallback


def _classify_tone(text: str) -> str:
    t = text or ""
    if re.search(r"(看多|乐观|积极|超预期|改善|提价|增持|买入)", t):
        return "positive"
    if re.search(r"(看空|谨慎|负面|下行|风险|下滑|回调|卖出|减持)", t):
        return "negative"
    return "neutral"


def _summarize_locally(text: str, limit_cn: int = 500) -> str:
    # 简单本地摘要：取前几段非空行拼接到限定长度（中文近似按字符计）
    raw = (text or "").strip()
    if not raw:
        return "ai: 信息有限"
    parts = [p.strip() for p in raw.splitlines() if p.strip()]
    acc = []
    length = 0
    for p in parts[:12]:
        for ch in p:
            length += 1
            if length > limit_cn:
                acc.append("…")
                return "ai: " + "".join(acc)
            acc.append(ch)
        acc.append("。")
        if length > limit_cn:
            break
    return "ai: " + "".join(acc).strip("。")


def _cache_get(db: Session, key: str) -> dict | None:
    try:
        row = db.get(SyncState, key)
        if row and row.value:
            if isinstance(row.value, dict):
                return row.value  # type: ignore[return-value]
            return json.loads(row.value)
    except Exception:
        return None
    return None


def _cache_set(db: Session, key: str, val: dict) -> None:
    try:
        row = db.get(SyncState, key)
        if not row:
            row = SyncState(key=key, value=val)
        else:
            existing: dict = {}
            try:
                if isinstance(row.value, dict):
                    existing = row.value  # type: ignore[assignment]
                elif isinstance(row.value, str) and row.value:
                    existing = json.loads(row.value)
            except Exception:
                existing = {}
            if not isinstance(existing, dict):
                existing = {}
            existing.update(val)
            row.value = existing
        db.add(row)
        db.commit()
    except Exception:
        db.rollback()

def _truncate_for_llm(text: str, max_chars: int = 20000) -> str:
    t = (text or "").strip()
    if not t:
        return ""
    if len(t) <= max_chars:
        return t
    # Prefer keeping the beginning (agenda/participants) and the end (Q&A/conclusion)
    head = t[: max_chars // 2]
    tail = t[-max_chars // 2 :]
    return head + "\n...\n" + tail


def _collect_minutes_items(refresh: bool = False, limit: int = 500) -> list[dict]:
    dirs = [p for p in _default_minutes_dirs() if os.path.isdir(p)]
    items: list[dict] = []
    # A) local folders (data/minutes + data/recordings)
    for base in dirs:
        for root, _, files in os.walk(base):
            for fn in files:
                path = os.path.join(root, fn)
                ext = os.path.splitext(path)[1].lower()
                if ext not in TEXT_EXTS and ext not in AUDIO_EXTS:
                    continue
                # Avoid duplicate rows: when a transcript .txt/.md sits next to its audio file, only show the audio row.
                if ext in TEXT_EXTS:
                    base_no_ext = os.path.splitext(path)[0]
                    if any(os.path.exists(base_no_ext + aext) for aext in AUDIO_EXTS):
                        continue
                try:
                    st = os.stat(path)
                except Exception:
                    continue
                mid = _hash_id(path, st.st_mtime)
                iso = _extract_time_from_name(fn) or datetime.fromtimestamp(st.st_mtime).isoformat()
                is_audio = ext in AUDIO_EXTS
                transcript_path = ""
                if is_audio:
                    base_no_ext = os.path.splitext(path)[0]
                    for t_ext in (".txt", ".md", ".markdown"):
                        cand = base_no_ext + t_ext
                        if os.path.exists(cand):
                            transcript_path = cand
                            break
                    text = _read_text_file(transcript_path) if transcript_path else ""
                else:
                    text = _read_text_file(path)
                speaker = _guess_speaker(text, os.path.splitext(fn)[0])
                audio_url = ""
                try:
                    rec_dir = os.path.abspath(os.path.join(os.getcwd(), "data", "recordings"))
                    abs_path = os.path.abspath(path)
                    if abs_path.startswith(rec_dir + os.sep):
                        audio_url = f"/api/recorder/files/{os.path.relpath(abs_path, rec_dir)}"
                except Exception:
                    audio_url = ""
                item = {
                    "channel": "minutes",
                    "id": mid,
                    "path": path,
                    "time": iso,
                    "timestamp": iso,
                    "sender_name": speaker,  # 主讲人
                    "talker_name": os.path.basename(base),
                    "message_type": "录音" if is_audio else "纪要",
                    "type": "minutes",
                    "content": text,
                    "content_text": text,
                    "derived": {
                        "category": "会议",
                        "tone": _classify_tone(text),
                    },
                    "meta": {
                        "need_transcript": bool(is_audio and not text),
                        "transcript_path": transcript_path,
                        "transcript_status": ("done" if transcript_path and text else ("pending" if is_audio else "")),
                        "audio_url": audio_url,
                        "file_mtime": int(st.st_mtime),
                    },
                }
                items.append(item)
                if len(items) >= limit:
                    break
            if len(items) >= limit:
                break
        if len(items) >= limit:
            break
    # 按时间降序
    items.sort(key=lambda x: x.get("time") or "", reverse=True)
    return items


@router.get("")
def list_minutes(
    q: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    refresh: bool = False,
    llm: bool = True,
) -> dict:
    """列出本地会议纪要/录音文件，生成≤500字的结构化会议摘要。"""
    db: Session = SessionLocal()
    try:
        base_items = _collect_minutes_items(refresh=refresh, limit=limit)
        if q:
            ql = q.strip().lower()
            base_items = [it for it in base_items if (ql in (it.get("sender_name") or "").lower()) or (ql in (it.get("content_text") or "").lower()) or (ql in (os.path.basename(it.get("path") or "")).lower())]
        # 工具模型摘要（可选）
        conf = load_ai_config()
        has_key = bool(conf.get("api_key"))
        desk_agent_enabled = bool((conf.get("desk_agent") or {}).get("enabled"))
        to_summarize: list[dict] = []
        out: list[dict] = []
        for it in base_items:
            cache_key = f"minutes:{it['id']}"
            cached = _cache_get(db, cache_key)
            if cached and isinstance(cached, dict):
                refined = cached.get("content_refined") or cached.get("refined")
                if isinstance(refined, str) and refined.strip():
                    it["content_refined"] = refined.strip()
                    try:
                        it["meta"]["refined_status"] = cached.get("refined_status") or "done"
                        it["meta"]["refined_origin"] = cached.get("refined_origin") or "tool"
                    except Exception:
                        pass
                if "summary" in cached:
                    it["summary"] = cached.get("summary")
                    it["summary_origin"] = cached.get("summary_origin") or "tool"
                    it["derived"]["tone"] = cached.get("tone") or it["derived"].get("tone")
                    it["derived"]["key_points"] = cached.get("key_points") or it["derived"].get("key_points") or []
                    it["derived"]["comment"] = cached.get("comment") or it["derived"].get("comment") or ""
                    if it["summary_origin"] == "tool":
                        out.append(it)
                        continue
            to_summarize.append({"id": it["id"], "time": it["time"], "sender": it["sender_name"], "content": it["content_text"]})
            out.append(it)
        # 调用小模型生成会议摘要（<=500字）
        if to_summarize:
            try:
                if llm and (has_key or desk_agent_enabled):
                    # 定义 minutes_summary 提示词；若未在 ai_config 中定义，则给出默认
                    if "minutes_summary" not in DEFAULT_TOOL_PROMPTS:
                        pass  # 由 llm_client 的 DEFAULT_TOOL_PROMPTS 提供
                    model_ovr = conf.get("tool_model_messages") or conf.get("tool_model")
                    feats = extract_message_features(
                        to_summarize,
                        batch_size=50,
                        concurrency=3,
                        temperature=0.1,
                        prompt_key="minutes_summary",
                        model_override=model_ovr,
                        route_key="minutes",
                    )
                    for it in out:
                        fid = str(it["id"])
                        f = feats.get(fid) or {}
                        feature_origin = "fallback" if f.get("summary_origin") == "fallback" else "tool"
                        summ = (f.get("summary") or "").strip()
                        if summ and not summ.lower().startswith("ai:"):
                            summ = "ai: " + summ
                        # 限制 500 字（保留换行以便弹窗阅读）
                        if summ:
                            txt = summ.strip()
                            if len(txt) > 520:
                                txt = txt[:500] + "…"
                            it["summary"] = txt
                            it["summary_origin"] = feature_origin
                            it["derived"]["tone"] = f.get("tone") or it["derived"].get("tone")
                            it["derived"]["key_points"] = f.get("key_points") or []
                            it["derived"]["comment"] = f.get("comment") or ""
                            _cache_set(db, f"minutes:{it['id']}", {
                                "summary": txt,
                                "summary_origin": feature_origin,
                                "tone": it["derived"]["tone"],
                                "key_points": it["derived"]["key_points"],
                                "comment": it["derived"]["comment"],
                            })
                        else:
                            local = _summarize_locally(it.get("content_text") or "")
                            it["summary"] = local
                            it["summary_origin"] = "fallback"
                            _cache_set(db, f"minutes:{it['id']}", {"summary": local, "summary_origin": "fallback", "tone": it["derived"]["tone"]})
                else:
                    for it in out:
                        if it.get("summary"):
                            continue
                        local = _summarize_locally(it.get("content_text") or "")
                        it["summary"] = local
                        it["summary_origin"] = "fallback"
                        _cache_set(db, f"minutes:{it['id']}", {"summary": local, "summary_origin": "fallback", "tone": it["derived"]["tone"]})
            except Exception:
                for it in out:
                    local = _summarize_locally(it.get("content_text") or "")
                    it["summary"] = local
                    it["summary_origin"] = "fallback"
                    _cache_set(db, f"minutes:{it['id']}", {"summary": local, "summary_origin": "fallback", "tone": it["derived"]["tone"]})
        return {"items": out, "total": len(out), "dirs": _default_minutes_dirs()}
    finally:
        db.close()


@router.post("/create")
def create_minutes(payload: dict) -> dict:
    """手动创建会议纪要（粘贴文本）到 data/minutes/manual/ 下。"""
    if not isinstance(payload, dict):
        return {"ok": False, "error": "invalid payload"}
    title = str(payload.get("title") or "").strip()
    content = str(payload.get("content") or "").strip()
    time_s = str(payload.get("time") or "").strip()
    if not content:
        return {"ok": False, "error": "content required"}

    dt = _parse_dt_str(time_s) if time_s else None
    if not dt:
        dt = datetime.now()
    ts = dt.strftime("%Y-%m-%d_%H%M")
    safe_title = _safe_filename(title or "会议纪要")
    filename = f"{ts}_{safe_title}.md"
    out_dir = _manual_minutes_dir()
    path = os.path.join(out_dir, filename)

    # Avoid overwrite
    if os.path.exists(path):
        path = os.path.join(out_dir, f"{ts}_{safe_title}_{int(datetime.now().timestamp())}.md")

    header = ""
    if title:
        header = f"# {title}\n\n"
    meta_line = f"时间：{dt.strftime('%Y-%m-%d %H:%M')}\n\n"
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(header + meta_line + content.strip() + "\n")
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    try:
        st = os.stat(path)
        mid = _hash_id(path, st.st_mtime)
    except Exception:
        mid = ""
    return {"ok": True, "id": mid, "path": path}


@router.post("/upload")
def upload_minutes(
    file: UploadFile = File(...),
    title: str | None = Form(None),
    time: str | None = Form(None),
) -> dict:
    """导入文本文件(.txt/.md)到 data/minutes/manual/ 下。"""
    fn = (file.filename or "").strip()
    ext = os.path.splitext(fn)[1].lower()
    if ext not in TEXT_EXTS:
        return {"ok": False, "error": f"unsupported file type: {ext or 'unknown'}"}

    dt = _parse_dt_str(time) if time else None
    if not dt:
        dt = datetime.now()
    ts = dt.strftime("%Y-%m-%d_%H%M")

    base_name = _safe_filename(title or os.path.splitext(fn)[0] or "会议纪要")
    out_dir = _manual_minutes_dir()
    path = os.path.join(out_dir, f"{ts}_{base_name}{ext}")
    if os.path.exists(path):
        path = os.path.join(out_dir, f"{ts}_{base_name}_{int(datetime.now().timestamp())}{ext}")
    try:
        raw = file.file.read()
        with open(path, "wb") as f:
            f.write(raw)
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

    try:
        st = os.stat(path)
        mid = _hash_id(path, st.st_mtime)
    except Exception:
        mid = ""
    return {"ok": True, "id": mid, "path": path}


@router.post("/refine")
def refine_minutes(payload: dict) -> dict:
    """将会议转写整理为结构化会议记录（LLM，可缓存）。"""
    mid = str(payload.get("id") or "").strip()
    if not mid:
        return {"ok": False, "error": "id required"}
    db: Session = SessionLocal()
    try:
        cache_key = f"minutes:{mid}"
        cached = _cache_get(db, cache_key)
        if cached and isinstance(cached, dict):
            refined_cached = cached.get("content_refined") or cached.get("refined")
            if isinstance(refined_cached, str) and refined_cached.strip():
                return {"ok": True, "id": mid, "content_refined": refined_cached.strip(), "origin": cached.get("refined_origin") or "tool"}

        # locate item
        items = _collect_minutes_items(refresh=False, limit=2000)
        target = next((it for it in items if str(it.get("id")) == mid), None)
        if not target:
            return {"ok": False, "error": "not found"}
        text = str(target.get("content_text") or target.get("content") or "").strip()
        if not text:
            return {"ok": False, "error": "no transcript"}

        conf = load_ai_config()
        if not conf.get("api_key") and not bool((conf.get("desk_agent") or {}).get("enabled")):
            return {"ok": False, "error": "AI 或 Desk Agent 未配置"}

        trimmed = _truncate_for_llm(text, max_chars=20000)
        model_ovr = conf.get("tool_model_messages") or conf.get("tool_model")
        feats = extract_message_features(
            [{"id": mid, "time": target.get("time"), "sender": target.get("sender_name"), "content": trimmed}],
            batch_size=1,
            concurrency=1,
            temperature=0.2,
            prompt_key="minutes_refine",
            model_override=model_ovr,
            route_key="minutes",
        )
        f = feats.get(mid) or {}
        refined = str(f.get("refined") or "").strip()
        if not refined:
            # fallback: use summary as a last resort (strip ai prefix)
            refined = str(f.get("summary") or "").strip()
            refined = re.sub(r"^\s*ai:\s*", "", refined, flags=re.IGNORECASE).strip()

        if not refined:
            return {"ok": False, "error": "refine failed"}

        _cache_set(db, cache_key, {"content_refined": refined, "refined_origin": "tool", "refined_status": "done"})
        return {"ok": True, "id": mid, "content_refined": refined, "origin": "tool"}
    finally:
        db.close()
