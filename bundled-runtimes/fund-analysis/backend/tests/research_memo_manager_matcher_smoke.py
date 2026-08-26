from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.local_research_folder_service import LocalResearchFolderService  # noqa: E402
from services.research_memo_manager_matcher import ResearchMemoManagerMatcher  # noqa: E402


def main():
    matcher = ResearchMemoManagerMatcher([
        {"wind_code": "zou", "name": "邹立虎", "company": "诺德基金管理有限公司"},
        {"wind_code": "zhang-xue", "name": "张雪", "company": "广发基金管理有限公司"},
        {"wind_code": "zhang-xue-wei", "name": "张雪薇", "company": "广发基金管理有限公司"},
        {"wind_code": "liu-li", "name": "刘力", "company": "华商基金管理有限公司"},
        {"wind_code": "liu-li-si", "name": "刘力思", "company": "汇添富基金管理有限公司"},
        {"wind_code": "guo-zi-kun", "name": "郭子琨", "company": "富国基金管理有限公司"},
        {"wind_code": "hu-jian", "name": "胡剑", "company": "易方达基金管理有限公司"},
        {"wind_code": "other", "name": "王五", "company": "汇丰晋信基金管理有限公司"},
    ], company_names=[
        "东方基金管理股份有限公司",
        "中邮创业基金管理股份有限公司",
        "易方达基金管理有限公司",
        "鹏华基金管理有限公司",
    ])

    assert matcher.resolve_candidate("邹立虎先生", "诺德基金路演")["candidate_id"] == "zou"
    assert matcher.resolve_candidate("2026", "2026/市场讨论.docx") is None
    assert matcher.resolve_candidate("汇丰晋信", "汇丰晋信交流纪要") is None

    zhang_xue = matcher.match("", "张雪 广发基金 240613.docx")
    assert [item["candidate_id"] for item in zhang_xue if item.get("candidate_id")] == ["zhang-xue"]
    zhang_xue_wei = matcher.match("", "张雪薇 广发基金 240613.docx")
    assert [item["candidate_id"] for item in zhang_xue_wei if item.get("candidate_id")] == ["zhang-xue-wei"]
    compact_company_title = matcher.match("", "广发基金张雪投资理念及风格介绍.pptx")
    assert [item["candidate_id"] for item in compact_company_title if item.get("candidate_id")] == ["zhang-xue"]
    liu_li_si = matcher.match("", "202602刘力思投资风格介绍.pdf")
    assert [item["candidate_id"] for item in liu_li_si if item.get("candidate_id")] == ["liu-li-si"]
    assert all(item.get("value") != "刘力" for item in liu_li_si)
    compact_roadshow = matcher.match("", "富国郭子琨路演纪要-20221012.docx")
    assert [item["candidate_id"] for item in compact_roadshow if item.get("candidate_id")] == ["guo-zi-kun"]
    compact_company = matcher.match("", "易方达胡剑路演纪要-20241115.docx")
    assert [item["candidate_id"] for item in compact_company if item.get("candidate_id")] == ["hu-jian"]
    real_filename_cases = {
        "【周期】东方基金刘文哲调研纪要20251027.docx": "刘文哲",
        "中邮基金张屹岩总交流纪要.docx": "张屹岩",
        "基金经理周珊珊路演报告20260402.pdf": "周珊珊",
        "易方达基金经理及产品介绍【张琦-创新成长】.pptx": "张琦",
    }
    for filename, expected in real_filename_cases.items():
        values = [item["value"] for item in matcher.match("", filename)]
        assert expected in values, (filename, values)
        assert not {"周期", "易方达", "东方", "中邮", "金张屹岩", "金经理及"}.intersection(values), (filename, values)
    historical_manager = matcher.match(
        "本基金历任基金经理：张雪，现任基金经理：张雪薇。",
        "产品资料.pdf",
    )
    assert all(item.get("value") != "张雪" for item in historical_manager)
    assert any(item.get("value") == "张雪薇" for item in historical_manager)

    service = LocalResearchFolderService(repo=object(), manager_matcher=matcher)
    rejected_prefix = service._merge_proposals(
        [],
        [{
            "kind": "manager",
            "value": "张雪",
            "confidence": 0.95,
            "excerpt": "基金经理：张雪薇",
        }],
        Path("/tmp"),
        Path("/tmp/张雪薇纪要.docx"),
    )
    assert rejected_prefix == []

    merged = service._merge_proposals(
        [],
        [{
            "kind": "manager",
            "value": "张雪",
            "confidence": 0.95,
            "excerpt": "基金经理：张雪",
        }],
        Path("/tmp"),
        Path("/tmp/张雪纪要.docx"),
    )
    assert len(merged) == 1
    assert merged[0]["value"] == "张雪"
    assert merged[0]["candidate_id"] == "zhang-xue"

    rejected = service._merge_proposals(
        [],
        [{"kind": "manager", "value": "不存在", "confidence": 0.99, "excerpt": "基金经理：不存在"}],
        Path("/tmp"),
        Path("/tmp/未知经理.docx"),
    )
    assert rejected == []
    print("research memo manager matcher smoke passed")


if __name__ == "__main__":
    main()
