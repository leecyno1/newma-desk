import type { ResearchIdea } from './ideaFunnel';
import type { ResearchArchiveIndex } from './researchArchive';
import type { ResearchAnalysis } from './researchAnalysis';

const substantive = (value: string) => Boolean(value.trim()) && !/^(待补充|待定义|待确认|待核验|待命名|新增|关键筛选指标|说明该条件|记录候选进入|定义可复核)/.test(value.trim());
const validDate = (value: string) => /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0, 10) === value;
export function ideaSourceUrl(value?: string) {
  try { const url = new URL(value || ''); return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : null; } catch { return null; }
}
export function reviewIdea(idea: ResearchIdea, index: ResearchArchiveIndex | null = null, today = new Date().toISOString().slice(0, 10)) {
  const usableSources = idea.sources.filter(source => ['available', 'verified'].includes(source.status)
    && substantive(source.label) && validDate(source.asOf) && source.asOf <= today && ideaSourceUrl(source.url));
  const sourceIds = new Set(usableSources.map(source => source.id));
  const supported = (ids: string[]) => ids.some(id => sourceIds.has(id));
  const supports = idea.signals.filter(signal => signal.direction === 'supports' && substantive(signal.summary) && supported(signal.sourceIds));
  const challenges = idea.signals.filter(signal => signal.direction === 'challenges' && substantive(signal.summary) && supported(signal.sourceIds));
  const checks = [
    { label: '研究问题', pass: substantive(idea.researchQuestion), detail: '明确需要验证的问题，不能用占位文字代替' },
    { label: '正反假设', pass: substantive(idea.initialHypothesis) && substantive(idea.opposingHypothesis), detail: '同时记录支持解释与足以推翻它的另一种解释' },
    { label: '研究时点', pass: substantive(idea.whyNow) && substantive(idea.marketMayMiss), detail: '说明为何现在研究，以及市场可能遗漏什么' },
    { label: '支持证据', pass: supports.length > 0, detail: `${supports.length} 条信号关联了有日期、可打开的来源；存在链接不等于核验原文` },
    { label: '反方证据', pass: challenges.length > 0, detail: `${challenges.length} 条挑战信号关联了有日期、可打开的来源；反方假设本身不是反方证据` },
    { label: '证伪条件', pass: idea.risks.some(risk => substantive(risk.statement) && substantive(risk.earlyWarning) && substantive(risk.falsificationCondition)), detail: '给出风险、领先预警与可观察的证伪条件' },
    { label: '下一步任务', pass: idea.nextActions.some(action => action.status !== 'skipped' && substantive(action.label) && substantive(action.completionStandard)
      && action.label !== '核验候选的基础事实与来源' && action.completionStandard !== '关键数据具备来源、截至日期和口径'), detail: '至少一项未跳过的任务具有具体任务和完成标准；人工标记完成不等于成果已核验' },
  ];
  const reference = index?.entries.find(entry => entry.sourceModId === idea.handoff.targetModId && entry.artifactId === idea.handoff.artifactId);
  const matched = Boolean(reference && reference.security?.market.toUpperCase() === idea.security.market.trim().toUpperCase()
    && reference.security?.symbol.toUpperCase() === idea.security.symbol.trim().toUpperCase() && !['archived', 'invalidated', 'stale', 'unknown'].includes(reference.status));
  const handoff = matched ? '已找到同证券目标档案；仅确认存在，不代表研究或交接内容已完成'
    : !index || index.truncated || index.unavailableSources?.includes(idea.handoff.targetModId) ? '档案未完整核对，交接结果未知'
      : reference ? '目标档案的证券或状态不匹配' : '未找到对应目标档案';
  const blockers = checks.filter(check => !check.pass).map(check => check.label);
  const overdue = idea.nextActions.filter(action => action.status === 'pending' && action.dueAt && validDate(action.dueAt) && action.dueAt < today);
  const dueToday = idea.nextActions.filter(action => action.status === 'pending' && action.dueAt === today);
  return { checks, blockers, ready: blockers.length === 0, usableSourceCount: usableSources.length, supports: supports.length, challenges: challenges.length,
    overdue, dueToday, handoff, reference: matched ? reference : undefined,
    warnings: ['评分为用户主观研究优先级，不是投资收益、胜率或客观证据质量。',
      '来源状态为用户记录；本核对不联网搜索、不核验原文，也不自动创建目标档案。',
      ...(idea.sources.some(source => ['stale', 'unavailable'].includes(source.status)) ? ['有陈旧或不可用来源，未计入可用证据。'] : []),
      ...(idea.nextActions.some(action => action.dueAt && !validDate(action.dueAt)) ? ['部分任务日期无效，未按未逾期处理，请修正。'] : [])] };
}

export const ideaAnalysisActions = [{ id: 'idea.audit-screen', label: '核对证据与推进条件' }, { id: 'idea.prepare-handoff', label: '准备交接清单（不创建档案）' }];
export function analyzeIdea(input: { idea: ResearchIdea; index: ResearchArchiveIndex | null }, actionId: string): ResearchAnalysis {
  const { idea, index } = input; const review = reviewIdea(idea, index);
  const handoff = actionId === 'idea.prepare-handoff';
  return { actionId, title: handoff ? '深度研究交接清单' : '机会池证据与推进核对', generatedAt: new Date().toISOString(),
    subject: { id: idea.id, ...idea.security, asOf: idea.origin.asOf },
    summary: `${review.checks.filter(check => check.pass).length}/${review.checks.length} 项推进条件具备；${review.overdue.length} 项任务逾期，${review.dueToday.length} 项今日到期。${review.ready ? '可以安排进一步研究，不构成投资结论。' : `先补：${review.blockers.join('、')}。`}`,
    columns: handoff ? ['交接项目', '当前内容'] : ['核对项', '结果', '依据与下一步'],
    rows: handoff ? [ ['研究对象', `${idea.security.market}:${idea.security.symbol} ${idea.security.name}`], ['研究问题', idea.researchQuestion],
      ['支持假设', idea.initialHypothesis], ['反方假设', idea.opposingHypothesis], ['尚缺条件', review.blockers.join('、') || '表单层条件具备，仍须核验原文'],
      ['目标模块', idea.handoff.targetModId], ['已有档案核对', review.handoff],
      ...idea.nextActions.filter(action => action.status === 'pending').map(action => [action.label, `${action.completionStandard}；期限：${action.dueAt || '未指定'}`]),
    ] : review.checks.map(check => [check.label, check.pass ? '具备（待原文核验）' : '待补', check.detail]),
    warnings: review.warnings,
  };
}
