from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from vibe_visualization_api.finance_pilots.adapters import PilotExtractionAdapter
from vibe_visualization_api.finance_pilots.models import (
    DailyStockAnalysisContext,
    PilotStatusDocument,
    StrategyLedgerRecord,
)
from vibe_visualization_api.finance_pilots.policy import FinancePilotPolicy


class FinancePilotNotFoundError(KeyError):
    """Raised when a pilot is not registered at the extraction seam."""


class FinancePilotActivationError(RuntimeError):
    def __init__(self, pilot_id: str, reasons: list[str]):
        super().__init__(f"finance pilot {pilot_id} is unavailable")
        self.pilot_id = pilot_id
        self.reasons = reasons


class FinancePilotService:
    def __init__(
        self,
        policy: FinancePilotPolicy,
        adapters: list[PilotExtractionAdapter],
    ):
        self._policy = policy
        self._adapters = {adapter.pilot_id: adapter for adapter in adapters}

    def status(self) -> PilotStatusDocument:
        return PilotStatusDocument(pilots=self._policy.statuses())

    def adapt(
        self,
        pilot_id: str,
        payload: Mapping[str, Any],
    ) -> DailyStockAnalysisContext | StrategyLedgerRecord:
        adapter = self._adapters.get(pilot_id)
        if adapter is None:
            raise FinancePilotNotFoundError(pilot_id)
        status = self._policy.status(pilot_id)
        if not status.activatable:
            raise FinancePilotActivationError(pilot_id, status.reasons)
        return adapter.adapt(payload)
