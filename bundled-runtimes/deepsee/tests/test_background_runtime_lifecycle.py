from __future__ import annotations

import asyncio
import importlib
import os
import sys
from dataclasses import FrozenInstanceError

import pytest
from fastapi import FastAPI

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app import background


def _fresh_bg_state(name: str) -> dict:
    background.BACKGROUND_RUNTIME.pop(name, None)
    return background._bg_state(name)


def _disable_default_background_specs(monkeypatch) -> None:
    monkeypatch.setitem(background.settings.__dict__, "SYNC_INTERVAL_SECONDS", 0)
    monkeypatch.setitem(background.settings.__dict__, "LANGBOT_ADAPTER_LOG_DIR", "")
    monkeypatch.setitem(background.settings.__dict__, "NEWSNOW_REFRESH_INTERVAL_SECONDS", 0)
    monkeypatch.setitem(background.settings.__dict__, "NEWS_SNAPSHOT_INTERVAL_SECONDS", 0)
    monkeypatch.setitem(background.settings.__dict__, "MEDIA_COLLECTOR_DAILY_ENABLED", False)
    monkeypatch.setitem(background.settings.__dict__, "SUMMARY_OVERLAY_INTERVAL_SECONDS", 0)
    monkeypatch.setitem(background.settings.__dict__, "AGGREGATION_RETENTION_INTERVAL_SECONDS", 0)
    monkeypatch.setitem(background.settings.__dict__, "MEDIA_CACHE_CLEANUP_ENABLED", False)
    monkeypatch.setitem(background.settings.__dict__, "MEDIA_CACHE_CLEANUP_INTERVAL_SECONDS", 0)
    monkeypatch.setattr("app.services.llm_client.load_ai_config", lambda: {})


def _load_main_without_db_init(monkeypatch):
    from app import db as app_db

    real_init_db = app_db.init_db
    monkeypatch.setattr(app_db, "init_db", lambda: None)
    if "app.main" in sys.modules:
        return sys.modules["app.main"]

    main = importlib.import_module("app.main")
    main.init_db = real_init_db
    return main


def _controlled_runtime():
    started = asyncio.Event()
    finished = asyncio.Event()
    starts: list[str] = []

    async def controlled_loop() -> None:
        starts.append("controlled")
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            finished.set()

    runtime = background.BackgroundRuntime(
        spec_provider=lambda: [
            background.BackgroundLoopSpec(
                name="controlled",
                enabled=True,
                runner=controlled_loop,
            )
        ]
    )
    return runtime, started, finished, starts


def test_runtime_start_is_idempotent_and_attaches_named_task_to_app():
    async def scenario() -> None:
        runtime, started, _finished, starts = _controlled_runtime()
        app = FastAPI()
        try:
            returned = await runtime.start(app)
            await started.wait()
            first = runtime.tasks["controlled"]

            returned_again = await runtime.start(app)
            await asyncio.sleep(0)

            assert returned is runtime
            assert returned_again is runtime
            assert runtime.tasks["controlled"] is first
            assert starts == ["controlled"]
            assert app.state.background_runtime is runtime
            assert first.get_name() == "deepsee-background:controlled"
        finally:
            await runtime.shutdown()

    asyncio.run(scenario())


def test_runtime_concurrent_start_constructs_only_one_runner_and_handle():
    async def scenario() -> None:
        constructed = 0
        started = asyncio.Event()

        async def controlled_loop() -> None:
            started.set()
            await asyncio.Event().wait()

        def runner_factory():
            nonlocal constructed
            constructed += 1
            return controlled_loop()

        runtime = background.BackgroundRuntime(
            spec_provider=lambda: [
                background.BackgroundLoopSpec(
                    name="concurrent_controlled",
                    enabled=True,
                    runner=runner_factory,
                )
            ]
        )
        try:
            first, second = await asyncio.gather(runtime.start(), runtime.start())
            await started.wait()

            assert first is runtime
            assert second is runtime
            assert constructed == 1
            assert len(runtime.tasks) == 1
            assert runtime.tasks["concurrent_controlled"].get_name() == (
                "deepsee-background:concurrent_controlled"
            )
        finally:
            await runtime.shutdown()

    asyncio.run(scenario())


@pytest.mark.parametrize("failure_kind", ["factory_raises", "invalid_awaitable"])
def test_runtime_start_cleans_new_tasks_when_later_spec_creation_fails(failure_kind):
    async def scenario() -> None:
        async def first_loop() -> None:
            await asyncio.Event().wait()

        def failing_factory():
            if failure_kind == "factory_raises":
                raise RuntimeError("second factory failed")
            return None

        runtime = background.BackgroundRuntime(
            spec_provider=lambda: [
                background.BackgroundLoopSpec("partial_first", True, first_loop),
                background.BackgroundLoopSpec("partial_second", True, failing_factory),
            ]
        )
        background._bg_state("partial_first")["running"] = True

        expected_error = RuntimeError if failure_kind == "factory_raises" else TypeError
        with pytest.raises(expected_error):
            await runtime.start()
        await asyncio.sleep(0)

        assert runtime.tasks == {}
        assert background._bg_state("partial_first")["running"] is False

    asyncio.run(scenario())


def test_background_loop_spec_is_frozen():
    async def runner() -> None:
        return None

    spec = background.BackgroundLoopSpec(name="frozen", enabled=True, runner=runner)

    with pytest.raises(FrozenInstanceError):
        spec.enabled = False


def test_runtime_tasks_returns_a_registry_copy():
    async def scenario() -> None:
        runtime, started, _finished, _starts = _controlled_runtime()
        try:
            await runtime.start()
            await started.wait()

            copied_tasks = runtime.tasks
            copied_tasks.clear()

            assert "controlled" in runtime.tasks
        finally:
            await runtime.shutdown()

    asyncio.run(scenario())


def test_runtime_rejects_foreign_loop_while_pending_and_reuses_after_clean_shutdown():
    async def controlled_loop() -> None:
        await asyncio.Event().wait()

    runtime = background.BackgroundRuntime(
        spec_provider=lambda: [
            background.BackgroundLoopSpec("loop_owned", True, controlled_loop)
        ]
    )
    first_loop = asyncio.new_event_loop()
    second_loop = asyncio.new_event_loop()
    try:
        first_loop.run_until_complete(runtime.start())
        first_loop.run_until_complete(asyncio.sleep(0))
        first = runtime.tasks["loop_owned"]

        with pytest.raises(RuntimeError, match="another event loop"):
            second_loop.run_until_complete(runtime.start())
        with pytest.raises(RuntimeError, match="another event loop"):
            second_loop.run_until_complete(runtime.shutdown())

        assert first.done() is False
        assert first.cancelled() is False

        first_loop.run_until_complete(runtime.shutdown())
        assert runtime.tasks == {}

        second_loop.run_until_complete(runtime.start())
        second_loop.run_until_complete(asyncio.sleep(0))
        second = runtime.tasks["loop_owned"]
        assert second is not first
        assert second.get_loop() is second_loop
        second_loop.run_until_complete(runtime.shutdown())
    finally:
        if runtime.tasks:
            owner_loop = next(iter(runtime.tasks.values())).get_loop()
            if not owner_loop.is_closed():
                owner_loop.run_until_complete(runtime.shutdown())
        first_loop.close()
        second_loop.close()


def test_runtime_does_not_call_or_schedule_disabled_runner():
    async def scenario() -> None:
        constructed = 0

        async def disabled_loop() -> None:
            return None

        def runner_factory():
            nonlocal constructed
            constructed += 1
            return disabled_loop()

        runtime = background.BackgroundRuntime(
            spec_provider=lambda: [
                background.BackgroundLoopSpec(
                    name="disabled_controlled",
                    enabled=False,
                    runner=runner_factory,
                )
            ]
        )

        await runtime.start()
        await asyncio.sleep(0)

        assert runtime.tasks == {}
        assert constructed == 0
        assert background._bg_state("disabled_controlled")["enabled"] is False

    asyncio.run(scenario())


def test_runtime_start_updates_enabled_state_for_every_spec():
    async def scenario() -> None:
        enabled_started = asyncio.Event()
        disabled_constructed = 0

        async def enabled_loop() -> None:
            enabled_started.set()
            await asyncio.Event().wait()

        async def disabled_loop() -> None:
            return None

        def disabled_factory():
            nonlocal disabled_constructed
            disabled_constructed += 1
            return disabled_loop()

        background._bg_state("enabled_state_true")["enabled"] = False
        background._bg_state("enabled_state_false")["enabled"] = True
        runtime = background.BackgroundRuntime(
            spec_provider=lambda: [
                background.BackgroundLoopSpec(
                    name="enabled_state_true",
                    enabled=True,
                    runner=enabled_loop,
                ),
                background.BackgroundLoopSpec(
                    name="enabled_state_false",
                    enabled=False,
                    runner=disabled_factory,
                ),
            ]
        )
        try:
            await runtime.start()
            await enabled_started.wait()

            assert background._bg_state("enabled_state_true")["enabled"] is True
            assert background._bg_state("enabled_state_false")["enabled"] is False
            assert set(runtime.tasks) == {"enabled_state_true"}
            assert disabled_constructed == 0
        finally:
            await runtime.shutdown()

    asyncio.run(scenario())


def test_runtime_shutdown_cancels_awaits_clears_and_is_repeatable():
    async def scenario() -> None:
        runtime, started, finished, _starts = _controlled_runtime()
        await runtime.start()
        await started.wait()
        state = background._bg_state("controlled")
        state["running"] = True
        state["failures"] = 7
        failures_before = state["failures"]

        await runtime.shutdown()

        assert finished.is_set()
        assert runtime.tasks == {}
        assert background._bg_state("controlled")["running"] is False
        assert background._bg_state("controlled")["failures"] == failures_before

        await runtime.shutdown()
        assert runtime.tasks == {}

    asyncio.run(scenario())


def test_runtime_shutdown_drains_all_owned_tasks_and_preserves_failures():
    async def scenario() -> None:
        first_started = asyncio.Event()
        second_started = asyncio.Event()
        first_finished = asyncio.Event()
        second_finished = asyncio.Event()

        async def first_loop() -> None:
            first_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                first_finished.set()

        async def second_loop() -> None:
            second_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                second_finished.set()

        runtime = background.BackgroundRuntime(
            spec_provider=lambda: [
                background.BackgroundLoopSpec("shutdown_first", True, first_loop),
                background.BackgroundLoopSpec("shutdown_second", True, second_loop),
            ]
        )
        await runtime.start()
        await asyncio.gather(first_started.wait(), second_started.wait())
        assert set(runtime.tasks) == {"shutdown_first", "shutdown_second"}

        first_state = background._bg_state("shutdown_first")
        second_state = background._bg_state("shutdown_second")
        first_state["running"] = True
        second_state["running"] = True
        first_state["failures"] = 13
        second_state["failures"] = 17

        await runtime.shutdown()

        assert first_finished.is_set()
        assert second_finished.is_set()
        assert runtime.tasks == {}
        assert first_state["running"] is False
        assert second_state["running"] is False
        assert first_state["failures"] == 13
        assert second_state["failures"] == 17

    asyncio.run(scenario())


def test_start_waits_for_shutdown_cleanup_then_creates_a_new_task():
    async def scenario() -> None:
        first_started = asyncio.Event()
        cancellation_seen = asyncio.Event()
        release_cleanup = asyncio.Event()
        restarted = asyncio.Event()
        runs = 0

        async def controlled_loop() -> None:
            nonlocal runs
            runs += 1
            if runs == 1:
                first_started.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError:
                    cancellation_seen.set()
                    await release_cleanup.wait()
                    raise
            restarted.set()
            await asyncio.Event().wait()

        runtime = background.BackgroundRuntime(
            spec_provider=lambda: [
                background.BackgroundLoopSpec("serialized", True, controlled_loop)
            ]
        )
        await runtime.start()
        await first_started.wait()
        first = runtime.tasks["serialized"]

        shutdown_task = asyncio.create_task(runtime.shutdown())
        await cancellation_seen.wait()
        restart_task = asyncio.create_task(runtime.start())
        await asyncio.sleep(0)

        assert restart_task.done() is False

        release_cleanup.set()
        await shutdown_task
        returned = await restart_task
        await restarted.wait()

        try:
            assert returned is runtime
            assert runtime.tasks["serialized"] is not first
            assert runs == 2
        finally:
            await runtime.shutdown()

    asyncio.run(scenario())


def test_done_callback_automatically_removes_completed_handle_and_clears_running():
    async def scenario() -> None:
        release = asyncio.Event()

        async def run_to_completion() -> None:
            await release.wait()

        runtime = background.BackgroundRuntime(
            spec_provider=lambda: [
                background.BackgroundLoopSpec(
                    name="auto_cleanup",
                    enabled=True,
                    runner=run_to_completion,
                )
            ]
        )
        await runtime.start()
        task = runtime.tasks["auto_cleanup"]
        background._bg_state("auto_cleanup")["running"] = True

        release.set()
        await task
        await asyncio.sleep(0)

        assert "auto_cleanup" not in runtime.tasks
        assert background._bg_state("auto_cleanup")["running"] is False

    asyncio.run(scenario())


def test_unexpected_task_exit_updates_runtime_error_health():
    async def scenario() -> None:
        loop_name = "raw_crash_health"

        async def crash() -> None:
            background._bg_mark_start(loop_name)
            raise RuntimeError("raw background crash")

        runtime = background.BackgroundRuntime(
            spec_provider=lambda: [
                background.BackgroundLoopSpec(
                    name=loop_name,
                    enabled=True,
                    runner=crash,
                )
            ]
        )
        state = _fresh_bg_state(loop_name)

        await runtime.start()
        task = runtime.tasks[loop_name]
        with pytest.raises(RuntimeError, match="raw background crash"):
            await task
        await asyncio.sleep(0)

        snapshot = background.get_background_runtime_snapshot()[loop_name]
        assert state["failures"] == 1
        assert state["running"] is False
        assert state["last_finished_at"]
        assert state["last_error_at"]
        assert state["last_error"] == "raw background crash"
        assert snapshot["health"] == "error"
        assert loop_name not in runtime.tasks

    asyncio.run(scenario())


def test_new_terminal_exception_with_same_text_is_counted_after_handled_failure():
    async def scenario() -> None:
        loop_name = "same_text_new_exception"

        async def fail_twice() -> None:
            background._bg_mark_start(loop_name)
            try:
                raise RuntimeError("same failure")
            except RuntimeError as first_exc:
                background._bg_mark_error(loop_name, first_exc)
            background._bg_mark_start(loop_name)
            raise RuntimeError("same failure")

        runtime = background.BackgroundRuntime(
            spec_provider=lambda: [
                background.BackgroundLoopSpec(loop_name, True, fail_twice)
            ]
        )
        state = _fresh_bg_state(loop_name)

        await runtime.start()
        task = runtime.tasks[loop_name]
        with pytest.raises(RuntimeError, match="same failure"):
            await task
        await asyncio.sleep(0)

        snapshot = background.get_background_runtime_snapshot()[loop_name]
        assert state["runs"] == 2
        assert state["failures"] == 2
        assert state["last_error"] == "same failure"
        assert state["last_error_at"]
        assert snapshot["health"] == "error"
        assert task not in background._BACKGROUND_TASK_ERROR_MARKERS

    asyncio.run(scenario())


def test_handled_exception_record_is_released_while_task_continues():
    async def scenario() -> None:
        loop_name = "continued_after_handled_error"
        handled = asyncio.Event()
        release_terminal_crash = asyncio.Event()

        async def handled_then_continue() -> None:
            background._bg_mark_start(loop_name)
            try:
                raise RuntimeError("handled and continued")
            except RuntimeError as handled_exc:
                background._bg_mark_error(loop_name, handled_exc)
            handled.set()
            await release_terminal_crash.wait()
            background._bg_mark_start(loop_name)
            raise RuntimeError("later terminal crash")

        runtime = background.BackgroundRuntime(
            spec_provider=lambda: [
                background.BackgroundLoopSpec(loop_name, True, handled_then_continue)
            ]
        )
        state = _fresh_bg_state(loop_name)
        await runtime.start()
        task = runtime.tasks[loop_name]

        try:
            await handled.wait()
            await asyncio.sleep(0)

            assert task.done() is False
            marker = background._BACKGROUND_TASK_ERROR_MARKERS[task]
            assert isinstance(marker, BaseException) is False
            assert hasattr(marker, "__traceback__") is False
            assert state["failures"] == 1

            release_terminal_crash.set()
            with pytest.raises(RuntimeError, match="later terminal crash"):
                await task
            await asyncio.sleep(0)

            assert state["runs"] == 2
            assert state["failures"] == 2
            assert state["last_error"] == "later terminal crash"
            assert task not in background._BACKGROUND_TASK_ERROR_MARKERS
        finally:
            if not task.done():
                release_terminal_crash.set()
                await asyncio.gather(task, return_exceptions=True)
            await runtime.shutdown()

    asyncio.run(scenario())


def test_empty_terminal_exception_uses_exception_type_for_error_health():
    async def scenario() -> None:
        loop_name = "empty_raw_crash"

        async def crash_without_message() -> None:
            background._bg_mark_start(loop_name)
            raise RuntimeError()

        runtime = background.BackgroundRuntime(
            spec_provider=lambda: [
                background.BackgroundLoopSpec(loop_name, True, crash_without_message)
            ]
        )
        state = _fresh_bg_state(loop_name)

        await runtime.start()
        task = runtime.tasks[loop_name]
        with pytest.raises(RuntimeError):
            await task
        await asyncio.sleep(0)

        snapshot = background.get_background_runtime_snapshot()[loop_name]
        assert state["failures"] == 1
        assert state["last_error"] == "RuntimeError"
        assert snapshot["health"] == "error"

    asyncio.run(scenario())


def test_same_recorded_exception_rethrown_after_yield_is_not_counted_twice():
    async def scenario() -> None:
        loop_name = "yielded_recorded_exception"

        async def record_yield_and_rethrow() -> None:
            background._bg_mark_start(loop_name)
            try:
                raise RuntimeError("yielded recorded crash")
            except RuntimeError as exc:
                background._bg_mark_error(loop_name, exc)
                await asyncio.sleep(0)
                raise

        runtime = background.BackgroundRuntime(
            spec_provider=lambda: [
                background.BackgroundLoopSpec(loop_name, True, record_yield_and_rethrow)
            ]
        )
        state = _fresh_bg_state(loop_name)

        await runtime.start()
        task = runtime.tasks[loop_name]
        with pytest.raises(RuntimeError, match="yielded recorded crash"):
            await task
        await asyncio.sleep(0)

        assert state["failures"] == 1
        assert state["last_error"] == "yielded recorded crash"

    asyncio.run(scenario())


def test_task_error_already_recorded_by_loop_is_not_counted_twice():
    async def scenario() -> None:
        loop_name = "recorded_crash"

        async def recorded_crash() -> None:
            background._bg_mark_start(loop_name)
            try:
                raise RuntimeError("recorded background crash")
            except RuntimeError as exc:
                background._bg_mark_error(loop_name, exc)
                raise

        runtime = background.BackgroundRuntime(
            spec_provider=lambda: [
                background.BackgroundLoopSpec(loop_name, True, recorded_crash)
            ]
        )
        state = _fresh_bg_state(loop_name)

        await runtime.start()
        task = runtime.tasks[loop_name]
        with pytest.raises(RuntimeError, match="recorded background crash"):
            await task
        await asyncio.sleep(0)

        assert state["failures"] == 1
        assert state["last_error"] == "recorded background crash"
        assert background.get_background_runtime_snapshot()[loop_name]["health"] == "error"
        assert task not in background._BACKGROUND_TASK_ERROR_MARKERS

    asyncio.run(scenario())


def test_start_retrieves_a_done_task_exception_before_replacing_handle():
    async def scenario() -> None:
        replacement_started = asyncio.Event()

        async def crash() -> None:
            raise RuntimeError("completed before start")

        async def replacement_loop() -> None:
            replacement_started.set()
            await asyncio.Event().wait()

        runtime = background.BackgroundRuntime(
            spec_provider=lambda: [
                background.BackgroundLoopSpec("done_before_start", True, replacement_loop)
            ]
        )
        old = asyncio.create_task(crash())
        await asyncio.sleep(0)
        assert old.done()
        assert old._log_traceback is True
        runtime._tasks["done_before_start"] = old

        retrieved = False
        try:
            await runtime.start()
            await replacement_started.wait()
            replacement = runtime.tasks["done_before_start"]
            retrieved = old._log_traceback is False

            assert replacement is not old
        finally:
            if old._log_traceback:
                old.exception()
            await runtime.shutdown()

        assert retrieved is True

    asyncio.run(scenario())


def test_stale_task_exception_is_retrieved_without_polluting_replacement_state():
    async def scenario() -> None:
        old_started = asyncio.Event()
        release_old = asyncio.Event()
        replacement_started = asyncio.Event()

        async def old_loop() -> None:
            old_started.set()
            await release_old.wait()
            raise RuntimeError("stale task crash")

        async def replacement_loop() -> None:
            replacement_started.set()
            await asyncio.Event().wait()

        runtime = background.BackgroundRuntime(
            spec_provider=lambda: [
                background.BackgroundLoopSpec("stale_crash", True, old_loop)
            ]
        )
        state = _fresh_bg_state("stale_crash")
        await runtime.start()
        await old_started.wait()
        old = runtime.tasks["stale_crash"]

        replacement = asyncio.create_task(replacement_loop())
        await replacement_started.wait()
        runtime._tasks["stale_crash"] = replacement
        state["running"] = True
        state["failures"] = 23
        state["last_error"] = "replacement state"
        state_before = dict(state)

        release_old.set()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        retrieved = old._log_traceback is False

        try:
            assert runtime.tasks["stale_crash"] is replacement
            assert state == state_before
            assert retrieved is True
        finally:
            if old._log_traceback:
                old.exception()
            replacement.cancel()
            await asyncio.gather(replacement, return_exceptions=True)
            runtime._tasks.pop("stale_crash", None)
            state["running"] = False

    asyncio.run(scenario())


def test_runtime_shutdown_does_not_clear_state_for_a_replacement_handle():
    async def scenario() -> None:
        cancellation_seen = asyncio.Event()
        release_cancelled_task = asyncio.Event()
        replacement_started = asyncio.Event()

        async def original_loop() -> None:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancellation_seen.set()
                await release_cancelled_task.wait()
                raise

        async def replacement_loop() -> None:
            replacement_started.set()
            await asyncio.Event().wait()

        runtime = background.BackgroundRuntime(
            spec_provider=lambda: [
                background.BackgroundLoopSpec(
                    name="replacement_race",
                    enabled=True,
                    runner=original_loop,
                )
            ]
        )
        await runtime.start()
        shutdown_task = asyncio.create_task(runtime.shutdown())
        await cancellation_seen.wait()

        replacement = asyncio.create_task(replacement_loop())
        await replacement_started.wait()
        runtime._tasks["replacement_race"] = replacement
        background._bg_state("replacement_race")["running"] = True
        release_cancelled_task.set()
        await shutdown_task

        try:
            assert runtime.tasks["replacement_race"] is replacement
            assert background._bg_state("replacement_race")["running"] is True
        finally:
            replacement.cancel()
            await asyncio.gather(replacement, return_exceptions=True)
            runtime._tasks.pop("replacement_race", None)
            background._bg_state("replacement_race")["running"] = False

    asyncio.run(scenario())


def test_runtime_recreates_a_task_after_the_previous_handle_completed():
    async def scenario() -> None:
        starts: list[int] = []

        async def run_once() -> None:
            starts.append(len(starts) + 1)

        runtime = background.BackgroundRuntime(
            spec_provider=lambda: [
                background.BackgroundLoopSpec(
                    name="run_once",
                    enabled=True,
                    runner=run_once,
                )
            ]
        )

        await runtime.start()
        first = runtime.tasks["run_once"]
        await first

        await runtime.start()
        second = runtime.tasks["run_once"]
        await second

        assert second is not first
        assert starts == [1, 2]

        await runtime.shutdown()

    asyncio.run(scenario())


def test_default_spec_provider_covers_all_runtime_names_and_enablement_rules(monkeypatch):
    monkeypatch.setitem(background.settings.__dict__, "SYNC_INTERVAL_SECONDS", 1)
    monkeypatch.setitem(background.settings.__dict__, "EMAIL_SYNC_INTERVAL_SECONDS", 1)
    monkeypatch.setitem(background.settings.__dict__, "LANGBOT_ADAPTER_LOG_DIR", "/tmp/adapters")
    monkeypatch.setitem(background.settings.__dict__, "NEWSNOW_REFRESH_INTERVAL_SECONDS", 1)
    monkeypatch.setitem(background.settings.__dict__, "NEWS_SNAPSHOT_INTERVAL_SECONDS", 1)
    monkeypatch.setitem(background.settings.__dict__, "MEDIA_COLLECTOR_DAILY_ENABLED", True)
    monkeypatch.setitem(background.settings.__dict__, "SUMMARY_OVERLAY_INTERVAL_SECONDS", 1)
    monkeypatch.setitem(background.settings.__dict__, "AGGREGATION_RETENTION_INTERVAL_SECONDS", 1)
    monkeypatch.setitem(background.settings.__dict__, "MEDIA_CACHE_CLEANUP_ENABLED", True)
    monkeypatch.setitem(background.settings.__dict__, "MEDIA_CACHE_CLEANUP_INTERVAL_SECONDS", 1)
    monkeypatch.setattr(
        "app.services.llm_client.load_ai_config",
        lambda: {"wechatpad_sync_enabled": True},
    )

    specs = background._build_background_loop_specs()
    enabled = {spec.name: spec.enabled for spec in specs}
    names = [spec.name for spec in specs]

    assert len(specs) == 10
    assert len(set(names)) == 10
    assert names == background._BACKGROUND_RUNTIME_NAMES
    assert enabled == {
        "chatlog_sync": True,
        "wechat8061_sync": False,
        "email_sync": False,
        "ext_adapter_sync": True,
        "news_refresh": True,
        "news_snapshot": True,
        "media_collector": True,
        "summary_overlay": True,
        "aggregation_retention": True,
        "media_cache_cleanup": True,
    }


def test_default_spec_provider_disables_each_optional_loop(monkeypatch):
    monkeypatch.setitem(background.settings.__dict__, "SYNC_INTERVAL_SECONDS", 0)
    monkeypatch.setitem(background.settings.__dict__, "LANGBOT_ADAPTER_LOG_DIR", "")
    monkeypatch.setitem(background.settings.__dict__, "NEWSNOW_REFRESH_INTERVAL_SECONDS", 0)
    monkeypatch.setitem(background.settings.__dict__, "NEWS_SNAPSHOT_INTERVAL_SECONDS", 0)
    monkeypatch.setitem(background.settings.__dict__, "MEDIA_COLLECTOR_DAILY_ENABLED", False)
    monkeypatch.setitem(background.settings.__dict__, "SUMMARY_OVERLAY_INTERVAL_SECONDS", 0)
    monkeypatch.setitem(background.settings.__dict__, "AGGREGATION_RETENTION_INTERVAL_SECONDS", 0)
    monkeypatch.setitem(background.settings.__dict__, "MEDIA_CACHE_CLEANUP_ENABLED", False)
    monkeypatch.setitem(background.settings.__dict__, "MEDIA_CACHE_CLEANUP_INTERVAL_SECONDS", 0)
    monkeypatch.setattr("app.services.llm_client.load_ai_config", lambda: {})

    specs = background._build_background_loop_specs()

    assert {spec.name: spec.enabled for spec in specs} == {
        name: False for name in background._BACKGROUND_RUNTIME_NAMES
    }


def test_start_background_loops_returns_the_configured_singleton(monkeypatch):
    async def scenario() -> None:
        runtime = background.BackgroundRuntime(spec_provider=lambda: [])
        monkeypatch.setattr(background, "BACKGROUND_TASK_RUNTIME", runtime)

        returned = await background.start_background_loops()

        assert returned is runtime

    asyncio.run(scenario())


def test_start_background_loops_creates_an_independent_runtime_per_app(monkeypatch):
    _disable_default_background_specs(monkeypatch)

    async def scenario() -> None:
        global_runtime = background.BackgroundRuntime(spec_provider=lambda: [])
        monkeypatch.setattr(background, "BACKGROUND_TASK_RUNTIME", global_runtime)
        first_app = FastAPI()
        second_app = FastAPI()

        first = await background.start_background_loops(first_app)
        second = await background.start_background_loops(second_app)
        try:
            assert first is first_app.state.background_runtime
            assert second is second_app.state.background_runtime
            assert first is not second
            assert first is not global_runtime
            assert second is not global_runtime
        finally:
            await background.stop_background_loops(first_app)
            await background.stop_background_loops(second_app)

    asyncio.run(scenario())


def test_start_background_loops_reuses_each_apps_runtime_without_sharing_handles(monkeypatch):
    async def scenario() -> None:
        first_started = asyncio.Event()
        second_started = asyncio.Event()

        async def first_loop() -> None:
            first_started.set()
            await asyncio.Event().wait()

        async def second_loop() -> None:
            second_started.set()
            await asyncio.Event().wait()

        first_runtime = background.BackgroundRuntime(
            spec_provider=lambda: [
                background.BackgroundLoopSpec("first_app_loop", True, first_loop)
            ]
        )
        second_runtime = background.BackgroundRuntime(
            spec_provider=lambda: [
                background.BackgroundLoopSpec("second_app_loop", True, second_loop)
            ]
        )
        monkeypatch.setattr(
            background,
            "BACKGROUND_TASK_RUNTIME",
            background.BackgroundRuntime(spec_provider=lambda: []),
        )
        first_app = FastAPI()
        second_app = FastAPI()
        first_app.state.background_runtime = first_runtime
        second_app.state.background_runtime = second_runtime

        returned_first, returned_second = await asyncio.gather(
            background.start_background_loops(first_app),
            background.start_background_loops(second_app),
        )
        try:
            assert returned_first is first_runtime
            assert returned_second is second_runtime
            await asyncio.gather(first_started.wait(), second_started.wait())
            first_handle = first_runtime.tasks["first_app_loop"]
            second_handle = second_runtime.tasks["second_app_loop"]
            assert first_handle is not second_handle
        finally:
            await first_runtime.shutdown()
            await second_runtime.shutdown()

    asyncio.run(scenario())


def test_stop_background_loops_falls_back_to_singleton_without_app_runtime(monkeypatch):
    async def scenario() -> None:
        runtime, started, finished, _starts = _controlled_runtime()
        monkeypatch.setattr(background, "BACKGROUND_TASK_RUNTIME", runtime)
        app = FastAPI()
        await runtime.start()
        await started.wait()

        await background.stop_background_loops(app)

        assert finished.is_set()
        assert runtime.tasks == {}

    asyncio.run(scenario())


def test_stop_background_loops_prefers_the_runtime_attached_to_the_app():
    async def scenario() -> None:
        runtime, started, finished, _starts = _controlled_runtime()
        app = FastAPI()
        await runtime.start(app)
        await started.wait()

        await background.stop_background_loops(app)

        assert finished.is_set()
        assert runtime.tasks == {}

    asyncio.run(scenario())


def test_app_lifespan_stops_background_loops_after_normal_exit(monkeypatch):
    main = _load_main_without_db_init(monkeypatch)

    calls: list[tuple[str, FastAPI]] = []

    async def fake_start(app: FastAPI) -> None:
        calls.append(("start", app))

    async def fake_stop(app: FastAPI) -> None:
        calls.append(("stop", app))

    monkeypatch.setattr(main, "start_background_loops", fake_start)
    monkeypatch.setattr(main, "stop_background_loops", fake_stop)
    app = FastAPI()

    async def scenario() -> None:
        async with main.app_lifespan(app):
            assert calls == [("start", app)]

    asyncio.run(scenario())

    assert calls == [("start", app), ("stop", app)]


def test_app_lifespan_stops_background_loops_when_context_raises(monkeypatch):
    main = _load_main_without_db_init(monkeypatch)

    calls: list[tuple[str, FastAPI]] = []

    async def fake_start(app: FastAPI) -> None:
        calls.append(("start", app))

    async def fake_stop(app: FastAPI) -> None:
        calls.append(("stop", app))

    monkeypatch.setattr(main, "start_background_loops", fake_start)
    monkeypatch.setattr(main, "stop_background_loops", fake_stop)
    app = FastAPI()

    async def scenario() -> None:
        with pytest.raises(RuntimeError, match="lifespan body failed"):
            async with main.app_lifespan(app):
                raise RuntimeError("lifespan body failed")

    asyncio.run(scenario())

    assert calls == [("start", app), ("stop", app)]


def test_app_lifespan_propagates_stop_background_loop_errors(monkeypatch):
    main = _load_main_without_db_init(monkeypatch)
    calls: list[str] = []

    async def fake_start(_app: FastAPI) -> None:
        calls.append("start")

    async def fake_stop(_app: FastAPI) -> None:
        calls.append("stop")
        raise RuntimeError("background shutdown failed")

    monkeypatch.setattr(main, "start_background_loops", fake_start)
    monkeypatch.setattr(main, "stop_background_loops", fake_stop)
    app = FastAPI()

    async def scenario() -> None:
        with pytest.raises(RuntimeError, match="background shutdown failed"):
            async with main.app_lifespan(app):
                pass

    asyncio.run(scenario())

    assert calls == ["start", "stop"]


def test_app_lifespan_stops_runtime_when_startup_partially_fails(monkeypatch):
    main = _load_main_without_db_init(monkeypatch)
    calls: list[str] = []

    async def fake_start(_app: FastAPI) -> None:
        calls.append("start")
        raise RuntimeError("background startup failed")

    async def fake_stop(_app: FastAPI) -> None:
        calls.append("stop")

    monkeypatch.setattr(main, "start_background_loops", fake_start)
    monkeypatch.setattr(main, "stop_background_loops", fake_stop)
    app = FastAPI()

    async def scenario() -> None:
        with pytest.raises(RuntimeError, match="background startup failed"):
            async with main.app_lifespan(app):
                pass

    asyncio.run(scenario())

    assert calls == ["start", "stop"]
