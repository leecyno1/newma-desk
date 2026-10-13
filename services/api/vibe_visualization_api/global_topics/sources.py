"""Bounded public evidence reads; scenario assumptions are never observations."""
from __future__ import annotations

import asyncio
import csv
import html
import io
import math
import re
import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit

import httpx
from vibe_visualization_api.data_services.client import DataServiceClientError
from vibe_visualization_api.data_services.registry import DataServiceRegistryError
from .maritime import NGA_URL, maritime_evidence

FRED = "https://fred.stlouisfed.org/graph/fredgraph.csv"
FED_FEED = "https://www.federalreserve.gov/feeds/press_monetary.xml"
REGISTER = "https://www.federalregister.gov/api/v1/documents.json"


def number(value: Any) -> float | None:
    try:
        result = float(value) if not isinstance(value, bool) else math.nan
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def period(value: str, today: date) -> str | None:
    try:
        parsed = date.fromisoformat(value[:10])
        return parsed.isoformat() if parsed <= today else None
    except (ValueError, TypeError):
        return None


def plain(value: str | None) -> str:
    return " ".join(re.sub(r"<[^>]*>", " ", html.unescape(value or "")).split())


def public_url(value: str | None) -> str:
    parsed = urlsplit(value or "")
    return value if parsed.scheme in {"https", "http"} and parsed.netloc and not parsed.username else ""


def parse_fred(text: str, series_id: str, today: date) -> list[dict]:
    rows = []
    for item in csv.DictReader(io.StringIO(text)):
        observed = period(item.get("observation_date", item.get("DATE", "")), today)
        value = number(item.get(series_id))
        if observed and value is not None:
            rows.append({"date": observed, "value": value})
    return sorted(rows, key=lambda row: row["date"])


def year_over_year(rows: list[dict]) -> list[dict]:
    by_month = {row["date"][:7]: row["value"] for row in rows}
    result = []
    for row in rows:
        year, month = row["date"][:7].split("-")
        base = by_month.get(f"{int(year) - 1:04d}-{month}")
        if base is not None and base > 0:
            result.append({"date": row["date"], "value": round((row["value"] / base - 1) * 100, 3)})
    return result


def parse_fed_events(text: str, today: date) -> list[dict]:
    events = []
    for item in ET.fromstring(text.lstrip("\ufeff")).findall("./channel/item"):
        raw_date = item.findtext("pubDate")
        try:
            published_at = parsedate_to_datetime(raw_date).astimezone(UTC).isoformat() if raw_date else ""
            published = published_at[:10]
        except (ValueError, TypeError):
            published_at = published = ""
        if published and not period(published, today):
            continue
        url = public_url(item.findtext("link"))
        title = plain(item.findtext("title"))
        if url and title:
            events.append({"id": url, "date": published, "title": title,
                           "summary": plain(item.findtext("description"))[:700], "source": "Federal Reserve",
                           "sourceUrl": url, "evidenceKey": url, "publishedAt": published_at or None,
                           "evidenceType": "official-release"})
    return sorted(events, key=lambda row: row["date"], reverse=True)[:12]


class TopicSources:
    def __init__(self, *, tushare_token: str = "", crucix_snapshot: Callable[[], Awaitable[dict]],
                 maritime_snapshot: Callable[[], Awaitable[dict]] | None = None,
                 client: httpx.AsyncClient | None = None, clock: Callable[[], datetime] = lambda: datetime.now(UTC)):
        self.token = tushare_token
        self.crucix_snapshot = crucix_snapshot
        self.maritime_snapshot = maritime_snapshot
        self.client = client
        self.clock = clock
        self.cache: dict[str, tuple[datetime, Any]] = {}
        self.locks: dict[str, asyncio.Lock] = {}

    async def _source(self, key: str, label: str, url: str, loader: Callable[[], Awaitable[Any]]) -> dict:
        async with self.locks.setdefault(key, asyncio.Lock()):
            cached = self.cache.get(key)
            now = self.clock()
            status, reason = "ready", ""
            if cached is None or (now - cached[0]).total_seconds() >= 300:
                try:
                    data = await loader()
                    if data is None or data == []:
                        raise ValueError("没有可用观测")
                    cached = (self.clock(), data)
                    self.cache[key] = cached
                except (httpx.HTTPError, ValueError, ET.ParseError, RuntimeError, DataServiceClientError, DataServiceRegistryError) as error:
                    status = "stale" if cached else "unavailable"
                    reason = f"来源暂不可用（{type(error).__name__}）" + ("，保留上次成功数据" if cached else "")
            return {"id": key, "label": label, "url": url, "status": status, "reason": reason,
                    "collectedAt": cached[0].isoformat() if cached else None, "data": cached[1] if cached else None}

    async def snapshot(self, topic_id: str) -> dict:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as owned_client:
            client = self.client or owned_client
            if topic_id == "fed-rates":
                return await self._fed(client)
            return await self._external(topic_id, client)

    async def _fred(self, client: httpx.AsyncClient, series_id: str, days: int = 120) -> list[dict]:
        today = self.clock().date()
        response = await client.get(FRED, params={"id": series_id, "cosd": (today - timedelta(days=days)).isoformat(), "coed": today.isoformat()})
        response.raise_for_status()
        return parse_fred(response.text, series_id, today)

    async def _yield_curve(self, client: httpx.AsyncClient) -> dict:
        reason = "未配置 Tushare Token"
        if self.token:
            try:
                today = self.clock().date()
                response = await client.post("https://api.tushare.pro", json={
                    "api_name": "us_tycr", "token": self.token,
                    "params": {"start_date": (today - timedelta(days=120)).strftime("%Y%m%d"), "end_date": today.strftime("%Y%m%d")},
                    "fields": "date,y2,y10",
                })
                response.raise_for_status()
                data = response.json()
                if data.get("code") != 0:
                    raise ValueError("Tushare 暂不可用或无权限")
                fields = data.get("data", {}).get("fields", [])
                rows = []
                for values in data.get("data", {}).get("items", []):
                    row = dict(zip(fields, values))
                    raw_date = str(row.get("date", ""))
                    observed = period(f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}", today)
                    y2, y10 = number(row.get("y2")), number(row.get("y10"))
                    if observed and y2 is not None and y10 is not None:
                        rows.append({"date": observed, "value": round((y10 - y2) * 100, 2)})
                if rows:
                    return {"rows": sorted(rows, key=lambda row: row["date"]), "source": "Tushare Pro · us_tycr", "url": "https://tushare.pro/document/search?q=us_tycr", "note": "同日 10 年期减 2 年期收益率，百分点 × 100 转为基点。"}
                reason = "Tushare 未返回有效美债收益率"
            except (httpx.HTTPError, ValueError):
                reason = "Tushare 接口不可用或权限不足"
        rows = [{**row, "value": round(row["value"] * 100, 2)} for row in await self._fred(client, "T10Y2Y")]
        if not rows:
            raise ValueError("美债利差无有效观测")
        return {"rows": rows, "source": "FRED · T10Y2Y", "url": "https://fred.stlouisfed.org/series/T10Y2Y", "note": reason + "；回退同口径 FRED 10Y−2Y 利差，百分点 × 100 转为基点。"}

    async def _fed(self, client: httpx.AsyncClient) -> dict:
        async def announcements():
            response = await client.get(FED_FEED)
            response.raise_for_status()
            return parse_fed_events(response.text, self.clock().date())

        sources = await asyncio.gather(
            self._source("DFF", "FRED · 有效联邦基金利率", "https://fred.stlouisfed.org/series/DFF", lambda: self._fred(client, "DFF")),
            self._source("CPILFESL", "FRED / BLS · 核心 CPI", "https://fred.stlouisfed.org/series/CPILFESL", lambda: self._fred(client, "CPILFESL", 760)),
            self._source("yield-curve", "美债期限利差", "https://tushare.pro/document/search?q=us_tycr", lambda: self._yield_curve(client)),
            self._source("UNRATE", "FRED / BLS · 失业率", "https://fred.stlouisfed.org/series/UNRATE", lambda: self._fred(client, "UNRATE", 400)),
            self._source("fed-releases", "美联储货币政策公告", FED_FEED, announcements),
        )
        metrics, observations, series, gaps = [], [], [], []
        specs = [("DFF", "有效联邦基金利率", "%", "#38bdf8", 7), ("CPILFESL", "核心 CPI 同比（季调指数计算）", "%", "#f59e0b", 75),
                 ("yield-curve", "10Y−2Y 美债利差", "bp", "#a3e635", 7), ("UNRATE", "失业率", "%", "#c084fc", 75)]
        for source, (identifier, label, unit, color, max_days) in zip(sources, specs):
            rows = source["data"] or []
            note = "美国官方发布序列，经 FRED 提供；当前 Desk 尚未接入该项对应的 Tushare 序列。"
            if identifier == "CPILFESL":
                rows = year_over_year(rows)
                note = "CPILFESL 为季调核心 CPI 指数；按同月去年值计算同比，不等同于 BLS 非季调同比标题值。缺少去年同月时不计算。"
            elif identifier == "yield-curve" and rows:
                source["label"], source["url"], note = rows["source"], rows["url"], rows["note"]
                rows = rows["rows"]
            rows = rows[-120:]
            metric = self._metric(source, label, rows[-1] if rows else None, unit, max_days, note)
            metrics.append(metric)
            if not rows:
                gaps.append(f"{label}暂无可用观测")
            series.append({"id": identifier, "label": label, "color": color})
            observations.extend({**row, "seriesId": identifier, "unit": unit, "source": source["label"], "sourceUrl": source["url"]} for row in rows)
        gaps.append("CME FedWatch 降息概率尚未接入；手动情景权重不替代市场定价。")
        events = [{**event, "collectedAt": sources[-1]["collectedAt"], "sourceStatus": sources[-1]["status"]}
                  for event in sources[-1]["data"] or []]
        return self._result(sources, metrics, observations, series, events, gaps)

    async def _external(self, topic_id: str, client: httpx.AsyncClient) -> dict:
        async def read_crucix():
            payload = await self.crucix_snapshot()
            if not payload.get("macro"):
                raise ValueError("Crucix 未返回宏观数据")
            return payload

        async def read_maritime():
            if not self.maritime_snapshot:
                raise RuntimeError("航行警告读取器未接入")
            result = await self.maritime_snapshot()
            if result.get("error") or not isinstance(result.get("warnings"), list):
                raise ValueError("航行警告不可用")
            return result

        loaders = [self._source("crucix", "Crucix 来源快照", "/api/crucix/snapshot", read_crucix)]
        if topic_id == "hormuz":
            loaders.append(self._source("nga-maritime", "NGA 官方航行警告", NGA_URL, read_maritime))
        loaded = await asyncio.gather(*loaders)
        source = loaded[0]
        payload = source["data"] or {}
        if payload.get("asOf"):
            source["collectedAt"] = payload["asOf"]
        if payload.get("freshness", {}).get("status") == "stale":
            source["status"], source["reason"] = "stale", "上游快照已过期，保留来源日期"
        sources, metrics, observations, series, events, gaps = [source], [], [], [], [], []
        if topic_id == "hormuz":
            energy = {row["id"]: row for row in payload.get("macro", {}).get("energy", {}).get("observations", [])}
            for identifier, label, color in [("wti", "WTI 现货", "#38bdf8"), ("brent", "Brent 现货", "#f59e0b")]:
                raw = energy.get(identifier, {})
                provenance = raw.get("source") or {}
                evidence_source = {**source, "id": identifier, "label": provenance.get("label", label), "url": provenance.get("url", "")}
                if raw.get("freshness", {}).get("status") == "stale":
                    evidence_source["status"] = "stale"
                observed = period(raw.get("period", ""), self.clock().date())
                value = number(raw.get("value")) if raw.get("kind") == "spot" and raw.get("unit") == "美元/桶" else None
                row = {"date": observed, "value": value} if observed and value is not None and provenance.get("seriesId") else None
                metrics.append(self._metric(evidence_source, label, row, "美元/桶", 7, raw.get("note", "")))
                series.append({"id": identifier, "label": label, "color": color})
                if row:
                    observations.append({**row, "seriesId": identifier, "unit": "美元/桶", "source": evidence_source["label"], "sourceUrl": evidence_source["url"]})
                else:
                    gaps.append(f"{label}缺少同口径来源或日期")
            metrics.extend([self._missing("通道中断状态", "未接入可核验的航道状态"), self._missing("油轮运价", "未接入油轮运价序列")])
            maritime_source, maritime = maritime_evidence(loaded[1], self.clock())
            sources.append(maritime_source)
            gaps.extend(["能源价格只反映市场价格，不证明海峡中断或战事升级。", "已接入 NGA 广播快照，但不保证覆盖全部 NAVAREA IX 或 UKMTO 公告；UKMTO 独立通报与油轮运价仍未接入。"])
            for row in payload.get("news", []):
                if re.search(r"hormuz|persian gulf|霍尔木兹|波斯湾", row.get("title", ""), re.I) and public_url(row.get("url")):
                    raw_date = row.get("publishedAt") or ""
                    if raw_date and not period(raw_date, self.clock().date()):
                        continue
                    title = plain(row.get("title"))
                    if title:
                        events.append({"id": row["url"], "date": raw_date[:10], "title": title,
                                       "summary": "专题关键词匹配报道，需打开原文核验，不代表官方确认。",
                                       "source": row.get("source", "Crucix"), "sourceUrl": row["url"],
                                       "evidenceKey": row["url"], "publishedAt": raw_date or None,
                                       "collectedAt": source["collectedAt"], "sourceStatus": source["status"],
                                       "evidenceType": "news-report"})
        else:
            async def register():
                today = self.clock().date()
                response = await client.get(REGISTER, params={"per_page": 20, "order": "newest", "conditions[agencies][]": "industry-and-security-bureau", "conditions[term]": "China", "conditions[publication_date][gte]": (today - timedelta(days=365)).isoformat(), "conditions[publication_date][lte]": today.isoformat()})
                response.raise_for_status()
                result = response.json()
                if not isinstance(result.get("results"), list) or number(result.get("count")) is None:
                    raise ValueError("联邦公报结果不完整")
                return result
            documents = await self._source("bis-register", "Federal Register · BIS 涉华文件", "https://www.federalregister.gov/agencies/industry-and-security-bureau", register)
            sources.append(documents)
            for row in (documents["data"] or {}).get("results", []):
                observed = period(row.get("publication_date", ""), self.clock().date())
                url = public_url(row.get("html_url"))
                title = plain(row.get("title"))
                summary = plain(row.get("abstract"))
                # Full-text search also returns unrelated notices with an incidental body mention.
                relevant = re.search(r"\b(?:China|Chinese|Hong Kong|Macau|Taiwan|PRC)\b", f"{title} {summary}", re.I)
                if observed and url and title and relevant:
                    events.append({"id": row["document_number"], "date": observed, "title": title,
                                   "summary": summary[:700], "source": "Federal Register · BIS",
                                   "sourceUrl": url, "evidenceKey": url, "publishedAt": observed,
                                   "collectedAt": documents["collectedAt"], "sourceStatus": documents["status"],
                                   "evidenceType": "official-document", "documentType": row.get("type"),
                                   "note": "公布日期不是生效日期；涉华全文检索不代表全部中美贸易政策。"})
            count = (documents["data"] or {}).get("count")
            metrics.append({"label": "BIS 涉华文件（近 365 天）", "value": str(count) if count is not None else "—", "change": "全文含 China；不是全部贸易政策", "unit": "份", "source": documents["label"], "sourceUrl": documents["url"], "date": documents["collectedAt"], "dateBasis": "query-time", "status": documents["status"]})
            gscpi = payload.get("macro", {}).get("gscpi", {})
            observed = gscpi.get("period")
            value = number(gscpi.get("value"))
            month = period(f"{observed}-01", self.clock().date()) if observed else None
            row = {"date": month, "value": value} if month and value is not None else None
            gscpi_source = {**source, "label": "纽约联储 · GSCPI", "url": "https://www.newyorkfed.org/research/policy/gscpi"}
            if gscpi.get("freshness", {}).get("status") == "stale":
                gscpi_source["status"] = "stale"
            metrics.append(self._metric(gscpi_source, "全球供应链压力", row, "标准差", 80, "全球月度指标，不是中美双边制裁强度。"))
            metrics.extend([self._missing("出口限制强度", "无统一可核验量化口径"), self._missing("中方政策覆盖", "商务部、海关原文尚未接入")])
            series = [{"id": "GSCPI", "label": "全球供应链压力", "color": "#a3e635"}]
            if row:
                observations.append({**row, "seriesId": "GSCPI", "unit": "标准差", "source": gscpi_source["label"], "sourceUrl": gscpi_source["url"]})
            gaps.extend(["BIS 文件数量是近 365 天的全文检索命中数；事件列表只保留标题或摘要明确相关的文件，最多展示 20 条，不能视为完整政策清单。", "中方政策、双边贸易额与企业受限名单尚未完整接入。"])
        result = self._result(sources, metrics, observations, series, events, gaps)
        if topic_id == "hormuz":
            result["maritime"] = maritime
        return result

    def _metric(self, source: dict, label: str, row: dict | None, unit: str, max_days: int, note: str) -> dict:
        status = "unavailable" if not row else "stale" if source["status"] == "stale" or (self.clock().date() - date.fromisoformat(row["date"])).days > max_days else "ready"
        return {"label": label, "value": f"{row['value']:.2f}" if row else "—", "change": note,
                "unit": unit, "date": row["date"] if row else None, "dateBasis": "observation-period", "frequency": "monthly" if max_days >= 70 else "daily",
                "source": source["label"], "sourceUrl": source["url"], "collectedAt": source["collectedAt"], "status": status}

    @staticmethod
    def _missing(label: str, reason: str) -> dict:
        return {"label": label, "value": "—", "change": reason, "status": "unavailable"}

    @staticmethod
    def _result(sources, metrics, observations, series, events, gaps) -> dict:
        statuses = [row["status"] for row in sources + metrics]
        available = bool(observations or events or any(row["status"] == "ready" for row in metrics))
        return {"metrics": metrics, "observations": observations, "series": series, "events": events,
                "eventCoverage": {"count": len(events),
                                  "readySourceCount": sum(row.get("sourceStatus") == "ready" for row in events),
                                  "staleSourceCount": sum(row.get("sourceStatus") == "stale" for row in events)},
                "sources": [source["label"] for source in sources],
                "sourceStatus": [{key: value for key, value in source.items() if key != "data"} for source in sources],
                "gaps": gaps, "dataMode": "source-backed" if available else "unavailable", "dataAsOf": None,
                "freshness": "stale" if "stale" in statuses else "unknown" if "unavailable" in statuses else "fresh",
                "dataWarning": "观测值保留各自来源、单位与数据期，非实时行情；手动情景参数未由这些观测自动校准，不能作为事实或市场概率。"}
