// @vitest-environment jsdom
import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import { canRefreshResearchData, fetchFinancialEvidence, fetchValuationPrice, fetchPeerSnapshot } from '@/lib/researchData';
import { api } from '@/lib/api';

const bridge = vi.hoisted(() => ({ config: null as any, embedded: false }));
vi.mock('@/lib/vibedesk', () => ({ getVibeDeskConfig: () => bridge.config, get isVibeDeskEmbedded() { return bridge.embedded; } }));
const data = { basis: 'annual', period: '2025-12-31', revenue: '0亿元', net_profit: null };
function desk(moduleId = 'earnings-workbench') {
  bridge.embedded = true;
  bridge.config = { moduleId, apiOrigin: 'https://desk.test', userId: 'alice', workspaceId: 'one', instanceId: 'one', accessToken: 'test-only', permissions: ['market.read'] };
}
beforeEach(() => { bridge.config = null; bridge.embedded = false; vi.stubGlobal('fetch', vi.fn()); });
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.restoreAllMocks(); });

it('Desk取数复用已签名Action，零值与缺失保留，不发送原生密钥', async () => {
  desk(); const readKey = vi.fn(() => 'native-only'); vi.stubGlobal('localStorage', { getItem: readKey });
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ data })));
  expect(await fetchFinancialEvidence('600519', 'annual')).toEqual(data);
  const [url, init] = vi.mocked(fetch).mock.calls[0];
  expect(url).toBe('https://desk.test/api/mods/earnings-workbench/actions/earnings.fetch-financials');
  const headers = new Headers(init?.headers);
  expect(headers.get('Authorization')).toBe('Bearer test-only');
  expect(headers.get('X-Newma-Desk-Instance-Id')).toBe('one');
  expect(init).toMatchObject({ credentials: 'omit', redirect: 'error', cache: 'no-store' });
  expect(JSON.parse(String(init?.body))).toEqual({ code: '600519', basis: 'annual' });
  expect(readKey).not.toHaveBeenCalled();
});

it('嵌入/集成构建缺授权、错误模块或缺权限均拒绝，不回退匿名原生API', async () => {
  bridge.embedded = true;
  await expect(fetchFinancialEvidence('600519', 'annual')).rejects.toThrow('授权');
  bridge.embedded = false; vi.stubEnv('VITE_NEWMA_DESK_INTEGRATED', '1');
  expect(canRefreshResearchData('earnings-workbench')).toBe(false);
  await expect(fetchFinancialEvidence('600519', 'annual')).rejects.toThrow('授权');
  desk('valuation-workbench');
  await expect(fetchFinancialEvidence('600519', 'annual')).rejects.toThrow('授权');
  desk(); bridge.config.permissions = [];
  await expect(fetchFinancialEvidence('600519', 'annual')).rejects.toThrow('授权');
  expect(fetch).not.toHaveBeenCalled();
});

it.each(['workspaceId', 'accessToken', 'permissions'])('JSON读取后%s变化也拒绝旧结果', async field => {
  desk(); let finish!: (value: unknown) => void;
  vi.mocked(fetch).mockResolvedValue({ ok: true, json: () => new Promise(resolve => { finish = resolve; }) } as Response);
  const pending = fetchFinancialEvidence('600519', 'annual');
  await vi.waitFor(() => expect(finish).toBeTypeOf('function'));
  bridge.config[field] = field === 'permissions' ? [] : 'changed';
  finish({ data });
  await expect(pending).rejects.toThrow('工作区或授权已变化');
});

it('接口失败不透传内部响应、不自动重试', async () => {
  desk(); vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ detail: 'secret upstream path' }), { status: 502 }));
  await expect(fetchFinancialEvidence('600519', 'annual')).rejects.toThrow('HTTP 502');
  expect(fetch).toHaveBeenCalledTimes(1);
});

it('取消读取后拒绝迟到数据，估值响应缺身份也拒绝', async () => {
  desk(); const cancel = new AbortController(); let finish!: (value: Response) => void;
  vi.mocked(fetch).mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  const pending = fetchFinancialEvidence('600519', 'annual', cancel.signal);
  cancel.abort(); finish(new Response(JSON.stringify({ data })));
  await expect(pending).rejects.toThrow('已停止');
  desk('valuation-workbench'); vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ data: {} })));
  await expect(fetchValuationPrice('600519')).rejects.toThrow('身份或证据');
});

it('原生独立模式保留自己的接口，传递可取消信号', async () => {
  vi.spyOn(api, 'financials').mockResolvedValue(data as any);
  expect(await fetchFinancialEvidence('600519', 'annual')).toEqual(data);
  expect(api.financials).toHaveBeenCalledWith('600519', 'annual', expect.any(AbortSignal));
});

it('同业通过本页签名Action获取单一证券快照，缺身份拒绝', async () => {
  desk('peer-comparison');
  const snapshot = { identity: { symbol: '00700', market: 'HK', currency: 'HKD', name: '测试公司' }, evidenceLedger: [] };
  vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ data: snapshot })))
    .mockResolvedValueOnce(new Response(JSON.stringify({ data: { evidenceLedger: [] } })));
  expect(await fetchPeerSnapshot('00700.HK')).toEqual(snapshot);
  expect(vi.mocked(fetch).mock.calls[0][0]).toBe('https://desk.test/api/mods/peer-comparison/actions/peer.fetch-snapshot');
  expect(JSON.parse(String(vi.mocked(fetch).mock.calls[0][1]?.body))).toEqual({ symbol: '00700.HK' });
  await expect(fetchPeerSnapshot('00700.HK')).rejects.toThrow('证券身份');
});
