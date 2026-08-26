"""Lifecycle and resource bounds for backtest subprocess execution."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import time
from pathlib import Path

import pytest

import src.core.runner as runner_module
from src.core.runner import _BoundedLogCapture, _MAX_CAPTURE_BYTES, Runner


def _runner(timeout: float) -> Runner:
    runner = Runner(timeout=timeout)
    runner._pick_python_interpreter = lambda: sys.executable
    return runner


def _process_exists(process_id: int) -> bool:
    try:
        os.kill(process_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _wait_for_process_exit(process_id: int, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while _process_exists(process_id) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not _process_exists(process_id), f"process {process_id} survived runner cleanup"


async def _wait_for_file(path: Path, timeout: float = 3.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not path.exists() and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.01)
    assert path.exists(), f"timed out waiting for {path}"


def _write_process_tree_script(tmp_path: Path) -> tuple[Path, Path]:
    child_pid_file = tmp_path / "grandchild.pid"
    child_source = (
        "import os, signal, time\n"
        "from pathlib import Path\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        f"Path({str(child_pid_file)!r}).write_text(str(os.getpid()), encoding='utf-8')\n"
        "while True:\n"
        "    time.sleep(1)\n"
    )
    script = tmp_path / "process_tree.py"
    script.write_text(
        "import subprocess, sys, time\n"
        f"subprocess.Popen([sys.executable, '-c', {child_source!r}])\n"
        "while True:\n"
        "    time.sleep(1)\n",
        encoding="utf-8",
    )
    return script, child_pid_file


@pytest.mark.skipif(os.name != "posix", reason="process-group assertion is POSIX-only")
def test_async_cancellation_terminates_descendants(tmp_path: Path) -> None:
    script, child_pid_file = _write_process_tree_script(tmp_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    async def scenario() -> int:
        task = asyncio.create_task(
            _runner(timeout=60).execute_async(script, run_dir, cwd=tmp_path)
        )
        await _wait_for_file(child_pid_file)
        child_pid = int(child_pid_file.read_text(encoding="utf-8"))
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return child_pid

    child_pid = asyncio.run(scenario())
    _wait_for_process_exit(child_pid)
    persisted = json.loads(
        (run_dir / "logs" / "runner_result.json").read_text(encoding="utf-8")
    )
    assert persisted["success"] is False
    assert persisted["reason"] == "cancelled"


@pytest.mark.skipif(os.name != "posix", reason="process-group assertion is POSIX-only")
def test_async_timeout_returns_failure_and_terminates_descendants(tmp_path: Path) -> None:
    script, child_pid_file = _write_process_tree_script(tmp_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    result = asyncio.run(
        _runner(timeout=0.2).execute_async(script, run_dir, cwd=tmp_path)
    )

    assert result.success is False
    assert result.exit_code == 124
    assert result.timed_out is True
    assert result.reason == "timeout"
    assert "timed out after 0.2 seconds" in result.stderr
    child_pid = int(child_pid_file.read_text(encoding="utf-8"))
    _wait_for_process_exit(child_pid)
    persisted = json.loads(
        (run_dir / "logs" / "runner_result.json").read_text(encoding="utf-8")
    )
    assert persisted == {
        "success": False,
        "exit_code": 124,
        "timed_out": True,
        "reason": "timeout",
    }


def test_sync_timeout_returns_structured_failure(tmp_path: Path) -> None:
    script = tmp_path / "sleep.py"
    script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    result = _runner(timeout=0.05).execute(script, run_dir, cwd=tmp_path)

    assert result.success is False
    assert result.exit_code == 124
    assert result.timed_out is True
    assert result.reason == "timeout"
    assert "timed out after 0.05 seconds" in result.stderr


def test_returned_and_persisted_output_are_bounded(tmp_path: Path) -> None:
    script = tmp_path / "noisy.py"
    extra = 64 * 1024
    script.write_text(
        "import sys\n"
        f"sys.stdout.write('A' * {_MAX_CAPTURE_BYTES + extra})\n"
        f"sys.stderr.write('B' * {_MAX_CAPTURE_BYTES + extra})\n",
        encoding="utf-8",
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    result = _runner(timeout=10).execute(script, run_dir, cwd=tmp_path)

    assert result.success is True
    assert result.stdout.startswith("[runner output truncated:")
    assert result.stderr.startswith("[runner output truncated:")
    assert len(result.stdout.encode("utf-8")) < _MAX_CAPTURE_BYTES + 256
    assert len(result.stderr.encode("utf-8")) < _MAX_CAPTURE_BYTES + 256
    assert (run_dir / "logs" / "runner_stdout.txt").stat().st_size < _MAX_CAPTURE_BYTES + 256
    assert (run_dir / "logs" / "runner_stderr.txt").stat().st_size < _MAX_CAPTURE_BYTES + 256


def test_capture_smaller_than_truncation_marker_preserves_bounded_raw_tail(
    tmp_path: Path,
) -> None:
    capture_path = tmp_path / "tiny.log"
    capture = _BoundedLogCapture(capture_path, max_bytes=8)

    capture.write(b"012345")
    assert capture_path.stat().st_size <= 8
    capture.write(b"6789abcdef")
    assert capture_path.stat().st_size <= 8

    output = capture.finalize()

    assert output == "89abcdef"
    assert capture_path.read_bytes() == b"89abcdef"
    assert capture_path.stat().st_size == 8


def test_async_cancellation_while_draining_finalizes_and_leaves_no_tasks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = tmp_path / "finished_before_drain.py"
    script.write_text(
        "import sys\n"
        "sys.stdout.write('stdout-complete')\n"
        "sys.stderr.write('stderr-complete')\n",
        encoding="utf-8",
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    async def scenario() -> None:
        allow_drain = asyncio.Event()
        drain_wait_entered = asyncio.Event()
        real_drain = runner_module._drain_async_stream
        real_shield = runner_module.asyncio.shield
        shield_calls = 0

        async def delayed_drain(
            stream: asyncio.StreamReader,
            capture: _BoundedLogCapture,
        ) -> None:
            await allow_drain.wait()
            await real_drain(stream, capture)

        def observed_shield(awaitable: object) -> asyncio.Future[object]:
            nonlocal shield_calls
            shield_calls += 1
            shielded = real_shield(awaitable)
            if shield_calls == 3:
                drain_wait_entered.set()
            return shielded

        monkeypatch.setattr(runner_module, "_drain_async_stream", delayed_drain)
        monkeypatch.setattr(runner_module.asyncio, "shield", observed_shield)
        current_task = asyncio.current_task()
        assert current_task is not None
        baseline_tasks = set(asyncio.all_tasks())
        task = asyncio.create_task(
            _runner(timeout=10).execute_async(script, run_dir, cwd=tmp_path)
        )

        await asyncio.wait_for(drain_wait_entered.wait(), timeout=3)
        task.cancel()
        await asyncio.sleep(0)
        allow_drain.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=3)

        await asyncio.sleep(0)
        remaining_tasks = {
            pending
            for pending in asyncio.all_tasks()
            if pending is not current_task and pending not in baseline_tasks and not pending.done()
        }
        assert remaining_tasks == set()

    asyncio.run(scenario())

    logs_dir = run_dir / "logs"
    assert (logs_dir / "runner_stdout.txt").read_text(encoding="utf-8") == "stdout-complete"
    assert "stderr-complete" in (logs_dir / "runner_stderr.txt").read_text(encoding="utf-8")
    persisted = json.loads((logs_dir / "runner_result.json").read_text(encoding="utf-8"))
    assert persisted == {
        "success": False,
        "exit_code": 0,
        "timed_out": False,
        "reason": "cancelled",
    }


def test_log_files_are_bounded_while_sync_process_is_running(tmp_path: Path) -> None:
    ready_file = tmp_path / "noisy.ready"
    stop_file = tmp_path / "noisy.stop"
    script = tmp_path / "continuous_output.py"
    script.write_text(
        "import sys, time\n"
        "from pathlib import Path\n"
        f"ready = Path({str(ready_file)!r})\n"
        f"stop = Path({str(stop_file)!r})\n"
        "chunk = b'X' * 65536\n"
        "ready.write_text('ready', encoding='utf-8')\n"
        "while not stop.exists():\n"
        "    sys.stdout.buffer.write(chunk)\n"
        "    sys.stdout.buffer.flush()\n"
        "    sys.stderr.buffer.write(chunk)\n"
        "    sys.stderr.buffer.flush()\n"
        "time.sleep(0.05)\n",
        encoding="utf-8",
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    outcome: list[object] = []

    def run() -> None:
        outcome.append(_runner(timeout=10).execute(script, run_dir, cwd=tmp_path))

    runner_thread = threading.Thread(target=run, daemon=True)
    runner_thread.start()
    deadline = time.monotonic() + 5
    stdout_path = run_dir / "logs" / "runner_stdout.txt"
    stderr_path = run_dir / "logs" / "runner_stderr.txt"
    try:
        while (
            (not ready_file.exists() or not stdout_path.exists() or not stderr_path.exists())
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        assert ready_file.exists()

        while (
            (stdout_path.stat().st_size < _MAX_CAPTURE_BYTES
             or stderr_path.stat().st_size < _MAX_CAPTURE_BYTES)
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)

        for _ in range(20):
            assert stdout_path.stat().st_size <= _MAX_CAPTURE_BYTES
            assert stderr_path.stat().st_size <= _MAX_CAPTURE_BYTES
            time.sleep(0.01)
    finally:
        stop_file.touch()
        runner_thread.join(timeout=5)

    assert not runner_thread.is_alive()
    assert outcome and outcome[0].success is True
    assert stdout_path.read_text(encoding="utf-8").startswith("[runner output truncated:")
    assert stderr_path.read_text(encoding="utf-8").startswith("[runner output truncated:")


def test_log_files_are_bounded_while_async_process_is_running(tmp_path: Path) -> None:
    ready_file = tmp_path / "async-noisy.ready"
    stop_file = tmp_path / "async-noisy.stop"
    script = tmp_path / "continuous_async_output.py"
    script.write_text(
        "import sys\n"
        "from pathlib import Path\n"
        f"ready = Path({str(ready_file)!r})\n"
        f"stop = Path({str(stop_file)!r})\n"
        "chunk = b'Y' * 65536\n"
        "ready.write_text('ready', encoding='utf-8')\n"
        "while not stop.exists():\n"
        "    sys.stdout.buffer.write(chunk)\n"
        "    sys.stdout.buffer.flush()\n"
        "    sys.stderr.buffer.write(chunk)\n"
        "    sys.stderr.buffer.flush()\n",
        encoding="utf-8",
    )
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    async def scenario() -> None:
        task = asyncio.create_task(
            _runner(timeout=10).execute_async(script, run_dir, cwd=tmp_path)
        )
        stdout_path = run_dir / "logs" / "runner_stdout.txt"
        stderr_path = run_dir / "logs" / "runner_stderr.txt"
        try:
            await _wait_for_file(ready_file)
            deadline = asyncio.get_running_loop().time() + 5
            while (
                (not stdout_path.exists()
                 or not stderr_path.exists()
                 or stdout_path.stat().st_size < _MAX_CAPTURE_BYTES
                 or stderr_path.stat().st_size < _MAX_CAPTURE_BYTES)
                and asyncio.get_running_loop().time() < deadline
            ):
                await asyncio.sleep(0.01)

            for _ in range(20):
                assert stdout_path.stat().st_size <= _MAX_CAPTURE_BYTES
                assert stderr_path.stat().st_size <= _MAX_CAPTURE_BYTES
                await asyncio.sleep(0.01)
        finally:
            stop_file.touch()

        result = await asyncio.wait_for(task, timeout=5)
        assert result.success is True
        assert result.stdout.startswith("[runner output truncated:")
        assert result.stderr.startswith("[runner output truncated:")

    asyncio.run(scenario())
