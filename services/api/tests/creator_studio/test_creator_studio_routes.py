import json
import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from vibe_visualization_api.config import Settings
from vibe_visualization_api.main import create_app


def wait_for_node(
    client: TestClient,
    headers: dict[str, str],
    run_id: str,
    *,
    stage_id: str,
    node_id: str,
    statuses: set[str],
    timeout: float = 2,
) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        snapshot = client.get(
            f"/api/creator-studio/runs/{run_id}", headers=headers
        ).json()
        node = next(
            node
            for stage in snapshot["stages"]
            if stage["id"] == stage_id
            for node in stage["nodes"]
            if node["id"] == node_id
        )
        if node["status"] in statuses:
            return snapshot
        time.sleep(0.01)
    raise AssertionError(f"node did not reach {sorted(statuses)}")


def creator_workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "creator-workspace"
    registry_path = (
        workspace
        / "configs"
        / "workflow"
        / "newma_creator_studio_registry.json"
    )
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(
        json.dumps(
            {
                "schema_version": "newma.creator_studio_registry.v1",
                "product": {
                    "id": "newma-creator-studio",
                    "name": "Newma Creator Studio",
                    "namespace": "newma",
                },
                "navigation": {"default_view": "dashboard"},
                "stages": [
                    {
                        "order": 1,
                        "id": "intake",
                        "name": "内容采集",
                        "nodes": [
                            {
                                "id": "source_setup",
                                "name": "来源配置",
                                "description": "配置来源",
                                "material_requirements": [
                                    {
                                        "type": "source",
                                        "label": "至少一个来源",
                                        "required": True,
                                        "accepts": ["url"],
                                        "sources": ["manual"],
                                    }
                                ],
                                "outputs": ["source_plan"],
                                "actions": ["run"],
                                "capabilities": ["browser_intake"],
                                "executor": "newma.test.executor",
                            },
                            {
                                "id": "collect",
                                "name": "采集入库",
                                "description": "采集来源",
                                "material_requirements": [
                                    {
                                        "type": "source_plan",
                                        "label": "来源计划",
                                        "required": True,
                                        "accepts": [".json"],
                                        "sources": ["upstream", "manual"],
                                    }
                                ],
                                "outputs": ["intake_records"],
                                "actions": ["run"],
                                "capabilities": ["web_capture"],
                                "executor": "newma.test.executor",
                            },
                        ],
                    },
                    {
                        "order": 2,
                        "id": "brief",
                        "name": "选题 Brief",
                        "nodes": [
                            {
                                "id": "topic_pool",
                                "name": "选题池",
                                "description": "生成选题",
                                "material_requirements": [],
                                "outputs": ["topic_cards"],
                                "actions": ["run"],
                                "capabilities": ["topic_generation"],
                                "executor": "newma.test.executor",
                            }
                        ],
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return workspace


def add_publish_stage(workspace: Path) -> None:
    registry_path = workspace / "configs" / "workflow" / "newma_creator_studio_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["stages"].append(
        {
            "order": 3,
            "id": "publish",
            "name": "发布",
            "nodes": [
                {
                    "id": "publish_preflight",
                    "name": "发布预检",
                    "material_requirements": [
                        {
                            "type": "execution_request",
                            "label": "发布请求",
                            "required": True,
                            "sources": ["upstream"],
                        }
                    ],
                    "outputs": ["publish_preflight_report"],
                    "actions": ["run"],
                    "capabilities": ["publish_guard"],
                    "executor": "newma.publish.preflight",
                    "gate": {"required": True},
                },
                {
                    "id": "publish_execute",
                    "name": "执行发布",
                    "material_requirements": [
                        {
                            "type": "publish_preflight_report",
                            "label": "发布预检",
                            "required": True,
                            "sources": ["upstream"],
                        }
                    ],
                    "outputs": ["publish_jobs", "platform_receipts"],
                    "actions": ["run"],
                    "capabilities": ["publish_cli"],
                    "executor": "newma.publish.execute",
                },
                {
                    "id": "receipt_verify",
                    "name": "回执验真",
                    "material_requirements": [
                        {
                            "type": "platform_receipts",
                            "label": "平台回执",
                            "required": True,
                            "sources": ["upstream"],
                        }
                    ],
                    "outputs": ["publish_verification_report", "postmortem_handoff"],
                    "actions": ["run"],
                    "capabilities": ["publish_verification"],
                    "executor": "newma.publish.verify",
                    "gate": {"required": True},
                },
            ],
        }
    )
    registry_path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")


def test_creator_runtime_startup_does_not_create_storage_until_used(tmp_path: Path):
    workspace = creator_workspace(tmp_path)
    database_path = tmp_path / "newma-desk.db"
    settings = Settings(
        runtime_dir=tmp_path / "runtime",
        database_path=database_path,
        creator_studio_workspace=workspace,
        creator_studio_dist=tmp_path / "missing-dist",
    )

    with TestClient(create_app(settings)):
        assert not database_path.exists()

    assert not database_path.exists()


def test_creator_commands_share_one_workspace_scoped_run_state(tmp_path: Path):
    workspace = creator_workspace(tmp_path)
    settings = Settings(
        runtime_dir=tmp_path / "runtime",
        database_path=tmp_path / "newma-desk.db",
        creator_studio_workspace=workspace,
        creator_studio_dist=tmp_path / "missing-dist",
    )
    headers = {"X-User-Id": "alice", "X-Workspace-Id": "creator-a"}

    with TestClient(create_app(settings)) as client:
        client.app.state.creator_studio_service.control_adapter.run_node = (
            lambda request, **_: {
                "execution_id": "execution-scope",
                "executor_id": "newma.test.executor",
                "status": "succeeded",
                "progress": 100,
                "artifacts": [],
            }
        )
        created = client.post(
            "/api/creator-studio/runs",
            headers=headers,
            json={
                "title": "共享创作任务",
                "stageId": "intake",
                "nodeId": "source_setup",
                "materials": [
                    {
                        "type": "source",
                        "path": "https://example.com/article",
                        "source": "manual",
                    }
                ],
            },
        )
        assert created.status_code == 201
        run_id = created.json()["run"]["runId"]

        executed = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.node.run",
                "stageId": "intake",
                "nodeId": "source_setup",
                "expectedRevision": 1,
            },
        )
        assert executed.status_code == 200
        assert executed.json()["stages"][0]["nodes"][0]["status"] == "queued"
        assert executed.json()["run"]["revision"] == 2

        completed = wait_for_node(
            client,
            headers,
            run_id,
            stage_id="intake",
            node_id="source_setup",
            statuses={"succeeded"},
        )
        assert completed["run"]["revision"] == 4

        isolated = client.get(
            "/api/creator-studio/runs",
            headers={"X-User-Id": "alice", "X-Workspace-Id": "creator-b"},
        )
        events = client.get(
            f"/api/creator-studio/runs/{run_id}/events?after=0",
            headers=headers,
        )

    assert isolated.status_code == 200
    assert isolated.json()["runs"] == []
    assert [event["type"] for event in events.json()["events"]] == [
        "run.created",
        "command.executed",
        "execution.started",
        "execution.finished",
    ]


def test_marketplace_preview_assets_are_served_only_from_creator_workspace(tmp_path: Path):
    workspace = creator_workspace(tmp_path)
    preview = workspace / "vendor" / "reserved" / "render" / "demo" / "preview.png"
    preview.parent.mkdir(parents=True)
    preview.write_bytes(b"preview-image")
    settings = Settings(
        runtime_dir=tmp_path / "runtime",
        database_path=tmp_path / "newma-desk.db",
        creator_studio_workspace=workspace,
        creator_studio_dist=tmp_path / "missing-dist",
    )

    with TestClient(create_app(settings)) as client:
        response = client.get(
            "/api/creator-studio/marketplace/assets/vendor/reserved/render/demo/preview.png"
        )
        missing = client.get(
            "/api/creator-studio/marketplace/assets/vendor/reserved/render/demo/missing.png"
        )

    assert response.status_code == 200
    assert response.content == b"preview-image"
    assert missing.status_code == 404


def test_marketplace_preset_is_checked_saved_and_applied_through_shared_run_control(tmp_path: Path):
    workspace = creator_workspace(tmp_path)
    settings = Settings(
        runtime_dir=tmp_path / "runtime",
        database_path=tmp_path / "newma-desk.db",
        creator_studio_workspace=workspace,
        creator_studio_dist=tmp_path / "missing-dist",
    )
    headers = {"X-User-Id": "alice", "X-Workspace-Id": "creator-a"}
    catalog = {
        "schema_version": "newma.creator_marketplace.v2",
        "projects": [
            {
                "id": "browser-intake",
                "kind": "project",
                "name": "Browser Intake",
                "version": "1.2.0",
                "stageIds": ["intake"],
                "capabilities": ["browser_intake"],
                "status": {"runtime": "available", "label": "可直接使用"},
            }
        ],
        "skills": [],
        "pipelines": [],
        "templates": [],
    }

    with TestClient(create_app(settings)) as client:
        client.app.state.creator_studio_service.control_adapter.marketplace = lambda: catalog
        checked = client.post(
            "/api/creator-studio/marketplace/compatibility",
            json={
                "itemId": "browser-intake",
                "itemKind": "project",
                "stageId": "intake",
                "nodeId": "source_setup",
            },
        )
        assert checked.status_code == 200
        assert checked.json()["canApply"] is True

        saved = client.post(
            "/api/creator-studio/marketplace/presets",
            headers=headers,
            json={
                "name": "新闻采集预设",
                "itemId": "browser-intake",
                "itemKind": "project",
                "stageId": "intake",
                "nodeId": "source_setup",
                "parameters": {"captureMode": "article"},
            },
        )
        assert saved.status_code == 201
        preset_id = saved.json()["presetId"]
        listed = client.get("/api/creator-studio/marketplace/presets", headers=headers)
        assert [item["presetId"] for item in listed.json()["presets"]] == [preset_id]

        updated = client.put(
            f"/api/creator-studio/marketplace/presets/{preset_id}",
            headers=headers,
            json={
                "name": "新闻采集预设",
                "stageId": "intake",
                "nodeId": "source_setup",
                "parameters": {"captureMode": "social"},
                "expectedVersion": 1,
            },
        )
        assert updated.status_code == 200
        assert updated.json()["version"] == 2
        versions = client.get(
            f"/api/creator-studio/marketplace/presets/{preset_id}/versions",
            headers=headers,
        )
        assert [item["version"] for item in versions.json()["versions"]] == [2, 1]
        stale = client.put(
            f"/api/creator-studio/marketplace/presets/{preset_id}",
            headers=headers,
            json={
                "name": "过期修改",
                "parameters": {},
                "expectedVersion": 1,
            },
        )
        assert stale.status_code == 409

        created = client.post(
            "/api/creator-studio/runs",
            headers=headers,
            json={
                "title": "Preset 绑定测试",
                "stageId": "intake",
                "nodeId": "source_setup",
                "materials": [
                    {"type": "source", "path": "https://example.com", "source": "manual"}
                ],
            },
        ).json()
        applied = client.post(
            f"/api/creator-studio/runs/{created['run']['runId']}/commands",
            headers=headers,
            json={
                "actionId": "creator.marketplace.apply-preset",
                "stageId": "intake",
                "nodeId": "source_setup",
                "input": {"presetId": preset_id, "presetVersion": 1},
                "expectedRevision": 1,
            },
        )
        assert applied.status_code == 200
        node = applied.json()["stages"][0]["nodes"][0]
        assert applied.json()["run"]["revision"] == 2
        assert node["parameters"]["captureMode"] == "article"
        assert node["parameters"]["marketplacePreset"]["presetId"] == preset_id
        assert node["parameters"]["marketplacePreset"]["presetVersion"] == 1

        latest = client.post(
            f"/api/creator-studio/runs/{created['run']['runId']}/commands",
            headers=headers,
            json={
                "actionId": "creator.marketplace.apply-preset",
                "stageId": "intake",
                "nodeId": "source_setup",
                "input": {"presetId": preset_id},
                "expectedRevision": 2,
            },
        )
        assert latest.status_code == 200
        latest_node = latest.json()["stages"][0]["nodes"][0]
        assert latest_node["parameters"]["captureMode"] == "social"
        assert latest_node["parameters"]["marketplacePreset"]["presetVersion"] == 2

        rejected = client.post(
            "/api/creator-studio/marketplace/compatibility",
            json={
                "itemId": "browser-intake",
                "itemKind": "project",
                "stageId": "brief",
                "nodeId": "topic_pool",
            },
        )
        assert rejected.status_code == 200
        assert rejected.json()["status"] == "incompatible"
        assert rejected.json()["canApply"] is False


def test_registered_executor_and_parameter_updates_share_the_same_revision_stream(tmp_path: Path):
    workspace = creator_workspace(tmp_path)
    registry_path = workspace / "configs" / "workflow" / "newma_creator_studio_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    registry["stages"][0]["nodes"][0]["executor"] = "newma.test.executor"
    registry_path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
    settings = Settings(
        runtime_dir=tmp_path / "runtime",
        database_path=tmp_path / "newma-desk.db",
        creator_studio_workspace=workspace,
        creator_studio_dist=tmp_path / "missing-dist",
    )
    headers = {"X-User-Id": "alice", "X-Workspace-Id": "creator-a"}

    with TestClient(create_app(settings)) as client:
        client.app.state.creator_studio_service.control_adapter.run_node = lambda request, **_: {
            "execution_id": "execution-test",
            "executor_id": "newma.test.executor",
            "status": "succeeded",
            "progress": 100,
            "exit_code": 0,
            "duration_ms": 12,
            "finished_at": "2026-08-15T00:00:00+00:00",
            "execution_result": "/tmp/execution_result.json",
            "logs": [{"at": "2026-08-15T00:00:00+00:00", "message": "真实执行完成"}],
            "artifacts": [{"type": "source_plan", "path": "/tmp/source_plan.json", "status": "created"}],
        }
        created = client.post(
            "/api/creator-studio/runs",
            headers=headers,
            json={
                "title": "双端执行测试",
                "stageId": "intake",
                "nodeId": "source_setup",
                "materials": [{"type": "source", "path": "https://example.com", "source": "manual"}],
            },
        ).json()
        run_id = created["run"]["runId"]
        configured = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.node.configure",
                "stageId": "intake",
                "nodeId": "source_setup",
                "input": {"parameters": {"lane": "vox_explainer"}, "replace": True},
                "expectedRevision": 1,
            },
        ).json()
        queued = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.node.run",
                "stageId": "intake",
                "nodeId": "source_setup",
                "expectedRevision": 2,
            },
        ).json()
        executed = wait_for_node(
            client,
            headers,
            run_id,
            stage_id="intake",
            node_id="source_setup",
            statuses={"succeeded"},
        )

    node = executed["stages"][0]["nodes"][0]
    assert configured["run"]["revision"] == 2
    assert queued["run"]["revision"] == 3
    assert queued["stages"][0]["nodes"][0]["status"] == "queued"
    assert node["parameters"] == {"lane": "vox_explainer"}
    assert node["status"] == "succeeded"
    assert node["executionResult"]["executorId"] == "newma.test.executor"
    assert node["artifacts"][0]["type"] == "source_plan"
    assert executed["run"]["revision"] == 5


def test_node_actions_follow_the_backend_state_contract(tmp_path: Path):
    settings = Settings(
        runtime_dir=tmp_path / "runtime",
        database_path=tmp_path / "newma-desk.db",
        creator_studio_workspace=creator_workspace(tmp_path),
        creator_studio_dist=tmp_path / "missing-dist",
    )
    headers = {"X-User-Id": "alice", "X-Workspace-Id": "creator-a"}

    with TestClient(create_app(settings)) as client:
        created = client.post(
            "/api/creator-studio/runs",
            headers=headers,
            json={
                "title": "动作契约测试",
                "stageId": "intake",
                "nodeId": "source_setup",
                "materials": [
                    {
                        "type": "source",
                        "path": "https://example.com",
                        "source": "manual",
                    }
                ],
            },
        ).json()
        run_id = created["run"]["runId"]
        node = created["stages"][0]["nodes"][0]

        assert "creator.node.run" in node["availableActions"]
        assert "creator.node.retry" not in node["availableActions"]
        assert "creator.node.approve" not in node["availableActions"]
        assert "creator.workflow.continue" not in node["availableActions"]

        for action_id in (
            "creator.node.retry",
            "creator.node.approve",
            "creator.workflow.continue",
        ):
            rejected = client.post(
                f"/api/creator-studio/runs/{run_id}/commands",
                headers=headers,
                json={
                    "actionId": action_id,
                    "stageId": "intake",
                    "nodeId": "source_setup",
                    "expectedRevision": 1,
                },
            )
            assert rejected.status_code == 422

        snapshot = client.get(
            f"/api/creator-studio/runs/{run_id}", headers=headers
        ).json()

    assert snapshot["run"]["revision"] == 1


def test_review_gate_actions_and_continue_use_one_revision_stream(tmp_path: Path):
    workspace = creator_workspace(tmp_path)
    registry_path = (
        workspace / "configs" / "workflow" / "newma_creator_studio_registry.json"
    )
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    source_node = registry["stages"][0]["nodes"][0]
    source_node["executor"] = "newma.test.review"
    source_node["gate"] = {"required": True, "kind": "human_review"}
    registry_path.write_text(
        json.dumps(registry, ensure_ascii=False), encoding="utf-8"
    )
    settings = Settings(
        runtime_dir=tmp_path / "runtime",
        database_path=tmp_path / "newma-desk.db",
        creator_studio_workspace=workspace,
        creator_studio_dist=tmp_path / "missing-dist",
    )
    headers = {"X-User-Id": "alice", "X-Workspace-Id": "creator-a"}

    with TestClient(create_app(settings)) as client:
        client.app.state.creator_studio_service.control_adapter.run_node = lambda request, **_: {
            "execution_id": "execution-review",
            "executor_id": "newma.test.review",
            "status": "succeeded",
            "progress": 100,
            "finished_at": "2026-08-15T00:00:00+00:00",
            "artifacts": [
                {
                    "type": "source_plan",
                    "path": "/tmp/source_plan.json",
                    "status": "created",
                }
            ],
        }
        created = client.post(
            "/api/creator-studio/runs",
            headers=headers,
            json={
                "title": "审核契约测试",
                "stageId": "intake",
                "nodeId": "source_setup",
                "materials": [
                    {
                        "type": "source",
                        "path": "https://example.com",
                        "source": "manual",
                    }
                ],
            },
        ).json()
        run_id = created["run"]["runId"]
        queued = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.node.run",
                "stageId": "intake",
                "nodeId": "source_setup",
                "expectedRevision": 1,
            },
        ).json()
        assert queued["stages"][0]["nodes"][0]["status"] == "queued"
        waiting = wait_for_node(
            client,
            headers,
            run_id,
            stage_id="intake",
            node_id="source_setup",
            statuses={"waiting_user"},
        )
        waiting_node = waiting["stages"][0]["nodes"][0]
        assert waiting_node["status"] == "waiting_user"
        assert "creator.node.approve" in waiting_node["availableActions"]
        assert "creator.node.request-changes" in waiting_node["availableActions"]
        assert "creator.workflow.continue" not in waiting_node["availableActions"]

        approved = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.node.approve",
                "stageId": "intake",
                "nodeId": "source_setup",
                "expectedRevision": waiting["run"]["revision"],
            },
        ).json()
        approved_node = approved["stages"][0]["nodes"][0]
        assert approved_node["status"] == "succeeded"
        assert "creator.workflow.continue" in approved_node["availableActions"]

        continued = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.workflow.continue",
                "stageId": "intake",
                "nodeId": "source_setup",
                "expectedRevision": approved["run"]["revision"],
            },
        ).json()

    assert continued["run"]["revision"] == approved["run"]["revision"] + 1
    assert continued["run"]["activeNodeId"] == "collect"


def test_execution_job_can_be_cancelled_and_retried(tmp_path: Path):
    settings = Settings(
        runtime_dir=tmp_path / "runtime",
        database_path=tmp_path / "newma-desk.db",
        creator_studio_workspace=creator_workspace(tmp_path),
        creator_studio_dist=tmp_path / "missing-dist",
    )
    headers = {"X-User-Id": "alice", "X-Workspace-Id": "creator-a"}
    started = threading.Event()

    def slow_execution(request, *, cancel_event=None):
        started.set()
        assert cancel_event is not None
        cancel_event.wait(2)
        return {"status": "cancelled", "progress": 10, "artifacts": []}

    with TestClient(create_app(settings)) as client:
        client.app.state.creator_studio_service.control_adapter.run_node = slow_execution
        created = client.post(
            "/api/creator-studio/runs",
            headers=headers,
            json={
                "title": "取消测试",
                "stageId": "intake",
                "nodeId": "source_setup",
                "materials": [
                    {"type": "source", "path": "https://example.com", "source": "manual"}
                ],
            },
        ).json()
        run_id = created["run"]["runId"]
        client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.node.run",
                "stageId": "intake",
                "nodeId": "source_setup",
                "expectedRevision": 1,
            },
        )
        assert started.wait(1)
        running = wait_for_node(
            client,
            headers,
            run_id,
            stage_id="intake",
            node_id="source_setup",
            statuses={"running"},
        )
        cancelled = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.node.cancel",
                "stageId": "intake",
                "nodeId": "source_setup",
                "expectedRevision": running["run"]["revision"],
            },
        )
        assert cancelled.status_code == 200
        final = wait_for_node(
            client,
            headers,
            run_id,
            stage_id="intake",
            node_id="source_setup",
            statuses={"cancelled"},
        )
        jobs = client.get(
            f"/api/creator-studio/runs/{run_id}/jobs", headers=headers
        ).json()["jobs"]

    node = final["stages"][0]["nodes"][0]
    assert "creator.node.retry" in node["availableActions"]
    assert jobs[0]["status"] == "cancelled"
    assert jobs[0]["cancelRequested"] is True


def test_editor_session_launch_and_save_share_creator_command_interface(tmp_path: Path):
    workspace = creator_workspace(tmp_path)
    registry_path = workspace / "configs" / "workflow" / "newma_creator_studio_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    source_node = registry["stages"][0]["nodes"][0]
    source_node["editors"] = ["storyboard_editor"]
    registry_path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
    settings = Settings(
        runtime_dir=tmp_path / "runtime",
        database_path=tmp_path / "newma-desk.db",
        creator_studio_workspace=workspace,
        creator_studio_dist=tmp_path / "missing-dist",
    )
    headers = {"X-User-Id": "alice", "X-Workspace-Id": "creator-a"}

    with TestClient(create_app(settings)) as client:
        service = client.app.state.creator_studio_service
        service.control_adapter.run_node = lambda request, **_: {
            "execution_id": "execution-editor",
            "executor_id": "newma.test.executor",
            "status": "waiting_user",
            "progress": 100,
            "artifacts": [],
            "result": {
                "kind": "editor_session",
                "editor_session": {
                    "session_id": "editor-session-test",
                    "status": "ready",
                    "editors": [
                        {
                            "id": "storyboard_editor",
                            "name": "分镜编辑器",
                            "kind": "internal",
                            "status": "available",
                        }
                    ],
                    "input_artifacts": [],
                    "output_contract": ["source_plan"],
                },
            },
        }
        service.control_adapter.launch_editor = lambda request: {
            "status": "open",
            "kind": "internal",
            "launch_url": "http://127.0.0.1/editor",
        }
        created = client.post(
            "/api/creator-studio/runs",
            headers=headers,
            json={
                "title": "编辑会话测试",
                "stageId": "intake",
                "nodeId": "source_setup",
                "materials": [
                    {"type": "source", "path": "https://example.com", "source": "manual"}
                ],
            },
        ).json()
        run_id = created["run"]["runId"]
        client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.node.run",
                "stageId": "intake",
                "nodeId": "source_setup",
                "expectedRevision": 1,
            },
        )
        waiting = wait_for_node(
            client,
            headers,
            run_id,
            stage_id="intake",
            node_id="source_setup",
            statuses={"waiting_user"},
        )
        waiting_node = waiting["stages"][0]["nodes"][0]
        assert waiting_node["editorSession"]["sessionId"] == "editor-session-test"
        opened = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.editor.launch",
                "stageId": "intake",
                "nodeId": "source_setup",
                "input": {"editorId": "storyboard_editor"},
                "expectedRevision": waiting["run"]["revision"],
            },
        ).json()
        opened_node = opened["stages"][0]["nodes"][0]
        assert opened_node["editorSession"]["status"] == "open"
        assert opened_node["editorSession"]["launch"]["launchUrl"].endswith("/editor")
        saved = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.editor.save",
                "stageId": "intake",
                "nodeId": "source_setup",
                "input": {
                    "outputs": [
                        {"type": "source_plan", "path": "/tmp/source-plan.json"}
                    ]
                },
                "expectedRevision": opened["run"]["revision"],
            },
        ).json()
        sessions = client.get(
            f"/api/creator-studio/runs/{run_id}/editor-sessions",
            headers=headers,
        ).json()["sessions"]

    node = saved["stages"][0]["nodes"][0]
    assert node["status"] == "succeeded"
    assert node["artifacts"][-1]["editorSessionId"] == "editor-session-test"
    assert sessions[0]["status"] == "saved"


def test_publish_execution_requires_fresh_confirmation_for_each_attempt(tmp_path: Path):
    workspace = creator_workspace(tmp_path)
    add_publish_stage(workspace)
    settings = Settings(
        runtime_dir=tmp_path / "runtime",
        database_path=tmp_path / "newma-desk.db",
        creator_studio_workspace=workspace,
        creator_studio_dist=tmp_path / "missing-dist",
    )
    headers = {"X-User-Id": "alice", "X-Workspace-Id": "creator-a"}
    attempts = 0

    def publish(request: dict, **_: object) -> dict:
        nonlocal attempts
        attempts += 1
        confirmation = request["parameters"]["publishConfirmation"]
        assert confirmation["confirmationText"] == "确认发布"
        assert confirmation["consumedByJobId"] == request["job_id"]
        if attempts == 1:
            return {
                "execution_id": "publish-failed",
                "executor_id": "newma.publish.execute",
                "status": "blocked",
                "progress": 0,
                "artifacts": [],
                "result": {
                    "kind": "publish_execute",
                    "status": "partially_failed",
                    "succeeded": 0,
                    "failed": 1,
                    "receipts": "/tmp/receipts-failed.json",
                },
            }
        return {
            "execution_id": "publish-succeeded",
            "executor_id": "newma.publish.execute",
            "status": "succeeded",
            "progress": 100,
            "artifacts": [
                {"type": "platform_receipts", "path": "/tmp/receipts.json"}
            ],
            "result": {
                "kind": "publish_execute",
                "status": "recorded",
                "succeeded": 1,
                "failed": 0,
                "receipts": "/tmp/receipts.json",
            },
        }

    with TestClient(create_app(settings)) as client:
        client.app.state.creator_studio_service.control_adapter.run_node = publish
        created = client.post(
            "/api/creator-studio/runs",
            headers=headers,
            json={
                "title": "发布确认测试",
                "stageId": "publish",
                "nodeId": "publish_execute",
                "materials": [
                    {
                        "type": "publish_preflight_report",
                        "path": "/tmp/preflight.json",
                        "source": "manual",
                    }
                ],
            },
        ).json()
        run_id = created["run"]["runId"]
        node = created["stages"][2]["nodes"][1]
        assert "creator.publish.confirm" in node["availableActions"]
        assert "creator.node.run" not in node["availableActions"]

        rejected = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.node.run",
                "stageId": "publish",
                "nodeId": "publish_execute",
                "expectedRevision": created["run"]["revision"],
            },
        )
        assert rejected.status_code == 422

        confirmed = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.publish.confirm",
                "stageId": "publish",
                "nodeId": "publish_execute",
                "input": {"confirmed": True, "confirmationText": "确认发布"},
                "expectedRevision": created["run"]["revision"],
            },
        ).json()
        confirmed_node = confirmed["stages"][2]["nodes"][1]
        assert "creator.node.run" in confirmed_node["availableActions"]
        assert "creator.publish.confirm" not in confirmed_node["availableActions"]

        client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.node.run",
                "stageId": "publish",
                "nodeId": "publish_execute",
                "expectedRevision": confirmed["run"]["revision"],
            },
        )
        blocked = wait_for_node(
            client,
            headers,
            run_id,
            stage_id="publish",
            node_id="publish_execute",
            statuses={"blocked"},
        )
        blocked_node = blocked["stages"][2]["nodes"][1]
        assert blocked["publishState"]["execution"]["failed"] == 1
        assert "creator.publish.confirm" in blocked_node["availableActions"]
        assert "creator.node.retry" not in blocked_node["availableActions"]

        reconfirmed = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.publish.confirm",
                "stageId": "publish",
                "nodeId": "publish_execute",
                "input": {"confirmed": True, "confirmationText": "确认发布"},
                "expectedRevision": blocked["run"]["revision"],
            },
        ).json()
        assert "creator.node.retry" in reconfirmed["stages"][2]["nodes"][1]["availableActions"]
        client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.node.retry",
                "stageId": "publish",
                "nodeId": "publish_execute",
                "expectedRevision": reconfirmed["run"]["revision"],
            },
        )
        succeeded = wait_for_node(
            client,
            headers,
            run_id,
            stage_id="publish",
            node_id="publish_execute",
            statuses={"succeeded"},
        )

    assert attempts == 2
    assert succeeded["publishState"]["execution"]["status"] == "recorded"
    assert succeeded["publishState"]["execution"]["succeeded"] == 1
    assert succeeded["publishState"]["confirmation"]["consumedByJobId"]


def test_publish_preflight_and_verification_are_visible_and_reviewable(tmp_path: Path):
    workspace = creator_workspace(tmp_path)
    add_publish_stage(workspace)
    settings = Settings(
        runtime_dir=tmp_path / "runtime",
        database_path=tmp_path / "newma-desk.db",
        creator_studio_workspace=workspace,
        creator_studio_dist=tmp_path / "missing-dist",
    )
    headers = {"X-User-Id": "alice", "X-Workspace-Id": "creator-a"}

    def execute(request: dict, **_: object) -> dict:
        if request["node_id"] == "publish_preflight":
            return {
                "execution_id": "preflight-ok",
                "executor_id": "newma.publish.preflight",
                "status": "succeeded",
                "progress": 100,
                "artifacts": [
                    {"type": "publish_preflight_report", "path": "/tmp/preflight.json"}
                ],
                "result": {
                    "kind": "publish_preflight",
                    "status": "ready_for_confirmation",
                    "taskCount": 2,
                    "blockers": [],
                    "warnings": [{"kind": "account", "status": "state_present_unverified"}],
                    "accountHealth": {
                        "accounts": [
                            {"channel": "wechat", "slot": "default", "label": "公众号", "status": "available"}
                        ]
                    },
                    "report": "/tmp/preflight.json",
                },
            }
        return {
            "execution_id": "verify-ok",
            "executor_id": "newma.publish.verify",
            "status": "succeeded",
            "progress": 100,
            "artifacts": [
                {"type": "postmortem_handoff", "path": "/tmp/postmortem.json"}
            ],
            "result": {
                "kind": "publish_verify",
                "status": "ready",
                "verificationCount": 1,
                "failures": [],
                "postmortemHandoff": "/tmp/postmortem.json",
            },
        }

    with TestClient(create_app(settings)) as client:
        client.app.state.creator_studio_service.control_adapter.run_node = execute
        preflight_run = client.post(
            "/api/creator-studio/runs",
            headers=headers,
            json={
                "title": "发布预检测试",
                "stageId": "publish",
                "nodeId": "publish_preflight",
                "materials": [
                    {"type": "execution_request", "path": "/tmp/request.json", "source": "manual"}
                ],
            },
        ).json()
        preflight_id = preflight_run["run"]["runId"]
        client.post(
            f"/api/creator-studio/runs/{preflight_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.node.run",
                "stageId": "publish",
                "nodeId": "publish_preflight",
                "expectedRevision": preflight_run["run"]["revision"],
            },
        )
        waiting_preflight = wait_for_node(
            client,
            headers,
            preflight_id,
            stage_id="publish",
            node_id="publish_preflight",
            statuses={"waiting_user"},
        )
        assert waiting_preflight["publishState"]["preflight"]["taskCount"] == 2
        assert waiting_preflight["publishState"]["preflight"]["accountHealth"]["accounts"][0]["status"] == "available"
        approved = client.post(
            f"/api/creator-studio/runs/{preflight_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.node.approve",
                "stageId": "publish",
                "nodeId": "publish_preflight",
                "expectedRevision": waiting_preflight["run"]["revision"],
            },
        ).json()
        assert approved["publishState"]["preflight"]["nodeStatus"] == "succeeded"

        verify_run = client.post(
            "/api/creator-studio/runs",
            headers=headers,
            json={
                "title": "回执验真测试",
                "stageId": "publish",
                "nodeId": "receipt_verify",
                "materials": [
                    {"type": "platform_receipts", "path": "/tmp/receipts.json", "source": "manual"}
                ],
            },
        ).json()
        verify_id = verify_run["run"]["runId"]
        client.post(
            f"/api/creator-studio/runs/{verify_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.node.run",
                "stageId": "publish",
                "nodeId": "receipt_verify",
                "expectedRevision": verify_run["run"]["revision"],
            },
        )
        waiting_verify = wait_for_node(
            client,
            headers,
            verify_id,
            stage_id="publish",
            node_id="receipt_verify",
            statuses={"waiting_user"},
        )

    assert waiting_verify["publishState"]["verification"]["verificationCount"] == 1
    assert waiting_verify["publishState"]["verification"]["postmortemHandoff"] == "/tmp/postmortem.json"


def test_artifact_versions_and_stale_state_propagate_through_handoffs(tmp_path: Path):
    workspace = creator_workspace(tmp_path)
    first_source = tmp_path / "source-plan-v1.json"
    first_source.write_text('{"version": 1}', encoding="utf-8")
    second_source = tmp_path / "source-plan-v2.json"
    second_source.write_text('{"version": 2}', encoding="utf-8")
    collected = tmp_path / "intake-records.json"
    collected.write_text('{"records": 1}', encoding="utf-8")
    settings = Settings(
        runtime_dir=tmp_path / "runtime",
        database_path=tmp_path / "newma-desk.db",
        creator_studio_workspace=workspace,
        creator_studio_dist=tmp_path / "missing-dist",
    )
    headers = {"X-User-Id": "alice", "X-Workspace-Id": "creator-a"}

    with TestClient(create_app(settings)) as client:
        client.app.state.creator_studio_service.control_adapter.run_node = (
            lambda request, **_: {
                "execution_id": "lineage-source-v1",
                "executor_id": "newma.test.executor",
                "status": "succeeded",
                "progress": 100,
                "artifacts": [
                    {"type": "source_plan", "path": str(first_source), "status": "created"}
                ],
            }
        )
        created = client.post(
            "/api/creator-studio/runs",
            headers=headers,
            json={
                "title": "Artifact Lineage 测试",
                "stageId": "intake",
                "nodeId": "source_setup",
                "materials": [
                    {"type": "source", "path": "https://example.com", "source": "manual"}
                ],
            },
        ).json()
        run_id = created["run"]["runId"]
        client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.node.run",
                "stageId": "intake",
                "nodeId": "source_setup",
                "expectedRevision": created["run"]["revision"],
            },
        )
        completed = wait_for_node(
            client,
            headers,
            run_id,
            stage_id="intake",
            node_id="source_setup",
            statuses={"succeeded"},
        )
        source_artifact = completed["stages"][0]["nodes"][0]["artifacts"][0]
        assert source_artifact["version"] == 1
        assert len(source_artifact["contentDigest"]) == 64
        assert source_artifact["producerJobId"]

        first_handoff = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.handoff.create",
                "stageId": "intake",
                "nodeId": "source_setup",
                "input": {
                    "targetStageId": "intake",
                    "targetNodeId": "collect",
                    "artifactIds": [source_artifact["id"]],
                },
                "expectedRevision": completed["run"]["revision"],
            },
        ).json()
        collect_node = first_handoff["stages"][0]["nodes"][1]
        assert collect_node["materials"][0]["artifactVersion"] == 1
        assert first_handoff["handoffs"][0]["artifactRefs"][0]["version"] == 1

        collected_snapshot = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.artifact.register",
                "stageId": "intake",
                "nodeId": "collect",
                "input": {"type": "intake_records", "path": str(collected)},
                "expectedRevision": first_handoff["run"]["revision"],
            },
        ).json()
        collect_artifact = collected_snapshot["stages"][0]["nodes"][1]["artifacts"][0]
        assert collect_artifact["parents"][0]["artifactId"] == source_artifact["id"]

        second_handoff = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.handoff.create",
                "stageId": "intake",
                "nodeId": "collect",
                "input": {
                    "targetStageId": "brief",
                    "targetNodeId": "topic_pool",
                    "artifactIds": [collect_artifact["id"]],
                },
                "expectedRevision": collected_snapshot["run"]["revision"],
            },
        ).json()

        replaced = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.artifact.register",
                "stageId": "intake",
                "nodeId": "source_setup",
                "input": {"type": "source_plan", "path": str(second_source)},
                "expectedRevision": second_handoff["run"]["revision"],
            },
        ).json()
        source_artifacts = replaced["stages"][0]["nodes"][0]["artifacts"]
        stale_collect = replaced["stages"][0]["nodes"][1]
        stale_topic = replaced["stages"][1]["nodes"][0]
        assert [item["version"] for item in source_artifacts] == [1, 2]
        assert source_artifacts[0]["status"] == "superseded"
        assert stale_collect["status"] == "stale"
        assert stale_collect["materialValidation"]["status"] == "needs_material"
        assert stale_collect["artifacts"][0]["status"] == "stale"
        assert stale_topic["status"] == "stale"
        assert all(item["status"] == "stale" for item in replaced["handoffs"])
        assert {item["nodeId"] for item in replaced["lineageState"]["affectedNodes"]} == {
            "collect",
            "topic_pool",
        }

        refreshed = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.handoff.create",
                "stageId": "intake",
                "nodeId": "source_setup",
                "input": {
                    "targetStageId": "intake",
                    "targetNodeId": "collect",
                    "artifactIds": [source_artifacts[1]["id"]],
                },
                "expectedRevision": replaced["run"]["revision"],
            },
        ).json()

    refreshed_collect = refreshed["stages"][0]["nodes"][1]
    assert refreshed_collect["status"] == "pending"
    assert refreshed_collect["materialValidation"]["status"] == "ready"
    assert refreshed_collect["materials"][0]["artifactVersion"] == 2
    assert refreshed["handoffs"][-1]["status"] == "ready"
