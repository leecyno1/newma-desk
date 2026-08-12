import pytest

from vibe_visualization_api.finance_pilots.adapters import (
    DailyStockAnalysisAdapter,
    PilotPayloadError,
    QuantDingerAdapter,
)


def test_daily_stock_analysis_extracts_context_and_drops_advice_fields() -> None:
    payload = {
        "dataPolicy": "dock-only",
        "analysisContext": {
            "pack_version": "1.0",
            "created_at": "2026-07-27T08:00:00Z",
            "subject": {"code": "AAPL", "stock_name": "Apple", "market": "US"},
            "blocks": [
                {
                    "key": "fundamentals",
                    "label": "宏观面",
                    "status": "available",
                    "source": "Desk Evidence Ledger",
                    "warnings": [],
                },
                {
                    "key": "news",
                    "label": "新闻",
                    "status": "fallback",
                    "source": "Desk last-good cache",
                    "warnings": ["provider unavailable"],
                    "missing_reasons": ["fresh feed unavailable"],
                },
            ],
            "data_quality": {
                "overall_score": 78,
                "level": "usable",
                "block_scores": {"fundamentals": 90, "news": 55},
                "limitations": ["新闻使用缓存"],
            },
        },
        "reportHistory": [
            {
                "id": "report-1",
                "status": "completed",
                "createdAt": "2026-07-27T08:05:00Z",
                "title": "AAPL evidence refresh",
                "recommendation": "buy",
                "targetPrice": 300,
            }
        ],
        "taskProgress": {
            "taskId": "task-1",
            "status": "running",
            "stage": "evidence",
            "progress": 65,
        },
        "investmentScore": 99,
        "buySellSignal": "buy",
    }

    result = DailyStockAnalysisAdapter().adapt(payload).model_dump(
        mode="json", by_alias=True
    )

    assert result["subject"] == {"symbol": "AAPL", "name": "Apple", "market": "US"}
    assert result["blocks"][1]["status"] == "fallback"
    assert result["dataQuality"]["score"] == 78
    assert result["taskProgress"]["progress"] == 0.65
    serialized = str(result).casefold()
    assert "recommendation" not in serialized
    assert "targetprice" not in serialized
    assert "buysellsignal" not in serialized
    assert result["agentContext"]["gapBlocks"] == ["news"]


def test_quantdinger_extracts_only_paper_strategy_ledger() -> None:
    payload = {
        "executionMode": "backtest",
        "generatedAt": "2026-07-27T09:00:00Z",
        "strategy": {
            "id": "trend-v1",
            "name": "趋势模板",
            "version": "1.2",
            "templateId": "dock-trend",
            "parameters": {"fast": 10, "slow": 30, "notes": ["paper"]},
        },
        "dataset": {
            "symbols": ["aapl", "msft"],
            "market": "US",
            "startDate": "2025-01-01",
            "endDate": "2026-06-30",
            "timeframe": "1d",
            "source": "newma-desk",
        },
        "result": {
            "status": "completed",
            "metrics": {
                "totalReturn": 0.18,
                "annualizedReturn": 0.11,
                "maxDrawdown": -0.09,
                "sharpeRatio": 1.2,
                "tradeCount": 24,
            },
            "equityCurve": [
                {"date": "2025-01-01", "nav": 1.0},
                {"date": "2026-06-30", "nav": 1.18},
            ],
            "performanceAttribution": [
                {"name": "选股", "value": 0.12, "unit": "%"},
                {"name": "择时", "value": 0.06, "unit": "%"},
            ],
            "tradesDetail": [{"symbol": "AAPL"}],
        },
    }

    result = QuantDingerAdapter().adapt(payload).model_dump(
        mode="json", by_alias=True
    )

    assert result["executionMode"] == "paper"
    assert result["dataset"]["source"] == "newma-desk"
    assert result["dataset"]["symbols"] == ["AAPL", "MSFT"]
    assert result["metrics"]["sharpe"] == 1.2
    assert result["metrics"]["tradeCount"] == 24
    assert result["attribution"][0]["factor"] == "选股"
    assert result["provenance"] == {
        "pilotId": "quantdinger",
        "dataPolicy": "desk-only",
        "executionPolicy": "paper-only",
    }
    assert "tradesDetail" not in str(result)


@pytest.mark.parametrize(
    "payload",
    [
        {
            "executionMode": "live",
            "strategy": {"id": "x", "name": "x"},
            "dataset": {"symbols": ["AAPL"], "startDate": "2025", "endDate": "2026", "source": "newma-desk"},
            "result": {},
        },
        {
            "executionMode": "paper",
            "strategy": {"id": "x", "name": "x", "source_code": "buy()"},
            "dataset": {"symbols": ["AAPL"], "startDate": "2025", "endDate": "2026", "source": "newma-desk"},
            "result": {},
        },
        {
            "executionMode": "paper",
            "strategy": {"id": "x", "name": "x"},
            "dataset": {"symbols": ["AAPL"], "startDate": "2025", "endDate": "2026", "source": "newma-desk"},
            "result": {"orders": []},
        },
        {
            "strategy": {"id": "x", "name": "x"},
            "dataset": {"symbols": ["AAPL"], "startDate": "2025", "endDate": "2026", "source": "newma-desk"},
            "result": {},
        },
        {
            "executionMode": "paper",
            "strategy": {"id": "x", "name": "x"},
            "dataset": {"symbols": ["AAPL"], "startDate": "2025", "endDate": "2026", "source": "yfinance"},
            "result": {},
        },
    ],
)
def test_quantdinger_rejects_live_code_and_order_surfaces(payload: dict) -> None:
    with pytest.raises(PilotPayloadError):
        QuantDingerAdapter().adapt(payload)


def test_quantdinger_drops_sensitive_strategy_parameters() -> None:
    result = QuantDingerAdapter().adapt(
        {
            "executionMode": "paper",
            "strategy": {
                "id": "safe",
                "name": "安全模板",
                "parameters": {
                    "window": 20,
                    "api_key": "never-persist",
                    "broker_account": "never-persist",
                },
            },
            "dataset": {
                "symbols": ["AAPL"],
                "startDate": "2025-01-01",
                "endDate": "2026-01-01",
                "source": "newma-desk",
            },
            "result": {"status": "completed"},
        }
    )

    assert result.strategy.parameters == {"window": 20}
