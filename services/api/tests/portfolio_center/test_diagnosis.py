from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from vibe_visualization_api.config import Settings
from vibe_visualization_api.main import create_app
from vibe_visualization_api.portfolio_center.diagnosis import PortfolioImportInput, PortfolioSnapshotInput, diagnose, parse_import
from vibe_visualization_api.portfolio_center.store import PortfolioStore


def mixed_snapshot():
    common = dict(account='证券账户', currency='CNY', market='CN', bookValue=100, source='验收合成数据')
    holdings = [dict(common, assetType='stock', symbol=f'S{i}', name=f'股票{i}', equityBeta=1, equityBenchmark='CSI300') for i in range(8)]
    holdings += [dict(common, assetType='fund', symbol=f'F{i}', name=f'基金{i}', equityBeta=.5, equityBenchmark='CSI300', ratePnlPerBp=-.5) for i in range(3)]
    holdings += [dict(common, assetType='bond', symbol=f'B{i}', name=f'债券{i}', ratePnlPerBp=-1) for i in range(10)]
    holdings += [dict(common, account='期货账户', assetType='equity_future', symbol='IF-TEST', name='股指期货', bookValue=0, direction='short', notional=800, equityBenchmark='CSI300'), dict(common, account='期货账户', assetType='bond_future', symbol='T-TEST', name='国债期货', bookValue=0, direction='short', ratePnlPerBp=10)]
    holdings += [dict(common, account=a, assetType='cash', symbol='CASH', name='现金', bookValue=50, availableCash=50) for a in ['证券账户', '期货账户']]
    return PortfolioSnapshotInput.model_validate(dict(name='验收混合组合', asOf=str(date.today()), navFloor=2100, holdings=holdings))


def duration_snapshot():
    common = dict(market='CN', currency='CNY', account='A', source='验收合成参数，非真实报价', rateAsOf=str(date.today()))
    return PortfolioSnapshotInput.model_validate(dict(name='久期换算验收', asOf=str(date.today()), holdings=[
        dict(common, assetType='bond', symbol='BOND-TEST', name='普通固定利率债', bookValue=1_000_000, modifiedDuration=5),
        dict(common, assetType='bond_future', symbol='T-TEST', name='国债期货', bookValue=0, direction='short', contracts=5, contractDv01=80, expiryDate=str(date.today()+timedelta(days=7))),
        dict(assetType='cash', symbol='CASH', name='现金', account='A', currency='CNY', bookValue=10_000, availableCash=10_000),
    ]))


def test_duration_and_contract_dv01_flow_into_scenarios_without_mutating_input():
    snapshot = duration_snapshot()
    before = snapshot.model_dump()
    report = diagnose(snapshot)
    assert report['rateHedge'] == dict(knownAssets=-500, knownFutures=400, net=-100)
    assert report['scenarios'][0]['totalPnl'] == -5000
    assert report['scenarios'][1]['totalPnl'] == 5000
    assert report['scenarios'][1]['cashByAccount'][0]['remaining'] == -10000
    assert report['rows'][0]['resolvedRatePnlPerBp'] == -500
    assert report['rows'][0]['ratePnlPerBp'] is None
    assert '修正久期' in report['rows'][0]['rateInputBasis']
    assert any('距合约到期 7 天' in a for a in report['alerts'])
    assert snapshot.model_dump() == before


def test_additional_scenario_keeps_baseline_and_drives_cash_and_conclusion():
    data = duration_snapshot().model_dump(by_alias=True)
    baseline = diagnose(PortfolioSnapshotInput.model_validate(data))
    data['additionalScenarios'] = [dict(label='利率快速下行', equityShockPct=0, rateShockBp=-100)]
    report = diagnose(PortfolioSnapshotInput.model_validate(data))
    assert report['scenarios'][:3] == baseline['scenarios']
    custom = report['scenarios'][3]
    assert custom['label'] == '自定义 · 利率快速下行'
    assert custom['knownAssetPnl'] == 50000
    assert custom['knownFuturesPnl'] == -40000
    assert custom['totalPnl'] == 10000
    assert custom['cashByAccount'][0]['remaining'] == -30000
    assert custom['contributions'] == [
        dict(rowIndex=0,pnl=50000,futuresLossDemand=None),
        dict(rowIndex=1,pnl=-40000,futuresLossDemand=40000),
        dict(rowIndex=2,pnl=0,futuresLossDemand=None),
    ]
    for scenario in report['scenarios']:
        assert sum(c['pnl'] for c in scenario['contributions']) == scenario['totalPnl']
        assert sum(c['futuresLossDemand'] or 0 for c in scenario['contributions']) == scenario['cashByAccount'][0]['futuresLossDemand']
    assert report['conclusion']['findings'][0]['amount'] == -30000
    assert report['conclusion']['findings'][0]['scenario'] == custom['label']
    data['holdings'][0]['modifiedDuration'] = None
    incomplete = diagnose(PortfolioSnapshotInput.model_validate(data))['scenarios'][3]
    assert incomplete['totalPnl'] is None
    assert incomplete['contributions'][0]['pnl'] is None
    assert incomplete['contributions'][1]['pnl'] == -40000


@pytest.mark.parametrize('items', [
    [dict(label='重复',equityShockPct=0,rateShockBp=0)]*2,
    [dict(label=' ',equityShockPct=0,rateShockBp=0)],
    [dict(label='越界',equityShockPct=-101,rateShockBp=0)],
    [dict(label='越界',equityShockPct=0,rateShockBp=1001)],
])
def test_custom_scenarios_reject_duplicate_blank_names_and_invalid_ranges(items):
    data = duration_snapshot().model_dump(by_alias=True)
    data['additionalScenarios'] = items
    with pytest.raises(ValueError):
        PortfolioSnapshotInput.model_validate(data)


@pytest.mark.parametrize('field,value', [('rate_as_of', None), ('rate_as_of', date.today()-timedelta(days=1)), ('rate_as_of', date.today()+timedelta(days=1)), ('source', '用户导入，未独立核验')])
def test_derived_sensitivity_needs_same_date_and_source(field, value):
    snapshot = duration_snapshot()
    setattr(snapshot.holdings[0], field, value)
    report = diagnose(snapshot)
    assert report['scenarios'][0]['totalPnl'] is None
    assert report['rows'][0]['ratePnlPerBpBase'] is None
    assert report['rows'][0]['gaps']


def test_explicit_whole_position_value_is_not_overwritten_by_helpers():
    snapshot = duration_snapshot()
    snapshot.holdings[0].rate_pnl_per_bp = -100
    report = diagnose(snapshot)
    assert report['rows'][0]['ratePnlPerBpBase'] == -100
    assert '未用久期' in report['rows'][0]['rateInputBasis']


def test_expired_contract_is_not_counted_as_live_hedge():
    snapshot = duration_snapshot()
    snapshot.holdings[1].expiry_date = date.today()
    report = diagnose(snapshot)
    assert report['rateHedge']['knownFutures'] == 0
    assert report['rateHedge']['net'] is None
    assert report['scenarios'][0]['totalPnl'] is None
    assert any('不再计作有效对冲' in a for a in report['alerts'])


def test_rate_buckets_expose_cross_currency_cancellation():
    snapshot = duration_snapshot()
    snapshot.holdings[0].currency = 'USD'
    snapshot.holdings[0].fx_to_base = 7
    snapshot.holdings[1].contract_dv01 = 700
    report = diagnose(snapshot)
    assert report['rateHedge']['net'] == 0
    assert report['rateBuckets'] == [dict(currency='CNY', assets=0, futures=3500, net=3500), dict(currency='USD', assets=-3500, futures=0, net=-3500)]


def test_duration_helper_rejects_fund_estimate_and_parses_chinese_headers():
    data = duration_snapshot().model_dump(by_alias=True)
    data['holdings'][0]['assetType'] = 'fund'
    with pytest.raises(ValueError, match='基金回归久期'):
        PortfolioSnapshotInput.model_validate(data)
    snapshot = parse_import(PortfolioImportInput(name='中文导入', asOf=date.today(), text=f'资产类型,代码,名称,账户,币种,账面金额,修正久期,利率参数日期,依据\n债券,000001,合成债,A,CNY,1000000,5,{date.today()},测试估值'))
    assert diagnose(snapshot)['rows'][0]['ratePnlPerBpBase'] == -500


def test_mixed_portfolio_hedge_and_cash_squeeze():
    report = diagnose(mixed_snapshot())
    assert report['nav'] == 2200
    assert report['navHeadroom'] == 100
    assert report['equityHedges'] == [dict(benchmark='CSI300', assets=950, futures=-800, net=150)]
    assert report['rateHedge'] == dict(knownAssets=-11.5, knownFutures=10, net=-1.5)
    fall, rise, _ = report['scenarios']
    assert fall['knownAssetPnl'] == -670
    assert fall['knownFuturesPnl'] == 580
    assert fall['totalPnl'] == -90
    assert fall['floorHeadroom'] == 10
    cash = next(c for c in rise['cashByAccount'] if c['account'] == '期货账户')
    assert rise['totalPnl'] == 90  # Net asset gain can coincide with a margin cash squeeze.
    assert cash['remaining'] == -530
    assert report['alerts']


def test_missing_fund_sensitivity_never_becomes_zero_risk():
    snapshot = mixed_snapshot()
    snapshot.holdings[8].equity_beta = None
    report = diagnose(snapshot)
    assert report['scenarios'][0]['totalPnl'] is None
    assert report['scenarios'][0]['floorHeadroom'] is None
    assert any('基金0' in gap for gap in report['gaps'])


def test_fx_missing_prevents_complete_nav_and_duplicate_snapshot_rows_rejected():
    snapshot = mixed_snapshot()
    snapshot.holdings[0].currency = 'USD'
    assert diagnose(snapshot)['nav'] is None
    data = mixed_snapshot().model_dump(by_alias=True)
    data['holdings'].append(data['holdings'][0])
    with pytest.raises(ValueError, match='重复持仓'):
        PortfolioSnapshotInput.model_validate(data)


def test_direction_and_sensitivity_sign_must_be_explicit():
    data = mixed_snapshot().model_dump(by_alias=True)
    data['holdings'][21]['direction'] = None
    with pytest.raises(ValueError, match='多空方向'):
        PortfolioSnapshotInput.model_validate(data)
    snapshot = mixed_snapshot()
    snapshot.holdings[22].rate_pnl_per_bp = -10
    report = diagnose(snapshot)
    assert report['scenarios'][0]['totalPnl'] is None
    assert any('符号' in gap for gap in report['gaps'])


def test_csv_and_excel_paste_preserve_identifiers_and_unknown_assets():
    for delimiter in [',', '\t']:
        text = delimiter.join(['资产类型','代码','名称','账户','币种','账面金额'])+'\n'+delimiter.join(['基金','000001','测试基金','a','CNY','100'])
        parsed = parse_import(PortfolioImportInput(name='test', asOf=date.today(), text=text))
        assert parsed.holdings[0].symbol == '000001'
        assert parsed.holdings[0].asset_type == 'fund'
    with pytest.raises(ValueError, match='第 2 行'):
        parse_import(PortfolioImportInput(name='test', asOf=date.today(), text='资产类型,代码,名称,账户,币种\n任意产品,0001,测试,a,CNY'))


def test_upstream_research_is_scoped_to_matching_stock_not_fund_code():
    snapshot = mixed_snapshot()
    archive = {'entries':[{'security':{'market':'CN','symbol':'S0'},'title':'失效投资论点','status':'invalidated','sourceModId':'stock-research'}]}
    report = diagnose(snapshot, archive)
    assert any('失效投资论点' in a for a in report['alerts'])
    snapshot.holdings[8].symbol = 'S0'
    assert diagnose(snapshot, archive)['rows'][8]['references'] == []


def test_snapshot_save_is_isolated_nonduplicating_and_does_not_create_trades(tmp_path):
    store = PortfolioStore(tmp_path/'portfolio.db')
    snapshot = mixed_snapshot()
    args = dict(user_id='alice', workspace_id='test', snapshot=snapshot.model_dump(mode='json', by_alias=True), report=diagnose(snapshot))
    first = store.save_import_snapshot(**args)
    assert store.save_import_snapshot(**args)['id'] == first['id']
    assert len(store.list_import_snapshots(user_id='alice',workspace_id='test')) == 1
    assert store.list_import_snapshots(user_id='bob',workspace_id='test') == []
    assert store.list_activities(user_id='alice',workspace_id='test') == []


def test_import_routes_validate_and_save_server_computed_diagnosis(tmp_path):
    settings = Settings(runtime_dir=tmp_path, database_path=tmp_path/'desk.db', legacy_portfolio_path=tmp_path/'missing.json')
    headers = {'X-User-Id':'e2e-import','X-Workspace-Id':'import'}
    with TestClient(create_app(settings)) as client:
        preview = client.post('/api/portfolio-center/import-previews', headers=headers, json={'name':'test','asOf':str(date.today()),'text':'资产类型,代码,名称,账户,币种,账面金额\n现金,CASH,现金,a,CNY,100'})
        assert preview.status_code == 200, preview.text
        structured = duration_snapshot().model_dump(mode='json', by_alias=True)
        structured['holdings'][0]['symbol'] = '001234'
        structured['holdings'][0]['source'] = '资料,含逗号与"引号"\n第二行'
        checked = client.post('/api/portfolio-center/import-previews', headers=headers, json=structured)
        assert checked.status_code == 200, checked.text
        assert checked.json()['snapshot'] == structured
        assert client.get('/api/portfolio-center/import-snapshots', headers=headers).json() == []
        structured['holdings'][-1]['availableCash'] = 20000
        assert client.post('/api/portfolio-center/import-previews', headers=headers, json=structured).status_code == 422
        assert client.get('/api/portfolio-center/import-snapshots',headers=headers).json() == []
        saved = client.post('/api/portfolio-center/import-snapshots',headers=headers,json=preview.json()['snapshot'])
        assert saved.status_code == 201, saved.text
        assert saved.json()['report']['nav'] == 100
        assert len(client.get('/api/portfolio-center/import-snapshots',headers=headers).json()) == 1
        malformed = client.post('/api/portfolio-center/import-previews',headers=headers,json={'name':'test','asOf':str(date.today()),'text':'资产类型,代码,名称,账户,币种\n股票,"unterminated'})
        assert malformed.status_code == 422
        invalid = client.post('/api/portfolio-center/import-previews',headers=headers,json={'name':'test','asOf':str(date.today()),'text':'资产类型,代码,名称,账户,币种,账面金额\n现金,CASH,现金,a,CNY,错误金额'})
        assert invalid.status_code == 422
        issue = invalid.json()['detail'][0]
        assert issue['loc'] == ['csvRow', 2, 'bookValue']
        assert issue['type'] == 'float_parsing'
        assert 'input' not in issue and 'url' not in issue
