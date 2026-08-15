import re
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from vibe_visualization_api.control_plane.schemas import (
    ApiModel,
    ModuleWikiProfile,
)


MOD_ID_PATTERN = r"^[a-z][a-z0-9-]{2,63}$"
ENTRYPOINT_ID_PATTERN = r"^[a-z][a-z0-9-]{1,63}$"
INTENT_ID_PATTERN = r"^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+$"
HANDOFF_ID_PATTERN = r"^hf_[A-Za-z0-9_-]{8,120}$"

WikiSubjectType = Literal[
    "security",
    "etf",
    "fund",
    "company",
    "industry",
    "concept",
    "event",
    "topic",
]


class WikiSubjectRef(ApiModel):
    type: WikiSubjectType
    canonical_id: str = Field(min_length=3, max_length=240)
    display_name: str = Field(min_length=1, max_length=160)
    market: Literal["CN", "HK", "US"] | None = None
    symbol: str | None = Field(default=None, min_length=1, max_length=40)
    asset_type: Literal["stock", "etf", "fund", "index", "other"] | None = None

    @model_validator(mode="after")
    def validate_identity(self):
        if any(character.isspace() for character in self.canonical_id):
            raise ValueError("Wiki canonical IDs cannot contain whitespace")
        if not self.canonical_id.startswith(f"{self.type}:"):
            raise ValueError("Wiki canonical ID prefix must match the subject type")
        if self.type in {"security", "etf", "fund"} and (
            self.market is None or self.symbol is None
        ):
            raise ValueError("Tradable Wiki subjects require market and symbol")
        if self.type == "etf" and self.asset_type not in {None, "etf"}:
            raise ValueError("ETF subjects must use the ETF asset type")
        if self.type == "fund" and self.asset_type not in {None, "fund"}:
            raise ValueError("Fund subjects must use the fund asset type")
        return self


class WikiPageContext(ApiModel):
    primary_subject: WikiSubjectRef
    related_subjects: list[WikiSubjectRef] = Field(default_factory=list, max_length=20)
    concept_ids: list[str] = Field(default_factory=list, max_length=50)
    intent: str = Field(pattern=INTENT_ID_PATTERN)
    timeframe: str | None = Field(default=None, min_length=1, max_length=40)
    snapshot_id: str | None = Field(default=None, min_length=1, max_length=160)

    @field_validator("related_subjects")
    @classmethod
    def unique_related_subjects(
        cls,
        value: list[WikiSubjectRef],
    ) -> list[WikiSubjectRef]:
        ids = [subject.canonical_id for subject in value]
        if len(ids) != len(set(ids)):
            raise ValueError("Related Wiki subjects must be unique")
        return value

    @field_validator("concept_ids")
    @classmethod
    def unique_concept_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)) or any(
            not item or len(item) > 240 or any(char.isspace() for char in item)
            for item in value
        ):
            raise ValueError("Wiki concept IDs must be unique canonical IDs")
        return value


class WikiLinkResolutionRequest(ApiModel):
    source_mod_id: str = Field(pattern=MOD_ID_PATTERN)
    context: WikiPageContext
    limit: int = Field(default=5, ge=1, le=20)


class WikiLinkMatch(ApiModel):
    subject_type: str
    intent_score: int = Field(ge=0, le=25)
    concepts: list[str] = Field(default_factory=list)
    data_capabilities: list[str] = Field(default_factory=list)


class WikiLink(ApiModel):
    id: str = Field(min_length=3, max_length=140)
    target_mod_id: str = Field(pattern=MOD_ID_PATTERN)
    target_revision: int = Field(ge=1)
    entrypoint_id: str = Field(pattern=ENTRYPOINT_ID_PATTERN)
    intent: str = Field(pattern=INTENT_ID_PATTERN)
    label: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=1, max_length=240)
    score: int = Field(ge=0, le=100)
    match: WikiLinkMatch


class WikiLinkResolutionResponse(ApiModel):
    source_mod_id: str = Field(pattern=MOD_ID_PATTERN)
    subject: WikiSubjectRef
    links: list[WikiLink]
    generated_at: datetime


class WikiModProfileResponse(ApiModel):
    module_id: str = Field(pattern=MOD_ID_PATTERN)
    revision: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=80)
    wiki: ModuleWikiProfile
    data_capabilities: list[str]


class WikiSubjectMatch(ApiModel):
    subject: WikiSubjectRef
    aliases: list[str] = Field(default_factory=list, max_length=20)
    concept_ids: list[str] = Field(default_factory=list, max_length=50)
    source: str = Field(min_length=1, max_length=120)
    matched_by: Literal["canonical", "symbol", "name", "alias", "upstream"]
    confidence: float = Field(ge=0, le=1)


WikiParameter = str | int | float | bool


class WikiHandoffCreate(ApiModel):
    source_mod_id: str = Field(pattern=MOD_ID_PATTERN)
    target_mod_id: str = Field(pattern=MOD_ID_PATTERN)
    entrypoint_id: str = Field(pattern=ENTRYPOINT_ID_PATTERN)
    context: WikiPageContext
    parameters: dict[str, WikiParameter] = Field(default_factory=dict, max_length=32)

    @field_validator("parameters")
    @classmethod
    def validate_parameters(
        cls,
        value: dict[str, WikiParameter],
    ) -> dict[str, WikiParameter]:
        if any(isinstance(item, str) and len(item) > 500 for item in value.values()):
            raise ValueError("Wiki parameter strings cannot exceed 500 characters")
        return value


class WikiHandoff(ApiModel):
    version: Literal[1]
    id: str = Field(pattern=HANDOFF_ID_PATTERN)
    source_mod_id: str = Field(pattern=MOD_ID_PATTERN)
    source_snapshot_id: str | None = Field(default=None, min_length=1, max_length=160)
    target_mod_id: str = Field(pattern=MOD_ID_PATTERN)
    entrypoint_id: str = Field(pattern=ENTRYPOINT_ID_PATTERN)
    subject: WikiSubjectRef
    related_subjects: list[WikiSubjectRef] = Field(default_factory=list, max_length=20)
    concept_ids: list[str] = Field(default_factory=list, max_length=50)
    intent: str = Field(pattern=INTENT_ID_PATTERN)
    timeframe: str | None = Field(default=None, min_length=1, max_length=40)
    parameters: dict[str, WikiParameter] = Field(default_factory=dict, max_length=32)
    created_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def validate_expiry(self):
        if self.expires_at <= self.created_at:
            raise ValueError("Wiki handoff expiry must be after creation")
        return self


class WikiHandoffResponse(WikiHandoff):
    pass
