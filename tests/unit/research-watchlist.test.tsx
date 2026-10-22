// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { connectWorkspaceWatchlist, createWatchlistClient, loadLocalWatchGroups, saveLocalWatchGroups, loadWorkspaceWatchGroups } from '@/lib/watchlist';
import { previewGraphArtifact } from '@/lib/artifacts';
import { Watchlist } from '@/pages/Watchlist';

const bridge = vi.hoisted(() => ({ config:null as any, embedded:false, context:undefined as any, changed:undefined as any }));
vi.mock('@/lib/vibedesk', () => ({
  getVibeDeskConfig: () => bridge.config, waitForVibeDeskConfig: async () => bridge.config,
  get isVibeDeskEmbedded() { return bridge.embedded; },
  subscribeVibeDeskConfig: (fn:any) => { bridge.changed=fn; return () => {}; },
  emitVibeDeskEvent:vi.fn(), publishVibeDeskContext:vi.fn(),
  registerVibeDeskContextProvider: (fn:any) => { bridge.context=fn; return () => {}; },
}));
vi.mock('@/lib/api', () => ({api:{terminalQuotes:vi.fn(async () => ({items:[]}))}}));
const groups = [{id:'mine',name:'本机研究',symbols:[]}];
let storage: Map<string,string>;
beforeEach(() => {
  bridge.config=null; bridge.embedded=false; bridge.context=undefined;
  storage = new Map();
  vi.stubGlobal('localStorage',{getItem:(k:string)=>storage.get(k)??null,setItem:(k:string,v:string)=>storage.set(k,v)});
  vi.stubGlobal('fetch',vi.fn());
  vi.stubEnv('VITE_NEWMA_DESK_INTEGRATED','');
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.restoreAllMocks(); });

describe('新闻与催化剂签名共享自选', () => {
  function configure(moduleId = 'news-radar') {
    bridge.embedded = true;
    bridge.config = { apiOrigin: 'https://desk.test', storageGateway: 'https://desk.test/api/mods', moduleId,
      userId: 'alice', workspaceId: 'one', instanceId: 'instance-a', accessToken: 'synthetic', permissions: ['storage.read'] };
  }
  it.each(['news-radar','catalyst-calendar'])('%s只读签名访问，不带自报身份或Cookie', async moduleId => {
    configure(moduleId);
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({userId:'alice',workspaceId:'one',revision:1,groups})));
    expect(await loadWorkspaceWatchGroups()).toEqual(groups);
    expect(fetch).toHaveBeenCalledWith('https://desk.test/api/watchlists', expect.objectContaining({
      credentials:'omit',redirect:'error',cache:'no-store',headers:{Accept:'application/json',Authorization:'Bearer synthetic','X-Newma-Desk-Instance-Id':'instance-a'},
    }));
  });
  it('嵌入缺握手、缺读取权或服务拒绝均不退回旧自选', async () => {
    saveLocalWatchGroups(groups); bridge.embedded = true;
    await expect(loadWorkspaceWatchGroups()).rejects.toMatchObject({status:401});
    configure(); bridge.config.permissions=[];
    await expect(loadWorkspaceWatchGroups()).rejects.toMatchObject({status:403});
    expect(fetch).not.toHaveBeenCalled();
    configure(); vi.mocked(fetch).mockResolvedValue(new Response('{}',{status:401}));
    await expect(loadWorkspaceWatchGroups()).rejects.toMatchObject({status:401});
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it('跨账户响应被拒绝', async () => {
    configure(); vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({userId:'bob',workspaceId:'one',revision:1,groups})));
    await expect(loadWorkspaceWatchGroups()).rejects.toMatchObject({status:403});
  });
  it('A到B再到A也不会接受旧读取', async () => {
    configure(); let finish!: (value: Response) => void;
    vi.mocked(fetch).mockImplementation(() => new Promise(resolve => {finish=resolve;}));
    const pending=loadWorkspaceWatchGroups().catch(error=>error);
    const original=bridge.config;
    bridge.config={...original,workspaceId:'two'}; bridge.changed(bridge.config);
    bridge.config=original; bridge.changed(bridge.config);
    finish(new Response(JSON.stringify({userId:'alice',workspaceId:'one',revision:1,groups})));
    expect(await pending).toMatchObject({status:409});
  });
  it('原生单机仍读取明确保存的本机自选', async () => {
    saveLocalWatchGroups(groups);
    expect(await loadWorkspaceWatchGroups()).toEqual(groups);
    expect(fetch).not.toHaveBeenCalled();
  });
});

describe('独立研究的本机保存与共享能力边界', () => {
  it('保存的空分组列表与旧空自选不复活示例', () => {
    saveLocalWatchGroups([]);
    expect(loadLocalWatchGroups()).toEqual({groups:[],hasStoredValue:true});
    storage.clear(); storage.set('vr-watchlist','[]');
    expect(loadLocalWatchGroups().hasStoredValue).toBe(true);
    expect(loadLocalWatchGroups().groups.flatMap(g=>g.symbols)).toEqual([]);
  });
  it('存储失败返回失败，不假报保存成功', () => {
    vi.spyOn(localStorage,'setItem').mockImplementation(()=>{throw new Error('quota');});
    expect(saveLocalWatchGroups(groups)).toBe(false);
  });
  it('独立未接共享服务不请求不存在的接口，嵌入握手失败不降级为本机身份', async () => {
    expect(await connectWorkspaceWatchlist()).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
    bridge.embedded=true;
    await expect(connectWorkspaceWatchlist()).rejects.toThrow('尚未连接');
    expect(fetch).not.toHaveBeenCalled();
  });
  it('本机与不同工作区的缓存互不混用', () => {
    saveLocalWatchGroups(groups);
    bridge.embedded=true;
    expect(loadLocalWatchGroups()).toEqual({groups:[],hasStoredValue:false});
    bridge.config={userId:'u',workspaceId:'a',apiOrigin:'http://desk.local'};
    expect(loadLocalWatchGroups().groups).toEqual([]);
    saveLocalWatchGroups([{id:'a',name:'工作区 A',symbols:[]}]);
    bridge.config={...bridge.config,workspaceId:'b'};
    expect(loadLocalWatchGroups().groups).toEqual([]);
    bridge.config={...bridge.config,workspaceId:'a'};
    expect(loadLocalWatchGroups().groups[0].name).toBe('工作区 A');
    bridge.config=null; bridge.embedded=false;
    expect(loadLocalWatchGroups().groups).toEqual(groups);
  });
  it('共享接口失败不透传上游原文，合法空结果仍成功', async () => {
    const request=vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({detail:'private upstream text'}),{status:503}))
      .mockResolvedValueOnce(new Response(JSON.stringify({userId:'u',workspaceId:'w',revision:1,groups:[]})));
    const client=createWatchlistClient({baseUrl:'http://desk.local',userId:'u',workspaceId:'w',fetch:request});
    await expect(client.load()).rejects.toThrow('暂时不可用');
    expect((await client.load()).groups).toEqual([]);
  });
  it('未配置预览服务时明确提示，保留集成构建的同源预览', async () => {
    const input={moduleId:'industry-map',title:'测试结构',nodes:[],edges:[]};
    await expect(previewGraphArtifact(input,new AbortController().signal)).rejects.toThrow('Desk');
    expect(fetch).not.toHaveBeenCalled();
    vi.stubEnv('VITE_NEWMA_DESK_INTEGRATED','1');
    vi.mocked(fetch).mockResolvedValue(new Response('<html>preview</html>'));
    expect(await previewGraphArtifact(input,new AbortController().signal)).toContain('preview');
  });
  it('本机模式可新建分组并重载，页面和Context不声称已同步', async () => {
    saveLocalWatchGroups(groups);
    const page=render(<Watchlist/>);
    expect(await screen.findByText('本机保存')).toBeTruthy();
    fireEvent.click(screen.getByTitle('新建分组'));
    fireEvent.change(screen.getByRole('textbox',{name:'分组名称'}),{target:{value:'观察二组'}});
    fireEvent.click(screen.getByRole('button',{name:'保存',exact:true}));
    await waitFor(()=>expect(loadLocalWatchGroups().groups).toHaveLength(2));
    expect(bridge.context().data.summary.syncState).toBe('local');
    expect(bridge.context().data.asOf).toBeUndefined();
    page.unmount(); render(<Watchlist/>);
    expect(screen.getByRole('button',{name:/观察二组/})).toBeTruthy();
    expect(fetch).not.toHaveBeenCalled();
  });
  it('本机存储不可用时展示未保存，不静默丢失', async () => {
    vi.spyOn(localStorage,'setItem').mockImplementation(()=>{throw new Error('quota');});
    render(<Watchlist/>);
    expect(await screen.findByText('本机未保存')).toBeTruthy();
    expect(screen.getByRole('alert').textContent).toContain('刷新或关闭');
  });
  it('迟到的旧工作区响应不能覆盖新工作区或本机自选', async () => {
    let resolveOld!: (value:Response)=>void;
    const oldResponse=new Promise<Response>(resolve=>{resolveOld=resolve;});
    saveLocalWatchGroups(groups);
    bridge.embedded=true;
    bridge.config={userId:'u',workspaceId:'a',apiOrigin:'http://desk.local',instanceId:'one'};
    vi.mocked(fetch).mockReturnValueOnce(oldResponse).mockResolvedValue(new Response(JSON.stringify({
      userId:'u',workspaceId:'b',revision:1,groups:[{id:'b',name:'工作区 B',symbols:[]}],
    })));
    render(<Watchlist/>);
    await waitFor(()=>expect(fetch).toHaveBeenCalledTimes(1));
    act(()=>{bridge.config={...bridge.config,workspaceId:'b',instanceId:'two'};bridge.changed();});
    await screen.findByRole('button',{name:/工作区 B/});
    await act(async()=>resolveOld(new Response(JSON.stringify({userId:'u',workspaceId:'a',revision:1,groups:[{id:'a',name:'迟到的 A',symbols:[]}]}))));
    expect(screen.queryByRole('button',{name:/迟到的 A/})).toBeNull();
    expect(loadLocalWatchGroups().groups[0].name).toBe('工作区 B');
    bridge.config=null;bridge.embedded=false;
    expect(loadLocalWatchGroups().groups).toEqual(groups);
  });
  it('共享连接失败明确显示未同步，不把错误当作成功空列表', async () => {
    bridge.embedded=true;
    bridge.config={userId:'u',workspaceId:'a',apiOrigin:'http://desk.local',instanceId:'one'};
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({detail:'private upstream'}),{status:503}));
    render(<Watchlist/>);
    expect(await screen.findByText('Desk 未同步')).toBeTruthy();
    expect(screen.getByRole('alert').textContent).toContain('暂时不可用');
    expect(screen.queryByText('private upstream')).toBeNull();
    expect(bridge.context().data.summary.syncState).toBe('offline');
  });
  it('打开新工作区只读取，不将旧缓存自动上传覆盖', async () => {
    bridge.embedded=true;
    bridge.config={userId:'u',workspaceId:'a',apiOrigin:'http://desk.local',instanceId:'one'};
    saveLocalWatchGroups(groups);
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({userId:'u',workspaceId:'a',revision:0,groups:[]})));
    render(<Watchlist/>);
    await screen.findByText('Desk 已同步');
    expect(fetch).toHaveBeenCalledTimes(1);
    expect(vi.mocked(fetch).mock.calls[0][1]?.method).toBe('GET');
    expect(screen.queryByRole('button',{name:/本机研究/})).toBeNull();
  });
});
