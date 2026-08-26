#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Reusable single-security CZSC analysis orchestration.

This module keeps market-data loading, CZSC execution, evidence generation,
Snapshot creation, and Snapshot registration behind one interface.  Web
handlers and batch scans therefore exercise the same implementation.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from instock.core.analysis_snapshot import (
    build_analysis_snapshot,
    get_analysis_snapshot_registry,
)
from instock.core.kline.cost_distribution import build_volume_cost_distribution
from instock.core.market_data_provider import MarketDataProvider


CZSC_SYMBOL_PATTERN = re.compile(r"^\d{6}(?:\.(?:SH|SZ|BJ))?$", re.IGNORECASE)
CZSC_PERIODS = frozenset({"daily", "weekly", "monthly"})
CZSC_BAR_LIMITS = frozenset({120, 240, 480, 800})
CZSC_MIN_DIRECTION_BARS = 80


class CZSCAnalysisFailed(ValueError):
    """Raised when valid market data cannot form a CZSC analysis result."""


def run_czsc_analysis(
    provider: MarketDataProvider,
    *,
    symbol: str,
    period: str,
    bars: int,
    as_of: Optional[str] = None,
    include_chart: bool = True,
) -> dict[str, Any]:
    """Run one traceable CZSC analysis and register its compact Snapshot."""

    # Loading the official CZSC runtime also loads its TA stack. Keep that
    # cost behind the analysis interface instead of every attached web start.
    from instock.core.indicator.czsc_analyzer import CZSCAnalyzer

    if as_of:
        kline = provider.get_kline(symbol, period, bars, as_of)
    else:
        kline = provider.get_kline(symbol, period, bars)
    analyzer = CZSCAnalyzer()
    result = analyzer.analyze_kline(kline, symbol.split(".")[0], period)
    if not result.get("success"):
        raise CZSCAnalysisFailed(result.get("error", "CZSC 结构分析失败"))

    payload = analyzer.get_analysis_payload(include_chart=include_chart)
    payload["cost_distribution"] = build_volume_cost_distribution(kline)
    actual_bars = len(kline)
    insufficient_history = actual_bars < CZSC_MIN_DIRECTION_BARS
    if insufficient_history:
        insight = dict(payload.get("insight") or {})
        risk_flags = list(insight.get("risk_flags") or [])
        history_warning = (
            f"有效 K 线仅 {actual_bars} 根，少于形成方向结论所需的 "
            f"{CZSC_MIN_DIRECTION_BARS} 根；结构图仅作事实观察。"
        )
        if history_warning not in risk_flags:
            risk_flags.insert(0, history_warning)
        insight.update({
            "bias": "unknown",
            "headline": (
                f"仅 {actual_bars} 根 K 线，结构置信度不足，不形成方向结论"
            ),
            "risk_flags": risk_flags,
            "conclusion_state": "insufficient_history",
        })
        payload["insight"] = insight
        payload["conclusion_state"] = "insufficient_history"
        payload["data_state"] = "partial"
        payload["limitations"] = [
            *list(payload.get("limitations") or []),
            "insufficient_history_for_directional_conclusion",
        ]
    else:
        payload["insight"]["conclusion_state"] = "formed"
        payload["conclusion_state"] = "formed"
        payload["data_state"] = "complete"
        payload["limitations"] = list(payload.get("limitations") or [])
    payload.update({
        "requested_bars": bars,
        "actual_bars": actual_bars,
        "minimum_direction_bars": CZSC_MIN_DIRECTION_BARS,
        "requested_as_of": as_of,
        "data_source": kline.attrs.get("data_source", provider.name),
        "data_endpoint": kline.attrs.get("data_endpoint", ""),
        "adjust": kline.attrs.get("adjust", "unknown"),
    })
    payload["snapshot"] = build_analysis_snapshot(
        analysis_name="czsc",
        analysis_version=(
            f"czsc-{payload['engine']['version']}+"
            f"instock-{payload['engine']['analysis_version']}"
        ),
        parameters={
            "symbol": symbol,
            "period": period,
            "bars": bars,
            "asOf": as_of,
        },
        frame=kline,
        requested_bars=bars,
        provider_name=provider.name,
        input_summary={
            "quality_state": payload["evidence"]["input_quality"]["state"],
            "large_gap_count": payload["evidence"]["input_quality"]["large_gap_count"],
            "rows_removed": payload["evidence"]["input_quality"]["rows_removed"],
        },
        result_summary={
            "summary": payload["summary"],
            "structure_stability": payload["evidence"]["structure_stability"],
            "latest_structure_change": payload["evidence"]["latest_structure_change"],
            "bias": payload["insight"].get("bias"),
            "headline": payload["insight"].get("headline"),
            "conclusion_state": payload["conclusion_state"],
            "end_date": payload["end_date"],
            "cost_distribution": {
                "state": payload["cost_distribution"].get("state"),
                "average_cost": payload["cost_distribution"].get("average_cost"),
                "profit_volume_pct": payload["cost_distribution"].get("profit_volume_pct"),
            },
        },
    )
    if insufficient_history:
        payload["snapshot"]["data_window"]["coverage"] = "partial"
        snapshot_limitations = payload["snapshot"]["provenance"]["limitations"]
        if "insufficient_history_for_directional_conclusion" not in snapshot_limitations:
            snapshot_limitations.append(
                "insufficient_history_for_directional_conclusion"
            )
    get_analysis_snapshot_registry().register(payload["snapshot"])
    return payload
