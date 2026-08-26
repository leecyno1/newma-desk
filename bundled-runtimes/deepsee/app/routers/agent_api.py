from __future__ import annotations

import time
from typing import Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlencode
from urllib.request import Request as UrlRequest, urlopen
from urllib.error import HTTPError, URLError
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel, Field

from ..config import settings
from ..db import SessionLocal
from ..models import SyncState


def _configured_agent_tokens() -> set[str]:
    tokens: set[str] = set()
    single = str(getattr(settings, "AGENT_API_TOKEN", "") or "").strip()
    if single:
        tokens.add(single)
    many = str(getattr(settings, "AGENT_API_TOKENS", "") or "").strip()
    if many:
        for item in many.split(","):
            token = str(item or "").strip()
            if token:
                tokens.add(token)
    return tokens


def _extract_bearer_token(authorization: str | None) -> str | None:
    raw = str(authorization or "").strip()
    if not raw:
        return None
    if raw.lower().startswith("bearer "):
        tok = raw[7:].strip()
        return tok or None
    return None


def require_agent_token(
    authorization: str | None = Header(default=None),
    x_agent_token: str | None = Header(default=None, alias="X-Agent-Token"),
) -> None:
    configured = _configured_agent_tokens()
    if not configured:
        return
    presented: list[str] = []
    bearer = _extract_bearer_token(authorization)
    if bearer:
        presented.append(bearer)
    x_token = str(x_agent_token or "").strip()
    if x_token:
        presented.append(x_token)
    if any(token in configured for token in presented):
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="unauthorized agent token",
    )


router = APIRouter(
    prefix="/api/agent",
    tags=["agent-api"],
    dependencies=[Depends(require_agent_token)],
)


class AgentInvokeIn(BaseModel):
    method: str = Field(default="GET", description="HTTP method: GET/POST/PUT/PATCH/DELETE")
    path: str = Field(description="Target API path, must start with /api/")
    query: dict[str, Any] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any | None = None
    timeout_ms: int = Field(default=10000, ge=100, le=120000)


class AgentBatchInvokeIn(BaseModel):
    requests: list[AgentInvokeIn] = Field(default_factory=list, description="Batch requests to execute")
    stop_on_error: bool = Field(default=False, description="Stop processing after the first non-2xx response")
    max_workers: int = Field(default=4, ge=1, le=32, description="Worker count when stop_on_error=false")


class AgentPolicyIn(BaseModel):
    allowlist: list[str] = Field(default_factory=list, description="Allowed API path prefixes, empty means allow all")
    blocklist: list[str] = Field(default_factory=list, description="Denied API path prefixes")


def _list_api_routes(request: Request) -> list[APIRoute]:
    routes: list[APIRoute] = []
    for route in request.app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.startswith("/api/"):
            continue
        if route.path.startswith("/api/agent"):
            continue
        routes.append(route)
    return routes


_AGENT_POLICY_KEY = "agent_api_policy"


def _normalize_path_prefix(raw: str) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    if not s.startswith("/"):
        s = f"/{s}"
    if s.endswith("/*"):
        s = s[:-2]
    if len(s) > 1 and s.endswith("/"):
        s = s[:-1]
    return s


def _normalize_path_prefixes(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for v in values or []:
        n = _normalize_path_prefix(str(v or ""))
        if not n:
            continue
        if not n.startswith("/api/"):
            continue
        if n.startswith("/api/agent"):
            continue
        if n in seen:
            continue
        seen.add(n)
        out.append(n)
    return out


def _matches_prefix(path: str, prefix: str) -> bool:
    if path == prefix:
        return True
    return path.startswith(f"{prefix}/")


def _parse_csv_prefixes(raw: str | None) -> list[str]:
    if not raw:
        return []
    vals = [str(x or "").strip() for x in str(raw).split(",")]
    return _normalize_path_prefixes(vals)


def _load_agent_policy_stored() -> dict[str, list[str]]:
    db = SessionLocal()
    try:
        row = db.get(SyncState, _AGENT_POLICY_KEY)
        if not row or not row.value:
            return {"allowlist": [], "blocklist": []}
        data = json.loads(row.value)
        if not isinstance(data, dict):
            return {"allowlist": [], "blocklist": []}
        allow = data.get("allowlist") if isinstance(data.get("allowlist"), list) else []
        block = data.get("blocklist") if isinstance(data.get("blocklist"), list) else []
        return {
            "allowlist": _normalize_path_prefixes([str(x) for x in allow]),
            "blocklist": _normalize_path_prefixes([str(x) for x in block]),
        }
    except Exception:
        return {"allowlist": [], "blocklist": []}
    finally:
        db.close()


def _save_agent_policy_stored(allowlist: list[str], blocklist: list[str]) -> None:
    payload = json.dumps({"allowlist": allowlist, "blocklist": blocklist}, ensure_ascii=False)
    db = SessionLocal()
    try:
        row = db.get(SyncState, _AGENT_POLICY_KEY)
        if not row:
            row = SyncState(key=_AGENT_POLICY_KEY, value=payload)
        else:
            row.value = payload
        db.add(row)
        db.commit()
    finally:
        db.close()


def _merge_prefixes(a: list[str], b: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for x in (a or []) + (b or []):
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


def _effective_agent_policy() -> dict[str, list[str]]:
    stored = _load_agent_policy_stored()
    env_allow = _parse_csv_prefixes(getattr(settings, "AGENT_API_ALLOWLIST", None))
    env_block = _parse_csv_prefixes(getattr(settings, "AGENT_API_BLOCKLIST", None))
    return {
        "allowlist": _merge_prefixes(stored.get("allowlist", []), env_allow),
        "blocklist": _merge_prefixes(stored.get("blocklist", []), env_block),
    }


def _check_agent_path_allowed(path: str) -> tuple[bool, str | None]:
    policy = _effective_agent_policy()
    allow = policy.get("allowlist", [])
    block = policy.get("blocklist", [])
    for p in block:
        if _matches_prefix(path, p):
            return False, f"path blocked by blocklist: {p}"
    if allow and not any(_matches_prefix(path, p) for p in allow):
        return False, "path not in allowlist"
    return True, None


@router.get("/health")
def agent_api_health(request: Request) -> dict[str, Any]:
    routes = _list_api_routes(request)
    return {"status": "ok", "api_route_count": len(routes)}


@router.get("/capabilities")
def agent_capabilities(request: Request) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for route in _list_api_routes(request):
        methods = sorted(m for m in (route.methods or set()) if m not in {"HEAD", "OPTIONS"})
        query_params = []
        try:
            for p in route.dependant.query_params:  # type: ignore[attr-defined]
                query_params.append({"name": p.name, "required": bool(p.required)})
        except Exception:
            query_params = []
        has_body = bool(getattr(route, "body_field", None))
        for method in methods:
            rows.append(
                {
                    "id": f"{method}:{route.path}",
                    "method": method,
                    "path": route.path,
                    "summary": route.summary or "",
                    "name": route.name,
                    "tags": list(route.tags or []),
                    "query_params": query_params,
                    "has_body": has_body,
                }
            )
    rows.sort(key=lambda x: (x["path"], x["method"]))
    return {"count": len(rows), "items": rows}


@router.get("/modules")
def agent_modules() -> dict[str, Any]:
    """High-level module map for other agents."""
    return {
        "items": [
            {
                "module": "wechat_aggregation",
                "apis": ["/api/messages", "/api/messages/effective", "/api/chats", "/api/contacts", "/api/filters"],
            },
            {
                "module": "email_aggregation",
                "apis": ["/api/email/accounts", "/api/email/messages", "/api/email/derive", "/api/email/send"],
            },
            {
                "module": "media_aggregation",
                "apis": ["/api/media/items", "/api/media/meeting-records", "/api/folo/posts"],
            },
            {
                "module": "mp_aggregation",
                "apis": ["/api/mp/articles", "/api/mp/articles/{article_id}"],
            },
            {
                "module": "minutes_aggregation",
                "apis": ["/api/minutes", "/api/minutes/create", "/api/minutes/upload", "/api/minutes/refine", "/api/recorder/*"],
            },
            {
                "module": "ai_summary_and_reply",
                "apis": ["/api/ai/summary", "/api/ai/summary-local", "/api/ai/suggest-replies", "/api/ai/mass-generate"],
            },
            {
                "module": "sending",
                "apis": ["/api/send", "/api/send/out", "/api/send/campaigns"],
            },
            {
                "module": "sync_and_backup",
                "apis": ["/api/sync/chatlog", "/api/sync/chatlog/full", "/api/sync/state", "/api/sync/policy"],
            },
            {
                "module": "system_and_config",
                "apis": [
                    "/api/config",
                    "/api/config/ai-runtime",
                    "/api/config/media",
                    "/api/config/mp",
                    "/api/config/minutes",
                    "/api/config/extensions",
                ],
            },
        ]
    }


@router.get("/openapi")
def agent_openapi(request: Request) -> dict[str, Any]:
    spec = request.app.openapi()
    paths = spec.get("paths", {}) if isinstance(spec, dict) else {}
    filtered_paths: dict[str, Any] = {}
    for path, cfg in paths.items():
        if str(path).startswith("/api/") and not str(path).startswith("/api/agent"):
            filtered_paths[path] = cfg
    return {
        "openapi": spec.get("openapi", "3.1.0"),
        "info": spec.get("info", {}),
        "paths": filtered_paths,
        "components": spec.get("components", {}),
    }


@router.get("/policy")
def agent_policy() -> dict[str, Any]:
    stored = _load_agent_policy_stored()
    effective = _effective_agent_policy()
    return {
        "stored": stored,
        "effective": effective,
        "env": {
            "AGENT_API_ALLOWLIST": _parse_csv_prefixes(getattr(settings, "AGENT_API_ALLOWLIST", None)),
            "AGENT_API_BLOCKLIST": _parse_csv_prefixes(getattr(settings, "AGENT_API_BLOCKLIST", None)),
        },
    }


@router.post("/policy")
def agent_set_policy(payload: AgentPolicyIn) -> dict[str, Any]:
    allow = _normalize_path_prefixes(payload.allowlist or [])
    block = _normalize_path_prefixes(payload.blocklist or [])
    _save_agent_policy_stored(allowlist=allow, blocklist=block)
    return {"status": "ok", "stored": {"allowlist": allow, "blocklist": block}, "effective": _effective_agent_policy()}


@router.post("/invoke")
def agent_invoke(payload: AgentInvokeIn, request: Request):
    status_code, out = _invoke_single(payload=payload, request=request)
    return JSONResponse(status_code=status_code, content=out)


@router.post("/invoke-batch")
def agent_invoke_batch(payload: AgentBatchInvokeIn, request: Request) -> dict[str, Any]:
    reqs = payload.requests or []
    if not reqs:
        return {
            "ok": True,
            "total": 0,
            "executed": 0,
            "success": 0,
            "failed": 0,
            "stop_on_error": bool(payload.stop_on_error),
            "results": [],
        }

    results: list[dict[str, Any]] = []
    success = 0
    failed = 0
    if bool(payload.stop_on_error):
        for idx, req in enumerate(reqs):
            status_code, out = _invoke_single(payload=req, request=request)
            ok = bool(isinstance(out, dict) and out.get("ok", False))
            if ok:
                success += 1
            else:
                failed += 1
            results.append(
                {
                    "index": idx,
                    "ok": ok,
                    "status_code": status_code,
                    "result": out,
                }
            )
            if failed > 0:
                break
    else:
        workers = max(1, min(int(payload.max_workers or 1), len(reqs)))
        slots: list[dict[str, Any] | None] = [None] * len(reqs)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_to_idx = {pool.submit(_invoke_single, req, request): idx for idx, req in enumerate(reqs)}
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    status_code, out = future.result()
                except Exception as e:
                    status_code, out = 500, {"ok": False, "error": f"batch worker failed: {e}"}
                ok = bool(isinstance(out, dict) and out.get("ok", False))
                if ok:
                    success += 1
                else:
                    failed += 1
                slots[idx] = {
                    "index": idx,
                    "ok": ok,
                    "status_code": status_code,
                    "result": out,
                }
        results = [r for r in slots if r is not None]

    return {
        "ok": failed == 0,
        "total": len(reqs),
        "executed": len(results),
        "success": success,
        "failed": failed,
        "stop_on_error": bool(payload.stop_on_error),
        "results": results,
    }


def _invoke_single(payload: AgentInvokeIn, request: Request) -> tuple[int, dict[str, Any]]:
    method = payload.method.upper().strip()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        return 400, {"ok": False, "error": f"unsupported method: {method}"}

    path = str(payload.path or "").strip()
    if not path.startswith("/api/"):
        return 400, {"ok": False, "error": "path must start with /api/"}
    if path.startswith("/api/agent"):
        return 400, {"ok": False, "error": "calling /api/agent via invoke is not allowed"}
    allowed, reason = _check_agent_path_allowed(path)
    if not allowed:
        return 403, {"ok": False, "error": reason or "path forbidden by policy"}

    query = payload.query or {}
    qs = urlencode(query, doseq=True) if isinstance(query, dict) else ""
    url = f"{path}?{qs}" if qs else path
    base = str(request.base_url).rstrip("/")
    full_url = f"{base}{url}"

    headers = {k: v for k, v in (payload.headers or {}).items() if isinstance(k, str) and isinstance(v, str)}
    timeout_sec = max(0.1, min(payload.timeout_ms / 1000.0, 120.0))
    body_bytes: bytes | None = None
    if payload.body is not None:
        body_bytes = json.dumps(payload.body, ensure_ascii=False).encode("utf-8")
        headers.setdefault("Content-Type", "application/json; charset=utf-8")

    started = time.perf_counter()
    try:
        req = UrlRequest(url=full_url, method=method, headers=headers, data=body_bytes)
        with urlopen(req, timeout=timeout_sec) as resp:
            status_code = int(resp.status)
            raw = resp.read()
            resp_text = raw.decode("utf-8", errors="replace")
            resp_headers = dict(resp.headers.items())
    except HTTPError as e:
        status_code = int(e.code)
        raw = e.read() if hasattr(e, "read") else b""
        resp_text = raw.decode("utf-8", errors="replace")
        resp_headers = dict(e.headers.items()) if getattr(e, "headers", None) else {}
    except URLError as e:
        return 502, {"ok": False, "error": f"invoke url error: {e}"}
    except Exception as e:
        return 500, {"ok": False, "error": f"invoke failed: {e}"}
    duration_ms = int((time.perf_counter() - started) * 1000)

    data: Any
    try:
        data = json.loads(resp_text) if resp_text else None
    except Exception:
        data = resp_text

    out = {
        "ok": 200 <= status_code < 300,
        "status_code": status_code,
        "duration_ms": duration_ms,
        "path": path,
        "method": method,
        "headers": resp_headers,
        "data": data,
    }
    return status_code, out
