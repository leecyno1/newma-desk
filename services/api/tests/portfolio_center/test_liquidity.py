from datetime import date, timedelta

import pytest

from vibe_visualization_api.portfolio_center.diagnosis import PortfolioSnapshotInput, PortfolioImportInput, parse_import, diagnose


def snapshot():
    today = date.today()
    return PortfolioSnapshotInput.model_validate(dict(name='到账计划验收', asOf=str(today), cashNeedDate=str(today+timedelta(days=3)), holdings=[
        dict(assetType='fund', market='CN', symbol='F-TEST', name='合成基金', account='证券', currency='CNY', bookValue=50000, equityBeta=0, ratePnlPerBp=0, proceedsAmount=15000, proceedsDate=str(today+timedelta(days=2)), proceedsAccount='期货', proceedsSource='合成假设：预计净款到账'),
        dict(assetType='bond_future', market='CN', symbol='T-TEST', name='合成对冲', account='期货', currency='CNY', bookValue=0, direction='short', ratePnlPerBp=400, expiryDate=str(today+timedelta(days=90))),
        dict(assetType='cash', symbol='CASH-A', name='现金', account='证券', currency='CNY', bookValue=0, availableCash=0),
        dict(assetType='cash', symbol='CASH-B', name='现金', account='期货', currency='CNY', bookValue=10000, availableCash=10000),
    ]))


def test_plans_never_inflate_nav_or_current_cash_and_do_not_remove_margin_alerts():
    data = snapshot()
    report = diagnose(data)
    assert report['nav'] == 60000
    assert report['liquidityPlan']['items'][0]['status'] == 'conditional'
    projected = next(p for p in report['liquidityPlan']['projections'] if p['scenario'] == '权益上涨，利率下行')
    assert projected['currentStressRemaining'] == -10000
    assert projected['conditionalRemaining'] == 5000
    assert any('期货 可用现金不足' in a for a in report['alerts'])
    data.holdings[0].proceeds_amount = None
    data.holdings[0].proceeds_date = None
    data.holdings[0].proceeds_account = data.holdings[0].proceeds_source = ''
    original = diagnose(data)
    assert original['nav'] == report['nav']
    assert original['scenarios'] == report['scenarios']
    assert original['alerts'] == report['alerts']
    assert original['liquidityPlan']['items'] == []  # Fund market value is not a receipt.
    assert original['conclusion'] == report['conclusion']
    shortages = [f for f in report['conclusion']['findings'] if f['kind'] == 'cash_shortfall']
    assert len(shortages) == 1  # Two alternative loss scenarios, one account finding.
    assert shortages[0]['amount'] == -10000
    assert shortages[0]['rowIndices'] == [1, 3]
    assert report['conclusion']['cashJudgment'] == '存在缺口'


def test_conclusion_does_not_call_missing_cash_or_floor_safe():
    data = snapshot()
    data.holdings[-1].available_cash = None
    report = diagnose(data)
    assert report['conclusion']['cashJudgment'] == '未评估完整'
    assert report['conclusion']['navJudgment'] == '未评估完整'
    assert any(f['kind'] == 'inputs' for f in report['conclusion']['findings'])


def test_conclusion_prioritizes_largest_account_shortfall_without_netting():
    data = snapshot()
    data.holdings.append(data.holdings[1].model_copy(update={'account': '证券', 'rate_pnl_per_bp': 500}))
    findings = diagnose(data)['conclusion']['findings']
    cash = [f for f in findings if f['kind'] == 'cash_shortfall']
    assert [(f['account'], f['amount']) for f in cash] == [('证券', -25000), ('期货', -10000)]


def test_conclusion_checks_unshocked_floor_and_marks_history():
    data = snapshot()
    data.nav_floor = 70000
    data.as_of = date.today()-timedelta(days=8)
    report = diagnose(data)
    assert report['conclusion']['historical'] is True
    assert report['conclusion']['navJudgment'] == '存在缺口'
    assert any('尚未施加' in a for a in report['alerts'])
    assert len([f for f in report['conclusion']['findings'] if f['kind'] == 'nav_floor']) == 1


@pytest.mark.parametrize('field,value,status', [
    ('proceeds_date', date.today(), 'reconcile'),
    ('proceeds_date', date.today()+timedelta(days=4), 'late'),
    ('proceeds_date', None, 'incomplete'),
    ('proceeds_source', '', 'incomplete'),
    ('proceeds_account', '未提供现金的账户', 'account_unverified'),
])
def test_late_past_missing_and_unverified_receipts_are_not_credited(field,value,status):
    data = snapshot()
    setattr(data.holdings[0], field, value)
    plan = diagnose(data)['liquidityPlan']
    assert plan['items'][0]['status'] == status
    assert plan['projections'] == []


def test_receiving_account_currency_and_deadline_must_be_explicit():
    data = snapshot()
    data.holdings[0].currency = 'USD'
    data.holdings[0].fx_to_base = 7
    assert diagnose(data)['liquidityPlan']['items'][0]['status'] == 'account_unverified'
    data.cash_need_date = None
    assert diagnose(data)['liquidityPlan']['items'][0]['status'] == 'no_deadline'
    data.holdings[0].fx_to_base = None
    assert diagnose(data)['liquidityPlan']['items'][0]['status'] == 'incomplete'


def test_import_accepts_chinese_receipt_fields_and_rejects_double_counted_cash():
    parsed = parse_import(PortfolioImportInput(name='导入', asOf=date.today(), text=f'资产类型,代码,名称,账户,币种,预计到账金额,预计到账日,收款账户,到账依据\n基金,F,基金,A,CNY,100,{date.today()+timedelta(days=2)},B,合成计划'))
    assert parsed.holdings[0].proceeds_amount == 100
    invalid = snapshot().model_dump(by_alias=True)
    invalid['holdings'][2]['proceedsAmount'] = 100
    with pytest.raises(ValueError, match='已到账现金'):
        PortfolioSnapshotInput.model_validate(invalid)
    invalid = snapshot().model_dump(by_alias=True)
    invalid['cashNeedDate'] = date.today()-timedelta(days=1)
    with pytest.raises(ValueError, match='资金观察日'):
        PortfolioSnapshotInput.model_validate(invalid)


def test_account_reserve_is_deducted_once_and_receipts_do_not_erase_alert():
    original = snapshot()
    original.near_term_outflow = 6000
    baseline = diagnose(original)
    data = original.model_dump(by_alias=True)
    data['outflowAllocations'] = [dict(account='期货', amount=5000)]
    report = diagnose(PortfolioSnapshotInput.model_validate(data))
    assert report['unallocatedOutflow'] == 1000
    assert report['nav'] == baseline['nav']
    for before, after in zip(baseline['scenarios'], report['scenarios']):
        assert after['totalPnl'] == before['totalPnl']
        assert after['cashAfterKnownNeeds'] == before['cashAfterKnownNeeds']
    cash = next(c for c in report['scenarios'][1]['cashByAccount'] if c['account']=='期货')
    assert cash['remaining'] == -15000
    assert cash['reservedOutflow'] == 5000
    projected = next(p for p in report['liquidityPlan']['projections'] if p['scenario']=='权益上涨，利率下行')
    assert projected['conditionalRemaining'] == 0
    assert report['conclusion']['cashJudgment'] == '存在缺口'


def test_positive_aggregate_cash_does_not_hide_payment_account_shortfall():
    data = snapshot().model_dump(by_alias=True)
    data['holdings'][1]['ratePnlPerBp'] = 0
    data['holdings'][2].update(bookValue=100000,availableCash=100000)
    data.update(nearTermOutflow=30000,outflowAllocations=[dict(account='期货',amount=20000)])
    report = diagnose(PortfolioSnapshotInput.model_validate(data))
    assert report['scenarios'][0]['cashAfterKnownNeeds'] == 80000
    assert report['conclusion']['findings'][0]['account'] == '期货'
    assert report['conclusion']['findings'][0]['amount'] == -10000
    data['holdings'][3]['availableCash'] = None
    assert diagnose(PortfolioSnapshotInput.model_validate(data))['scenarios'][0]['cashAfterKnownNeeds'] is None


@pytest.mark.parametrize('allocations', [[dict(account='不存在',amount=1)],[dict(account='期货',amount=101)],[dict(account='期货',amount=-1)],[dict(account='期货',amount=1)]*2])
def test_invalid_account_reserves_are_rejected(allocations):
    data = snapshot().model_dump(by_alias=True)
    data.update(nearTermOutflow=100,outflowAllocations=allocations)
    with pytest.raises(ValueError):
        PortfolioSnapshotInput.model_validate(data)
