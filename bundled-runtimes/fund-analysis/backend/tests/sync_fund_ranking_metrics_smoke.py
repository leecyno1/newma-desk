import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.sync_fund_ranking_metrics import (
    BROWSER_CORE_PEER_GROUPS,
    BROWSER_CORE_TARGET_PER_GROUP,
    _panel_has_required_category_metrics,
    _tenure_nav_coverage_is_valid,
    build_fof_lookthrough_coverage_states,
    build_company_evaluation_group_states,
    latest_nav_payload,
    manager_tenure_required,
    manager_evaluation_gap_codes,
    manager_evaluation_required_days,
    manager_tenure_peer_gap_states,
    round_robin_peer_candidates,
    save_latest_fund_facts,
    sync_fof_lookthrough,
)


class FakeMetricRepo:
    def __init__(self):
        self.saved = []

    def upsert_metric(self, **payload):
        self.saved.append(payload)


class FakeFofHoldingService:
    def __init__(self):
        self.calls = []

    def get(self, wind_code, limit=8, refresh=False):
        self.calls.append((wind_code, limit, refresh))
        return {
            "status": "available",
            "latest": {"report_date": "2026-06-30"},
            "professional_profile": {
                "disclosed_fund_count": 10,
                "disclosed_nav_ratio": 49.55,
            },
            "evidence_gate": {"status": "sufficient", "missing_items": []},
            "source": "eastmoney.fundmobapi.fof_holdings",
        }


def main() -> int:
    payload = latest_nav_payload([
        {"date": "2026-03-31", "unit_nav": 1.2, "net_asset": 1_250_000_000},
        {"date": "2026-04-01", "unit_nav": 1.21, "net_asset": None},
        {"date": "2026-04-02", "unit_nav": 1.22, "net_asset": None},
    ])
    if payload.get("nav") != 1.22 or payload.get("nav_date") != "2026-04-02":
        raise AssertionError(f"Latest NAV must remain the latest observation: {payload}")
    if payload.get("total_asset") != 12.5 or payload.get("total_asset_as_of") != "2026-03-31":
        raise AssertionError(f"AUM must use the latest reported non-null asset observation: {payload}")
    if payload.get("total_asset_source") != "tushare.fund_nav.latest_reported_net_asset":
        raise AssertionError(f"AUM source lineage must be explicit: {payload}")

    metric_repo = FakeMetricRepo()
    saved = save_latest_fund_facts(
        metric_repo,
        "000051.OF",
        {
            "total_asset": 115.57,
            "raw_data": {
                "source": "tushare",
                "universe": {"management_fee": 0.15, "custodian_fee": 0.05},
            },
        },
        date(2026, 8, 11),
    )
    saved_values = {item["metric_name"]: float(item["metric_value"]) for item in metric_repo.saved}
    if saved != 2 or saved_values != {"expense_ratio": 0.002, "aum": 115.57}:
        raise AssertionError(f"Ranking sync must persist real fee and AUM facts: {metric_repo.saved}")
    if any(item.get("details", {}).get("source") != "funds.total_asset+funds.raw_data.tushare" for item in metric_repo.saved):
        raise AssertionError(f"Static evaluation metrics need explicit source lineage: {metric_repo.saved}")

    fof_service = FakeFofHoldingService()
    fof_result = sync_fof_lookthrough(
        "005220.OF",
        {"strategy_family_key": "fof_equity_allocation"},
        fof_service,
    )
    if fof_service.calls != [("005220.OF", 20, True)]:
        raise AssertionError(f"FOF coverage must refresh public lookthrough holdings: {fof_service.calls}")
    if fof_result.get("evidence_gate_status") != "sufficient" or fof_result.get("disclosed_fund_count") != 10:
        raise AssertionError(f"FOF lookthrough result must expose the evaluation gate: {fof_result}")
    if sync_fof_lookthrough("000051.OF", {"evaluation_profile_key": "index_fund"}).get("status") != "not_applicable":
        raise AssertionError("Non-FOF ranking sync must not call the FOF holding source")

    fof_states = build_fof_lookthrough_coverage_states([
        {
            "peer_group_key": "peer-fof-equity-allocation",
            "peer_group_name": "FOF-偏股配置",
            "strategy_family_key": "fof_equity_allocation",
            "wind_code": "READY.OF",
        },
        {
            "peer_group_key": "peer-fof-equity-allocation",
            "peer_group_name": "FOF-偏股配置",
            "strategy_family_key": "fof_equity_allocation",
            "wind_code": "MISSING.OF",
        },
    ], {
        code: [
            {"metric_window": "1y", "metric_name": "annualized_return", "metric_value": 0.08},
            {"metric_window": "1y", "metric_name": "max_drawdown", "metric_value": -0.1},
            {"metric_window": "1y", "metric_name": "sharpe_ratio", "metric_value": 0.8},
        ]
        for code in ("READY.OF", "MISSING.OF")
    }, {"READY.OF": True}, target_per_group=2)
    if len(fof_states) != 1 or fof_states[0]["valid_count"] != 1:
        raise AssertionError(f"FOF coverage must count only passed lookthrough gates: {fof_states}")
    if fof_states[0]["candidates"] != ["MISSING.OF"]:
        raise AssertionError(f"FOF coverage must select metric-ready funds missing lookthrough: {fof_states}")

    if not manager_tenure_required({
        "status": "resolved",
        "strategy_family_key": "active_equity_core",
        "active_passive": "active",
    }):
        raise AssertionError("Active evaluation coverage must also sync manager tenure")
    for context in (
        {"status": "unresolved", "strategy_family_key": "active_equity_core"},
        {"status": "resolved", "strategy_family_key": "cash_management", "active_passive": "active"},
        {"status": "resolved", "strategy_family_key": "index_broad", "active_passive": "passive"},
    ):
        if manager_tenure_required(context):
            raise AssertionError(f"Category must not require manager tenure sync: {context}")

    states = [
        {"candidates": ["A.OF", "B.OF", "C.OF"], "selected_count": 0},
        {"candidates": ["D.OF", "E.OF"], "selected_count": 0},
    ]
    if round_robin_peer_candidates(states, 4) != ["A.OF", "D.OF", "B.OF", "E.OF"]:
        raise AssertionError(f"Peer backfill must round-robin categories: {states}")

    company_states = build_company_evaluation_group_states([
        {"peer_group_key": "peer-a", "peer_group_name": "同类A", "strategy_family_key": "active_equity_core", "wind_code": "A1.OF"},
        {"peer_group_key": "peer-a", "peer_group_name": "同类A", "strategy_family_key": "active_equity_core", "wind_code": "A2.OF"},
        {"peer_group_key": "peer-b", "peer_group_name": "同类B", "strategy_family_key": "fixed_income_general", "wind_code": "B1.OF"},
    ], {
        "A1.OF": [
            {"metric_window": "1y", "metric_name": "annualized_return", "metric_value": 0.1},
            {"metric_window": "1y", "metric_name": "max_drawdown", "metric_value": -0.1},
            {"metric_window": "1y", "metric_name": "sharpe_ratio", "metric_value": 1.0},
        ],
    }, target_per_group=2)
    company_state_map = {state["peer_group_key"]: state for state in company_states}
    if company_state_map["peer-a"]["valid_count"] != 1 or company_state_map["peer-a"]["candidates"] != ["A2.OF"]:
        raise AssertionError(f"Company coverage must retain valid samples and select only gaps: {company_states}")
    if company_state_map["peer-b"]["desired_count"] != 1 or company_state_map["peer-b"]["candidates"] != ["B1.OF"]:
        raise AssertionError(f"Company coverage target cannot exceed classified entities: {company_states}")

    index_configs = [
        {"paths": [("selected", "tracking_error")], "required_for_sample": True, "valid_range": (0, 0.1)},
        {"paths": [("latest", "aum")], "required_for_sample": True, "valid_range": (0.000001, 1000000)},
    ]
    if _panel_has_required_category_metrics([
        {"metric_window": "1y", "metric_name": "annualized_return", "metric_value": 0.1},
    ], index_configs):
        raise AssertionError("Index coverage cannot treat annualized return as sufficient category evidence")
    if not _panel_has_required_category_metrics([
        {"metric_window": "1y", "metric_name": "tracking_error", "metric_value": 0.02},
        {"metric_window": "latest", "metric_name": "aum", "metric_value": 15},
    ], index_configs):
        raise AssertionError("Index coverage must accept its actual required category evidence")

    manager_gaps = manager_tenure_peer_gap_states({
        "product_tenures": {"items": [
            {
                "fund_code": "TARGET-A.OF",
                "entity_id": "entity-a",
                "is_current": True,
                "peer_ranking": {
                    "status": "insufficient_peer_sample",
                    "peer_group_id": "peer-a",
                    "peer_group_name": "同类A",
                    "period_start": "2022-03-25",
                    "period_end": "2026-08-11",
                    "valid_peer_count": 1,
                    "minimum_peer_count": 5,
                },
            },
            {
                "fund_code": "TARGET-B.OF",
                "entity_id": "entity-b",
                "is_current": True,
                "peer_ranking": {
                    "status": "insufficient_peer_sample",
                    "peer_group_id": "peer-a",
                    "peer_group_name": "同类A",
                    "period_start": "2023-01-01",
                    "period_end": "2026-08-11",
                    "valid_peer_count": 3,
                    "minimum_peer_count": 5,
                },
            },
            {
                "fund_code": "HISTORY.OF",
                "is_current": False,
                "peer_ranking": {
                    "status": "insufficient_peer_sample",
                    "peer_group_id": "peer-history",
                    "period_start": "2020-01-01",
                    "period_end": "2021-01-01",
                    "valid_peer_count": 1,
                    "minimum_peer_count": 5,
                },
            },
        ]},
    })
    if len(manager_gaps) != 1:
        raise AssertionError(f"Only current products should drive manager peer backfill: {manager_gaps}")
    gap = manager_gaps[0]
    if gap["needed_count"] != 4 or str(gap["period_start"]) != "2022-03-25":
        raise AssertionError(f"Manager peer backfill must use the earliest and largest gap: {gap}")
    if gap["target_entity_ids"] != {"entity-a", "entity-b"}:
        raise AssertionError(f"Target products must be excluded from peer candidates: {gap}")

    if not _tenure_nav_coverage_is_valid(
        {"first_date": "2022-03-25", "last_date": "2026-08-11", "observations": 1100},
        date(2022, 3, 25),
        date(2026, 8, 11),
    ):
        raise AssertionError("Full-period real NAV should satisfy manager tenure peer coverage")
    if _tenure_nav_coverage_is_valid(
        {"first_date": "2023-07-18", "last_date": "2026-08-11", "observations": 747},
        date(2022, 3, 25),
        date(2026, 8, 11),
    ):
        raise AssertionError("Short history cannot satisfy a long manager tenure period")

    evaluation_gaps = manager_evaluation_gap_codes({
        "current_funds": [
            {"wind_code": "READY.OF", "professional_score": 80, "establishment_date": "2020-01-01"},
            {"wind_code": "PARTIAL.OF", "professional_score": 70, "establishment_date": "2020-01-01",
             "evaluation_missing_data": ["metric_window:manager_tenure"]},
            {"wind_code": "MISSING.OF", "professional_score": None, "establishment_date": "2020-01-01"},
            {"wind_code": "NEW.OF", "professional_score": None, "establishment_date": "2026-01-01"},
        ],
    }, limit=10, as_of_date=date(2026, 8, 12))
    if evaluation_gaps != ["PARTIAL.OF", "MISSING.OF"]:
        raise AssertionError(f"Manager evaluation backfill must include incomplete tenure windows: {evaluation_gaps}")
    required_days = manager_evaluation_required_days({
        "product_tenures": {"items": [
            {"fund_code": "PARTIAL.OF", "is_current": True, "start_date": "2022-03-25"},
            {"fund_code": "MISSING.OF", "is_current": True, "start_date": "2024-01-01"},
        ]},
    }, evaluation_gaps, as_of_date=date(2026, 8, 12))
    if required_days != (date(2026, 8, 12) - date(2022, 3, 25)).days + 7:
        raise AssertionError(f"Manager evaluation backfill must cover the full current tenure: {required_days}")

    script_source = Path(__file__).resolve().parents[1].joinpath(
        "scripts", "sync_fund_ranking_metrics.py"
    ).read_text(encoding="utf-8")
    if len(BROWSER_CORE_PEER_GROUPS) < 10 or BROWSER_CORE_TARGET_PER_GROUP != 10:
        raise AssertionError("Browser core coverage must retain at least ten categories with a ten-fund floor")
    coverage_branch = script_source.split("elif not codes and (args.peer_evaluation_coverage or args.browser_core_coverage):", 1)[1].split(
        "elif not codes:", 1
    )[0]
    for required in ("BROWSER_CORE_PEER_GROUPS", "BROWSER_CORE_TARGET_PER_GROUP", "include_exchange_funds=True"):
        if required not in coverage_branch:
            raise AssertionError(f"Peer evaluation backfill branch missing: {required}")
    for required in ("--company-evaluation-coverage", "select_company_evaluation_coverage", "--company-target-per-group"):
        if required not in script_source:
            raise AssertionError(f"Company evaluation backfill mode missing: {required}")
    for required in ("evaluation_coverage_mode", "manager_tenure_required", "tenure_synced", "manager_tenure_history_status"):
        if required not in script_source:
            raise AssertionError(f"Evaluation coverage must complete manager tenure automatically: {required}")
    for required in ("--fof-lookthrough-coverage", "select_fof_lookthrough_coverage_codes"):
        if required not in script_source:
            raise AssertionError(f"FOF lookthrough backfill mode missing: {required}")

    print("OK ranking sync keeps latest NAV and persists real AUM and fee snapshots")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
