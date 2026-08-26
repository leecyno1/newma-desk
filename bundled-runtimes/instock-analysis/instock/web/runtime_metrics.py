#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Low-cardinality process-local metrics for the attached analysis API."""

from __future__ import annotations

import math
import re
import time
from collections import defaultdict, deque
from threading import RLock
from typing import Any, Callable


_ROUTE_PATTERNS = (
    (re.compile(r"^/api/v1/health$"), "/api/v1/health"),
    (re.compile(r"^/api/v1/capabilities$"), "/api/v1/capabilities"),
    (re.compile(r"^/api/v1/czsc/analyses$"), "/api/v1/czsc/analyses"),
    (re.compile(r"^/api/v1/czsc/scans$"), "/api/v1/czsc/scans"),
    (re.compile(r"^/api/v1/czsc/scans/[^/]+$"), "/api/v1/czsc/scans/{scan_id}"),
    (
        re.compile(r"^/api/v1/rotations/snapshots$"),
        "/api/v1/rotations/snapshots",
    ),
    (
        re.compile(r"^/api/v1/rotations/experiments$"),
        "/api/v1/rotations/experiments",
    ),
    (
        re.compile(r"^/api/v1/rotations/supply-chain-research$"),
        "/api/v1/rotations/supply-chain-research",
    ),
    (
        re.compile(r"^/api/v1/industry-chain/research$"),
        "/api/v1/industry-chain/research",
    ),
    (
        re.compile(r"^/api/v1/stock-candidates/snapshots$"),
        "/api/v1/stock-candidates/snapshots",
    ),
    (
        re.compile(r"^/api/v1/stock-research/dossiers$"),
        "/api/v1/stock-research/dossiers",
    ),
    (
        re.compile(r"^/api/v1/strategy-validations$"),
        "/api/v1/strategy-validations",
    ),
    (
        re.compile(r"^/api/v1/event-flows$"),
        "/api/v1/event-flows",
    ),
    (
        re.compile(r"^/api/v1/research-books$"),
        "/api/v1/research-books",
    ),
    (
        re.compile(r"^/api/v1/market-workbench/snapshots$"),
        "/api/v1/market-workbench/snapshots",
    ),
    (
        re.compile(r"^/api/v1/market-maps/snapshots$"),
        "/api/v1/market-maps/snapshots",
    ),
    (
        re.compile(r"^/api/v1/technical-signals/snapshots$"),
        "/api/v1/technical-signals/snapshots",
    ),
    (
        re.compile(r"^/api/v1/analysis-snapshots/[^/]+$"),
        "/api/v1/analysis-snapshots/{snapshot_id}",
    ),
    (
        re.compile(r"^/api/v1/analysis-history$"),
        "/api/v1/analysis-history",
    ),
    (
        re.compile(r"^/api/v1/analysis-history/[^/]+$"),
        "/api/v1/analysis-history/{history_id}",
    ),
)


def metric_route(path: str) -> str:
    for pattern, template in _ROUTE_PATTERNS:
        if pattern.fullmatch(path):
            return template
    return "/api/v1/unmatched"


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(math.ceil(percentile * len(ordered)) - 1, 0)
    return round(ordered[index], 3)


class ApiMetricsRegistry:
    """Store aggregate request outcomes with a bounded latency sample."""

    def __init__(
        self,
        *,
        latency_sample_max: int = 256,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.latency_sample_max = max(16, min(int(latency_sample_max), 4096))
        self._clock = clock
        self._lock = RLock()
        self._routes: dict[str, dict[str, Any]] = {}

    def start(self) -> float:
        return self._clock()

    def record(self, method: str, path: str, status: int, started_at: float) -> None:
        route = metric_route(path)
        key = f"{str(method).upper()} {route}"
        status_code = min(max(int(status), 100), 599)
        status_class = f"{status_code // 100}xx"
        latency_ms = max((self._clock() - float(started_at)) * 1000, 0.0)
        with self._lock:
            metric = self._routes.get(key)
            if metric is None:
                metric = {
                    "requests": 0,
                    "errors": 0,
                    "server_errors": 0,
                    "status_classes": defaultdict(int),
                    "latencies": deque(maxlen=self.latency_sample_max),
                }
                self._routes[key] = metric
            metric["requests"] += 1
            metric["errors"] += int(status_code >= 400)
            metric["server_errors"] += int(status_code >= 500)
            metric["status_classes"][status_class] += 1
            metric["latencies"].append(latency_ms)

    def clear(self) -> None:
        with self._lock:
            self._routes.clear()

    def stats(self) -> dict[str, Any]:
        with self._lock:
            routes = {}
            total_requests = 0
            total_errors = 0
            total_server_errors = 0
            for key in sorted(self._routes):
                metric = self._routes[key]
                requests = int(metric["requests"])
                errors = int(metric["errors"])
                server_errors = int(metric["server_errors"])
                latencies = list(metric["latencies"])
                total_requests += requests
                total_errors += errors
                total_server_errors += server_errors
                routes[key] = {
                    "requests": requests,
                    "errors": errors,
                    "server_errors": server_errors,
                    "error_rate": round(errors / requests, 4) if requests else 0.0,
                    "status_classes": dict(sorted(metric["status_classes"].items())),
                    "latency_ms": {
                        "sample_size": len(latencies),
                        "p50": _percentile(latencies, 0.50),
                        "p95": _percentile(latencies, 0.95),
                        "max": round(max(latencies), 3) if latencies else 0.0,
                    },
                }
            return {
                "storage": "process_memory",
                "volatile": True,
                "cleared_on_restart": True,
                "route_labels": "fixed_templates",
                "observation_scope": "completed_requests_before_current_health_response",
                "latency_sample_max_per_route": self.latency_sample_max,
                "totals": {
                    "requests": total_requests,
                    "errors": total_errors,
                    "server_errors": total_server_errors,
                    "error_rate": (
                        round(total_errors / total_requests, 4) if total_requests else 0.0
                    ),
                },
                "routes": routes,
            }


_API_METRICS_REGISTRY = ApiMetricsRegistry()


def get_api_metrics_registry() -> ApiMetricsRegistry:
    return _API_METRICS_REGISTRY
