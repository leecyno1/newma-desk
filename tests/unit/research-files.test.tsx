// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { api, reportBlob, reportScope } from '@/lib/api';
import { MyReports } from '@/pages/MyReports';
import { ReportSourceLink } from '@/components/ReportSourceLink';

const bridge=vi.hoisted(()=>({config:null as any,embedded:false,listeners:new Set<()=>void>(),context:undefined as any}));
vi.mock('@/lib/vibedesk',()=>({
  getVibeDeskConfig:()=>bridge.config,waitForVibeDeskConfig:async()=>bridge.config,
  get isVibeDeskEmbedded(){return bridge.embedded},
  subscribeVibeDeskConfig:(fn:()=>void)=>{bridge.listeners.add(fn);return()=>bridge.listeners.delete(fn)},
  publishVibeDeskContext:vi.fn(),registerVibeDeskContextProvider:(fn:any)=>{bridge.context=fn;return()=>{}},
}));
function desk(workspaceId='a') {
  bridge.embedded=true;
  bridge.config={apiOrigin:'http://desk.test',gatewayOrigin:'http://desk.test',userId:'u',workspaceId,moduleId:'research-library',instanceId:workspaceId,accessToken:'test-token',permissions:['investment.files','investment.read']};
}
function notify(){bridge.listeners.forEach(fn=>fn())}
const report=(id='r1')=>({id,name:`${id}.pdf`,industry:'未分类',ext:'.pdf',size:20,ts:10000});
function json(data:any){return new Response(JSON.stringify({data}))}
function index(){return new Response(JSON.stringify({schemaVersion:'newma-desk.research-archive.v1',userId:'u',workspaceId:bridge.config.workspaceId,generatedAt:'2026-10-20T00:00:00Z',entries:[],unavailableSources:[],truncated:false}))}
beforeEach(()=>{
  bridge.config=null;bridge.embedded=false;bridge.listeners.clear();
  vi.stubGlobal('localStorage',{getItem:()=>null,setItem:vi.fn()});
  vi.stubGlobal('fetch',vi.fn());
});
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks()});

it('uses signed file permissions, refuses missing authorization without native fallback',async()=>{
  desk();vi.mocked(fetch).mockResolvedValue(json([]));
  await api.myReports();
  expect(fetch).toHaveBeenCalledWith('http://desk.test/api/research/myreports',expect.objectContaining({headers:{Authorization:'Bearer test-token','X-Newma-Desk-Instance-Id':'a'}}));
  bridge.config.permissions=['storage.write'];
  await expect(api.uploadReport('a.pdf','test')).rejects.toThrow('文件权限');
  bridge.config=null;
  await expect(api.myReports()).rejects.toThrow('已授权');
  expect(fetch).toHaveBeenCalledTimes(1);
});

it('keeps native backend key support and never sends a session token to the native endpoint',async()=>{
  vi.stubGlobal('localStorage',{getItem:()=> 'native-key'});
  vi.mocked(fetch).mockResolvedValue(json([]));
  await api.myReports();
  expect(fetch).toHaveBeenCalledWith('/api/myreports',expect.objectContaining({headers:{Authorization:'Bearer native-key'}}));
});

it('explains storage failures without exposing backend details or retrying',async()=>{
  desk();
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({code:'REPORT_STORAGE_UNAVAILABLE',detail:'/private/secret-path'}),{status:503}));
  await expect(api.myReports()).rejects.toThrow('请先检查索引、磁盘空间及存储权限');
  expect(fetch).toHaveBeenCalledTimes(1);
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({detail:'untrusted upstream error'}),{status:503}));
  await expect(api.myReports()).rejects.toThrow('HTTP 503');
});

it('rejects an old workspace error after reading a delayed error body',async()=>{
  desk();let finish!:(data:unknown)=>void;
  vi.mocked(fetch).mockResolvedValue({ok:false,status:503,json:()=>new Promise(resolve=>{finish=resolve})} as Response);
  const pending=api.myReports();const rejected=expect(pending).rejects.toThrow('工作区已切换');
  await waitFor(()=>expect(finish).toBeDefined());desk('b');finish({code:'REPORT_STORAGE_UNAVAILABLE'});await rejected;
});

it('rejects a scope change before sending or after reading a delayed body',async()=>{
  desk();const scope=reportScope();desk('b');
  await expect(api.uploadReport('x.pdf','abc',{scope})).rejects.toThrow('工作区已切换');
  expect(fetch).not.toHaveBeenCalled();
  let finish!:(b:Blob)=>void;
  vi.mocked(fetch).mockResolvedValue({ok:true,blob:()=>new Promise<Blob>(resolve=>{finish=resolve})} as Response);
  const read=reportBlob('r1');const failed=expect(read).rejects.toThrow('工作区已切换');
  await waitFor(()=>expect(finish).toBeDefined());desk('c');finish(new Blob(['private']));await failed;
});

it('clears old workspace rows and ignores late results; theme updates do not reload',async()=>{
  desk();let finish!:(r:Response)=>void;
  vi.mocked(fetch).mockImplementation(async(url)=>String(url).endsWith('research-archive')?index():json([report('new')]));
  vi.mocked(fetch).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve}));
  render(<MyReports/>);
  await act(async()=>{desk('b');notify()});
  await screen.findByText('new.pdf');
  const count=vi.mocked(fetch).mock.calls.length;
  await act(async()=>{bridge.config={...bridge.config,theme:'dark'};notify()});
  expect(fetch).toHaveBeenCalledTimes(count);
  await act(async()=>{finish(json([report('old')]))});
  expect(screen.queryByText('old.pdf')).toBeNull();
  expect(localStorage.setItem).not.toHaveBeenCalled();
});

it('stops a batch if identity changes while the file reader is pending',async()=>{
  desk();vi.mocked(fetch).mockImplementation(async(url)=>String(url).endsWith('research-archive')?index():json([]));
  let reader:any;
  vi.stubGlobal('FileReader',class {result='data:application/pdf;base64,dGVzdA==';onload:any;readAsDataURL(){reader=this}});
  render(<MyReports/>);
  await screen.findByText('没有符合条件的研究档案。');
  fireEvent.change(screen.getByLabelText('选择研报文件'),{target:{files:[new File(['x'],'a.pdf'),new File(['y'],'b.pdf')]}});
  await act(async()=>{desk('b');notify();reader.onload()});
  expect(vi.mocked(fetch).mock.calls.some(([,init])=>init?.method==='POST')).toBe(false);
});

it('reports partial upload success and failed refresh honestly',async()=>{
  desk();let uploaded=false;
  vi.mocked(fetch).mockImplementation(async(url,init)=>{
    if(init?.method==='POST'){if(uploaded)return new Response(null,{status:503});uploaded=true;return json(report())}
    return String(url).endsWith('research-archive')?index():json(uploaded?[report()]:[]);
  });
  vi.stubGlobal('FileReader',class {result='data:application/pdf;base64,dGVzdA==';onload:any;readAsDataURL(){queueMicrotask(()=>this.onload())}});
  render(<MyReports/>);await screen.findByText('没有符合条件的研究档案。');
  fireEvent.change(screen.getByLabelText('选择研报文件'),{target:{files:[new File(['x'],'a.pdf'),new File(['y'],'b.pdf')]}});
  await screen.findByText(/本批已确认保存 1\/2/);await screen.findByText('r1.pdf');
  expect(bridge.context().data.asOf).toBeUndefined();
  expect(bridge.context().actions.every((a:any)=>!a.available)).toBe(true);
  vi.mocked(fetch).mockResolvedValue(new Response(null,{status:503}));
  fireEvent.click(screen.getByText('刷新索引'));
  await waitFor(()=>expect(bridge.context().data.freshness).toBe('stale'));
  expect(screen.getByText('r1.pdf')).toBeTruthy();
});

it('keeps the visible document and selection after deletion fails',async()=>{
  desk();vi.stubGlobal('confirm',()=>true);
  vi.mocked(fetch).mockImplementation(async(url,init)=>{
    if(init?.method==='DELETE')return new Response(JSON.stringify({code:'REPORT_STORAGE_UNAVAILABLE'}),{status:503});
    return String(url).endsWith('research-archive')?index():json([report()]);
  });
  render(<MyReports/>);
  fireEvent.click(await screen.findByText('r1.pdf'));
  const selected=bridge.context().selection;
  fireEvent.click(screen.getByTitle('删除'));
  await screen.findByText(/资料库读写异常/);
  expect(screen.getByText('r1.pdf')).toBeTruthy();
  expect(bridge.context().selection).toEqual(selected);
  expect(bridge.context().data.freshness).toBe('stale');
  expect(vi.mocked(fetch).mock.calls.filter(([,init])=>init?.method==='DELETE')).toHaveLength(1);
});

it('offers an authorized PDF download in sandboxed Desk and revokes it on workspace switch',async()=>{
  desk();vi.mocked(fetch).mockResolvedValue(new Response('synthetic pdf',{headers:{'Content-Type':'application/pdf'}}));
  const create=vi.fn(()=> 'blob:synthetic'),revoke=vi.fn();
  vi.stubGlobal('URL',class extends URL {static createObjectURL=create;static revokeObjectURL=revoke});
  Object.defineProperty(HTMLDialogElement.prototype,'showModal',{configurable:true,value:function(){this.setAttribute('open','')}});
  Object.defineProperty(HTMLDialogElement.prototype,'close',{configurable:true,value:function(){this.removeAttribute('open')}});
  render(<p><ReportSourceLink href="/api/myreports/file/r1?inline=true#page=3">核对原页</ReportSourceLink></p>);
  fireEvent.click(screen.getByText('核对原页'));
  await waitFor(()=>expect(screen.getByText('下载已授权原文').getAttribute('href')).toBe('blob:synthetic'));
  expect(screen.queryByTitle('研报 PDF 原文')).toBeNull();
  expect(fetch).toHaveBeenCalledWith('http://desk.test/api/research/myreports/file/r1',expect.objectContaining({headers:expect.objectContaining({Authorization:'Bearer test-token'})}));
  await act(async()=>{desk('b');notify()});
  expect(screen.queryByText('下载已授权原文')).toBeNull();expect(revoke).toHaveBeenCalledWith('blob:synthetic');
});
