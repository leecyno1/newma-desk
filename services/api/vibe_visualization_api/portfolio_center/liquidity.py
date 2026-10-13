"""User-declared settlement plans, separate from current cash and NAV."""
from collections import defaultdict
from datetime import date


def compile_liquidity_plan(rows: list[dict], as_of: date, deadline: date | None, base_currency: str, scenarios: list[dict]) -> dict:
    items = []
    receipts: dict[str, float] = defaultdict(float)
    cash_pairs = {(r['account'], r['currency']) for r in rows if r['assetType'] == 'cash' and r['availableCash'] is not None and r['baseValue'] is not None}
    for row in rows:
        amount, day, account, source = (row.get(k) for k in ('proceedsAmount', 'proceedsDate', 'proceedsAccount', 'proceedsSource'))
        if amount is None and not any((day, account, source)):
            continue
        fx = 1 if row['currency'] == base_currency else row['fxToBase']
        value = amount * fx if amount is not None and fx is not None else None
        missing = []
        if amount is None:
            missing.append('预计净到账金额')
        if not day:
            missing.append('预计到账日')
        if not account or not account.strip():
            missing.append('明确收款账户')
        if not source or not source.strip():
            missing.append('具体到账依据')
        if fx is None:
            missing.append('折算汇率')
        if missing:
            status, note = 'incomplete', '缺少' + '、'.join(missing) + '，未计入条件测算'
        elif date.fromisoformat(day) <= as_of:
            status, note = 'reconcile', '到账日已到或早于快照，请先核对是否已计入现金；本次不重复计入'
        elif deadline is None:
            status, note = 'no_deadline', '未设资金观察日，无法判断是否赶得上资金需求'
        elif date.fromisoformat(day) > deadline:
            status, note = 'late', '晚于资金观察日，不能用于该日前的资金需求'
        elif (account, row['currency']) not in cash_pairs:
            status, note = 'account_unverified', '未提供收款账户同币种可用现金，不能假设账户、币种或调拨可用'
        else:
            status, note = 'conditional', '仅在列示计划全额如期到账的假设下纳入；未经独立确认，不是现有现金'
            receipts[account] += value
        items.append({'name': row['name'], 'symbol': row['symbol'], 'holdingAccount': row['account'], 'currency': row['currency'], 'amount': amount, 'baseAmount': value, 'date': day, 'receivingAccount': account, 'source': source, 'status': status, 'note': note})
    projected = []
    for scenario in scenarios:
        for cash in scenario['cashByAccount']:
            if cash['account'] not in receipts:
                continue
            incoming = receipts[cash['account']]
            projected.append({'scenario': scenario['label'], 'account': cash['account'], 'currentStressRemaining': cash['remaining'], 'plannedReceipts': incoming,
                              'conditionalRemaining': cash['remaining'] + incoming if cash['remaining'] is not None else None})
    return {'deadline': deadline.isoformat() if deadline else None, 'items': items, 'projections': projected, 'accountReservesIncluded': True,
            'basis': '仅评估用户列示的预计净变现款，未执行卖出、赎回或转账，未确认开放日、赎回受理、暂停赎回及结算规则。计划款不增加当前净资产或现有可用现金，也未重算变现后的剩余持仓和对冲。条件余额已扣该账户已分配预留；组合层面未分配预留仍须另留，不能替代前述当前现金压力。资金观察日前如发生追保，未来到账不能自动解决当时缺口。外币仅按快照汇率折算，不保证即时换汇或充抵保证金。'}
