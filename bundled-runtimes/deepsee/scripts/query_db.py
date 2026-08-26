#!/usr/bin/env python3
"""查询 Deepsee SQLite 数据库：最近消息 + subsession 配置。"""
import os
import sqlite3
from pathlib import Path

DB = Path(
    os.environ.get(
        "DEEPSEE_DATABASE_PATH",
        Path(__file__).resolve().parents[1] / "data" / "app.db",
    )
)
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

# 最近 20 条消息
rows = conn.execute("""
    SELECT id, chat_id, sender_name, direction, content_text, timestamp
    FROM messages
    ORDER BY id DESC LIMIT 20
""").fetchall()

print("=== 最近 20 条消息 ===")
for r in reversed(rows):
    d = "IN " if r["direction"] == "in" else "OUT"
    ts = str(r["timestamp"] or "")[:19]
    txt = str(r["content_text"] or "")[:100]
    print(f"[{r['id']}] {ts} {d} [{r['sender_name'] or '?'}] {txt}")

# subsession 配置
print("\n=== subsession 配置 ===")
subs = conn.execute("SELECT * FROM wechat_subsessions").fetchall()
for s in subs:
    prompt = (s["system_prompt"] or "")[:120]
    print(f"  id={s['id']} enabled={s['enabled']} prompt={prompt}")

# API token
print("\n=== API token ===")
tokens = conn.execute("SELECT value FROM sync_state WHERE key='api_token'").fetchone()
if tokens:
    print(f"  api_token={tokens[0][:20]}...")

conn.close()
