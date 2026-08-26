#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

import yaml

from canonical_workflow import optional_asset_dir, write_json
from path_config import get_output_root
from path_config import get_output_root
from path_config import get_output_root
from provider_registry import extract_chat_content, resolve_chat_provider


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = get_output_root("paradigm")
MAX_SAMPLE_CHARS_FOR_AI = 18000


@dataclass(frozen=True)
class Sample:
    path: Path
    title: str
    text: str
    char_count: int
    paragraph_count: int
    heading_count: int
    sha256: str


def read_text_file(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"样本不存在：{path}")
    if path.suffix.lower() not in {".md", ".txt"}:
        raise ValueError(f"当前最小执行器仅支持 .md / .txt：{path}")
    return path.read_text(encoding="utf-8")


def normalize_text(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text.replace("\r\n", "\n").strip())


def title_from_text(path: Path, text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or path.stem
        if stripped:
            return stripped[:80]
    return path.stem


def split_paragraphs(text: str) -> list[str]:
    return [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]


def count_headings(text: str) -> int:
    return sum(1 for line in text.splitlines() if re.match(r"^#{1,6}\s+", line.strip()))


def load_samples(paths: list[str]) -> list[Sample]:
    samples: list[Sample] = []
    for value in paths:
        path = Path(value).expanduser().resolve()
        text = normalize_text(read_text_file(path))
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        samples.append(
            Sample(
                path=path,
                title=title_from_text(path, text),
                text=text,
                char_count=len(text),
                paragraph_count=len(split_paragraphs(text)),
                heading_count=count_headings(text),
                sha256=digest,
            )
        )
    return samples


def slugify(value: str) -> str:
    cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "-", value.strip())
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned or "paradigm-profile"


def infer_profile_name(samples: list[Sample], provided: str | None) -> str:
    if provided:
        return provided.strip()
    if samples:
        return f"{samples[0].title[:24]}范式"
    return "未命名范式"


def top_heading_lines(samples: list[Sample]) -> list[str]:
    headings: list[str] = []
    for sample in samples:
        for line in sample.text.splitlines():
            stripped = line.strip()
            if re.match(r"^#{1,3}\s+", stripped):
                headings.append(stripped.lstrip("#").strip())
    return headings[:20]


def paragraph_stats(samples: list[Sample]) -> dict[str, Any]:
    lengths: list[int] = []
    for sample in samples:
        lengths.extend(len(paragraph) for paragraph in split_paragraphs(sample.text))
    if not lengths:
        return {"count": 0, "average_chars": 0, "short_paragraph_ratio": 0}
    short_count = sum(1 for length in lengths if length <= 80)
    return {
        "count": len(lengths),
        "average_chars": round(sum(lengths) / len(lengths), 1),
        "short_paragraph_ratio": round(short_count / len(lengths), 3),
    }


def strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    return cleaned


def parse_json_object_from_text(text: str) -> dict[str, Any] | None:
    cleaned = strip_code_fence(text)
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", cleaned, re.S)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def resolve_paradigm_ai_config() -> dict[str, str] | None:
    return resolve_chat_provider(
        custom_env_var="DASHENG_PARADIGM_PROVIDER_ENV",
        base_url_keys=["PARADIGM_AI_BASE_URL", "PHASE3_AI_BASE_URL", "PHASE2_AI_BASE_URL", "QHAIGC_BASE_URL"],
        api_key_keys=["PARADIGM_AI_API_KEY", "PHASE3_AI_API_KEY", "PHASE2_AI_API_KEY", "QHAIGC_API_KEY"],
        model_keys=["PARADIGM_AI_MODEL", "PHASE3_AI_MODEL", "DRAFT_AI_MODEL", "PHASE2_AI_MODEL"],
        timeout_keys=["PARADIGM_AI_TIMEOUT_SECONDS", "PHASE3_AI_TIMEOUT_SECONDS", "PHASE2_AI_TIMEOUT_SECONDS"],
        default_model="gpt-4.1-mini",
        default_timeout_seconds="180",
    )


def request_ai_json(system_prompt: str, user_prompt: str, *, max_tokens: int = 6000) -> dict[str, Any] | None:
    fake_response_file = (os.environ.get("DASHENG_PARADIGM_FAKE_RESPONSE_FILE") or "").strip()
    if fake_response_file:
        return parse_json_object_from_text(Path(fake_response_file).expanduser().resolve().read_text(encoding="utf-8"))
    fake_response = os.environ.get("DASHENG_PARADIGM_FAKE_RESPONSE")
    if fake_response:
        return parse_json_object_from_text(fake_response)
    config = resolve_paradigm_ai_config()
    if not config:
        return None
    body = {
        "model": config["model"],
        "temperature": 0.45,
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
    }
    req = urllib_request.Request(
        config["base_url"],
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config['api_key']}",
        },
        method="POST",
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib_request.urlopen(req, timeout=float(config["timeout_seconds"])) as resp:
                response_payload = json.loads(resp.read().decode("utf-8"))
            content = extract_chat_content(response_payload)
            if not content:
                return None
            return parse_json_object_from_text(content)
        except (
            urllib_error.URLError,
            urllib_error.HTTPError,
            TimeoutError,
            json.JSONDecodeError,
            ValueError,
            http.client.RemoteDisconnected,
        ) as exc:
            last_error = exc
            if attempt >= 2:
                break
            time.sleep(2 * (attempt + 1))
    if last_error:
        return None
    return None


def sample_excerpt_for_ai(samples: list[Sample]) -> list[dict[str, str]]:
    excerpts: list[dict[str, str]] = []
    per_sample_limit = max(2000, MAX_SAMPLE_CHARS_FOR_AI // max(len(samples), 1))
    for sample in samples:
        text = sample.text
        if len(text) > per_sample_limit:
            text = text[:per_sample_limit] + "\n...[truncated]"
        excerpts.append({"title": sample.title, "path": str(sample.path), "text": text})
    return excerpts


def build_ai_prompt_payload(
    *,
    profile_name: str,
    sample_type: str,
    scenarios: list[str],
    channels: list[str],
    bind_style_dna: str,
    samples: list[Sample],
) -> dict[str, Any]:
    return {
        "profile_name": profile_name,
        "sample_type": sample_type,
        "target_scenarios": scenarios,
        "target_channels": channels,
        "style_dna_binding": bind_style_dna,
        "sample_metrics": [
            {
                "title": sample.title,
                "char_count": sample.char_count,
                "paragraph_count": sample.paragraph_count,
                "heading_count": sample.heading_count,
            }
            for sample in samples
        ],
        "sample_excerpts": sample_excerpt_for_ai(samples),
        "output_contract": {
            "one_line_definition": "string",
            "opening_mechanism": ["string"],
            "section_framework": ["string"],
            "argument_model": ["string"],
            "information_density": {"facts": "string", "opinions": "string", "cases": "string", "data": "string"},
            "paragraph_recipe": ["string"],
            "scenario_fit": {"best_fit": ["string"], "misfit": ["string"], "preconditions": ["string"]},
            "channel_adaptation": {"channel_name": "rule"},
            "style_boundary": ["string"],
            "misfit_risks": ["string"],
        },
    }


def request_deep_paradigm_analysis(
    *,
    profile_name: str,
    sample_type: str,
    scenarios: list[str],
    channels: list[str],
    bind_style_dna: str,
    samples: list[Sample],
) -> dict[str, Any] | None:
    payload = build_ai_prompt_payload(
        profile_name=profile_name,
        sample_type=sample_type,
        scenarios=scenarios,
        channels=channels,
        bind_style_dna=bind_style_dna,
        samples=samples,
    )
    system_prompt = (
        "你是内容产品架构师和资深主编，任务是从样本文章/模板中提炼可复用的文章范式。"
        "你必须区分 ParadigmProfile 与 Style DNA：前者只管结构、叙事、论证、场景和渠道适配；后者才管口吻和语言。"
        "不得把样本事实、样本金句、未核验数据搬进新文章。输出必须是 JSON 对象。"
    )
    user_prompt = (
        "请深度学习这些样本，输出可被 Brief/Draft/Rewrite/Publish 直接消费的 ParadigmProfile。"
        "不要输出泛泛的开头-正文-结尾模板；必须包含不适用场景、渠道差异、风格边界和禁用项。\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )
    return request_ai_json(system_prompt, user_prompt)


def merge_ai_analysis(base_paradigm: dict[str, Any], ai_analysis: dict[str, Any] | None) -> tuple[dict[str, Any], str]:
    if not ai_analysis:
        return base_paradigm, "heuristic_fallback"
    allowed_keys = {
        "one_line_definition",
        "opening_mechanism",
        "section_framework",
        "argument_model",
        "information_density",
        "paragraph_recipe",
        "scenario_fit",
        "channel_adaptation",
        "style_boundary",
        "misfit_risks",
    }
    merged = dict(base_paradigm)
    for key in allowed_keys:
        value = ai_analysis.get(key)
        if value:
            merged[key] = value
    return merged, "ai_enriched"


def build_profile_payload(
    *,
    run_id: str,
    profile_name: str,
    sample_type: str,
    scenarios: list[str],
    channels: list[str],
    bind_style_dna: str,
    samples: list[Sample],
    ai_analysis: dict[str, Any] | None = None,
) -> dict[str, Any]:
    headings = top_heading_lines(samples)
    stats = paragraph_stats(samples)
    sample_rows = [
        {
            "title": sample.title,
            "path": str(sample.path),
            "char_count": sample.char_count,
            "paragraph_count": sample.paragraph_count,
            "heading_count": sample.heading_count,
            "sha256": sample.sha256,
        }
        for sample in samples
    ]
    base_paradigm = {
        "one_line_definition": "待编辑校准：根据样本抽取文章组织范式。",
        "opening_mechanism": ["待补充：冲突/问题/收益/身份代入机制"],
        "section_framework": headings[:8] or ["待补充：一级章节功能与顺序"],
        "argument_model": ["提出判断", "排列证据", "处理反例或风险", "收束到可迁移框架"],
        "information_density": {
            "facts": "待校准",
            "opinions": "待校准",
            "cases": "待校准",
            "data": "待校准",
        },
        "paragraph_recipe": ["待校准：段落长度、短段落触发条件、转场句功能"],
        "scenario_fit": {
            "best_fit": scenarios or ["待指定"],
            "misfit": ["事实证据不足", "只需要末端润色", "只想复用样本事实"],
            "preconditions": ["当前任务必须有独立事实来源和可验证证据"],
        },
        "channel_adaptation": {channel: "待补充该渠道标题、开头、结构和 CTA 变形规则" for channel in channels},
        "style_boundary": ["结构范式可复用，作者口吻需交给 Style DNA"],
        "misfit_risks": ["事实证据不足时不适用", "只适合套结构，不允许搬运样本事实"],
    }
    paradigm, analysis_mode = merge_ai_analysis(base_paradigm, ai_analysis)
    return {
        "schema_version": "1.0",
        "stage": "paradigm",
        "run_id": run_id,
        "profile_name": profile_name,
        "sample_type": sample_type,
        "target_scenarios": scenarios,
        "target_channels": channels,
        "style_dna_binding": bind_style_dna,
        "samples": sample_rows,
        "observed_structure": {
            "heading_examples": headings,
            "paragraph_stats": stats,
            "average_chars_per_sample": round(sum(sample.char_count for sample in samples) / max(len(samples), 1), 1),
        },
        "analysis_mode": analysis_mode,
        "paradigm": paradigm,
        "boundaries": {
            "not_fact_source": True,
            "do_not_copy_sample_facts": True,
            "separate_from_style_dna": True,
        },
    }


def render_markdown(payload: dict[str, Any]) -> str:
    samples = payload["samples"]
    paradigm = payload["paradigm"]
    channels = payload["target_channels"]
    headings = payload["observed_structure"]["heading_examples"]
    sample_lines = "\n".join(
        f"- `{Path(sample['path']).name}`：{sample['char_count']} 字，{sample['paragraph_count']} 段，{sample['heading_count']} 个标题"
        for sample in samples
    )
    heading_lines = "\n".join(f"- {heading}" for heading in headings) or "- 待从样本中校准"
    channel_lines = "\n".join(f"- {channel}：{paradigm['channel_adaptation'][channel]}" for channel in channels) or "- 待指定渠道"
    scenario_fit = paradigm.get("scenario_fit") or {}
    paragraph_recipe = paradigm.get("paragraph_recipe") or []
    style_boundary = paradigm.get("style_boundary") or []
    return f"""# {payload['profile_name']} 范式画像

## 1. 样本概况

- run_id：`{payload['run_id']}`
- 样本类型：{payload['sample_type']}
- 目标场景：{', '.join(payload['target_scenarios']) or '待指定'}
- 目标渠道：{', '.join(channels) or '待指定'}
- Style DNA 绑定：{payload['style_dna_binding']}
- 分析模式：{payload.get('analysis_mode', 'unknown')}

{sample_lines}

## 2. 范式一句话定义

{paradigm['one_line_definition']}

## 3. 适用场景与不适用场景

- 适用：{', '.join(scenario_fit.get('best_fit') or payload['target_scenarios']) or '待编辑补充'}
- 不适用：{', '.join(scenario_fit.get('misfit') or ['事实证据不足、只想复用样本事实、仅需末端润色的任务'])}
- 使用前置条件：{', '.join(scenario_fit.get('preconditions') or ['当前任务必须有独立事实来源和可验证证据'])}

## 4. 开篇机制

{chr(10).join(f'- {item}' for item in paradigm['opening_mechanism'])}

## 5. 主干章节框架

{heading_lines}

## 6. 论证推进模型

{chr(10).join(f'- {item}' for item in paradigm['argument_model'])}

## 7. 信息密度与段落配方

- 平均段落长度：{payload['observed_structure']['paragraph_stats']['average_chars']} 字
- 短段落比例：{payload['observed_structure']['paragraph_stats']['short_paragraph_ratio']}
- 事实/观点/案例/数据比例：待编辑校准
{chr(10).join(f'- {item}' for item in paragraph_recipe)}

## 8. 渠道适配矩阵

{channel_lines}

## 9. 与 Style DNA 的边界

- `ParadigmProfile` 控制结构、叙事、论证和渠道框架。
- `Style DNA` 控制口吻、词汇、句式、节奏和作者感。
- Draft 只能继承结构范式，不能注入作者口吻或平台腔。
{chr(10).join(f'- {item}' for item in style_boundary)}

## 10. 禁用项与风险

- 不把样本当事实来源。
- 不搬运样本事实、金句、未核验数据。
- 不把范式学习等同于风格模仿。
- 不跳过不适用场景和渠道差异。

## 11. 可复用 Prompt Block

见 `paradigm_prompt_block.md`。

## 12. 下游注入建议

- Brief：为候选题标注推荐范式、适配分、适用理由和风险边界。
- Draft：继承章节骨架、论证顺序、信息密度和转场机制。
- Rewrite：与 Style DNA 组合，范式管结构，DNA 管表达。
- Publish：按渠道拆成不同标题、开头、结构和 CTA。
"""


def render_prompt_block(payload: dict[str, Any]) -> str:
    paradigm = payload["paradigm"]
    return f"""# Paradigm Prompt Block｜{payload['profile_name']}

你将使用 `ParadigmProfile` 作为结构约束，而不是事实来源或文风模仿对象。

## 适用场景

{chr(10).join(f'- {item}' for item in payload['target_scenarios']) or '- 待指定'}

## 结构范式

{chr(10).join(f'- {item}' for item in paradigm['section_framework'])}

## 论证推进

{chr(10).join(f'- {item}' for item in paradigm['argument_model'])}

## 渠道适配

{chr(10).join(f"- {channel}：{rule}" for channel, rule in paradigm['channel_adaptation'].items()) or '- 待指定'}

## 禁止事项

- 不得复用样本事实。
- 不得照搬样本金句。
- 不得把样本文风注入标准初稿。
- 所有正文事实必须来自当前任务的可复核来源。
"""


def write_outputs(output_dir: Path, payload: dict[str, Any]) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    profile_md = output_dir / "00_范式画像.md"
    profile_yaml = output_dir / "paradigm_profile.yaml"
    prompt_block = output_dir / "paradigm_prompt_block.md"
    manifest_path = output_dir / "paradigm_manifest.json"

    profile_md.write_text(render_markdown(payload), encoding="utf-8")
    profile_yaml.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
    prompt_block.write_text(render_prompt_block(payload), encoding="utf-8")

    manifest = {
        "stage": "paradigm",
        "run_id": payload["run_id"],
        "status": "pending_editor_calibration",
        "analysis_mode": payload.get("analysis_mode", "unknown"),
        "profile_name": payload["profile_name"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "outputs": {
            "profile_md": str(profile_md),
            "profile_yaml": str(profile_yaml),
            "prompt_block": str(prompt_block),
        },
        "samples": payload["samples"],
        "next_recommended_stage": "brief",
    }
    write_json(manifest_path, manifest)
    return {
        "profile_md": str(profile_md),
        "profile_yaml": str(profile_yaml),
        "prompt_block": str(prompt_block),
        "manifest": str(manifest_path),
    }


def split_csv(values: list[str] | None) -> list[str]:
    if not values:
        return []
    result: list[str] = []
    for value in values:
        result.extend(item.strip() for item in value.split(",") if item.strip())
    return result


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build Newma ParadigmProfile artifacts from standard articles/templates")
    parser.add_argument("samples", nargs="+", help="Sample .md/.txt files")
    parser.add_argument("--run-id", required=True, help="Run id to bind this optional asset")
    parser.add_argument("--profile-name", help="Profile name; inferred from first sample if omitted")
    parser.add_argument("--sample-type", default="standard_article", help="standard_article/template/success_sample/channel_template")
    parser.add_argument("--scenario", action="append", help="Target scenario; repeat or comma-separate")
    parser.add_argument("--channel", action="append", help="Target channel; repeat or comma-separate")
    parser.add_argument("--bind-style-dna", default="none", help="none/existing/new")
    parser.add_argument("--output-dir", help="Output directory; defaults to canonical paradigm dir for run")
    parser.add_argument("--no-ai", action="store_true", help="Disable optional AI enrichment and only write heuristic skeleton")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    samples = load_samples(args.samples)
    profile_name = infer_profile_name(samples, args.profile_name)
    output_dir = Path(args.output_dir).expanduser().resolve() if args.output_dir else optional_asset_dir("paradigm", args.run_id) / slugify(profile_name)
    ai_analysis = None if args.no_ai else request_deep_paradigm_analysis(
        profile_name=profile_name,
        sample_type=args.sample_type,
        scenarios=split_csv(args.scenario),
        channels=split_csv(args.channel),
        bind_style_dna=args.bind_style_dna,
        samples=samples,
    )
    payload = build_profile_payload(
        run_id=args.run_id,
        profile_name=profile_name,
        sample_type=args.sample_type,
        scenarios=split_csv(args.scenario),
        channels=split_csv(args.channel),
        bind_style_dna=args.bind_style_dna,
        samples=samples,
        ai_analysis=ai_analysis,
    )
    outputs = write_outputs(output_dir, payload)
    print(json.dumps({"success": True, "run_id": args.run_id, "output_dir": str(output_dir), **outputs}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
