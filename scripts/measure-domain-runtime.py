#!/usr/bin/env python3
"""Fail fast when the integrated Research/Trading runtime becomes heavy again."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import resource
import sys
from pathlib import Path
from types import ModuleType


FORBIDDEN_MODULE_PREFIXES = (
    "ccxt",
    "fastmcp",
    "langchain",
    "langgraph",
    "llvmlite",
    "matplotlib",
    "numba",
    "openai",
    "scipy",
    "sklearn",
    "weasyprint",
)


def load_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(name, None)
        raise
    return module


def route_paths(application) -> set[str]:
    return {
        path
        for route in application.routes
        if (path := getattr(route, "path", ""))
    }


def rss_mib() -> float:
    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    bytes_value = raw if sys.platform == "darwin" else raw * 1024
    return bytes_value / 1024 / 1024


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--max-rss-mib", type=float, default=192.0)
    args = parser.parse_args()

    root = args.root.resolve()
    research_backend = root / "mod-projects" / "vibe-research" / "backend"
    trading_agent = root / "mod-projects" / "vibe-trading" / "agent"
    sys.path[:0] = [str(trading_agent), str(research_backend)]
    os.environ["NEWMA_DESK_INTEGRATED_DOMAIN_RUNTIME"] = "1"
    os.environ["VIBEDESK_INTEGRATED_DOMAIN_RUNTIME"] = "1"
    os.environ.setdefault("API_AUTH_KEY", "newma-runtime-footprint-probe")

    research = load_module(
        "newma_integrated_research_probe",
        research_backend / "app.py",
    )
    trading = load_module("api_server", trading_agent / "api_server.py")
    research_routes = route_paths(research.app)
    trading_routes = route_paths(trading.app)

    violations: list[str] = []
    if "/api/chat" in research_routes:
        violations.append("Research native model route /api/chat is registered")
    if "/settings/llm" in trading_routes:
        violations.append("Trading native model route /settings/llm is registered")
    for prefix in ("/sessions", "/channels", "/swarm", "/scheduled-runs", "/upload"):
        if any(path == prefix or path.startswith(f"{prefix}/") for path in trading_routes):
            violations.append(f"Trading native route {prefix} is registered")

    imported_forbidden = [
        prefix
        for prefix in FORBIDDEN_MODULE_PREFIXES
        if any(name == prefix or name.startswith(f"{prefix}.") for name in sys.modules)
    ]
    violations.extend(
        f"forbidden heavyweight module imported: {prefix}"
        for prefix in imported_forbidden
    )
    measured_rss = rss_mib()
    if measured_rss > args.max_rss_mib:
        violations.append(
            f"import RSS {measured_rss:.1f} MiB exceeds {args.max_rss_mib:.1f} MiB"
        )

    report = {
        "ok": not violations,
        "rssMiB": round(measured_rss, 1),
        "maxRssMiB": args.max_rss_mib,
        "researchRouteCount": len(research_routes),
        "tradingRouteCount": len(trading_routes),
        "forbiddenImports": imported_forbidden,
        "violations": violations,
    }
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
