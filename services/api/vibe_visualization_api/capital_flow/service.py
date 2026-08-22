from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import json
import os
from urllib.parse import urlencode
from typing import Any

import httpx


class CapitalFlowService:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 15.0,
        client: httpx.AsyncClient | None = None,
        tushare_token: str | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client = client
        self._tushare_token = (
            tushare_token if tushare_token is not None else os.environ.get("TUSHARE_TOKEN", "")
        ).strip()

    async def _fetch(self, client: httpx.AsyncClient, path: str) -> Any:
        response = await client.get(f"{self._base_url}{path}")
        response.raise_for_status()
        payload = response.json()
        return payload.get("data", payload) if isinstance(payload, dict) else payload

    async def search_securities(self, query: str, limit: int = 8) -> dict:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=False,
            trust_env=False,
        )
        try:
            upstream_limit = min(30, max(limit * 3, limit))
            result = await self._fetch(
                client,
                f"/api/market-terminal/search?{urlencode({'query': query, 'market': 'CN', 'limit': upstream_limit})}",
            )
            if not isinstance(result, dict):
                return {"items": []}
            items = result.get("items") if isinstance(result.get("items"), list) else []
            stocks = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                symbol = str(item.get("symbol") or "").strip()
                if (
                    str(item.get("market") or "").upper() == "CN"
                    and str(item.get("assetType") or "").casefold() == "stock"
                    and str(item.get("exchange") or "").upper() in {"SH", "SZ", "BJ"}
                    and len(symbol) == 6
                    and symbol.isdigit()
                ):
                    stocks.append(item)
            return {**result, "items": stocks[:limit]}
        finally:
            if owns_client:
                await client.aclose()

    @staticmethod
    def _clean_stock_flow(rows: Any) -> list[dict[str, Any]]:
        """剔除数据源为未上市交易日补出的全零伪记录。"""
        if not isinstance(rows, list):
            return []

        cleaned: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue

            def number(field: str) -> float | None:
                try:
                    value = row.get(field)
                    return None if value in (None, "") else float(value)
                except (TypeError, ValueError):
                    return None

            close = number("close")
            flow_values = [number(field) for field in ("main_net", "net_amount", "super_net", "large_net")]
            has_flow = any(value is not None and abs(value) > 0 for value in flow_values)
            if close is not None and close <= 0 and not has_flow:
                continue
            cleaned.append(row)
        return cleaned

    async def _fetch_hkex_connect(self, client: httpx.AsyncClient, market_date: str | None) -> dict:
        """Read HKEX's public daily stock-connect snapshot.

        HKEX publishes this as a JavaScript assignment rather than JSON.  The
        payload is still JSON after the assignment prefix is removed, so parse
        it structurally and keep the source/date visible to the UI.
        """
        if not market_date:
            return {}
        requested = datetime.fromisoformat(market_date[:10]).date()
        response = None
        snapshot_date = None
        for offset in range(7):
            candidate = requested - timedelta(days=offset)
            if candidate.weekday() >= 5:
                continue
            date_key = candidate.strftime("%Y%m%d")
            url = f"https://www.hkex.com.hk/chi/csm/DailyStat/data_tab_daily_{date_key}c.js"
            candidate_response = await client.get(url, headers={
                "User-Agent": "Mozilla/5.0 Newma-Desk/1.0",
                "Referer": "https://www.hkex.com.hk/",
            })
            if candidate_response.status_code == 200:
                response = candidate_response
                snapshot_date = candidate
                break
        if response is None or snapshot_date is None:
            return {}
        raw = response.text.lstrip("\ufeff")
        start = raw.find("[")
        end = raw.rfind("]")
        if start < 0 or end <= start:
            return {}
        try:
            payload = json.loads(raw[start:end + 1])
        except json.JSONDecodeError:
            return {}

        result: dict[str, Any] = {"date": snapshot_date.isoformat(), "source": "HKEX 官方每日统计"}
        for item in payload if isinstance(payload, list) else []:
            market = str(item.get("market", ""))
            table = next((content.get("table") for content in item.get("content", [])
                          if isinstance(content, dict) and isinstance(content.get("table"), dict)), None)
            if not table:
                continue
            schema = table.get("schema", [[]])
            columns = schema[0] if schema and isinstance(schema[0], list) else []
            rows = []
            if table.get("classname") == "tradingTable":
                summary_values = []
                for row in table.get("tr", []):
                    cells = row.get("td", []) if isinstance(row, dict) else []
                    for cell in cells:
                        if isinstance(cell, list) and cell:
                            summary_values.append(cell[0] if not isinstance(cell[0], list) else cell[0][0])
                rows = [dict(zip(columns, summary_values, strict=False))] if summary_values else []
            for row in table.get("tr", []) if table.get("classname") != "tradingTable" else []:
                cells = row.get("td", []) if isinstance(row, dict) else []
                values = []
                for cell in cells:
                    if not isinstance(cell, list) or not cell:
                        continue
                    # Trading summary cells are one value per <tr>; top-ten
                    # rows carry the complete row inside the first cell.
                    values.extend(cell[0] if isinstance(cell[0], list) else [cell[0]])
                if values:
                    rows.append(dict(zip(columns, values, strict=False)))
            key = market.lower().replace(" ", "-")
            result[key] = {"market": market, "summary": rows[0] if rows else {}, "rows": rows}
        return result

    async def _fetch_northbound_history(
        self,
        client: httpx.AsyncClient,
        market_date: str | None,
    ) -> dict:
        """Fetch daily Stock Connect turnover without treating it as net flow."""
        if not self._tushare_token:
            return {
                "points": [], "status": "missing-token", "metric": "turnover",
                "reason": "Tushare 未配置，历史线未展示",
            }
        try:
            end = datetime.fromisoformat(
                (market_date or datetime.now().date().isoformat())[:10]
            ).date()
        except ValueError:
            end = datetime.now().date()
        start = end - timedelta(days=60)
        response = await client.post(
            "https://api.tushare.pro",
            json={
                "api_name": "moneyflow_hsgt",
                "token": self._tushare_token,
                "params": {
                    "start_date": start.strftime("%Y%m%d"),
                    "end_date": end.strftime("%Y%m%d"),
                },
                "fields": "trade_date,hgt,sgt,north_money",
            },
            headers={"User-Agent": "Newma-Desk/1.0"},
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") not in (0, None):
            return {
                "points": [], "status": "upstream-error", "metric": "turnover",
                "reason": "Tushare 历史接口异常，历史线未展示",
            }
        data = payload.get("data") or {}
        fields = data.get("fields") or []
        indexes = {name: index for index, name in enumerate(fields)}

        def amount(row: list[Any], field: str) -> float | None:
            index = indexes.get(field)
            if index is None or index >= len(row) or row[index] in (None, "", "-"):
                return None
            try:
                # moneyflow_hsgt monetary fields are expressed in millions of
                # their market currency. Northbound fields are RMB; the
                # southbound aggregate is HKD. This history view only charts
                # the northbound RMB fields.
                return round(float(row[index]) / 100, 4)
            except (TypeError, ValueError):
                return None

        points = []
        date_index = indexes.get("trade_date")
        for row in data.get("items") or []:
            if date_index is None or date_index >= len(row):
                continue
            raw_date = str(row[date_index])
            if len(raw_date) != 8:
                continue
            points.append({
                "date": f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}",
                "sseTurnoverYi": amount(row, "hgt"),
                "szseTurnoverYi": amount(row, "sgt"),
                "northTurnoverYi": amount(row, "north_money"),
            })
        points.sort(key=lambda item: item["date"])
        return {
            "points": points,
            "status": "ready" if points else "empty",
            "metric": "turnover",
            "currency": "CNY",
            "unit": "人民币亿元",
            "source": "Tushare moneyflow_hsgt（待 HKEX 同日校验）",
        }

    @staticmethod
    def _connect_summary(snapshot: dict, prefix: str) -> dict:
        item = snapshot.get(prefix, {}) if isinstance(snapshot, dict) else {}
        summary = item.get("summary", {}) if isinstance(item, dict) else {}
        northbound = prefix.endswith("-northbound")
        currency = "CNY" if northbound else "HKD"
        unit = "人民币亿元" if northbound else "港元亿元"

        def amount(name: str) -> float | None:
            value = summary.get(name)
            if value in (None, "", "-"):
                return None
            try:
                # HKEX reports Northbound in RMB million and Southbound in HKD
                # million. Divide by 100 to display hundred-millions while
                # preserving the currency explicitly in the response.
                return float(str(value).replace(",", "")) / 100
            except (TypeError, ValueError):
                return None
        buy = amount("Buy Turnover")
        sell = amount("Sell Turnover")
        return {
            "market": item.get("market"),
            "currency": currency,
            "unit": unit,
            "turnoverYi": amount("Total Turnover"),
            "buyYi": buy,
            "sellYi": sell,
            "netBuyYi": round(buy - sell, 4) if buy is not None and sell is not None else None,
            "etfTurnoverYi": amount("ETF Turnover"),
        }

    @classmethod
    def _validate_northbound_history(cls, history: dict, snapshot: dict) -> dict:
        """Only expose Tushare history after its latest point matches HKEX."""
        if not isinstance(history, dict):
            return {}
        result = {**history}
        points = [item for item in history.get("points", []) if isinstance(item, dict)]
        result["points"] = points
        if not points:
            return result

        official_date = str(snapshot.get("date") or "")
        sse_total = cls._connect_summary(snapshot, "sse-northbound").get("turnoverYi")
        szse_total = cls._connect_summary(snapshot, "szse-northbound").get("turnoverYi")
        latest = points[-1]
        latest_date = str(latest.get("date") or "")
        try:
            history_total = float(latest.get("northTurnoverYi"))
        except (TypeError, ValueError):
            history_total = None

        if not official_date or sse_total is None or szse_total is None:
            return {
                **result,
                "points": [],
                "status": "unverified",
                "reason": "HKEX 官方快照不可用，历史线未展示",
            }

        official_total = round(float(sse_total) + float(szse_total), 4)
        if latest_date != official_date:
            return {
                **result,
                "points": [],
                "status": "date-mismatch",
                "reason": "Tushare 与 HKEX 最新日期不一致，历史线未展示",
                "validation": {
                    "status": "date-mismatch",
                    "officialDate": official_date,
                    "historyDate": latest_date,
                },
            }
        if history_total is None:
            return {
                **result,
                "points": [],
                "status": "metric-mismatch",
                "reason": "字段口径不一致",
                "validation": {
                    "status": "metric-mismatch",
                    "date": official_date,
                    "officialTurnoverYi": official_total,
                },
            }

        difference = abs(history_total - official_total)
        threshold = max(0.5, abs(official_total) * 0.005)
        difference_pct = round(difference / abs(official_total) * 100, 4) if official_total else 0.0
        validation = {
            "status": "verified" if difference <= threshold else "metric-mismatch",
            "date": official_date,
            "officialTurnoverYi": official_total,
            "historyTurnoverYi": round(history_total, 4),
            "differenceYi": round(difference, 4),
            "differencePct": difference_pct,
            "thresholdPct": 0.5,
        }
        if difference > threshold:
            return {
                **result,
                "points": [],
                "status": "metric-mismatch",
                "reason": "字段口径不一致",
                "validation": validation,
            }
        return {
            **result,
            "status": "ready",
            "source": "Tushare moneyflow_hsgt（经 HKEX 同日总成交额校验）",
            "validation": validation,
        }

    @staticmethod
    def _risk_appetite(
        sectors: list[dict[str, Any]],
        *,
        sector_net: float,
        north: dict[str, Any],
        south: dict[str, Any],
        liquidity_regime: dict[str, Any] | None,
        top_turnover_yi: float,
        active: Any,
    ) -> dict[str, Any]:
        """Build explainable funding drivers without inventing a composite score."""
        drivers: list[dict[str, Any]] = []
        sector_rows = [item for item in sectors if isinstance(item, dict)]
        positive_sectors = sum(1 for item in sector_rows if float(item.get("net", 0) or 0) > 0)
        sector_count = len(sector_rows)
        if sector_count:
            sector_signal = (
                "supportive" if sector_net > 0 and positive_sectors >= sector_count / 2
                else "restrained" if sector_net < 0 and positive_sectors < sector_count / 2
                else "mixed"
            )
            drivers.append({
                "id": "sector-flow",
                "name": "行业资金",
                "signal": sector_signal,
                "value": f"{sector_net:+.2f} 亿元",
                "detail": f"{positive_sectors}/{sector_count} 个行业净流入",
                "source": "A Stock Data / AKShare",
            })
        else:
            drivers.append({
                "id": "sector-flow", "name": "行业资金", "signal": "unavailable",
                "detail": "行业净流序列未返回", "source": "A Stock Data / AKShare",
            })

        north_turnover = [
            item.get("turnoverYi")
            for item in (north.get("sse", {}), north.get("szse", {}))
            if item.get("turnoverYi") is not None
        ]
        history_points = (north.get("history") or {}).get("points") or []
        if not north_turnover and history_points:
            latest_turnover = history_points[-1].get("northTurnoverYi")
            if latest_turnover is not None:
                north_turnover = [latest_turnover]
        if north_turnover:
            north_unit = north.get("unit") or "人民币亿元"
            drivers.append({
                "id": "northbound-turnover",
                "name": "北向成交额",
                "signal": "observed",
                "value": f"{sum(float(value) for value in north_turnover):.2f} {north_unit}",
                "detail": "沪股通与深股通成交额，只反映活跃度，不代表净流入方向",
                "source": north.get("source") or "HKEX 官方每日统计",
                "asOf": north.get("date"),
            })
        else:
            drivers.append({
                "id": "northbound-turnover", "name": "北向成交额", "signal": "unavailable",
                "detail": "官方日成交额未返回", "source": north.get("source") or "HKEX 官方每日统计",
                "asOf": north.get("date"),
            })

        south_net = [
            item.get("netBuyYi")
            for item in (south.get("sse", {}), south.get("szse", {}))
            if item.get("netBuyYi") is not None
        ]
        if south_net:
            total_net = sum(float(value) for value in south_net)
            south_unit = south.get("unit") or "港元亿元"
            drivers.append({
                "id": "southbound-flow", "name": "南向净买入",
                "signal": "supportive" if total_net > 0 else "restrained" if total_net < 0 else "mixed",
                "value": f"{total_net:+.2f} {south_unit}",
                "detail": "港股通沪与港股通深的买入成交额减卖出成交额",
                "source": south.get("source") or "HKEX 官方每日统计",
                "asOf": south.get("date"),
            })
        else:
            drivers.append({
                "id": "southbound-flow", "name": "南向净买入", "signal": "unavailable",
                "detail": "官方日买入/卖出成交额未返回", "source": south.get("source") or "HKEX 官方每日统计",
                "asOf": south.get("date"),
            })

        liquidity_signal = str((liquidity_regime or {}).get("signal", "")).lower()
        liquidity_map = {"positive": "supportive", "negative": "restrained", "mixed": "mixed", "neutral": "observed"}
        if liquidity_regime and liquidity_signal in liquidity_map:
            drivers.append({
                "id": "macro-liquidity",
                "name": "宏观流动性",
                "signal": liquidity_map[liquidity_signal],
                "value": str(liquidity_regime.get("summary") or liquidity_signal),
                "detail": "宏观监测模块的状态标签，不与市场成交合并",
                "source": "Vibe Research / 宏观监测",
            })
        else:
            drivers.append({
                "id": "macro-liquidity", "name": "宏观流动性", "signal": "unavailable",
                "detail": "宏观流动性状态未返回", "source": "Vibe Research / 宏观监测",
            })

        drivers.append({
            "id": "market-activity",
            "name": "成交活跃度",
            "signal": "observed" if top_turnover_yi > 0 or active not in (None, "") else "unavailable",
            "value": str(active) if active not in (None, "") else (f"{top_turnover_yi:.2f} 亿元" if top_turnover_yi > 0 else None),
            "detail": f"成交额 TOP20 合计 {top_turnover_yi:.2f} 亿元；暂无历史基线，不判断强弱",
            "source": "交易行情聚合",
        })
        drivers.extend([
            {
                "id": "etf-flow", "name": "ETF 申赎", "signal": "unavailable",
                "detail": "基金份额与申赎序列尚未接入", "source": "基金公告 / 份额数据",
            },
            {
                "id": "market-leverage", "name": "全市场杠杆", "signal": "unavailable",
                "detail": "当前仅支持输入标的查询两融，全市场序列尚未接入", "source": "沪深交易所 / A Stock Data",
            },
        ])
        available = sum(1 for driver in drivers if driver["signal"] != "unavailable")
        return {"drivers": drivers, "available": available, "total": len(drivers)}

    async def dashboard(self, code: str | None = None) -> dict:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=False,
            trust_env=False,
        )
        paths = [
            "/api/market/overview",
            "/api/market/turnover-top",
            "/api/macro-monitor?days=30",
        ]
        if code:
            paths.extend([
                f"/api/fund-flow?{urlencode({'code': code})}",
                f"/api/margin?{urlencode({'code': code})}",
                f"/api/dragon-tiger?{urlencode({'code': code})}",
            ])
        results = await asyncio.gather(
            *(self._fetch(client, path) for path in paths),
            return_exceptions=True,
        )

        overview = results[0] if not isinstance(results[0], Exception) else {}
        turnover = results[1] if not isinstance(results[1], Exception) else {}
        macro = results[2] if not isinstance(results[2], Exception) else {}
        sectors = overview.get("sectors", []) if isinstance(overview, dict) else []
        sectors = sorted(sectors, key=lambda item: float(item.get("net", 0)), reverse=True)
        inflow = sum(float(item.get("inflow", 0) or 0) for item in sectors)
        outflow = sum(float(item.get("outflow", 0) or 0) for item in sectors)
        net = sum(float(item.get("net", 0) or 0) for item in sectors)
        leaders = turnover.get("stocks", []) if isinstance(turnover, dict) else []
        top_turnover = sum(float(item.get("amount", 0) or 0) for item in leaders)

        offset = 3
        raw_stock_flow = results[offset] if code and len(results) > offset and not isinstance(results[offset], Exception) else []
        stock_flow = self._clean_stock_flow(raw_stock_flow)
        margin = results[offset + 1] if code and len(results) > offset + 1 and not isinstance(results[offset + 1], Exception) else []
        dragon_tiger = results[offset + 2] if code and len(results) > offset + 2 and not isinstance(results[offset + 2], Exception) else {}
        sentiment = overview.get("sentiment", {}) if isinstance(overview, dict) else {}
        market_date = (sentiment.get("date") or overview.get("updated")) if isinstance(sentiment, dict) and isinstance(overview, dict) else None
        cross_result, north_history_result = await asyncio.gather(
            self._fetch_hkex_connect(client, market_date),
            self._fetch_northbound_history(client, market_date),
            return_exceptions=True,
        )
        cross_border = cross_result if isinstance(cross_result, dict) else {}
        north_history = north_history_result if isinstance(north_history_result, dict) else {}
        north_history = self._validate_northbound_history(north_history, cross_border)
        if owns_client:
            await client.aclose()
        north = {
            "sse": self._connect_summary(cross_border, "sse-northbound"),
            "szse": self._connect_summary(cross_border, "szse-northbound"),
            "history": north_history,
            "source": cross_border.get("source", "HKEX 官方每日统计"),
            "date": cross_border.get("date", market_date),
            "currency": "CNY",
            "unit": "人民币亿元",
        }
        south = {
            "sse": self._connect_summary(cross_border, "sse-southbound"),
            "szse": self._connect_summary(cross_border, "szse-southbound"),
            "source": cross_border.get("source", "HKEX 官方每日统计"),
            "date": cross_border.get("date", market_date),
            "currency": "HKD",
            "unit": "港元亿元",
        }
        north_ready = any(item.get("turnoverYi") is not None for item in (north["sse"], north["szse"])) or bool(north_history.get("points"))
        south_ready = any(item.get("turnoverYi") is not None for item in (south["sse"], south["szse"]))
        macro_liquidity = macro.get("liquidity", {}) if isinstance(macro, dict) and isinstance(macro.get("liquidity", {}), dict) else {}
        liquidity_rows = macro_liquidity.get("indicators", []) or (macro.get("indicators", []) if isinstance(macro, dict) else [])
        liquidity_regime = macro.get("regime", {}).get("liquidity") if isinstance(macro, dict) else None
        active = sentiment.get("active") if isinstance(sentiment, dict) else None
        top_turnover_yi = top_turnover / 100_000_000
        risk_appetite = self._risk_appetite(
            sectors,
            sector_net=net,
            north=north,
            south=south,
            liquidity_regime=liquidity_regime if isinstance(liquidity_regime, dict) else None,
            top_turnover_yi=top_turnover_yi,
            active=active,
        )
        upstream_ok = bool(sectors or leaders)
        return {
            "schemaVersion": "newma-desk.capital-flow.v1",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "marketDate": market_date,
            "summary": {
                "sectorNetYi": round(net, 2),
                "sectorInflowYi": round(inflow, 2),
                "sectorOutflowYi": round(outflow, 2),
                "top20TurnoverYi": round(top_turnover_yi, 2),
                "active": active,
            },
            "sectors": sectors,
            "turnoverLeaders": leaders[:20],
            "security": {"code": code, "fundFlow": stock_flow, "margin": margin, "dragonTiger": dragon_tiger} if code else None,
            "crossBorder": {"northbound": north, "southbound": south},
            "liquidity": {
                "indicators": liquidity_rows,
                "groups": macro_liquidity.get("groups", []),
                "forecast": macro_liquidity.get("forecast"),
                "coverage": macro_liquidity.get("coverage"),
                "note": macro_liquidity.get("note"),
                "regime": liquidity_regime,
                "source": macro_liquidity.get("source", "Vibe Research / 宏观监测"),
            },
            "riskAppetite": risk_appetite,
            "dimensions": [
                {"id": "market", "name": "市场成交", "status": "ready" if leaders else "degraded", "frequency": "盘中/日频", "lag": "约 5 分钟", "source": "交易行情聚合"},
                {"id": "sector", "name": "行业资金", "status": "ready" if sectors else "degraded", "frequency": "盘中", "lag": "约 5 分钟", "source": "A Stock Data / AKShare"},
                {"id": "northbound", "name": "北向资金", "status": "ready" if north_ready else "degraded", "frequency": "日频", "lag": "收盘后", "source": "HKEX 官方 / Tushare", "note": "展示沪股通、深股通成交额历史，单位人民币亿元；成交额不等于净流入。"},
                {"id": "southbound", "name": "南向资金", "status": "ready" if south_ready else "degraded", "frequency": "日频", "lag": "收盘后", "source": "HKEX 官方每日统计", "note": "净买入 = 买入成交额 - 卖出成交额，单位港元亿元。"},
                {"id": "margin", "name": "杠杆资金", "status": "ready" if code and margin else "on-demand", "frequency": "日频", "lag": "T+1", "source": "沪深交易所 / A Stock Data"},
                {"id": "main-flow", "name": "主力资金", "status": "ready" if code and stock_flow else "on-demand", "frequency": "日频", "lag": "约 15 分钟", "source": "A Stock Data / 东财 + 新浪回退", "note": "东财为空或被风控时自动切换新浪日度资金流。"},
                {"id": "lhb", "name": "龙虎榜", "status": "ready" if code and dragon_tiger else "on-demand", "frequency": "日频", "lag": "收盘后", "source": "A Stock Data / 东财"},
                {"id": "etf", "name": "ETF 申赎", "status": "planned", "frequency": "日频", "lag": "T+1", "source": "基金份额与净值公告", "note": "当前研究服务尚未提供份额序列，暂不展示估算值。"},
                {"id": "liquidity", "name": "宏观流动性", "status": "ready" if liquidity_rows else "degraded", "frequency": "日/周/月", "lag": "按指标发布", "source": "Vibe Research / 金十与央行口径", "note": "M2、LPR及宏观流动性状态分开展示。"},
            ],
            "sources": [
                {"name": "HKEX 沪深港通", "url": "https://www.hkex.com.hk/Mutual-Market/Stock-Connect/Statistics/Historical-Daily"},
                {"name": "Tushare 沪深港通日线", "url": "https://tushare.pro/document/search?q=%E6%B2%AA%E6%B7%B1%E6%B8%AF%E9%80%9A%E8%B5%84%E9%87%91%E6%B5%81%E5%90%91"},
                {"name": "上海证券交易所", "url": "https://www.sse.com.cn/market/othersdata/margin/"},
                {"name": "深圳证券交易所", "url": "https://www.szse.cn/market/dealdata/margin/"},
                {"name": "中国人民银行", "url": "https://www.pbc.gov.cn/"},
            ],
            "upstream": {"status": "ready" if upstream_ok else "degraded", "base": "Vibe Research / a-stock-data"},
        }
