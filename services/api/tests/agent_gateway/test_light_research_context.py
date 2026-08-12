import json
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.agent_gateway.fakes import FakeAgentAdapter
from vibe_visualization_api.agent_gateway.models import AgentTaskCreate
from vibe_visualization_api.ai_context.light_research import (
    MAX_RESEARCH_CONTEXT_CHARACTERS,
    LightResearchContextEnricher,
)
from vibe_visualization_api.config import Settings
from vibe_visualization_api.data_services.models import (
    DataServiceDescriptor,
    ServiceCapability,
)
from vibe_visualization_api.data_services.registry import DataServiceRegistry
from vibe_visualization_api.main import create_app


def _capability(path: str) -> ServiceCapability:
    return ServiceCapability(
        method="GET",
        path=path,
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        permission="market.read",
    )


def _service() -> DataServiceDescriptor:
    return DataServiceDescriptor(
        id="market-data",
        base_url="http://127.0.0.1:8911/api/research",
        transport="rest",
        allowed_hosts=["127.0.0.1"],
        capabilities={
            "market.ohlcv": _capability("/api/market-terminal/ohlcv"),
            "market.news": _capability("/news"),
            "market.announcements": _capability("/announcements"),
            "market.reports": _capability("/reports"),
            "research.equity-snapshot": _capability(
                "/equity-research/snapshot"
            ),
            "research.equity-comparison": _capability(
                "/equity-research/comparison"
            ),
        },
    )


def _bars(count: int = 156) -> dict[str, object]:
    items = [
        {
            "timestamp": 1_700_000_000_000 + index * 604_800_000,
            "open": 100 + index,
            "high": 102 + index,
            "low": 98 + index,
            "close": 101 + index,
            "volume": 1_000_000 + index,
        }
        for index in range(count)
    ]
    return {
        "data": {
            "symbol": "600519",
            "market": "CN",
            "timeframe": "1w",
            "adjust": "qfq",
            "items": items,
            "source": "test-weekly",
            "asOf": "2026-07-31T00:00:00Z",
        }
    }


def _snapshot() -> dict[str, object]:
    return {
        "data": {
            "identity": {
                "symbol": "600519",
                "name": "贵州茅台",
                "market": "CN",
                "currency": "CNY",
            },
            "coverage": {"coveredDimensions": 4, "totalDimensions": 7},
            "analytics": {
                "metrics": [
                    {
                        "id": "derived.cash_conversion",
                        "label": "盈利现金转化率",
                        "value": 98.7,
                        "unit": "%",
                        "method": "经营现金流 / 净利润",
                        "dependsOn": ["cash_flow.op_cf_ps", "profitability.eps"],
                    }
                ]
            },
            "scorecard": [
                {
                    "id": "quality",
                    "title": "盈利质量",
                    "score": 80.2,
                    "status": "strong",
                    "signalCount": 3,
                    "evidenceIds": ["profitability.roe"],
                }
            ],
            "comparisonProfile": {
                "metrics": {"pe": 20.4, "roePct": 10.57},
                "scores": {"quality": 80.2},
            },
            "workflow": {
                "task": {
                    "status": "partial",
                    "stage": "quality-review",
                    "progress": 1,
                    "updatedAt": "2026-07-31T00:00:00Z",
                },
                "dataQuality": {
                    "score": 68,
                    "level": "usable",
                    "blockScores": {"valuation": 92, "disclosure": 0},
                    "limitations": ["缺少一致预期修订历史"],
                    "warnings": [],
                },
                "blocks": [
                    {
                        "id": "valuation",
                        "title": "估值",
                        "status": "available",
                        "qualityScore": 92,
                        "evidenceCount": 20,
                        "sources": ["test-source"],
                        "asOf": "2026-07-31",
                        "warnings": [],
                        "gaps": [],
                    },
                    {
                        "id": "disclosure",
                        "title": "披露",
                        "status": "missing",
                        "qualityScore": 0,
                        "evidenceCount": 0,
                        "sources": [],
                        "warnings": [],
                        "gaps": ["未启用原始披露"],
                    },
                ],
                "sourceStatus": [
                    {
                        "id": "test-source",
                        "title": "测试数据源",
                        "status": "available",
                        "source": "test-source",
                    }
                ],
                "diagnostics": {
                    "missingBlocks": ["disclosure"],
                    "failedSources": [],
                    "fallbackSources": [],
                    "gapCount": 1,
                },
                "history": {
                    "state": "saved",
                    "lastGoodAt": "2026-07-30T00:00:00Z",
                },
            },
            "reportHistory": [
                {
                    "id": "report-1",
                    "status": "completed",
                    "qualityScore": 82,
                    "qualityLevel": "good",
                    "coverageRatio": 0.83,
                    "gapCount": 1,
                    "createdAt": "2026-07-30T00:00:00Z",
                }
            ],
            "sections": [
                {"id": "valuation", "title": "估值", "status": "covered"},
                {"id": "disclosure", "title": "披露", "status": "gap"},
            ],
            "evidenceLedger": [
                {
                    "id": f"valuation.item-{index}",
                    "dimension": "valuation",
                    "label": f"估值指标 {index}",
                    "value": index,
                    "source": "test-source",
                    "asOf": "2026-07-31",
                    "confidence": "high",
                }
                for index in range(40)
            ],
            "sources": ["test-source"],
            "gaps": ["缺少一致预期修订历史"],
            "generatedAt": "2026-07-31T00:00:00Z",
        }
    }


class FakeResearchClient:
    def __init__(
        self,
        responses: dict[str, object] | None = None,
        failures: set[str] | None = None,
    ):
        self.responses = responses or {}
        self.failures = failures or set()
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def invoke(
        self,
        service: DataServiceDescriptor,
        capability_id: str,
        input_data: dict[str, Any],
    ) -> object:
        self.calls.append((capability_id, input_data))
        if capability_id in self.failures:
            raise RuntimeError("secret upstream detail")
        return self.responses.get(capability_id, {"data": []})


def _request(prompt: str, capability: str = "module.explain") -> AgentTaskCreate:
    return AgentTaskCreate(
        module_id="market-daily",
        capability=capability,
        prompt=prompt,
        context={
            "vibedesk": {
                "page": {
                    "selection": {
                        "symbol": "600519",
                        "name": "贵州茅台",
                        "market": "CN",
                    },
                    "filters": {"adjustment": "hfq"},
                }
            }
        },
    )


@pytest.mark.asyncio
async def test_generic_question_adds_long_term_market_and_research_snapshot():
    client = FakeResearchClient(
        {"market.ohlcv": _bars(), "research.equity-snapshot": _snapshot()}
    )
    enricher = LightResearchContextEnricher(
        DataServiceRegistry([_service()]), client
    )

    enriched = await enricher.enrich(_request("综合分析一下当前标的"))

    assert [call[0] for call in client.calls] == [
        "market.ohlcv",
        "research.equity-snapshot",
    ]
    assert client.calls[0][1] == {
        "symbol": "600519",
        "market": "CN",
        "timeframe": "1w",
        "limit": 156,
        "adjust": "hfq",
    }
    research = enriched.context["vibedesk"]["research"]
    assert research["usedCapabilities"] == [
        "market.ohlcv",
        "research.equity-snapshot",
    ]
    assert research["evidence"]["market.ohlcv"]["barCount"] == 156
    assert len(
        research["evidence"]["research.equity-snapshot"]["evidenceLedger"]
    ) == 20
    assert research["evidence"]["research.equity-snapshot"]["scorecard"][0]["score"] == 80.2
    assert research["evidence"]["research.equity-snapshot"]["analytics"][0]["id"] == "derived.cash_conversion"
    workflow = research["evidence"]["research.equity-snapshot"]["workflow"]
    assert workflow["task"]["status"] == "partial"
    assert workflow["dataQuality"]["score"] == 68
    assert workflow["diagnostics"]["missingBlocks"] == ["disclosure"]
    assert workflow["history"]["items"][0]["qualityLevel"] == "good"
    assert (
        len(json.dumps(research, ensure_ascii=False))
        <= MAX_RESEARCH_CONTEXT_CHARACTERS
    )


@pytest.mark.asyncio
async def test_event_question_uses_news_instead_of_financial_snapshot():
    client = FakeResearchClient(
        {
            "market.ohlcv": _bars(),
            "market.news": {
                "data": [
                    {
                        "新闻标题": "公司发布新产品",
                        "发布时间": "2026-07-31 09:30:00",
                        "文章来源": "测试新闻",
                        "新闻链接": "https://example.com/news",
                    }
                ]
            },
        }
    )
    enricher = LightResearchContextEnricher(
        DataServiceRegistry([_service()]), client
    )

    enriched = await enricher.enrich(_request("今天为什么异动，有什么新闻？"))

    assert [call[0] for call in client.calls] == ["market.ohlcv", "market.news"]
    news = enriched.context["vibedesk"]["research"]["evidence"]["market.news"]
    assert news["items"][0]["title"] == "公司发布新产品"
    assert news["untrustedExternalText"] is True


@pytest.mark.asyncio
async def test_peer_symbols_in_prompt_use_standard_equity_comparison():
    client = FakeResearchClient(
        {
            "market.ohlcv": _bars(),
            "research.equity-comparison": {
                "data": {
                    "rows": [
                        {
                            "identity": {"symbol": "600519", "market": "CN"},
                            "coverage": {"ratio": 0.83},
                            "metrics": {"pe": 20.4, "roePct": 10.57},
                            "scores": {"quality": 80.2},
                        },
                        {
                            "identity": {"symbol": "000858", "market": "CN"},
                            "coverage": {"ratio": 0.67},
                            "metrics": {"pe": 18.1, "roePct": 9.2},
                            "scores": {"quality": 72.5},
                        },
                    ],
                    "errors": [],
                }
            },
        }
    )
    enricher = LightResearchContextEnricher(
        DataServiceRegistry([_service()]), client
    )

    enriched = await enricher.enrich(_request("把 600519 和 000858、AAPL 做同行横向比较"))

    assert [call[0] for call in client.calls] == [
        "market.ohlcv",
        "research.equity-comparison",
    ]
    assert client.calls[1][1] == {"symbols": "600519,000858,AAPL"}
    comparison = enriched.context["vibedesk"]["research"]["evidence"]["research.equity-comparison"]
    assert comparison["rows"][1]["metrics"]["pe"] == 18.1


@pytest.mark.asyncio
async def test_edit_tasks_and_non_security_pages_are_not_enriched():
    client = FakeResearchClient()
    enricher = LightResearchContextEnricher(
        DataServiceRegistry([_service()]), client
    )

    edited = await enricher.enrich(_request("修改页面", capability="module.edit"))
    missing = await enricher.enrich(
        AgentTaskCreate(
            module_id="industry-map",
            capability="module.explain",
            prompt="分析页面",
            context={"vibedesk": {"page": {"selection": {}}}},
        )
    )

    assert edited.context == _request("修改页面", capability="module.edit").context
    assert "research" not in missing.context["vibedesk"]
    assert client.calls == []


@pytest.mark.asyncio
async def test_partial_failure_keeps_successful_evidence_without_error_details():
    client = FakeResearchClient(
        {"market.ohlcv": _bars()}, failures={"research.equity-snapshot"}
    )
    enricher = LightResearchContextEnricher(
        DataServiceRegistry([_service()]), client
    )

    enriched = await enricher.enrich(_request("分析基本面和估值"))

    research = enriched.context["vibedesk"]["research"]
    assert research["usedCapabilities"] == ["market.ohlcv"]
    assert research["gaps"] == [
        {
            "capability": "research.equity-snapshot",
            "reason": "temporarily_unavailable",
        }
    ]
    assert "secret upstream detail" not in json.dumps(research)


def test_create_app_passes_enriched_context_to_selected_agent(tmp_path: Path):
    adapter = FakeAgentAdapter()
    data_client = FakeResearchClient(
        {"market.ohlcv": _bars(), "research.equity-snapshot": _snapshot()}
    )
    application = create_app(
        Settings(
            runtime_dir=tmp_path,
            database_path=tmp_path / "gateway.db",
            agent_default_adapter=adapter.id,
        ),
        agent_adapters=[adapter],
        data_services=[_service()],
        data_service_client=data_client,
    )

    with TestClient(application) as client:
        response = client.post(
            "/api/agent/tasks",
            json=_request("综合分析").model_dump(mode="json", by_alias=True),
        )
        assert response.status_code == 202
        deadline = time.monotonic() + 2
        while not adapter.requests and time.monotonic() < deadline:
            time.sleep(0.01)

    assert adapter.requests
    research = adapter.requests[0].context["vibedesk"]["research"]
    assert research["subject"] == {
        "symbol": "600519",
        "market": "CN",
        "name": "贵州茅台",
    }
