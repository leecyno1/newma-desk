from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import Field, model_validator

from vibe_visualization_api.agent_gateway.models import AgentTaskCreate
from vibe_visualization_api.workflow_control.models import WorkflowModel


class WorkflowTriggerType(StrEnum):
    MANUAL = "manual"
    API = "api"
    EVENT = "event"
    SCHEDULE = "schedule"


class WorkflowPersistentTriggerType(StrEnum):
    EVENT = "event"
    SCHEDULE = "schedule"


class WorkflowRuntimeStart(WorkflowModel):
    idempotency_key: str = Field(min_length=3, max_length=200)
    trigger_type: WorkflowTriggerType = WorkflowTriggerType.MANUAL
    input: dict[str, Any] = Field(default_factory=dict, max_length=100)


class WorkflowRuntimeTick(WorkflowModel):
    max_jobs: int = Field(default=20, ge=1, le=200)


class WorkflowRuntimeCommand(WorkflowModel):
    reason: str = Field(default="", max_length=1000)


class WorkflowRuntimeTriggerCreate(WorkflowModel):
    trigger_type: WorkflowPersistentTriggerType
    event_type: str | None = Field(
        default=None,
        min_length=1,
        max_length=160,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$",
    )
    interval_seconds: int | None = Field(default=None, ge=1, le=31_536_000)
    cron_expression: str | None = Field(default=None, min_length=5, max_length=120)
    timezone: str | None = Field(default=None, min_length=1, max_length=80)
    enabled: bool = True
    input: dict[str, Any] = Field(default_factory=dict, max_length=100)

    @model_validator(mode="after")
    def validate_trigger_configuration(self):
        if self.trigger_type == WorkflowPersistentTriggerType.EVENT:
            if not self.event_type:
                raise ValueError("event trigger requires eventType")
            if self.interval_seconds is not None:
                raise ValueError("event trigger does not accept intervalSeconds")
            if self.cron_expression is not None or self.timezone is not None:
                raise ValueError("event trigger does not accept schedule fields")
        if self.trigger_type == WorkflowPersistentTriggerType.SCHEDULE:
            if bool(self.interval_seconds) == bool(self.cron_expression):
                raise ValueError(
                    "schedule trigger requires exactly one of intervalSeconds or cronExpression"
                )
            if self.event_type is not None:
                raise ValueError("schedule trigger does not accept eventType")
            if self.cron_expression and not self.timezone:
                self.timezone = "Asia/Shanghai"
        return self


class WorkflowRuntimeTriggerState(WorkflowModel):
    enabled: bool


class WorkflowRuntimeEventPublish(WorkflowModel):
    idempotency_key: str = Field(min_length=3, max_length=200)
    input: dict[str, Any] = Field(default_factory=dict, max_length=100)


class WorkflowRemoteAgentTaskCreate(WorkflowModel):
    user_id: str = Field(min_length=1, max_length=128)
    workspace_id: str = Field(min_length=1, max_length=128)
    request: AgentTaskCreate

    @model_validator(mode="after")
    def validate_user_identity(self):
        if self.request.user_id != self.user_id:
            raise ValueError("remote Agent request userId must match envelope")
        return self
