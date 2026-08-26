import asyncio

from orchestra_app.service import CommitteeService
from orchestra_app.registry import load_profiles


def test_demo_committee_completes_all_registered_seats() -> None:
    async def scenario() -> None:
        seat_count = len(load_profiles())
        service = CommitteeService()
        snapshot = await service.create_run("测试议题", "demo")
        record = service._runs[snapshot.id]  # noqa: SLF001
        assert record.task is not None
        await record.task
        completed = service.get_run(snapshot.id)
        assert completed.status == "completed"
        assert completed.phase == "completed"
        assert len(completed.agents) == seat_count
        assert all(agent.status == "completed" for agent in completed.agents.values())
        assert all(len(agent.thoughts) == 3 for agent in completed.agents.values())
        assert all(agent.thinking_stage == "synthesis" for agent in completed.agents.values())
        assert completed.decision
        events = service.list_events(snapshot.id)
        assert len(events) > seat_count * 4
        assert completed.last_event_seq == len(events)
        assert sum(event.type == "agent.thinking" for event in events) == seat_count * 3
        replay_events = service.replay_events(snapshot.id)
        assert len(replay_events) < len(events)
        assert replay_events[0].type == "run.started"
        assert replay_events[-1].type == "run.completed"
        assert sum(
            event.type == "agent.output.delta" for event in replay_events
        ) == seat_count
        summaries = service.list_runs()
        assert summaries[0].id == snapshot.id
        assert summaries[0].completed_agents == seat_count
        assert service.run_metrics() == {"total": 1, "active": 0}

    asyncio.run(scenario())


def test_cancel_run_emits_a_single_terminal_event() -> None:
    async def scenario() -> None:
        service = CommitteeService()
        snapshot = await service.create_run("取消测试", "demo")
        await asyncio.sleep(0)
        await service.cancel_run(snapshot.id)
        await service.cancel_run(snapshot.id)

        cancelled = service.get_run(snapshot.id)
        events = service.list_events(snapshot.id)
        assert cancelled.status == "cancelled"
        assert sum(event.type == "run.cancelled" for event in events) == 1
        assert cancelled.last_event_seq == len(events)

    asyncio.run(scenario())


def test_completed_run_supports_persisted_single_agent_intervention() -> None:
    async def scenario() -> None:
        service = CommitteeService()
        snapshot = await service.create_run("单席干预测试", "demo")
        record = service._runs[snapshot.id]  # noqa: SLF001
        assert record.task is not None
        await record.task

        agent_id = next(iter(service.get_run(snapshot.id).agents))
        result = await service.start_agent_intervention(
            snapshot.id,
            agent_id,
            "local-user",
            "supplement",
            "补充近期数据并检查原结论",
        )
        intervention = record.interventions[agent_id]
        await intervention

        completed = service.get_run(snapshot.id)
        runtime = completed.agents[agent_id]
        events = service.list_events(snapshot.id)
        artifacts = service.list_artifacts(snapshot.id, "local-user")

        assert result["status"] == "queued"
        assert completed.status == "completed"
        assert runtime.status == "completed"
        assert runtime.phase == "intervention"
        assert runtime.intervention_action == "supplement"
        assert "单席干预增量报告" in runtime.output
        assert any(event.type == "agent.intervention.requested" for event in events)
        assert any(event.type == "agent.intervention.started" for event in events)
        assert any(event.type == "agent.intervention.completed" for event in events)
        assert any(
            artifact["agent_id"] == agent_id
            and artifact["kind"] == "intervention_report"
            for artifact in artifacts
        )

    asyncio.run(scenario())
