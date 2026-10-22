import { calculateVariance, earningsDataStatus, type EarningsWorkbook } from './earningsWorkbench';
import { calculateValuationModel, type ValuationModel } from './valuationWorkbench';
import { priceComparisonIssue, scenarioReviewIssue, valuationReadiness } from './valuationReview';

export interface ResearchAnalysis {
  actionId: string;
  title: string;
  generatedAt: string;
  subject: { id: string; market: string; symbol: string; currency: string; asOf: string };
  summary: string;
  columns: string[];
  rows: (string | number | null)[][];
  warnings: string[];
}

export const earningsAnalysisActions = [{ id: 'earnings.compare', label: '核对实际与预期差' }];
export const valuationAnalysisActions = [
  { id: 'valuation.audit-inputs', label: '检查输入与核验缺口' },
  { id: 'valuation.test-scenarios', label: '对照三种情景' },
  { id: 'valuation.explain-sensitivity', label: '查看敏感性对照' },
];

export function compareEarnings(workbook: EarningsWorkbook): ResearchAnalysis {
  const status = earningsDataStatus(workbook);
  return {
    actionId: 'earnings.compare', title: '实际与预期差核对', generatedAt: new Date().toISOString(),
    subject: { id: workbook.id, ...workbook.security, asOf: workbook.fiscalPeriod.periodEnd || '' },
    summary: `${status.total} 项核心指标中，${status.comparable} 项期间和口径可比，${status.total - status.comparable} 项暂不可比。`,
    columns: ['指标', '单位', '实际', '一致预期', '差额', '相对差异（%）', '差异（bp）', '可比性 / 来源'],
    rows: workbook.metrics.map((metric, index) => {
      const variance = calculateVariance(metric).varianceVsConsensus;
      const row = status.rows[index]!;
      return [metric.label, metric.unit, metric.reported, metric.consensus, variance.amount, variance.percent, variance.bps,
        [row.comparisonIssue || row.comparisonNote || '期间和口径可比', row.originLabel].join('；')];
    }),
    warnings: ['只核对当前底稿，不刷新、不保存、不提升原文核验状态；无预期不能判定超预期。',
      '差额正负仅表示数值差异，不自动代表投资利好或利空；负预期以其绝对值作相对差异分母。'],
  };
}

export function analyzeValuation(model: ValuationModel, actionId: string): ResearchAnalysis {
  const calculated = calculateValuationModel(model);
  const readiness = valuationReadiness(model);
  const scenario = model.scenarios.find(row => row.id === model.selectedScenario)!;
  const warnings = ['只使用当前已录入模型，未采用资本编辑不计入；不改情景选择、不保存、不代替人工确认或独立审计。',
    '计算时间不是数据日期。每股价值仅在对应情景和资本依据确认后展示，仍属研究试算，不是目标价。'];
  const priceIssue = priceComparisonIssue(model);
  if (priceIssue) warnings.push(priceIssue);
  const report: ResearchAnalysis = {
    actionId, title: '', generatedAt: new Date().toISOString(),
    subject: { id: model.id, ...model.security, asOf: model.asOf },
    summary: '', columns: [], rows: [], warnings,
  };
  if (actionId === 'valuation.audit-inputs') {
    const statusLabel = { pass: '通过规则检查', warning: '待核对', fail: '不通过' };
    const checks = calculated.auditChecks;
    return { ...report, title: '输入与核验缺口',
      summary: `${checks.length} 项规则检查，${checks.filter(row => row.status !== 'pass').length} 项需处理。规则通过不等于原文已审计。`,
      columns: ['检查项', '状态', '依据 / 待办'],
      rows: checks.map(row => [row.label, statusLabel[row.status],
        row.id === 'scenario-review' && !readiness.assumptionsConfirmed
          ? scenarioReviewIssue(model, scenario) || row.message : row.message]),
    };
  }
  if (actionId === 'valuation.test-scenarios') {
    const labels = { bear: '悲观', base: '基准', bull: '乐观' };
    const runs = model.scenarios.map(row => {
      const candidate = { ...model, selectedScenario: row.id };
      return { scenario: row, ready: valuationReadiness(candidate), result: calculateValuationModel(candidate).result };
    });
    return { ...report, title: '三情景对照',
      summary: `${runs.filter(row => row.ready.ready).length}/${runs.length} 个情景满足人工确认门槛；未改变页面选中的${labels[model.selectedScenario]}情景。`,
      columns: ['情景', 'WACC（%）', '终值增长（%）', `每股价值（${model.security.currency}）`, '相对股价差异（%）', '核验状态'],
      rows: runs.map(({ scenario: row, ready, result }) => [labels[row.id], row.waccPct, row.terminalGrowthPct,
        result.impliedPrice, result.impliedReturnPct, ready.ready ? '满足人工确认门槛（非独立审计）' : [
          !ready.assumptionsConfirmed ? scenarioReviewIssue(model, row) || '情景未确认或确认已失效' : '',
          ...ready.capital.filter(item => item.issue).map(item => `${item.label}：${item.issue}`),
        ].filter(Boolean).join('；')]),
    };
  }
  if (actionId === 'valuation.explain-sensitivity') {
    const grid = calculated.sensitivity;
    const prices = grid.impliedPrices.flat().filter((value): value is number => value !== null && Number.isFinite(value));
    return { ...report, title: 'WACC × 终值增长敏感性对照',
      summary: prices.length ? `${prices.length} 个可计算组合，每股价值区间 ${Math.min(...prices).toFixed(2)}–${Math.max(...prices).toFixed(2)} ${model.security.currency}；这是假设网格，不是置信区间。` : '当前没有可展示的每股敏感性结果，请先核验情景与资本输入；不以零代替缺失。',
      columns: ['WACC（%） / 终值增长', ...grid.terminalGrowthPct.map(value => `${value}%`)],
      rows: grid.waccPct.map((wacc, index) => [wacc, ...grid.impliedPrices[index]!]),
      warnings: [...warnings, '矩阵单位为证券币种/股，其他经营假设固定；WACC 不大于终值增长的组合不计算。非概率预测，也不是各驱动的因果归因。'],
    };
  }
  throw new Error('当前页未提供此分析操作');
}
