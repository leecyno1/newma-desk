from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel


MODULE_ID_PATTERN = r"^[a-z][a-z0-9-]{2,63}$"
CAPABILITY_PATTERN = r"^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)*$"
ADAPTER_ID_PATTERN = r"^[a-z][a-z0-9-]{1,63}$"


class GatewayModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        serialize_by_alias=True,
        validate_by_alias=True,
        validate_by_name=True,
    )


class AgentTaskCreate(GatewayModel):
    module_id: str | None = Field(default=None, pattern=MODULE_ID_PATTERN)
    capability: str | None = Field(default=None, pattern=CAPABILITY_PATTERN)
    prompt: str = ""
    context: dict[str, Any] = Field(default_factory=dict)
    input: dict[str, Any] = Field(default_factory=dict)
    adapter: str | None = Field(default=None, pattern=ADAPTER_ID_PATTERN)

    @model_validator(mode="after")
    def require_intent(self) -> Self:
        if not self.prompt.strip() and not self.capability:
            raise ValueError("prompt or capability is required")
        return self


class TaskEvent(GatewayModel):
    task_id: str = Field(min_length=1, max_length=128)
    sequence: int = Field(ge=1, strict=True)
    type: Literal[
        "queued",
        "progress",
        "artifact",
        "completed",
        "failed",
        "cancelled",
    ]
    data: dict[str, Any] = Field(default_factory=dict)


class AdapterEvent(GatewayModel):
    type: Literal["progress", "artifact", "completed", "failed", "cancelled"]
    data: dict[str, Any] = Field(default_factory=dict)


class AgentTask(GatewayModel):
    id: str = Field(min_length=1, max_length=128)
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    request: AgentTaskCreate
    result: dict[str, Any] | None = None
    error: str | None = None
