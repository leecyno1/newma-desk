// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { blankPeerComparisonCase, calculatePeerStatistics, type PeerComparisonCase } from '@/lib/peerComparison';
import { analyzePeerComparison, peerRequestSymbol, peerRowFromSnapshot, peerSecurityKey, reviewPeerComparison } from '@/lib/peerReview';

export function peerCase(): PeerComparisonCase {
  const draft = blankPeerComparisonCase();
  draft.name = '测试同业';
  draft.members.forEach((member, index) => {
    member.security = { market: 'CN', symbol: ['600519', '000858', '600809'][index], name: ['目标', '同业甲', '同业乙'][index], currency: 'CNY' };
  });
  draft.target = draft.members[0].security;
  draft.rows = draft.members.map((member, index) => peerRowFromSnapshot(member, {
    identity: member.security, evidenceLedger: [
      { id: 'growth.revenue_yoy', source: 'synthetic-test', asOf: '2025-12-31', unit: '%', value: [100, 0, 20][index] },
      { id: 'valuation.pe_ttm', source: 'synthetic-test', asOf: '2026-10-19', unit: 'x', value: [30, 10, 20][index] },
    ], gaps: [],
  } as any));
  return draft;
}

describe('同业可比性核心口径', () => {
  it('目标排除，真实零保留，两个有效同业才展示中位数，差值为百分点', () => {
    const draft = peerCase();
    expect(calculatePeerStatistics(draft.rows, draft.metrics).revenueGrowthPct.median).toBe(10);
    const metric = reviewPeerComparison(draft).metrics[0];
    expect(metric).toMatchObject({ sampleSize: 2, targetValue: 100, difference: 90, differenceUnit: '百分点', statistics: { median: 10, q25: null, q75: null } });
    draft.members[2].included = false;
    expect(reviewPeerComparison(draft).metrics[0]).toMatchObject({ sampleSize: 1, requestedPeers: 1, difference: null, statistics: { min: 0, median: null } });
  });
  it('角色以当前成员为准，换代码和重复成员不混入旧结果', () => {
    const draft = peerCase(); draft.members[0].role = 'direct'; draft.members[1].role = 'target';
    expect(reviewPeerComparison(draft).metrics[0]).toMatchObject({ targetValue: 0, statistics: { median: 60 } });
    draft.members[2].security = { ...draft.members[2].security, symbol: '600000' };
    expect(reviewPeerComparison(draft).rows).toHaveLength(2);
    draft.members[2].security = draft.members[0].security;
    expect(reviewPeerComparison(draft).rows).toHaveLength(1);
  });
  it.each([
    ['asOf', '2025-09-30'], ['asOf', null], ['unit', 'ratio'], ['source', 'another-provider'], ['id', 'growth.revenue_quarter_yoy'],
  ])('%s不同或缺失不纳入比较', (field, value) => {
    const draft = peerCase(); (draft.rows[1].metricEvidence!.revenueGrowthPct as any)[field] = value;
    expect(reviewPeerComparison(draft).metrics[0].sampleSize).toBe(1);
  });
  it('负PE与未知PE期间排除，历史分位不横比', () => {
    const draft = peerCase(); draft.rows[1].values.pe = -10;
    const metric = reviewPeerComparison(draft).metrics.find(item => item.id === 'pe')!;
    expect(metric.sampleSize).toBe(1); expect(metric.exclusions.join()).toContain('非正');
    draft.rows.forEach(row => { row.metricEvidence!.pe.id = 'valuation.pe'; });
    expect(reviewPeerComparison(draft).metrics.find(item => item.id === 'pe')!.sampleSize).toBe(0);
    expect(reviewPeerComparison(draft).statistics.valuationPercentile.median).toBeNull();
  });
  it('至少四个非目标有效观察才展示四分位', () => {
    const draft = peerCase();
    for (const [symbol, value] of [['600000', 40], ['600001', 60]] as const) {
      const member = { ...draft.members[1], security: { ...draft.members[1].security, symbol } };
      draft.members.push(member); draft.rows.push({ ...draft.rows[1], security: member.security, values: { revenueGrowthPct: value } });
    }
    expect(reviewPeerComparison(draft).statistics.revenueGrowthPct).toEqual({ min: 0, max: 60, median: 30, q25: 15, q75: 45 });
  });
  it('单一证据账本生成数据，不拿另一份profile补零；拒绝证券错配', () => {
    const member = peerCase().members[0];
    const snapshot: any = { identity: member.security, evidenceLedger: [{ id: 'growth.revenue_yoy', value: '10', unit: '%', source: 'test', asOf: '2025-12-31' }], comparisonProfile: { values: { pe: 20 } } };
    expect(peerRowFromSnapshot(member, snapshot).values).toMatchObject({ revenueGrowthPct: null, pe: null });
    snapshot.identity = { ...snapshot.identity, currency: 'USD' };
    expect(() => peerRowFromSnapshot(member, snapshot)).toThrow('不匹配');
    const hk = { ...member, security: { ...member.security, market: 'HK', symbol: '700' } };
    expect(peerSecurityKey(hk.security)).toBe('HK:00700'); expect(peerRequestSymbol(hk)).toBe('00700.HK');
    expect(() => peerRequestSymbol({ ...hk, security: { ...hk.security, symbol: 'BAD' } })).toThrow('代码');
  });
  it('只读核对不会修改投资逻辑或保存，也不宣称原文已核验', () => {
    const draft = peerCase(); const before = structuredClone(draft);
    expect(analyzePeerComparison(draft).summary).toContain('未完成原文核验');
    expect(draft).toEqual(before);
  });
});
