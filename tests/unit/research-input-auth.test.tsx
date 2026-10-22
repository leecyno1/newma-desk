// @vitest-environment jsdom
import {cleanup, waitFor} from '@testing-library/react';
import {afterEach, beforeEach, expect, it, vi} from 'vitest';
import {earningsInputScope, loadSavedEarningsInputs} from '@/lib/valuationInputs';

const bridge = vi.hoisted(() => ({config: null as any}));
vi.mock('@/lib/vibedesk', () => ({getVibeDeskConfig:()=>bridge.config,waitForVibeDeskConfig:async()=>bridge.config}));
const book = {id:'synthetic',security:{symbol:'000001',name:'合成资料',market:'CN',currency:'CNY'},
  fiscalPeriod:{periodEnd:'2025-12-31',basis:'annual'},metrics:[],sourceMaterials:[]};
const payload = {revision:2,workbooks:[book]};
const response = () => new Response(JSON.stringify(payload));
function valuationConfig() {return {apiOrigin:'https://desk.test',userId:'u',workspaceId:'w',moduleId:'valuation-workbench',instanceId:'frame',accessToken:'synthetic-token',permissions:['storage.read']};}
beforeEach(()=>{bridge.config=valuationConfig();vi.stubGlobal('fetch',vi.fn().mockImplementation(async()=>response()));});
afterEach(()=>{cleanup();vi.unstubAllGlobals();vi.restoreAllMocks();});

it('valuation reads only with a signed session and ignores theme-only changes',async()=>{
  const scope=earningsInputScope();bridge.config={...bridge.config,theme:'dark'};
  expect(earningsInputScope()).toBe(scope);
  expect(await loadSavedEarningsInputs()).toEqual([book]);
  expect(fetch).toHaveBeenCalledWith('https://desk.test/api/research-archive/earnings-inputs',expect.objectContaining({
    headers:{Authorization:'Bearer synthetic-token','X-Newma-Desk-Instance-Id':'frame'},cache:'no-store'}));
  for(const invalid of [null,{...valuationConfig(),accessToken:undefined},{...valuationConfig(),permissions:[]},{...valuationConfig(),moduleId:'research-memo'}]){
    bridge.config=invalid;await expect(loadSavedEarningsInputs()).rejects.toThrow();
  }
  expect(fetch).toHaveBeenCalledTimes(1);
});

it('valuation rejects a body arriving after instance change or cancellation',async()=>{
  let finish!:(data:any)=>void;
  vi.mocked(fetch).mockResolvedValue({ok:true,json:()=>new Promise(resolve=>{finish=resolve})} as Response);
  const controller=new AbortController();
  const read=loadSavedEarningsInputs(controller.signal);const reject=expect(read).rejects.toThrow('实例已变化');
  await waitFor(()=>expect(finish).toBeDefined());bridge.config={...bridge.config,instanceId:'new-frame'};finish(payload);await reject;
  controller.abort();await expect(loadSavedEarningsInputs(controller.signal)).rejects.toThrow();
  expect(fetch).toHaveBeenCalledTimes(1);
});

it('valuation rejects malformed or failed reads instead of adopting an empty result',async()=>{
  for(const data of [{revision:1,workbooks:null},{revision:1,workbooks:[null]},{revision:-1,workbooks:[]}]){
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify(data)));
    await expect(loadSavedEarningsInputs()).rejects.toThrow('格式异常');
  }
  vi.mocked(fetch).mockResolvedValue(new Response('private backend text',{status:403}));
  await expect(loadSavedEarningsInputs()).rejects.toThrow('底稿读取失败');
});

