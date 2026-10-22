// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { hydrateThesisPortfolio, persistThesisPortfolio, type InvestmentThesisPortfolio } from '@/lib/thesisTracker';
import { researchArchiveSourceUrl } from '@/lib/researchArchive';
import { ThesisTracker } from '@/pages/ThesisTracker';

const bridge=vi.hoisted(()=>({config:null as any,embedded:false,changed:undefined as any,context:undefined as any}));
vi.mock('@/lib/vibedesk',()=>({
  getVibeDeskConfig:()=>bridge.config,waitForVibeDeskConfig:async()=>bridge.config,
  get isVibeDeskEmbedded(){return bridge.embedded;},
  subscribeVibeDeskConfig:(fn:any)=>{bridge.changed=fn;return()=>{};},
  registerVibeDeskContextProvider:(fn:any)=>{bridge.context=fn;return()=>{};},
  publishVibeDeskContext:vi.fn(),
}));
const key='newma-desk.thesis-tracker.v1';
let storage:Map<string,string>;
function portfolio(title='已存逻辑',id='t1'):InvestmentThesisPortfolio {
  const now='2026-10-20T00:00:00Z';
  return {schemaVersion:'newma-desk.investment-thesis.v1',updatedAt:now,theses:[{
    id,title,security:{market:'CN',symbol:'TEST',name:'合成公司'},statement:'待验证的研究论点',status:'draft',conviction:'low',
    pillars:[1,2,3].map(i=>({id:`p${i}`,title:`支柱${i}`,expectation:'原预期',currentStatus:'待核验',trend:'pending',evidenceIds:[]})),
    invalidationRisks:[1,2,3].map(i=>({id:`r${i}`,statement:`风险${i}`,invalidationCondition:'指标恶化',status:'monitoring',evidenceIds:[]})),
    linkedCatalysts:[],evidence:[],updates:[],nextReviewAt:'2026-12-01',gaps:[],createdAt:now,updatedAt:now,
  }]};
}
function desk(workspaceId='a') {
  bridge.embedded=true;bridge.config={moduleId:'thesis-tracker',apiOrigin:'http://desk.test',storageGateway:'http://desk.test/storage',userId:'test-user',workspaceId,instanceId:workspaceId,accessToken:'test-only',permissions:['storage.read','storage.write']};
}
function response(value=portfolio(),revision=3){return new Response(JSON.stringify({value,revision}));}
beforeEach(()=>{
  bridge.config=null;bridge.embedded=false;bridge.changed=undefined;bridge.context=undefined;
  storage=new Map();
  vi.stubGlobal('localStorage',{getItem:(k:string)=>storage.get(k)??null,setItem:(k:string,v:string)=>storage.set(k,v)});
  vi.stubGlobal('fetch',vi.fn());vi.stubGlobal('confirm',vi.fn(()=>true));
  window.history.replaceState(null,'','/thesis-tracker');
});
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks();});

describe('投资逻辑保存与来源选择',()=>{
  it('本机保存回读，拒绝旧窗口覆盖与存储失败',async()=>{
    const first=await hydrateThesisPortfolio();
    const saved=await persistThesisPortfolio(portfolio(),first);
    expect(saved.mode).toBe('local');
    expect((await hydrateThesisPortfolio()).portfolio.theses[0].title).toBe('已存逻辑');
    await expect(persistThesisPortfolio(portfolio('旧窗口'),first)).rejects.toThrow('保存冲突');
    vi.spyOn(localStorage,'setItem').mockImplementation(()=>{throw new Error('quota');});
    await expect(persistThesisPortfolio(portfolio('新稿'),saved)).rejects.toThrow('本机保存失败');
  });
  it('Desk空库或失败不读取本机缓存，嵌入未授权拒绝',async()=>{
    storage.set(key,JSON.stringify(portfolio('私有旧缓存')));desk();
    vi.mocked(fetch).mockResolvedValueOnce(new Response(null,{status:404})).mockResolvedValueOnce(new Response(null,{status:503}));
    expect((await hydrateThesisPortfolio()).portfolio.theses).toEqual([]);
    await expect(hydrateThesisPortfolio()).rejects.toThrow('未使用本机');
    bridge.config=null;
    await expect(hydrateThesisPortfolio()).rejects.toThrow('尚未连接');
    expect(fetch).toHaveBeenCalledTimes(2);
  });
  it('按加载版本提交，冲突不重读重试，也不污染本机',async()=>{
    desk();vi.mocked(fetch).mockResolvedValueOnce(response()).mockResolvedValueOnce(new Response(null,{status:409}));
    const session=await hydrateThesisPortfolio();
    await expect(persistThesisPortfolio(portfolio('修改'),session)).rejects.toThrow('保存冲突');
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(JSON.parse(String(vi.mocked(fetch).mock.calls[1][1]?.body)).expectedRevision).toBe(3);
    expect(storage.size).toBe(0);
  });
  it('保存成功采纳真实回执，旧身份与只读会话不能写入',async()=>{
    desk();vi.mocked(fetch).mockResolvedValueOnce(response()).mockResolvedValueOnce(response(portfolio('回执'),4));
    const session=await hydrateThesisPortfolio();
    const saved=await persistThesisPortfolio(portfolio('提交'),session);
    expect(saved).toMatchObject({revision:4,portfolio:{theses:[{title:'回执'}]}});
    bridge.config.permissions=['storage.read'];
    await expect(persistThesisPortfolio(portfolio(),saved)).rejects.toThrow('没有保存权限');
    desk('b');await expect(persistThesisPortfolio(portfolio(),saved)).rejects.toThrow('工作区已变化');
  });
  it('损坏的档案或证据不能被静默丢弃后覆盖',async()=>{
    storage.set(key,'broken');await expect(hydrateThesisPortfolio()).rejects.toThrow('读取失败');
    const data=portfolio();(data.theses[0].evidence as any[]).push({id:'broken'});
    storage.set(key,JSON.stringify(data));await expect(hydrateThesisPortfolio()).rejects.toThrow('证据不完整');
  });
  it('页面保存失败保留旧档案与当前草稿，Context读取实际编辑值',async()=>{
    storage.set(key,JSON.stringify(portfolio()));render(<ThesisTracker/>);await screen.findByDisplayValue('已存逻辑');
    fireEvent.change(screen.getByLabelText('逻辑标题'),{target:{value:'尚未保存'}});
    expect(bridge.context().data.summary.selectedThesis.title).toBe('尚未保存');
    expect(bridge.context().data.freshness).toBe('unknown');expect(bridge.context().data.asOf).toBeUndefined();
    vi.spyOn(localStorage,'setItem').mockImplementation(()=>{throw new Error('quota');});
    fireEvent.click(screen.getByRole('button',{name:'保存',exact:true}));
    await screen.findByRole('alert');
    expect((screen.getByLabelText('逻辑标题') as HTMLInputElement).value).toBe('尚未保存');
    expect(storage.get(key)).toContain('已存逻辑');
    expect(screen.queryByText('Desk 已确认保存')).toBeNull();
    expect(bridge.context().filters.unsavedChanges).toBe(true);
  });
  it('等待回执期间锁定编辑，成功后才更新档案',async()=>{
    desk();let finish!:(value:Response)=>void;
    vi.mocked(fetch).mockResolvedValueOnce(response()).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
    render(<ThesisTracker/>);await screen.findByDisplayValue('已存逻辑');
    fireEvent.change(screen.getByLabelText('逻辑标题'),{target:{value:'新结论'}});
    fireEvent.click(screen.getByRole('button',{name:'保存',exact:true}));
    await waitFor(()=>expect(fetch).toHaveBeenCalledTimes(2));
    expect(screen.getByLabelText('逻辑标题').closest('fieldset')?.disabled).toBe(true);
    expect(screen.queryByText('Desk 已确认保存')).toBeNull();
    await act(async()=>finish(response(portfolio('新结论'),4)));
    await screen.findByText('Desk 已确认保存');
    expect(bridge.context().filters.unsavedChanges).toBe(false);
    expect(bridge.context().data.summary.storage.revision).toBe(4);
  });
  it('删除失败保留当前档案和草稿',async()=>{
    desk();vi.mocked(fetch).mockResolvedValueOnce(response()).mockResolvedValueOnce(new Response(null,{status:503}));
    render(<ThesisTracker/>);await screen.findByDisplayValue('已存逻辑');
    fireEvent.click(screen.getByRole('button',{name:'删除投资逻辑'}));await screen.findByRole('alert');
    expect((screen.getByLabelText('逻辑标题') as HTMLInputElement).value).toBe('已存逻辑');
    expect(bridge.context().data.summary.thesisCount).toBe(1);
    expect((screen.getByRole('button',{name:'保存',exact:true}) as HTMLButtonElement).disabled).toBe(true);
  });
  it('切换工作区后旧读取结果不会覆盖新工作区',async()=>{
    desk();let finish!:(value:Response)=>void;
    vi.mocked(fetch).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;})).mockResolvedValueOnce(response(portfolio('B工作区')));
    render(<ThesisTracker/>);await waitFor(()=>expect(fetch).toHaveBeenCalledTimes(1));
    expect(screen.getByLabelText('逻辑标题').closest('fieldset')?.disabled).toBe(true);
    act(()=>{desk('b');bridge.changed();});await screen.findByDisplayValue('B工作区');
    await act(async()=>finish(response(portfolio('A旧结果'))));
    expect((screen.getByLabelText('逻辑标题') as HTMLInputElement).value).toBe('B工作区');
  });
  it('旧工作区写入回执迟到，不会把旧稿带入新工作区',async()=>{
    desk();let finish!:(value:Response)=>void;
    vi.mocked(fetch).mockResolvedValueOnce(response()).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;})).mockResolvedValueOnce(response(portfolio('B工作区')));
    render(<ThesisTracker/>);await screen.findByDisplayValue('已存逻辑');
    fireEvent.change(screen.getByLabelText('逻辑标题'),{target:{value:'A提交稿'}});
    fireEvent.click(screen.getByRole('button',{name:'保存',exact:true}));await waitFor(()=>expect(fetch).toHaveBeenCalledTimes(2));
    act(()=>{desk('b');bridge.changed();});await screen.findByDisplayValue('B工作区');
    await act(async()=>finish(response(portfolio('A提交稿'),4)));
    expect((screen.getByLabelText('逻辑标题') as HTMLInputElement).value).toBe('B工作区');
    expect(screen.queryByText('Desk 已确认保存')).toBeNull();
  });
  it('引用深链精确选择第二档案，缺失时不借用第一档案',async()=>{
    const data=portfolio();data.theses.push(portfolio('被引用逻辑','t2').theses[0]);storage.set(key,JSON.stringify(data));
    window.history.replaceState(null,'','/thesis-tracker#artifact=t2');
    const view=render(<ThesisTracker/>);await screen.findByDisplayValue('被引用逻辑');
    expect(bridge.context().selection.thesisId).toBe('t2');view.unmount();
    window.history.replaceState(null,'','/thesis-tracker#artifact=missing');render(<ThesisTracker/>);
    await screen.findByText(/未找到链接指定/);
    expect((screen.getByLabelText('逻辑标题') as HTMLInputElement).value).toBe('');
    expect(researchArchiveSourceUrl({id:'archive:t2',kind:'thesis',sourceModId:'thesis-tracker',artifactId:'t:2',title:'测试',updatedAt:'2026-10-20',status:'draft',tags:[]})).toBe('/thesis-tracker#artifact=t%3A2');
  });
  it('同页引用切换保留未保存草稿，明确确认后才切换',async()=>{
    const data=portfolio();data.theses.push(portfolio('另一档案','t2').theses[0]);storage.set(key,JSON.stringify(data));
    render(<ThesisTracker/>);await screen.findByDisplayValue('已存逻辑');
    const navigate=(id:string)=>act(()=>{window.history.replaceState(null,'',`/thesis-tracker#artifact=${id}`);window.dispatchEvent(new HashChangeEvent('hashchange'));});
    navigate('t2');await screen.findByDisplayValue('另一档案');
    fireEvent.change(screen.getByLabelText('逻辑标题'),{target:{value:'未保存草稿'}});
    navigate('t1');
    expect((screen.getByLabelText('逻辑标题') as HTMLInputElement).value).toBe('未保存草稿');
    vi.mocked(confirm).mockReturnValue(false);
    fireEvent.click(screen.getByRole('button',{name:'打开链接指定档案'}));
    expect(bridge.context().selection.thesisId).toBe('t2');
    expect(bridge.context().data.summary.pendingArtifactId).toBe('t1');
    fireEvent.click(screen.getByRole('button',{name:'保存',exact:true}));await screen.findByText('已保存到本机浏览器，未同步到 Desk');
    expect(screen.getByRole('button',{name:'打开链接指定档案'})).toBeTruthy();
    expect(bridge.context().selection.thesisId).toBe('t2');
    vi.mocked(confirm).mockReturnValue(true);
    fireEvent.click(screen.getByRole('button',{name:'打开链接指定档案'}));await screen.findByDisplayValue('已存逻辑');
    navigate('missing');await screen.findByText(/未找到链接指定/);
    expect((screen.getByLabelText('逻辑标题') as HTMLInputElement).value).toBe('已存逻辑');
  });
  it('尚未加入的证据不因保存或切换被静默丢弃',async()=>{
    storage.set(key,JSON.stringify(portfolio()));render(<ThesisTracker/>);await screen.findByDisplayValue('已存逻辑');
    fireEvent.change(screen.getByPlaceholderText('来源名称（必填）'),{target:{value:'未加入的原件'}});
    fireEvent.click(screen.getByRole('button',{name:'保存',exact:true}));await screen.findByText(/还有尚未加入/);
    expect(bridge.context().filters.unsavedChanges).toBe(true);
    vi.mocked(confirm).mockReturnValue(false);fireEvent.click(screen.getAllByRole('button',{name:'新建',exact:true})[0]);
    expect((screen.getByPlaceholderText('来源名称（必填）') as HTMLInputElement).value).toBe('未加入的原件');
    expect(bridge.context().data.summary.pendingInputs.evidence.source).toBe('未加入的原件');
    vi.mocked(confirm).mockReturnValue(true);fireEvent.click(screen.getByRole('button',{name:'清空未加入输入'}));
    expect((screen.getByLabelText('逻辑标题') as HTMLInputElement).value).toBe('已存逻辑');
    expect(bridge.context().filters.unsavedChanges).toBe(false);
  });
});
