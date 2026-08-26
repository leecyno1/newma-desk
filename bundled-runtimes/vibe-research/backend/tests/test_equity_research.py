from __future__ import annotations

import equity_research
from fastapi.testclient import TestClient


def test_cn_adapter_builds_common_framework_and_evidence_ledger():
    adapter = equity_research.ChinaEquityResearchAdapter(
        valuation_loader=lambda symbol: {
            "code": symbol,
            "name": "示例公司",
            "price": 100,
            "mcap_yi": 500,
            "pe_ttm": 20,
            "pb": 3,
            "pe_26e": 16,
            "analyst_count": 12,
        },
        financial_loader=lambda symbol: {
            "period": "2026-06-30",
            "revenue": 1000,
            "revenue_yoy": 18,
            "net_profit": 120,
            "net_profit_yoy": 22,
            "roe": 14,
            "gross_margin": 35,
            "net_margin": 12,
            "op_cf_ps": 2.4,
        },
        percentile_loader=lambda symbol: {
            "period": "近5年",
            "metrics": {
                "pe_ttm": {"percentile": 42},
                "pb": {"percentile": 55},
            },
        },
    )
    service = equity_research.EquityResearchService([adapter])

    snapshot = service.snapshot("600000")

    assert snapshot["identity"] == {
        "symbol": "600000",
        "name": "示例公司",
        "market": "CN",
        "currency": "CNY",
    }
    assert snapshot["schemaVersion"] == "newma-dock.equity-research.v1"
    assert snapshot["methodology"] == [
        "cross-market-normalization",
        "evidence-ledger",
        "source-provenance",
        "explicit-data-gaps",
        "research-workflow",
        "data-quality-diagnostics",
    ]
    evidence = {item["id"]: item for item in snapshot["evidenceLedger"]}
    assert evidence["valuation.pe_ttm"]["source"] == "Tencent quote / THS consensus"
    assert evidence["growth.revenue_yoy"]["asOf"] == "2026-06-30"
    assert evidence["cash_flow.op_cf_ps"]["unit"] == "CNY/share"
    sections = {item["id"]: item for item in snapshot["sections"]}
    assert sections["valuation"]["status"] == "covered"
    assert sections["cash_flow"]["status"] == "covered"
    assert sections["balance_sheet"]["status"] == "gap"
    assert sections["disclosure"]["status"] == "gap"
    workflow = snapshot["workflow"]
    assert workflow["schemaVersion"] == "newma-desk.research-workflow.v1"
    assert workflow["task"]["status"] == "partial"
    assert workflow["task"]["progress"] == 1
    assert workflow["dataQuality"]["blockScores"]["valuation"] > 0
    blocks = {item["id"]: item for item in workflow["blocks"]}
    assert blocks["valuation"]["status"] == "available"
    assert blocks["balance_sheet"]["status"] == "missing"
    assert workflow["history"] == {
        "mode": "desk-managed",
        "namespace": "research-history",
        "state": "pending",
        "lastGoodAt": None,
    }


def test_global_adapter_reuses_same_dimensions_without_requiring_edgar():
    adapter = equity_research.GlobalEquityResearchAdapter(
        stock_loader=lambda symbol: {
            "code": symbol,
            "name": "Example Inc.",
            "market": "US",
            "quote": {
                "price": 220,
                "mcap": 3_000_000_000_000,
                "pe": 31,
                "pb": 12,
                "source": "sina",
                "sources": ["sina", "tencent"],
            },
            "metrics": {
                "report_date": "2026-06-30",
                "revenue": 100_000_000,
                "revenue_yoy": 9,
                "net_profit": 25_000_000,
                "roe": 42,
                "gross_margin": 46,
                "net_margin": 25,
                "debt_ratio": 58,
            },
            "data_sources": ["sina", "tencent"],
        }
    )
    service = equity_research.EquityResearchService([adapter])

    snapshot = service.snapshot("AAPL")

    assert snapshot["identity"]["market"] == "US"
    assert snapshot["identity"]["currency"] == "USD"
    assert snapshot["sources"] == ["sina", "tencent"]
    sections = {item["id"]: item for item in snapshot["sections"]}
    assert sections["valuation"]["status"] == "covered"
    assert sections["profitability"]["status"] == "covered"
    assert sections["balance_sheet"]["status"] == "covered"
    assert sections["cash_flow"]["status"] == "gap"
    assert sections["disclosure"]["status"] == "gap"
    assert "统一经营现金流证据尚未接入" in snapshot["gaps"]
    source_status = {item["id"]: item for item in snapshot["workflow"]["sourceStatus"]}
    assert source_status["global-quote-route"]["status"] == "available"
    assert source_status["global-quote-route"]["message"] == "sina → tencent"


def test_source_failures_remain_visible_in_quality_diagnostics():
    adapter = equity_research.ChinaEquityResearchAdapter(
        valuation_loader=lambda symbol: (_ for _ in ()).throw(RuntimeError("quote down")),
        financial_loader=lambda symbol: {"period": "2026-06-30", "roe": 12},
        percentile_loader=lambda symbol: {},
    )

    snapshot = equity_research.EquityResearchService([adapter]).snapshot("600000")

    workflow = snapshot["workflow"]
    assert workflow["task"]["status"] == "partial"
    assert workflow["diagnostics"]["failedSources"] == ["cn-quote-valuation"]
    source_status = {item["id"]: item for item in workflow["sourceStatus"]}
    assert source_status["cn-quote-valuation"]["status"] == "fetch_failed"
    blocks = {item["id"]: item for item in workflow["blocks"]}
    assert blocks["valuation"]["status"] == "fetch_failed"
    assert "quote down" in workflow["dataQuality"]["warnings"]


def test_global_quote_route_marks_secondary_provider_as_fallback():
    adapter = equity_research.GlobalEquityResearchAdapter(
        stock_loader=lambda symbol: {
            "code": symbol,
            "name": "Fallback Inc.",
            "market": "US",
            "quote": {
                "price": 50,
                "source": "tencent",
                "sources": ["tencent", "eastmoney"],
            },
            "metrics": {},
            "data_sources": ["tencent", "eastmoney"],
        }
    )

    snapshot = equity_research.EquityResearchService([adapter]).snapshot("FALL")

    source_status = {item["id"]: item for item in snapshot["workflow"]["sourceStatus"]}
    assert source_status["global-quote-route"]["status"] == "fallback"
    assert source_status["global-quote-route"]["message"] == (
        "主源 sina 不可用，已降级到 tencent"
    )
    blocks = {item["id"]: item for item in snapshot["workflow"]["blocks"]}
    assert blocks["valuation"]["status"] == "fallback"
    assert snapshot["workflow"]["diagnostics"]["fallbackSources"] == [
        "global-quote-route"
    ]


def test_edgar_adapter_is_optional_until_a_user_agent_is_configured():
    edgar = equity_research.EdgarEvidenceAdapter("")
    inputs = equity_research.ResearchInputs(
        symbol="AAPL",
        market="US",
        name="Apple",
        currency="USD",
    )

    assert edgar.enabled is False
    assert edgar.supports(inputs) is False


def test_equity_research_route_exposes_snapshot(monkeypatch):
    import app as app_module

    expected = {"schemaVersion": "newma-dock.equity-research.v1"}
    monkeypatch.setattr(
        app_module.equity_research.default_service,
        "snapshot",
        lambda symbol: {**expected, "symbol": symbol},
    )

    response = TestClient(app_module.app).get(
        "/api/equity-research/snapshot?symbol=AAPL"
    )

    assert response.status_code == 200
    assert response.json()["data"] == {**expected, "symbol": "AAPL"}


def test_equity_research_comparison_route(monkeypatch):
    import app as app_module

    monkeypatch.setattr(
        app_module.equity_research.default_service,
        "comparison",
        lambda symbols: {"rows": symbols},
    )

    response = TestClient(app_module.app).get(
        "/api/equity-research/comparison?symbols=AAPL,MSFT"
    )

    assert response.status_code == 200
    assert response.json()["data"] == {"rows": ["AAPL", "MSFT"]}
