from pathlib import Path
import shutil

from pydantic import ValidationError
import pytest
import yaml

from seven_cycle_platform.registry.loader import load_registry_bundle
from seven_cycle_platform.registry.models import CycleSpec


REGISTRY_DIR = Path(__file__).resolve().parents[3] / "config" / "seven_cycle"

APPROVED_CYCLE_BANDS = {
    "C1": ("A", 35.0, 70.0),
    "C2": ("A", 12.0, 27.0),
    "C3": ("A", 7.0, 15.0),
    "C4": ("M", 30.0, 54.0),
    "C5": ("M", 12.0, 30.0),
    "C6": ("M", 11.5, 12.5),
    "C7": ("M", 3.0, 9.0),
}

APPROVED_HORIZONS = {
    "C1": [12, 24, 60],
    "C2": [6, 12, 24],
    "C3": [3, 6, 12],
    "C4": [1, 3, 6, 12],
    "C5": [1, 3, 6],
    "C6": [1, 3, 6, 12],
    "C7": [1, 3],
}

APPROVED_CYCLE_PRIORS = {
    "C1": (600.0, "years", "scenario_only", "blocked", "blocked", "blocked"),
    "C2": (200.0, "years", "blocked", "blocked", "blocked", "blocked"),
    "C3": (100.0, "years", "blocked", "blocked", "blocked", "blocked"),
    "C4": (42.0, "months", "formal", "limited", "limited", "formal"),
    "C5": (20.0, "months", "blocked", "blocked", "blocked", "blocked"),
    "C6": (
        12.0,
        "calendar",
        "calendar_only",
        "blocked",
        "calendar_only",
        "blocked",
    ),
    "C7": (6.0, "months", "blocked", "blocked", "blocked", "blocked"),
}

APPROVED_CHANNEL_IDS = {
    "growth_demand",
    "inflation_prices",
    "real_rate_discount",
    "liquidity_credit",
    "earnings_margin",
    "risk_premium_crowding",
    "fx_external_demand",
    "supply_inventory_geopolitics",
}

REQUIRED_INDICATOR_CONCEPTS = {
    "pmi",
    "new_orders",
    "gdp",
    "industrial_output",
    "consumption",
    "exports",
    "employment",
    "cpi",
    "ppi",
    "policy_rate",
    "government_bond_yield",
    "real_rate",
    "social_financing",
    "loans",
    "m1",
    "m2",
    "lpr",
    "rrr",
    "reverse_repo",
    "mlf",
    "fiscal_deficit",
    "fiscal_spending",
    "government_bonds",
    "fx",
    "dxy",
    "external_demand",
    "profits",
    "roe",
    "margins",
    "capacity_utilization",
    "market_breadth",
    "turnover",
    "valuation",
    "financing",
    "etf_flow",
    "volatility",
}

CORE_ASSET_SYMBOLS = {
    "cn_equity_hs300": "000300.SH",
    "cn_equity_csi500": "000905.SH",
    "cn_equity_csi1000": "000852.SH",
    "cn_equity_baijiu": "399997.SZ",
    "cn_bond_government_index": "sh000012",
    "gold": "GC=F",
    "copper": "HG=F",
    "crude_oil": "CL=F",
    "usd_cny": "CNY=X",
    "us_equity_sp500": "^GSPC",
    "cny_cash": "DR007",
}


def _copy_registry(tmp_path: Path) -> Path:
    target = tmp_path / "registry"
    shutil.copytree(REGISTRY_DIR, target)
    return target


def _load_yaml(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as registry_file:
        loaded = yaml.safe_load(registry_file)
    assert isinstance(loaded, dict)
    return loaded


def _write_yaml(path: Path, payload: dict[str, object]) -> None:
    with path.open("w", encoding="utf-8") as registry_file:
        yaml.safe_dump(
            payload,
            registry_file,
            allow_unicode=True,
            sort_keys=False,
        )


def _asset_proxy(
    *,
    proxy_id: str,
    proxy_for: str,
    effective_from: str,
    effective_to: str | None,
    is_current: bool,
) -> dict[str, object]:
    return {
        "proxy_id": proxy_id,
        "proxy_for": proxy_for,
        "name_zh": proxy_id,
        "name_en": proxy_id,
        "source": "test",
        "backend": "test.proxy",
        "symbol": proxy_id.upper(),
        "effective_from": effective_from,
        "effective_to": effective_to,
        "is_current": is_current,
        "overlap_calibration": "Test calibration rule.",
        "confidence_discount": 0.25,
    }


def _assert_file_validation_error(
    registry_dir: Path,
    registry_path: Path,
    expected_message: str,
) -> None:
    with pytest.raises(ValueError) as error_info:
        load_registry_bundle(registry_dir)

    assert str(registry_path) in str(error_info.value)
    assert isinstance(error_info.value.__cause__, ValidationError)
    assert expected_message in str(error_info.value.__cause__)


def test_registry_loads_exactly_c1_through_c7() -> None:
    bundle = load_registry_bundle(REGISTRY_DIR)

    assert [cycle.cycle_id for cycle in bundle.cycles] == [
        "C1",
        "C2",
        "C3",
        "C4",
        "C5",
        "C6",
        "C7",
    ]


def test_cycle_search_bands_and_horizons_match_approved_ranges() -> None:
    bundle = load_registry_bundle(REGISTRY_DIR)

    actual_bands = {
        cycle.cycle_id: (
            cycle.frequency,
            cycle.search_min,
            cycle.search_max,
        )
        for cycle in bundle.cycles
    }
    actual_horizons = {
        cycle.cycle_id: cycle.horizons for cycle in bundle.cycles
    }

    assert actual_bands == APPROVED_CYCLE_BANDS
    assert actual_horizons == APPROVED_HORIZONS


def test_cycle_priors_and_layer_policies_match_approved_design() -> None:
    bundle = load_registry_bundle(REGISTRY_DIR)

    actual = {
        cycle.cycle_id: (
            cycle.center_prior_months,
            cycle.period_mode,
            cycle.publication.historical.value,
            cycle.publication.realtime.value,
            cycle.publication.forecast.value,
            cycle.publication.asset_statistics.value,
        )
        for cycle in bundle.cycles
    }

    assert actual == APPROVED_CYCLE_PRIORS


def test_cycle_empirical_bands_match_approved_evidence() -> None:
    bundle = load_registry_bundle(REGISTRY_DIR)

    actual = {
        cycle.cycle_id: cycle.empirical_band_months for cycle in bundle.cycles
    }

    assert actual == {
        "C1": None,
        "C2": None,
        "C3": None,
        "C4": (40.0, 42.2),
        "C5": None,
        "C6": (12.0, 12.0),
        "C7": None,
    }


@pytest.mark.parametrize(
    "empirical_band",
    ([0, 42.2], [42.2, 40]),
)
def test_cycle_rejects_invalid_empirical_band(
    tmp_path: Path,
    empirical_band: list[float],
) -> None:
    registry_dir = _copy_registry(tmp_path)
    cycles_path = registry_dir / "cycles.yaml"
    payload = _load_yaml(cycles_path)
    cycles = payload["cycles"]
    assert isinstance(cycles, list)
    cycle = cycles[3]
    assert isinstance(cycle, dict)
    cycle["empirical_band_months"] = empirical_band
    _write_yaml(cycles_path, payload)

    _assert_file_validation_error(
        registry_dir,
        cycles_path,
        "empirical_band_months must be positive and ordered",
    )


@pytest.mark.parametrize(
    ("cycle_id", "period_mode", "expected_message"),
    (
        ("C5", "calendar", "Only C6 may use calendar period mode"),
        ("C6", "months", "C6 must use calendar period mode"),
    ),
)
def test_cycle_rejects_inconsistent_calendar_period_mode(
    tmp_path: Path,
    cycle_id: str,
    period_mode: str,
    expected_message: str,
) -> None:
    registry_dir = _copy_registry(tmp_path)
    cycles_path = registry_dir / "cycles.yaml"
    payload = _load_yaml(cycles_path)
    cycles = payload["cycles"]
    assert isinstance(cycles, list)
    cycle = next(
        cycle
        for cycle in cycles
        if isinstance(cycle, dict) and cycle.get("cycle_id") == cycle_id
    )
    cycle["period_mode"] = period_mode
    _write_yaml(cycles_path, payload)

    _assert_file_validation_error(
        registry_dir,
        cycles_path,
        expected_message,
    )


@pytest.mark.parametrize(
    ("cycle_id", "updates", "expected_message"),
    (
        (
            "C1",
            {"period_mode": "months"},
            "Annual cycles must use years period mode",
        ),
        (
            "C4",
            {"period_mode": "years"},
            "Monthly cycles must use months period mode",
        ),
        (
            "C6",
            {"frequency": "A"},
            "C6 must use monthly frequency",
        ),
        (
            "C1",
            {"center_prior_months": 601},
            "center_prior_months must equal initial_center converted to months",
        ),
        (
            "C4",
            {"center_prior_months": 43},
            "center_prior_months must equal initial_center converted to months",
        ),
        (
            "C4",
            {"initial_center": None},
            "Cycle initial_center is required for center prior validation",
        ),
    ),
)
def test_cycle_model_rejects_inconsistent_period_units(
    cycle_id: str,
    updates: dict[str, object],
    expected_message: str,
) -> None:
    payload = _load_yaml(REGISTRY_DIR / "cycles.yaml")
    cycles = payload["cycles"]
    assert isinstance(cycles, list)
    cycle = next(
        cycle
        for cycle in cycles
        if isinstance(cycle, dict) and cycle.get("cycle_id") == cycle_id
    )

    with pytest.raises(ValidationError, match=expected_message):
        CycleSpec.model_validate({**cycle, **updates})


def test_cycle_model_accepts_rounded_repeating_annual_center() -> None:
    payload = _load_yaml(REGISTRY_DIR / "cycles.yaml")
    cycles = payload["cycles"]
    assert isinstance(cycles, list)
    cycle = next(
        cycle
        for cycle in cycles
        if isinstance(cycle, dict) and cycle.get("cycle_id") == "C2"
    )

    validated = CycleSpec.model_validate(
        {**cycle, "initial_center": 16.666667}
    )

    assert validated.center_prior_months == 200.0


@pytest.mark.parametrize(
    ("cycle_id", "new_center", "expected_prior_months"),
    (("C1", 51.0, 612.0), ("C5", 21.0, 21.0)),
)
def test_cycle_center_update_normalizes_prior_months(
    cycle_id: str,
    new_center: float,
    expected_prior_months: float,
) -> None:
    bundle = load_registry_bundle(REGISTRY_DIR)
    cycle = next(cycle for cycle in bundle.cycles if cycle.cycle_id == cycle_id)

    updated = cycle.with_initial_center(new_center)

    assert updated.initial_center == new_center
    assert updated.center_prior_months == expected_prior_months


def test_cycle_center_update_revalidates_period_mode() -> None:
    bundle = load_registry_bundle(REGISTRY_DIR)
    cycle = next(cycle for cycle in bundle.cycles if cycle.cycle_id == "C4")
    forged = cycle.model_copy(update={"period_mode": "years"})

    with pytest.raises(
        ValidationError,
        match="Monthly cycles must use months period mode",
    ):
        forged.with_initial_center(43.0)


def test_loader_rejects_formal_asset_statistics_without_formal_history(
    tmp_path: Path,
) -> None:
    registry_dir = _copy_registry(tmp_path)
    cycles_path = registry_dir / "cycles.yaml"
    payload = _load_yaml(cycles_path)
    cycles = payload["cycles"]
    assert isinstance(cycles, list)
    cycle = cycles[0]
    assert isinstance(cycle, dict)
    publication = cycle["publication"]
    assert isinstance(publication, dict)
    publication["asset_statistics"] = "formal"
    _write_yaml(cycles_path, payload)

    with pytest.raises(
        ValueError,
        match=(
            "Cycle C1 cannot publish asset statistics without formal historical "
            "evidence"
        ),
    ):
        load_registry_bundle(registry_dir)


@pytest.mark.parametrize(
    ("cycle_id", "layer", "status"),
    (
        ("C2", "historical", "scenario_only"),
        ("C1", "realtime", "scenario_only"),
        ("C5", "forecast", "calendar_only"),
        ("C6", "realtime", "calendar_only"),
    ),
)
def test_loader_rejects_special_publication_gate_outside_approved_position(
    tmp_path: Path,
    cycle_id: str,
    layer: str,
    status: str,
) -> None:
    registry_dir = _copy_registry(tmp_path)
    cycles_path = registry_dir / "cycles.yaml"
    payload = _load_yaml(cycles_path)
    cycles = payload["cycles"]
    assert isinstance(cycles, list)
    cycle = next(
        cycle
        for cycle in cycles
        if isinstance(cycle, dict) and cycle.get("cycle_id") == cycle_id
    )
    publication = cycle["publication"]
    assert isinstance(publication, dict)
    publication[layer] = status
    _write_yaml(cycles_path, payload)

    with pytest.raises(
        ValueError,
        match=f"Cycle {cycle_id} publication {layer} cannot use {status}",
    ):
        load_registry_bundle(registry_dir)


def test_indicator_registry_covers_the_governed_m1_concepts() -> None:
    bundle = load_registry_bundle(REGISTRY_DIR)

    concepts = {indicator.concept for indicator in bundle.indicators}

    assert REQUIRED_INDICATOR_CONCEPTS <= concepts
    assert all("weight" not in indicator.model_dump() for indicator in bundle.indicators)


def test_seed_indicator_concepts_are_explicitly_systemic() -> None:
    payload = _load_yaml(REGISTRY_DIR / "indicators.yaml")
    indicators = payload["indicators"]
    assert isinstance(indicators, list)

    assert all(
        isinstance(indicator, dict)
        and indicator.get("concept_scope") == "systemic"
        for indicator in indicators
    )


def test_loader_rejects_mixed_scopes_for_one_concept(tmp_path: Path) -> None:
    registry_dir = _copy_registry(tmp_path)
    indicators_path = registry_dir / "indicators.yaml"
    payload = _load_yaml(indicators_path)
    indicators = payload["indicators"]
    assert isinstance(indicators, list)
    new_orders = next(
        indicator
        for indicator in indicators
        if isinstance(indicator, dict)
        and indicator.get("concept") == "new_orders"
    )
    new_orders["concept"] = "pmi"
    new_orders["concept_scope"] = "asset_specific"
    _write_yaml(indicators_path, payload)

    with pytest.raises(ValueError, match="mixes concept scopes"):
        load_registry_bundle(registry_dir)


def test_channel_rejects_asset_specific_indicator_concept(
    tmp_path: Path,
) -> None:
    registry_dir = _copy_registry(tmp_path)
    indicators_path = registry_dir / "indicators.yaml"
    payload = _load_yaml(indicators_path)
    indicators = payload["indicators"]
    assert isinstance(indicators, list)
    cpi = next(
        indicator
        for indicator in indicators
        if isinstance(indicator, dict) and indicator.get("concept") == "cpi"
    )
    cpi["concept_scope"] = "asset_specific"
    _write_yaml(indicators_path, payload)

    with pytest.raises(ValueError, match="only systemic concepts"):
        load_registry_bundle(registry_dir)


def test_new_systemic_indicator_concept_is_extensible(tmp_path: Path) -> None:
    registry_dir = _copy_registry(tmp_path)
    indicators_path = registry_dir / "indicators.yaml"
    indicator_payload = _load_yaml(indicators_path)
    indicators = indicator_payload["indicators"]
    assert isinstance(indicators, list)
    pmi = next(
        indicator
        for indicator in indicators
        if isinstance(indicator, dict) and indicator.get("concept") == "pmi"
    )
    custom_indicator = dict(pmi)
    custom_indicator["indicator_id"] = "custom_systemic_indicator"
    custom_indicator["concept"] = "custom_systemic_concept"
    custom_indicator["concept_scope"] = "systemic"
    indicators.append(custom_indicator)
    _write_yaml(indicators_path, indicator_payload)

    channels_path = registry_dir / "channels.yaml"
    channel_payload = _load_yaml(channels_path)
    channels = channel_payload["channels"]
    assert isinstance(channels, list)
    growth_channel = next(
        channel
        for channel in channels
        if isinstance(channel, dict)
        and channel.get("channel_id") == "growth_demand"
    )
    growth_channel["eligible_indicator_concepts"] = [
        "custom_systemic_concept"
    ]
    growth_channel["minimum_breadth"] = 1
    _write_yaml(channels_path, channel_payload)

    bundle = load_registry_bundle(registry_dir)

    assert any(
        indicator.concept == "custom_systemic_concept"
        for indicator in bundle.indicators
    )


def test_asset_registry_contains_the_approved_core_tier() -> None:
    bundle = load_registry_bundle(REGISTRY_DIR)

    actual_symbols = {asset.asset_id: asset.symbol for asset in bundle.assets}

    assert actual_symbols == CORE_ASSET_SYMBOLS
    assert all(asset.tier == "core" for asset in bundle.assets)


def test_every_asset_proxy_has_explicit_effective_dates() -> None:
    bundle = load_registry_bundle(REGISTRY_DIR)
    proxies = [
        proxy
        for asset in bundle.assets
        for proxy in asset.proxy_chain
    ]

    assert proxies
    assert all(proxy.effective_from is not None for proxy in proxies)
    assert all(proxy.effective_to is not None for proxy in proxies)

    baijiu_proxy = next(
        proxy for proxy in proxies if proxy.symbol == "CI005019.CI"
    )
    assert baijiu_proxy.proxy_for == "cn_equity_baijiu"


def test_indicator_proxy_rejects_closed_current_interval(tmp_path: Path) -> None:
    registry_dir = _copy_registry(tmp_path)
    indicators_path = registry_dir / "indicators.yaml"
    payload = _load_yaml(indicators_path)
    indicators = payload["indicators"]
    assert isinstance(indicators, list)
    indicator = indicators[1]
    assert isinstance(indicator, dict)
    indicator["proxy"] = {
        "is_proxy": True,
        "proxy_for": "cn_pmi_manufacturing",
        "effective_from": "2020-01-01",
        "effective_to": "2020-12-31",
        "is_current": True,
        "notes": "Test proxy.",
    }
    _write_yaml(indicators_path, payload)

    _assert_file_validation_error(
        registry_dir,
        indicators_path,
        "Closed proxy intervals cannot be current",
    )


def test_indicator_proxy_rejects_open_noncurrent_interval(tmp_path: Path) -> None:
    registry_dir = _copy_registry(tmp_path)
    indicators_path = registry_dir / "indicators.yaml"
    payload = _load_yaml(indicators_path)
    indicators = payload["indicators"]
    assert isinstance(indicators, list)
    indicator = indicators[1]
    assert isinstance(indicator, dict)
    indicator["proxy"] = {
        "is_proxy": True,
        "proxy_for": "cn_pmi_manufacturing",
        "effective_from": "2020-01-01",
        "effective_to": None,
        "is_current": False,
        "notes": "Test proxy.",
    }
    _write_yaml(indicators_path, payload)

    _assert_file_validation_error(
        registry_dir,
        indicators_path,
        "Open-ended proxy intervals must be current",
    )


def test_asset_proxy_rejects_closed_current_interval(tmp_path: Path) -> None:
    registry_dir = _copy_registry(tmp_path)
    assets_path = registry_dir / "assets.yaml"
    payload = _load_yaml(assets_path)
    assets = payload["assets"]
    assert isinstance(assets, list)
    baijiu = next(
        asset
        for asset in assets
        if isinstance(asset, dict) and asset.get("asset_id") == "cn_equity_baijiu"
    )
    proxy_chain = baijiu["proxy_chain"]
    assert isinstance(proxy_chain, list)
    proxy = proxy_chain[0]
    assert isinstance(proxy, dict)
    proxy["is_current"] = True
    _write_yaml(assets_path, payload)

    _assert_file_validation_error(
        registry_dir,
        assets_path,
        "Closed asset proxy intervals cannot be current",
    )


def test_asset_proxy_rejects_open_noncurrent_interval(tmp_path: Path) -> None:
    registry_dir = _copy_registry(tmp_path)
    assets_path = registry_dir / "assets.yaml"
    payload = _load_yaml(assets_path)
    assets = payload["assets"]
    assert isinstance(assets, list)
    baijiu = next(
        asset
        for asset in assets
        if isinstance(asset, dict) and asset.get("asset_id") == "cn_equity_baijiu"
    )
    proxy_chain = baijiu["proxy_chain"]
    assert isinstance(proxy_chain, list)
    proxy = proxy_chain[0]
    assert isinstance(proxy, dict)
    proxy["effective_to"] = None
    _write_yaml(assets_path, payload)

    _assert_file_validation_error(
        registry_dir,
        assets_path,
        "Open-ended asset proxy intervals must be current",
    )


def test_asset_proxy_chain_rejects_overlapping_intervals(tmp_path: Path) -> None:
    registry_dir = _copy_registry(tmp_path)
    assets_path = registry_dir / "assets.yaml"
    payload = _load_yaml(assets_path)
    assets = payload["assets"]
    assert isinstance(assets, list)
    baijiu = next(
        asset
        for asset in assets
        if isinstance(asset, dict) and asset.get("asset_id") == "cn_equity_baijiu"
    )
    proxy_chain = baijiu["proxy_chain"]
    assert isinstance(proxy_chain, list)
    proxy_chain.append(
        _asset_proxy(
            proxy_id="overlapping_baijiu_proxy",
            proxy_for="cn_equity_baijiu",
            effective_from="2014-01-01",
            effective_to="2018-12-31",
            is_current=False,
        )
    )
    _write_yaml(assets_path, payload)

    with pytest.raises(ValueError, match="overlapping proxy intervals"):
        load_registry_bundle(registry_dir)


def test_asset_proxy_chain_rejects_out_of_order_intervals(tmp_path: Path) -> None:
    registry_dir = _copy_registry(tmp_path)
    assets_path = registry_dir / "assets.yaml"
    payload = _load_yaml(assets_path)
    assets = payload["assets"]
    assert isinstance(assets, list)
    baijiu = next(
        asset
        for asset in assets
        if isinstance(asset, dict) and asset.get("asset_id") == "cn_equity_baijiu"
    )
    proxy_chain = baijiu["proxy_chain"]
    assert isinstance(proxy_chain, list)
    proxy_chain.append(
        _asset_proxy(
            proxy_id="earlier_baijiu_proxy",
            proxy_for="cn_equity_baijiu",
            effective_from="2000-01-01",
            effective_to="2004-12-31",
            is_current=False,
        )
    )
    _write_yaml(assets_path, payload)

    with pytest.raises(ValueError, match="chronological order"):
        load_registry_bundle(registry_dir)


def test_asset_proxy_chain_rejects_multiple_current_proxies(tmp_path: Path) -> None:
    registry_dir = _copy_registry(tmp_path)
    assets_path = registry_dir / "assets.yaml"
    payload = _load_yaml(assets_path)
    assets = payload["assets"]
    assert isinstance(assets, list)
    hs300 = next(
        asset
        for asset in assets
        if isinstance(asset, dict) and asset.get("asset_id") == "cn_equity_hs300"
    )
    hs300["proxy_chain"] = [
        _asset_proxy(
            proxy_id="hs300_current_proxy_one",
            proxy_for="cn_equity_hs300",
            effective_from="2020-01-01",
            effective_to=None,
            is_current=True,
        ),
        _asset_proxy(
            proxy_id="hs300_current_proxy_two",
            proxy_for="cn_equity_hs300",
            effective_from="2021-01-01",
            effective_to=None,
            is_current=True,
        ),
    ]
    _write_yaml(assets_path, payload)

    with pytest.raises(ValueError, match="multiple current proxies"):
        load_registry_bundle(registry_dir)


def test_channels_use_indicator_concepts_without_asset_whitelists() -> None:
    bundle = load_registry_bundle(REGISTRY_DIR)
    indicator_concepts = {indicator.concept for indicator in bundle.indicators}
    prohibited_fields = {
        "asset_id",
        "asset_ids",
        "asset_whitelist",
        "industries",
        "industry_ids",
    }

    assert {channel.channel_id for channel in bundle.channels} == APPROVED_CHANNEL_IDS
    for channel in bundle.channels:
        channel_payload = channel.model_dump()
        assert channel.eligible_indicator_concepts
        assert set(channel.eligible_indicator_concepts) <= indicator_concepts
        assert prohibited_fields.isdisjoint(channel_payload)


def test_inactive_indicator_concept_remains_known(tmp_path: Path) -> None:
    registry_dir = _copy_registry(tmp_path)
    indicators_path = registry_dir / "indicators.yaml"
    indicator_payload = _load_yaml(indicators_path)
    indicators = indicator_payload["indicators"]
    assert isinstance(indicators, list)
    cpi = next(
        indicator
        for indicator in indicators
        if isinstance(indicator, dict) and indicator.get("concept") == "cpi"
    )
    cpi["active"] = False
    _write_yaml(indicators_path, indicator_payload)

    channels_path = registry_dir / "channels.yaml"
    channel_payload = _load_yaml(channels_path)
    channels = channel_payload["channels"]
    assert isinstance(channels, list)
    inflation_channel = next(
        channel
        for channel in channels
        if isinstance(channel, dict)
        and channel.get("channel_id") == "inflation_prices"
    )
    inflation_channel["eligible_indicator_concepts"] = ["cpi"]
    inflation_channel["minimum_breadth"] = 1
    _write_yaml(channels_path, channel_payload)

    with pytest.raises(ValueError, match="breadth 0, below minimum 1"):
        load_registry_bundle(registry_dir)


def test_channel_passes_when_active_series_count_meets_minimum(
    tmp_path: Path,
) -> None:
    registry_dir = _copy_registry(tmp_path)
    indicators_path = registry_dir / "indicators.yaml"
    indicator_payload = _load_yaml(indicators_path)
    indicators = indicator_payload["indicators"]
    assert isinstance(indicators, list)
    pmi = next(
        indicator
        for indicator in indicators
        if isinstance(indicator, dict) and indicator.get("concept") == "pmi"
    )
    second_pmi = dict(pmi)
    second_pmi["indicator_id"] = "cn_pmi_manufacturing_secondary"
    indicators.append(second_pmi)
    _write_yaml(indicators_path, indicator_payload)

    channels_path = registry_dir / "channels.yaml"
    channel_payload = _load_yaml(channels_path)
    channels = channel_payload["channels"]
    assert isinstance(channels, list)
    growth_channel = next(
        channel
        for channel in channels
        if isinstance(channel, dict)
        and channel.get("channel_id") == "growth_demand"
    )
    growth_channel["eligible_indicator_concepts"] = ["pmi"]
    growth_channel["minimum_breadth"] = 2
    _write_yaml(channels_path, channel_payload)

    bundle = load_registry_bundle(registry_dir)

    assert sum(
        indicator.active and indicator.concept == "pmi"
        for indicator in bundle.indicators
    ) == 2


def test_channel_fails_when_active_series_count_is_below_minimum(
    tmp_path: Path,
) -> None:
    registry_dir = _copy_registry(tmp_path)
    channels_path = registry_dir / "channels.yaml"
    channel_payload = _load_yaml(channels_path)
    channels = channel_payload["channels"]
    assert isinstance(channels, list)
    growth_channel = next(
        channel
        for channel in channels
        if isinstance(channel, dict)
        and channel.get("channel_id") == "growth_demand"
    )
    growth_channel["eligible_indicator_concepts"] = ["pmi"]
    growth_channel["minimum_breadth"] = 2
    _write_yaml(channels_path, channel_payload)

    with pytest.raises(ValueError, match="breadth 1, below minimum 2"):
        load_registry_bundle(registry_dir)


def test_loader_rejects_duplicate_registry_ids(tmp_path: Path) -> None:
    registry_dir = _copy_registry(tmp_path)
    cycles_path = registry_dir / "cycles.yaml"
    payload = _load_yaml(cycles_path)
    cycles = payload["cycles"]
    assert isinstance(cycles, list)
    cycles.append(cycles[0])
    _write_yaml(cycles_path, payload)

    with pytest.raises(ValueError, match="Duplicate cycle_id"):
        load_registry_bundle(registry_dir)


def test_loader_rejects_unknown_channel_indicator_concepts(
    tmp_path: Path,
) -> None:
    registry_dir = _copy_registry(tmp_path)
    channels_path = registry_dir / "channels.yaml"
    payload = _load_yaml(channels_path)
    channels = payload["channels"]
    assert isinstance(channels, list)
    first_channel = channels[0]
    assert isinstance(first_channel, dict)
    concepts = first_channel["eligible_indicator_concepts"]
    assert isinstance(concepts, list)
    concepts.append("unknown_indicator_concept")
    _write_yaml(channels_path, payload)

    with pytest.raises(ValueError, match="unknown indicator concept"):
        load_registry_bundle(registry_dir)


def test_loader_rejects_unknown_asset_proxy_targets(tmp_path: Path) -> None:
    registry_dir = _copy_registry(tmp_path)
    assets_path = registry_dir / "assets.yaml"
    payload = _load_yaml(assets_path)
    assets = payload["assets"]
    assert isinstance(assets, list)
    baijiu = next(
        asset
        for asset in assets
        if isinstance(asset, dict) and asset.get("asset_id") == "cn_equity_baijiu"
    )
    proxy_chain = baijiu["proxy_chain"]
    assert isinstance(proxy_chain, list)
    proxy = proxy_chain[0]
    assert isinstance(proxy, dict)
    proxy["proxy_for"] = "missing_asset"
    _write_yaml(assets_path, payload)

    with pytest.raises(ValueError, match="unknown asset"):
        load_registry_bundle(registry_dir)


def test_channel_schema_forbids_asset_ids(tmp_path: Path) -> None:
    registry_dir = _copy_registry(tmp_path)
    channels_path = registry_dir / "channels.yaml"
    payload = _load_yaml(channels_path)
    channels = payload["channels"]
    assert isinstance(channels, list)
    first_channel = channels[0]
    assert isinstance(first_channel, dict)
    first_channel["asset_ids"] = ["cn_equity_hs300"]
    _write_yaml(channels_path, payload)

    with pytest.raises(ValueError) as error_info:
        load_registry_bundle(registry_dir)

    assert str(channels_path) in str(error_info.value)
    assert isinstance(error_info.value.__cause__, ValidationError)
    assert "asset_ids" in str(error_info.value.__cause__)


def test_yaml_errors_include_registry_path_and_preserve_cause(
    tmp_path: Path,
) -> None:
    registry_dir = _copy_registry(tmp_path)
    channels_path = registry_dir / "channels.yaml"
    channels_path.write_text("channels: [\n", encoding="utf-8")

    with pytest.raises(ValueError) as error_info:
        load_registry_bundle(registry_dir)

    assert str(channels_path) in str(error_info.value)
    assert isinstance(error_info.value.__cause__, yaml.YAMLError)
