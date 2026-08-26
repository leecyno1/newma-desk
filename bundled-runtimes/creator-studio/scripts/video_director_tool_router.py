#!/usr/bin/env python3
"""Route director scenes through the unified video project, Skill, and tool registry."""

from __future__ import annotations

import argparse
import json
import os
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TOOL_REGISTRY = PROJECT_ROOT / "configs" / "video" / "tool_registry.json"
DEFAULT_PROJECT_REGISTRY = PROJECT_ROOT / "configs" / "external" / "reserved_projects.json"
DEFAULT_DIRECTOR_REGISTRY = PROJECT_ROOT / "configs" / "video" / "director_registry.json"


TIER_SCORE = {
    "production_candidate": 70,
    "existing_bridge": 65,
    "preferred_local_experiment": 50,
    "backup": 35,
    "experimental": 20,
    "reference": 5,
    "reference_only": -60,
    "catalog_source": -80,
}

KIND_SCORE = {"tool": 35, "skill": 25, "project": 10, "reserve": -10}


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_registry_path(value: str, *, base: Path = PROJECT_ROOT) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def load_director_registry(path: Path = DEFAULT_DIRECTOR_REGISTRY) -> dict[str, Any]:
    payload = read_json(path)
    payload["directors"] = sorted(
        payload.get("directors") or [],
        key=lambda row: (int(row.get("order") or 999), str(row.get("lane") or "")),
    )
    return payload


def director_profile_for_lane(registry: dict[str, Any], lane: str) -> dict[str, Any]:
    matches = [row for row in registry.get("directors", []) if str(row.get("lane") or "") == lane]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one director for lane {lane}, found {len(matches)}")
    return deepcopy(matches[0])


def _project_entry(project: dict[str, Any], capability: dict[str, Any], upstream: dict[str, Any] | None = None) -> dict[str, Any]:
    execution_mode = str(capability.get("execution_mode") or "")
    scope = "advisory" if any(token in execution_mode for token in ["catalog", "advisory", "reference"]) else "execution"
    return {
        **project,
        **capability,
        "id": f"project:{project['name']}",
        "kind": "project",
        "status": project.get("dependency_status", "source_ready"),
        "scope": scope,
        **({"upstream_role": upstream.get("role"), "upstream_fit": upstream.get("dasheng_fit"), "upstream_notes": upstream.get("notes")} if upstream else {}),
    }


def _skill_entry(skill: dict[str, Any]) -> dict[str, Any]:
    return {**skill, "id": f"skill:{skill['name']}", "kind": "skill", "tier": skill.get("tier", "production_candidate")}


def _reserve_entry(candidate: dict[str, Any], upstream: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        **candidate,
        "id": f"reserve:{candidate['name']}",
        "kind": "reserve",
        "status": candidate.get("dependency_status", "reserve_candidate"),
        "scope": "advisory",
        "local_path": candidate.get("local_source_path", ""),
        **({"upstream_role": upstream.get("role"), "upstream_fit": upstream.get("dasheng_fit"), "upstream_notes": upstream.get("notes")} if upstream else {}),
    }


def _tool_entry(tool: dict[str, Any]) -> dict[str, Any]:
    return {
        **tool,
        "id": f"tool:{tool['name']}",
        "kind": "tool",
        "scope": tool.get("scope", "execution"),
        "status": tool.get("status", "ready"),
        "tier": tool.get("tier", "production_candidate"),
    }


def load_unified_registry(
    tool_registry_path: Path = DEFAULT_TOOL_REGISTRY,
    project_registry_path: Path = DEFAULT_PROJECT_REGISTRY,
) -> dict[str, Any]:
    tool_registry = read_json(tool_registry_path)
    project_registry = read_json(project_registry_path)
    capability_index = project_registry.get("project_capability_index") or {}
    upstream_source = str((tool_registry.get("catalog_sources") or {}).get("upstream_video_skills") or "")
    upstream_records: list[dict[str, Any]] = []
    if upstream_source:
        upstream_path = resolve_registry_path(upstream_source)
        if upstream_path.exists():
            upstream_records = read_json(upstream_path).get("repositories") or []
    upstream_index = {str(item.get("name")): item for item in upstream_records}

    projects = []
    for project in project_registry.get("projects", []):
        capability = capability_index.get(project.get("name"), {})
        projects.append(_project_entry(project, capability, upstream_index.get(str(project.get("name")))))

    reserves = [
        _reserve_entry(candidate, upstream_index.get(str(candidate.get("name"))))
        for candidate in project_registry.get("reserve_candidates", [])
    ]
    skills = [_skill_entry(skill) for skill in tool_registry.get("skills", [])]
    tools = [_tool_entry(tool) for tool in tool_registry.get("tools", [])]
    entries = [*tools, *skills, *projects, *reserves]
    return {
        "schema_version": "dasheng.video.unified_technical_registry.v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "tool_registry_schema": tool_registry.get("schema_version"),
        "project_registry_schema": project_registry.get("schema_version"),
        "routing_policy": tool_registry.get("routing_policy") or {},
        "tools": tools,
        "skills": skills,
        "projects": projects,
        "reserve_candidates": reserves,
        "entries": entries,
        "rejected_projects": project_registry.get("rejected") or [],
        "upstream_records": upstream_records,
    }


def missing_required_env(entry: dict[str, Any]) -> list[str]:
    return [name for name in entry.get("required_env", []) if not os.getenv(str(name))]


def allowed_provider_ids(policy: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    provider_policy = policy.get("provider_policy") or {}
    for row in provider_policy.get("allowed_first_party_model_providers") or []:
        ids.add(str(row.get("id") or "").lower())
        ids.update(str(alias).lower() for alias in row.get("aliases") or [])
    return {value for value in ids if value}


def provider_policy_violation(entry: dict[str, Any], policy: dict[str, Any]) -> str | None:
    if entry.get("requires_desktop_app") or entry.get("requires_local_app_backend"):
        return "additional_app_required"

    provider_policy = policy.get("provider_policy") or {}
    blocked = {
        str(value).lower()
        for value in provider_policy.get("blocked_third_party_service_providers") or []
    }
    declared = {
        str(value).lower()
        for value in [entry.get("provider_family"), entry.get("provider"), *(entry.get("providers") or [])]
        if value
    }
    if entry.get("provider_class") == "third_party_service" or declared.intersection(blocked):
        return "third_party_service_provider"

    if entry.get("provider_class") == "first_party_model":
        allowed = allowed_provider_ids(policy)
        eligible = {str(value).lower() for value in entry.get("allowed_providers") or []}
        eligible.update(declared)
        if eligible and not eligible.issubset(allowed):
            return "provider_not_allowlisted"
    return None


def availability(entry: dict[str, Any], policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = policy or {}
    status = str(entry.get("status") or "ready").lower()
    if entry.get("execution_enabled") is False or "deferred" in status:
        return {"state": "blocked", "reason": status or "execution_disabled"}
    missing_env = missing_required_env(entry)
    provider_violation = provider_policy_violation(entry, policy)
    if provider_violation:
        return {"state": "blocked", "reason": provider_violation}
    if missing_env:
        return {"state": "blocked", "reason": f"missing_env:{','.join(missing_env)}"}
    if entry.get("kind") == "reserve":
        if any(token in status for token in ["upstream_only", "adapter_required", "not_cloned", "missing"]):
            return {"state": "blocked", "reason": status}
        return {"state": "fallback", "reason": "reserve_candidate_not_promoted"}
    if "reference_only" in status:
        return {"state": "reference", "reason": "reference_only"}
    for token in ["runtime_incomplete", "needs_desktop_app", "server_stack_not_installed"]:
        if token in status:
            return {"state": "blocked", "reason": token}
    for token in ["needs_api_key", "needs_model_access", "needs_provider_keys", "needs_login"]:
        if token in status:
            if token != "needs_login" and entry.get("provider_class") == "first_party_model":
                continue
            if entry.get("required_env") and not missing_env:
                continue
            return {"state": "blocked", "reason": token}
    if entry.get("kind") == "project" and any(token in status for token in ["cloned", "source_ready", "skill_ready"]):
        return {"state": "fallback", "reason": status}
    if any(token in status for token in ["warning", "audit", "experimental", "benchmark", "optional", "reference"]):
        return {"state": "fallback", "reason": status}
    return {"state": "ready", "reason": status}


def score_entry(entry: dict[str, Any], *, lane: str, policy: dict[str, Any] | None = None) -> int:
    result = KIND_SCORE.get(str(entry.get("kind")), 0)
    result += TIER_SCORE.get(str(entry.get("tier") or "production_candidate"), 0)
    scope = str(entry.get("scope") or "execution")
    if scope == "execution":
        result += 20
    elif scope == "review":
        result -= 5
    if lane in (entry.get("lanes") or []):
        result += 15
    if str(entry.get("name") or "").startswith("dasheng-"):
        result += 25
    if entry.get("enabled_by_default") is False:
        result -= 25
    state = availability(entry, policy)["state"]
    result += {"ready": 25, "fallback": 5, "reference": -30, "blocked": -100}.get(state, 0)
    result += int(entry.get("priority", 0) or 0)
    return result


def compact_entry(entry: dict[str, Any], *, lane: str, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    state = availability(entry, policy)
    payload = {
        "id": entry["id"],
        "name": entry["name"],
        "kind": entry["kind"],
        "scope": entry.get("scope", "execution"),
        "status": entry.get("status", "ready"),
        "availability": state["state"],
        "reason": state["reason"],
        "score": score_entry(entry, lane=lane, policy=policy),
    }
    for key in ["path", "root", "local_path", "command", "python", "endpoint", "skill", "source_project", "required_env", "provider_class", "provider_family", "allowed_providers", "blocked_providers"]:
        value = entry.get(key)
        if value is not None and value != "" and value != []:
            payload[key] = value
    return payload


def candidates_for_capability(registry: dict[str, Any], capability: str, *, lane: str) -> list[dict[str, Any]]:
    policy = registry.get("routing_policy") or {}
    candidates = [
        entry
        for entry in registry["entries"]
        if capability in (entry.get("capabilities") or [])
        and (not entry.get("lanes") or lane in entry.get("lanes", []))
    ]
    candidates.sort(key=lambda entry: (-score_entry(entry, lane=lane, policy=policy), str(entry.get("id"))))
    return candidates


def route_capability(registry: dict[str, Any], capability: str, *, lane: str) -> dict[str, Any]:
    candidates = candidates_for_capability(registry, capability, lane=lane)
    policy = registry.get("routing_policy") or {}
    execution_ready = [
        entry
        for entry in candidates
        if entry.get("scope", "execution") in {"execution", "review"} and availability(entry, policy)["state"] == "ready"
    ]
    fallback = [
        entry
        for entry in candidates
        if entry.get("scope", "execution") in {"execution", "review"} and availability(entry, policy)["state"] == "fallback"
    ]
    advisors = [entry for entry in candidates if entry.get("scope") in {"advisory", "review"} and availability(entry, policy)["state"] != "blocked"]
    blocked = [entry for entry in candidates if availability(entry, policy)["state"] in {"blocked", "reference"}]

    primary = compact_entry(execution_ready[0], lane=lane, policy=policy) if execution_ready else None
    fallback_pool = [*execution_ready[1:], *fallback]
    return {
        "capability": capability,
        "primary": primary,
        "fallbacks": [compact_entry(entry, lane=lane, policy=policy) for entry in fallback_pool[:4]],
        "advisors": [compact_entry(entry, lane=lane, policy=policy) for entry in advisors[:3]],
        "blocked": [compact_entry(entry, lane=lane, policy=policy) for entry in blocked[:4]],
        "status": "ready" if primary else ("fallback_only" if fallback_pool else ("blocked_only" if blocked else "unresolved")),
    }


def infer_scene_capabilities(scene: dict[str, Any], *, lane: str) -> list[str]:
    motion = scene.get("motion") or {}
    motion_text = json.dumps(motion, ensure_ascii=False) if isinstance(motion, dict) else str(motion)
    text = " ".join(
        str(scene.get(key) or "")
        for key in ["title", "beat_class", "content_part", "shot", "template_id", "html_animation_behavior", "evidence_authenticity", "narrative_function", "visual_grammar", "production_route"]
    ).lower()
    text = f"{text} {motion_text.lower()}"
    capabilities = {"motion_design", "visual_design"}
    if lane == "explainer_html_video":
        capabilities.update({"html_video", "remotion_render", "final_render"})
    elif lane == "vox_explainer_video":
        capabilities.update({"html_video", "remotion_render", "final_render", "editorial_collage", "reference_download", "reusable_footage"})
    elif lane == "talking_head_video":
        capabilities.update({"talking_head_packaging", "subtitle_motion", "broll_routing"})
    elif lane == "digital_human_video":
        capabilities.update({"digital_human_composition", "subtitle_motion", "remotion_render", "final_render"})
    elif lane == "commercial_promo_video":
        capabilities.update(
            {
                "brand_system",
                "product_showcase",
                "product_asset_routing",
                "commercial_edit",
                "subtitle_motion",
                "remotion_render",
                "final_render",
            }
        )
    elif lane == "cinematic_short_drama_video":
        capabilities.update({"cinematic_camera", "continuity_edit", "remotion_render", "final_render"})

    keyword_capabilities = {
        "dynamic_chart": ["chart", "graph", "data", "kpi", "ticker", "evidence_data", "数据", "图表"],
        "animated_financial_display": ["finance", "valuation", "price", "multiple", "market", "估值", "股价", "财务"],
        "document_visualization": ["document", "source", "pdf", "filing", "evidence_document", "文件", "公告"],
        "kinetic_typography": ["hook", "title", "quote", "headline", "recap", "标题", "金句"],
        "generated_broll": ["broll", "cutaway", "collage", "示意", "资料片"],
        "video_download": ["real_broll", "real-broll", "real_video", "broll_fullscreen", "broll", "真实视频"],
        "reference_download": ["real_broll", "real-broll", "real_video", "broll_fullscreen", "broll", "真实视频"],
        "conceptual_illustration": ["schematic", "logic", "metaphor", "illustration", "概念", "逻辑"],
        "lottie_asset": ["lottie", "sticker", "icon", "贴纸", "图标"],
        "reusable_footage": ["archive", "footage", "news", "纪录片", "资料片", "real_broll", "real-broll", "broll"],
        "social_card": ["card", "poster", "cover", "卡片", "封面"],
        "claims_compliance": ["proof", "offer", "price", "comparison", "证明", "优惠", "价格", "对比"],
        "product_showcase": ["product", "product_promise", "feature_benefit", "产品", "卖点", "功能"],
        "brand_system": ["brand", "logo", "brand_memory", "cta", "品牌", "标志"],
    }
    for capability, tokens in keyword_capabilities.items():
        if any(token in text for token in tokens):
            capabilities.add(capability)
    if isinstance(motion, dict) and motion.get("shotcraft_card"):
        capabilities.update({"shotcraft_binding", "shot_recipe_library"})
    return sorted(capabilities)


def _unique_selected(routes: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
    seen: set[str] = set()
    selected: list[dict[str, Any]] = []
    for route in routes:
        if field == "primary":
            values = [route[field]] if route.get(field) else []
        else:
            values = route.get(field) or []
        for value in values:
            if value and value["id"] not in seen:
                seen.add(value["id"])
                selected.append(value)
    return selected


def route_scene(scene: dict[str, Any], registry: dict[str, Any], *, lane: str) -> dict[str, Any]:
    required = infer_scene_capabilities(scene, lane=lane)
    routes = [route_capability(registry, capability, lane=lane) for capability in required]
    return {
        "required_capabilities": required,
        "capability_routes": routes,
        "primary_stack": _unique_selected(routes, "primary"),
        "fallback_stack": _unique_selected(routes, "fallbacks")[:8],
        "unresolved_capabilities": [route["capability"] for route in routes if route["status"] == "unresolved"],
    }


def build_stage_routes(
    registry: dict[str, Any],
    *,
    lane: str,
    director_profile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stages = {}
    policy = registry.get("routing_policy", {})
    stage_capabilities = (
        (director_profile or {}).get("stage_capabilities")
        or (policy.get("lane_stage_capabilities") or {}).get(lane)
        or policy.get("stage_capabilities")
        or {}
    )
    for stage, capabilities in stage_capabilities.items():
        routes = [route_capability(registry, capability, lane=lane) for capability in capabilities]
        stages[stage] = {
            "capability_routes": routes,
            "primary_stack": _unique_selected(routes, "primary"),
            "fallback_stack": _unique_selected(routes, "fallbacks")[:12],
            "unresolved_capabilities": [route["capability"] for route in routes if route["status"] == "unresolved"],
            "blocked_capabilities": [route["capability"] for route in routes if route["status"] == "blocked_only"],
        }
    return stages


def apply_routes_to_scene_plan(
    scene_plan: dict[str, Any],
    *,
    tool_registry_path: Path = DEFAULT_TOOL_REGISTRY,
    project_registry_path: Path = DEFAULT_PROJECT_REGISTRY,
    director_registry_path: Path = DEFAULT_DIRECTOR_REGISTRY,
) -> tuple[dict[str, Any], dict[str, Any]]:
    registry = load_unified_registry(tool_registry_path, project_registry_path)
    director_registry = load_director_registry(director_registry_path)
    routed = deepcopy(scene_plan)
    lane = str(routed.get("lane") or "explainer_html_video")
    director_profile = director_profile_for_lane(director_registry, lane)
    scene_routes = []
    for scene in routed.get("scenes", []):
        route = route_scene(scene, registry, lane=lane)
        scene["tool_routing"] = route
        scene_routes.append({"scene_id": scene.get("id"), **route})

    plan = {
        "schema_version": "dasheng.video.tool_routing_plan.v1",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "lane": lane,
        "director_profile": director_profile,
        "registry_summary": {
            "tools": len(registry["tools"]),
            "skills": len(registry["skills"]),
            "projects": len(registry["projects"]),
            "reserve_candidates": len(registry["reserve_candidates"]),
            "rejected_projects": len(registry["rejected_projects"]),
            "upstream_records": len(registry["upstream_records"]),
            "directors": len(director_registry.get("directors", [])),
        },
        "stage_routes": build_stage_routes(registry, lane=lane, director_profile=director_profile),
        "scene_routes": scene_routes,
    }
    routed["director_tool_routing"] = {
        "schema_version": plan["schema_version"],
        "director_id": director_profile["id"],
        "director_status": director_profile.get("status"),
        "pipeline_id": director_profile.get("pipeline_id"),
        "registry_summary": plan["registry_summary"],
        "stage_route_names": list(plan["stage_routes"]),
    }
    return routed, plan


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Route a scene plan through all registered video tools, Skills, and reserved projects.")
    parser.add_argument("--scene-plan", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--routed-scene-plan", default="")
    parser.add_argument("--tool-registry", default=str(DEFAULT_TOOL_REGISTRY))
    parser.add_argument("--project-registry", default=str(DEFAULT_PROJECT_REGISTRY))
    parser.add_argument("--director-registry", default=str(DEFAULT_DIRECTOR_REGISTRY))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    scene_plan = read_json(Path(args.scene_plan).expanduser().resolve())
    routed, plan = apply_routes_to_scene_plan(
        scene_plan,
        tool_registry_path=Path(args.tool_registry).expanduser().resolve(),
        project_registry_path=Path(args.project_registry).expanduser().resolve(),
        director_registry_path=Path(args.director_registry).expanduser().resolve(),
    )
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.routed_scene_plan:
        routed_path = Path(args.routed_scene_plan).expanduser().resolve()
        routed_path.parent.mkdir(parents=True, exist_ok=True)
        routed_path.write_text(json.dumps(routed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "routing_plan": str(output), "scenes": len(plan["scene_routes"])}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
