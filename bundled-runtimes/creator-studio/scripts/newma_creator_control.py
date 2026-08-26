#!/usr/bin/env python3
"""Newma Creator Studio 的统一控制 Module。"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlsplit
from urllib.request import urlopen
from uuid import uuid4

import yaml

from canonical_workflow import canonical_stage_dir
from execute_publish_request import execute_request as execute_publish_request
from path_config import get_desktop_root, get_project_root
from prepare_publish_execution import build_plan as build_publish_execution_plan
from project_run_manifest import build_manifest, save_manifest
from publish_accounts import build_report as build_publish_account_report


ROOT = get_project_root()
REGISTRY_PATH = ROOT / "configs" / "workflow" / "newma_creator_studio_registry.json"
ALIAS_PATH = ROOT / "configs" / "workflow" / "newma_namespace_aliases.json"
RESERVED_PROJECTS_PATH = ROOT / "configs" / "external" / "reserved_projects.json"
RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{2,79}$")
EDITOR_EXPORT_EXTENSIONS = {".mp4", ".webm", ".mov", ".mp3", ".wav"}

# 各阶段 gate 文件（desk review-gate approve 时联动写盘，与 workflow_doctor 保持一致）
GATE_FILENAMES: dict[str, str] = {
    "intake": "intake_review.json",
    "brief": "selected_topics.json",
    "draft": "final_structure_snapshot.json",
    "transwrite": "transwrite_decision.json",
    "publish": "publish_decision.json",
}
NODE_RESULT_STATUSES = {
    "succeeded",
    "waiting_user",
    "blocked",
    "failed",
}

STATUS_MAP = {
    "pending": "pending",
    "queued": "queued",
    "running": "running",
    "pending_review": "waiting_user",
    "waiting_user": "waiting_user",
    "approved": "succeeded",
    "complete": "succeeded",
    "succeeded": "succeeded",
    "needs_revision": "changes_requested",
    "changes_requested": "changes_requested",
    "blocked": "blocked",
    "failed": "failed",
    "skipped": "skipped",
    "stale": "stale",
    "cancelled": "cancelled",
}

CLI_ADAPTERS: dict[str, dict[str, Any]] = {
    "claude": {
        "binary": "claude",
        "version_args": ["--version"],
        "args": ["--print"],
        "prompt_via_stdin": True,
    },
    "codex": {
        "binary": "codex",
        "version_args": ["--version"],
        "args": ["exec", "--skip-git-repo-check"],
        "prompt_via_stdin": True,
    },
    "gemini": {
        "binary": "gemini",
        "version_args": ["--version"],
        "args": [],
        "prompt_via_stdin": True,
    },
    "cursor-agent": {
        "binary": "cursor-agent",
        "version_args": ["--version"],
        "args": ["--print"],
        "prompt_via_stdin": True,
    },
    "opencode": {
        "binary": "opencode",
        "version_args": ["--version"],
        "args": ["run"],
        "prompt_via_stdin": True,
    },
    "qwen": {
        "binary": "qwen",
        "version_args": ["--version"],
        "args": [],
        "prompt_via_stdin": True,
    },
    "qoder-cli": {
        "binary": "qodercli",
        "version_args": ["-v"],
        "args": ["-p", "-"],
        "prompt_via_stdin": True,
    },
    "hermes": {
        "binary": "hermes",
        "version_args": ["version"],
        "args": ["chat", "-Q", "-q"],
        "prompt_via_stdin": False,
        "prompt_as_last_arg": True,
    },
}


def approve_stage_gate(run_id: str, stage: str, gate_file: str = "", selected_ids: str = "") -> dict[str, Any]:
    """把阶段 gate 文件状态翻 approved（desk review-gate approve 联动写盘）。

    selected_ids 非空且为选题 gate（brief/selected_topics.json）时，
    先把选择结果写入 gate 文件（从 topic_cards.json 拉所选卡），再翻 approved。
    """
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError(f"run_id 格式不安全：{run_id}")
    if gate_file:
        path = Path(gate_file).expanduser().resolve()
    else:
        filename = GATE_FILENAMES.get(stage)
        if not filename:
            raise ValueError(f"未定义阶段 gate 文件：{stage}")
        path = canonical_stage_dir(stage, run_id) / filename
    chosen = [item.strip() for item in selected_ids.split(",") if item.strip()]
    if not path.is_file():
        # gate 文件尚未生成：带选题选择时直接创建（UI 直批路径无需 AI 预生成骨架）
        if chosen and stage == "brief" and path.name == "selected_topics.json":
            cards_path = canonical_stage_dir("brief", run_id) / "topic_cards.json"
            cards_payload = read_json(cards_path) if cards_path.is_file() else {}
            cards = (
                cards_payload.get("topic_cards", [])
                if isinstance(cards_payload, dict)
                else cards_payload
            )
            selected_cards = [
                card for card in cards if str(card.get("topic_id", "")) in chosen
            ]
            payload = {
                "schema_version": "newma.brief_selected_topics.v1",
                "run_id": run_id,
                "stage": "brief",
                "status": "approved",
                "selected_topic_ids": chosen,
                "selected_topics": selected_cards,
                "selected_at": now_iso(),
                "approved_at": now_iso(),
            }
            write_json(path, payload)
            return {
                "status": "created",
                "gate_file": str(path),
                "stage": stage,
                "previous_status": None,
                "selected_topic_ids": chosen,
            }
        return {"status": "missing", "gate_file": str(path), "stage": stage}
    payload = read_json(path)
    if not isinstance(payload, dict):
        return {"status": "invalid", "gate_file": str(path), "stage": stage}
    previous = payload.get("status")
    if chosen and path.name == "selected_topics.json":
        cards_path = canonical_stage_dir("brief", run_id) / "topic_cards.json"
        cards_payload = read_json(cards_path) if cards_path.is_file() else {}
        cards = (
            cards_payload.get("topic_cards", [])
            if isinstance(cards_payload, dict)
            else cards_payload
        )
        selected_cards = [
            card for card in cards if str(card.get("topic_id", "")) in chosen
        ]
        payload["selected_topic_ids"] = chosen
        payload["selected_topics"] = selected_cards
        payload["selected_at"] = now_iso()
    payload["status"] = "approved"
    payload["approved_at"] = now_iso()
    write_json(path, payload)
    return {
        "status": "succeeded",
        "gate_file": str(path),
        "stage": stage,
        "previous_status": previous,
        "selected_topic_ids": chosen or None,
    }


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def emit(payload: dict[str, Any], output: str = "") -> None:
    if output:
        write_json(Path(output).expanduser().resolve(), payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def load_registry() -> dict[str, Any]:
    return read_json(REGISTRY_PATH)


def load_aliases() -> dict[str, Any]:
    return read_json(ALIAS_PATH)


def canonical_id(value: str) -> str:
    if value.startswith("dasheng-"):
        return "newma-" + value[len("dasheng-") :]
    if value.startswith("dasheng_"):
        return "newma_" + value[len("dasheng_") :]
    return value


def runtime_skill_id(value: str) -> str:
    return str(load_aliases().get("skill_aliases", {}).get(value, value))


def expand_config_value(value: str) -> str:
    match = re.match(r"^\$\{([A-Z0-9_]+):-([^}]+)\}(.*)$", value)
    if match:
        variable, fallback, suffix = match.groups()
        value = f"{os.environ.get(variable, fallback)}{suffix}"
    return value


def resolve_config_path(value: str) -> Path:
    value = expand_config_value(value)
    path = Path(value).expanduser()
    return path if path.is_absolute() else (ROOT / path).resolve()


def resolve_editor_project(adapter: dict[str, Any]) -> tuple[Path, list[Path]]:
    configured = adapter.get("project_candidates") or [adapter.get("project_path")]
    candidates = [
        resolve_config_path(str(value))
        for value in configured
        if str(value or "").strip()
    ]
    if not candidates:
        candidates = [ROOT]
    return next((path for path in candidates if path.is_dir()), candidates[0]), candidates


def resolve_editor_command(adapter: dict[str, Any]) -> tuple[list[str], str | None]:
    configured = adapter.get("command_candidates") or [adapter.get("command")]
    fallback: list[str] = []
    for value in configured:
        if not isinstance(value, list) or not value:
            continue
        command = [expand_config_value(str(item)) for item in value]
        fallback = fallback or command
        binary_value = command[0]
        binary_path = Path(binary_value).expanduser()
        binary = str(binary_path) if binary_path.is_file() else shutil.which(binary_value)
        if binary:
            command[0] = binary
            return command, binary
    return fallback, None


def normalized_status(value: Any) -> str:
    return STATUS_MAP.get(str(value or "pending"), "pending")


def normalized_artifact_status(value: Any) -> str:
    status = str(value or "planned")
    if status in {"planned", "created", "approved", "superseded", "failed", "stale"}:
        return status
    return normalized_status(status)


def stage_definition(registry: dict[str, Any], stage_id: str) -> dict[str, Any]:
    for stage in registry.get("stages", []):
        if stage.get("id") == stage_id:
            return stage
    raise KeyError(f"未知阶段：{stage_id}")


def node_definition(registry: dict[str, Any], stage_id: str, node_id: str) -> dict[str, Any]:
    stage = stage_definition(registry, stage_id)
    for node in stage.get("nodes", []):
        if node.get("id") == node_id:
            return node
    raise KeyError(f"未知节点：{stage_id}/{node_id}")


def material_from_pair(value: str) -> dict[str, Any]:
    if "=" not in value:
        raise ValueError(f"素材必须使用 type=value：{value}")
    material_type, material_value = value.split("=", 1)
    material_type = material_type.strip()
    material_value = material_value.strip()
    if not material_type or not material_value:
        raise ValueError(f"素材必须使用 type=value：{value}")
    return {"type": material_type, "path": material_value, "source": "manual"}


def artifact_materials(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for artifact in manifest.get("artifacts", []):
        if normalized_status(artifact.get("status")) in {"failed", "cancelled", "stale"}:
            continue
        rows.append(
            {
                "type": str(artifact.get("type") or "artifact"),
                "path": str(artifact.get("path") or ""),
                "source": "upstream",
                "artifact_id": artifact.get("id"),
                "stage": artifact.get("stage"),
                "node_id": artifact.get("node_id"),
            }
        )
    return rows


def material_matches(requirement: dict[str, Any], material: dict[str, Any]) -> bool:
    material_type = str(material.get("type") or "")
    if material_type == str(requirement.get("type")):
        return True
    if material_type not in {"file", "source", "url", "artifact"}:
        return False
    value = str(material.get("path") or "").lower()
    accepts = [str(item).lower() for item in requirement.get("accepts", [])]
    if value.startswith(("http://", "https://")) and "url" in accepts:
        return True
    return any(item.startswith(".") and value.endswith(item) for item in accepts)


def validate_node_materials(
    registry: dict[str, Any],
    stage_id: str,
    node_id: str,
    materials: list[dict[str, Any]],
    *,
    allow_manual_bootstrap: bool = False,
) -> dict[str, Any]:
    node = node_definition(registry, stage_id, node_id)
    bindings: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    for requirement in node.get("material_requirements", []):
        allowed_sources = set(requirement.get("sources") or ["manual", "upstream"])
        if allow_manual_bootstrap:
            allowed_sources.add("manual")
        match = next(
            (
                item
                for item in materials
                if str(item.get("source") or "manual") in allowed_sources
                and str(item.get("status") or "active")
                not in {"stale", "superseded", "failed"}
                and material_matches(requirement, item)
            ),
            None,
        )
        if match:
            bindings.append(
                {
                    "requirement_type": requirement.get("type"),
                    "label": requirement.get("label"),
                    "material": match,
                }
            )
        elif requirement.get("required"):
            missing.append(
                {
                    "type": requirement.get("type"),
                    "label": requirement.get("label"),
                    "accepts": requirement.get("accepts", []),
                    "sources": sorted(allowed_sources),
                }
            )
    return {
        "status": "ready" if not missing else "needs_material",
        "stage_id": stage_id,
        "node_id": node_id,
        "bindings": bindings,
        "missing": missing,
    }


def infer_current_node(stage: dict[str, Any], stage_run: dict[str, Any]) -> str | None:
    current = stage_run.get("current_node") or stage_run.get("current_node_id")
    if current:
        return str(current)
    status = normalized_status(stage_run.get("status"))
    if status in {"waiting_user", "changes_requested"}:
        for node in stage.get("nodes", []):
            if (node.get("gate") or {}).get("required"):
                return str(node.get("id"))
    if status in {"running", "blocked", "failed", "stale"}:
        nodes = stage.get("nodes", [])
        return str(nodes[0].get("id")) if nodes else None
    return None


def artifact_node_id(stage: dict[str, Any], artifact: dict[str, Any]) -> str | None:
    if artifact.get("node_id"):
        return str(artifact["node_id"])
    artifact_type = artifact.get("type")
    for node in stage.get("nodes", []):
        if artifact_type in node.get("outputs", []):
            return str(node.get("id"))
    return None


def build_notifications(
    stage_rows: list[dict[str, Any]], artifacts: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    notifications: list[dict[str, Any]] = []
    for stage in stage_rows:
        for node in stage.get("nodes", []):
            status = node.get("status")
            if status == "waiting_user":
                notifications.append(
                    {
                        "id": f"review:{stage['id']}:{node['id']}",
                        "kind": "review",
                        "level": "action",
                        "title": f"{node['name']}待审核",
                        "stage_id": stage["id"],
                        "node_id": node["id"],
                    }
                )
            elif status in {"blocked", "failed", "changes_requested", "stale"}:
                notifications.append(
                    {
                        "id": f"warning:{stage['id']}:{node['id']}",
                        "kind": "warning",
                        "level": "warning",
                        "title": f"{node['name']}：{status}",
                        "stage_id": stage["id"],
                        "node_id": node["id"],
                    }
                )
    for artifact in artifacts[-8:]:
        if artifact.get("status") in {"created", "approved", "succeeded"}:
            notifications.append(
                {
                    "id": f"artifact:{artifact.get('id')}",
                    "kind": "artifact",
                    "level": "info",
                    "title": f"新交付物：{artifact.get('type')}",
                    "stage_id": artifact.get("stage"),
                    "artifact_id": artifact.get("id"),
                    "path": artifact.get("path"),
                }
            )
    return notifications


def build_snapshot(manifest: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    manifest_stages = {
        str(row.get("id") or row.get("name")): row for row in manifest.get("stages", [])
    }
    node_runs = {
        (str(row.get("stage_id") or row.get("stage")), str(row.get("node_id") or row.get("node"))): row
        for row in manifest.get("node_runs", [])
    }
    artifacts = [dict(row, status=normalized_artifact_status(row.get("status"))) for row in manifest.get("artifacts", [])]
    stage_rows: list[dict[str, Any]] = []
    graph_nodes: list[dict[str, Any]] = []
    graph_edges: list[dict[str, Any]] = []

    previous_stage_id: str | None = None
    for stage in registry.get("stages", []):
        stage_id = str(stage["id"])
        stage_run = manifest_stages.get(stage_id, {"status": "pending"})
        stage_status = normalized_status(stage_run.get("status"))
        current_node = infer_current_node(stage, stage_run)
        completed_nodes = set(stage_run.get("completed_nodes") or [])
        nodes: list[dict[str, Any]] = []
        previous_node_id: str | None = None
        for node in stage.get("nodes", []):
            node_id = str(node["id"])
            node_run = node_runs.get((stage_id, node_id))
            if node_run:
                node_status = normalized_status(node_run.get("status"))
            elif stage_status in {"succeeded", "skipped", "cancelled"}:
                node_status = stage_status
            elif node_id in completed_nodes:
                node_status = "succeeded"
            elif node_id == current_node:
                node_status = stage_status
            else:
                node_status = "pending"
            node_artifacts = [
                item for item in artifacts if item.get("stage") == stage_id and artifact_node_id(stage, item) == node_id
            ]
            row = {
                "id": node_id,
                "name": node.get("name"),
                "description": node.get("description"),
                "status": node_status,
                "progress": (
                    node_run.get("progress")
                    if node_run and node_run.get("progress") is not None
                    else (100 if node_status in {"succeeded", "skipped"} else 0)
                ),
                "gate": node.get("gate"),
                "artifact_count": len(node_artifacts),
                "artifacts": node_artifacts,
                "actions": node.get("actions", []),
                "capabilities": node.get("capabilities", []),
                "editors": node.get("editors", []),
                "material_requirements": node.get("material_requirements", []),
            }
            nodes.append(row)
            graph_id = f"{stage_id}.{node_id}"
            graph_nodes.append({"id": graph_id, "stage_id": stage_id, "node_id": node_id, "status": node_status, "label": node.get("name")})
            if previous_node_id:
                graph_edges.append({"from": f"{stage_id}.{previous_node_id}", "to": graph_id, "kind": "node"})
            previous_node_id = node_id
        completed = sum(1 for row in nodes if row["status"] in {"succeeded", "skipped"})
        progress = (
            int(stage_run["progress"])
            if stage_run.get("progress") is not None
            else (round((completed / len(nodes)) * 100) if nodes else 0)
        )
        stage_rows.append(
            {
                "order": stage.get("order"),
                "id": stage_id,
                "name": stage.get("name"),
                "short_label": stage.get("short_label"),
                "color": stage.get("color"),
                "status": stage_status,
                "progress": progress,
                "nodes": nodes,
            }
        )
        if previous_stage_id:
            graph_edges.append({"from": previous_stage_id, "to": stage_id, "kind": "stage"})
        previous_stage_id = stage_id

    notifications = build_notifications(stage_rows, artifacts)
    active = next(
        (
            row
            for row in stage_rows
            if row["status"] in {"running", "waiting_user", "changes_requested", "blocked", "failed", "stale"}
        ),
        next((row for row in stage_rows if row["status"] == "pending"), stage_rows[-1] if stage_rows else None),
    )
    return {
        "schema_version": "newma.creator_studio_snapshot.v1",
        "generated_at": now_iso(),
        "run": {
            "run_id": manifest.get("run_id"),
            "title": manifest.get("title"),
            "pipeline_id": manifest.get("pipeline_id"),
            "lane": manifest.get("lane"),
            "updated_at": manifest.get("updated_at"),
            "progress": round(sum(row["progress"] for row in stage_rows) / len(stage_rows)) if stage_rows else 0,
            "active_stage_id": active.get("id") if active else None,
        },
        "stages": stage_rows,
        "graph": {"nodes": graph_nodes, "edges": graph_edges},
        "notifications": notifications,
        "counters": {
            "waiting_review": sum(1 for item in notifications if item["kind"] == "review"),
            "new_artifacts": sum(1 for item in notifications if item["kind"] == "artifact"),
            "blocked_nodes": sum(1 for item in notifications if item["kind"] == "warning"),
        },
    }


def build_handoff(
    manifest: dict[str, Any],
    registry: dict[str, Any],
    target_stage: str,
    target_node: str,
    artifact_types: list[str],
) -> dict[str, Any]:
    materials = artifact_materials(manifest)
    if artifact_types:
        materials = [item for item in materials if item.get("type") in artifact_types]
    validation = validate_node_materials(registry, target_stage, target_node, materials)
    return {
        "schema_version": "newma.artifact_handoff.v1",
        "handoff_id": f"handoff_{manifest.get('run_id')}_{target_stage}_{target_node}",
        "created_at": now_iso(),
        "source_run_id": manifest.get("run_id"),
        "target": {"stage_id": target_stage, "node_id": target_node},
        "materials": materials,
        "validation": validation,
        "status": "ready" if validation["status"] == "ready" else "needs_material",
    }


def init_node_project(
    title: str,
    stage_id: str,
    node_id: str,
    materials: list[dict[str, Any]],
    output_root: str,
    run_id: str,
) -> tuple[dict[str, Any], Path]:
    registry = load_registry()
    validation = validate_node_materials(
        registry,
        stage_id,
        node_id,
        materials,
        allow_manual_bootstrap=True,
    )
    if validation["status"] != "ready":
        raise ValueError(json.dumps(validation, ensure_ascii=False))
    manifest = build_manifest(
        title=title,
        pipeline_id="mainline",
        output_root=output_root or None,
        source_materials=materials,
        run_id=run_id or None,
    )
    selected_stage = stage_definition(registry, stage_id)
    selected_stage_order = int(selected_stage["order"])
    node_runs: list[dict[str, Any]] = []
    for stage in registry.get("stages", []):
        stage_order = int(stage["order"])
        stage_status = "skipped" if stage_order < selected_stage_order else "pending"
        if stage_order == selected_stage_order:
            stage_status = "running"
        stage_row = next(row for row in manifest["stages"] if row["name"] == stage["id"])
        stage_row["status"] = stage_status
        if stage_order == selected_stage_order:
            stage_row["current_node"] = node_id
            stage_row["started_at"] = now_iso()
        for node in stage.get("nodes", []):
            status = "pending"
            if stage_order < selected_stage_order:
                status = "skipped"
            elif stage_order == selected_stage_order:
                node_order = [item["id"] for item in stage["nodes"]].index(node["id"])
                selected_node_order = [item["id"] for item in stage["nodes"]].index(node_id)
                if node_order < selected_node_order:
                    status = "skipped"
                elif node["id"] == node_id:
                    status = "running"
            node_runs.append({"stage_id": stage["id"], "node_id": node["id"], "status": status})
    manifest["node_runs"] = node_runs
    manifest["material_bindings"] = validation["bindings"]
    manifest["events"] = [
        {
            "id": "event_001",
            "type": "project_created_at_node",
            "created_at": now_iso(),
            "stage_id": stage_id,
            "node_id": node_id,
        }
    ]
    manifest["updated_at"] = now_iso()
    manifest_path = Path(manifest["output_root"]) / "project_run_manifest.json"
    save_manifest(manifest, manifest_path)
    return manifest, manifest_path


def execution_adapter_definition(
    registry: dict[str, Any],
    node: dict[str, Any],
) -> dict[str, Any]:
    executor_id = str(node.get("executor") or "").strip()
    adapters = {
        str(item.get("id")): item
        for item in registry.get("execution_adapters", [])
        if isinstance(item, dict) and item.get("id")
    }
    if not executor_id or executor_id not in adapters:
        raise ValueError(f"节点未注册执行器：{node.get('id')}")
    return adapters[executor_id]


def editor_adapter_definition(
    registry: dict[str, Any], editor_id: str
) -> dict[str, Any]:
    for adapter in registry.get("editor_adapters", []):
        if adapter.get("id") == editor_id:
            return adapter
    raise ValueError(f"编辑器未注册：{editor_id}")


def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(0.2)
        return connection.connect_ex(("127.0.0.1", port)) == 0


def node_execution_dir(run_id: str, stage_id: str, node_id: str) -> Path:
    if not RUN_ID_PATTERN.fullmatch(run_id):
        raise ValueError(f"run_id 格式不安全：{run_id}")
    return (
        get_desktop_root()
        / run_id
        / "nodes"
        / stage_id
        / node_id
    ).resolve()


def execution_artifact(
    artifact_type: str,
    path: Path,
    *,
    slot: str | None = None,
    label: str | None = None,
    status: str = "created",
    origin: str = "deliverable",
) -> dict[str, Any]:
    artifact = {
        "type": artifact_type,
        "path": str(path.resolve()),
        "label": label or artifact_type,
        "status": status,
        "origin": origin,
    }
    if slot:
        artifact["slot"] = slot
    return artifact


PACKET_SCHEMA_VERSION = "newma.creator_node_artifact.v1"


def is_packet_document(payload: Any) -> bool:
    """识别占位 packet（write_node_packets 自产，非真实交付物）。"""
    return (
        isinstance(payload, dict)
        and payload.get("schema_version") == PACKET_SCHEMA_VERSION
        and payload.get("packet") is True
    )


def packet_origin_for(kind: str, artifact_type: str) -> str:
    """判定 write_node_packets 产物的 origin：

    配置包、执行请求和编辑会话只服务后台运行，不是用户产品；Handoff
    仍参与节点流转，但前端只在“底层文件”中展示。真实交付物必须由执行器
    或人工会话另行登记为 deliverable。
    """
    if kind in {"package", "capability_session", "publish_confirmation"}:
        return "system"
    if kind == "review_gate":
        return "handoff" if artifact_type.endswith("_handoff") else "packet"
    return "deliverable"


def write_node_packets(
    request: dict[str, Any],
    node: dict[str, Any],
    adapter: dict[str, Any],
    output_types: list[str],
) -> list[dict[str, Any]]:
    kind = str(adapter.get("kind") or "")
    output_dir = node_execution_dir(
        str(request["run_id"]),
        str(request["stage_id"]),
        str(request["node_id"]),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[dict[str, Any]] = []
    for artifact_type in output_types:
        target = output_dir / f"{artifact_type}.json"
        write_json(
            target,
            {
                "schema_version": PACKET_SCHEMA_VERSION,
                "packet": packet_origin_for(kind, artifact_type) == "packet",
                "run_id": request["run_id"],
                "title": request.get("title"),
                "stage_id": request["stage_id"],
                "node_id": request["node_id"],
                "artifact_type": artifact_type,
                "executor_id": adapter["id"],
                "created_at": now_iso(),
                "materials": request.get("materials", []),
                "parameters": request.get("parameters", {}),
                "editors": node.get("editors", []),
                "status": "pending_review" if node.get("gate") else "created",
                "note": (
                    "占位 packet：真实交付物由会话产出后另行登记（origin=deliverable）。"
                    if packet_origin_for(kind, artifact_type) == "packet"
                    else "配置载体：由本节点生成并直接被下游消费。"
                ),
            },
        )
        artifacts.append(
            execution_artifact(
                artifact_type,
                target,
                origin=packet_origin_for(kind, artifact_type),
            )
        )
    return artifacts


def describe_editor(
    registry: dict[str, Any],
    editor_id: str,
    materials: list[dict[str, Any]],
) -> dict[str, Any]:
    adapter = editor_adapter_definition(registry, editor_id)
    kind = str(adapter.get("kind") or "unavailable")
    agent_bridge = dict(adapter.get("agent_bridge") or {})
    if agent_bridge.get("endpoint"):
        agent_bridge["endpoint"] = expand_config_value(str(agent_bridge["endpoint"]))
    row: dict[str, Any] = {
        "id": editor_id,
        "name": adapter.get("name") or editor_id,
        "kind": kind,
        "status": "available",
        "launch_url": expand_config_value(str(adapter.get("launch_url") or "")) or None,
        "embed_mode": adapter.get("embed_mode") or "new_window",
        "agent_bridge": agent_bridge or None,
        "session_protocol": adapter.get("session_protocol"),
        "template_catalogs": list(adapter.get("template_catalogs") or []),
    }
    if kind == "local_web":
        project, candidates = resolve_editor_project(adapter)
        command, binary = resolve_editor_command(adapter)
        missing = []
        if not project.is_dir():
            missing.append(str(project))
        if not binary:
            missing.append(command[0] if command else "launch command")
        for required_path in adapter.get("required_paths", []):
            candidate = project / str(required_path)
            if not candidate.exists():
                missing.append(str(candidate))
        row.update(
            {
                "project_path": str(project),
                "project_candidates": [str(path) for path in candidates],
                "already_running": port_open(int(adapter.get("health_port") or 0)),
                "status": "available" if not missing else "blocked",
                "missing": missing,
            }
        )
    elif kind == "artifact_preview":
        preview = next(
            (
                material
                for material in materials
                if resolve_candidate_path(str(material.get("path") or ""), ROOT)
            ),
            None,
        )
        row["artifact_path"] = preview.get("path") if preview else None
        if preview is None:
            row["status"] = "blocked"
            row["missing"] = ["可预览的本地素材"]
    elif kind == "publish_console":
        script = ROOT / "scripts" / "start_publish_console.py"
        if not script.is_file():
            row["status"] = "blocked"
            row["missing"] = [str(script)]
    elif kind == "unavailable":
        row["status"] = "unavailable"
        row["reason"] = adapter.get("reason") or "当前环境不可用"
    return row


def prepare_editor_session(
    request: dict[str, Any],
    node: dict[str, Any],
    registry: dict[str, Any],
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    materials = [item for item in request.get("materials", []) if isinstance(item, dict)]
    editors = [
        describe_editor(registry, str(editor_id), materials)
        for editor_id in node.get("editors", [])
    ]
    session = {
        "schema_version": "newma.editor_session.v1",
        "session_id": f"editor-{uuid4().hex[:12]}",
        "run_id": request["run_id"],
        "stage_id": request["stage_id"],
        "node_id": request["node_id"],
        "status": "ready" if any(row["status"] == "available" for row in editors) else "blocked",
        "editors": editors,
        "input_artifacts": materials,
        "output_contract": [str(item) for item in node.get("outputs", [])],
        "created_at": now_iso(),
    }
    output_dir = node_execution_dir(
        str(request["run_id"]),
        str(request["stage_id"]),
        str(request["node_id"]),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    session_path = output_dir / f"{session['session_id']}.json"
    write_json(session_path, session)
    artifacts = [execution_artifact("editor_session", session_path, origin="system")]
    logs = [
        {
            "at": now_iso(),
            "message": f"已创建编辑会话，可用编辑器 {sum(row['status'] == 'available' for row in editors)} 个。",
        }
    ]
    status = "waiting_user" if session["status"] == "ready" else "blocked"
    return status, artifacts, logs, {"kind": "editor_session", "editor_session": session}


def launch_registered_editor(
    request: dict[str, Any],
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    registry = registry or load_registry()
    editor_id = str(request.get("editor_id") or "")
    adapter = editor_adapter_definition(registry, editor_id)
    kind = str(adapter.get("kind") or "unavailable")
    started_at = now_iso()
    result: dict[str, Any] = {
        "schema_version": "newma.editor_launch.v1",
        "session_id": request.get("session_id"),
        "editor_id": editor_id,
        "kind": kind,
        "started_at": started_at,
        "launch_url": expand_config_value(str(adapter.get("launch_url") or "")) or None,
        "embed_mode": adapter.get("embed_mode") or "new_window",
        "agent_bridge": {
            **dict(adapter.get("agent_bridge") or {}),
            **(
                {"endpoint": expand_config_value(str((adapter.get("agent_bridge") or {}).get("endpoint")))}
                if (adapter.get("agent_bridge") or {}).get("endpoint")
                else {}
            ),
        } or None,
        "session_protocol": adapter.get("session_protocol"),
    }
    external_project_id = str(request.get("external_project_id") or "").strip()
    if editor_id == "openchatcut" and external_project_id:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", external_project_id):
            result.update({"status": "blocked", "error": "OpenChatCut project id 格式无效"})
            return result
        base_url = str(result.get("launch_url") or "").split("#", 1)[0].rstrip("/")
        result["launch_url"] = f"{base_url}/#/editor/{quote(external_project_id, safe='')}"
    if kind == "internal":
        result.update({"status": "open", "mode": "internal"})
        return result
    if kind == "artifact_preview":
        artifact_path = str(request.get("artifact_path") or "")
        path = resolve_candidate_path(artifact_path, ROOT)
        result.update(
            {
                "status": "open" if path else "blocked",
                "mode": "artifact_preview",
                "artifact_path": str(path) if path else artifact_path or None,
                "error": None if path else "没有可预览的本地素材",
            }
        )
        return result
    if kind == "unavailable":
        result.update({"status": "blocked", "error": adapter.get("reason")})
        return result
    if kind == "publish_console":
        command = [
            sys.executable,
            str(ROOT / "scripts" / "start_publish_console.py"),
            "--confirm-start",
        ]
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        payload = parse_json_stdout(completed.stdout)
        frontend = payload.get("frontend") if isinstance(payload.get("frontend"), dict) else {}
        configured_url = expand_config_value(str(adapter.get("launch_url") or ""))
        result.update(
            {
                "status": "open" if frontend.get("ready") else "blocked",
                "launch_url": configured_url or frontend.get("url"),
                "process": payload,
                "error": None if frontend.get("ready") else payload.get("status") or completed.stderr,
            }
        )
        return result
    if kind != "local_web":
        result.update({"status": "blocked", "error": f"不支持的编辑器类型：{kind}"})
        return result

    project, candidates = resolve_editor_project(adapter)
    port = int(adapter.get("health_port") or 0)
    if port and port_open(port):
        result.update({
            "status": "open",
            "already_running": True,
            "project_path": str(project),
            "project_candidates": [str(path) for path in candidates],
        })
        return result
    command, binary = resolve_editor_command(adapter)
    if not project.is_dir() or not binary:
        result.update(
            {
                "status": "blocked",
                "error": "编辑器项目或启动命令不可用",
                "project_path": str(project),
                "project_candidates": [str(path) for path in candidates],
            }
        )
        return result
    output_dir = node_execution_dir(
        str(request["run_id"]),
        str(request["stage_id"]),
        str(request["node_id"]),
    ) / "editor_logs"
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / f"{editor_id}.log"
    with log_path.open("ab") as log_handle:
        process = subprocess.Popen(
            command,
            cwd=project,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    deadline = time.monotonic() + 12
    while port and time.monotonic() < deadline and not port_open(port):
        time.sleep(0.2)
    ready = not port or port_open(port)
    result.update(
        {
            "status": "open" if ready else "blocked",
            "pid": process.pid,
            "log_path": str(log_path),
            "project_path": str(project),
            "project_candidates": [str(path) for path in candidates],
            "error": None if ready else "编辑器已启动，但健康检查尚未通过",
        }
    )
    return result


def materialize_editor_export(
    request: dict[str, Any],
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    registry = registry or load_registry()
    editor_id = str(request.get("editor_id") or "").strip()
    if editor_id != "openchatcut":
        raise ValueError("当前只支持导入 OpenChatCut 导出")
    project_id = str(request.get("external_project_id") or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,160}", project_id):
        raise ValueError("必须先绑定有效的 OpenChatCut 工程")
    download_url = str(request.get("download_url") or "").strip()
    if not download_url:
        raise ValueError("缺少 OpenChatCut 导出地址")

    adapter = editor_adapter_definition(registry, editor_id)
    project, _ = resolve_editor_project(adapter)
    configured_origin = urlsplit(
        expand_config_value(str(adapter.get("launch_url") or ""))
    )
    parsed = urlsplit(download_url)
    if parsed.scheme:
        if (
            parsed.scheme,
            parsed.hostname,
            parsed.port,
        ) != (
            configured_origin.scheme,
            configured_origin.hostname,
            configured_origin.port,
        ):
            raise ValueError("导出地址不属于已注册的 OpenChatCut Runtime")
        media_path = parsed.path
        source_url = download_url
    else:
        media_path = parsed.path or download_url
        origin = f"{configured_origin.scheme}://{configured_origin.netloc}"
        source_url = f"{origin}{media_path if media_path.startswith('/') else '/' + media_path}"
    prefix = "/media/uploads/"
    if not media_path.startswith(prefix):
        raise ValueError("OpenChatCut 导出地址必须来自 /media/uploads/")
    source_name = unquote(media_path[len(prefix) :])
    if not source_name or Path(source_name).name != source_name or source_name.startswith("."):
        raise ValueError("OpenChatCut 导出文件名无效")

    requested_name = str(request.get("name") or "").strip()
    output_name = Path(requested_name).name if requested_name else source_name
    extension = Path(output_name).suffix.lower() or Path(source_name).suffix.lower()
    if extension not in EDITOR_EXPORT_EXTENSIONS:
        raise ValueError("OpenChatCut 导出格式不受支持")
    if not Path(output_name).suffix:
        output_name += extension
    token = re.sub(
        r"[^A-Za-z0-9_-]",
        "-",
        str(request.get("render_id") or uuid4().hex[:12]),
    ).strip("-") or uuid4().hex[:12]

    output_dir = node_execution_dir(
        str(request["run_id"]),
        str(request["stage_id"]),
        str(request["node_id"]),
    ) / "editor_outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"{token[:40]}-{output_name}"
    local_source = project / "public" / "media" / "uploads" / source_name
    if local_source.is_file():
        shutil.copy2(local_source, target)
    else:
        with urlopen(source_url, timeout=60) as response, target.open("wb") as handle:
            shutil.copyfileobj(response, handle)

    timestamp = now_iso()
    proposal = request.get("proposal") if isinstance(request.get("proposal"), dict) else None
    decisions_path = output_dir / f"{token[:40]}-edit-decisions.json"
    timeline_path = output_dir / f"{token[:40]}-timeline-exchange.json"
    edit_decisions = {
        "schema_version": "newma.edit_decisions.v1",
        "run_id": request["run_id"],
        "stage_id": request["stage_id"],
        "node_id": request["node_id"],
        "editor_id": editor_id,
        "newma_editor_session_id": request.get("session_id"),
        "external_project_id": project_id,
        "external_edit_session_id": request.get("external_edit_session_id"),
        "proposal": proposal,
        "render_id": request.get("render_id"),
        "edited_master": str(target),
        "created_at": timestamp,
    }
    timeline_exchange = {
        "schema_version": "newma.timeline_exchange.v1",
        "format": "openchatcut-project-ref",
        "editor_id": editor_id,
        "project_id": project_id,
        "editor_url": (
            f"{configured_origin.scheme}://{configured_origin.netloc}"
            f"/#/editor/{quote(project_id, safe='')}"
        ),
        "render_id": request.get("render_id"),
        "edited_master": str(target),
        "created_at": timestamp,
    }
    write_json(decisions_path, edit_decisions)
    write_json(timeline_path, timeline_exchange)
    outputs = [
        execution_artifact("edited_master", target, label="OpenChatCut 剪辑成片"),
        execution_artifact("edit_decisions", decisions_path, label="剪辑决策"),
        execution_artifact("timeline_exchange", timeline_path, label="时间线交换记录"),
    ]
    return {
        "status": "succeeded",
        "editor_id": editor_id,
        "external_project_id": project_id,
        "render_id": request.get("render_id"),
        "outputs": outputs,
    }


def resolve_candidate_path(value: str, base: Path) -> Path | None:
    if not value or value.startswith(("http://", "https://")):
        return None
    candidate = Path(value).expanduser()
    if not candidate.is_absolute():
        candidate = (base / candidate).resolve()
    else:
        candidate = candidate.resolve()
    return candidate if candidate.exists() else None


def find_material_path(
    request: dict[str, Any],
    material_types: list[str],
    filenames: list[str],
    fallback: Path | None = None,
) -> Path:
    wanted_types = set(material_types)
    wanted_names = set(filenames)
    queue: list[Path] = []
    for material in request.get("materials", []):
        if not isinstance(material, dict):
            continue
        path = resolve_candidate_path(str(material.get("path") or ""), ROOT)
        if path and str(material.get("type") or "") in wanted_types:
            return path
        if path:
            queue.append(path)

    seen: set[Path] = set()
    while queue and len(seen) < 40:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        if current.is_dir():
            for name in wanted_names:
                candidate = current / name
                if candidate.exists():
                    return candidate.resolve()
            continue
        if current.name in wanted_names:
            return current
        if current.suffix.lower() != ".json":
            continue
        try:
            payload = read_json(current)
        except (OSError, json.JSONDecodeError):
            continue

        def walk(value: Any, key: str = "") -> Path | None:
            if isinstance(value, dict):
                item_type = str(value.get("type") or value.get("artifact_type") or "")
                item_path = value.get("path")
                if item_type in wanted_types and isinstance(item_path, str):
                    matched = resolve_candidate_path(item_path, current.parent)
                    if matched:
                        return matched
                for child_key, child in value.items():
                    matched = walk(child, str(child_key))
                    if matched:
                        return matched
            elif isinstance(value, list):
                for child in value:
                    matched = walk(child, key)
                    if matched:
                        return matched
            elif isinstance(value, str):
                candidate = resolve_candidate_path(value, current.parent)
                if candidate and (key in wanted_types or candidate.name in wanted_names):
                    return candidate
                if candidate and candidate.suffix.lower() == ".json":
                    queue.append(candidate)
            return None

        matched = walk(payload)
        if matched:
            return matched

    if fallback and fallback.exists():
        return fallback.resolve()
    raise ValueError(f"缺少执行输入：{', '.join(material_types)}")


def parse_json_stdout(stdout: str) -> dict[str, Any]:
    content = stdout.strip()
    if not content:
        return {}
    try:
        payload = json.loads(content)
        return payload if isinstance(payload, dict) else {}
    except json.JSONDecodeError:
        start = content.find("{")
        end = content.rfind("}")
        if start >= 0 and end > start:
            try:
                payload = json.loads(content[start : end + 1])
                return payload if isinstance(payload, dict) else {}
            except json.JSONDecodeError:
                return {}
    return {}


def discover_named_material_files(
    request: dict[str, Any],
    names: set[str],
) -> list[Path]:
    queue: list[Path] = []
    for material in request.get("materials", []):
        if not isinstance(material, dict):
            continue
        candidate = resolve_candidate_path(str(material.get("path") or ""), ROOT)
        if candidate:
            queue.append(candidate)
    seen: set[Path] = set()
    matches: dict[str, Path] = {}

    def is_deliverable_file(path: Path) -> bool:
        """占位 packet 不是真实交付物，按名查找时跳过。"""
        try:
            return not is_packet_document(read_json(path))
        except (OSError, json.JSONDecodeError):
            return True

    while queue and len(seen) < 200:
        current = queue.pop(0).resolve()
        if current in seen:
            continue
        seen.add(current)
        if current.is_dir():
            for name in names:
                for candidate in current.rglob(name):
                    resolved = candidate.resolve()
                    if is_deliverable_file(resolved):
                        matches[str(resolved)] = resolved
            continue
        if current.name in names and is_deliverable_file(current):
            matches[str(current)] = current
        if current.suffix.lower() != ".json":
            continue
        try:
            payload = read_json(current)
        except (OSError, json.JSONDecodeError):
            continue

        def walk(value: Any) -> None:
            if isinstance(value, dict):
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
            elif isinstance(value, str):
                candidate = resolve_candidate_path(value, current.parent)
                if candidate and candidate not in seen:
                    queue.append(candidate)

        walk(payload)
    return list(matches.values())


def execute_publish_preflight(
    adapter: dict[str, Any],
    request: dict[str, Any],
) -> tuple[str, int, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    execution_requests = discover_named_material_files(
        request,
        {"execution_request.json"},
    )
    plans = [build_publish_execution_plan(path) for path in execution_requests]
    channels = sorted({str(plan.get("channel")) for plan in plans if plan.get("channel")})
    slots = sorted({str(plan.get("account_slot")) for plan in plans if plan.get("account_slot")})
    accounts = build_publish_account_report(
        channels or None,
        slots=slots or None,
        check_auth=False,
        initialize=False,
    )
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for plan in plans:
        if plan.get("status") != "ready_for_user_confirmation":
            blockers.append(
                {
                    "kind": "route",
                    "taskId": plan.get("task_id"),
                    "status": plan.get("status"),
                }
            )
    ready_account_statuses = {
        "available",
        "state_present_unverified",
        "configured_unverified",
    }
    for account in accounts.get("accounts", []):
        status = str(account.get("status") or "unknown")
        issue = {
            "kind": "account",
            "channel": account.get("channel"),
            "slot": account.get("slot"),
            "status": status,
        }
        if status not in ready_account_statuses:
            blockers.append(issue)
        elif status != "available":
            warnings.append(issue)
    if not execution_requests:
        blockers.append({"kind": "input", "status": "missing_execution_request"})
    output_dir = node_execution_dir(
        str(request["run_id"]),
        str(request["stage_id"]),
        str(request["node_id"]),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "publish_preflight_report.json"
    report = {
        "schema_version": "newma.publish_preflight.v1",
        "run_id": request["run_id"],
        "created_at": now_iso(),
        "status": "ready_for_confirmation" if not blockers else "blocked",
        "execution_requests": [str(path) for path in execution_requests],
        "plans": plans,
        "account_health": accounts,
        "blockers": blockers,
        "warnings": warnings,
        "requires_user_confirmation": True,
        "will_not_publish": True,
    }
    write_json(report_path, report)
    status = "succeeded" if not blockers else "blocked"
    logs = [
        {
            "at": now_iso(),
            "message": f"发布预检完成：{len(plans)} 个任务，{len(blockers)} 个阻塞项。",
        }
    ]
    return (
        status,
        0 if status == "succeeded" else 2,
        [execution_artifact("publish_preflight_report", report_path)],
        logs,
        {
            "kind": "publish_preflight",
            "status": report["status"],
            "taskCount": len(plans),
            "accountHealth": accounts,
            "blockers": blockers,
            "warnings": warnings,
            "report": str(report_path),
        },
    )


def execute_confirmed_publish(
    adapter: dict[str, Any],
    request: dict[str, Any],
) -> tuple[str, int, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    confirmation = (request.get("parameters") or {}).get("publishConfirmation")
    if (
        not isinstance(confirmation, dict)
        or confirmation.get("confirmed") is not True
        or confirmation.get("confirmationText") != "确认发布"
        or confirmation.get("consumedByJobId") != request.get("job_id")
    ):
        raise ValueError("执行发布前必须完成当前任务的明确确认")
    reports = discover_named_material_files(
        request,
        {"publish_preflight_report.json"},
    )
    if not reports:
        raise ValueError("缺少 publish_preflight_report.json")
    preflight = read_json(reports[0])
    if preflight.get("status") != "ready_for_confirmation":
        raise ValueError("发布预检尚未通过")
    execution_requests = [
        Path(str(path)).expanduser().resolve()
        for path in preflight.get("execution_requests", [])
        if Path(str(path)).expanduser().exists()
    ]
    if not execution_requests:
        raise ValueError("发布预检没有可执行任务")

    rows: list[dict[str, Any]] = []
    for execution_path in execution_requests:
        try:
            result = execute_publish_request(
                execution_path,
                confirm_execute=True,
            )
        except Exception as exc:
            result = {
                "status": "failed",
                "error": str(exc),
                "will_not_publish": False,
            }
        rows.append(
            {
                "execution_request": str(execution_path),
                "status": result.get("status"),
                "selected_route": result.get("selected_route"),
                "result": result,
            }
        )
    succeeded = [row for row in rows if row.get("status") == "executed_and_recorded"]
    failed = [row for row in rows if row not in succeeded]
    output_dir = node_execution_dir(
        str(request["run_id"]),
        str(request["stage_id"]),
        str(request["node_id"]),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    jobs_path = output_dir / "publish_jobs.json"
    receipts_path = output_dir / "platform_receipts.json"
    jobs = {
        "schema_version": "newma.publish_jobs.v1",
        "run_id": request["run_id"],
        "created_at": now_iso(),
        "confirmation": confirmation,
        "jobs": rows,
    }
    receipts = {
        "schema_version": "newma.platform_receipts.v1",
        "run_id": request["run_id"],
        "created_at": now_iso(),
        "status": "recorded" if not failed else "partially_failed",
        "receipts": rows,
    }
    write_json(jobs_path, jobs)
    write_json(receipts_path, receipts)
    status = "succeeded" if not failed else "blocked"
    logs = [
        {
            "at": now_iso(),
            "message": f"发布执行完成：成功 {len(succeeded)}，未完成 {len(failed)}。",
        }
    ]
    return (
        status,
        0 if status == "succeeded" else 2,
        [
            execution_artifact("publish_jobs", jobs_path),
            execution_artifact("platform_receipts", receipts_path),
        ],
        logs,
        {
            "kind": "publish_execute",
            "status": receipts["status"],
            "succeeded": len(succeeded),
            "failed": len(failed),
            "receipts": str(receipts_path),
        },
    )


def publish_root_from_channel_pack(path: Path) -> Path | None:
    for parent in path.parents:
        if parent.name == "channel_packs":
            return parent.parent
    return None


def execute_publish_verify(
    adapter: dict[str, Any],
    request: dict[str, Any],
) -> tuple[str, int, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    receipt_paths = discover_named_material_files(
        request,
        {"platform_receipts.json"},
    )
    if not receipt_paths:
        raise ValueError("缺少 platform_receipts.json")
    receipts = read_json(receipt_paths[0])
    rows = receipts.get("receipts") if isinstance(receipts.get("receipts"), list) else []
    publish_roots: dict[str, Path] = {}
    failures: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        result = row.get("result") if isinstance(row.get("result"), dict) else {}
        record = result.get("record") if isinstance(result.get("record"), dict) else {}
        channel_pack = record.get("channel_pack")
        if channel_pack:
            root = publish_root_from_channel_pack(Path(str(channel_pack)).expanduser().resolve())
            if root:
                publish_roots[str(root)] = root
        if row.get("status") != "executed_and_recorded":
            failures.append(row)

    artifacts: list[dict[str, Any]] = []
    verification_rows: list[dict[str, Any]] = []
    for root in publish_roots.values():
        manifest = root / "publish_manifest.json"
        verification = root / "publish_verification_report.json"
        if manifest.exists():
            artifacts.append(execution_artifact("publish_manifest", manifest))
        if verification.exists():
            artifacts.append(
                execution_artifact("publish_verification_report", verification)
            )
            verification_rows.append(read_json(verification))
    if not publish_roots:
        failures.append({"status": "missing_publish_root"})

    output_dir = node_execution_dir(
        str(request["run_id"]),
        str(request["stage_id"]),
        str(request["node_id"]),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    handoff_path = output_dir / "postmortem_handoff.json"
    handoff = {
        "schema_version": "newma.postmortem_handoff.v1",
        "run_id": request["run_id"],
        "created_at": now_iso(),
        "status": "ready" if not failures else "blocked",
        "publish_roots": list(publish_roots),
        "verification_reports": verification_rows,
        "failures": failures,
    }
    write_json(handoff_path, handoff)
    artifacts.append(execution_artifact("postmortem_handoff", handoff_path))
    status = "succeeded" if not failures else "blocked"
    return (
        status,
        0 if status == "succeeded" else 2,
        artifacts,
        [
            {
                "at": now_iso(),
                "message": f"平台回执验真完成：{len(verification_rows)} 份报告，{len(failures)} 个异常。",
            }
        ],
        {
            "kind": "publish_verify",
            "status": handoff["status"],
            "verificationCount": len(verification_rows),
            "failures": failures,
            "postmortemHandoff": str(handoff_path),
        },
    )


def discover_execution_artifacts(
    adapter: dict[str, Any],
    output_dir: Path,
    payload: dict[str, Any],
) -> list[dict[str, Any]]:
    artifacts: list[dict[str, Any]] = []
    for spec in adapter.get("artifacts", []):
        if not isinstance(spec, dict) or not spec.get("type"):
            continue
        paths: list[Path] = []
        if spec.get("path"):
            paths.append(output_dir / str(spec["path"]))
        if spec.get("glob"):
            paths.extend(sorted(output_dir.glob(str(spec["glob"]))))
        json_key = str(spec.get("json_key") or "")
        if json_key:
            values: list[str] = []

            def collect(value: Any, key: str = "") -> None:
                if isinstance(value, dict):
                    for child_key, child in value.items():
                        collect(child, str(child_key))
                elif isinstance(value, list):
                    for child in value:
                        collect(child, key)
                elif key == json_key and isinstance(value, str):
                    values.append(value)

            collect(payload)
            paths.extend(Path(value).expanduser() for value in values)
        for path in paths:
            candidate = path.resolve()
            if not candidate.exists():
                continue
            artifacts.append(
                execution_artifact(
                    str(spec["type"]),
                    candidate,
                    slot=candidate.stem if spec.get("glob") else None,
                    label=str(spec.get("label") or spec["type"]),
                )
            )
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for artifact in artifacts:
        deduped[(artifact["type"], artifact["path"])] = artifact
    return list(deduped.values())


def mainline_command(
    adapter: dict[str, Any],
    request: dict[str, Any],
) -> tuple[list[str], Path]:
    run_id = str(request["run_id"])
    stage = str(adapter.get("stage") or request["stage_id"])
    output_dir = canonical_stage_dir(stage, run_id).resolve()
    script = ROOT / "scripts" / "run_mainline_stage.py"
    if stage == "intake":
        return [str(script), "intake", "--run-id", run_id, "--no-project-manifest"], output_dir
    if stage == "brief":
        intake_records = find_material_path(
            request,
            ["intake_records"],
            ["intake_records.json"],
            canonical_stage_dir("intake", run_id) / "raw" / "intake_records.json",
        )
        command = [
            str(script),
            "brief",
            "--run-id",
            run_id,
            "--input-file",
            str(intake_records),
            "--no-project-manifest",
        ]
        for topic in request.get("parameters", {}).get("manualTopics", []):
            command.extend(["--manual-topic", str(topic)])
        return command, output_dir
    if stage == "draft":
        selected_topics = find_material_path(
            request,
            ["selected_topics"],
            ["selected_topics.json"],
            canonical_stage_dir("brief", run_id) / "selected_topics.json",
        )
        topic_cards = find_material_path(
            request,
            ["topic_cards"],
            ["topic_cards.json"],
            canonical_stage_dir("brief", run_id) / "topic_cards.json",
        )
        return [
            str(ROOT / "scripts" / "build_stage3_draft.py"),
            str(selected_topics),
            str(topic_cards),
            "--output-dir",
            str(output_dir),
            "--run-id",
            run_id,
        ], output_dir
    if stage == "transwrite":
        draft_manifest = find_material_path(
            request,
            ["draft_manifest"],
            ["draft_manifest.json"],
            canonical_stage_dir("draft", run_id) / "draft_manifest.json",
        )
        decision = find_material_path(
            request,
            ["transwrite_decision"],
            ["transwrite_decision.json"],
            canonical_stage_dir("transwrite", run_id) / "transwrite_decision.json",
        )
        return [
            str(ROOT / "scripts" / "build_stage4_transwrite.py"),
            "--draft-manifest",
            str(draft_manifest),
            "--transwrite-decision",
            str(decision),
            "--output-dir",
            str(output_dir),
        ], output_dir
    if stage == "publish":
        transwrite_manifest = find_material_path(
            request,
            ["transwrite_manifest"],
            ["transwrite_manifest.json"],
            canonical_stage_dir("transwrite", run_id) / "transwrite_manifest.json",
        )
        decision = find_material_path(
            request,
            ["publish_decision"],
            ["publish_decision.json"],
            canonical_stage_dir("publish", run_id) / "publish_decision.json",
        )
        return [
            str(ROOT / "scripts" / "build_stage5_publish.py"),
            "--transwrite-manifest",
            str(transwrite_manifest),
            "--publish-decision",
            str(decision),
            "--output-dir",
            str(output_dir),
        ], output_dir
    if stage == "postmortem":
        publish_manifest = find_material_path(
            request,
            ["publish_manifest"],
            ["publish_manifest.json"],
            canonical_stage_dir("publish", run_id) / "publish_manifest.json",
        )
        return [
            str(ROOT / "scripts" / "postmortem_writeback.py"),
            "--publish-manifest",
            str(publish_manifest),
        ], output_dir
    raise ValueError(f"未支持的主线阶段执行器：{stage}")


def execute_subprocess_adapter(
    adapter: dict[str, Any],
    request: dict[str, Any],
) -> tuple[str, int, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    command, output_dir = mainline_command(adapter, request)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build subprocess env: inherit parent env, then inject agent selection
    env = os.environ.copy()
    parameters = request.get("parameters") or {}
    agent_cli = (
        request.get("agent_cli")
        or parameters.get("agent_cli")
        or parameters.get("agentCli")
        or ""
    )
    agent_bin = (
        request.get("agent_cli_bin")
        or parameters.get("agent_cli_bin")
        or parameters.get("agentCliBin")
        or ""
    )
    if agent_cli:
        env["DRAFT_CLI_AGENT"] = str(agent_cli)
        # Also set generic env vars other stages might read
        env["NEWMA_CLI_AGENT"] = str(agent_cli)
    if agent_bin:
        env["DRAFT_CLI_BIN_OVERRIDE"] = str(agent_bin)
        env["NEWMA_CLI_BIN_OVERRIDE"] = str(agent_bin)

    result = subprocess.run(
        [sys.executable, *command],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=int(adapter.get("timeout_seconds") or 1800),
        env=env,
    )
    payload = parse_json_stdout(result.stdout)
    artifacts = discover_execution_artifacts(adapter, output_dir, payload)
    logs = [
        {
            "at": now_iso(),
            "message": f"已调用 {adapter['id']}，退出码 {result.returncode}。" + (
                f"（agent={agent_cli}）" if agent_cli else ""
            ),
        }
    ]
    if result.stderr.strip():
        logs.append({"at": now_iso(), "message": result.stderr.strip()[-2000:]})
    status = "succeeded" if result.returncode == 0 else "failed"
    if status == "succeeded" and adapter.get("artifacts") and not artifacts:
        status = "failed"
        logs.append({"at": now_iso(), "message": "执行完成但未发现注册表声明的交付物。"})
    return status, result.returncode, artifacts, logs, payload


def execute_director_adapter(
    adapter: dict[str, Any],
    request: dict[str, Any],
) -> tuple[str, int, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    parameters = request.get("parameters", {})
    lane_aliases = {
        "talking_head": "talking_head_video",
        "vox_explainer": "vox_explainer_video",
        "headless_explainer": "explainer_html_video",
        "digital_human": "digital_human_video",
        "commercial_promo": "commercial_promo_video",
    }
    lane = lane_aliases.get(str(parameters.get("lane")), str(parameters.get("lane") or ""))
    if not lane:
        raise ValueError("导演分镜执行前必须在参数中设置 lane")
    output_dir = node_execution_dir(
        str(request["run_id"]),
        str(request["stage_id"]),
        str(request["node_id"]),
    ) / "director"
    command = [
        str(ROOT / "scripts" / "dasheng_video_director.py"),
        "--lane",
        lane,
        "--output-dir",
        str(output_dir),
        "--title",
        str(request.get("title") or request["run_id"]),
    ]
    if lane in {"explainer_html_video", "vox_explainer_video"}:
        configured_article = str(parameters.get("articleHtml") or "")
        article = (
            resolve_candidate_path(configured_article, ROOT)
            if configured_article
            else find_material_path(
                request,
                ["illustrated_article", "article_html"],
                [],
            )
        )
        if article is None:
            raise ValueError("该导演通路必须提供 articleHtml 或 illustrated_article 素材")
        command.extend(["--article-html", str(article)])
    for parameter_key, flag in {
        "durationTargetSec": "--duration-target-sec",
        "centralQuestion": "--central-question",
        "creatorIntro": "--creator-intro",
        "sourceVideo": "--source-video",
        "srt": "--srt",
        "captionsJson": "--captions-json",
        "commercialBrief": "--commercial-brief",
    }.items():
        value = parameters.get(parameter_key)
        if value is not None and value != "":
            command.extend([flag, str(value)])
    result = subprocess.run(
        [sys.executable, *command],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=int(adapter.get("timeout_seconds") or 1800),
    )
    payload = parse_json_stdout(result.stdout)
    artifacts = discover_execution_artifacts(adapter, output_dir, payload)
    logs = [{"at": now_iso(), "message": f"导演执行器退出码 {result.returncode}。"}]
    if result.stderr.strip():
        logs.append({"at": now_iso(), "message": result.stderr.strip()[-2000:]})
    status = "succeeded" if result.returncode == 0 else "failed"
    if status == "succeeded" and not artifacts:
        status = "failed"
        logs.append({"at": now_iso(), "message": "导演执行完成但未发现分镜交付物。"})
    return (
        status,
        result.returncode,
        artifacts,
        logs,
        payload,
    )


def execute_route_select(
    adapter: dict[str, Any],
    request: dict[str, Any],
) -> tuple[str, int, list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    run_id = str(request["run_id"])
    draft_manifest_path = find_material_path(
        request,
        ["draft_manifest"],
        ["draft_manifest.json"],
        canonical_stage_dir("draft", run_id) / "draft_manifest.json",
    )
    draft_manifest = read_json(draft_manifest_path)
    dna_selection_path = find_material_path(
        request,
        ["dna_selection"],
        ["dna_selection.json", "04_DNA选择_4题.json"],
    )
    dna_selection = read_json(dna_selection_path)
    dna_routes = {
        str(item.get("topic_id")): item
        for item in dna_selection.get("selections", [])
        if item.get("topic_id")
    }
    parameters = request.get("parameters", {})
    lanes = parameters.get("lanes") or [parameters.get("lane") or "wechat_article"]
    if isinstance(lanes, str):
        lanes = [lanes]
    lane_aliases = {
        "talking_head": "talking_head_video",
        "vox_explainer": "vox_explainer_video",
        "headless_explainer": "explainer_html_video",
        "digital_human": "digital_human_video",
        "commercial_promo": "commercial_promo_video",
        "cinematic_short_drama": "cinematic_short_drama_video",
    }
    normalized_lanes = [lane_aliases.get(str(item), str(item)) for item in lanes]
    topics = []
    for row in draft_manifest.get("drafts", []):
        topic_id = str(row.get("topic_id") or row.get("id") or "")
        if not topic_id:
            continue
        dna_route = dna_routes.get(topic_id, {})
        topics.append(
            {
                "topic_id": topic_id,
                "title": row.get("title"),
                "lanes": normalized_lanes,
                "account_slot": dna_route.get("account_slot"),
                "account_name": dna_route.get("account_name"),
                "dna_alias": dna_route.get("dna_alias"),
            }
        )
    if not topics:
        raise ValueError("draft_manifest 中没有可转写的 topic_id")
    output_dir = canonical_stage_dir("transwrite", run_id).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    decision_path = output_dir / "transwrite_decision.json"
    jobs_path = output_dir / "lane_jobs.json"
    decision = {
        "run_id": run_id,
        "gate": "Transwrite Gate",
        "status": "approved",
        "dna_selection": str(dna_selection_path),
        "topics": topics,
    }
    jobs = {
        "run_id": run_id,
        "draft_manifest": str(draft_manifest_path),
        "dna_selection": str(dna_selection_path),
        "transwrite_decision": str(decision_path),
        "topics": topics,
    }
    write_json(decision_path, decision)
    write_json(jobs_path, jobs)
    artifacts = [
        execution_artifact("transwrite_decision", decision_path),
        execution_artifact("lane_jobs", jobs_path),
    ]
    return (
        "succeeded",
        0,
        artifacts,
        [{"at": now_iso(), "message": f"已为 {len(topics)} 个选题生成通路任务。"}],
        jobs,
    )


def run_registered_node(
    request: dict[str, Any],
    registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    registry = registry or load_registry()
    stage_id = str(request.get("stage_id") or "")
    node_id = str(request.get("node_id") or "")
    run_id = str(request.get("run_id") or "")
    if not stage_id or not node_id or not run_id:
        raise ValueError("run_id、stage_id、node_id 不能为空")
    node = node_definition(registry, stage_id, node_id)
    adapter = execution_adapter_definition(registry, node)
    started_at = now_iso()
    started = time.monotonic()
    status = "failed"
    exit_code = 2
    artifacts: list[dict[str, Any]] = []
    logs: list[dict[str, Any]] = []
    payload: dict[str, Any] = {}
    try:
        kind = str(adapter.get("kind") or "")
        if kind == "mainline_stage":
            status, exit_code, artifacts, logs, payload = execute_subprocess_adapter(adapter, request)
        elif kind == "video_director":
            status, exit_code, artifacts, logs, payload = execute_director_adapter(adapter, request)
        elif kind == "route_select":
            status, exit_code, artifacts, logs, payload = execute_route_select(adapter, request)
        elif kind == "publish_preflight":
            status, exit_code, artifacts, logs, payload = execute_publish_preflight(
                adapter,
                request,
            )
        elif kind == "publish_execute":
            status, exit_code, artifacts, logs, payload = execute_confirmed_publish(
                adapter,
                request,
            )
        elif kind == "publish_verify":
            status, exit_code, artifacts, logs, payload = execute_publish_verify(
                adapter,
                request,
            )
        elif kind == "editor_session":
            status, artifacts, logs, payload = prepare_editor_session(
                request,
                node,
                registry,
            )
            exit_code = 0 if status == "waiting_user" else 2
        elif kind in {"package", "review_gate", "capability_session", "publish_confirmation"}:
            if kind in {"package", "review_gate"}:
                output_types = [str(item) for item in node.get("outputs", [])]
            else:
                output_types = ["execution_request"]
            artifacts = write_node_packets(request, node, adapter, output_types)
            status = "succeeded" if kind == "package" else "waiting_user"
            exit_code = 0
            payload = {"kind": kind, "editors": node.get("editors", [])}
            logs = [{"at": now_iso(), "message": str(adapter.get("message") or "已创建受控节点会话。") }]
        else:
            raise ValueError(f"未知执行器类型：{kind}")
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        status = "failed"
        exit_code = 2
        logs.append({"at": now_iso(), "message": str(exc)})
        payload = {"error": str(exc)}

    if status not in NODE_RESULT_STATUSES:
        status = "failed"
    result = {
        "schema_version": "newma.creator_node_execution.v1",
        "execution_id": f"execution-{uuid4().hex[:12]}",
        "executor_id": adapter["id"],
        "run_id": run_id,
        "stage_id": stage_id,
        "node_id": node_id,
        "status": status,
        "progress": 100 if status in {"succeeded", "waiting_user"} else 0,
        "started_at": started_at,
        "finished_at": now_iso(),
        "duration_ms": round((time.monotonic() - started) * 1000),
        "exit_code": exit_code,
        "artifacts": artifacts,
        "logs": logs,
        "result": payload,
    }
    output_dir = node_execution_dir(run_id, stage_id, node_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "execution_result.json"
    write_json(result_path, result)
    result["execution_result"] = str(result_path)
    return result


def detect_cli_capabilities(registry: dict[str, Any]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for adapter in registry.get("capability_adapters", []):
        binary = adapter.get("binary")
        if adapter.get("kind") != "local_cli" or not binary:
            continue
        resolved = shutil.which(str(binary))
        version = None
        if resolved:
            version_args = CLI_ADAPTERS.get(str(adapter.get("id")), {}).get("version_args", ["--version"])
            try:
                result = subprocess.run(
                    [resolved, *version_args],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=5,
                )
                version = (result.stdout or result.stderr).strip().splitlines()[0] if (result.stdout or result.stderr).strip() else None
            except (OSError, subprocess.TimeoutExpired):
                version = None
        rows.append(
            {
                "id": adapter.get("id"),
                "name": adapter.get("name"),
                "mode": adapter.get("mode"),
                "available": bool(resolved),
                "path": resolved,
                "version": version,
                "stages": adapter.get("stages", []),
            }
        )
    return {
        "schema_version": "newma.capability_detection.v1",
        "generated_at": now_iso(),
        "capabilities": rows,
        "available_count": sum(1 for row in rows if row["available"]),
    }


def invoke_cli(
    agent_id: str,
    prompt: str,
    workdir: str,
    timeout: int,
    binary_override: str = "",
) -> dict[str, Any]:
    registry = load_registry()
    registered = {row["id"]: row for row in registry.get("capability_adapters", [])}
    adapter = registered.get(agent_id)
    if not adapter or adapter.get("mode") != "output_only" or agent_id not in CLI_ADAPTERS:
        raise ValueError(f"CLI 未注册为可调用的 output_only Adapter：{agent_id}")
    definition = CLI_ADAPTERS[agent_id]
    binary = ""
    if binary_override.strip():
        candidate = Path(binary_override).expanduser().resolve()
        if not candidate.is_file() or not os.access(candidate, os.X_OK):
            raise FileNotFoundError(f"CLI binary 不可执行：{candidate}")
        binary = str(candidate)
    else:
        binary = shutil.which(definition["binary"])
    if not binary:
        raise FileNotFoundError(f"未安装 CLI：{definition['binary']}")
    cwd = Path(workdir).expanduser().resolve()
    if not cwd.is_dir() or cwd in {Path("/"), Path.home()}:
        raise ValueError(f"不安全的工作目录：{cwd}")
    args = [binary, *definition.get("args", [])]
    input_text = prompt if definition.get("prompt_via_stdin") else None
    if definition.get("prompt_as_last_arg"):
        args.append(prompt)
    started = time.monotonic()
    result = subprocess.run(
        args,
        cwd=cwd,
        input=input_text,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    return {
        "schema_version": "newma.capability_invocation.v1",
        "agent_id": agent_id,
        "status": "succeeded" if result.returncode == 0 else "failed",
        "exit_code": result.returncode,
        "duration_ms": round((time.monotonic() - started) * 1000),
        "stdout": result.stdout,
        "stderr": result.stderr,
        "workdir": str(cwd),
    }


CAPABILITY_LABELS = {
    "account_labels": "账号标签", "account_launch_advice": "账号启动建议",
    "account_management": "账号管理", "algorithmic_art": "算法艺术",
    "animated_sticker": "动态贴纸", "animation_audit": "动画审查",
    "anti_slop_review": "视觉质量审查", "api_publish": "API 发布",
    "art_direction": "视觉指导", "article_illustration": "文章配图",
    "audio_mastering": "音频母带", "bilibili_publish": "B 站发布",
    "brand_system": "品牌视觉系统", "browser_publish": "浏览器发布",
    "browser_recording_reference": "浏览器录屏参考", "browser_session_reuse": "浏览器会话复用",
    "caption_render": "字幕渲染", "chapter_titles": "章节标题", "cloud_draft": "云端草稿",
    "color_grade": "色彩调整", "competitor_intake": "竞品素材采集",
    "competitor_analysis": "竞品对比分析", "competitor_discovery": "竞品发现", "cross_platform_research": "跨平台研究",
    "comment_analysis": "评论分析", "comment_collection": "评论采集",
    "comment_topic_clustering": "评论主题聚类", "theme_evolution": "话题演变",
    "audience_question_mining": "用户问题提炼", "audience_insights": "受众洞察",
    "wechat_official_metrics": "公众号官方数据", "article_read_metrics": "文章阅读数据",
    "share_metrics": "分享数据", "follower_metrics": "关注数据",
    "domestic_platform_search": "国内平台搜索", "multi_platform_competitor_search": "多平台竞品搜索",
    "competitor_posts": "竞品作品采集", "author_profiles": "作者资料采集", "comment_threads": "评论线程采集",
    "conceptual_illustration": "概念插画", "contact_sheet": "镜头接触表",
    "content_adaptation": "平台内容适配", "cover_design": "封面设计", "cover_editor": "封面编辑器",
    "data_callout": "数据强调卡", "data_card": "数据卡片", "data_visualization": "数据可视化",
    "document_visualization": "文档可视化", "douyin_activity_discovery": "抖音活动发现",
    "douyin_activity_publish": "抖音活动发布", "douyin_publish": "抖音发布",
    "dynamic_chart": "动态图表", "editorial_layout": "编辑式排版", "final_render": "最终渲染",
    "full_edit_provider_routing": "剪辑工具路由", "generated_broll": "生成式 B-roll",
    "gsap_motion": "GSAP 动效", "hand_drawn_illustration": "手绘插画",
    "highlight_detection": "高光片段识别", "html_template": "HTML 模板", "html_video": "HTML 视频",
    "image_generation": "图片生成", "image_to_html": "图片转 HTML", "infographic": "信息图",
    "keyframes": "关键帧提取", "layout_design": "版式设计", "live_photo": "Live Photo",
    "local_asr": "本地语音识别", "long_to_short": "长视频切短", "lottie_asset": "Lottie 动画",
    "lottie_overlay": "Lottie 叠加", "lower_thirds": "人物信息条", "markdown_format": "Markdown 排版",
    "markdown_to_html": "Markdown 转 HTML", "material_center": "素材中心", "motion_design": "动态设计",
    "motion_graphic": "动态图形", "motion_review": "动画评审", "multi_angle_edit": "多机位剪辑",
    "multi_platform_publish": "多平台发布", "multi_platform_analytics": "多平台数据分析",
    "engagement_metrics": "互动指标", "social_dataset_capture": "社媒数据集采集",
    "social_dataset_export": "社媒数据集导出", "browser_social_capture": "浏览器社媒采集",
    "visible_data_export": "可见数据导出", "web_mining": "网页数据挖掘",
    "overlay_animation": "叠加动画", "pacing_cleanup": "节奏清理",
    "platform_api": "平台 API", "platform_readback": "发布结果回读", "platform_upload": "平台上传",
    "poster_design": "海报设计", "product_video": "产品视频", "programmatic_video": "程序化视频",
    "public_asset_collection": "公共素材采集", "publish_operations": "发布运营", "publish_queue": "发布队列",
    "quote_cards": "引用卡片", "reference_download": "参考素材下载", "reference_to_video": "参考图生视频",
    "remotion_render": "Remotion 渲染", "remotion_template": "Remotion 模板",
    "renderer_library_selection": "渲染器选型", "roughcut_plan": "粗剪规划",
    "scene_detection": "镜头识别", "short_clip_distribution": "短视频分发", "shot_list": "镜头清单",
    "shot_recipe_library": "镜头配方库", "cinematic_camera": "电影化运镜", "beat_sync": "节拍卡点",
    "sound_design": "声音设计", "storyboard_review": "分镜审核", "silence_cleanup": "口水词与静音清理",
    "skill_discovery": "Skill 发现", "social_card": "社交媒体卡片", "social_scheduling": "社交媒体排期",
    "subtitle_burnin": "字幕压制", "talking_head_packaging": "口播包装",
    "technical_stack_mapping": "技术栈梳理", "three_d": "三维动画", "timed_caption": "时间轴字幕",
    "transcript": "语音转写", "transition_library": "转场库", "transparent_overlay": "透明叠加素材",
    "tts": "语音合成", "vertical_caption_render": "竖屏字幕渲染", "video_download": "视频下载",
    "video_edit": "视频剪辑", "multi_track_timeline": "多轨时间线", "roughcut": "粗剪",
    "video_metadata": "视频元数据", "subtitle_download": "字幕下载", "thumbnail_download": "封面下载",
    "comment_export": "评论导出", "sample_download": "样片下载",
    "aspect_sentiment": "分方面情绪分析", "comment_opinion_extraction": "评论观点提取", "feature_feedback": "内容要素反馈",
    "causal_inference": "因果推断", "hypothesis_refutation": "假设反驳检验", "confounder_checks": "混杂因素检查",
    "fine_cut": "精剪", "agent_mcp_editing": "Agent 协同剪辑", "edit_proposal_review": "修改提案审核",
    "atomic_undo": "原子撤销", "project_template_library": "工程模板库",
    "video_prompt_design": "视频提示词设计", "video_reading": "视频理解",
    "visual_design": "视觉设计", "visual_polish": "视觉精修", "web_animation": "网页动画",
    "wechat_html_layout": "公众号排版", "weibo_publish": "微博发布", "x_publish": "X 平台发布",
    "xiaohongshu_download": "小红书素材下载", "xiaohongshu_publish": "小红书发布",
    "xiaohongshu_search": "小红书搜索", "xiaohongshu_public_metrics": "小红书公开指标",
    "tiktok_public_metrics": "TikTok 公开指标", "tiktok_search": "TikTok 搜索",
    "x_public_metrics": "X 公开指标", "x_search": "X 内容搜索", "thread_capture": "帖子线程采集",
    "youtube_public_metrics": "YouTube 公开指标", "youtube_search": "YouTube 搜索",
    "video_lookup": "视频信息查询", "comment_lookup": "评论查询", "api_fallback": "API 后备读取",
    "semantic_labels": "语义标签",
}

TEMPLATE_CATEGORY_LABELS = {
    "presentation": "标题与观点呈现", "data-viz": "数据图表", "explainer": "解释型动画",
    "data-visualization": "数据图表", "koubo-scenes": "真人口播包装",
    "ambient": "氛围背景", "marketing": "营销开场", "intro-outro": "片头片尾",
    "social-shorts": "社交短视频", "product-demo": "产品演示", "video-template": "视频组件",
}

STAGE_LABELS = {
    "intake": "内容采集", "intake_and_analysis": "内容采集",
    "brief": "选题 Brief", "draft": "初稿生产", "scene_design": "导演与分镜",
    "asset_generation": "素材生产", "roughcut": "粗剪",
    "render_and_composite": "渲染合成", "caption_and_audio": "字幕与音频",
    "quality_control": "质量检查", "distribution": "发布", "publish": "发布",
    "postmortem": "复盘", "registry_only": "仅注册目录",
}

SKILL_SUMMARIES = {
    "newma-media-sop": "统筹 Newma 自媒体六阶段流程、交付物和质量门禁。",
    "newma-daily-intake": "采集网页、公众号、热点和本地素材，形成可追溯的内容来源池。",
    "newma-daily-phase2": "把采集内容整理成选题卡、研究角度和证据缺口。",
    "newma-daily-draft": "基于 Brief 和证据生成长文、图表计划与公众号底稿。",
    "newma-finance-data": "获取财经数据、官方统计和图表，为文章与视频提供证据。",
    "newma-video-director": "把文章或口播稿重写为审核分镜、生产镜头和导演决策。",
    "newma-video-talking-head": "处理真人出镜口播的粗剪、字幕、动画包装、音频和终版渲染。",
    "newma-video-vox": "规划 VOX 调查解释视频的叙事、证据画面和视觉语法。",
    "newma-vox-skills": "完整执行 VOX 视频，从剧本、分镜、素材到 Remotion 渲染和 QC。",
    "newma-video-explainer-html": "制作无头口播和 HTML 动画解释视频。",
    "newma-digital-human-talking-head": "制作单人或双人 AI 数字人口播与访谈视频。",
    "newma-commercial-promo-video": "制作品牌片、产品宣传片、发布预告和效果广告。",
    "newma-video-roughcut": "执行语音识别、口水词清理、静音剪除和粗剪时间线。",
    "newma-caption-motion": "生成字幕、重点花字、人物机构标签和字幕动效。",
    "newma-ffmpeg-toolkit": "执行视频转码、音量调整、滤镜、拼接和媒体检查。",
    "newma-html-anything-bridge": "调用 HTML Anything 生成文章视觉、卡片和可编辑 HTML。",
    "newma-html-video-bridge": "调用 HTML Video、Remotion、GSAP 和 Lottie 渲染视频场景。",
    "newma-stage-publish": "完成多账号、多平台包装、发布和回执验真。",
    "newma-daily-postmortem": "回收发布数据、对比同题竞品、分析有效因素，并把经审核的经验回写到 Learning。",
    "newma-video-style-trainer": "从参考样片提炼剪辑节奏、构图、转场和视觉 DNA。",
    "newma-video-self-learning": "持续跟踪样板创作者并更新导演知识和风格规则。",
}

PIPELINE_PREVIEWS = {
    "vox_explainer": "vendor/reserved/video/vox-director/assets/thumbs/money.jpg",
    "explainer_html": "vendor/reserved/render/html-video/docs/assets/hero.png",
    "commercial_promo": "vendor/reserved/render/html-video/templates/frame-product-promo-30s/poster.svg",
    "cinematic_short_drama": "vendor/reserved/video/claude-code-video-toolkit/assets/banner/toolkit-banner-poster.png",
    "style_training": "vendor/reserved/video/claude-real-video/docs/crv-demo-poster.jpg",
}

PIPELINE_STAGE_LABELS = {
    "intake": "素材接收", "script_rewrite": "剧本重写", "scene_plan": "导演分镜",
    "asset_build": "素材生产", "edit_composite": "剪辑合成", "edit_decisions": "剪辑设计",
    "roughcut": "粗剪", "render": "渲染", "render_qc": "渲染质检",
    "caption_audio": "字幕音频", "caption_and_audio": "字幕音频",
    "qc_delivery": "质检交付", "quality_control": "质量检查",
    "claim_compliance": "文案合规", "claim_evidence": "证据绑定",
    "presenter_generation": "数字人生成", "investigation_intake": "调查选题接收",
    "omni_reference_frames": "参考图生成", "reference_storyboard_review": "参考分镜审核",
    "shot_video_generation": "逐镜视频生成", "source_preflight": "素材预检",
    "style_analysis": "风格分析", "profile_build": "风格建档",
    "ingest_reference": "参考样片接收", "extract_style_profile": "风格档案提取",
}

PIPELINE_ORDER = {
    "talking_head": 1, "vox_explainer": 2, "explainer_html": 3,
    "digital_human": 4, "commercial_promo": 5, "cinematic_short_drama": 6,
}


def marketplace_asset(path: Path | None) -> dict[str, str] | None:
    if not path or not path.is_file():
        return None
    try:
        relative = path.resolve().relative_to(ROOT.resolve())
    except ValueError:
        return None
    suffix = path.suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".mp4", ".webm"}:
        return None
    asset_path = relative.as_posix()
    return {
        "assetPath": asset_path,
        "url": f"/api/creator-studio/marketplace/assets/{quote(asset_path, safe='/')}",
        "kind": "video" if suffix in {".mp4", ".webm"} else "image",
        "alt": path.stem.replace("-", " ").replace("_", " "),
    }


def first_project_preview(local_path: Path) -> dict[str, str] | None:
    if not local_path.is_dir():
        return None
    ignored = {".git", ".venv", "node_modules", "dist", "build", "coverage"}
    scored: list[tuple[int, Path]] = []
    tokens = ("preview", "hero", "showcase", "demo", "screenshot", "banner", "poster", "thumb")
    for current, dirs, files in os.walk(local_path):
        current_path = Path(current)
        depth = len(current_path.relative_to(local_path).parts)
        dirs[:] = [item for item in dirs if item not in ignored and depth < 4]
        for filename in files:
            path = current_path / filename
            if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".mp4", ".webm"}:
                continue
            lowered = filename.lower()
            if any(token in lowered for token in ("qrcode", "qr-code", "donate", "wechat", "alipay", "icon", "logo")):
                continue
            score = next((index for index, token in enumerate(tokens) if token in lowered), 99)
            if score < 99:
                scored.append((score * 10 + depth, path))
    return marketplace_asset(min(scored, key=lambda item: (item[0], str(item[1])))[1]) if scored else None


def capability_labels(values: list[Any]) -> list[str]:
    return [CAPABILITY_LABELS.get(str(value), str(value).replace("_", " ")) for value in values]


def stage_labels(values: list[Any]) -> list[str]:
    return list(dict.fromkeys(STAGE_LABELS.get(str(value), str(value)) for value in values))


def creator_stage_ids(values: list[Any]) -> list[str]:
    mapping = {
        "intake": "intake", "intake_and_analysis": "intake",
        "brief": "brief", "draft": "draft",
        "scene_design": "transwrite", "asset_generation": "transwrite",
        "roughcut": "transwrite", "render_and_composite": "transwrite",
        "caption_and_audio": "transwrite", "quality_control": "transwrite",
        "distribution": "publish", "publish": "publish", "postmortem": "postmortem",
    }
    return list(dict.fromkeys(mapping[str(value)] for value in values if str(value) in mapping))


def infer_capability_stage_ids(values: list[Any]) -> list[str]:
    text = " ".join(str(value).lower() for value in values)
    rules = (
        ("intake", ("browser", "capture", "source", "intake", "download")),
        ("brief", ("topic", "brief", "research", "trend")),
        ("draft", ("article", "draft", "evidence", "wechat", "chart", "illustration")),
        ("transwrite", ("video", "remotion", "render", "storyboard", "shot", "camera", "caption", "audio", "digital_human")),
        ("publish", ("publish", "distribution", "account", "upload")),
        ("postmortem", ("postmortem", "analytics", "metrics", "attribution")),
    )
    return [stage_id for stage_id, tokens in rules if any(token in text for token in tokens)]


def marketplace_status(*, registration: str, installed: bool, runtime: str, reason: str = "") -> dict[str, Any]:
    labels = {
        "available": ("可直接使用", "ready"), "degraded": ("可用，但能力不完整", "warning"),
        "missing_runtime": ("已注册，缺少运行依赖", "danger"),
        "reference_only": ("仅供参考", "muted"), "deferred": ("已登记，暂缓执行", "warning"),
        "disabled": ("已停用", "muted"),
    }
    label, tone = labels.get(runtime, (runtime, "muted"))
    if not installed:
        label, tone = "已注册，尚未安装", "danger"
    return {
        "discovery": "discovered", "registration": registration,
        "installation": "installed" if installed else "missing",
        "runtime": runtime if installed else "missing_runtime",
        "compatibility": "compatible" if installed else "unknown",
        "label": label, "tone": tone, "reasons": [reason] if reason else [],
    }


def compile_marketplace_project(row: dict[str, Any], indexed: dict[str, Any]) -> dict[str, Any]:
    project_id = str(row.get("name") or "unknown-project")
    local_path = resolve_config_path(str(row.get("local_path") or ""))
    capabilities = list(row.get("capabilities") or indexed.get("capabilities") or [])
    labels = capability_labels(capabilities)
    dependency = str(row.get("dependency_status") or "registered")
    dependency_lower = dependency.lower()
    tier = str(row.get("tier") or "registered")
    if any(token in dependency_lower for token in ("incomplete", "missing", "unavailable")):
        runtime = "missing_runtime"
    elif tier in {"reference", "advisory"} or "reference" in dependency_lower:
        runtime = "reference_only"
    elif "deferred" in dependency_lower or "disabled" in dependency_lower:
        runtime = "deferred"
    elif "partial" in dependency_lower or "optional" in dependency_lower:
        runtime = "degraded"
    else:
        runtime = "available"
    route_stages = list(row.get("route_stages") or indexed.get("route_stages") or [])
    stage_ids = creator_stage_ids(route_stages) or infer_capability_stage_ids(capabilities)
    return {
        "id": project_id, "kind": "project", "name": project_id,
        "summary": f"用于{'、'.join(labels[:4])}。" if labels else f"Newma 已登记的{row.get('category') or '创作'}项目。",
        "category": row.get("category") or "project", "source": row.get("repo"),
        "localPath": row.get("local_path"), "version": row.get("git_head"),
        "tier": tier, "license": row.get("license"), "capabilities": capabilities,
        "capabilityLabels": labels, "stages": stage_labels(route_stages),
        "stageIds": stage_ids,
        "skillIds": [canonical_id(str(item)) for item in row.get("installed_skills", [])],
        "executionMode": indexed.get("execution_mode"), "technicalNotes": row.get("notes"),
        "preview": first_project_preview(local_path),
        "status": marketplace_status(registration="catalog_registered", installed=local_path.is_dir(), runtime=runtime, reason=dependency),
    }


def read_skill_metadata(path: Path) -> dict[str, Any]:
    skill_path = path / "SKILL.md"
    if not skill_path.is_file():
        return {}
    text = skill_path.read_text(encoding="utf-8", errors="replace")
    metadata: dict[str, Any] = {}
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end >= 0:
            loaded = yaml.safe_load(text[4:end]) or {}
            if isinstance(loaded, dict):
                metadata.update(loaded)
    heading = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    if heading:
        metadata["title"] = heading.group(1).strip()
    return metadata


def infer_skill_category(skill_id: str) -> str:
    rules = (
        (("publish", "upload", "xhs", "bilibili"), "发布与账号"),
        (("video", "vox", "caption", "ffmpeg", "remotion"), "视频生产"),
        (("image", "illustration", "cover"), "图片与视觉"),
        (("finance", "data"), "数据与证据"), (("intake", "hotspot", "search"), "内容采集"),
        (("brief", "phase2"), "选题研究"), (("draft", "rewrite", "article"), "写作与排版"),
        (("style", "paradigm", "learning"), "范式学习"),
    )
    return next((label for tokens, label in rules if any(token in skill_id for token in tokens)), "工作流能力")


def infer_skill_stages(skill_id: str) -> list[str]:
    stages: list[str] = []
    rules = (
        (("intake", "hotspot", "search"), "内容采集"), (("brief", "phase2"), "选题 Brief"),
        (("draft", "rewrite", "article", "finance", "illustration"), "初稿生产"),
        (("video", "vox", "caption", "ffmpeg", "html", "digital-human", "commercial"), "多通路转写"),
        (("publish", "upload", "xhs", "bilibili"), "发布"),
        (("postmortem", "style-trainer", "self-learning"), "复盘"),
    )
    for tokens, stage in rules:
        if any(token in skill_id for token in tokens):
            stages.append(stage)
    return list(dict.fromkeys(stages))


def infer_skill_stage_ids(skill_id: str) -> list[str]:
    label_to_id = {
        "内容采集": "intake", "选题 Brief": "brief", "初稿生产": "draft",
        "多通路转写": "transwrite", "发布": "publish", "复盘": "postmortem",
    }
    return [label_to_id[label] for label in infer_skill_stages(skill_id)]


def compile_marketplace_skill(path: Path, project_by_skill: dict[str, str], reference_text: str) -> dict[str, Any]:
    skill_id = canonical_id(path.name)
    metadata = read_skill_metadata(path)
    referenced = path.name in reference_text or skill_id in reference_text
    category = infer_skill_category(skill_id)
    return {
        "id": skill_id, "kind": "skill", "name": str(metadata.get("title") or skill_id),
        "summary": SKILL_SUMMARIES.get(skill_id) or str(metadata.get("description") or ""),
        "category": category, "sourceProjectId": project_by_skill.get(skill_id, "newma-media-studio"),
        "stages": infer_skill_stages(skill_id), "stageIds": infer_skill_stage_ids(skill_id),
        "capabilities": [category], "capabilityLabels": [category],
        "status": marketplace_status(
            registration="workflow_registered" if referenced else "catalog_registered",
            installed=(path / "SKILL.md").is_file(), runtime="available" if (path / "SKILL.md").is_file() else "degraded",
            reason="已被工作流或工具注册表引用" if referenced else "已进入能力目录，尚未绑定具体工作流节点",
        ),
    }


def marketplace_reference_text(registry: dict[str, Any]) -> str:
    chunks = [json.dumps(registry, ensure_ascii=False)]
    for value in registry.get("marketplace", {}).get("source_registries", []):
        path = resolve_config_path(str(value))
        if path.is_file():
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
    pipeline_root = ROOT / "configs" / "video" / "pipelines"
    if pipeline_root.is_dir():
        chunks.extend(path.read_text(encoding="utf-8", errors="replace") for path in pipeline_root.glob("*.yaml"))
    return "\n".join(chunks)


def compile_marketplace_pipelines() -> list[dict[str, Any]]:
    pipeline_root = ROOT / "configs" / "video" / "pipelines"
    rows: list[dict[str, Any]] = []
    if not pipeline_root.is_dir():
        return rows
    for path in sorted(pipeline_root.glob("*.yaml")):
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            continue
        pipeline_id = str(payload.get("id") or path.stem)
        stages = list(payload.get("stages") or [])
        style = payload.get("style_reference") or {}
        deferred = str(payload.get("status") or "").lower() == "deferred" or payload.get("execution_enabled", True) is False
        first_stage, last_stage = (stages[0] if stages else {}), (stages[-1] if stages else {})
        default_format = payload.get("default_format") or {}
        preview_path = PIPELINE_PREVIEWS.get(pipeline_id)
        rows.append({
            "id": pipeline_id, "kind": "pipeline", "name": payload.get("title") or pipeline_id,
            "summary": style.get("principle") or first_stage.get("description") or "Newma 视频生产流水线。",
            "category": "support" if pipeline_id == "style_training" else "production",
            "stageIds": ["transwrite"],
            "sourceProjectId": "newma-media-studio",
            "orchestratorSkill": canonical_id(str(payload.get("orchestrator_skill") or "")),
            "directorId": canonical_id(str(payload.get("director_id") or "")),
            "useCases": list(payload.get("supported_modes") or ([style.get("primary")] if style.get("primary") else [])),
            "inputs": list(first_stage.get("required_artifacts_in") or []), "outputs": list(last_stage.get("produces") or []),
            "aspectRatios": [item for item in [default_format.get("aspect_ratio"), *(default_format.get("alternate_profiles") or [])] if item],
            "flow": [{"id": stage.get("name"), "name": PIPELINE_STAGE_LABELS.get(str(stage.get("name")), str(stage.get("name") or "").replace("_", " ")), "description": stage.get("description")} for stage in stages],
            "preview": marketplace_asset(ROOT / preview_path) if preview_path else None,
            "status": marketplace_status(registration="workflow_registered", installed=True, runtime="deferred" if deferred else "available", reason="流水线已注册但执行开关关闭" if deferred else "已注册到视频导演与渲染流程"),
        })
    return rows


def compile_marketplace_templates(registry: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen_templates: set[tuple[str, str]] = set()
    for root_value in registry.get("marketplace", {}).get("template_roots", []):
        root = resolve_config_path(str(root_value))
        if not root.is_dir():
            continue
        project_id = "html-video" if "html-video" in root.as_posix() else root.name
        for path in sorted(root.iterdir()):
            if not path.is_dir() or (project_id, path.name) in seen_templates:
                continue
            seen_templates.add((project_id, path.name))
            manifest_path = path / "template.html-video.yaml"
            payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
            payload = payload if isinstance(payload, dict) else {}
            output = payload.get("output") or {}
            resolution = output.get("resolution") or {}
            input_schema = (payload.get("inputs") or {}).get("schema") or {}
            preview_value = (payload.get("preview") or {}).get("poster")
            preview = marketplace_asset(path / str(preview_value)) if preview_value else first_project_preview(path)
            category = str(payload.get("category") or "video-template")
            category_label = TEMPLATE_CATEGORY_LABELS.get(category, category.replace("-", " "))
            rows.append({
                "id": str(payload.get("id") or path.name), "kind": "template", "name": payload.get("name") or path.name,
                "summary": f"{category_label}模板，可用于{str((payload.get('best_for') or ['视频场景'])[0])}。",
                "technicalNotes": str(payload.get("description") or "").strip(),
                "category": category, "categoryLabel": category_label, "subcategory": payload.get("subcategory"),
                "stageIds": ["transwrite"],
                "sourceProjectId": project_id, "version": payload.get("version"), "tags": list(payload.get("tags") or []),
                "useCases": list(payload.get("best_for") or []), "inputs": list(input_schema.get("required") or []),
                "outputs": list(output.get("formats") or []), "aspectRatios": list(resolution.get("supported_aspects") or []),
                "engine": payload.get("engine"), "preview": preview,
                "status": marketplace_status(registration="catalog_registered", installed=True, runtime="available", reason=f"模板 Manifest：{manifest_path.relative_to(ROOT) if manifest_path.is_file() else path.relative_to(ROOT)}"),
            })

    openchatcut = next(
        (item for item in registry.get("editor_adapters", []) if item.get("id") == "openchatcut"),
        None,
    )
    if isinstance(openchatcut, dict):
        project, _ = resolve_editor_project(openchatcut)
        installed = project.is_dir()
        runtime_ready = installed and all(
            (project / str(required_path)).exists()
            for required_path in openchatcut.get("required_paths", [])
        )
        for catalog_value in openchatcut.get("template_catalogs", []):
            catalog_path = project / str(catalog_value)
            if not catalog_path.is_file():
                continue
            payload = json.loads(catalog_path.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                continue
            for template in payload:
                if not isinstance(template, dict) or not template.get("id"):
                    continue
                source_template_id = str(template["id"])
                template_id = f"openchatcut-{source_template_id}"
                if ("openchatcut", template_id) in seen_templates:
                    continue
                seen_templates.add(("openchatcut", template_id))
                width = int(template.get("width") or 0)
                height = int(template.get("height") or 0)
                aspect = "9:16" if height > width else "16:9" if width > height else "1:1"
                thumb = str(template.get("thumb") or "").lstrip("/")
                preview_path = project / "assets" / thumb if thumb else None
                category = str(template.get("category") or "video-template")
                category_label = TEMPLATE_CATEGORY_LABELS.get(category, category.replace("-", " "))
                prop_schema = template.get("propSchema") or []
                rows.append({
                    "id": template_id,
                    "sourceTemplateId": source_template_id,
                    "kind": "template",
                    "name": template.get("name") or source_template_id,
                    "summary": str(template.get("description") or f"OpenChatCut {category_label}模板。"),
                    "technicalNotes": f"OpenChatCut 内置模板；{width}×{height}，{template.get('fps') or 30}fps。",
                    "category": category,
                    "categoryLabel": category_label,
                    "stageIds": ["transwrite"],
                    "sourceProjectId": "openchatcut",
                    "tags": list(template.get("tags") or []),
                    "useCases": [category_label, "剪辑中插入", "Agent 可调用"],
                    "inputs": [str(item.get("key")) for item in prop_schema if isinstance(item, dict) and item.get("key")],
                    "outputs": ["motion_overlay", "timeline_item"],
                    "aspectRatios": [aspect],
                    "engine": "OpenChatCut + Remotion",
                    "capabilities": ["motion_overlay", "template_library", "remotion_render"],
                    "preview": marketplace_asset(preview_path),
                    "status": marketplace_status(
                        registration="catalog_registered",
                        installed=installed,
                        runtime="available" if runtime_ready else "missing_runtime",
                        reason=f"OpenChatCut 模板目录：{catalog_path}",
                    ),
                })
        rows.append({
            "id": "openchatcut-user-template",
            "kind": "template",
            "name": "我的 OpenChatCut 工程模板",
            "summary": "把已经跑通的剪辑工程保存为可复用模板，并绑定到 Newma 工作流节点。",
            "category": "video-template",
            "categoryLabel": "我的工程模板",
            "stageIds": ["transwrite"],
            "sourceProjectId": "openchatcut",
            "useCases": ["剪辑完成后入库", "复用完整工程", "教学案例沉淀"],
            "inputs": ["templateId", "editorId"],
            "outputs": ["project_template"],
            "capabilities": ["template_library", "timeline_edit", "preset_selection"],
            "status": marketplace_status(
                registration="workflow_registered",
                installed=installed,
                runtime="available" if runtime_ready else "missing_runtime",
                reason="模板内容由 OpenChatCut 管理，Newma 保存引用、版本和适用节点。",
            ),
        })
    return rows


def compile_marketplace(registry: dict[str, Any]) -> dict[str, Any]:
    reserved = read_json(RESERVED_PROJECTS_PATH)
    project_rows = [
        *(reserved.get("reserve_candidates") or []),
        *(reserved.get("projects") or []),
    ]
    capability_index = reserved.get("project_capability_index", {})
    project_by_skill: dict[str, str] = {}
    for row in project_rows:
        for skill_id in row.get("installed_skills", []):
            project_by_skill[canonical_id(str(skill_id))] = str(row.get("name"))

    reference_text = marketplace_reference_text(registry)
    projects = [
        compile_marketplace_project(row, capability_index.get(row.get("name"), {}))
        for row in project_rows
    ]
    skills = [
        compile_marketplace_skill(path, project_by_skill, reference_text)
        for path in sorted((ROOT / "skills").iterdir())
        if path.is_dir() and not path.name.startswith(".")
    ]
    all_pipelines = compile_marketplace_pipelines()
    pipelines = sorted(
        (item for item in all_pipelines if item.get("category") == "production"),
        key=lambda item: PIPELINE_ORDER.get(str(item.get("id")), 99),
    )
    support_pipelines = [item for item in all_pipelines if item.get("category") == "support"]
    templates = compile_marketplace_templates(registry)
    ready_count = sum(
        item.get("status", {}).get("runtime") == "available"
        for group in (projects, skills, pipelines, support_pipelines, templates)
        for item in group
    )
    return {
        "schema_version": "newma.creator_marketplace.v2",
        "generated_at": now_iso(),
        "counts": {
            "projects": len(projects),
            "repositories": len(projects),
            "skills": len(skills),
            "pipelines": len(pipelines),
            "templates": len(templates),
            "supportPipelines": len(support_pipelines),
            "ready": ready_count,
        },
        "projects": projects,
        "repositories": projects,
        "skills": skills,
        "pipelines": pipelines,
        "supportPipelines": support_pipelines,
        "templates": templates,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Newma Creator Studio 控制 Module")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("registry", help="输出六阶段工作流注册表。")

    snapshot_parser = subparsers.add_parser("snapshot", help="从项目 Manifest 生成状态看板快照。")
    snapshot_parser.add_argument("manifest")
    snapshot_parser.add_argument("--output", default="")

    validate_parser = subparsers.add_parser("validate-node", help="校验当前节点素材是否齐全。")
    validate_parser.add_argument("--stage", required=True)
    validate_parser.add_argument("--node", required=True)
    validate_parser.add_argument("--material", action="append", default=[])
    validate_parser.add_argument("--upstream-manifest", default="")
    validate_parser.add_argument("--project-start", action="store_true")

    handoff_parser = subparsers.add_parser("handoff", help="把上游交付物转接到目标节点。")
    handoff_parser.add_argument("manifest")
    handoff_parser.add_argument("--target-stage", required=True)
    handoff_parser.add_argument("--target-node", required=True)
    handoff_parser.add_argument("--type", action="append", default=[])
    handoff_parser.add_argument("--output", required=True)

    init_parser = subparsers.add_parser("init-node-project", help="从任意节点创建项目。")
    init_parser.add_argument("--title", required=True)
    init_parser.add_argument("--stage", required=True)
    init_parser.add_argument("--node", required=True)
    init_parser.add_argument("--material", action="append", default=[])
    init_parser.add_argument("--output-root", default="")
    init_parser.add_argument("--run-id", default="")

    subparsers.add_parser("detect-capabilities", help="检测本机已安装的 CLI 能力。")

    invoke_parser = subparsers.add_parser("invoke-cli", help="调用已注册的 output-only CLI Adapter。")
    invoke_parser.add_argument("--agent", required=True)
    invoke_parser.add_argument("--prompt", default="")
    invoke_parser.add_argument("--prompt-file", default="")
    invoke_parser.add_argument("--workdir", default=str(ROOT))
    invoke_parser.add_argument("--timeout", type=int, default=180)
    invoke_parser.add_argument("--bin-override", default="")
    invoke_parser.add_argument("--output", default="")

    run_node_parser = subparsers.add_parser("run-node", help="调用节点已注册的白名单执行器。")
    run_node_parser.add_argument("--request-file", default="-", help="节点执行请求 JSON；- 表示 stdin。")
    run_node_parser.add_argument("--output", default="")

    launch_editor_parser = subparsers.add_parser("launch-editor", help="启动已注册的人工编辑器。")
    launch_editor_parser.add_argument("--request-file", default="-", help="编辑会话请求 JSON；- 表示 stdin。")
    launch_editor_parser.add_argument("--output", default="")

    import_export_parser = subparsers.add_parser(
        "materialize-editor-export",
        help="把已完成的编辑器导出固化为 Newma 交付物。",
    )
    import_export_parser.add_argument("--request-file", default="-", help="导出回写请求 JSON；- 表示 stdin。")
    import_export_parser.add_argument("--output", default="")

    market_parser = subparsers.add_parser("marketplace", help="编译仓库、Skills 与模板超市。")
    market_parser.add_argument("--output", default="")

    batch_parser = subparsers.add_parser("batch-ingest", help="批量灌入素材并创建/启动对应阶段节点。")
    approve_gate_parser = subparsers.add_parser(
        "approve-gate", help="把阶段 gate 文件状态翻 approved（review-gate approve 联动写盘）。"
    )
    approve_gate_parser.add_argument("--run-id", required=True)
    approve_gate_parser.add_argument("--stage", required=True)
    approve_gate_parser.add_argument("--gate-file", default="", help="显式 gate 文件路径（默认按阶段 canonical 路径）")
    approve_gate_parser.add_argument("--selected-ids", default="", help="选题 gate 专用：逗号分隔的入选 topic_id 列表")
    batch_parser.add_argument("--stage", default="intake", help="起始阶段 ID（默认 intake）")
    batch_parser.add_argument("--node", default="source_setup", help="起始节点 ID（默认 source_setup）")
    batch_parser.add_argument("--title", default="", help="任务名称（默认为当天日期 MMdd）")
    batch_parser.add_argument("--run-node", action="store_true", help="创建后立即调用 creator.node.run")
    batch_parser.add_argument("--output", default="", dest="batch_output")
    batch_parser.add_argument("sources", nargs="*", help="来源素材：URL、文件路径或文本内容")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry = load_registry()
    try:
        if args.command == "registry":
            emit(registry)
            return 0
        if args.command == "snapshot":
            emit(build_snapshot(read_json(Path(args.manifest).expanduser().resolve()), registry), args.output)
            return 0
        if args.command == "validate-node":
            materials = [material_from_pair(item) for item in args.material]
            if args.upstream_manifest:
                materials.extend(artifact_materials(read_json(Path(args.upstream_manifest).expanduser().resolve())))
            emit(
                validate_node_materials(
                    registry,
                    args.stage,
                    args.node,
                    materials,
                    allow_manual_bootstrap=args.project_start,
                )
            )
            return 0
        if args.command == "handoff":
            payload = build_handoff(
                read_json(Path(args.manifest).expanduser().resolve()),
                registry,
                args.target_stage,
                args.target_node,
                args.type,
            )
            emit(payload, args.output)
            return 0 if payload["status"] == "ready" else 2
        if args.command == "init-node-project":
            manifest, manifest_path = init_node_project(
                args.title,
                args.stage,
                args.node,
                [material_from_pair(item) for item in args.material],
                args.output_root,
                args.run_id,
            )
            emit({"status": "succeeded", "manifest": str(manifest_path), "snapshot": build_snapshot(manifest, registry)})
            return 0
        if args.command == "approve-gate":
            emit(approve_stage_gate(args.run_id, args.stage, args.gate_file, args.selected_ids))
            return 0
        if args.command == "detect-capabilities":
            emit(detect_cli_capabilities(registry))
            return 0
        if args.command == "invoke-cli":
            prompt = args.prompt
            if args.prompt_file:
                prompt = Path(args.prompt_file).expanduser().resolve().read_text(encoding="utf-8")
            if not prompt.strip():
                raise ValueError("prompt 或 prompt-file 不能为空")
            emit(
                invoke_cli(
                    args.agent,
                    prompt,
                    args.workdir,
                    args.timeout,
                    args.bin_override,
                ),
                args.output,
            )
            return 0
        if args.command == "run-node":
            request = (
                json.load(sys.stdin)
                if args.request_file == "-"
                else read_json(Path(args.request_file).expanduser().resolve())
            )
            payload = run_registered_node(request, registry)
            emit(payload, args.output)
            return 0 if payload["status"] != "failed" else 2
        if args.command == "launch-editor":
            request = (
                json.load(sys.stdin)
                if args.request_file == "-"
                else read_json(Path(args.request_file).expanduser().resolve())
            )
            payload = launch_registered_editor(request, registry)
            emit(payload, args.output)
            return 0 if payload["status"] == "open" else 2
        if args.command == "materialize-editor-export":
            request = (
                json.load(sys.stdin)
                if args.request_file == "-"
                else read_json(Path(args.request_file).expanduser().resolve())
            )
            payload = materialize_editor_export(request, registry)
            emit(payload, args.output)
            return 0
        if args.command == "marketplace":
            emit(compile_marketplace(registry), args.output)
            return 0
        if args.command == "batch-ingest":
            title = args.title or datetime.now().strftime("%m%d")
            materials: list[dict[str, Any]] = []
            for src in args.sources:
                if src.startswith("http://") or src.startswith("https://"):
                    materials.append({"type": "source", "path": src, "source": "manual", "label": src[:60]})
                elif Path(src).expanduser().exists():
                    materials.append({"type": "source", "path": str(Path(src).expanduser().resolve()), "source": "manual", "label": Path(src).name})
                else:
                    # Treat as inline text — write to temp file
                    tmp_path = Path(get_desktop_root()) / "_tmp" / f"_batch_text_{uuid4().hex[:8]}.txt"
                    tmp_path.parent.mkdir(parents=True, exist_ok=True)
                    tmp_path.write_text(src, encoding="utf-8")
                    materials.append({"type": "source", "path": str(tmp_path), "source": "manual", "label": f"文本: {src[:40]}"})
            manifest, manifest_path = init_node_project(
                title,
                args.stage,
                args.node,
                materials,
                "",
                "",
            )
            result: dict[str, Any] = {
                "status": "succeeded",
                "manifest": str(manifest_path),
                "title": title,
                "stage": args.stage,
                "node": args.node,
                "materials_count": len(materials),
            }
            if args.run_node:
                # Forward to API if running
                api_url = f"http://127.0.0.1:8911/api/creator-studio/runs"
                try:
                    import urllib.request
                    body = json.dumps({
                        "title": title,
                        "stageId": args.stage,
                        "nodeId": args.node,
                        "materials": [{"type": m["type"], "path": m["path"], "source": m["source"], "label": m.get("label", "")} for m in materials],
                    }).encode()
                    req = urllib.request.Request(api_url, data=body, headers={
                        "Content-Type": "application/json",
                        "X-User-Id": "batch-cli",
                        "X-Workspace-Id": "default",
                    }, method="POST")
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        api_result = json.loads(resp.read())
                        result["api_run"] = api_result.get("run", {}).get("runId")
                        result["api_status"] = "created"
                except Exception as exc:
                    result["api_status"] = f"failed: {exc}"
            emit(result, args.batch_output)
            return 0
    except (FileNotFoundError, KeyError, ValueError, subprocess.TimeoutExpired) as exc:
        emit({"status": "failed", "error": str(exc)})
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
