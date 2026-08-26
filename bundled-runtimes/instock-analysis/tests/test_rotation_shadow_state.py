from instock.core.rotation.rotation_shadow_state import RotationShadowState


def shadow_state(day, *, selected_code="510300", lifecycle="bootstrap"):
    return {
        "schema_version": "instock.rotation.shadow.v1",
        "strategy_id": "rotation-stateful-ensemble-v1",
        "as_of": day,
        "lifecycle_state": lifecycle,
        "signal_id": f"rotation-stateful-ensemble-v1:{day}",
        "models": [{
            "id": "balanced-w60",
            "selected_code": selected_code,
            "code": selected_code,
        }],
    }


def test_rotation_shadow_state_is_forward_only_and_survives_restart(tmp_path):
    path = tmp_path / "rotation-shadow.sqlite3"
    ledger = RotationShadowState(str(path))

    assert ledger.record("510300", shadow_state("2026-08-10")) is True
    assert ledger.record(
        "510300", shadow_state("2026-08-10", selected_code="159915")
    ) is False
    assert ledger.record("510300", shadow_state("2026-08-09")) is False
    assert ledger.record(
        "510300", shadow_state("2026-08-20", lifecycle="rebalanced")
    ) is True
    assert ledger.record("510500", shadow_state("2026-08-15")) is True

    restarted = RotationShadowState(str(path))
    assert restarted.latest("510300")["as_of"] == "2026-08-20"
    assert restarted.latest("510300")["benchmark"] == "510300"
    assert [row["as_of"] for row in restarted.recent(
        benchmark="510300", limit=5
    )] == ["2026-08-20", "2026-08-10"]
    assert restarted.stats() == {
        "storage": "sqlite",
        "volatile": False,
        "cleared_on_restart": False,
        "entries": 3,
        "benchmarks": 2,
        "signal_entries": 3,
        "latest_as_of": "2026-08-20",
    }


def test_rotation_shadow_state_rejects_incomplete_payload(tmp_path):
    ledger = RotationShadowState(str(tmp_path / "rotation-shadow.sqlite3"))

    assert ledger.record("510300", {}) is False
    assert ledger.record("510300", {
        "strategy_id": "rotation-stateful-ensemble-v1",
        "as_of": "2026-08-10",
        "models": [],
    }) is False
    assert ledger.stats()["entries"] == 0
