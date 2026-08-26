from datetime import date, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.fund_manager_comparison_service import FundManagerComparisonService


CATEGORY = "混合型-偏股配置"


def product(code, name, category=CATEGORY, current=True, start="2025-01-01"):
    return {
        "fund_code": code,
        "fund_name": name,
        "category": category,
        "start_date": start,
        "end_date": None if current else "2025-12-31",
        "is_current": current,
        "share_codes": [code],
        "share_count": 1,
        "metric_status": "manager_product_tenure",
        "metric_start_date": start,
        "metric_as_of_date": "2026-02-10",
        "metric_observations": 30,
        "total_asset": 12.5,
        "peer_ranking": {
            "status": "sufficient",
            "peer_group_name": category,
            "period_start": start,
            "period_end": "2026-02-10",
            "valid_peer_count": 10,
            "minimum_peer_count": 5,
            "metrics": {
                "total_return": {"rank": 2, "peer_count": 10, "percentile": 88.89, "sample_status": "sufficient"},
                "annualized_return": {"rank": 3, "peer_count": 10, "percentile": 77.78, "sample_status": "sufficient"},
                "max_drawdown": {"rank": 4, "peer_count": 10, "percentile": 66.67, "sample_status": "sufficient"},
                "sharpe_ratio": {"rank": 8, "peer_count": 10, "percentile": 22.22, "sample_status": "sufficient"},
            },
        },
    }


class ResearchService:
    def __init__(self, unrelated=False):
        self.unrelated = unrelated

    def build(self, manager_id, research_limit=50):
        assert research_limit == 50
        second_category = "债券型-中长债" if self.unrelated and manager_id == "manager-2" else CATEGORY
        manager_name = "张三" if manager_id == "manager-1" else "李四"
        items = [
            product("000001.OF" if manager_id == "manager-1" else "000002.OF", f"{manager_name}代表基金", second_category),
            product("900001.OF" if manager_id == "manager-1" else "900002.OF", f"{manager_name}历史基金", second_category, current=False),
        ]
        if manager_id == "manager-1" and not self.unrelated:
            items.append(product("000003.OF", "张三债基", "债券型-中长债"))
        return {
            "manager": {
                "manager_id": manager_id,
                "name": manager_name,
                "company": "真实基金公司",
                "education": "硕士",
                "work_years": 10,
                "management_years": 7,
            },
            "profile": {
                "status": "available",
                "product_positioning": "主动权益产品，覆盖全市场质量成长机会",
                "investment_objective": "争取长期稳健回报并控制下行风险",
                "investment_method": "自上而下判断环境，自下而上选择公司",
                "holding_style": "适度分散",
                "core_philosophy": "基于真实纪要归纳",
                "risk_philosophy": "重视回撤",
                "focus_industries": ["制造"],
                "style_labels_from_memos": ["质量成长"],
                "classifications_from_memos": ["主动权益"],
                "evidence": {
                    "fields": {
                        "product_positioning": [{"report_id": f"memo-{manager_id}", "value": "主动权益产品"}],
                        "investment_method": [{"report_id": f"memo-{manager_id}", "value": "自下而上"}],
                    }
                },
            },
            "product_tenures": {
                "items": items,
                "current_product_count": sum(bool(item["is_current"]) for item in items),
                "current_share_count": sum(bool(item["is_current"]) for item in items),
            },
            "research_memos": {
                "count": 1,
                "items": [{
                    "id": f"memo-{manager_id}",
                    "report_date": "2026-01-20",
                    "title": f"{manager_name}调研纪要",
                    "summary": "只展示真实纪要摘要。",
                    "source": "本地调研纪要",
                    "tags": ["质量成长"],
                }],
            },
            "manager_assessment": {
                "status": "partial",
                "summary": "当前关联 2 个在管产品，其中 1 个已有单产品任期指标，1 个达到同区间同类排名门槛。",
                "current_product_count": 2,
                "tenure_evaluated_product_count": 1,
                "peer_ranked_product_count": 1,
                "memo_count": 1,
                "representative_product": items[0],
                "strengths": [{
                    "direction": "strength",
                    "label": "任期收益处于同类前列",
                    "statement": f"{items[0]['fund_name']}任期收益排名 2/10。",
                    "fund_code": items[0]["fund_code"],
                    "metric_name": "total_return",
                }],
                "risks": [],
                "scope_note": "不生成经理综合分。",
            },
            "evidence": {
                "fund_metric_latest_date": "2026-02-10",
                "research_latest_date": "2026-01-20",
                "missing_items": [],
            },
        }


class NavRepo:
    def __init__(self):
        common_dates = [date(2026, 1, 5) + timedelta(days=index) for index in range(25)]
        stable_values = [1.0]
        volatile_values = [1.0]
        for index in range(1, 25):
            stable_values.append(stable_values[-1] * 1.002)
            volatile_values.append(volatile_values[-1] * (1.03 if index % 2 else 0.985))
        self.rows = {
            "000001.OF": [
                {"date": date(2026, 1, 4), "nav": 0.998},
                *[{"date": item_date, "nav": value} for item_date, value in zip(common_dates, stable_values)],
            ],
            "000002.OF": [
                *[{"date": item_date, "nav": value} for item_date, value in zip(common_dates, volatile_values)],
                {"date": date(2026, 1, 30), "nav": volatile_values[-1] * 1.01},
            ],
        }

    def get_nav_series(self, code, start_date, end_date):
        return [
            row for row in self.rows.get(code, [])
            if start_date <= row["date"].isoformat() <= end_date
        ]


def service(unrelated=False):
    return FundManagerComparisonService(
        research_service=ResearchService(unrelated=unrelated),
        nav_repo=NavRepo(),
    )


def assert_raises(fragment, callback):
    try:
        callback()
    except ValueError as error:
        assert fragment in str(error)
        return
    raise AssertionError("expected ValueError")


def main():
    assert_raises("At least two", lambda: service().build(["manager-1"]))
    assert_raises("At most 4", lambda: service().build(["1", "2", "3", "4", "5"]))
    assert_raises(
        "every selected manager",
        lambda: service().build(["manager-1", "manager-2"], category="债券型-中长债"),
    )

    payload = service().build(["manager-1", "manager-2"], category=CATEGORY)
    assert payload["status"] == "available"
    assert payload["selected_category"] == CATEGORY
    assert payload["simulation_used"] is False
    assert payload["common_period"]["observation_count"] == 25
    assert payload["common_period"]["period_start"] == "2026-01-05"
    assert payload["common_period"]["period_end"] == "2026-01-29"
    assert payload["common_period"]["leaders"]["total_return"] == ["manager-2"]
    assert payload["common_period"]["leaders"]["annualized_volatility"] == ["manager-1"]
    assert payload["common_period"]["leaders"]["max_drawdown"] == ["manager-1"]
    assert payload["common_period"]["leaders"]["record_breaking_days_ratio"] == ["manager-1"]
    assert payload["common_period"]["observation_coverage"] == 1.0
    assert payload["common_period"]["highlight_eligible"] is True
    assert payload["comparison_gate"]["highlight_eligible"] is True
    assert all("benchmark_return" not in metrics for metrics in payload["common_period"]["metrics"].values())
    assert all(len(manager["product_tenures"]) == 2 or manager["id"] == "manager-1" for manager in payload["managers"])
    assert all(manager["profile"]["product_positioning"] for manager in payload["managers"])
    assert all(manager["profile"]["investment_objective"] for manager in payload["managers"])
    assert all(manager["profile"]["investment_method"] for manager in payload["managers"])
    assert all(manager["manager_assessment"]["peer_ranked_product_count"] == 1 for manager in payload["managers"])
    assert {manager["id"]: manager["managed_asset"] for manager in payload["managers"]} == {
        "manager-1": 25.0,
        "manager-2": 12.5,
    }
    assert all(manager["management_start_date"] == "2025-01-01" for manager in payload["managers"])
    assert all(manager["evidence"]["profile_evidence_field_count"] == 2 for manager in payload["managers"])
    assert all(manager["product_tenures"][0]["peer_ranking"]["metrics"]["total_return"]["rank"] == 2 for manager in payload["managers"])
    assert "score" not in payload and all("score" not in manager for manager in payload["managers"])
    assert payload["comparison_summary"]["status"] == "available"
    assert "代表产品" in payload["comparison_summary"]["headline"]

    no_common = service(unrelated=True).build(["manager-1", "manager-2"])
    assert no_common["status"] == "no_common_category"
    assert no_common["common_period"]["status"] == "no_common_category"
    assert no_common["common_period"]["highlight_eligible"] is False
    assert no_common["simulation_used"] is False
    print("fund manager comparison uses exact common category and common real NAV dates")


if __name__ == "__main__":
    main()
