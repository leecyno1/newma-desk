from __future__ import annotations

import argparse

import pytest
from pydantic import ValidationError

from src.api import alpha_routes
from src.factors import cli_handlers


def test_api_strict_options_are_explicit() -> None:
    request = alpha_routes.BenchRequest(
        zoo="alpha101",
        universe="sp500",
        period="2020-2025",
        strict=True,
        oos_split="2023-01-01",
        random_seeds=7,
    )
    assert request.strict is True
    assert request.oos_split == "2023-01-01"
    assert request.random_seeds == 7

    with pytest.raises(ValidationError, match="require strict=true"):
        alpha_routes.BenchRequest(
            zoo="alpha101",
            universe="sp500",
            period="2020-2025",
            strict=False,
            oos_split="2023-01-01",
        )


def test_strict_wire_summary_keeps_gate_and_universe_disclosure() -> None:
    result = alpha_routes._result_for_wire(
        {
            "confirmed_alive": 2,
            "train_only": 1,
            "reversed_strict": 3,
            "noise": 4,
            "random_control": True,
            "n_random_seeds": 5,
            "oos_split": "2023-01-01",
            "n_skipped": 6,
            "meta": {"degraded": True, "constituent_source": "hand-picked fallback"},
            "rows": [{"id": "must-not-leak"}],
        }
    )

    assert result["confirmed_alive"] == 2
    assert result["train_only"] == 1
    assert result["random_control"] is True
    assert result["skipped"] == 6
    assert result["meta"]["degraded"] is True
    assert "rows" not in result


def test_cli_rejects_strict_only_flags_without_strict(capsys) -> None:
    args = argparse.Namespace(
        zoo="alpha101",
        universe="sp500",
        period="2020-2025",
        top=20,
        yes=True,
        strict=False,
        oos_split="2023-01-01",
        random_seeds=5,
        verbose=False,
    )

    assert cli_handlers.cmd_alpha_bench(args) == 1
    assert "require --strict" in capsys.readouterr().err


def test_multi_zoo_strict_summary_preserves_counts_and_metadata(monkeypatch) -> None:
    class Handle:
        zoo = "z1"

    class Registry:
        def get(self, alpha_id):
            handle = Handle()
            handle.zoo = alpha_id.split("_")[0]
            return handle

        def list(self, *, zoo=None):
            return [f"{zoo}_alpha"] if zoo else ["z1_alpha", "z2_alpha"]

    def run_bench(*, zoo, **kwargs):
        count = 1 if zoo == "z1" else 2
        return {
            "status": "ok",
            "rows": [{"id": f"{zoo}_alpha", "_category": "confirmed_alive"}],
            "skipped": [],
            "alive": count,
            "confirmed_alive": count,
            "train_only": count + 1,
            "reversed_strict": 0,
            "noise": 3,
            "random_control": True,
            "n_random_seeds": 5,
            "oos_split": "2023-01-01",
            "meta": {"universe": "sp500", "degraded": False},
        }

    monkeypatch.setattr(cli_handlers, "_console", None)
    result = cli_handlers._run_all_zoos_with_progress(
        target_ids=["z1_alpha", "z2_alpha"],
        universe="sp500",
        period="2020-2025",
        top=20,
        start_ts=0.0,
        reg=Registry(),
        run_bench=run_bench,
    )

    assert result["confirmed_alive"] == 3
    assert result["train_only"] == 5
    assert result["noise"] == 6
    assert result["random_control"] is True
    assert result["meta"] == {"universe": "sp500", "degraded": False}
