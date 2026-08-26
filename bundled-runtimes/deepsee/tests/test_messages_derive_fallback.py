import json
import os
import sys
from datetime import datetime, timedelta

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.schemas import MessageDeriveRequest


class _FakeMessage:
    def __init__(self, msg_id: int, content: str):
        self.id = msg_id
        self.timestamp = datetime.utcnow() - timedelta(hours=1)
        self.content_text = content
        self.type = "1"
        self.derived = None


class _ScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _ExecuteResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return list(self._rows)


class _FakeDB:
    def __init__(self, messages):
        self._messages = messages
        self._calls = 0

    def execute(self, _query):
        self._calls += 1
        if self._calls == 1:
            return _ScalarResult(self._messages)
        return _ExecuteResult([(m.id, m.derived) for m in self._messages])

    def add(self, _obj):
        return None

    def commit(self):
        return None

    def rollback(self):
        return None


class _IdsOnlyDb:
    def __init__(self, ids):
        self._ids = ids

    def execute(self, _query):
        return _ExecuteResult([(x,) for x in self._ids])


class _DeriveFlowDb:
    def __init__(self, messages):
        self._messages = messages
        self._calls = 0

    def execute(self, _query):
        self._calls += 1
        if self._calls == 1:
            return _ExecuteResult([(m.id,) for m in self._messages])
        if self._calls == 2:
            return _ScalarResult(self._messages)
        return _ExecuteResult([(m.id, m.derived) for m in self._messages])

    def add(self, _obj):
        return None

    def commit(self):
        return None

    def rollback(self):
        return None


def test_messages_derive_prefills_fallback_before_tool_overlay(monkeypatch):
    from app.routers import messages as messages_router

    msg = _FakeMessage(101, "这是一个足够长的微信消息正文，用于验证在小模型没有产出时，仍然会先写入 fallback 摘要。")
    db = _DeriveFlowDb([msg])
    called = {"fallback": 0, "ensure": 0}

    def _fake_load_ai_config():
        return {"derive_defaults": {"batch_size": 20, "concurrency": 2, "temperature": 0.1, "force": False}}

    def _fake_populate_fallback(db_obj, rows, force=False, **kwargs):
        called["fallback"] += 1
        assert db_obj is db
        assert rows == [msg]
        # 手动指定 message_ids 只限定增量范围，不再隐式强制覆盖 tool 缓存。
        assert force is False
        msg.derived = {"summary": "fallback: 这是一个兜底摘要", "summary_origin": "fallback"}
        return 1

    def _fake_ensure(db_obj, rows, **kwargs):
        called["ensure"] += 1
        assert db_obj is db
        assert rows == [msg]
        assert msg.derived["summary_origin"] == "fallback"
        return {"updated": 0, "errors": [], "debug": [], "applied": []}

    monkeypatch.setattr(messages_router, "load_ai_config", _fake_load_ai_config)
    monkeypatch.setattr(messages_router, "populate_fallback_derived", _fake_populate_fallback, raising=False)
    monkeypatch.setattr(messages_router, "ensure_message_features", _fake_ensure)

    body = MessageDeriveRequest(message_ids=[101])
    result = messages_router.derive_message_features(body=body, progress_key=None, db=db)

    assert result["status"] == "ok"
    assert called == {"fallback": 1, "ensure": 1}
    assert result["debug_readback"][0]["summary_origin"] == "fallback"


def test_ensure_message_features_keeps_tool_origin_after_overlay(monkeypatch):
    from app.services import ai_tools

    msg = _FakeMessage(202, "这是一个长度超过二十字的微信观点消息，包含会议号和明确观点。")
    msg.derived = {"summary": "fallback: 原兜底摘要", "summary_origin": "fallback"}
    db = _FakeDB([msg])

    monkeypatch.setattr(ai_tools, "load_ai_config", lambda: {"tool_model_messages": "tool-x"})
    monkeypatch.setattr(
        ai_tools,
        "extract_message_features",
        lambda *args, **kwargs: {
            "202": {
                "summary": "ai: 推荐关注半导体，会议号491436856",
                "meeting_number": "491436856",
                "tone": "neutral",
                "confidence": 0.82,
                "category": "观点",
                "keywords": ["半导体"],
            }
        },
    )

    out = ai_tools.ensure_message_features(db, [msg], force=False, batch_size=10, concurrency=1, temperature=0.1)
    assert out["updated"] == 1
    assert msg.derived["summary"].startswith("ai:")
    assert msg.derived["summary_origin"] == "tool"


def test_ensure_message_features_skips_text_under_twenty_chars(monkeypatch):
    from app.services import ai_tools

    msg = _FakeMessage(303, "请问老师这个医疗金投保人可以使用吗")
    db = _FakeDB([msg])

    monkeypatch.setattr(ai_tools, "load_ai_config", lambda: {"tool_model_messages": "tool-x"})

    def _fake_extract(messages, **kwargs):
        raise AssertionError("short messages must not be sent to the tool model")

    monkeypatch.setattr(ai_tools, "extract_message_features", _fake_extract)
    out = ai_tools.ensure_message_features(db, [msg], force=False, batch_size=10, concurrency=1, temperature=0.1)
    assert out["updated"] == 0
    assert msg.derived is None


def test_populate_fallback_derived_skips_text_under_twenty_chars():
    from app.services import ai_tools

    msg = _FakeMessage(304, "短消息不摘要")
    db = _FakeDB([msg])

    changed = ai_tools.populate_fallback_derived(db, [msg], force=False)

    assert changed == 0
    assert msg.derived is None


def test_tool_summary_stores_clean_body_without_duplicate_meeting_prefix(monkeypatch):
    from app.services import ai_tools

    msg = _FakeMessage(305, "这是一个长度超过二十字的腾讯会议消息，会议号491436856，需要提炼重点观点。")
    db = _FakeDB([msg])

    monkeypatch.setattr(ai_tools, "load_ai_config", lambda: {"tool_model_messages": "tool-x"})
    monkeypatch.setattr(
        ai_tools,
        "extract_message_features",
        lambda *args, **kwargs: {
            "305": {
                "summary": "ai: 腾讯 491436856 关注订单改善",
                "meeting_number": "491436856",
                "platform": "腾讯",
                "tone": "neutral",
                "confidence": 0.82,
            }
        },
    )

    out = ai_tools.ensure_message_features(db, [msg], force=False, batch_size=10, concurrency=1, temperature=0.1)

    assert out["updated"] == 1
    assert msg.derived["meeting_number"] == "491436856"
    assert msg.derived["platform"] == "腾讯"
    assert msg.derived["summary"] == "ai: 关注订单改善"


def test_extract_message_features_falls_back_to_single_item_retry(monkeypatch):
    from app.services import ai_tools

    calls = {"n": 0}
    monkeypatch.setattr(ai_tools, "load_ai_config", lambda: {"tool_prompts": {}, "tool_model_messages": "tool-x"})

    def _fake_chat(_prompt, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return '{"id":"1","summary":"第一条"}{"id":"2","summary":"第二条"}'
        if calls["n"] == 2:
            return '{"id":"1","summary":"第一条"}'
        return '{"id":"2","summary":"第二条"}'

    monkeypatch.setattr(ai_tools, "siliconflow_tool_chat", _fake_chat)
    out = ai_tools.extract_message_features(
        [
            {"id": "1", "content": "第一条足够长的消息内容用于提取摘要。"},
            {"id": "2", "content": "第二条足够长的消息内容用于提取摘要。"},
        ],
        batch_size=6,
        concurrency=1,
        temperature=0.1,
    )
    assert out["1"]["summary"].startswith("ai:")
    assert out["2"]["summary"].startswith("ai:")
    assert calls["n"] == 1


def test_cli_summarizes_fifty_messages_in_one_task(monkeypatch):
    from app.services import ai_tools

    calls = []

    class _FakeDeskAgent:
        def summarize(self, messages, prompt, **kwargs):
            calls.append({"messages": messages, "prompt": prompt, **kwargs})
            return json.dumps(
                [{"id": item["id"], "summary": f"摘要 {item['id']}"} for item in messages],
                ensure_ascii=False,
            )

    fake_agent = _FakeDeskAgent()
    monkeypatch.setattr(ai_tools, "load_ai_config", lambda: {"tool_prompts": {}})
    monkeypatch.setattr(
        ai_tools.DeskAgentClient,
        "from_config",
        classmethod(lambda cls, config: fake_agent),
    )
    monkeypatch.setattr(
        ai_tools,
        "siliconflow_tool_chat",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("不应调用兼容模型")),
    )

    messages = [
        {"id": str(index), "content": f"第 {index} 条聊天记录，包含足够的信息用于摘要。"}
        for index in range(1, 51)
    ]
    out = ai_tools.extract_message_features(messages, batch_size=50, concurrency=3)

    assert len(calls) == 1
    assert len(calls[0]["messages"]) == 50
    assert calls[0]["module_id"] == "deepsee-wechat"
    assert calls[0]["capability"] == "deepsee.wechat.batch-summarize"
    assert calls[0]["operation"] == "message-summary"
    assert all(out[str(index)]["summary"].startswith("ai:") for index in range(1, 51))
    assert all(item["source"] == "desk-agent" for item in out["__debug__"])


def test_wechat_cli_summarizes_one_hundred_messages_in_one_task(monkeypatch):
    from app.services import ai_tools

    calls = []

    class _FakeDeskAgent:
        def summarize(self, messages, prompt, **kwargs):
            calls.append({"messages": messages, **kwargs})
            return json.dumps(
                [{"id": item["id"], "summary": f"摘要 {item['id']}"} for item in messages],
                ensure_ascii=False,
            )

    fake_agent = _FakeDeskAgent()
    monkeypatch.setattr(ai_tools, "load_ai_config", lambda: {"tool_prompts": {}})
    monkeypatch.setattr(
        ai_tools.DeskAgentClient,
        "from_config",
        classmethod(lambda cls, config: fake_agent),
    )
    messages = [
        {"id": str(index), "content": f"第 {index} 条微信记录，包含足够信息用于摘要。"}
        for index in range(1, 101)
    ]

    out = ai_tools.extract_message_features(messages, batch_size=100, concurrency=3)

    assert len(calls) == 1
    assert len(calls[0]["messages"]) == 100
    assert calls[0]["module_id"] == "deepsee-wechat"
    assert calls[0]["capability"] == "deepsee.wechat.batch-summarize"
    assert len([key for key in out if not key.startswith("__")]) == 100


def test_cli_summary_kinds_use_their_own_declared_agent_capabilities(monkeypatch):
    from app.services import ai_tools

    calls = []

    class _FakeDeskAgent:
        def summarize(self, messages, prompt, **kwargs):
            calls.append(kwargs)
            return json.dumps(
                [{"id": item["id"], "summary": "摘要"} for item in messages],
                ensure_ascii=False,
            )

    monkeypatch.setattr(ai_tools, "load_ai_config", lambda: {"tool_prompts": {}})
    monkeypatch.setattr(
        ai_tools.DeskAgentClient,
        "from_config",
        classmethod(lambda cls, config: _FakeDeskAgent()),
    )

    expected = {
        "email_message_summary": ("deepsee-email", "deepsee.email.batch-summarize"),
        "minutes_summary": ("deepsee-minutes", "deepsee.minutes.batch-summarize"),
        "minutes_refine": ("deepsee-minutes", "deepsee.minutes.batch-refine"),
        "media_content_summary": ("deepsee-media", "deepsee.media.batch-summarize"),
        "mp_content_summary": (
            "deepsee-official-accounts",
            "deepsee.official-accounts.batch-summarize",
        ),
    }
    for prompt_key in expected:
        ai_tools.extract_message_features(
            [{"id": prompt_key, "content": "这是一条足够长的待摘要内容。"}],
            batch_size=1,
            concurrency=1,
            prompt_key=prompt_key,
        )

    assert [
        (call["module_id"], call["capability"])
        for call in calls
    ] == list(expected.values())


def test_minutes_refine_cli_prompt_requires_batch_json_array(monkeypatch):
    from app.services import ai_tools

    calls = []

    class _FakeDeskAgent:
        def summarize(self, messages, prompt, **kwargs):
            calls.append(prompt)
            return json.dumps(
                [
                    {"id": item["id"], "summary": "ai: ok", "refined": "整理结果"}
                    for item in messages
                ],
                ensure_ascii=False,
            )

    monkeypatch.setattr(
        ai_tools,
        "load_ai_config",
        lambda: {
            "tool_prompts": {
                "minutes_refine": {
                    "system": "旧配置：输出单个 JSON 对象。",
                    "user": "旧配置：只处理单条。数据：{{messages_json}}",
                }
            }
        },
    )
    monkeypatch.setattr(
        ai_tools.DeskAgentClient,
        "from_config",
        classmethod(lambda cls, config: _FakeDeskAgent()),
    )

    out = ai_tools.extract_message_features(
        [
            {"id": "m1", "content": "第一条会议逐字稿，包含足够内容。"},
            {"id": "m2", "content": "第二条会议逐字稿，包含足够内容。"},
        ],
        batch_size=50,
        concurrency=1,
        prompt_key="minutes_refine",
    )

    assert len(calls) == 1
    prompt_text = "\n".join(item["content"] for item in calls[0])
    assert "必须返回 2 个结果" in prompt_text
    assert "必须返回单元素 JSON 数组" in prompt_text
    assert out["m1"]["refined"] == "整理结果"
    assert out["m2"]["refined"] == "整理结果"


def test_cli_missing_item_uses_local_fallback_without_retry(monkeypatch):
    from app.services import ai_tools

    calls = {"count": 0}

    class _FakeDeskAgent:
        def summarize(self, messages, prompt, **kwargs):
            calls["count"] += 1
            return json.dumps(
                [{"id": item["id"], "summary": f"摘要 {item['id']}"} for item in messages[:-1]],
                ensure_ascii=False,
            )

    fake_agent = _FakeDeskAgent()
    monkeypatch.setattr(ai_tools, "load_ai_config", lambda: {"tool_prompts": {}})
    monkeypatch.setattr(
        ai_tools.DeskAgentClient,
        "from_config",
        classmethod(lambda cls, config: fake_agent),
    )

    messages = [
        {"id": str(index), "content": f"第 {index} 条聊天记录，包含待提取的关键信息。"}
        for index in range(1, 51)
    ]
    out = ai_tools.extract_message_features(messages, batch_size=50, concurrency=1)

    assert calls["count"] == 1
    assert out["50"]["summary_origin"] == "fallback"
    assert out["50"]["summary"].startswith("ai:")
    assert any(item["id"] == "50" and item["local_fallback"] for item in out["__debug__"])


def test_extract_message_features_parses_concatenated_json_objects_without_retry(monkeypatch):
    from app.services import ai_tools

    calls = {"n": 0}
    monkeypatch.setattr(ai_tools, "load_ai_config", lambda: {"tool_prompts": {}, "tool_model_messages": "tool-x"})

    def _fake_chat(_prompt, **kwargs):
        calls["n"] += 1
        return '{"id":"1","summary":"第一条"}{"id":"2","summary":"第二条"}'

    monkeypatch.setattr(ai_tools, "siliconflow_tool_chat", _fake_chat)
    out = ai_tools.extract_message_features(
        [
            {"id": "1", "content": "第一条足够长的消息内容用于提取摘要。"},
            {"id": "2", "content": "第二条足够长的消息内容用于提取摘要。"},
        ],
        batch_size=6,
        concurrency=1,
        temperature=0.1,
    )
    assert calls["n"] == 1
    assert out["1"]["summary"].startswith("ai:")
    assert out["2"]["summary"].startswith("ai:")


def test_extract_message_features_keeps_key_points_and_comment(monkeypatch):
    from app.services import ai_tools

    monkeypatch.setattr(ai_tools, "load_ai_config", lambda: {"tool_prompts": {}, "tool_model_messages": "tool-x"})
    monkeypatch.setattr(
        ai_tools,
        "siliconflow_tool_chat",
        lambda *_args, **_kwargs: (
            '[{"id":"1","summary":"ai: 关注订单改善","key_points":["订单环比改善","毛利率仍承压"],"comment":"短期有催化，但需观察利润兑现。","tone":"bullish","confidence":0.8}]'
        ),
    )

    out = ai_tools.extract_message_features(
        [{"id": "1", "content": "公司订单环比改善，但毛利率仍承压，需要继续跟踪利润兑现。"}],
        batch_size=1,
        concurrency=1,
    )

    assert out["1"]["key_points"] == ["订单环比改善", "毛利率仍承压"]
    assert out["1"]["comment"] == "短期有催化，但需观察利润兑现。"


def test_ensure_message_features_persists_key_points_and_comment(monkeypatch):
    from app.services import ai_tools

    msg = _FakeMessage(404, "这是一个长度超过二十字的微信观点消息，包含订单改善和利润承压。")
    db = _FakeDB([msg])

    monkeypatch.setattr(ai_tools, "load_ai_config", lambda: {"tool_model_messages": "tool-x"})
    monkeypatch.setattr(
        ai_tools,
        "extract_message_features",
        lambda *args, **kwargs: {
            "404": {
                "summary": "ai: 订单改善但利润承压",
                "meeting_number": "",
                "tone": "neutral",
                "confidence": 0.7,
                "category": "观点",
                "keywords": ["订单"],
                "key_points": ["订单改善", "利润承压"],
                "comment": "需要跟踪后续利润兑现。",
            }
        },
    )

    out = ai_tools.ensure_message_features(db, [msg], force=False, batch_size=10, concurrency=1, temperature=0.1)

    assert out["updated"] == 1
    assert msg.derived["summary_origin"] == "tool"
    assert msg.derived["key_points"] == ["订单改善", "利润承压"]
    assert msg.derived["comment"] == "需要跟踪后续利润兑现。"


def test_background_derive_job_does_not_force_message_ids(monkeypatch):
    from app.routers import messages as messages_router

    msg = _FakeMessage(505, "这是一条已经有工具摘要的微信消息，用于验证后台任务不会因为指定ID而强制覆盖。")
    msg.derived = {"summary": "ai: 已有工具摘要", "summary_origin": "tool"}
    db = _FakeDB([msg])
    db.close = lambda: None
    captured = {}

    monkeypatch.setattr(messages_router, "SessionLocal", lambda: db)
    monkeypatch.setattr(messages_router, "_set_progress", lambda *args, **kwargs: None)
    monkeypatch.setattr(messages_router, "_PROGRESS_LOCK", type("L", (), {"__enter__": lambda self: self, "__exit__": lambda self, *a: None})())
    messages_router._DERIVE_JOBS.clear()

    def _fake_internal(db_obj, rows, body, *, effective_force, progress_key=None):
        captured["effective_force"] = effective_force
        captured["ids"] = [m.id for m in rows]
        return {"status": "ok", "updated": 0}

    monkeypatch.setattr(messages_router, "_derive_messages_internal", _fake_internal)
    messages_router._run_derive_job("job-505", {"message_ids": [505], "force": False}, [505])

    assert captured == {"effective_force": False, "ids": [505]}


def test_messages_derive_with_progress_key_queues_background_job(monkeypatch):
    from app.routers import messages as messages_router

    started = {}

    class _DummyThread:
        def __init__(self, target=None, args=None, daemon=None, name=None):
            self.target = target
            self.args = args
            self.daemon = daemon
            self.name = name

        def is_alive(self):
            return False

        def start(self):
            started["target"] = self.target
            started["args"] = self.args
            started["name"] = self.name

    monkeypatch.setattr(messages_router.threading, "Thread", _DummyThread)
    messages_router.PROGRESS.clear()

    body = MessageDeriveRequest(message_ids=[101], force=True)
    result = messages_router.derive_message_features(body=body, progress_key="queued-1", db=_IdsOnlyDb([101]))

    assert result["status"] == "queued"
    assert result["progress_key"] == "queued-1"
    assert result["total"] == 1
    assert callable(started["target"])
    assert started["args"][0] == "queued-1"
    assert messages_router.PROGRESS["queued-1"]["status"] == "queued"
