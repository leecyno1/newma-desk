"""Selected ETF evidence and explicitly matched, retrospective policy references."""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit

from .etf_catalog import ETFCatalog
from .research import CapitalResearchService, iso_date
from .store import CapitalHistoryStore
from vibe_visualization_api.policy_analysis.store import PolicyStore


def policy_candidates(events: list[dict], documents: dict, *, code: str, aliases: list[str], as_of: date) -> dict:
    start, end = (as_of - timedelta(days=89)).isoformat(), as_of.isoformat()
    matches = []
    for event in events:
        document = documents.get(event["id"], {})
        # A saved official publication date overrides the event/calendar date.
        published = iso_date(document.get("publishedAt") or event.get("date"))
        if event.get("status") != "published" or not published or not start <= published <= end:
            continue
        url = event.get("sourceUrl", "")
        if urlsplit(url).scheme not in {"https", "http"} or not urlsplit(url).hostname:
            continue
        entities = [entity for entity in event.get("entities", [])
                    if (entity.get("type") == "industry" and entity.get("displayName") in aliases)
                    or (entity.get("assetType") == "etf" and entity.get("symbol") == code.split(".")[0])]
        if not entities:
            continue
        first_seen = event.get("firstSeenAt")
        try:
            seen_date = datetime.fromisoformat(first_seen.replace("Z", "+00:00")).astimezone(timezone(timedelta(hours=8))).date().isoformat()
        except (AttributeError, ValueError, TypeError):
            seen_date = None
        matches.append({"id": event["id"], "title": event["title"], "publishedDate": published,
            "dateBasis": "已保存正文发布日期" if document.get("publishedAt") else "政策记录日期，原文发布日期待核验",
            "institution": event.get("institution"), "sourceUrl": url,
            "firstSeenAt": first_seen, "documentFetchedAt": document.get("fetchedAt"),
            "documentStatus": document.get("status", "missing"),
            "timingLabel": "复盘日后入库，仅供事后参考" if seen_date and seen_date > end else "内容历史版本未核验",
            "matchedEntities": [{key: entity.get(key) for key in ("displayName", "type", "evidence", "source", "confidence")} for entity in entities],
            "pointInTimeVerified": False})
    matches.sort(key=lambda row: (row["publishedDate"], row["id"]), reverse=True)
    return {"items": matches[:8], "matchedCount": len(matches), "start": start, "end": end,
            "pointInTimeVerified": False,
            "note": "仅按明确行业实体/ETF代码关联；规则命中不证明受益方向。仅列截止日前90日已发布记录，不纳入排名或历史交易确认。"}


class MarketEvidenceService:
    def __init__(self, token: str, database_path, *, client=None):
        self.token, self.path, self.client = token, database_path, client

    async def research(self, code: str, as_of: date, industry: str, aliases: list[str], *, refresh=False):
        store = CapitalHistoryStore(self.path)
        catalog = await ETFCatalog(self.token, store, client=self.client).read()
        item = next((row for row in catalog["items"] if row["code"] == code), None)
        policy_store = PolicyStore(self.path)
        events, documents = await asyncio.gather(asyncio.to_thread(policy_store.list_events), asyncio.to_thread(policy_store.document_summaries))
        policies = policy_candidates(events, documents, code=code, aliases=aliases, as_of=as_of)
        etf = None
        if item:
            # Reuse the capital module's exact share/NAV math and historical store.
            result = await CapitalResearchService(self.token, store, client=self.client, today=as_of + timedelta(days=1)).research(
                refresh=refresh, samples=[(code, item["name"], "行业")])
            raw = result["etfs"][0]
            windows = raw["summary"]["strength"]
            for window in windows.values():
                if result["expectedDate"] != as_of.isoformat() or catalog["status"] != "ready" or catalog.get("usingSaved"):
                    window["current"] = False
                    window["reason"] = "目标交易日或ETF目录未核验；数值仅作参考"
            etf = {key: raw.get(key) for key in ("code", "name", "asOf", "source", "fetchStatus", "sourceNote", "usingSaved", "receivedAt", "note")}
            etf.update(windows=windows, current=all(window["current"] for window in windows.values()), pointInTimeVerified=False)
        return {"schemaVersion": "newma-desk.market-evidence.v1", "requestedDate": as_of.isoformat(),
            "code": code, "industry": industry, "aliases": aliases, "etf": etf, "policies": policies,
            "catalog": {"item": item, "status": catalog["status"], "reason": catalog["reason"],
                        "receivedAt": catalog["receivedAt"], "source": catalog["source"], "usingSaved": catalog["usingSaved"]},
            "notes": ["只研究所选ETF，不把一只代理ETF的申赎当成整个行业资金。",
                "跟踪指数来自当前ETF目录；行业关系来自轮动显式配置，不保证历史跟踪指数未变。",
                "申赎为份额变化×当日净值的估算，包含实物申赎与套利，不等于新增外部现金。",
                "按复盘截止日重算数据窗口；当前修订数据不等于当时可知快照，不能用于无前视偏差回测。",
                "政策仅展示已有记录，不重新采集、不改写政策记录；首次入库时间不等于政策发布时间。"]}
