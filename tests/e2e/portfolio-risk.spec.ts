import { expect, test } from '@playwright/test';
import type { PortfolioDashboard, PortfolioPerformanceResult } from '../../modules/portfolio-center/src/types';
import { RISK_PAGES } from '../../modules/portfolio-center/src/riskNavigation';

const shell = process.env.VIBE_E2E_DOMAIN_SUITES_ORIGIN || 'http://127.0.0.1:5888';
const api = process.env.VIBE_E2E_DOMAIN_SUITES_API_ORIGIN || 'http://127.0.0.1:8911';
const runtime = `${api}/mod-runtime/portfolio-center/?workspace=portfolio-risk`;

test('saved product risk can be registered, assigned and closed without changing its report',async({page,request},testInfo)=>{
  const workspace=`e2e-risk-actions-${Date.now()}`;
  const ready=page.waitForResponse(r=>r.url().includes('/api/portfolio-center?includeQuotes=false'));
  await page.goto(`${shell}/?mod=portfolio-risk&workspace=${workspace}`);
  const identity=await(await ready).json() as PortfolioDashboard;
  const headers={'X-User-Id':identity.userId,'X-Workspace-Id':identity.workspaceId};
  const saved=await request.post(`${api}/api/portfolio-center/import-snapshots`,{headers,data:{productId:'A',name:'处置验收产品',asOf:new Date().toLocaleDateString('en-CA'),navFloor:200,holdings:[{assetType:'cash',symbol:'CASH',name:'现金',account:'资金账户',currency:'CNY',bookValue:100,availableCash:100}]}});
  expect(saved.ok()).toBe(true);const original=await saved.json();
  await page.reload();const frame=page.frameLocator('iframe').first();
  await frame.getByLabel('组合快照',{exact:true}).selectOption(original.id);
  await page.getByRole('button',{name:'预警',exact:true}).click();
  const panel=frame.getByRole('region',{name:'产品风险处置'});
  await panel.getByRole('button',{name:'登记风险提示 1',exact:true}).click();
  await expect(panel.getByRole('table',{name:'快照风险登记'}).getByRole('row').filter({hasText:'风险提示 1'})).toContainText('处置中');
  const endpoint=`${api}/api/portfolio-center/import-snapshots/${original.id}/risk-actions`;
  const actions=await(await request.get(endpoint,{headers})).json();expect(actions).toHaveLength(1);
  const reviewed=await request.post(`${api}/api/portfolio-center/import-snapshots`,{headers,data:{...original.snapshot,name:'处置验收产品复核版本',holdings:original.snapshot.holdings.map((p:Record<string,unknown>)=>({...p,bookValue:300,availableCash:300}))}});
  expect(reviewed.ok()).toBe(true);const review=await reviewed.json();
  await page.reload();
  await frame.getByLabel('组合快照',{exact:true}).selectOption(review.id);
  await page.getByRole('button',{name:'处置记录',exact:true}).click();
  const row=panel.locator('.risk-action-row').first();
  await row.locator('summary').first().click();
  await row.getByRole('button',{name:'确认接手',exact:true}).click();
  await expect(row.getByRole('alert')).toContainText('负责人');
  await row.getByLabel('负责人',{exact:true}).fill('合成复核人');
  await row.getByLabel('处理期限',{exact:true}).fill('2026-12-31T16:00');
  await row.getByRole('button',{name:'确认接手',exact:true}).click();
  await expect(row.locator('summary').first()).toContainText('处理中');
  await row.getByRole('button',{name:'复核结案',exact:true}).click();
  await expect(row.getByRole('alert')).toContainText('复核依据');
  await row.getByLabel('处置说明 / 复核依据 / 豁免理由',{exact:true}).fill('合成验收：已核对来源，记录处置，不代表原风险消失');
  await row.getByRole('button',{name:'采用当前快照复核',exact:true}).click();
  await expect(row.getByText(/尚未保存/)).toBeVisible();
  await row.getByRole('button',{name:'复核结案',exact:true}).click();
  await expect(row.locator('summary').first()).toContainText('已复核结案');
  await expect(row.getByLabel('负责人',{exact:true})).toHaveCount(0);
  const readComparisonContext=async()=>{
    const c=(await(await request.get(`${api}/api/mods/portfolio-risk-actions/context`,{headers})).json()).context;
    return c?.data?.summary?.reviewComparisons||{};
  };
  await expect.poll(readComparisonContext).toEqual({});
  await row.getByRole('button',{name:'对照来源与复核指标',exact:true}).click();
  const comparison=row.getByRole('table',{name:'复核关键指标对照'});
  await expect(comparison.getByRole('row').filter({hasText:'账面净资产'})).toHaveText('账面净资产100300200');
  await expect(comparison.getByRole('row').filter({hasText:'距底线余量'})).toHaveText('距底线余量-100100200');
  await expect(row.getByText(/安全垫变化 200 = 净资产变化 200/)).toBeVisible();
  await row.getByText('核对持仓与风控参数变化',{exact:true}).click();
  const changes=row.getByRole('region',{name:'来源与复核输入变更'});
  await expect(changes.getByRole('table').getByRole('row').filter({hasText:'账面金额'})).toContainText('100300');
  await expect(changes).not.toContainText('修改后必须重新预览');
  await expect.poll(async()=>{
    const evidence=(await readComparisonContext())[actions[0].id];
    return [evidence?.source?.id,evidence?.review?.id,evidence?.metrics?.find((m:{label:string})=>m.label==='账面净资产')];
  }).toEqual([original.id,review.id,{label:'账面净资产',before:100,after:300}]);
  await panel.screenshot({path:testInfo.outputPath('risk-product-action-closed.png')});
  expect(await(await request.get(`${api}/api/portfolio-center/import-snapshots/${original.id}`,{headers})).json()).toEqual(original);
  await expect.poll(async()=>{
    const c=(await(await request.get(`${api}/api/mods/portfolio-risk-actions/context`,{headers})).json()).context;
    return [c?.selection?.productId,c?.data?.summary?.riskActions?.[0]?.status,c?.data?.summary?.riskActions?.[0]?.reviewSnapshotId];
  }).toEqual(['A','resolved',review.id]);
  await panel.getByRole('button',{name:'查看来源快照',exact:true}).click();
  await expect(frame.getByLabel('组合快照',{exact:true})).toHaveValue(original.id);
  await expect.poll(readComparisonContext).toEqual({});
  await panel.getByRole('button',{name:'查看复核快照',exact:true}).click();
  await expect(frame.getByLabel('组合快照',{exact:true})).toHaveValue(review.id);
  await page.reload();
  await expect(panel.locator('.risk-action-row').first()).toContainText('已复核结案');
  await expect.poll(readComparisonContext).toEqual({});
  await panel.locator('.risk-action-row').first().locator('summary').first().click();
  await panel.getByRole('button',{name:'查看来源快照',exact:true}).click();
  await expect(frame.getByLabel('组合快照',{exact:true})).toHaveValue(original.id);
  await panel.getByRole('button',{name:'查看复核快照',exact:true}).click();
  await expect(frame.getByLabel('组合快照',{exact:true})).toHaveValue(review.id);
  await frame.getByLabel('组合快照',{exact:true}).selectOption('');
  await expect(frame.getByText('暂无处置记录；从“预警”页面登记风险或数据缺口。',{exact:true})).toBeVisible();
});

test('product warning line distinguishes scenario risk, rejects inverted limits and saves a new version',async({page,request},testInfo)=>{
  const workspace=`e2e-risk-thresholds-${Date.now()}`;
  const ready=page.waitForResponse(r=>r.url().includes('/api/portfolio-center?includeQuotes=false'));
  await page.goto(`${shell}/?mod=portfolio-risk&workspace=${workspace}`);
  const identity=await(await ready).json() as PortfolioDashboard;
  const headers={'X-User-Id':identity.userId,'X-Workspace-Id':identity.workspaceId};
  const response=await request.post(`${api}/api/portfolio-center/import-snapshots`,{headers,data:{productId:'P',name:'分级预警合成产品',asOf:new Date().toLocaleDateString('en-CA'),navFloor:80,navWarningFloor:95,holdings:[
    {assetType:'stock',market:'CN',symbol:'S',name:'合成股票',account:'A',currency:'CNY',bookValue:100,equityBeta:1,equityBenchmark:'CSI300'},
    {assetType:'cash',symbol:'CASH',name:'现金',account:'A',currency:'CNY',bookValue:0,availableCash:0},
  ]}});
  expect(response.ok()).toBe(true);const original=await response.json();
  await page.reload();const frame=page.frameLocator('iframe').first();
  await frame.getByLabel('组合快照',{exact:true}).selectOption(original.id);
  await page.getByRole('button',{name:'风险限额',exact:true}).click();
  const table=frame.getByRole('table',{name:'净值分级预警明细'});
  await expect(table.getByRole('row').filter({hasText:'持仓快照（未施加冲击）'})).toContainText('高于已设阈值');
  await expect(table.getByRole('row').filter({hasText:'权益下跌，利率上行'})).toContainText('触发预警');
  await frame.getByRole('button',{name:'编辑持仓并另存'}).click();
  await expect(frame.getByLabel('净值预警线（基准币）',{exact:true})).toHaveValue('95');
  await frame.getByLabel('净值预警线（基准币）',{exact:true}).fill('79');
  await frame.getByRole('button',{name:'预览并检查'}).click();
  await expect(frame.getByRole('alert')).toContainText('预警线不能低于净值底线');
  await expect(frame.getByRole('button',{name:'确认保存快照'})).toHaveCount(0);
  await frame.getByLabel('净值预警线（基准币）',{exact:true}).fill('105');
  await frame.getByRole('button',{name:'预览并检查'}).click();
  await expect(frame.getByRole('table',{name:'快照输入变更'})).toContainText('净值预警线');
  await frame.getByRole('button',{name:'确认保存快照'}).click();
  await expect(frame.getByRole('status')).toContainText('已保存');
  const records=await(await request.get(`${api}/api/portfolio-center/import-snapshots`,{headers})).json();
  expect(records).toHaveLength(2);
  expect(records.find((r:{id:string})=>r.id===original.id)).toEqual(original);
  await page.reload();
  await expect(table.getByRole('row').filter({hasText:'持仓快照（未施加冲击）'})).toContainText('触发预警');
  await frame.getByRole('region',{name:'净值分级预警'}).screenshot({path:testInfo.outputPath('risk-nav-thresholds.png')});
  await page.getByRole('button',{name:'预警',exact:true}).click();
  await expect.poll(async()=>{
    const c=(await(await request.get(`${api}/api/mods/portfolio-risk-alerts/context`,{headers})).json()).context;
    return [c?.selection?.productId,c?.data?.summary?.snapshot?.navWarningFloor,c?.data?.summary?.report?.navThresholds?.rows?.[0]?.status];
  }).toEqual(['P',105,'warning']);
});

test('product import keeps account cash and floors separate, persists assignment and switches context', async ({page,request},testInfo)=>{
  const workspace=`e2e-risk-products-${Date.now()}`;
  const ready=page.waitForResponse(r=>r.url().includes('/api/portfolio-center?includeQuotes=false'));
  await page.goto(`${shell}/?mod=portfolio-risk&workspace=${workspace}`);
  const identity=await (await ready).json() as PortfolioDashboard;
  const headers={'X-User-Id':identity.userId,'X-Workspace-Id':identity.workspaceId};
  const b=await request.post(`${api}/api/portfolio-center/import-snapshots`,{headers,data:{productId:'B',name:'合成产品乙',asOf:new Date().toLocaleDateString('en-CA'),navFloor:5000,holdings:[{assetType:'cash',symbol:'CASH',name:'现金',account:'同名账户',currency:'CNY',bookValue:10000,availableCash:10000}]}});
  expect(b.ok()).toBe(true);const productB=await b.json();
  await page.reload();
  const frame=page.frameLocator('iframe').first();
  await frame.getByRole('button',{name:'导入组合',exact:true}).click();
  await frame.getByLabel('产品编号（可选）',{exact:true}).fill('A');
  await frame.getByLabel('组合名称',{exact:true}).fill('合成产品甲');
  await frame.getByLabel('净值底线（基准币）').fill('200');
  const fields=['assetType','symbol','name','account','currency','bookValue','availableCash','direction','notional','equityBenchmark'];
  const rows:Record<string,string|number>[]=[{assetType:'cash',symbol:'CASH',name:'现金',account:'同名账户',currency:'CNY',bookValue:100,availableCash:100},{assetType:'equity_future',symbol:'IF-TEST',name:'合成空头',account:'同名账户',currency:'CNY',bookValue:0,direction:'short',notional:10000,equityBenchmark:'CSI300'}];
  await frame.getByLabel('持仓表格',{exact:true}).fill([fields.join(','),...rows.map(r=>fields.map(f=>r[f]??'').join(','))].join('\n'));
  await frame.getByRole('button',{name:'预览并检查'}).click();
  expect(await (await request.get(`${api}/api/portfolio-center/import-products`,{headers})).json()).toHaveLength(1);
  await frame.getByRole('button',{name:'确认保存快照'}).click();
  await expect(frame.getByRole('status')).toContainText('已保存');
  const table=frame.getByRole('table',{name:'产品风险总表',exact:true});
  const aRow=table.getByRole('row').filter({hasText:'合成产品甲'});
  await expect(aRow).toContainText('-900');
  await expect(table.getByRole('row').filter({hasText:'合成产品乙'})).toContainText('10,000');
  const productFilter=frame.getByLabel('产品核验筛选',{exact:true});
  await productFilter.selectOption('cash');
  await expect(aRow).toContainText('对应情景：');
  await expect(table.getByRole('row').filter({hasText:'合成产品乙'})).toHaveCount(0);
  await productFilter.selectOption('current');
  await expect(aRow).toBeVisible();
  await expect(table.getByRole('row').filter({hasText:'合成产品乙'})).toHaveCount(0);
  await productFilter.selectOption('stale');
  await expect(frame.getByText('没有符合该筛选的产品，不代表其他风险已排除。',{exact:true})).toBeVisible();
  await productFilter.selectOption('all');
  await expect(table.getByRole('row').filter({hasText:'合成产品乙'})).toBeVisible();
  await table.screenshot({path:testInfo.outputPath('risk-product-overview.png')});
  await frame.getByRole('button',{name:'编辑持仓并另存'}).click();
  await expect(frame.getByLabel('产品编号（可选）',{exact:true})).toHaveValue('A');
  await frame.getByLabel('组合名称',{exact:true}).fill('合成产品甲修订');
  await frame.getByRole('button',{name:'预览并检查'}).click();
  await frame.getByRole('button',{name:'确认保存快照'}).click();
  await expect(table.getByRole('row').filter({hasText:'合成产品甲修订'})).toContainText('-900');
  expect(await (await request.get(`${api}/api/portfolio-center/import-products`,{headers})).json()).toHaveLength(2);
  await frame.getByRole('button',{name:'查看产品 B',exact:true}).click();
  await expect(frame.getByLabel('组合快照',{exact:true})).toHaveValue(productB.id);
  await page.getByRole('button',{name:'流动性',exact:true}).click();
  await expect(frame.getByRole('table',{name:'组合账户现金压力'})).toContainText('10,000');
  await expect(frame.getByRole('table',{name:'组合账户现金压力'})).not.toContainText('-900');
  await expect.poll(async()=>{
    const value=await (await request.get(`${api}/api/mods/portfolio-risk-liquidity/context`,{headers})).json();
    return [value.context?.selection?.productId,value.context?.data?.summary?.report?.nav];
  }).toEqual(['B',10000]);
  await page.reload();
  await expect(frame.getByLabel('组合快照',{exact:true})).toHaveValue(productB.id);
});

test('mixed snapshot stays selected across all risk pages without ledger results', async ({page,request},testInfo) => {
  const workspace=`e2e-risk-scope-${Date.now()}`;
  const ready=page.waitForResponse(r=>r.url().includes('/api/portfolio-center?includeQuotes=false'));
  await page.goto(`${shell}/?mod=portfolio-risk&workspace=${workspace}`);
  const identity=await (await ready).json() as PortfolioDashboard;
  const headers={'X-User-Id':identity.userId,'X-Workspace-Id':identity.workspaceId};
  const created=await request.post(`${api}/api/portfolio-center/import-snapshots`,{headers,data:{
    name:'跨标签合成组合',asOf:new Date().toLocaleDateString('en-CA'),baseCurrency:'CNY',navFloor:1200,nearTermOutflow:0,
    holdings:[{assetType:'stock',market:'CN',symbol:'600519',name:'合成股票',account:'证券',currency:'CNY',bookValue:1000,equityBeta:1,equityBenchmark:'沪深300',issuer:'合成发行人'},
      {assetType:'cash',symbol:'CASH',name:'现金',account:'证券',currency:'CNY',bookValue:100,availableCash:100}],
  }});
  expect(created.ok()).toBe(true);
  const saved=await created.json();
  await page.reload();
  const frame=page.frameLocator('iframe').first();
  await frame.getByLabel('组合快照',{exact:true}).selectOption(saved.id);
  for(const {id,label,view} of RISK_PAGES){
    await page.getByRole('button',{name:label,exact:true}).click();
    await expect(frame.getByLabel('组合快照',{exact:true})).toHaveValue(saved.id);
    await expect(frame.getByRole('status')).toContainText('跨标签合成组合');
    await expect(frame.getByRole('button',{name:'计算历史风险',exact:true})).toHaveCount(0);
    await expect(frame.getByText('风险处置台账',{exact:true})).toHaveCount(0);
    await expect.poll(async()=>{
      const result=await request.get(`${api}/api/mods/${id}/context`,{headers});
      if(!result.ok())return null;
      const c=(await result.json()).context;
      return [c?.selection?.snapshotId,c?.filters?.riskView,c?.data?.summary?.report?.nav];
    }).toEqual([saved.id,view,1100]);
    if(view==='concentration')await expect(frame.getByRole('table',{name:'导入快照集中度'})).toBeVisible();
    if(view==='exposure')await expect(frame.getByRole('table',{name:'组合对冲暴露'})).toBeVisible();
    if(view==='stress')await expect(frame.getByRole('table',{name:'组合诊断情景'})).toBeVisible();
    if(view==='liquidity'){
      await expect(frame.getByRole('table',{name:'组合账户现金压力'})).toBeVisible();
      await expect(frame.getByRole('table',{name:'组合对冲暴露'})).toHaveCount(0);
      await page.screenshot({path:testInfo.outputPath('risk-shared-snapshot-liquidity.png')});
    }
    if(view==='drawdown')await expect(frame.getByText(/当前混合组合尚无净值时间序列/)).toBeVisible();
    if(view==='alerts')await expect(frame.getByText('持仓快照净值已低于设定底线，尚未施加情景冲击',{exact:true})).toBeVisible();
  }
  await frame.getByLabel('组合快照',{exact:true}).selectOption('');
  await expect(frame.getByText('风险处置台账',{exact:true})).toBeVisible();
  await page.reload();
  await expect(frame.getByLabel('组合快照',{exact:true})).toBeEnabled();
  await expect(frame.getByLabel('组合快照',{exact:true})).toHaveValue('');
});

test('edit saved snapshot preserves raw fields, cancels and saves a separate version', async ({page,request},testInfo) => {
  const workspace=`e2e-risk-edit-${Date.now()}`;
  const ready=page.waitForResponse(r=>r.url().includes('/api/portfolio-center?includeQuotes=false'));
  await page.goto(`${shell}/?mod=portfolio-risk&workspace=${workspace}`);
  const identity=await (await ready).json() as PortfolioDashboard;
  const headers={'X-User-Id':identity.userId,'X-Workspace-Id':identity.workspaceId};
  const today=new Date().toLocaleDateString('en-CA');
  const next=new Date();next.setDate(next.getDate()+3);
  const snapshot={name:'合成持仓编辑验收',asOf:today,baseCurrency:'CNY',navFloor:null,nearTermOutflow:10,cashNeedDate:next.toLocaleDateString('en-CA'),holdings:[
    {assetType:'fund',market:'CN',symbol:'000001',name:'合成基金',account:'证券',currency:'CNY',bookValue:50000,equityBeta:0,ratePnlPerBp:0,source:'合成依据,含"引号"\n第二行',issuer:'',proceedsAmount:15000,proceedsDate:next.toLocaleDateString('en-CA'),proceedsAccount:'证券',proceedsSource:'合成到账计划'},
    {assetType:'cash',symbol:'CASH',name:'现金',account:'证券',currency:'CNY',bookValue:10000,availableCash:10000},
  ]};
  const response=await request.post(`${api}/api/portfolio-center/import-snapshots`,{headers,data:snapshot});
  expect(response.ok()).toBe(true);
  const original=await response.json();
  await page.reload();
  const frame=page.frameLocator('iframe').first();
  await frame.getByLabel('组合快照',{exact:true}).selectOption(original.id);
  await frame.getByRole('button',{name:'编辑持仓并另存'}).click();
  await expect(frame.getByLabel('代码',{exact:true})).toHaveValue('000001');
  await expect(frame.getByLabel('持仓截止日',{exact:true})).toHaveValue(today);
  await frame.getByLabel('净值底线（基准币）',{exact:true}).fill('55000');
  await frame.getByLabel('账面金额',{exact:true}).fill('40000');
  await expect.poll(async()=>{
    const value=await (await request.get(`${api}/api/mods/portfolio-risk/context`,{headers})).json();
    return value.context?.data?.summary?.draftPending;
  }).toBe(true);
  await frame.getByRole('button',{name:'取消编辑'}).click();
  await expect(frame.getByRole('status')).toContainText('已保存');
  await frame.getByRole('button',{name:'编辑持仓并另存'}).click();
  await expect(frame.getByLabel('账面金额',{exact:true})).toHaveValue('50000');
  await frame.getByLabel('净值底线（基准币）',{exact:true}).fill('55000');
  await frame.getByLabel('账面金额',{exact:true}).fill('40000');
  await frame.getByRole('button',{name:'预览并检查'}).click();
  await expect(frame.getByRole('region',{name:'组合风险结论'})).toContainText('净值底线存在缺口');
  const changes=frame.getByRole('region',{name:'保存前变更核对'});
  await expect(changes).toContainText('修改 1 行 · 组合参数 1 项');
  const amountRow=changes.getByRole('row').filter({hasText:'账面金额'});
  await expect(amountRow).toContainText('50000');
  await expect(amountRow).toContainText('40000');
  expect(await (await request.get(`${api}/api/portfolio-center/import-snapshots`,{headers})).json()).toHaveLength(1);
  await frame.getByLabel('账面金额',{exact:true}).fill('41000');
  await expect(frame.getByRole('button',{name:'确认保存快照'})).toHaveCount(0);
  await expect(changes).toHaveCount(0);
  await frame.getByRole('button',{name:'预览并检查'}).click();
  await frame.getByRole('button',{name:'确认保存快照'}).click();
  await expect(frame.getByRole('status')).toContainText('已保存');
  const records=await (await request.get(`${api}/api/portfolio-center/import-snapshots`,{headers})).json();
  expect(records).toHaveLength(2);
  expect(records.find((r:{id:string})=>r.id===original.id)).toEqual(original);
  const edited=records.find((r:{id:string})=>r.id!==original.id);
  expect(edited.snapshot).toEqual({...original.snapshot,navFloor:55000,holdings:[{...original.snapshot.holdings[0],bookValue:41000},original.snapshot.holdings[1]]});
  expect(edited.report.nav).toBe(51000);
  await page.reload();
  await expect(frame.getByLabel('组合快照',{exact:true})).toHaveValue(edited.id);
  await expect(frame.getByRole('region',{name:'组合风险结论'})).toContainText('-4,000');
  await frame.getByRole('button',{name:'编辑持仓并另存'}).click();
  await frame.getByRole('region',{name:'编辑原始持仓'}).screenshot({path:testInfo.outputPath('risk-snapshot-editor.png')});
  await frame.getByRole('button',{name:'新增持仓行'}).click();
  await expect(frame.getByLabel('账面金额',{exact:true})).toHaveValue('');
  await frame.getByRole('combobox',{name:'资产类型',exact:true}).selectOption('bond');
  await frame.getByLabel('名称',{exact:true}).fill('合成新增债券');
  await frame.getByLabel('代码',{exact:true}).fill('001234');
  await frame.getByLabel('账面金额',{exact:true}).fill('2000');
  const editor=frame.getByRole('region',{name:'编辑原始持仓'});
  await editor.getByText('风险参数与期限',{exact:true}).click();
  await frame.getByLabel('整笔利率每基点损益',{exact:true}).fill('-0.6');
  await frame.getByRole('combobox',{name:'选择持仓',exact:true}).selectOption('0');
  await frame.getByRole('button',{name:'移除当前行',exact:true}).click();
  await frame.getByRole('button',{name:'确认移除此行'}).click();
  await frame.getByRole('button',{name:'撤销上次移除'}).click();
  await expect(frame.getByLabel('代码',{exact:true})).toHaveValue('000001');
  await editor.getByText('预计到账计划',{exact:true}).click();
  await expect(frame.getByLabel('预计到账金额',{exact:true})).toHaveValue('15000');
  await frame.getByRole('button',{name:'移除当前行',exact:true}).click();
  await frame.getByRole('button',{name:'确认移除此行'}).click();
  await frame.getByRole('button',{name:'预览并检查'}).click();
  await expect(changes).toContainText('新增 1 行 · 移除 1 行 · 修改 0 行');
  await changes.screenshot({path:testInfo.outputPath('risk-input-changes.png')});
  await frame.getByRole('button',{name:'确认保存快照'}).click();
  await expect(frame.getByRole('status')).toContainText('已保存');
  const after=await (await request.get(`${api}/api/portfolio-center/import-snapshots`,{headers})).json();
  expect(after).toHaveLength(3);
  expect(after.find((r:{id:string})=>r.id===original.id)).toEqual(original);
  expect(after.find((r:{id:string})=>r.id===edited.id)).toEqual(edited);
  const changed=after.find((r:{id:string})=>![original.id,edited.id].includes(r.id));
  expect(changed.snapshot.holdings).toHaveLength(2);
  expect(changed.snapshot.holdings[0]).toEqual(original.snapshot.holdings[1]);
  expect(changed.snapshot.holdings[1]).toMatchObject({symbol:'001234',bookValue:2000,ratePnlPerBp:-0.6,proceedsAmount:null});
  expect(changed.report.nav).toBe(12000);
  const ledger=await (await request.get(`${api}/api/portfolio-center?includeQuotes=false`,{headers})).json();
  expect(ledger.activities).toEqual([]);
  await page.reload();
  await expect(frame.getByLabel('组合快照',{exact:true})).toHaveValue(changed.id);
  await frame.getByRole('button',{name:'编辑持仓并另存'}).click();
  await expect(frame.getByRole('combobox',{name:'选择持仓',exact:true}).locator('option')).toHaveCount(2);
  await frame.getByLabel('账面金额',{exact:true}).fill('999');
  await page.reload();
  await expect(frame.getByLabel('组合快照',{exact:true})).toHaveValue(changed.id);
  await expect(frame.getByRole('region',{name:'编辑原始持仓'})).toHaveCount(0);
  // An explicitly selected old version must not silently become the latest one.
  await frame.getByLabel('组合快照',{exact:true}).selectOption(original.id);
  await page.reload();
  await expect(frame.getByLabel('组合快照',{exact:true})).toHaveValue(original.id);
  await frame.getByRole('button',{name:'编辑持仓并另存'}).click();
  await expect(frame.getByLabel('账面金额',{exact:true})).toHaveValue('50000');
  await frame.getByRole('button',{name:'取消编辑'}).click();
  await page.goto(`${shell}/?mod=portfolio-risk&workspace=${workspace}-other`);
  await expect(frame.getByLabel('组合快照',{exact:true})).toBeEnabled();
  await expect(frame.getByLabel('组合快照',{exact:true})).toHaveValue('');
  await expect(frame.getByLabel('组合快照',{exact:true}).locator('option')).toHaveCount(1);
  await page.goto(`${shell}/?mod=portfolio-risk&workspace=${workspace}`);
  await expect(frame.getByLabel('组合快照',{exact:true})).toHaveValue(original.id);
  await frame.getByLabel('组合快照',{exact:true}).selectOption('');
  await page.reload();
  await expect(frame.getByLabel('组合快照',{exact:true})).toBeEnabled();
  await expect(frame.getByLabel('组合快照',{exact:true})).toHaveValue('');
});

test('risk empty state, all nine tabs, immutable saved report and Agent context', async ({page,request}, testInfo) => {
  const workspace = `e2e-risk-${Date.now()}`;
  const errors: string[]=[]; page.on('pageerror',e=>errors.push(e.message));
  const dashboardResponse = page.waitForResponse(r=>r.url().includes('/api/portfolio-center?includeQuotes=false'));
  const url = `${shell}/?mod=portfolio-risk&workspace=${workspace}`;
  await page.goto(url);
  const identity = await (await dashboardResponse).json() as PortfolioDashboard;
  const headers={'X-User-Id':identity.userId,'X-Workspace-Id':identity.workspaceId};
  const frame = page.frameLocator('iframe').first();
  await expect(frame.locator('.workbench-metrics').first()).toContainText('未评估');
  await expect(frame.getByText('正常',{exact:true})).toHaveCount(0);
  for (const {label,id,view} of RISK_PAGES) {
    await page.getByRole('button',{name:label,exact:true}).click();
    await expect(page).toHaveURL(new RegExp(`mod=${id}(&|$)`));
    await expect(frame.getByRole('navigation',{name:'组合风控标签'})).toHaveCount(0);
    await expect.poll(async()=>{
      const response=await request.get(`${api}/api/mods/${id}/context`,{headers});
      if (!response.ok()) return null;
      const payload=await response.json();
      return [payload.context?.view?.id,payload.context?.filters?.subview];
    }).toEqual([id,view]);
  }
  await page.getByRole('button',{name:'压力测试',exact:true}).click();
  await frame.getByLabel('CN 价格冲击 / %').fill('-25');
  await page.getByRole('button',{name:'集中度',exact:true}).click();
  await expect(frame.getByText(/按币种、证券合并跨账户持仓/)).toBeVisible();
  await page.getByRole('button',{name:'压力测试',exact:true}).click();
  await expect(frame.getByLabel('CN 价格冲击 / %')).toHaveValue('-25');
  await page.getByRole('button',{name:'风险总览',exact:true}).click();
  await frame.getByRole('button',{name:'保存风险评估',exact:true}).click();
  await expect(frame.getByText('历史快照 · 只读，不作为当前通过结论')).toBeVisible();
  const reports = await (await request.get(`${api}/api/portfolio-center/risk-reports`,{headers})).json();
  expect(reports).toHaveLength(1);
  const reportId=reports[0].id;
  await page.reload();
  await frame.getByLabel('查看历史评估').selectOption(reportId);
  await expect(frame.locator('.risk-archive')).toContainText(reportId);
  await expect.poll(async()=>{
    const response=await request.get(`${api}/api/mods/portfolio-risk/context`,{headers});
    if (!response.ok()) return null;
    const payload=await response.json();
    return payload.context?.data?.summary?.viewedHistoricalReport?.id;
  }).toBe(reportId);
  const context = await (await request.get(`${api}/api/mods/portfolio-risk/context`,{headers})).json();
  expect(context.context.data.summary.riskAssessment.status).toBe('unassessed');
  await frame.getByLabel('查看历史评估').selectOption('');
  await page.screenshot({path:testInfo.outputPath('risk-overview.png'),animations:'disabled',fullPage:true});
  expect(errors).toEqual([]);
});

test('standalone risk actions and history invalidation with explicit synthetic market data', async ({page,request}) => {
  const identity = {'X-User-Id':'e2e-risk','X-Workspace-Id':`e2e-risk-actions-${Date.now()}`};
  const base = await (await request.get(`${api}/api/portfolio-center?includeQuotes=false`,{headers:identity})).json() as PortfolioDashboard;
  const now = new Date().toISOString();
  let quantity=100;
  const fixture = (ledger: PortfolioDashboard): PortfolioDashboard => ({...ledger,
    positions:[{accountId:'main',market:'CN',symbol:'600519',name:'测试持仓（合成数据）',currency:'CNY',quantity,averageCost:10,costValue:1000,realizedPnl:0,price:10,marketValue:quantity*10,quoteAsOf:now,quoteSource:'e2e-synthetic'}],
    currencies:[{currency:'CNY',cash:0,costValue:1000,marketValue:quantity*10,realizedPnl:0,income:0,fees:0}],valuationStatus:'live',updatedAt:now,
  });
  await page.route('**/api/portfolio-center**',async route=>{
    const path=new URL(route.request().url()).pathname;
    if (path === '/api/portfolio-center') {
      const ledger=await (await request.get(`${api}/api/portfolio-center?includeQuotes=false`,{headers:identity})).json();
      await route.fulfill({json:fixture(ledger)}); return;
    }
    if (path === '/api/portfolio-center/performance/analyze') {
      const input=route.request().postDataJSON();
      const r:PortfolioPerformanceResult={...input,status:'ready',method:'quantstats-inspired-weekly',timeframe:'1w',observations:input.lookbackWeeks,coverageWeightPct:100,basisPositions:fixture(base).positions,asOf:now,generatedAt:now,dataSources:['e2e-synthetic'],warnings:['验收合成数据，不是真实行情'],missingAssets:[],series:[],metrics:{totalReturnPct:10,annualizedReturnPct:10,annualizedVolatilityPct:5,maxDrawdownPct:-2,maxDrawdownDurationWeeks:2,winRatePct:80,bestWeekPct:8,worstWeekPct:-2,valueAtRisk95Pct:6,conditionalValueAtRisk95Pct:4}};
      await route.fulfill({json:r}); return;
    }
    await route.continue();
  });
  await page.goto(runtime);
  await page.getByRole('button',{name:'回撤与 VaR',exact:true}).click();
  await page.getByRole('button',{name:'计算历史风险',exact:true}).click();
  await expect(page.getByText('当前条件的历史模拟结果',{exact:true})).toBeVisible();
  await expect(page.locator('.workbench-metrics article').filter({hasText:'95% 周度 VaR'})).toContainText('0%');
  await page.getByLabel('历史窗口').selectOption('52');
  await expect(page.getByText(/已过期 · 持仓或分析条件已变化/)).toBeVisible();
  await page.getByRole('button',{name:'计算历史风险',exact:true}).click();
  await expect(page.getByText('当前条件的历史模拟结果',{exact:true})).toBeVisible();
  quantity=200;
  await page.getByRole('button',{name:'刷新',exact:true}).click();
  await expect(page.getByText(/已过期 · 持仓或分析条件已变化/)).toBeVisible();
  await page.getByRole('button',{name:'预警',exact:true}).click();
  await page.locator('.risk-check-table tr').filter({hasText:'CNY 单一证券限额'}).getByRole('button',{name:'登记处置'}).click();
  await page.getByRole('button',{name:'处置记录',exact:true}).click();
  await page.locator('.risk-action-row > summary').first().click();
  await page.getByRole('button',{name:'确认接手'}).click();
  await expect(page.getByRole('alert')).toContainText('负责人');
  await page.getByLabel('负责人',{exact:true}).fill('验收负责人');
  await page.getByLabel('处理期限',{exact:true}).fill('2026-09-20T10:00');
  await page.getByRole('button',{name:'确认接手'}).click();
  await page.getByRole('button',{name:'复核结案'}).click();
  await expect(page.getByRole('alert')).toContainText('复核依据');
  await page.getByLabel('处置说明 / 复核依据 / 豁免理由',{exact:true}).fill('测试：检查数据与持仓后完成复核');
  await page.getByRole('button',{name:'复核结案'}).click();
  await expect(page.locator('.risk-action-row > summary')).toContainText('已复核结案');
  await page.reload();
  await expect(page.locator('.risk-action-row > summary')).toContainText('已复核结案');
  await page.unrouteAll({behavior:'wait'});
});

test('standalone narrow viewport keeps controls usable', async ({page}, testInfo) => {
  await page.setViewportSize({width:390,height:844});
  await page.goto(runtime);
  await page.getByRole('button',{name:'风险限额',exact:true}).click();
  await expect(page.getByRole('button',{name:'保存限额',exact:true})).toBeVisible();
  await page.getByRole('button',{name:'风险总览',exact:true}).click();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({path:testInfo.outputPath('risk-narrow.png'),animations:'disabled',fullPage:true});
});

test('embedded synthetic holdings: detailed analysis and historical report survive host navigation', async ({page},testInfo) => {
  const now=new Date().toISOString();
  let ledger:PortfolioDashboard;
  const performance=():PortfolioPerformanceResult=>({currency:'CNY',lookbackWeeks:52,riskFreeRatePct:2,status:'ready',method:'quantstats-inspired-weekly',timeframe:'1w',observations:52,coverageWeightPct:100,basisPositions:ledger.positions,asOf:now,generatedAt:now,dataSources:['e2e-synthetic'],warnings:['验收合成数据，不是真实行情'],missingAssets:[],series:[{label:'W1',equity:1.1,drawdownPct:0},{label:'W2',equity:0.99,drawdownPct:-10},{label:'W3',equity:1.1,drawdownPct:0},{label:'W4',equity:1.045,drawdownPct:-5}],metrics:{totalReturnPct:4.5,annualizedReturnPct:4.5,annualizedVolatilityPct:5,maxDrawdownPct:-10,maxDrawdownDurationWeeks:1,winRatePct:50,bestWeekPct:11.11,worstWeekPct:-10,valueAtRisk95Pct:-9,conditionalValueAtRisk95Pct:-10}});
  await page.route('**/api/portfolio-center**',async route=>{
    const path=new URL(route.request().url()).pathname;
    if(path==='/api/portfolio-center') {
      const base=await (await route.fetch()).json() as PortfolioDashboard;
      ledger={...base,positions:[{accountId:'main',market:'CN',symbol:'600519',name:'合成持仓 A',currency:'CNY',quantity:60,averageCost:10,costValue:600,realizedPnl:0,price:10,marketValue:600,quoteAsOf:now},{accountId:'main',market:'CN',symbol:'000001',name:'合成持仓 B',currency:'CNY',quantity:40,averageCost:10,costValue:400,realizedPnl:0,price:10,marketValue:400,quoteAsOf:now}],currencies:[{currency:'CNY',cash:1000,costValue:1000,marketValue:1000,realizedPnl:0,income:0,fees:0}],valuationStatus:'live',updatedAt:now};
      await route.fulfill({json:ledger});return;
    }
    if(path==='/api/portfolio-center/risk-reports') {
      await route.fulfill({json:[{id:'synthetic-history',savedAt:now,dashboard:ledger,performance:performance(),analysisInput:{currency:'CNY',lookbackWeeks:52,riskFreeRatePct:2}}]});return;
    }
    await route.continue();
  });
  await page.goto(`${shell}/?mod=portfolio-risk&workspace=e2e-risk-detail-${Date.now()}`);
  const frame=page.frameLocator('iframe').first();
  await frame.getByLabel('查看历史评估').selectOption('synthetic-history');
  await frame.getByRole('button',{name:'载入历史结果并校验当前条件'}).click();
  await expect(page).toHaveURL(/mod=portfolio-risk-drawdown/);
  await expect(frame.getByLabel('历史窗口')).toHaveValue('52');
  await expect(frame.getByText('当前条件的历史模拟结果',{exact:true})).toBeVisible();
  await expect(frame.getByRole('table',{name:'回撤阶段',exact:true})).toContainText('尚未恢复');
  await page.screenshot({path:testInfo.outputPath('risk-drawdown.png'),fullPage:true});
  await page.getByRole('button',{name:'集中度',exact:true}).click();
  await expect(frame.getByRole('table',{name:'CNY 证券集中度'})).toContainText('69.23%');
  await page.screenshot({path:testInfo.outputPath('risk-concentration.png'),fullPage:true});
  await page.getByRole('button',{name:'压力测试',exact:true}).click();
  await frame.getByLabel('CN 价格冲击 / %').fill('-20');
  await expect(frame.getByRole('table',{name:'压力情景矩阵'}).getByRole('row').filter({hasText:'自定义冲击'})).toContainText('-200');
  await page.screenshot({path:testInfo.outputPath('risk-stress.png'),fullPage:true});
  await page.getByRole('button',{name:'回撤与 VaR',exact:true}).click();
  await expect(frame.getByText('当前条件的历史模拟结果',{exact:true})).toBeVisible();
  await page.setViewportSize({width:390,height:844});
  await expect(frame.getByLabel('历史窗口')).toBeVisible();
  expect(await frame.locator('body').evaluate(el=>el.scrollWidth<=innerWidth)).toBe(true);
});

test('receipt plans stay separate from current cash and survive save and reopen', async ({page,request},testInfo) => {
  const workspace=`e2e-risk-liquidity-${Date.now()}`;
  const dashboardResponse=page.waitForResponse(r=>r.url().includes('/api/portfolio-center?includeQuotes=false'));
  await page.goto(`${shell}/?mod=portfolio-risk&workspace=${workspace}`);
  const identity=await (await dashboardResponse).json() as PortfolioDashboard;
  const headers={'X-User-Id':identity.userId,'X-Workspace-Id':identity.workspaceId};
  const frame=page.frameLocator('iframe').first();
  await frame.getByRole('button',{name:'导入组合',exact:true}).click();
  const today=await frame.getByLabel('持仓截止日').inputValue();
  const day=(days:number)=>{const d=new Date(`${today}T12:00:00`);d.setDate(d.getDate()+days);return d.toLocaleDateString('en-CA')};
  await frame.getByLabel('资金观察日（可选）',{exact:true}).fill(day(3));
  const fields=['assetType','market','symbol','name','account','currency','bookValue','availableCash','equityBeta','ratePnlPerBp','direction','expiryDate','proceedsAmount','proceedsDate','proceedsAccount','proceedsSource'];
  const common={market:'CN',account:'证券',currency:'CNY'};
  const rows:Record<string,string|number>[]=[
    {...common,assetType:'fund',symbol:'F1-TEST',name:'合成预计到账基金',bookValue:25000,equityBeta:0,ratePnlPerBp:0,proceedsAmount:15000,proceedsDate:day(2),proceedsAccount:'期货',proceedsSource:'验收合成计划，未经实际确认'},
    {...common,assetType:'fund',symbol:'F2-TEST',name:'合成慢到账基金',bookValue:25000,equityBeta:0,ratePnlPerBp:0,proceedsAmount:5000,proceedsDate:day(5),proceedsAccount:'期货',proceedsSource:'验收合成计划，未经实际确认'},
    {...common,assetType:'bond_future',symbol:'T-TEST',name:'合成对冲',account:'期货',bookValue:0,direction:'short',ratePnlPerBp:400,expiryDate:day(90)},
    {...common,assetType:'cash',symbol:'CASH-A',name:'现金',bookValue:0,availableCash:0},
    {...common,assetType:'cash',symbol:'CASH-B',name:'现金',account:'期货',bookValue:10000,availableCash:10000},
  ];
  await frame.getByLabel('持仓表格',{exact:true}).fill([fields.join(','),...rows.map(r=>fields.map(f=>r[f]??'').join(','))].join('\n'));
  await frame.getByRole('button',{name:'预览并检查'}).click();
  await expect(frame.getByRole('table',{name:'资金到账计划明细'}).getByRole('row').filter({hasText:'合成慢到账基金'})).toContainText('晚于观察日');
  await expect(frame.getByRole('table',{name:'组合账户现金压力'})).toContainText('-10,000');
  const projected=frame.getByRole('table',{name:'条件到账现金余额'});
  await expect(projected.getByRole('row').filter({hasText:'权益上涨，利率下行'}).getByRole('cell').last()).toHaveText('5,000');
  await frame.getByRole('button',{name:'确认保存快照'}).click();
  await expect(frame.getByRole('status')).toContainText('已保存');
  const records=await (await request.get(`${api}/api/portfolio-center/import-snapshots`,{headers})).json();
  expect(records).toHaveLength(1);
  expect(records[0].report.nav).toBe(60000);
  const conclusion=frame.getByRole('region',{name:'组合风险结论'});
  await expect(conclusion).toContainText('期货：优先核对现金缺口');
  expect(records[0].report.conclusion.findings.filter((f:{kind:string})=>f.kind==='cash_shortfall')).toHaveLength(1);
  await conclusion.getByRole('button',{name:'查看依据'}).first().click();
  await expect(frame.locator('#diagnosis-cash')).toBeFocused();
  expect(records[0].report.alerts.some((x:string)=>x.includes('期货 可用现金不足'))).toBe(true);
  await expect.poll(async()=>{
    const data=await (await request.get(`${api}/api/mods/portfolio-risk/context`,{headers})).json();
    return data.context?.data?.summary?.report?.liquidityPlan?.projections?.[0]?.plannedReceipts;
  }).toBe(15000);
  await page.reload();
  await frame.getByLabel('组合快照',{exact:true}).selectOption(records[0].id);
  await expect(conclusion).toContainText('现金安全垫：存在缺口');
  await expect.poll(async()=>{
    const data=await (await request.get(`${api}/api/mods/portfolio-risk/context`,{headers})).json();
    return data.context?.data?.summary?.report?.conclusion;
  }).toEqual(records[0].report.conclusion);
  await conclusion.screenshot({path:testInfo.outputPath('risk-conclusion.png')});
  await expect(projected.getByRole('row').filter({hasText:'权益上涨，利率下行'}).getByRole('cell').last()).toHaveText('5,000');
  await projected.screenshot({path:testInfo.outputPath('risk-conditional-cash.png')});
  await frame.getByRole('button',{name:'编辑持仓并另存'}).click();
  await frame.getByLabel('近期需留资金（基准币）',{exact:true}).fill('6000');
  await frame.getByText('近期预留分配到账户',{exact:true}).click();
  await frame.getByRole('button',{name:'分配账户预留',exact:true}).click();
  await frame.getByLabel('预留 1 账户',{exact:true}).fill('期货');
  await frame.getByLabel('预留 1 金额（CNY）',{exact:true}).fill('5000');
  await frame.getByLabel('近期需留资金（基准币）',{exact:true}).fill('4000');
  await frame.getByRole('button',{name:'预览并检查'}).click();
  await expect(frame.getByRole('alert')).toContainText('账户预留合计不能超过近期需留资金总额');
  await expect(frame.getByRole('alert')).not.toContainText('Portfolio');
  await expect(frame.getByRole('alert')).not.toContainText('input');
  await expect(frame.getByRole('button',{name:'确认保存快照'})).toHaveCount(0);
  expect(await (await request.get(`${api}/api/portfolio-center/import-snapshots`,{headers})).json()).toHaveLength(1);
  await frame.getByRole('alert').screenshot({path:testInfo.outputPath('risk-actionable-validation.png')});
  await frame.getByLabel('近期需留资金（基准币）',{exact:true}).fill('6000');
  await frame.getByRole('button',{name:'预览并检查'}).click();
  await expect(frame.getByRole('region',{name:'保存前变更核对'})).toContainText('账户预留分配');
  const cash=frame.getByRole('table',{name:'组合账户现金压力'}).getByRole('row').filter({hasText:'权益上涨，利率下行'}).filter({hasText:'期货'});
  await expect(cash.getByRole('cell').last()).toHaveText('-15,000');
  await expect(projected.getByRole('row').filter({hasText:'权益上涨，利率下行'}).getByRole('cell').last()).toHaveText('0');
  await frame.getByRole('button',{name:'确认保存快照'}).click();
  await expect(frame.getByRole('status')).toContainText('已保存');
  const versions=await (await request.get(`${api}/api/portfolio-center/import-snapshots`,{headers})).json();
  expect(versions).toHaveLength(2);
  expect(versions.find((r:{id:string})=>r.id===records[0].id)).toEqual(records[0]);
  const allocated=versions.find((r:{id:string})=>r.id!==records[0].id);
  expect(allocated.report.unallocatedOutflow).toBe(1000);
  expect(allocated.report.scenarios[1].cashAfterKnownNeeds).toBe(-16000);
  expect(allocated.report.nav).toBe(records[0].report.nav);
  await page.reload();
  await frame.getByLabel('组合快照',{exact:true}).selectOption(allocated.id);
  await expect(cash.getByRole('cell').last()).toHaveText('-15,000');
  await expect.poll(async()=>{
    const data=await (await request.get(`${api}/api/mods/portfolio-risk/context`,{headers})).json();
    return data.context?.data?.summary?.report?.unallocatedOutflow;
  }).toBe(1000);
  await frame.getByRole('table',{name:'组合账户现金压力'}).screenshot({path:testInfo.outputPath('risk-account-reserves.png')});
});

test('bond duration and contract DV01 import calculate and persist a transparent hedge', async ({page,request},testInfo) => {
  const workspace=`e2e-risk-duration-${Date.now()}`;
  const dashboardResponse=page.waitForResponse(r=>r.url().includes('/api/portfolio-center?includeQuotes=false'));
  await page.goto(`${shell}/?mod=portfolio-risk&workspace=${workspace}`);
  const identity=await (await dashboardResponse).json() as PortfolioDashboard;
  const headers={'X-User-Id':identity.userId,'X-Workspace-Id':identity.workspaceId};
  const frame=page.frameLocator('iframe').first();
  await frame.getByRole('button',{name:'导入组合',exact:true}).click();
  const today=await frame.getByLabel('持仓截止日').inputValue();
  const expiry=new Date(`${today}T12:00:00`);expiry.setDate(expiry.getDate()+7);
  const fields=['资产类型','市场','代码','名称','账户','币种','账面金额','可用现金','修正久期','持仓手数','每手DV01','利率参数日期','合约到期日','方向','依据'];
  const rows=[
    ['债券','CN','BOND-TEST','合成固定利率债','A','CNY',1000000,'',5,'','',today,'','','验收合成估值'],
    ['国债期货','CN','T-TEST','合成国债期货','A','CNY',0,'','',5,80,today,expiry.toLocaleDateString('en-CA'),'空','验收合成合约DV01'],
    ['现金','','CASH','现金','A','CNY',10000,10000],
  ];
  await frame.getByLabel('持仓表格',{exact:true}).fill([fields.join(','),...rows.map(r=>r.join(','))].join('\n'));
  await frame.getByRole('button',{name:'预览并检查'}).click();
  await expect(frame.getByRole('table',{name:'组合利率对冲'})).toContainText('-100');
  await frame.getByRole('region',{name:'组合风险结论'}).getByRole('listitem').filter({hasText:'核验持仓与研究提示'}).getByRole('button',{name:'查看依据'}).click();
  await expect(frame.locator('#diagnosis-warnings').getByText(/距合约到期 7 天/)).toBeVisible();
  await frame.getByText('利率参数换算与合约期限',{exact:true}).click();
  const details=frame.getByRole('table',{name:'利率参数换算依据'});
  await expect(details).toContainText('−含息市值 × 修正久期');
  await expect(details).toContainText('每手 DV01');
  await expect(details).toContainText('-500');
  await details.screenshot({path:testInfo.outputPath('risk-duration-basis.png')});
  await frame.getByRole('button',{name:'确认保存快照'}).click();
  await expect(frame.getByRole('status')).toContainText('已保存');
  const records=await (await request.get(`${api}/api/portfolio-center/import-snapshots`,{headers})).json();
  expect(records).toHaveLength(1);
  expect(records[0].snapshot.holdings[0].ratePnlPerBp).toBeNull();
  expect(records[0].report.rows[0].resolvedRatePnlPerBp).toBe(-500);
  await expect.poll(async()=>{
    const data=await (await request.get(`${api}/api/mods/portfolio-risk/context`,{headers})).json();
    return data.context?.data?.summary?.report?.rows?.[0]?.resolvedRatePnlPerBp;
  }).toBe(-500);
  await page.reload();
  await frame.getByLabel('组合快照',{exact:true}).selectOption(records[0].id);
  await expect(frame.getByRole('table',{name:'分币种利率敞口'})).toContainText('-100');
  await expect(frame.getByRole('table',{name:'组合账户现金压力'})).toContainText('-10,000');
  await frame.getByRole('button',{name:'编辑持仓并另存'}).click();
  await frame.getByText('自定义压力情景',{exact:true}).click();
  await frame.getByRole('button',{name:'追加压力情景'}).click();
  await frame.getByLabel('情景 1 名称',{exact:true}).fill('利率快速下行');
  await frame.getByLabel('情景 1 权益变动（%）',{exact:true}).fill('0');
  await frame.getByLabel('情景 1 利率变动（bp）',{exact:true}).fill('-100');
  await frame.getByRole('button',{name:'预览并检查'}).click();
  await expect(frame.getByRole('region',{name:'保存前变更核对'})).toContainText('自定义压力情景');
  const stress=frame.getByRole('table',{name:'组合诊断情景'});
  await expect(stress.getByRole('row')).toHaveCount(5);
  await expect(stress.getByRole('row').filter({hasText:'自定义 · 利率快速下行'})).toContainText('-100bp');
  await expect(frame.getByRole('region',{name:'组合风险结论'})).toContainText('-30,000');
  await frame.getByRole('button',{name:'确认保存快照'}).click();
  await expect(frame.getByRole('status')).toContainText('已保存');
  const versions=await (await request.get(`${api}/api/portfolio-center/import-snapshots`,{headers})).json();
  expect(versions).toHaveLength(2);
  expect(versions.find((r:{id:string})=>r.id===records[0].id)).toEqual(records[0]);
  const custom=versions.find((r:{id:string})=>r.id!==records[0].id);
  expect(custom.report.scenarios.slice(0,3)).toEqual(records[0].report.scenarios);
  expect(custom.report.scenarios[3].totalPnl).toBe(10000);
  await page.reload();
  await frame.getByLabel('组合快照',{exact:true}).selectOption(custom.id);
  await expect(stress.getByRole('row')).toHaveCount(5);
  await expect.poll(async()=>{
    const data=await (await request.get(`${api}/api/mods/portfolio-risk/context`,{headers})).json();
    return data.context?.data?.summary?.snapshot?.additionalScenarios;
  }).toEqual([{label:'利率快速下行',equityShockPct:0,rateShockBp:-100}]);
  await stress.screenshot({path:testInfo.outputPath('risk-custom-scenarios.png')});
  await frame.getByText('逐笔持仓情景贡献 · 定位亏损与期货现金需求',{exact:true}).click();
  await frame.getByRole('combobox',{name:'贡献分析情景',exact:true}).selectOption('自定义 · 利率快速下行');
  const contributions=frame.getByRole('table',{name:'逐笔情景损益贡献'});
  await expect(contributions.getByRole('row').nth(1)).toContainText('合成国债期货');
  const future=contributions.getByRole('row').filter({hasText:'合成国债期货'});
  await expect(future.getByRole('cell').nth(1)).toHaveText('-40,000');
  await expect(future.getByRole('cell').nth(2)).toHaveText('40,000');
  await expect(contributions.getByRole('row').filter({hasText:'合成固定利率债'})).toContainText('50,000');
  await future.getByText('查看参数与来源',{exact:true}).click();
  await expect(future).toContainText('验收合成合约DV01');
  await expect.poll(async()=>{
    const data=await (await request.get(`${api}/api/mods/portfolio-risk/context`,{headers})).json();
    return data.context?.data?.summary?.report?.scenarios?.[3]?.contributions;
  }).toEqual(custom.report.scenarios[3].contributions);
  await contributions.screenshot({path:testInfo.outputPath('risk-holding-contributions.png')});
});

test('mixed snapshot import previews, persists, preserves ledger and publishes its own Agent evidence', async ({page,request},testInfo) => {
  const workspace=`e2e-risk-import-${Date.now()}`;
  const dashboardResponse=page.waitForResponse(r=>r.url().includes('/api/portfolio-center?includeQuotes=false'));
  await page.goto(`${shell}/?mod=portfolio-risk&workspace=${workspace}`);
  const identity=await (await dashboardResponse).json() as PortfolioDashboard;
  const headers={'X-User-Id':identity.userId,'X-Workspace-Id':identity.workspaceId};
  const frame=page.frameLocator('iframe').first();
  const fields=['assetType','market','symbol','name','account','currency','bookValue','availableCash','equityBeta','equityBenchmark','ratePnlPerBp','direction','notional','source','issuer'];
  const base={market:'CN',account:'证券账户',currency:'CNY',bookValue:100,source:'明确标注的验收合成数据'};
  const rows:Record<string,string|number>[]=[
    ...Array.from({length:8},(_,i)=>({...base,assetType:'stock',symbol:`S${i}`,name:`合成股票${i}`,equityBeta:1,equityBenchmark:'CSI300'})),
    ...Array.from({length:3},(_,i)=>({...base,assetType:'fund',symbol:`F${i}`,name:`合成基金${i}`,equityBeta:0.5,equityBenchmark:'CSI300',ratePnlPerBp:-0.5})),
    ...Array.from({length:10},(_,i)=>({...base,assetType:'bond',symbol:`B${i}`,name:`合成债券${i}`,ratePnlPerBp:-1})),
    {...base,assetType:'equity_future',account:'期货账户',symbol:'IF-TEST',name:'合成股指期货',bookValue:0,direction:'short',notional:800,equityBenchmark:'CSI300'},
    {...base,assetType:'bond_future',account:'期货账户',symbol:'T-TEST',name:'合成国债期货',bookValue:0,direction:'short',ratePnlPerBp:10},
    ...['证券账户','期货账户'].map(account=>({...base,assetType:'cash',account,symbol:'CASH',name:'现金',bookValue:50,availableCash:50})),
  ];
  rows[0].issuer='合成发行主体';
  rows[8].issuer='合成发行主体'; // A fund manager must not become underlying issuer exposure.
  rows[11].issuer='合成发行主体';
  await frame.getByRole('button',{name:'导入组合',exact:true}).click();
  await frame.getByLabel('组合名称',{exact:true}).fill('混合持仓验收（合成）');
  await frame.getByLabel('净值底线（基准币）').fill('2100');
  await frame.getByLabel('持仓表格',{exact:true}).fill([fields.join(','),...rows.map(r=>fields.map(f=>r[f]??'').join(','))].join('\n'));
  await frame.getByRole('button',{name:'预览并检查'}).click();
  await expect(frame.getByRole('table',{name:'组合诊断情景'}).getByRole('row').filter({hasText:'权益下跌，利率上行'})).toContainText('-90');
  await expect(frame.getByRole('table',{name:'组合账户现金压力'})).toContainText('-530');
  expect(await (await request.get(`${api}/api/portfolio-center/import-snapshots`,{headers})).json()).toEqual([]);
  await frame.getByRole('button',{name:'确认保存快照'}).click();
  await expect(frame.getByRole('status')).toContainText('已保存');
  const saved=await (await request.get(`${api}/api/portfolio-center/import-snapshots`,{headers})).json();
  expect(saved).toHaveLength(1);
  expect(saved[0].report.issuerExposure.items[0].baseValue).toBe(200);
  expect(saved[0].report.issuerExposure.items[0].crossAsset).toBe(true);
  await expect(frame.getByRole('table',{name:'发行人集中暴露明细'})).toContainText('9.09%');
  await expect(frame.getByRole('table',{name:'发行人集中暴露明细'})).toContainText('股债同主体');
  await frame.getByRole('table',{name:'发行人集中暴露明细'}).screenshot({path:testInfo.outputPath('risk-issuer-exposure.png')});
  await expect.poll(async()=>{
    const data=await (await request.get(`${api}/api/mods/portfolio-risk/context`,{headers})).json();
    return data.context?.data?.summary?.id;
  }).toBe(saved[0].id);
  const context=await (await request.get(`${api}/api/mods/portfolio-risk/context`,{headers})).json();
  expect(context.context.filters.source).toBe('imported-snapshot');
  expect(context.context.data.summary.report.nav).toBe(2200);
  expect(context.context.data.summary.report.issuerExposure.items[0].baseValue).toBe(200);
  expect(context.context.actions).toEqual([]);
  expect(context.context.data.summary.riskAssessment).toBeUndefined();
  await expect(frame.getByRole('heading',{name:'风险核验清单'})).toHaveCount(0);
  const ledger=await (await request.get(`${api}/api/portfolio-center?includeQuotes=false`,{headers})).json();
  expect(ledger.positions).toEqual([]);
  expect(ledger.activities).toEqual([]);
  await frame.getByRole('button',{name:'读取基金证据并留档'}).click();
  await expect(frame.getByRole('table',{name:'基金上游风险证据'})).toContainText('暂无证据');
  const versions=await (await request.get(`${api}/api/portfolio-center/import-snapshots`,{headers})).json();
  expect(versions).toHaveLength(2);
  const enriched=versions.find((r:{id:string})=>r.id!==saved[0].id);
  expect(enriched.snapshot).toEqual(saved[0].snapshot);
  expect(enriched.report.scenarios).toEqual(saved[0].report.scenarios);
  expect(enriched.report.researchEvidence).toHaveLength(3);
  await expect.poll(async()=>{
    const data=await (await request.get(`${api}/api/mods/portfolio-risk/context`,{headers})).json();
    return data.context?.data?.summary?.report?.researchEvidence?.length;
  }).toBe(3);
  await page.reload();
  await frame.getByLabel('组合快照',{exact:true}).selectOption(enriched.id);
  await expect(frame.getByRole('table',{name:'基金上游风险证据'})).toContainText('暂无证据');
  await frame.getByRole('table',{name:'基金上游风险证据'}).screenshot({path:testInfo.outputPath('risk-fund-evidence.png')});
  await frame.getByLabel('组合快照',{exact:true}).selectOption(saved[0].id);
  await expect(frame.getByRole('table',{name:'基金上游风险证据'})).toHaveCount(0);
  await expect(frame.getByRole('table',{name:'发行人集中暴露明细'})).toContainText('9.09%');
  const reassessedResponse=page.waitForResponse(r=>r.url().endsWith('/api/portfolio-center/import-snapshots')&&r.request().method()==='POST');
  await frame.getByRole('button',{name:'按最新口径重评估'}).click();
  const reassessed=await (await reassessedResponse).json();
  expect(reassessed.snapshot).toEqual(saved[0].snapshot);
  expect(reassessed.report.issuerExposure.items[0].baseValue).toBe(200);
  const retained=await (await request.get(`${api}/api/portfolio-center/import-snapshots`,{headers})).json();
  expect(retained.find((r:{id:string})=>r.id===saved[0].id)).toEqual(saved[0]);
  expect(retained.find((r:{id:string})=>r.id===enriched.id)).toEqual(enriched);
  await expect(frame.getByRole('table',{name:'组合诊断情景'})).toContainText('-90');
  await page.screenshot({path:testInfo.outputPath('risk-import-diagnosis.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  expect(await frame.locator('body').evaluate(el=>el.scrollWidth<=innerWidth)).toBe(true);
  await frame.getByLabel('组合快照',{exact:true}).selectOption('');
  await expect(frame.getByRole('heading',{name:'风险核验清单'})).toBeVisible();
});
