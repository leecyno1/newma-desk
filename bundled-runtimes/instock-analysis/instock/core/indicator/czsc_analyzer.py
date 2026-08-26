#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""基于官方 CZSC 引擎的缠论结构分析与 ECharts 数据适配。"""

from __future__ import annotations

import logging
from importlib import metadata
from typing import Any, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

try:
    import czsc
except ImportError as exc:  # pragma: no cover - 由调用方给出更友好的错误
    raise ImportError("缠论功能需要安装 czsc==0.10.12") from exc

try:
    import czsc.signals as czsc_signals
except ImportError:  # CZSC 1.0 将官方信号迁移到 Rust registry
    czsc_signals = None


_FREQ_MAP = {
    "daily": czsc.Freq.D,
    "day": czsc.Freq.D,
    "d": czsc.Freq.D,
    "日线": czsc.Freq.D,
    "weekly": czsc.Freq.W,
    "week": czsc.Freq.W,
    "w": czsc.Freq.W,
    "周线": czsc.Freq.W,
    "monthly": czsc.Freq.M,
    "month": czsc.Freq.M,
    "m": czsc.Freq.M,
    "月线": czsc.Freq.M,
}

_OFFICIAL_SIGNAL_RULES = (
    ("一买", "cxt_first_buy_V221126", (("di", 1),), "D{di}B_BUY1"),
    ("一卖", "cxt_first_sell_V221126", (("di", 1),), "D{di}B_SELL1"),
    (
        "二买卖（中枢）", "cxt_second_bs_V240524",
        (("di", 1), ("w", 15), ("t", 2)),
        "D{di}W{w}T{t}_第二买卖点V240524",
    ),
    (
        "二买卖（均线）", "cxt_second_bs_V230320",
        (("di", 1), ("ma_type", "SMA"), ("timeperiod", 34)),
        "D{di}#{ma_type}#{timeperiod}_BS2辅助V230320",
    ),
    (
        "三买卖", "cxt_third_bs_V230319",
        (("di", 1), ("ma_type", "SMA"), ("timeperiod", 34)),
        "D{di}#{ma_type}#{timeperiod}_BS3辅助V230319",
    ),
    (
        "三买辅助", "cxt_third_buy_V230228", (("di", 1),),
        "D{di}_三买辅助V230228",
    ),
    ("趋势买卖辅助", "cxt_bs_V240526", (), "趋势跟随_BS辅助V240526"),
)

_CZSC_PRODUCTION_VERSION = "0.10.12"
_CZSC_TESTED_VERSIONS = (_CZSC_PRODUCTION_VERSION, "1.0.0rc8")
_ANALYSIS_MODEL_VERSION = "2.2.0"


def _number(value: Any, digits: int = 4) -> float:
    """将 numpy / pandas 数值转换成可 JSON 序列化的有限浮点数。"""
    try:
        result = float(value)
        return round(result, digits) if np.isfinite(result) else 0.0
    except (TypeError, ValueError):
        return 0.0


def _date_text(value: Any) -> str:
    return pd.Timestamp(value).strftime("%Y-%m-%d")


def _czsc_version() -> str:
    """返回实际运行中的 CZSC 版本，兼容旧版未暴露 __version__ 的情况。"""
    return str(getattr(czsc, "__version__", None) or metadata.version("czsc"))


def _czsc_runtime_compatibility() -> Dict[str, Any]:
    """Describe the tested CZSC seam without blocking compatible core structures."""

    installed_version = _czsc_version()
    if czsc_signals is not None:
        official_signal_adapter = "czsc.signals-v0.10"
    elif callable(getattr(czsc, "generate_czsc_signals", None)):
        official_signal_adapter = "czsc.rust-registry-v1"
    else:
        official_signal_adapter = "unavailable"
    official_signals_available = official_signal_adapter != "unavailable"
    return {
        "production_version": _CZSC_PRODUCTION_VERSION,
        "tested_versions": list(_CZSC_TESTED_VERSIONS),
        "installed_version": installed_version,
        "tested": installed_version in _CZSC_TESTED_VERSIONS,
        "mode": "full" if official_signals_available else "structure-only",
        "official_signal_adapter": official_signal_adapter,
        "official_signals_available": official_signals_available,
        "release_policy": "stable-pinned",
    }


def _official_signal_result(
    *, label: str, function_name: str, key: Any, value: Any
) -> Dict[str, Any]:
    signal = str(value).split("_", 1)[0]
    active = signal not in {"", "其他", "任意", "0"}
    side = "buy" if "买" in signal or "看多" in signal else (
        "sell" if "卖" in signal or "看空" in signal else "neutral"
    )
    return {
        "label": label,
        "function": function_name,
        "key": str(key),
        "value": str(value),
        "signal": signal,
        "side": side,
        "active": active,
        "source": "czsc_official",
    }


def _legacy_official_czsc_signals(czsc_obj: Any) -> List[Dict[str, Any]]:
    """Execute the CZSC 0.10 Python signal functions."""

    results: List[Dict[str, Any]] = []
    for label, function_name, kwargs_items, _ in _OFFICIAL_SIGNAL_RULES:
        function = getattr(czsc_signals, function_name, None)
        if not callable(function):
            logging.warning("CZSC 官方信号函数不可用: %s", function_name)
            continue
        try:
            raw_signals = function(czsc_obj, **dict(kwargs_items))
        except Exception as exc:  # 单个官方信号失败不应中断结构分析
            logging.warning("CZSC 官方信号 %s 计算失败: %s", function_name, exc)
            continue
        for key, value in raw_signals.items():
            results.append(_official_signal_result(
                label=label, function_name=function_name, key=key, value=value
            ))
    return results


def _native_official_czsc_signals(
    bars: List[Any], freq_text: str
) -> List[Dict[str, Any]]:
    """Execute the CZSC 1.0 Rust signal registry in one batch."""

    generate = getattr(czsc, "generate_czsc_signals", None)
    if not callable(generate):
        return []
    configs = []
    for _, function_name, kwargs_items, _ in _OFFICIAL_SIGNAL_RULES:
        configs.append({
            "name": function_name,
            "freq": freq_text,
            **dict(kwargs_items),
        })
    try:
        records = generate(
            bars,
            configs,
            init_n=max(len(bars) - 1, 1),
            df=False,
        )
    except Exception as exc:
        logging.warning("CZSC Rust registry 官方信号计算失败: %s", exc)
        return []
    if not records:
        return []

    latest = records[-1]
    results: List[Dict[str, Any]] = []
    for label, function_name, kwargs_items, native_key_template in _OFFICIAL_SIGNAL_RULES:
        kwargs = dict(kwargs_items)
        key = f"{freq_text}_{native_key_template.format(**kwargs)}"
        if key not in latest:
            logging.warning("CZSC Rust registry 未返回官方信号字段: %s", key)
            continue
        results.append(_official_signal_result(
            label=label,
            function_name=function_name,
            key=key,
            value=latest[key],
        ))
    return results


def _official_czsc_signals(
    czsc_obj: Any, bars: List[Any], freq_text: str
) -> List[Dict[str, Any]]:
    """Execute official signals through the available CZSC adapter."""

    if czsc_signals is not None:
        return _legacy_official_czsc_signals(czsc_obj)
    if callable(getattr(czsc, "generate_czsc_signals", None)):
        return _native_official_czsc_signals(bars, freq_text)
    logging.warning("当前 CZSC 版本未提供兼容的官方信号适配器")
    return []


def build_czsc_insight(result: Dict[str, Any]) -> Dict[str, Any]:
    """把底层结构数据整理成前端和选股任务都能复用的可解释结论。"""
    if not result.get("success"):
        return {
            "bias": "unknown", "headline": "缠论结构尚未形成有效结论",
            "evidence": [], "key_levels": [], "risk_flags": [result.get("error", "分析失败")],
            "recent_signals": [],
        }

    summary = result.get("summary", {})
    trend = result.get("trend", "sideways")
    strength = float(result.get("trend_strength", 0) or 0)
    centers = result.get("zs_list", [])
    bis = result.get("bi_list", [])
    unfinished = result.get("unfinished_direction", "none")
    structure_evidence = result.get("evidence", {})
    stability = structure_evidence.get("structure_stability", {})
    latest_change = structure_evidence.get("latest_structure_change", {})
    input_quality = structure_evidence.get("input_quality", {})
    trend_text = {"up": "上行", "down": "下行", "sideways": "震荡"}.get(trend, "震荡")
    unfinished_text = {"up": "向上", "down": "向下", "none": "未形成"}.get(unfinished, "未形成")
    bias = {"up": "bullish", "down": "bearish"}.get(trend, "neutral")

    if trend == "up":
        headline = "笔结构保持上行，重点观察最近中枢上沿能否转化为支撑"
    elif trend == "down":
        headline = "笔结构仍处下行，出现底分型并重新站回中枢前宜控制风险"
    else:
        headline = "当前结构以震荡为主，等待价格有效脱离最近中枢"

    official_compatibility = result.get("engine", {}).get("compatibility", {})
    official_signals_available = official_compatibility.get(
        "official_signals_available", True
    )
    official_signals = [x for x in result.get("official_signals", []) if x.get("active")]
    official_text = "、".join(dict.fromkeys(x["signal"] for x in official_signals)) or (
        "无" if official_signals_available else "适配器不可用"
    )
    evidence = [
        f"已识别 {summary.get('fx_count', 0)} 个分型、{summary.get('bi_count', 0)} 笔、{summary.get('zs_count', 0)} 个中枢。",
        f"结构方向为{trend_text}，强度 {strength:.1f}/100，未完成笔方向为{unfinished_text}。",
        f"CZSC 官方当前信号为{official_text}；项目启发式历史买点 {summary.get('buy_points', 0)} 个、卖点 {summary.get('sell_points', 0)} 个。",
    ]
    stability_text = {
        "strong": "较强",
        "moderate": "中等",
        "forming": "形成中",
        "insufficient": "证据不足",
    }.get(stability.get("state"), "未知")
    if stability:
        evidence.append(
            f"结构稳定性为{stability_text}（启发式 {stability.get('score', 0)}/100）；"
            f"最近确认笔距当前 {stability.get('bars_since_last_confirmed_stroke', '--')} 根 K 线。"
        )
    if latest_change:
        evidence.append(
            f"最近结构变化：{latest_change.get('date', '--')} "
            f"{latest_change.get('label', '结构更新')}，确认级别为{latest_change.get('confirmation', 'derived')}。"
        )
    if input_quality:
        evidence.append(
            f"输入质量 {input_quality.get('state', 'unknown')}："
            f"{input_quality.get('normalized_rows', 0)}/{input_quality.get('source_rows', 0)} 根有效，"
            f"疑似大时间间隔 {input_quality.get('large_gap_count', 0)} 处。"
        )

    key_levels: List[Dict[str, Any]] = []
    if centers:
        latest_center = centers[-1]
        key_levels.extend([
            {"label": "最近中枢上沿", "value": _number(latest_center["upper"]), "role": "resistance"},
            {"label": "最近中枢中轴", "value": _number(latest_center["center"]), "role": "pivot"},
            {"label": "最近中枢下沿", "value": _number(latest_center["lower"]), "role": "support"},
        ])
    if bis:
        latest_bi = bis[-1]
        key_levels.extend([
            {"label": "最近一笔高点", "value": _number(latest_bi["high"]), "role": "resistance"},
            {"label": "最近一笔低点", "value": _number(latest_bi["low"]), "role": "support"},
        ])
    key_levels.append({"label": "最新收盘", "value": _number(result.get("latest_close")), "role": "last"})

    risk_flags: List[str] = []
    if not centers:
        risk_flags.append("样本内尚未形成有效中枢，结构稳定性有限。")
    if strength < 35:
        risk_flags.append("趋势强度偏低，结构信号容易在震荡中失效。")
    if trend == "up" and unfinished == "down":
        risk_flags.append("上行结构中未完成笔向下，短线仍有回撤确认需求。")
    elif trend == "down" and unfinished == "up":
        risk_flags.append("下行结构中未完成笔向上，当前反弹尚未完成反转确认。")
    if not result.get("buy_points") and not result.get("sell_points"):
        risk_flags.append("当前样本未出现可重复确认的买卖点，不宜把趋势判断等同于交易指令。")
    if not official_signals_available:
        risk_flags.append(
            "当前 CZSC 版本未接入兼容的官方信号适配器；结构分析仍可用，当前提示降级为项目启发式。"
        )
    elif not official_signals:
        risk_flags.append("CZSC 官方当前买卖点规则未触发；页面中的历史标记仅为项目启发式结构提示。")
    if input_quality.get("state") == "partial":
        risk_flags.append("输入数据存在剔除行或疑似大时间间隔；间隔识别未接入交易所日历，需结合停牌与节假日复核。")
    if not risk_flags:
        risk_flags.append("缠论结构会随新增 K 线重绘，请结合成交量、基本面与仓位纪律复核。")

    recent_signals = [{
        "time": result.get("end_date"),
        "type": item["signal"],
        "side": item["side"],
        "level": result.get("freq", "--"),
        "price": _number(result.get("latest_close")),
        "score": "--",
        "description": f"CZSC 官方信号：{item['label']}（{item['function']}）",
        "source": "czsc_official",
    } for item in official_signals]
    for item in sorted(result.get("buy_points", []) + result.get("sell_points", []),
                       key=lambda x: x.get("date", ""), reverse=True)[:12]:
        side = "buy" if "买" in item.get("type", "") else "sell"
        recent_signals.append({
            "time": item.get("date"), "type": item.get("type", "--"), "side": side,
            "level": result.get("freq", "--"), "price": _number(item.get("price")),
            "score": int(item.get("score", 0) or 0),
            "description": f"项目启发式：{item.get('reason', '')}",
            "source": "instock_heuristic",
        })

    return {
        "bias": bias, "headline": headline, "evidence": evidence,
        "key_levels": key_levels, "risk_flags": risk_flags, "recent_signals": recent_signals,
    }


class CZSCAnalyzer:
    """把项目中的 OHLCV DataFrame 转换为 CZSC 的分型、笔、中枢和买卖点。"""

    def __init__(self, max_bi_num: int = 100):
        self.max_bi_num = max(20, int(max_bi_num))
        self.data: Optional[pd.DataFrame] = None
        self.czsc_obj = None
        self.result: Dict[str, Any] = {}

    @staticmethod
    def _normalize_data(data: pd.DataFrame) -> pd.DataFrame:
        if data is None or not isinstance(data, pd.DataFrame) or data.empty:
            raise ValueError("K线数据为空")

        source_attrs = dict(data.attrs)
        frame = data.copy()
        source_rows = len(frame)
        frame = frame.rename(columns={
            "日期": "date", "时间": "date", "datetime": "date", "dt": "date",
            "开盘": "open", "收盘": "close", "最高": "high", "最低": "low",
            "成交量": "volume", "vol": "volume", "成交额": "amount",
            "股票代码": "symbol", "code": "symbol",
        })
        required = ["date", "open", "close", "high", "low", "volume"]
        missing = [name for name in required if name not in frame.columns]
        if missing:
            raise ValueError(f"K线数据缺少字段: {', '.join(missing)}")

        if "amount" not in frame.columns:
            frame["amount"] = 0.0
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        for name in ["open", "close", "high", "low", "volume", "amount"]:
            frame[name] = pd.to_numeric(frame[name], errors="coerce")
        source_was_sorted = bool(frame["date"].dropna().is_monotonic_increasing)
        invalid_required_rows = int(frame[required].isna().any(axis=1).sum())
        frame = frame.dropna(subset=required)
        duplicate_dates_removed = int(frame.duplicated(subset=["date"], keep="last").sum())
        frame = frame.sort_values("date")
        frame = frame.drop_duplicates(subset=["date"], keep="last").reset_index(drop=True)
        positive_mask = (frame["open"] > 0) & (frame["close"] > 0)
        nonpositive_rows_removed = int((~positive_mask).sum())
        frame = frame[positive_mask].copy()
        frame["high"] = frame[["open", "close", "high"]].max(axis=1)
        frame["low"] = frame[["open", "close", "low"]].min(axis=1)
        frame["volume"] = frame["volume"].clip(lower=0).fillna(0)
        # VibeDesk may return an integer amount column even when missing values
        # need to be reconstructed from floating-point close * volume.
        frame["amount"] = frame["amount"].clip(lower=0).fillna(0).astype(float)
        reconstruct_amount = frame["amount"] <= 0
        reconstructed_amount_rows = int(reconstruct_amount.sum())
        frame.loc[reconstruct_amount, "amount"] = (
            frame.loc[reconstruct_amount, "close"]
            * frame.loc[reconstruct_amount, "volume"]
        )
        if len(frame) < 20:
            raise ValueError(f"有效K线不足20根，当前仅 {len(frame)} 根")
        frame = frame.reset_index(drop=True)
        frame.attrs.update(source_attrs)
        frame.attrs["normalization_evidence"] = {
            "source_rows": source_rows,
            "normalized_rows": len(frame),
            "rows_removed": max(source_rows - len(frame), 0),
            "invalid_required_rows": invalid_required_rows,
            "duplicate_dates_removed": duplicate_dates_removed,
            "nonpositive_rows_removed": nonpositive_rows_removed,
            "reconstructed_amount_rows": reconstructed_amount_rows,
            "source_was_sorted": source_was_sorted,
        }
        return frame

    @staticmethod
    def _resolve_freq(freq: Any):
        if isinstance(freq, czsc.Freq):
            return freq
        key = str(freq or "daily").strip().lower()
        if key not in _FREQ_MAP:
            raise ValueError(f"不支持的周期: {freq}")
        return _FREQ_MAP[key]

    @staticmethod
    def _build_centers(bis: List[Any]) -> List[Dict[str, Any]]:
        """以三个连续笔为起点，向后扩展价格区间仍有重叠的中枢。"""
        centers: List[Dict[str, Any]] = []
        index = 0
        while index + 2 < len(bis):
            seed = bis[index:index + 3]
            zs = czsc.ZS(seed)
            # CZSC 0.10.x 的底层 ZS 对象在少数相邻笔组合中会给出
            # ``is_valid=True``，但 zg / zd 已经没有正的价格重叠区间。
            # 中枢对外输出前再次按三笔高低点显式校验，避免上下沿倒置。
            upper = min(float(item.high) for item in seed)
            lower = max(float(item.low) for item in seed)
            if not zs.is_valid or lower >= upper:
                index += 1
                continue

            end_index = index + 2
            while end_index + 1 < len(bis):
                next_bi = bis[end_index + 1]
                if float(next_bi.high) < lower or float(next_bi.low) > upper:
                    break
                end_index += 1

            group = bis[index:end_index + 1]
            centers.append({
                "start_date": _date_text(group[0].fx_a.dt),
                "end_date": _date_text(group[-1].fx_b.dt),
                "upper": _number(upper),
                "lower": _number(lower),
                "center": _number((upper + lower) / 2),
                "highest": _number(max(float(x.high) for x in group)),
                "lowest": _number(min(float(x.low) for x in group)),
                "bi_count": len(group),
                "start_bi": index,
                "end_bi": end_index,
            })
            index = end_index + 1
        return centers

    @staticmethod
    def _center_before(centers: Iterable[Dict[str, Any]], bi_index: int):
        valid = [x for x in centers if x["start_bi"] < bi_index]
        return valid[-1] if valid else None

    @classmethod
    def _build_trade_points(cls, bis: List[Any], centers: List[Dict[str, Any]]) -> tuple:
        buy_points: List[Dict[str, Any]] = []
        sell_points: List[Dict[str, Any]] = []
        for index, bi in enumerate(bis):
            if index < 2:
                continue
            previous_same = bis[index - 2]
            center = cls._center_before(centers, index)
            direction_up = bi.direction == czsc.Direction.Up
            power_now = max(float(bi.power_price), 1e-9)
            power_previous = max(float(previous_same.power_price), 1e-9)
            weaker = power_now <= power_previous * 0.9

            if direction_up:
                new_extreme = float(bi.high) >= float(previous_same.high)
                outside_center = bool(center and float(bi.fx_b.fx) >= center["upper"])
                if weaker and (new_extreme or outside_center):
                    score = min(100, 60 + (15 if new_extreme else 0) + (15 if outside_center else 0))
                    sell_points.append({
                        "date": _date_text(bi.fx_b.dt), "price": _number(bi.fx_b.fx),
                        "type": "类一卖" if new_extreme and outside_center else "类卖点",
                        "score": score, "reason": "向上笔创新高/离开中枢且力度衰减",
                        "bi_index": index, "source": "instock_heuristic",
                    })
            else:
                new_extreme = float(bi.low) <= float(previous_same.low)
                outside_center = bool(center and float(bi.fx_b.fx) <= center["lower"])
                if weaker and (new_extreme or outside_center):
                    score = min(100, 60 + (15 if new_extreme else 0) + (15 if outside_center else 0))
                    buy_points.append({
                        "date": _date_text(bi.fx_b.dt), "price": _number(bi.fx_b.fx),
                        "type": "类一买" if new_extreme and outside_center else "类买点",
                        "score": score, "reason": "向下笔创新低/离开中枢且力度衰减",
                        "bi_index": index, "source": "instock_heuristic",
                    })
        return buy_points, sell_points

    @staticmethod
    def _trend(frame: pd.DataFrame, bis: List[Any]) -> tuple:
        closes = frame["close"].tail(min(60, len(frame))).astype(float).to_numpy()
        x = np.arange(len(closes), dtype=float)
        slope, intercept = np.polyfit(x, closes, 1)
        fitted = slope * x + intercept
        residual = float(np.square(closes - fitted).sum())
        total = float(np.square(closes - closes.mean()).sum())
        r_squared = max(0.0, min(1.0, 1 - residual / total)) if total > 0 else 0.0
        normalized_slope = slope * len(closes) / max(float(closes.mean()), 1e-9)

        structure = "sideways"
        if len(bis) >= 4:
            ups = [x for x in bis[-6:] if x.direction == czsc.Direction.Up]
            downs = [x for x in bis[-6:] if x.direction == czsc.Direction.Down]
            higher = len(ups) >= 2 and len(downs) >= 2 and ups[-1].high > ups[-2].high and downs[-1].low > downs[-2].low
            lower = len(ups) >= 2 and len(downs) >= 2 and ups[-1].high < ups[-2].high and downs[-1].low < downs[-2].low
            if higher:
                structure = "up"
            elif lower:
                structure = "down"

        if structure == "sideways":
            if normalized_slope > 0.08 and r_squared >= 0.25:
                structure = "up"
            elif normalized_slope < -0.08 and r_squared >= 0.25:
                structure = "down"
        structure_bonus = 25 if structure != "sideways" else 0
        strength = min(100, abs(normalized_slope) * 180 + r_squared * 45 + structure_bonus)
        return structure, round(strength, 1), round(normalized_slope, 4), round(r_squared, 4)

    @staticmethod
    def _input_quality_evidence(frame: pd.DataFrame, freq_value: Any) -> Dict[str, Any]:
        normalization = dict(frame.attrs.get("normalization_evidence") or {})
        frequency = getattr(freq_value, "value", str(freq_value))
        threshold_days = {
            getattr(czsc.Freq.D, "value", "日线"): 12,
            getattr(czsc.Freq.W, "value", "周线"): 21,
            getattr(czsc.Freq.M, "value", "月线"): 70,
        }.get(frequency, 12)
        gaps: List[Dict[str, Any]] = []
        dates = frame["date"].reset_index(drop=True)
        for index in range(1, len(dates)):
            gap_days = int((dates.iloc[index] - dates.iloc[index - 1]).days)
            if gap_days > threshold_days:
                gaps.append({
                    "start_date": _date_text(dates.iloc[index - 1]),
                    "end_date": _date_text(dates.iloc[index]),
                    "calendar_days": gap_days,
                })
        rows_removed = int(normalization.get("rows_removed") or 0)
        state = "partial" if rows_removed or gaps else "clean"
        return {
            "method": "calendar-gap-screen-v1",
            "state": state,
            **normalization,
            "frequency": frequency,
            "large_gap_threshold_days": threshold_days,
            "large_gap_count": len(gaps),
            "largest_gap_days": max((item["calendar_days"] for item in gaps), default=0),
            "recent_large_gaps": gaps[-8:],
            "limitations": [
                "calendar_gap_detection_does_not_use_exchange_calendar",
                "large_gaps_may_include_suspensions_or_exchange_holidays",
            ],
        }

    @staticmethod
    def _structure_evidence(frame: pd.DataFrame, result: Dict[str, Any]) -> Dict[str, Any]:
        bis = result.get("bi_list", [])
        centers = result.get("zs_list", [])
        input_quality = result.get("input_quality", {})
        last_bi = bis[-1] if bis else None
        date_positions = {
            _date_text(value): index for index, value in enumerate(frame["date"].tolist())
        }
        bars_since_last_bi = (
            len(frame) - 1 - date_positions.get(last_bi["end_date"], len(frame) - 1)
            if last_bi else len(frame)
        )

        score = 0
        reasons: List[str] = []
        if len(bis) >= 8:
            score += 35
            reasons.append("至少 8 笔提供了连续结构证据")
        elif len(bis) >= 4:
            score += 25
            reasons.append("至少 4 笔形成了基础结构证据")
        elif len(bis) >= 2:
            score += 12
            reasons.append("确认笔数量仍少")
        else:
            reasons.append("确认笔不足 2 笔")
        if centers:
            score += min(25, 15 + (len(centers) - 1) * 5)
            reasons.append(f"样本内存在 {len(centers)} 个派生中枢")
        else:
            reasons.append("样本内尚无有效中枢")
        if last_bi:
            if int(last_bi.get("length") or 0) >= 7:
                score += 12
                reasons.append("最近确认笔长度不少于 7 根 K 线")
            if float(last_bi.get("rsq") or 0) >= 0.5:
                score += 13
                reasons.append("最近确认笔拟合度不低于 0.5")
            if bars_since_last_bi <= 8:
                score += 15
                reasons.append("最近确认笔仍接近当前价格边缘")
            elif bars_since_last_bi > 15:
                score -= 10
                reasons.append("未完成结构已超过 15 根 K 线")
        conflict = (
            result.get("trend") == "up" and result.get("unfinished_direction") == "down"
        ) or (
            result.get("trend") == "down" and result.get("unfinished_direction") == "up"
        )
        if conflict:
            score -= 10
            reasons.append("未完成笔方向与当前趋势判断相反")
        if input_quality.get("state") == "partial":
            score -= 10
            reasons.append("输入质量证据为 partial")
        score = max(0, min(100, int(score)))
        stability_state = (
            "strong" if score >= 75 else
            "moderate" if score >= 50 else
            "forming" if score >= 25 else
            "insufficient"
        )

        changes: List[Dict[str, Any]] = []
        if result.get("fx_list"):
            latest_fx = result["fx_list"][-1]
            changes.append({
                "kind": "fractal_observed",
                "label": f"{latest_fx.get('type_cn', '分型')}出现",
                "date": latest_fx["date"],
                "price": latest_fx.get("price"),
                "confirmation": "observed",
            })
        if last_bi:
            direction_text = "向上笔确认" if last_bi.get("direction") == "up" else "向下笔确认"
            changes.append({
                "kind": "stroke_confirmed",
                "label": direction_text,
                "date": last_bi["end_date"],
                "price": last_bi.get("end_price"),
                "direction": last_bi.get("direction"),
                "confirmation": "confirmed",
            })
        if centers:
            latest_center = centers[-1]
            changes.append({
                "kind": "center_derived",
                "label": "最近中枢更新",
                "date": latest_center["end_date"],
                "price": latest_center.get("center"),
                "confirmation": "derived",
            })
        priority = {"fractal_observed": 1, "center_derived": 2, "stroke_confirmed": 3}
        changes.sort(key=lambda item: (item["date"], priority.get(item["kind"], 0)))
        latest_change = dict(changes[-1]) if changes else {}
        if latest_change:
            latest_change["bars_ago"] = max(
                len(frame) - 1 - date_positions.get(latest_change["date"], len(frame) - 1),
                0,
            )
            latest_change["repainting_possible"] = True

        return {
            "schema_version": "1.0",
            "method": "instock-czsc-structure-evidence-v1",
            "structure_stability": {
                "state": stability_state,
                "score": score,
                "heuristic": True,
                "confirmed_strokes": len(bis),
                "derived_centers": len(centers),
                "bars_since_last_confirmed_stroke": bars_since_last_bi,
                "reasons": reasons,
                "limitations": [
                    "stability_score_is_instock_heuristic_not_official_czsc_signal",
                    "unfinished_structure_can_repaint_with_new_bars",
                ],
            },
            "latest_structure_change": latest_change,
            "recent_structure_changes": changes[-6:],
            "input_quality": input_quality,
        }

    def analyze_kline(self, data: pd.DataFrame, symbol: Optional[str] = None, freq: Any = "daily") -> Dict[str, Any]:
        """执行分析；返回值仅包含可 JSON 序列化的数据。"""
        try:
            frame = self._normalize_data(data)
            freq_value = self._resolve_freq(freq)
            if not symbol:
                symbol = str(frame["symbol"].iloc[-1]) if "symbol" in frame.columns else "UNKNOWN"
            symbol = str(symbol).split(".")[0]

            bars = [
                czsc.RawBar(
                    symbol=symbol, id=index, dt=row.date.to_pydatetime(), freq=freq_value,
                    open=float(row.open), close=float(row.close), high=float(row.high), low=float(row.low),
                    vol=float(row.volume), amount=float(row.amount),
                )
                for index, row in frame.iterrows()
            ]
            czsc_obj = czsc.CZSC(bars, max_bi_num=self.max_bi_num)
            bis = list(czsc_obj.finished_bis)
            fractals = [{
                "date": _date_text(fx.dt),
                "type": "top" if fx.mark.value == "顶分型" else "bottom",
                "type_cn": fx.mark.value,
                "price": _number(fx.fx), "high": _number(fx.high), "low": _number(fx.low),
            } for fx in czsc_obj.fx_list]
            bi_list = [{
                "start_date": _date_text(bi.fx_a.dt), "end_date": _date_text(bi.fx_b.dt),
                "start_price": _number(bi.fx_a.fx), "end_price": _number(bi.fx_b.fx),
                "direction": "up" if bi.direction == czsc.Direction.Up else "down",
                "direction_cn": bi.direction.value,
                "high": _number(bi.high), "low": _number(bi.low),
                "power_price": _number(bi.power_price), "power_volume": _number(bi.power_volume, 0),
                "change": _number(bi.change), "length": int(bi.length), "rsq": _number(bi.rsq),
            } for bi in bis]
            centers = self._build_centers(bis)
            buy_points, sell_points = self._build_trade_points(bis, centers)
            official_signals = _official_czsc_signals(
                czsc_obj, bars, freq_value.value
            )
            runtime_compatibility = _czsc_runtime_compatibility()
            active_official_signals = [x for x in official_signals if x["active"]]
            trend, strength, slope, r_squared = self._trend(frame, bis)
            heuristic_latest_signal = "无"
            trade_points = sorted(buy_points + sell_points, key=lambda x: x["date"])
            if trade_points:
                heuristic_latest_signal = trade_points[-1]["type"]
            official_latest_signal = "、".join(dict.fromkeys(
                item["signal"] for item in active_official_signals
            )) or "无"
            latest_signal = official_latest_signal if active_official_signals else heuristic_latest_signal
            signal_source = "czsc_official" if active_official_signals else "instock_heuristic"

            self.data = frame
            self.czsc_obj = czsc_obj
            self.result = {
                "success": True, "symbol": symbol, "freq": freq_value.value,
                "engine": {
                    "name": "czsc",
                    "version": _czsc_version(),
                    "analysis_model": "instock-czsc",
                    "analysis_version": _ANALYSIS_MODEL_VERSION,
                    "compatibility": runtime_compatibility,
                },
                "start_date": _date_text(frame.iloc[0]["date"]),
                "end_date": _date_text(frame.iloc[-1]["date"]),
                "latest_close": _number(frame.iloc[-1]["close"]),
                "trend": trend, "trend_strength": strength,
                "normalized_slope": slope, "trend_r_squared": r_squared,
                "fx_list": fractals, "bi_list": bi_list, "zs_list": centers,
                "buy_points": buy_points, "sell_points": sell_points,
                "official_signals": official_signals,
                "official_latest_signal": official_latest_signal,
                "heuristic_latest_signal": heuristic_latest_signal,
                "latest_signal": latest_signal, "signal_source": signal_source,
                "unfinished_direction": (
                    "up" if czsc_obj.ubi and czsc_obj.ubi.get("direction") == czsc.Direction.Up
                    else "down" if czsc_obj.ubi else "none"
                ),
            }
            self.result["input_quality"] = self._input_quality_evidence(frame, freq_value)
            self.result["evidence"] = self._structure_evidence(frame, self.result)
            self.result["summary"] = get_czsc_signals_summary(self.result)
            self.result["insight"] = build_czsc_insight(self.result)
            return self.result
        except Exception as exc:
            logging.exception("CZSC K线分析失败")
            self.data = None
            self.czsc_obj = None
            self.result = {"success": False, "error": str(exc)}
            return self.result

    def get_echarts_option(self) -> Dict[str, Any]:
        if not self.result.get("success") or self.data is None:
            raise RuntimeError(self.result.get("error", "请先完成缠论分析"))

        frame = self.data
        result = self.result
        dates = frame["date"].dt.strftime("%Y-%m-%d").tolist()
        candles = [[_number(row.open), _number(row.close), _number(row.low), _number(row.high)]
                   for row in frame.itertuples()]
        volumes = [{
            "value": _number(row.volume, 0),
            "itemStyle": {"color": "#ef5350" if row.close >= row.open else "#26a69a"},
        } for row in frame.itertuples()]
        top_fx = [[x["date"], x["price"]] for x in result["fx_list"] if x["type"] == "top"]
        bottom_fx = [[x["date"], x["price"]] for x in result["fx_list"] if x["type"] == "bottom"]
        bi_points: List[List[Any]] = []
        for index, bi in enumerate(result["bi_list"]):
            if index == 0:
                bi_points.append([bi["start_date"], bi["start_price"]])
            bi_points.append([bi["end_date"], bi["end_price"]])
        mark_areas = [[
            {"name": f"中枢{index + 1}", "xAxis": zs["start_date"], "yAxis": zs["lower"]},
            {"xAxis": zs["end_date"], "yAxis": zs["upper"]},
        ] for index, zs in enumerate(result["zs_list"])]

        return {
            "title": {"text": f"{result['symbol']} 缠论分析", "subtext": (
                f"{result['freq']} · 趋势 {result['trend']} · 强度 {result['trend_strength']}"
            )},
            "animation": False,
            "tooltip": {"trigger": "axis", "axisPointer": {"type": "cross"}},
            "legend": {"data": ["K线", "笔", "顶分型", "底分型", "买点", "卖点", "成交量"]},
            "axisPointer": {"link": [{"xAxisIndex": "all"}]},
            "grid": [
                {"left": "7%", "right": "4%", "top": 70, "height": "60%"},
                {"left": "7%", "right": "4%", "top": "76%", "height": "13%"},
            ],
            "xAxis": [
                {"type": "category", "data": dates, "boundaryGap": False, "axisLine": {"onZero": False},
                 "min": "dataMin", "max": "dataMax"},
                {"type": "category", "gridIndex": 1, "data": dates, "boundaryGap": False,
                 "axisLabel": {"show": False}, "axisTick": {"show": False}},
            ],
            "yAxis": [
                {"scale": True, "splitArea": {"show": True}},
                {"scale": True, "gridIndex": 1, "splitNumber": 2, "axisLabel": {"show": False}},
            ],
            "dataZoom": [
                {"type": "inside", "xAxisIndex": [0, 1], "start": 60, "end": 100},
                {"type": "slider", "xAxisIndex": [0, 1], "top": "91%", "start": 60, "end": 100},
            ],
            "series": [
                {"name": "K线", "type": "candlestick", "data": candles,
                 "itemStyle": {"color": "#ef5350", "color0": "#26a69a", "borderColor": "#ef5350", "borderColor0": "#26a69a"},
                 "markArea": {"silent": True, "itemStyle": {"color": "rgba(255,193,7,0.16)"}, "data": mark_areas}},
                {"name": "笔", "type": "line", "data": bi_points, "showSymbol": True, "symbolSize": 5,
                 "lineStyle": {"color": "#1565c0", "width": 2}, "connectNulls": False},
                {"name": "顶分型", "type": "scatter", "data": top_fx, "symbol": "triangle", "symbolRotate": 180,
                 "symbolSize": 9, "itemStyle": {"color": "#d32f2f"}},
                {"name": "底分型", "type": "scatter", "data": bottom_fx, "symbol": "triangle",
                 "symbolSize": 9, "itemStyle": {"color": "#2e7d32"}},
                {"name": "买点", "type": "scatter", "data": [[x["date"], x["price"], x["type"]] for x in result["buy_points"]],
                 "symbol": "pin", "symbolSize": 36, "itemStyle": {"color": "#e91e63"}},
                {"name": "卖点", "type": "scatter", "data": [[x["date"], x["price"], x["type"]] for x in result["sell_points"]],
                 "symbol": "pin", "symbolSize": 36, "itemStyle": {"color": "#673ab7"}},
                {"name": "成交量", "type": "bar", "xAxisIndex": 1, "yAxisIndex": 1, "data": volumes},
            ],
            "czscSummary": result["summary"],
        }

    def get_analysis_payload(self, *, include_chart: bool = True) -> Dict[str, Any]:
        """返回面向 Web/API 的稳定数据契约，同时保留完整结构明细。"""
        if not self.result.get("success"):
            raise RuntimeError(self.result.get("error", "请先完成缠论分析"))
        payload = {
            "symbol": self.result["symbol"],
            "period": self.result["freq"],
            "start_date": self.result["start_date"],
            "end_date": self.result["end_date"],
            "latest_close": self.result["latest_close"],
            "engine": self.result["engine"],
            "summary": self.result["summary"],
            "evidence": self.result["evidence"],
            "insight": self.result["insight"],
            "structure": {
                "fractals": self.result["fx_list"],
                "strokes": self.result["bi_list"],
                "centers": self.result["zs_list"],
                "buy_points": self.result["buy_points"],
                "sell_points": self.result["sell_points"],
                "official_signals": self.result["official_signals"],
                "unfinished_direction": self.result["unfinished_direction"],
            },
            "signal_model": {
                "current_signals": (
                    "czsc_official"
                    if self.result["engine"]["compatibility"]["official_signals_available"]
                    else "unavailable"
                ),
                "fallback_current_signal": "instock_heuristic_v1",
                "historical_markers": "instock_heuristic_v1",
                "historical_markers_are_official": False,
            },
        }
        if include_chart:
            payload["chart"] = self.get_echarts_option()
        return payload


def calculate_czsc_indicators(data: pd.DataFrame, symbol: Optional[str] = None, freq: Any = "daily") -> Dict[str, Any]:
    """兼容选股作业的函数式入口。"""
    return CZSCAnalyzer().analyze_kline(data, symbol=symbol, freq=freq)


def get_czsc_signals_summary(result: Dict[str, Any]) -> Dict[str, Any]:
    """提取可直接写入选股结果表的稳定摘要字段。"""
    if not result or not result.get("success"):
        return {
            "trend": "unknown", "trend_strength": 0, "fx_count": 0, "bi_count": 0,
            "zs_count": 0, "buy_points": 0, "sell_points": 0, "latest_signal": "无",
            "official_latest_signal": "无", "heuristic_latest_signal": "无",
            "signal_source": "none", "official_signal_status": "unavailable",
        }
    return {
        "trend": result.get("trend", "sideways"),
        "trend_strength": result.get("trend_strength", 0),
        "fx_count": len(result.get("fx_list", [])),
        "bi_count": len(result.get("bi_list", [])),
        "zs_count": len(result.get("zs_list", [])),
        "buy_points": len(result.get("buy_points", [])),
        "sell_points": len(result.get("sell_points", [])),
        "latest_signal": result.get("latest_signal", "无"),
        "official_latest_signal": result.get("official_latest_signal", "无"),
        "heuristic_latest_signal": result.get("heuristic_latest_signal", "无"),
        "signal_source": result.get("signal_source", "none"),
        "official_signal_status": (
            "available"
            if result.get("engine", {}).get("compatibility", {}).get(
                "official_signals_available", False
            )
            else "unavailable"
        ),
        "latest_close": result.get("latest_close", 0),
        "unfinished_direction": result.get("unfinished_direction", "none"),
        "structure_stability": result.get("evidence", {}).get("structure_stability", {}).get("state", "insufficient"),
        "structure_stability_score": result.get("evidence", {}).get("structure_stability", {}).get("score", 0),
    }
