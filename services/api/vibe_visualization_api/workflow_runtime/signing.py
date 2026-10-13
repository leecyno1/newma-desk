from __future__ import annotations

import hashlib
import hmac
import time


class WorkflowSignatureError(ValueError):
    """Raised when a signed workflow request cannot be trusted."""


class WorkflowRequestSigner:
    def __init__(self, secret: str, *, tolerance_seconds: int = 300):
        self._secret = secret.encode("utf-8")
        self._tolerance_seconds = tolerance_seconds

    @property
    def available(self) -> bool:
        return bool(self._secret)

    def sign(self, *, timestamp: str, scope: str, body: bytes) -> str:
        digest = hmac.new(
            self._secret,
            self._message(timestamp, scope, body),
            hashlib.sha256,
        ).hexdigest()
        return f"sha256={digest}"

    def verify(
        self,
        *,
        timestamp: str,
        signature: str,
        scope: str,
        body: bytes,
        now: float | None = None,
    ) -> None:
        if not self.available:
            raise WorkflowSignatureError("workflow signing is not configured")
        try:
            signed_at = int(timestamp)
        except ValueError as error:
            raise WorkflowSignatureError("invalid workflow signature timestamp") from error
        current = int(time.time() if now is None else now)
        if abs(current - signed_at) > self._tolerance_seconds:
            raise WorkflowSignatureError("workflow signature expired")
        expected = self.sign(timestamp=timestamp, scope=scope, body=body)
        if not hmac.compare_digest(signature, expected):
            raise WorkflowSignatureError("invalid workflow signature")

    @staticmethod
    def _message(timestamp: str, scope: str, body: bytes) -> bytes:
        return timestamp.encode("ascii") + b"\n" + scope.encode("utf-8") + b"\n" + body
