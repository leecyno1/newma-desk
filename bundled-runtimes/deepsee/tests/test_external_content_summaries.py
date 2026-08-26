import json

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import SyncState
from app.services import external_content_summaries as service


def _session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'summaries.db'}", future=True)
    Base.metadata.create_all(engine, tables=[SyncState.__table__])
    return sessionmaker(bind=engine, future=True)()


def test_media_summaries_use_ten_item_cli_batches_and_cache(tmp_path, monkeypatch):
    db = _session(tmp_path)
    calls = []

    def fake_extract(messages, **kwargs):
        calls.append((messages, kwargs))
        return {
            **{
                item["id"]: {
                    "summary": f"ai: {item['id']} 摘要",
                    "summary_origin": "tool",
                    "tone": "neutral",
                    "keywords": [],
                }
                for item in messages
            },
            "__debug__": [],
        }

    monkeypatch.setattr(service, "extract_message_features", fake_extract)
    items = [
        {"id": str(index), "title": f"标题 {index}", "description": f"内容 {index}"}
        for index in range(25)
    ]

    first = service.summarize_external_items(db, "media", items)
    second = service.summarize_external_items(db, "media", items)

    assert len(calls) == 1
    assert calls[0][1]["batch_size"] == 10
    assert calls[0][1]["prompt_key"] == "media_content_summary"
    assert first["generated"] == 25
    assert second["generated"] == 0
    assert second["cached"] == 25
    assert all(item["summary"].startswith("ai:") for item in second["items"])


def test_mp_summaries_select_mp_prompt(tmp_path, monkeypatch):
    db = _session(tmp_path)
    captured = {}

    def fake_extract(messages, **kwargs):
        captured.update(kwargs)
        return {
            "a": {"summary": "ai: 文章摘要", "summary_origin": "tool"},
            "__debug__": [],
        }

    monkeypatch.setattr(service, "extract_message_features", fake_extract)
    result = service.summarize_external_items(
        db,
        "mp",
        [{"id": "a", "title": "文章", "content": "正文"}],
    )

    assert captured["batch_size"] == 10
    assert captured["prompt_key"] == "mp_content_summary"
    assert result["items"][0]["summary"] == "ai: 文章摘要"


def test_cached_tool_summary_keeps_original_source_fingerprint(tmp_path, monkeypatch):
    db = _session(tmp_path)
    calls = []

    def fake_extract(messages, **kwargs):
        calls.append(messages)
        return {
            "a": {"summary": "ai: 生成摘要", "summary_origin": "tool"},
            "__debug__": [],
        }

    monkeypatch.setattr(service, "extract_message_features", fake_extract)
    source = [{"id": "a", "title": "文章", "summary": "原始简介"}]
    service.summarize_external_items(db, "mp", source)
    overlaid = service.overlay_cached_summaries(db, "mp", source)
    second = service.summarize_external_items(db, "mp", overlaid)

    assert len(calls) == 1
    assert overlaid[0]["source_summary"] == "原始简介"
    assert second["generated"] == 0
    assert second["cached"] == 1


def test_cli_fallback_is_not_cached_as_success(tmp_path, monkeypatch):
    db = _session(tmp_path)
    calls = []

    def fake_extract(messages, **kwargs):
        calls.append(messages)
        return {
            "a": {"summary": "ai: 本地兜底", "summary_origin": "fallback"},
            "__errors__": ["cli failed"],
            "__debug__": [],
        }

    monkeypatch.setattr(service, "extract_message_features", fake_extract)
    item = [{"id": "a", "title": "文章", "content": "正文"}]
    first = service.summarize_external_items(db, "mp", item)
    second = service.summarize_external_items(db, "mp", item)

    assert len(calls) == 2
    assert first["generated"] == 0
    assert first["failed"] == 1
    assert second["generated"] == 0


def test_legacy_fallback_cache_is_retried(tmp_path, monkeypatch):
    db = _session(tmp_path)
    calls = []

    def fake_extract(messages, **kwargs):
        calls.append(messages)
        return {
            "a": {"summary": "ai: 重试成功", "summary_origin": "tool"},
            "__debug__": [],
        }

    monkeypatch.setattr(service, "extract_message_features", fake_extract)
    item = [{"id": "a", "title": "文章", "content": "正文"}]
    service._save_cache(
        db,
        "mp",
        {
            "a": {
                "fingerprint": service._fingerprint(service._source_text("mp", item[0])),
                "summary": "ai: 旧兜底",
                "origin": "fallback",
                "updated_at": "old",
            }
        },
    )

    result = service.summarize_external_items(db, "mp", item)

    assert len(calls) == 1
    assert result["generated"] == 1
    assert result["items"][0]["summary"] == "ai: 重试成功"
