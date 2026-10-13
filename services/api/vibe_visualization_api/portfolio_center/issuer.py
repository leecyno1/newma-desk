"""Direct legal-issuer exposure, not a credit model or fund look-through."""
from collections import defaultdict


def compile_issuer_exposure(rows: list[dict], nav: float | None) -> dict:
    direct = [r for r in rows if r['assetType'] in {'stock', 'bond'}]
    funds = [r for r in rows if r['assetType'] == 'fund']
    names_by_security: dict[tuple, set] = defaultdict(set)

    def identity(row):
        return row['assetType'], row['market'], row['symbol']

    def issuer(row):
        name = row.get('issuer', '').strip()
        return '' if name.upper() in {'', '未知', '未提供', '--', 'N/A'} else name

    for row in direct:
        if issuer(row):
            names_by_security[identity(row)].add(issuer(row))
    conflicts = {key for key, names in names_by_security.items() if len(names) > 1}
    buckets: dict[str, list[dict]] = defaultdict(list)
    unmatched = []
    for row in direct:
        name = issuer(row)
        if not name or identity(row) in conflicts:
            unmatched.append({'name': row['name'], 'symbol': row['symbol'], 'market': row['market'], 'account': row['account'], 'baseValue': row['baseValue'], 'reason': '同一证券的发行人填写冲突：' + ' / '.join(sorted(names_by_security[identity(row)])) if identity(row) in conflicts else '未提供明确发行人'})
        else:
            buckets[name].append(row)
    items = []
    for name, members in buckets.items():
        known = sum(r['baseValue'] or 0 for r in members)
        complete = all(r['baseValue'] is not None for r in members)
        by_type = {}
        for kind in ('stock', 'bond'):
            selected = [r for r in members if r['assetType'] == kind]
            by_type[kind] = sum(r['baseValue'] for r in selected) if all(r['baseValue'] is not None for r in selected) else None
        items.append({'issuer': name, 'knownBaseValue': known, 'baseValue': known if complete else None,
                      'stockValue': by_type['stock'], 'bondValue': by_type['bond'],
                      'navWeightPct': known / nav * 100 if complete and nav is not None and nav > 0 else None,
                      'securityCount': len({identity(r) for r in members}), 'accounts': sorted({r['account'] for r in members}),
                      'crossAsset': any(r['assetType'] == 'stock' and (r['baseValue'] is None or r['baseValue'] > 0) for r in members) and any(r['assetType'] == 'bond' and (r['baseValue'] is None or r['baseValue'] > 0) for r in members),
                      'members': [{'name': r['name'], 'market': r['market'], 'symbol': r['symbol'], 'account': r['account'], 'assetType': r['assetType'], 'baseValue': r['baseValue'], 'source': r['source']} for r in members]})
    direct_total = sum(r['baseValue'] for r in direct) if all(r['baseValue'] is not None for r in direct) else None
    mapped_known = sum(i['knownBaseValue'] for i in items)
    return {'items': sorted(items, key=lambda i: -i['knownBaseValue']), 'unmatched': unmatched,
            'coverage': {'directRows': len(direct), 'identifiedRows': len(direct)-len(unmatched),
                         'valuedRows': sum(r['baseValue'] is not None for r in direct),
                         'identifiedValuePct': mapped_known / direct_total * 100 if direct_total is not None and direct_total > 0 else None,
                         'unmatchedKnownValue': sum(r['baseValue'] or 0 for r in unmatched),
                         'excludedFundRows': len(funds), 'excludedFundKnownValue': sum(r['baseValue'] or 0 for r in funds)},
            'basis': '仅按导入的完整发行人名称精确匹配；未核验法律实体，未归并集团、担保人、SPV 或别名。股票与债券市值分列，不代表相同受偿顺位或违约损失。基金、现金、负债及期货不参与此归属，期货对冲不抵销发行人信用暴露。未知归属与基金穿透可能增加实际集中度。'}
