from types import SimpleNamespace

import financial_analytics
import equity_research


def evidence(evidence_id, value, *, as_of="2026-06-30", confidence="high", period_start="2026-01-01", unit="USD"):
    return SimpleNamespace(
        id=evidence_id,
        value=value,
        as_of=as_of,
        confidence=confidence,
        period_start=period_start,
        unit=unit,
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
    assert "derived.cash_conversion" not in metrics
    assert metrics["derived.per_share_cash_earnings_proxy"].value == 1.5
    assert metrics["derived.per_share_cash_earnings_proxy"].depends_on == (
        "cash_flow.op_cf_ps",
        "profitability.eps",
    )
    scorecard = {item.id: item for item in result.scorecard}
    assert set(scorecard) == {"quality", "growth", "valuation", "resilience"}
    assert all(item.score is not None for item in scorecard.values())
    assert scorecard["quality"].signal_count == 2
    assert "derived.per_share_cash_earnings_proxy" not in scorecard["quality"].evidence_ids


def test_mismatched_period_stops_cash_conversion_instead_of_guessing():
    result = financial_analytics.analyze_financials([
        evidence("profitability.eps", 2, as_of="2026-06-30"),
        evidence("cash_flow.op_cf_ps", 3, as_of="2026-03-31"),
    ])

    assert "derived.cash_conversion" not in {item.id for item in result.metrics}
    assert "derived.per_share_cash_earnings_proxy" not in {item.id for item in result.metrics}
    assert "每股现金流／EPS（参考）所需证据报告期不一致，已停止计算" in result.gaps


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
    assert snapshot["comparisonProfile"]["metrics"]["cashConversionPct"] is None
    assert snapshot["comparisonProfile"]["scores"]["quality"] is not None
    derived = next(item for item in snapshot["evidenceLedger"] if item["id"] == "derived.per_share_cash_earnings_proxy")
    assert derived["value"] == 1.25
    assert derived["unit"] == "x"
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
    assert profile["metrics"]["cashConversionPct"] is None
    assert next(item for item in snapshot["evidenceLedger"] if item["id"] == "cash_flow.op_cf_ps")["value"] == 2.4
    assert profile["scores"]["growth"] is not None


def test_cash_conversion_requires_same_duration_and_currency_not_just_end_date():
    for start, unit in [(None, "USD"), ("2026-04-01", "USD"), ("2026-01-01", "CNY")]:
        result = financial_analytics.analyze_financials([
            evidence("disclosure.edgar_net_income", 10),
            evidence("disclosure.edgar_operating_cash_flow", 12, period_start=start, unit=unit),
        ])
        assert "derived.cash_conversion" not in {item.id for item in result.metrics}
        assert any("期间起点或币种" in gap for gap in result.gaps)


def test_edgar_retains_period_start_and_only_selects_usd_facts():
    facts = {"us-gaap": {"NetIncomeLoss": {"units": {
        "USD": [{"val": 10, "start": "2026-01-01", "end": "2026-06-30", "filed": "2026-08-01", "form": "10-Q"}],
        "CNY": [{"val": 70, "end": "2026-06-30", "filed": "2026-08-02"}],
    }}}}
    assert equity_research.EdgarEvidenceAdapter._latest_fact(facts, ("NetIncomeLoss",)) == (
        10, "2026-06-30", "10-Q", "2026-01-01", "2026-08-01")


def test_nonpositive_eps_does_not_generate_a_proxy_or_quality_score():
    for eps in (0, -2):
        result = financial_analytics.analyze_financials([
            evidence("profitability.eps", eps), evidence("cash_flow.op_cf_ps", 3),
        ])
        assert not result.metrics
        assert next(axis for axis in result.scorecard if axis.id == "quality").score is None


def test_edgar_old_period_amendment_does_not_replace_latest_period():
    facts = {"us-gaap": {"NetIncomeLoss": {"units": {"USD": [
        {"val": 10, "start": "2026-01-01", "end": "2026-06-30", "filed": "2026-08-01", "form": "10-Q"},
        {"val": 5, "start": "2025-01-01", "end": "2025-12-31", "filed": "2026-09-01", "form": "10-K/A"},
    ]}}}}
    assert equity_research.EdgarEvidenceAdapter._latest_fact(facts, ("NetIncomeLoss",)) == (
        10, "2026-06-30", "10-Q", "2026-01-01", "2026-08-01")
