import math
from datetime import datetime, timedelta
from threading import Event, Thread
from time import sleep

import pandas as pd

from instock.core.czsc_batch_scanner import CZSCBatchScanner


def _bars(size=180):
    rows = []
    for index in range(size):
        close = 20 + math.sin(index / 8) * 2 + index * 0.01
        open_ = close + math.sin(index * 1.3) * 0.15
        volume = 100000 + index * 100
        rows.append({
            "date": datetime(2025, 1, 1) + timedelta(days=index),
            "open": open_,
            "high": max(open_, close) + 0.3,
            "low": min(open_, close) - 0.3,
            "close": close,
            "volume": volume,
            "amount": volume * close,
        })
    frame = pd.DataFrame(rows)
    frame.attrs.update({"data_source": "fixture", "adjust": "qfq"})
    return frame


class FixtureProvider:
    name = "fixture"

    def get_kline(self, symbol, period="daily", limit=480, as_of=None):
        return _bars(max(limit, 180)).tail(limit).reset_index(drop=True)


class MixedHistoryProvider(FixtureProvider):
    def get_kline(self, symbol, period="daily", limit=480, as_of=None):
        size = 44 if symbol == "688825" else max(limit, 180)
        return _bars(size).tail(limit).reset_index(drop=True)


def test_batch_scanner_returns_ranked_compact_candidates_and_snapshots():
    progress = []
    result = CZSCBatchScanner(FixtureProvider(), max_workers=2).scan(
        ["300502", "512800", "510300"],
        period="daily",
        bars=120,
        on_progress=progress.append,
    )

    assert result["status"] == "completed"
    assert result["progress"] == {
        "total": 3,
        "completed": 3,
        "succeeded": 3,
        "failed": 0,
        "cancel_requested": False,
    }
    assert [row["rank"] for row in result["candidates"]] == [1, 2, 3]
    assert all("chart" not in row for row in result["candidates"])
    assert all(row["snapshot_id"].startswith("czsc:") for row in result["candidates"])
    assert result["ranking_is_official_czsc"] is False
    assert progress[-1]["completed"] == 3


def test_batch_scanner_honors_cancellation_before_scheduling():
    cancellation = Event()
    cancellation.set()

    result = CZSCBatchScanner(FixtureProvider()).scan(
        ["300502", "512800"],
        bars=120,
        cancel_event=cancellation,
    )

    assert result["status"] == "cancelled"
    assert result["progress"]["completed"] == 0
    assert result["candidates"] == []


def test_batch_scanner_excludes_short_history_from_formal_ranking():
    result = CZSCBatchScanner(MixedHistoryProvider(), max_workers=2).scan(
        ["300502", "688825"], bars=120
    )

    assert [row["symbol"] for row in result["candidates"]] == ["300502"]
    assert result["candidates"][0]["rank"] == 1
    assert result["short_history_watchlist"][0]["symbol"] == "688825"
    assert result["short_history_watchlist"][0]["bias"] == "unknown"
    assert result["short_history_watchlist"][0]["candidate_score"] == 0
    assert result["summary"]["short_history_watch"] == 1
    assert "short_history_securities_excluded_from_formal_ranking" in result["limitations"]


def test_cancelled_scan_waits_for_running_requests_to_settle(monkeypatch):
    cancellation = Event()
    release = Event()
    started = Event()
    calls = []
    outcome = {}
    scanner = CZSCBatchScanner(FixtureProvider(), max_workers=2)

    def blocking_analysis(symbol, period, bars, as_of):
        calls.append(symbol)
        if len(calls) == 2:
            started.set()
        release.wait(timeout=2)
        return {
            "symbol": symbol,
            "candidate_score": 50,
            "bias": "neutral",
            "input_quality": {"state": "complete"},
        }

    monkeypatch.setattr(scanner, "_analyze_one", blocking_analysis)
    worker = Thread(target=lambda: outcome.update(scanner.scan(
        ["300502", "512800", "510300"],
        bars=120,
        cancel_event=cancellation,
    )))
    worker.start()
    try:
        assert started.wait(timeout=1)
        cancellation.set()
        sleep(0.05)

        assert worker.is_alive()
        assert calls == ["300502", "512800"]
    finally:
        release.set()
        worker.join(timeout=2)

    assert not worker.is_alive()
    assert outcome["status"] == "cancelled"
