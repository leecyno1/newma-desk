from pathlib import Path

import pytest

from earnings_import import extract_report
from earnings_revenue import revenue_candidates


def table(rows, unit="单位：元 币种：人民币", heading="主营业务分产品情况", header=None):
    header = header or f"{'分产品':<12}{'营业收入':<24}{'营业成本':<20}毛利率"
    return [{"page": 8, "text": "第三节 管理层讨论与分析\n" + unit + "\n" + heading + "\n" + header + "\n" + "\n".join(rows) + "\n(2). 产销量情况分析表\n不应采纳 888 999"}]


def row(label, amount, cost="100.00"):
    return f"{label:<12}{amount:<24}{cost:<20}90.00"


def test_real_revenue_tables_are_separate_and_preserve_wrapped_name():
    path = Path(__file__).resolve().parents[4] / "output/pdf/kweichow-moutai-2024-annual-report.pdf"
    if not path.exists():
        pytest.skip("Requires real Moutai filing")
    result = extract_report(path, "real", path.name, include_revenue=True)
    groups = {group["dimension"]: group for group in result["revenueGroups"]}
    assert set(groups) == {"industry", "product", "region", "channel"}
    assert all(group["page"] == 9 and group["scope"] == "main-business" for group in groups.values())
    products = groups["product"]["rows"]
    assert [item["label"] for item in products] == ["茅台酒", "其他系列酒"]
    assert products[0]["value"] == pytest.approx(1459.2807595531)
    assert products[1]["value"] == pytest.approx(246.8376209671)
    assert "\n酒" in products[1]["excerpt"]
    assert groups["product"]["total"] is None
    assert sum(item["value"] for item in products) == pytest.approx(1706.1183805202)
    assert next(item["value"] for item in result["candidates"] if item["id"] == "revenue") == pytest.approx(1708.9915227634)
    assert [item["label"] for item in groups["channel"]["rows"]] == ["批发代理", "直销"]


def test_missing_revenue_does_not_shift_cost_and_totals_are_not_rows():
    result = revenue_candidates(table([row("甲业务", "0.00"), row("乙业务", "—"), row("丙业务", ""), row("合计", "1,000.00")]))
    group = result["revenueGroups"][0]
    assert group["rows"][0]["value"] == 0
    assert len(group["rows"]) == 1
    assert group["total"]["value"] == 0.00001
    assert group["skippedRows"] == 2


def test_scope_currency_columns_and_restatements_require_review():
    for pages in [table([row("甲", "100.00")], unit="单位：元 币种：美元"),
                  table([row("甲", "100.00")], header="分产品    营业成本          营业收入"),
                  table(["调整前 调整后", row("甲", "100.00")]),
                  table([row("甲", "100.00"), row("甲", "200.00")])]:
        assert revenue_candidates(pages)["revenueGroups"] == []
    pages = table([row("甲", "100.00")])
    pages[0]["text"] = pages[0]["text"].replace("第三节 管理层讨论与分析", "第三节 管理层讨论与分析 ... 8")
    assert revenue_candidates(pages)["revenueGroups"] == []


def test_new_units_and_next_section_do_not_leak_into_old_group():
    pages = table([row("甲", "1,000.00")], unit="单位：万元 币种：人民币")
    pages[0]["text"] += "\n第四节 公司治理\n主营业务分产品情况\n" + row("不应采纳", "999.00")
    group = revenue_candidates(pages)["revenueGroups"][0]
    assert group["rows"][0]["value"] == 0.1
    assert len(group["rows"]) == 1
    pages[0]["text"] = pages[0]["text"].replace("单位：万元 币种：人民币\n主营业务分产品情况", "主营业务分产品情况\n单位：万元 币种：人民币")
    assert revenue_candidates(pages)["revenueGroups"][0]["rows"][0]["value"] == 0.1
    assert revenue_candidates(table([row("3C产品", "100.00")]))["revenueGroups"][0]["rows"][0]["label"] == "3C产品"


def test_same_page_repeated_dimension_is_ambiguous_not_two_candidates():
    pages = table([row("甲", "100.00")])
    pages[0]["text"] += "\n" + table([row("乙", "200.00")])[0]["text"]
    result = revenue_candidates(pages)
    assert result["revenueGroups"] == []
    assert any("重复分类标题" in warning for warning in result["revenueWarnings"])
    other_page = table([row("乙", "200.00")])[0]
    other_page["page"] = 9
    result = revenue_candidates(table([row("甲", "100.00")]) + [other_page])
    assert len(result["revenueGroups"]) == 2
    assert len({group["id"] for group in result["revenueGroups"]}) == 2
