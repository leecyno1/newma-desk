from pydantic import ValidationError
import pytest

import seven_cycle_platform.governance as governance
from seven_cycle_platform.governance.gates import (
    GateDecision,
    GateInput,
    evaluate_gate,
)
from seven_cycle_platform.types import (
    FreshnessStatus,
    PublicationGateStatus,
    VintageKind,
)


def _gate_input(**overrides: object) -> GateInput:
    payload: dict[str, object] = {
        "cycle_id": "C4",
        "layer": "historical",
        "configured_status": PublicationGateStatus.FORMAL,
        "evidence_status": "supported",
        "vintage_kind": VintageKind.LATEST_HISTORICAL,
        "freshness": FreshnessStatus.FRESH,
        "model_qualified": None,
    }
    payload.update(overrides)
    return GateInput.model_validate(payload)


def test_c4_historical_is_formal() -> None:
    decision = evaluate_gate(
        _gate_input(
            freshness=FreshnessStatus.STALE,
        )
    )

    assert decision.status is PublicationGateStatus.FORMAL
    assert decision.reason_codes == ("configured_policy",)


def test_c1_historical_is_scenario_only() -> None:
    decision = evaluate_gate(
        _gate_input(
            cycle_id="C1",
            configured_status=PublicationGateStatus.SCENARIO_ONLY,
            evidence_status="scenario_supported",
        )
    )

    assert decision.status is PublicationGateStatus.SCENARIO_ONLY
    assert decision.reason_codes == ("configured_policy",)


def test_c1_explanatory_historical_is_scenario_only() -> None:
    decision = evaluate_gate(
        _gate_input(
            cycle_id="C1",
            configured_status=PublicationGateStatus.SCENARIO_ONLY,
            evidence_status="explanatory_only",
        )
    )

    assert decision.status is PublicationGateStatus.SCENARIO_ONLY
    assert decision.reason_codes == ("configured_policy",)


def test_c6_historical_is_calendar_only() -> None:
    decision = evaluate_gate(
        _gate_input(
            cycle_id="C6",
            configured_status=PublicationGateStatus.CALENDAR_ONLY,
            evidence_status="calendar_defined",
        )
    )

    assert decision.status is PublicationGateStatus.CALENDAR_ONLY
    assert decision.reason_codes == ("configured_policy",)


def test_c4_realtime_is_limited_without_true_vintage() -> None:
    decision = evaluate_gate(
        _gate_input(
            layer="realtime",
            configured_status=PublicationGateStatus.LIMITED,
            vintage_kind=VintageKind.PSEUDO_VINTAGE,
            freshness=FreshnessStatus.STALE,
        )
    )

    assert decision.status is PublicationGateStatus.LIMITED
    assert decision.reason_codes == ("pseudo_vintage",)


def test_c6_realtime_rejects_pseudo_vintage_under_configured_block() -> None:
    decision = evaluate_gate(
        _gate_input(
            cycle_id="C6",
            layer="realtime",
            configured_status=PublicationGateStatus.BLOCKED,
            evidence_status="calendar_defined",
            vintage_kind=VintageKind.PSEUDO_VINTAGE,
        )
    )

    assert decision.status is PublicationGateStatus.BLOCKED
    assert decision.reason_codes == ("configured_block",)


def test_stale_forecast_cannot_be_formal() -> None:
    decision = evaluate_gate(
        _gate_input(
            layer="forecast",
            configured_status=PublicationGateStatus.FORMAL,
            vintage_kind=VintageKind.PSEUDO_VINTAGE,
            freshness=FreshnessStatus.STALE,
            model_qualified=True,
        )
    )

    assert decision.status is PublicationGateStatus.LIMITED
    assert decision.reason_codes == ("stale_input",)


def test_c6_fresh_forecast_is_calendar_only() -> None:
    decision = evaluate_gate(
        _gate_input(
            cycle_id="C6",
            layer="forecast",
            configured_status=PublicationGateStatus.CALENDAR_ONLY,
            evidence_status="calendar_defined",
        )
    )

    assert decision.status is PublicationGateStatus.CALENDAR_ONLY
    assert decision.reason_codes == ("configured_policy",)


def test_c6_stale_forecast_remains_calendar_only() -> None:
    decision = evaluate_gate(
        _gate_input(
            cycle_id="C6",
            layer="forecast",
            configured_status=PublicationGateStatus.CALENDAR_ONLY,
            evidence_status="calendar_defined",
            freshness=FreshnessStatus.STALE,
        )
    )

    assert decision.status is PublicationGateStatus.CALENDAR_ONLY
    assert decision.reason_codes == ("configured_policy",)


def test_unidentified_cycle_is_blocked_for_assets() -> None:
    decision = evaluate_gate(
        _gate_input(
            cycle_id="C5",
            layer="asset_statistics",
            configured_status=PublicationGateStatus.BLOCKED,
            evidence_status="unidentified",
        )
    )

    assert decision.status is PublicationGateStatus.BLOCKED
    assert decision.reason_codes == ("period_unidentified",)


@pytest.mark.parametrize(
    ("vintage_kind", "freshness"),
    [
        (VintageKind.UNAVAILABLE, FreshnessStatus.UNAVAILABLE),
        (VintageKind.LATEST_HISTORICAL, FreshnessStatus.UNAVAILABLE),
    ],
)
def test_unavailable_data_blocks_publication(
    vintage_kind: VintageKind,
    freshness: FreshnessStatus,
) -> None:
    decision = evaluate_gate(
        _gate_input(
            layer="forecast",
            vintage_kind=vintage_kind,
            freshness=freshness,
            model_qualified=True,
        )
    )

    assert decision.status is PublicationGateStatus.BLOCKED
    assert decision.reason_codes == ("data_unavailable",)


def test_unqualified_forecast_model_is_blocked() -> None:
    decision = evaluate_gate(
        _gate_input(
            layer="forecast",
            model_qualified=False,
        )
    )

    assert decision.status is PublicationGateStatus.BLOCKED
    assert decision.reason_codes == ("model_not_qualified",)


def test_qualified_challenger_cannot_exceed_configured_forecast_policy() -> None:
    decision = evaluate_gate(
        _gate_input(
            layer="forecast",
            configured_status=PublicationGateStatus.LIMITED,
            model_qualified=True,
        )
    )

    assert decision.status is PublicationGateStatus.LIMITED
    assert decision.reason_codes == ("configured_policy",)


def test_asset_statistics_require_supported_historical_evidence() -> None:
    decision = evaluate_gate(
        _gate_input(
            layer="asset_statistics",
            evidence_status="scenario_supported",
        )
    )

    assert decision.status is PublicationGateStatus.BLOCKED
    assert decision.reason_codes == ("historical_evidence_not_formal",)


def test_configured_block_is_preserved() -> None:
    decision = evaluate_gate(
        _gate_input(
            configured_status=PublicationGateStatus.BLOCKED,
        )
    )

    assert decision.status is PublicationGateStatus.BLOCKED
    assert decision.reason_codes == ("configured_block",)


def test_gate_inputs_and_decisions_are_strict_and_immutable() -> None:
    request = _gate_input()
    decision = evaluate_gate(request)

    with pytest.raises(ValidationError, match="frozen"):
        request.layer = "forecast"
    with pytest.raises(ValidationError, match="frozen"):
        decision.status = PublicationGateStatus.BLOCKED
    with pytest.raises(ValidationError):
        GateInput.model_validate(
            {
                **request.model_dump(mode="python"),
                "configured_status": "formal",
            }
        )


def test_gate_input_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        GateInput.model_validate(
            {
                **_gate_input().model_dump(mode="python"),
                "model_name": "timesfm",
            }
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        (
            {"model_qualified": True},
            "model_qualified must be None for non-forecast layers",
        ),
        (
            {"layer": "realtime", "model_qualified": False},
            "model_qualified must be None for non-forecast layers",
        ),
        (
            {"layer": "forecast", "model_qualified": None},
            "model_qualified must be an explicit bool for forecast layers",
        ),
        (
            {
                "cycle_id": "C6",
                "layer": "forecast",
                "configured_status": PublicationGateStatus.CALENDAR_ONLY,
                "evidence_status": "calendar_defined",
                "model_qualified": True,
            },
            "model_qualified must be None for calendar_only forecasts",
        ),
        (
            {
                "cycle_id": "C1",
                "configured_status": PublicationGateStatus.SCENARIO_ONLY,
                "evidence_status": "supported",
            },
            "scenario_only requires scenario-supported or explanatory evidence",
        ),
        (
            {
                "cycle_id": "C6",
                "configured_status": PublicationGateStatus.CALENDAR_ONLY,
                "evidence_status": "supported",
            },
            "calendar_only requires calendar_defined evidence",
        ),
    ],
)
def test_gate_input_rejects_inconsistent_cross_field_values(
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        _gate_input(**overrides)


@pytest.mark.parametrize(
    ("cycle_id", "layer", "configured_status", "message"),
    [
        (
            "C4",
            "historical",
            PublicationGateStatus.SCENARIO_ONLY,
            "scenario_only is allowed only for C1 historical",
        ),
        (
            "C1",
            "forecast",
            PublicationGateStatus.SCENARIO_ONLY,
            "scenario_only is allowed only for C1 historical",
        ),
        (
            "C4",
            "forecast",
            PublicationGateStatus.CALENDAR_ONLY,
            "calendar_only is allowed only for C6 historical or forecast",
        ),
        (
            "C6",
            "realtime",
            PublicationGateStatus.CALENDAR_ONLY,
            "calendar_only is allowed only for C6 historical or forecast",
        ),
    ],
)
def test_special_statuses_reject_unsupported_cycle_layer_combinations(
    cycle_id: str,
    layer: str,
    configured_status: PublicationGateStatus,
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        _gate_input(
            cycle_id=cycle_id,
            layer=layer,
            configured_status=configured_status,
        )


@pytest.mark.parametrize(
    ("overrides", "expected_status", "expected_reason_codes"),
    [
        (
            {
                "cycle_id": "C5",
                "layer": "forecast",
                "configured_status": PublicationGateStatus.BLOCKED,
                "evidence_status": "unidentified",
                "vintage_kind": VintageKind.UNAVAILABLE,
                "freshness": FreshnessStatus.UNAVAILABLE,
                "model_qualified": False,
            },
            PublicationGateStatus.BLOCKED,
            ("period_unidentified",),
        ),
        (
            {
                "layer": "forecast",
                "configured_status": PublicationGateStatus.BLOCKED,
                "vintage_kind": VintageKind.UNAVAILABLE,
                "freshness": FreshnessStatus.UNAVAILABLE,
                "model_qualified": False,
            },
            PublicationGateStatus.BLOCKED,
            ("data_unavailable",),
        ),
        (
            {
                "layer": "forecast",
                "configured_status": PublicationGateStatus.BLOCKED,
                "model_qualified": False,
            },
            PublicationGateStatus.BLOCKED,
            ("configured_block",),
        ),
        (
            {
                "layer": "forecast",
                "configured_status": PublicationGateStatus.LIMITED,
                "model_qualified": False,
            },
            PublicationGateStatus.BLOCKED,
            ("model_not_qualified",),
        ),
    ],
)
def test_gate_blocking_precedence_is_deterministic(
    overrides: dict[str, object],
    expected_status: PublicationGateStatus,
    expected_reason_codes: tuple[str, ...],
) -> None:
    decision = evaluate_gate(_gate_input(**overrides))

    assert decision.status is expected_status
    assert decision.reason_codes == expected_reason_codes


def test_gate_decision_rejects_duplicate_reason_codes() -> None:
    with pytest.raises(ValidationError, match="reason_codes must be unique"):
        GateDecision(
            cycle_id="C4",
            layer="forecast",
            status=PublicationGateStatus.LIMITED,
            reason_codes=("stale_input", "stale_input"),
        )


def test_gate_contracts_are_exported_with_stable_reason_codes() -> None:
    assert governance.GateInput is GateInput
    assert governance.GateDecision is GateDecision
    assert governance.evaluate_gate is evaluate_gate

    with pytest.raises(ValidationError, match="Input should be"):
        GateDecision(
            cycle_id="C4",
            layer="historical",
            status=PublicationGateStatus.FORMAL,
            reason_codes=("model_name_preferred",),
        )
