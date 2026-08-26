from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


class WorkflowModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class PrincipalKind(StrEnum):
    HUMAN = "human"
    SERVER_AGENT = "server_agent"


class OrganizationRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"


class WorkflowAction(StrEnum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    REVIEW = "review"
    ASSIGN = "assign"
    DELEGATE = "delegate"
    ADMIN = "admin"


class WorkflowScopeType(StrEnum):
    ORGANIZATION = "organization"
    TEMPLATE = "template"
    RUN = "run"
    NODE = "node"
    ROLE = "role"


class WorkflowScope(WorkflowModel):
    type: WorkflowScopeType
    template_id: str | None = None
    run_id: str | None = None
    node_id: str | None = None
    role_key: str | None = None

    @model_validator(mode="after")
    def validate_scope(self) -> "WorkflowScope":
        if self.type == WorkflowScopeType.ORGANIZATION:
            if any((self.template_id, self.run_id, self.node_id, self.role_key)):
                raise ValueError("organization scope cannot include child identifiers")
        elif self.type == WorkflowScopeType.TEMPLATE:
            if not self.template_id or any((self.run_id, self.node_id, self.role_key)):
                raise ValueError("template scope requires only templateId")
        elif self.type == WorkflowScopeType.RUN:
            if not self.run_id or any((self.template_id, self.node_id, self.role_key)):
                raise ValueError("run scope requires only runId")
        elif self.type == WorkflowScopeType.NODE:
            if not self.run_id or not self.node_id or any(
                (self.template_id, self.role_key)
            ):
                raise ValueError("node scope requires runId and nodeId")
        elif self.type == WorkflowScopeType.ROLE:
            if not self.role_key or bool(self.template_id) == bool(self.run_id):
                raise ValueError(
                    "role scope requires roleKey and exactly one templateId or runId"
                )
            if self.node_id:
                raise ValueError("role scope cannot include nodeId")
        return self


class WorkflowPrincipalCreate(WorkflowModel):
    principal_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9:_-]{3,128}$")
    kind: PrincipalKind
    name: str = Field(min_length=1, max_length=120)
    role: OrganizationRole = OrganizationRole.MEMBER
    external_ref: str | None = Field(default=None, max_length=240)
    endpoint: str | None = Field(default=None, max_length=500)
    capabilities: list[str] = Field(default_factory=list, max_length=100)


class WorkflowLaneDefinition(WorkflowModel):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)


class WorkflowStageDefinition(WorkflowModel):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)


class WorkflowNodeDefinition(WorkflowModel):
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{1,63}$")
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    role_key: str = Field(min_length=1, max_length=80)
    kind: Literal["task", "review", "gate", "automation"] = "task"
    requires_review: bool = False
    outputs: list[str] = Field(default_factory=list, max_length=30)
    lane_id: str | None = None
    stage_id: str | None = None
    promoted_to_menu: bool = False


class WorkflowEdgeDefinition(WorkflowModel):
    source: str
    target: str


class WorkflowTemplateCreate(WorkflowModel):
    name: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=2000)
    nodes: list[WorkflowNodeDefinition] = Field(min_length=1, max_length=80)
    edges: list[WorkflowEdgeDefinition] = Field(default_factory=list, max_length=200)
    lanes: list[WorkflowLaneDefinition] = Field(default_factory=list, max_length=26)
    stages: list[WorkflowStageDefinition] = Field(default_factory=list, max_length=24)


class WorkflowTemplateVersionCreate(WorkflowTemplateCreate):
    expected_version: int = Field(ge=1)
    change_note: str = Field(default="", max_length=1000)


class WorkflowTemplateRestore(WorkflowModel):
    expected_version: int = Field(ge=1)
    change_note: str = Field(default="", max_length=1000)


class WorkflowRunCreate(WorkflowModel):
    template_id: str
    template_version: int | None = Field(default=None, ge=1)
    title: str = Field(min_length=1, max_length=180)
    assignments: dict[str, str] = Field(default_factory=dict)
    reviewers: dict[str, str] = Field(default_factory=dict)
    role_assignments: dict[str, str] = Field(default_factory=dict)


class DelegationGrantCreate(WorkflowModel):
    delegate_principal_id: str
    scope: WorkflowScope
    actions: list[WorkflowAction] = Field(min_length=1, max_length=7)
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    allow_redelegate: bool = False
    max_redelegation_depth: int = Field(default=0, ge=0, le=8)
    parent_grant_id: str | None = None

    @model_validator(mode="after")
    def validate_delegation(self) -> "DelegationGrantCreate":
        unique_actions = list(dict.fromkeys(self.actions))
        self.actions = unique_actions
        if self.expires_at and self.starts_at and self.expires_at <= self.starts_at:
            raise ValueError("expiresAt must be later than startsAt")
        if self.allow_redelegate:
            if WorkflowAction.DELEGATE not in self.actions:
                raise ValueError("redelegation requires the delegate action")
            if self.max_redelegation_depth < 1:
                raise ValueError("redelegation requires a positive depth")
        elif self.max_redelegation_depth:
            raise ValueError("maxRedelegationDepth requires allowRedelegate")
        return self


class NodeRevisionInput(WorkflowModel):
    expected_revision: int = Field(ge=1)


class NodeClaimInput(NodeRevisionInput):
    lease_seconds: int = Field(default=900, ge=60, le=3600)


class NodeDataCreate(NodeRevisionInput):
    slot_key: str = Field(min_length=1, max_length=100)
    payload: Any


class WorkflowArtifactCreate(NodeRevisionInput):
    artifact_key: str = Field(min_length=1, max_length=100)
    label: str = Field(min_length=1, max_length=180)
    kind: str = Field(default="document", min_length=1, max_length=80)
    uri: str | None = Field(default=None, max_length=2000)
    content: Any = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    input_artifact_ids: list[str] = Field(default_factory=list, max_length=100)


class NodeSubmitInput(NodeRevisionInput):
    note: str = Field(default="", max_length=2000)


class NodeReviewInput(NodeRevisionInput):
    decision: Literal["approve", "request_changes"]
    note: str = Field(default="", max_length=2000)


class NodeAssignmentInput(NodeRevisionInput):
    accountable_principal_id: str
    reviewer_principal_id: str | None = None


class WorkflowEventQuery(WorkflowModel):
    run_id: str | None = None
    limit: int = Field(default=200, ge=1, le=1000)
