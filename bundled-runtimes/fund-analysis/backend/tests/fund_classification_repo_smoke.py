import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from repositories.fund_classification_repo import FundClassificationRepo


class FakeRow:
    def __init__(self, values: dict):
        self._mapping = values


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, engine):
        self.engine = engine

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, statement, params=None):
        self.engine.statements.append((str(statement), params or {}))
        return self.engine.results.pop(0)


class FakeEngine:
    def __init__(self, results):
        self.results = list(results)
        self.statements = []

    def connect(self):
        return FakeConnection(self)


def main() -> int:
    schema_row = FakeRow({"schema_ready": True})
    context_row = FakeRow({
        "fund_code": "000005.OF",
        "entity_id": "entity-000005",
        "canonical_code": "000005",
        "canonical_name": "信用债策略基金",
        "entity_source": "entity_standardization",
        "entity_source_updated_at": "2026-07-31",
        "share_class": "A",
        "share_class_source": "share_class_normalizer",
        "strategy_family_key": "fixed_income_credit",
        "strategy_family_name": "信用债策略",
        "asset_class": "fixed_income",
        "active_passive": "active",
        "strategy_family_source": "methodology_config",
        "peer_group_id": "peer-fixed-income",
        "peer_group_key": "peer-fixed-income-credit",
        "peer_group_name": "固收-信用债-中久期",
        "minimum_peer_count": 5,
        "peer_group_source": "peer_group_policy",
        "membership_role": "member",
        "matched_rules": {"matched": ["strategy_family=fixed_income_credit"]},
        "excluded_rules": {"excluded": []},
        "sample_as_of_date": "2026-07-31",
        "membership_confidence": 0.93,
        "membership_source": "peer_group_builder",
        "peer_group_membership_count": 1,
        "benchmark_code": "CBA_CREDIT",
        "benchmark_name": "中债信用债总财富指数",
        "benchmark_type": "bond_credit",
        "mapping_method": "peer_group_policy",
        "benchmark_confidence": 0.91,
        "benchmark_rationale": "按信用债策略族谱和久期层映射",
        "benchmark_evidence_refs": {"source": "taxonomy"},
        "effective_from": "2026-01-01",
        "effective_to": None,
        "benchmark_source": "benchmark_mapping_policy",
    })
    peer_rows = [
        FakeRow({
            "wind_code": "000005.OF",
            "name": "信用债策略基金",
            "type": "bond",
            "performance_data": {},
            "risk_metrics": {},
            "entity_id": "entity-000005",
            "canonical_code": "000005",
            "share_class": "A",
        }),
    ]
    engine = FakeEngine([FakeResult([schema_row]), FakeResult([context_row]), FakeResult(peer_rows)])
    repo = FundClassificationRepo(engine=engine)

    context = repo.get_classification_context("000005.OF", as_of_date="2026-08-01")
    if context.get("status") != "resolved":
        raise AssertionError(f"Context should resolve from normalized tables: {context}")
    if context.get("strategy_family_key") != "fixed_income_credit":
        raise AssertionError(f"Strategy family missing: {context}")
    if context.get("benchmark_mapping", {}).get("mapping_method") != "peer_group_policy":
        raise AssertionError(f"Benchmark method missing: {context}")
    evidence_sources = {item.get("source") for item in context.get("classification_evidence", [])}
    if not {"fund_entities", "strategy_families", "peer_group_members", "benchmark_mappings"}.issubset(evidence_sources):
        raise AssertionError(f"Classification evidence is incomplete: {context}")

    peers = repo.list_peer_funds("peer-fixed-income", target_wind_code="000005.OF")
    if [fund.get("wind_code") for fund in peers] != ["000005.OF"]:
        raise AssertionError(f"Explicit peer membership query failed: {peers}")

    executed_sql = "\n".join(statement for statement, _ in engine.statements)
    for table_name in [
        "fund_entities",
        "fund_share_classes",
        "strategy_families",
        "peer_group_members",
        "peer_groups",
        "benchmark_mappings",
    ]:
        if table_name not in executed_sql:
            raise AssertionError(f"Adapter does not read required table {table_name}")

    print("OK classification repository reads normalized taxonomy, peer and benchmark evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
