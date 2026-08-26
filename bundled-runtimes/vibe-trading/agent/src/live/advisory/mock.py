"""Mock advisory provider for testing.

:class:`MockAdvisory` is a configurable in-memory implementation of
:class:`~src.live.advisory.PreTradeAdvisoryInterface` that records every
invocation and supports deterministic verdict injection, optional delay, and
forced failure — everything a test suite needs to exercise the advisory
orchestrator and gate integration without any network dependency.
"""

from __future__ import annotations

import time

from src.live.advisory import (
    AdvisoryContext,
    AdvisoryResult,
    PreTradeAdvisoryInterface,
    Verdict,
)


class MockAdvisory(PreTradeAdvisoryInterface):
    """Configurable mock advisory provider.

    Args:
        verdict: Verdict to return on every :meth:`review` call.
        concerns: Concern strings attached to every result.
        summary: Summary text attached to every result.
        confidence: Optional confidence score in ``[0.0, 1.0]``.
        delay_s: Artificial delay in seconds before returning (simulates
            slow providers / timeout scenarios).
        raise_on_review: When ``True``, :meth:`review` raises
            :class:`RuntimeError` instead of returning a result.
        provider_id: Identifier stamped onto every result.
    """

    def __init__(
        self,
        verdict: Verdict = Verdict.APPROVE,
        concerns: tuple[str, ...] = (),
        summary: str = "",
        confidence: float | None = None,
        delay_s: float = 0,
        raise_on_review: bool = False,
        provider_id: str = "mock",
    ) -> None:
        self._verdict = verdict
        self._concerns = concerns
        self._summary = summary
        self._confidence = confidence
        self._delay_s = delay_s
        self._raise_on_review = raise_on_review
        self._provider_id = provider_id
        self.call_history: list[AdvisoryContext] = []

    @property
    def provider_id(self) -> str:
        """Unique identifier for this advisory provider."""
        return self._provider_id

    def review(self, context: AdvisoryContext) -> AdvisoryResult:
        """Return the configured verdict, or raise if configured to fail.

        Every invocation appends *context* to :attr:`call_history` before any
        delay or exception, so tests can assert the context was received even
        when the provider is configured to fail.

        Args:
            context: Normalized pre-trade context.

        Returns:
            An :class:`AdvisoryResult` carrying the injected verdict.

        Raises:
            RuntimeError: When ``raise_on_review`` is ``True``.
        """
        self.call_history.append(context)
        if self._delay_s > 0:
            time.sleep(self._delay_s)
        if self._raise_on_review:
            raise RuntimeError("mock advisory failure")
        return AdvisoryResult(
            verdict=self._verdict,
            concerns=self._concerns,
            summary=self._summary,
            confidence=self._confidence,
            provider=self._provider_id,
        )
