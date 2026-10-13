import { describe, expect, it } from 'vitest';
import { capitalExposure, concentrationDetail, concentrationGroups, DEFAULT_RISK_INPUT, evaluateRisk, historyDiagnostics, historyValidity, lossPct, scenarioImpact, stressResults } from './risk';
import type { PortfolioDashboard, PortfolioPerformanceResult } from './types';

const now = Date.parse('2026-09-11T08:00:00Z');
const time = new Date(now).toISOString();
const input = { ...DEFAULT_RISK_INPUT, lookbackWeeks: 52 };
function dashboard(): PortfolioDashboard {
  return {
    userId: 'risk-test', workspaceId: 'test', accounts: [], orders: [], activities: [],
    positions: [{ accountId: 'one', market: 'CN', symbol: '600519', name: '测试持仓', currency: 'CNY', quantity: 100, averageCost: 10, costValue: 1000, realizedPnl: 0, price: 10, marketValue: 1000, quoteAsOf: time }],
    currencies: [{ currency: 'CNY', cash: 0, costValue: 1000, marketValue: 1000, realizedPnl: 0, income: 0, fees: 0 }],
    analytics: { basis: 'market-value', byMarket: [], byCurrency: [], byAccount: [], concentration: { positionCount: 1, topPositionWeight: 100, topThreeWeight: 100, herfindahlIndex: 1, effectivePositionCount: 1 } },
    riskPolicy: { singlePositionLimitPct: 100, topThreeLimitPct: 100, minEffectivePositions: 1, maxDrawdownLimitPct: 15, var95LimitPct: 5, maxUnpricedPositions: 0, allowNegativeCash: false, updatedAt: time },
    riskActions: [], valuationStatus: 'live', updatedAt: time,
  };
}
function result(d: PortfolioDashboard): PortfolioPerformanceResult {
  return {
    status:'ready', method:'quantstats-inspired-weekly', currency:'CNY', timeframe:'1w', lookbackWeeks:52, riskFreeRatePct:2,
    observations:52, coverageWeightPct:100, basisPositions:structuredClone(d.positions), generatedAt:time, asOf:time, series:[], dataSources:['test'], missingAssets:[], warnings:[],
    metrics:{totalReturnPct:10, annualizedReturnPct:10, annualizedVolatilityPct:5, maxDrawdownPct:-2, maxDrawdownDurationWeeks:2, winRatePct:60, bestWeekPct:6, worstWeekPct:-2, valueAtRisk95Pct:6, conditionalValueAtRisk95Pct:4},
  };
}
describe('risk evidence', () => {
  it('decomposes concentration and excess exposure without confusing it with volatility risk', () => {
    const d=dashboard(); d.positions[0].marketValue=600;
    d.positions.push({...d.positions[0],symbol:'000001',marketValue:400});
    d.riskPolicy.singlePositionLimitPct=30;
    const [g]=concentrationDetail(d,now);
    expect(g.hhi).toBeCloseTo(0.52);
    expect(g.rows.map(r=>r.headroomPct)).toEqual([-30,-10]);
    expect(g.rows.map(r=>r.excessValue)).toEqual([300,100]);
    expect(g.rows.map(r=>r.cumulativeWeight)).toEqual([60,100]);
    expect(g.rows[0].concentrationContributionPct).toBeCloseTo(69.230769);
  });
  it('measures remaining limit-buy commitments separately from cash and nonpositive NAV', () => {
    const d=dashboard(); d.currencies[0].cash=-1000;
    d.orders=[{id:'test',accountId:'one',side:'buy',market:'CN',symbol:'600519',currency:'CNY',orderType:'limit',quantity:100,filledQuantity:40,limitPrice:10,timeInForce:'day',status:'partial',source:'manual',createdAt:time,updatedAt:time}];
    d.orders.push({...d.orders[0],id:'market',orderType:'market',limitPrice:null});
    const [c]=capitalExposure(d,now);
    expect(c.knownCommitment).toBe(600); expect(c.unpricedOrders).toBe(1);
    expect(c.cashAfterKnownOrders).toBe(-1600);
    expect(c.nav).toBe(0); expect(c.grossExposurePct).toBeNull();
  });
  it('separates recovered and open drawdowns and calculates the rebound needed', () => {
    const r=result(dashboard());
    r.series=[{label:'W1',equity:1.1,drawdownPct:0},{label:'W2',equity:0.99,drawdownPct:-10},{label:'W3',equity:1.1,drawdownPct:0},{label:'W4',equity:1.045,drawdownPct:-5}];
    const h=historyDiagnostics(r);
    expect(h.episodes).toEqual([{peak:'W1',trough:'W2',recovery:'W3',depthPct:-10,weeks:1},{peak:'W3',trough:'W4',recovery:null,depthPct:-5,weeks:1}]);
    expect(h.worstWeeks[0].label).toBe('W2'); expect(h.worstWeeks[0].returnPct).toBeCloseTo(-10);
    expect(h.recoveryNeededPct).toBeCloseTo(5.263157);
  });
  it('keeps scenario P&L in native currency and excludes unusable quotes', () => {
    const d=dashboard(); d.currencies[0].cash=1000;
    d.positions.push({...d.positions[0],market:'US',symbol:'AAPL',currency:'USD'});
    d.currencies.push({...d.currencies[0],currency:'USD',cash:-1000});
    const s=scenarioImpact(d,{CN:-20,HK:-10,US:5},now);
    expect(s[0]).toMatchObject({currency:'CNY',pnl:-200,lossOnInvestedPct:20,lossOnNavPct:10});
    expect(s[1]).toMatchObject({currency:'USD',pnl:50,lossOnInvestedPct:-5,lossOnNavPct:null});
    d.positions[0].quoteAsOf=undefined;
    expect(scenarioImpact(d,{CN:-20,HK:-10,US:5},now)[0].pnl).toBeNull();
  });
  it('never passes an empty or uncomputed portfolio', () => {
    const d = dashboard(); d.positions=[]; d.currencies=[];
    expect(evaluateRisk(d,input,undefined,now).status).toBe('unassessed');
    const checks = evaluateRisk(dashboard(),input,undefined,now).checks;
    expect(checks.find(c => c.id === 'var95-CNY')?.status).toBe('unassessed');
  });
  it('merges the same security across accounts', () => {
    const d = dashboard(); d.positions.push({...d.positions[0],accountId:'two'});
    const [group] = concentrationGroups(d,now);
    expect(group.rows).toHaveLength(1); expect(group.top).toBe(100); expect(group.effective).toBe(1);
  });
  it('does not pass concentration or stress using cost or undated quotes', () => {
    const d=dashboard(); d.positions[0].quoteAsOf=undefined;
    expect(concentrationGroups(d,now)[0].status).toBe('missing-data');
    expect(stressResults(d,now).every(s => s.impactPct === null)).toBe(true);
  });
  it('does not aggregate nominal multi-currency amounts', () => {
    const d=dashboard(); d.positions.push({...d.positions[0],market:'US',symbol:'AAPL',currency:'USD'}); d.currencies.push({...d.currencies[0],currency:'USD'});
    expect(evaluateRisk(d,input,undefined,now).checks.find(c => c.id==='fx')?.status).toBe('missing-data');
    expect(concentrationGroups(d,now).map(g => g.top)).toEqual([100,100]);
  });
  it('does not turn positive returns into VaR losses', () => {
    const d=dashboard();
    expect(lossPct(6)).toBe(0); expect(lossPct(-6)).toBe(6);
    expect(evaluateRisk(d,input,result(d),now).checks.find(c => c.id==='var95-CNY')).toMatchObject({status:'passed',value:'0%'});
  });
  it('invalidates changes in holdings, weights, currency and window', () => {
    const d=dashboard(); const r=result(d);
    expect(historyValidity(d,input,r,now).status).toBe('passed');
    d.positions[0].quantity+=1;
    expect(historyValidity(d,input,r,now).status).toBe('expired');
    expect(historyValidity(dashboard(),{...input,lookbackWeeks:104},r,now).status).toBe('expired');
    expect(historyValidity(dashboard(),input,{...r,currency:'USD'},now).status).toBe('unassessed');
    const weighted=dashboard(); weighted.positions.push({...weighted.positions[0],symbol:'000001'}); const old=result(weighted); weighted.positions[0].marketValue=2000;
    expect(historyValidity(weighted,input,old,now).status).toBe('expired');
  });
  it('rejects stale and partial historical evidence', () => {
    const d=dashboard(); const r=result(d);
    expect(historyValidity(d,input,{...r,status:'partial',coverageWeightPct:50},now).status).toBe('missing-data');
    expect(historyValidity(d,input,{...r,asOf:'2026-08-01'},now).status).toBe('expired');
    expect(historyValidity(d,input,{...r,generatedAt:'2026-09-09'},now).status).toBe('expired');
    expect(historyValidity(d,input,{...r,basisPositions:[]},now).status).toBe('expired');
  });
  it('applies current limits and retains a breach even with a waived action', () => {
    const d=dashboard(); d.riskPolicy.singlePositionLimitPct=30;
    d.riskActions=[{id:'one',ruleId:'single-CNY',severity:'high',status:'waived',title:'豁免',detail:'测试',owner:'经理',note:'短期例外',createdAt:time,updatedAt:time}];
    expect(evaluateRisk(d,input,result(d),now).checks.find(c=>c.id==='single-CNY')?.status).toBe('triggered');
  });
});
