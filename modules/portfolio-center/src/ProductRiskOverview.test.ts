import { expect,it } from 'vitest';
import { productRiskSummary, productReviewFlags } from './ProductRiskOverview';
import type { ImportDiagnosis } from './PortfolioDiagnosis';

const record=(cash:Array<number|null>,productCash:number|null):ImportDiagnosis=>({report:{navHeadroom:100,scenarios:[{floorHeadroom:-50,cashAfterKnownNeeds:productCash,cashByAccount:cash.map((remaining,i)=>({account:`A${i}`,remaining}))}]}} as ImportDiagnosis);

it('keeps an account deficit visible when the product cash total is positive',()=>{
  const result=productRiskSummary(record([-900,10000],9100));
  expect(result).toMatchObject({cash:-900,account:'A0',cashComplete:true,productCash:9100,floor:-50,floorComplete:true});
});

it('retains known deficits while marking missing inputs, and shows unallocated reserves',()=>{
  expect(productRiskSummary(record([-900,null],null))).toMatchObject({cash:-900,cashComplete:false,productCash:null,productCashComplete:false});
  expect(productRiskSummary(record([100],-900))).toMatchObject({cash:100,productCash:-900});
});

it('separates snapshot thresholds from stress deficits and preserves incomplete historical warnings',()=>{
  const data=record([-900,null],100);
  data.snapshot={name:'产品',asOf:'2026-09-01',baseCurrency:'CNY',navFloor:200,nearTermOutflow:0,holdings:[]};
  Object.assign(data.report,{nav:300,gaps:[],coverage:{total:2,valued:2,sensitivity:1}});
  data.report.scenarios[0].label='权益上涨';
  expect(productRiskSummary(data).cashScenario).toBe('权益上涨');
  expect(productReviewFlags(data,Date.parse('2026-09-16T12:00:00'))).toEqual({current:false,scenario:true,cash:true,incomplete:true,stale:true});
  data.report.navHeadroom=0;
  expect(productReviewFlags(data).current).toBe(true);
});
