from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import re

import httpx

from .store import CapitalHistoryStore


class ETFCatalog:
    def __init__(self, token: str, store: CapitalHistoryStore, *, client=None):
        self.token, self.store, self.client = token, store, client

    async def read(self) -> dict:
        dataset, day = "capital.etf-catalog.v1", "2000-01-01"
        rows, run = await asyncio.to_thread(self.store.read, dataset, "CN", day, day)
        now = datetime.now(timezone.utc)
        if rows and run and (now - datetime.fromisoformat(run["received_at"])).total_seconds() < 86400:
            return rows[0]["catalog"]
        client = self.client or httpx.AsyncClient(timeout=15, trust_env=False)
        try:
            if not self.token:
                raise ValueError("Tushare未配置")
            items = {}
            for offset in range(0, 8000, 2000):
                response = await client.post("https://api.tushare.pro", json={"api_name": "etf_basic", "token": self.token,
                    "params": {"list_status": "L", "limit": 2000, "offset": offset},
                    "fields": "ts_code,csname,index_code,index_name"})
                response.raise_for_status()
                payload = response.json()
                if payload.get("code") != 0:
                    raise ValueError("ETF目录接口不可用或权限不足")
                data = payload.get("data") or {}
                batch = data.get("items") or []
                for values in batch:
                    row = dict(zip(data.get("fields") or [], values))
                    code = row.get("ts_code") or ""
                    if re.fullmatch(r"\d{6}\.(SH|SZ)", code) and row.get("csname"):
                        items[code] = {"code": code, "name": row["csname"], "indexCode": row.get("index_code"), "indexName": row.get("index_name")}
                if data.get("has_more") is False or ("has_more" not in data and len(batch) < 2000):
                    break
                if not batch:
                    raise ValueError("ETF目录分页不完整")
            else:
                raise ValueError("ETF目录超过本次分页上限")
            if not items:
                raise ValueError("ETF目录为空，不覆盖已保存目录")
            result = {"status": "ready", "source": "Tushare etf_basic", "receivedAt": now.isoformat(),
                      "usingSaved": False, "reason": "", "items": list(items.values())}
            await asyncio.to_thread(self.store.save, dataset, "CN", [{"date": day, "catalog": result}],
                                    start=day, end=day, status="ready", reason="", received_at=now.isoformat())
            return result
        except (httpx.HTTPError, ValueError) as exc:
            return {"status": "unavailable", "source": "Tushare etf_basic", "receivedAt": rows[0]["catalog"]["receivedAt"] if rows else None,
                    "usingSaved": bool(rows), "reason": str(exc) if isinstance(exc, ValueError) else "ETF目录请求失败",
                    "items": rows[0]["catalog"]["items"] if rows else []}
        finally:
            if self.client is None:
                await client.aclose()

    async def search(self, query: str) -> dict:
        result = await self.read()
        term = query.strip().casefold()
        matched = [row for row in result["items"] if any(term in str(row.get(key) or "").casefold() for key in ("code", "name", "indexName"))]
        matched.sort(key=lambda row: (row["code"].split(".")[0] != term, row["code"]))
        return {**result, "total": len(result["items"]), "matched": len(matched), "items": matched[:20]}
