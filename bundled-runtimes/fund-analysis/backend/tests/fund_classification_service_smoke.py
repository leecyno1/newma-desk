import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.fund_classification_service import FundClassificationService


def main() -> int:
    service = FundClassificationService()

    explicit = service.classify(
        {"wind_code": "FIXED.TEST", "name": "信用债测试基金", "type": "bond"},
        {
            "strategy_family_key": "fixed_income_credit",
            "asset_class": "fixed_income",
            "active_passive": "active",
            "peer_group": "固收-信用债-中久期",
            "primary_benchmark": "中债信用债总财富指数",
        },
    )
    if explicit.get("status") != "classified":
        raise AssertionError(f"Explicit classification should be usable: {explicit}")
    if explicit.get("strategy_family_key") != "fixed_income_credit":
        raise AssertionError(f"Explicit strategy family must win: {explicit}")
    if explicit.get("evaluation_profile_key") != "fixed_income":
        raise AssertionError(f"Fixed-income evaluation profile expected: {explicit}")
    if explicit.get("confidence", 0) < 0.9:
        raise AssertionError(f"Explicit classification should have high confidence: {explicit}")

    index_fund = service.classify(
        {"wind_code": "INDEX.TEST", "name": "沪深300ETF联接A", "type": "指数型"},
        {},
    )
    if index_fund.get("strategy_family_key") != "index_broad":
        raise AssertionError(f"Index fund classification failed: {index_fund}")
    if index_fund.get("active_passive") != "passive":
        raise AssertionError(f"Index fund must be passive: {index_fund}")
    if index_fund.get("evaluation_profile_key") != "index_fund":
        raise AssertionError(f"Index evaluation profile expected: {index_fund}")

    sector_index = service.classify(
        {"wind_code": "SECTOR.INDEX", "name": "沪深300医药卫生ETF", "type": "指数型"},
        {},
    )
    if sector_index.get("strategy_family_key") != "index_sector":
        raise AssertionError(f"Sector index must not fall into broad-index peers: {sector_index}")
    if sector_index.get("evaluation_profile_key") != "index_fund":
        raise AssertionError(f"Sector index should reuse passive-index evaluation: {sector_index}")

    fixed_index = service.classify(
        {"wind_code": "CD.TEST", "name": "中证同业存单AAA指数7天持有", "type": "指数型"},
        {},
    )
    if fixed_index.get("strategy_family_key") != "index_fixed_income":
        raise AssertionError(f"Fixed-income index classification failed: {fixed_index}")
    if fixed_index.get("asset_class") != "fixed_income" or fixed_index.get("evaluation_profile_key") != "index_fund":
        raise AssertionError(f"Fixed-income index must use index evaluation without entering equity peers: {fixed_index}")

    qdii_fund = service.classify(
        {
            "wind_code": "QDII.TEST",
            "name": "全球消费精选QDII",
            "type": "QDII",
            "raw_data": {"universe": {
                "invest_type": "股票型",
                "contract_type": "股票型",
                "benchmark": "MSCI全球指数收益率×100%",
            }},
        },
        {},
    )
    if qdii_fund.get("strategy_family_key") != "qdii_equity":
        raise AssertionError(f"QDII classification failed: {qdii_fund}")
    if qdii_fund.get("evaluation_profile_key") != "qdii_equity":
        raise AssertionError(f"QDII must not fall into active equity scoring: {qdii_fund}")

    qdii_name_only = service.classify(
        {"wind_code": "QDII.NAME", "name": "全球消费精选QDII", "type": "QDII"},
        {},
    )
    if qdii_name_only.get("status") != "insufficient_evidence":
        raise AssertionError(f"QDII must not infer asset class from its name: {qdii_name_only}")

    fof_fund = service.classify(
        {
            "wind_code": "FOF.TEST",
            "name": "养老目标日期2035三年持有期混合(FOF)-A",
            "type": "混合型",
            "contract_benchmark": "沪深300指数收益率×40%+上证国债指数收益率×60%",
            "invest_type": "混合型",
            "contract_type": "混合型",
        },
        {},
    )
    if fof_fund.get("status") != "classified":
        raise AssertionError(f"FOF with contract allocation evidence must be classified: {fof_fund}")
    if fof_fund.get("strategy_family_key") != "fof_balanced_allocation":
        raise AssertionError(f"FOF must enter its dedicated balanced peer family: {fof_fund}")
    if fof_fund.get("evaluation_profile_key") != "fof_balanced":
        raise AssertionError(f"FOF must use its dedicated evaluation profile: {fof_fund}")

    fof_missing_benchmark = service.classify(
        {"wind_code": "FOF.MISSING", "name": "养老目标日期混合(FOF)-A", "type": "混合型"},
        {},
    )
    if fof_missing_benchmark.get("status") != "insufficient_evidence":
        raise AssertionError(f"FOF without a contract benchmark must remain blocked: {fof_missing_benchmark}")

    profile_only = service.classify(
        {"wind_code": "PROFILE.TEST", "name": "基础信息待补", "type": ""},
        {"peer_group": "主动权益-行业主题", "primary_benchmark": "中证行业指数"},
    )
    if profile_only.get("strategy_family_key") != "active_equity_sector":
        raise AssertionError(f"Existing peer-group evidence should remain usable: {profile_only}")

    unknown = service.classify(
        {"wind_code": "UNKNOWN.TEST", "name": "无法识别产品", "type": "其他"},
        {},
    )
    if unknown.get("status") != "insufficient_evidence":
        raise AssertionError(f"Unknown fund must be explicitly unavailable: {unknown}")
    if unknown.get("strategy_family_key") is not None:
        raise AssertionError(f"Unknown fund must not default to active equity: {unknown}")
    if not unknown.get("missing_items"):
        raise AssertionError(f"Unknown classification must explain the evidence gap: {unknown}")

    for result in [explicit, index_fund, sector_index, fixed_index, qdii_fund, qdii_name_only, fof_fund, fof_missing_benchmark, profile_only, unknown]:
        for key in [
            "status",
            "asset_class",
            "strategy_family_key",
            "active_passive",
            "evaluation_profile_key",
            "confidence",
            "evidence",
            "missing_items",
        ]:
            if key not in result:
                raise AssertionError(f"Classification contract missing {key}: {result}")

    print("OK fund classification is multi-layered, evidenced and never defaults to active equity")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
