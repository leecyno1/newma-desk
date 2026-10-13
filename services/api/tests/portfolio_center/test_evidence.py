import asyncio
from copy import deepcopy
from datetime import date, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient

from vibe_visualization_api.config import Settings
from vibe_visualization_api.main import create_app
from vibe_visualization_api.data_services.client import UpstreamServiceError
from vibe_visualization_api.portfolio_center.diagnosis import PortfolioSnapshotInput, diagnose
from vibe_visualization_api.portfolio_center.evidence import project_fund_evidence, read_fund_evidence


def payload():
    return dict(status='available', symbol='000001.OF', duration=dict(status='ok', as_of_date=str(date.today()), estimated_duration=3.2, r_squared=.8, methodology_version='regression-test', source='synthetic'))


def snapshot():
    return PortfolioSnapshotInput.model_validate(dict(name='基金测试', asOf=str(date.today()), holdings=[
        dict(assetType='fund', market='CN', symbol='000001', name='测试基金', account='A', currency='CNY', bookValue=100, equityBeta=0, ratePnlPerBp=-.03),
        dict(assetType='fund', market='CN', symbol='000001', name='测试基金', account='B', currency='CNY', bookValue=200, equityBeta=0),
    ]))


class FundClient:
    def __init__(self):
        self.calls = []
        self.data = payload()
        self.fail = False

    async def invoke(self, service, capability, args):
        self.calls.append((capability, args))
        if self.fail:
            raise UpstreamServiceError('private upstream detail')
        return deepcopy(self.data)


def test_projection_rejects_wrong_identity_and_future_evidence():
    data = payload()
    assert project_fund_evidence('000002', data, date.today())['estimatedDuration'] is None
    assert project_fund_evidence('000001.SH', data, date.today())['estimatedDuration'] is None
    data['duration']['as_of_date'] = str(date.today()+timedelta(days=1))
    projected = project_fund_evidence('000001', data, date.today())
    assert projected['status'] == 'after_snapshot'
    assert projected['estimatedDuration'] is None


def test_estimate_staleness_low_fit_and_missing_date_are_visible():
    data = payload()
    assert project_fund_evidence('000001', data, date.today())['status'] == 'reference_only'
    data['duration']['r_squared'] = .2
    assert project_fund_evidence('000001', data, date.today())['status'] == 'low_fit'
    data['duration']['as_of_date'] = str(date.today()-timedelta(days=32))
    assert project_fund_evidence('000001', data, date.today())['status'] == 'stale'
    data['duration']['as_of_date'] = None
    assert project_fund_evidence('000001', data, date.today())['estimatedDuration'] is None


def test_deduplication_failure_and_manual_values_preserved():
    portfolio = snapshot()
    before = portfolio.model_dump()
    client = FundClient()
    registry = SimpleNamespace(get=lambda _: object())
    result = asyncio.run(read_fund_evidence(portfolio, client, registry))
    assert len(result) == len(client.calls) == 1
    assert client.calls[0][0] == 'fund.risk.evidence'
    assert result[0]['estimatedDuration'] == 3.2
    assert portfolio.model_dump() == before
    assert diagnose(portfolio)['scenarios'][0]['totalPnl'] is None  # Missing sensitivity stays missing.
    client.fail = True
    result = asyncio.run(read_fund_evidence(portfolio, client, registry))
    assert result[0]['status'] == 'unavailable'
    assert 'private' not in str(result)
    portfolio.holdings[0].market = 'US'
    assert asyncio.run(read_fund_evidence(portfolio, client, registry))[0]['status'] == 'unsupported'


def test_research_evaluation_is_server_sourced_versioned_and_workspace_scoped(tmp_path):
    app = create_app(Settings(runtime_dir=tmp_path, database_path=tmp_path/'desk.db', legacy_portfolio_path=tmp_path/'none.json'))
    headers = {'X-User-Id': 'evidence-test', 'X-Workspace-Id': 'A'}
    upstream = FundClient()
    with TestClient(app) as client:
        app.state.data_service_client = upstream
        app.state.data_service_registry = SimpleNamespace(get=lambda _: object())
        original = client.post('/api/portfolio-center/import-snapshots', headers=headers, json=snapshot().model_dump(mode='json', by_alias=True)).json()
        url = f"/api/portfolio-center/import-snapshots/{original['id']}/research-evaluations"
        assert client.post(url, headers={**headers, 'X-Workspace-Id': 'B'}).status_code == 404
        assert upstream.calls == []
        response = client.post(url, headers=headers, json={'researchEvidence': [{'estimatedDuration': 999}]})
        assert response.status_code == 201, response.text
        updated = response.json()
        assert updated['id'] != original['id']
        assert updated['snapshot'] == original['snapshot']
        assert updated['report']['researchEvidence'][0]['estimatedDuration'] == 3.2
        assert updated['report']['scenarios'] == original['report']['scenarios']
        assert updated['report']['conclusion'] == original['report']['conclusion']  # Read-only evidence is not a new calculation.
        assert client.post(url, headers=headers).json()['id'] == updated['id']
        upstream.data['duration']['estimated_duration'] = 4.1
        third = client.post(url, headers=headers).json()
        assert third['id'] not in {original['id'], updated['id']}
        records = client.get('/api/portfolio-center/import-snapshots', headers=headers).json()
        assert len(records) == 3
        assert next(r for r in records if r['id'] == original['id']) == original
        assert next(r for r in records if r['id'] == updated['id']) == updated
