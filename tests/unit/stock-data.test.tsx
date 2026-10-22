// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { StockData } from '@/pages/StockData';
import { api, ApiError } from '@/lib/api';

const bridge = vi.hoisted(() => ({
  context: undefined as undefined | (() => any),
  select: undefined as undefined | ((event: any) => void),
  cache: new Map<string, any>(),
}));
vi.mock('@/lib/vibedesk', () => ({
  createVibeDeskSnapshotCache: (key: string) => ({
    read: () => bridge.cache.has(key) ? { value: bridge.cache.get(key) } : null,
    write: (value: any) => bridge.cache.set(key, value),
  }),
  emitVibeDeskEvent: vi.fn(), publishVibeDeskContext: vi.fn(),
  registerVibeDeskContextProvider: (fn: () => any) => { bridge.context = fn; return () => {}; },
  subscribeVibeDeskEvent: (fn: (event: any) => void) => { bridge.select = fn; return () => {}; },
  subscribeVibeDeskConfig: () => () => {}, registerVibeDeskHandoffHandler: () => () => {},
}));
vi.mock('@/lib/api', async (original) => {
  const actual = await original<typeof import('@/lib/api')>();
  const names = ['valuation','reports','news','percentile','financials','announcements','margin','blockTrade','holders','dividend','fundFlow','dragonTiger','lockup','blocks','hotConcepts','investorQa','equityResearch','globalStock'];
  return { ...actual, api: Object.fromEntries(names.map(name => [name, vi.fn()])) };
});
vi.mock('@/lib/researchHistory', () => ({ persistEquityResearchHistory: async (s: any) => s, loadEquityResearchHistory: async () => [] }));
vi.mock('@/components/equity/EquityResearchFramework', () => ({ EquityResearchFramework: () => <div>研究证据面板</div> }));
vi.mock('@/components/equity/EquityPeerComparison', () => ({ EquityPeerComparison: () => null }));

const quote = { code:'300502', name:'测试公司甲', price:100, mcap_yi:10, pe_ttm:20, pb:2, analyst_count:0, eps_26e:null, eps_27e:null, pe_26e:null, cagr_pct:null, peg:null, digest_years:null };
function deferred<T>() { let resolve!: (value: T) => void; const promise = new Promise<T>(r => { resolve = r; }); return { promise, resolve }; }
async function query(symbol = '300502') {
  fireEvent.change(screen.getByRole('textbox'), { target:{value:symbol} });
  fireEvent.click(screen.getByRole('button', { name:'查询' }));
  await waitFor(() => expect(bridge.context?.().data.summary.loading).toBe(false));
}
function sourceRow(label: string) { return within(screen.getByRole('region', { name:'数据源覆盖' })).getByRole('row', { name: new RegExp(label) }); }

beforeEach(() => {
  vi.resetAllMocks(); bridge.cache.clear(); bridge.context = undefined;
  for (const method of Object.values(api)) vi.mocked(method).mockResolvedValue([] as never);
  vi.mocked(api.valuation).mockResolvedValue(quote);
  for (const key of ['percentile','financials','globalStock'] as const) vi.mocked(api[key]).mockResolvedValue(null as never);
  vi.mocked(api.equityResearch).mockRejectedValue(new ApiError('internal upstream failure',502));
  vi.mocked(api.dragonTiger).mockResolvedValue({ records:[], seats:{buy:[],sell:[]}, institution:{buy_amt:0,sell_amt:0,net_amt:0} });
  vi.mocked(api.lockup).mockResolvedValue({ history:[],upcoming:[] });
  vi.mocked(api.blocks).mockResolvedValue({ total:0,boards:[],concept_tags:[] });
});
afterEach(cleanup);

describe('个股研究的独立来源与当前对象', () => {
  it('行情失败不阻挡公告、资金、新闻和研究面板，Context仍是A股', async () => {
    vi.mocked(api.valuation).mockRejectedValue(new ApiError('secret upstream URL',502));
    vi.mocked(api.announcements).mockResolvedValue([{title:'测试分红公告',date:'2026-10-19',type:'分红',url:''}]);
    vi.mocked(api.margin).mockResolvedValue([{date:'2026-10-19',rzye:100000000,rqye:0}]);
    vi.mocked(api.news).mockResolvedValue([{新闻标题:'测试有效新闻'}]);
    vi.mocked(api.equityResearch).mockResolvedValue({identity:{symbol:'300502'}} as never);
    render(<StockData />); await query();
    expect(screen.getByText('测试分红公告')).toBeTruthy();
    expect(screen.getByText('测试有效新闻')).toBeTruthy();
    expect(screen.getByText('融资余额')).toBeTruthy();
    expect(screen.getByText('研究证据面板')).toBeTruthy();
    expect(sourceRow('行情与估值').textContent).toContain('失败');
    expect(document.body.textContent).not.toContain('secret upstream URL');
    expect(bridge.context?.().selection).toMatchObject({symbol:'300502',market:'CN'});
    expect(bridge.context?.().data.summary.sourceStates.val.status).toBe('failed');
  });

  it('刷新失败保留旧记录并标明待更新；成功空结果才清空', async () => {
    vi.mocked(api.news).mockResolvedValue([{新闻标题:'上次新闻'}]);
    render(<StockData />); await query();
    vi.mocked(api.news).mockRejectedValueOnce(new ApiError('timeout',504));
    await query();
    expect(screen.getByText('上次新闻')).toBeTruthy();
    expect(sourceRow('个股新闻').textContent).toContain('保留上次结果');
    expect(bridge.context?.().data.summary.sourceStates.news).toMatchObject({status:'failed',retained:true});
    expect(bridge.context?.().data.freshness).toBe('stale');
    vi.mocked(api.news).mockResolvedValue([]); await query();
    expect(screen.queryByText('上次新闻')).toBeNull();
    expect(sourceRow('个股新闻').textContent).toContain('空结果');
    expect(bridge.context?.().data.summary.sourceStates.news).toMatchObject({status:'empty',retained:false});
  });

  it('编辑未提交的代码不改变Context对象；换股时迟到结果不能覆盖新证券', async () => {
    const old = deferred<any>(); vi.mocked(api.announcements).mockReturnValueOnce(old.promise);
    render(<StockData />);
    fireEvent.change(screen.getByRole('textbox'),{target:{value:'300502'}});
    fireEvent.click(screen.getByRole('button',{name:'查询'}));
    await waitFor(() => expect(screen.getByText('测试公司甲')).toBeTruthy());
    fireEvent.change(screen.getByRole('textbox'),{target:{value:'600519'}});
    expect(bridge.context?.().selection.symbol).toBe('300502');
    vi.mocked(api.valuation).mockResolvedValue({...quote,code:'600519',name:'测试公司乙'});
    vi.mocked(api.announcements).mockResolvedValue([{title:'新证券公告',date:'2026-10-19',type:'公告',url:''}]);
    await act(async () => { bridge.select?.({event:'security.selected',payload:{symbol:'600519'}}); });
    await waitFor(() => expect(screen.getByText('新证券公告')).toBeTruthy());
    await act(async () => { old.resolve([{title:'迟到的旧证券公告',date:'2026-10-19',type:'公告',url:''}]); });
    expect(screen.queryByText('迟到的旧证券公告')).toBeNull();
    expect(bridge.context?.().selection).toMatchObject({symbol:'600519',market:'CN'});
    expect(bridge.context?.().data.summary.sourceStates.anns.status).toBe('available');
  });

  it('资金接口尚未返回时明确加载中；零余额仍为有效记录，空龙虎榜不是失败', async () => {
    const pending = deferred<any>(); vi.mocked(api.margin).mockReturnValueOnce(pending.promise);
    render(<StockData />);
    fireEvent.change(screen.getByRole('textbox'),{target:{value:'300502'}});
    fireEvent.click(screen.getByRole('button',{name:'查询'}));
    await waitFor(() => expect(screen.getByText('测试公司甲')).toBeTruthy());
    expect(sourceRow('融资融券').textContent).toContain('加载中');
    expect(sourceRow('龙虎榜').textContent).toContain('空结果');
    await act(async () => { pending.resolve([{date:'2026-10-19',rzye:0,rqye:0}]); });
    expect(sourceRow('融资融券').textContent).toContain('已返回');
    expect(bridge.context?.().data.summary.margin.financingBalanceCny).toBe(0);
  });

  it('旧版缓存保留数据但不伪造获取时间，研究刷新失败仍显示旧面板及失败状态', async () => {
    vi.mocked(api.equityResearch).mockResolvedValueOnce({identity:{symbol:'300502'}, workflow:{task:{id:'old-task',status:'completed'}}} as never);
    render(<StockData />); await query(); cleanup();
    const cached = bridge.cache.get('stock-data:300502'); delete cached.sourceStates;
    vi.mocked(api.valuation).mockRejectedValue(new ApiError('bad',502));
    render(<StockData />); await query();
    expect(screen.getByText('研究证据面板')).toBeTruthy();
    expect(screen.getByText('研究流程未完成')).toBeTruthy();
    expect(sourceRow('行情与估值').textContent).toContain('未知');
    expect(bridge.context?.().data.summary.sourceStates.research).toMatchObject({status:'failed',retained:true,lastSuccessAt:null});
    expect(bridge.context?.().tasks[0].status).toBe('failed');
  });

  it('没有报价的韩股不冒充美股，也不沿用上一只A股数据', async () => {
    render(<StockData />); await query();
    vi.mocked(api.globalStock).mockRejectedValue(new ApiError('bad',502));
    await query('005930.KS');
    expect(screen.queryByText('测试公司甲')).toBeNull();
    expect(bridge.context?.().selection).toMatchObject({symbol:'005930.KS',market:'KR'});
    expect(bridge.context?.().wiki).toBeUndefined();
    expect(Object.keys(bridge.context?.().data.summary.sourceStates)).toEqual(['gstock','research']);
    expect(sourceRow('海外行情与财务').textContent).toContain('失败');
    expect(bridge.context?.().data.summary.sourceStates.gstock.retained).toBe(false);
  });
});
