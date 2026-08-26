#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from canonical_workflow import (
    CANONICAL_STAGES,
    OPTIONAL_ASSET_ROOTS,
    CANONICAL_MANIFEST_FILENAMES,
    canonical_manifest_path,
    canonical_stage_dir,
    ensure_json_file,
    stage_contract_snapshot,
)
from provider_registry import resolve_chat_provider
from path_config import (
    get_desktop_root,
    get_project_root,
    get_feishu_config_path,
    get_feishu_bot_config_path,
    get_feishu_stage_contract_path,
)


ROOT = get_project_root()
FEISHU_CONFIG_FILES = [
    get_feishu_config_path(),
    get_feishu_bot_config_path(),
    get_feishu_stage_contract_path(),
]
LEGACY_SKILL_DIRS = [
    ROOT / "skills" / "dasheng-daily-brief",
    ROOT / "skills" / "dasheng-daily-clustering",
    ROOT / "skills" / "dasheng-daily-outline",
    ROOT / "skills" / "dasheng-daily-final",
    ROOT / "skills" / "dasheng-stage-distribute",
    ROOT / "skills" / "dasheng-stage-intake-brief-draft",
    ROOT / "skills" / "dasheng-stage-publish-video",
    ROOT / "skills" / "dasheng-stage-rewrite",
    ROOT / "skills" / "dasheng-collection-workflow",
    ROOT / "skills" / "dasheng-sop-orchestrator",
]
# 旧版按环节分目录的结构名（2026-08 前的桌面结构与项目内 产物/ 镜像），保留用于诊断旧产物
LEGACY_STAGE_DIR_NAMES: dict[str, str] = {
    "intake": "01_内容采集",
    "brief": "02_内容聚合及选题分析",
    "draft": "05_初稿生成",
    "transwrite": "06_转写生产",
    "publish": "07_发布执行",
    "postmortem": "08_分析复盘",
}
LEGACY_STAGE_ROOTS = {
    stage: ROOT / "产物" / name for stage, name in LEGACY_STAGE_DIR_NAMES.items()
}
LEGACY_OPTIONAL_ASSET_ROOTS = {
    asset: ROOT / "产物" / root.name
    for asset, root in OPTIONAL_ASSET_ROOTS.items()
}
GATE_FILENAMES = {
    "intake": "intake_review.json",
    "brief": "selected_topics.json",
    "draft": "final_structure_snapshot.json",
    "transwrite": "transwrite_decision.json",
    "publish": "publish_decision.json",
}


def mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    secret = str(value)
    if len(secret) <= 8:
        return "*" * len(secret)
    return f"{secret[:4]}***{secret[-4:]}"


def discover_latest_run_id() -> str | None:
    candidates: dict[str, float] = {}
    # 新结构：任务文件夹直接位于桌面根下；另扫全局资产目录与旧版结构
    search_roots = [
        get_desktop_root(),
        *OPTIONAL_ASSET_ROOTS.values(),
        *LEGACY_STAGE_ROOTS.values(),
        *LEGACY_OPTIONAL_ASSET_ROOTS.values(),
    ]
    for root in search_roots:
        if not root.exists():
            continue
        for stage_dir in root.iterdir():
            if not stage_dir.is_dir() or stage_dir.name.startswith((".", "_", "0")):
                continue
            stat = stage_dir.stat()
            candidates[stage_dir.name] = max(candidates.get(stage_dir.name, 0.0), stat.st_mtime)
    if not candidates:
        return None
    return sorted(candidates.items(), key=lambda item: item[1], reverse=True)[0][0]


def _stage_dir_candidates(stage: str, run_id: str) -> list[Path]:
    return [
        canonical_stage_dir(stage, run_id),
        LEGACY_STAGE_ROOTS[stage] / run_id,
    ]


def _optional_asset_dir_candidates(asset: str, run_id: str) -> list[Path]:
    return [
        OPTIONAL_ASSET_ROOTS[asset] / run_id,
        LEGACY_OPTIONAL_ASSET_ROOTS[asset] / run_id,
    ]


def _first_existing_or_default(paths: list[Path]) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[0]


def doctor_stage_contract_snapshot(run_id: str) -> dict[str, Any]:
    """Build a doctor view that can inspect current desktop outputs and legacy project outputs."""
    contract = stage_contract_snapshot(run_id)
    for stage in CANONICAL_STAGES:
        stage_dir = _first_existing_or_default(_stage_dir_candidates(stage, run_id))
        manifest_path = stage_dir / CANONICAL_MANIFEST_FILENAMES[stage]
        gate_path = stage_dir / GATE_FILENAMES[stage] if stage in GATE_FILENAMES else None
        contract["stages"][stage] = {
            "stage_dir": str(stage_dir),
            "manifest_path": str(manifest_path),
            "manifest_exists": manifest_path.exists(),
            "gate_path": str(gate_path) if gate_path else None,
            "gate_exists": gate_path.exists() if gate_path else None,
        }
    return contract


def load_manifest_if_exists(stage: str, run_id: str) -> dict[str, Any] | None:
    path = _first_existing_or_default([
        canonical_manifest_path(stage, run_id),
        LEGACY_STAGE_ROOTS[stage] / run_id / CANONICAL_MANIFEST_FILENAMES[stage],
    ])
    if not path.exists():
        return None
    try:
        return ensure_json_file(path, f"{stage}_manifest.json")
    except Exception as exc:
        return {
            "_invalid": True,
            "status": "invalid",
            "error": str(exc),
            "path": str(path),
        }


def load_optional_asset_manifest(path: Path, asset: str) -> dict[str, Any]:
    try:
        return ensure_json_file(path, f"{asset}_manifest.json")
    except Exception as exc:
        return {
            "_invalid": True,
            "status": "invalid",
            "error": str(exc),
            "path": str(path),
        }


def discover_optional_asset_manifests(asset: str, run_id: str) -> list[dict[str, Any]]:
    manifest_name = f"{asset}_manifest.json"
    manifests: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for root in _optional_asset_dir_candidates(asset, run_id):
        if not root.exists():
            continue
        for path in sorted(root.glob(f"**/{manifest_name}")):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            payload = load_optional_asset_manifest(path, asset)
            manifests.append(
                {
                    "path": str(path),
                    "status": payload.get("status"),
                    "profile_name": payload.get("profile_name"),
                    "analysis_mode": payload.get("analysis_mode"),
                    "invalid": bool(payload.get("_invalid")),
                    "error": payload.get("error"),
                }
            )
    return manifests


def optional_assets_report(run_id: str) -> dict[str, Any]:
    report: dict[str, Any] = {}
    for asset, root in OPTIONAL_ASSET_ROOTS.items():
        manifests = discover_optional_asset_manifests(asset, run_id)
        asset_dir = _first_existing_or_default(_optional_asset_dir_candidates(asset, run_id))
        report[asset] = {
            "asset_dir": str(asset_dir),
            "manifest_exists": bool(manifests),
            "manifest_count": len(manifests),
            "manifest_status": manifests[0]["status"] if len(manifests) == 1 else None,
            "manifests": manifests,
        }
    return report


def stage_issues(contract: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    stages = contract.get("stages") or {}
    for stage, row in stages.items():
        if stage == "intake":
            continue
        previous_ready = True
        if stage == "brief":
            previous_ready = bool(stages.get("intake", {}).get("manifest_exists"))
        elif stage == "draft":
            previous_ready = bool(stages.get("brief", {}).get("gate_exists"))
        elif stage == "transwrite":
            previous_ready = bool(stages.get("draft", {}).get("gate_exists"))
        elif stage == "publish":
            previous_ready = bool(stages.get("transwrite", {}).get("gate_exists"))
        elif stage == "postmortem":
            previous_ready = bool(stages.get("publish", {}).get("manifest_exists"))
        if previous_ready and not row.get("manifest_exists"):
            issues.append(f"{stage}: 上游已就绪，但本阶段 manifest 缺失")
    return issues


def provider_summary() -> dict[str, Any]:
    def sanitize(provider: dict[str, Any] | None) -> dict[str, Any] | None:
        if not provider:
            return None
        # Preserve _unavailable marker for diagnostics
        if provider.get("_unavailable"):
            return {"_unavailable": True, "status": "unavailable"}
        payload = dict(provider)
        if "api_key" in payload:
            payload["api_key"] = mask_secret(payload.get("api_key"))
            payload["api_key_present"] = bool(provider.get("api_key"))
        return payload

    return {
        "brief": sanitize(resolve_chat_provider(
            custom_env_var="DASHENG_PHASE2_PROVIDER_ENV",
            base_url_keys=["PHASE2_AI_BASE_URL", "QHAIGC_BASE_URL"],
            api_key_keys=["PHASE2_AI_API_KEY", "QHAIGC_API_KEY"],
            model_keys=["PHASE2_AI_MODEL", "PHASE3_AI_MODEL", "DRAFT_AI_MODEL"],
            timeout_keys=["PHASE2_AI_TIMEOUT_SECONDS"],
        )),
        "draft": sanitize(resolve_chat_provider(
            custom_env_var="DASHENG_DRAFT_PROVIDER_ENV",
            base_url_keys=["PHASE3_AI_BASE_URL", "DRAFT_AI_BASE_URL", "QHAIGC_BASE_URL"],
            api_key_keys=["PHASE3_AI_API_KEY", "DRAFT_AI_API_KEY", "QHAIGC_API_KEY"],
            model_keys=["PHASE3_AI_MODEL", "DRAFT_AI_MODEL", "PHASE2_AI_MODEL"],
            timeout_keys=["PHASE3_AI_TIMEOUT_SECONDS", "DRAFT_AI_TIMEOUT_SECONDS"],
        )),
        "optional_tools": {
            "draft_assets": "charts_images_and_data_are_generated_in_draft",
            "transwrite_lanes": "wechat_article_explainer_html_video_vox_explainer_video_talking_head_video_digital_human_video_commercial_promo_video_cinematic_short_drama_video_podcast",
            "rewrite_variants": "merged_into_transwrite_or_on_demand",
        },
    }


def build_report(run_id: str) -> dict[str, Any]:
    contract = doctor_stage_contract_snapshot(run_id)
    run_root = get_desktop_root() / run_id
    manifests = {stage: load_manifest_if_exists(stage, run_id) for stage in CANONICAL_STAGES}
    optional_assets = optional_assets_report(run_id)
    invalid_manifests = [
        f"{stage}: manifest 无法解析"
        for stage, manifest in manifests.items()
        if manifest and manifest.get("_invalid")
    ]
    invalid_optional_manifests = [
        f"{asset}: optional asset manifest 无法解析：{manifest['path']}"
        for asset, report in optional_assets.items()
        for manifest in report["manifests"]
        if manifest.get("invalid")
    ]
    return {
        "run_id": run_id,
        "canonical_contract": contract,
        "optional_assets": optional_assets,
        "issues": stage_issues(contract) + invalid_manifests + invalid_optional_manifests,
        "run_root": {
            "root": str(run_root),
            "exists": run_root.exists(),
        },
        "feishu": {
            "files": [{"path": str(path), "exists": path.exists()} for path in FEISHU_CONFIG_FILES],
        },
        "providers": provider_summary(),
        "legacy_skill_dirs": [{"path": str(path), "exists": path.exists()} for path in LEGACY_SKILL_DIRS],
        "stage_status": {
            stage: {
                "manifest_status": (manifest or {}).get("status"),
                "next_stage": (manifest or {}).get("next_stage"),
                "manifest_error": (manifest or {}).get("error"),
            }
            for stage, manifest in manifests.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Newma 主链 doctor / 自检")
    parser.add_argument("--run-id")
    parser.add_argument("--latest", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    run_id = args.run_id or (discover_latest_run_id() if args.latest else None)
    if not run_id:
        if args.latest:
            raise SystemExit("未找到任何可用 run；请先运行工作流，或通过 --run-id 指定要检查的运行。")
        raise SystemExit("请提供 --run-id，或使用 --latest")

    report = build_report(run_id)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.strict and report["issues"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
