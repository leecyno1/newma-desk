// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { blankPeerComparisonCase, emptyPeerComparisonWorkspace, hydratePeerComparisonWorkspace, persistPeerComparisonWorkspace } from '@/lib/peerComparison';
import { PeerComparison } from '@/pages/PeerComparison';
import { peerRowFromSnapshot } from '@/lib/peerReview';

const bridge = vi.hoisted(() => ({ config: null as any, embedded: false, changed: undefined as any, context: undefined as any, action: undefined as any }));
vi.mock('@/lib/vibedesk', () => ({
  getVibeDeskConfig: () => bridge.config, waitForVibeDeskConfig: async () => bridge.config,
  get isVibeDeskEmbedded() { return bridge.embedded; },
  subscribeVibeDeskConfig: (fn: any) => { bridge.changed = fn; return () => {}; },
  subscribeVibeDeskEvent: () => () => {},
  registerVibeDeskUiActionHandler: (fn: any) => { bridge.action = fn; return () => { bridge.action = undefined; }; },
  registerVibeDeskContextProvider: (fn: any) => { bridge.context = fn; return () => {}; },
  publishVibeDeskContext: vi.fn(),
}));
const key = 'newma-desk.peer-comparison.v1';
let storage: Map<string, string>;
function workspace(name = '已存比较') {
  const draft = blankPeerComparisonCase(); draft.id = 'peer-1'; draft.name = name;
  draft.members.forEach((member, index) => { member.security = { market: 'CN', symbol: ['600519', '000858', '600809'][index], name: ['目标', '甲', '乙'][index], currency: 'CNY' }; });
  draft.target = draft.members[0].security;
  draft.rows = draft.members.map((member, index) => peerRowFromSnapshot(member, snapshot(member.security, index)));
  return { ...emptyPeerComparisonWorkspace(), cases: [draft] };
}
function snapshot(identity: any, index = 0): any {
  return { identity, evidenceLedger: [{ id: 'growth.revenue_yoy', value: [100, 0, 20][index], source: 'synthetic-test', asOf: '2025-12-31', unit: '%' }], gaps: [] };
}
function desk(workspaceId = 'a') {
  bridge.embedded = true;
  bridge.config = { moduleId: 'peer-comparison', apiOrigin: 'http://desk.test', storageGateway: 'http://desk.test/storage', userId: 'test-user', workspaceId, instanceId: workspaceId, accessToken: 'test-only', permissions: ['storage.read', 'storage.write', 'market.read'] };
}
function response(value = workspace(), revision = 7) { return new Response(JSON.stringify({ value, revision })); }
beforeEach(() => {
  bridge.config = null; bridge.embedded = false; bridge.changed = undefined; bridge.context = undefined;
  storage = new Map();
  vi.stubGlobal('localStorage', { getItem: (k: string) => storage.get(k) ?? null, setItem: (k: string, v: string) => storage.set(k, v) });
  vi.stubGlobal('fetch', vi.fn());
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; };
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it('保留原修订号，409不重试或转存本机；只读禁止写入', async () => {
  desk(); vi.mocked(fetch).mockResolvedValueOnce(response()).mockResolvedValueOnce(new Response(null, { status: 409 }));
  const session = await hydratePeerComparisonWorkspace();
  await expect(persistPeerComparisonWorkspace(workspace('修改'), session)).rejects.toThrow('保存冲突');
  expect(JSON.parse(String(vi.mocked(fetch).mock.calls[1][1]?.body)).expectedRevision).toBe(7);
  expect(fetch).toHaveBeenCalledTimes(2); expect(storage.size).toBe(0);
  bridge.config.permissions = ['storage.read'];
  vi.mocked(fetch).mockResolvedValueOnce(response());
  const readonly = await hydratePeerComparisonWorkspace();
  await expect(persistPeerComparisonWorkspace(workspace(), readonly)).rejects.toThrow('保存权限');
  expect(fetch).toHaveBeenCalledTimes(3);
});
it('Desk空库或故障不混用本机旧缓存，坏库不得当空库', async () => {
  storage.set(key, JSON.stringify(workspace('本机旧档'))); desk();
  vi.mocked(fetch).mockResolvedValueOnce(new Response(null, { status: 404 })).mockResolvedValueOnce(new Response(null, { status: 503 }));
  expect((await hydratePeerComparisonWorkspace()).workspace.cases).toEqual([]);
  await expect(hydratePeerComparisonWorkspace()).rejects.toThrow('未使用本机');
  bridge.config = null; bridge.embedded = false; storage.set(key, '{broken');
  await expect(hydratePeerComparisonWorkspace()).rejects.toThrow('读取失败');
});
it('原生保存回读、旧窗口冲突；未纳入的空白公司不会丢失或妨碍保存', async () => {
  const first = await hydratePeerComparisonWorkspace(); const data = workspace();
  data.cases[0].members[2].included = false;
  data.cases[0].members[2].security = { ...data.cases[0].members[2].security, symbol: '', name: '' };
  const saved = await persistPeerComparisonWorkspace(data, first);
  expect(saved.workspace.cases[0].members).toHaveLength(3);
  expect((await hydratePeerComparisonWorkspace()).workspace.cases[0].name).toBe('已存比较');
  await expect(persistPeerComparisonWorkspace(workspace('旧稿'), first)).rejects.toThrow('保存冲突');
});
it('回读的统计与当前纳入样本一致，不恢复旧的全样本统计', async () => {
  const data = workspace(); data.cases[0].members[2].included = false;
  storage.set(key, JSON.stringify(data));
  const loaded = await hydratePeerComparisonWorkspace();
  expect(loaded.workspace.cases[0].statistics.revenueGrowthPct.median).toBeNull();
});
it('逐指标证据结构损坏不让页面崩溃，也不静默删记录', async () => {
  const data = workspace(); (data.cases[0].rows[0].metricEvidence!.revenueGrowthPct as any).asOf = 20251231;
  storage.set(key, JSON.stringify(data));
  await expect(hydratePeerComparisonWorkspace()).rejects.toThrow('不完整');
});
it('保存失败保留草稿与档案列表，重新读取须确认，取消不丢稿', async () => {
  desk(); vi.mocked(fetch).mockResolvedValueOnce(response()).mockResolvedValueOnce(new Response(null, { status: 409 })).mockResolvedValueOnce(response(workspace('对方新版'), 8));
  render(<PeerComparison/>); await screen.findByDisplayValue('已存比较');
  fireEvent.change(screen.getByLabelText('比较名称'), { target: { value: '我的未保存稿' } });
  fireEvent.click(screen.getByRole('button', { name: '保存', exact: true }));
  await screen.findByRole('alert');
  expect(screen.getByDisplayValue('我的未保存稿')).toBeTruthy();
  expect(screen.getByRole('button', { name: /已存比较 CN:600519/ })).toBeTruthy();
  expect((screen.getByRole('button', { name: '保存', exact: true }) as HTMLButtonElement).disabled).toBe(true);
  const exported = JSON.parse(decodeURIComponent(screen.getByRole('link', { name: '导出当前草稿' }).getAttribute('href')!.split(',')[1]));
  expect(exported.draft.name).toBe('我的未保存稿');
  fireEvent.click(screen.getByRole('button', { name: '重新读取档案' })); fireEvent.click(screen.getByRole('button', { name: '取消操作' }));
  expect(fetch).toHaveBeenCalledTimes(2);
  fireEvent.click(screen.getByRole('button', { name: '重新读取档案' })); fireEvent.click(screen.getByRole('button', { name: '确认继续' }));
  await screen.findByDisplayValue('对方新版'); expect(bridge.context().filters.unsavedChanges).toBe(false);
});
it('Agent核对与页面读取同一当前集合，修改后旧分析失效，不自动写库', async () => {
  desk(); vi.mocked(fetch).mockResolvedValueOnce(response());
  render(<PeerComparison/>); await screen.findByDisplayValue('已存比较');
  fireEvent.click(screen.getByLabelText('纳入公司3'));
  expect(bridge.context().data.summary.statistics.revenueGrowthPct.median).toBeNull();
  let report: any; await act(async () => { report = await bridge.action('peer.audit-comparability', {}); });
  expect(report.rows[0][1]).toBe('1/1'); expect(bridge.context().data.summary.currentAnalysis).toEqual(report);
  fireEvent.click(screen.getByLabelText('纳入公司3'));
  expect(bridge.context().data.summary.currentAnalysis).toBeNull(); expect(fetch).toHaveBeenCalledTimes(1);
  await expect(bridge.action('peer.audit-comparability', { save: true })).rejects.toThrow('不支持');
});
it('刷新部分失败明确报告并回读最新草稿；全失败保留旧结果；不重复提交', async () => {
  desk(); const data = workspace(); vi.mocked(fetch).mockResolvedValueOnce(response(data));
  render(<PeerComparison/>); await screen.findByDisplayValue('已存比较');
  let finish!: (response: Response) => void;
  vi.mocked(fetch).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ data: snapshot(data.cases[0].members[1].security, 1) })))
    .mockResolvedValueOnce(new Response(null, { status: 503 }));
  let refresh!: Promise<any>;
  act(() => { refresh = bridge.action('peer.refresh', {}); });
  await waitFor(() => expect(finish).toBeTypeOf('function'));
  await expect(bridge.action('peer.refresh', {})).rejects.toThrow();
  let result: any;
  await act(async () => { finish(new Response(JSON.stringify({ data: snapshot(data.cases[0].target) }))); result = await refresh; });
  expect(result).toMatchObject({ status: 'partial', received: 2, requested: 3, saved: false });
  expect(bridge.context().data.summary.rows).toHaveLength(2);
  expect(bridge.context().data.summary.sources.every((row: any) => row.status === 'available')).toBe(true);
  const rows = bridge.context().data.summary.rows;
  vi.mocked(fetch).mockImplementation(async () => new Response(null, { status: 503 }));
  await act(async () => { await expect(bridge.action('peer.refresh', {})).rejects.toThrow('旧比较保留'); });
  expect(bridge.context().data.summary.rows).toEqual(rows); expect(bridge.context().tasks).toEqual([]);
  expect(fetch).toHaveBeenCalledTimes(7); expect(storage.size).toBe(0);
});
it('工作区切换隔离迟到回执，主题变化不清草稿', async () => {
  desk(); vi.mocked(fetch).mockResolvedValueOnce(response());
  render(<PeerComparison/>); await screen.findByDisplayValue('已存比较');
  fireEvent.change(screen.getByLabelText('比较名称'), { target: { value: 'A草稿' } });
  act(() => { bridge.config = { ...bridge.config, theme: 'light' }; bridge.changed(); });
  expect(screen.getByDisplayValue('A草稿')).toBeTruthy(); expect(fetch).toHaveBeenCalledTimes(1);
  let finish!: (response: Response) => void;
  vi.mocked(fetch).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; })).mockResolvedValueOnce(response(workspace('B工作区')));
  fireEvent.click(screen.getByRole('button', { name: '保存', exact: true }));
  await waitFor(() => expect(finish).toBeTypeOf('function'));
  act(() => { desk('b'); bridge.changed(); }); await screen.findByDisplayValue('B工作区');
  await act(async () => finish(response(workspace('A迟到稿'), 8)));
  expect(screen.getByDisplayValue('B工作区')).toBeTruthy(); expect(screen.queryByDisplayValue('A迟到稿')).toBeNull();
});
