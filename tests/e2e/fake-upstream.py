from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit


def _quote(
    symbol: str,
    name: str,
    market: str,
    price: float,
    change_pct: float,
) -> dict[str, object]:
    exchange = "SH" if market == "CN" else "NASDAQ"
    currency = "CNY" if market == "CN" else "USD"
    return {
        "symbol": symbol,
        "name": name,
        "market": market,
        "exchange": exchange,
        "currency": currency,
        "timezone": "Asia/Shanghai" if market == "CN" else "America/New_York",
        "price": price,
        "change": round(price * change_pct / 100, 2),
        "changePct": change_pct,
        "prevClose": round(price / (1 + change_pct / 100), 2),
        "open": round(price * 0.995, 2),
        "high": round(price * 1.012, 2),
        "low": round(price * 0.988, 2),
        "volume": 35_609_000,
        "amount": 4_622_000_000,
        "turnoverPct": 0.29,
        "marketCap": 1_620_000_000_000,
        "floatMarketCap": 1_620_000_000_000,
        "pe": 22.3,
        "pb": 7.1,
        "amplitudePct": 2.4,
        "volumeRatio": 1.08,
        "limitUp": round(price * 1.1, 2) if market == "CN" else None,
        "limitDown": round(price * 0.9, 2) if market == "CN" else None,
        "orderBook": {
            "bids": [{"price": price, "volume": 1500}],
            "asks": [{"price": round(price + 0.01, 2), "volume": 1200}],
        },
        "trades": [],
        "source": "e2e-market-data",
        "sources": ["e2e-market-data"],
        "asOf": "2026-07-24T15:00:00+08:00",
    }


QUOTES = {
    "CN:600519": _quote("600519", "贵州茅台", "CN", 1488.0, 0.81),
    "HK:00700": _quote("00700", "腾讯控股", "HK", 628.0, 1.24),
    "US:NVDA": _quote("NVDA", "NVIDIA", "US", 186.5, -1.06),
}


def _ohlcv(symbol: str, market: str, timeframe: str, adjust: str) -> dict[str, object]:
    start = datetime(2026, 4, 1, tzinfo=UTC)
    items = []
    for index in range(90):
        base = 1320 + index * 1.4 + ((index % 9) - 4) * 3
        items.append({
            "timestamp": int((start + timedelta(days=index)).timestamp() * 1000),
            "open": round(base - 3, 2),
            "high": round(base + 9, 2),
            "low": round(base - 11, 2),
            "close": round(base + (4 if index % 2 == 0 else -2), 2),
            "volume": 40_000 + index * 700,
            "turnover": 55_000_000 + index * 1_000_000,
        })
    return {
        "symbol": symbol,
        "market": market,
        "timeframe": timeframe,
        "adjust": adjust,
        "items": items,
        "source": "e2e-market-data",
        "asOf": "2026-07-24T15:00:00+08:00",
        "hasMore": False,
    }


RESPONSES: dict[str, object] = {
    "/health": {"ok": True, "service": "vibe-e2e-upstream"},
    "/api/market/overview": {
        "data": {
            "sentiment": {
                "up": 3120,
                "down": 1800,
                "flat": 120,
                "zt": 64,
                "dt": 7,
                "breadth": "偏强",
            },
            "sectors": [
                {"name": "半导体", "pct": 2.1, "net": 2_000_000_000},
                {"name": "光模块", "pct": 1.7, "net": 1_200_000_000},
            ],
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
    "/api/announcements": {
        "data": [
            {
                "title": "贵州茅台2026年半年度业绩预告",
                "date": "2026-07-22 18:30:00",
                "type": "业绩预告",
                "url": "https://example.test/evidence/announcement-600519",
            }
        ]
    },
    "/api/reports": {
        "data": [
            {
                "reportTitle": "贵州茅台：渠道韧性与中长期现金流观察",
                "publishDate": "2026-07-21 09:15:00",
                "orgSName": "E2E证券研究所",
                "emRatingName": "跟踪",
                "pdfUrl": "https://example.test/evidence/report-600519.pdf",
            }
        ]
    },
    "/api/news": {
        "data": [
            {
                "新闻标题": "贵州茅台披露最新渠道运营信息",
                "发布时间": "2026-07-20 14:00:00",
                "文章来源": "E2E财经",
                "新闻链接": "https://example.test/evidence/news-600519",
            }
        ]
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
        parsed = urlsplit(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
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
            if "执行界面动作" in stream["message"]:
                answer += (
                    "\n<vibedesk_actions>"
                    '[{"actionId":"market.set-timeframe","input":{"timeframe":"15m"}},'
                    '{"actionId":"chart.set-indicator","input":{"position":"secondary","indicator":"MACD"}},'
                    '{"actionId":"market.set-alert","input":{"direction":"above","price":190,"label":"E2E 上穿预警"}},'
                    '{"actionId":"workspace.save-layout","input":{"name":"E2E Agent 布局"}}]'
                    "</vibedesk_actions>"
                )
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
        if path.startswith("/api/market-terminal/"):
            path = path[4:]
        if path == "/market-terminal/search":
            self._json(
                200,
                {
                    "data": {
                        "items": [
                            {
                                "symbol": "NVDA",
                                "name": "NVIDIA",
                                "market": "US",
                                "exchange": "NASDAQ",
                                "currency": "USD",
                                "timezone": "America/New_York",
                                "assetType": "stock",
                                "source": "e2e-market-data",
                            }
                        ],
                        "asOf": "2026-07-24T15:00:00+08:00",
                        "source": "e2e-market-data",
                    }
                },
            )
            return
        if path == "/market-terminal/quotes":
            requested = str(query.get("symbols", [""])[0]).split(",")
            items = [QUOTES[symbol] for symbol in requested if symbol in QUOTES]
            self._json(
                200,
                {
                    "data": {
                        "items": items,
                        "asOf": "2026-07-24T15:00:00+08:00",
                        "source": "e2e-market-data",
                    }
                },
            )
            return
        if path == "/market-terminal/quote":
            market = str(query.get("market", ["CN"])[0]).upper()
            symbol = str(query.get("symbol", ["600519"])[0]).upper()
            quote = QUOTES.get(f"{market}:{symbol}", QUOTES["CN:600519"])
            self._json(200, {"data": quote})
            return
        if path == "/market-terminal/scan":
            market = str(query.get("market", ["CN"])[0]).upper()
            sort = str(query.get("sort", ["amount"])[0])
            order = str(query.get("order", ["desc"])[0])
            items = [
                quote for quote in QUOTES.values()
                if quote.get("market") == market
            ]
            self._json(200, {
                "data": {
                    "items": items,
                    "market": market,
                    "sort": sort,
                    "order": order,
                    "source": "e2e-market-data",
                    "asOf": "2026-07-24T15:00:00+08:00",
                    "coverage": {"requested": len(items), "returned": len(items)},
                }
            })
            return
        if path == "/market-terminal/ohlcv":
            market = str(query.get("market", ["CN"])[0]).upper()
            symbol = str(query.get("symbol", ["600519"])[0]).upper()
            timeframe = str(query.get("timeframe", ["1d"])[0])
            adjust = str(query.get("adjust", ["none"])[0])
            self._json(200, {"data": _ohlcv(symbol, market, timeframe, adjust)})
            return
        payload = RESPONSES.get(path)
        if payload is None and not path.startswith("/api/"):
            payload = RESPONSES.get(f"/api{path}")
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
