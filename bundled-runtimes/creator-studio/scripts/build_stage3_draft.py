#!/usr/bin/env python3

from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from canonical_workflow import ensure_pending_gate_file, ensure_runtime_output_dir
from draft_html_pack import write_draft_html_from_markdown
from finance_data_adapter import build_finance_chart_specs_with_report
from provider_registry import extract_chat_content, resolve_chat_provider
from path_config import get_project_root, get_stage_dir


ROOT = get_project_root()
DEFAULT_DRAFT_MIN_CJK_CHARS = 10000
DEFAULT_DRAFT_QUALITY_FLOOR_CJK_CHARS = 10000
DEFAULT_MAX_PRIMARY_SECTIONS = 8


def slugify(text: str) -> str:
    value = re.sub(r"[^0-9A-Za-z\u4e00-\u9fa5]+", "-", text or "").strip("-").lower()
    return value or "topic"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data.rstrip() + "\n", encoding="utf-8")


def unique_texts(values: list[Any] | None) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values or []:
        if isinstance(value, dict):
            text = value.get("chart_need") or value.get("description") or value.get("title") or value.get("name") or ""
        else:
            text = str(value or "")
        text = re.sub(r"\s+", " ", text).strip()
        if not text or text in seen or text == "无":
            continue
        seen.add(text)
        result.append(text)
    return result


def collect_chart_needs(card: dict[str, Any], reasoning: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    values.extend(card.get("chart_needs") or [])
    values.extend(card.get("recommended_data_angles") or [])
    for claim in reasoning.get("claims") or []:
        chart_need = claim.get("chart_need")
        if chart_need:
            values.append(f"{claim.get('claim_id')}｜{chart_need}")
    return unique_texts(values)


def collect_visual_needs(card: dict[str, Any], reasoning: dict[str, Any]) -> list[str]:
    values: list[Any] = []
    values.extend(card.get("recommended_visual_angles") or [])
    values.extend(card.get("question_units") or [])
    values.extend(card.get("case_units") or [])
    for claim in reasoning.get("claims") or []:
        statement = claim.get("statement")
        if statement:
            values.append(f"{claim.get('claim_id')}｜{statement}")
    return unique_texts(values)


LEMON_ILLUSTRATION_TRIGGERS = {
    "example": re.compile(r"(?:比如|例如|举个例子|举例来说|假设一下|想象一下|试想|打个比方)"),
    "metaphor": re.compile(r"(?:就像|好比|仿佛|如同|可以把.+?看[作成]|把.+?比作|这就像)"),
    "financial_metaphor": re.compile(
        r"(?:抽血|虹吸|踩刹车|开闸|蓄水池|地心引力|安全绳|接力|吞噬|黑洞|跷跷板|温度计|发动机|传送带|漏斗|闸门)"
    ),
}


def detect_lemon_illustration_intents(text: str, max_intents: int = 8) -> list[dict[str, Any]]:
    """Find explicit metaphor/example beats for later Agent enrichment and generation."""
    if not text:
        return []
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    chunks = re.split(r"(?<=[。！？!?])\s*|\n+", text)
    for raw in chunks:
        sentence = re.sub(r"\s+", " ", raw).strip(" #-*\t")
        if len(sentence) < 8 or len(sentence) > 260 or sentence.startswith(("{{", "|")):
            continue
        matched_type = None
        matched_terms: list[str] = []
        for trigger_type, pattern in LEMON_ILLUSTRATION_TRIGGERS.items():
            terms = pattern.findall(sentence)
            if terms:
                matched_type = trigger_type
                matched_terms = [str(term) for term in terms]
                break
        if not matched_type:
            continue
        signature = re.sub(r"\W+", "", sentence)
        if not signature or signature in seen:
            continue
        seen.add(signature)
        index = len(candidates) + 1
        candidates.append(
            {
                "intent_id": f"lemon-illustration-{index:02d}",
                "trigger_type": matched_type,
                "trigger_terms": matched_terms,
                "source_text": sentence,
                "core_meaning": "",
                "visual_metaphor_brief": "",
                "character_action": "",
                "skill": "dasheng-lemon-illustrations",
                "evidence_authenticity": "schematic",
                "status": "triggered_pending_agent_enrichment",
                "required": matched_type in {"example", "metaphor"},
                "channel_adaptation": {
                    "wechat_article": {
                        "mode": "full_canvas",
                        "placement": "after_source_paragraph",
                    },
                    "talking_head_video": {
                        "mode": "transparent_overlay_or_full_canvas",
                        "motion": "setup_action_result",
                    },
                    "explainer_html_video": {
                        "mode": "full_canvas",
                        "motion": "setup_action_result",
                    },
                    "vox_explainer_video": {
                        "mode": "editorial_schematic_or_transparent_overlay",
                        "motion": "setup_action_result",
                    },
                    "digital_human_video": {
                        "mode": "evidence_fullscreen_or_presenter_overlay",
                        "motion": "setup_action_result",
                    },
                    "commercial_promo_video": {
                        "mode": "brand_concept_or_product_proof",
                        "motion": "hook_reveal_proof_cta",
                    },
                    "cinematic_short_drama_video": {
                        "mode": "planning_reference_only",
                        "motion": "director_decides_after_activation",
                    },
                },
            }
        )
        if len(candidates) >= max_intents:
            break
    return candidates


def merge_illustration_intents(*groups: Any) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        if not isinstance(group, list):
            continue
        for raw in group:
            if not isinstance(raw, dict):
                continue
            signature = str(raw.get("intent_id") or raw.get("source_text") or "").strip()
            if not signature or signature in seen:
                continue
            seen.add(signature)
            merged.append(raw)
    return merged


def load_asset_specs(path: Path | None) -> dict[str, dict[str, Any]]:
    if not path:
        return {}
    payload = read_json(path)
    if isinstance(payload, list):
        return {str(item.get("topic_id")): item for item in payload if isinstance(item, dict) and item.get("topic_id")}
    if isinstance(payload, dict) and isinstance(payload.get("topics"), list):
        return {
            str(item.get("topic_id")): item
            for item in payload.get("topics", [])
            if isinstance(item, dict) and item.get("topic_id")
        }
    if isinstance(payload, dict) and isinstance(payload.get("drafts"), list):
        return {
            str(item.get("topic_id")): item
            for item in payload.get("drafts", [])
            if isinstance(item, dict) and item.get("topic_id")
        }
    if isinstance(payload, dict):
        return {str(key): value for key, value in payload.items() if isinstance(value, dict)}
    return {}


def resolve_asset_specs(
    card: dict[str, Any],
    reasoning: dict[str, Any],
    external_asset_specs: dict[str, dict[str, Any]] | None = None,
    draft_text: str | None = None,
) -> dict[str, Any]:
    topic_id = str(card.get("topic_id") or reasoning.get("topic_id"))
    external = (external_asset_specs or {}).get(topic_id) or {}
    chart_requests = collect_chart_needs(card, reasoning)
    image_requests = collect_visual_needs(card, reasoning)
    chart_specs = (
        external.get("chart_specs")
        or external.get("charts")
        or card.get("chart_specs")
        or card.get("draft_chart_specs")
        or []
    )
    finance_chart_requests = (
        external.get("finance_chart_requests")
        or external.get("market_data_requests")
        or external.get("data_requests")
        or card.get("finance_chart_requests")
        or card.get("market_data_requests")
        or card.get("data_requests")
        or []
    )
    image_specs = (
        external.get("image_specs")
        or external.get("images")
        or card.get("image_specs")
        or card.get("draft_image_specs")
        or []
    )
    illustration_specs = (
        external.get("illustration_specs")
        or external.get("comic_specs")
        or card.get("illustration_specs")
        or card.get("lemon_illustration_specs")
        or []
    )
    illustration_intents = merge_illustration_intents(
        external.get("illustration_intents"),
        card.get("illustration_intents"),
        detect_lemon_illustration_intents(draft_text or ""),
    )
    chart_specs = chart_specs if isinstance(chart_specs, list) else []
    finance_chart_requests = finance_chart_requests if isinstance(finance_chart_requests, list) else []
    finance_report = build_finance_chart_specs_with_report(finance_chart_requests)
    finance_chart_specs = finance_report.get("chart_specs") or []
    finance_failures = finance_report.get("failures") or []
    data_validation = finance_report.get("validation_report") or {}
    chart_specs = chart_specs + finance_chart_specs
    image_specs = image_specs if isinstance(image_specs, list) else []
    illustration_specs = illustration_specs if isinstance(illustration_specs, list) else []
    image_specs = image_specs + illustration_specs
    resolved_intent_ids = {
        str(spec.get("intent_id"))
        for spec in illustration_specs
        if isinstance(spec, dict) and spec.get("intent_id")
    }
    unresolved_illustration_intents = [
        intent
        for intent in illustration_intents
        if intent.get("required") and str(intent.get("intent_id")) not in resolved_intent_ids
    ]
    missing = []
    if (chart_requests or finance_chart_requests) and not chart_specs:
        missing.append("chart_specs")
    if finance_failures:
        missing.append("finance_chart_specs")
    if image_requests and not image_specs:
        missing.append("image_specs")
    if unresolved_illustration_intents:
        missing.append("illustration_specs")
    return {
        "chart_requests": chart_requests,
        "image_requests": image_requests,
        "chart_specs": chart_specs,
        "finance_chart_requests": finance_chart_requests,
        "finance_chart_failures": finance_failures,
        "data_validation": data_validation,
        "image_specs": image_specs,
        "illustration_intents": illustration_intents,
        "illustration_specs": illustration_specs,
        "unresolved_illustration_intents": unresolved_illustration_intents,
        "illustration_status": "complete" if not unresolved_illustration_intents else "pending_agent_generation",
        "asset_status": "complete" if not missing else "incomplete",
        "asset_missing": sorted(set(missing)),
    }


def resolve_draft_ai_config() -> dict[str, str] | None:
    return resolve_chat_provider(
        custom_env_var="DASHENG_DRAFT_PROVIDER_ENV",
        base_url_keys=["PHASE3_AI_BASE_URL", "DRAFT_AI_BASE_URL", "QHAIGC_BASE_URL"],
        api_key_keys=["PHASE3_AI_API_KEY", "DRAFT_AI_API_KEY", "QHAIGC_API_KEY"],
        model_keys=["PHASE3_AI_MODEL", "DRAFT_AI_MODEL", "PHASE2_AI_MODEL"],
        timeout_keys=["PHASE3_AI_TIMEOUT_SECONDS", "DRAFT_AI_TIMEOUT_SECONDS"],
        default_model="gpt-4.1-mini",
        default_timeout_seconds="180",
    )


def request_ai_markdown(system_prompt: str, user_prompt: str, *, max_tokens: int = 9000) -> str:
    fake_response_file = (os.environ.get("DASHENG_DRAFT_FAKE_RESPONSE_FILE") or "").strip()
    if fake_response_file:
        return Path(fake_response_file).expanduser().resolve().read_text(encoding="utf-8")
    fake_response = os.environ.get("DASHENG_DRAFT_FAKE_RESPONSE")
    if fake_response:
        return fake_response

    # === Priority 1: Local CLI Agent ===
    cli_result = _try_cli_agent(system_prompt, user_prompt)
    if cli_result is not None:
        return cli_result

    # === Priority 2: HTTP AI API (fallback) ===
    config = resolve_draft_ai_config()
    if not config:
        raise RuntimeError("未找到可用的本地 CLI Agent 且 Draft AI API 配置缺失。请安装 claude/codex/gemini CLI 或配置 QHAIGC_BASE_URL。")
    body = {
        "model": config["model"],
        "temperature": 0.4,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    api_key = config['api_key']
    req = urllib_request.Request(
        config["base_url"],
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib_request.urlopen(req, timeout=float(config["timeout_seconds"])) as resp:
                response_payload = json.loads(resp.read().decode("utf-8"))
            content = extract_chat_content(response_payload)
            if content:
                return content
            raise RuntimeError("AI 返回空内容")
        except (
            urllib_error.URLError,
            urllib_error.HTTPError,
            TimeoutError,
            json.JSONDecodeError,
            ValueError,
            http.client.RemoteDisconnected,
            RuntimeError,
        ) as exc:
            last_error = exc
            if attempt >= 2:
                break
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Draft AI 调用失败：{last_error}")


# --- Local CLI Agent integration ---

_CLI_AGENT_PRIORITY = ["qoder-cli", "claude", "codex", "gemini", "qwen"]

_CLI_DEFINITIONS: dict[str, dict[str, Any]] = {
    "qoder-cli": {"binary": "qodercli", "args": ["-p"], "prompt_via_stdin": False, "prompt_as_last_arg": True, "clean_env": True},
    "claude": {"binary": "claude", "args": ["--print"], "prompt_via_stdin": True},
    "codex": {"binary": "codex", "args": ["exec", "--skip-git-repo-check"], "prompt_via_stdin": True},
    "gemini": {"binary": "gemini", "args": [], "prompt_via_stdin": True},
    "qwen": {"binary": "qwen", "args": [], "prompt_via_stdin": True},
}


def _clean_agent_env() -> dict[str, str]:
    """Return env with ALL QODER_*/QODERCN_*/QODERWORK_* vars stripped so CLI runs in normal mode."""
    env = os.environ.copy()
    for k in list(env.keys()):
        if k.startswith("QODER_") or k.startswith("QODERCN_") or k.startswith("QODERWORK_"):
            env.pop(k, None)
    return env


def _try_cli_agent(system_prompt: str, user_prompt: str) -> str | None:
    """Try to invoke a local CLI agent. Returns generated text or None if no CLI available."""
    explicit_agent = (os.environ.get("DRAFT_CLI_AGENT") or "").strip()
    agents_to_try = [explicit_agent] if explicit_agent else _CLI_AGENT_PRIORITY

    for agent_id in agents_to_try:
        definition = _CLI_DEFINITIONS.get(agent_id)
        if not definition:
            continue
        binary = shutil.which(definition["binary"])
        if not binary:
            continue

        # Build combined prompt
        full_prompt = f"{system_prompt}\n\n---\n\n{user_prompt}\n\n---\n请直接输出 Markdown 正文，不要输出任何解释或元信息。"

        timeout = int(os.environ.get("DRAFT_CLI_TIMEOUT", "300"))
        args = [binary, *definition.get("args", [])]
        input_text = full_prompt if definition.get("prompt_via_stdin") else None
        if definition.get("prompt_as_last_arg"):
            args.append(full_prompt)

        env = _clean_agent_env() if definition.get("clean_env") else None

        try:
            result = subprocess.run(
                args,
                input=input_text,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
                cwd=str(ROOT),
                env=env,
            )
            if result.returncode == 0 and result.stdout.strip():
                print(f"[Draft] 使用本地 CLI: {agent_id} ({binary})", file=sys.stderr)
                return result.stdout.strip()
            # Non-zero exit or empty output — try next agent
            if explicit_agent:
                raise RuntimeError(f"CLI {agent_id} 失败 (exit={result.returncode}): {result.stderr[:200]}")
        except subprocess.TimeoutExpired:
            if explicit_agent:
                raise RuntimeError(f"CLI {agent_id} 超时 ({timeout}s)")
            continue
        except OSError:
            continue

    return None


def count_cjk_chars(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", text or ""))


def draft_min_chars(card: dict[str, Any]) -> int:
    configured = int((card.get("draft_contract") or {}).get("target_cjk_chars_min") or DEFAULT_DRAFT_MIN_CJK_CHARS)
    return max(DEFAULT_DRAFT_MIN_CJK_CHARS, configured)


def draft_quality_floor(card: dict[str, Any]) -> int:
    configured = int(
        (card.get("draft_contract") or {}).get("quality_floor_cjk_chars")
        or DEFAULT_DRAFT_QUALITY_FLOOR_CJK_CHARS
    )
    return max(DEFAULT_DRAFT_QUALITY_FLOOR_CJK_CHARS, configured)


AI_CLICHE_PATTERNS = [
    {
        "pattern_id": "not_but",
        "label": "不是……而是……",
        "regex": r"不是[^。！？\n]{0,32}而是",
        "severity": "warning",
        "guidance": "少用这种二元对立句式；改成直接陈述判断，或拆成两句具体事实。",
    },
    {
        "pattern_id": "this_means",
        "label": "这意味着",
        "regex": r"这意味着",
        "severity": "warning",
        "guidance": "少用抽象转译句；直接写出具体影响、传导链条或读者该看的变量。",
    },
    {
        "pattern_id": "essentially",
        "label": "本质上",
        "regex": r"本质上",
        "severity": "warning",
        "guidance": "除非后面给出可验证机制，否则改成更具体的机制描述。",
    },
    {
        "pattern_id": "undeniable",
        "label": "不可否认",
        "regex": r"不可否认",
        "severity": "warning",
        "guidance": "这是典型套话开头；删掉，直接给事实或判断。",
    },
    {
        "pattern_id": "in_summary",
        "label": "综上所述",
        "regex": r"综上所述",
        "severity": "warning",
        "guidance": "公众号长文里少用论文式收束；用一个更具体的回扣句替代。",
    },
]


def inspect_draft_quality(draft: str, card: dict[str, Any], reasoning: dict[str, Any]) -> dict[str, Any]:
    hits = []
    for pattern in AI_CLICHE_PATTERNS:
        matches = list(re.finditer(pattern["regex"], draft or ""))
        if not matches:
            continue
        examples = []
        for match in matches[:3]:
            start = max(0, match.start() - 12)
            end = min(len(draft), match.end() + 24)
            examples.append(re.sub(r"\s+", " ", draft[start:end]).strip())
        hits.append(
            {
                "pattern_id": pattern["pattern_id"],
                "label": pattern["label"],
                "severity": pattern["severity"],
                "count": len(matches),
                "examples": examples,
                "guidance": pattern["guidance"],
            }
        )
    h2_count = len(re.findall(r"^##\s+", draft or "", flags=re.M))
    cjk_chars = count_cjk_chars(draft)
    claim_count = len(reasoning.get("claims") or [])
    has_reference_section = "引用与待补源" in (draft or "")
    status = "warning" if hits else "pass"
    draft_contract = card.get("draft_contract") or {}
    quality_floor = draft_quality_floor(card)
    max_primary_sections = int(draft_contract.get("max_primary_sections") or DEFAULT_MAX_PRIMARY_SECTIONS)
    max_h2_count = max_primary_sections + (1 if has_reference_section else 0)
    if cjk_chars < quality_floor or h2_count > max_h2_count:
        status = "warning"
    return {
        "topic_id": card.get("topic_id"),
        "title": card.get("title"),
        "status": status,
        "cjk_chars": cjk_chars,
        "h2_count": h2_count,
        "claim_count": claim_count,
        "has_reference_section": has_reference_section,
        "max_primary_sections": max_primary_sections,
        "max_h2_count": max_h2_count,
        "ai_cliche_hits": hits,
        "checks": {
            "length_floor_10000": cjk_chars >= quality_floor,
            "primary_sections_within_contract": h2_count <= max_h2_count,
            "reference_section_present": has_reference_section,
            "style_polish_disabled": (draft_contract.get("style_polish") is False),
        },
    }


def build_ai_draft_prompts(card: dict[str, Any], reasoning: dict[str, Any]) -> tuple[str, str]:
    evidence_lines = "\n".join(
        f"- {item.get('title', '')}｜{item.get('url', '')}"
        for item in card.get("existing_evidence", [])[:20]
    ) or "- 暂无已匹配证据"
    proof_lines = "\n".join(f"- {item}" for item in card.get("proof_requirements", [])) or "- 暂无"
    data_angle_lines = "\n".join(f"- {item}" for item in card.get("recommended_data_angles", [])) or "- 暂无"
    visual_angle_lines = "\n".join(f"- {item}" for item in card.get("recommended_visual_angles", [])) or "- 暂无"
    question_unit_lines = "\n".join(f"- {item}" for item in card.get("question_units", [])) or "- 暂无"
    opinion_unit_lines = "\n".join(f"- {item}" for item in card.get("opinion_units", [])) or "- 暂无"
    case_unit_lines = "\n".join(f"- {item}" for item in card.get("case_units", [])) or "- 暂无"
    solution_unit_lines = "\n".join(f"- {item}" for item in card.get("solution_units", [])) or "- 暂无"

    claim_list = []
    for claim in reasoning.get("claims", []):
        section_id = claim['section_id']
        statement = claim['statement']
        chart_need = claim.get('chart_need') or '无'
        missing_proof = claim.get('missing_proof') or ['无']
        missing_str = '；'.join(missing_proof)
        claim_list.append(f"- {section_id}｜判断：{statement}｜建议图表：{chart_need}｜待补证明：{missing_str}")
    claim_lines = "\n".join(claim_list)
    system_prompt = (
        "你是资深财经、产业与宏观研究员。"
        "你的任务是基于选题卡和 Reasoning Sheet 写出供后续编辑使用的分析底稿。"
        "Draft 阶段不做 DNA 模仿、文风修饰、平台化包装、传播节奏设计或情绪渲染。"
        "重点生产事实陈述、数据材料、概念界定、机制分析、正反论证、反驳、情景推演和明确结论。"
        "必须区分已核验事实、推理判断、情景假设和仍待补证据，不能把它们混写。"
        "禁止编造不存在的事实、机构表态、具体数字。"
        "允许根据上游判断做分析，但所有强事实都必须与已知证据兼容。"
    )
    title = card['title']
    core_prop = card.get('core_proposition') or card.get('core_thesis') or ''
    one_line = card.get('one_line_judgment') or ''
    why_now = card.get('why_now') or ''
    reader_payoff = card.get('reader_payoff') or ''
    article_use = card.get('article_use') or ''
    struct_hint = card.get("structure_hint") or {}
    # 兼容两种结构：旧版 {opening, part_1..3, ending} 与新版 {opening, body, ending}
    hint_opening = struct_hint.get('opening', '')
    if 'part_1' in struct_hint or 'part_2' in struct_hint or 'part_3' in struct_hint:
        hint_part1 = struct_hint.get('part_1', '')
        hint_part2 = struct_hint.get('part_2', '')
        hint_part3 = struct_hint.get('part_3', '')
    else:
        body_hint = struct_hint.get('body', '')
        hint_part1 = body_hint
        hint_part2 = body_hint
        hint_part3 = struct_hint.get('ending', '')
    hint_ending = struct_hint.get('ending', '')
    draft_contract = card.get("draft_contract") or {}
    primary_sections = draft_contract.get("primary_sections") or []
    target_min = draft_min_chars(card)
    if primary_sections:
        section_lines = "\n".join(
            f"{index}. {item.get('title', '')}：{item.get('brief', '')}"
            for index, item in enumerate(primary_sections, start=1)
            if isinstance(item, dict) and item.get("title")
        )
        structure_constraint = (
            "- 一级标题必须严格按以下章节各写一章；每章都要独立完成事实、机制或判断任务，不能把章节合并成几段摘要：\n"
            f"{section_lines}\n"
            f"- 除上述章节外，只保留一个 `## 引用与待补源`，不要另加一级标题。"
        )
    else:
        structure_constraint = f"- 一级标题总数最多 {int(draft_contract.get('max_primary_sections') or DEFAULT_MAX_PRIMARY_SECTIONS)} 个，另加引用与待补源。"

    # Build anchor examples (avoid f-string issues with double braces)
    anchor_section = """
【锚点标注要求】（重要）
在文章中需要配图、链接或引用的位置，必须使用以下标注格式：
- `{{image: 描述内容}}` — 配图占位符，例如：{{image: AI工作流架构对比图}}
- `{{chart: claim_id|图表描述|数据来源或待补来源}}` — 图表占位符，例如：{{chart: topic-a-claim-01|2018-2026房价与成交量对比|国家统计局}}
- `{{link: URL|显示文字}}` — 链接占位符，例如：{{link: https://example.com|相关报告}}
- `{{ref: 来源名称}}` — 参考文献标注，例如：{{ref: 麦肯锡AI报告2024}}

请在以下位置添加锚点标注：
- 每个一级标题（h2）下至少添加1个 {{image:}} 或 {{chart:}} 占位符，用于后续配图/图表
- 需要图表的位置必须绑定 claim_id；数据未核验时，把第三段写成“待补：来源/口径”，不要虚构数值
- 引用外部数据或观点时，使用 {{ref:}} 标注来源
- 提到具体案例或报告时，使用 {{link:}} 标注（如果有URL）

这些锚点标注会进入 Draft HTML 和 manifest，供编辑、发布或人工补证据时直接定位。
"""

    user_prompt = f"""请生成一篇标准初稿，要求如下：

【选题】
- 标题：{title}
- 主判断：{core_prop}
- 一句话判断：{one_line}
- 为什么现在值得写：{why_now}
- 读者收益：{reader_payoff}
- 文章用途：{article_use}

【结构约束】
- 必须遵从当前分析底稿框架，不得随意增删或合并约定章节。
{structure_constraint}
- 可以在一级标题下使用二级标题增强层次。
- 中文正文不得少于 {target_min} 个汉字，可以更长，不设上限。
- 这是研究分析底稿，不是平台改写稿；不要做 DNA、文风、标题党、金句或发布包装。

【结构提示】
- opening：{hint_opening}
- part_1：{hint_part1}
- part_2：{hint_part2}
- part_3：{hint_part3}
- ending：{hint_ending}

【论证骨架 / Claims】
{claim_lines}

【已知证据】
{evidence_lines}

【待补证明】
{proof_lines}

【建议数据角度】
{data_angle_lines}

【建议图表/配图角度】
{visual_angle_lines}

【Brief 内容单元】
- 问题单元：
{question_unit_lines}
- 观点单元：
{opinion_unit_lines}
- 案例单元：
{case_unit_lines}
- 方案单元：
{solution_unit_lines}

【写作要求】
1. 开篇先界定事件、问题和需要纠正的误判，不做情绪化钩子。
2. 正文按事实层 -> 概念与口径 -> 机制层 -> 正反论证 -> 情景推演 -> 判断与结论推进。
3. 每个核心判断都要给出数据、案例、可验证机制或明确的待补证据，不能用空话代替论证。
4. 已核验事实写明来源和日期；推理用“由此可推”“在这一假设下”等方式标明；无法核验的数字不得写成事实。
5. 主动写出反方观点、适用边界、可能失效的条件以及对反方的回应。
6. 不做文风修饰，不追求金句、节奏、口语感或平台传播效果；语言只需准确、清楚、可审核。
7. 表格只用于口径、价格、情景或指标比较，必须是标准 Markdown 表格。
8. 输出必须是完整 Markdown，直接从 `# 标题` 开始。
9. 文末加一个 `## 引用与待补源` 小节，分开列出已使用来源、待补数据和事实核验风险。
10. 少用 AI 味二元句式，尤其避免反复写“不是……而是……”“这意味着”“本质上”“不可否认”“综上所述”。
{anchor_section}
"""
    return system_prompt, user_prompt


def generate_ai_draft(card: dict[str, Any], reasoning: dict[str, Any]) -> str:
    agent_draft_dir = (os.environ.get("DASHENG_DRAFT_AGENT_DIR") or "").strip()
    if agent_draft_dir:
        agent_draft_file = Path(agent_draft_dir).expanduser().resolve() / f"{card['topic_id']}.md"
        if agent_draft_file.exists():
            draft = agent_draft_file.read_text(encoding="utf-8").strip()
            if count_cjk_chars(draft) < draft_quality_floor(card):
                raise RuntimeError(f"Agent 初稿长度不足：{count_cjk_chars(draft)} 字")
            return draft
    system_prompt, user_prompt = build_ai_draft_prompts(card, reasoning)
    draft_contract = card.get("draft_contract") or {}
    min_chars = draft_min_chars(card)
    draft = request_ai_markdown(system_prompt, user_prompt, max_tokens=24000).strip()
    if count_cjk_chars(draft) >= min_chars:
        return draft
    for attempt in range(2):
        expand_prompt = (
            user_prompt
            + "\n\n下面是上一版初稿，请你在保留标题、主判断和一级结构约束的前提下继续扩写。"
            "重点补足事实、数据口径、机制、正反论证、案例、情景和结论，避免空话，直接输出完整修订版 Markdown。\n\n"
            f"{draft}\n\n"
            f"扩写后正文至少达到 {min_chars} 字中文左右，仍然遵守上面的一级标题契约。"
        )
        draft = request_ai_markdown(system_prompt, expand_prompt, max_tokens=32000).strip()
        if count_cjk_chars(draft) >= min_chars:
            return draft
        time.sleep(1 + attempt)
    if count_cjk_chars(draft) < draft_quality_floor(card):
        raise RuntimeError(f"AI 初稿长度不足：{count_cjk_chars(draft)} 字")
    return draft


def infer_run_id(selected_topics: dict[str, Any], arg_run_id: str | None, selected_topics_file: Path) -> str:
    if arg_run_id:
        return arg_run_id
    if selected_topics.get("run_id"):
        return str(selected_topics["run_id"])
    return selected_topics_file.parent.name


def load_selected_topics(path: Path) -> dict[str, Any]:
    payload = read_json(path)
    selected = payload.get("selected_topics") or []
    if payload.get("status") != "approved" or not selected:
        raise RuntimeError(f"Brief Gate 未通过：{path} 中 status 必须为 approved 且 selected_topics 非空")
    return payload


def load_topic_cards(path: Path) -> dict[str, dict[str, Any]]:
    payload = read_json(path)
    # 兼容两种结构：纯数组，或 {schema_version, run_id, topic_cards: [...]} 包装
    cards = payload.get("topic_cards") if isinstance(payload, dict) else payload
    if not isinstance(cards, list):
        raise RuntimeError(f"topic_cards 结构不识别（期望数组或 topic_cards 包装）: {path}")
    return {card["topic_id"]: card for card in cards}


def _merge_unique_list(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for value in values:
        signature = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
        if signature in seen:
            continue
        seen.add(signature)
        result.append(value)
    return result


def resolve_selected_card(selected_topic: dict[str, Any], cards: dict[str, dict[str, Any]]) -> dict[str, Any]:
    topic_id = str(selected_topic["topic_id"])
    source_ids = [str(item) for item in (selected_topic.get("source_topic_ids") or [topic_id])]
    missing = [source_id for source_id in source_ids if source_id not in cards]
    if missing:
        raise RuntimeError(f"selected topic `{topic_id}` 的来源题卡不存在：{', '.join(missing)}")

    merged: dict[str, Any] = {}
    list_values: dict[str, list[Any]] = {}
    for source_id in source_ids:
        for key, value in cards[source_id].items():
            if isinstance(value, list):
                list_values.setdefault(key, []).extend(value)
            elif isinstance(value, dict):
                merged[key] = {**(merged.get(key) or {}), **value}
            elif key not in merged or not merged[key]:
                merged[key] = value
    for key, values in list_values.items():
        merged[key] = _merge_unique_list(values)

    for key, value in selected_topic.items():
        if isinstance(value, dict):
            merged[key] = {**(merged.get(key) or {}), **value}
        else:
            merged[key] = value
    merged["topic_id"] = topic_id
    merged["source_topic_ids"] = source_ids
    merged.setdefault("structure_hint", {})
    merged.setdefault("draft_contract", {})
    return merged


def build_claims(card: dict[str, Any]) -> list[dict[str, Any]]:
    proofs = card.get("proof_requirements") or []
    chart_needs = card.get("chart_needs") or card.get("recommended_visual_angles") or card.get("recommended_data_angles") or []
    core_thesis = card.get("core_thesis") or card.get("core_proposition") or card.get("one_line_judgment") or card["title"]
    missing_evidence = card.get("missing_evidence") or card.get("proof_requirements") or []
    topic_id = card["topic_id"]
    primary_sections = (card.get("draft_contract") or {}).get("primary_sections") or []
    if primary_sections:
        section_map = [
            (
                f"section-{index:02d}",
                str(section.get("brief") or section.get("title") or core_thesis),
            )
            for index, section in enumerate(primary_sections, start=1)
            if isinstance(section, dict)
        ]
    else:
        section_map = [
            ("section-01", proofs[0] if len(proofs) > 0 else core_thesis),
            ("section-02", proofs[1] if len(proofs) > 1 else core_thesis),
            ("section-03", proofs[2] if len(proofs) > 2 else "给出可执行框架和边界。"),
        ]
    claims = []
    for index, (section_id, statement) in enumerate(section_map, start=1):
        claims.append(
            {
                "claim_id": f"{topic_id}-claim-{index:02d}",
                "section_id": section_id,
                "statement": statement,
                "counterpoint": card.get("counterintuitive_angle") or card.get("distinctiveness_reason"),
                "missing_proof": missing_evidence[:2],
                "chart_need": chart_needs[index - 1] if len(chart_needs) >= index else None,
            }
        )
    return claims


def build_reasoning_sheet(run_id: str, card: dict[str, Any], selected_topic: dict[str, Any]) -> dict[str, Any]:
    now_iso = datetime.now().astimezone().isoformat()
    topic_id = card['topic_id']
    card_meta = card.get("meta")
    if card_meta is None:
        card_meta = {}
    upstream_id = card_meta.get("id")
    if upstream_id is None:
        upstream_id = f"{run_id}:{topic_id}:topic-card"

    title = card["title"]
    core_thesis = card.get("core_thesis") or card.get("core_proposition") or card.get("one_line_judgment") or title

    return {
        "meta": {
            "id": f"{run_id}:{topic_id}:reasoning",
            "object_type": "ReasoningSheet",
            "run_id": run_id,
            "version": "1.0.0",
            "status": "ready",
            "generated_by": "build_stage3_draft.py",
            "input_digest": f"{topic_id}::{title}",
            "upstream_ids": [upstream_id],
            "doc_refs": [],
            "created_at": now_iso,
            "updated_at": now_iso,
        },
        "topic_id": topic_id,
        "title": title,
        "core_thesis": core_thesis,
        "editor_note": selected_topic.get("editor_note", ""),
        "selection_reason": selected_topic.get("selection_reason", ""),
        "brief_context": {
            "source_material_summary": card.get("source_material_summary", ""),
            "controversy_points": card.get("controversy_points", []),
            "viewpoint_notes": card.get("viewpoint_notes", []),
            "question_units": card.get("question_units", []),
            "opinion_units": card.get("opinion_units", []),
            "case_units": card.get("case_units", []),
            "solution_units": card.get("solution_units", []),
        },
        "claims": build_claims(card),
        "evidence_items": card.get("existing_evidence", []),
        "structure_contract": {
            "max_primary_sections": int(
                (card.get("draft_contract") or {}).get("max_primary_sections")
                or DEFAULT_MAX_PRIMARY_SECTIONS
            ),
            "inherit_from_topic_card": True,
            "source_of_truth": "selected_topics.json + topic_cards.json",
        },
    }


def render_reasoning_sheet_md(reasoning: dict[str, Any], card: dict[str, Any]) -> str:
    title = reasoning['title']
    topic_id = reasoning['topic_id']
    core_thesis = reasoning['core_thesis']
    selection_reason = reasoning.get('selection_reason') or '待补'
    editor_note = reasoning.get('editor_note') or '无'

    lines = [
        f"# 03 Reasoning Sheet｜{title}",
        "",
        f"- topic_id：`{topic_id}`",
        f"- 核心命题：{core_thesis}",
        f"- 编辑选择原因：{selection_reason}",
        f"- 编辑备注：{editor_note}",
        "",
        "## Brief 上下文",
        "",
        f"- 来源内容记录：{(reasoning.get('brief_context') or {}).get('source_material_summary') or '待补'}",
        "- 争议点：",
    ]
    brief_context = reasoning.get("brief_context") or {}
    for item in brief_context.get("controversy_points") or ["待补"]:
        lines.append(f"  - {item}")
    lines.extend(
        [
            "- 已见观点：",
        ]
    )
    for item in brief_context.get("viewpoint_notes") or ["待补"]:
        lines.append(f"  - {item}")
    lines.extend(
        [
            "- 内容单元：",
        ]
    )
    for label, key in (
        ("问题", "question_units"),
        ("观点", "opinion_units"),
        ("案例", "case_units"),
        ("方案", "solution_units"),
    ):
        values = brief_context.get(key) or []
        lines.append(f"  - {label}：{'；'.join(values) if values else '待补'}")
    lines.extend(
        [
            "",
            "## Claims",
            "",
        ]
    )
    for claim in reasoning["claims"]:
        claim_id = claim['claim_id']
        section_id = claim['section_id']
        statement = claim['statement']
        counterpoint = claim.get('counterpoint') or '待补'
        missing_proof = claim.get('missing_proof') or ['无']
        missing_str = '；'.join(missing_proof)
        chart_need = claim.get('chart_need') or '无'

        lines.extend(
            [
                f"### {claim_id}",
                f"- section_id：`{section_id}`",
                f"- 判断：{statement}",
                f"- 反驳位：{counterpoint}",
                f"- 待补证明：{missing_str}",
                f"- 建议图表：{chart_need}",
                "",
            ]
        )
    lines.extend(["## 已有证据", ""])
    for item in reasoning["evidence_items"]:
        item_title = item.get('title')
        item_tier = item.get('source_tier', 'unknown')
        item_url = item.get('url', '')
        lines.append(f"- {item_title}｜{item_tier}｜{item_url}")
    lines.extend(["", "## 结构契约", ""])
    max_sections = reasoning['structure_contract']['max_primary_sections']
    opening_hint = (card.get('structure_hint') or {}).get('opening') or "从读者利益切入，先给结论再展开证据链。"
    lines.append(f"- 一级标题上限：{max_sections}")
    lines.append(f"- 起稿原则：{opening_hint}")
    return "\n".join(lines)


def render_template_draft(card: dict[str, Any], reasoning: dict[str, Any]) -> str:
    sources = card.get("existing_evidence", [])[:3]
    source_lines = "\n".join(f"- {item['title']}｜{item['url']}" for item in sources) or "- 待补权威来源"

    struct_hint = card.get("structure_hint") or {}
    section_titles = [
        ("开篇", struct_hint.get("opening") or "以行情剧烈波动切入，先给判断再展开逻辑。"),
        ("第一部分", struct_hint.get("part_1") or "拆解驱动逻辑与关键变量。"),
        ("第二部分", struct_hint.get("part_2") or "正反证据分层梳理。"),
        ("第三部分", struct_hint.get("part_3") or "给出可操作的应对框架。"),
        ("结尾", struct_hint.get("ending") or "落到可跟踪的指标与风险信号。"),
    ]

    card_title = card['title']
    topic_id = card['topic_id']
    core_thesis = card.get('core_thesis') or card.get('core_proposition') or card.get('one_line_judgment') or card['title']
    audience = card.get('audience') or '关注该议题的公众号读者'
    counterintuitive_angle = card.get('counterintuitive_angle') or card.get('controversy_points') or '主流叙事之外的变量'

    lines = [
        f"# 03 标准初稿｜{card_title}",
        "",
        "## 一、成稿说明",
        f"- topic_id：`{topic_id}`",
        f"- 主判断：{core_thesis}",
        f"- 目标读者：{audience}",
        f"- 结构契约：一级标题不超过 4 个，当前沿用 TopicCard 结构。",
        f"- 当前上游：`selected_topics.json` + `topic_cards.json` + `Reasoning Sheet`。",
        "",
        "## 二、标准初稿正文",
        "",
    ]
    for index, (heading, prompt) in enumerate(section_titles):
        if heading == "结尾":
            lines.append(f"### {heading}")
            lines.append("")
            lines.append(f"这篇稿子的落点不应停在情绪和表面消息，而要回到一个更硬的判断：{prompt}。只要证据链能补齐，正文就应该让读者明确看到哪些变量是真正值得继续跟踪的，哪些波动只是短期情绪。")
            lines.append("")
            continue
        lines.append(f"### {heading}：{prompt}")
        lines.append("")
        claim = reasoning["claims"][min(index, len(reasoning["claims"]) - 1)] if heading != "开篇" else None
        if heading == "开篇":
            lines.append(f"这篇文章真正想处理的，不是把新闻再复述一遍，而是把题目背后的误判点拎出来：{counterintuitive_angle}。如果这个误判不拆开，后续所有判断都会停留在热闹层，而不是结构层。")
            lines.append(f'因此开篇的任务只有一个：告诉读者为什么今天值得写、为什么这个题不该只按热点处理，以及为什么它最后会落到"{core_thesis}"这个主判断上。')
        else:
            claim_statement = claim['statement']
            claim_chart_need = claim.get('chart_need') or '关键数据图'
            lines.append(f"这一部分的核心判断是：{claim_statement}。正文应先交代事实层，再交代它为什么重要，最后给出与主线判断的连接方式。")
            lines.append(f'如果这一段容易写偏，最该防止的是把它写成情绪化描述，而忽略证据边界。这里至少需要围绕"{claim_chart_need}"补一个能证明差异和趋势的数据支点。')
        lines.append("")
    lines.extend(
        [
            "## 三、证据清单",
            source_lines,
            "",
            "## 四、待补证据项",
        ]
    )
    for item in card.get("missing_evidence", []):
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "## 五、写作约束",
            "- 不机械照抄 Brief，要从作者视角重组论证。",
            "- 能用数据或原始报道支撑的地方，不要停留在抽象判断。",
            "- 一级结构不超过 4 个，允许二级标题增强层次。",
        ]
    )
    return "\n".join(lines)


def render_report(run_id: str, drafts: list[dict[str, Any]]) -> str:
    lines = [
        "# 03 初稿报告",
        "",
        f"- run_id：`{run_id}`",
        f"- 题目数：`{len(drafts)}`",
        "",
        "## 本轮输出",
        "",
    ]
    for draft in drafts:
        draft_title = draft['title']
        reasoning_file = draft['reasoning_sheet_file']
        draft_file = draft['draft_file']
        html_file = draft.get("html_file")
        quality_status = (draft.get("quality_gate") or {}).get("status", "unknown")
        lines.append(f"- `{draft_title}`")
        lines.append(f"  - [Reasoning Sheet](<{reasoning_file}>)")
        lines.append(f"  - [标准初稿](<{draft_file}>)")
        if html_file:
            lines.append(f"  - [HTML 草稿](<{html_file}>)")
        lines.append(f"  - 中文字数：`{(draft.get('quality_gate') or {}).get('cjk_chars', 0)}`")
        lines.append(f"  - 文字洁癖 / 质量门禁：`{quality_status}`")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build canonical stage-3 drafts from selected topics")
    parser.add_argument("selected_topics_file", help="Path to selected_topics.json")
    parser.add_argument("topic_cards_file", help="Path to topic_cards.json")
    parser.add_argument("--output-dir", help="Output dir, default=~/Desktop/自媒体创作/<run_id>/03_初稿")
    parser.add_argument("--run-id")
    parser.add_argument("--asset-specs-file", help="Optional topic_id keyed chart_specs/image_specs for final HTML assets")
    parser.add_argument("--chartjs-file", help="Optional local Chart.js v4.4.4 UMD file for offline HTML packing")
    args = parser.parse_args()

    selected_topics_file = Path(args.selected_topics_file).expanduser().resolve()
    topic_cards_file = Path(args.topic_cards_file).expanduser().resolve()
    selected_payload = load_selected_topics(selected_topics_file)
    cards = load_topic_cards(topic_cards_file)
    external_asset_specs = load_asset_specs(Path(args.asset_specs_file).expanduser().resolve() if args.asset_specs_file else None)
    run_id = infer_run_id(selected_payload, args.run_id, selected_topics_file)
    output_dir = ensure_runtime_output_dir(
        Path(args.output_dir).expanduser().resolve() if args.output_dir else get_stage_dir("draft", run_id),
        label="draft output_dir",
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    selected_topics_for_draft = []
    drafts = []
    draft_quality_items = []
    for item in selected_payload["selected_topics"]:
        topic_id = item["topic_id"]
        card = resolve_selected_card(item, cards)
        reasoning = build_reasoning_sheet(run_id, card, item)
        slug = slugify(card["title"])[:48]
        reasoning_json_file = output_dir / f"03_ReasoningSheet_{slug}.json"
        reasoning_md_file = output_dir / f"03_ReasoningSheet_{slug}.md"
        draft_file = output_dir / f"03_标准初稿_{slug}.md"
        html_file = output_dir / f"03_HTML草稿_{slug}.html"
        quality_file = output_dir / f"03_质量门禁_{slug}.json"
        asset_specs_file = output_dir / f"03_DraftAssets_{slug}.json"
        illustration_intents_file = output_dir / f"03_IllustrationIntents_{slug}.json"
        write_json(reasoning_json_file, reasoning)
        write_text(reasoning_md_file, render_reasoning_sheet_md(reasoning, card))
        draft_text = generate_ai_draft(card, reasoning)
        quality_gate = inspect_draft_quality(draft_text, card, reasoning)
        write_text(draft_file, draft_text)
        asset_specs = resolve_asset_specs(card, reasoning, external_asset_specs, draft_text=draft_text)
        write_json(asset_specs_file, asset_specs)
        write_json(
            illustration_intents_file,
            {
                "schema_version": "dasheng.lemon_illustration_intents.v1",
                "topic_id": topic_id,
                "skill": "dasheng-lemon-illustrations",
                "status": asset_specs["illustration_status"],
                "intents": asset_specs["illustration_intents"],
                "unresolved": asset_specs["unresolved_illustration_intents"],
            },
        )
        write_draft_html_from_markdown(
            draft_file,
            html_file,
            title=card["title"],
            chart_specs=asset_specs["chart_specs"],
            image_specs=asset_specs["image_specs"],
            chartjs_file=args.chartjs_file,
        )
        write_json(quality_file, quality_gate)
        draft_quality_items.append(quality_gate)
        selected_topics_for_draft.append(item)
        drafts.append(
            {
                "topic_id": topic_id,
                "title": card["title"],
                "reasoning_sheet_file": str(reasoning_md_file),
                "reasoning_sheet_json": str(reasoning_json_file),
                "draft_file": str(draft_file),
                "html_file": str(html_file),
                "asset_specs_file": str(asset_specs_file),
                "illustration_intents_file": str(illustration_intents_file),
                "asset_status": asset_specs["asset_status"],
                "asset_missing": asset_specs["asset_missing"],
                "asset_failures": {
                    "finance_charts": asset_specs["finance_chart_failures"],
                },
                "asset_validation": {
                    "data": asset_specs["data_validation"],
                },
                "chart_specs": asset_specs["chart_specs"],
                "image_specs": asset_specs["image_specs"],
                "illustration_intents": asset_specs["illustration_intents"],
                "illustration_specs": asset_specs["illustration_specs"],
                "illustration_status": asset_specs["illustration_status"],
                "asset_requests": {
                    "charts": asset_specs["chart_requests"],
                    "images": asset_specs["image_requests"],
                    "finance_charts": asset_specs["finance_chart_requests"],
                    "lemon_illustrations": asset_specs["unresolved_illustration_intents"],
                },
                "html_contract": {
                    "self_contained": True,
                    "editable": True,
                    "offline": True,
                    "chartjs": "inline_when_chart_specs_exist",
                    "wechat_note": "发布前如需规避 canvas 白屏，可将图表截图替换为静态图。",
                },
                "quality_gate_file": str(quality_file),
                "quality_gate": {
                    "status": quality_gate["status"],
                    "ai_cliche_hit_count": sum(hit["count"] for hit in quality_gate["ai_cliche_hits"]),
                    "cjk_chars": quality_gate["cjk_chars"],
                    "h2_count": quality_gate["h2_count"],
                },
            }
        )

    aggregate_quality_gate = {
        "run_id": run_id,
        "stage": "draft",
        "status": "warning"
        if any(item["status"] == "warning" for item in draft_quality_items)
        or any(item.get("asset_status") == "incomplete" for item in drafts)
        else "pass",
        "checks": {
            "draft_count": len(draft_quality_items),
            "warning_count": sum(1 for item in draft_quality_items if item["status"] == "warning"),
            "ai_cliche_total": sum(sum(hit["count"] for hit in item["ai_cliche_hits"]) for item in draft_quality_items),
            "asset_incomplete_count": sum(1 for item in drafts if item.get("asset_status") == "incomplete"),
        },
        "items": draft_quality_items,
    }
    write_json(output_dir / "draft_quality_gate.json", aggregate_quality_gate)
    write_json(output_dir / "selected_topics_for_draft.json", {"run_id": run_id, "selected_topics": selected_topics_for_draft})
    write_json(
        output_dir / "final_structure_snapshot.template.json",
        {
            "run_id": run_id,
            "gate": "Final Structure Gate",
            "status": "pending_editor_review",
            "instructions": [
                "编辑完成标准稿修订后，在本文件写入最终保留的一级/二级结构。",
                "确认后进入 transwrite；数据、图表和配图缺口必须在 Draft 内处理，多版本改写仅作为按需工具。",
            ],
            "topics": [
                {
                    "topic_id": item["topic_id"],
                    "title": item["title"],
                    "doc_file": item["draft_file"],
                    "html_file": item["html_file"],
                    "final_primary_sections": [],
                    "editor_note": "",
                }
                for item in drafts
            ],
        },
    )
    ensure_pending_gate_file(
        output_dir / "final_structure_snapshot.json",
        run_id=run_id,
        gate_name="Final Structure Gate",
        topic_rows=[
            {
                "topic_id": item["topic_id"],
                "title": item["title"],
                "doc_file": item["draft_file"],
                "html_file": item["html_file"],
                "final_primary_sections": [],
                "editor_note": "",
            }
            for item in drafts
        ],
        instructions=[
            "编辑完成标准稿修订后，在本文件写入最终保留的一级/二级结构。",
            "status 改为 approved / locked / finalized 后，可进入 transwrite。",
        ],
    )
    write_text(output_dir / "03_初稿_报告.md", render_report(run_id, drafts))
    write_json(
        output_dir / "draft_manifest.json",
        {
            "run_id": run_id,
            "stage": "draft",
            "status": "ready_for_review"
            if not any(item.get("asset_status") == "incomplete" for item in drafts)
            else "incomplete_assets",
            "upstream": {
                "selected_topics": str(selected_topics_file),
                "topic_cards": str(topic_cards_file),
            },
            "drafts": drafts,
            "artifacts": [
                str((output_dir / "03_初稿_报告.md").resolve()),
                str((output_dir / "draft_manifest.json").resolve()),
                str((output_dir / "draft_quality_gate.json").resolve()),
                str((output_dir / "selected_topics_for_draft.json").resolve()),
                str((output_dir / "final_structure_snapshot.json").resolve()),
                str((output_dir / "final_structure_snapshot.template.json").resolve()),
            ]
            + [item["reasoning_sheet_file"] for item in drafts]
            + [item["reasoning_sheet_json"] for item in drafts]
            + [item["draft_file"] for item in drafts]
            + [item["html_file"] for item in drafts]
            + [item["asset_specs_file"] for item in drafts]
            + [item["quality_gate_file"] for item in drafts],
            "quality_gate_file": str((output_dir / "draft_quality_gate.json").resolve()),
            "quality_gate": {
                "status": aggregate_quality_gate["status"],
                "warning_count": aggregate_quality_gate["checks"]["warning_count"],
                "ai_cliche_total": aggregate_quality_gate["checks"]["ai_cliche_total"],
            },
            "integrated_capabilities": {
                "rewrite": "merged_into_transwrite_or_on_demand",
                "assets": "generated_inside_draft",
            },
            "next_stage": "transwrite",
        },
    )

    print(
        json.dumps(
            {
                "success": True,
                "run_id": run_id,
                "out_dir": str(output_dir),
                "draft_count": len(drafts),
                "draft_files": [item["draft_file"] for item in drafts],
                "html_files": [item["html_file"] for item in drafts],
                "manifest_file": str((output_dir / "draft_manifest.json").resolve()),
                "final_structure_snapshot": str((output_dir / "final_structure_snapshot.json").resolve()),
                "drafts": drafts,
                "next_step": "dasheng-stage-transwrite",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
