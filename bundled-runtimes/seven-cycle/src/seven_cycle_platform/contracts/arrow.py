"""Stable PyArrow schemas for persisted platform contracts."""

import pyarrow as pa


RAW_OBSERVATION_SCHEMA = pa.schema(
    [
        pa.field("entity_id", pa.string()),
        pa.field("observation_date", pa.date32()),
        pa.field("release_date", pa.date32()),
        pa.field("vintage_date", pa.date32()),
        pa.field("value", pa.float64()),
        pa.field("unit", pa.string()),
        pa.field("source", pa.string()),
        pa.field("retrieval_time", pa.timestamp("us", tz="UTC")),
        pa.field("revision_number", pa.int32()),
        pa.field("quality_status", pa.string()),
        pa.field("vintage_kind", pa.string()),
    ]
)


QUALITY_FINDING_SCHEMA = pa.schema(
    [
        pa.field("entity_id", pa.string()),
        pa.field("check", pa.string()),
        pa.field("severity", pa.string()),
        pa.field("status", pa.string()),
        pa.field("message", pa.string()),
        pa.field("observed_value", pa.float64()),
        pa.field("threshold", pa.float64()),
    ]
)


CYCLE_PHASE_VINTAGE_SCHEMA = pa.schema(
    [
        pa.field("date", pa.date32()),
        pa.field("cycle_id", pa.string()),
        pa.field("vintage", pa.string()),
        pa.field("vintage_caveat", pa.string()),
        pa.field("angle", pa.float64()),
        pa.field("phase", pa.string()),
        pa.field("level", pa.float64()),
        pa.field("slope", pa.float64()),
        pa.field("amplitude", pa.float64()),
        pa.field("uncertainty", pa.float64()),
        pa.field("center_period", pa.float64()),
        pa.field("bandwidth", pa.float64()),
        pa.field("confidence", pa.float64()),
        pa.field("run_id", pa.string()),
        pa.field("as_of", pa.date32()),
        pa.field("data_vintage", pa.date32()),
        pa.field("model_version", pa.string()),
        pa.field("config_hash", pa.string()),
        pa.field("created_at", pa.timestamp("us", tz="UTC")),
    ]
)


CHANNEL_STATE_SCHEMA = pa.schema(
    [
        pa.field("date", pa.date32()),
        pa.field("channel_id", pa.string()),
        pa.field("state", pa.float64()),
        pa.field("innovation", pa.float64()),
        pa.field("uncertainty", pa.float64()),
        pa.field("member_count", pa.int32()),
        pa.field("concept_count", pa.int32()),
        pa.field("revision_risk", pa.float64()),
        pa.field("vintage_kind", pa.string()),
        pa.field("confidence", pa.float64()),
        pa.field("status", pa.string()),
        pa.field("status_reason", pa.string()),
        pa.field("member_weights_json", pa.string()),
        pa.field("run_id", pa.string()),
        pa.field("as_of", pa.date32()),
        pa.field("data_vintage", pa.date32()),
        pa.field("model_version", pa.string()),
        pa.field("config_hash", pa.string()),
        pa.field("created_at", pa.timestamp("us", tz="UTC")),
    ]
)


ASSET_ATTRIBUTION_SCHEMA = pa.schema(
    [
        pa.field("asset_id", pa.string()),
        pa.field("period_start", pa.date32()),
        pa.field("period_end", pa.date32()),
        pa.field("horizon_months", pa.int32()),
        pa.field("return_basis", pa.string()),
        pa.field("component_type", pa.string()),
        pa.field("component_id", pa.string()),
        pa.field("point_contribution", pa.float64()),
        pa.field("lower_50", pa.float64()),
        pa.field("upper_50", pa.float64()),
        pa.field("lower_80", pa.float64()),
        pa.field("upper_80", pa.float64()),
        pa.field("significance", pa.string()),
        pa.field("is_explained", pa.bool_()),
        pa.field("is_residual", pa.bool_()),
        pa.field("observed_return", pa.float64()),
        pa.field("reconstructed_return", pa.float64()),
        pa.field("interval_status", pa.string()),
        pa.field("status", pa.string()),
        pa.field("evidence_level", pa.string()),
        pa.field("effective_samples", pa.int32()),
        pa.field("draw_count", pa.int32()),
        pa.field("run_id", pa.string()),
        pa.field("as_of", pa.date32()),
        pa.field("data_vintage", pa.date32()),
        pa.field("model_version", pa.string()),
        pa.field("config_hash", pa.string()),
        pa.field("created_at", pa.timestamp("us", tz="UTC")),
    ]
)


ASSET_ATTRIBUTION_CONSERVATION_SCHEMA = pa.schema(
    [
        pa.field("asset_id", pa.string()),
        pa.field("period_start", pa.date32()),
        pa.field("period_end", pa.date32()),
        pa.field("horizon_months", pa.int32()),
        pa.field("return_basis", pa.string()),
        pa.field("point_component_sum", pa.float64()),
        pa.field("observed_return", pa.float64()),
        pa.field("point_conservation_error", pa.float64()),
        pa.field("max_draw_conservation_error", pa.float64()),
        pa.field("available_component_count", pa.int32()),
        pa.field("unavailable_component_count", pa.int32()),
        pa.field("status", pa.string()),
        pa.field("run_id", pa.string()),
        pa.field("as_of", pa.date32()),
        pa.field("data_vintage", pa.date32()),
        pa.field("model_version", pa.string()),
        pa.field("config_hash", pa.string()),
        pa.field("created_at", pa.timestamp("us", tz="UTC")),
    ]
)
