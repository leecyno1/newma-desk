#!/usr/bin/env python3
"""Fail-closed preflight for a co-located Newma production stack."""

from __future__ import annotations

import argparse
import json
import sys
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen


def origin(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError(f"invalid HTTP(S) URL: {value}")
    return f"{parsed.scheme}://{parsed.netloc}"


def read(url: str, timeout: float) -> tuple[int, str, str]:
    request = Request(url, headers={"User-Agent": "Newma-stack-preflight/1"})
    with urlopen(request, timeout=timeout) as response:
        return response.status, response.headers.get("Content-Type", ""), response.read().decode("utf-8", "replace")


def require_2xx(label: str, url: str, timeout: float) -> tuple[str, str]:
    status, content_type, body = read(url, timeout)
    if not 200 <= status < 300:
        raise RuntimeError(f"{label} returned HTTP {status}: {url}")
    return content_type, body


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify Hermes, Newma WebUI, and NewmaDesk connectivity")
    parser.add_argument("--desk-origin", required=True, help="Browser-facing dedicated NewmaDesk Origin")
    parser.add_argument("--mod-origin", required=True, help="Browser-facing dedicated Mod/API Origin")
    parser.add_argument("--webui-origin", required=True, help="Browser-facing Newma WebUI Origin")
    parser.add_argument("--webui-health-url", required=True, help="Server-local or public WebUI health URL")
    parser.add_argument("--hermes-health-url", required=True, help="Server-local Hermes health URL")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--allow-loopback-http", action="store_true", help="Local development only")
    args = parser.parse_args()

    desk_origin = origin(args.desk_origin)
    mod_origin = origin(args.mod_origin)
    webui_origin = origin(args.webui_origin)
    if len({desk_origin, mod_origin, webui_origin}) != 3:
        raise RuntimeError("Desk, Mod/API, and WebUI must use three distinct browser Origins")
    for label, value in (("Desk", desk_origin), ("Mod/API", mod_origin), ("WebUI", webui_origin)):
        parsed = urlsplit(value)
        loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if parsed.scheme != "https" and not (args.allow_loopback_http and loopback):
            raise RuntimeError(f"{label} browser Origin must use HTTPS: {value}")

    _, desk_html = require_2xx("NewmaDesk shell", desk_origin + "/", args.timeout)
    if "Newma-Desk" not in desk_html:
        raise RuntimeError("NewmaDesk shell marker is missing")
    if "/@vite/client" in desk_html or "/src/main.tsx" in desk_html:
        raise RuntimeError("NewmaDesk is serving a Vite development shell instead of production assets")

    _, health_body = require_2xx("NewmaDesk API", urljoin(desk_origin + "/", "api/health"), args.timeout)
    health = json.loads(health_body)
    if health.get("ok") is not True or health.get("service") != "newma-desk-api":
        raise RuntimeError("NewmaDesk API health payload is invalid")

    _, capabilities_body = require_2xx("NewmaDesk capabilities", urljoin(desk_origin + "/", "api/capabilities"), args.timeout)
    capabilities = json.loads(capabilities_body)
    hermes_adapter = next((row for row in capabilities.get("adapters", []) if row.get("id") == "hermes-webui"), None)
    if not hermes_adapter or hermes_adapter.get("available") is not True:
        raise RuntimeError("NewmaDesk cannot reach the configured Newma/Hermes WebUI adapter")

    _, mod_html = require_2xx("NewmaDesk Mod runtime", urljoin(mod_origin + "/", "mod-runtime/trading/"), args.timeout)
    if "127.0.0.1" in mod_html or "localhost" in mod_html:
        raise RuntimeError("Mod runtime HTML leaks a browser-visible loopback URL")

    require_2xx("Newma WebUI", args.webui_health_url, args.timeout)
    require_2xx("Hermes", args.hermes_health_url, args.timeout)
    print(json.dumps({
        "ok": True,
        "deskOrigin": desk_origin,
        "modOrigin": mod_origin,
        "webuiOrigin": webui_origin,
        "checks": ["desk-shell", "desk-api", "desk-hermes-adapter", "mod-runtime", "webui", "hermes"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"NEWMA_STACK_PREFLIGHT_FAILED: {error}", file=sys.stderr)
        raise SystemExit(1)
