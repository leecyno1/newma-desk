from __future__ import annotations

from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text, JSON, ForeignKey, Float, UniqueConstraint
from sqlalchemy.orm import mapped_column, Mapped, relationship
from datetime import datetime
from .db import Base


class Chat(Base):
    __tablename__ = "chats"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # talker id or room id
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    type: Mapped[str | None] = mapped_column(String, nullable=True)  # single/group
    is_chatroom: Mapped[bool] = mapped_column(Boolean, default=False)
    members: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    messages: Mapped[list[Message]] = relationship("Message", back_populates="chat")  # type: ignore


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[str] = mapped_column(String, primary_key=True)  # wxid
    name: Mapped[str | None] = mapped_column(String, nullable=True)
    alias: Mapped[str | None] = mapped_column(String, nullable=True)
    rating: Mapped[int] = mapped_column(Integer, default=50)
    labels: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    stats: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    prediction_events: Mapped[list["ContactPredictionEvent"]] = relationship(
        "ContactPredictionEvent",
        back_populates="contact",
        cascade="all, delete-orphan",
    )
    score_snapshots: Mapped[list["ContactScoreSnapshot"]] = relationship(
        "ContactScoreSnapshot",
        back_populates="contact",
        cascade="all, delete-orphan",
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chat_id: Mapped[str | None] = mapped_column(String, ForeignKey("chats.id"), index=True)
    sender_id: Mapped[str | None] = mapped_column(String, index=True)
    sender_name: Mapped[str | None] = mapped_column(String, nullable=True)
    talker_name: Mapped[str | None] = mapped_column(String, nullable=True)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    direction: Mapped[str | None] = mapped_column(String)  # in/out
    type: Mapped[str | None] = mapped_column(String)  # text/image/file/voice/video/link/other
    content_text: Mapped[str | None] = mapped_column(Text)
    media_url: Mapped[str | None] = mapped_column(Text)
    meta: Mapped[dict | None] = mapped_column(JSON)
    tags: Mapped[dict | None] = mapped_column(JSON)  # array-like
    derived: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    importance_score: Mapped[int] = mapped_column(Integer, default=50)
    upvotes: Mapped[int] = mapped_column(Integer, default=0)
    downvotes: Mapped[int] = mapped_column(Integer, default=0)
    ai_suggestions: Mapped[dict | None] = mapped_column(JSON)
    send_status: Mapped[str | None] = mapped_column(String)  # pending/sent/failed

    chat: Mapped[Chat | None] = relationship("Chat", back_populates="messages")
    prediction_events: Mapped[list["ContactPredictionEvent"]] = relationship(
        "ContactPredictionEvent",
        back_populates="source_message",
    )


class WechatSubsession(Base):
    __tablename__ = "wechat_subsessions"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    channel: Mapped[str] = mapped_column(String(32), default="wechat_gateway", index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    mode: Mapped[str] = mapped_column(String(32), default="fixed")
    system_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    workflow_guardrails: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    model_route_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model_route_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    model_override: Mapped[str | None] = mapped_column(String(255), nullable=True)
    history_max_messages: Mapped[int] = mapped_column(Integer, default=30)
    history_max_tokens: Mapped[int] = mapped_column(Integer, default=4000)
    rolling_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    pinned_memory: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    allow_cross_chat_context: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_cross_sender_context: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)


class WechatSubsessionMembership(Base):
    __tablename__ = "wechat_subsession_memberships"
    __table_args__ = (
        UniqueConstraint("subsession_id", "member_type", "member_key", name="uq_wechat_subsession_member"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subsession_id: Mapped[str] = mapped_column(String(128), ForeignKey("wechat_subsessions.id"), index=True)
    member_type: Mapped[str] = mapped_column(String(16), index=True)
    member_key: Mapped[str] = mapped_column(String(255), index=True)
    chat_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    sender_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class WechatSubsessionTurn(Base):
    __tablename__ = "wechat_subsession_turns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subsession_id: Mapped[str] = mapped_column(String(128), ForeignKey("wechat_subsessions.id"), index=True)
    message_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("messages.id"), index=True, nullable=True)
    chat_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    sender_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    direction: Mapped[str] = mapped_column(String(8), index=True)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime, index=True, nullable=True)
    content_text_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ContactPredictionEvent(Base):
    __tablename__ = "contact_prediction_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contact_id: Mapped[str] = mapped_column(String, ForeignKey("contacts.id"), index=True)
    source_message_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("messages.id"), index=True, nullable=True)
    source_chat_id: Mapped[str | None] = mapped_column(String, nullable=True)
    source_time: Mapped[datetime | None] = mapped_column(DateTime, index=True, nullable=True)
    asset_type: Mapped[str] = mapped_column(String(32), index=True)
    asset_code: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    asset_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    benchmark_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    topic: Mapped[str | None] = mapped_column(String(255), nullable=True)
    topic_key: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    direction: Mapped[str] = mapped_column(String(32), index=True)
    event_kind: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    is_actionable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    signal_strength: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    event_cluster_id: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    horizon_flags: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extractor_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="extracted", index=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    contact: Mapped[Contact] = relationship("Contact", back_populates="prediction_events")
    source_message: Mapped[Message | None] = relationship("Message", back_populates="prediction_events")
    evaluations: Mapped[list["ContactPredictionEvaluation"]] = relationship(
        "ContactPredictionEvaluation",
        back_populates="event",
        cascade="all, delete-orphan",
        order_by="ContactPredictionEvaluation.horizon_code",
    )


class ContactPredictionEvaluation(Base):
    __tablename__ = "contact_prediction_evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(Integer, ForeignKey("contact_prediction_events.id"), index=True)
    horizon_code: Mapped[str] = mapped_column(String(16), index=True)
    benchmark_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    evaluation_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    benchmark_entry: Mapped[float | None] = mapped_column(Float, nullable=True)
    benchmark_evaluation: Mapped[float | None] = mapped_column(Float, nullable=True)
    absolute_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    excess_return: Mapped[float | None] = mapped_column(Float, nullable=True)
    direction_hit: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    event_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime, index=True, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    event: Mapped[ContactPredictionEvent] = relationship("ContactPredictionEvent", back_populates="evaluations")


class ContactScoreSnapshot(Base):
    __tablename__ = "contact_score_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contact_id: Mapped[str] = mapped_column(String, ForeignKey("contacts.id"), index=True)
    score_total: Mapped[float] = mapped_column(Float, default=50)
    score_auto: Mapped[float] = mapped_column(Float, default=50)
    score_manual: Mapped[float] = mapped_column(Float, default=50)
    accuracy_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    service_value_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    direction_accuracy_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    excess_return_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_alert_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    consistency_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    hit_rate_overall: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy_1m: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy_3m: Mapped[float | None] = mapped_column(Float, nullable=True)
    accuracy_1y: Mapped[float | None] = mapped_column(Float, nullable=True)
    excess_mean: Mapped[float | None] = mapped_column(Float, nullable=True)
    stability_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    frequency_penalty: Mapped[float | None] = mapped_column(Float, nullable=True)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    as_of: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    contact: Mapped[Contact] = relationship("Contact", back_populates="score_snapshots")


class ContactFocusSetting(Base):
    __tablename__ = "contact_focus_settings"

    contact_id: Mapped[str] = mapped_column(String, ForeignKey("contacts.id"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ContactSignalCluster(Base):
    __tablename__ = "contact_signal_clusters"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    contact_id: Mapped[str] = mapped_column(String, ForeignKey("contacts.id"), index=True)
    topic_key: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    event_kind: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    direction: Mapped[str | None] = mapped_column(String(32), index=True, nullable=True)
    primary_asset_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    merged_event_count: Mapped[int] = mapped_column(Integer, default=0)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime, index=True, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, index=True, nullable=True)
    cluster_status: Mapped[str | None] = mapped_column(String(32), default="active")
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ContactValueMetricSnapshot(Base):
    __tablename__ = "contact_value_metric_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contact_id: Mapped[str] = mapped_column(String, ForeignKey("contacts.id"), index=True)
    roadshow_value_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    exchange_value_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    timeliness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    coverage_depth_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    signal_cleanliness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    as_of: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ContactScoringCase(Base):
    __tablename__ = "contact_scoring_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    contact_id: Mapped[str] = mapped_column(String, ForeignKey("contacts.id"), index=True)
    case_type: Mapped[str] = mapped_column(String(32), index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_message_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("messages.id"), nullable=True)
    topic_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    asset_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    horizon_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    score_impact: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String)  # ai_reply/summary/send
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String, default="pending")
    result: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SendCampaign(Base):
    __tablename__ = "send_campaigns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_parts: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    attachments: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    channel: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    target_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    deliveries: Mapped[list["SendDelivery"]] = relationship(
        "SendDelivery",
        back_populates="campaign",
        cascade="all, delete-orphan",
        order_by="SendDelivery.id",
    )


class SendDelivery(Base):
    __tablename__ = "send_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    campaign_id: Mapped[int] = mapped_column(Integer, ForeignKey("send_campaigns.id"), index=True)
    target_id: Mapped[str] = mapped_column(String(255), index=True)
    target_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rendered_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_parts: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    attachment_snapshot: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    channel: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    campaign: Mapped[SendCampaign] = relationship("SendCampaign", back_populates="deliveries")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String)
    time_range: Mapped[str | None] = mapped_column(String)
    filters: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String, default="pending")
    result_type: Mapped[str | None] = mapped_column(String)  # html/markdown/json
    result_body: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    artifacts: Mapped[list["ReportArtifact"]] = relationship(
        "ReportArtifact",
        back_populates="report",
        cascade="all, delete-orphan",
        order_by="ReportArtifact.sequence",
    )


class AnalysisSnapshot(Base):
    __tablename__ = "analysis_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope_key: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    filters: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    options: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    message_ids: Mapped[list[int] | None] = mapped_column(JSON, nullable=True)
    messages: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    contact_ratings: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String, default="ready")
    message_count: Mapped[int] = mapped_column(Integer, default=0)
    time_from: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    time_to: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Interaction(Base):
    __tablename__ = "interactions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    message_id: Mapped[int] = mapped_column(Integer, ForeignKey("messages.id"), index=True)
    kind: Mapped[str] = mapped_column(String)  # 约/问/答/顶/踩
    payload: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class InteractionExt(Base):
    __tablename__ = "interactions_ext"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kind: Mapped[str] = mapped_column(String)
    payload: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SyncState(Base):
    __tablename__ = "sync_state"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str | None] = mapped_column(String, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ReportArtifact(Base):
    __tablename__ = "report_artifacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(Integer, ForeignKey("reports.id"), index=True)
    module: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    sequence: Mapped[int] = mapped_column(Integer, default=0)
    data_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    data_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    report: Mapped[Report] = relationship("Report", back_populates="artifacts")


# ===============
# New: Mail & Ext Adapters
# ===============

class EmailAccount(Base):
    """Outgoing/incoming mail account configuration.

    Note: Credentials are stored in JSON for flexibility (username/password/oauth).
    In production, consider encrypting the password at rest and masking in APIs.
    """

    __tablename__ = "email_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128))  # display name in UI
    email_address: Mapped[str] = mapped_column(String(255), index=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)  # gmail/qq/outlook/custom
    imap_host: Mapped[str] = mapped_column(String(255))
    imap_port: Mapped[int] = mapped_column(Integer, default=993)
    imap_ssl: Mapped[bool] = mapped_column(Boolean, default=True)
    smtp_host: Mapped[str] = mapped_column(String(255))
    smtp_port: Mapped[int] = mapped_column(Integer, default=465)
    smtp_ssl: Mapped[bool] = mapped_column(Boolean, default=True)
    auth: Mapped[dict] = mapped_column(JSON, default=dict)  # {username, password, oauth_token?}
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class EmailMessage(Base):
    """Persisted email headers and light body for listing/search.

    Attachments and full raw bodies are omitted for now to keep the DB light.
    """

    __tablename__ = "email_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(Integer, ForeignKey("email_accounts.id"), index=True)
    external_id: Mapped[str | None] = mapped_column(String(255), index=True)  # Message-ID/UID
    thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(512), nullable=True)
    from_addr: Mapped[str | None] = mapped_column(String(255), nullable=True)
    to_addrs: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    cc_addrs: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    bcc_addrs: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    direction: Mapped[str] = mapped_column(String(8), default="in")  # in/out
    snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    flags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)  # seen/flagged/etc
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    derived: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class ExtAdapter(Base):
    """Configured external adapter (e.g., langbot adapters for telegram/qq/feishu)."""

    __tablename__ = "ext_adapters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), unique=True, index=True)  # e.g., telegram, qq, feishu
    name: Mapped[str] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    source_type: Mapped[str] = mapped_column(String(32), default="langbot")
    config: Mapped[dict] = mapped_column(JSON, default=dict)  # e.g., {log_dir, api_base, token}
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AdapterMessage(Base):
    """Messages ingested from adapters' logs/APIs, displayed in extension tabs."""

    __tablename__ = "adapter_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    adapter_key: Mapped[str] = mapped_column(String(64), index=True)
    external_id: Mapped[str | None] = mapped_column(String(255), index=True)
    chat_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    sender: Mapped[str | None] = mapped_column(String(128), nullable=True)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    direction: Mapped[str] = mapped_column(String(8), default="in")  # in/out
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
