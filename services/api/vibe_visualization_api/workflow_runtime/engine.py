from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import CroniterBadCronError, croniter

from vibe_visualization_api.workflow_control.service import WorkflowControlService
from vibe_visualization_api.workflow_runtime.adapters import (
    NodeExecutionAdapterRegistry,
    NodeExecutionContext,
)
from vibe_visualization_api.workflow_runtime.conditions import (
    ConditionExpressionError,
    evaluate_condition,
    parse_condition,
)
from vibe_visualization_api.workflow_runtime.repository import (
    WorkflowRuntimeConflictError,
    WorkflowRuntimeRepository,
)


EXECUTION_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
JOB_TERMINAL_STATUSES = {"completed", "failed", "blocked", "cancelled", "skipped"}
DEPENDENCY_TERMINAL_STATUSES = {"completed", "cancelled", "skipped"}
JOB_OPEN_STATUSES = {
    "pending",
    "ready",
    "leased",
    "running",
    "retry_wait",
    "waiting",
}


def utc_now() -> datetime:
    return datetime.now(UTC)


class WorkflowRuntimeEngine:
    """Deep Module for persistent workflow scheduling and controlled execution."""

    def __init__(
        self,
        database_path: Path,
        control: WorkflowControlService,
        *,
        adapters: NodeExecutionAdapterRegistry | None = None,
        clock: Callable[[], datetime] = utc_now,
    ):
        self.repository = WorkflowRuntimeRepository(database_path)
        self.control = control
        self.adapters = adapters or NodeExecutionAdapterRegistry()
        self._clock = clock
        self._execution_locks: dict[tuple[str, str], Lock] = {}
        self._execution_locks_guard = Lock()

    def _now(self) -> datetime:
        value = self._clock()
        return value if value.tzinfo else value.replace(tzinfo=UTC)

    def current_timestamp(self) -> str:
        return self._now().isoformat()

    def start(
        self,
        *,
        organization_id: str,
        actor_principal_id: str,
        run_id: str,
        trigger_type: str,
        idempotency_key: str,
        input_payload: dict[str, Any],
        user_id: str = "local-user",
        dispatch: bool = True,
    ) -> dict[str, Any]:
        run = self.control.authorize_runtime_execution(
            organization_id=organization_id,
            actor_principal_id=actor_principal_id,
            run_id=run_id,
        )
        for edge in run["edges"]:
            parse_condition(edge.get("condition", ""))
        timestamp = self._now().isoformat()
        jobs: list[dict[str, Any]] = []
        for position, node in enumerate(run["nodes"]):
            executor_id = node.get("executorId") or "approval_wait"
            self.adapters.require(executor_id)
            status = "pending"
            result = None
            completed_at = None
            if node["status"] == "completed":
                status = "completed"
                result = {"source": "workflow_control"}
                completed_at = timestamp
            elif node["status"] in {"cancelled", "skipped", "failed", "blocked"}:
                status = node["status"]
                completed_at = timestamp
            jobs.append(
                {
                    "id": f"job-{uuid4().hex[:20]}",
                    "nodeId": node["id"],
                    "position": position,
                    "executorId": executor_id,
                    "status": status,
                    "maxAttempts": int(node.get("retryLimit", 0)) + 1,
                    "timeoutSeconds": int(node.get("timeoutSeconds", 300)),
                    "retryDelaySeconds": int(node.get("retryDelaySeconds", 0)),
                    "availableAt": timestamp if status == "pending" else None,
                    "completedAt": completed_at,
                    "input": node.get("executorParameters", {}),
                    "result": result,
                }
            )
        snapshot, created = self.repository.create_execution(
            organization_id=organization_id,
            run_id=run_id,
            trigger_type=trigger_type,
            idempotency_key=idempotency_key,
            requested_by=actor_principal_id,
            user_id=user_id,
            input_payload=input_payload,
            jobs=jobs,
            timestamp=timestamp,
        )
        if not created:
            return snapshot
        if dispatch:
            return self.tick(
                organization_id=organization_id,
                execution_id=snapshot["id"],
            )
        return self.repository.snapshot(organization_id, snapshot["id"])

    def get(self, organization_id: str, execution_id: str) -> dict[str, Any]:
        return self.repository.snapshot(organization_id, execution_id)

    def list(
        self,
        organization_id: str,
        run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return self.repository.list_executions(organization_id, run_id)

    def create_trigger(
        self,
        *,
        organization_id: str,
        actor_principal_id: str,
        run_id: str,
        trigger_type: str,
        event_type: str | None,
        interval_seconds: int | None,
        cron_expression: str | None = None,
        timezone: str | None = None,
        input_payload: dict[str, Any],
        user_id: str,
        enabled: bool = True,
    ) -> dict[str, Any]:
        self.control.authorize_runtime_execution(
            organization_id=organization_id,
            actor_principal_id=actor_principal_id,
            run_id=run_id,
        )
        if trigger_type not in {"event", "schedule"}:
            raise ValueError("persistent trigger must be event or schedule")
        if trigger_type == "event" and not event_type:
            raise ValueError("event trigger requires eventType")
        if trigger_type == "schedule" and bool(interval_seconds) == bool(
            cron_expression
        ):
            raise ValueError(
                "schedule trigger requires exactly one schedule expression"
            )
        timestamp = self._now().isoformat()
        next_fire_at = None
        if trigger_type == "schedule" and enabled:
            next_fire_at = self._next_schedule_fire(
                {
                    "intervalSeconds": interval_seconds,
                    "cronExpression": cron_expression,
                    "timezone": timezone or "Asia/Shanghai",
                },
                self._now(),
            ).isoformat()
        return self.repository.create_trigger(
            organization_id=organization_id,
            run_id=run_id,
            trigger_type=trigger_type,
            event_type=event_type if trigger_type == "event" else None,
            interval_seconds=(
                interval_seconds if trigger_type == "schedule" else None
            ),
            cron_expression=(
                cron_expression if trigger_type == "schedule" else None
            ),
            timezone=(timezone or "Asia/Shanghai") if cron_expression else None,
            next_fire_at=next_fire_at,
            enabled=enabled,
            requested_by=actor_principal_id,
            user_id=user_id,
            input_payload=input_payload,
            timestamp=timestamp,
        )

    def list_triggers(
        self,
        organization_id: str,
        run_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return self.repository.list_triggers(organization_id, run_id)

    def set_trigger_enabled(
        self,
        *,
        organization_id: str,
        trigger_id: str,
        enabled: bool,
        actor_principal_id: str,
    ) -> dict[str, Any]:
        trigger = self.repository.get_trigger(organization_id, trigger_id)
        self.control.authorize_runtime_execution(
            organization_id=organization_id,
            actor_principal_id=actor_principal_id,
            run_id=trigger["runId"],
        )
        return self.repository.set_trigger_enabled(
            organization_id=organization_id,
            trigger_id=trigger_id,
            enabled=enabled,
            next_fire_at=(
                self._next_schedule_fire(trigger, self._now()).isoformat()
                if enabled and trigger["triggerType"] == "schedule"
                else None
            ),
            timestamp=self._now().isoformat(),
        )

    def emit_event(
        self,
        *,
        organization_id: str,
        event_type: str,
        idempotency_key: str,
        input_payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        executions = []
        for trigger in self.repository.list_event_triggers(
            organization_id,
            event_type,
        ):
            executions.append(
                self._dispatch_trigger(
                    trigger,
                    dispatch_key=idempotency_key,
                    trigger_type="event",
                    input_payload={**trigger["input"], **input_payload},
                )
            )
        return executions

    def dispatch_due_schedules(self, *, limit: int = 100) -> list[dict[str, Any]]:
        executions = []
        timestamp = self._now().isoformat()
        for trigger in self.repository.list_due_schedule_triggers(
            timestamp,
            limit=limit,
        ):
            try:
                execution = self._dispatch_trigger(
                    trigger,
                    dispatch_key=trigger["scheduledFor"],
                    trigger_type="schedule",
                    input_payload={
                        **trigger["input"],
                        "scheduledFor": trigger["scheduledFor"],
                    },
                )
            except Exception:
                continue
            executions.append(execution)
            self.repository.advance_schedule_trigger(
                organization_id=trigger["organizationId"],
                trigger_id=trigger["id"],
                scheduled_for=trigger["scheduledFor"],
                next_fire_at=self._next_schedule_fire(
                    trigger,
                    self._now(),
                ).isoformat(),
                timestamp=timestamp,
            )
        return executions

    @staticmethod
    def _next_schedule_fire(
        trigger: dict[str, Any],
        after: datetime,
    ) -> datetime:
        interval_seconds = trigger.get("intervalSeconds")
        if interval_seconds:
            return after + timedelta(seconds=int(interval_seconds))
        expression = str(trigger.get("cronExpression") or "").strip()
        timezone_name = str(trigger.get("timezone") or "Asia/Shanghai")
        try:
            zone = ZoneInfo(timezone_name)
            localized = after.astimezone(zone)
            return croniter(expression, localized).get_next(datetime).astimezone(UTC)
        except (CroniterBadCronError, ValueError, ZoneInfoNotFoundError) as error:
            raise ValueError("invalid workflow schedule") from error

    def _dispatch_trigger(
        self,
        trigger: dict[str, Any],
        *,
        dispatch_key: str,
        trigger_type: str,
        input_payload: dict[str, Any],
    ) -> dict[str, Any]:
        run_id = (
            "run-"
            + uuid5(
                NAMESPACE_URL,
                ":".join(
                    (
                        trigger["organizationId"],
                        trigger["id"],
                        dispatch_key,
                    )
                ),
            ).hex[:20]
        )
        source = self.control.repository.get_run(
            trigger["organizationId"],
            trigger["runId"],
        )
        self.control.create_triggered_run(
            organization_id=trigger["organizationId"],
            actor_principal_id=trigger["requestedBy"],
            source_run_id=trigger["runId"],
            run_id=run_id,
            title=f"{source['title']} · {trigger_type} · {dispatch_key}",
        )
        return self.start(
            organization_id=trigger["organizationId"],
            actor_principal_id=trigger["requestedBy"],
            run_id=run_id,
            trigger_type=trigger_type,
            idempotency_key=f"{trigger_type}:{trigger['id']}:{dispatch_key}",
            input_payload={
                **input_payload,
                "sourceRunId": trigger["runId"],
                "triggerId": trigger["id"],
            },
            user_id=trigger["userId"],
            dispatch=False,
        )

    def _execution_lock(self, organization_id: str, execution_id: str) -> Lock:
        key = (organization_id, execution_id)
        with self._execution_locks_guard:
            return self._execution_locks.setdefault(key, Lock())

    def tick(
        self,
        *,
        organization_id: str,
        execution_id: str,
        max_jobs: int = 20,
        actor_principal_id: str | None = None,
    ) -> dict[str, Any]:
        with self._execution_lock(organization_id, execution_id):
            return self._tick(
                organization_id=organization_id,
                execution_id=execution_id,
                max_jobs=max_jobs,
                actor_principal_id=actor_principal_id,
            )

    def _tick(
        self,
        *,
        organization_id: str,
        execution_id: str,
        max_jobs: int = 20,
        actor_principal_id: str | None = None,
    ) -> dict[str, Any]:
        execution = self.repository.get_execution(organization_id, execution_id)
        command_actor = actor_principal_id or execution["requestedBy"]
        self.control.authorize_runtime_execution(
            organization_id=organization_id,
            actor_principal_id=command_actor,
            run_id=execution["runId"],
        )
        if execution["status"] == "queued":
            execution = self.repository.set_execution_status(
                organization_id=organization_id,
                execution_id=execution_id,
                status="running",
                expected_statuses={"queued"},
                timestamp=self._now().isoformat(),
            )
        if execution["status"] != "running":
            return self.repository.snapshot(organization_id, execution_id)

        self._recover_expired_jobs(organization_id, execution)
        self._refresh_jobs(organization_id, execution)
        worker_id = f"runtime-{uuid4().hex[:12]}"
        dispatched = self._poll_waiting_jobs(
            organization_id,
            execution,
            worker_id=worker_id,
            limit=max_jobs,
        )
        self._refresh_jobs(organization_id, execution)
        while dispatched < max_jobs:
            now = self._now()
            self.repository.make_due_retries_ready(
                organization_id=organization_id,
                execution_id=execution_id,
                timestamp=now.isoformat(),
            )
            self._refresh_jobs(organization_id, execution)
            leased = self.repository.lease_next_ready_job(
                organization_id=organization_id,
                execution_id=execution_id,
                worker_id=worker_id,
                timestamp=now.isoformat(),
                lease_expires_at=(now + timedelta(seconds=60)).isoformat(),
            )
            if leased is None:
                break
            dispatched += 1
            self._execute_job(organization_id, execution, leased)

        self._refresh_jobs(organization_id, execution)
        return self._finalize_execution(organization_id, execution_id)

    def pause(
        self,
        *,
        organization_id: str,
        execution_id: str,
        reason: str = "",
        actor_principal_id: str | None = None,
    ) -> dict[str, Any]:
        execution = self.repository.get_execution(organization_id, execution_id)
        command_actor = actor_principal_id or execution["requestedBy"]
        self.control.authorize_runtime_execution(
            organization_id=organization_id,
            actor_principal_id=command_actor,
            run_id=execution["runId"],
        )
        if execution["status"] == "paused":
            return self.repository.snapshot(organization_id, execution_id)
        return self.repository.set_execution_status(
            organization_id=organization_id,
            execution_id=execution_id,
            status="paused",
            expected_statuses={"queued", "running"},
            timestamp=self._now().isoformat(),
            reason=reason,
        )

    def resume(
        self,
        *,
        organization_id: str,
        execution_id: str,
        reason: str = "",
        actor_principal_id: str | None = None,
    ) -> dict[str, Any]:
        execution = self.repository.get_execution(organization_id, execution_id)
        self.control.authorize_runtime_execution(
            organization_id=organization_id,
            actor_principal_id=actor_principal_id or execution["requestedBy"],
            run_id=execution["runId"],
        )
        self.repository.set_execution_status(
            organization_id=organization_id,
            execution_id=execution_id,
            status="running",
            expected_statuses={"paused"},
            timestamp=self._now().isoformat(),
            reason=reason,
        )
        return self.tick(
            organization_id=organization_id,
            execution_id=execution_id,
            actor_principal_id=actor_principal_id,
        )

    def cancel(
        self,
        *,
        organization_id: str,
        execution_id: str,
        reason: str = "",
        actor_principal_id: str | None = None,
    ) -> dict[str, Any]:
        execution = self.repository.get_execution(organization_id, execution_id)
        command_actor = actor_principal_id or execution["requestedBy"]
        self.control.authorize_runtime_execution(
            organization_id=organization_id,
            actor_principal_id=command_actor,
            run_id=execution["runId"],
        )
        if execution["status"] == "cancelled":
            return self.repository.snapshot(organization_id, execution_id)
        if execution["status"] in {"completed", "failed"}:
            raise WorkflowRuntimeConflictError(
                f"execution {execution_id} is {execution['status']}"
            )
        timestamp = self._now().isoformat()
        self.repository.set_execution_status(
            organization_id=organization_id,
            execution_id=execution_id,
            status="cancelled",
            expected_statuses={"queued", "running", "paused"},
            timestamp=timestamp,
            reason=reason,
        )
        for job in self.repository.list_jobs(organization_id, execution_id):
            if job["status"] not in JOB_OPEN_STATUSES:
                continue
            self._cancel_adapter_job(organization_id, execution, job)
            self.repository.transition_job(
                organization_id=organization_id,
                execution_id=execution_id,
                job_id=job["id"],
                status="cancelled",
                expected_statuses={job["status"]},
                timestamp=timestamp,
                fields={
                    "completedAt": timestamp,
                    "leaseOwner": None,
                    "leaseExpiresAt": None,
                    "deadlineAt": None,
                },
                event_payload={"reason": reason},
            )
            self.control.runtime_transition_node(
                organization_id=organization_id,
                actor_principal_id=command_actor,
                run_id=execution["runId"],
                node_id=job["nodeId"],
                status="cancelled",
                execution_id=execution_id,
                job_id=job["id"],
                detail={"reason": reason},
            )
        return self.repository.snapshot(organization_id, execution_id)

    def retry_job(
        self,
        *,
        organization_id: str,
        execution_id: str,
        job_id: str,
        actor_principal_id: str | None = None,
    ) -> dict[str, Any]:
        execution = self.repository.get_execution(organization_id, execution_id)
        command_actor = actor_principal_id or execution["requestedBy"]
        self.control.authorize_runtime_execution(
            organization_id=organization_id,
            actor_principal_id=command_actor,
            run_id=execution["runId"],
        )
        job = self.repository.get_job(organization_id, execution_id, job_id)
        timestamp = self._now().isoformat()
        self.repository.transition_job(
            organization_id=organization_id,
            execution_id=execution_id,
            job_id=job_id,
            status="ready",
            expected_statuses={"failed", "blocked"},
            timestamp=timestamp,
            fields={
                "availableAt": timestamp,
                "error": None,
                "result": None,
                "completedAt": None,
            },
            event_payload={"reason": "manual_retry"},
        )
        self.control.runtime_transition_node(
            organization_id=organization_id,
            actor_principal_id=command_actor,
            run_id=execution["runId"],
            node_id=job["nodeId"],
            status="ready",
            execution_id=execution_id,
            job_id=job_id,
            detail={"reason": "manual_retry"},
        )
        if execution["status"] == "failed":
            self.repository.set_execution_status(
                organization_id=organization_id,
                execution_id=execution_id,
                status="running",
                expected_statuses={"failed"},
                timestamp=timestamp,
            )
        return self.tick(
            organization_id=organization_id,
            execution_id=execution_id,
            actor_principal_id=actor_principal_id,
        )

    def _execute_job(
        self,
        organization_id: str,
        execution: dict[str, Any],
        job: dict[str, Any],
        *,
        resume: bool = False,
    ) -> None:
        now = self._now()
        runtime_fields = (
            {}
            if resume
            else {
                "startedAt": now.isoformat(),
                "deadlineAt": (
                    now + timedelta(seconds=job["timeoutSeconds"])
                ).isoformat(),
            }
        )
        job = self.repository.transition_job(
            organization_id=organization_id,
            execution_id=execution["id"],
            job_id=job["id"],
            status="running",
            expected_statuses={"leased"},
            timestamp=now.isoformat(),
            fields=runtime_fields,
        )
        run = self.control.runtime_transition_node(
            organization_id=organization_id,
            actor_principal_id=execution["requestedBy"],
            run_id=execution["runId"],
            node_id=job["nodeId"],
            status="running",
            execution_id=execution["id"],
            job_id=job["id"],
        )
        try:
            context = self._execution_context(organization_id, execution, run, job)
            adapter = self.adapters.require(job["executorId"])
            if resume:
                poll = getattr(adapter, "poll", None)
                if not callable(poll):
                    raise ValueError(
                        f"executor {job['executorId']} does not support polling"
                    )
                result = poll(context, job["input"], job.get("result") or {})
            else:
                result = adapter.execute(context, job["input"])
            deadline = datetime.fromisoformat(job["deadlineAt"])
            if self._now() >= deadline:
                raise TimeoutError("workflow node timed out")
            timestamp = self._now().isoformat()
            if result.status == "waiting":
                self.repository.transition_job(
                    organization_id=organization_id,
                    execution_id=execution["id"],
                    job_id=job["id"],
                    status="waiting",
                    expected_statuses={"running"},
                    timestamp=timestamp,
                    fields={
                        "result": result.output,
                        "leaseOwner": None,
                        "leaseExpiresAt": None,
                    },
                )
                self.control.runtime_transition_node(
                    organization_id=organization_id,
                    actor_principal_id=execution["requestedBy"],
                    run_id=execution["runId"],
                    node_id=job["nodeId"],
                    status="ready",
                    execution_id=execution["id"],
                    job_id=job["id"],
                    detail={"waiting": True},
                )
                return
            if result.status != "completed":
                raise ValueError(f"unsupported adapter result status: {result.status}")
            if result.output:
                self.control.record_runtime_output(
                    organization_id=organization_id,
                    actor_principal_id=execution["requestedBy"],
                    run_id=execution["runId"],
                    node_id=job["nodeId"],
                    execution_id=execution["id"],
                    job_id=job["id"],
                    output=result.output,
                )
            transitioned = self.control.runtime_transition_node(
                organization_id=organization_id,
                actor_principal_id=execution["requestedBy"],
                run_id=execution["runId"],
                node_id=job["nodeId"],
                status="completed",
                execution_id=execution["id"],
                job_id=job["id"],
            )
            node_status = next(
                node["status"]
                for node in transitioned["nodes"]
                if node["id"] == job["nodeId"]
            )
            waiting_review = node_status == "waiting_review"
            self.repository.transition_job(
                organization_id=organization_id,
                execution_id=execution["id"],
                job_id=job["id"],
                status="waiting" if waiting_review else "completed",
                expected_statuses={"running"},
                timestamp=timestamp,
                fields={
                    "result": result.output,
                    "completedAt": None if waiting_review else timestamp,
                    "leaseOwner": None,
                    "leaseExpiresAt": None,
                    "deadlineAt": None,
                },
                event_payload={"waitingReview": waiting_review},
            )
        except Exception as error:
            self._retry_or_fail_job(
                organization_id,
                execution,
                job,
                {
                    "type": type(error).__name__,
                    "message": str(error),
                },
            )

    def _poll_waiting_jobs(
        self,
        organization_id: str,
        execution: dict[str, Any],
        *,
        worker_id: str,
        limit: int,
    ) -> int:
        polled = 0
        run = self.control.repository.get_run(organization_id, execution["runId"])
        node_status = {node["id"]: node["status"] for node in run["nodes"]}
        for job in self.repository.list_jobs(organization_id, execution["id"]):
            if (
                polled >= limit
                or job["status"] != "waiting"
                or node_status.get(job["nodeId"]) == "waiting_review"
            ):
                continue
            adapter = self.adapters.require(job["executorId"])
            if not callable(getattr(adapter, "poll", None)):
                continue
            now = self._now()
            leased = self.repository.transition_job(
                organization_id=organization_id,
                execution_id=execution["id"],
                job_id=job["id"],
                status="leased",
                expected_statuses={"waiting"},
                timestamp=now.isoformat(),
                fields={
                    "leaseOwner": worker_id,
                    "leaseExpiresAt": (now + timedelta(seconds=60)).isoformat(),
                },
                event_payload={"reason": "poll_external_task"},
            )
            self._execute_job(
                organization_id,
                execution,
                leased,
                resume=True,
            )
            polled += 1
        return polled

    def _refresh_jobs(
        self,
        organization_id: str,
        execution: dict[str, Any],
    ) -> None:
        for _ in range(100):
            changed = False
            run = self.control.repository.get_run(organization_id, execution["runId"])
            jobs = self.repository.list_jobs(organization_id, execution["id"])
            node_map = {node["id"]: node for node in run["nodes"]}
            job_map = {job["nodeId"]: job for job in jobs}
            timestamp = self._now().isoformat()

            for job in jobs:
                if job["status"] in JOB_TERMINAL_STATUSES:
                    continue
                node_status = node_map[job["nodeId"]]["status"]
                mirrored = {
                    "completed": "completed",
                    "cancelled": "cancelled",
                    "skipped": "skipped",
                    "failed": "failed",
                    "blocked": "blocked",
                }.get(node_status)
                if mirrored:
                    self.repository.transition_job(
                        organization_id=organization_id,
                        execution_id=execution["id"],
                        job_id=job["id"],
                        status=mirrored,
                        expected_statuses={job["status"]},
                        timestamp=timestamp,
                        fields={"completedAt": timestamp},
                        event_payload={"source": "workflow_control"},
                    )
                    changed = True
                    break
                if node_status == "waiting_review" and job["status"] != "waiting":
                    self.repository.transition_job(
                        organization_id=organization_id,
                        execution_id=execution["id"],
                        job_id=job["id"],
                        status="waiting",
                        expected_statuses={job["status"]},
                        timestamp=timestamp,
                        fields={
                            "leaseOwner": None,
                            "leaseExpiresAt": None,
                            "deadlineAt": None,
                        },
                        event_payload={"reason": "waiting_review"},
                    )
                    changed = True
                    break
            if changed:
                continue

            data, artifacts, results = self._runtime_context_data(
                organization_id,
                execution,
                jobs,
            )
            incoming: dict[str, list[dict[str, Any]]] = {
                node_id: [] for node_id in node_map
            }
            for edge in run["edges"]:
                incoming[edge["target"]].append(edge)

            for job in jobs:
                if job["status"] != "pending":
                    continue
                edges = incoming[job["nodeId"]]
                target_status: str | None = None
                detail: dict[str, Any] = {}
                if not edges:
                    target_status = (
                        "waiting" if job["executorId"] == "approval_wait" else "ready"
                    )
                else:
                    source_jobs = [job_map[edge["source"]] for edge in edges]
                    if any(
                        item["status"] in {"failed", "blocked"}
                        for item in source_jobs
                    ):
                        target_status = "blocked"
                        detail = {"reason": "upstream_failed"}
                    elif not all(
                        item["status"] in DEPENDENCY_TERMINAL_STATUSES
                        for item in source_jobs
                    ):
                        continue
                    elif any(
                        item["status"] in {"cancelled", "skipped"}
                        for item in source_jobs
                    ):
                        target_status = "skipped"
                        detail = {"reason": "upstream_not_executed"}
                    else:
                        try:
                            conditions_pass = all(
                                self._edge_condition(
                                    edge,
                                    run,
                                    node_map,
                                    data,
                                    artifacts,
                                    results,
                                )
                                for edge in edges
                            )
                        except ConditionExpressionError as error:
                            target_status = "failed"
                            detail = {
                                "reason": "invalid_condition",
                                "message": str(error),
                            }
                        else:
                            if conditions_pass:
                                target_status = (
                                    "waiting"
                                    if job["executorId"] == "approval_wait"
                                    else "ready"
                                )
                            else:
                                target_status = "skipped"
                                detail = {"reason": "condition_false"}
                if target_status is None:
                    continue
                self.repository.transition_job(
                    organization_id=organization_id,
                    execution_id=execution["id"],
                    job_id=job["id"],
                    status=target_status,
                    expected_statuses={"pending"},
                    timestamp=timestamp,
                    fields={
                        "availableAt": None,
                        "completedAt": (
                            timestamp
                            if target_status in {"failed", "blocked", "skipped"}
                            else None
                        ),
                        "error": detail if target_status == "failed" else None,
                    },
                    event_payload=detail,
                )
                control_status = {
                    "waiting": "ready",
                    "ready": "ready",
                    "failed": "failed",
                    "blocked": "blocked",
                    "skipped": "skipped",
                }[target_status]
                self.control.runtime_transition_node(
                    organization_id=organization_id,
                    actor_principal_id=execution["requestedBy"],
                    run_id=execution["runId"],
                    node_id=job["nodeId"],
                    status=control_status,
                    execution_id=execution["id"],
                    job_id=job["id"],
                    detail=detail,
                )
                changed = True
                break
            if not changed:
                return
        raise WorkflowRuntimeConflictError("workflow runtime refresh did not converge")

    def _runtime_context_data(
        self,
        organization_id: str,
        execution: dict[str, Any],
        jobs: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        data: dict[str, dict[str, Any]] = {}
        for record in self.control.repository.list_node_data(
            organization_id,
            execution["runId"],
        ):
            node_data = data.setdefault(record["nodeId"], {})
            node_data.setdefault(record["slotKey"], record["payload"])
        artifacts: dict[str, dict[str, Any]] = {}
        for artifact in self.control.repository.list_artifacts(
            organization_id,
            execution["runId"],
            current_only=True,
        ):
            artifacts.setdefault(artifact["nodeId"], {})[artifact["artifactKey"]] = (
                artifact["content"]
                if artifact["content"] is not None
                else artifact
            )
        results = {
            job["nodeId"]: job["result"]
            for job in jobs
            if job.get("result") is not None
        }
        return data, artifacts, results

    def _execution_context(
        self,
        organization_id: str,
        execution: dict[str, Any],
        run: dict[str, Any],
        job: dict[str, Any],
    ) -> NodeExecutionContext:
        jobs = self.repository.list_jobs(organization_id, execution["id"])
        data, artifacts, results = self._runtime_context_data(
            organization_id,
            execution,
            jobs,
        )
        node = next(node for node in run["nodes"] if node["id"] == job["nodeId"])
        return NodeExecutionContext(
            organization_id=organization_id,
            execution_id=execution["id"],
            user_id=execution.get("userId") or "local-user",
            run=run,
            node=node,
            job=job,
            input=execution["input"],
            data=data,
            artifacts=artifacts,
            results=results,
        )

    @staticmethod
    def _edge_condition(
        edge: dict[str, Any],
        run: dict[str, Any],
        node_map: dict[str, dict[str, Any]],
        data: dict[str, Any],
        artifacts: dict[str, Any],
        results: dict[str, Any],
    ) -> bool:
        parameters = edge.get("parameters", {})
        context = {
            **parameters,
            "run": run,
            "node": node_map[edge["source"]],
            "target": node_map[edge["target"]],
            "data": data,
            "artifact": artifacts,
            "result": results,
            "parameters": parameters,
        }
        return evaluate_condition(edge.get("condition", ""), context)

    def _recover_expired_jobs(
        self,
        organization_id: str,
        execution: dict[str, Any],
    ) -> None:
        timestamp = self._now().isoformat()
        for job in self.repository.list_expired_jobs(
            organization_id=organization_id,
            execution_id=execution["id"],
            timestamp=timestamp,
        ):
            self._retry_or_fail_job(
                organization_id,
                execution,
                job,
                {"type": "TimeoutError", "message": "workflow node timed out"},
            )

    def _retry_or_fail_job(
        self,
        organization_id: str,
        execution: dict[str, Any],
        job: dict[str, Any],
        error: dict[str, Any],
    ) -> None:
        now = self._now()
        self._cancel_adapter_job(organization_id, execution, job)
        if job["attempt"] < job["maxAttempts"]:
            self.repository.transition_job(
                organization_id=organization_id,
                execution_id=execution["id"],
                job_id=job["id"],
                status="retry_wait",
                expected_statuses={"leased", "running", "waiting"},
                timestamp=now.isoformat(),
                fields={
                    "availableAt": (
                        now + timedelta(seconds=job["retryDelaySeconds"])
                    ).isoformat(),
                    "leaseOwner": None,
                    "leaseExpiresAt": None,
                    "startedAt": None,
                    "deadlineAt": None,
                    "result": None,
                    "error": error,
                },
                event_payload=error,
            )
            self.control.runtime_transition_node(
                organization_id=organization_id,
                actor_principal_id=execution["requestedBy"],
                run_id=execution["runId"],
                node_id=job["nodeId"],
                status="ready",
                execution_id=execution["id"],
                job_id=job["id"],
                detail={"retry": True, **error},
            )
            return
        timestamp = now.isoformat()
        self.repository.transition_job(
            organization_id=organization_id,
            execution_id=execution["id"],
            job_id=job["id"],
            status="failed",
            expected_statuses={"leased", "running", "waiting"},
            timestamp=timestamp,
            fields={
                "completedAt": timestamp,
                "leaseOwner": None,
                "leaseExpiresAt": None,
                "deadlineAt": None,
                "error": error,
            },
            event_payload=error,
        )
        self.control.runtime_transition_node(
            organization_id=organization_id,
            actor_principal_id=execution["requestedBy"],
            run_id=execution["runId"],
            node_id=job["nodeId"],
            status="failed",
            execution_id=execution["id"],
            job_id=job["id"],
            detail=error,
        )

    def _cancel_adapter_job(
        self,
        organization_id: str,
        execution: dict[str, Any],
        job: dict[str, Any],
    ) -> None:
        state = job.get("result")
        if not isinstance(state, dict):
            return
        adapter = self.adapters.require(job["executorId"])
        cancel = getattr(adapter, "cancel", None)
        if not callable(cancel):
            return
        run = self.control.repository.get_run(organization_id, execution["runId"])
        context = self._execution_context(organization_id, execution, run, job)
        try:
            cancel(context, job["input"], state)
        except Exception:
            return

    def _finalize_execution(
        self,
        organization_id: str,
        execution_id: str,
    ) -> dict[str, Any]:
        execution = self.repository.get_execution(organization_id, execution_id)
        if execution["status"] != "running":
            return self.repository.snapshot(organization_id, execution_id)
        jobs = self.repository.list_jobs(organization_id, execution_id)
        status: str | None = None
        error = None
        if any(job["status"] in {"failed", "blocked"} for job in jobs):
            status = "failed"
            error = {"message": "one or more workflow jobs failed"}
        elif jobs and all(
            job["status"] in {"completed", "cancelled", "skipped"} for job in jobs
        ):
            status = "completed"
        if status is not None:
            return self.repository.set_execution_status(
                organization_id=organization_id,
                execution_id=execution_id,
                status=status,
                expected_statuses={"running"},
                timestamp=self._now().isoformat(),
                error=error,
            )
        return self.repository.snapshot(organization_id, execution_id)


__all__ = [
    "ConditionExpressionError",
    "WorkflowRuntimeConflictError",
    "WorkflowRuntimeEngine",
]
