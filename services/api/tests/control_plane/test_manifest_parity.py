import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from vibe_visualization_api.control_plane.schemas import ModuleManifest


FIXTURE_PATH = (
    Path(__file__).resolve().parents[4]
    / "tests"
    / "fixtures"
    / "mod-manifest-parity.json"
)
CASES = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_manifest_contract_matches_shared_fixture(case: dict[str, object]) -> None:
    if case["expectedValid"]:
        ModuleManifest.model_validate(case["manifest"])
        return

    with pytest.raises(ValidationError):
        ModuleManifest.model_validate(case["manifest"])
