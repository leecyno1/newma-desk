from copy import deepcopy
from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.research_memo_manager_profile_projection_service import (  # noqa: E402
    ResearchMemoManagerProfileProjectionService,
)


class ReportRepo:
    def __init__(self, reports):
        self.reports = reports

    def list_reports_for_manager_exact(self, manager_id, limit=200):
        return [
            deepcopy(report)
            for report in self.reports
            if report.get("manager_id") == manager_id
            or manager_id in [item.get("manager_id") for item in report.get("manager_links") or []]
        ][:limit]


class ManagerRepo:
    def __init__(self, profile=None, orphaned_count=0):
        self.profile = deepcopy(profile)
        self.orphaned_count = orphaned_count

    def get_profile(self, manager_id):
        return deepcopy(self.profile)

    def upsert_profile(self, manager_id, profile):
        self.profile = {"manager_id": manager_id, **deepcopy(profile)}
        return True

    def delete_projected_profile(self, manager_id, updated_by):
        if self.profile and self.profile.get("updated_by") == updated_by:
            self.profile = None
            return True
        return False

    def delete_orphaned_projected_profiles(self, updated_by):
        assert updated_by == ResearchMemoManagerProfileProjectionService.UPDATED_BY
        return self.orphaned_count


def main():
    report = {
        "id": "memo-1",
        "manager_id": "manager-1",
        "title": "经理路演纪要",
        "report_date": "2026-07-01",
        "local_relative_path": "2026/经理路演纪要.docx",
        "local_source_path": "/memo/2026/经理路演纪要.docx",
        "content": "\n".join([
            "经理投资理念及风格介绍",
            "投资理念：重视现金流和长期竞争力。",
            "目前管理5只权益产品，定位清晰区分，周期优选聚焦上游赛道，其余产品定位全市场价值风格。",
            "我们始终坚持偏绝对收益、为客户持续赚钱，更注重在下行市场中控制回撤。",
            "自上而下宏观分析、自下而上选股相结合。",
            "选股逻辑：从行业空间、竞争格局和估值三方面筛选。",
            "风险控制：估值过高或逻辑破坏时主动减仓。",
            "能力优势：擅长制造与科技行业研究。",
            "当前组合重点关注电子和医药，电子仓位约20%。",
            "能力边界：不参与无法验证盈利模式的主题交易。",
            "持仓集中度：前十大持仓保持适度分散。",
            "换手率：以中低换手为主。",
            "相对基准的超额收益主要来自行业配置效应和个股选择效应。",
            "当前产品为全市场质量成长风格，组合持仓适度分散。",
        ]),
        "style_labels": ["质量", "成长"],
        "review_proposals": [{
            "kind": "style_label",
            "value": "质量",
            "review_status": "confirmed",
            "scope": "manager",
            "source_ref": {"excerpt": "投资风格：质量"},
        }, {
            "kind": "style_label",
            "value": "成长",
            "review_status": "confirmed",
            "scope": "fund",
            "target_fund_ids": ["000001.OF"],
            "source_ref": {"excerpt": "000001.OF：成长风格"},
        }],
    }
    repo = ManagerRepo()
    result = ResearchMemoManagerProfileProjectionService(ReportRepo([report]), repo).project_report(report, ["manager-1"])
    assert result["projected_count"] == 1
    profile = repo.profile
    assert profile["core_philosophy"]
    assert profile["competence_boundaries"]
    assert profile["product_positioning"] == "目前管理5只权益产品，定位清晰区分，周期优选聚焦上游赛道，其余产品定位全市场价值风格。"
    assert profile["investment_objective"] == "我们始终坚持偏绝对收益、为客户持续赚钱，更注重在下行市场中控制回撤。"
    assert profile["investment_method"] == "自上而下宏观分析、自下而上选股相结合。"
    assert profile["core_philosophy"] == "重视现金流和长期竞争力。"
    assert profile["excess_return_source"] == "相对基准的超额收益主要来自行业配置效应和个股选择效应。"
    assert profile["holding_style"] == "当前产品为全市场质量成长风格，组合持仓适度分散。"
    assert profile["style_label"] == "质量"
    assert profile["focus_industries"] == ["医药", "电子"]
    assert profile["evidence"]["framework"]["excess_return_source"]
    assert profile["evidence"]["framework"]["product_positioning"]
    evidence = profile["evidence"]["fields"]["core_philosophy"][0]
    assert evidence["relative_path"] == "2026/经理路演纪要.docx"
    assert evidence["report_date"] == "2026-07-01"
    assert evidence["excerpt"]
    assert 0 <= evidence["confidence"] <= 1

    shared_report = {
        **report,
        "id": "memo-shared",
        "manager_id": "",
        "manager_links": [
            {"manager_id": "manager-1", "manager_name": "经理一"},
            {"manager_id": "manager-2", "manager_name": "经理二"},
        ],
    }
    shared_repo = ManagerRepo()
    shared_result = ResearchMemoManagerProfileProjectionService(
        ReportRepo([shared_report]), shared_repo,
    ).project_report(shared_report, ["manager-2"])
    assert shared_result["projected_count"] == 1
    assert shared_repo.profile["interviews_analyzed"] == 1

    noisy_report = {
        **report,
        "id": "memo-noisy",
        "content": "\n".join([
            "投资方法：Q：您在选股的时候更在意什么？如何权衡自下而上和自上而下？",
            "风险控制：且成立以来最大回撤控制优秀，为同期产品最佳！",
            "投资理念：组合构建方法 投资约束",
        ]),
        "style_labels": [],
        "review_proposals": [],
    }
    noisy_repo = ManagerRepo()
    noisy_result = ResearchMemoManagerProfileProjectionService(
        ReportRepo([noisy_report]), noisy_repo,
    ).project_report(noisy_report, ["manager-1"])
    assert noisy_result["managers"][0]["status"] in {"deleted", "skipped"}
    assert noisy_repo.profile is None

    semantic_report = {
        **report,
        "id": "memo-semantic",
        "content": "\n".join([
            "产品定位：绝对收益目标，主动控回撤，预期收益率年化10%-15%。",
            "定位：投资范围覆盖上游资源和中游周期行业。",
            "投资目标及理念",
            "投资目标：",
            "景气驱动内部定位为周期资源主题基金，聚焦周期资源能源材料投资。",
            "从绝对收益目标出发，力争组合实现长期复合10%左右收益率。",
            "使组合处于良好的风险收益比，组合最大回撤不超过20%。",
            "组合构建方法：",
            "",
            "根据宏观景气度和供需面筛选较优行业，再自下而上选择个股。",
            "注重估值与价格的匹配，严格执行止盈止损。",
            "化工与电子行业对比",
            "这部分不是投资方法结论。",
        ]),
        "style_labels": [],
        "review_proposals": [],
    }
    semantic_repo = ManagerRepo()
    semantic_result = ResearchMemoManagerProfileProjectionService(
        ReportRepo([semantic_report]), semantic_repo,
    ).project_report(semantic_report, ["manager-1"])
    assert semantic_result["projected_count"] == 1
    assert "周期资源主题基金" in semantic_repo.profile["product_positioning"]
    assert "绝对收益目标" in semantic_repo.profile["investment_objective"]
    assert semantic_repo.profile["investment_objective"] != "投资目标及理念"
    assert "宏观景气度" in semantic_repo.profile["investment_method"]
    assert "行业对比" not in semantic_repo.profile["investment_method"]

    vague_objective = ResearchMemoManagerProfileProjectionService(
        ReportRepo([{**semantic_report, "id": "memo-vague", "content": "核心是希望能涨且波动率可控。"}]),
        ManagerRepo(),
    )
    assert vague_objective._direct_field_evidence(
        "investment_objective", "核心是希望能涨且波动率可控。", semantic_report,
    ) is None
    assert vague_objective._direct_field_evidence(
        "investment_objective", "目前预期收益率要降低，更多去研究个股。", semantic_report,
    ) is None
    assert vague_objective._direct_field_evidence(
        "investment_objective", "权重依赖于主观的预期收益率。", semantic_report,
    ) is None
    assert vague_objective._is_interview_question("是否会在港股当中寻找投资机会？")

    industry_noise = "\n".join([
        "个人履历：曾任职于光大银行资金部。",
        "北京汇成基金销售有限公司已获得基金销售牌照，并服务银行理财和保险资管。",
        "风险揭示：本材料仅供特定专业人士参考，不构成投资建议。",
        "当前组合重点关注化工和有色，化工仓位40%，后续仍会进行行业轮动。",
    ])
    industry_evidence = vague_objective._industry_evidence(industry_noise, semantic_report)
    industry_values = [item["value"] for item in industry_evidence]
    assert "化工" in industry_values
    assert "有色" in industry_values
    assert "银行" not in industry_values
    assert "保险" not in industry_values
    assert "银行" not in [
        item["value"]
        for item in vague_objective._industry_evidence(
            "CD放量：银行支付某一时间的损失成本，不会像二级关注那么多。",
            semantic_report,
        )
    ]
    for third_party_finance in (
        "保险公司有长期配置红利资产的需求，近年来也在加仓。",
        "很多银行介入购买，把信用利差压到较低水平。",
        "商业银行资本新规明年开始实施，投资级信用债配置时点已到。",
        "我们观察到公募、保险等机构高度关注有色板块。",
    ):
        values = [
            item["value"]
            for item in vague_objective._industry_evidence(third_party_finance, semantic_report)
        ]
        assert "银行" not in values
        assert "保险" not in values
    direct_finance_values = [
        item["value"]
        for item in vague_objective._industry_evidence(
            "组合配置上相对均衡，银行等高股息方向占股票配置的一半。",
            semantic_report,
        )
    ]
    assert "银行" in direct_finance_values

    fragmented_industry = "\n".join(list("目前组合持仓以化工和有色为主，化工仓位40%。"))
    fragmented_values = [
        item["value"]
        for item in vague_objective._industry_evidence(fragmented_industry, semantic_report)
    ]
    assert "化工" in fragmented_values
    assert "有色" in fragmented_values

    rebuilt_repo = ManagerRepo(orphaned_count=2)
    rebuilt = ResearchMemoManagerProfileProjectionService(
        ReportRepo([report]), rebuilt_repo,
    ).rebuild_managers(["manager-1", "manager-1"])
    assert rebuilt["projected_count"] == 1
    assert rebuilt["orphaned_deleted_count"] == 2

    manual_repo = ManagerRepo({
        "manager_id": "manager-1",
        "core_philosophy": "人工确认画像",
        "updated_by": None,
    })
    preserved = ResearchMemoManagerProfileProjectionService(ReportRepo([report]), manual_repo).project_report(report, ["manager-1"])
    assert preserved["managers"][0]["reason"] == "manual_profile_preserved"
    assert manual_repo.profile["core_philosophy"] == "人工确认画像"
    print("research memo manager profile projection smoke passed")


if __name__ == "__main__":
    main()
