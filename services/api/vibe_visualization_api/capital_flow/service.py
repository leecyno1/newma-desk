from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx


class CapitalFlowService:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 15.0,
        client: httpx.AsyncClient | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client = client

    async def _fetch(self, client: httpx.AsyncClient, path: str) -> Any:
        response = await client.get(f"{self._base_url}{path}")
        response.raise_for_status()
        payload = response.json()
        return payload.get("data", payload) if isinstance(payload, dict) else payload

    async def dashboard(self, code: str | None = None) -> dict:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=False,
            trust_env=False,
        )
        paths = ["/api/market/overview", "/api/market/turnover-top"]
        if code:
            paths.extend([f"/api/fund-flow?code={code}", f"/api/margin?code={code}"])
        try:
            results = await asyncio.gather(
                *(self._fetch(client, path) for path in paths),
                return_exceptions=True,
            )
        finally:
            if owns_client:
                await client.aclose()

        overview = results[0] if not isinstance(results[0], Exception) else {}
        turnover = results[1] if not isinstance(results[1], Exception) else {}
        sectors = overview.get("sectors", []) if isinstance(overview, dict) else []
        sectors = sorted(sectors, key=lambda item: float(item.get("net", 0)), reverse=True)
        inflow = sum(float(item.get("inflow", 0) or 0) for item in sectors)
        outflow = sum(float(item.get("outflow", 0) or 0) for item in sectors)
        net = sum(float(item.get("net", 0) or 0) for item in sectors)
        leaders = turnover.get("stocks", []) if isinstance(turnover, dict) else []
        top_turnover = sum(float(item.get("amount", 0) or 0) for item in leaders)

        stock_flow = results[2] if code and len(results) > 2 and not isinstance(results[2], Exception) else []
        margin = results[3] if code and len(results) > 3 and not isinstance(results[3], Exception) else []
        upstream_ok = bool(sectors or leaders)
        return {
            "schemaVersion": "newma-desk.capital-flow.v1",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "marketDate": overview.get("sentiment", {}).get("date") if isinstance(overview, dict) else None,
            "summary": {
                "sectorNetYi": round(net, 2),
                "sectorInflowYi": round(inflow, 2),
                "sectorOutflowYi": round(outflow, 2),
                "top20TurnoverYi": round(top_turnover / 100_000_000, 2),
                "active": overview.get("sentiment", {}).get("active") if isinstance(overview, dict) else None,
            },
            "sectors": sectors,
            "turnoverLeaders": leaders[:20],
            "security": {"code": code, "fundFlow": stock_flow, "margin": margin} if code else None,
            "dimensions": [
                {"id": "market", "name": "市场成交", "status": "ready" if leaders else "degraded", "frequency": "盘中/日频", "lag": "约 5 分钟", "source": "交易行情聚合"},
                {"id": "sector", "name": "行业资金", "status": "ready" if sectors else "degraded", "frequency": "盘中", "lag": "约 5 分钟", "source": "A Stock Data / AKShare"},
                {"id": "northbound", "name": "北向资金", "status": "planned", "frequency": "日频", "lag": "收盘后", "source": "HKEX 官方披露", "note": "盘中额度数据不等同净买入，深股通实时估算不作为正式口径。"},
                {"id": "southbound", "name": "南向资金", "status": "planned", "frequency": "日频", "lag": "收盘后", "source": "HKEX 沪深港通"},
                {"id": "margin", "name": "杠杆资金", "status": "ready" if code and margin else "on-demand", "frequency": "日频", "lag": "T+1", "source": "沪深交易所 / A Stock Data"},
                {"id": "etf", "name": "ETF 申赎", "status": "planned", "frequency": "日频", "lag": "T+1", "source": "基金份额与净值公告"},
                {"id": "liquidity", "name": "宏观流动性", "status": "planned", "frequency": "日/周/月", "lag": "按指标", "source": "人民银行 / 货币市场"},
            ],
            "sources": [
                {"name": "HKEX 沪深港通", "url": "https://www.hkex.com.hk/Mutual-Market/Stock-Connect/Statistics/Historical-Daily"},
                {"name": "上海证券交易所", "url": "https://www.sse.com.cn/market/othersdata/margin/"},
                {"name": "深圳证券交易所", "url": "https://www.szse.cn/market/dealdata/margin/"},
                {"name": "中国人民银行", "url": "https://www.pbc.gov.cn/"},
            ],
            "upstream": {"status": "ready" if upstream_ok else "degraded", "base": "Vibe Research / a-stock-data"},
        }
