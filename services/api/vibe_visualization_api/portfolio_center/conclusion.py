"""A deterministic reading guide for the saved calculation, not a new risk model."""


def compile_conclusion(report: dict) -> dict:
    scenarios = report['scenarios']
    rows = report['rows']
    findings = []

    def add(kind, title, detail, target, **evidence):
        findings.append(dict(kind=kind, title=title, detail=detail, target=target, **evidence))

    # Compare alternative scenarios; never sum losses across them.
    accounts = sorted({c['account'] for s in scenarios for c in s['cashByAccount']})
    for account in accounts:
        candidates = [(c['remaining'], s['label']) for s in scenarios for c in s['cashByAccount']
                      if c['account'] == account and c['remaining'] is not None]
        if candidates:
            amount, scenario = min(candidates)
            if amount < 0:
                add('cash_shortfall', f'{account}：优先核对现金缺口',
                    '所列情景中最差已知账户余额，已扣该账户的预留支出；不抵销其他账户资金，也不计入预计到账款。先核对可用额度、期货亏损及预留需求。',
                    'cash', amount=amount, scenario=scenario, account=account,
                    rowIndices=[i for i, r in enumerate(rows) if r['account'] == account])
    findings.sort(key=lambda f: f['amount'])  # Same base currency: largest shortfall first.
    totals = [(s['cashAfterKnownNeeds'], s['label']) for s in scenarios if s['cashAfterKnownNeeds'] is not None]
    if totals and report['nearTermOutflow'] > 0:
        amount, scenario = min(totals)
        if amount < 0:
            add('cash_reserve', '近期支出预留不足', '合计已扣近期需留资金；与账户缺口有重叠，不能再次相加。',
                'cash', amount=amount, scenario=scenario)

    floors = [(s['floorHeadroom'], s['label']) for s in scenarios if s['floorHeadroom'] is not None]
    if report['navHeadroom'] is not None:
        floors.append((report['navHeadroom'], '持仓快照（未施加冲击）'))
    if floors:
        amount, scenario = min(floors)
        if amount < 0:
            add('nav_floor', '净值底线存在缺口', '列示快照及已建模情景中的最低底线余量，需复核承受能力；不是发生概率或最大损失。',
                'scenarios', amount=amount, scenario=scenario)

    threshold_rows = report.get('navThresholds', {}).get('rows', [])
    touches = [r for r in threshold_rows if r['status'] == 'floor_reached']
    warnings = [r for r in threshold_rows if r['status'] == 'warning']
    if not any(f['kind'] == 'nav_floor' for f in findings):
        if touches:
            add('nav_floor_touch', '已触及净值底线', '已知快照或情景的底线余量为零，须优先复核；不是自动止损指令。',
                'thresholds', amount=0, scenario=touches[0]['label'])
        elif warnings:
            worst = min(warnings, key=lambda r: r['warningHeadroom'])
            add('nav_warning', '触发净值预警', '已知快照或情景触及预警线。请区分当前事实与压力假设；未设置底线时不能据此判断底线安全。',
                'thresholds', amount=worst['warningHeadroom'], scenario=worst['label'])

    cash_complete = bool(scenarios) and all(s['cashAfterKnownNeeds'] is not None for s in scenarios)
    nav_complete = report['navHeadroom'] is not None and bool(scenarios) and all(s['floorHeadroom'] is not None for s in scenarios)
    affected = [i for i, r in enumerate(rows) if r['gaps']]
    if not cash_complete or not nav_complete or affected:
        missing = []
        if not cash_complete:
            missing.append('账户可用现金或期货亏损需求未齐备')
        if report['navFloor'] is None:
            missing.append('未设净值底线')
        if report['nav'] is None:
            missing.append('持仓估值或汇率未齐备')
        if any(s['totalPnl'] is None for s in scenarios):
            missing.append('情景敏感度未齐备')
        if affected:
            missing.append(f'{len(affected)} 行持仓有字段待核验，详见输入依据')
        add('inputs', '补齐判断所需的输入',
            '；'.join(missing) + '。缺失项不按零处理，不能据此判断整体安全。',
            'inputs', rowIndices=affected)

    other_alerts = [a for a in report['alerts'] if not any(a.startswith(s['label'] + '：') for s in scenarios)]
    if other_alerts:
        add('holding_warnings', f'核验持仓与研究提示 {len(other_alerts)} 项',
            '；'.join(other_alerts[:2]) + ('；其余见完整提示。' if len(other_alerts) > 2 else '。'),
            'warnings', alerts=other_alerts)

    cash_breach = any(f['kind'] in {'cash_shortfall', 'cash_reserve'} for f in findings)
    nav_breach = any(f['kind'] == 'nav_floor' for f in findings)
    has_warning = cash_breach or nav_breach or bool(report['alerts'])
    headline = ('已识别风险提示，先核对下列缺口与持仓依据' if has_warning else
                '证据仍有缺口，暂不能判断组合安全' if report['gaps'] or not cash_complete or not nav_complete else
                '列示情景未触及现金或净值底线；不代表整体安全')
    return dict(
        version='calculation-conclusion-v1', asOf=report['asOf'], basis='saved-calculation',
        historical=report['status'] == '历史参考', headline=headline, findings=findings,
        cashJudgment='存在缺口' if cash_breach else '未评估完整' if not cash_complete else '列示情景未见缺口',
        navJudgment='存在缺口' if nav_breach else '触及底线' if touches else '触发预警，底线仍需核验' if warnings else '未评估完整' if not nav_complete else '列示情景未触底线',
        boundary='仅解读这份快照的计算。预计到账不消除当前预警；基金上游证据仅作独立线索，未用于补齐敏感度。信用、基差、汇率与保证金比例上调等仍未覆盖。',
    )
