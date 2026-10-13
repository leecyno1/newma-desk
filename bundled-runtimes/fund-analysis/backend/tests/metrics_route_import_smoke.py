import os
import sys
from unittest.mock import Mock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from routes.metrics import router
from routes import metrics as metrics_routes


def main() -> int:
    app = FastAPI()
    app.include_router(router)
    routes = set(app.openapi()['paths'])
    expected = {"/api/metrics/fund/{fund_code}", "/api/metrics/fund/{fund_code}/recalculate",
                "/api/metrics/fund/{fund_code}/archives", "/api/metrics/fund/{fund_code}/archives/{archive_id}"}
    if not expected.issubset(routes):
        print(f"Missing expected metric routes. routes={routes}")
        return 1
    client = TestClient(app)
    repo = Mock()
    archive_id = '00000000-0000-0000-0000-000000000001'
    repo.list_invalidation_archives.return_value = [{'id': archive_id, 'record_count': 3}]
    repo.get_invalidation_archive.side_effect = lambda fund, identifier: {'id': str(identifier), 'metadata': {'reason': 'invalid_nav'}} if fund == 'TEST.OF' else None
    with patch.object(metrics_routes, 'get_metric_snapshot_repo', return_value=repo):
        summaries = client.get('/api/metrics/fund/TEST.OF/archives?limit=5')
        assert summaries.status_code == 200 and summaries.json()['count'] == 1
        repo.list_invalidation_archives.assert_called_once_with('TEST.OF', 5)
        detail = client.get(f'/api/metrics/fund/TEST.OF/archives/{archive_id}')
        assert detail.status_code == 200 and detail.json()['eligible_for_scoring'] is False
        assert client.get(f'/api/metrics/fund/OTHER.OF/archives/{archive_id}').status_code == 404
        assert client.get('/api/metrics/fund/TEST.OF/archives/invalid-id').status_code == 422
        assert client.get('/api/metrics/fund/TEST.OF/archives?limit=1000').status_code == 422
    response = client.get("/api/metrics/health")
    if response.status_code != 200 or response.json().get("status") != "ok":
        print(f"Expected metrics health ok, got {response.status_code}: {response.text}")
        return 1
    print("OK metrics route import and health")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
