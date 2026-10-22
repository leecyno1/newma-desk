"""Limit-pool dates must come from the upstream snapshot, not the request."""
from datetime import datetime
from types import SimpleNamespace

import pytest

import astock
import market


@pytest.mark.parametrize("qdate", [20261020, None, "invalid"])
def test_limit_pool_rejects_unverified_or_mismatched_date(monkeypatch, qdate):
    monkeypatch.setattr(astock, "em_get", lambda *a, **kw: SimpleNamespace(
        json=lambda: {"data": {"qdate": qdate, "pool": [{"c": "600001"}]}}
    ))
    assert astock.em_zt_topic_pool("getTopicZTPool", "20261021") == []


@pytest.mark.parametrize("qdate", [20261021, "20261021"])
def test_limit_pool_accepts_matching_upstream_date(monkeypatch, qdate):
    rows = [{"c": "600001", "lbc": 2}]
    monkeypatch.setattr(astock, "em_get", lambda *a, **kw: SimpleNamespace(
        json=lambda: {"data": {"qdate": qdate, "pool": rows}}
    ))
    assert astock.em_zt_topic_pool("getTopicZTPool", "20261021") == rows


def test_preopen_emotion_uses_actual_previous_snapshot_date(monkeypatch):
    class Preopen(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 22, 7, 30, tzinfo=tz)

    monkeypatch.setattr(market, "datetime", Preopen)
    monkeypatch.setattr(astock, "em_get", lambda *a, **kw: SimpleNamespace(
        json=lambda: {"data": {"qdate": 20261021, "pool": [{"c": "600001", "lbc": 2}]}}
    ))
    result = market._emotion()
    assert result["date"] == "2026-10-21"
    assert result["zt_count"] == 1
