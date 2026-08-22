"""CreatorExecutionRuntime 启动恢复语义：重启不自动重跑未完成执行。"""

from __future__ import annotations

from vibe_visualization_api.creator_studio.execution import CreatorExecutionRuntime


class FakeRepository:
    def __init__(self, jobs: list[dict]):
        self._jobs = {job["jobId"]: dict(job) for job in jobs}
        self.updated: list[dict] = []

    def list_incomplete_jobs(self) -> list[dict]:
        return [dict(job) for job in self._jobs.values()
                if job.get("status") not in {"succeeded", "failed", "cancelled"}]

    def get_job(self, *, user_id: str, workspace_id: str, job_id: str) -> dict:
        return dict(self._jobs[job_id])

    def update_job(self, job: dict) -> None:
        self._jobs[job["jobId"]] = dict(job)
        self.updated.append(dict(job))


class FakeAdapter:
    def __init__(self):
        self.calls: list[dict] = []

    def run_node(self, request, *, cancel_event=None):
        self.calls.append(request)
        return {"status": "succeeded", "progress": 100}


def _job(job_id: str, status: str) -> dict:
    return {
        "jobId": job_id,
        "userId": "alice",
        "workspaceId": "creator-a",
        "status": status,
        "progress": 0,
        "request": {"run_id": "creator-t", "stage_id": "s", "node_id": "n"},
    }


def test_startup_interrupts_queued_and_running_jobs_without_redispatch():
    repo = FakeRepository([
        _job("job-queued", "queued"),
        _job("job-running", "running"),
    ])
    adapter = FakeAdapter()
    finished: list[dict] = []
    runtime = CreatorExecutionRuntime(
        repo,
        adapter,
        on_started=lambda job: None,
        on_finished=lambda job: finished.append(dict(job)),
    )

    runtime.startup()

    # 未完成执行一律显式中断，不自动重跑（有副作用的 job 如发布会被重新触发）
    assert adapter.calls == []
    statuses = {job["jobId"]: job for job in finished}
    assert statuses["job-queued"]["status"] == "failed"
    assert "排队中的执行已取消" in statuses["job-queued"]["error"]
    assert statuses["job-running"]["status"] == "failed"
    assert "原执行已中断" in statuses["job-running"]["error"]

    runtime.shutdown()
