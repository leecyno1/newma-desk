from __future__ import annotations

from typing import Any, Dict, List, Optional


FALLBACK_KEY_MAP = {
    "market_html": ("market", "html"),
    "market_markdown": ("market", "markdown"),
    "market_json": ("market", "json"),
    "meetings_html": ("meetings", "html"),
    "meetings_markdown": ("meetings", "markdown"),
    "meetings_json": ("meetings", "json"),
    "counter_html": ("counter", "html"),
    "counter_markdown": ("counter", "markdown"),
    "counter_json": ("counter", "json"),
    "top_contacts_html": ("contacts", "html"),
    "top_contacts_markdown": ("contacts", "markdown"),
    "contacts_html": ("contacts", "html"),
    "contacts_markdown": ("contacts", "markdown"),
    "contacts_csv": ("contacts", "csv"),
    "contacts_json": ("contacts", "json"),
}


class ArtifactPayload(Dict[str, Any]):
    """Typed dict-like container to describe a ReportArtifact."""


def _clean_content(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return None
    text = str(value).strip()
    return text or None


def _clean_json(value: Any) -> Optional[Dict[str, Any]]:
    if isinstance(value, dict):
        return value
    return None


def _module_title(module: str) -> str:
    titles = {
        "market": "市场观点总结",
        "meetings": "会议路演信息",
    "counter": "分歧观点分析",
        "contacts": "高评分分析师摘要",
        "legacy": "原始报告结果",
    }
    return titles.get(module, module.title())


def build_artifact_payloads(result: Dict[str, Any]) -> List[ArtifactPayload]:
    payloads: List[ArtifactPayload] = []

    def append_payload(module: str, content_type: Optional[str], data_text: Optional[str],
                       data_json: Optional[Dict[str, Any]], meta: Optional[Dict[str, Any]],
                       title: Optional[str], sequence: int) -> None:
        if not (data_text or data_json):
            return
        payloads.append(
            ArtifactPayload(
                module=module,
                content_type=content_type,
                data_text=data_text,
                data_json=data_json,
                meta=meta,
                title=title or _module_title(module),
                sequence=sequence,
            )
        )

    sequence = 0

    def parse_modules(modules: Any) -> None:
        nonlocal sequence
        if not isinstance(modules, list):
            return
        for idx, module in enumerate(modules):
            if not isinstance(module, dict):
                continue
            module_name = str(
                module.get("module")
                or module.get("name")
                or module.get("key")
                or f"module_{sequence}"
            ).strip()
            if not module_name:
                module_name = f"module_{sequence}"
            content_type = module.get("content_type") or module.get("format")
            data_text = (
                _clean_content(module.get("html"))
                or _clean_content(module.get("markdown"))
                or _clean_content(module.get("text"))
            )
            data_json = _clean_json(module.get("json") or module.get("data"))
            meta = module.get("meta") if isinstance(module.get("meta"), dict) else None
            title = module.get("title") if isinstance(module.get("title"), str) else None
            append_payload(module_name, content_type, data_text, data_json, meta, title, sequence)
            sequence += 1

    # check structured modules in different places
    parse_modules(result.get("modules"))
    report_block = result.get("report")
    if isinstance(report_block, dict):
        parse_modules(report_block.get("modules"))

    # fallback to known keys if no structured modules
    if not payloads:
        containers = [result]
        if isinstance(report_block, dict):
            containers.append(report_block)
        for container in containers:
            if not isinstance(container, dict):
                continue
            for key, value in container.items():
                if key not in FALLBACK_KEY_MAP:
                    continue
                module, content_type = FALLBACK_KEY_MAP[key]
                data_text = None
                data_json = None
                if content_type == "json":
                    if isinstance(value, dict):
                        data_json = value
                elif content_type == "csv":
                    data_text = _clean_content(value)
                else:
                    data_text = _clean_content(value)
                if not (data_text or data_json):
                    continue
                append_payload(module, content_type, data_text, data_json, {"source_key": key}, None, sequence)
                sequence += 1

    # ensure at least legacy html captured if available
    if not payloads and isinstance(report_block, dict):
        legacy_html = _clean_content(report_block.get("html"))
        legacy_md = _clean_content(report_block.get("markdown"))
        if legacy_html or legacy_md:
            content_type = "html" if legacy_html else "markdown"
            append_payload("legacy", content_type, legacy_html or legacy_md, None, None, None, sequence)

    return payloads


__all__ = ["build_artifact_payloads", "ArtifactPayload"]
