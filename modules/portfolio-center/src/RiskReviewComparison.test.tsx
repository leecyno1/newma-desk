import '@testing-library/jest-dom/vitest';
import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react';
import {afterEach,expect,it,vi} from 'vitest';
import {comparisonRows,floorChangeExplanation,RiskReviewComparison} from './RiskReviewComparison';
import type {ImportDiagnosis} from './PortfolioDiagnosis';

const call=vi.hoisted(()=>vi.fn());
vi.mock('./api',()=>({callPortfolioImport:call}));
afterEach(()=>{cleanup();call.mockReset()});
const fixture=():ImportDiagnosis=>({snapshot:{productId:'A',name:'测试',asOf:'2026-09-15',baseCurrency:'CNY',nearTermOutflow:0,holdings:[],navFloor:200},report:{baseCurrency:'CNY',method:'v9',status:'test',asOf:'2026-09-15',knownBookValue:100,coverage:{total:0,valued:0,sensitivity:0},alerts:[],gaps:[],rows:[],concentrations:[],limitations:[],nav:100,navHeadroom:-100,nearTermOutflow:0,equityHedges:[],scenarios:[{label:'旧名称',equityShockPct:-10,rateShockBp:25,knownAssetPnl:-20,knownFuturesPnl:0,totalPnl:-20,stressNav:80,cashAfterKnownNeeds:-20,floorHeadroom:-120,cashByAccount:[{account:'期货账户',available:0,futuresLossDemand:20,remaining:-20}]}]}});

it('separates lowering the floor from changes in assets, without filling unknown NAV',()=>{
  const a=fixture(),b=fixture();b.snapshot.navFloor=50;
  expect(floorChangeExplanation(a,b)).toContain('安全垫变化 150 = 净资产变化 0 + 底线调整影响 150');
  expect(floorChangeExplanation(a,b)).toContain('不代表资产风险下降');
  b.report.nav=null;
  expect(floorChangeExplanation(a,b)).toContain('不能拆解');
});

it('publishes only loaded evidence and clears it on read failure and unmount',async()=>{
  const a=fixture(),b=fixture();a.id='source';b.id='review';b.report.nav=300;
  const listener=vi.fn();call.mockResolvedValueOnce(a).mockResolvedValueOnce(b);
  const view=render(<RiskReviewComparison sourceId="source" reviewId="review" identity={{userId:'u',workspaceId:'w'}} evidenceKey="action" onEvidence={listener}/>);
  expect(listener).toHaveBeenLastCalledWith('action',undefined);
  fireEvent.click(screen.getByRole('button',{name:'对照来源与复核指标'}));
  await waitFor(()=>expect(listener).toHaveBeenLastCalledWith('action',expect.objectContaining({source:expect.objectContaining({id:'source'}),review:expect.objectContaining({id:'review'}),metrics:expect.arrayContaining([expect.objectContaining({label:'账面净资产',before:100,after:300})])})));
  call.mockRejectedValue(new Error('无法读取'));
  fireEvent.click(screen.getByRole('button',{name:'重新读取指标对照'}));
  await screen.findByRole('alert');
  expect(listener).toHaveBeenLastCalledWith('action',undefined);
  view.unmount();
  expect(listener).toHaveBeenLastCalledWith('action',undefined);
});

it('matches shock parameters despite label edits and never fills a missing account with zero',()=>{
  const a=fixture(),b=fixture();b.report.scenarios[0].label='新名称';b.report.scenarios[0].floorHeadroom=80;b.report.scenarios[0].cashByAccount=[];
  const rows=comparisonRows(a,b);
  expect(rows.find(r=>r.label.includes('· 底线余量'))).toMatchObject({before:-120,after:80});
  expect(rows.find(r=>r.label.includes('期货账户'))).toMatchObject({before:-20,after:undefined});
  b.report.scenarios[0].rateShockBp=50;
  expect(comparisonRows(a,b).filter(r=>r.label.includes('· 底线余量'))).toEqual([
    expect.objectContaining({before:-120,after:undefined}),expect.objectContaining({before:undefined,after:80}),
  ]);
});

it('loads on demand and refuses incompatible currency or methodology',async()=>{
  const a=fixture(),b=fixture();b.report.baseCurrency='USD';
  call.mockResolvedValueOnce(a).mockResolvedValueOnce(b);
  render(<RiskReviewComparison sourceId="source" reviewId="review" identity={{userId:'u',workspaceId:'w'}}/>);
  expect(call).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'对照来源与复核指标'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('基准币种或计算方法不同');
  expect(screen.queryByRole('table')).toBeNull();
  b.report.baseCurrency='CNY';b.report.method='v8';
  call.mockResolvedValueOnce(a).mockResolvedValueOnce(b);
  fireEvent.click(screen.getByRole('button',{name:'对照来源与复核指标'}));
  expect(await screen.findByRole('alert')).toHaveTextContent('基准币种或计算方法不同');
  expect(screen.queryByRole('table')).toBeNull();
});
