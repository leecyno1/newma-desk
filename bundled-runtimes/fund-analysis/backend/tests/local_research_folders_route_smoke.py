import os
import sys
from copy import deepcopy

from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routes import research_folders  # noqa: E402


class FakeFolderService:
    def __init__(self):
        self.review_action = None

    def list_folders(self):
        return [{
            "id": "folder-1",
            "name": "调研纪要",
            "path": "/tmp/调研纪要",
            "status": "ready",
            "last_scan_at": "2026-08-05T09:00:00+00:00",
            "last_scan_counts": {"created": 2, "updated": 1, "unchanged": 4, "failed": 0, "supported": 7},
        }]

    def add_folder(self, path):
        if path == "/missing":
            raise research_folders.FolderValidationError("文件夹不存在或无法读取")
        return {"id": "folder-1", "name": "调研纪要", "path": path, "status": "ready"}

    def scan_folder(self, folder_id, retry_llm=False):
        if folder_id == "missing":
            raise research_folders.FolderValidationError("未找到已连接的调研文件夹")
        return {
            "folder_id": folder_id,
            "retry_llm": retry_llm,
            "counts": {"created": 1, "updated": 0, "unchanged": 2, "failed": 0, "supported": 3},
            "results": [],
        }

    def list_pending_reviews(self, folder_id=None):
        return [{
            "id": "proposal-1",
            "report_id": "report-1",
            "report_title": "张三访谈",
            "kind": "manager",
            "value": "张三",
            "confidence": 0.88,
            "review_status": "pending",
            "source_ref": {"relative_path": "张三/访谈.md", "excerpt": "基金经理：张三"},
        }]

    def review_proposal(self, report_id, proposal_id, action):
        self.review_action = (report_id, proposal_id, action)
        return {"status": action, "report": {"id": report_id}, "proposal": {"id": proposal_id}}

    def confirm_manager_proposals(self, folder_id=None, min_confidence=0.88):
        return {
            "status": "completed",
            "requested_reports": 2,
            "confirmed": 2,
            "multi_manager": 1,
            "ambiguous": 0,
            "failed": 0,
            "linked_fund_count": 2,
            "min_confidence": min_confidence,
        }

    def confirm_label_proposals(self, folder_id=None, min_confidence=0.9):
        return {
            "status": "completed",
            "requested": 2,
            "confirmed": 2,
            "failed": 0,
            "skipped_unresolved": 1,
            "min_confidence": min_confidence,
        }


def main() -> int:
    service = FakeFolderService()
    original_get_service = research_folders._get_service
    research_folders._get_service = lambda: service
    try:
        app = FastAPI()
        app.include_router(research_folders.router)
        client = TestClient(app)

        paths = {route.path for route in app.routes}
        expected = {
            "/api/research-folders/",
            "/api/research-folders/{folder_id}/scan",
            "/api/research-folders/reviews",
            "/api/research-folders/reviews/confirm-managers",
            "/api/research-folders/reviews/confirm-labels",
            "/api/research-folders/reviews/{report_id}/{proposal_id}",
        }
        if not expected.issubset(paths):
            raise AssertionError(f"Missing local research folder routes: {paths}")

        listing = client.get("/api/research-folders/")
        if listing.status_code != 200 or listing.json().get("data", [{}])[0].get("id") != "folder-1":
            raise AssertionError(f"Folder listing contract failed: {listing.status_code} {listing.text}")

        created = client.post("/api/research-folders/", json={"path": "/tmp/调研纪要"})
        if created.status_code != 201 or created.json().get("folder", {}).get("path") != "/tmp/调研纪要":
            raise AssertionError(f"Folder connect contract failed: {created.status_code} {created.text}")

        invalid = client.post("/api/research-folders/", json={"path": "/missing"})
        if invalid.status_code != 400:
            raise AssertionError(f"Invalid folder should return 400: {invalid.status_code} {invalid.text}")

        scan = client.post("/api/research-folders/folder-1/scan")
        if scan.status_code != 200 or scan.json().get("counts", {}).get("created") != 1:
            raise AssertionError(f"Folder scan contract failed: {scan.status_code} {scan.text}")
        retry_scan = client.post("/api/research-folders/folder-1/scan?retry_llm=true")
        if retry_scan.status_code != 200 or retry_scan.json().get("retry_llm") is not True:
            raise AssertionError(f"Explicit LLM retry contract failed: {retry_scan.status_code} {retry_scan.text}")

        reviews = client.get("/api/research-folders/reviews?folder_id=folder-1")
        if reviews.status_code != 200 or reviews.json().get("total") != 1:
            raise AssertionError(f"Pending review contract failed: {reviews.status_code} {reviews.text}")

        bulk = client.post(
            "/api/research-folders/reviews/confirm-managers",
            json={"folder_id": "folder-1", "min_confidence": 0.88},
        )
        if (
            bulk.status_code != 200
            or bulk.json().get("confirmed") != 2
            or bulk.json().get("multi_manager") != 1
        ):
            raise AssertionError(f"Bulk manager review contract failed: {bulk.status_code} {bulk.text}")

        labels = client.post(
            "/api/research-folders/reviews/confirm-labels",
            json={"folder_id": "folder-1", "min_confidence": 0.9},
        )
        if labels.status_code != 200 or labels.json().get("confirmed") != 2:
            raise AssertionError(f"Bulk label review contract failed: {labels.status_code} {labels.text}")

        confirmed = client.patch(
            "/api/research-folders/reviews/report-1/proposal-1",
            json={"action": "confirmed"},
        )
        if confirmed.status_code != 200 or service.review_action != ("report-1", "proposal-1", "confirmed"):
            raise AssertionError(f"Review decision contract failed: {confirmed.status_code} {confirmed.text}")

        rejected_action = client.patch(
            "/api/research-folders/reviews/report-1/proposal-1",
            json={"action": "maybe"},
        )
        if rejected_action.status_code != 422:
            raise AssertionError(f"Invalid review action should return 422: {rejected_action.status_code}")
    finally:
        research_folders._get_service = original_get_service

    print("OK local research folder API exposes connect, scan, status and human review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
