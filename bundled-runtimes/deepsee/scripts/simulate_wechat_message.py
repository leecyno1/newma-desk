#!/usr/bin/env python3
"""
完整链路模拟：模拟微信用户发消息 → 0913 回调 → Hermes 处理 → 回复

绕过 wechatapi.net，直接 POST 到 0913 /api/wechat-gateway/callback，
触发完整的 ingest → hermes_bridge → reply → record_outbound 链路。
"""

import json, time, sys, requests

# ── 配置 ──
GATEWAY_URL = "http://127.0.0.1:8001"
CALLBACK_URL = f"{GATEWAY_URL}/api/wechat-gateway/callback"

# ── 模拟微信用户 ──
# 你希望我当天模拟谁给我发微信？
# 这里放两个测试账号做例子
SIMULATED_CHATS = [
    {
        "name": "测试 1：王杨在 2057 群里发消息",
        "chat_id": "20570037229@chatroom",
        "from_user": "20570037229@chatroom",
        "sender_name": "王杨",
        "text": "GRPO算法和PPO的核心区别是什么？请简短回答",
    },
    {
        "name": "测试 2：wenliang 私聊发消息",
        "chat_id": "wxid_1234952349421",
        "from_user": "wxid_1234952349421",
        "sender_name": "wenliang",
        "text": "美债上了这么多对A股有什么影响",
    },
]


def simulate_wechat_callback(chat_id: str, from_user: str, sender_name: str, text: str):
    """
    模拟 wechatapi.net 转发微信回调给 0913
    格式和真实回调完全一致
    """
    import random

    msg_id = int(time.time() * 1000) + random.randint(1, 9999)

    # wechatapi.net 的 JSON 格式（已将微信 XML 转成 JSON）
    payload = {
        "Appid": "test_app_001",
        "TypeName": "AddMsg",
        "Wxid": "wxid_self_account",
        "Data": {
            "MsgId": str(msg_id),
            "NewMsgId": str(msg_id),
            "MsgType": 1,  # 文本消息
            "FromUserName": from_user,
            "ToUserName": "wxid_self_account",
            "Content": f"{sender_name}:\n{text}" if chat_id.endswith("@chatroom") else text,
            "CreateTime": int(time.time()),
        },
    }

    # 打印发送的内容
    group_indicator = " [群聊]" if chat_id.endswith("@chatroom") else ""
    print(f"\n{'─'*60}")
    print(f"📱 模拟微信消息{group_indicator}")
    print(f"   chat_id: {chat_id}")
    print(f"   sender:  {sender_name}")
    print(f"   text:    {text}")
    print(f"{'─'*60}")

    start = time.time()
    try:
        resp = requests.post(
            CALLBACK_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=120,
        )
        elapsed = time.time() - start
        body = resp.json() if resp.text else {}
    except requests.ConnectionError:
        print(f"\n❌ 无法连接 0913 Gateway ({GATEWAY_URL})")
        print("   请确认 0913 正在运行: bash scripts/manage.sh status")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        return

    # ── 分析响应 ──
    print(f"\nHTTP {resp.status_code} | 耗时 {elapsed:.1f}s")

    # 回调是否成功入库
    stored = body.get("stored") if isinstance(body, dict) else None
    duplicate = body.get("duplicate") if isinstance(body, dict) else None
    auto_reply_status = body.get("auto_reply", {}).get("status") if isinstance(body.get("auto_reply"), dict) else None

    print(f"   ingest:  stored={stored}, duplicate={duplicate}")

    # 自动回复
    auto_reply = body.get("auto_reply") if isinstance(body, dict) else {}
    if auto_reply:
        status = auto_reply.get("status", "?")
        reply_text = auto_reply.get("reply", auto_reply.get("error", ""))
        if isinstance(reply_text, str) and len(reply_text) > 300:
            reply_text = reply_text[:300] + "..."
        print(f"   auto_reply: status={status}")
        if reply_text:
            print(f"   reply: {reply_text}")
        if status == "sent":
            provider = auto_reply.get("provider_result", {})
            if provider:
                print(f"   provider: msgId={provider.get('msgId', '?')}")

    # ── 查询 DB 中的消息 ──
    try:
        messages_resp = requests.get(
            f"{GATEWAY_URL}/api/messages",
            params={"chat_id": chat_id, "limit": 3},
            headers={"Authorization": f"Bearer iv19whot"},
            timeout=10,
        )
        if messages_resp.status_code == 200:
            msgs = messages_resp.json()
            if isinstance(msgs, list):
                print(f"\n   DB 最近消息:")
                for m in reversed(msgs[-3:]):
                    direction = "⬅️ IN" if m.get("direction") == "in" else "➡️ OUT"
                    content = str(m.get("content_text", ""))[:80]
                    sender = m.get("sender_name", "?")
                    ts = m.get("timestamp", "")[:19] if m.get("timestamp") else ""
                    print(f"   {ts} {direction} [{sender}] {content}")
    except Exception:
        pass


if __name__ == "__main__":
    print("╔══════════════════════════════════════════╗")
    print("║  0913 → Hermes 完整链路模拟             ║")
    print("╚══════════════════════════════════════════╝")
    print(f"Gateway: {GATEWAY_URL}")
    print(f"Callback: {CALLBACK_URL}")

    for case in SIMULATED_CHATS:
        simulate_wechat_callback(
            chat_id=case["chat_id"],
            from_user=case["from_user"],
            sender_name=case["sender_name"],
            text=case["text"],
        )

    print(f"\n{'='*60}")
    print("模拟完成")
    print(f"{'='*60}")
