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


class Handler(BaseHTTPRequestHandler):
    server_version = "VibeE2EUpstream/1.0"

    def _json(self, status: int, payload: object) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        payload = RESPONSES.get(path)
        if payload is None:
            self._json(404, {"detail": "not found"})
            return
        self._json(200, payload)

    def do_POST(self) -> None:  # noqa: N802
        path = urlsplit(self.path).path
        if path != "/v1/chat/completions":
            self._json(404, {"detail": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        if length:
            self.rfile.read(length)
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
