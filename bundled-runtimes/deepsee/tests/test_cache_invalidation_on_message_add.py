"""验证问题1：缓存是否感知消息更新

测试场景：
1. 创建快照，生成缓存
2. 添加新消息到快照
3. 验证缓存 key 是否变化（message_count + updated_at）
4. 确认新的 summary 调用会跳过旧缓存
"""
import json
import os
import sys
import time
from datetime import datetime
from sqlalchemy.orm import Session

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.models import Message, AnalysisSnapshot, Contact
from app.services.snapshot_service import upsert_snapshot
from app.routers.ai import _build_snap_version
from app.db import SessionLocal


def test_cache_key_updates_on_message_count_change():
    """验证：message_count 变化 → cache key 变化"""
    db = SessionLocal()
    try:
        # Step 1: 创建初始快照（无消息）
        snap1 = upsert_snapshot(db, filters={"period": "1day"})
        db.commit()
        db.refresh(snap1)

        snap1_id = snap1.id
        snap1_count = snap1.message_count
        snap1_updated_at = snap1.updated_at

        # 生成第一个缓存 key
        key1 = _build_snap_version(str(snap1_id), "market", db)
        print(f"✓ Snapshot 1 created:")
        print(f"  - ID: {snap1_id}")
        print(f"  - message_count: {snap1_count}")
        print(f"  - updated_at: {snap1_updated_at}")
        print(f"  - cache_key: {key1}")

        # Step 2: 等待 1 秒以确保 updated_at 不同
        time.sleep(1.1)

        # Step 3: 添加测试消息
        test_msg = Message(
            chat_id="test_chat_cache_invalidation",
            sender_id="test_user_cache_invalidation",
            sender_name="测试用户",
            talker_name="测试会话",
            direction="in",
            type="text",
            content_text="Test message for cache invalidation with enough content to pass filters.",
            timestamp=datetime.utcnow(),
            derived={"summary": "cache invalidation test", "is_spam": False},
        )
        db.add(test_msg)
        db.commit()

        # Step 4: 重新生成快照（这会更新 message_count 和 updated_at）
        snap2 = upsert_snapshot(db, filters={"period": "1day"})
        db.commit()
        db.refresh(snap2)

        snap2_id = snap2.id
        snap2_count = snap2.message_count
        snap2_updated_at = snap2.updated_at

        # 生成第二个缓存 key
        key2 = _build_snap_version(str(snap2_id), "market", db)
        print(f"\n✓ Snapshot 2 created (after adding 1 message):")
        print(f"  - ID: {snap2_id}")
        print(f"  - message_count: {snap2_count}")
        print(f"  - updated_at: {snap2_updated_at}")
        print(f"  - cache_key: {key2}")

        # Step 5: 验证
        print(f"\n📊 Cache Key Comparison:")
        print(f"  - Key 1: {key1}")
        print(f"  - Key 2: {key2}")
        print(f"  - Keys different? {key1 != key2}")

        # 关键验证
        assert snap2_count > snap1_count, f"message_count 未增加: {snap1_count} -> {snap2_count}"
        assert snap2_updated_at > snap1_updated_at, f"updated_at 未更新: {snap1_updated_at} -> {snap2_updated_at}"
        assert key1 != key2, f"Cache key 未改变！这表示问题1未修复。key1={key1}, key2={key2}"

        print(f"\n✅ TEST PASSED: Cache key correctly invalidates on message count change")
    finally:
        db.close()


def test_snapshot_updated_at_initialized_correctly():
    """验证：新建 snapshot 时 updated_at 是否被正确初始化"""
    db = SessionLocal()
    try:
        before_create = datetime.utcnow()
        snap = upsert_snapshot(db, filters={"period": "3days"})
        db.commit()
        db.refresh(snap)
        after_create = datetime.utcnow()

        print(f"✓ Snapshot created:")
        print(f"  - created_at: {snap.created_at}")
        print(f"  - updated_at: {snap.updated_at}")
        print(f"  - Test time range: {before_create.isoformat()} ~ {after_create.isoformat()}")

        # 验证 updated_at 在创建时被初始化
        assert snap.updated_at is not None, "updated_at 为 None！"
        assert before_create <= snap.updated_at <= after_create, \
            f"updated_at 不在预期范围内: {snap.updated_at} not in [{before_create}, {after_create}]"

        print(f"\n✅ TEST PASSED: updated_at correctly initialized on snapshot creation")
    finally:
        db.close()


if __name__ == "__main__":
    print("\n" + "="*60)
    print("Testing Cache Invalidation on Message Updates (Problem #1)")
    print("="*60 + "\n")

    result1 = True
    try:
        test_snapshot_updated_at_initialized_correctly()
    except AssertionError:
        result1 = False
    print("\n" + "-"*60 + "\n")
    result2 = True
    try:
        test_cache_key_updates_on_message_count_change()
    except AssertionError:
        result2 = False

    print("\n" + "="*60)
    if result1 and result2:
        print("✅ All tests passed")
    else:
        print("❌ Some tests failed")
    print("="*60)
