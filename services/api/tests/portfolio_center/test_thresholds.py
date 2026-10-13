from datetime import date

import pytest

from vibe_visualization_api.portfolio_center.diagnosis import PortfolioSnapshotInput, diagnose
from vibe_visualization_api.portfolio_center.thresholds import compile_nav_thresholds


@pytest.mark.parametrize('nav,warning,floor,status',[(100,95,80,'above_lines'),(95,95,80,'warning'),(90,95,80,'warning'),(80,95,80,'floor_reached'),(79,95,80,'floor_breached'),(None,95,80,'unassessed'),(100,None,None,'unconfigured'),(80,80,80,'floor_reached')])
def test_threshold_boundaries(nav,warning,floor,status):
    row=compile_nav_thresholds(nav,[],warning,floor)['rows'][0]
    assert row['status']==status
    assert row['warningHeadroom']==(nav-warning if nav is not None and warning is not None else None)


def snapshot(warning=95):
    return PortfolioSnapshotInput.model_validate(dict(name='分级预警合成',productId='A',asOf=str(date.today()),navFloor=80,navWarningFloor=warning,holdings=[
        dict(assetType='stock',market='CN',symbol='S',name='合成股票',account='A',currency='CNY',bookValue=100,equityBeta=1,equityBenchmark='CSI300'),
        dict(assetType='cash',symbol='CASH',name='现金',account='A',currency='CNY',bookValue=0,availableCash=0),
    ]))


def test_scenario_warning_is_not_reported_as_a_current_breach_and_does_not_change_cash():
    p=snapshot();r=diagnose(p);old=diagnose(snapshot(None))
    assert r['navThresholds']['rows'][0]['status']=='above_lines'
    assert r['navThresholds']['rows'][1]['status']=='warning'
    assert r['scenarios']==old['scenarios']
    assert r['nav']==old['nav']==100
    assert any(f['kind']=='nav_warning' for f in r['conclusion']['findings'])
    assert not any(f['kind']=='nav_floor' for f in r['conclusion']['findings'])
    assert not any(a.startswith('持仓快照') for a in r['alerts'])
    assert p.nav_warning_floor==95
    with pytest.raises(ValueError,match='预警线不能低于'):
        snapshot(79)


def test_missing_values_remain_unassessed_and_missing_floor_is_explicit():
    raw=snapshot().model_dump(mode='json',by_alias=True)
    raw['holdings'][0]['bookValue']=None
    r=diagnose(PortfolioSnapshotInput.model_validate(raw))
    assert all(row['status']=='unassessed' for row in r['navThresholds']['rows'])
    raw=snapshot(105).model_dump(mode='json',by_alias=True)
    raw['navFloor']=None
    r=diagnose(PortfolioSnapshotInput.model_validate(raw))
    assert any('尚未设定底线' in a for a in r['alerts'])
