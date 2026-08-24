from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from vibe_visualization_api.creator_studio.adapter import CreatorControlAdapter
from vibe_visualization_api.creator_studio.editor_sessions import (
    EditorSessionError,
    EditorSessionRuntime,
)
from vibe_visualization_api.creator_studio.execution import CreatorExecutionRuntime
from vibe_visualization_api.creator_studio.lineage import ArtifactLineage
from vibe_visualization_api.creator_studio.models import (
    CreatorCommand,
    CreatorMaterialInput,
    CreatorRunCreate,
    MarketplaceCompatibilityRequest,
    MarketplacePresetCreate,
    MarketplacePresetUpdate,
)
from vibe_visualization_api.creator_studio.products import CreatorProductCatalog
from vibe_visualization_api.creator_studio.registry import (
    CreatorMaterialError,
    CreatorRegistry,
)
from vibe_visualization_api.creator_studio.repository import (
    CreatorRunConflictError,
    CreatorRunRepository,
)


FINAL_NODE_STATUSES = {"succeeded", "skipped", "cancelled"}
RUNNABLE_NODE_STATUSES = {"pending", "stale"}
RETRYABLE_NODE_STATUSES = {
    "failed",
    "blocked",
    "changes_requested",
    "cancelled",
}
USABLE_ARTIFACT_STATUSES = {"created", "approved", "succeeded"}
SESSION_EXECUTOR_IDS = {
    "newma.control.editor-session",
    "newma.control.capability-session",
}
ATTENTION_NODE_STATUSES = {
    "waiting_user",
    "changes_requested",
    "blocked",
    "failed",
    "stale",
}
PUBLISH_EXECUTOR_PHASES = {
    "newma.publish.preflight": "preflight",
    "newma.publish.execute": "execution",
    "newma.publish.verify": "verification",
}
COMMANDS = {
    "creator.node.run",
    "creator.node.retry",
    "creator.node.rerun",
    "creator.node.complete",
    "creator.node.skip",
    "creator.node.cancel",
    "creator.editor.launch",
    "creator.editor.start-agent",
    "creator.editor.submit-proposal",
    "creator.editor.review-proposal",
    "creator.editor.import-export",
    "creator.editor.save-template",
    "creator.editor.save",
    "creator.editor.close",
    "creator.publish.confirm",
    "creator.node.configure",
    "creator.node.submit-feedback",
    "creator.node.approve",
    "creator.node.request-changes",
    "creator.material.attach",
    "creator.artifact.register",
    "creator.handoff.create",
    "creator.workflow.continue",
    "creator.marketplace.apply-preset",
}


class CreatorCommandError(Exception):
    """Raised when a Creator Studio command is invalid for the current run."""


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def node_key(stage_id: str, node_id: str) -> str:
    return f"{stage_id}.{node_id}"


class CreatorStudioService:
    """Deep Module shared by visual controls and Desk Agent UI actions."""

    def __init__(self, database_path: Path, creator_workspace: Path):
        self.registry = CreatorRegistry(creator_workspace)
        self.repository = CreatorRunRepository(database_path)
        self.control_adapter = CreatorControlAdapter(creator_workspace)
        self.lineage = ArtifactLineage()
        self.products = CreatorProductCatalog()
        self.editor_sessions = EditorSessionRuntime(
            self.repository,
            self.control_adapter,
        )
        self.execution_runtime = CreatorExecutionRuntime(
            self.repository,
            self.control_adapter,
            on_started=self._execution_started,
            on_finished=self._execution_finished,
        )

    def startup(self) -> None:
        self.execution_runtime.startup()

    def shutdown(self) -> None:
        self.execution_runtime.shutdown()

    def registry_document(self) -> dict[str, Any]:
        return self.registry.load()

    def system_info(self) -> dict[str, Any]:
        registry = self.registry.load()
        return {
            "schemaVersion": "newma.creator-studio-system.v1",
            "workspace": str(self.registry.workspace),
            "registryPath": str(self.registry.path),
            "product": registry.get("product", {}),
            "navigation": registry.get("navigation", {}),
            "stageCount": len(registry.get("stages", [])),
        }

    def list_runs(self, *, user_id: str, workspace_id: str) -> dict[str, Any]:
        documents = self.repository.list_runs(
            user_id=user_id,
            workspace_id=workspace_id,
        )
        return {
            "schemaVersion": "newma.creator-studio-run-list.v1",
            "runs": [self._summary(document) for document in documents],
        }

    @staticmethod
    def _summary(document: dict[str, Any]) -> dict[str, Any]:
        return {
            "runId": document["runId"],
            "title": document["title"],
            "status": document["status"],
            "activeStageId": document.get("activeStageId"),
            "activeNodeId": document.get("activeNodeId"),
            "revision": document["revision"],
            "updatedAt": document["updatedAt"],
        }

    def create_run(
        self,
        *,
        user_id: str,
        workspace_id: str,
        request: CreatorRunCreate,
    ) -> dict[str, Any]:
        registry = self.registry.load()
        self.registry.node(registry, request.stage_id, request.node_id)
        material_report = self.registry.validate_materials(
            registry,
            request.stage_id,
            request.node_id,
            request.materials,
            project_start=True,
        )
        if material_report["status"] != "ready":
            raise CreatorMaterialError(material_report)

        selected_stage = self.registry.stage(registry, request.stage_id)
        selected_stage_order = int(selected_stage.get("order", 0))
        selected_node_ids = [str(item["id"]) for item in selected_stage.get("nodes", [])]
        selected_node_order = selected_node_ids.index(request.node_id)
        states: dict[str, dict[str, Any]] = {}
        for stage in registry.get("stages", []):
            stage_order = int(stage.get("order", 0))
            for node_index, node in enumerate(stage.get("nodes", [])):
                status = "pending"
                if stage_order < selected_stage_order or (
                    stage_order == selected_stage_order and node_index < selected_node_order
                ):
                    status = "skipped"
                states[node_key(str(stage["id"]), str(node["id"]))] = {
                    "status": status,
                    "progress": 100 if status == "skipped" else 0,
                    "materials": [],
                    "artifacts": [],
                    "feedback": [],
                    "logs": [],
                    "parameters": {},
                    "attempt": 0,
                    "updatedAt": now_iso(),
                }
        target = states[node_key(request.stage_id, request.node_id)]
        target["allowManualBootstrap"] = True
        target["materials"] = [
            item.model_dump(by_alias=True) for item in request.materials
        ]
        target["logs"].append(
            {"at": now_iso(), "message": "项目已从当前节点创建，素材校验通过。"}
        )
        timestamp = now_iso()
        document = {
            "schemaVersion": "newma.creator-studio-run.v1",
            "runId": f"creator-{uuid4().hex[:12]}",
            "title": request.title,
            "status": "pending",
            "activeStageId": request.stage_id,
            "activeNodeId": request.node_id,
            "nodeStates": states,
            "handoffs": [],
            "events": [],
            "revision": 1,
            "createdAt": timestamp,
            "updatedAt": timestamp,
        }
        event = self._event(
            "run.created",
            action_id="creator.run.create",
            stage_id=request.stage_id,
            node_id=request.node_id,
            payload={"title": request.title},
        )
        stored = self.repository.create_run(
            user_id=user_id,
            workspace_id=workspace_id,
            document=document,
            event=event,
        )
        return self.snapshot(stored, registry)

    def get_snapshot(
        self,
        *,
        user_id: str,
        workspace_id: str,
        run_id: str,
    ) -> dict[str, Any]:
        return self.snapshot(
            self.repository.get_run(
                user_id=user_id,
                workspace_id=workspace_id,
                run_id=run_id,
            ),
            self.registry.load(),
        )

    def execute_command(
        self,
        *,
        user_id: str,
        workspace_id: str,
        run_id: str,
        command: CreatorCommand,
    ) -> dict[str, Any]:
        if command.action_id not in COMMANDS:
            raise CreatorCommandError(f"unsupported Creator command: {command.action_id}")
        registry = self.registry.load()
        current = self.repository.get_run(
            user_id=user_id,
            workspace_id=workspace_id,
            run_id=run_id,
        )
        if (
            command.expected_revision is not None
            and command.expected_revision != int(current["revision"])
        ):
            raise CreatorRunConflictError(run_id)
        document = deepcopy(current)
        stage_id = command.stage_id or str(document.get("activeStageId") or "")
        node_id = command.node_id or str(document.get("activeNodeId") or "")
        node_definition = self.registry.node(registry, stage_id, node_id)
        state = self._node_state(document, stage_id, node_id)
        material_report = self.registry.validate_materials(
            registry,
            stage_id,
            node_id,
            state.get("materials", []),
            project_start=bool(state.get("allowManualBootstrap")),
        )
        if (
            command.action_id
            in {
                "creator.node.run",
                "creator.node.retry",
                "creator.node.rerun",
                "creator.node.approve",
            }
            and material_report["status"] != "ready"
        ):
            raise CreatorMaterialError(material_report)
        available_actions = self._available_actions(
            node_definition,
            state,
            material_report,
        )
        if command.action_id not in available_actions:
            raise CreatorCommandError(
                f"{command.action_id} is unavailable for {stage_id}/{node_id} "
                f"while status is {state.get('status', 'pending')}"
            )
        payload: dict[str, Any] = {}
        queued_job: dict[str, Any] | None = None
        cancel_job_id: str | None = None

        if command.action_id in {"creator.node.run", "creator.node.retry"}:
            executor_id = str(node_definition.get("executor") or "").strip()
            if not executor_id:
                raise CreatorCommandError(
                    f"{stage_id}/{node_id} has no registered executor"
                )
            execution_adapter = next(
                (
                    item
                    for item in registry.get("execution_adapters", [])
                    if item.get("id") == executor_id
                ),
                {},
            )
            if executor_id == "newma.publish.execute":
                confirmation = (state.get("parameters") or {}).get(
                    "publishConfirmation"
                )
                if (
                    not isinstance(confirmation, dict)
                    or confirmation.get("confirmed") is not True
                    or confirmation.get("consumedByJobId")
                ):
                    raise CreatorCommandError(
                        "publish execution requires a fresh explicit confirmation"
                    )
            # Merge agent CLI selection from command.input into state parameters
            agent_cli = str(command.input.get("agent_cli") or "").strip()
            agent_cli_bin = str(command.input.get("agent_cli_bin") or "").strip()
            if agent_cli or agent_cli_bin:
                merged_params = dict(state.get("parameters") or {})
                if agent_cli:
                    merged_params["agent_cli"] = agent_cli
                if agent_cli_bin:
                    merged_params["agent_cli_bin"] = agent_cli_bin
                state["parameters"] = merged_params
            state["attempt"] = int(state.get("attempt") or 0) + 1
            requested_at = now_iso()
            job_id = f"job-{uuid4().hex[:12]}"
            state["status"] = "queued"
            state["progress"] = 0
            state["executionRequest"] = {
                "jobId": job_id,
                "status": "queued",
                "executorId": executor_id,
                "capabilities": node_definition.get("capabilities", []),
                "requestedAt": requested_at,
            }
            if executor_id == "newma.publish.execute":
                confirmation = deepcopy(
                    state["parameters"]["publishConfirmation"]
                )
                confirmation["consumedByJobId"] = job_id
                confirmation["consumedAt"] = requested_at
                state["parameters"]["publishConfirmation"] = confirmation
                publish_state = document.setdefault(
                    "publishState",
                    {"schemaVersion": "newma.creator-publish-state.v1"},
                )
                publish_state["confirmation"] = deepcopy(confirmation)
                publish_state["updatedAt"] = requested_at
            state.pop("executionResult", None)
            self._append_log(state, "节点已进入执行队列。")
            document["status"] = "queued"
            request_payload = {
                "schema_version": "newma.creator_node_request.v1",
                "job_id": job_id,
                "run_id": run_id,
                "title": document["title"],
                "stage_id": stage_id,
                "node_id": node_id,
                "action_id": command.action_id,
                "attempt": state["attempt"],
                "timeout_seconds": int(
                    execution_adapter.get("timeout_seconds") or 3600
                ),
                "materials": deepcopy(state.get("materials", [])),
                "parameters": deepcopy(state.get("parameters", {})),
            }
            queued_job = {
                "schemaVersion": "newma.creator-execution-job.v1",
                "jobId": job_id,
                "userId": user_id,
                "workspaceId": workspace_id,
                "runId": run_id,
                "stageId": stage_id,
                "nodeId": node_id,
                "executorId": executor_id,
                "status": "queued",
                "progress": 0,
                "cancelRequested": False,
                "request": request_payload,
                "result": None,
                "error": None,
                "createdAt": requested_at,
                "updatedAt": requested_at,
            }
            payload = {
                "attempt": state["attempt"],
                "jobId": job_id,
                "executorId": executor_id,
                "status": "queued",
            }
        elif command.action_id == "creator.node.cancel":
            execution_request = state.get("executionRequest") or {}
            cancel_job_id = str(execution_request.get("jobId") or "").strip()
            if not cancel_job_id:
                raise CreatorCommandError("current node has no active execution job")
            requested_at = now_iso()
            state["executionRequest"] = {
                **execution_request,
                "cancelRequestedAt": requested_at,
            }
            self._append_log(state, "已请求取消当前节点执行。")
            payload = {"jobId": cancel_job_id, "status": "cancel_requested"}
        elif command.action_id == "creator.editor.launch":
            session_ref = state.get("editorSession") or {}
            session_id = str(
                command.input.get("sessionId")
                or session_ref.get("sessionId")
                or ""
            ).strip()
            editor_id = str(command.input.get("editorId") or "").strip()
            if not session_id or not editor_id:
                raise CreatorCommandError("sessionId and editorId are required")
            session = self.editor_sessions.launch(
                user_id=user_id,
                workspace_id=workspace_id,
                session_id=session_id,
                editor_id=editor_id,
                external_project_id=str(
                    command.input.get("externalProjectId") or ""
                ).strip(),
            )
            state["editorSession"] = self._editor_session_summary(session)
            self._append_log(
                state,
                f"已打开人工编辑器：{editor_id}。",
            )
            payload = {
                "sessionId": session_id,
                "editorId": editor_id,
                "status": session["status"],
                "launch": session.get("launch"),
                "externalProject": session.get("externalProject"),
            }
        elif command.action_id == "creator.editor.start-agent":
            session_ref = state.get("editorSession") or {}
            session_id = str(
                command.input.get("sessionId")
                or session_ref.get("sessionId")
                or ""
            ).strip()
            editor_id = str(
                command.input.get("editorId")
                or session_ref.get("selectedEditorId")
                or ""
            ).strip()
            if not session_id or not editor_id:
                raise CreatorCommandError("sessionId and editorId are required")
            if (
                session_ref.get("status") not in {"open", "agent_editing", "waiting_review"}
                or session_ref.get("selectedEditorId") != editor_id
            ):
                launched = self.editor_sessions.launch(
                    user_id=user_id,
                    workspace_id=workspace_id,
                    session_id=session_id,
                    editor_id=editor_id,
                    external_project_id=str(
                        command.input.get("externalProjectId") or ""
                    ).strip(),
                )
                if launched.get("status") != "open":
                    raise CreatorCommandError(
                        str((launched.get("launch") or {}).get("error") or "editor launch failed")
                    )
            session = self.editor_sessions.start_agent(
                user_id=user_id,
                workspace_id=workspace_id,
                session_id=session_id,
                editor_id=editor_id,
                approval_mode=str(command.input.get("approvalMode") or "manual"),
                prompt=str(command.input.get("prompt") or "").strip(),
                external_project_id=str(
                    command.input.get("externalProjectId") or ""
                ).strip(),
            )
            state["editorSession"] = self._editor_session_summary(session)
            self._append_log(state, f"已启动 Agent 协同剪辑：{editor_id}。")
            payload = {
                "sessionId": session_id,
                "editorId": editor_id,
                "status": session["status"],
                "collaboration": session.get("collaboration"),
                "externalProject": session.get("externalProject"),
            }
        elif command.action_id == "creator.editor.submit-proposal":
            session_ref = state.get("editorSession") or {}
            session_id = str(command.input.get("sessionId") or session_ref.get("sessionId") or "").strip()
            external_id = str(command.input.get("externalEditSessionId") or "").strip()
            if not session_id or not external_id:
                raise CreatorCommandError("sessionId and externalEditSessionId are required")
            raw_change_count = command.input.get("changeCount")
            change_count = int(raw_change_count) if isinstance(raw_change_count, (int, float)) else None
            session = self.editor_sessions.submit_proposal(
                user_id=user_id,
                workspace_id=workspace_id,
                session_id=session_id,
                external_edit_session_id=external_id,
                summary=str(command.input.get("summary") or "").strip(),
                change_count=change_count,
                external_project_id=str(
                    command.input.get("externalProjectId") or ""
                ).strip(),
            )
            state["editorSession"] = self._editor_session_summary(session)
            self._append_log(state, "Agent 剪辑提案已提交，等待审核。")
            payload = {
                "sessionId": session_id,
                "status": session["status"],
                "proposal": (session.get("collaboration") or {}).get("proposal"),
            }
        elif command.action_id == "creator.editor.review-proposal":
            session_ref = state.get("editorSession") or {}
            session_id = str(command.input.get("sessionId") or session_ref.get("sessionId") or "").strip()
            decision = str(command.input.get("decision") or "").strip()
            if not session_id:
                raise CreatorCommandError("sessionId is required")
            raw_change_count = command.input.get("changeCount")
            change_count = int(raw_change_count) if isinstance(raw_change_count, (int, float)) else None
            session = self.editor_sessions.review_proposal(
                user_id=user_id,
                workspace_id=workspace_id,
                session_id=session_id,
                decision=decision,
                note=str(command.input.get("note") or "").strip(),
                external_edit_session_id=str(
                    command.input.get("externalEditSessionId") or ""
                ).strip(),
                summary=str(command.input.get("summary") or "").strip(),
                change_count=change_count,
                external_project_id=str(
                    command.input.get("externalProjectId") or ""
                ).strip(),
            )
            state["editorSession"] = self._editor_session_summary(session)
            if decision == "applied":
                marketplace_binding = (state.get("parameters") or {}).get(
                    "marketplacePreset"
                )
                if (
                    isinstance(marketplace_binding, dict)
                    and marketplace_binding.get("applicationMode")
                    == "openchatcut_mcp"
                ):
                    marketplace_binding["status"] = "applied_in_editor"
                    marketplace_binding["editorAppliedAt"] = now_iso()
            self._append_log(state, f"Agent 剪辑提案状态已同步：{decision}。")
            payload = {
                "sessionId": session_id,
                "status": session["status"],
                "proposal": (session.get("collaboration") or {}).get("proposal"),
            }
        elif command.action_id == "creator.editor.save-template":
            session_ref = state.get("editorSession") or {}
            session_id = str(command.input.get("sessionId") or session_ref.get("sessionId") or "").strip()
            template_id = str(command.input.get("templateId") or "").strip()
            name = str(command.input.get("name") or "").strip()
            mode = str(command.input.get("mode") or "project").strip()
            source_action = str(command.input.get("sourceAction") or "").strip()
            if not session_id or not template_id or not name or not source_action:
                raise CreatorCommandError(
                    "sessionId, templateId, name and sourceAction are required"
                )
            if mode not in {"project", "selection"}:
                raise CreatorCommandError("template mode must be project or selection")
            if (
                session_ref.get("selectedEditorId") == "openchatcut"
                and source_action != "manage_template.save"
            ):
                raise CreatorCommandError(
                    "OpenChatCut template must come from manage_template.save"
                )
            session = self.editor_sessions.save_template(
                user_id=user_id,
                workspace_id=workspace_id,
                session_id=session_id,
                template_id=template_id,
                name=name,
                mode=mode,
                source_action=source_action,
            )
            timestamp = now_iso()
            compatibility = {
                "schemaVersion": "newma.creator-marketplace-compatibility.v1",
                "status": "compatible",
                "canSave": True,
                "canApply": True,
                "item": {
                    "id": "openchatcut-user-template",
                    "kind": "template",
                    "name": "我的 OpenChatCut 工程模板",
                    "sourceProjectId": "openchatcut",
                },
                "target": {"stageId": stage_id, "nodeId": node_id, "name": node_definition.get("name")},
                "checks": [{"id": "editor-result", "status": "pass", "label": "OpenChatCut 已返回稳定模板 ID"}],
                "recommendedNodes": [{"stageId": stage_id, "nodeId": node_id, "label": node_definition.get("name")}],
                "demo": {"mode": "flow", "available": True},
            }
            preset = self.repository.create_preset(
                user_id=user_id,
                workspace_id=workspace_id,
                document={
                    "schemaVersion": "newma.creator-marketplace-preset.v1",
                    "presetId": f"preset-{uuid4().hex[:12]}",
                    "version": 1,
                    "name": name,
                    "itemId": "openchatcut-user-template",
                    "itemKind": "template",
                    "sourceProjectId": "openchatcut",
                    "target": {"stageId": stage_id, "nodeId": node_id},
                    "parameters": {
                        "editorId": session.get("selectedEditorId"),
                        "templateId": template_id,
                        "templateMode": mode,
                        "sourceAction": source_action,
                        "sourceVerification": "editor_returned",
                        "sourceRunId": run_id,
                        "sourceEditorSessionId": session_id,
                    },
                    "compatibility": compatibility,
                    "createdAt": timestamp,
                    "updatedAt": timestamp,
                },
            )
            state["editorSession"] = self._editor_session_summary(session)
            self._append_log(state, f"已登记 OpenChatCut 模板引用：{name}。")
            payload = {"sessionId": session_id, "templateId": template_id, "preset": preset}
        elif command.action_id == "creator.editor.import-export":
            session_ref = state.get("editorSession") or {}
            session_id = str(
                command.input.get("sessionId")
                or session_ref.get("sessionId")
                or ""
            ).strip()
            external_project_id = str(
                command.input.get("externalProjectId")
                or (session_ref.get("externalProject") or {}).get("projectId")
                or ""
            ).strip()
            download_url = str(command.input.get("downloadUrl") or "").strip()
            if not session_id or not external_project_id or not download_url:
                raise CreatorCommandError(
                    "sessionId, externalProjectId and downloadUrl are required"
                )
            session, import_result = self.editor_sessions.import_export(
                user_id=user_id,
                workspace_id=workspace_id,
                session_id=session_id,
                external_project_id=external_project_id,
                download_url=download_url,
                render_id=str(command.input.get("renderId") or "").strip(),
                name=str(command.input.get("name") or "").strip(),
            )
            outputs = [
                item
                for item in import_result.get("outputs", [])
                if isinstance(item, dict)
            ]
            created_at = str(session.get("savedAt") or now_iso())
            editor_impacts: list[dict[str, str]] = []
            for item in outputs:
                _, impacts = self.lineage.register_artifact(
                    document,
                    stage_id=stage_id,
                    node_id=node_id,
                    artifact=item,
                    created_at=created_at,
                    editor_session_id=session_id,
                )
                editor_impacts.extend(impacts)
            state["editorSession"] = self._editor_session_summary(session)
            state["status"] = "succeeded"
            state["progress"] = 100
            document["status"] = (
                "changes_requested" if editor_impacts else "pending"
            )
            self._append_log(
                state,
                f"OpenChatCut 导出已固化并回写 {len(outputs)} 个产物。",
            )
            payload = {
                "sessionId": session_id,
                "status": "saved",
                "artifactCount": len(outputs),
                "externalProjectId": external_project_id,
                "renderId": import_result.get("render_id"),
            }
        elif command.action_id == "creator.editor.save":
            session_ref = state.get("editorSession") or {}
            session_id = str(
                command.input.get("sessionId")
                or session_ref.get("sessionId")
                or ""
            ).strip()
            raw_outputs = command.input.get("outputs")
            if not session_id or not isinstance(raw_outputs, list):
                raise CreatorCommandError("sessionId and outputs are required")
            outputs: list[dict[str, Any]] = []
            for item in raw_outputs:
                if not isinstance(item, dict):
                    continue
                artifact_type = str(item.get("type") or "").strip()
                path = str(item.get("path") or "").strip()
                if artifact_type and path:
                    outputs.append(
                        {
                            "type": artifact_type,
                            "path": path,
                            "label": item.get("label") or artifact_type,
                            "status": item.get("status") or "created",
                        }
                    )
            session = self.editor_sessions.save(
                user_id=user_id,
                workspace_id=workspace_id,
                session_id=session_id,
                outputs=outputs,
            )
            created_at = str(session.get("savedAt") or now_iso())
            editor_impacts: list[dict[str, str]] = []
            for item in outputs:
                _, impacts = self.lineage.register_artifact(
                    document,
                    stage_id=stage_id,
                    node_id=node_id,
                    artifact=item,
                    created_at=created_at,
                    editor_session_id=session_id,
                )
                editor_impacts.extend(impacts)
            state["editorSession"] = self._editor_session_summary(session)
            state["status"] = "succeeded"
            state["progress"] = 100
            document["status"] = (
                "changes_requested" if editor_impacts else "pending"
            )
            self._append_log(state, f"人工编辑已保存，回写 {len(outputs)} 个产物。")
            payload = {
                "sessionId": session_id,
                "status": "saved",
                "artifactCount": len(outputs),
            }
        elif command.action_id == "creator.editor.close":
            session_ref = state.get("editorSession") or {}
            session_id = str(
                command.input.get("sessionId")
                or session_ref.get("sessionId")
                or ""
            ).strip()
            if not session_id:
                raise CreatorCommandError("sessionId is required")
            session = self.editor_sessions.close(
                user_id=user_id,
                workspace_id=workspace_id,
                session_id=session_id,
            )
            state["editorSession"] = self._editor_session_summary(session)
            self._append_log(state, "人工编辑会话已关闭。")
            payload = {"sessionId": session_id, "status": "closed"}
        elif command.action_id == "creator.publish.confirm":
            if (
                command.input.get("confirmed") is not True
                or str(command.input.get("confirmationText") or "").strip()
                != "确认发布"
            ):
                raise CreatorCommandError("publish confirmation text must be 确认发布")
            timestamp = now_iso()
            confirmation = {
                "confirmed": True,
                "confirmationText": "确认发布",
                "confirmedAt": timestamp,
                "confirmedBy": user_id,
                "consumedByJobId": None,
                "note": str(command.input.get("note") or "").strip() or None,
            }
            state["parameters"] = {
                **state.get("parameters", {}),
                "publishConfirmation": confirmation,
            }
            publish_state = document.setdefault(
                "publishState",
                {"schemaVersion": "newma.creator-publish-state.v1"},
            )
            publish_state["confirmation"] = deepcopy(confirmation)
            publish_state["updatedAt"] = timestamp
            self._append_log(state, "已取得本次发布的明确确认。")
            payload = {"publishConfirmation": confirmation}
        elif command.action_id == "creator.node.configure":
            parameters = command.input.get("parameters")
            if not isinstance(parameters, dict):
                raise CreatorCommandError("parameters must be an object")
            if command.input.get("replace") is True:
                state["parameters"] = deepcopy(parameters)
            else:
                state["parameters"] = {**state.get("parameters", {}), **parameters}
            self._append_log(state, "节点参数已更新。")
            payload = {"parameters": state["parameters"]}
        elif command.action_id == "creator.marketplace.apply-preset":
            preset_id = str(command.input.get("presetId") or "").strip()
            if not preset_id:
                raise CreatorCommandError("presetId is required")
            preset_version = command.input.get("presetVersion")
            if preset_version is not None:
                if not isinstance(preset_version, int) or preset_version < 1:
                    raise CreatorCommandError("presetVersion must be a positive integer")
                preset = self.repository.get_preset_version(
                    user_id=user_id,
                    workspace_id=workspace_id,
                    preset_id=preset_id,
                    version=preset_version,
                )
            else:
                preset = self.repository.get_preset(
                    user_id=user_id,
                    workspace_id=workspace_id,
                    preset_id=preset_id,
                )
            compatibility = self._marketplace_compatibility(
                item_id=str(preset["itemId"]),
                item_kind=str(preset["itemKind"]),
                stage_id=stage_id,
                node_id=node_id,
            )
            if not compatibility["canApply"]:
                raise CreatorCommandError("preset is incompatible with the target node")
            binding = {
                "presetId": preset_id,
                "presetVersion": preset["version"],
                "itemId": preset["itemId"],
                "itemKind": preset["itemKind"],
                "itemVersion": preset.get("itemVersion"),
                "appliedAt": now_iso(),
            }
            uses_openchatcut = (
                preset.get("itemKind") == "template"
                and preset.get("sourceProjectId") == "openchatcut"
            )
            if uses_openchatcut:
                bound_at = binding.pop("appliedAt")
                binding.update(
                    {
                        "applicationMode": "openchatcut_mcp",
                        "status": "pending_editor_application",
                        "boundAt": bound_at,
                    }
                )
            state["parameters"] = {
                **state.get("parameters", {}),
                **deepcopy(preset.get("parameters", {})),
                "marketplacePreset": binding,
            }
            state.setdefault("presetBindings", []).append(binding)
            self._append_log(
                state,
                (
                    f"已绑定 OpenChatCut 模板：{preset['name']}；进入剪辑后通过 MCP 应用。"
                    if uses_openchatcut
                    else f"已应用能力预设：{preset['name']}。"
                ),
            )
            payload = {"preset": binding, "parameters": state["parameters"]}
        elif command.action_id == "creator.node.submit-feedback":
            message = str(command.input.get("message") or "").strip()
            if not message:
                raise CreatorCommandError("feedback message is required")
            feedback = {"id": uuid4().hex, "message": message, "createdAt": now_iso()}
            state.setdefault("feedback", []).append(feedback)
            state["status"] = "changes_requested"
            self._append_log(state, f"收到修改反馈：{message}")
            document["status"] = "changes_requested"
            payload = feedback
        elif command.action_id == "creator.node.skip":
            # 显式跳过不适用节点（如文章 run 的 video lane 节点）
            state["status"] = "skipped"
            state["progress"] = 100
            self._append_log(state, "节点已跳过（不适用当前任务）。")
            document["status"] = "pending"
            payload = {"skipped": True}
        elif command.action_id == "creator.node.complete":
            # 显式收尾会话型节点：人工确认会话完成（登记产物可不齐）
            state["status"] = "succeeded"
            state["progress"] = 100
            self._append_log(state, "会话已人工确认完成。")
            document["status"] = "pending"
            payload = {"completed": True}
        elif command.action_id == "creator.node.rerun":
            # 强制重跑已 succeeded 的节点：旧交付物转 superseded，节点回到 pending，
            # 需重新 run（publish_execute 需重新走确认门禁）。
            superseded = 0
            for artifact in state.get("artifacts", []):
                if artifact.get("status") in USABLE_ARTIFACT_STATUSES:
                    artifact["status"] = "superseded"
                    superseded += 1
            state["status"] = "pending"
            state["progress"] = 0
            parameters = state.get("parameters") or {}
            if "publishConfirmation" in parameters:
                parameters.pop("publishConfirmation")
                state["parameters"] = parameters
            self._append_log(
                state,
                f"节点已重置重跑（{superseded} 个旧交付物转 superseded）。",
            )
            phase = PUBLISH_EXECUTOR_PHASES.get(
                str(node_definition.get("executor") or "")
            )
            if phase and isinstance((document.get("publishState") or {}).get(phase), dict):
                document["publishState"][phase]["nodeStatus"] = "pending"
                document["publishState"][phase].pop("approvedAt", None)
                document["publishState"]["updatedAt"] = now_iso()
            document["status"] = "pending"
            payload = {"reset": True, "supersededArtifacts": superseded}
        elif command.action_id == "creator.node.approve":
            state["status"] = "succeeded"
            state["progress"] = 100
            for artifact in state.get("artifacts", []):
                if artifact.get("status") == "created":
                    artifact["status"] = "approved"
                self._approve_artifact_file(artifact, command.input)
            self._append_log(state, "节点已审核通过。")
            # review-gate 节点：联动把 media 侧阶段 gate 文件翻 approved（消除双状态轨道）
            if str(node_definition.get("executor") or "") == "newma.control.review-gate":
                selected_ids = [
                    str(item).strip()
                    for item in (command.input.get("selectedTopicIds") or [])
                    if str(item).strip()
                ]
                try:
                    gate_result = self.control_adapter.approve_gate(
                        document["runId"], stage_id, selected_ids=selected_ids
                    )
                    self._append_log(
                        state,
                        f"阶段门禁写盘：{gate_result.get('status')} {gate_result.get('gate_file')}",
                    )
                    payload = {"gate": gate_result}
                    gate_file = str(gate_result.get("gate_file") or "").strip()
                    gate_type = Path(gate_file).stem if gate_file else ""
                    if (
                        gate_result.get("status") in {"created", "succeeded", "approved"}
                        and gate_type in {str(item) for item in node_definition.get("outputs", [])}
                    ):
                        gate_artifact, _ = self.lineage.register_artifact(
                            document,
                            stage_id=stage_id,
                            node_id=node_id,
                            artifact={
                                "type": gate_type,
                                "path": gate_file,
                                "label": gate_type,
                                "status": "approved",
                                "origin": "deliverable",
                            },
                            created_at=now_iso(),
                            producer_job_id=str(
                                (state.get("executionRequest") or {}).get("jobId") or ""
                            ) or None,
                        )
                        payload["gateArtifact"] = gate_artifact
                        self._append_log(state, f"已登记门禁交付物：{gate_type}")
                except Exception as exc:  # noqa: BLE001 - 写盘尽力而为，不阻断审批
                    self._append_log(state, f"阶段门禁写盘失败：{exc}")
            # 批准后自动转接：把本节点可用交付物交给下一节点。
            # 消除 UI 直批与 Agent 推进的双路径差异（此前 UI 批准后无人做 handoff，
            # 下一节点素材门禁不通过、运行按钮置灰）。
            next_target = self.registry.next_node(registry, stage_id, node_id)
            if next_target is not None:
                next_stage_id, next_node_id = next_target
                try:
                    handoff_payload = self._create_handoff(
                        document,
                        registry,
                        stage_id,
                        node_id,
                        {
                            "targetStageId": next_stage_id,
                            "targetNodeId": next_node_id,
                            "artifactIds": [],
                        },
                    )
                    self._append_log(
                        state,
                        f"已自动转接 {len(handoff_payload.get('materials', []))} 项交付物至 {next_stage_id}/{next_node_id}。",
                    )
                except Exception as exc:  # noqa: BLE001 - 转接尽力而为，不阻断审批
                    self._append_log(state, f"自动转接失败：{exc}")
            document["status"] = "pending"
            phase = PUBLISH_EXECUTOR_PHASES.get(
                str(node_definition.get("executor") or "")
            )
            if phase and isinstance((document.get("publishState") or {}).get(phase), dict):
                document["publishState"][phase]["nodeStatus"] = "succeeded"
                document["publishState"][phase]["approvedAt"] = now_iso()
                document["publishState"]["updatedAt"] = now_iso()
        elif command.action_id == "creator.node.request-changes":
            message = str(command.input.get("message") or "请按审核意见修改").strip()
            state["status"] = "changes_requested"
            state.setdefault("feedback", []).append(
                {"id": uuid4().hex, "message": message, "createdAt": now_iso()}
            )
            self._append_log(state, f"审核退回：{message}")
            document["status"] = "changes_requested"
            phase = PUBLISH_EXECUTOR_PHASES.get(
                str(node_definition.get("executor") or "")
            )
            if phase and isinstance((document.get("publishState") or {}).get(phase), dict):
                document["publishState"][phase]["nodeStatus"] = "changes_requested"
                document["publishState"][phase]["reviewMessage"] = message
                document["publishState"]["updatedAt"] = now_iso()
            payload = {"message": message}
        elif command.action_id == "creator.material.attach":
            raw = command.input.get("material", command.input)
            material = CreatorMaterialInput.model_validate(raw).model_dump(by_alias=True)
            state.setdefault("materials", []).append(material)
            self._append_log(state, f"新增素材：{material['type']}")
            payload = material
        elif command.action_id == "creator.artifact.register":
            artifact_type = str(command.input.get("type") or "").strip()
            path = str(command.input.get("path") or "").strip()
            if not artifact_type or not path:
                raise CreatorCommandError("artifact type and path are required")
            artifact, _ = self.lineage.register_artifact(
                document,
                stage_id=stage_id,
                node_id=node_id,
                artifact={
                    "type": artifact_type,
                    "path": path,
                    "label": command.input.get("label") or artifact_type,
                    "status": command.input.get("status") or "created",
                },
                created_at=now_iso(),
            )
            self._append_log(state, f"登记交付物：{artifact_type}")
            self._maybe_auto_complete_session_node(
                document, registry, stage_id, node_id, state, node_definition
            )
            payload = artifact
        elif command.action_id == "creator.handoff.create":
            payload = self._create_handoff(
                document,
                registry,
                stage_id,
                node_id,
                command.input,
            )
        elif command.action_id == "creator.workflow.continue":
            # 主流程推进：把 active 指针移到下一节点。纯指针操作——
            # 不强置当前节点完成（人工确认收尾用 node.complete），
            # 不重置下一节点状态（进度只前进不倒退），
            # run 完成状态由 _refresh_active_pointer 统一判定。
            if str(state.get("status") or "pending") not in FINAL_NODE_STATUSES:
                raise CreatorCommandError(
                    "当前节点未完成，不能推进到下一节点；执行型节点请先运行。"
                )
            next_target = self.registry.next_node(registry, stage_id, node_id)
            if next_target is None:
                self._append_log(state, "主流程已完成。")
                payload = {"completed": True}
            else:
                next_stage_id, next_node_id = next_target
                document["activeStageId"] = next_stage_id
                document["activeNodeId"] = next_node_id
                next_state = self._node_state(document, next_stage_id, next_node_id)
                self._append_log(
                    next_state,
                    f"由 {stage_id}/{node_id} 转接进入当前节点。",
                )
                payload = {"stageId": next_stage_id, "nodeId": next_node_id}

        self._refresh_active_pointer(document, registry)
        state["updatedAt"] = now_iso()
        document["updatedAt"] = now_iso()
        event = self._event(
            "command.executed",
            action_id=command.action_id,
            stage_id=stage_id,
            node_id=node_id,
            payload=payload,
        )
        expected_revision = command.expected_revision or int(current["revision"])
        if queued_job is not None:
            stored = self.repository.update_run_with_job(
                user_id=user_id,
                workspace_id=workspace_id,
                document=document,
                expected_revision=expected_revision,
                event=event,
                job=queued_job,
            )
            self.execution_runtime.dispatch(queued_job)
            return self.snapshot(stored, registry)

        stored = self.repository.update_run(
            user_id=user_id,
            workspace_id=workspace_id,
            document=document,
            expected_revision=expected_revision,
            event=event,
        )
        if cancel_job_id is not None:
            self.execution_runtime.cancel(
                user_id=user_id,
                workspace_id=workspace_id,
                job_id=cancel_job_id,
                requested_at=state["executionRequest"]["cancelRequestedAt"],
            )
            return self.get_snapshot(
                user_id=user_id,
                workspace_id=workspace_id,
                run_id=run_id,
            )
        return self.snapshot(stored, registry)

    def _execution_started(self, job: dict[str, Any]) -> None:
        stage_id = str(job["stageId"])
        node_id = str(job["nodeId"])
        event = self._event(
            "execution.started",
            action_id="creator.node.run",
            stage_id=stage_id,
            node_id=node_id,
            payload={
                "jobId": job["jobId"],
                "executorId": job["executorId"],
                "status": "running",
            },
        )

        def mutate(document: dict[str, Any]) -> None:
            state = self._node_state(document, stage_id, node_id)
            request = state.get("executionRequest") or {}
            if request.get("jobId") != job["jobId"]:
                event["payload"]["ignored"] = True
                return
            state["status"] = "running"
            state["progress"] = max(10, int(job.get("progress") or 0))
            state["executionRequest"] = {
                **request,
                "status": "running",
                "startedAt": job.get("startedAt") or event["createdAt"],
            }
            state["updatedAt"] = event["createdAt"]
            self._append_log(state, "执行器已开始处理当前节点。")
            document["status"] = "running"

        self.repository.mutate_run(
            user_id=str(job["userId"]),
            workspace_id=str(job["workspaceId"]),
            run_id=str(job["runId"]),
            mutate=mutate,
            event=event,
        )

    def _execution_finished(self, job: dict[str, Any]) -> None:
        registry = self.registry.load()
        stage_id = str(job["stageId"])
        node_id = str(job["nodeId"])
        node_definition = self.registry.node(registry, stage_id, node_id)
        execution = job.get("result") if isinstance(job.get("result"), dict) else {}
        execution_status = str(execution.get("status") or job.get("status") or "failed")
        if job.get("status") == "cancelled":
            execution_status = "cancelled"
        if (
            execution_status == "succeeded"
            and (node_definition.get("gate") or {}).get("required")
        ):
            execution_status = "waiting_user"
        if execution_status not in {
            "succeeded",
            "waiting_user",
            "blocked",
            "failed",
            "cancelled",
        }:
            execution_status = "failed"
        editor_session = self.editor_sessions.create_from_execution(
            job=job,
            execution=execution,
        )

        event = self._event(
            "execution.finished",
            action_id="creator.node.run",
            stage_id=stage_id,
            node_id=node_id,
            payload={
                "jobId": job["jobId"],
                "executionId": execution.get("execution_id"),
                "executorId": execution.get("executor_id") or job["executorId"],
                "status": execution_status,
                "artifactCount": len(execution.get("artifacts", [])),
                "editorSessionId": (
                    editor_session.get("sessionId") if editor_session else None
                ),
            },
        )

        def mutate(document: dict[str, Any]) -> None:
            state = self._node_state(document, stage_id, node_id)
            request = state.get("executionRequest") or {}
            if request.get("jobId") != job["jobId"]:
                event["payload"]["ignored"] = True
                return
            finished_at = str(
                execution.get("finished_at")
                or job.get("finishedAt")
                or event["createdAt"]
            )
            stale_pending = state.pop("stalePending", None)
            final_status = (
                "stale"
                if stale_pending
                and execution_status in {"succeeded", "waiting_user"}
                else execution_status
            )
            event["payload"]["finalStatus"] = final_status
            state["status"] = final_status
            state["progress"] = (
                0
                if final_status == "stale"
                else int(
                    execution.get("progress")
                    or (100 if final_status in {"succeeded", "waiting_user"} else 0)
                )
            )
            if final_status == "stale" and stale_pending:
                state["staleAt"] = stale_pending.get("at")
                state["staleReason"] = stale_pending.get("reason")
            state["executionRequest"] = {
                **request,
                "status": (
                    "completed"
                    if execution_status in {"succeeded", "waiting_user"}
                    else execution_status
                ),
                "completedAt": finished_at,
            }
            state["executionResult"] = {
                "jobId": job["jobId"],
                "executionId": execution.get("execution_id"),
                "executorId": execution.get("executor_id") or job["executorId"],
                "status": final_status,
                "adapterStatus": execution_status,
                "exitCode": execution.get("exit_code"),
                "durationMs": execution.get("duration_ms"),
                "resultPath": execution.get("execution_result"),
                "error": job.get("error"),
                "finishedAt": finished_at,
            }
            publish_phase = PUBLISH_EXECUTOR_PHASES.get(str(job["executorId"]))
            if publish_phase:
                publish_payload = (
                    execution.get("result")
                    if isinstance(execution.get("result"), dict)
                    else {}
                )
                publish_state = document.setdefault(
                    "publishState",
                    {"schemaVersion": "newma.creator-publish-state.v1"},
                )
                publish_state[publish_phase] = {
                    **deepcopy(publish_payload),
                    "jobId": job["jobId"],
                    "nodeId": node_id,
                    "nodeStatus": final_status,
                    "finishedAt": finished_at,
                }
                if publish_phase == "execution":
                    publish_state["confirmation"] = deepcopy(
                        (state.get("parameters") or {}).get("publishConfirmation")
                    )
                publish_state["updatedAt"] = finished_at
            if editor_session is not None:
                state["editorSession"] = self._editor_session_summary(
                    editor_session
                )
            for log in execution.get("logs", []):
                message = str(
                    log.get("message") if isinstance(log, dict) else log
                ).strip()
                if message:
                    state.setdefault("logs", []).append(
                        {
                            "at": (
                                str(log.get("at") or finished_at)
                                if isinstance(log, dict)
                                else finished_at
                            ),
                            "message": message,
                        }
                    )
            existing = {
                (
                    str(item.get("producerJobId") or ""),
                    str(item.get("type") or ""),
                    str(item.get("path") or ""),
                )
                for item in state.get("artifacts", [])
            }
            stale_impacts: list[dict[str, str]] = []
            for item in execution.get("artifacts", []):
                if not isinstance(item, dict):
                    continue
                artifact_type = str(item.get("type") or "").strip()
                artifact_path = str(item.get("path") or "").strip()
                key = (str(job["jobId"]), artifact_type, artifact_path)
                if not artifact_type or not artifact_path or key in existing:
                    continue
                artifact_status = (
                    "stale"
                    if final_status == "stale"
                    else item.get("status") or "created"
                )
                created_artifact, impacts = self.lineage.register_artifact(
                    document,
                    stage_id=stage_id,
                    node_id=node_id,
                    artifact={
                        "type": artifact_type,
                        "path": artifact_path,
                        "label": item.get("label") or artifact_type,
                        "status": artifact_status,
                        "origin": str(item.get("origin") or "deliverable"),
                    },
                    created_at=finished_at,
                    producer_job_id=str(job["jobId"]),
                    execution_id=execution.get("execution_id"),
                )
                if final_status == "stale" and stale_pending:
                    created_artifact["staleAt"] = stale_pending.get("at")
                    created_artifact["staleReason"] = stale_pending.get("reason")
                stale_impacts.extend(impacts)
                existing.add(key)
            state["updatedAt"] = finished_at
            document["status"] = {
                "succeeded": "pending",
                "waiting_user": "waiting_user",
                "blocked": "blocked",
                "failed": "failed",
                "cancelled": "cancelled",
                "stale": "changes_requested",
            }[final_status]
            if stale_impacts:
                document["status"] = "changes_requested"
            # 执行型节点成功后自动转接：把本节点产物交给下一节点（与 approve 的
            # 自动转接同一语义——消除「执行成功但下游素材缺失、运行置灰」的断链）。
            # waiting_user（gate/会话）节点不在此转接：gate 等 approve 联动，
            # 会话节点等 register 收尾。
            if final_status == "succeeded":
                next_target = self.registry.next_node(registry, stage_id, node_id)
                if next_target is not None:
                    next_stage_id, next_node_id = next_target
                    try:
                        handoff_payload = self._create_handoff(
                            document,
                            registry,
                            stage_id,
                            node_id,
                            {
                                "targetStageId": next_stage_id,
                                "targetNodeId": next_node_id,
                                "artifactIds": [],
                            },
                        )
                        state.setdefault("logs", []).append(
                            {
                                "at": finished_at,
                                "message": (
                                    f"已自动转接 {len(handoff_payload.get('materials', []))} 项交付物至 "
                                    f"{next_stage_id}/{next_node_id}。"
                                ),
                            }
                        )
                    except Exception as exc:  # noqa: BLE001 - 转接尽力而为，不阻断执行收尾
                        state.setdefault("logs", []).append(
                            {"at": finished_at, "message": f"自动转接失败：{exc}"}
                        )
            # 执行器异步完成也会改变节点终态分布，同步刷新 active 指针与 run 完成判断
            self._refresh_active_pointer(document, registry)

        self.repository.mutate_run(
            user_id=str(job["userId"]),
            workspace_id=str(job["workspaceId"]),
            run_id=str(job["runId"]),
            mutate=mutate,
            event=event,
        )

    def list_jobs(
        self,
        *,
        user_id: str,
        workspace_id: str,
        run_id: str,
    ) -> dict[str, Any]:
        self.repository.get_run(
            user_id=user_id,
            workspace_id=workspace_id,
            run_id=run_id,
        )
        return {
            "schemaVersion": "newma.creator-execution-job-list.v1",
            "jobs": self.repository.list_jobs(
                user_id=user_id,
                workspace_id=workspace_id,
                run_id=run_id,
            ),
        }

    def list_editor_sessions(
        self,
        *,
        user_id: str,
        workspace_id: str,
        run_id: str,
    ) -> dict[str, Any]:
        self.repository.get_run(
            user_id=user_id,
            workspace_id=workspace_id,
            run_id=run_id,
        )
        return {
            "schemaVersion": "newma.editor-session-list.v1",
            "sessions": self.repository.list_editor_sessions(
                user_id=user_id,
                workspace_id=workspace_id,
                run_id=run_id,
            ),
        }

    @staticmethod
    def _editor_session_summary(session: dict[str, Any]) -> dict[str, Any]:
        return {
            "sessionId": session["sessionId"],
            "status": session["status"],
            "editors": deepcopy(session.get("editors", [])),
            "selectedEditorId": session.get("selectedEditorId"),
            "externalProject": deepcopy(session.get("externalProject")),
            "outputContract": session.get("outputContract", []),
            "outputArtifacts": deepcopy(session.get("outputArtifacts", [])),
            "collaboration": deepcopy(session.get("collaboration")),
            "savedTemplates": deepcopy(session.get("savedTemplates", [])),
            "launch": deepcopy(session.get("launch")),
            "createdAt": session["createdAt"],
            "updatedAt": session["updatedAt"],
        }

    def list_events(
        self,
        *,
        user_id: str,
        workspace_id: str,
        run_id: str,
        after: int,
    ) -> dict[str, Any]:
        events = self.repository.list_events(
            user_id=user_id,
            workspace_id=workspace_id,
            run_id=run_id,
            after=after,
        )
        return {
            "events": events,
            "lastSequence": events[-1]["sequence"] if events else after,
        }

    def detect_capabilities(self) -> dict[str, Any]:
        return self.control_adapter.detect_capabilities()

    def test_agent(self, *, agent_id: str, bin_override: str = "") -> dict[str, Any]:
        """Run a minimal hello prompt through the specified CLI agent to verify it works."""
        return self.control_adapter.test_agent(agent_id, bin_override)

    def preview_artifact(self, path: str) -> dict[str, Any]:
        """Safely read a file for artifact preview.

        Allowed roots: user's Desktop/自媒体创作/, the media workspace root, and their subtrees.
        Returns { path, exists, mime, encoding, content, size, truncated, error? }.
        """
        import base64
        import mimetypes
        from pathlib import Path as _Path

        target = _Path(path).expanduser().resolve()
        home = _Path.home().resolve()
        allowed_roots = [
            home / "Desktop" / "自媒体创作",
            self.control_adapter.workspace,
        ]
        allowed = any(
            str(target).startswith(str(root)) for root in allowed_roots if root
        )
        if not allowed:
            return {
                "path": str(target),
                "exists": False,
                "error": "path not in allowed artifact roots",
            }
        if not target.exists():
            return {"path": str(target), "exists": False, "error": "file not found"}
        if target.is_dir():
            entries = [
                {"name": p.name, "is_dir": p.is_dir(), "size": p.stat().st_size if p.is_file() else 0}
                for p in sorted(target.iterdir())[:200]
            ]
            return {
                "path": str(target),
                "exists": True,
                "mime": "inode/directory",
                "encoding": "directory",
                "entries": entries,
                "size": len(entries),
            }
        size = target.stat().st_size
        mime, _ = mimetypes.guess_type(str(target))
        suffix = target.suffix.lower()
        text_suffixes = {
            ".md", ".json", ".txt", ".html", ".htm", ".yaml", ".yml",
            ".csv", ".tsv", ".log", ".srt", ".vtt", ".py", ".js",
            ".ts", ".tsx", ".jsx", ".css",
        }
        if suffix in text_suffixes or (mime and mime.startswith("text/")):
            try:
                content = target.read_text(encoding="utf-8", errors="replace")
                truncated = False
                if len(content) > 200_000:
                    content = content[:200_000] + "\n\n... [truncated for preview] ..."
                    truncated = True
                return {
                    "path": str(target),
                    "exists": True,
                    "mime": mime or ("application/json" if suffix == ".json" else "text/plain"),
                    "encoding": "text",
                    "content": content,
                    "size": size,
                    "truncated": truncated,
                    "suffix": suffix,
                }
            except OSError as exc:
                return {"path": str(target), "exists": True, "error": str(exc)}
        binary_max = 4_000_000
        if size <= binary_max and (
            (mime and (mime.startswith("image/") or mime.startswith("video/") or mime.startswith("audio/")))
            or suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".mp4", ".webm", ".mp3", ".wav"}
        ):
            data = target.read_bytes()
            return {
                "path": str(target),
                "exists": True,
                "mime": mime or "application/octet-stream",
                "encoding": "base64",
                "content": base64.b64encode(data).decode("ascii"),
                "size": size,
                "truncated": False,
                "suffix": suffix,
            }
        return {
            "path": str(target),
            "exists": True,
            "mime": mime or "application/octet-stream",
            "encoding": "binary",
            "size": size,
            "suffix": suffix,
            "hint": "文件过大或不支持预览，仅返回元信息",
        }

    def marketplace(self) -> dict[str, Any]:
        return self.control_adapter.marketplace()

    def marketplace_compatibility(
        self,
        request: MarketplaceCompatibilityRequest,
    ) -> dict[str, Any]:
        return self._marketplace_compatibility(
            item_id=request.item_id,
            item_kind=request.item_kind,
            stage_id=request.stage_id,
            node_id=request.node_id,
        )

    def list_marketplace_presets(
        self,
        *,
        user_id: str,
        workspace_id: str,
    ) -> dict[str, Any]:
        presets = self.repository.list_presets(
            user_id=user_id,
            workspace_id=workspace_id,
        )
        return {
            "schemaVersion": "newma.creator-marketplace-preset-list.v1",
            "presets": presets,
        }

    def create_marketplace_preset(
        self,
        *,
        user_id: str,
        workspace_id: str,
        request: MarketplacePresetCreate,
    ) -> dict[str, Any]:
        compatibility = self._marketplace_compatibility(
            item_id=request.item_id,
            item_kind=request.item_kind,
            stage_id=request.stage_id,
            node_id=request.node_id,
        )
        if compatibility["status"] == "incompatible":
            raise CreatorCommandError("marketplace item is incompatible with the selected target")
        item = compatibility["item"]
        timestamp = now_iso()
        document = {
            "schemaVersion": "newma.creator-marketplace-preset.v1",
            "presetId": f"preset-{uuid4().hex[:12]}",
            "version": 1,
            "name": request.name,
            "itemId": request.item_id,
            "itemKind": request.item_kind,
            "itemVersion": item.get("version"),
            "sourceProjectId": item.get("sourceProjectId"),
            "target": {
                "stageId": request.stage_id,
                "nodeId": request.node_id,
            } if request.stage_id and request.node_id else None,
            "parameters": deepcopy(request.parameters),
            "compatibility": compatibility,
            "createdAt": timestamp,
            "updatedAt": timestamp,
        }
        return self.repository.create_preset(
            user_id=user_id,
            workspace_id=workspace_id,
            document=document,
        )

    def list_marketplace_preset_versions(
        self,
        *,
        user_id: str,
        workspace_id: str,
        preset_id: str,
    ) -> dict[str, Any]:
        versions = self.repository.list_preset_versions(
            user_id=user_id,
            workspace_id=workspace_id,
            preset_id=preset_id,
        )
        return {
            "schemaVersion": "newma.creator-marketplace-preset-version-list.v1",
            "presetId": preset_id,
            "versions": versions,
        }

    def update_marketplace_preset(
        self,
        *,
        user_id: str,
        workspace_id: str,
        preset_id: str,
        request: MarketplacePresetUpdate,
    ) -> dict[str, Any]:
        current = self.repository.get_preset(
            user_id=user_id,
            workspace_id=workspace_id,
            preset_id=preset_id,
        )
        if bool(request.stage_id) != bool(request.node_id):
            raise CreatorCommandError("stageId and nodeId must be provided together")
        compatibility = self._marketplace_compatibility(
            item_id=str(current["itemId"]),
            item_kind=str(current["itemKind"]),
            stage_id=request.stage_id,
            node_id=request.node_id,
        )
        if compatibility["status"] == "incompatible":
            raise CreatorCommandError("marketplace item is incompatible with the selected target")
        document = {
            **deepcopy(current),
            "version": request.expected_version + 1,
            "name": request.name,
            "target": {
                "stageId": request.stage_id,
                "nodeId": request.node_id,
            } if request.stage_id and request.node_id else None,
            "parameters": deepcopy(request.parameters),
            "compatibility": compatibility,
            "updatedAt": now_iso(),
        }
        return self.repository.update_preset(
            user_id=user_id,
            workspace_id=workspace_id,
            document=document,
            expected_version=request.expected_version,
        )

    def _marketplace_compatibility(
        self,
        *,
        item_id: str,
        item_kind: str,
        stage_id: str | None,
        node_id: str | None,
    ) -> dict[str, Any]:
        catalog = self.marketplace()
        groups = {
            "project": catalog.get("projects", []),
            "skill": catalog.get("skills", []),
            "pipeline": catalog.get("pipelines", []),
            "template": catalog.get("templates", []),
        }
        if item_kind not in groups:
            raise CreatorCommandError(f"unsupported marketplace kind: {item_kind}")
        item = next((row for row in groups[item_kind] if row.get("id") == item_id), None)
        if not item:
            raise CreatorCommandError(f"marketplace item not found: {item_kind}/{item_id}")
        if bool(stage_id) != bool(node_id):
            raise CreatorCommandError("stageId and nodeId must be provided together")

        checks: list[dict[str, Any]] = []
        runtime = str((item.get("status") or {}).get("runtime") or "unknown")
        runtime_ok = runtime in {"available", "degraded"}
        checks.append({
            "id": "runtime",
            "status": "pass" if runtime == "available" else "warning" if runtime == "degraded" else "fail",
            "label": (item.get("status") or {}).get("label") or runtime,
        })

        registry = self.registry.load()
        recommended_nodes: list[dict[str, str]] = []
        supported_stages = set(item.get("stageIds") or [])
        for stage in registry.get("stages", []):
            candidate_stage_id = str(stage.get("id"))
            if supported_stages and candidate_stage_id not in supported_stages:
                continue
            for node in stage.get("nodes", []):
                recommended_nodes.append({
                    "stageId": candidate_stage_id,
                    "nodeId": str(node.get("id")),
                    "label": f"{stage.get('name')} / {node.get('name')}",
                })

        stage_ok = True
        node_match = False
        target: dict[str, Any] | None = None
        if stage_id and node_id:
            node = self.registry.node(registry, stage_id, node_id)
            stage_ok = not supported_stages or stage_id in supported_stages
            node_capabilities = set(node.get("capabilities") or [])
            item_capabilities = set(item.get("capabilities") or [])
            node_match = bool(node_capabilities & item_capabilities)
            if item_kind == "pipeline":
                node_match = bool(node_capabilities & {"preset_selection", "lane_routing", "director_routing"})
            elif item_kind == "template":
                node_match = bool(node_capabilities & {"html_storyboard", "remotion_render", "html_video_render", "motion_overlay", "preset_selection"})
            target = {"stageId": stage_id, "nodeId": node_id, "name": node.get("name")}
            checks.append({
                "id": "stage",
                "status": "pass" if stage_ok else "fail",
                "label": "适用于当前阶段" if stage_ok else "不适用于当前阶段",
            })
            checks.append({
                "id": "node",
                "status": "pass" if node_match else "warning",
                "label": "节点能力直接匹配" if node_match else "阶段兼容，节点将作为参数预设使用",
            })
        else:
            checks.append({"id": "target", "status": "warning", "label": "尚未选择目标节点"})

        incompatible = not runtime_ok or not stage_ok
        status = "incompatible" if incompatible else "compatible" if stage_id and node_id else "ready_for_target"
        preview = item.get("preview") or {}
        return {
            "schemaVersion": "newma.creator-marketplace-compatibility.v1",
            "status": status,
            "canSave": not incompatible,
            "canApply": not incompatible and bool(stage_id and node_id),
            "item": {
                "id": item.get("id"),
                "kind": item.get("kind"),
                "name": item.get("name"),
                "version": item.get("version"),
                "sourceProjectId": item.get("sourceProjectId"),
            },
            "target": target,
            "checks": checks,
            "recommendedNodes": recommended_nodes[:12],
            "demo": {
                "mode": "preview" if preview.get("url") else "source" if item.get("source") else "flow",
                "url": preview.get("url") or item.get("source"),
                "available": bool(preview.get("url") or item.get("source") or item.get("flow")),
            },
        }

    def marketplace_asset(self, asset_path: str) -> Path:
        return self.control_adapter.marketplace_asset(asset_path)

    def _node_state(
        self,
        document: dict[str, Any],
        stage_id: str,
        node_id: str,
    ) -> dict[str, Any]:
        """获取节点状态；registry 后续新增的节点对旧 run 惰性创建默认 state。

        避免 run 创建后 registry 插入新节点导致 snapshot/命令路径 KeyError（500）。
        """
        key = node_key(stage_id, node_id)
        states = document["nodeStates"]
        state = states.get(key)
        if state is None:
            state = {
                "status": "pending",
                "progress": 0,
                "materials": [],
                "artifacts": [],
                "feedback": [],
                "logs": [],
                "parameters": {},
                "attempt": 0,
                "updatedAt": now_iso(),
            }
            states[key] = state
        return state

    def snapshot(
        self,
        document: dict[str, Any],
        registry: dict[str, Any],
    ) -> dict[str, Any]:
        file_catalog = self.products.build(document, registry)
        stages: list[dict[str, Any]] = []
        graph_nodes: list[dict[str, Any]] = []
        graph_edges: list[dict[str, Any]] = []
        notifications: list[dict[str, Any]] = []
        previous_graph_id: str | None = None
        all_nodes: list[dict[str, Any]] = []
        for stage in registry.get("stages", []):
            stage_id = str(stage["id"])
            nodes: list[dict[str, Any]] = []
            for node in stage.get("nodes", []):
                node_id = str(node["id"])
                state = self._node_state(document, stage_id, node_id)
                material_report = self.registry.validate_materials(
                    registry,
                    stage_id,
                    node_id,
                    state.get("materials", []),
                    project_start=bool(state.get("allowManualBootstrap")),
                )
                product = self.products.resolve_node(
                    stage_id,
                    node,
                    state,
                    file_catalog,
                )
                row = {
                    "id": node_id,
                    "name": node.get("name"),
                    "description": node.get("description"),
                    "status": state.get("status", "pending"),
                    "progress": int(state.get("progress") or 0),
                    "gate": node.get("gate"),
                    "actions": node.get("actions", []),
                    "capabilities": node.get("capabilities", []),
                    "executor": node.get("executor"),
                    "editors": node.get("editors", []),
                    "materialRequirements": node.get("material_requirements", []),
                    "materialValidation": material_report,
                    "materials": state.get("materials", []),
                    "outputs": node.get("outputs", []),
                    "artifacts": state.get("artifacts", []),
                    "product": product,
                    "feedback": state.get("feedback", []),
                    "logs": state.get("logs", []),
                    "parameters": state.get("parameters", {}),
                    "attempt": state.get("attempt", 0),
                    "executionRequest": state.get("executionRequest"),
                    "executionResult": state.get("executionResult"),
                    "editorSession": state.get("editorSession"),
                    "staleAt": state.get("staleAt"),
                    "staleReason": state.get("staleReason"),
                    "availableActions": self._available_actions(
                        node,
                        state,
                        material_report,
                    ),
                }
                nodes.append(row)
                all_nodes.append(row)
                graph_id = node_key(stage_id, node_id)
                graph_nodes.append(
                    {
                        "id": graph_id,
                        "stageId": stage_id,
                        "nodeId": node_id,
                        "label": node.get("name"),
                        "status": row["status"],
                    }
                )
                if previous_graph_id:
                    graph_edges.append({"from": previous_graph_id, "to": graph_id})
                previous_graph_id = graph_id
                if row["status"] == "waiting_user":
                    notifications.append(
                        {
                            "id": f"review:{graph_id}",
                            "kind": "review",
                            "title": f"{node.get('name')}待审核",
                            "stageId": stage_id,
                            "nodeId": node_id,
                        }
                    )
                elif row["status"] in ATTENTION_NODE_STATUSES - {"waiting_user"}:
                    notifications.append(
                        {
                            "id": f"warning:{graph_id}",
                            "kind": "warning",
                            "title": f"{node.get('name')}：{row['status']}",
                            "stageId": stage_id,
                            "nodeId": node_id,
                        }
                    )
                for artifact in row["product"]["deliverables"][-3:]:
                    if (
                        artifact.get("source") == "artifact"
                        and artifact.get("status") in {"created", "approved", "succeeded"}
                    ):
                        notifications.append(
                            {
                                "id": f"artifact:{artifact.get('artifactId') or artifact.get('id')}",
                                "kind": "artifact",
                                "title": f"新交付：{artifact.get('label') or artifact.get('type')}",
                                "stageId": stage_id,
                                "nodeId": node_id,
                                "artifactId": artifact.get("artifactId"),
                                "artifactPath": artifact.get("path"),
                            }
                        )
            statuses = [row["status"] for row in nodes]
            stage_status = self._stage_status(statuses)
            stage_progress = round(
                sum(int(row["progress"]) for row in nodes) / len(nodes)
            ) if nodes else 0
            stages.append(
                {
                    "order": stage.get("order"),
                    "id": stage_id,
                    "name": stage.get("name"),
                    "shortLabel": stage.get("short_label"),
                    "color": stage.get("color"),
                    "status": stage_status,
                    "progress": stage_progress,
                    "nodes": nodes,
                    "products": [
                        {
                            "nodeId": row["id"],
                            "nodeName": row["name"],
                            **row["product"],
                        }
                        for row in nodes
                    ],
                    "laneCatalog": stage.get("lane_catalog", []),
                }
            )
        progress = round(
            sum(int(row["progress"]) for row in all_nodes) / len(all_nodes)
        ) if all_nodes else 0
        return {
            "schemaVersion": "newma.creator-studio-snapshot.v1",
            "generatedAt": now_iso(),
            "run": {
                **self._summary(document),
                "progress": progress,
                "createdAt": document["createdAt"],
            },
            "stages": stages,
            "graph": {"nodes": graph_nodes, "edges": graph_edges},
            "fileCatalog": file_catalog,
            "handoffs": document.get("handoffs", []),
            "lineageState": document.get("lineageState"),
            "publishState": document.get("publishState"),
            "notifications": notifications[-30:],
            "counters": {
                "waitingReview": sum(1 for item in notifications if item["kind"] == "review"),
                "newArtifacts": sum(1 for item in notifications if item["kind"] == "artifact"),
                "blockedNodes": sum(1 for item in notifications if item["kind"] == "warning"),
            },
            "lastEventSequence": (
                document.get("events", [])[-1].get("sequence", 0)
                if document.get("events")
                else 0
            ),
        }

    def _create_handoff(
        self,
        document: dict[str, Any],
        registry: dict[str, Any],
        source_stage_id: str,
        source_node_id: str,
        input_data: dict[str, Any],
    ) -> dict[str, Any]:
        target_stage_id = str(input_data.get("targetStageId") or "")
        target_node_id = str(input_data.get("targetNodeId") or "")
        self.registry.node(registry, target_stage_id, target_node_id)
        source_state = self._node_state(document, source_stage_id, source_node_id)
        requested_ids = {
            str(item) for item in input_data.get("artifactIds", []) if str(item)
        }
        artifacts = [
            item
            for item in source_state.get("artifacts", [])
            if (not requested_ids or str(item.get("id")) in requested_ids)
            and str(item.get("status") or "created") in USABLE_ARTIFACT_STATUSES
            # 占位 packet（write_node_packets 自产）不是真实交付物，不参与 handoff
            and str(item.get("origin") or "deliverable") != "packet"
        ]
        if not artifacts:
            raise CreatorCommandError("no artifacts are available for handoff")
        target_state = self._node_state(document, target_stage_id, target_node_id)
        materials = [
            self.lineage.material_reference(
                run_id=str(document["runId"]),
                stage_id=source_stage_id,
                node_id=source_node_id,
                artifact=artifact,
            )
            for artifact in artifacts
        ]
        material_types = {str(item["type"]) for item in materials}
        previous_artifact_ids: set[str] = set()
        for existing_handoff in document.get("handoffs", []):
            existing_source = existing_handoff.get("source") or {}
            existing_target = existing_handoff.get("target") or {}
            if (
                existing_source.get("stageId") == source_stage_id
                and existing_source.get("nodeId") == source_node_id
                and existing_target.get("stageId") == target_stage_id
                and existing_target.get("nodeId") == target_node_id
            ):
                for item in existing_handoff.get("materials", []):
                    if str(item.get("type") or "") in material_types:
                        previous_artifact_ids.add(str(item.get("artifactId") or ""))
                if existing_handoff.get("status") != "stale":
                    existing_handoff["status"] = "superseded"
                    existing_handoff["supersededAt"] = now_iso()
        target_state["materials"] = [
            item
            for item in target_state.get("materials", [])
            if str(item.get("artifactId") or "") not in previous_artifact_ids
            and not (
                item.get("sourceStageId") == source_stage_id
                and item.get("sourceNodeId") == source_node_id
                and str(item.get("type") or "") in material_types
            )
        ]
        target_state["materials"].extend(materials)
        validation = self.registry.validate_materials(
            registry,
            target_stage_id,
            target_node_id,
            target_state["materials"],
        )
        handoff = {
            "id": f"handoff-{uuid4().hex[:12]}",
            "source": {"stageId": source_stage_id, "nodeId": source_node_id},
            "target": {"stageId": target_stage_id, "nodeId": target_node_id},
            "materials": materials,
            "artifactRefs": [
                {
                    "artifactId": item["artifactId"],
                    "version": item["artifactVersion"],
                    "contentDigest": item.get("contentDigest"),
                }
                for item in materials
            ],
            "status": validation["status"],
            "createdAt": now_iso(),
        }
        document.setdefault("handoffs", []).append(handoff)
        if validation["status"] == "ready" and target_state.get("status") == "stale":
            target_state["status"] = "pending"
            target_state["progress"] = 0
            target_state.pop("staleAt", None)
            target_state.pop("staleReason", None)
        self._append_log(
            target_state,
            f"收到来自 {source_stage_id}/{source_node_id} 的交付物转接。",
        )
        return handoff

    def _approve_artifact_file(
        self,
        artifact: dict[str, Any],
        approve_input: dict[str, Any],
    ) -> None:
        """Approve 后同步 gate 产物文件（pending_review → approved，注入审定内容）。"""
        path_text = str(artifact.get("path") or "").strip()
        artifact_type = str(artifact.get("type") or "").strip()
        if not path_text or not artifact_type:
            return
        path = Path(path_text)
        if not path.is_file():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(payload, dict) or payload.get("status") != "pending_review":
            return
        payload["status"] = "approved"
        payload["approved_at"] = now_iso()
        extra = approve_input.get(artifact_type)
        if isinstance(extra, (list, dict)) and extra:
            payload[artifact_type] = extra
        try:
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            return

    @staticmethod
    def _append_log(state: dict[str, Any], message: str) -> None:
        state.setdefault("logs", []).append({"at": now_iso(), "message": message})

    def _maybe_auto_complete_session_node(
        self,
        document: dict[str, Any],
        registry: dict[str, Any],
        stage_id: str,
        node_id: str,
        state: dict[str, Any],
        node_definition: dict[str, Any],
    ) -> None:
        """会话型节点（editor/capacity session）已登记产物覆盖全部声明输出时自动完成。

        自动完成与执行型 succeeded 同语义：自动把产物转接给下一节点。
        """
        if state.get("status") != "waiting_user":
            return
        executor_id = str(node_definition.get("executor") or "")
        if executor_id not in SESSION_EXECUTOR_IDS:
            return
        outputs = {str(item) for item in (node_definition.get("outputs") or [])}
        if not outputs:
            return
        registered = {
            str(item.get("type"))
            for item in state.get("artifacts", [])
            if item.get("status") in USABLE_ARTIFACT_STATUSES
        }
        if outputs <= registered:
            state["status"] = "succeeded"
            state["progress"] = 100
            self._append_log(state, "已登记产物覆盖全部声明输出，会话自动完成。")
            document["status"] = "pending"
            # 会话自动完成与执行型 succeeded 同语义：自动转接产物给下一节点
            next_target = self.registry.next_node(registry, stage_id, node_id)
            if next_target is not None:
                next_stage_id, next_node_id = next_target
                try:
                    handoff_payload = self._create_handoff(
                        document,
                        registry,
                        stage_id,
                        node_id,
                        {
                            "targetStageId": next_stage_id,
                            "targetNodeId": next_node_id,
                            "artifactIds": [],
                        },
                    )
                    self._append_log(
                        state,
                        f"已自动转接 {len(handoff_payload.get('materials', []))} 项交付物至 {next_stage_id}/{next_node_id}。",
                    )
                except Exception as exc:  # noqa: BLE001 - 转接尽力而为，不阻断自动完成
                    self._append_log(state, f"自动转接失败：{exc}")

    def _refresh_active_pointer(
        self, document: dict[str, Any], registry: dict[str, Any]
    ) -> None:
        """把 activeStageId/activeNodeId 指到顺序上第一个未完成节点；全终态时保持现状。"""
        for stage in registry.get("stages", []):
            stage_id = str(stage.get("id") or "")
            for node in stage.get("nodes", []):
                node_id = str(node.get("id") or "")
                state = (document.get("nodeStates") or {}).get(
                    node_key(stage_id, node_id)
                )
                if state and state.get("status") not in FINAL_NODE_STATUSES:
                    document["activeStageId"] = stage_id
                    document["activeNodeId"] = node_id
                    return
        # 全部节点终态：run 完成
        document["status"] = "succeeded"

    @staticmethod
    def _available_actions(
        node_definition: dict[str, Any],
        state: dict[str, Any],
        material_report: dict[str, Any],
    ) -> list[str]:
        status = str(state.get("status") or "pending")
        actions: list[str] = []

        if status not in {"queued", "running"}:
            actions.extend(
                [
                    "creator.node.configure",
                    "creator.marketplace.apply-preset",
                    "creator.node.submit-feedback",
                    "creator.material.attach",
                    "creator.artifact.register",
                ]
            )
        if status in {"queued", "running"} and (
            state.get("executionRequest") or {}
        ).get("jobId"):
            actions.append("creator.node.cancel")
        editor_session = state.get("editorSession") or {}
        editor_status = str(editor_session.get("status") or "")
        if editor_session and any(
            item.get("status") in {"available", "open"}
            for item in editor_session.get("editors", [])
        ):
            actions.append("creator.editor.launch")
        selected_editor_id = editor_session.get("selectedEditorId")
        agent_editors = [
            item
            for item in editor_session.get("editors", [])
            if isinstance(item.get("agentBridge"), dict)
            and item.get("agentBridge", {}).get("endpoint")
            and item.get("status") in {"available", "open"}
        ]
        if agent_editors and editor_status in {"ready", "open", "saved"}:
            actions.append("creator.editor.start-agent")
        if editor_status == "agent_editing":
            actions.append("creator.editor.submit-proposal")
            actions.append("creator.editor.review-proposal")
        if editor_status == "waiting_review":
            actions.append("creator.editor.review-proposal")
        if editor_status == "open":
            actions.append("creator.editor.save")
        if editor_status in {"open", "saved"} and selected_editor_id == "openchatcut":
            actions.append("creator.editor.import-export")
        if editor_status in {"open", "saved"} and selected_editor_id:
            actions.append("creator.editor.save-template")
        if editor_status in {"open", "saved", "blocked", "agent_editing", "waiting_review"}:
            actions.append("creator.editor.close")
        if material_report.get("status") == "ready":
            executor_id = str(node_definition.get("executor") or "")
            confirmation = (state.get("parameters") or {}).get(
                "publishConfirmation"
            )
            has_fresh_publish_confirmation = (
                isinstance(confirmation, dict)
                and confirmation.get("confirmed") is True
                and not confirmation.get("consumedByJobId")
            )
            execution_allowed = (
                executor_id != "newma.publish.execute"
                or has_fresh_publish_confirmation
            )
            if (
                executor_id == "newma.publish.execute"
                and status in RUNNABLE_NODE_STATUSES | RETRYABLE_NODE_STATUSES
                and not has_fresh_publish_confirmation
            ):
                actions.append("creator.publish.confirm")
            if execution_allowed and status in RUNNABLE_NODE_STATUSES:
                actions.append("creator.node.run")
            if execution_allowed and status in RETRYABLE_NODE_STATUSES:
                actions.append("creator.node.retry")
        if status not in {"queued", "running"} and status not in FINAL_NODE_STATUSES:
            actions.append("creator.node.skip")
        if (
            bool((node_definition.get("gate") or {}).get("required"))
            and status == "waiting_user"
        ):
            actions.extend(
                ["creator.node.approve", "creator.node.request-changes"]
            )
        elif (
            status == "waiting_user"
            and str(node_definition.get("executor") or "") not in SESSION_EXECUTOR_IDS
        ):
            actions.append("creator.node.complete")
        if status not in {"queued", "running"} and any(
            str(item.get("status") or "created") in USABLE_ARTIFACT_STATUSES
            for item in state.get("artifacts", [])
        ):
            actions.append("creator.handoff.create")
        if status == "succeeded":
            actions.append("creator.workflow.continue")
            actions.append("creator.node.rerun")
        return actions

    @staticmethod
    def _event(
        event_type: str,
        *,
        action_id: str,
        stage_id: str,
        node_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "id": f"event-{uuid4().hex[:12]}",
            "type": event_type,
            "actionId": action_id,
            "stageId": stage_id,
            "nodeId": node_id,
            "payload": payload,
            "createdAt": now_iso(),
        }

    @staticmethod
    def _stage_status(statuses: list[str]) -> str:
        for status in (
            "running",
            "waiting_user",
            "changes_requested",
            "blocked",
            "failed",
            "stale",
        ):
            if status in statuses:
                return status
        if statuses and all(status in FINAL_NODE_STATUSES for status in statuses):
            return "succeeded" if "succeeded" in statuses else "skipped"
        return "pending"
