import json
import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from vibe_visualization_api.config import Settings
from vibe_visualization_api.creator_studio.adapter import CreatorControlAdapter
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


def test_creator_agent_check_passes_cli_args_without_http_error(tmp_path: Path):
    workspace = tmp_path / "creator-workspace"
    script = workspace / "scripts" / "newma_creator_control.py"
    script.parent.mkdir(parents=True)
    script.write_text(
        "import json, sys\n"
        "print(json.dumps({'status': 'succeeded', 'args': sys.argv[1:]}))\n",
        encoding="utf-8",
    )

    result = CreatorControlAdapter(workspace).test_agent(
        "codex",
        "/tmp/custom-codex",
    )

    assert result["status"] == "succeeded"
    assert result["args"][0] == "invoke-cli"
    assert "--agent" in result["args"]
    assert "--bin-override" in result["args"]


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

        # 单机单用户模式：身份统一归一，不同 header（shell UI 随机身份）
        # 与 Agent/CLI 直连共享同一份数据
        shared = client.get(
            "/api/creator-studio/runs",
            headers={"X-User-Id": "alice", "X-Workspace-Id": "creator-b"},
        )
        events = client.get(
            f"/api/creator-studio/runs/{run_id}/events?after=0",
            headers=headers,
        )

    assert shared.status_code == 200
    assert [r["runId"] for r in shared.json()["runs"]] == [run_id]
    assert [event["type"] for event in events.json()["events"]] == [
        "run.created",
        "command.executed",
        "execution.started",
        "execution.finished",
    ]


def test_reconcile_external_products_registers_artifacts_and_completes_node(tmp_path: Path):
    workspace = creator_workspace(tmp_path)
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    source_plan = tmp_path / "source_plan.json"
    source_plan.write_text('{"sources": []}', encoding="utf-8")
    settings = Settings(
        runtime_dir=tmp_path / "runtime",
        database_path=tmp_path / "newma-desk.db",
        creator_studio_workspace=workspace,
        creator_studio_dist=tmp_path / "missing-dist",
    )
    headers = {"X-User-Id": "alice", "X-Workspace-Id": "creator-a"}

    with TestClient(create_app(settings)) as client:
        created = client.post(
            "/api/creator-studio/runs",
            headers=headers,
            json={
                "title": "外部产物回写",
                "stageId": "intake",
                "nodeId": "source_setup",
                "materials": [
                    {"type": "source", "path": str(source), "source": "manual"}
                ],
            },
        ).json()
        run_id = created["run"]["runId"]
        reconciled = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.node.reconcile",
                "stageId": "intake",
                "nodeId": "source_setup",
                "expectedRevision": created["run"]["revision"],
                "input": {
                    "outputs": [
                        {
                            "type": "source_plan",
                            "path": str(source_plan),
                            "label": "来源计划",
                        }
                    ]
                },
            },
        )

    assert reconciled.status_code == 200
    snapshot = reconciled.json()
    node = snapshot["stages"][0]["nodes"][0]
    assert node["status"] == "succeeded"
    assert node["artifacts"][-1]["type"] == "source_plan"
    assert snapshot["run"]["activeNodeId"] == "collect"


def test_reconcile_external_products_rejects_missing_declared_outputs(tmp_path: Path):
    workspace = creator_workspace(tmp_path)
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    wrong = tmp_path / "wrong.json"
    wrong.write_text("{}", encoding="utf-8")
    settings = Settings(
        runtime_dir=tmp_path / "runtime",
        database_path=tmp_path / "newma-desk.db",
        creator_studio_workspace=workspace,
        creator_studio_dist=tmp_path / "missing-dist",
    )
    headers = {"X-User-Id": "alice", "X-Workspace-Id": "creator-a"}

    with TestClient(create_app(settings)) as client:
        created = client.post(
            "/api/creator-studio/runs",
            headers=headers,
            json={
                "title": "错误回写",
                "stageId": "intake",
                "nodeId": "source_setup",
                "materials": [
                    {"type": "source", "path": str(source), "source": "manual"}
                ],
            },
        ).json()
        response = client.post(
            f"/api/creator-studio/runs/{created['run']['runId']}/commands",
            headers=headers,
            json={
                "actionId": "creator.node.reconcile",
                "stageId": "intake",
                "nodeId": "source_setup",
                "expectedRevision": created["run"]["revision"],
                "input": {"outputs": [{"type": "wrong_type", "path": str(wrong)}]},
            },
        )

    assert response.status_code == 422
    assert "undeclared artifact type" in response.json()["detail"]


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
                            "agent_bridge": {
                                "kind": "mcp",
                                "endpoint": "http://127.0.0.1:5199/api/external-mcp/mcp",
                                "protocol": "openchatcut.edit-session.v1",
                                "approval_modes": ["manual", "auto"],
                            },
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
        agent_started = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.editor.start-agent",
                "stageId": "intake",
                "nodeId": "source_setup",
                "input": {
                    "editorId": "storyboard_editor",
                    "approvalMode": "manual",
                    "prompt": "按分镜完成粗剪",
                },
                "expectedRevision": opened["run"]["revision"],
            },
        ).json()
        assert agent_started["stages"][0]["nodes"][0]["editorSession"]["status"] == "agent_editing"
        reviewed = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.editor.review-proposal",
                "stageId": "intake",
                "nodeId": "source_setup",
                "input": {
                    "externalEditSessionId": "occ-edit-1",
                    "summary": "删除停顿并重排字幕",
                    "changeCount": 3,
                    "decision": "applied",
                    "note": "已在编辑器审核",
                },
                "expectedRevision": agent_started["run"]["revision"],
            },
        ).json()
        assert reviewed["stages"][0]["nodes"][0]["editorSession"]["collaboration"]["proposal"]["status"] == "applied"
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
                "expectedRevision": reviewed["run"]["revision"],
            },
        ).json()
        templated = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.editor.save-template",
                "stageId": "intake",
                "nodeId": "source_setup",
                "input": {
                    "templateId": "occ-template-1",
                    "name": "粗剪模板",
                    "sourceAction": "manage_template.save",
                },
                "expectedRevision": saved["run"]["revision"],
            },
        ).json()
        sessions = client.get(
            f"/api/creator-studio/runs/{run_id}/editor-sessions",
            headers=headers,
        ).json()["sessions"]
        presets = client.get(
            "/api/creator-studio/marketplace/presets",
            headers=headers,
        ).json()["presets"]

    node = templated["stages"][0]["nodes"][0]
    assert node["status"] == "succeeded"
    assert node["artifacts"][-1]["editorSessionId"] == "editor-session-test"
    assert sessions[0]["status"] == "saved"
    assert sessions[0]["savedTemplates"][0]["templateId"] == "occ-template-1"
    assert sessions[0]["savedTemplates"][0]["sourceAction"] == "manage_template.save"
    assert presets[0]["parameters"]["templateId"] == "occ-template-1"
    assert presets[0]["parameters"]["sourceVerification"] == "editor_returned"


def test_openchatcut_project_binding_and_export_import(tmp_path: Path):
    workspace = creator_workspace(tmp_path)
    registry_path = workspace / "configs" / "workflow" / "newma_creator_studio_registry.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    source_node = registry["stages"][0]["nodes"][0]
    source_node["editors"] = ["openchatcut"]
    registry_path.write_text(json.dumps(registry, ensure_ascii=False), encoding="utf-8")
    settings = Settings(
        runtime_dir=tmp_path / "runtime",
        database_path=tmp_path / "newma-desk.db",
        creator_studio_workspace=workspace,
        creator_studio_dist=tmp_path / "missing-dist",
    )
    headers = {"X-User-Id": "alice", "X-Workspace-Id": "creator-a"}
    edited_master = tmp_path / "edited-master.mp4"
    edit_decisions = tmp_path / "edit-decisions.json"
    timeline_exchange = tmp_path / "timeline-exchange.json"
    edited_master.write_bytes(b"video")
    edit_decisions.write_text("{}", encoding="utf-8")
    timeline_exchange.write_text("{}", encoding="utf-8")

    with TestClient(create_app(settings)) as client:
        service = client.app.state.creator_studio_service
        service.control_adapter.run_node = lambda request, **_: {
            "execution_id": "execution-openchatcut",
            "executor_id": "newma.test.executor",
            "status": "waiting_user",
            "progress": 100,
            "artifacts": [],
            "result": {
                "kind": "editor_session",
                "editor_session": {
                    "session_id": "editor-openchatcut-test",
                    "status": "ready",
                    "editors": [
                        {
                            "id": "openchatcut",
                            "name": "OpenChatCut",
                            "kind": "local_web",
                            "status": "available",
                            "launch_url": "http://127.0.0.1:5199",
                            "agent_bridge": {
                                "kind": "mcp",
                                "endpoint": "http://127.0.0.1:5199/api/external-mcp/mcp",
                                "protocol": "openchatcut.edit-session.v1",
                                "approval_modes": ["manual"],
                            },
                        }
                    ],
                    "input_artifacts": [],
                    "output_contract": [
                        "edited_master",
                        "edit_decisions",
                        "timeline_exchange",
                    ],
                },
            },
        }
        service.control_adapter.launch_editor = lambda request: {
            "status": "open",
            "kind": "local_web",
            "launch_url": "http://127.0.0.1:5199",
        }
        service.control_adapter.import_editor_export = lambda request: {
            "status": "succeeded",
            "render_id": "render-1",
            "outputs": [
                {"type": "edited_master", "path": str(edited_master)},
                {"type": "edit_decisions", "path": str(edit_decisions)},
                {"type": "timeline_exchange", "path": str(timeline_exchange)},
            ],
        }
        created = client.post(
            "/api/creator-studio/runs",
            headers=headers,
            json={
                "title": "OpenChatCut 回写测试",
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
        waiting = wait_for_node(
            client,
            headers,
            run_id,
            stage_id="intake",
            node_id="source_setup",
            statuses={"waiting_user"},
        )
        opened = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.editor.launch",
                "stageId": "intake",
                "nodeId": "source_setup",
                "input": {
                    "editorId": "openchatcut",
                    "externalProjectId": "occ-project-42",
                },
                "expectedRevision": waiting["run"]["revision"],
            },
        ).json()
        opened_session = opened["stages"][0]["nodes"][0]["editorSession"]
        assert opened_session["externalProject"]["projectId"] == "occ-project-42"
        assert opened_session["launch"]["launchUrl"].endswith("#/editor/occ-project-42")
        agent_started = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.editor.start-agent",
                "stageId": "intake",
                "nodeId": "source_setup",
                "input": {
                    "editorId": "openchatcut",
                    "externalProjectId": "occ-project-42",
                    "prompt": "完成粗剪",
                },
                "expectedRevision": opened["run"]["revision"],
            },
        ).json()
        started_collaboration = agent_started["stages"][0]["nodes"][0][
            "editorSession"
        ]["collaboration"]
        assert started_collaboration["reviewDeadlineAt"] is None
        submitted = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.editor.submit-proposal",
                "stageId": "intake",
                "nodeId": "source_setup",
                "input": {
                    "externalProjectId": "occ-project-42",
                    "externalEditSessionId": "occ-edit-42",
                    "summary": "完成粗剪与字幕校正",
                    "changeCount": 4,
                },
                "expectedRevision": agent_started["run"]["revision"],
            },
        ).json()
        assert submitted["stages"][0]["nodes"][0]["editorSession"][
            "collaboration"
        ]["reviewDeadlineAt"]
        reviewed = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.editor.review-proposal",
                "stageId": "intake",
                "nodeId": "source_setup",
                "input": {
                    "externalProjectId": "occ-project-42",
                    "externalEditSessionId": "occ-edit-42",
                    "summary": "完成粗剪与字幕校正",
                    "changeCount": 4,
                    "decision": "rejected",
                },
                "expectedRevision": submitted["run"]["revision"],
            },
        ).json()
        imported_response = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.editor.import-export",
                "stageId": "intake",
                "nodeId": "source_setup",
                "input": {
                    "externalProjectId": "occ-project-42",
                    "downloadUrl": "/media/uploads/export.mp4",
                    "renderId": "render-1",
                },
                "expectedRevision": reviewed["run"]["revision"],
            },
        )
        assert imported_response.status_code == 200, imported_response.text
        imported = imported_response.json()
        sessions = client.get(
            f"/api/creator-studio/runs/{run_id}/editor-sessions",
            headers=headers,
        ).json()["sessions"]

    node = imported["stages"][0]["nodes"][0]
    assert node["status"] == "succeeded"
    assert {item["type"] for item in node["artifacts"]} == {
        "edited_master",
        "edit_decisions",
        "timeline_exchange",
    }
    assert sessions[0]["externalProject"]["projectId"] == "occ-project-42"
    assert sessions[0]["outputArtifacts"][0]["type"] == "edited_master"


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
        # 自动转接（执行成功/approve 联动）与手动 handoff 并存时：
        # 旧 handoff 可能因重复转接转 superseded，也可能因上游替换转 stale——两者都是失效态
        assert all(
            item["status"] in {"stale", "superseded"} for item in replaced["handoffs"]
        )
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


def test_review_gate_approval_rejects_node_with_unsatisfied_materials(tmp_path: Path):
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
        client.app.state.creator_studio_service.control_adapter.run_node = (
            lambda request, **_: {
                "execution_id": "execution-review-materials",
                "executor_id": "newma.test.review",
                "status": "succeeded",
                "progress": 100,
                "finished_at": "2026-08-15T00:00:00+00:00",
                "artifacts": [],
            }
        )
        created = client.post(
            "/api/creator-studio/runs",
            headers=headers,
            json={
                "title": "素材失效后审批必须被拒绝",
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

        # 模拟运行后素材要求不再满足（例如上游交付物失效）。
        stale_registry = json.loads(registry_path.read_text(encoding="utf-8"))
        stale_registry["stages"][0]["nodes"][0]["material_requirements"].append(
            {
                "type": "evidence_pack",
                "label": "证据包",
                "required": True,
                "accepts": [".md"],
                "sources": ["upstream"],
            }
        )
        registry_path.write_text(
            json.dumps(stale_registry, ensure_ascii=False), encoding="utf-8"
        )

        rejected = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.node.approve",
                "stageId": "intake",
                "nodeId": "source_setup",
                "expectedRevision": waiting["run"]["revision"],
            },
        )
        snapshot = client.get(
            f"/api/creator-studio/runs/{run_id}", headers=headers
        ).json()

    assert rejected.status_code == 422
    assert snapshot["stages"][0]["nodes"][0]["status"] == "waiting_user"


def test_approve_syncs_pending_review_artifact_file_to_approved(tmp_path: Path):
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

    artifact_path = tmp_path / "selected_topics.json"
    artifact_path.write_text(
        json.dumps(
            {
                "schema_version": "newma.creator_node_artifact.v1",
                "run_id": "pending",
                "stage_id": "brief",
                "node_id": "brief_review",
                "artifact_type": "selected_topics",
                "status": "pending_review",
            }
        ),
        encoding="utf-8",
    )

    with TestClient(create_app(settings)) as client:
        client.app.state.creator_studio_service.control_adapter.run_node = lambda request, **_: {
            "execution_id": "execution-review",
            "executor_id": "newma.test.review",
            "status": "succeeded",
            "progress": 100,
            "finished_at": "2026-08-15T00:00:00+00:00",
            "artifacts": [
                {
                    "type": "selected_topics",
                    "path": str(artifact_path),
                    "status": "created",
                }
            ],
        }
        created = client.post(
            "/api/creator-studio/runs",
            headers=headers,
            json={
                "title": "审核产物回写测试",
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
        approved = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.node.approve",
                "stageId": "intake",
                "nodeId": "source_setup",
                "expectedRevision": waiting["run"]["revision"],
                "input": {
                    "selected_topics": [
                        {"topic_id": "topic-01", "title": "验收选题"}
                    ]
                },
            },
        ).json()
        assert approved["stages"][0]["nodes"][0]["status"] == "succeeded"

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["status"] == "approved"
    assert payload["approved_at"]
    assert payload["selected_topics"] == [
        {"topic_id": "topic-01", "title": "验收选题"}
    ]


def test_rerun_resets_succeeded_node_and_supersedes_artifacts(tmp_path: Path):
    settings = Settings(
        runtime_dir=tmp_path / "runtime",
        database_path=tmp_path / "newma-desk.db",
        creator_studio_workspace=creator_workspace(tmp_path),
        creator_studio_dist=tmp_path / "missing-dist",
    )
    headers = {"X-User-Id": "alice", "X-Workspace-Id": "creator-a"}

    with TestClient(create_app(settings)) as client:
        client.app.state.creator_studio_service.control_adapter.run_node = lambda request, **_: {
            "execution_id": "execution-rerun",
            "executor_id": "newma.test.executor",
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
                "title": "重跑契约测试",
                "stageId": "intake",
                "nodeId": "source_setup",
                "materials": [
                    {"type": "source", "path": "https://example.com", "source": "manual"}
                ],
            },
        ).json()
        run_id = created["run"]["runId"]

        executed = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.node.run",
                "stageId": "intake",
                "nodeId": "source_setup",
                "expectedRevision": 1,
            },
        ).json()
        node = executed["stages"][0]["nodes"][0]
        if node["status"] != "succeeded":
            # 异步执行：轮询等待 job 完成
            for _ in range(20):
                import time

                time.sleep(0.1)
                snap = client.get(
                    f"/api/creator-studio/runs/{run_id}", headers=headers
                ).json()
                node = snap["stages"][0]["nodes"][0]
                if node["status"] not in {"queued", "running"}:
                    break
        assert node["status"] == "succeeded"
        assert "creator.node.rerun" in node["availableActions"]

        rerun = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.node.rerun",
                "stageId": "intake",
                "nodeId": "source_setup",
                "expectedRevision": node.get("revision") or snap["run"]["revision"],
            },
        ).json()
        node = rerun["stages"][0]["nodes"][0]
        assert node["status"] == "pending"
        assert node["progress"] == 0
        assert node["artifacts"]
        assert all(a["status"] == "superseded" for a in node["artifacts"])
        assert "creator.node.run" in node["availableActions"]
        assert "creator.node.rerun" not in node["availableActions"]

        rerun_again = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.node.rerun",
                "stageId": "intake",
                "nodeId": "source_setup",
                "expectedRevision": rerun["run"]["revision"],
            },
        )
        assert rerun_again.status_code == 422


def test_review_gate_approve_writes_stage_gate_file(tmp_path: Path):
    workspace = creator_workspace(tmp_path)
    registry_path = (
        workspace / "configs" / "workflow" / "newma_creator_studio_registry.json"
    )
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    review_node = registry["stages"][0]["nodes"][0]
    review_node["executor"] = "newma.control.review-gate"
    review_node["gate"] = {"required": True, "kind": "human_review"}
    review_node["outputs"] = ["selected_topics"]
    registry["stages"][0]["nodes"][1]["material_requirements"] = [
        {
            "type": "selected_topics",
            "label": "已选题目",
            "required": True,
            "accepts": [".json"],
            "sources": ["upstream"],
        }
    ]
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
    gate_path = tmp_path / "selected_topics.json"
    gate_path.write_text('{"status":"approved"}', encoding="utf-8")

    with TestClient(create_app(settings)) as client:
        client.app.state.creator_studio_service.control_adapter.run_node = lambda request, **_: {
            "execution_id": "execution-gate",
            "executor_id": "newma.control.review-gate",
            "status": "waiting_user",
            "progress": 60,
            "finished_at": "2026-08-19T00:00:00+00:00",
            "artifacts": [
                {
                    "type": "selected_topics",
                    "path": str(tmp_path / "selected_topics.packet.json"),
                    "status": "created",
                    "origin": "packet",
                }
            ],
        }
        gate_calls: list[tuple[str, str]] = []

        def fake_approve_gate(run_id: str, stage: str, selected_ids=None) -> dict:
            gate_calls.append((run_id, stage))
            return {
                "status": "succeeded",
                "gate_file": str(gate_path),
                "stage": stage,
                "previous_status": "pending",
            }

        client.app.state.creator_studio_service.control_adapter.approve_gate = fake_approve_gate

        created = client.post(
            "/api/creator-studio/runs",
            headers=headers,
            json={
                "title": "门禁写盘测试",
                "stageId": "intake",
                "nodeId": "source_setup",
                "materials": [
                    {"type": "source", "path": "https://example.com", "source": "manual"}
                ],
            },
        ).json()
        run_id = created["run"]["runId"]

        executed = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.node.run",
                "stageId": "intake",
                "nodeId": "source_setup",
                "expectedRevision": 1,
            },
        ).json()
        node = next(
            n
            for s in executed["stages"]
            if s["id"] == "intake"
            for n in s["nodes"]
            if n["id"] == "source_setup"
        )
        if node["status"] != "waiting_user":
            import time

            for _ in range(20):
                time.sleep(0.1)
                snap = client.get(
                    f"/api/creator-studio/runs/{run_id}", headers=headers
                ).json()
                node = next(
                    n
                    for s in snap["stages"]
                    if s["id"] == "intake"
                    for n in s["nodes"]
                    if n["id"] == "source_setup"
                )
                if node["status"] not in {"queued", "running", "pending"}:
                    break
        assert node["status"] == "waiting_user"

        approved = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.node.approve",
                "stageId": "intake",
                "nodeId": "source_setup",
                "expectedRevision": snap["run"]["revision"],
            },
        ).json()
        assert gate_calls == [(run_id, "intake")]
        node = next(
            n
            for s in approved["stages"]
            if s["id"] == "intake"
            for n in s["nodes"]
            if n["id"] == "source_setup"
        )
        assert node["status"] == "succeeded"
        current_artifacts = [
            item for item in node["artifacts"] if item["status"] == "approved"
        ]
        assert len(current_artifacts) == 1
        assert current_artifacts[0]["origin"] == "deliverable"
        assert current_artifacts[0]["path"] == str(gate_path)
        collect = next(
            n
            for s in approved["stages"]
            if s["id"] == "intake"
            for n in s["nodes"]
            if n["id"] == "collect"
        )
        assert collect["materialValidation"]["status"] == "ready"
        assert collect["materials"][0]["type"] == "selected_topics"
        assert any("阶段门禁写盘：succeeded" in log.get("message", "") for log in node.get("logs", []))


def test_execution_finished_marks_run_succeeded(tmp_path: Path):
    """executor 异步完成最后一个节点时，run 应自动收尾 succeeded（非命令路径）。"""
    settings = Settings(
        runtime_dir=tmp_path / "runtime",
        database_path=tmp_path / "newma-desk.db",
        creator_studio_workspace=creator_workspace(tmp_path),
        creator_studio_dist=tmp_path / "missing-dist",
    )
    headers = {"X-User-Id": "alice", "X-Workspace-Id": "creator-a"}

    with TestClient(create_app(settings)) as client:
        client.app.state.creator_studio_service.control_adapter.run_node = lambda request, **_: {
            "execution_id": "execution-finish",
            "executor_id": "newma.test.executor",
            "status": "succeeded",
            "progress": 100,
            "finished_at": "2026-08-15T00:00:00+00:00",
            "artifacts": [],
        }
        created = client.post(
            "/api/creator-studio/runs",
            headers=headers,
            json={
                "title": "执行完成收尾测试",
                "stageId": "intake",
                "nodeId": "source_setup",
                "materials": [
                    {"type": "source", "path": "https://example.com", "source": "manual"}
                ],
            },
        ).json()
        run_id = created["run"]["runId"]

        def revision() -> int:
            snap = client.get(
                f"/api/creator-studio/runs/{run_id}", headers=headers
            ).json()
            return int(snap["run"]["revision"])

        def skip(stage: str, node: str) -> None:
            client.post(
                f"/api/creator-studio/runs/{run_id}/commands",
                headers=headers,
                json={
                    "actionId": "creator.node.skip",
                    "stageId": stage,
                    "nodeId": node,
                    "expectedRevision": revision(),
                },
            )

        # 先跳过另外两个节点：source_setup 仍是唯一非终态节点
        skip("intake", "collect")
        skip("brief", "topic_pool")

        executed = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.node.run",
                "stageId": "intake",
                "nodeId": "source_setup",
                "expectedRevision": revision(),
            },
        ).json()
        # run 命令响应时刻 source_setup 尚未终态，run 不应已完成
        assert executed["run"]["status"] != "succeeded"

        # 轮询等待 executor 异步完成：唯一可能的收尾路径是 execution.finished
        final = executed
        for _ in range(30):
            if final["run"]["status"] == "succeeded":
                break
            import time

            time.sleep(0.1)
            final = client.get(
                f"/api/creator-studio/runs/{run_id}", headers=headers
            ).json()
        assert final["run"]["status"] == "succeeded"
        assert final["stages"][0]["nodes"][0]["status"] == "succeeded"


def test_handoff_excludes_packet_artifacts(tmp_path: Path):
    """rerun 后 packet 成为唯一 USABLE 产物时，handoff 不得把它转交给下游。"""
    workspace = creator_workspace(tmp_path)
    real_source = tmp_path / "source-plan-real.json"
    real_source.write_text('{"kind": "deliverable"}', encoding="utf-8")
    packet_source = tmp_path / "source-plan-packet.json"
    packet_source.write_text('{"kind": "packet"}', encoding="utf-8")
    settings = Settings(
        runtime_dir=tmp_path / "runtime",
        database_path=tmp_path / "newma-desk.db",
        creator_studio_workspace=workspace,
        creator_studio_dist=tmp_path / "missing-dist",
    )
    headers = {"X-User-Id": "alice", "X-Workspace-Id": "creator-a"}

    responses: list[dict] = [
        {
            "execution_id": "execution-deliverable",
            "executor_id": "newma.test.executor",
            "status": "succeeded",
            "progress": 100,
            "artifacts": [
                {
                    "type": "source_plan",
                    "path": str(real_source),
                    "status": "created",
                    "origin": "deliverable",
                }
            ],
        },
        {
            "execution_id": "execution-packet",
            "executor_id": "newma.test.executor",
            "status": "succeeded",
            "progress": 100,
            "artifacts": [
                {
                    "type": "source_plan",
                    "path": str(packet_source),
                    "status": "created",
                    "origin": "packet",
                }
            ],
        },
    ]
    calls = {"index": 0}

    def fake_run_node(request, **_):
        response = responses[min(calls["index"], len(responses) - 1)]
        calls["index"] += 1
        return response

    with TestClient(create_app(settings)) as client:
        client.app.state.creator_studio_service.control_adapter.run_node = fake_run_node
        created = client.post(
            "/api/creator-studio/runs",
            headers=headers,
            json={
                "title": "packet handoff 排除测试",
                "stageId": "intake",
                "nodeId": "source_setup",
                "materials": [
                    {"type": "source", "path": "https://example.com", "source": "manual"}
                ],
            },
        ).json()
        run_id = created["run"]["runId"]

        def command(action: str, extra: dict | None = None) -> dict:
            snap = client.get(
                f"/api/creator-studio/runs/{run_id}", headers=headers
            ).json()
            body = {
                "actionId": action,
                "stageId": "intake",
                "nodeId": "source_setup",
                "expectedRevision": snap["run"]["revision"],
            }
            if extra:
                body["input"] = extra
            return client.post(
                f"/api/creator-studio/runs/{run_id}/commands",
                headers=headers,
                json=body,
            )

        command("creator.node.run")
        done = wait_for_node(
            client,
            headers,
            run_id,
            stage_id="intake",
            node_id="source_setup",
            statuses={"succeeded"},
        )
        node = done["stages"][0]["nodes"][0]
        assert node["artifacts"][0]["origin"] == "deliverable"

        # rerun → 旧交付物 superseded，重新执行产出 packet（唯一 USABLE）
        command("creator.node.rerun")
        command("creator.node.run")
        wait_for_node(
            client,
            headers,
            run_id,
            stage_id="intake",
            node_id="source_setup",
            statuses={"succeeded"},
        )
        snap = client.get(
            f"/api/creator-studio/runs/{run_id}", headers=headers
        ).json()
        node = snap["stages"][0]["nodes"][0]
        usable = [
            item
            for item in node["artifacts"]
            if item["status"] in {"created", "approved"}
        ]
        assert len(usable) == 1
        assert usable[0]["origin"] == "packet"

        # handoff 全量转交：packet 被排除 → 无可用产物 → 命令被拒
        rejected = command(
            "creator.handoff.create",
            {
                "targetStageId": "intake",
                "targetNodeId": "collect",
            },
        )
        assert rejected.status_code in {400, 422}
        assert "no artifacts are available for handoff" in rejected.json()["detail"]


def test_continue_is_pointer_only_and_never_regresses(tmp_path: Path):
    """continue 是纯指针推进：未完成节点被拒；已完成下一节点不被重置（进度只前进）。"""
    workspace = creator_workspace(tmp_path)
    registry_path = (
        workspace / "configs" / "workflow" / "newma_creator_studio_registry.json"
    )
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    intake_nodes = registry["stages"][0]["nodes"]
    for node in intake_nodes[:2]:
        node["executor"] = "newma.test.review"
        node["gate"] = {"required": True, "kind": "human_review"}
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
                {"type": "source_plan", "path": "/tmp/source_plan.json", "status": "created"}
            ],
        }
        created = client.post(
            "/api/creator-studio/runs",
            headers=headers,
            json={
                "title": "指针推进语义测试",
                "stageId": "intake",
                "nodeId": "source_setup",
                "materials": [
                    {"type": "source", "path": "https://example.com", "source": "manual"}
                ],
            },
        ).json()
        run_id = created["run"]["runId"]

        def run_and_approve(stage_id: str, node_id: str, expected_revision: int):
            client.post(
                f"/api/creator-studio/runs/{run_id}/commands",
                headers=headers,
                json={
                    "actionId": "creator.node.run",
                    "stageId": stage_id,
                    "nodeId": node_id,
                    "expectedRevision": expected_revision,
                },
            )
            snapshot = wait_for_node(
                client, headers, run_id,
                stage_id=stage_id, node_id=node_id,
                statuses={"waiting_user"},
            )
            return client.post(
                f"/api/creator-studio/runs/{run_id}/commands",
                headers=headers,
                json={
                    "actionId": "creator.node.approve",
                    "stageId": stage_id,
                    "nodeId": node_id,
                    "expectedRevision": snapshot["run"]["revision"],
                },
            ).json()

        approved_first = run_and_approve("intake", "source_setup", 1)
        approved_second = run_and_approve(
            "intake", "collect", approved_first["run"]["revision"]
        )
        collect = approved_second["stages"][0]["nodes"][1]
        assert collect["status"] == "succeeded"

        # 未完成节点（normalize pending）continue 被拒
        rejected = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.workflow.continue",
                "stageId": "intake",
                "nodeId": "normalize",
                "expectedRevision": approved_second["run"]["revision"],
            },
        )
        assert rejected.status_code in {400, 409, 422}

        # succeeded 节点 continue：active 指到 collect，且 collect 不被重置回 pending
        continued = client.post(
            f"/api/creator-studio/runs/{run_id}/commands",
            headers=headers,
            json={
                "actionId": "creator.workflow.continue",
                "stageId": "intake",
                "nodeId": "source_setup",
                "expectedRevision": approved_second["run"]["revision"],
            },
        ).json()
        # continue 推进后 _refresh_active_pointer 把 active 指到第一个未完成节点
        # （fixture registry 的 intake 只有 2 节点，全完成后指到 brief/topic_pool）
        assert continued["run"]["activeNodeId"] == "topic_pool"
        collect_after = continued["stages"][0]["nodes"][1]
        assert collect_after["status"] == "succeeded", "已完成的下一节点被 continue 重置（进度倒退）"
        assert collect_after["progress"] == 100
        # approve 已自动转接：collect 收到上游交付物素材
        collect_materials = collect_after.get("materials", [])
        assert any(m.get("type") == "source_plan" for m in collect_materials), (
            "approve 后未自动转接交付物（UI 直批路径与 Agent 推进不一致）"
        )
