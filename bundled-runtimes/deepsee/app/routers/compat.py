from __future__ import annotations

from fastapi import APIRouter, Request
from ..services.n8n_client import N8NClient

router = APIRouter(tags=["compat"])


@router.post("/generate_ai_reply")
async def generate_ai_reply(req: Request):
    body = await req.json()
    text = body.get("message") or body.get("text") or ""
    prompt = body.get("prompt") or body.get("prompt_hint")
    message_id = body.get("message_id") or 0
    ctx = {
        "request_id": f"reply-{message_id}",
        "context": {"messages": [{"id": message_id, "text": text, "sender": "user", "ts": None}]},
        "prompt_hint": prompt,
    }
    client = N8NClient()
    try:
        resp = client.suggest_replies(ctx)
        # normalize
        suggestions = resp.get("suggestions") or []
        reply = ""
        if suggestions:
            first = suggestions[0]
            reply = first.get("text") if isinstance(first, dict) else str(first)
        return {"reply": reply or ""}
    except Exception as e:
        return {"reply": "", "error": str(e)}


@router.post("/send_to_n8n")
async def send_to_n8n(req: Request):
    body = await req.json()
    # accepted shapes: { aiReply, messageData:{ chat_id|talker_name } } or { items: [...] }
    items = body.get("items")
    if not items:
        target = (body.get("messageData") or {}).get("chat_id") or (body.get("messageData") or {}).get("talker_name") or body.get("target") or ""
        text = body.get("aiReply") or body.get("text") or ""
        items = [{"target": target, "text": text}]
    client = N8NClient()
    ctx = {"request_id": "send-compat", "items": items}
    try:
        resp = client.send(ctx)
        return resp
    except Exception as e:
        return {"error": str(e)}

