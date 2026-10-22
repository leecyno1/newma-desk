// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { blankEarningsWorkbook, emptyEarningsWorkspace, hydrateEarningsWorkspace, persistEarningsWorkspace } from '@/lib/earningsWorkbench';
import { EarningsWorkbench } from '@/pages/EarningsWorkbench';
import { api, type Financials, type EarningsPdfImport } from '@/lib/api';
import * as researchData from '@/lib/researchData';

const bridge = vi.hoisted(() => ({ config: null as any, embedded: false, listeners: new Set<() => void>(), context: undefined as any, action: undefined as any }));
vi.mock('@/lib/vibedesk', () => ({
  getVibeDeskConfig: () => bridge.config, waitForVibeDeskConfig: async () => bridge.config,
  get isVibeDeskEmbedded() { return bridge.embedded; },
  subscribeVibeDeskConfig: (fn: () => void) => { bridge.listeners.add(fn); return () => bridge.listeners.delete(fn); },
  subscribeVibeDeskEvent: () => () => {},
  registerVibeDeskUiActionHandler: (fn: any) => { bridge.action = fn; return () => { bridge.action = undefined; }; },
  registerVibeDeskContextProvider: (fn: any) => { bridge.context = fn; return () => {}; },
  publishVibeDeskContext: vi.fn(), requestVibeDeskAgent: vi.fn(),
}));
const key = 'newma-desk.earnings-workbench.v1';
let storage: Map<string, string>;
function workspace(name = '已存合成公司') {
  const workbook = blankEarningsWorkbook();
  return { ...emptyEarningsWorkspace(), workbooks: [{ ...workbook, id: 'e1',
    fiscalPeriod: { ...workbook.fiscalPeriod, label: '2025 年报', periodEnd: '2025-12-31', basis: 'annual' as const },
    security: { market: 'CN', symbol: 'TEST', name, currency: 'CNY' } }] };
}
function desk(workspaceId = 'a') {
  bridge.embedded = true;
  bridge.config = { moduleId: 'earnings-workbench', apiOrigin: 'http://desk.test', storageGateway: 'http://desk.test/storage', userId: 'test-user', workspaceId, instanceId: workspaceId, accessToken: 'test-only', permissions: ['storage.read', 'storage.write'] };
}
function response(value = workspace(), revision = 7) { return new Response(JSON.stringify({ value, revision })); }
beforeEach(() => {
  bridge.config = null; bridge.embedded = false; bridge.listeners.clear(); bridge.context = undefined;
  storage = new Map();
  vi.stubGlobal('localStorage', { getItem: (k: string) => storage.get(k) ?? null, setItem: (k: string, v: string) => storage.set(k, v) });
  vi.stubGlobal('fetch', vi.fn());
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; };
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe('财报持久化', () => {
  it('Agent等待授权取数完成，候选先显示再回执，不采用或保存', async () => {
    desk(); bridge.config.permissions.push('market.read');
    const source = workspace(); source.workbooks[0].security.symbol = '600519';
    let finish!: (value: Response) => void;
    vi.mocked(fetch).mockResolvedValueOnce(response(source)).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    render(<EarningsWorkbench/>); await screen.findByDisplayValue('已存合成公司');
    expect(bridge.context().actions.find((row: any) => row.id === 'earnings.refresh-evidence').available).toBe(true);
    await expect(bridge.action('earnings.refresh-evidence', { code: 'OTHER' })).rejects.toThrow('不支持');
    let request!: Promise<any>;
    act(() => { request = bridge.action('earnings.refresh-evidence', {}); });
    expect(bridge.context().tasks[0].status).toBe('running');
    await expect(bridge.action('earnings.refresh-evidence', {})).rejects.toThrow('完成读取');
    let result: any;
    await act(async () => { finish(new Response(JSON.stringify({ data: { basis: 'annual', period: '2025-12-31', revenue: '0亿元', net_profit: null } }))); result = await request; });
    expect(result).toMatchObject({ status: 'pending-review', adopted: false, saved: false });
    expect(bridge.context().data.summary.candidateEvidence.rows[0].after).toBe(0);
    expect(bridge.context().data.summary.metrics[0].reported).toBeNull();
    expect(bridge.context().tasks).toEqual([]);
    expect(screen.getByRole('table', { name: '刷新候选指标' })).toBeTruthy();
    expect(fetch).toHaveBeenCalledTimes(2); expect(storage.size).toBe(0);
  });

  it('取数失败或错期返回失败回执并保留底稿，不制造候选', async () => {
    desk(); bridge.config.permissions.push('market.read');
    vi.mocked(fetch).mockResolvedValueOnce(response()).mockResolvedValueOnce(new Response(null, { status: 502 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: { basis: 'annual', period: '2024-12-31', revenue: '123亿元' } })));
    render(<EarningsWorkbench/>); await screen.findByDisplayValue('已存合成公司');
    await act(async () => { await expect(bridge.action('earnings.refresh-evidence', {})).rejects.toThrow('HTTP 502'); });
    await act(async () => { await expect(bridge.action('earnings.refresh-evidence', {})).rejects.toThrow('未跨期覆盖'); });
    expect(bridge.context().data.summary.pendingEvidenceReview).toBe(false);
    expect(bridge.context().data.summary.metrics[0].reported).toBeNull();
    expect(bridge.context().tasks).toEqual([]);
    expect(fetch).toHaveBeenCalledTimes(3);
  });

  it('只读Agent核对落到页面与Context，编辑后失效，拒绝额外输入与无权限', async () => {
    desk(); bridge.config.permissions = ['storage.read'];
    vi.mocked(fetch).mockResolvedValueOnce(response());
    const page = render(<EarningsWorkbench/>);
    await screen.findByDisplayValue('已存合成公司');
    expect(bridge.context().actions.find((row: any) => row.id === 'earnings.compare').available).toBe(true);
    let result: any;
    await act(async () => { result = await bridge.action('earnings.compare', {}); });
    expect(screen.getByText(result.summary)).toBeTruthy();
    expect(bridge.context().data.summary.currentAnalysis).toEqual(result);
    expect(fetch).toHaveBeenCalledTimes(1);
    fireEvent.change(screen.getByDisplayValue('已存合成公司'), { target: { value: '修改名称' } });
    expect(bridge.context().data.summary.currentAnalysis).toBeNull();
    expect(screen.getByText(/上次核对结果已失效/)).toBeTruthy();
    await expect(bridge.action('earnings.compare', { symbol: 'OTHER' })).rejects.toThrow('不支持');
    await expect(bridge.action('earnings.revise-estimates', {})).rejects.toThrow('不支持');
    bridge.config.permissions = [];
    await expect(bridge.action('earnings.compare', {})).rejects.toThrow('授权');
    page.unmount(); expect(bridge.action).toBeUndefined();
  });

  it('原生按钮可运行同一核对，档案未读取前拒绝Agent执行', async () => {
    storage.set(key, JSON.stringify(workspace()));
    render(<EarningsWorkbench/>);
    await screen.findByDisplayValue('已存合成公司');
    fireEvent.click(screen.getByRole('button', { name: '核对实际与预期差' }));
    expect(bridge.context().data.summary.currentAnalysis.actionId).toBe('earnings.compare');
    cleanup();
    desk(); vi.mocked(fetch).mockReturnValue(new Promise(() => {}));
    render(<EarningsWorkbench/>);
    await expect(bridge.action('earnings.compare', {})).rejects.toThrow('完成读取');
  });

  it('按读取时版本提交，409不重试也不写本机', async () => {
    desk(); vi.mocked(fetch).mockResolvedValueOnce(response()).mockResolvedValue(new Response(null, { status: 409 }));
    const session = await hydrateEarningsWorkspace();
    await expect(persistEarningsWorkspace(workspace('修改'), session)).rejects.toThrow('保存冲突');
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(JSON.parse(String(vi.mocked(fetch).mock.calls[1][1]?.body)).expectedRevision).toBe(7);
    expect(storage.size).toBe(0);
  });
  it('原生回读、旧窗口冲突，损坏档案不当空库', async () => {
    const first = await hydrateEarningsWorkspace();
    expect((await persistEarningsWorkspace(workspace(), first)).mode).toBe('local');
    expect((await hydrateEarningsWorkspace()).workspace.workbooks[0].security.name).toBe('已存合成公司');
    await expect(persistEarningsWorkspace(workspace('旧稿'), first)).rejects.toThrow('保存冲突');
    storage.set(key, '{broken');
    await expect(hydrateEarningsWorkspace()).rejects.toThrow('读取失败');
    const invalid = workspace(); invalid.workbooks.push(invalid.workbooks[0]);
    storage.set(key, JSON.stringify(invalid));
    await expect(hydrateEarningsWorkspace()).rejects.toThrow('不完整');
  });
  it('Desk空库、故障和无权不借用本机旧缓存', async () => {
    storage.set(key, JSON.stringify(workspace('旧私人缓存'))); desk();
    vi.mocked(fetch).mockResolvedValueOnce(new Response(null, {status:404})).mockResolvedValueOnce(new Response(null, {status:503}));
    expect((await hydrateEarningsWorkspace()).workspace.workbooks).toEqual([]);
    await expect(hydrateEarningsWorkspace()).rejects.toThrow('未使用本机');
    bridge.config.moduleId='valuation-workbench';
    await expect(hydrateEarningsWorkspace()).rejects.toThrow('尚未连接');
    bridge.config=null;
    await expect(hydrateEarningsWorkspace()).rejects.toThrow('尚未连接');
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(storage.get(key)).toContain('旧私人缓存');
  });
  it('采用真实回执，错误修订和不完整指标不算成功', async () => {
    desk(); vi.mocked(fetch).mockResolvedValueOnce(response()).mockResolvedValueOnce(response(workspace('回执公司'),8));
    const session=await hydrateEarningsWorkspace();
    const saved=await persistEarningsWorkspace(workspace('提交公司'),session);
    expect(saved.workspace.workbooks[0].security.name).toBe('回执公司');
    expect(saved.revision).toBe(8);
    vi.mocked(fetch).mockResolvedValueOnce(response(workspace(),8));
    await expect(persistEarningsWorkspace(workspace(),saved)).rejects.toThrow('修订号异常');
    const broken=workspace();broken.workbooks[0].metrics.pop();
    await expect(persistEarningsWorkspace(broken,saved)).rejects.toThrow('不完整');
  });
  it('只读、取消及解析回执时切身份均拒绝继续', async () => {
    desk();bridge.config.permissions=['storage.read'];
    vi.mocked(fetch).mockImplementation(async()=>response());
    const readonly=await hydrateEarningsWorkspace();
    await expect(persistEarningsWorkspace(workspace(),readonly)).rejects.toThrow('没有保存权限');
    desk();const session=await hydrateEarningsWorkspace();
    const controller=new AbortController();controller.abort();
    await expect(persistEarningsWorkspace(workspace(),session,controller.signal)).rejects.toThrow();
    let finish!:(value:unknown)=>void;
    vi.mocked(fetch).mockResolvedValueOnce({ok:true,status:200,json:()=>new Promise(resolve=>{finish=resolve})} as Response);
    const save=persistEarningsWorkspace(workspace(),session);const rejected=expect(save).rejects.toThrow('工作区');
    await waitFor(()=>expect(finish).toBeTypeOf('function'));
    desk('b');finish({value:workspace(),revision:8});await rejected;
    expect(storage.size).toBe(0);
  });
  it('失败保留草稿列表，导出原稿，重读先确认', async () => {
    desk();vi.mocked(fetch).mockResolvedValueOnce(response()).mockResolvedValueOnce(new Response(null,{status:409})).mockResolvedValueOnce(response(workspace('其他窗口新版'),8));
    render(<EarningsWorkbench/>);await screen.findByDisplayValue('已存合成公司');
    fireEvent.change(screen.getByLabelText('公司名称'),{target:{value:'我的未存草稿'}});
    fireEvent.click(screen.getByRole('button',{name:'保存',exact:true}));
    await screen.findByRole('alert');
    expect((screen.getByLabelText('公司名称') as HTMLInputElement).value).toBe('我的未存草稿');
    expect(screen.getByRole('button',{name:/已存合成公司 CN:TEST/})).toBeTruthy();
    expect((screen.getByRole('button',{name:'保存',exact:true}) as HTMLButtonElement).disabled).toBe(true);
    expect(bridge.context().filters.unsavedChanges).toBe(true);
    expect(bridge.context().data.summary.storage.status).toBe('error');
    const backup=JSON.parse(decodeURIComponent(screen.getByRole('link',{name:'导出当前草稿'}).getAttribute('href')!.split(',')[1]));
    expect(backup.workbook.security.name).toBe('我的未存草稿');
    fireEvent.click(screen.getByRole('button',{name:'重新读取档案'}));fireEvent.click(screen.getByRole('button',{name:'取消操作'}));
    expect(fetch).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole('button',{name:'重新读取档案'}));fireEvent.click(screen.getByRole('button',{name:'确认继续'}));
    await screen.findByDisplayValue('其他窗口新版');
    expect(bridge.context().filters.unsavedChanges).toBe(false);
  });
  it('读取保存锁定编辑，主题稳定，保存后显示真实版本', async () => {
    desk();let finish!:(r:Response)=>void;
    vi.mocked(fetch).mockResolvedValueOnce(response()).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}));
    render(<EarningsWorkbench/>);await screen.findByDisplayValue('已存合成公司');
    act(()=>{bridge.config={...bridge.config,theme:'light'};bridge.listeners.forEach(fn=>fn())});
    expect(fetch).toHaveBeenCalledTimes(1);
    fireEvent.change(screen.getByLabelText('公司名称'),{target:{value:'新名称'}});
    fireEvent.click(screen.getByRole('button',{name:'保存',exact:true}));
    await waitFor(()=>expect(fetch).toHaveBeenCalledTimes(2));
    expect(screen.getByLabelText('公司名称').closest('fieldset')?.disabled).toBe(true);
    await act(async()=>finish(response(workspace('新名称'),8)));
    await screen.findByText('Desk 已确认保存');
    expect(bridge.context().data.summary.storage.revision).toBe(8);
    expect(bridge.context().filters.unsavedChanges).toBe(false);
  });
  it.each(['read','write','refresh'])('切工作区丢弃迟到%s，主题变化不丢草稿', async operation => {
    desk();let finish!:(r:any)=>void;
    if(operation==='write'||operation==='refresh')vi.mocked(fetch).mockResolvedValueOnce(response());
    if(operation==='refresh') { bridge.config.permissions.push('market.read'); vi.spyOn(researchData,'fetchFinancialEvidence').mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve})); }
    else vi.mocked(fetch).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}));
    vi.mocked(fetch).mockResolvedValueOnce(response(workspace('B工作区')));
    render(<EarningsWorkbench/>);
    if(operation!=='read') {
      await screen.findByDisplayValue('已存合成公司');
      fireEvent.click(screen.getByRole('button',{name:operation==='write'?'保存':'刷新证据',exact:true}));
    }
    await waitFor(()=>expect(finish).toBeTypeOf('function'));
    act(()=>{desk('b');bridge.listeners.forEach(fn=>fn())});
    await screen.findByDisplayValue('B工作区');
    await act(async()=>finish(operation==='refresh'?{basis:'annual',period:'2025-12-31',revenue:'123亿元'}:response(workspace('A迟到结果'),8)));
    expect(screen.queryByDisplayValue('A迟到结果')).toBeNull();
    expect(screen.queryByRole('region',{name:'财务刷新变更核对'})).toBeNull();
    expect((screen.getByLabelText('公司名称') as HTMLInputElement).value).toBe('B工作区');
  });
  it('删除失败不移除底稿，新稿只编辑结论也需确认', async () => {
    desk();vi.mocked(fetch).mockResolvedValueOnce(response()).mockResolvedValueOnce(new Response(null,{status:503}));
    render(<EarningsWorkbench/>);await screen.findByDisplayValue('已存合成公司');
    fireEvent.click(screen.getByRole('button',{name:'删除当前财报底稿'}));fireEvent.click(screen.getByRole('button',{name:'确认继续'}));
    await screen.findByRole('alert');expect(screen.getByDisplayValue('已存合成公司')).toBeTruthy();
    fireEvent.click(screen.getByRole('button',{name:'新建',exact:true}));
    fireEvent.change(screen.getByLabelText('一句话结论'),{target:{value:'仅填写研究判断'}});
    fireEvent.click(screen.getByRole('button',{name:'新建',exact:true}));
    expect(screen.getByRole('dialog')).toBeTruthy();fireEvent.click(screen.getByRole('button',{name:'取消操作'}));
    expect(screen.getByDisplayValue('仅填写研究判断')).toBeTruthy();
  });
  it('刷新只产生待核对候选，采用保留预期与旧底稿', async () => {
    const original=workspace();original.workbooks[0].headline='人工研究判断';original.workbooks[0].metrics[0].consensus=100;
    storage.set(key,JSON.stringify(original));
    const financials={basis:'annual',period:'2025-12-31',revenue:'123亿元',revenue_yoy:null,net_profit:null,net_profit_yoy:null,eps:null,bvps:null,roe:null,gross_margin:null,net_margin:null,op_cf_ps:null} as Financials;
    vi.spyOn(api,'financials').mockResolvedValue(financials);
    render(<EarningsWorkbench/>);await screen.findByDisplayValue('已存合成公司');
    fireEvent.click(screen.getByRole('button',{name:'刷新证据'}));await screen.findByRole('table',{name:'刷新候选指标'});
    expect((screen.getByLabelText('营业收入 实际') as HTMLInputElement).value).toBe('');
    const backup=JSON.parse(decodeURIComponent(screen.getByRole('link',{name:'导出当前草稿'}).getAttribute('href')!.split(',')[1]));
    expect(backup.pendingEvidence.rows[0].after).toBe(123);
    fireEvent.click(screen.getByRole('button',{name:'确认采用到草稿'}));
    expect((screen.getByLabelText('营业收入 实际') as HTMLInputElement).value).toBe('123');
    expect((screen.getByLabelText('营业收入 一致预期') as HTMLInputElement).value).toBe('100');
    expect(screen.getByDisplayValue('人工研究判断')).toBeTruthy();
    expect(JSON.parse(storage.get(key)!).workbooks[0].metrics[0].reported).toBeNull();
    expect(bridge.context().filters.unsavedChanges).toBe(true);
  });
  it('上传保存冲突保留原稿及PDF候选，禁止再次采用并可导出', async () => {
    desk();bridge.config.permissions.push('investment.files');
    vi.mocked(fetch).mockResolvedValueOnce(response()).mockResolvedValueOnce(new Response(null,{status:409}));
    const document:EarningsPdfImport={reportId:'pdf-test',name:'合成财报.pdf',security:{market:'CN',symbol:'SAMPLE',name:'上传合成公司',currency:'CNY'},periodEnd:'2025-12-31',basis:'annual',retrievedAt:'2026-10-20T00:00:00Z',pageCount:2,readPages:[1,2],warnings:[],candidates:[{id:'revenue',label:'营业收入',value:12,unit:'亿元',rawValue:'12',rawUnit:'亿元',page:2,excerpt:'合成营业收入12亿元',columnHeader:'2025年'}],discussion:[]};
    vi.spyOn(api,'uploadReport').mockResolvedValue({id:'pdf-test',name:'合成财报.pdf',ext:'.pdf',size:20,ts:10000,industry:'合成'});
    vi.spyOn(api,'earningsPdfCandidates').mockResolvedValue(document);
    render(<EarningsWorkbench/>);await screen.findByDisplayValue('已存合成公司');
    fireEvent.change(screen.getByLabelText('一句话结论'),{target:{value:'上传前未保存判断'}});
    fireEvent.change(screen.getByLabelText('选择财报 PDF'),{target:{files:[new File(['synthetic'],'合成财报.pdf',{type:'application/pdf'})]}});
    await screen.findByRole('table',{name:'PDF 指标候选'});
    fireEvent.click(screen.getByLabelText('已核对财报身份、期间、单位和选中指标'));
    fireEvent.click(screen.getByRole('button',{name:'确认新建并保存底稿'}));
    fireEvent.click(screen.getByRole('button',{name:'确认继续'}));
    await waitFor(()=>expect(bridge.context().data.summary.storage.status).toBe('error'));
    expect(screen.getByDisplayValue('上传前未保存判断')).toBeTruthy();
    expect(screen.getByRole('table',{name:'PDF 指标候选'})).toBeTruthy();
    expect((screen.getByRole('button',{name:'确认新建并保存底稿'}) as HTMLButtonElement).disabled).toBe(true);
    const backup=JSON.parse(decodeURIComponent(screen.getByRole('link',{name:'导出当前草稿'}).getAttribute('href')!.split(',')[1]));
    expect(backup.workbook.headline).toBe('上传前未保存判断');
    expect(backup.pendingUpload.document.reportId).toBe('pdf-test');
    expect(storage.size).toBe(0);
  });
});
