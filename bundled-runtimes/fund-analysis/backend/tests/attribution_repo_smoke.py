import os
import sys
from decimal import Decimal

from sqlalchemy import text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from database import get_engine, init_database
from repositories.attribution_repo import AttributionRepo

WIND_CODE = "TEST.ATTRIB.SMOKE"
QUARTER = "2099Q4"


def _cleanup(engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM performance_attributions WHERE wind_code = :code"), {"code": WIND_CODE})


def main():
    init_database()
    engine = get_engine()
    _cleanup(engine)
    try:
        repo = AttributionRepo(engine)
        bundle = {
            "fund": {"wind_code": WIND_CODE},
            "quarter": QUARTER,
            "holding_snapshot_quarter": "2099Q3",
            "benchmark": "000300.SH",
            "status": "partial_evidence",
            "brinson": {
                "status": "partial_evidence",
                "returns": {"fund": 0.08, "benchmark": 0.06, "active": 0.02},
                "effects": [
                    {"name": "allocation", "value": 0.01},
                    {"name": "selection", "value": 0.005},
                    {"name": "interaction", "value": 0.001},
                    {"name": "residual", "value": 0.004},
                ],
            },
        }
        assert repo.save_bundle(bundle)
        history = repo.list_history(WIND_CODE)
        assert len(history) == 1, history
        assert history[0]["active_return"] == 0.02, history
        assert history[0]["holding_quarter"] == "2099Q3", history
        assert repo._serialize({"active": Decimal("0.0200")}) == {"active": 0.02}
        print("OK on-demand attribution history is persisted by fund and quarter")
    finally:
        _cleanup(engine)


if __name__ == "__main__":
    main()
