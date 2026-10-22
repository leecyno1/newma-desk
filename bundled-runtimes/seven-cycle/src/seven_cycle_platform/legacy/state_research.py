"""Build paired C5/C7 research and their historical asset associations."""

import json
from pathlib import Path
from shutil import copyfile
from tempfile import TemporaryDirectory

from seven_cycle_platform.legacy import (
    c5_liquidity_state,
    c7_risk_appetite_state,
    state_asset_association,
)


def build_state_research(
    *, panel_path: Path, returns_path: Path, public_signal_dir: Path,
    destination: Path, refresh_public: bool = False,
) -> dict[str, object]:
    destination = destination.absolute()
    if destination.exists() or destination.is_symlink():
        raise ValueError("destination already exists; state research is never overwritten")
    required = [panel_path, returns_path]
    if not refresh_public:
        required.extend(public_signal_dir / f"fred_{series}.csv"
                        for series in c7_risk_appetite_state.FRED_SIGNAL_IDS)
    for path in required:
        if not path.is_file():
            raise FileNotFoundError(f"required state research input is missing: {path}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".state-research-", dir=destination.parent) as temporary:
        prepared = Path(temporary) / "prepared"
        signals = prepared / "public-signals"
        signals.mkdir(parents=True)
        if refresh_public:
            c7_risk_appetite_state._refresh_public_signals(signals)
        else:
            for series in c7_risk_appetite_state.FRED_SIGNAL_IDS:
                filename = f"fred_{series}.csv"
                copyfile(public_signal_dir / filename, signals / filename)
        state_paths: dict[str, Path] = {}
        states: dict[str, dict[str, object]] = {}
        for cycle, filename, builder, extra in (
            ("C5", "c5_liquidity_state_research.json", c5_liquidity_state.build_payload, {}),
            ("C7", "c7_risk_appetite_state_research.json", c7_risk_appetite_state.build_payload,
             {"public_signal_dir": signals}),
        ):
            payload = builder(panel_path=panel_path, returns_path=returns_path, **extra)
            path = prepared / filename
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False),
                            encoding="utf-8")
            states[cycle] = payload
            state_paths[cycle] = path
        association = state_asset_association.build_payload(
            returns_path=returns_path, state_paths=state_paths)
        (prepared / "c5_c7_asset_association.json").write_text(
            json.dumps(association, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        if destination.exists() or destination.is_symlink():
            raise ValueError("destination already exists; state research is never overwritten")
        prepared.rename(destination)
    return {
        "status": "prepared", "path": str(destination),
        "cycles": {cycle: {"date": payload["current"]["date"], "status": payload["status"],
                           "publicationStatus": payload["publicationStatus"],
                           "assetForecastStatus": payload["governance"]["assetForecastStatus"]}
                   for cycle, payload in states.items()},
        "associationAssets": {cycle: len(mapping["assets"])
                              for cycle, mapping in association["cycles"].items()},
    }
