from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from threading import Lock
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
import tornado.web
from tornado.testing import AsyncHTTPTestCase

from instock.core.analysis_snapshot import get_analysis_snapshot_registry
from instock.core.analysis_history import get_analysis_history_registry
from instock.core.market_data_provider import MarketDataError, MarketDataProvider
from instock.core.selection.stock_candidates import StockCandidateEngine, StockCandidateError
from instock.core.research.event_flow import EventFlowEngine
from instock.web import stock_candidates_handler
from instock.web.stock_candidates_handler import StockCandidateSnapshotHandler


def _frame(*, growth: float, noise: float = 0.0, size: int = 140, volume_boost: float = 1.0):
    dates = pd.bdate_range("2026-01-02", periods=size)
    base = np.linspace(20, 20 * (1 + growth), size)
    wave = np.sin(np.arange(size) / 4) * noise
    close = base * (1 + wave)
    volume = np.full(size, 2_000_000.0)
    volume[-1] *= volume_boost
    frame = pd.DataFrame({
        "date": dates,
        "open": close * 0.995,
        "high": close * 1.015,
        "low": close * 0.985,
        "close": close,
        "volume": volume,
        "amount": close * volume,
    })
    frame.attrs.update({
        "data_source": "fixture",
        "data_endpoint": "fixture://ohlcv",
        "adjust": "qfq",
        "upstream_source": "fixture",
        "upstream_as_of": dates[-1].isoformat(),
    })
    return frame


def _fundamental(
    symbol,
    *,
    quality=50.0,
    growth=50.0,
    valuation=50.0,
    omitted=(),
):
    scores = {"quality": quality, "growth": growth, "valuation": valuation}
    return {
        "schemaVersion": "newma-dock.equity-research.v1",
        "identity": {"symbol": symbol, "name": symbol, "market": "CN"},
        "coverage": {"coveredDimensions": 6, "totalDimensions": 6, "ratio": 1.0},
        "scorecard": [
            {"id": factor, "title": factor, "score": score, "status": "balanced"}
            for factor, score in scores.items()
            if factor not in omitted
        ],
        "comparisonProfile": {"metrics": {
            "revenueGrowthPct": 20.0,
            "netProfitGrowthPct": 18.0,
            "roePct": 12.0,
            "grossMarginPct": 30.0,
            "netMarginPct": 10.0,
            "cashConversionPct": 80.0,
            "valuationPercentile": 50.0,
            "pe": 20.0,
            "pb": 2.0,
        }},
        "workflow": {"dataQuality": {"score": 85, "level": "good", "limitations": []}},
        "gaps": [],
        "generatedAt": "2026-07-17T18:00:00+08:00",
    }


class CandidateFixtureProvider(MarketDataProvider):
    name = "fixture"

    def __init__(self, items, frames, fundamentals=None):
        self.items = items
        self.frames = frames
        self.fundamentals = fundamentals or {}
        self.snapshot_requests = []

    def get_stock_scan(self, *, sort="amount", order="desc", limit=50):
        return {
            "items": self.items[:limit],
            "market": "CN",
            "sort": sort,
            "order": order,
            "source": "fixture-scan",
            "as_of": "2026-07-17T15:00:00+08:00",
            "coverage": {"requested": limit, "returned": min(limit, len(self.items))},
        }

    def get_liquidity_scan(self, *, limit=50):
        result = self.get_stock_scan(sort="amount", order="desc", limit=limit)
        result["coverage"].update({
            "scope": "full_market_top20_plus_market_cap_pool",
            "sort_basis": "amount_top20_then_marketCap",
        })
        return result

    def get_kline(self, symbol, period="daily", limit=480, as_of=None):
        value = self.frames[symbol]
        if isinstance(value, Exception):
            raise value
        return value.tail(limit).reset_index(drop=True)

    def get_equity_snapshot(self, symbol, *, refresh=False):
        self.snapshot_requests.append(symbol)
        value = self.fundamentals.get(symbol, _fundamental(symbol))
        if isinstance(value, Exception):
            raise value
        return value


def _comparison_row(symbol, *, quality=50.0, growth=50.0, valuation=50.0):
    return {
        "identity": {"symbol": symbol, "name": symbol, "market": "CN"},
        "scores": {
            "quality": quality,
            "growth": growth,
            "valuation": valuation,
        },
        "coverage": {"coveredDimensions": 3, "totalDimensions": 3, "ratio": 1.0},
        "metrics": {},
    }


class ComparisonFixtureProvider(CandidateFixtureProvider):
    def __init__(self, items, frames, fundamentals=None, comparison_resolver=None):
        super().__init__(items, frames, fundamentals)
        self.comparison_resolver = comparison_resolver
        self.comparison_requests = []
        self._comparison_lock = Lock()
        self._comparison_active = 0
        self.comparison_peak = 0
        self._snapshot_lock = Lock()
        self._snapshot_active = 0
        self.snapshot_peak = 0
        self.comparison_refreshes = []
        self.snapshot_refreshes = []

    def get_equity_comparison(self, symbols, *, refresh=False):
        chunk = list(symbols)
        self.comparison_requests.append(chunk)
        self.comparison_refreshes.append(refresh)
        with self._comparison_lock:
            self._comparison_active += 1
            self.comparison_peak = max(self.comparison_peak, self._comparison_active)
        try:
            time.sleep(0.02)
            if self.comparison_resolver is not None:
                return self.comparison_resolver(chunk)
            return {
                "rows": [_comparison_row(symbol) for symbol in chunk],
                "errors": [],
                "generatedAt": "2026-08-13T10:00:00+08:00",
            }
        finally:
            with self._comparison_lock:
                self._comparison_active -= 1

    def get_equity_snapshot(self, symbol, *, refresh=False):
        self.snapshot_refreshes.append(refresh)
        with self._snapshot_lock:
            self._snapshot_active += 1
            self.snapshot_peak = max(self.snapshot_peak, self._snapshot_active)
        try:
            time.sleep(0.01)
            return super().get_equity_snapshot(symbol, refresh=refresh)
        finally:
            with self._snapshot_lock:
                self._snapshot_active -= 1


class MultiMarketCandidateProvider(CandidateFixtureProvider):
    def __init__(self, items, frames, fundamentals=None):
        super().__init__(items, frames, fundamentals)
        self.kline_symbols = []

    def get_candidate_universe(self, *, markets=("CN",), per_scan_limit=200):
        items = [item for item in self.items if item.get("market") in markets]
        return {
            "items": items,
            "market": "+".join(markets),
            "source": "fixture-multi-market",
            "as_of": "2026-08-15T10:00:00+08:00",
            "coverage": {
                "requested": per_scan_limit * len(markets),
                "returned": len(items),
                "scope": "desk_multi_scan_union",
                "sort_basis": "fixture",
                "full_security_master": False,
            },
        }

    def get_kline(self, symbol, period="daily", limit=480, as_of=None):
        self.kline_symbols.append(symbol)
        return super().get_kline(symbol.split(".")[0], period, limit, as_of)


def _quote(symbol, name, *, change, amount, turnover, volume_ratio, pe, pb, industry):
    return {
        "symbol": symbol,
        "name": name,
        "market": "CN",
        "exchange": "SZ",
        "price": 30.0,
        "change_pct": change,
        "amount": amount,
        "turnover_pct": turnover,
        "volume_ratio": volume_ratio,
        "market_cap": 80_000_000_000,
        "float_market_cap": 60_000_000_000,
        "pe": pe,
        "pb": pb,
        "industry": industry,
    }


def _event_packet():
    return {
        "schema_version": "instock-event-flow-packet-v1",
        "as_of": "2026-08-11",
        "market": "CN",
        "events": [
            {"id": "flow-1", "type": "fund_flow", "symbol": "300502", "occurred_at": "2026-08-10", "title": "主力资金净流入", "direction": "positive", "magnitude_score": 80, "evidence_strength": "strong", "source_ref": "desk://flow/300502/20260810"},
            {"id": "risk-1", "type": "announcement", "symbol": "300502", "occurred_at": "2026-08-09", "title": "股东减持计划", "direction": "negative", "magnitude_score": 70, "evidence_strength": "medium", "source_ref": "desk://announcement/300502/risk-1"},
            {"id": "other-1", "type": "report", "symbol": "000001", "occurred_at": "2026-08-08", "title": "银行跟踪", "direction": "neutral", "magnitude_score": 40, "evidence_strength": "weak", "source_ref": "desk://report/000001/1"},
        ],
    }


def test_candidate_engine_ranks_explainable_balanced_candidate_first():
    items = [
        _quote("000001", "稳健成长", change=2.6, amount=2.2e9, turnover=4.2, volume_ratio=1.35, pe=18, pb=2.1, industry="银行"),
        _quote("000002", "高热题材", change=9.7, amount=3.6e9, turnover=24.0, volume_ratio=3.8, pe=160, pb=18, industry="电子"),
        _quote("000003", "低估震荡", change=0.3, amount=1.3e9, turnover=1.8, volume_ratio=0.8, pe=9, pb=0.9, industry="公用事业"),
    ]
    provider = CandidateFixtureProvider(items, {
        "000001": _frame(growth=0.65, noise=0.005, volume_boost=1.8),
        "000002": _frame(growth=0.9, noise=0.06, volume_boost=4.2),
        "000003": _frame(growth=0.08, noise=0.012),
    })

    result = StockCandidateEngine(provider).analyze(universe_size=30, output_size=10, bars=120)

    assert result["engine"] == {
        "name": "instock-stock-candidate-engine",
        "version": "1.4.0",
        "factor_model": "instock-stock-candidate-score-v3",
    }
    assert result["factor_model"]["weights"] == {
        "trend": 0.20,
        "momentum": 0.15,
        "liquidity": 0.10,
        "stability": 0.10,
        "valuation": 0.10,
        "quality": 0.15,
        "growth": 0.10,
        "classic": 0.10,
    }
    assert result["candidates"][0]["symbol"] == "000001"
    assert result["candidates"][0]["rank"] == 1
    assert result["candidates"][0]["score"] > result["candidates"][1]["score"]
    assert set(result["candidates"][0]["factor_scores"]) == set(result["factor_model"]["weights"])
    assert "均线多头" in result["candidates"][0]["classic_signals"]
    assert any("过热" in item for item in next(row for row in result["candidates"] if row["symbol"] == "000002")["risks"])
    assert result["summary"]["top_symbol"] == "000001"
    assert result["coverage"]["fundamental_available_count"] == 3
    assert result["coverage"]["scan_scope"] == "full_market_top20_plus_market_cap_pool"
    assert result["coverage"]["scan_sort_basis"] == "amount_top20_then_marketCap"
    assert "candidate_pool_uses_turnover_top20_then_market_cap_fill" in result["limitations"]
    assert result["candidates"][0]["fundamentals"]["source"] == "research.equity-snapshot"
    assert result["candidates"][0]["amount_source"] == "scan_realtime"
    assert result["calibrated_backtest"] is False
    quality = {item["id"]: item for item in result["evidence_quality"]["items"]}
    assert result["evidence_quality"]["positioning"] == "research_candidate_only"
    assert result["evidence_quality"]["calibration_state"] == "not_calibrated"
    assert quality["universe"]["state"] == "limited"
    assert quality["point_in_time"]["state"] == "unavailable"
    assert quality["calibration"]["state"] == "unavailable"
    assert quality["price_history"]["state"] == "available"
    assert quality["fundamentals"]["state"] == "available"
    assert result["snapshot"]["snapshot_id"].startswith("instock-stock-candidate-engine:")


def test_candidate_engine_supports_hk_market_and_qualified_kline_symbol():
    hk_item = {
        **_quote("00700", "腾讯控股", change=1.2, amount=8e9, turnover=0.4,
                 volume_ratio=1.1, pe=16, pb=3.1, industry="软件服务"),
        "market": "HK",
        "exchange": "HKEX",
    }
    provider = MultiMarketCandidateProvider(
        [hk_item],
        {"00700": _frame(growth=0.35)},
        {"00700": _fundamental("00700", quality=72, growth=60, valuation=78)},
    )

    result = StockCandidateEngine(provider).analyze(
        market="HK", universe_mode="broad", universe_size=30
    )

    assert result["market"] == "HK"
    assert result["coverage"]["markets"] == ["HK"]
    assert result["candidates"][0]["market"] == "HK"
    assert provider.kline_symbols == ["00700.HK"]
    assert "desk_scan_union_not_full_security_master" in result["limitations"]


def test_candidate_engine_uses_desk_financial_scores_to_rerank_preselected_stocks():
    items = [
        _quote("000001", "财务弱", change=1.0, amount=2e9, turnover=3, volume_ratio=1, pe=20, pb=2, industry="电子"),
        _quote("000002", "财务强", change=1.0, amount=2e9, turnover=3, volume_ratio=1, pe=20, pb=2, industry="电子"),
    ]
    provider = CandidateFixtureProvider(
        items,
        {symbol: _frame(growth=0.35) for symbol in ("000001", "000002")},
        {
            "000001": _fundamental("000001", quality=15, growth=20, valuation=25),
            "000002": _fundamental("000002", quality=95, growth=90, valuation=85),
        },
    )

    result = StockCandidateEngine(provider).analyze()

    assert [row["symbol"] for row in result["candidates"]] == ["000002", "000001"]
    assert result["candidates"][0]["factor_scores"]["quality"] == 95.0
    assert result["candidates"][0]["factor_scores"]["growth"] == 90.0
    assert result["candidates"][0]["factor_scores"]["valuation"] == 85.0


def test_candidate_engine_neutralizes_failed_financial_snapshot_without_dropping_stock():
    items = [
        _quote("000001", "快照失败", change=1.0, amount=2e9, turnover=3, volume_ratio=1, pe=20, pb=2, industry="电子"),
    ]
    provider = CandidateFixtureProvider(
        items,
        {"000001": _frame(growth=0.35)},
        {"000001": MarketDataError("equity snapshot unavailable")},
    )

    result = StockCandidateEngine(provider).analyze()

    assert [row["symbol"] for row in result["candidates"]] == ["000001"]
    assert result["candidates"][0]["fundamentals"]["available"] is False
    assert result["candidates"][0]["fundamentals"]["scores"] == {
        "valuation": 50.0,
        "quality": 50.0,
        "growth": 50.0,
    }
    assert result["coverage"]["fundamental_failed_count"] == 1
    assert result["data_state"] == "partial"
    assert "partial_fundamental_coverage_neutralized" in result["limitations"]


def test_candidate_engine_does_not_repeat_failed_financial_requests():
    provider = CandidateFixtureProvider(
        [_quote("000001", "快照失败", change=1.0, amount=2e9, turnover=3, volume_ratio=1, pe=20, pb=2, industry="电子")],
        {"000001": _frame(growth=0.35)},
        {"000001": MarketDataError("temporary gateway failure")},
    )

    result = StockCandidateEngine(provider).analyze()

    assert provider.snapshot_requests == ["000001"]
    assert result["coverage"]["fundamental_retry_count"] == 0
    assert result["coverage"]["fundamental_recovered_count"] == 0
    assert result["coverage"]["fundamental_failed_count"] == 1


def test_candidate_engine_limits_ten_output_financial_requests_to_top_20():
    symbols = [f"{index:06d}" for index in range(1, 51)]
    items = [
        _quote(symbol, f"候选{symbol}", change=1.0, amount=2e9, turnover=3, volume_ratio=1, pe=20, pb=2, industry="电子")
        for symbol in symbols
    ]
    provider = CandidateFixtureProvider(
        items,
        {symbol: _frame(growth=0.1 + index / 200) for index, symbol in enumerate(symbols)},
    )

    result = StockCandidateEngine(provider).analyze(universe_size=50)

    assert result["coverage"]["analyzed_count"] == 50
    assert result["coverage"]["fundamental_requested_count"] == 20
    assert result["coverage"]["fundamental_available_count"] == 20
    assert len(provider.snapshot_requests) == 20
    assert "two_stage_preselection_top_20" in result["limitations"]


def test_candidate_engine_limits_comparison_batches_to_three_concurrent_requests():
    symbols = [f"{index:06d}" for index in range(1, 31)]
    provider = ComparisonFixtureProvider(
        [
            _quote(symbol, symbol, change=1.0, amount=2e9, turnover=3,
                   volume_ratio=1, pe=20, pb=2, industry="电子")
            for symbol in symbols
        ],
        {symbol: _frame(growth=0.2) for symbol in symbols},
    )

    result = StockCandidateEngine(provider, max_workers=12).analyze(
        universe_size=30, output_size=30
    )

    assert result["coverage"]["fundamental_batch_count"] == 8
    assert result["coverage"]["fundamental_snapshot_fallback_count"] == 0
    assert result["coverage"]["fundamental_batch_worker_limit"] == 3
    assert result["coverage"]["fundamental_batch_failure_count"] == 0
    assert result["coverage"]["fundamental_batch_timeout_seconds"] == 60.0
    assert provider.comparison_peak == 3
    assert provider.snapshot_requests == []


def test_candidate_engine_forwards_refresh_to_financial_provider():
    symbols = [f"{index:06d}" for index in range(1, 6)]
    provider = ComparisonFixtureProvider(
        [
            _quote(symbol, symbol, change=1.0, amount=2e9, turnover=3,
                   volume_ratio=1, pe=20, pb=2, industry="电子")
            for symbol in symbols
        ],
        {symbol: _frame(growth=0.2) for symbol in symbols},
    )

    StockCandidateEngine(provider).analyze(refresh=True)

    assert provider.comparison_refreshes
    assert all(provider.comparison_refreshes)


def test_candidate_engine_only_falls_back_for_rows_missing_from_comparison():
    symbols = [f"{index:06d}" for index in range(1, 11)]
    missing = {symbols[2], symbols[7]}

    def comparison(chunk):
        return {
            "rows": [
                _comparison_row(symbol)
                for symbol in chunk
                if symbol not in missing
            ],
            "errors": [
                {"symbol": symbol, "error": "comparison row unavailable"}
                for symbol in chunk
                if symbol in missing
            ],
            "generatedAt": "2026-08-13T10:00:00+08:00",
        }

    provider = ComparisonFixtureProvider(
        [
            _quote(symbol, symbol, change=1.0, amount=2e9, turnover=3,
                   volume_ratio=1, pe=20, pb=2, industry="电子")
            for symbol in symbols
        ],
        {symbol: _frame(growth=0.2) for symbol in symbols},
        comparison_resolver=comparison,
    )

    result = StockCandidateEngine(provider).analyze(
        universe_size=30, output_size=10
    )

    assert result["coverage"]["fundamental_available_count"] == 10
    assert result["coverage"]["fundamental_snapshot_fallback_count"] == 2
    assert set(provider.snapshot_requests) == missing
    assert len(provider.snapshot_requests) == 2


def test_candidate_engine_limits_snapshot_fallback_after_batch_failure():
    symbols = [f"{index:06d}" for index in range(1, 13)]

    def comparison(_chunk):
        raise MarketDataError("comparison unavailable")

    provider = ComparisonFixtureProvider(
        [
            _quote(symbol, symbol, change=1.0, amount=2e9, turnover=3,
                   volume_ratio=1, pe=20, pb=2, industry="电子")
            for symbol in symbols
        ],
        {symbol: _frame(growth=0.2) for symbol in symbols},
        comparison_resolver=comparison,
    )

    result = StockCandidateEngine(provider, max_workers=12).analyze(
        universe_size=30, output_size=10
    )

    assert result["coverage"]["fundamental_available_count"] == len(symbols)
    assert result["coverage"]["fundamental_snapshot_fallback_count"] == len(symbols)
    assert result["coverage"]["fundamental_batch_failure_count"] == 3
    assert result["coverage"]["fundamental_snapshot_failure_count"] == 0
    assert result["coverage"]["fundamental_snapshot_worker_limit"] == 3
    assert result["coverage"]["fundamental_snapshot_timeout_seconds"] == 20.0
    assert provider.snapshot_peak == 3
    assert set(provider.snapshot_requests) == set(symbols)


def test_candidate_engine_reports_batch_and_snapshot_timeouts_separately():
    symbol = "000001"

    def comparison(_chunk):
        raise MarketDataError("comparison request timed out")

    provider = ComparisonFixtureProvider(
        [_quote(symbol, symbol, change=1.0, amount=2e9, turnover=3,
                volume_ratio=1, pe=20, pb=2, industry="电子")],
        {symbol: _frame(growth=0.2)},
        {symbol: MarketDataError("snapshot 请求超时")},
        comparison_resolver=comparison,
    )

    result = StockCandidateEngine(provider).analyze()

    assert result["coverage"]["fundamental_batch_timeout_count"] == 1
    assert result["coverage"]["fundamental_snapshot_timeout_count"] == 1
    assert result["coverage"]["fundamental_snapshot_failure_count"] == 1
    assert result["data_state"] == "partial"


def test_candidate_engine_keeps_top_30_financial_pool_for_thirty_outputs():
    symbols = [f"{index:06d}" for index in range(1, 51)]
    provider = CandidateFixtureProvider(
        [
            _quote(symbol, f"候选{symbol}", change=1.0, amount=2e9, turnover=3, volume_ratio=1, pe=20, pb=2, industry="电子")
            for symbol in symbols
        ],
        {symbol: _frame(growth=0.1 + index / 200) for index, symbol in enumerate(symbols)},
    )

    result = StockCandidateEngine(provider).analyze(
        universe_size=50, output_size=30
    )

    assert result["coverage"]["fundamental_requested_count"] == 30
    assert len(provider.snapshot_requests) == 30
    assert "two_stage_preselection_top_30" in result["limitations"]


def test_candidate_engine_keeps_top_30_financial_pool_for_twenty_outputs():
    symbols = [f"{index:06d}" for index in range(1, 51)]
    provider = CandidateFixtureProvider(
        [
            _quote(symbol, f"候选{symbol}", change=1.0, amount=2e9, turnover=3, volume_ratio=1, pe=20, pb=2, industry="电子")
            for symbol in symbols
        ],
        {symbol: _frame(growth=0.1 + index / 200) for index, symbol in enumerate(symbols)},
    )

    result = StockCandidateEngine(provider).analyze(
        universe_size=50, output_size=20
    )

    assert result["coverage"]["fundamental_requested_count"] == 30
    assert len(provider.snapshot_requests) == 30


def test_candidate_engine_filters_legacy_noise_and_marks_partial_coverage():
    items = [
        _quote("000001", "正常公司", change=1.2, amount=1.1e9, turnover=3.0, volume_ratio=1.1, pe=22, pb=2.4, industry="机械设备"),
        _quote("000002", "*ST 风险", change=4.0, amount=9e8, turnover=5.0, volume_ratio=1.8, pe=10, pb=1.0, industry="综合"),
        _quote("000003", "行情失败", change=2.0, amount=8e8, turnover=4.0, volume_ratio=1.2, pe=28, pb=3.0, industry="电子"),
    ]
    provider = CandidateFixtureProvider(items, {
        "000001": _frame(growth=0.3),
        "000002": _frame(growth=0.5),
        "000003": MarketDataError("fixture missing"),
    })

    first = StockCandidateEngine(provider).analyze(universe_size=30, output_size=10, bars=120)
    second = StockCandidateEngine(provider).analyze(universe_size=30, output_size=10, bars=120)

    assert [row["symbol"] for row in first["candidates"]] == ["000001"]
    assert first["data_state"] == "partial"
    assert first["coverage"]["scan_count"] == 3
    assert first["coverage"]["eligible_count"] == 2
    assert first["coverage"]["analyzed_count"] == 1
    assert first["failures"] == [{"symbol": "000003", "error": "fixture missing"}]
    assert "excluded_special_treatment:000002" in first["limitations"]
    assert first["snapshot"]["snapshot_id"] == second["snapshot"]["snapshot_id"]


def test_candidate_engine_uses_confidence_adjusted_short_history_model():
    items = [
        _quote("000001", "正常公司", change=1.2, amount=1.1e9, turnover=3.0, volume_ratio=1.1, pe=22, pb=2.4, industry="机械设备"),
        _quote("688825", "次新公司", change=2.0, amount=8e8, turnover=4.0, volume_ratio=1.2, pe=28, pb=3.0, industry="电子"),
    ]
    provider = CandidateFixtureProvider(items, {
        "000001": _frame(growth=0.3),
        "688825": _frame(growth=0.1, size=12),
    })

    result = StockCandidateEngine(provider).analyze()

    assert result["data_state"] == "complete"
    assert result["failures"] == []
    assert result["coverage"]["analyzed_count"] == 2
    assert result["coverage"]["failed_count"] == 0
    assert result["coverage"]["history_excluded_count"] == 0
    assert result["coverage"]["short_history_count"] == 1
    assert result["history_exclusions"] == []
    assert result["new_listing_watchlist"] == []
    short = next(row for row in result["candidates"] if row["symbol"] == "688825")
    assert short["history_bars"] == 12
    assert short["history_mode"] == "short"
    assert short["technical_confidence"] == 0.15
    assert short["status"] == "短历史观察"
    assert short["metrics"]["momentum_20_window"] < 20
    assert all(
        abs(short["factor_scores"][factor] - 50) <= 7.5
        for factor in ("trend", "momentum", "stability", "classic")
    )
    assert "short_history_scores_confidence_adjusted" in result["limitations"]
    assert "partial_kline_coverage" not in result["limitations"]


def test_candidate_engine_places_fewer_than_ten_bars_in_new_listing_watchlist():
    items = [
        _quote("000001", "正常公司", change=1.2, amount=1.1e9, turnover=3.0, volume_ratio=1.1, pe=22, pb=2.4, industry="机械设备"),
        _quote("301717", "C超纯应材", change=0.1, amount=8e8, turnover=4.0, volume_ratio=1.2, pe=28, pb=3.0, industry="电子"),
    ]
    provider = CandidateFixtureProvider(items, {
        "000001": _frame(growth=0.3),
        "301717": _frame(growth=0.1, size=2),
    })

    result = StockCandidateEngine(provider).analyze()

    assert result["data_state"] == "complete"
    assert result["failures"] == []
    assert result["coverage"]["analyzed_count"] == 1
    assert result["coverage"]["history_excluded_count"] == 1
    assert result["coverage"]["new_listing_watch_count"] == 1
    assert result["history_exclusions"] == [{
        "symbol": "301717",
        "name": "C超纯应材",
        "reason": "new_listing_watch",
        "basis": "daily_bars",
        "required_bars": 10,
        "available_bars": 2,
        "history_mode": "new_listing_watch",
        "technical_confidence": 0.025,
        "data_start": "2026-01-02",
        "data_end": "2026-01-05",
        "history_source": "fixture",
        "history_has_more": None,
        "message": "有效日线不足 10 根（实际 2），暂列新股观察",
    }]
    assert result["new_listing_watchlist"] == result["history_exclusions"]
    assert "new_listing_watch_not_ranked" in result["limitations"]
    assert "partial_kline_coverage" not in result["limitations"]


def test_candidate_engine_requires_full_twenty_day_history_for_twenty_day_filter():
    items = [
        _quote("000001", "正常公司", change=1.2, amount=1.1e9, turnover=3.0, volume_ratio=1.1, pe=22, pb=2.4, industry="机械设备"),
        _quote("688825", "次新公司", change=2.0, amount=8e8, turnover=4.0, volume_ratio=1.2, pe=28, pb=3.0, industry="电子"),
    ]
    provider = CandidateFixtureProvider(items, {
        "000001": _frame(growth=0.3),
        "688825": _frame(growth=0.5, size=13),
    })

    result = StockCandidateEngine(provider).analyze(
        filters={"min_momentum_20_pct": 1},
    )

    assert [row["symbol"] for row in result["candidates"]] == ["000001"]
    excluded = next(
        row for row in result["excluded_by_rules"] if row["symbol"] == "688825"
    )
    assert excluded["reasons"] == ["momentum_20_history_unavailable"]


def test_candidate_engine_uses_latest_daily_bar_amount_when_scan_amount_is_zero():
    item = _quote(
        "000001", "盘前候选", change=0, amount=0, turnover=0,
        volume_ratio=0, pe=20, pb=2, industry="银行",
    )
    item["price"] = 30
    provider = CandidateFixtureProvider([item], {"000001": _frame(growth=0.3)})

    result = StockCandidateEngine(provider).analyze()

    assert result["data_state"] == "complete"
    assert result["candidates"][0]["amount"] > 0
    assert result["candidates"][0]["amount_source"] == "latest_daily_bar_proxy"
    assert "liquidity_uses_latest_daily_bar_proxy" in result["limitations"]


def test_candidate_engine_applies_explicit_screening_profile_and_rules():
    items = [
        _quote("000001", "稳健成长", change=2.6, amount=2.2e9, turnover=4.2, volume_ratio=1.35, pe=18, pb=2.1, industry="银行"),
        _quote("000002", "高热题材", change=9.7, amount=3.6e9, turnover=24.0, volume_ratio=3.8, pe=160, pb=18, industry="电子"),
        _quote("000003", "低估震荡", change=0.3, amount=1.3e9, turnover=1.8, volume_ratio=0.8, pe=9, pb=0.9, industry="公用事业"),
    ]
    provider = CandidateFixtureProvider(items, {
        "000001": _frame(growth=0.65, noise=0.005, volume_boost=1.8),
        "000002": _frame(growth=0.9, noise=0.06, volume_boost=4.2),
        "000003": _frame(growth=0.08, noise=0.012),
    })

    result = StockCandidateEngine(provider).analyze(
        universe_size=30,
        output_size=10,
        bars=120,
        profile="trend",
        filters={
            "industries": ["银行", "电子"],
            "max_pe": 50,
            "min_momentum_20_pct": 5,
            "max_volatility_pct": 40,
            "required_signals": ["均线多头"],
        },
    )

    assert [row["symbol"] for row in result["candidates"]] == ["000001"]
    assert result["screening_model"]["profile"] == "trend"
    assert result["screening_model"]["filters"]["max_pe"] == 50.0
    assert result["screening_coverage"] == {
        "before_rules": 3,
        "after_market_rules": 1,
        "deep_pool_count": 1,
        "analyzed_count": 1,
        "after_market_technical_rules": 1,
        "after_rules": 1,
        "excluded_by_rules": 2,
        "fundamental_evaluated": 1,
        "not_fundamental_preselected": 0,
    }
    excluded = {item["symbol"]: item["reasons"] for item in result["excluded_by_rules"]}
    assert "pe_above_max" in excluded["000002"]
    assert "industry_not_selected" in excluded["000003"]
    assert result["candidates"][0]["screening_evidence"]["passed"] is True


def test_candidate_engine_applies_market_and_fundamental_advanced_filters():
    items = [
        _quote("000001", "高质成长", change=2.0, amount=2.0e9, turnover=4.0, volume_ratio=1.4, pe=20, pb=2.0, industry="电子"),
        _quote("000002", "低质成长", change=2.0, amount=2.0e9, turnover=4.0, volume_ratio=1.4, pe=20, pb=2.0, industry="电子"),
        _quote("000003", "高换手", change=2.0, amount=2.0e9, turnover=18.0, volume_ratio=3.5, pe=20, pb=2.0, industry="电子"),
    ]
    fundamentals = {
        "000001": _fundamental("000001"),
        "000002": _fundamental("000002"),
        "000003": _fundamental("000003"),
    }
    fundamentals["000002"]["comparisonProfile"]["metrics"].update({
        "roePct": 6.0,
        "revenueGrowthPct": 4.0,
        "netProfitGrowthPct": 2.0,
        "valuationPercentile": 85.0,
    })
    provider = CandidateFixtureProvider(
        items,
        {symbol: _frame(growth=0.4) for symbol in fundamentals},
        fundamentals,
    )

    result = StockCandidateEngine(provider).analyze(filters={
        "min_market_cap": 50_000_000_000,
        "max_market_cap": 100_000_000_000,
        "max_pb": 3,
        "min_turnover_pct": 1,
        "max_turnover_pct": 10,
        "min_volume_ratio": 1,
        "max_volume_ratio": 2,
        "min_roe_pct": 10,
        "min_revenue_growth_pct": 10,
        "min_net_profit_growth_pct": 10,
        "max_valuation_percentile": 70,
    })

    assert [row["symbol"] for row in result["candidates"]] == ["000001"]
    excluded = {item["symbol"]: item["reasons"] for item in result["excluded_by_rules"]}
    assert "roe_below_min" in excluded["000002"]
    assert "turnover_above_max" in excluded["000003"]
    assert result["screening_coverage"] == {
        "before_rules": 3,
        "after_market_rules": 2,
        "deep_pool_count": 2,
        "analyzed_count": 2,
        "after_market_technical_rules": 2,
        "after_rules": 1,
        "excluded_by_rules": 2,
        "fundamental_evaluated": 2,
        "not_fundamental_preselected": 0,
    }


def test_candidate_market_rules_filter_broad_pool_before_deep_selection():
    items = []
    frames = {}
    for index in range(35):
        symbol = f"60{index:04d}"
        item = _quote(
            symbol, f"样本{index}", change=1, amount=1e9, turnover=2,
            volume_ratio=1.2, pe=5 if index == 34 else 50, pb=2,
            industry="样本行业",
        )
        item.update({
            "scan_rank_score": 35 - index,
            "scan_memberships": ["pe:asc"] if index == 34 else ["marketCap:desc"],
            "scan_membership_scores": {"pe:asc": 1.0} if index == 34 else {"marketCap:desc": 1.0},
        })
        items.append(item)
        frames[symbol] = _frame(growth=0.4)
    provider = MultiMarketCandidateProvider(items, frames)

    result = StockCandidateEngine(provider).analyze(
        universe_size=30,
        output_size=10,
        filters={"max_pe": 10},
    )

    assert [row["symbol"] for row in result["candidates"]] == ["600034"]
    assert result["coverage"]["broad_eligible_count"] == 35
    assert result["coverage"]["market_prefilter_count"] == 1
    assert result["coverage"]["deep_pool_count"] == 1
    assert result["coverage"]["deep_pool_selection_basis"] == ["pe:asc"]
    assert result["coverage"]["technical_excluded_count"] == 0
    assert result["coverage"]["fundamental_excluded_count"] == 0
    assert all(
        row["stage"] == "market_prefilter"
        for row in result["excluded_by_rules"]
    )


def test_candidate_engine_does_not_treat_missing_fundamental_metric_as_passing():
    item = _quote("000001", "指标缺失", change=2.0, amount=2e9, turnover=4, volume_ratio=1.2, pe=20, pb=2, industry="电子")
    packet = _fundamental("000001")
    packet["comparisonProfile"]["metrics"].pop("roePct")
    provider = CandidateFixtureProvider([item], {"000001": _frame(growth=0.4)}, {"000001": packet})

    with pytest.raises(StockCandidateError, match="高级筛选条件没有匹配"):
        StockCandidateEngine(provider).analyze(filters={"min_roe_pct": 8})


@pytest.mark.parametrize(
    ("filters", "message"),
    [
        ({"min_market_cap": 200, "max_market_cap": 100}, "最低市值不能高于最高市值"),
        ({"min_turnover_pct": 10, "max_turnover_pct": 5}, "最低换手率不能高于最高换手率"),
        ({"min_volume_ratio": 3, "max_volume_ratio": 1}, "最低量比不能高于最高量比"),
        ({"max_valuation_percentile": 101}, "最高估值分位不能超过 100"),
    ],
)
def test_candidate_engine_rejects_conflicting_filter_ranges(filters, message):
    with pytest.raises(StockCandidateError, match=message):
        StockCandidateEngine._normalize_filters(filters)


def test_candidate_engine_attaches_event_evidence_without_changing_factor_score():
    get_analysis_snapshot_registry().clear()
    event_result = EventFlowEngine().analyze(_event_packet())
    items = [
        _quote("300502", "新易盛", change=2.6, amount=2.2e9, turnover=4.2, volume_ratio=1.35, pe=50, pb=8, industry="通信"),
        _quote("000001", "平安银行", change=0.6, amount=1.8e9, turnover=1.2, volume_ratio=1.0, pe=7, pb=0.8, industry="银行"),
    ]
    provider = CandidateFixtureProvider(items, {
        "300502": _frame(growth=0.65),
        "000001": _frame(growth=0.20),
    })

    baseline = StockCandidateEngine(provider).analyze()
    result = StockCandidateEngine(provider).analyze(
        event_flow_snapshot_id=event_result["snapshot"]["snapshot_id"]
    )

    assert [(row["symbol"], row["score"]) for row in result["candidates"]] == [
        (row["symbol"], row["score"]) for row in baseline["candidates"]
    ]
    event_candidate = next(row for row in result["candidates"] if row["symbol"] == "300502")
    assert [item["id"] for item in event_candidate["event_evidence"]["alerts"]] == ["flow-1", "risk-1"]
    assert result["event_flow"]["snapshot_id"] == event_result["snapshot"]["snapshot_id"]


class FailingScanProvider(MarketDataProvider):
    name = "fixture-failure"

    def get_stock_scan(self, *, sort="amount", order="desc", limit=50):
        raise MarketDataError("Desk market.scan unavailable")

    def get_kline(self, symbol, period="daily", limit=480, as_of=None):
        raise AssertionError("scan failure must stop before K-line loading")


class StockCandidateSnapshotHandlerTest(AsyncHTTPTestCase):
    def get_app(self):
        return tornado.web.Application([
            (r"/api/v1/stock-candidates/snapshots", StockCandidateSnapshotHandler),
        ])

    def setUp(self):
        get_analysis_snapshot_registry().clear()
        get_analysis_history_registry().clear()
        stock_candidates_handler._RESULT_CACHE.clear()
        stock_candidates_handler._INFLIGHT.clear()
        super().setUp()

    def tearDown(self):
        super().tearDown()
        get_analysis_snapshot_registry().clear()
        get_analysis_history_registry().clear()
        stock_candidates_handler._RESULT_CACHE.clear()
        stock_candidates_handler._INFLIGHT.clear()

    def test_get_returns_v1_contract_and_registers_snapshot(self):
        items = [
            _quote(
                "000001", "稳健成长", change=2.6, amount=2.2e9,
                turnover=4.2, volume_ratio=1.35, pe=18, pb=2.1, industry="银行",
            ),
        ]
        provider = CandidateFixtureProvider(items, {"000001": _frame(growth=0.65)})

        with patch.object(stock_candidates_handler, "get_market_data_provider", return_value=provider):
            response = self.fetch(
                "/api/v1/stock-candidates/snapshots?universeSize=30&outputSize=10&bars=120"
            )

        payload = json.loads(response.body)
        snapshot_id = payload["data"]["snapshot"]["snapshot_id"]
        assert response.code == 200
        assert payload["ok"] is True
        assert payload["meta"]["api_version"] == "1.0"
        assert payload["data"]["engine"]["name"] == "instock-stock-candidate-engine"
        assert payload["data"]["candidate_lifecycle"]["observation_count"] == 1
        assert payload["data"]["candidates"][0]["lifecycle"]["state"] == "new"
        assert get_analysis_snapshot_registry().get(snapshot_id)["snapshot_id"] == snapshot_id
        assert len(get_analysis_history_registry().list("stock-candidates")) == 1

    def test_get_reuses_identical_request_for_short_ttl(self):
        class CountingEngine:
            calls = 0

            def __init__(self, provider):
                self.provider = provider

            def analyze(self, **kwargs):
                type(self).calls += 1
                return StockCandidateEngine(self.provider).analyze(**kwargs)

        items = [
            _quote(
                "000001", "稳健成长", change=2.6, amount=2.2e9,
                turnover=4.2, volume_ratio=1.35, pe=18, pb=2.1, industry="银行",
            ),
        ]
        provider = CandidateFixtureProvider(items, {"000001": _frame(growth=0.65)})
        CountingEngine.calls = 0

        with (
            patch.object(stock_candidates_handler, "get_market_data_provider", return_value=provider),
            patch.object(stock_candidates_handler, "StockCandidateEngine", CountingEngine),
        ):
            first = self.fetch("/api/v1/stock-candidates/snapshots")
            second = self.fetch("/api/v1/stock-candidates/snapshots")

        assert first.code == 200
        assert second.code == 200
        assert CountingEngine.calls == 1
        assert len(get_analysis_history_registry().list("stock-candidates")) == 1
        assert stock_candidates_handler.stock_candidate_runtime_stats()["inflight"] == 0

    def test_get_rejects_invalid_parameters(self):
        response = self.fetch(
            "/api/v1/stock-candidates/snapshots?universeSize=all",
            raise_error=False,
        )
        payload = json.loads(response.body)

        assert response.code == 400
        assert payload["error"]["code"] == "invalid_parameters"

    def test_get_accepts_screening_query_parameters(self):
        items = [
            _quote(
                "000001", "稳健成长", change=2.6, amount=2.2e9,
                turnover=4.2, volume_ratio=1.35, pe=18, pb=2.1, industry="银行",
            ),
        ]
        provider = CandidateFixtureProvider(items, {"000001": _frame(growth=0.65)})
        with patch.object(stock_candidates_handler, "get_market_data_provider", return_value=provider):
            response = self.fetch(
                "/api/v1/stock-candidates/snapshots?profile=trend&industries=%E9%93%B6%E8%A1%8C&minMarketCap=50000000000&maxMarketCap=100000000000&maxPE=30&maxPB=3&minTurnover=1&maxTurnover=10&minVolumeRatio=1&maxVolumeRatio=2&minMomentum20=5&maxVolatility=40&minROE=10&minRevenueGrowth=10&minNetProfitGrowth=10&maxValuationPercentile=70&requiredSignals=%E5%9D%87%E7%BA%BF%E5%A4%9A%E5%A4%B4"
            )
        payload = json.loads(response.body)
        assert response.code == 200
        assert payload["data"]["screening_model"]["profile"] == "trend"
        assert payload["data"]["screening_model"]["filters"]["min_roe_pct"] == 10.0
        assert payload["data"]["screening_coverage"]["after_rules"] == 1

    def test_get_accepts_event_flow_snapshot_reference(self):
        event_result = EventFlowEngine().analyze(_event_packet())
        event_snapshot_id = event_result["snapshot"]["snapshot_id"]
        items = [
            _quote("300502", "新易盛", change=2.6, amount=2.2e9, turnover=4.2, volume_ratio=1.35, pe=50, pb=8, industry="通信"),
        ]
        provider = CandidateFixtureProvider(items, {"300502": _frame(growth=0.65)})
        with patch.object(stock_candidates_handler, "get_market_data_provider", return_value=provider):
            response = self.fetch(
                "/api/v1/stock-candidates/snapshots"
                f"?eventFlowSnapshotId={event_snapshot_id}"
            )
        payload = json.loads(response.body)

        assert response.code == 200
        assert payload["data"]["event_flow"]["snapshot_id"] == event_snapshot_id

    def test_get_maps_desk_data_failure_to_502(self):
        with patch.object(
            stock_candidates_handler,
            "get_market_data_provider",
            return_value=FailingScanProvider(),
        ):
            response = self.fetch(
                "/api/v1/stock-candidates/snapshots",
                raise_error=False,
            )
        payload = json.loads(response.body)

        assert response.code == 502
        assert payload["error"] == {
            "code": "market_data_unavailable",
            "message": "Desk market.scan unavailable",
        }
