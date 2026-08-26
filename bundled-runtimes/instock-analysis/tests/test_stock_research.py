from __future__ import annotations

import json
from unittest.mock import patch

import pytest
import tornado.web
from tornado.testing import AsyncHTTPTestCase

from instock.core.analysis_snapshot import get_analysis_snapshot_registry
from instock.core.market_data_provider import MarketDataError
from instock.core.research.stock_dossier import StockResearchDossier, StockResearchError
from instock.core.research.event_flow import EventFlowEngine
from instock.web import stock_research_handler
from instock.web.stock_research_handler import StockResearchDossierHandler


class ResearchFixtureProvider:
    name = "fixture-desk"

    def get_equity_snapshot(self, symbol, *, refresh=False):
        return {
            "schemaVersion": "newma-dock.equity-research.v1",
            "identity": {"symbol": symbol, "name": "新易盛", "market": "CN", "currency": "CNY"},
            "coverage": {"coveredDimensions": 5, "totalDimensions": 6, "ratio": 0.8333},
            "scorecard": [
                {"id": "quality", "title": "盈利质量", "score": 60.8, "status": "balanced", "summary": "中性"},
                {"id": "growth", "title": "增长动能", "score": 95.0, "status": "strong", "summary": "增长较强"},
                {"id": "valuation", "title": "估值位置", "score": 27.1, "status": "weak", "summary": "估值承压"},
            ],
            "comparisonProfile": {
                "metrics": {
                    "pe": 53.92,
                    "pb": 29.83,
                    "revenueGrowthPct": 105.76,
                    "netProfitGrowthPct": 76.8,
                    "roePct": 14.52,
                    "cashConversionPct": 24.64,
                }
            },
            "workflow": {"dataQuality": {"score": 72, "level": "usable", "limitations": ["缺少 ROIC"]}},
            "evidenceLedger": [
                {"id": "valuation.pe_ttm", "dimension": "valuation", "label": "PE(TTM)", "value": 53.92, "unit": "x", "source": "fixture", "asOf": "2026-08-11", "confidence": "high"},
                {"id": "growth.revenue_yoy", "dimension": "growth", "label": "营收同比", "value": 105.76, "unit": "%", "source": "fixture", "asOf": "2026-03-31", "confidence": "high"},
            ],
            "gaps": ["标准 ROA/ROIC 证据尚不完整"],
            "generatedAt": "2026-08-11T18:00:00+08:00",
        }

    def get_security_announcements(self, symbol):
        return [{"date": "2026-07-20", "title": "投资者关系活动记录", "type": "调研活动", "url": "https://example.test/a"}]

    def get_security_reports(self, symbol, pages=1):
        return [{"publishDate": "2026-07-26 00:00:00", "title": "订单交付快速增长", "orgSName": "测试证券", "emRatingName": "买入", "pdfUrl": "https://example.test/r.pdf"}]

    def get_security_news(self, symbol, limit=10):
        return [{"发布时间": "2026-07-28 16:25:55", "新闻标题": "龙虎榜数据", "文章来源": "测试数据", "新闻链接": "https://example.test/n"}]


def fake_czsc_runner(provider, *, symbol, period, bars, as_of=None, include_chart=False):
    return {
        "symbol": symbol,
        "period": period,
        "end_date": "2026-08-11",
        "engine": {"name": "czsc", "version": "0.10.12", "analysis_version": "2.2.0"},
        "summary": {"trend": "up", "signal": "多头结构"},
        "evidence": {"structure_stability": {"state": "stable"}, "latest_structure_change": {"type": "none"}},
        "structure": {"bi_count": 8, "latest_direction": "up"},
        "insight": {"headline": "结构偏强", "bias": "bullish"},
        "cost_distribution": {
            "state": "available",
            "label": "成交成本分布代理",
            "average_cost": 120.5,
            "profit_volume_pct": 64.2,
            "profile": [{"price": 120.0, "volume_share_pct": 18.0}],
        },
        "chart": {"xAxis": [], "yAxis": [], "series": []},
        "snapshot": {"snapshot_id": "czsc:fixture", "schema_version": "1.0"},
        "data_state": "complete",
        "conclusion_state": "formed",
        "actual_bars": bars,
        "minimum_direction_bars": 80,
        "limitations": [],
    }


def fake_short_czsc_runner(provider, *, symbol, period, bars, as_of=None, include_chart=False):
    payload = fake_czsc_runner(
        provider, symbol=symbol, period=period, bars=bars,
        as_of=as_of, include_chart=include_chart,
    )
    payload.update({
        "data_state": "partial",
        "conclusion_state": "insufficient_history",
        "actual_bars": 44,
        "limitations": ["insufficient_history_for_directional_conclusion"],
    })
    payload["insight"] = {
        "headline": "仅 44 根 K 线，结构置信度不足，不形成方向结论",
        "bias": "unknown",
        "conclusion_state": "insufficient_history",
    }
    return payload


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


def _register_industry_chain_snapshot():
    snapshot_id = "instock-industry-chain-research:fixture"
    get_analysis_snapshot_registry().register({
        "schema_version": "1.0",
        "snapshot_id": snapshot_id,
        "generated_at": "2026-08-11T10:00:00+08:00",
        "analysis": {"name": "instock-industry-chain-research", "version": "2.0.0"},
        "parameters": {},
        "data_window": {"end_date": "2026-08-11", "coverage": "complete"},
        "provenance": {},
        "freshness": {"state": "current"},
        "input": {"digest": "sha256:fixture", "summary": {}},
        "result": {
            "digest": "sha256:fixture",
            "summary": {"theme": "AI 光通信扩产瓶颈", "top_candidate": "300502.SZ"},
            "evidence": {
                "candidates": [{
                    "symbol": "300502.SZ",
                    "name": "新易盛",
                    "layer_id": "optical-engine",
                    "priority_score": 82.5,
                    "research_priority": "top_priority",
                    "confidence": "high",
                    "invalidation": ["替代供应商完成批量认证"],
                }],
                "layers": [{"id": "optical-engine", "name": "光引擎与关键器件", "rank": 1}],
            },
        },
    })
    return snapshot_id


def test_stock_research_dossier_combines_technical_financial_and_disclosure_evidence():
    registry = get_analysis_snapshot_registry()
    registry.clear()

    result = StockResearchDossier(
        ResearchFixtureProvider(), czsc_runner=fake_czsc_runner
    ).analyze(symbol="300502", period="daily", bars=240)

    assert result["engine"] == {
        "name": "instock-stock-research-dossier",
        "version": "1.2.0",
        "model": "instock-stock-research-dossier-v1.2",
    }
    assert result["identity"]["name"] == "新易盛"
    assert result["technical"]["insight"]["headline"] == "结构偏强"
    assert result["technical"]["cost_distribution"]["average_cost"] == 120.5
    assert result["fundamentals"]["metrics"]["revenueGrowthPct"] == 105.76
    assert result["fundamentals"]["scorecard"][1]["status"] == "strong"
    assert result["disclosures"]["coverage"] == {
        "announcements": 1,
        "reports": 1,
        "news": 1,
    }
    assert result["assessment"]["strengths"] == [
        "基本面：增长动能",
        "技术结构：结构偏强",
    ]
    assert result["assessment"]["tensions"] == ["基本面：估值位置"]
    assert result["assessment"]["invalidation_conditions"] == [
        "基本面：增长动能由强转弱，且连续两个报告期未恢复",
        "技术结构：CZSC 偏强结构失效并转为明确偏弱",
    ]
    assert result["assessment"]["evidence_balance"] == {
        "strength_count": 2,
        "tension_count": 1,
        "gap_count": 1,
        "event_count": 0,
        "industry_chain_attached": False,
    }
    assert result["data_state"] == "complete"
    assert result["snapshot"]["snapshot_id"].startswith("instock-stock-research-dossier:")
    assert registry.get(result["snapshot"]["snapshot_id"])["analysis"]["name"] == "instock-stock-research-dossier"


def test_stock_research_dossier_keeps_partial_result_when_optional_news_fails():
    class PartialProvider(ResearchFixtureProvider):
        def get_security_news(self, symbol, limit=10):
            raise MarketDataError("news unavailable")

    result = StockResearchDossier(
        PartialProvider(), czsc_runner=fake_czsc_runner
    ).analyze(symbol="300502", period="daily", bars=240)

    assert result["data_state"] == "partial"
    assert result["disclosures"]["coverage"]["news"] == 0
    assert result["failures"] == [{"capability": "market.news", "error": "news unavailable"}]
    assert "market.news_unavailable" in result["limitations"]


def test_stock_research_marks_short_czsc_history_as_partial_and_suppresses_direction():
    result = StockResearchDossier(
        ResearchFixtureProvider(), czsc_runner=fake_short_czsc_runner
    ).analyze(symbol="300502", period="daily", bars=480)

    assert result["data_state"] == "partial"
    assert result["technical"]["conclusion_state"] == "insufficient_history"
    assert result["assessment"]["technical_bias"] == "unknown"
    assert result["assessment"]["conclusion"] == (
        "技术历史不足，当前只保留结构事实，不形成综合方向判断"
    )
    assert any("仅 44 根 K 线" in item for item in result["assessment"]["gaps"])
    assert "insufficient_history_for_directional_conclusion" in result["limitations"]


def test_stock_research_dossier_rejects_invalid_symbol():
    with pytest.raises(StockResearchError, match="6 位 A 股代码"):
        StockResearchDossier(
            ResearchFixtureProvider(), czsc_runner=fake_czsc_runner
        ).analyze(symbol="AAPL", period="daily", bars=240)


def test_stock_research_dossier_reuses_symbol_event_flow_evidence():
    registry = get_analysis_snapshot_registry()
    registry.clear()
    event_result = EventFlowEngine().analyze(_event_packet())

    result = StockResearchDossier(
        ResearchFixtureProvider(), czsc_runner=fake_czsc_runner
    ).analyze(
        symbol="300502",
        period="daily",
        bars=240,
        event_flow_snapshot_id=event_result["snapshot"]["snapshot_id"],
    )

    assert result["event_flow"]["snapshot_id"] == event_result["snapshot"]["snapshot_id"]
    assert [item["id"] for item in result["event_flow"]["alerts"]] == ["flow-1", "risk-1"]
    assert result["event_flow"]["symbol_summary"]["symbol"] == "300502"
    assert result["snapshot"]["input"]["summary"]["event_flow_snapshot_id"] == event_result["snapshot"]["snapshot_id"]
    assert "事件证据：主力资金净流入" in result["assessment"]["strengths"]
    assert "事件风险：股东减持计划" in result["assessment"]["tensions"]


def test_stock_research_historical_mode_removes_forward_looking_evidence():
    result = StockResearchDossier(
        ResearchFixtureProvider(), czsc_runner=fake_czsc_runner
    ).analyze(
        symbol="300502",
        period="daily",
        bars=240,
        as_of="2026-06-30",
    )

    assert result["as_of"] == "2026-06-30"
    assert result["data_state"] == "partial"
    assert result["fundamentals"]["mode"] == "historical_evidence_only"
    assert "pe" not in result["fundamentals"]["metrics"]
    assert result["fundamentals"]["metrics"]["revenueGrowthPct"] == 105.76
    assert result["fundamentals"]["scorecard"] == []
    assert result["disclosures"]["announcements"] == []
    assert result["disclosures"]["reports"] == []
    assert result["disclosures"]["news"] == []
    assert result["disclosures"]["excluded_after_as_of"] == {
        "announcements": 1,
        "reports": 1,
        "news": 1,
    }
    assert "historical_equity_snapshot_unavailable" in result["limitations"]
    assert "historical_disclosures_client_filtered_from_latest_desk_window" in result["limitations"]
    assert result["snapshot"]["freshness"]["state"] == "historical"
    assert result["snapshot"]["freshness"]["resolution"] == "partial_point_in_time"


def test_stock_research_historical_event_snapshot_replays_to_requested_date():
    registry = get_analysis_snapshot_registry()
    registry.clear()
    event_result = EventFlowEngine().analyze(_event_packet())

    result = StockResearchDossier(
        ResearchFixtureProvider(), czsc_runner=fake_czsc_runner
    ).analyze(
        symbol="300502",
        as_of="2026-08-09",
        event_flow_snapshot_id=event_result["snapshot"]["snapshot_id"],
    )

    assert result["event_flow"]["as_of"] == "2026-08-09"
    assert result["event_flow"]["as_of_mode"] == "historical_replay"
    assert [item["id"] for item in result["event_flow"]["alerts"]] == ["risk-1"]
    assert result["event_flow"]["alerts"][0]["age_days"] == 0
    assert result["event_flow"]["summary"]["deduplicated_events"] == 1
    assert result["event_flow"]["summary"]["top_event_id"] == "risk-1"
    assert result["event_flow"]["freshness"]["resolution"] == "point_in_time_replay"


def test_stock_research_rejects_industry_chain_snapshot_after_historical_cutoff():
    get_analysis_snapshot_registry().clear()
    snapshot_id = _register_industry_chain_snapshot()

    result = StockResearchDossier(
        ResearchFixtureProvider(), czsc_runner=fake_czsc_runner
    ).analyze(
        symbol="300502",
        as_of="2026-06-30",
        industry_chain_snapshot_id=snapshot_id,
    )

    assert result["industry_chain"] is None
    assert "industry_chain_snapshot_after_research_as_of" in result["limitations"]


def test_stock_research_dossier_resolves_security_industry_chain_exposure():
    get_analysis_snapshot_registry().clear()
    snapshot_id = _register_industry_chain_snapshot()

    result = StockResearchDossier(
        ResearchFixtureProvider(), czsc_runner=fake_czsc_runner
    ).analyze(
        symbol="300502",
        industry_chain_snapshot_id=snapshot_id,
    )

    assert result["industry_chain"]["snapshot_id"] == snapshot_id
    assert result["industry_chain"]["exposure"]["symbol"] == "300502.SZ"
    assert result["industry_chain"]["exposure"]["layer"]["name"] == "光引擎与关键器件"
    assert "产业链：光引擎与关键器件暴露已核验（high 置信）" in result["assessment"]["strengths"]
    assert "产业链证伪：替代供应商完成批量认证" in result["assessment"]["tensions"]


class FixtureHandlerDossier:
    def __init__(self, provider):
        self.provider = provider

    def analyze(self, **parameters):
        return StockResearchDossier(
            ResearchFixtureProvider(), czsc_runner=fake_czsc_runner
        ).analyze(**parameters)


class StockResearchDossierHandlerTest(AsyncHTTPTestCase):
    def get_app(self):
        return tornado.web.Application([
            (r"/api/v1/stock-research/dossiers", StockResearchDossierHandler),
        ])

    def setUp(self):
        get_analysis_snapshot_registry().clear()
        self.provider_patch = patch.object(
            stock_research_handler,
            "get_market_data_provider",
            return_value=ResearchFixtureProvider(),
        )
        self.engine_patch = patch.object(
            stock_research_handler,
            "StockResearchDossier",
            FixtureHandlerDossier,
        )
        self.provider_patch.start()
        self.engine_patch.start()
        super().setUp()

    def tearDown(self):
        super().tearDown()
        self.engine_patch.stop()
        self.provider_patch.stop()
        get_analysis_snapshot_registry().clear()

    def test_get_returns_dossier_and_v1_contract(self):
        response = self.fetch(
            "/api/v1/stock-research/dossiers?symbol=300502&period=daily&bars=240"
        )
        payload = json.loads(response.body)

        assert response.code == 200
        assert payload["ok"] is True
        assert payload["meta"]["api_version"] == "1.0"
        assert payload["data"]["identity"]["symbol"] == "300502"
        snapshot_id = payload["data"]["snapshot"]["snapshot_id"]
        assert get_analysis_snapshot_registry().get(snapshot_id) is not None

    def test_get_accepts_event_flow_snapshot_reference(self):
        event_result = EventFlowEngine().analyze(_event_packet())
        event_snapshot_id = event_result["snapshot"]["snapshot_id"]
        response = self.fetch(
            "/api/v1/stock-research/dossiers?symbol=300502&period=daily&bars=240"
            f"&eventFlowSnapshotId={event_snapshot_id}"
        )
        payload = json.loads(response.body)

        assert response.code == 200
        assert payload["data"]["event_flow"]["snapshot_id"] == event_snapshot_id

    def test_get_rejects_non_integer_bars(self):
        response = self.fetch(
            "/api/v1/stock-research/dossiers?symbol=300502&bars=all",
            raise_error=False,
        )
        payload = json.loads(response.body)

        assert response.code == 400
        assert payload["error"]["code"] == "invalid_parameters"
