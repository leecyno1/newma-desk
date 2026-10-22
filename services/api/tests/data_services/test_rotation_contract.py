import json
from pathlib import Path

import pytest

from vibe_visualization_api.schema_validation import JsonContractError, validate_json_contract


ROOT = Path(__file__).resolve().parents[4]
DESCRIPTORS = [
    "integrations/instock-analysis/data-service.json",
    "bundled-runtimes/instock-analysis/integrations/newma-desk/data-service.json",
    "bundled-runtimes/instock-analysis/integrations/vibedesk/data-service.json",
]


@pytest.mark.parametrize("path", DESCRIPTORS)
def test_rotation_breadth_allows_missing_values_but_preserves_numeric_limits(path):
    schema = json.loads((ROOT / path).read_text())["capabilities"]["analysis.rotation"]["outputSchema"]
    breadth_schema = schema["properties"]["data"]["properties"]["market_breadth"]
    base = {"state": "unavailable", "breadth": "unknown", "up": None,
            "down": None, "flat": None, "up_ratio": None}
    validate_json_contract(breadth_schema, base, direction="output")
    validate_json_contract(breadth_schema, {**base, "up": 1981, "down": 3364, "flat": 223}, direction="output")
    validate_json_contract(breadth_schema, {**base, "state": "available", "up": 0,
                           "down": 10, "flat": 0, "up_ratio": 0}, direction="output")
    for field, invalid in (("up", -1), ("down", "unknown"), ("flat", 1.5), ("up_ratio", 101)):
        with pytest.raises(JsonContractError):
            validate_json_contract(breadth_schema, {**base, field: invalid}, direction="output")
