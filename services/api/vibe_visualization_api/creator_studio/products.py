from __future__ import annotations

import fnmatch
import mimetypes
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


STAGE_DIRS = {
    "01_采集": "intake",
    "02_选题": "brief",
    "03_初稿": "draft",
    "04_转写": "transwrite",
    "05_发布": "publish",
    "06_复盘": "postmortem",
}

SYSTEM_FILE_NAMES = {
    "execution_result.json",
    "project_run_manifest.json",
}

SYSTEM_FILE_PREFIXES = (
    "editor-",
    "execution_request",
)

SYSTEM_ARTIFACT_ORIGINS = {"packet", "system", "runtime"}

TECHNICAL_OUTPUTS = {
    "editor_session",
    "execution_request",
    "source_plan",
    "source_material_index",
    "publish_jobs",
}


def _output_label(value: str) -> str:
    labels = {
        "intake_records": "全部热点记录",
        "duplicate_report": "去重与冲突报告",
        "event_clusters": "事件归并报告",
        "topic_cards": "候选选题卡",
        "topic_ranking": "选题排序",
        "selected_topics": "入选题目",
        "research_plan": "研究计划",
        "brief_manifest": "详细 Brief",
        "article_outline": "文章提纲",
        "data_tables": "数据表",
        "image_pool": "图表与图片素材",
        "article_markdown": "文章初稿",
        "article_html": "文章 HTML 预览",
        "illustrated_article": "图文成稿",
        "title_candidates": "候选标题",
        "video_script": "视频口播稿",
        "scene_plan": "导演分镜",
        "storyboard_review": "分镜审阅页",
        "review_render": "视频审片",
        "edited_master": "剪辑成片",
        "final_delivery_manifest": "最终交付清单",
        "channel_packs": "平台发布包",
        "platform_receipts": "平台发布回执",
        "postmortem_report": "传播复盘报告",
        "next_cycle_plan": "下一轮行动计划",
    }
    return labels.get(value, value.replace("_", " "))


def _normalize_spec(value: Any) -> dict[str, Any] | None:
    if isinstance(value, str) and value.strip():
        output_type = value.strip()
        return {"type": output_type, "label": _output_label(output_type), "patterns": []}
    if not isinstance(value, dict):
        return None
    output_type = str(value.get("type") or "").strip()
    if not output_type:
        return None
    patterns = value.get("patterns") or value.get("pattern") or []
    if isinstance(patterns, str):
        patterns = [patterns]
    return {
        **value,
        "type": output_type,
        "label": str(value.get("label") or _output_label(output_type)),
        "patterns": [str(item) for item in patterns if str(item).strip()],
    }


def _contract_specs(node: dict[str, Any], role: str) -> list[dict[str, Any]]:
    contract = node.get("product") if isinstance(node.get("product"), dict) else {}
    key = "primary_outputs" if role == "primary" else "supporting_outputs"
    values = contract.get(key, [])
    if role == "primary" and not values:
        values = [
            item
            for item in node.get("outputs", [])
            if str(item) not in TECHNICAL_OUTPUTS
        ]
    specs = [_normalize_spec(item) for item in values]
    return [item for item in specs if item is not None]


class CreatorProductCatalog:
    """Projects workflow files into user products without polluting artifact lineage."""

    @staticmethod
    def _candidate_paths(document: dict[str, Any]) -> list[Path]:
        candidates: list[Path] = []
        for state in (document.get("nodeStates") or {}).values():
            for item in [*(state.get("artifacts") or []), *(state.get("materials") or [])]:
                value = str(item.get("path") or "").strip()
                if value and not value.startswith(("http://", "https://", "dasheng-local://")):
                    candidates.append(Path(value).expanduser())
        return candidates

    def run_root(self, document: dict[str, Any]) -> Path | None:
        run_id = str(document.get("runId") or "")
        for candidate in self._candidate_paths(document):
            resolved = candidate.resolve(strict=False)
            for parent in (resolved, *resolved.parents):
                if parent.name == run_id and parent.is_dir():
                    return parent
        fallback = Path.home() / "Desktop" / "自媒体创作" / run_id
        return fallback.resolve() if fallback.is_dir() else None

    @staticmethod
    def _path_location(relative_path: str) -> tuple[str | None, str | None]:
        parts = Path(relative_path).parts
        if len(parts) >= 3 and parts[0] == "nodes":
            return parts[1], parts[2]
        return (STAGE_DIRS.get(parts[0]), None) if parts else (None, None)

    @staticmethod
    def _matches(relative_path: str, spec: dict[str, Any]) -> bool:
        patterns = spec.get("patterns") or []
        return any(
            fnmatch.fnmatch(relative_path, pattern)
            or relative_path.endswith(pattern.lstrip("*/"))
            for pattern in patterns
        )

    def build(
        self,
        document: dict[str, Any],
        registry: dict[str, Any],
    ) -> dict[str, Any]:
        root = self.run_root(document)
        if root is None:
            return {"root": None, "entries": [], "counts": {}}

        artifact_by_path: dict[str, dict[str, Any]] = {}
        for state_key, state in (document.get("nodeStates") or {}).items():
            stage_id, _, node_id = str(state_key).partition(".")
            for artifact in state.get("artifacts") or []:
                path_value = str(artifact.get("path") or "").strip()
                if path_value:
                    artifact_by_path[str(Path(path_value).expanduser().resolve(strict=False))] = {
                        **artifact,
                        "stageId": stage_id,
                        "nodeId": node_id,
                    }

        product_specs: list[dict[str, Any]] = []
        for stage in registry.get("stages", []):
            stage_id = str(stage.get("id") or "")
            for node in stage.get("nodes", []):
                node_id = str(node.get("id") or "")
                for role in ("primary", "supporting"):
                    for spec in _contract_specs(node, role):
                        product_specs.append(
                            {**spec, "role": role, "stageId": stage_id, "nodeId": node_id}
                        )

        entries: list[dict[str, Any]] = []
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            relative_path = path.relative_to(root).as_posix()
            parts = Path(relative_path).parts
            if any(part.startswith(".") for part in parts):
                continue
            stage_id, node_id = self._path_location(relative_path)
            artifact = artifact_by_path.get(str(path.resolve()))
            if artifact:
                stage_id = str(artifact.get("stageId") or stage_id or "") or None
                node_id = str(artifact.get("nodeId") or node_id or "") or None

            matched = next(
                (
                    spec
                    for spec in product_specs
                    if spec.get("patterns") and self._matches(relative_path, spec)
                ),
                None,
            )
            artifact_origin = str((artifact or {}).get("origin") or "")
            if matched is None and artifact and artifact_origin not in SYSTEM_ARTIFACT_ORIGINS:
                matched = next(
                    (
                        spec
                        for spec in product_specs
                        if spec["stageId"] == stage_id
                        and spec["nodeId"] == node_id
                        and spec["type"] == artifact.get("type")
                    ),
                    None,
                )
            if matched:
                role = str(matched["role"])
                stage_id = str(matched["stageId"])
                node_id = str(matched["nodeId"])
                output_type = str(matched["type"])
                label = str(matched["label"])
            else:
                output_type = str((artifact or {}).get("type") or path.stem)
                label = str((artifact or {}).get("label") or path.name)
                if (
                    artifact_origin in SYSTEM_ARTIFACT_ORIGINS
                    or path.name in SYSTEM_FILE_NAMES
                    or path.name.startswith(SYSTEM_FILE_PREFIXES)
                ):
                    role = "system"
                elif "raw" in parts:
                    role = "raw"
                else:
                    role = "supporting"

            stat = path.stat()
            mime_type, _ = mimetypes.guess_type(str(path))
            entries.append(
                {
                    "id": f"file:{relative_path}",
                    "name": path.name,
                    "label": label,
                    "type": output_type,
                    "path": str(path),
                    "relativePath": relative_path,
                    "stageId": stage_id,
                    "nodeId": node_id,
                    "role": role,
                    "status": str((artifact or {}).get("status") or "ready"),
                    "source": "artifact" if artifact else "catalog",
                    "artifactId": (artifact or {}).get("id"),
                    "version": int((artifact or {}).get("version") or 1),
                    "mimeType": mime_type or "application/octet-stream",
                    "size": stat.st_size,
                    "modifiedAt": datetime.fromtimestamp(stat.st_mtime, UTC).isoformat(),
                }
            )

        counts: dict[str, int] = {}
        for entry in entries:
            role = str(entry["role"])
            counts[role] = counts.get(role, 0) + 1
        return {"root": str(root), "entries": entries, "counts": counts}

    def resolve_node(
        self,
        stage_id: str,
        node: dict[str, Any],
        state: dict[str, Any],
        file_catalog: dict[str, Any],
    ) -> dict[str, Any]:
        node_id = str(node.get("id") or "")
        contract = node.get("product") if isinstance(node.get("product"), dict) else {}
        primary_specs = _contract_specs(node, "primary")
        supporting_specs = _contract_specs(node, "supporting")
        entries = file_catalog.get("entries") or []

        def resolve(specs: list[dict[str, Any]], role: str) -> list[dict[str, Any]]:
            resolved: list[dict[str, Any]] = []
            for spec in specs:
                matches = [
                    entry
                    for entry in entries
                    if (
                        entry.get("stageId") == stage_id
                        and entry.get("nodeId") == node_id
                        and entry.get("role") == role
                        and (
                            entry.get("type") == spec["type"]
                            or self._matches(str(entry.get("relativePath") or ""), spec)
                        )
                    )
                ]
                for artifact in state.get("artifacts") or []:
                    if str(artifact.get("origin") or "") in SYSTEM_ARTIFACT_ORIGINS:
                        continue
                    if str(artifact.get("type") or "") != spec["type"]:
                        continue
                    path_value = str(artifact.get("path") or "")
                    if any(item.get("path") == path_value for item in matches):
                        continue
                    matches.append(
                        {
                            "id": f"artifact:{artifact.get('id')}",
                            "name": Path(path_value).name,
                            "label": artifact.get("label") or spec["label"],
                            "type": spec["type"],
                            "path": path_value,
                            "relativePath": path_value,
                            "stageId": stage_id,
                            "nodeId": node_id,
                            "role": role,
                            "status": artifact.get("status") or "created",
                            "source": "artifact",
                            "artifactId": artifact.get("id"),
                            "version": int(artifact.get("version") or 1),
                            "mimeType": mimetypes.guess_type(path_value)[0] or "application/octet-stream",
                        }
                    )
                for item in matches:
                    resolved.append({**item, "label": spec["label"], "role": role})
            unique: dict[str, dict[str, Any]] = {}
            for item in resolved:
                if str(item.get("status") or "") in {"stale", "superseded", "failed"}:
                    continue
                unique[str(item.get("path") or item.get("id"))] = item
            return list(unique.values())

        deliverables = resolve(primary_specs, "primary")
        supporting_files = resolve(supporting_specs, "supporting")
        expected = [
            {
                "type": spec["type"],
                "label": spec["label"],
                "ready": any(item.get("type") == spec["type"] for item in deliverables),
            }
            for spec in primary_specs
        ]
        return {
            "kind": str(contract.get("kind") or "deliverable"),
            "title": str(contract.get("title") or node.get("name") or "节点交付"),
            "summary": str(contract.get("summary") or node.get("description") or ""),
            "interaction": contract.get("interaction") or {"mode": "preview"},
            "expected": expected,
            "deliverables": deliverables,
            "supportingFiles": supporting_files,
            "availableCount": len(deliverables),
            "expectedCount": len(expected),
            "status": "ready" if deliverables else "pending",
        }
