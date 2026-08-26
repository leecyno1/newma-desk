#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Evidence-first market event and capital-flow normalization."""

from __future__ import annotations

import hashlib
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from typing import Any, Mapping

import pandas as pd

from instock.core.analysis_snapshot import (
    SNAPSHOT_SCHEMA_VERSION,
    get_analysis_snapshot_registry,
    normalize_as_of,
)
from instock.core.market_data_provider import (
    MarketDataError,
    MarketDataProvider,
    get_market_data_provider,
)


class EventFlowError(ValueError):
    """Raised when a Desk event request violates the module contract."""


class EventFlowEngine:
    engine_name = "instock-event-flow"
    engine_version = "1.1.0"
    packet_schema_version = "instock-event-flow-packet-v1"
    freshness_days = 30
    supported_markets = {"CN", "HK", "US", "GLOBAL"}
    supported_types = {
        "announcement", "news", "report", "fund_flow", "margin",
        "dragon_tiger", "block_trade", "holder_change", "dividend",
        "lockup", "limit_up", "northbound", "institutional_flow",
    }
    supported_directions = {"positive", "negative", "neutral"}
    strength_scores = {"strong": 90.0, "medium": 60.0, "weak": 30.0}
    symbol_pattern = re.compile(r"^[A-Za-z0-9.^_-]{1,32}$")
    cn_symbol_pattern = re.compile(r"^[0-9]{6}(?:\.(?:SH|SZ|BJ))?$", re.I)
    source_order = (
        "announcements", "reports", "news", "fund_flow", "margin",
        "dragon_tiger", "block_trade", "holders", "dividend", "lockup",
    )
    source_labels = {
        "announcements": "公司公告", "reports": "机构研报", "news": "市场新闻",
        "fund_flow": "主力资金", "margin": "融资融券", "dragon_tiger": "龙虎榜",
        "block_trade": "大宗交易", "holders": "股东户数",
        "dividend": "分红送转", "lockup": "限售解禁",
    }
    source_endpoints = {
        "announcements": "capability:market.announcements",
        "reports": "capability:market.reports",
        "news": "capability:market.news",
        "fund_flow": "/api/research/api/fund-flow",
        "margin": "/api/research/api/margin",
        "dragon_tiger": "/api/research/api/dragon-tiger",
        "block_trade": "/api/research/api/block-trade",
        "holders": "/api/research/api/holders",
        "dividend": "/api/research/api/dividend",
        "lockup": "/api/research/api/lockup",
    }

    def analyze_request(
        self,
        payload: Mapping[str, Any],
        *,
        provider: MarketDataProvider | None = None,
    ) -> dict[str, Any]:
        """Keep the packet contract while adding a direct A-share query mode."""

        if isinstance(payload, Mapping) and "symbol" in payload:
            unknown = set(payload) - {"symbol", "asOf"}
            if unknown:
                raise EventFlowError(
                    f"股票查询包含未知字段: {', '.join(sorted(unknown))}"
                )
            return self.analyze_symbol(
                payload.get("symbol"),
                as_of=payload.get("asOf"),
                provider=provider,
            )
        return self.analyze(payload)

    def analyze(
        self,
        packet: Mapping[str, Any],
        *,
        allow_empty: bool = False,
        input_mode: str = "packet",
        data_source: str = "newma-desk-agent",
        coverage: Mapping[str, Any] | None = None,
        failures: list[Mapping[str, Any]] | None = None,
        query: Mapping[str, Any] | None = None,
        provenance: Mapping[str, Any] | None = None,
        extra_limitations: list[str] | None = None,
    ) -> dict[str, Any]:
        payload = self._validate_packet(packet, allow_empty=allow_empty)
        parsed = [
            self._parse_event(item, payload["as_of"], index)
            for index, item in enumerate(payload["events"])
        ]
        alerts = sorted(
            self._deduplicate(parsed),
            key=lambda item: (
                -item["intensity_score"],
                -date.fromisoformat(item["occurred_at"]).toordinal(),
                item["id"],
            ),
        )
        symbol_summary = self._group_symbols(alerts)
        summary = {
            "input_events": len(parsed),
            "deduplicated_events": len(alerts),
            "duplicates_removed": len(parsed) - len(alerts),
            "fresh_events": sum(item["freshness"] == "fresh" for item in alerts),
            "stale_events": sum(item["freshness"] == "stale" for item in alerts),
            "symbols": len(symbol_summary),
            "top_event_id": alerts[0]["id"] if alerts else None,
        }
        normalized_failures = [dict(item) for item in (failures or [])]
        normalized_coverage = dict(coverage or self._packet_coverage(len(parsed)))
        limitations = [
            "event_magnitude_is_evidence_priority_not_a_return_forecast",
            "capital_flow_direction_describes_observed_evidence_not_expected_return",
            "capital_flow_fields_are_normalized_evidence_not_trade_instructions",
        ]
        if summary["stale_events"]:
            limitations.append("stale_events_retained_for_audit")
        if normalized_coverage.get("empty_sources"):
            limitations.append("empty_source_does_not_mean_no_market_activity")
        if normalized_failures:
            limitations.append("source_failures_retained_in_coverage")
        for item in extra_limitations or []:
            if item not in limitations:
                limitations.append(item)
        data_state = "partial" if (
            summary["stale_events"]
            or normalized_failures
            or normalized_coverage.get("empty_sources")
        ) else "complete"
        stable_result = {
            "summary": summary,
            "alerts": alerts,
            "symbol_summary": symbol_summary,
            "coverage": normalized_coverage,
            "failures": normalized_failures,
        }
        snapshot = self._build_snapshot(
            payload,
            stable_result,
            limitations,
            data_source=data_source,
            data_state=data_state,
            input_mode=input_mode,
            query=dict(query or {}),
            provenance=dict(provenance or {}),
        )
        get_analysis_snapshot_registry().register(snapshot)
        return {
            "engine": {
                "name": self.engine_name,
                "version": self.engine_version,
                "methodology": "magnitude_65_evidence_25_freshness_10",
            },
            "schema_version": self.packet_schema_version,
            "input_mode": input_mode,
            "query": dict(query or {}),
            "market": payload["market"],
            "as_of": payload["as_of"],
            "data_source": data_source,
            "data_state": data_state,
            "summary": summary,
            "coverage": normalized_coverage,
            "alerts": alerts,
            "symbol_summary": symbol_summary,
            "failures": normalized_failures,
            "limitations": limitations,
            "snapshot": snapshot,
        }

    def analyze_symbol(
        self,
        symbol: Any,
        *,
        as_of: Any = None,
        provider: MarketDataProvider | None = None,
    ) -> dict[str, Any]:
        raw_symbol = str(symbol or "").strip().upper()
        if not self.cn_symbol_pattern.fullmatch(raw_symbol):
            raise EventFlowError("symbol 必须是 6 位 A 股代码，可带 SH、SZ 或 BJ 后缀")
        code = raw_symbol.split(".")[0]
        try:
            normalized_as_of = normalize_as_of(as_of, reject_future=True) or date.today().isoformat()
        except ValueError as exc:
            raise EventFlowError(str(exc)) from exc
        data_provider = provider or get_market_data_provider()
        sources, failures = self._collect_desk_sources(data_provider, code)
        if not any(item.get("state") in {"available", "empty"} for item in sources.values()):
            raise MarketDataError("Newma-Desk 事件与资金数据源全部不可用")

        events = []
        for source_id in self.source_order:
            source = sources.get(source_id) or {}
            if source.get("state") != "available":
                continue
            normalizer = getattr(self, f"_normalize_{source_id}")
            events.extend(normalizer(code, normalized_as_of, source.get("data")))
        coverage = self._source_coverage(sources)
        packet = {
            "schema_version": self.packet_schema_version,
            "as_of": normalized_as_of,
            "market": "CN",
            "events": events[:500],
        }
        limitations = ["desk_research_interfaces_are_latest_window_without_historical_anchor"]
        if normalized_as_of != date.today().isoformat():
            limitations.append("historical_event_replay_is_client_filtered_from_latest_desk_payloads")
        return self.analyze(
            packet,
            allow_empty=True,
            input_mode="desk_symbol",
            data_source="newma-desk-research",
            coverage=coverage,
            failures=failures,
            query={"symbol": code},
            provenance={
                "provider": "newma-desk",
                "endpoint": "Desk Research HTTP Interface + market data capabilities",
                "upstream_source": "Tushare/Eastmoney/Tencent via Newma-Desk",
            },
            extra_limitations=limitations,
        )

    def _collect_desk_sources(
        self,
        provider: MarketDataProvider,
        code: str,
    ) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
        jobs = {
            "capital": lambda: provider.get_security_event_flow(code),
            "announcements": lambda: provider.get_security_announcements(code),
            "reports": lambda: provider.get_security_reports(code, pages=1),
            "news": lambda: provider.get_security_news(code, limit=20),
        }
        results: dict[str, Any] = {}
        errors: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="event-flow") as executor:
            futures = {executor.submit(job): name for name, job in jobs.items()}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    results[name] = future.result()
                except MarketDataError as exc:
                    errors[name] = str(exc)

        sources: dict[str, dict[str, Any]] = {}
        failures: list[dict[str, Any]] = []
        capital = results.get("capital")
        if isinstance(capital, Mapping):
            for source_id, item in (capital.get("sources") or {}).items():
                if isinstance(item, Mapping):
                    sources[str(source_id)] = dict(item)
            failures.extend(
                dict(item) for item in (capital.get("failures") or [])
                if isinstance(item, Mapping)
            )
        else:
            message = errors.get("capital", "Desk 资金接口未返回数据")
            for source_id in self.source_order[3:]:
                sources[source_id] = self._failed_source(source_id, message)
                failures.append(self._failure(source_id, message))

        capability_units = {
            "announcements": {"record": "公告"},
            "reports": {"record": "研报"},
            "news": {"record": "新闻"},
        }
        for source_id in self.source_order[:3]:
            data = results.get(source_id)
            if isinstance(data, list):
                sources[source_id] = {
                    "id": source_id,
                    "label": self.source_labels[source_id],
                    "state": "available" if data else "empty",
                    "endpoint": self.source_endpoints[source_id],
                    "units": capability_units[source_id],
                    "records": len(data),
                    "data": data,
                }
            else:
                message = errors.get(source_id, f"Desk {self.source_labels[source_id]}未返回数据")
                sources[source_id] = self._failed_source(source_id, message)
                failures.append(self._failure(source_id, message))
        for source_id in self.source_order:
            sources.setdefault(
                source_id,
                self._failed_source(source_id, "Desk 数据源未声明覆盖"),
            )
        return sources, failures

    def _failed_source(self, source_id: str, message: str) -> dict[str, Any]:
        return {
            "id": source_id,
            "label": self.source_labels[source_id],
            "state": "failed",
            "endpoint": self.source_endpoints[source_id],
            "units": {},
            "records": 0,
            "data": None,
            "message": message,
        }

    def _failure(self, source_id: str, message: str) -> dict[str, Any]:
        return {
            "source": source_id,
            "label": self.source_labels[source_id],
            "endpoint": self.source_endpoints[source_id],
            "message": message,
        }

    def _source_coverage(self, sources: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
        rows = []
        for source_id in self.source_order:
            source = dict(sources.get(source_id) or {})
            units = source.get("units") if isinstance(source.get("units"), Mapping) else {}
            rows.append({
                "id": source_id,
                "label": str(source.get("label") or self.source_labels[source_id]),
                "state": str(source.get("state") or "failed"),
                "records": int(source.get("records") or 0),
                "latest_date": self._latest_date(source.get("data")),
                "endpoint": str(source.get("endpoint") or self.source_endpoints[source_id]),
                "units": dict(units),
            })
        return {
            "mode": "desk_symbol",
            "requested_sources": len(rows),
            "available_sources": sum(item["state"] == "available" for item in rows),
            "empty_sources": sum(item["state"] == "empty" for item in rows),
            "failed_sources": sum(item["state"] == "failed" for item in rows),
            "records": sum(item["records"] for item in rows),
            "sources": rows,
        }

    @staticmethod
    def _packet_coverage(event_count: int) -> dict[str, Any]:
        return {
            "mode": "host_packet",
            "requested_sources": 1,
            "available_sources": 1,
            "empty_sources": 0,
            "failed_sources": 0,
            "records": event_count,
            "sources": [{
                "id": "host_packet",
                "label": "宿主事件包",
                "state": "available",
                "records": event_count,
                "latest_date": None,
                "endpoint": "host-action-input",
                "units": {},
            }],
        }

    def _normalize_announcements(self, symbol: str, as_of: str, data: Any) -> list[dict[str, Any]]:
        events = []
        for index, row in enumerate(self._dated_rows(data, as_of, ("date",))[:10]):
            title = str(row.get("title") or "公司公告").strip()
            category = str(row.get("type") or "公告").strip()
            url = str(row.get("url") or "").strip()
            events.append(self._event(
                "announcement", symbol, row["_date"], title, "neutral", 55, "strong",
                url or f"desk://announcement/{symbol}/{row['_date']}/{index}",
                {"category": category, "url": url or None},
            ))
        return events

    def _normalize_reports(self, symbol: str, as_of: str, data: Any) -> list[dict[str, Any]]:
        events = []
        for index, row in enumerate(self._dated_rows(data, as_of, ("publishDate", "date"))[:8]):
            title = str(row.get("title") or "机构研报").strip()
            organization = str(row.get("orgSName") or row.get("orgName") or "").strip()
            rating = str(row.get("emRatingName") or row.get("sRatingName") or "").strip()
            url = str(row.get("pdfUrl") or "").strip()
            events.append(self._event(
                "report", symbol, row["_date"], title, "neutral", 45, "medium",
                url or f"desk://report/{symbol}/{row.get('infoCode') or index}",
                {"organization": organization or None, "rating": rating or None, "url": url or None},
            ))
        return events

    def _normalize_news(self, symbol: str, as_of: str, data: Any) -> list[dict[str, Any]]:
        events = []
        for index, row in enumerate(self._dated_rows(data, as_of, ("发布时间", "date"))[:10]):
            title = str(row.get("新闻标题") or row.get("title") or "市场新闻").strip()
            source = str(row.get("文章来源") or row.get("source") or "").strip()
            url = str(row.get("新闻链接") or row.get("url") or "").strip()
            events.append(self._event(
                "news", symbol, row["_date"], title, "neutral", 35, "weak",
                url or f"desk://news/{symbol}/{row['_date']}/{index}",
                {"publisher": source or None, "url": url or None},
            ))
        return events

    def _normalize_fund_flow(self, symbol: str, as_of: str, data: Any) -> list[dict[str, Any]]:
        rows = self._dated_rows(data, as_of, ("date",))
        if not rows:
            return []
        values = [self._number(row.get("main_net")) for row in rows]
        five_day = sum(values[:5])
        twenty_day = sum(values[:20])
        rolling = [sum(values[index:index + 5]) for index in range(max(len(values) - 4, 1))]
        magnitude = self._percentile(abs(five_day), [abs(value) for value in rolling])
        latest = rows[0]
        direction = self._direction(five_day)
        title = (
            f"近5日主力资金{self._flow_word(five_day)} {self._format_cny(abs(five_day))}；"
            f"近20日净额 {self._format_signed_cny(twenty_day)}"
        )
        return [self._event(
            "fund_flow", symbol, latest["_date"], title, direction, magnitude,
            "strong" if len(rows) >= 20 else "medium" if len(rows) >= 5 else "weak",
            f"desk://research/fund-flow/{symbol}/{latest['_date']}",
            {
                "main_net_5d_cny": round(five_day, 2),
                "main_net_20d_cny": round(twenty_day, 2),
                "latest_main_net_cny": round(values[0], 2),
                "five_day_abs_percentile_pct": round(magnitude, 2),
            },
        )]

    def _normalize_margin(self, symbol: str, as_of: str, data: Any) -> list[dict[str, Any]]:
        rows = self._dated_rows(data, as_of, ("date",))
        if not rows:
            return []
        daily_net = [self._number(row.get("rzmre")) - self._number(row.get("rzche")) for row in rows]
        five_day = sum(daily_net[:5])
        rolling = [sum(daily_net[index:index + 5]) for index in range(max(len(daily_net) - 4, 1))]
        magnitude = self._percentile(abs(five_day), [abs(value) for value in rolling])
        latest = rows[0]
        balance = self._number(latest.get("rzye"))
        title = (
            f"融资余额 {self._format_cny(balance)}；"
            f"近5日融资{self._flow_word(five_day)} {self._format_cny(abs(five_day))}"
        )
        return [self._event(
            "margin", symbol, latest["_date"], title, self._direction(five_day), magnitude,
            "strong" if len(rows) >= 20 else "medium",
            f"desk://research/margin/{symbol}/{latest['_date']}",
            {
                "financing_balance_cny": round(balance, 2),
                "financing_net_5d_cny": round(five_day, 2),
                "securities_lending_balance_cny": round(self._number(latest.get("rqye")), 2),
                "five_day_abs_percentile_pct": round(magnitude, 2),
            },
        )]

    def _normalize_dragon_tiger(self, symbol: str, as_of: str, data: Any) -> list[dict[str, Any]]:
        if not isinstance(data, Mapping):
            return []
        rows = self._dated_rows(data.get("records"), as_of, ("date",))
        if not rows:
            return []
        latest = rows[0]
        institution = data.get("institution") if isinstance(data.get("institution"), Mapping) else {}
        institution_net = self._number(institution.get("net_amt"))
        net_wan = institution_net if institution_net else self._number(latest.get("net_buy"))
        label = "机构席位净额" if institution_net else "榜单净买额"
        title = (
            f"龙虎榜：{str(latest.get('reason') or '交易公开信息').strip()}；"
            f"{label} {net_wan:+,.1f} 万元"
        )
        return [self._event(
            "dragon_tiger", symbol, latest["_date"], title, self._direction(net_wan),
            self._amount_priority(abs(net_wan) * 10_000),
            "strong" if institution_net else "medium",
            f"desk://research/dragon-tiger/{symbol}/{latest['_date']}",
            {
                "net_buy_cny_10k": round(self._number(latest.get("net_buy")), 2),
                "institution_net_cny_10k": round(institution_net, 2),
                "turnover_pct": round(self._number(latest.get("turnover")), 2),
            },
        )]

    def _normalize_block_trade(self, symbol: str, as_of: str, data: Any) -> list[dict[str, Any]]:
        rows = self._dated_rows(data, as_of, ("date",))
        if not rows:
            return []
        latest_date = rows[0]["_date"]
        latest_rows = [row for row in rows if row["_date"] == latest_date]
        amount = sum(self._number(row.get("amount")) for row in latest_rows)
        weighted_premium = (
            sum(self._number(row.get("premium_pct")) * self._number(row.get("amount")) for row in latest_rows)
            / amount if amount else 0.0
        )
        direction = "positive" if weighted_premium > 0.5 else "negative" if weighted_premium < -0.5 else "neutral"
        title = (
            f"大宗交易 {len(latest_rows)} 笔，成交额 {self._format_cny(amount)}；"
            f"加权折溢价 {weighted_premium:+.2f}%"
        )
        return [self._event(
            "block_trade", symbol, latest_date, title, direction,
            self._amount_priority(amount), "strong",
            f"desk://research/block-trade/{symbol}/{latest_date}",
            {
                "trade_count": len(latest_rows),
                "amount_cny": round(amount, 2),
                "weighted_premium_pct": round(weighted_premium, 2),
            },
        )]

    def _normalize_holders(self, symbol: str, as_of: str, data: Any) -> list[dict[str, Any]]:
        rows = self._dated_rows(data, as_of, ("date",))
        if not rows:
            return []
        latest = rows[0]
        ratio = self._number(latest.get("change_ratio"))
        direction = "positive" if ratio < 0 else "negative" if ratio > 0 else "neutral"
        movement = "减少" if ratio < 0 else "增加" if ratio > 0 else "持平"
        title = (
            f"股东户数 {self._number(latest.get('holder_num')):,.0f} 户，"
            f"环比{movement} {abs(ratio):.2f}%"
        )
        return [self._event(
            "holder_change", symbol, latest["_date"], title, direction,
            min(95.0, 30.0 + abs(ratio) * 4.0), "strong",
            f"desk://research/holders/{symbol}/{latest['_date']}",
            {
                "holder_count": round(self._number(latest.get("holder_num")), 2),
                "holder_change_pct": round(ratio, 4),
                "average_shares_per_holder": round(self._number(latest.get("avg_shares")), 2),
            },
        )]

    def _normalize_dividend(self, symbol: str, as_of: str, data: Any) -> list[dict[str, Any]]:
        events = []
        for row in self._dated_rows(data, as_of, ("date",))[:2]:
            cash = self._number(row.get("bonus_rmb"))
            transfer = self._number(row.get("transfer_ratio"))
            bonus = self._number(row.get("bonus_ratio"))
            title = f"分红送转：每10股派 {cash:g} 元、转增 {transfer:g} 股、送 {bonus:g} 股"
            events.append(self._event(
                "dividend", symbol, row["_date"], title, "neutral", 45, "strong",
                f"desk://research/dividend/{symbol}/{row['_date']}",
                {
                    "cash_dividend_cny_per_10_shares": cash,
                    "transfer_shares_per_10": transfer,
                    "bonus_shares_per_10": bonus,
                    "plan": str(row.get("plan") or "") or None,
                },
            ))
        return events

    def _normalize_lockup(self, symbol: str, as_of: str, data: Any) -> list[dict[str, Any]]:
        if not isinstance(data, Mapping):
            return []
        if as_of == date.today().isoformat():
            upcoming = self._future_rows(data.get("upcoming"), as_of, ("date",))
            if upcoming:
                row = upcoming[0]
                ratio = self._number(row.get("ratio"))
                able_shares = self._number(row.get("able_shares"))
                direction = "negative" if ratio >= 0.05 else "neutral"
                title = (
                    f"未来解禁：{row['_date']} {str(row.get('type') or '限售股份')}，"
                    f"实际可流通约 {able_shares:,.2f} 万股，占比 {ratio:.2%}"
                )
                return [self._event(
                    "lockup", symbol, as_of, title, direction,
                    min(95.0, 40.0 + ratio * 300.0), "strong",
                    f"desk://research/lockup/{symbol}/{row['_date']}",
                    {
                        "effective_at": row["_date"],
                        "able_shares_10k": round(able_shares, 4),
                        "unlock_ratio": round(ratio, 8),
                        "share_type": str(row.get("type") or "") or None,
                    },
                )]
        history = self._dated_rows(data.get("history"), as_of, ("date",))
        if not history:
            return []
        row = history[0]
        ratio = self._number(row.get("ratio"))
        title = (
            f"最近解禁记录：{str(row.get('type') or '限售股份')}，"
            f"实际可流通约 {self._number(row.get('able_shares')):,.2f} 万股，占比 {ratio:.2%}"
        )
        return [self._event(
            "lockup", symbol, row["_date"], title, "neutral", min(80.0, 35.0 + ratio * 200.0),
            "strong", f"desk://research/lockup/{symbol}/{row['_date']}",
            {
                "able_shares_10k": round(self._number(row.get("able_shares")), 4),
                "unlock_ratio": round(ratio, 8),
                "share_type": str(row.get("type") or "") or None,
            },
        )]

    def _event(
        self,
        event_type: str,
        symbol: str,
        occurred_at: str,
        title: str,
        direction: str,
        magnitude: float,
        strength: str,
        source_ref: str,
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        digest = hashlib.sha256(source_ref.encode("utf-8")).hexdigest()[:12]
        return {
            "id": f"{event_type}-{symbol}-{digest}",
            "type": event_type,
            "symbol": symbol,
            "occurred_at": occurred_at,
            "title": str(title)[:300],
            "direction": direction,
            "magnitude_score": round(max(0.0, min(float(magnitude), 100.0)), 2),
            "evidence_strength": strength,
            "source_ref": source_ref,
            "details": dict(details or {}),
        }

    def _validate_packet(self, packet: Mapping[str, Any], *, allow_empty: bool = False) -> dict[str, Any]:
        if not isinstance(packet, Mapping):
            raise EventFlowError("事件资金请求必须是 JSON 对象")
        required = {"schema_version", "as_of", "market", "events"}
        missing, unknown = required - set(packet), set(packet) - required
        if missing:
            raise EventFlowError(f"事件资金包缺少字段: {', '.join(sorted(missing))}")
        if unknown:
            raise EventFlowError(f"事件资金包包含未知字段: {', '.join(sorted(unknown))}")
        if packet.get("schema_version") != self.packet_schema_version:
            raise EventFlowError(f"schema_version 必须是 {self.packet_schema_version}")
        try:
            as_of = normalize_as_of(packet.get("as_of"), reject_future=True)
        except ValueError as exc:
            raise EventFlowError(str(exc)) from exc
        if not as_of:
            raise EventFlowError("as_of 不能为空")
        market = str(packet.get("market") or "").upper()
        if market not in self.supported_markets:
            raise EventFlowError("market 仅支持 CN、HK、US、GLOBAL")
        events = packet.get("events")
        minimum = 0 if allow_empty else 1
        if not isinstance(events, list) or not minimum <= len(events) <= 500:
            raise EventFlowError(f"events 数量必须在 {minimum} 到 500 之间")
        return {"as_of": as_of, "market": market, "events": events}

    def _parse_event(self, raw: Any, as_of: str, index: int) -> dict[str, Any]:
        context = f"events[{index}]"
        if not isinstance(raw, Mapping):
            raise EventFlowError(f"{context} 必须是对象")
        required = {
            "id", "type", "symbol", "occurred_at", "title", "direction",
            "magnitude_score", "evidence_strength", "source_ref",
        }
        optional = {"details"}
        missing, unknown = required - set(raw), set(raw) - required - optional
        if missing:
            raise EventFlowError(f"{context} 缺少字段: {', '.join(sorted(missing))}")
        if unknown:
            raise EventFlowError(f"{context} 包含未知字段: {', '.join(sorted(unknown))}")
        event_type = str(raw["type"] or "").strip().lower()
        if event_type not in self.supported_types:
            raise EventFlowError(f"{context} 事件类型不支持")
        direction = str(raw["direction"] or "").strip().lower()
        if direction not in self.supported_directions:
            raise EventFlowError(f"{context}.direction 仅支持 positive、negative、neutral")
        strength = str(raw["evidence_strength"] or "").strip().lower()
        if strength not in self.strength_scores:
            raise EventFlowError(f"{context}.evidence_strength 仅支持 strong、medium、weak")
        symbol = str(raw["symbol"] or "").strip().upper()
        if not self.symbol_pattern.fullmatch(symbol):
            raise EventFlowError(f"{context}.symbol 格式无效")
        try:
            occurred_at = normalize_as_of(raw["occurred_at"])
        except ValueError as exc:
            raise EventFlowError(f"{context}.occurred_at: {exc}") from exc
        if not occurred_at:
            raise EventFlowError(f"{context}.occurred_at 不能为空")
        if occurred_at > as_of:
            raise EventFlowError(f"{context}.occurred_at 晚于 as_of")
        try:
            magnitude = float(raw["magnitude_score"])
        except (TypeError, ValueError) as exc:
            raise EventFlowError(f"{context}.magnitude_score 必须是 0..100 数字") from exc
        if not math.isfinite(magnitude) or not 0 <= magnitude <= 100:
            raise EventFlowError(f"{context}.magnitude_score 必须在 0..100 之间")
        details = self._parse_details(raw.get("details"), f"{context}.details")
        age_days = max((pd.Timestamp(as_of) - pd.Timestamp(occurred_at)).days, 0)
        freshness_score = max(0.0, 100 * (1 - age_days / self.freshness_days))
        intensity = magnitude * 0.65 + self.strength_scores[strength] * 0.25 + freshness_score * 0.10
        return {
            "id": self._text(raw["id"], f"{context}.id", 120),
            "type": event_type,
            "symbol": symbol,
            "occurred_at": occurred_at,
            "title": self._text(raw["title"], f"{context}.title", 300),
            "direction": direction,
            "magnitude_score": round(magnitude, 2),
            "evidence_strength": strength,
            "source_ref": self._text(raw["source_ref"], f"{context}.source_ref", 500),
            "details": details,
            "age_days": age_days,
            "freshness": "fresh" if age_days <= self.freshness_days else "stale",
            "intensity_score": round(intensity, 2),
        }

    @staticmethod
    def _parse_details(value: Any, context: str) -> dict[str, Any]:
        if value in (None, {}):
            return {}
        if not isinstance(value, Mapping) or len(value) > 20:
            raise EventFlowError(f"{context} 必须是最多 20 项的对象")
        output = {}
        for key, item in value.items():
            name = str(key or "").strip()
            if not name or len(name) > 80:
                raise EventFlowError(f"{context} 字段名无效")
            if isinstance(item, float) and not math.isfinite(item):
                raise EventFlowError(f"{context}.{name} 必须是有限数值")
            if item is not None and not isinstance(item, (str, int, float, bool)):
                raise EventFlowError(f"{context}.{name} 仅支持标量值")
            output[name] = item
        return output

    @staticmethod
    def _deduplicate(events):
        selected = {}
        for item in events:
            current = selected.get(item["source_ref"])
            if current is None or item["intensity_score"] > current["intensity_score"]:
                selected[item["source_ref"]] = item
        return list(selected.values())

    @staticmethod
    def _group_symbols(alerts):
        grouped = {}
        for item in alerts:
            grouped.setdefault(item["symbol"], []).append(item)
        output = []
        for symbol, items in grouped.items():
            positive = [item for item in items if item["direction"] == "positive"]
            negative = [item for item in items if item["direction"] == "negative"]
            positive_score = sum(item["intensity_score"] for item in positive)
            negative_score = sum(item["intensity_score"] for item in negative)
            output.append({
                "symbol": symbol,
                "event_count": len(items),
                "positive_events": len(positive),
                "negative_events": len(negative),
                "positive_intensity": round(positive_score, 2),
                "negative_intensity": round(negative_score, 2),
                "net_intensity": round(positive_score - negative_score, 2),
                "top_event_id": max(items, key=lambda item: item["intensity_score"])["id"],
            })
        return sorted(
            output,
            key=lambda item: (-max(item["positive_intensity"], item["negative_intensity"]), item["symbol"]),
        )

    def _build_snapshot(
        self,
        packet,
        result,
        limitations,
        *,
        data_source,
        data_state,
        input_mode,
        query,
        provenance,
    ):
        input_digest, result_digest = self._digest(packet), self._digest(result)
        snapshot_hash = self._digest({
            "analysis": self.engine_name,
            "version": self.engine_version,
            "as_of": packet["as_of"],
            "input": input_digest,
            "result": result_digest,
        }).split(":", 1)[1]
        lag_days = max((date.today() - pd.Timestamp(packet["as_of"]).date()).days, 0)
        return {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "snapshot_id": f"{self.engine_name}:{snapshot_hash[:24]}",
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "analysis": {"name": self.engine_name, "version": self.engine_version},
            "parameters": {
                "market": packet["market"],
                "asOf": packet["as_of"],
                "freshnessDays": self.freshness_days,
                "inputMode": input_mode,
                **query,
            },
            "data_window": {
                "requested_as_of": packet["as_of"],
                "start_date": None,
                "end_date": packet["as_of"],
                "coverage": data_state,
            },
            "provenance": {
                "provider": str(provenance.get("provider") or data_source),
                "endpoint": str(provenance.get("endpoint") or "host-action-input"),
                "upstream_source": str(provenance.get("upstream_source") or "structured-event-flow-packet"),
                "upstream_as_of": packet["as_of"],
                "limitations": limitations,
            },
            "freshness": {
                "state": "current" if lag_days <= 3 else "historical",
                "resolution": "point_in_time",
                "calendar_lag_days": lag_days,
            },
            "input": {
                "digest": input_digest,
                "summary": {
                    "market": packet["market"],
                    "as_of": packet["as_of"],
                    "event_count": len(packet["events"]),
                    "input_mode": input_mode,
                    **query,
                },
            },
            "result": {
                "digest": result_digest,
                "summary": result["summary"],
                "evidence": {
                    "alerts": [dict(item) for item in result["alerts"]],
                    "symbol_summary": [dict(item) for item in result["symbol_summary"]],
                    "coverage": dict(result["coverage"]),
                    "failures": [dict(item) for item in result["failures"]],
                },
            },
        }

    @staticmethod
    def _dated_rows(data: Any, as_of: str, keys: tuple[str, ...]) -> list[dict[str, Any]]:
        rows = []
        for raw in data if isinstance(data, list) else []:
            if not isinstance(raw, Mapping):
                continue
            normalized = EventFlowEngine._row_date(raw, keys)
            if normalized and normalized <= as_of:
                rows.append({**dict(raw), "_date": normalized})
        return sorted(rows, key=lambda row: row["_date"], reverse=True)

    @staticmethod
    def _future_rows(data: Any, as_of: str, keys: tuple[str, ...]) -> list[dict[str, Any]]:
        rows = []
        for raw in data if isinstance(data, list) else []:
            if not isinstance(raw, Mapping):
                continue
            normalized = EventFlowEngine._row_date(raw, keys)
            if normalized and normalized > as_of:
                rows.append({**dict(raw), "_date": normalized})
        return sorted(rows, key=lambda row: row["_date"])

    @staticmethod
    def _row_date(row: Mapping[str, Any], keys: tuple[str, ...]) -> str | None:
        for key in keys:
            value = row.get(key)
            if value in (None, ""):
                continue
            parsed = pd.to_datetime(value, errors="coerce")
            if not pd.isna(parsed):
                return parsed.strftime("%Y-%m-%d")
        return None

    @classmethod
    def _latest_date(cls, data: Any) -> str | None:
        dates = []
        if isinstance(data, list):
            for row in data:
                if isinstance(row, Mapping):
                    value = cls._row_date(row, ("date", "publishDate", "发布时间"))
                    if value:
                        dates.append(value)
        elif isinstance(data, Mapping):
            for key in ("records", "history", "upcoming"):
                value = cls._latest_date(data.get(key))
                if value:
                    dates.append(value)
        return max(dates) if dates else None

    @staticmethod
    def _number(value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        return number if math.isfinite(number) else 0.0

    @staticmethod
    def _percentile(value: float, population: list[float]) -> float:
        numbers = [float(item) for item in population if math.isfinite(float(item))]
        if not numbers:
            return 0.0
        return round(100.0 * sum(item <= value for item in numbers) / len(numbers), 2)

    @staticmethod
    def _amount_priority(amount_cny: float) -> float:
        if amount_cny <= 0:
            return 30.0
        return round(min(95.0, 35.0 + 12.0 * math.log10(max(amount_cny / 1_000_000, 1.0))), 2)

    @staticmethod
    def _direction(value: float) -> str:
        return "positive" if value > 0 else "negative" if value < 0 else "neutral"

    @staticmethod
    def _flow_word(value: float) -> str:
        return "净流入" if value > 0 else "净流出" if value < 0 else "净额持平"

    @staticmethod
    def _format_cny(value: float) -> str:
        value = abs(float(value))
        if value >= 100_000_000:
            return f"{value / 100_000_000:,.2f} 亿元"
        if value >= 10_000:
            return f"{value / 10_000:,.0f} 万元"
        return f"{value:,.0f} 元"

    @classmethod
    def _format_signed_cny(cls, value: float) -> str:
        prefix = "+" if value > 0 else "-" if value < 0 else ""
        return f"{prefix}{cls._format_cny(abs(value))}"

    @staticmethod
    def _text(value: Any, context: str, maximum: int) -> str:
        text = str(value or "").strip()
        if not text:
            raise EventFlowError(f"{context} 不能为空")
        if len(text) > maximum:
            raise EventFlowError(f"{context} 长度不能超过 {maximum}")
        return text

    @staticmethod
    def _digest(value: Any) -> str:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def resolve_event_flow_snapshot(
    snapshot_id: str | None,
    *,
    symbols: list[str] | tuple[str, ...] | set[str] | None = None,
    as_of: str | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Resolve reusable security-level evidence from an Event Flow Snapshot."""

    if not snapshot_id:
        return None, []
    snapshot = get_analysis_snapshot_registry().get(snapshot_id)
    if snapshot is None:
        return None, ["event_flow_snapshot_not_found"]
    if (snapshot.get("analysis") or {}).get("name") != EventFlowEngine.engine_name:
        return None, ["event_flow_snapshot_type_mismatch"]
    evidence = (snapshot.get("result") or {}).get("evidence") or {}
    if not evidence:
        return None, ["event_flow_snapshot_evidence_unavailable"]
    snapshot_as_of = (snapshot.get("data_window") or {}).get("end_date")
    try:
        requested_as_of = normalize_as_of(as_of) if as_of else None
    except ValueError:
        return None, ["event_flow_snapshot_as_of_invalid"]
    if requested_as_of and snapshot_as_of and snapshot_as_of < requested_as_of:
        return None, ["event_flow_snapshot_older_than_research_as_of"]
    selected = {
        str(symbol or "").strip().upper().split(".")[0]
        for symbol in (symbols or [])
        if str(symbol or "").strip()
    }
    alerts = []
    for item in evidence.get("alerts") or []:
        symbol = str(item.get("symbol") or "").upper().split(".")[0]
        occurred_at = str(item.get("occurred_at") or "")[:10]
        if selected and symbol not in selected:
            continue
        if requested_as_of and (not occurred_at or occurred_at > requested_as_of):
            continue
        normalized = dict(item)
        if requested_as_of and occurred_at:
            age_days = max((pd.Timestamp(requested_as_of) - pd.Timestamp(occurred_at)).days, 0)
            freshness_score = max(0.0, 100 * (1 - age_days / EventFlowEngine.freshness_days))
            strength_score = EventFlowEngine.strength_scores.get(
                str(normalized.get("evidence_strength") or "weak"), 30.0
            )
            magnitude = float(normalized.get("magnitude_score") or 0)
            normalized["age_days"] = age_days
            normalized["freshness"] = "fresh" if age_days <= EventFlowEngine.freshness_days else "stale"
            normalized["intensity_score"] = round(
                magnitude * 0.65 + strength_score * 0.25 + freshness_score * 0.10,
                2,
            )
        alerts.append(normalized)
    alerts.sort(key=lambda item: (-float(item.get("intensity_score") or 0), str(item.get("id") or "")))
    summaries = EventFlowEngine._group_symbols(alerts)
    resolved_summary = {
        "input_events": len(alerts),
        "deduplicated_events": len(alerts),
        "duplicates_removed": 0,
        "fresh_events": sum(item.get("freshness") == "fresh" for item in alerts),
        "stale_events": sum(item.get("freshness") == "stale" for item in alerts),
        "symbols": len(summaries),
        "top_event_id": alerts[0].get("id") if alerts else None,
    }
    resolved_freshness = dict(snapshot.get("freshness") or {})
    if requested_as_of:
        lag_days = max((date.today() - pd.Timestamp(requested_as_of).date()).days, 0)
        resolved_freshness = {
            "state": "current" if lag_days <= 3 else "historical",
            "resolution": "point_in_time_replay",
            "calendar_lag_days": lag_days,
            "source_snapshot_state": resolved_freshness.get("state"),
        }
    return {
        "snapshot_id": snapshot_id,
        "as_of": requested_as_of or snapshot_as_of,
        "snapshot_as_of": snapshot_as_of,
        "as_of_mode": "historical_replay" if requested_as_of and requested_as_of != snapshot_as_of else "snapshot",
        "freshness": resolved_freshness,
        "summary": resolved_summary,
        "alerts": alerts,
        "symbol_summaries": summaries,
    }, []
