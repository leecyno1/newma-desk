from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Event, Lock
from typing import Any, Callable, Protocol

from vibe_visualization_api.creator_studio.repository import CreatorRunRepository


FINAL_JOB_STATUSES = {"succeeded", "failed", "cancelled"}


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


class NodeExecutionAdapter(Protocol):
    def run_node(
        self,
        request: dict[str, Any],
        *,
        cancel_event: Event | None = None,
    ) -> dict[str, Any]: ...


class CreatorExecutionRuntime:
    """Persistent background queue for all Creator Workflow Node executions."""

    def __init__(
        self,
        repository: CreatorRunRepository,
        adapter: NodeExecutionAdapter,
        *,
        on_started: Callable[[dict[str, Any]], None],
        on_finished: Callable[[dict[str, Any]], None],
        max_workers: int = 2,
    ):
        self.repository = repository
        self.adapter = adapter
        self.on_started = on_started
        self.on_finished = on_finished
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="creator-execution",
        )
        self._futures: dict[tuple[str, str, str], Future[None]] = {}
        self._cancellations: dict[tuple[str, str, str], Event] = {}
        self._lock = Lock()
        self._started = False
        self._stopping = False

    @staticmethod
    def _key(job: dict[str, Any]) -> tuple[str, str, str]:
        return (
            str(job["userId"]),
            str(job["workspaceId"]),
            str(job["jobId"]),
        )

    def startup(self) -> None:
        if self._started:
            return
        self._started = True
        for job in self.repository.list_incomplete_jobs():
            if job.get("status") == "running":
                self._finish_interrupted(job)
            elif job.get("cancelRequested"):
                self._finish_cancelled(job)
            else:
                self.dispatch(job)

    def dispatch(self, job: dict[str, Any]) -> None:
        key = self._key(job)
        with self._lock:
            if self._stopping:
                return
            current = self._futures.get(key)
            if current is not None and not current.done():
                return
            cancellation = Event()
            self._cancellations[key] = cancellation
            future = self._executor.submit(self._run, job, cancellation)
            self._futures[key] = future
            future.add_done_callback(lambda _future, key=key: self._forget(key))

    def cancel(
        self,
        *,
        user_id: str,
        workspace_id: str,
        job_id: str,
        requested_at: str,
    ) -> dict[str, Any]:
        job = self.repository.request_job_cancel(
            user_id=user_id,
            workspace_id=workspace_id,
            job_id=job_id,
            requested_at=requested_at,
        )
        if job.get("status") in FINAL_JOB_STATUSES:
            return job
        key = (user_id, workspace_id, job_id)
        with self._lock:
            cancellation = self._cancellations.get(key)
            future = self._futures.get(key)
            if cancellation is not None:
                cancellation.set()
            cancelled_before_start = bool(future and future.cancel())
        if cancelled_before_start or future is None:
            job["cancelRequested"] = True
            self._finish_cancelled(job)
        return self.repository.get_job(
            user_id=user_id,
            workspace_id=workspace_id,
            job_id=job_id,
        )

    def shutdown(self) -> None:
        with self._lock:
            if self._stopping:
                return
            self._stopping = True
            active = list(self._cancellations.values())
        for cancellation in active:
            cancellation.set()
        self._executor.shutdown(wait=True, cancel_futures=False)

    def _forget(self, key: tuple[str, str, str]) -> None:
        with self._lock:
            self._futures.pop(key, None)
            self._cancellations.pop(key, None)

    def _run(self, queued_job: dict[str, Any], cancellation: Event) -> None:
        job = self.repository.get_job(
            user_id=str(queued_job["userId"]),
            workspace_id=str(queued_job["workspaceId"]),
            job_id=str(queued_job["jobId"]),
        )
        if cancellation.is_set() or job.get("cancelRequested"):
            self._finish_cancelled(job)
            return

        timestamp = now_iso()
        job.update(
            {
                "status": "running",
                "progress": max(10, int(job.get("progress") or 0)),
                "startedAt": timestamp,
                "updatedAt": timestamp,
            }
        )
        self.repository.update_job(job)
        self.on_started(job)

        try:
            result = self.adapter.run_node(
                dict(job["request"]),
                cancel_event=cancellation,
            )
        except Exception as error:  # The runtime normalizes all Adapter failures.
            result = {
                "status": "failed",
                "progress": 0,
                "error": str(error),
                "logs": [{"message": str(error)}],
            }

        result_status = str(result.get("status") or "failed")
        if cancellation.is_set() or result_status == "cancelled":
            job["cancelRequested"] = True
            self._finish_cancelled(job, result=result)
            return

        job_status = (
            "succeeded"
            if result_status in {"succeeded", "waiting_user"}
            else "failed"
        )
        finished_at = str(result.get("finished_at") or now_iso())
        nested_result = result.get("result")
        nested_error = (
            nested_result.get("error")
            if isinstance(nested_result, dict)
            else None
        )
        job.update(
            {
                "status": job_status,
                "progress": int(
                    result.get("progress")
                    or (100 if job_status == "succeeded" else 0)
                ),
                "result": result,
                "error": result.get("error") or nested_error,
                "finishedAt": finished_at,
                "updatedAt": finished_at,
            }
        )
        self.repository.update_job(job)
        self.on_finished(job)

    def _finish_cancelled(
        self,
        job: dict[str, Any],
        *,
        result: dict[str, Any] | None = None,
    ) -> None:
        timestamp = str(
            (result or {}).get("finished_at")
            or job.get("cancelRequestedAt")
            or now_iso()
        )
        job.update(
            {
                "status": "cancelled",
                "progress": int(job.get("progress") or 0),
                "cancelRequested": True,
                "result": result or {"status": "cancelled"},
                "finishedAt": timestamp,
                "updatedAt": timestamp,
            }
        )
        self.repository.update_job(job)
        self.on_finished(job)

    def _finish_interrupted(self, job: dict[str, Any]) -> None:
        timestamp = now_iso()
        job.update(
            {
                "status": "failed",
                "progress": 0,
                "error": "Creator Runtime 重启，原执行已中断，请重试。",
                "result": {
                    "status": "failed",
                    "error": "Creator Runtime restarted during execution",
                },
                "finishedAt": timestamp,
                "updatedAt": timestamp,
            }
        )
        self.repository.update_job(job)
        self.on_finished(job)
