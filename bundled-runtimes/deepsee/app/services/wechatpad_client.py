from __future__ import annotations

import requests
from urllib.parse import urlparse
from typing import Dict, Any, List
from ..config import settings
from .llm_client import load_ai_config


class WeChatPadClient:
    def __init__(self, base: str | None = None, text_path: str | None = None, wxid: str | None = None):
        # Prefer explicit args; then dynamic ai_config; finally .env settings
        if base is None or text_path is None:
            try:
                conf = load_ai_config()
            except Exception:
                conf = {}
        else:
            conf = {}
        resolved_base = base or conf.get("wechatpad_http_base") or settings.WECHATPAD_HTTP_BASE or ""
        resolved_path = text_path or conf.get("wechatpad_text_path") or settings.WECHATPAD_TEXT_PATH or "/api/v1/message/sendText"
        resolved_wxid = wxid or conf.get("wechatpad_wxid") or ""
        self.base = str(resolved_base).rstrip("/")
        self.text_path = self._normalize_path(resolved_path)
        self.wxid = str(resolved_wxid).strip()
        # Disable environment proxies to avoid local proxy interfering with LAN endpoints
        try:
            self._session = requests.Session()
            self._session.trust_env = False
        except Exception:
            self._session = None

    @staticmethod
    def _normalize_path(value: str | None) -> str:
        raw = (value or "").strip()
        if not raw:
            return "/api/v1/message/sendText"
        # Accept full URL pasted by user; keep only path component.
        # Also handle accidental leading "/" before full URL (e.g., "/http://host/...").
        candidate = raw[1:] if raw.startswith("/http://") or raw.startswith("/https://") else raw
        if candidate.startswith("http://") or candidate.startswith("https://"):
            try:
                parsed = urlparse(candidate)
                raw = parsed.path or "/"
            except Exception:
                raw = "/"
        if not raw.startswith("/"):
            raw = "/" + raw
        return raw

    def configured(self) -> bool:
        return bool(self.base)

    def send_text(self, to_user: str, text: str) -> Dict[str, Any]:
        if not self.configured():
            raise RuntimeError("WeChatPadPro base not configured")
        url = f"{self.base}{self.text_path}"
        # Try common payload shapes used by WeChatPad variants.
        is_room = to_user.endswith("@chatroom")
        is_wechat8061 = self.text_path.lower().endswith("/msg/sendtxt") or self.text_path.lower() == "/api/msg/sendtxt"
        payloads = [
            {"toUserName": to_user, "content": text},
            {"toUserName": to_user, "text": text},
            {"to": to_user, "content": text},
            {"wxid": to_user, "content": text},
        ]
        # wechat8061 / wechat-go (port 1238) expects Wxid/ToWxid/Content/Type
        if self.wxid:
            payloads = [
                {"Wxid": self.wxid, "ToWxid": to_user, "Content": text, "Type": 1},
                {"wxid": self.wxid, "ToWxid": to_user, "Content": text, "Type": 1},
                {"wxid": self.wxid, "to_wxid": to_user, "content": text, "type": 1},
            ] + payloads
        if is_room:
            payloads = [
                {"toUserName": to_user, "content": text, "isRoom": True},
                {"room": to_user, "content": text},
            ] + payloads
        last_err: Exception | None = None
        for data in payloads:
            try:
                if self._session is not None:
                    r = self._session.post(url, json=data, timeout=8)
                else:
                    r = requests.post(url, json=data, timeout=8, proxies={"http": None, "https": None})
                if not r.ok:
                    # Keep last HTTP error to avoid masking useful diagnostics.
                    last_err = RuntimeError(f"HTTP {r.status_code}: {(r.text or '')[:200]}")
                    continue
                else:
                    # Consider JSON success conventions
                    try:
                        resp = r.json()
                    except Exception:
                        return {"status": "ok", "raw": r.text}

                    # Evaluate success from common fields (be strict when fields exist).
                    verdict: bool | None = None
                    if isinstance(resp, dict):
                        if isinstance(resp.get("ok"), bool):
                            verdict = bool(resp.get("ok"))
                        elif isinstance(resp.get("success"), (bool, int)):
                            verdict = bool(resp.get("success"))
                        elif isinstance(resp.get("Success"), (bool, int)):
                            verdict = bool(resp.get("Success"))
                        elif resp.get("code") is not None:
                            verdict = str(resp.get("code")) in {"0", "200"}
                        elif resp.get("Code") is not None:
                            verdict = str(resp.get("Code")) in {"0", "200"}
                        elif is_wechat8061 and resp.get("Data") is not None:
                            # WeChat 8061 often returns {Code:0, Data:{...}}
                            verdict = True

                    if verdict is True:
                        return {"status": "ok", "data": resp}

                    if verdict is False:
                        # Surface best-effort message for UI.
                        msg = ""
                        if isinstance(resp, dict):
                            msg = str(resp.get("Message") or resp.get("message") or resp.get("error") or "").strip()
                            code = resp.get("Code") if resp.get("Code") is not None else resp.get("code")
                            if code is not None:
                                msg = (f"Code={code} " + msg).strip()
                        raise RuntimeError(msg or "send failed")

                    # Unknown shape: return as-is for diagnostics.
                    return {"status": "unknown", "data": resp}
            except Exception as e:
                last_err = e
        if last_err:
            raise last_err
        raise RuntimeError("failed to send text via WeChatPadPro")

    def send_batch(self, items: List[Dict[str, str]]) -> Dict[str, Any]:
        results: List[Dict[str, Any]] = []
        for it in items:
            target = it.get("target") or it.get("talker") or it.get("chat_id")
            text = it.get("text") or it.get("aiReply") or it.get("ai_reply")
            if not target or not text:
                results.append({"ok": False, "error": "missing target/text", "item": it})
                continue
            try:
                resp = self.send_text(target, text)
                ok = bool(resp.get("status") == "ok")
                if ok:
                    results.append({"ok": True, "resp": resp})
                else:
                    results.append({"ok": False, "error": "send returned unknown status", "resp": resp})
            except Exception as e:
                results.append({"ok": False, "error": str(e)})
        return {"status": "ok", "results": results}
