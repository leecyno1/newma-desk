// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { compareEarnings, analyzeValuation } from '@/lib/researchAnalysis';
import { blankEarningsWorkbook } from '@/lib/earningsWorkbench';
import { blankValuationModel, calculateValuationModel } from '@/lib/valuationWorkbench';
import { activeCapitalFields, alignValuationYears, attachCapitalEvidence, confirmScenario } from '@/lib/valuationReview';

describe('当前底稿只读核对', () => {
  it('财报重算当前值，错期不比较、零预期不除零、负预期保留方向', () => {
    const workbook = blankEarningsWorkbook();
    workbook.metrics = [-10, 0, 100, 50].map((consensus, index) => ({ ...workbook.metrics[0]!,
      id: `test-${index}`, reported: index === 2 ? null : 10, consensus,
      reportedBasis: 'annual', consensusBasis: 'annual', periodEnd: '2025-12-31',
      consensusPeriodEnd: index === 3 ? '2024-12-31' : '2025-12-31',
      varianceVsConsensus: { amount: 999, percent: 999, bps: null },
    }));
    const original = structuredClone(workbook);
    const report = compareEarnings(workbook);
    expect(report.rows[0].slice(4, 6)).toEqual([20, 200]);
    expect(report.rows[1].slice(4, 6)).toEqual([10, null]);
    expect(report.rows[2].slice(4, 7)).toEqual([null, null, null]);
    expect(report.rows[3].slice(4, 7)).toEqual([null, null, null]);
    expect(report.summary).toContain('2 项期间和口径可比');
    expect(workbook).toEqual(original);
  });
  it('未确认估值不生成每股价值或敏感性，检查给出缺口', () => {
    const model = blankValuationModel();
    const report = analyzeValuation(model, 'valuation.test-scenarios');
    expect(report.rows).toHaveLength(3);
    expect(report.rows.every(row => row[3] === null && row[4] === null)).toBe(true);
    const sensitivity = analyzeValuation(model, 'valuation.explain-sensitivity');
    expect(sensitivity.rows).toHaveLength(5);
    expect(sensitivity.rows.every(row => row.slice(1).every(value => value === null))).toBe(true);
    const audit = analyzeValuation(model, 'valuation.audit-inputs');
    expect(audit.rows).toHaveLength(calculateValuationModel(model).auditChecks.length);
    expect(audit.rows.some(row => row[0] === '当前情景确认' && row[1] === '待核对')).toBe(true);
    expect(() => analyzeValuation(model, 'valuation.refresh-evidence')).toThrow('未提供');
  });
  it('逐情景遵循确认门槛，使用既有计算器且不改变选中情景和确认状态', () => {
    let model = blankValuationModel();
    model.security = { market: 'CN', symbol: 'TEST', name: '合成测试', currency: 'CNY' };
    model.historicals = [{ ...model.historicals[0]!, period: '2025A', revenue: 100 }];
    model = alignValuationYears(model);
    Object.assign(model.capitalInputs, { dilutedSharesM: 10, totalDebtM: 0, cashM: 0, excludedCashM: 0,
      nonOperatingAssetsM: 0, minorityInterestM: 0, otherClaimsM: 0, currentPrice: 10, currentPriceAsOf: model.asOf });
    for (const field of activeCapitalFields(model)) model = attachCapitalEvidence(model, field, {
      title: '合成测试资料', url: '', locator: '第 1 页', excerpt: '测试值，仅用于验收', method: '合成口径，不代表真实财务核验',
    });
    model.scenarios = model.scenarios.map(row => ({ ...row, rationale: '合成测试假设，验证情景计算' }));
    model = confirmScenario(model, 'base');
    const original = structuredClone(model);
    let report = analyzeValuation(model, 'valuation.test-scenarios');
    expect(report.rows[0][3]).toBeNull();
    expect(report.rows[1][3]).toBe(calculateValuationModel(model).result.impliedPrice);
    expect(report.rows[1][3]).not.toBeNull();
    expect(report.rows[2][3]).toBeNull();
    expect(model).toEqual(original);
    for (const id of ['bear', 'bull'] as const) model = confirmScenario(model, id);
    report = analyzeValuation(model, 'valuation.test-scenarios');
    expect(report.rows.every(row => typeof row[3] === 'number')).toBe(true);
    const matrix = analyzeValuation(model, 'valuation.explain-sensitivity');
    expect(matrix.rows.map(row => row.slice(1))).toEqual(calculateValuationModel(model).sensitivity.impliedPrices);
    expect(matrix.summary).toContain('不是置信区间');
    model.capitalInputs.currentPriceAsOf = '2026-01-01';
    expect(analyzeValuation(model, 'valuation.test-scenarios').rows.every(row => row[4] === null)).toBe(true);
  });
});
