# Circle Phase A Research Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Correct the governed C1–C7 definitions, publish auditable evidence and data-identity products, and expose formal/limited/blocked release decisions through the existing immutable catalog and FastAPI stack.

**Architecture:** Extend the existing registry without replacing the cycle engine, add small governance modules for data identity and publication gates, then publish the approved 2026-07-19 research prototypes as immutable Parquet products. The existing DuckDB catalog remains the only query layer; the API only reads stable catalog views and never parses prototype JSON at request time.

**Tech Stack:** Python 3.12, Pydantic 2, PyArrow, Pandas, DuckDB, FastAPI, pytest, Ruff, existing `seven_cycle_platform` publication framework.

---

## File Structure

### New files

- `config/seven_cycle/evidence_baseline.yaml` — machine-readable approved C1–C7 evidence baseline.
- `src/seven_cycle_platform/data/identity.py` — data identity, vintage and freshness contracts.
- `src/seven_cycle_platform/governance/__init__.py` — governance public exports.
- `src/seven_cycle_platform/governance/baseline.py` — strict evidence-baseline loader.
- `src/seven_cycle_platform/governance/gates.py` — deterministic publication gate engine.
- `src/seven_cycle_platform/products/research_governance.py` — Arrow schemas and writers for evidence, data identity, gates and calibration records.
- `src/seven_cycle_platform/pipeline/research_foundation.py` — approved-prototype import and atomic publication pipeline.
- `src/seven_cycle_platform/api/routes/governance.py` — read-only evidence and audit endpoints.
- `tests/unit/data/test_identity.py` — data identity and freshness tests.
- `tests/unit/governance/test_baseline.py` — evidence baseline validation tests.
- `tests/unit/governance/test_gates.py` — publication decision tests.
- `tests/unit/products/test_research_governance.py` — product schema and provenance tests.
- `tests/integration/test_research_foundation_pipeline.py` — immutable publication acceptance test.
- `tests/api/test_governance_api.py` — endpoint and filtering contract tests.
- `docs/runbooks/2026-07-19-research-foundation-release.md` — operator instructions and release interpretation.

### Modified files

- `config/seven_cycle/cycles.yaml` — corrected names, priors and layer policies.
- `src/seven_cycle_platform/types.py` — publication gate enum and expanded data identity enum.
- `src/seven_cycle_platform/registry/models.py` — cycle policy fields.
- `src/seven_cycle_platform/registry/loader.py` — policy cross-validation.
- `src/seven_cycle_platform/catalog/duckdb.py` — managed governance products and stable views.
- `src/seven_cycle_platform/catalog/views.sql` — governance query views.
- `src/seven_cycle_platform/api/app.py` — governance router registration.
- `src/seven_cycle_platform/api/repository.py` — allow-listed governance views and status columns.
- `src/seven_cycle_platform/cli.py` — `build-foundation` command.
- `tests/unit/test_package_smoke.py` — new enum contracts.
- `tests/unit/registry/test_registry_loader.py` — corrected seven-cycle expectations.
- `tests/integration/test_duckdb_catalog.py` — governance product catalog coverage.
- `tests/api/conftest.py` — governance product API fixture tables.
- `tests/unit/test_cli.py` — foundation CLI contract.

## Task 1: Correct the Seven-Cycle Governance Contract

**Files:**
- Modify: `src/seven_cycle_platform/types.py`
- Modify: `src/seven_cycle_platform/registry/models.py`
- Modify: `src/seven_cycle_platform/registry/loader.py`
- Modify: `config/seven_cycle/cycles.yaml`
- Modify: `tests/unit/test_package_smoke.py`
- Modify: `tests/unit/registry/test_registry_loader.py`

- [ ] **Step 1: Write failing enum and registry tests**

Add to `tests/unit/test_package_smoke.py`:

```python
from seven_cycle_platform.types import PublicationGateStatus


def test_publication_gate_status_contract() -> None:
    assert [status.value for status in PublicationGateStatus] == [
        "formal",
        "limited",
        "blocked",
        "scenario_only",
        "calendar_only",
    ]
```

Replace the old band expectations in `tests/unit/registry/test_registry_loader.py` with:

```python
APPROVED_CYCLE_PRIORS = {
    "C1": (600.0, "years", "scenario_only", "blocked", "blocked", "blocked"),
    "C2": (200.0, "years", "blocked", "blocked", "blocked", "blocked"),
    "C3": (100.0, "years", "blocked", "blocked", "blocked", "blocked"),
    "C4": (42.0, "months", "formal", "limited", "limited", "formal"),
    "C5": (20.0, "months", "blocked", "blocked", "blocked", "blocked"),
    "C6": (12.0, "calendar", "calendar_only", "blocked", "calendar_only", "blocked"),
    "C7": (6.0, "months", "blocked", "blocked", "blocked", "blocked"),
}


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
```

- [ ] **Step 2: Run tests and verify the new contract is missing**

Run:

```bash
uv run pytest \
  tests/unit/test_package_smoke.py::test_publication_gate_status_contract \
  tests/unit/registry/test_registry_loader.py::test_cycle_priors_and_layer_policies_match_approved_design \
  -q
```

Expected: FAIL because `PublicationGateStatus`, `center_prior_months`, `period_mode` and `publication` do not exist.

- [ ] **Step 3: Add the publication status enum**

Append to `src/seven_cycle_platform/types.py`:

```python
class PublicationGateStatus(StrEnum):
    FORMAL = "formal"
    LIMITED = "limited"
    BLOCKED = "blocked"
    SCENARIO_ONLY = "scenario_only"
    CALENDAR_ONLY = "calendar_only"
```

- [ ] **Step 4: Add strict cycle layer policy models**

In `src/seven_cycle_platform/registry/models.py`, import `PublicationGateStatus` and add the following definitions immediately after `RegistryModel`:

```python
PeriodMode = Literal["years", "months", "calendar"]


class CyclePublicationPolicy(RegistryModel):
    historical: PublicationGateStatus
    realtime: PublicationGateStatus
    forecast: PublicationGateStatus
    asset_statistics: PublicationGateStatus
    reason: str = Field(min_length=1)
```

Add these fields to `CycleSpec` after `initial_center`:

```python
    center_prior_months: float = Field(gt=0)
    period_mode: PeriodMode
    empirical_band_months: tuple[float, float] | None
    publication: CyclePublicationPolicy
```

Extend `validate_search_band` with:

```python
        if self.empirical_band_months is not None:
            lower, upper = self.empirical_band_months
            if lower <= 0 or lower > upper:
                raise ValueError("empirical_band_months must be positive and ordered")
        if self.period_mode == "calendar" and self.cycle_id != "C6":
            raise ValueError("Only C6 may use calendar period mode")
        if self.cycle_id == "C6" and self.period_mode != "calendar":
            raise ValueError("C6 must use calendar period mode")
```

- [ ] **Step 5: Replace cycle configuration with the approved values**

Keep existing `search_min`, `search_max`, `initial_center`, drift and horizon fields for engine compatibility, but set the following exact values in `config/seven_cycle/cycles.yaml`:

```yaml
cycles:
  - cycle_id: C1
    name_zh: 康波周期
    economic_role: 技术、生产率、人口、能源、制度与长期债务结构。
    frequency: A
    search_min: 42.5
    search_max: 59
    initial_center: 50
    center_prior_months: 600
    period_mode: years
    empirical_band_months: [510, 708]
    publication:
      historical: scenario_only
      realtime: blocked
      forecast: blocked
      asset_statistics: blocked
      reason: 仅发布42.5至59年长期情景带，不发布月度实时相位。
    max_quarterly_drift: 2
    horizons: [12, 24, 60]
    default_usage: conditional

  - cycle_id: C2
    name_zh: 地产周期
    economic_role: 房地产、建设、城市化、按揭信用与财富效应。
    frequency: A
    search_min: 12
    search_max: 27
    initial_center: 16.6666667
    center_prior_months: 200
    period_mode: years
    empirical_band_months: null
    publication:
      historical: blocked
      realtime: blocked
      forecast: blocked
      asset_statistics: blocked
      reason: 尺度敏感且红噪声显著性不足，经验中心暂不发布。
    max_quarterly_drift: 1
    horizons: [6, 12, 24]
    default_usage: unavailable

  - cycle_id: C3
    name_zh: 资本周期
    economic_role: 设备投资、资本形成、利润、产能与融资条件。
    frequency: A
    search_min: 7
    search_max: 15
    initial_center: 8.3333333
    center_prior_months: 100
    period_mode: years
    empirical_band_months: null
    publication:
      historical: blocked
      realtime: blocked
      forecast: blocked
      asset_statistics: blocked
      reason: 原值、对数与增长口径结果不稳定，经验中心暂不发布。
    max_quarterly_drift: 0.5
    horizons: [3, 6, 12]
    default_usage: unavailable

  - cycle_id: C4
    name_zh: 库存周期
    economic_role: 订单、生产、库存、价格与贸易循环。
    frequency: M
    search_min: 30
    search_max: 54
    initial_center: 42
    center_prior_months: 42
    period_mode: months
    empirical_band_months: [40, 42.2]
    publication:
      historical: formal
      realtime: limited
      forecast: limited
      asset_statistics: formal
      reason: 历史周期得到强支持；实时缺少真实vintage，预测输入已过期。
    max_quarterly_drift: 3
    horizons: [1, 3, 6, 12]
    default_usage: formal

  - cycle_id: C5
    name_zh: 流动性周期
    economic_role: 信用脉冲、货币政策、财政投放与全球美元流动性。
    frequency: M
    search_min: 12
    search_max: 30
    initial_center: 20
    center_prior_months: 20
    period_mode: months
    empirical_band_months: null
    publication:
      historical: blocked
      realtime: blocked
      forecast: blocked
      asset_statistics: blocked
      reason: 12至27个月候选分散且未稳定通过红噪声检验。
    max_quarterly_drift: 2
    horizons: [1, 3, 6]
    default_usage: unavailable

  - cycle_id: C6
    name_zh: 季节效应
    economic_role: 日历、财政、信贷、生产、消费与资金面的年度结构。
    frequency: M
    search_min: 11.5
    search_max: 12.5
    initial_center: 12
    center_prior_months: 12
    period_mode: calendar
    empirical_band_months: [12, 12]
    publication:
      historical: calendar_only
      realtime: blocked
      forecast: calendar_only
      asset_statistics: blocked
      reason: 频率由日历定义，仅发布随时间变化的季节振幅和月份结构。
    max_quarterly_drift: 0.25
    horizons: [1, 3, 6, 12]
    default_usage: conditional

  - cycle_id: C7
    name_zh: 风偏和市场交易周期
    economic_role: 风险偏好、市场广度、波动、资金流与拥挤。
    frequency: M
    search_min: 3
    search_max: 9
    initial_center: 6
    center_prior_months: 6
    period_mode: months
    empirical_band_months: null
    publication:
      historical: blocked
      realtime: blocked
      forecast: blocked
      asset_statistics: blocked
      reason: 约5.6个月仅为条件候选，市场收益和广度触及搜索边界。
    max_quarterly_drift: 1
    horizons: [1, 3]
    default_usage: unavailable
```

- [ ] **Step 6: Cross-validate policy consistency**

Add to `_validate_cycles` in `src/seven_cycle_platform/registry/loader.py`:

```python
    for cycle in cycles:
        if (
            cycle.publication.asset_statistics
            is PublicationGateStatus.FORMAL
            and cycle.publication.historical
            is not PublicationGateStatus.FORMAL
        ):
            raise ValueError(
                f"Cycle {cycle.cycle_id} cannot publish asset statistics "
                "without formal historical evidence"
            )
```

- [ ] **Step 7: Run registry and package tests**

Run:

```bash
uv run pytest tests/unit/test_package_smoke.py tests/unit/registry/test_registry_loader.py -q
```

Expected: all tests PASS.

- [ ] **Step 8: Commit**

```bash
git add config/seven_cycle/cycles.yaml \
  src/seven_cycle_platform/types.py \
  src/seven_cycle_platform/registry/models.py \
  src/seven_cycle_platform/registry/loader.py \
  tests/unit/test_package_smoke.py \
  tests/unit/registry/test_registry_loader.py
git commit -m "feat: govern approved seven-cycle publication policies"
```

## Task 2: Add Data Identity and Freshness Contracts

**Files:**
- Create: `src/seven_cycle_platform/data/identity.py`
- Create: `src/seven_cycle_platform/data/__init__.py`
- Modify: `src/seven_cycle_platform/types.py`
- Create: `tests/unit/data/test_identity.py`
- Modify: `tests/unit/test_package_smoke.py`

- [ ] **Step 1: Write failing identity tests**

Create `tests/unit/data/test_identity.py`:

```python
from datetime import date, datetime, timezone

import pytest

from seven_cycle_platform.data.identity import DataIdentity, month_distance
from seven_cycle_platform.types import FreshnessStatus, VintageKind


def test_month_distance_counts_complete_calendar_months() -> None:
    assert month_distance(date(2025, 12, 31), date(2026, 7, 19)) == 7


def test_data_identity_marks_stale_source() -> None:
    identity = DataIdentity.from_dates(
        entity_id="c4_macro_panel",
        source="approved_prototype",
        frequency="M",
        unit="mixed_standardized",
        transform="family_balanced_composite",
        observation_start=date(2005, 1, 31),
        data_as_of=date(2025, 12, 31),
        release_date=date(2026, 1, 15),
        retrieval_time=datetime(2026, 7, 19, tzinfo=timezone.utc),
        vintage_kind=VintageKind.LATEST_HISTORICAL,
        stale_after_months=2,
        proxy_for=None,
        caveat="Latest-restated observations; original release vintages unavailable.",
    )

    assert identity.stale_months == 7
    assert identity.freshness_status is FreshnessStatus.STALE


def test_proxy_identity_requires_target_and_caveat() -> None:
    with pytest.raises(ValueError, match="proxy_for"):
        DataIdentity.from_dates(
            entity_id="proxy",
            source="test",
            frequency="A",
            unit="index",
            transform="none",
            observation_start=date(1900, 1, 1),
            data_as_of=date(2020, 1, 1),
            release_date=date(2020, 1, 2),
            retrieval_time=datetime(2020, 1, 3, tzinfo=timezone.utc),
            vintage_kind=VintageKind.EXPLICIT_PROXY,
            stale_after_months=24,
            proxy_for=None,
            caveat="Historical proxy.",
        )
```

- [ ] **Step 2: Run tests and verify missing contracts**

Run:

```bash
uv run pytest tests/unit/data/test_identity.py -q
```

Expected: FAIL because `identity.py`, `FreshnessStatus` and `EXPLICIT_PROXY` do not exist.

- [ ] **Step 3: Extend shared enums**

Add to `src/seven_cycle_platform/types.py`:

```python
class FreshnessStatus(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNAVAILABLE = "unavailable"
```

Extend `VintageKind` without removing existing values:

```python
class VintageKind(StrEnum):
    REALTIME = "realtime"
    LATEST_HISTORICAL = "latest_historical"
    PSEUDO_VINTAGE = "pseudo_vintage"
    EXPLICIT_PROXY = "explicit_proxy"
    UNAVAILABLE = "unavailable"
```

Replace the existing vintage enum assertion in `tests/unit/test_package_smoke.py` and add freshness coverage:

```python
from seven_cycle_platform.types import FreshnessStatus


def test_vintage_kind_contract() -> None:
    assert [kind.value for kind in VintageKind] == [
        "realtime",
        "latest_historical",
        "pseudo_vintage",
        "explicit_proxy",
        "unavailable",
    ]


def test_freshness_status_contract() -> None:
    assert [status.value for status in FreshnessStatus] == [
        "fresh",
        "stale",
        "unavailable",
    ]
```

- [ ] **Step 4: Implement the immutable identity model**

Create `src/seven_cycle_platform/data/identity.py`:

```python
from datetime import date, datetime, timezone
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from seven_cycle_platform.types import FreshnessStatus, VintageKind


Frequency = Literal["D", "W", "M", "Q", "A"]


def month_distance(start: date, end: date) -> int:
    if end < start:
        raise ValueError("end cannot precede start")
    return (end.year - start.year) * 12 + end.month - start.month


class DataIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    frequency: Frequency
    unit: str = Field(min_length=1)
    transform: str = Field(min_length=1)
    observation_start: date
    data_as_of: date
    release_date: date
    retrieval_time: datetime
    vintage_kind: VintageKind
    stale_months: int = Field(ge=0)
    stale_after_months: int = Field(ge=0)
    freshness_status: FreshnessStatus
    proxy_for: str | None
    caveat: str = Field(min_length=1)

    @classmethod
    def from_dates(
        cls,
        *,
        entity_id: str,
        source: str,
        frequency: Frequency,
        unit: str,
        transform: str,
        observation_start: date,
        data_as_of: date,
        release_date: date,
        retrieval_time: datetime,
        vintage_kind: VintageKind,
        stale_after_months: int,
        proxy_for: str | None,
        caveat: str,
    ) -> Self:
        if retrieval_time.tzinfo is None or retrieval_time.utcoffset() is None:
            raise ValueError("retrieval_time must be timezone-aware")
        utc_retrieval = retrieval_time.astimezone(timezone.utc)
        stale_months = month_distance(data_as_of, utc_retrieval.date())
        freshness = (
            FreshnessStatus.UNAVAILABLE
            if vintage_kind is VintageKind.UNAVAILABLE
            else FreshnessStatus.STALE
            if stale_months > stale_after_months
            else FreshnessStatus.FRESH
        )
        return cls(
            entity_id=entity_id,
            source=source,
            frequency=frequency,
            unit=unit,
            transform=transform,
            observation_start=observation_start,
            data_as_of=data_as_of,
            release_date=release_date,
            retrieval_time=utc_retrieval,
            vintage_kind=vintage_kind,
            stale_months=stale_months,
            stale_after_months=stale_after_months,
            freshness_status=freshness,
            proxy_for=proxy_for,
            caveat=caveat,
        )

    @model_validator(mode="after")
    def validate_identity(self) -> Self:
        if self.observation_start > self.data_as_of:
            raise ValueError("observation_start cannot exceed data_as_of")
        if self.release_date < self.data_as_of:
            raise ValueError("release_date cannot precede data_as_of")
        if self.retrieval_time.tzinfo is None:
            raise ValueError("retrieval_time must be timezone-aware")
        if self.vintage_kind is VintageKind.EXPLICIT_PROXY and not self.proxy_for:
            raise ValueError("explicit proxy identity requires proxy_for")
        if self.vintage_kind is not VintageKind.EXPLICIT_PROXY and self.proxy_for:
            raise ValueError("proxy_for is allowed only for explicit proxies")
        return self
```

Create `src/seven_cycle_platform/data/__init__.py` and export `DataIdentity` and `month_distance`.

- [ ] **Step 5: Run identity and shared enum tests**

Run:

```bash
uv run pytest tests/unit/data/test_identity.py tests/unit/test_package_smoke.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/seven_cycle_platform/types.py \
  src/seven_cycle_platform/data/__init__.py \
  src/seven_cycle_platform/data/identity.py \
  tests/unit/data/test_identity.py \
  tests/unit/test_package_smoke.py
git commit -m "feat: add auditable data identity contracts"
```

## Task 3: Add the Approved Evidence Baseline

**Files:**
- Create: `config/seven_cycle/evidence_baseline.yaml`
- Create: `src/seven_cycle_platform/governance/__init__.py`
- Create: `src/seven_cycle_platform/governance/baseline.py`
- Create: `tests/unit/governance/test_baseline.py`

- [ ] **Step 1: Write failing baseline tests**

Create `tests/unit/governance/test_baseline.py`:

```python
from pathlib import Path

from seven_cycle_platform.governance.baseline import load_evidence_baseline


BASELINE_PATH = (
    Path(__file__).resolve().parents[3]
    / "config"
    / "seven_cycle"
    / "evidence_baseline.yaml"
)


def test_baseline_contains_exactly_c1_through_c7() -> None:
    baseline = load_evidence_baseline(BASELINE_PATH)
    assert [record.cycle_id for record in baseline.cycles] == [
        "C1", "C2", "C3", "C4", "C5", "C6", "C7"
    ]


def test_c4_is_supported_and_c5_is_blocked() -> None:
    baseline = load_evidence_baseline(BASELINE_PATH)
    records = {record.cycle_id: record for record in baseline.cycles}

    assert records["C4"].evidence_status == "supported"
    assert records["C4"].empirical_band_months == (40.0, 42.2)
    assert records["C5"].evidence_status == "unidentified"
    assert "red_noise" in records["C5"].reason_codes
```

- [ ] **Step 2: Run tests and verify the baseline loader is absent**

Run:

```bash
uv run pytest tests/unit/governance/test_baseline.py -q
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Create the exact baseline YAML**

Create `config/seven_cycle/evidence_baseline.yaml`:

```yaml
generated: 2026-07-19
source_document: output/seven_cycle_retest_summary_2026-07-19.md
cycles:
  - cycle_id: C1
    evidence_status: scenario_supported
    center_prior_months: 600
    empirical_band_months: [510, 708]
    family_centers_months: [510, 612, 708]
    reason_codes: [long_sample_only, annual_frequency, family_balanced]
    summary: 高置信家族集中在42.5至51年，利率债务给出59年条件候选。
  - cycle_id: C2
    evidence_status: unidentified
    center_prior_months: 200
    empirical_band_months: null
    family_centers_months: []
    reason_codes: [scale_sensitive, red_noise_not_significant]
    summary: 原始水平约16.8年，对数口径移至20至27年，经验中心暂不发布。
  - cycle_id: C3
    evidence_status: unidentified
    center_prior_months: 100
    empirical_band_months: null
    family_centers_months: []
    reason_codes: [scale_sensitive, red_noise_not_significant]
    summary: 原始水平约8.9年，对数或增长口径多移至10.7至15年。
  - cycle_id: C4
    evidence_status: supported
    center_prior_months: 42
    empirical_band_months: [40, 42.2]
    family_centers_months: [41.55, 40, 42.05, 42.2]
    reason_codes: [cross_family_consensus, cutoff_stable, leave_one_out_stable]
    summary: 生产、库存、价格和贸易四家族稳定集中在40.0至42.2个月。
  - cycle_id: C5
    evidence_status: unidentified
    center_prior_months: 20
    empirical_band_months: null
    family_centers_months: []
    reason_codes: [red_noise_not_significant, transformation_sensitive]
    summary: 水平与脉冲口径分散在12至27个月，没有家族稳定通过检验。
  - cycle_id: C6
    evidence_status: calendar_defined
    center_prior_months: 12
    empirical_band_months: [12, 12]
    family_centers_months: [12]
    reason_codes: [calendar_frequency, amplitude_only]
    summary: 12个月由日历定义，仅估计季节振幅与月份结构。
  - cycle_id: C7
    evidence_status: unidentified
    center_prior_months: 6
    empirical_band_months: null
    family_centers_months: [5.6]
    reason_codes: [conditional_candidate, search_boundary]
    summary: 风格风险偏好约5.6个月为条件候选，市场收益与广度触及9个月上界。
```

- [ ] **Step 4: Implement strict Pydantic loader**

Create `src/seven_cycle_platform/governance/baseline.py` with:

```python
from datetime import date
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
import yaml

from seven_cycle_platform.registry.models import CycleId


EvidenceStatus = Literal[
    "supported",
    "scenario_supported",
    "calendar_defined",
    "unidentified",
]


class EvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cycle_id: CycleId
    evidence_status: EvidenceStatus
    center_prior_months: float = Field(gt=0)
    empirical_band_months: tuple[float, float] | None
    family_centers_months: tuple[float, ...]
    reason_codes: tuple[str, ...] = Field(min_length=1)
    summary: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_band(self) -> "EvidenceRecord":
        if self.evidence_status == "supported" and self.empirical_band_months is None:
            raise ValueError("supported evidence requires empirical_band_months")
        if self.evidence_status == "unidentified" and self.empirical_band_months:
            raise ValueError("unidentified evidence cannot publish an empirical band")
        return self


class EvidenceBaseline(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    generated: date
    source_document: str = Field(min_length=1)
    cycles: tuple[EvidenceRecord, ...] = Field(min_length=7, max_length=7)


def load_evidence_baseline(path: str | Path) -> EvidenceBaseline:
    baseline_path = Path(path)
    with baseline_path.open(encoding="utf-8") as baseline_file:
        payload = yaml.safe_load(baseline_file)
    baseline = EvidenceBaseline.model_validate(payload)
    if [record.cycle_id for record in baseline.cycles] != [
        "C1", "C2", "C3", "C4", "C5", "C6", "C7"
    ]:
        raise ValueError("evidence baseline must contain C1 through C7 in order")
    return baseline
```

Export the loader and models from `src/seven_cycle_platform/governance/__init__.py`.

- [ ] **Step 5: Run baseline tests**

Run:

```bash
uv run pytest tests/unit/governance/test_baseline.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add config/seven_cycle/evidence_baseline.yaml \
  src/seven_cycle_platform/governance \
  tests/unit/governance/test_baseline.py
git commit -m "feat: add approved seven-cycle evidence baseline"
```

## Task 4: Implement Deterministic Publication Gates

**Files:**
- Create: `src/seven_cycle_platform/governance/gates.py`
- Modify: `src/seven_cycle_platform/governance/__init__.py`
- Create: `tests/unit/governance/test_gates.py`

- [ ] **Step 1: Write failing gate tests**

Create `tests/unit/governance/test_gates.py`:

```python
from seven_cycle_platform.governance.gates import GateInput, evaluate_gate
from seven_cycle_platform.types import (
    FreshnessStatus,
    PublicationGateStatus,
    VintageKind,
)


def test_c4_historical_is_formal() -> None:
    decision = evaluate_gate(
        GateInput(
            cycle_id="C4",
            layer="historical",
            configured_status=PublicationGateStatus.FORMAL,
            evidence_status="supported",
            vintage_kind=VintageKind.LATEST_HISTORICAL,
            freshness=FreshnessStatus.STALE,
            model_qualified=None,
        )
    )
    assert decision.status is PublicationGateStatus.FORMAL


def test_c4_realtime_is_limited_without_true_vintage() -> None:
    decision = evaluate_gate(
        GateInput(
            cycle_id="C4",
            layer="realtime",
            configured_status=PublicationGateStatus.LIMITED,
            evidence_status="supported",
            vintage_kind=VintageKind.PSEUDO_VINTAGE,
            freshness=FreshnessStatus.STALE,
            model_qualified=True,
        )
    )
    assert decision.status is PublicationGateStatus.LIMITED
    assert "pseudo_vintage" in decision.reason_codes


def test_stale_forecast_cannot_be_formal() -> None:
    decision = evaluate_gate(
        GateInput(
            cycle_id="C4",
            layer="forecast",
            configured_status=PublicationGateStatus.LIMITED,
            evidence_status="supported",
            vintage_kind=VintageKind.PSEUDO_VINTAGE,
            freshness=FreshnessStatus.STALE,
            model_qualified=True,
        )
    )
    assert decision.status is PublicationGateStatus.LIMITED
    assert "stale_input" in decision.reason_codes


def test_unidentified_cycle_is_blocked_for_assets() -> None:
    decision = evaluate_gate(
        GateInput(
            cycle_id="C5",
            layer="asset_statistics",
            configured_status=PublicationGateStatus.BLOCKED,
            evidence_status="unidentified",
            vintage_kind=VintageKind.LATEST_HISTORICAL,
            freshness=FreshnessStatus.FRESH,
            model_qualified=None,
        )
    )
    assert decision.status is PublicationGateStatus.BLOCKED
    assert "period_unidentified" in decision.reason_codes
```

- [ ] **Step 2: Run tests and verify the gate engine is absent**

Run:

```bash
uv run pytest tests/unit/governance/test_gates.py -q
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement the gate engine**

Create `src/seven_cycle_platform/governance/gates.py`:

```python
from typing import Literal

from pydantic import BaseModel, ConfigDict

from seven_cycle_platform.governance.baseline import EvidenceStatus
from seven_cycle_platform.registry.models import CycleId
from seven_cycle_platform.types import (
    FreshnessStatus,
    PublicationGateStatus,
    VintageKind,
)


ResearchLayer = Literal["historical", "realtime", "forecast", "asset_statistics"]


class GateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cycle_id: CycleId
    layer: ResearchLayer
    configured_status: PublicationGateStatus
    evidence_status: EvidenceStatus
    vintage_kind: VintageKind
    freshness: FreshnessStatus
    model_qualified: bool | None


class GateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cycle_id: CycleId
    layer: ResearchLayer
    status: PublicationGateStatus
    reason_codes: tuple[str, ...]


def evaluate_gate(request: GateInput) -> GateDecision:
    reasons: list[str] = []

    if request.configured_status is PublicationGateStatus.BLOCKED:
        reasons.append(
            "period_unidentified"
            if request.evidence_status == "unidentified"
            else "configured_block"
        )
        return GateDecision(
            cycle_id=request.cycle_id,
            layer=request.layer,
            status=PublicationGateStatus.BLOCKED,
            reason_codes=tuple(reasons),
        )

    if request.evidence_status == "unidentified":
        return GateDecision(
            cycle_id=request.cycle_id,
            layer=request.layer,
            status=PublicationGateStatus.BLOCKED,
            reason_codes=("period_unidentified",),
        )

    status = request.configured_status
    if request.layer == "realtime" and request.vintage_kind is not VintageKind.REALTIME:
        status = PublicationGateStatus.LIMITED
        reasons.append("pseudo_vintage")
    if request.layer == "forecast":
        if request.model_qualified is not True:
            return GateDecision(
                cycle_id=request.cycle_id,
                layer=request.layer,
                status=PublicationGateStatus.BLOCKED,
                reason_codes=("model_not_qualified",),
            )
        if request.freshness is FreshnessStatus.STALE:
            status = PublicationGateStatus.LIMITED
            reasons.append("stale_input")
    if request.layer == "asset_statistics" and request.evidence_status != "supported":
        status = PublicationGateStatus.BLOCKED
        reasons.append("historical_evidence_not_formal")
    if not reasons:
        reasons.append("configured_policy")

    return GateDecision(
        cycle_id=request.cycle_id,
        layer=request.layer,
        status=status,
        reason_codes=tuple(reasons),
    )
```

Export `GateInput`, `GateDecision` and `evaluate_gate` from the governance package.

- [ ] **Step 4: Run gate tests**

Run:

```bash
uv run pytest tests/unit/governance/test_gates.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/seven_cycle_platform/governance \
  tests/unit/governance/test_gates.py
git commit -m "feat: enforce cycle publication gates"
```

## Task 5: Add Governance Product Schemas and Writers

**Files:**
- Create: `src/seven_cycle_platform/products/research_governance.py`
- Modify: `src/seven_cycle_platform/products/__init__.py`
- Create: `tests/unit/products/test_research_governance.py`

- [ ] **Step 1: Write failing product tests**

Create `tests/unit/products/test_research_governance.py`:

```python
from datetime import date, datetime, timezone

import pyarrow.parquet as pq

from seven_cycle_platform.products.research_governance import (
    CYCLE_EVIDENCE_FILENAME,
    CYCLE_EVIDENCE_SCHEMA,
    write_records,
)
from seven_cycle_platform.storage import RunContext


def test_writer_injects_manifest_provenance(tmp_path) -> None:
    context = RunContext.create(
        as_of=date(2026, 7, 19),
        data_vintage=date(2025, 12, 31),
        model_version="research-foundation-v1",
        config={"kind": "research_foundation"},
        input_checksums={"evidence": "0" * 64},
        quality_summary={"passed": 1},
        created_at=datetime(2026, 7, 19, tzinfo=timezone.utc),
    )
    record = {
        "cycle_id": "C4",
        "evidence_status": "supported",
        "center_prior_months": 42.0,
        "empirical_min_months": 40.0,
        "empirical_max_months": 42.2,
        "family_centers_json": "[40.0,41.55,42.05,42.2]",
        "reason_codes_json": '["cross_family_consensus"]',
        "summary": "C4 supported.",
    }

    path = write_records(
        tmp_path,
        filename=CYCLE_EVIDENCE_FILENAME,
        schema=CYCLE_EVIDENCE_SCHEMA,
        records=[record],
        context=context,
    )
    table = pq.read_table(path)

    assert table.column("run_id").to_pylist() == [context.run_id]
    assert table.schema.equals(CYCLE_EVIDENCE_SCHEMA, check_metadata=False)
```

- [ ] **Step 2: Run test and verify the product module is absent**

Run:

```bash
uv run pytest tests/unit/products/test_research_governance.py -q
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement schemas and one generic governed writer**

Create `src/seven_cycle_platform/products/research_governance.py` with four filenames, schemas and a shared writer. Use this exact provenance suffix on every schema:

```python
PROVENANCE_FIELDS = [
    pa.field("run_id", pa.string()),
    pa.field("as_of", pa.date32()),
    pa.field("data_vintage", pa.date32()),
    pa.field("model_version", pa.string()),
    pa.field("config_hash", pa.string()),
    pa.field("created_at", pa.timestamp("us", tz="UTC")),
]
```

Define schemas:

```python
CYCLE_EVIDENCE_FILENAME = "cycle_evidence.parquet"
CYCLE_EVIDENCE_SCHEMA = pa.schema([
    pa.field("cycle_id", pa.string()),
    pa.field("evidence_status", pa.string()),
    pa.field("center_prior_months", pa.float64()),
    pa.field("empirical_min_months", pa.float64()),
    pa.field("empirical_max_months", pa.float64()),
    pa.field("family_centers_json", pa.string()),
    pa.field("reason_codes_json", pa.string()),
    pa.field("summary", pa.string()),
    *PROVENANCE_FIELDS,
])

DATA_IDENTITY_FILENAME = "data_identity.parquet"
DATA_IDENTITY_SCHEMA = pa.schema([
    pa.field("entity_id", pa.string()),
    pa.field("source", pa.string()),
    pa.field("frequency", pa.string()),
    pa.field("unit", pa.string()),
    pa.field("transform", pa.string()),
    pa.field("observation_start", pa.date32()),
    pa.field("source_data_as_of", pa.date32()),
    pa.field("release_date", pa.date32()),
    pa.field("retrieval_time", pa.timestamp("us", tz="UTC")),
    pa.field("vintage_kind", pa.string()),
    pa.field("stale_months", pa.int32()),
    pa.field("stale_after_months", pa.int32()),
    pa.field("freshness_status", pa.string()),
    pa.field("proxy_for", pa.string()),
    pa.field("caveat", pa.string()),
    *PROVENANCE_FIELDS,
])

PUBLICATION_GATE_FILENAME = "publication_gate.parquet"
PUBLICATION_GATE_SCHEMA = pa.schema([
    pa.field("cycle_id", pa.string()),
    pa.field("layer", pa.string()),
    pa.field("status", pa.string()),
    pa.field("reason_codes_json", pa.string()),
    *PROVENANCE_FIELDS,
])

CALIBRATION_LOG_FILENAME = "calibration_log.parquet"
CALIBRATION_LOG_SCHEMA = pa.schema([
    pa.field("calibration_date", pa.date32()),
    pa.field("subject_id", pa.string()),
    pa.field("version", pa.string()),
    pa.field("change_summary", pa.string()),
    pa.field("impact_summary", pa.string()),
    pa.field("status", pa.string()),
    *PROVENANCE_FIELDS,
])
```

Implement `write_records`:

```python
def write_records(
    run_dir: Path,
    *,
    filename: str,
    schema: pa.Schema,
    records: list[dict[str, object]],
    context: RunContext,
) -> Path:
    provenance = {
        "run_id": context.run_id,
        "as_of": context.as_of,
        "data_vintage": context.data_vintage,
        "model_version": context.model_version,
        "config_hash": context.config_hash,
        "created_at": context.created_at,
    }
    rows = [{**record, **provenance} for record in records]
    table = pa.Table.from_pylist(rows, schema=schema)
    path = run_dir / filename
    pq.write_table(table, path, compression="zstd")
    return path
```

- [ ] **Step 4: Run product tests**

Run:

```bash
uv run pytest tests/unit/products/test_research_governance.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/seven_cycle_platform/products/research_governance.py \
  src/seven_cycle_platform/products/__init__.py \
  tests/unit/products/test_research_governance.py
git commit -m "feat: add governed research audit products"
```

## Task 6: Build and Atomically Publish the Research Foundation Run

**Files:**
- Create: `src/seven_cycle_platform/pipeline/research_foundation.py`
- Modify: `src/seven_cycle_platform/pipeline/__init__.py`
- Create: `tests/integration/test_research_foundation_pipeline.py`

- [ ] **Step 1: Write the failing integration test**

Create `tests/integration/test_research_foundation_pipeline.py`:

```python
from datetime import date
from pathlib import Path

import pyarrow.parquet as pq

from seven_cycle_platform.pipeline.research_foundation import (
    FoundationSources,
    build_research_foundation,
)
from seven_cycle_platform.storage.manifest import load_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_foundation_run_publishes_auditable_products(tmp_path) -> None:
    result = build_research_foundation(
        sources=FoundationSources(
            config_dir=PROJECT_ROOT / "config" / "seven_cycle",
            evidence_path=PROJECT_ROOT / "config" / "seven_cycle" / "evidence_baseline.yaml",
            historical_path=PROJECT_ROOT / "output" / "c4_c5_phase_display_prototype_2026-07-19.json",
            realtime_path=PROJECT_ROOT / "output" / "c4_pseudo_realtime_prototype_2026-07-19.json",
            forecast_path=PROJECT_ROOT / "output" / "c4_forecast_prototype_2026-07-19.json",
            asset_path=PROJECT_ROOT / "output" / "c4_asset_statistics_prototype_2026-07-19.json",
        ),
        product_root=tmp_path / "products",
        as_of=date(2026, 7, 19),
    )

    manifest = load_manifest(result.run_dir)
    assert set(manifest.product_checksums) == {
        "calibration_log.parquet",
        "cycle_evidence.parquet",
        "cycle_phase_vintage.parquet",
        "data_identity.parquet",
        "publication_gate.parquet",
    }
    gates = pq.read_table(result.run_dir / "publication_gate.parquet").to_pylist()
    lookup = {(row["cycle_id"], row["layer"]): row for row in gates}
    assert lookup[("C4", "historical")]["status"] == "formal"
    assert lookup[("C4", "realtime")]["status"] == "limited"
    assert lookup[("C5", "asset_statistics")]["status"] == "blocked"
```

- [ ] **Step 2: Run test and verify the pipeline is absent**

Run:

```bash
uv run pytest tests/integration/test_research_foundation_pipeline.py -q
```

Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement source and result contracts**

Create `src/seven_cycle_platform/pipeline/research_foundation.py` with:

```python
@dataclass(frozen=True, slots=True)
class FoundationSources:
    config_dir: Path
    evidence_path: Path
    historical_path: Path
    realtime_path: Path
    forecast_path: Path
    asset_path: Path


@dataclass(frozen=True, slots=True)
class FoundationBuildResult:
    run_id: str
    run_dir: Path
```

Add `_load_json(path)` that returns a dictionary and rejects non-object JSON.

- [ ] **Step 4: Convert the approved C4 historical curve into the existing cycle product**

In the pipeline, read `historical["C4"]["cycle"]`, calculate a one-month slope with `Series.diff().fillna(0)`, and build rows with these exact meanings:

```python
phase_rows = pd.DataFrame({
    "date": pd.to_datetime([row["date"] for row in cycle_rows]) + pd.offsets.MonthEnd(0),
    "cycle_id": "C4",
    "vintage": VintageKind.LATEST_HISTORICAL.value,
    "vintage_caveat": (
        "Two-sided Gaussian and Butterworth historical estimate; "
        "endpoint is not a realtime signal."
    ),
    "angle": [row["phase_angle"] for row in cycle_rows],
    "phase": [
        phase_from_level_slope(level, slope).value
        for level, slope in zip(levels, slopes, strict=True)
    ],
    "level": levels,
    "slope": slopes,
    "amplitude": [row["amplitude"] for row in cycle_rows],
    "uncertainty": [abs(row["high"] - row["low"]) / 2 for row in cycle_rows],
    "center_period": 42.0,
    "bandwidth": 2.2,
    "confidence": [row["method_concentration"] for row in cycle_rows],
})
```

Pass this frame to the existing `build_and_write_cycle_phase_vintage`. Do not create C2/C3/C5/C6/C7 phase rows.

- [ ] **Step 5: Build data identity records from prototype metadata**

Create exactly these entities:

```python
identities = [
    DataIdentity.from_dates(
        entity_id="c4_historical_panel",
        source="output/c4_c5_phase_display_prototype_2026-07-19.json",
        frequency="M",
        unit="standardized_factor",
        transform="family_balanced_two_sided_filter",
        observation_start=date(2005, 1, 31),
        data_as_of=date(2025, 12, 31),
        release_date=date(2026, 7, 19),
        retrieval_time=retrieval_time,
        vintage_kind=VintageKind.LATEST_HISTORICAL,
        stale_after_months=12,
        proxy_for=None,
        caveat="Historical two-sided result; endpoint is not publishable realtime state.",
    ),
    DataIdentity.from_dates(
        entity_id="c4_realtime_panel",
        source="output/c4_pseudo_realtime_prototype_2026-07-19.json",
        frequency="M",
        unit="standardized_factor",
        transform="one_sided_harmonic_kalman",
        observation_start=date(2005, 1, 31),
        data_as_of=date(2025, 12, 31),
        release_date=date(2026, 7, 19),
        retrieval_time=retrieval_time,
        vintage_kind=VintageKind.PSEUDO_VINTAGE,
        stale_after_months=2,
        proxy_for=None,
        caveat=realtime["meta"]["data_vintage_limit"],
    ),
    DataIdentity.from_dates(
        entity_id="c4_asset_return_panel",
        source="output/c4_asset_statistics_prototype_2026-07-19.json",
        frequency="M",
        unit="monthly_return",
        transform="observed_return",
        observation_start=date(2005, 12, 31),
        data_as_of=date(2024, 10, 31),
        release_date=date(2026, 7, 19),
        retrieval_time=retrieval_time,
        vintage_kind=VintageKind.LATEST_HISTORICAL,
        stale_after_months=2,
        proxy_for=None,
        caveat="Gold, copper and crude oil direct sources are unavailable.",
    ),
]
```

- [ ] **Step 6: Evaluate every cycle and layer**

Before evaluating gates, convert the evidence baseline and approved calibration decisions into product rows:

```python
evidence_records = [
    {
        "cycle_id": record.cycle_id,
        "evidence_status": record.evidence_status,
        "center_prior_months": record.center_prior_months,
        "empirical_min_months": (
            record.empirical_band_months[0]
            if record.empirical_band_months is not None
            else None
        ),
        "empirical_max_months": (
            record.empirical_band_months[1]
            if record.empirical_band_months is not None
            else None
        ),
        "family_centers_json": json.dumps(record.family_centers_months),
        "reason_codes_json": json.dumps(record.reason_codes),
        "summary": record.summary,
    }
    for record in baseline.cycles
]

calibration_records = [
    {
        "calibration_date": date(2026, 7, 19),
        "subject_id": "C1",
        "version": "v3",
        "change_summary": "Use family-balanced composites instead of GDP-led aggregation.",
        "impact_summary": "Retain 600-month prior and publish 510-708 month band.",
        "status": "scenario_only",
    },
    {
        "calibration_date": date(2026, 7, 19),
        "subject_id": "C2/C3",
        "version": "v2",
        "change_summary": "Add raw, log and growth transformation sensitivity.",
        "impact_summary": "Withdraw empirical centers.",
        "status": "blocked",
    },
    {
        "calibration_date": date(2026, 7, 19),
        "subject_id": "C4",
        "version": "v4",
        "change_summary": "Add production, inventory, prices and trade validation.",
        "impact_summary": "Publish 40.0-42.2 month empirical band.",
        "status": "formal",
    },
    {
        "calibration_date": date(2026, 7, 19),
        "subject_id": "C5/C7",
        "version": "v2",
        "change_summary": "Add red-noise and search-boundary audit.",
        "impact_summary": "Downgrade to blocked conditional priors.",
        "status": "blocked",
    },
    {
        "calibration_date": date(2026, 7, 19),
        "subject_id": "C4-realtime",
        "version": "v1",
        "change_summary": "Separate two-sided history from one-sided realtime state.",
        "impact_summary": "Label current validation pseudo-realtime.",
        "status": "limited",
    },
    {
        "calibration_date": date(2026, 7, 19),
        "subject_id": "C4-forecast",
        "version": "v1",
        "change_summary": "Evaluate persistence, harmonic, ridge and analog models.",
        "impact_summary": "Only ridge qualifies; stale input prevents formal release.",
        "status": "limited",
    },
]
```

For each cycle in the registry and each layer in `historical`, `realtime`, `forecast`, `asset_statistics`, call `evaluate_gate`. Use:

- historical identity for historical and asset layers;
- realtime identity for realtime and forecast layers;
- `model_qualified=True` only for C4 forecast because `qualified_models == ["ridge"]`;
- `model_qualified=None` for non-forecast layers.

Serialize reason codes with canonical JSON.

- [ ] **Step 7: Publish the five products atomically**

Create a `RunContext` with:

```python
context = RunContext.create(
    as_of=as_of,
    data_vintage=date(2025, 12, 31),
    model_version="research-foundation-v1",
    config={
        "pipeline": "research_foundation",
        "evidence_generated": baseline.generated.isoformat(),
    },
    input_checksums={path.name: sha256_file(path) for path in source_paths},
    quality_summary={
        "cycle_evidence_records": 7,
        "formal_historical_cycles": 1,
        "pseudo_realtime": 1,
        "stale_sources": 2,
    },
    created_at=retrieval_time,
)
```

Use `publish_run(product_root, context, write_staging=...)`. The staging writer must write `cycle_phase_vintage.parquet` plus the four governance products. Return the published run directory.

- [ ] **Step 8: Run integration test**

Run:

```bash
uv run pytest tests/integration/test_research_foundation_pipeline.py -q
```

Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add src/seven_cycle_platform/pipeline/research_foundation.py \
  src/seven_cycle_platform/pipeline/__init__.py \
  tests/integration/test_research_foundation_pipeline.py
git commit -m "feat: publish approved research foundation run"
```

## Task 7: Add Governance Products to the DuckDB Catalog

**Files:**
- Modify: `src/seven_cycle_platform/catalog/duckdb.py`
- Modify: `src/seven_cycle_platform/catalog/views.sql`
- Modify: `tests/integration/test_duckdb_catalog.py`

- [ ] **Step 1: Write failing catalog assertions**

Extend the existing stable-view test in `tests/integration/test_duckdb_catalog.py`:

```python
assert {
    "cycle_evidence",
    "data_identity",
    "publication_gates",
    "calibration_log",
} <= set(result.view_names)
```

Add a test that builds a foundation run, builds a catalog and asserts:

```python
with open_catalog(result.path, run_dir=foundation.run_dir) as connection:
    rows = connection.execute(
        "SELECT cycle_id, layer, status "
        "FROM publication_gates ORDER BY cycle_id, layer"
    ).fetchall()

assert ("C4", "historical", "formal") in rows
assert ("C5", "asset_statistics", "blocked") in rows
```

- [ ] **Step 2: Run the targeted catalog tests**

Run:

```bash
uv run pytest tests/integration/test_duckdb_catalog.py -q
```

Expected: FAIL because the governance source specs and stable views do not exist.

- [ ] **Step 3: Register four managed products**

Import the four schemas and filenames from `products.research_governance`. Add `_SourceSpec` entries:

```python
_SourceSpec(
    product_name="cycle_evidence",
    filename=CYCLE_EVIDENCE_FILENAME,
    source_view="_src_cycle_evidence",
    schema=CYCLE_EVIDENCE_SCHEMA,
),
_SourceSpec(
    product_name="data_identity",
    filename=DATA_IDENTITY_FILENAME,
    source_view="_src_data_identity",
    schema=DATA_IDENTITY_SCHEMA,
),
_SourceSpec(
    product_name="publication_gate",
    filename=PUBLICATION_GATE_FILENAME,
    source_view="_src_publication_gate",
    schema=PUBLICATION_GATE_SCHEMA,
),
_SourceSpec(
    product_name="calibration_log",
    filename=CALIBRATION_LOG_FILENAME,
    source_view="_src_calibration_log",
    schema=CALIBRATION_LOG_SCHEMA,
),
```

Add the stable view names to `STABLE_VIEW_NAMES`.

- [ ] **Step 4: Add stable SQL views**

Append to `src/seven_cycle_platform/catalog/views.sql`:

```sql
CREATE VIEW cycle_evidence AS
SELECT evidence.*
FROM _src_cycle_evidence AS evidence
JOIN _catalog_metadata AS metadata ON evidence.run_id = metadata.run_id;

CREATE VIEW data_identity AS
SELECT identity.*
FROM _src_data_identity AS identity
JOIN _catalog_metadata AS metadata ON identity.run_id = metadata.run_id;

CREATE VIEW publication_gates AS
SELECT gate.*
FROM _src_publication_gate AS gate
JOIN _catalog_metadata AS metadata ON gate.run_id = metadata.run_id;

CREATE VIEW calibration_log AS
SELECT calibration.*
FROM _src_calibration_log AS calibration
JOIN _catalog_metadata AS metadata ON calibration.run_id = metadata.run_id;
```

- [ ] **Step 5: Run catalog tests**

Run:

```bash
uv run pytest tests/integration/test_duckdb_catalog.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/seven_cycle_platform/catalog/duckdb.py \
  src/seven_cycle_platform/catalog/views.sql \
  tests/integration/test_duckdb_catalog.py
git commit -m "feat: catalog research governance products"
```

## Task 8: Expose Evidence and Audit API Endpoints

**Files:**
- Create: `src/seven_cycle_platform/api/routes/governance.py`
- Modify: `src/seven_cycle_platform/api/app.py`
- Modify: `src/seven_cycle_platform/api/repository.py`
- Create: `tests/api/test_governance_api.py`
- Modify: `tests/api/conftest.py`

- [ ] **Step 1: Write failing API tests**

Create `tests/api/test_governance_api.py` using the existing published-run fixtures:

```python
from fastapi.testclient import TestClient


def test_cycle_evidence_endpoint_filters_cycle(client: TestClient) -> None:
    response = client.get("/v1/governance/evidence?cycle_ids=C4")

    assert response.status_code == 200
    rows = response.json()["data"]
    assert [(row["cycle_id"], row["evidence_status"]) for row in rows] == [
        ("C4", "supported")
    ]


def test_publication_endpoint_exposes_block_reason(client: TestClient) -> None:
    response = client.get("/v1/governance/publication?cycle_ids=C5")

    assert response.status_code == 200
    rows = response.json()["data"]
    assert {row["status"] for row in rows} == {"blocked"}
    assert all("period_unidentified" in row["reason_codes_json"] for row in rows)


def test_data_identity_endpoint_reports_stale_sources(client: TestClient) -> None:
    response = client.get("/v1/governance/data-identity")

    assert response.status_code == 200
    assert any(
        row["freshness_status"] == "stale"
        for row in response.json()["data"]
    )
```

- [ ] **Step 2: Run API tests and verify routes are missing**

Run:

```bash
uv run pytest tests/api/test_governance_api.py -q
```

Expected: FAIL with 404 responses.

- [ ] **Step 3: Allow-list governance views and statuses**

Add to `_VIEWS` in `src/seven_cycle_platform/api/repository.py`:

```python
"cycle_evidence",
"data_identity",
"publication_gates",
"calibration_log",
```

Add to `_PRIMARY_STATUS_COLUMNS`:

```python
"publication_gates": "status",
```

Add `entity_id`, `layer`, `calibration_date` and `subject_id` to `_ORDER_COLUMNS`.

- [ ] **Step 4: Add governance products to the API catalog fixture**

Import `CYCLE_EVIDENCE_SCHEMA`, `DATA_IDENTITY_SCHEMA`, `PUBLICATION_GATE_SCHEMA` and `CALIBRATION_LOG_SCHEMA` in `tests/api/conftest.py`. Extend `_tables` with:

```python
        "cycle_evidence.parquet": _table(
            CYCLE_EVIDENCE_SCHEMA,
            {
                "cycle_id": ["C4", "C5"],
                "evidence_status": ["supported", "unidentified"],
                "center_prior_months": [42.0, 20.0],
                "empirical_min_months": [40.0, None],
                "empirical_max_months": [42.2, None],
                "family_centers_json": ["[40.0,42.2]", "[]"],
                "reason_codes_json": [
                    '["cross_family_consensus"]',
                    '["red_noise_not_significant"]',
                ],
                "summary": ["C4 supported.", "C5 unidentified."],
                **_provenance(context, 2),
            },
        ),
        "publication_gate.parquet": _table(
            PUBLICATION_GATE_SCHEMA,
            {
                "cycle_id": ["C4", "C5", "C5", "C5", "C5"],
                "layer": [
                    "historical",
                    "historical",
                    "realtime",
                    "forecast",
                    "asset_statistics",
                ],
                "status": ["formal", "blocked", "blocked", "blocked", "blocked"],
                "reason_codes_json": [
                    '["configured_policy"]',
                    '["period_unidentified"]',
                    '["period_unidentified"]',
                    '["period_unidentified"]',
                    '["period_unidentified"]',
                ],
                **_provenance(context, 5),
            },
        ),
        "data_identity.parquet": _table(
            DATA_IDENTITY_SCHEMA,
            {
                "entity_id": ["c4_macro_panel"],
                "source": ["approved_prototype"],
                "frequency": ["M"],
                "unit": ["standardized_factor"],
                "transform": ["family_balanced_composite"],
                "observation_start": [date(2005, 1, 31)],
                "source_data_as_of": [date(2025, 12, 31)],
                "release_date": [date(2026, 7, 19)],
                "retrieval_time": [datetime(2026, 7, 19, tzinfo=timezone.utc)],
                "vintage_kind": ["pseudo_vintage"],
                "stale_months": [7],
                "stale_after_months": [2],
                "freshness_status": ["stale"],
                "proxy_for": [None],
                "caveat": ["Original release vintages unavailable."],
                **_provenance(context, 1),
            },
        ),
        "calibration_log.parquet": _table(
            CALIBRATION_LOG_SCHEMA,
            {
                "calibration_date": [date(2026, 7, 19)],
                "subject_id": ["C4"],
                "version": ["v4"],
                "change_summary": ["Added four-family validation."],
                "impact_summary": ["Empirical band 40.0-42.2 months."],
                "status": ["formal"],
                **_provenance(context, 1),
            },
        ),
```

- [ ] **Step 5: Implement governance routes**

Create `src/seven_cycle_platform/api/routes/governance.py`:

```python
from fastapi import APIRouter, Request

from seven_cycle_platform.api.app import envelope_response
from seven_cycle_platform.api.dependencies import (
    QueryFiltersDependency,
    RequestContextDependency,
)
from seven_cycle_platform.api.repository import query_view
from seven_cycle_platform.api.schemas import APPROVED_ROUTE_RESPONSES, ResponseEnvelope


router = APIRouter(prefix="/governance", tags=["governance"])


def _respond(request, context, filters, view):
    return envelope_response(
        request,
        context,
        query_view(context, view, filters),
        filters,
    )


@router.get("/evidence", response_model=ResponseEnvelope, responses=APPROVED_ROUTE_RESPONSES)
def evidence(request: Request, context: RequestContextDependency, filters: QueryFiltersDependency):
    return _respond(request, context, filters, "cycle_evidence")


@router.get("/publication", response_model=ResponseEnvelope, responses=APPROVED_ROUTE_RESPONSES)
def publication(request: Request, context: RequestContextDependency, filters: QueryFiltersDependency):
    return _respond(request, context, filters, "publication_gates")


@router.get("/data-identity", response_model=ResponseEnvelope, responses=APPROVED_ROUTE_RESPONSES)
def data_identity(request: Request, context: RequestContextDependency, filters: QueryFiltersDependency):
    return _respond(request, context, filters, "data_identity")


@router.get("/calibrations", response_model=ResponseEnvelope, responses=APPROVED_ROUTE_RESPONSES)
def calibrations(request: Request, context: RequestContextDependency, filters: QueryFiltersDependency):
    return _respond(request, context, filters, "calibration_log")
```

Import and register this router in `create_app`.

- [ ] **Step 6: Run API tests**

Run:

```bash
uv run pytest tests/api/test_governance_api.py tests/api/test_release_degradation.py -q
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/seven_cycle_platform/api/routes/governance.py \
  src/seven_cycle_platform/api/app.py \
  src/seven_cycle_platform/api/repository.py \
  tests/api/test_governance_api.py \
  tests/api/conftest.py
git commit -m "feat: expose cycle evidence and release audit API"
```

## Task 9: Add CLI, Runbook and Full Phase Verification

**Files:**
- Modify: `src/seven_cycle_platform/cli.py`
- Modify: `tests/unit/test_cli.py`
- Create: `docs/runbooks/2026-07-19-research-foundation-release.md`

- [ ] **Step 1: Write failing CLI test**

Add to `tests/unit/test_cli.py`:

```python
def test_build_foundation_command_publishes_run(tmp_path, capsys) -> None:
    exit_code = main([
        "build-foundation",
        "--as-of", "2026-07-19",
        "--product-root", str(tmp_path / "products"),
        "--project-root", str(PROJECT_ROOT),
    ])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "live"
    assert payload["run_id"]
```

- [ ] **Step 2: Run test and verify command is absent**

Run:

```bash
uv run pytest tests/unit/test_cli.py -q
```

Expected: FAIL because `build-foundation` is not recognized.

- [ ] **Step 3: Add the CLI handler and parser**

Add:

```python
def handle_build_foundation(arguments: argparse.Namespace) -> int:
    project_root = arguments.project_root
    result = build_research_foundation(
        sources=FoundationSources(
            config_dir=project_root / "config" / "seven_cycle",
            evidence_path=project_root / "config" / "seven_cycle" / "evidence_baseline.yaml",
            historical_path=project_root / "output" / "c4_c5_phase_display_prototype_2026-07-19.json",
            realtime_path=project_root / "output" / "c4_pseudo_realtime_prototype_2026-07-19.json",
            forecast_path=project_root / "output" / "c4_forecast_prototype_2026-07-19.json",
            asset_path=project_root / "output" / "c4_asset_statistics_prototype_2026-07-19.json",
        ),
        product_root=arguments.product_root,
        as_of=arguments.as_of,
    )
    _print_json({
        "run_id": result.run_id,
        "path": redact_secrets(str(result.run_dir)),
        "status": "live",
    })
    return 0
```

Register `build-foundation` with `--as-of`, `--product-root` and `--project-root` arguments.

- [ ] **Step 4: Write the operator runbook**

Create `docs/runbooks/2026-07-19-research-foundation-release.md` with these exact sections:

```markdown
# Research Foundation Release

## Build

`uv run seven-cycle build-foundation --as-of 2026-07-19 --product-root products/circle`

## Verify

`RUN_ID=$(python -c 'import json; print(json.load(open("products/circle/latest.json"))["run_id"])')`

`uv run seven-cycle verify --run-id "$RUN_ID" --product-root products/circle`

## Interpretation

- C4 historical: formal.
- C4 realtime: limited because the source is pseudo-vintage.
- C4 forecast: limited because the model passed but input data are stale.
- C1: scenario only.
- C2/C3/C5/C7: blocked.
- C6: calendar only.

## Failure Rule

If any input checksum, schema, provenance or publication test fails, the prior `latest.json` remains unchanged.
```

- [ ] **Step 5: Run the complete Phase A test set**

Run:

```bash
uv run pytest \
  tests/unit/test_package_smoke.py \
  tests/unit/registry/test_registry_loader.py \
  tests/unit/data/test_identity.py \
  tests/unit/governance \
  tests/unit/products/test_research_governance.py \
  tests/integration/test_research_foundation_pipeline.py \
  tests/integration/test_duckdb_catalog.py \
  tests/api/test_governance_api.py \
  tests/unit/test_cli.py \
  -q
```

Expected: all tests PASS.

- [ ] **Step 6: Run formatting and static checks**

Run:

```bash
uv run ruff check src tests
uv run ruff format --check src tests
```

Expected: both commands exit 0.

- [ ] **Step 7: Commit the phase completion**

```bash
git add src/seven_cycle_platform/cli.py \
  tests/unit/test_cli.py \
  docs/runbooks/2026-07-19-research-foundation-release.md
git commit -m "feat: complete research foundation release workflow"
```

- [ ] **Step 8: Push both remotes**

```bash
git push github main
git -c http.proxy= push gitee main
```

Expected: both remotes report `main` updated to the same commit.

## Phase A Acceptance Checklist

- [ ] C1–C7 names and center priors match the approved design.
- [ ] C2/C3/C5/C7 are not marked formally publishable.
- [ ] C6 is represented as calendar-defined seasonal structure.
- [ ] C4 historical state is formal, C4 realtime and forecast are limited.
- [ ] Every source carries vintage identity and freshness.
- [ ] The governed run contains evidence, phase, data identity, gate and calibration products.
- [ ] DuckDB exposes stable governance views.
- [ ] FastAPI exposes evidence, publication, data identity and calibration endpoints.
- [ ] Prototype JSON is consumed only at build time, never at request time.
- [ ] All Phase A tests and Ruff checks pass.
- [ ] GitHub and Gitee contain the same Phase A completion commit.
