from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from vibe_visualization_api.creator_studio.adapter import CreatorControlAdapter
from vibe_visualization_api.creator_studio.repository import CreatorRunRepository


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class EditorSessionError(Exception):
    """Raised when an editor action is invalid for the current session."""


class EditorSessionRuntime:
    """Lifecycle Module for whitelisted local and embedded editor sessions."""

    def __init__(
        self,
        repository: CreatorRunRepository,
        control_adapter: CreatorControlAdapter,
    ):
        self.repository = repository
        self.control_adapter = control_adapter

    def create_from_execution(
        self,
        *,
        job: dict[str, Any],
        execution: dict[str, Any],
    ) -> dict[str, Any] | None:
        result = execution.get("result")
        if not isinstance(result, dict) or result.get("kind") != "editor_session":
            return None
        descriptor = result.get("editor_session")
        if not isinstance(descriptor, dict):
            return None
        timestamp = str(descriptor.get("created_at") or now_iso())
        editors = []
        for item in descriptor.get("editors", []):
            if not isinstance(item, dict) or not item.get("id"):
                continue
            editors.append(
                {
                    "id": str(item["id"]),
                    "name": item.get("name") or item["id"],
                    "kind": item.get("kind") or "unavailable",
                    "status": item.get("status") or "unavailable",
                    "launchUrl": item.get("launch_url"),
                    "artifactPath": item.get("artifact_path"),
                    "projectPath": item.get("project_path"),
                    "alreadyRunning": bool(item.get("already_running")),
                    "missing": item.get("missing", []),
                    "reason": item.get("reason"),
                }
            )
        session = {
            "schemaVersion": "newma.editor-session.v1",
            "sessionId": str(
                descriptor.get("session_id") or f"editor-{job['jobId']}"
            ),
            "userId": str(job["userId"]),
            "workspaceId": str(job["workspaceId"]),
            "runId": str(job["runId"]),
            "stageId": str(job["stageId"]),
            "nodeId": str(job["nodeId"]),
            "producerJobId": str(job["jobId"]),
            "status": str(descriptor.get("status") or "ready"),
            "editors": editors,
            "selectedEditorId": None,
            "inputArtifacts": deepcopy(descriptor.get("input_artifacts", [])),
            "outputContract": [
                str(item) for item in descriptor.get("output_contract", [])
            ],
            "outputArtifacts": [],
            "launch": None,
            "createdAt": timestamp,
            "updatedAt": timestamp,
        }
        return self.repository.create_editor_session(session)

    def launch(
        self,
        *,
        user_id: str,
        workspace_id: str,
        session_id: str,
        editor_id: str,
    ) -> dict[str, Any]:
        session = self.repository.get_editor_session(
            user_id=user_id,
            workspace_id=workspace_id,
            session_id=session_id,
        )
        editor = next(
            (item for item in session.get("editors", []) if item.get("id") == editor_id),
            None,
        )
        if editor is None:
            raise EditorSessionError(f"editor is not available in session: {editor_id}")
        if editor.get("status") not in {"available", "open"}:
            raise EditorSessionError(
                str(editor.get("reason") or "editor is unavailable")
            )
        launch = self.control_adapter.launch_editor(
            {
                "schema_version": "newma.editor_launch_request.v1",
                "session_id": session_id,
                "run_id": session["runId"],
                "stage_id": session["stageId"],
                "node_id": session["nodeId"],
                "editor_id": editor_id,
                "artifact_path": editor.get("artifactPath"),
            }
        )
        timestamp = now_iso()
        session["selectedEditorId"] = editor_id
        session["launch"] = {
            "status": launch.get("status"),
            "editorId": editor_id,
            "kind": launch.get("kind"),
            "launchUrl": launch.get("launch_url"),
            "artifactPath": launch.get("artifact_path"),
            "pid": launch.get("pid"),
            "logPath": launch.get("log_path"),
            "error": launch.get("error"),
        }
        session["status"] = "open" if launch.get("status") == "open" else "blocked"
        session["lastHeartbeatAt"] = timestamp if session["status"] == "open" else None
        session["updatedAt"] = timestamp
        return self.repository.update_editor_session(session)

    def save(
        self,
        *,
        user_id: str,
        workspace_id: str,
        session_id: str,
        outputs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        session = self.repository.get_editor_session(
            user_id=user_id,
            workspace_id=workspace_id,
            session_id=session_id,
        )
        if not outputs:
            raise EditorSessionError("at least one editor output is required")
        timestamp = now_iso()
        session["outputArtifacts"] = deepcopy(outputs)
        session["status"] = "saved"
        session["savedAt"] = timestamp
        session["updatedAt"] = timestamp
        return self.repository.update_editor_session(session)

    def close(
        self,
        *,
        user_id: str,
        workspace_id: str,
        session_id: str,
    ) -> dict[str, Any]:
        session = self.repository.get_editor_session(
            user_id=user_id,
            workspace_id=workspace_id,
            session_id=session_id,
        )
        timestamp = now_iso()
        session["status"] = "closed"
        session["closedAt"] = timestamp
        session["updatedAt"] = timestamp
        return self.repository.update_editor_session(session)
