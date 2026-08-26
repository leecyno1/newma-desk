import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.routers import agent_api


def test_invoke_batch_counts_success_and_failure(monkeypatch):
    calls = []

    def _fake_invoke_single(payload, request):  # noqa: ARG001
        calls.append(payload.path)
        if payload.path.endswith("ok"):
            return 200, {"ok": True, "path": payload.path}
        return 500, {"ok": False, "path": payload.path}

    monkeypatch.setattr(agent_api, "_invoke_single", _fake_invoke_single)

    payload = agent_api.AgentBatchInvokeIn(
        requests=[
            agent_api.AgentInvokeIn(method="GET", path="/api/mock-ok"),
            agent_api.AgentInvokeIn(method="GET", path="/api/mock-fail"),
        ],
        stop_on_error=False,
        max_workers=2,
    )
    out = agent_api.agent_invoke_batch(payload=payload, request=object())

    assert out["total"] == 2
    assert out["executed"] == 2
    assert out["success"] == 1
    assert out["failed"] == 1
    assert out["ok"] is False
    assert calls == ["/api/mock-ok", "/api/mock-fail"]


def test_invoke_batch_stop_on_error(monkeypatch):
    calls = []

    def _fake_invoke_single(payload, request):  # noqa: ARG001
        calls.append(payload.path)
        if payload.path.endswith("fail"):
            return 500, {"ok": False, "path": payload.path}
        return 200, {"ok": True, "path": payload.path}

    monkeypatch.setattr(agent_api, "_invoke_single", _fake_invoke_single)

    payload = agent_api.AgentBatchInvokeIn(
        requests=[
            agent_api.AgentInvokeIn(method="GET", path="/api/mock-fail"),
            agent_api.AgentInvokeIn(method="GET", path="/api/mock-ok"),
        ],
        stop_on_error=True,
        max_workers=4,
    )
    out = agent_api.agent_invoke_batch(payload=payload, request=object())

    assert out["total"] == 2
    assert out["executed"] == 1
    assert out["success"] == 0
    assert out["failed"] == 1
    assert out["ok"] is False
    assert calls == ["/api/mock-fail"]


def test_invoke_batch_passes_max_workers_to_executor(monkeypatch):
    calls = []
    workers_seen = []

    def _fake_invoke_single(payload, request):  # noqa: ARG001
        calls.append(payload.path)
        return 200, {"ok": True}

    class _FakeFuture:
        def __init__(self, value):
            self._value = value

        def result(self):
            return self._value

    class _FakeExecutor:
        def __init__(self, max_workers):
            workers_seen.append(max_workers)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def submit(self, fn, req, request):
            return _FakeFuture(fn(req, request))

    monkeypatch.setattr(agent_api, "_invoke_single", _fake_invoke_single)
    monkeypatch.setattr(agent_api, "ThreadPoolExecutor", _FakeExecutor)
    monkeypatch.setattr(agent_api, "as_completed", lambda futures: list(futures))

    payload = agent_api.AgentBatchInvokeIn(
        requests=[
            agent_api.AgentInvokeIn(method="GET", path="/api/a"),
            agent_api.AgentInvokeIn(method="GET", path="/api/b"),
            agent_api.AgentInvokeIn(method="GET", path="/api/c"),
        ],
        stop_on_error=False,
        max_workers=2,
    )
    out = agent_api.agent_invoke_batch(payload=payload, request=object())

    assert out["ok"] is True
    assert out["executed"] == 3
    assert workers_seen == [2]
    assert calls == ["/api/a", "/api/b", "/api/c"]
