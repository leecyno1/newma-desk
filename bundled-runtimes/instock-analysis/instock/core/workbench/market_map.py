#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Desk-native A-share market treemap engine."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from typing import Any

import pandas as pd

from instock.core.analysis_snapshot import SNAPSHOT_SCHEMA_VERSION
from instock.core.industry_taxonomy import (
    SW_2021_L1_INDUSTRIES,
    SW_2021_L2_DIRECTORY,
    UNCLASSIFIED_INDUSTRY,
    resolve_sw_l1_industry,
    resolve_sw_l2_industry,
)
from instock.core.market_data_provider import MarketDataError, MarketDataProvider


class MarketMapError(ValueError):
    pass


class MarketMapEngine:
    engine_name = "instock-market-map"
    engine_version = "1.1.0"
    supported_capacities = (100, 500)
    per_ranking_limit = 100
    ranking_specs = (
        ("market_cap", "市值", "marketCap", "desc"),
        ("amount", "成交额", "amount", "desc"),
        ("turnover", "换手率", "turnoverPct", "desc"),
        ("volume_ratio", "量比", "volumeRatio", "desc"),
        ("gainers", "涨幅", "changePct", "desc"),
        ("losers", "跌幅", "changePct", "asc"),
    )

    def __init__(self, provider: MarketDataProvider):
        self.provider = provider

    def analyze(self, *, capacity: int = 100) -> dict[str, Any]:
        if capacity not in self.supported_capacities:
            raise MarketMapError("大盘云图仅支持 Top100 或多榜 Top500")

        requested_specs = self.ranking_specs[:1] if capacity == 100 else self.ranking_specs
        scans: dict[str, dict[str, Any]] = {}
        failures: list[dict[str, str]] = []
        with ThreadPoolExecutor(max_workers=len(requested_specs)) as pool:
            jobs = {
                pool.submit(
                    self.provider.get_stock_scan,
                    sort=sort,
                    order=order,
                    limit=self.per_ranking_limit,
                ): (ranking_id, label, sort, order)
                for ranking_id, label, sort, order in requested_specs
            }
            for future in as_completed(jobs):
                ranking_id, label, sort, order = jobs[future]
                try:
                    scans[ranking_id] = future.result()
                except MarketDataError as exc:
                    failures.append({
                        "ranking": ranking_id,
                        "label": label,
                        "sort": sort,
                        "order": order,
                        "error": str(exc),
                    })

        if not scans:
            raise MarketMapError("Desk A 股扫描没有返回可用于大盘云图的数据")

        rows, unique_count = self._merge_and_select(scans, requested_specs, capacity)
        groups, map_coverage, size_basis = self._build_groups(rows)
        if not groups:
            raise MarketMapError("Desk 返回的数据缺少市值、流通市值和成交额，无法绘制云图")

        contributing_rankings = []
        for ranking_id, label, sort, order in requested_specs:
            scan = scans.get(ranking_id)
            if not scan:
                continue
            coverage = scan.get("coverage") if isinstance(scan.get("coverage"), dict) else {}
            contributing_rankings.append({
                "id": ranking_id,
                "label": label,
                "sort": sort,
                "order": order,
                "returned": len([item for item in scan.get("items") or [] if isinstance(item, dict)]),
                "scope": str(coverage.get("scope") or "returned_scan_pool"),
                "sort_basis": str(coverage.get("sort_basis") or sort),
                "source": str(scan.get("source") or self.provider.name),
            })

        displayed = sum(group["stock_count"] for group in groups)
        pool_kind = "market_cap_ranked_top" if capacity == 100 else "multi_rank_union"
        coverage = {
            **map_coverage,
            "requested_capacity": capacity,
            "displayed_securities": displayed,
            "unique_securities": unique_count,
            "pool_kind": pool_kind,
            "contributing_rankings": contributing_rankings,
            "rankings_requested": len(requested_specs),
            "rankings_succeeded": len(scans),
            "full_market": False,
        }
        summary = self._summary(groups)
        limitations = ["market_map_is_ranked_coverage_pool_not_full_market"]
        if capacity == 500:
            limitations.append("top500_is_multi_rank_union_not_market_cap_top500")
        if map_coverage["float_market_cap_fallback_count"]:
            limitations.append("market_map_uses_float_market_cap_fallback")
        if map_coverage["amount_fallback_count"]:
            limitations.append("market_map_uses_amount_fallback")
        if map_coverage["l1_only_securities"]:
            limitations.append("desk_scan_missing_verified_sw2021_l2_for_some_securities")
        if failures:
            limitations.append("partial_ranking_coverage")

        as_of = self._as_of(scans)
        data_source = "+".join(dict.fromkeys(
            str(scan.get("source") or "")
            for scan in scans.values()
            if scan.get("source")
        )) or self.provider.name
        stable = {
            "as_of": as_of,
            "data_source": data_source,
            "data_state": "partial" if failures else "complete",
            "size_basis": size_basis,
            "color_basis": "change_pct",
            "groups": groups,
            "coverage": coverage,
            "summary": summary,
            "failures": sorted(failures, key=lambda item: item["ranking"]),
            "limitations": limitations,
        }
        snapshot = self._build_snapshot(stable, scans, capacity)
        return {
            "engine": {"name": self.engine_name, "version": self.engine_version},
            **stable,
            "snapshot": snapshot,
        }

    @classmethod
    def _merge_and_select(
        cls,
        scans: dict[str, dict[str, Any]],
        requested_specs: tuple[tuple[str, str, str, str], ...],
        capacity: int,
    ) -> tuple[list[dict[str, Any]], int]:
        merged: dict[str, dict[str, Any]] = {}
        ranked_symbols: dict[str, list[str]] = {}
        numeric_fields = (
            "price", "change_pct", "amount", "turnover_pct", "volume_ratio",
            "market_cap", "float_market_cap", "pe", "pb",
        )
        text_fields = (
            "name", "market", "exchange", "industry", "industry_l1", "industry_l2",
        )

        for ranking_id, label, _, _ in requested_specs:
            scan = scans.get(ranking_id) or {}
            symbols = []
            for rank, item in enumerate(scan.get("items") or [], start=1):
                if not isinstance(item, dict):
                    continue
                symbol = str(item.get("symbol") or "").strip()
                if not symbol:
                    continue
                row = merged.setdefault(symbol, {"symbol": symbol, "rank_sources": []})
                for field in text_fields:
                    value = str(item.get(field) or "").strip()
                    if value and not row.get(field):
                        row[field] = value
                for field in numeric_fields:
                    value = cls._number(item.get(field))
                    if value and not cls._number(row.get(field)):
                        row[field] = value
                row["rank_sources"].append({"id": ranking_id, "label": label, "rank": rank})
                symbols.append(symbol)
            ranked_symbols[ranking_id] = symbols

        selected_symbols: list[str] = []
        selected: set[str] = set()
        if capacity == 100:
            selected_symbols = ranked_symbols.get("market_cap", [])[:capacity]
        else:
            max_rank = max((len(symbols) for symbols in ranked_symbols.values()), default=0)
            for rank_index in range(max_rank):
                for ranking_id, _, _, _ in requested_specs:
                    symbols = ranked_symbols.get(ranking_id, [])
                    if rank_index >= len(symbols):
                        continue
                    symbol = symbols[rank_index]
                    if symbol in selected:
                        continue
                    selected.add(symbol)
                    selected_symbols.append(symbol)
                    if len(selected_symbols) >= capacity:
                        break
                if len(selected_symbols) >= capacity:
                    break

        return [dict(merged[symbol]) for symbol in selected_symbols if symbol in merged], len(merged)

    @classmethod
    def _build_groups(
        cls,
        source_rows: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], dict[str, Any], str]:
        valid_rows = [
            row for row in source_rows
            if str(row.get("symbol") or "").strip()
            and str(row.get("name") or "").strip()
            and any(cls._number(row.get(field)) > 0 for field in (
                "market_cap", "float_market_cap", "amount",
            ))
        ]
        market_cap_count = sum(cls._number(row.get("market_cap")) > 0 for row in valid_rows)
        float_market_cap_fallback_count = sum(
            cls._number(row.get("market_cap")) <= 0
            and cls._number(row.get("float_market_cap")) > 0
            for row in valid_rows
        )
        amount_fallback_count = sum(
            cls._number(row.get("market_cap")) <= 0
            and cls._number(row.get("float_market_cap")) <= 0
            and cls._number(row.get("amount")) > 0
            for row in valid_rows
        )
        if market_cap_count == len(valid_rows) and valid_rows:
            size_basis = "market_cap"
        elif market_cap_count or float_market_cap_fallback_count:
            size_basis = "market_cap_with_fallback"
        else:
            size_basis = "amount"

        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in valid_rows:
            raw_industry = str(row.get("industry") or "").strip()
            explicit_l1 = str(row.get("industry_l1") or "").strip()
            explicit_l2 = str(row.get("industry_l2") or "").strip()
            secondary_industry = resolve_sw_l2_industry(explicit_l2 or raw_industry)
            industry = resolve_sw_l1_industry(
                explicit_l1 or secondary_industry or raw_industry
            )
            if secondary_industry and resolve_sw_l1_industry(secondary_industry) != industry:
                secondary_industry = ""
            market_cap = cls._number(row.get("market_cap"))
            float_market_cap = cls._number(row.get("float_market_cap"))
            amount = cls._number(row.get("amount"))
            if market_cap > 0:
                size_value, size_source = market_cap, "market_cap"
            elif float_market_cap > 0:
                size_value, size_source = float_market_cap, "float_market_cap"
            else:
                size_value, size_source = amount, "amount"
            grouped.setdefault(industry, []).append({
                "symbol": str(row.get("symbol") or ""),
                "name": str(row.get("name") or ""),
                "industry": industry,
                "industry_l1": industry,
                "industry_l2": secondary_industry,
                "secondary_industry": secondary_industry,
                "raw_industry": raw_industry or UNCLASSIFIED_INDUSTRY,
                "classification_depth": (
                    "l2" if secondary_industry
                    else "l1" if industry != UNCLASSIFIED_INDUSTRY
                    else "none"
                ),
                "classification_source": (
                    "desk_explicit_l2"
                    if secondary_industry and explicit_l2
                    else "desk_industry_verified_l2"
                    if secondary_industry
                    else "desk_l1_only"
                    if industry != UNCLASSIFIED_INDUSTRY
                    else "unclassified"
                ),
                "price": round(cls._number(row.get("price")), 3),
                "change_pct": round(cls._number(row.get("change_pct")), 3),
                "amount": round(amount, 2),
                "turnover_pct": round(cls._number(row.get("turnover_pct")), 3),
                "volume_ratio": round(cls._number(row.get("volume_ratio")), 3),
                "market_cap": round(market_cap, 2),
                "float_market_cap": round(float_market_cap, 2),
                "pe": round(cls._number(row.get("pe")), 3),
                "pb": round(cls._number(row.get("pb")), 3),
                "size_value": round(size_value, 2),
                "size_basis": size_source,
                "rank_sources": list(row.get("rank_sources") or []),
            })

        groups = []
        for industry, items in grouped.items():
            items.sort(key=lambda item: item["size_value"], reverse=True)
            total_size = sum(item["size_value"] for item in items)
            weighted_change = (
                sum(item["change_pct"] * item["size_value"] for item in items) / total_size
                if total_size else 0.0
            )
            grouped_secondary: dict[str, list[dict[str, Any]]] = {}
            direct_items = []
            for item in items:
                if item["industry_l2"]:
                    grouped_secondary.setdefault(item["industry_l2"], []).append(item)
                else:
                    direct_items.append(item)
            secondary_groups = []
            for secondary_name, secondary_items in grouped_secondary.items():
                secondary_size = sum(item["size_value"] for item in secondary_items)
                secondary_change = (
                    sum(item["change_pct"] * item["size_value"] for item in secondary_items)
                    / secondary_size
                    if secondary_size else 0.0
                )
                secondary_groups.append({
                    "name": secondary_name,
                    "industry_l1": industry,
                    "change_pct": round(secondary_change, 3),
                    "size_value": round(secondary_size, 2),
                    "stock_count": len(secondary_items),
                    "items": secondary_items,
                })
            secondary_groups.sort(key=lambda item: item["size_value"], reverse=True)
            groups.append({
                "name": industry,
                "change_pct": round(weighted_change, 3),
                "size_value": round(total_size, 2),
                "stock_count": len(items),
                "secondary_count": len(secondary_groups),
                "direct_stock_count": len(direct_items),
                "secondary_groups": secondary_groups,
                "direct_items": direct_items,
                "items": items,
            })
        groups.sort(key=lambda item: item["size_value"], reverse=True)

        classified = sum(
            group["stock_count"] for group in groups
            if group["name"] != UNCLASSIFIED_INDUSTRY
        )
        unclassified = sum(
            group["stock_count"] for group in groups
            if group["name"] == UNCLASSIFIED_INDUSTRY
        )
        all_items = [item for group in groups for item in group["items"]]
        verified_l2 = sum(bool(item["industry_l2"]) for item in all_items)
        l1_only = sum(
            not item["industry_l2"] and item["industry"] != UNCLASSIFIED_INDUSTRY
            for item in all_items
        )
        coverage = {
            "valid_securities": sum(group["stock_count"] for group in groups),
            "industry_count": len(groups),
            "taxonomy": "sw_2021_l1_l2",
            "taxonomy_source": "embedded_tushare_sw2021_directory+desk.market.scan",
            "classified_securities": classified,
            "unclassified_securities": unclassified,
            "verified_l2_securities": verified_l2,
            "l1_only_securities": l1_only,
            "represented_l1_industries": sum(
                group["name"] in SW_2021_L1_INDUSTRIES for group in groups
            ),
            "total_l1_industries": len(SW_2021_L1_INDUSTRIES),
            "represented_l2_industries": len({
                item["industry_l2"] for item in all_items if item["industry_l2"]
            }),
            "total_l2_industries": len(SW_2021_L2_DIRECTORY),
            "market_cap_count": market_cap_count,
            "float_market_cap_fallback_count": float_market_cap_fallback_count,
            "amount_fallback_count": amount_fallback_count,
            "excluded_without_size": len(source_rows) - len(valid_rows),
        }
        return groups, coverage, size_basis

    @classmethod
    def _summary(cls, groups: list[dict[str, Any]]) -> dict[str, Any]:
        rows = [item for group in groups for item in group["items"]]
        ranked_industries = [group for group in groups if group["name"] != UNCLASSIFIED_INDUSTRY]
        strongest = max(ranked_industries, key=lambda item: item["change_pct"], default={})
        weakest = min(ranked_industries, key=lambda item: item["change_pct"], default={})
        largest = max(rows, key=lambda item: item["size_value"], default={})
        return {
            "securities": len(rows),
            "advancers": sum(item["change_pct"] > 0.05 for item in rows),
            "decliners": sum(item["change_pct"] < -0.05 for item in rows),
            "flat": sum(abs(item["change_pct"]) <= 0.05 for item in rows),
            "strongest_industry": str(strongest.get("name") or "--"),
            "strongest_industry_change_pct": round(cls._number(strongest.get("change_pct")), 3),
            "weakest_industry": str(weakest.get("name") or "--"),
            "weakest_industry_change_pct": round(cls._number(weakest.get("change_pct")), 3),
            "largest_symbol": str(largest.get("symbol") or ""),
            "largest_name": str(largest.get("name") or "--"),
        }

    @staticmethod
    def _as_of(scans: dict[str, dict[str, Any]]) -> str:
        parsed = []
        for scan in scans.values():
            value = str(scan.get("as_of") or "")
            if not value:
                continue
            try:
                stamp = pd.Timestamp(value)
                parsed.append(stamp.tz_localize(None) if stamp.tzinfo else stamp)
            except ValueError:
                continue
        return max(parsed).strftime("%Y-%m-%d") if parsed else date.today().isoformat()

    def _build_snapshot(
        self,
        stable: dict[str, Any],
        scans: dict[str, dict[str, Any]],
        capacity: int,
    ) -> dict[str, Any]:
        material = {
            "analysis": {"name": self.engine_name, "version": self.engine_version},
            "parameters": {"capacity": capacity, "perRankingLimit": self.per_ranking_limit},
            "scan_meta": {
                ranking: {
                    "source": scan.get("source"),
                    "as_of": scan.get("as_of"),
                    "coverage": scan.get("coverage"),
                }
                for ranking, scan in scans.items()
            },
            "result": stable,
        }
        digest = hashlib.sha256(
            json.dumps(material, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
        lag_days = max((date.today() - pd.Timestamp(stable["as_of"]).date()).days, 0)
        return {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "snapshot_id": f"{self.engine_name}:{digest[:24]}",
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "analysis": {"name": self.engine_name, "version": self.engine_version},
            "parameters": {"capacity": capacity, "perRankingLimit": self.per_ranking_limit},
            "data_window": {
                "requested_as_of": None,
                "start_date": None,
                "end_date": stable["as_of"],
                "coverage": stable["data_state"],
            },
            "provenance": {
                "provider": self.provider.name,
                "endpoint": (
                    "market.scan[marketCap,amount,turnoverPct,volumeRatio,changePct]"
                    "+embedded_tushare.index_classify[SW2021 reference taxonomy]"
                ),
                "upstream_source": stable["data_source"],
                "limitations": list(stable["limitations"]),
            },
            "freshness": {
                "state": "fresh" if lag_days <= 3 else "delayed",
                "resolution": "latest_cross_section",
                "calendar_lag_days": lag_days,
            },
            "input": {"digest": f"sha256:{digest}", "summary": stable["coverage"]},
            "result": {"digest": f"sha256:{digest}", "summary": stable["summary"]},
        }

    @staticmethod
    def _number(value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        return number if pd.notna(number) else 0.0
