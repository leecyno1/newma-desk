from pathlib import Path

import pytest

from vibe_visualization_api.workflow_control.authorization import (
    WorkflowAuthorizationError,
)
from vibe_visualization_api.workflow_control.models import (
    DelegationGrantCreate,
    NodeClaimInput,
    NodeSubmitInput,
    WorkflowArtifactCreate,
    WorkflowPrincipalCreate,
    WorkflowRunCreate,
    WorkflowScope,
    WorkflowTemplateCreate,
    WorkflowTemplateRestore,
    WorkflowTemplateVersionCreate,
)
from vibe_visualization_api.workflow_control.repository import (
    WorkflowClaimConflictError,
)
from vibe_visualization_api.workflow_control.service import WorkflowControlService


@pytest.fixture
def workflow(tmp_path: Path):
    service = WorkflowControlService(tmp_path / "workflow.db")
    overview = service.overview(organization_id="org-1", user_id="owner")
    return service, overview["currentPrincipal"]["id"], overview["templates"][0]


def principal(service: WorkflowControlService, owner: str, name: str, kind: str):
    return service.create_principal(
        organization_id="org-1",
        actor_principal_id=owner,
        request=WorkflowPrincipalCreate(kind=kind, name=name),
    )


def run_for(
    service: WorkflowControlService,
    owner: str,
    template: dict,
    title: str,
    assignments: dict[str, str] | None = None,
):
    return service.create_run(
        organization_id="org-1",
        actor_principal_id=owner,
        request=WorkflowRunCreate(
            template_id=template["id"],
            title=title,
            assignments=assignments or {},
        ),
    )


def test_server_agent_can_delegate_multiple_nodes_without_expanding_scope(workflow):
    service, owner, template = workflow
    agent = principal(service, owner, "研究 Agent", "server_agent")
    delegate = principal(service, owner, "协作成员", "human")
    first = run_for(
        service,
        owner,
        template,
        "第一条流程",
        {"intake": agent["id"]},
    )
    second = run_for(
        service,
        owner,
        template,
        "第二条流程",
        {"intake": agent["id"]},
    )

    for run in (first, second):
        service.create_grant(
            organization_id="org-1",
            actor_principal_id=agent["id"],
            request=DelegationGrantCreate(
                delegate_principal_id=delegate["id"],
                scope=WorkflowScope(
                    type="node",
                    run_id=run["id"],
                    node_id="intake",
                ),
                actions=["write", "execute"],
            ),
        )

    authority = service.effective_authority(
        organization_id="org-1",
        principal_id=delegate["id"],
    )
    assert len(authority["incoming"]) == 2
    claimed = service.claim_node(
        organization_id="org-1",
        actor_principal_id=delegate["id"],
        run_id=first["id"],
        node_id="intake",
        request=NodeClaimInput(expected_revision=1),
    )
    assert claimed["nodes"][0]["claim"]["principalId"] == delegate["id"]

    with pytest.raises(WorkflowAuthorizationError):
        service.create_grant(
            organization_id="org-1",
            actor_principal_id=delegate["id"],
            request=DelegationGrantCreate(
                delegate_principal_id=agent["id"],
                scope=WorkflowScope(type="organization"),
                actions=["admin"],
            ),
        )


def test_revoking_parent_grant_cascades_and_removes_execution_right(workflow):
    service, owner, template = workflow
    agent = principal(service, owner, "主 Agent", "server_agent")
    delegate = principal(service, owner, "代理 Agent", "server_agent")
    run = run_for(service, owner, template, "转授权流程")
    parent = service.create_grant(
        organization_id="org-1",
        actor_principal_id=owner,
        request=DelegationGrantCreate(
            delegate_principal_id=agent["id"],
            scope=WorkflowScope(type="run", run_id=run["id"]),
            actions=["read", "write", "execute", "delegate"],
            allow_redelegate=True,
            max_redelegation_depth=2,
        ),
    )
    child = service.create_grant(
        organization_id="org-1",
        actor_principal_id=agent["id"],
        request=DelegationGrantCreate(
            delegate_principal_id=delegate["id"],
            scope=WorkflowScope(
                type="node",
                run_id=run["id"],
                node_id="intake",
            ),
            actions=["execute"],
        ),
    )
    assert child["parentGrantId"] == parent["id"]

    revoked = service.revoke_grant(
        organization_id="org-1",
        actor_principal_id=owner,
        grant_id=parent["id"],
    )
    assert set(revoked["revokedGrantIds"]) == {parent["id"], child["id"]}
    with pytest.raises(WorkflowAuthorizationError):
        service.claim_node(
            organization_id="org-1",
            actor_principal_id=delegate["id"],
            run_id=run["id"],
            node_id="intake",
            request=NodeClaimInput(expected_revision=1),
        )


def test_active_claim_prevents_duplicate_agent_execution(workflow):
    service, owner, template = workflow
    first = principal(service, owner, "Agent A", "server_agent")
    second = principal(service, owner, "Agent B", "server_agent")
    run = run_for(service, owner, template, "租约冲突")
    for actor in (first, second):
        service.create_grant(
            organization_id="org-1",
            actor_principal_id=owner,
            request=DelegationGrantCreate(
                delegate_principal_id=actor["id"],
                scope=WorkflowScope(
                    type="node",
                    run_id=run["id"],
                    node_id="intake",
                ),
                actions=["execute"],
            ),
        )
    claimed = service.claim_node(
        organization_id="org-1",
        actor_principal_id=first["id"],
        run_id=run["id"],
        node_id="intake",
        request=NodeClaimInput(expected_revision=1),
    )
    with pytest.raises(WorkflowClaimConflictError):
        service.claim_node(
            organization_id="org-1",
            actor_principal_id=second["id"],
            run_id=run["id"],
            node_id="intake",
            request=NodeClaimInput(expected_revision=claimed["revision"]),
        )


def test_artifact_replacement_marks_downstream_lineage_stale(workflow):
    service, owner, template = workflow
    run = run_for(service, owner, template, "交付物谱系")
    claimed = service.claim_node(
        organization_id="org-1",
        actor_principal_id=owner,
        run_id=run["id"],
        node_id="intake",
        request=NodeClaimInput(expected_revision=1),
    )
    first = service.save_artifact(
        organization_id="org-1",
        actor_principal_id=owner,
        run_id=run["id"],
        node_id="intake",
        request=WorkflowArtifactCreate(
            expected_revision=claimed["revision"],
            artifact_key="brief",
            label="任务说明 v1",
            content={"goal": "first"},
        ),
    )
    submitted = service.submit_node(
        organization_id="org-1",
        actor_principal_id=owner,
        run_id=run["id"],
        node_id="intake",
        request=NodeSubmitInput(expected_revision=first["run"]["revision"]),
    )
    research_claim = service.claim_node(
        organization_id="org-1",
        actor_principal_id=owner,
        run_id=run["id"],
        node_id="research",
        request=NodeClaimInput(expected_revision=submitted["revision"]),
    )
    downstream = service.save_artifact(
        organization_id="org-1",
        actor_principal_id=owner,
        run_id=run["id"],
        node_id="research",
        request=WorkflowArtifactCreate(
            expected_revision=research_claim["revision"],
            artifact_key="evidence",
            label="证据底稿",
            content={"facts": []},
            input_artifact_ids=[first["artifact"]["id"]],
        ),
    )
    replacement = service.save_artifact(
        organization_id="org-1",
        actor_principal_id=owner,
        run_id=run["id"],
        node_id="intake",
        request=WorkflowArtifactCreate(
            expected_revision=downstream["run"]["revision"],
            artifact_key="brief",
            label="任务说明 v2",
            content={"goal": "changed"},
        ),
    )
    assert replacement["staleNodeIds"] == ["research"]
    assert next(
        node for node in replacement["run"]["nodes"] if node["id"] == "research"
    )["status"] == "stale"
    artifacts = service.repository.list_artifacts("org-1", run["id"])
    stale = next(item for item in artifacts if item["id"] == downstream["artifact"]["id"])
    assert stale["stale"] is True


def test_workflow_routes_bootstrap_organization_and_agent(client):
    headers = {"X-User-Id": "route-owner", "X-Workspace-Id": "route-org"}
    overview = client.get("/api/workflows/overview", headers=headers)
    assert overview.status_code == 200
    body = overview.json()
    assert body["templates"][0]["id"] == "workflow-standard-research"
    created = client.post(
        "/api/workflows/principals",
        headers=headers,
        json={
            "kind": "server_agent",
            "name": "Route Agent",
            "role": "member",
            "capabilities": ["research"],
        },
    )
    assert created.status_code == 201
    assert created.json()["kind"] == "server_agent"
    template_id = body["templates"][0]["id"]
    versions = client.get(
        f"/api/workflows/templates/{template_id}/versions",
        headers=headers,
    )
    assert versions.status_code == 200
    assert [item["version"] for item in versions.json()["versions"]] == [1]
    restored = client.post(
        f"/api/workflows/templates/{template_id}/versions/1/restore",
        headers=headers,
        json={"expectedVersion": 1, "changeNote": "路由恢复验证"},
    )
    assert restored.status_code == 200
    assert restored.json()["currentVersion"] == 2


def test_overview_upgrades_legacy_starter_to_matrix(tmp_path: Path):
    service = WorkflowControlService(tmp_path / "legacy-workflow.db")
    owner = service.identity(organization_id="org-1", user_id="owner")
    service.repository.create_template(
        organization_id="org-1",
        template_id="workflow-standard-research",
        actor_principal_id=owner["id"],
        definition={
            "name": "通用研究决策流程",
            "description": "旧版线性流程",
            "nodes": [
                {
                    "id": node_id,
                    "name": name,
                    "description": "",
                    "roleKey": role_key,
                    "kind": "task",
                    "requiresReview": False,
                    "outputs": [],
                }
                for node_id, name, role_key in [
                    ("intake", "任务受理", "sponsor"),
                    ("research", "证据研究", "researcher"),
                    ("challenge", "反方审查", "challenger"),
                    ("decision", "负责人决策", "decision_owner"),
                    ("delivery", "交付归档", "delivery_owner"),
                ]
            ],
            "edges": [
                {"source": "intake", "target": "research"},
                {"source": "research", "target": "challenge"},
                {"source": "challenge", "target": "decision"},
                {"source": "decision", "target": "delivery"},
            ],
        },
    )

    overview = service.overview(organization_id="org-1", user_id="owner")
    starter = overview["templates"][0]
    versions = service.repository.list_template_versions(
        "org-1", "workflow-standard-research"
    )

    assert starter["currentVersion"] == 2
    assert [lane["id"] for lane in starter["lanes"]] == [
        "mandate",
        "research",
        "governance",
        "delivery",
    ]
    assert [item["version"] for item in versions] == [2, 1]


def test_template_version_history_restores_without_overwriting(workflow):
    service, owner, template = workflow
    changed_nodes = [dict(node) for node in template["nodes"]]
    changed_nodes[0]["name"] = "重新受理"
    version_two = service.add_template_version(
        organization_id="org-1",
        actor_principal_id=owner,
        template_id=template["id"],
        request=WorkflowTemplateVersionCreate(
            name=template["name"],
            description=template["description"],
            nodes=changed_nodes,
            edges=template["edges"],
            lanes=template["lanes"],
            stages=template["stages"],
            expected_version=1,
            change_note="调整受理节点",
        ),
    )
    restored = service.restore_template_version(
        organization_id="org-1",
        actor_principal_id=owner,
        template_id=template["id"],
        source_version=1,
        request=WorkflowTemplateRestore(
            expected_version=version_two["currentVersion"],
            change_note="恢复稳定版本",
        ),
    )
    versions = service.list_template_versions(
        organization_id="org-1",
        actor_principal_id=owner,
        template_id=template["id"],
    )

    assert restored["currentVersion"] == 3
    assert restored["nodes"][0]["name"] == template["nodes"][0]["name"]
    assert [version["version"] for version in versions] == [3, 2, 1]
    assert versions[0]["changeNote"] == "恢复稳定版本"
    assert versions[1]["nodes"][0]["name"] == "重新受理"


def test_matrix_template_is_preserved_in_run(workflow):
    service, owner, _template = workflow
    template = service.create_template(
        organization_id="org-1",
        actor_principal_id=owner,
        request=WorkflowTemplateCreate(
            name="矩阵流程",
            lanes=[
                {"id": "research", "name": "研究", "description": ""},
                {"id": "review", "name": "复核", "description": ""},
            ],
            stages=[
                {"id": "input", "name": "输入", "description": ""},
                {"id": "decision", "name": "决策", "description": ""},
            ],
            nodes=[
                {
                    "id": "research-input",
                    "name": "证据输入",
                    "roleKey": "researcher",
                    "laneId": "research",
                    "stageId": "input",
                    "promotedToMenu": True,
                },
                {
                    "id": "review-decision",
                    "name": "复核决策",
                    "roleKey": "reviewer",
                    "laneId": "review",
                    "stageId": "decision",
                },
            ],
            edges=[{"source": "research-input", "target": "review-decision"}],
        ),
    )
    run = run_for(service, owner, template, "矩阵运行")

    assert [lane["id"] for lane in run["lanes"]] == ["research", "review"]
    assert [stage["id"] for stage in run["stages"]] == ["input", "decision"]
    assert run["nodes"][0]["promotedToMenu"] is True


def test_completed_run_becomes_needs_rework_when_lineage_is_stale(workflow):
    service, owner, _template = workflow
    template = service.create_template(
        organization_id="org-1",
        actor_principal_id=owner,
        request=WorkflowTemplateCreate(
            name="两阶段交付",
            lanes=[{"id": "main", "name": "主流程", "description": ""}],
            stages=[
                {"id": "source", "name": "源文件", "description": ""},
                {"id": "delivery", "name": "交付", "description": ""},
            ],
            nodes=[
                {
                    "id": "source",
                    "name": "源文件",
                    "roleKey": "owner",
                    "laneId": "main",
                    "stageId": "source",
                },
                {
                    "id": "delivery",
                    "name": "交付",
                    "roleKey": "owner",
                    "laneId": "main",
                    "stageId": "delivery",
                },
            ],
            edges=[{"source": "source", "target": "delivery"}],
        ),
    )
    run = run_for(service, owner, template, "状态重算")
    source_claim = service.claim_node(
        organization_id="org-1",
        actor_principal_id=owner,
        run_id=run["id"],
        node_id="source",
        request=NodeClaimInput(expected_revision=run["revision"]),
    )
    source = service.save_artifact(
        organization_id="org-1",
        actor_principal_id=owner,
        run_id=run["id"],
        node_id="source",
        request=WorkflowArtifactCreate(
            expected_revision=source_claim["revision"],
            artifact_key="source",
            label="源文件 v1",
        ),
    )
    source_done = service.submit_node(
        organization_id="org-1",
        actor_principal_id=owner,
        run_id=run["id"],
        node_id="source",
        request=NodeSubmitInput(expected_revision=source["run"]["revision"]),
    )
    delivery_claim = service.claim_node(
        organization_id="org-1",
        actor_principal_id=owner,
        run_id=run["id"],
        node_id="delivery",
        request=NodeClaimInput(expected_revision=source_done["revision"]),
    )
    delivery = service.save_artifact(
        organization_id="org-1",
        actor_principal_id=owner,
        run_id=run["id"],
        node_id="delivery",
        request=WorkflowArtifactCreate(
            expected_revision=delivery_claim["revision"],
            artifact_key="delivery",
            label="正式交付",
            input_artifact_ids=[source["artifact"]["id"]],
        ),
    )
    completed = service.submit_node(
        organization_id="org-1",
        actor_principal_id=owner,
        run_id=run["id"],
        node_id="delivery",
        request=NodeSubmitInput(expected_revision=delivery["run"]["revision"]),
    )
    assert completed["status"] == "completed"

    replacement = service.save_artifact(
        organization_id="org-1",
        actor_principal_id=owner,
        run_id=run["id"],
        node_id="source",
        request=WorkflowArtifactCreate(
            expected_revision=completed["revision"],
            artifact_key="source",
            label="源文件 v2",
        ),
    )
    assert replacement["run"]["status"] == "needs_rework"
    assert replacement["staleNodeIds"] == ["delivery"]
