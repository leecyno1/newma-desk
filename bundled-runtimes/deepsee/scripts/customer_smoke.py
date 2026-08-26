#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def _fetch_json(url: str, timeout: float) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


def _find_pid_on_port(port: int) -> int | None:
    try:
        out = subprocess.check_output(
            ["lsof", f"-nPiTCP:{port}", "-sTCP:LISTEN", "-t"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=3,
        ).strip()
    except Exception:
        return None
    first = out.splitlines()[0].strip() if out else ""
    return int(first) if first.isdigit() else None


def _rss_mb(pid: int | None) -> float | None:
    if not pid:
        return None
    try:
        out = subprocess.check_output(["ps", "-p", str(pid), "-o", "rss="], text=True, timeout=3).strip()
        return round(int(out) / 1024, 1) if out else None
    except Exception:
        return None


def _load_offline_ready(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def run(args: argparse.Namespace) -> dict[str, Any]:
    base = str(args.base_url).rstrip("/")
    ready = _load_offline_ready(args.offline_ready_json)
    offline_mode = ready is not None
    health_samples: list[dict[str, Any]] = []
    errors: list[str] = []
    started = time.time()

    if ready is None:
        for idx in range(max(1, int(args.iterations))):
            try:
                health_samples.append(_fetch_json(f"{base}/api/health", args.timeout))
            except Exception as exc:
                errors.append(f"health[{idx}] {exc}")
            time.sleep(max(0.0, float(args.interval)))
        try:
            ready = _fetch_json(f"{base}/api/ready", args.timeout)
        except Exception as exc:
            ready = {"healthy": False, "error": str(exc), "checks": []}
            errors.append(f"ready {exc}")

    port = int(args.port or base.rsplit(":", 1)[-1].split("/", 1)[0] or 8001)
    pid = None if offline_mode else _find_pid_on_port(port)
    rss = None if offline_mode else _rss_mb(pid)
    max_rss = float(args.max_rss_mb)
    ready_healthy = bool(ready.get("healthy"))
    rss_ok = rss is None or rss <= max_rss
    status = "ok" if ready_healthy and rss_ok and not errors else "fail"
    report: dict[str, Any] = {
        "status": status,
        "base_url": base,
        "duration_seconds": round(time.time() - started, 2),
        "thresholds": {"max_rss_mb": max_rss},
        "process": {"pid": pid, "rss_mb": rss, "inspected": not offline_mode},
        "health_samples": health_samples,
        "ready": ready,
        "errors": errors,
    }
    if rss is not None and not rss_ok:
        report["errors"].append(f"rss_mb {rss} exceeds max_rss_mb {max_rss}")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Customer low-resource smoke test for Dasheng local deployment.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001", help="Service base URL")
    parser.add_argument("--port", type=int, default=8001, help="Local service port for RSS detection")
    parser.add_argument("--iterations", type=int, default=8, help="Number of health probes to run")
    parser.add_argument("--interval", type=float, default=0.25, help="Seconds between health probes")
    parser.add_argument("--timeout", type=float, default=5.0, help="HTTP timeout in seconds")
    parser.add_argument("--max-rss-mb", type=float, default=250.0, help="Maximum acceptable RSS memory in MB")
    parser.add_argument("--offline-ready-json", default="", help="Use an existing ready JSON file instead of HTTP")
    parser.add_argument("--output", default="", help="Write JSON report to this path")
    args = parser.parse_args(argv)
    report = run(args)
    body = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(body + "\n", encoding="utf-8")
    print(body)
    return 0 if report["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
