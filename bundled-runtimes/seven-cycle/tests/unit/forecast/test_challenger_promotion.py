from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil

import pandas as pd
import pytest

from seven_cycle_platform.forecast import evaluation as evaluation_api
from seven_cycle_platform.forecast import protocol as protocol_api
from seven_cycle_platform.forecast.evaluation import (
    AGGREGATE_METRIC_COLUMNS,
    FOLD_METRIC_COLUMNS,
    GATE_RESULT_COLUMNS,
    OOS_FOLD_ARTIFACT_COLUMNS,
    PromotionConfig,
    PromotionResult,
    evaluate_challenger_promotion,
)
from seven_cycle_platform.forecast.protocol import (
    FeatureAudit,
    ForecastModel,
    ModelCard,
    PredictionRequest,
    TrainVintage,
)
from seven_cycle_platform.storage.manifest import RunManifest
from seven_cycle_platform.storage.publisher import publish_run
from seven_cycle_platform.storage.run_context import RunContext, canonical_json_bytes


HASH_A = "a" * 64
HASH_B = "b" * 64
HASH_C = "c" * 64
HASH_D = "d" * 64
PHASES = ("expansion", "downturn", "contraction", "recovery")
METRICS = (
    "brier_score",
    "log_loss",
    "interval_coverage_error",
    "downstream_asset_oos_loss",
)

MAPPING_ARTIFACT_FILENAME = "mapping.json"
MAPPING_ARTIFACT_BYTES = b'{"assets":["asset-0","asset-1"]}\n'
_DEFAULT_MAPPING_RUN: tuple[Path, RunManifest] | None = None


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _publish_mapping_run(
    tmp_path: Path,
    *,
    catalog_overrides: dict[str, object] | None = None,
    catalog_bytes: bytes | None = None,
    artifact_bytes: bytes = MAPPING_ARTIFACT_BYTES,
    model_version: str = "mapping-v1",
    as_of: date = date(2020, 3, 31),
) -> tuple[Path, RunManifest]:
    mapping_product = "asset_mapping_future"
    mapping_id = "cn-core-assets"
    manifest_metadata = {
        "schema_version": evaluation_api.MAPPING_REFERENCE_SCHEMA_VERSION,
        "mapping_product": mapping_product,
        "mapping_id": mapping_id,
        "artifact_filename": MAPPING_ARTIFACT_FILENAME,
    }
    context = RunContext.create(
        as_of=as_of,
        data_vintage=as_of,
        model_version=model_version,
        config={"mapping_id": mapping_id, "method": "governed-linear"},
        input_checksums={"inputs/channels.parquet": HASH_A},
        quality_summary={
            evaluation_api.MAPPING_MANIFEST_METADATA_KEY: manifest_metadata,
            "passed": 1,
        },
        created_at=datetime(2020, 4, 1, tzinfo=timezone.utc),
    )
    catalog: dict[str, object] = {
        **manifest_metadata,
        "version": context.model_version,
        "run_id": context.run_id,
        "config_hash": context.config_hash,
        "artifact_hash": _sha256_bytes(artifact_bytes),
        "as_of": context.as_of.isoformat(),
    }
    if catalog_overrides:
        catalog.update(catalog_overrides)
    product_root = tmp_path / "products" / mapping_product

    def write_staging(staging_dir: Path) -> None:
        (staging_dir / MAPPING_ARTIFACT_FILENAME).write_bytes(artifact_bytes)
        reference_bytes = (
            canonical_json_bytes(catalog) + b"\n"
            if catalog_bytes is None
            else catalog_bytes
        )
        (staging_dir / evaluation_api.MAPPING_REFERENCE_FILENAME).write_bytes(
            reference_bytes
        )

    manifest = publish_run(
        product_root,
        context,
        write_staging=write_staging,
    )
    return product_root / "runs" / manifest.run_id, manifest


@pytest.fixture(scope="module", autouse=True)
def _published_mapping_fixture(tmp_path_factory: pytest.TempPathFactory):
    global _DEFAULT_MAPPING_RUN
    run_root = tmp_path_factory.mktemp("published-mapping")
    _DEFAULT_MAPPING_RUN = _publish_mapping_run(run_root)
    try:
        yield
    finally:
        _DEFAULT_MAPPING_RUN = None


def _mapping_reference() -> object:
    assert _DEFAULT_MAPPING_RUN is not None
    run_dir, manifest = _DEFAULT_MAPPING_RUN
    return evaluation_api.MappingReference.from_published_run(
        run_dir,
        expected_manifest=manifest,
    )


def _evidence_context(**overrides: object) -> object:
    values: dict[str, object] = {
        "evaluation_cutoff": date(2022, 12, 31),
        "mapping_reference": _mapping_reference(),
    }
    values.update(overrides)
    return evaluation_api.PromotionEvidenceContext(**values)


def _prediction_envelope(card: ModelCard) -> object:
    request = protocol_api.ForecastRequest(
        as_of=date(2020, 6, 30),
        horizons=(3,),
        scope=card.scope,
    )
    return protocol_api.PredictionEnvelope(
        request=request,
        model_id=card.model_id,
        version=card.version,
        role=card.role,
        scope=card.scope,
        output_contract=card.output_contract,
        predictions=(
            protocol_api.ForecastPoint(
                target_id="C3",
                horizon=3,
                output_id="expansion_probability",
                value=0.6,
            ),
        ),
    )


def _protocol_card(**overrides: object) -> ModelCard:
    values: dict[str, object] = {
        "model_id": "cycle-challenger",
        "version": "1.0.0",
        "role": "challenger",
        "scope": "cycle",
        "algorithm": "temporal_fusion_transformer",
        "code_hash": HASH_A,
        "config_hash": HASH_B,
        "seed_policy": "fixed",
        "seed": 7,
        "training_objective": "minimize nested-walk-forward log loss",
        "output_contract": "cycle_phase_probabilities_v1",
        "downstream_mapping_requirement": protocol_api.GOVERNED_MAPPING_REQUIRED,
        "direct_asset_weights_allowed": False,
        "direct_asset_prediction_bypass_allowed": False,
        "historical_contribution_weights_allowed": False,
        "feature_ids": ("f_growth", "f_credit"),
        "data_vintage": date(2020, 3, 31),
        "training_cutoff": date(2020, 3, 30),
    }
    values.update(overrides)
    return ModelCard(**values)


def _protocol_audit(
    card: ModelCard | None = None,
    **overrides: object,
) -> FeatureAudit:
    card = card or _protocol_card()
    values: dict[str, object] = {
        "model_id": card.model_id,
        "version": card.version,
        "role": card.role,
        "scope": card.scope,
        "as_of": date(2020, 3, 31),
        "feature_ids": card.feature_ids,
        "max_visible_date": date(2020, 3, 30),
        "max_generated_date": date(2020, 3, 30),
        "max_vintage_date": date(2020, 3, 30),
        "train_start": date(2018, 1, 1),
        "train_end": date(2020, 3, 30),
        "data_vintage": date(2020, 3, 31),
        "leakage_checks": (
            "visible_date_lte_as_of",
            "generated_date_lte_as_of",
            "vintage_date_lte_as_of",
        ),
        "forbidden_features": (),
        "status": "passed",
        "reasons": (),
        "code_hash": card.code_hash,
        "config_hash": card.config_hash,
    }
    values.update(overrides)
    return FeatureAudit(**values)


def _card(
    role: str,
    *,
    seed: int = 7,
    scope: str = "cycle",
    seed_policy: str = "fixed",
) -> ModelCard:
    return ModelCard(
        model_id=f"{role}-model",
        version=f"{role}-v1",
        role=role,
        scope=scope,
        algorithm="state_space" if role == "champion" else "challenger_sequence",
        code_hash=HASH_A if role == "champion" else HASH_B,
        config_hash=HASH_B if role == "champion" else HASH_A,
        seed_policy=seed_policy,
        seed=seed,
        training_objective="minimize governed out-of-sample forecast loss",
        output_contract=f"{scope}_forecast_v1",
        downstream_mapping_requirement=protocol_api.GOVERNED_MAPPING_REQUIRED,
        direct_asset_weights_allowed=False,
        direct_asset_prediction_bypass_allowed=False,
        historical_contribution_weights_allowed=False,
        feature_ids=("f_growth", "f_credit"),
        data_vintage=date(2020, 3, 31),
        training_cutoff=date(2020, 3, 31),
    )


def _audit(
    card: ModelCard,
    *,
    leakage_checks: tuple[str, ...] = (
        "visible_date_lte_as_of",
        "generated_date_lte_as_of",
        "vintage_date_lte_as_of",
    ),
    status: str = "passed",
    reasons: tuple[str, ...] = (),
    forbidden_features: tuple[str, ...] = (),
) -> FeatureAudit:
    return FeatureAudit(
        model_id=card.model_id,
        version=card.version,
        role=card.role,
        scope=card.scope,
        as_of=card.data_vintage,
        feature_ids=card.feature_ids,
        max_visible_date=date(2020, 3, 30),
        max_generated_date=date(2020, 3, 30),
        max_vintage_date=date(2020, 3, 30),
        train_start=date(2018, 1, 1),
        train_end=card.training_cutoff,
        data_vintage=card.data_vintage,
        leakage_checks=leakage_checks,
        forbidden_features=forbidden_features,
        status=status,
        reasons=reasons,
        code_hash=card.code_hash,
        config_hash=card.config_hash,
    )


def _probabilities(realized_phase: str, true_probability: float) -> dict[str, float]:
    other_probability = (1.0 - true_probability) / 3.0
    return {
        f"{phase}_probability": (
            true_probability if phase == realized_phase else other_probability
        )
        for phase in PHASES
    }


def _artifacts(
    card: ModelCard,
    *,
    challenger: bool,
    folds: int = 3,
    samples_per_fold: int = 4,
    evidence_context: object | None = None,
) -> pd.DataFrame:
    evidence_context = evidence_context or _evidence_context()
    mapping_reference = evidence_context.mapping_reference
    validation_origins = pd.date_range("2020-06-30", periods=folds, freq="6ME")
    records: list[dict[str, object]] = []
    for fold_index, validation_origin in enumerate(validation_origins, start=1):
        embargo_cutoff = validation_origin - pd.Timedelta(days=5)
        train_end = embargo_cutoff - pd.Timedelta(days=1)
        inner_end = train_end - pd.Timedelta(days=1)
        for sample_index in range(samples_per_fold):
            realized_phase = PHASES[sample_index % len(PHASES)]
            target_date = validation_origin + pd.offsets.MonthEnd(3)
            downstream_actual = float(sample_index) / 10.0
            downstream_error = 0.5 if challenger else 1.0
            covered = sample_index < (3 if challenger else 1)
            interval_lower = -1.0 if covered else 1.0
            interval_upper = 1.0 if covered else 2.0
            record = {
                "outer_fold_id": f"fold-{fold_index}",
                "sample_id": f"fold-{fold_index}-sample-{sample_index}",
                "train_start": pd.Timestamp("2018-01-01"),
                "train_end": train_end,
                "inner_tuning_start": train_end - pd.Timedelta(days=90),
                "inner_tuning_end": inner_end,
                "validation_origin": validation_origin,
                "embargo_cutoff": embargo_cutoff,
                "evaluation_cutoff": pd.Timestamp(evidence_context.evaluation_cutoff),
                "target_date": target_date,
                "target_visible_date": target_date + pd.Timedelta(days=5),
                "target_revision_window_end": target_date + pd.Timedelta(days=10),
                "model_id": card.model_id,
                "model_role": card.role,
                "model_version": card.version,
                "seed": card.seed,
                "prediction_scope": card.scope,
                "prediction_id": "C3",
                "horizon_months": 3,
                **_probabilities(
                    realized_phase,
                    0.70 if challenger else 0.45,
                ),
                "realized_phase": realized_phase,
                "interval_lower": interval_lower,
                "interval_upper": interval_upper,
                "interval_nominal_coverage": 0.75,
                "realized_target": 0.0,
                "downstream_asset_id": f"asset-{sample_index % 2}",
                "downstream_asset_prediction": (downstream_actual + downstream_error),
                "downstream_asset_actual": downstream_actual,
                "downstream_asset_loss": downstream_error**2,
                "downstream_loss": "squared_error",
                "mapping_product": mapping_reference.mapping_product,
                "mapping_id": mapping_reference.mapping_id,
                "mapping_version": mapping_reference.version,
                "mapping_run_id": mapping_reference.run_id,
                "mapping_config_hash": mapping_reference.config_hash,
                "mapping_artifact_hash": mapping_reference.artifact_hash,
                "mapping_manifest_hash": mapping_reference.manifest_hash,
                "mapping_reference_hash": mapping_reference.reference_hash,
                "mapping_reference_filename": mapping_reference.reference_filename,
                "mapping_artifact_filename": mapping_reference.artifact_filename,
                "mapping_as_of": mapping_reference.as_of,
                "data_vintage": validation_origin - pd.Timedelta(days=1),
                "feature_max_visible_date": validation_origin - pd.Timedelta(days=1),
                "feature_max_generated_date": validation_origin - pd.Timedelta(days=1),
                "feature_max_vintage_date": validation_origin - pd.Timedelta(days=1),
                "status": "complete",
                "reason": None,
            }
            records.append(record)
    return pd.DataFrame(records, columns=OOS_FOLD_ARTIFACT_COLUMNS)


def _config(**overrides: object) -> PromotionConfig:
    values = {
        "minimum_folds": 3,
        "minimum_samples": 12,
        "min_brier_improvement": 0.0,
        "min_log_loss_improvement": 0.0,
        "min_interval_coverage_improvement": 0.0,
        "min_downstream_asset_loss_improvement": 0.0,
        "coverage_tolerance": 0.05,
        "probability_epsilon": 1e-12,
        "embargo_days": 5,
        "seed_policy": "matched",
        "downstream_loss": "squared_error",
    }
    values.update(overrides)
    return PromotionConfig(**values)


def _evaluate(
    *,
    champion: pd.DataFrame | None = None,
    challenger: pd.DataFrame | None = None,
    champion_card: ModelCard | None = None,
    challenger_card: ModelCard | None = None,
    champion_audit: FeatureAudit | None = None,
    challenger_audit: FeatureAudit | None = None,
    config: PromotionConfig | None = None,
    champion_replay: pd.DataFrame | None = None,
    challenger_replay: pd.DataFrame | None = None,
    evidence_context: object | None = None,
) -> PromotionResult:
    evidence_context = evidence_context or _evidence_context()
    champion_card = champion_card or _card("champion")
    challenger_card = challenger_card or _card("challenger")
    champion = (
        _artifacts(
            champion_card,
            challenger=False,
            evidence_context=evidence_context,
        )
        if champion is None
        else champion
    )
    challenger = (
        _artifacts(
            challenger_card,
            challenger=True,
            evidence_context=evidence_context,
        )
        if challenger is None
        else challenger
    )
    return evaluate_challenger_promotion(
        champion,
        challenger,
        champion_model_card=champion_card,
        challenger_model_card=challenger_card,
        champion_feature_audit=champion_audit or _audit(champion_card),
        challenger_feature_audit=challenger_audit or _audit(challenger_card),
        evidence_context=evidence_context,
        config=config or _config(),
        champion_replay_artifacts=champion_replay,
        challenger_replay_artifacts=challenger_replay,
    )


def _aggregate(result: PromotionResult, metric: str) -> pd.Series:
    return result.aggregate_metrics.loc[
        result.aggregate_metrics["metric"].eq(metric)
    ].iloc[0]


def _rebuild_result(
    result: PromotionResult,
    **overrides: object,
) -> PromotionResult:
    values: dict[str, object] = {
        "fold_metrics": result.fold_metrics,
        "aggregate_metrics": result.aggregate_metrics,
        "gate_results": result.gate_results,
        "champion_artifacts": result.champion_artifacts,
        "challenger_artifacts": result.challenger_artifacts,
        "champion_model_card": result.champion_model_card,
        "challenger_model_card": result.challenger_model_card,
        "champion_feature_audit": result.champion_feature_audit,
        "challenger_feature_audit": result.challenger_feature_audit,
        "evidence_context": result.evidence_context,
        "config": result.config,
        "champion_replay_artifacts": result.champion_replay_artifacts,
        "challenger_replay_artifacts": result.challenger_replay_artifacts,
        "promotion_decision": result.promotion_decision,
        "live_model": result.live_model,
        "live_model_role": result.live_model_role,
        "challenger_status": result.challenger_status,
        "failure_reason_codes": result.failure_reason_codes,
    }
    values.update(overrides)
    return PromotionResult(**values)


def test_forecast_model_protocol_requires_every_method() -> None:
    card = _protocol_card()
    audit = _protocol_audit(card)

    def fit(self: object, train_vintage: TrainVintage) -> None:
        del self, train_vintage

    def predict(
        self: object,
        as_of: date,
        horizons: tuple[int, ...],
    ) -> protocol_api.PredictionEnvelope:
        del self, as_of, horizons
        return _prediction_envelope(card)

    def model_card(self: object) -> ModelCard:
        del self
        return card

    def feature_audit(self: object) -> FeatureAudit:
        del self
        return audit

    methods = {
        "fit": fit,
        "predict": predict,
        "model_card": model_card,
        "feature_audit": feature_audit,
    }
    complete_model = type("CompleteModel", (), methods)()

    assert isinstance(complete_model, ForecastModel)
    for missing_method in methods:
        incomplete = type(
            f"Missing{missing_method.title()}",
            (),
            {
                name: implementation
                for name, implementation in methods.items()
                if name != missing_method
            },
        )()
        assert not isinstance(incomplete, ForecastModel)


def test_runtime_validator_rejects_wrong_forecast_method_signatures() -> None:
    card = _protocol_card()
    audit = _protocol_audit(card)

    class CompleteModel:
        def fit(self, train_vintage: TrainVintage) -> None:
            del train_vintage

        def predict(
            self,
            as_of: date,
            horizons: tuple[int, ...],
        ) -> protocol_api.PredictionEnvelope:
            del as_of, horizons
            return _prediction_envelope(card)

        def model_card(self) -> ModelCard:
            return card

        def feature_audit(self) -> FeatureAudit:
            return audit

    class BadFit(CompleteModel):
        def fit(self) -> None:
            return None

    class BadFitAnnotation(CompleteModel):
        def fit(self, train_vintage: TrainVintage) -> object:
            return train_vintage

    class BadPredict(CompleteModel):
        def predict(self) -> protocol_api.PredictionEnvelope:
            return None

    class BadPredictAnnotation(CompleteModel):
        def predict(self, as_of: date, horizons: tuple[int, ...]) -> object:
            return as_of, horizons

    class BadPredictDictAnnotation(CompleteModel):
        def predict(
            self,
            as_of: date,
            horizons: tuple[int, ...],
        ) -> dict[str, object]:
            return {"as_of": as_of, "horizons": horizons}

    class BadModelCardValue(CompleteModel):
        def model_card(self) -> ModelCard:
            return {"model_id": card.model_id}

    class BadFeatureAuditValue(CompleteModel):
        def feature_audit(self) -> FeatureAudit:
            return {"model_id": card.model_id}

    assert protocol_api.is_forecast_model(CompleteModel())
    assert not protocol_api.is_forecast_model(BadFit())
    assert not protocol_api.is_forecast_model(BadFitAnnotation())
    assert not protocol_api.is_forecast_model(BadPredict())
    assert not protocol_api.is_forecast_model(BadPredictAnnotation())
    assert not protocol_api.is_forecast_model(BadPredictDictAnnotation())
    assert not protocol_api.is_forecast_model(BadModelCardValue())
    assert not protocol_api.is_forecast_model(BadFeatureAuditValue())
    with pytest.raises(TypeError, match=r"fit\(train_vintage\)"):
        protocol_api.validate_forecast_model(BadFit())
    with pytest.raises(TypeError, match="fit must return None"):
        protocol_api.validate_forecast_model(BadFitAnnotation())
    with pytest.raises(TypeError, match=r"predict\(as_of, horizons\)"):
        protocol_api.validate_forecast_model(BadPredict())
    with pytest.raises(TypeError, match="predict must return PredictionEnvelope"):
        protocol_api.validate_forecast_model(BadPredictAnnotation())
    with pytest.raises(TypeError, match="predict must return PredictionEnvelope"):
        protocol_api.validate_forecast_model(BadPredictDictAnnotation())
    with pytest.raises(TypeError, match="model_card must return ModelCard"):
        protocol_api.validate_forecast_model(BadModelCardValue())
    with pytest.raises(TypeError, match="feature_audit must return FeatureAudit"):
        protocol_api.validate_forecast_model(BadFeatureAuditValue())


def test_protocol_records_are_frozen_hashable_and_defensively_copy_inputs() -> None:
    feature_ids = ["f_growth", "f_credit"]
    horizons = [6, 3]
    leakage_checks = ["visible_date_lte_as_of", "vintage_date_lte_as_of"]
    predictions = [
        protocol_api.ForecastPoint(
            target_id="C3",
            horizon=3,
            output_id="expansion_probability",
            value=0.6,
        )
    ]
    card = _protocol_card(feature_ids=feature_ids)
    audit = _protocol_audit(
        card,
        feature_ids=feature_ids,
        leakage_checks=leakage_checks,
    )
    request = protocol_api.ForecastRequest(
        as_of=date(2020, 3, 31),
        horizons=horizons,
        scope="cycle",
    )
    envelope = protocol_api.PredictionEnvelope(
        request=request,
        model_id=card.model_id,
        version=card.version,
        role=card.role,
        scope=card.scope,
        output_contract=card.output_contract,
        predictions=predictions,
    )

    feature_ids.append("future_target")
    horizons.append(12)
    leakage_checks.append("generated_date_lte_as_of")
    predictions.append(
        protocol_api.ForecastPoint(
            target_id="C3",
            horizon=6,
            output_id="expansion_probability",
            value=0.5,
        )
    )

    assert card.feature_ids == ("f_credit", "f_growth")
    assert audit.feature_ids == ("f_credit", "f_growth")
    assert request.horizons == (3, 6)
    assert audit.leakage_checks == (
        "visible_date_lte_as_of",
        "vintage_date_lte_as_of",
    )
    assert len(envelope.predictions) == 1
    for record in (card, audit, request, envelope, envelope.predictions[0]):
        assert isinstance(hash(record), int)
    with pytest.raises(FrozenInstanceError):
        card.algorithm = "forged"
    with pytest.raises(FrozenInstanceError):
        audit.status = "failed"
    with pytest.raises(FrozenInstanceError):
        request.scope = "channel"


@pytest.mark.parametrize("scope", ["asset", "portfolio", "weight"])
def test_model_card_rejects_challenger_scope_outside_cycle_or_channel(
    scope: str,
) -> None:
    with pytest.raises(ValueError, match="cycle or channel"):
        _protocol_card(scope=scope)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("model_id", "", "non-empty"),
        ("algorithm", "   ", "non-empty"),
        ("code_hash", "ABC", "SHA-256"),
        ("config_hash", "g" * 64, "SHA-256"),
        ("seed_policy", "random_each_run", "deterministic"),
        (
            "downstream_mapping_requirement",
            "",
            "governed_mapping_required",
        ),
        ("direct_asset_weights_allowed", True, "direct asset weights"),
        (
            "direct_asset_prediction_bypass_allowed",
            True,
            "asset Mapping",
        ),
        (
            "historical_contribution_weights_allowed",
            True,
            "historical contribution",
        ),
    ],
)
def test_model_card_rejects_invalid_governance_contract(
    field: str,
    value: object,
    message: str,
) -> None:
    with pytest.raises((TypeError, ValueError), match=message):
        _protocol_card(**{field: value})


def test_feature_audit_enforces_pit_dates_status_and_feature_uniqueness() -> None:
    card = _protocol_card()
    audit = _protocol_audit(card)

    assert audit.train_end <= audit.as_of
    assert audit.data_vintage <= audit.as_of
    assert audit.max_visible_date <= audit.as_of
    assert audit.max_generated_date <= audit.as_of
    assert audit.max_vintage_date <= audit.as_of
    assert audit.status == "passed"
    assert audit.reasons == ()

    for field in (
        "train_end",
        "data_vintage",
        "max_visible_date",
        "max_generated_date",
        "max_vintage_date",
    ):
        with pytest.raises(ValueError, match="as_of"):
            _protocol_audit(card, **{field: date(2020, 4, 1)})

    with pytest.raises(ValueError, match="duplicates"):
        _protocol_audit(card, feature_ids=("f_growth", "f_growth"))
    with pytest.raises(ValueError, match="duplicates"):
        _protocol_audit(
            card,
            leakage_checks=("visible_date_lte_as_of", "visible_date_lte_as_of"),
        )
    with pytest.raises(ValueError, match="reasons"):
        _protocol_audit(card, status="failed", reasons=())
    with pytest.raises(ValueError, match="forbidden"):
        _protocol_audit(card, forbidden_features=("future_target",))

    failed = _protocol_audit(
        card,
        forbidden_features=("future_target",),
        status="failed",
        reasons=("FORBIDDEN_FEATURE_PRESENT",),
    )
    assert failed.status == "failed"
    assert failed.forbidden_features == ("future_target",)


def test_prediction_envelope_rejects_scope_horizon_and_duplicate_mismatches() -> None:
    card = _protocol_card()
    request = protocol_api.ForecastRequest(
        as_of=date(2020, 3, 31),
        horizons=(3, 6),
        scope="cycle",
    )
    point = protocol_api.ForecastPoint(
        target_id="C3",
        horizon=3,
        output_id="expansion_probability",
        value=0.6,
    )
    values: dict[str, object] = {
        "request": request,
        "model_id": card.model_id,
        "version": card.version,
        "role": card.role,
        "scope": card.scope,
        "output_contract": card.output_contract,
        "predictions": (point,),
    }

    with pytest.raises(ValueError, match="request scope"):
        protocol_api.PredictionEnvelope(**{**values, "scope": "channel"})
    with pytest.raises(ValueError, match="requested horizon"):
        protocol_api.PredictionEnvelope(
            **{
                **values,
                "predictions": (
                    protocol_api.ForecastPoint(
                        target_id="C3",
                        horizon=12,
                        output_id="expansion_probability",
                        value=0.6,
                    ),
                ),
            }
        )
    with pytest.raises(ValueError, match="duplicates"):
        protocol_api.PredictionEnvelope(**{**values, "predictions": (point, point)})


def test_forecast_model_protocol_and_request_contracts_are_strict() -> None:
    champion_card = _card("champion")

    class CompleteModel:
        def fit(self, train_vintage: TrainVintage) -> None:
            del train_vintage

        def predict(
            self,
            as_of: date,
            horizons: tuple[int, ...],
        ) -> protocol_api.PredictionEnvelope:
            del as_of, horizons
            return _prediction_envelope(champion_card)

        def model_card(self) -> ModelCard:
            return champion_card

        def feature_audit(self) -> FeatureAudit:
            return _audit(champion_card)

    class MissingAudit:
        def fit(self, train_vintage: TrainVintage) -> None:
            del train_vintage

        def predict(
            self,
            as_of: date,
            horizons: tuple[int, ...],
        ) -> protocol_api.PredictionEnvelope:
            del as_of, horizons
            return _prediction_envelope(champion_card)

        def model_card(self) -> ModelCard:
            return champion_card

    assert isinstance(CompleteModel(), ForecastModel)
    assert not isinstance(MissingAudit(), ForecastModel)

    train = TrainVintage(
        train_start=date(2018, 1, 1),
        train_end=date(2020, 3, 30),
        data_vintage=date(2020, 3, 31),
        feature_ids=("f_growth", "f_credit"),
        seed=7,
        code_hash=HASH_A,
        config_hash=HASH_B,
    )
    request = PredictionRequest(
        as_of=date(2020, 6, 30),
        horizons=(12, 3, 3, 6),
        scope="cycle",
    )
    assert request.horizons == (3, 6, 12)
    with pytest.raises(FrozenInstanceError):
        train.seed = 8
    with pytest.raises(FrozenInstanceError):
        champion_card.seed = 8


def test_task_27_public_contract_is_exported() -> None:
    from seven_cycle_platform import forecast as api

    for name in (
        "ForecastModel",
        "ForecastPoint",
        "ForecastRequest",
        "GOVERNED_LEAKAGE_CHECKS",
        "GOVERNED_MAPPING_REQUIRED",
        "MAPPING_MANIFEST_METADATA_KEY",
        "MAPPING_REFERENCE_FILENAME",
        "MAPPING_REFERENCE_SCHEMA_VERSION",
        "MappingReference",
        "MappingReferenceVerificationError",
        "PredictionEnvelope",
        "PromotionEvidenceContext",
        "is_forecast_model",
        "validate_forecast_model",
        "ModelCard",
        "FeatureAudit",
        "TrainVintage",
        "PredictionRequest",
        "PromotionConfig",
        "PromotionResult",
        "evaluate_challenger_promotion",
        "OOS_FOLD_ARTIFACT_COLUMNS",
    ):
        assert hasattr(api, name)


@pytest.mark.parametrize("scope", ["asset", "weight"])
def test_asset_or_weight_prediction_scope_is_forbidden(scope: str) -> None:
    with pytest.raises(ValueError, match="cycle or channel"):
        _card("challenger", scope=scope)

    card = _card("challenger")
    artifacts = _artifacts(card, challenger=True)
    artifacts.loc[0, "prediction_scope"] = scope
    with pytest.raises(ValueError, match="cycle or channel"):
        _evaluate(challenger=artifacts, challenger_card=card)


def test_all_four_metrics_improve_and_promote_challenger() -> None:
    result = _evaluate()

    assert result.promotion_decision == "promoted"
    assert result.live_model == "challenger-model"
    assert result.live_model_role == "challenger"
    assert result.challenger_status == "live"
    assert result.failure_reason_codes == ()
    assert set(result.aggregate_metrics["metric"]) == set(METRICS)
    assert result.aggregate_metrics["improvement"].gt(0.0).all()
    assert result.gate_results["passed"].all()


@pytest.mark.parametrize(
    ("metric", "config_field", "reason_code"),
    [
        ("brier_score", "min_brier_improvement", "BRIER_NOT_IMPROVED"),
        ("log_loss", "min_log_loss_improvement", "LOG_LOSS_NOT_IMPROVED"),
        (
            "interval_coverage_error",
            "min_interval_coverage_improvement",
            "INTERVAL_COVERAGE_NOT_IMPROVED",
        ),
        (
            "downstream_asset_oos_loss",
            "min_downstream_asset_loss_improvement",
            "DOWNSTREAM_ASSET_LOSS_NOT_IMPROVED",
        ),
    ],
)
def test_each_metric_gate_can_fail_independently(
    metric: str,
    config_field: str,
    reason_code: str,
) -> None:
    baseline = _evaluate()
    improvement = float(_aggregate(baseline, metric)["improvement"])
    result = _evaluate(config=replace(_config(), **{config_field: improvement + 0.01}))

    assert result.promotion_decision == "rejected"
    assert reason_code in result.failure_reason_codes
    assert result.live_model == "champion-model"
    assert result.challenger_status == "experimental"


@pytest.mark.parametrize(
    ("metric", "config_field", "reason_code"),
    [
        ("brier_score", "min_brier_improvement", "BRIER_NOT_IMPROVED"),
        ("log_loss", "min_log_loss_improvement", "LOG_LOSS_NOT_IMPROVED"),
        (
            "interval_coverage_error",
            "min_interval_coverage_improvement",
            "INTERVAL_COVERAGE_NOT_IMPROVED",
        ),
        (
            "downstream_asset_oos_loss",
            "min_downstream_asset_loss_improvement",
            "DOWNSTREAM_ASSET_LOSS_NOT_IMPROVED",
        ),
    ],
)
def test_improvement_equal_to_threshold_is_conservatively_rejected(
    metric: str,
    config_field: str,
    reason_code: str,
) -> None:
    baseline = _evaluate()
    improvement = float(_aggregate(baseline, metric)["improvement"])
    result = _evaluate(config=replace(_config(), **{config_field: improvement}))

    assert result.promotion_decision == "rejected"
    assert reason_code in result.failure_reason_codes


def test_probabilities_must_be_finite_normalized_and_zero_logloss_is_clipped() -> None:
    card = _card("challenger")
    invalid = _artifacts(card, challenger=True)
    invalid.loc[0, "expansion_probability"] += 0.1
    with pytest.raises(ValueError, match="sum to one"):
        _evaluate(challenger=invalid, challenger_card=card)

    clipped = _artifacts(card, challenger=True)
    row = clipped.index[0]
    clipped.loc[row, [f"{phase}_probability" for phase in PHASES]] = [
        0.0,
        0.4,
        0.3,
        0.3,
    ]
    result = _evaluate(challenger=clipped, challenger_card=card)
    expected = (
        -math.log(_config().probability_epsilon)
        + sum(-math.log(0.70) for _ in range(len(clipped) - 1))
    ) / len(clipped)
    assert _aggregate(result, "log_loss")["challenger_value"] == pytest.approx(expected)
    assert math.isfinite(float(_aggregate(result, "log_loss")["challenger_value"]))


def test_interval_coverage_error_is_measured_against_nominal_coverage() -> None:
    result = _evaluate()
    coverage = _aggregate(result, "interval_coverage_error")

    assert coverage["champion_coverage_rate"] == pytest.approx(0.25)
    assert coverage["challenger_coverage_rate"] == pytest.approx(0.75)
    assert coverage["nominal_coverage"] == pytest.approx(0.75)
    assert coverage["champion_value"] == pytest.approx(0.50)
    assert coverage["challenger_value"] == pytest.approx(0.0)


def test_cherry_picked_or_mismatched_pairs_cannot_promote() -> None:
    champion_card = _card("champion")
    challenger_card = _card("challenger")
    champion = _artifacts(champion_card, challenger=False)
    challenger = _artifacts(challenger_card, challenger=True).iloc[:-1]

    cherry_picked = _evaluate(
        champion=champion,
        challenger=challenger,
        champion_card=champion_card,
        challenger_card=challenger_card,
    )
    assert cherry_picked.promotion_decision == "rejected"
    assert "PAIRED_SAMPLE_SET_MISMATCH" in cherry_picked.failure_reason_codes

    challenger = _artifacts(challenger_card, challenger=True)
    challenger.loc[0, "realized_phase"] = "downturn"
    mismatched = _evaluate(
        champion=champion,
        challenger=challenger,
        champion_card=champion_card,
        challenger_card=challenger_card,
    )
    assert mismatched.promotion_decision == "rejected"
    assert "PAIRED_TARGET_MISMATCH" in mismatched.failure_reason_codes


def test_all_metrics_are_computed_only_on_common_paired_eligible_samples() -> None:
    champion_card = _card("champion")
    challenger_card = _card("challenger")
    champion = _artifacts(champion_card, challenger=False)
    challenger = _artifacts(challenger_card, challenger=True).iloc[:-1].copy()
    paired_keys = challenger.loc[:, ["outer_fold_id", "sample_id"]]
    paired_champion = champion.merge(
        paired_keys,
        on=["outer_fold_id", "sample_id"],
        how="inner",
        validate="one_to_one",
    )

    missing_sample = _evaluate(
        champion=champion,
        challenger=challenger,
        champion_card=champion_card,
        challenger_card=challenger_card,
    )
    paired_reference = _evaluate(
        champion=paired_champion,
        challenger=challenger,
        champion_card=champion_card,
        challenger_card=challenger_card,
    )

    assert missing_sample.promotion_decision == "rejected"
    assert missing_sample.challenger_status == "experimental"
    assert "PAIRED_SAMPLE_SET_MISMATCH" in missing_sample.failure_reason_codes
    assert (
        missing_sample.aggregate_metrics[
            [
                "champion_sample_count",
                "challenger_sample_count",
                "paired_sample_count",
            ]
        ]
        .eq(11)
        .all(axis=None)
    )
    assert missing_sample.fold_metrics["champion_sample_count"].equals(
        missing_sample.fold_metrics["challenger_sample_count"]
    )
    assert missing_sample.fold_metrics["champion_sample_count"].equals(
        missing_sample.fold_metrics["paired_sample_count"]
    )
    pd.testing.assert_frame_equal(
        missing_sample.fold_metrics,
        paired_reference.fold_metrics,
    )
    pd.testing.assert_frame_equal(
        missing_sample.aggregate_metrics,
        paired_reference.aggregate_metrics,
    )


@pytest.mark.parametrize(
    ("field", "reason_code"),
    [
        ("train_end", "TRAIN_END_NOT_BEFORE_EMBARGO"),
        ("inner_tuning_end", "INNER_TUNING_END_NOT_BEFORE_EMBARGO"),
    ],
)
def test_embargo_equal_boundaries_are_rejected(
    field: str,
    reason_code: str,
) -> None:
    card = _card("challenger")
    challenger = _artifacts(card, challenger=True)
    challenger.loc[challenger["outer_fold_id"].eq("fold-1"), field] = challenger.loc[
        challenger["outer_fold_id"].eq("fold-1"), "embargo_cutoff"
    ].to_numpy()

    result = _evaluate(challenger=challenger, challenger_card=card)
    assert result.promotion_decision == "rejected"
    assert reason_code in result.failure_reason_codes


def test_nested_windows_and_fold_origins_must_be_strict_walk_forward() -> None:
    card = _card("challenger")
    outside = _artifacts(card, challenger=True)
    outside.loc[outside["outer_fold_id"].eq("fold-2"), "inner_tuning_start"] = (
        pd.Timestamp("2017-12-31")
    )
    result = _evaluate(challenger=outside, challenger_card=card)
    assert "INNER_TUNING_WINDOW_OUTSIDE_TRAIN" in result.failure_reason_codes

    overlap = _artifacts(card, challenger=True)
    fold_two = overlap["outer_fold_id"].eq("fold-2")
    overlap.loc[fold_two, "validation_origin"] = pd.Timestamp("2020-06-30")
    overlap.loc[fold_two, "embargo_cutoff"] = pd.Timestamp("2020-06-25")
    result = _evaluate(challenger=overlap, challenger_card=card)
    assert "NON_INCREASING_OUTER_FOLDS" in result.failure_reason_codes

    overlapping_targets = _artifacts(card, challenger=True)
    fold_two = overlapping_targets["outer_fold_id"].eq("fold-2")
    new_origin = pd.Timestamp("2020-09-30")
    new_embargo = new_origin - pd.Timedelta(days=5)
    new_train_end = new_embargo - pd.Timedelta(days=1)
    new_target = new_origin + pd.offsets.MonthEnd(3)
    overlapping_targets.loc[fold_two, "validation_origin"] = new_origin
    overlapping_targets.loc[fold_two, "embargo_cutoff"] = new_embargo
    overlapping_targets.loc[fold_two, "train_end"] = new_train_end
    overlapping_targets.loc[fold_two, "inner_tuning_start"] = (
        new_train_end - pd.Timedelta(days=90)
    )
    overlapping_targets.loc[fold_two, "inner_tuning_end"] = (
        new_train_end - pd.Timedelta(days=1)
    )
    overlapping_targets.loc[fold_two, "target_date"] = new_target
    overlapping_targets.loc[fold_two, "target_visible_date"] = (
        new_target + pd.Timedelta(days=5)
    )
    overlapping_targets.loc[fold_two, "target_revision_window_end"] = (
        new_target + pd.Timedelta(days=10)
    )
    for field in (
        "data_vintage",
        "feature_max_visible_date",
        "feature_max_generated_date",
        "feature_max_vintage_date",
    ):
        overlapping_targets.loc[fold_two, field] = new_origin - pd.Timedelta(days=1)
    result = _evaluate(challenger=overlapping_targets, challenger_card=card)
    assert "OVERLAPPING_OUTER_FOLDS" in result.failure_reason_codes


@pytest.mark.parametrize(
    ("field", "value_source", "reason_code"),
    [
        (
            "feature_max_visible_date",
            "validation_origin",
            "FEATURE_VISIBLE_NOT_BEFORE_ORIGIN",
        ),
        (
            "feature_max_generated_date",
            "validation_origin",
            "FEATURE_GENERATED_NOT_BEFORE_ORIGIN",
        ),
        (
            "feature_max_vintage_date",
            "validation_origin",
            "FEATURE_VINTAGE_NOT_BEFORE_ORIGIN",
        ),
        (
            "target_revision_window_end",
            "evaluation_cutoff",
            "TARGET_NOT_MATURE_AT_EVALUATION_CUTOFF",
        ),
    ],
)
def test_future_visible_or_revision_contamination_fails_without_hiding_results(
    field: str,
    value_source: str,
    reason_code: str,
) -> None:
    card = _card("challenger")
    challenger = _artifacts(card, challenger=True)
    challenger.loc[0, field] = challenger.loc[0, value_source]

    result = _evaluate(challenger=challenger, challenger_card=card)
    assert result.promotion_decision == "rejected"
    assert reason_code in result.failure_reason_codes
    assert len(result.challenger_artifacts) == len(challenger)
    assert not result.aggregate_metrics.empty


@pytest.mark.parametrize(
    "boundary_field",
    ["target_date", "target_visible_date", "target_revision_window_end"],
)
def test_target_dates_equal_to_cutoff_are_not_mature(
    boundary_field: str,
) -> None:
    card = _card("challenger")
    challenger = _artifacts(card, challenger=True)
    cutoff = challenger.loc[0, "evaluation_cutoff"]
    if boundary_field == "target_date":
        challenger.loc[0, "target_date"] = cutoff
        challenger.loc[0, "target_visible_date"] = cutoff
        challenger.loc[0, "target_revision_window_end"] = cutoff
    elif boundary_field == "target_visible_date":
        challenger.loc[0, "target_date"] = cutoff - pd.Timedelta(days=1)
        challenger.loc[0, "target_visible_date"] = cutoff
        challenger.loc[0, "target_revision_window_end"] = cutoff
    else:
        challenger.loc[0, "target_revision_window_end"] = cutoff

    result = _evaluate(challenger=challenger, challenger_card=card)

    assert result.promotion_decision == "rejected"
    assert "TARGET_NOT_MATURE_AT_EVALUATION_CUTOFF" in (result.failure_reason_codes)


def test_artifact_evaluation_cutoff_cannot_override_authority() -> None:
    card = _card("challenger")
    challenger = _artifacts(card, challenger=True)
    fold_three = challenger["outer_fold_id"].eq("fold-3")
    challenger.loc[fold_three, "evaluation_cutoff"] = challenger.loc[
        fold_three, "validation_origin"
    ].to_numpy()

    result = _evaluate(challenger=challenger, challenger_card=card)
    assert "EVALUATION_CUTOFF_MISMATCH" in result.failure_reason_codes
    assert result.live_model == "champion-model"


def test_authoritative_cutoff_rejects_joint_future_forgery() -> None:
    context = _evidence_context()
    champion_card = _card("champion")
    challenger_card = _card("challenger")
    champion = _artifacts(
        champion_card,
        challenger=False,
        evidence_context=context,
    )
    challenger = _artifacts(
        challenger_card,
        challenger=True,
        evidence_context=context,
    )
    for artifacts in (champion, challenger):
        future_fold = artifacts["outer_fold_id"].eq("fold-3")
        validation_origin = pd.Timestamp("2099-06-30")
        embargo_cutoff = validation_origin - pd.Timedelta(days=5)
        train_end = embargo_cutoff - pd.Timedelta(days=1)
        target_date = validation_origin + pd.offsets.MonthEnd(3)
        artifacts.loc[future_fold, "train_end"] = train_end
        artifacts.loc[future_fold, "inner_tuning_start"] = train_end - pd.Timedelta(
            days=90
        )
        artifacts.loc[future_fold, "inner_tuning_end"] = train_end - pd.Timedelta(
            days=1
        )
        artifacts.loc[future_fold, "validation_origin"] = validation_origin
        artifacts.loc[future_fold, "embargo_cutoff"] = embargo_cutoff
        artifacts.loc[future_fold, "evaluation_cutoff"] = pd.Timestamp("2099-12-31")
        artifacts.loc[future_fold, "target_date"] = target_date
        artifacts.loc[future_fold, "target_visible_date"] = target_date + pd.Timedelta(
            days=5
        )
        artifacts.loc[future_fold, "target_revision_window_end"] = (
            target_date + pd.Timedelta(days=10)
        )
        for field in (
            "data_vintage",
            "feature_max_visible_date",
            "feature_max_generated_date",
            "feature_max_vintage_date",
        ):
            artifacts.loc[future_fold, field] = validation_origin - pd.Timedelta(days=1)

    result = _evaluate(
        champion=champion,
        challenger=challenger,
        champion_card=champion_card,
        challenger_card=challenger_card,
        evidence_context=context,
    )

    assert result.promotion_decision == "rejected"
    assert result.challenger_status == "experimental"
    assert "EVALUATION_CUTOFF_MISMATCH" in result.failure_reason_codes
    assert "VALIDATION_ORIGIN_AFTER_EVALUATION_CUTOFF" in result.failure_reason_codes
    assert "TARGET_DATE_AFTER_EVALUATION_CUTOFF" in result.failure_reason_codes


def test_evaluation_requires_explicit_authoritative_evidence_context() -> None:
    context = _evidence_context()
    champion_card = _card("champion")
    challenger_card = _card("challenger")
    champion = _artifacts(
        champion_card,
        challenger=False,
        evidence_context=context,
    )
    challenger = _artifacts(
        challenger_card,
        challenger=True,
        evidence_context=context,
    )

    with pytest.raises(TypeError, match="evidence_context"):
        evaluate_challenger_promotion(
            champion,
            challenger,
            champion_model_card=champion_card,
            challenger_model_card=challenger_card,
            champion_feature_audit=_audit(champion_card),
            challenger_feature_audit=_audit(challenger_card),
            config=_config(),
        )


def test_seed_mismatch_and_non_deterministic_replay_block_promotion() -> None:
    challenger_card = _card("challenger", seed=8)
    challenger = _artifacts(challenger_card, challenger=True)
    seed_mismatch = _evaluate(
        challenger=challenger,
        challenger_card=challenger_card,
        challenger_audit=_audit(challenger_card),
    )
    assert "SEED_POLICY_VIOLATION" in seed_mismatch.failure_reason_codes

    replay_card = _card("challenger")
    challenger = _artifacts(replay_card, challenger=True)
    replay = challenger.sample(frac=1.0, random_state=9).reset_index(drop=True)
    replay.loc[0, "downstream_asset_prediction"] += 0.1
    replay.loc[0, "downstream_asset_loss"] = (
        replay.loc[0, "downstream_asset_prediction"]
        - replay.loc[0, "downstream_asset_actual"]
    ) ** 2
    replay_failure = _evaluate(
        challenger=challenger,
        challenger_card=replay_card,
        challenger_replay=replay,
    )
    assert "NON_DETERMINISTIC_REPLAY" in replay_failure.failure_reason_codes


def test_different_model_specific_seeds_do_not_change_evaluation_formula() -> None:
    champion_card = _card("champion", seed=4)
    challenger_card = _card("challenger", seed=9)
    result = _evaluate(
        champion=_artifacts(champion_card, challenger=False),
        challenger=_artifacts(challenger_card, challenger=True),
        champion_card=champion_card,
        challenger_card=challenger_card,
        champion_audit=_audit(champion_card),
        challenger_audit=_audit(challenger_card),
        config=_config(seed_policy="model_specific"),
    )
    reference = _evaluate()

    pd.testing.assert_frame_equal(result.aggregate_metrics, reference.aggregate_metrics)
    assert result.promotion_decision == "promoted"


def test_mapping_version_and_loss_definition_must_match_paired_samples() -> None:
    card = _card("challenger")
    challenger = _artifacts(card, challenger=True)
    challenger["mapping_version"] = "mapping-v2"
    result = _evaluate(challenger=challenger, challenger_card=card)
    assert "PAIRED_MAPPING_MISMATCH" in result.failure_reason_codes

    forged_loss = _artifacts(card, challenger=True)
    forged_loss.loc[0, "downstream_asset_loss"] += 1.0
    with pytest.raises(ValueError, match="downstream asset loss"):
        _evaluate(challenger=forged_loss, challenger_card=card)


def test_governed_mapping_reference_is_required_and_retained() -> None:
    context = _evidence_context()
    result = _evaluate(evidence_context=context)
    rebuilt = _rebuild_result(result)

    assert result.promotion_decision == "promoted"
    assert result.evidence_context == context
    assert result.evidence_context.mapping_reference == context.mapping_reference
    assert result.evidence_context.mapping_reference.revalidate() == (
        context.mapping_reference
    )
    assert rebuilt.promotion_decision == "promoted"
    assert isinstance(hash(result.evidence_context), int)
    assert isinstance(hash(result.evidence_context.mapping_reference), int)
    with pytest.raises(FrozenInstanceError):
        result.evidence_context.evaluation_cutoff = date(2099, 1, 1)
    with pytest.raises(ValueError, match="governed_mapping_required"):
        _protocol_card(downstream_mapping_requirement="free_text_mapping_claim")


def test_mapping_reference_cannot_be_constructed_from_claimed_fields() -> None:
    with pytest.raises(TypeError, match="from_published_run"):
        evaluation_api.MappingReference(
            mapping_product="made-up-product",
            mapping_id="made-up-id",
            version="made-up-v1",
            run_id="made-up-run",
            config_hash=HASH_A,
            artifact_hash=HASH_B,
            as_of=date(2020, 3, 31),
        )


def test_forged_mapping_reference_cannot_form_evidence_context() -> None:
    reference = _mapping_reference()
    forged = object.__new__(type(reference))
    for field in fields(reference):
        object.__setattr__(forged, field.name, getattr(reference, field.name))
    object.__setattr__(forged, "mapping_product", "made-up-product")
    object.__setattr__(forged, "mapping_id", "made-up-id")
    object.__setattr__(forged, "version", "made-up-v1")
    object.__setattr__(forged, "run_id", "made-up-run")
    object.__setattr__(forged, "config_hash", HASH_A)
    object.__setattr__(forged, "artifact_hash", HASH_B)

    with pytest.raises(
        evaluation_api.MappingReferenceVerificationError,
        match="does not match the published Mapping run",
    ):
        evaluation_api.PromotionEvidenceContext(
            evaluation_cutoff=date(2022, 12, 31),
            mapping_reference=forged,
        )


def test_unpublished_mapping_directory_is_rejected(tmp_path: Path) -> None:
    run_dir, manifest = _publish_mapping_run(tmp_path / "source")
    unpublished_dir = tmp_path / "unpublished" / manifest.run_id
    unpublished_dir.parent.mkdir()
    shutil.copytree(run_dir, unpublished_dir)

    with pytest.raises(
        evaluation_api.MappingReferenceVerificationError,
        match="published runs directory",
    ):
        evaluation_api.MappingReference.from_published_run(
            unpublished_dir,
            expected_manifest=manifest,
        )


def test_noncanonical_or_untrusted_manifest_is_rejected(tmp_path: Path) -> None:
    run_dir, manifest = _publish_mapping_run(tmp_path / "noncanonical")
    manifest_path = run_dir / "manifest.json"
    manifest_payload = json.loads(manifest_path.read_bytes())
    manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    with pytest.raises(
        evaluation_api.MappingReferenceVerificationError,
        match="canonical",
    ):
        evaluation_api.MappingReference.from_published_run(
            run_dir,
            expected_manifest=manifest,
        )

    trusted_run, _ = _publish_mapping_run(tmp_path / "trusted")
    _, other_manifest = _publish_mapping_run(
        tmp_path / "other",
        model_version="mapping-v2",
    )
    with pytest.raises(
        evaluation_api.MappingReferenceVerificationError,
        match="trusted expected manifest",
    ):
        evaluation_api.MappingReference.from_published_run(
            trusted_run,
            expected_manifest=other_manifest,
        )


@pytest.mark.parametrize(
    ("field", "forged_value"),
    [
        ("mapping_product", "made-up-product"),
        ("mapping_id", "made-up-id"),
        ("version", "mapping-v999"),
        ("run_id", "made-up-run"),
        ("config_hash", HASH_D),
        ("artifact_hash", HASH_C),
        ("as_of", "2099-01-01"),
        ("artifact_filename", "made-up-mapping.json"),
    ],
)
def test_published_catalog_must_match_trusted_manifest_and_products(
    tmp_path: Path,
    field: str,
    forged_value: object,
) -> None:
    run_dir, manifest = _publish_mapping_run(
        tmp_path,
        catalog_overrides={field: forged_value},
    )

    with pytest.raises(evaluation_api.MappingReferenceVerificationError):
        evaluation_api.MappingReference.from_published_run(
            run_dir,
            expected_manifest=manifest,
        )


def test_mapping_artifact_tamper_is_rechecked_before_evaluation(
    tmp_path: Path,
) -> None:
    run_dir, manifest = _publish_mapping_run(tmp_path)
    reference = evaluation_api.MappingReference.from_published_run(
        run_dir,
        expected_manifest=manifest,
    )
    context = _evidence_context(mapping_reference=reference)
    (run_dir / reference.artifact_filename).write_bytes(b"tampered")

    with pytest.raises(
        evaluation_api.MappingReferenceVerificationError,
        match="checksums",
    ):
        _evaluate(evidence_context=context)


def test_mapping_catalog_tamper_is_rechecked_by_result_rebuild(
    tmp_path: Path,
) -> None:
    run_dir, manifest = _publish_mapping_run(tmp_path)
    reference = evaluation_api.MappingReference.from_published_run(
        run_dir,
        expected_manifest=manifest,
    )
    result = _evaluate(evidence_context=_evidence_context(mapping_reference=reference))
    (run_dir / reference.reference_filename).write_bytes(b'{"forged":true}\n')

    with pytest.raises(
        evaluation_api.MappingReferenceVerificationError,
        match="checksums",
    ):
        _rebuild_result(result)


@pytest.mark.parametrize(
    "filename_attribute",
    [None, "reference_filename", "artifact_filename"],
)
def test_mapping_revalidation_rejects_replaced_published_files(
    tmp_path: Path,
    filename_attribute: str | None,
) -> None:
    run_dir, manifest = _publish_mapping_run(tmp_path)
    reference = evaluation_api.MappingReference.from_published_run(
        run_dir,
        expected_manifest=manifest,
    )
    filename = (
        "manifest.json"
        if filename_attribute is None
        else getattr(reference, filename_attribute)
    )
    published_file = run_dir / filename
    replacement = run_dir / f".{published_file.name}.replacement"
    replacement.write_bytes(published_file.read_bytes())
    replacement.replace(published_file)

    with pytest.raises(
        evaluation_api.MappingReferenceVerificationError,
        match="identity changed",
    ):
        reference.revalidate()


def test_mapping_as_of_after_authoritative_cutoff_is_rejected(
    tmp_path: Path,
) -> None:
    run_dir, manifest = _publish_mapping_run(
        tmp_path,
        as_of=date(2099, 1, 1),
    )
    future_mapping = evaluation_api.MappingReference.from_published_run(
        run_dir,
        expected_manifest=manifest,
    )
    with pytest.raises(ValueError, match="evaluation_cutoff"):
        _evidence_context(mapping_reference=future_mapping)


@pytest.mark.parametrize(
    ("field", "forged_value"),
    [
        ("mapping_version", "mapping-v999"),
        ("mapping_run_id", "forged-run"),
        ("mapping_config_hash", HASH_A),
        ("mapping_artifact_hash", HASH_B),
        ("mapping_manifest_hash", HASH_A),
        ("mapping_reference_hash", HASH_B),
        ("mapping_reference_filename", "forged-reference.json"),
        ("mapping_artifact_filename", "forged-mapping.json"),
    ],
)
def test_fold_artifacts_must_match_authoritative_mapping_reference(
    field: str,
    forged_value: str,
) -> None:
    context = _evidence_context()
    champion_card = _card("champion")
    challenger_card = _card("challenger")
    champion = _artifacts(
        champion_card,
        challenger=False,
        evidence_context=context,
    )
    challenger = _artifacts(
        challenger_card,
        challenger=True,
        evidence_context=context,
    )
    champion[field] = forged_value
    challenger[field] = forged_value

    result = _evaluate(
        champion=champion,
        challenger=challenger,
        champion_card=champion_card,
        challenger_card=challenger_card,
        evidence_context=context,
    )

    assert result.promotion_decision == "rejected"
    assert result.challenger_status == "experimental"
    assert "GOVERNED_MAPPING_REFERENCE_MISMATCH" in result.failure_reason_codes


@pytest.mark.parametrize(
    ("config", "reason_code"),
    [
        (_config(minimum_folds=4), "INSUFFICIENT_FOLDS"),
        (_config(minimum_samples=13), "INSUFFICIENT_SAMPLES"),
    ],
)
def test_insufficient_folds_or_samples_keep_champion_live(
    config: PromotionConfig,
    reason_code: str,
) -> None:
    result = _evaluate(config=config)

    assert result.promotion_decision == "rejected"
    assert reason_code in result.failure_reason_codes
    assert result.live_model == "champion-model"
    assert result.challenger_status == "experimental"


def test_model_card_and_feature_audit_prohibitions_are_mandatory() -> None:
    card = _card("challenger")
    direct = _evaluate(
        challenger=_artifacts(card, challenger=True),
        challenger_card=card,
        challenger_audit=_audit(
            card,
            status="failed",
            reasons=("DIRECT_ASSET_ALLOCATION_PROHIBITED",),
        ),
    )
    assert "DIRECT_ASSET_ALLOCATION_PROHIBITED" in direct.failure_reason_codes

    audit = _audit(
        card,
        status="failed",
        reasons=("HISTORICAL_CONTRIBUTION_WEIGHTS_PROHIBITED",),
    )
    historical_weights = _evaluate(
        challenger=_artifacts(card, challenger=True),
        challenger_card=card,
        challenger_audit=audit,
    )
    assert (
        "HISTORICAL_CONTRIBUTION_WEIGHTS_PROHIBITED"
        in historical_weights.failure_reason_codes
    )

    prohibited_feature = _evaluate(
        challenger=_artifacts(card, challenger=True),
        challenger_card=card,
        challenger_audit=_audit(
            card,
            status="failed",
            reasons=("PROHIBITED_FEATURES_PRESENT",),
            forbidden_features=("asset_weight",),
        ),
    )
    assert "PROHIBITED_FEATURES_PRESENT" in prohibited_feature.failure_reason_codes


@pytest.mark.parametrize(
    ("leakage_checks", "reason_code"),
    [
        (
            (
                "visible_date_lte_as_of",
                "generated_date_lte_as_of",
                "trust_me_no_leakage",
            ),
            "FEATURE_AUDIT_UNKNOWN_LEAKAGE_CHECKS",
        ),
        (
            (
                "visible_date_lte_as_of",
                "generated_date_lte_as_of",
            ),
            "FEATURE_AUDIT_MISSING_LEAKAGE_CHECKS",
        ),
    ],
)
def test_feature_audit_gate_rejects_forged_leakage_checks(
    leakage_checks: tuple[str, ...],
    reason_code: str,
) -> None:
    card = _card("challenger")
    result = _evaluate(
        challenger=_artifacts(card, challenger=True),
        challenger_card=card,
        challenger_audit=_audit(card, leakage_checks=leakage_checks),
    )
    gate = result.gate_results.loc[
        result.gate_results["gate"].eq("feature_audit")
    ].iloc[0]

    assert result.promotion_decision == "rejected"
    assert result.challenger_status == "experimental"
    assert reason_code in result.failure_reason_codes
    assert reason_code in gate["reason_codes"]


def test_feature_audit_gate_rejects_checks_reported_as_failed() -> None:
    card = _card("challenger")
    result = _evaluate(
        challenger=_artifacts(card, challenger=True),
        challenger_card=card,
        challenger_audit=_audit(
            card,
            status="failed",
            reasons=("VISIBLE_DATE_CHECK_FAILED",),
        ),
    )
    gate = result.gate_results.loc[
        result.gate_results["gate"].eq("feature_audit")
    ].iloc[0]

    assert "FEATURE_AUDIT_STATUS_FAILED" in result.failure_reason_codes
    assert "VISIBLE_DATE_CHECK_FAILED" in result.failure_reason_codes
    assert "FEATURE_AUDIT_STATUS_FAILED" in gate["reason_codes"]


def test_result_rebuild_rejects_forged_fold_aggregate_decision_and_reasons() -> None:
    result = _evaluate()

    fold_metrics = result.fold_metrics
    fold_metrics.loc[0, "challenger_value"] += 1.0
    with pytest.raises(ValueError, match="fold_metrics.*inconsistent"):
        _rebuild_result(result, fold_metrics=fold_metrics)

    aggregate = result.aggregate_metrics
    aggregate.loc[0, "improvement"] += 1.0
    with pytest.raises(ValueError, match="aggregate_metrics.*inconsistent"):
        _rebuild_result(result, aggregate_metrics=aggregate)

    with pytest.raises(ValueError, match="promotion_decision.*inconsistent"):
        _rebuild_result(
            result,
            promotion_decision="rejected",
            live_model="champion-model",
        )

    with pytest.raises(ValueError, match="failure_reason_codes.*inconsistent"):
        _rebuild_result(result, failure_reason_codes=("FORGED",))

    forged_cutoff = replace(
        result.evidence_context,
        evaluation_cutoff=date(2099, 12, 31),
    )
    with pytest.raises(ValueError, match="inconsistent"):
        _rebuild_result(result, evidence_context=forged_cutoff)


def test_input_shuffle_outputs_are_identical_and_frames_are_defensive() -> None:
    champion_card = _card("champion")
    challenger_card = _card("challenger")
    champion = _artifacts(champion_card, challenger=False)
    challenger = _artifacts(challenger_card, challenger=True)
    champion_before = champion.copy(deep=True)
    challenger_before = challenger.copy(deep=True)

    ordered = _evaluate(
        champion=champion,
        challenger=challenger,
        champion_card=champion_card,
        challenger_card=challenger_card,
    )
    shuffled = _evaluate(
        champion=champion.sample(frac=1.0, random_state=1),
        challenger=challenger.sample(frac=1.0, random_state=2),
        champion_card=champion_card,
        challenger_card=challenger_card,
        champion_replay=champion.sample(frac=1.0, random_state=3),
        challenger_replay=challenger.sample(frac=1.0, random_state=4),
    )

    pd.testing.assert_frame_equal(ordered.fold_metrics, shuffled.fold_metrics)
    pd.testing.assert_frame_equal(
        ordered.aggregate_metrics,
        shuffled.aggregate_metrics,
    )
    pd.testing.assert_frame_equal(ordered.gate_results, shuffled.gate_results)
    pd.testing.assert_frame_equal(champion, champion_before)
    pd.testing.assert_frame_equal(challenger, challenger_before)

    detached_artifacts = ordered.challenger_artifacts
    detached_aggregate = ordered.aggregate_metrics
    detached_artifacts.loc[0, "model_version"] = "forged"
    detached_aggregate.loc[0, "challenger_value"] = 999.0
    assert ordered.challenger_artifacts.loc[0, "model_version"] != "forged"
    assert ordered.aggregate_metrics.loc[0, "challenger_value"] != 999.0
    with pytest.raises(FrozenInstanceError):
        ordered.config.minimum_folds = 1


def test_contract_columns_are_exact_and_stable() -> None:
    assert tuple(_evaluate().fold_metrics.columns) == FOLD_METRIC_COLUMNS
    assert tuple(_evaluate().aggregate_metrics.columns) == AGGREGATE_METRIC_COLUMNS
    assert tuple(_evaluate().gate_results.columns) == GATE_RESULT_COLUMNS
    assert len(OOS_FOLD_ARTIFACT_COLUMNS) == len(set(OOS_FOLD_ARTIFACT_COLUMNS))
