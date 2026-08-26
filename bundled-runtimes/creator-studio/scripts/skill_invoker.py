#!/usr/bin/env python3
"""
skill_invoker.py — 统一 OpenClaw/Claude Code Skill 调用适配层

从 Python 脚本中调用 ~/.claude/skills/ 或 ~/.openclaw/ 中的 skill，
通过 Anthropic API 执行并返回结构化 JSON 结果。
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any

import anthropic

SKILL_SEARCH_PATHS: list[Path] = [
    Path.home() / ".claude" / "skills",
    Path.home() / ".codex" / "skills",
    Path.home() / ".agents" / "skills",
    Path.home() / ".openclaw" / ".openclaw.pre-migration" / "skills",
    Path.home() / ".openclaw" / ".openclaw.pre-migration" / "skills-backup-nonofficial-20260303-230337",
    Path(__file__).resolve().parent.parent / "skills",
]

DEFAULT_MODEL = "claude-sonnet-4-6"


def _find_skill_md(skill_name: str) -> Path | None:
    for base in SKILL_SEARCH_PATHS:
        candidate = base / skill_name / "SKILL.md"
        if candidate.exists():
            return candidate
    return None


def _parse_skill_md(skill_md_path: Path) -> tuple[str, str]:
    """返回 (frontmatter_str, body_str)"""
    content = skill_md_path.read_text(encoding="utf-8")
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            return parts[1].strip(), parts[2].strip()
    return "", content.strip()


def _strip_json_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*\n?", "", text)
    text = re.sub(r"\n?```\s*$", "", text)
    return text.strip()


class SkillInvoker:
    """统一调用 OpenClaw/Claude Code skill 的适配器。"""

    def __init__(self, model: str = DEFAULT_MODEL):
        self.client = anthropic.Anthropic()
        self.model = model

    def invoke(
        self,
        skill_name: str,
        payload: dict[str, Any],
        context: dict[str, Any] | None = None,
        *,
        max_tokens: int = 4096,
    ) -> dict[str, Any]:
        """
        调用指定 skill，返回结构化 JSON 结果。

        Args:
            skill_name: skill 名称，如 "wechat-title-generator"
            payload: 传给 skill 的输入数据
            context: 可选的额外上下文
            max_tokens: Claude API 最大返回 token 数

        Returns:
            包含 "success" 字段的 dict
        """
        skill_md_path = _find_skill_md(skill_name)
        if not skill_md_path:
            return {
                "success": False,
                "error": f"Skill '{skill_name}' not found in any search path",
                "searched_paths": [str(p / skill_name) for p in SKILL_SEARCH_PATHS],
            }

        _frontmatter, skill_body = _parse_skill_md(skill_md_path)

        system_prompt = (
            f"You are executing the '{skill_name}' skill as a programmatic API.\n\n"
            f"## Skill Reference\n{skill_body}\n\n"
            "## Output Contract\n"
            "Respond with valid JSON ONLY. No markdown fences, no explanations, no preamble.\n"
            'The JSON must contain a "success": true/false field.\n'
            "For generation tasks, include the main result under a key that matches the task "
            '(e.g. "titles", "outline", "content", "image_prompt", etc.).'
        )

        user_parts: list[str] = [
            f"Execute the '{skill_name}' skill with the following input:\n",
            f"```json\n{json.dumps(payload, ensure_ascii=False, indent=2)}\n```",
        ]
        if context:
            user_parts.append(
                f"\n## Additional Context\n```json\n{json.dumps(context, ensure_ascii=False, indent=2)}\n```"
            )
        user_parts.append("\nReturn structured JSON only.")

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": "\n".join(user_parts)}],
            )
        except Exception as exc:
            return {
                "success": False,
                "error": f"Skill '{skill_name}' invocation failed: {exc}",
                "skill_name": skill_name,
            }

        raw_text = message.content[0].text
        cleaned = _strip_json_fences(raw_text)

        try:
            result = json.loads(cleaned)
        except json.JSONDecodeError:
            # 尝试从响应中提取第一个 JSON 对象
            match = re.search(r"\{[\s\S]+\}", cleaned)
            if match:
                try:
                    result = json.loads(match.group())
                except json.JSONDecodeError:
                    result = None
            else:
                result = None

        if result is None:
            return {
                "success": False,
                "error": "Failed to parse skill response as JSON",
                "raw_response": raw_text[:800],
                "skill_name": skill_name,
            }

        if "success" not in result:
            result["success"] = True
        return result

    def list_available_skills(self) -> list[dict[str, str]]:
        """列出所有可用的 skills。"""
        skills: list[dict[str, str]] = []
        seen: set[str] = set()
        for base in SKILL_SEARCH_PATHS:
            if not base.exists():
                continue
            for skill_dir in sorted(base.iterdir()):
                if not skill_dir.is_dir():
                    continue
                skill_md = skill_dir / "SKILL.md"
                if skill_md.exists() and skill_dir.name not in seen:
                    seen.add(skill_dir.name)
                    skills.append({"name": skill_dir.name, "path": str(skill_md)})
        return skills


# ─── 模块级单例 ────────────────────────────────────────────────────────────────

_default_invoker: SkillInvoker | None = None


def get_invoker() -> SkillInvoker:
    global _default_invoker
    if _default_invoker is None:
        _default_invoker = SkillInvoker()
    return _default_invoker


def invoke_skill(
    skill_name: str,
    payload: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """便捷函数：使用默认 invoker 调用 skill。"""
    return get_invoker().invoke(skill_name, payload, context)


# ─── CLI ───────────────────────────────────────────────────────────────────────

def _main() -> None:
    parser = argparse.ArgumentParser(description="skill_invoker — 调用 OpenClaw/Claude Code skill")
    sub = parser.add_subparsers(dest="cmd")

    invoke_p = sub.add_parser("invoke", help="调用一个 skill")
    invoke_p.add_argument("skill_name")
    invoke_p.add_argument("--payload", default="{}", help="JSON payload 字符串")
    invoke_p.add_argument("--payload-file", help="JSON payload 文件路径")

    sub.add_parser("list", help="列出所有可用的 skills")

    args = parser.parse_args()

    invoker = SkillInvoker()

    if args.cmd == "list":
        skills = invoker.list_available_skills()
        for s in skills:
            print(f"{s['name']:40s}  {s['path']}")
        return

    if args.cmd == "invoke":
        if args.payload_file:
            payload = json.loads(Path(args.payload_file).read_text(encoding="utf-8"))
        else:
            payload = json.loads(args.payload)
        result = invoker.invoke(args.skill_name, payload)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    parser.print_help()


if __name__ == "__main__":
    _main()
