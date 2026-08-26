from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Callable

from sqlalchemy.orm import Session

from ..db import SessionLocal
from ..models import Contact, Message


logger = logging.getLogger(__name__)


def _generate_reply_with_hermes(**kwargs) -> dict[str, Any]:
    # Resolve the module at call time so existing Hermes module monkeypatches remain effective.
    from . import hermes_bridge

    return hermes_bridge.call_hermes_for_reply(**kwargs)


def _evaluate_rules_default(*args, **kwargs) -> dict[str, Any]:
    from . import wechat_gateway

    return wechat_gateway.evaluate_auto_reply_rules(*args, **kwargs)


def _load_config_default(*args, **kwargs) -> dict[str, Any]:
    from . import wechat_gateway

    return wechat_gateway.load_config(*args, **kwargs)


def _evaluate_outbound_default(*args, **kwargs) -> dict[str, Any]:
    from . import wechat_gateway

    return wechat_gateway.evaluate_outbound_message(*args, **kwargs)


def _apply_delay_default(*args, **kwargs) -> float:
    from . import wechat_gateway

    return wechat_gateway.apply_outbound_random_delay(*args, **kwargs)


def _record_outbound_default(*args, **kwargs) -> Message:
    from . import wechat_gateway

    kwargs["commit"] = False
    return wechat_gateway.record_outbound_message(*args, **kwargs)


def _claim_attempt_default(*args, **kwargs) -> dict[str, Any]:
    from . import wechat_gateway

    return wechat_gateway.claim_auto_reply_attempt(*args, **kwargs)


def _update_attempt_default(*args, **kwargs) -> dict[str, Any]:
    from . import wechat_gateway

    return wechat_gateway.update_auto_reply_attempt(*args, **kwargs)


def _client_factory_default(*args, **kwargs) -> Any:
    from . import wechatapi_client

    return wechatapi_client.WechatApiClient(*args, **kwargs)


@dataclass(frozen=True)
class AutoReplyTransactionResult:
    status: str
    reason: str
    message_id: int
    outbound_message_id: int | None = None
    execution: dict[str, Any] | None = None
    delivery: dict[str, Any] | None = None


@dataclass(frozen=True)
class AutoReplyAdapters:
    evaluate_rules: Callable[..., dict[str, Any]] = _evaluate_rules_default
    generate_reply: Callable[..., dict[str, Any]] = _generate_reply_with_hermes
    load_config: Callable[[Session], dict[str, Any]] = _load_config_default
    evaluate_outbound: Callable[..., dict[str, Any]] = _evaluate_outbound_default
    apply_delay: Callable[[dict[str, Any]], float] = _apply_delay_default
    client_factory: Callable[..., Any] = _client_factory_default
    record_outbound: Callable[..., Message] = _record_outbound_default
    claim_attempt: Callable[..., dict[str, Any]] = _claim_attempt_default
    update_attempt: Callable[..., dict[str, Any]] = _update_attempt_default


def _result(
    *,
    status: str,
    reason: str,
    message_id: int,
    outbound_message_id: int | None = None,
    execution: dict[str, Any] | None = None,
    delivery: dict[str, Any] | None = None,
) -> AutoReplyTransactionResult:
    return AutoReplyTransactionResult(
        status=status,
        reason=reason,
        message_id=message_id,
        outbound_message_id=outbound_message_id,
        execution=dict(execution) if isinstance(execution, dict) else None,
        delivery=dict(delivery) if isinstance(delivery, dict) else None,
    )


def _generation_execution(generated: Any) -> dict[str, Any] | None:
    if not isinstance(generated, dict) or not isinstance(generated.get("execution"), dict):
        return None
    return dict(generated["execution"])


def _provider_result_data(provider_result: Any) -> dict[str, Any]:
    if not isinstance(provider_result, dict):
        return {}
    data = provider_result.get("data") if isinstance(provider_result.get("data"), dict) else {}
    if data:
        return data
    results = provider_result.get("results") if isinstance(provider_result.get("results"), list) else []
    for item in results:
        if not isinstance(item, dict):
            continue
        response = item.get("resp") if isinstance(item.get("resp"), dict) else {}
        nested = response.get("data") if isinstance(response.get("data"), dict) else {}
        if nested:
            return nested
    return {}


def _delivery_summary(*, target: str, provider_result: Any) -> dict[str, Any]:
    result = provider_result if isinstance(provider_result, dict) else {}
    data = _provider_result_data(result)
    return {
        "target": str(target or ""),
        "provider_message_id": data.get("msgId") or data.get("MsgId"),
        "provider_new_message_id": data.get("newMsgId") or data.get("NewMsgId"),
        "provider_status": result.get("ret") or result.get("code") or result.get("status"),
        "provider_message": result.get("msg") or result.get("message"),
    }


def _execution_with_delivery(generated: Any, delivery: dict[str, Any]) -> dict[str, Any]:
    execution = _generation_execution(generated) or {}
    execution["delivery"] = dict(delivery)
    return execution


def _rollback_quietly(db: Any) -> None:
    rollback = getattr(db, "rollback", None)
    if not callable(rollback):
        return
    try:
        rollback()
    except Exception:
        logger.exception("wechat auto reply rollback failed")


def _close_quietly(db: Any) -> None:
    close = getattr(db, "close", None)
    if not callable(close):
        return
    try:
        close()
    except Exception:
        logger.exception("wechat auto reply session close failed")


def _update_attempt_quietly(
    adapters: AutoReplyAdapters,
    db: Any,
    *,
    message_id: int,
    state: str,
    delivery: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    try:
        adapters.update_attempt(
            db,
            message_id=message_id,
            state=state,
            delivery=delivery,
            error=error,
            commit=True,
        )
    except Exception:
        _rollback_quietly(db)
        logger.exception(
            "wechat auto reply attempt update failed: message_id=%s state=%s",
            message_id,
            state,
        )


def execute_wechat_auto_reply_transaction(
    message_id: int,
    *,
    session_factory: Callable[[], Session] = SessionLocal,
    adapters: AutoReplyAdapters | None = None,
) -> AutoReplyTransactionResult:
    resolved_adapters = adapters or AutoReplyAdapters()
    db: Session | None = None
    generated: dict[str, Any] | None = None
    chat_id = ""
    trigger_message_id = int(message_id)
    claimed = False
    send_started = False
    send_succeeded = False
    delivery: dict[str, Any] | None = None
    stage = "open_session"

    try:
        db = session_factory()

        stage = "load_message"
        message = db.get(Message, message_id)
        if message is None:
            return _result(status="skipped", reason="message_not_found", message_id=message_id)
        if message.direction != "in":
            return _result(status="skipped", reason="message_not_inbound", message_id=message_id)
        if str(message.type or "") != "text":
            return _result(status="skipped", reason="message_not_text", message_id=message_id)

        trigger_message_id = int(message.id) if message.id is not None else int(message_id)
        chat_id = str(message.chat_id or "")
        sender_id = str(message.sender_id or "") or None
        is_group = chat_id.endswith("@chatroom")
        message_time = message.timestamp.isoformat() if message.timestamp else None
        message_meta = message.meta if isinstance(message.meta, dict) else {}

        stage = "precheck"
        final_gate = resolved_adapters.evaluate_rules(
            db,
            chat_id=chat_id,
            sender_id=sender_id,
            text=str(message.content_text or ""),
            is_group=is_group,
            message_time=message_time,
            wait_for_human_reply_suppression=True,
            message_meta=message_meta,
        )
        if not final_gate.get("allowed"):
            reason = str(final_gate.get("reason") or "precheck_blocked")
            logger.info("wechat auto reply blocked: message_id=%s reason=%s", message_id, reason)
            return _result(status="blocked", reason=reason, message_id=message_id)

        subsession = message_meta.get("subsession") if isinstance(message_meta.get("subsession"), dict) else {}
        subsession_id = str(subsession.get("id") or "wechat_gateway_default")
        sender_remark = ""
        if sender_id:
            contact = db.get(Contact, sender_id)
            if contact:
                sender_remark = str(contact.alias or contact.name or "").strip()

        stage = "generate"
        generated = resolved_adapters.generate_reply(
            message_text=str(message.content_text or ""),
            subsession_id=subsession_id,
            chat_id=chat_id,
            sender_id=str(message.sender_id or ""),
            sender_name=str(message.sender_name or ""),
            sender_remark=sender_remark,
            talker_name=str(message.talker_name or message.chat_id or ""),
            is_group=is_group,
        )
        execution = _generation_execution(generated)
        if not isinstance(generated, dict) or generated.get("status") != "ok":
            generation_data = generated if isinstance(generated, dict) else {}
            reason = str(
                generation_data.get("reason")
                or generation_data.get("error")
                or generation_data.get("status")
                or "invalid_generation_result"
            )
            logger.info("wechat auto reply generation failed: message_id=%s reason=%s", message_id, reason)
            return _result(
                status="failed",
                reason=reason,
                message_id=message_id,
                execution=execution,
            )

        stage = "recheck"
        recheck = resolved_adapters.evaluate_rules(
            db,
            chat_id=chat_id,
            sender_id=sender_id,
            text=str(message.content_text or ""),
            is_group=is_group,
            message_time=message_time,
            wait_for_human_reply_suppression=False,
            message_meta=message_meta,
        )
        if not recheck.get("allowed"):
            reason = str(recheck.get("reason") or "recheck_blocked")
            logger.info("wechat auto reply blocked before send: message_id=%s reason=%s", message_id, reason)
            return _result(
                status="blocked",
                reason=reason,
                message_id=message_id,
                execution=execution,
            )

        stage = "load_config"
        config = resolved_adapters.load_config(db)
        reply_text = str(generated.get("reply") or "")

        stage = "outbound_rule"
        outbound_rule = resolved_adapters.evaluate_outbound(config, target=chat_id, text=reply_text)
        if not outbound_rule.get("allowed", True):
            reason = str(outbound_rule.get("reason") or "outbound_blocked")
            logger.info("wechat outbound blocked: message_id=%s reason=%s", message_id, reason)
            return _result(
                status="blocked",
                reason=reason,
                message_id=message_id,
                execution=execution,
            )

        stage = "create_client"
        client = resolved_adapters.client_factory(
            base_url=str(config.get("base_url") or ""),
            token=str(config.get("token") or ""),
            header_name=str(config.get("header_name") or "VideosApi-token"),
            app_id=str(config.get("app_id") or ""),
        )
        if not client.configured():
            logger.warning("wechat auto reply skipped: gateway not configured")
            return _result(
                status="skipped",
                reason="gateway_not_configured",
                message_id=message_id,
                execution=execution,
            )

        stage = "claim"
        claim_result = resolved_adapters.claim_attempt(
            db,
            message_id=trigger_message_id,
            target=chat_id,
        )
        if not isinstance(claim_result, dict) or not claim_result.get("claimed"):
            attempt = claim_result.get("attempt") if isinstance(claim_result, dict) else {}
            existing_delivery = attempt.get("delivery") if isinstance(attempt, dict) else None
            existing_execution = execution
            if isinstance(existing_delivery, dict):
                existing_execution = _execution_with_delivery(generated, existing_delivery)
            return _result(
                status="skipped",
                reason="already_claimed",
                message_id=message_id,
                execution=existing_execution,
                delivery=existing_delivery,
            )
        claimed = True

        stage = "delay"
        delay_seconds = resolved_adapters.apply_delay(config)

        stage = "send"
        send_started = True
        provider_result = client.send_text(to_wxid=chat_id, text=reply_text)
        send_succeeded = True
        delivery = _delivery_summary(target=chat_id, provider_result=provider_result)
        execution = _execution_with_delivery(generated, delivery)

        stage = "attempt_sent_pending_record"
        resolved_adapters.update_attempt(
            db,
            message_id=trigger_message_id,
            state="sent_pending_record",
            delivery=delivery,
            commit=True,
        )

        recorded_provider_result = {
            "source": "wechat_gateway_auto_reply",
            "auto_reply": {"trigger_message_id": trigger_message_id},
            **(provider_result if isinstance(provider_result, dict) else {}),
        }

        stage = "record"
        outbound = resolved_adapters.record_outbound(
            db,
            target=chat_id,
            text=reply_text,
            provider_result=recorded_provider_result,
        )
        meta = dict(outbound.meta or {})
        meta["auto_reply"] = {
            "trigger_message_id": trigger_message_id,
            "rule": final_gate,
            "prompt_key": generated.get("prompt_key"),
            "execution": execution,
            "outbound_rule": outbound_rule,
            "outbound_delay_seconds": delay_seconds,
        }
        outbound.meta = meta
        db.add(outbound)

        stage = "attempt_recorded"
        resolved_adapters.update_attempt(
            db,
            message_id=trigger_message_id,
            state="recorded",
            delivery=delivery,
            commit=False,
        )

        stage = "commit"
        db.commit()
        outbound_id = int(outbound.id) if outbound.id is not None else None
        return _result(
            status="sent",
            reason="sent",
            message_id=message_id,
            outbound_message_id=outbound_id,
            execution=execution,
            delivery=delivery,
        )
    except Exception as exc:
        if db is not None:
            _rollback_quietly(db)
        execution = _generation_execution(generated) or {}
        execution["transaction_stage"] = stage
        execution["transaction_error"] = str(exc)
        logger.exception("wechat auto reply failed: message_id=%s stage=%s", message_id, stage)

        if send_started:
            if delivery is None:
                delivery = {"target": chat_id, "send_error": str(exc)}
            execution["delivery"] = dict(delivery)
            if db is not None and claimed:
                if send_succeeded and stage == "attempt_sent_pending_record":
                    _update_attempt_quietly(
                        resolved_adapters,
                        db,
                        message_id=trigger_message_id,
                        state="sent_pending_record",
                        delivery=delivery,
                        error=str(exc),
                    )
                elif not send_succeeded:
                    _update_attempt_quietly(
                        resolved_adapters,
                        db,
                        message_id=trigger_message_id,
                        state="delivery_unknown",
                        delivery=delivery,
                        error=str(exc),
                    )
            return _result(
                status="delivery_unknown",
                reason="persistence_failed_after_send" if send_succeeded else "send_failed_delivery_unknown",
                message_id=message_id,
                execution=execution,
                delivery=delivery,
            )

        if db is not None and claimed:
            _update_attempt_quietly(
                resolved_adapters,
                db,
                message_id=trigger_message_id,
                state="failed_before_send",
                error=str(exc),
            )
            return _result(
                status="error",
                reason="failed_before_send",
                message_id=message_id,
                execution=execution,
            )

        return _result(
            status="error",
            reason="unexpected_error",
            message_id=message_id,
            execution=execution,
        )
    finally:
        if db is not None:
            _close_quietly(db)
