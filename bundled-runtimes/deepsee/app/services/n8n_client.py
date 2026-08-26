from __future__ import annotations

import requests
from typing import Any, Dict, List, Optional
from ..config import settings


class N8NClient:
    def __init__(self, auth_token: Optional[str] = None):
        self.auth = auth_token or settings.N8N_AUTH_TOKEN

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.auth:
            h["Authorization"] = f"Bearer {self.auth}"
        return h

    def post(self, url: str, payload: dict) -> dict:
        resp = requests.post(url, json=payload, headers=self._headers(), timeout=60)
        resp.raise_for_status()
        if resp.headers.get("content-type", "").startswith("application/json"):
            return resp.json()
        return {"raw": resp.text}

    def suggest_replies(self, message_context: dict) -> dict:
        if not settings.N8N_REPLY_WEBHOOK:
            return {"error": "N8N_REPLY_WEBHOOK not configured"}
        return self.post(settings.N8N_REPLY_WEBHOOK, message_context)

    def summary(self, summary_context: dict) -> dict:
        if not settings.N8N_SUMMARY_WEBHOOK:
            return {"error": "N8N_SUMMARY_WEBHOOK not configured"}
        return self.post(settings.N8N_SUMMARY_WEBHOOK, summary_context)

    def analyze_contacts(self, contact_context: dict) -> dict:
        if not settings.N8N_CONTACT_WEBHOOK:
            return {"error": "N8N_CONTACT_WEBHOOK not configured"}
        return self.post(settings.N8N_CONTACT_WEBHOOK, contact_context)

    def send(self, send_context: dict) -> dict:
        if not settings.N8N_SEND_WEBHOOK:
            return {"error": "N8N_SEND_WEBHOOK not configured"}
        return self.post(settings.N8N_SEND_WEBHOOK, send_context)

