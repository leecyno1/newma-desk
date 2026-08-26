#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Explainable A-share candidate ranking built from Desk market data."""

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

from instock.core.analysis_snapshot import SNAPSHOT_SCHEMA_VERSION
from instock.core.market_data_provider import MarketDataError, MarketDataProvider
from instock.core.research.event_flow import resolve_event_flow_snapshot


class StockCandidateError(ValueError):
    pass


class StockCandidateInsufficientHistory(StockCandidateError):
    def __init__(
        self,
        actual_bars: int,
        *,
        required_bars: int = 10,
        basis: str = "daily_bars",
        data_start: str = "",
        data_end: str = "",
        source: str = "",
        has_more: bool | None = None,
    ):
        self.actual_bars = int(actual_bars)
        self.required_bars = int(required_bars)
        self.basis = basis
        self.data_start = data_start
        self.data_end = data_end
        self.source = source
        self.has_more = has_more
        label = "有效日线" if basis == "daily_bars" else "有效收盘价"
        super().__init__(
            f"{label}不足 {self.required_bars} 根（实际 {self.actual_bars}），暂列新股观察"
        )


class StockCandidateEngine:
    engine_name = "instock-stock-candidate-engine"
    engine_version = "1.4.0"
    factor_model = "instock-stock-candidate-score-v3"
    minimum_rank_bars = 10
    full_history_bars = 80
    supported_universe_sizes = (30, 50, 100, 200)
    supported_output_sizes = (10, 20, 30)
    supported_bars = (120, 240)
    supported_markets = ("CN", "HK", "CN_HK")
    supported_universe_modes = ("broad", "quick")
    fundamental_preselection_limit = 30
    fundamental_batch_size = 4
    fundamental_batch_workers = 3
    fundamental_snapshot_workers = 3
    fundamental_batch_timeout_seconds = 60.0
    fundamental_snapshot_timeout_seconds = 20.0
    technical_factors = (
        "trend", "momentum", "liquidity", "stability", "valuation", "classic",
    )
    history_sensitive_factors = {"trend", "momentum", "stability", "classic"}
    weights = {
        "trend": 0.20,
        "momentum": 0.15,
        "liquidity": 0.10,
        "stability": 0.10,
        "valuation": 0.10,
        "quality": 0.15,
        "growth": 0.10,
        "classic": 0.10,
    }
    profile_weights = {
        "balanced": weights,
        "trend": {
            "trend": 0.25,
            "momentum": 0.20,
            "liquidity": 0.10,
            "stability": 0.05,
            "valuation": 0.05,
            "quality": 0.10,
            "growth": 0.15,
            "classic": 0.10,
        },
        "value": {
            "trend": 0.10,
            "momentum": 0.05,
            "liquidity": 0.10,
            "stability": 0.15,
            "valuation": 0.25,
            "quality": 0.20,
            "growth": 0.10,
            "classic": 0.05,
        },
        "defensive": {
            "trend": 0.10,
            "momentum": 0.05,
            "liquidity": 0.10,
            "stability": 0.20,
            "valuation": 0.15,
            "quality": 0.25,
            "growth": 0.10,
            "classic": 0.05,
        },
    }

    def __init__(self, provider: MarketDataProvider, *, max_workers: int = 8):
        self.provider = provider
        self.max_workers = max(1, min(int(max_workers), 12))

    @classmethod
    def _fundamental_limit(cls, output_size: int) -> int:
        return 20 if int(output_size) == 10 else cls.fundamental_preselection_limit

    def analyze(
        self,
        *,
        universe_size: int = 30,
        output_size: int = 10,
        bars: int = 120,
        market: str = "CN",
        universe_mode: str = "broad",
        profile: str = "balanced",
        filters: Mapping[str, Any] | None = None,
        event_flow_snapshot_id: str | None = None,
        refresh: bool = False,
    ):
        if universe_size not in self.supported_universe_sizes:
            raise StockCandidateError("深度计算池仅支持 30、50、100、200 只")
        if output_size not in self.supported_output_sizes:
            raise StockCandidateError("输出数量仅支持 10、20、30 只")
        if output_size > universe_size:
            raise StockCandidateError("输出数量不能大于候选池")
        if bars not in self.supported_bars:
            raise StockCandidateError("历史窗口仅支持 120、240 根日线")
        market = str(market or "CN").strip().upper()
        if market not in self.supported_markets:
            raise StockCandidateError("候选市场仅支持 CN、HK、CN_HK")
        universe_mode = str(universe_mode or "broad").strip().lower()
        if universe_mode not in self.supported_universe_modes:
            raise StockCandidateError("候选池模式仅支持 broad、quick")
        profile = str(profile or "balanced").strip().lower()
        if profile not in self.profile_weights:
            raise StockCandidateError("筛选画像仅支持 balanced、trend、value、defensive")
        active_weights = self.profile_weights[profile]
        normalized_filters = self._normalize_filters(filters)

        markets = ("CN", "HK") if market == "CN_HK" else (market,)
        if universe_mode == "broad":
            scan = self.provider.get_candidate_universe(
                markets=markets,
                per_scan_limit=200,
            )
        elif market == "CN":
            scan = self.provider.get_liquidity_scan(limit=universe_size)
        else:
            scan = self.provider.get_stock_scan(
                market="HK", sort="amount", order="desc", limit=universe_size
            )
        raw_items = scan.get("items") or []
        if not raw_items:
            raise StockCandidateError("Desk 股票扫描没有返回候选")

        eligible = []
        limitations = []
        seen = set()
        for item in raw_items:
            symbol = str(item.get("symbol") or "").split(".")[0]
            item_market = str(item.get("market") or markets[0]).strip().upper()
            name = str(item.get("name") or "").strip()
            valid_symbol = bool(re.fullmatch(
                r"\d{6}" if item_market == "CN" else r"\d{5}", symbol
            ))
            security_key = f"{item_market}:{symbol}"
            if item_market not in markets or not valid_symbol or security_key in seen:
                continue
            seen.add(security_key)
            if "ST" in name.upper() or "退" in name:
                limitations.append(f"excluded_special_treatment:{symbol}")
                continue
            if self._number(item.get("price")) <= 0:
                limitations.append(f"excluded_untradable:{symbol}")
                continue
            eligible.append({
                **dict(item),
                "symbol": symbol,
                "name": name,
                "market": item_market,
            })

        broad_eligible_count = len(eligible)
        market_eligible = []
        market_excluded = []
        for item in eligible:
            evidence = self._market_screening_evidence(item, normalized_filters)
            item["_market_screening_evidence"] = evidence
            if evidence["passed"]:
                market_eligible.append(item)
            else:
                market_excluded.append({
                    "symbol": item["symbol"],
                    "name": item["name"],
                    "stage": "market_prefilter",
                    "reasons": evidence["reasons"],
                })
        eligible = market_eligible
        market_eligible_count = len(eligible)
        if not eligible:
            raise StockCandidateError("当前市场筛选条件没有匹配到 A/H 股候选")
        deep_pool_basis = self._deep_pool_selection_basis(normalized_filters)
        if len(eligible) > universe_size:
            eligible = self._select_deep_pool(
                eligible, universe_size, markets, normalized_filters
            )

        analyzed = []
        failures = []
        history_exclusions = []
        with ThreadPoolExecutor(max_workers=min(self.max_workers, max(1, len(eligible)))) as pool:
            jobs = {
                pool.submit(self._analyze_one, item, bars): item
                for item in eligible
            }
            for future in as_completed(jobs):
                item = jobs[future]
                try:
                    analyzed.append(future.result())
                except StockCandidateInsufficientHistory as exc:
                    history_exclusions.append({
                        "symbol": item["symbol"],
                        "name": item["name"],
                        "reason": "new_listing_watch",
                        "basis": exc.basis,
                        "required_bars": exc.required_bars,
                        "available_bars": exc.actual_bars,
                        "history_mode": "new_listing_watch",
                        "technical_confidence": round(min(
                            1.0, exc.actual_bars / self.full_history_bars
                        ), 4),
                        "data_start": exc.data_start,
                        "data_end": exc.data_end,
                        "history_source": exc.source,
                        "history_has_more": exc.has_more,
                        "message": str(exc),
                    })
                except (MarketDataError, StockCandidateError, ValueError) as exc:
                    failures.append({
                        "symbol": item["symbol"],
                        "error": str(exc),
                    })
        analyzed.sort(key=lambda row: next(
            (index for index, item in enumerate(eligible) if (
                item["symbol"], item.get("market", "CN")
            ) == (row["symbol"], row.get("market", "CN"))),
            len(eligible),
        ))
        failures.sort(key=lambda row: next(
            (index for index, item in enumerate(eligible) if item["symbol"] == row["symbol"]),
            len(eligible),
        ))
        history_exclusions.sort(key=lambda row: next(
            (index for index, item in enumerate(eligible) if item["symbol"] == row["symbol"]),
            len(eligible),
        ))
        if not analyzed:
            raise StockCandidateError("候选池没有足够历史行情完成评分")

        screened = []
        excluded_by_rules = list(market_excluded)
        for row in analyzed:
            evidence = self._merge_screening_evidence(
                row.pop("_market_screening_evidence", {}),
                self._technical_screening_evidence(row, normalized_filters),
            )
            if evidence["passed"]:
                row["screening_evidence"] = evidence
                screened.append(row)
            else:
                excluded_by_rules.append({
                    "symbol": row["symbol"],
                    "name": row["name"],
                    "stage": "technical_rules",
                    "reasons": evidence["reasons"],
                })
        screening_coverage = {
            "before_rules": broad_eligible_count,
            "after_market_rules": market_eligible_count,
            "deep_pool_count": len(eligible),
            "analyzed_count": len(analyzed),
            "after_market_technical_rules": len(screened),
            "after_rules": len(screened),
            "excluded_by_rules": len(excluded_by_rules),
            "fundamental_evaluated": 0,
            "not_fundamental_preselected": 0,
        }
        if not screened:
            raise StockCandidateError("当前筛选条件没有匹配到 A/H 股候选")
        analyzed = screened

        frame = pd.DataFrame([
            {key: row["raw_factors"][key] for key in self.technical_factors}
            for row in analyzed
        ])
        factor_scores = {}
        for factor in self.technical_factors:
            series = pd.to_numeric(frame[factor], errors="coerce")
            if series.notna().sum() <= 1:
                factor_scores[factor] = pd.Series([50.0] * len(series), index=series.index)
            else:
                filled = series.fillna(series.median())
                factor_scores[factor] = filled.rank(method="average", pct=True) * 100

        preselection_weights = {
            factor: active_weights[factor]
            for factor in self.technical_factors
        }
        preselection_weight_total = sum(preselection_weights.values())
        preselection_weights = {
            factor: weight / preselection_weight_total
            for factor, weight in preselection_weights.items()
        }
        for index, row in enumerate(analyzed):
            row["_technical_percentile_scores"] = {
                factor: round(float(factor_scores[factor].iloc[index]), 2)
                for factor in self.technical_factors
            }
            row["_technical_scores"] = {}
            for factor in self.technical_factors:
                score = row["_technical_percentile_scores"][factor]
                if factor in self.history_sensitive_factors:
                    score = 50.0 + row["technical_confidence"] * (score - 50.0)
                row["_technical_scores"][factor] = round(score, 2)
            penalty, _ = self._risk_penalty(row)
            row["preselection_score"] = round(max(0.0, min(
                100.0,
                sum(
                    row["_technical_scores"][factor] * weight
                    for factor, weight in preselection_weights.items()
                ) - penalty,
            )), 2)

        analyzed.sort(key=lambda row: (-row["preselection_score"], row["symbol"]))
        for rank, row in enumerate(analyzed, 1):
            row["preselection_rank"] = rank
        fundamental_limit = self._fundamental_limit(output_size)
        fundamental_pool = analyzed[:fundamental_limit]
        screening_coverage["fundamental_evaluated"] = len(fundamental_pool)
        screening_coverage["not_fundamental_preselected"] = max(
            len(analyzed) - len(fundamental_pool), 0
        )
        (
            fundamental_packets,
            fundamental_errors,
            fundamental_batch_count,
            fundamental_fallback_count,
            fundamental_request_stats,
        ) = self._load_fundamentals(
            fundamental_pool,
            refresh=refresh,
        )

        fundamental_failures = [
            {
                "symbol": row["symbol"],
                "error": fundamental_errors[row["symbol"]],
            }
            for row in fundamental_pool
            if row["symbol"] not in fundamental_packets
        ]
        for row in fundamental_pool:
            symbol = row["symbol"]
            if symbol not in fundamental_packets:
                fundamental_packets[symbol] = self._neutral_fundamentals(
                    fundamental_errors.get(symbol, "Desk 财务快照不可用")
                )

        candidates = []
        for row in fundamental_pool:
            fundamentals = fundamental_packets[row["symbol"]]
            fundamental_evidence = self._fundamental_screening_evidence(
                fundamentals, normalized_filters
            )
            screening_evidence = self._merge_screening_evidence(
                row["screening_evidence"], fundamental_evidence
            )
            if not screening_evidence["passed"]:
                excluded_by_rules.append({
                    "symbol": row["symbol"],
                    "name": row["name"],
                    "stage": "fundamental_rules",
                    "reasons": screening_evidence["reasons"],
                })
                continue
            scores = {
                factor: (
                    fundamentals["scores"][factor]
                    if factor in {"valuation", "quality", "growth"}
                    else row["_technical_scores"][factor]
                )
                for factor in active_weights
            }
            contributions = {
                factor: round(scores[factor] * weight, 2)
                for factor, weight in active_weights.items()
            }
            penalty, risks = self._risk_penalty(row)
            total = max(0.0, min(100.0, sum(contributions.values()) - penalty))
            candidates.append({
                "symbol": row["symbol"],
                "market": row["market"],
                "name": row["name"],
                "industry": row["industry"],
                "price": row["price"],
                "change_pct": row["change_pct"],
                "amount": row["amount"],
                "amount_source": row["amount_source"],
                "turnover_pct": row["turnover_pct"],
                "volume_ratio": row["volume_ratio"],
                "market_cap": row["market_cap"],
                "pe": row["pe"],
                "pb": row["pb"],
                "score": round(total, 2),
                "preselection_rank": row["preselection_rank"],
                "preselection_score": row["preselection_score"],
                "penalty_score": round(penalty, 2),
                "history_bars": row["history_bars"],
                "history_mode": row["history_mode"],
                "technical_confidence": row["technical_confidence"],
                "data_start": row["data_start"],
                "factor_scores": scores,
                "factor_contributions": contributions,
                "fundamentals": fundamentals,
                "metrics": row["metrics"],
                "classic_signals": row["classic_signals"],
                "screening_evidence": screening_evidence,
                "risks": risks,
                "data_end": row["data_end"],
                "history_source": row["history_source"],
                "history_has_more": row["history_has_more"],
            })
        screening_coverage["after_rules"] = len(candidates)
        screening_coverage["excluded_by_rules"] = len(excluded_by_rules)
        if not candidates:
            raise StockCandidateError("当前高级筛选条件没有匹配到 A 股候选")
        candidates.sort(key=lambda row: (-row["score"], row["symbol"]))
        for rank, candidate in enumerate(candidates, 1):
            candidate["rank"] = rank
            if candidate["history_mode"] == "short":
                candidate["status"] = "短历史观察"
            else:
                candidate["status"] = "重点观察" if rank <= max(3, math.ceil(len(candidates) * 0.15)) else "候选" if candidate["score"] >= 60 else "观察"
        candidates = candidates[:output_size]

        event_flow, event_limitations = resolve_event_flow_snapshot(
            event_flow_snapshot_id,
            symbols=[
                row["symbol"] for row in candidates if row["market"] == "CN"
            ],
        )
        event_alerts = {}
        event_summaries = {}
        if event_flow is not None:
            for item in event_flow["alerts"]:
                event_alerts.setdefault(item["symbol"].split(".")[0], []).append(item)
            event_summaries = {
                item["symbol"].split(".")[0]: item
                for item in event_flow["symbol_summaries"]
            }
        for candidate in candidates:
            symbol = candidate["symbol"]
            candidate["event_evidence"] = None if (
                event_flow is None or candidate["market"] != "CN"
            ) else {
                "snapshot_id": event_flow["snapshot_id"],
                "symbol_summary": event_summaries.get(symbol),
                "alerts": event_alerts.get(symbol, []),
            }

        fundamental_available_count = sum(
            bool(packet["available"])
            for packet in fundamental_packets.values()
        )
        fundamental_retry_count = 0
        fundamental_recovered_count = 0
        fundamental_partial_count = sum(
            bool(packet["neutralized_factors"])
            for packet in fundamental_packets.values()
            if packet["available"]
        )
        short_history_count = sum(
            row["history_mode"] == "short" for row in analyzed
        )
        if failures:
            limitations.append("partial_kline_coverage")
        if history_exclusions:
            limitations.append("new_listing_watch_not_ranked")
        if short_history_count:
            limitations.append("short_history_scores_confidence_adjusted")
        if any(row.get("amount_source") == "latest_daily_bar_proxy" for row in candidates):
            limitations.append("liquidity_uses_latest_daily_bar_proxy")
        if fundamental_failures:
            limitations.append("partial_fundamental_coverage_neutralized")
        if fundamental_partial_count:
            limitations.append("partial_fundamental_factor_coverage_neutralized")
        if len(analyzed) > len(fundamental_pool):
            limitations.append(f"two_stage_preselection_top_{fundamental_limit}")
        if any(row["pe"] <= 0 or row["pb"] <= 0 for row in candidates):
            limitations.append("missing_or_invalid_scan_valuation")
        limitations.extend(event_limitations)
        scan_scope = str((scan.get("coverage") or {}).get("scope") or "")
        if scan_scope == "full_market_top20_plus_market_cap_pool":
            limitations.append("candidate_pool_uses_turnover_top20_then_market_cap_fill")
        elif scan_scope == "market_cap_pool_only":
            limitations.append("candidate_pool_fell_back_to_market_cap_pool")
        elif scan_scope == "desk_multi_scan_union":
            limitations.append("desk_scan_union_not_full_security_master")
        security_master = (scan.get("coverage") or {}).get("security_master") or {}
        if security_master.get("state") == "available" and not security_master.get("enumerable"):
            limitations.append("desk_security_master_summary_only")
        if market_eligible_count > len(eligible):
            limitations.append(f"deep_kline_pool_top_{len(eligible)}")
        limitations.append("latest_cross_section_only_no_historical_replay")
        data_state = "complete" if (
            not failures
            and not fundamental_failures
            and not fundamental_partial_count
            and not event_limitations
            and screening_coverage["analyzed_count"] + len(history_exclusions) == len(eligible)
        ) else "partial"
        as_of = self._as_of(scan, analyzed)
        coverage = {
            "scan_count": len(raw_items),
            "broad_eligible_count": broad_eligible_count,
            "market_prefilter_count": market_eligible_count,
            "market_prefilter_excluded_count": len(market_excluded),
            "deep_pool_count": len(eligible),
            "eligible_count": len(eligible),
            "analyzed_count": len(analyzed),
            "technical_excluded_count": sum(
                item.get("stage") == "technical_rules"
                for item in excluded_by_rules
            ),
            "fundamental_excluded_count": sum(
                item.get("stage") == "fundamental_rules"
                for item in excluded_by_rules
            ),
            "failed_count": len(failures),
            "history_excluded_count": len(history_exclusions),
            "new_listing_watch_count": len(history_exclusions),
            "short_history_count": short_history_count,
            "preselection_count": len(fundamental_pool),
            "fundamental_requested_count": len(fundamental_pool),
            "fundamental_available_count": fundamental_available_count,
            "fundamental_failed_count": len(fundamental_failures),
            "fundamental_partial_count": fundamental_partial_count,
            "fundamental_retry_count": fundamental_retry_count,
            "fundamental_recovered_count": fundamental_recovered_count,
            "fundamental_batch_count": fundamental_batch_count,
            "fundamental_snapshot_fallback_count": fundamental_fallback_count,
            **fundamental_request_stats,
            "returned_count": len(candidates),
            "scan_scope": scan_scope,
            "markets": list(markets),
            "universe_mode": universe_mode,
            "full_security_master": bool(
                (scan.get("coverage") or {}).get("full_security_master")
            ),
            "security_master": security_master,
            "scan_sort_basis": str(
                (scan.get("coverage") or {}).get("sort_basis") or "amount"
            ),
            "deep_pool_selection_basis": deep_pool_basis,
        }
        uses_liquidity_proxy = any(
            row.get("amount_source") == "latest_daily_bar_proxy"
            for row in candidates
        )
        fundamental_ratio = (
            fundamental_available_count / len(fundamental_pool)
            if fundamental_pool else 0.0
        )
        evidence_quality = {
            "positioning": "research_candidate_only",
            "calibration_state": "not_calibrated",
            "items": [
                {
                    "id": "universe",
                    "label": "证券池",
                    "state": "available" if coverage["full_security_master"] else "limited",
                    "detail": (
                        "Desk 全市场证券主表"
                        if coverage["full_security_master"]
                        else (
                            "Desk 已登记 %s 只，但当前 capability 只返回统计，未开放分页明细"
                            % security_master.get("count")
                            if security_master.get("state") == "available"
                            else "Desk 多榜合并池，不是全市场枚举"
                        )
                    ),
                },
                {
                    "id": "price_history",
                    "label": "日线覆盖",
                    "state": "available" if not failures else "partial",
                    "detail": f"深算 {len(analyzed)}/{len(eligible)} 只，短历史 {short_history_count} 只",
                },
                {
                    "id": "fundamentals",
                    "label": "财务覆盖",
                    "state": "available" if fundamental_ratio >= 0.9 else "partial",
                    "detail": f"可用 {fundamental_available_count}/{len(fundamental_pool)}",
                },
                {
                    "id": "liquidity",
                    "label": "流动性口径",
                    "state": "limited" if uses_liquidity_proxy else "available",
                    "detail": "最近完整日线成交额代理" if uses_liquidity_proxy else "Desk 实时扫描成交额",
                },
                {
                    "id": "point_in_time",
                    "label": "点时复盘",
                    "state": "unavailable",
                    "detail": "没有历史证券池与原生 asOf，禁止回填今日股票池",
                },
                {
                    "id": "calibration",
                    "label": "样本外校准",
                    "state": "unavailable",
                    "detail": "尚未完成滚动样本外检验，不输出预测胜率",
                },
            ],
        }
        summary = {
            "top_symbol": candidates[0]["symbol"],
            "top_name": candidates[0]["name"],
            "top_score": candidates[0]["score"],
            "candidate_count": len(candidates),
            "average_score": round(sum(row["score"] for row in candidates) / len(candidates), 2),
            "positive_momentum_count": sum(row["metrics"]["momentum_20_pct"] > 0 for row in candidates),
            "classic_signal_count": sum(bool(row["classic_signals"]) for row in candidates),
            "fundamental_available_count": fundamental_available_count,
            "short_history_candidate_count": sum(
                row["history_mode"] == "short" for row in candidates
            ),
            "new_listing_watch_count": len(history_exclusions),
        }
        new_listing_watchlist = [dict(item) for item in history_exclusions]
        stable_result = {
            "market": market,
            "universe_mode": universe_mode,
            "as_of": as_of,
            "data_state": data_state,
            "coverage": coverage,
            "candidates": candidates,
            "failures": failures,
            "history_exclusions": history_exclusions,
            "new_listing_watchlist": new_listing_watchlist,
            "fundamental_failures": fundamental_failures,
            "limitations": limitations,
            "summary": summary,
            "screening_model": {"profile": profile, "filters": normalized_filters},
            "screening_coverage": screening_coverage,
            "excluded_by_rules": excluded_by_rules,
            "event_flow": event_flow,
            "evidence_quality": evidence_quality,
        }
        snapshot = self._build_snapshot(
            scan, stable_result, universe_size, output_size, bars, market,
            universe_mode, profile,
            normalized_filters, event_flow_snapshot_id
        )
        warnings = [
            "财务质量、成长和最终估值优先使用 Desk 批量横向比较，缺失时回退单股快照；缺失因子按 50 分中性处理",
        ]
        if len(analyzed) > len(fundamental_pool):
            warnings.append(
                f"只对技术预评分前 {fundamental_limit} 名补财务并进入最终排名"
            )
        if history_exclusions:
            warnings.append(
                f"{len(history_exclusions)} 只股票少于 {self.minimum_rank_bars} 根日线，暂列新股观察"
            )
        if short_history_count:
            warnings.append(
                f"{short_history_count} 只股票使用短历史模型，历史敏感技术分按覆盖率向 50 分收缩"
            )
        return {
            "engine": {
                "name": self.engine_name,
                "version": self.engine_version,
                "factor_model": self.factor_model,
            },
            "factor_model": {
                "id": self.factor_model,
                "weights": dict(active_weights),
                "method": "two_stage_percentile_plus_desk_scorecard_with_overheat_penalty",
                "preselection": {
                    "limit": fundamental_limit,
                    "factors": list(self.technical_factors),
                    "weights": preselection_weights,
                },
                "fundamental_source": "research.equity-comparison + research.equity-snapshot fallback",
                "missing_policy": "neutral_50",
                "history_policy": {
                    "minimum_rank_bars": self.minimum_rank_bars,
                    "full_history_bars": self.full_history_bars,
                    "short_history_range": [
                        self.minimum_rank_bars, self.full_history_bars - 1,
                    ],
                    "confidence_formula": "min(1, history_bars / 80)",
                    "score_adjustment": "50 + confidence * (percentile_score - 50)",
                    "adjusted_factors": sorted(self.history_sensitive_factors),
                },
            },
            "market": market,
            "universe_mode": universe_mode,
            "screening_model": stable_result["screening_model"],
            "screening_coverage": screening_coverage,
            "excluded_by_rules": excluded_by_rules,
            "event_flow": event_flow,
            "evidence_quality": evidence_quality,
            "as_of": as_of,
            "data_source": str(scan.get("source") or self.provider.name),
            "data_state": data_state,
            "coverage": coverage,
            "summary": summary,
            "candidates": candidates,
            "failures": failures,
            "history_exclusions": history_exclusions,
            "new_listing_watchlist": new_listing_watchlist,
            "fundamental_failures": fundamental_failures,
            "warnings": warnings,
            "limitations": limitations,
            "calibrated_backtest": False,
            "snapshot": snapshot,
        }

    def _load_fundamentals(self, rows, *, refresh: bool = False):
        packets = {}
        errors = {}
        symbols = [row["symbol"] for row in rows]
        stats = {
            "fundamental_batch_failure_count": 0,
            "fundamental_batch_timeout_count": 0,
            "fundamental_snapshot_failure_count": 0,
            "fundamental_snapshot_timeout_count": 0,
            "fundamental_batch_worker_limit": min(
                self.max_workers, self.fundamental_batch_workers
            ),
            "fundamental_snapshot_worker_limit": min(
                self.max_workers, self.fundamental_snapshot_workers
            ),
            "fundamental_batch_timeout_seconds": self.fundamental_batch_timeout_seconds,
            "fundamental_snapshot_timeout_seconds": self.fundamental_snapshot_timeout_seconds,
        }
        if not symbols:
            return packets, errors, 0, 0, stats

        chunks = [
            symbols[offset:offset + self.fundamental_batch_size]
            for offset in range(0, len(symbols), self.fundamental_batch_size)
        ]

        def resolve_comparison(chunk):
            return chunk, self.provider.get_equity_comparison(chunk, refresh=refresh)

        batch_workers = min(
            self.max_workers,
            self.fundamental_batch_workers,
            len(chunks),
        )
        with ThreadPoolExecutor(max_workers=batch_workers) as pool:
            jobs = {pool.submit(resolve_comparison, chunk): chunk for chunk in chunks}
            for future in as_completed(jobs):
                chunk = jobs[future]
                try:
                    _, comparison = future.result()
                    generated_at = str(comparison.get("generatedAt") or "")
                    for item in comparison.get("rows") or []:
                        if not isinstance(item, Mapping):
                            continue
                        symbol = str((item.get("identity") or {}).get("symbol") or "").split(".")[0]
                        if symbol not in chunk:
                            continue
                        packet = self._normalize_comparison_fundamentals(
                            item, generated_at=generated_at
                        )
                        if packet["available"]:
                            packets[symbol] = packet
                    for item in comparison.get("errors") or []:
                        if isinstance(item, Mapping):
                            symbol = str(item.get("symbol") or "").split(".")[0]
                            if symbol:
                                errors[symbol] = str(item.get("error") or "横向比较失败")
                except (MarketDataError, TypeError, ValueError, KeyError) as exc:
                    stats["fundamental_batch_failure_count"] += 1
                    if self._is_timeout_error(exc):
                        stats["fundamental_batch_timeout_count"] += 1
                    for symbol in chunk:
                        errors.setdefault(symbol, str(exc))

        missing = [symbol for symbol in symbols if symbol not in packets]
        if not missing:
            return packets, errors, len(chunks), 0, stats

        def resolve_snapshot(future):
            packet = self._normalize_fundamentals(future.result())
            if not packet["available"]:
                raise StockCandidateError("Desk 财务快照缺少可用评分卡")
            return packet

        snapshot_workers = min(
            self.max_workers,
            self.fundamental_snapshot_workers,
            len(missing),
        )
        with ThreadPoolExecutor(max_workers=snapshot_workers) as pool:
            jobs = {
                pool.submit(
                    self.provider.get_equity_snapshot,
                    symbol,
                    refresh=refresh,
                ): symbol
                for symbol in missing
            }
            for future in as_completed(jobs):
                symbol = jobs[future]
                try:
                    packets[symbol] = resolve_snapshot(future)
                    errors.pop(symbol, None)
                except (MarketDataError, StockCandidateError, TypeError, ValueError, KeyError) as exc:
                    stats["fundamental_snapshot_failure_count"] += 1
                    if self._is_timeout_error(exc):
                        stats["fundamental_snapshot_timeout_count"] += 1
                    errors[symbol] = str(exc)
        return packets, errors, len(chunks), len(missing), stats

    @staticmethod
    def _is_timeout_error(exc: Exception) -> bool:
        message = str(exc).lower()
        return "timeout" in message or "timed out" in message or "超时" in message

    @classmethod
    def _select_deep_pool(
        cls, rows, limit: int, markets: tuple[str, ...], filters=None
    ):
        """Select the expensive K-line pool without letting one market crowd out another."""
        relevant_memberships = cls._deep_pool_selection_basis(filters)
        use_composite = relevant_memberships == ["multi_axis_composite"]

        def priority(row):
            membership_scores = row.get("scan_membership_scores") or {}
            filter_score = (
                float(row.get("scan_rank_score") or 0)
                if use_composite
                else sum(cls._number(membership_scores.get(key)) for key in relevant_memberships)
            )
            return (
                filter_score,
                float(row.get("scan_rank_score") or 0),
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
        base_quota, extra = divmod(limit, max(len(markets), 1))
        for index, market in enumerate(markets):
            quota = base_quota + (1 if index < extra else 0)
            for row in buckets[market][:quota]:
                key = (row.get("market"), row.get("symbol"))
                selected.append(row)
                selected_keys.add(key)
        if len(selected) < limit:
            remaining = sorted(rows, key=priority, reverse=True)
            for row in remaining:
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

    def _analyze_one(self, item: Mapping[str, Any], bars: int):
        symbol = str(item["symbol"])
        market = str(item.get("market") or "CN").upper()
        query_symbol = f"{symbol}.HK" if market == "HK" else symbol
        frame = self.provider.get_kline(query_symbol, period="daily", limit=bars)
        data_start = pd.Timestamp(frame["date"].iloc[0]).strftime("%Y-%m-%d")
        data_end = pd.Timestamp(frame["date"].iloc[-1]).strftime("%Y-%m-%d")
        history_source = str(
            frame.attrs.get("upstream_source") or frame.attrs.get("data_source") or ""
        )
        history_has_more = frame.attrs.get("upstream_has_more")
        if len(frame) < self.minimum_rank_bars:
            raise StockCandidateInsufficientHistory(
                len(frame),
                required_bars=self.minimum_rank_bars,
                data_start=data_start,
                data_end=data_end,
                source=history_source,
                has_more=history_has_more,
            )
        close = pd.to_numeric(frame["close"], errors="coerce").dropna()
        volume = pd.to_numeric(frame["volume"], errors="coerce").fillna(0)
        if len(close) < self.minimum_rank_bars:
            raise StockCandidateInsufficientHistory(
                len(close),
                required_bars=self.minimum_rank_bars,
                basis="valid_closes",
                data_start=data_start,
                data_end=data_end,
                source=history_source,
                has_more=history_has_more,
            )
        history_bars = len(close)
        history_mode = "full" if history_bars >= self.full_history_bars else "short"
        technical_confidence = min(1.0, history_bars / self.full_history_bars)
        if history_mode == "full":
            fast_window, slow_window = 20, 60
            momentum_short_window, momentum_long_window = 20, 60
        else:
            fast_window = min(20, max(5, history_bars // 3))
            slow_window = min(60, max(fast_window + 1, history_bars - 1))
            momentum_short_window = (
                20 if history_bars >= 21
                else max(5, (history_bars - 1) // 2)
            )
            momentum_long_window = min(60, history_bars - 1)
        returns = close.pct_change().dropna()
        ma_fast = float(close.tail(fast_window).mean())
        ma_slow = float(close.tail(slow_window).mean())
        prior_fast_end = history_bars - fast_window
        prior_fast_start = max(0, prior_fast_end - fast_window)
        prior_ma_fast = float(close.iloc[prior_fast_start:prior_fast_end].mean())
        latest = float(close.iloc[-1])
        momentum_short = latest / float(close.iloc[-momentum_short_window - 1]) - 1
        momentum_long = latest / float(close.iloc[-momentum_long_window - 1]) - 1
        volatility_window = min(60, len(returns))
        annual_vol = float(returns.tail(volatility_window).std(ddof=0) * np.sqrt(252))
        rolling_peak = close.cummax()
        drawdown_window = min(120, history_bars)
        max_drawdown = float((close / rolling_peak - 1).tail(drawdown_window).min())
        last_volume = float(volume.iloc[-1])
        previous_volume = float(volume.iloc[-6:-1].mean()) or 1.0
        latest_frame_amount = float(frame["amount"].iloc[-1]) if "amount" in frame else 0.0
        historical_amount = latest_frame_amount if latest_frame_amount > 0 else latest * last_volume * 100
        scan_amount = self._number(item.get("amount"))
        liquidity_amount = scan_amount if scan_amount > 0 else historical_amount
        daily_return = latest / float(close.iloc[-2]) - 1
        prior_high = float(close.iloc[-momentum_short_window - 1:-1].max())
        classic_signals = []
        if latest > ma_fast > ma_slow and ma_fast > prior_ma_fast:
            classic_signals.append("均线多头" if history_mode == "full" else "短期均线多头")
        if daily_return >= 0.02 and latest >= float(frame["open"].iloc[-1]) and last_volume / previous_volume >= 1.5 and historical_amount >= 2e8:
            classic_signals.append("放量上涨")
        if latest > prior_high and last_volume / previous_volume >= 1.3:
            classic_signals.append("平台突破" if history_mode == "full" else "短窗突破")
        if momentum_long > 0.10 and annual_vol < 0.35:
            classic_signals.append("低波动成长" if history_mode == "full" else "短期低波动上涨")

        pe = self._number(item.get("pe"))
        pb = self._number(item.get("pb"))
        valuation = -(math.log(pe) + 0.5 * math.log(pb)) if pe > 0 and pb > 0 else math.nan
        trend = (latest / ma_fast - 1) * 0.45 + (ma_fast / ma_slow - 1) * 0.35 + (ma_fast / prior_ma_fast - 1) * 0.20
        momentum = momentum_short * 0.60 + momentum_long * 0.40
        liquidity = math.log1p(max(liquidity_amount, 0)) + min(self._number(item.get("turnover_pct")), 15) * 0.04 + min(self._number(item.get("volume_ratio")), 3) * 0.08
        stability = -(annual_vol + abs(max_drawdown) * 0.7)
        return {
            "symbol": symbol,
            "market": market,
            "name": str(item.get("name") or symbol),
            "industry": str(item.get("industry") or "未分类"),
            "price": round(self._number(item.get("price")), 3),
            "change_pct": round(self._number(item.get("change_pct")), 3),
            "amount": round(liquidity_amount, 2),
            "amount_source": "scan_realtime" if scan_amount > 0 else "latest_daily_bar_proxy",
            "turnover_pct": round(self._number(item.get("turnover_pct")), 3),
            "volume_ratio": round(self._number(item.get("volume_ratio")), 3),
            "market_cap": round(self._number(item.get("market_cap")), 2),
            "pe": round(pe, 3),
            "pb": round(pb, 3),
            "history_bars": history_bars,
            "history_mode": history_mode,
            "technical_confidence": round(technical_confidence, 4),
            "data_start": data_start,
            "history_source": history_source,
            "history_has_more": history_has_more,
            "raw_factors": {
                "trend": trend,
                "momentum": momentum,
                "liquidity": liquidity,
                "stability": stability,
                "valuation": valuation,
                "classic": len(classic_signals) / 4,
            },
            "metrics": {
                "momentum_20_pct": round(momentum_short * 100, 2),
                "momentum_20_window": momentum_short_window,
                "momentum_60_pct": round(momentum_long * 100, 2),
                "momentum_60_window": momentum_long_window,
                "annualized_volatility_pct": round(annual_vol * 100, 2),
                "volatility_window": volatility_window,
                "max_drawdown_pct": round(max_drawdown * 100, 2),
                "drawdown_window": drawdown_window,
                "close_vs_ma20_pct": round((latest / ma_fast - 1) * 100, 2),
                "ma20_window": fast_window,
                "ma20_vs_ma60_pct": round((ma_fast / ma_slow - 1) * 100, 2),
                "ma60_window": slow_window,
            },
            "classic_signals": classic_signals,
            "data_end": data_end,
            "_market_screening_evidence": item.get("_market_screening_evidence"),
        }

    @classmethod
    def _normalize_fundamentals(cls, payload: Mapping[str, Any]):
        if not isinstance(payload, Mapping):
            raise TypeError("Desk 财务快照格式无效")

        raw_scorecard = payload.get("scorecard") or []
        entries = []
        if isinstance(raw_scorecard, Mapping):
            for factor, value in raw_scorecard.items():
                if isinstance(value, Mapping):
                    entries.append({"id": factor, **dict(value)})
                else:
                    entries.append({"id": factor, "score": value})
        elif isinstance(raw_scorecard, list):
            entries = [dict(item) for item in raw_scorecard if isinstance(item, Mapping)]

        score_map = {}
        normalized_scorecard = []
        for item in entries:
            factor = str(item.get("id") or item.get("key") or "").strip().lower()
            if not factor:
                continue
            score = cls._optional_score(item.get("score"))
            normalized_scorecard.append({
                "id": factor,
                "title": str(item.get("title") or factor),
                "score": score,
                "status": str(item.get("status") or ""),
                "summary": str(item.get("summary") or ""),
            })
            if score is not None:
                score_map[factor] = score

        expected_factors = ("valuation", "quality", "growth")
        scores = {
            factor: score_map.get(factor, 50.0)
            for factor in expected_factors
        }
        profile = payload.get("comparisonProfile") or {}
        raw_metrics = profile.get("metrics") if isinstance(profile, Mapping) else {}
        raw_metrics = raw_metrics if isinstance(raw_metrics, Mapping) else {}
        metric_keys = (
            "revenueGrowthPct", "netProfitGrowthPct", "roePct",
            "grossMarginPct", "netMarginPct", "cashConversionPct",
            "valuationPercentile", "pe", "pb",
        )
        metrics = {
            key: raw_metrics.get(key)
            for key in metric_keys
            if key in raw_metrics
        }
        workflow = payload.get("workflow") or {}
        raw_quality = workflow.get("dataQuality") if isinstance(workflow, Mapping) else {}
        raw_quality = raw_quality if isinstance(raw_quality, Mapping) else {}
        coverage = payload.get("coverage") or {}
        gaps = payload.get("gaps") or []
        neutralized_factors = [
            factor for factor in expected_factors if factor not in score_map
        ]
        return {
            "available": any(factor in score_map for factor in expected_factors),
            "source": "research.equity-snapshot",
            "schema_version": str(payload.get("schemaVersion") or ""),
            "generated_at": str(payload.get("generatedAt") or ""),
            "scores": scores,
            "scorecard": normalized_scorecard,
            "metrics": metrics,
            "data_quality": {
                "score": cls._optional_score(raw_quality.get("score")),
                "level": str(raw_quality.get("level") or ""),
                "limitations": [str(item) for item in raw_quality.get("limitations") or []],
            },
            "coverage": dict(coverage) if isinstance(coverage, Mapping) else {},
            "gaps": [str(item) for item in gaps] if isinstance(gaps, list) else [],
            "neutralized_factors": neutralized_factors,
            "error": None,
        }

    @classmethod
    def _normalize_comparison_fundamentals(
        cls,
        payload: Mapping[str, Any],
        *,
        generated_at: str = "",
    ):
        raw_scores = payload.get("scores") or {}
        raw_scores = raw_scores if isinstance(raw_scores, Mapping) else {}
        scorecard = [
            {
                "id": factor,
                "title": factor,
                "score": raw_scores.get(factor),
                "status": "",
                "summary": "",
            }
            for factor in ("valuation", "quality", "growth")
            if cls._optional_score(raw_scores.get(factor)) is not None
        ]
        normalized = cls._normalize_fundamentals({
            "schemaVersion": "newma-dock.equity-comparison.v1",
            "identity": dict(payload.get("identity") or {}),
            "coverage": dict(payload.get("coverage") or {}),
            "scorecard": scorecard,
            "comparisonProfile": {"metrics": dict(payload.get("metrics") or {})},
            "workflow": {"dataQuality": {
                "score": None,
                "level": "comparison_compact",
                "limitations": ["compact_comparison_omits_evidence_ledger"],
            }},
            "gaps": [],
            "generatedAt": generated_at,
        })
        normalized["source"] = "research.equity-comparison"
        return normalized

    @staticmethod
    def _neutral_fundamentals(error: str):
        return {
            "available": False,
            "source": "research.equity-snapshot",
            "schema_version": "",
            "generated_at": "",
            "scores": {"valuation": 50.0, "quality": 50.0, "growth": 50.0},
            "scorecard": [],
            "metrics": {},
            "data_quality": {"score": None, "level": "unavailable", "limitations": []},
            "coverage": {},
            "gaps": ["Desk 财务快照不可用，估值、质量与成长按中性分处理"],
            "neutralized_factors": ["valuation", "quality", "growth"],
            "error": str(error),
        }

    @staticmethod
    def _optional_score(value):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(number):
            return None
        return round(max(0.0, min(100.0, number)), 2)

    def _risk_penalty(self, row):
        penalty = 0.0
        risks = []
        if row["change_pct"] >= 9:
            penalty += 10
            risks.append("单日涨幅接近涨停，短线过热")
        if row["turnover_pct"] >= 20:
            penalty += 6
            risks.append("换手率超过 20%，筹码快速交换")
        if row["volume_ratio"] >= 3:
            penalty += 5
            risks.append("量比超过 3，成交脉冲过热")
        if row["pe"] > 120 or row["pb"] > 15:
            penalty += 4
            risks.append("静态估值处于高风险区")
        if row["metrics"]["annualized_volatility_pct"] > 65:
            penalty += 5
            risks.append("历史波动率偏高")
        if row.get("history_mode") == "short":
            risks.append(
                f"仅有 {row['history_bars']} 根日线，技术置信度 "
                f"{row['technical_confidence'] * 100:.0f}%"
            )
        if not risks:
            risks.append("未触发硬性过热惩罚，仍需结合公告与基本面复核")
        return penalty, risks

    def _build_snapshot(
        self, scan, stable_result, universe_size, output_size, bars, market,
        universe_mode, profile, filters, event_flow_snapshot_id,
    ):
        input_summary = {
            "source": scan.get("source"),
            "as_of": scan.get("as_of"),
            "items": scan.get("items"),
            "universe_size": universe_size,
            "output_size": output_size,
            "bars": bars,
            "market": market,
            "universe_mode": universe_mode,
            "profile": profile,
            "filters": filters,
            "event_flow_snapshot_id": event_flow_snapshot_id,
        }
        input_digest = self._digest(input_summary)
        result_digest = self._digest(stable_result)
        material = {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "analysis": {"name": self.engine_name, "version": self.engine_version},
            "input_digest": input_digest,
            "result_digest": result_digest,
        }
        snapshot_hash = self._digest(material).split(":", 1)[1]
        as_of = stable_result["as_of"]
        lag_days = max((date.today() - pd.Timestamp(as_of).date()).days, 0)
        return {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "snapshot_id": f"{self.engine_name}:{snapshot_hash[:24]}",
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "analysis": {"name": self.engine_name, "version": self.engine_version},
            "parameters": {
                "universeSize": universe_size,
                "outputSize": output_size,
                "bars": bars,
                "market": market,
                "universeMode": universe_mode,
                "profile": profile,
                "filters": filters,
                "eventFlowSnapshotId": event_flow_snapshot_id,
            },
            "data_window": {"requested_as_of": None, "start_date": None, "end_date": as_of, "coverage": stable_result["data_state"]},
            "provenance": {
                "provider": self.provider.name,
                "endpoint": "market.scan + market.quotes + market.ohlcv + research.equity-comparison + research.equity-snapshot fallback",
                "upstream_source": str(scan.get("source") or ""),
                "upstream_as_of": str(scan.get("as_of") or ""),
                "limitations": list(stable_result["limitations"]),
            },
            "freshness": {"state": "fresh" if lag_days <= 3 else "delayed", "resolution": "latest_cross_section", "calendar_lag_days": lag_days},
            "input": {"digest": input_digest, "summary": {
                "scan_count": stable_result["coverage"]["scan_count"],
                "analyzed_count": stable_result["coverage"]["analyzed_count"],
                "fundamental_requested_count": stable_result["coverage"]["fundamental_requested_count"],
                "fundamental_available_count": stable_result["coverage"]["fundamental_available_count"],
            }},
            "result": {"digest": result_digest, "summary": dict(stable_result["summary"])},
        }

    @classmethod
    def _normalize_filters(cls, filters):
        source = dict(filters or {})

        def string_list(key):
            value = source.get(key) or []
            if isinstance(value, str):
                value = value.split(",")
            return [str(item).strip() for item in value if str(item).strip()]

        def optional_number(key):
            value = source.get(key)
            if value in (None, ""):
                return None
            number = cls._number(value)
            if number < 0:
                raise StockCandidateError(f"筛选参数 {key} 不能为负数")
            return number

        normalized = {
            "industries": string_list("industries"),
            "min_amount": optional_number("min_amount"),
            "min_market_cap": optional_number("min_market_cap"),
            "max_market_cap": optional_number("max_market_cap"),
            "max_pe": optional_number("max_pe"),
            "max_pb": optional_number("max_pb"),
            "min_turnover_pct": optional_number("min_turnover_pct"),
            "max_turnover_pct": optional_number("max_turnover_pct"),
            "min_volume_ratio": optional_number("min_volume_ratio"),
            "max_volume_ratio": optional_number("max_volume_ratio"),
            "min_momentum_20_pct": optional_number("min_momentum_20_pct"),
            "max_volatility_pct": optional_number("max_volatility_pct"),
            "min_roe_pct": optional_number("min_roe_pct"),
            "min_revenue_growth_pct": optional_number("min_revenue_growth_pct"),
            "min_net_profit_growth_pct": optional_number("min_net_profit_growth_pct"),
            "max_valuation_percentile": optional_number("max_valuation_percentile"),
            "required_signals": string_list("required_signals"),
        }
        ranges = (
            ("min_market_cap", "max_market_cap", "最低市值不能高于最高市值"),
            ("min_turnover_pct", "max_turnover_pct", "最低换手率不能高于最高换手率"),
            ("min_volume_ratio", "max_volume_ratio", "最低量比不能高于最高量比"),
        )
        for minimum_key, maximum_key, message in ranges:
            minimum = normalized[minimum_key]
            maximum = normalized[maximum_key]
            if minimum is not None and maximum is not None and minimum > maximum:
                raise StockCandidateError(message)
        valuation_percentile = normalized["max_valuation_percentile"]
        if valuation_percentile is not None and valuation_percentile > 100:
            raise StockCandidateError("最高估值分位不能超过 100")
        return normalized

    @staticmethod
    def _market_screening_evidence(row, filters):
        reasons = []
        rules = []

        def check(rule, passed, actual, expected):
            rules.append({
                "rule": rule,
                "passed": bool(passed),
                "actual": actual,
                "expected": expected,
            })
            if not passed:
                reasons.append(rule)

        if filters["industries"]:
            check(
                "industry_not_selected",
                row["industry"] in filters["industries"],
                row["industry"],
                filters["industries"],
            )
        if filters["min_amount"] is not None:
            check("amount_below_min", row["amount"] >= filters["min_amount"], row["amount"], filters["min_amount"])
        if filters["min_market_cap"] is not None:
            check(
                "market_cap_below_min",
                row["market_cap"] >= filters["min_market_cap"],
                row["market_cap"],
                filters["min_market_cap"],
            )
        if filters["max_market_cap"] is not None:
            if row["market_cap"] <= 0:
                check("missing_market_cap", False, row["market_cap"], filters["max_market_cap"])
            else:
                check(
                    "market_cap_above_max",
                    row["market_cap"] <= filters["max_market_cap"],
                    row["market_cap"],
                    filters["max_market_cap"],
                )
        if filters["max_pe"] is not None:
            if row["pe"] <= 0:
                check("missing_pe", False, row["pe"], filters["max_pe"])
            else:
                check("pe_above_max", row["pe"] <= filters["max_pe"], row["pe"], filters["max_pe"])
        if filters["max_pb"] is not None:
            if row["pb"] <= 0:
                check("missing_pb", False, row["pb"], filters["max_pb"])
            else:
                check("pb_above_max", row["pb"] <= filters["max_pb"], row["pb"], filters["max_pb"])
        if filters["min_turnover_pct"] is not None:
            check(
                "turnover_below_min",
                row["turnover_pct"] >= filters["min_turnover_pct"],
                row["turnover_pct"],
                filters["min_turnover_pct"],
            )
        if filters["max_turnover_pct"] is not None:
            check(
                "turnover_above_max",
                row["turnover_pct"] <= filters["max_turnover_pct"],
                row["turnover_pct"],
                filters["max_turnover_pct"],
            )
        if filters["min_volume_ratio"] is not None:
            check(
                "volume_ratio_below_min",
                row["volume_ratio"] >= filters["min_volume_ratio"],
                row["volume_ratio"],
                filters["min_volume_ratio"],
            )
        if filters["max_volume_ratio"] is not None:
            check(
                "volume_ratio_above_max",
                row["volume_ratio"] <= filters["max_volume_ratio"],
                row["volume_ratio"],
                filters["max_volume_ratio"],
            )
        return {"passed": not reasons, "rules": rules, "reasons": reasons}

    @staticmethod
    def _technical_screening_evidence(row, filters):
        reasons = []
        rules = []

        def check(rule, passed, actual, expected):
            rules.append({
                "rule": rule,
                "passed": bool(passed),
                "actual": actual,
                "expected": expected,
            })
            if not passed:
                reasons.append(rule)

        if filters["min_momentum_20_pct"] is not None:
            actual = row["metrics"]["momentum_20_pct"]
            actual_window = row["metrics"].get("momentum_20_window", 20)
            if actual_window < 20:
                check(
                    "momentum_20_history_unavailable", False,
                    {"value": actual, "window": actual_window}, 20,
                )
            else:
                check("momentum_20_below_min", actual >= filters["min_momentum_20_pct"], actual, filters["min_momentum_20_pct"])
        if filters["max_volatility_pct"] is not None:
            actual = row["metrics"]["annualized_volatility_pct"]
            check("volatility_above_max", actual <= filters["max_volatility_pct"], actual, filters["max_volatility_pct"])
        if filters["required_signals"]:
            missing = [signal for signal in filters["required_signals"] if signal not in row["classic_signals"]]
            check("required_signal_missing", not missing, row["classic_signals"], filters["required_signals"])
        return {"passed": not reasons, "rules": rules, "reasons": reasons}

    @classmethod
    def _fundamental_screening_evidence(cls, fundamentals, filters):
        reasons = []
        rules = []
        metrics = fundamentals.get("metrics") or {}

        def check_metric(filter_key, metric_key, missing_reason, failed_reason, comparator):
            expected = filters[filter_key]
            if expected is None:
                return
            actual = cls._optional_metric(metrics.get(metric_key))
            passed = actual is not None and comparator(actual, expected)
            reason = failed_reason if actual is not None else missing_reason
            rules.append({
                "rule": reason,
                "passed": passed,
                "actual": actual,
                "expected": expected,
                "source": fundamentals.get("source") or "research.equity-snapshot",
            })
            if not passed:
                reasons.append(reason)

        check_metric("min_roe_pct", "roePct", "missing_roe", "roe_below_min", lambda actual, expected: actual >= expected)
        check_metric(
            "min_revenue_growth_pct", "revenueGrowthPct",
            "missing_revenue_growth", "revenue_growth_below_min",
            lambda actual, expected: actual >= expected,
        )
        check_metric(
            "min_net_profit_growth_pct", "netProfitGrowthPct",
            "missing_net_profit_growth", "net_profit_growth_below_min",
            lambda actual, expected: actual >= expected,
        )
        check_metric(
            "max_valuation_percentile", "valuationPercentile",
            "missing_valuation_percentile", "valuation_percentile_above_max",
            lambda actual, expected: actual <= expected,
        )
        return {"passed": not reasons, "rules": rules, "reasons": reasons}

    @staticmethod
    def _merge_screening_evidence(*items):
        rules = [rule for item in items for rule in item.get("rules") or []]
        reasons = [reason for item in items for reason in item.get("reasons") or []]
        return {"passed": not reasons, "rules": rules, "reasons": reasons}

    @staticmethod
    def _optional_metric(value):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    @staticmethod
    def _number(value):
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0
        return number if math.isfinite(number) else 0.0

    @staticmethod
    def _digest(value):
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return f"sha256:{hashlib.sha256(encoded).hexdigest()}"

    @staticmethod
    def _as_of(scan, analyzed):
        raw = str(scan.get("as_of") or "")
        if raw:
            try:
                return pd.Timestamp(raw).strftime("%Y-%m-%d")
            except ValueError:
                pass
        return max(row["data_end"] for row in analyzed)
