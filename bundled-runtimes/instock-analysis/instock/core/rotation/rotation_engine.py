#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Cross-sectional industry and ETF rotation scoring.

The engine deliberately contains no database or web-framework dependencies.
It only consumes the small :class:`MarketDataProvider` contract and produces a
stable JSON-friendly payload for APIs, browser UI, tests, and later schedulers.
"""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from instock.core.analysis_snapshot import build_analysis_snapshot, normalize_as_of
from instock.core.industry_taxonomy import resolve_sw_l1_industry
from instock.core.market_data_provider import MarketDataError, MarketDataProvider
from instock.core.rotation.etf_universe import DEFAULT_SECTOR_ETFS, SectorETF


ROTATION_WEIGHT_PROFILES: Dict[str, Dict[str, float]] = {
    "balanced": {
        "momentum": 0.26,
        "relative_strength": 0.22,
        "trend": 0.17,
        "volume_continuity": 0.13,
        "crowding_reversal": 0.13,
        "valuation": 0.045,
        "fundamental_quality": 0.045,
    },
    "momentum": {
        "momentum": 0.34,
        "relative_strength": 0.25,
        "trend": 0.14,
        "volume_continuity": 0.10,
        "crowding_reversal": 0.08,
        "valuation": 0.045,
        "fundamental_quality": 0.045,
    },
    "defensive": {
        "momentum": 0.18,
        "relative_strength": 0.18,
        "trend": 0.23,
        "volume_continuity": 0.13,
        "crowding_reversal": 0.19,
        "valuation": 0.045,
        "fundamental_quality": 0.045,
    },
}


def _safe_return(series: pd.Series, periods: int) -> float:
    usable = min(max(int(periods), 1), len(series) - 1)
    if usable <= 0:
        return 0.0
    start = float(series.iloc[-usable - 1])
    end = float(series.iloc[-1])
    return end / start - 1 if start else 0.0


def _max_drawdown(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    running_max = series.cummax().replace(0, np.nan)
    drawdown = series / running_max - 1
    return abs(float(drawdown.min())) if not drawdown.empty else 0.0


def _rank_score(series: pd.Series, *, higher_is_better: bool = True) -> pd.Series:
    clean = series.replace([np.inf, -np.inf], np.nan)
    if clean.notna().sum() <= 1:
        return pd.Series(50.0, index=series.index)
    ranked = clean.rank(method="average", pct=True, ascending=higher_is_better) * 100
    # pandas ascending=True gives the largest value the highest percentile.
    return ranked.fillna(50.0)


def _round(value: Any, digits: int = 2) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return round(number, digits) if math.isfinite(number) else 0.0


def _optional_number(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return number if math.isfinite(number) else float("nan")


class RotationEngine:
    """Build a reproducible rotation snapshot from daily ETF bars."""

    engine_name = "instock-rotation"
    engine_version = "2.1.1"
    max_stale_sessions = 2
    slow_factor_min_coverage = 0.75
    shadow_strategy_id = "rotation-stateful-ensemble-v1"
    shadow_rebalance_days = 10
    shadow_hold_rank_limit = 3
    shadow_switch_score_gap = 5.0
    factor_keys = (
        "momentum",
        "relative_strength",
        "trend",
        "volume_continuity",
        "crowding_reversal",
        "valuation",
        "fundamental_quality",
    )
    slow_factor_keys = ("valuation", "fundamental_quality")
    weights = ROTATION_WEIGHT_PROFILES["balanced"]

    def __init__(
        self,
        provider: MarketDataProvider,
        universe: Sequence[SectorETF] = DEFAULT_SECTOR_ETFS,
        max_workers: int = 8,
        weights: Optional[Mapping[str, float]] = None,
    ):
        self.provider = provider
        self.universe = tuple(universe)
        self.max_workers = max(1, min(int(max_workers), 16))
        resolved_weights = dict(type(self).weights if weights is None else weights)
        required_weights = set(type(self).weights)
        if set(resolved_weights) != required_weights:
            raise ValueError(f"轮动权重必须包含: {', '.join(sorted(required_weights))}")
        if any(not math.isfinite(float(value)) or float(value) < 0 for value in resolved_weights.values()):
            raise ValueError("轮动权重必须是非负有限数")
        self.weights = {key: float(value) for key, value in resolved_weights.items()}

    def _get_kline(
        self,
        symbol: str,
        period: str,
        limit: int,
        as_of: Optional[str],
    ) -> pd.DataFrame:
        """Keep latest-data compatibility with providers implementing the old interface."""

        if as_of:
            return self.provider.get_kline(symbol, period, limit, as_of)
        return self.provider.get_kline(symbol, period, limit)

    def _get_signal_kline(
        self,
        symbol: str,
        period: str,
        limit: int,
        as_of: Optional[str],
    ) -> pd.DataFrame:
        if as_of:
            return self.provider.get_signal_kline(symbol, period, limit, as_of)
        return self.provider.get_signal_kline(symbol, period, limit)

    def analyze(
        self,
        window: int = 60,
        benchmark: str = "510300",
        as_of: Optional[str] = None,
        fund_flow_history: Optional[Sequence[Mapping[str, Any]]] = None,
        slow_factors: Optional[Mapping[str, Any]] = None,
        shadow_state: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        if window not in {40, 60, 120}:
            raise ValueError("分析窗口仅支持 40、60、120 个交易日")
        normalized_as_of = normalize_as_of(as_of)

        # Keep enough leading bars to replay the last 20 ranking dates without
        # introducing extra network requests or look-ahead data.
        request_limit = min(240, max(window + 45, 165))
        warnings: List[str] = []
        failures: List[Dict[str, str]] = []
        industry_snapshot: Dict[str, Any] = {"top": [], "bottom": [], "total": 0}
        market_overview: Dict[str, Any] = {"sentiment": {}, "sectors": [], "updated": ""}
        resolved_slow_factors = slow_factors
        if resolved_slow_factors is None:
            try:
                resolved_slow_factors = self.provider.get_rotation_slow_factors(
                    [
                        {"code": item.code, "name": item.name, "industry": item.industry}
                        for item in self.universe
                    ],
                    as_of=normalized_as_of,
                )
            except Exception as exc:  # optional Desk capability
                resolved_slow_factors = None
                warnings.append(f"行业估值与基本面点时因子暂不可用：{exc}")

        if normalized_as_of:
            warnings.append("历史截面不复用当前行业广度，行业宽度仅作当日确认")
            if resolved_slow_factors and resolved_slow_factors.get("items"):
                warnings.append("历史截面仅接受不晚于截止日的点时慢因子证据")
        else:
            try:
                market_overview = self.provider.get_market_overview()
            except Exception:
                # Aggregate breadth is context evidence only.  Its absence
                # must not change the ETF ranking or make an otherwise valid
                # analysis fail.
                market_overview = {"sentiment": {}, "sectors": [], "updated": ""}
            try:
                industry_snapshot = self.provider.get_industry_ranking(top=50)
                if not industry_snapshot.get("top") and not industry_snapshot.get("bottom"):
                    warnings.append("行业广度暂不可用，不影响七因子价格排名")
            except Exception as exc:  # industry data is an optional contribution
                warnings.append(f"行业广度暂不可用，不影响七因子价格排名：{exc}")

        try:
            benchmark_frame = self._get_kline(
                benchmark, "daily", request_limit, normalized_as_of
            )
        except Exception as exc:
            raise MarketDataError(f"基准 {benchmark} 行情不可用: {exc}") from exc

        trade_frames: Dict[str, pd.DataFrame] = {}
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(self.universe))) as pool:
            future_map = {
                pool.submit(
                    self._get_kline,
                    item.code,
                    "daily",
                    request_limit,
                    normalized_as_of,
                ): item
                for item in self.universe
            }
            for future in as_completed(future_map):
                item = future_map[future]
                try:
                    frame = future.result()
                    if len(frame) < 25:
                        raise MarketDataError(f"有效 K 线不足 25 根（实际 {len(frame)}）")
                    trade_frames[item.code] = frame
                except Exception as exc:  # noqa: BLE001
                    failures.append({"code": item.code, "name": item.name, "error": str(exc)})

        if not trade_frames:
            raise MarketDataError("ETF 候选池没有可用于轮动分析的行情")

        benchmark_as_of = pd.Timestamp(benchmark_frame["date"].iloc[-1])
        benchmark_dates = benchmark_frame["date"]
        aligned_frames: Dict[str, pd.DataFrame] = {}
        for item in self.universe:
            source = trade_frames.get(item.code)
            if source is None:
                continue
            frame = source[source["date"] <= benchmark_as_of].copy()
            if frame.empty:
                failures.append({
                    "code": item.code,
                    "name": item.name,
                    "error": f"基准截面 {benchmark_as_of:%Y-%m-%d} 前没有有效行情",
                })
                continue
            lag_sessions = self._session_lag(benchmark_dates, frame["date"].iloc[-1])
            if lag_sessions > self.max_stale_sessions:
                failures.append({
                    "code": item.code,
                    "name": item.name,
                    "error": f"行情滞后 {lag_sessions} 个交易日，超过允许的 {self.max_stale_sessions} 日",
                })
                continue
            frame.attrs.update(source.attrs)
            frame.attrs["data_lag_sessions"] = lag_sessions
            aligned_frames[item.code] = frame
        trade_frames = aligned_frames
        if not trade_frames:
            raise MarketDataError("ETF 候选池在基准最新交易日没有可用于轮动分析的行情")

        signal_frames: Dict[str, pd.DataFrame] = {}
        signal_modes: Dict[str, str] = {}
        signal_failures: List[Dict[str, str]] = []
        signal_candidates = [
            item for item in self.universe
            if (
                item.code in trade_frames
                and item.has_industry_index_signal
                and self.provider.supports_signal_kline(item.resolved_signal_code)
            )
        ]
        configured_signal_proxy_codes = {
            item.code
            for item in self.universe
            if (
                item.code in trade_frames
                and item.has_industry_index_signal
                and not self.provider.supports_signal_kline(item.resolved_signal_code)
            )
        }
        loaded_signals: Dict[str, pd.DataFrame] = {}
        if signal_candidates:
            with ThreadPoolExecutor(max_workers=min(self.max_workers, len(signal_candidates))) as pool:
                future_map = {
                    pool.submit(
                        self._get_signal_kline,
                        item.resolved_signal_code,
                        "daily",
                        request_limit,
                        normalized_as_of,
                    ): item
                    for item in signal_candidates
                }
                for future in as_completed(future_map):
                    item = future_map[future]
                    try:
                        frame = future.result()
                        if len(frame) < 25:
                            raise MarketDataError(f"有效指数 K 线不足 25 根（实际 {len(frame)}）")
                        loaded_signals[item.code] = frame
                    except Exception as exc:  # noqa: BLE001
                        signal_failures.append({
                            "etf_code": item.code,
                            "signal_code": item.resolved_signal_code,
                            "signal_name": item.resolved_signal_name,
                            "error": str(exc),
                        })

        failed_signal_codes = {row["etf_code"] for row in signal_failures}
        for item in self.universe:
            trade_frame = trade_frames.get(item.code)
            if trade_frame is None:
                continue
            if not item.has_industry_index_signal:
                signal_frame = trade_frame.copy()
                signal_mode = "trade_asset"
            else:
                signal_frame = loaded_signals.get(item.code)
                signal_mode = "industry_index"
                if signal_frame is not None:
                    signal_frame = signal_frame[signal_frame["date"] <= benchmark_as_of].copy()
                    if signal_frame.empty:
                        signal_error = f"基准截面 {benchmark_as_of:%Y-%m-%d} 前没有有效指数行情"
                    else:
                        signal_lag = self._session_lag(
                            benchmark_dates, signal_frame["date"].iloc[-1]
                        )
                        signal_error = (
                            f"指数行情滞后 {signal_lag} 个交易日，超过允许的 {self.max_stale_sessions} 日"
                            if signal_lag > self.max_stale_sessions else ""
                        )
                    if signal_error:
                        if item.code not in failed_signal_codes:
                            signal_failures.append({
                                "etf_code": item.code,
                                "signal_code": item.resolved_signal_code,
                                "signal_name": item.resolved_signal_name,
                                "error": signal_error,
                            })
                        signal_frame = None
                if signal_frame is None:
                    signal_frame = trade_frame.copy()
                    signal_mode = "etf_fallback"

            signal_lag = self._session_lag(
                benchmark_dates, signal_frame["date"].iloc[-1]
            )
            signal_frame.attrs["signal_lag_sessions"] = signal_lag
            signal_frame.attrs["rotation_signal_mode"] = signal_mode
            signal_frame.attrs["rotation_signal_code"] = (
                item.resolved_signal_code if signal_mode == "industry_index" else item.code
            )
            signal_frame.attrs["rotation_signal_name"] = (
                item.resolved_signal_name if signal_mode == "industry_index" else item.name
            )
            signal_frames[item.code] = signal_frame
            signal_modes[item.code] = signal_mode

        benchmark_metrics = self._benchmark_metrics(benchmark_frame, window)
        industry_rows = self._industry_rows(industry_snapshot)
        raw_rows = [
            self._raw_metrics(
                item,
                signal_frames[item.code],
                benchmark_metrics,
                window,
                industry_rows,
                trade_frame=trade_frames[item.code],
                signal_mode=signal_modes[item.code],
                slow_factors=resolved_slow_factors,
            )
            for item in self.universe
            if item.code in trade_frames
        ]
        factor_frame = self._factor_frame(raw_rows)
        factor_model = self._factor_model(factor_frame)
        factor_model["slow_factor_source"] = str(
            (resolved_slow_factors.get("source") or "")
            if isinstance(resolved_slow_factors, Mapping) else ""
        )
        factor_model["slow_factor_as_of"] = str(
            (resolved_slow_factors.get("as_of") or "")
            if isinstance(resolved_slow_factors, Mapping) else ""
        )
        scored = self._score_factor_frame(factor_frame, factor_model=factor_model)
        parameter_consensus = self._parameter_consensus(
            trade_frames=trade_frames,
            signal_frames=signal_frames,
            benchmark_frame=benchmark_frame,
            industry_rows=industry_rows,
            slow_factors=resolved_slow_factors,
            shadow_state=shadow_state,
            shadow_enabled=not bool(normalized_as_of),
        )
        consensus_votes = {
            str(row["code"]): int(row["votes"])
            for row in parameter_consensus.get("ranking") or ()
        }
        model_count = int(parameter_consensus.get("model_count") or 0)
        consensus_code = str(
            (parameter_consensus.get("winner") or {}).get("code") or ""
        )
        shadow_state_payload = parameter_consensus.get("shadow_state") or {}
        shadow_votes = {
            str(row["code"]): int(row["votes"])
            for row in shadow_state_payload.get("ranking") or ()
        }
        shadow_model_count = int(shadow_state_payload.get("model_count") or 0)
        shadow_code = str(
            (shadow_state_payload.get("winner") or {}).get("code") or ""
        )
        for row in scored:
            vote_count = consensus_votes.get(str(row["code"]), 0)
            row["parameter_vote_count"] = vote_count
            row["parameter_vote_share_pct"] = _round(
                vote_count / model_count * 100 if model_count else 0.0
            )
            row["parameter_consensus_winner"] = str(row["code"]) == consensus_code
            row["parameter_consensus_label"] = (
                parameter_consensus.get("signal", "参数分歧")
                if row["parameter_consensus_winner"] else "--"
            )
            row["predictive_signal"] = (
                "观察" if row["parameter_consensus_winner"] else "--"
            )
            shadow_vote_count = shadow_votes.get(str(row["code"]), 0)
            row["shadow_vote_count"] = shadow_vote_count
            row["shadow_vote_share_pct"] = _round(
                shadow_vote_count / shadow_model_count * 100
                if shadow_model_count else 0.0
            )
            row["shadow_consensus_winner"] = str(row["code"]) == shadow_code
        inactive_slow_factors = factor_model["inactive_slow_factors"]
        if inactive_slow_factors:
            labels = {
                "valuation": "估值分位",
                "fundamental_quality": "基本面质量",
            }
            factor_model["note"] = (
                "、".join(labels[key] for key in inactive_slow_factors)
                + "缺少足够点时覆盖，当前不参与排名；有效权重已在量价因子间归一化"
            )
        else:
            factor_model["note"] = "七因子均达到点时覆盖门槛"
        self._attach_sector_fund_flow(scored, market_overview)
        resolved_as_of = str(benchmark_metrics["date"])
        self._attach_sector_fund_flow_persistence(
            scored,
            fund_flow_history or (),
            resolved_as_of=resolved_as_of,
            historical=bool(normalized_as_of),
        )
        history = self._build_history(
            trade_frames,
            signal_frames,
            benchmark_frame,
            window,
            history_days=20,
        )

        if failures:
            warnings.append(f"{len(failures)} 个 ETF 行情失败，已用其余 {len(scored)} 个候选完成排名")
        if len(scored) < min(8, len(self.universe)):
            warnings.append("有效 ETF 少于 8 个，横截面排名稳定性下降")
        index_signal_count = sum(row["signal_mode"] == "industry_index" for row in scored)
        signal_fallback_count = sum(row["signal_mode"] == "etf_fallback" for row in scored)
        effective_signal_count = sum(
            row["signal_mode"] in {"industry_index", "etf_fallback", "trade_asset"}
            for row in scored
        )
        effective_signal_coverage_pct = _round(
            effective_signal_count / max(len(scored), 1) * 100, 1
        )
        signal_adjust_values = {
            str(row.get("signal_adjust") or "unknown") for row in scored
        }
        signal_adjust = (
            next(iter(signal_adjust_values))
            if len(signal_adjust_values) == 1 else "mixed"
        )
        if signal_fallback_count:
            runtime_fallback_count = signal_fallback_count - len(configured_signal_proxy_codes)
            if runtime_fallback_count > 0:
                warnings.append(
                    f"{runtime_fallback_count} 个行业指数请求失败，已使用对应行业 ETF 作为价格信号代理"
                )
        if (signal_candidates or configured_signal_proxy_codes) and index_signal_count == 0:
            signal_state = "fallback"
        elif signal_fallback_count:
            signal_state = "partial"
        else:
            signal_state = "complete"
        stale_count = sum(int(row["data_lag_sessions"]) > 0 for row in scored)
        if stale_count:
            warnings.append(f"{stale_count} 个 ETF 行情较基准滞后不超过 {self.max_stale_sessions} 个交易日，已明确标记")
        compatibility_codes = [
            code for code, frame in trade_frames.items()
            if frame.attrs.get("data_endpoint") == "/api/kline"
        ]
        if benchmark_frame.attrs.get("data_endpoint") == "/api/kline":
            warnings.append("基准使用 VibeDesk /api/kline 兼容回退，未确认前复权口径")
        if compatibility_codes:
            warnings.append(f"{len(compatibility_codes)} 个 ETF 使用 /api/kline 兼容回退，需留意复权断点")

        market_breadth = self._market_breadth(market_overview)
        summary = self._summary(scored, benchmark_metrics, industry_rows)
        summary.update(self._history_summary(history, scored[0]["code"]))
        self._attach_rotation_confirmation(scored, history)
        summary.update(self._rotation_environment(scored, summary))
        summary.update({
            "consensus_leader": (parameter_consensus.get("winner") or {}).get("name", ""),
            "consensus_leader_code": consensus_code,
            "consensus_votes": (parameter_consensus.get("winner") or {}).get("votes", 0),
            "consensus_model_count": model_count,
            "consensus_state": parameter_consensus.get("state", "unavailable"),
            "consensus_label": parameter_consensus.get("signal", "参数分歧"),
            "predictive_signal": "观察",
            "shadow_signal": shadow_state_payload.get("signal", "影子未启用"),
            "shadow_state": shadow_state_payload.get("lifecycle_state", "unavailable"),
            "shadow_leader": (shadow_state_payload.get("winner") or {}).get("name", ""),
            "shadow_leader_code": shadow_code,
            "shadow_votes": (shadow_state_payload.get("winner") or {}).get("votes", 0),
            "shadow_model_count": shadow_model_count,
            "shadow_next_rebalance_in_sessions": shadow_state_payload.get(
                "next_rebalance_in_sessions", 0
            ),
            "shadow_new_signal": bool(shadow_state_payload.get("new_signal")),
        })
        summary["signal_distribution"] = self._signal_distribution(scored)
        summary["market_breadth"] = market_breadth["breadth"]
        summary["market_up_ratio"] = market_breadth["up_ratio"]
        leader_flow = scored[0]["sector_fund_flow"]
        summary["leading_sector_flow_state"] = leader_flow["state"]
        summary["leading_sector_flow_net"] = leader_flow["net"]
        summary["leading_sector_flow_direction"] = leader_flow["direction"]
        summary["leading_sector_flow_persistence"] = leader_flow["persistence"]
        for row in scored:
            row["insight"] = self._row_insight(row, scored, summary, warnings)
            row["insight"]["evidence"].append(
                f"固定9组参数中有 {row['parameter_vote_count']} 组选择该标的；"
                f"至少 {parameter_consensus.get('majority_threshold', 0)} 票只表示当日参数一致，"
                "不直接升级为预测强信号。"
            )
            if shadow_model_count:
                row["insight"]["evidence"].append(
                    f"状态化影子账本有 {row['shadow_vote_count']}/{shadow_model_count} "
                    f"个模型持有该标的；当前状态为{shadow_state_payload.get('signal', '影子观察')}。"
                )
        if market_breadth["state"] == "available":
            breadth_evidence = (
                f"Desk 市场宽度为{market_breadth['breadth']}：上涨 {market_breadth['up']} 家、"
                f"下跌 {market_breadth['down']} 家，上涨占比 {market_breadth['up_ratio']:.1f}%。"
            )
            for row in scored:
                row["insight"]["evidence"].append(breadth_evidence)
        for row in scored:
            fund_flow = row["sector_fund_flow"]
            if fund_flow["state"] == "available":
                row["insight"]["evidence"].append(
                    f"Desk 行业资金确认：{fund_flow['name']}当日净额 "
                    f"{fund_flow['net']:+.2f} 亿元；仅作确认，不改变综合分。"
                )
                persistence = fund_flow["persistence"]
                if persistence["state"] == "available":
                    row["insight"]["evidence"].append(
                        f"行业资金日度账本确认：近{persistence['observed_days']}个已保存交易日中，"
                        f"净流入 {persistence['inflow_days']} 日、净流出 {persistence['outflow_days']} 日，"
                        f"累计净额 {persistence['net_sum']:+.2f} 亿元；不参与综合分。"
                    )
        insight = scored[0]["insight"]
        data_state = "complete" if not warnings and len(scored) == len(self.universe) else "partial"

        payload = {
            "engine": {"name": self.engine_name, "version": self.engine_version},
            "as_of": resolved_as_of,
            "requested_as_of": normalized_as_of,
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "window": window,
            "benchmark": {
                "code": benchmark,
                "name": "沪深300ETF" if benchmark == "510300" else benchmark,
                **{key: _round(value) for key, value in benchmark_metrics.items() if key != "date"},
            },
            "data_source": self.provider.name,
            "data_endpoint": benchmark_frame.attrs.get("data_endpoint", ""),
            "adjust": benchmark_frame.attrs.get("adjust", "unknown"),
            "data_state": data_state,
            "universe_size": len(self.universe),
            "universe_standard": "申万行业分类标准（2021版）一级行业",
            "proxy_count": sum(item.proxy_type != "direct" for item in self.universe),
            "successful_count": len(scored),
            "stale_count": stale_count,
            "weights": self.weights,
            "factor_model": factor_model,
            "parameter_consensus": parameter_consensus,
            "summary": summary,
            "market_breadth": market_breadth,
            "industry_rankings": [
                {
                    "rank": index + 1,
                    "industry": row["industry"],
                    "etf_code": row["code"],
                    "etf_name": row["name"],
                    "proxy_type": row["proxy_type"],
                    "proxy_note": row["proxy_note"],
                    "signal_code": row["signal_code"],
                    "signal_name": row["signal_name"],
                    "signal_mode": row["signal_mode"],
                    "score": row["total_score"],
                    "momentum_20d": row["momentum_20d"],
                    "industry_day_change": row["industry_day_change"],
                    "sector_fund_flow": row["sector_fund_flow"],
                    "regime": row["regime"],
                    "rotation_signal": row["rotation_signal"],
                    "signal_tone": row["signal_tone"],
                    "persistence_score": row["persistence_score"],
                    "parameter_vote_count": row["parameter_vote_count"],
                    "parameter_vote_share_pct": row["parameter_vote_share_pct"],
                    "parameter_consensus_label": row["parameter_consensus_label"],
                    "predictive_signal": row["predictive_signal"],
                    "shadow_vote_count": row["shadow_vote_count"],
                    "shadow_vote_share_pct": row["shadow_vote_share_pct"],
                    "shadow_consensus_winner": row["shadow_consensus_winner"],
                }
                for index, row in enumerate(scored[:10])
            ],
            "rotation_history": history,
            "history_method": "历史轨迹只使用各日期当时可见的价格与成交数据；指数不可用时明确回退 ETF，行业宽度、估值和基本面没有点时证据时不进入历史评分",
            "confirmation_method": "轮动确认使用近20日点时排名持续性、行业宽度、均线结构与拥挤风险，不重复进入综合分",
            "parameter_consensus_method": "固定40/60/120日窗口与balanced/momentum/defensive权重共9组等票；至少5票同向仅表示当日参数一致，不改变综合分，也不直接视为预测强信号",
            "shadow_strategy_method": "前向影子账本按10个交易日再平衡；未到期继续持有，到期时原持仓仍在前三且落后榜首不足5分则保留；历史回放不读写影子状态",
            "fund_flow_confirmation_method": "行业资金使用 Desk 即时截面，并从行业资金日度账本按交易日去重累计最多5日；至少3日才判断持续方向，不参与综合分加权",
            "signal_state": signal_state,
            "index_signal_count": index_signal_count,
            "signal_fallback_count": signal_fallback_count,
            "configured_signal_proxy_count": len(configured_signal_proxy_codes),
            "effective_signal_count": effective_signal_count,
            "effective_signal_coverage_pct": effective_signal_coverage_pct,
            "signal_policy": (
                "same_industry_etf_proxy"
                if len(configured_signal_proxy_codes) == len(scored)
                else "sw_industry_index_preferred_same_industry_etf_proxy_allowed"
            ),
            "signal_adjust": signal_adjust,
            "etfs": scored,
            "insight": insight,
            "warnings": warnings,
            "failures": failures,
            "signal_failures": signal_failures,
        }
        payload["snapshot"] = build_analysis_snapshot(
            analysis_name=self.engine_name,
            analysis_version=self.engine_version,
            parameters={
                "benchmark": benchmark,
                "period": "daily",
                "window": window,
                "asOf": normalized_as_of,
            },
            frame=benchmark_frame,
            requested_bars=request_limit,
            provider_name=self.provider.name,
            input_summary={
                "universe_size": len(self.universe),
                "index_signal_count": index_signal_count,
                "signal_fallback_count": signal_fallback_count,
                "effective_signal_count": effective_signal_count,
                "effective_signal_coverage_pct": effective_signal_coverage_pct,
                "fund_flow_observed_days": leader_flow["persistence"]["observed_days"],
                "active_factor_count": factor_model["active_factor_count"],
                "slow_factor_coverage": factor_model["coverage"],
                "parameter_consensus_models": model_count,
                "shadow_strategy_models": shadow_model_count,
                "shadow_lifecycle_state": shadow_state_payload.get(
                    "lifecycle_state", "unavailable"
                ),
            },
            result_summary={
                "data_state": data_state,
                "successful_count": len(scored),
                "stale_count": stale_count,
                "leader": scored[0]["code"],
                "leader_score": scored[0]["total_score"],
                "summary": summary,
                "warning_count": len(warnings),
                "failure_count": len(failures),
                "signal_state": signal_state,
                "effective_signal_coverage_pct": effective_signal_coverage_pct,
                "factor_model_state": factor_model["state"],
                "active_factor_count": factor_model["active_factor_count"],
                "consensus_leader": consensus_code,
                "consensus_votes": summary["consensus_votes"],
                "predictive_signal": summary["predictive_signal"],
                "shadow_leader": shadow_code,
                "shadow_signal": summary["shadow_signal"],
                "shadow_new_signal": summary["shadow_new_signal"],
            },
        )
        return payload

    @staticmethod
    def _market_breadth(overview: Mapping[str, Any]) -> Dict[str, Any]:
        sentiment = overview.get("sentiment") if isinstance(overview, Mapping) else {}
        sentiment = sentiment if isinstance(sentiment, Mapping) else {}
        up = max(int(sentiment.get("up") or 0), 0)
        down = max(int(sentiment.get("down") or 0), 0)
        flat = max(int(sentiment.get("flat") or 0), 0)
        total = up + down + flat
        available = total > 0 or bool(sentiment.get("breadth"))
        return {
            "state": "available" if available else "unavailable",
            "breadth": str(sentiment.get("breadth") or "暂无"),
            "speculation": str(sentiment.get("speculation") or ""),
            "up": up,
            "down": down,
            "flat": flat,
            "up_ratio": _round(up / total * 100) if total else 0.0,
            "date": str(sentiment.get("date") or ""),
            "updated": str(overview.get("updated") or "") if isinstance(overview, Mapping) else "",
        }

    def _attach_sector_fund_flow(
        self,
        rows: Sequence[Dict[str, Any]],
        overview: Mapping[str, Any],
    ) -> None:
        """Attach latest Desk sector-flow evidence without changing scores."""

        sectors = overview.get("sectors") if isinstance(overview, Mapping) else []
        sectors = sectors if isinstance(sectors, list) else []
        for row in rows:
            industry = str(row.get("industry") or "")
            aliases = next(
                (item.industry_aliases for item in self.universe if item.industry == industry),
                (industry,),
            )
            matched = self._match_sector_flow(industry, aliases, sectors)
            net = _round(matched.get("net")) if matched else 0.0
            row["sector_fund_flow"] = {
                "state": "available" if matched else "unavailable",
                "name": str(matched.get("name") or "") if matched else "",
                "net": net,
                "inflow": _round(matched.get("inflow")) if matched else 0.0,
                "outflow": _round(matched.get("outflow")) if matched else 0.0,
                "direction": (
                    "inflow" if net > 0 else "outflow" if net < 0 else "neutral"
                ),
                "unit": "亿元",
                "source": "desk_market_overview",
                "score_effect": "confirmation_only",
                "persistence": self._empty_sector_fund_flow_persistence(
                    "current_flow_unavailable" if not matched else "history_not_loaded"
                ),
            }

    @staticmethod
    def _empty_sector_fund_flow_persistence(reason: str) -> Dict[str, Any]:
        return {
            "state": "unavailable",
            "reason": reason,
            "observed_days": 0,
            "window_days": 5,
            "inflow_days": 0,
            "outflow_days": 0,
            "neutral_days": 0,
            "net_sum": 0.0,
            "direction": "unknown",
            "label": "积累中",
            "as_of_dates": [],
            "source": "sector_fund_flow_history",
            "score_effect": "confirmation_only",
        }

    @classmethod
    def _attach_sector_fund_flow_persistence(
        cls,
        rows: Sequence[Dict[str, Any]],
        history: Sequence[Mapping[str, Any]],
        *,
        resolved_as_of: str,
        historical: bool,
    ) -> None:
        """Summarize distinct saved trading days; repeated refreshes count once."""

        if historical:
            for row in rows:
                row["sector_fund_flow"]["persistence"] = (
                    cls._empty_sector_fund_flow_persistence("historical_as_of_isolated")
                )
            return

        observations: Dict[str, Dict[str, float]] = {}
        for record in history:
            if not isinstance(record, Mapping):
                continue
            as_of = str(record.get("as_of") or "")
            if not as_of or as_of >= resolved_as_of or as_of in observations:
                continue
            day: Dict[str, float] = {}
            for item in record.get("flows") or ():
                if not isinstance(item, Mapping):
                    continue
                industry = str(item.get("industry") or "")
                if industry:
                    day[industry] = _round(item.get("net"))
            if day:
                observations[as_of] = day

        history_dates = sorted(observations, reverse=True)[:4]
        for row in rows:
            flow = row["sector_fund_flow"]
            if flow["state"] != "available":
                flow["persistence"] = cls._empty_sector_fund_flow_persistence(
                    "current_flow_unavailable"
                )
                continue
            values = [(resolved_as_of, _round(flow.get("net")))]
            industry = str(row.get("industry") or "")
            values.extend(
                (as_of, observations[as_of][industry])
                for as_of in history_dates
                if industry in observations[as_of]
            )
            observed_days = len(values)
            inflow_days = sum(net > 0 for _, net in values)
            outflow_days = sum(net < 0 for _, net in values)
            neutral_days = observed_days - inflow_days - outflow_days
            net_sum = _round(sum(net for _, net in values))
            if observed_days < 3:
                state, direction, label, reason = (
                    "unavailable", "unknown", "积累中", "insufficient_distinct_trading_days"
                )
            elif inflow_days >= observed_days - 1 and net_sum > 0:
                state, direction, label, reason = "available", "inflow", "持续流入", None
            elif outflow_days >= observed_days - 1 and net_sum < 0:
                state, direction, label, reason = "available", "outflow", "持续流出", None
            else:
                state, direction, label, reason = "available", "mixed", "方向反复", None
            flow["persistence"] = {
                "state": state,
                "reason": reason,
                "observed_days": observed_days,
                "window_days": 5,
                "inflow_days": inflow_days,
                "outflow_days": outflow_days,
                "neutral_days": neutral_days,
                "net_sum": net_sum,
                "direction": direction,
                "label": label,
                "as_of_dates": [as_of for as_of, _ in values],
                "source": "sector_fund_flow_history",
                "score_effect": "confirmation_only",
            }

    @staticmethod
    def _match_sector_flow(
        industry: str,
        aliases: Sequence[str],
        sectors: Sequence[Mapping[str, Any]],
    ) -> Dict[str, Any] | None:
        matches = []
        for sector in sectors:
            if not isinstance(sector, Mapping):
                continue
            name = str(sector.get("name") or "")
            standardized = resolve_sw_l1_industry(name) == industry
            custom_alias = any(alias and alias.lower() in name.lower() for alias in aliases)
            if name and (standardized or custom_alias):
                matches.append(dict(sector))
        return max(matches, key=lambda item: abs(_round(item.get("net"))), default=None)

    @staticmethod
    def _benchmark_metrics(frame: pd.DataFrame, window: int) -> Dict[str, float | str]:
        close = frame["close"].astype(float)
        returns = close.pct_change().dropna()
        ma20 = float(close.tail(20).mean())
        return {
            "date": frame["date"].iloc[-1].strftime("%Y-%m-%d"),
            "return_20d": _safe_return(close, 20) * 100,
            "return_window": _safe_return(close, window) * 100,
            "annual_volatility": float(returns.tail(20).std(ddof=0) * math.sqrt(252) * 100),
            "distance_ma20": (float(close.iloc[-1]) / ma20 - 1) * 100 if ma20 else 0.0,
        }

    @staticmethod
    def _session_lag(reference_dates: pd.Series, data_date: Any) -> int:
        """Return the number of reference trading sessions after ``data_date``."""
        timestamp = pd.Timestamp(data_date)
        return int((pd.to_datetime(reference_dates) > timestamp).sum())

    @staticmethod
    def _industry_rows(snapshot: Mapping[str, Any]) -> List[Dict[str, Any]]:
        merged: Dict[str, Dict[str, Any]] = {}
        for row in list(snapshot.get("top") or []) + list(snapshot.get("bottom") or []):
            if not isinstance(row, Mapping):
                continue
            key = str(row.get("code") or row.get("name") or "")
            if key:
                merged[key] = dict(row)
        total = int(snapshot.get("total") or len(merged) or 0)
        rows = list(merged.values())
        for row in rows:
            rank = float(row.get("rank") or total or 1)
            row["rank_score"] = 100 - ((rank - 1) / max(total - 1, 1) * 100)
        return rows

    @staticmethod
    def _match_industry(item: SectorETF, rows: Iterable[Mapping[str, Any]]) -> Dict[str, Any] | None:
        matches = []
        for row in rows:
            name = str(row.get("name") or "")
            standardized = resolve_sw_l1_industry(name) == item.industry
            custom_alias = any(alias.lower() in name.lower() for alias in item.industry_aliases)
            if standardized or custom_alias:
                matches.append(dict(row))
        return max(matches, key=lambda row: float(row.get("rank_score") or 0), default=None)

    @staticmethod
    def _slow_factor_row(
        item: SectorETF,
        slow_factors: Optional[Mapping[str, Any]],
    ) -> Mapping[str, Any]:
        if not isinstance(slow_factors, Mapping):
            return {}
        items = slow_factors.get("items", slow_factors)
        if not isinstance(items, Mapping):
            return {}
        for key in (item.code, item.industry, item.name):
            value = items.get(key)
            if isinstance(value, Mapping):
                return value
        return {}

    def _raw_metrics(
        self,
        item: SectorETF,
        frame: pd.DataFrame,
        benchmark: Mapping[str, float | str],
        window: int,
        industry_rows: Sequence[Mapping[str, Any]],
        *,
        trade_frame: Optional[pd.DataFrame] = None,
        signal_mode: Optional[str] = None,
        slow_factors: Optional[Mapping[str, Any]] = None,
    ) -> Dict[str, Any]:
        trade_frame = frame if trade_frame is None else trade_frame
        signal_mode = signal_mode or str(frame.attrs.get("rotation_signal_mode") or "trade_asset")
        close = frame["close"].astype(float)
        trade_close = trade_frame["close"].astype(float)
        volume = trade_frame["volume"].astype(float).replace(0, np.nan)
        returns = close.pct_change()
        trade_returns = trade_close.pct_change()
        ma20 = float(close.tail(20).mean())
        ma60 = float(close.tail(min(60, len(close))).mean())
        momentum_5 = _safe_return(close, 5) * 100
        momentum_20 = _safe_return(close, 20) * 100
        momentum_window = _safe_return(close, window) * 100
        relative_20 = momentum_20 - float(benchmark["return_20d"])
        relative_window = momentum_window - float(benchmark["return_window"])
        distance_ma20 = (float(close.iloc[-1]) / ma20 - 1) * 100 if ma20 else 0.0
        ma20_vs_ma60 = (ma20 / ma60 - 1) * 100 if ma60 else 0.0
        trend_raw = distance_ma20 + ma20_vs_ma60
        recent_volume = float(volume.tail(5).mean())
        base_volume = float(volume.tail(20).mean())
        volume_ratio = recent_volume / base_volume if base_volume and math.isfinite(base_volume) else 1.0
        positive_volume_share = float((trade_returns.tail(10).fillna(0) > 0).mean())
        volume_continuity_raw = volume_ratio * 0.65 + positive_volume_share * 0.35
        annual_volatility = float(returns.tail(20).std(ddof=0) * math.sqrt(252) * 100)
        drawdown = _max_drawdown(close.tail(min(window, 60))) * 100
        crowding_raw = annual_volatility * 0.55 + drawdown * 0.30 + max(distance_ma20 - 8, 0) * 0.15
        short_exhaustion = (
            max(momentum_5 - 6.0, 0.0) * 0.80
            + max(volume_ratio - 1.5, 0.0) * 8.0
            + max(distance_ma20 - 8.0, 0.0) * 0.55
        )
        downside_break = (
            max(-distance_ma20 - 4.0, 0.0) * 0.55
            + max(-momentum_20, 0.0) * 0.20
        )
        healthy_pullback = (
            momentum_20 > 0
            and ma20_vs_ma60 > 0
            and -4.0 <= momentum_5 <= 1.5
            and -3.0 <= distance_ma20 <= 4.0
            and volume_ratio <= 1.4
        )
        pullback_reward = 8.0 if healthy_pullback else 0.0
        crowding_reversal_raw = pullback_reward - crowding_raw - short_exhaustion - downside_break

        slow_row = self._slow_factor_row(item, slow_factors)
        valuation_percentile = _optional_number(slow_row.get("valuation_percentile"))
        valuation_score = _optional_number(slow_row.get("valuation_score"))
        if math.isnan(valuation_score) and not math.isnan(valuation_percentile):
            valuation_score = 100.0 - min(max(valuation_percentile, 0.0), 100.0)
        fundamental_quality_score = _optional_number(
            slow_row.get("fundamental_quality_score", slow_row.get("fundamental_quality"))
        )
        slow_factor_as_of = str(
            slow_row.get("as_of")
            or (slow_factors.get("as_of") if isinstance(slow_factors, Mapping) else "")
            or ""
        )
        slow_factor_source = str(
            slow_row.get("source")
            or (slow_factors.get("source") if isinstance(slow_factors, Mapping) else "")
            or ""
        )
        if slow_factor_as_of:
            try:
                if pd.Timestamp(slow_factor_as_of) > pd.Timestamp(frame["date"].iloc[-1]):
                    valuation_percentile = float("nan")
                    valuation_score = float("nan")
                    fundamental_quality_score = float("nan")
            except (TypeError, ValueError):
                valuation_percentile = float("nan")
                valuation_score = float("nan")
                fundamental_quality_score = float("nan")

        matched = self._match_industry(item, industry_rows)
        industry_score = 50.0
        industry_day_change = 0.0
        industry_rank = None
        industry_name = ""
        if matched:
            up_count = float(matched.get("up_count") or 0)
            down_count = float(matched.get("down_count") or 0)
            breadth = up_count / max(up_count + down_count, 1) * 100
            industry_day_change = float(matched.get("change_pct") or 0)
            change_score = min(100.0, max(0.0, 50 + industry_day_change * 12))
            industry_score = float(matched.get("rank_score") or 50) * 0.50 + breadth * 0.30 + change_score * 0.20
            industry_rank = int(matched.get("rank") or 0) or None
            industry_name = str(matched.get("name") or "")

        return {
            "code": item.code,
            "name": item.name,
            "industry": item.industry,
            "proxy_type": item.proxy_type,
            "proxy_note": item.proxy_note,
            "date": trade_frame["date"].iloc[-1].strftime("%Y-%m-%d"),
            "close": float(trade_close.iloc[-1]),
            "signal_code": str(
                frame.attrs.get("rotation_signal_code")
                or (item.resolved_signal_code if signal_mode == "industry_index" else item.code)
            ),
            "signal_name": str(
                frame.attrs.get("rotation_signal_name")
                or (item.resolved_signal_name if signal_mode == "industry_index" else item.name)
            ),
            "signal_mode": signal_mode,
            "signal_adjust": str(frame.attrs.get("adjust") or "unknown"),
            "signal_date": frame["date"].iloc[-1].strftime("%Y-%m-%d"),
            "signal_lag_sessions": int(frame.attrs.get("signal_lag_sessions", 0) or 0),
            "momentum_5d": momentum_5,
            "momentum_20d": momentum_20,
            "momentum_window": momentum_window,
            "relative_20d": relative_20,
            "relative_window": relative_window,
            "trend_raw": trend_raw,
            "distance_ma20": distance_ma20,
            "ma20_vs_ma60": ma20_vs_ma60,
            "volume_ratio": volume_ratio,
            "volume_continuity_raw": volume_continuity_raw,
            "annual_volatility": annual_volatility,
            "max_drawdown": drawdown,
            "risk_raw": crowding_raw,
            "crowding_reversal_raw": crowding_reversal_raw,
            "short_exhaustion": short_exhaustion,
            "downside_break": downside_break,
            "healthy_pullback": healthy_pullback,
            "valuation_percentile": valuation_percentile,
            "valuation_score_raw": valuation_score,
            "fundamental_quality_score_raw": fundamental_quality_score,
            "slow_factor_as_of": slow_factor_as_of,
            "slow_factor_source": slow_factor_source,
            "industry_score": industry_score,
            "industry_day_change": industry_day_change,
            "industry_rank": industry_rank,
            "industry_match": industry_name,
            "data_lag_sessions": int(trade_frame.attrs.get("data_lag_sessions", 0) or 0),
        }

    @staticmethod
    def _factor_frame(rows: List[Dict[str, Any]]) -> pd.DataFrame:
        """Rank weight-independent factors once for a cross section."""

        frame = pd.DataFrame(rows)
        frame["momentum_score"] = (
            _rank_score(frame["momentum_5d"]) * 0.15
            + _rank_score(frame["momentum_20d"]) * 0.50
            + _rank_score(frame["momentum_window"]) * 0.35
        )
        frame["relative_strength_score"] = (
            _rank_score(frame["relative_20d"]) * 0.65
            + _rank_score(frame["relative_window"]) * 0.35
        )
        frame["trend_score"] = _rank_score(frame["trend_raw"])
        frame["volume_continuity_score"] = _rank_score(frame["volume_continuity_raw"])
        frame["crowding_reversal_score"] = _rank_score(frame["crowding_reversal_raw"])
        frame["risk_score"] = _rank_score(frame["risk_raw"])
        frame["valuation_score"] = pd.to_numeric(
            frame["valuation_score_raw"], errors="coerce"
        ).clip(0, 100)
        frame["fundamental_quality_score"] = pd.to_numeric(
            frame["fundamental_quality_score_raw"], errors="coerce"
        ).clip(0, 100)
        return frame

    def _factor_model(self, factors: pd.DataFrame) -> Dict[str, Any]:
        coverage = {
            "valuation": float(factors["valuation_score"].notna().mean()),
            "fundamental_quality": float(
                factors["fundamental_quality_score"].notna().mean()
            ),
        }
        active_factors = [
            key for key in self.factor_keys
            if key not in self.slow_factor_keys
            or coverage[key] >= self.slow_factor_min_coverage
        ]
        denominator = sum(self.weights[key] for key in active_factors)
        effective_weights = {
            key: (self.weights[key] / denominator if key in active_factors else 0.0)
            for key in self.factor_keys
        }
        inactive = [key for key in self.slow_factor_keys if key not in active_factors]
        return {
            "schema_version": "instock.rotation.factors.v2",
            "state": "complete" if not inactive else "fast_factors_only",
            "configured_factor_count": len(self.factor_keys),
            "active_factor_count": len(active_factors),
            "active_factors": active_factors,
            "inactive_slow_factors": inactive,
            "configured_weights": {key: _round(value, 4) for key, value in self.weights.items()},
            "effective_weights": {
                key: _round(value, 4) for key, value in effective_weights.items()
            },
            "coverage": {key: _round(value * 100, 1) for key, value in coverage.items()},
            "slow_factor_min_coverage_pct": _round(self.slow_factor_min_coverage * 100, 1),
            "industry_breadth_role": "confirmation_only",
            "missing_slow_factor_policy": "exclude_and_renormalize_without_lookahead",
        }

    def _score_factor_frame(
        self,
        factors: pd.DataFrame,
        *,
        factor_model: Optional[Mapping[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Apply this engine's weights to a pre-ranked factor frame."""

        frame = factors.copy()
        model = dict(factor_model or self._factor_model(frame))
        effective_weights = model["effective_weights"]
        frame["valuation_score"] = frame["valuation_score"].fillna(50.0)
        frame["fundamental_quality_score"] = frame["fundamental_quality_score"].fillna(50.0)
        frame["total_score"] = sum(
            frame[f"{key}_score"] * float(effective_weights[key])
            for key in self.factor_keys
        ).clip(0, 100)
        frame = frame.sort_values(["total_score", "momentum_20d"], ascending=False).reset_index(drop=True)

        output = []
        for index, row in frame.iterrows():
            score = float(row["total_score"])
            distance_ma20 = float(row["distance_ma20"])
            ma20_vs_ma60 = float(row["ma20_vs_ma60"])
            if distance_ma20 > 0 and ma20_vs_ma60 > 0:
                trend_state = "多头"
            elif distance_ma20 > 0:
                trend_state = "修复"
            elif ma20_vs_ma60 > 0:
                trend_state = "回踩"
            else:
                trend_state = "空头"
            if score >= 70 and row["momentum_20d"] > 0 and row["relative_20d"] > 0:
                regime, signal = "领先", "持有"
            elif score >= 58:
                regime, signal = "转强", "关注"
            elif score >= 42:
                regime, signal = "中性", "观察"
            else:
                regime, signal = "回避", "减配"
            output.append({
                "rank": index + 1,
                "code": row["code"],
                "name": row["name"],
                "industry": row["industry"],
                "proxy_type": row["proxy_type"],
                "proxy_note": row["proxy_note"],
                "signal_code": row["signal_code"],
                "signal_name": row["signal_name"],
                "signal_mode": row["signal_mode"],
                "signal_adjust": row["signal_adjust"],
                "signal_date": row["signal_date"],
                "signal_lag_sessions": int(row["signal_lag_sessions"]),
                "date": row["date"],
                "close": _round(row["close"], 3),
                "total_score": _round(score),
                "momentum_5d": _round(row["momentum_5d"]),
                "momentum_20d": _round(row["momentum_20d"]),
                "momentum_window": _round(row["momentum_window"]),
                "relative_20d": _round(row["relative_20d"]),
                "relative_window": _round(row["relative_window"]),
                "distance_ma20": _round(distance_ma20),
                "ma20_vs_ma60": _round(ma20_vs_ma60),
                "trend_state": trend_state,
                "annual_volatility": _round(row["annual_volatility"]),
                "max_drawdown": _round(row["max_drawdown"]),
                "volume_ratio": _round(row["volume_ratio"]),
                "short_exhaustion": _round(row["short_exhaustion"]),
                "downside_break": _round(row["downside_break"]),
                "healthy_pullback": bool(row["healthy_pullback"]),
                "valuation_percentile": (
                    None if pd.isna(row["valuation_percentile"])
                    else _round(row["valuation_percentile"])
                ),
                "slow_factor_as_of": row["slow_factor_as_of"],
                "slow_factor_source": row["slow_factor_source"],
                "industry_day_change": _round(row["industry_day_change"]),
                "industry_rank": None if pd.isna(row["industry_rank"]) else int(row["industry_rank"]),
                "industry_match": row["industry_match"],
                "data_date": row["date"],
                "data_lag_sessions": int(row["data_lag_sessions"]),
                "is_stale": int(row["data_lag_sessions"]) > 0,
                "factor_scores": {
                    "momentum": _round(row["momentum_score"]),
                    "relative_strength": _round(row["relative_strength_score"]),
                    "trend": _round(row["trend_score"]),
                    "volume_continuity": _round(row["volume_continuity_score"]),
                    "crowding_reversal": _round(row["crowding_reversal_score"]),
                    "valuation": _round(row["valuation_score"]),
                    "fundamental_quality": _round(row["fundamental_quality_score"]),
                    # Compatibility evidence retained for confirmation/UI consumers.
                    "industry": _round(row["industry_score"]),
                    "risk_penalty": _round(row["risk_score"]),
                },
                "factor_availability": {
                    "valuation": not pd.isna(row["valuation_score_raw"]),
                    "fundamental_quality": not pd.isna(
                        row["fundamental_quality_score_raw"]
                    ),
                },
                "regime": regime,
                "signal": signal,
            })
        return output

    def _score_rows(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return self._score_factor_frame(self._factor_frame(rows))

    @classmethod
    def _select_with_buffer(
        cls,
        rankings: Sequence[Mapping[str, Any]],
        held_symbol: Optional[str],
    ) -> Mapping[str, Any]:
        leader = rankings[0]
        if not held_symbol or leader["code"] == held_symbol:
            return leader
        incumbent = next(
            (row for row in rankings if row["code"] == held_symbol), None
        )
        if (
            incumbent
            and int(incumbent["rank"]) <= cls.shadow_hold_rank_limit
            and float(leader["total_score"])
            - float(incumbent["total_score"])
            < cls.shadow_switch_score_gap
        ):
            return incumbent
        return leader

    @classmethod
    def _select_shadow_position(
        cls,
        rankings: Sequence[Mapping[str, Any]],
        previous_code: str,
        lifecycle_state: str,
    ) -> tuple[Mapping[str, Any], str]:
        leader = rankings[0]
        if lifecycle_state in {"bootstrap", "reinitialized_after_gap"}:
            return leader, lifecycle_state
        if lifecycle_state in {"holding", "same_day"}:
            incumbent = next(
                (row for row in rankings if row["code"] == previous_code), None
            )
            if incumbent is not None:
                return incumbent, "hold"
            return leader, "forced_switch_unavailable"
        selected = cls._select_with_buffer(rankings, previous_code)
        if previous_code and selected["code"] == previous_code:
            return selected, "hold_buffer"
        return selected, "switch"

    @staticmethod
    def _parameter_vote_summary(models: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        model_count = len(models)
        if not model_count:
            return {
                "model_count": 0,
                "majority_threshold": 0,
                "state": "unavailable",
                "winner": {},
                "ranking": [],
            }
        vote_counts: Dict[str, int] = {}
        score_totals: Dict[str, float] = {}
        metadata: Dict[str, Dict[str, Any]] = {}
        for model in models:
            code = str(model["code"])
            vote_counts[code] = vote_counts.get(code, 0) + 1
            score_totals[code] = score_totals.get(code, 0.0) + float(model["score"])
            metadata[code] = model
        ranking = sorted(
            (
                {
                    "code": code,
                    "name": metadata[code]["name"],
                    "industry": metadata[code]["industry"],
                    "votes": votes,
                    "vote_share_pct": _round(votes / model_count * 100),
                    "average_leader_score": _round(score_totals[code] / votes),
                }
                for code, votes in vote_counts.items()
            ),
            key=lambda row: (
                int(row["votes"]),
                float(row["average_leader_score"]),
                str(row["code"]),
            ),
            reverse=True,
        )
        majority_threshold = model_count // 2 + 1
        winner = dict(ranking[0])
        strict_majority = int(winner["votes"]) >= majority_threshold
        return {
            "model_count": model_count,
            "majority_threshold": majority_threshold,
            "state": "strict_majority" if strict_majority else "split_vote",
            "winner": winner,
            "ranking": ranking,
        }

    @classmethod
    def _shadow_schedule(
        cls,
        benchmark_frame: pd.DataFrame,
        shadow_state: Optional[Mapping[str, Any]],
        *,
        enabled: bool,
    ) -> Dict[str, Any]:
        current_date = pd.Timestamp(benchmark_frame["date"].iloc[-1]).strftime(
            "%Y-%m-%d"
        )
        base = {
            "as_of": current_date,
            "previous_as_of": "",
            "last_rebalance_date": current_date,
            "sessions_since_rebalance": 0,
            "next_rebalance_in_sessions": cls.shadow_rebalance_days,
            "lifecycle_state": "bootstrap",
            "new_signal": True,
        }
        if not enabled:
            return {
                **base,
                "lifecycle_state": "historical_disabled",
                "new_signal": False,
            }
        if (
            not isinstance(shadow_state, Mapping)
            or shadow_state.get("strategy_id") != cls.shadow_strategy_id
            or not shadow_state.get("models")
        ):
            return base
        previous_as_of = str(shadow_state.get("as_of") or "")
        last_rebalance_date = str(
            shadow_state.get("last_rebalance_date") or previous_as_of or ""
        )
        base["previous_as_of"] = previous_as_of
        if not last_rebalance_date:
            return base
        try:
            current = pd.Timestamp(current_date)
            last_rebalance = pd.Timestamp(last_rebalance_date)
        except (TypeError, ValueError):
            return base
        if last_rebalance > current:
            return base
        benchmark_dates = pd.DatetimeIndex(pd.to_datetime(benchmark_frame["date"]))
        sessions_since = int(((benchmark_dates > last_rebalance) & (benchmark_dates <= current)).sum())
        base.update({
            "last_rebalance_date": last_rebalance.strftime("%Y-%m-%d"),
            "sessions_since_rebalance": sessions_since,
            "next_rebalance_in_sessions": max(
                cls.shadow_rebalance_days - sessions_since, 0
            ),
        })
        if previous_as_of == current_date:
            base.update({"lifecycle_state": "same_day", "new_signal": False})
        elif sessions_since < cls.shadow_rebalance_days:
            base.update({"lifecycle_state": "holding", "new_signal": False})
        elif sessions_since < cls.shadow_rebalance_days * 2:
            base.update({
                "lifecycle_state": "rebalanced",
                "last_rebalance_date": current_date,
                "sessions_since_rebalance": 0,
                "next_rebalance_in_sessions": cls.shadow_rebalance_days,
                "new_signal": True,
            })
        else:
            base.update({
                "lifecycle_state": "reinitialized_after_gap",
                "last_rebalance_date": current_date,
                "sessions_since_rebalance": 0,
                "next_rebalance_in_sessions": cls.shadow_rebalance_days,
                "new_signal": True,
            })
        return base

    def _parameter_consensus(
        self,
        *,
        trade_frames: Mapping[str, pd.DataFrame],
        signal_frames: Mapping[str, pd.DataFrame],
        benchmark_frame: pd.DataFrame,
        industry_rows: Sequence[Mapping[str, Any]],
        slow_factors: Optional[Mapping[str, Any]],
        shadow_state: Optional[Mapping[str, Any]] = None,
        shadow_enabled: bool = True,
    ) -> Dict[str, Any]:
        """Vote fixed parameters and maintain a separate forward shadow state."""

        schedule = self._shadow_schedule(
            benchmark_frame, shadow_state, enabled=shadow_enabled
        )
        previous_models = {
            str(row.get("id")): row
            for row in ((shadow_state or {}).get("models") or ())
            if isinstance(row, Mapping) and row.get("id")
        }
        models: List[Dict[str, Any]] = []
        shadow_models: List[Dict[str, Any]] = []
        for window in (40, 60, 120):
            if len(benchmark_frame) < window + 1:
                continue
            benchmark_metrics = self._benchmark_metrics(benchmark_frame, window)
            raw_rows = []
            for item in self.universe:
                trade_frame = trade_frames.get(item.code)
                signal_frame = signal_frames.get(item.code)
                if (
                    trade_frame is None
                    or signal_frame is None
                    or len(trade_frame) < window + 1
                    or len(signal_frame) < window + 1
                ):
                    continue
                raw_rows.append(self._raw_metrics(
                    item,
                    signal_frame,
                    benchmark_metrics,
                    window,
                    industry_rows,
                    trade_frame=trade_frame,
                    signal_mode=str(
                        signal_frame.attrs.get("rotation_signal_mode") or "trade_asset"
                    ),
                    slow_factors=slow_factors,
                ))
            if len(raw_rows) < min(8, len(self.universe)):
                continue
            factors = self._factor_frame(raw_rows)
            for profile, weights in ROTATION_WEIGHT_PROFILES.items():
                scorer = RotationEngine(
                    self.provider,
                    universe=self.universe,
                    max_workers=self.max_workers,
                    weights=weights,
                )
                rankings = scorer._score_factor_frame(
                    factors,
                    factor_model=scorer._factor_model(factors),
                )
                if not rankings:
                    continue
                model_id = f"{profile}-w{window}"
                leader = rankings[0]
                models.append({
                    "id": model_id,
                    "profile": profile,
                    "window": window,
                    "code": leader["code"],
                    "name": leader["name"],
                    "industry": leader["industry"],
                    "score": leader["total_score"],
                })
                if not shadow_enabled:
                    continue
                previous_code = str(
                    (previous_models.get(model_id) or {}).get("selected_code") or ""
                )
                lifecycle = schedule["lifecycle_state"]
                selected, action = scorer._select_shadow_position(
                    rankings, previous_code, lifecycle
                )
                shadow_models.append({
                    "id": model_id,
                    "profile": profile,
                    "window": window,
                    "code": selected["code"],
                    "name": selected["name"],
                    "industry": selected["industry"],
                    "score": selected["total_score"],
                    "selected_code": selected["code"],
                    "selected_rank": selected["rank"],
                    "previous_code": previous_code,
                    "leader_code": leader["code"],
                    "leader_name": leader["name"],
                    "leader_score": leader["total_score"],
                    "action": action,
                })

        static_vote = self._parameter_vote_summary(models)
        if not models:
            return {
                "method": "equal_vote_3_profiles_x_3_windows",
                **static_vote,
                "signal": "不可用",
                "prediction_state": "unavailable",
                "models": [],
                "shadow_state": {
                    "strategy_id": self.shadow_strategy_id,
                    **schedule,
                    "state": "unavailable",
                    "models": [],
                    "deployment": "shadow_only",
                },
                "score_effect": "confirmation_only",
            }
        strict_majority = static_vote["state"] == "strict_majority"
        shadow_vote = self._parameter_vote_summary(shadow_models)
        shadow_strict = shadow_vote["state"] == "strict_majority"
        lifecycle = schedule["lifecycle_state"]
        if lifecycle == "historical_disabled":
            shadow_label = "历史状态不回填"
        elif lifecycle == "bootstrap":
            shadow_label = "影子初始化"
        elif lifecycle == "reinitialized_after_gap":
            shadow_label = "影子断档重置"
        elif lifecycle == "same_day":
            shadow_label = "影子已记录"
        elif lifecycle == "holding":
            shadow_label = "影子持有" if shadow_strict else "影子分歧"
        else:
            shadow_label = "影子一致" if shadow_strict else "影子分歧"
        shadow_payload = {
            "schema_version": "instock.rotation.shadow.v1",
            "strategy_id": self.shadow_strategy_id,
            **schedule,
            "state": shadow_vote["state"],
            "signal": shadow_label,
            "model_count": shadow_vote["model_count"],
            "majority_threshold": shadow_vote["majority_threshold"],
            "winner": shadow_vote["winner"],
            "ranking": shadow_vote["ranking"],
            "models": shadow_models,
            "rebalance_days": self.shadow_rebalance_days,
            "hold_rank_limit": self.shadow_hold_rank_limit,
            "switch_score_gap": self.shadow_switch_score_gap,
            "signal_id": (
                f"{self.shadow_strategy_id}:{schedule['as_of']}"
                if schedule["new_signal"] else ""
            ),
            "deployment": "shadow_only",
            "note": "影子状态只按新交易日推进；历史回放不写入，断档两期自动重置。",
        }
        return {
            "method": "equal_vote_3_profiles_x_3_windows",
            **static_vote,
            "signal": "参数一致" if strict_majority else "参数分歧",
            "prediction_state": "observation_only",
            "models": models,
            "shadow_state": shadow_payload,
            "score_effect": "confirmation_only",
            "note": "当日静态投票只表示参数一致；状态化选择单独写入影子账本并等待前向验证。",
        }

    def _build_history(
        self,
        trade_frames: Mapping[str, pd.DataFrame],
        signal_frames: Mapping[str, pd.DataFrame],
        benchmark_frame: pd.DataFrame,
        window: int,
        history_days: int = 20,
    ) -> List[Dict[str, Any]]:
        """Replay recent cross-sectional rankings using only data known that day."""

        points: List[Dict[str, Any]] = []
        candidate_dates = list(benchmark_frame["date"].tail(history_days))
        for target_date in candidate_dates:
            benchmark_slice = benchmark_frame[benchmark_frame["date"] <= target_date]
            if len(benchmark_slice) < 25:
                continue
            benchmark_metrics = self._benchmark_metrics(benchmark_slice, window)
            raw_rows = []
            for item in self.universe:
                trade_source = trade_frames.get(item.code)
                signal_source = signal_frames.get(item.code)
                if trade_source is None or signal_source is None:
                    continue
                trade_slice = trade_source[trade_source["date"] <= target_date]
                if len(trade_slice) < 25:
                    continue
                trade_lag = self._session_lag(
                    benchmark_slice["date"], trade_slice["date"].iloc[-1]
                )
                if trade_lag > self.max_stale_sessions:
                    continue
                trade_slice = trade_slice.copy()
                trade_slice.attrs.update(trade_source.attrs)
                trade_slice.attrs["data_lag_sessions"] = trade_lag

                signal_slice = signal_source[signal_source["date"] <= target_date]
                signal_mode = str(
                    signal_source.attrs.get("rotation_signal_mode") or "trade_asset"
                )
                signal_lag = (
                    self._session_lag(
                        benchmark_slice["date"], signal_slice["date"].iloc[-1]
                    )
                    if not signal_slice.empty else self.max_stale_sessions + 1
                )
                if len(signal_slice) < 25 or signal_lag > self.max_stale_sessions:
                    signal_slice = trade_slice.copy()
                    signal_mode = "etf_fallback" if item.has_industry_index_signal else "trade_asset"
                else:
                    signal_slice = signal_slice.copy()
                    signal_slice.attrs.update(signal_source.attrs)
                signal_slice.attrs["signal_lag_sessions"] = self._session_lag(
                    benchmark_slice["date"], signal_slice["date"].iloc[-1]
                )
                signal_slice.attrs["rotation_signal_mode"] = signal_mode
                signal_slice.attrs["rotation_signal_code"] = (
                    item.resolved_signal_code if signal_mode == "industry_index" else item.code
                )
                signal_slice.attrs["rotation_signal_name"] = (
                    item.resolved_signal_name if signal_mode == "industry_index" else item.name
                )
                # Historical industry breadth is intentionally neutral: the
                # existing VibeDesk industry endpoint is a current snapshot,
                # so reusing it here would leak future information.
                raw_rows.append(self._raw_metrics(
                    item,
                    signal_slice,
                    benchmark_metrics,
                    window,
                    [],
                    trade_frame=trade_slice,
                    signal_mode=signal_mode,
                ))
            if not raw_rows:
                continue
            rankings = self._score_rows(raw_rows)
            points.append({
                "date": pd.Timestamp(target_date).strftime("%Y-%m-%d"),
                "leader": {
                    "code": rankings[0]["code"],
                    "name": rankings[0]["name"],
                    "industry": rankings[0]["industry"],
                    "score": rankings[0]["total_score"],
                    "signal_mode": rankings[0]["signal_mode"],
                },
                "rankings": [
                    {
                        "rank": row["rank"],
                        "code": row["code"],
                        "name": row["name"],
                        "industry": row["industry"],
                        "score": row["total_score"],
                        "signal_mode": row["signal_mode"],
                    }
                    for row in rankings
                ],
            })
        return points

    @staticmethod
    def _history_summary(history: Sequence[Mapping[str, Any]], current_leader_code: str) -> Dict[str, Any]:
        leaders = [str(point.get("leader", {}).get("code") or "") for point in history]
        changes = sum(left != right for left, right in zip(leaders, leaders[1:]))
        streak = 0
        for code in reversed(leaders):
            if code != current_leader_code:
                break
            streak += 1
        unique_leaders = len({code for code in leaders if code})
        return {
            "leader_streak_days": streak,
            "rotation_changes_20d": changes,
            "unique_leaders_20d": unique_leaders,
            "history_days": len(history),
        }

    @staticmethod
    def _attach_rotation_confirmation(
        rows: Sequence[Dict[str, Any]],
        history: Sequence[Mapping[str, Any]],
    ) -> None:
        """Add a confirmation layer without changing the cross-sectional score."""

        rank_history: Dict[str, List[int]] = {str(row["code"]): [] for row in rows}
        for point in history:
            for item in point.get("rankings") or []:
                code = str(item.get("code") or "")
                if code in rank_history:
                    rank_history[code].append(int(item.get("rank") or len(rows)))

        top3_limit = min(3, len(rows))
        top5_limit = min(5, len(rows))
        for row in rows:
            ranks = rank_history.get(str(row["code"]), [])
            sample_days = len(ranks)
            top3_days = sum(rank <= top3_limit for rank in ranks)
            top5_days = sum(rank <= top5_limit for rank in ranks)
            leader_days = sum(rank == 1 for rank in ranks)
            top3_rate = top3_days / sample_days * 100 if sample_days else 0.0
            top5_rate = top5_days / sample_days * 100 if sample_days else 0.0
            persistence_score = top3_rate * 0.65 + top5_rate * 0.35
            if ranks:
                previous_rank = ranks[-6] if len(ranks) >= 6 else ranks[0]
                rank_change_5d = previous_rank - ranks[-1]
                average_rank = sum(ranks) / len(ranks)
            else:
                rank_change_5d = 0
                average_rank = float(row["rank"])

            trend_confirmed = (
                row.get("trend_state") == "多头"
                and float(row.get("momentum_20d") or 0) > 0
                and float(row.get("relative_20d") or 0) > 0
            )
            risk_score = float(row.get("factor_scores", {}).get("risk_penalty") or 0)
            overheated = (
                float(row.get("distance_ma20") or 0) >= 8
                or (risk_score >= 85 and float(row.get("momentum_20d") or 0) >= 10)
            )
            if overheated:
                risk_state = "过热"
            elif risk_score >= 70:
                risk_state = "偏热"
            else:
                risk_state = "正常"

            rank = int(row["rank"])
            if rank <= top3_limit:
                if not trend_confirmed and (
                    row.get("trend_state") == "空头"
                    or float(row.get("momentum_20d") or 0) <= 0
                ):
                    rotation_signal, signal_tone = "相对防御", "neutral"
                elif overheated:
                    rotation_signal, signal_tone = "领先过热", "hot"
                elif trend_confirmed and top3_rate >= 60:
                    rotation_signal, signal_tone = "确认领先", "leading"
                elif rank_change_5d >= 3:
                    rotation_signal, signal_tone = "加速上行", "strong"
                else:
                    rotation_signal, signal_tone = "新晋观察", "neutral"
            elif rank <= min(6, len(rows)):
                if overheated:
                    rotation_signal, signal_tone = "过热观察", "hot"
                elif row.get("trend_state") == "空头" or float(row.get("momentum_20d") or 0) < 0:
                    rotation_signal, signal_tone = "弱势回避", "avoid"
                elif trend_confirmed and rank_change_5d >= 2:
                    rotation_signal, signal_tone = "转强观察", "strong"
                elif trend_confirmed:
                    rotation_signal, signal_tone = "趋势跟随", "strong"
                else:
                    rotation_signal, signal_tone = "中性等待", "neutral"
            elif row.get("trend_state") == "空头" or float(row.get("momentum_20d") or 0) < 0:
                rotation_signal, signal_tone = "弱势回避", "avoid"
            else:
                rotation_signal, signal_tone = "中性等待", "neutral"

            if rotation_signal == "确认领先" and persistence_score >= 70:
                confidence = "high"
            elif rank <= top5_limit and trend_confirmed and not overheated:
                confidence = "medium"
            else:
                confidence = "low"

            row.update({
                "history_sample_days": sample_days,
                "leader_days_20d": leader_days,
                "top3_days_20d": top3_days,
                "top5_days_20d": top5_days,
                "top3_rate_20d": _round(top3_rate),
                "average_rank_20d": _round(average_rank),
                "rank_change_5d": rank_change_5d,
                "persistence_score": _round(persistence_score),
                "trend_confirmed": trend_confirmed,
                "overheated": overheated,
                "risk_state": risk_state,
                "rotation_signal": rotation_signal,
                "signal_tone": signal_tone,
                "confirmation_level": confidence,
            })

    @staticmethod
    def _rotation_environment(
        rows: Sequence[Mapping[str, Any]],
        summary: Mapping[str, Any],
    ) -> Dict[str, Any]:
        leader = rows[0]
        score_gap = (
            max(float(leader["total_score"]) - float(rows[1]["total_score"]), 0.0)
            if len(rows) > 1 else 0.0
        )
        if leader.get("overheated"):
            environment = "高位拥挤"
        elif int(summary.get("rotation_changes_20d") or 0) >= 8:
            environment = "快速轮动"
        elif len(rows) > 1 and score_gap < 3:
            environment = "双强竞争"
        elif leader.get("rotation_signal") == "确认领先" and int(summary.get("leader_streak_days") or 0) >= 3:
            environment = "趋势延续"
        else:
            environment = "结构轮动"
        return {
            "rotation_environment": environment,
            "leader_signal": leader.get("rotation_signal"),
            "leader_confirmation": leader.get("confirmation_level"),
            "leader_persistence_score": leader.get("persistence_score"),
            "leader_score_gap": _round(score_gap),
        }

    @staticmethod
    def _signal_distribution(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        for row in rows:
            signal = str(row.get("rotation_signal") or "中性等待")
            counts[signal] = counts.get(signal, 0) + 1
        return {
            "counts": counts,
            "confirmed_count": sum(counts.get(signal, 0) for signal in ("确认领先", "加速上行")),
            "overheated_count": sum(bool(row.get("overheated")) for row in rows),
            "avoid_count": counts.get("弱势回避", 0),
            "candidate_count": len(rows),
        }

    @staticmethod
    def _summary(
        rows: Sequence[Mapping[str, Any]],
        benchmark: Mapping[str, float | str],
        industry_rows: Sequence[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        leader = rows[0]
        positive_share = sum(float(row["momentum_20d"]) > 0 for row in rows) / len(rows)
        benchmark_return = float(benchmark["return_20d"])
        if benchmark_return > 0 and positive_share >= 0.55:
            market_style = "进攻"
        elif benchmark_return < 0 and positive_share < 0.45:
            market_style = "防御"
        else:
            market_style = "震荡"

        mean_risk = sum(float(row["factor_scores"]["risk_penalty"]) for row in rows) / len(rows)
        if mean_risk < 42:
            risk_temperature = "温和"
        elif mean_risk < 66:
            risk_temperature = "中性"
        else:
            risk_temperature = "偏热"

        top_industry = max(industry_rows, key=lambda row: float(row.get("rank_score") or 0), default={})
        return {
            "market_style": market_style,
            "leading_industry": leader["industry"],
            "leading_industry_daily": top_industry.get("name") or "暂无行业广度",
            "leading_etf": f"{leader['name']}（{leader['code']}）",
            "leading_score": leader["total_score"],
            "risk_temperature": risk_temperature,
            "positive_share": _round(positive_share * 100),
        }

    @staticmethod
    def _row_insight(
        row: Mapping[str, Any],
        rows: Sequence[Mapping[str, Any]],
        summary: Mapping[str, Any],
        warnings: Sequence[str],
    ) -> Dict[str, Any]:
        leader = rows[0]
        rank = int(row["rank"])
        if rank == 1:
            position = f"{row['industry']}居首"
        else:
            gap = max(float(leader["total_score"]) - float(row["total_score"]), 0.0)
            position = f"{row['industry']}当前排名第{rank}，距榜首 {gap:.2f} 分"
        headline = (
            f"{position}；{row['name']}综合分 {row['total_score']:.1f}。"
            f"当前市场风格为{summary['market_style']}，风险温度{summary['risk_temperature']}；"
            f"轮动确认为{row.get('rotation_signal', row.get('regime', '观察'))}。"
        )
        signal_label = str(row.get("signal_name") or row["name"])
        evidence = [
            f"价格信号来自{signal_label}：近20日动量 {row['momentum_20d']:+.2f}%，相对基准 {row['relative_20d']:+.2f}%。",
            f"{signal_label}的趋势、动量、相对强弱得分分别为 {row['factor_scores']['trend']:.1f}、{row['factor_scores']['momentum']:.1f}、{row['factor_scores']['relative_strength']:.1f}。",
            f"{signal_label}均线结构为{row.get('trend_state', '未知')}：距20日均线 {float(row.get('distance_ma20') or 0):+.2f}%，20日均线相对60日均线 {float(row.get('ma20_vs_ma60') or 0):+.2f}%。",
            f"执行标的为{row['name']}（{row['code']}），近5日量能比 {row['volume_ratio']:.2f}，成交连续性得分 {row['factor_scores']['volume_continuity']:.1f}。",
            f"拥挤/条件反转得分 {row['factor_scores']['crowding_reversal']:.1f}；该因子同时惩罚过热、放量拥挤与破位，仅奖励中期趋势内的温和回踩。",
            f"候选池中 {summary['positive_share']:.1f}% 的行业价格信号近20日上涨。",
        ]
        availability = row.get("factor_availability") or {}
        if availability.get("valuation") or availability.get("fundamental_quality"):
            evidence.append(
                f"慢因子确认：估值分位得分 {row['factor_scores']['valuation']:.1f}，"
                f"基本面质量得分 {row['factor_scores']['fundamental_quality']:.1f}；"
                f"证据日期 {row.get('slow_factor_as_of') or '未标注'}。"
            )
        if int(row.get("history_sample_days") or 0) > 0:
            evidence.append(
                f"近{row['history_sample_days']}日有 {row['top3_days_20d']} 日位列前三，"
                f"排名持续度 {row['persistence_score']:.1f}，5日排名变化 {int(row['rank_change_5d']):+d}。"
            )
        if rank == 1:
            evidence.append(
                f"近{summary.get('history_days', 0)}个交易日领先方向切换 "
                f"{summary.get('rotation_changes_20d', 0)} 次，当前领先已持续 "
                f"{summary.get('leader_streak_days', 0)} 日。"
            )
            if len(rows) > 1:
                runner_up = rows[1]
                evidence.append(
                    f"次强方向为{runner_up['industry']}，与首位相差 "
                    f"{float(leader['total_score']) - float(runner_up['total_score']):.2f} 分。"
                )
        else:
            evidence.append(
                f"当前榜首为{leader['name']}（{leader['code']}），"
                f"{row['name']}在横截面中位列第{rank}。"
            )
        risks = []
        if row.get("overheated"):
            risks.append(f"{row['name']}短线涨幅与拥挤度同时偏高，轮动状态标记为领先过热。")
        elif float(row["factor_scores"]["risk_penalty"]) >= 70:
            risks.append(f"{row['name']}的波动/拥挤惩罚偏高，追涨时需控制仓位。")
        if not availability.get("valuation") or not availability.get("fundamental_quality"):
            risks.append("估值分位或基本面缺少足够点时覆盖，本次排名仅启用可回放的量价因子。")
        if float(row["max_drawdown"]) >= 12:
            risks.append(f"{row['name']}窗口内最大回撤约 {row['max_drawdown']:.1f}%，并非低风险趋势。")
        if int(row.get("data_lag_sessions") or 0) > 0:
            risks.append(f"{row['name']}行情较基准滞后 {row['data_lag_sessions']} 个交易日。")
        if row.get("signal_mode") == "etf_fallback":
            risks.append(
                f"申万{row['industry']}指数不可用，本次价格信号已回退到 {row['name']}，行业纯度下降。"
            )
        elif int(row.get("signal_lag_sessions") or 0) > 0:
            risks.append(
                f"{signal_label}行情较基准滞后 {row['signal_lag_sessions']} 个交易日。"
            )
        if row.get("proxy_note"):
            risks.append(str(row["proxy_note"]))
        if summary["market_style"] != "进攻":
            risks.append("市场尚未形成普遍进攻状态，轮动结果更适合作为相对排序而非满仓信号。")
        risks.extend(warnings)
        if not risks:
            risks.append("排名基于点时可见证据，不代表未来收益承诺。")
        return {"headline": headline, "evidence": evidence, "risks": risks}

    @staticmethod
    def _insight(
        rows: Sequence[Mapping[str, Any]],
        summary: Mapping[str, Any],
        warnings: Sequence[str],
    ) -> Dict[str, Any]:
        """Keep the previous helper contract for callers outside the engine."""

        return RotationEngine._row_insight(rows[0], rows, summary, warnings)
