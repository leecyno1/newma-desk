from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional, Any
from datetime import datetime


class MessageOut(BaseModel):
    id: int
    chat_id: Optional[str]
    sender_id: Optional[str]
    sender_name: Optional[str]
    talker_name: Optional[str]
    timestamp: Optional[datetime]
    direction: Optional[str]
    type: Optional[str]
    content_text: Optional[str]
    media_url: Optional[str]
    meta: Optional[dict]  # include raw metadata (e.g., contents for links/images)
    tags: Optional[dict]
    derived: Optional[dict]
    importance_score: int
    upvotes: int
    downvotes: int

    model_config = ConfigDict(from_attributes=True)


class PaginatedMessages(BaseModel):
    total: int
    items: List[MessageOut]


class ContactOut(BaseModel):
    id: str
    name: Optional[str]
    alias: Optional[str]
    rating: int
    labels: Optional[dict]
    manual_rating: Optional[float] = None
    auto_rating: Optional[float] = None
    sample_size: Optional[int] = None
    hit_rate_overall: Optional[float] = None
    last_scored_at: Optional[str] = None
    focus: Optional[bool] = None
    watch: Optional[dict] = None
    score_summary: Optional[dict] = None
    role: Optional[str] = None
    is_sales: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True)


class ContactsLookupRequest(BaseModel):
    ids: List[str]


class ChatOut(BaseModel):
    id: str
    title: Optional[str]
    type: Optional[str]
    is_chatroom: bool
    last_message_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class UpDownVoteResult(BaseModel):
    id: int
    upvotes: int
    downvotes: int


class TagUpdateIn(BaseModel):
    tags: dict


class AIReplyRequest(BaseModel):
    message_ids: List[int]
    prompt_hint: Optional[str] = None


class AISummaryRequest(BaseModel):
    message_ids: Optional[List[int]] = None
    filters: Optional[dict] = None
    options: Optional[dict] = None
    prompts: Optional[dict] = None


class MessageDeriveRequest(BaseModel):
    message_ids: Optional[List[int]] = None
    period: Optional[str] = None
    limit: Optional[int] = None
    batch_size: int = Field(default=100, ge=1, le=100)
    concurrency: int = Field(default=3, ge=1, le=3)
    temperature: float = Field(default=0.1, ge=0, le=1)
    force: bool = False


class SendItem(BaseModel):
    target: str  # chat_id or talker
    text: str = ""
    target_name: Optional[str] = None
    content_parts: Optional[List[dict]] = None
    attachments: Optional[List[dict]] = None
    campaign_id: Optional[int] = None
    delivery_id: Optional[int] = None
    template_vars: Optional[dict] = None
    provider_override: Optional[str] = None
    channel: Optional[str] = None


class SendRequest(BaseModel):
    items: List[SendItem]


class SendUploadOut(BaseModel):
    file_id: str
    name: str
    mime: Optional[str] = None
    size: int = 0
    url: str
    kind: Optional[str] = None


class SendCapabilityOut(BaseModel):
    provider: str
    configured: bool
    supports_text: bool = True
    supports_link: bool = True
    supports_image: bool = False
    supports_file: bool = False
    fallback_text_for_media: bool = True
    upload_max_bytes: int = 0
    notes: List[str] = Field(default_factory=list)


class SendDeliveryOut(BaseModel):
    id: int
    campaign_id: int
    target_id: str
    target_name: Optional[str] = None
    rendered_text: Optional[str] = None
    content_parts: Optional[Any] = None
    attachment_snapshot: Optional[Any] = None
    provider: Optional[str] = None
    channel: Optional[str] = None
    status: str
    error: Optional[str] = None
    provider_result: Optional[dict] = None
    sent_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SendCampaignOut(BaseModel):
    id: int
    title: Optional[str] = None
    body_text: Optional[str] = None
    content_parts: Optional[Any] = None
    attachments: Optional[Any] = None
    provider: Optional[str] = None
    channel: Optional[str] = None
    created_by: Optional[str] = None
    status: str
    target_count: int
    success_count: int
    failed_count: int
    meta: Optional[dict] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SendCampaignDetailOut(SendCampaignOut):
    deliveries: List[SendDeliveryOut] = Field(default_factory=list)


class SendCampaignCreateRequest(BaseModel):
    title: Optional[str] = None
    body_text: Optional[str] = None
    content_parts: Optional[List[dict]] = None
    attachments: Optional[List[dict]] = None
    items: List[SendItem] = Field(default_factory=list)
    provider_override: Optional[str] = None
    channel: Optional[str] = None
    created_by: Optional[str] = None
    send_now: bool = True
    save_only: bool = False


class SendRetryRequest(BaseModel):
    delivery_ids: Optional[List[int]] = None
    target_ids: Optional[List[str]] = None


class TaskOut(BaseModel):
    id: int
    type: str
    status: str
    result: Optional[Any]


class Health(BaseModel):
    status: str
    chatlog_http_base: Optional[str]
    chatlog_dir: Optional[str]


class HealthCheckItem(BaseModel):
    name: str
    status: str
    error_code: Optional[str] = None
    message: Optional[str] = None
    latency_ms: Optional[int] = None


class ReadyOut(BaseModel):
    status: str
    healthy: bool
    error_code: Optional[str] = None
    checks: List[HealthCheckItem] = Field(default_factory=list)
    timestamp: Optional[str] = None


class ChatlogWebhookMessage(BaseModel):
    seq: int
    time: str
    talker: str
    talkerName: Optional[str] = None
    isChatRoom: bool
    sender: str
    senderName: Optional[str] = None
    isSelf: bool
    type: int
    subType: int
    content: Optional[str] = None
    contents: Optional[dict] = None


class ChatlogWebhookBody(BaseModel):
    keyword: str | None = None
    lastTime: str | None = None
    length: int
    messages: List[ChatlogWebhookMessage]
    sender: str | None = None
    talker: str


class ReportOut(BaseModel):
    id: int
    title: str
    time_range: Optional[str]
    status: str
    result_type: Optional[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReportArtifactOut(BaseModel):
    id: int
    report_id: int
    module: str
    title: Optional[str]
    content_type: Optional[str]
    sequence: int
    data_json: Optional[dict]
    data_text: Optional[str]
    meta: Optional[dict]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReportDetailOut(ReportOut):
    filters: Optional[dict]
    result_body: Optional[str]
    artifacts: List[ReportArtifactOut] = []


# =====================
# New: Email & Extensions Schemas
# =====================

class EmailAccountIn(BaseModel):
    name: str
    email_address: str
    provider: str | None = None
    imap_host: str
    imap_port: int = 993
    imap_ssl: bool = True
    smtp_host: str
    smtp_port: int = 465
    smtp_ssl: bool = True
    auth: dict = {}
    enabled: bool = True


class EmailAccountOut(EmailAccountIn):
    id: int
    last_sync_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class EmailSendRequest(BaseModel):
    account_id: int
    to: List[str]
    subject: str
    body_text: str
    cc: List[str] | None = None
    bcc: List[str] | None = None


class EmailMessageOut(BaseModel):
    id: int
    account_id: int
    external_id: str | None = None
    subject: str | None = None
    from_addr: str | None = None
    to_addrs: List[str] | None = None
    cc_addrs: List[str] | None = None
    bcc_addrs: List[str] | None = None
    sent_at: datetime | None = None
    direction: str
    snippet: str | None = None
    body_text: str | None = None
    body_html: str | None = None
    flags: List[str] | None = None
    meta: dict | None = None
    derived: dict | None = None

    model_config = ConfigDict(from_attributes=True)


class PaginatedEmailMessages(BaseModel):
    total: int
    items: List[EmailMessageOut]


class ExtAdapterIn(BaseModel):
    key: str
    name: str
    enabled: bool = False
    source_type: str = "langbot"
    config: dict = {}


class ExtAdapterOut(ExtAdapterIn):
    id: int
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class AdapterMessageOut(BaseModel):
    id: int
    adapter_key: str
    external_id: str | None = None
    chat_id: str | None = None
    sender: str | None = None
    timestamp: datetime | None = None
    direction: str
    content_text: str | None = None
    meta: dict | None = None

    model_config = ConfigDict(from_attributes=True)


class PaginatedAdapterMessages(BaseModel):
    total: int
    items: List[AdapterMessageOut]
