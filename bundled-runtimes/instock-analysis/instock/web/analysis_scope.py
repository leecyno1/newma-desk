"""Resolve Desk scope through a fixed, operator-configured session validator."""

import json
import os
from urllib.parse import urlsplit

from tornado.httpclient import AsyncHTTPClient, HTTPClientError, HTTPRequest

from instock.core.analysis_scope import desk_scope


class AnalysisScopeError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(message)


def desk_session_required(environ=None) -> bool:
    env = os.environ if environ is None else environ
    value = env.get("INSTOCK_REQUIRE_DESK_SESSION", "0")
    if value not in {"0", "1"}:
        raise ValueError("INSTOCK_REQUIRE_DESK_SESSION must be 0 or 1")
    return value == "1"


def validate_scope_url(endpoint: str) -> str:
    url = urlsplit(endpoint)
    if (url.scheme != "http" or url.hostname not in {"127.0.0.1", "::1", "localhost"}
            or url.path != "/api/mods/runtime/instock-scope" or url.username or url.password
            or url.query or url.fragment):
        raise ValueError("INSTOCK_DESK_SCOPE_URL must select the loopback Desk stock validator")
    return endpoint


async def resolve_request_scope(headers, *, method: str, path: str) -> str:
    token = headers.get("X-Newma-Desk-Session")
    instance = headers.get("X-Newma-Desk-Instance-Id")
    authorization = headers.get("Authorization")
    legacy = headers.get("X-Newma-Dock-Instance-Id")
    supplied = any(value is not None for value in (token, instance, authorization, legacy))
    if not supplied and not desk_session_required():
        # Explicit local single-user API. It never reads Desk or ownerless data.
        return "standalone:local"
    if authorization is not None:
        bearer = authorization[7:] if authorization.startswith("Bearer ") else ""
        if not bearer or (token is not None and token != bearer):
            raise AnalysisScopeError(401, "Desk 会话不完整，请刷新后重试")
        token = bearer
    if legacy is not None and legacy != instance:
        raise AnalysisScopeError(401, "Desk 实例不匹配，请刷新后重试")
    if not token or not instance or len(token) > 16384 or len(instance) > 128:
        raise AnalysisScopeError(401, "Desk 会话不完整，请刷新后重试")
    endpoint = os.environ.get("INSTOCK_DESK_SCOPE_URL", "").strip()
    if not endpoint:
        raise AnalysisScopeError(503, "尚未配置 Desk 会话校验，未回退到共享研究结果")
    try:
        validate_scope_url(endpoint)
        response = await AsyncHTTPClient().fetch(HTTPRequest(
            endpoint, method="POST", follow_redirects=False, request_timeout=8,
            headers={"Authorization": "Bearer " + token, "X-Newma-Desk-Instance-Id": instance,
                     "Content-Type": "application/json"},
            body=json.dumps({"method": method, "path": path}),
        ))
        claims = json.loads(response.body)
        if not isinstance(claims, dict) or not all(isinstance(claims.get(key), str) and claims[key] for key in ("userId", "workspaceId")):
            raise ValueError("invalid Desk identity")
        return desk_scope(claims["userId"], claims["workspaceId"])
    except HTTPClientError as exc:
        status = exc.code if exc.code in (401, 403) else 503
        raise AnalysisScopeError(status, "Desk 会话校验失败，请刷新后重试；未读取独立模式数据") from exc
    except (ValueError, KeyError, TypeError) as exc:
        raise AnalysisScopeError(503, "Desk 会话校验响应无效") from exc
