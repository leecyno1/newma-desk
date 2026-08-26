from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError
from sqlalchemy import select
from sqlalchemy import text as _sql_text
from typing import List, Any
from collections import OrderedDict
from datetime import datetime, timedelta
import base64
from ..db import SessionLocal
from ..models import Message, Task, Report, ReportArtifact, SyncState, Contact
from ..schemas import AIReplyRequest, TaskOut
from ..services.n8n_client import N8NClient
from ..services.llm_client import (
    DASHENG_CLOUD_API_URL,
    DASHENG_CLOUD_MAIN_MODEL,
    DASHENG_CLOUD_ONEPAGE_MODEL,
    DASHENG_CLOUD_PROVIDER_NAME,
    DASHENG_CLOUD_TOOL_MODEL,
    load_ai_config,
    save_ai_config,
    siliconflow_chat,
    siliconflow_tool_chat,
    resolve_chat_targets,
    get_router_runtime_stats,
    reset_router_runtime_stats,
    DEFAULT_MODULE_PROMPTS,
    DEFAULT_TOOL_PROMPTS,
)
from ..services import llm_client as llm_client_service
from ..services.ai_tools import extract_message_features, build_ai_input_messages
from ..services.report_artifacts import build_artifact_payloads
from ..services.snapshot_service import upsert_snapshot
from ..services.reply_generation import generate_local_reply
import os
import subprocess

# 媒体采集器数据源 — 运行时按需加载
try:
    from ..services.media_collector_store import list_all_items as _list_collector_items
except Exception:
    _list_collector_items = None

import time
import threading
from urllib.parse import urlparse


def _commit_with_retry(
    db: Session,
    *,
    retries: int = 18,
    base_delay: float = 0.2,
    objects: list[Any] | None = None,
) -> None:
    """SQLite may transiently raise 'database is locked' under concurrent access; retry commits briefly."""
    last: Exception | None = None
    tracked = [obj for obj in (objects or []) if obj is not None]
    for attempt in range(max(1, retries)):
        try:
            db.commit()
            return
        except OperationalError as exc:
            db.rollback()
            for obj in tracked:
                try:
                    db.add(obj)
                except Exception:
                    pass
            last = exc
            msg_parts = [str(exc)]
            try:
                if getattr(exc, "orig", None):
                    msg_parts.append(str(exc.orig))
            except Exception:
                pass
            msg = " | ".join(msg_parts).lower()
            if "database is locked" in msg or "locked" in msg:
                # Use bounded exponential backoff to survive short write storms.
                sleep_s = min(0.9, base_delay * (1.45 ** attempt))
                time.sleep(max(0.05, sleep_s))
                continue
            raise
    if last:
        raise last
from hashlib import sha1
import html
import json
import re
import requests
from ..services.quant_analysis import normalize_quant, render_quant_section_markdown


router = APIRouter(prefix="/api/ai", tags=["ai"]) 


def _sanitize_wechatpad_ws_url(value: Any) -> str:
    url = str(value or "").strip()
    lowered = url.lower()
    if (
        not url
        or "{wxid}" in lowered
        or "60.205.58.39:8088" in lowered
        or "getsyncmsg" in lowered
        or not lowered.startswith(("ws://", "wss://"))
    ):
        return ""
    return url


def _desk_agent_request_options(base_url: str) -> dict[str, Any]:
    """Keep local Desk calls on loopback instead of the user's HTTP proxy."""
    host = urlparse(base_url).hostname
    if host in {"127.0.0.1", "localhost", "::1"}:
        return {"proxies": {"http": None, "https": None, "socks": None}}
    return {}


# 进程内 LRU 缓存：按 (snapshot_id, module, prompt_hash, temperature) 缓存模块产出
SUMMARY_CACHE_MAX = int(os.getenv("SUMMARY_CACHE_MAX", "64"))
SUMMARY_CACHE: "OrderedDict[tuple[object, str, str, float], str]" = OrderedDict()
SUMMARY_PENDING_TIMEOUT_SECONDS = max(60, int(os.getenv("SUMMARY_PENDING_TIMEOUT_SECONDS", "1800")))
SUMMARY_RUN_LOCK = threading.Lock()
SUMMARY_RUN_STATE: dict[str, Any] = {"task_id": None, "started_at": 0.0}


def _sanitize_secret_value(value: Any) -> tuple[Any, bool]:
    text = str(value or "").strip()
    if not text:
        return "", False
    return "", True


def _sanitize_model_router_for_ui(router_conf: Any) -> Any:
    if isinstance(router_conf, list):
        return [_sanitize_model_router_for_ui(item) for item in router_conf]
    if not isinstance(router_conf, dict):
        return router_conf

    sanitized: dict[str, Any] = {}
    for key, value in router_conf.items():
        lowered = str(key).lower()
        if lowered in {"api_key", "token", "auth_token", "secret"}:
            masked, has_value = _sanitize_secret_value(value)
            sanitized[key] = masked
            sanitized[f"has_{key}"] = has_value
            continue
        sanitized[key] = _sanitize_model_router_for_ui(value)
    return sanitized

def _summary_cache_get(key: tuple) -> str | None:
    try:
        val = SUMMARY_CACHE.get(key)
        if val is not None:
            try:
                del SUMMARY_CACHE[key]
            except Exception:
                pass
            SUMMARY_CACHE[key] = val
        return val
    except Exception:
        return None

def _summary_cache_set(key: tuple, value: str) -> None:
    try:
        if key in SUMMARY_CACHE:
            del SUMMARY_CACHE[key]
        SUMMARY_CACHE[key] = value
        while len(SUMMARY_CACHE) > max(1, SUMMARY_CACHE_MAX):
            try:
                SUMMARY_CACHE.popitem(last=False)
            except Exception:
                break
    except Exception:
        pass


def _empty_summary_report(modules: list[str] | None = None, text: str = "") -> dict[str, str]:
    field_map = {
        "market": "market_markdown",
        "meetings": "meetings_markdown",
        "counter": "counter_markdown",
        "contacts": "top_contacts_markdown",
        "newswatch": "newswatch_markdown",
        "socialwatch": "socialwatch_markdown",
        "mediawatch": "mediawatch_markdown",
        "mpwatch": "mpwatch_markdown",
        "minuteswatch": "minuteswatch_markdown",
    }
    report = {
        "market_markdown": "",
        "meetings_markdown": "",
        "counter_markdown": "",
        "top_contacts_markdown": "",
        "market_html": "",
        "meetings_html": "",
        "counter_html": "",
        "top_contacts_html": "",
        "newswatch_markdown": "",
        "socialwatch_markdown": "",
        "mediawatch_markdown": "",
        "mpwatch_markdown": "",
        "minuteswatch_markdown": "",
    }
    for module in modules or []:
        field = field_map.get(module)
        if field:
            report[field] = text
    return report


def _load_latest_summary_report(db: Session) -> dict[str, Any] | None:
    try:
        latest = db.scalars(select(Report).where(Report.status == "done").order_by(Report.id.desc()).limit(1)).first()
        if latest and latest.result_body:
            parsed = json.loads(latest.result_body)
            if isinstance(parsed, dict):
                return parsed
    except Exception:
        return None
    return None


def _mark_stale_summary_tasks(
    db: Session,
    *,
    timeout_seconds: int | None = None,
    now: datetime | None = None,
) -> list[int]:
    timeout = max(60, int(timeout_seconds or SUMMARY_PENDING_TIMEOUT_SECONDS))
    current = now or datetime.utcnow()
    cutoff = current - timedelta(seconds=timeout)
    stale_ids: list[int] = []
    try:
        rows = db.scalars(select(Task).where(Task.type == "summary", Task.status == "pending")).all()
    except Exception:
        return stale_ids

    for row in rows:
        created_at = row.created_at or current
        if created_at > cutoff:
            continue
        row.status = "failed"
        row.updated_at = current
        result = row.result if isinstance(row.result, dict) else {}
        row.result = {
            **result,
            "status": "error",
            "error": "stale_summary_task_timeout",
            "detail": f"summary task exceeded {timeout} seconds and was recycled",
            "task_id": row.id,
        }
        db.add(row)
        stale_ids.append(int(row.id))

    if stale_ids:
        _commit_with_retry(db, objects=rows)
    return stale_ids


def _latest_pending_summary_task(db: Session) -> Task | None:
    try:
        return db.scalars(
            select(Task).where(Task.type == "summary", Task.status == "pending").order_by(Task.id.desc()).limit(1)
        ).first()
    except Exception:
        return None


def _build_summary_busy_result(db: Session, *, modules: list[str], active_task: Task | None = None) -> dict[str, Any]:
    cached_report = _load_latest_summary_report(db) or _empty_summary_report(modules)
    active_id = int(getattr(active_task, "id", 0) or 0) or SUMMARY_RUN_STATE.get("task_id")
    started_at = float(SUMMARY_RUN_STATE.get("started_at") or 0.0)
    elapsed = max(0, int(time.time() - started_at)) if started_at else None
    return {
        "status": "ok",
        "report": cached_report,
        "modules": modules,
        "meta": {
            "busy": True,
            "active_task_id": active_id,
            "elapsed_seconds": elapsed,
            "message": "已有一项 AI 总结正在运行，已回退到最近一次可用结果。",
        },
    }


def _persist_task_status(task_id: int, *, status: str, result: dict[str, Any] | None) -> dict[str, Any] | None:
    try:
        db = SessionLocal()
        try:
            task = db.get(Task, int(task_id))
            if not task:
                return None
            task.status = status
            task.result = result
            task.updated_at = datetime.utcnow()
            db.add(task)
            _commit_with_retry(db, objects=[task])
            db.refresh(task)
            return {"id": int(task.id), "type": str(task.type), "status": str(task.status), "result": task.result}
        finally:
            db.close()
    except Exception:
        return None


def _chat_with_retry(chat_fn, *, max_retries: int = 3, backoff: float = 1.0) -> str | dict:
    """Wrap siliconflow_chat with exponential-backoff retry; returns {\"__error__\": ...} on all failures."""
    errors: list[str] = []
    for attempt in range(max_retries):
        try:
            return chat_fn()
        except Exception as exc:
            errors.append(f"attempt_{attempt + 1}: {exc}")
            if attempt < max_retries - 1:
                time.sleep(backoff * (2 ** attempt))
    return {"__error__": "; ".join(errors)}


def _build_snap_version(snap_id: str, module_key: str, cache_db: Session | None) -> str:
    """Append snapshot message_count + updated_at to snap_id so cache key is version-aware.
    This ensures new messages automatically invalidate old cache for non-external modules.
    External modules (mediawatch/mpwatch/minuteswatch) handle versioning via source_rev separately.
    """
    if module_key in {"mediawatch", "mpwatch", "minuteswatch"}:
        return snap_id  # versioned via source_rev, caller handles this
    try:
        from ..models import AnalysisSnapshot
        if cache_db is not None:
            snap = cache_db.get(AnalysisSnapshot, snap_id)
        else:
            snap = None
        if snap is None:
            from ..db import SessionLocal as _SL
            dbx = _SL()
            try:
                snap = dbx.get(AnalysisSnapshot, snap_id)
            finally:
                dbx.close()
        if snap is not None:
            ts = int(snap.updated_at.timestamp()) if snap.updated_at else 0
            return f"{snap_id}:v{snap.message_count}:{ts}"
    except Exception:
        pass
    return snap_id



def _strip_llm_thoughts(text: str) -> str:
    if not isinstance(text, str):
        return text
    cleaned = text
    cleaned = re.sub(r"<think>[\s\S]*?</think>", "", cleaned, flags=re.IGNORECASE)
    for marker in ("<section", "<article", "<div", "<table", "<ol", "<ul", "<p>"):
        idx = cleaned.lower().find(marker)
        if idx > 0:
            cleaned = cleaned[idx:]
            break
    lines = cleaned.splitlines()
    filtered: list[str] = []
    skipping = True
    trigger_keywords = ("思考", "推理", "分析", "chain of thought", "reasoning")
    for line in lines:
        stripped = line.strip()
        if skipping:
            if not stripped:
                continue
            lower = stripped.lower()
            if any(keyword in lower for keyword in trigger_keywords) and not stripped.startswith("<"):
                continue
            skipping = False
        filtered.append(line)
    cleaned = "\n".join(filtered).lstrip()
    return cleaned


def _unwrap_markdown_payload(text: str) -> tuple[str | None, str | None, dict | None]:
    """Try to parse LLM output shaped as JSON payload and extract markdown/html/quant.

    Models sometimes return:
    - raw JSON string: {"markdown":"...","quant":{...}}
    - fenced JSON block
    - JSON embedded in extra prose
    This helper extracts structured fields when possible, otherwise returns (None, None, None).
    """
    if not isinstance(text, str):
        return None, None, None
    raw = text.strip()
    if not raw:
        return None, None, None

    # strip fenced code blocks like ```json ... ```
    if raw.startswith("```"):
        lines = raw.splitlines()
        if len(lines) >= 2:
            first = lines[0].strip().lower()
            if first.startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            raw = "\n".join(lines).strip()

    parsed: dict | None = None
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            parsed = obj
    except Exception:
        parsed = None

    # loose parse from first "{" to last "}" when model adds leading/trailing prose
    if parsed is None:
        try:
            s = raw.find("{")
            e = raw.rfind("}")
            if s >= 0 and e > s:
                obj = json.loads(raw[s : e + 1])
                if isinstance(obj, dict):
                    parsed = obj
        except Exception:
            parsed = None

    if not isinstance(parsed, dict):
        return None, None, None

    md = parsed.get("markdown")
    html_v = parsed.get("html")
    quant_v = parsed.get("quant")
    md_out = str(md) if isinstance(md, str) else None
    html_out = str(html_v) if isinstance(html_v, str) else None
    quant_out = quant_v if isinstance(quant_v, dict) else None
    if md_out is None and html_out is None:
        return None, None, None
    return md_out, html_out, quant_out


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _render_template(tpl: str, ctx: dict[str, Any]) -> str:
    out = tpl or ""
    for k, v in (ctx or {}).items():
        out = out.replace("{{" + k + "}}", str(v if v is not None else ""))
    return out


@router.post("/suggest-replies", response_model=TaskOut)
def suggest_replies(body: AIReplyRequest, db: Session = Depends(get_db)):
    msgs: List[Message] = db.scalars(select(Message).where(Message.id.in_(body.message_ids))).all()
    if not msgs:
        raise HTTPException(400, "no messages found")

    ctx = {
        "request_id": f"reply-{','.join(map(str, body.message_ids))}",
        "context": {
            "messages": [
                {
                    "id": m.id,
                    "text": m.content_text,
                    "sender": m.sender_name or m.sender_id,
                    "ts": m.timestamp.isoformat() if m.timestamp else None,
                }
                for m in msgs
            ]
        },
        "prompt_hint": body.prompt_hint,
    }

    task = Task(type="ai_reply", payload=ctx, status="pending")
    db.add(task)
    db.commit()
    db.refresh(task)

    client = N8NClient()
    try:
        result = client.suggest_replies(ctx)
        task.status = "done"
        task.result = result
        db.add(task)
        db.commit()
        db.refresh(task)
    except Exception as e:
        db.rollback()
        task.status = "failed"
        task.result = {"error": str(e)}
        db.add(task)
        db.commit()
        db.refresh(task)

    return TaskOut(id=task.id, type=task.type, status=task.status, result=task.result)


@router.post("/reply-local")
def reply_local(payload: dict, db: Session = Depends(get_db)) -> dict:
    """Generate a single reply locally using SiliconFlow + tool prompt keys (reply_*)."""
    return generate_local_reply(db, payload if isinstance(payload, dict) else {})


@router.post("/mass-generate")
def mass_generate(payload: dict):
    """Generate a short mass-send template text.

    Returns {text: string}. The template should include `{name}` placeholder.
    """
    instruction = str((payload or {}).get("instruction") or "").strip()
    if not instruction:
        raise HTTPException(400, "instruction required")
    conf = load_ai_config()
    tool_model = conf.get("tool_model") or "Qwen/Qwen3-8B"
    messages = [
        {
            "role": "system",
            "content": "\n".join(
                [
                    "你是微信群发文案助手。",
                    "你将生成一段可直接发送的群发消息模板，必须包含 {name} 占位符用于个性化称呼。",
                    "输出要求：纯文本；不要 Markdown；不要代码块；不要多余解释。",
                    "内容要求：专业礼貌、简短清晰、避免营销腔、避免夸张。",
                ]
            ),
        },
        {
            "role": "user",
            "content": "\n".join(
                [
                    f"需求：{instruction}",
                    "请只输出一段模板文本，必须包含 {name}。",
                ]
            ),
        },
    ]
    try:
        text = siliconflow_chat(
            messages,
            temperature=0.2,
            model_override=tool_model,
            force_json=False,
            route_kind="tool",
            route_key="reply",
        )
    except Exception as e:
        return {"error": str(e)}
    text = (text or "").strip()
    # defensive: strip fenced blocks if any
    if text.startswith("```"):
        text = text.strip("`").strip()
    return {"text": text}


@router.post("/summary", response_model=TaskOut)
def summary(payload: dict, db: Session = Depends(get_db)):
    message_ids_raw = payload.get("message_ids") or []
    if not isinstance(message_ids_raw, list):
        message_ids_raw = [message_ids_raw]
    message_ids: list[int] = []
    for mid in message_ids_raw:
        try:
            if mid is None:
                continue
            message_ids.append(int(mid))
        except (ValueError, TypeError):
            continue

    filters = payload.get("filters") or {}
    options = payload.get("options") or {"format": "markdown"}
    prompts = payload.get("prompts") or {}
    # 前端为准：若本次请求携带了提示词，立刻与后端配置合并并持久化，保证后端保持同步
    try:
        if isinstance(prompts, dict) and prompts:
            _conf = load_ai_config()
            stored = _conf.get("module_prompts", {}) or {}
            for key, val in prompts.items():
                if key not in DEFAULT_MODULE_PROMPTS:
                    continue
                if not isinstance(val, dict):
                    continue
                cur = stored.get(key, {}) if isinstance(stored.get(key), dict) else {}
                upd = cur.copy()
                if isinstance(val.get("system"), str):
                    upd["system"] = val.get("system")
                if isinstance(val.get("user"), str):
                    upd["user"] = val.get("user")
                stored[key] = upd
            _conf["module_prompts"] = stored
            save_ai_config(_conf)
    except Exception:
        # 持久化失败不阻断主流程
        pass
    module_candidates = payload.get("modules")
    ALLOWED_MODULES = {"market", "meetings", "counter", "contacts", "newswatch", "socialwatch", "mediawatch", "mpwatch", "minuteswatch"}
    if isinstance(module_candidates, list) and module_candidates:
        modules = [m for m in module_candidates if m in ALLOWED_MODULES]
    else:
        modules = options.get("modules") or []
        if isinstance(modules, list):
            modules = [m for m in modules if m in ALLOWED_MODULES]
        else:
            modules = []
    if not modules:
        modules = ["market", "meetings", "counter", "contacts", "newswatch", "mediawatch", "mpwatch", "minuteswatch", "socialwatch"]
    temperature = options.get("temperature") if isinstance(options, dict) else None
    try:
        temperature = float(temperature) if temperature is not None else None
    except Exception:
        temperature = None
    concurrency = options.get("concurrency") if isinstance(options, dict) else None
    try:
        concurrency = int(concurrency) if concurrency is not None else None
    except Exception:
        concurrency = None
    force_snapshot = bool(options.get("force_snapshot", True)) if isinstance(options, dict) else True

    options = {**options, "modules": modules, "temperature": temperature, "concurrency": concurrency, "force_snapshot": force_snapshot}

    _mark_stale_summary_tasks(db)
    lock_acquired = SUMMARY_RUN_LOCK.acquire(blocking=False)
    if not lock_acquired:
        active_task = _latest_pending_summary_task(db)
        busy_result = _build_summary_busy_result(db, modules=modules, active_task=active_task)
        return TaskOut(
            id=int(getattr(active_task, "id", 0) or 0),
            type="summary",
            status="pending",
            result=busy_result,
        )

    ctx = {
        "request_id": "summary-task",
        "scope": {"message_ids": message_ids, "filters": filters},
        "options": options,
        "prompts": prompts,
        "modules": modules,
    }

    task = Task(type="summary", payload=ctx, status="pending")
    response_status = "failed"
    response_result: dict[str, Any] | None = None
    try:
        db.add(task)
        _commit_with_retry(db, objects=[task])
        db.refresh(task)
        SUMMARY_RUN_STATE["task_id"] = int(task.id)
        SUMMARY_RUN_STATE["started_at"] = time.time()

        external_modules = {"mediawatch", "mpwatch", "minuteswatch"}
        external_only = bool(modules) and set(modules).issubset(external_modules)

        snapshot = None
        if not external_only:
            snapshot = upsert_snapshot(
                db,
                message_ids=message_ids,
                filters=filters,
                options=options,
            )
            db.flush()

        contacts_full: dict[str, dict[str, Any]] = {}
        contact_ratings_simple: dict[str, Any] = {}
        if not external_only:
            # 高评分联系人完全以联系人管理表为准，忽略任何模型/缓存生成的评分
            try:
                rows = db.scalars(select(Contact)).all()
            except Exception:
                rows = []
            for contact in rows:
                cid = str(contact.id)
                contacts_full[cid] = {
                    "cid": cid,
                    "rating": float(contact.rating) if contact.rating is not None else None,
                    "name": contact.name,
                    "alias": contact.alias,
                    "labels": contact.labels or {},
                }
            for key, data in contacts_full.items():
                rating_val = data.get("rating")
                if rating_val is None:
                    continue
                try:
                    contact_ratings_simple[str(key)] = float(rating_val)
                except Exception:
                    continue

        # 保存原始数据集文件，供大模型完整读取与审计（按渠道分组）
        ds_path = None
        ds_dir = None
        if not external_only and snapshot is not None:
            try:
                ds_dir = os.path.abspath(os.path.join(os.getcwd(), "data", "datasets"))
                os.makedirs(ds_dir, exist_ok=True)
                ds_name = f"messages_{(filters or {}).get('period') or 'custom'}_{snapshot.id}.json"
                ds_path = os.path.join(ds_dir, ds_name)
                # 精简版数据集：仅保留对总结有用的最小字段，避免无关信息（邮件地址、链接、附件等）造成体积膨胀
                def _slim(m: dict) -> dict:
                    return {
                        "id": m.get("id"),
                        "time": m.get("time") or m.get("timestamp"),
                        "sender": m.get("sender_name") or m.get("sender_id"),
                        "talker": m.get("talker_name") or m.get("chat_id"),
                        "type": m.get("message_type") or m.get("type"),
                        "content": m.get("content") or m.get("content_text") or m.get("text"),
                    }
                by_channel: dict[str, list] = {}
                for m in (snapshot.messages or []):
                    ch = str((m or {}).get("channel") or "wechat")
                    by_channel.setdefault(ch, []).append(_slim(m))
                dataset = {
                    "period": (filters or {}).get("period") if filters else None,
                    "counts": {k: len(v) for k, v in by_channel.items()},
                    "channels": by_channel,
                }
                with open(ds_path, "w", encoding="utf-8") as f:
                    json.dump(dataset, f, ensure_ascii=False, indent=2)
            except Exception:
                ds_path = None

        # 创建摘要数据库（包含微信和邮件的摘要内容）
        summary_db_path = None
        if not external_only and snapshot is not None and ds_dir:
            try:
                summary_db_name = f"summaries_{(filters or {}).get('period') or 'custom'}_{snapshot.id}.json"
                summary_db_path = os.path.join(ds_dir, summary_db_name)

                wechat_summaries = []
                email_summaries = []

                for m in (snapshot.messages or []):
                    channel = str((m or {}).get("channel") or "wechat")
                    derived = m.get("derived") or {}
                    summary = derived.get("summary") or ""

                    if summary:
                        if summary.lower().startswith("ai:"):
                            summary = summary[3:].strip()
                        elif summary.lower().startswith("fallback:"):
                            summary = summary[9:].strip()

                    if not summary:
                        continue

                    summary_item = {
                        "id": m.get("id"),
                        "time": m.get("time") or m.get("timestamp"),
                        "sender": m.get("sender_name") or m.get("sender_id"),
                        "talker": m.get("talker_name") or m.get("chat_id"),
                        "summary": summary,
                        "tone": derived.get("tone"),
                        "category": derived.get("category"),
                    }

                    if channel == "email":
                        email_summaries.append(summary_item)
                    else:
                        wechat_summaries.append(summary_item)

                summary_dataset = {
                    "period": (filters or {}).get("period") if filters else None,
                    "snapshot_id": snapshot.id,
                    "counts": {
                        "wechat": len(wechat_summaries),
                        "email": len(email_summaries),
                    },
                    "wechat_summaries": wechat_summaries,
                    "email_summaries": email_summaries,
                }

                with open(summary_db_path, "w", encoding="utf-8") as f:
                    json.dump(summary_dataset, f, ensure_ascii=False, indent=2)
            except Exception:
                summary_db_path = None

        summary_payload = {
            "messages": [] if external_only else (snapshot.messages or []),
            "prompts": prompts,
            "contact_ratings": contact_ratings_simple,
            "contact_details": contacts_full,
            "meta": {} if external_only else (snapshot.meta or {}),
            "modules": modules,
            "temperature": temperature,
            "dataset_path": ds_path,
            "summary_db_path": summary_db_path,  # 新增：摘要数据库路径，可用于验证从摘要表提取总结的方法
            "snapshot_id": f"external:{(filters or {}).get('period') or 'custom'}" if external_only else snapshot.id,
            "_cache_db": db,
        }

        local_summary = _run_summary_local(summary_payload)
        status = local_summary.get("status", "error")
        summary_result = local_summary.get("result") or {}
        returned_modules = local_summary.get("modules") or modules

        artifact_payloads = build_artifact_payloads(summary_result) if status == "ok" else []

        time_range = None
        if snapshot is not None and snapshot.time_from and snapshot.time_to:
            time_range = f"{snapshot.time_from.isoformat()} ~ {snapshot.time_to.isoformat()}"

        if status == "ok":
            rep = Report(
                title="AI 报告",
                time_range=time_range,
                filters=filters,
                status="done",
                result_type="json",
                result_body=json.dumps(summary_result, ensure_ascii=False),
            )
            for art_payload in artifact_payloads:
                rep.artifacts.append(ReportArtifact(**art_payload))
            db.add(rep)

        response_status = "done" if status == "ok" else "failed"
        response_result = {
            "status": status,
            "snapshot_id": summary_payload.get("snapshot_id"),
            "report": summary_result,
            "meta": {**((snapshot.meta or {}) if snapshot is not None else {}), **({"time_range": time_range} if time_range else {})},
            "modules": returned_modules,
            "options": {
                "modules": returned_modules,
                "temperature": temperature,
                "concurrency": concurrency,
                "force_snapshot": force_snapshot,
            },
        }
        if artifact_payloads:
            response_result["artifacts"] = artifact_payloads
        try:
            tracked_objects: list[Any] = []
            if status == "ok":
                tracked_objects.append(rep)
            _commit_with_retry(db, objects=tracked_objects)
        except Exception as persist_exc:
            warnings = response_result.setdefault("warnings", [])
            if isinstance(warnings, list):
                warnings.append(f"report_persist_warning: {persist_exc}")
    except Exception as e:
        db.rollback()
        response_status = "failed"
        response_result = {"status": "error", "error": str(e)}
    finally:
        persisted = _persist_task_status(int(getattr(task, "id", 0) or 0), status=response_status, result=response_result)
        SUMMARY_RUN_STATE["task_id"] = None
        SUMMARY_RUN_STATE["started_at"] = 0.0
        SUMMARY_RUN_LOCK.release()

    if persisted:
        return TaskOut(**persisted)
    return TaskOut(
        id=int(getattr(task, "id", 0) or 0),
        type="summary",
        status=response_status,
        result=response_result,
    )


@router.get("/config")
def get_ai_config():
    conf = load_ai_config()
    desk_agent_conf = conf.get("desk_agent") if isinstance(conf.get("desk_agent"), dict) else {}
    # Also return UI/analysis defaults so the frontend can persist settings across restarts
    analysis_defaults = conf.get("analysis_defaults") or {}
    ui_prefs = conf.get("ui_prefs") or {}
    send_provider = str(conf.get("send_provider") or "").strip()
    if send_provider not in {"wechatpad_direct", "wechatapi_gateway"}:
        send_provider = "wechatapi_gateway"
    allow_code_digits = conf.get("mass_name_allow_code_digits")
    allow_code_digits = True if allow_code_digits is None else bool(allow_code_digits)
    ai_provider_mode = str(conf.get("ai_provider_mode") or "").strip()
    if ai_provider_mode not in {"dasheng", "custom"}:
        ai_provider_mode = "dasheng" if str(conf.get("api_url") or "").strip() == DASHENG_CLOUD_API_URL and bool(conf.get("api_key")) else "custom"
    return {
        "api_url": conf.get("api_url"),
        "model": conf.get("model"),
        "has_key": bool(conf.get("api_key")),
        "ai_provider_mode": ai_provider_mode,
        "preset_provider": {
            "name": DASHENG_CLOUD_PROVIDER_NAME,
            "api_url": DASHENG_CLOUD_API_URL,
            "main_model": DASHENG_CLOUD_MAIN_MODEL,
            "tool_model": DASHENG_CLOUD_TOOL_MODEL,
            "onepage_model": DASHENG_CLOUD_ONEPAGE_MODEL,
        },
        "main_model": conf.get("main_model") or conf.get("model"),
        "fallback_model": conf.get("fallback_model"),
        "onepage_model": conf.get("onepage_model") or DASHENG_CLOUD_ONEPAGE_MODEL,
        "tool_model": conf.get("tool_model"),
        "tool_model_messages": conf.get("tool_model_messages") or conf.get("tool_model"),
        "tool_model_emails": conf.get("tool_model_emails") or conf.get("tool_model"),
        "max_tokens": conf.get("max_tokens"),
        "model_temperature": conf.get("model_temperature"),
        # Send (WeChatPadPro) config surface for UI
        "wechatpad_http_base": conf.get("wechatpad_http_base"),
        "wechatpad_text_path": conf.get("wechatpad_text_path"),
        "wechatpad_ws_url": _sanitize_wechatpad_ws_url(conf.get("wechatpad_ws_url")),
        "wechatpad_wxid": conf.get("wechatpad_wxid"),
        "wechatpad_sync_enabled": bool(conf.get("wechatpad_sync_enabled") or False),
        "wechatpad_sync_poll_seconds": int(conf.get("wechatpad_sync_poll_seconds") or 30),
        "wechatpad_sync_ws_heartbeat_seconds": int(conf.get("wechatpad_sync_ws_heartbeat_seconds") or 30),
        # Send (wechat gateway / direct fallback) config
        "send_provider": send_provider,
        # Mass send config (persisted)
        "mass_send_targets": conf.get("mass_send_targets") or [],
        "mass_send_template": conf.get("mass_send_template") or "",
        "mass_send_throttle_ms": int(conf.get("mass_send_throttle_ms") or 1500),
        "mass_greeting_default_suffix": conf.get("mass_greeting_default_suffix") or "",
        "mass_greeting_rules": conf.get("mass_greeting_rules") or "",
        "mass_greeting_rank_map": conf.get("mass_greeting_rank_map") or "",
        "mass_name_allow_code_digits": allow_code_digits,
        "mass_honorific_default_enabled": bool(conf.get("mass_honorific_default_enabled") or False),
        "message_filters": conf.get("message_filters", {}),
        "module_prompts": conf.get("module_prompts", {}),
        "default_module_prompts": DEFAULT_MODULE_PROMPTS,
        "tool_prompts": conf.get("tool_prompts", {}),
        "default_tool_prompts": DEFAULT_TOOL_PROMPTS,
        "model_router": _sanitize_model_router_for_ui(conf.get("model_router") or {}),
        "desk_agent": {
            "enabled": bool(desk_agent_conf.get("enabled")),
            "base_url": str(desk_agent_conf.get("base_url") or "").strip(),
            "module_id": str(desk_agent_conf.get("module_id") or "deepsee-news").strip(),
            "adapter": str(desk_agent_conf.get("adapter") or "").strip(),
            "model": str(desk_agent_conf.get("model") or "").strip(),
            "command_profile": str(desk_agent_conf.get("command_profile") or "batch").strip(),
            "timeout_seconds": int(desk_agent_conf.get("timeout_seconds") or 180),
            "has_token": bool(desk_agent_conf.get("token")),
        },
        "onepage_temperature": conf.get("onepage_temperature", 0.35),
        "onepage_template_style": conf.get("onepage_template_style") or "executive_blue",
        "onepage_output_mode": conf.get("onepage_output_mode") or "auto",
        "onepage_image_api_url": conf.get("onepage_image_api_url") or "",
        "onepage_image_has_key": bool(conf.get("onepage_image_api_key") or conf.get("api_key")),
        "onepage_image_model": conf.get("onepage_image_model") or DASHENG_CLOUD_ONEPAGE_MODEL,
        "onepage_image_size": conf.get("onepage_image_size") or "1024x1536",
        "onepage_image_quality": conf.get("onepage_image_quality") or "medium",
        "onepage_prompt": _get_onepage_config(conf).get("prompt"),
        "default_onepage_prompt": _default_onepage_prompt(),
        "analysis_defaults": {
            # 默认包含新闻舆情模块（默认必出）
            "modules": analysis_defaults.get("modules") or ["market", "meetings", "counter", "contacts", "newswatch", "mediawatch", "mpwatch", "minuteswatch"],
            "concurrency": int(analysis_defaults.get("concurrency") or 32),
            "temperature": float(analysis_defaults.get("temperature") or 0.3),
            "force_snapshot": bool(analysis_defaults.get("force_snapshot") if analysis_defaults.get("force_snapshot") is not None else True),
            "last_period": analysis_defaults.get("last_period") or "1day",
        },
        "ui_prefs": ui_prefs,
        "message_filters": conf.get("message_filters", {}),
        "derive_defaults": conf.get("derive_defaults", {}),
    }


@router.get("/desk-agent/capabilities")
def get_desk_agent_capabilities():
    """Return the Desk CLI catalog without exposing its credentials.

    Deepsee owns only the batch-summary override. Discovery, executable paths,
    login state, and global concurrency remain in Newma-Desk. Keeping this as
    a same-origin proxy also lets Desk deployments that require a bearer token
    populate the Deepsee selector without putting that token in the browser.
    """
    conf = load_ai_config()
    raw = conf.get("desk_agent") if isinstance(conf.get("desk_agent"), dict) else {}
    base_url = str(raw.get("base_url") or "").strip().rstrip("/")
    if not base_url:
        return {"available": False, "adapters": [], "error": "Desk Agent 地址未配置"}
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return {"available": False, "adapters": [], "error": "Desk Agent 地址无效"}
    headers = {"Accept": "application/json"}
    token = str(raw.get("token") or "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = requests.get(
            f"{base_url}/api/capabilities",
            headers=headers,
            timeout=10,
            **_desk_agent_request_options(base_url),
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        return {
            "available": False,
            "adapters": [],
            "error": f"Desk Agent 连接失败：{str(exc)[:160]}",
        }

    adapters: list[dict[str, Any]] = []
    for item in payload.get("adapters", []) if isinstance(payload, dict) else []:
        if not isinstance(item, dict):
            continue
        adapter_id = str(item.get("id") or "").strip()
        if not adapter_id:
            continue
        adapters.append(
            {
                "id": adapter_id,
                "name": str(item.get("name") or adapter_id),
                "kind": str(item.get("kind") or ""),
                "available": bool(item.get("available")),
                "capabilities": [
                    str(capability)
                    for capability in item.get("capabilities", [])
                    if isinstance(capability, str) and capability.strip()
                ][:40],
                "models": [
                    str(model)
                    for model in item.get("models", [])
                    if isinstance(model, str) and model.strip()
                ][:100],
                "commandProfiles": [
                    str(profile)
                    for profile in item.get("commandProfiles", [])
                    if isinstance(profile, str) and profile.strip()
                ][:20],
                "commandProfileDetails": item.get("commandProfileDetails")
                if isinstance(item.get("commandProfileDetails"), dict)
                else {},
                "modelSource": str(item.get("modelSource") or ""),
                "version": str(item.get("version") or ""),
            }
        )
    return {"available": True, "adapters": adapters}


@router.post("/config")
def set_ai_config(conf: dict):
    def _merge_router_channel_secrets(existing_router: dict, incoming_router: dict) -> dict:
        merged_router = dict(incoming_router or {})
        for field in ("main_channels", "mid_channels", "tool_channels"):
            incoming_channels = merged_router.get(field)
            if not isinstance(incoming_channels, list):
                continue
            existing_channels = existing_router.get(field) if isinstance(existing_router, dict) else []
            existing_by_id: dict[str, dict] = {}
            if isinstance(existing_channels, list):
                for item in existing_channels:
                    if not isinstance(item, dict):
                        continue
                    cid = str(item.get("id") or "").strip()
                    if cid:
                        existing_by_id[cid] = item

            patched: list[dict] = []
            for item in incoming_channels:
                if not isinstance(item, dict):
                    continue
                row = dict(item)
                cid = str(row.get("id") or "").strip()
                key_text = str(row.get("api_key") or "").strip()
                keep_existing = bool(row.get("has_api_key")) and not key_text
                if keep_existing and cid:
                    old = existing_by_id.get(cid) or {}
                    old_key = str(old.get("api_key") or "").strip()
                    if old_key:
                        row["api_key"] = old_key
                row.pop("has_api_key", None)
                patched.append(row)
            merged_router[field] = patched
        return merged_router

    merged = load_ai_config()
    if "ai_provider_mode" in conf and conf["ai_provider_mode"] is not None:
        mode = str(conf.get("ai_provider_mode") or "").strip()
        if mode in {"dasheng", "custom"}:
            merged["ai_provider_mode"] = mode
    for key in (
        "api_url",
        "model",
        "main_model",
        "fallback_model",
        "onepage_model",
        "tool_model",
        "tool_model_messages",
        "tool_model_emails",
        "onepage_template_style",
    ):
        if key in conf and conf[key] is not None:
            merged[key] = conf[key]
    if "api_key" in conf and conf["api_key"] is not None:
        incoming_key = str(conf.get("api_key") or "").strip()
        preserve_existing = bool(conf.get("has_key")) and not incoming_key
        if incoming_key or not preserve_existing:
            merged["api_key"] = incoming_key
    # Allow frontend to configure WeChatPadPro endpoint without editing .env
    if "wechatpad_http_base" in conf and conf["wechatpad_http_base"] is not None:
        merged["wechatpad_http_base"] = conf["wechatpad_http_base"].strip()
    if "wechatpad_text_path" in conf and conf["wechatpad_text_path"] is not None:
        raw = str(conf["wechatpad_text_path"]).strip() or "/api/v1/message/sendText"
        # Accept user-pasted full URL (or accidental "/http://..."), store only URL path.
        candidate = raw[1:] if raw.startswith("/http://") or raw.startswith("/https://") else raw
        if candidate.startswith("http://") or candidate.startswith("https://"):
            try:
                parsed = urlparse(candidate)
                raw = parsed.path or "/"
            except Exception:
                raw = "/"
        p = raw.strip() or "/api/v1/message/sendText"
        merged["wechatpad_text_path"] = p if p.startswith("/") else "/" + p
    if "wechatpad_ws_url" in conf and conf["wechatpad_ws_url"] is not None:
        merged["wechatpad_ws_url"] = _sanitize_wechatpad_ws_url(conf["wechatpad_ws_url"])
    if "wechatpad_wxid" in conf and conf["wechatpad_wxid"] is not None:
        merged["wechatpad_wxid"] = str(conf["wechatpad_wxid"]).strip()
    if "wechatpad_sync_enabled" in conf and conf["wechatpad_sync_enabled"] is not None:
        merged["wechatpad_sync_enabled"] = bool(conf["wechatpad_sync_enabled"])
    if "wechatpad_sync_poll_seconds" in conf and conf["wechatpad_sync_poll_seconds"] is not None:
        try:
            merged["wechatpad_sync_poll_seconds"] = max(5, min(3600, int(conf["wechatpad_sync_poll_seconds"])))
        except Exception:
            pass
    if "wechatpad_sync_ws_heartbeat_seconds" in conf and conf["wechatpad_sync_ws_heartbeat_seconds"] is not None:
        try:
            merged["wechatpad_sync_ws_heartbeat_seconds"] = max(10, min(600, int(conf["wechatpad_sync_ws_heartbeat_seconds"])))
        except Exception:
            pass

    # Send provider (gateway vs direct fallback)
    if "send_provider" in conf and conf["send_provider"] is not None:
        v = str(conf.get("send_provider") or "").strip()
        if v in {"wechatpad_direct", "wechatapi_gateway"}:
            merged["send_provider"] = v

    # Mass send config
    if "mass_send_targets" in conf and conf["mass_send_targets"] is not None:
        if isinstance(conf["mass_send_targets"], list):
            # store [{id,name}] only
            cleaned: list[dict] = []
            for it in conf["mass_send_targets"][:500]:
                if not isinstance(it, dict):
                    continue
                tid = str(it.get("id") or "").strip()
                if not tid:
                    continue
                name = str(it.get("name") or "").strip()
                cleaned.append({"id": tid, "name": name})
            merged["mass_send_targets"] = cleaned
    if "mass_send_template" in conf and conf["mass_send_template"] is not None:
        merged["mass_send_template"] = str(conf["mass_send_template"])
    if "mass_send_throttle_ms" in conf and conf["mass_send_throttle_ms"] is not None:
        try:
            merged["mass_send_throttle_ms"] = max(0, min(60_000, int(conf["mass_send_throttle_ms"])))
        except Exception:
            pass
    if "mass_greeting_default_suffix" in conf and conf["mass_greeting_default_suffix"] is not None:
        merged["mass_greeting_default_suffix"] = str(conf["mass_greeting_default_suffix"]).strip()
    if "mass_greeting_rules" in conf and conf["mass_greeting_rules"] is not None:
        # store as multiline text ("keyword=suffix")
        merged["mass_greeting_rules"] = str(conf["mass_greeting_rules"])
    if "mass_greeting_rank_map" in conf and conf["mass_greeting_rank_map"] is not None:
        merged["mass_greeting_rank_map"] = str(conf["mass_greeting_rank_map"])
    if "mass_name_allow_code_digits" in conf and conf["mass_name_allow_code_digits"] is not None:
        merged["mass_name_allow_code_digits"] = bool(conf["mass_name_allow_code_digits"])
    if "mass_honorific_default_enabled" in conf and conf["mass_honorific_default_enabled"] is not None:
        merged["mass_honorific_default_enabled"] = bool(conf["mass_honorific_default_enabled"])

    # optional runtime LLM params
    if "max_tokens" in conf and conf["max_tokens"] is not None:
        merged["max_tokens"] = conf["max_tokens"]
    if "model_temperature" in conf and conf["model_temperature"] is not None:
        merged["model_temperature"] = conf["model_temperature"]
    if "desk_agent" in conf and isinstance(conf["desk_agent"], dict):
        current = merged.get("desk_agent") if isinstance(merged.get("desk_agent"), dict) else {}
        incoming = conf["desk_agent"]
        current["enabled"] = bool(incoming.get("enabled", current.get("enabled", False)))
        if "base_url" in incoming:
            current["base_url"] = str(incoming.get("base_url") or "").strip().rstrip("/")
        if "module_id" in incoming:
            current["module_id"] = str(incoming.get("module_id") or "deepsee-news").strip()
        if "adapter" in incoming:
            current["adapter"] = str(incoming.get("adapter") or "").strip()
        if "model" in incoming:
            current["model"] = str(incoming.get("model") or "").strip()
        profile_value = incoming.get(
            "command_profile",
            incoming.get("commandProfile"),
        )
        if profile_value is not None:
            profile = str(profile_value or "batch").strip()
            current["command_profile"] = profile if profile in {"quick", "batch", "deep", "edit"} else "batch"
        if "timeout_seconds" in incoming:
            try:
                current["timeout_seconds"] = max(10, min(900, int(incoming.get("timeout_seconds") or 180)))
            except Exception:
                pass
        if "token" in incoming or "has_token" in incoming:
            token = str(incoming.get("token") or "").strip()
            if token or not bool(incoming.get("has_token")):
                current["token"] = token
        merged["desk_agent"] = current
    if "message_filters" in conf and isinstance(conf["message_filters"], dict):
        mf = merged.get("message_filters") or {}
        mf.update({
            "external_only": bool(conf["message_filters"].get("external_only", mf.get("external_only", True))),
            "exclude_short": bool(conf["message_filters"].get("exclude_short", mf.get("exclude_short", True))),
            "exclude_system": bool(conf["message_filters"].get("exclude_system", mf.get("exclude_system", True))),
        })
        merged["message_filters"] = mf
    if "derive_defaults" in conf and isinstance(conf["derive_defaults"], dict):
        dd = merged.get("derive_defaults") or {}
        try:
            bs = int(conf["derive_defaults"].get("batch_size", dd.get("batch_size", 20)))
            dd["batch_size"] = max(1, min(128, bs))
        except Exception:
            pass
        try:
            cc = int(conf["derive_defaults"].get("concurrency", dd.get("concurrency", 8)))
            dd["concurrency"] = max(1, min(64, cc))
        except Exception:
            pass
        try:
            tp = float(conf["derive_defaults"].get("temperature", dd.get("temperature", 0.1)))
            dd["temperature"] = 0.0 if tp < 0 else (1.0 if tp > 1 else tp)
        except Exception:
            pass
        if "force" in conf["derive_defaults"]:
            dd["force"] = bool(conf["derive_defaults"].get("force", dd.get("force", False)))
        merged["derive_defaults"] = dd

    # Persist analysis defaults & UI preferences if provided
    if isinstance(conf.get("analysis_defaults"), dict):
        ad = merged.get("analysis_defaults") or {}
        incoming = conf["analysis_defaults"]
        if "modules" in incoming and isinstance(incoming["modules"], list):
            # keep valid modules only
            valid = {"market", "meetings", "counter", "contacts", "newswatch", "socialwatch", "mediawatch", "mpwatch", "minuteswatch"}
            ad["modules"] = [m for m in incoming["modules"] if m in valid] or ["market", "meetings", "counter", "contacts", "newswatch", "mediawatch", "mpwatch", "minuteswatch"]
        if "concurrency" in incoming:
            try:
                ad["concurrency"] = max(1, min(128, int(incoming["concurrency"])) )
            except Exception:
                pass
        if "temperature" in incoming:
            try:
                t = float(incoming["temperature"])  # 0..1
                ad["temperature"] = 0.0 if t < 0 else (1.0 if t > 1 else t)
            except Exception:
                pass
        if "force_snapshot" in incoming:
            ad["force_snapshot"] = bool(incoming["force_snapshot"])  # type: ignore[truthy-bool]
        if "last_period" in incoming:
            last = str(incoming["last_period"]).lower()
            if last in {"1day", "3days", "1week", "1month"}:
                ad["last_period"] = last
        merged["analysis_defaults"] = ad

    if isinstance(conf.get("ui_prefs"), dict):
        up = merged.get("ui_prefs") or {}
        up.update({k: v for k, v in conf["ui_prefs"].items()})
        merged["ui_prefs"] = up

    if "onepage_temperature" in conf:
        try:
            t = float(conf.get("onepage_temperature") or 0.35)
            merged["onepage_temperature"] = 0.0 if t < 0 else (1.0 if t > 1 else t)
        except Exception:
            pass
    if "onepage_output_mode" in conf and conf["onepage_output_mode"] is not None:
        mode = str(conf.get("onepage_output_mode") or "").strip().lower()
        if mode in {"auto", "image", "local"}:
            merged["onepage_output_mode"] = mode
    if "onepage_image_api_url" in conf and conf["onepage_image_api_url"] is not None:
        merged["onepage_image_api_url"] = str(conf.get("onepage_image_api_url") or "").strip()
    if "onepage_image_api_key" in conf and conf["onepage_image_api_key"] is not None:
        incoming_image_key = str(conf.get("onepage_image_api_key") or "").strip()
        preserve_existing_image_key = bool(conf.get("onepage_image_has_key")) and not incoming_image_key
        if incoming_image_key or not preserve_existing_image_key:
            merged["onepage_image_api_key"] = incoming_image_key
    if "onepage_image_model" in conf and conf["onepage_image_model"] is not None:
        merged["onepage_image_model"] = str(conf.get("onepage_image_model") or "").strip() or DASHENG_CLOUD_ONEPAGE_MODEL
    if "onepage_image_size" in conf and conf["onepage_image_size"] is not None:
        size = str(conf.get("onepage_image_size") or "").strip()
        if size in {"1024x1024", "1024x1536", "1536x1024"}:
            merged["onepage_image_size"] = size
    if "onepage_image_quality" in conf and conf["onepage_image_quality"] is not None:
        quality = str(conf.get("onepage_image_quality") or "").strip().lower()
        if quality in {"low", "medium", "high", "auto"}:
            merged["onepage_image_quality"] = quality
    if "onepage_prompt" in conf and isinstance(conf["onepage_prompt"], dict):
        current = merged.get("onepage_prompt") if isinstance(merged.get("onepage_prompt"), dict) else {}
        updated = dict(current)
        incoming = conf["onepage_prompt"]
        if isinstance(incoming.get("system"), str):
            updated["system"] = incoming.get("system")
        if isinstance(incoming.get("user"), str):
            updated["user"] = incoming.get("user")
        merged["onepage_prompt"] = updated

    if "module_prompts" in conf and isinstance(conf["module_prompts"], dict):
        stored = merged.get("module_prompts", {})
        incoming = conf["module_prompts"]
        for module, prompts in incoming.items():
            if module not in DEFAULT_MODULE_PROMPTS:
                continue
            current = stored.get(module, {})
            if not isinstance(current, dict):
                current = {}
            if isinstance(prompts, dict):
                updated = current.copy()
                if "system" in prompts and isinstance(prompts["system"], str):
                    updated["system"] = prompts["system"]
                if "user" in prompts and isinstance(prompts["user"], str):
                    updated["user"] = prompts["user"]
                stored[module] = updated
        merged["module_prompts"] = stored
    if "tool_prompts" in conf and isinstance(conf["tool_prompts"], dict):
        stored_tool = merged.get("tool_prompts", {})
        incoming_tool = conf["tool_prompts"]
        for key, prompts in incoming_tool.items():
            # Allow custom tool prompts (e.g., reply_* shortcuts)
            key = str(key or "").strip()
            if not key:
                continue
            current = stored_tool.get(key, {})
            if not isinstance(current, dict):
                current = {}
            if isinstance(prompts, dict):
                updated = current.copy()
                if "system" in prompts and isinstance(prompts["system"], str):
                    updated["system"] = prompts["system"]
                if "user" in prompts and isinstance(prompts["user"], str):
                    updated["user"] = prompts["user"]
                if "label" in prompts and isinstance(prompts["label"], str):
                    updated["label"] = prompts["label"].strip()
                stored_tool[key] = updated
        merged["tool_prompts"] = stored_tool
    # Allow deleting custom tool prompts (e.g., reply_* shortcuts) from UI
    if "tool_prompts_delete" in conf and isinstance(conf["tool_prompts_delete"], list):
        stored_tool = merged.get("tool_prompts", {})
        reserved = set(DEFAULT_TOOL_PROMPTS.keys())
        for k in conf["tool_prompts_delete"]:
            key = str(k or "").strip()
            if not key:
                continue
            if key in reserved:
                continue
            # Safety: only allow deleting reply_* custom shortcuts from UI
            if not key.startswith("reply_"):
                continue
            stored_tool.pop(key, None)
        merged["tool_prompts"] = stored_tool
    if "model_router" in conf and isinstance(conf["model_router"], dict):
        current_router = merged.get("model_router") if isinstance(merged.get("model_router"), dict) else {}
        incoming_router = _merge_router_channel_secrets(current_router, conf["model_router"])
        updated_router = dict(current_router)
        for field in (
            "enabled",
            "strategy",
            "prefer_router",
            "dynamic_weighting",
            "breaker_failures",
            "cooldown_seconds",
            "latency_ref_ms",
            "main_channels",
            "mid_channels",
            "tool_channels",
            "main_module_channels",
            "mid_route_channels",
            "tool_route_channels",
        ):
            if field in incoming_router:
                updated_router[field] = incoming_router[field]
        merged["model_router"] = updated_router
    save_ai_config(merged)
    return {"status": "ok"}


@router.get("/entities")
def get_entities():
    path = os.path.abspath(os.path.join(os.getcwd(), 'data', 'entities.json'))
    try:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = {"industries": []}
    except Exception:
        data = {"industries": []}
    return data


@router.post("/entities")
def set_entities(body: dict):
    inds = body.get('industries')
    if inds is None or not isinstance(inds, list):
        raise HTTPException(400, 'industries must be a list')
    payload = {"industries": [str(x) for x in inds]}
    path = os.path.abspath(os.path.join(os.getcwd(), 'data', 'entities.json'))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return {"status": "ok"}


def _run_summary_local(payload: dict) -> dict:
    # payload expects: { messages: [...], prompts: {...}, options:{}, contact_ratings:{}, contact_details:{} }
    msgs = payload.get("messages", []) or []
    prompts = payload.get("prompts", {}) or {}
    snapshot_meta = payload.get("meta", {}) or {}

    contacts_raw: dict[str, dict[str, Any]] = {}
    for key, value in (payload.get("contact_ratings") or {}).items():
        entry: dict[str, Any]
        if isinstance(value, dict):
            entry = value.copy()
        else:
            try:
                entry = {"rating": float(value)}
            except Exception:
                entry = {}
        entry["cid"] = str(key)
        contacts_raw[str(key)] = entry
    for key, value in (payload.get("contact_details") or {}).items():
        entry = contacts_raw.get(str(key), {}).copy()
        if isinstance(value, dict):
            entry.update(value)
        else:
            entry.setdefault("extra", value)
        entry["cid"] = str(key)
        contacts_raw[str(key)] = entry

    name_to_cid: dict[str, str] = {}
    for cid, detail in contacts_raw.items():
        name_to_cid[str(cid)] = str(cid)
        if isinstance(detail, dict):
            for key in ("name", "alias", "display_name"):
                v = str(detail.get(key) or "").strip()
                if v:
                    name_to_cid[v] = str(cid)

    def _extract_text(message: dict) -> str:
        if not isinstance(message, dict):
            return ""
        for field in ("content", "content_text", "text"):
            value = message.get(field)
            if isinstance(value, str) and value.strip():
                return value
        raw = message.get("raw")
        if isinstance(raw, dict):
            for field in ("content", "content_text", "text"):
                value = raw.get(field)
                if isinstance(value, str) and value.strip():
                    return value
        # Some channels (links/files/derived-only rows) may not carry `content_text`,
        # but still have meaningful derived summaries. Use them to avoid filtering out
        # high-signal messages and causing empty market summaries.
        derived = message.get("derived")
        if isinstance(derived, dict):
            for field in ("summary", "summary_full", "key_info"):
                value = derived.get(field)
                if isinstance(value, str) and value.strip():
                    t = value.strip()
                    low = t.lower()
                    if low.startswith("ai:"):
                        t = t[3:].strip()
                    elif low.startswith("fallback:"):
                        t = t[9:].strip()
                    return t
        return ""

    def _is_short_message(message: dict) -> bool:
        text = _extract_text(message).strip()
        if not text:
            return True
        compact = "".join(text.split())
        if not compact:
            return True
        chinese_chars = sum(1 for ch in compact if "\u4e00" <= ch <= "\u9fff")
        if chinese_chars > 0:
            return chinese_chars <= 15
        return len(compact) <= 30

    filtered_msgs: list[dict] = []
    for m in msgs[:2000]:
        direction = (m.get("direction") or "").lower()
        if direction == "out":
            continue
        if str(m.get("is_spam", "")).lower() == "true":
            continue
        if _is_short_message(m):
            continue
        filtered_msgs.append(m)

    msgs = filtered_msgs

    try:
        conf = load_ai_config()
        module_prompts = conf.get("module_prompts", {})
        # By default, external aggregation modules are summarized locally to avoid heavy LLM usage / long hangs.
        # Can be overridden per-request with options.use_llm_external_modules=true (best-effort).
        try:
            req_opts = payload.get("options") or {}
            use_llm_external_modules = bool((req_opts or {}).get("use_llm_external_modules", False))
        except Exception:
            use_llm_external_modules = False
        # 强化"高评分联系人"提示词：禁止模型自行打分，评分来自系统
        try:
            cp = module_prompts.get('contacts') or {}
            if isinstance(cp, dict):
                sys_p = str(cp.get('system') or '')
                user_p = str(cp.get('user') or '')
                if '严禁自行评定' not in sys_p:
                    cp['system'] = (
                        '你是联系人摘要助手。评分信息由系统提供，严禁自行评定或修改分数。仅展示评分≥60的联系人，使用消息摘要（summary）概括观点，禁止复制原文。'
                    )
                if '评分来自系统' not in user_p:
                    cp['user'] = (
                        '请输出 JSON 对象 {"markdown": string}：\n'
                        '# 高评分分析师摘要\n'
                        '（评分≥60，按评分降序排列）\n\n'
                        '## <姓名或别名> (评分 <x.x>)\n'
                        '- 核心观点：<一句话概括> #<id>\n'
                        '- 核心观点：<一句话概括> #<id>\n\n'
                        '## <姓名或别名> (评分 <x.x>)\n'
                        '...\n\n'
                        '注意：\n'
                        '1. 严禁使用 wxid_xxx 作为姓名，必须使用 sender_name 或 alias。\n'
                        '2. 仅分析列表中评分>=60的联系人。\n'
                        '3. 必须基于 summary 字段生成，禁止编造。\n'
                        '数据：{{messages_data}}'
                    )
                module_prompts['contacts'] = cp
        except Exception:
            pass
        # 允许前端在本次任务中覆盖提示词（不落盘），优先级：前端传入 > 已保存 > 默认
        if isinstance(prompts, dict) and prompts:
            try:
                for key, ov in prompts.items():
                    if key not in DEFAULT_MODULE_PROMPTS:
                        continue
                    if not isinstance(ov, dict):
                        continue
                    current = module_prompts.get(key, {})
                    if not isinstance(current, dict):
                        current = {}
                    updated = current.copy()
                    if isinstance(ov.get("system"), str):
                        updated["system"] = ov.get("system")
                    if isinstance(ov.get("user"), str):
                        updated["user"] = ov.get("user")
                    module_prompts[key] = updated
            except Exception:
                pass

        # 使用消息的"摘要列（derived.summary）"作为大模型输入上下文，避免传入完整正文，节省 token
        enriched_messages = []
        for m in msgs[:2000]:
            # 从derived中提取summary字段
            derived = m.get("derived") or {}
            # Prefer tool summary; fallback to richer heuristic fields when needed.
            summary = derived.get("summary") or derived.get("summary_full") or derived.get("key_info") or ""
            cid = str(m.get("sender_id") or "").strip()
            if not cid:
                sender_label = (m.get("sender_name") or "").strip()
                cid = name_to_cid.get(sender_label, "")
            entry = {
                "id": m.get("id"),
                "time": m.get("time") or m.get("timestamp"),
                "sender": m.get("sender_name") or m.get("sender_id"),
                "sender_name": m.get("sender_name"),
                "talker": m.get("talker_name") or m.get("chat_id"),
                "message_type": m.get("message_type") or m.get("type"),
                # 不再传递完整 content，只保留摘要；必要时前端/本地回退渲染
                "content": None,
                "summary": summary,  # 供_compact函数与统计使用
                "tone": derived.get("tone"),
                "category": derived.get("category"),
                "meeting_number": derived.get("meeting_number"),
                "keywords": derived.get("keywords") or [],
                "contact_id": cid if cid else None,
            }
            enriched_messages.append(entry)

        from collections import defaultdict
        messages_by_cid: dict[str, list[dict]] = defaultdict(list)
        for em in enriched_messages:
            cid = em.get("contact_id")
            if cid:
                messages_by_cid[cid].append(em)

        # 紧凑化传入大模型的数据，避免上下文过大导致超限/失败
        def _safe_str(v: Any) -> str:
            try:
                return str(v) if v is not None else ""
            except Exception:
                return ""

        def _iso(v: Any) -> str:
            s = _safe_str(v)
            return s

        # 排序：按重要度与时间倒序；会议模块再优先保留带 meeting_number 的消息
        def _sort_key(m: dict) -> tuple:
            imp = m.get("importance")
            try:
                impv = float(imp) if imp is not None else 0.0
            except Exception:
                impv = 0.0
            return (impv, _iso(m.get("time")))

        sorted_messages = sorted(enriched_messages, key=_sort_key, reverse=True)

        # —— 按模块预过滤，降低无关噪声并保证"遍历所有消息后再总结"的语义 ——
        meeting_terms = ("会议", "路演", "电话会", "报名", "通知", "腾讯会议", "进门财经", "Zoom", "Teams")
        market_terms = ("认为", "观点", "策略", "看多", "看空", "判断", "建议", "风险", "目标价", "估值", "行业", "公司", "基本面", "宏观", "政策")

        def _is_meeting(m: dict) -> bool:
            text = (m.get("summary") or m.get("content") or "").strip()
            if m.get("meeting_number"):
                return True
            if not text:
                keywords = " ".join(k for k in (m.get("keywords") or []) if isinstance(k, str))
                text = keywords.strip()
            return any(t in text for t in meeting_terms)

        def _is_market(m: dict) -> bool:
            text = (m.get("summary") or m.get("content") or "").strip()
            return any(t in text for t in market_terms)

        def _is_counter(m: dict) -> bool:
            text = (m.get("summary") or m.get("content") or "").strip()
            return any(t in text for t in market_terms)

        # 仅使用摘要字段作为上下文；无摘要则传空字符串，避免拉长上下文
        def _compact(ms: list[dict], prefer_meetings: bool = False, limit: int = 400) -> list[dict]:
            # 内部函数：去除ai:前缀
            def _strip_prefix(text: str) -> str:
                t = (text or "").strip()
                if t.lower().startswith("ai:"):
                    t = t[3:].strip()
                elif t.lower().startswith("fallback:"):
                    t = t[9:].strip()
                return t
            
            # 内部函数：时间去去年份 (YYYY-MM-DD HH:MM:SS -> MM-DD HH:MM)
            def _short_time(ts: Any) -> str:
                s = str(ts) if ts else ""
                # 简单处理：若包含 T 或空格，且长度足够，则截取
                # 2025-11-24 10:00:00 -> 11-24 10:00
                # 2025-11-24T10:00:00 -> 11-24 10:00
                if len(s) >= 16 and (s[4] == '-' or s[4] == '/'):
                    return s[5:16].replace('T', ' ')
                return s

            selected: list[dict] = []
            pool = ms
            for m in pool:
                if len(selected) >= limit:
                    break
                # 仅使用摘要字段，去除 ai:/fallback: 前缀
                summary = _strip_prefix((m.get("summary") or "").strip())
                content_to_use = summary  # 无摘要传空字符串
                
                # 尝试解析发送人名称与评分
                cid = m.get("contact_id")
                sender_display = m.get("sender") or m.get("sender_name")
                rating = None
                if cid and cid in contacts_raw:
                    c_info = contacts_raw[cid]
                    # 优先使用备注 > 昵称 > 原始ID
                    sender_display = c_info.get("remark") or c_info.get("name") or c_info.get("alias") or sender_display
                    rating = c_info.get("rating")

                selected.append({
                    "id": m.get("id"),
                    "time": _short_time(m.get("time")), # 去除年份
                    "sender": sender_display,
                    "rating": rating,  # 显式传递评分给 LLM
                    "talker": m.get("talker"),
                    "message_type": m.get("message_type"),
                    # 传摘要；无摘要传 None 以便下游可感知
                    "summary": summary if summary else None,
                    "content": content_to_use,
                })
            return selected

        def _normalize_kw(kw: str) -> str:
            return (kw or "").strip().lower()

        stopwords = {
            "流通股本", "所属行业", "市值", "成交量", "换手率", "pe", "pb", "roe",
            "板块", "行业", "公司", "观点", "认为", "建议", "相关", "影响",
        }

        N = max(1, len(enriched_messages))
        df: dict[str, int] = {}
        for m in enriched_messages:
            kws = set(_normalize_kw(k) for k in (m.get("keywords") or []) if isinstance(k, str))
            for k in kws:
                if k and k not in stopwords:
                    df[k] = df.get(k, 0) + 1

        def _idf(term: str) -> float:
            import math

            return math.log((N + 1) / (1 + df.get(term, 0))) + 1.0

        for m in enriched_messages:
            kws = [_normalize_kw(k) for k in (m.get("keywords") or []) if isinstance(k, str)]
            scored = [
                (k, _idf(k))
                for k in kws
                if k and k not in stopwords
            ]
            scored.sort(key=lambda x: x[1], reverse=True)
            m["keywords"] = [k for k, _ in scored[:5]]

        from datetime import datetime, timedelta, timezone

        def _parse_time(ts: str | None):
            if not ts:
                return None
            text_ts = ts.replace("Z", "+00:00") if isinstance(ts, str) else ts
            try:
                return datetime.fromisoformat(text_ts)  # type: ignore[arg-type]
            except Exception:
                return None

        cutoff_dt = datetime.utcnow() - timedelta(days=3)
        norm_ratings: dict[str, float] = {}
        for cid, data in contacts_raw.items():
            rating_val = data.get("rating")
            if rating_val is None:
                continue
            try:
                rating = float(rating_val)
            except Exception:
                continue
            if rating <= 10:
                rating *= 10.0
            norm_ratings[cid] = rating

        def _latest_contact_time(msgs_for_contact: list[dict]) -> str:
            if not msgs_for_contact:
                return ""
            return _iso(max((m.get("time") for m in msgs_for_contact if m.get("time")), default=""))

        high_contacts = []
        for cid, rating in norm_ratings.items():
            if rating is None or rating < 60.0:
                continue
            contact_msgs = messages_by_cid.get(cid)
            if not contact_msgs:
                continue
            detail = contacts_raw.get(cid) or {}
            display = detail.get("name") or detail.get("alias") or cid
            # 跳过仅有 wxid_ 而无真实姓名/别名的联系人，避免在"高评分联系人"模块展示微信ID
            if (not (detail.get("name") or detail.get("alias"))) and str(display).startswith("wxid_"):
                continue
            ordered_msgs = sorted(contact_msgs, key=lambda x: _iso(x.get("time")), reverse=True)
            high_contacts.append({
                "cid": cid,
                "sender": display,
                "name": detail.get("name") or display,
                "alias": detail.get("alias"),
                "rating": float(rating),
                "messages": ordered_msgs,
            })
        high_contacts.sort(key=lambda x: (x["rating"], _latest_contact_time(x.get("messages") or [])), reverse=True)
        high_contact_ids = {c.get("cid") for c in high_contacts if c.get("cid")}
        # 若严格阈值导致为空，则以活跃度Top且评分>=60补足，避免"高评分联系人"卡片空白
        # 无回退：若期间内没有符合条件的联系人，则允许为空，避免误报

        time_min = min((m.get("time") for m in enriched_messages if m.get("time")), default=None)
        time_max = max((m.get("time") for m in enriched_messages if m.get("time")), default=None)

        base_payload = {
            "messages": enriched_messages,
            "raw_messages": msgs,
            "contact_ratings": {k: v.get("rating") for k, v in contacts_raw.items() if v.get("rating") is not None},
            "contacts": contacts_raw,
            "prompts": prompts,
            "meta": {
                "total_messages": len(enriched_messages),
                "time_range": [time_min, time_max],
                "high_score_contacts": high_contacts,
                "window_days": 3,
                "snapshot_meta": snapshot_meta,
            },
        }

        requested_modules = payload.get("modules")
        if isinstance(requested_modules, list) and requested_modules:
            module_filter = {m for m in requested_modules if m in {"market", "meetings", "counter", "contacts", "newswatch", "socialwatch", "mediawatch", "mpwatch", "minuteswatch"}}
        else:
            module_filter = {"market", "meetings", "counter", "contacts", "newswatch", "socialwatch", "mediawatch", "mpwatch", "minuteswatch"}

        temperature = payload.get("temperature")
        try:
            temperature = float(temperature) if temperature is not None else 0.3
        except Exception:
            temperature = 0.3

        module_map = {
            "market": "market_markdown",
            "meetings": "meetings_markdown",
            "counter": "counter_markdown",
            "contacts": "top_contacts_markdown",
            "newswatch": "newswatch_markdown",
            "socialwatch": "socialwatch_markdown",
            "mediawatch": "mediawatch_markdown",
            "mpwatch": "mpwatch_markdown",
            "minuteswatch": "minuteswatch_markdown",
        }

        module_titles = {
            "market": "市场观点总结",
            "meetings": "会议路演信息",
            "counter": "分歧观点分析",
            "contacts": "高评分分析师摘要",
            "newswatch": "新闻舆情监测",
            "socialwatch": "自媒体舆情监测",
            "mediawatch": "自媒体引擎摘要",
            "mpwatch": "公众号引擎摘要",
            "minuteswatch": "会议引擎摘要",
        }

        def _looks_cross_module_output(module_key: str, text: str) -> bool:
            raw = str(text or "").strip()
            if not raw:
                return False
            if raw.lstrip().startswith("<"):
                return False

            expected = str(module_titles.get(module_key) or "").strip()
            if not expected:
                return False

            def _norm(v: str) -> str:
                return re.sub(r"\s+", "", str(v or "")).strip()

            first_line = ""
            for line in raw.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                stripped = re.sub(r"^[#>\-\*\d\.\)\s]+", "", stripped).strip()
                if stripped:
                    first_line = stripped
                    break
            if not first_line:
                return False

            first_norm = _norm(first_line)
            expected_norm = _norm(expected)
            if expected_norm and expected_norm in first_norm:
                return False

            for other_key, title in module_titles.items():
                if other_key == module_key:
                    continue
                title_norm = _norm(title)
                if title_norm and title_norm in first_norm:
                    return True
            return False

        html_result_map = {
            "market": "market_html",
            "meetings": "meetings_html",
            "counter": "counter_html",
            "contacts": "top_contacts_html",
        }

        result: dict[str, str] = {
            "market_markdown": "",
            "meetings_markdown": "",
            "counter_markdown": "",
            "top_contacts_markdown": "",
            "market_html": "",
            "meetings_html": "",
            "counter_html": "",
            "top_contacts_html": "",
            "newswatch_markdown": "",
            "socialwatch_markdown": "",
            "mediawatch_markdown": "",
            "mpwatch_markdown": "",
            "minuteswatch_markdown": "",
        }

        def _ensure_heading(module_key: str, result_key: str, html_key: str | None) -> None:
            """确保每个模块有首段标题，避免前端看不到第一个小标题。"""
            title = module_titles.get(module_key)
            if not title:
                return
            # 若 html 为空但 markdown 本身是 HTML，则同步写入 html 字段
            if html_key and not result.get(html_key):
                md_val = str(result.get(result_key) or "").strip()
                if md_val.lstrip().startswith("<"):
                    result[html_key] = md_val
            if html_key:
                html_val = str(result.get(html_key) or "").strip()
                if html_val and not re.search(r"<h[1-3][^>]*>", html_val, flags=re.IGNORECASE):
                    result[html_key] = f"<h2>{html.escape(title)}</h2>\n{html_val}"
                    return
            md_val = str(result.get(result_key) or "").strip()
            if md_val and not md_val.lstrip().startswith("#"):
                result[result_key] = f"# {title}\n\n{md_val}"

        def _short_time(v: Any) -> str:
            s = str(v or "").strip()
            if not s:
                return ""
            if len(s) >= 16 and (s[4] == "-" or s[4] == "/"):
                return s[5:16].replace("T", " ")
            return s[:16].replace("T", " ")

        def _short_text(v: Any, limit: int = 36) -> str:
            t = str(v or "").strip().replace("\n", " ")
            if len(t) > limit:
                return t[:limit] + "…"
            return t

        def _md_link(label: str, url: str) -> str:
            u = (url or "").strip()
            if not u:
                return label
            safe = u.replace(")", "%29").replace("(", "%28")
            return f"[{label}]({safe})"

        def _md_cell(full: Any, limit: int = 36) -> str:
            # Render an HTML span with full content embedded for frontend popover.
            # IMPORTANT: avoid '|' in markdown-table cells; we normalize to full-width '｜'.
            import html as _html

            raw = str(full or "").strip()
            if not raw:
                return ""
            raw = raw.replace("|", "｜")
            short = _short_text(raw.replace("\r", " ").replace("\n", " "), limit)
            attr = raw.replace("\\", "\\\\").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")
            return f'<span data-full-content="{_html.escape(attr, quote=True)}">{_html.escape(short)}</span>'

        def _md_link_cell(label_full: Any, url: str, limit: int = 24) -> str:
            # HTML <a> with embedded full label, opens in new tab.
            import html as _html

            u = (url or "").strip()
            label_raw = str(label_full or "").strip().replace("|", "｜")
            if not u:
                return _md_cell(label_raw, limit=limit)
            safe = u.replace("|", "%7C").replace(")", "%29").replace("(", "%28")
            short = _short_text(label_raw.replace("\r", " ").replace("\n", " "), limit)
            attr = label_raw.replace("\\", "\\\\").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")
            return (
                f'<a href="{_html.escape(safe, quote=True)}" target="_blank" rel="noreferrer" '
                f'data-full-content="{_html.escape(attr, quote=True)}">{_html.escape(short)}</a>'
            )

        def _render_external_module_md(module_key: str, rows: list[dict]) -> str:
            if module_key == "mediawatch":
                lines: list[str] = ["# 自媒体引擎摘要"]
                if not rows:
                    lines.append("暂无数据。")
                    return "\n".join(lines)
                platforms: dict[str, int] = {}
                for r in rows:
                    p = str(r.get("talker_name") or r.get("platform") or "").strip() or "unknown"
                    platforms[p] = platforms.get(p, 0) + 1
                top_plat = " / ".join([k for k, _ in sorted(platforms.items(), key=lambda kv: kv[1], reverse=True)[:3]])
                lines.append(f"条目数：{len(rows)}；平台Top：{top_plat}")
                lines.append("")
                lines.append("| 时间 | 平台 | 作者 | 标题 | 摘要 | 互动 |")
                lines.append("| --- | --- | --- | --- | --- | --- |")
                for r in rows[:30]:
                    meta = r.get("meta") or {}
                    stats = meta.get("stats") or {}
                    like = int(stats.get("like") or 0)
                    comment = int(stats.get("comment") or 0)
                    share = int(stats.get("share") or 0)
                    collect = int(stats.get("collect") or 0)
                    engagement = f"赞{like}/评{comment}/转{share}/藏{collect}"
                    url = str(meta.get("url") or r.get("url") or "").strip()
                    title = str(meta.get("title") or r.get("title") or r.get("content") or "").strip()
                    summary = str(r.get("content") or "").strip()
                    lines.append(
                        "| "
                        + " | ".join(
                            [
                                _short_time(r.get("time")),
                                _md_cell(r.get("talker_name") or r.get("platform") or "", 10),
                                _md_cell(r.get("sender_name") or r.get("sender") or "", 10),
                                _md_link_cell(title, url, 18),
                                _md_cell(summary, 28),
                                engagement,
                            ]
                        )
                        + " |"
                    )
                return "\n".join(lines)

            if module_key == "mpwatch":
                lines = ["# 公众号引擎摘要"]
                if not rows:
                    lines.append("暂无数据。")
                    return "\n".join(lines)
                channels: dict[str, int] = {}
                for r in rows:
                    c = str(r.get("sender_name") or r.get("sender") or "").strip() or "unknown"
                    channels[c] = channels.get(c, 0) + 1
                top_ch = " / ".join([k for k, _ in sorted(channels.items(), key=lambda kv: kv[1], reverse=True)[:3]])
                lines.append(f"条目数：{len(rows)}；公众号Top：{top_ch}")
                lines.append("")
                lines.append("| 时间 | 公众号 | 标题 | 摘要 |")
                lines.append("| --- | --- | --- | --- |")
                for r in rows[:30]:
                    meta = r.get("meta") or {}
                    url = str(meta.get("url") or "").strip()
                    title = str(meta.get("title") or r.get("title") or "").strip() or str(r.get("content") or "").strip()
                    summary = str(r.get("content") or "").strip()
                    lines.append(
                        "| "
                        + " | ".join(
                            [
                                _short_time(r.get("time")),
                                _md_cell(r.get("sender_name") or r.get("sender") or "", 10),
                                _md_link_cell(title, url, 22),
                                _md_cell(summary, 42),
                            ]
                        )
                        + " |"
                    )
                return "\n".join(lines)

            if module_key == "minuteswatch":
                lines = ["# 会议引擎摘要"]
                if not rows:
                    lines.append("暂无数据。")
                    return "\n".join(lines)
                lines.append(f"条目数：{len(rows)}")
                lines.append("")
                lines.append("| 时间 | 主题 | 摘要 | 音频 |")
                lines.append("| --- | --- | --- | --- |")
                for r in rows[:20]:
                    title = str(r.get("sender_name") or r.get("sender") or "").strip()
                    text = str(r.get("content") or "").strip()
                    meta = r.get("meta") or {}
                    audio_url = str(meta.get("audio_url") or "").strip().replace("|", "%7C")
                    if audio_url:
                        import html as _html

                        audio = f'<a href="{_html.escape(audio_url, quote=True)}" target="_blank" rel="noreferrer">音频</a>'
                    else:
                        audio = ""
                    lines.append(
                        "| "
                        + " | ".join(
                            [
                                _short_time(r.get("time")),
                                _md_cell(title, 18),
                                _md_cell(text, 56),
                                audio,
                            ]
                        )
                        + " |"
                    )
                return "\n".join(lines)

            return ""

        cache_db = payload.get("_cache_db")

        def _persistent_cache_get(db_key: str) -> str | None:
            try:
                if isinstance(cache_db, Session):
                    row = cache_db.get(SyncState, db_key)
                    if row and row.value:
                        return row.value
                    return None
            except Exception:
                return None
            try:
                from ..db import SessionLocal as _SL

                dbx = _SL()
                try:
                    row = dbx.get(SyncState, db_key)
                    return row.value if row and row.value else None
                finally:
                    dbx.close()
            except Exception:
                return None

        def _persistent_cache_set(db_key: str, value: str) -> None:
            try:
                if isinstance(cache_db, Session):
                    row = cache_db.get(SyncState, db_key)
                    if not row:
                        row = SyncState(key=db_key, value=value)
                    else:
                        row.value = value
                    cache_db.add(row)
                    return
            except Exception:
                pass
            try:
                from ..db import SessionLocal as _SL

                dbx = _SL()
                try:
                    row = dbx.get(SyncState, db_key)
                    if not row:
                        row = SyncState(key=db_key, value=value)
                    else:
                        row.value = value
                    dbx.add(row)
                    dbx.commit()
                finally:
                    dbx.close()
            except Exception:
                pass

        for module_key, result_key in module_map.items():
            if module_key not in module_filter:
                continue
            prompt_conf = module_prompts.get(module_key, {})
            defaults = DEFAULT_MODULE_PROMPTS.get(module_key, {})
            system_prompt = prompt_conf.get("system") or defaults.get("system") or ""
            user_template = prompt_conf.get("user") or defaults.get("user") or ""
            module_payload = base_payload.copy()
            # 为不同模块选择更相关的子集，既覆盖"全部消息"，又避免无关噪声
            if module_key == "meetings":
                source = [m for m in sorted_messages if _is_meeting(m)] or sorted_messages
                module_payload["messages"] = _compact(source, prefer_meetings=True, limit=250)
            elif module_key == "market":
                # 市场观点总揽：确保覆盖所有消息，不要遗漏；优先包含摘要
                # 排除会议通知/报名等噪声（会议模块单独处理）
                source = [m for m in sorted_messages if _is_market(m) and not _is_meeting(m)]
                # 如果筛选后消息太少，则使用全部消息
                if len(source) < len(sorted_messages) * 0.3:
                    source = [m for m in sorted_messages if not _is_meeting(m)] or sorted_messages
                module_payload["messages"] = _compact(source, prefer_meetings=False, limit=400)  # 增加limit确保覆盖更多消息
            elif module_key == "counter":
                # 分歧观点分析：视窗内的所有有效摘要都应纳入分析，避免只看最近少量消息
                # _compact 仅做 ai: 前缀清理与结构统一，limit 设为 source 长度，由后续分片逻辑控制 token 大小
                source = [m for m in sorted_messages if _is_counter(m)] or sorted_messages
                module_payload["messages"] = _compact(source, prefer_meetings=False, limit=len(source))
            elif module_key == "contacts":
                if high_contact_ids:
                    source = [m for m in sorted_messages if (m.get("contact_id") or "") in high_contact_ids]
                else:
                    source = []
                module_payload["messages"] = _compact(source, prefer_meetings=False, limit=220)
            elif module_key == "newswatch":
                # 舆情分析读取直接新闻源，而非聊天消息
                try:
                    from ..services.news_engine import engine_payload
                    news_payload = engine_payload(limit=120)
                    raw_items = news_payload.get("items") or []
                    module_payload["trend_analysis"] = news_payload.get("analysis") or {}
                    # 仅保留近72小时内的新闻，优先覆盖最新的重要事件
                    from time import time as _time
                    now_ms = int(_time() * 1000)
                    cutoff = now_ms - 72 * 3600 * 1000
                    items_72h = [it for it in raw_items if int(it.get("pub_ts") or 0) >= cutoff]
                    # 若过滤过严导致为空，则回退到全部列表
                    use_items = items_72h or raw_items
                    news_items = []
                    for it in use_items[:80]:
                        news_items.append({
                            "id": str(it.get("id")),
                            "source": it.get("source_name") or it.get("source_id") or "",
                            "title": it.get("title") or "",
                            "url": it.get("url") or "",
                            "time": it.get("pub_ts") or None,
                        })
                    module_payload["messages"] = news_items
                except Exception:
                    module_payload["messages"] = []
            elif module_key == "mediawatch":
                # 自媒体引擎：读取 media-collector 落盘 JSON + MediaCrawlerPro 兼容
                try:
                    from ..services.media_store import list_media_items as list_legacy

                    all_items = []
                    
                    # 优先读取 media-collector 新数据
                    if _list_collector_items:
                        try:
                            cdata = _list_collector_items(limit=200)
                            all_items.extend(cdata.get("items") or [])
                        except Exception as e:
                            import logging
                            logging.getLogger("ai").warning(f"media-collector load failed: {e}")

                    # 补充旧 MediaCrawlerPro 数据
                    try:
                        ldata = list_media_items(limit=80)
                        all_items.extend(ldata.get("items") or [])
                    except Exception:
                        pass

                    # 合并去重
                    seen_urls = set()
                    unique = []
                    for it in all_items:
                        url = it.get("url", "")
                        if url and url in seen_urls:
                            continue
                        if url:
                            seen_urls.add(url)
                        unique.append(it)

                    unique.sort(key=lambda x: x.get("source_mtime", 0), reverse=True)

                    try:
                        from ..db import SessionLocal as _SL
                        from ..services.external_content_summaries import summarize_external_items

                        summary_db = _SL()
                        try:
                            summary_result = summarize_external_items(summary_db, "media", unique[:120])
                        finally:
                            summary_db.close()
                        summaries = {
                            str(item.get("id") or ""): item
                            for item in summary_result.get("items") or []
                        }
                    except Exception:
                        summaries = {}

                    rev = max((int(it.get("source_mtime") or 0) for it in unique), default=0)
                    msgs = []
                    for it in unique[:120]:
                        generated = summaries.get(str(it.get("id") or "")) or {}
                        msgs.append(
                            {
                                "channel": "media",
                                "id": str(it.get("id") or ""),
                                "time": it.get("time"),
                                "sender": it.get("author") or "",
                                "sender_name": it.get("author") or "",
                                "talker_name": f"{it.get('platform','')} {it.get('keyword','')}".strip(),
                                "type": it.get("source_type", "media"),
                                "content": generated.get("summary") or it.get("description") or it.get("title") or "",
                                "content_text": generated.get("summary") or it.get("description") or it.get("title") or "",
                                "meta": {
                                    "url": it.get("url") or "",
                                    "title": it.get("title") or "",
                                    "heat": it.get("heat") or 0,
                                    "stats": it.get("stats") or {},
                                    "source": it.get("source_type", "hot"),
                                    "keyword": it.get("keyword", ""),
                                },
                            }
                        )
                    module_payload["messages"] = msgs
                    module_payload["meta"] = {
                        **(module_payload.get("meta") or {}),
                        "source_rev": rev,
                    }
                except Exception as e:
                    import logging
                    logging.getLogger("ai").error(f"mediawatch payload build error: {e}")
                    module_payload["messages"] = []
            elif module_key == "mpwatch":
                # 公众号引擎：读取 we-mp-rss 的 sqlite（articles + feeds + insights）
                try:
                    from ..services.mp_rss_store import list_mp_articles, _default_we_mp_rss_db

                    mp_cfg: dict[str, Any] = {}
                    try:
                        row = None
                        if isinstance(cache_db, Session):
                            row = cache_db.get(SyncState, "mp_config")
                        if row is None:
                            from ..db import SessionLocal as _SL
                            dbx = _SL()
                            try:
                                row = dbx.get(SyncState, "mp_config")
                            finally:
                                dbx.close()
                        if row and row.value:
                            parsed = json.loads(row.value)
                            if isinstance(parsed, dict):
                                mp_cfg = parsed
                    except Exception:
                        mp_cfg = {}

                    res = list_mp_articles(
                        limit=120,
                        offset=0,
                        q=None,
                        db_path=str(mp_cfg.get("db_path") or "").strip() or None,
                        upstream_base_url=str(mp_cfg.get("upstream_base_url") or mp_cfg.get("base_url") or "").strip() or None,
                        upstream_auth_token=str(mp_cfg.get("upstream_auth_token") or mp_cfg.get("auth_token") or "").strip() or None,
                    )
                    items = res.get("items") or []
                    try:
                        from ..db import SessionLocal as _SL
                        from ..services.external_content_summaries import summarize_external_items

                        summary_db = _SL()
                        try:
                            summary_result = summarize_external_items(summary_db, "mp", items[:120])
                        finally:
                            summary_db.close()
                        summaries = {
                            str(item.get("id") or ""): item
                            for item in summary_result.get("items") or []
                        }
                    except Exception:
                        summaries = {}
                    # cache rev = db mtime
                    rev = 0
                    try:
                        src = res.get("source") if isinstance(res, dict) else None
                        if isinstance(src, dict):
                            rev = int(src.get("mtime") or 0)
                        if not rev:
                            dbp = _default_we_mp_rss_db()
                            rev = int(dbp.stat().st_mtime) if dbp and dbp.exists() else 0
                    except Exception:
                        rev = 0
                    msgs = []
                    for it in items[:120]:
                        generated = summaries.get(str(it.get("id") or "")) or {}
                        msgs.append(
                            {
                                "channel": "mp",
                                "id": str(it.get("id") or ""),
                                "time": it.get("publish_time"),
                                "sender": it.get("channel_name") or "",
                                "sender_name": it.get("channel_name") or "",
                                "talker_name": "we-mp-rss",
                                "type": "mp",
                                "content": generated.get("summary") or it.get("summary") or it.get("title") or "",
                                "content_text": generated.get("summary") or it.get("summary") or it.get("title") or "",
                                "meta": {"url": it.get("url") or "", "title": it.get("title") or ""},
                            }
                        )
                    module_payload["messages"] = msgs
                    module_payload["meta"] = {**(module_payload.get("meta") or {}), "source_rev": rev}
                except Exception:
                    module_payload["messages"] = []
            elif module_key == "minuteswatch":
                # 会议引擎：读取当前项目本地 minutes（data/minutes + data/recordings）
                try:
                    from ..routers.minutes import list_minutes as _list_minutes

                    data = _list_minutes(q=None, limit=200, refresh=False, llm=False)
                    items = data.get("items") or []
                    rev = 0
                    msgs = []
                    for it in items[:60]:
                        meta = it.get("meta") or {}
                        path = str(it.get("path") or "").strip()
                        title = ""
                        if path:
                            try:
                                import os as _os

                                title = _os.path.splitext(_os.path.basename(path))[0]
                            except Exception:
                                title = path
                        title = title or str(it.get("sender_name") or it.get("sender") or "").strip()
                        summary = str(it.get("summary") or "").strip()
                        if not summary:
                            # best-effort fallback for AI summary panel (avoid huge transcript)
                            summary = str(it.get("content_refined") or "").strip() or str(it.get("content_text") or "").strip()[:800]
                        msgs.append(
                            {
                                "channel": "minutes",
                                "id": str(it.get("id") or ""),
                                "time": it.get("time") or "",
                                "sender": title,
                                "sender_name": title,
                                "talker_name": it.get("talker_name") or "minutes",
                                "type": "minutes",
                                "content": summary,
                                "content_text": summary,
                                "meta": {"audio_url": meta.get("audio_url") or "", "transcript_status": meta.get("transcript_status") or "", "path": path},
                            }
                        )
                    module_payload["messages"] = msgs
                    module_payload["meta"] = {**(module_payload.get("meta") or {}), "source_rev": rev}
                except Exception:
                    module_payload["messages"] = []
            else:
                module_payload["messages"] = _compact(sorted_messages, prefer_meetings=False, limit=300)

            # External aggregation modules: local summarization first to avoid long remote LLM calls.
            if module_key in {"mediawatch", "mpwatch", "minuteswatch"} and not use_llm_external_modules:
                try:
                    md = _render_external_module_md(module_key, module_payload.get("messages") or [])
                    if md:
                        result[result_key] = md
                        # Cache like normal (prompt hash still participates so prompt changes invalidate)
                        try:
                            snap_id = payload.get("snapshot_id")
                            rev = (module_payload.get("meta") or {}).get("source_rev")
                            if rev:
                                snap_id = f"{snap_id}:{module_key}:{int(rev)}"
                            ph = sha1(((system_prompt or "") + "\n" + (user_template or "")).encode("utf-8", "ignore")).hexdigest()[:12]
                            cache_key = (snap_id, module_key, ph, float(temperature))
                            _summary_cache_set(cache_key, result[result_key])
                            db_key = f"summary_cache:{snap_id}:{module_key}:{ph}:{float(temperature):.2f}"
                            _persistent_cache_set(db_key, result[result_key])
                        except Exception:
                            pass
                        continue
                except Exception:
                    pass

            # 粗略 token 预算，防止超过大上下文（~128k tokens）；按字符估算并分块摘要再合并
            try:
                est_tokens = sum(len((m.get("content") or "")) for m in module_payload["messages"]) * 1.1
                if est_tokens > 120_000 and len(module_payload["messages"]) > 200:
                    chunks: list[list[dict]] = []
                    chunk: list[dict] = []
                    budget = 0
                    for m in module_payload["messages"]:
                        cost = len((m.get("content") or "")) + 64
                        if budget + cost > 40_000 and chunk:
                            chunks.append(chunk)
                            chunk = []
                            budget = 0
                        chunk.append(m)
                        budget += cost
                    if chunk:
                        chunks.append(chunk)

                    partial_markdowns: list[str] = []
                    partial_errors: list[str] = []
                    for idx, ch in enumerate(chunks[:6]):  # 最多6片，避免长时间调用
                        cp = module_payload.copy()
                        cp["messages"] = ch
                        cp_str = json.dumps(cp, ensure_ascii=False)
                        if "{{messages_data}}" in user_template:
                            user_content = user_template.replace("{{messages_data}}", cp_str)
                        else:
                            user_content = user_template + "\n\n数据：\n" + cp_str
                        messages_payload = [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_content},
                        ]
                        raw = _chat_with_retry(
                            lambda _mp=_messages_payload: siliconflow_chat(
                                _mp,
                                temperature=temperature,
                                route_kind="main",
                                route_key=module_key,
                            ),
                        )
                        if isinstance(raw, dict) and "__error__" in raw:
                            partial_errors.append(f"chunk_{idx}: {raw['__error__']}")
                        elif raw:
                            partial_markdowns.append(_strip_llm_thoughts(raw))

                    if partial_errors:
                        result["_partial_errors"] = result.get("_partial_errors", []) + partial_errors

                    if partial_markdowns:
                        # 合并阶段：将多段 markdown 汇总为最终 markdown
                        merge_user = "\n".join([
                            "请将多段模块性摘要合并为一段更高质量的最终摘要，避免重复，保留结构化标题：",
                            "---",
                            "\n\n".join(f"[片段{idx+1}]\n{md}" for idx, md in enumerate(partial_markdowns[:6]))
                        ])
                        merge_payload = [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": merge_user},
                        ]
                        try:
                            output_text = siliconflow_chat(
                                merge_payload,
                                temperature=temperature,
                                route_kind="main",
                                route_key=module_key,
                            )
                            md_payload, html_payload, _ = _unwrap_markdown_payload(output_text)
                            if md_payload is not None:
                                result[result_key] = _strip_llm_thoughts(md_payload)
                            elif html_payload is not None:
                                result[result_key] = _strip_llm_thoughts(html_payload)
                            else:
                                result[result_key] = _strip_llm_thoughts(output_text)
                            continue  # 已产出结果，跳过常规路径
                        except Exception:
                            pass
            except Exception:
                pass
            module_payload["target_module"] = module_key
            module_payload["module_title"] = module_titles.get(module_key, module_key)
            # 降低 newswatch 上下文体积：仅传递精简 messages，避免夹带 raw_messages 导致超长
            if module_key == "newswatch":
                compact = {"messages": module_payload.get("messages", [])}
                payload_str = json.dumps(compact, ensure_ascii=False)
            else:
                # 压缩上下文：避免把超大的 contacts/ratings 字典传入大模型（会导致请求过大/超长）
                meta_raw = module_payload.get("meta") or {}
                slim_meta: dict[str, Any] = {}
                for k in ("total_messages", "time_range", "window_days"):
                    if k in meta_raw:
                        slim_meta[k] = meta_raw.get(k)
                slim: dict[str, Any] = {
                    "messages": module_payload.get("messages", []),
                    "meta": slim_meta,
                }
                payload_str = json.dumps(slim, ensure_ascii=False)

            # ===== 增量缓存命中检查 =====
            try:
                raw_snap_id = payload.get("snapshot_id")
                # 对外部引擎模块：把数据源版本纳入缓存 key，避免"数据更新但命中旧缓存"
                try:
                    rev = (module_payload.get("meta") or {}).get("source_rev")
                    if module_key in {"mediawatch", "mpwatch", "minuteswatch"} and rev:
                        snap_id = f"{raw_snap_id}:{module_key}:{int(rev)}"
                    else:
                        # 纳入 snapshot.message_count + updated_at，使缓存感知消息增量
                        snap_id = _build_snap_version(raw_snap_id, module_key, cache_db)
                except Exception:
                    snap_id = raw_snap_id
                ph = sha1(((system_prompt or '') + '\n' + (user_template or '')).encode('utf-8', 'ignore')).hexdigest()[:12]
                cache_key = (snap_id, module_key, ph, float(temperature))
                cached = _summary_cache_get(cache_key)
                if not cached:
                    # 持久化缓存：SyncState("summary_cache:<...>")
                    db_key = f"summary_cache:{snap_id}:{module_key}:{ph}:{float(temperature):.2f}"
                    cached = _persistent_cache_get(db_key)
                if cached:
                    _summary_cache_set(cache_key, cached)
                if cached:
                    result[result_key] = cached
                    hk = html_result_map.get(module_key)
                    if hk and cached and str(cached).lstrip().startswith("<"):
                        result[hk] = cached
                    _ensure_heading(module_key, result_key, hk)
                    continue
            except Exception:
                pass
            if "{{messages_data}}" in user_template:
                user_content = user_template.replace("{{messages_data}}", payload_str)
            else:
                user_content = user_template + "\n\n数据：\n" + payload_str

            messages_payload = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]

            try:
                # 模块级重试：网络抖动 / 模型限流时最多重试 3 次，记录所有失败原因
                raw_output = _chat_with_retry(
                    lambda: siliconflow_chat(
                        messages_payload,
                        temperature=temperature,
                        route_kind="main",
                        route_key=module_key,
                    )
                )
                if isinstance(raw_output, dict) and "__error__" in raw_output:
                    # 记录错误但不中断，其他模块继续执行；前端可通过 _module_errors 感知
                    result[f"_{module_key}_error"] = raw_output["__error__"]
                    result[result_key] = ""
                    continue
                output_text = raw_output  # type: ignore[assignment]
            except Exception as exc:  # pragma: no cover
                result[result_key] = ""
                # 不中断，让后续使用本地兜底生成
                continue

            md_payload, html_payload, quant_payload = _unwrap_markdown_payload(output_text)
            if md_payload is not None or html_payload is not None:
                if md_payload is not None:
                    result[result_key] = _strip_llm_thoughts(md_payload)
                if html_payload is not None:
                    html_out = _strip_llm_thoughts(html_payload)
                    # Preserve for markdown-slot rendering (back-compat), but also store in *_html for UI/artifacts.
                    if not result.get(result_key):
                        result[result_key] = html_out
                    hk = html_result_map.get(module_key)
                    if hk and html_out:
                        result[hk] = html_out
                # Append deterministic quant section (server-rendered) for selected modules.
                try:
                    if module_key in {"market", "newswatch"}:
                        q_raw = quant_payload
                        q_norm = normalize_quant(q_raw if isinstance(q_raw, dict) else None)
                        q_md = render_quant_section_markdown(q_norm, module=module_key)
                        cur = str(result.get(result_key) or "")
                        # Only append to markdown-like content (avoid corrupting raw HTML).
                        if q_md and cur and not cur.lstrip().startswith("<"):
                            result[result_key] = cur.rstrip() + "\n\n" + q_md
                except Exception:
                    pass
            else:
                # 兜底：如果返回纯文本，视为 Markdown；若是原生 HTML，则同步写入 *_html 供前端优先使用
                text_out = _strip_llm_thoughts(output_text)
                result[result_key] = text_out
                hk = html_result_map.get(module_key)
                if hk and text_out and text_out.lstrip().startswith("<"):
                    result[hk] = text_out

            if _looks_cross_module_output(module_key, result.get(result_key) or ""):
                result[f"_{module_key}_error"] = "cross_module_output_mismatch"
                result[result_key] = ""
                hk = html_result_map.get(module_key)
                if hk:
                    result[hk] = ""
                continue

            _ensure_heading(module_key, result_key, html_result_map.get(module_key))
            # 写入缓存（使用与命中检查一致的 versioned snap_id）
            try:
                raw_snap_id = payload.get("snapshot_id")
                try:
                    rev = (module_payload.get("meta") or {}).get("source_rev")
                    if module_key in {"mediawatch", "mpwatch", "minuteswatch"} and rev:
                        snap_id = f"{raw_snap_id}:{module_key}:{int(rev)}"
                    else:
                        snap_id = _build_snap_version(raw_snap_id, module_key, cache_db)
                except Exception:
                    snap_id = raw_snap_id
                ph = sha1(((system_prompt or '') + '\n' + (user_template or '')).encode('utf-8', 'ignore')).hexdigest()[:12]
                cache_key = (snap_id, module_key, ph, float(temperature))
                _summary_cache_set(cache_key, result[result_key])
                # 写入持久化缓存
                db_key = f"summary_cache:{snap_id}:{module_key}:{ph}:{float(temperature):.2f}"
                _persistent_cache_set(db_key, result[result_key])
            except Exception:
                pass

        # 补充缺失的首段标题（涵盖缓存/本地生成等路径）
        for mk, rk in module_map.items():
            _ensure_heading(mk, rk, html_result_map.get(mk))

        # ---------- Local fallbacks to guarantee useful content ----------
        POS = {"看多","看好","上涨","增持","买入","积极","乐观","超配","超预期","改善","提价","扩产","胜诉","达成"}
        NEG = {"看空","不看好","下跌","减持","卖出","悲观","谨慎","风险","压力","回调","不及预期","降价","停产","失利","受阻"}

        from collections import Counter
        import re as _re

        def _strip_ai_prefix(text: str) -> str:
            t = (text or "").strip()
            if t.lower().startswith("ai:"):
                t = t[3:].strip()
            return t

        def _top_terms(texts: list[str], limit: int = 3) -> list[str]:
            tokens: list[str] = []
            for txt in texts:
                for tok in _re.findall(r"[A-Za-z]{3,}|[\u4e00-\u9fa5]{2,6}", txt):
                    if len(tok) < 2:
                        continue
                    tokens.append(tok)
            commons = [w for w, _ in Counter(tokens).most_common(limit)]
            return commons

        def _pick_risk(texts: list[str]) -> str:
            for txt in texts:
                if "风险" in txt or "待" in txt or "不确定" in txt or "关注" in txt:
                    return txt
            return "关注政策节奏与资金面变化"

        def _short(txt: str, n: int = 80) -> str:
            t = (txt or "").strip().replace("\n", " ")
            return t[: n] + ("…" if len(t) > n else "")

        def _short_cn(txt: str, limit: int = 10) -> str:
            t = (txt or "").strip().replace("\n", " ")
            if t.lower().startswith("ai:"):
                t = t[3:].strip()
            count = 0
            result_chars: list[str] = []
            for ch in t:
                count += 2 if ord(ch) > 127 else 1
                if count > limit * 2:
                    result_chars.append("…")
                    break
                result_chars.append(ch)
            return "".join(result_chars)

        def _has_any(text: str, words: set[str]) -> bool:
            return any(w in text for w in words)

        # Category rules
        CAT_RULES = [
            ("宏观政策", ["宏观","政策","降息","加息","降准","货币政策","财政政策","专项债","美联储","央行","社融","通胀","CPI","PPI"]),
            ("行业板块", ["行业","板块","AI","人工智能","芯片","半导体","新能源","煤炭","钢铁","地产","医药","消费","军工","汽车","高景气"]),
            ("公司基本面", ["公司","个股","业绩","盈利","估值","财报","公告","订单","收入","净利","股价"]),
            ("投资策略", ["策略","配置","仓位","增持","减仓","组合","资产配置","风格","价值","成长","红利","低波","大类资产"]),
            ("市场情绪", ["情绪","北向","资金","成交","量能","波动","风险偏好","恐慌","贪婪"]),
            ("其他观点", []),
        ]

        # Build indices for quick search
        def _match_cats(m: dict) -> list[str]:
            text = (m.get("content") or "").strip()
            kws = set(str(k) for k in (m.get("keywords") or []))
            cats: list[str] = []
            for name, keys in CAT_RULES:
                if not keys:
                    continue
                if any(k in text for k in keys) or (kws and any(k in " ".join(kws) for k in keys)):
                    cats.append(name)
            if not cats:
                cats.append("其他观点")
            return cats

        def _summarize_bucket(bucket: list[dict], limit: int = 4) -> list[str]:
            if not bucket:
                return ["- 信息有限"]
            texts = [_strip_ai_prefix(m.get("summary") or m.get("content") or "") for m in bucket]
            top_terms = _top_terms(texts, 3)
            headline = "、".join(top_terms[:2]) if top_terms else "重点线索"
            primary = _short(texts[0], 120)
            risk = _short(_pick_risk(texts), 80)
            lines = [f"- 主题：{headline}；结论：{primary}", f"- 风险/待跟进：{risk}"]
            return lines[:limit]

        def _build_market_md() -> str:
            total = len(enriched_messages)
            pos = sum(1 for m in enriched_messages if _has_any(str(m.get("content") or ""), POS) or (m.get("tone") == "positive"))
            neg = sum(1 for m in enriched_messages if _has_any(str(m.get("content") or ""), NEG) or (m.get("tone") == "negative"))
            md = ["# 市场观点总览", f"- 样本：{total} 条；正向 {pos} 条 / 负向 {neg} 条"]
            md.append("- 今日关键风险：关注政策节奏与资金流、业绩兑现度以及外部宏观变量带来的波动。")
            for name, _ in CAT_RULES:
                bucket = [m for m in enriched_messages if name in _match_cats(m)]
                md.append(f"\n## {name}")
                md.extend(_summarize_bucket(bucket))
            md.append("\n## 今日重点提示\n- 按主题监控数据验证窗口，遇到分歧议题先补齐证据再决策；保持仓位弹性和对冲准备。")
            return "\n".join(md)

        def _build_market_html() -> str:
            total = len(enriched_messages)
            pos = sum(1 for m in enriched_messages if _has_any(str(m.get("content") or ""), POS) or (m.get("tone") == "positive"))
            neg = sum(1 for m in enriched_messages if _has_any(str(m.get("content") or ""), NEG) or (m.get("tone") == "negative"))
            sections = [f"<p>样本：{total} 条；正向 {pos} / 负向 {neg}</p>"]
            topic_idx = 1
            for name, _ in CAT_RULES:
                bucket = [m for m in enriched_messages if name in _match_cats(m)]
                if not bucket:
                    continue
                sections.append(f"<div class=\"section-label\">【主题{topic_idx}：{html.escape(name)}】</div>")
                lines = _summarize_bucket(bucket)
                sections.append("<ul>" + "".join(f"<li>{html.escape(line)}</li>" for line in lines) + "</ul>")
                topic_idx += 1
            sections.append("<div class=\"section-label\">【行动建议】</div><ul><li>按主题监控验证窗口，补齐证据再做仓位调整，保留对冲准备。</li></ul>")
            return "".join(sections)

        PLATFORM_ABBREV = {
            "腾讯会议": "腾讯",
            "进门财经": "进门",
            "飞书": "飞书",
            "Zoom": "Zoom",
            "Teams": "Teams",
            "钉钉": "钉钉",
            "电话会议": "电话",
        }

        def _detect_platform(text: str) -> str | None:
            t = text.lower()
            if "腾讯会议" in text: return "腾讯会议"
            if "进门财经" in text: return "进门财经"
            if "飞书" in text or "feishu" in t or "lark" in t: return "飞书"
            if "zoom" in t: return "Zoom"
            if "teams" in t: return "Teams"
            if "钉钉" in text or "dingtalk" in t: return "钉钉"
            if "电话会" in text or "电话会议" in text: return "电话会议"
            return None

        def _abbr_platform(name: str | None) -> str:
            if not name:
                return "待定"
            return PLATFORM_ABBREV.get(name, name[:2])

        def _fmt_meeting_time(ts: str | None) -> str:
            if not ts:
                return "待定"
            text = ts.replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(text)
            except Exception:
                return ts.replace("T", " ")[:16]
            return dt.strftime("%m-%d %H:%M")

        def _extract_time_from_text(text: str) -> str | None:
            """从正文中提取"会议时间"，而不是消息发送时间。

            支持模式：
            - 9-24 19:30 / 09-24 19:30 / 9月24日 19:30 / 9/24 19:30
            - "今晚/今天/明天 xx:xx" 等，仅时间时默认使用当天日期。
            """
            import re as _re
            t = (text or "").strip()
            if not t:
                return None
            pats = [
                _re.compile(r"(?P<m>\d{1,2})[-/\.月](?P<d>\d{1,2})(?:日)?\s*(?P<h>\d{1,2}):(?P<mi>\d{2})"),
                _re.compile(r"(?P<h>\d{1,2}):(?P<mi>\d{2})"),
            ]
            for p in pats:
                m = p.search(t)
                if m:
                    gd = m.groupdict()
                    try:
                        mm = int(gd.get('m') or 0)
                        dd = int(gd.get('d') or 0)
                        hh = int(gd.get('h') or 0)
                        mi = int(gd.get('mi') or 0)
                        if mm and dd:
                            return f"{mm:02d}-{dd:02d} {hh:02d}:{mi:02d}"
                        # If only time found, use today as date
                        from datetime import datetime as _dt
                        now = _dt.utcnow()
                        return f"{now.month:02d}-{now.day:02d} {hh:02d}:{mi:02d}"
                    except Exception:
                        continue
            return None

        def _extract_meetings() -> list[dict]:
            import re as _re
            items: list[dict] = []
            seen: set[str] = set()
            for m in enriched_messages:
                text = (m.get("content") or "")
                platform = _detect_platform(text)
                meeting_no = (m.get("meeting_number") or "").strip()
                if not meeting_no:
                    mm = _re.search(r"(?<!\d)(\d{8,12})(?!\d)", text)
                    if mm:
                        meeting_no = mm.group(1)
                if platform or meeting_no or ("会议" in text) or ("路演" in text) or ("报名" in text):
                    key = f"{m.get('time')}|{meeting_no}|{platform}"
                    if key in seen:
                        continue
                    seen.add(key)
                    # 使用 summary 作为主题要点来源，严格只使用summary字段，去除ai:前缀
                    base_summary = (m.get("summary") or "").strip()
                    if not base_summary:
                        continue  # 没有摘要则跳过该消息，不使用content作为fallback
                    base_summary = _strip_ai_prefix(base_summary)
                    shown_time = _extract_time_from_text(text) or _fmt_meeting_time(m.get("time"))
                    label_idx = len(items) + 1
                    items.append({
                        "id": m.get("id") or m.get("message_id"),
                        "time": shown_time,
                        "platform": _abbr_platform(platform),
                        "number": meeting_no or "待确认",
                        "speaker": m.get("sender") or m.get("sender_name") or "-",
                        "topic": _short_cn(base_summary, 10) or "-",
                        "label": f"会议{label_idx}",
                    })
            # sort by time desc
            items.sort(key=lambda x: x.get("time") or "", reverse=True)
            return items[:20]

        def _build_meetings_md() -> str:
            items = _extract_meetings()
            if not items:
                return "- 近期未检测到可用的会议路演信息"
            platform_counter = Counter(it.get("platform") or "待定" for it in items)
            top_platforms = ", ".join(f"{k}{v}场" for k, v in platform_counter.most_common(3))
            lines = [f"今日共 {len(items)} 场；主流平台：{top_platforms or '—'}"]
            for idx, it in enumerate(items, 1):
                code = it['number'] if it['number'] != "待确认" else ''
                news_id = str(it.get("id") or "")
                lines.append(f"【会议{idx}】{it['time']} | {it['platform']} {code} | {it['topic']} #{news_id}")
            return "\n".join(lines)

        def _normalize_conflict_theme(m: dict) -> str:
            # 统一使用 summary 作为议题主题来源
            base = (m.get("summary") or m.get("content") or "").strip()
            if base.lower().startswith("ai:"):
                base = base[3:].strip()
            return _short(base, 40) or "未命名议题"

        def _classify_tone(m: dict) -> str:
            tone = (m.get("tone") or "").lower()
            text = (m.get("content") or "")
            if tone in ("positive", "negative"):
                return tone
            if _has_any(text, POS):
                return "positive"
            if _has_any(text, NEG):
                return "negative"
            return "neutral"

        def _extract_conflicts() -> list[dict]:
            topics: dict[str, dict[str, list[str]]] = {}
            for m in enriched_messages:
                tone = _classify_tone(m)
                if tone not in ("positive", "negative"):
                    continue
                summary = _strip_ai_prefix(m.get("summary") or m.get("content") or "")
                if not summary:
                    continue
                theme = _normalize_conflict_theme(m)
                entry = _short(summary, 140)
                bucket = topics.setdefault(theme, {"positive": [], "negative": [], "pos_ids": [], "neg_ids": []})
                if tone == "positive":
                    bucket["positive"].append(entry)
                    bucket["pos_ids"].append(str(m.get("id") or m.get("message_id") or ""))
                else:
                    bucket["negative"].append(entry)
                    bucket["neg_ids"].append(str(m.get("id") or m.get("message_id") or ""))
            conflicts: list[dict] = []
            for theme, bucket in topics.items():
                if bucket["positive"] and bucket["negative"]:
                    conflicts.append({
                        "theme": theme,
                        "positive": bucket["positive"],
                        "negative": bucket["negative"],
                        "pos_ids": bucket["pos_ids"],
                        "neg_ids": bucket["neg_ids"],
                    })
            return conflicts[:6]

        def _build_counter_md() -> str:
            conflicts = _extract_conflicts()
            if not conflicts:
                return "- 暂未识别具备证据支撑的分歧观点，可继续收集信息。"
            md = [f"共发现 {len(conflicts)} 个存在明显分歧的议题，需重点核查。"]
            for idx, item in enumerate(conflicts, 1):
                theme = _short(item["theme"], 40)
                md.append(f"\n【分歧观点{idx}】{theme}")
                pos_line = item["positive"][0]
                if item["pos_ids"]:
                    ids = " ".join(f"#{i}" for i in item["pos_ids"][:2] if i)
                    if ids:
                        pos_line += f" (来源:{ids})"
                neg_line = item["negative"][0]
                if item["neg_ids"]:
                    ids = " ".join(f"#{i}" for i in item["neg_ids"][:2] if i)
                    if ids:
                        neg_line += f" (来源:{ids})"
                md.append(f"- 主流观点：{pos_line}")
                md.append(f"- 对立观点：{neg_line}")
                merged = item["positive"] + item["negative"]
                md.append(f"- 待核查：{_short(_pick_risk([_strip_ai_prefix(x) for x in merged]), 100)}")
            md.append("\n【行动建议】对上述议题安排快速访谈或数据核查，先补证据再定调；及时反馈投委会。")
            return "\n".join(md)

        def _build_contacts_md() -> str:
            lines = []
            if not high_contacts:
                lines.append("- 近3天暂无评分≥60分且活跃的分析师")
                return "\n".join(lines)
            for idx, c in enumerate(high_contacts[:20], 1):
                sender = c.get("name") or c.get("alias") or c.get("sender") or c.get("cid")
                rating = c.get("rating") or 0
                msg_entries = []
                for msg in c.get("messages", [])[:3]:
                    summary = _strip_ai_prefix(msg.get("summary") or "")
                    if not summary:
                        continue
                    msg_entries.append({
                        "text": _short(summary, 120),
                        "id": msg.get("id"),
                    })
                if not msg_entries:
                    continue
                lines.append(f"【分析师{idx}】{sender}（评分 {rating:.1f}）")
                primary = msg_entries[0]
                badge = f" (#{primary['id']})" if primary.get("id") else ""
                lines.append(f"- 核心观点：{primary['text']}{badge}")
                if len(msg_entries) > 1:
                    extras = []
                    for extra in msg_entries[1:]:
                        tag = f" (#{extra['id']})" if extra.get('id') else ''
                        extras.append(f"{extra['text']}{tag}")
                    lines.append(f"- 补充观点：{'；'.join(extras)}")
                else:
                    lines.append("- 补充观点：近期信息已记录于聊天摘要中")
                lines.append("- 跟进建议：关注其重点议题，准备应答要点。")
            return "\n".join(lines)

        # === HTML 版本（用于更好的交互与排版） ===
        def _build_meetings_html() -> str:
            items = _extract_meetings()
            if not items:
                return "<p>近期未检测到可用的会议路演信息。</p>"
            platform_counter = Counter(it.get("platform") or "待定" for it in items)
            top_platforms = ", ".join(f"{html.escape(k)}{v}场" for k, v in platform_counter.most_common(3)) or "—"
            rows = []
            for idx, it in enumerate(items, 1):
                msg_id = html.escape(str(it.get('id') or ''))
                platform = html.escape(it['platform'])
                code = html.escape(it['number']) if it['number'] != "待确认" else ""
                full_time = html.escape(it['time'])
                full_code = (platform + " " + code).strip()
                label = html.escape(f"【会议{idx}】")
                rows.append(
                    f"<tr data-msg-id=\"{msg_id}\"><td title=\"{full_time}\">{full_time}</td><td title=\"{full_code}\">{full_code}</td>"
                    f"<td>{label} <span class=\"msg-badge\" data-msg-id=\"{msg_id}\">源</span> {html.escape(it['topic'])}</td></tr>"
                )
            table = f"""
            <p>今日共 {len(items)} 场；主流平台：{top_platforms}</p>
            <table class=\"meeting-table\"><thead><tr><th>时间</th><th>平台/会议号</th><th>主题要点</th></tr></thead>
            <tbody>{''.join(rows)}</tbody></table>
            """
            return table

        def _build_counter_html() -> str:
            conflicts = _extract_conflicts()
            if not conflicts:
                return "<p>暂无明确分歧。建议继续跟踪关键数据与风险点。</p>"

            parts: list[str] = []
            parts.append(f"<p>共发现 {len(conflicts)} 个存在实质分歧的议题，建议优先核查证据、补齐数据缺口。</p>")

            for idx, it in enumerate(conflicts, 1):
                theme = _short(str(it.get("theme") or "未命名议题"), 40)
                pos_txt = _short(_strip_ai_prefix(it["positive"][0]), 200)
                neg_txt = _short(_strip_ai_prefix(it["negative"][0]), 200)
                pos_id = (it.get("pos_ids") or [None])[0]
                neg_id = (it.get("neg_ids") or [None])[0]
                pos_badge = f"<span class=\"msg-badge\" data-msg-id=\"{html.escape(str(pos_id))}\">源</span> " if pos_id else ""
                neg_badge = f"<span class=\"msg-badge\" data-msg-id=\"{html.escape(str(neg_id))}\">源</span> " if neg_id else ""
                conflict = _short(_pick_risk([_strip_ai_prefix(x) for x in (it["positive"] + it["negative"]) ]), 200)

                parts.append(f"<div class=\"section-label\">【分歧观点{idx}】{html.escape(theme)}</div>")
                parts.append(
                    "<table class=\"counter-table\"><thead><tr><th>正方</th><th>反方</th><th>冲突点</th></tr></thead><tbody>"
                    + "<tr>"
                    + f"<td>{pos_badge}{html.escape(pos_txt)}</td>"
                    + f"<td>{neg_badge}{html.escape(neg_txt)}</td>"
                    + f"<td>{html.escape(conflict)}</td>"
                    + "</tr>"
                    + "</tbody></table>"
                )
            return "\n".join(parts)

        def _build_contacts_html() -> str:
            if not high_contacts:
                return "<p>近3天暂无评分≥60分且活跃的分析师。</p>"
            cards: list[str] = []
            for idx, c in enumerate(high_contacts[:20], 1):
                sender = c.get("name") or c.get("alias") or c.get("sender") or c.get("cid")
                rating = c.get("rating") or 0
                msg_rows: list[str] = []
                for msg in c.get("messages", [])[:3]:
                    summary = _strip_ai_prefix(msg.get("summary") or "")
                    if not summary:
                        continue
                    msg_id = str(msg.get("id") or "")
                    badge = f"<span class=\"msg-badge\" data-msg-id=\"{html.escape(msg_id)}\">源</span> " if msg_id else ""
                    msg_rows.append(f"<li>{badge}{html.escape(_short(summary, 120))}</li>")
                if not msg_rows:
                    continue
                cards.append(
                    f"<section class=\"contact-card\"><div class=\"section-label\">【分析师{idx}】{html.escape(sender)}（评分 {rating:.1f}）</div><ul>{''.join(msg_rows)}</ul></section>"
                )
            return "".join(cards)

        if "market" in module_filter and not result.get("market_markdown"):
            # 更紧凑：每类最多3条，降低噪声（并保证不为空）
            def _build_market_md_compact() -> str:
                total = len(enriched_messages)
                pos = sum(
                    1
                    for m in enriched_messages
                    if _has_any(str(m.get("content") or ""), POS) or (m.get("tone") == "positive")
                )
                neg = sum(
                    1
                    for m in enriched_messages
                    if _has_any(str(m.get("content") or ""), NEG) or (m.get("tone") == "negative")
                )
                md_lines: list[str] = [f"样本数：{total}；正向：{pos}；负向：{neg}"]
                topic_idx = 1
                for name, _ in CAT_RULES:
                    bucket = [m for m in enriched_messages if name in _match_cats(m)]
                    if not bucket:
                        continue
                    md_lines.append(f"\n【主题{topic_idx}：{name}】")
                    for m in bucket[:3]:
                        sent = m.get("sender") or m.get("sender_name") or "未知"
                        ts = m.get("time") or ""
                        text = _short(m.get("summary") or m.get("content") or "", 120)
                        tone = m.get("tone") or "neutral"
                        md_lines.append(f"- ({tone}) {text}（来源：{sent} {ts}）")
                    topic_idx += 1
                md_lines.append("\n【行动建议】聚焦确定性主线，跟踪关键数据点，控制仓位风险。")
                return "\n".join(md_lines)

            result["market_markdown"] = _build_market_md_compact()
            result["market_html"] = _build_market_html()
        if "meetings" in module_filter and not result.get("meetings_markdown"):
            result["meetings_markdown"] = _build_meetings_md()
            result["meetings_html"] = _build_meetings_html()
        if "counter" in module_filter and not result.get("counter_markdown"):
            result["counter_markdown"] = _build_counter_md()
            result["counter_html"] = _build_counter_html()
        if "contacts" in module_filter and not result.get("top_contacts_markdown"):
            result["top_contacts_markdown"] = _build_contacts_md()
            result["top_contacts_html"] = _build_contacts_html()

        # Newswatch 本地兜底：当大模型返回为空时，使用直接汇总构造基础舆情摘要
        if "newswatch" in module_filter and not result.get("newswatch_markdown"):
            try:
                from ..services.news_engine import engine_payload
                news_payload = engine_payload(limit=60)
                items = news_payload.get("items") or []
                analysis = news_payload.get("analysis") or {}
                if items:
                    cat_counter = Counter((it.get("category") or "其他") for it in items)
                    src_counter = Counter((it.get("source_name") or it.get("source_id") or "未知") for it in items)
                    tone_counter = Counter(((it.get("derived") or {}).get("tone") or "neutral") for it in items)

                    def _theme_key(title: str) -> str:
                        t = _strip_ai_prefix(title)
                        t = _re.sub(r"[（）()\[\]【】·]|\s+", "", t)
                        parts = _re.split(r"[:：、，。]\s*", t)
                        return parts[0][:12] if parts and parts[0] else t[:12]

                    theme_map: dict[str, list[dict]] = {}
                    for it in items:
                        title = it.get("title") or ""
                        key = _theme_key(title)
                        theme_map.setdefault(key, []).append(it)

                    def _clean_title(title: str) -> str:
                        t = _strip_ai_prefix(title)
                        return _short(t, 120)

                    lines: list[str] = [
                        f"数据概览：内置新闻引擎共监测 {len(items)} 条，来源 {len(src_counter)} 家；热度速度 {analysis.get('velocity', 0)}%，情绪净值 {analysis.get('sentiment_score', 0)}。"
                    ]
                    pos = tone_counter.get("positive", 0)
                    neg = tone_counter.get("negative", 0)
                    neu = tone_counter.get("neutral", 0)
                    lines.append(f"舆情温度：正面 {pos} / 中性 {neu} / 负面 {neg}，仍以{('负面' if neg>pos else '中性' if neu>=pos and neu>=neg else '正面')}为主调。")

                    for idx, (theme, arr) in enumerate(sorted(theme_map.items(), key=lambda kv: len(kv[1]), reverse=True)[:5], start=1):
                        sample = arr[0]
                        srcs = {it.get("source_name") or it.get("source_id") or "未知" for it in arr[:3]}
                        lines.append(
                            f"【新闻主题{idx}】{theme}（{len(arr)}条，主要来自 {', '.join(srcs)}）：{_clean_title(sample.get('title') or '')}"
                        )
                    if analysis.get('prediction'):
                        lines.append(f"趋势预测：{analysis.get('prediction')}")
                    lines.append("【关注动作】把新闻主题输入 AI 推理链路，结合情绪净值、热度速度与机会/风险信号，判断其对交易、仓位和客户沟通优先级的影响。")
                    result["newswatch_markdown"] = "\n".join(lines)
            except Exception:
                pass

        active_modules = [m for m in module_map.keys() if m in module_filter]
        return {
            "status": "ok",
            "result": result,
            "modules": active_modules,
            "temperature": temperature,
            "meta": base_payload.get("meta") or {},
            "_partial_errors": result.get("_partial_errors") or [],
        }
    except Exception as exc:  # pragma: no cover
        safe = html.escape(str(exc))
        err_markdown = f"**summary-local error:** {safe}"
        empty = {
            "market_markdown": err_markdown if "market" in module_filter else "",
            "meetings_markdown": err_markdown if "meetings" in module_filter else "",
            "counter_markdown": err_markdown if "counter" in module_filter else "",
            "top_contacts_markdown": err_markdown if "contacts" in module_filter else "",
            "market_html": "",
            "meetings_html": "",
            "counter_html": "",
            "top_contacts_html": "",
        }
        return {"status": "error", "result": empty, "modules": [m for m in module_filter], "temperature": temperature}



@router.post("/onepage")
def generate_onepage(payload: dict) -> dict:
    conf = load_ai_config()
    cfg = _get_onepage_config(conf)
    sections = payload.get("sections") if isinstance(payload, dict) else []
    if not isinstance(sections, list):
        sections = []
    period = str((payload or {}).get("period") or "最近").strip()
    template_style = str((payload or {}).get("template_style") or cfg.get("template_style") or "executive_blue").strip()
    safe_sections = []
    for item in sections[:12]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("module") or "模块").strip()[:80]
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        safe_sections.append({"module": str(item.get("module") or ""), "title": title, "text": text[:6000]})
    if not safe_sections:
        raise HTTPException(400, "empty sections")
    import json as _json
    system_prompt = str(cfg["prompt"].get("system") or _default_onepage_prompt()["system"])
    user_tpl = str(cfg["prompt"].get("user") or _default_onepage_prompt()["user"])
    sections_json = _json.dumps(safe_sections, ensure_ascii=False, indent=2)
    user_prompt = (user_tpl
        .replace("{period}", period)
        .replace("{template_style}", template_style)
        .replace("{sections_json}", sections_json))
    try:
        output = siliconflow_chat(
            [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            temperature=float(conf.get("onepage_temperature") if conf.get("onepage_temperature") is not None else 0.35),
            model_override=None,
            route_kind="mid",
            route_key="onepage",
        )
        raw = str(output or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            if raw.lower().startswith("json"):
                raw = raw[4:].strip()
        start = raw.find("{")
        end = raw.rfind("}")
        parsed = _json.loads(raw[start:end+1] if start >= 0 and end > start else raw)
        if not isinstance(parsed, dict):
            raise ValueError("onepage result is not object")
        parsed.setdefault("sections", [])
        return {"status": "ok", "result": parsed, "model": cfg.get("model"), "template_style": template_style}
    except Exception as e:
        return {"status": "error", "error": str(e), "fallback": True}


def _trim_words(text: Any, limit: int) -> str:
    raw = re.sub(r"\s+", " ", str(text or "")).strip()
    return raw[: max(0, limit)]


def _onepage_plain_brief(onepage: dict[str, Any]) -> str:
    parts: list[str] = []
    parts.append(f"标题：{_trim_words(onepage.get('hero_title'), 80)}")
    parts.append(f"副标题：{_trim_words(onepage.get('hero_subtitle'), 120)}")
    parts.append(f"核心结论：{_trim_words(onepage.get('key_takeaway'), 220)}")
    sections = onepage.get("sections") if isinstance(onepage.get("sections"), list) else []
    for idx, section in enumerate(sections[:7], 1):
        if not isinstance(section, dict):
            continue
        title = _trim_words(section.get("title") or f"模块{idx}", 40)
        bullets = section.get("bullets") if isinstance(section.get("bullets"), list) else []
        clean_bullets = [_trim_words(x, 90) for x in bullets[:3] if str(x or "").strip()]
        metrics = section.get("metrics") if isinstance(section.get("metrics"), dict) else {}
        metric_text = "；".join([f"{_trim_words(k, 12)}:{_trim_words(v, 22)}" for k, v in list(metrics.items())[:3]])
        hint = _trim_words(section.get("chart_hint"), 60)
        parts.append(f"{idx}. {title}：{'；'.join(clean_bullets)}。指标：{metric_text}。图形：{hint}")
    return "\n".join([p for p in parts if p.strip()])[:2600]


def _build_onepage_image_prompt(onepage: dict[str, Any], *, period: str, template_style: str) -> str:
    brief = _onepage_plain_brief(onepage)
    visual_prompt = _trim_words(onepage.get("visual_prompt"), 500)
    palette = "深蓝、青蓝、白底、少量绿色强调" if template_style != "fund_red" else "红色、金色、白底、少量深灰强调"
    return (
        "生成一张中文投研情报一页通海报，竖版，清晰可读，现代金融终端风格。\n"
        "必须是结构化信息图，不要流水账，不要密密麻麻长段文字。\n"
        "布局要求：顶部大标题；中间使用中心节点+6个分支的思维导图/关系图；右侧或底部放3个关键指标卡；底部放风险与行动清单。\n"
        "文字总量控制在约900个中文字以内；每个节点只放短句，字号足够大，留白充足。\n"
        "禁止生成很小的说明文字；禁止把以下材料逐字塞满页面。\n"
        f"配色：{palette}。周期：{period}。\n"
        "海报中文字必须为简体中文，标题醒目，节点文字准确。\n"
        f"{('视觉提示：' + visual_prompt + chr(10)) if visual_prompt else ''}"
        "参考内容如下，请二次概括后作图：\n"
        f"{brief}"
    )


def _resolve_onepage_image_target(conf: dict[str, Any]) -> dict[str, str]:
    targets = resolve_chat_targets(
        conf,
        route_kind="mid",
        route_key="onepage",
        model_override=None,
    )
    target = targets[0] if targets else {}
    api_url = str(conf.get("onepage_image_api_url") or target.get("api_url") or conf.get("api_url") or "").strip()
    api_key = str(conf.get("onepage_image_api_key") or target.get("api_key") or conf.get("api_key") or "").strip()
    model = str(conf.get("onepage_image_model") or DASHENG_CLOUD_ONEPAGE_MODEL).strip() or DASHENG_CLOUD_ONEPAGE_MODEL
    return {"api_url": api_url, "api_key": api_key, "model": model}


def _onepage_media_dir() -> str:
    path = os.path.abspath(os.path.join(os.getcwd(), "data", "onepage_media"))
    os.makedirs(path, exist_ok=True)
    return path


def _onepage_size_pair(value: str) -> tuple[int, int]:
    raw = str(value or "1024x1536").lower().strip()
    if raw not in {"1024x1024", "1024x1536", "1536x1024"}:
        raw = "1024x1536"
    w, h = raw.split("x", 1)
    return int(w), int(h)


def _mmx_env(api_key: str | None = None) -> dict[str, str]:
    env = os.environ.copy()
    key = str(api_key or env.get("MINIMAX_API_KEY") or "").strip()
    if key:
        env["MINIMAX_API_KEY"] = key
    return env


def _resolve_mmx_cli_key(conf: dict[str, Any]) -> str:
    return str(conf.get("onepage_image_api_key") or os.environ.get("MINIMAX_API_KEY") or "").strip()


def _run_mmx_image(
    prompt: str,
    *,
    api_key: str,
    size: str,
    timeout: int = 240,
) -> dict[str, Any] | None:
    width, height = _onepage_size_pair(size)
    out_dir = _onepage_media_dir()
    prefix = "onepage-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    cmd = [
        "mmx",
        "image",
        "generate",
        "--prompt",
        prompt,
        "--width",
        str(width),
        "--height",
        str(height),
        "--out-dir",
        out_dir,
        "--out-prefix",
        prefix,
        "--quiet",
        "--non-interactive",
    ]
    if api_key:
        cmd.extend(["--api-key", api_key])
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_mmx_env(api_key),
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(err or f"mmx image failed with code {proc.returncode}")
    lines = [x.strip() for x in (proc.stdout or "").splitlines() if x.strip()]
    if not lines:
        return None
    first = lines[-1]
    if os.path.exists(first):
        with open(first, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        return {
            "status": "ok",
            "model": "mmx image generate",
            "provider": "MiniMax CLI",
            "size": size,
            "quality": "cli",
            "mime_type": "image/png",
            "b64_json": b64,
            "file_path": first,
        }
    if first.startswith("http://") or first.startswith("https://"):
        return {
            "status": "ok",
            "model": "mmx image generate",
            "provider": "MiniMax CLI",
            "size": size,
            "quality": "cli",
            "mime_type": "image/png",
            "url": first,
        }
    if len(first) > 200 and all(ch.isalnum() or ch in "+/=" for ch in first[:160]):
        return {
            "status": "ok",
            "model": "mmx image generate",
            "provider": "MiniMax CLI",
            "size": size,
            "quality": "cli",
            "mime_type": "image/png",
            "b64_json": first,
        }
    return None


@router.post("/onepage-image")
def generate_onepage_image(payload: dict) -> dict:
    conf = load_ai_config()
    mode = str(conf.get("onepage_output_mode") or "auto").strip().lower()
    if mode == "local":
        return {"status": "skipped", "reason": "local_mode"}
    onepage = payload.get("onepage") if isinstance(payload, dict) and isinstance(payload.get("onepage"), dict) else {}
    if not onepage:
        raise HTTPException(400, "empty onepage")
    period = str((payload or {}).get("period") or "最近").strip()
    template_style = str((payload or {}).get("template_style") or conf.get("onepage_template_style") or "executive_blue").strip()
    target = _resolve_onepage_image_target(conf)
    api_url = target["api_url"].rstrip("/")
    api_key = target["api_key"]
    cli_api_key = _resolve_mmx_cli_key(conf)
    model = target["model"]
    image_prompt = _build_onepage_image_prompt(onepage, period=period, template_style=template_style)
    size = str(conf.get("onepage_image_size") or "1024x1536").strip()
    quality = str(conf.get("onepage_image_quality") or "medium").strip().lower()
    if not api_url or not api_key:
        try:
            cli_result = _run_mmx_image(image_prompt, api_key=cli_api_key, size=size)
            if cli_result:
                return cli_result
        except Exception as cli_exc:
            if mode == "image":
                raise HTTPException(502, f"MiniMax CLI生图失败: {cli_exc}") from cli_exc
        return {"status": "skipped", "reason": "missing_image_provider"}

    body = {
        "model": model,
        "prompt": image_prompt,
        "size": size,
        "n": 1,
    }
    if quality and quality != "auto":
        body["quality"] = quality
    # OpenAI-compatible image providers differ: some ignore response_format, some require it.
    body["response_format"] = "b64_json"
    try:
        resp = requests.post(
            api_url + "/images/generations",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=body,
            timeout=180,
        )
        if resp.status_code >= 400 and "response_format" in body:
            body.pop("response_format", None)
            resp = requests.post(
                api_url + "/images/generations",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=body,
                timeout=180,
            )
        resp.raise_for_status()
        data = resp.json()
        item = (data.get("data") or [{}])[0] if isinstance(data, dict) else {}
        b64 = str(item.get("b64_json") or item.get("base64") or "").strip()
        url = str(item.get("url") or "").strip()
        if not b64 and not url:
            raise ValueError("image provider returned no image")
        return {
            "status": "ok",
            "model": model,
            "provider": llm_client_service._safe_domain(api_url),  # type: ignore[attr-defined]
            "size": size,
            "quality": quality,
            "mime_type": "image/png",
            "b64_json": b64,
            "url": url,
        }
    except Exception as exc:
        try:
            cli_result = _run_mmx_image(image_prompt, api_key=cli_api_key, size=size)
            if cli_result:
                return cli_result
        except Exception as cli_exc:
            if mode == "image":
                raise HTTPException(502, f"onepage image generation failed: {exc}; MiniMax CLI failed: {cli_exc}") from cli_exc
        if mode == "image":
            raise HTTPException(502, f"onepage image generation failed: {exc}") from exc
        return {"status": "error", "fallback": True, "error": str(exc)}


def _collect_onepage_audio_source(payload: dict) -> str:
    onepage = payload.get("onepage") if isinstance(payload.get("onepage"), dict) else {}
    sections = payload.get("sections") if isinstance(payload.get("sections"), list) else []
    parts: list[str] = []
    if onepage:
        parts.append(_onepage_plain_brief(onepage))
    for item in sections[:12]:
        if not isinstance(item, dict):
            continue
        title = _trim_words(item.get("title") or item.get("module") or "模块", 60)
        text = _trim_words(item.get("text") or "", 900)
        if title or text:
            parts.append(f"{title}\n{text}")
    return "\n\n".join([p for p in parts if str(p or "").strip()])[:9000]


def _local_onepage_audio_script(source: str, duration_minutes: int) -> str:
    limit = 1500 if duration_minutes <= 5 else 3000
    intro = f"这里是 Deepsee AI 分析播报，时长约{duration_minutes}分钟。"
    body = _trim_words(source, max(800, limit - len(intro) - 60))
    outro = "以上是本次重点，请优先跟踪核心风险、会议线索和新闻催化。"
    return f"{intro}\n\n{body}\n\n{outro}"[:limit]


def _build_onepage_audio_script(payload: dict, conf: dict[str, Any]) -> str:
    duration = int(payload.get("duration_minutes") or 5)
    duration = 10 if duration >= 10 else 5
    source = _collect_onepage_audio_source(payload)
    if not source:
        raise HTTPException(400, "empty audio source")
    char_limit = 1500 if duration == 5 else 3000
    prompt = (
        f"请把下面的 AI 分析内容改写成适合中文口播的晨会播报稿，目标时长约{duration}分钟。\n"
        "要求：开头直接给结论；按“主线、催化、风险、行动”组织；不要逐条念原文；"
        "语气专业、自然、适合基金/投研场景；不要 Markdown；不要编号太多；"
        f"总字数控制在{char_limit}字以内。\n\n"
        f"材料：\n{source}"
    )
    try:
        script = siliconflow_chat(
            [{"role": "user", "content": prompt}],
            temperature=0.35,
            max_tokens=2200 if duration == 5 else 4200,
            model_override=None,
            route_kind="main",
            route_key="minuteswatch",
        )
        script = _trim_words(script, char_limit)
        return script or _local_onepage_audio_script(source, duration)
    except Exception:
        return _local_onepage_audio_script(source, duration)


def _run_mmx_speech(script: str, *, api_key: str, duration_minutes: int) -> dict[str, Any]:
    out_dir = _onepage_media_dir()
    out_path = os.path.join(out_dir, f"onepage-audio-{duration_minutes}m-{datetime.now().strftime('%Y%m%d-%H%M%S')}.mp3")
    cmd = [
        "mmx",
        "speech",
        "synthesize",
        "--text-file",
        "-",
        "--out",
        out_path,
        "--format",
        "mp3",
        "--language",
        "zh",
        "--quiet",
        "--non-interactive",
    ]
    if api_key:
        cmd.extend(["--api-key", api_key])
    proc = subprocess.run(
        cmd,
        input=script,
        capture_output=True,
        text=True,
        timeout=360,
        env=_mmx_env(api_key),
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(err or f"mmx speech failed with code {proc.returncode}")
    final_path = out_path if os.path.exists(out_path) else (proc.stdout or "").strip().splitlines()[-1].strip()
    if not final_path or not os.path.exists(final_path):
        raise RuntimeError("MiniMax CLI did not produce audio file")
    with open(final_path, "rb") as f:
        audio_b64 = base64.b64encode(f.read()).decode("ascii")
    return {
        "status": "ok",
        "duration_minutes": duration_minutes,
        "mime_type": "audio/mpeg",
        "b64_audio": audio_b64,
        "file_path": final_path,
        "script": script,
        "provider": "MiniMax CLI",
    }


@router.post("/onepage-audio")
def generate_onepage_audio(payload: dict) -> dict:
    conf = load_ai_config()
    duration = int((payload or {}).get("duration_minutes") or 5)
    duration = 10 if duration >= 10 else 5
    script = _build_onepage_audio_script(payload or {}, conf)
    api_key = _resolve_mmx_cli_key(conf)
    try:
        return _run_mmx_speech(script, api_key=api_key, duration_minutes=duration)
    except Exception as exc:
        raise HTTPException(502, f"MiniMax CLI语音生成失败: {exc}") from exc


@router.post("/summary-local")
def summary_local(payload: dict):
    return _run_summary_local(payload)
def _markdown_to_html(markdown_text: str) -> str:
    if not markdown_text:
        return ""
    # 将 `#123` 引用转换为可点击消息徽标
    import re
    md = re.sub(r"#(\d+)", r"<span class=\"msg-badge\" data-msg-id=\"\\1\">源</span>", markdown_text)
    lines = [line.rstrip() for line in md.strip().splitlines()]
    html_parts: list[str] = []
    list_open = False

    def close_list():
        nonlocal list_open
        if list_open:
            html_parts.append("</ul>")
            list_open = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("### "):
            close_list()
            html_parts.append(f"<h3>{html.escape(stripped[4:].strip())}</h3>")
        elif stripped.startswith("## "):
            close_list()
            html_parts.append(f"<h2>{html.escape(stripped[3:].strip())}</h2>")
        elif stripped.startswith("# "):
            close_list()
            html_parts.append(f"<h1>{html.escape(stripped[2:].strip())}</h1>")
        elif stripped.startswith("- "):
            if not list_open:
                html_parts.append("<ul>")
                list_open = True
            html_parts.append(f"<li>{html.escape(stripped[2:].strip())}</li>")
        else:
            close_list()
            html_parts.append(f"<p>{html.escape(stripped)}</p>")

    close_list()
    return "\n".join(html_parts)


def _default_onepage_prompt() -> dict[str, str]:
    return {
        "system": (
            "你是一名资深投研产品经理、财经信息架构师和信息图设计导演。"
            "你的任务不是拼接材料，而是把多个情报模块二次提炼为可直接用于一页通海报的结构化报告。"
            "必须中文输出，强调结论、证据、趋势、分歧、风险和行动。"
            "尤其要避免流水账和长段文字，要为思维导图、关系图和指标卡服务。"
        ),
        "user": (
            "请基于以下 AI 分析模块内容，生成一份一页通结构化 JSON。\n"
            "要求：\n"
            "1. 严格输出 JSON，不要 Markdown，不要代码块。\n"
            "2. 总内容控制在 3000 个中文字符以内；每条 bullet 控制在 45 字以内。\n"
            "3. 固定 7 个章节：核心结论、市场主线、新闻趋势、会议路演、分歧与风险、自媒体脉冲、公众号深读。\n"
            "4. 每章包含 title、subtitle、bullets(2-3条)、metrics(2-3个键值)、chart_hint。\n"
            "5. 增加 mind_map 字段：center、branches，branches 每项包含 label、summary、children(最多3个短词)。\n"
            "6. 增加 relations 字段：最多6条，格式 {from,to,label}，用于关系图。\n"
            "7. 增加 visual_prompt 字段：给生图模型的中文视觉提示，强调思维导图/关系图、少文字、大字号、金融信息图。\n"
            "8. 增加 hero_title、hero_subtitle、key_takeaway、heat_score(0-100)、sentiment。\n"
            "9. chart_hint 要描述适合生成的信息图：如思维导图、关系图、矩阵、时间轴、风险表。\n"
            "10. 不要照抄原文，合并重复信息，保留可行动判断。\n"
            "11. 如果某模块为空，用其他模块推断，不要输出空章节。\n\n"
            "模板风格：{template_style}\n"
            "统计周期：{period}\n"
            "模块材料 JSON：\n{sections_json}"
        ),
    }

def _get_onepage_config(conf: dict[str, Any]) -> dict[str, Any]:
    prompt = conf.get("onepage_prompt") if isinstance(conf.get("onepage_prompt"), dict) else {}
    defaults = _default_onepage_prompt()
    return {
        "template_style": str(conf.get("onepage_template_style") or "executive_blue").strip(),
        "prompt": {
            "system": str(prompt.get("system") or defaults["system"]),
            "user": str(prompt.get("user") or defaults["user"]),
        },
    }

@router.get("/test-main")
def test_main_model():
    conf = load_ai_config()
    info = {
        "api_url": conf.get("api_url"),
        "model": conf.get("model"),
        "has_key": bool(conf.get("api_key")),
    }
    try:
        out = siliconflow_chat([
            {"role": "system", "content": "你是一个测试助手，回答四个字：连接成功。"},
            {"role": "user", "content": "请输出“连接成功”四个字"},
        ], temperature=0.0)
        return {"status": "ok", "output": out, "config": info}
    except Exception as e:
        return {"status": "error", "error": str(e), "config": info}


@router.get("/test-tool")
def test_tool_model():
    conf = load_ai_config()
    info = {
        "api_url": conf.get("api_url"),
        "tool_model": conf.get("tool_model"),
        "has_key": bool(conf.get("api_key")),
    }
    try:
        out = siliconflow_tool_chat([
            {"role": "system", "content": "你是一个测试助手，回答四个字：连接成功。"},
            {"role": "user", "content": "请输出“连接成功”四个字"},
        ], temperature=0.0)
        return {"status": "ok", "output": out, "config": info}
    except Exception as e:
        return {"status": "error", "error": str(e), "config": info}


def _test_router_channel_connectivity(channel: dict[str, Any], lane: str, conf: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    cid = str(channel.get("id") or "").strip() or f"{lane}-unknown"
    model = str(channel.get("model") or "").strip()
    api_url = str(channel.get("api_url") or conf.get("api_url") or "https://api.siliconflow.cn/v1").strip()
    api_key = str(channel.get("api_key") or "").strip() or str(conf.get("api_key") or "").strip()
    has_key = bool(api_key or channel.get("has_api_key"))
    base = {
        "lane": lane,
        "channel_id": cid,
        "name": str(channel.get("name") or cid),
        "model": model,
        "api_url": api_url,
        "enabled": channel.get("enabled") is not False,
        "has_api_key": has_key,
    }
    if channel.get("enabled") is False:
        return {
            **base,
            "status": "disabled",
            "ok": False,
            "latency_ms": 0,
            "output": "",
            "error": "channel disabled",
        }
    if not model:
        return {
            **base,
            "status": "error",
            "ok": False,
            "latency_ms": 0,
            "output": "",
            "error": "missing model",
        }
    if not api_key:
        return {
            **base,
            "status": "error",
            "ok": False,
            "latency_ms": 0,
            "output": "",
            "error": "missing api key",
        }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    if "openrouter.ai" in api_url:
        headers.setdefault("HTTP-Referer", "https://localhost")
        headers.setdefault("X-Title", "Dr.Lemon Information Aggregation AI")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "你是一个测试助手，回答四个字：连接成功。"},
            {"role": "user", "content": "请输出“连接成功”四个字"},
        ],
        "temperature": 0.0,
        "max_tokens": 32,
        "stream": False,
    }
    if lane == "tool":
        payload["response_format"] = {"type": "json_object"}
    try:
        http_timeout = int(conf.get("http_timeout") or 20)
    except Exception:
        http_timeout = 20
    try:
        resp = llm_client_service._post_with_backoff(  # type: ignore[attr-defined]
            api_url.rstrip("/") + "/chat/completions",
            headers,
            payload,
            timeout=http_timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        content = llm_client_service._normalize_llm_content(  # type: ignore[attr-defined]
            data.get("choices", [{}])[0].get("message", {}).get("content", "")
        )
        latency_ms = max(1, int((time.perf_counter() - started) * 1000))
        return {
            **base,
            "status": "ok",
            "ok": True,
            "latency_ms": latency_ms,
            "output": str(content or "")[:120],
            "error": "",
        }
    except Exception as exc:
        latency_ms = max(1, int((time.perf_counter() - started) * 1000))
        return {
            **base,
            "status": "error",
            "ok": False,
            "latency_ms": latency_ms,
            "output": "",
            "error": str(exc)[:240],
        }


@router.get("/test-all-models")
def test_all_router_models():
    conf = load_ai_config()
    router = conf.get("model_router") if isinstance(conf.get("model_router"), dict) else {}
    lanes = {
        "main": [c for c in (router.get("main_channels") if isinstance(router.get("main_channels"), list) else []) if isinstance(c, dict)],
        "mid": [c for c in (router.get("mid_channels") if isinstance(router.get("mid_channels"), list) else []) if isinstance(c, dict)],
        "tool": [c for c in (router.get("tool_channels") if isinstance(router.get("tool_channels"), list) else []) if isinstance(c, dict)],
    }
    out: dict[str, list[dict[str, Any]]] = {"main": [], "mid": [], "tool": []}
    total = ok = disabled = 0
    for lane, channels in lanes.items():
        for channel in channels:
            row = _test_router_channel_connectivity(channel, lane, conf)
            out[lane].append(row)
            total += 1
            if row["status"] == "ok":
                ok += 1
            elif row["status"] == "disabled":
                disabled += 1
    return {
        "status": "ok",
        "summary": {
            "total": total,
            "ok": ok,
            "error": max(0, total - ok - disabled),
            "disabled": disabled,
        },
        "lanes": out,
    }


@router.get("/router-stats")
def router_stats():
    """Expose in-process routing runtime metrics for diagnostics/weight tuning."""
    return {"status": "ok", "stats": get_router_runtime_stats()}


@router.get("/route-preview")
def route_preview(route_kind: str = "main", route_key: str = "default", model_override: str | None = None):
    """Preview the actual backend target order for a module route without exposing secrets."""
    kind = str(route_kind or "main").strip().lower()
    if kind not in {"main", "tool", "mid"}:
        raise HTTPException(status_code=400, detail="route_kind must be main/tool/mid")
    key = str(route_key or "default").strip() or "default"
    conf = load_ai_config()
    targets = resolve_chat_targets(
        conf,
        route_kind=kind,
        route_key=key,
        model_override=model_override,
    )
    safe_targets = []
    for idx, target in enumerate(targets):
        api_url = str(target.get("api_url") or "").strip()
        safe_targets.append({
            "order": idx + 1,
            "channel_id": target.get("channel_id"),
            "model": target.get("model"),
            "api_url": api_url,
            "provider": llm_client_service._safe_domain(api_url),  # type: ignore[attr-defined]
            "has_api_key": bool(str(target.get("api_key") or "").strip()),
            "fallback": not bool(target.get("channel_id")),
        })
    return {
        "status": "ok",
        "route_kind": kind,
        "route_key": key,
        "router_enabled": bool((conf.get("model_router") or {}).get("enabled")) if isinstance(conf.get("model_router"), dict) else False,
        "targets": safe_targets,
    }


@router.post("/router-stats/reset")
def router_stats_reset(body: dict | None = None):
    target = ""
    if isinstance(body, dict):
        target = str(body.get("channel_id") or "").strip()
    reset_router_runtime_stats(channel_id=target or None)
    return {"status": "ok", "channel_id": target or None}


# ===== 缓存调试与清理 =====
@router.get("/debug/caches")
def debug_caches():
    """返回缓存统计：内存/数据库/新闻源缓存规模。"""
    mem = len(SUMMARY_CACHE)
    db_count = 0
    try:
        db = SessionLocal()
        try:
            row = db.execute(_sql_text("SELECT COUNT(1) FROM sync_state WHERE key LIKE 'summary_cache:%'"))
            db_count = int(list(row)[0][0]) if row is not None else 0
        finally:
            db.close()
    except Exception:
        db_count = 0
    news_count = 0
    try:
        from ..services import news_client as _nc
        news_count = len(getattr(_nc, "_CACHE", {}) or {})
    except Exception:
        news_count = 0
    return {"summary_cache_memory": mem, "summary_cache_db": db_count, "news_cache": news_count}


@router.post("/summary/cache/clear")
def clear_summary_cache():
    """清空进程内与持久化的总结缓存。"""
    try:
        SUMMARY_CACHE.clear()
    except Exception:
        pass
    cleared = 0
    try:
        db = SessionLocal()
        try:
            r1 = db.execute(_sql_text("SELECT COUNT(1) FROM sync_state WHERE key LIKE 'summary_cache:%'"))
            cleared = int(list(r1)[0][0]) if r1 is not None else 0
            db.execute(_sql_text("DELETE FROM sync_state WHERE key LIKE 'summary_cache:%'"))
            db.commit()
        finally:
            db.close()
    except Exception:
        pass
    return {"status": "ok", "cleared_db": cleared, "memory": 0}


@router.post("/test-tool-summary")
def test_tool_summary(payload: dict):
    from datetime import datetime

    text = str(payload.get("text") or "").strip()
    if not text:
        raise HTTPException(400, "text required")
    conf = load_ai_config()
    prompt_conf = (conf.get("tool_prompts") or {}).get("message_summary") or DEFAULT_TOOL_PROMPTS["message_summary"]
    system_prompt = prompt_conf.get("system") or DEFAULT_TOOL_PROMPTS["message_summary"]["system"]
    user_template = prompt_conf.get("user") or DEFAULT_TOOL_PROMPTS["message_summary"]["user"]
    sample = {
        "id": "demo",
        "time": datetime.utcnow().isoformat(),
        "sender": payload.get("sender") or "测试联系人",
        "content": text,
    }
    payload_json = json.dumps([sample], ensure_ascii=False)
    if "{{messages_json}}" in user_template:
        user_content = user_template.replace("{{messages_json}}", payload_json)
    else:
        user_content = user_template + "\n\n数据：\n" + payload_json
    messages_payload = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    try:
        raw = siliconflow_tool_chat(
            messages_payload,
            temperature=payload.get("temperature") or 0.1,
            route_key="messages",
        )
    except Exception as exc:
        # 直返错误文本，便于前端查看具体问题
        return {
            "status": "error",
            "error": str(exc),
            "raw": None,
            "config": {"tool_model": conf.get("tool_model"), "api_url": conf.get("api_url")},
        }

    # 尝试解析为 JSON；若失败也返回 200 并带上 raw，方便前端直观核对
    parsed = None
    try:
        raw_clean = str(raw or "").strip()
        if raw_clean.startswith("```"):
            lines = raw_clean.split("\n")
            if lines:
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            raw_clean = "\n".join(lines).strip()
        parsed = json.loads(raw_clean)
    except Exception:
        parsed = None
    return {
        "status": "ok",
        "raw": raw,
        "parsed": parsed,
        "config": {"tool_model": conf.get("tool_model"), "api_url": conf.get("api_url")},
    }
