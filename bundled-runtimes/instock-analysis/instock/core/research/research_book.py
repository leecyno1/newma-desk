#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Deterministic research-book contract without persistence or trading."""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime
from typing import Any, Mapping

import pandas as pd

from instock.core.analysis_snapshot import SNAPSHOT_SCHEMA_VERSION, get_analysis_snapshot_registry, normalize_as_of
from instock.core.research.supply_chain import resolve_industry_chain_snapshot
from instock.core.research.thesis_review import review_thesis, summarize_reviews


class ResearchBookError(ValueError):
    """Raised when a research-book packet violates its contract."""


class ResearchBookEngine:
    engine_name = "instock-research-book"
    engine_version = "1.6.0"
    packet_schema_version = "instock-research-book-packet-v1"
    supported_markets = {"CN", "HK", "US", "GLOBAL"}
    symbol_pattern = re.compile(r"^[A-Za-z0-9.^_-]{1,32}$")

    def analyze(self, packet: Mapping[str, Any]) -> dict[str, Any]:
        payload = self._validate_packet(packet)
        items = [self._parse_item(item, index) for index, item in enumerate(payload["items"])]
        total_weight = round(sum(item["target_weight_pct"] for item in items), 2)
        if total_weight > 100:
            raise ResearchBookError("总目标权重不能超过 100%")
        resolved_count = missing_count = 0
        registry = get_analysis_snapshot_registry()
        for item in items:
            references = []
            for snapshot_id in item["snapshot_ids"]:
                snapshot = registry.get(snapshot_id)
                reference = self._reference(snapshot_id, snapshot, item, payload["as_of"])
                references.append(reference)
                if reference["state"] == "resolved": resolved_count += 1
                else: missing_count += 1
            item["snapshot_references"] = references
            item["snapshot_coverage"] = "complete" if references and all(ref["state"] == "resolved" for ref in references) else "missing" if references else "none"
            item["thesis_review"] = review_thesis(item, payload["as_of"])
        review_summary = summarize_reviews(items)
        exposures = self._exposures(items)
        warnings = []
        for item in items:
            if item["target_weight_pct"] > 20:
                warnings.append(f"position_concentration:{item['symbol']}")
            if item["snapshot_coverage"] != "complete":
                warnings.append(f"snapshot_coverage:{item['symbol']}:{item['snapshot_coverage']}")
            for reference in item["snapshot_references"]:
                if reference["state"] == "resolved" and reference.get("source_coverage") != "complete":
                    warnings.append(f"source_incomplete:{item['symbol']}:{reference['snapshot_id']}")
        for sector in exposures["sectors"]:
            if sector["weight_pct"] > 40:
                warnings.append(f"sector_concentration:{sector['name']}")
        data_state = "partial" if missing_count or any(item["snapshot_coverage"] == "none" for item in items) or any(warning.startswith('source_incomplete:') for warning in warnings) else "complete"
        summary = {"items": len(items), "total_target_weight_pct": total_weight, "cash_weight_pct": round(100 - total_weight, 2), "resolved_snapshots": resolved_count, "missing_snapshots": missing_count, "data_state": data_state}
        limitations = ["research_book_history_is_scoped_and_retention_limited", "research_book_contains_no_order_or_execution_actions", "target_weights_are_research_exposure_not_portfolio_advice", "matched_references_are_not_verified_investment_claims", "workspace_human_reviews_are_not_in_result_snapshots"]
        limitations.append("text_alignment_is_not_thesis_validity_conditions_require_human_review")
        stable_result = {"summary": summary, "items": items, "exposures": exposures, "warnings": warnings, "review_summary": review_summary}
        snapshot = self._build_snapshot(payload, stable_result, limitations)
        registry.register(snapshot)
        return {"engine": {"name": self.engine_name, "version": self.engine_version}, "schema_version": self.packet_schema_version, "name": payload["name"], "as_of": payload["as_of"], "data_source": "newma-desk-context", "data_state": data_state, **stable_result, "limitations": limitations, "snapshot": snapshot}

    @staticmethod
    def _same_security(left, right, market):
        left, right = str(left or "").strip().upper(), str(right or "").strip().upper()
        if market != "CN": return bool(left and left == right)
        pattern = r"\d{6}(?:\.(?:SH|SZ|BJ))?"
        if not re.fullmatch(pattern, left) or not re.fullmatch(pattern, right): return False
        a, _, ae = left.partition("."); b, _, be = right.partition(".")
        return a == b and (not ae or not be or ae == be)

    def _reference(self, snapshot_id, snapshot, item, as_of):
        ref = {"snapshot_id": snapshot_id, "state": "missing"}
        if snapshot is None: return ref
        ref.update(analysis=dict(snapshot.get("analysis") or {}), freshness=dict(snapshot.get("freshness") or {}),
                   source_generated_at=snapshot.get("generated_at"), freshness_basis="original_analysis_time")
        window = snapshot.get("data_window") or {}
        end = window.get("end_date")
        try: end = date.fromisoformat(end).isoformat()
        except (ValueError, TypeError): return {**ref, "state": "date_unknown"}
        ref.update(as_of=end, source_coverage=window.get("coverage", "unknown"))
        if end > as_of: return {**ref, "state": "after_cutoff"}
        parameters = snapshot.get("parameters") or {}
        result = snapshot.get("result") or {}; summary = result.get("summary") or {}; evidence = result.get("evidence") or {}
        engine = ref["analysis"].get("name")
        if engine == "instock-stock-research-dossier":
            market = summary.get("market", "CN")  # This engine's documented contract is A shares only.
            symbols = [parameters.get("symbol") or summary.get("symbol")]
        elif engine == "instock-industry-chain-research":
            candidates = evidence.get("candidates") or []
            market = item["market"]
            symbols = [row.get("symbol") for row in candidates if row.get("market") == market]
        elif engine == "instock-event-flow":
            market = parameters.get("market")
            symbols = [row.get("symbol") for row in evidence.get("symbol_summary") or []]
        else:
            market = parameters.get("market")
            symbols = [parameters.get("symbol")]
        if not market or not any(symbols): return {**ref, "state": "scope_unverified"}
        if market != item["market"]: return {**ref, "state": "market_mismatch"}
        if not any(self._same_security(symbol, item["symbol"], market) for symbol in symbols):
            return {**ref, "state": "security_mismatch"}
        if engine == "instock-industry-chain-research" and market == "CN":
            chain, limitations = resolve_industry_chain_snapshot(snapshot_id, symbol=item["symbol"], as_of=as_of)
            if "industry_chain_security_exposure_ambiguous" in limitations:
                return {**ref, "state": "scope_ambiguous"}
            if chain and chain.get("exposure") and chain.get("research_context"):
                # Only public relation identities; private saved reviews are fetched by Desk session later.
                ref["review_context"] = {"snapshot_id": snapshot_id,
                    "exposure": {"symbol": item["symbol"], "market": market},
                    "research_context": chain["research_context"]}
        ref["state"] = "resolved"
        if engine == "instock-stock-research-dossier":
            ref["research"] = {key: summary[key] for key in ("conclusion", "strengths", "tensions", "gaps", "invalidation_conditions") if key in summary}
            ref["research_details_complete"] = all(key in summary for key in ("conclusion", "gaps", "invalidation_conditions"))
        return ref

    def draft_from_dossier(self, snapshot_id, *, symbol, market="CN"):
        snapshot = get_analysis_snapshot_registry().get(snapshot_id)
        if not snapshot: raise ResearchBookError("公司档案快照不存在或已过期，请返回公司档案重新生成")
        if (snapshot.get("analysis") or {}).get("name") != "instock-stock-research-dossier":
            raise ResearchBookError("交接来源不是公司档案")
        as_of = (snapshot.get("data_window") or {}).get("end_date")
        reference = self._reference(snapshot_id, snapshot, {"symbol":symbol,"market":market}, as_of or "")
        if reference["state"] != "resolved": raise ResearchBookError("公司档案与请求证券、市场或日期不符")
        if not reference["research_details_complete"]: raise ResearchBookError("旧公司档案缺少完整交接字段，请重新生成")
        summary = snapshot["result"]["summary"]
        ids = list(dict.fromkeys(value for value in [snapshot_id, summary.get("event_flow_snapshot_id"), summary.get("industry_chain_snapshot_id")] if value))
        return {"as_of":as_of, "item":{"symbol":symbol, "market":market, "name":summary.get("name") or "",
            "sector":summary.get("sector") or "", "thesis":summary["conclusion"], "target_weight_pct":0,
            "invalidation":list(summary["invalidation_conditions"]), "risk_tags":list(dict.fromkeys([*summary.get("tensions", []), *summary["gaps"]])),
            "snapshot_ids":ids}, "boundary":"仅带入草稿，尚未加入或保存；加入并检查后，人工复核按当前运行模式单独读取，不混用本机与工作区记录。"}

    def _validate_packet(self, packet):
        if not isinstance(packet, Mapping):
            raise ResearchBookError("研究组合包必须是 JSON 对象")
        required = {"schema_version", "name", "as_of", "items"}
        missing, unknown = required - set(packet), set(packet) - required
        if missing:
            raise ResearchBookError(f"研究组合包缺少字段: {', '.join(sorted(missing))}")
        if unknown:
            raise ResearchBookError(f"研究组合包包含未知字段: {', '.join(sorted(unknown))}")
        if packet.get("schema_version") != self.packet_schema_version:
            raise ResearchBookError(f"schema_version 必须是 {self.packet_schema_version}")
        name = self._text(packet["name"], "name", 160)
        try:
            as_of = normalize_as_of(packet["as_of"], reject_future=True)
        except ValueError as exc:
            raise ResearchBookError(str(exc)) from exc
        items = packet.get("items")
        if not isinstance(items, list) or not 1 <= len(items) <= 100:
            raise ResearchBookError("items 数量必须在 1 到 100 之间")
        return {"name": name, "as_of": as_of, "items": items}

    def _parse_item(self, raw, index):
        context = f"items[{index}]"
        if not isinstance(raw, Mapping):
            raise ResearchBookError(f"{context} 必须是对象")
        required = {"symbol", "name", "market", "sector", "target_weight_pct", "thesis", "invalidation", "risk_tags", "snapshot_ids"}
        missing, unknown = required - set(raw), set(raw) - required - {"research_origin"}
        if missing:
            raise ResearchBookError(f"{context} 缺少字段: {', '.join(sorted(missing))}")
        if unknown:
            raise ResearchBookError(f"{context} 包含未知字段: {', '.join(sorted(unknown))}")
        symbol = str(raw["symbol"] or "").strip().upper()
        if not self.symbol_pattern.fullmatch(symbol):
            raise ResearchBookError(f"{context}.symbol 格式无效")
        market = str(raw["market"] or "").strip().upper()
        if market not in self.supported_markets:
            raise ResearchBookError(f"{context}.market 仅支持 CN、HK、US、GLOBAL")
        try:
            weight = float(raw["target_weight_pct"])
        except (TypeError, ValueError) as exc:
            raise ResearchBookError(f"{context}.target_weight_pct 必须是数字") from exc
        if not math.isfinite(weight) or not 0 <= weight <= 100:
            raise ResearchBookError(f"{context}.target_weight_pct 必须在 0..100 之间")
        invalidation = self._text_list(raw["invalidation"], f"{context}.invalidation", 1, 20)
        risks = self._text_list(raw["risk_tags"], f"{context}.risk_tags", 0, 20)
        snapshot_ids = self._text_list(raw["snapshot_ids"], f"{context}.snapshot_ids", 0, 10)
        item = {"symbol": symbol, "name": self._text(raw["name"], f"{context}.name", 120), "market": market, "sector": self._text(raw["sector"], f"{context}.sector", 120), "target_weight_pct": round(weight, 2), "thesis": self._text(raw["thesis"], f"{context}.thesis", 800), "invalidation": invalidation, "risk_tags": risks, "snapshot_ids": snapshot_ids}
        if "research_origin" in raw:
            origin = raw["research_origin"]
            keys = {"researchOriginId", "originUserId", "originWorkspaceId", "snapshotId"}
            if not isinstance(origin, Mapping) or set(origin) != keys or any(not isinstance(origin[key], str) or not origin[key].strip() or len(origin[key]) > 128 for key in keys):
                raise ResearchBookError(f"{context}.research_origin 只能包含完整的记录标识、归属和来源快照编号，不能包含原文")
            if not re.fullmatch(r"[a-f0-9]{32}", origin["researchOriginId"]) or origin["snapshotId"] not in snapshot_ids:
                raise ResearchBookError(f"{context}.research_origin 标识无效或未关联对应来源快照")
            # A locator is not an authorization or a verified research claim.
            # Its contents are fetched separately with the current Desk session.
            item["research_origin"] = dict(origin)
        return item

    @staticmethod
    def _exposures(items):
        sectors, risks = {}, {}
        for item in items:
            sectors[item["sector"]] = sectors.get(item["sector"], 0.0) + item["target_weight_pct"]
            for risk in item["risk_tags"]:
                risks[risk] = risks.get(risk, 0.0) + item["target_weight_pct"]
        normalize = lambda values: [{"name": name, "weight_pct": round(weight, 2)} for name, weight in sorted(values.items(), key=lambda pair: (-pair[1], pair[0]))]
        return {"sectors": normalize(sectors), "risks": normalize(risks), "top_position_weight_pct": max((item["target_weight_pct"] for item in items), default=0.0)}

    def _build_snapshot(self, packet, result, limitations):
        input_digest, result_digest = self._digest(packet), self._digest(result)
        snapshot_hash = self._digest({"analysis": self.engine_name, "version": self.engine_version, "as_of": packet["as_of"], "input": input_digest, "result": result_digest}).split(":", 1)[1]
        lag_days = max((date.today() - pd.Timestamp(packet["as_of"]).date()).days, 0)
        return {"schema_version": SNAPSHOT_SCHEMA_VERSION, "snapshot_id": f"{self.engine_name}:{snapshot_hash[:24]}", "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"), "analysis": {"name": self.engine_name, "version": self.engine_version}, "parameters": {"name": packet["name"], "asOf": packet["as_of"]}, "data_window": {"requested_as_of": packet["as_of"], "start_date": None, "end_date": packet["as_of"], "coverage": result["summary"]["data_state"]}, "provenance": {"provider": "newma-desk-context", "endpoint": "host-action-input", "upstream_source": "structured-research-book-packet", "upstream_as_of": packet["as_of"], "limitations": limitations}, "freshness": {"state": "current" if lag_days <= 3 else "historical", "resolution": "point_in_time", "calendar_lag_days": lag_days}, "input": {"digest": input_digest, "summary": {"name": packet["name"], "items": len(packet["items"])}}, "result": {"digest": result_digest, "summary": result["summary"]}}

    @staticmethod
    def _text(value: Any, context: str, maximum: int) -> str:
        text = str(value or "").strip()
        if not text:
            raise ResearchBookError(f"{context} 不能为空")
        if len(text) > maximum:
            raise ResearchBookError(f"{context} 长度不能超过 {maximum}")
        return text

    @classmethod
    def _text_list(cls, value, context, minimum, maximum):
        if not isinstance(value, list) or not minimum <= len(value) <= maximum:
            raise ResearchBookError(f"{context} 数量必须在 {minimum}..{maximum} 之间")
        output = []
        for index, item in enumerate(value):
            text = cls._text(item, f"{context}[{index}]", 300)
            if text not in output:
                output.append(text)
        return output

    @staticmethod
    def _digest(value: Any) -> str:
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
