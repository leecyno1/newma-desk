from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Iterator

from .settings import settings


@dataclass(frozen=True)
class CredentialBundle:
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    openai_model: str | None = None
    tushare_token: str | None = None
    tavily_api_key: str | None = None
    ima_client_id: str | None = None
    ima_api_key: str | None = None
    agent_secrets: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_settings(cls) -> "CredentialBundle":
        return cls(
            openai_api_key=settings.openai_api_key,
            openai_base_url=settings.openai_base_url,
            openai_model=settings.openai_model,
            tushare_token=settings.tushare_token,
            tavily_api_key=settings.tavily_api_key,
            ima_client_id=settings.ima_client_id,
            ima_api_key=settings.ima_api_key,
        )


_active_credentials: ContextVar[CredentialBundle | None] = ContextVar(
    "orchestra_active_credentials",
    default=None,
)


def current_credentials() -> CredentialBundle:
    return _active_credentials.get() or CredentialBundle.from_settings()


@contextmanager
def credential_scope(bundle: CredentialBundle) -> Iterator[None]:
    token = _active_credentials.set(bundle)
    try:
        yield
    finally:
        _active_credentials.reset(token)
