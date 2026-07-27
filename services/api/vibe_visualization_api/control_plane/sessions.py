import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


class ModSessionError(Exception):
    """Raised when a Mod capability token is missing, invalid, or expired."""


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(value + padding)
    except (ValueError, TypeError) as error:
        raise ModSessionError("invalid Mod session token") from error


@dataclass(frozen=True)
class ModSessionClaims:
    session_id: str
    instance_id: str
    user_id: str
    workspace_id: str
    module_id: str
    revision: int
    actions: tuple[str, ...]
    permissions: tuple[str, ...]
    issued_at: int
    expires_at: int

    @property
    def expires_at_iso(self) -> str:
        return datetime.fromtimestamp(self.expires_at, UTC).isoformat()


class ModSessionService:
    def __init__(self, secret: str, *, ttl_seconds: int = 900):
        self._secret = (secret or secrets.token_urlsafe(32)).encode("utf-8")
        self._ttl_seconds = ttl_seconds

    def issue(
        self,
        *,
        instance_id: str,
        user_id: str,
        workspace_id: str,
        module_id: str,
        revision: int,
        actions: list[str],
        permissions: list[str],
    ) -> tuple[str, ModSessionClaims]:
        now = int(time.time())
        claims = {
            "v": 1,
            "sid": f"mod-session-{secrets.token_urlsafe(12)}",
            "iid": instance_id,
            "sub": user_id,
            "wid": workspace_id,
            "mid": module_id,
            "rev": revision,
            "act": sorted(set(actions)),
            "prm": sorted(set(permissions)),
            "iat": now,
            "exp": now + self._ttl_seconds,
            "nonce": secrets.token_urlsafe(8),
        }
        encoded = _encode(
            json.dumps(
                claims,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        signature = _encode(
            hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest()
        )
        return f"{encoded}.{signature}", self._claims(claims)

    def validate(self, token: str) -> ModSessionClaims:
        if not token or len(token) > 16_384:
            raise ModSessionError("invalid Mod session token")
        try:
            encoded, signature = token.split(".", 1)
        except ValueError as error:
            raise ModSessionError("invalid Mod session token") from error
        expected = _encode(
            hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(signature, expected):
            raise ModSessionError("invalid Mod session token")
        try:
            raw: Any = json.loads(_decode(encoded))
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise ModSessionError("invalid Mod session token") from error
        if not isinstance(raw, dict):
            raise ModSessionError("invalid Mod session token")
        claims = self._claims(raw)
        now = int(time.time())
        if claims.expires_at <= now or claims.issued_at > now + 60:
            raise ModSessionError("expired Mod session token")
        return claims

    @staticmethod
    def _claims(raw: dict[str, Any]) -> ModSessionClaims:
        try:
            version = raw["v"]
            session_id = raw["sid"]
            instance_id = raw["iid"]
            user_id = raw["sub"]
            workspace_id = raw["wid"]
            module_id = raw["mid"]
            revision = raw["rev"]
            actions = raw["act"]
            permissions = raw["prm"]
            issued_at = raw["iat"]
            expires_at = raw["exp"]
        except KeyError as error:
            raise ModSessionError("invalid Mod session token") from error
        if (
            version != 1
            or not isinstance(session_id, str)
            or not isinstance(instance_id, str)
            or not 1 <= len(instance_id) <= 128
            or not isinstance(user_id, str)
            or not isinstance(workspace_id, str)
            or not isinstance(module_id, str)
            or not isinstance(revision, int)
            or not isinstance(actions, list)
            or not all(isinstance(item, str) for item in actions)
            or not isinstance(permissions, list)
            or not all(isinstance(item, str) for item in permissions)
            or not isinstance(issued_at, int)
            or not isinstance(expires_at, int)
        ):
            raise ModSessionError("invalid Mod session token")
        return ModSessionClaims(
            session_id=session_id,
            instance_id=instance_id,
            user_id=user_id,
            workspace_id=workspace_id,
            module_id=module_id,
            revision=revision,
            actions=tuple(actions),
            permissions=tuple(permissions),
            issued_at=issued_at,
            expires_at=expires_at,
        )


def bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise ModSessionError("Mod session token is required")
    scheme, separator, token = authorization.partition(" ")
    if separator != " " or scheme.casefold() != "bearer" or not token:
        raise ModSessionError("Mod session token is required")
    return token
