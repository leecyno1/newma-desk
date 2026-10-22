// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { blankResearchMemo, emptyResearchMemoWorkspace, hydrateResearchMemoWorkspace, persistResearchMemoWorkspace, researchReferenceCheck, researchReferenceFromEntry } from '@/lib/researchMemo';
import { loadResearchArchive, researchArchiveSourceUrl, type ResearchArchiveEntry, type ResearchArchiveIndex } from '@/lib/researchArchive';
import { ResearchMemo } from '@/pages/ResearchMemo';

const bridge = vi.hoisted(() => ({ config:null as any, embedded:false, context:undefined as any, changed:undefined as any, event:undefined as any }));
vi.mock('@/lib/vibedesk', () => ({
  getVibeDeskConfig: () => bridge.config, waitForVibeDeskConfig: async () => bridge.config,
  get isVibeDeskEmbedded() { return bridge.embedded; },
  subscribeVibeDeskConfig: (fn:any) => { bridge.changed=fn; return () => {}; },
  subscribeVibeDeskEvent: (fn:any) => { bridge.event=fn; return () => {}; },
  publishVibeDeskContext:vi.fn(),
  registerVibeDeskContextProvider: (fn:any) => { bridge.context=fn; return () => {}; },
}));
const key='newma-desk.research-memo.v1';
let storage: Map<string,string>;
function workspace(title='测试备忘录') {
  const memo=blankResearchMemo(); memo.title=title;
  memo.security={market:'CN',symbol:'TEST',name:'测试公司',currency:'CNY'};
  for(const field of ['conclusion','coreThesis','keyDebate','variantPerception','whatMayBeMissing','breakpoint'] as const) memo.executiveView[field]='测试研究判断';
  return {...emptyResearchMemoWorkspace(),memos:[memo]};
}
function desk(workspaceId='a') {
  bridge.embedded=true;
  bridge.config={moduleId:'research-memo',userId:'test-user',workspaceId,instanceId:workspaceId,apiOrigin:'http://desk.test',gatewayOrigin:'http://desk.test',storageGateway:'http://desk.test/storage',accessToken:'test-only',permissions:['storage.read','storage.write']};
}
function response(value=workspace(),revision=3) { return new Response(JSON.stringify({value,revision})); }
beforeEach(() => {
  bridge.config=null;bridge.embedded=false;bridge.context=undefined;bridge.changed=undefined;
  storage=new Map();
  vi.stubGlobal('localStorage',{getItem:(k:string)=>storage.get(k)??null,setItem:(k:string,v:string)=>storage.set(k,v)});
  vi.stubGlobal('fetch',vi.fn());
  vi.stubGlobal('confirm',vi.fn(()=>true));
});
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks();});

function archiveEntry(): ResearchArchiveEntry {
  return {id:'archive:thesis-tracker:t1',kind:'thesis',sourceModId:'thesis-tracker',artifactId:'t1',title:'测试投资逻辑',status:'active',updatedAt:'2026-10-20T00:00:00Z',sourceRevision:2,tags:[]};
}
function archiveIndex(entries=[archiveEntry()]): ResearchArchiveIndex {
  return {schemaVersion:'newma-desk.research-archive.v1',userId:'test-user',workspaceId:'a',generatedAt:'2026-10-20T00:00:00Z',entries,unavailableSources:[],truncated:false};
}

describe('研究备忘录工作区引用',()=>{
  it('使用真实会话头读取，拒绝错工作区，不降级本机缓存',async()=>{
    desk();storage.set('newma-desk.thesis-tracker.v1',JSON.stringify({theses:[{id:'private',title:'旧缓存'}]}));
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify(archiveIndex())))
      .mockResolvedValueOnce(new Response(JSON.stringify({...archiveIndex(),workspaceId:'other'})))
      .mockResolvedValueOnce(new Response(null,{status:503}));
    expect((await loadResearchArchive()).entries[0].artifactId).toBe('t1');
    expect(fetch).toHaveBeenNthCalledWith(1,'http://desk.test/api/research-archive',expect.objectContaining({headers:{Authorization:'Bearer test-only','X-Newma-Desk-Instance-Id':'a'}}));
    await expect(loadResearchArchive()).rejects.toThrow('工作区身份');
    await expect(loadResearchArchive()).rejects.toThrow('未使用本机缓存');
  });
  it('档案未完整读取时不误报删除，完整覆盖才报告缺失',()=>{
    const ref=researchReferenceFromEntry(archiveEntry());
    expect(researchReferenceCheck(ref,null).state).toBe('unchecked');
    expect(researchReferenceCheck(ref,{...archiveIndex([]),truncated:true}).state).toBe('unavailable');
    expect(researchReferenceCheck(ref,{...archiveIndex([]),unavailableSources:['thesis-tracker']}).state).toBe('unavailable');
    expect(researchReferenceCheck(ref,archiveIndex([])).state).toBe('missing');
    expect(researchReferenceCheck({...ref,sourceModId:'macro-monitor'},archiveIndex([])).state).toBe('unavailable');
  });
  it('来源更新只提示，显式采纳保留备注和引用身份，版本可保存回读',async()=>{
    const source=archiveEntry(),ref={...researchReferenceFromEntry(source),note:'保留原研究备注'};
    const next={...source,sourceRevision:3,title:'更新后的逻辑',updatedAt:'2026-10-20T01:00:00Z'};
    expect(researchReferenceCheck(ref,archiveIndex()).state).toBe('current');
    expect(researchReferenceCheck(ref,archiveIndex([next])).state).toBe('changed');
    expect(ref.title).toBe('测试投资逻辑');
    const adopted=researchReferenceFromEntry(next,ref);
    expect(adopted).toMatchObject({id:ref.id,note:ref.note,sourceRevision:3,sourceUpdatedAt:next.updatedAt});
    const value=workspace();value.memos[0].linkedArtifacts=[adopted];
    await persistResearchMemoWorkspace(value,await hydrateResearchMemoWorkspace());
    expect((await hydrateResearchMemoWorkspace()).workspace.memos[0].linkedArtifacts[0]).toEqual(adopted);
    expect(researchReferenceFromEntry({...source,sourceRevision:undefined}).status).toBe('unverified');
    expect(researchReferenceCheck(ref,archiveIndex([{...source,status:'invalidated'}])).state).toBe('inactive');
    const local={...source,sourceRevision:undefined};
    const localRef=researchReferenceFromEntry(local);
    expect(researchReferenceCheck(localRef,archiveIndex([{...local,title:'本机更新'}])).state).toBe('changed');
    expect(researchReferenceFromEntry({...local,title:'本机更新'},localRef).status).toBe('unverified');
  });
  it('页面发现、引用、再核对并采纳新版，不自动改写结论',async()=>{
    desk();const value=workspace();
    vi.mocked(fetch).mockResolvedValueOnce(response(value))
      .mockResolvedValueOnce(new Response(JSON.stringify(archiveIndex())))
      .mockResolvedValueOnce(new Response(JSON.stringify(archiveIndex([{...archiveEntry(),title:'来源新版标题',sourceRevision:3}]))));
    render(<ResearchMemo/>);await screen.findByDisplayValue('测试备忘录');
    fireEvent.click(screen.getByRole('button',{name:'发现 / 核对工作区档案'}));
    fireEvent.click(await screen.findByRole('button',{name:/测试投资逻辑.*添加引用/}));
    expect(screen.getByLabelText('引用标题').getAttribute('value')).toBe('测试投资逻辑');
    fireEvent.change(screen.getByLabelText('引用备注'),{target:{value:'需要保留的备注'}});
    fireEvent.click(screen.getByRole('button',{name:'发现 / 核对工作区档案'}));
    await screen.findByText('来源版本已变化，需复核后采纳');
    expect(screen.getByLabelText('引用标题').getAttribute('value')).toBe('测试投资逻辑');
    fireEvent.click(screen.getByRole('button',{name:'采纳当前引用版本'}));
    expect(screen.getByLabelText('引用标题').getAttribute('value')).toBe('来源新版标题');
    expect((screen.getByLabelText('研究结论') as HTMLTextAreaElement).value).toBe('测试研究判断');
    expect((screen.getByLabelText('引用备注') as HTMLTextAreaElement).value).toBe('需要保留的备注');
    expect(bridge.context().data.summary.referenceChecks[0].state).toBe('current');
    fireEvent.change(screen.getByLabelText('档案 ID'),{target:{value:'manual-id'}});
    expect(bridge.context().data.summary.linkedArtifacts[0]).toMatchObject({status:'unverified',sourceRevision:undefined});
  });
  it('读取失败保留已有引用，不能采纳旧索引，独立链接使用真实路由',async()=>{
    desk();const value=workspace();value.memos[0].linkedArtifacts=[researchReferenceFromEntry(archiveEntry())];
    vi.mocked(fetch).mockResolvedValueOnce(response(value)).mockResolvedValueOnce(new Response(null,{status:503}));
    render(<ResearchMemo/>);await screen.findByDisplayValue('测试备忘录');
    fireEvent.click(screen.getByRole('button',{name:'发现 / 核对工作区档案'}));
    await screen.findByText(/工作区档案读取失败/);
    expect(screen.getByLabelText('引用标题').getAttribute('value')).toBe('测试投资逻辑');
    expect(screen.queryByRole('button',{name:'采纳当前引用版本'})).toBeNull();
    bridge.config=null;bridge.embedded=false;
    expect(researchArchiveSourceUrl({...archiveEntry(),kind:'research-record'})).toBe('/notes');
    expect(researchArchiveSourceUrl({...archiveEntry(),kind:'uploaded-report'})).toBe('/my-reports');
  });
});

describe('研究备忘录真实持久化',()=>{
  it('本机保存后重新读取，失败不会声称保存成功',async()=>{
    const session=await hydrateResearchMemoWorkspace();
    const saved=await persistResearchMemoWorkspace(workspace(),session);
    expect(saved.mode).toBe('local');
    expect((await hydrateResearchMemoWorkspace()).workspace.memos[0].title).toBe('测试备忘录');
    vi.spyOn(localStorage,'setItem').mockImplementation(()=>{throw new Error('quota');});
    await expect(persistResearchMemoWorkspace(workspace('新稿'),saved)).rejects.toThrow('本机保存失败');
  });
  it('新工作区为空或读取失败时均不借用本机数据',async()=>{
    storage.set(key,JSON.stringify(workspace('本机私有草稿')));desk();
    vi.mocked(fetch).mockResolvedValueOnce(new Response(null,{status:404})).mockResolvedValueOnce(new Response('private upstream',{status:503}));
    expect((await hydrateResearchMemoWorkspace()).workspace.memos).toEqual([]);
    await expect(hydrateResearchMemoWorkspace()).rejects.toThrow('读取失败');
    expect(storage.get(key)).toContain('本机私有草稿');
  });
  it('嵌入无授权不降级本机，缓存发现不混入旧工作区',async()=>{
    storage.set(key,JSON.stringify(workspace()));bridge.embedded=true;
    storage.set('newma-desk.thesis-tracker.v1',JSON.stringify({theses:[{id:'private',title:'旧缓存'}]}));
    await expect(hydrateResearchMemoWorkspace()).rejects.toThrow('尚未连接');
    await expect(loadResearchArchive()).rejects.toThrow('尚未连接');
    expect(fetch).not.toHaveBeenCalled();
  });
  it('按加载修订号提交，409不重新读取并覆盖，原本机数据不变',async()=>{
    desk();vi.mocked(fetch).mockResolvedValueOnce(response()).mockResolvedValueOnce(new Response(null,{status:409}));
    const session=await hydrateResearchMemoWorkspace();
    await expect(persistResearchMemoWorkspace(workspace('当前草稿'),session)).rejects.toThrow('保存冲突');
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(JSON.parse(String(vi.mocked(fetch).mock.calls[1][1]?.body)).expectedRevision).toBe(3);
    expect(storage.size).toBe(0);
  });
  it('成功采纳存储回执修订号，失败不回退到本机',async()=>{
    desk();const value=workspace('新版本');
    vi.mocked(fetch).mockResolvedValueOnce(response()).mockResolvedValueOnce(response(value,4)).mockRejectedValueOnce(new Error('private network'));
    const session=await hydrateResearchMemoWorkspace();
    const saved=await persistResearchMemoWorkspace(value,session);
    expect(saved.revision).toBe(4);expect(saved.workspace.memos[0].title).toBe('新版本');
    await expect(persistResearchMemoWorkspace(workspace(),saved)).rejects.toThrow('保存未确认');
    expect(storage.size).toBe(0);
  });
  it('身份切换后不能将旧草稿写入新工作区',async()=>{
    desk();vi.mocked(fetch).mockResolvedValueOnce(response());
    const session=await hydrateResearchMemoWorkspace();desk('b');
    await expect(persistResearchMemoWorkspace(workspace(),session)).rejects.toThrow('工作区已变化');
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it('异常存储文档不能当空档案并被后续覆盖',async()=>{
    desk();vi.mocked(fetch).mockResolvedValueOnce(response({schemaVersion:'broken',memos:[]} as any));
    await expect(hydrateResearchMemoWorkspace()).rejects.toThrow('格式');
  });
  it('保存失败保留输入、已存档案和未保存状态',async()=>{
    storage.set(key,JSON.stringify(workspace()));render(<ResearchMemo/>);
    await screen.findByDisplayValue('测试备忘录');
    fireEvent.change(screen.getByRole('textbox',{name:'备忘录标题'}),{target:{value:'尚未保存的改动'}});
    vi.spyOn(localStorage,'setItem').mockImplementation(()=>{throw new Error('quota');});
    fireEvent.click(screen.getByRole('button',{name:'保存',exact:true}));
    expect((await screen.findByRole('alert')).textContent).toContain('本机保存失败');
    expect(screen.getByDisplayValue('尚未保存的改动')).toBeTruthy();
    expect(screen.getByRole('button',{name:/测试备忘录/})).toBeTruthy();
    expect(bridge.context().data.summary.unsavedChanges).toBe(true);
    expect(screen.queryByText('已保存到 Desk 工作区')).toBeNull();
  });
  it('读取中禁用编辑，迟到的旧工作区结果不覆盖新工作区',async()=>{
    desk();let resolveOld!:(r:Response)=>void;
    vi.mocked(fetch).mockReturnValueOnce(new Promise(r=>{resolveOld=r;})).mockResolvedValueOnce(response(workspace('工作区 B')));
    render(<ResearchMemo/>);await waitFor(()=>expect(fetch).toHaveBeenCalledTimes(1));
    expect(screen.getByRole('textbox',{name:'备忘录标题'}).closest('fieldset')?.disabled).toBe(true);
    act(()=>{desk('b');bridge.changed();});await screen.findByDisplayValue('工作区 B');
    await act(async()=>resolveOld(response(workspace('迟到的 A'))));
    expect(screen.queryByDisplayValue('迟到的 A')).toBeNull();
  });
  it('只改风险也提示未保存',async()=>{
    render(<ResearchMemo/>);await waitFor(()=>expect(screen.getByRole('button',{name:'保存',exact:true}).disabled).toBe(false));
    fireEvent.change(screen.getByDisplayValue('关键风险 1'),{target:{value:'新的风险'}});
    expect(bridge.context().data.summary.unsavedChanges).toBe(true);
    fireEvent.click(screen.getByRole('button',{name:'新建',exact:true}));expect(confirm).toHaveBeenCalled();
  });
  it('本机另一窗口保存后，旧窗口不能覆盖',async()=>{
    const session=await hydrateResearchMemoWorkspace();
    await persistResearchMemoWorkspace(workspace('其他窗口的新稿'),session);
    await expect(persistResearchMemoWorkspace(workspace('旧窗口草稿'),session)).rejects.toThrow('保存冲突');
    expect((await hydrateResearchMemoWorkspace()).workspace.memos[0].title).toBe('其他窗口的新稿');
  });
  it('等待远端回执时不提前改档案，拒绝二次保存，确认后清除未保存标志',async()=>{
    desk();const value=workspace();let resolveSave!:(r:Response)=>void;
    vi.mocked(fetch).mockResolvedValueOnce(response(value)).mockReturnValueOnce(new Promise(r=>{resolveSave=r;}));
    render(<ResearchMemo/>);await screen.findByDisplayValue('测试备忘录');
    fireEvent.change(screen.getByRole('textbox',{name:'备忘录标题'}),{target:{value:'新标题'}});
    fireEvent.click(screen.getByRole('button',{name:'保存',exact:true}));
    expect(screen.getByRole('button',{name:'保存中…'}).disabled).toBe(true);
    expect(screen.getByRole('button',{name:/测试备忘录/})).toBeTruthy();
    expect(screen.queryByText('Desk 已确认保存')).toBeNull();
    const sent=JSON.parse(String(vi.mocked(fetch).mock.calls[1][1]?.body));
    await act(async()=>resolveSave(response(sent.value,4)));
    expect(screen.getByText('Desk 已确认保存')).toBeTruthy();
    expect(bridge.context().data.summary.unsavedChanges).toBe(false);
    expect(bridge.context().data.summary.storage.revision).toBe(4);
    expect(fetch).toHaveBeenCalledTimes(2);
  });
  it('删除失败不移除原档案，也不切换草稿',async()=>{
    storage.set(key,JSON.stringify(workspace()));render(<ResearchMemo/>);await screen.findByDisplayValue('测试备忘录');
    vi.spyOn(localStorage,'setItem').mockImplementation(()=>{throw new Error('quota');});
    fireEvent.click(screen.getByRole('button',{name:'删除备忘录'}));
    expect((await screen.findByRole('alert')).textContent).toContain('本机保存失败');
    expect(screen.getByDisplayValue('测试备忘录')).toBeTruthy();
    expect(storage.get(key)).toContain('测试备忘录');
  });
  it('已有研究对象不被证券事件改写，有来源不等于新鲜数据',async()=>{
    const value=workspace();value.memos[0].sources=[{id:'source',label:'待核验来源',kind:'user',claimType:'inference',asOf:'2020-01-01',status:'available'}];
    storage.set(key,JSON.stringify(value));render(<ResearchMemo/>);await screen.findByDisplayValue('测试备忘录');
    act(()=>bridge.event({event:'security.selected',payload:{market:'US',symbol:'OTHER',name:'另一公司'}}));
    expect(screen.getByDisplayValue('TEST')).toBeTruthy();
    expect(bridge.context().data.freshness).toBe('unknown');
  });
  it('概率总和正确但单项越界时也不能保存或静默裁剪',async()=>{
    storage.set(key,JSON.stringify(workspace()));render(<ResearchMemo/>);await screen.findByDisplayValue('测试备忘录');
    fireEvent.change(screen.getByRole('spinbutton',{name:'悲观概率'}),{target:{value:'-20'}});
    fireEvent.change(screen.getByRole('spinbutton',{name:'基准概率'}),{target:{value:'95'}});
    fireEvent.click(screen.getByRole('button',{name:'保存',exact:true}));
    expect(await screen.findByText('每个情景的概率必须在 0–100% 之间')).toBeTruthy();
    expect(JSON.parse(storage.get(key)!).memos[0].scenarios[0].probabilityPct).toBe(25);
  });
});
