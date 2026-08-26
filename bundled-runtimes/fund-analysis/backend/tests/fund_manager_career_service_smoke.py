from datetime import date
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.fund_manager_career_service import FundManagerCareerService


class ManagerRepo:
    def get_manager(self, manager_id):
        return {"wind_code": manager_id, "name": "张三"}

    def list_fund_tenures(self, _manager_id):
        return [
            {
                "fund_code": "000001.OF", "fund_name": "真实基金A", "entity_id": "entity-1",
                "start_date": "2024-01-01", "end_date": None, "is_current": True,
                "is_primary": True, "peer_group_name": "主动权益核心",
                "performance_snapshot": {"status": "available", "observations": 4},
            },
            {
                "fund_code": "000002.OF", "fund_name": "真实基金A-C", "entity_id": "entity-1",
                "start_date": "2024-01-01", "end_date": None, "is_current": True,
                "is_primary": False, "peer_group_name": "主动权益核心",
                "performance_snapshot": {"status": "available", "observations": 4},
            },
        ]


class NavRepo:
    def __init__(self, benchmark=True):
        self.benchmark = benchmark

    def get_nav_series(self, code, start_date, end_date):
        if code != "000001.OF":
            return []
        values = [1.0, 1.02, 1.01, 1.05]
        benchmarks = [100.0, 101.0, 100.5, 102.0]
        dates = ["2026-01-02", "2026-01-05", "2026-02-02", "2026-03-02"]
        return [
            {
                "date": item_date,
                "nav": value,
                "benchmark_nav": benchmarks[index] if self.benchmark else None,
            }
            for index, (item_date, value) in enumerate(zip(dates, values))
            if start_date <= item_date <= end_date
        ]


class ClassificationRepo:
    def __init__(self, allocation_bucket=False):
        self.allocation_bucket = allocation_bucket

    def get_classification_context(self, _code):
        if self.allocation_bucket:
            benchmark_mapping = {
                "benchmark_code": "MIXED-EQUITY-60",
                "benchmark_name": "合同基准权益权重≥60%",
                "benchmark_type": "declared_allocation_bucket",
                "evidence_refs": {
                    "declaredBenchmark": "沪深300指数收益率×60%+中证综合债券指数收益率×30%+恒生指数收益率×10%",
                    "benchmarkComponents": [
                        {"code": "000300.SH", "weight": 60},
                        {"code": "H11009.CSI", "weight": 30},
                        {"code": "HSI", "weight": 10},
                    ],
                },
            }
        else:
            benchmark_mapping = {"benchmark_code": "000300.SH", "benchmark_name": "沪深300"}
        return {
            "status": "resolved",
            "entity_id": "entity-1",
            "peer_group_id": "peer-active-equity",
            "peer_group_name": "主动权益核心",
            "peer_group_membership_count": 8,
            "minimum_peer_count": 5,
            "benchmark_mapping": benchmark_mapping,
        }

    def list_peer_period_nav_summaries(self, _peer_group_id, period_start, period_end):
        returns = [0.10, 0.08, 0.04, 0.02]
        return [
            {
                "wind_code": f"peer-{index}",
                "entity_id": f"peer-entity-{index}",
                "first_date": period_start,
                "last_date": period_end,
                "first_nav": 1.0,
                "last_nav": 1.0 + value,
                "observations": 60,
                "record_breaking_days_ratio": 0.90 - index * 0.10,
                "max_drawdown": -0.10 - index * 0.01,
                "sharpe_ratio": 0.8 - index * 0.05,
            }
            for index, value in enumerate(returns, start=1)
        ]


class ReportRepo:
    def list_reports_for_manager_exact(self, _manager_id, limit=200):
        return [{
            "id": "memo-1", "title": "张三调研纪要", "report_date": "2026-02-01",
            "summary": "只来自真实纪要。", "source": "本地调研纪要", "tags": ["质量成长"],
        }]


def service(benchmark=True, allocation_bucket=False):
    return FundManagerCareerService(
        manager_repo=ManagerRepo(),
        nav_repo=NavRepo(benchmark=benchmark),
        classification_repo=ClassificationRepo(allocation_bucket=allocation_bucket),
        report_repo=ReportRepo(),
        today=date(2026, 3, 3),
    )


def main():
    payload = service().build("张三|M|硕士", fund_code="000002.OF", period="ytd")
    assert payload["status"] == "available" and payload["simulation_used"] is False
    assert len(payload["products"]) == 1 and payload["products"][0]["share_count"] == 2
    assert payload["selected_product"]["actual_curve_code"] == "000001.OF"
    assert payload["benchmark"]["status"] == "available"
    assert payload["metrics"]["benchmark_return"] is not None
    assert payload["metrics"]["excess_return"] is not None
    assert payload["metrics"]["downside_risk"] is not None
    assert payload["metrics"]["sortino_ratio"] is not None
    assert payload["metrics"]["record_breaking_days_ratio"] == 0.75
    assert payload["peer_ranking"]["status"] == "sufficient"
    assert payload["peer_ranking"]["peer_group_name"] == "主动权益核心"
    assert payload["peer_ranking"]["metrics"]["total_return"]["rank"] == 3
    assert payload["peer_ranking"]["metrics"]["total_return"]["peer_count"] == 5
    assert payload["peer_ranking"]["metrics"]["total_return"]["percentile"] == 50.0
    assert "max_drawdown" in payload["peer_ranking"]["metrics"]
    assert "sharpe_ratio" in payload["peer_ranking"]["metrics"]
    assert "record_breaking_days_ratio" in payload["peer_ranking"]["metrics"]
    assert payload["events"][0]["date"] == "2026-02-01"
    assert payload["events"][0]["chart_date"] == "2026-02-02"
    assert payload["curve"][0]["fund_return"] == 0

    allocation_payload = service(allocation_bucket=True).build("张三|M|硕士", period="ytd")
    assert allocation_payload["benchmark"]["code"] == "CONTRACT-COMPOSITE"
    assert allocation_payload["benchmark"]["classification_code"] == "MIXED-EQUITY-60"
    assert allocation_payload["benchmark"]["name"].startswith("沪深300指数收益率×60%")

    no_benchmark = service(benchmark=False).build("张三|M|硕士", period="ytd")
    assert no_benchmark["benchmark"]["status"] == "data_unavailable"
    assert no_benchmark["benchmark"]["observations"] == 0
    assert no_benchmark["metrics"].get("benchmark_return") is None
    assert no_benchmark["metrics"].get("excess_return") is None
    assert all(item["benchmark_return"] is None for item in no_benchmark["curve"])
    assert no_benchmark["simulation_used"] is False

    natural_year = service().build("张三|M|硕士", period="year:2026")
    assert natural_year["period_label"] == "2026"

    repeated_tenures = [
        {"fund_code": "512560.SH", "share_codes": ["512560.SH"], "start_date": "2022-11-01"},
        {"fund_code": "512560.SH", "share_codes": ["512560.SH"], "start_date": "2017-07-14"},
    ]
    selected_tenure = service()._select_product(repeated_tenures, "512560.SH", "2017-07-14")
    assert selected_tenure["start_date"] == "2017-07-14"
    print("fund manager career service exposes only real product NAV, benchmark and memo events")


if __name__ == "__main__":
    main()
