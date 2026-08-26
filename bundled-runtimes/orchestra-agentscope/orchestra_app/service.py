from __future__ import annotations

import asyncio
import difflib
import hashlib
import json
import logging
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from .credentials import CredentialBundle
from .engine import AgentScopeEngine, DemoEngine
from .job_queue import ClaimedJob, JobQueue, RedisJobQueue, SQLiteJobQueue
from .models import (
    AgentInterventionAction,
    AgentRuntime,
    DecisionEvent,
    EvidenceRecord,
    ExecutionMode,
    Portfolio,
    PortfolioDetail,
    PortfolioMarkInput,
    PortfolioNavSnapshot,
    PortfolioPosition,
    PortfolioSummary,
    PortfolioTransaction,
    CreatePortfolioTransactionRequest,
    RunSnapshot,
    RunSummary,
    SecretMetadata,
    UserProfile,
    utc_now,
)
from .prompts import (
    consensus_prompt,
    data_foundation_prompt,
    decision_prompt,
    pm_prompt,
    research_prompt,
)
from .registry import get_profile, load_profiles, required_skill_names
from .security import SecretVault
from .signals import extract_vote_signal
from .settings import settings
from .storage import SQLiteStore, create_store


RESEARCH_GROUPS = {"宏观组", "配置组", "股票组"}
PM_GROUP = "基金经理组"
TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
LOGGER = logging.getLogger(__name__)


@dataclass
class RunRecord:
    snapshot: RunSnapshot
    events: list[DecisionEvent] = field(default_factory=list)
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    task: asyncio.Task[None] | None = None
    interventions: dict[str, asyncio.Task[None]] = field(default_factory=dict)


class CommitteeService:
    def __init__(
        self,
        store: SQLiteStore | None = None,
        vault: SecretVault | None = None,
        queue: JobQueue | None = None,
    ) -> None:
        self.store = store or SQLiteStore(":memory:", settings.default_user_id)
        self.vault = vault
        self.queue: JobQueue = queue or (
            RedisJobQueue(settings.redis_url, settings.redis_queue_prefix)
            if settings.redis_url
            else SQLiteJobQueue(self.store)
        )
        self.queue_fallback_reason: str | None = None
        self._runs: dict[str, RunRecord] = {}
        self._shutting_down = False
        self._started = False
        self._worker_tasks: list[asyncio.Task[None]] = []
        self._queue_wakeup = asyncio.Event()
        self._instance_id = uuid.uuid4().hex[:12]
        for snapshot in self.store.load_runs(settings.max_run_history):
            self._runs[snapshot.id] = RunRecord(
                snapshot=snapshot,
                events=self.store.list_events(snapshot.id),
            )

    async def create_run(
        self,
        topic: str,
        mode: ExecutionMode,
        *,
        owner_id: str | None = None,
        portfolio_id: str | None = None,
        parent_run_id: str | None = None,
        revision_note: str = "",
        secret_refs: dict[str, str] | None = None,
    ) -> RunSnapshot:
        owner_id = owner_id or settings.default_user_id
        if self.store.get_user(owner_id) is None:
            raise PermissionError("用户不存在。")
        parent = self.get_run(parent_run_id, owner_id) if parent_run_id else None
        run_id = uuid.uuid4().hex
        now = utc_now()
        agents = {
            profile.id: AgentRuntime(id=profile.id)
            for profile in load_profiles()
        }
        snapshot = RunSnapshot(
            id=run_id,
            topic=topic,
            mode=mode,
            status="queued",
            phase="queued",
            created_at=now,
            updated_at=now,
            agents=agents,
            owner_id=owner_id,
            portfolio_id=portfolio_id,
            parent_run_id=parent_run_id,
            revision=(parent.revision + 1) if parent else 1,
            revision_note=revision_note,
            secret_refs=secret_refs or {},
        )
        record = RunRecord(snapshot=snapshot)
        self._runs[run_id] = record
        self.store.save_run(snapshot)
        await self.queue.enqueue(run_id)
        if self._started:
            self._queue_wakeup.set()
        else:
            worker_id = f"{self._instance_id}:inline"
            record.task = asyncio.create_task(self._run_inline(record, worker_id))
        return snapshot.model_copy(deep=True)

    def list_runs(
        self,
        limit: int = 20,
        owner_id: str | None = None,
    ) -> list[RunSummary]:
        return self.store.list_runs(owner_id or settings.default_user_id, limit)

    def run_metrics(self, owner_id: str | None = None) -> dict[str, int]:
        return self.store.metrics(owner_id)

    def _prune_runs(self) -> None:
        return

    def get_run(self, run_id: str | None, owner_id: str | None = None) -> RunSnapshot:
        if not run_id:
            raise KeyError(run_id)
        record = self._runs.get(run_id)
        if record is None:
            snapshot = self.store.load_run(run_id, owner_id)
            if snapshot is None:
                raise KeyError(run_id)
            record = RunRecord(snapshot=snapshot, events=self.store.list_events(run_id))
            self._runs[run_id] = record
        if owner_id is not None and record.snapshot.owner_id != owner_id:
            raise KeyError(run_id)
        return record.snapshot.model_copy(deep=True)

    def list_events(
        self,
        run_id: str,
        after: int = 0,
        owner_id: str | None = None,
    ) -> list[DecisionEvent]:
        record = self._runs.get(run_id)
        if record is None:
            self.get_run(run_id, owner_id)
            record = self._runs[run_id]
        if owner_id is not None and record.snapshot.owner_id != owner_id:
            raise KeyError(run_id)
        return [event for event in record.events if event.seq > after]

    def recent_events(
        self,
        run_id: str,
        limit: int = 600,
        owner_id: str | None = None,
    ) -> list[DecisionEvent]:
        events = self.list_events(run_id, owner_id=owner_id)
        return events[-limit:]

    def replay_events(
        self,
        run_id: str,
        owner_id: str | None = None,
    ) -> list[DecisionEvent]:
        events = self.list_events(run_id, owner_id=owner_id)
        result: list[DecisionEvent] = []
        pending_output: dict[str, tuple[DecisionEvent, str, int]] = {}
        progress_counts: dict[str, int] = {}
        output_types = {
            "agent.output.delta",
            "data.output.delta",
            "orchestra.agent.output.delta",
        }

        for event in events:
            actor = event.agent_id or event.type.split(".", 1)[0]
            if event.type in output_types:
                previous = pending_output.get(actor)
                text = (previous[1] if previous else "") + str(
                    event.payload.get("delta", ""),
                )
                count = (previous[2] if previous else 0) + 1
                pending_output[actor] = (event, text, count)
                if count >= 30:
                    result.append(
                        event.model_copy(update={"payload": {"delta": text}}),
                    )
                    pending_output.pop(actor, None)
                continue

            if event.type == "agent.progress":
                count = progress_counts.get(actor, 0) + 1
                progress_counts[actor] = count
                if count != 1 and count % 3:
                    continue
            result.append(event)

        for event, text, _ in pending_output.values():
            result.append(event.model_copy(update={"payload": {"delta": text}}))
        result.sort(key=lambda item: item.seq)
        return result

    async def startup(self) -> None:
        self._shutting_down = False
        try:
            await self.queue.start()
        except Exception as error:  # noqa: BLE001
            if isinstance(self.queue, SQLiteJobQueue):
                raise
            self.queue_fallback_reason = str(error)
            LOGGER.warning("Redis queue unavailable; falling back to SQLite: %s", error)
            self.queue = SQLiteJobQueue(self.store)
            await self.queue.start()
        self._started = True
        for snapshot in self.store.recoverable_runs():
            record = self._runs.get(snapshot.id)
            if record is None:
                record = RunRecord(snapshot=snapshot, events=self.store.list_events(snapshot.id))
                self._runs[snapshot.id] = record
            if record.task and not record.task.done():
                continue
            await self.queue.ensure(snapshot.id)
        self._worker_tasks = [
            asyncio.create_task(self._worker_loop(index))
            for index in range(settings.run_workers)
        ]
        self._queue_wakeup.set()

    async def shutdown(self) -> None:
        self._shutting_down = True
        tasks = [
            record.task
            for record in self._runs.values()
            if record.task is not None and not record.task.done()
        ]
        tasks.extend(
            task
            for record in self._runs.values()
            for task in record.interventions.values()
            if not task.done()
        )
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        deadline = asyncio.get_running_loop().time() + 3
        while any(record.task is not None for record in self._runs.values()):
            if asyncio.get_running_loop().time() >= deadline:
                break
            await asyncio.sleep(0.05)
        for worker in self._worker_tasks:
            worker.cancel()
        if self._worker_tasks:
            await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        self._worker_tasks.clear()
        await self.queue.close()
        self._started = False

    async def cancel_run(self, run_id: str, owner_id: str | None = None) -> None:
        record = self._runs.get(run_id)
        if record is None:
            self.get_run(run_id, owner_id)
            record = self._runs[run_id]
        if owner_id is not None and record.snapshot.owner_id != owner_id:
            raise KeyError(run_id)
        if record.snapshot.status in TERMINAL_STATUSES:
            return
        await self.queue.cancel(run_id)
        if record.task and not record.task.done():
            record.task.cancel()
            try:
                await record.task
            except asyncio.CancelledError:
                pass
        if record.snapshot.status not in TERMINAL_STATUSES:
            record.snapshot.status = "cancelled"
            record.snapshot.phase = "cancelled"
            await self._emit(record, "run.cancelled")

    async def start_agent_intervention(
        self,
        run_id: str,
        agent_id: str,
        owner_id: str,
        action: AgentInterventionAction,
        instruction: str,
    ) -> dict[str, str]:
        self.get_run(run_id, owner_id)
        record = self._runs[run_id]
        if record.snapshot.status not in TERMINAL_STATUSES:
            raise ValueError("主投委会执行期间不能发起单席干预。")
        if agent_id not in record.snapshot.agents:
            raise KeyError(agent_id)
        get_profile(agent_id)
        active = record.interventions.get(agent_id)
        if active is not None and not active.done():
            raise ValueError("该 Agent 已有一个干预任务在执行。")

        intervention_id = uuid.uuid4().hex
        runtime = record.snapshot.agents[agent_id]
        runtime.intervention_id = intervention_id
        runtime.intervention_action = action
        await self._emit(
            record,
            "agent.intervention.requested",
            phase="intervention",
            agent_id=agent_id,
            payload={
                "intervention_id": intervention_id,
                "action": action,
                "instruction": instruction,
            },
        )
        task = asyncio.create_task(
            self._execute_agent_intervention(
                record,
                agent_id,
                intervention_id,
                action,
                instruction,
            ),
        )
        record.interventions[agent_id] = task
        task.add_done_callback(
            lambda completed, key=agent_id, current=record: (
                current.interventions.pop(key, None)
                if current.interventions.get(key) is completed
                else None
            ),
        )
        return {
            "intervention_id": intervention_id,
            "run_id": run_id,
            "agent_id": agent_id,
            "action": action,
            "status": "queued",
        }

    async def _run_inline(self, record: RunRecord, worker_id: str) -> None:
        claimed = await self.queue.claim(worker_id, settings.job_lease_seconds)
        if claimed is None:
            raise RuntimeError("任务未能从持久化队列领取。")
        await self._process_job(claimed, worker_id, record)

    async def _worker_loop(self, index: int) -> None:
        worker_id = f"{self._instance_id}:worker-{index + 1}"
        while not self._shutting_down:
            claimed = await self.queue.claim(worker_id, settings.job_lease_seconds)
            if claimed is None:
                self._queue_wakeup.clear()
                try:
                    await asyncio.wait_for(
                        self._queue_wakeup.wait(),
                        timeout=settings.queue_poll_seconds,
                    )
                except TimeoutError:
                    pass
                continue
            await self._process_job(claimed, worker_id)

    def _reset_recovered_record(self, record: RunRecord) -> None:
        record.snapshot.status = "queued"
        record.snapshot.phase = "queued"
        record.snapshot.error = None
        record.snapshot.plan = ""
        record.snapshot.consensus = ""
        record.snapshot.decision = ""
        record.snapshot.orchestra_thinking = ""
        record.snapshot.orchestra_thinking_stage = None
        record.snapshot.agents = {
            profile.id: AgentRuntime(id=profile.id) for profile in load_profiles()
        }

    async def _process_job(
        self,
        claimed: ClaimedJob,
        worker_id: str,
        record: RunRecord | None = None,
    ) -> None:
        if record is None:
            try:
                self.get_run(claimed.run_id)
            except KeyError:
                await self.queue.fail(
                    claimed.run_id,
                    worker_id,
                    "持久化运行不存在。",
                    1,
                    0,
                )
                return
            record = self._runs[claimed.run_id]
        if record.snapshot.status in TERMINAL_STATUSES:
            if record.snapshot.status == "completed":
                await self.queue.complete(claimed.run_id, worker_id)
            else:
                await self.queue.cancel(claimed.run_id)
            return

        has_prior_execution = record.snapshot.status == "running" or any(
            event.type in {"run.started", "run.interrupted", "run.failed"}
            for event in record.events
        )
        if has_prior_execution:
            self._reset_recovered_record(record)
            await self._emit(
                record,
                "run.recovered",
                payload={
                    "reason": "从持久化任务队列重新领取",
                    "attempt": claimed.attempts,
                    "worker": worker_id,
                },
            )

        execution = asyncio.create_task(self._execute(record))
        record.task = execution
        heartbeat = asyncio.create_task(
            self._lease_heartbeat(claimed.run_id, worker_id, execution),
        )
        try:
            outcome = await execution
            if outcome == "completed":
                await self.queue.complete(claimed.run_id, worker_id)
            elif outcome == "failed":
                retry_delay = settings.job_retry_base_seconds * (2 ** max(0, claimed.attempts - 1))
                queue_status = await self.queue.fail(
                    claimed.run_id,
                    worker_id,
                    record.snapshot.error or "运行失败",
                    settings.job_max_attempts,
                    retry_delay,
                )
                if queue_status == "queued":
                    self._queue_wakeup.set()
            else:
                await self.queue.cancel(claimed.run_id)
        except asyncio.CancelledError:
            if self._shutting_down:
                await self.queue.release(claimed.run_id, worker_id)
            else:
                await self.queue.cancel(claimed.run_id)
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
            if record.task is execution:
                record.task = None

    async def _lease_heartbeat(
        self,
        run_id: str,
        worker_id: str,
        execution: asyncio.Task[str],
    ) -> None:
        interval = max(1, settings.job_lease_seconds // 3)
        while not execution.done():
            await asyncio.sleep(interval)
            renewed = await self.queue.renew(
                run_id,
                worker_id,
                settings.job_lease_seconds,
            )
            if not renewed and not execution.done():
                execution.cancel()
                return

    async def queue_stats(self) -> dict[str, Any]:
        return {
            **await self.queue.stats(),
            "workers": settings.run_workers,
            "lease_seconds": settings.job_lease_seconds,
            "max_attempts": settings.job_max_attempts,
            "fallback_reason": self.queue_fallback_reason,
        }

    async def list_queue_jobs(self, limit: int = 50) -> list[dict[str, Any]]:
        return await self.queue.list_jobs(limit)

    async def stream(self, run_id: str, after: int = 0, owner_id: str | None = None):
        record = self._runs.get(run_id)
        if record is None:
            self.get_run(run_id, owner_id)
            record = self._runs[run_id]
        if owner_id is not None and record.snapshot.owner_id != owner_id:
            raise KeyError(run_id)
        cursor = after
        while True:
            pending = [event for event in record.events if event.seq > cursor]
            for event in pending:
                cursor = event.seq
                payload = event.model_dump_json()
                yield f"id: {event.seq}\nevent: {event.type}\ndata: {payload}\n\n"
            if (
                record.snapshot.status in TERMINAL_STATUSES
                and not any(not task.done() for task in record.interventions.values())
                and cursor >= record.snapshot.last_event_seq
            ):
                break
            try:
                async with record.condition:
                    await asyncio.wait_for(record.condition.wait(), timeout=12)
            except TimeoutError:
                yield ": keepalive\n\n"

    async def _emit(
        self,
        record: RunRecord,
        event_type: str,
        *,
        phase: str | None = None,
        agent_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        event = DecisionEvent(
            id=uuid.uuid4().hex,
            run_id=record.snapshot.id,
            seq=record.snapshot.last_event_seq + 1,
            type=event_type,
            phase=phase,
            agent_id=agent_id,
            payload=payload or {},
        )
        record.events.append(event)
        record.snapshot.last_event_seq = event.seq
        record.snapshot.updated_at = event.created_at
        self.store.append_event(event, record.snapshot)
        async with record.condition:
            record.condition.notify_all()

    async def _set_phase(self, record: RunRecord, phase: str, label: str) -> None:
        record.snapshot.phase = phase
        await self._emit(
            record,
            "phase.started",
            phase=phase,
            payload={"label": label},
        )

    async def _execute(self, record: RunRecord) -> str:
        record.snapshot.agents = {
            agent_id: AgentRuntime(id=agent_id)
            for agent_id in record.snapshot.agents
        }
        record.snapshot.plan = ""
        record.snapshot.consensus = ""
        record.snapshot.decision = ""
        record.snapshot.orchestra_thinking = ""
        record.snapshot.orchestra_thinking_stage = None
        record.snapshot.error = None
        record.snapshot.status = "running"
        await self._emit(record, "run.started", payload={"mode": record.snapshot.mode})
        try:
            engine = (
                DemoEngine()
                if record.snapshot.mode == "demo"
                else AgentScopeEngine(self._credential_bundle(record.snapshot))
            )

            await self._set_phase(record, "planning", "议题拆解")
            record.snapshot.plan = (
                "宏观组、配置组和股票组先独立研究；基金经理组读取研究包后完成质询与投票；"
                "最后由 Orchestra 收敛分歧并形成决议。"
            )
            await self._emit(
                record,
                "orchestra.plan",
                phase="planning",
                payload={"plan": record.snapshot.plan},
            )

            await self._emit(
                record,
                "data.foundation.started",
                phase="planning",
                payload={
                    "sources": [
                        "Tushare Pro",
                        "A Stock Data",
                        "Global Stock Data",
                        "Tavily",
                        "IMA Knowledge Base",
                    ],
                },
            )
            if record.snapshot.mode == "demo":
                evidence_pack = (
                    "【数据基座】演示模式不调用真实接口。切换 live 模式后，系统会先建立"
                    " Tushare、A Stock、Global Stock、Tavily 与 IMA 三端证据包。"
                )
            else:
                try:
                    evidence_pack = await self._run_data_foundation(
                        record,
                        engine,
                        data_foundation_prompt(record.snapshot.topic),
                    )
                except Exception as error:  # noqa: BLE001
                    evidence_pack = f"【数据基座失败】{error}。所有席位必须把该缺口计入置信度。"
                    await self._emit(
                        record,
                        "data.foundation.failed",
                        phase="planning",
                        payload={"error": str(error)},
                    )
            self.store.save_artifact(
                record.snapshot.id,
                "data_foundation",
                "共享数据基座证据包",
                evidence_pack,
                record.snapshot.revision,
                "DATA-FOUNDATION",
            )
            await self._emit(
                record,
                "data.foundation.completed",
                phase="planning",
                payload={"characters": len(evidence_pack)},
            )
            await asyncio.sleep(settings.demo_delay)
            await self._emit(record, "phase.completed", phase="planning")

            research_profiles = [p for p in load_profiles() if p.group in RESEARCH_GROUPS]
            await self._set_phase(record, "research", "独立研究")
            research_outputs = await self._run_profiles(
                record,
                engine,
                research_profiles,
                "research",
                lambda profile: research_prompt(
                    record.snapshot.topic,
                    profile,
                    evidence_pack,
                ),
            )
            await self._emit(record, "phase.completed", phase="research")

            research_pack = self._format_pack(research_outputs)
            pm_profiles = [p for p in load_profiles() if p.group == PM_GROUP]
            await self._set_phase(record, "deliberation", "经理审议")
            pm_outputs = await self._run_profiles(
                record,
                engine,
                pm_profiles,
                "deliberation",
                lambda profile: pm_prompt(
                    record.snapshot.topic,
                    profile,
                    research_pack,
                    evidence_pack,
                ),
            )
            await self._emit(record, "phase.completed", phase="deliberation")

            all_outputs = {**research_outputs, **pm_outputs}
            full_pack = self._format_pack(all_outputs)
            await self._set_phase(record, "convergence", "分歧收敛")
            if record.snapshot.mode == "demo":
                record.snapshot.consensus = (
                    "【共识】多席位协作链路、分组研究与经理审议已完成。\n"
                    "【主要分歧】当前推演未调用真实数据，不能形成真实投资判断。\n"
                    "【需要主席裁决的事项】切换 live 模式并核验数据后再审议。\n"
                    "【关键少数意见】数据缺失本身应触发风险否决。"
                )
            else:
                record.snapshot.consensus = await self._run_orchestra_agent(
                    record,
                    engine,
                    consensus_prompt(record.snapshot.topic, full_pack),
                    "convergence",
                )
            await self._emit(
                record,
                "orchestra.consensus",
                phase="convergence",
                payload={"consensus": record.snapshot.consensus},
            )
            self.store.save_artifact(
                record.snapshot.id,
                "consensus",
                "分歧收敛纪要",
                record.snapshot.consensus,
                record.snapshot.revision,
            )
            await self._emit(record, "phase.completed", phase="convergence")

            await self._set_phase(record, "decision", "主席决议")
            if record.snapshot.mode == "demo":
                record.snapshot.decision = (
                    f"【议题】{record.snapshot.topic}\n"
                    "【共识】常设研究席位、个性化 Skills 注入和四阶段事件流运行正常。\n"
                    "【分歧】当前推演不包含真实金融数据。\n"
                    "【决策】系统验收通过；真实投资决策需使用 live 模式。\n"
                    "【风险预算】当前推演不建立真实仓位。\n"
                    "【待验证指标】LLM连通性、Skills可用率、Tushare/Tavily/IMA工具返回。\n"
                    "【下次审议条件】完成真实数据工具接入后。"
                )
            else:
                record.snapshot.decision = await self._run_orchestra_agent(
                    record,
                    engine,
                    decision_prompt(
                        record.snapshot.topic,
                        full_pack,
                        record.snapshot.consensus,
                    ),
                    "decision",
                )
            await self._emit(
                record,
                "orchestra.decision",
                phase="decision",
                payload={"decision": record.snapshot.decision},
            )
            self.store.save_artifact(
                record.snapshot.id,
                "decision",
                "正式投委会决议",
                record.snapshot.decision,
                record.snapshot.revision,
            )
            await self._emit(record, "phase.completed", phase="decision")
            record.snapshot.status = "completed"
            record.snapshot.phase = "completed"
            await self._emit(record, "run.completed")
            return "completed"
        except asyncio.CancelledError:
            if self._shutting_down:
                record.snapshot.status = "queued"
                record.snapshot.phase = "queued"
                await self._emit(
                    record,
                    "run.interrupted",
                    payload={"reason": "服务关闭，任务已回到持久化队列"},
                )
            else:
                record.snapshot.status = "cancelled"
                record.snapshot.phase = "cancelled"
                await self._emit(record, "run.cancelled")
            raise
        except Exception as error:  # noqa: BLE001
            record.snapshot.status = "failed"
            record.snapshot.phase = "failed"
            record.snapshot.error = str(error)
            await self._emit(record, "run.failed", payload={"error": str(error)})
            return "failed"

    async def _run_profiles(
        self,
        record: RunRecord,
        engine: DemoEngine | AgentScopeEngine,
        profiles,
        phase: str,
        prompt_factory,
    ) -> dict[str, str]:
        semaphore = asyncio.Semaphore(settings.max_concurrency)
        outputs: dict[str, str] = {}

        async def run_one(profile) -> None:
            runtime = record.snapshot.agents[profile.id]
            runtime.required_skills = required_skill_names(profile)
            await self._emit(
                record,
                "agent.skill.required",
                phase=phase,
                agent_id=profile.id,
                payload={"skills": runtime.required_skills},
            )
            runtime.status = "queued"
            runtime.phase = phase
            await self._emit(record, "agent.queued", phase=phase, agent_id=profile.id)
            async with semaphore:
                runtime.status = "working"
                runtime.started_at = utc_now()
                await self._emit(record, "agent.started", phase=phase, agent_id=profile.id)

                async def emit_agent(event_type: str, payload: dict[str, Any]) -> None:
                    if event_type == "agent.output.delta":
                        runtime.output += str(payload.get("delta", ""))
                    if event_type == "agent.thinking":
                        summary = str(payload.get("summary", ""))
                        runtime.thinking = summary
                        runtime.thinking_stage = str(payload.get("stage", "")) or None
                        if summary and (not runtime.thoughts or runtime.thoughts[-1] != summary):
                            runtime.thoughts = [*runtime.thoughts[-3:], summary]
                    if event_type == "agent.tool.started":
                        tool = str(payload.get("tool", ""))
                        if tool and tool not in runtime.tools:
                            runtime.tools.append(tool)
                    if event_type == "agent.skill.registered":
                        skill = str(payload.get("skill", ""))
                        if skill and skill not in runtime.registered_skills:
                            runtime.registered_skills.append(skill)
                    if event_type == "agent.skill.used":
                        skill = str(payload.get("skill", ""))
                        if skill and skill not in runtime.used_skills:
                            runtime.used_skills.append(skill)
                    if event_type == "agent.evidence.recorded":
                        evidence = EvidenceRecord.model_validate(payload)
                        if all(item.id != evidence.id for item in runtime.evidence):
                            runtime.evidence.append(evidence)
                            self.store.save_evidence(
                                record.snapshot.id,
                                profile.id,
                                evidence,
                            )
                    await self._emit(
                        record,
                        event_type,
                        phase=phase,
                        agent_id=profile.id,
                        payload=payload,
                    )

                started = asyncio.get_running_loop().time()

                async def emit_progress() -> None:
                    while runtime.status == "working":
                        await asyncio.sleep(settings.agent_progress_interval)
                        if runtime.status != "working":
                            break
                        await emit_agent(
                            "agent.progress",
                            {
                                "elapsed_seconds": round(
                                    asyncio.get_running_loop().time() - started,
                                    1,
                                ),
                                "stage": runtime.thinking_stage or "working",
                                "summary": runtime.thinking or "执行角色专属研究与证据核验",
                                "evidence_count": len(runtime.evidence),
                                "output_chars": len(runtime.output),
                                "used_skills": runtime.used_skills,
                            },
                        )

                progress_task = asyncio.create_task(emit_progress())

                try:
                    output = await engine.run_agent(
                        profile,
                        prompt_factory(profile),
                        phase,
                        emit_agent,
                    )
                    runtime.output = output
                    runtime.status = "completed"
                    runtime.completed_at = utc_now()
                    outputs[profile.id] = output
                    if phase == "deliberation":
                        vote_signal = extract_vote_signal(output)
                        if vote_signal:
                            await self._emit(
                                record,
                                "agent.vote.recorded",
                                phase=phase,
                                agent_id=profile.id,
                                payload=dict(vote_signal),
                            )
                    await self._emit(
                        record,
                        "agent.completed",
                        phase=phase,
                        agent_id=profile.id,
                        payload={"output": output},
                    )
                    self.store.save_artifact(
                        record.snapshot.id,
                        f"{phase}_report",
                        f"{profile.id} {profile.name} 阶段成果",
                        output,
                        record.snapshot.revision,
                        profile.id,
                    )
                except Exception as error:  # noqa: BLE001
                    runtime.status = "failed"
                    runtime.error = str(error)
                    runtime.completed_at = utc_now()
                    outputs[profile.id] = f"执行失败：{error}"
                    await self._emit(
                        record,
                        "agent.failed",
                        phase=phase,
                        agent_id=profile.id,
                        payload={"error": str(error)},
                    )
                finally:
                    progress_task.cancel()
                    await asyncio.gather(progress_task, return_exceptions=True)

        await asyncio.gather(*(run_one(profile) for profile in profiles))
        return outputs

    async def _execute_agent_intervention(
        self,
        record: RunRecord,
        agent_id: str,
        intervention_id: str,
        action: AgentInterventionAction,
        instruction: str,
    ) -> None:
        profile = get_profile(agent_id)
        runtime = record.snapshot.agents[agent_id]
        artifacts = self.store.list_artifacts(record.snapshot.id)
        prior_reports = [
            item
            for item in artifacts
            if item.get("agent_id") == agent_id and str(item.get("content", "")).strip()
        ]
        foundation_reports = [
            item for item in artifacts if item.get("kind") == "data_foundation"
        ]
        prior_report = str(prior_reports[-1]["content"]) if prior_reports else runtime.output
        evidence_pack = (
            str(foundation_reports[-1]["content"])
            if foundation_reports
            else "未找到已持久化的共享数据基座报告。"
        )
        action_labels = {
            "follow_up": "追问",
            "supplement": "补充数据",
            "rereview": "重新审视",
        }
        action_requirements = {
            "follow_up": (
                "直接回答追问，逐项区分已知事实、分析判断与待核验项；"
                "不要重写原报告。"
            ),
            "supplement": (
                "优先调用角色已配置的数据工具与 Skills 取得增量证据，"
                "列出新数据、来源、日期、参数及它对原结论的影响。"
            ),
            "rereview": (
                "从反方视角重新审视原报告，明确保留、修正或撤回的结论，"
                "给出变化前后的观点、置信度和反证条件。"
            ),
        }
        prompt = (
            f"【人类干预任务】{action_labels[action]}\n"
            f"【原始议题】{record.snapshot.topic}\n"
            f"【用户指令】{instruction}\n"
            f"【执行要求】{action_requirements[action]}\n\n"
            "【本席已有报告】\n"
            f"{prior_report or '本席尚未生成报告。'}\n\n"
            "【共享数据基座】\n"
            f"{evidence_pack}\n\n"
            "输出 Markdown 增量报告。必须保持本角色边界，标注证据与推断的区别，"
            "并在结尾给出《结论变化》《新增证据》《未解问题》。"
        )

        runtime.status = "working"
        runtime.phase = "intervention"
        runtime.output = ""
        runtime.thinking = "读取人类干预指令与已有报告"
        runtime.thinking_stage = "framing"
        runtime.thoughts = [*runtime.thoughts[-3:], runtime.thinking]
        runtime.tools = []
        runtime.required_skills = required_skill_names(profile)
        runtime.registered_skills = []
        runtime.used_skills = []
        runtime.started_at = utc_now()
        runtime.completed_at = None
        runtime.error = None
        await self._emit(
            record,
            "agent.intervention.started",
            phase="intervention",
            agent_id=agent_id,
            payload={
                "intervention_id": intervention_id,
                "action": action,
                "required_skills": runtime.required_skills,
            },
        )

        engine = (
            DemoEngine()
            if record.snapshot.mode == "demo"
            else AgentScopeEngine(self._credential_bundle(record.snapshot))
        )

        async def emit_agent(event_type: str, payload: dict[str, Any]) -> None:
            if event_type == "agent.output.delta":
                runtime.output += str(payload.get("delta", ""))
            if event_type == "agent.thinking":
                summary = str(payload.get("summary", ""))
                runtime.thinking = summary
                runtime.thinking_stage = str(payload.get("stage", "")) or None
                if summary and (not runtime.thoughts or runtime.thoughts[-1] != summary):
                    runtime.thoughts = [*runtime.thoughts[-3:], summary]
            if event_type == "agent.tool.started":
                tool = str(payload.get("tool", ""))
                if tool and tool not in runtime.tools:
                    runtime.tools.append(tool)
            if event_type == "agent.skill.registered":
                skill = str(payload.get("skill", ""))
                if skill and skill not in runtime.registered_skills:
                    runtime.registered_skills.append(skill)
            if event_type == "agent.skill.used":
                skill = str(payload.get("skill", ""))
                if skill and skill not in runtime.used_skills:
                    runtime.used_skills.append(skill)
            if event_type == "agent.evidence.recorded":
                evidence = EvidenceRecord.model_validate(payload)
                if all(item.id != evidence.id for item in runtime.evidence):
                    runtime.evidence.append(evidence)
                    self.store.save_evidence(record.snapshot.id, agent_id, evidence)
            await self._emit(
                record,
                event_type,
                phase="intervention",
                agent_id=agent_id,
                payload={**payload, "intervention_id": intervention_id},
            )

        started = asyncio.get_running_loop().time()

        async def emit_progress() -> None:
            while runtime.status == "working":
                await asyncio.sleep(settings.agent_progress_interval)
                if runtime.status != "working":
                    break
                await emit_agent(
                    "agent.progress",
                    {
                        "elapsed_seconds": round(
                            asyncio.get_running_loop().time() - started,
                            1,
                        ),
                        "stage": runtime.thinking_stage or "working",
                        "summary": runtime.thinking or "执行单席增量研究",
                        "evidence_count": len(runtime.evidence),
                        "output_chars": len(runtime.output),
                        "used_skills": runtime.used_skills,
                    },
                )

        progress_task = asyncio.create_task(emit_progress())
        try:
            output = await engine.run_agent(
                profile,
                prompt,
                "intervention",
                emit_agent,
            )
            runtime.output = output
            runtime.status = "completed"
            runtime.completed_at = utc_now()
            artifact_kind = "intervention_report"
            artifact_version = 1 + max(
                (
                    int(item.get("version", 0))
                    for item in self.store.list_artifacts(record.snapshot.id)
                    if item.get("agent_id") == agent_id
                    and item.get("kind") == artifact_kind
                ),
                default=0,
            )
            title = f"{profile.id} {profile.name} · {action_labels[action]}"
            self.store.save_artifact(
                record.snapshot.id,
                artifact_kind,
                title,
                output,
                artifact_version,
                agent_id,
            )
            if profile.group == PM_GROUP:
                vote_signal = extract_vote_signal(output)
                if vote_signal:
                    await self._emit(
                        record,
                        "agent.vote.recorded",
                        phase="intervention",
                        agent_id=agent_id,
                        payload={**dict(vote_signal), "intervention_id": intervention_id},
                    )
            await self._emit(
                record,
                "agent.intervention.completed",
                phase="intervention",
                agent_id=agent_id,
                payload={
                    "intervention_id": intervention_id,
                    "action": action,
                    "output": output,
                    "artifact_kind": artifact_kind,
                    "artifact_version": artifact_version,
                },
            )
        except asyncio.CancelledError:
            runtime.status = "failed"
            runtime.error = "服务关闭导致单席干预中断，请手动重新发起。"
            runtime.completed_at = utc_now()
            await self._emit(
                record,
                "agent.intervention.failed",
                phase="intervention",
                agent_id=agent_id,
                payload={
                    "intervention_id": intervention_id,
                    "action": action,
                    "error": runtime.error,
                    "interrupted": True,
                },
            )
            raise
        except Exception as error:  # noqa: BLE001
            runtime.status = "failed"
            runtime.error = str(error)
            runtime.completed_at = utc_now()
            await self._emit(
                record,
                "agent.intervention.failed",
                phase="intervention",
                agent_id=agent_id,
                payload={
                    "intervention_id": intervention_id,
                    "action": action,
                    "error": str(error),
                },
            )
        finally:
            progress_task.cancel()
            await asyncio.gather(progress_task, return_exceptions=True)

    async def _run_orchestra_agent(
        self,
        record: RunRecord,
        engine: AgentScopeEngine,
        prompt: str,
        phase: str,
    ) -> str:
        async def emit(event_type: str, payload: dict[str, Any]) -> None:
            if event_type == "agent.thinking":
                record.snapshot.orchestra_thinking = str(payload.get("summary", ""))
                record.snapshot.orchestra_thinking_stage = (
                    str(payload.get("stage", "")) or None
                )
            await self._emit(record, f"orchestra.{event_type}", phase=phase, payload=payload)

        return await engine.run_orchestra(prompt, emit)

    async def _run_data_foundation(
        self,
        record: RunRecord,
        engine: AgentScopeEngine,
        prompt: str,
    ) -> str:
        async def emit(event_type: str, payload: dict[str, Any]) -> None:
            normalized_type = event_type.removeprefix("agent.")
            if event_type == "agent.evidence.recorded":
                evidence = EvidenceRecord.model_validate(payload)
                self.store.save_evidence(record.snapshot.id, "DATA-FOUNDATION", evidence)
            await self._emit(
                record,
                f"data.{normalized_type}",
                phase="planning",
                agent_id="DATA-FOUNDATION",
                payload=payload,
            )

        return await engine.run_data_foundation(prompt, emit)

    @staticmethod
    def _format_pack(outputs: dict[str, str]) -> str:
        parts = []
        for agent_id, output in outputs.items():
            profile = get_profile(agent_id)
            parts.append(f"--- {profile.id} {profile.name} ---\n{output}")
        return "\n\n".join(parts)

    def _credential_bundle(self, snapshot: RunSnapshot) -> CredentialBundle:
        defaults = CredentialBundle.from_settings()
        agent_secrets: dict[str, str] = {}
        values = {
            "openai": defaults.openai_api_key,
            "tushare": defaults.tushare_token,
            "tavily": defaults.tavily_api_key,
            "ima_client_id": defaults.ima_client_id,
            "ima_api_key": defaults.ima_api_key,
        }
        if snapshot.secret_refs:
            if self.vault is None:
                raise RuntimeError("当前服务未配置用户密钥保险箱。")
            for provider, secret_id in snapshot.secret_refs.items():
                stored = self.store.get_secret_ciphertext(secret_id, snapshot.owner_id)
                if stored is None or stored[0] != provider:
                    raise PermissionError(f"无权使用 {provider} 密钥。")
                decrypted = self.vault.decrypt(stored[1])
                if provider == "ima":
                    try:
                        ima_secret = json.loads(decrypted)
                        values["ima_client_id"] = str(ima_secret["client_id"])
                        values["ima_api_key"] = str(ima_secret["api_key"])
                    except (json.JSONDecodeError, KeyError, TypeError) as error:
                        raise ValueError(
                            "IMA 密钥需保存为包含 client_id 与 api_key 的 JSON。",
                        ) from error
                else:
                    values[provider] = decrypted
        if self.vault is not None:
            for profile in load_profiles():
                secret_id = profile.connection.secret_id
                if not secret_id or secret_id in agent_secrets:
                    continue
                stored = self.store.get_secret_ciphertext(secret_id, snapshot.owner_id)
                if stored is not None and stored[0] in {"agent", "openai"}:
                    agent_secrets[secret_id] = self.vault.decrypt(stored[1])
        return CredentialBundle(
            openai_api_key=values["openai"],
            openai_base_url=defaults.openai_base_url,
            openai_model=defaults.openai_model,
            tushare_token=values["tushare"],
            tavily_api_key=values["tavily"],
            ima_client_id=values["ima_client_id"],
            ima_api_key=values["ima_api_key"],
            agent_secrets=agent_secrets,
        )

    def list_artifacts(self, run_id: str, owner_id: str) -> list[dict[str, Any]]:
        self.get_run(run_id, owner_id)
        return self.store.list_artifacts(run_id)

    def list_evidence(self, run_id: str, owner_id: str) -> list[dict[str, Any]]:
        self.get_run(run_id, owner_id)
        return self.store.list_evidence(run_id)

    async def reconsider_run(
        self,
        run_id: str,
        owner_id: str,
        note: str,
        mode: ExecutionMode | None = None,
    ) -> RunSnapshot:
        parent = self.get_run(run_id, owner_id)
        return await self.create_run(
            parent.topic,
            mode or parent.mode,
            owner_id=owner_id,
            portfolio_id=parent.portfolio_id,
            parent_run_id=parent.id,
            revision_note=note,
            secret_refs=parent.secret_refs,
        )

    def compare_runs(self, run_ids: list[str], owner_id: str) -> dict[str, Any]:
        snapshots = [self.get_run(run_id, owner_id) for run_id in run_ids]
        base = snapshots[0]
        comparisons = []
        for snapshot in snapshots[1:]:
            comparisons.append(
                {
                    "base_run_id": base.id,
                    "target_run_id": snapshot.id,
                    "decision_diff": list(
                        difflib.unified_diff(
                            base.decision.splitlines(),
                            snapshot.decision.splitlines(),
                            fromfile=f"{base.id}:v{base.revision}",
                            tofile=f"{snapshot.id}:v{snapshot.revision}",
                            lineterm="",
                        ),
                    ),
                    "consensus_changed": base.consensus != snapshot.consensus,
                    "evidence_delta": sum(
                        len(runtime.evidence) for runtime in snapshot.agents.values()
                    )
                    - sum(len(runtime.evidence) for runtime in base.agents.values()),
                },
            )
        return {
            "runs": [
                {
                    "id": snapshot.id,
                    "topic": snapshot.topic,
                    "revision": snapshot.revision,
                    "status": snapshot.status,
                    "updated_at": snapshot.updated_at,
                    "decision": snapshot.decision,
                }
                for snapshot in snapshots
            ],
            "comparisons": comparisons,
        }

    def current_user(self, user_id: str) -> UserProfile:
        user = self.store.get_user(user_id)
        if user is None:
            raise KeyError(user_id)
        return user

    def list_users(self) -> list[UserProfile]:
        return self.store.list_users()

    def create_user(self, name: str, role: str) -> tuple[UserProfile, str]:
        api_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(api_token.encode("utf-8")).hexdigest()
        return self.store.create_user(name, role, token_hash), api_token

    def verify_user_token(self, user_id: str, api_token: str) -> bool:
        token_hash = hashlib.sha256(api_token.encode("utf-8")).hexdigest()
        return self.store.verify_user_token(user_id, token_hash)

    def create_session(self, user_id: str, api_token: str) -> tuple[UserProfile, str, str]:
        if not self.verify_user_token(user_id, api_token):
            raise PermissionError("用户令牌无效。")
        user = self.current_user(user_id)
        session_token = secrets.token_urlsafe(48)
        token_hash = hashlib.sha256(session_token.encode("utf-8")).hexdigest()
        expires_at = (
            datetime.now(timezone.utc) + timedelta(seconds=settings.session_ttl_seconds)
        ).isoformat()
        self.store.create_session(user_id, token_hash, expires_at)
        return user, session_token, expires_at

    def authenticate_session(self, session_token: str) -> UserProfile | None:
        token_hash = hashlib.sha256(session_token.encode("utf-8")).hexdigest()
        return self.store.get_session_user(token_hash)

    def revoke_session(self, session_token: str) -> bool:
        token_hash = hashlib.sha256(session_token.encode("utf-8")).hexdigest()
        return self.store.delete_session(token_hash)

    def list_portfolios(self, owner_id: str) -> list[Portfolio]:
        return self.store.list_portfolios(owner_id)

    def create_portfolio(
        self,
        owner_id: str,
        name: str,
        description: str,
        base_currency: str,
    ) -> Portfolio:
        return self.store.create_portfolio(owner_id, name, description, base_currency)

    def _calculate_portfolio(
        self,
        portfolio: Portfolio,
        transactions: list[PortfolioTransaction],
        as_of: date,
    ) -> tuple[PortfolioSummary, list[PortfolioPosition]]:
        zero = Decimal("0")
        cash = zero
        income = zero
        fees_total = zero
        realized_total = zero
        states: dict[str, dict[str, Any]] = {}

        for transaction in sorted(
            (item for item in transactions if item.trade_date <= as_of),
            key=lambda item: (item.trade_date, item.created_at, item.id),
        ):
            if transaction.currency != portfolio.base_currency:
                raise ValueError("当前组合账本仅支持以组合本位币记账。")
            kind = transaction.transaction_type
            if kind == "cash_in":
                cash += transaction.amount
                continue
            if kind == "cash_out":
                cash -= transaction.amount
                continue
            if kind in {"dividend", "interest"}:
                cash += transaction.amount
                income += transaction.amount
                continue
            if kind == "fee":
                cash -= transaction.amount
                fees_total += transaction.amount
                realized_total -= transaction.amount
                continue

            state = states.setdefault(
                transaction.asset_code,
                {
                    "asset_name": transaction.asset_name,
                    "asset_class": transaction.asset_class,
                    "currency": transaction.currency,
                    "quantity": zero,
                    "average_cost": zero,
                    "last_price": transaction.price,
                    "realized_pnl": zero,
                },
            )
            state["asset_name"] = transaction.asset_name or state["asset_name"]
            state["asset_class"] = transaction.asset_class
            state["last_price"] = transaction.price
            fees_total += transaction.fees

            if kind == "buy":
                previous_cost = state["quantity"] * state["average_cost"]
                next_quantity = state["quantity"] + transaction.quantity
                state["average_cost"] = (
                    previous_cost + transaction.amount + transaction.fees
                ) / next_quantity
                state["quantity"] = next_quantity
                cash -= transaction.amount + transaction.fees
                continue

            if transaction.quantity > state["quantity"]:
                raise ValueError(f"{transaction.asset_code} 卖出数量超过可用持仓。")
            realized = (
                (transaction.price - state["average_cost"]) * transaction.quantity
                - transaction.fees
            )
            state["quantity"] -= transaction.quantity
            state["realized_pnl"] += realized
            realized_total += realized
            cash += transaction.amount - transaction.fees
            if state["quantity"] == zero:
                state["average_cost"] = zero

        latest_marks: dict[str, Decimal] = {}
        for mark in self.store.list_portfolio_marks(portfolio.id):
            if mark["asset_code"] in latest_marks or mark["as_of"] > as_of.isoformat():
                continue
            latest_marks[mark["asset_code"]] = Decimal(mark["price"])

        positions: list[PortfolioPosition] = []
        market_value = zero
        total_cost = zero
        unrealized_total = zero
        for asset_code, state in states.items():
            if state["quantity"] <= zero:
                continue
            last_price = latest_marks.get(asset_code, state["last_price"])
            value = state["quantity"] * last_price
            cost_value = state["quantity"] * state["average_cost"]
            unrealized = value - cost_value
            positions.append(
                PortfolioPosition(
                    asset_code=asset_code,
                    asset_name=state["asset_name"],
                    asset_class=state["asset_class"],
                    currency=state["currency"],
                    quantity=state["quantity"],
                    average_cost=state["average_cost"],
                    last_price=last_price,
                    market_value=value,
                    cost_value=cost_value,
                    unrealized_pnl=unrealized,
                    realized_pnl=state["realized_pnl"],
                ),
            )
            market_value += value
            total_cost += cost_value
            unrealized_total += unrealized

        positions.sort(key=lambda item: abs(item.market_value), reverse=True)
        summary = PortfolioSummary(
            as_of=as_of,
            currency=portfolio.base_currency,
            cash_balance=cash,
            market_value=market_value,
            net_asset_value=cash + market_value,
            total_cost=total_cost,
            gross_exposure=sum((abs(item.market_value) for item in positions), zero),
            unrealized_pnl=unrealized_total,
            realized_pnl=realized_total,
            income=income,
            fees=fees_total,
            position_count=len(positions),
        )
        return summary, positions

    def get_portfolio_detail(self, portfolio_id: str, owner_id: str) -> PortfolioDetail:
        portfolio = self.store.get_portfolio(portfolio_id, owner_id)
        if portfolio is None:
            raise KeyError(portfolio_id)
        transactions = self.store.list_portfolio_transactions(portfolio_id)
        summary, positions = self._calculate_portfolio(portfolio, transactions, date.today())
        return PortfolioDetail(
            portfolio=portfolio,
            summary=summary,
            positions=positions,
            transactions=list(reversed(transactions[-100:])),
            nav_history=self.store.list_nav_snapshots(portfolio_id),
        )

    def create_portfolio_transaction(
        self,
        portfolio_id: str,
        owner_id: str,
        request: CreatePortfolioTransactionRequest,
    ) -> PortfolioTransaction:
        portfolio = self.store.get_portfolio(portfolio_id, owner_id)
        if portfolio is None:
            raise KeyError(portfolio_id)
        currency = request.currency.upper()
        if currency != portfolio.base_currency:
            raise ValueError("当前组合账本仅支持以组合本位币记账。")
        transaction = PortfolioTransaction(
            id=uuid.uuid4().hex,
            portfolio_id=portfolio_id,
            trade_date=request.trade_date,
            transaction_type=request.transaction_type,
            asset_code=request.asset_code.strip().upper(),
            asset_name=request.asset_name.strip(),
            asset_class=request.asset_class,
            quantity=request.quantity,
            price=request.price,
            amount=request.amount,
            fees=request.fees,
            currency=currency,
            notes=request.notes.strip(),
            created_at=utc_now(),
        )
        existing = self.store.list_portfolio_transactions(portfolio_id)
        self._calculate_portfolio(portfolio, [*existing, transaction], request.trade_date)
        self.store.create_portfolio_transaction(transaction)
        summary, _ = self._calculate_portfolio(
            portfolio,
            [*existing, transaction],
            request.trade_date,
        )
        self._save_nav_snapshot(portfolio_id, summary, None, "交易后自动快照")
        return transaction

    def _save_nav_snapshot(
        self,
        portfolio_id: str,
        summary: PortfolioSummary,
        unit_count: Decimal | None,
        note: str,
    ) -> PortfolioNavSnapshot:
        if unit_count is None:
            history = self.store.list_nav_snapshots(portfolio_id, 1)
            unit_count = history[0].unit_count if history else None
        snapshot = PortfolioNavSnapshot(
            id=uuid.uuid4().hex,
            portfolio_id=portfolio_id,
            as_of=summary.as_of,
            cash_balance=summary.cash_balance,
            market_value=summary.market_value,
            net_asset_value=summary.net_asset_value,
            unit_count=unit_count,
            unit_nav=(summary.net_asset_value / unit_count) if unit_count else None,
            total_cost=summary.total_cost,
            unrealized_pnl=summary.unrealized_pnl,
            realized_pnl=summary.realized_pnl,
            note=note,
            created_at=utc_now(),
        )
        return self.store.save_nav_snapshot(snapshot)

    def create_portfolio_valuation(
        self,
        portfolio_id: str,
        owner_id: str,
        as_of: date,
        marks: list[PortfolioMarkInput],
        unit_count: Decimal | None,
        note: str,
    ) -> PortfolioNavSnapshot:
        portfolio = self.store.get_portfolio(portfolio_id, owner_id)
        if portfolio is None:
            raise KeyError(portfolio_id)
        transactions = self.store.list_portfolio_transactions(portfolio_id)
        _, positions = self._calculate_portfolio(portfolio, transactions, as_of)
        position_codes = {position.asset_code for position in positions}
        unknown_codes = {mark.asset_code.strip().upper() for mark in marks} - position_codes
        if unknown_codes:
            raise ValueError(f"估值包含非当前持仓：{', '.join(sorted(unknown_codes))}")
        self.store.save_portfolio_marks(
            portfolio_id,
            as_of.isoformat(),
            [
                (mark.asset_code.strip().upper(), str(mark.price), mark.source.strip())
                for mark in marks
            ],
        )
        summary, _ = self._calculate_portfolio(portfolio, transactions, as_of)
        return self._save_nav_snapshot(portfolio_id, summary, unit_count, note.strip())

    def create_secret(
        self,
        owner_id: str,
        provider: str,
        label: str,
        value: str,
    ) -> SecretMetadata:
        if self.vault is None:
            raise RuntimeError("密钥保险箱未配置。")
        return self.store.create_secret(
            owner_id,
            provider,
            label,
            self.vault.encrypt(value),
        )

    def list_secrets(self, owner_id: str) -> list[SecretMetadata]:
        return self.store.list_secrets(owner_id)

    def delete_secret(self, secret_id: str, owner_id: str) -> bool:
        return self.store.delete_secret(secret_id, owner_id)


committee_service = CommitteeService(
    create_store(
        settings.database_url,
        settings.database_path,
        settings.default_user_id,
    ),
    SecretVault(settings.secret_key_path, settings.secret_master_key),
)
