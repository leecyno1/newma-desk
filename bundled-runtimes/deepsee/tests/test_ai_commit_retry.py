import os
import sys

import pytest
from sqlalchemy.exc import OperationalError

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.routers import ai as ai_router


class _FakeSession:
    def __init__(self, fail_times: int, *, lock_error: bool = True) -> None:
        self.fail_times = fail_times
        self.lock_error = lock_error
        self.commit_calls = 0
        self.rollback_calls = 0
        self.add_calls = 0

    def commit(self):
        self.commit_calls += 1
        if self.fail_times > 0:
            self.fail_times -= 1
            msg = "database is locked" if self.lock_error else "constraint failed"
            raise OperationalError("INSERT ...", {}, Exception(msg))

    def rollback(self):
        self.rollback_calls += 1

    def add(self, _obj):
        self.add_calls += 1


def test_commit_with_retry_recovers_from_locked(monkeypatch):
    monkeypatch.setattr(ai_router.time, "sleep", lambda *_: None)
    db = _FakeSession(3, lock_error=True)
    marker = object()

    ai_router._commit_with_retry(db, retries=5, base_delay=0.01, objects=[marker])

    assert db.commit_calls == 4
    assert db.rollback_calls == 3
    assert db.add_calls == 3


def test_commit_with_retry_raises_non_lock_error(monkeypatch):
    monkeypatch.setattr(ai_router.time, "sleep", lambda *_: None)
    db = _FakeSession(1, lock_error=False)

    with pytest.raises(OperationalError):
        ai_router._commit_with_retry(db, retries=5, base_delay=0.01, objects=[object()])

    assert db.commit_calls == 1
    assert db.rollback_calls == 1
