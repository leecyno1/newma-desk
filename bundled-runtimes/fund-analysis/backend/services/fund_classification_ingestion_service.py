"""高置信度基金分类标准化 Module。

只把能够由基金法定类型或合同基准明确确认的对象写入标准化分类表；
模糊、未登记主题和缺少合同基准的对象保留为证据不足。
"""
import hashlib
import re
import unicodedata
from datetime import date, datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from services.fund_classification_catalog import FundClassificationCatalog


class FundClassificationIngestionService:
    """生成可审计的基金实体、份额、同类组和基准映射写入计划。"""

    SOURCE = "tushare_classification_ingestion"
    SHARE_CLASSES = {"A", "B", "C", "D", "E", "F", "H", "I", "R", "Y"}
    PRIMARY_SHARE_PRIORITY = {"A": 0, None: 1, "I": 2, "B": 3, "C": 4, "D": 5, "E": 6, "F": 7, "H": 8, "R": 9, "Y": 10}
    CURRENCY_PRIORITY = {"CNY": 0, "HKD": 1, "USD": 2}
    ENHANCED_INDEX_TERMS = ("增强", "量化", "主动", "策略增强")
    TERMINATED_TERMS = ("清算", "终止", "退市")
    ACTIVE_EQUITY_NAME_EXCLUSIONS = (
        "etf", "fof", "联接", "指数", "增强", "量化", "行业", "主题", "医药", "医疗",
        "健康", "科技", "半导体", "芯片", "集成电路", "新能源", "消费", "军工", "传媒",
        "金融", "地产", "人工智能", "互联网", "农业", "制造", "环保", "绿色", "资源",
        "能源", "材料", "低碳", "创新药", "新经济", "改革", "产业", "养老", "文化",
        "文体", "沪港深", "港股", "全球", "外向", "专精特新", "内需", "国策", "智造",
        "事件驱动", "大数据",
    )
    ACTIVE_FIXED_INCOME_NAME_EXCLUSIONS = (
        "可转债", "转债", "二级债", "信用", "产业债", "双债", "混合",
    )
    ACTIVE_EQUITY_ALLOWED_SECONDARY_TERMS = (
        "存款", "利率", "中债", "全债", "综合债", "国债", "债券", "同业存单",
    )
    MIXED_DEFENSIVE_BENCHMARK_TERMS = ("债", "国债", "存款", "利率", "现金", "DR007", "同业存单")
    MIXED_EQUITY_BENCHMARK_TERMS = (
        "沪深", "中证", "上证", "上海证券交易所", "深证", "创业板", "恒生", "港股", "国证", "股票",
        "金融", "地产", "消费", "产业", "科技", "互联网", "数字经济", "战略新兴",
    )
    CHINABOND_SECONDARY_TERMS = ("存款", "现金", "DR007")
    CHINABOND_TENOR_ALIASES = (
        ("under_1y", ("1年以下", "1年以内", "0-1年")),
        ("1_3y", ("1-3年", "1至3年")),
        ("0_3y", ("0-3年", "0至3年")),
        ("0_5y", ("0-5年", "0至5年")),
        ("3_5y", ("3-5年", "3至5年")),
        ("1_5y", ("1-5年", "1至5年")),
        ("3_7y", ("3-7年", "3至7年")),
        ("5_10y", ("5-10年", "5至10年")),
        ("7_10y", ("7-10年", "7至10年")),
        ("over_10y", ("10年以上", "10年及以上")),
    )
    FUND_CODE_PATTERN = re.compile(r"^[0-9]{6}\.(OF|SH|SZ|BJ)$", re.IGNORECASE)

    INDEX_RULES = tuple(FundClassificationCatalog.TRACKED_INDEX_RULES)
    QDII_INDEX_RULES = tuple(FundClassificationCatalog.QDII_INDEX_RULES)
    ENHANCED_INDEX_RULES = tuple(FundClassificationCatalog.ENHANCED_INDEX_RULES)
    ACTIVE_EQUITY_RULES = tuple(FundClassificationCatalog.ACTIVE_EQUITY_REFERENCE_RULES)
    ACTIVE_EQUITY_SECTOR_RULES = tuple(FundClassificationCatalog.ACTIVE_EQUITY_SECTOR_RULES)
    ACTIVE_FIXED_INCOME_RULES = tuple(FundClassificationCatalog.ACTIVE_FIXED_INCOME_REFERENCE_RULES)

    def __init__(self, repository: Optional[Any] = None):
        self._repository = repository

    def build_plan(self, funds: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
        grouped: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        skipped: List[Dict[str, Any]] = []
        seen_codes = set()

        for fund in funds:
            wind_code = self._text(fund.get("wind_code") or fund.get("ts_code")).upper()
            if not wind_code or wind_code in seen_codes:
                skipped.append({"wind_code": wind_code or None, "reason": "invalid_or_duplicate_code"})
                continue
            seen_codes.add(wind_code)
            if not self.FUND_CODE_PATTERN.fullmatch(wind_code):
                skipped.append({"wind_code": wind_code, "reason": "invalid_fund_code_format"})
                continue
            candidate, reason = self._candidate(fund, wind_code)
            if candidate is None:
                skipped.append({"wind_code": wind_code, "reason": reason})
                continue

            key = (
                candidate["strategy_family_key"],
                candidate["normalized_name"],
                candidate["benchmark_code"],
            )
            group = grouped.setdefault(key, {
                "strategy_family_key": candidate["strategy_family_key"],
                "asset_class": candidate["asset_class"],
                "active_passive": candidate["active_passive"],
                "peer_group_key": candidate["peer_group_key"],
                "peer_group_benchmark_code": candidate.get("peer_group_benchmark_code") or candidate["benchmark_code"],
                "peer_group_benchmark_name": candidate.get("peer_group_benchmark_name") or candidate["benchmark_name"],
                "benchmark_code": candidate["benchmark_code"],
                "benchmark_name": candidate["benchmark_name"],
                "benchmark_type": candidate["benchmark_type"],
                "mapping_method": candidate["mapping_method"],
                "classification_confidence": candidate["classification_confidence"],
                "benchmark_confidence": candidate["benchmark_confidence"],
                "benchmark_weight": candidate.get("benchmark_weight"),
                "contract_dimensions": candidate.get("contract_dimensions"),
                "contract_components": candidate.get("contract_components"),
                "rationale": candidate["rationale"],
                "automatic_rule_scope": candidate["automatic_rule_scope"],
                "normalized_name": candidate["normalized_name"],
                "shares": [],
            })
            group["shares"].append(candidate["share"])

        groups = [self._finalize_group(group) for group in grouped.values()]
        groups.sort(key=lambda group: (group["strategy_family_key"], group["canonical_code"]))
        skipped_by_reason: Dict[str, int] = {}
        for item in skipped:
            reason = str(item.get("reason") or "unknown")
            skipped_by_reason[reason] = skipped_by_reason.get(reason, 0) + 1
        eligible_by_family: Dict[str, int] = {}
        eligible_by_benchmark: Dict[str, int] = {}
        eligible_by_peer_group: Dict[str, int] = {}
        for group in groups:
            family = str(group.get("strategy_family_key") or "unknown")
            benchmark = str(group.get("benchmark_code") or "unknown")
            peer_group = str(group.get("peer_group_key") or "unknown")
            share_count = len(group.get("shares") or [])
            eligible_by_family[family] = eligible_by_family.get(family, 0) + share_count
            eligible_by_benchmark[benchmark] = eligible_by_benchmark.get(benchmark, 0) + share_count
            eligible_by_peer_group[peer_group] = eligible_by_peer_group.get(peer_group, 0) + share_count
        return {
            "groups": groups,
            "skipped": skipped,
            "summary": {
                "input_funds": len(seen_codes),
                "eligible_funds": sum(len(group["shares"]) for group in groups),
                "entity_groups": len(groups),
                "skipped_funds": len(skipped),
                "skipped_by_reason": skipped_by_reason,
                "eligible_by_family": eligible_by_family,
                "eligible_by_benchmark": eligible_by_benchmark,
                "eligible_by_peer_group": eligible_by_peer_group,
            },
        }

    def apply_plan(self, plan: Dict[str, Any], reconcile: bool = False) -> Dict[str, Any]:
        repository = self._get_repository()
        catalog_result = repository.ensure_catalog(
            FundClassificationCatalog.STRATEGY_FAMILIES,
            FundClassificationCatalog.peer_groups(),
            source=FundClassificationCatalog.VERSION,
        )
        result = repository.apply_ingestion_plan(
            plan.get("groups") or [],
            source=self.SOURCE,
            reconcile=reconcile,
        )
        return {**plan.get("summary", {}), **catalog_result, **result}

    def _candidate(self, fund: Dict[str, Any], wind_code: str) -> Tuple[Optional[Dict[str, Any]], str]:
        name = self._display_text(fund.get("name") or fund.get("fund_name"))
        if not name:
            return None, "missing_name"
        if any(term in name for term in self.TERMINATED_TERMS):
            return None, "inactive_or_terminated"

        fund_type = self._text(fund.get("type") or fund.get("fund_type")).lower()
        is_qdii = self._is_qdii_fund_type(fund_type)
        normalized_name, share_class, currency = self._share_identity(name, is_qdii=is_qdii)
        declared_benchmark = self._declared_benchmark(fund)
        invest_type = self._raw_classification_value(fund, "invest_type")
        contract_type = self._raw_classification_value(fund, "contract_type")

        if is_qdii:
            classification, reason = self._qdii_candidate(
                declared_benchmark,
                invest_type,
                contract_type,
            )
        elif self._is_fof(name, invest_type, contract_type):
            classification, reason = self._fof_candidate(
                declared_benchmark,
                invest_type,
                contract_type,
            )
        elif "货币" in fund_type or fund_type == "money":
            classification, reason = self._money_market_candidate()
        elif "指数" in fund_type or fund_type == "index":
            classification, reason = self._passive_index_candidate(
                name,
                declared_benchmark,
                invest_type,
                contract_type,
            )
        elif fund_type in {"混合型", "hybrid"} or contract_type == "混合型":
            classification, reason = self._mixed_allocation_candidate(
                declared_benchmark,
                invest_type,
                contract_type,
            )
        elif fund_type in {"股票型", "stock"}:
            classification, reason = self._active_equity_candidate(
                name,
                declared_benchmark,
                invest_type,
                contract_type,
            )
        elif fund_type in {"债券型", "bond"}:
            classification, reason = self._active_fixed_income_candidate(
                name,
                declared_benchmark,
                invest_type,
                contract_type,
            )
        else:
            return None, "unsupported_fund_type"
        if classification is None:
            return None, reason

        established_at = self._date_text(fund.get("establishment_date") or fund.get("found_date"))
        return {
            **classification,
            "normalized_name": normalized_name,
            "share": {
                "wind_code": wind_code,
                "fund_id": self._text(fund.get("id")) or None,
                "name": name,
                "share_class": share_class,
                "currency": currency,
                "established_at": established_at,
                "declared_benchmark": declared_benchmark or None,
                "fund_type": fund.get("type") or fund.get("fund_type"),
                "invest_type": invest_type or None,
                "contract_type": contract_type or None,
                "source_updated_at": self._date_text(fund.get("nav_date")) or date.today().isoformat(),
            },
        }, "eligible"

    @staticmethod
    def _is_fof(name: str, invest_type: str, contract_type: str) -> bool:
        evidence = f"{name} {invest_type} {contract_type}".lower()
        return "fof" in evidence or "基金中基金" in evidence

    @staticmethod
    def _is_qdii_fund_type(fund_type: str) -> bool:
        return "qdii" in str(fund_type or "").lower()

    def _qdii_candidate(
        self,
        declared_benchmark: str,
        invest_type: str,
        contract_type: str,
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        if not declared_benchmark:
            return None, "qdii_missing_declared_benchmark"
        if invest_type == "被动指数型":
            return self._qdii_index_candidate(declared_benchmark, contract_type)
        if invest_type == "增强指数型":
            return None, "qdii_index_not_supported"

        if invest_type == "股票型" and contract_type == "股票型":
            family_key = "qdii_equity"
            peer_group_key = "peer-qdii-equity"
            peer_group_benchmark_code = "QDII-ACTIVE-EQUITY"
            peer_group_benchmark_name = "QDII 主动权益同类组"
        elif invest_type == "债券型" and contract_type == "债券型":
            family_key = "qdii_bond"
            peer_group_key = "peer-qdii-bond"
            peer_group_benchmark_code = "QDII-ACTIVE-BOND"
            peer_group_benchmark_name = "QDII 债券同类组"
        elif invest_type in {"混合型", "灵活配置型"} and contract_type == "混合型":
            family_key = "qdii_multi_asset"
            peer_group_key = "peer-qdii-multi-asset"
            peer_group_benchmark_code = "QDII-ACTIVE-MULTI-ASSET"
            peer_group_benchmark_name = "QDII 多资产同类组"
        else:
            return None, "qdii_unsupported_or_conflicting_asset_class"

        return {
            "strategy_family_key": family_key,
            "asset_class": "global",
            "active_passive": "active",
            "peer_group_key": peer_group_key,
            "peer_group_benchmark_code": peer_group_benchmark_code,
            "peer_group_benchmark_name": peer_group_benchmark_name,
            "benchmark_code": self._contract_benchmark_code(declared_benchmark),
            "benchmark_name": declared_benchmark,
            "benchmark_type": "declared_contract_benchmark",
            "mapping_method": "legal_qdii_type_and_declared_asset_class",
            "classification_confidence": 0.98,
            "benchmark_confidence": 0.96,
            "benchmark_weight": None,
            "automatic_rule_scope": "qdii_explicit_asset_class",
            "rationale": (
                f"法定类型为 QDII，投资类型为{invest_type}，合同类型为{contract_type}；"
                "按资产类别进入 QDII 同类组，同时保留基金自身合同业绩比较基准。"
            ),
        }, "eligible"

    def _qdii_index_candidate(
        self,
        declared_benchmark: str,
        contract_type: str,
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        if contract_type != "股票型":
            return None, "qdii_index_contract_type_conflict"

        matched_rules = [
            rule
            for rule in self.QDII_INDEX_RULES
            if any(alias in declared_benchmark for alias in rule.get("aliases") or [])
        ]
        if len(matched_rules) != 1:
            return None, "qdii_index_not_supported"
        rule = matched_rules[0]

        normalized_benchmark = re.sub(r"\s+", "", unicodedata.normalize("NFKC", declared_benchmark))
        matches = self._weighted_rule_matches([rule], normalized_benchmark)
        weights = {
            float(match["weight"])
            for match in matches
            if match.get("rule", {}).get("benchmark_code") == rule["benchmark_code"]
        }
        operator = r"(?:\*|×|x|X)"
        for alias in rule.get("aliases") or []:
            patterns = (
                re.compile(
                    re.escape(alias)
                    + r"(?:收益率)?(?:\([^)]*(?:汇率|人民币)[^)]*\))?"
                    + operator
                    + r"(\d+(?:\.\d+)?)%",
                    re.IGNORECASE,
                ),
                re.compile(
                    r"(\d+(?:\.\d+)?)%"
                    + operator
                    + re.escape(alias)
                    + r"(?:收益率)?(?:\([^)]*(?:汇率|人民币)[^)]*\))?",
                    re.IGNORECASE,
                ),
            )
            for pattern in patterns:
                weights.update(float(item.group(1)) for item in pattern.finditer(normalized_benchmark))
        if weights != {float(rule["required_weight"])}:
            return None, "qdii_index_reference_not_100_percent"

        if not any(term in normalized_benchmark for term in rule.get("currency_basis_terms") or []):
            return None, "qdii_index_currency_basis_unverified"

        return {
            "strategy_family_key": rule["strategy_family_key"],
            "asset_class": rule["asset_class"],
            "active_passive": "passive",
            "peer_group_key": rule["peer_group_key"],
            "peer_group_benchmark_code": rule["benchmark_code"],
            "peer_group_benchmark_name": rule["benchmark_name"],
            "benchmark_code": rule["benchmark_code"],
            "benchmark_name": rule["benchmark_name"],
            "benchmark_type": "derived_global_index_cny",
            "mapping_method": "declared_qdii_index_alias_weight_and_currency_basis",
            "classification_confidence": 0.99,
            "benchmark_confidence": 0.98,
            "benchmark_weight": float(rule["required_weight"]),
            "automatic_rule_scope": "qdii_passive_ndx_100_percent_explicit_cny_basis",
            "rationale": (
                "投资类型为被动指数型、合同类型为股票型；"
                "合同基准明确为纳斯达克100指数100%，并声明汇率调整或人民币计价口径。"
            ),
        }, "eligible"

    @staticmethod
    def _contract_benchmark_code(declared_benchmark: str) -> str:
        normalized = re.sub(r"\s+", "", unicodedata.normalize("NFKC", declared_benchmark))
        digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16].upper()
        return f"CONTRACT-QDII-{digest}"

    def _money_market_candidate(self) -> Tuple[Dict[str, Any], str]:
        return {
            "strategy_family_key": "cash_management",
            "asset_class": "money_market",
            "active_passive": "active",
            "peer_group_key": "peer-money-cash-management",
            "benchmark_code": "DR007",
            "benchmark_name": "DR007",
            "benchmark_type": "money_market_rate",
            "mapping_method": "legal_type_cash_rate_policy",
            "classification_confidence": 0.97,
            "benchmark_confidence": 0.86,
            "benchmark_weight": None,
            "automatic_rule_scope": "legal_money_market",
            "rationale": "基金法定类型明确为货币基金；DR007 仅作为资金利率参照，不生成净值跟踪误差。",
        }, "eligible"

    def _fof_candidate(
        self,
        declared_benchmark: str,
        invest_type: str,
        contract_type: str,
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        if contract_type and contract_type not in {"混合型", "基金中基金", "FOF"}:
            return None, "fof_contract_type_conflict"
        if invest_type and invest_type not in {"混合型", "基金中基金", "FOF", "养老目标基金"}:
            return None, "fof_investment_type_conflict"
        if not declared_benchmark:
            return None, "fof_missing_declared_benchmark"

        components = self._weighted_benchmark_components(declared_benchmark)
        if not components:
            return None, "fof_benchmark_weights_unavailable"
        total_weight = sum(weight for _, weight in components)
        if not 95 <= total_weight <= 105:
            return None, "fof_benchmark_weights_incomplete"

        equity_weight = 0.0
        for component, weight in components:
            if any(term.lower() in component.lower() for term in self.MIXED_DEFENSIVE_BENCHMARK_TERMS):
                continue
            if any(term.lower() in component.lower() for term in self.MIXED_EQUITY_BENCHMARK_TERMS):
                equity_weight += weight
                continue
            return None, "fof_benchmark_asset_class_ambiguous"

        if equity_weight >= 60:
            family_key = "fof_equity_allocation"
            peer_group_key = "peer-fof-equity-allocation"
            benchmark_code = "FOF-EQUITY-60"
            benchmark_name = "FOF 合同基准权益权重≥60%"
        elif equity_weight <= 30:
            family_key = "fof_bond_allocation"
            peer_group_key = "peer-fof-bond-allocation"
            benchmark_code = "FOF-BOND-30"
            benchmark_name = "FOF 合同基准权益权重≤30%"
        else:
            family_key = "fof_balanced_allocation"
            peer_group_key = "peer-fof-balanced-allocation"
            benchmark_code = "FOF-BALANCED-30-60"
            benchmark_name = "FOF 合同基准权益权重>30%且<60%"
        return {
            "strategy_family_key": family_key,
            "asset_class": "fof",
            "active_passive": "active",
            "peer_group_key": peer_group_key,
            "benchmark_code": benchmark_code,
            "benchmark_name": benchmark_name,
            "benchmark_type": "declared_fof_allocation_bucket",
            "mapping_method": "declared_fof_benchmark_asset_weight_bucket",
            "classification_confidence": 0.97,
            "benchmark_confidence": 0.96,
            "benchmark_weight": round(equity_weight, 4),
            "automatic_rule_scope": "fof_explicit_contract_allocation",
            "rationale": (
                f"产品名称或类型明确为 FOF；合同基准权重合计{total_weight:g}%，"
                f"其中权益类权重{equity_weight:g}%，进入独立 FOF 配置同类组。"
            ),
        }, "eligible"

    def _passive_index_candidate(
        self,
        name: str,
        declared_benchmark: str,
        invest_type: str,
        contract_type: str,
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        combined = f"{name} {declared_benchmark} {invest_type}"
        if any(term in combined for term in self.ENHANCED_INDEX_TERMS):
            return self._enhanced_index_candidate(
                declared_benchmark,
                invest_type,
                contract_type,
            )
        if invest_type and invest_type != "被动指数型":
            return None, "unsupported_index_investment_type"
        matched = [rule for rule in self.INDEX_RULES if self._matches_index_rule(rule, declared_benchmark)]
        if len(matched) != 1:
            return None, "unsupported_or_ambiguous_index_benchmark"
        rule = matched[0]
        required_contract_term = rule.get("required_contract_term")
        if required_contract_term and required_contract_term not in contract_type:
            return None, "index_contract_type_conflict"
        if rule["asset_class"] == "index" and "债券" in contract_type:
            return None, "index_contract_type_conflict"
        return {
            "strategy_family_key": rule["strategy_family_key"],
            "asset_class": rule["asset_class"],
            "active_passive": "passive",
            "peer_group_key": rule["peer_group_key"],
            "benchmark_code": rule["benchmark_code"],
            "benchmark_name": rule["benchmark_name"],
            "benchmark_type": "tracked_index",
            "mapping_method": "declared_benchmark_exact_alias",
            "classification_confidence": 0.99,
            "benchmark_confidence": 0.99,
            "benchmark_weight": None,
            "automatic_rule_scope": "exact_supported_passive_index",
            "rationale": f"投资类型为被动指数型，合同业绩比较基准明确引用{rule['benchmark_name']}指数。",
        }, "eligible"

    def _enhanced_index_candidate(
        self,
        declared_benchmark: str,
        invest_type: str,
        contract_type: str,
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        if invest_type != "增强指数型":
            return None, "unsupported_index_enhanced_investment_type"
        if contract_type != "股票型":
            return None, "index_enhanced_contract_type_conflict"
        if not declared_benchmark:
            return None, "missing_declared_benchmark"

        matches = self._weighted_rule_matches(self.ENHANCED_INDEX_RULES, declared_benchmark)
        unique_matches: Dict[str, Dict[str, Any]] = {}
        for match in matches:
            key = str(match["rule"]["benchmark_code"])
            existing = unique_matches.get(key)
            if existing is None or float(match["weight"]) > float(existing["weight"]):
                unique_matches[key] = match
        if len(unique_matches) != 1:
            return None, "unsupported_or_ambiguous_index_enhanced_benchmark"

        match = next(iter(unique_matches.values()))
        if match["weight"] < 90 or match["weight"] > 100:
            return None, "index_enhanced_reference_weight_out_of_range"
        if self._has_unsupported_equity_secondary(declared_benchmark, match["alias"]):
            return None, "unsupported_index_enhanced_secondary_reference"

        rule = match["rule"]
        return {
            "strategy_family_key": "index_enhanced",
            "asset_class": "index",
            "active_passive": "active",
            "peer_group_key": rule["peer_group_key"],
            "benchmark_code": rule["benchmark_code"],
            "benchmark_name": rule["benchmark_name"],
            "benchmark_type": "enhanced_index_primary_reference",
            "mapping_method": "declared_benchmark_enhanced_index_alias_and_weight",
            "classification_confidence": 0.99,
            "benchmark_confidence": 0.99,
            "benchmark_weight": match["weight"],
            "automatic_rule_scope": "enhanced_index_supported_primary_reference",
            "rationale": (
                f"投资类型为增强指数型、合同类型为股票型；合同基准以{rule['benchmark_name']}"
                f"为唯一支持指数参考（权重{match['weight']:g}%），与同指数被动产品分池评价。"
            ),
        }, "eligible"

    def _active_equity_candidate(
        self,
        name: str,
        declared_benchmark: str,
        invest_type: str,
        contract_type: str,
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        if invest_type not in {"股票型", "普通股票型"}:
            return None, "unsupported_active_equity_investment_type"
        if contract_type != "股票型":
            return None, "active_equity_contract_type_conflict"
        if not declared_benchmark:
            return None, "missing_declared_benchmark"
        cross_market_candidate = self._active_equity_cross_market_candidate(declared_benchmark)
        if cross_market_candidate is not None:
            return cross_market_candidate, "eligible"
        sector_candidate = self._active_equity_sector_candidate(declared_benchmark)
        if sector_candidate is not None:
            return sector_candidate, "eligible"
        lower_name = name.lower()
        if any(term in lower_name for term in self.ACTIVE_EQUITY_NAME_EXCLUSIONS):
            return None, "unsupported_active_equity_sector_or_index_style"

        matched = self._weighted_rule_matches(self.ACTIVE_EQUITY_RULES, declared_benchmark)
        if len(matched) != 1:
            return None, "unsupported_or_ambiguous_active_equity_benchmark"
        match = matched[0]
        if match["weight"] < 80:
            return None, "active_equity_reference_weight_below_80"
        if self._has_unsupported_equity_secondary(declared_benchmark, match["alias"]):
            return None, "unsupported_active_equity_secondary_reference"

        rule = match["rule"]
        return {
            "strategy_family_key": "active_equity_core",
            "asset_class": "equity",
            "active_passive": "active",
            "peer_group_key": rule["peer_group_key"],
            "benchmark_code": rule["benchmark_code"],
            "benchmark_name": rule["benchmark_name"],
            "benchmark_type": "composite_primary_equity_reference",
            "mapping_method": "declared_benchmark_primary_equity_alias_and_weight",
            "classification_confidence": 0.96,
            "benchmark_confidence": 0.96,
            "benchmark_weight": match["weight"],
            "automatic_rule_scope": "active_stock_single_broad_equity_reference",
            "rationale": (
                f"基金法定、投资与合同类型均为股票型；合同组合基准以{rule['benchmark_name']}"
                f"为主权益参考（权重{match['weight']:g}%）。基准代码仅表示主权益参考，不代表完整复合基准。"
            ),
        }, "eligible"

    def _active_equity_cross_market_candidate(
        self,
        declared_benchmark: str,
    ) -> Optional[Dict[str, Any]]:
        weighted_components = self._weighted_benchmark_components(declared_benchmark)
        if not weighted_components:
            return None

        components = []
        mainland_weight = 0.0
        hong_kong_weight = 0.0
        defensive_weight = 0.0
        for component_name, weight in weighted_components:
            component = self._cross_market_component(component_name, weight)
            if component is None:
                return None
            components.append(component)
            if component["asset"] == "mainland_equity":
                mainland_weight += weight
            elif component["asset"] == "hong_kong_equity":
                hong_kong_weight += weight
            else:
                defensive_weight += weight

        total_weight = sum(float(item["weight"]) for item in components)
        equity_weight = mainland_weight + hong_kong_weight
        if not 99.999 <= total_weight <= 100.001:
            return None
        if mainland_weight < 20 or hong_kong_weight < 20:
            return None
        if equity_weight < 80 or defensive_weight > 20:
            return None

        return {
            "strategy_family_key": "active_equity_cross_market",
            "asset_class": "equity",
            "active_passive": "active",
            "peer_group_key": "peer-active-equity-cross-market-cn-hk",
            "benchmark_code": "CONTRACT-CN-HK-EQUITY",
            "benchmark_name": "合同沪港深复合基准",
            "benchmark_type": "contract_composite_benchmark",
            "mapping_method": "declared_benchmark_verified_component_weights",
            "classification_confidence": 0.99,
            "benchmark_confidence": 0.99,
            "benchmark_weight": round(equity_weight, 4),
            "contract_components": components,
            "automatic_rule_scope": "active_stock_mainland_hong_kong_contract_composite",
            "rationale": (
                f"基金法定、投资与合同类型均为股票型；合同基准中A股权益权重{mainland_weight:g}%、"
                f"港股权益权重{hong_kong_weight:g}%、防御资产权重{defensive_weight:g}%。"
                "按合同权重使用真实成分行情构建日频复合基准。"
            ),
        }

    def _cross_market_component(self, name: str, weight: float) -> Optional[Dict[str, Any]]:
        normalized_name = self._display_text(name).replace("收益率", "").replace("涨跌幅", "")
        for rule in self.ACTIVE_EQUITY_RULES:
            if any(alias in normalized_name for alias in rule.get("aliases") or []):
                return {
                    "code": rule["benchmark_code"],
                    "name": rule["benchmark_name"],
                    "weight": float(weight),
                    "asset": "mainland_equity",
                }
        if "恒生指数" in normalized_name and "恒生中国企业" not in normalized_name:
            return {
                "code": "HSI",
                "name": "恒生指数",
                "weight": float(weight),
                "asset": "hong_kong_equity",
            }
        if "中证全债指数" in normalized_name:
            return {
                "code": "H11001.CSI",
                "name": "中证全债",
                "weight": float(weight),
                "asset": "fixed_income",
            }
        return None

    def _active_equity_sector_candidate(self, declared_benchmark: str) -> Optional[Dict[str, Any]]:
        matches = self._weighted_rule_matches(self.ACTIVE_EQUITY_SECTOR_RULES, declared_benchmark)
        weights: Dict[str, float] = {}
        rules: Dict[str, Dict[str, Any]] = {}
        for match in matches:
            key = match["rule"]["peer_group_key"]
            weights[key] = weights.get(key, 0.0) + float(match["weight"])
            rules[key] = match["rule"]
        candidates = [key for key, weight in weights.items() if weight >= 70]
        if len(candidates) != 1:
            return None
        key = candidates[0]
        rule = rules[key]
        return {
            "strategy_family_key": "active_equity_sector",
            "asset_class": "equity",
            "active_passive": "active",
            "peer_group_key": rule["peer_group_key"],
            "benchmark_code": rule["benchmark_code"],
            "benchmark_name": rule["benchmark_name"],
            "benchmark_type": "declared_sector_bucket",
            "mapping_method": "declared_benchmark_sector_alias_and_weight",
            "classification_confidence": 0.96,
            "benchmark_confidence": 0.96,
            "benchmark_weight": round(weights[key], 4),
            "automatic_rule_scope": "active_stock_explicit_sector_reference",
            "rationale": f"合同基准中{rule['benchmark_name']}行业指数权重合计{weights[key]:g}%，达到行业主题分类门槛。",
        }

    def _active_fixed_income_candidate(
        self,
        name: str,
        declared_benchmark: str,
        invest_type: str,
        contract_type: str,
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        if invest_type not in {"债券型", "强化收益型", "稳健增长型"}:
            return None, "unsupported_fixed_income_investment_type"
        if contract_type != "债券型":
            return None, "fixed_income_contract_type_conflict"
        if not declared_benchmark:
            return None, "missing_declared_benchmark"
        if any(term in name for term in ("可转债", "转债")):
            return None, "unsupported_fixed_income_style"

        components = re.findall(r"([^+＋]+?)[×xX*]\s*(\d+(?:\.\d+)?)\s*%", declared_benchmark)
        if components:
            total_weight = sum(float(weight) for _, weight in components)
            if 95 <= total_weight <= 105:
                equity_weight = 0.0
                defensive_weight = 0.0
                ambiguous = False
                for component, raw_weight in components:
                    weight = float(raw_weight)
                    if any(term.lower() in component.lower() for term in self.MIXED_DEFENSIVE_BENCHMARK_TERMS):
                        defensive_weight += weight
                    elif any(term.lower() in component.lower() for term in self.MIXED_EQUITY_BENCHMARK_TERMS):
                        equity_weight += weight
                    else:
                        ambiguous = True
                if not ambiguous and equity_weight > 0:
                    if equity_weight > 20 or defensive_weight < 80:
                        return None, "fixed_income_equity_weight_out_of_range"
                    return {
                        "strategy_family_key": "fixed_income_equity_allocation",
                        "asset_class": "fixed_income",
                        "active_passive": "active",
                        "peer_group_key": "peer-fixed-income-equity-allocation",
                        "benchmark_code": "FIXED-INCOME-EQUITY-20",
                        "benchmark_name": "合同基准权益权重>0%且≤20%",
                        "benchmark_type": "declared_allocation_bucket",
                        "mapping_method": "declared_benchmark_bond_equity_weight_bucket",
                        "classification_confidence": 0.96,
                        "benchmark_confidence": 0.96,
                        "benchmark_weight": round(equity_weight, 4),
                        "automatic_rule_scope": "bond_fund_explicit_equity_allocation",
                        "rationale": f"合同类型为债券型；基准权重合计{total_weight:g}%，其中债券/现金{defensive_weight:g}%、权益{equity_weight:g}%。",
                    }, "eligible"

        if any(term in name for term in self.ACTIVE_FIXED_INCOME_NAME_EXCLUSIONS):
            return None, "unsupported_fixed_income_style"

        chinabond_candidate, chinabond_reason = self._chinabond_contract_candidate(declared_benchmark)
        if chinabond_candidate is not None:
            return chinabond_candidate, "eligible"
        if chinabond_reason:
            return None, chinabond_reason

        matched = self._weighted_rule_matches(self.ACTIVE_FIXED_INCOME_RULES, declared_benchmark)
        if len(matched) != 1:
            return None, "unsupported_or_ambiguous_fixed_income_benchmark"
        match = matched[0]
        if match["weight"] != 100 or "+" in unicodedata.normalize("NFKC", declared_benchmark):
            return None, "fixed_income_reference_not_100_percent"

        rule = match["rule"]
        return {
            "strategy_family_key": "fixed_income_general",
            "asset_class": "fixed_income",
            "active_passive": "active",
            "peer_group_key": rule["peer_group_key"],
            "benchmark_code": rule["benchmark_code"],
            "benchmark_name": rule["benchmark_name"],
            "benchmark_type": rule.get("benchmark_type") or "declared_bond_index",
            "mapping_method": "declared_benchmark_exact_bond_alias_and_weight",
            "classification_confidence": 0.98,
            "benchmark_confidence": 0.99,
            "benchmark_weight": match["weight"],
            "automatic_rule_scope": "active_bond_exact_supported_100_percent_reference",
            "rationale": (
                f"基金法定、投资与合同类型均为债券型；合同业绩比较基准为"
                f"{rule['benchmark_name']}100%，且未混入权益或转债基准。"
                + (
                    "基准代码为本系统合同基准分类桶，不冒充官方行情代码。"
                    if rule.get("benchmark_type") == "contract_benchmark_bucket"
                    else ""
                )
            ),
        }, "eligible"

    def _chinabond_contract_candidate(
        self,
        declared_benchmark: str,
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        components = self._weighted_benchmark_components(declared_benchmark)
        if not components:
            return None, ""

        index_components = []
        unsupported_components = []
        for component_name, weight in components:
            dimensions = self._chinabond_contract_dimensions(component_name)
            if dimensions is not None:
                index_components.append((dimensions, weight))
            elif not any(term.lower() in component_name.lower() for term in self.CHINABOND_SECONDARY_TERMS):
                unsupported_components.append(component_name)

        if not index_components:
            return None, ""
        if len(index_components) != 1:
            return None, "chinabond_multiple_bond_indices"
        if unsupported_components:
            return None, "chinabond_unsupported_secondary_reference"

        dimensions, primary_weight = index_components[0]
        total_weight = sum(weight for _, weight in components)
        if not 99.999 <= total_weight <= 100.001:
            return None, "chinabond_contract_weights_incomplete"
        if primary_weight < 80 or primary_weight > 100:
            return None, "chinabond_primary_weight_out_of_range"

        rule = next((
            item for item in FundClassificationCatalog.CHINABOND_CONTRACT_REFERENCE_RULES
            if item.get("contract_dimensions") == dimensions
        ), None)
        if rule is None:
            return None, "unsupported_chinabond_contract_dimensions"

        return {
            "strategy_family_key": "fixed_income_general",
            "asset_class": "fixed_income",
            "active_passive": "active",
            "peer_group_key": rule["peer_group_key"],
            "benchmark_code": rule["benchmark_code"],
            "benchmark_name": rule["benchmark_name"],
            "benchmark_type": "contract_benchmark_bucket",
            "mapping_method": "declared_chinabond_base_price_tenor_and_weight",
            "classification_confidence": 0.98,
            "benchmark_confidence": 0.99,
            "benchmark_weight": primary_weight,
            "automatic_rule_scope": "active_bond_strict_chinabond_contract_dimensions",
            "contract_dimensions": dimensions,
            "rationale": (
                f"合同基准只包含一个受支持的中债主指数（权重{primary_weight:g}%），"
                f"其余成分仅为存款、现金或DR007；按基础指数、价格口径、期限三维进入"
                f"“{rule['benchmark_name']}”同类组。该代码是合同基准分类桶，不冒充官方行情代码。"
            ),
        }, "eligible"

    @classmethod
    def _chinabond_contract_dimensions(cls, component_name: str) -> Optional[Dict[str, str]]:
        text = unicodedata.normalize("NFKC", str(component_name or ""))
        text = text.translate(str.maketrans({char: "-" for char in "‐‑‒–—―−"}))
        text = re.sub(r"\s+", "", text)
        text = text.replace("收益率", "").replace("涨跌幅", "")
        tenor_aliases = [
            alias
            for _, aliases in cls.CHINABOND_TENOR_ALIASES
            for alias in aliases
        ]
        tenor_pattern = "|".join(
            re.escape(alias)
            for alias in sorted(tenor_aliases, key=len, reverse=True)
        )
        matched = re.match(
            rf"^(?:中债|中国债券)-?(?:({tenor_pattern})(?:债券)?-?)?(新综合|综合|总)(?:指数)?",
            text,
        )
        if not matched:
            return None

        base_index = {
            "综合": "composite",
            "新综合": "new_composite",
            "总": "total",
        }[matched.group(2)]
        remainder = text[matched.end():]

        tenor_matches = []
        prefix_tenor = matched.group(1)
        if prefix_tenor:
            tenor_matches.extend(
                (tenor_key, prefix_tenor)
                for tenor_key, aliases in cls.CHINABOND_TENOR_ALIASES
                if prefix_tenor in aliases
            )
        for tenor_key, aliases in cls.CHINABOND_TENOR_ALIASES:
            for alias in aliases:
                if alias in remainder:
                    tenor_matches.append((tenor_key, alias))
        tenor_keys = {item[0] for item in tenor_matches}
        if len(tenor_keys) > 1:
            return None
        tenor = next(iter(tenor_keys), "all")
        for _, alias in tenor_matches:
            remainder = remainder.replace(alias, "")

        if "总财富" in remainder:
            price_return = "total_wealth"
            remainder = remainder.replace("总财富", "")
        elif "全价" in remainder:
            price_return = "full_price"
            remainder = remainder.replace("全价", "")
        elif "财富" in remainder:
            price_return = "wealth"
            remainder = remainder.replace("财富", "")
        else:
            price_return = "unspecified"

        for token in ("总值", "指数", "(", ")", "[", "]", "-", "_"):
            remainder = remainder.replace(token, "")
        if remainder:
            return None
        return {
            "base_index": base_index,
            "price_return": price_return,
            "tenor": tenor,
        }

    @staticmethod
    def _weighted_benchmark_components(benchmark: str) -> List[Tuple[str, float]]:
        normalized = unicodedata.normalize("NFKC", str(benchmark or ""))
        normalized = normalized.translate(str.maketrans({char: "-" for char in "‐‑‒–—―−"}))
        components = []
        for raw_component in re.split(r"\s*\+\s*", normalized):
            component = raw_component.strip()
            after = re.fullmatch(
                r"(.+?)[×xX*]\s*(\d+(?:\.\d+)?)\s*%",
                component,
                re.IGNORECASE,
            )
            before = re.fullmatch(
                r"(\d+(?:\.\d+)?)\s*%\s*[×xX*](.+)",
                component,
                re.IGNORECASE,
            )
            if after:
                components.append((after.group(1).strip(), float(after.group(2))))
            elif before:
                components.append((before.group(2).strip(), float(before.group(1))))
            else:
                return []
        return components

    @classmethod
    def resolve_contract_benchmark_components(cls, benchmark: str) -> List[Dict[str, Any]]:
        """把合同基准解析为可请求真实行情的完整成分；任一成分不支持则返回空。"""
        weighted_components = cls._weighted_benchmark_components(benchmark)
        if len(weighted_components) < 2:
            return []
        if abs(sum(weight for _, weight in weighted_components) - 100.0) > 0.001:
            return []

        resolved: List[Dict[str, Any]] = []
        rules = (
            list(FundClassificationCatalog.TRACKED_INDEX_RULES)
            + list(FundClassificationCatalog.ACTIVE_FIXED_INCOME_REFERENCE_RULES)
        )
        for raw_name, weight in weighted_components:
            name = cls._display_text(raw_name)
            normalized_name = re.sub(r"(?:收益率|涨跌幅)$", "", name).strip()
            matched_rule = next(
                (
                    rule
                    for rule in rules
                    if any(alias in normalized_name for alias in rule.get("aliases") or [])
                ),
                None,
            )
            if matched_rule is not None:
                code = str(matched_rule["benchmark_code"])
                resolved.append({
                    "code": code,
                    "name": matched_rule["benchmark_name"],
                    "weight": float(weight),
                    "asset": "fixed_income" if code in {"H11001.CSI", "H11009.CSI", "000012.SH"} else "equity",
                })
                continue
            if "恒生指数" in normalized_name and "恒生中国企业" not in normalized_name:
                resolved.append({
                    "code": "HSI",
                    "name": "恒生指数",
                    "weight": float(weight),
                    "asset": "hong_kong_equity",
                })
                continue
            return []
        return resolved

    def _mixed_allocation_candidate(
        self,
        declared_benchmark: str,
        invest_type: str,
        contract_type: str,
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        if contract_type != "混合型":
            return None, "mixed_contract_type_conflict"
        if invest_type not in {"混合型", "灵活配置型", "稳健增长型", "股债配置型", ""}:
            return None, "unsupported_mixed_investment_type"
        if not declared_benchmark:
            return None, "missing_declared_benchmark"

        components = self._weighted_benchmark_components(declared_benchmark)
        if not components:
            return None, "mixed_benchmark_weights_unavailable"
        total_weight = sum(weight for _, weight in components)
        if total_weight < 95 or total_weight > 105:
            return None, "mixed_benchmark_weights_incomplete"

        equity_weight = 0.0
        for component, weight in components:
            if any(term.lower() in component.lower() for term in self.MIXED_DEFENSIVE_BENCHMARK_TERMS):
                continue
            if any(term.lower() in component.lower() for term in self.MIXED_EQUITY_BENCHMARK_TERMS):
                equity_weight += weight
                continue
            return None, "mixed_benchmark_asset_class_ambiguous"

        if equity_weight >= 60:
            family_key = "mixed_equity_allocation"
            peer_group_key = "peer-mixed-equity-allocation"
            benchmark_code = "MIXED-EQUITY-60"
            benchmark_name = "合同基准权益权重≥60%"
        elif equity_weight <= 30:
            family_key = "mixed_bond_allocation"
            peer_group_key = "peer-mixed-bond-allocation"
            benchmark_code = "MIXED-BOND-30"
            benchmark_name = "合同基准权益权重≤30%"
        else:
            family_key = "mixed_balanced_allocation"
            peer_group_key = "peer-mixed-balanced-allocation"
            benchmark_code = "MIXED-BALANCED-30-60"
            benchmark_name = "合同基准权益权重>30%且<60%"
        contract_components = self.resolve_contract_benchmark_components(declared_benchmark)
        return {
            "strategy_family_key": family_key,
            "asset_class": "multi_asset",
            "active_passive": "active",
            "peer_group_key": peer_group_key,
            "benchmark_code": benchmark_code,
            "benchmark_name": benchmark_name,
            "benchmark_type": "declared_allocation_bucket",
            "mapping_method": "declared_benchmark_asset_weight_bucket",
            "classification_confidence": 0.96,
            "benchmark_confidence": 0.96,
            "benchmark_weight": round(equity_weight, 4),
            "contract_components": contract_components or None,
            "automatic_rule_scope": "mixed_fund_explicit_contract_allocation",
            "rationale": f"合同基准各资产权重合计{total_weight:g}%，其中权益类权重{equity_weight:g}%，据此进入配置同类组。",
        }, "eligible"

    def _finalize_group(self, group: Dict[str, Any]) -> Dict[str, Any]:
        shares = sorted(
            group["shares"],
            key=lambda share: (
                0 if str(share.get("wind_code") or "").upper().endswith(".OF") else 1,
                self.CURRENCY_PRIORITY.get(str(share.get("currency") or "").upper(), 9),
                self.PRIMARY_SHARE_PRIORITY.get(share.get("share_class"), 99),
                share.get("established_at") or "9999-12-31",
                share["wind_code"],
            ),
        )
        primary = shares[0]
        for share in shares:
            share["is_primary"] = share is primary
        established_dates = [share["established_at"] for share in shares if share.get("established_at")]
        stable_key = f"{group['strategy_family_key']}|{group['normalized_name']}|{group['benchmark_code']}"
        digest = hashlib.sha1(stable_key.encode("utf-8")).hexdigest()[:20]
        return {
            **group,
            "entity_id": f"entity-auto-{digest}",
            "canonical_code": primary["wind_code"],
            "canonical_name": group["normalized_name"],
            "established_at": min(established_dates) if established_dates else None,
            "source_updated_at": max(share["source_updated_at"] for share in shares),
            "shares": shares,
            "evidence_refs": {
                "source": "funds.raw_data.info/universe",
                "fundType": primary.get("fund_type"),
                "investType": primary.get("invest_type"),
                "contractType": primary.get("contract_type"),
                "declaredBenchmark": primary.get("declared_benchmark"),
                "shareCodes": [share["wind_code"] for share in shares],
                "catalogVersion": FundClassificationCatalog.VERSION,
                "primaryReferenceWeight": group.get("benchmark_weight"),
                "automaticRuleScope": group.get("automatic_rule_scope"),
                **(
                    {"contractBenchmarkDimensions": group["contract_dimensions"]}
                    if group.get("contract_dimensions")
                    else {}
                ),
                **(
                    {"benchmarkComponents": group["contract_components"]}
                    if group.get("contract_components")
                    else {}
                ),
            },
        }

    def _weighted_rule_matches(
        self,
        rules: Iterable[Dict[str, Any]],
        benchmark: str,
    ) -> List[Dict[str, Any]]:
        matches: List[Dict[str, Any]] = []
        normalized = unicodedata.normalize("NFKC", benchmark)
        operator = r"(?:\*|×|x|X)"
        suffix = r"(?:收益率|涨跌幅)?"
        for rule in rules:
            for alias in rule.get("aliases") or []:
                after = re.compile(
                    re.escape(alias) + suffix + r"\s*" + operator + r"\s*(\d+(?:\.\d+)?)\s*%",
                    re.IGNORECASE,
                )
                before = re.compile(
                    r"(\d+(?:\.\d+)?)\s*%\s*" + operator + r"\s*" + re.escape(alias) + suffix,
                    re.IGNORECASE,
                )
                for pattern in (after, before):
                    for item in pattern.finditer(normalized):
                        matches.append({
                            "rule": rule,
                            "alias": alias,
                            "weight": float(item.group(1)),
                        })
        return matches

    def _has_unsupported_equity_secondary(self, benchmark: str, primary_alias: str) -> bool:
        components = re.split(r"\s*\+\s*", unicodedata.normalize("NFKC", benchmark))
        for component in components:
            if primary_alias in component:
                continue
            if any(term in component for term in ("可转债", "可转换债券", "可交换债")):
                return True
            if any(term in component for term in self.ACTIVE_EQUITY_ALLOWED_SECONDARY_TERMS):
                continue
            return True
        return False

    def _matches_index_rule(self, rule: Dict[str, Any], benchmark: str) -> bool:
        if not benchmark or benchmark.count("指数") > 1:
            return False
        suffix = r"(?:收益率|涨跌幅)?(?=\s*(?:\*|×|x|X|\+|$))"
        return any(
            re.search(re.escape(alias) + suffix, benchmark, re.IGNORECASE)
            for alias in rule.get("aliases") or []
        )

    def _raw_classification_value(self, fund: Dict[str, Any], field: str) -> str:
        direct = self._display_text(fund.get(field))
        if direct:
            return direct
        raw_data = fund.get("raw_data") or {}
        if not isinstance(raw_data, dict):
            return ""
        for key in ("universe", "info"):
            section = raw_data.get(key) or {}
            if isinstance(section, dict):
                value = self._display_text(section.get(field))
                if value:
                    return value
        return ""

    def _share_identity(self, name: str, is_qdii: bool = False) -> Tuple[str, Optional[str], str]:
        compact = re.sub(r"\s+", "", unicodedata.normalize("NFKC", name)).strip()
        currency = "CNY"
        if is_qdii:
            currency_match = re.search(r"-(CNY|USD|HKD)(?:-(?:现汇|现钞))?$", compact, re.IGNORECASE)
            if currency_match:
                currency = currency_match.group(1).upper()
                compact = compact[:currency_match.start()].rstrip("-_ /")

        upper = compact.upper()
        if upper.endswith(("ETF", "LOF", "QDII")):
            return compact, None, currency
        match = re.search(r"-?([A-Z](?:[0-9])?)(?:类|份额)?$", upper)
        if match and match.group(1)[:1] in self.SHARE_CLASSES:
            return compact[:match.start()].rstrip("-_ /"), match.group(1), currency
        return compact, None, currency

    def _declared_benchmark(self, fund: Dict[str, Any]) -> str:
        direct = self._display_text(fund.get("benchmark"))
        if direct:
            return direct
        raw_data = fund.get("raw_data") or {}
        if not isinstance(raw_data, dict):
            return ""
        for key in ("info", "universe"):
            section = raw_data.get(key) or {}
            if isinstance(section, dict):
                value = self._display_text(section.get("benchmark"))
                if value:
                    return value
        return ""

    def _get_repository(self):
        if self._repository is None:
            from repositories import get_fund_classification_repo

            self._repository = get_fund_classification_repo()
        return self._repository

    @staticmethod
    def _date_text(value: Any) -> Optional[str]:
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        text = str(value or "").strip()
        if len(text) == 8 and text.isdigit():
            text = f"{text[:4]}-{text[4:6]}-{text[6:8]}"
        try:
            return datetime.fromisoformat(text[:10]).date().isoformat()
        except ValueError:
            return None

    @staticmethod
    def _display_text(value: Any) -> str:
        return unicodedata.normalize("NFKC", str(value or "")).strip()

    @staticmethod
    def _text(value: Any) -> str:
        return str(value or "").strip()
