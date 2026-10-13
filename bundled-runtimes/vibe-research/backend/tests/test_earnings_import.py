from pathlib import Path

import pytest

from earnings_import import annual_candidates, discussion_candidates, extract_report
from earnings_capital import capital_candidates
from earnings_capital_notes import capital_note_candidates


def test_capital_notes_keep_boundaries_and_never_convert_amounts():
    pages = [{"page": 1, "text": "七、合并财务报表项目注释 ... 80\n1、货币资金\n目录勿采用"},
             {"page": 80, "text": "七、合并财务报表项目注释\n1、货币资金\n单位：元 币种：人民币\n期末余额 期初余额\n受限资金 100.00 90.00\n2、应收账款\n旁表勿采用\n七、短期利润分享计划"},
             {"page": 81, "text": "31、1年内到期的非流动负债\n一年内租赁负债 20.00 10.00\n32、其他流动负债\n旁表勿采用\n33、租赁负债\n长期租赁负债 30.00 40.00"},
             {"page": 82, "text": "补充租赁说明\n八、研发支出\n1、货币资金\n另一章节勿采用"},
             {"page": 83, "text": "十九、母公司财务报表主要项目注释\n1、货币资金\n母公司勿采用"}]
    result = capital_note_candidates(pages)
    rows = result["capitalNotes"]
    assert [p["page"] for p in rows] == [80, 81, 81, 82]
    assert "期末余额" in rows[0]["text"]
    assert rows[2]["title"] == rows[3]["title"] == "33、租赁负债"
    assert not any("勿采用" in row["text"] or "value" in row for row in rows)
    assert result["capitalNotesReadPages"][-1] == 82
    assert capital_note_candidates(pages[:1])["capitalNotes"] == []


def test_capital_notes_report_truncation_and_scan_limit():
    pages = [{"page": 1, "text": "七、合并财务报表项目注释\n1、货币资金\n" + "原文" * 4000}]
    pages.extend({"page": i, "text": "续页"} for i in range(2, 202))
    result = capital_note_candidates(pages)
    assert len(result["capitalNotes"][0]["text"]) == 6000
    assert result["capitalNotes"][0]["truncated"]
    assert len(result["capitalNotes"]) <= 24
    assert len(result["capitalNotesReadPages"]) == 200
    assert "部分未列出" in "".join(result["capitalNotesWarnings"])


def test_real_capital_notes_retain_cash_exclusion_and_lease_details():
    path = Path(__file__).resolve().parents[4] / "output/pdf/kweichow-moutai-2024-annual-report.pdf"
    if not path.exists():
        pytest.skip("Requires real filing")
    result = extract_report(path, "real", path.name, include_notes=True)
    rows = result["capitalNotes"]
    current = next(p for p in rows if p["title"].startswith("31、"))
    lease = next(p for p in rows if p["title"].startswith("33、"))
    cash = next(p for p in rows if p["page"] == 117)
    assert current["page"] == lease["page"] == 106
    assert "111,951,112.20" in current["text"] and "其他流动负债" not in current["text"]
    assert "313,906,415.76" in lease["text"] and "111,951,112.20" not in lease["text"]
    assert "不属于现金及现金等价物的货币资金" in cash["text"]
    assert "7,403,523,670.43" in cash["text"] and "169,970,089,257.83" in cash["text"]
    assert "所有者权益变动表" not in cash["text"]
    assert result["capitalNotesReadPages"][-1] == 119
    assert "capitalCandidates" not in result


def test_capital_only_uses_consolidated_current_column_and_preserves_zero():
    pages = [{"page": 50, "text": "合并资产负债表\n单位：元 币种：人民币\n项目 附注 2024年12月31日 2023年12月31日\n货币资金 1 1,000,000.00 500,000.00\n短期借款 2 0.00 100.00\n长期借款 3 — 100.00\n应付债券 4 100.00\n租赁负债 5 (100.00) 200.00\n股本 6 1,000.00 900.00\n负债合计 999,000.00 990,000.00"},
             {"page": 51, "text": "母公司资产负债表\n货币资金 1 9,000,000.00 500,000.00"}]
    result = capital_candidates(pages, "2024-12-31")
    rows = {row["id"]: row for row in result["capitalCandidates"]}
    assert set(rows) == {"capital-cash-funds", "capital-short-borrowings", "capital-share-capital"}
    assert rows["capital-cash-funds"]["value"] == 1
    assert rows["capital-short-borrowings"]["value"] == 0
    assert rows["capital-share-capital"]["unit"] == "百万元"
    for invalid in ["2023年12月31日 2024年12月31日", "2024年12月31日 2023年12月31日 调整前 调整后"]:
        changed = [{**pages[0], "text": pages[0]["text"].replace("2024年12月31日 2023年12月31日", invalid)}]
        assert capital_candidates(changed, "2024-12-31")["capitalCandidates"] == []
    assert capital_candidates([{**pages[0], "text": pages[0]["text"].replace("人民币", "美元")}], "2024-12-31")["capitalCandidates"] == []


def test_real_moutai_capital_is_reference_not_diluted_shares_or_available_cash():
    path = Path(__file__).resolve().parents[4] / "output/pdf/kweichow-moutai-2024-annual-report.pdf"
    if not path.exists():
        pytest.skip("Requires real filing")
    result = extract_report(path, "real", path.name, include_capital=True)
    rows = {row["id"]: row for row in result["capitalCandidates"]}
    assert len(result["candidates"]) == 7
    assert len(rows) == 5
    assert rows["capital-cash-funds"]["value"] == pytest.approx(59295.82295689)
    assert rows["capital-cash-funds"]["page"] == 58
    assert rows["capital-lease-liabilities"]["value"] == pytest.approx(313.90641576)
    assert rows["capital-current-noncurrent-liabilities"]["value"] == pytest.approx(111.9511122)
    assert rows["capital-customer-deposits"]["value"] == pytest.approx(23102.85882097)
    assert rows["capital-share-capital"]["value"] == 1256.1978
    assert "capital-short-borrowings" not in rows
    assert result["capitalReadPages"][-1] == 61


def summary(body, unit="元", header="2024年 2023年 本期比上年同期增减 2022年"):
    return [{"page": 1, "text": "公司代码：600519 公司简称：贵州茅台\n2024 年年度报告"},
            {"page": 5, "text": f"主要会计数据\n单位：{unit} 币种：人民币\n{header}\n{body}"}]


def test_candidates_preserve_unit_page_and_zero():
    result = annual_candidates(summary("营业收入 0.00 100.00 -100.00 90.00", "万元"), 100, "test", "年报.pdf")
    row = result["candidates"][0]
    assert row["value"] == 0
    assert row["page"] == 5
    assert row["rawUnit"] == "万元"
    assert result["periodEnd"] == "2024-12-31"
    assert result["candidates"][1]["value"] == -100


@pytest.mark.parametrize("body,unit,header", [
    ("营业收入 — 100 20 90", "元", "2024年 2023年 2022年"),
    ("营业收入 100 90 11.11 80", "未知", "2024年 2023年 2022年"),
    ("营业收入 100 90 11.11 80", "元", "2023年 2024年 2022年"),
    ("营业收入 100 90 11.11 80", "元", "2024年 2023年 调整前 调整后"),
    ("营业总收入 100 90 11.11 80", "元", "2024年 2023年 2022年"),
])
def test_ambiguous_or_different_accounting_values_are_not_imported(body, unit, header):
    assert annual_candidates(summary(body, unit, header), 100, "test", "年报.pdf")["candidates"] == []


def test_real_moutai_pdf_if_downloaded():
    path = Path(__file__).resolve().parents[4] / "output/pdf/kweichow-moutai-2024-annual-report.pdf"
    if not path.exists():
        pytest.skip("Run real-filing acceptance with the public source PDF downloaded")
    result = extract_report(path, "real", path.name)
    rows = {row["id"]: row for row in result["candidates"]}
    assert len(rows) == 7
    assert rows["revenue"]["value"] == pytest.approx(1708.9915227634)
    assert rows["net-profit"]["value"] == pytest.approx(862.2814642162)
    assert rows["operating-cash-flow"]["value"] == pytest.approx(924.6369216843)
    assert rows["eps"]["value"] == 68.64
    assert rows["roe"]["value"] == 36.02
    assert {row["page"] for row in rows.values()} == {5}
    assert result["pageCount"] == 143
    passages = {p["page"]: p for p in result["discussion"]}
    assert "归集集团公司其他成员单位资金" in passages[9]["text"]
    assert "经销商预付货款减少" in passages[13]["text"]
    assert "-10.51" in passages[16]["text"]
    assert "9%左右" in passages[21]["text"]
    assert "第四节" not in passages[22]["text"]
    assert sum(len(p["text"]) for p in passages.values()) <= 18000


def test_discussion_scope_ignores_contents_and_stops_at_next_section():
    pages = [{"page": 2, "text": "第三节 管理层讨论与分析 .... 7\n合同负债"},
             {"page": 7, "text": "第三节 管理层讨论与分析\n合同负债减少"},
             {"page": 8, "text": "风险因素\n市场波动\n第四节 公司治理\n经营计划不应入库"},
             {"page": 9, "text": "应收账款审计"}]
    passages, section_pages = discussion_candidates(pages)
    assert section_pages == [7, 8]
    assert {p["page"] for p in passages} == {7, 8}
    assert "经营计划不应入库" not in passages[1]["text"]
    assert discussion_candidates(pages[:1]) == ([], [])


def test_long_discussion_discloses_truncation_and_keeps_page_budget():
    passages, _ = discussion_candidates([{"page": 7, "text": "第三节 管理层讨论与分析\n合同负债\n" + "测试原文" * 2000}])
    assert len(passages[0]["text"]) == 6000
    assert passages[0]["truncated"] is True
