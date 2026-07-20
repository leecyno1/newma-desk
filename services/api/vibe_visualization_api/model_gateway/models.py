from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

from vibe_visualization_api.agent_gateway.models import (
    ADAPTER_ID_PATTERN,
    CAPABILITY_PATTERN,
    MODULE_ID_PATTERN,
)


class ModelGatewayModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        serialize_by_alias=True,
        validate_by_alias=True,
        validate_by_name=True,
    )


class ModelResponseCreate(ModelGatewayModel):
    module_id: str | None = Field(default=None, pattern=MODULE_ID_PATTERN)
    capability: str | None = Field(default=None, pattern=CAPABILITY_PATTERN)
    prompt: str = ""
    context: dict[str, Any] = Field(default_factory=dict)
    input: dict[str, Any] = Field(default_factory=dict)
    adapter: str | None = Field(default=None, pattern=ADAPTER_ID_PATTERN)
    model: str | None = Field(default=None, min_length=1, max_length=256)

    @model_validator(mode="after")
    def require_intent(self) -> Self:
        if not self.prompt.strip() and not self.capability:
            raise ValueError("prompt or capability is required")
        return self


class ModelResponse(ModelGatewayModel):
    answer: str
    adapter: str
    model: str
