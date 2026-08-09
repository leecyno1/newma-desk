from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


ArchiveKind = Literal[
    "uploaded-report",
    "research-record",
    "thesis",
    "earnings",
    "peer-comparison",
    "valuation",
    "research-memo",
]
ArchiveStatus = Literal[
    "active",
    "draft",
    "archived",
    "invalidated",
    "stale",
    "unknown",
]


class ResearchArchiveModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        extra="forbid",
        serialize_by_alias=True,
        validate_by_alias=True,
        validate_by_name=True,
    )


class ResearchArchiveSecurity(ResearchArchiveModel):
    market: str = Field(min_length=1, max_length=24)
    symbol: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=160)


class ResearchArchiveEntry(ResearchArchiveModel):
    id: str = Field(min_length=1, max_length=320)
    kind: ArchiveKind
    source_mod_id: str = Field(min_length=1, max_length=64)
    artifact_id: str = Field(min_length=1, max_length=240)
    title: str = Field(min_length=1, max_length=320)
    status: ArchiveStatus
    security: ResearchArchiveSecurity | None = None
    as_of: str | None = Field(default=None, max_length=80)
    updated_at: str
    tags: list[str] = Field(default_factory=list, max_length=16)
    source_revision: int = Field(ge=1)


class ResearchArchiveIndex(ResearchArchiveModel):
    schema_version: Literal["newma-desk.research-archive.v1"] = (
        "newma-desk.research-archive.v1"
    )
    user_id: str
    workspace_id: str
    generated_at: str
    entries: list[ResearchArchiveEntry]
