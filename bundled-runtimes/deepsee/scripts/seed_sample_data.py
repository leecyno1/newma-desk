#!/usr/bin/env python3
"""Seed demo chats/messages for AI summary testing."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import List, Dict

from sqlalchemy import select

from app.db import SessionLocal, init_db
from app.models import Chat, Contact, Message


SEED_KEY = "ai_summary_seed"
CHAT_ID = "demo_market_room"


def ensure_chat(session) -> Chat:
    chat = session.get(Chat, CHAT_ID)
    if not chat:
        chat = Chat(
            id=CHAT_ID,
            title="市场情报交流群",
            is_chatroom=True,
            type="group",
        )
        session.add(chat)
        session.flush()
    return chat


def ensure_contact(session, contact_id: str, name: str, rating: int) -> Contact:
    contact = session.get(Contact, contact_id)
    if not contact:
        contact = Contact(id=contact_id, name=name, rating=rating)
        session.add(contact)
    else:
        if contact.name != name:
            contact.name = name
        if rating and contact.rating != rating:
            contact.rating = rating
    return contact


def seed_messages(session) -> int:
    base_time = datetime.utcnow()
    contacts = [
        ("c_macro", "张宏观（中金公司）", 92),
        ("c_industry", "李行业（海通证券）", 89),
        ("c_company", "王公司（腾讯投资）", 90),
        ("c_strategy", "赵策略（华泰证券）", 88),
        ("c_sentiment", "陈情绪（银河证券）", 86),
        ("c_other", "孙其他（独立分析师）", 85),
    ]

    ensure_chat(session)
    for cid, name, rating in contacts:
        ensure_contact(session, cid, name, rating)

    seed_payload: List[Dict] = [
        {
            "sender_id": "c_macro",
            "sender_name": "张宏观（中金公司）",
            "content_text": "多家机构预计美联储9月降息25BP，专项债投向新基建，A股政策底逐步确立。",
        },
        {
            "sender_id": "c_industry",
            "sender_name": "李行业（海通证券）",
            "content_text": "AI算力需求持续攀升，关注光模块与服务器供应链，订单能见度已覆盖至2026年。",
        },
        {
            "sender_id": "c_company",
            "sender_name": "王公司（腾讯投资）",
            "content_text": "华为发布新款昇腾芯片，合作厂商交付节奏提前两季度，建议关注核心供应商。",
        },
        {
            "sender_id": "c_strategy",
            "sender_name": "赵策略（华泰证券）",
            "content_text": "建议以价保量配置龙头，利用事件驱动进行滚动操作，回避高杠杆地产企业。",
        },
        {
            "sender_id": "c_sentiment",
            "sender_name": "陈情绪（银河证券）",
            "content_text": "北向资金连续五日净流入，空头回补推动指数上行，但量能不足需关注回调压力。",
        },
        {
            "sender_id": "c_other",
            "sender_name": "孙其他（独立分析师）",
            "content_text": "若降息落地仍需观察经济数据修复力度，若复苏不及预期，可能掩盖结构性风险。",
        },
    ]

    inserted = 0
    for idx, payload in enumerate(seed_payload):
        timestamp = base_time - timedelta(minutes=5 * (len(seed_payload) - idx))
        existing = session.execute(
            select(Message)
            .where(
                Message.chat_id == CHAT_ID,
                Message.sender_id == payload["sender_id"],
                Message.content_text == payload["content_text"],
            )
            .order_by(Message.id.desc())
        ).scalars().first()
        if existing and isinstance(existing.meta, dict) and existing.meta.get(SEED_KEY):
            continue
        message = Message(
            chat_id=CHAT_ID,
            talker_name="市场情报交流群",
            sender_id=payload["sender_id"],
            sender_name=payload["sender_name"],
            timestamp=timestamp,
            direction="in",
            type="text",
            content_text=payload["content_text"],
            meta={SEED_KEY: True},
            importance_score=80,
        )
        session.add(message)
        inserted += 1
    return inserted


def main() -> None:
    init_db()
    session = SessionLocal()
    try:
        inserted = seed_messages(session)
        session.commit()
        print(f"Inserted {inserted} demo messages into chat {CHAT_ID}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
