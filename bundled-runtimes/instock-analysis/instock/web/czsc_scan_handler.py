#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Cancellable process-local task resources for bounded CZSC batch scans."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from copy import deepcopy
from datetime import datetime
from threading import Event, RLock
from typing import Any, Optional

from instock.core.analysis_snapshot import normalize_as_of
from instock.core.czsc_analysis import CZSC_BAR_LIMITS, CZSC_PERIODS, CZSC_SYMBOL_PATTERN
from instock.core.czsc_batch_scanner import CZSCBatchScanner
from instock.core.market_data_provider import get_market_data_provider
from instock.web.api_contract import AnalysisApiHandler


_TERMINAL_STATUSES = {"completed", "cancelled", "failed"}


def _int_setting(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        return default
    return min(max(value, minimum), maximum)


class CZSCScanCapacityExceeded(RuntimeError):
    """Raised when the bounded task registry has no active-scan capacity."""


class CZSCScanTaskRegistry:
    """Own task lifecycle, cancellation, retention, and copy isolation."""

    def __init__(
        self,
        *,
        max_active: int = 2,
        max_entries: int = 64,
        retention_seconds: float = 3600,
        clock=time.monotonic,
    ):
        self.max_active = max(1, int(max_active))
        self.max_entries = max(self.max_active, int(max_entries))
        self.retention_seconds = max(60.0, float(retention_seconds))
        self._clock = clock
        self._lock = RLock()
        self._records: dict[str, dict[str, Any]] = {}
        self._cancel_events: dict[str, Event] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def _cleanup(self) -> None:
        now = self._clock()
        expired = [
            scan_id
            for scan_id, record in self._records.items()
            if record["status"] in _TERMINAL_STATUSES
            and now - float(record.get("_finished_monotonic") or now) >= self.retention_seconds
        ]
        for scan_id in expired:
            self._records.pop(scan_id, None)
            self._cancel_events.pop(scan_id, None)
            self._tasks.pop(scan_id, None)
        terminal_ids = [
            scan_id for scan_id, record in self._records.items()
            if record["status"] in _TERMINAL_STATUSES
        ]
        while len(self._records) > self.max_entries and terminal_ids:
            scan_id = terminal_ids.pop(0)
            self._records.pop(scan_id, None)
            self._cancel_events.pop(scan_id, None)
            self._tasks.pop(scan_id, None)

    @staticmethod
    def _public(record: dict[str, Any]) -> dict[str, Any]:
        return deepcopy({key: value for key, value in record.items() if not key.startswith("_")})

    def create(self, parameters: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._cleanup()
            active = sum(record["status"] not in _TERMINAL_STATUSES for record in self._records.values())
            if active >= self.max_active:
                raise CZSCScanCapacityExceeded("批量扫描并发已满，请稍后重试")
            scan_id = f"czsc-scan-{uuid.uuid4().hex}"
            now = datetime.now().astimezone().isoformat(timespec="seconds")
            record = {
                "scan_id": scan_id,
                "status": "queued",
                "created_at": now,
                "started_at": None,
                "completed_at": None,
                "parameters": deepcopy(parameters),
                "progress": {
                    "total": len(parameters["symbols"]),
                    "completed": 0,
                    "succeeded": 0,
                    "failed": 0,
                    "current_symbol": None,
                    "cancel_requested": False,
                },
                "result": None,
                "error": None,
            }
            cancel_event = Event()
            self._records[scan_id] = record
            self._cancel_events[scan_id] = cancel_event
            self._tasks[scan_id] = asyncio.create_task(
                self._execute(scan_id, parameters, cancel_event)
            )
            return self._public(record)

    async def _execute(
        self,
        scan_id: str,
        parameters: dict[str, Any],
        cancel_event: Event,
    ) -> None:
        with self._lock:
            record = self._records.get(scan_id)
            if record is None:
                return
            record["status"] = "cancelling" if cancel_event.is_set() else "running"
            record["started_at"] = datetime.now().astimezone().isoformat(timespec="seconds")

        def progress(value: dict[str, Any]) -> None:
            with self._lock:
                current = self._records.get(scan_id)
                if current is not None:
                    current["progress"] = deepcopy(value)
                    if cancel_event.is_set() and current["status"] == "running":
                        current["status"] = "cancelling"

        try:
            provider = get_market_data_provider()
            scanner = CZSCBatchScanner(provider, max_workers=parameters["max_workers"])
            result = await asyncio.to_thread(
                scanner.scan,
                parameters["symbols"],
                period=parameters["period"],
                bars=parameters["bars"],
                as_of=parameters["asOf"],
                cancel_event=cancel_event,
                on_progress=progress,
            )
            with self._lock:
                current = self._records.get(scan_id)
                if current is not None:
                    current["status"] = result["status"]
                    current["progress"] = deepcopy(result["progress"])
                    current["result"] = result
        except Exception as exc:  # noqa: BLE001
            logging.exception("CZSC 批量扫描任务异常")
            with self._lock:
                current = self._records.get(scan_id)
                if current is not None:
                    current["status"] = "cancelled" if cancel_event.is_set() else "failed"
                    current["error"] = str(exc) if not cancel_event.is_set() else None
        finally:
            with self._lock:
                current = self._records.get(scan_id)
                if current is not None:
                    current["completed_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
                    current["_finished_monotonic"] = self._clock()

    def get(self, scan_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            self._cleanup()
            record = self._records.get(scan_id)
            return self._public(record) if record is not None else None

    def cancel(self, scan_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            self._cleanup()
            record = self._records.get(scan_id)
            if record is None:
                return None
            if record["status"] not in _TERMINAL_STATUSES:
                self._cancel_events[scan_id].set()
                record["status"] = "cancelling"
                record["progress"]["cancel_requested"] = True
            return self._public(record)

    def clear(self) -> None:
        with self._lock:
            for event in self._cancel_events.values():
                event.set()
            self._records.clear()
            self._cancel_events.clear()
            self._tasks.clear()

    def stats(self) -> dict[str, Any]:
        """Return aggregate capacity only; task parameters and results stay private."""

        with self._lock:
            self._cleanup()
            status_counts: dict[str, int] = {}
            for record in self._records.values():
                status = str(record["status"])
                status_counts[status] = status_counts.get(status, 0) + 1
            active = sum(
                count for status, count in status_counts.items()
                if status not in _TERMINAL_STATUSES
            )
            return {
                "storage": "process_memory",
                "volatile": True,
                "entries": len(self._records),
                "max_entries": self.max_entries,
                "active": active,
                "max_active": self.max_active,
                "terminal": len(self._records) - active,
                "retention_seconds": self.retention_seconds,
                "status_counts": dict(sorted(status_counts.items())),
            }


_CZSC_SCAN_REGISTRY = CZSCScanTaskRegistry(
    max_active=_int_setting("INSTOCK_CZSC_SCAN_MAX_ACTIVE", 2, 1, 8),
    max_entries=_int_setting("INSTOCK_CZSC_SCAN_MAX_ENTRIES", 64, 8, 512),
    retention_seconds=_int_setting("INSTOCK_CZSC_SCAN_RETENTION_SECONDS", 3600, 60, 86_400),
)


def get_czsc_scan_registry() -> CZSCScanTaskRegistry:
    return _CZSC_SCAN_REGISTRY


def _parse_scan_input(handler: AnalysisApiHandler) -> tuple[Optional[dict[str, Any]], Optional[tuple[int, str, str]]]:
    if len(handler.request.body) > 32_768:
        return None, (413, "request_too_large", "批量扫描请求体不能超过 32KB")
    try:
        raw = json.loads(handler.request.body or b"{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return None, (400, "invalid_json", "请求体必须是 JSON 对象")
    if not isinstance(raw, dict):
        return None, (400, "invalid_request", "请求体必须是 JSON 对象")
    allowed = {"symbols", "period", "bars", "asOf", "maxWorkers"}
    extra = sorted(set(raw) - allowed)
    if extra:
        return None, (400, "unknown_fields", f"不支持的字段: {', '.join(extra)}")
    symbols = raw.get("symbols")
    if not isinstance(symbols, list):
        return None, (400, "invalid_symbols", "symbols 必须是股票代码数组")
    normalized_symbols = list(dict.fromkeys(str(item).strip().upper() for item in symbols))
    if not 1 <= len(normalized_symbols) <= 20:
        return None, (400, "invalid_symbols", "每次批量扫描须包含 1 至 20 个唯一代码")
    invalid = [symbol for symbol in normalized_symbols if not CZSC_SYMBOL_PATTERN.fullmatch(symbol)]
    if invalid:
        return None, (400, "invalid_symbols", f"股票代码格式错误: {', '.join(invalid[:5])}")
    period = str(raw.get("period") or "daily").strip().lower()
    if period not in CZSC_PERIODS:
        return None, (400, "invalid_period", "周期仅支持 daily、weekly、monthly")
    try:
        bars = int(raw.get("bars", 240))
    except (TypeError, ValueError):
        return None, (400, "invalid_bar_limit", "K线数量必须是整数")
    if bars not in CZSC_BAR_LIMITS:
        return None, (400, "invalid_bar_limit", "K线数量仅支持 120、240、480、800")
    try:
        max_workers = int(raw.get("maxWorkers", 4))
    except (TypeError, ValueError):
        return None, (400, "invalid_workers", "并发数必须是整数")
    if not 1 <= max_workers <= 4:
        return None, (400, "invalid_workers", "并发数仅支持 1 至 4")
    try:
        as_of = normalize_as_of(raw.get("asOf"), reject_future=True)
    except ValueError as exc:
        return None, (400, "invalid_as_of", str(exc))
    return {
        "symbols": normalized_symbols,
        "period": period,
        "bars": bars,
        "asOf": as_of,
        "max_workers": max_workers,
    }, None


class CZSCScanCollectionHandler(AnalysisApiHandler):
    """Create a bounded asynchronous batch scan resource."""

    def post(self) -> None:
        parameters, error = _parse_scan_input(self)
        if error:
            self.write_error(*error)
            return
        try:
            record = get_czsc_scan_registry().create(parameters)
        except CZSCScanCapacityExceeded as exc:
            self.set_header("Retry-After", "5")
            self.write_error(429, "scan_capacity_exceeded", str(exc))
            return
        location = f"/api/v1/czsc/scans/{record['scan_id']}"
        self.set_status(202)
        self.set_header("Location", location)
        self.write_success(record, meta={"poll": location})


class CZSCScanResourceHandler(AnalysisApiHandler):
    """Read or request cancellation of one batch scan resource."""

    def get(self, scan_id: str) -> None:
        record = get_czsc_scan_registry().get(scan_id)
        if record is None:
            self.write_error(404, "czsc_scan_not_found", "批量扫描任务不存在或已过期")
            return
        self.write_success(record)

    def delete(self, scan_id: str) -> None:
        record = get_czsc_scan_registry().cancel(scan_id)
        if record is None:
            self.write_error(404, "czsc_scan_not_found", "批量扫描任务不存在或已过期")
            return
        self.set_status(200 if record["status"] in _TERMINAL_STATUSES else 202)
        self.write_success(record)
