from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import Any, Iterable

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Chat, Contact, Message


# Seed detection aims to capture actual "invitation" intents, not generic strategy notes.
ACTION_RE = re.compile(r"(邀请|请|麻烦|能否|可否|方便|约|安排|来|参加|出席|连线|一起|沟通|交流)", re.IGNORECASE)
SEED_TOPIC_RE = re.compile(
    r"(路演|分享会|交流会|电话会|电话会议|会议|直播|闭门|拜访|见面|连线|演讲)",
    re.IGNORECASE,
)
NEGATIVE_SEED_RE = re.compile(r"(复盘|日报|周报|晨报|晚报|汇总|快讯|策略跟踪|观点合集|市场观点|纪要整理)", re.IGNORECASE)
MEETING_CONTEXT_RE = re.compile(r"(腾讯会议|进门财经|飞书|Zoom|Teams|钉钉|电话会|电话会议|会议|路演|连线|直播|分享会|交流会|见面|拜访)", re.IGNORECASE)
SPEAKER_INVITE_RE = re.compile(
    r"(想请|邀请|能否请|可否请|麻烦|方便|劳驾).{0,8}(您|你|老师|总|博士|嘉宾).{0,10}(分享|讲|发言|交流|点评|路演|访谈|连线)",
    re.IGNORECASE,
)
# Strict "invite you to speak/share" intent: avoids false positives like "请支持/请投票".
SPEAKER_DIRECT_RE = re.compile(
    r"(想请|邀请|能否|可否|麻烦|方便|劳驾|请).{0,12}(你|您).{0,20}(分享|讲观点|讲|发言|交流|点评|路演|演讲|访谈|连线)",
    re.IGNORECASE,
)
ROLE_RE = re.compile(r"(主讲|发言|分享|嘉宾|点评|访谈|主持|连线)", re.IGNORECASE)
BROADCAST_RE = re.compile(r"(今日共\d+场|欢迎参会|报名参会|路演安排|转发|订阅|点击|场次|排期|扫码|二维码)", re.IGNORECASE)
# Helper patterns (used in tokenization/filters).
SECOND_PERSON_RE = re.compile(r"(你|您)", re.IGNORECASE)
GREETING_RE = re.compile(r"^[\u4e00-\u9fffA-Za-z0-9]{1,6}(总|老师|兄|姐|哥|博士)", re.IGNORECASE)

SCHEDULE_HINT_RE = re.compile(
    r"(时间|几点|何时|什么时候|今晚|明天|后天|周[一二三四五六日天]|下周|本周|下午|上午|中午|晚上|\d{1,2}[:：]\d{2}|\d{1,2}[月/\.\-]\d{1,2})",
    re.IGNORECASE,
)
PLACE_RE = re.compile(
    r"(腾讯会议|进门财经|飞书|Zoom|Teams|钉钉|电话会议|线下|国贸|望京|金融街|中关村|会议室|咖啡|办公室)",
    re.IGNORECASE,
)
MEETING_NO_RE = re.compile(r"(会议号|meeting\s*id|会议ID|会号|ID|密码|passcode)[：:\s-]*([0-9\-\s]{6,})", re.IGNORECASE)
MEETING_NO_ALT_RE = re.compile(r"(#\s*腾讯会议|腾讯会议)[:：]\s*([0-9\-\s]{6,})", re.IGNORECASE)

ACCEPT_RE = re.compile(r"(好|可以|行|没问题|收到|参加|到|ok|OK|安排|确认|约|可以的)", re.IGNORECASE)
DECLINE_RE = re.compile(r"(不行|不方便|没空|改期|下次|再约|抱歉|取消|推迟|无法)", re.IGNORECASE)


def _safe_text(v: Any) -> str:
    return str(v or "").strip()


def _norm(s: str) -> str:
    # Collapse whitespace (including NBSP) into single spaces for stable matching.
    return re.sub(r"[\s\u00A0]+", " ", _safe_text(s)).strip()


def _tokenize(s: str) -> set[str]:
    s = _norm(s)
    if not s:
        return set()
    toks = set(re.findall(r"[A-Za-z]{2,}|[\u4e00-\u9fff]{2,8}", s))
    # Drop very generic tokens that cause false merges
    stop = {"今天", "明天", "后天", "下午", "上午", "晚上", "中午", "时间", "会议", "交流", "分享", "路演", "策略", "观点"}
    return {t for t in toks if t not in stop}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _extract_platform_and_place(text: str) -> tuple[str | None, str | None]:
    t = _safe_text(text)
    if not t:
        return None, None
    m = PLACE_RE.search(t)
    if not m:
        return None, None
    place = m.group(1)
    platform = place
    # Normalize a few
    if "腾讯" in place:
        platform = "腾讯会议"
    if "进门" in place:
        platform = "进门财经"
    if place.lower() == "zoom":
        platform = "Zoom"
    if place.lower() == "teams":
        platform = "Teams"
    if place.lower() == "lark" or "飞书" in place:
        platform = "飞书"
    return platform, place


def _parse_event_time_from_text(text: str, anchor: datetime | None) -> datetime | None:
    """Best-effort parse event time from a message body.

    Supports:
    - 2025-09-24 19:30 / 09-24 19:30 / 9月24日 19:30 / 9/24 19:30
    - time-only "19:30" -> anchored to the same day as anchor
    - relative day words: 今天/明天/后天
    """
    t = _safe_text(text)
    if not t:
        return None

    # Normalize weird "1 :3" => "1:3"
    t2 = re.sub(r"(\d)\s*[:：]\s*(\d)", r"\1:\2", t)
    t2 = re.sub(r"(\d)\s*[:：]\s*(\d{2})", r"\1:\2", t2)

    # Parse date part first (allow separators and optional year)
    date_m = re.search(r"(?:(?P<y>20\d{2})[年/\.\-])?(?P<m>\d{1,2})[月/\.\-](?P<d>\d{1,2})(?:日)?", t2)
    time_m = re.search(r"(?P<h>\d{1,2})[:：](?P<mi>\d{1,2})", t2)
    if date_m and time_m:
        y = int(date_m.group("y") or (anchor.year if anchor else datetime.utcnow().year))
        mm = int(date_m.group("m"))
        dd = int(date_m.group("d"))
        hh = int(time_m.group("h"))
        mi_raw = time_m.group("mi")
        mi = int(mi_raw)
        if len(mi_raw) == 1:
            mi = mi * 10  # 9:3 -> 9:30
        # Heuristic: 1-7 o'clock in meeting texts is more likely afternoon unless explicitly 上午/凌晨
        if hh <= 7 and ("上午" not in t2) and ("凌晨" not in t2) and ("早上" not in t2):
            if "下午" in t2 or "晚上" in t2:
                hh += 12
            else:
                # Many broker schedules omit 下午; default to PM for very small hours
                hh += 12
        try:
            return datetime(y, mm, dd, hh, mi)
        except Exception:
            return None

    # Relative day + time
    m = re.search(r"(今天|明天|后天)\s*(?P<h>\d{1,2})[:：](?P<mi>\d{2})", t)
    if m and anchor:
        delta = {"今天": 0, "明天": 1, "后天": 2}.get(m.group(1), 0)
        hh = int(m.group("h"))
        mi = int(m.group("mi"))
        day = (anchor + timedelta(days=delta)).date()
        return datetime(day.year, day.month, day.day, hh, mi)

    # Time-only
    m = re.search(r"(?P<h>\d{1,2})[:：](?P<mi>\d{2})", t)
    if m and anchor:
        hh = int(m.group("h"))
        mi = int(m.group("mi"))
        day = anchor.date()
        return datetime(day.year, day.month, day.day, hh, mi)

    return None


def _extract_topic(text: str) -> str | None:
    t = _norm(text)
    if not t:
        return None
    # Bracketed headline like 【xxx】yyy
    first_line = re.split(r"[\n\r]", t)[0].strip()
    if first_line.startswith("【") or first_line.startswith("["):
        # Keep the whole headline (often contains organizer + topic).
        return first_line[:80]
    # Prefer explicit markers
    m = re.search(r"(主题|分享|交流|路演|策略|观点)[:：\s]+([^\n\r]{4,60})", t)
    if m:
        cand = _norm(m.group(2))
        cand = re.split(r"[，,。.!！?？；;（(【\\[]", cand)[0].strip()
        return cand[:60] if cand else None

    # Otherwise, take the first "sentence" as a weak topic
    cand = re.split(r"[\n\r。.!！?？；;]", t)[0].strip()
    cand = re.sub(r"^(请|麻烦|方便|能否|可否|想|我想|我们|这边)\s*", "", cand)
    if len(cand) >= 6:
        return cand[:60]
    return None


def _extract_meeting_number(text: str) -> str | None:
    t = _safe_text(text)
    if not t:
        return None
    m = MEETING_NO_RE.search(t)
    if not m:
        m = MEETING_NO_ALT_RE.search(t)
    if not m:
        return None
    digits = re.sub(r"\D", "", m.group(2) or "")
    if 6 <= len(digits) <= 13:
        return digits
    return None


def _split_invite_segments(text: str) -> list[str]:
    """Split a broadcast invite message into per-session segments.

    Supports common formats like:
    - '1️⃣ ...' '2️⃣ ...'
    - '1)' '2.' '3、'
    """
    # Keep newlines for segment detection; only normalize CRLF.
    t = _safe_text(text).replace("\r\n", "\n").replace("\r", "\n").strip()
    if not t:
        return []
    # Detect common list markers (keycap digits like 1️⃣ are multi-codepoint).
    vs16 = "\ufe0f"
    keycap = "\u20e3"
    keycap_pat = rf"[0-9]{vs16}?{keycap}"
    marker = re.compile(rf"(?:^|\n)\s*(?:{keycap_pat}|\d+[\)\.]|[一二三四五六七八九十]+、)\s*")
    hits = list(marker.finditer(t))
    if len(hits) <= 1:
        return [_norm(t)]
    segs: list[str] = []
    for i, h in enumerate(hits):
        start = h.start()
        end = hits[i + 1].start() if i + 1 < len(hits) else len(t)
        seg = t[start:end].strip()
        # Strip marker prefix
        seg = marker.sub("", seg, count=1).strip()
        seg = _norm(seg)
        if len(seg) >= 12:
            segs.append(seg)
    return segs or [_norm(t)]


def _classify_status(context: list["MessageRow"]) -> str:
    """accepted/declined/pending based on the last inbound signal."""
    # Prefer the latest inbound message with a clear signal
    inbound = [m for m in context if (m.direction or "").lower() == "in"]
    for m in reversed(inbound[-30:]):
        txt = _norm(m.content_text)
        if not txt:
            continue
        if DECLINE_RE.search(txt):
            return "declined"
        if ACCEPT_RE.search(txt):
            return "accepted"
    return "pending"


@dataclass
class MessageRow:
    id: int
    timestamp: str
    direction: str | None
    sender_name: str | None
    content_text: str | None


@dataclass
class InviteEvent:
    contact_id: str
    contact_name: str | None
    chat_id: str
    initiator: str  # contact/me
    first_invite_at: str
    last_activity_at: str
    event_time: str | None
    platform: str | None
    place: str | None
    meeting_number: str | None
    topic: str | None
    status: str
    source_message_ids: list[int]
    messages: list[MessageRow]


def extract_invite_events(
    db: Session,
    *,
    year: int = 2025,
    include_outgoing_seeds: bool = False,
    mode: str = "speaker",
    window_before_hours: int = 24,
    window_after_hours: int = 72,
    merge_gap_hours: int = 12,
    max_events: int = 2000,
    max_messages_per_event: int = 30,
) -> dict[str, Any]:
    """Extract roadshow/strategy-sharing invitation events from WeChat messages."""
    start = datetime(year, 1, 1)
    end = datetime(year + 1, 1, 1)

    # Only non-chatroom chats (single contacts)
    chat_ids = set(
        db.execute(select(Chat.id).where(Chat.is_chatroom == False))  # noqa: E712
        .scalars()
        .all()
    )

    # Seed invitations: primarily inbound ("对我邀请"), optionally include outgoing too.
    seed_dirs = {"in"}
    if include_outgoing_seeds:
        seed_dirs.add("out")

    # Fetch seeds first (narrow query).
    seeds: list[Message] = []
    q = (
        select(Message)
        .where(Message.chat_id.in_(chat_ids))
        .where(Message.timestamp >= start)
        .where(Message.timestamp < end)
        .where(Message.direction.in_(list(seed_dirs)))
        .where(Message.content_text.is_not(None))
        .order_by(Message.timestamp.asc())
    )
    for m in db.execute(q).scalars().all():
        txt = _norm(m.content_text)
        if not txt:
            continue
        # Avoid counting generic notes as "invites". If it's a recap/report, require strong meeting context.
        if NEGATIVE_SEED_RE.search(txt) and not MEETING_CONTEXT_RE.search(txt):
            continue

        if not ACTION_RE.search(txt):
            continue

        # Must contain meeting-like topic, OR strategy/viewpoint with explicit meeting context.
        has_meeting_topic = bool(SEED_TOPIC_RE.search(txt))
        has_strategy_view = bool(re.search(r"(策略|观点)", txt))
        if not (has_meeting_topic or (has_strategy_view and MEETING_CONTEXT_RE.search(txt))):
            continue

        if mode in {"speaker", "direct", "to_me"}:
            # Direct-to-me invites: exclude broadcast schedules, require second-person or a greeting like "李兄/王总".
            if BROADCAST_RE.search(txt):
                continue
            if not (SECOND_PERSON_RE.search(txt) or GREETING_RE.search(txt)):
                continue

        if mode in {"speak", "speaker_strict"}:
            # Strict "invite you to speak/share".
            if BROADCAST_RE.search(txt):
                continue
            if not (SPEAKER_DIRECT_RE.search(txt) or SPEAKER_INVITE_RE.search(txt)):
                continue

        # Require some schedule hint or platform/meeting number.
        if not (SCHEDULE_HINT_RE.search(txt) or PLACE_RE.search(txt) or MEETING_NO_RE.search(txt)):
            continue
        seeds.append(m)

    if not seeds:
        return {
            "meta": {"year": year, "seeds": 0, "events": 0},
            "stats": {"total_events": 0},
            "events": [],
        }

    # Group seeds by chat_id to batch-fetch context messages.
    by_chat: dict[str, list[Message]] = {}
    for s in seeds:
        if not s.chat_id:
            continue
        by_chat.setdefault(str(s.chat_id), []).append(s)

    # Lookup contacts for display names.
    contacts = {c.id: c for c in db.execute(select(Contact)).scalars().all()}

    events: list[InviteEvent] = []
    events_by_contact: dict[str, list[InviteEvent]] = {}
    merged_seed_count = 0

    before = timedelta(hours=window_before_hours)
    after = timedelta(hours=window_after_hours)
    merge_gap = timedelta(hours=merge_gap_hours)

    for chat_id, chat_seeds in by_chat.items():
        chat_seeds.sort(key=lambda x: x.timestamp or start)
        min_ts = min((s.timestamp for s in chat_seeds if s.timestamp), default=start) - before
        max_ts = max((s.timestamp for s in chat_seeds if s.timestamp), default=start) + after

        chat_msgs = (
            db.execute(
                select(Message)
                .where(Message.chat_id == chat_id)
                .where(Message.timestamp >= min_ts)
                .where(Message.timestamp <= max_ts)
                .where(Message.content_text.is_not(None))
                .order_by(Message.timestamp.asc())
            )
            .scalars()
            .all()
        )

        # Candidate contact id for this chat (for single chats, chat_id is typically wxid).
        contact_id = chat_id
        contact = contacts.get(contact_id)
        contact_name = None
        if contact:
            contact_name = contact.name or contact.alias

        # Build per-seed event candidates.
        contact_events = events_by_contact.setdefault(contact_id, [])

        for seed in chat_seeds:
            if not seed.timestamp:
                continue
            anchor = seed.timestamp
            w_start = anchor - before
            w_end = anchor + after
            context = [m for m in chat_msgs if m.timestamp and (w_start <= m.timestamp <= w_end)]
            if not context:
                continue

            seed_txt_raw = _safe_text(seed.content_text)
            initiator = "contact" if (seed.direction or "").lower() == "in" else "me"
            segments = _split_invite_segments(seed_txt_raw)

            for seg in segments:
                platform, place = _extract_platform_and_place(seg)
                meeting_no = _extract_meeting_number(seg)
                event_dt = _parse_event_time_from_text(seg, anchor)
                topic = _extract_topic(seg)

                # Improve details from context (later confirmations may carry the real time/place/topic).
                for cm in context[-20:]:
                    t = _norm(cm.content_text)
                    if not t:
                        continue
                    if not event_dt:
                        event_dt = _parse_event_time_from_text(t, anchor)
                    if not platform and PLACE_RE.search(t):
                        platform, place = _extract_platform_and_place(t)
                    if not meeting_no:
                        meeting_no = _extract_meeting_number(t)
                    if not topic:
                        topic = _extract_topic(t)

                # Build condensed message rows and choose "relevant" snippets first.
                relevant: list[MessageRow] = []
                for cm in context:
                    txt = _norm(cm.content_text)
                    if not txt:
                        continue
                    is_relevant = bool((ACTION_RE.search(txt) and MEETING_CONTEXT_RE.search(txt)) or SCHEDULE_HINT_RE.search(txt) or PLACE_RE.search(txt) or MEETING_NO_RE.search(txt) or MEETING_NO_ALT_RE.search(txt))
                    if not is_relevant:
                        continue
                    relevant.append(
                        MessageRow(
                            id=int(cm.id),
                            timestamp=(cm.timestamp.isoformat(sep=" ", timespec="minutes") if cm.timestamp else ""),
                            direction=(cm.direction or ""),
                            sender_name=cm.sender_name,
                            content_text=txt[:500],
                        )
                    )

                # Fallback: include the segment / seed message at least.
                if not relevant:
                    relevant = [
                        MessageRow(
                            id=int(seed.id),
                            timestamp=(seed.timestamp.isoformat(sep=" ", timespec="minutes") if seed.timestamp else ""),
                            direction=(seed.direction or ""),
                            sender_name=seed.sender_name,
                            content_text=seg[:500],
                        )
                    ]

                # Keep it bounded.
                msgs_out = relevant[:max_messages_per_event]
                status = _classify_status(msgs_out)

                candidate = InviteEvent(
                    contact_id=contact_id,
                    contact_name=contact_name,
                    chat_id=chat_id,
                    initiator=initiator,
                    first_invite_at=anchor.isoformat(sep=" ", timespec="minutes"),
                    last_activity_at=(context[-1].timestamp.isoformat(sep=" ", timespec="minutes") if context[-1].timestamp else anchor.isoformat(sep=" ", timespec="minutes")),
                    event_time=(event_dt.isoformat(sep=" ", timespec="minutes") if event_dt else None),
                    platform=platform,
                    place=place,
                    meeting_number=meeting_no,
                    topic=topic,
                    status=status,
                    source_message_ids=[int(seed.id)],
                    messages=msgs_out,
                )

                # Merge into an existing event for this contact.
                merged = False
                cand_tokens = _tokenize((candidate.topic or "") + " " + _norm(candidate.place or "") + " " + _norm(candidate.platform or ""))
                for ev in reversed(contact_events[-400:]):
                    # Merge if same meeting number
                    if ev.meeting_number and candidate.meeting_number and ev.meeting_number == candidate.meeting_number:
                        merged = True
                    else:
                        # Merge if close in time and semantically similar
                        base_time = None
                        cand_time = None
                        try:
                            base_time = datetime.fromisoformat(ev.first_invite_at)
                            cand_time = datetime.fromisoformat(candidate.first_invite_at)
                        except Exception:
                            base_time = None
                            cand_time = None
                        if base_time and cand_time and abs(cand_time - base_time) <= merge_gap:
                            ev_tokens = _tokenize((ev.topic or "") + " " + _norm(ev.place or "") + " " + _norm(ev.platform or ""))
                            if _jaccard(ev_tokens, cand_tokens) >= 0.35:
                                merged = True

                    if merged:
                        merged_seed_count += 1
                        ev.last_activity_at = max(ev.last_activity_at, candidate.last_activity_at)
                        # Prefer richer fields
                        ev.event_time = ev.event_time or candidate.event_time
                        ev.platform = ev.platform or candidate.platform
                        ev.place = ev.place or candidate.place
                        ev.topic = ev.topic or candidate.topic
                        ev.meeting_number = ev.meeting_number or candidate.meeting_number
                        # Status: accepted > declined > pending
                        if ev.status != "accepted":
                            if candidate.status == "accepted":
                                ev.status = "accepted"
                            elif ev.status == "pending" and candidate.status == "declined":
                                ev.status = "declined"
                        ev.source_message_ids.extend(candidate.source_message_ids)
                        # Merge snippets, keep unique by id
                        existing_ids = {m.id for m in ev.messages}
                        for mrow in candidate.messages:
                            if mrow.id not in existing_ids and len(ev.messages) < max_messages_per_event:
                                ev.messages.append(mrow)
                        break

                if not merged:
                    contact_events.append(candidate)
                    events.append(candidate)
                    if len(events) >= max_events:
                        break

            if len(events) >= max_events:
                break

        if len(events) >= max_events:
            break

    # Stats
    def _month_key(s: str) -> str:
        try:
            dt = datetime.fromisoformat(s)
            return dt.strftime("%Y-%m")
        except Exception:
            return f"{year}-??"

    by_status: dict[str, int] = {"accepted": 0, "declined": 0, "pending": 0}
    by_month: dict[str, int] = {}
    by_contact: dict[str, int] = {}
    by_platform: dict[str, int] = {}

    for ev in events:
        by_status[ev.status] = by_status.get(ev.status, 0) + 1
        by_month[_month_key(ev.first_invite_at)] = by_month.get(_month_key(ev.first_invite_at), 0) + 1
        key = ev.contact_name or ev.contact_id
        by_contact[key] = by_contact.get(key, 0) + 1
        if ev.platform:
            by_platform[ev.platform] = by_platform.get(ev.platform, 0) + 1

    top_contacts = sorted(by_contact.items(), key=lambda kv: kv[1], reverse=True)[:20]
    top_platforms = sorted(by_platform.items(), key=lambda kv: kv[1], reverse=True)[:20]

    # Serialize
    payload_events = []
    for ev in events:
        d = asdict(ev)
        d["messages"] = [asdict(m) for m in ev.messages]
        payload_events.append(d)

    return {
        "meta": {"year": year, "seeds": len(seeds), "events": len(events), "merged_seeds": merged_seed_count},
        "stats": {
            "total_events": len(events),
            "by_status": by_status,
            "by_month": dict(sorted(by_month.items())),
            "top_contacts": [{"contact": k, "events": v} for k, v in top_contacts],
            "top_platforms": [{"platform": k, "events": v} for k, v in top_platforms],
        },
        "events": payload_events,
    }
