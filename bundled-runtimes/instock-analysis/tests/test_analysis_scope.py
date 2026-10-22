"""Ownership tests use synthetic research only; no live market/model requests."""

import asyncio
from contextlib import contextmanager
import json
import os
import sqlite3
from unittest.mock import patch

import pytest
import tornado.web
from tornado.httpclient import HTTPClientError
from tornado.testing import AsyncHTTPTestCase, gen_test

from instock.core.analysis_scope import analysis_scope, desk_scope
from instock.core.analysis_snapshot import AnalysisSnapshotRegistry, get_analysis_snapshot_registry
from instock.core.analysis_history import AnalysisHistoryRegistry
from instock.core.research.research_book import ResearchBookEngine
from instock.web.analysis_scope import resolve_request_scope, AnalysisScopeError
from instock.web.api_contract import AnalysisApiHandler
from instock.web.result_cache import AsyncTaskCoalescer, BoundedTTLCache
from test_research_book import _packet, _register_fixture_snapshot


@contextmanager
def workspace(user, name):
    token = analysis_scope.set(desk_scope(user, name))
    try:
        yield
    finally:
        analysis_scope.reset(token)


@pytest.mark.parametrize("persistent", [False, True])
def test_history_and_identical_snapshot_ids_are_isolated(tmp_path, persistent):
    history = AnalysisHistoryRegistry(db_path=str(tmp_path / 'history.db') if persistent else None)
    snapshots = AnalysisSnapshotRegistry()
    value = {"schema_version": "1.0", "snapshot_id": "same:id", "private": "first workspace"}
    with workspace("alice", "a"):
        snapshots.register(value)
        record = history.register(module_id="industry-chain", title="私有研究", payload=value)
    for user, name in [("alice", "b"), ("bob", "a")]:
        with workspace(user, name):
            assert snapshots.get("same:id") is None
            assert history.get(record["history_id"]) is None
            assert history.list("industry-chain") == []
            assert history.stats()["entries"] == snapshots.stats()["entries"] == 0
            snapshots.register({**value, "private": name})
    with workspace("alice", "a"):
        assert snapshots.get("same:id")["private"] == "first workspace"
        assert history.get(record["history_id"])["payload"] == value
        if persistent:
            assert AnalysisHistoryRegistry(db_path=str(tmp_path / 'history.db')).get(record["history_id"])
    assert snapshots.get("same:id") is None  # unsigned standalone is a separate scope
    assert history.get(record["history_id"]) is None


def test_old_sqlite_records_are_preserved_but_not_claimed_or_purged(tmp_path):
    path = str(tmp_path / "legacy.db")
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE analysis_history(history_id TEXT PRIMARY KEY,module_id TEXT NOT NULL,stored_at REAL NOT NULL,entry_json TEXT NOT NULL)")
        db.execute("INSERT INTO analysis_history VALUES ('old','research-book',0,?)", ('{"private":"original"}',))
    history = AnalysisHistoryRegistry(db_path=path, max_entries=1)
    for scope in ("standalone:local", desk_scope("alice", "a")):
        token = analysis_scope.set(scope)
        try:
            assert history.get("old") is None
            assert history.list("research-book") == []
            history.register(module_id="research-book", title="new", payload={})
            assert history.stats()["entries"] == 1
        finally:
            analysis_scope.reset(token)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT entry_json,scope FROM analysis_history WHERE history_id='old'").fetchone() == ('{"private":"original"}', None)


def test_research_book_references_resolve_only_in_the_same_workspace():
    registry = get_analysis_snapshot_registry()
    with workspace("alice", "a"):
        _register_fixture_snapshot()
        result = ResearchBookEngine().analyze(_packet())
        assert result["summary"]["resolved_snapshots"] == 1
        assert registry.get(result["snapshot"]["snapshot_id"])
    with workspace("alice", "b"):
        other = ResearchBookEngine().analyze(_packet())
        assert other["summary"]["resolved_snapshots"] == 0
        assert registry.get(result["snapshot"]["snapshot_id"]) is None


def test_concurrent_cache_and_inflight_scope_follow_worker_threads():
    cache = BoundedTTLCache(max_entries=8, ttl_seconds=60)
    tasks = AsyncTaskCoalescer()

    async def run(name):
        with workspace("alice", name):
            assert cache.get("identical request") is None
            assert tasks.get("identical request") is None
            task = asyncio.create_task(asyncio.to_thread(analysis_scope.get))
            tasks.set("identical request", task)
            await asyncio.sleep(0)
            assert tasks.get("identical request") is task
            assert len(tasks) == 1
            cache.set("identical request", {"owner": await task})
            tasks.discard("identical request", task)
            return cache.get("identical request")

    async def main():
        left, right = await asyncio.gather(run("a"), run("b"))
        assert left["owner"] == desk_scope("alice", "a")
        assert right["owner"] == desk_scope("alice", "b")
    asyncio.run(main())
    assert cache.get("identical request") is None
    assert cache.stats()["entries"] == len(tasks) == 0


def test_scan_result_and_cancellation_stay_with_the_owner():
    from instock.web.czsc_scan_handler import CZSCScanTaskRegistry

    async def main():
        registry = CZSCScanTaskRegistry()
        finished = asyncio.Event()
        async def execute(*_):
            await finished.wait()
        registry._execute = execute
        with workspace("alice", "a"):
            scan = registry.create({"symbols": ["300502"]})
            task = registry._tasks[scan["scan_id"]]
            assert registry.get(scan["scan_id"])
        with workspace("alice", "b"):
            assert registry.get(scan["scan_id"]) is None
            assert registry.cancel(scan["scan_id"]) is None
            assert registry.stats()["entries"] == 0
        with workspace("alice", "a"):
            assert registry.get(scan["scan_id"])["status"] == "queued"
            assert registry.cancel(scan["scan_id"])["status"] == "cancelling"
        finished.set()
        await task
    asyncio.run(main())


class ScopeEcho(AnalysisApiHandler):
    async def get(self):
        await asyncio.sleep(0.01)
        self.write_success({"scope": analysis_scope.get(), "thread": await asyncio.to_thread(analysis_scope.get)})


class RequestScopeTest(AsyncHTTPTestCase):
    def get_app(self):
        return tornado.web.Application([(r"/api/v1/test-scope", ScopeEcho)])

    @gen_test
    async def test_http_context_survives_await_thread_and_resets(self):
        async def resolve(headers, **_):
            return desk_scope("alice", headers["X-Test-Workspace"])
        with patch("instock.web.api_contract.resolve_request_scope", resolve):
            responses = await asyncio.gather(*[self.http_client.fetch(self.get_url("/api/v1/test-scope"),
                headers={"X-Test-Workspace": name}) for name in ("a", "b")])
        for response, name in zip(responses, ("a", "b")):
            assert json.loads(response.body)["data"] == {"scope": desk_scope("alice", name), "thread": desk_scope("alice", name)}
        unsigned = await self.http_client.fetch(self.get_url("/api/v1/test-scope"))
        assert json.loads(unsigned.body)["data"]["scope"] == "standalone:local"
        assert analysis_scope.get() == "standalone:local"

    @gen_test
    async def test_invalid_scope_never_runs_handler_or_falls_back(self):
        async def reject(*_, **__):
            raise AnalysisScopeError(403, "invalid")
        with patch("instock.web.api_contract.resolve_request_scope", reject):
            response = await self.http_client.fetch(self.get_url("/api/v1/test-scope"), raise_error=False)
        assert response.code == 403
        assert "data" not in json.loads(response.body)

    @gen_test
    async def test_required_mode_blocks_unsigned_http_before_business_handler(self):
        with patch.dict(os.environ, {"INSTOCK_REQUIRE_DESK_SESSION": "1"}):
            response = await self.http_client.fetch(self.get_url("/api/v1/test-scope"),
                headers={"Cookie": "synthetic=logged-in"}, raise_error=False)
        assert response.code == 401
        assert response.headers["X-Instock-Access-Mode"] == "desk-required"
        assert "data" not in json.loads(response.body)


def test_scope_validation_failure_is_not_anonymous(monkeypatch):
    async def main():
        args = {"method": "GET", "path": "/api/v1/analysis-history"}
        assert await resolve_request_scope({"X-User-Id": "alice", "X-Workspace-Id": "a"}, **args) == "standalone:local"
        monkeypatch.delenv("INSTOCK_DESK_SCOPE_URL", raising=False)
        headers = {"X-Newma-Desk-Session": "bad", "X-Newma-Desk-Instance-Id": "instance"}
        with pytest.raises(AnalysisScopeError) as missing:
            await resolve_request_scope(headers, **args)
        assert missing.value.status == 503
        monkeypatch.setenv("INSTOCK_DESK_SCOPE_URL", "http://127.0.0.1/api/mods/runtime/instock-scope")
        async def denied(request):
            assert request.follow_redirects is False
            assert request.headers["Authorization"] == "Bearer bad"
            raise HTTPClientError(401)
        with patch("instock.web.analysis_scope.AsyncHTTPClient") as factory:
            factory.return_value.fetch = denied
            with pytest.raises(AnalysisScopeError) as invalid:
                await resolve_request_scope(headers, **args)
            assert invalid.value.status == 401
    asyncio.run(main())


def test_required_desk_mode_rejects_anonymous_and_partial_credentials(monkeypatch):
    monkeypatch.setenv("INSTOCK_REQUIRE_DESK_SESSION", "1")
    monkeypatch.setenv("INSTOCK_DESK_SCOPE_URL", "http://127.0.0.1/api/mods/runtime/instock-scope")

    async def main():
        for headers in ({}, {"Cookie": "logged-in"}, {"X-User-Id": "alice"},
                        {"Authorization": ""}, {"Authorization": "Bearer token"},
                        {"X-Newma-Desk-Session": "token", "X-Newma-Desk-Instance-Id": "one", "Authorization": "Bearer other"}):
            with pytest.raises(AnalysisScopeError) as error:
                await resolve_request_scope(headers, method="GET", path="/api/v1/analysis-history")
            assert error.value.status == 401
    asyncio.run(main())


def test_stock_validator_is_loopback_and_uses_authoritative_identity(monkeypatch):
    from types import SimpleNamespace
    from instock.web.analysis_scope import validate_scope_url
    for endpoint in ("https://other.example/api/mods/runtime/instock-scope", "http://localhost/private",
                     "http://user@localhost/api/mods/runtime/instock-scope", "http://localhost/api/mods/runtime/instock-scope?x=y"):
        with pytest.raises(ValueError):
            validate_scope_url(endpoint)
    monkeypatch.setenv("INSTOCK_DESK_SCOPE_URL", "http://127.0.0.1/api/mods/runtime/instock-scope")

    async def main():
        async def granted(request):
            assert request.follow_redirects is False
            assert set(request.headers) == {"Authorization", "X-Newma-Desk-Instance-Id", "Content-Type"}
            return SimpleNamespace(body=b'{"userId":"bound-user","workspaceId":"bound-workspace"}')
        with patch("instock.web.analysis_scope.AsyncHTTPClient") as factory:
            factory.return_value.fetch = granted
            result = await resolve_request_scope({"Authorization": "Bearer token", "X-Newma-Desk-Instance-Id": "one",
                "Cookie": "private", "X-User-Id": "forged"}, method="GET", path="/api/v1/analysis-history")
        assert result == desk_scope("bound-user", "bound-workspace")
    asyncio.run(main())
