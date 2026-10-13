from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from vibe_visualization_api.config import Settings
from vibe_visualization_api.main import create_app
from vibe_visualization_api.portfolio_center.diagnosis import PortfolioSnapshotInput, diagnose
from vibe_visualization_api.portfolio_center.store import PortfolioStore


def product(product_id, cash, floor, short=False, as_of=None):
    holdings = [dict(assetType='cash', symbol='CASH', name='现金', account='同名账户', currency='CNY', bookValue=cash, availableCash=cash)]
    if short:
        holdings.append(dict(assetType='equity_future', symbol='IF-TEST', name='合成空头', account='同名账户', currency='CNY', bookValue=0, direction='short', notional=10000, equityBenchmark='CSI300'))
    return PortfolioSnapshotInput.model_validate(dict(productId=product_id, name=product_id or '未归属', asOf=as_of or str(date.today()), navFloor=floor, holdings=holdings))


def test_products_keep_same_named_accounts_and_shortfalls_separate(tmp_path):
    store=PortfolioStore(tmp_path/'portfolio.db')
    for p in [product('A',100,200,True),product('B',10000,5000),product('',999999,0)]:
        store.save_import_snapshot(user_id='u',workspace_id='w',snapshot=p.model_dump(mode='json',by_alias=True),report=diagnose(p))
    items=store.list_import_products(user_id='u',workspace_id='w')
    assert [i['snapshot']['productId'] for i in items]==['A','B']
    assert [i['report']['nav'] for i in items]==[100,10000]
    assert min(c['remaining'] for s in items[0]['report']['scenarios'] for c in s['cashByAccount'])==-900
    assert min(c['remaining'] for s in items[1]['report']['scenarios'] for c in s['cashByAccount'])==10000
    assert store.list_import_products(user_id='other',workspace_id='w')==[]
    assert store.list_import_products(user_id='u',workspace_id='other')==[]


def test_product_list_uses_latest_position_date_without_recent_fifty_cutoff(tmp_path):
    store=PortfolioStore(tmp_path/'portfolio.db')
    def save(p):
        return store.save_import_snapshot(user_id='u',workspace_id='w',snapshot=p.model_dump(mode='json',by_alias=True),report=diagnose(p))
    first=save(product('A',100,0))
    updated=save(product('A',200,0))
    for i in range(51):
        save(product('B',100+i,0))
    save(product('A',300,0,as_of=str(date.today()-timedelta(days=1))))
    latest=store.list_import_products(user_id='u',workspace_id='w')
    assert latest[0]['id']==updated['id']
    assert updated['id'] not in [i['id'] for i in store.list_import_snapshots(user_id='u',workspace_id='w')]
    assert store.get_import_snapshot(user_id='u',workspace_id='w',snapshot_id=first['id'])['report']['nav']==100
    with pytest.raises(ValueError,match='产品编号'):
        product(' A ',100,0)


def test_product_import_and_read_routes_keep_identity_scope(tmp_path):
    settings=Settings(runtime_dir=tmp_path,database_path=tmp_path/'desk.db',legacy_portfolio_path=tmp_path/'missing.json')
    headers={'X-User-Id':'u','X-Workspace-Id':'w'}
    with TestClient(create_app(settings)) as client:
        preview=client.post('/api/portfolio-center/import-previews',headers=headers,json=dict(productId='P001',name='产品一',asOf=str(date.today()),text='资产类型,代码,名称,账户,币种,账面金额,可用现金\n现金,CASH,现金,账户一,CNY,100,100'))
        assert preview.status_code==200,preview.text
        assert client.get('/api/portfolio-center/import-products',headers=headers).json()==[]
        saved=client.post('/api/portfolio-center/import-snapshots',headers=headers,json=preview.json()['snapshot']).json()
        assert client.get('/api/portfolio-center/import-products',headers=headers).json()==[saved]
        path=f"/api/portfolio-center/import-snapshots/{saved['id']}"
        assert client.get(path,headers=headers).json()==saved
        assert client.get(path,headers={**headers,'X-User-Id':'other'}).status_code==404
        assert client.get('/api/portfolio-center/import-products',headers={**headers,'X-Workspace-Id':'other'}).json()==[]
