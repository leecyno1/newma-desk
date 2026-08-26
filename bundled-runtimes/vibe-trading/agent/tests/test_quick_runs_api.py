"""Regression tests for the fixed-template quick backtest Interface."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import api_server
from src.api.quick_runs import (
    QuickRunCapacityError,
    QuickRunConflictError,
    QuickRunManager,
    QuickRunRequest,
)
from src.core.runner import RunResult, Runner


def _local_client() -> TestClient:
    return TestClient(api_server.app, client=("127.0.0.1", 50000))


def _remote_client() -> TestClient:
    return TestClient(api_server.app, client=("203.0.113.10", 50000))


def _request(**updates) -> dict:
    payload = {
        "template_id": "sma_crossover",
        "symbol": "AAPL.US",
        "start_date": "2024-01-01",
        "end_date": "2024-06-30",
        "params": {"fast_window": 5, "slow_window": 20},
    }
    payload.update(updates)
    return payload


class _ImmediateRunner:
    async def execute_async(self, _entry_script, _run_dir, **_kwargs) -> RunResult:
        return RunResult(
            success=True,
            exit_code=0,
            stdout="ok",
            stderr="",
            artifacts={},
        )


class _ResultRunner:
    def __init__(self, result: RunResult) -> None:
        self._result = result

    async def execute_async(self, _entry_script, _run_dir, **_kwargs) -> RunResult:
        return self._result


@pytest.fixture
def quick_api(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    manager = api_server.app.state.quick_run_manager
    manager._jobs.clear()
    monkeypatch.setattr(api_server, "RUNS_DIR", tmp_path)
    monkeypatch.setattr(manager, "_runner_factory", lambda: _ImmediateRunner())
    monkeypatch.setattr(manager, "_max_active", 1)
    yield manager, tmp_path
    manager._jobs.clear()


def test_post_quick_materializes_only_fixed_files(quick_api) -> None:
    _, runs_dir = quick_api
    response = _local_client().post("/runs/quick", json=_request())

    assert response.status_code == 202
    payload = response.json()
    assert payload["run_id"].startswith("run_")
    assert payload["status"] in {"queued", "running", "success"}

    run_dir = runs_dir / payload["run_id"]
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    source = (run_dir / "code" / "signal_engine.py").read_text(encoding="utf-8")
    design = json.loads((run_dir / "design_spec.json").read_text(encoding="utf-8"))

    assert config["source"] == "auto"
    assert config["engine"] == "daily"
    assert config["interval"] == "1D"
    assert config["codes"] == ["AAPL.US"]
    assert "FAST_WINDOW = 5" in source
    assert "SLOW_WINDOW = 20" in source
    assert config["execution_mode"] == "paper"
    assert config["execution_policy"] == "paper-only"
    assert design["schema_version"] == "newma-desk.strategy-experiment.v1"
    assert design["strategy_id"] == "vibe-trading.sma-crossover"
    assert design["template_version"] == "1.0.0"
    assert design["accepts_arbitrary_code"] is False
    assert set(path.name for path in (run_dir / "code").iterdir()) == {"signal_engine.py"}


@pytest.mark.parametrize(
    "payload",
    [
        _request(params={"python": 1}),
        _request(params={"fast_window": 20, "slow_window": 5}),
        _request(source="ccxt"),
        _request(symbol="../../etc/passwd"),
        _request(symbol="AAPL/../../etc/passwd"),
        _request(params={"fast_window": "5", "slow_window": 20}),
    ],
)
def test_post_quick_rejects_non_whitelisted_input(quick_api, payload: dict) -> None:
    response = _local_client().post("/runs/quick", json=payload)
    assert response.status_code == 422


def test_quick_route_requires_remote_auth(
    quick_api,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("API_AUTH_KEY", "secret")
    monkeypatch.setattr(api_server, "_API_KEY", "secret")

    response = _remote_client().post("/runs/quick", json=_request())
    assert response.status_code == 401


def test_status_endpoint_reads_persisted_terminal_run(quick_api) -> None:
    _, runs_dir = quick_api
    run_dir = runs_dir / "run_20240101_000000_deadbeef"
    run_dir.mkdir()
    (run_dir / "state.json").write_text(
        json.dumps(
            {
                "status": "success",
                "template_id": "buy_and_hold",
                "symbol": "AAPL.US",
            }
        ),
        encoding="utf-8",
    )

    response = _local_client().get(f"/runs/{run_dir.name}/status")
    assert response.status_code == 200
    assert response.json() == {
        "run_id": run_dir.name,
        "status": "success",
        "template_id": "buy_and_hold",
        "symbol": "AAPL.US",
        "created_at": None,
        "started_at": None,
        "finished_at": None,
        "reason": None,
    }


def test_manager_completes_and_persists_success(tmp_path: Path) -> None:
    async def scenario() -> None:
        manager = QuickRunManager(
            lambda: tmp_path,
            runner_factory=lambda: _ImmediateRunner(),
        )
        accepted = manager.create(QuickRunRequest.model_validate(_request()))
        job = manager._jobs[accepted.run_id]
        assert job.task is not None
        await job.task
        assert manager.status(accepted.run_id).status == "success"
        await asyncio.sleep(0)
        assert accepted.run_id not in manager._jobs

    asyncio.run(scenario())


def test_manager_persists_structured_timeout_result(tmp_path: Path) -> None:
    async def scenario() -> None:
        result = RunResult(
            success=False,
            exit_code=124,
            stdout="",
            stderr="backtest timed out",
            artifacts={},
            timed_out=True,
            reason="timeout",
        )
        manager = QuickRunManager(
            lambda: tmp_path,
            runner_factory=lambda: _ResultRunner(result),
        )
        accepted = manager.create(QuickRunRequest.model_validate(_request()))
        job = manager._jobs[accepted.run_id]
        assert job.task is not None
        await job.task

        status = manager.status(accepted.run_id)
        state = json.loads(
            (tmp_path / accepted.run_id / "state.json").read_text(encoding="utf-8")
        )
        assert status.status == "failed"
        assert status.reason == "timeout"
        assert state["exit_code"] == 124

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("runner_reason", "expected_reason"),
    [
        ("market data unavailable", "market data unavailable"),
        (None, "backtest process exited with code 2"),
    ],
)
def test_manager_persists_runner_failure_reason(
    tmp_path: Path,
    runner_reason: str | None,
    expected_reason: str,
) -> None:
    async def scenario() -> None:
        result = RunResult(
            success=False,
            exit_code=2,
            stdout="",
            stderr="market data unavailable",
            artifacts={},
            reason=runner_reason,
        )
        manager = QuickRunManager(
            lambda: tmp_path,
            runner_factory=lambda: _ResultRunner(result),
        )
        accepted = manager.create(QuickRunRequest.model_validate(_request()))
        job = manager._jobs[accepted.run_id]
        assert job.task is not None
        await job.task

        status = manager.status(accepted.run_id)
        state = json.loads(
            (tmp_path / accepted.run_id / "state.json").read_text(encoding="utf-8")
        )
        assert status.status == "failed"
        assert status.reason == expected_reason
        assert state["exit_code"] == 2

    asyncio.run(scenario())


def test_manager_cancel_marks_job_cancelled(tmp_path: Path) -> None:
    async def scenario() -> None:
        started = asyncio.Event()

        class BlockingRunner:
            async def execute_async(self, _entry_script, _run_dir, **_kwargs):
                started.set()
                await asyncio.Event().wait()

        manager = QuickRunManager(
            lambda: tmp_path,
            runner_factory=lambda: BlockingRunner(),
        )
        accepted = manager.create(
            QuickRunRequest.model_validate(
                _request(template_id="buy_and_hold", params={})
            )
        )
        await started.wait()
        cancelled = await manager.cancel(accepted.run_id)
        assert cancelled == manager.status(accepted.run_id)
        assert cancelled.status == "cancelled"
        await asyncio.sleep(0)
        assert accepted.run_id not in manager._jobs

    asyncio.run(scenario())


def test_manager_rejects_a_second_active_quick_run(tmp_path: Path) -> None:
    async def scenario() -> None:
        started = asyncio.Event()

        class BlockingRunner:
            async def execute_async(self, _entry_script, _run_dir, **_kwargs):
                started.set()
                await asyncio.Event().wait()

        manager = QuickRunManager(
            lambda: tmp_path,
            runner_factory=lambda: BlockingRunner(),
            max_active=1,
        )
        first = manager.create(QuickRunRequest.model_validate(_request()))
        await started.wait()

        with pytest.raises(QuickRunCapacityError):
            manager.create(QuickRunRequest.model_validate(_request(symbol="MSFT.US")))

        await manager.cancel(first.run_id)

    asyncio.run(scenario())


def test_manager_refuses_to_cancel_an_unowned_active_run(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_20240101_000000_deadbeef"
    run_dir.mkdir()
    (run_dir / "state.json").write_text(
        json.dumps({"run_id": run_dir.name, "status": "running"}),
        encoding="utf-8",
    )
    manager = QuickRunManager(lambda: tmp_path)

    with pytest.raises(QuickRunConflictError):
        asyncio.run(manager.cancel(run_dir.name))


@pytest.mark.skipif(os.name != "posix", reason="process liveness assertion is POSIX-only")
def test_async_runner_cancellation_terminates_child(tmp_path: Path) -> None:
    script = tmp_path / "sleeping_runner.py"
    pid_file = tmp_path / "child.pid"
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    script.write_text(
        "import os, pathlib, time\n"
        f"pathlib.Path({str(pid_file)!r}).write_text(str(os.getpid()))\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )

    async def scenario() -> int:
        runner = Runner(timeout=60)
        runner._pick_python_interpreter = lambda: sys.executable
        task = asyncio.create_task(
            runner.execute_async(script, run_dir, cwd=tmp_path)
        )
        for _ in range(100):
            if pid_file.exists():
                break
            await asyncio.sleep(0.01)
        assert pid_file.exists()
        pid = int(pid_file.read_text(encoding="utf-8"))
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return pid

    child_pid = asyncio.run(scenario())
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)
    assert (run_dir / "logs" / "runner_stderr.txt").exists()
