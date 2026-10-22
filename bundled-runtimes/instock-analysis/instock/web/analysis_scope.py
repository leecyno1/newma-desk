"""Resolve Desk scope through a fixed, operator-configured session validator."""

import json
import os

from tornado.httpclient import AsyncHTTPClient, HTTPClientError, HTTPRequest

from instock.core.analysis_scope import desk_scope


class AnalysisScopeError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(message)


async def resolve_request_scope(headers, *, method: str, path: str) -> str:
    token = headers.get("X-Newma-Desk-Session")
    instance = headers.get("X-Newma-Desk-Instance-Id")
    if token is None and instance is None:
        # Explicit local single-user API. It never reads Desk or ownerless data.
        return "standalone:local"
    if not token or not instance or len(token) > 16384 or len(instance) > 128:
        raise AnalysisScopeError(401, "Desk 会话不完整，请刷新后重试")
    endpoint = os.environ.get("INSTOCK_DESK_SCOPE_URL", "").strip()
    if not endpoint:
        raise AnalysisScopeError(503, "尚未配置 Desk 会话校验，未回退到共享研究结果")
    try:
        response = await AsyncHTTPClient().fetch(HTTPRequest(
            endpoint, method="POST", follow_redirects=False, request_timeout=8,
            headers={"Authorization": "Bearer " + token, "X-Newma-Desk-Instance-Id": instance,
                     "Content-Type": "application/json"},
            body=json.dumps({"method": method, "path": path}),
        ))
        claims = json.loads(response.body)
        return desk_scope(claims["userId"], claims["workspaceId"])
    except HTTPClientError as exc:
        status = exc.code if exc.code in (401, 403) else 503
        raise AnalysisScopeError(status, "Desk 会话校验失败，请刷新后重试；未读取独立模式数据") from exc
    except (ValueError, KeyError, TypeError) as exc:
        raise AnalysisScopeError(503, "Desk 会话校验响应无效") from exc
