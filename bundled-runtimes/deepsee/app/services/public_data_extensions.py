"""Read-only grouped search and persisted scoring evidence."""
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..data_api_schemas import (SearchGroup, PageMeta, ScorecardData, PredictionData, EvaluationData)
from ..models import Chat, Contact, Message, EmailMessage, ContactPredictionEvent, ContactScoreSnapshot
from . import public_data as data

SEARCH_SOURCES = ("messages", "contacts", "chats", "emails", "news", "media", "mp", "meetings")


def search_groups(db, sources, q, limit, offset):
    database = {
        "messages": (Message, (Message.content_text, Message.sender_name, Message.talker_name)),
        "contacts": (Contact, (Contact.id, Contact.alias, Contact.name)),
        "chats": (Chat, (Chat.id, Chat.title)),
        "emails": (EmailMessage, (EmailMessage.subject, EmailMessage.body_text, EmailMessage.from_addr)),
    }
    groups = []
    for source in sources:
        if source not in database:
            page = data.snapshot_page(db, source, limit, offset, q)
            groups.append(SearchGroup(source=source, data=page.data, meta=page.meta))
            continue
        model, columns = database[source]
        rows = list(db.scalars(select(model).where(*data.text_search(q, *columns))
                               .order_by(model.id.desc()).offset(offset).limit(limit + 1)))
        more = len(rows) > limit
        rows = rows[:limit]
        if source == "messages":
            items = data.message_data(db, rows)
        else:
            serializer = {"contacts": data.contact_data, "chats": data.chat_data, "emails": data.email_data}[source]
            items = [serializer(row) for row in rows]
        groups.append(SearchGroup(source=source, data=items, meta=PageMeta(
            limit=limit, has_more=more, next_offset=offset + limit if more else None)))
    return groups


def scorecard_data(db, contact_id, limit, offset):
    from .contact_scoring import _contact_evidence
    if db.get(Contact, contact_id) is None:
        raise HTTPException(404, "not_found")
    events = list(db.scalars(select(ContactPredictionEvent)
        .options(selectinload(ContactPredictionEvent.evaluations))
        .where(ContactPredictionEvent.contact_id == contact_id)
        .order_by(ContactPredictionEvent.source_time.desc(), ContactPredictionEvent.id.desc())))
    evidence = _contact_evidence(events, datetime.now())
    snapshot = db.scalars(select(ContactScoreSnapshot).where(ContactScoreSnapshot.contact_id == contact_id)
                           .order_by(ContactScoreSnapshot.as_of.desc()).limit(1)).first()
    verified = bool(evidence["verified_samples"] and snapshot and snapshot.sample_size)
    predictions = []
    for event in events[offset:offset + limit]:
        evaluations = []
        for evaluation in event.evaluations:
            fields = {key: getattr(evaluation, key) for key in EvaluationData.model_fields if key != "evaluated_at"}
            evaluations.append(EvaluationData(**fields, evaluated_at=data.utc_time(evaluation.evaluated_at)))
        predictions.append(PredictionData(
            **{key: getattr(event, key) for key in PredictionData.model_fields if key not in {"source_time", "evaluations"}},
            source_time=data.utc_time(event.source_time), evaluations=evaluations))
    return ScorecardData(contact_id=contact_id, as_of=data.utc_time(snapshot.as_of) if snapshot else None,
        accuracy_score=snapshot.accuracy_score if verified else None,
        hit_rate_overall=snapshot.hit_rate_overall if verified else None,
        excess_mean=snapshot.excess_mean if verified else None, evidence=evidence, predictions=predictions,
        predictions_has_more=offset + limit < len(events), predictions_offset=offset)
