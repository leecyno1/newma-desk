"""Tests for dashboard runner configuration."""

import asyncio
import json

import pytest
from starlette.requests import Request

import world_intel_mcp.dashboard.app as dashboard_app
from world_intel_mcp.dashboard.app import _cancel_tasks, _parse_run_args, api_static
from world_intel_mcp.sources import news


def test_parse_run_args_port() -> None:
    host, port = _parse_run_args(["--port", "8765"])

    assert host == "127.0.0.1"
    assert port == 8765


def test_parse_run_args_host_and_port() -> None:
    host, port = _parse_run_args(["--host", "0.0.0.0", "--port", "9000"])

    assert host == "0.0.0.0"
    assert port == 9000


def test_parse_run_args_env_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORLD_INTEL_DASHBOARD_HOST", "0.0.0.0")
    monkeypatch.setenv("WORLD_INTEL_DASHBOARD_PORT", "7777")

    host, port = _parse_run_args([])

    assert host == "0.0.0.0"
    assert port == 7777


async def test_cancel_tasks_reaps_pending_source_work() -> None:
    cancelled = asyncio.Event()

    async def source_work() -> None:
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    task = asyncio.create_task(source_work())
    await asyncio.sleep(0)

    await _cancel_tasks([task])

    assert task.cancelled()
    assert cancelled.is_set()


async def test_static_snapshot_is_timestamped_and_settled() -> None:
    response = await api_static(Request({"type": "http", "method": "GET", "path": "/api/static", "headers": []}))
    payload = json.loads(response.body)

    assert payload["_static"] is True
    assert payload["_complete"] is True
    assert payload["_done"] == payload["_total"] == 1
    assert payload["timestamp"].endswith("+00:00")


async def test_stream_replays_stale_completed_snapshot_before_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(dashboard_app, "_stream_snapshot", {
        "news_feed": {"items": [{"title": "Cached event"}], "count": 1},
    })
    monkeypatch.setattr(dashboard_app, "_stream_meta", {
        "timestamp": "2026-08-22T00:00:00+00:00",
    })
    monkeypatch.setattr(dashboard_app, "_stream_completed_at", 1.0)
    monkeypatch.setattr(dashboard_app, "_stream_total", 48)

    response = await dashboard_app.api_stream(
        Request({"type": "http", "method": "GET", "path": "/api/stream", "headers": []}),
    )
    first_chunk = await anext(response.body_iterator)
    payload = json.loads(first_chunk.removeprefix("data: ").strip())
    await response.body_iterator.aclose()

    assert payload["_cached"] is True
    assert payload["_stale"] is True
    assert payload["_complete"] is True
    assert payload["_done"] == payload["_total"] == 48
    assert payload["news_feed"]["count"] == 1


async def test_news_bundle_reuses_one_rss_batch(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    async def fake_fetch_news_feed(fetcher, category=None, limit=50):
        nonlocal calls
        calls += 1
        return {
            "items": [
                {"title": "Global risk rises"},
                {"title": "Global markets rise"},
                {"title": "Global policy shifts"},
            ],
            "count": 3,
            "source": "rss-aggregator",
        }

    monkeypatch.setattr(news, "fetch_news_feed", fake_fetch_news_feed)

    result = await news.fetch_news_bundle(object(), feed_limit=2, min_count=3)

    assert calls == 1
    assert result["news_feed"]["count"] == 2
    assert result["trending_keywords"]["keywords"] == [
        {"word": "global", "count": 3}
    ]
    assert result["media_monitor"]["summary"]["analyzed_items"] == 3
