from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import Message, SyncState, WechatSubsession, WechatSubsessionTurn
from .llm_client import DEFAULT_TOOL_PROMPTS, load_ai_config, siliconflow_chat
from .wechat_gateway import _coerce_message_time, evaluate_auto_reply_rules, load_trigger_rules

_PRIVATE_WAKEUP_PREFIX = "wechat_gateway:private_wakeup:"


def _render_template(tpl: str, ctx: dict[str, Any]) -> str:
    out = tpl or ""
    for k, v in (ctx or {}).items():
        out = out.replace("{{" + k + "}}", str(v if v is not None else ""))
    return out


def _load_subsession_reply_config(db: Session, subsession_id: str | None) -> dict[str, Any] | None:
    sid = str(subsession_id or "").strip()
    if not sid:
        return None
    row = db.get(WechatSubsession, sid)
    if not row or not bool(row.enabled):
        return None
    return {
        "id": row.id,
        "name": row.name,
        "system_prompt": str(row.system_prompt or "").strip() or None,
        "model_route_kind": str(row.model_route_kind or "").strip() or None,
        "model_route_key": str(row.model_route_key or "").strip() or None,
        "model_override": str(row.model_override or "").strip() or None,
        "rolling_summary": str(row.rolling_summary or "").strip() or None,
        "pinned_memory": row.pinned_memory if isinstance(row.pinned_memory, dict) else None,
        "history_max_messages": max(0, int(row.history_max_messages or 30)),
        "history_max_tokens": max(0, int(row.history_max_tokens or 4000)),
        "allow_cross_chat_context": bool(row.allow_cross_chat_context),
        "allow_cross_sender_context": bool(row.allow_cross_sender_context),
    }


def _private_wakeup_key(chat_id: str) -> str:
    return f"{_PRIVATE_WAKEUP_PREFIX}{str(chat_id or '').strip()}"


def _private_wakeup_rules(rules: dict[str, Any]) -> dict[str, Any]:
    return {
        "window_seconds": max(0, int(rules.get("private_wakeup_window_seconds") or 180)),
        "whitelist_enabled": bool(rules.get("private_wakeup_whitelist_enabled")),
        "whitelist_chat_ids": {str(x or "").strip() for x in (rules.get("private_wakeup_whitelist_chat_ids") or []) if str(x or "").strip()},
        "exit_commands": {str(x or "").strip() for x in (rules.get("private_wakeup_exit_commands") or []) if str(x or "").strip()},
    }


def _private_wakeup_allowed_for_chat(chat_id: str, rules: dict[str, Any]) -> bool:
    cfg = _private_wakeup_rules(rules)
    effective_chat_id = str(chat_id or "").strip()
    if not effective_chat_id:
        return False
    if not cfg["whitelist_enabled"]:
        return True
    return effective_chat_id in cfg["whitelist_chat_ids"]


def _record_private_wakeup(db: Session, *, chat_id: str, wake_time: Any) -> None:
    effective_chat_id = str(chat_id or "").strip()
    if not effective_chat_id:
        return
    baseline = _coerce_message_time(wake_time) or datetime.now()
    key = _private_wakeup_key(effective_chat_id)
    row = db.get(SyncState, key)
    value = baseline.isoformat()
    if row is None:
        db.add(SyncState(key=key, value=value, updated_at=baseline))
    else:
        row.value = value
        row.updated_at = baseline
        db.add(row)
    db.flush()


def _clear_private_wakeup(db: Session, *, chat_id: str) -> None:
    effective_chat_id = str(chat_id or "").strip()
    if not effective_chat_id:
        return
    row = db.get(SyncState, _private_wakeup_key(effective_chat_id))
    if row is None:
        return
    db.delete(row)
    db.flush()


def _private_recent_wakeup_active(db: Session, *, chat_id: str, baseline_time: Any, wake_window_seconds: int = 180) -> bool:
    effective_chat_id = str(chat_id or "").strip()
    if not effective_chat_id:
        return False
    baseline = _coerce_message_time(baseline_time)
    if baseline is None:
        return False
    row = db.get(SyncState, _private_wakeup_key(effective_chat_id))
    if row is None:
        return False
    wake_time = _coerce_message_time((row.value or "").strip()) or row.updated_at
    if wake_time is None:
        return False
    return baseline - wake_time <= timedelta(seconds=int(wake_window_seconds or 0))


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~3 chars per token for CJK, ~4 for mixed."""
    if not text:
        return 0
    chars = len(text)
    cjk = sum(1 for c in text if '\u4e00' <= c <= '\u9fff' or '\u3040' <= c <= '\u30ff')
    return max(1, int(cjk / 3 + (chars - cjk) / 4))


def _build_subsession_history(
    db: Session,
    *,
    subsession_id: str,
    chat_id: str,
    sender_id: str | None,
    history_max_messages: int,
    history_max_tokens: int,
    allow_cross_chat: bool,
    allow_cross_sender: bool,
) -> list[dict[str, str]]:
    """Build a message history array from subsession turns, respecting context isolation settings."""
    if history_max_messages <= 0:
        return []

    from sqlalchemy import and_

    filters = [WechatSubsessionTurn.subsession_id == subsession_id]
    if not allow_cross_chat and chat_id:
        filters.append(WechatSubsessionTurn.chat_id == chat_id)
    if not allow_cross_sender and sender_id:
        filters.append(WechatSubsessionTurn.sender_id == sender_id)

    base_q = (
        db.query(WechatSubsessionTurn)
        .filter(and_(*filters))
        .filter(WechatSubsessionTurn.content_text_snapshot.isnot(None))
        .filter(WechatSubsessionTurn.content_text_snapshot != "")
        .order_by(WechatSubsessionTurn.timestamp.asc())
    )

    turns = base_q.order_by(WechatSubsessionTurn.id.desc()).limit(history_max_messages * 2).all()

    if not turns:
        return []

    turns = sorted(turns, key=lambda t: t.id)
    if len(turns) > history_max_messages:
        turns = turns[-history_max_messages:]

    if history_max_tokens > 0:
        history: list[dict[str, str]] = []
        token_budget = history_max_tokens
        for t in reversed(turns):
            role = "assistant" if (t.direction or "") == "out" else "user"
            body = str(t.content_text_snapshot or "").strip()
            cost = _estimate_tokens(body)
            if cost > token_budget:
                if not history:
                    body = body[: int(token_budget * 4)]
                    cost = _estimate_tokens(body)
                    token_budget -= cost
                    if body:
                        history.insert(0, {"role": role, "content": body})
                break
            token_budget -= cost
            history.insert(0, {"role": role, "content": body})
        return history

    return [
        {"role": "assistant" if (t.direction or "") == "out" else "user",
         "content": str(t.content_text_snapshot or "").strip()}
        for t in turns
    ]


def generate_local_reply(db: Session, payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(400, "invalid payload")

    message_id = payload.get("message_id")
    message_text = str(payload.get("message_text") or "").strip()
    operation_type = str(payload.get("operation_type") or "答").strip() or "答"
    prompt_key = str(payload.get("prompt_key") or "").strip()
    sender_name = str(payload.get("sender_name") or "").strip()
    talker_name = str(payload.get("talker_name") or "").strip()
    chat_id = str(payload.get("chat_id") or "").strip()
    sender_id = str(payload.get("sender_id") or "").strip()
    subsession_id = str(payload.get("subsession_id") or "").strip()
    is_group = bool(payload.get("is_group"))

    if not message_text and message_id is not None:
        try:
            mid = int(message_id)
            msg = db.get(Message, mid)
            if msg:
                message_text = str(msg.content_text or "").strip()
                sender_name = sender_name or str(msg.sender_name or msg.sender_id or "").strip()
                talker_name = talker_name or str(msg.talker_name or msg.chat_id or "").strip()
                chat_id = chat_id or str(msg.chat_id or "").strip()
                sender_id = sender_id or str(msg.sender_id or "").strip()
                is_group = is_group or str(msg.chat_id or "").strip().endswith("@chatroom")
        except Exception:
            pass

    if not message_text:
        raise HTTPException(400, "message_text required")

    effective_chat_id = chat_id or talker_name
    effective_sender_id = sender_id or sender_name or None
    effective_is_group = bool(is_group or str(effective_chat_id or "").endswith("@chatroom"))
    message_time = payload.get("message_time") or payload.get("timestamp")
    trigger_rules = load_trigger_rules(db)
    wake_cfg = _private_wakeup_rules(trigger_rules)

    if not effective_is_group and message_text in wake_cfg["exit_commands"]:
        _clear_private_wakeup(db, chat_id=str(effective_chat_id or "").strip())
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise
        return {
            "status": "blocked",
            "reason": "private_wakeup_exited",
            "rule": {
                "scope": "wechat_gateway",
                "allowed": False,
                "reason": "private_wakeup_exited",
                "matched_by": "private_wakeup_exit_command",
            },
        }

    try:
        reply_gate = evaluate_auto_reply_rules(
            db,
            chat_id=str(effective_chat_id or "").strip(),
            sender_id=str(effective_sender_id or "").strip() or None,
            text=message_text,
            is_group=effective_is_group,
            message_time=message_time,
            wait_for_human_reply_suppression=bool(payload.get("wait_for_human_reply_suppression")),
            message_meta=payload.get("message_meta") or payload.get("meta"),
        )
    except Exception:
        reply_gate = {"allowed": True, "reason": "rule_check_failed_open"}

    if (
        not reply_gate.get("allowed")
        and not effective_is_group
        and str(reply_gate.get("reason") or "") == "prefix_miss"
        and _private_wakeup_allowed_for_chat(str(effective_chat_id or "").strip(), trigger_rules)
        and _private_recent_wakeup_active(
            db,
            chat_id=str(effective_chat_id or "").strip(),
            baseline_time=message_time,
            wake_window_seconds=wake_cfg["window_seconds"],
        )
    ):
        reply_gate = {
            **reply_gate,
            "allowed": True,
            "reason": "private_wakeup_active",
            "matched_by": "private_wakeup_active",
        }

    if not reply_gate.get("allowed"):
        return {"status": "blocked", "reason": str(reply_gate.get("reason") or "blocked"), "rule": reply_gate}

    if (
        not effective_is_group
        and str(reply_gate.get("matched_by") or "") == "prefix"
        and _private_wakeup_allowed_for_chat(str(effective_chat_id or "").strip(), trigger_rules)
    ):
        _record_private_wakeup(
            db,
            chat_id=str(effective_chat_id or "").strip(),
            wake_time=message_time,
        )
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise

    conf = load_ai_config()
    if not conf.get("api_key"):
        raise HTTPException(400, "SILICONFLOW_API_KEY not configured")

    subsession_conf = _load_subsession_reply_config(db, subsession_id)
    tool_prompts = conf.get("tool_prompts") or {}
    if not prompt_key:
        if operation_type == "约":
            prompt_key = "reply_yue"
        elif operation_type == "问":
            prompt_key = "reply_wen"
        else:
            prompt_key = "reply_da"

    prompt_conf = tool_prompts.get(prompt_key) or DEFAULT_TOOL_PROMPTS.get(prompt_key)
    if not isinstance(prompt_conf, dict):
        raise HTTPException(400, f"unknown prompt_key: {prompt_key}")

    system_prompt = str(prompt_conf.get("system") or "").strip()
    user_template = str(prompt_conf.get("user") or "").strip()
    if not system_prompt or not user_template:
        legacy = tool_prompts.get("reply_generation") or DEFAULT_TOOL_PROMPTS.get("reply_generation") or {}
        system_prompt = system_prompt or str(legacy.get("system") or "").strip()
        user_template = user_template or str(legacy.get("user") or "").strip()
    if subsession_conf and subsession_conf.get("system_prompt"):
        system_prompt = str(subsession_conf.get("system_prompt") or "").strip()
    if not system_prompt or not user_template:
        raise HTTPException(400, f"prompt_key not configured: {prompt_key}")

    ctx = {
        "operation_type": operation_type,
        "sender_name": sender_name,
        "talker_name": talker_name,
        "message_text": message_text,
    }
    user_prompt = _render_template(user_template, ctx)
    history_turns: list[dict[str, str]] = []
    if subsession_conf:
        history_turns = _build_subsession_history(
            db,
            subsession_id=str(subsession_conf["id"]),
            chat_id=str(effective_chat_id or "").strip(),
            sender_id=str(effective_sender_id or "").strip() or None,
            history_max_messages=int(subsession_conf.get("history_max_messages") or 0),
            history_max_tokens=int(subsession_conf.get("history_max_tokens") or 0),
            allow_cross_chat=bool(subsession_conf.get("allow_cross_chat_context")),
            allow_cross_sender=bool(subsession_conf.get("allow_cross_sender_context")),
        )
    messages = [{"role": "system", "content": system_prompt}]
    if history_turns:
        messages.extend(history_turns)
    messages.append({"role": "user", "content": user_prompt})
    model = (
        (subsession_conf or {}).get("model_override")
        or conf.get("tool_model_messages")
        or conf.get("tool_model")
        or conf.get("model")
        or "Qwen/Qwen3-8B"
    )
    route_kind = str((subsession_conf or {}).get("model_route_kind") or "tool").strip() or "tool"
    route_key = str((subsession_conf or {}).get("model_route_key") or "reply").strip() or "reply"
    execution = {
        "route_kind": route_kind,
        "route_key": route_key,
        "configured_model": model,
        "subsession_id": subsession_id or None,
        "history_turns": len(history_turns),
    }
    try:
        chat_result = siliconflow_chat(
            messages,
            temperature=0.2,
            model_override=model,
            force_json=False,
            route_kind=route_kind,
            route_key=route_key,
            return_metadata=True,
        )
    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
            "prompt_key": prompt_key,
            "rule": reply_gate,
            "subsession_id": subsession_id or None,
            "execution": {**execution, "error": str(exc)},
        }

    if isinstance(chat_result, dict):
        execution.update(chat_result.get("execution") or {})
        text = chat_result.get("text")
    else:
        text = chat_result

    reply = str(text or "").strip()
    if reply.startswith("```"):
        reply = reply.strip("`").strip()
    return {
        "status": "ok",
        "reply": reply,
        "prompt_key": prompt_key,
        "rule": reply_gate,
        "subsession_id": subsession_id or None,
        "execution": execution,
    }
