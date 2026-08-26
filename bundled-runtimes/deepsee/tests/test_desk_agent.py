from __future__ import annotations

import pytest

from app.services.desk_agent import DeskAgentClient, DeskAgentError


class _Response:
    def __init__(self, body):
        self.body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self.body


def test_client_submits_stateless_batch_and_polls(monkeypatch):
    posted = {}
    states = iter([
        {"status": "running"},
        {"status": "completed", "result": {"answer": '{"items": []}'}},
    ])

    def fake_post(url, **kwargs):
        posted.update({"url": url, **kwargs})
        return _Response({"id": "task-1"})

    monkeypatch.setattr("app.services.desk_agent.requests.post", fake_post)
    monkeypatch.setattr(
        "app.services.desk_agent.requests.get",
        lambda url, **kwargs: _Response(next(states)),
    )

    client = DeskAgentClient(
        "http://desk",
        module_id="deepsee-news",
        adapter="minimax-cli",
        model="MiniMax-M3",
        command_profile="batch",
    )
    answer = client.summarize(
        [{"id": "1", "content": "消息"}],
        [{"role": "system", "content": "返回 JSON"}],
        module_id="deepsee-wechat",
        capability="deepsee.wechat.batch-summarize",
    )

    assert answer == '{"items": []}'
    assert posted["url"] == "http://desk/api/agent/tasks"
    assert posted["json"]["profile"] == "batch"
    assert posted["json"]["memoryScope"] == "task"
    assert posted["json"]["moduleId"] == "deepsee-wechat"
    assert posted["json"]["capability"] == "deepsee.wechat.batch-summarize"
    assert posted["json"]["adapter"] == "minimax-cli"
    assert posted["json"]["model"] == "MiniMax-M3"
    assert posted["json"]["commandProfile"] == "batch"
    assert posted["json"]["input"] == {"itemIds": ["1"]}
    assert posted["json"]["context"]["operation"] == "message-summary"


def test_client_can_be_disabled_from_config():
    assert DeskAgentClient.from_config({"desk_agent": {"enabled": False}}) is None


def test_local_desk_agent_calls_bypass_system_proxy():
    local = DeskAgentClient("http://127.0.0.1:8911")
    remote = DeskAgentClient("https://desk.example.test")

    assert local._request_options() == {
        "proxies": {"http": None, "https": None, "socks": None}
    }
    assert remote._request_options() == {}


def test_client_surfaces_failed_task(monkeypatch):
    monkeypatch.setattr(
        "app.services.desk_agent.requests.post",
        lambda url, **kwargs: _Response({"id": "task-2"}),
    )
    monkeypatch.setattr(
        "app.services.desk_agent.requests.get",
        lambda url, **kwargs: _Response({"status": "failed", "error": "cli_unavailable"}),
    )

    with pytest.raises(DeskAgentError, match="cli_unavailable"):
        DeskAgentClient("http://desk").summarize([], [])


def test_client_cancels_gateway_task_after_timeout(monkeypatch):
    posted_urls = []

    def fake_post(url, **kwargs):
        posted_urls.append(url)
        if url.endswith("/cancel"):
            return _Response({"status": "cancelled"})
        return _Response({"id": "task-timeout"})

    times = iter([0.0, 11.0])
    monkeypatch.setattr("app.services.desk_agent.requests.post", fake_post)
    monkeypatch.setattr("app.services.desk_agent.time.monotonic", lambda: next(times))

    with pytest.raises(DeskAgentError, match="超时"):
        DeskAgentClient("http://desk", timeout_seconds=10).summarize([], [])

    assert posted_urls[-1] == "http://desk/api/agent/tasks/task-timeout/cancel"


def test_client_cancels_gateway_task_after_unexpected_poll_error(monkeypatch):
    posted_urls = []

    def fake_post(url, **kwargs):
        posted_urls.append(url)
        if url.endswith("/cancel"):
            return _Response({"status": "cancelled"})
        return _Response({"id": "task-error"})

    monkeypatch.setattr("app.services.desk_agent.requests.post", fake_post)

    def fake_get(url, **kwargs):
        raise ValueError("malformed gateway response")

    monkeypatch.setattr("app.services.desk_agent.requests.get", fake_get)

    with pytest.raises(ValueError, match="malformed gateway response"):
        DeskAgentClient("http://desk").summarize([], [])

    assert posted_urls[-1] == "http://desk/api/agent/tasks/task-error/cancel"
