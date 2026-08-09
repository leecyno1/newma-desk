from datetime import UTC, datetime

from vibe_visualization_api.portfolio_center.models import PortfolioPosition
from vibe_visualization_api.portfolio_center.research import (
    compile_portfolio_research_coverage,
)


def position(account_id: str = "main") -> PortfolioPosition:
    return PortfolioPosition(
        accountId=account_id,
        market="CN",
        symbol="600519",
        name="贵州茅台",
        currency="CNY",
        quantity=100,
        averageCost=1000,
        costValue=100_000,
        realizedPnl=0,
    )


def archive_entry(**overrides):
    entry = {
        "id": "archive:thesis-tracker:thesis-1",
        "kind": "thesis",
        "sourceModId": "thesis-tracker",
        "artifactId": "thesis-1",
        "title": "贵州茅台核心逻辑",
        "status": "active",
        "security": {"market": "CN", "symbol": "600519", "name": "贵州茅台"},
        "asOf": "2026-09-01",
        "updatedAt": "2026-08-05T07:00:00+00:00",
        "tags": ["active"],
        "sourceRevision": 2,
    }
    entry.update(overrides)
    return entry


def test_compiles_cross_account_reference_only_coverage():
    result = compile_portfolio_research_coverage(
        user_id="alice",
        workspace_id="desk",
        positions=[position(), position("retirement")],
        archive={
            "entries": [
                archive_entry(),
                archive_entry(
                    id="archive:valuation-workbench:valuation-1",
                    kind="valuation",
                    sourceModId="valuation-workbench",
                    artifactId="valuation-1",
                    title="贵州茅台 DCF",
                ),
            ]
        },
        generated_at=datetime(2026, 8, 5, 8, tzinfo=UTC),
    )

    assert result["summary"] == {
        "positionCount": 1,
        "completeCount": 1,
        "partialCount": 0,
        "missingCount": 0,
        "attentionCount": 0,
        "activeReferenceCount": 2,
    }
    item = result["positions"][0]
    assert item["accountIds"] == ["main", "retirement"]
    assert item["coreKinds"] == ["thesis"]
    assert item["supportingKinds"] == ["valuation"]
    assert all("content" not in reference for reference in item["references"])


def test_flags_overdue_and_invalidated_core_research_without_scoring():
    result = compile_portfolio_research_coverage(
        user_id="alice",
        workspace_id="desk",
        positions=[position()],
        archive={
            "entries": [
                archive_entry(asOf="2026-08-01"),
                archive_entry(
                    id="archive:thesis-tracker:thesis-old",
                    artifactId="thesis-old",
                    title="旧逻辑",
                    status="invalidated",
                ),
            ]
        },
        generated_at=datetime(2026, 8, 5, 8, tzinfo=UTC),
    )

    item = result["positions"][0]
    assert item["status"] == "partial"
    assert item["missingGroups"] == ["supporting-analysis"]
    assert item["attentionReasons"] == ["review-overdue", "invalidated-thesis"]
    assert "score" not in item
