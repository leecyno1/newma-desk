from __future__ import annotations

import re
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

from vibe_visualization_api.creator_studio.adapter import CreatorControlAdapter
from vibe_visualization_api.creator_studio.repository import CreatorRunRepository


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class EditorSessionError(Exception):
    """Raised when an editor action is invalid for the current session."""


EXTERNAL_PROJECT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,160}$")
COLLABORATION_REVIEW_TIMEOUT_SECONDS = 30 * 60


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
                    "projectCandidates": item.get("project_candidates", []),
                    "alreadyRunning": bool(item.get("already_running")),
                    "embedMode": item.get("embed_mode") or "new_window",
                    "agentBridge": deepcopy(item.get("agent_bridge")),
                    "sessionProtocol": deepcopy(item.get("session_protocol")),
                    "templateCatalogs": deepcopy(item.get("template_catalogs", [])),
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
            "collaboration": None,
            "savedTemplates": [],
            "launch": None,
            "createdAt": timestamp,
            "updatedAt": timestamp,
        }
        return self.repository.create_editor_session(session)

    @staticmethod
    def _editor(session: dict[str, Any], editor_id: str) -> dict[str, Any]:
        editor = next(
            (item for item in session.get("editors", []) if item.get("id") == editor_id),
            None,
        )
        if editor is None:
            raise EditorSessionError(f"editor is not available in session: {editor_id}")
        return editor

    @staticmethod
    def _project_url(editor: dict[str, Any], project_id: str) -> str | None:
        launch_url = str(editor.get("launchUrl") or "").strip()
        if not launch_url:
            return None
        base_url = launch_url.split("#", 1)[0].rstrip("/")
        return f"{base_url}/#/editor/{quote(project_id, safe='')}"

    def _bind_project_document(
        self,
        session: dict[str, Any],
        *,
        editor_id: str,
        project_id: str,
        source: str,
    ) -> None:
        if editor_id != "openchatcut":
            raise EditorSessionError("external project binding currently requires OpenChatCut")
        if not EXTERNAL_PROJECT_ID_PATTERN.fullmatch(project_id):
            raise EditorSessionError("OpenChatCut project id is invalid")
        editor = self._editor(session, editor_id)
        timestamp = now_iso()
        binding = {
            "editorId": editor_id,
            "projectId": project_id,
            "editorUrl": self._project_url(editor, project_id),
            "source": source,
            "boundAt": (
                (session.get("externalProject") or {}).get("boundAt")
                or timestamp
            ),
            "updatedAt": timestamp,
        }
        session["externalProject"] = binding
        launch = session.get("launch")
        if isinstance(launch, dict) and launch.get("editorId") == editor_id:
            launch["launchUrl"] = binding["editorUrl"] or launch.get("launchUrl")

    def bind_project(
        self,
        *,
        user_id: str,
        workspace_id: str,
        session_id: str,
        editor_id: str,
        project_id: str,
        source: str,
    ) -> dict[str, Any]:
        session = self.repository.get_editor_session(
            user_id=user_id,
            workspace_id=workspace_id,
            session_id=session_id,
        )
        self._bind_project_document(
            session,
            editor_id=editor_id,
            project_id=project_id,
            source=source,
        )
        session["updatedAt"] = now_iso()
        return self.repository.update_editor_session(session)

    def launch(
        self,
        *,
        user_id: str,
        workspace_id: str,
        session_id: str,
        editor_id: str,
        external_project_id: str = "",
    ) -> dict[str, Any]:
        session = self.repository.get_editor_session(
            user_id=user_id,
            workspace_id=workspace_id,
            session_id=session_id,
        )
        editor = self._editor(session, editor_id)
        if editor.get("status") not in {"available", "open"}:
            raise EditorSessionError(
                str(editor.get("reason") or "editor is unavailable")
            )
        if external_project_id:
            self._bind_project_document(
                session,
                editor_id=editor_id,
                project_id=external_project_id,
                source="user",
            )
        project_id = str(
            (session.get("externalProject") or {}).get("projectId") or ""
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
                "external_project_id": project_id,
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
            "projectPath": launch.get("project_path"),
            "embedMode": launch.get("embed_mode"),
            "agentBridge": deepcopy(launch.get("agent_bridge")),
            "sessionProtocol": deepcopy(launch.get("session_protocol")),
            "pid": launch.get("pid"),
            "logPath": launch.get("log_path"),
            "error": launch.get("error"),
        }
        if project_id:
            session["launch"]["launchUrl"] = (
                (session.get("externalProject") or {}).get("editorUrl")
                or session["launch"].get("launchUrl")
            )
        session["status"] = "open" if launch.get("status") == "open" else "blocked"
        session["lastHeartbeatAt"] = timestamp if session["status"] == "open" else None
        session["updatedAt"] = timestamp
        return self.repository.update_editor_session(session)

    def start_agent(
        self,
        *,
        user_id: str,
        workspace_id: str,
        session_id: str,
        editor_id: str,
        approval_mode: str,
        prompt: str,
        external_project_id: str = "",
    ) -> dict[str, Any]:
        session = self.repository.get_editor_session(
            user_id=user_id,
            workspace_id=workspace_id,
            session_id=session_id,
        )
        editor = self._editor(session, editor_id)
        bridge = editor.get("agentBridge")
        if not isinstance(bridge, dict) or not bridge.get("endpoint"):
            raise EditorSessionError("selected editor does not expose an Agent bridge")
        supported_modes = bridge.get("approval_modes") or ["manual"]
        if approval_mode not in supported_modes:
            raise EditorSessionError(f"unsupported approval mode: {approval_mode}")
        if external_project_id:
            self._bind_project_document(
                session,
                editor_id=editor_id,
                project_id=external_project_id,
                source="user",
            )
        timestamp = now_iso()
        session["selectedEditorId"] = editor_id
        session["collaboration"] = {
            "protocol": bridge.get("protocol") or "external-editor.v1",
            "bridgeKind": bridge.get("kind") or "mcp",
            "endpoint": bridge["endpoint"],
            "approvalMode": approval_mode,
            "status": "drafting",
            "prompt": prompt,
            "externalProjectId": (
                (session.get("externalProject") or {}).get("projectId")
            ),
            "externalEditSessionId": None,
            "proposal": None,
            "reviewTimeoutSeconds": COLLABORATION_REVIEW_TIMEOUT_SECONDS,
            "reviewDeadlineAt": None,
            "startedAt": timestamp,
            "updatedAt": timestamp,
        }
        session["status"] = "agent_editing"
        session["updatedAt"] = timestamp
        return self.repository.update_editor_session(session)

    def submit_proposal(
        self,
        *,
        user_id: str,
        workspace_id: str,
        session_id: str,
        external_edit_session_id: str,
        summary: str,
        change_count: int | None,
        external_project_id: str = "",
    ) -> dict[str, Any]:
        session = self.repository.get_editor_session(
            user_id=user_id,
            workspace_id=workspace_id,
            session_id=session_id,
        )
        collaboration = session.get("collaboration")
        if not isinstance(collaboration, dict):
            raise EditorSessionError("Agent collaboration has not started")
        timestamp = now_iso()
        if external_project_id:
            self._bind_project_document(
                session,
                editor_id=str(session.get("selectedEditorId") or "openchatcut"),
                project_id=external_project_id,
                source="agent",
            )
            collaboration["externalProjectId"] = external_project_id
        collaboration["externalEditSessionId"] = external_edit_session_id
        collaboration["status"] = "awaiting_review"
        collaboration["reviewDeadlineAt"] = (
            datetime.now(UTC) + timedelta(seconds=COLLABORATION_REVIEW_TIMEOUT_SECONDS)
        ).isoformat()
        collaboration["proposal"] = {
            "status": "awaiting_review",
            "summary": summary,
            "changeCount": change_count,
            "submittedAt": timestamp,
        }
        collaboration["updatedAt"] = timestamp
        session["status"] = "waiting_review"
        session["updatedAt"] = timestamp
        return self.repository.update_editor_session(session)

    def review_proposal(
        self,
        *,
        user_id: str,
        workspace_id: str,
        session_id: str,
        decision: str,
        note: str,
        external_edit_session_id: str = "",
        summary: str = "",
        change_count: int | None = None,
        external_project_id: str = "",
    ) -> dict[str, Any]:
        if decision not in {"applied", "rejected", "discarded"}:
            raise EditorSessionError("proposal decision must be applied, rejected or discarded")
        session = self.repository.get_editor_session(
            user_id=user_id,
            workspace_id=workspace_id,
            session_id=session_id,
        )
        collaboration = session.get("collaboration")
        if not isinstance(collaboration, dict):
            raise EditorSessionError("Agent collaboration has not started")
        proposal = collaboration.get("proposal")
        timestamp = now_iso()
        if external_project_id:
            self._bind_project_document(
                session,
                editor_id=str(session.get("selectedEditorId") or "openchatcut"),
                project_id=external_project_id,
                source="agent",
            )
            collaboration["externalProjectId"] = external_project_id
        if not isinstance(proposal, dict):
            if not external_edit_session_id:
                raise EditorSessionError("current session has no proposal to review")
            collaboration["externalEditSessionId"] = external_edit_session_id
            proposal = {
                "status": "awaiting_review",
                "summary": summary,
                "changeCount": change_count,
                "submittedAt": timestamp,
            }
            collaboration["proposal"] = proposal
        elif external_edit_session_id:
            collaboration["externalEditSessionId"] = external_edit_session_id
            if summary:
                proposal["summary"] = summary
            if change_count is not None:
                proposal["changeCount"] = change_count
        proposal.update({"status": decision, "reviewNote": note, "reviewedAt": timestamp})
        collaboration["status"] = decision
        collaboration["updatedAt"] = timestamp
        session["status"] = "open" if decision in {"applied", "rejected"} else "closed"
        session["updatedAt"] = timestamp
        return self.repository.update_editor_session(session)

    def import_export(
        self,
        *,
        user_id: str,
        workspace_id: str,
        session_id: str,
        external_project_id: str,
        download_url: str,
        render_id: str,
        name: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        session = self.repository.get_editor_session(
            user_id=user_id,
            workspace_id=workspace_id,
            session_id=session_id,
        )
        if session.get("selectedEditorId") != "openchatcut":
            raise EditorSessionError("editor export import currently requires OpenChatCut")
        collaboration = session.get("collaboration")
        proposal = (
            collaboration.get("proposal")
            if isinstance(collaboration, dict)
            else None
        )
        if isinstance(proposal, dict) and proposal.get("status") not in {
            "applied",
            "rejected",
        }:
            raise EditorSessionError("apply or reject the current proposal before importing an export")
        self._bind_project_document(
            session,
            editor_id="openchatcut",
            project_id=external_project_id,
            source="agent" if isinstance(collaboration, dict) else "user",
        )
        session["updatedAt"] = now_iso()
        self.repository.update_editor_session(session)
        result = self.control_adapter.import_editor_export(
            {
                "schema_version": "newma.editor_export_import_request.v1",
                "session_id": session_id,
                "run_id": session["runId"],
                "stage_id": session["stageId"],
                "node_id": session["nodeId"],
                "editor_id": "openchatcut",
                "external_project_id": external_project_id,
                "external_edit_session_id": (
                    collaboration.get("externalEditSessionId")
                    if isinstance(collaboration, dict)
                    else None
                ),
                "proposal": deepcopy(proposal),
                "download_url": download_url,
                "render_id": render_id,
                "name": name,
            }
        )
        outputs = result.get("outputs")
        if not isinstance(outputs, list) or not outputs:
            raise EditorSessionError("OpenChatCut export import returned no artifacts")
        return (
            self.save(
                user_id=user_id,
                workspace_id=workspace_id,
                session_id=session_id,
                outputs=[item for item in outputs if isinstance(item, dict)],
            ),
            result,
        )

    def save_template(
        self,
        *,
        user_id: str,
        workspace_id: str,
        session_id: str,
        template_id: str,
        name: str,
        mode: str,
        source_action: str,
    ) -> dict[str, Any]:
        session = self.repository.get_editor_session(
            user_id=user_id,
            workspace_id=workspace_id,
            session_id=session_id,
        )
        timestamp = now_iso()
        template = {
            "templateId": template_id,
            "name": name,
            "mode": mode,
            "editorId": session.get("selectedEditorId"),
            "sourceAction": source_action,
            "sourceStatus": "confirmed",
            "savedAt": timestamp,
        }
        session["savedTemplates"] = [
            item
            for item in session.setdefault("savedTemplates", [])
            if item.get("templateId") != template_id
        ]
        session["savedTemplates"].append(template)
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
