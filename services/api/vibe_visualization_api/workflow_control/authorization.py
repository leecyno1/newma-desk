from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from vibe_visualization_api.workflow_control.errors import (
    WorkflowAuthorizationError,
    WorkflowValidationError,
)
from vibe_visualization_api.workflow_control.models import (
    DelegationGrantCreate,
    WorkflowAction,
    WorkflowScope,
    WorkflowScopeType,
)
from vibe_visualization_api.workflow_control.repository import (
    WorkflowNotFoundError,
    WorkflowRepository,
    now_iso,
)

@dataclass(frozen=True)
class AuthorizationDecision:
    allowed: bool
    source: str
    grant_id: str | None = None
    accountable_principal_id: str | None = None


NODE_ACCOUNTABLE_ACTIONS = {
    WorkflowAction.READ.value,
    WorkflowAction.WRITE.value,
    WorkflowAction.EXECUTE.value,
    WorkflowAction.DELEGATE.value,
}
NODE_REVIEWER_ACTIONS = {
    WorkflowAction.READ.value,
    WorkflowAction.REVIEW.value,
    WorkflowAction.DELEGATE.value,
}


class WorkflowAuthorization:
    def __init__(self, repository: WorkflowRepository):
        self._repository = repository

    @staticmethod
    def _scope_dict(scope: WorkflowScope | dict[str, Any]) -> dict[str, Any]:
        if isinstance(scope, WorkflowScope):
            return scope.model_dump(mode="json", by_alias=True, exclude_none=True)
        return dict(scope)

    @staticmethod
    def _parse_time(value: str | None) -> datetime | None:
        if not value:
            return None
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

    def _valid_grant(
        self,
        organization_id: str,
        grant: dict[str, Any],
        *,
        seen: set[str] | None = None,
    ) -> bool:
        if grant["status"] != "active":
            return False
        current = datetime.now(UTC)
        starts_at = self._parse_time(grant["startsAt"])
        expires_at = self._parse_time(grant.get("expiresAt"))
        if starts_at and starts_at > current:
            return False
        if expires_at and expires_at <= current:
            return False
        parent_id = grant.get("parentGrantId")
        if not parent_id:
            return True
        visited = set() if seen is None else set(seen)
        if grant["id"] in visited:
            return False
        visited.add(grant["id"])
        try:
            parent = self._repository.get_grant(organization_id, parent_id)
        except WorkflowNotFoundError:
            return False
        return self._valid_grant(organization_id, parent, seen=visited)

    def _run_for_scope(
        self,
        organization_id: str,
        scope: dict[str, Any],
    ) -> dict[str, Any] | None:
        run_id = scope.get("runId")
        return self._repository.get_run(organization_id, run_id) if run_id else None

    def _template_id_for_scope(
        self,
        organization_id: str,
        scope: dict[str, Any],
    ) -> str | None:
        if scope.get("templateId"):
            return str(scope["templateId"])
        run = self._run_for_scope(organization_id, scope)
        return str(run["templateId"]) if run else None

    @staticmethod
    def _node(run: dict[str, Any], node_id: str) -> dict[str, Any]:
        node = next((item for item in run["nodes"] if item["id"] == node_id), None)
        if node is None:
            raise WorkflowNotFoundError(node_id)
        return node

    def validate_scope(self, organization_id: str, scope: WorkflowScope | dict[str, Any]) -> None:
        value = self._scope_dict(scope)
        scope_type = value["type"]
        if scope_type == WorkflowScopeType.ORGANIZATION.value:
            self._repository.get_organization(organization_id)
            return
        if scope_type == WorkflowScopeType.TEMPLATE.value:
            self._repository.get_template(organization_id, value["templateId"])
            return
        if scope_type == WorkflowScopeType.RUN.value:
            self._repository.get_run(organization_id, value["runId"])
            return
        if scope_type == WorkflowScopeType.NODE.value:
            run = self._repository.get_run(organization_id, value["runId"])
            self._node(run, value["nodeId"])
            return
        if scope_type == WorkflowScopeType.ROLE.value:
            if value.get("runId"):
                nodes = self._repository.get_run(organization_id, value["runId"])["nodes"]
            else:
                nodes = self._repository.get_template(
                    organization_id, value["templateId"]
                )["nodes"]
            if not any(node["roleKey"] == value["roleKey"] for node in nodes):
                raise WorkflowNotFoundError(value["roleKey"])

    def scope_contains(
        self,
        organization_id: str,
        parent_scope: WorkflowScope | dict[str, Any],
        child_scope: WorkflowScope | dict[str, Any],
    ) -> bool:
        parent = self._scope_dict(parent_scope)
        child = self._scope_dict(child_scope)
        parent_type = parent["type"]
        child_type = child["type"]
        if parent_type == WorkflowScopeType.ORGANIZATION.value:
            return True
        if parent_type == WorkflowScopeType.TEMPLATE.value:
            return self._template_id_for_scope(organization_id, child) == parent["templateId"]
        if parent_type == WorkflowScopeType.RUN.value:
            return child_type in {
                WorkflowScopeType.RUN.value,
                WorkflowScopeType.NODE.value,
                WorkflowScopeType.ROLE.value,
            } and child.get("runId") == parent["runId"]
        if parent_type == WorkflowScopeType.NODE.value:
            return (
                child_type == WorkflowScopeType.NODE.value
                and child.get("runId") == parent["runId"]
                and child.get("nodeId") == parent["nodeId"]
            )
        if parent_type != WorkflowScopeType.ROLE.value:
            return False
        if child_type == WorkflowScopeType.ROLE.value:
            return (
                parent.get("runId") == child.get("runId")
                and parent.get("templateId") == child.get("templateId")
                and parent["roleKey"] == child["roleKey"]
            )
        if child_type != WorkflowScopeType.NODE.value:
            return False
        run = self._repository.get_run(organization_id, child["runId"])
        if parent.get("runId") and parent["runId"] != run["id"]:
            return False
        if parent.get("templateId") and parent["templateId"] != run["templateId"]:
            return False
        return self._node(run, child["nodeId"])["roleKey"] == parent["roleKey"]

    def _base_decision(
        self,
        *,
        organization_id: str,
        principal_id: str,
        scope: dict[str, Any],
        action: str,
    ) -> AuthorizationDecision:
        principal = self._repository.get_principal(organization_id, principal_id)
        if principal["status"] != "active":
            return AuthorizationDecision(False, "principal_inactive")
        if principal["role"] in {"owner", "admin"}:
            return AuthorizationDecision(True, "organization_role")
        if action == WorkflowAction.READ.value:
            return AuthorizationDecision(True, "organization_membership")

        template_id = self._template_id_for_scope(organization_id, scope)
        if template_id:
            template = self._repository.get_template(organization_id, template_id)
            if template["ownerPrincipalId"] == principal_id:
                return AuthorizationDecision(True, "template_owner")

        run = self._run_for_scope(organization_id, scope)
        if run and run["ownerPrincipalId"] == principal_id:
            return AuthorizationDecision(True, "run_owner")

        if scope["type"] == WorkflowScopeType.NODE.value and run:
            node = self._node(run, scope["nodeId"])
            accountable = node["accountablePrincipalId"]
            if accountable == principal_id and action in NODE_ACCOUNTABLE_ACTIONS:
                return AuthorizationDecision(
                    True,
                    "node_accountable",
                    accountable_principal_id=accountable,
                )
            if (
                node.get("reviewerPrincipalId") == principal_id
                and action in NODE_REVIEWER_ACTIONS
            ):
                return AuthorizationDecision(
                    True,
                    "node_reviewer",
                    accountable_principal_id=accountable,
                )
        return AuthorizationDecision(False, "no_base_right")

    def decide(
        self,
        *,
        organization_id: str,
        principal_id: str,
        scope: WorkflowScope | dict[str, Any],
        action: WorkflowAction | str,
    ) -> AuthorizationDecision:
        target = self._scope_dict(scope)
        action_value = action.value if isinstance(action, WorkflowAction) else str(action)
        self.validate_scope(organization_id, target)
        base = self._base_decision(
            organization_id=organization_id,
            principal_id=principal_id,
            scope=target,
            action=action_value,
        )
        if base.allowed:
            if target["type"] == WorkflowScopeType.NODE.value:
                run = self._repository.get_run(organization_id, target["runId"])
                accountable = self._node(run, target["nodeId"])[
                    "accountablePrincipalId"
                ]
                return AuthorizationDecision(
                    True,
                    base.source,
                    accountable_principal_id=accountable,
                )
            return base

        for grant in self._repository.list_grants(organization_id, principal_id):
            if grant["delegatePrincipalId"] != principal_id:
                continue
            if action_value not in grant["actions"]:
                continue
            if not self._valid_grant(organization_id, grant):
                continue
            if not self.scope_contains(organization_id, grant["scope"], target):
                continue
            accountable = None
            if target["type"] == WorkflowScopeType.NODE.value:
                run = self._repository.get_run(organization_id, target["runId"])
                accountable = self._node(run, target["nodeId"])[
                    "accountablePrincipalId"
                ]
            return AuthorizationDecision(
                True,
                "delegation_grant",
                grant_id=grant["id"],
                accountable_principal_id=accountable,
            )
        return AuthorizationDecision(False, "not_authorized")

    def require(
        self,
        *,
        organization_id: str,
        principal_id: str,
        scope: WorkflowScope | dict[str, Any],
        action: WorkflowAction | str,
    ) -> AuthorizationDecision:
        decision = self.decide(
            organization_id=organization_id,
            principal_id=principal_id,
            scope=scope,
            action=action,
        )
        if not decision.allowed:
            action_value = action.value if isinstance(action, WorkflowAction) else action
            raise WorkflowAuthorizationError(
                f"principal {principal_id} cannot {action_value} this workflow scope"
            )
        return decision

    def build_grant(
        self,
        *,
        organization_id: str,
        delegator_principal_id: str,
        request: DelegationGrantCreate,
        grant_id: str,
    ) -> dict[str, Any]:
        delegate = self._repository.get_principal(
            organization_id, request.delegate_principal_id
        )
        if delegate["status"] != "active":
            raise WorkflowAuthorizationError("delegate principal is inactive")
        if request.delegate_principal_id == delegator_principal_id:
            raise WorkflowValidationError("a principal cannot delegate to itself")
        scope = self._scope_dict(request.scope)
        self.validate_scope(organization_id, scope)
        requested_actions = {action.value for action in request.actions}
        needed_actions = requested_actions | {WorkflowAction.DELEGATE.value}

        base_supported = all(
            self._base_decision(
                organization_id=organization_id,
                principal_id=delegator_principal_id,
                scope=scope,
                action=action,
            ).allowed
            for action in needed_actions
        )
        parent: dict[str, Any] | None = None
        if not base_supported:
            candidates = self._repository.list_grants(
                organization_id, delegator_principal_id
            )
            if request.parent_grant_id:
                candidates = [
                    grant
                    for grant in candidates
                    if grant["id"] == request.parent_grant_id
                ]
            for grant in candidates:
                if grant["delegatePrincipalId"] != delegator_principal_id:
                    continue
                if not grant["allowRedelegate"] or grant["maxRedelegationDepth"] < 1:
                    continue
                if not needed_actions.issubset(set(grant["actions"])):
                    continue
                if not self._valid_grant(organization_id, grant):
                    continue
                if not self.scope_contains(organization_id, grant["scope"], scope):
                    continue
                parent = grant
                break
            if parent is None:
                raise WorkflowAuthorizationError(
                    "delegation would expand the delegator's current authority"
                )
            available_depth = parent["maxRedelegationDepth"] - 1
            if request.max_redelegation_depth > available_depth:
                raise WorkflowAuthorizationError(
                    "delegation depth exceeds the parent grant"
                )
            parent_expiry = self._parse_time(parent.get("expiresAt"))
            if parent_expiry and (
                request.expires_at is None or request.expires_at > parent_expiry
            ):
                raise WorkflowAuthorizationError(
                    "delegation expiry exceeds the parent grant"
                )
        elif request.parent_grant_id:
            raise WorkflowValidationError(
                "parentGrantId is only used when authority comes from a grant"
            )

        starts_at = request.starts_at or datetime.now(UTC)
        return {
            "id": grant_id,
            "delegatorPrincipalId": delegator_principal_id,
            "delegatePrincipalId": request.delegate_principal_id,
            "scope": scope,
            "actions": sorted(requested_actions),
            "startsAt": starts_at.isoformat(),
            "expiresAt": request.expires_at.isoformat() if request.expires_at else None,
            "allowRedelegate": request.allow_redelegate,
            "maxRedelegationDepth": request.max_redelegation_depth,
            "parentGrantId": parent["id"] if parent else None,
            "createdAt": now_iso(),
        }

    def require_revoke(
        self,
        *,
        organization_id: str,
        actor_principal_id: str,
        grant: dict[str, Any],
    ) -> None:
        if grant["delegatorPrincipalId"] == actor_principal_id:
            return
        decision = self.decide(
            organization_id=organization_id,
            principal_id=actor_principal_id,
            scope=grant["scope"],
            action=WorkflowAction.ADMIN,
        )
        if not decision.allowed:
            raise WorkflowAuthorizationError("principal cannot revoke this grant")
