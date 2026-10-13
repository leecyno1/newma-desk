import type { PortfolioDashboard, PortfolioPerformanceInput, PortfolioPerformanceResult, PortfolioPosition } from './types';

export type RiskStatus = 'passed' | 'triggered' | 'unassessed' | 'missing-data' | 'expired';
export const RISK_LABELS: Record<RiskStatus, string> = { passed: '通过', triggered: '触发', unassessed: '未评估', 'missing-data': '缺数据', expired: '已过期' };
export interface RiskCheck {
  id: string; label: string; status: RiskStatus; value: string; detail: string;
  severity: 'medium' | 'high' | 'critical';
}
export const DEFAULT_RISK_INPUT = { currency: 'CNY', lookbackWeeks: 156, riskFreeRatePct: 2 };
const DAY = 86400000;
const fmt = (value: number) => Number(value.toFixed(2)).toLocaleString('zh-CN');
export const lossPct = (signedReturn: number) => Math.max(0, -signedReturn);
function age(value: string | null | undefined, now: number) { return value ? now - Date.parse(value) : NaN; }

export function quoteStatus(positions: PortfolioPosition[], now = Date.now()): RiskStatus {
  if (!positions.length) return 'unassessed';
  if (positions.some(p => p.price == null || p.price <= 0 || p.marketValue == null || !Number.isFinite(p.marketValue) || !Number.isFinite(age(p.quoteAsOf, now)))) return 'missing-data';
  if (positions.some(p => age(p.quoteAsOf, now) > 4 * DAY || age(p.quoteAsOf, now) < -DAY)) return 'expired';
  return 'passed';
}

export function concentrationGroups(dashboard: PortfolioDashboard, now = Date.now()) {
  return [...new Set(dashboard.positions.map(p => p.currency))].map(currency => {
    const positions = dashboard.positions.filter(p => p.currency === currency);
    const merged = new Map<string, { symbol: string; name: string; market: string; value: number }>();
    for (const position of positions) {
      const key = `${position.market}:${position.symbol}`;
      const item = merged.get(key) || { symbol: position.symbol, name: position.name, market: position.market, value: 0 };
      item.value += position.marketValue ?? 0;
      merged.set(key, item);
    }
    const total = [...merged.values()].reduce((sum, p) => sum + p.value, 0);
    const rows = [...merged.values()].map(p => ({ ...p, weight: total > 0 ? p.value / total * 100 : 0 })).sort((a,b) => b.weight - a.weight);
    const hhi = rows.reduce((sum, p) => sum + (p.weight / 100) ** 2, 0);
    const status = total <= 0 && positions.length ? 'missing-data' : quoteStatus(positions, now);
    return { currency, status: status as RiskStatus, rows, total, top: rows[0]?.weight ?? 0, top3: rows.slice(0,3).reduce((sum,p) => sum + p.weight,0), effective: hhi ? 1 / hhi : 0, hhi };
  });
}

function holdingBasis(positions: PortfolioPosition[]) {
  return positions.map(p => [p.accountId, p.market, p.symbol, p.currency, p.quantity, p.averageCost].join(':')).sort().join('|');
}
export function historyValidity(dashboard: PortfolioDashboard, input: PortfolioPerformanceInput, result?: PortfolioPerformanceResult | null, now = Date.now()): { status: RiskStatus; reason: string } {
  const positions = dashboard.positions.filter(p => p.currency === input.currency);
  if (!positions.length) return { status: 'unassessed', reason: '当前币种没有持仓' };
  if (!result || result.currency !== input.currency) return { status: 'unassessed', reason: '尚未计算此币种的历史风险' };
  if (!result.basisPositions?.length) return { status: 'expired', reason: '旧结果没有持仓基准，请重新计算' };
  if (holdingBasis(positions) !== holdingBasis(result.basisPositions) || input.lookbackWeeks !== result.lookbackWeeks || input.riskFreeRatePct !== result.riskFreeRatePct)
    return { status: 'expired', reason: '持仓或分析条件已变化，请重新计算' };
  if (result.method !== 'quantstats-inspired-weekly' || result.timeframe !== '1w') return { status: 'expired', reason: '分析方法已变化，请重新计算' };
  if (age(result.generatedAt, now) > DAY) return { status: 'expired', reason: '评估生成已超过 24 小时，请重新计算' };
  if (!result.metrics || result.status !== 'ready' || result.coverageWeightPct < 99.99 || result.observations < input.lookbackWeeks)
    return { status: 'missing-data', reason: '历史覆盖或连续样本不足，指标仅供局部参考' };
  if (!Number.isFinite(age(result.asOf, now))) return { status: 'missing-data', reason: '缺少历史数据截止日期' };
  if (age(result.asOf, now) > 10 * DAY || age(result.asOf, now) < -DAY) return { status: 'expired', reason: '周线截止已超过 10 天或日期异常' };
  if (quoteStatus(positions, now) !== 'passed') return { status: quoteStatus(positions, now), reason: '当前行情缺失、缺时间或过期，无法确认当前权重' };
  const total = positions.reduce((sum,p) => sum + (p.marketValue ?? 0),0);
  const basisTotal = result.basisPositions.reduce((sum,p) => sum + (p.marketValue ?? 0),0);
  if (total <= 0 || basisTotal <= 0) return { status: 'missing-data', reason: '缺少估值权重基准' };
  if (positions.some(p => {
    const old = result.basisPositions!.find(b => b.accountId === p.accountId && b.market === p.market && b.symbol === p.symbol);
    return !old || Math.abs((p.marketValue ?? 0) / total - (old.marketValue ?? 0) / basisTotal) > 0.0001;
  })) return { status: 'expired', reason: '估值权重已变化，请重新计算' };
  return { status: 'passed', reason: '持仓、权重、币种、窗口和方法一致；当前权重模拟，不是账户实际回撤' };
}

export function evaluateRisk(dashboard: PortfolioDashboard, input: PortfolioPerformanceInput = DEFAULT_RISK_INPUT, result?: PortfolioPerformanceResult | null, now = Date.now()) {
  const policy = dashboard.riskPolicy;
  const groups = concentrationGroups(dashboard, now);
  const checks: RiskCheck[] = [];
  for (const group of groups) {
    for (const [id, label, value, limit, hit] of [
      ['single', '单一证券限额', group.top, policy.singlePositionLimitPct, group.top > policy.singlePositionLimitPct],
      ['top3', '前三证券限额', group.top3, policy.topThreeLimitPct, group.top3 > policy.topThreeLimitPct],
      ['count', '有效持仓数', group.effective, policy.minEffectivePositions, group.effective < policy.minEffectivePositions],
    ] as const) {
      checks.push({ id: `${id}-${group.currency}`, label: `${group.currency} ${label}`, status: group.status === 'passed' ? hit ? 'triggered' : 'passed' : group.status, value: group.status === 'passed' ? `${fmt(value)}${id === 'count' ? '' : '%'}` : '—', detail: `${id === 'count' ? '下限' : '上限'} ${limit}${id === 'count' ? '' : '%'}；同证券跨账户合并，按币种市值计算`, severity: 'high' });
    }
  }
  if (!groups.length) checks.push({ id: 'holdings', label: '持仓风险', status: 'unassessed', value: '—', detail: '请先在交易流水中录入持仓', severity: 'medium' });
  const unpriced = dashboard.positions.filter(p => p.price == null).length;
  checks.push({ id: 'quote', label: '行情覆盖与时效', status: unpriced > policy.maxUnpricedPositions ? 'triggered' : quoteStatus(dashboard.positions, now), value: `${unpriced} 只缺价`, detail: `缺价上限 ${policy.maxUnpricedPositions} 只；缺时间不通过；行情超过 4 个自然日标记过期`, severity: 'medium' });
  checks.push({ id: 'fx', label: '全组合币种折算', status: !groups.length ? 'unassessed' : dashboard.currencies.length > 1 ? 'missing-data' : 'passed', value: `${dashboard.currencies.length} 币种`, detail: '没有汇率快照时不汇总不同币种的名义金额；分币种评估仍可使用', severity: 'medium' });
  const deficits = dashboard.currencies.filter(c => c.cash < -0.01);
  checks.push({ id: 'cash', label: '现金约束', status: !dashboard.currencies.length ? 'unassessed' : !policy.allowNegativeCash && deficits.length ? 'triggered' : 'passed', value: deficits.map(c => `${c.currency} ${fmt(c.cash)}`).join(' / ') || '无负现金', detail: policy.allowNegativeCash ? '限额允许负现金；不是融资合规认定' : '不允许负现金', severity: 'critical' });
  const mismatches = dashboard.orders.filter(order => {
    const executions = dashboard.activities.filter(a => a.orderId === order.id && ['buy','sell'].includes(a.type));
    return (order.status === 'filled' && !executions.length) || Math.abs(executions.reduce((sum,a) => sum + (a.quantity || 0),0) - order.filledQuantity) > 0.000001;
  }).length;
  checks.push({ id: 'ledger', label: '委托成交一致性', status: mismatches ? 'triggered' : 'passed', value: `${mismatches} 项异常`, detail: '委托成交数量与账本核对；不是券商对账认证', severity: 'high' });
  for (const currency of groups.map(g => g.currency)) {
    const conditions = { ...input, currency };
    const valid = historyValidity(dashboard, conditions, result, now);
    for (const [id,label,value,limit] of [
      ['drawdown','最大回撤', result?.metrics ? lossPct(result.metrics.maxDrawdownPct) : 0, policy.maxDrawdownLimitPct],
      ['var95','95% 周度 VaR', result?.metrics ? lossPct(result.metrics.valueAtRisk95Pct) : 0, policy.var95LimitPct],
    ] as const) checks.push({ id: `${id}-${currency}`, label: `${currency} ${label}`, status: valid.status === 'passed' ? value > limit ? 'triggered' : 'passed' : valid.status, value: valid.status === 'passed' ? `${fmt(value)}%` : '—', detail: `损失上限 ${limit}%；${valid.reason}`, severity: 'high' });
  }
  checks.push({ id: 'liquidity', label: '退出流动性', status: groups.length ? 'missing-data' : 'unassessed', value: '—', detail: '缺少 ADV、盘口、停牌状态；结算规则不能替代退出天数', severity: 'medium' });
  const count = (status: RiskStatus) => checks.filter(c => c.status === status).length;
  const status: RiskStatus = count('triggered') ? 'triggered' : !groups.length ? 'unassessed' : count('expired') ? 'expired' : count('missing-data') ? 'missing-data' : count('unassessed') ? 'unassessed' : 'passed';
  return { status, label: RISK_LABELS[status], checks, passed: count('passed'), triggered: count('triggered'), gaps: checks.filter(c => !['passed','triggered'].includes(c.status)).length, input, note: '规则通过不等于组合安全；处置和豁免不消除客观风险。' };
}

export const STRESS_SCENARIOS = [
  { name: '全球权益回撤', shocks: { CN: -10, HK: -10, US: -10 } },
  { name: '中国风险偏好冲击', shocks: { CN: -8, HK: -12, US: -2 } },
  { name: '海外利率冲击', shocks: { CN: -3, HK: -6, US: -12 } },
];
export function stressResults(dashboard: PortfolioDashboard, now = Date.now()) {
  return concentrationGroups(dashboard, now).flatMap(group => STRESS_SCENARIOS.map(scenario => ({
    currency: group.currency, scenario: scenario.name, shocks: scenario.shocks, status: group.status,
    impactPct: group.status === 'passed' ? group.rows.reduce((sum,p) => sum + p.weight / 100 * scenario.shocks[p.market as 'CN'|'HK'|'US'], 0) : null,
  })));
}

export function concentrationDetail(dashboard: PortfolioDashboard, now = Date.now()) {
  return concentrationGroups(dashboard, now).map(group => {
    let cumulativeWeight = 0;
    const usable = group.status === 'passed';
    return { ...group, rows: group.rows.map(row => {
      cumulativeWeight += row.weight;
      return { ...row,
        cumulativeWeight: usable ? cumulativeWeight : null,
        headroomPct: usable ? dashboard.riskPolicy.singlePositionLimitPct - row.weight : null,
        excessValue: usable ? Math.max(0, row.value - group.total * dashboard.riskPolicy.singlePositionLimitPct / 100) : null,
        concentrationContributionPct: usable && group.hhi > 0 ? (row.weight / 100) ** 2 / group.hhi * 100 : null,
        accounts: [...new Set(dashboard.positions.filter(p => p.currency === group.currency && p.market === row.market && p.symbol === row.symbol).map(p => dashboard.accounts.find(a => a.id === p.accountId)?.name || p.accountId))],
      };
    }) };
  });
}

export function capitalExposure(dashboard: PortfolioDashboard, now = Date.now()) {
  return dashboard.currencies.map(currency => {
    const positions = dashboard.positions.filter(p => p.currency === currency.currency);
    const usable = !positions.length || quoteStatus(positions, now) === 'passed';
    const invested = usable ? positions.reduce((sum,p) => sum + (p.marketValue ?? 0),0) : null;
    const nav = invested == null ? null : invested + currency.cash;
    const buyOrders = dashboard.orders.filter(o => o.currency === currency.currency && ['submitted','partial'].includes(o.status) && o.side === 'buy');
    const pricedOrders = buyOrders.filter(o => o.limitPrice != null);
    const knownCommitment = pricedOrders.reduce((sum,o) => sum + Math.max(0,o.quantity-o.filledQuantity) * o.limitPrice!,0);
    return {
      currency: currency.currency, invested, cash: currency.cash, nav,
      grossExposurePct: nav != null && nav > 0 && invested != null ? invested/nav*100 : null,
      cashPct: nav != null && nav > 0 ? currency.cash/nav*100 : null,
      knownCommitment, unpricedOrders: buyOrders.length-pricedOrders.length,
      cashAfterKnownOrders: currency.cash-knownCommitment,
      note: '简化净资产=持仓市值+账本现金，非券商可用资金，不含未记账负债；委托仅统计已报/部分成交限价买单的未成交额，未计费用。',
    };
  });
}

export function historyDiagnostics(result?: PortfolioPerformanceResult | null) {
  if (!result?.series.length) return { episodes: [], worstWeeks: [], currentDrawdownPct: null, recoveryNeededPct: null };
  type Episode = { peak: string; trough: string; recovery: string | null; depthPct: number; weeks: number };
  const episodes: Episode[]=[];
  const weekly: Array<{label:string; returnPct:number}>=[];
  let previous = 1, peakLabel='窗口起点', active: Episode | undefined;
  for (const point of result.series) {
    weekly.push({label:point.label,returnPct:previous > 0 ? (point.equity/previous-1)*100 : 0});
    previous=point.equity;
    if (point.drawdownPct < -0.00001) {
      if (!active) active={peak:peakLabel,trough:point.label,recovery:null,depthPct:point.drawdownPct,weeks:0};
      active.weeks += 1;
      if (point.drawdownPct < active.depthPct) { active.depthPct=point.drawdownPct; active.trough=point.label; }
    } else {
      if (active) { active.recovery=point.label; episodes.push(active); active=undefined; }
      peakLabel=point.label;
    }
  }
  if (active) episodes.push(active);
  const currentDrawdownPct=result.series.at(-1)!.drawdownPct;
  return { episodes: episodes.sort((a,b)=>a.depthPct-b.depthPct), worstWeeks: weekly.sort((a,b)=>a.returnPct-b.returnPct).slice(0,5), currentDrawdownPct,
    recoveryNeededPct: currentDrawdownPct > -100 ? (1/(1+currentDrawdownPct/100)-1)*100 : null };
}

export function scenarioImpact(dashboard: PortfolioDashboard, shocks: Record<'CN'|'HK'|'US',number>, now=Date.now()) {
  return concentrationGroups(dashboard,now).map(group => {
    const usable=group.status==='passed';
    const rows=group.rows.map(p=>({symbol:p.symbol,name:p.name,market:p.market,weight:usable?p.weight:null,shockPct:shocks[p.market as 'CN'|'HK'|'US'],pnl:usable?p.value*shocks[p.market as 'CN'|'HK'|'US']/100:null}));
    const pnl=usable?rows.reduce((sum,p)=>sum+(p.pnl||0),0):null;
    const cash=dashboard.currencies.find(c=>c.currency===group.currency)?.cash||0;
    const nav=usable?group.total+cash:null;
    return {currency:group.currency,status:group.status,invested:usable?group.total:null,nav,pnl,
      lossOnInvestedPct:pnl!=null&&group.total>0?-pnl/group.total*100:null,
      lossOnNavPct:pnl!=null&&nav!=null&&nav>0?-pnl/nav*100:null,rows:rows.sort((a,b)=>(a.pnl||0)-(b.pnl||0))};
  });
}
