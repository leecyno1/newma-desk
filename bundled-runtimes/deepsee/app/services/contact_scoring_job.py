"""One background refresh for the imported six-month history and current messages."""
from __future__ import annotations

import calendar
import json
import threading
from datetime import datetime

from sqlalchemy import select

from ..db import SessionLocal
from ..models import Contact, Message, SyncState, ContactPredictionEvent
from .contact_scoring import (EXTRACTOR_VERSION, extract_prediction_events_to_db, evaluate_prediction_events_to_db,
                              recompute_contact_scores)
from .market_data import refresh_stock_name_directory

_lock = threading.Lock()
_state = {"status": "idle", "phase": "尚未开始"}
STATE_KEY = "contact_scoring_refresh_v3"


def scoring_job_status():
    if _state["status"] == "running":
        return dict(_state)
    with SessionLocal() as db:
        saved = db.get(SyncState, STATE_KEY)
        result = json.loads(saved.value) if saved and saved.value else dict(_state)
    if result.get("status") == "running":
        result.update(status="interrupted", phase="服务重启，点击刷新可继续；已保存的阶段不会丢失")
    return result


def _update(**values):
    _state.update(values)
    with SessionLocal() as db:
        row = db.get(SyncState, STATE_KEY) or SyncState(key=STATE_KEY)
        row.value = json.dumps(_state, ensure_ascii=False)
        db.add(row)
        db.commit()


def _run():
    try:
        as_of = datetime.now()
        month_index = as_of.year * 12 + as_of.month - 1 - 6
        year, month = divmod(month_index, 12)
        start = as_of.replace(year=year, month=month + 1,
                              day=min(as_of.day, calendar.monthrange(year, month + 1)[1]),
                              hour=0, minute=0, second=0, microsecond=0)
        _update(phase="更新证券名称表", started_at=as_of.isoformat(), time_from=start.isoformat())
        try:
            names = refresh_stock_name_directory()
            _update(security_names=names)
        except Exception:
            _update(directory_warning="名称表更新失败，使用本地缓存；不影响已识别代码的行情验证")
        with SessionLocal() as db:
            ids = set(db.execute(select(Message.sender_id).join(Contact, Contact.id == Message.sender_id)
                .where(Message.timestamp >= start, Message.timestamp <= as_of,
                       Message.sender_id.not_like("gh_%"),
                       (Message.direction.is_(None) | (Message.direction != "out")))
                .distinct()).scalars())
            if not ids:
                _update(status="complete", phase="没有可评分的历史联系人", contacts=0)
                return
            _update(phase="抽取半年历史观点", contacts=len(ids))
            needs_upgrade = db.execute(select(ContactPredictionEvent.id).where(
                ContactPredictionEvent.contact_id.in_(ids),
                (ContactPredictionEvent.extractor_version.is_(None) | (ContactPredictionEvent.extractor_version != EXTRACTOR_VERSION))
            ).limit(1)).first() is not None
            extracted = extract_prediction_events_to_db(db, contact_ids=ids, time_from=start, time_to=as_of, force=needs_upgrade)
            _update(phase="获取真实行情并验证到期观点", extract=extracted)
            evaluated = evaluate_prediction_events_to_db(db, contact_ids=ids, as_of=as_of, progress=_update, direct_history=True)
            _update(phase="更新联系人的实证评分", evaluate=evaluated)
            recomputed = recompute_contact_scores(db, contact_ids=ids, as_of=as_of)
            _update(status="complete", phase="更新完成", recompute=recomputed, finished_at=datetime.now().isoformat())
    except Exception as exc:
        # Do not expose provider URLs or tokens in the public job status.
        _update(status="failed", phase="刷新失败，可重试", error=type(exc).__name__)
    finally:
        _lock.release()


def start_scoring_job():
    if not _lock.acquire(blocking=False):
        return scoring_job_status()
    _state.clear()
    _state.update(status="running", phase="准备历史重算")
    threading.Thread(target=_run, name="contact-scoring-refresh", daemon=True).start()
    return dict(_state)
