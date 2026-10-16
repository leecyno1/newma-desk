from copy import deepcopy
import json
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest
from tornado.testing import AsyncHTTPTestCase
from tornado.web import Application

from instock.core.analysis_history import AnalysisHistoryRegistry
from instock.core.workbench.market_journal import MarketJournalStore
from instock.web.market_journal_handler import MarketJournalHandler


def draft():
    return {"judgment": "相对领先但并非普涨", "support": "上涨占比40%", "counter": "缺少政策原文", "watch": "观察广度是否修复",
            "evidence": {"marketStructure": {"data": {"schemaVersion": "newma-desk.market-structure.v1", "expectedDate": "2026-10-15", "breadth": {"upRatioPct": 40}}},
                         "marketContinuity": {"data": None, "error": "读取失败"}, "marketEvidence": {"data": None, "selected": None}}}


def test_durable_review_survives_analysis_cache_expiry_and_checks_do_not_rewrite(tmp_path):
    path = str(tmp_path / "history.sqlite3")
    store = MarketJournalStore(path)
    body = draft()
    saved = store.create(body)
    body["evidence"]["marketStructure"]["data"]["breadth"]["upRatioPct"] = 99
    now = [100.0]
    cache = AnalysisHistoryRegistry(db_path=path, ttl_seconds=1, wall_clock=lambda: now[0])
    old = cache.register(module_id="test", payload={}, title="cache")
    now[0] += 2
    assert cache.get(old["history_id"]) is None
    reopened = MarketJournalStore(path)
    assert reopened.get(saved["id"]) == saved
    updated = reopened.add_check(saved["id"], {"observedDate": "2026-10-15", "outcome": "削弱", "note": "广度没有改善"})
    assert updated["notes"] == saved["notes"]
    assert updated["evidence"] == saved["evidence"]
    assert updated["evidence"]["marketContinuity"]["error"] == "读取失败"
    assert len(updated["checks"]) == 1
    assert MarketJournalStore(path).get(saved["id"]) == updated


@pytest.mark.parametrize("case", ["loading", "historical", "date", "shape", "blank", "missing_date"])
def test_invalid_or_mixed_evidence_not_saved(tmp_path, case):
    body = draft()
    if case in {"loading", "historical"}:
        body["evidence"]["marketStructure"][case] = True
    elif case == "date":
        body["evidence"]["marketContinuity"]["data"] = {"requestedDate": "2026-10-14"}
    elif case == "shape":
        body["evidence"]["marketStructure"] = []
    elif case == "blank":
        body["watch"] = " "
    else:
        del body["evidence"]["marketStructure"]["data"]["expectedDate"]
    store = MarketJournalStore(tmp_path / "history.sqlite3")
    with pytest.raises(ValueError):
        store.create(body)
    assert store.list()["items"] == []


def test_pagination_and_invalid_check(tmp_path):
    store = MarketJournalStore(tmp_path / "history.sqlite3")
    saved = [store.create(draft()) for _ in range(21)]
    first, second = store.list(), store.list(20)
    assert len(first["items"]) == 20 and first["hasMore"]
    assert len(second["items"]) == 1 and not second["hasMore"]
    assert second["items"][0]["id"] == saved[0]["id"]
    for change in ({"observedDate": "2026-01-01"}, {"observedDate": "2999-01-01"}, {"outcome": "成功"}, {"note": ""}):
        with pytest.raises(ValueError):
            store.add_check(saved[0]["id"], {"observedDate": "2026-10-15", "outcome": "支持", "note": "观察依据", **change})
    assert store.get(saved[0]["id"])["checks"] == []


def test_pending_filter_precedes_pagination_and_covers_old_records(tmp_path):
    store = MarketJournalStore(tmp_path / "journal.sqlite3")
    saved = [store.create(draft()) for _ in range(22)]
    for record in saved[1:]:
        store.add_check(record["id"], {"observedDate": "2026-10-15", "outcome": "支持", "note": "人工核验，不是回测胜率"})
    pending = store.list(status="pending")
    assert pending["counts"] == {"total": 22, "pending": 1, "reviewed": 21}
    assert [item["id"] for item in pending["items"]] == [saved[0]["id"]]
    assert not pending["hasMore"]
    reviewed = store.list(status="reviewed")
    assert len(reviewed["items"]) == 20 and reviewed["hasMore"]
    assert len(store.list(offset=20, status="reviewed")["items"]) == 1
    assert all(item["latestCheck"]["outcome"] == "支持" for item in reviewed["items"])


def test_latest_entered_check_drives_followup_and_can_reopen(tmp_path):
    store = MarketJournalStore(tmp_path / "journal.sqlite3")
    body = draft()
    body["evidence"]["marketStructure"]["data"]["expectedDate"] = "2026-10-13"
    body["watch"] = "观察条件" * 100
    record = store.create(body)
    store.add_check(record["id"], {"observedDate": "2026-10-15", "outcome": "削弱", "note": "原观察"})
    assert store.list(status="pending")["items"] == []
    store.add_check(record["id"], {"observedDate": "2026-10-14", "outcome": "待观察", "note": "补录发现依据不足" * 40})
    result = MarketJournalStore(store.path).list(status="pending")
    item = result["items"][0]
    assert result["counts"] == {"total": 1, "pending": 1, "reviewed": 0}
    assert item["checkCount"] == 2 and item["latestCheck"]["observedDate"] == "2026-10-14"
    assert item["watchTruncated"] and len(item["watch"]) == 240
    assert item["latestCheck"]["noteTruncated"] and len(item["latestCheck"]["note"]) == 160
    assert store.get(record["id"])["notes"]["watch"] == body["watch"]


def test_empty_queue_and_unknown_filter(tmp_path):
    store = MarketJournalStore(tmp_path / "journal.sqlite3")
    assert store.list(status="pending")["counts"] == {"total": 0, "pending": 0, "reviewed": 0}
    with pytest.raises(ValueError):
        store.list(status="winning")


class TestJournalHTTP(AsyncHTTPTestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.store = MarketJournalStore(self.temp.name + "/journal.sqlite3")
        self.store_patch = patch("instock.web.market_journal_handler.get_market_journal_store", return_value=self.store)
        self.store_patch.start()
        super().setUp()

    def tearDown(self):
        super().tearDown()
        self.store_patch.stop()
        self.temp.cleanup()

    def get_app(self):
        return Application([(r"/reviews", MarketJournalHandler), (r"/reviews/([a-f0-9]{32})", MarketJournalHandler)])

    def test_roundtrip_validation_and_origin(self):
        response = self.fetch('/reviews', method='POST', body=json.dumps(draft()), headers={'Origin': self.get_url('/').rstrip('/')})
        assert response.code == 200
        saved = json.loads(response.body)["data"]
        url = '/reviews/' + saved['id']
        assert json.loads(self.fetch(url).body)["data"] == saved
        response = self.fetch(url, method='POST', body=json.dumps({"observedDate": "2026-10-15", "outcome": "支持", "note": "核验"}))
        assert len(json.loads(response.body)["data"]["checks"]) == 1
        assert self.fetch('/reviews?offset=-1').code == 400
        assert self.fetch('/reviews?status=invalid').code == 400
        pending = json.loads(self.fetch('/reviews?status=pending').body)["data"]
        assert pending["items"] == [] and pending["counts"]["reviewed"] == 1
        assert self.fetch('/reviews/' + '0' * 32).code == 404
        invalid = deepcopy(draft())
        del invalid['evidence']['marketStructure']['data']['expectedDate']
        assert self.fetch('/reviews', method='POST', body=json.dumps(invalid)).code == 400
        assert self.fetch('/reviews', method='POST', body='[]').code == 400
        assert self.fetch('/reviews', method='POST', body=json.dumps(draft()), headers={'Origin': 'https://untrusted.example'}).code == 403
