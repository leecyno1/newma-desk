#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Unified Desk-native technical, candlestick and classic strategy scanner."""

from __future__ import annotations

import hashlib
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from typing import Any, Mapping

import numpy as np
import pandas as pd
import talib as tl

from instock.core.analysis_snapshot import SNAPSHOT_SCHEMA_VERSION
from instock.core.market_data_provider import MarketDataError, MarketDataProvider


class TechnicalSignalCenterError(ValueError):
    pass


class TechnicalSignalInsufficientHistory(TechnicalSignalCenterError):
    def __init__(
        self,
        actual_bars: int,
        *,
        required_bars: int = 80,
        data_start: str = "",
        data_end: str = "",
        source: str = "",
        has_more: bool | None = None,
    ):
        self.actual_bars = int(actual_bars)
        self.required_bars = int(required_bars)
        self.data_start = data_start
        self.data_end = data_end
        self.source = source
        self.has_more = has_more
        super().__init__(
            f"有效日线不足 {self.required_bars} 根（实际 {self.actual_bars}），暂列短历史观察"
        )


STRATEGY_CATALOG = (
    ("volume_rise", "放量上涨", "technical"),
    ("ma_bull", "均线多头", "technical"),
    ("parking_apron", "停机坪", "pattern"),
    ("backtrace_ma250", "回踩年线", "technical"),
    ("breakthrough_platform", "突破平台", "pattern"),
    ("low_backtrace_increase", "无大幅回撤", "pattern"),
    ("turtle_trade", "海龟交易", "technical"),
    ("high_tight_flag", "高而窄旗形", "pattern"),
    ("climax_limitdown", "放量跌停", "risk"),
    ("low_atr_growth", "低 ATR 成长", "technical"),
)

PATTERN_CATALOG = (
    ("engulfing", "吞噬形态", tl.CDLENGULFING),
    ("hammer", "锤头", tl.CDLHAMMER),
    ("inverted_hammer", "倒锤头", tl.CDLINVERTEDHAMMER),
    ("morning_star", "晨星", tl.CDLMORNINGSTAR),
    ("morning_doji_star", "十字晨星", tl.CDLMORNINGDOJISTAR),
    ("piercing", "刺透形态", tl.CDLPIERCING),
    ("three_white_soldiers", "三个白兵", tl.CDL3WHITESOLDIERS),
    ("harami", "母子线", tl.CDLHARAMI),
    ("doji", "十字", tl.CDLDOJI),
    ("evening_star", "暮星", tl.CDLEVENINGSTAR),
    ("dark_cloud_cover", "乌云压顶", tl.CDLDARKCLOUDCOVER),
    ("shooting_star", "射击之星", tl.CDLSHOOTINGSTAR),
    ("hanging_man", "上吊线", tl.CDLHANGINGMAN),
    ("three_black_crows", "三只乌鸦", tl.CDL3BLACKCROWS),
    ("gravestone_doji", "墓碑十字", tl.CDLGRAVESTONEDOJI),
    ("breakaway", "脱离", tl.CDLBREAKAWAY),
)


class TechnicalSignalCenterEngine:
    engine_name = "instock-technical-signal-center"
    engine_version = "1.4.0"
    minimum_analysis_bars = 80
    fundamental_batch_size = 8
    fundamental_batch_workers = 2
    fundamental_snapshot_workers = 3
    fundamental_snapshot_fallback_limit = 30
    supported_universe_sizes = (30, 50, 100, 200)
    supported_bars = (120, 260)
    supported_markets = ("CN", "HK", "CN_HK")
    supported_universe_modes = ("broad", "quick")

    def __init__(self, provider: MarketDataProvider, *, max_workers: int = 6):
        self.provider = provider
        self.max_workers = max(1, min(int(max_workers), 8))

    def analyze(
        self,
        *,
        universe_size: int = 30,
        bars: int = 260,
        market: str = "CN",
        universe_mode: str = "broad",
        filters: dict[str, Any] | None = None,
        refresh: bool = False,
    ) -> dict[str, Any]:
        if universe_size not in self.supported_universe_sizes:
            raise TechnicalSignalCenterError("深度计算池仅支持 30、50、100、200 只")
        if bars not in self.supported_bars:
            raise TechnicalSignalCenterError("技术信号历史窗口仅支持 120、260 根日线")
        market = str(market or "CN").strip().upper()
        if market not in self.supported_markets:
            raise TechnicalSignalCenterError("选股市场仅支持 CN、HK、CN_HK")
        universe_mode = str(universe_mode or "broad").strip().lower()
        if universe_mode not in self.supported_universe_modes:
            raise TechnicalSignalCenterError("覆盖方式仅支持 broad、quick")
        normalized_filters = self._normalize_filters(filters)
        markets = ("CN", "HK") if market == "CN_HK" else (market,)

        broad_error = ""
        if universe_mode == "broad":
            try:
                scan = self.provider.get_candidate_universe(
                    markets=markets,
                    per_scan_limit=200,
                )
            except MarketDataError as exc:
                broad_error = str(exc)
                scan = self._quick_scan(market, universe_size)
        else:
            scan = self._quick_scan(market, universe_size)
        items = []
        seen = set()
        for raw in scan.get("items") or []:
            item = dict(raw)
            item_market = str(item.get("market") or markets[0]).strip().upper()
            symbol = str(item.get("symbol") or "").split(".")[0]
            key = (item_market, symbol)
            if key in seen or not self._valid_item(item, item_market):
                continue
            seen.add(key)
            items.append({**item, "symbol": symbol, "market": item_market})
        broad_eligible_count = len(items)
        market_items = []
        market_excluded = []
        for item in items:
            evidence = self._market_screening_evidence(item, normalized_filters)
            item["_market_screening_evidence"] = evidence
            if evidence["passed"]:
                market_items.append(item)
            else:
                market_excluded.append({
                    "symbol": item["symbol"],
                    "market": item["market"],
                    "name": str(item.get("name") or item["symbol"]),
                    "stage": "market_prefilter",
                    "reasons": evidence["reasons"],
                })
        items = market_items
        market_eligible_count = len(items)
        if not items:
            return self._empty_screening_result(
                scan=scan,
                universe_size=universe_size,
                bars=bars,
                market=market,
                universe_mode=universe_mode,
                filters=normalized_filters,
                broad_error=broad_error,
                broad_eligible_count=broad_eligible_count,
                market_excluded=market_excluded,
            )
        deep_pool_basis = self._deep_pool_selection_basis(normalized_filters)
        if len(items) > universe_size:
            items = self._select_deep_pool(
                items, universe_size, markets, normalized_filters
            )

        rows: list[dict[str, Any]] = []
        failures: list[dict[str, str]] = []
        short_history_watchlist: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(items))) as pool:
            jobs = {pool.submit(self._analyze_one, item, bars): item for item in items}
            for future in as_completed(jobs):
                item = jobs[future]
                try:
                    rows.append(future.result())
                except TechnicalSignalInsufficientHistory as exc:
                    short_history_watchlist.append({
                        "symbol": str(item.get("symbol") or ""),
                        "market": str(item.get("market") or "CN"),
                        "name": str(item.get("name") or item.get("symbol") or ""),
                        "industry": str(item.get("industry") or "未分类"),
                        "reason": "short_history_watch",
                        "required_bars": exc.required_bars,
                        "available_bars": exc.actual_bars,
                        "data_start": exc.data_start,
                        "data_end": exc.data_end,
                        "history_source": exc.source,
                        "history_has_more": exc.has_more,
                        "message": str(exc),
                    })
                except (MarketDataError, TechnicalSignalCenterError, ValueError) as exc:
                    failures.append({
                        "symbol": str(item.get("symbol") or ""),
                        "market": str(item.get("market") or "CN"),
                        "error": str(exc),
                    })
        if not rows:
            raise TechnicalSignalCenterError("候选池没有足够日线完成技术信号计算")

        rows.sort(key=lambda item: (-item["technical_score"], item["market"], item["symbol"]))
        analyzed_rows = rows
        fundamental_requested = self._fundamental_requested(normalized_filters)
        fundamental_packets: dict[str, dict[str, Any]] = {}
        fundamental_failures: list[dict[str, str]] = []
        if fundamental_requested:
            fundamental_packets, fundamental_failures = self._load_fundamentals(
                analyzed_rows,
                filters=normalized_filters,
                refresh=refresh,
            )
        matched_rows = []
        excluded_by_rules = list(market_excluded)
        fundamental_excluded_count = 0
        technical_excluded_count = 0
        for row in analyzed_rows:
            fundamental_evidence = None
            if fundamental_requested:
                packet = fundamental_packets.get(row["symbol"], self._empty_fundamentals())
                row["fundamentals"] = packet
                fundamental_evidence = self._fundamental_screening_evidence(
                    packet,
                    normalized_filters,
                )
                if not fundamental_evidence["passed"]:
                    row["screening_evidence"] = self._merge_screening_evidence(
                        row.pop("_market_screening_evidence", None),
                        fundamental_evidence,
                    )
                    fundamental_excluded_count += 1
                    excluded_by_rules.append({
                        "symbol": row["symbol"],
                        "market": row["market"],
                        "name": row["name"],
                        "stage": "fundamental_rules",
                        "reasons": fundamental_evidence["reasons"],
                    })
                    continue
            technical_evidence = self._technical_screening_evidence(row, normalized_filters)
            evidence = self._merge_screening_evidence(
                row.pop("_market_screening_evidence", None),
                fundamental_evidence,
                technical_evidence,
            )
            row["screening_evidence"] = evidence
            if evidence["passed"]:
                matched_rows.append(row)
            else:
                technical_excluded_count += 1
                excluded_by_rules.append({
                    "symbol": row["symbol"],
                    "market": row["market"],
                    "name": row["name"],
                    "stage": "technical_rules",
                    "reasons": evidence["reasons"],
                })
        rows = matched_rows
        for rank, row in enumerate(rows, 1):
            row["rank"] = rank
        failures.sort(key=lambda item: item["symbol"])
        short_history_watchlist.sort(key=lambda item: item["symbol"])
        limitations = ["latest_cross_section_only_no_historical_replay"]
        if broad_error:
            limitations.append("broad_universe_unavailable_quick_fallback")
        if bars < 250:
            limitations.append("long_window_strategies_partial")
        if failures:
            limitations.append("partial_kline_coverage")
        if short_history_watchlist:
            limitations.append("short_history_securities_excluded_from_ranking")
        if fundamental_requested and fundamental_failures:
            limitations.append("partial_fundamental_coverage")
        if any(
            strategy["state"] == "needs_evidence"
            for row in rows
            for strategy in row["strategies"]
        ):
            limitations.append("high_tight_flag_requires_institutional_lhb")
        institutional_evidence_failures = [
            {
                "symbol": row["symbol"],
                "error": row["institutional_evidence_failure"],
            }
            for row in analyzed_rows
            if row.get("institutional_evidence_failure")
        ]
        if institutional_evidence_failures:
            limitations.append("partial_institutional_lhb_coverage")
        scan_scope = str((scan.get("coverage") or {}).get("scope") or "")
        if scan_scope == "full_market_top20_plus_market_cap_pool":
            limitations.append("signal_pool_uses_turnover_top20_then_market_cap_fill")
        elif scan_scope == "market_cap_pool_only":
            limitations.append("signal_pool_fell_back_to_market_cap_pool")
        data_state = "partial" if (
            failures or bars < 250 or broad_error or fundamental_failures
            or institutional_evidence_failures
        ) else "complete"
        as_of = self._as_of(scan, analyzed_rows)
        fundamental_available_count = sum(
            bool(packet.get("available")) for packet in fundamental_packets.values()
        )
        coverage = {
            "scan_count": len(scan.get("items") or []),
            "broad_eligible_count": broad_eligible_count,
            "market_prefilter_count": market_eligible_count,
            "market_prefilter_excluded_count": len(market_excluded),
            "eligible_count": len(items),
            "analyzed_count": len(analyzed_rows),
            "matched_count": len(rows),
            "excluded_by_rules_count": len(excluded_by_rules),
            "fundamental_requested": fundamental_requested,
            "fundamental_evaluated_count": len(analyzed_rows) if fundamental_requested else 0,
            "fundamental_available_count": fundamental_available_count,
            "fundamental_failed_count": len(fundamental_failures),
            "institutional_evidence_failed_count": len(
                institutional_evidence_failures
            ),
            "fundamental_excluded_count": fundamental_excluded_count,
            "technical_excluded_count": technical_excluded_count,
            "failed_count": len(failures),
            "short_history_watch_count": len(short_history_watchlist),
            "scan_scope": scan_scope,
            "scan_sort_basis": str(
                (scan.get("coverage") or {}).get("sort_basis") or "amount"
            ),
            "deep_pool_selection_basis": deep_pool_basis,
            "requested_universe_mode": universe_mode,
            "effective_universe_mode": "quick" if broad_error else universe_mode,
            "broad_fallback_reason": broad_error,
        }
        leader = rows[0] if rows else None
        summary = {
            "leading_symbol": leader["symbol"] if leader else "",
            "leading_name": leader["name"] if leader else "",
            "leading_score": leader["technical_score"] if leader else 0,
            "bullish_count": sum(row["bias"] == "bullish" for row in rows),
            "neutral_count": sum(row["bias"] == "neutral" for row in rows),
            "bearish_count": sum(row["bias"] == "bearish" for row in rows),
            "active_strategy_signals": sum(len(row["active_strategies"]) for row in rows),
            "active_pattern_signals": sum(len(row["patterns"]) for row in rows),
        }
        stable = {
            "as_of": as_of,
            "data_source": str(scan.get("source") or self.provider.name),
            "data_state": data_state,
            "coverage": coverage,
            "summary": summary,
            "catalog": self._catalog(),
            "rows": rows,
            "matched_rows": rows,
            "excluded_by_rules": excluded_by_rules,
            "screening_model": {
                "type": "hard_rules",
                "market": market,
                "universe_mode": universe_mode,
                "effective_universe_mode": "quick" if broad_error else universe_mode,
                "filters": normalized_filters,
            },
            "screening_coverage": {
                "before_rules": broad_eligible_count,
                "after_market_rules": market_eligible_count,
                "deep_pool_count": len(items),
                "analyzed_count": len(analyzed_rows),
                "after_fundamental_rules": len(analyzed_rows) - fundamental_excluded_count,
                "after_rules": len(rows),
                "excluded_by_rules": len(excluded_by_rules),
            },
            "failures": failures,
            "fundamental_failures": fundamental_failures,
            "institutional_evidence_failures": institutional_evidence_failures,
            "short_history_watchlist": short_history_watchlist,
            "limitations": limitations,
        }
        return {
            "engine": {"name": self.engine_name, "version": self.engine_version},
            **stable,
            "snapshot": self._build_snapshot(
                scan, stable, universe_size, bars, market, universe_mode, normalized_filters
            ),
        }

    def _quick_scan(self, market: str, universe_size: int):
        if market == "CN":
            return self.provider.get_liquidity_scan(limit=universe_size)
        if market == "HK":
            return self.provider.get_stock_scan(
                market="HK", sort="amount", order="desc", limit=universe_size
            )
        cn_scan = self.provider.get_liquidity_scan(limit=universe_size)
        hk_scan = self.provider.get_stock_scan(
            market="HK", sort="amount", order="desc", limit=universe_size
        )
        return {
            "items": [
                *({**item, "market": "CN"} for item in cn_scan.get("items") or []),
                *({**item, "market": "HK"} for item in hk_scan.get("items") or []),
            ],
            "source": "+".join(str(value) for value in (
                cn_scan.get("source"), hk_scan.get("source")
            ) if value),
            "as_of": max(str(cn_scan.get("as_of") or ""), str(hk_scan.get("as_of") or "")),
            "coverage": {
                "scope": "combined_liquidity_pool",
                "sort_basis": "amount",
                "markets": ["CN", "HK"],
            },
        }

    def _empty_screening_result(
        self,
        *,
        scan,
        universe_size,
        bars,
        market,
        universe_mode,
        filters,
        broad_error,
        broad_eligible_count,
        market_excluded,
    ):
        raw_as_of = str(scan.get("as_of") or "")
        try:
            as_of = pd.Timestamp(raw_as_of).strftime("%Y-%m-%d") if raw_as_of else date.today().isoformat()
        except ValueError:
            as_of = date.today().isoformat()
        limitations = ["latest_cross_section_only_no_historical_replay"]
        if broad_error:
            limitations.append("broad_universe_unavailable_quick_fallback")
        coverage = {
            "scan_count": len(scan.get("items") or []),
            "broad_eligible_count": broad_eligible_count,
            "market_prefilter_count": 0,
            "market_prefilter_excluded_count": len(market_excluded),
            "eligible_count": 0,
            "analyzed_count": 0,
            "matched_count": 0,
            "excluded_by_rules_count": len(market_excluded),
            "fundamental_requested": self._fundamental_requested(filters),
            "fundamental_evaluated_count": 0,
            "fundamental_available_count": 0,
            "fundamental_failed_count": 0,
            "fundamental_excluded_count": 0,
            "technical_excluded_count": 0,
            "failed_count": 0,
            "short_history_watch_count": 0,
            "scan_scope": str((scan.get("coverage") or {}).get("scope") or ""),
            "scan_sort_basis": str((scan.get("coverage") or {}).get("sort_basis") or "amount"),
            "deep_pool_selection_basis": self._deep_pool_selection_basis(filters),
            "requested_universe_mode": universe_mode,
            "effective_universe_mode": "quick" if broad_error else universe_mode,
            "broad_fallback_reason": broad_error,
        }
        summary = {
            "leading_symbol": "",
            "leading_name": "",
            "leading_score": 0,
            "bullish_count": 0,
            "neutral_count": 0,
            "bearish_count": 0,
            "active_strategy_signals": 0,
            "active_pattern_signals": 0,
        }
        stable = {
            "as_of": as_of,
            "data_source": str(scan.get("source") or self.provider.name),
            "data_state": "partial" if broad_error else "complete",
            "coverage": coverage,
            "summary": summary,
            "catalog": self._catalog(),
            "rows": [],
            "matched_rows": [],
            "excluded_by_rules": market_excluded,
            "screening_model": {
                "type": "hard_rules",
                "market": market,
                "universe_mode": universe_mode,
                "effective_universe_mode": "quick" if broad_error else universe_mode,
                "filters": filters,
            },
            "screening_coverage": {
                "before_rules": broad_eligible_count,
                "after_market_rules": 0,
                "deep_pool_count": 0,
                "analyzed_count": 0,
                "after_fundamental_rules": 0,
                "after_rules": 0,
                "excluded_by_rules": len(market_excluded),
            },
            "failures": [],
            "fundamental_failures": [],
            "short_history_watchlist": [],
            "limitations": limitations,
        }
        return {
            "engine": {"name": self.engine_name, "version": self.engine_version},
            **stable,
            "snapshot": self._build_snapshot(
                scan, stable, universe_size, bars, market, universe_mode, filters
            ),
        }

    def _analyze_one(self, item: dict[str, Any], bars: int) -> dict[str, Any]:
        symbol = str(item.get("symbol") or "").split(".")[0]
        market = str(item.get("market") or "CN").upper()
        query_symbol = f"{symbol}.HK" if market == "HK" else symbol
        frame = self._normalize_frame(
            self.provider.get_kline(query_symbol, limit=bars), symbol
        )
        if len(frame) < self.minimum_analysis_bars:
            raise TechnicalSignalInsufficientHistory(
                len(frame),
                required_bars=self.minimum_analysis_bars,
                data_start=(
                    pd.Timestamp(frame["date"].iloc[0]).strftime("%Y-%m-%d")
                    if not frame.empty else ""
                ),
                data_end=(
                    pd.Timestamp(frame["date"].iloc[-1]).strftime("%Y-%m-%d")
                    if not frame.empty else ""
                ),
                source=str(
                    frame.attrs.get("upstream_source")
                    or frame.attrs.get("data_source")
                    or ""
                ),
                has_more=frame.attrs.get("upstream_has_more"),
            )

        indicators = self._indicators(frame)
        indicator_signals = self._indicator_signals(frame, indicators)
        patterns = self._patterns(frame)
        scan_amount = self._number(item.get("amount"))
        strategies = self._strategies(
            frame,
            indicators,
            latest_amount=scan_amount if scan_amount > 0 else None,
        )
        institutional_evidence_failure = self._confirm_high_tight_flag(
            symbol, market, strategies
        )
        active_strategies = [item["name"] for item in strategies if item["state"] == "active"]
        bullish_patterns = sum(item["direction"] == "bullish" for item in patterns)
        bearish_patterns = sum(item["direction"] == "bearish" for item in patterns)
        bullish_strategies = sum(
            item["state"] == "active" and item["id"] != "climax_limitdown"
            for item in strategies
        )
        bearish_strategies = sum(
            item["state"] == "active" and item["id"] == "climax_limitdown"
            for item in strategies
        )
        score = 50 + len(indicator_signals["buy"]) * 5 - len(indicator_signals["sell"]) * 6
        score += bullish_patterns * 3 - bearish_patterns * 4
        score += bullish_strategies * 4 - bearish_strategies * 8
        score = round(max(0.0, min(100.0, score)), 2)
        bias = "bullish" if score >= 65 else "bearish" if score <= 35 else "neutral"
        return {
            "symbol": symbol,
            "market": market,
            "name": str(item.get("name") or symbol),
            "industry": str(item.get("industry") or "未分类"),
            "price": round(self._number(item.get("price"), float(frame["close"].iloc[-1])), 3),
            "change_pct": round(self._number(item.get("change_pct"), float(frame["p_change"].iloc[-1])), 3),
            "amount": round(self._number(item.get("amount"), float(frame["amount"].iloc[-1])), 2),
            "turnover_pct": round(self._number(item.get("turnover_pct")), 3),
            "volume_ratio": round(self._number(item.get("volume_ratio"), indicators["volume_ratio_5"]), 3),
            "pe": round(self._number(item.get("pe")), 3),
            "pb": round(self._number(item.get("pb")), 3),
            "market_cap": round(self._number(item.get("market_cap")), 2),
            "technical_score": score,
            "bias": bias,
            "indicators": indicators,
            "indicator_signals": indicator_signals,
            "patterns": patterns,
            "strategies": strategies,
            "active_strategies": active_strategies,
            "institutional_evidence_failure": institutional_evidence_failure,
            "history_bars": len(frame),
            "data_end": pd.Timestamp(frame["date"].iloc[-1]).strftime("%Y-%m-%d"),
            "_market_screening_evidence": item.get("_market_screening_evidence"),
        }

    @staticmethod
    def _normalize_frame(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
        required = ["date", "open", "high", "low", "close", "volume"]
        missing = [name for name in required if name not in frame]
        if missing:
            raise TechnicalSignalCenterError(f"行情字段缺失: {', '.join(missing)}")
        result = frame.copy()
        result["date"] = pd.to_datetime(result["date"], errors="coerce")
        for column in required[1:]:
            result[column] = pd.to_numeric(result[column], errors="coerce")
        result = result.dropna(subset=required).sort_values("date").reset_index(drop=True)
        if "amount" not in result:
            result["amount"] = result["close"] * result["volume"]
        else:
            result["amount"] = pd.to_numeric(result["amount"], errors="coerce").fillna(
                result["close"] * result["volume"]
            )
        result["p_change"] = result["close"].pct_change().fillna(0.0) * 100
        result["code"] = symbol
        return result

    def _indicators(self, frame: pd.DataFrame) -> dict[str, float]:
        close = frame["close"].to_numpy(dtype=float)
        high = frame["high"].to_numpy(dtype=float)
        low = frame["low"].to_numpy(dtype=float)
        volume = frame["volume"].to_numpy(dtype=float)
        macd, macd_signal, macd_hist = tl.MACD(close, 12, 26, 9)
        kdj_k, kdj_d = tl.STOCH(high, low, close, 9, 3, 0, 3, 0)
        boll_upper, boll_mid, boll_lower = tl.BBANDS(close, 20, 2, 2, 0)
        ma5 = tl.MA(close, 5)
        ma10 = tl.MA(close, 10)
        ma20 = tl.MA(close, 20)
        ma60 = tl.MA(close, 60)
        ma250 = tl.MA(close, 250)
        atr = tl.ATR(high, low, close, 14)
        latest = float(close[-1])
        volume_base = float(np.nanmean(volume[-6:-1])) if len(volume) >= 6 else float(np.nanmean(volume))
        return {
            "macd": self._last(macd),
            "macd_signal": self._last(macd_signal),
            "macd_hist": self._last(macd_hist),
            "rsi": self._last(tl.RSI(close, 14)),
            "kdj_k": self._last(kdj_k),
            "kdj_d": self._last(kdj_d),
            "boll_upper": self._last(boll_upper),
            "boll_mid": self._last(boll_mid),
            "boll_lower": self._last(boll_lower),
            "atr_pct": round(self._last(atr) / latest * 100, 3) if latest else 0.0,
            "cci": self._last(tl.CCI(high, low, close, 14)),
            "mfi": self._last(tl.MFI(high, low, close, volume, 14)),
            "obv": self._last(tl.OBV(close, volume)),
            "sar": self._last(tl.SAR(high, low)),
            "roc_20": round((latest / float(close[-21]) - 1) * 100, 3) if len(close) > 20 else 0.0,
            "ma5": self._last(ma5),
            "ma10": self._last(ma10),
            "ma20": self._last(ma20),
            "ma60": self._last(ma60),
            "ma250": self._last(ma250),
            "volume_ratio_5": round(float(volume[-1]) / volume_base, 3) if volume_base > 0 else 0.0,
        }

    @staticmethod
    def _indicator_signals(frame: pd.DataFrame, indicators: dict[str, float]) -> dict[str, list[str]]:
        close = float(frame["close"].iloc[-1])
        buy: list[str] = []
        sell: list[str] = []
        if close > indicators["ma20"] > indicators["ma60"] > 0:
            buy.append("价格站上中期均线")
        if indicators["ma5"] > indicators["ma10"] > indicators["ma20"] > 0:
            buy.append("短中期均线多头")
        if indicators["macd_hist"] > 0 and indicators["macd"] > indicators["macd_signal"]:
            buy.append("MACD 多头")
        if 50 <= indicators["rsi"] <= 75:
            buy.append("RSI 强势未极端")
        if indicators["volume_ratio_5"] >= 1.5 and frame["p_change"].iloc[-1] > 0:
            buy.append("量价共振")
        if close < indicators["ma20"] < indicators["ma60"] and indicators["ma60"] > 0:
            sell.append("价格跌破中期均线")
        if indicators["macd_hist"] < 0 and indicators["macd"] < indicators["macd_signal"]:
            sell.append("MACD 空头")
        if indicators["rsi"] >= 80:
            sell.append("RSI 过热")
        if indicators["rsi"] <= 25:
            sell.append("RSI 极弱")
        if indicators["boll_upper"] > 0 and close > indicators["boll_upper"] * 1.02:
            sell.append("突破布林上轨过远")
        return {"buy": buy, "sell": sell}

    @staticmethod
    def _patterns(frame: pd.DataFrame) -> list[dict[str, Any]]:
        arrays = [frame[column].to_numpy(dtype=float) for column in ("open", "high", "low", "close")]
        patterns = []
        for pattern_id, name, function in PATTERN_CATALOG:
            value = TechnicalSignalCenterEngine._last(function(*arrays))
            if not value:
                continue
            patterns.append({
                "id": pattern_id,
                "name": name,
                "direction": "bullish" if value > 0 else "bearish",
                "value": int(value),
            })
        return patterns

    def _strategies(
        self,
        frame: pd.DataFrame,
        indicators: dict[str, float],
        *,
        latest_amount: float | None = None,
    ) -> list[dict[str, Any]]:
        close = frame["close"]
        p_change = frame["p_change"]
        latest_close = float(close.iloc[-1])
        latest_amount = (
            float(latest_amount)
            if latest_amount is not None and latest_amount > 0
            else float(frame["amount"].iloc[-1])
        )
        latest_change = float(p_change.iloc[-1])
        volume_ratio = indicators["volume_ratio_5"]

        results = []
        results.append(self._strategy(
            "volume_rise", latest_change >= 2 and latest_close >= float(frame["open"].iloc[-1])
            and latest_amount >= 2e8 and volume_ratio >= 2,
            [f"涨幅 {latest_change:.2f}%", f"5日量比 {volume_ratio:.2f}", f"成交额 {latest_amount / 1e8:.1f} 亿"],
        ))

        ma20_prior = float(close.iloc[-40:-20].mean()) if len(close) >= 40 else 0.0
        results.append(self._strategy(
            "ma_bull", indicators["ma5"] > indicators["ma10"] > indicators["ma20"] > indicators["ma60"] > 0
            and indicators["ma20"] > ma20_prior,
            ["MA5 > MA10 > MA20 > MA60", "MA20 斜率向上"],
        ))

        results.append(self._strategy(
            "parking_apron", self._parking_apron(frame),
            ["近 15 日涨停后连续 3 日在涨停收盘价上方窄幅整理"],
        ))

        if len(frame) < 250:
            results.append(self._strategy(
                "backtrace_ma250", False, [], state="unavailable", missing=["至少 250 根日线"]
            ))
        else:
            results.append(self._strategy(
                "backtrace_ma250", self._backtrace_ma250(frame, indicators),
                ["近 60 日由年线下方突破后保持在 MA250 上方", "回踩阶段缩量"],
            ))

        prior_high = float(close.iloc[-21:-1].max()) if len(close) > 21 else float(close.iloc[:-1].max())
        results.append(self._strategy(
            "breakthrough_platform", latest_close > prior_high and volume_ratio >= 1.3,
            [f"突破前 20 日收盘高点 {prior_high:.2f}", f"5日量比 {volume_ratio:.2f}"],
        ))

        window = frame.tail(60)
        return_60 = latest_close / float(window["close"].iloc[0]) - 1
        bad_single = bool((window["p_change"] < -7).any())
        bad_two_day = bool((window["p_change"] + window["p_change"].shift(1) < -10).any())
        results.append(self._strategy(
            "low_backtrace_increase", return_60 >= 0.60 and not bad_single and not bad_two_day,
            [f"60 日涨幅 {return_60 * 100:.2f}%", "无单日 -7% 或两日累计 -10% 回撤"],
        ))

        prior_60_high = float(close.iloc[-61:-1].max()) if len(close) > 60 else float(close.iloc[:-1].max())
        results.append(self._strategy(
            "turtle_trade", latest_close >= prior_60_high,
            [f"收盘 {latest_close:.2f}", f"前 60 日最高收盘 {prior_60_high:.2f}"],
        ))

        high_tight_ready = self._high_tight_price_ready(frame)
        results.append(self._strategy(
            "high_tight_flag", False,
            ["价格形态前置条件已满足"] if high_tight_ready else ["价格形态前置条件未满足"],
            state="needs_evidence" if high_tight_ready else "inactive",
            missing=["机构龙虎榜证据"] if high_tight_ready else [],
        ))

        results.append(self._strategy(
            "climax_limitdown", latest_change <= -9.5 and latest_amount >= 2e8 and volume_ratio >= 4,
            [f"跌幅 {latest_change:.2f}%", f"5日量比 {volume_ratio:.2f}"],
        ))

        results.append(self._strategy(
            "low_atr_growth", indicators["roc_20"] > 5 and indicators["atr_pct"] <= 4
            and latest_close > indicators["ma60"] > 0,
            [f"20 日动量 {indicators['roc_20']:.2f}%", f"ATR/价格 {indicators['atr_pct']:.2f}%", "价格在 MA60 上方"],
        ))
        return results

    def _confirm_high_tight_flag(
        self, symbol: str, market: str, strategies: list[dict[str, Any]]
    ) -> str:
        strategy = next(
            (item for item in strategies if item["id"] == "high_tight_flag"),
            None,
        )
        if not strategy or strategy["state"] != "needs_evidence":
            return ""
        if market != "CN":
            strategy.update({
                "state": "unavailable",
                "missing": ["龙虎榜机构席位证据仅覆盖 A 股"],
            })
            return ""
        try:
            packet = self.provider.get_dragon_tiger_evidence(symbol)
        except MarketDataError as exc:
            strategy["missing"] = ["机构龙虎榜证据读取失败"]
            return str(exc)

        records = packet.get("records") or []
        institution = packet.get("institution") or {}
        net_amount = self._number(institution.get("net_amt"))
        latest = records[0] if records else {}
        external = {
            "source": str(packet.get("source") or "capital.dragon-tiger"),
            "date": str(latest.get("date") or ""),
            "institution_net_cny_10k": round(net_amount, 2),
        }
        if records and net_amount > 0:
            strategy.update({
                "state": "active",
                "evidence": strategy["evidence"] + [
                    f"{str(latest.get('date') or '最近一期')} 机构专用席位净买 {net_amount:,.1f} 万元",
                    f"上榜原因：{str(latest.get('reason') or '交易公开信息')}",
                ],
                "missing": [],
                "external_evidence": external,
            })
            return ""

        reason = (
            f"机构专用席位净额 {net_amount:,.1f} 万元，未形成净买确认"
            if records else "近 30 日无龙虎榜机构席位记录"
        )
        strategy.update({
            "state": "inactive",
            "evidence": strategy["evidence"] + [reason],
            "missing": [],
            "external_evidence": external,
        })
        return ""

    @staticmethod
    def _parking_apron(frame: pd.DataFrame) -> bool:
        window = frame.tail(15).reset_index(drop=True)
        for index in range(max(len(window) - 3, 0)):
            row = window.iloc[index]
            if row["p_change"] < 9.5:
                continue
            follow = window.iloc[index + 1:index + 4]
            if len(follow) == 3 and all(
                item["close"] > row["close"] and item["open"] > row["close"]
                and abs(item["close"] / item["open"] - 1) < 0.03
                and abs(item["p_change"]) < 5
                for _, item in follow.iterrows()
            ):
                return True
        return False

    @staticmethod
    def _backtrace_ma250(frame: pd.DataFrame, indicators: dict[str, float]) -> bool:
        close = frame["close"].to_numpy(dtype=float)
        ma250 = tl.MA(close, 250)
        window = frame.tail(60).copy()
        window["ma250"] = ma250[-len(window):]
        window = window.dropna(subset=["ma250"])
        if len(window) < 20:
            return False
        crossed = bool(((window["close"].shift(1) < window["ma250"].shift(1)) & (window["close"] >= window["ma250"])).any())
        above = bool((window.tail(10)["close"] >= window.tail(10)["ma250"]).all())
        peak_index = int(window["close"].to_numpy().argmax())
        after_peak = window.iloc[peak_index:]
        if len(after_peak) < 5:
            return False
        peak_volume = float(window.iloc[peak_index]["volume"])
        low_row = after_peak.loc[after_peak["close"].idxmin()]
        shrunk = peak_volume > float(low_row["volume"]) * 1.5
        near_ma = float(low_row["close"]) <= float(low_row["ma250"]) * 1.08
        return crossed and above and shrunk and near_ma and indicators["ma250"] > 0

    @staticmethod
    def _high_tight_price_ready(frame: pd.DataFrame) -> bool:
        if len(frame) < 60:
            return False
        segment = frame.iloc[-24:-10]
        if segment.empty or float(segment["low"].min()) <= 0:
            return False
        price_run = float(segment["high"].max()) / float(segment["low"].min()) >= 1.9
        consecutive_limit = bool(((segment["p_change"] >= 9.5) & (segment["p_change"].shift(1) >= 9.5)).any())
        return price_run and consecutive_limit

    @staticmethod
    def _strategy(strategy_id, active, evidence, *, state=None, missing=None):
        name, category = next((name, category) for item_id, name, category in STRATEGY_CATALOG if item_id == strategy_id)
        return {
            "id": strategy_id,
            "name": name,
            "category": category,
            "state": state or ("active" if active else "inactive"),
            "evidence": evidence,
            "missing": list(missing or []),
        }

    @staticmethod
    def _catalog():
        return {
            "indicators": [
                {"id": "macd", "name": "MACD"}, {"id": "kdj", "name": "KDJ"},
                {"id": "rsi", "name": "RSI"}, {"id": "boll", "name": "BOLL"},
                {"id": "atr", "name": "ATR"}, {"id": "cci", "name": "CCI"},
                {"id": "mfi", "name": "MFI"}, {"id": "obv", "name": "OBV"},
                {"id": "sar", "name": "SAR"}, {"id": "ma", "name": "均线系统"},
            ],
            "patterns": [{"id": item[0], "name": item[1]} for item in PATTERN_CATALOG],
            "strategies": [
                {"id": item_id, "name": name, "category": category}
                for item_id, name, category in STRATEGY_CATALOG
            ],
        }

    @staticmethod
    def _valid_item(item, market="CN"):
        if not isinstance(item, dict):
            return False
        symbol = str(item.get("symbol") or "").split(".")[0]
        name = str(item.get("name") or "")
        pattern = r"\d{6}" if market == "CN" else r"\d{5}"
        return bool(re.fullmatch(pattern, symbol)) and "ST" not in name.upper() and "退" not in name

    @classmethod
    def _select_deep_pool(cls, rows, limit, markets, filters=None):
        relevant_memberships = cls._deep_pool_selection_basis(filters)
        use_composite = relevant_memberships == ["multi_axis_composite"]

        def priority(row):
            membership_scores = row.get("scan_membership_scores") or {}
            filter_score = (
                cls._number(row.get("scan_rank_score"))
                if use_composite
                else sum(cls._number(membership_scores.get(key)) for key in relevant_memberships)
            )
            return (
                filter_score,
                cls._number(row.get("scan_rank_score")),
                len(row.get("scan_memberships") or []),
                cls._number(row.get("amount")),
                cls._number(row.get("market_cap")),
                str(row.get("symbol") or ""),
            )

        buckets = {
            market: sorted(
                (row for row in rows if row.get("market") == market),
                key=priority,
                reverse=True,
            )
            for market in markets
        }
        selected = []
        selected_keys = set()
        base_quota, extra = divmod(limit, len(markets))
        for index, market in enumerate(markets):
            for row in buckets[market][:base_quota + (1 if index < extra else 0)]:
                selected.append(row)
                selected_keys.add((row.get("market"), row.get("symbol")))
        if len(selected) < limit:
            for row in sorted(rows, key=priority, reverse=True):
                key = (row.get("market"), row.get("symbol"))
                if key in selected_keys:
                    continue
                selected.append(row)
                selected_keys.add(key)
                if len(selected) >= limit:
                    break
        return selected

    @staticmethod
    def _deep_pool_selection_basis(filters):
        filters = filters or {}
        mapping = (
            ("min_amount", "amount:desc"),
            ("min_market_cap", "marketCap:desc"),
            ("max_market_cap", "marketCap:asc"),
            ("max_pe", "pe:asc"),
            ("max_pb", "pb:asc"),
            ("min_turnover_pct", "turnoverPct:desc"),
            ("max_turnover_pct", "turnoverPct:asc"),
            ("min_volume_ratio", "volumeRatio:desc"),
            ("max_volume_ratio", "volumeRatio:asc"),
        )
        basis = [membership for key, membership in mapping if filters.get(key) is not None]
        return basis or ["multi_axis_composite"]

    def _load_fundamentals(self, rows, *, filters, refresh=False):
        symbols = list(dict.fromkeys(row["symbol"] for row in rows))
        packets: dict[str, dict[str, Any]] = {}
        errors: dict[str, str] = {}
        chunks = [
            symbols[offset:offset + self.fundamental_batch_size]
            for offset in range(0, len(symbols), self.fundamental_batch_size)
        ]

        def load_chunk(chunk):
            return chunk, self.provider.get_equity_comparison(chunk, refresh=refresh)

        if chunks:
            workers = min(self.fundamental_batch_workers, len(chunks))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                jobs = {pool.submit(load_chunk, chunk): chunk for chunk in chunks}
                for future in as_completed(jobs):
                    chunk = jobs[future]
                    try:
                        _, payload = future.result()
                        generated_at = str(payload.get("generatedAt") or "")
                        for raw in payload.get("rows") or []:
                            if not isinstance(raw, Mapping):
                                continue
                            symbol = str((raw.get("identity") or {}).get("symbol") or "").split(".")[0]
                            if symbol not in chunk:
                                continue
                            packet = self._normalize_fundamentals(
                                raw.get("metrics"),
                                source="research.equity-comparison",
                                generated_at=generated_at,
                            )
                            if self._fundamental_packet_complete(packet, filters):
                                packets[symbol] = packet
                        for raw in payload.get("errors") or []:
                            if not isinstance(raw, Mapping):
                                continue
                            symbol = str(raw.get("symbol") or "").split(".")[0]
                            if symbol in chunk:
                                errors[symbol] = str(raw.get("error") or "Desk 横向比较失败")
                    except (MarketDataError, TypeError, ValueError, KeyError) as exc:
                        for symbol in chunk:
                            errors[symbol] = str(exc)

        missing = [symbol for symbol in symbols if symbol not in packets]
        fallback_symbols = missing[:self.fundamental_snapshot_fallback_limit]

        def load_snapshot(symbol):
            payload = self.provider.get_equity_snapshot(symbol, refresh=refresh)
            profile = payload.get("comparisonProfile") or {}
            metrics = profile.get("metrics") if isinstance(profile, Mapping) else {}
            return self._normalize_fundamentals(
                metrics,
                source="research.equity-snapshot",
                generated_at=str(payload.get("generatedAt") or ""),
            )

        if fallback_symbols:
            workers = min(self.fundamental_snapshot_workers, len(fallback_symbols))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                jobs = {pool.submit(load_snapshot, symbol): symbol for symbol in fallback_symbols}
                for future in as_completed(jobs):
                    symbol = jobs[future]
                    try:
                        packet = future.result()
                        if not self._fundamental_packet_complete(packet, filters):
                            raise TechnicalSignalCenterError("Desk 财务快照缺少所需 ROE 或成长指标")
                        packets[symbol] = packet
                        errors.pop(symbol, None)
                    except (MarketDataError, TechnicalSignalCenterError, TypeError, ValueError, KeyError) as exc:
                        errors[symbol] = str(exc)

        for symbol in missing[self.fundamental_snapshot_fallback_limit:]:
            errors.setdefault(symbol, "Desk 横向比较未返回财务指标，逐股回退上限为 30 只")
        for symbol in symbols:
            if symbol not in packets:
                errors.setdefault(symbol, "Desk 未返回可用基本面指标")
        failures = [
            {"symbol": symbol, "error": errors[symbol]}
            for symbol in sorted(errors)
        ]
        return packets, failures

    @classmethod
    def _normalize_fundamentals(cls, raw_metrics, *, source, generated_at=""):
        metrics = raw_metrics if isinstance(raw_metrics, Mapping) else {}

        def metric(*keys):
            for key in keys:
                if key in metrics:
                    value = cls._optional_number(metrics.get(key))
                    if value is not None:
                        return round(value, 2)
            return None

        normalized = {
            "roe_pct": metric("roePct", "roe_pct", "roe"),
            "revenue_growth_pct": metric(
                "revenueGrowthPct", "revenue_growth_pct", "revenueGrowth"
            ),
            "net_profit_growth_pct": metric(
                "netProfitGrowthPct", "net_profit_growth_pct", "netProfitGrowth"
            ),
        }
        return {
            "available": any(value is not None for value in normalized.values()),
            "source": source,
            "generated_at": generated_at,
            **normalized,
        }

    @staticmethod
    def _empty_fundamentals():
        return {
            "available": False,
            "source": "",
            "generated_at": "",
            "roe_pct": None,
            "revenue_growth_pct": None,
            "net_profit_growth_pct": None,
        }

    @staticmethod
    def _fundamental_requested(filters):
        return any(filters.get(key) is not None for key in (
            "min_roe_pct",
            "min_revenue_growth_pct",
            "min_net_profit_growth_pct",
        ))

    @staticmethod
    def _fundamental_packet_complete(packet, filters):
        rules = (
            ("min_roe_pct", "roe_pct"),
            ("min_revenue_growth_pct", "revenue_growth_pct"),
            ("min_net_profit_growth_pct", "net_profit_growth_pct"),
        )
        return all(
            filters.get(filter_key) is None or packet.get(metric_key) is not None
            for filter_key, metric_key in rules
        )

    @staticmethod
    def _fundamental_screening_evidence(packet, filters):
        reasons = []
        checks = []
        rules = (
            ("min_roe_pct", "roe_pct", "ROE"),
            ("min_revenue_growth_pct", "revenue_growth_pct", "营收增长"),
            ("min_net_profit_growth_pct", "net_profit_growth_pct", "净利润增长"),
        )
        for filter_key, metric_key, label in rules:
            target = filters[filter_key]
            if target is None:
                continue
            actual = packet.get(metric_key)
            if actual is None:
                message = f"{label}数据缺失"
                checks.append({"passed": False, "message": message})
                reasons.append(message)
                continue
            passed = float(actual) >= target
            message = (
                f"{label} {float(actual):g}% >= {target:g}%"
                if passed
                else f"{label} {float(actual):g}% 未满足 >= {target:g}%"
            )
            checks.append({"passed": passed, "message": message})
            if not passed:
                reasons.append(message)
        return {"passed": not reasons, "checks": checks, "reasons": reasons}

    @classmethod
    def _normalize_filters(cls, filters):
        raw = dict(filters or {})
        list_fields = ("industries", "required_strategies", "required_patterns")
        number_fields = (
            "min_technical_score", "min_amount", "min_market_cap", "max_market_cap",
            "max_pe", "max_pb", "min_turnover_pct", "max_turnover_pct",
            "min_volume_ratio", "max_volume_ratio", "min_roe_pct",
            "min_revenue_growth_pct", "min_net_profit_growth_pct",
        )
        result = {key: sorted({str(value).strip() for value in raw.get(key) or [] if str(value).strip()}) for key in list_fields}
        for key in number_fields:
            value = raw.get(key)
            result[key] = None if value in (None, "") else cls._number(value)
        bias = str(raw.get("bias") or "all").strip().lower()
        if bias not in {"all", "bullish", "neutral", "bearish"}:
            raise TechnicalSignalCenterError("方向仅支持 all、bullish、neutral、bearish")
        result["bias"] = bias
        valid_strategies = {item[0] for item in STRATEGY_CATALOG}
        valid_patterns = {item[0] for item in PATTERN_CATALOG}
        if not set(result["required_strategies"]) <= valid_strategies:
            raise TechnicalSignalCenterError("包含未知经典策略")
        if not set(result["required_patterns"]) <= valid_patterns:
            raise TechnicalSignalCenterError("包含未知 K 线形态")
        return result

    @staticmethod
    def _market_screening_evidence(row, filters):
        reasons = []
        checks = []

        def require(condition, passed_text, failed_text):
            checks.append({"passed": bool(condition), "message": passed_text if condition else failed_text})
            if not condition:
                reasons.append(failed_text)

        if filters["industries"]:
            require(row["industry"] in filters["industries"], f"行业为 {row['industry']}", f"行业 {row['industry']} 不在指定范围")
        numeric_rules = (
            ("min_amount", "amount", ">=", "成交额"),
            ("min_market_cap", "market_cap", ">=", "市值"),
            ("max_market_cap", "market_cap", "<=", "市值"),
            ("max_pe", "pe", "<=", "PE"),
            ("max_pb", "pb", "<=", "PB"),
            ("min_turnover_pct", "turnover_pct", ">=", "换手率"),
            ("max_turnover_pct", "turnover_pct", "<=", "换手率"),
            ("min_volume_ratio", "volume_ratio", ">=", "量比"),
            ("max_volume_ratio", "volume_ratio", "<=", "量比"),
        )
        for filter_key, row_key, operator, label in numeric_rules:
            target = filters[filter_key]
            if target is None:
                continue
            actual = float(row.get(row_key) or 0)
            has_required_value = not (
                operator == "<=" and row_key in {"market_cap", "pe", "pb"} and actual <= 0
            )
            passed = has_required_value and (
                actual >= target if operator == ">=" else actual <= target
            )
            require(passed, f"{label} {actual:g} {operator} {target:g}", f"{label} {actual:g} 未满足 {operator} {target:g}")
        return {"passed": not reasons, "checks": checks, "reasons": reasons}

    @staticmethod
    def _technical_screening_evidence(row, filters):
        reasons = []
        checks = []

        def require(condition, passed_text, failed_text):
            checks.append({"passed": bool(condition), "message": passed_text if condition else failed_text})
            if not condition:
                reasons.append(failed_text)

        if filters["bias"] != "all":
            require(row["bias"] == filters["bias"], f"方向为 {row['bias']}", f"方向为 {row['bias']}，要求 {filters['bias']}")
        target_score = filters["min_technical_score"]
        if target_score is not None:
            actual_score = float(row.get("technical_score") or 0)
            require(
                actual_score >= target_score,
                f"技术分 {actual_score:g} >= {target_score:g}",
                f"技术分 {actual_score:g} 未满足 >= {target_score:g}",
            )
        active_strategies = {item["id"] for item in row["strategies"] if item["state"] == "active"}
        for strategy_id in filters["required_strategies"]:
            name = next(item[1] for item in STRATEGY_CATALOG if item[0] == strategy_id)
            require(strategy_id in active_strategies, f"命中策略：{name}", f"未命中策略：{name}")
        active_patterns = {item["id"] for item in row["patterns"]}
        for pattern_id in filters["required_patterns"]:
            name = next(item[1] for item in PATTERN_CATALOG if item[0] == pattern_id)
            require(pattern_id in active_patterns, f"命中形态：{name}", f"未命中形态：{name}")
        return {"passed": not reasons, "checks": checks, "reasons": reasons}

    @staticmethod
    def _merge_screening_evidence(*parts):
        checks = []
        reasons = []
        for part in parts:
            if not part:
                continue
            checks.extend(part.get("checks") or [])
            reasons.extend(part.get("reasons") or [])
        return {"passed": not reasons, "checks": checks, "reasons": reasons}

    @staticmethod
    def _last(values) -> float:
        if values is None or len(values) == 0:
            return 0.0
        value = float(values[-1])
        return round(value, 6) if math.isfinite(value) else 0.0

    @staticmethod
    def _number(value, fallback=0.0):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return float(fallback)
        return number if math.isfinite(number) else float(fallback)

    @staticmethod
    def _optional_number(value):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    @staticmethod
    def _as_of(scan, rows):
        raw = str(scan.get("as_of") or "")
        if raw:
            try:
                return pd.Timestamp(raw).strftime("%Y-%m-%d")
            except ValueError:
                pass
        return max(row["data_end"] for row in rows)

    def _build_snapshot(self, scan, stable, universe_size, bars, market, universe_mode, filters):
        parameters = {
            "universeSize": universe_size,
            "bars": bars,
            "market": market,
            "universeMode": universe_mode,
            "filters": filters,
        }
        material = {
            "analysis": {"name": self.engine_name, "version": self.engine_version},
            "parameters": parameters,
            "scan": {"source": scan.get("source"), "as_of": scan.get("as_of"), "items": scan.get("items")},
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
            "parameters": parameters,
            "data_window": {"requested_as_of": None, "start_date": None, "end_date": stable["as_of"], "coverage": stable["data_state"]},
            "provenance": {
                "provider": self.provider.name,
                "endpoint": "market.scan + market.ohlcv",
                "upstream_source": stable["data_source"],
                "adjust": "qfq",
                "limitations": list(stable["limitations"]),
            },
            "freshness": {"state": "fresh" if lag_days <= 3 else "delayed", "resolution": "latest_cross_section", "calendar_lag_days": lag_days},
            "input": {"digest": f"sha256:{digest}", "summary": stable["coverage"]},
            "result": {"digest": f"sha256:{digest}", "summary": stable["summary"]},
        }
