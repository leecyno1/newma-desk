#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Auditable single-stock research dossier assembled from Desk evidence."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from typing import Any, Callable, Mapping, Optional

import pandas as pd

from instock.core.analysis_snapshot import (
    SNAPSHOT_SCHEMA_VERSION,
    get_analysis_snapshot_registry,
    normalize_as_of,
)
from instock.core.czsc_analysis import run_czsc_analysis
from instock.core.market_data_provider import MarketDataError, MarketDataProvider
from instock.core.research.event_flow import resolve_event_flow_snapshot
from instock.core.research.supply_chain import resolve_industry_chain_snapshot


class StockResearchError(ValueError):
    """Raised when a stock dossier request is invalid or cannot be assembled."""


class StockResearchDossier:
    engine_name = "instock-stock-research-dossier"
    engine_version = "1.2.0"
    model = "instock-stock-research-dossier-v1.2"
    _symbol_pattern = re.compile(r"^\d{6}(?:\.(?:SH|SZ|BJ))?$", re.IGNORECASE)
    _periods = {"daily", "weekly", "monthly"}
    _bars = {120, 240, 480, 800}
    _historical_metric_ids = {
        "growth.revenue_yoy": "revenueGrowthPct",
        "growth.net_profit_yoy": "netProfitGrowthPct",
        "profitability.roe": "roePct",
        "profitability.gross_margin": "grossMarginPct",
        "profitability.net_margin": "netMarginPct",
        "derived.cash_conversion": "cashConversionPct",
        "balance_sheet.debt_ratio": "debtRatioPct",
    }

    def __init__(
        self,
        provider: MarketDataProvider,
        *,
        czsc_runner: Callable[..., dict[str, Any]] = run_czsc_analysis,
    ):
        self.provider = provider
        self.czsc_runner = czsc_runner

    def analyze(
        self,
        *,
        symbol: str,
        period: str = "daily",
        bars: int = 240,
        as_of: Optional[str] = None,
        industry_chain_snapshot_id: Optional[str] = None,
        event_flow_snapshot_id: Optional[str] = None,
    ) -> dict[str, Any]:
        normalized_symbol = str(symbol or "").strip().upper()
        if not self._symbol_pattern.fullmatch(normalized_symbol):
            raise StockResearchError("股票代码必须是 6 位 A 股代码，可带 SH/SZ/BJ 后缀")
        if period not in self._periods:
            raise StockResearchError("技术周期仅支持 daily、weekly、monthly")
        if bars not in self._bars:
            raise StockResearchError("历史窗口仅支持 120、240、480、800 根")
        try:
            normalized_as_of = normalize_as_of(as_of, reject_future=True)
        except ValueError as exc:
            raise StockResearchError(str(exc)) from exc

        code = normalized_symbol.split(".")[0]
        equity = self.provider.get_equity_snapshot(code)
        identity = equity.get("identity") or {}
        if str(identity.get("symbol") or "").split(".")[0] != code:
            raise StockResearchError("Desk 股票研究快照与请求代码不一致")

        try:
            technical_payload = self.czsc_runner(
                self.provider,
                symbol=normalized_symbol,
                period=period,
                bars=bars,
                as_of=normalized_as_of,
                include_chart=True,
            )
        except MarketDataError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise StockResearchError(f"CZSC 技术结构分析失败: {exc}") from exc

        disclosures, failures = self._load_disclosures(code, as_of=normalized_as_of)
        fundamentals = self._fundamentals(equity, as_of=normalized_as_of)
        technical = self._technical(technical_payload)
        industry_chain, chain_limitations = self._industry_chain(
            industry_chain_snapshot_id, code, as_of=normalized_as_of
        )
        event_flow, event_limitations = resolve_event_flow_snapshot(
            event_flow_snapshot_id, symbols=[code], as_of=normalized_as_of
        )
        if event_flow is not None:
            event_flow["symbol_summary"] = (
                event_flow.pop("symbol_summaries", [None])[0]
                if event_flow.get("symbol_summaries")
                else None
            )
        assessment = self._assessment(
            fundamentals,
            technical,
            equity,
            event_flow=event_flow,
            industry_chain=industry_chain,
        )
        limitations = [
            *[f"{item['capability']}_unavailable" for item in failures],
            *fundamentals["limitations"],
            *disclosures["limitations"],
            *chain_limitations,
            *event_limitations,
            *[str(item) for item in equity.get("gaps") or []],
            "research_dossier_is_not_a_rating_or_trade_instruction",
        ]
        technical_partial = (
            technical_payload.get("data_state") == "partial"
            or technical_payload.get("conclusion_state") == "insufficient_history"
        )
        if technical_partial:
            limitations.extend(
                item for item in technical_payload.get("limitations") or []
                if item not in limitations
            )
        data_state = "partial" if (
            failures
            or fundamentals["limitations"]
            or disclosures["limitations"]
            or chain_limitations
            or event_limitations
            or technical_partial
        ) else "complete"
        as_of_value = str(
            normalized_as_of
            or technical_payload.get("end_date")
            or equity.get("generatedAt")
            or date.today().isoformat()
        )[:10]

        stable_result = {
            "identity": identity,
            "as_of": as_of_value,
            "data_state": data_state,
            "technical": technical,
            "fundamentals": fundamentals,
            "disclosures": disclosures,
            "industry_chain": industry_chain,
            "event_flow": event_flow,
            "assessment": assessment,
            "failures": failures,
            "limitations": limitations,
        }
        snapshot = self._build_snapshot(
            stable_result,
            equity=equity,
            technical_snapshot=technical_payload.get("snapshot") or {},
            symbol=normalized_symbol,
            period=period,
            bars=bars,
            requested_as_of=normalized_as_of,
            industry_chain_snapshot_id=industry_chain_snapshot_id,
            event_flow_snapshot_id=event_flow_snapshot_id,
        )
        get_analysis_snapshot_registry().register(snapshot)
        return {
            "engine": {
                "name": self.engine_name,
                "version": self.engine_version,
                "model": self.model,
            },
            **stable_result,
            "data_source": self.provider.name,
            "snapshot": snapshot,
        }

    def _load_disclosures(self, code: str, *, as_of: Optional[str] = None):
        failures = []
        values: dict[str, list[dict[str, Any]]] = {}
        loaders = (
            ("announcements", "market.announcements", lambda: self.provider.get_security_announcements(code)),
            ("reports", "market.reports", lambda: self.provider.get_security_reports(code, pages=1)),
            ("news", "market.news", lambda: self.provider.get_security_news(code, limit=10)),
        )
        for key, capability, loader in loaders:
            try:
                values[key] = loader()
            except MarketDataError as exc:
                values[key] = []
                failures.append({"capability": capability, "error": str(exc)})
        excluded_after_as_of = {key: 0 for key in values}
        if as_of:
            date_fields = {
                "announcements": ("date",),
                "reports": ("publishDate", "date"),
                "news": ("发布时间", "time", "date"),
            }
            for key, items in values.items():
                filtered = []
                for item in items:
                    observed_at = self._row_date(item, date_fields[key])
                    if observed_at and observed_at <= as_of:
                        filtered.append(item)
                    else:
                        excluded_after_as_of[key] += 1
                values[key] = filtered
        historical_mode = bool(as_of and as_of < date.today().isoformat())
        return {
            "announcements": [self._announcement(item) for item in values["announcements"][:10]],
            "reports": [self._report(item) for item in values["reports"][:10]],
            "news": [self._news(item) for item in values["news"][:10]],
            "coverage": {key: len(values[key]) for key in ("announcements", "reports", "news")},
            "as_of_mode": "client_filter" if as_of else "latest",
            "excluded_after_as_of": excluded_after_as_of,
            "limitations": (
                ["historical_disclosures_client_filtered_from_latest_desk_window"]
                if historical_mode else []
            ),
        }, failures

    @staticmethod
    def _announcement(item: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "date": str(item.get("date") or "")[:10],
            "title": str(item.get("title") or ""),
            "type": str(item.get("type") or ""),
            "url": str(item.get("url") or ""),
        }

    @staticmethod
    def _report(item: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "date": str(item.get("publishDate") or item.get("date") or "")[:10],
            "title": str(item.get("title") or ""),
            "organization": str(item.get("orgSName") or item.get("organization") or ""),
            "rating": str(item.get("emRatingName") or item.get("rating") or ""),
            "url": str(item.get("pdfUrl") or item.get("url") or ""),
        }

    @staticmethod
    def _news(item: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "date": str(item.get("发布时间") or item.get("time") or item.get("date") or "")[:19],
            "title": str(item.get("新闻标题") or item.get("title") or ""),
            "source": str(item.get("文章来源") or item.get("source") or ""),
            "url": str(item.get("新闻链接") or item.get("url") or ""),
        }

    @classmethod
    def _fundamentals(
        cls,
        equity: Mapping[str, Any],
        *,
        as_of: Optional[str] = None,
    ) -> dict[str, Any]:
        profile = equity.get("comparisonProfile") or {}
        workflow = equity.get("workflow") or {}
        quality = workflow.get("dataQuality") or {}
        ledger = [dict(item) for item in equity.get("evidenceLedger") or [] if isinstance(item, Mapping)]
        generated_at = cls._date_only(equity.get("generatedAt"))
        historical_mode = bool(as_of and as_of < date.today().isoformat())
        snapshot_is_point_in_time = not historical_mode or bool(
            generated_at and generated_at <= as_of
        )
        excluded_future = 0
        excluded_unanchored = 0
        if as_of:
            filtered_ledger = []
            for item in ledger:
                observed_at = cls._date_only(item.get("asOf"))
                if observed_at is None:
                    excluded_unanchored += 1
                elif observed_at <= as_of:
                    filtered_ledger.append(item)
                else:
                    excluded_future += 1
            ledger = filtered_ledger

        limitations = []
        if historical_mode and not snapshot_is_point_in_time:
            limitations.extend([
                "historical_equity_snapshot_unavailable",
                "historical_fundamentals_limited_to_dated_evidence",
            ])
            metrics = {}
            for item in ledger:
                metric = cls._historical_metric_ids.get(str(item.get("id") or ""))
                value = item.get("value")
                if metric and isinstance(value, (int, float)) and not isinstance(value, bool):
                    metrics[metric] = float(value)
            dimensions = {
                str(item.get("dimension") or "").strip()
                for item in ledger
                if str(item.get("dimension") or "").strip()
            }
            total_dimensions = int((equity.get("coverage") or {}).get("totalDimensions") or 6)
            covered_dimensions = min(len(dimensions), total_dimensions)
            coverage = {
                "coveredDimensions": covered_dimensions,
                "totalDimensions": total_dimensions,
                "ratio": round(covered_dimensions / total_dimensions, 4) if total_dimensions else 0,
            }
            scorecard = []
            normalized_quality = {
                "score": None,
                "level": "historical_evidence_only",
                "limitations": ["Desk 未提供截止日点时基本面快照，已排除当前估值与综合评分"],
            }
            mode = "historical_evidence_only"
        else:
            metrics = dict(profile.get("metrics") or {})
            coverage = dict(equity.get("coverage") or {})
            scorecard = [dict(item) for item in equity.get("scorecard") or []]
            normalized_quality = {
                "score": quality.get("score"),
                "level": quality.get("level"),
                "limitations": list(quality.get("limitations") or []),
            }
            mode = "point_in_time_snapshot" if historical_mode else "latest_snapshot"
        return {
            "mode": mode,
            "requested_as_of": as_of,
            "snapshot_generated_at": str(equity.get("generatedAt") or ""),
            "point_in_time": snapshot_is_point_in_time,
            "coverage": coverage,
            "metrics": metrics,
            "scorecard": scorecard,
            "quality": normalized_quality,
            "evidence": ledger[:40],
            "excluded_future_evidence_count": excluded_future,
            "excluded_unanchored_evidence_count": excluded_unanchored,
            "limitations": limitations,
        }

    @staticmethod
    def _technical(payload: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "engine": dict(payload.get("engine") or {}),
            "period": str(payload.get("period") or ""),
            "end_date": str(payload.get("end_date") or ""),
            "summary": dict(payload.get("summary") or {}),
            "evidence": dict(payload.get("evidence") or {}),
            "structure": dict(payload.get("structure") or {}),
            "insight": dict(payload.get("insight") or {}),
            "cost_distribution": dict(payload.get("cost_distribution") or {}),
            "chart": dict(payload.get("chart") or {}),
            "snapshot": dict(payload.get("snapshot") or {}),
            "data_state": str(payload.get("data_state") or "complete"),
            "conclusion_state": str(payload.get("conclusion_state") or "formed"),
            "actual_bars": int(payload.get("actual_bars") or 0),
            "minimum_direction_bars": int(payload.get("minimum_direction_bars") or 80),
            "limitations": list(payload.get("limitations") or []),
        }

    @staticmethod
    def _assessment(
        fundamentals,
        technical,
        equity,
        *,
        event_flow=None,
        industry_chain=None,
    ):
        scorecard = fundamentals["scorecard"]
        strengths = [
            f"基本面：{item.get('title') or item.get('id')}"
            for item in scorecard if item.get("status") == "strong"
        ]
        tensions = [
            f"基本面：{item.get('title') or item.get('id')}"
            for item in scorecard if item.get("status") == "weak"
        ]
        gaps = [str(item) for item in equity.get("gaps") or []]
        for item in scorecard:
            if item.get("status") == "unavailable":
                gaps.append(str(item.get("title") or item.get("id")))
        if fundamentals.get("mode") == "historical_evidence_only":
            gaps.append("Desk 未提供截止日点时基本面快照，当前估值与综合评分已排除")
        bias = str((technical.get("insight") or {}).get("bias") or "neutral")
        headline = str((technical.get("insight") or {}).get("headline") or "").strip()
        trend_strength = float((technical.get("summary") or {}).get("trend_strength") or 0)
        insufficient_history = technical.get("conclusion_state") == "insufficient_history"
        if insufficient_history:
            gaps.append(
                f"技术结构：仅 {technical.get('actual_bars', 0)} 根 K 线，"
                "保留结构事实但不形成方向结论"
            )
        elif bias == "bullish":
            strengths.append(f"技术结构：{headline or '结构偏强'}")
        elif bias == "bearish":
            tensions.append(f"技术结构：{headline or '结构偏弱'}")
        elif trend_strength < 35:
            gaps.append("技术结构趋势强度偏低，方向确认不足")

        alerts = (event_flow or {}).get("alerts") or []
        positive_events = [item for item in alerts if item.get("direction") == "positive"]
        negative_events = [item for item in alerts if item.get("direction") == "negative"]
        if positive_events:
            top = max(positive_events, key=lambda item: float(item.get("intensity_score") or 0))
            strengths.append(f"事件证据：{top.get('title') or '存在正向观察证据'}")
        if negative_events:
            top = max(negative_events, key=lambda item: float(item.get("intensity_score") or 0))
            tensions.append(f"事件风险：{top.get('title') or '存在负向观察证据'}")

        exposure = (industry_chain or {}).get("exposure") or {}
        if exposure:
            layer = exposure.get("layer") or {}
            layer_name = str(layer.get("name") or exposure.get("layer_id") or "产业链暴露")
            confidence = str(exposure.get("confidence") or "unknown")
            priority = str(exposure.get("research_priority") or "worth_tracking")
            if confidence in {"high", "medium"} and priority in {"top_priority", "high_priority", "worth_tracking"}:
                strengths.append(f"产业链：{layer_name}暴露已核验（{confidence} 置信）")
            else:
                gaps.append(f"产业链：{layer_name}暴露证据置信度仍低")
            for text in (exposure.get("invalidation") or [])[:2]:
                tensions.append(f"产业链证伪：{text}")

        strengths = list(dict.fromkeys(strengths))
        tensions = list(dict.fromkeys(tensions))
        gaps = list(dict.fromkeys(gaps))
        invalidation_conditions = []
        for item in scorecard:
            if item.get("status") == "strong":
                title = str(item.get("title") or item.get("id") or "基本面优势")
                invalidation_conditions.append(
                    f"基本面：{title}由强转弱，且连续两个报告期未恢复"
                )
        if insufficient_history:
            invalidation_conditions.append(
                f"技术结构：补足至少 {technical.get('minimum_direction_bars', 80)} 根 K 线后重新评估方向"
            )
        elif bias == "bullish":
            invalidation_conditions.append(
                "技术结构：CZSC 偏强结构失效并转为明确偏弱"
            )
        elif bias == "bearish":
            invalidation_conditions.append(
                "技术结构：偏弱结构持续且未出现有效反转确认"
            )
        if positive_events:
            top = max(
                positive_events,
                key=lambda item: float(item.get("intensity_score") or 0),
            )
            invalidation_conditions.append(
                f"事件证据：{top.get('title') or '正向事件'}被后续公告否定或失去时效"
            )
        invalidation_conditions.extend(
            f"产业链：{text}" for text in (exposure.get("invalidation") or [])[:3]
        )
        if not invalidation_conditions:
            invalidation_conditions.append(
                "核心证据仍不足，若后续没有新增可核验证据则停止跟踪"
            )
        invalidation_conditions = list(dict.fromkeys(invalidation_conditions))
        if insufficient_history:
            conclusion = "技术历史不足，当前只保留结构事实，不形成综合方向判断"
        elif strengths and tensions:
            conclusion = "多维证据存在分歧：优势与风险同时成立，需优先核验张力项"
        elif tensions:
            conclusion = "当前风险与负向证据更集中，等待技术或基本面重新确认"
        elif strengths:
            conclusion = "现有多维证据偏正向，但仍需按证伪条件持续跟踪"
        else:
            conclusion = "证据不足，暂不形成方向判断"
        return {
            "technical_bias": bias,
            "strengths": strengths,
            "tensions": tensions,
            "gaps": gaps,
            "invalidation_conditions": invalidation_conditions,
            "evidence_balance": {
                "strength_count": len(strengths),
                "tension_count": len(tensions),
                "gap_count": len(gaps),
                "event_count": len(alerts),
                "industry_chain_attached": bool(exposure),
            },
            "conclusion": conclusion,
        }

    @staticmethod
    def _industry_chain(
        snapshot_id: Optional[str],
        symbol: str,
        *,
        as_of: Optional[str] = None,
    ):
        return resolve_industry_chain_snapshot(snapshot_id, symbol=symbol, as_of=as_of)

    def _build_snapshot(
        self,
        result,
        *,
        equity,
        technical_snapshot,
        symbol,
        period,
        bars,
        requested_as_of,
        industry_chain_snapshot_id,
        event_flow_snapshot_id,
    ):
        digest_result = dict(result)
        technical_for_digest = dict(digest_result.get("technical") or {})
        technical_for_digest.pop("chart", None)
        digest_result["technical"] = technical_for_digest
        input_summary = {
            "equity_schema": equity.get("schemaVersion"),
            "equity_generated_at": equity.get("generatedAt"),
            "technical_snapshot_id": technical_snapshot.get("snapshot_id"),
            "industry_chain_snapshot_id": industry_chain_snapshot_id,
            "event_flow_snapshot_id": event_flow_snapshot_id,
            "fundamental_mode": result["fundamentals"].get("mode"),
            "disclosure_as_of_mode": result["disclosures"].get("as_of_mode"),
        }
        input_digest = self._digest(input_summary)
        result_digest = self._digest(digest_result)
        snapshot_hash = self._digest({
            "analysis": self.engine_name,
            "version": self.engine_version,
            "parameters": {"symbol": symbol, "period": period, "bars": bars, "asOf": requested_as_of},
            "input": input_digest,
            "result": result_digest,
        }).split(":", 1)[1]
        end_date = result["as_of"]
        lag_days = max((date.today() - pd.Timestamp(end_date).date()).days, 0)
        if requested_as_of:
            freshness = {
                "state": "historical",
                "resolution": (
                    "partial_point_in_time"
                    if result["fundamentals"].get("mode") == "historical_evidence_only"
                    else "point_in_time"
                ),
                "calendar_lag_days": lag_days,
            }
        else:
            freshness = {
                "state": "fresh" if lag_days <= 3 else "delayed",
                "resolution": "latest_composite",
                "calendar_lag_days": lag_days,
            }
        return {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "snapshot_id": f"{self.engine_name}:{snapshot_hash[:24]}",
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "analysis": {"name": self.engine_name, "version": self.engine_version},
            "parameters": {"symbol": symbol, "period": period, "bars": bars, "asOf": requested_as_of},
            "data_window": {"requested_as_of": requested_as_of, "start_date": None, "end_date": end_date, "coverage": result["data_state"]},
            "provenance": {
                "provider": self.provider.name,
                "endpoint": "research.equity-snapshot + market disclosures + market.ohlcv",
                "upstream_source": "newma-desk",
                "upstream_as_of": str(equity.get("generatedAt") or ""),
                "limitations": list(result["limitations"]),
            },
            "freshness": freshness,
            "input": {"digest": input_digest, "summary": input_summary},
            "result": {
                "digest": result_digest,
                "summary": {
                    "symbol": symbol,
                    "data_state": result["data_state"],
                    "technical_bias": result["assessment"]["technical_bias"],
                    "strengths": result["assessment"]["strengths"],
                    "tensions": result["assessment"]["tensions"],
                },
            },
        }

    @staticmethod
    def _digest(value: Any) -> str:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return f"sha256:{hashlib.sha256(encoded).hexdigest()}"

    @classmethod
    def _row_date(cls, item: Mapping[str, Any], fields: tuple[str, ...]) -> Optional[str]:
        for field in fields:
            value = cls._date_only(item.get(field))
            if value:
                return value
        return None

    @staticmethod
    def _date_only(value: Any) -> Optional[str]:
        if value is None or str(value).strip() == "":
            return None
        try:
            timestamp = pd.Timestamp(value)
        except (TypeError, ValueError):
            return None
        if pd.isna(timestamp):
            return None
        if timestamp.tzinfo is not None:
            timestamp = timestamp.tz_convert("Asia/Shanghai").tz_localize(None)
        return timestamp.strftime("%Y-%m-%d")
