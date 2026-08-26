from __future__ import annotations

import json
import re
import logging
import time
from typing import Any, Dict, Iterable, List
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from ..models import Message
from .llm_client import DEFAULT_TOOL_PROMPTS, load_ai_config, siliconflow_tool_chat
from .desk_agent import DeskAgentClient

# Optional JSON5 for lenient parsing; fall back to stdlib json when unavailable
try:  # pragma: no cover - optional dependency
    import json5  # type: ignore
    _HAS_JSON5 = True
except Exception:  # pragma: no cover
    json5 = None  # type: ignore
    _HAS_JSON5 = False

logger = logging.getLogger(__name__)

CLI_BATCH_PROMPTS = {
    "message_summary",
    "email_message_summary",
    "minutes_summary",
    "minutes_refine",
    "media_content_summary",
    "mp_content_summary",
}
CLI_TASK_META = {
    "message_summary": (
        "deepsee-wechat",
        "deepsee.wechat.batch-summarize",
        "message-summary",
    ),
    "email_message_summary": (
        "deepsee-email",
        "deepsee.email.batch-summarize",
        "email-summary",
    ),
    "minutes_summary": (
        "deepsee-minutes",
        "deepsee.minutes.batch-summarize",
        "minutes-summary",
    ),
    "minutes_refine": (
        "deepsee-minutes",
        "deepsee.minutes.batch-refine",
        "minutes-refine",
    ),
    "media_content_summary": (
        "deepsee-media",
        "deepsee.media.batch-summarize",
        "media-summary",
    ),
    "mp_content_summary": (
        "deepsee-official-accounts",
        "deepsee.official-accounts.batch-summarize",
        "mp-summary",
    ),
}
CLI_BATCH_LIMITS = {
    "message_summary": 100,
    "email_message_summary": 50,
    "minutes_summary": 50,
    "minutes_refine": 50,
    "media_content_summary": 10,
    "mp_content_summary": 10,
}
MAX_CLI_BATCH_CHARS = 80_000


# ----------------------------- helpers -----------------------------

def _commit_with_retry(
    db: Session,
    *,
    retries: int = 10,
    base_delay: float = 0.12,
) -> None:
    """Retry SQLite commit on transient lock conflicts."""
    last_exc: Exception | None = None
    for attempt in range(max(1, retries)):
        try:
            db.commit()
            return
        except OperationalError as exc:
            db.rollback()
            last_exc = exc
            msg = str(exc).lower()
            try:
                if getattr(exc, "orig", None):
                    msg = f"{msg} | {str(exc.orig).lower()}"
            except Exception:
                pass
            if "database is locked" in msg or "locked" in msg:
                sleep_s = min(1.2, base_delay * (1.55 ** attempt))
                time.sleep(max(0.05, sleep_s))
                continue
            raise
    if last_exc is not None:
        raise last_exc

def _batched(
    iterable: Iterable[Dict[str, Any]],
    size: int,
    *,
    max_chars: int = MAX_CLI_BATCH_CHARS,
) -> Iterable[List[Dict[str, Any]]]:
    batch: List[Dict[str, Any]] = []
    batch_chars = 0
    for item in iterable:
        item_chars = len(str(item.get("content") or ""))
        if batch and (len(batch) >= size or batch_chars + item_chars > max_chars):
            yield batch
            batch = []
            batch_chars = 0
        batch.append(item)
        batch_chars += item_chars
    if batch:
        yield batch


def _tool_prompt_payload(
    messages: List[Dict[str, Any]],
    prompt_conf: Dict[str, str],
    *,
    prompt_key: str = "message_summary",
) -> List[Dict[str, str]]:
    """Build JSON payload for the tool model with defensive normalization.

    Some callers may pass `datetime` objects (e.g., from DB) in the `time` field,
    which are not JSON-serializable by default. Normalize typical fields to avoid
    `TypeError: Object of type datetime is not JSON serializable`.
    """
    system_prompt = prompt_conf.get("system") or DEFAULT_TOOL_PROMPTS["message_summary"]["system"]
    user_template = prompt_conf.get("user") or DEFAULT_TOOL_PROMPTS["message_summary"]["user"]

    norm_messages: List[Dict[str, Any]] = []
    for m in messages:
        try:
            mid = m.get("id")
            t = m.get("time") or m.get("timestamp")
            if hasattr(t, "isoformat"):
                t = t.isoformat()  # datetime -> ISO string
            sender = m.get("sender") or m.get("sender_name")
            content = m.get("content") or m.get("content_text") or m.get("text")
            norm_messages.append(
                {
                    "id": str(mid) if mid is not None else "",
                    "time": t,
                    "sender": str(sender) if sender is not None else "",
                    "content": str(content) if content is not None else "",
                }
            )
        except Exception:
            # Best-effort fallback: convert values that have isoformat(); else use raw
            try:
                norm_messages.append({k: (v.isoformat() if hasattr(v, "isoformat") else v) for k, v in m.items()})  # type: ignore[arg-type]
            except Exception:
                norm_messages.append({"id": "", "time": None, "sender": "", "content": ""})

    payload_json = json.dumps(norm_messages, ensure_ascii=False)
    if "{{messages_json}}" in user_template:
        user_content = user_template.replace("{{messages_json}}", payload_json)
    else:
        user_content = user_template + "\n\n数据：\n" + payload_json
    exact_count_rule = (
        f"输入共 {len(norm_messages)} 条。必须返回 {len(norm_messages)} 个结果，"
        "每个结果保留对应输入 id；不得合并、遗漏、改写 id；只返回 JSON 数组。"
    )
    if prompt_key == "minutes_refine":
        exact_count_rule += (
            " 每个数组元素包含 id、summary、refined；refined 保存对应逐字稿的整理结果。"
            " 即使只有一条输入，也必须返回单元素 JSON 数组，不要返回单个对象。"
        )
    return [
        {"role": "system", "content": f"{system_prompt}\n\n{exact_count_rule}"},
        {"role": "user", "content": user_content},
    ]


# ------------------------- tool extraction -------------------------

def extract_message_features(
    messages: List[Dict[str, Any]],
    batch_size: int = 50,
    concurrency: int = 3,
    temperature: float = 0.1,
    *,
    prompt_key: str = "message_summary",
    model_override: str | None = None,
    route_key: str | None = None,
) -> Dict[str, Dict[str, Any]]:
    """小模型提取特征（按批并发调用）"""

    if concurrency < 1:
        concurrency = 1
    if batch_size < 1:
        batch_size = 1
    batch_size = min(batch_size, CLI_BATCH_LIMITS.get(prompt_key, 50))

    conf = load_ai_config()
    tool_prompt_conf = (conf.get("tool_prompts") or {}).get(prompt_key) or DEFAULT_TOOL_PROMPTS.get(prompt_key) or DEFAULT_TOOL_PROMPTS["message_summary"]
    desk_agent = DeskAgentClient.from_config(conf) if prompt_key in CLI_BATCH_PROMPTS else None
    # Keep the number of gateway tasks bounded when CLI batch routing is on.
    # The gateway limits active CLI processes; this avoids creating a large
    # backlog of HTTP tasks for a single summary run.
    if desk_agent is not None:
        concurrency = min(concurrency, 3)

    # 准备消息
    prepared: List[Dict[str, Any]] = []
    for msg in messages:
        msg_id = msg.get("id") or msg.get("time") or msg.get("message_id") or ""
        msg_id = str(msg_id)
        if not msg_id:
            continue
        content = str(msg.get("content") or msg.get("content_text") or msg.get("text") or "")
        # Short messages can fill a 50-item batch. Long meeting documents retain
        # more context and are split earlier by the total-character limit.
        item_limit = 8_000 if prompt_key in {"minutes_summary", "minutes_refine"} else 1_600
        if len(content) > item_limit:
            head_len = int(item_limit * 0.75)
            content = f"{content[:head_len]}\n...\n{content[-(item_limit - head_len):]}"
        prepared.append({
            "id": msg_id,
            "time": msg.get("time") or msg.get("timestamp"),
            "sender": msg.get("sender") or msg.get("sender_name"),
            "content": content,
        })

    errors: List[str] = []
    debug: List[Dict[str, Any]] = []

    def _parse_response_content(content: str, for_log_id: str) -> Any:
        if not content or not isinstance(content, str):
            raise ValueError(f"API返回为空或非字符串: {type(content)}")

        content_clean = content.strip()
        original_content = content_clean
        logger.debug("小模型原始返回 [%s] (前1000字符): %s", for_log_id, original_content[:1000])

        if content_clean.startswith("```"):
            lines = content_clean.split("\n", 1)
            if len(lines) > 1:
                content_clean = lines[1]
            if content_clean.startswith("json"):
                content_clean = content_clean[4:].lstrip()
            elif content_clean.startswith("JSON"):
                content_clean = content_clean[4:].lstrip()
        if content_clean.endswith("```"):
            content_clean = content_clean.rsplit("```", 1)[0].rstrip()

        data = None
        json_error = None
        try:
            data = json.loads(content_clean)
        except json.JSONDecodeError as je:
            json_error = je
            # Support providers that emit multiple top-level JSON objects back-to-back:
            # {"id":"1",...}{"id":"2",...}
            decoder = json.JSONDecoder()
            seq_items: List[Any] = []
            seq_pos = 0
            try:
                while seq_pos < len(content_clean):
                    while seq_pos < len(content_clean) and content_clean[seq_pos] in " \t\r\n,":
                        seq_pos += 1
                    if seq_pos >= len(content_clean):
                        break
                    obj, end = decoder.raw_decode(content_clean, seq_pos)
                    seq_items.append(obj)
                    seq_pos = end
                while seq_pos < len(content_clean) and content_clean[seq_pos] in " \t\r\n,":
                    seq_pos += 1
                if seq_items and seq_pos >= len(content_clean):
                    data = seq_items if len(seq_items) > 1 else seq_items[0]
            except Exception:
                pass
            if data is None and _HAS_JSON5:
                try:
                    data = json5.loads(content_clean)  # type: ignore
                except Exception:
                    pass
            array_match = re.search(r'\[[^\]]*(?:\{[^}]*\}[^\]]*)*\]', content_clean, re.DOTALL)
            if data is None and array_match:
                try:
                    data = json.loads(array_match.group(0))
                except json.JSONDecodeError:
                    if _HAS_JSON5:
                        try:
                            data = json5.loads(array_match.group(0))  # type: ignore
                        except Exception:
                            pass
            if data is None:
                brace_start = content_clean.find('{')
                if brace_start >= 0:
                    brace_count = 0
                    brace_end = -1
                    for i in range(brace_start, len(content_clean)):
                        if content_clean[i] == '{':
                            brace_count += 1
                        elif content_clean[i] == '}':
                            brace_count -= 1
                            if brace_count == 0:
                                brace_end = i
                                break
                    if brace_end > brace_start:
                        try:
                            json_str = content_clean[brace_start:brace_end + 1]
                            data = json.loads(json_str)
                        except json.JSONDecodeError:
                            if _HAS_JSON5:
                                try:
                                    data = json5.loads(json_str)  # type: ignore
                                except Exception:
                                    pass
            if data is None:
                json_matches = re.finditer(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content_clean, re.DOTALL)
                for match in json_matches:
                    try:
                        candidate = match.group(0)
                        data = json.loads(candidate)
                        break
                    except json.JSONDecodeError:
                        if _HAS_JSON5:
                            try:
                                data = json5.loads(candidate)  # type: ignore
                                break
                            except Exception:
                                pass
                        continue
            if data is None:
                error_detail = f"JSON解析失败: {json_error.msg if json_error else '未找到有效JSON'} (位置 {json_error.pos if json_error else 'N/A'})"
                logger.warning("小模型返回内容无法解析 [%s]: %s | 原始返回(前500字符): %s", for_log_id, error_detail, original_content[:500])
                raise ValueError(f"{error_detail}。原始返回(前300字符): {original_content[:300]}")
        return data

    def _normalize_item(item: Any, fallback_id: str) -> Dict[str, Any]:
        if not isinstance(item, dict):
            if isinstance(item, str):
                item = {"summary": item}
            else:
                raise ValueError(f"返回元素不是dict: {type(item)}")

        summary = str(item.get("summary") or "").strip()
        if not summary:
            alt = str(item.get("key_info") or item.get("markdown") or "").strip()
            summary = alt if alt else "ai: 信息有限"
        if not summary.lower().startswith("ai:"):
            summary = f"ai: {summary}"

        refined = str(
            item.get("refined")
            or item.get("content_refined")
            or item.get("refined_content")
            or item.get("minutes_refined")
            or ""
        ).strip()

        def _clean_points(value: Any) -> List[str]:
            if isinstance(value, list):
                raw_points = value
            elif isinstance(value, str):
                raw_points = re.split(r"[\n；;]+", value)
            else:
                raw_points = []
            points: List[str] = []
            for raw in raw_points:
                text = re.sub(r"^\s*[-*•\d.、）)]+\s*", "", str(raw or "")).strip()
                if not text:
                    continue
                points.append(text[:120])
                if len(points) >= 5:
                    break
            return points

        key_points = _clean_points(
            item.get("key_points")
            or item.get("points")
            or item.get("bullet_points")
            or item.get("highlights")
        )
        comment = str(
            item.get("comment")
            or item.get("one_sentence_comment")
            or item.get("review")
            or item.get("insight")
            or ""
        ).strip()[:160]

        meeting_number_raw = item.get("meeting_number") or ""
        meeting_number_digits = re.sub(r"\D", "", str(meeting_number_raw))
        meeting_number = meeting_number_digits if 9 <= len(meeting_number_digits) <= 13 else ""

        tone = str(item.get("tone") or "neutral").lower()
        allowed_tones = {"bullish", "bearish", "neutral", "meeting", "positive", "negative"}
        if tone not in allowed_tones:
            tone = "neutral"

        try:
            confidence = float(item.get("confidence", 0.5))
        except Exception:
            confidence = 0.5
        confidence = max(0.0, min(1.0, confidence))

        return {
            "id": str(item.get("id") or fallback_id or "").strip(),
            "summary": summary,
            "meeting_number": meeting_number,
            "tone": tone,
            "confidence": confidence,
            "refined": refined,
            "key_points": key_points,
            "comment": comment,
            "keywords": item.get("keywords") if isinstance(item.get("keywords"), list) else [],
            "platform": str(item.get("platform") or item.get("meeting_platform") or "").strip(),
            "category": str(item.get("category") or "").strip(),
            "summary_origin": str(item.get("summary_origin") or "tool").strip(),
        }

    def _local_fallback(item: Dict[str, Any]) -> Dict[str, Any]:
        text = re.sub(r"\s+", " ", str(item.get("content") or "")).strip()
        summary = text[:80].rstrip("，,；;。 ") if text else "信息有限"
        return {
            "summary": f"ai: {summary}",
            "summary_origin": "fallback",
            "meeting_number": "",
            "tone": "neutral",
            "confidence": 0.0,
            "refined": "",
            "key_points": [],
            "comment": "",
            "keywords": [],
            "platform": "",
            "category": "",
        }

    def _process_batch(batch: List[Dict[str, Any]]) -> tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
        batch_ids = [str(x.get("id") or "").strip() for x in batch]
        batch_tag = ",".join(batch_ids[:3]) + ("..." if len(batch_ids) > 3 else "")
        content = None
        source = "model"
        try:
            prompt = _tool_prompt_payload(
                batch,
                tool_prompt_conf,
                prompt_key=prompt_key,
            )
            if desk_agent is not None:
                module_id, capability, operation = CLI_TASK_META.get(
                    prompt_key,
                    (
                        "deepsee-news",
                        "deepsee.news.batch-analyze",
                        prompt_key,
                    ),
                )
                content = desk_agent.summarize(
                    batch,
                    prompt,
                    module_id=module_id,
                    capability=capability,
                    operation=operation,
                )
                source = "desk-agent"
            else:
                content = siliconflow_tool_chat(
                    prompt,
                    temperature=temperature,
                    model_override=model_override,
                    route_key=route_key,
                )
            data = _parse_response_content(content, batch_tag or "batch")

            items: List[Any] = []
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                if isinstance(data.get("items"), list):
                    items = data["items"]
                else:
                    items = [data]
            elif isinstance(data, str):
                items = [{"summary": data}]
            else:
                raise ValueError(f"返回结构不支持: {type(data)}")

            out: Dict[str, Dict[str, Any]] = {}
            for idx, it in enumerate(items):
                raw_id = str(it.get("id") or "").strip() if isinstance(it, dict) else ""
                fallback_id = batch_ids[idx] if len(items) == len(batch_ids) and idx < len(batch_ids) else ""
                if len(batch_ids) == 1:
                    fallback_id = batch_ids[0]
                norm = _normalize_item(it, fallback_id)
                rid = raw_id if raw_id in batch_ids and raw_id not in out else fallback_id
                if not rid or rid not in batch_ids or rid in out:
                    continue
                norm["id"] = rid
                out[rid] = {k: v for k, v in norm.items() if k != "id"}

            returned_count = len(items)
            matched_count = len(out)
            missing_ids = [bid for bid in batch_ids if bid and bid not in out]
            if desk_agent is not None:
                by_id = {str(item.get("id") or ""): item for item in batch}
                for bid in missing_ids:
                    out[bid] = _local_fallback(by_id.get(bid) or {})
                if missing_ids:
                    errors.append(f"{batch_tag}: CLI 返回缺少 {len(missing_ids)} 条，已本地兜底")

            dbg = [{
                "id": bid,
                "ok": (bid in out),
                "source": source,
                "input_count": len(batch_ids),
                "returned_count": returned_count,
                "matched_count": matched_count,
                "missing_count": len(missing_ids),
                "local_fallback": bid in missing_ids and desk_agent is not None,
                "raw": (content[:500] if isinstance(content, str) else str(type(content))),
            } for bid in batch_ids]
            return out, dbg
        except Exception as exc:
            raw_preview = None
            try:
                if content:
                    raw_preview = content[:2000] if isinstance(content, str) else str(content)[:2000]
            except Exception:
                raw_preview = None
            for bid in batch_ids:
                errors.append(f"{bid}: {exc}")
            if len(errors) <= 20 or (len(errors) % 10 == 0):
                logger.warning(
                    "小模型批量提取失败 [%s]: %s | 原始返回(前800字符): %s",
                    batch_tag,
                    str(exc),
                    raw_preview[:800] if raw_preview else "(无返回内容)",
                )
            fallback_out: Dict[str, Dict[str, Any]] = {}
            if desk_agent is not None:
                fallback_out = {
                    str(item.get("id") or ""): _local_fallback(item)
                    for item in batch
                    if str(item.get("id") or "")
                }
            dbg = [{
                "id": bid,
                "ok": bid in fallback_out,
                "source": "desk-agent" if desk_agent is not None else source,
                "input_count": len(batch_ids),
                "returned_count": 0,
                "matched_count": 0,
                "missing_count": len(batch_ids),
                "local_fallback": bid in fallback_out,
                "error": str(exc),
            } for bid in batch_ids]
            if raw_preview:
                for d in dbg[:1]:
                    d["raw"] = raw_preview[:1000]
            return fallback_out, dbg

    results: Dict[str, Dict[str, Any]] = {}

    batches = list(_batched(prepared, batch_size))
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        future_map = {executor.submit(_process_batch, b): b for b in batches}
        for future in as_completed(future_map):
            try:
                batch_res, dbg = future.result()
                if isinstance(dbg, list):
                    debug.extend(dbg)
                if isinstance(batch_res, dict):
                    results.update(batch_res)
            except Exception as exc:
                errors.append(str(exc))

    if errors:
        results["__errors__"] = errors
    results["__debug__"] = debug
    if errors:
        logger.warning("批量摘要部分失败: %s", "; ".join(errors[:5]))

    return results


# ---------------------------- adapters ----------------------------

def build_ai_input_messages(messages: List[Dict[str, Any]], features: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    for msg in messages:
        msg_id = str(msg.get("id") or msg.get("time") or msg.get("message_id") or len(enriched))
        feature = features.get(msg_id, {})
        enriched.append(
            {
                "id": msg_id,
                "time": msg.get("time") or msg.get("timestamp"),
                "sender": msg.get("sender_name") or msg.get("sender_id") or msg.get("sender"),
                "talker": msg.get("talker_name") or msg.get("chat_id"),
                "direction": msg.get("direction"),
                "message_type": msg.get("message_type") or msg.get("type"),
                "content": msg.get("content") or msg.get("content_text") or msg.get("text"),
                "importance": msg.get("importance_score"),
                "keywords": feature.get("keywords", []),
                "meeting_number": feature.get("meeting_number", ""),
                "platform": feature.get("platform", ""),
                "category": feature.get("category", ""),
                "summary": feature.get("summary", ""),
                # Normalize tone for downstream filters/modules
                "tone": str(feature.get("tone", "neutral")).lower(),
            }
        )
    return enriched


# ---------------------------- two-pass API ----------------------------

def ensure_message_features(
    db: Session,
    messages: List[Message],
    days_to_keep: int = 7,
    *,
    force: bool = False,
    batch_size: int = 50,
    concurrency: int = 3,
    temperature: float = 0.1,
    commit: bool = True,
) -> dict:
    """Overlay tool-model outputs onto Message.derived.

    Assumes populate_fallback_derived has already provided an initial snapshot.
    This function does NOT do any local fallback; it only updates rows where the tool
    produced results. summary_origin will be set to "tool" for updated rows.
    """
    if not messages:
        return {"updated": 0, "errors": []}

    cutoff = datetime.utcnow() - timedelta(days=days_to_keep)
    to_extract: List[Dict[str, Any]] = []
    updated = False
    updated_count = 0
    applied: List[Dict[str, Any]] = []

    def _vis_len(s: str) -> int:
        try:
            return len((s or '').replace('\n',' ').replace('\r',' ').replace('\t',' ').strip())
        except Exception:
            return len(s or '')

    def _should_send_to_tool(text: str) -> bool:
        clean = str(text or '').replace('\n', ' ').replace('\r', ' ').replace('\t', ' ').strip()
        if not clean:
            return False
        return _vis_len(clean) >= 20

    for msg in messages:
        # Skip very old messages unless force=True (explicit derive request)
        if (not force) and msg.timestamp and msg.timestamp < cutoff:
            continue

        text = (msg.content_text or "").strip()
        if not text:
            try:
                meta = msg.meta or {}
                contents = meta.get("contents") if isinstance(meta, dict) else None
                parts: list[str] = []
                if isinstance(contents, dict):
                    # Prefer true body content first; title/url are last-resort hints only
                    for k in ("content", "desc", "title", "url"):
                        v = contents.get(k)
                        if isinstance(v, str) and v.strip():
                            parts.append(v.strip())
                text = " \n".join(parts).strip()
            except Exception:
                text = ""
        # Skip only truly low-signal texts; meaningful short WeChat messages should still be covered.
        if not text or (not _should_send_to_tool(text)):
            continue

        # Skip non-text messages (image/file/video) entirely
        try:
            t = (msg.type or '').lower()
            if t in ('image','file','video'):
                continue
        except Exception:
            pass

        derived = msg.derived if isinstance(msg.derived, dict) else {}
        has_summary = bool(derived.get("summary"))
        origin = str(derived.get("summary_origin") or "").lower()
        if (not force) and has_summary and origin == "tool":
            continue

        to_extract.append({
            "id": str(msg.id),
            "content": text,
            "time": msg.timestamp.isoformat() if msg.timestamp else None,
        })

    if not to_extract:
        if updated and commit:
            db.commit()
        return {"updated": 0, "errors": []}

    # Per-channel model override: prefer tool_model_messages when configured
    model_ovr = None
    try:
        conf = load_ai_config()
        model_ovr = conf.get("tool_model_messages") or conf.get("tool_model")
    except Exception:
        model_ovr = None

    content_by_id = {str(item.get("id")): str(item.get("content") or "") for item in to_extract}

    features = extract_message_features(
        to_extract,
        batch_size=batch_size,
        concurrency=concurrency,
        temperature=temperature,
        prompt_key="message_summary",
        model_override=model_ovr,
        route_key="messages",
    )
    tool_errors = features.pop("__errors__", None)
    tool_debug = features.pop("__debug__", None)
    if tool_errors:
        logger.warning("小模型提取存在部分失败：%s", "; ".join(tool_errors))

    for msg in messages:
        fid = str(msg.id)
        data = features.get(fid)
        if not data:
            continue
        
        summary_text = str(data.get("summary") or "").strip()
        if not summary_text:
            continue
        if not summary_text.lower().startswith("ai:"):
            summary_text = f"ai: {summary_text}"
        
        meeting_number = str(data.get("meeting_number") or "").strip()
        tone = str(data.get("tone") or "neutral").lower()
        confidence = float(data.get("confidence", 0.5))

        def _fallback_points(source: str, summary: str) -> List[str]:
            text_value = re.sub(r"\s+", " ", str(source or summary or "")).strip()
            if not text_value:
                return []
            chunks = [x.strip() for x in re.split(r"[。；;！!？?\n]+", text_value) if x.strip()]
            scored = sorted(chunks, key=lambda x: (len(x) < 8, -len(x)))
            points: List[str] = []
            for chunk in scored:
                clean = re.sub(r"^\s*[-*•\d.、）)]+\s*", "", chunk).strip()
                if not clean or clean in points:
                    continue
                points.append(clean[:120])
                if len(points) >= 3:
                    break
            return points

        key_points = data.get("key_points") or _fallback_points(content_by_id.get(fid, ""), summary_text)
        comment = str(data.get("comment") or "").strip()
        if not comment:
            if tone in {"bullish", "positive"}:
                comment = "信号偏积极，建议跟踪后续兑现。"
            elif tone in {"bearish", "negative"}:
                comment = "信号偏谨慎，建议关注风险扩散。"
            elif tone == "meeting":
                comment = "会议类信息，建议确认时间与参会安排。"
            else:
                comment = "信息已提炼，建议按重要性继续跟进。"
        comment = comment[:160]
        
        platform = str(data.get("platform") or data.get("meeting_platform") or "").strip()
        summary_lower = summary_text.lower()
        if not platform and ("腾讯" in summary_text or "wemeet" in summary_lower):
            platform = "腾讯"
        elif not platform and ("进门" in summary_text or "jinmen" in summary_lower):
            platform = "进门"
        elif not platform and ("飞书" in summary_text or "feishu" in summary_lower):
            platform = "飞书"
        elif not platform and "zoom" in summary_lower:
            platform = "Zoom"
        elif not platform and "teams" in summary_lower:
            platform = "Teams"
        elif not platform and "钉钉" in summary_text:
            platform = "钉钉"
        elif not platform and ("外呼" in summary_text or re.search(r"(?i)tel|电话|phone", summary_text)):
            platform = "电话"

        body = re.sub(r'^\s*ai:\s*', '', summary_text, flags=re.IGNORECASE).strip()
        if platform:
            body = re.sub(rf"^\s*{re.escape(platform)}\s*[:：|]?\s*", "", body).strip()
        if meeting_number:
            body = re.sub(rf"^\s*(会议号[:：]?\s*)?{re.escape(meeting_number)}\s*[:：|]?\s*", "", body).strip()
            body = re.sub(rf"\s*(会议号[:：]?\s*)?{re.escape(meeting_number)}\s*$", "", body).strip()
        if platform:
            body = re.sub(rf"^\s*{re.escape(platform)}\s*[:：|]?\s*", "", body).strip()
        display_summary = f"ai: {body}".strip() if body else "ai:"

        summary_origin = "fallback" if data.get("summary_origin") == "fallback" else "tool"
        new_part: Dict[str, Any] = {
            "summary": display_summary,
            "meeting_number": meeting_number,
            "platform": platform,
            "tone": tone,
            "confidence": confidence,
            "summary_origin": summary_origin,
            "key_points": key_points,
            "comment": comment,
            # 兼容字段（保持向后兼容）
            "keywords": data.get("keywords") or [],
            "category": data.get("category") or "",
        }
        
        # Always assign a new dict instance so SQLAlchemy marks column as changed
        before = msg.derived if isinstance(msg.derived, dict) else {}
        merged = dict(before)
        merged.update({k: v for k, v in new_part.items()})
        msg.derived = merged
        db.add(msg)
        updated = True
        updated_count += 1
        try:
            applied.append({
                "id": int(getattr(msg, 'id')),
                "summary": summary_text,
                "origin": summary_origin,
            })
        except Exception:
            pass

    if updated and commit:
        _commit_with_retry(db)
    return {"updated": updated_count, "errors": tool_errors or [], "debug": tool_debug or [], "applied": applied}


def populate_fallback_derived(
    db: Session,
    messages: List[Message],
    days_to_keep: int = 7,
    *,
    force: bool = False,
    summary_limit: int = 50,
    commit: bool = True,
) -> int:
    """Write fallback snapshot first for instant UI.

    Skip rows that already have summary_origin=tool unless force is True.
    Returns number of rows updated.
    """
    cutoff = datetime.utcnow() - timedelta(days=days_to_keep)
    changed = 0

    def _fallback_keywords(text: str, topk: int = 5) -> List[str]:
        if not text:
            return []
        t = re.sub(r"https?://\S+", " ", text)
        t = re.sub(r"#[A-Za-z0-9_]+|@\S+", " ", t)
        t = re.sub(r"\b\d{5,}\b", " ", t)
        tokens = re.split(r"[^\w\u4e00-\u9fff]+", t)
        tokens = [k.strip().lower() for k in tokens if k.strip()]
        stop = {"的","了","和","是","在","对","及","与","于","以及","相关","我们","他们","你们","你","我","他","她","它","这个","那个","进行","公司","行业","板块","认为","建议","报告","最新","今天","明天","市场","影响","可能"}
        freq: Dict[str,int] = {}
        for k in tokens:
            if k in stop:
                continue
            if re.fullmatch(r"\d{5,}", k):
                continue
            freq[k] = freq.get(k, 0) + 1
        return [w for w,_ in sorted(freq.items(), key=lambda x:x[1], reverse=True)[:topk]]

    def _fallback_summary(text: str, limit: int) -> str:
        if not text:
            return ""
        t = re.sub(r"https?://\S+", "", text)
        t = re.sub(r"[\s]+", " ", t).strip()
        return (t[:limit] + ("…" if len(t) > limit else ""))

    def _fallback_meeting(text: str) -> tuple[str,str]:
        if not text:
            return "",""
        # Robust number detection: 9–13 digits, 9–10 digits, hyphenated forms, +86-, 400-xxx-xxxx
        patterns = [
            r"(?<!\d)(\d{9,13})(?!\d)",
            r"(?<!\d)(\d{9,10})(?!\d)",
            r"(\d{3}[-\s]?\d{3}[-\s]?\d{3,6})",
            r"\+?86[-\s]?(\d{3}[-\s]?\d{3}[-\s]?\d{3,6}|\d{8,12})",
            r"(400[-\s]?\d{3}[-\s]?\d{4})",
        ]
        number = ""
        for pat in patterns:
            m = re.search(pat, text)
            if m:
                g = m.group(1) if m.groups() else m.group(0)
                number = re.sub(r"\D", "", g)
                break
        platform = ""
        low = text.lower()
        if "腾讯会议" in text or "wemeet" in low or "meeting.tencent.com" in low:
            platform = "腾讯"
        elif "进门财经" in text or "jinmen" in low:
            platform = "进门"
        elif "飞书" in text or "feishu" in low or "lark" in low:
            platform = "飞书"
        elif "zoom" in low:
            platform = "Zoom"
        elif "teams" in low or "microsoft.com" in low:
            platform = "Teams"
        elif "钉钉" in text or "dingtalk" in low:
            platform = "钉钉"
        elif "电话会" in text or "电话会议" in text or "外呼" in text or re.search(r"(?i)tel|电话|phone", text):
            platform = "电话"
        return number, platform

    def _infer_tone(text: str) -> str:
        low = (text or '').lower()
        pos = ('看多','利好','上调','增持','上涨','改善','超预期','提价','回暖','反弹','增长','积极','强势')
        neg = ('看空','利空','下调','减持','下跌','承压','不及预期','回落','下滑','风险','下行','疲弱')
        if any(p in text for p in pos) or any(p in low for p in ('bullish','positive')):
            return 'bullish'
        if any(n in text for n in neg) or any(n in low for n in ('bearish','negative')):
            return 'bearish'
        return 'neutral'

    def _extract_key_info(text: str) -> str:
        """Heuristic key_info from full body: prefer 观点/结论/主旨，再看 建议/下一步，兼顾标的/行业。"""
        if not text:
            return ''
        t = re.sub(r"\s+", " ", text)
        # 1) 明确标注的观点/结论/主旨
        m = re.search(r"(?:观点|结论|主旨|判断)[:：]\s*([^；。\n]{6,60})", t)
        if m:
            return m.group(1).strip()
        # 2) 建议/下一步
        m = re.search(r"(?:建议|下一步|行动|策略)[:：]\s*([^；。\n]{6,60})", t)
        if m:
            return m.group(1).strip()
        # 3) 简要抽取前一句较长语句
        m = re.search(r"([^；。\n]{6,60})(?:；|。|\n)", t)
        return (m.group(1).strip() if m else t[:60]).strip()

    for msg in messages:
        if msg.timestamp and msg.timestamp < cutoff:
            continue
        derived = msg.derived if isinstance(msg.derived, dict) else {}
        origin = str(derived.get("summary_origin") or "").lower()
        if origin == "tool" and not force:
            continue
        text = (msg.content_text or "").strip()
        if not text:
            meta = msg.meta or {}
            contents = meta.get("contents") if isinstance(meta, dict) else None
            parts: list[str] = []
            if isinstance(contents, dict):
                for k in ("title", "desc", "content", "url"):
                    v = contents.get(k)
                    if isinstance(v, str) and v.strip():
                        parts.append(v.strip())
            text = " \n".join(parts).strip()
        if not text:
            continue
        if len(text.replace('\n', ' ').replace('\r', ' ').replace('\t', ' ').strip()) < 20:
            continue

        kws = _fallback_keywords(text, topk=5)
        summ = _fallback_summary(text, limit=summary_limit)
        num, plat = _fallback_meeting(text)
        # key_info: 倾向 观点/结论/主旨/建议，长于 6 字。
        key_src = _extract_key_info(text) or summ or text[:60]
        # 轻量实体增强：若 key_info 中未明显包含“行业/标的”，且空间允许，则补充首个行业/代码
        ents = _detect_entities(text)
        enrich_parts: list[str] = []
        base = key_src
        def _present(s: str, frag: str) -> bool:
            return frag and (frag in s)
        # prefer industry then ticker
        if ents.get("industries"):
            ind = ents["industries"][0]
            if not _present(base, ind):
                enrich_parts.append(ind)
        for group in ("a", "hk", "us"):
            codes = ents.get(group) or []
            if codes:
                code = codes[0]
                if not _present(base, code):
                    enrich_parts.append(code)
                    break
        if enrich_parts:
            candidate = (base + " | " + " ".join(enrich_parts)).strip()
            key_src = candidate
        def _clip_vis(s: str, limit: int) -> str:
            acc = []
            for ch in (s or "").strip():
                if len("".join(acc).replace(" ", "")) >= limit:
                    break
                acc.append(ch)
            return "".join(acc).strip()
        key_info = _clip_vis(key_src, 30)
        tone = _infer_tone(text)
        # 形成可阅读的 summary_full（结论/建议/要点拼接）
        parts = []
        if key_info:
            parts.append(f"结论：{key_info}")
        sug = re.search(r"(?:建议|下一步|行动)[:：]\s*([^；。\n]{4,60})", text)
        if sug:
            parts.append(f"建议：{sug.group(1).strip()}")
        # 选取一条依据
        ev = re.search(r"(?:依据|原因|背景)[:：]\s*([^；。\n]{4,60})", text)
        if ev:
            parts.append(f"依据：{ev.group(1).strip()}")
        summary_full = "；".join(parts)[:180]
        new_derived = {
            "keywords": kws,
            "meeting_number": num,
            "platform": plat,
            "tone": tone,
            "summary": f"fallback: {summ}" if summ else "fallback: ",
            "summary_origin": "fallback",
            "key_info": key_info,
            "key_info_origin": "fallback",
            "summary_full": summary_full,
        }
        before = msg.derived if isinstance(msg.derived, dict) else {}
        # Do not override tool results unless force=True
        try:
            if (not force) and isinstance(before, dict) and str(before.get("summary_origin") or '').lower() == 'tool':
                continue
        except Exception:
            pass
        if any(before.get(k) != v for k, v in new_derived.items()):
            merged = dict(before)
            merged.update(new_derived)
            msg.derived = merged
            db.add(msg)
            changed += 1

    if changed and commit:
        _commit_with_retry(db)
    return changed
# ---------------------- lightweight entity dictionary ----------------------

_DEFAULT_INDUSTRIES: list[str] = [
    "半导体", "芯片", "集成电路", "算力", "人工智能", "AI", "云计算",
    "新能源", "光伏", "储能", "风电", "锂电", "动力电池",
    "煤炭", "石油", "有色", "钢铁", "化工", "机械",
    "汽车", "汽车零部件", "整车", "电动车",
    "银行", "券商", "保险",
    "白酒", "消费", "家电",
    "医药", "生物", "医疗",
    "军工", "国防",
    "地产", "房地产",
    "通信", "电力", "公用事业",
    "TMT", "软件", "游戏", "传媒", "互联网", "电商", "物流", "航运", "航空",
]

def _load_external_industries() -> list[str]:
    """Optionally load extra industries from data/entities.json: {"industries": [...]}"""
    try:
        import os, json
        path = os.path.abspath(os.path.join(os.getcwd(), 'data', 'entities.json'))
        if not os.path.exists(path):
            return []
        with open(path, 'r', encoding='utf-8') as f:
            j = json.load(f)
        inds = j.get('industries') if isinstance(j, dict) else None
        if isinstance(inds, list):
            return [str(x) for x in inds if isinstance(x, (str, int))]
        return []
    except Exception:
        return []

def _detect_entities(text: str) -> dict[str, list[str]]:
    """Detect lightweight entities: A/H/US tickers and industries.

    - A-share: 60x/00x/30x/68x patterns (strict 6 digits)
    - HK: 4 digits + .HK or HKxxxx
    - US: after prefixes (NASDAQ|NYSE|AMEX|US:|Ticker:|代码:) + 1-5 uppercase letters
    - industries: substring match from a small dictionary
    """
    if not text:
        return {"a": [], "hk": [], "us": [], "industries": []}
    low = text.lower()
    # A-share 6-digit codes
    a_pat = re.compile(r"(?<!\d)(?:60\d{4}|601\d{3}|603\d{3}|605\d{3}|000\d{3}|001\d{3}|002\d{3}|300\d{3}|301\d{3}|688\d{3})(?!\d)")
    a_codes = a_pat.findall(text)
    # HK codes
    hk_pat1 = re.compile(r"\b\d{4}\.(?:hk|HK)\b")
    hk_pat2 = re.compile(r"\b(?:hk|HK)\d{4}\b")
    hk_codes = sorted(set(hk_pat1.findall(text) + hk_pat2.findall(text)))
    # US tickers with context
    us_pat = re.compile(r"\b(?:NASDAQ|NYSE|AMEX|US:|Ticker[:：]|代码[:：])\s*([A-Z]{1,5})\b")
    us_codes = [m.group(1) for m in us_pat.finditer(text)]
    # industries (dedup preserve order)
    inds: list[str] = []
    seen = set()
    ext_inds = _load_external_industries()
    for ind in list(dict.fromkeys(_DEFAULT_INDUSTRIES + ext_inds)):
        if ind in text and ind not in seen:
            inds.append(ind)
            seen.add(ind)
    return {"a": a_codes[:3], "hk": hk_codes[:3], "us": us_codes[:3], "industries": inds[:3]}
