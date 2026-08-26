"""Native Strategy Ledger projections stay paper-only and reproducible."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from backtest.run_card import write_run_card
from backtest.strategy_ledger import SCHEMA_VERSION, build_strategy_ledger


def _prepare_quick_run(run_dir: Path) -> dict:
    config = {
        "source": "auto",
        "codes": ["AAPL"],
        "start_date": "2025-01-01",
        "end_date": "2025-12-31",
        "interval": "1D",
        "initial_cash": 100_000,
        "commission": 0.001,
        "engine": "daily",
        "quick_template_id": "sma_crossover",
        "execution_mode": "paper",
        "execution_policy": "paper-only",
    }
    (run_dir / "code").mkdir(parents=True)
    (run_dir / "config.json").write_text(json.dumps(config), encoding="utf-8")
    (run_dir / "code" / "signal_engine.py").write_text("class SignalEngine: pass\n", encoding="utf-8")
    (run_dir / "state.json").write_text(
        json.dumps({"status": "running", "created_at": "2026-08-01T00:00:00Z"}),
        encoding="utf-8",
    )
    (run_dir / "design_spec.json").write_text(
        json.dumps(
            {
                "strategy_id": "vibe-trading.sma-crossover",
                "name": "SMA Crossover",
                "template_id": "sma_crossover",
                "template_version": "1.0.0",
                "parameters": {"fast_window": 10, "slow_window": 40},
                "accepts_arbitrary_code": False,
            }
        ),
        encoding="utf-8",
    )
    return config


def test_run_card_materializes_native_strategy_ledger(tmp_path: Path) -> None:
    config = _prepare_quick_run(tmp_path)
    metrics = {
        "final_value": 112_000,
        "total_return": 0.12,
        "annual_return": 0.118,
        "max_drawdown": -0.08,
        "sharpe": 1.4,
        "sortino": 1.9,
        "win_rate": 0.55,
        "trade_count": 40,
        "benchmark_return": 0.09,
        "excess_return": 0.03,
    }

    write_run_card(
        tmp_path,
        config,
        metrics,
        data_sources=["sina"],
        strategy_path=tmp_path / "code" / "signal_engine.py",
    )

    ledger = json.loads((tmp_path / "strategy_ledger.json").read_text(encoding="utf-8"))
    assert ledger["schema_version"] == SCHEMA_VERSION
    assert ledger["mode"] == "paper-only"
    assert ledger["execution_mode"] == "paper"
    assert ledger["status"] == "completed"
    assert ledger["strategy"]["id"] == "vibe-trading.sma-crossover"
    assert ledger["strategy"]["version"].startswith("1.0.0+")
    assert ledger["experiment"]["revision"]
    assert ledger["dataset"] == {
        "symbols": ["AAPL"],
        "market": "US",
        "start_date": "2025-01-01",
        "end_date": "2025-12-31",
        "timeframe": "1D",
        "source": "newma-desk",
        "data_sources": ["sina"],
    }
    assert ledger["metrics"]["annualized_return"] == 0.118
    assert ledger["metrics"]["trade_count"] == 40
    assert {item["kind"] for item in ledger["attribution"]} == {
        "return",
        "risk",
        "cost",
        "activity",
    }
    assert ledger["quality"] == {"level": "complete", "flags": []}
    assert ledger["provenance"]["runtime"] == "vibe-trading-native"


def test_strategy_ledger_projects_risk_rebalances_and_constraints(tmp_path: Path) -> None:
    config = _prepare_quick_run(tmp_path)
    config.update(
        {
            "optimizer": "risk_parity",
            "constraints": [{"type": "max_weight", "cap": 0.5}],
        }
    )
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "risk_xray.json").write_text(
        json.dumps(
            {
                "concentration": {"hhi": 0.4, "effective_n": 2.5},
                "volatility": {"annualized_vol": 0.18},
                "drawdown": {"max_drawdown": -0.12},
                "tail_risk": {"var_95": 0.025, "expected_shortfall_95": 0.04},
            }
        ),
        encoding="utf-8",
    )
    (artifacts / "rebalance_notes.json").write_text(
        json.dumps(
            {
                "summary": {
                    "rebalance_count": 3,
                    "turnover_total": 0.8,
                    "turnover_mean": 0.8 / 3,
                    "turnover_max": 0.4,
                    "largest_rebalance_date": "2025-06-01",
                }
            }
        ),
        encoding="utf-8",
    )

    ledger = build_strategy_ledger(
        tmp_path,
        config=config,
        metrics={
            "total_return": 0.1,
            "max_drawdown": -0.12,
            "sharpe": 1.2,
            "trade_count": 30,
            "avg_turnover": 0.03,
            "total_turnover": 0.6,
            "risk_xray_avg_invested": 0.9,
        },
        run_card={},
        state={"status": "success"},
    )

    assert ledger["metrics"]["turnover"] == 0.03
    assert ledger["metrics"]["total_turnover"] == 0.6
    assert ledger["risk"]["hhi"] == 0.4
    assert ledger["risk"]["artifact"]["path"] == "artifacts/risk_xray.json"
    assert ledger["rebalances"]["count"] == 3
    assert ledger["rebalances"]["target_turnover_total"] == 0.8
    assert ledger["constraints"] == {
        "configured_count": 1,
        "types": ["max_weight"],
        "group_count": 0,
        "optimizer": "risk_parity",
        "status": "applied",
    }


def test_strategy_ledger_preserves_valid_zero_diagnostics(tmp_path: Path) -> None:
    config = _prepare_quick_run(tmp_path)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "risk_xray.json").write_text(
        json.dumps(
            {
                "concentration": {"hhi": 0.0, "effective_n": 0.0},
                "volatility": {"annualized_vol": 0.0},
                "drawdown": {"max_drawdown": 0.0},
                "tail_risk": {"var_95": 0.0, "expected_shortfall_95": 0.0},
            }
        ),
        encoding="utf-8",
    )
    (artifacts / "rebalance_notes.json").write_text(
        json.dumps(
            {
                "summary": {
                    "rebalance_count": 0,
                    "turnover_total": 0.0,
                    "turnover_mean": 0.0,
                    "turnover_max": 0.0,
                    "largest_rebalance_date": None,
                }
            }
        ),
        encoding="utf-8",
    )

    ledger = build_strategy_ledger(
        tmp_path,
        config=config,
        metrics={"total_return": 0.0, "max_drawdown": 0.0, "sharpe": 0.0},
        run_card={},
        state={"status": "success"},
    )

    assert ledger["risk"]["hhi"] == 0.0
    assert ledger["risk"]["annualized_volatility"] == 0.0
    assert ledger["risk"]["max_drawdown"] == 0.0
    assert ledger["rebalances"]["count"] == 0
    assert ledger["rebalances"]["target_turnover_total"] == 0.0


def test_strategy_ledger_marks_zero_cost_and_low_sample_without_inventing_metrics(tmp_path: Path) -> None:
    config = _prepare_quick_run(tmp_path)
    config["commission"] = 0
    ledger = build_strategy_ledger(
        tmp_path,
        config=config,
        state={"status": "success"},
        metrics={"total_return": 0.04, "sharpe": 0.8, "max_drawdown": -0.12, "trade_count": 3},
        run_card={"data_sources": ["sina"]},
    )

    assert ledger["metrics"]["volatility"] is None
    assert ledger["metrics"]["fees"] is None
    assert ledger["cost_model"] == {
        "commission_rate": 0.0,
        "realized_fees_available": False,
    }
    assert ledger["quality"]["level"] == "complete"
    assert ledger["quality"]["flags"] == ["low_trade_sample", "zero_cost_assumption"]


def test_strategy_ledger_uses_30_trades_as_the_minimum_sample_boundary(tmp_path: Path) -> None:
    config = _prepare_quick_run(tmp_path)
    below_minimum = build_strategy_ledger(
        tmp_path,
        config=config,
        state={"status": "success"},
        metrics={"total_return": 0.04, "sharpe": 0.8, "max_drawdown": -0.12, "trade_count": 29},
        run_card={"data_sources": ["sina"]},
    )
    at_minimum = build_strategy_ledger(
        tmp_path,
        config=config,
        state={"status": "success"},
        metrics={"total_return": 0.04, "sharpe": 0.8, "max_drawdown": -0.12, "trade_count": 30},
        run_card={"data_sources": ["sina"]},
    )

    assert "low_trade_sample" in below_minimum["quality"]["flags"]
    assert "low_trade_sample" not in at_minimum["quality"]["flags"]


def test_run_api_response_exposes_fresh_strategy_ledger_projection(tmp_path: Path) -> None:
    import api_server

    config = _prepare_quick_run(tmp_path)
    (tmp_path / "state.json").write_text('{"status": "success"}\n', encoding="utf-8")
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir()
    (artifacts / "metrics.csv").write_text(
        "final_value,total_return,annual_return,max_drawdown,sharpe,win_rate,trade_count\n"
        "110000,0.1,0.09,-0.07,1.2,0.5,30\n",
        encoding="utf-8",
    )
    write_run_card(
        tmp_path,
        config,
        {
            "final_value": 110_000,
            "total_return": 0.1,
            "annual_return": 0.09,
            "max_drawdown": -0.07,
            "sharpe": 1.2,
            "win_rate": 0.5,
            "trade_count": 30,
        },
        data_sources=["sina"],
        strategy_path=tmp_path / "code" / "signal_engine.py",
    )

    response = api_server._build_response_from_run_dir(tmp_path, elapsed=0.0)

    assert response.strategy_ledger["schema_version"] == SCHEMA_VERSION
    assert response.strategy_ledger["status"] == "completed"
    assert response.strategy_ledger["metrics"]["max_drawdown"] == -0.07


def test_run_list_includes_strategy_ledger_summary(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import api_server

    run_dir = tmp_path / "run_20260801_010203_abc12345"
    run_dir.mkdir()
    config = _prepare_quick_run(run_dir)
    (run_dir / "state.json").write_text('{"status": "success"}\n', encoding="utf-8")
    artifacts = run_dir / "artifacts"
    artifacts.mkdir()
    (artifacts / "metrics.csv").write_text(
        "final_value,total_return,annual_return,max_drawdown,sharpe,win_rate,trade_count\n"
        "110000,0.1,0.09,-0.07,1.2,0.5,30\n",
        encoding="utf-8",
    )
    write_run_card(
        run_dir,
        config,
        {
            "final_value": 110_000,
            "total_return": 0.1,
            "annual_return": 0.09,
            "max_drawdown": -0.07,
            "sharpe": 1.2,
            "win_rate": 0.5,
            "trade_count": 30,
        },
        data_sources=["sina"],
        strategy_path=run_dir / "code" / "signal_engine.py",
    )
    monkeypatch.setattr(api_server, "RUNS_DIR", tmp_path)

    response = TestClient(api_server.app, client=("127.0.0.1", 50000)).get("/runs?limit=5")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["run_id"] == run_dir.name
    assert payload[0]["strategy_ledger"]["schema_version"] == SCHEMA_VERSION
    assert payload[0]["strategy_ledger"]["strategy"]["version"].startswith("1.0.0+")
    assert payload[0]["strategy_ledger"]["metrics"]["max_drawdown"] == -0.07
