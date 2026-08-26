"""Route contract smoke test for analysis health and version history."""

import os
import sys
from unittest import mock

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routes.reports import router  # noqa: E402


REPORT_ID = "8ce9edb7-cc49-4b05-8747-497977159bea"
MISSING_REPORT_ID = "4f312583-0928-45ad-958b-9e69af25f7c1"


class FakeReportGenerator:
    def health(self):
        return {
            "status": "degraded",
            "configured": True,
            "provider": "siliconflow",
            "model": "test-model",
            "circuit_open": True,
            "retry_after_seconds": 42,
        }


class FakeHistoryService:
    def timeline_for_report(self, report_id, limit=50):
        if report_id == MISSING_REPORT_ID:
            raise ValueError("analysis_report_not_found")
        return {
            "current_report_id": report_id,
            "current_revision": 2,
            "total_revisions": 2,
            "requested_limit": limit,
            "revisions": [{"id": report_id, "revision": 2, "is_current": True}],
        }


def main() -> int:
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    with mock.patch(
        "services.ai_report.get_report_generator",
        return_value=FakeReportGenerator(),
    ), mock.patch(
        "services.analysis_history_service.AnalysisHistoryService",
        FakeHistoryService,
    ):
        health = client.get("/api/reports/ai-health")
        if health.status_code != 200 or health.json().get("status") != "degraded":
            raise AssertionError(f"AI health route contract failed: {health.status_code} {health.text}")

        timeline = client.get(f"/api/reports/{REPORT_ID}/timeline?limit=12")
        payload = timeline.json()
        if timeline.status_code != 200 or payload.get("requested_limit") != 12:
            raise AssertionError(f"Timeline route contract failed: {timeline.status_code} {timeline.text}")

        missing = client.get(f"/api/reports/{MISSING_REPORT_ID}/timeline")
        if missing.status_code != 404 or missing.json().get("detail") != "分析报告不存在":
            raise AssertionError(f"Missing timeline should return 404: {missing.status_code} {missing.text}")

        malformed = client.get("/api/reports/not-a-uuid/timeline")
        if malformed.status_code != 422:
            raise AssertionError(f"Malformed report IDs should return 422: {malformed.status_code} {malformed.text}")

    print("OK analysis runtime routes expose health, timeline and explicit 404 behavior")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
