from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.research_c4_forecast import DEFAULT_INPUT, build_forecast


def test_c4_forecast_is_reproducible_and_governed(tmp_path: Path) -> None:
    output = tmp_path / "forecast.json"
    payload = build_forecast(DEFAULT_INPUT, output)

    assert output.exists()
    assert payload["meta"]["data_as_of"] == "2025-12"
    assert payload["meta"]["generator"] == "scripts/research_c4_forecast.py"
    assert payload["qualified_models"] == ["ridge"]
    assert len(payload["forecast"]) == 24
    assert payload["forecast"][0]["date"] == "2026-01"
    assert payload["forecast"][-1]["date"] == "2027-12"

    metrics = {
        (row["model"], row["horizon_months"]): row
        for row in payload["metrics"]
    }
    for horizon in (3, 6, 12):
        ridge = metrics[("ridge", horizon)]
        persistence = metrics[("persistence", horizon)]
        assert ridge["n_origins"] == 52
        assert ridge["mae"] < persistence["mae"]
        assert ridge["phase_accuracy"] > persistence["phase_accuracy"]

    harmonic = next(
        row for row in payload["model_summary"] if row["model"] == "harmonic"
    )
    assert harmonic["qualified_horizons"] >= 2
    assert harmonic["governance_eligible"] is False
    assert harmonic["publish_eligible"] is False
