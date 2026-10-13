from copy import deepcopy

import pytest

from vibe_visualization_api.portfolio_center.issuer import compile_issuer_exposure


def rows():
    common = dict(market='CN', currency='CNY', account='A', source='合成测试', issuer='发行主体甲')
    return [
        dict(common, assetType='stock', symbol='S', name='股票', baseValue=100),
        dict(common, assetType='stock', symbol='S', name='股票', account='B', baseValue=100),
        dict(common, assetType='bond', symbol='B1', name='债券一', baseValue=200),
        dict(common, assetType='bond', symbol='B2', name='债券二', account='B', baseValue=300),
        dict(common, assetType='bond', symbol='B3', name='未知债券', issuer='', baseValue=100),
        dict(common, assetType='fund', symbol='F', name='基金', baseValue=400),
        dict(common, assetType='bond_future', symbol='T', name='对冲期货', baseValue=0),
        dict(common, assetType='cash', symbol='CASH', name='现金', baseValue=100),
    ]


def test_issuer_aggregates_accounts_and_securities_not_funds_or_hedges():
    data = rows()
    before = deepcopy(data)
    result = compile_issuer_exposure(data, 1300)
    item = result['items'][0]
    assert item['stockValue'] == 200
    assert item['bondValue'] == 500
    assert item['baseValue'] == 700
    assert item['securityCount'] == 3
    assert item['accounts'] == ['A', 'B']
    assert item['navWeightPct'] == pytest.approx(700/1300*100)
    assert item['crossAsset']
    assert result['coverage']['identifiedValuePct'] == 87.5
    assert result['coverage']['unmatchedKnownValue'] == 100
    assert result['coverage']['excludedFundKnownValue'] == 400
    assert data == before


def test_conflicting_issuers_on_same_security_are_not_silently_resolved():
    data = rows()
    data[1]['issuer'] = '发行主体乙'
    result = compile_issuer_exposure(data, 1300)
    assert result['items'][0]['baseValue'] == 500
    assert not result['items'][0]['crossAsset']
    assert len(result['unmatched']) == 3
    assert sum('冲突' in r['reason'] for r in result['unmatched']) == 2


def test_missing_valuation_is_not_replaced_with_zero_and_nav_ratio_needs_positive_nav():
    data = rows()
    data[2]['baseValue'] = None
    result = compile_issuer_exposure(data, None)
    assert result['items'][0]['baseValue'] is None
    assert result['items'][0]['bondValue'] is None
    assert result['items'][0]['knownBaseValue'] == 500
    assert result['coverage']['identifiedValuePct'] is None
    assert result['items'][0]['navWeightPct'] is None
    assert compile_issuer_exposure(rows(), 0)['items'][0]['navWeightPct'] is None
    assert compile_issuer_exposure(rows(), -100)['items'][0]['navWeightPct'] is None


def test_exact_names_only_and_unknown_placeholders_remain_unassigned():
    data = rows()
    data[0]['issuer'] = '甲公司简称'
    data[1]['issuer'] = '未知'
    result = compile_issuer_exposure(data, 1300)
    assert len(result['items']) == 2  # No fuzzy name/group/guarantor inference.
    assert len(result['unmatched']) == 2
