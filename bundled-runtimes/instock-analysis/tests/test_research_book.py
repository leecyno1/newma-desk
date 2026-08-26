from __future__ import annotations

import json

import pytest
import tornado.web
from tornado.testing import AsyncHTTPTestCase

from instock.core.analysis_snapshot import get_analysis_snapshot_registry
from instock.core.research.research_book import ResearchBookEngine, ResearchBookError
from instock.web.research_book_handler import ResearchBookHandler


def _register_fixture_snapshot(snapshot_id="instock-stock-research-dossier:fixture"):
    get_analysis_snapshot_registry().register({
        "schema_version": "1.0",
        "snapshot_id": snapshot_id,
        "generated_at": "2026-08-11T10:00:00+08:00",
        "analysis": {"name": "instock-stock-research-dossier", "version": "1.0.0"},
        "parameters": {}, "data_window": {"coverage": "complete"},
        "provenance": {}, "freshness": {"state": "current"},
        "input": {"digest": "sha256:fixture", "summary": {}},
        "result": {"digest": "sha256:fixture", "summary": {"symbol": "300502"}},
    })


def _packet():
    return {
        "schema_version": "instock-research-book-packet-v1",
        "name": "核心观察组合",
        "as_of": "2026-08-11",
        "items": [
            {
                "symbol": "300502", "name": "新易盛", "market": "CN",
                "sector": "通信", "target_weight_pct": 25,
                "thesis": "高速光模块需求与交付能力需持续核验",
                "invalidation": ["订单增速显著低于预期", "现金转化持续恶化"],
                "risk_tags": ["高估值", "客户集中"],
                "snapshot_ids": ["instock-stock-research-dossier:fixture"],
            },
            {
                "symbol": "000001", "name": "平安银行", "market": "CN",
                "sector": "银行", "target_weight_pct": 15,
                "thesis": "资产质量和息差企稳仍需跟踪",
                "invalidation": ["不良率持续抬升"],
                "risk_tags": ["宏观信用"],
                "snapshot_ids": ["missing:snapshot"],
            },
        ],
    }


def test_research_book_resolves_snapshots_and_aggregates_exposure_and_risk():
    registry = get_analysis_snapshot_registry()
    registry.clear()
    _register_fixture_snapshot()

    result = ResearchBookEngine().analyze(_packet())

    assert result["engine"]["name"] == "instock-research-book"
    assert result["summary"] == {
        "items": 2,
        "total_target_weight_pct": 40.0,
        "cash_weight_pct": 60.0,
        "resolved_snapshots": 1,
        "missing_snapshots": 1,
        "data_state": "partial",
    }
    assert result["exposures"]["sectors"] == [
        {"name": "通信", "weight_pct": 25.0},
        {"name": "银行", "weight_pct": 15.0},
    ]
    assert result["exposures"]["risks"][0] == {"name": "客户集中", "weight_pct": 25.0}
    assert result["items"][0]["snapshot_coverage"] == "complete"
    assert result["items"][1]["snapshot_coverage"] == "missing"
    assert "position_concentration:300502" in result["warnings"]
    assert result["snapshot"]["snapshot_id"].startswith("instock-research-book:")


def test_research_book_rejects_overallocated_or_thesis_free_items():
    packet = _packet()
    packet["items"][0]["target_weight_pct"] = 90
    packet["items"][1]["target_weight_pct"] = 20
    with pytest.raises(ResearchBookError, match="总目标权重不能超过 100"):
        ResearchBookEngine().analyze(packet)

    packet = _packet()
    packet["items"][0]["thesis"] = ""
    with pytest.raises(ResearchBookError, match="thesis 不能为空"):
        ResearchBookEngine().analyze(packet)


class ResearchBookHandlerTest(AsyncHTTPTestCase):
    def get_app(self):
        return tornado.web.Application([(r"/api/v1/research-books", ResearchBookHandler)])

    def test_post_returns_research_book(self):
        get_analysis_snapshot_registry().clear()
        _register_fixture_snapshot()
        response = self.fetch(
            "/api/v1/research-books", method="POST",
            headers={"Content-Type": "application/json"}, body=json.dumps(_packet()),
        )
        payload = json.loads(response.body)
        assert response.code == 200
        assert payload["ok"] is True
        assert payload["data"]["summary"]["items"] == 2

    def test_post_rejects_invalid_json(self):
        response = self.fetch("/api/v1/research-books", method="POST", body="{broken", raise_error=False)
        assert response.code == 400
        assert json.loads(response.body)["error"]["code"] == "invalid_json"
