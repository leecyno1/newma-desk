"""Evidence-bound LLM metadata extraction for local research memos."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional


class ResearchMemoMetadataExtractor:
    FIELD_KINDS = {
        "manager_names": "manager",
        "fund_ids": "fund",
        "classifications": "classification",
        "style_labels": "style_label",
    }

    def __init__(self, generator: Optional[Any] = None):
        self.generator = generator

    def extract(self, content: str, filename: str) -> Dict[str, Any]:
        if not self.generator:
            return {"status": "unavailable", "provider": None, "model": None, "proposals": []}
        try:
            raw = self.generator.extract_research_memo_metadata(content, filename)
            data = self._parse_json(raw)
            proposals = self._validated_proposals(data, content)
            return {
                "status": "complete",
                "provider": getattr(self.generator, "provider", None),
                "model": getattr(self.generator, "model", None),
                "proposals": proposals,
            }
        except Exception as exc:
            return {
                "status": "failed",
                "provider": getattr(self.generator, "provider", None),
                "model": getattr(self.generator, "model", None),
                "proposals": [],
                "error": str(exc),
            }

    @staticmethod
    def _parse_json(raw: Any) -> Dict[str, Any]:
        expected_fields = set(ResearchMemoMetadataExtractor.FIELD_KINDS)

        def unwrap(value: Any) -> Optional[Dict[str, Any]]:
            if isinstance(value, dict):
                if expected_fields.intersection(value):
                    return value
                for key in ("result", "output", "data", "content", "text"):
                    if key in value and (nested := unwrap(value[key])) is not None:
                        return nested
                return None
            if isinstance(value, list):
                for item in value:
                    if (nested := unwrap(item)) is not None:
                        return nested
                return None
            if isinstance(value, str):
                return decode_text(value)
            return None

        def decode_text(text: str) -> Optional[Dict[str, Any]]:
            cleaned = str(text or "").strip()
            if not cleaned:
                return None
            candidates = [
                match.group(1).strip()
                for match in re.finditer(r"```(?:json)?\s*([\s\S]*?)```", cleaned, re.IGNORECASE)
            ]
            candidates.append(cleaned)
            decoder = json.JSONDecoder()
            for candidate in candidates:
                try:
                    parsed = json.loads(candidate)
                except json.JSONDecodeError:
                    parsed = None
                if parsed is not None and (unwrapped := unwrap(parsed)) is not None:
                    return unwrapped
                for index, character in enumerate(candidate):
                    if character not in "{[":
                        continue
                    try:
                        parsed, _ = decoder.raw_decode(candidate[index:])
                    except json.JSONDecodeError:
                        continue
                    if (unwrapped := unwrap(parsed)) is not None:
                        return unwrapped
            return None

        parsed = unwrap(raw)
        if parsed is None:
            raise ValueError("模型没有返回可用的 JSON 对象")
        return parsed

    def _validated_proposals(self, data: Dict[str, Any], content: str) -> List[Dict[str, Any]]:
        proposals: List[Dict[str, Any]] = []
        seen = set()
        for field, kind in self.FIELD_KINDS.items():
            items = data.get(field, [])
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                value = str(item.get("value") or "").strip()[:120]
                excerpt = re.sub(r"\s+", " ", str(item.get("excerpt") or "")).strip()[:240]
                normalized_content = re.sub(r"\s+", " ", content)
                if not value or not excerpt or excerpt not in normalized_content:
                    continue
                if kind == "fund" and not re.fullmatch(r"\d{6}\.(?:OF|SH|SZ|BJ|HK)", value.upper()):
                    continue
                if kind == "fund":
                    value = value.upper()
                try:
                    confidence = min(1.0, max(0.0, float(item.get("confidence", 0))))
                except (TypeError, ValueError):
                    continue
                identity = (kind, value)
                if identity in seen:
                    continue
                seen.add(identity)
                proposals.append({
                    "kind": kind,
                    "value": value,
                    "confidence": confidence,
                    "excerpt": excerpt,
                    "extraction_source": "llm",
                })
        return proposals


def get_research_memo_metadata_extractor() -> ResearchMemoMetadataExtractor:
    try:
        from services.ai_report import get_report_generator

        generator = get_report_generator()
        return ResearchMemoMetadataExtractor(generator=generator)
    except Exception:
        return ResearchMemoMetadataExtractor(generator=None)
