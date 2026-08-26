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


class ResearchBookError(ValueError):
    """Raised when a research-book packet violates its contract."""


class ResearchBookEngine:
    engine_name = "instock-research-book"
    engine_version = "1.0.0"
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
                if snapshot is None:
                    missing_count += 1
                    references.append({"snapshot_id": snapshot_id, "state": "missing"})
                else:
                    resolved_count += 1
                    references.append({"snapshot_id": snapshot_id, "state": "resolved", "analysis": dict(snapshot.get("analysis") or {}), "freshness": dict(snapshot.get("freshness") or {})})
            item["snapshot_references"] = references
            item["snapshot_coverage"] = "complete" if references and all(ref["state"] == "resolved" for ref in references) else "missing" if references else "none"
        exposures = self._exposures(items)
        warnings = []
        for item in items:
            if item["target_weight_pct"] > 20:
                warnings.append(f"position_concentration:{item['symbol']}")
            if item["snapshot_coverage"] != "complete":
                warnings.append(f"snapshot_coverage:{item['symbol']}:{item['snapshot_coverage']}")
        for sector in exposures["sectors"]:
            if sector["weight_pct"] > 40:
                warnings.append(f"sector_concentration:{sector['name']}")
        data_state = "partial" if missing_count or any(item["snapshot_coverage"] == "none" for item in items) else "complete"
        summary = {"items": len(items), "total_target_weight_pct": total_weight, "cash_weight_pct": round(100 - total_weight, 2), "resolved_snapshots": resolved_count, "missing_snapshots": missing_count, "data_state": data_state}
        limitations = ["research_book_is_not_persisted_by_this_runtime", "research_book_contains_no_order_or_execution_actions", "target_weights_are_research_exposure_not_portfolio_advice"]
        stable_result = {"summary": summary, "items": items, "exposures": exposures, "warnings": warnings}
        snapshot = self._build_snapshot(payload, stable_result, limitations)
        registry.register(snapshot)
        return {"engine": {"name": self.engine_name, "version": self.engine_version}, "schema_version": self.packet_schema_version, "name": payload["name"], "as_of": payload["as_of"], "data_source": "newma-desk-context", "data_state": data_state, "summary": summary, "items": items, "exposures": exposures, "warnings": warnings, "limitations": limitations, "snapshot": snapshot}

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
        missing, unknown = required - set(raw), set(raw) - required
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
        return {"symbol": symbol, "name": self._text(raw["name"], f"{context}.name", 120), "market": market, "sector": self._text(raw["sector"], f"{context}.sector", 120), "target_weight_pct": round(weight, 2), "thesis": self._text(raw["thesis"], f"{context}.thesis", 800), "invalidation": invalidation, "risk_tags": risks, "snapshot_ids": snapshot_ids}

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
