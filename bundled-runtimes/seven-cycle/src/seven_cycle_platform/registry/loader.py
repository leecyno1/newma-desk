"""Load and cross-validate governed YAML registries."""

from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError
import yaml

from seven_cycle_platform.registry.models import (
    AssetRegistry,
    AssetSpec,
    ChannelRegistry,
    ChannelSpec,
    CycleRegistry,
    CycleSpec,
    IndicatorRegistry,
    IndicatorSpec,
    RegistryBundle,
)
from seven_cycle_platform.types import PublicationGateStatus


RegistryFileModel = TypeVar("RegistryFileModel", bound=BaseModel)
EXPECTED_CYCLE_IDS = ["C1", "C2", "C3", "C4", "C5", "C6", "C7"]


class RegistryLoadError(ValueError):
    """A registry file could not be parsed or validated."""


def _load_registry_file(
    directory: Path,
    filename: str,
    model_type: type[RegistryFileModel],
) -> RegistryFileModel:
    path = directory / filename
    if not path.is_file():
        raise FileNotFoundError(f"Registry file does not exist: {path}")

    try:
        with path.open(encoding="utf-8") as registry_file:
            payload = yaml.safe_load(registry_file)
        return model_type.model_validate(payload)
    except (ValidationError, yaml.YAMLError) as error:
        raise RegistryLoadError(
            f"Failed to load registry file: {path}"
        ) from error


def _reject_duplicates(values: list[str], field_name: str) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    if duplicates:
        duplicate_list = ", ".join(sorted(duplicates))
        raise ValueError(f"Duplicate {field_name}: {duplicate_list}")


def _validate_cycles(cycles: list[CycleSpec]) -> None:
    cycle_ids = [cycle.cycle_id for cycle in cycles]
    _reject_duplicates(cycle_ids, "cycle_id")
    if cycle_ids != EXPECTED_CYCLE_IDS:
        raise ValueError("Cycle registry must contain exactly C1 through C7 in order")
    for cycle in cycles:
        for layer in (
            "historical",
            "realtime",
            "forecast",
            "asset_statistics",
        ):
            status = getattr(cycle.publication, layer)
            if status is PublicationGateStatus.SCENARIO_ONLY and (
                cycle.cycle_id,
                layer,
            ) != ("C1", "historical"):
                raise ValueError(
                    f"Cycle {cycle.cycle_id} publication {layer} "
                    "cannot use scenario_only"
                )
            if status is PublicationGateStatus.CALENDAR_ONLY and (
                cycle.cycle_id,
                layer,
            ) not in {("C6", "historical"), ("C6", "forecast")}:
                raise ValueError(
                    f"Cycle {cycle.cycle_id} publication {layer} "
                    "cannot use calendar_only"
                )
        if (
            cycle.publication.asset_statistics is PublicationGateStatus.FORMAL
            and cycle.publication.historical is not PublicationGateStatus.FORMAL
        ):
            raise ValueError(
                f"Cycle {cycle.cycle_id} cannot publish asset statistics "
                "without formal historical evidence"
            )


def _validate_indicators(
    indicators: list[IndicatorSpec],
    cycle_ids: set[str],
) -> None:
    indicator_ids = [indicator.indicator_id for indicator in indicators]
    _reject_duplicates(indicator_ids, "indicator_id")

    concept_scopes: dict[str, set[str]] = {}
    for indicator in indicators:
        concept_scopes.setdefault(indicator.concept, set()).add(
            indicator.concept_scope
        )
    for concept, scopes in concept_scopes.items():
        if len(scopes) > 1:
            scope_list = ", ".join(sorted(scopes))
            raise ValueError(
                f"Indicator concept {concept} mixes concept scopes: {scope_list}"
            )

    for indicator in indicators:
        unknown_cycles = set(indicator.allowed_cycles) - cycle_ids
        if unknown_cycles:
            unknown_list = ", ".join(sorted(unknown_cycles))
            raise ValueError(
                f"Indicator {indicator.indicator_id} references unknown cycles: "
                f"{unknown_list}"
            )

        proxy_for = indicator.proxy.proxy_for
        if indicator.proxy.is_proxy and proxy_for not in indicator_ids:
            raise ValueError(
                f"Indicator {indicator.indicator_id} references unknown indicator "
                f"proxy target: {proxy_for}"
            )
        if indicator.proxy.is_proxy and proxy_for == indicator.indicator_id:
            raise ValueError(
                f"Indicator {indicator.indicator_id} cannot proxy itself"
            )


def _validate_channels(
    channels: list[ChannelSpec],
    indicators: list[IndicatorSpec],
) -> None:
    channel_ids = [channel.channel_id for channel in channels]
    _reject_duplicates(channel_ids, "channel_id")

    registered_concepts = {indicator.concept for indicator in indicators}
    concept_scopes = {
        indicator.concept: indicator.concept_scope for indicator in indicators
    }
    active_indicators = [indicator for indicator in indicators if indicator.active]
    for channel in channels:
        eligible_concepts = set(channel.eligible_indicator_concepts)
        unknown_concepts = eligible_concepts - registered_concepts
        if unknown_concepts:
            unknown_list = ", ".join(sorted(unknown_concepts))
            raise ValueError(
                f"Channel {channel.channel_id} references unknown indicator "
                f"concepts: {unknown_list}"
            )

        asset_specific_concepts = {
            concept
            for concept in eligible_concepts
            if concept_scopes[concept] != "systemic"
        }
        if asset_specific_concepts:
            concept_list = ", ".join(sorted(asset_specific_concepts))
            raise ValueError(
                f"Channel {channel.channel_id} may reference only systemic concepts: "
                f"{concept_list}"
            )

        breadth = sum(
            indicator.concept in eligible_concepts
            for indicator in active_indicators
        )
        if breadth < channel.minimum_breadth:
            raise ValueError(
                f"Channel {channel.channel_id} has breadth {breadth}, below "
                f"minimum {channel.minimum_breadth}"
            )


def _validate_assets(assets: list[AssetSpec]) -> None:
    asset_ids = [asset.asset_id for asset in assets]
    _reject_duplicates(asset_ids, "asset_id")
    asset_id_set = set(asset_ids)

    proxies = [proxy for asset in assets for proxy in asset.proxy_chain]
    _reject_duplicates([proxy.proxy_id for proxy in proxies], "proxy_id")
    for asset in assets:
        current_proxies = [
            proxy for proxy in asset.proxy_chain if proxy.is_current
        ]
        if len(current_proxies) > 1:
            raise ValueError(
                f"Asset {asset.asset_id} has multiple current proxies"
            )

        effective_starts = [
            proxy.effective_from for proxy in asset.proxy_chain
        ]
        if effective_starts != sorted(effective_starts):
            raise ValueError(
                f"Asset {asset.asset_id} proxy_chain must be in chronological order"
            )

        for previous, current in zip(
            asset.proxy_chain,
            asset.proxy_chain[1:],
            strict=False,
        ):
            if (
                previous.effective_to is None
                or current.effective_from <= previous.effective_to
            ):
                raise ValueError(
                    f"Asset {asset.asset_id} has overlapping proxy intervals"
                )

        for proxy in asset.proxy_chain:
            if proxy.proxy_for not in asset_id_set:
                raise ValueError(
                    f"Asset proxy {proxy.proxy_id} references unknown asset: "
                    f"{proxy.proxy_for}"
                )
            if proxy.proxy_for != asset.asset_id:
                raise ValueError(
                    f"Asset proxy {proxy.proxy_id} is listed under "
                    f"{asset.asset_id} but targets {proxy.proxy_for}"
                )


def load_registry_bundle(directory: str | Path) -> RegistryBundle:
    """Load all registry YAML files from an explicit directory."""

    registry_directory = Path(directory)
    if not registry_directory.is_dir():
        raise NotADirectoryError(
            f"Registry directory does not exist: {registry_directory}"
        )

    cycles = _load_registry_file(
        registry_directory,
        "cycles.yaml",
        CycleRegistry,
    ).cycles
    indicators = _load_registry_file(
        registry_directory,
        "indicators.yaml",
        IndicatorRegistry,
    ).indicators
    channels = _load_registry_file(
        registry_directory,
        "channels.yaml",
        ChannelRegistry,
    ).channels
    assets = _load_registry_file(
        registry_directory,
        "assets.yaml",
        AssetRegistry,
    ).assets

    _validate_cycles(cycles)
    cycle_ids = {cycle.cycle_id for cycle in cycles}
    _validate_indicators(indicators, cycle_ids)
    _validate_channels(channels, indicators)
    _validate_assets(assets)

    return RegistryBundle(
        cycles=cycles,
        indicators=indicators,
        channels=channels,
        assets=assets,
    )
