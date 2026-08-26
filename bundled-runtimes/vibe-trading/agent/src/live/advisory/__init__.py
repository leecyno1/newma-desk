"""Pre-trade advisory interface — observational risk assessments on live orders.

The advisory layer sits **outside** the mandate gate. It provides a
broker-agnostic hook for external services (e.g. invinoveritas ``/review``,
local rule engines, MCP advisory providers) to render a *risk opinion* on a
proposed order. Advisory verdicts are **purely observational**: they never block,
deny, or alter order execution. The mandate gate
(:func:`src.live.enforcement.check_mandate`) remains the sole authority for
order allow/deny decisions.

Key design principles:

* **Fail-open**: any provider exception is caught and converted to
  :attr:`Verdict.REVIEW_UNAVAILABLE` — the order proceeds unaffected.
* **Default-off**: advisory review is activated only when the environment
  variable ``VIBE_TRADING_ENABLE_ADVISORY`` is set to a truthy value.
* **Broker-agnostic**: :class:`AdvisoryContext` decouples providers from
  broker-specific payload shapes, carrying only the normalized fields a risk
  reviewer needs.
* **Audit-embedded**: the aggregated verdict is included in the existing
  ``gate_decision["advisory"]`` audit field — no new audit event kind.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class Verdict(str, Enum):
    """Advisory verdict on a proposed order.

    Values align with the invinoveritas ``/review`` contract (``approve``,
    ``approve_with_concerns``, ``reject``) plus a fourth ``review_unavailable``
    sentinel emitted when a provider fails or times out.
    """

    APPROVE = "approve"
    APPROVE_WITH_CONCERNS = "approve_with_concerns"
    REJECT = "reject"
    REVIEW_UNAVAILABLE = "review_unavailable"


# Severity ordering for worst-case aggregation: higher index = more severe.
_VERDICT_SEVERITY: dict[Verdict, int] = {
    Verdict.APPROVE: 0,
    Verdict.APPROVE_WITH_CONCERNS: 1,
    Verdict.REVIEW_UNAVAILABLE: 2,
    Verdict.REJECT: 3,
}


@dataclass(frozen=True)
class AdvisoryContext:
    """Broker-agnostic input for an advisory review.

    Carries the normalized fields a risk reviewer needs, decoupled from any
    specific broker's order payload or account snapshot shape.

    Attributes:
        symbol: Normalized upper-case symbol (e.g. ``AAPL``, ``BTC-USDT``).
        side: ``"buy"`` or ``"sell"``.
        notional_usd: Order notional in USD.
        account_equity: Current account equity in USD.
        utilization_ratio: Funding utilization as a fraction (0.0 = unused,
            1.0 = fully utilized). Approximated from mandate funding cap
            when the broker does not supply a high-water mark.
        open_position_count: Number of currently open positions.
        total_exposure_usd: Sum of all open position market values in USD.
        funding_usd: Mandate's ``account_funding_usd`` (the committed capital
            ceiling).
    """

    symbol: str
    side: str
    notional_usd: float
    account_equity: float
    utilization_ratio: float
    open_position_count: int
    total_exposure_usd: float
    funding_usd: float


@dataclass(frozen=True)
class AdvisoryResult:
    """Output from a single advisory provider.

    Attributes:
        verdict: The provider's assessment of the proposed order.
        confidence: Optional confidence score in ``[0.0, 1.0]``.
        summary: Short human-readable summary of the assessment.
        concerns: Tuple of concern strings (may be empty).
        provider: Identifier of the originating provider.
        detail: Arbitrary provider-specific metadata.
        created_at: ISO-8601 UTC timestamp, auto-filled on construction.
    """

    verdict: Verdict
    confidence: float | None = None
    summary: str = ""
    concerns: tuple[str, ...] = ()
    provider: str = ""
    detail: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            object.__setattr__(
                self,
                "created_at",
                datetime.now(timezone.utc).isoformat(),
            )


class PreTradeAdvisoryInterface(ABC):
    """Abstract base for pre-trade advisory providers.

    Implementations must expose a :attr:`provider_id` and implement
    :meth:`review`. The orchestrator catches all exceptions from ``review()``
    and converts them to :attr:`Verdict.REVIEW_UNAVAILABLE`, so providers may
    raise freely on internal failure.
    """

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """Unique identifier for this advisory provider."""

    @abstractmethod
    def review(self, context: AdvisoryContext) -> AdvisoryResult:
        """Assess the proposed order described by *context*.

        Args:
            context: Normalized pre-trade context.

        Returns:
            An :class:`AdvisoryResult` carrying the provider's verdict.
        """


@dataclass(frozen=True)
class AggregatedVerdict:
    """Aggregated result from running all advisory providers.

    The overall :attr:`verdict` is the **worst-case** across all individual
    provider results (most severe verdict wins).

    Attributes:
        verdict: Worst-case verdict across all providers.
        results: Tuple of individual provider results.
    """

    verdict: Verdict
    results: tuple[AdvisoryResult, ...]

    @property
    def all_concerns(self) -> tuple[str, ...]:
        """Flattened de-duplicated concerns from every provider result."""
        seen: list[str] = []
        seen_set: set[str] = set()
        for result in self.results:
            for concern in result.concerns:
                if concern not in seen_set:
                    seen.append(concern)
                    seen_set.add(concern)
        return tuple(seen)


class AdvisoryOrchestrator:
    """Run advisory providers sequentially, aggregate worst-case verdict.

    Each provider's :meth:`~PreTradeAdvisoryInterface.review` is called in
    order. Any exception is caught and converted to an
    :class:`AdvisoryResult` with :attr:`Verdict.REVIEW_UNAVAILABLE` so the
    order is never blocked by a failing advisory provider.

    Args:
        providers: Ordered list of advisory providers to consult.
    """

    def __init__(self, providers: list[PreTradeAdvisoryInterface]) -> None:
        self._providers = list(providers)

    @property
    def providers(self) -> list[PreTradeAdvisoryInterface]:
        """The configured provider list (read-only copy)."""
        return list(self._providers)

    def review(self, context: AdvisoryContext) -> AggregatedVerdict:
        """Run every provider and return the aggregated worst-case verdict.

        An empty provider list yields an :class:`AggregatedVerdict` with
        :attr:`Verdict.APPROVE` and no results — the caller may interpret this
        as "no advisory configured, proceed normally".

        Args:
            context: Normalized pre-trade context passed to each provider.

        Returns:
            Aggregated verdict with all individual results.
        """
        if not self._providers:
            return AggregatedVerdict(verdict=Verdict.APPROVE, results=())

        results: list[AdvisoryResult] = []
        for provider in self._providers:
            try:
                result = provider.review(context)
            except Exception as exc:
                logger.warning(
                    "advisory provider %s failed: %s",
                    getattr(provider, "provider_id", "<unknown>"),
                    exc,
                    exc_info=True,
                )
                result = AdvisoryResult(
                    verdict=Verdict.REVIEW_UNAVAILABLE,
                    summary=f"provider error: {type(exc).__name__}",
                    provider=getattr(provider, "provider_id", "<unknown>"),
                )
            results.append(result)

        worst = max(results, key=lambda r: _VERDICT_SEVERITY.get(r.verdict, 0))
        return AggregatedVerdict(
            verdict=worst.verdict,
            results=tuple(results),
        )


# -- Provider registry -------------------------------------------------------

_advisory_providers: list[PreTradeAdvisoryInterface] = []


def register_advisory_provider(provider: PreTradeAdvisoryInterface) -> None:
    """Register an advisory provider to be consulted on each review.

    Providers are consulted in registration order. Call
    :func:`clear_advisory_providers` to remove all registered providers.

    Args:
        provider: An advisory provider instance.
    """
    _advisory_providers.append(provider)


def clear_advisory_providers() -> None:
    """Remove all registered advisory providers."""
    _advisory_providers.clear()


def get_advisory_providers() -> list[PreTradeAdvisoryInterface]:
    """Return a copy of the current advisory provider list."""
    return list(_advisory_providers)


__all__ = [
    "AdvisoryContext",
    "AdvisoryOrchestrator",
    "AdvisoryResult",
    "AggregatedVerdict",
    "PreTradeAdvisoryInterface",
    "Verdict",
    "clear_advisory_providers",
    "get_advisory_providers",
    "register_advisory_provider",
]
