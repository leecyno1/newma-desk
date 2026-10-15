from __future__ import annotations

import asyncio
import calendar
from datetime import date, datetime, timezone
import re

import httpx

from vibe_visualization_api.capital_flow.research import iso_date
from vibe_visualization_api.capital_flow.supply import CapitalSupplyService


DATE = r"(20\d{2})[年/.-](\d{1,2})[月/.-](\d{1,2})日?"
TOPICS = {"repurchase": ("回购",), "stk_holdertrade": ("增持", "减持", "持股变动"), "share_float": ("限售", "解禁", "解除限售")}


def parse_repurchase(text: str, code: str) -> dict:
    compact = re.sub(r"\s+", "", text)
    quotes = []
    def number(pattern, units):
        match = re.search(pattern, compact)
        if not match:
            return None
        quotes.append(match.group(0))
        return float(match.group(1).replace(",", "")) * units[match.group(2)]
    amount = number(r"(?:累计已回购金额|实际回购金额)([\d,]+(?:\.\d+)?)(亿元|万元|元)", {"亿元": 1e8, "万元": 1e4, "元": 1})
    shares = number(r"(?:累计已回购股数|实际回购股数)([\d,]+(?:\.\d+)?)(万股|股)", {"万股": 1e4, "股": 1})
    first = re.search(r"回购方案首次披露日" + DATE, compact)
    plan_date = date(*(int(part) for part in first.groups())).isoformat() if first else None
    if first:
        quotes.append(first.group(0))
    budget = re.search(r"预计回购金额(?:人民币)?([\d.]+)亿元[^。]{0,15}?[～~至-](?:人民币)?([\d.]+)亿元", compact)
    cap = re.search(r"回购价格(?:上限|不超过)([\d,.]+)元/股", compact)
    purpose = re.search(r"√([^□\n]{2,20}?)(?=□|回购用途|实际|累计)", compact)
    currency = "CNY" if re.search(r"预计回购金额人民币", compact) else None
    # This is a documented scheme signature, not a fabricated official scheme ID.
    signature = f"{code}:{plan_date}:{budget.group(1)}:{budget.group(2)}:{cap.group(1).replace(',', '')}" if currency and plan_date and budget and cap else None
    quotes.extend(match.group(0) for match in (budget, cap, purpose) if match)
    as_of = None
    cutoff = re.search(r"截至(20\d{2})年(\d{1,2})月底", compact)
    if cutoff:
        year, month = map(int, cutoff.groups())
        as_of = date(year, month, calendar.monthrange(year, month)[1]).isoformat()
        quotes.append(cutoff.group(0))
    complete = re.search(DATE + r"[,，]?公司回购股份实施完成", compact)
    if complete:
        as_of = date(*(int(part) for part in complete.groups())).isoformat()
        quotes.append(complete.group(0))
    stage = "完成" if complete else "实施进展" if amount is not None and "回购股份实施进展" in compact else "待核验"
    return {"planSignature": signature, "planDate": plan_date, "signatureBasis": "证券代码、方案首次披露日、预算上下限、价格上限；不是官方方案ID",
            "purpose": purpose.group(1) if purpose else None, "currency": currency, "cumulativeAmountYi": amount / 1e8 if currency and amount is not None else None,
            "cumulativeSharesWan": shares / 1e4 if shares is not None else None, "cumulativeAsOf": as_of,
            "stage": stage, "quotes": quotes}


def execution_delta(current: dict, previous: dict | None) -> dict:
    blocked = {"status": "unverified", "amountYi": None, "sharesWan": None,
               "note": "未确认同方案特征、累计字段与截止日，未计算执行差额"}
    if not previous or not current.get("planSignature") or current["planSignature"] != previous.get("planSignature"):
        return blocked
    if not current.get("purpose") or current["purpose"] != previous.get("purpose"):
        return blocked
    start, end = previous.get("cumulativeAsOf"), current.get("cumulativeAsOf")
    if not start or not end or start >= end:
        return blocked
    fields = ("cumulativeAmountYi", "cumulativeSharesWan")
    if any(current.get(field) is None or previous.get(field) is None or current[field] < previous[field] for field in fields):
        return blocked
    return {"status": "signature-matched", "amountYi": round(current[fields[0]] - previous[fields[0]], 6),
            "sharesWan": round(current[fields[1]] - previous[fields[1]], 4), "fromExclusive": start, "toInclusive": end,
            "note": "同方案特征的累计披露差额，不是当日净买入；缺少官方方案ID，仍需复核方案变更及交易费用口径"}


class CapitalVerificationService(CapitalSupplyService):
    async def _documents(self, client, code: str, kind: str, ann_date: str, refresh: bool) -> dict:
        dataset = f"eastmoney:supply:{kind}"
        rows, run = await asyncio.to_thread(self.store.read, dataset, code, ann_date, ann_date)
        now = datetime.now(timezone.utc)
        if rows and not refresh and run and (now - datetime.fromisoformat(run["received_at"])).total_seconds() < 900:
            saved = rows[0]["result"]
            return {**saved, "items": [{**item, "parsed": parse_repurchase(item["text"], code) if kind == "repurchase" and item["text"] else None} for item in saved["items"]]}
        result = {"status": "unavailable", "reason": "公告来源不可用", "items": [], "source": "东方财富公司公告镜像", "receivedAt": now.isoformat()}
        try:
            response = await client.get("https://np-anotice-stock.eastmoney.com/api/security/ann", params={
                "stock_list": code, "begin_time": ann_date, "end_time": ann_date, "page_size": 100,
                "page_index": 1, "ann_type": "A", "client_source": "web", "sr": -1})
            response.raise_for_status()
            payload = response.json()
            if payload.get("success") != 1:
                raise ValueError("公告列表返回异常")
            listing = payload.get("data") or {}
            candidates = [row for row in listing.get("list", []) if str(row.get("notice_date", ""))[:10] == ann_date
                and any(stock.get("stock_code") == code for stock in row.get("codes", []))
                and any(topic in row.get("title", "") for topic in TOPICS[kind])]
            items = []
            for row in candidates[:3]:
                art = row.get("art_code", "")
                if not re.fullmatch(r"AN\d{12,24}", art):
                    continue
                detail_response = await client.get("https://np-cnotice-stock.eastmoney.com/api/content/ann", params={
                    "art_code": art, "client_source": "web", "page_index": 1})
                detail_response.raise_for_status()
                detail_payload = detail_response.json()
                detail = detail_payload.get("data") or {}
                valid = detail_payload.get("success") == 1 and detail.get("art_code") == art and str(detail.get("notice_date", ""))[:10] == ann_date and any(stock.get("stock") == code for stock in detail.get("security", []))
                full_text = str(detail.get("notice_content") or "") if valid else ""
                text = full_text[:30000]
                parsed = parse_repurchase(text, code) if kind == "repurchase" and text else None
                items.append({"id": art, "title": row["title"], "date": ann_date,
                    "url": f"https://data.eastmoney.com/notices/detail/{code}/{art}.html",
                    "pdfUrl": f"https://pdf.dfcfw.com/pdf/H2_{art}_1.pdf", "text": text,
                    "textTruncated": len(full_text) > 30000,
                    "status": "body-read" if text else "title-only", "parsed": parsed,
                    "note": "证券代码、公告日与主题匹配的候选；镜像正文已读取不等于所有字段已核验"})
            result.update(status="ready" if items else "empty", reason="" if items else "该公告日未取得同标的同主题候选",
                          items=items, candidates=len(candidates), truncated=len(candidates) > 3 or listing.get("total_hits", 0) > 100)
        except (httpx.HTTPError, ValueError):
            if rows:
                return {**rows[0]["result"], "status": "unavailable", "reason": "更新失败，使用保存正文", "usingSaved": True}
        await asyncio.to_thread(self.store.save, dataset, code, [{"date": ann_date, "result": result}],
            start=ann_date, end=ann_date, status=result["status"], reason=result["reason"], received_at=now.isoformat())
        return result

    async def verify(self, code: str, kind: str, ann_date: str, *, refresh=False) -> dict:
        client = self.client or httpx.AsyncClient(timeout=15, trust_env=False)
        try:
            supply = await CapitalSupplyService(self.token, self.store, client=client, today=self.today).research(code)
            feed = next(feed for feed in supply["feeds"] if feed["id"] == kind)
            selected = [row for row in feed["items"] if row["annDate"] == ann_date]
            result = await self._documents(client, code, kind, ann_date, refresh)
            result = {**result, "code": code, "kind": kind, "annDate": ann_date,
                      "comparison": [], "sourceStatus": feed["status"], "sourceUsingSaved": feed["usingSaved"],
                      "delta": execution_delta({}, None), "previousDocument": None}
            if len(result["items"]) == 1 and kind == "repurchase" and len(selected) == 1:
                parsed = result["items"][0].get("parsed") or {}
                row = selected[0]
                for field, key in (("累计金额亿元", "cumulativeAmountYi"), ("累计数量万股", "cumulativeSharesWan")):
                    original = row["amountYi" if key == "cumulativeAmountYi" else "sharesWan"]
                    value = parsed.get(key)
                    result["comparison"].append({"field": field, "sourceValue": original, "documentValue": value,
                        "status": "unknown" if original is None or value is None else "consistent" if abs(original - value) < .00001 else "conflict"})
                result["comparison"].append({"field": "阶段", "sourceValue": row["progress"], "documentValue": parsed.get("stage"),
                    "status": "conflict" if row["stage"] == "完成披露" and parsed.get("stage") == "实施进展" else "reference"})
                preceding = sorted((item for item in feed["items"] if item["annDate"] and item["annDate"] < ann_date and item["endDate"] and item["sharesWan"] is not None), key=lambda item: item["annDate"], reverse=True)
                if preceding and result["status"] == "ready" and not result.get("usingSaved") and not result.get("truncated") and not result["items"][0].get("textTruncated"):
                    previous = await self._documents(client, code, kind, preceding[0]["annDate"], refresh)
                    if previous["status"] == "ready" and not previous.get("usingSaved") and not previous.get("truncated") and len(previous["items"]) == 1 and not previous["items"][0].get("textTruncated"):
                        previous_doc = previous["items"][0]
                        result["previousDocument"] = previous_doc
                        result["delta"] = execution_delta(parsed, previous_doc.get("parsed"))
            return result
        finally:
            if self.client is None:
                await client.aclose()
