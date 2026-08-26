from __future__ import annotations

import asyncio
import inspect
import logging
import weakref
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI

from .config import settings
from .db import SessionLocal
from .services.sync_service import sync_from_chatlog
from .services.email_engine import imap_fetch, FetchOptions
from .models import EmailAccount, ExtAdapter, SyncState
from .services.ext_adapter_service import ingest_adapter_logs
from .services import news_client, sync_runtime
from .services.wechat8061_sync import wechat8061_sync_loop
from .services.aggregation_retention import prune_aggregation_data
from .services.media_collector_runner import run_media_collector_once
from .services.cache_cleanup import cleanup_application_cache

logger = logging.getLogger(__name__)
_BACKGROUND_ERROR_MARKER_ATTR = "_deepsee_background_error_marker"
_BACKGROUND_TASK_ERROR_MARKERS: weakref.WeakKeyDictionary[
    asyncio.Task[object],
    object,
] = weakref.WeakKeyDictionary()
BACKGROUND_RUNTIME: dict[str, dict] = {}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bg_state(name: str) -> dict:
    state = BACKGROUND_RUNTIME.get(name)
    if state is None:
        state = {
            "name": name,
            "enabled": False,
            "running": False,
            "runs": 0,
            "failures": 0,
            "last_started_at": None,
            "last_finished_at": None,
            "last_success_at": None,
            "last_error_at": None,
            "last_error": None,
        }
        BACKGROUND_RUNTIME[name] = state
    return state


def _bg_mark_enabled(name: str, enabled: bool) -> None:
    state = _bg_state(name)
    state["enabled"] = bool(enabled)


def _clear_current_task_recorded_exception() -> None:
    try:
        current_task = asyncio.current_task()
    except RuntimeError:
        current_task = None
    if current_task is not None:
        _BACKGROUND_TASK_ERROR_MARKERS.pop(current_task, None)


def _bg_mark_start(name: str) -> None:
    _clear_current_task_recorded_exception()
    state = _bg_state(name)
    state["running"] = True
    state["runs"] = int(state.get("runs") or 0) + 1
    state["last_started_at"] = _utc_now()


def _bg_mark_success(name: str) -> None:
    _clear_current_task_recorded_exception()
    state = _bg_state(name)
    now = _utc_now()
    state["running"] = False
    state["last_finished_at"] = now
    state["last_success_at"] = now
    state["last_error"] = None


def _background_error_text(exc: BaseException) -> str:
    return str(exc).strip() or type(exc).__name__


def _bg_mark_error(name: str, exc: Exception) -> None:
    try:
        current_task = asyncio.current_task()
    except RuntimeError:
        current_task = None
    if current_task is not None:
        marker = object()
        try:
            setattr(exc, _BACKGROUND_ERROR_MARKER_ATTR, marker)
        except Exception:
            _BACKGROUND_TASK_ERROR_MARKERS.pop(current_task, None)
        else:
            _BACKGROUND_TASK_ERROR_MARKERS[current_task] = marker
    state = _bg_state(name)
    now = _utc_now()
    state["running"] = False
    state["failures"] = int(state.get("failures") or 0) + 1
    state["last_finished_at"] = now
    state["last_error_at"] = now
    state["last_error"] = _background_error_text(exc)
    logger.exception("background loop failed: %s", name)


_BACKGROUND_RUNTIME_NAMES = [
    "chatlog_sync",
    "wechat8061_sync",
    "email_sync",
    "ext_adapter_sync",
    "news_refresh",
    "news_snapshot",
    "media_collector",
    "summary_overlay",
    "aggregation_retention",
    "media_cache_cleanup",
]


def _runtime_age_seconds(value: str | None) -> int | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))
    except Exception:
        return None


def _runtime_health(state: dict) -> str:
    if bool(state.get("running")):
        return "running"
    if bool(state.get("last_error")):
        return "error"
    if not bool(state.get("enabled")):
        return "off"
    if not state.get("last_success_at") and not state.get("last_finished_at"):
        return "waiting"
    return "ok"


def get_background_runtime_snapshot() -> dict[str, dict]:
    for name in _BACKGROUND_RUNTIME_NAMES:
        _bg_state(name)
    snapshot: dict[str, dict] = {}
    for key, value in BACKGROUND_RUNTIME.items():
        state = dict(value)
        last_at = state.get("last_started_at") if state.get("running") else (
            state.get("last_success_at") or state.get("last_error_at") or state.get("last_finished_at")
        )
        state["health"] = _runtime_health(state)
        state["last_activity_at"] = last_at
        state["last_activity_age_seconds"] = _runtime_age_seconds(last_at)
        snapshot[key] = state
    return snapshot


def _load_ai_runtime_config(db) -> dict:
    try:
        from .models import SyncState
        import json as _json

        state = db.get(SyncState, "ai_runtime")
        if state and state.value:
            data = _json.loads(state.value) or {}
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}


def _message_visible_len(message) -> int:
    text = (getattr(message, "content_text", None) or "").strip()
    if not text:
        try:
            meta = getattr(message, "meta", None) or {}
            contents = meta.get("contents") if isinstance(meta, dict) else None
            parts: list[str] = []
            if isinstance(contents, dict):
                for key in ("content", "desc", "title", "url"):
                    value = contents.get(key)
                    if isinstance(value, str) and value.strip():
                        parts.append(value.strip())
            text = " ".join(parts).strip()
        except Exception:
            text = ""
    return len(text.replace("\n", " ").replace("\r", " ").replace("\t", " ").strip())


def run_summary_overlay_once(db, *, cfg: dict | None = None) -> dict[str, int]:
    from sqlalchemy import desc, select
    from .models import EmailMessage, Message
    from .services.ai_tools import ensure_message_features, populate_fallback_derived
    from .services.email_features import persist_email_features, persist_email_fallback

    cfg = cfg or _load_ai_runtime_config(db)
    result = {
        "wechat_fallback": 0,
        "wechat_tool": 0,
        "email_fallback": 0,
        "email_tool": 0,
    }

    if bool(cfg.get("enable_msg_tool_overlay", True)):
        cutoff = datetime.utcnow() - timedelta(days=3)
        recent_messages = db.execute(
            select(Message)
            .where(Message.timestamp >= cutoff)
            .order_by(desc(Message.timestamp), desc(Message.id))
            .limit(2000)
        ).scalars().all()
        result["wechat_fallback"] = int(populate_fallback_derived(db, recent_messages, force=False) or 0)
        pending_limit = max(1, int(cfg.get("msg_tool_overlay_limit", 100) or 100))
        pending_messages = []
        for msg in recent_messages:
            if _message_visible_len(msg) < 20:
                continue
            derived = msg.derived if isinstance(msg.derived, dict) else {}
            origin = str(derived.get("summary_origin") or "").lower()
            summary = str(derived.get("summary") or "").strip().lower()
            if origin == "tool" and summary.startswith("ai:"):
                continue
            pending_messages.append(msg)
            if len(pending_messages) >= pending_limit:
                break
        if pending_messages:
            info = ensure_message_features(
                db,
                pending_messages,
                force=False,
                concurrency=3,
                batch_size=100,
                temperature=0.1,
            )
            result["wechat_tool"] = int((info or {}).get("updated") or 0)

    if bool(cfg.get("enable_email_tool_overlay", True)):
        email_window = max(20, min(1000, int(cfg.get("email_overlay_window", 120) or 120)))
        email_cap = max(20, min(2000, int(cfg.get("email_overlay_cap", 160) or 160)))
        recent_emails = db.execute(
            select(EmailMessage)
            .order_by(desc(EmailMessage.sent_at), desc(EmailMessage.id))
            .limit(email_window)
        ).scalars().all()
        result["email_fallback"] = len(persist_email_fallback(db, recent_emails, force=False, commit=False))
        pending_emails = []
        for email in recent_emails:
            derived = email.derived if isinstance(email.derived, dict) else {}
            if str(derived.get("summary_origin") or "").lower() == "tool":
                continue
            pending_emails.append(email)
            if len(pending_emails) >= email_cap:
                break
        if pending_emails:
            result["email_tool"] = len(persist_email_features(db, pending_emails, force=False, commit=False))
    return result


def _run_chatlog_sync_job() -> None:
    db = SessionLocal()
    try:
        adapters = sync_runtime.ChatlogSyncRunAdapters(
            sync_from_chatlog=lambda run_db, since: sync_from_chatlog(run_db, since),
        )
        result = sync_runtime.execute_chatlog_sync_run(
            db,
            adapters=adapters,
            overlay_mode="inline",
            model_cls=SyncState,
        )
        if str(result.get("status") or "") == "error":
            error_code = str(result.get("error_code") or "SYNC-CHATLOG-UNKNOWN-001")
            error = str(result.get("error") or "chatlog sync failed")
            raise RuntimeError(f"{error_code}: {error}")
    finally:
        db.close()


def _run_summary_overlay_job() -> dict[str, int]:
    db = SessionLocal()
    try:
        stats = run_summary_overlay_once(db)
        db.commit()
        return stats
    finally:
        db.close()


def _run_aggregation_retention_job() -> dict:
    db = SessionLocal()
    try:
        retention_days = int(settings.__dict__.get("AGGREGATION_RETENTION_DAYS", 90) or 90)
        result = prune_aggregation_data(db, retention_days=retention_days)
        db.commit()
        return result
    finally:
        db.close()


def _run_media_cache_cleanup_job() -> dict:
    db = SessionLocal()
    try:
        result = cleanup_application_cache(
            db,
            ttl_hours=int(settings.__dict__.get("MEDIA_CACHE_TTL_HOURS", 720) or 720),
            max_mb=int(settings.__dict__.get("MEDIA_CACHE_MAX_MB", 256) or 256),
            dry_run=False,
        )
        db.commit()
        return result
    finally:
        db.close()


async def _sync_loop():
    loop_name = "chatlog_sync"
    interval = int(settings.__dict__.get("SYNC_INTERVAL_SECONDS", 0) or 0)
    if interval <= 0:
        _bg_mark_enabled(loop_name, False)
        return
    _bg_mark_enabled(loop_name, True)
    while True:
        try:
            _bg_mark_start(loop_name)
            await asyncio.to_thread(_run_chatlog_sync_job)
            _bg_mark_success(loop_name)
        except Exception as exc:
            _bg_mark_error(loop_name, exc)
        await asyncio.sleep(interval)


async def _email_loop():
    loop_name = "email_sync"
    interval = int(settings.__dict__.get("EMAIL_SYNC_INTERVAL_SECONDS", 0) or 0)
    if interval <= 0:
        _bg_mark_enabled(loop_name, False)
        return
    _bg_mark_enabled(loop_name, True)
    while True:
        try:
            _bg_mark_start(loop_name)
            db = SessionLocal()
            try:
                accounts = db.query(EmailAccount).filter(EmailAccount.enabled == True).all()  # noqa
                for acc in accounts:
                    try:
                        imap_fetch(db, acc, FetchOptions(limit=50, unseen_only=True))
                    except Exception as exc:
                        logger.warning(
                            "background subtask failed: imap_fetch account_id=%s email=%s: %s",
                            getattr(acc, "id", None),
                            getattr(acc, "email_address", None),
                            exc,
                        )
                db.commit()
            finally:
                db.close()
            _bg_mark_success(loop_name)
        except Exception as exc:
            _bg_mark_error(loop_name, exc)
        await asyncio.sleep(interval)


async def _ext_adapter_loop():
    loop_name = "ext_adapter_sync"
    # poll every 30 seconds by default to ingest adapter logs if configured
    interval = 30
    base_dir = settings.__dict__.get("LANGBOT_ADAPTER_LOG_DIR") or "./data/adapters"
    if not base_dir:
        _bg_mark_enabled(loop_name, False)
        return
    _bg_mark_enabled(loop_name, True)
    while True:
        try:
            _bg_mark_start(loop_name)
            db = SessionLocal()
            try:
                adapters = db.query(ExtAdapter).filter(ExtAdapter.enabled == True).all()  # noqa
                for a in adapters:
                    try:
                        ingest_adapter_logs(db, a, a.config.get("log_dir") or base_dir, since=None)
                    except Exception as exc:
                        logger.warning(
                            "background subtask failed: ingest_adapter_logs adapter_id=%s name=%s: %s",
                            getattr(a, "id", None),
                            getattr(a, "name", None),
                            exc,
                        )
                db.commit()
            finally:
                db.close()
            _bg_mark_success(loop_name)
        except Exception as exc:
            _bg_mark_error(loop_name, exc)
        await asyncio.sleep(interval)


async def _news_loop():
    loop_name = "news_refresh"
    interval = int(settings.__dict__.get("NEWSNOW_REFRESH_INTERVAL_SECONDS", 0) or 0)
    if interval <= 0:
        _bg_mark_enabled(loop_name, False)
        return
    _bg_mark_enabled(loop_name, True)
    while True:
        try:
            _bg_mark_start(loop_name)
            # Trigger upstream refresh and warm local caches
            try:
                await asyncio.to_thread(news_client.newsnow_refresh)
            except Exception as exc:
                logger.warning("background subtask failed: newsnow_refresh: %s", exc)
            try:
                await asyncio.to_thread(news_client.newsnow_sources, force=True)
            except Exception as exc:
                logger.warning("background subtask failed: newsnow_sources: %s", exc)
            try:
                # warm a small slice
                await asyncio.to_thread(news_client.newsnow_news, limit=20, simple=True)
            except Exception as exc:
                logger.warning("background subtask failed: newsnow_news warmup: %s", exc)
            _bg_mark_success(loop_name)
        except Exception as exc:
            _bg_mark_error(loop_name, exc)
        await asyncio.sleep(max(30, interval))


async def _news_snapshot_loop():
    loop_name = "news_snapshot"
    """Periodic writer for news sentiment dataset snapshots.

    Writes compact JSON snapshots under data/datasets/ every
    settings.NEWS_SNAPSHOT_INTERVAL_SECONDS seconds using direct collectors.
    """
    interval = int(settings.__dict__.get("NEWS_SNAPSHOT_INTERVAL_SECONDS", 0) or 0)
    if interval <= 0:
        _bg_mark_enabled(loop_name, False)
        return
    _bg_mark_enabled(loop_name, True)
    # short initial delay to allow app startup
    await asyncio.sleep(3)
    while True:
        try:
            _bg_mark_start(loop_name)
            # Best-effort: collect and persist a fresh snapshot
            try:
                await asyncio.to_thread(news_client.write_news_snapshot, limit=200)
            except Exception as exc:
                logger.warning("background subtask failed: write_news_snapshot: %s", exc)
            # Optionally warm aggregation cache for UI consumption
            try:
                await asyncio.to_thread(news_client.direct_from_sources_json, limit=50)
            except Exception as exc:
                logger.warning("background subtask failed: direct_from_sources_json: %s", exc)
            _bg_mark_success(loop_name)
        except Exception as exc:
            _bg_mark_error(loop_name, exc)
        await asyncio.sleep(max(60, interval))


def _seconds_until_daily(hour: int, minute: int) -> int:
    now = datetime.now()
    target = now.replace(hour=max(0, min(23, hour)), minute=max(0, min(59, minute)), second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return max(1, int((target - now).total_seconds()))


async def _media_collector_loop():
    loop_name = "media_collector"
    enabled = bool(settings.__dict__.get("MEDIA_COLLECTOR_DAILY_ENABLED", True))
    if not enabled:
        _bg_mark_enabled(loop_name, False)
        return
    _bg_mark_enabled(loop_name, True)
    while True:
        hour = int(settings.__dict__.get("MEDIA_COLLECTOR_DAILY_HOUR", 5) or 5)
        minute = int(settings.__dict__.get("MEDIA_COLLECTOR_DAILY_MINUTE", 0) or 0)
        await asyncio.sleep(_seconds_until_daily(hour, minute))
        try:
            _bg_mark_start(loop_name)
            result = await asyncio.to_thread(run_media_collector_once, hot=True, search=True, authors=True)
            if not bool(result.get("ok")) and not bool(result.get("running")):
                raise RuntimeError("media collector failed")
            logger.info("media collector refreshed: %s", {
                "ok": result.get("ok"),
                "tasks": result.get("tasks"),
            })
            _bg_mark_success(loop_name)
        except Exception as exc:
            _bg_mark_error(loop_name, exc)


async def _aggregation_retention_loop():
    loop_name = "aggregation_retention"
    interval = int(settings.__dict__.get("AGGREGATION_RETENTION_INTERVAL_SECONDS", 86400) or 0)
    if interval <= 0:
        _bg_mark_enabled(loop_name, False)
        return
    _bg_mark_enabled(loop_name, True)
    await asyncio.sleep(5)
    while True:
        try:
            _bg_mark_start(loop_name)
            result = await asyncio.to_thread(_run_aggregation_retention_job)
            logger.info("aggregation retention pruned: %s", result)
            _bg_mark_success(loop_name)
        except Exception as exc:
            _bg_mark_error(loop_name, exc)
        await asyncio.sleep(max(3600, interval))


async def _media_cache_cleanup_loop():
    loop_name = "media_cache_cleanup"
    enabled = bool(settings.__dict__.get("MEDIA_CACHE_CLEANUP_ENABLED", True))
    interval = int(settings.__dict__.get("MEDIA_CACHE_CLEANUP_INTERVAL_SECONDS", 86400) or 0)
    if not enabled or interval <= 0:
        _bg_mark_enabled(loop_name, False)
        return
    _bg_mark_enabled(loop_name, True)
    await asyncio.sleep(10)
    while True:
        try:
            _bg_mark_start(loop_name)
            result = await asyncio.to_thread(_run_media_cache_cleanup_job)
            logger.info("media cache cleanup finished: %s", result)
            _bg_mark_success(loop_name)
        except Exception as exc:
            _bg_mark_error(loop_name, exc)
        await asyncio.sleep(max(3600, interval))


async def _summary_overlay_loop():
    loop_name = "summary_overlay"
    interval = int(settings.__dict__.get("SUMMARY_OVERLAY_INTERVAL_SECONDS", 3600) or 0)
    if interval <= 0:
        _bg_mark_enabled(loop_name, False)
        return
    _bg_mark_enabled(loop_name, True)
    await asyncio.sleep(5)
    while True:
        try:
            _bg_mark_start(loop_name)
            stats = await asyncio.to_thread(_run_summary_overlay_job)
            logger.info("summary overlay updated: %s", stats)
            _bg_mark_success(loop_name)
        except Exception as exc:
            _bg_mark_error(loop_name, exc)
        await asyncio.sleep(max(300, interval))


@dataclass(frozen=True)
class BackgroundLoopSpec:
    name: str
    enabled: bool
    runner: Callable[[], Awaitable[None]]


def _build_background_loop_specs() -> list[BackgroundLoopSpec]:
    interval = int(settings.__dict__.get("SYNC_INTERVAL_SECONDS", 0) or 0)
    wechat8061_enabled = False
    news_interval = int(settings.__dict__.get("NEWSNOW_REFRESH_INTERVAL_SECONDS", 0) or 0)
    snap_interval = int(settings.__dict__.get("NEWS_SNAPSHOT_INTERVAL_SECONDS", 0) or 0)
    media_collector_enabled = bool(settings.__dict__.get("MEDIA_COLLECTOR_DAILY_ENABLED", True))
    summary_interval = int(settings.__dict__.get("SUMMARY_OVERLAY_INTERVAL_SECONDS", 3600) or 0)
    retention_interval = int(settings.__dict__.get("AGGREGATION_RETENTION_INTERVAL_SECONDS", 86400) or 0)
    cache_cleanup_enabled = bool(settings.__dict__.get("MEDIA_CACHE_CLEANUP_ENABLED", True))
    cache_cleanup_interval = int(settings.__dict__.get("MEDIA_CACHE_CLEANUP_INTERVAL_SECONDS", 86400) or 0)

    return [
        BackgroundLoopSpec("chatlog_sync", interval > 0, _sync_loop),
        BackgroundLoopSpec("wechat8061_sync", wechat8061_enabled, wechat8061_sync_loop),
        # 邮件同步保持“仅手动触发”，不再定时自动拉取。
        BackgroundLoopSpec("email_sync", False, _email_loop),
        BackgroundLoopSpec(
            "ext_adapter_sync",
            bool(settings.__dict__.get("LANGBOT_ADAPTER_LOG_DIR")),
            _ext_adapter_loop,
        ),
        BackgroundLoopSpec("news_refresh", news_interval > 0, _news_loop),
        BackgroundLoopSpec("news_snapshot", snap_interval > 0, _news_snapshot_loop),
        BackgroundLoopSpec("media_collector", media_collector_enabled, _media_collector_loop),
        BackgroundLoopSpec("summary_overlay", summary_interval > 0, _summary_overlay_loop),
        BackgroundLoopSpec("aggregation_retention", retention_interval > 0, _aggregation_retention_loop),
        BackgroundLoopSpec(
            "media_cache_cleanup",
            cache_cleanup_enabled and cache_cleanup_interval > 0,
            _media_cache_cleanup_loop,
        ),
    ]


class BackgroundRuntime:
    def __init__(
        self,
        spec_provider: Callable[[], list[BackgroundLoopSpec]] = _build_background_loop_specs,
    ) -> None:
        self._spec_provider = spec_provider
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._lifecycle_lock: asyncio.Lock | None = None
        self._lifecycle_loop: asyncio.AbstractEventLoop | None = None
        self._owner_loop: asyncio.AbstractEventLoop | None = None
        self._handled_tasks: weakref.WeakSet[asyncio.Task[None]] = weakref.WeakSet()

    @property
    def tasks(self) -> dict[str, asyncio.Task[None]]:
        return dict(self._tasks)

    def _handle_task_completion(self, name: str, task: asyncio.Task[None]) -> None:
        if task in self._handled_tasks:
            return
        self._handled_tasks.add(task)
        recorded_marker = _BACKGROUND_TASK_ERROR_MARKERS.pop(task, None)
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            exc = None

        if self._tasks.get(name) is not task:
            if exc is not None:
                logger.error(
                    "stale background loop exited unexpectedly: %s",
                    name,
                    exc_info=(type(exc), exc, exc.__traceback__),
                )
            return
        self._tasks.pop(name, None)
        state = _bg_state(name)
        state["running"] = False
        exception_marker = getattr(exc, _BACKGROUND_ERROR_MARKER_ATTR, None) if exc is not None else None
        already_recorded = recorded_marker is not None and exception_marker is recorded_marker
        if exc is not None and not already_recorded:
            now = _utc_now()
            state["failures"] = int(state.get("failures") or 0) + 1
            state["last_finished_at"] = now
            state["last_error_at"] = now
            state["last_error"] = _background_error_text(exc)
            logger.error(
                "background loop exited unexpectedly: %s",
                name,
                exc_info=(type(exc), exc, exc.__traceback__),
            )
        if not self._tasks:
            self._owner_loop = None

    def _get_lifecycle_lock(self) -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        foreign_pending = [
            task
            for task in self._tasks.values()
            if not task.done() and task.get_loop() is not loop
        ]
        owner_is_foreign = self._owner_loop is not None and self._owner_loop is not loop
        if foreign_pending or (owner_is_foreign and any(not task.done() for task in self._tasks.values())):
            raise RuntimeError("background runtime has pending tasks owned by another event loop")

        if self._lifecycle_loop is not loop:
            if self._lifecycle_lock is not None and self._lifecycle_lock.locked():
                raise RuntimeError("background runtime lifecycle is active on another event loop")
            for name, task in list(self._tasks.items()):
                if task.done() and task.get_loop() is not loop:
                    self._handle_task_completion(name, task)
            self._lifecycle_lock = asyncio.Lock()
            self._lifecycle_loop = loop
        if self._owner_loop is None and any(not task.done() for task in self._tasks.values()):
            self._owner_loop = loop
        return self._lifecycle_lock

    async def start(self, app: FastAPI | None = None) -> "BackgroundRuntime":
        async with self._get_lifecycle_lock():
            if app is not None:
                app.state.background_runtime = self

            for name, task in list(self._tasks.items()):
                if task.done():
                    self._handle_task_completion(name, task)

            new_tasks: list[tuple[str, asyncio.Task[None]]] = []
            try:
                for spec in self._spec_provider():
                    _bg_mark_enabled(spec.name, spec.enabled)
                    current = self._tasks.get(spec.name)
                    if not spec.enabled or (current is not None and not current.done()):
                        continue
                    runner = spec.runner()
                    try:
                        task = asyncio.create_task(
                            runner,
                            name=f"deepsee-background:{spec.name}",
                        )
                    except BaseException:
                        if inspect.iscoroutine(runner):
                            runner.close()
                        raise
                    self._tasks[spec.name] = task
                    if self._owner_loop is None:
                        self._owner_loop = asyncio.get_running_loop()
                    new_tasks.append((spec.name, task))
                    task.add_done_callback(
                        lambda completed, name=spec.name: self._handle_task_completion(name, completed)
                    )
            except BaseException:
                for _name, task in new_tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(
                    *(task for _name, task in new_tasks),
                    return_exceptions=True,
                )
                for name, task in new_tasks:
                    self._handle_task_completion(name, task)
                raise
            return self

    async def shutdown(self) -> None:
        async with self._get_lifecycle_lock():
            owned_tasks = list(self._tasks.items())
            if not owned_tasks:
                return

            for _name, task in owned_tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*(task for _name, task in owned_tasks), return_exceptions=True)

            for name, task in owned_tasks:
                self._handle_task_completion(name, task)


BACKGROUND_TASK_RUNTIME = BackgroundRuntime()


async def start_background_loops(app: FastAPI | None = None) -> BackgroundRuntime:
    if app is None:
        runtime = BACKGROUND_TASK_RUNTIME
    else:
        runtime = getattr(app.state, "background_runtime", None)
        if runtime is None:
            runtime = BackgroundRuntime()
            app.state.background_runtime = runtime
    return await runtime.start(app)


async def stop_background_loops(app: FastAPI | None = None) -> None:
    runtime = getattr(getattr(app, "state", None), "background_runtime", None)
    await (runtime or BACKGROUND_TASK_RUNTIME).shutdown()
