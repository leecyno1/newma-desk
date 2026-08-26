from types import SimpleNamespace

import financial_analytics
import equity_research


def evidence(evidence_id, value, *, as_of="2026-06-30", confidence="high"):
    return SimpleNamespace(
        id=evidence_id,
        value=value,
        as_of=as_of,
        confidence=confidence,
    )


def test_derives_traceable_ratios_and_four_axis_scorecard():
    result = financial_analytics.analyze_financials([
        evidence("valuation.pe_ttm", 20),
        evidence("valuation.pb", 4),
        evidence("valuation.pe_ttm_percentile", 40),
        evidence("valuation.pb_percentile", 60),
        evidence("growth.revenue_yoy", 18),
        evidence("growth.net_profit_yoy", 12),
        evidence("profitability.roe", 16),
        evidence("profitability.net_margin", 12),
        evidence("profitability.eps", 2),
        evidence("cash_flow.op_cf_ps", 3),
        evidence("balance_sheet.debt_ratio", 48),
    ])

    metrics = {item.id: item for item in result.metrics}
    assert metrics["derived.earnings_yield"].value == 5
    assert metrics["derived.cash_conversion"].value == 150
    assert metrics["derived.cash_conversion"].depends_on == (
        "cash_flow.op_cf_ps",
        "profitability.eps",
    )
    scorecard = {item.id: item for item in result.scorecard}
    assert set(scorecard) == {"quality", "growth", "valuation", "resilience"}
    assert all(item.score is not None for item in scorecard.values())


def test_mismatched_period_stops_cash_conversion_instead_of_guessing():
    result = financial_analytics.analyze_financials([
        evidence("profitability.eps", 2, as_of="2026-06-30"),
        evidence("cash_flow.op_cf_ps", 3, as_of="2026-03-31"),
    ])

    assert "derived.cash_conversion" not in {item.id for item in result.metrics}
    assert "盈利现金转化率所需证据报告期不一致，已停止计算" in result.gaps


def test_sec_facts_enable_cash_conversion_leverage_and_roa_approximation():
    result = financial_analytics.analyze_financials([
        evidence("disclosure.edgar_net_income", 10),
        evidence("disclosure.edgar_operating_cash_flow", 12),
        evidence("disclosure.edgar_assets", 100),
        evidence("disclosure.edgar_liabilities", 40),
    ])

    metrics = {item.id: item for item in result.metrics}
    assert metrics["derived.cash_conversion"].value == 120
    assert metrics["derived.debt_ratio"].value == 40
    assert metrics["derived.equity_multiplier"].value == 1.6667
    assert metrics["derived.equity_multiplier"].depends_on == (
        "disclosure.edgar_assets",
        "disclosure.edgar_liabilities",
    )
    assert metrics["derived.roa_approx"].value == 10


def test_missing_inputs_leave_scores_unavailable():
    result = financial_analytics.analyze_financials([])

    assert result.metrics == ()
    assert all(axis.score is None and axis.status == "unavailable" for axis in result.scorecard)


def test_snapshot_exposes_standard_comparison_profile_and_derived_evidence():
    adapter = equity_research.ChinaEquityResearchAdapter(
        valuation_loader=lambda symbol: {"name": symbol, "pe_ttm": 20, "pb": 3},
        financial_loader=lambda symbol: {
            "period": "2026-06-30",
            "revenue_yoy": 15,
            "net_profit_yoy": 12,
            "roe": 16,
            "net_margin": 11,
            "eps": 2,
            "op_cf_ps": 2.5,
        },
        percentile_loader=lambda symbol: {"metrics": {}},
    )

    snapshot = equity_research.EquityResearchService([adapter]).snapshot("600000")

    assert snapshot["comparisonProfile"]["metrics"]["pe"] == 20
    assert snapshot["comparisonProfile"]["metrics"]["cashConversionPct"] == 125
    assert snapshot["comparisonProfile"]["scores"]["quality"] is not None
    derived = next(item for item in snapshot["evidenceLedger"] if item["id"] == "derived.cash_conversion")
    assert derived["sourceType"] == "derived"
    assert derived["dependsOn"] == ["cash_flow.op_cf_ps", "profitability.eps"]


def test_adapter_normalizes_source_percent_and_per_share_strings_once():
    adapter = equity_research.ChinaEquityResearchAdapter(
        valuation_loader=lambda symbol: {"name": symbol, "pe_ttm": "20.5"},
        financial_loader=lambda symbol: {
            "period": "2026-06-30",
            "revenue_yoy": "18.20%",
            "roe": "12.5%",
            "eps": "2.00元",
            "op_cf_ps": "2.40元",
        },
        percentile_loader=lambda symbol: {"metrics": {}},
    )

    snapshot = equity_research.EquityResearchService([adapter]).snapshot("600000")

    profile = snapshot["comparisonProfile"]
    assert profile["metrics"]["pe"] == 20.5
    assert profile["metrics"]["revenueGrowthPct"] == 18.2
    assert profile["metrics"]["roePct"] == 12.5
    assert profile["metrics"]["cashConversionPct"] == 120
    assert profile["scores"]["growth"] is not None
