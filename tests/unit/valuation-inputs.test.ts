import { describe, expect, it, vi, beforeEach } from 'vitest';
import { blankValuationModel, calculateValuationModel, calculateWacc, hydrateValuationWorkspace, persistValuationWorkspace } from '../../bundled-runtimes/vibe-research/frontend/src/lib/valuationWorkbench';
import { applyMarketPrice, capitalReferences, capitalNoteReferences, hasValuationFacts, previewEarningsInput, valuationFromEarnings, type SavedEarningsInput } from '../../bundled-runtimes/vibe-research/frontend/src/lib/valuationInputs';
import type { EquityResearchSnapshot } from '../../bundled-runtimes/vibe-research/frontend/src/lib/api';
import type { ValuationModel } from '../../bundled-runtimes/vibe-research/frontend/src/lib/valuationWorkbench';
import { activeCapitalFields, alignValuationYears, attachCapitalEvidence, confirmScenario, valuationReadiness } from '../../bundled-runtimes/vibe-research/frontend/src/lib/valuationReview';
import {summarizeCapitalLines, type CapitalLineItem} from '../../bundled-runtimes/vibe-research/frontend/src/lib/valuationCapitalLines';
import {capitalEvidenceIssue, normalizeCapitalEvidence, stageCapitalEvidence, capitalDraftIssue, normalizeCapitalDrafts} from '../../bundled-runtimes/vibe-research/frontend/src/lib/valuationReview';
import {valuationModelSchema} from '../../packages/contracts/src/valuation';

const { config } = vi.hoisted(() => ({ config: { userId:'u',workspaceId:'w',accessToken:'test',instanceId:'i',storageGateway:'http://test/storage',permissions:['storage.read','storage.write'] } }));
vi.mock('@/lib/vibedesk', () => ({ waitForVibeDeskConfig:async()=>config }));
const workbook = ():SavedEarningsInput => ({
  id:'earnings:moutai',updatedAt:'2026-09-20T00:00:00Z',mode:'reported',
  security:{market:'CN',symbol:'600519',name:'贵州茅台',currency:'CNY'},
  fiscalPeriod:{label:'2024 年报',basis:'annual',periodEnd:'2024-12-31',reportingTime:'unknown'},
  metrics:[{id:'revenue',label:'营业收入',category:'financial',unit:'亿元',reported:1708.9915227634,internalEstimate:null,consensus:null,
    varianceVsConsensus:{amount:null,percent:null,bps:null},sourceIds:['pdf:revenue'],reportedBasis:'annual',periodEnd:'2024-12-31',reportedCurrency:'CNY'}],
  sourceMaterials:[{id:'pdf:revenue',label:'茅台年报 · 第 5 页',kind:'filing',status:'available',periodEnd:'2024-12-31',basis:'annual',url:'https://example.org/report.pdf#page=5',
    importedReport:{reportId:'r',rawValue:'170899152276.34',rawUnit:'元',columnHeader:'2024',confirmedAt:'2026-09-20'},
    excerpt:{text:'营业收入',metricId:'revenue',reportedValue:1708.9915227634,unit:'亿元',contentOrigin:'pdf-text',association:'user-linked',pdfPage:5}}],
});

function reviewed(model:ValuationModel) {
  // Explicit synthetic assumption, not a production default for absent adjustments.
  for(const field of ['nonOperatingAssetsM','minorityInterestM','otherClaimsM'] as const)model.capitalInputs[field] ??= 0;
  for(const field of activeCapitalFields(model))model=attachCapitalEvidence(model,field,{
    title:'验收用资料（非真实投资数据）',url:'https://example.org/filing.pdf',locator:'第 10 页',
    excerpt:`测试摘录：${field} = ${model.capitalInputs[field]}`,method:'验收用口径说明，百万单位；实际使用需核对原文',
  });
  model.scenarios[1].rationale='测试用经营假设，已分别评估增速、利润率及资本强度';
  return confirmScenario(model);
}

describe('资本调整明细',()=>{
  const line=(amountM:number|null,treatment:CapitalLineItem['treatment']='add',label='短期借款'):CapitalLineItem=>({id:crypto.randomUUID(),label,amountM,treatment,locator:'模拟年报第 106 页',reason:'测试口径，不代表真实投资数据'});
  const input=(lineItems:CapitalLineItem[])=>({title:'模拟资本附注',url:'',locator:'第 106 页',excerpt:'模拟原文，金额待真实年报核验',method:'各行均为百万元，纳入相加、已包含的扣除项相减；仅记录项不计入',lineItems});
  it('纳入相加、扣除相减、仅记录不计入；显式确认才替换原值',()=>{
    const model=valuationFromEarnings(workbook());model.capitalInputs.totalDebtM=250;
    const rows=[line(100),line(40,'add','租赁负债'),line(10,'deduct','已含重复项'),line(70,'exclude','不属有息债务')];
    expect(summarizeCapitalLines(rows,'totalDebtM')).toMatchObject({total:130,included:140,deducted:10,issues:[]});
    const next=attachCapitalEvidence(model,'totalDebtM',input(rows));
    expect(model.capitalInputs.totalDebtM).toBe(250);expect(next.capitalInputs.totalDebtM).toBe(130);
    expect(capitalEvidenceIssue(next,'totalDebtM')).toBeNull();
    expect(next.capitalEvidence.totalDebtM?.lineItems).toEqual(rows);
    expect(valuationModelSchema.parse(calculateValuationModel(next)).capitalEvidence.totalDebtM?.lineItems).toEqual(rows);
    rows[0].amountM=999;expect(next.capitalEvidence.totalDebtM?.lineItems?.[0]?.amountM).toBe(100);
    expect(summarizeCapitalLines([line(0.1),line(0.2)],'totalDebtM').total).toBe(0.3);
  });
  it('缺失不填零，负数或无纳入项不计算；零值有依据才允许',()=>{
    for(const rows of [[],[line(null)],[line(-1)],[line(5,'exclude')],[line(2),line(3,'deduct')],[{...line(1),reason:''}]]){
      expect(summarizeCapitalLines(rows,'totalDebtM').total).toBeNull();
      expect(()=>attachCapitalEvidence(valuationFromEarnings(workbook()),'totalDebtM',input(rows))).toThrow();
    }
    expect(summarizeCapitalLines([line(0)],'totalDebtM').total).toBe(0);
    expect(summarizeCapitalLines([line(1)],'dilutedSharesM').total).toBeNull();
  });
  it('原始现金余额不允许内部扣减，剔除额不得超出余额',()=>{
    const rows=[line(100),line(20,'deduct','受限资金')];
    expect(summarizeCapitalLines(rows,'cashM','adjusted').total).toBe(80);
    expect(summarizeCapitalLines(rows,'cashM','gross').total).toBeNull();
    const model=valuationFromEarnings(workbook());Object.assign(model.capitalInputs,{cashBasis:'gross',cashM:100});
    expect(()=>attachCapitalEvidence(model,'cashM',input(rows))).toThrow('原始现金余额');
    expect(()=>attachCapitalEvidence(model,'excludedCashM',input([line(101)]))).toThrow('不得超过现金余额');
    expect(attachCapitalEvidence(model,'excludedCashM',input([line(20)])).capitalInputs.excludedCashM).toBe(20);
  });
  it('明细金额、定位或理由变化均使旧确认失效，即使合计未变',()=>{
    const model=attachCapitalEvidence(valuationFromEarnings(workbook()),'totalDebtM',input([line(100),line(40)]));
    for(const change of [
      (row:ValuationModel)=>{row.capitalInputs.totalDebtM=150},
      (row:ValuationModel)=>{row.capitalEvidence.totalDebtM!.lineItems![0].reason='改变口径'},
      (row:ValuationModel)=>{row.capitalEvidence.totalDebtM!.lineItems![0].locator='第 107 页'},
      (row:ValuationModel)=>{row.capitalEvidence.totalDebtM!.lineItems![0].amountM=110;row.capitalEvidence.totalDebtM!.lineItems![1].amountM=30},
    ]){const changed=structuredClone(model);change(changed);expect(capitalEvidenceIssue(changed,'totalDebtM')).not.toBeNull()}
    model.capitalEvidence=normalizeCapitalEvidence(model.capitalEvidence);
    expect(capitalEvidenceIssue(model,'totalDebtM')).toBeNull();
    model.capitalEvidence=normalizeCapitalEvidence({...model.capitalEvidence,totalDebtM:{...model.capitalEvidence.totalDebtM,lineItems:'损坏的明细'}});
    expect(capitalEvidenceIssue(model,'totalDebtM')).not.toBeNull();
    expect(model.capitalEvidence.totalDebtM?.excerpt).toContain('模拟原文');
  });
  it('未核验暂存允许缺失金额，不覆盖已确认输入，采用后只清除对应暂存',()=>{
    let model=valuationFromEarnings(workbook());Object.assign(model.capitalInputs,{dilutedSharesM:10,totalDebtM:20,cashM:50});
    model=reviewed(model);
    const partial=input([line(null)]);partial.excerpt='';partial.lineItems[0].reason='';
    const staged=stageCapitalEvidence(model,'totalDebtM',partial);
    expect(hasValuationFacts(stageCapitalEvidence(blankValuationModel(),'totalDebtM',partial))).toBe(true);
    expect(staged.capitalInputs).toEqual(model.capitalInputs);expect(staged.capitalEvidence).toEqual(model.capitalEvidence);
    expect(valuationReadiness(staged).ready).toBe(true);
    expect(calculateValuationModel(staged).result).toEqual(calculateValuationModel(model).result);
    expect(valuationModelSchema.safeParse(calculateValuationModel(staged)).success).toBe(true);
    expect(capitalDraftIssue(staged,'totalDebtM')).toBeNull();
    expect(staged.capitalEvidenceDrafts?.totalDebtM?.input.lineItems?.[0]?.amountM).toBeNull();
    expect(normalizeCapitalDrafts(staged.capitalEvidenceDrafts)).toEqual(staged.capitalEvidenceDrafts);
    partial.lineItems[0].amountM=999;expect(staged.capitalEvidenceDrafts?.totalDebtM?.input.lineItems?.[0]?.amountM).toBeNull();
    const changed={...staged,asOf:'2025-12-31'};expect(capitalDraftIssue(changed,'totalDebtM')).toContain('已变化');
    const withCash=stageCapitalEvidence(staged,'cashM',input([line(null)]));
    const adopted=attachCapitalEvidence(withCash,'totalDebtM',input([line(100)]));
    expect(adopted.capitalInputs.totalDebtM).toBe(100);
    expect(adopted.capitalEvidenceDrafts?.totalDebtM).toBeUndefined();
    expect(adopted.capitalEvidenceDrafts?.cashM).toEqual(withCash.capitalEvidenceDrafts?.cashM);
  });
});

describe('财报收入接入',()=>{
  it('资本附注只引用同证券币种年度且已采用的原文，不回填金额',()=>{
    const row=workbook(),model=valuationFromEarnings(row);
    row.sourceMaterials.push({id:'cash-note',label:'现金构成附注',kind:'filing',status:'available',periodEnd:'2024-12-31',basis:'annual',
      capitalNote:{reportId:'r',title:'现金流量表补充资料',topics:['现金与受限资金'],text:'不属于现金及现金等价物的货币资金',pdfPage:117,pdfPageCount:143,readPages:[117],truncated:false,confirmedAt:'2026-09-20T00:00:00Z',contentOrigin:'pdf-text'}});
    expect(capitalNoteReferences([row],model,'cashM')).toHaveLength(1);
    expect(capitalNoteReferences([row],model,'excludedCashM')).toHaveLength(1);
    expect(capitalNoteReferences([row],model,'totalDebtM')).toEqual([]);
    expect(capitalNoteReferences([row],{...model,asOf:'2023-12-31'},'cashM')).toEqual([]);
    expect(capitalNoteReferences([row],{...model,security:{...model.security,currency:'USD'}},'cashM')).toEqual([]);
    expect(capitalNoteReferences([row],{...model,security:{...model.security,symbol:'000001'}},'cashM')).toEqual([]);
    row.sourceMaterials[1].status='unavailable';expect(capitalNoteReferences([row],model,'cashM')).toEqual([]);
    expect(model.capitalInputs.cashM).toBeNull();expect(model.capitalEvidence.cashM).toBeUndefined();
  });
  it('只转换年度收入、保留原文引用、按基期开始预测，不猜资本输入',()=>{
    const original=workbook();const model=valuationFromEarnings(original);
    expect(model.historicals[0].revenue).toBeCloseTo(170899.15227634,8);
    expect(model.historicals[0].ebitMarginPct).toBeNull();
    expect(model.scenarios[1].drivers.map(row=>row.year)).toEqual([2025,2026,2027,2028,2029]);
    expect(model.scenarios[1].rationale).toContain('模板假设');
    expect(model.capitalInputs.dilutedSharesM).toBeNull();
    expect(model.capitalInputs.totalDebtM).toBeNull();expect(model.capitalInputs.cashM).toBeNull();
    expect(calculateValuationModel(model).result.impliedPrice).toBeNull();
    expect(model.sourceMaterials[0].url).toContain('#page=5');
    expect(model.sourceMaterials[0].source).toContain(original.id);
    expect(original).toEqual(workbook());
  });
  it.each(['quarter','ytd','ttm'] as const)('拒绝将 %s 直接作为年度收入',basis=>{
    const row=workbook();row.metrics[0].reportedBasis=basis;
    expect(()=>valuationFromEarnings(row)).toThrow('完整年度');
  });
  it('修改实际值后旧原文不再背书，也不接入失效证据',()=>{
    const row=workbook();row.metrics[0].reported=999;
    expect(previewEarningsInput(row).issues.join()).toContain('匹配');
    row.metrics[0].reported=1708.9915227634;row.sourceMaterials[0].status='unavailable';
    expect(previewEarningsInput(row).revenueM).toBeNull();
  });
  it('拒绝缺少币种、币种冲突和期间不一致',()=>{
    const row=workbook();row.metrics[0].reportedCurrency='USD';row.metrics[0].periodEnd='2023-12-31';
    expect(previewEarningsInput(row).issues.join()).toMatch(/人民币/);
    expect(previewEarningsInput(row).issues.join()).toMatch(/期间/);
  });
});

describe('行情与 DCF 口径',()=>{
  it('估值只比较基期同日价格，旧模型没有日期时不输出模型差异',()=>{
    let model=valuationFromEarnings(workbook());Object.assign(model.capitalInputs,{currentPrice:100,dilutedSharesM:10,totalDebtM:0,cashM:50});
    model=reviewed(model);
    expect(calculateValuationModel(model).result.impliedPrice).not.toBeNull();
    expect(calculateValuationModel(model).result.impliedReturnPct).toBeNull();
    model.capitalInputs.currentPriceAsOf='2026-09-20';
    expect(calculateValuationModel(model).result.impliedReturnPct).toBeNull();
    model.capitalInputs.currentPriceAsOf='2024-12-31';
    expect(calculateValuationModel(model).result.impliedReturnPct).not.toBeNull();
    model.historicals.push({...model.historicals[0],period:'2024A',revenue:1});
    expect(calculateValuationModel(model).projections).toEqual([]);
  });
  it('资本参考只采用同证券同基期、值与原文匹配的已存事实，不自动改资本输入',()=>{
    const row=workbook();const model=valuationFromEarnings(row);
    row.operatingMetrics=[{...row.metrics[0],id:'capital-cash-funds',unit:'百万元',reported:10,sourceIds:['cash']}];
    row.sourceMaterials.push({...row.sourceMaterials[0],id:'cash',
      importedReport:{...row.sourceMaterials[0].importedReport!,columnHeader:'合并资产负债表 · 2024年12月31日 2023年12月31日'},
      excerpt:{...row.sourceMaterials[0].excerpt!,metricId:'capital-cash-funds',unit:'百万元',reportedValue:10}});
    expect(capitalReferences([row],model,'cashM')).toHaveLength(1);
    expect(capitalReferences([row],model,'totalDebtM')).toEqual([]);
    expect(model.capitalInputs.cashM).toBeNull();
    expect(capitalReferences([row],{...model,asOf:'2023-12-31'},'cashM')).toEqual([]);
    expect(capitalReferences([row],{...model,security:{...model.security,symbol:'000001'}},'cashM')).toEqual([]);
    row.operatingMetrics[0].reported=20;
    expect(capitalReferences([row],model,'cashM')).toEqual([]);
  });
  it('股价不做百万元换算，不以市值推稀释股数，也不覆盖假设和基期',()=>{
    const model=valuationFromEarnings(workbook());
    const snapshot={identity:model.security,evidenceLedger:[{id:'valuation.price',value:1500,unit:'CNY',currency:'CNY',source:'验收行情',label:'现价'},
      {id:'valuation.mcap_yi',value:18000},{id:'growth.revenue_yoy',value:80}]} as EquityResearchSnapshot;
    const next=applyMarketPrice(model,snapshot);
    expect(next.capitalInputs.currentPrice).toBe(1500);expect(next.capitalInputs.dilutedSharesM).toBeNull();
    expect(next.scenarios).toEqual(model.scenarios);expect(next.historicals).toEqual(model.historicals);expect(next.asOf).toBe(model.asOf);
    expect(()=>applyMarketPrice(model,{...snapshot,identity:{...model.security,currency:'USD'}})).toThrow('不一致');
  });
  it('净现金只在股权桥接增加价值，不变成负债务权重',()=>{
    let model=valuationFromEarnings(workbook());Object.assign(model.capitalInputs,{currentPrice:100,dilutedSharesM:10,totalDebtM:0,cashM:50,preTaxCostDebtPct:null,taxRatePct:null});
    model=reviewed(model);
    expect(calculateWacc(model.capitalInputs)).toBe(8);
    const result=calculateValuationModel(model).result;
    expect(result.netDebtM).toBe(-50);expect(result.equityValueM! - result.enterpriseValueM!).toBeCloseTo(50,3);
    expect(result.impliedPrice).toBeCloseTo(result.equityValueM!/10,3);
    const grid=calculateValuationModel(model).sensitivity;
    expect(grid.impliedPrices[2][2]).toBe(result.impliedPrice);
  });
  it.each(['totalDebtM','cashM','dilutedSharesM'] as const)('拒绝负数 %s 的股权桥接',field=>{
    const model=valuationFromEarnings(workbook());Object.assign(model.capitalInputs,{currentPrice:100,dilutedSharesM:10,totalDebtM:0,cashM:50,[field]:-1});
    const result=calculateValuationModel(model);
    expect(result.result.impliedPrice).toBeNull();expect(result.auditChecks.find(row=>row.id==='capital-bridge')?.status).toBe('fail');
    if(field!=='cashM')expect(calculateWacc(model.capitalInputs)).toBeNull();
  });
  it('历史基期按期间取最新，不按数组顺序；不支持金额单位时停止计算',()=>{
    const model=valuationFromEarnings(workbook());model.historicals.push({...model.historicals[0],period:'2023-12-31',revenue:1});
    expect(calculateValuationModel(model).projections[0].revenue).toBeCloseTo(170899.15227634*1.1,3);
    model.unitScale='亿元';expect(calculateValuationModel(model).projections).toHaveLength(0);
  });
});

describe('资本依据与情景确认',()=>{
  it('按现金口径和其他索偿桥接普通股价值，敏感性矩阵使用同一计算',()=>{
    let model=valuationFromEarnings(workbook());
    Object.assign(model.capitalInputs,{dilutedSharesM:10,totalDebtM:30,cashM:100,cashBasis:'gross',excludedCashM:20,nonOperatingAssetsM:40,minorityInterestM:15,otherClaimsM:5});
    model=reviewed(model);
    const result=calculateValuationModel(model);
    expect(result.result.eligibleCashM).toBe(80);expect(result.result.netDebtM).toBe(-50);
    expect(result.result.equityAdjustmentsM).toBe(20);
    expect(result.result.equityValueM! - result.result.enterpriseValueM!).toBeCloseTo(70,3);
    expect(result.sensitivity.impliedPrices[2][2]).toBe(result.result.impliedPrice);
    model.capitalInputs.cashBasis='adjusted';
    expect(valuationReadiness(model).ready).toBe(false);
    expect(calculateValuationModel(model).result.eligibleCashM).toBe(100);
    // Changing basis does not silently erase or subtract the saved exclusion.
    expect(model.capitalInputs.excludedCashM).toBe(20);
    expect(calculateValuationModel(reviewed(model)).result.equityValueM! - result.result.equityValueM!).toBeCloseTo(20,3);
  });
  it('剔除额不能大于余额，调整金额及其证据变化使每股输出失效',()=>{
    let model=valuationFromEarnings(workbook());
    Object.assign(model.capitalInputs,{dilutedSharesM:10,totalDebtM:30,cashM:100,cashBasis:'gross',excludedCashM:20});
    model=reviewed(model);
    for(const field of ['nonOperatingAssetsM','minorityInterestM','otherClaimsM','excludedCashM'] as const){
      const changed=structuredClone(model);changed.capitalInputs[field]=null;
      expect(calculateValuationModel(changed).result.equityValueM).toBeNull();
      expect(valuationReadiness(changed).ready).toBe(false);
      changed.capitalInputs[field]=-1;expect(calculateValuationModel(changed).result.equityValueM).toBeNull();
      changed.capitalInputs[field]=1;expect(calculateValuationModel(changed).result.impliedPrice).toBeNull();
    }
    model.capitalInputs.excludedCashM=101;
    expect(calculateValuationModel(model).result.equityValueM).toBeNull();
    expect(()=>reviewed(model)).toThrow('不得超过');
  });
  it('旧模型未填新调整项时不假设零、不继续输出原每股价值',()=>{
    const model=valuationFromEarnings(workbook());Object.assign(model.capitalInputs,{dilutedSharesM:10,totalDebtM:0,cashM:50});
    delete model.capitalInputs.nonOperatingAssetsM;delete model.capitalInputs.minorityInterestM;delete model.capitalInputs.otherClaimsM;
    const result=calculateValuationModel(model);
    expect(result.result.equityValueM).toBeNull();expect(result.result.impliedPrice).toBeNull();
    expect(result.projections).toHaveLength(5);expect(valuationReadiness(result).capital).toHaveLength(6);
  });
  const prepared=()=>{const model=valuationFromEarnings(workbook());Object.assign(model.capitalInputs,{dilutedSharesM:10,totalDebtM:0,cashM:50});return model};
  it('即使资本数值完整，未确认时只提供现金流试算，不输出每股结果',()=>{
    const model=prepared();const result=calculateValuationModel(model);
    expect(result.projections).toHaveLength(5);expect(result.result.impliedPrice).toBeNull();
    expect(result.sensitivity.impliedPrices.flat().every(value=>value===null)).toBe(true);
    expect(()=>confirmScenario(model)).toThrow('模板');
  });
  it('零债务需原文与口径，不能将缺失自动当作零',()=>{
    const model=prepared();
    expect(()=>attachCapitalEvidence(model,'totalDebtM',{title:'年报',url:'',locator:'',excerpt:'',method:''})).toThrow('请填写');
    expect(valuationReadiness(reviewed(model)).ready).toBe(true);
    model.capitalInputs.totalDebtM=null;
    expect(()=>reviewed(model)).toThrow('有效资本数值');
  });
  it('预测年度不能跨过历史基期，显式对齐不改增长率但撤销情景确认',()=>{
    const model=reviewed(prepared());model.scenarios[1].drivers.forEach(row=>{row.year+=2});
    expect(()=>confirmScenario(model)).toThrow('对齐');
    const aligned=alignValuationYears(model);
    expect(aligned.asOf).toBe('2024-12-31');expect(aligned.scenarios[1].drivers[0].year).toBe(2025);
    expect(aligned.scenarios[1].drivers[0].revenueGrowthPct).toBe(model.scenarios[1].drivers[0].revenueGrowthPct);
    expect(aligned.scenarios[1].review).toBeUndefined();
  });
  it('资本、基期、情景和来源变化都会阻止沿用确认，其他情景不被连带确认',()=>{
    const model=reviewed(prepared());expect(valuationReadiness(model).ready).toBe(true);
    for(const change of [
      (row:ValuationModel)=>{row.capitalInputs.cashM=55},
      (row:ValuationModel)=>{row.asOf='2025-12-31'},
      (row:ValuationModel)=>{row.security.currency='USD'},
      (row:ValuationModel)=>{row.historicals[0].revenue=999},
      (row:ValuationModel)=>{row.scenarios[1].drivers[0].ebitMarginPct=99},
      (row:ValuationModel)=>{row.scenarios[1].waccPct=10},
      (row:ValuationModel)=>{row.sourceMaterials.find(s=>s.id==='capital:cashM')!.status='unavailable'},
      (row:ValuationModel)=>{row.selectedScenario='bear'},
    ]){
      const changed=structuredClone(model);change(changed);
      expect(valuationReadiness(changed).ready).toBe(false);expect(calculateValuationModel(changed).result.impliedPrice).toBeNull();
    }
    model.capitalInputs.currentPrice=1500;expect(valuationReadiness(model).ready).toBe(true);
  });
});

describe('工作区存储结果',()=>{
  const values=new Map<string,string>();
  beforeEach(()=>{vi.restoreAllMocks();values.clear();vi.stubGlobal('localStorage',{getItem:(key:string)=>values.get(key)??null,setItem:(key:string,value:string)=>values.set(key,value)});});
  it('远端空工作区不读取其他工作区的旧全局缓存',async()=>{
    const model=valuationFromEarnings(workbook());values.set('newma-desk.valuation-workbench.v1',JSON.stringify({models:[model]}));
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('',{status:404})));
    expect((await hydrateValuationWorkspace()).models).toEqual([]);
  });
  it('确认记录保存重开仍有效；存量模型不默认获得确认',async()=>{
    const model=valuationFromEarnings(workbook());Object.assign(model.capitalInputs,{dilutedSharesM:10,totalDebtM:0,cashM:50});
    const confirmed=reviewed(model);
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('',{status:404})));
    // PUT is deliberately unavailable; check the same-workspace local round trip.
    await persistValuationWorkspace({schemaVersion:'newma-desk.valuation-workbench.v1',updatedAt:'2026-09-20',models:[confirmed]});
    const restored=(await hydrateValuationWorkspace()).models[0];
    expect(valuationReadiness(restored).ready).toBe(true);
    expect(restored.result.impliedPrice).toBe(calculateValuationModel(confirmed).result.impliedPrice);
    expect(restored.capitalEvidence.cashM?.excerpt).toContain('cashM');
    const legacy=structuredClone(model);delete (legacy as Partial<ValuationModel>).capitalEvidence;
    delete legacy.capitalInputs.nonOperatingAssetsM;delete legacy.capitalInputs.minorityInterestM;delete legacy.capitalInputs.otherClaimsM;
    values.set('newma-desk.valuation-workbench.v1:u:w',JSON.stringify({models:[legacy]}));
    const old=(await hydrateValuationWorkspace()).models[0];
    expect(old.capitalInputs.cashM).toBe(50);expect(valuationReadiness(old).ready).toBe(false);expect(old.result.impliedPrice).toBeNull();
    expect(old.capitalInputs.nonOperatingAssetsM).toBeNull();expect(old.capitalInputs.minorityInterestM).toBeNull();expect(old.capitalInputs.otherClaimsM).toBeNull();
  });
  it('远端失败只报告本地保存；均失败则报错',async()=>{
    vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new Error('offline')));
    const workspace={schemaVersion:'newma-desk.valuation-workbench.v1' as const,updatedAt:'2026-09-20',models:[valuationFromEarnings(workbook())]};
    expect(await persistValuationWorkspace(workspace)).toBe('local');
    expect(values.has('newma-desk.valuation-workbench.v1:u:w')).toBe(true);
    vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response('',{status:404})));
    expect((await hydrateValuationWorkspace()).models[0].id).toBe(workspace.models[0].id);
    vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new Error('offline')));
    vi.stubGlobal('localStorage',{setItem:()=>{throw new Error('full')}});
    await expect(persistValuationWorkspace(workspace)).rejects.toThrow('未能保存');
  });
  it('未核验编辑本地重开仍保留空字段，旧值与原确认不变',async()=>{
    let model=valuationFromEarnings(workbook());Object.assign(model.capitalInputs,{dilutedSharesM:10,totalDebtM:20,cashM:50});model=reviewed(model);
    const staged=stageCapitalEvidence(model,'totalDebtM',{title:'未完成资料',url:'',locator:'',excerpt:'',method:'',lineItems:[{id:'draft-1',label:'待核对借款',amountM:null,treatment:'add',locator:'',reason:''}]});
    vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new Error('offline')));
    await persistValuationWorkspace({schemaVersion:'newma-desk.valuation-workbench.v1',updatedAt:staged.updatedAt,models:[staged]});
    const restored=(await hydrateValuationWorkspace()).models[0];
    expect(restored.capitalEvidenceDrafts).toEqual(staged.capitalEvidenceDrafts);
    expect(restored.capitalInputs.totalDebtM).toBe(20);expect(valuationReadiness(restored).ready).toBe(true);
  });
});
