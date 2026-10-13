import { expect,it } from 'vitest';
import { compareSnapshots } from './SnapshotChanges';
import type { Holding,Snapshot } from './PortfolioDiagnosis';
const holding:Holding={assetType:'bond',market:'CN',symbol:'001234',name:'合成债券',account:'A',currency:'CNY',bookValue:100,fxToBase:null,availableCash:null,equityBeta:null,equityBenchmark:'',ratePnlPerBp:-1,direction:null,notional:null,source:'合成依据'};
const snapshot:Snapshot={name:'合成组合',asOf:'2026-09-13',baseCurrency:'CNY',navFloor:null,nearTermOutflow:0,holdings:[holding]};

it('records explicit product assignment without rewriting holdings or legacy snapshots',()=>{
  expect(compareSnapshots(snapshot,{...snapshot,productId:''}).parameters).toEqual([]);
  const diff=compareSnapshots(snapshot,{...snapshot,productId:'P001'});
  expect(diff.parameters).toEqual([{label:'产品归属编号',before:undefined,after:'P001'}]);
  expect(diff.changed).toEqual([]);
  expect(snapshot.productId).toBeUndefined();
});

it('includes warning-line changes in confirmation and treats legacy absence as unset',()=>{
  expect(compareSnapshots(snapshot,{...snapshot,navWarningFloor:null}).parameters).toEqual([]);
  expect(compareSnapshots(snapshot,{...snapshot,navWarningFloor:95}).parameters).toEqual([{label:'净值预警线',before:undefined,after:95}]);
});

it('compares unknown versus zero and all changed input fields without mutating sources',()=>{
  const next={...snapshot,navFloor:0,holdings:[{...holding,bookValue:0,proceedsAmount:0,source:'新依据\n第二行'}]};
  const diff=compareSnapshots(snapshot,next);
  expect(diff.parameters).toEqual([{label:'净值底线',before:null,after:0}]);
  expect(diff.changed[0].fields.map(f=>f.label)).toEqual(['账面金额','依据','预计到账金额']);
  expect(diff.added).toEqual([]);expect(diff.removed).toEqual([]);
  expect(holding.bookValue).toBe(100);
});

it('ignores row order and distinguishes identity changes from ordinary currency changes',()=>{
  const second={...holding,symbol:'002345'};
  const original={...snapshot,holdings:[holding,second]};
  expect(compareSnapshots(original,{...snapshot,holdings:[second,holding]}).changed).toEqual([]);
  const moved={...holding,account:'B'};
  const diff=compareSnapshots(snapshot,{...snapshot,holdings:[moved]});
  expect(diff.added).toEqual([moved]);expect(diff.removed).toEqual([holding]);expect(diff.changed).toEqual([]);
  expect(compareSnapshots(snapshot,{...snapshot,holdings:[{...holding,currency:'USD'}]}).changed[0].fields).toEqual([{label:'币种',before:'CNY',after:'USD'}]);
});

it('normalizes absent optional values, and detects sensitivity and date changes',()=>{
  const same={...holding,proceedsAmount:null,proceedsSource:''};
  expect(compareSnapshots(snapshot,{...snapshot,holdings:[same]})).toEqual({parameters:[],added:[],removed:[],changed:[]});
  const diff=compareSnapshots(snapshot,{...snapshot,asOf:'2026-09-14',holdings:[{...holding,ratePnlPerBp:null}]});
  expect(diff.parameters[0].label).toBe('持仓截止日');
  expect(diff.changed[0].fields[0]).toEqual({label:'整笔利率每基点损益',before:-1,after:null});
});

it('includes custom assumptions in the save comparison while retaining legacy defaults',()=>{
  expect(compareSnapshots(snapshot,{...snapshot,additionalScenarios:[]}).parameters).toEqual([]);
  const diff=compareSnapshots(snapshot,{...snapshot,additionalScenarios:[{label:'降息',equityShockPct:0,rateShockBp:-100}]});
  expect(diff.parameters).toEqual([{label:'自定义压力情景',before:'仅基础情景',after:'降息：权益 0%，利率 -100bp'}]);
});

it('compares account allocations, treating absence as unassigned',()=>{
  expect(compareSnapshots(snapshot,{...snapshot,outflowAllocations:[]}).parameters).toEqual([]);
  const diff=compareSnapshots(snapshot,{...snapshot,outflowAllocations:[{account:'A',amount:50}]});
  expect(diff.parameters).toEqual([{label:'账户预留分配',before:'未分配到账户',after:'A：50 CNY'}]);
});
