"""Deterministic publication decisions for governed research layers."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from seven_cycle_platform.governance.baseline import EvidenceStatus
from seven_cycle_platform.registry.models import CycleId
from seven_cycle_platform.types import (
    FreshnessStatus,
    PublicationGateStatus,
    VintageKind,
)


ResearchLayer = Literal["historical", "realtime", "forecast", "asset_statistics"]
GateReasonCode = Literal[
    "configured_block",
    "configured_policy",
    "data_unavailable",
    "historical_evidence_not_formal",
    "model_not_qualified",
    "period_unidentified",
    "pseudo_vintage",
    "stale_input",
]


class GateInput(BaseModel):
    """Strict immutable inputs for one cycle-layer publication decision."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    cycle_id: CycleId
    layer: ResearchLayer
    configured_status: PublicationGateStatus
    evidence_status: EvidenceStatus
    vintage_kind: VintageKind
    freshness: FreshnessStatus
    model_qualified: bool | None

    @model_validator(mode="after")
    def validate_cross_field_contract(self) -> Self:
        if self.configured_status is PublicationGateStatus.SCENARIO_ONLY and (
            self.cycle_id != "C1" or self.layer != "historical"
        ):
            raise ValueError("scenario_only is allowed only for C1 historical")
        if self.configured_status is PublicationGateStatus.CALENDAR_ONLY and (
            self.cycle_id != "C6" or self.layer not in {"historical", "forecast"}
        ):
            raise ValueError(
                "calendar_only is allowed only for C6 historical or forecast"
            )
        if (
            self.configured_status is PublicationGateStatus.SCENARIO_ONLY
            and self.evidence_status not in {"scenario_supported", "explanatory_only"}
        ):
            raise ValueError(
                "scenario_only requires scenario-supported or explanatory evidence"
            )
        if (
            self.configured_status is PublicationGateStatus.CALENDAR_ONLY
            and self.evidence_status != "calendar_defined"
        ):
            raise ValueError("calendar_only requires calendar_defined evidence")
        if self.layer == "forecast":
            if self.configured_status is PublicationGateStatus.CALENDAR_ONLY:
                if self.model_qualified is not None:
                    raise ValueError(
                        "model_qualified must be None for calendar_only forecasts"
                    )
            elif self.model_qualified is None:
                raise ValueError(
                    "model_qualified must be an explicit bool for forecast layers"
                )
        if self.layer != "forecast" and self.model_qualified is not None:
            raise ValueError("model_qualified must be None for non-forecast layers")
        return self


class GateDecision(BaseModel):
    """Strict immutable result with stable machine-readable reasons."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    cycle_id: CycleId
    layer: ResearchLayer
    status: PublicationGateStatus
    reason_codes: tuple[GateReasonCode, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_reason_codes(self) -> Self:
        if len(self.reason_codes) != len(set(self.reason_codes)):
            raise ValueError("reason_codes must be unique")
        return self


def _decision(
    request: GateInput,
    status: PublicationGateStatus,
    *reason_codes: GateReasonCode,
) -> GateDecision:
    return GateDecision(
        cycle_id=request.cycle_id,
        layer=request.layer,
        status=status,
        reason_codes=reason_codes,
    )


def evaluate_gate(request: GateInput) -> GateDecision:
    """Apply deterministic publication blocks and layer-specific limits."""

    if request.evidence_status == "unidentified":
        return _decision(
            request,
            PublicationGateStatus.BLOCKED,
            "period_unidentified",
        )

    if (
        request.vintage_kind is VintageKind.UNAVAILABLE
        or request.freshness is FreshnessStatus.UNAVAILABLE
    ):
        return _decision(
            request,
            PublicationGateStatus.BLOCKED,
            "data_unavailable",
        )

    if request.configured_status is PublicationGateStatus.BLOCKED:
        return _decision(
            request,
            PublicationGateStatus.BLOCKED,
            "configured_block",
        )

    if request.configured_status is PublicationGateStatus.CALENDAR_ONLY:
        return _decision(
            request,
            PublicationGateStatus.CALENDAR_ONLY,
            "configured_policy",
        )

    status = request.configured_status
    reason_codes: list[GateReasonCode] = []

    if request.layer == "realtime" and request.vintage_kind is not VintageKind.REALTIME:
        status = PublicationGateStatus.LIMITED
        reason_codes.append("pseudo_vintage")

    if request.layer == "forecast":
        if request.model_qualified is not True:
            return _decision(
                request,
                PublicationGateStatus.BLOCKED,
                "model_not_qualified",
            )
        if request.freshness is FreshnessStatus.STALE:
            status = PublicationGateStatus.LIMITED
            reason_codes.append("stale_input")

    if request.layer == "asset_statistics" and request.evidence_status != "supported":
        return _decision(
            request,
            PublicationGateStatus.BLOCKED,
            "historical_evidence_not_formal",
        )

    if not reason_codes:
        reason_codes.append("configured_policy")

    return _decision(request, status, *reason_codes)
