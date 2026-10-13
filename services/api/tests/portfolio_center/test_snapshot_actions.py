from datetime import date, datetime, timedelta, UTC

from fastapi.testclient import TestClient
from vibe_visualization_api.config import Settings
from vibe_visualization_api.main import create_app


def test_snapshot_actions_are_source_bound_isolated_and_leave_reports_immutable(tmp_path):
    settings=Settings(runtime_dir=tmp_path,database_path=tmp_path/'desk.db',legacy_portfolio_path=tmp_path/'missing.json')
    headers={'X-User-Id':'u','X-Workspace-Id':'w'}
    with TestClient(create_app(settings)) as client:
        def save(product,cash):
            response=client.post('/api/portfolio-center/import-snapshots',headers=headers,json=dict(productId=product,name='合成产品',asOf=str(date.today()),navFloor=200,holdings=[dict(assetType='cash',symbol='CASH',name='现金',account='同名账户',currency='CNY',bookValue=cash,availableCash=cash)]))
            assert response.status_code==201,response.text
            return response.json()
        earlier=save('A',90);source=save('A',100);newer=save('A',110);other=save('B',100)
        path=f"/api/portfolio-center/import-snapshots/{source['id']}/risk-actions"
        created=client.post(path,headers=headers,json=dict(category='alerts',index=0))
        assert created.status_code==201,created.text
        action=created.json()
        assert action['sourceSnapshotId']==source['id']
        assert source['report']['alerts'][0] in action['detail']
        assert client.post(path,headers=headers,json=dict(category='alerts',index=0)).json()['id']==action['id']
        assert len(client.get(f"/api/portfolio-center/import-snapshots/{newer['id']}/risk-actions",headers=headers).json())==1
        assert client.get(f"/api/portfolio-center/import-snapshots/{other['id']}/risk-actions",headers=headers).json()==[]
        assert client.get(path,headers={**headers,'X-User-Id':'other'}).status_code==404
        assert client.post(path,headers={**headers,'X-Workspace-Id':'other'},json=dict(category='alerts',index=0)).status_code==404
        assert client.post(path,headers=headers,json=dict(category='alerts',index=9999)).status_code==409
        assert client.get('/api/portfolio-center?includeQuotes=false',headers=headers).json()['riskActions']==[]
        update=f"/api/portfolio-center/risk-actions/{action['id']}"
        assert client.patch(update,headers=headers,json=dict(status='resolved',owner='合成负责人',note='跳过接手')).status_code==409
        assert client.patch(update,headers=headers,json=dict(status='acknowledged',owner='合成负责人')).status_code==409
        ack=client.patch(update,headers=headers,json=dict(status='acknowledged',owner='合成负责人',dueAt=(datetime.now(UTC)+timedelta(days=1)).isoformat()))
        assert ack.status_code==200,ack.text
        assert client.patch(update,headers=headers,json=dict(reviewSnapshotId=other['id'])).status_code==409
        assert client.patch(update,headers=headers,json=dict(reviewSnapshotId=source['id'])).status_code==409
        assert client.patch(update,headers=headers,json=dict(reviewSnapshotId=earlier['id'])).status_code==409
        assert client.patch(update,headers=headers,json=dict(reviewSnapshotId='missing')).status_code==404
        old_date=client.post('/api/portfolio-center/import-snapshots',headers=headers,json={**source['snapshot'],'asOf':str(date.today()-timedelta(days=1))}).json()
        assert client.patch(update,headers=headers,json=dict(reviewSnapshotId=old_date['id'])).status_code==409
        attached=client.patch(update,headers=headers,json=dict(reviewSnapshotId=newer['id']))
        assert attached.status_code==200,attached.text
        assert attached.json()['reviewSnapshotId']==newer['id']
        assert client.patch(update,headers=headers,json=dict(reviewSnapshotId=None)).json()['reviewSnapshotId'] is None
        assert client.patch(update,headers=headers,json=dict(reviewSnapshotId=newer['id'])).status_code==200
        assert client.post(path,headers=headers,json=dict(category='alerts',index=0)).json()['id']==action['id']
        assert client.patch(update,headers=headers,json=dict(status='resolved')).status_code==409
        closed=client.patch(update,headers=headers,json=dict(status='resolved',note='合成复核依据；记录结案不代表原风险消失'))
        assert closed.status_code==200,closed.text
        assert closed.json()['sourceSnapshotId']==source['id']
        assert closed.json()['reviewSnapshotId']==newer['id']
        assert client.patch(update,headers=headers,json=dict(note='修改已结案')).status_code==409
        assert client.get(f"/api/portfolio-center/import-snapshots/{source['id']}",headers=headers).json()==source
        assert client.post(path,headers=headers,json=dict(category='alerts',index=0)).json()['id']!=action['id']


def test_unassigned_snapshot_actions_do_not_bleed_into_other_unassigned_snapshots(tmp_path):
    settings=Settings(runtime_dir=tmp_path,database_path=tmp_path/'desk.db',legacy_portfolio_path=tmp_path/'missing.json')
    with TestClient(create_app(settings)) as client:
        ids=[]
        for cash in [100,110]:
            result=client.post('/api/portfolio-center/import-snapshots',json=dict(name='未归属',asOf=str(date.today()),holdings=[dict(assetType='cash',symbol='CASH',name='现金',account='A',currency='CNY',bookValue=cash)]))
            ids.append(result.json()['id'])
        path=f'/api/portfolio-center/import-snapshots/{ids[0]}/risk-actions'
        action=client.post(path,json=dict(category='gaps',index=0))
        assert action.status_code==201
        assert client.patch(f"/api/portfolio-center/risk-actions/{action.json()['id']}",json=dict(reviewSnapshotId=ids[1])).status_code==409
        assert len(client.get(path).json())==1
        assert client.get(f'/api/portfolio-center/import-snapshots/{ids[1]}/risk-actions').json()==[]
