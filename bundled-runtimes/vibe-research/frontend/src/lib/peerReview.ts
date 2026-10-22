import type { EquityResearchSnapshot } from './api';
import type { MetricStatistics, PeerComparisonCase, PeerMember, PeerMetric, PeerRow, PeerSecurity } from './peerComparison';
import type { ResearchAnalysis } from './researchAnalysis';

function quantile(sorted: number[], p: number) {
  if (!sorted.length) return null;
  const position = (sorted.length - 1) * p;
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  const fraction = position - lower;
  return sorted[lower]! * (1 - fraction) + sorted[upper]! * fraction;
}

export function calculatePeerStatistics(rows: PeerRow[], metrics: PeerMetric[]) {
  return Object.fromEntries(metrics.map(metric => {
    const values = rows.filter(row => !row.isTarget).map(row => row.values[metric.id])
      .filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
      .sort((left, right) => left - right);
    return [metric.id, { max: values[values.length - 1] ?? null, q75: quantile(values, 0.75), median: quantile(values, 0.5),
      q25: quantile(values, 0.25), min: values[0] ?? null } satisfies MetricStatistics];
  }));
}

const evidenceIds: Record<string, string[]> = {
  pe: ['valuation.pe_ttm', 'valuation.pe'], pb: ['valuation.pb'],
  revenueGrowthPct: ['growth.revenue_yoy'], netProfitGrowthPct: ['growth.net_profit_yoy'],
  roePct: ['profitability.roe'], grossMarginPct: ['profitability.gross_margin'], netMarginPct: ['profitability.net_margin'],
  cashConversionPct: ['derived.cash_conversion'], debtRatioPct: ['balance_sheet.debt_ratio', 'derived.debt_ratio'],
  valuationPercentile: ['derived.valuation_percentile_midpoint'],
};

export function peerSecurityKey(security: PeerSecurity) {
  const market = security.market.trim().toUpperCase();
  let symbol = security.symbol.trim().toUpperCase();
  if (market === 'HK') symbol = symbol.replace(/\.HK$/, '').padStart(5, '0');
  return `${market}:${symbol}`;
}

export function peerRequestSymbol(member: PeerMember) {
  const market = member.security.market.trim().toUpperCase();
  const symbol = member.security.symbol.trim().toUpperCase();
  if (market === 'CN' && /^\d{6}$/.test(symbol)) return symbol;
  if (market === 'HK' && /^\d{1,5}(\.HK)?$/.test(symbol)) return `${symbol.replace(/\.HK$/, '').padStart(5, '0')}.HK`;
  if (market === 'US' && /^[A-Z][A-Z0-9.-]{0,14}$/.test(symbol)) return symbol;
  throw new Error(`${member.security.name || symbol}：请核对市场和代码；当前刷新支持 CN 六位代码、HK 数字代码和 US 交易代码。`);
}

export function peerRowFromSnapshot(member: PeerMember, snapshot: EquityResearchSnapshot): PeerRow {
  if (peerSecurityKey(member.security) !== peerSecurityKey(snapshot.identity)
    || member.security.currency.trim().toUpperCase() !== snapshot.identity.currency.toUpperCase()) {
    throw new Error(`${member.security.symbol}：返回证券、市场或币种不匹配，未采用。`);
  }
  const values: Record<string, number | null> = {};
  const metricEvidence: NonNullable<PeerRow['metricEvidence']> = {};
  for (const [metricId, ids] of Object.entries(evidenceIds)) {
    const evidence = ids.map(id => snapshot.evidenceLedger.find(row => row.id === id)).find(Boolean);
    if (evidence && (typeof evidence.source !== 'string'
      || (evidence.asOf != null && typeof evidence.asOf !== 'string')
      || (evidence.unit != null && typeof evidence.unit !== 'string')
      || (evidence.note != null && typeof evidence.note !== 'string'))) {
      throw new Error(`${member.security.symbol}：指标来源结构异常，未采用。`);
    }
    values[metricId] = typeof evidence?.value === 'number' && Number.isFinite(evidence.value) ? evidence.value : null;
    if (evidence) metricEvidence[metricId] = { id: evidence.id, source: evidence.source, asOf: evidence.asOf || null, unit: evidence.unit || null, note: evidence.note };
  }
  const dates = [...new Set(Object.entries(metricEvidence).filter(([key]) => !['pe', 'pb', 'valuationPercentile'].includes(key))
    .map(([, value]) => value.asOf).filter(Boolean))];
  return { security: snapshot.identity, isTarget: member.role === 'target', period: dates.length === 1 ? dates[0]! : dates.length ? '多期间' : '待确认',
    values, metricEvidence, scores: snapshot.comparisonProfile?.scores || {},
    coverageRatio: Object.values(values).filter(value => value !== null).length / Object.keys(evidenceIds).length,
    sourceIds: [`research:${peerSecurityKey(member.security)}`], warnings: snapshot.gaps || [],
  };
}

export function reviewPeerComparison(draft: PeerComparisonCase) {
  const members = draft.members.filter(member => member.included);
  const targets = members.filter(member => member.role === 'target');
  const targetMember = targets.length === 1 ? targets[0] : undefined;
  const issues: string[] = [];
  if (!targetMember) issues.push('必须且只能纳入一家目标公司');
  const keys = members.map(member => peerSecurityKey(member.security));
  const duplicate = keys.filter((key, index) => keys.indexOf(key) !== index);
  if (duplicate.length) issues.push(`重复证券未计入：${[...new Set(duplicate)].join('、')}`);
  const rows = members.flatMap(member => {
    const key = peerSecurityKey(member.security);
    if (!member.security.symbol.trim() || duplicate.includes(key)) return [];
    const matches = draft.rows.filter(row => peerSecurityKey(row.security) === key && row.security.currency.toUpperCase() === member.security.currency.trim().toUpperCase());
    if (matches.length !== 1) { issues.push(`${key}：${matches.length ? '重复结果' : '缺少匹配数据'}，未计入`); return []; }
    return [{ ...matches[0]!, isTarget: member.role === 'target' }];
  });
  const target = targetMember ? rows.find(row => peerSecurityKey(row.security) === peerSecurityKey(targetMember.security)) : undefined;
  const peers = rows.filter(row => !row.isTarget);
  const metrics = draft.metrics.map(metric => {
    const targetValue = target?.values[metric.id] ?? null;
    const targetEvidence = target?.metricEvidence?.[metric.id];
    const exclusions: string[] = [];
    const check = (row: PeerRow): string => {
      const value = row.values[metric.id];
      const evidence = row.metricEvidence?.[metric.id];
      if (typeof value !== 'number' || !Number.isFinite(value)) return '数值缺失';
      if (['pe', 'pb'].includes(metric.id) && value <= 0) return '非正估值倍数不适用';
      if (metric.id === 'valuationPercentile') return '历史窗口与截止日未统一，不做横向分布';
      if (!evidence?.source || !evidence.asOf || !targetEvidence?.asOf) return '逐项来源或日期缺失';
      if (evidence.unit !== metric.unit || targetEvidence.unit !== metric.unit) return '单位口径不匹配';
      if (evidence.asOf.slice(0, 10) !== targetEvidence.asOf.slice(0, 10)) return '报告期或行情日不一致';
      if (!/^\d{4}-\d{2}-\d{2}/.test(evidence.asOf) || !Number.isFinite(Date.parse(evidence.asOf))) return '来源日期无法确认';
      if (evidence.id !== targetEvidence.id || evidence.source !== targetEvidence.source) return '指标定义或供应商不同，需另行核对';
      if (metric.id === 'pe' && evidence.id !== 'valuation.pe_ttm') return 'PE 分母期间未确认';
      return '';
    };
    const targetIssue = target ? check(target) : '目标公司缺少匹配数据';
    const valid = peers.filter(row => {
      const reason = targetIssue || check(row);
      if (reason) exclusions.push(`${row.security.name}：${reason}`);
      return !reason;
    });
    const stats = calculatePeerStatistics(valid, [metric])[metric.id]!;
    // One peer is a single observation, not a useful distribution. Quartiles
    // remain hidden until four non-target observations are available.
    if (valid.length < 2) stats.median = null;
    if (valid.length < 4) { stats.q25 = null; stats.q75 = null; }
    const delta = typeof targetValue === 'number' && stats.median !== null ? targetValue - stats.median : null;
    return { id: metric.id, label: metric.label, unit: metric.unit, targetValue, targetIssue,
      sampleSize: valid.length, requestedPeers: members.filter(member => member.role !== 'target').length,
      statistics: stats, difference: delta, differenceUnit: metric.unit === '%' ? '百分点' : metric.unit,
      exclusions, note: targetIssue || (valid.length < 2 ? '同业不足2家，不生成中位差' : valid.length < 4 ? '小样本，四分位暂不展示' : '同日同源描述性分布，仍须核对业务可比性与累计/单季口径') };
  });
  return { rows, target, metrics, issues,
    statistics: Object.fromEntries(metrics.map(metric => [metric.id, metric.statistics])),
    policy: '仅统计当前纳入且证券/币种匹配的非目标公司；逐指标核对日期、单位、来源和定义。至少2家同业生成中位数，至少4家生成四分位。相同报告期末不证明累计/单季或财年口径一致；数值差异不是排名、买卖建议或目标价。',
  };
}

export const peerAnalysisActions = [{ id: 'peer.audit-comparability', label: '核对同业样本与口径' }];

export function analyzePeerComparison(draft: PeerComparisonCase): ResearchAnalysis {
  const review = reviewPeerComparison(draft);
  const comparable = review.metrics.filter(metric => metric.statistics.median !== null).length;
  return { actionId: 'peer.audit-comparability', title: '同业样本与口径核对', generatedAt: new Date().toISOString(),
    subject: { id: draft.id, ...(review.target?.security || draft.target), asOf: draft.period.asOf },
    summary: `${draft.metrics.length} 项指标中，${comparable} 项有至少2家同日同源有效同业；仅作描述性比较，未完成原文核验。`,
    columns: ['指标', '有效同业 / 拟纳入', '目标值', '同业中位数', '目标－中位数', '差值单位', '限制'],
    rows: review.metrics.map(metric => [metric.label, `${metric.sampleSize}/${metric.requestedPeers}`, metric.targetValue,
      metric.statistics.median, metric.difference, metric.differenceUnit, [metric.note, ...metric.exclusions].join('；')]),
    warnings: [review.policy, ...review.issues, '来源覆盖率不代表已核验；负PE/PB不进入倍数分布，真实零增长仍保留。只核对，不刷新、不保存、不改投资逻辑。'],
  };
}
