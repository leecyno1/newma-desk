from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit


RESPONSES: dict[str, object] = {
    "/health": {"ok": True, "service": "vibe-e2e-upstream"},
    "/api/market/overview": {
        "data": {
            "sentiment": {"up": 3120, "down": 1800, "flat": 120},
            "updated": "2026-07-20 15:00",
        }
    },
    "/api/indices": {
        "data": [
            {
                "name": "上证指数",
                "price": 3520.1,
                "change_pct": 0.8,
                "change_amt": 28.0,
            },
            {
                "name": "创业板指",
                "price": 2300.2,
                "change_pct": -0.3,
                "change_amt": -6.9,
            },
        ]
    },
    "/api/global/indices": {
        "data": [
            {
                "key": "spx",
                "name": "标普500",
                "region": "美股",
                "price": 6300.0,
                "change_pct": 0.5,
            }
        ]
    },
    "/api/market/turnover-top": {
        "data": {
            "stocks": [
                {
                    "code": "600519",
                    "name": "贵州茅台",
                    "price": 1488.0,
                    "pct": 3.2,
                    "amount": 120000000,
                    "mcap": 1800000000000,
                    "float_cap": 1800000000000,
                    "industry": "白酒",
                }
            ],
            "updated": "2026-07-20 15:00",
        }
    },
}

HERMES_NEW_SESSION_CALLS = 0
HERMES_CHAT_STARTS: list[dict[str, str]] = []
HERMES_STREAMS: dict[str, dict[str, str]] = {}


class Handler(BaseHTTPRequestHandler):
    server_version = "VibeE2EUpstream/1.0"

    def _json(self, status: int, payload: object) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _sse(self, payload: str) -> None:
        encoded = payload.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path == "/api/testing/hermes-stats":
            self._json(
                200,
                {
                    "newSessionCalls": HERMES_NEW_SESSION_CALLS,
                    "chatStarts": HERMES_CHAT_STARTS,
                },
            )
            return
        if path == "/api/chat/stream":
            query = urlsplit(self.path).query
            stream_id = next(
                (
                    pair.split("=", 1)[1]
                    for pair in query.split("&")
                    if pair.startswith("stream_id=")
                ),
                "",
            )
            stream = HERMES_STREAMS.get(stream_id)
            if stream is None:
                self._json(404, {"error": "stream not found"})
                return
            answer = f"Hermes E2E Agent 回答 #{stream['turn']}"
            done = {
                "session": {
                    "session_id": stream["session_id"],
                    "messages": [
                        {"role": "user", "content": stream["message"]},
                        {"role": "assistant", "content": answer},
                    ],
                }
            }
            self._sse(
                "event: token\n"
                f"data: {json.dumps({'text': answer}, ensure_ascii=False)}\n\n"
                "event: done\n"
                f"data: {json.dumps(done, ensure_ascii=False)}\n\n"
                "event: stream_end\n"
                f"data: {json.dumps({'session_id': stream['session_id']})}\n\n"
            )
            return
        if path == "/api/chat/cancel":
            self._json(200, {"ok": True, "cancelled": True})
            return
        payload = RESPONSES.get(path)
        if payload is None:
            self._json(404, {"detail": "not found"})
            return
        self._json(200, payload)

    def do_POST(self) -> None:  # noqa: N802
        global HERMES_NEW_SESSION_CALLS
        path = urlsplit(self.path).path
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw_body)
        except json.JSONDecodeError:
            body = {}
        if path == "/api/session/new":
            HERMES_NEW_SESSION_CALLS += 1
            self._json(
                200,
                {"session": {"session_id": "hermes-e2e-session"}},
            )
            return
        if path == "/api/chat/start":
            turn = len(HERMES_CHAT_STARTS) + 1
            session_id = str(body.get("session_id") or "")
            message = str(body.get("message") or "")
            stream_id = f"hermes-e2e-stream-{turn}"
            HERMES_CHAT_STARTS.append(
                {"sessionId": session_id, "message": message}
            )
            HERMES_STREAMS[stream_id] = {
                "session_id": session_id,
                "message": message,
                "turn": str(turn),
            }
            self._json(200, {"stream_id": stream_id, "session_id": session_id})
            return
        if path != "/v1/chat/completions":
            self._json(404, {"detail": "not found"})
            return
        self._json(
            200,
            {
                "id": "chatcmpl-e2e",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": (
                                "## 观察\nE2E 行情解释完成。\n\n"
                                "## 可能驱动\n仅用于确定性测试。\n\n"
                                "## 风险\n不构成投资建议。"
                            ),
                        },
                    }
                ],
            },
        )

    def log_message(self, format: str, *args: Any) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    arguments = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", arguments.port), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
