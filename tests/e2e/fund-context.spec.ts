import {test,expect} from '@playwright/test';

const fundApiOrigin=process.env.FUND_E2E_API_ORIGIN||'http://127.0.0.1:8035';

test('fund NAV live refresh saves official records and exposes latest dates',async({page,request},testInfo)=>{
  test.skip(process.env.FUND_E2E_ALLOW_NAV_REFRESH !== '1','Opt-in: updates two fund NAV caches and latest-NAV metadata');
  for(const code of ['000015.OF','000028.OF']){
    await page.goto(`http://127.0.0.1:3035/funds/${code}`);
    const responsePromise=page.waitForResponse(r=>r.url().endsWith(`/api/funds/${code}/nav-refresh`)&&r.request().method()==='POST');
    await expect(page.getByRole('button',{name:'更新净值',exact:true})).toBeVisible();
    await page.getByRole('button',{name:'更新净值',exact:true}).click();
    const response=await responsePromise;
    expect(response.ok()).toBe(true);
    const result=await response.json();
    expect(result.status).toBe('synced');
    expect(result.source).toBe('tushare.fund_nav');
    expect(result.metrics_recalculated).toBe(false);
    expect(result.adjusted_observations).toBe(result.observations);
    await expect(page.getByRole('status')).toContainText(`已更新至 ${result.latest_nav_date}`);
    const localResponse=await request.get(`${fundApiOrigin}/api/funds/${code}/nav?start_date=${result.requested_start_date}&end_date=${result.requested_end_date}`);
    expect(localResponse.ok()).toBe(true);
    const local=await localResponse.json();
    expect(local.source).toBe('local.postgres.fund_nav');
    expect(local.data.at(-1).date).toBe(result.latest_nav_date);
    expect(local.data.at(-1).adj_nav).toBeGreaterThan(0);
    await page.getByRole('status').screenshot({path:testInfo.outputPath(`live-nav-${code}.png`)});
    await testInfo.attach(`nav-result-${code}`,{body:JSON.stringify(result,null,2),contentType:'application/json'});
  }
});

test('fund NAV update reports failures, blocks duplicate requests and preserves saved result',async({page},testInfo)=>{
  let calls=0, release!:()=>void;
  const gate=new Promise<void>(resolve=>{release=resolve;});
  await page.route('**/api/funds/000015.OF/nav-refresh',async route=>{
    calls++;
    if(calls===1){await route.fulfill({status:500,json:{detail:'净值保存失败，本次写入已回滚'}});return;}
    await gate;
    await route.fulfill({json:{status:'synced',latest_nav_date:'2026-09-30',observations:21,adjusted_observations:20,metrics_recalculated:false}});
  });
  await page.goto('http://127.0.0.1:3035/funds/000015.OF');
  const button=page.getByRole('button',{name:'更新净值',exact:true});
  await expect(button).toBeVisible();
  await button.click();
  await expect(page.getByRole('status')).toContainText('净值保存失败，本次写入已回滚');
  await button.click();
  const updating=page.getByRole('button',{name:'正在更新净值',exact:true});
  await expect(updating).toBeDisabled();
  await updating.evaluate(el=>{(el as HTMLButtonElement).click();});
  expect(calls).toBe(2);
  release();
  await expect(page.getByRole('status')).toContainText('已更新至 2026-09-30');
  await expect(page.getByRole('status')).toContainText('21 条净值，20 条有复权值');
  await expect(page.getByRole('status')).toContainText('评价指标未重算');
  await expect(button).toBeEnabled();
  await page.getByRole('status').screenshot({path:testInfo.outputPath('nav-update-result.png')});
});

test('embedded fund NAV update shares actual action state with Desk Agent',async({page,request})=>{
  const workspace=`fund-nav-${Date.now()}`,user='fund-nav-acceptance';
  await page.addInitScript(({workspace,user})=>{localStorage.setItem('vibedesk.userId.v1',user);localStorage.setItem('vibedesk.workspaceId.v1',workspace);},{workspace,user});
  await page.route('**/api/funds/000015.OF/nav-refresh',route=>route.fulfill({status:502,json:{detail:'官方净值读取失败，请稍后重试'}}));
  await page.goto(`http://127.0.0.1:5888/?${new URLSearchParams({mod:'fund-discover',workspace,modSearch:'symbol=000015.OF'})}`);
  const frame=page.frameLocator('iframe[title="找基金"]');
  const read=async()=>(await(await request.get('http://127.0.0.1:8911/api/mods/fund-discover/context',{headers:{'X-User-Id':user,'X-Workspace-Id':workspace}})).json()).context;
  await expect(frame.getByRole('button',{name:'更新净值',exact:true})).toBeVisible();
  await frame.getByRole('button',{name:'更新净值',exact:true}).click();
  await expect(frame.getByRole('status')).toContainText('官方净值读取失败');
  await expect.poll(async()=>(await read())?.data?.summary?.page?.sections?.['nav-refresh']?.summary?.status).toBe('error');
  const section=(await read()).data.summary.page.sections['nav-refresh'].summary;
  expect(section.fundCode).toBe('000015.OF');
  expect(section.result).toBeNull();
  expect(section.message).toContain('官方净值读取失败');
});

test('bond duration live calculation persists results and exposes weak evidence',async({page,request},testInfo)=>{
  test.skip(process.env.FUND_E2E_ALLOW_CALCULATE !== '1', 'Opt-in: saves two real research estimates, never holdings or trades');
  for(const code of ['000015.OF','000028.OF']){
    await page.goto(`http://127.0.0.1:3035/funds/${code}`);
    const panel=page.locator('section').filter({has:page.getByRole('heading',{name:'净值回归久期',exact:true})});
    await expect(panel).toContainText('指数数据就绪 40/40');
    const responsePromise=page.waitForResponse(r=>r.url().includes(`/api/funds/${code}/bond-duration?`) && r.request().method()==='POST');
    await panel.getByRole('button',{name:/现场测算久期|重新测算/}).click();
    const response=await responsePromise;
    expect(response.ok()).toBe(true);
    const result=await response.json();
    expect(result.methodology_version).toBe('jigouyun_public_rbsa_adj_endpoints_v3');
    expect(result.observations).toBe(104);
    expect(result.estimated_duration).toBeGreaterThan(0);
    await expect(panel).toContainText(`${result.estimated_duration.toFixed(2)} 年`);
    if(!result.formal_duration_ready){
      await expect(panel).toContainText('暂不判定');
      await expect(panel).toContainText('原始模型输出');
      await expect(panel).toContainText('不能当作当前有效久期');
      await expect(panel).toContainText(result.missing_items[0]);
    }
    const cached=await (await request.get(`${fundApiOrigin}/api/funds/${code}/bond-duration`)).json();
    expect(cached.estimated_duration).toBe(result.estimated_duration);
    expect(cached.formal_duration_ready).toBe(result.formal_duration_ready);
    await panel.screenshot({path:testInfo.outputPath(`duration-${code}.png`)});
  }
});

test('bond evidence uses adjusted NAV and shows current peer coverage',async({page,request},testInfo)=>{
  const response=await request.get(`${fundApiOrigin}/api/funds/000015.OF/bond-anomaly`);
  expect(response.ok()).toBe(true);
  const evidence=await response.json();
  expect(evidence.nav_basis).toBe('adj_nav');
  expect(evidence.status).toBe('available');
  expect(typeof evidence.current_peer_count).toBe('number');
  await page.goto('http://127.0.0.1:3035/funds/000015.OF');
  const panel=page.locator('section').filter({has:page.getByRole('heading',{name:'债基净值异常监控',exact:true})});
  await expect(panel).toContainText('复权净值26期下轨');
  await expect(panel).toContainText(`最新区间有效 ${evidence.current_peer_count} 只`);
  await expect(panel).toContainText(evidence.current_label);
  await expect(panel).toContainText('近5期涨跌');
  await panel.scrollIntoViewIfNeeded();
  await panel.screenshot({path:testInfo.outputPath('bond-adjusted-evidence.png')});
});

test('bond missing adjusted NAV is unavailable rather than normal',async({request})=>{
  const response=await request.get(`${fundApiOrigin}/api/funds/000003.OF/bond-anomaly`);
  expect(response.ok()).toBe(true);
  const evidence=await response.json();
  expect(evidence.nav_basis).toBe('adj_nav');
  expect(evidence.status).toBe('insufficient_evidence');
  expect(evidence.formal_monitor_ready).toBe(false);
  expect(evidence.market_regime).toBe('unknown');
  expect(evidence.missing_items.join(' ')).toContain('复权净值');
});

test('material evidence requires preview and confirmation, preserves zero and refuses overwrite',async({page,request},testInfo)=>{
  const workspace=`material-action-${Date.now()}`,user='fund-action-acceptance';
  await page.addInitScript(({workspace,user})=>{localStorage.setItem('vibedesk.userId.v1',user);localStorage.setItem('vibedesk.workspaceId.v1',workspace);},{workspace,user});
  const read=async()=>(await(await request.get('http://127.0.0.1:8911/api/mods/fund-research-library/context',{headers:{'X-User-Id':user,'X-Workspace-Id':workspace}})).json()).context;
  const writes:any[]=[];let allow=false,readFail=false;
  await page.route('**/api/evidence-coverage/materials?**',route=>route.fulfill(readFail?{status:503,json:{error:'验收保存后刷新失败'}}:{json:{total:0,rules:[],source:'隔离样本'}}));
  await page.route('**/api/evidence-coverage/materials',async route=>{
    if(route.request().method()!=='POST'){await route.abort();return;}
    const body=route.request().postDataJSON();writes.push(body);
    if(!allow){await route.fulfill({status:422,json:{savedCount:0,failedCount:1,failed:[{error:'该基金和平台已有来源记录，未覆盖'}]}});return;}
    readFail=true;await route.fulfill({json:{savedCount:1,failedCount:0,saved:body.rules}});
  });
  await page.goto(`http://127.0.0.1:5888/?${new URLSearchParams({mod:'fund-research-library',workspace,modSearch:'view=evidence&section=materials&codes=000171.OF'})}`);
  const frame=page.frameLocator('iframe');
  await expect.poll(async()=>(await read())?.data?.summary?.page?.status).toBe('ready');
  await frame.getByRole('button',{name:'新增来源证据',exact:true}).click();
  const panel=frame.getByRole('region',{name:'证据处置'});
  await panel.getByRole('button',{name:'检查并预览',exact:true}).click();
  await expect(panel.getByRole('alert')).toContainText('实际销售平台');expect(writes).toHaveLength(0);
  await panel.getByLabel('证据平台或机构').fill('隔离验收机构');
  await panel.getByLabel('来源核验日期').fill(new Date().toISOString().slice(0,10));
  await panel.getByLabel('来源说明').fill('基金合同费率章节，核验本渠道免收申购费。');
  await panel.getByLabel('申购费率（%）',{exact:true}).fill('0');
  await panel.getByRole('button',{name:'检查并预览',exact:true}).click();
  await expect(panel.getByRole('button',{name:'确认提交',exact:true})).toBeDisabled();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.sections?.['evidence-action']?.summary?.proposed?.purchaseFeeRate).toBe(0);
  const draft=(await read()).data.summary.page.sections['evidence-action'].summary.proposed;
  expect(draft.salesServiceFeeRate).toBeUndefined();expect(draft.riskLevel).toBeUndefined();
  await panel.getByRole('checkbox').check();
  await panel.getByRole('button',{name:'确认提交',exact:true}).click();
  await expect(panel.getByRole('alert')).toContainText('未覆盖');
  expect(writes[0].createOnly).toBe(true);expect(writes[0].rules[0].purchaseFeeRate).toBe(0);
  await expect(panel.getByLabel('证据平台或机构')).toHaveValue('隔离验收机构');
  await page.screenshot({path:testInfo.outputPath('material-confirmation.png')});
  allow=true;await panel.getByRole('button',{name:'确认提交',exact:true}).click();
  await expect(frame.getByRole('status').filter({hasText:'来源证据已新增'})).toBeVisible();
  await expect(frame.getByRole('alert').filter({hasText:'验收保存后刷新失败'})).toBeVisible();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.lastOperation).toContain('已新增');
  expect(writes).toHaveLength(2);
});

test('review disposition requires confirmation and only updates after server success',async({page,request})=>{
  const workspace=`review-action-${Date.now()}`,user='fund-review-acceptance';
  await page.addInitScript(({workspace,user})=>{localStorage.setItem('vibedesk.userId.v1',user);localStorage.setItem('vibedesk.workspaceId.v1',workspace);},{workspace,user});
  const read=async()=>(await(await request.get('http://127.0.0.1:8911/api/mods/fund-research-library/context',{headers:{'X-User-Id':user,'X-Workspace-Id':workspace}})).json()).context;
  let status='open',allow=false;const writes:any[]=[];
  await page.route('**/api/evidence-coverage/review-events?**',route=>route.fulfill({json:{count:1,events:[{id:'isolated-event',fund_id:'000171.OF',title:'验收来源复查',status}]}}));
  await page.route('**/api/evidence-coverage/review-events/events/isolated-event',route=>{
    const body=route.request().postDataJSON();writes.push(body);
    if(!allow)return route.fulfill({status:503,json:{error:'验收处置失败'}});
    status=body.status;return route.fulfill({json:{id:'isolated-event',status}});
  });
  await page.goto(`http://127.0.0.1:5888/?${new URLSearchParams({mod:'fund-research-library',workspace,modSearch:'view=evidence&section=review-events'})}`);
  const frame=page.frameLocator('iframe');
  await expect.poll(async()=>(await read())?.data?.summary?.page?.status).toBe('ready');
  await frame.getByRole('button',{name:'处置事件',exact:true}).click();
  const panel=frame.getByRole('region',{name:'证据处置'});
  await expect(panel.getByRole('button',{name:'确认提交',exact:true})).toBeDisabled();
  await panel.getByRole('checkbox').check();await panel.getByRole('button',{name:'确认提交',exact:true}).click();
  await expect(panel.getByRole('alert')).toContainText('验收处置失败');
  expect(status).toBe('open');
  allow=true;await panel.getByRole('button',{name:'确认提交',exact:true}).click();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.rows?.[0]?.status).toBe('acknowledged');
  expect(writes).toEqual([{status:'acknowledged'},{status:'acknowledged'}]);
  await frame.getByRole('button',{name:'处置事件',exact:true}).click();
  await panel.getByRole('checkbox').check();await panel.getByRole('button',{name:'确认提交',exact:true}).click();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.rows?.[0]?.status).toBe('resolved');
  await expect(frame.getByRole('button',{name:'处置事件',exact:true})).toBeDisabled();
  const invalid=await request.patch('http://127.0.0.1:3035/api/evidence-coverage/review-events/events/invalid',{data:{status:'invalid'}});
  expect(invalid.status()).toBe(400);
});

test('real saved reports and material records are readable inside Desk',async({page,request},testInfo)=>{
  const workspace=`research-records-real-${Date.now()}`,user='fund-records-real-acceptance';
  await page.addInitScript(({workspace,user})=>{localStorage.setItem('vibedesk.userId.v1',user);localStorage.setItem('vibedesk.workspaceId.v1',workspace);},{workspace,user});
  const read=async()=>(await(await request.get('http://127.0.0.1:8911/api/mods/fund-research-library/context',{headers:{'X-User-Id':user,'X-Workspace-Id':workspace}})).json()).context;
  const goto=async(search:string)=>page.goto(`http://127.0.0.1:5888/?${new URLSearchParams({mod:'fund-research-library',workspace,modSearch:search})}`);
  await goto('view=reports');
  await expect.poll(async()=>(await read())?.data?.summary?.page?.status,{timeout:45000}).toBe('ready');
  const reportContext=(await read()).data.summary.page;expect(reportContext.rows.length).toBeGreaterThan(0);
  await page.screenshot({path:testInfo.outputPath('real-report-list.png')});
  const materials=await(await request.get('http://127.0.0.1:3035/api/evidence-coverage/materials?limit=100')).json();
  expect(Array.isArray(materials.rules)).toBe(true);
  await goto('view=evidence&section=materials');
  await expect.poll(async()=>(await read())?.data?.summary?.page?.view).toBe('materials');
  await expect.poll(async()=>(await read())?.data?.summary?.page?.status).toBe('ready');
  expect((await read()).data.summary.page.sourceTotal).toBe(materials.total);
  expect((await read()).data.summary.page.rows).toEqual(materials.rules.slice(0,25));
  expect((await read()).data.freshness).toBe('unknown');
  await page.screenshot({path:testInfo.outputPath('real-material-records.png')});
});

test('report list keeps submitted filters, details and read failures in Desk',async({page,request},testInfo)=>{
  const workspace=`reports-${Date.now()}`,user='fund-reports-acceptance';
  await page.addInitScript(({workspace,user})=>{localStorage.setItem('vibedesk.userId.v1',user);localStorage.setItem('vibedesk.workspaceId.v1',workspace);},{workspace,user});
  const read=async()=>(await(await request.get('http://127.0.0.1:8911/api/mods/fund-research-library/context',{headers:{'X-User-Id':user,'X-Workspace-Id':workspace}})).json()).context;
  const report={id:'acceptance-report',title:'验收研究留痕',content:'历史报告，不代表最新净值。',summary:'隔离样本',targetId:'000171.OF',targetType:'fund',reportType:'fund_research_report',reportTypeLabel:'基金研究',reportDate:'2026-08-01',source:'隔离样本',tags:[],relatedCodes:['000171.OF'],managerId:null,createdAt:'2026-08-01',actionHref:'/reports/acceptance-report',keyPoints:[]};
  let failed=false;const calls:string[]=[];
  await page.route('**/api/reports?**',route=>{
    const search=new URL(route.request().url()).searchParams.get('search')||'';calls.push(search);
    return route.fulfill(failed?{status:503,json:{error:'验收报告读取失败'}}:{json:{data:[report],pagination:{total:1,totalPages:1}}});
  });
  await page.route('**/api/reports/acceptance-report',route=>route.fulfill({json:report}));
  await page.goto(`http://127.0.0.1:5888/?${new URLSearchParams({mod:'fund-research-library',workspace,modSearch:'view=reports'})}`);
  const frame=page.frameLocator('iframe');
  await expect.poll(async()=>(await read())?.data?.summary?.page?.status).toBe('ready');
  await frame.getByPlaceholder('搜索报告标题、内容或摘要...').fill('验收');
  await expect.poll(async()=>(await read())?.filters?.draftSearch).toBe('验收');
  expect((await read()).filters.applied.search).toBe('');expect(calls).toEqual(['']);
  await frame.getByRole('button',{name:'搜索',exact:true}).click();
  await expect.poll(async()=>(await read())?.filters?.applied?.search).toBe('验收');
  expect(new URLSearchParams(new URL(page.url()).searchParams.get('modSearch')||'').get('search')).toBe('验收');
  await page.screenshot({path:testInfo.outputPath('report-list.png')});
  await frame.getByRole('link',{name:'查看报告',exact:true}).click();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.report?.id).toBe(report.id);
  await frame.getByRole('link',{name:'返回报告列表',exact:true}).click();
  await expect.poll(async()=>(await read())?.filters?.applied?.search).toBe('验收');
  failed=true;await frame.getByRole('button',{name:'搜索',exact:true}).click();
  await expect(frame.getByRole('alert').filter({hasText:'验收报告读取失败'})).toBeVisible();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.status).toBe('error');
  expect((await read()).data.summary.page.rows).toEqual([]);
  expect((await read()).data.summary.page.total).toBeNull();
  await expect(frame.getByText('暂无本地基金研究报告',{exact:true})).toHaveCount(0);
  failed=false;await frame.getByRole('button',{name:'重试读取列表',exact:true}).click();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.status).toBe('ready');
});

test('evidence sections preserve missing values and never write or hide read failures',async({page,request},testInfo)=>{
  const workspace=`evidence-${Date.now()}`,user='fund-evidence-acceptance';
  await page.addInitScript(({workspace,user})=>{localStorage.setItem('vibedesk.userId.v1',user);localStorage.setItem('vibedesk.workspaceId.v1',workspace);},{workspace,user});
  const read=async()=>(await(await request.get('http://127.0.0.1:8911/api/mods/fund-research-library/context',{headers:{'X-User-Id':user,'X-Workspace-Id':workspace}})).json()).context;
  let failed=false;const methods:string[]=[];
  await page.route('**/api/evidence-coverage/review-events?**',route=>{methods.push(route.request().method());return route.fulfill(failed?{status:503,json:{error:'验收复查读取失败'}}:{json:{count:2,events:[
    {id:'e1',fund_id:'000171.OF',title:'验收材料过期',message:'请核验来源',severity:'high',status:'open',triggered_at:'2026-08-01'},
    {id:'e2',fund_id:'000002.OF',title:'其他对象',severity:'low',status:'resolved'},
  ]}})});
  await page.route('**/api/evidence-coverage/materials?**',route=>{methods.push(route.request().method());return route.fulfill({json:{total:1,missingCodes:['000002.OF'],source:'隔离样本',rules:[
    {windCode:'000171.OF',platform:'验收平台',purchaseStatusLabel:'待核',purchaseFeeRate:0.15,salesServiceFeeRate:null,riskLevel:null,sourceUpdatedAt:null,sourceUrl:null,notes:'材料待补'},
  ]}})});
  await page.route('**/api/evidence-coverage',route=>route.fulfill({json:{totalFunds:2,coverageScore:0,generatedAt:'2026-08-01',source:'隔离样本',dimensions:[],groupSummary:[],priorityQueue:[],gapFunds:[]}}));
  await page.goto(`http://127.0.0.1:5888/?${new URLSearchParams({mod:'fund-research-library',workspace,modSearch:'view=evidence&section=review-events&codes=000171.OF'})}`);
  const frame=page.frameLocator('iframe');
  await expect.poll(async()=>(await read())?.data?.summary?.page?.filteredCount).toBe(1);
  await expect(frame.getByText('验收材料过期',{exact:true})).toBeVisible();
  await expect(frame.getByText('其他对象',{exact:true})).toHaveCount(0);
  failed=true;await frame.getByRole('button',{name:'查询证据',exact:true}).click();
  await expect(frame.getByRole('alert').filter({hasText:'验收复查读取失败'})).toBeVisible();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.filteredCount).toBeNull();
  failed=false;await frame.getByRole('button',{name:'重试读取证据',exact:true}).click();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.filteredCount).toBe(1);
  await frame.getByRole('link',{name:'材料证据',exact:true}).click();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.view).toBe('materials');
  await expect.poll(async()=>(await read())?.data?.summary?.page?.status).toBe('ready');
  expect((await read()).data.summary.page.rows[0].riskLevel).toBeNull();
  await expect(frame.getByText('申购费率：0.15%',{exact:true})).toBeVisible();
  await expect(frame.getByText('销售服务费：—',{exact:true})).toBeVisible();
  await expect(frame.getByText('未找到材料记录：000002.OF',{exact:true})).toBeVisible();
  expect(methods.every(method=>method==='GET')).toBe(true);
  await page.screenshot({path:testInfo.outputPath('evidence-materials.png')});
  await frame.getByRole('link',{name:'覆盖总览',exact:true}).click();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.view).toBe('evidence-coverage');
  await expect.poll(async()=>(await read())?.data?.summary?.page?.result?.totalFunds).toBe(2);
  expect((await read()).data.asOf).toBeUndefined();
});

test('real manager comparison and saved report load without generation',async({page,request},testInfo)=>{
  const workspace=`fund-research-real-${Date.now()}`,user='fund-real-acceptance';
  await page.addInitScript(({workspace,user})=>{localStorage.setItem('vibedesk.userId.v1',user);localStorage.setItem('vibedesk.workspaceId.v1',workspace);},{workspace,user});
  const read=async()=>(await(await request.get('http://127.0.0.1:8911/api/mods/fund-research-library/context',{headers:{'X-User-Id':user,'X-Workspace-Id':workspace}})).json()).context;
  const browser=await(await request.get(`${fundApiOrigin}/api/managers/browser?page_size=2`)).json();
  const ids=browser.managers.map((m:{id:string})=>m.id);
  expect(ids).toHaveLength(2);
  const search=new URLSearchParams({view:'manager-compare'});ids.forEach((id:string)=>search.append('manager_id',id));
  await page.goto(`http://127.0.0.1:5888/?${new URLSearchParams({mod:'fund-research-library',workspace,modSearch:search.toString()})}`);
  await expect.poll(async()=>(await read())?.data?.summary?.page?.result?.managers?.length,{timeout:45000}).toBe(2);
  expect((await read()).filters.requested.managerIds).toEqual(ids);
  expect((await read()).selection).toEqual({});
  await page.screenshot({path:testInfo.outputPath('real-manager-comparison.png')});
  const reports=await(await request.get('http://127.0.0.1:3035/api/reports?page=1&pageSize=1')).json();
  const report=reports.data[0];expect(report.id).toBeTruthy();
  await page.goto(`http://127.0.0.1:5888/?${new URLSearchParams({mod:'fund-research-library',workspace,modSearch:new URLSearchParams({view:'report',reportId:report.id}).toString()})}`);
  await expect.poll(async()=>(await read())?.data?.summary?.page?.report?.id).toBe(report.id);
  const frame=page.frameLocator('iframe');
  await expect(frame.getByRole('heading',{name:report.title,exact:true})).toBeVisible();
  expect((await read()).data.freshness).toBe('unknown');
  await page.screenshot({path:testInfo.outputPath('real-fund-report.png')});
});

test('manager comparison preserves all manager ids and separates failed evidence from empty results',async({page,request})=>{
  const workspace=`manager-compare-${Date.now()}`,user='fund-acceptance';
  await page.addInitScript(({workspace,user})=>{localStorage.setItem('vibedesk.userId.v1',user);localStorage.setItem('vibedesk.workspaceId.v1',workspace);},{workspace,user});
  const read=async()=>(await(await request.get('http://127.0.0.1:8911/api/mods/fund-research-library/context',{headers:{'X-User-Id':user,'X-Workspace-Id':workspace}})).json()).context;
  const managers=['验收甲','验收乙','验收丙'].map((name,i)=>({id:`fixture-${i}`,name,company:'隔离样本',current_fund_count:0,current_share_count:0,memo_count:0,current_products:[],selected_category_products:[],product_tenures:[],history:[]}));
  await page.route('**/api/managers/browser?**',route=>route.fulfill({json:{managers}}));
  const calls:string[][]=[];
  await page.route('**/api/managers/compare?**',async route=>{
    const ids=new URL(route.request().url()).searchParams.getAll('manager_id');calls.push(ids);
    if(ids.length===3){await route.fulfill({status:503,json:{detail:'验收对比失败'}});return;}
    await route.fulfill({json:{status:'insufficient_evidence',categories:[],managers:managers.filter(m=>ids.includes(m.id)),common_period:{status:'insufficient_evidence',observation_count:0,metrics:{},leaders:{}},simulation_used:false}});
  });
  const search=new URLSearchParams({view:'manager-compare'});search.append('manager_id','fixture-0');search.append('manager_id','fixture-1');
  await page.goto(`http://127.0.0.1:5888/?${new URLSearchParams({mod:'fund-research-library',workspace,modSearch:search.toString()})}`);
  const frame=page.frameLocator('iframe');
  await expect.poll(async()=>(await read())?.data?.summary?.page?.result?.managers?.length).toBe(2);
  expect(calls[0]).toEqual(['fixture-0','fixture-1']);
  expect((await read()).selection).toEqual({});
  await frame.getByRole('button').filter({hasText:'验收丙'}).click();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.status).toBe('error');
  expect(calls.at(-1)).toEqual(['fixture-0','fixture-1','fixture-2']);
  expect((await read()).data.summary.page.result).toBeNull();
  await expect(frame.getByRole('alert').filter({hasText:'验收对比失败'})).toBeVisible();
  await frame.getByRole('button',{name:'清空',exact:true}).click();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.status).toBe('needs-selection');
  expect((await read()).data.summary.page.error).toBeNull();
});

test('manager career publishes dynamic evidence without replacing the manager profile',async({page,request})=>{
  const workspace=`manager-career-${Date.now()}`,user='fund-acceptance';
  const managers=await(await request.get(`${fundApiOrigin}/api/managers/browser?page_size=1`)).json();
  const managerId=managers.managers[0].id;
  await page.addInitScript(({workspace,user})=>{localStorage.setItem('vibedesk.userId.v1',user);localStorage.setItem('vibedesk.workspaceId.v1',workspace);},{workspace,user});
  const read=async()=>(await(await request.get('http://127.0.0.1:8911/api/mods/fund-research-library/context',{headers:{'X-User-Id':user,'X-Workspace-Id':workspace}})).json()).context;
  let release!:()=>void;const gate=new Promise<void>(resolve=>{release=resolve});
  await page.route('**/api/managers/*/career?**',async route=>{
    const period=new URL(route.request().url()).searchParams.get('period');
    if(period==='ytd')await gate;
    if(period==='6m'){await route.fulfill({status:503,json:{detail:'验收曲线失败'}});return;}
    const product={fund_code:'910001.OF',fund_name:'验收任职基金',start_date:'2024-01-01',is_current:true};
    await route.fulfill({json:{status:'available',products:[product],selected_product:product,period,actual_start_date:'2026-01-01',actual_end_date:'2026-03-31',metrics:{total_return:null},curve:[{date:'2026-01-01',fund_return:0,benchmark_return:null},{date:'2026-03-31',fund_return:0.01,benchmark_return:null}],events:[],simulation_used:true}});
  });
  await page.goto(`http://127.0.0.1:5888/?${new URLSearchParams({mod:'fund-research-library',workspace,modSearch:new URLSearchParams({view:'managers',managerId}).toString()})}`);
  const section=async()=>(await read())?.data?.summary?.page?.sections?.['manager-career'];
  await expect.poll(async()=>(await section())?.summary?.result?.period).toBe('tenure');
  const frame=page.frameLocator('iframe'),chart=frame.getByTestId('manager-career-chart');
  expect((await read()).data.summary.page.view).toBe('manager-detail');
  expect((await section()).summary.result.metrics.total_return).toBeNull();
  const slow=page.waitForRequest(r=>r.url().includes('/career?')&&r.url().includes('period=ytd'));
  await chart.getByRole('button',{name:'今年以来',exact:true}).click();await slow;
  await expect.poll(async()=>(await section())?.summary?.result).toBeNull();
  await chart.getByRole('button',{name:'近3月',exact:true}).click();
  await expect.poll(async()=>(await section())?.summary?.result?.period).toBe('3m');release();
  await chart.getByRole('button',{name:'近6月',exact:true}).click();
  await expect.poll(async()=>(await section())?.summary?.status).toBe('error');
  expect((await section()).summary.result).toBeNull();
  await chart.getByRole('button',{name:'自定义',exact:true}).click();
  await chart.getByLabel('任期开始日期').fill('2026-06-30');await chart.getByLabel('任期结束日期').fill('2026-01-01');
  await expect(chart.getByText('开始日期不能晚于结束日期。',{exact:true})).toBeVisible();
  expect((await read()).filters.managerId).toBe(managerId);
  expect((await read()).selection).toEqual({});
});

test('report detail stays embedded, exposes historical evidence and distinguishes read errors',async({page,request},testInfo)=>{
  const workspace=`fund-report-${Date.now()}`,user='fund-acceptance';
  await page.addInitScript(({workspace,user})=>{localStorage.setItem('vibedesk.userId.v1',user);localStorage.setItem('vibedesk.workspaceId.v1',workspace);},{workspace,user});
  let fail=true;
  const fixture={id:'fixture-report',title:'验收研究报告',content:'# 证据边界\n仅供验收，净值日期未核验。',summary:'历史报告样本',reportDate:'2025-01-02',source:'验收隔离响应',targetId:'910001.OF',targetType:'fund',reportType:'fund_analysis',tags:[],keyPoints:[],relatedCodes:[],managerId:null,createdAt:'2025-01-02'};
  await page.route('**/api/reports/fixture-report',route=>route.fulfill(fail?{status:503,json:{error:'验收不可用'}}:{json:fixture}));
  const read=async()=>(await(await request.get('http://127.0.0.1:8911/api/mods/fund-research-library/context',{headers:{'X-User-Id':user,'X-Workspace-Id':workspace}})).json()).context;
  await page.goto(`http://127.0.0.1:5888/?${new URLSearchParams({mod:'fund-research-library',workspace,modSearch:'view=report&reportId=fixture-report'})}`);
  const frame=page.frameLocator('iframe');
  await expect(frame.getByRole('alert').filter({hasText:'报告读取失败'})).toBeVisible();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.status).toBe('error');
  expect((await read()).data.summary.page.report).toBeNull();
  fail=false;await frame.getByRole('button',{name:'重试读取报告',exact:true}).click();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.report?.id).toBe('fixture-report');
  expect((await read()).data.asOf).toBeUndefined();expect((await read()).selection).toEqual({});
  await expect(frame.getByRole('heading',{name:'验收研究报告',exact:true})).toBeVisible();
  await page.screenshot({path:testInfo.outputPath('fund-report.png')});
  await frame.getByRole('link',{name:'返回调研库',exact:true}).click();
  await expect(frame.getByRole('button',{name:/^纪要 /})).toBeVisible();
  await page.goto('http://127.0.0.1:3035/reports/fixture-report');
  await expect(page.getByRole('heading',{name:'验收研究报告',exact:true})).toBeVisible();
  await expect(page.getByRole('link',{name:'返回列表',exact:true})).toHaveAttribute('href','/reports');
});

test('fund workflow navigation switches the Desk panel and keeps fund parameters across reload and back',async({page,request})=>{
  const workspace=`fund-navigation-${Date.now()}`,user='fund-navigation-acceptance';
  await page.addInitScript(({workspace,user})=>{localStorage.setItem('vibedesk.userId.v1',user);localStorage.setItem('vibedesk.workspaceId.v1',workspace);},{workspace,user});
  const read=async(mod:string)=>(await(await request.get(`http://127.0.0.1:8911/api/mods/${mod}/context`,{headers:{'X-User-Id':user,'X-Workspace-Id':workspace}})).json()).context;
  await page.goto(`http://127.0.0.1:5888/?mod=fund-discover&workspace=${workspace}`);
  const frame=page.frameLocator('iframe');
  await expect.poll(async()=>(await read('fund-discover'))?.data?.summary?.contextStatus).toBe('page-data');
  await frame.getByRole('textbox',{name:'搜索基金',exact:true}).fill('000171');
  await frame.getByRole('button',{name:'查找基金',exact:true}).click();
  await frame.getByRole('link',{name:'易方达裕丰回报债券-A',exact:true}).click();
  await expect.poll(async()=>(await read('fund-discover'))?.selection?.symbol).toBe('000171.OF');
  await frame.getByRole('link',{name:'开始 AI 分析',exact:true}).click();
  await expect(page).toHaveURL(/mod=fund-ai-analysis/);
  await expect.poll(async()=>(await read('fund-ai-analysis'))?.selection?.symbol).toBe('000171.OF');
  await frame.getByRole('link',{name:'单独查看 Barra / Brinson 业绩归因',exact:true}).click();
  await expect(page).toHaveURL(/mod=fund-attribution/);
  await expect.poll(async()=>(await read('fund-attribution'))?.filters?.requested?.symbol).toBe('000171.OF');
  await expect(frame.getByRole('textbox',{name:'基金代码',exact:true})).toHaveValue('000171.OF');
  await page.reload();
  await expect(frame.getByRole('link',{name:'返回 AI 分析',exact:true})).toBeVisible();
  expect(new URL(page.url()).searchParams.get('modSearch')).toContain('000171.OF');
  await page.goBack();
  await expect(page).toHaveURL(/mod=fund-ai-analysis/);
  await expect(frame.locator('main[data-vibe-mod-id="fund-ai-analysis"]')).toBeVisible();
  await expect.poll(async()=>(await read('fund-ai-analysis'))?.selection?.symbol).toBe('000171.OF');
});

test('manager research search and detail stay in Desk with real manager evidence',async({page,request},testInfo)=>{
  const workspace=`fund-manager-${Date.now()}`,user='fund-manager-acceptance';
  await page.addInitScript(({workspace,user})=>{localStorage.setItem('vibedesk.userId.v1',user);localStorage.setItem('vibedesk.workspaceId.v1',workspace);},{workspace,user});
  const read=async()=>(await(await request.get('http://127.0.0.1:8911/api/mods/fund-research-library/context',{headers:{'X-User-Id':user,'X-Workspace-Id':workspace}})).json()).context;
  await page.goto(`http://127.0.0.1:5888/?mod=fund-research-library&workspace=${workspace}`);
  const frame=page.frameLocator('iframe');
  await expect.poll(async()=>(await read())?.data?.summary?.page?.status).toBe('ready');
  await frame.getByRole('link',{name:'基金经理研究：任职、在管产品与调研证据 →',exact:true}).click();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.view).toBe('manager-browser');
  const first=(await read()).data.summary.page.rows[0];
  expect(first.id).toBeTruthy();
  expect((await read()).selection).toEqual({});
  await frame.getByPlaceholder('搜索基金经理、基金公司或代表基金').fill(first.name);
  await frame.getByRole('button',{name:'搜索',exact:true}).click();
  await expect.poll(async()=>(await read())?.filters?.search).toBe(first.name);
  await frame.getByRole('link',{name:first.name,exact:true}).first().click();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.view).toBe('manager-detail');
  expect((await read()).filters.managerId).toBe(first.id);
  expect((await read()).selection).toEqual({});
  expect((await read()).data.freshness).toBe('unknown');
  await expect(frame.getByRole('heading',{name:first.name,exact:true})).toBeVisible();
  await page.screenshot({path:testInfo.outputPath('fund-manager-detail.png')});
  await frame.getByRole('link',{name:'复查事件',exact:true}).click();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.view).toBe('review-events');
  await frame.getByRole('link',{name:'返回基金经理',exact:true}).click();
  await expect(frame.getByRole('heading',{name:first.name,exact:true})).toBeVisible();
  await page.reload();
  await expect(frame.getByRole('heading',{name:first.name,exact:true})).toBeVisible();
  await frame.getByRole('link',{name:'返回基金经理',exact:true}).click();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.view).toBe('manager-browser');
  await frame.getByRole('link',{name:'返回调研库',exact:true}).click();
  await expect(frame.getByRole('button',{name:/^纪要 /})).toBeVisible();
});

test('comparison keeps its window and add or remove actions inside Desk',async({page,request},testInfo)=>{
  const workspace=`fund-compare-${Date.now()}`,user='fund-compare-acceptance';
  await page.addInitScript(({workspace,user})=>{localStorage.setItem('vibedesk.userId.v1',user);localStorage.setItem('vibedesk.workspaceId.v1',workspace);},{workspace,user});
  const params=new URLSearchParams({mod:'fund-discover',workspace,modSearch:'view=compare&codes=000171.OF,001199.OF'});
  const read=async()=>(await(await request.get('http://127.0.0.1:8911/api/mods/fund-discover/context',{headers:{'X-User-Id':user,'X-Workspace-Id':workspace}})).json()).context;
  await page.goto(`http://127.0.0.1:5888/?${params}`);
  const frame=page.frameLocator('iframe');
  await expect.poll(async()=>(await read())?.data?.summary?.page?.view).toBe('comparison');
  const rows=(await read()).data.summary.page.rows;
  await expect(frame.getByTestId('aligned-comparison-evidence')).toContainText('仅使用共同日期的复权净值');
  await expect(frame.getByTestId('aligned-comparison-evidence')).toContainText('缺口或稀疏样本不输出日频风险');
  expect(rows).toHaveLength(2);
  expect((await read()).selection).toEqual({});
  await frame.getByRole('button',{name:'近 3 年',exact:true}).click();
  await expect.poll(async()=>(await read())?.filters?.window).toBe('3y');
  const aligned=(await read()).data.summary.page.aligned;
  expect(Object.values(aligned.funds)).toHaveLength(2);
  await expect(frame.getByTestId('trading-calendar-evidence')).toContainText('正常休市不算缺口');
  for(const fund of Object.values(aligned.funds) as Array<{navBasis:string;methodology:{methodology_version:string;calendar_status:string;risk_sampling:string;missing_open_days:number}}>){
    expect(fund.navBasis).toBe('adj_nav');
    expect(fund.methodology.methodology_version).toBe('adjusted_nav_trading_calendar_v3');
    expect(fund.methodology.calendar_status).toBe('verified');
    expect(fund.methodology.risk_sampling).toBe('exchange_open_days');
    expect(fund.methodology.missing_open_days).toBe(0);
  }
  await page.screenshot({path:testInfo.outputPath('fund-comparison.png')});
  await frame.getByRole('button',{name:`移出比较：${rows[1].name}`,exact:true}).first().click();
  await expect.poll(async()=>(await read())?.filters?.codes).toEqual(['000171.OF']);
  expect(new URL(page.url()).searchParams.get('modSearch')).not.toContain('001199');
  expect((await read()).filters.window).toBe('3y');
  await frame.getByRole('textbox',{name:'搜索基金名称或代码',exact:true}).fill('001199');
  await frame.getByRole('button',{name:'搜索基金',exact:true}).click();
  await frame.getByRole('button',{name:'加入比较',exact:true}).click();
  await expect.poll(async()=>(await read())?.filters?.codes).toEqual(['000171.OF','001199.OF']);
  expect((await read()).filters.window).toBe('3y');
  await frame.getByRole('link',{name:'返回基金浏览器',exact:true}).click();
  await expect(frame.getByRole('textbox',{name:'搜索基金',exact:true})).toBeVisible();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.rows).toEqual([]);
});

test('portfolio switching, drafts and recalculation stay bound to the saved composition',async({page,request},testInfo)=>{
  const workspace=`fund-portfolio-${Date.now()}`,user='fund-portfolio-acceptance';
  await page.addInitScript(({workspace,user})=>{localStorage.setItem('vibedesk.userId.v1',user);localStorage.setItem('vibedesk.workspaceId.v1',workspace);},{workspace,user});
  const writes:Array<{url:string;body:any}>=[];
  let releaseOld!:()=>void,releaseSave!:()=>void;
  const oldGate=new Promise<void>(resolve=>{releaseOld=resolve});
  const saveGate=new Promise<void>(resolve=>{releaseSave=resolve});
  let weights=[0.333333,0.333333,0.333334],failAnalysis=false;
  const holdings=()=>weights.map((weight,i)=>({wind_code:`91000${i+1}.OF`,fund_name:`验收成分${i+1}`,weight,weight_source:'custom',note:null,evaluation:null}));
  await page.route('**/api/portfolios**',async route=>{
    const url=new URL(route.request().url()),method=route.request().method(),parts=url.pathname.split('/');
    const id=parts[3],operation=parts[4];
    if(method!=='GET')writes.push({url:url.pathname,body:route.request().postDataJSON()});
    if(!id){await route.fulfill({json:{data:['a','b'].map(id=>({id,name:`验收组合${id}`,objective:null,status:'draft',holding_count:3,total_weight:1}))}});return;}
    if(operation==='weights'&&method==='PUT'){
      await saveGate;weights=route.request().postDataJSON().items.map((item:any)=>item.weight);
      await route.fulfill({json:{status:'ok'}});return;
    }
    if(!operation){await route.fulfill({json:{id,name:`验收组合${id}`,objective:'仅供自动化验收',status:'draft',targets:[],holdings:holdings(),weight_summary:{holding_count:3,weighted_count:3,total_weight:1,is_complete:true}}});return;}
    if(operation==='analysis'){
      if(failAnalysis){await route.fulfill({status:503,json:{detail:'验收穿透不可用'}});return;}
      await route.fulfill({json:{holding_count:3,weights:Object.fromEntries(holdings().map(h=>[h.wind_code,h.weight])),overlap:{status:'insufficient_evidence',reason:'验收缺少共同季度'},style_aggregate:{status:'insufficient_evidence',coverage:0,reason:'验收缺少风格证据'},correlation:{status:'insufficient_evidence',lookback_days:90,reason:'验收缺少净值'},boundary:'验收样本，不是真实组合'}});return;
    }
    if(operation==='backtest'){
      if(id==='a')await oldGate;
      await route.fulfill({json:{status:'available',sample:{days:60,start_date:'2026-01-01',end_date:'2026-03-31',lookback_days:Number(url.searchParams.get('lookback_days'))},metrics:{cumulative_return:0.01,annualized_return:0.02,max_drawdown:-0.03,annualized_volatility:0.04,sample_days:60},curve:[],boundary:`验收组合${id}回测`}});return;
    }
    if(operation==='monitor'){await route.fulfill({json:{status:'available',summary:'验收监控结果',rebalance_needed:false,target_deviations:[],style_drifts:[]}});return;}
    await route.fulfill({status:503,json:{detail:'验收接口失败'}});
  });
  await page.goto(`http://127.0.0.1:5888/?mod=fund-portfolio&workspace=${workspace}`);
  const frame=page.frameLocator('iframe[title="基金组合"]');
  const read=async()=>(await(await request.get('http://127.0.0.1:8911/api/mods/fund-portfolio/context',{headers:{'X-User-Id':user,'X-Workspace-Id':workspace}})).json()).context;
  await expect.poll(async()=>(await read())?.data?.summary?.page?.portfolio?.id).toBe('a');
  expect((await read()).selection).toEqual({});
  const weight=frame.getByRole('textbox',{name:'910001.OF 权重百分比'});
  await expect(weight).toHaveValue('33.3333');
  const oldRequest=page.waitForRequest(r=>r.url().includes('/portfolios/a/backtest'));
  await frame.getByRole('button',{name:'运行回测'}).click();await oldRequest;
  await frame.getByRole('button').filter({hasText:'验收组合b'}).click();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.portfolio?.id).toBe('b');
  const oldResponse=page.waitForResponse(r=>r.url().includes('/portfolios/a/backtest'));
  releaseOld();await oldResponse;
  expect((await read()).data.summary.page.backtest.result).toBeNull();
  await weight.fill('');
  await frame.getByRole('button',{name:'保存权重'}).click();
  await expect(frame.getByRole('alert').filter({hasText:'空白不代表'})).toBeVisible();
  expect(writes).toEqual([]);
  await frame.getByRole('button',{name:'关闭',exact:true}).click();
  await frame.getByRole('button',{name:'配置目标权重',exact:true}).click();
  await frame.getByRole('button',{name:'添加一行',exact:true}).click();
  const targetKey=frame.getByPlaceholder('如 混合型-偏股配置');
  await targetKey.pressSequentially('test-group');
  await expect(targetKey).toHaveValue('test-group');
  await frame.getByRole('button',{name:'保存目标配置',exact:true}).click();
  await expect(frame.getByRole('alert').filter({hasText:'请补齐每一行'})).toBeVisible();
  expect(writes).toEqual([]);
  await frame.getByRole('button',{name:'取消',exact:true}).click();
  await weight.fill('34');
  await expect.poll(async()=>(await read())?.filters?.weightDraftPercent?.['910001.OF']).toBe('34');
  expect((await read()).data.summary.page.portfolio.holdings[0].weight).toBe(0.333333);
  await frame.getByRole('button',{name:'运行回测'}).click();
  await expect.poll(async()=>(await read())?.filters?.backtest?.appliedDays).toBe(365);
  await frame.getByRole('combobox',{name:'回看窗口'}).selectOption('730');
  await expect.poll(async()=>(await read())?.data?.summary?.page?.backtest?.result).toBeNull();
  await frame.getByRole('button',{name:'运行监控'}).click();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.monitor?.status).toBe('ready');
  await frame.getByRole('textbox',{name:'910002.OF 权重百分比'}).fill('33');
  await frame.getByRole('textbox',{name:'910003.OF 权重百分比'}).fill('33');
  await frame.getByRole('button',{name:'保存权重'}).click();
  await expect(frame.getByRole('button').filter({hasText:'验收组合a'})).toBeDisabled();
  failAnalysis=true;releaseSave();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.portfolio?.holdings?.[0]?.weight).toBe(0.34);
  await expect.poll(async()=>(await read())?.data?.summary?.page?.analysis?.status).toBe('error');
  expect((await read()).data.summary.page.monitor.result).toBeNull();
  expect(writes[0].url).toBe('/api/portfolios/b/weights');
  await frame.getByRole('textbox',{name:'当前持仓',exact:true}).fill('910001.OF');
  await frame.getByRole('button',{name:'生成清单'}).click();
  await expect(frame.getByRole('alert').filter({hasText:'未知持仓不能按零计算'})).toBeVisible();
  expect(writes.length).toBe(1);
  await frame.getByRole('textbox',{name:'当前持仓',exact:true}).fill('910001.OF 100');
  await frame.getByRole('button',{name:'生成清单'}).click();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.tradeList?.status).toBe('error');
  expect((await read()).data.summary.page.tradeList.result).toBeNull();
  await expect(frame.getByText('当前持仓与目标组合已一致，无需申赎调整。')).toHaveCount(0);
  await frame.getByRole('heading',{name:'验收组合b',exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:testInfo.outputPath('portfolio-fixture.png')});
});

test('portfolio monitoring discloses missing evidence instead of repeating a legacy all-clear',async({page,request},testInfo)=>{
  const workspace=`fund-coverage-${Date.now()}`,user='fund-coverage-acceptance';
  await page.addInitScript(({workspace,user})=>{localStorage.setItem('vibedesk.userId.v1',user);localStorage.setItem('vibedesk.workspaceId.v1',workspace);},{workspace,user});
  let missingWeights=false;
  const writes:string[]=[];
  const holdings=()=>[1,2,3].map((i)=>({wind_code:`91000${i}.OF`,fund_name:`验收基金${i}`,weight:missingWeights?(i===1?1:null):(i===1?0.4:0.3),weight_source:'custom',note:null,evaluation:null}));
  await page.route('**/api/portfolios**',async route=>{
    const req=route.request(),parts=new URL(req.url()).pathname.split('/'),operation=parts[4];
    if(req.method()!=='GET'){writes.push(req.method());await route.fulfill({status:400,json:{error:'禁止真实写入'}});return;}
    if(!parts[3]){await route.fulfill({json:{data:[{id:'coverage',name:'验收覆盖组合',status:'draft',holding_count:3,total_weight:1}]}});return;}
    if(!operation){await route.fulfill({json:{id:'coverage',name:'验收覆盖组合',status:'draft',targets:[{peer_group_key:'group',target_weight:1}],holdings:holdings(),weight_summary:{holding_count:3,weighted_count:missingWeights?1:3,total_weight:1,is_complete:true}}});return;}
    if(operation==='analysis'){await route.fulfill({json:{holding_count:3,weights:missingWeights?{'910001.OF':1}:Object.fromEntries(holdings().map(h=>[h.wind_code,h.weight])),overlap:{status:'insufficient',reason:'缺少共同披露期'},correlation:{status:'insufficient',reason:'缺少净值'},style_aggregate:{status:'available',coverage:1,factors:[{factor:'BETA',label:'市场 Beta',unit:'multiple',weighted_exposure:0}]},boundary:'验收样本'}});return;}
    if(operation==='monitor'){await route.fulfill({json:{status:'available',summary:'成分风格未见明显漂移。',rebalance_needed:false,target_deviations:[{peer_group_key:'group',target_weight:1,actual_weight:1,deviation:0,needs_rebalance:false}],style_drifts:holdings().map((h,i)=>({...h,status:i===0?'available':'insufficient_evidence',level:i===0?'low':'unavailable',note:i===0?'历史披露期稳定':'缺少两个可比披露期'}))}});return;}
    await route.fulfill({status:404,json:{error:'验收未配置接口'}});
  });
  await page.goto(`http://127.0.0.1:5888/?mod=fund-portfolio&workspace=${workspace}`);
  const frame=page.frameLocator('iframe[title="基金组合"]');
  const read=async()=>(await(await request.get('http://127.0.0.1:8911/api/mods/fund-portfolio/context',{headers:{'X-User-Id':user,'X-Workspace-Id':workspace}})).json()).context?.data?.summary?.page;
  await expect.poll(async()=>(await read())?.evidence?.calculationMatchesSaved).toBe(true);
  await expect(frame.getByRole('row').filter({hasText:'市场 Beta'})).toContainText('0.000');
  await expect(frame.getByRole('row').filter({hasText:'市场 Beta'})).toContainText('未提供');
  await frame.getByRole('button',{name:'运行监控'}).click();
  await expect(frame.getByRole('status')).toContainText('风格已判定 1/3');
  await expect(frame.getByRole('status')).toContainText('证据不足部分不能判断为稳定');
  await expect(frame.getByText('成分风格未见明显漂移。',{exact:true})).toHaveCount(0);
  await expect.poll(async()=>(await read())?.evidence?.assessedWeight).toBe(0.4);
  expect((await read()).monitor.result.summary).not.toContain('未见明显漂移');
  missingWeights=true;
  await frame.getByRole('button',{name:'刷新',exact:true}).click();
  await expect.poll(async()=>(await read())?.evidence?.savedWeightsComplete).toBe(false);
  await frame.getByRole('button',{name:'运行监控'}).click();
  await expect(frame.getByRole('status')).toContainText('暂不能判断配置偏离');
  await expect.poll(async()=>(await read())?.monitor?.result?.rebalance_needed).toBeNull();
  expect((await read()).evidence.assessedWeight).toBeNull();
  expect(writes).toEqual([]);
  await frame.getByRole('heading',{name:'组合监控',exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:testInfo.outputPath('portfolio-coverage.png')});
});

test('portfolio history hides legacy metrics and exposes adjusted aligned intervals',async({page,request},testInfo)=>{
  const workspace=`fund-history-${Date.now()}`,user='fund-history-acceptance';
  await page.addInitScript(({workspace,user})=>{localStorage.setItem('vibedesk.userId.v1',user);localStorage.setItem('vibedesk.workspaceId.v1',workspace);},{workspace,user});
  let verified=false,aligned=false;
  const writes:string[]=[];
  const holdings=[1,2,3].map(i=>({wind_code:`91000${i}.OF`,fund_name:`验收基金${i}`,weight:i===1?0.4:0.3,evaluation:null}));
  await page.route('**/api/portfolios**',async route=>{
    const req=route.request(),parts=new URL(req.url()).pathname.split('/'),operation=parts[4];
    if(req.method()!=='GET'){writes.push(req.method());await route.fulfill({status:400,json:{}});return;}
    if(!parts[3]){await route.fulfill({json:{data:[{id:'history',name:'验收历史组合',status:'draft',holding_count:3,total_weight:1}]}});return;}
    if(!operation){await route.fulfill({json:{id:'history',name:'验收历史组合',status:'draft',targets:[],holdings,weight_summary:{holding_count:3,weighted_count:3,total_weight:1,is_complete:true}}});return;}
    const method=verified?{methodology_version:'portfolio_adj_common_dates_v2',nav_basis:'adj_nav'}:{};
    if(operation==='analysis'){await route.fulfill({json:{weights:Object.fromEntries(holdings.map(h=>[h.wind_code,h.weight])),overlap:{status:'insufficient'},style_aggregate:{status:'insufficient'},correlation:{status:'available',lookback_days:500,...method,pairs:[{fund_a:'910001.OF',fund_b:'910002.OF',correlation:verified?null:0.9876,overlap_days:71,return_intervals:70,start_date:'2026-01-01',end_date:'2026-04-01',status:verified?'zero_variance':'ok'}]}}});return;}
    if(operation==='backtest'){await route.fulfill({json:{status:'available',...method,sample:{days:71,return_intervals:70,start_date:'2026-01-01',end_date:'2026-04-01',omitted_union_dates:1,data_lag_calendar_days:10},metrics:{cumulative_return:-0.2,max_drawdown:-0.2,annualized_return:-0.3,annualized_volatility:null,volatility_note:'缺日，不输出年化波动'},curve:[{date:'2026-01-01',value:1},{date:'2026-04-01',value:0.8}],benchmark:{status:'available',aligned_to_portfolio:aligned,name:'验收基准',metrics:{cumulative_return:0.05},excess_return:-0.25}}});return;}
    await route.fulfill({status:404,json:{}});
  });
  await page.goto(`http://127.0.0.1:5888/?mod=fund-portfolio&workspace=${workspace}`);
  const frame=page.frameLocator('iframe[title="基金组合"]');
  const read=async()=>(await(await request.get('http://127.0.0.1:8911/api/mods/fund-portfolio/context',{headers:{'X-User-Id':user,'X-Workspace-Id':workspace}})).json()).context?.data?.summary?.page;
  await expect.poll(async()=>(await read())?.analysis?.result?.correlation?.status).toBe('unsupported_methodology');
  await expect(frame.getByText('0.9876',{exact:true})).toHaveCount(0);
  await frame.getByRole('button',{name:'运行回测'}).click();
  await expect.poll(async()=>(await read())?.backtest?.result?.status).toBe('unsupported_methodology');
  expect((await read()).backtest.result.metrics).toBeUndefined();
  expect((await read()).backtest.result.curveTail).toBeUndefined();
  verified=true;
  await frame.getByRole('button',{name:'刷新',exact:true}).click();
  await expect(frame.getByText('常数序列，未定义',{exact:true})).toBeVisible();
  await frame.getByRole('button',{name:'运行回测'}).click();
  await expect.poll(async()=>(await read())?.backtest?.result?.benchmark?.status).toBe('unaligned');
  expect((await read()).backtest.result.benchmark.excess_return).toBeUndefined();
  await expect(frame.getByText(/71 个共同净值点 \/ 70 个收益区间/)).toBeVisible();
  await expect(frame.getByText(/缺日，不输出年化波动/)).toBeVisible();
  aligned=true;
  await frame.getByRole('button',{name:'运行回测'}).click();
  await expect.poll(async()=>(await read())?.backtest?.result?.benchmark?.excess_return).toBe(-0.25);
  await expect(frame.getByText('同区间累计收益差',{exact:true})).toBeVisible();
  expect((await read()).backtest.result.curveTail[0].value).toBe(1);
  expect(writes).toEqual([]);
  await frame.getByRole('heading',{name:'基础回测（当前权重回看历史）',exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:testInfo.outputPath('portfolio-history.png')});
});

test('real portfolio uses the dedicated backend and verified history without saving snapshots',async({page,request},testInfo)=>{
  const workspace=`fund-runtime-${Date.now()}`,user='fund-runtime-acceptance';
  await page.addInitScript(({workspace,user})=>{localStorage.setItem('vibedesk.userId.v1',user);localStorage.setItem('vibedesk.workspaceId.v1',workspace);},{workspace,user});
  const health=await(await request.get('http://127.0.0.1:8035/api/health')).json();
  expect(health.database_init_mode).toBe('check');
  expect(health.portfolio_history_methodology).toBe('portfolio_adj_common_dates_v2');
  expect(health.mock_mode).toBe(false);
  const writes:string[]=[];
  await page.route('**/api/portfolios**',async route=>{
    const req=route.request();
    if(req.method()!=='GET'||new URL(req.url()).searchParams.get('save_snapshot')==='true'){
      writes.push(req.method());await route.fulfill({status:400,json:{error:'验收不允许写入'}});return;
    }
    await route.continue();
  });
  await page.goto(`http://127.0.0.1:5888/?mod=fund-portfolio&workspace=${workspace}`);
  const frame=page.frameLocator('iframe[title="基金组合"]');
  const read=async()=>(await(await request.get('http://127.0.0.1:8911/api/mods/fund-portfolio/context',{headers:{'X-User-Id':user,'X-Workspace-Id':workspace}})).json()).context?.data?.summary?.page;
  await expect.poll(async()=>(await read())?.analysis?.result?.correlation?.methodology_version).toBe('portfolio_adj_common_dates_v2');
  await frame.getByRole('button',{name:'运行回测'}).click();
  await expect.poll(async()=>(await read())?.backtest?.status).toBe('ready');
  const result=(await read()).backtest.result;
  expect(result.methodology_version).toBe('portfolio_adj_common_dates_v2');
  expect(result.status).toBe('available');
  expect(result.sample.days).toBeGreaterThanOrEqual(61);
  expect(result.sample.return_intervals).toBe(result.sample.days-1);
  expect(result.metrics.start_date).toBe(result.sample.start_date);
  expect(result.curvePointCount).toBe(result.sample.days);
  await frame.getByRole('button',{name:'运行监控'}).click();
  await expect.poll(async()=>(await read())?.monitor?.status).toBe('ready');
  expect((await read()).monitor.result.drift_coverage.total_count).toBe((await read()).portfolio.holdings.length);
  await expect(frame.getByText(/当前基金服务尚未接入已校验/)).toHaveCount(0);
  expect(writes).toEqual([]);
  await frame.getByRole('heading',{name:'基础回测（当前权重回看历史）',exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:testInfo.outputPath('portfolio-live-runtime.png')});
});

test('portfolio list failure is not presented as an empty account',async({page,request})=>{
  const workspace=`fund-portfolio-error-${Date.now()}`,user='fund-portfolio-error';
  await page.addInitScript(({workspace,user})=>{localStorage.setItem('vibedesk.userId.v1',user);localStorage.setItem('vibedesk.workspaceId.v1',workspace);},{workspace,user});
  await page.route('**/api/portfolios',route=>route.fulfill({status:503,json:{detail:'验收列表不可用'}}));
  await page.goto(`http://127.0.0.1:5888/?mod=fund-portfolio&workspace=${workspace}`);
  const frame=page.frameLocator('iframe[title="基金组合"]');
  await expect(frame.getByRole('alert').filter({hasText:'验收列表不可用'})).toBeVisible();
  await expect(frame.getByText('暂无组合，先创建一个。',{exact:true})).toHaveCount(0);
  const read=async()=>(await(await request.get('http://127.0.0.1:8911/api/mods/fund-portfolio/context',{headers:{'X-User-Id':user,'X-Workspace-Id':workspace}})).json()).context;
  await expect.poll(async()=>(await read())?.data?.summary?.page?.list?.status).toBe('error');
  expect((await read()).data.summary.page.list.count).toBeNull();
});

test('attribution keeps fund and period evidence aligned without converting missing effects to zero',async({page,request})=>{
  const workspace=`fund-attribution-${Date.now()}`,user='fund-attribution-acceptance';
  await page.addInitScript(({workspace,user})=>{localStorage.setItem('vibedesk.userId.v1',user);localStorage.setItem('vibedesk.workspaceId.v1',workspace);},{workspace,user});
  let releaseHistory!:()=>void,releaseRun!:()=>void,failHistory=false;
  const historyGate=new Promise<void>(resolve=>{releaseHistory=resolve});
  const runGate=new Promise<void>(resolve=>{releaseRun=resolve});
  const bundle=(code:string,quarter='2026Q1')=>({status:'partial_evidence',quarter,holding_snapshot_quarter:'2025Q4',benchmark:'000300.SH',
    fund:{wind_code:code,name:`验收归因-${code}`,type:'混合'},barra:{status:'partial_evidence',formal_model_ready:false,holdings_disclosed_weight:0.1,missing_items:['仅覆盖部分披露持仓']},
    brinson:{status:'insufficient_evidence',returns:{fund:0.02,benchmark:null,active:null},effects:[{name:'allocation',label:'配置效应',value:null},{name:'selection',label:'选择效应',value:0}]},
    nav_return_attribution:{status:'insufficient_evidence',missing_items:['净值序列不足']}});
  await page.route('**/api/attribution/fund/**',async route=>{
    const url=new URL(route.request().url()),history=url.pathname.endsWith('/history');
    const code=url.pathname.split('/')[4];
    if(history){
      if(code==='910001.OF')await historyGate;
      if(failHistory){await route.fulfill({status:503,json:{error:'验收历史读取失败'}});return;}
      await route.fulfill({json:{history:[{quarter:'2026Q1',holding_quarter:'2025Q4',benchmark_id:'000300.SH',status:'partial_evidence',active_return:null,updated_at:'2026-04-15',evidence:bundle(code)}]}});
    }else{
      await runGate;
      await route.fulfill({json:bundle(code,url.searchParams.get('quarter')!)});
    }
  });
  await page.goto(`http://127.0.0.1:5888/?mod=fund-attribution&workspace=${workspace}`);
  const frame=page.frameLocator('iframe[title="业绩归因"]');
  const read=async()=>(await(await request.get('http://127.0.0.1:8911/api/mods/fund-attribution/context',{headers:{'X-User-Id':user,'X-Workspace-Id':workspace}})).json()).context;
  await expect.poll(async()=>(await read())?.data?.summary?.contextStatus).toBe('page-data');
  const code=frame.getByRole('textbox',{name:'基金代码'});
  await code.fill('910001.OF');
  const oldRequested=page.waitForRequest(r=>r.url().includes('910001.OF/history'));
  await frame.getByRole('button',{name:'查看历史'}).click();await oldRequested;
  await code.fill('910002.OF');
  await frame.getByRole('button',{name:'查看历史'}).click();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.result?.symbol).toBe('910002.OF');
  const oldResponse=page.waitForResponse(r=>r.url().includes('910001.OF/history'));
  releaseHistory();await oldResponse;
  expect((await read()).selection.symbol).toBe('910002.OF');
  expect((await read()).data.summary.page.result).toMatchObject({origin:'history',savedAt:'2026-04-15',quarter:'2026Q1',holdingQuarter:'2025Q4'});
  expect((await read()).data.summary.page.result.brinson.effects[0].value).toBeNull();
  await expect(frame.getByText('— · 证据缺失',{exact:true})).toBeVisible();
  await frame.getByRole('textbox',{name:'归因季度'}).fill('2026Q2');
  await expect.poll(async()=>(await read())?.data?.summary?.page?.result).toBeNull();
  expect((await read()).filters.applied).toBeNull();
  failHistory=true;
  await frame.getByRole('button',{name:'查看历史'}).click();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.history?.status).toBe('error');
  expect((await read()).data.summary.page.history.count).toBeNull();
  await frame.getByRole('button',{name:'现场运行'}).click();
  await expect(code).toBeDisabled();
  releaseRun();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.status).toBe('ready');
  expect((await read()).data.summary.page.result).toMatchObject({symbol:'910002.OF',quarter:'2026Q2',origin:'calculated',savedAt:null});
  expect((await read()).data.summary.page.history.status).toBe('error');
  expect((await read()).data.freshness).toBe('unknown');
});

test('analysis keeps report identity, submitted questions and historical evidence separate',async({page,request})=>{
  const workspace=`fund-analysis-${Date.now()}`,user='fund-analysis-acceptance';
  await page.addInitScript(({workspace,user})=>{localStorage.setItem('vibedesk.userId.v1',user);localStorage.setItem('vibedesk.workspaceId.v1',workspace);},{workspace,user});
  const funds=[{windCode:'910001.OF',name:'验收基金甲',type:'债券'},{windCode:'910002.OF',name:'验收基金乙',type:'混合'}];
  const requests:unknown[]=[];
  let releaseRun!:()=>void, releaseHistory!:()=>void;
  const runGate=new Promise<void>(resolve=>{releaseRun=resolve});
  const historyGate=new Promise<void>(resolve=>{releaseHistory=resolve});
  await page.route('**/api/fund-browser?**',route=>route.fulfill({json:{data:funds}}));
  await page.route('**/research-snapshot?**',route=>route.fulfill({json:{assessment_summary:{peer_group:'验收同类',score:null,status:'partial',verdict:'当前预览证据'},attribution:{quarter:'2026Q2'}}}));
  await page.route('**/api/analysis**',async route=>{
    const path=new URL(route.request().url()).pathname;
    if(path==='/api/analysis/health'){await route.fulfill({json:{status:'unconfigured',configured:false}});return;}
    if(path==='/api/analysis/evaluate'){
      requests.push(route.request().postDataJSON());await runGate;
      await route.fulfill({json:{id:'fixture-new',report:'验收生成报告：仅供测试',metadata:{mode:'deterministic_evaluation_evidence',evaluation_score:null,multi_period_data_as_of:'2026-08-31'}}});return;
    }
    if(path==='/api/analysis/fixture-old'){
      await historyGate;
      await route.fulfill({json:{id:'fixture-old',targetId:'910002.OF',content:'验收历史报告：旧证据',createdAt:'2026-01-02',metadata:{fund_name:'验收基金乙',fund_type:'混合',question:'历史问题',mode:'llm_evaluation_evidence',multi_period_data_as_of:'2025-12-31'}}});return;
    }
    await route.fulfill({json:{data:[{id:'fixture-old',targetId:'910002.OF',reportType:'fund_evaluation_analysis',content:'验收历史摘要',createdAt:'2026-01-02',metadata:{fund_name:'验收旧报告'}}]}});
  });
  await page.goto(`http://127.0.0.1:5888/?mod=fund-ai-analysis&workspace=${workspace}`);
  const frame=page.frameLocator('iframe[title="AI 分析"]');
  const read=async()=>(await(await request.get('http://127.0.0.1:8911/api/mods/fund-ai-analysis/context',{headers:{'X-User-Id':user,'X-Workspace-Id':workspace}})).json()).context;
  const search=frame.getByPlaceholder('输入基金名称或代码');
  await expect.poll(async()=>(await read())?.data?.summary?.contextStatus).toBe('page-data');
  await search.fill('验收');
  await frame.getByRole('button').filter({hasText:'验收基金甲'}).click();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.evidence?.status).toBe('ready');
  await frame.locator('#analysis-question').fill('原始问题');
  await frame.getByRole('button',{name:'开始分析',exact:true}).click();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.status).toBe('running');
  await expect(search).toBeDisabled();
  await expect(frame.locator('#analysis-question')).toBeDisabled();
  releaseRun();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.result?.symbol).toBe('910001.OF');
  expect(requests).toEqual([{windCode:'910001.OF',question:'原始问题'}]);
  expect((await read()).data.summary.page.result.mode).toBe('deterministic_evaluation_evidence');
  await frame.locator('#analysis-question').fill('尚未提交的问题');
  await expect.poll(async()=>(await read())?.filters?.question).toBe('尚未提交的问题');
  expect((await read()).data.summary.page.result.question).toBe('原始问题');
  await search.fill('另一只');
  await expect.poll(async()=>(await read())?.data?.summary?.page?.result).toBeNull();
  await frame.getByRole('button').filter({hasText:'验收基金乙'}).click();
  await expect.poll(async()=>(await read())?.selection?.symbol).toBe('910002.OF');
  const historyRequested=page.waitForRequest(r=>r.url().endsWith('/api/analysis/fixture-old'));
  await frame.getByRole('button').filter({hasText:'验收旧报告'}).click();await historyRequested;
  await search.fill('重新选择');
  const historyResponse=page.waitForResponse(r=>r.url().endsWith('/api/analysis/fixture-old'));
  releaseHistory();await historyResponse;
  await expect.poll(async()=>(await read())?.data?.summary?.page?.status).toBe('idle');
  expect((await read()).data.summary.page.result).toBeNull();
  await frame.getByRole('button').filter({hasText:'验收旧报告'}).click();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.result?.origin).toBe('history');
  const result=(await read()).data.summary.page.result;
  expect(result).toMatchObject({symbol:'910002.OF',question:'历史问题',createdAt:'2026-01-02',dataAsOf:'2025-12-31'});
  expect((await read()).data.freshness).toBe('unknown');
  expect((await read()).data.asOf).toBeUndefined();
});

test('recommendation switching ignores old queries and preserves missing evidence',async({page,request})=>{
  const workspace=`fund-recommend-${Date.now()}`,user='fund-recommend-acceptance';
  await page.addInitScript(({workspace,user})=>{localStorage.setItem('vibedesk.userId.v1',user);localStorage.setItem('vibedesk.workspaceId.v1',workspace);},{workspace,user});
  let release!:()=>void;
  const gate=new Promise<void>(resolve=>{release=resolve});
  let firstCategory='', fail=false;
  await page.route('**/api/recommendations?**',async route=>{
    const category=new URL(route.request().url()).searchParams.get('category');
    if(category===firstCategory)await gate;
    if(fail){await route.fulfill({status:503,json:{error:'验收候选读取失败'}});return;}
    await route.fulfill({json:{data:[{windCode:category===firstCategory?'910001.OF':'910002.OF',name:`验收候选-${category}`,type:'混合',nav:null,navDate:null,professionalScoring:{status:'partial'},recommendationEvidence:{reasons:['验收入选理由'],risks:['验收证据不足'],dataAsOf:null}}],peerUniverseCount:10,evidenceEligibleCount:1,excludedCount:9,excludedReasonCounts:{required_category_evidence_missing:9},availableStyles:['验收风格']}});
  });
  await page.goto(`http://127.0.0.1:5888/?mod=fund-recommendations&workspace=${workspace}`);
  const frame=page.frameLocator('iframe[title="基金推荐"]');
  const read=async()=>(await(await request.get('http://127.0.0.1:8911/api/mods/fund-recommendations/context',{headers:{'X-User-Id':user,'X-Workspace-Id':workspace}})).json()).context;
  const categories=frame.getByRole('combobox').first();
  await expect(categories).toBeVisible();
  const values=await categories.locator('option').evaluateAll(options=>options.map(option=>(option as HTMLOptionElement).value).filter(Boolean));
  expect(values.length).toBeGreaterThan(1);firstCategory=values[0];
  const slow=page.waitForRequest(r=>r.url().includes('/api/recommendations?')&&new URL(r.url()).searchParams.get('category')===firstCategory);
  await categories.selectOption(firstCategory);await slow;
  await categories.selectOption(values[1]);
  await expect.poll(async()=>(await read())?.data?.summary?.page?.rows?.[0]?.symbol).toBe('910002.OF');
  const oldResponse=page.waitForResponse(r=>r.url().includes('/api/recommendations?')&&new URL(r.url()).searchParams.get('category')===firstCategory);
  release();await oldResponse;
  await expect(frame.getByRole('link',{name:`验收候选-${values[1]}`,exact:true})).toBeVisible();
  expect((await read()).filters.applied.category).toBe(values[1]);
  expect((await read()).data.summary.page.rows[0].navDate).toBeNull();
  expect((await read()).data.summary.page.exclusionReasons.required_category_evidence_missing).toBe(9);
  fail=true;
  await frame.getByRole('combobox').nth(1).selectOption('验收风格');
  await expect.poll(async()=>(await read())?.data?.summary?.page?.status).toBe('error');
  expect((await read()).data.summary.page.counts).toBeNull();
  expect((await read()).data.summary.page.rows).toEqual([]);
  await expect(frame.getByRole('alert').filter({hasText:'候选读取失败'})).toBeVisible();
  await categories.selectOption('');
  await expect.poll(async()=>(await read())?.data?.summary?.page?.status).toBe('idle');
  expect((await read()).filters.applied).toBeNull();
});

// Validate a bundled frontend without changing the user's published registry or stopping standalone services.
test.beforeEach(async({page})=>{
  const origin=process.env.FUND_E2E_WEB_ORIGIN;
  if(!origin)return;
  await page.route('**/api/mods',async route=>{
    const response=await route.fetch();
    const rows=await response.json();
    for(const row of rows)if(row.manifest.navigation?.directory?.id==='professional-fund-research-suite'){
      const url=new URL(row.manifest.entry.url);
      row.manifest.entry.url=new URL(url.pathname+url.search,origin).href;
    }
    await route.fulfill({response,json:rows});
  });
});

test('fund list publishes applied filters, visible results, missing dates and failed or out-of-order queries',async({page,request})=>{
  const workspace=`fund-context-${Date.now()}`,user='fund-context-acceptance';
  await page.addInitScript(({workspace,user})=>{localStorage.setItem('vibedesk.userId.v1',user);localStorage.setItem('vibedesk.workspaceId.v1',workspace);},{workspace,user});
  await page.goto(`http://127.0.0.1:5888/?mod=fund-discover&workspace=${workspace}`);
  const frame=page.frameLocator('iframe[title="找基金"]');
  const read=async()=>(await(await request.get('http://127.0.0.1:8911/api/mods/fund-discover/context',{headers:{'X-User-Id':user,'X-Workspace-Id':workspace}})).json()).context;
  await expect.poll(async()=>(await read())?.data?.summary?.contextStatus).toBe('page-data');
  expect((await read()).data.summary.page.rows).toEqual([]);
  expect((await read()).data.asOf).toBeUndefined();
  let release!:()=>void;
  const gate=new Promise<void>(resolve=>{release=resolve});
  await page.route('**/api/fund-browser?**',async route=>{
    const search=new URL(route.request().url()).searchParams.get('search');
    if(search==='失败'){await route.fulfill({status:503,json:{error:'验收模拟查询失败'}});return;}
    if(search==='较慢')await gate;
    await route.fulfill({json:{data:[{id:search,windCode:search==='较慢'?'910002.OF':'910001.OF',name:`验收模拟基金-${search}`,type:'混合',
      nav:null,navDate:null,totalAsset:null,performanceData:{},riskMetrics:{},professionalScoring:{status:'insufficient_evidence',missing_data:['缺净值日期']}}],
      pagination:{total:1},availability:'all',source:'acceptance-fixture',selectionContext:{},styleTagCatalog:{}}});
  });
  const search=frame.getByRole('textbox',{name:'搜索基金',exact:true});
  await search.fill('首查');await frame.getByRole('button',{name:'查找基金',exact:true}).click();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.rows?.[0]?.symbol).toBe('910001.OF');
  await search.fill('尚未应用');
  await expect.poll(async()=>(await read())?.filters?.form?.search).toBe('尚未应用');
  expect((await read()).filters.applied.search).toBe('首查');
  expect((await read()).data.summary.page.rows[0].nav).toBeNull();
  expect((await read()).data.summary.page.rows[0].navDate).toBeNull();
  expect((await read()).data.freshness).toBe('unknown');
  await frame.getByRole('button',{name:'数据表格',exact:true}).click();
  await expect.poll(async()=>(await read())?.filters?.viewMode).toBe('table');
  await search.fill('失败');await frame.getByRole('button',{name:'查找基金',exact:true}).click();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.status).toBe('error');
  expect((await read()).filters.applied.search).toBe('首查');
  expect((await read()).data.summary.page.resultsArePrevious).toBe(true);
  // Category changes remain available while a search is in flight.
  const slowRequested=page.waitForRequest(r=>r.url().includes('/api/fund-browser?')&&new URL(r.url()).searchParams.get('search')==='较慢');
  await search.fill('较慢');await search.press('Enter');await slowRequested;
  await expect.poll(async()=>(await read())?.data?.summary?.page?.status).toBe('loading');
  const fastRequested=page.waitForRequest(r=>r.url().includes('/api/fund-browser?')&&new URL(r.url()).searchParams.get('search')==='后查');
  await search.fill('后查');
  const category=frame.getByRole('combobox',{name:'专业同类组',exact:true});
  const categoryValue=await category.locator('option').filter({hasText:'混合型-偏股配置'}).getAttribute('value');
  await category.selectOption(categoryValue!);await fastRequested;
  await expect.poll(async()=>(await read())?.filters?.applied?.search).toBe('后查');
  const slowResponse=page.waitForResponse(r=>r.url().includes('/api/fund-browser?')&&new URL(r.url()).searchParams.get('search')==='较慢');
  release();await slowResponse;
  await expect(frame.getByText('验收模拟基金-后查',{exact:true})).toBeVisible();
  expect((await read()).data.summary.page.rows[0].symbol).toBe('910001.OF');
});

test('real fund detail stays embedded and sends the selected evaluation window to Desk',async({page,request},testInfo)=>{
  const workspace=`fund-detail-${Date.now()}`,user='fund-detail-acceptance';
  await page.addInitScript(({workspace,user})=>{localStorage.setItem('vibedesk.userId.v1',user);localStorage.setItem('vibedesk.workspaceId.v1',workspace);},{workspace,user});
  await page.goto(`http://127.0.0.1:5888/?mod=fund-discover&workspace=${workspace}`);
  const frame=page.frameLocator('iframe[title="找基金"]');
  const read=async()=>(await(await request.get('http://127.0.0.1:8911/api/mods/fund-discover/context',{headers:{'X-User-Id':user,'X-Workspace-Id':workspace}})).json()).context;
  await expect.poll(async()=>(await read())?.data?.summary?.contextStatus).toBe('page-data');
  await frame.getByRole('textbox',{name:'搜索基金',exact:true}).fill('000171');
  await frame.getByRole('button',{name:'查找基金',exact:true}).click();
  await frame.getByRole('link',{name:'易方达裕丰回报债券-A',exact:true}).click();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.fund?.symbol).toBe('000171.OF');
  expect((await read()).selection.symbol).toBe('000171.OF');
  expect(page.frames().some(f=>new URL(f.url()).pathname==='/mod/fund-research/discover'&&new URL(f.url()).searchParams.get('symbol')==='000171.OF')).toBe(true);
  expect((await read()).data.freshness).toBe('unknown');
  expect((await read()).data.asOf).toBeUndefined();
  const heading=frame.getByRole('heading',{name:'易方达裕丰回报债券-A',exact:true});
  expect((await read()).data.summary.page.derivedSeries.observations).toBeGreaterThan(0);
  expect((await read()).data.summary.page.derivedSeries.historyEnd).toBeTruthy();
  await expect(frame.getByRole('heading',{name:'回撤轨迹与滚动收益',exact:true})).toBeVisible();
  const darkEmbedded=await heading.evaluate(el=>el.ownerDocument.documentElement.matches('html.vibedesk-embedded[data-theme="dark"]'));
  if(darkEmbedded)await expect.poll(()=>heading.evaluate(el=>getComputedStyle(el).color===getComputedStyle(el.closest('main')!).color)).toBe(true);
  await frame.getByRole('button',{name:'近 3 年',exact:true}).click();
  await expect.poll(async()=>(await read())?.filters?.window).toBe('3y');
  expect((await read()).data.summary.page.evaluation.window).toBe('3y');
  await frame.getByRole('link',{name:'返回找基金',exact:true}).scrollIntoViewIfNeeded();
  await page.screenshot({path:testInfo.outputPath('real-fund-detail.png')});
  await frame.getByRole('link',{name:'返回找基金',exact:true}).click();
  await expect(frame.getByRole('textbox',{name:'搜索基金',exact:true})).toBeVisible();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.rows).toEqual([]);
  expect((await read()).selection).toEqual({});
  expect(page.frames().some(f=>new URL(f.url()).pathname==='/mod/fund-research/discover'&&!new URL(f.url()).searchParams.has('symbol'))).toBe(true);
});

test('standalone fund navigation keeps its original routes',async({page,request})=>{
  const registry=await(await request.get('http://127.0.0.1:8911/api/mods')).json();
  const origin=process.env.FUND_E2E_WEB_ORIGIN || new URL(registry.find((row:{moduleId:string})=>row.moduleId==='fund-discover').manifest.entry.url).origin;
  await page.goto(`${origin}/discover`);
  await page.getByRole('textbox',{name:'搜索基金',exact:true}).fill('000171');
  await page.getByRole('button',{name:'查找基金',exact:true}).click();
  await page.getByRole('link',{name:'易方达裕丰回报债券-A',exact:true}).click();
  await expect(page).toHaveURL(/\/funds\/000171\.OF$/);
  await expect(page.getByRole('button',{name:'近 3 年',exact:true})).toBeVisible();
  await page.getByRole('link',{name:'返回找基金',exact:true}).click();
  await expect(page).toHaveURL(`${origin}/discover`);
  await expect(page.getByRole('textbox',{name:'搜索基金',exact:true})).toBeVisible();
});

test('all six fund workspaces load and identify their evidence boundary',async({page,request},testInfo)=>{
  const workspace=`fund-suite-${Date.now()}`,user='fund-suite-acceptance';
  await page.addInitScript(({workspace,user})=>{localStorage.setItem('vibedesk.userId.v1',user);localStorage.setItem('vibedesk.workspaceId.v1',workspace);},{workspace,user});
  for(const moduleId of ['fund-discover','fund-research-library','fund-ai-analysis','fund-recommendations','fund-attribution','fund-portfolio']){
    await page.goto(`http://127.0.0.1:5888/?mod=${moduleId}&workspace=${workspace}`);
    await expect(page.frameLocator('iframe').locator(`main[data-vibe-mod-id="${moduleId}"]`)).toBeVisible();
    const read=async()=>(await(await request.get(`http://127.0.0.1:8911/api/mods/${moduleId}/context`,{headers:{'X-User-Id':user,'X-Workspace-Id':workspace}})).json()).context;
    await expect.poll(async()=>(await read())?.view?.id).toBe(moduleId);
    const context=await read();
    expect(context.data.freshness).toBe('unknown');
    expect(context.data.asOf).toBeUndefined();
    if(moduleId==='fund-research-library'){
      await expect.poll(async()=>(await read())?.data?.summary?.page?.status).toBe('ready');
      await page.screenshot({path:testInfo.outputPath('research-library.png')});
    }
    if(moduleId==='fund-recommendations'){
      const frame=page.frameLocator('iframe');
      await frame.getByRole('combobox').first().selectOption('债券型-含权益配置');
      await expect.poll(async()=>(await read())?.data?.summary?.page?.status).toBe('ready');
      const actual=(await read()).data.summary.page;
      expect(actual.candidateCount).toBeGreaterThan(0);
      expect(actual.counts.peerUniverseCount).toBeGreaterThanOrEqual(actual.candidateCount);
      await expect(frame.getByRole('link',{name:actual.rows[0].name,exact:true}).first()).toBeVisible();
      await frame.getByRole('link',{name:actual.rows[0].name,exact:true}).first().scrollIntoViewIfNeeded();
      await page.screenshot({path:testInfo.outputPath('real-fund-recommendations.png')});
    }
    if(moduleId==='fund-ai-analysis')await page.screenshot({path:testInfo.outputPath('fund-ai-analysis.png')});
    if(moduleId==='fund-attribution')await page.screenshot({path:testInfo.outputPath('fund-attribution.png')});
    await expect.poll(async()=>(await read())?.data?.summary?.contextStatus).toBe('page-data');
    if(moduleId==='fund-portfolio'){
      await expect.poll(async()=>(await read())?.data?.summary?.page?.list?.status).toBe('ready');
      if((await read()).data.summary.page.list.count > 0) {
        await expect.poll(async()=>(await read())?.data?.summary?.page?.status).toBe('ready');
        const current=(await read()).data.summary.page.portfolio;
        expect(current.id).toBeTruthy();
        await expect(page.frameLocator('iframe').getByRole('heading',{name:current.name,exact:true})).toBeVisible();
      }
      await page.screenshot({path:testInfo.outputPath('fund-portfolio.png')});
    }
  }
});

test('research library shares visible evidence and never revives a closed detail',async({page,request})=>{
  const workspace=`fund-research-${Date.now()}`,user='fund-research-acceptance';
  await page.addInitScript(({workspace,user})=>{localStorage.setItem('vibedesk.userId.v1',user);localStorage.setItem('vibedesk.workspaceId.v1',workspace);},{workspace,user});
  const memos=[
    {id:'fixture-a',title:'验收纪要甲',manager_name:'经理甲',report_date:'2026-06-30',report_date_precision:'quarter',report_date_source:'filename',summary:'经理观点，不代表产品持仓',review_status:'pending',viewpoint_topics:['债市'],research_domains:['fixed_income']},
    {id:'fixture-b',title:'验收纪要乙',manager_name:'经理乙',report_date:null,summary:'日期未核验',llm_extraction_status:'unavailable',viewpoint_topics:['科技'],research_domains:['equity']},
  ];
  const writes:string[]=[];
  await page.route('**/api/research-folders**',async route=>{
    if(route.request().method()!=='GET'){writes.push(route.request().url());await route.fulfill({status:405});return;}
    const reviews=new URL(route.request().url()).pathname.endsWith('/reviews');
    await route.fulfill({json:{data:reviews?[{id:'candidate',report_id:'fixture-a',report_title:'验收纪要甲',kind:'style_label',value:'待确认风格',confidence:0.95,scope:'manager',extraction_source:'llm',source_ref:{relative_path:'fixture.txt',excerpt:'仅用于验收的来源摘录'}}]:[]}});
  });
  let release!:()=>void;
  const gate=new Promise<void>(resolve=>{release=resolve});
  await page.route('**/api/research-memos**',async route=>{
    if(route.request().method()!=='GET'){writes.push(route.request().url());await route.fulfill({status:405});return;}
    const path=new URL(route.request().url()).pathname;
    if(path.endsWith('/fixture-a')){await gate;await route.fulfill({json:{...memos[0],content:'验收原文：经理观点不能当作基金持仓。'}});return;}
    if(path.endsWith('/fixture-b')){await route.fulfill({status:503,json:{error:'验收模拟原文读取失败'}});return;}
    await route.fulfill({json:{data:memos,total:2}});
  });
  await page.goto(`http://127.0.0.1:5888/?mod=fund-research-library&workspace=${workspace}`);
  const frame=page.frameLocator('iframe[title="调研库"]');
  const read=async()=>(await(await request.get('http://127.0.0.1:8911/api/mods/fund-research-library/context',{headers:{'X-User-Id':user,'X-Workspace-Id':workspace}})).json()).context;
  await expect.poll(async()=>(await read())?.data?.summary?.page?.status).toBe('ready');
  expect((await read()).data.summary.page.folder).toBeNull();
  expect((await read()).data.summary.page.managers.total).toBe(2);
  expect((await read()).selection).toEqual({});
  await frame.getByRole('button',{name:'纪要 2',exact:true}).click();
  const search=frame.getByPlaceholder('搜索经理、基金公司、标题或关键词');
  await search.fill('经理乙');
  await expect.poll(async()=>(await read())?.data?.summary?.page?.memos?.rows?.map((m:{id:string})=>m.id)).toEqual(['fixture-b']);
  expect((await read()).data.summary.page.memos.rows[0].reportDate).toBeNull();
  expect((await read()).data.summary.page.managers).toBeNull();
  await search.fill('');
  const slowRequest=page.waitForRequest(r=>r.url().endsWith('/api/research-memos/fixture-a'));
  await frame.getByRole('button').filter({hasText:'验收纪要甲'}).click();await slowRequest;
  await expect.poll(async()=>(await read())?.data?.summary?.page?.selectedMemo?.detailStatus).toBe('loading');
  await frame.getByRole('button',{name:'关闭详情',exact:true}).click();
  const response=page.waitForResponse(r=>r.url().endsWith('/api/research-memos/fixture-a'));
  release();await response;
  await expect(frame.getByRole('dialog',{name:'调研纪要详情'})).toBeHidden();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.selectedMemo).toBeNull();
  await frame.getByRole('button').filter({hasText:'验收纪要甲'}).click();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.selectedMemo?.contentExcerpt).toContain('经理观点不能当作基金持仓');
  expect((await read()).data.summary.page.selectedMemo.datePrecision).toBe('quarter');
  expect((await read()).data.summary.page.selectedMemo.reviewStatus).toBe('pending');
  await frame.getByRole('button',{name:'关闭详情',exact:true}).click();
  await frame.getByRole('button').filter({hasText:'验收纪要乙'}).click();
  await expect(frame.getByRole('dialog',{name:'调研纪要详情'}).getByRole('alert')).toContainText('验收模拟原文读取失败');
  await expect.poll(async()=>(await read())?.data?.summary?.page?.selectedMemo?.detailStatus).toBe('error');
  expect((await read()).data.summary.page.selectedMemo.contentExcerpt).toBeNull();
  await frame.getByRole('button',{name:'关闭详情',exact:true}).click();
  await frame.getByRole('button',{name:'待确认 1',exact:true}).click();
  await frame.getByRole('button',{name:'分类与风格 1',exact:true}).click();
  await expect.poll(async()=>(await read())?.data?.summary?.page?.reviews?.rows?.[0]?.scope).toBe('manager');
  expect((await read()).data.summary.page.reviews.status).toBe('pending-human-review');
  expect((await read()).data.freshness).toBe('unknown');
  expect((await read()).data.asOf).toBeUndefined();
  expect(writes).toEqual([]);
});
