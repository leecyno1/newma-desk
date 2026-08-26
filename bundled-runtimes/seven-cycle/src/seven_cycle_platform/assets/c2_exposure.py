"""Explicit geographic exposure identities used by the modern C2 validation."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

import pandas as pd
import yaml


def build_c2_asset_exposure_registry(
    columns: Iterable[tuple[str, str]],
    config_path: Path,
) -> pd.DataFrame:
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    default = dict(payload["default"])
    category_rules = payload.get("category_rules", {})
    asset_overrides = payload.get("asset_overrides", {})
    allowed_tracks = set(payload["allowed_c2_tracks"])
    rows: list[dict[str, object]] = []
    for category, name in columns:
        asset_id = f"{category}||{name}"
        specification = {
            **default,
            **category_rules.get(category, {}),
            **asset_overrides.get(asset_id, {}),
        }
        raw_weights = specification["c2_weights"]
        unknown_tracks = set(raw_weights) - allowed_tracks
        if unknown_tracks:
            raise ValueError(f"unknown C2 tracks for {asset_id}: {unknown_tracks}")
        total_weight = float(sum(float(value) for value in raw_weights.values()))
        if total_weight <= 0:
            raise ValueError(f"C2 exposure weights must be positive for {asset_id}")
        weights = {
            str(track): float(value) / total_weight
            for track, value in raw_weights.items()
            if float(value) > 0
        }
        rows.append(
            {
                "assetId": asset_id,
                "category": str(category),
                "name": str(name),
                "listingMarket": specification["listing_market"],
                "underlyingMarket": specification["underlying_market"],
                "revenueExposure": specification["revenue_exposure"],
                "productionExposure": specification["production_exposure"],
                "fundingCurrency": specification["funding_currency"],
                "rateSensitivity": specification["rate_sensitivity"],
                "exposureConfidence": specification["exposure_confidence"],
                "weightBasis": specification["weight_basis"],
                "c2Weights": weights,
            }
        )
    return pd.DataFrame(rows)


def build_weighted_c2_features(
    track_features: Mapping[str, pd.DataFrame],
    weights: Mapping[str, float],
) -> pd.DataFrame:
    weighted: pd.DataFrame | None = None
    for track_id, weight in weights.items():
        track = track_features[track_id] * float(weight)
        weighted = track.copy() if weighted is None else weighted.add(track)
    if weighted is None:
        raise ValueError("at least one C2 exposure weight is required")
    return weighted
