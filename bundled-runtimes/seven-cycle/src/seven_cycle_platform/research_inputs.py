"""Portable, paired browser/API research inputs; no database or raw data copy."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import tempfile

from seven_cycle_platform.pipeline.circle_deployment import RESEARCH_DATA_FILENAMES


SNAPSHOT_FILENAME = "research-inputs.json"
RESEARCH_FILENAMES = (
    "asset_cycle_state_forecast.json",
    "c4_asset_statistics_current.json",
    "c4_forecast.json",
)


def _read_object(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Research input must be a JSON object: {path.name}")
    return value


@dataclass(frozen=True)
class ResearchInputs:
    root: Path

    @property
    def web_data_dir(self) -> Path:
        return self.root / "web-data"

    @property
    def asset_forecast_path(self) -> Path:
        return self.root / "research" / RESEARCH_FILENAMES[0]

    @property
    def asset_statistics_path(self) -> Path:
        return self.root / "research" / RESEARCH_FILENAMES[1]

    @property
    def c4_forecast_path(self) -> Path:
        return self.root / "research" / RESEARCH_FILENAMES[2]

    def install_web_data(self, web_root: Path) -> None:
        destination = web_root / "data"
        destination.mkdir(parents=True, exist_ok=True)
        for name in RESEARCH_DATA_FILENAMES:
            shutil.copyfile(self.web_data_dir / name, destination / name)


def _validate_pairing(inputs: ResearchInputs) -> dict:
    web = {name: _read_object(inputs.web_data_dir / name) for name in RESEARCH_DATA_FILENAMES}
    raw_forecast = _read_object(inputs.asset_forecast_path)
    raw_statistics = _read_object(inputs.asset_statistics_path)
    raw_c4 = _read_object(inputs.c4_forecast_path)
    assets = web["asset-statistics.json"]
    joint = assets.get("currentCycleForecast")
    if not isinstance(joint, dict) or not isinstance(raw_forecast.get("assets"), list):
        raise ValueError("Research snapshot is missing joint asset forecasts")
    # The browser builder adds only these three presentation fields to the
    # embedded forecast. All source fields and predictions must still agree.
    joint = {**joint, "meta": dict(joint.get("meta", {}))}
    for key in ("layer", "includedCycles", "separateFromSingleCycleMapping"):
        joint["meta"].pop(key, None)
    if joint != raw_forecast:
        raise ValueError("Browser/API joint asset forecasts do not match")
    if not isinstance(raw_statistics.get("assets"), list) or assets.get("assets") != raw_statistics["assets"]:
        raise ValueError("Browser/API historical asset statistics do not match")
    for key in ("phase_labels", "summary"):
        if assets.get(key) != raw_statistics.get(key):
            raise ValueError(f"Browser/API historical asset statistics do not match: {key}")
    extension = web["forecast-extension.json"]
    for browser_key, source_key in (
        ("forecast", "forecast"), ("history", "history"),
        ("modelSummary", "model_summary"), ("qualifiedModels", "qualified_models"),
        ("phaseWindows", "phase_windows"), ("eligibility", "eligibility"),
    ):
        if source_key not in raw_c4 or extension.get(browser_key) != raw_c4[source_key]:
            raise ValueError(f"Browser/API C4 forecast does not match: {browser_key}")
    c4_meta = dict(extension.get("meta", {}))
    for key in ("build_as_of", "stale_months_at_build"):
        c4_meta.pop(key, None)
    if not isinstance(raw_c4.get("meta"), dict) or c4_meta != raw_c4["meta"]:
        raise ValueError("Browser/API C4 forecast metadata does not match")
    return {
        name: {key: payload.get("meta", {}).get(key) for key in (
            "generated", "asOf", "data_as_of", "assetDataThrough", "modelVersion",
        )}
        for name, payload in {
            **web,
            **dict(zip(RESEARCH_FILENAMES, (raw_forecast, raw_statistics, raw_c4))),
        }.items()
    }


def load_research_inputs(root: Path) -> ResearchInputs:
    inputs = ResearchInputs(root.resolve())
    manifest = _read_object(inputs.root / SNAPSHOT_FILENAME)
    if manifest.get("schemaVersion") != 1 or manifest.get("kind") != "circle-research-inputs":
        raise ValueError("Unsupported research input snapshot")
    if manifest.get("sourceDates") != _validate_pairing(inputs):
        raise ValueError("Research input snapshot dates do not match its files")
    return inputs


def export_research_inputs(
    *, web_data_dir: Path, research_output_dir: Path,
    c4_forecast_path: Path, destination: Path,
) -> ResearchInputs:
    """Copy the allowlisted derived inputs without refreshing or rewriting them."""
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError(f"Research snapshot destination already exists: {destination}")
    sources = [
        *((web_data_dir / name, Path("web-data") / name) for name in RESEARCH_DATA_FILENAMES),
        *((research_output_dir / name, Path("research") / name) for name in RESEARCH_FILENAMES[:2]),
        (c4_forecast_path, Path("research") / RESEARCH_FILENAMES[2]),
    ]
    for source, _ in sources:
        if not source.is_file():
            raise FileNotFoundError(f"Required research input is missing: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".research-inputs-", dir=destination.parent) as temporary:
        staged = Path(temporary) / "snapshot"
        for source, relative in sources:
            target = staged / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        inputs = ResearchInputs(staged)
        dates = _validate_pairing(inputs)
        (staged / SNAPSHOT_FILENAME).write_text(
            json.dumps({
                "schemaVersion": 1, "kind": "circle-research-inputs",
                "sourceDates": dates,
                "usage": "Derived research snapshot; dates are unchanged; not a live refresh or publication approval.",
            }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        if destination.exists():
            raise FileExistsError(f"Research snapshot destination already exists: {destination}")
        staged.rename(destination)
    return ResearchInputs(destination)
