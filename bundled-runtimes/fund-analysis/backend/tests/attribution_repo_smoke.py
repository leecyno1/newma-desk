import os
import sys
from decimal import Decimal

from sqlalchemy import create_engine, text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from repositories.attribution_repo import AttributionRepo


def main():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE performance_attributions (
                wind_code TEXT NOT NULL,
                benchmark_id TEXT NOT NULL,
                quarter TEXT NOT NULL,
                holding_quarter TEXT,
                status TEXT,
                total_return NUMERIC,
                benchmark_return NUMERIC,
                active_return NUMERIC,
                allocation_effect NUMERIC,
                selection_effect NUMERIC,
                interaction_effect NUMERIC,
                residual NUMERIC,
                evidence TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(wind_code, quarter)
            )
        """))
    repo = AttributionRepo(engine)
    bundle = {
        "fund": {"wind_code": "TEST.OF"},
        "quarter": "2026Q2",
        "holding_snapshot_quarter": "2026Q1",
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
    history = repo.list_history("TEST.OF")
    assert len(history) == 1, history
    assert history[0]["active_return"] == 0.02, history
    assert history[0]["holding_quarter"] == "2026Q1", history
    assert repo._serialize({"active": Decimal("0.0200")}) == {"active": 0.02}
    print("OK on-demand attribution history is persisted by fund and quarter")


if __name__ == "__main__":
    main()
