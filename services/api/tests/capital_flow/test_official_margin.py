import io
import json
import zipfile
from datetime import date
from urllib.parse import parse_qs
from xml.sax.saxutils import escape

import httpx
import pytest

from vibe_visualization_api.capital_flow.evidence import CapitalEvidenceService, compare_margin
from vibe_visualization_api.capital_flow.official_margin import bse_page, fetch_official_rows, szse_xlsx
from vibe_visualization_api.capital_flow.store import CapitalHistoryStore


DAY = "2026-10-13"
PRIOR = "2026-10-12"


def workbook(code="300308", buy=1_628_335_069, balance=29_278_520_594, unit="元"):
    rows = [["证券代码", "证券简称", f"融资买入额({unit})", f"融资余额({unit})"], [code, "测试股份", f"{buy:,}", f"{balance:,}"]]
    xml = '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
    for index, row in enumerate(rows, 1):
        xml += f'<row r="{index}">' + "".join(f'<c r="{chr(65+i)}{index}" t="inlineStr"><is><t>{escape(value)}</t></is></c>' for i, value in enumerate(row)) + '</row>'
    xml += '</sheetData></worksheet>'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("xl/worksheets/sheet1.xml", xml)
    return buffer.getvalue()


def szse_report(day=DAY, code="300308", buy="16.28", balance="292.78", pages=1):
    return {"metadata": {"subname": day, "tabkey": "tab2", "pagecount": pages,
                         "cols": {"jrrzmr": "融资买入额<br>(亿元)", "jrrzye": "融资余额<br>(亿元)"}},
            "data": [{"zqdm": code, "jrrzmr": buy, "jrrzye": balance}]}


def bse_response(day=DAY, code="920093", page=0, pages=2):
    row = {"zqdm": code, "rzye": 4_570_965, "rzmre": 307_725, "rzyeRound": "457.10", "rzmreRound": "30.77",
           "sxrq": {"year": 126, "month": 9, "date": int(day[-2:])}}
    payload = json.dumps([[{"content": [row], "totalPages": pages, "number": page}], day])
    return "cb(" + payload[:-13] + "'" + day + "']" + ")"


def test_szse_exact_yuan_not_rounded_grid_and_no_invented_repayment():
    rows = szse_xlsx(workbook(), "300308", DAY, szse_report())
    assert rows[0]["rzye"] == 29_278_520_594 and rows[0]["rzmre"] == 1_628_335_069
    assert rows[0]["rzche"] is None
    assert rows[0]["dateEvidence"]["reportDate"] == DAY
    with pytest.raises(ValueError, match="日期"):
        szse_xlsx(workbook(), "300308", DAY, szse_report(day=PRIOR))
    with pytest.raises(ValueError, match="单位"):
        szse_xlsx(workbook(unit="亿元"), "300308", DAY, szse_report())
    with pytest.raises(ValueError, match="冲突"):
        szse_xlsx(workbook(), "300308", DAY, szse_report(balance="290.00"))
    assert szse_xlsx(workbook(code="300001"), "300308", DAY, szse_report()) == []


def test_partial_comparison_has_three_matching_fields_without_residual():
    case = {"previousBalanceYuan": 1000, "buyYuan": 30, "repayYuan": 20, "balanceYuan": 1010}
    result = compare_margin(case, {"rzye": 1010, "rzmre": 30}, {"rzye": 1000})
    assert result["status"] == "partial" and result["available"] == result["matched"] == 3
    assert result["referenceResidualYuan"] is None
    assert result["fields"][2]["referenceYuan"] is None


@pytest.mark.asyncio
async def test_szse_filters_security_and_requires_matching_report_day(tmp_path):
    def handler(request):
        assert request.url.params["txtZqdm"] == "300308" and request.url.params["TABKEY"] == "tab2"
        return httpx.Response(200, json=[szse_report()]) if request.url.params["SHOWTYPE"] == "JSON" else httpx.Response(200, content=workbook())
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert (await fetch_official_rows(client, "SZ", "300308", DAY))[0]["rzye"] == 29_278_520_594
        with pytest.raises(ValueError, match="日期"):
            await fetch_official_rows(client, "SZ", "300308", PRIOR)


@pytest.mark.asyncio
async def test_bse_strict_date_and_second_page_exact_units():
    called = []
    def handler(request):
        page = int(parse_qs(request.content.decode())["page"][0])
        called.append(page)
        return httpx.Response(200, text=bse_response(code="920001" if page == 0 else "920093", page=page))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        rows = await fetch_official_rows(client, "BJ", "920093", DAY)
    assert called == [0, 1] and rows[0]["page"] == 1
    assert rows[0]["rzye"] == 4_570_965 and rows[0]["rzmre"] == 307_725 and rows[0]["rzche"] is None
    assert bse_page(bse_response(), DAY)["totalPages"] == 2
    with pytest.raises(ValueError, match="日期"):
        bse_page(bse_response(), PRIOR)


@pytest.mark.asyncio
async def test_bse_over_bound_is_failure_not_no_security():
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, text=bse_response(code="920001", pages=17)))) as client:
        with pytest.raises(ValueError, match="16页"):
            await fetch_official_rows(client, "BJ", "920093", DAY)


@pytest.mark.asyncio
@pytest.mark.parametrize("exchange,code", [("SZ", "300308"), ("BJ", "920093")])
async def test_audit_normal_day_partial_official_confirmation_and_failed_update(tmp_path, exchange, code):
    failing = False
    def handler(request):
        nonlocal failing
        if request.url.host == "api.tushare.pro":
            body = json.loads(request.content)
            fields = body["fields"].split(",")
            rows = [{"cal_date": day.replace("-", ""), "is_open": 1} for day in [PRIOR, DAY]] if body["api_name"] == "trade_cal" else [
                {"ts_code": f"{code}.{exchange}", "trade_date": PRIOR.replace("-", ""), "rzye": 1000, "rzmre": 30, "rzche": 20},
                {"ts_code": f"{code}.{exchange}", "trade_date": DAY.replace("-", ""), "rzye": 1010, "rzmre": 30, "rzche": 20}]
            return httpx.Response(200, json={"code": 0, "data": {"fields": fields, "items": [[row.get(field) for field in fields] for row in rows]}})
        if failing:
            return httpx.Response(503)
        if exchange == "SZ":
            day = request.url.params["txtDate"]
            balance = 1010 if day == DAY else 1000
            return httpx.Response(200, json=[szse_report(day=day, buy="0.00", balance="0.00")]) if request.url.params["SHOWTYPE"] == "JSON" else httpx.Response(200, content=workbook(buy=30, balance=balance))
        day = parse_qs(request.content.decode())["transDate"][0]
        row = {"zqdm": code, "rzye": 1010 if day == DAY else 1000, "rzmre": 30, "sxrq": {"year": 126, "month": 9, "date": int(day[-2:])}}
        return httpx.Response(200, text="cb(" + json.dumps([[{"totalPages": 1, "content": [row]}], day]) + ")")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        service = CapitalEvidenceService("test", CapitalHistoryStore(tmp_path / "history.sqlite"), client=client, today=date(2026, 10, 14))
        result = await service._audit(client, code, f"{code}.{exchange}", DAY, False)
        assert result["cases"] == [] and result["dates"] == [DAY]
        assert result["official"]["status"] == "partial-verified"
        assert result["official"]["comparison"]["referenceResidualYuan"] is None
        assert result["official"]["missingFields"] == ["融资偿还额"]
        failing = True
        saved = await service._audit(client, code, f"{code}.{exchange}", DAY, True)
        assert saved["official"]["status"] == "unavailable"
        assert saved["official"]["current"]["usingSaved"]
