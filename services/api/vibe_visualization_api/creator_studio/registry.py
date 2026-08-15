from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from vibe_visualization_api.creator_studio.models import CreatorMaterialInput


class CreatorStudioUnavailableError(Exception):
    """Raised when the Creator Studio registry cannot be loaded."""


class CreatorDefinitionError(Exception):
    """Raised when a stage or node is not registered."""


class CreatorMaterialError(Exception):
    def __init__(self, report: dict[str, Any]):
        super().__init__("node materials are incomplete")
        self.report = report


class CreatorRegistry:
    def __init__(self, workspace: Path):
        self.workspace = workspace.expanduser().resolve()
        self.path = (
            self.workspace
            / "configs"
            / "workflow"
            / "newma_creator_studio_registry.json"
        )

    def load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CreatorStudioUnavailableError(
                f"Creator Studio registry unavailable: {self.path}"
            ) from error
        if not isinstance(value, dict) or not isinstance(value.get("stages"), list):
            raise CreatorStudioUnavailableError("Creator Studio registry is invalid")
        return value

    def stage(self, registry: dict[str, Any], stage_id: str) -> dict[str, Any]:
        for stage in registry.get("stages", []):
            if stage.get("id") == stage_id:
                return stage
        raise CreatorDefinitionError(f"unknown Creator Studio stage: {stage_id}")

    def node(
        self,
        registry: dict[str, Any],
        stage_id: str,
        node_id: str,
    ) -> dict[str, Any]:
        stage = self.stage(registry, stage_id)
        for node in stage.get("nodes", []):
            if node.get("id") == node_id:
                return node
        raise CreatorDefinitionError(
            f"unknown Creator Studio node: {stage_id}/{node_id}"
        )

    def next_node(
        self,
        registry: dict[str, Any],
        stage_id: str,
        node_id: str,
    ) -> tuple[str, str] | None:
        stages = registry.get("stages", [])
        for stage_index, stage in enumerate(stages):
            if stage.get("id") != stage_id:
                continue
            nodes = stage.get("nodes", [])
            for node_index, node in enumerate(nodes):
                if node.get("id") != node_id:
                    continue
                if node_index + 1 < len(nodes):
                    return stage_id, str(nodes[node_index + 1]["id"])
                if stage_index + 1 < len(stages):
                    next_stage = stages[stage_index + 1]
                    next_nodes = next_stage.get("nodes", [])
                    if next_nodes:
                        return str(next_stage["id"]), str(next_nodes[0]["id"])
                return None
        raise CreatorDefinitionError(
            f"unknown Creator Studio node: {stage_id}/{node_id}"
        )

    @staticmethod
    def _matches(requirement: dict[str, Any], material: dict[str, Any]) -> bool:
        material_type = str(material.get("type") or "")
        if material_type == str(requirement.get("type") or ""):
            return True
        if material_type not in {"file", "source", "url", "artifact"}:
            return False
        value = str(material.get("path") or "").lower()
        accepts = [str(item).lower() for item in requirement.get("accepts", [])]
        if value.startswith(("http://", "https://")) and "url" in accepts:
            return True
        return any(item.startswith(".") and value.endswith(item) for item in accepts)

    def validate_materials(
        self,
        registry: dict[str, Any],
        stage_id: str,
        node_id: str,
        materials: list[dict[str, Any] | CreatorMaterialInput],
        *,
        project_start: bool = False,
    ) -> dict[str, Any]:
        node = self.node(registry, stage_id, node_id)
        normalized = [
            item.model_dump(by_alias=False) if isinstance(item, CreatorMaterialInput) else item
            for item in materials
        ]
        bindings: list[dict[str, Any]] = []
        missing: list[dict[str, Any]] = []
        for requirement in node.get("material_requirements", []):
            allowed_sources = set(requirement.get("sources") or ["manual", "upstream"])
            if project_start:
                allowed_sources.add("manual")
            match = next(
                (
                    item
                    for item in normalized
                    if str(item.get("source") or "manual") in allowed_sources
                    and str(item.get("status") or "active")
                    not in {"stale", "superseded", "failed"}
                    and self._matches(requirement, item)
                ),
                None,
            )
            if match:
                bindings.append(
                    {
                        "requirementType": requirement.get("type"),
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
            "stageId": stage_id,
            "nodeId": node_id,
            "bindings": bindings,
            "missing": missing,
        }
