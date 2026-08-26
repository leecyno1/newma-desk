from services.fund_bond_holding_service import FundBondHoldingService


PAYLOAD = r'''var apidata={ content:"<div><font class='px12'>2026-06-30</font><table class='w782 comm tzxq'><tbody><tr><td>1</td><td>232580009</td><td>25中信银行二级资本债01BC</td><td>6.88%</td><td>300,259.73</td></tr><tr><td>2</td><td>132026</td><td>G三峡EB2</td><td>2.45%</td><td>106,907.93</td></tr><tr><td>3</td><td>250431</td><td>25农发31</td><td>1.20%</td><td>52,000.00</td></tr></tbody></table></div>",arryear:[2026,2025],curyear:2026};'''


rows, years, current_year = FundBondHoldingService.parse_payload(
    PAYLOAD,
    source_url="https://fundf10.eastmoney.com/ccmx1_110017.html",
)

assert years == [2026, 2025]
assert current_year == 2026
assert len(rows) == 3
assert rows[0]["report_date"] == "2026-06-30"
assert rows[0]["bond_type"] == "financial"
assert rows[0]["nav_ratio"] == 0.0688
assert rows[0]["market_value_wan"] == 300259.73
assert rows[1]["bond_type"] == "convertible_exchangeable"
assert rows[2]["bond_type"] == "policy_bank"
assert FundBondHoldingService.classify_bond("齐翔转2")[0] == "convertible_exchangeable"
assert FundBondHoldingService.classify_bond("20浦发银行二级04")[0] == "financial"
assert FundBondHoldingService.classify_bond("26附息国债08")[0] == "government"
assert FundBondHoldingService.classify_bond("26内蒙古债01")[0] == "local_government"
assert FundBondHoldingService.classify_security_type("二级资本工具")[0] == "financial"
assert FundBondHoldingService.classify_security_type("国债")[0] == "government"
assert FundBondHoldingService.classify_security_type("地方政府债")[0] == "local_government"

rows[0].update({
    "issuer": "中信银行股份有限公司",
    "security_bond_type": "二级资本工具",
    "credit_rating": "AAA",
    "rating_type": "issuer_subject",
    "maturity_date": "2035-05-19",
    "coupon_rate": 0.0199,
    "metadata_status": "available",
})
rows[1].update({
    "issuer": None,
    "credit_rating": None,
    "rating_type": None,
    "maturity_date": None,
    "metadata_status": "unavailable",
})
rows[2].update({
    "issuer": "中国农业发展银行",
    "security_bond_type": "政策性金融债",
    "credit_rating": "AAA",
    "rating_type": "bond",
    "maturity_date": "2030-06-30",
    "coupon_rate": 0.018,
    "metadata_status": "available",
})

summary = FundBondHoldingService._summarize(rows)[0]
assert summary["disclosed_count"] == 3
assert summary["disclosed_nav_ratio"] == 0.1053
assert summary["classification_coverage"] == 1.0
assert summary["dominant_type"] == "金融债/资本债"
assert summary["metadata_available_count"] == 2
assert summary["issuer_concentration"]["issuer_count"] == 2
assert summary["rating_distribution"][0]["rating"] == "AAA"
assert summary["maturity_buckets"][2]["holding_count"] == 1
assert summary["maturity_buckets"][3]["holding_count"] == 1

four_period_rows = []
for report_date in ("2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30"):
    four_period_rows.extend([
        {
            "report_date": report_date,
            "sequence": 1,
            "bond_code": f"FIN-{report_date}",
            "bond_name": "银行二级资本债",
            "bond_type": "financial",
            "nav_ratio": 0.06,
            "market_value_wan": 100,
            "classification_basis": "公开主数据券种：二级资本工具",
            "issuer": "示例银行",
            "credit_rating": "AAA",
            "rating_type": "issuer_subject",
            "maturity_date": "2035-06-30",
            "metadata_status": "available",
            "source": "test",
            "source_url": "",
        },
        {
            "report_date": report_date,
            "sequence": 2,
            "bond_code": f"POL-{report_date}",
            "bond_name": "农发债",
            "bond_type": "policy_bank",
            "nav_ratio": 0.04,
            "market_value_wan": 80,
            "classification_basis": "公开主数据券种：政策性金融债",
            "issuer": "中国农业发展银行",
            "credit_rating": None,
            "rating_type": None,
            "maturity_date": "2030-06-30",
            "metadata_status": "available",
            "source": "test",
            "source_url": "",
        },
    ])

professional_profile = FundBondHoldingService._professional_profile(
    FundBondHoldingService._summarize(four_period_rows)
)
assert professional_profile["status"] == "available"
assert professional_profile["label"] == "金融债型公开证据"
assert professional_profile["averages"]["financial_share"] == 0.6
assert professional_profile["averages"]["rate_share"] == 0.4
assert professional_profile["formal_classification_ready"] is False
assert {item["value"] for item in FundBondHoldingService.style_evidence(professional_profile)} == {"金融债"}

legacy_local_rows = []
for report_date in ("2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30"):
    legacy_local_rows.append({
        "report_date": report_date,
        "sequence": 1,
        "bond_code": f"LOCAL-{report_date}",
        "bond_name": "26内蒙古债01",
        "bond_type": "government_local",
        "nav_ratio": 0.1,
        "market_value_wan": 100,
        "classification_basis": "旧口径",
        "metadata_status": "unavailable",
        "source": "test",
        "source_url": "",
    })

local_history = FundBondHoldingService._summarize(legacy_local_rows)
assert local_history[0]["buckets"][0]["key"] == "local_government"
local_profile = FundBondHoldingService._professional_profile(local_history)
assert local_profile["averages"]["rate_share"] == 0
assert local_profile["averages"]["local_government_share"] == 1
assert local_profile["label"] not in {"利率债型公开证据", "金融债型公开证据"}
assert "地方政府债暴露" in local_profile["secondary_labels"]


def credit_profile(rating_type: str, rating: str):
    credit_rows = []
    for report_date in ("2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30"):
        credit_rows.append({
            "report_date": report_date,
            "sequence": 1,
            "bond_code": f"CREDIT-{report_date}",
            "bond_name": "信用债",
            "bond_type": "credit",
            "nav_ratio": 0.1,
            "market_value_wan": 100,
            "classification_basis": "测试信用债",
            "credit_rating": rating,
            "rating_type": rating_type,
            "metadata_status": "available",
            "source": "test",
            "source_url": "",
        })
    return FundBondHoldingService._professional_profile(FundBondHoldingService._summarize(credit_rows))


issuer_only_profile = credit_profile("issuer_subject", "AAA")
assert issuer_only_profile["label"] == "信用债主导，等级待核验"
assert issuer_only_profile["averages"]["bond_rating_coverage"] == 0
assert issuer_only_profile["averages"]["issuer_rating_coverage"] == 1

high_grade_profile = credit_profile("bond", "AAA")
assert high_grade_profile["label"] == "中高等级信用债公开证据"
assert high_grade_profile["averages"]["bond_rating_coverage"] == 1
assert {item["value"] for item in FundBondHoldingService.style_evidence(high_grade_profile)} == {"高等级信用", "信用债"}

low_grade_profile = credit_profile("bond", "AA")
assert low_grade_profile["label"] == "中低等级信用债风险证据"
assert {item["value"] for item in FundBondHoldingService.style_evidence(low_grade_profile)} == {"中低等级信用", "信用债"}

print("OK public bond holdings parse and aggregate without claiming full-portfolio coverage")
