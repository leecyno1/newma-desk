from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4


CURRENT_ARTIFACT_STATUSES = {"created", "approved", "succeeded"}


class ArtifactLineage:
    """Version, parent and stale propagation rules for Creator Artifacts."""

    @staticmethod
    def _digest(value: Any) -> str:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def _content_digest(cls, artifact_type: str, path_value: str) -> str:
        if not urlparse(path_value).scheme:
            path = Path(path_value).expanduser()
            if path.is_file():
                try:
                    digest = hashlib.sha256()
                    with path.open("rb") as handle:
                        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                            digest.update(chunk)
                    return digest.hexdigest()
                except OSError:
                    pass
        return cls._digest({"type": artifact_type, "path": path_value})

    @staticmethod
    def _parents(state: dict[str, Any]) -> list[dict[str, Any]]:
        parents: list[dict[str, Any]] = []
        seen: set[tuple[str, int]] = set()
        for material in state.get("materials", []):
            artifact_id = str(material.get("artifactId") or "").strip()
            if not artifact_id:
                continue
            version = int(material.get("artifactVersion") or 1)
            key = (artifact_id, version)
            if key in seen:
                continue
            seen.add(key)
            parents.append(
                {
                    "artifactId": artifact_id,
                    "version": version,
                    "contentDigest": material.get("contentDigest"),
                    "runId": material.get("sourceRunId"),
                    "stageId": material.get("sourceStageId"),
                    "nodeId": material.get("sourceNodeId"),
                }
            )
        return parents

    def register_artifact(
        self,
        document: dict[str, Any],
        *,
        stage_id: str,
        node_id: str,
        artifact: dict[str, Any],
        created_at: str,
        producer_job_id: str | None = None,
        execution_id: str | None = None,
        editor_session_id: str | None = None,
    ) -> tuple[dict[str, Any], list[dict[str, str]]]:
        state = document["nodeStates"][f"{stage_id}.{node_id}"]
        artifact_type = str(artifact.get("type") or "").strip()
        artifact_slot = str(artifact.get("slot") or "").strip() or None
        artifact_path = str(artifact.get("path") or "").strip()
        if not artifact_type or not artifact_path:
            raise ValueError("artifact type and path are required")

        previous = [
            item
            for item in state.get("artifacts", [])
            if str(item.get("type") or "") == artifact_type
            and (str(item.get("slot") or "").strip() or None) == artifact_slot
            and str(item.get("status") or "created") in CURRENT_ARTIFACT_STATUSES
        ]
        requested_status = str(artifact.get("status") or "created")
        stale_parent = next(
            (
                item
                for item in state.get("materials", [])
                if item.get("artifactId") and item.get("status") == "stale"
            ),
            None,
        )
        artifact_status = (
            "stale"
            if stale_parent and requested_status in CURRENT_ARTIFACT_STATUSES
            else requested_status
        )
        version = max(
            (
                int(item.get("version") or 1)
                for item in state.get("artifacts", [])
                if item.get("type") == artifact_type
                and (str(item.get("slot") or "").strip() or None) == artifact_slot
            ),
            default=0,
        ) + 1
        artifact_id = str(artifact.get("id") or f"artifact-{uuid4().hex[:12]}")
        created = {
            "id": artifact_id,
            "type": artifact_type,
            "path": artifact_path,
            "label": artifact.get("label") or artifact_type,
            "status": artifact_status,
            "origin": str(artifact.get("origin") or "deliverable"),
            "version": version,
            "contentDigest": self._content_digest(artifact_type, artifact_path),
            "parents": self._parents(state),
            "producerJobId": producer_job_id,
            "parametersDigest": self._digest(state.get("parameters", {})),
            "createdAt": created_at,
        }
        if artifact_slot:
            created["slot"] = artifact_slot
        if execution_id:
            created["executionId"] = execution_id
        if editor_session_id:
            created["editorSessionId"] = editor_session_id
        if artifact_status == "stale" and stale_parent:
            created["staleAt"] = stale_parent.get("staleAt") or created_at
            created["staleReason"] = (
                stale_parent.get("staleReason") or "父产物版本已失效"
            )
        state.setdefault("artifacts", []).append(created)

        impacts: list[dict[str, str]] = []
        if str(created["status"]) in CURRENT_ARTIFACT_STATUSES and previous:
            for item in previous:
                item["status"] = "superseded"
                item["supersededAt"] = created_at
                item["supersededByArtifactId"] = artifact_id
            impacts = self.mark_downstream_stale(
                document,
                source_stage_id=stage_id,
                source_node_id=node_id,
                artifact_ids={str(item["id"]) for item in previous},
                artifact_types=set() if artifact_slot else {artifact_type},
                reason=(
                    f"{stage_id}/{node_id} 生成了 {artifact_type}[{artifact_slot}] v{version}"
                    if artifact_slot
                    else f"{stage_id}/{node_id} 生成了 {artifact_type} v{version}"
                ),
                stale_at=created_at,
            )
        return created, impacts

    @staticmethod
    def material_reference(
        *,
        run_id: str,
        stage_id: str,
        node_id: str,
        artifact: dict[str, Any],
    ) -> dict[str, Any]:
        material = {
            "type": artifact["type"],
            "path": artifact["path"],
            "source": "upstream",
            "label": artifact.get("label") or artifact["type"],
            "artifactId": artifact["id"],
            "artifactVersion": int(artifact.get("version") or 1),
            "contentDigest": artifact.get("contentDigest"),
            "sourceRunId": run_id,
            "sourceStageId": stage_id,
            "sourceNodeId": node_id,
            "status": "active",
        }
        if artifact.get("slot"):
            material["slot"] = artifact["slot"]
        return material

    def mark_downstream_stale(
        self,
        document: dict[str, Any],
        *,
        source_stage_id: str,
        source_node_id: str,
        artifact_ids: set[str],
        artifact_types: set[str],
        reason: str,
        stale_at: str,
    ) -> list[dict[str, str]]:
        queue: list[tuple[str, str, bool]] = [
            (source_stage_id, source_node_id, True)
        ]
        visited: set[tuple[str, str]] = set()
        impacts: list[dict[str, str]] = []

        while queue:
            current_stage_id, current_node_id, first_hop = queue.pop(0)
            current_key = (current_stage_id, current_node_id)
            if current_key in visited:
                continue
            visited.add(current_key)
            for handoff in document.get("handoffs", []):
                source = handoff.get("source") or {}
                if (
                    source.get("stageId") != current_stage_id
                    or source.get("nodeId") != current_node_id
                    or handoff.get("status") == "superseded"
                ):
                    continue
                materials = handoff.get("materials", [])
                if first_hop and not any(
                    str(item.get("artifactId") or "") in artifact_ids
                    or str(item.get("type") or "") in artifact_types
                    for item in materials
                ):
                    continue

                handoff["status"] = "stale"
                handoff["staleAt"] = stale_at
                handoff["staleReason"] = reason
                for material in materials:
                    material["status"] = "stale"
                    material["staleAt"] = stale_at

                target = handoff.get("target") or {}
                target_stage_id = str(target.get("stageId") or "")
                target_node_id = str(target.get("nodeId") or "")
                target_state = document["nodeStates"].get(
                    f"{target_stage_id}.{target_node_id}"
                )
                if target_state is None:
                    continue
                handoff_ids = {
                    str(item.get("artifactId") or "") for item in materials
                }
                for material in target_state.get("materials", []):
                    if str(material.get("artifactId") or "") in handoff_ids:
                        material["status"] = "stale"
                        material["staleAt"] = stale_at
                        material["staleReason"] = reason
                for artifact in target_state.get("artifacts", []):
                    if str(artifact.get("status") or "created") in CURRENT_ARTIFACT_STATUSES:
                        artifact["status"] = "stale"
                        artifact["staleAt"] = stale_at
                        artifact["staleReason"] = reason

                if target_state.get("status") in {"queued", "running"}:
                    target_state["stalePending"] = {
                        "at": stale_at,
                        "reason": reason,
                    }
                else:
                    target_state["status"] = "stale"
                    target_state["progress"] = 0
                    target_state["staleAt"] = stale_at
                    target_state["staleReason"] = reason
                target_state.setdefault("logs", []).append(
                    {"at": stale_at, "message": f"上游版本变化，当前节点已失效：{reason}"}
                )
                impacts.append(
                    {"stageId": target_stage_id, "nodeId": target_node_id}
                )
                queue.append((target_stage_id, target_node_id, False))

        if impacts:
            document["status"] = "changes_requested"
            document["lineageState"] = {
                "lastInvalidatedAt": stale_at,
                "reason": reason,
                "affectedNodes": impacts,
            }
        return impacts
