import pytest
from earnings_statements import statement_candidates


def pages(*body, currency=True, cover="2026年半年度报告全文"):
    first = [{"page": 1, "text": cover + "\n股票代码：300502"},
             {"page": 5, "text": "元、万元、亿元 指 人民币元、人民币万元、人民币亿元" if currency else "单位未说明"}]
    first.extend({"page": i, "text": ""} for i in range(6, 14))
    return first + [{"page": 36+i, "text": item} for i, item in enumerate(body)]


def test_consolidated_scope_cross_page_and_zero():
    result = statement_candidates(pages(
        "1、合并资产负债表\n2026年06月30日\n单位：元\n项目 期末余额 期初余额",
        "资产总计 1,000.00 900.00\n负债合计 0.00 100.00\n2、母公司资产负债表\n资产总计 999.00 888.00",
        "3、合并利润表\n单位：元\n项目 2026年半年度 2025年半年度",
        "五、净利润（净亏损以“—”号填列） 100.00 80.00\n1.归属于母公司股东的净利润 99.00 77.00\n4、母公司利润表\n净利润 120.00 88.00",
        "5、合并现金流量表\n单位：元\n项目 2026年半年度 2025年半年度\n经营活动产生的现金流量净额 20.00 18.00",
    ), "300502")
    facts = {row["id"]: row for row in result["facts"]}
    assert {key: row["value"] for key, row in facts.items()} == {"assets": 1000, "liabilities": 0, "net_income": 100, "operating_cash_flow": 20}
    assert facts["assets"]["page"] == 37 and facts["assets"]["headerPage"] == 36
    assert facts["net_income"]["periodStart"] == "2026-01-01"
    assert facts["assets"]["periodStart"] is None
    assert result["currencyEvidence"]["page"] == 5


@pytest.mark.parametrize("change", ["missing-current", "three-columns", "unknown-currency", "wrong-period", "restatement", "parent-only"])
def test_uncertain_column_or_scope_is_not_guessed(change):
    header = "合并资产负债表\n2026年06月30日\n单位：元\n项目 期末余额 期初余额"
    row = "资产总计 100.00 80.00"
    if change == "missing-current": row = "资产总计   —   80.00"
    if change == "three-columns": row += " 70.00"
    if change == "wrong-period": header = header.replace("06月", "03月")
    if change == "restatement": header += "\n调整前 调整后"
    if change == "parent-only": header = header.replace("合并", "母公司")
    assert statement_candidates(pages(header + "\n" + row, currency=change != "unknown-currency"), "300502")["facts"] == []


def test_annual_explicit_date_columns_and_unit_scaling():
    result = statement_candidates(pages("合并资产负债表\n单位：万元 币种：人民币\n项目 2025年12月31日 2024年12月31日\n资产总计 100.00 80.00",
                                        currency=False, cover="2025年年度报告全文"), "300502")
    assert result["periodEnd"] == "2025-12-31"
    assert result["facts"][0]["value"] == 1000000


@pytest.mark.parametrize("header", ["项目 2025年度 2024年度", "项目 2025 年度 2024 年度", "项目 2025年年度 2024年年度"])
def test_annual_flow_headers_preserve_period_and_consolidated_scope(header):
    result = statement_candidates(pages(
        "3、合并利润表\n单位：元\n" + header,
        "五、净利润（净亏损以“－”号填列） 9,553,276,217.15 2,837,813,624.37\n"
        "1.归属于母公司股东的净利润 9,531,922,730.17 2,837,813,624.37\n"
        "4、母公司利润表\n单位：元\n" + header + "\n净利润 10,149,097,046.30 1,555,945,935.24",
        "5、合并现金流量表\n单位：元\n" + header,
        "经营活动产生的现金流量净额 7,701,234,651.00 640,930,145.58\n"
        "6、母公司现金流量表\n单位：元\n" + header + "\n经营活动产生的现金流量净额 7,290,251,191.03 989,096,129.11",
        cover="2025年年度报告全文"), "300502")
    facts = {row["id"]: row for row in result["facts"]}
    assert {key: row["value"] for key, row in facts.items()} == {
        "net_income": 9553276217.15, "operating_cash_flow": 7701234651.00}
    assert result["basis"] == "annual"
    for key, page in (("net_income", 37), ("operating_cash_flow", 39)):
        assert facts[key]["page"] == page and facts[key]["headerPage"] == page - 1
        assert facts[key]["asOf"] == "2025-12-31"
        assert facts[key]["periodStart"] == "2025-01-01"


@pytest.mark.parametrize("header", [
    "项目 2024年度 2025年度", "项目 2026年度 2025年度",
    "项目 2025年半年度 2024年半年度", "项目 2025年度 2024年度 2023年度",
])
def test_annual_flow_rejects_wrong_order_period_or_extra_columns(header):
    result = statement_candidates(pages(
        "合并利润表\n单位：元\n" + header + "\n净利润 100.00 80.00",
        "合并现金流量表\n单位：元\n" + header + "\n经营活动产生的现金流量净额 20.00 18.00",
        cover="2025年年度报告全文"), "300502")
    assert not result["facts"]


def test_identity_and_duplicate_conflict():
    with pytest.raises(ValueError, match="同一证券"):
        statement_candidates(pages(), "600519")
    with pytest.raises(ValueError, match="完整财报"):
        statement_candidates(pages(cover="2026年半年度报告摘要"), "300502")
    result = statement_candidates(pages("合并资产负债表\n2026年06月30日\n单位：元\n项目 期末余额 期初余额\n资产总计 100.00 80.00\n资产总计 101.00 80.00"), "300502")
    assert not result["facts"]
    assert "assets" in result["warnings"][-1]


def test_changed_column_order_cannot_reuse_previous_page_header():
    result = statement_candidates(pages("合并资产负债表\n2026年06月30日\n单位：元\n项目 期末余额 期初余额",
                                        "项目 期初余额 期末余额\n资产总计 100.00 80.00"), "300502")
    assert not result["facts"]


def test_statement_route_validates_input_and_does_not_write_snapshot(monkeypatch):
    from fastapi.testclient import TestClient
    import app
    calls = []
    def extract(code, announcement, source="eastmoney"):
        calls.append((code, announcement))
        return {"symbol": code, "facts": [], "contentOrigin": "pdf-text"}
    monkeypatch.setattr(app.astock, "announcement_statement_evidence", extract)
    client = TestClient(app.app)
    params = {"code": "300502", "announcementId": "AN202608240006746577"}
    response = client.get("/api/equity-research/statement-evidence", params=params)
    assert response.status_code == 200
    assert response.json()["data"]["facts"] == []
    assert client.get("/api/equity-research/statement-evidence", params={**params, "code": "bad"}).status_code == 422
    assert len(calls) == 1
    def failed(*_): raise ValueError("未确认同一证券")
    monkeypatch.setattr(app.astock, "announcement_statement_evidence", failed)
    assert client.get("/api/equity-research/statement-evidence", params=params).status_code == 422


def test_statement_route_requires_explicit_cninfo_choice(monkeypatch):
    from fastapi.testclient import TestClient
    import app
    calls=[]
    def extract(code, announcement, source):
        calls.append((code, announcement, source))
        return {'symbol':code, 'announcementSource':source, 'facts':[]}
    monkeypatch.setattr(app.astock, 'announcement_statement_evidence', extract)
    client=TestClient(app.app)
    response=client.get('/api/equity-research/statement-evidence', params={'code':'300502','announcementId':'1225499406','source':'cninfo'})
    assert response.status_code==200 and calls==[('300502','1225499406','cninfo')]
    assert client.get('/api/equity-research/statement-evidence', params={'code':'300502','announcementId':'1225499406','source':'other'}).status_code==422
