import json
from datetime import date

import httpx
import pytest

from vibe_visualization_api.capital_flow.evidence import CapitalEvidenceService, board_disclosures, board_window, compare_margin, margin_cases
from vibe_visualization_api.capital_flow.store import CapitalHistoryStore


DATES = ["2026-09-11", "2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17"]
DAILY = "日涨幅达到15%的前5只证券"
THREE = "连续三个交易日内，涨幅偏离值累计达到30%的证券"
MARGINS = [{"date": day, "ts_code": "600519.SH", "rzye": balance, "rzmre": 30, "rzche": 20}
           for day, balance in zip(DATES, [1000, 1010, 1220, 1230, 1238])]


def record(reason=DAILY, **fields):
    return {"date": DATES[-1], "ts_code": "600519.SH", "reason": reason, "l_buy": 500, "l_sell": 100, "net_amount": 400, **fields}


def seat(name="具名营业部", side="0", reason=DAILY, **fields):
    return {"date": DATES[-1], "ts_code": "600519.SH", "reason": reason, "exalter": name, "side": side,
            "buy": 500, "sell": 100, "net_buy": 400, **fields}


def test_windows_follow_exchange_sessions_and_unknown_stays_unknown():
    assert board_window(THREE, DATES[-1], DATES)["start"] == "2026-09-15"
    assert board_window(DAILY, DATES[-1], DATES)["start"] == DATES[-1]
    assert board_window("未知上榜理由", DATES[-1], DATES)["sessions"] is None
    assert board_window(THREE, DATES[-1], [DATES[-1]])["start"] is None
    assert board_window(THREE, DATES[-1], [])["start"] is None


def test_named_cross_side_display_merge_but_generic_institutions_never_aggregate():
    rows = [seat(), seat(side="1"), seat("机构专用"), seat("机构专用", side="1"), seat("机构专用", buy=600, net_buy=500)]
    groups, unmatched = board_disclosures([record(), record(THREE)], rows, "600519.SH", DATES[-1], DATES)
    group = next(item for item in groups if item["reasonKey"] == DAILY)
    assert group["seats"][0]["sides"] == ["0", "1"]
    assert group["seats"][0]["disclosureCount"] == 2
    assert group["rawSeatCount"] == 5 and len(group["seats"]) == 4
    assert group["repeatedNamedRows"] == 1
    assert group["ambiguousSeatRows"] == 3
    assert group["seats"][1]["possibleRepeat"] is True
    assert group["seats"][-1]["possibleRepeat"] is False
    assert not group["aggregateSafe"] and unmatched == 0
    assert next(item for item in groups if item["reasonKey"] == THREE)["seats"] == []


def test_conflicting_amounts_and_unmatched_reason_preserve_raw_without_wrong_security_or_day():
    groups, unmatched = board_disclosures(
        [record(), record(net_amount=399), record(ts_code="600000.SH"), record(date=DATES[-2])],
        [seat(), seat(buy=600, net_buy=500), seat(reason=""), seat(date=DATES[-2]), seat(ts_code="600000.SH")],
        "600519.SH", DATES[-1], DATES)
    assert len(groups) == 1 and len(groups[0]["records"]) == 2
    assert groups[0]["amountConflict"] and groups[0]["netYuan"] is None
    assert len(groups[0]["seats"]) == 2 and unmatched == 1


def test_margin_raw_yuan_strict_previous_day_small_and_review():
    cases, checked = margin_cases(MARGINS, DATES)
    assert checked == 4
    assert [(item["date"], item["residualYuan"], item["size"]) for item in cases] == [(DATES[2], 200, "review"), (DATES[4], -2, "small")]
    assert cases[0]["previousRaw"] == MARGINS[1]
    reduced, count = margin_cases([row for row in MARGINS if row["date"] != DATES[1]], DATES)
    assert count == 2 and len(reduced) == 1
    compared = compare_margin(cases[0], MARGINS[2], MARGINS[1])
    assert compared["status"] == "agree" and compared["referenceResidualYuan"] == 200
    assert compare_margin(cases[0], {}, {})["status"] == "partial"
    assert compare_margin(cases[0], {**MARGINS[2], "rzye": 1222}, MARGINS[1])["status"] == "conflict"


def source_handler(*, bad_official=False, failing=False, calendar_failure=False):
    def handler(request):
        if request.method == "POST":
            body = json.loads(request.content)
            api = body["api_name"]
            if failing or (calendar_failure and api == "trade_cal"):
                return httpx.Response(503)
            if api == "trade_cal":
                rows = [{"cal_date": day.replace("-", ""), "is_open": 1} for day in DATES]
            elif api == "margin_detail":
                rows = [{**row, "trade_date": row["date"].replace("-", "")} for row in MARGINS]
            elif api in {"top_list", "top_inst"}:
                assert body["params"]["trade_date"] == "20260917"
                rows = [{**(record() if api == "top_list" else seat()), "trade_date": "20260917"}]
            else:
                raise AssertionError(api)
            fields = body["fields"].split(",")
            return httpx.Response(200, json={"code": 0, "data": {"fields": fields, "items": [[row.get(key) for key in fields] for row in rows]}})
        if "eastmoney" in request.url.host:
            assert "2026-09-11" in request.url.params["filter"]
            rows = [{"DATE": row["date"], "SCODE": "600519", "RZYE": row["rzye"], "RZMRE": row["rzmre"], "RZCHE": row["rzche"]} for row in MARGINS]
            return httpx.Response(200, json={"success": True, "result": {"pages": 1, "data": rows}})
        assert "sse" in request.url.host
        day = request.url.params["detailsDate"]
        row = next(row for row in MARGINS if row["date"].replace("-", "") == day)
        return httpx.Response(200, json={"result": [{**row, "opDate": "20260911" if bad_official else day,
                                                   "stockCode": "600000" if bad_official else "600519"}]})
    return handler


@pytest.mark.asyncio
async def test_service_official_confirms_values_not_cause_and_cache_is_single_day(tmp_path):
    async with httpx.AsyncClient(transport=httpx.MockTransport(source_handler())) as client:
        service = CapitalEvidenceService("test", CapitalHistoryStore(tmp_path / "history.sqlite"), client=client, today=date(2026, 9, 18))
        result = await service.research("600519")
        assert result["board"]["date"] == DATES[-1] and len(result["board"]["groups"]) == 1
        assert result["audit"]["checked"] == 4 and result["audit"]["confirmedInputs"]
        official = result["audit"]["official"]
        assert official["date"] == DATES[2] and official["status"] == "verified"
        assert official["comparison"]["referenceResidualYuan"] == 200
        assert "原因仍待核查" in official["reason"]
        assert result["audit"]["cases"][0]["mirrorComparison"]["status"] == "agree"
        selected = await service.research("600519", audit_date=DATES[4])
        assert selected["audit"]["official"]["date"] == DATES[4]
        assert selected["audit"]["official"]["comparison"]["referenceResidualYuan"] == -2


@pytest.mark.asyncio
async def test_wrong_official_code_and_date_cannot_confirm(tmp_path):
    async with httpx.AsyncClient(transport=httpx.MockTransport(source_handler(bad_official=True))) as client:
        result = await CapitalEvidenceService("test", CapitalHistoryStore(tmp_path / "history.sqlite"), client=client, today=date(2026, 9, 18)).research("600519")
    assert result["audit"]["official"]["status"] == "unavailable"
    assert result["audit"]["official"]["comparison"] is None


@pytest.mark.asyncio
async def test_saved_calendar_or_margin_cannot_generate_official_confirmation(tmp_path):
    store = CapitalHistoryStore(tmp_path / "history.sqlite")
    async with httpx.AsyncClient(transport=httpx.MockTransport(source_handler())) as client:
        await CapitalEvidenceService("test", store, client=client, today=date(2026, 9, 18)).research("600519")
    async with httpx.AsyncClient(transport=httpx.MockTransport(source_handler(calendar_failure=True))) as client:
        result = await CapitalEvidenceService("test", store, client=client, today=date(2026, 9, 18)).research("600519", refresh=True)
    assert result["audit"]["cases"] and not result["audit"]["confirmedInputs"]
    assert result["audit"]["official"]["status"] == "not-requested"
    assert result["board"]["groups"][0]["window"]["start"] is None
    async with httpx.AsyncClient(transport=httpx.MockTransport(source_handler(failing=True))) as client:
        failed = await CapitalEvidenceService("test", store, client=client, today=date(2026, 9, 18)).research("600519", refresh=True)
    assert failed["audit"]["coverage"]["usingSaved"]
    assert failed["audit"]["official"]["status"] != "verified"
    assert failed["board"]["recordsCoverage"]["usingSaved"]


@pytest.mark.asyncio
@pytest.mark.parametrize("payload,status", [
    ({"success": False, "code": 9201, "result": None}, "empty"),
    ({"success": False, "code": 9501, "result": None}, "upstream-error"),
    ({"success": True, "result": {"pages": 2, "data": []}}, "upstream-error"),
    ({"result": {"unexpected": "structure"}}, "upstream-error"),
])
async def test_public_failure_is_not_empty_or_silent_truncation(tmp_path, payload, status):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))) as client:
        service = CapitalEvidenceService("", CapitalHistoryStore(tmp_path / "history.sqlite"), client=client)
        result = await service._public_rows(client, "eastmoney:margin" if "success" in payload else "sse:margin", "test", DATES[0], DATES[-1],
            lambda: client.get("https://example.com/"), lambda row: row)
    assert result["status"] == status


@pytest.mark.asyncio
async def test_no_token_no_fake_zero_or_network_for_empty_audit(tmp_path):
    def no_network(request):
        raise AssertionError("No source without inputs")
    async with httpx.AsyncClient(transport=httpx.MockTransport(no_network)) as client:
        result = await CapitalEvidenceService("", CapitalHistoryStore(tmp_path / "history.sqlite"), client=client).research("920093")
    assert result["symbol"] == "920093.BJ"
    assert result["board"]["groups"] == []
    assert result["audit"]["checked"] == 0 and not result["audit"]["confirmedInputs"]
