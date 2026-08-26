#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Evidence-first industry-chain and supply-chain bottleneck research.

The module deliberately does not fetch market data or browse the web.  It
accepts a point-in-time research packet assembled by Newma-Desk's data and
Agent runtime, validates the industry-chain topology and every reference,
ranks scarce layers before public companies, and returns a compact
reproducible snapshot.

The numeric score is a research-priority heuristic, not a calibrated return
forecast and not a trading instruction.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime
from typing import Any, Iterable, Mapping

from instock.core.analysis_snapshot import (
    SNAPSHOT_SCHEMA_VERSION,
    get_analysis_snapshot_registry,
    normalize_as_of,
)


class SupplyChainResearchError(ValueError):
    """Raised when a research packet violates the module interface."""


class IndustryChainResearchEngine:
    engine_name = "instock-industry-chain-research"
    engine_version = "2.0.0"
    methodology = "industry-chain-topology-bottleneck-evidence-ranking-v1"
    packet_schema_version = "2.0"
    legacy_packet_schema_version = "1.0"

    _markets = {"CN", "HK", "US", "TW", "JP", "KR", "EU", "GLOBAL"}
    _chain_stages = {"upstream", "midstream", "downstream", "infrastructure"}
    _stage_order = {"upstream": 0, "midstream": 1, "downstream": 2, "infrastructure": 3}
    _symbol_pattern = re.compile(r"^[A-Za-z0-9.^_-]{1,32}$")
    _strength_scores = {"strong": 1.0, "medium": 0.65, "weak": 0.25, "unverified": 0.0}
    _layer_weights = {
        "demand_pressure": 0.20,
        "chokepoint_severity": 0.25,
        "supplier_concentration": 0.20,
        "expansion_difficulty": 0.20,
        "substitution_difficulty": 0.15,
    }
    _candidate_weights = {
        "exposure_purity": 0.20,
        "valuation_disconnect": 0.10,
        "catalyst_timing": 0.10,
        "financial_resilience": 0.10,
    }
    _penalty_weights = {
        "dilution_financing": 4.0,
        "governance": 4.0,
        "geopolitics": 3.0,
        "liquidity": 2.0,
        "hype_risk": 3.0,
        "accounting_quality": 4.0,
        "cyclicality": 2.5,
        "alternative_design_risk": 2.5,
    }

    def analyze(self, packet: Mapping[str, Any]) -> dict[str, Any]:
        payload = self._mapping(packet, "研究包")
        schema_version = str(payload.get("schema_version") or "").strip()
        if schema_version not in {self.packet_schema_version, self.legacy_packet_schema_version}:
            raise SupplyChainResearchError(
                f"研究包 schema_version 仅支持 {self.legacy_packet_schema_version} 或 {self.packet_schema_version}"
            )
        required = {"schema_version", "theme", "market", "as_of", "evidence", "layers", "candidates"}
        if schema_version == self.packet_schema_version:
            required.add("chain")
        self._require_exact_keys(
            payload,
            required=required,
            optional={"notes"},
            context="研究包",
        )

        theme = self._text(payload["theme"], "theme", maximum=160)
        market = self._market(payload["market"], "market")
        try:
            as_of = normalize_as_of(payload["as_of"], reject_future=True)
        except ValueError as exc:
            raise SupplyChainResearchError(str(exc)) from exc
        if not as_of:
            raise SupplyChainResearchError("as_of 为必填点时日期")

        evidence = self._parse_evidence(payload["evidence"], as_of)
        chain = (
            self._parse_chain(payload["chain"], evidence)
            if schema_version == self.packet_schema_version else None
        )
        chain_nodes = {item["id"]: item for item in (chain or {}).get("nodes", [])}
        layers, layer_limitations = self._parse_layers(
            payload["layers"],
            evidence,
            chain_nodes=chain_nodes,
            require_node_id=schema_version == self.packet_schema_version,
        )
        if chain is None:
            chain = self._legacy_chain(layers)
        layer_by_id = {item["id"]: item for item in layers}
        candidates, candidate_limitations = self._parse_candidates(
            payload["candidates"], evidence, layer_by_id
        )

        layers.sort(key=lambda item: (-item["priority_score"], item["name"], item["id"]))
        for rank, item in enumerate(layers, start=1):
            item["rank"] = rank
        layer_rank = {item["id"]: item["rank"] for item in layers}

        candidates.sort(
            key=lambda item: (-item["priority_score"], layer_rank[item["layer_id"]], item["symbol"])
        )
        for rank, item in enumerate(candidates, start=1):
            item["rank"] = rank

        chain = self._score_chain(chain, layers)

        limitations = sorted(set(layer_limitations + candidate_limitations))
        if schema_version == self.legacy_packet_schema_version:
            limitations.append("legacy_packet_without_explicit_chain_topology")
        data_state = "partial" if limitations else "complete"
        result_summary = {
            "theme": theme,
            "market": market,
            "as_of": as_of,
            "data_state": data_state,
            "layer_count": len(layers),
            "candidate_count": len(candidates),
            "evidence_count": len(evidence),
            "chain_node_count": len(chain["nodes"]),
            "chain_link_count": len(chain["links"]),
            "top_chain_node": chain["critical_nodes"][0]["name"],
            "top_layer": layers[0]["name"],
            "top_candidate": candidates[0]["symbol"],
            "limitations": limitations,
        }
        stable_result = {
            "chain": chain,
            "layers": layers,
            "candidates": candidates,
            "summary": result_summary,
        }
        snapshot = self._build_snapshot(payload, stable_result, result_summary, as_of)

        return {
            "engine": {
                "name": self.engine_name,
                "version": self.engine_version,
                "methodology": self.methodology,
                "calibrated_backtest": False,
            },
            "schema_version": schema_version,
            "canonical_schema_version": self.packet_schema_version,
            "theme": theme,
            "market": market,
            "as_of": as_of,
            "data_source": "newma-desk-agent",
            "data_state": data_state,
            "summary": result_summary,
            "chain": chain,
            "layers": layers,
            "candidates": candidates,
            "evidence_summary": self._evidence_summary(evidence.values()),
            "limitations": limitations,
            "snapshot": snapshot,
        }

    def _parse_evidence(self, values: Any, as_of: str) -> dict[str, dict[str, Any]]:
        items = self._list(values, "evidence", minimum=1, maximum=300)
        parsed: dict[str, dict[str, Any]] = {}
        for index, raw in enumerate(items):
            context = f"evidence[{index}]"
            item = self._mapping(raw, context)
            self._require_exact_keys(
                item,
                required={"id", "claim", "strength", "source_type", "source_ref", "observed_at"},
                optional=set(),
                context=context,
            )
            evidence_id = self._identifier(item["id"], f"{context}.id")
            if evidence_id in parsed:
                raise SupplyChainResearchError(f"重复证据 id: {evidence_id}")
            strength = str(item["strength"]).strip().lower()
            if strength not in self._strength_scores:
                raise SupplyChainResearchError(
                    f"{context}.strength 仅支持 {', '.join(self._strength_scores)}"
                )
            try:
                observed_at = normalize_as_of(item["observed_at"], reject_future=True)
            except ValueError as exc:
                raise SupplyChainResearchError(f"{context}.observed_at: {exc}") from exc
            if observed_at and observed_at > as_of:
                raise SupplyChainResearchError(f"{context}.observed_at 晚于研究截止日")
            parsed[evidence_id] = {
                "id": evidence_id,
                "claim": self._text(item["claim"], f"{context}.claim", maximum=800),
                "strength": strength,
                "source_type": self._text(item["source_type"], f"{context}.source_type", maximum=80),
                "source_ref": self._text(item["source_ref"], f"{context}.source_ref", maximum=500),
                "observed_at": observed_at,
            }
        return parsed

    def _parse_chain(
        self,
        value: Any,
        evidence: Mapping[str, Mapping[str, Any]],
    ) -> dict[str, Any]:
        chain = self._mapping(value, "chain")
        self._require_exact_keys(
            chain,
            required={"nodes", "links"},
            optional=set(),
            context="chain",
        )
        nodes = []
        node_ids = set()
        for index, raw in enumerate(self._list(chain["nodes"], "chain.nodes", minimum=1, maximum=60)):
            context = f"chain.nodes[{index}]"
            item = self._mapping(raw, context)
            self._require_exact_keys(
                item,
                required={"id", "name", "stage", "role", "evidence_ids"},
                optional=set(),
                context=context,
            )
            node_id = self._identifier(item["id"], f"{context}.id")
            if node_id in node_ids:
                raise SupplyChainResearchError(f"重复产业链节点 id: {node_id}")
            node_ids.add(node_id)
            stage = str(item["stage"] or "").strip().lower()
            if stage not in self._chain_stages:
                raise SupplyChainResearchError(
                    f"{context}.stage 仅支持 {', '.join(sorted(self._chain_stages))}"
                )
            refs = self._evidence_refs(item["evidence_ids"], evidence, f"{context}.evidence_ids")
            nodes.append({
                "id": node_id,
                "name": self._text(item["name"], f"{context}.name", maximum=120),
                "stage": stage,
                "role": self._text(item["role"], f"{context}.role", maximum=500),
                "evidence_ids": refs,
                "evidence_summary": self._evidence_summary(evidence[ref] for ref in refs),
            })

        links = []
        seen_links = set()
        for index, raw in enumerate(self._list(chain["links"], "chain.links", minimum=0, maximum=120)):
            context = f"chain.links[{index}]"
            item = self._mapping(raw, context)
            self._require_exact_keys(
                item,
                required={"source", "target", "relation", "criticality", "evidence_ids"},
                optional=set(),
                context=context,
            )
            source = self._identifier(item["source"], f"{context}.source")
            target = self._identifier(item["target"], f"{context}.target")
            if source not in node_ids or target not in node_ids:
                raise SupplyChainResearchError(f"{context} 引用了不存在的产业链节点")
            if source == target:
                raise SupplyChainResearchError(f"{context} 不允许节点自连接")
            identity = (source, target)
            if identity in seen_links:
                raise SupplyChainResearchError(f"重复产业链关系: {source}->{target}")
            seen_links.add(identity)
            raw_criticality = item["criticality"]
            if isinstance(raw_criticality, bool):
                raise SupplyChainResearchError(f"{context}.criticality 必须是 0..5 数字")
            try:
                criticality = float(raw_criticality)
            except (TypeError, ValueError) as exc:
                raise SupplyChainResearchError(f"{context}.criticality 必须是 0..5 数字") from exc
            if not math.isfinite(criticality) or not 0 <= criticality <= 5:
                raise SupplyChainResearchError(f"{context}.criticality 必须在 0..5 之间")
            refs = self._evidence_refs(item["evidence_ids"], evidence, f"{context}.evidence_ids")
            links.append({
                "source": source,
                "target": target,
                "relation": self._text(item["relation"], f"{context}.relation", maximum=300),
                "criticality": round(criticality, 2),
                "evidence_ids": refs,
                "evidence_summary": self._evidence_summary(evidence[ref] for ref in refs),
            })
        return {"nodes": nodes, "links": links}

    def _parse_layers(
        self,
        values: Any,
        evidence: Mapping[str, Mapping[str, Any]],
        *,
        chain_nodes: Mapping[str, Mapping[str, Any]],
        require_node_id: bool,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        items = self._list(values, "layers", minimum=1, maximum=20)
        parsed = []
        seen = set()
        limitations = []
        for index, raw in enumerate(items):
            context = f"layers[{index}]"
            item = self._mapping(raw, context)
            self._require_exact_keys(
                item,
                required={"id", "name", "constraint", "ratings", "evidence_ids"},
                optional={"node_id"},
                context=context,
            )
            if require_node_id and "node_id" not in item:
                raise SupplyChainResearchError(f"{context} 缺少字段: node_id")
            layer_id = self._identifier(item["id"], f"{context}.id")
            if layer_id in seen:
                raise SupplyChainResearchError(f"重复层级 id: {layer_id}")
            seen.add(layer_id)
            node_id = self._identifier(
                item.get("node_id") or layer_id,
                f"{context}.node_id",
            )
            if require_node_id and node_id not in chain_nodes:
                raise SupplyChainResearchError(f"{context}.node_id 不存在: {node_id}")
            ratings = self._ratings(item["ratings"], self._layer_weights, f"{context}.ratings")
            refs = self._evidence_refs(item["evidence_ids"], evidence, f"{context}.evidence_ids")
            summary = self._evidence_summary(evidence[ref] for ref in refs)
            base_score = self._weighted_rating(ratings, self._layer_weights)
            priority_score = round(base_score * 0.85 + summary["score"] * 0.15, 2)
            if summary["strong"] + summary["medium"] == 0:
                limitations.append(f"layer_without_strong_or_medium_evidence:{layer_id}")
            parsed.append({
                "id": layer_id,
                "node_id": node_id,
                "name": self._text(item["name"], f"{context}.name", maximum=120),
                "constraint": self._text(item["constraint"], f"{context}.constraint", maximum=600),
                "ratings": ratings,
                "factor_score": round(base_score, 2),
                "priority_score": priority_score,
                "evidence_ids": refs,
                "evidence_summary": summary,
            })
        return parsed, limitations

    @staticmethod
    def _legacy_chain(layers: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        nodes = [
            {
                "id": str(layer["node_id"]),
                "name": str(layer["name"]),
                "stage": "midstream",
                "role": str(layer["constraint"]),
                "evidence_ids": list(layer["evidence_ids"]),
                "evidence_summary": dict(layer["evidence_summary"]),
            }
            for layer in layers
        ]
        return {"nodes": nodes, "links": []}

    def _score_chain(
        self,
        chain: Mapping[str, Any],
        layers: Iterable[Mapping[str, Any]],
    ) -> dict[str, Any]:
        layer_scores: dict[str, list[float]] = {}
        for layer in layers:
            layer_scores.setdefault(str(layer["node_id"]), []).append(float(layer["priority_score"]))
        link_scores: dict[str, list[float]] = {}
        for link in chain["links"]:
            score = float(link["criticality"]) / 5 * 100
            link_scores.setdefault(str(link["source"]), []).append(score)
            link_scores.setdefault(str(link["target"]), []).append(score)

        nodes = []
        for raw in chain["nodes"]:
            node = dict(raw)
            node_layer_scores = layer_scores.get(str(node["id"]), [])
            node_link_scores = link_scores.get(str(node["id"]), [])
            bottleneck_score = max(node_layer_scores, default=0.0)
            relationship_score = sum(node_link_scores) / len(node_link_scores) if node_link_scores else 0.0
            evidence_score = float(node["evidence_summary"]["score"])
            node["bottleneck_score"] = round(bottleneck_score, 2)
            node["relationship_score"] = round(relationship_score, 2)
            node["criticality_score"] = round(
                bottleneck_score * 0.55 + relationship_score * 0.25 + evidence_score * 0.20,
                2,
            )
            node["layer_count"] = len(node_layer_scores)
            nodes.append(node)

        nodes.sort(
            key=lambda item: (
                self._stage_order.get(str(item["stage"]), 99),
                -float(item["criticality_score"]),
                str(item["name"]),
            )
        )
        critical_nodes = sorted(
            (dict(item) for item in nodes),
            key=lambda item: (-float(item["criticality_score"]), str(item["name"])),
        )
        for rank, node in enumerate(critical_nodes, start=1):
            node["rank"] = rank
        return {
            "nodes": nodes,
            "links": list(chain["links"]),
            "critical_nodes": critical_nodes,
            "method": "bottleneck_55_relationship_25_evidence_20",
        }

    def _parse_candidates(
        self,
        values: Any,
        evidence: Mapping[str, Mapping[str, Any]],
        layers: Mapping[str, Mapping[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        items = self._list(values, "candidates", minimum=1, maximum=100)
        parsed = []
        seen = set()
        limitations = []
        for index, raw in enumerate(items):
            context = f"candidates[{index}]"
            item = self._mapping(raw, context)
            self._require_exact_keys(
                item,
                required={
                    "symbol", "name", "market", "layer_id", "ratings", "penalties",
                    "evidence_ids", "invalidation",
                },
                optional=set(),
                context=context,
            )
            symbol = str(item["symbol"]).strip().upper()
            if not self._symbol_pattern.fullmatch(symbol):
                raise SupplyChainResearchError(f"{context}.symbol 格式无效")
            identity = (self._market(item["market"], f"{context}.market"), symbol)
            if identity in seen:
                raise SupplyChainResearchError(f"重复候选: {identity[0]}:{symbol}")
            seen.add(identity)
            layer_id = self._identifier(item["layer_id"], f"{context}.layer_id")
            if layer_id not in layers:
                raise SupplyChainResearchError(f"{context}.layer_id 不存在: {layer_id}")
            ratings = self._ratings(item["ratings"], self._candidate_weights, f"{context}.ratings")
            penalties = self._ratings(item["penalties"], self._penalty_weights, f"{context}.penalties")
            refs = self._evidence_refs(item["evidence_ids"], evidence, f"{context}.evidence_ids")
            invalidation = [
                self._text(value, f"{context}.invalidation", maximum=500)
                for value in self._list(item["invalidation"], f"{context}.invalidation", minimum=1, maximum=8)
            ]
            evidence_summary = self._evidence_summary(evidence[ref] for ref in refs)
            confidence = self._confidence(evidence_summary)
            layer_score = float(layers[layer_id]["priority_score"])
            raw_score = (
                layer_score * 0.30
                + ratings["exposure_purity"] / 5 * 100 * 0.20
                + ratings["valuation_disconnect"] / 5 * 100 * 0.10
                + ratings["catalyst_timing"] / 5 * 100 * 0.10
                + ratings["financial_resilience"] / 5 * 100 * 0.10
                + evidence_summary["score"] * 0.20
            )
            penalty_score = sum(
                penalties[key] / 5 * weight for key, weight in self._penalty_weights.items()
            )
            final_score = round(max(0.0, min(100.0, raw_score - penalty_score)), 2)
            priority = self._priority(final_score, confidence, evidence_summary)
            if confidence == "low":
                limitations.append(f"candidate_without_strong_or_medium_evidence:{symbol}")
            if evidence_summary["strong"] >= 2 and evidence_summary["source_count"] < 2:
                limitations.append(f"candidate_evidence_source_concentration:{symbol}")
            parsed.append({
                "symbol": symbol,
                "name": self._text(item["name"], f"{context}.name", maximum=120),
                "market": identity[0],
                "layer_id": layer_id,
                "layer_priority_score": round(layer_score, 2),
                "ratings": ratings,
                "penalties": penalties,
                "raw_score": round(raw_score, 2),
                "penalty_score": round(penalty_score, 2),
                "priority_score": final_score,
                "research_priority": priority,
                "confidence": confidence,
                "evidence_ids": refs,
                "evidence_summary": evidence_summary,
                "invalidation": invalidation,
            })
        return parsed, limitations

    def _build_snapshot(
        self,
        packet: Mapping[str, Any],
        stable_result: Mapping[str, Any],
        summary: Mapping[str, Any],
        as_of: str,
    ) -> dict[str, Any]:
        input_digest = self._digest(packet)
        result_digest = self._digest(stable_result)
        snapshot_material = {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "analysis": {"name": self.engine_name, "version": self.engine_version},
            "as_of": as_of,
            "input_digest": input_digest,
            "result_digest": result_digest,
        }
        snapshot_hash = self._digest(snapshot_material).split(":", 1)[1]
        lag_days = max((date.today() - datetime.strptime(as_of, "%Y-%m-%d").date()).days, 0)
        return {
            "schema_version": SNAPSHOT_SCHEMA_VERSION,
            "snapshot_id": f"{self.engine_name}:{snapshot_hash[:24]}",
            "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "analysis": {"name": self.engine_name, "version": self.engine_version},
            "parameters": {
                "theme": summary["theme"],
                "market": summary["market"],
                "asOf": as_of,
                "methodology": self.methodology,
            },
            "data_window": {
                "requested_as_of": as_of,
                "start_date": None,
                "end_date": as_of,
                "coverage": summary["data_state"],
            },
            "provenance": {
                "provider": "newma-desk-agent",
                "endpoint": "host-action-input",
                "upstream_source": "structured-research-packet",
                "upstream_as_of": as_of,
                "limitations": list(summary["limitations"]),
            },
            "freshness": {
                "state": "current" if lag_days <= 3 else "historical",
                "resolution": "point_in_time",
                "calendar_lag_days": lag_days,
            },
            "input": {
                "digest": input_digest,
                "summary": {
                    "theme": summary["theme"],
                    "market": summary["market"],
                    "as_of": as_of,
                    "chain_node_count": summary["chain_node_count"],
                    "chain_link_count": summary["chain_link_count"],
                    "layer_count": summary["layer_count"],
                    "candidate_count": summary["candidate_count"],
                    "evidence_count": summary["evidence_count"],
                },
            },
            "result": {
                "digest": result_digest,
                "summary": dict(summary),
                "evidence": {
                    "layers": [dict(item) for item in stable_result["layers"]],
                    "candidates": [dict(item) for item in stable_result["candidates"]],
                },
            },
        }

    @staticmethod
    def _mapping(value: Any, context: str) -> dict[str, Any]:
        if not isinstance(value, Mapping):
            raise SupplyChainResearchError(f"{context} 必须是对象")
        return dict(value)

    @staticmethod
    def _list(value: Any, context: str, *, minimum: int, maximum: int) -> list[Any]:
        if not isinstance(value, list):
            raise SupplyChainResearchError(f"{context} 必须是数组")
        if not minimum <= len(value) <= maximum:
            raise SupplyChainResearchError(f"{context} 数量须在 {minimum}..{maximum} 之间")
        return value

    @staticmethod
    def _text(value: Any, context: str, *, maximum: int) -> str:
        text = str(value or "").strip()
        if not text:
            raise SupplyChainResearchError(f"{context} 不能为空")
        if len(text) > maximum:
            raise SupplyChainResearchError(f"{context} 长度不能超过 {maximum}")
        return text

    @classmethod
    def _identifier(cls, value: Any, context: str) -> str:
        text = cls._text(value, context, maximum=80)
        if re.fullmatch(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", text) is None:
            raise SupplyChainResearchError(f"{context} 只能使用小写字母、数字、连字符或下划线")
        return text

    @classmethod
    def _market(cls, value: Any, context: str) -> str:
        market = str(value or "").strip().upper()
        if market not in cls._markets:
            raise SupplyChainResearchError(f"{context} 仅支持 {', '.join(sorted(cls._markets))}")
        return market

    @staticmethod
    def _require_exact_keys(
        value: Mapping[str, Any], *, required: set[str], optional: set[str], context: str
    ) -> None:
        keys = set(value)
        missing = sorted(required - keys)
        unknown = sorted(keys - required - optional)
        if missing:
            raise SupplyChainResearchError(f"{context} 缺少字段: {', '.join(missing)}")
        if unknown:
            raise SupplyChainResearchError(f"{context} 包含未知字段: {', '.join(unknown)}")

    @classmethod
    def _ratings(
        cls, value: Any, weights: Mapping[str, float], context: str
    ) -> dict[str, float]:
        ratings = cls._mapping(value, context)
        keys = set(ratings)
        expected = set(weights)
        if keys != expected:
            missing = sorted(expected - keys)
            unknown = sorted(keys - expected)
            if unknown:
                raise SupplyChainResearchError(f"{context} 包含未知评分字段: {', '.join(unknown)}")
            raise SupplyChainResearchError(f"{context} 缺少评分字段: {', '.join(missing)}")
        parsed = {}
        for key in weights:
            raw = ratings[key]
            if isinstance(raw, bool):
                raise SupplyChainResearchError(f"{context}.{key} 必须是 0..5 数字")
            try:
                number = float(raw)
            except (TypeError, ValueError) as exc:
                raise SupplyChainResearchError(f"{context}.{key} 必须是 0..5 数字") from exc
            if not math.isfinite(number) or not 0 <= number <= 5:
                raise SupplyChainResearchError(f"{context}.{key} 必须在 0..5 之间")
            parsed[key] = round(number, 2)
        return parsed

    @classmethod
    def _evidence_refs(
        cls,
        value: Any,
        evidence: Mapping[str, Mapping[str, Any]],
        context: str,
    ) -> list[str]:
        refs = [
            cls._identifier(item, context)
            for item in cls._list(value, context, minimum=1, maximum=30)
        ]
        if len(set(refs)) != len(refs):
            raise SupplyChainResearchError(f"{context} 包含重复证据")
        missing = [ref for ref in refs if ref not in evidence]
        if missing:
            raise SupplyChainResearchError(f"{context} 引用了不存在的证据: {', '.join(missing)}")
        return refs

    @classmethod
    def _evidence_summary(cls, evidence: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        counts = {key: 0 for key in cls._strength_scores}
        scores = []
        source_refs = set()
        source_types = set()
        for item in evidence:
            strength = str(item["strength"])
            counts[strength] += 1
            scores.append(cls._strength_scores[strength])
            source_refs.add(str(item["source_ref"]))
            source_types.add(str(item["source_type"]))
        return {
            **counts,
            "total": len(scores),
            "score": round(sum(scores) / len(scores) * 100, 2) if scores else 0.0,
            "source_count": len(source_refs),
            "source_type_count": len(source_types),
        }

    @staticmethod
    def _weighted_rating(ratings: Mapping[str, float], weights: Mapping[str, float]) -> float:
        return sum(ratings[key] / 5 * 100 * weight for key, weight in weights.items())

    @staticmethod
    def _confidence(summary: Mapping[str, Any]) -> str:
        if summary["strong"] >= 2 and summary["source_count"] >= 2:
            return "high"
        if summary["strong"] >= 1 or summary["medium"] >= 2:
            return "medium"
        return "low"

    @staticmethod
    def _priority(score: float, confidence: str, evidence: Mapping[str, Any]) -> str:
        if confidence == "low":
            return "early_lead"
        if score >= 85 and confidence == "high" and evidence["strong"] >= 2:
            return "top_priority"
        if score >= 70:
            return "high_priority"
        if score >= 55:
            return "worth_tracking"
        return "early_lead"

    @staticmethod
    def _digest(value: Any) -> str:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def resolve_industry_chain_snapshot(
    snapshot_id: str | None,
    *,
    symbol: str,
    as_of: str | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    if not snapshot_id:
        return None, []
    snapshot = get_analysis_snapshot_registry().get(snapshot_id)
    if snapshot is None:
        return None, ["industry_chain_snapshot_not_found"]
    if (snapshot.get("analysis") or {}).get("name") != IndustryChainResearchEngine.engine_name:
        return None, ["industry_chain_snapshot_type_mismatch"]
    snapshot_as_of = (snapshot.get("data_window") or {}).get("end_date")
    if as_of and snapshot_as_of and snapshot_as_of > as_of:
        return None, ["industry_chain_snapshot_after_research_as_of"]
    result = snapshot.get("result") or {}
    evidence = result.get("evidence") or {}
    if not evidence:
        return None, ["industry_chain_snapshot_evidence_unavailable"]
    code = str(symbol or "").strip().upper().split(".")[0]
    candidate = next(
        (
            dict(item) for item in evidence.get("candidates") or []
            if str(item.get("symbol") or "").upper().split(".")[0] == code
        ),
        None,
    )
    response = {
        "snapshot_id": snapshot_id,
        "as_of": snapshot_as_of,
        "summary": dict(result.get("summary") or {}),
        "freshness": dict(snapshot.get("freshness") or {}),
        "exposure": None,
    }
    if candidate is None:
        return response, ["industry_chain_security_exposure_not_found"]
    layer = next(
        (
            dict(item) for item in evidence.get("layers") or []
            if item.get("id") == candidate.get("layer_id")
        ),
        None,
    )
    response["exposure"] = {**candidate, "layer": layer}
    return response, []


# Compatibility aliases for callers migrating from the former rotation-owned
# supply-chain Action. New code should use the industry-chain names.
IndustryChainResearchError = SupplyChainResearchError
SupplyChainResearchEngine = IndustryChainResearchEngine
