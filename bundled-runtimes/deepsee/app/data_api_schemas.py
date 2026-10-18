"""Stable contracts for project-to-project data access."""
from __future__ import annotations

from typing import Generic, Literal, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class PageMeta(BaseModel):
    limit: int
    has_more: bool
    next_cursor: str | None = None
    next_offset: int | None = None
    last_id: int | None = None
    coverage: Literal["database", "local_snapshot"] = "database"
    truncated: bool = False
    warnings: list[str] = Field(default_factory=list)


class DataPage(BaseModel, Generic[T]):
    data: list[T]
    meta: PageMeta


class DataItem(BaseModel, Generic[T]):
    data: T


class ContactData(BaseModel):
    id: str
    display_name: str
    nickname: str | None = None
    remark: str | None = None
    labels: list[str] = Field(default_factory=list)
    label_ids: list[str] = Field(default_factory=list)
    rating: int


class ChatData(BaseModel):
    id: str
    display_name: str
    is_group: bool
    last_message_at: str | None = None


class MessageData(BaseModel):
    id: int
    source: Literal["wechat"] = "wechat"
    chat_id: str | None = None
    chat_name: str | None = None
    sender_id: str | None = None
    sender_name: str | None = None
    occurred_at: str | None = None
    type: str
    direction: str | None = None
    text: str
    summary: str | None = None
    category: str | None = None
    sentiment: str | None = None
    importance: int
    attachment_path: str | None = None


class EmailData(BaseModel):
    id: int
    source: Literal["email"] = "email"
    account_id: int
    subject: str
    sender: str | None = None
    recipients: list[str] = Field(default_factory=list)
    occurred_at: str | None = None
    direction: str | None = None
    text: str
    summary: str | None = None


class ContentData(BaseModel):
    id: str
    source: Literal["news", "media", "mp", "meetings"]
    source_id: str
    title: str
    author: str | None = None
    published_at: str | None = None
    url: str | None = None
    text: str
    summary: str | None = None


class LabelData(BaseModel):
    id: str
    name: str | None = None
    member_count: int


class LabelsData(BaseModel):
    data: list[LabelData]
    name_source: Literal["local_cache", "unavailable"]
    account_id: str | None = None
    names_cached_at: str | None = None


class ResourceCapability(BaseModel):
    resource: str
    path: str
    scope: str
    pagination: Literal["cursor", "offset", "none"]
    incremental: Literal["new_records_by_id", "none"] = "none"


class CapabilitiesData(BaseModel):
    version: str = "1.1.0"
    project: str
    read_only: bool = True
    resources: list[ResourceCapability]
    rate_limit_per_minute: int
    timestamps: str = "RFC3339 UTC; unknown timestamps are null"
    search_path: str = "/api/v1/search"


class SearchGroup(BaseModel):
    source: str
    data: list[MessageData | ContactData | ChatData | EmailData | ContentData]
    meta: PageMeta


class SearchResponse(BaseModel):
    data: list[SearchGroup]
    mode: str = "literal_substring_grouped_by_source"


class EvaluationData(BaseModel):
    horizon_code: str
    direction_hit: bool | None = None
    absolute_return: float | None = None
    excess_return: float | None = None
    event_score: float | None = None
    entry_price: float | None = None
    evaluation_price: float | None = None
    benchmark_entry: float | None = None
    benchmark_evaluation: float | None = None
    evaluated_at: str | None = None


class PredictionData(BaseModel):
    id: int
    source_message_id: int | None = None
    source_time: str | None = None
    asset_type: str
    asset_code: str | None = None
    asset_name: str | None = None
    benchmark_code: str | None = None
    direction: str
    evaluations: list[EvaluationData]


class ScoreEvidence(BaseModel):
    status: str
    verified_samples: int
    actionable_samples: int
    matured_samples: int
    waiting_samples: int
    missing_samples: int
    coverage: float | None = None
    method: str


class ScorecardData(BaseModel):
    contact_id: str
    as_of: str | None = None
    accuracy_score: float | None = None
    hit_rate_overall: float | None = None
    excess_mean: float | None = None
    evidence: ScoreEvidence
    predictions: list[PredictionData]
    predictions_has_more: bool
    predictions_offset: int


class ErrorInfo(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorData(BaseModel):
    error: ErrorInfo
