import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any


def payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


class TradeConfirmationService:
    def __init__(self, secret: str, ttl_seconds: int = 300):
        self._secret = secret.encode("utf-8")
        self._ttl_seconds = ttl_seconds

    def issue(
        self,
        *,
        user_id: str,
        module_id: str,
        action_id: str,
        payload_hash: str,
    ) -> str:
        if not self._secret:
            raise ValueError("trade confirmation is not configured")
        claims = {
            "user_id": user_id,
            "module_id": module_id,
            "action_id": action_id,
            "payload_hash": payload_hash,
            "expires_at": int(time.time()) + self._ttl_seconds,
            "nonce": secrets.token_urlsafe(12),
        }
        encoded_claims = _encode(
            json.dumps(
                claims,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        signature = hmac.new(
            self._secret,
            encoded_claims.encode("ascii"),
            hashlib.sha256,
        ).digest()
        return f"{encoded_claims}.{_encode(signature)}"

    def validate(
        self,
        token: str | None,
        *,
        user_id: str,
        module_id: str,
        action_id: str,
        payload_hash: str,
    ) -> bool:
        if not token or not self._secret:
            return False
        try:
            encoded_claims, encoded_signature = token.split(".", 1)
            expected_signature = hmac.new(
                self._secret,
                encoded_claims.encode("ascii"),
                hashlib.sha256,
            ).digest()
            if not hmac.compare_digest(
                expected_signature,
                _decode(encoded_signature),
            ):
                return False
            claims = json.loads(_decode(encoded_claims))
        except (ValueError, TypeError):
            return False
        return (
            isinstance(claims, dict)
            and claims.get("user_id") == user_id
            and claims.get("module_id") == module_id
            and claims.get("action_id") == action_id
            and claims.get("payload_hash") == payload_hash
            and type(claims.get("expires_at")) is int
            and claims["expires_at"] >= int(time.time())
        )
