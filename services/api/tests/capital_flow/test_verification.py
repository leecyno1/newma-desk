from datetime import date
import json

import httpx
import pytest

from vibe_visualization_api.capital_flow.verification import CapitalVerificationService, execution_delta, parse_repurchase
from vibe_visualization_api.capital_flow.store import CapitalHistoryStore


def body(amount="1,520,943,540.21", shares="1,083,323", month=4):
    return f"""证券代码：600519
回购方案首次披露日 2025/11/6
预计回购金额 人民币15亿元（含）～人民币30亿元（含）
回购价格上限 1,863.67元/股
√减少注册资本
回购用途 □用于员工持股计划
累计已回购股数 {shares}股
累计已回购金额 {amount}元
关于回购股份实施进展的公告
截至2026年{month}月底，公司已累计回购股份。
"""


def test_extract_only_labelled_cumulative_fields_and_documented_signature():
    parsed = parse_repurchase(body(), "600519")
    assert parsed["planDate"] == "2025-11-06" and parsed["planSignature"]
    assert parsed["cumulativeAmountYi"] == pytest.approx(15.2094354021)
    assert parsed["cumulativeSharesWan"] == 108.3323
    assert parsed["cumulativeAsOf"] == "2026-04-30" and parsed["stage"] == "实施进展"
    assert parsed["purpose"] == "减少注册资本"
    unknown = parse_repurchase("公司拟使用30亿元回购，本月支付100万元，预计数量20万股。", "600519")
    assert unknown["cumulativeAmountYi"] is None and unknown["planSignature"] is None
    currency_unknown = parse_repurchase(body().replace("人民币", "港元"), "600519")
    assert currency_unknown["currency"] is None and currency_unknown["cumulativeAmountYi"] is None


def test_delta_does_not_cross_plans_dates_or_non_cumulative_values():
    current = parse_repurchase(body(), "600519")
    previous = parse_repurchase(body("1,112,118,415.55", "794,176", 3), "600519")
    delta = execution_delta(current, previous)
    assert delta["amountYi"] == pytest.approx(4.088251) and delta["sharesWan"] == 28.9147
    assert delta["fromExclusive"] == "2026-03-31"
    for invalid in [None, {**previous, "planSignature": "other"}, {**previous, "purpose": "股权激励"},
                    {**previous, "cumulativeAsOf": current["cumulativeAsOf"]}, {**previous, "cumulativeAmountYi": 100}]:
        assert execution_delta(current, invalid)["amountYi"] is None


@pytest.mark.asyncio
async def test_matching_body_conflict_previous_evidence_and_cache(tmp_path):
    calls = []
    fail = False
    ambiguous = False
    def handler(request):
        calls.append(request)
        if request.method == "POST":
            payload = json.loads(request.content)
            fields = payload["fields"].split(",")
            rows = [{"ts_code": "600519.SH", "ann_date": ann, "end_date": end, "proc": "完成", "amount": amount, "vol": shares}
                    for ann, end, amount, shares in [("20260508", "20260430", 1520943540.21, 1083323), ("20260403", "20260331", 1112118415.55, 794176)]] if payload["api_name"] == "repurchase" else []
            return httpx.Response(200, json={"code": 0, "data": {"fields": fields, "items": [[row.get(field) for field in fields] for row in rows]}})
        if fail:
            return httpx.Response(503)
        if request.url.host == "np-anotice-stock.eastmoney.com":
            day = request.url.params["begin_time"]
            ann = "AN202605071822034858" if day == "2026-05-08" else "AN202604021820985327"
            candidates = [{"art_code": ann, "notice_date": day, "codes": [{"stock_code": "600519"}], "title": "贵州茅台关于回购股份实施进展的公告"},
                          {"art_code": "AN202604021820985328", "notice_date": day, "codes": [{"stock_code": "000001"}], "title": "其他股票回购股份的公告"}]
            if ambiguous:
                candidates.append({**candidates[0], "art_code": "AN202605071822034859"})
            return httpx.Response(200, json={"success": 1, "data": {"list": candidates, "total_hits": len(candidates)}})
        ann = request.url.params["art_code"]
        current = ann.startswith("AN202605")
        return httpx.Response(200, json={"success": 1, "data": {"art_code": ann, "notice_date": "2026-05-08" if current else "2026-04-03",
            "security": [{"stock": "600519"}], "notice_content": body() if current else body("1,112,118,415.55", "794,176", 3)}})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = CapitalVerificationService("test", CapitalHistoryStore(tmp_path / "capital.sqlite"), client=client, today=date(2026, 10, 14))
        result = await service.verify("600519", "repurchase", "2026-05-08")
        assert result["status"] == "ready" and len(result["items"]) == 1
        assert result["delta"]["amountYi"] == pytest.approx(4.088251)
        assert result["comparison"][-1]["status"] == "conflict"
        count = len(calls)
        await service.verify("600519", "repurchase", "2026-05-08")
        assert len(calls) == count
        fail = True
        saved = await service.verify("600519", "repurchase", "2026-05-08", refresh=True)
        assert saved["usingSaved"] and saved["delta"]["amountYi"] is None
        fail = False
        ambiguous = True
        result = await service.verify("600519", "repurchase", "2026-05-08", refresh=True)
        assert len(result["items"]) == 2 and result["delta"]["amountYi"] is None
