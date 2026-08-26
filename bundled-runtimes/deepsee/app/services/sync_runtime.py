from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from time import perf_counter
from typing import Any, Callable

import requests


CHATLOG_LAST_SYNC_KEY = "chatlog_last_sync"
CHATLOG_LAST_RUN_KEY = "chatlog_sync_last_run"
CHATLOG_SYNC_POLICY_KEY = "chatlog_sync_policy"
DEFAULT_CHATLOG_SYNC_POLICY = {"max_attempts": 2, "sleep_seconds": 0.6}
WECHAT_DUAL_TRACK_POLICY_KEY = "wechat_dual_track_policy"
VALID_WECHAT_TRACKS = ("wechatapi", "chatlog", "wx_cli")


@dataclass
class ChatlogSyncRunAdapters:
    """Late-bound integration points used by a chatlog sync run."""

    sync_from_chatlog: Callable[[Any, datetime | None], dict[str, Any]] | None = None
    load_policy: Callable[[Any], dict[str, Any]] | None = None
    populate_fallback: Callable[[Any, datetime | None], Any] | None = None
    run_tool_overlay: Callable[[Any, Any, str], Any] | None = None
    refresh_snapshots: Callable[[Any], Any] | None = None
    refresh_contact_predictions: Callable[[Any, dict[str, Any]], Any] | None = None
    persist_run: Callable[[Any, dict[str, Any]], Any] | None = None


@dataclass
class DualTrackSyncAdapters:
    """Late-bound integration points used by a WeChat dual-track sync run."""

    load_policy: Callable[[Any], dict[str, Any]] | None = None
    get_wechatapi_state: Callable[[Any], dict[str, Any]] | None = None
    get_chatlog_state: Callable[[Any], dict[str, Any]] | None = None
    get_wx_cli_state: Callable[[Any], dict[str, Any]] | None = None
    sync_full: Callable[[Any, int], dict[str, Any]] | None = None
    sync_from_wx_cli: Callable[[Any, int], dict[str, Any]] | None = None
    refresh_snapshots: Callable[[Any], Any] | None = None
    persist_run: Callable[[Any, dict[str, Any]], Any] | None = None


@dataclass(frozen=True)
class _DeferredPostCommitAction:
    stage: str
    starter: Callable[[], Any]


def classify_sync_error(exc: Exception) -> tuple[str, bool]:
    """Map sync exceptions to stable error_code + retryable flag."""
    if isinstance(exc, (requests.Timeout, TimeoutError)):
        return "SYNC-CHATLOG-TIMEOUT-001", True
    if isinstance(exc, (requests.ConnectionError, ConnectionError, OSError)):
        return "SYNC-CHATLOG-UNAVAILABLE-001", True
    if isinstance(exc, requests.HTTPError):
        status = None
        try:
            status = int(getattr(getattr(exc, "response", None), "status_code", 0) or 0)
        except Exception:
            status = 0
        if status >= 500:
            return "SYNC-CHATLOG-UPSTREAM-5XX-001", True
        if status >= 400:
            return "SYNC-CHATLOG-UPSTREAM-4XX-001", False
    msg = str(exc).lower()
    if "timed out" in msg or "timeout" in msg:
        return "SYNC-CHATLOG-TIMEOUT-001", True
    if "remote end closed connection" in msg or "connection aborted" in msg or "connection reset" in msg:
        return "SYNC-CHATLOG-UNAVAILABLE-001", True
    return "SYNC-CHATLOG-UNKNOWN-001", False


def run_with_retry(
    fn: Callable[[], Any],
    *,
    max_attempts: int = 2,
    sleep_seconds: float = 0.6,
    on_error: Callable[[Exception], None] | None = None,
) -> tuple[Any | None, int, Exception | None]:
    """Run fn with error-code-aware retry strategy.

    Returns (result, attempts, last_error).
    """
    attempts = max(1, int(max_attempts or 1))
    last_error: Exception | None = None
    attempted = 0
    for i in range(1, attempts + 1):
        attempted = i
        try:
            return fn(), i, None
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if on_error:
                try:
                    on_error(exc)
                except Exception:
                    pass
            _, retryable = classify_sync_error(exc)
            if i >= attempts or not retryable:
                break
            if sleep_seconds > 0:
                time.sleep(float(sleep_seconds))
    return None, attempted, last_error


def _get_row_value(db: Any, model_cls: Any, key: str) -> str | None:
    row = db.get(model_cls, key)
    return (row.value if row else None)


def _upsert_row_value(db: Any, model_cls: Any, key: str, value: str) -> None:
    row = db.get(model_cls, key)
    if not row:
        row = model_cls(key=key, value=value)
    else:
        row.value = value
        if hasattr(row, "updated_at"):
            row.updated_at = datetime.utcnow()
    db.add(row)


def persist_sync_run(db: Any, model_cls: Any, run_payload: dict[str, Any]) -> None:
    payload = json.dumps(run_payload or {}, ensure_ascii=False)
    _upsert_row_value(db, model_cls, CHATLOG_LAST_RUN_KEY, payload)


def _safe_json_dict(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def normalize_chatlog_sync_policy(raw: Any) -> dict[str, Any]:
    policy = dict(DEFAULT_CHATLOG_SYNC_POLICY)
    if not isinstance(raw, dict):
        return policy
    if "max_attempts" in raw:
        try:
            policy["max_attempts"] = max(1, min(5, int(raw.get("max_attempts") or 2)))
        except Exception:
            pass
    if "sleep_seconds" in raw:
        try:
            policy["sleep_seconds"] = max(0.0, min(3.0, float(raw.get("sleep_seconds") or 0.6)))
        except Exception:
            pass
    return policy


def get_chatlog_sync_policy(db: Any, *, model_cls: Any) -> dict[str, Any]:
    row = db.get(model_cls, CHATLOG_SYNC_POLICY_KEY)
    parsed = _safe_json_dict(row.value if row else None)
    return normalize_chatlog_sync_policy(parsed)


def save_chatlog_sync_policy(db: Any, *, model_cls: Any, payload: Any) -> dict[str, Any]:
    policy = normalize_chatlog_sync_policy(payload)
    _upsert_row_value(db, model_cls, CHATLOG_SYNC_POLICY_KEY, json.dumps(policy, ensure_ascii=False))
    return policy


def normalize_track_list(value: Any, *, default: list[str]) -> list[str]:
    if isinstance(value, str):
        raw_items = [item.strip() for item in value.split(",")]
    elif isinstance(value, list):
        raw_items = [str(item or "").strip() for item in value]
    else:
        raw_items = []
    tracks: list[str] = []
    for item in raw_items:
        if item in VALID_WECHAT_TRACKS and item not in tracks:
            tracks.append(item)
    for item in default:
        if item in VALID_WECHAT_TRACKS and item not in tracks:
            tracks.append(item)
    return tracks


def legacy_dual_track_selection(mode: str) -> tuple[list[str], list[str]]:
    if mode == "wechatapi_only":
        return ["wechatapi"], ["wechatapi", "chatlog", "wx_cli"]
    if mode == "chatlog_only":
        return ["chatlog", "wx_cli"], ["chatlog", "wx_cli", "wechatapi"]
    return ["wechatapi", "chatlog", "wx_cli"], ["wechatapi", "chatlog", "wx_cli"]


def _bounded_sync_days(value: Any, *, default: int = 1) -> int:
    try:
        return max(1, min(90, int(value or default)))
    except Exception:
        return default


def normalize_dual_track_policy(raw: Any) -> dict[str, Any]:
    raw_policy = dict(raw) if isinstance(raw, dict) else {}
    policy: dict[str, Any] = {
        "mode": "custom",
        "enabled_tracks": ["wechatapi", "chatlog", "wx_cli"],
        "track_order": ["wechatapi", "chatlog", "wx_cli"],
        "use_multiple_tracks": False,
        "chatlog_window_days": 1,
    }
    policy.update(raw_policy)
    policy["chatlog_window_days"] = _bounded_sync_days(policy.get("chatlog_window_days"))
    mode = str(policy.get("mode") or "").strip()
    legacy_enabled, legacy_order = legacy_dual_track_selection(mode)
    if "enabled_tracks" not in raw_policy and "track_order" not in raw_policy:
        policy["enabled_tracks"] = legacy_enabled
        policy["track_order"] = legacy_order
    policy["track_order"] = normalize_track_list(
        policy.get("track_order"),
        default=list(VALID_WECHAT_TRACKS),
    )
    enabled = normalize_track_list(policy.get("enabled_tracks"), default=[])
    if not enabled:
        enabled = ["wechatapi"]
    policy["enabled_tracks"] = [
        track for track in policy["track_order"] if track in enabled
    ]
    for track in enabled:
        if track not in policy["enabled_tracks"]:
            policy["enabled_tracks"].append(track)
    policy["use_multiple_tracks"] = bool(policy.get("use_multiple_tracks"))
    policy["mode"] = "custom"
    return policy


def get_dual_track_policy(db: Any, *, model_cls: Any) -> dict[str, Any]:
    row = db.get(model_cls, WECHAT_DUAL_TRACK_POLICY_KEY)
    raw = _safe_json_dict(row.value if row else None)
    return normalize_dual_track_policy(raw)


def save_dual_track_policy(
    db: Any,
    *,
    model_cls: Any,
    payload: Any,
) -> dict[str, Any]:
    current = get_dual_track_policy(db, model_cls=model_cls)
    if isinstance(payload, dict):
        current.update(payload)
    order = normalize_track_list(
        current.get("track_order"),
        default=list(VALID_WECHAT_TRACKS),
    )
    enabled = normalize_track_list(current.get("enabled_tracks"), default=[])
    enabled = [track for track in order if track in set(enabled)]
    if not enabled:
        enabled = [order[0] if order else "wechatapi"]
    policy = {
        "mode": "custom",
        "enabled_tracks": enabled,
        "track_order": order,
        "use_multiple_tracks": bool(current.get("use_multiple_tracks")),
        "chatlog_window_days": _bounded_sync_days(current.get("chatlog_window_days")),
    }
    _upsert_row_value(
        db,
        model_cls,
        WECHAT_DUAL_TRACK_POLICY_KEY,
        json.dumps(policy, ensure_ascii=False),
    )
    return policy


def _resolve_sync_state_model(model_cls: Any | None) -> Any:
    if model_cls is not None:
        return model_cls
    from ..models import SyncState

    return SyncState


def _default_sync_from_chatlog(db: Any, since: datetime | None) -> dict[str, Any]:
    from .sync_service import sync_from_chatlog

    return sync_from_chatlog(db, since)


def _default_populate_fallback(db: Any, since: datetime | None) -> dict[str, Any]:
    from datetime import timedelta

    from sqlalchemy import select

    from ..models import Message
    from .ai_tools import populate_fallback_derived

    cutoff = since or (datetime.utcnow() - timedelta(days=3))
    recent = db.execute(
        select(Message)
        .where(Message.timestamp >= cutoff)
        .order_by(Message.id.desc())
        .limit(5000)
    ).scalars().all()
    populate_fallback_derived(db, recent, force=False, commit=False)
    return {
        "message_ids": [int(message.id) for message in recent if getattr(message, "id", None) is not None],
        "messages": recent,
    }


def _load_ai_runtime_config(db: Any) -> dict[str, Any]:
    try:
        from ..models import SyncState

        state = db.get(SyncState, "ai_runtime")
        parsed = _safe_json_dict(state.value if state else None)
        return parsed or {}
    except Exception:
        return {}


def _message_visible_len(message: Any) -> int:
    text = str(getattr(message, "content_text", None) or "").strip()
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


def _run_inline_tool_overlay(db: Any, fallback_result: Any) -> None:
    from sqlalchemy import select

    from ..models import Message
    from .ai_tools import ensure_message_features

    context = fallback_result if isinstance(fallback_result, dict) else {}
    ids = [int(value) for value in (context.get("message_ids") or [])]
    messages = context.get("messages") if isinstance(context.get("messages"), list) else None
    if not messages and ids:
        messages = db.execute(select(Message).where(Message.id.in_(ids))).scalars().all()
    if not messages:
        return
    cfg = _load_ai_runtime_config(db)
    if not bool(cfg.get("enable_msg_tool_overlay", True)):
        return
    try:
        pending_limit = max(1, int(cfg.get("msg_tool_overlay_limit", 60) or 60))
    except Exception:
        pending_limit = 60
    pending_messages: list[Any] = []
    for message in messages:
        if _message_visible_len(message) < 20:
            continue
        derived = getattr(message, "derived", None)
        derived = derived if isinstance(derived, dict) else {}
        origin = str(derived.get("summary_origin") or "").lower()
        summary = str(derived.get("summary") or "").strip().lower()
        if origin == "tool" and summary.startswith("ai:"):
            continue
        pending_messages.append(message)
        if len(pending_messages) >= pending_limit:
            break
    if not pending_messages:
        return
    ensure_message_features(
        db,
        pending_messages,
        force=False,
        concurrency=1,
        batch_size=1,
        temperature=0.1,
        commit=False,
    )


def _start_async_tool_overlay(message_ids: list[int]) -> threading.Thread:
    def _overlay(message_ids: list[int]) -> None:
        from sqlalchemy import select

        from ..db import SessionLocal
        from ..models import Message
        from .ai_tools import ensure_message_features

        session = SessionLocal()
        try:
            cfg = _load_ai_runtime_config(session)
            if not bool(cfg.get("enable_msg_tool_overlay", True)):
                return
            rows = session.execute(select(Message).where(Message.id.in_(message_ids))).scalars().all()
            concurrency = int(cfg.get("default_concurrency", 3) or 3)
            ensure_message_features(
                session,
                rows,
                force=False,
                concurrency=max(1, min(16, concurrency)),
            )
        except Exception:
            pass
        finally:
            session.close()

    thread = threading.Thread(target=_overlay, args=(message_ids,), daemon=True)
    thread.start()
    return thread


def _defer_async_tool_overlay(fallback_result: Any) -> _DeferredPostCommitAction | None:
    context = fallback_result if isinstance(fallback_result, dict) else {}
    ids = tuple(int(value) for value in (context.get("message_ids") or []))
    if not ids:
        return None
    return _DeferredPostCommitAction(
        stage="tool_overlay",
        starter=lambda: _start_async_tool_overlay(list(ids)),
    )


def _default_run_tool_overlay(db: Any, fallback_result: Any, mode: str) -> Any:
    if str(mode or "async").lower() == "inline":
        _run_inline_tool_overlay(db, fallback_result)
        return
    return _defer_async_tool_overlay(fallback_result)


def _default_refresh_snapshots(db: Any) -> Any:
    from .snapshot_service import refresh_default_snapshots

    return refresh_default_snapshots(db)


def _parse_sync_datetime(value: Any) -> datetime | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _default_refresh_contact_predictions(db: Any, sync_result: dict[str, Any]) -> dict[str, Any]:
    if int(sync_result.get("inserted") or 0) <= 0:
        return {"status": "skipped", "reason": "no_new_messages"}
    if not hasattr(db, "execute"):
        return {"status": "skipped", "reason": "unsupported_session"}

    from .contact_scoring import extract_prediction_events_to_db

    result = extract_prediction_events_to_db(
        db,
        time_from=_parse_sync_datetime(sync_result.get("since") or sync_result.get("from")),
        time_to=_parse_sync_datetime(sync_result.get("until") or sync_result.get("to")),
        force=False,
    )
    return {"status": "ok", **dict(result or {})}


def _resolve_chatlog_run_adapters(
    adapters: ChatlogSyncRunAdapters | None,
    *,
    model_cls: Any,
) -> ChatlogSyncRunAdapters:
    supplied = adapters or ChatlogSyncRunAdapters()
    return ChatlogSyncRunAdapters(
        sync_from_chatlog=supplied.sync_from_chatlog or _default_sync_from_chatlog,
        load_policy=supplied.load_policy
        or (lambda db: get_chatlog_sync_policy(db, model_cls=model_cls)),
        populate_fallback=supplied.populate_fallback or _default_populate_fallback,
        run_tool_overlay=supplied.run_tool_overlay or _default_run_tool_overlay,
        refresh_snapshots=supplied.refresh_snapshots or _default_refresh_snapshots,
        refresh_contact_predictions=supplied.refresh_contact_predictions
        or _default_refresh_contact_predictions,
        persist_run=supplied.persist_run
        or (lambda db, payload: persist_sync_run(db, model_cls, payload)),
    )


def _run_timing_payload(
    *,
    run_id: str,
    status: str,
    started_at: datetime,
    started_clock: float,
    attempts: int,
    error_code: str | None,
    error: str | None,
    fetched: int,
    inserted: int,
    since: Any,
    until: Any,
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "status": status,
        "started_at": started_at.isoformat(),
        "ended_at": datetime.utcnow().isoformat(),
        "duration_ms": int((perf_counter() - started_clock) * 1000),
        "attempts": int(attempts),
        "error_code": error_code,
        "error": error,
        "fetched": int(fetched or 0),
        "inserted": int(inserted or 0),
        "since": since,
        "until": until,
    }


def _safe_rollback(db: Any) -> None:
    try:
        db.rollback()
    except Exception:
        pass


def _finalize_chatlog_failure(
    db: Any,
    *,
    resolved: ChatlogSyncRunAdapters,
    run_id: str,
    started_at: datetime,
    started_clock: float,
    attempts: int,
    error: Exception,
    since: datetime | None,
    rollback: bool,
) -> dict[str, Any]:
    if rollback:
        _safe_rollback(db)
    error_code, _retryable = classify_sync_error(error)
    until = datetime.now().isoformat()
    response: dict[str, Any] = {
        "status": "error",
        "run_id": run_id,
        "attempts": int(attempts),
        "error_code": error_code,
        "error": str(error),
        "fetched": 0,
        "inserted": 0,
        "since": since.isoformat() if since else None,
        "until": until,
    }
    run_payload = _run_timing_payload(
        run_id=run_id,
        status="error",
        started_at=started_at,
        started_clock=started_clock,
        attempts=attempts,
        error_code=error_code,
        error=str(error),
        fetched=0,
        inserted=0,
        since=response["since"],
        until=until,
    )
    try:
        resolved.persist_run(db, run_payload)
        db.commit()
    except Exception as persist_error:  # noqa: BLE001
        _safe_rollback(db)
        response["run_persist_error"] = str(persist_error)
    return response


def _flush_primary_sync_state(db: Any) -> None:
    flush = getattr(db, "flush", None)
    if callable(flush):
        flush()


def _run_isolated_postprocess_stage(db: Any, operation: Callable[[], Any]) -> Any:
    """Run one stage in a savepoint when the session supports nested transactions."""
    begin_nested = getattr(db, "begin_nested", None)
    flush = getattr(db, "flush", None)
    if not callable(begin_nested) or not callable(flush):
        return operation()

    with begin_nested():
        no_autoflush = getattr(db, "no_autoflush", None)
        if no_autoflush is None:
            result = operation()
        else:
            with no_autoflush:
                result = operation()
        flush()
        return result


def execute_chatlog_sync_run(
    db: Any,
    *,
    since: datetime | None = None,
    adapters: ChatlogSyncRunAdapters | None = None,
    model_cls: Any | None = None,
    overlay_mode: str = "async",
) -> dict[str, Any]:
    """Execute one observable chatlog run with shared retry and post-processing semantics."""
    sync_state_model = _resolve_sync_state_model(model_cls)
    resolved = _resolve_chatlog_run_adapters(adapters, model_cls=sync_state_model)
    started_at = datetime.utcnow()
    started_clock = perf_counter()
    run_id = f"chatlog-{uuid.uuid4().hex[:12]}"
    attempts = 0

    try:
        policy = normalize_chatlog_sync_policy(resolved.load_policy(db))
    except Exception as exc:  # noqa: BLE001
        return _finalize_chatlog_failure(
            db,
            resolved=resolved,
            run_id=run_id,
            started_at=started_at,
            started_clock=started_clock,
            attempts=attempts,
            error=exc,
            since=since,
            rollback=True,
        )

    try:
        result, attempts, sync_error = run_with_retry(
            lambda: resolved.sync_from_chatlog(db, since),
            max_attempts=int(policy["max_attempts"]),
            sleep_seconds=float(policy["sleep_seconds"]),
            on_error=lambda _exc: db.rollback(),
        )
    except Exception as exc:  # noqa: BLE001
        return _finalize_chatlog_failure(
            db,
            resolved=resolved,
            run_id=run_id,
            started_at=started_at,
            started_clock=started_clock,
            attempts=attempts,
            error=exc,
            since=since,
            rollback=True,
        )

    if sync_error is not None:
        return _finalize_chatlog_failure(
            db,
            resolved=resolved,
            run_id=run_id,
            started_at=started_at,
            started_clock=started_clock,
            attempts=attempts,
            error=sync_error,
            since=since,
            rollback=False,
        )

    try:
        # SQLAlchemy begin_nested() flushes before creating its savepoint. Flush the
        # successful sync explicitly first so later stage failures cannot be
        # misclassified as pre-savepoint work or poison the outer transaction.
        _flush_primary_sync_state(db)

        response = dict(result or {})
        response["run_id"] = run_id
        response["attempts"] = int(attempts)
        postprocess_errors: list[dict[str, str]] = []
        deferred_post_commit_actions: list[_DeferredPostCommitAction] = []
        fallback_result: Any = None
        stages = (
            (
                "fallback_summary",
                lambda: resolved.populate_fallback(db, since),
            ),
            (
                "tool_overlay",
                lambda: resolved.run_tool_overlay(db, fallback_result, overlay_mode),
            ),
            (
                "snapshot_refresh",
                lambda: resolved.refresh_snapshots(db),
            ),
        )
        for stage, operation in stages:
            try:
                stage_result = _run_isolated_postprocess_stage(db, operation)
                if stage == "fallback_summary":
                    fallback_result = stage_result
                if isinstance(stage_result, _DeferredPostCommitAction):
                    deferred_post_commit_actions.append(stage_result)
            except Exception as exc:  # noqa: BLE001
                postprocess_errors.append({"stage": stage, "error": str(exc)})
                if stage == "snapshot_refresh":
                    response["snapshot_error"] = str(exc)
        if postprocess_errors:
            response["postprocess_errors"] = postprocess_errors

        run_payload = _run_timing_payload(
            run_id=run_id,
            status="ok",
            started_at=started_at,
            started_clock=started_clock,
            attempts=attempts,
            error_code=None,
            error=None,
            fetched=int(response.get("fetched") or 0),
            inserted=int(response.get("inserted") or 0),
            since=response.get("since"),
            until=response.get("until"),
        )
        if postprocess_errors:
            run_payload["postprocess_errors"] = postprocess_errors
        resolved.persist_run(db, run_payload)
        db.commit()
        post_commit_errors: list[dict[str, str]] = []
        for action in deferred_post_commit_actions:
            try:
                action.starter()
            except Exception as exc:  # noqa: BLE001
                post_commit_errors.append({"stage": action.stage, "error": str(exc)})
        try:
            response["contact_prediction_refresh"] = resolved.refresh_contact_predictions(db, response)
        except Exception as exc:  # noqa: BLE001
            post_commit_errors.append({"stage": "contact_prediction_refresh", "error": str(exc)})
        if post_commit_errors:
            response["post_commit_errors"] = post_commit_errors
        return response
    except Exception as exc:  # noqa: BLE001
        return _finalize_chatlog_failure(
            db,
            resolved=resolved,
            run_id=run_id,
            started_at=started_at,
            started_clock=started_clock,
            attempts=attempts,
            error=exc,
            since=since,
            rollback=True,
        )


def get_wechatapi_track_state(db: Any) -> dict[str, Any]:
    from .wechat_gateway import load_config as load_wechat_gateway_config
    from .wechatapi_client import WechatApiClient

    cfg = load_wechat_gateway_config(db)
    configured = bool(
        str(cfg.get("base_url") or "").strip()
        and str(cfg.get("token") or "").strip()
        and str(cfg.get("app_id") or "").strip()
    )
    state: dict[str, Any] = {
        "name": "wechatapi",
        "role": "实时轨道",
        "configured": configured,
        "enabled": bool(cfg.get("enabled")),
        "outbound_enabled": bool(cfg.get("outbound_enabled")),
        "callback_public_url": str(cfg.get("callback_public_url") or "").strip(),
        "healthy": False,
        "status": "not_configured",
        "message": "未配置 wechatapi 网关",
    }
    if not configured:
        return state
    try:
        result = WechatApiClient(
            base_url=str(cfg.get("base_url") or ""),
            token=str(cfg.get("token") or ""),
            header_name=str(cfg.get("header_name") or "VideosApi-token"),
            app_id=str(cfg.get("app_id") or ""),
        ).check_online()
        state.update(
            {
                "healthy": True,
                "status": "ok",
                "message": "wechatapi 在线，实时回调可作为主轨道",
                "result": result,
            }
        )
    except Exception as exc:  # noqa: BLE001
        state.update({"status": "error", "message": str(exc)})
    return state


def get_chatlog_track_state(_db: Any = None) -> dict[str, Any]:
    from .deployment_status import probe_chatlog_http

    state: dict[str, Any] = {
        "name": "chatlog",
        "role": "本地兜底轨道",
        "configured": True,
        "healthy": False,
        "status": "unknown",
        "message": "",
    }
    try:
        probe = probe_chatlog_http()
        ok = bool(probe.get("ok"))
        state.update(
            {
                "healthy": ok,
                "status": "ok" if ok else "error",
                "message": "chatlog 本地服务可用"
                if ok
                else str(probe.get("error") or "chatlog unavailable"),
                "result": probe,
            }
        )
    except Exception as exc:  # noqa: BLE001
        state.update({"status": "error", "message": str(exc)})
    return state


def get_wx_cli_track_state(_db: Any = None) -> dict[str, Any]:
    from .deployment_status import probe_wx_cli

    state: dict[str, Any] = {
        "name": "wx_cli",
        "role": "本地 CLI 增强兜底",
        "configured": True,
        "healthy": False,
        "status": "unknown",
        "message": "",
    }
    try:
        probe = probe_wx_cli(timeout=3)
        ok = bool(probe.get("ok"))
        state.update(
            {
                "healthy": ok,
                "status": "ok" if ok else "error",
                "message": "wx-cli 本地服务可用"
                if ok
                else str(probe.get("error") or "wx-cli unavailable"),
                "result": probe,
            }
        )
    except Exception as exc:  # noqa: BLE001
        state.update({"status": "error", "message": str(exc)})
    return state


def _default_sync_full(db: Any, days: int) -> dict[str, Any]:
    from .sync_service import sync_full

    return sync_full(db, days=days)


def _default_sync_from_wx_cli(db: Any, days: int) -> dict[str, Any]:
    from .sync_service import sync_from_wx_cli

    return sync_from_wx_cli(db, days=days)


def _resolve_dual_track_adapters(
    adapters: DualTrackSyncAdapters | None,
    *,
    model_cls: Any,
) -> DualTrackSyncAdapters:
    supplied = adapters or DualTrackSyncAdapters()
    return DualTrackSyncAdapters(
        load_policy=supplied.load_policy
        or (lambda db: get_dual_track_policy(db, model_cls=model_cls)),
        get_wechatapi_state=supplied.get_wechatapi_state or get_wechatapi_track_state,
        get_chatlog_state=supplied.get_chatlog_state or get_chatlog_track_state,
        get_wx_cli_state=supplied.get_wx_cli_state or get_wx_cli_track_state,
        sync_full=supplied.sync_full or _default_sync_full,
        sync_from_wx_cli=supplied.sync_from_wx_cli or _default_sync_from_wx_cli,
        refresh_snapshots=supplied.refresh_snapshots or _default_refresh_snapshots,
        persist_run=supplied.persist_run
        or (lambda db, payload: persist_sync_run(db, model_cls, payload)),
    )


def _probe_track(
    track: str,
    operation: Callable[[Any], dict[str, Any]],
    db: Any,
) -> dict[str, Any]:
    try:
        state = operation(db)
        return dict(state or {})
    except Exception as exc:  # noqa: BLE001
        return {
            "name": track,
            "configured": True,
            "healthy": False,
            "status": "error",
            "message": str(exc),
        }


def execute_dual_track_sync_run(
    db: Any,
    *,
    days: int | None = None,
    adapters: DualTrackSyncAdapters | None = None,
    model_cls: Any | None = None,
) -> dict[str, Any]:
    """Execute enabled WeChat tracks in policy order without cross-track failure coupling."""
    sync_state_model = _resolve_sync_state_model(model_cls)
    resolved = _resolve_dual_track_adapters(adapters, model_cls=sync_state_model)
    policy = normalize_dual_track_policy(resolved.load_policy(db))
    requested_days = _bounded_sync_days(
        days if days is not None else policy.get("chatlog_window_days")
    )
    started_at = datetime.utcnow()
    started_clock = perf_counter()
    run_id = f"wechat-dual-{uuid.uuid4().hex[:12]}"
    wechatapi = _probe_track("wechatapi", resolved.get_wechatapi_state, db)
    chatlog = _probe_track("chatlog", resolved.get_chatlog_state, db)
    wx_cli = _probe_track("wx_cli", resolved.get_wx_cli_state, db)
    track_states = {"wechatapi": wechatapi, "chatlog": chatlog, "wx_cli": wx_cli}
    enabled = set(policy["enabled_tracks"])
    enabled_order = [track for track in policy["track_order"] if track in enabled]
    execution_order = enabled_order if policy["use_multiple_tracks"] else enabled_order[:1]
    actions: list[dict[str, Any]] = []
    chatlog_result: dict[str, Any] | None = None
    wx_cli_result: dict[str, Any] | None = None

    for track in execution_order:
        state = track_states.get(track) or {}
        if track == "wechatapi":
            actions.append(
                {
                    "track": "wechatapi",
                    "status": "ok" if state.get("healthy") else "error",
                    "reason": state.get("message")
                    or ("wechatapi 在线" if state.get("healthy") else "wechatapi 不可用"),
                }
            )
            continue
        if not state.get("healthy"):
            actions.append(
                {
                    "track": track,
                    "status": "error",
                    "reason": state.get("message") or f"{track} unavailable",
                }
            )
            continue
        try:
            if track == "chatlog":
                chatlog_result = dict(resolved.sync_full(db, requested_days) or {})
                result = chatlog_result
                reason = "已按优先级使用 chatlog 补齐窗口数据"
            elif track == "wx_cli":
                wx_cli_result = dict(resolved.sync_from_wx_cli(db, requested_days) or {})
                result = wx_cli_result
                reason = "已按优先级使用 wx-cli 补齐窗口数据"
            else:
                continue
            resolved.refresh_snapshots(db)
            db.commit()
            actions.append(
                {
                    "track": track,
                    "status": "ok",
                    "reason": reason,
                    "fetched": int(result.get("fetched") or 0),
                    "inserted": int(result.get("inserted") or 0),
                }
            )
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            actions.append({"track": track, "status": "error", "reason": str(exc)})

    ok = any(item.get("status") == "ok" for item in actions)
    payload: dict[str, Any] = {
        "run_id": run_id,
        "status": "ok" if ok else "error",
        "started_at": started_at.isoformat(),
        "ended_at": datetime.utcnow().isoformat(),
        "duration_ms": int((perf_counter() - started_clock) * 1000),
        "policy": policy,
        "days": requested_days,
        "enabled_order": enabled_order,
        "execution_order": execution_order,
        "tracks": track_states,
        "actions": actions,
        "chatlog": chatlog_result,
        "wx_cli": wx_cli_result,
    }
    result_for_run = chatlog_result or wx_cli_result or {}
    run_payload = _run_timing_payload(
        run_id=run_id,
        status=payload["status"],
        started_at=started_at,
        started_clock=started_clock,
        attempts=1,
        error_code=None if ok else "SYNC-WECHAT-DUAL-TRACK-001",
        error=None
        if ok
        else "; ".join(str(item.get("reason") or "") for item in actions),
        fetched=int(result_for_run.get("fetched") or 0),
        inserted=int(result_for_run.get("inserted") or 0),
        since=result_for_run.get("since") or result_for_run.get("from"),
        until=result_for_run.get("until") or result_for_run.get("to"),
    )
    try:
        resolved.persist_run(db, run_payload)
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    return payload


def build_sync_state_payload(db: Any, *, _model_cls: Any) -> dict[str, Any]:
    last_sync = _get_row_value(db, _model_cls, CHATLOG_LAST_SYNC_KEY)
    last_run_raw = _get_row_value(db, _model_cls, CHATLOG_LAST_RUN_KEY)
    last_run = _safe_json_dict(last_run_raw)

    out: dict[str, Any] = {
        "last_sync": last_sync,
        "last_run": last_run,
    }

    # Best-effort lag estimate, compatible with existing callers.
    lag_seconds = None
    if isinstance(last_sync, str) and last_sync:
        try:
            dt = datetime.fromisoformat(last_sync.replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                dt = dt.astimezone().replace(tzinfo=None)
            lag_seconds = max(0, int((datetime.now() - dt).total_seconds()))
        except Exception:
            lag_seconds = None
    out["lag_seconds"] = lag_seconds
    return out
