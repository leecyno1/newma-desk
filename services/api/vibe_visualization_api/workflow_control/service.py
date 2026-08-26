from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from vibe_visualization_api.workflow_control.definition import (
    normalize_workflow_matrix,
    validate_workflow_definition,
)
from vibe_visualization_api.workflow_control.authorization import (
    AuthorizationDecision,
    WorkflowAuthorization,
)
from vibe_visualization_api.workflow_control.errors import (
    WorkflowAuthorizationError,
    WorkflowValidationError,
)
from vibe_visualization_api.workflow_control.models import (
    DelegationGrantCreate,
    NodeAssignmentInput,
    NodeClaimInput,
    NodeDataCreate,
    NodeReviewInput,
    NodeSubmitInput,
    WorkflowAction,
    WorkflowArtifactCreate,
    WorkflowPrincipalCreate,
    WorkflowRunCreate,
    WorkflowScope,
    WorkflowScopeType,
    WorkflowTemplateCreate,
    WorkflowTemplateRestore,
    WorkflowTemplateVersionCreate,
)
from vibe_visualization_api.workflow_control.repository import (
    WorkflowClaimConflictError,
    WorkflowConflictError,
    WorkflowNotFoundError,
    WorkflowRepository,
    now_iso,
)
from vibe_visualization_api.workflow_control.state import (
    TERMINAL_NODE_STATUSES,
    recalculate_run_status,
)


class WorkflowControlService:
    """Deep Module for organization workflow state, authorization and lineage."""

    def __init__(self, database_path):
        self.repository = WorkflowRepository(database_path)
        self.authorization = WorkflowAuthorization(self.repository)

    def identity(
        self,
        *,
        organization_id: str,
        user_id: str,
        acting_principal_id: str | None = None,
    ) -> dict[str, Any]:
        human = self.repository.ensure_identity(
            organization_id=organization_id,
            user_id=user_id,
        )
        if not acting_principal_id or acting_principal_id == human["id"]:
            return human
        return self.repository.get_principal(organization_id, acting_principal_id)

    @staticmethod
    def _definition(document: WorkflowTemplateCreate) -> dict[str, Any]:
        return normalize_workflow_matrix(
            document.model_dump(mode="json", by_alias=True)
        )

    @staticmethod
    def _validate_definition(definition: dict[str, Any]) -> None:
        validate_workflow_definition(definition)

    def _ensure_starter_template(
        self,
        organization_id: str,
        actor_principal_id: str,
    ) -> None:
        templates = self.repository.list_templates(organization_id)
        starter = next(
            (item for item in templates if item["id"] == "workflow-standard-research"),
            None,
        )
        legacy_starter = bool(
            starter
            and starter["currentVersion"] == 1
            and [lane["id"] for lane in starter["lanes"]] == ["main"]
            and [node["id"] for node in starter["nodes"]]
            == ["intake", "research", "challenge", "decision", "delivery"]
        )
        if starter and not legacy_starter:
            return
        definition = {
            "name": "通用研究决策流程",
            "description": "从任务受理、证据研究、反方审查到决策与交付归档。",
            "lanes": [
                {"id": "mandate", "name": "任务与立项", "description": "明确目标、范围和验收口径。"},
                {"id": "research", "name": "研究与生产", "description": "形成事实、证据和专业成果。"},
                {"id": "governance", "name": "复核与决策", "description": "挑战假设并完成组织决策。"},
                {"id": "delivery", "name": "交付与运营", "description": "归档交付并进入持续运营。"},
            ],
            "stages": [
                {"id": "intake", "name": "受理", "description": "定义问题"},
                {"id": "evidence", "name": "研究", "description": "形成证据"},
                {"id": "challenge", "name": "复核", "description": "反方审查"},
                {"id": "decision", "name": "决策", "description": "形成结论"},
                {"id": "delivery", "name": "交付", "description": "验收归档"},
            ],
            "nodes": [
                {
                    "id": "intake",
                    "name": "任务受理",
                    "description": "确认目标、范围、时限和验收口径。",
                    "roleKey": "sponsor",
                    "kind": "task",
                    "requiresReview": False,
                    "outputs": ["任务说明"],
                    "laneId": "mandate",
                    "stageId": "intake",
                    "promotedToMenu": True,
                },
                {
                    "id": "research",
                    "name": "证据研究",
                    "description": "收集事实、数据、来源与待核验项。",
                    "roleKey": "researcher",
                    "kind": "task",
                    "requiresReview": False,
                    "outputs": ["证据底稿"],
                    "laneId": "research",
                    "stageId": "evidence",
                    "promotedToMenu": False,
                },
                {
                    "id": "challenge",
                    "name": "反方审查",
                    "description": "挑战假设、识别缺口并给出反例。",
                    "roleKey": "challenger",
                    "kind": "review",
                    "requiresReview": False,
                    "outputs": ["反方意见"],
                    "laneId": "governance",
                    "stageId": "challenge",
                    "promotedToMenu": False,
                },
                {
                    "id": "decision",
                    "name": "负责人决策",
                    "description": "记录选择、分歧、条件与复核日期。",
                    "roleKey": "decision_owner",
                    "kind": "gate",
                    "requiresReview": False,
                    "outputs": ["决策记录"],
                    "laneId": "governance",
                    "stageId": "decision",
                    "promotedToMenu": True,
                },
                {
                    "id": "delivery",
                    "name": "交付归档",
                    "description": "整理最终交付物并完成负责人验收。",
                    "roleKey": "delivery_owner",
                    "kind": "task",
                    "requiresReview": True,
                    "outputs": ["正式交付物"],
                    "laneId": "delivery",
                    "stageId": "delivery",
                    "promotedToMenu": True,
                },
            ],
            "edges": [
                {"source": "intake", "target": "research"},
                {"source": "research", "target": "challenge"},
                {"source": "challenge", "target": "decision"},
                {"source": "decision", "target": "delivery"},
            ],
        }
        if legacy_starter:
            try:
                self.repository.add_template_version(
                    organization_id=organization_id,
                    template_id="workflow-standard-research",
                    definition=definition,
                    expected_version=1,
                    change_note="升级为横竖组织矩阵",
                    actor_principal_id=actor_principal_id,
                )
            except WorkflowConflictError:
                pass
            return
        if templates:
            return
        try:
            self.repository.create_template(
                organization_id=organization_id,
                template_id="workflow-standard-research",
                definition=definition,
                actor_principal_id=actor_principal_id,
                change_note="Organization starter workflow",
            )
        except WorkflowConflictError:
            pass

    def overview(
        self,
        *,
        organization_id: str,
        user_id: str,
        acting_principal_id: str | None = None,
    ) -> dict[str, Any]:
        principal = self.identity(
            organization_id=organization_id,
            user_id=user_id,
            acting_principal_id=acting_principal_id,
        )
        self._ensure_starter_template(organization_id, principal["id"])
        templates = self.repository.list_templates(organization_id)
        runs = self.repository.list_runs(organization_id)
        grants = self.repository.list_grants(organization_id)
        events = self.repository.list_events(organization_id, limit=40)
        active_grants = [
            grant for grant in grants if grant["status"] == "active"
        ]
        waiting_review = sum(
            node["status"] == "waiting_review"
            for run in runs
            for node in run["nodes"]
        )
        ready_nodes = sum(
            node["status"] in {"ready", "claimed", "running", "blocked", "stale"}
            for run in runs
            for node in run["nodes"]
        )
        return {
            "organization": self.repository.get_organization(organization_id),
            "currentPrincipal": principal,
            "principals": self.repository.list_principals(organization_id),
            "templates": templates,
            "runs": runs,
            "grants": grants,
            "recentEvents": events,
            "metrics": {
                "templates": len(templates),
                "activeRuns": sum(
                    run["status"] not in {"completed", "cancelled"} for run in runs
                ),
                "readyNodes": ready_nodes,
                "waitingReview": waiting_review,
                "activeGrants": len(active_grants),
                "serverAgents": sum(
                    principal["kind"] == "server_agent"
                    for principal in self.repository.list_principals(organization_id)
                ),
            },
        }

    def create_principal(
        self,
        *,
        organization_id: str,
        actor_principal_id: str,
        request: WorkflowPrincipalCreate,
    ) -> dict[str, Any]:
        self.authorization.require(
            organization_id=organization_id,
            principal_id=actor_principal_id,
            scope=WorkflowScope(type=WorkflowScopeType.ORGANIZATION),
            action=WorkflowAction.ADMIN,
        )
        return self.repository.create_principal(
            organization_id=organization_id,
            principal=request.model_dump(mode="json", by_alias=True),
            actor_principal_id=actor_principal_id,
        )

    def create_template(
        self,
        *,
        organization_id: str,
        actor_principal_id: str,
        request: WorkflowTemplateCreate,
    ) -> dict[str, Any]:
        self.repository.get_principal(organization_id, actor_principal_id)
        definition = self._definition(request)
        self._validate_definition(definition)
        return self.repository.create_template(
            organization_id=organization_id,
            template_id=f"workflow-{uuid4().hex[:16]}",
            definition=definition,
            actor_principal_id=actor_principal_id,
        )

    def add_template_version(
        self,
        *,
        organization_id: str,
        actor_principal_id: str,
        template_id: str,
        request: WorkflowTemplateVersionCreate,
    ) -> dict[str, Any]:
        self.authorization.require(
            organization_id=organization_id,
            principal_id=actor_principal_id,
            scope=WorkflowScope(
                type=WorkflowScopeType.TEMPLATE,
                template_id=template_id,
            ),
            action=WorkflowAction.ADMIN,
        )
        definition = normalize_workflow_matrix(
            request.model_dump(
                mode="json",
                by_alias=True,
                exclude={"expected_version", "change_note"},
            )
        )
        self._validate_definition(definition)
        return self.repository.add_template_version(
            organization_id=organization_id,
            template_id=template_id,
            definition=definition,
            expected_version=request.expected_version,
            change_note=request.change_note,
            actor_principal_id=actor_principal_id,
        )

    def list_template_versions(
        self,
        *,
        organization_id: str,
        actor_principal_id: str,
        template_id: str,
    ) -> list[dict[str, Any]]:
        self.authorization.require(
            organization_id=organization_id,
            principal_id=actor_principal_id,
            scope=WorkflowScope(
                type=WorkflowScopeType.TEMPLATE,
                template_id=template_id,
            ),
            action=WorkflowAction.READ,
        )
        return self.repository.list_template_versions(organization_id, template_id)

    def restore_template_version(
        self,
        *,
        organization_id: str,
        actor_principal_id: str,
        template_id: str,
        source_version: int,
        request: WorkflowTemplateRestore,
    ) -> dict[str, Any]:
        self.authorization.require(
            organization_id=organization_id,
            principal_id=actor_principal_id,
            scope=WorkflowScope(
                type=WorkflowScopeType.TEMPLATE,
                template_id=template_id,
            ),
            action=WorkflowAction.ADMIN,
        )
        source = self.repository.get_template_version(
            organization_id,
            template_id,
            source_version,
        )
        definition = {
            key: source[key]
            for key in ("name", "description", "nodes", "edges", "lanes", "stages")
        }
        self._validate_definition(definition)
        return self.repository.add_template_version(
            organization_id=organization_id,
            template_id=template_id,
            definition=definition,
            expected_version=request.expected_version,
            change_note=request.change_note or f"恢复至 v{source_version}",
            actor_principal_id=actor_principal_id,
        )

    def create_run(
        self,
        *,
        organization_id: str,
        actor_principal_id: str,
        request: WorkflowRunCreate,
    ) -> dict[str, Any]:
        template = self.repository.get_template(organization_id, request.template_id)
        version = request.template_version or template["currentVersion"]
        definition = self.repository.get_template_version(
            organization_id,
            request.template_id,
            version,
        )
        timestamp = now_iso()
        incoming = {node["id"]: 0 for node in definition["nodes"]}
        for edge in definition["edges"]:
            incoming[edge["target"]] += 1
        nodes: list[dict[str, Any]] = []
        for node in definition["nodes"]:
            accountable = (
                request.assignments.get(node["id"])
                or request.role_assignments.get(node["roleKey"])
                or actor_principal_id
            )
            reviewer = request.reviewers.get(node["id"])
            if node["requiresReview"] and not reviewer:
                reviewer = actor_principal_id
            self.repository.get_principal(organization_id, accountable)
            if reviewer:
                self.repository.get_principal(organization_id, reviewer)
            nodes.append(
                {
                    **node,
                    "status": "ready" if incoming[node["id"]] == 0 else "pending",
                    "accountablePrincipalId": accountable,
                    "reviewerPrincipalId": reviewer,
                    "claim": None,
                    "dataRevision": 0,
                    "artifactCount": 0,
                    "updatedAt": timestamp,
                }
            )
        run_id = f"run-{uuid4().hex[:20]}"
        document = {
            "id": run_id,
            "organizationId": organization_id,
            "templateId": request.template_id,
            "templateVersion": version,
            "title": request.title,
            "status": "active",
            "ownerPrincipalId": actor_principal_id,
            "nodes": nodes,
            "edges": definition["edges"],
            "lanes": definition["lanes"],
            "stages": definition["stages"],
            "revision": 1,
            "createdAt": timestamp,
            "updatedAt": timestamp,
        }
        return self.repository.create_run(
            organization_id=organization_id,
            document=document,
            actor_principal_id=actor_principal_id,
        )

    def run_snapshot(self, organization_id: str, run_id: str) -> dict[str, Any]:
        return {
            "run": self.repository.get_run(organization_id, run_id),
            "nodeData": self.repository.list_node_data(organization_id, run_id),
            "artifacts": self.repository.list_artifacts(organization_id, run_id),
            "events": self.repository.list_events(
                organization_id, run_id=run_id, limit=300
            ),
        }

    @staticmethod
    def _node(document: dict[str, Any], node_id: str) -> dict[str, Any]:
        node = next((item for item in document["nodes"] if item["id"] == node_id), None)
        if node is None:
            raise WorkflowNotFoundError(node_id)
        return node

    @staticmethod
    def _node_scope(run_id: str, node_id: str) -> WorkflowScope:
        return WorkflowScope(
            type=WorkflowScopeType.NODE,
            run_id=run_id,
            node_id=node_id,
        )

    @staticmethod
    def _claim_active(claim: dict[str, Any] | None) -> bool:
        if not claim:
            return False
        expires = datetime.fromisoformat(claim["leaseExpiresAt"])
        if not expires.tzinfo:
            expires = expires.replace(tzinfo=UTC)
        return expires > datetime.now(UTC)

    def _require_node(
        self,
        *,
        organization_id: str,
        actor_principal_id: str,
        run_id: str,
        node_id: str,
        action: WorkflowAction,
    ) -> AuthorizationDecision:
        return self.authorization.require(
            organization_id=organization_id,
            principal_id=actor_principal_id,
            scope=self._node_scope(run_id, node_id),
            action=action,
        )

    def claim_node(
        self,
        *,
        organization_id: str,
        actor_principal_id: str,
        run_id: str,
        node_id: str,
        request: NodeClaimInput,
    ) -> dict[str, Any]:
        decision = self._require_node(
            organization_id=organization_id,
            actor_principal_id=actor_principal_id,
            run_id=run_id,
            node_id=node_id,
            action=WorkflowAction.EXECUTE,
        )
        lease_until = (datetime.now(UTC) + timedelta(seconds=request.lease_seconds)).isoformat()

        def mutate(document: dict[str, Any]) -> dict[str, Any]:
            node = self._node(document, node_id)
            if node["status"] not in {"ready", "claimed", "running", "stale"}:
                raise WorkflowConflictError(f"node {node_id} is not claimable")
            claim = node.get("claim")
            if (
                self._claim_active(claim)
                and claim["principalId"] != actor_principal_id
            ):
                raise WorkflowClaimConflictError(node_id)
            node["claim"] = {
                "id": f"claim-{uuid4().hex[:16]}",
                "principalId": actor_principal_id,
                "leaseExpiresAt": lease_until,
            }
            node["status"] = "claimed"
            node["updatedAt"] = now_iso()
            return document

        return self.repository.mutate_run(
            organization_id=organization_id,
            run_id=run_id,
            expected_revision=request.expected_revision,
            mutate=mutate,
            event_type="node.claimed",
            actor_principal_id=actor_principal_id,
            accountable_principal_id=decision.accountable_principal_id,
            delegation_grant_id=decision.grant_id,
            event_payload={"nodeId": node_id, "leaseExpiresAt": lease_until},
        )

    def release_node(
        self,
        *,
        organization_id: str,
        actor_principal_id: str,
        run_id: str,
        node_id: str,
        expected_revision: int,
    ) -> dict[str, Any]:
        decision = self._require_node(
            organization_id=organization_id,
            actor_principal_id=actor_principal_id,
            run_id=run_id,
            node_id=node_id,
            action=WorkflowAction.EXECUTE,
        )

        def mutate(document: dict[str, Any]) -> dict[str, Any]:
            node = self._node(document, node_id)
            claim = node.get("claim")
            if (
                self._claim_active(claim)
                and claim["principalId"] != actor_principal_id
            ):
                raise WorkflowClaimConflictError(node_id)
            node["claim"] = None
            node["status"] = "ready"
            node["updatedAt"] = now_iso()
            return document

        return self.repository.mutate_run(
            organization_id=organization_id,
            run_id=run_id,
            expected_revision=expected_revision,
            mutate=mutate,
            event_type="node.released",
            actor_principal_id=actor_principal_id,
            accountable_principal_id=decision.accountable_principal_id,
            delegation_grant_id=decision.grant_id,
            event_payload={"nodeId": node_id},
        )

    @staticmethod
    def _assert_claim_available(node: dict[str, Any], actor_principal_id: str) -> None:
        claim = node.get("claim")
        if (
            WorkflowControlService._claim_active(claim)
            and claim["principalId"] != actor_principal_id
        ):
            raise WorkflowClaimConflictError(node["id"])

    @staticmethod
    def _assert_claim_owned(node: dict[str, Any], actor_principal_id: str) -> None:
        claim = node.get("claim")
        if (
            not WorkflowControlService._claim_active(claim)
            or claim["principalId"] != actor_principal_id
        ):
            raise WorkflowClaimConflictError(
                f"principal {actor_principal_id} does not own an active lease for {node['id']}"
            )

    def save_node_data(
        self,
        *,
        organization_id: str,
        actor_principal_id: str,
        run_id: str,
        node_id: str,
        request: NodeDataCreate,
    ) -> dict[str, Any]:
        decision = self._require_node(
            organization_id=organization_id,
            actor_principal_id=actor_principal_id,
            run_id=run_id,
            node_id=node_id,
            action=WorkflowAction.WRITE,
        )
        document = self.repository.get_run(organization_id, run_id)
        node = self._node(document, node_id)
        if node["status"] != "completed":
            self._assert_claim_owned(node, actor_principal_id)
        node["dataRevision"] += 1
        if node["status"] in {"ready", "claimed", "stale"}:
            node["status"] = "running"
        node["updatedAt"] = now_iso()
        updated, record = self.repository.add_node_data(
            organization_id=organization_id,
            run_id=run_id,
            node_id=node_id,
            slot_key=request.slot_key,
            payload=request.payload,
            document=document,
            expected_revision=request.expected_revision,
            actor_principal_id=actor_principal_id,
            accountable_principal_id=decision.accountable_principal_id,
            delegation_grant_id=decision.grant_id,
        )
        return {"run": updated, "dataRevision": record}

    def save_artifact(
        self,
        *,
        organization_id: str,
        actor_principal_id: str,
        run_id: str,
        node_id: str,
        request: WorkflowArtifactCreate,
    ) -> dict[str, Any]:
        decision = self._require_node(
            organization_id=organization_id,
            actor_principal_id=actor_principal_id,
            run_id=run_id,
            node_id=node_id,
            action=WorkflowAction.WRITE,
        )
        document = self.repository.get_run(organization_id, run_id)
        node = self._node(document, node_id)
        if node["status"] != "completed":
            self._assert_claim_owned(node, actor_principal_id)
        node["artifactCount"] += 1
        if node["status"] in {"ready", "claimed", "stale"}:
            node["status"] = "running"
        node["updatedAt"] = now_iso()
        updated, artifact, stale_nodes = self.repository.add_artifact(
            organization_id=organization_id,
            run_id=run_id,
            node_id=node_id,
            artifact=request.model_dump(
                mode="json", by_alias=True, exclude={"expected_revision"}
            ),
            document=document,
            expected_revision=request.expected_revision,
            actor_principal_id=actor_principal_id,
            accountable_principal_id=decision.accountable_principal_id,
            delegation_grant_id=decision.grant_id,
        )
        return {"run": updated, "artifact": artifact, "staleNodeIds": stale_nodes}

    @staticmethod
    def _unlock_downstream(document: dict[str, Any], completed_node_id: str) -> None:
        target_ids = [
            edge["target"]
            for edge in document["edges"]
            if edge["source"] == completed_node_id
        ]
        node_map = {node["id"]: node for node in document["nodes"]}
        for target_id in target_ids:
            target = node_map[target_id]
            sources = [
                edge["source"]
                for edge in document["edges"]
                if edge["target"] == target_id
            ]
            if all(node_map[source]["status"] in TERMINAL_NODE_STATUSES for source in sources):
                if target["status"] == "pending":
                    target["status"] = "ready"
                    target["updatedAt"] = now_iso()
        recalculate_run_status(document)

    def submit_node(
        self,
        *,
        organization_id: str,
        actor_principal_id: str,
        run_id: str,
        node_id: str,
        request: NodeSubmitInput,
    ) -> dict[str, Any]:
        decision = self._require_node(
            organization_id=organization_id,
            actor_principal_id=actor_principal_id,
            run_id=run_id,
            node_id=node_id,
            action=WorkflowAction.EXECUTE,
        )

        def mutate(document: dict[str, Any]) -> dict[str, Any]:
            node = self._node(document, node_id)
            self._assert_claim_owned(node, actor_principal_id)
            if node["status"] not in {"ready", "claimed", "running"}:
                raise WorkflowConflictError(f"node {node_id} cannot be submitted")
            node["claim"] = None
            node["status"] = "waiting_review" if node["requiresReview"] else "completed"
            node["updatedAt"] = now_iso()
            if node["status"] == "completed":
                self._unlock_downstream(document, node_id)
            return document

        return self.repository.mutate_run(
            organization_id=organization_id,
            run_id=run_id,
            expected_revision=request.expected_revision,
            mutate=mutate,
            event_type="node.submitted",
            actor_principal_id=actor_principal_id,
            accountable_principal_id=decision.accountable_principal_id,
            delegation_grant_id=decision.grant_id,
            event_payload={"nodeId": node_id, "note": request.note},
        )

    def review_node(
        self,
        *,
        organization_id: str,
        actor_principal_id: str,
        run_id: str,
        node_id: str,
        request: NodeReviewInput,
    ) -> dict[str, Any]:
        decision = self._require_node(
            organization_id=organization_id,
            actor_principal_id=actor_principal_id,
            run_id=run_id,
            node_id=node_id,
            action=WorkflowAction.REVIEW,
        )

        def mutate(document: dict[str, Any]) -> dict[str, Any]:
            node = self._node(document, node_id)
            if node["status"] != "waiting_review":
                raise WorkflowConflictError(f"node {node_id} is not waiting for review")
            node["status"] = (
                "completed" if request.decision == "approve" else "ready"
            )
            node["claim"] = None
            node["updatedAt"] = now_iso()
            if request.decision == "approve":
                self._unlock_downstream(document, node_id)
            return document

        return self.repository.mutate_run(
            organization_id=organization_id,
            run_id=run_id,
            expected_revision=request.expected_revision,
            mutate=mutate,
            event_type=f"node.review.{request.decision}",
            actor_principal_id=actor_principal_id,
            accountable_principal_id=decision.accountable_principal_id,
            delegation_grant_id=decision.grant_id,
            event_payload={"nodeId": node_id, "note": request.note},
        )

    def assign_node(
        self,
        *,
        organization_id: str,
        actor_principal_id: str,
        run_id: str,
        node_id: str,
        request: NodeAssignmentInput,
    ) -> dict[str, Any]:
        decision = self.authorization.require(
            organization_id=organization_id,
            principal_id=actor_principal_id,
            scope=WorkflowScope(type=WorkflowScopeType.RUN, run_id=run_id),
            action=WorkflowAction.ASSIGN,
        )
        self.repository.get_principal(
            organization_id, request.accountable_principal_id
        )
        if request.reviewer_principal_id:
            self.repository.get_principal(
                organization_id, request.reviewer_principal_id
            )
        current = self.repository.get_run(organization_id, run_id)
        old_accountable = self._node(current, node_id)["accountablePrincipalId"]

        def mutate(document: dict[str, Any]) -> dict[str, Any]:
            node = self._node(document, node_id)
            node["accountablePrincipalId"] = request.accountable_principal_id
            node["reviewerPrincipalId"] = request.reviewer_principal_id
            node["updatedAt"] = now_iso()
            return document

        return self.repository.mutate_run(
            organization_id=organization_id,
            run_id=run_id,
            expected_revision=request.expected_revision,
            mutate=mutate,
            event_type="node.assignment.changed",
            actor_principal_id=actor_principal_id,
            accountable_principal_id=old_accountable,
            delegation_grant_id=decision.grant_id,
            event_payload={
                "nodeId": node_id,
                "previousAccountablePrincipalId": old_accountable,
                "accountablePrincipalId": request.accountable_principal_id,
                "reviewerPrincipalId": request.reviewer_principal_id,
            },
        )

    def create_grant(
        self,
        *,
        organization_id: str,
        actor_principal_id: str,
        request: DelegationGrantCreate,
    ) -> dict[str, Any]:
        grant = self.authorization.build_grant(
            organization_id=organization_id,
            delegator_principal_id=actor_principal_id,
            request=request,
            grant_id=f"grant-{uuid4().hex[:20]}",
        )
        return self.repository.create_grant(
            organization_id=organization_id,
            grant=grant,
        )

    def revoke_grant(
        self,
        *,
        organization_id: str,
        actor_principal_id: str,
        grant_id: str,
    ) -> dict[str, Any]:
        grant = self.repository.get_grant(organization_id, grant_id)
        self.authorization.require_revoke(
            organization_id=organization_id,
            actor_principal_id=actor_principal_id,
            grant=grant,
        )
        return {
            "grantId": grant_id,
            "revokedGrantIds": self.repository.revoke_grant(
                organization_id=organization_id,
                grant_id=grant_id,
                actor_principal_id=actor_principal_id,
            ),
        }

    def effective_authority(
        self,
        *,
        organization_id: str,
        principal_id: str,
    ) -> dict[str, Any]:
        self.repository.get_principal(organization_id, principal_id)
        grants = self.repository.list_grants(organization_id, principal_id)
        return {
            "principalId": principal_id,
            "incoming": [
                grant for grant in grants if grant["delegatePrincipalId"] == principal_id
            ],
            "outgoing": [
                grant for grant in grants if grant["delegatorPrincipalId"] == principal_id
            ],
        }

    def artifacts(self, organization_id: str) -> list[dict[str, Any]]:
        return self.repository.list_artifacts(organization_id, current_only=True)

    def events(
        self,
        organization_id: str,
        *,
        run_id: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        return self.repository.list_events(
            organization_id,
            run_id=run_id,
            limit=limit,
        )


__all__ = [
    "WorkflowAuthorizationError",
    "WorkflowClaimConflictError",
    "WorkflowConflictError",
    "WorkflowControlService",
    "WorkflowNotFoundError",
    "WorkflowValidationError",
]
