from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from path_config import get_output_root, get_project_root, get_stage_dir


ROOT = get_project_root()

OPTIONAL_ASSET_ROOTS: dict[str, Path] = {
    "paradigm": get_output_root("paradigm"),
    "video_training": get_output_root("video_training"),
}

# 六阶段清单（目录名见 path_config.STAGE_DIR_NAMES；桌面结构按任务组织）
CANONICAL_STAGES: tuple[str, ...] = (
    "intake",
    "brief",
    "draft",
    "transwrite",
    "publish",
    "postmortem",
)

FORBIDDEN_RUNTIME_OUTPUT_ROOTS: tuple[Path, ...] = (
    ROOT,
    ROOT / "skills",
    ROOT / "openclaw-skill-exports",
)

CANONICAL_MANIFEST_FILENAMES: dict[str, str] = {
    "intake": "intake_manifest.json",
    "brief": "brief_manifest.json",
    "draft": "draft_manifest.json",
    "transwrite": "transwrite_manifest.json",
    "publish": "publish_manifest.json",
    "postmortem": "postmortem_manifest.json",
}

APPROVED_GATE_STATUSES = {
    "approved",
    "accepted",
    "confirmed",
    "ready",
    "locked",
    "finalized",
    "completed",
    "done",
}


class WorkflowContractError(RuntimeError):
    pass


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def ensure_json_file(path: Path, label: str) -> dict[str, Any]:
    candidate = path.expanduser().resolve()
    if not candidate.exists():
        raise WorkflowContractError(f"缺少 {label}：{candidate}")
    payload = read_json(candidate)
    if not isinstance(payload, dict):
        raise WorkflowContractError(f"{label} 格式无效：{candidate}")
    return payload


def infer_run_id_from_payload(payload: dict[str, Any], fallback: str | None = None) -> str:
    run_id = str(payload.get("run_id") or fallback or "").strip()
    if not run_id:
        raise WorkflowContractError("无法推断 run_id")
    return run_id


def ensure_stage_manifest(path: Path, expected_stage: str) -> dict[str, Any]:
    payload = ensure_json_file(path, f"{expected_stage}_manifest.json")
    stage = str(payload.get("stage") or "").strip()
    if stage != expected_stage:
        raise WorkflowContractError(f"阶段清单不匹配：期望 `{expected_stage}`，实际 `{stage or 'unknown'}`，文件：{path}")
    infer_run_id_from_payload(payload)
    return payload


def canonical_stage_dir(stage: str, run_id: str) -> Path:
    if stage not in CANONICAL_STAGES:
        raise WorkflowContractError(f"未知 stage：{stage}")
    return get_stage_dir(stage, run_id)


def ensure_runtime_output_dir(path: Path, *, label: str = "output_dir") -> Path:
    candidate = path.expanduser().resolve()
    for forbidden in FORBIDDEN_RUNTIME_OUTPUT_ROOTS:
        forbidden_resolved = forbidden.resolve()
        if candidate == forbidden_resolved or forbidden_resolved in candidate.parents:
            raise WorkflowContractError(
                f"{label} 不能位于项目仓库、skill 或 export 目录下：{candidate}。运行产物必须写入桌面创作目录或用户显式指定的外部工作目录。"
            )
    return candidate


def canonical_manifest_path(stage: str, run_id: str) -> Path:
    return canonical_stage_dir(stage, run_id) / CANONICAL_MANIFEST_FILENAMES[stage]


def optional_asset_dir(asset: str, run_id: str) -> Path:
    if asset not in OPTIONAL_ASSET_ROOTS:
        raise WorkflowContractError(f"未知 optional asset：{asset}")
    return OPTIONAL_ASSET_ROOTS[asset] / run_id


def _normalized_status(payload: dict[str, Any]) -> str:
    return str(payload.get("status") or "").strip().lower()


def ensure_gate_payload(
    path: Path,
    gate_name: str,
    *,
    required_key: str | None = None,
    require_nonempty: bool = False,
    allow_pending: bool = False,
) -> dict[str, Any]:
    payload = ensure_json_file(path, gate_name)
    status = _normalized_status(payload)
    if status:
        if not allow_pending and status.startswith("pending"):
            raise WorkflowContractError(f"{gate_name} 未通过：{path}")
        if not allow_pending and status not in APPROVED_GATE_STATUSES:
            raise WorkflowContractError(f"{gate_name} 状态无效：{status}（{path}）")
    if required_key is not None:
        value = payload.get(required_key)
        if value is None:
            raise WorkflowContractError(f"{gate_name} 缺少字段 `{required_key}`：{path}")
        if require_nonempty and not value:
            raise WorkflowContractError(f"{gate_name} 字段 `{required_key}` 为空：{path}")
    return payload


def ensure_selected_topics_gate(path: Path) -> dict[str, Any]:
    return ensure_gate_payload(
        path,
        "Brief Gate",
        required_key="selected_topics",
        require_nonempty=True,
        allow_pending=False,
    )


def ensure_final_structure_gate(path: Path) -> dict[str, Any]:
    return ensure_gate_payload(
        path,
        "Final Structure Gate",
        required_key="topics",
        require_nonempty=True,
        allow_pending=False,
    )


def ensure_publish_decision_gate(path: Path) -> dict[str, Any]:
    return ensure_gate_payload(
        path,
        "Channel Gate",
        required_key="topics",
        require_nonempty=True,
        allow_pending=False,
    )


def ensure_transwrite_decision_gate(path: Path) -> dict[str, Any]:
    return ensure_gate_payload(
        path,
        "Transwrite Gate",
        required_key="topics",
        require_nonempty=True,
        allow_pending=False,
    )


def pending_gate_payload(
    *,
    run_id: str,
    gate_name: str,
    topic_rows: list[dict[str, Any]],
    instructions: list[str],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "gate": gate_name,
        "status": "pending_editor_review",
        "topics": topic_rows,
        "instructions": instructions,
    }


def ensure_pending_gate_file(
    path: Path,
    *,
    run_id: str,
    gate_name: str,
    topic_rows: list[dict[str, Any]],
    instructions: list[str],
) -> Path:
    candidate = path.expanduser().resolve()
    if not candidate.exists():
        write_json(
            candidate,
            pending_gate_payload(
                run_id=run_id,
                gate_name=gate_name,
                topic_rows=topic_rows,
                instructions=instructions,
            ),
        )
    return candidate


def stage_contract_snapshot(run_id: str) -> dict[str, Any]:
    contract: dict[str, Any] = {"run_id": run_id, "stages": {}}
    gate_map = {
        "intake": "intake_review.json",
        "brief": "selected_topics.json",
        "draft": "final_structure_snapshot.json",
        "transwrite": "transwrite_decision.json",
        "publish": "publish_decision.json",
    }
    for stage in CANONICAL_STAGES:
        stage_dir = canonical_stage_dir(stage, run_id)
        manifest_path = stage_dir / CANONICAL_MANIFEST_FILENAMES[stage]
        gate_path = stage_dir / gate_map[stage] if stage in gate_map else None
        contract["stages"][stage] = {
            "stage_dir": str(stage_dir),
            "manifest_path": str(manifest_path),
            "manifest_exists": manifest_path.exists(),
            "gate_path": str(gate_path) if gate_path else None,
            "gate_exists": gate_path.exists() if gate_path else None,
        }
    return contract
