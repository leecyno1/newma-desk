from __future__ import annotations

import json
from unittest.mock import patch

import pytest
import tornado.web
from tornado.testing import AsyncHTTPTestCase

from instock.core.analysis_snapshot import get_analysis_snapshot_registry
from instock.core.research.event_flow import EventFlowEngine, EventFlowError
from instock.web.event_flow_handler import EventFlowHandler


class DeskEventProvider:
    def get_security_event_flow(self, symbol):
        return {
            "sources": {
                "fund_flow": {
                    "id": "fund_flow", "label": "主力资金", "state": "available",
                    "endpoint": "/api/research/api/fund-flow", "units": {"main_net": "元"},
                    "records": 6,
                    "data": [
                        {"date": f"2026-08-{day:02d}", "main_net": value}
                        for day, value in zip(range(10, 4, -1), [2e8, 1e8, -5e7, 8e7, 6e7, -2e7])
                    ],
                },
                "margin": {
                    "id": "margin", "label": "融资融券", "state": "available",
                    "endpoint": "/api/research/api/margin", "units": {"rzye": "元"},
                    "records": 5,
                    "data": [
                        {"date": f"2026-08-{day:02d}", "rzye": 19e9, "rzmre": 2e9, "rzche": 1.5e9, "rqye": 8e7}
                        for day in range(10, 5, -1)
                    ],
                },
                "dragon_tiger": {
                    "id": "dragon_tiger", "label": "龙虎榜", "state": "available",
                    "endpoint": "/api/research/api/dragon-tiger", "units": {"net_buy": "万元"},
                    "records": 1,
                    "data": {
                        "records": [{"date": "2026-07-28", "reason": "日跌幅达到15%", "net_buy": 192753.5, "turnover": 6.16}],
                        "institution": {"net_amt": 210775.1},
                    },
                },
                "block_trade": {
                    "id": "block_trade", "label": "大宗交易", "state": "empty",
                    "endpoint": "/api/research/api/block-trade", "units": {"amount": "元"},
                    "records": 0, "data": [],
                },
                "holders": {
                    "id": "holders", "label": "股东户数", "state": "available",
                    "endpoint": "/api/research/api/holders", "units": {"holder_num": "户"},
                    "records": 1,
                    "data": [{"date": "2026-03-31", "holder_num": 155489, "change_ratio": 11.48, "avg_shares": 0}],
                },
                "dividend": {
                    "id": "dividend", "label": "分红送转", "state": "available",
                    "endpoint": "/api/research/api/dividend", "units": {"bonus_rmb": "元/每10股"},
                    "records": 1,
                    "data": [{"date": "2026-06-11", "bonus_rmb": 10, "transfer_ratio": 0, "bonus_ratio": 0, "plan": "实施分配"}],
                },
                "lockup": {
                    "id": "lockup", "label": "限售解禁", "state": "available",
                    "endpoint": "/api/research/api/lockup", "units": {"able_shares": "万股"},
                    "records": 1,
                    "data": {"history": [{"date": "2025-06-13", "type": "股权激励限售股份", "able_shares": 153.4, "ratio": 0.0017}], "upcoming": []},
                },
            },
            "failures": [],
        }

    def get_security_announcements(self, symbol):
        return [{"date": "2026-07-20", "title": "2026年半年度业绩预告", "type": "业绩预告", "url": "https://example.test/a"}]

    def get_security_reports(self, symbol, pages=1):
        return [{"publishDate": "2026-07-26", "title": "公司事件点评", "orgSName": "研究机构", "emRatingName": "买入", "pdfUrl": "https://example.test/r.pdf"}]

    def get_security_news(self, symbol, limit=10):
        return [{"发布时间": "2026-08-11 09:30:00", "新闻标题": "资金数据更新", "文章来源": "公开媒体", "新闻链接": "https://example.test/n"}]


def _packet():
    return {
        "schema_version": "instock-event-flow-packet-v1",
        "as_of": "2026-08-11",
        "market": "CN",
        "events": [
            {
                "id": "flow-1", "type": "fund_flow", "symbol": "300502",
                "occurred_at": "2026-08-10", "title": "主力资金净流入",
                "direction": "positive", "magnitude_score": 80,
                "evidence_strength": "strong", "source_ref": "desk://flow/300502/20260810",
            },
            {
                "id": "flow-duplicate", "type": "fund_flow", "symbol": "300502",
                "occurred_at": "2026-08-10", "title": "主力资金净流入重复记录",
                "direction": "positive", "magnitude_score": 40,
                "evidence_strength": "medium", "source_ref": "desk://flow/300502/20260810",
            },
            {
                "id": "risk-1", "type": "announcement", "symbol": "300502",
                "occurred_at": "2026-08-09", "title": "股东减持计划",
                "direction": "negative", "magnitude_score": 70,
                "evidence_strength": "medium", "source_ref": "desk://announcement/300502/risk-1",
            },
            {
                "id": "report-1", "type": "report", "symbol": "000001",
                "occurred_at": "2026-06-01", "title": "行业跟踪报告",
                "direction": "neutral", "magnitude_score": 50,
                "evidence_strength": "weak", "source_ref": "desk://report/000001/1",
            },
        ],
    }


def test_event_flow_deduplicates_scores_freshness_and_groups_symbols():
    get_analysis_snapshot_registry().clear()
    result = EventFlowEngine().analyze(_packet())

    assert result["engine"]["name"] == "instock-event-flow"
    assert result["summary"] == {
        "input_events": 4,
        "deduplicated_events": 3,
        "duplicates_removed": 1,
        "fresh_events": 2,
        "stale_events": 1,
        "symbols": 2,
        "top_event_id": "flow-1",
    }
    assert result["alerts"][0]["id"] == "flow-1"
    assert result["alerts"][0]["freshness"] == "fresh"
    assert result["alerts"][-1]["freshness"] == "stale"
    stock = next(item for item in result["symbol_summary"] if item["symbol"] == "300502")
    assert stock["positive_events"] == 1
    assert stock["negative_events"] == 1
    assert stock["top_event_id"] == "flow-1"
    assert result["snapshot"]["snapshot_id"].startswith("instock-event-flow:")
    assert result["snapshot"]["result"]["evidence"]["alerts"][0]["id"] == "flow-1"
    assert get_analysis_snapshot_registry().get(result["snapshot"]["snapshot_id"]) is not None


def test_event_flow_orders_equal_intensity_by_latest_date():
    packet = _packet()
    packet["events"] = [
        {
            "id": "older", "type": "report", "symbol": "300502",
            "occurred_at": "2026-06-01", "title": "较早事件",
            "direction": "neutral", "magnitude_score": 50,
            "evidence_strength": "medium", "source_ref": "desk://report/older",
        },
        {
            "id": "newer", "type": "report", "symbol": "300502",
            "occurred_at": "2026-07-01", "title": "较新事件",
            "direction": "neutral", "magnitude_score": 50,
            "evidence_strength": "medium", "source_ref": "desk://report/newer",
        },
    ]

    result = EventFlowEngine().analyze(packet)

    assert [item["id"] for item in result["alerts"]] == ["newer", "older"]


def test_event_flow_rejects_future_or_unknown_event_types():
    packet = _packet()
    packet["events"][0]["occurred_at"] = "2026-08-12"
    with pytest.raises(EventFlowError, match="晚于 as_of"):
        EventFlowEngine().analyze(packet)

    packet = _packet()
    packet["events"][0]["type"] = "social_rumor"
    with pytest.raises(EventFlowError, match="事件类型"):
        EventFlowEngine().analyze(packet)


def test_event_flow_symbol_mode_collects_real_desk_source_shapes():
    result = EventFlowEngine().analyze_symbol(
        "300502.SZ", as_of="2026-08-11", provider=DeskEventProvider()
    )

    assert result["input_mode"] == "desk_symbol"
    assert result["query"] == {"symbol": "300502"}
    assert result["data_source"] == "newma-desk-research"
    assert result["coverage"]["requested_sources"] == 10
    assert result["coverage"]["empty_sources"] == 1
    assert result["coverage"]["failed_sources"] == 0
    assert {"announcement", "report", "news", "fund_flow", "margin", "dragon_tiger", "holder_change", "dividend", "lockup"}.issubset(
        {item["type"] for item in result["alerts"]}
    )
    fund_flow = next(item for item in result["alerts"] if item["type"] == "fund_flow")
    assert fund_flow["details"]["main_net_5d_cny"] == 390_000_000
    assert result["snapshot"]["provenance"]["provider"] == "newma-desk"


class EventFlowHandlerTest(AsyncHTTPTestCase):
    def get_app(self):
        return tornado.web.Application([(r"/api/v1/event-flows", EventFlowHandler)])

    def test_post_returns_event_radar(self):
        response = self.fetch(
            "/api/v1/event-flows",
            method="POST",
            headers={"Content-Type": "application/json"},
            body=json.dumps(_packet()),
        )
        payload = json.loads(response.body)
        assert response.code == 200
        assert payload["ok"] is True
        assert payload["data"]["summary"]["duplicates_removed"] == 1

    def test_post_accepts_symbol_query_mode(self):
        with patch(
            "instock.core.research.event_flow.get_market_data_provider",
            return_value=DeskEventProvider(),
        ):
            response = self.fetch(
                "/api/v1/event-flows",
                method="POST",
                headers={"Content-Type": "application/json"},
                body=json.dumps({"symbol": "300502", "asOf": "2026-08-11"}),
            )
        payload = json.loads(response.body)
        assert response.code == 200
        assert payload["data"]["input_mode"] == "desk_symbol"
        assert payload["data"]["coverage"]["requested_sources"] == 10

    def test_post_rejects_invalid_json(self):
        response = self.fetch(
            "/api/v1/event-flows", method="POST", body="{broken", raise_error=False
        )
        assert response.code == 400
        assert json.loads(response.body)["error"]["code"] == "invalid_json"
