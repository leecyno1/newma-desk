import { spawnSync } from 'node:child_process'

const pythonCode = String.raw`
from datetime import UTC, datetime, timedelta
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

module_path = Path("backend/services/evidence_report.py")
spec = spec_from_file_location("evidence_report_smoke", module_path)
module = module_from_spec(spec)
spec.loader.exec_module(module)
build_buy_before_decision_summary = module.build_buy_before_decision_summary
build_sales_rule_cost_report_section = module.build_sales_rule_cost_report_section


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


fresh_date = datetime.now(UTC).date().isoformat()
stale_date = (datetime.now(UTC).date() - timedelta(days=31)).isoformat()

base_rule = {
    "purchase_status": "open",
    "purchase_status_label": "开放申购",
    "purchase_fee_rate": 0.001,
    "redemption_fee_rules": [{"label": "赎回费", "holding_days": 7, "fee_rate": 0.015}],
    "risk_level": "R3",
    "supports_sip": True,
    "min_sip_amount": 10,
    "min_purchase_amount": 10,
    "daily_limit_amount": 0,
    "sales_service_fee_rate": 0,
    "platform": "sales_platform",
    "source_updated_at": fresh_date,
    "source_url": "https://sales.example.com/funds/000001/risk",
    "notes": "",
}

valid_snapshot = {"status": "available", "source": "local_postgres.fund_sales_rules", "merged": dict(base_rule)}
valid_summary = build_buy_before_decision_summary(
    {"sample_status": "sufficient", "metrics": {}},
    valid_snapshot,
    [{"stock_name": "样本持仓", "stock_code": "000001", "industry": "样本行业", "weight": 0.1}],
    [{"metric_window": "manager_tenure", "metric_name": "tenure_days", "metric_value": 365}],
    "sip",
)
assert_true(not valid_summary["hardBlocks"], "fresh sales-platform R1-R5 source should not hard-block")

stale_rule = dict(base_rule)
stale_rule["source_updated_at"] = stale_date
stale_snapshot = {"status": "available", "source": "local_postgres.fund_sales_rules", "merged": stale_rule}
stale_report = build_sales_rule_cost_report_section(stale_snapshot, "sip")
stale_summary = build_buy_before_decision_summary(
    {"sample_status": "sufficient", "metrics": {}},
    stale_snapshot,
    [{"stock_name": "样本持仓", "stock_code": "000001", "industry": "样本行业", "weight": 0.1}],
    [{"metric_window": "manager_tenure", "metric_name": "tenure_days", "metric_value": 365}],
    "sip",
)
assert_true("R3（来源过期）" in stale_report, "stale source should be labelled in report table")
assert_true(
    any("销售风险等级（R1-R5 30天来源背书）" in item for item in stale_summary["hardBlocks"]),
    "stale R1-R5 source should hard-block buy-before summary",
)

tushare_rule = dict(base_rule)
tushare_rule["platform"] = "tushare"
tushare_rule["source_url"] = "https://docs.example/tushare.fund_basic"
tushare_snapshot = {"status": "available", "source": "local_postgres.fund_sales_rules", "merged": tushare_rule}
tushare_report = build_sales_rule_cost_report_section(tushare_snapshot, "lump_sum")
assert_true("Tushare fund_basic 不可作为 R1-R5 来源" in tushare_report, "report must reject Tushare as R1-R5 source")
assert_true("起购金额" in tushare_report and "定投支持" not in tushare_report.split("销售规则缺口")[1], "lump-sum gap should not require SIP-only fields")

missing_service_fee_rule = dict(base_rule)
missing_service_fee_rule.pop("sales_service_fee_rate")
missing_service_fee_snapshot = {"status": "available", "source": "local_postgres.fund_sales_rules", "merged": missing_service_fee_rule}
missing_service_fee_summary = build_buy_before_decision_summary(
    {"sample_status": "sufficient", "metrics": {}},
    missing_service_fee_snapshot,
    [{"stock_name": "样本持仓", "stock_code": "000001", "industry": "样本行业", "weight": 0.1}],
    [{"metric_window": "manager_tenure", "metric_name": "tenure_days", "metric_value": 365}],
    "lump_sum",
)
assert_true(
    any("销售服务费（30天来源背书）" in item for item in missing_service_fee_summary["hardBlocks"]),
    "missing sales service fee should hard-block deterministic buy-before summary",
)

print("OK deterministic reports require source-backed 30d R1-R5 and transaction fields")
`

const result = spawnSync('python3', ['-c', pythonCode], {
  cwd: new URL('..', import.meta.url),
  stdio: 'inherit',
})

if (result.error) throw result.error
if (result.status !== 0) {
  throw new Error(`report risk-level source gate smoke failed with exit ${result.status}`)
}
