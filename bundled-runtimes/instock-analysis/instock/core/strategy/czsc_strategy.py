#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""InStock 缠论选股策略；结构由官方 CZSC 引擎计算。"""

from __future__ import annotations

import logging
from typing import Any, Dict, Tuple

import pandas as pd

from instock.core.indicator.czsc_analyzer import calculate_czsc_indicators


def _analyze(code_name, data: pd.DataFrame, date=None, threshold: int = 60) -> Tuple[Dict[str, Any], pd.DataFrame]:
    if data is None or not isinstance(data, pd.DataFrame) or len(data) < max(20, threshold):
        return {"success": False}, pd.DataFrame()
    frame = data.copy()
    if "日期" in frame.columns and "date" not in frame.columns:
        frame = frame.rename(columns={"日期": "date"})
    if "date" not in frame.columns:
        return {"success": False}, pd.DataFrame()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    end_date = date if date is not None else (code_name[0] if code_name else None)
    if end_date is not None:
        frame = frame[frame["date"] <= pd.Timestamp(end_date)]
    if len(frame) < max(20, threshold):
        return {"success": False}, frame
    symbol = str(code_name[1]) if code_name and len(code_name) > 1 else None
    return calculate_czsc_indicators(frame, symbol=symbol), frame


def _safe_check(checker, code_name, data, date, threshold) -> bool:
    try:
        result, frame = _analyze(code_name, data, date, threshold)
        return bool(result.get("success") and checker(result, frame))
    except Exception as exc:
        code = code_name[1] if code_name and len(code_name) > 1 else "unknown"
        logging.warning("股票 %s 的缠论策略判断失败: %s", code, exc)
        return False


def _recent_point(result: Dict[str, Any], kind: str, max_bi_distance: int = 2):
    points = result.get(kind, [])
    if not points:
        return None
    latest = points[-1]
    last_bi_index = len(result.get("bi_list", [])) - 1
    return latest if last_bi_index - latest.get("bi_index", -99) <= max_bi_distance else None


def check_czsc_comprehensive(code_name, data, date=None, threshold=60) -> bool:
    """综合结构：至少形成一个中枢，并出现较强趋势或近期结构买点。"""
    return _safe_check(
        lambda r, _: len(r["bi_list"]) >= 5 and len(r["zs_list"]) >= 1 and (
            r["trend_strength"] >= 45 or _recent_point(r, "buy_points", 2) is not None
        ), code_name, data, date, threshold,
    )


def check_czsc_buy_strategy(code_name, data, date=None, threshold=30) -> bool:
    """买点策略：最近两笔内出现底背驰类买点，且当前未完成方向向上。"""
    return _safe_check(
        lambda r, _: _recent_point(r, "buy_points", 2) is not None
        and r.get("unfinished_direction") == "up",
        code_name, data, date, threshold,
    )


def check_czsc_trend_following(code_name, data, date=None, threshold=90) -> bool:
    """趋势跟随：高低点同步抬升，趋势强度达标，价格位于最近中枢上沿。"""
    def checker(result, _):
        centers = result.get("zs_list", [])
        return bool(centers and result["trend"] == "up" and result["trend_strength"] >= 50
                    and result["latest_close"] > centers[-1]["upper"])
    return _safe_check(checker, code_name, data, date, threshold)


def check_czsc_reversal_pattern(code_name, data, date=None, threshold=60) -> bool:
    """反转策略：底背驰类买点后，未完成笔已经转为向上。"""
    return _safe_check(
        lambda r, _: _recent_point(r, "buy_points", 1) is not None
        and r.get("unfinished_direction") == "up" and r.get("trend") != "down",
        code_name, data, date, threshold,
    )


def check_czsc_consolidation_breakout(code_name, data, date=None, threshold=60) -> bool:
    """中枢突破：最近收盘价刚从最后一个中枢上沿向上突破。"""
    def checker(result, frame):
        centers = result.get("zs_list", [])
        if not centers or len(frame) < 6:
            return False
        upper = centers[-1]["upper"]
        closes = pd.to_numeric(frame["close"], errors="coerce").dropna().tail(6)
        return bool(len(closes) >= 2 and closes.iloc[-1] > upper and (closes.iloc[:-1] <= upper).any()
                    and result.get("unfinished_direction") == "up")
    return _safe_check(checker, code_name, data, date, threshold)
