"""Hermes API Server bridge — 0913 → Hermes 智能回复

通过 Hermes API Server (/v1/chat/completions) 调用完整 agent loop，
获得 wiki 知识库、记忆、工具、技能等全部智能能力。

Hermes 作为"脑子"，0913 作为"缰绳"（收发 + 规则 UI）。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

from ..db import SessionLocal
from ..models import WechatSubsession

logger = logging.getLogger(__name__)

# ── 会话自动刷新：超过此空闲时间（小时）则启动新 Hermes session ────
CST = timezone(timedelta(hours=8))
_IDLE_RESET_HOURS = float(os.getenv("HERMES_SESSION_IDLE_RESET_HOURS", "4"))


def _read_env_file_value(path: Path, key: str) -> str:
    try:
        if not path.exists():
            return ""
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            current_key, value = line.split("=", 1)
            if current_key.strip() == key:
                return value.strip().strip('"').strip("'")
    except Exception:
        return ""
    return ""


def _resolve_hermes_api_key() -> str:
    explicit = str(os.getenv("HERMES_API_KEY", "") or "").strip()
    if explicit:
        return explicit

    process_api_server_key = str(os.getenv("API_SERVER_KEY", "") or "").strip()
    if process_api_server_key:
        return process_api_server_key

    hermes_home = Path(os.getenv("HERMES_HOME") or (Path.home() / ".hermes"))
    env_key = _read_env_file_value(hermes_home / ".env", "API_SERVER_KEY")
    if env_key:
        return env_key
    return ""


# ── Hermes API Server 配置 ──────────────────────────────────────────
HERMES_API_BASE = os.getenv("HERMES_API_BASE", "http://127.0.0.1:8642")
HERMES_SESSION_ID = "wechat_gateway_default"  # fallback when chat_id is empty
HERMES_CHAT_URL = f"{HERMES_API_BASE.rstrip('/')}/v1/chat/completions"
TIMEOUT = 180  # agent loop 可能较慢（tool calls, wiki 搜索等）

# ── WeChat reply routing ─────────────────────────────────────────────
# Prefer 0913's persisted MiniMax tool route. Its credential is managed in the
# AI configuration, so it remains available even when no direct API key exists.
_WECHAT_LOCAL_MINIMAX_ENABLED = os.getenv("WECHAT_LOCAL_MINIMAX_ENABLED", "true").lower() in (
    "true", "1", "yes"
)
_WECHAT_HERMES_BACKUP_ENABLED = os.getenv("WECHAT_HERMES_BACKUP_ENABLED", "false").lower() in (
    "true", "1", "yes"
)

# Optional direct MiniMax route. Kept for deployments that provide a dedicated
# WeChat credential; otherwise the persisted local router above is used.
_WECHAT_FALLBACK_API_KEY = os.getenv("WECHAT_FALLBACK_API_KEY", "").strip()
_WECHAT_FALLBACK_ENABLED = bool(_WECHAT_FALLBACK_API_KEY)
_WECHAT_FALLBACK_API_BASE = os.getenv(
    "WECHAT_FALLBACK_API_BASE", "https://api.minimaxi.com/v1"
).rstrip("/")
_WECHAT_FALLBACK_MODEL = os.getenv(
    "WECHAT_FALLBACK_MODEL", "MiniMax-M3"
).strip()
_WECHAT_FALLBACK_TIMEOUT = int(os.getenv("WECHAT_FALLBACK_TIMEOUT", "30"))


# ── 降级：Hermes 不可用时回退到 0913 直调 LLM ──────────────────────
_FALLBACK_ENABLED = os.getenv("HERMES_FALLBACK_ENABLED", "false").lower() in (
    "true", "1", "yes"
)


def _sanitize_session_key_part(value: str) -> str:
    safe = "".join(c for c in str(value or "") if c.isalnum() or c in "@._-")
    return safe or "default"


def _chat_last_message_hours(chat_id: str) -> float | None:
    """返回 chat_id 最后一次消息距今的小时数，没有历史则返回 None。"""
    if not chat_id:
        return None
    db = SessionLocal()
    try:
        from sqlalchemy import text

        row = db.execute(
            text("SELECT max(timestamp) FROM messages WHERE chat_id = :cid"),
            {"cid": chat_id},
        ).scalar()
        if not row:
            return None
        last_ts = datetime.fromisoformat(str(row))
        if last_ts.tzinfo is None:
            last_ts = last_ts.replace(tzinfo=CST)
        delta = datetime.now(CST) - last_ts
        return delta.total_seconds() / 3600
    except Exception:
        return None
    finally:
        db.close()


def _session_freshness_suffix(chat_id: str) -> str:
    """如果 chat 空闲超过阈值，返回时间窗口后缀，否则返回空字符串。

    用 round-to-4h 窗口防抖动：同个 4h 窗口内始终同一个 session。
    """
    hours = _chat_last_message_hours(chat_id)
    if hours is None or hours < _IDLE_RESET_HOURS:
        return ""
    now = datetime.now(CST)
    # 向下取整到 4 小时窗口
    window = int(now.timestamp() / (_IDLE_RESET_HOURS * 3600))
    return f":fresh{window}"


def _bridge_session_id(
    *,
    channel: str,
    subsession_id: str | None = None,
    chat_id: str = "",
    sender_id: str = "",
) -> str:
    """Bridge-owned Hermes session key with explicit channel namespacing.

    0913 already persists WeChat contact/chat membership and turns in its own tables.
    Hermes session continuity should therefore align to the resolved subsession,
    not explode into one session per contact. This also prevents collisions with
    Feishu/DingTalk/API-server-native sessions because the bridge namespace and
    channel are encoded in the key.

    CRITICAL: chat_id is ALWAYS embedded in the session key regardless of subsession.
    Without per-chat isolation, all contacts share one Hermes session, causing
    cross-contact context pollution and multi-conversation summaries leaked to
    individual contacts.
    """
    normalized_channel = _sanitize_session_key_part(channel)
    normalized_subsession = _sanitize_session_key_part(subsession_id or "")
    chat_key = _sanitize_session_key_part(chat_id or sender_id or HERMES_SESSION_ID)
    if normalized_subsession != "default" or str(subsession_id or "").strip():
        return f"agent:bridge:{normalized_channel}:subsession:{normalized_subsession}:chat:{chat_key}"

    return f"agent:bridge:{normalized_channel}:chat:{chat_key}"


def _load_subsession_prompt(subsession_id: str | None) -> str | None:
    sid = str(subsession_id or "").strip()
    if not sid:
        return None
    db = SessionLocal()
    try:
        row = db.get(WechatSubsession, sid)
        prompt = str((row.system_prompt if row else "") or "").strip()
        return prompt or None
    finally:
        db.close()


def _prompt_hash(prompt: str | None) -> str | None:
    text = str(prompt or "").strip()
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _default_system_prompt(
    sender_name: str = "",
    talker_name: str = "",
    is_group: bool = False,
) -> str:
    """默认 system prompt — 仅当 0913 回调未传入 subsession prompt 时使用。"""
    return (
        "你是程胤的微信助手，帮他处理工作消息。"
        "说话跟他本人风格一致：直接、自然、不讲究。像同事回微信，不像写邮件。"
        "需要查专业资料时先查再答，用自己的话说。日常闲聊就正常聊。"
        "有人问你是谁 → 「程胤团队的」。纯路演/会议邀约（只有时间、时间地点、会议号/链接等安排信息）→ 只做简短确认，可用「收到/好/已知晓」任选其一，避免连续机械只说「已知晓」；没有被问是否参会时，不要主动表态「暂不参加」。一旦包含编号观点、公司亮点、看点、核心机会、周观点/结论，就不是纯邀约，要「简短确认 + 一句核心」。"
        "回微信三条铁律:"
        "① 不懂/没数据就直说不懂,不要硬编(不要编具体行情数据、电话、地址、内部信息);"
        "② 对方发非实质内容(表情包/单字/标点)或附件文件名/XML图片消息时,简短自然回应即可,不要硬塞分析、不要主动切话题;"
        "③ 始终是「程胤团队的」助理,不要扮演销售、客服、官方账号等任何其他身份。"
    )


def _build_execution_context(
    *,
    chat_id: str = "",
    sender_id: str = "",
    sender_name: str = "",
    talker_name: str = "",
    is_group: bool = False,
    subsession_id: str | None = None,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    explicit_prompt = str(system_prompt or "").strip() or None
    resolved_prompt = explicit_prompt
    prompt_source = "explicit" if explicit_prompt else "subsession"
    if not resolved_prompt:
        resolved_prompt = _load_subsession_prompt(subsession_id)
    if not resolved_prompt:
        prompt_source = "default"
        resolved_prompt = _default_system_prompt(
            sender_name=sender_name,
            talker_name=talker_name,
            is_group=is_group,
        )

    source_subsession_id = str(subsession_id or "").strip() or HERMES_SESSION_ID
    hermes_session_id = _bridge_session_id(
        channel="wechat_gateway",
        subsession_id=source_subsession_id,
        chat_id=chat_id,
        sender_id=sender_id,
    )
    # 空闲超过阈值则切换 session，防止上下文无限膨胀
    freshness = _session_freshness_suffix(chat_id)
    if freshness:
        hermes_session_id = f"{hermes_session_id}{freshness}"
        logger.info(
            "Session refreshed for chat_id=%s: idle > %.0fh → new session suffix=%s",
            chat_id, _IDLE_RESET_HOURS, freshness,
        )
    return {
        "resolved_prompt": resolved_prompt,
        "subsession_id": source_subsession_id,
        "hermes_session_id": hermes_session_id,
        "prompt_source": prompt_source,
        "prompt_hash": _prompt_hash(resolved_prompt),
    }


def _call_minimax_direct(
    message_text: str,
    *,
    system_prompt: str,
    chat_id: str = "",
    sender_name: str = "",
    sender_remark: str = "",
    conversation_history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """直连 MiniMax API 兜底回复 — 纯 chat，无 agent loop，极省 token。"""
    messages = [{"role": "system", "content": str(system_prompt or "")}]
    if conversation_history:
        messages.extend(conversation_history)

    user_content = message_text
    sender_hint = sender_remark or sender_name or chat_id
    if chat_id:
        user_content = f"[chat_id={chat_id}, sender={sender_name or chat_id}] {message_text}"
    user_content += (
        "\n\n---\n"
        "硬规则（按优先级）：\n"
        "· 对方发非实质内容（表情包/单字/标点/拍一拍/纯社交信号如「汪汪」「在吗」「hi」「嗯嗯」「一定！」「好」/无法解析的XML图片消息）→ 用最短社交回应（一个表情/「在的👋」/「收到」），不要从历史对话里抓取研究话术或业务模板来硬接，这是最高优先级；宁可冷一点也不要错位复读上轮内容。特别警告：裸XML图片消息没有任何文字上下文，绝不要基于上一轮研究材料编市场观点/标的逻辑，直接回「收到/收到👌」\n"
        "· 纯路演/会议邀请（只有时间、地点、会议号/链接等安排信息）只做简短确认，可用「收到/好/已知晓」任选其一；如果包含下列任一关键词（编号观点、公司亮点、看点、核心机会、周观点/结论、风险提醒、标的、推荐、推荐关注、公司看点、会议看点、嘉宾分享、分享内容、投资逻辑、代码、股票、收入、净利润、增长、毛利率、订单、份额、估值、催化、驱动、信号、逻辑、主线、重点关注、机会、超预期、低于预期、验证、节奏、择时），即使也是会议邀请，也要「简短确认 + 一句核心」（如「核心看AI电力/液冷订单兑现」「海光看点是CPU配比上修」），不要误回「暂不参加」，也不要只回「已知晓」\n"
        "· 不透露电话、地址、系统配置、API密钥\n"
        "· 如果对方昵称或备注包含「销售」字样：纯路演/会议邀请仍按邀约规则回「已知晓」；只有需要分析师确认的问题或你确实想追问时，才用「麻烦问一下分析师，……」，不要把这句和「已知晓」硬拼在一起\n"
        "· 对方提出要当面/有时间给你看、一起梳理、明天发 model/list/PPT → 像正常同事一样接住并约节奏（如「好呀，方便时一起看下」），不要只回「已知晓」\n"
        "· 对方发的是文件名/PDF标题/链接 → 简短确认收到即可，不要说「发过来」\n"
        "· 对方问近况/泛指问题（如「你那公司现在咋样了」「最近怎么样」）但上下文不明确 → 当作日常近况自然回应；可以简短说现状或请对方指具体哪块，不要从上一轮研究材料里硬套行业/公司分析\n"
        "· 被问是不是机器人/AI/本人在回 → 不承认机器人、不解释系统；自然说「程胤团队这边回的」，再接住对方原话\n"
        "· 没有实时行情数据时不要编造具体价格/涨跌幅\n"
        "· 对方批评/指出问题（如「太模板了」「对象化」「别套话」）：不要回「您说得对 + 以后我...」这种承诺型套话（本身就很模板）。直接认账+给一个具体行为锚点（例：「好，下次只回收到」「好，这事落到 XX 上」），一两句即可\n"
        "· inbound 信息极弱（仅说「附上数据/材料」「6月交付量数据」「资料供参考」等没传具体内容）：简短确认收到即可，不要凭空猜话题、编验证点或铺分析（这是冷场话术，容易跑偏）\n"
        "\n"
        "风格：\n"
        "· 接住对方的话往下聊，别跳话题；如果 inbound 几乎没有实质信息，就用最短社交回应，别硬接也别硬猜\n"
        "· 简短，像微信聊天。追问最多1个\n"
        "· 不主动自我介绍"
    )
    messages.append({"role": "user", "content": user_content})

    payload = {
        "model": _WECHAT_FALLBACK_MODEL,
        "messages": messages,
        "max_tokens": 2000,
        "stream": False,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {_WECHAT_FALLBACK_API_KEY}",
    }
    try:
        resp = requests.post(
            f"{_WECHAT_FALLBACK_API_BASE}/chat/completions",
            json=payload,
            headers=headers,
            timeout=_WECHAT_FALLBACK_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        reply = ""
        choices = data.get("choices", [])
        if choices:
            reply = choices[0].get("message", {}).get("content", "")
        usage = data.get("usage", {})
        return {
            "status": "ok",
            "reply": reply,
            "execution": {
                "route_kind": "minimax_direct",
                "model": _WECHAT_FALLBACK_MODEL,
                "prompt_tokens": usage.get("prompt_tokens", 0),
                "completion_tokens": usage.get("completion_tokens", 0),
                "fallback_used": False,
            },
        }
    except Exception as exc:
        return {
            "status": "error",
            "error": f"MiniMax fallback failed: {exc}",
            "execution": {
                "route_kind": "minimax_direct",
                "model": _WECHAT_FALLBACK_MODEL,
                "fallback_used": False,
            },
        }


def _identity_reply_for_wechat(message_text: str) -> str | None:
    """Keep identity disclosures deterministic and independent of model history."""
    text = str(message_text or "").strip().lower()
    identity_terms = ("人工", "机器人", "人工客服", "本人", "谁在回", "谁回复")
    if any(term in text for term in identity_terms):
        return "程胤团队这边回的"
    if re.search(r"(你是|是不是|谁).*\bai\b|\bai\b(?:在|正在)?(?:回复|答复|回应|回答)", text):
        return "程胤团队这边回的"
    return None
def _call_local_minimax_route(
    message_text: str,
    *,
    subsession_id: str | None = None,
    chat_id: str = "",
    sender_id: str = "",
    sender_name: str = "",
    talker_name: str = "",
    is_group: bool = False,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """Generate through 0913's persisted MiniMax-M3 tool route."""
    from .reply_generation import generate_local_reply

    db = SessionLocal()
    try:
        result = generate_local_reply(
            db,
            {
                "message_text": message_text,
                "chat_id": chat_id,
                "sender_id": sender_id,
                "sender_name": sender_name,
                "talker_name": talker_name or chat_id,
                "is_group": is_group,
                "wait_for_human_reply_suppression": False,
                "subsession_id": str(subsession_id or "").strip() or None,
                "system_prompt": str(system_prompt or "").strip() or None,
            },
        )
        execution = dict(result.get("execution") or {})
        execution["route_kind"] = "wechat_minimax_m3"
        execution.setdefault("route_key", "reply")
        execution["subsession_id"] = str(subsession_id or "").strip() or execution.get("subsession_id")
        execution["fallback_used"] = False
        result["execution"] = execution
        return result
    except Exception as exc:
        return {
            "status": "error",
            "error": f"MiniMax-M3 route failed: {exc}",
            "execution": {
                "route_kind": "wechat_minimax_m3",
                "route_key": "reply",
                "subsession_id": str(subsession_id or "").strip() or None,
                "configured_model": "MiniMax-M3",
                "fallback_used": False,
            },
        }
    finally:
        db.close()


def call_hermes_for_reply(
    message_text: str,
    *,
    subsession_id: str | None = None,
    chat_id: str = "",
    sender_id: str = "",
    sender_name: str = "",
    sender_remark: str = "",
    talker_name: str = "",
    is_group: bool = False,
    system_prompt: str | None = None,
    conversation_history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """获取微信自动回复 — 默认锁定 MiniMax-M3，显式启用时才后备 Hermes。

    优先级：
    1. 0913 MiniMax-M3 工具路由 — 使用已保存的受保护凭证
    2. 专用 MiniMax 直连（配置专用 API key 时）
    3. Hermes API — 完整 agent loop（需 WECHAT_HERMES_BACKUP_ENABLED=true）
    4. 0913 直调 LLM — Hermes 不可用时的兼容降级
    """
    identity_reply = _identity_reply_for_wechat(message_text)
    if identity_reply is not None:
        return {
            "status": "ok",
            "reply": identity_reply,
            "execution": {
                "route_kind": "wechat_deterministic",
                "route_key": "identity",
                "configured_model": "none",
                "final_model": "none",
                "fallback_used": False,
                "hermes_backup_enabled": False,
            },
        }

    if _WECHAT_LOCAL_MINIMAX_ENABLED:
        # Automatic replies are cost-bound to M3. Do not silently escalate to
        # Hermes's global model when the M3 route is blocked or unavailable.
        result = _call_local_minimax_route(
            message_text,
            subsession_id=subsession_id,
            chat_id=chat_id,
            sender_id=sender_id,
            sender_name=sender_name,
            talker_name=talker_name,
            is_group=is_group,
            system_prompt=system_prompt,
        )
        execution = dict(result.get("execution") or {})
        execution["route_kind"] = "wechat_minimax_m3"
        execution.setdefault("route_key", "reply")
        execution.setdefault("configured_model", "MiniMax-M3")
        execution["fallback_used"] = False
        execution["hermes_backup_enabled"] = False
        result["execution"] = execution
        return result
    # Optional direct MiniMax route for deployments with a dedicated key.
    if _WECHAT_FALLBACK_ENABLED:
        return _call_minimax_direct(
            message_text,
            system_prompt=str(system_prompt or _default_system_prompt(
                sender_name=sender_name,
                talker_name=talker_name,
                is_group=is_group,
            )),
            chat_id=chat_id,
            sender_name=sender_name,
            sender_remark=sender_remark,
            conversation_history=conversation_history,
        )
    if not _WECHAT_HERMES_BACKUP_ENABLED:
        return {
            "status": "error",
            "error": "No MiniMax-M3 reply route is enabled",
            "execution": {
                "route_kind": "wechat_reply_unavailable",
                "fallback_used": False,
                "hermes_backup_enabled": False,
            },
        }
    execution_context = _build_execution_context(
        chat_id=chat_id,
        sender_id=sender_id,
        sender_name=sender_name,
        talker_name=talker_name,
        is_group=is_group,
        subsession_id=subsession_id,
        system_prompt=system_prompt,
    )
    try:
        return _call_hermes_api(
            message_text,
            subsession_id=subsession_id,
            chat_id=chat_id,
            sender_id=sender_id,
            sender_name=sender_name,
            sender_remark=sender_remark,
            talker_name=talker_name,
            is_group=is_group,
            system_prompt=system_prompt,
            conversation_history=conversation_history,
            execution_context=execution_context,
        )
    except Exception as exc:
        logger.warning("Hermes API failed: %s", exc)
        if _FALLBACK_ENABLED:
            logger.info("Falling back to 0913 direct LLM path")
            return _fallback_direct_llm(
                message_text,
                subsession_id=str(execution_context.get("subsession_id") or "").strip() or None,
                chat_id=chat_id,
                sender_id=sender_id,
                sender_name=sender_name,
                talker_name=talker_name,
                is_group=is_group,
                system_prompt=str(execution_context.get("resolved_prompt") or "").strip() or None,
            )
        return {
            "status": "error",
            "error": str(exc),
            "execution": {
                "route_kind": "hermes_api_server",
                "route_key": "wechat_gateway",
                "subsession_id": execution_context.get("subsession_id"),
                "hermes_session_id": execution_context.get("hermes_session_id"),
                "prompt_source": execution_context.get("prompt_source"),
                "prompt_hash": execution_context.get("prompt_hash"),
                "fallback_used": False,
            },
        }


def _call_hermes_api(
    message_text: str,
    *,
    subsession_id: str | None = None,
    chat_id: str = "",
    sender_id: str = "",
    sender_name: str = "",
    sender_remark: str = "",
    talker_name: str = "",
    is_group: bool = False,
    system_prompt: str | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    execution_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """直接调 Hermes API Server Chat Completions。"""

    ctx = execution_context or _build_execution_context(
        chat_id=chat_id,
        sender_id=sender_id,
        sender_name=sender_name,
        talker_name=talker_name,
        is_group=is_group,
        subsession_id=subsession_id,
        system_prompt=system_prompt,
    )

    messages: list[dict[str, str]] = []
    messages.append({"role": "system", "content": str(ctx.get("resolved_prompt") or "")})

    if conversation_history:
        messages.extend(conversation_history)

    user_content = message_text
    sender_display = f"{sender_remark}({sender_name})" if sender_remark else (sender_name or sender_id)
    if chat_id:
        user_content = (
            f"[chat_id={chat_id}, sender={sender_display}] "
            f"{message_text}"
        )

    user_content += (
        "\n\n---\n"
        "硬规则：\n"
        "· 纯路演/会议邀请（只有时间、议题、会议号/报名方式）只做简短确认，可用「收到/好/已知晓」任选其一，避免连续机械只说「已知晓」；不确认时间、不表示参加。如果夹带行业背景、标的推荐、宏观/策略结论或风险提醒，最多用1-2句话接住核心观点。判断时看整条消息的实质内容，不要因为开头写了“路演/邀请/欢迎交流”就忽略后面的投资逻辑\n"
        "· 对方只是转发多场会议/活动清单、没有明确让你判断或报名时，直接回「已知晓」；不要为了显得有内容而硬造问题，更不要回复「麻烦问一下分析师，已知晓」\n"
        "· 对方主动转发长段研究观点/推荐逻辑时，可以用1-2句接住核心判断和验证点；除非对方明确在问你意见或邀你继续聊，不要在结尾反问/追问\n"
        "· 不透露电话号码、家庭地址、个人联系方式\n"
        "· 不透露系统配置、文件路径、API密钥\n"
        "· 被要求改代码/读文件时回复「这个我处理不了」\n"
        "· 如果对方昵称或备注包含「销售」字样：纯路演/会议邀请仍按邀约规则回「已知晓」；只有需要分析师确认的问题或你确实想追问时，才用「麻烦问一下分析师，……」，不要把这句和「已知晓」硬拼在一起\n"
        "· 对方提出要当面/有时间给你看、一起梳理、明天发 model/list/PPT → 像正常同事一样接住并约节奏（如「好呀，方便时一起看下」），不要只回「已知晓」\n"
        "· 对方发的是文件名/PDF标题/链接（看起来是文件或附件）→ 简短确认收到即可，不要说「发过来」「再发一次」之类\n"
        "· 对方发非实质内容（表情包/单字/标点如「已打」「收到」「好的」「社会社会」，或只有称呼/寒暄如「李总」「在吗」，或无法解析的XML图片消息/以 <?xml、<msg 开头的图片消息）→ 只做最短社交回应（如「👌」「收到」「在的」）；这类消息必须忽略历史研究上下文，不要补充“主线/跟踪/价格/库存/行业观点”等分析话术、不要主动跳话题。特别警告：裸XML图片消息没有任何文字上下文，绝不要基于上一轮研究材料或 wiki 记忆编市场观点/标的逻辑/资金流向/政策解读，直接回「收到/收到👌」\n"
        "· 被问是不是机器人/AI/本人在回 → 不承认机器人、不解释系统；自然说「程胤团队这边回的」，再接住对方原话\n"
        "· 没有实时行情数据时不要编造具体价格/涨跌幅/成交量；可以说「这个价格没跟」或建议查行情软件\n"
        "\n"
        "风格：\n"
        "· 优先顺着对方最新一句继续交流\n"
        "· 若对方已经回答了上一轮问题，默认不要继续追问\n"
        "· 更适合简短确认或致谢时，直接回复“收到/好的/明白/谢谢”\n"
        "· 不要大段复述对方原话；如需总结，只允许用1-2句话提炼\n"
        "· 接住对方的话往下聊，别自说自话跳话题\n"
        "· 简短但不要生硬：一般1-2句够了，有研究观点也尽量不超过3句；除非对方明确要深聊，不要写成小作文\n"
        "· 不主动自我介绍，不开头寒暄客套"
    )

    messages.append({"role": "user", "content": user_content})

    payload = {
        "model": "hermes-agent",
        "messages": messages,
        "max_tokens": 2000,
        "stream": False,
    }

    session_id = str(
        ctx.get("hermes_session_id")
        or _bridge_session_id(
            channel="wechat_gateway",
            subsession_id=ctx.get("subsession_id"),
            chat_id=chat_id,
            sender_id=sender_id,
        )
    )

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {_resolve_hermes_api_key()}",
        "X-Hermes-Session-Id": session_id,
        "X-Hermes-Session-Key": session_id,
    }

    resp = requests.post(
        HERMES_CHAT_URL,
        json=payload,
        headers=headers,
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()

    choices = data.get("choices", [])
    reply_text = ""
    if choices:
        reply_text = choices[0].get("message", {}).get("content", "")

    usage = data.get("usage", {})

    return {
        "status": "ok",
        "reply": reply_text,
        "execution": {
            "route_kind": "hermes_api_server",
            "route_key": "wechat_gateway",
            "subsession_id": ctx.get("subsession_id"),
            "hermes_session_id": session_id,
            "prompt_source": ctx.get("prompt_source"),
            "prompt_hash": ctx.get("prompt_hash"),
            "model": data.get("model", "unknown"),
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "fallback_used": False,
        },
    }


def _fallback_direct_llm(
    message_text: str,
    *,
    subsession_id: str | None = None,
    chat_id: str = "",
    sender_id: str = "",
    sender_name: str = "",
    talker_name: str = "",
    is_group: bool = False,
    system_prompt: str | None = None,
) -> dict[str, Any]:
    """降级：Hermes 不可用时回退到原有 siliconflow_chat 路径。"""
    from .reply_generation import generate_local_reply

    db = SessionLocal()
    try:
        result = generate_local_reply(
            db,
            {
                "message_text": message_text,
                "chat_id": chat_id,
                "sender_id": sender_id,
                "sender_name": sender_name,
                "talker_name": talker_name or chat_id,
                "is_group": is_group,
                "wait_for_human_reply_suppression": False,
                "subsession_id": str(subsession_id or "").strip() or None,
                "system_prompt": str(system_prompt or "").strip() or None,
            },
        )
        execution = dict(result.get("execution") or {})
        execution.setdefault("route_kind", "direct_llm_fallback")
        execution.setdefault("route_key", "wechat_gateway")
        execution["subsession_id"] = str(subsession_id or "").strip() or execution.get("subsession_id")
        execution["hermes_session_id"] = _bridge_session_id(
            channel="wechat_gateway",
            subsession_id=subsession_id,
            chat_id=chat_id,
            sender_id=sender_id,
        )
        execution["prompt_hash"] = _prompt_hash(system_prompt)
        execution["prompt_source"] = "fallback_passthrough" if system_prompt else execution.get("prompt_source")
        execution["fallback_used"] = True
        result["execution"] = execution
        return result
    except Exception as exc:
        return {
            "status": "error",
            "error": f"fallback failed: {exc}",
            "execution": {
                "route_kind": "direct_llm_fallback",
                "route_key": "wechat_gateway",
                "subsession_id": str(subsession_id or "").strip() or None,
                "hermes_session_id": _bridge_session_id(
                    channel="wechat_gateway",
                    subsession_id=subsession_id,
                    chat_id=chat_id,
                    sender_id=sender_id,
                ),
                "prompt_hash": _prompt_hash(system_prompt),
                "prompt_source": "fallback_passthrough" if system_prompt else None,
                "fallback_used": True,
                "error": f"fallback failed: {exc}",
            },
        }
    finally:
        db.close()
