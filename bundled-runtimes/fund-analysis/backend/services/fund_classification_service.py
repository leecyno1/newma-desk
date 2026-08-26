"""
基金分类 Module。

把分散在评分、同类比较和页面调用方中的类型/关键词判断收口为一个可审计
Interface。显式策略族谱优先；基础类型与名称只作为带置信度的回退证据；无法
分类时明确返回证据不足，禁止默认归入主动权益。
"""
from typing import Any, Dict, List, Optional, Tuple

from services.fund_classification_catalog import FundClassificationCatalog


class FundClassificationService:
    """生成多层基金分类及其证据。"""

    METHODOLOGY_VERSION = "fund_classification_v4"

    FAMILY_META: Dict[str, Dict[str, Any]] = FundClassificationCatalog.family_meta()

    EXPLICIT_FAMILY_KEYS = (
        "strategy_family_key",
        "strategyFamilyKey",
        "strategy_family",
        "strategyFamily",
    )

    SECTOR_TERMS = (
        "行业", "主题", "医药", "医疗", "科技", "半导体", "芯片", "新能源", "消费",
        "军工", "传媒", "金融地产", "人工智能", "ai", "互联网",
    )

    def classify(
        self,
        fund: Dict[str, Any],
        profile: Optional[Dict[str, Any]] = None,
        standardized_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        profile = profile or {}
        standardized_context = standardized_context or {}
        if standardized_context.get("status") == "resolved":
            return self._classify_standardized(fund, standardized_context)

        evidence: List[Dict[str, Any]] = []
        fund_type = self._text(fund.get("type"))
        fund_name = self._text(fund.get("name") or fund.get("fund_name"))

        explicit_family = self._explicit_family(profile)
        if explicit_family:
            evidence.append(self._evidence("strategy_family_key", explicit_family, "research_profile", "显式策略族谱"))
            family_key = explicit_family if explicit_family in self.FAMILY_META else None
            if family_key:
                return self._classified_result(
                    fund,
                    profile,
                    family_key,
                    evidence,
                    confidence=0.98,
                    source="explicit_strategy_family",
                )
            return self._unavailable_result(
                fund,
                evidence,
                [f"策略族谱 {explicit_family} 尚未登记到分类方法中"],
            )

        if self._is_qdii(fund_type):
            evidence.append(self._evidence(
                "fund.type",
                fund_type,
                "fund_metadata",
                "QDII 法定类型证据",
            ))
            qdii_candidate, qdii_reason = self._qdii_candidate(fund, profile)
            if qdii_candidate:
                evidence.extend(qdii_candidate["evidence"])
                return self._classified_result(
                    fund,
                    {
                        **profile,
                        "peer_group": qdii_candidate["peer_group_name"],
                        "primary_benchmark": qdii_candidate["benchmark_name"],
                    },
                    qdii_candidate["strategy_family_key"],
                    evidence,
                    confidence=0.94,
                    source="qdii_asset_class_fallback",
                )
            return self._unavailable_result(
                fund,
                evidence,
                [qdii_reason or "QDII 资产类别证据不足，不能进入同类评价"],
            )

        if self._is_fof(fund_name, fund_type):
            evidence.append(self._evidence(
                "fund.type/name",
                f"{fund_type} {fund_name}".strip(),
                "fund_metadata",
                "FOF 产品类型证据",
            ))
            fof_candidate, fof_reason = self._fof_candidate(fund, profile)
            if fof_candidate:
                evidence.append(self._evidence(
                    "fund.contract_benchmark",
                    fof_candidate["benchmark_name"],
                    "fund_metadata",
                    fof_candidate["rationale"],
                ))
                return self._classified_result(
                    fund,
                    {
                        **profile,
                        "peer_group": fof_candidate["peer_group_name"],
                        "primary_benchmark": fof_candidate["benchmark_name"],
                    },
                    fof_candidate["strategy_family_key"],
                    evidence,
                    confidence=0.9,
                    source="fof_contract_benchmark_fallback",
                )
            return self._unavailable_result(
                fund,
                evidence,
                [fof_reason or "FOF 合同基准资产权重不足，不能进入专属 FOF 同类组"],
            )

        family_key, matched_field, matched_value = self._infer_family(fund_type, fund_name, profile)
        if family_key:
            evidence.append(self._evidence(matched_field, matched_value, "fund_metadata", "基础类型/名称分类回退"))
            peer_group = self._text(profile.get("peer_group"))
            if peer_group:
                evidence.append(self._evidence("peer_group", peer_group, "research_profile", "现有同类组辅助验证"))
            confidence = 0.82 if fund_type else 0.58
            return self._classified_result(
                fund,
                profile,
                family_key,
                evidence,
                confidence=confidence,
                source="fund_metadata_fallback",
            )

        if fund_type:
            evidence.append(self._evidence("fund.type", fund_type, "fund_metadata", "未命中已登记分类规则"))
        if fund_name:
            evidence.append(self._evidence("fund.name", fund_name, "fund_metadata", "未命中已登记分类规则"))
        return self._unavailable_result(
            fund,
            evidence,
            ["缺少可确认的资产类别、策略族谱或主动/被动证据，不能进入分类内基金评价"],
        )

    def _classify_standardized(
        self,
        fund: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        evidence = list(context.get("classification_evidence") or [])
        family_key = self._text(context.get("strategy_family_key"))
        if not family_key:
            return self._unavailable_result(
                fund,
                evidence,
                context.get("missing_items") or ["标准化基金实体缺少策略族谱"],
                standardized_context=context,
            )
        if family_key not in self.FAMILY_META:
            return self._unavailable_result(
                fund,
                evidence,
                [f"标准化策略族谱 {family_key} 尚未登记到基金评价方法中"],
                standardized_context=context,
            )

        meta = self.FAMILY_META[family_key]
        conflicts = []
        asset_class = self._text(context.get("asset_class"))
        active_passive = self._text(context.get("active_passive"))
        if asset_class and asset_class != meta["asset_class"]:
            conflicts.append(
                f"标准化资产类别 {asset_class} 与策略族谱 {family_key} 的 {meta['asset_class']} 冲突"
            )
        if active_passive and active_passive != meta["active_passive"]:
            conflicts.append(
                f"标准化主动/被动 {active_passive} 与策略族谱 {family_key} 的 {meta['active_passive']} 冲突"
            )
        if conflicts:
            return self._unavailable_result(
                fund,
                evidence,
                conflicts,
                standardized_context=context,
            )

        return self._classified_result(
            fund,
            {},
            family_key,
            evidence,
            confidence=self._confidence(context.get("classification_confidence"), 0.95),
            source="standardized_classification_adapter",
            standardized_context=context,
        )

    def _explicit_family(self, profile: Dict[str, Any]) -> Optional[str]:
        for key in self.EXPLICIT_FAMILY_KEYS:
            value = self._text(profile.get(key))
            if value:
                return value
        return None

    @staticmethod
    def _is_fof(fund_name: str, fund_type: str) -> bool:
        evidence = f"{fund_name} {fund_type}".lower()
        return "fof" in evidence or "基金中基金" in evidence

    @staticmethod
    def _is_qdii(fund_type: str) -> bool:
        return "qdii" in str(fund_type or "").lower()

    def _qdii_candidate(
        self,
        fund: Dict[str, Any],
        profile: Dict[str, Any],
    ) -> Tuple[Optional[Dict[str, Any]], str]:
        from services.fund_classification_ingestion_service import FundClassificationIngestionService

        raw_data = fund.get("raw_data") if isinstance(fund.get("raw_data"), dict) else {}
        info = raw_data.get("info") if isinstance(raw_data.get("info"), dict) else {}
        universe = raw_data.get("universe") if isinstance(raw_data.get("universe"), dict) else {}
        invest_type = self._text(fund.get("invest_type") or universe.get("invest_type") or info.get("invest_type"))
        contract_type = self._text(fund.get("contract_type") or universe.get("contract_type") or info.get("contract_type"))
        declared_benchmark = self._text(
            fund.get("contract_benchmark")
            or fund.get("benchmark")
            or profile.get("primary_benchmark")
            or universe.get("benchmark")
            or info.get("benchmark")
        )
        candidate, reason = FundClassificationIngestionService()._qdii_candidate(
            declared_benchmark,
            invest_type,
            contract_type,
        )
        if not candidate:
            reason_labels = {
                "qdii_missing_declared_benchmark": "QDII 缺少合同业绩比较基准",
                "qdii_index_not_supported": "该 QDII 指数尚未进入可核验的全球指数基准目录",
                "qdii_index_contract_type_conflict": "QDII 被动指数的合同类型不是股票型",
                "qdii_index_reference_not_100_percent": "QDII 指数基金的纳斯达克100合同基准权重不是100%",
                "qdii_index_currency_basis_unverified": "QDII 指数基金的合同基准未明确汇率调整或人民币计价口径",
                "qdii_unsupported_or_conflicting_asset_class": "QDII 投资类型与合同类型不足以确认资产类别",
            }
            return None, reason_labels.get(reason, "QDII 资产类别证据不足")
        return {
            "strategy_family_key": str(candidate["strategy_family_key"]),
            "peer_group_name": str(candidate["peer_group_benchmark_name"]),
            "benchmark_name": str(candidate["benchmark_name"]),
            "evidence": [
                self._evidence("fund.invest_type", invest_type, "fund_metadata", "QDII 投资类型"),
                self._evidence("fund.contract_type", contract_type, "fund_metadata", "QDII 合同类型"),
                self._evidence("fund.contract_benchmark", declared_benchmark, "fund_metadata", "QDII 合同业绩比较基准"),
            ],
        }, ""

    def _fof_candidate(
        self,
        fund: Dict[str, Any],
        profile: Dict[str, Any],
    ) -> Tuple[Optional[Dict[str, str]], str]:
        from services.fund_classification_ingestion_service import FundClassificationIngestionService

        raw_data = fund.get("raw_data") if isinstance(fund.get("raw_data"), dict) else {}
        info = raw_data.get("info") if isinstance(raw_data.get("info"), dict) else {}
        universe = raw_data.get("universe") if isinstance(raw_data.get("universe"), dict) else {}
        declared_benchmark = self._text(
            fund.get("contract_benchmark")
            or fund.get("benchmark")
            or profile.get("primary_benchmark")
            or universe.get("benchmark")
            or info.get("benchmark")
        )
        candidate, reason = FundClassificationIngestionService()._fof_candidate(
            declared_benchmark,
            self._text(fund.get("invest_type") or universe.get("invest_type") or info.get("invest_type")),
            self._text(fund.get("contract_type") or universe.get("contract_type") or info.get("contract_type")),
        )
        if not candidate:
            reason_labels = {
                "fof_missing_declared_benchmark": "FOF 缺少合同业绩比较基准，不能确认风险目标",
                "fof_benchmark_weights_unavailable": "FOF 合同基准没有可核验的资产权重",
                "fof_benchmark_weights_incomplete": "FOF 合同基准资产权重合计不完整",
                "fof_benchmark_asset_class_ambiguous": "FOF 合同基准包含无法识别的资产类别",
            }
            return None, reason_labels.get(reason, "FOF 合同类型或投资类型与专属分类口径冲突")
        return {
            "strategy_family_key": str(candidate["strategy_family_key"]),
            "peer_group_name": str(candidate["benchmark_name"]).replace("FOF 合同基准", "FOF"),
            "benchmark_name": str(candidate["benchmark_name"]),
            "rationale": str(candidate["rationale"]),
        }, ""

    def _infer_family(
        self,
        fund_type: str,
        fund_name: str,
        profile: Dict[str, Any],
    ) -> Tuple[Optional[str], str, str]:
        combined = f"{fund_type} {fund_name} {self._text(profile.get('peer_group'))}".lower()

        if any(token in combined for token in ("货币", "money", "现金管理")):
            return "cash_management", "fund.type/name", combined.strip()
        if any(token in combined for token in ("指数增强", "增强指数", "enhanced index")):
            return "index_enhanced", "fund.type/name", combined.strip()
        if any(token in combined for token in ("指数", "index", "etf", "联接")):
            if any(token in combined for token in ("债券", "同业存单", "国开债", "政金债")):
                return "index_fixed_income", "fund.type/name", combined.strip()
            if any(token in combined for token in self.SECTOR_TERMS):
                return "index_sector", "fund.type/name", combined.strip()
            return "index_broad", "fund.type/name", combined.strip()
        if any(token in combined for token in ("债券", "纯债", "信用债", "产业债", "bond", "固收")):
            family = "fixed_income_credit" if any(token in combined for token in ("信用", "产业债")) else "fixed_income_general"
            return family, "fund.type/name", combined.strip()
        if any(token in combined for token in ("偏股混合", "偏股", "主动权益", "equity", "stock", "股票")):
            family = "active_equity_sector" if any(token in combined for token in self.SECTOR_TERMS) else "active_equity_core"
            return family, "fund.type/name", combined.strip()
        if any(token in combined for token in ("混合型", "hybrid", "灵活配置", "平衡混合")):
            return "multi_asset_allocation", "fund.type/name", combined.strip()
        return None, "", ""

    def _classified_result(
        self,
        fund: Dict[str, Any],
        profile: Dict[str, Any],
        family_key: str,
        evidence: List[Dict[str, Any]],
        confidence: float,
        source: str,
        standardized_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        meta = self.FAMILY_META[family_key]
        context = standardized_context or {}
        benchmark_mapping = context.get("benchmark_mapping") or {}
        peer_group = context.get("peer_group_name") or context.get("peer_group_key") or profile.get("peer_group")
        primary_benchmark = benchmark_mapping.get("benchmark_name") or profile.get("primary_benchmark")
        missing_items = list(context.get("missing_items") or [])
        if not peer_group:
            missing_items.append("缺少显式同类组，不能形成完整的分类内基金评价")
        if not primary_benchmark:
            missing_items.append("缺少有效基准映射，不能形成完整的分类内基金评价")
        return {
            "status": "classified",
            "methodology_version": self.METHODOLOGY_VERSION,
            "fund_code": fund.get("wind_code") or fund.get("ts_code") or fund.get("id"),
            "legal_type": fund.get("type"),
            "entity_id": context.get("entity_id"),
            "canonical_code": context.get("canonical_code"),
            "canonical_name": context.get("canonical_name"),
            "asset_class": context.get("asset_class") or meta["asset_class"],
            "strategy_family_key": family_key,
            "strategy_family_name": context.get("strategy_family_name"),
            "active_passive": context.get("active_passive") or meta["active_passive"],
            "evaluation_profile_key": meta["evaluation_profile_key"],
            "peer_group": peer_group,
            "peer_group_id": context.get("peer_group_id"),
            "peer_group_key": context.get("peer_group_key"),
            "peer_group_name": context.get("peer_group_name"),
            "minimum_peer_count": context.get("minimum_peer_count"),
            "primary_benchmark": primary_benchmark,
            "benchmark_code": benchmark_mapping.get("benchmark_code"),
            "benchmark_mapping": benchmark_mapping or None,
            "compatible_fund_types": list(meta["compatible_fund_types"]),
            "confidence": round(confidence, 2),
            "source": source,
            "evidence": evidence,
            "missing_items": list(dict.fromkeys(missing_items)),
        }

    def _unavailable_result(
        self,
        fund: Dict[str, Any],
        evidence: List[Dict[str, Any]],
        missing_items: List[str],
        standardized_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        context = standardized_context or {}
        benchmark_mapping = context.get("benchmark_mapping") or {}
        context_family_key = context.get("strategy_family_key")
        context_meta = self.FAMILY_META.get(str(context_family_key or ""), {})
        return {
            "status": "insufficient_evidence",
            "methodology_version": self.METHODOLOGY_VERSION,
            "fund_code": fund.get("wind_code") or fund.get("ts_code") or fund.get("id"),
            "legal_type": fund.get("type"),
            "entity_id": context.get("entity_id"),
            "canonical_code": context.get("canonical_code"),
            "canonical_name": context.get("canonical_name"),
            "asset_class": context.get("asset_class"),
            "strategy_family_key": context_family_key,
            "strategy_family_name": context.get("strategy_family_name"),
            "active_passive": context.get("active_passive"),
            "evaluation_profile_key": context_meta.get("evaluation_profile_key"),
            "peer_group": context.get("peer_group_name") or context.get("peer_group_key"),
            "peer_group_id": context.get("peer_group_id"),
            "peer_group_key": context.get("peer_group_key"),
            "peer_group_name": context.get("peer_group_name"),
            "minimum_peer_count": context.get("minimum_peer_count"),
            "primary_benchmark": benchmark_mapping.get("benchmark_name"),
            "benchmark_code": benchmark_mapping.get("benchmark_code"),
            "benchmark_mapping": benchmark_mapping or None,
            "compatible_fund_types": [],
            "confidence": 0.0,
            "source": "standardized_evidence_gate" if context else "evidence_gate",
            "evidence": evidence,
            "missing_items": list(dict.fromkeys(str(item) for item in missing_items if item)),
        }

    def _evidence(self, field: str, value: str, source: str, reason: str) -> Dict[str, str]:
        return {"field": field, "value": value, "source": source, "reason": reason}

    def _confidence(self, value: Any, default: float) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return default

    def _text(self, value: Any) -> str:
        return str(value or "").strip()
