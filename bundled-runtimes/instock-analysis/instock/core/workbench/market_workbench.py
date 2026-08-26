#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Desk-native market tape for the migrated InStock overview surfaces."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from statistics import median
from typing import Any

import pandas as pd

from instock.core.analysis_snapshot import SNAPSHOT_SCHEMA_VERSION
from instock.core.industry_taxonomy import (
    SW_2021_L1_INDUSTRIES,
    UNCLASSIFIED_INDUSTRY,
    resolve_sw_l1_industry,
)
from instock.core.market_data_provider import MarketDataError, MarketDataProvider


class MarketWorkbenchError(ValueError):
    pass


class MarketWorkbenchEngine:
    engine_name = "instock-market-workbench"
    engine_version = "1.4.0"
    supported_scan_limits = (50, 100, 200)
    market_map_limit = 200  # 兼容旧调用；市场概览运行时不再请求云图数据。
    board_specs = {
        "gainers": ("changePct", "desc"),
        "losers": ("changePct", "asc"),
        "amount": ("amount", "desc"),
        "turnover": ("turnoverPct", "desc"),
        "volume_ratio": ("volumeRatio", "desc"),
    }

    def __init__(self, provider: MarketDataProvider):
        self.provider = provider

    def analyze(self, *, scan_limit: int = 100) -> dict[str, Any]:
        if scan_limit not in self.supported_scan_limits:
            raise MarketWorkbenchError("市场扫描仅支持 50、100、200 只")

        failures: list[dict[str, str]] = []
        limitations: list[str] = []
        try:
            overview = self.provider.get_market_overview()
        except MarketDataError as exc:
            overview = {"sentiment": {}, "sectors": [], "updated": ""}
            failures.append({"board": "overview", "error": str(exc)})
            limitations.append("overview_unavailable")
        try:
            market_emotion = self.provider.get_market_emotion()
        except MarketDataError as exc:
            market_emotion = {
                "state": "unavailable", "leaders": [], "ladder": []
            }
            failures.append({"board": "market_emotion", "error": str(exc)})
            limitations.append("market_emotion_unavailable")

        leaderboards: dict[str, list[dict[str, Any]]] = {
            board: [] for board in self.board_specs
        }
        scan_meta: dict[str, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=len(self.board_specs)) as pool:
            jobs = {
                pool.submit(
                    self.provider.get_market_turnover_top,
                    limit=20,
                ) if board == "amount" else pool.submit(
                    self.provider.get_stock_scan,
                    sort=sort,
                    order=order,
                    limit=scan_limit,
                ): board
                for board, (sort, order) in self.board_specs.items()
            }
            for future in as_completed(jobs):
                board = jobs[future]
                try:
                    scan = future.result()
                except MarketDataError as exc:
                    failures.append({"board": board, "error": str(exc)})
                    continue
                rows = [dict(item) for item in (scan.get("items") or []) if isinstance(item, dict)]
                sort_basis = str((scan.get("coverage") or {}).get("sort_basis") or "")
                expected_sort = self.board_specs[board][0]
                required_field = {
                    "gainers": "change_pct",
                    "losers": "change_pct",
                    "amount": "amount",
                    "turnover": "turnover_pct",
                    "volume_ratio": "volume_ratio",
                }[board]
                if board in {"amount", "turnover", "volume_ratio"} and (
                    sort_basis != expected_sort
                    or not any(self._number(item.get(required_field)) > 0 for item in rows)
                ):
                    failures.append({
                        "board": board,
                        "error": f"Desk 未返回可用于{board}排序的有效字段",
                    })
                    limitations.append(f"{board}_leaderboard_unavailable")
                    continue
                leaderboards[board] = rows[:20]
                scan_meta[board] = scan

        if not any(leaderboards.values()):
            raise MarketWorkbenchError("Desk A 股扫描没有返回任何可用榜单")

        scan_rows = self._unique_scan_rows(scan_meta)
        sector_sample_rows = self._unique_scan_rows(
            {"amount": scan_meta["amount"]} if "amount" in scan_meta else scan_meta
        )
        sectors = [
            self._sector_row(item)
            for item in (overview.get("sectors") or [])
            if isinstance(item, dict) and item.get("name")
        ]
        sector_source = "desk_overview"
        if not sectors:
            sectors = self._scan_sector_rows(sector_sample_rows)
            if sectors:
                sector_source = "ranked_scan_sample"
                limitations.append("sector_leaders_from_ranked_scan_sample")
            else:
                sector_source = "unavailable"
                limitations.append("sector_leaders_unavailable")
        sectors.sort(key=lambda item: item["change_pct"], reverse=True)
        sentiment = overview.get("sentiment") if isinstance(overview.get("sentiment"), dict) else {}
        up = int(self._number(sentiment.get("up")))
        down = int(self._number(sentiment.get("down")))
        flat = int(self._number(sentiment.get("flat")))
        breadth_total = up + down + flat
        breadth_available = breadth_total > 0
        if not breadth_available:
            limitations.append("market_breadth_unavailable")
        active = leaderboards["amount"][0] if leaderboards["amount"] else {}
        summary = {
            "market_breadth": str(sentiment.get("breadth") or "--"),
            "up": up,
            "down": down,
            "flat": flat,
            "up_ratio": round(up / breadth_total * 100, 2) if breadth_total else 0.0,
            "leading_sector": sectors[0]["name"] if sectors else "--",
            "most_active_symbol": str(active.get("symbol") or ""),
            "most_active_name": str(active.get("name") or "--"),
        }
        as_of = self._as_of(scan_meta, overview)
        data_source = "+".join(dict.fromkeys(
            str(scan.get("source") or "")
            for scan in scan_meta.values()
            if scan.get("source")
        )) or self.provider.name
        coverage = {
            "requested_scan_limit": scan_limit,
            "successful_boards": len(scan_meta),
            "requested_boards": len(self.board_specs),
            "unique_securities": len(scan_rows),
            "overview_available": "overview_unavailable" not in limitations,
            "sector_source": sector_source,
            "sector_count": len(sectors),
            "sector_sample_size": len(sector_sample_rows) if sector_source == "ranked_scan_sample" else 0,
            "leaderboard_scopes": {
                board: str((scan.get("coverage") or {}).get("scope") or "returned_scan_pool")
                for board, scan in scan_meta.items()
            },
            "leaderboard_sort_basis": {
                board: str((scan.get("coverage") or {}).get("sort_basis") or "")
                for board, scan in scan_meta.items()
            },
        }
        market_anomalies = self._market_anomalies(scan_rows, sectors)
        if failures:
            limitations.append("partial_desk_market_coverage")
        price_rank_scopes = {
            board: str((scan_meta.get(board, {}).get("coverage") or {}).get("scope") or "")
            for board in ("gainers", "losers")
        }
        if all(
            price_rank_scopes.get(board) == "full_market_ranked_top"
            for board in ("gainers", "losers")
        ):
            limitations.append("gainers_and_losers_are_full_market_ranked_top_results")
        else:
            limitations.append("price_rank_boards_limited_to_returned_scan_scope")
        if "amount" in scan_meta:
            limitations.append("amount_leaderboard_is_full_market_top20")
        limitations.append("latest_cross_section_only_no_historical_replay")
        data_state = (
            "partial"
            if failures or sector_source != "desk_overview" or not breadth_available
            else "complete"
        )
        stable = {
            "as_of": as_of,
            "data_source": data_source,
            "data_state": data_state,
            "coverage": coverage,
            "summary": summary,
            "market_breadth": {
                "state": "available" if breadth_available else "unavailable",
                "updated": str(overview.get("updated") or ""),
                **summary,
            },
            "market_emotion": market_emotion,
            "sector_basis": {
                "source": sector_source,
                "sample_size": len(sector_sample_rows) if sector_source == "ranked_scan_sample" else 0,
                "sample_sort": "amount" if sector_source == "ranked_scan_sample" else None,
            },
            "sector_leaders": sectors[:20],
            "market_anomalies": market_anomalies,
            "leaderboards": leaderboards,
            "failures": sorted(failures, key=lambda item: item["board"]),
            "limitations": limitations,
        }
        snapshot = self._build_snapshot(
            stable, scan_meta, overview, market_emotion, scan_limit
        )
        return {
            "engine": {"name": self.engine_name, "version": self.engine_version},
            **stable,
            "snapshot": snapshot,
        }

    @classmethod
    def _market_map(cls, scan: dict[str, Any]) -> dict[str, Any]:
        coverage = scan.get("coverage") if isinstance(scan.get("coverage"), dict) else {}
        source_rows = [
            dict(item)
            for item in (scan.get("items") or [])
            if isinstance(item, dict)
        ]
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

        groups: dict[str, list[dict[str, Any]]] = {}
        for row in valid_rows:
            raw_industry = str(row.get("industry") or "").strip()
            industry = resolve_sw_l1_industry(raw_industry)
            market_cap = cls._number(row.get("market_cap"))
            float_market_cap = cls._number(row.get("float_market_cap"))
            amount = cls._number(row.get("amount"))
            if market_cap > 0:
                size_value, size_source = market_cap, "market_cap"
            elif float_market_cap > 0:
                size_value, size_source = float_market_cap, "float_market_cap"
            else:
                size_value, size_source = amount, "amount"
            groups.setdefault(industry, []).append({
                "symbol": str(row.get("symbol") or ""),
                "name": str(row.get("name") or ""),
                "industry": industry,
                "raw_industry": raw_industry or UNCLASSIFIED_INDUSTRY,
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
            })

        map_groups = []
        for industry, items in groups.items():
            items.sort(key=lambda item: item["size_value"], reverse=True)
            total_size = sum(item["size_value"] for item in items)
            weighted_change = (
                sum(item["change_pct"] * item["size_value"] for item in items) / total_size
                if total_size else 0.0
            )
            map_groups.append({
                "name": industry,
                "change_pct": round(weighted_change, 3),
                "size_value": round(total_size, 2),
                "stock_count": len(items),
                "items": items,
            })
        map_groups.sort(key=lambda item: item["size_value"], reverse=True)

        scope = str(coverage.get("scope") or "returned_scan_pool")
        classified_securities = sum(
            item["stock_count"] for item in map_groups
            if item["name"] != UNCLASSIFIED_INDUSTRY
        )
        unclassified_securities = sum(
            item["stock_count"] for item in map_groups
            if item["name"] == UNCLASSIFIED_INDUSTRY
        )
        represented_l1_industries = sum(
            item["name"] in SW_2021_L1_INDUSTRIES for item in map_groups
        )
        return {
            "state": "available" if map_groups else "unavailable",
            "groups": map_groups,
            "size_basis": size_basis,
            "color_basis": "change_pct",
            "coverage": {
                "requested": int(coverage.get("requested") or cls.market_map_limit),
                "returned": int(coverage.get("returned") or len(source_rows)),
                "valid_securities": sum(item["stock_count"] for item in map_groups),
                "industry_count": len(map_groups),
                "taxonomy": "sw_2021_l1",
                "classified_securities": classified_securities,
                "unclassified_securities": unclassified_securities,
                "represented_l1_industries": represented_l1_industries,
                "total_l1_industries": len(SW_2021_L1_INDUSTRIES),
                "market_cap_count": market_cap_count,
                "float_market_cap_fallback_count": float_market_cap_fallback_count,
                "amount_fallback_count": amount_fallback_count,
                "excluded_without_size": len(source_rows) - len(valid_rows),
                "sort_basis": str(coverage.get("sort_basis") or "marketCap"),
                "scope": scope,
                "sample_kind": "market_cap_ranked_top",
                "full_market": scope in {"full_market", "all_market"},
            },
        }

    @staticmethod
    def _sector_row(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": str(item.get("name") or ""),
            "change_pct": round(MarketWorkbenchEngine._number(item.get("pct", item.get("change_pct"))), 3),
            "net": round(MarketWorkbenchEngine._number(item.get("net")), 2),
            "firms": int(MarketWorkbenchEngine._number(item.get("firms"))),
            "source": "desk_overview",
        }

    @staticmethod
    def _unique_scan_rows(scan_meta: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        rows: dict[str, dict[str, Any]] = {}
        for board in sorted(scan_meta):
            for item in scan_meta[board].get("items") or []:
                if not isinstance(item, dict):
                    continue
                symbol = str(item.get("symbol") or "").strip()
                if symbol and symbol not in rows:
                    rows[symbol] = dict(item)
        return list(rows.values())

    @staticmethod
    def _scan_sector_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        grouped: dict[str, list[float]] = {}
        for row in rows:
            industry = str(row.get("industry") or "").strip()
            if not industry or industry in {"--", "未分类"}:
                continue
            change = MarketWorkbenchEngine._number(row.get("change_pct"))
            if abs(change) > 30:
                continue
            grouped.setdefault(industry, []).append(change)

        sectors = []
        for industry, changes in grouped.items():
            if len(changes) < 2:
                continue
            sectors.append({
                "name": industry,
                "change_pct": round(float(median(changes)), 3),
                "net": 0.0,
                "firms": len(changes),
                "up_ratio": round(sum(value > 0 for value in changes) / len(changes) * 100, 2),
                "source": "ranked_scan_sample",
            })
        return sectors

    @classmethod
    def _market_anomalies(
        cls,
        rows: list[dict[str, Any]],
        sectors: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Build an honest latest-cross-section anomaly docket.

        Desk currently exposes price, amount, turnover, volume ratio and sector
        net-flow fields.  Intraday auction timing and limit-up reasons are not
        inferred from those fields.
        """

        valid_rows = [row for row in rows if cls._number(row.get("price")) > 0]
        volume_spikes = sorted(
            (
                cls._anomaly_row(row, "量比显著放大")
                for row in valid_rows
                if cls._number(row.get("volume_ratio")) >= 2.0
            ),
            key=lambda item: item["volume_ratio"],
            reverse=True,
        )[:8]
        turnover_heat = sorted(
            (
                cls._anomaly_row(row, "换手活跃")
                for row in valid_rows
                if cls._number(row.get("turnover_pct")) >= 8.0
            ),
            key=lambda item: item["turnover_pct"],
            reverse=True,
        )[:8]
        price_volume_surges = sorted(
            (
                cls._anomaly_row(row, "量价同步上行")
                for row in valid_rows
                if cls._number(row.get("change_pct")) >= 3.0
                and cls._number(row.get("volume_ratio")) >= 1.5
                and cls._number(row.get("amount")) > 0
            ),
            key=lambda item: (item["change_pct"], item["volume_ratio"]),
            reverse=True,
        )[:8]

        limit_watch = []
        for row in valid_rows:
            name = str(row.get("name") or "")
            if name[:1].upper() in {"N", "C"}:
                continue
            limit_pct = cls._limit_pct(row)
            change_pct = cls._number(row.get("change_pct"))
            if limit_pct * 0.9 <= change_pct <= limit_pct + 0.5:
                item = cls._anomaly_row(row, "接近涨停观察")
                distance_pct = round(limit_pct - change_pct, 2)
                item.update({
                    "limit_pct": limit_pct,
                    "distance_pct": distance_pct,
                    "threshold_state": (
                        "below" if distance_pct > 0
                        else "above" if distance_pct < 0
                        else "at"
                    ),
                })
                limit_watch.append(item)
        limit_watch.sort(key=lambda item: item["distance_pct"])

        sector_fund_flows = [
            {
                "name": str(item.get("name") or ""),
                "change_pct": round(cls._number(item.get("change_pct")), 3),
                "net": round(cls._number(item.get("net")), 2),
                "direction": "inflow" if cls._number(item.get("net")) > 0 else "outflow",
                "source": str(item.get("source") or "desk_overview"),
            }
            for item in sectors
            if cls._number(item.get("net")) != 0
        ]
        sector_fund_flows.sort(key=lambda item: abs(item["net"]), reverse=True)

        return {
            "basis": "latest_cross_section",
            "volume_spikes": volume_spikes,
            "turnover_heat": turnover_heat,
            "price_volume_surges": price_volume_surges,
            "limit_watch": limit_watch[:8],
            "sector_fund_flows": sector_fund_flows[:10],
            "unavailable_topics": [
                {"id": "morning_accumulation", "label": "早盘抢筹", "reason": "等待 Desk 集合竞价委托金额与成交确认字段；分钟 K 线不能替代"},
                {"id": "closing_accumulation", "label": "尾盘抢筹", "reason": "等待 Desk 尾盘委托金额与撮合字段；分钟 K 线不能替代"},
                {"id": "limit_up_reason", "label": "涨停原因 / 概念资金", "reason": "等待 Desk 逐股涨停原因与概念资金正式 capability；市场情绪聚合不能替代"},
            ],
        }

    @classmethod
    def _anomaly_row(cls, row: dict[str, Any], signal: str) -> dict[str, Any]:
        return {
            "symbol": str(row.get("symbol") or ""),
            "name": str(row.get("name") or ""),
            "industry": str(row.get("industry") or ""),
            "price": round(cls._number(row.get("price")), 3),
            "change_pct": round(cls._number(row.get("change_pct")), 3),
            "amount": round(cls._number(row.get("amount")), 2),
            "turnover_pct": round(cls._number(row.get("turnover_pct")), 3),
            "volume_ratio": round(cls._number(row.get("volume_ratio")), 3),
            "signal": signal,
        }

    @staticmethod
    def _limit_pct(row: dict[str, Any]) -> float:
        symbol = str(row.get("symbol") or "").split(".")[0]
        name = str(row.get("name") or "").upper()
        if "ST" in name:
            return 5.0
        if symbol.startswith(("300", "301", "688", "689")):
            return 20.0
        if symbol.startswith(("4", "8", "92")):
            return 30.0
        return 10.0

    @staticmethod
    def _number(value: Any) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        return number if pd.notna(number) else 0.0

    @staticmethod
    def _as_of(scan_meta: dict[str, dict[str, Any]], overview: dict[str, Any]) -> str:
        values = [str(scan.get("as_of") or "") for scan in scan_meta.values()]
        values.append(str(overview.get("updated") or ""))
        parsed = []
        for value in values:
            if not value:
                continue
            try:
                stamp = pd.Timestamp(value)
                parsed.append(stamp.tz_localize(None) if stamp.tzinfo else stamp)
            except ValueError:
                continue
        return max(parsed).strftime("%Y-%m-%d") if parsed else date.today().isoformat()

    def _build_snapshot(
        self, stable, scan_meta, overview, market_emotion, scan_limit
    ):
        material = {
            "analysis": {"name": self.engine_name, "version": self.engine_version},
            "parameters": {"scanLimit": scan_limit},
            "overview": overview,
            "market_emotion": market_emotion,
            "scan_meta": {
                board: {
                    "source": scan.get("source"),
                    "as_of": scan.get("as_of"),
                    "coverage": scan.get("coverage"),
                }
                for board, scan in scan_meta.items()
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
            "parameters": {"scanLimit": scan_limit},
            "data_window": {
                "requested_as_of": None,
                "start_date": None,
                "end_date": stable["as_of"],
                "coverage": stable["data_state"],
            },
            "provenance": {
                "provider": self.provider.name,
                "endpoint": "market.overview + market.emotion + market.scan[leaderboards] + market.turnover-top",
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
