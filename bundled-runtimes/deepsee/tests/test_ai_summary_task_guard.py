import json
import os
import sys
import tempfile
from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.db import Base
from app.models import Report, Task
from app.routers import ai as ai_router


class _BusyLock:
    def acquire(self, blocking: bool = True):
        return False

    def release(self):
        return None


def _make_session():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_engine(f"sqlite:///{path}", future=True)
    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    Base.metadata.create_all(engine, tables=[Task.__table__, Report.__table__])
    return path, TestingSession


def test_mark_stale_summary_tasks_marks_old_pending():
    path, TestingSession = _make_session()
    try:
        with TestingSession() as db:
            row = Task(
                type="summary",
                payload={"request_id": "x"},
                status="pending",
                created_at=datetime.utcnow() - timedelta(hours=2),
                updated_at=datetime.utcnow() - timedelta(hours=2),
            )
            db.add(row)
            db.commit()
            db.refresh(row)

            stale_ids = ai_router._mark_stale_summary_tasks(db, timeout_seconds=60)
            db.refresh(row)

            assert stale_ids == [row.id]
            assert row.status == "failed"
            assert row.result["error"] == "stale_summary_task_timeout"
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def test_summary_returns_cached_report_when_another_run_is_active(monkeypatch):
    path, TestingSession = _make_session()
    old_lock = ai_router.SUMMARY_RUN_LOCK
    try:
        with TestingSession() as db:
            active = Task(
                type="summary",
                payload={"request_id": "running"},
                status="pending",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            report_payload = {
                "market_markdown": "# 市场观点总结\n- 旧结果保留",
                "meetings_markdown": "",
                "counter_markdown": "",
                "top_contacts_markdown": "",
                "newswatch_markdown": "",
                "socialwatch_markdown": "",
                "mediawatch_markdown": "",
                "mpwatch_markdown": "",
                "minuteswatch_markdown": "",
            }
            rep = Report(
                title="AI 报告",
                time_range="2026-04-12",
                filters={"period": "1day"},
                status="done",
                result_type="json",
                result_body=json.dumps(report_payload, ensure_ascii=False),
            )
            db.add(active)
            db.add(rep)
            db.commit()
            db.refresh(active)

            monkeypatch.setattr(ai_router, "SUMMARY_RUN_LOCK", _BusyLock())
            out = ai_router.summary(
                {
                    "filters": {"period": "1day"},
                    "modules": ["market", "newswatch"],
                    "options": {"modules": ["market", "newswatch"], "temperature": 0.3},
                },
                db=db,
            )

            assert out.status == "pending"
            assert out.id == active.id
            assert out.result["meta"]["busy"] is True
            assert out.result["report"]["market_markdown"].startswith("# 市场观点总结")
    finally:
        ai_router.SUMMARY_RUN_LOCK = old_lock
        try:
            os.remove(path)
        except OSError:
            pass
