from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.fund_manager_research_service import FundManagerResearchService
from services.fund_product_identity import fund_product_identity


class ManagerRepo:
    def get_manager(self, manager_id):
        return {
            "wind_code": "张三|M|硕士",
            "name": "张三",
            "company": "示例基金",
            "education": "硕士",
            "work_years": 8,
            "management_years": 6.2,
            "current_funds": ["000001.OF", "000004.OF", "000002.OF"],
            "historical_performance": {},
            "style_analysis": {},
        }

    def get_profile(self, manager_id):
        return {
            "manager_id": manager_id,
            "product_positioning": "主动权益产品，覆盖全市场质量成长机会",
            "investment_objective": "争取长期稳健回报并控制下行风险",
            "investment_method": "自上而下判断环境，自下而上选择公司",
            "excess_return_source": "行业比较和个股选择",
            "holding_style": "质量成长、适度分散",
            "evidence": {
                "fields": {
                    "product_positioning": [{"report_id": "memo-1", "value": "主动权益产品，覆盖全市场质量成长机会"}],
                    "investment_objective": [{"report_id": "memo-1", "value": "争取长期稳健回报并控制下行风险"}],
                    "investment_method": [{"report_id": "memo-1", "value": "自上而下判断环境，自下而上选择公司"}],
                    "excess_return_source": [{"value": "行业比较和个股选择"}],
                    "holding_style": [{"value": "质量成长、适度分散"}],
                }
            },
        }

    def list_fund_tenures(self, manager_id):
        return [
            {
                "fund_code": "000001.OF",
                "fund_name": "基金000001.OF",
                "type": "混合型",
                "total_asset": 120,
                "start_date": "2020-01-01",
                "end_date": None,
                "is_current": True,
                "entity_id": "entity-1",
                "is_primary": True,
                "peer_group_name": "主动权益核心",
                "benchmark_code": "000300.SH",
                "benchmark_name": "沪深300",
                "benchmark_type": "broad_market_index",
                "benchmark_nav_observations": 1500,
                "performance_snapshot": {
                    "status": "available", "start_date": "2020-01-01", "end_date": "2026-08-01",
                    "observations": 1600, "total_return": 0.16, "annualized_return": 0.025,
                    "record_breaking_days_ratio": 0.42, "max_drawdown": -0.12,
                    "annualized_volatility": 0.18, "downside_risk": 0.11,
                    "sharpe_ratio": 0.45, "sortino_ratio": 0.62,
                },
                "manager_tenure": {"total_return": 0.16, "max_drawdown": -0.12},
            },
            {
                "fund_code": "000004.OF",
                "fund_name": "基金000001.OF-C",
                "type": "混合型",
                "total_asset": 118,
                "start_date": "2020-01-01",
                "end_date": None,
                "is_current": True,
                "entity_id": "entity-1",
                "is_primary": False,
                "peer_group_name": "主动权益核心",
                "performance_snapshot": {
                    "status": "available", "start_date": "2020-01-01", "end_date": "2026-08-01",
                    "observations": 1600, "total_return": 0.15, "annualized_return": 0.024,
                    "record_breaking_days_ratio": 0.41, "max_drawdown": -0.12,
                    "annualized_volatility": 0.18, "downside_risk": 0.11,
                    "sharpe_ratio": 0.44, "sortino_ratio": 0.61,
                },
                "manager_tenure": {"total_return": 0.15, "max_drawdown": -0.12},
            },
            {
                "fund_code": "000002.OF",
                "fund_name": "基金000002.OF",
                "type": "混合型",
                "total_asset": 80,
                "start_date": "2021-01-01",
                "end_date": None,
                "is_current": True,
                "entity_id": "entity-2",
                "is_primary": True,
            },
            {
                "fund_code": "000003.OF",
                "fund_name": "历史基金",
                "type": "混合型",
                "start_date": "2018-01-01",
                "end_date": "2019-12-31",
                "is_current": False,
                "entity_id": "entity-3",
                "is_primary": True,
            },
        ]


class FundRepo:
    def get_fund(self, code):
        return {"wind_code": code, "name": f"基金{code}", "type": "混合型", "manager_ids": ["张三|M|硕士"]}


class FundBrowser:
    def enrich_rows(self, rows):
        result = []
        for index, row in enumerate(rows):
            result.append({
                **row,
                "research_profile": {"peer_group": "主动权益核心", "style_label": "均衡"},
                "professional_scoring": {
                    "status": "ok" if index == 0 else "insufficient_evidence",
                    "overall_score": 72 if index == 0 else None,
                    "overall_grade": "B" if index == 0 else "insufficient_evidence",
                    "missing_data": [] if index == 0 else ["core_metric:1y.annualized_return"],
                    "data_quality": {"score": 100 if index == 0 else 55},
                },
                "rolling_metrics": {
                    "manager_tenure": {
                        "total_return": 0.16,
                        "max_drawdown": -0.12,
                        "as_of_date": "2026-08-01",
                    }
                },
            })
        return result


class ReportRepo:
    def list_reports_for_manager_exact(self, manager_id, limit=50):
        assert manager_id == "张三|M|硕士"
        return [{
            "id": "memo-1",
            "manager_id": "张三|M|硕士",
            "title": "张三路演纪要",
            "report_date": "2026-07-01",
            "source": "本地调研纪要文件夹",
            "summary": "重视估值与现金流。",
            "key_points": ["优先研究现金流可验证的公司。"],
            "style_labels": ["价值"],
            "review_proposals": [{
                "kind": "style_label",
                "value": "价值",
                "review_status": "confirmed",
                "scope": "manager",
                "source_ref": {"excerpt": "投资风格：价值"},
            }, {
                "kind": "style_label",
                "value": "成长",
                "review_status": "confirmed",
                "scope": "fund",
                "target_fund_ids": ["000001.OF"],
                "source_ref": {"excerpt": "000001.OF：成长风格"},
            }],
        }]


class TenurePeerRankingService:
    def rank(self, tenure):
        return {
            "status": "sufficient",
            "peer_group_name": tenure.get("category"),
            "valid_peer_count": 12,
            "metrics": {
                "total_return": {
                    "rank": 3,
                    "peer_count": 12,
                    "percentile": 81.82,
                    "sample_status": "sufficient",
                },
                "max_drawdown": {
                    "rank": 2,
                    "peer_count": 12,
                    "percentile": 90.91,
                    "sample_status": "sufficient",
                },
                "sharpe_ratio": {
                    "rank": 11,
                    "peer_count": 12,
                    "percentile": 9.09,
                    "sample_status": "sufficient",
                },
            },
        }


def main():
    assert fund_product_identity({"fund_name": "易方达示例混合A"}) == "name:易方达示例混合"
    assert fund_product_identity({"fund_name": "易方达示例混合C"}) == "name:易方达示例混合"
    snapshot = FundManagerResearchService(
        manager_repo=ManagerRepo(),
        fund_repo=FundRepo(),
        report_repo=ReportRepo(),
        fund_browser=FundBrowser(),
        tenure_peer_ranking_service=TenurePeerRankingService(),
    ).build("张三|M|硕士")

    assert snapshot["interface_version"] == "fund_manager_research_snapshot_v1"
    assert snapshot["coverage"] == {
        "current_fund_count": 2,
        "classified_fund_count": 2,
        "evaluated_fund_count": 1,
        "evaluation_complete_fund_count": 1,
        "evaluation_partial_fund_count": 0,
        "evaluation_missing_fund_count": 1,
        "tenure_metric_fund_count": 1,
    }
    current_funds = {fund["wind_code"]: fund for fund in snapshot["current_funds"]}
    assert set(current_funds) == {"000001.OF", "000002.OF"}
    assert current_funds["000001.OF"]["share_codes"] == ["000001.OF", "000004.OF"]
    assert current_funds["000001.OF"]["manager_product_tenure"]["total_return"] == 0.16
    assert current_funds["000002.OF"]["evaluation_summary"] == "缺少近1年净值评价指标"
    assert current_funds["000001.OF"]["manager_product_tenure"]["peer_ranking"]["metrics"]["total_return"]["rank"] == 3
    assert set(snapshot["manager"]["current_funds"]) == {"000001.OF", "000002.OF"}
    assert snapshot["manager"]["current_share_codes"] == ["000001.OF", "000004.OF", "000002.OF"]
    assert snapshot["research_memos"]["count"] == 1
    assert snapshot["research_memos"]["items"][0]["title"] == "张三路演纪要"
    assert snapshot["historical_viewpoints"]["methodology"] == "confirmed_manager_memo_timeline_v1"
    assert snapshot["historical_viewpoints"]["years"] == ["2026"]
    assert snapshot["historical_viewpoints"]["items"][0]["viewpoint"] == "争取长期稳健回报并控制下行风险 主动权益产品，覆盖全市场质量成长机会 自上而下判断环境，自下而上选择公司"
    assert snapshot["historical_viewpoints"]["items"][0]["viewpoint_source"] == "manager_profile_evidence"
    assert snapshot["historical_viewpoints"]["items"][0]["evidence_fields"] == ["investment_objective", "product_positioning", "investment_method"]
    assert snapshot["historical_viewpoints"]["unavailable_sources"] == ["quarterly_report", "annual_report", "other_public_source"]
    assert FundManagerResearchService._viewpoint_excerpt("经理简介若干 市场观点及投资方向 看好现金流。") == "市场观点及投资方向 看好现金流。"
    assert snapshot["profile"]["style_labels_from_memos"] == ["价值"]
    assert snapshot["profile"]["product_positioning"] == "主动权益产品，覆盖全市场质量成长机会"
    assert snapshot["profile"]["investment_objective"] == "争取长期稳健回报并控制下行风险"
    assert snapshot["profile"]["investment_method"] == "自上而下判断环境，自下而上选择公司"
    assert snapshot["profile"]["excess_return_source"] == "行业比较和个股选择"
    assert snapshot["profile"]["holding_style"] == "质量成长、适度分散"
    assert snapshot["product_tenures"]["current_product_count"] == 2
    assert snapshot["product_tenures"]["current_share_count"] == 3
    assert next(
        item for item in snapshot["product_tenures"]["items"] if item["fund_code"] == "000001.OF"
    )["peer_ranking"]["metrics"]["total_return"]["rank"] == 3
    assert next(
        item for item in snapshot["product_tenures"]["items"] if item["fund_code"] == "000002.OF"
    )["peer_ranking"]["status"] == "manager_product_tenure_unavailable"
    assert snapshot["manager_assessment"]["current_product_count"] == 2
    assert snapshot["manager_assessment"]["peer_ranked_product_count"] == 1
    assert snapshot["manager_assessment"]["representative_product"]["fund_code"] == "000001.OF"
    assert snapshot["manager_assessment"]["representative_product"]["benchmark"]["status"] == "available"
    assert snapshot["manager_assessment"]["strengths"][0]["metric_name"] in {"total_return", "max_drawdown"}
    assert snapshot["manager_assessment"]["risks"][0]["metric_name"] == "sharpe_ratio"
    assert "不生成经理综合收益" in snapshot["manager_assessment"]["scope_note"]
    assert snapshot["product_tenures"]["historical_product_count"] == 1
    assert len(snapshot["product_tenures"]["items"]) == 3
    assert snapshot["portfolio_summary"]["current_product_count"] == 2
    assert snapshot["portfolio_summary"]["current_share_count"] == 3
    assert snapshot["portfolio_summary"]["managed_asset"] == 200.0
    assert snapshot["portfolio_summary"]["managed_asset_product_count"] == 2
    assert snapshot["portfolio_summary"]["managed_asset_coverage"] == 1.0
    assert snapshot["portfolio_summary"]["institutional_holding_status"] == "holder_structure_not_connected"
    assert snapshot["product_scope"]["investment_decision"] == "excluded"
    print("fund manager research service smoke passed")


if __name__ == "__main__":
    main()
