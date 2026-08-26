from __future__ import annotations

import json
import re
import threading
import uuid
from functools import lru_cache
from pathlib import Path

from .models import AgentProfile, PublicAgentProfile
from .settings import settings


MINIMUM_GROUP_COUNTS = {
    "宏观组": 3,
    "配置组": 3,
    "股票组": 5,
    "基金经理组": 8,
}
_registry_lock = threading.Lock()


def _frontmatter_name(skill_file: Path) -> str | None:
    try:
        text = skill_file.read_text(encoding="utf-8")[:4000]
    except (OSError, UnicodeError):
        return None
    match = re.search(r"(?m)^name:\s*[\"']?([^\n\"']+)", text)
    return match.group(1).strip() if match else None


def _frontmatter_description(skill_file: Path) -> str:
    try:
        text = skill_file.read_text(encoding="utf-8")[:6000]
    except (OSError, UnicodeError):
        return ""
    match = re.search(r"(?m)^description:\s*[\"']?([^\n\"']+)", text)
    return match.group(1).strip() if match else ""


def _canonical_skill_name(path: Path) -> str:
    return _frontmatter_name(path / "SKILL.md") or path.name


@lru_cache(maxsize=1)
def skill_catalog() -> dict[str, Path]:
    catalog: dict[str, Path] = {}
    for root in (settings.codex_skills_root, settings.agent_skills_root):
        if not root.exists():
            continue
        for skill_file in root.rglob("SKILL.md"):
            skill_dir = skill_file.parent
            names = {skill_dir.name}
            frontmatter_name = _frontmatter_name(skill_file)
            if frontmatter_name:
                names.add(frontmatter_name)
            for name in names:
                catalog.setdefault(name, skill_dir)
    return catalog


def resolve_skill_paths(skill_names: list[str]) -> tuple[list[Path], list[str]]:
    catalog = skill_catalog()
    paths: list[Path] = []
    missing: list[str] = []
    seen: set[Path] = set()
    for name in skill_names:
        path = catalog.get(name)
        if path is None:
            missing.append(name)
        elif path not in seen:
            paths.append(path)
            seen.add(path)
    return paths, missing


@lru_cache(maxsize=1)
def load_profiles() -> list[AgentProfile]:
    raw = json.loads(settings.registry_path.read_text(encoding="utf-8"))
    profiles: list[AgentProfile] = []
    for item in raw.get("standing_agents", []):
        skill_paths, missing = resolve_skill_paths(item.get("skills", []))
        role_card_path = settings.project_root / item.get("role_card", "")
        role_card_content = (
            role_card_path.read_text(encoding="utf-8") if role_card_path.is_file() else ""
        )
        profiles.append(
            AgentProfile(
                **item,
                available_skills=[_canonical_skill_name(path) for path in skill_paths],
                missing_skills=missing,
                role_card_content=role_card_content,
            ),
        )

    ids = [profile.id for profile in profiles]
    if not profiles or len(ids) != len(set(ids)):
        raise RuntimeError("投委会注册表必须包含至少一个席位，且席位编号不得重复。")

    for group, expected in MINIMUM_GROUP_COUNTS.items():
        actual = sum(profile.group == group for profile in profiles)
        if actual < expected:
            raise RuntimeError(f"{group}至少应有{expected}席，当前为{actual}席。")
    return profiles


def public_profiles() -> list[PublicAgentProfile]:
    return [
        PublicAgentProfile.model_validate(profile.model_dump(exclude={"role_card_content"}))
        for profile in load_profiles()
    ]


def public_skill_catalog() -> list[dict[str, object]]:
    profiles = load_profiles()
    assigned: dict[str, list[str]] = {}
    for profile in profiles:
        for skill in profile.skills:
            path = skill_catalog().get(skill)
            canonical_name = _canonical_skill_name(path) if path else skill
            assigned.setdefault(canonical_name, []).append(profile.id)
    unique_paths = sorted(set(skill_catalog().values()), key=lambda item: item.name)
    items = []
    for path in unique_paths:
        skill_file = path / "SKILL.md"
        name = _frontmatter_name(skill_file) or path.name
        items.append(
            {
                "name": name,
                "description": _frontmatter_description(skill_file),
                "assigned_agents": assigned.get(name, []),
            },
        )
    return sorted(items, key=lambda item: str(item["name"]))


def get_profile(agent_id: str) -> AgentProfile:
    for profile in load_profiles():
        if profile.id == agent_id:
            return profile
    raise KeyError(agent_id)


def required_skill_names(profile: AgentProfile) -> list[str]:
    registered = registered_skill_names(profile)
    return registered[:5]


def registered_skill_names(profile: AgentProfile) -> list[str]:
    paths, _ = resolve_skill_paths(profile.skills)
    return list(dict.fromkeys(_canonical_skill_name(path) for path in paths))


def update_profile(agent_id: str, changes: dict[str, object]) -> PublicAgentProfile:
    with _registry_lock:
        original = settings.registry_path.read_text(encoding="utf-8")
        raw = json.loads(original)
        target = next(
            (item for item in raw.get("standing_agents", []) if item.get("id") == agent_id),
            None,
        )
        if target is None:
            raise KeyError(agent_id)
        if "skills" in changes:
            skills = list(dict.fromkeys(str(item) for item in changes["skills"] or []))
            if not 3 <= len(skills) <= 5:
                raise ValueError("每个 Agent 必须配置 3 至 5 个 Skills。")
            unknown = [name for name in skills if name not in skill_catalog()]
            if unknown:
                raise ValueError(f"未知 Skills：{', '.join(unknown[:5])}")
            changes = {**changes, "skills": skills}
        target.update(changes)
        target["display_name"] = target.get("name", target.get("display_name", ""))
        target["status_bar_name"] = target.get("name", target.get("status_bar_name", ""))
        temp_path = settings.registry_path.with_suffix(".json.tmp")
        temp_path.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temp_path.replace(settings.registry_path)
        load_profiles.cache_clear()
        try:
            profile = get_profile(agent_id)
        except Exception:
            settings.registry_path.write_text(original, encoding="utf-8")
            load_profiles.cache_clear()
            raise
        return PublicAgentProfile.model_validate(
            profile.model_dump(exclude={"role_card_content"}),
        )


def create_profile(values: dict[str, object]) -> PublicAgentProfile:
    with _registry_lock:
        original = settings.registry_path.read_text(encoding="utf-8")
        raw = json.loads(original)
        skills = list(dict.fromkeys(str(item) for item in values.get("skills", []) or []))
        if not 3 <= len(skills) <= 5:
            raise ValueError("每个 Agent 必须配置 3 至 5 个 Skills。")
        unknown = [name for name in skills if name not in skill_catalog()]
        if unknown:
            raise ValueError(f"未知 Skills：{', '.join(unknown[:5])}")

        agent_id = f"CUSTOM-{uuid.uuid4().hex[:8].upper()}"
        group = str(values["group"])
        default_outputs = {
            "基金经理组": ["框架判断", "组合动作", "风险预算", "投票"],
            "宏观组": ["核心变量", "传导链路", "情景推演", "配置含义"],
            "配置组": ["市场状态", "定价与拥挤", "组合影响", "执行条件"],
            "股票组": ["产业驱动", "公司映射", "估值与催化", "风险与反证"],
        }
        item = {
            "id": agent_id,
            "alias": agent_id.lower(),
            "slug": agent_id.lower(),
            "name": str(values["name"]),
            "title": str(values["title"]),
            "group": group,
            "focus": str(values["focus"]),
            "persona": str(values["persona"]),
            "style": str(values["style"]),
            "role_card": "",
            "shared_skills": [],
            "specialty_skills": skills,
            "skills": skills,
            "default_prompt": str(values.get("default_prompt", "")),
            "research_channels": ["Tushare Pro", "A Stock Data", "Global Stock Data", "Tavily", "IMA Knowledge Base"],
            "tushare_endpoints": [],
            "outputs": default_outputs[group],
            "risk_controls": [
                "所有数据和观点必须保留来源与日期",
                "必须给出关键假设、反证条件和可跟踪指标",
            ],
            "connection": values.get("connection") or {"kind": "orchestra"},
            "is_custom": True,
            "display_name": str(values["name"]),
            "status_bar_name": str(values["name"]),
        }
        raw.setdefault("standing_agents", []).append(item)
        temp_path = settings.registry_path.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp_path.replace(settings.registry_path)
        load_profiles.cache_clear()
        try:
            profile = get_profile(agent_id)
        except Exception:
            settings.registry_path.write_text(original, encoding="utf-8")
            load_profiles.cache_clear()
            raise
        return PublicAgentProfile.model_validate(profile.model_dump(exclude={"role_card_content"}))


def delete_profile(agent_id: str) -> None:
    with _registry_lock:
        original = settings.registry_path.read_text(encoding="utf-8")
        raw = json.loads(original)
        agents = raw.get("standing_agents", [])
        target = next((item for item in agents if item.get("id") == agent_id), None)
        if target is None:
            raise KeyError(agent_id)
        if not target.get("is_custom", False):
            raise ValueError("常设核心席位不能删除，只能删除用户新增的 Agent。")
        raw["standing_agents"] = [item for item in agents if item.get("id") != agent_id]
        temp_path = settings.registry_path.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp_path.replace(settings.registry_path)
        load_profiles.cache_clear()
        try:
            load_profiles()
        except Exception:
            settings.registry_path.write_text(original, encoding="utf-8")
            load_profiles.cache_clear()
            raise


def skill_paths_for(profile: AgentProfile) -> list[str]:
    paths, _ = resolve_skill_paths(profile.skills)
    return [str(path) for path in paths]
