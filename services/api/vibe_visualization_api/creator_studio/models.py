from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class CreatorModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
        extra="forbid",
    )


class CreatorMaterialInput(CreatorModel):
    type: str = Field(min_length=1, max_length=80)
    slot: str | None = Field(default=None, min_length=1, max_length=160)
    path: str = Field(min_length=1, max_length=2048)
    source: Literal["manual", "upstream"] = "manual"
    label: str | None = Field(default=None, min_length=1, max_length=160)
    artifact_id: str | None = Field(default=None, min_length=1, max_length=160)
    artifact_version: int | None = Field(default=None, ge=1)
    content_digest: str | None = Field(default=None, min_length=8, max_length=128)
    source_run_id: str | None = Field(default=None, min_length=1, max_length=160)
    source_stage_id: str | None = Field(default=None, min_length=1, max_length=80)
    source_node_id: str | None = Field(default=None, min_length=1, max_length=80)
    status: Literal["active", "stale", "superseded", "failed"] | None = None


class CreatorRunCreate(CreatorModel):
    title: str = Field(min_length=1, max_length=160)
    stage_id: str = Field(min_length=1, max_length=80)
    node_id: str = Field(min_length=1, max_length=80)
    materials: list[CreatorMaterialInput] = Field(default_factory=list, max_length=100)


class CreatorCommand(CreatorModel):
    action_id: str = Field(pattern=r"^creator(?:\.[a-z][a-z0-9-]*)+$")
    stage_id: str | None = Field(default=None, min_length=1, max_length=80)
    node_id: str | None = Field(default=None, min_length=1, max_length=80)
    input: dict[str, Any] = Field(default_factory=dict)
    expected_revision: int | None = Field(default=None, ge=1)


MarketplaceKind = Literal["project", "skill", "pipeline", "template"]


class MarketplaceCompatibilityRequest(CreatorModel):
    item_id: str = Field(min_length=1, max_length=160)
    item_kind: MarketplaceKind
    stage_id: str | None = Field(default=None, min_length=1, max_length=80)
    node_id: str | None = Field(default=None, min_length=1, max_length=80)


class MarketplacePresetCreate(MarketplaceCompatibilityRequest):
    name: str = Field(min_length=1, max_length=160)
    parameters: dict[str, Any] = Field(default_factory=dict)


class MarketplacePresetUpdate(CreatorModel):
    name: str = Field(min_length=1, max_length=160)
    stage_id: str | None = Field(default=None, min_length=1, max_length=80)
    node_id: str | None = Field(default=None, min_length=1, max_length=80)
    parameters: dict[str, Any] = Field(default_factory=dict)
    expected_version: int = Field(ge=1)
