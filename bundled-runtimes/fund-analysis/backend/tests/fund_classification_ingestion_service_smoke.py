import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.fund_classification_ingestion_service import FundClassificationIngestionService
from repositories.fund_classification_repo import FundClassificationRepo


class _Result:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row

    def fetchall(self):
        return [self.row] if self.row is not None else []


class _MigrationConnection:
    def __init__(self, existing_source: str, curated: bool):
        self.existing_source = existing_source
        self.curated = curated

    def execute(self, statement, params=None):
        sql = str(statement)
        if "FROM strategy_families" in sql:
            return _Result(SimpleNamespace(
                _mapping={
                    "id": "strategy-family-index-enhanced",
                    "key": "index_enhanced",
                    "asset_class": "index",
                    "active_passive": "active",
                }
            ))
        if "FROM peer_groups" in sql and "WHERE key" in sql:
            return _Result(SimpleNamespace(
                _mapping={
                    "id": "peer-index-enhanced-hs300",
                    "key": "peer-index-enhanced-hs300",
                    "benchmark_code": "000300.SH",
                }
            ))
        if "SELECT DISTINCT" in sql and "FROM fund_share_classes" in sql:
            return _Result(SimpleNamespace(
                id="legacy-auto-entity",
                source=self.existing_source,
                strategy_family_id="strategy-family-index-broad",
                normalized_name="审计沪深300指数增强",
            ))
        if "UNION ALL" in sql and "benchmark_mappings" in sql:
            return _Result(SimpleNamespace(value=1) if self.curated else None)
        return _Result()

    def begin_nested(self):
        class _Nested:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, traceback):
                return False

        return _Nested()


class _MigrationEngine:
    def __init__(self, existing_source: str, curated: bool):
        self.connection = _MigrationConnection(existing_source, curated)

    def begin(self):
        connection = self.connection

        class _Begin:
            def __enter__(self):
                return connection

            def __exit__(self, exc_type, exc, traceback):
                return False

        return _Begin()


def _migration_group():
    return {
        "strategy_family_key": "index_enhanced",
        "asset_class": "index",
        "active_passive": "active",
        "peer_group_key": "peer-index-enhanced-hs300",
        "benchmark_code": "000300.SH",
        "benchmark_name": "沪深300",
        "canonical_code": "980004.OF",
        "canonical_name": "审计沪深300指数增强",
        "normalized_name": "审计沪深300指数增强",
        "shares": [{"wind_code": "980004.OF"}],
    }


def main() -> int:
    service = FundClassificationIngestionService()
    plan = service.build_plan([
        {
            "id": "money-a",
            "wind_code": "980001.OF",
            "name": "审计现金宝货币A",
            "type": "货币型",
            "establishment_date": "2020-01-01",
        },
        {
            "id": "money-b",
            "wind_code": "980002.OF",
            "name": "审计现金宝货币B类",
            "type": "货币型",
            "establishment_date": "2020-02-01",
        },
        {
            "id": "index-a",
            "wind_code": "980003.OF",
            "name": "审计沪深300ETF联接A",
            "type": "指数型",
            "raw_data": {"universe": {
                "benchmark": "沪深300指数收益率*95%+银行活期存款利率*5%",
                "invest_type": "被动指数型",
                "contract_type": "股票型",
            }},
        },
        {
            "wind_code": "980007.OF",
            "name": "审计中证A500ETF联接A",
            "type": "指数型",
            "raw_data": {"universe": {
                "benchmark": "中证A500指数收益率×95%+银行活期存款利率(税后)×5%",
                "invest_type": "被动指数型",
                "contract_type": "股票型",
            }},
        },
        {
            "wind_code": "989035.OF",
            "name": "审计沪深300医药卫生ETF联接A",
            "type": "指数型",
            "raw_data": {"universe": {
                "benchmark": "活期存款利率(税后)×5%+沪深300医药卫生指数×95%",
                "invest_type": "被动指数型",
                "contract_type": "股票型",
            }},
        },
        {
            "wind_code": "989099.OF",
            "name": "审计养老目标日期2035三年持有期混合(FOF)-A",
            "type": "混合型",
            "raw_data": {"universe": {
                "benchmark": "沪深300指数收益率×40%+上证国债指数收益率×60%",
                "invest_type": "混合型",
                "contract_type": "混合型",
            }},
        },
        {
            "wind_code": "989036.OF",
            "name": "审计沪深300医药卫生ETF联接C",
            "type": "指数型",
            "raw_data": {"universe": {
                "benchmark": "活期存款利率(税后)×5%+沪深300医药卫生指数×95%",
                "invest_type": "被动指数型",
                "contract_type": "股票型",
            }},
        },
        {
            "wind_code": "980008.OF",
            "name": "审计同业存单AAA指数A",
            "type": "指数型",
            "raw_data": {"universe": {
                "benchmark": "中证同业存单AAA指数收益率×95%+银行人民币一年定期存款利率(税后)×5%",
                "invest_type": "被动指数型",
                "contract_type": "债券型",
            }},
        },
        {
            "wind_code": "980004.OF",
            "name": "审计沪深300指数增强A",
            "type": "指数型",
            "raw_data": {"universe": {
                "benchmark": "沪深300指数收益率*95%+银行活期存款利率*5%",
                "invest_type": "增强指数型",
                "contract_type": "股票型",
            }},
        },
        {
            "wind_code": "980005.OF",
            "name": "审计沪深300红利低波ETF",
            "type": "指数型",
            "raw_data": {"info": {"benchmark": "沪深300红利低波指数收益率"}},
        },
        {
            "wind_code": "981101.OF",
            "name": "审计中证500指数增强A",
            "type": "指数型",
            "raw_data": {"universe": {
                "benchmark": "中证500指数收益率×95%+银行活期存款利率(税后)×5%",
                "invest_type": "增强指数型",
                "contract_type": "股票型",
            }},
        },
        {
            "wind_code": "980030.OF",
            "name": "审计中证800指数增强A",
            "type": "指数型",
            "raw_data": {"universe": {
                "benchmark": "中证800指数收益率×95%+银行活期存款利率(税后)×5%",
                "invest_type": "增强指数型",
                "contract_type": "股票型",
            }},
        },
        {
            "wind_code": "980031.OF",
            "name": "审计中证2000指数增强A",
            "type": "指数型",
            "raw_data": {"universe": {
                "benchmark": "中证2000指数收益率×95%+银行活期存款利率(税后)×5%",
                "invest_type": "增强指数型",
                "contract_type": "股票型",
            }},
        },
        {
            "wind_code": "980032.OF",
            "name": "审计中证A50指数增强A",
            "type": "指数型",
            "raw_data": {"universe": {
                "benchmark": "中证A50指数收益率×95%+银行活期存款利率(税后)×5%",
                "invest_type": "增强指数型",
                "contract_type": "股票型",
            }},
        },
        {
            "wind_code": "980033.OF",
            "name": "审计创业板指数增强A",
            "type": "指数型",
            "raw_data": {"universe": {
                "benchmark": "创业板指数收益率×95%+银行活期存款利率(税后)×5%",
                "invest_type": "增强指数型",
                "contract_type": "股票型",
            }},
        },
        {
            "wind_code": "980034.OF",
            "name": "审计科创50指数增强A",
            "type": "指数型",
            "raw_data": {"universe": {
                "benchmark": "上证科创板50成份指数收益率×95%+银行活期存款利率(税后)×5%",
                "invest_type": "增强指数型",
                "contract_type": "股票型",
            }},
        },
        {
            "wind_code": "980035.OF",
            "name": "审计上证50指数增强A",
            "type": "指数型",
            "raw_data": {"universe": {
                "benchmark": "上证50指数收益率×95%+银行活期存款利率(税后)×5%",
                "invest_type": "增强指数型",
                "contract_type": "股票型",
            }},
        },
        {
            "wind_code": "981102.OF",
            "name": "审计主题指数增强A",
            "type": "指数型",
            "raw_data": {"universe": {
                "benchmark": "中证医疗主题指数收益率×95%+银行活期存款利率(税后)×5%",
                "invest_type": "增强指数型",
                "contract_type": "股票型",
            }},
        },
        {
            "wind_code": "980006.OF",
            "name": "审计信用债基金A",
            "type": "债券型",
            "raw_data": {"universe": {
                "benchmark": "中证全债指数×100%",
                "invest_type": "债券型",
                "contract_type": "债券型",
            }},
        },
        {
            "wind_code": "980009.OF",
            "name": "审计价值股票A",
            "type": "股票型",
            "raw_data": {"universe": {
                "benchmark": "沪深300指数×80%+中证全债指数×20%",
                "invest_type": "股票型",
                "contract_type": "股票型",
            }},
        },
        {
            "wind_code": "980010.OF",
            "name": "审计价值股票C",
            "type": "股票型",
            "raw_data": {"universe": {
                "benchmark": "沪深300指数×80%+中证全债指数×20%",
                "invest_type": "股票型",
                "contract_type": "股票型",
            }},
        },
        {
            "wind_code": "150003.SZ",
            "name": "审计价值股票",
            "type": "股票型",
            "raw_data": {"universe": {
                "benchmark": "沪深300指数×80%+中证全债指数×20%",
                "invest_type": "股票型",
                "contract_type": "股票型",
            }},
        },
        {
            "wind_code": "980011.OF",
            "name": "审计成长股票A",
            "type": "股票型",
            "raw_data": {"universe": {
                "benchmark": "中证1000指数收益率×95%+银行活期存款利率(税后)×5%",
                "invest_type": "普通股票型",
                "contract_type": "股票型",
            }},
        },
        {
            "wind_code": "980012.OF",
            "name": "审计医药股票A",
            "type": "股票型",
            "raw_data": {"universe": {
                "benchmark": "沪深300指数×80%+中证全债指数×20%",
                "invest_type": "股票型",
                "contract_type": "股票型",
            }},
        },
        {
            "wind_code": "980013.OF",
            "name": "审计多元股票A",
            "type": "股票型",
            "raw_data": {"universe": {
                "benchmark": "沪深300指数×80%+恒生指数×10%+中证全债指数×10%",
                "invest_type": "股票型",
                "contract_type": "股票型",
            }},
        },
        {
            "wind_code": "980014.OF",
            "name": "审计均衡股票A",
            "type": "股票型",
            "raw_data": {"universe": {
                "benchmark": "沪深300指数×45%+恒生指数×45%+中证全债指数×10%",
                "invest_type": "股票型",
                "contract_type": "股票型",
            }},
        },
        {
            "wind_code": "980015.OF",
            "name": "审计稳健纯债A",
            "type": "债券型",
            "raw_data": {"universe": {
                "benchmark": "中证全债指数×100%",
                "invest_type": "债券型",
                "contract_type": "债券型",
            }},
        },
        {
            "wind_code": "980016.OF",
            "name": "审计稳健纯债C",
            "type": "债券型",
            "raw_data": {"universe": {
                "benchmark": "中证全债指数收益率×100%",
                "invest_type": "债券型",
                "contract_type": "债券型",
            }},
        },
        {
            "wind_code": "980017.OF",
            "name": "审计安心纯债A",
            "type": "债券型",
            "raw_data": {"universe": {
                "benchmark": "中证综合债券指数×100%",
                "invest_type": "债券型",
                "contract_type": "债券型",
            }},
        },
        {
            "wind_code": "980026.OF",
            "name": "审计中债综合全价纯债A",
            "type": "债券型",
            "raw_data": {"universe": {
                "benchmark": "中债-综合指数-全价指数×100%",
                "invest_type": "债券型",
                "contract_type": "债券型",
            }},
        },
        {
            "wind_code": "980027.OF",
            "name": "审计中债综合未注明纯债A",
            "type": "债券型",
            "raw_data": {"universe": {
                "benchmark": "中债综合指数收益率×100%",
                "invest_type": "债券型",
                "contract_type": "债券型",
            }},
        },
        {
            "wind_code": "980028.OF",
            "name": "审计中债综合财富短债A",
            "type": "债券型",
            "raw_data": {"universe": {
                "benchmark": "中债综合财富(1年以下)指数收益率×90%+一年期定期存款利率(税后)×10%",
                "invest_type": "债券型",
                "contract_type": "债券型",
            }},
        },
        {
            "wind_code": "981103.OF",
            "name": "审计中债综合财富中短债A",
            "type": "债券型",
            "raw_data": {"universe": {
                "benchmark": "中债综合财富(1-3年)指数收益率×80%+一年期定期存款利率(税后)×20%",
                "invest_type": "债券型",
                "contract_type": "债券型",
            }},
        },
        {
            "wind_code": "981104.OF",
            "name": "审计中债新综合全价纯债A",
            "type": "债券型",
            "raw_data": {"universe": {
                "benchmark": "中债新综合指数(全价)收益率×100%",
                "invest_type": "债券型",
                "contract_type": "债券型",
            }},
        },
        {
            "wind_code": "981105.OF",
            "name": "审计中债总财富中短债A",
            "type": "债券型",
            "raw_data": {"universe": {
                "benchmark": "中债总财富(1-3年)指数收益率×80%+一年期定期存款利率(税后)×20%",
                "invest_type": "债券型",
                "contract_type": "债券型",
            }},
        },
        {
            "wind_code": "981106.OF",
            "name": "审计多债券指数纯债A",
            "type": "债券型",
            "raw_data": {"universe": {
                "benchmark": "中债综合财富(1年以下)指数收益率×60%+中债综合财富(1-3年)指数收益率×30%+一年期定期存款利率(税后)×10%",
                "invest_type": "债券型",
                "contract_type": "债券型",
            }},
        },
        {
            "wind_code": "981107.OF",
            "name": "审计中债0至3年综合财富纯债A",
            "type": "债券型",
            "raw_data": {"universe": {
                "benchmark": "中债-0—3年债券综合财富(总值)指数收益率×100%",
                "invest_type": "债券型",
                "contract_type": "债券型",
            }},
        },
        {
            "wind_code": "980018.OF",
            "name": "审计可转债A",
            "type": "债券型",
            "raw_data": {"universe": {
                "benchmark": "中证全债指数×100%",
                "invest_type": "债券型",
                "contract_type": "债券型",
            }},
        },
        {
            "wind_code": "980019.OF",
            "name": "审计收益债券A",
            "type": "债券型",
            "raw_data": {"universe": {
                "benchmark": "中证综合债指数收益率×90%+沪深300指数收益率×10%",
                "invest_type": "债券型",
                "contract_type": "债券型",
            }},
        },
        {
            "wind_code": "980020.OF",
            "name": "审计偏股配置混合A",
            "type": "混合型",
            "raw_data": {"universe": {
                "benchmark": "沪深300指数收益率×65%+中证港股通综合指数收益率×15%+中债综合全价指数收益率×20%",
                "invest_type": "混合型",
                "contract_type": "混合型",
            }},
        },
        {
            "wind_code": "980024.OF",
            "name": "审计高权益债券A",
            "type": "债券型",
            "raw_data": {"universe": {
                "benchmark": "中债综合指数收益率×70%+沪深300指数收益率×30%",
                "invest_type": "债券型",
                "contract_type": "债券型",
            }},
        },
        {
            "wind_code": "980025.OF",
            "name": "审计新能源股票A",
            "type": "股票型",
            "raw_data": {"universe": {
                "benchmark": "中证新能源指数收益率×75%+中证港股通能源综合指数收益率×10%+中证综合债券指数收益率×15%",
                "invest_type": "股票型",
                "contract_type": "股票型",
            }},
        },
        {
            "wind_code": "980021.OF",
            "name": "审计平衡配置混合A",
            "type": "混合型",
            "raw_data": {"universe": {
                "benchmark": "沪深300指数收益率×50%+中债综合指数收益率×50%",
                "invest_type": "灵活配置型",
                "contract_type": "混合型",
            }},
        },
        {
            "wind_code": "980022.OF",
            "name": "审计偏债配置混合A",
            "type": "债券型",
            "raw_data": {"universe": {
                "benchmark": "沪深300指数收益率×20%+中债综合财富指数收益率×80%",
                "invest_type": "混合型",
                "contract_type": "混合型",
            }},
        },
        {
            "wind_code": "980023.OF",
            "name": "审计权重缺失混合A",
            "type": "混合型",
            "raw_data": {"universe": {
                "benchmark": "沪深300指数收益率×60%+中债综合指数收益率×20%",
                "invest_type": "混合型",
                "contract_type": "混合型",
            }},
        },
        {
            "wind_code": "0000371.OF",
            "name": "审计脏代码货币A",
            "type": "货币型",
        },
    ])

    groups = plan.get("groups") or []
    if plan.get("summary", {}).get("eligible_funds") != 36 or len(groups) != 31:
        raise AssertionError(f"Only high-confidence standardized funds should be eligible: {plan}")
    money = next(group for group in groups if group.get("strategy_family_key") == "cash_management")
    if money.get("benchmark_code") != "DR007" or len(money.get("shares") or []) != 2:
        raise AssertionError(f"Money share classes must merge into one DR007 entity: {money}")
    if money.get("canonical_name") != "审计现金宝货币":
        raise AssertionError(f"Share suffix normalization failed: {money}")
    if sum(1 for share in money["shares"] if share.get("is_primary")) != 1:
        raise AssertionError(f"Entity must have exactly one primary share: {money}")

    index = next(group for group in groups if group.get("peer_group_key") == "peer-index-hs300")
    if index.get("benchmark_code") != "000300.SH" or index.get("peer_group_key") != "peer-index-hs300":
        raise AssertionError(f"Exact declared index benchmark mapping failed: {index}")
    a500 = next(group for group in groups if group.get("benchmark_code") == "000510.SH")
    if a500.get("peer_group_key") != "peer-index-csi-a500":
        raise AssertionError(f"A500 benchmark mapping failed: {a500}")
    deposit = next(group for group in groups if group.get("strategy_family_key") == "index_fixed_income")
    if deposit.get("benchmark_code") != "931059.CSI" or deposit.get("asset_class") != "fixed_income":
        raise AssertionError(f"Fixed-income index must not enter equity index peers: {deposit}")
    enhanced_indices = [
        group for group in groups if group.get("strategy_family_key") == "index_enhanced"
    ]
    if {group.get("peer_group_key") for group in enhanced_indices} != {
        "peer-index-enhanced-hs300",
        "peer-index-enhanced-csi500",
        "peer-index-enhanced-csi800",
        "peer-index-enhanced-csi2000",
        "peer-index-enhanced-csi-a50",
        "peer-index-enhanced-chinext",
        "peer-index-enhanced-star50",
        "peer-index-enhanced-sse50",
    }:
        raise AssertionError(f"Enhanced index funds need separate same-index peer groups: {enhanced_indices}")
    if any(group.get("active_passive") != "active" for group in enhanced_indices):
        raise AssertionError(f"Enhanced index funds must remain active products: {enhanced_indices}")

    active_equity = next(group for group in groups if group.get("peer_group_key") == "peer-active-equity-stock-hs300")
    if len(active_equity.get("shares") or []) != 3 or active_equity.get("benchmark_weight") != 80:
        raise AssertionError(f"Active equity share classes and primary benchmark weight are wrong: {active_equity}")
    if active_equity.get("canonical_code") != "980009.OF":
        raise AssertionError(f"Open-end A share must take priority over legacy exchange shares: {active_equity}")
    if active_equity.get("benchmark_type") != "composite_primary_equity_reference":
        raise AssertionError(f"Composite benchmark must remain explicitly identified: {active_equity}")
    active_csi1000 = next(
        group for group in groups if group.get("peer_group_key") == "peer-active-equity-stock-csi1000"
    )
    if active_csi1000.get("benchmark_code") != "000852.SH":
        raise AssertionError(f"Active equity CSI1000 reference mapping failed: {active_csi1000}")
    cross_market = next(
        group for group in groups
        if group.get("peer_group_key") == "peer-active-equity-cross-market-cn-hk"
    )
    if cross_market.get("benchmark_type") != "contract_composite_benchmark":
        raise AssertionError(f"Cross-market fund must retain its contract composite type: {cross_market}")
    if [item.get("weight") for item in cross_market.get("contract_components") or []] != [45.0, 45.0, 10.0]:
        raise AssertionError(f"Cross-market contract weights are not auditable: {cross_market}")

    total_bond = next(group for group in groups if group.get("benchmark_code") == "H11001.CSI")
    if len(total_bond.get("shares") or []) != 2 or total_bond.get("benchmark_weight") != 100:
        raise AssertionError(f"Total-bond share classes and benchmark mapping are wrong: {total_bond}")
    composite_bond = next(group for group in groups if group.get("benchmark_code") == "H11009.CSI")
    if composite_bond.get("strategy_family_key") != "fixed_income_general":
        raise AssertionError(f"Composite bond must enter general fixed-income peers: {composite_bond}")
    chinabond_composite = next(
        group for group in groups
        if group.get("peer_group_key") == "peer-fixed-income-chinabond-composite-full-price"
    )
    if chinabond_composite.get("benchmark_code") != "CONTRACT-CBA-COMPOSITE-FULL-PRICE":
        raise AssertionError(f"ChinaBond full-price contract bucket is wrong: {chinabond_composite}")
    if chinabond_composite.get("benchmark_type") != "contract_benchmark_bucket":
        raise AssertionError(f"Contract bucket must not pretend to be an official quote code: {chinabond_composite}")
    contract_buckets = {
        group.get("benchmark_name"): group
        for group in groups
        if group.get("benchmark_type") == "contract_benchmark_bucket"
    }
    expected_contract_buckets = {
        "中债综合指数·全价·全期限",
        "中债综合指数·价格口径未注明·全期限",
        "中债综合指数·财富·1年以下",
        "中债综合指数·财富·1—3年",
        "中债新综合指数·全价·全期限",
        "中债总指数·财富·1—3年",
        "中债综合指数·财富·0—3年",
    }
    if set(contract_buckets) != expected_contract_buckets:
        raise AssertionError(f"ChinaBond base, price-return and tenor dimensions must not merge: {contract_buckets}")
    if contract_buckets["中债综合指数·财富·1年以下"].get("benchmark_weight") != 90:
        raise AssertionError(f"ChinaBond deposit secondary weight parsing failed: {contract_buckets}")
    enhanced_bond = next(group for group in groups if group.get("strategy_family_key") == "fixed_income_equity_allocation")
    if enhanced_bond.get("benchmark_weight") != 10:
        raise AssertionError(f"Bond fund equity allocation bucket failed: {enhanced_bond}")
    sector_equity = next(group for group in groups if group.get("peer_group_key") == "peer-active-equity-sector-new-energy")
    if sector_equity.get("benchmark_weight") != 85:
        raise AssertionError(f"Explicit sector benchmark classification failed: {sector_equity}")
    sector_index = next(group for group in groups if group.get("peer_group_key") == "peer-index-hs300-health-care")
    if sector_index.get("strategy_family_key") != "index_sector" or sector_index.get("benchmark_code") != "000913.SH":
        raise AssertionError(f"Exact sector index classification failed: {sector_index}")
    if [share.get("wind_code") for share in sector_index.get("shares") or []] != ["989035.OF", "989036.OF"]:
        raise AssertionError(f"Sector index share classes must merge into one product: {sector_index}")

    mixed_groups = {group.get("strategy_family_key"): group for group in groups if group.get("asset_class") == "multi_asset"}
    if mixed_groups.get("mixed_equity_allocation", {}).get("benchmark_weight") != 80:
        raise AssertionError(f"Equity-oriented mixed fund weight bucket failed: {mixed_groups}")
    executable_components = FundClassificationIngestionService.resolve_contract_benchmark_components(
        "沪深300指数收益率×60%+中证综合债券指数收益率×30%+恒生指数收益率×10%"
    )
    if {item.get("code") for item in executable_components} != {"000300.SH", "H11009.CSI", "HSI"}:
        raise AssertionError(f"Supported mixed contract components must resolve exactly: {executable_components}")
    if mixed_groups.get("mixed_balanced_allocation", {}).get("benchmark_weight") != 50:
        raise AssertionError(f"Balanced mixed fund weight bucket failed: {mixed_groups}")
    if mixed_groups.get("mixed_bond_allocation", {}).get("benchmark_weight") != 20:
        raise AssertionError(f"Bond-oriented mixed fund weight bucket failed: {mixed_groups}")

    fof_group = next((group for group in groups if group.get("asset_class") == "fof"), None)
    if not fof_group or fof_group.get("strategy_family_key") != "fof_balanced_allocation":
        raise AssertionError(f"FOF must enter a dedicated FOF family: {fof_group}")
    if fof_group.get("benchmark_weight") != 40:
        raise AssertionError(f"FOF contract equity allocation was not preserved: {fof_group}")

    reasons = plan.get("summary", {}).get("skipped_by_reason") or {}
    if reasons.get("unsupported_or_ambiguous_index_enhanced_benchmark") != 1:
        raise AssertionError(f"Unregistered enhanced themes must remain outside supported peer groups: {plan}")
    if reasons.get("unsupported_or_ambiguous_index_benchmark") != 1:
        raise AssertionError(f"Theme index must not collapse into HS300: {plan}")
    if reasons.get("unsupported_active_equity_sector_or_index_style") != 1:
        raise AssertionError(f"Sector equity funds must not enter broad-reference peers: {plan}")
    if reasons.get("unsupported_active_equity_secondary_reference") != 1:
        raise AssertionError(f"Multiple equity market references must remain outside the catalog: {plan}")
    if reasons.get("active_equity_reference_weight_below_80"):
        raise AssertionError(f"Verified mainland/Hong Kong composites should no longer be rejected: {plan}")
    if reasons.get("unsupported_fixed_income_style") != 2:
        raise AssertionError(f"Credit and convertible bond funds must remain outside general bond peers: {plan}")
    if reasons.get("fixed_income_equity_weight_out_of_range") != 1:
        raise AssertionError(f"Bond funds with equity benchmark weight above 20% must remain outside the catalog: {plan}")
    if reasons.get("chinabond_multiple_bond_indices") != 1:
        raise AssertionError(f"Multiple ChinaBond indices must remain outside one-dimensional peer groups: {plan}")
    if reasons.get("mixed_benchmark_weights_incomplete") != 1:
        raise AssertionError(f"Incomplete mixed benchmark weights must remain unclassified: {plan}")
    if reasons.get("fof_requires_dedicated_classification"):
        raise AssertionError(f"Supported FOF products must no longer be discarded: {plan}")
    if reasons.get("invalid_fund_code_format") != 1:
        raise AssertionError(f"Malformed fund codes must not enter standardized entities: {plan}")

    for source, curated in [
        ("manual_curated", False),
        ("tushare_classification_ingestion", True),
    ]:
        repo = FundClassificationRepo(engine=_MigrationEngine(source, curated))
        repo._schema_ready_cache = True
        result = repo.apply_ingestion_plan([_migration_group()])
        if result.get("conflicts", [{}])[0].get("reason") != "existing_entity_strategy_family_conflict":
            raise AssertionError(f"Curated or externally sourced classification must block auto migration: {result}")

    print("OK classification ingestion only materializes high-confidence entities and share classes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
