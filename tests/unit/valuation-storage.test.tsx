// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { blankValuationModel, emptyValuationWorkspace, hydrateValuationWorkspace, persistValuationWorkspace } from '@/lib/valuationWorkbench';
import { ValuationWorkbench } from '@/pages/ValuationWorkbench';

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
const key = 'newma-desk.valuation-workbench.v1';
let storage: Map<string, string>;
function workspace(name = '已存模型') {
  return { ...emptyValuationWorkspace(), models: [{ ...blankValuationModel(), id: 'v1', name,
    security: { market: 'CN', symbol: 'TEST', name: '合成公司', currency: 'CNY' } }] };
}
function desk(workspaceId = 'a') {
  bridge.embedded = true;
  bridge.config = { moduleId: 'valuation-workbench', apiOrigin: 'http://desk.test', storageGateway: 'http://desk.test/storage', userId: 'test-user', workspaceId, instanceId: workspaceId, accessToken: 'test-only', permissions: ['storage.read', 'storage.write'] };
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

it('估值三项Agent核对使用当前模型、提交页面后回执，不自动保存或确认', async () => {
  desk(); bridge.config.permissions = ['storage.read'];
  vi.mocked(fetch).mockResolvedValueOnce(response());
  const page = render(<ValuationWorkbench/>);
  await screen.findByDisplayValue('已存模型');
  for (const id of ['valuation.audit-inputs', 'valuation.test-scenarios', 'valuation.explain-sensitivity']) {
    expect(bridge.context().actions.find((row: any) => row.id === id).available).toBe(true);
    let report: any;
    await act(async () => { report = await bridge.action(id, {}); });
    expect(screen.getByText(report.summary)).toBeTruthy();
    expect(bridge.context().data.summary.currentAnalysis).toEqual(report);
  }
  expect(bridge.context().data.summary.reviewStatus.ready).toBe(false);
  expect(fetch).toHaveBeenCalledTimes(1);
  fireEvent.change(screen.getByDisplayValue('已存模型'), { target: { value: '修改模型' } });
  expect(bridge.context().data.summary.currentAnalysis).toBeNull();
  await expect(bridge.action('valuation.test-scenarios', { confirm: true })).rejects.toThrow('不支持');
  await expect(bridge.action('valuation.refresh-evidence', {})).rejects.toThrow('授权');
  bridge.config.moduleId = 'earnings-workbench';
  await expect(bridge.action('valuation.test-scenarios', {})).rejects.toThrow('授权');
  page.unmount(); expect(bridge.action).toBeUndefined();
});

describe('估值持久化', () => {
  it('Agent刷新股价等实际结果再回执，匹配身份且保留假设，不自动保存', async () => {
    desk(); bridge.config.permissions.push('market.read');
    const snapshot = { identity: { symbol: 'TEST', market: 'CN', currency: 'CNY' },
      evidenceLedger: [{ id: 'valuation.price', label: '股价', value: 12, currency: 'CNY', asOf: '2026-10-19', source: 'synthetic-test' }] };
    vi.mocked(fetch).mockResolvedValueOnce(response()).mockResolvedValueOnce(new Response(JSON.stringify({ data: snapshot })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ data: { ...snapshot, identity: { ...snapshot.identity, symbol: 'OTHER' } } })));
    render(<ValuationWorkbench/>); await screen.findByDisplayValue('已存模型');
    const before = structuredClone(bridge.context().data.summary);
    let result: any;
    await act(async () => { result = await bridge.action('valuation.refresh-evidence', {}); });
    expect(result).toMatchObject({ status: 'draft-updated', currentPrice: 12, assumptionsChanged: false, saved: false });
    expect(bridge.context().data.summary.capitalInputs.currentPrice).toBe(12);
    expect(bridge.context().selection.currency).toBe('CNY');
    expect(bridge.context().data.summary.scenarios).toEqual(before.scenarios);
    expect(bridge.context().data.summary.historicals).toEqual(before.historicals);
    expect(bridge.context().data.summary.reviewStatus.ready).toBe(false);
    await act(async () => { await expect(bridge.action('valuation.refresh-evidence', {})).rejects.toThrow('行情证券或币种'); });
    expect(bridge.context().data.summary.capitalInputs.currentPrice).toBe(12);
    expect(bridge.context().tasks).toEqual([]); expect(storage.size).toBe(0);
    expect(fetch).toHaveBeenCalledTimes(3);
  });

  it('使用打开时版本，409不重读覆盖、不转存本机', async () => {
    desk(); vi.mocked(fetch).mockResolvedValueOnce(response()).mockResolvedValue(new Response(null, { status: 409 }));
    const session = await hydrateValuationWorkspace();
    await expect(persistValuationWorkspace(workspace('修改'), session)).rejects.toThrow('保存冲突');
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(JSON.parse(String(vi.mocked(fetch).mock.calls[1][1]?.body)).expectedRevision).toBe(7);
    expect(storage.size).toBe(0);
  });
  it('原生回读与旧窗口冲突，不把损坏档案当空库', async () => {
    const first = await hydrateValuationWorkspace();
    const saved = await persistValuationWorkspace(workspace(), first);
    expect(saved.mode).toBe('local');
    expect((await hydrateValuationWorkspace()).workspace.models[0].name).toBe('已存模型');
    await expect(persistValuationWorkspace(workspace('旧稿'), first)).rejects.toThrow('保存冲突');
    storage.set(key, '{broken');
    await expect(hydrateValuationWorkspace()).rejects.toThrow('读取失败');
    const broken = workspace(); broken.models.push(broken.models[0]);
    storage.set(key, JSON.stringify(broken));
    await expect(hydrateValuationWorkspace()).rejects.toThrow('不完整');
  });
  it('Desk空库或故障不读取旧缓存，未授权和错误Mod拒绝', async () => {
    storage.set(key, JSON.stringify(workspace('私人旧缓存'))); desk();
    vi.mocked(fetch).mockResolvedValueOnce(new Response(null, { status: 404 })).mockResolvedValueOnce(new Response(null, { status: 503 }));
    expect((await hydrateValuationWorkspace()).workspace.models).toEqual([]);
    await expect(hydrateValuationWorkspace()).rejects.toThrow('未使用本机');
    bridge.config.moduleId = 'research-memo';
    await expect(hydrateValuationWorkspace()).rejects.toThrow('尚未连接');
    bridge.config = null;
    await expect(hydrateValuationWorkspace()).rejects.toThrow('尚未连接');
    expect(fetch).toHaveBeenCalledTimes(2);
  });
  it('成功采用实际回执，低修订和格式错误不算成功', async () => {
    desk(); vi.mocked(fetch).mockResolvedValueOnce(response()).mockResolvedValueOnce(response(workspace('服务端回执'), 8));
    const session = await hydrateValuationWorkspace();
    const saved = await persistValuationWorkspace(workspace('提交稿'), session);
    expect(saved).toMatchObject({ revision: 8, workspace: { models: [{ name: '服务端回执' }] } });
    vi.mocked(fetch).mockResolvedValueOnce(response(workspace(), 8));
    await expect(persistValuationWorkspace(workspace(), saved)).rejects.toThrow('修订号异常');
    vi.mocked(fetch).mockResolvedValueOnce(response({ models: [] } as any, 9));
    await expect(persistValuationWorkspace(workspace(), saved)).rejects.toThrow('格式异常');
    expect(storage.size).toBe(0);
  });
  it('加载和解析回执期间身份变化，旧请求不得继续使用', async () => {
    desk(); vi.mocked(fetch).mockResolvedValueOnce(response());
    const session = await hydrateValuationWorkspace();
    let finish!: (value: unknown) => void;
    vi.mocked(fetch).mockResolvedValueOnce({ ok: true, status: 200, json: () => new Promise(resolve => { finish = resolve; }) } as Response);
    const pending = persistValuationWorkspace(workspace(), session);
    const rejected = expect(pending).rejects.toThrow('工作区');
    await waitFor(() => expect(finish).toBeTypeOf('function'));
    desk('b'); finish({ value: workspace(), revision: 8 });
    await rejected;
    await expect(persistValuationWorkspace(workspace(), session)).rejects.toThrow('工作区');
    expect(fetch).toHaveBeenCalledTimes(2);
  });
  it('只读不能保存，取消请求不发送写入', async () => {
    desk(); bridge.config.permissions = ['storage.read'];
    vi.mocked(fetch).mockResolvedValueOnce(response());
    const session = await hydrateValuationWorkspace();
    await expect(persistValuationWorkspace(workspace(), session)).rejects.toThrow('没有保存权限');
    const controller = new AbortController(); controller.abort();
    await expect(persistValuationWorkspace(workspace(), session, controller.signal)).rejects.toThrow();
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it('页面保存失败保留草稿和列表，禁重复提交，重新读取须确认', async () => {
    desk(); vi.mocked(fetch).mockResolvedValueOnce(response()).mockResolvedValueOnce(new Response(null, { status: 409 })).mockResolvedValueOnce(response(workspace('其他窗口新版'), 8));
    render(<ValuationWorkbench />); await screen.findByDisplayValue('已存模型');
    fireEvent.change(screen.getByLabelText('模型名称'), { target: { value: '本页未保存' } });
    fireEvent.click(screen.getByRole('button', { name: '保存', exact: true }));
    await screen.findByRole('alert');
    expect((screen.getByLabelText('模型名称') as HTMLInputElement).value).toBe('本页未保存');
    expect(screen.getByRole('button', { name: '已存模型 CN:TEST · 基准' })).toBeTruthy();
    expect((screen.getByRole('button', { name: '保存', exact: true }) as HTMLButtonElement).disabled).toBe(true);
    expect(bridge.context().filters.unsavedChanges).toBe(true);
    expect(bridge.context().data.summary.storage.status).toBe('error');
    const backup = JSON.parse(decodeURIComponent(screen.getByRole('link', { name: '导出当前草稿' }).getAttribute('href')!.split(',')[1]));
    expect(backup.model.name).toBe('本页未保存');
    fireEvent.click(screen.getByRole('button', { name: '重新读取档案' }));
    fireEvent.click(screen.getByRole('button', { name: '取消操作' }));
    expect(fetch).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole('button', { name: '重新读取档案' }));
    fireEvent.click(screen.getByRole('button', { name: '确认继续' }));
    await screen.findByDisplayValue('其他窗口新版');
    expect(bridge.context().filters.unsavedChanges).toBe(false);
  });
  it('读取与保存等待时锁定编辑，主题不重读，回执后更新修订', async () => {
    desk(); let finish!: (value: Response) => void;
    vi.mocked(fetch).mockResolvedValueOnce(response()).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    render(<ValuationWorkbench />); await screen.findByDisplayValue('已存模型');
    act(() => { bridge.config = { ...bridge.config, theme: 'light' }; bridge.changed(); });
    expect(fetch).toHaveBeenCalledTimes(1);
    fireEvent.change(screen.getByLabelText('模型名称'), { target: { value: '新模型名' } });
    fireEvent.click(screen.getByRole('button', { name: '保存', exact: true }));
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2));
    expect(screen.getByLabelText('模型名称').closest('fieldset')?.disabled).toBe(true);
    expect(screen.queryByText('Desk 已确认保存')).toBeNull();
    await act(async () => finish(response(workspace('新模型名'), 8)));
    await screen.findByText('Desk 已确认保存');
    expect(bridge.context().filters.unsavedChanges).toBe(false);
    expect(bridge.context().data.summary.storage.revision).toBe(8);
  });
  it('删除失败仍显示原模型，不把移除当作成功', async () => {
    desk(); vi.mocked(fetch).mockResolvedValueOnce(response()).mockResolvedValueOnce(new Response(null, { status: 503 }));
    render(<ValuationWorkbench />); await screen.findByDisplayValue('已存模型');
    fireEvent.click(screen.getByRole('button', { name: '删除当前估值模型' }));
    fireEvent.click(screen.getByRole('button', { name: '确认继续' }));
    await screen.findByRole('alert');
    expect((screen.getByLabelText('模型名称') as HTMLInputElement).value).toBe('已存模型');
    expect(screen.queryByText('模型已从 Desk 工作区移除')).toBeNull();
  });
  it.each(['read', 'write'])('切工作区隔离迟到%s结果', async operation => {
    desk(); let finish!: (value: Response) => void;
    if (operation === 'write') vi.mocked(fetch).mockResolvedValueOnce(response());
    vi.mocked(fetch).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; })).mockResolvedValueOnce(response(workspace('B工作区模型')));
    render(<ValuationWorkbench />);
    if (operation === 'write') {
      await screen.findByDisplayValue('已存模型');
      fireEvent.change(screen.getByLabelText('模型名称'), { target: { value: 'A草稿' } });
      fireEvent.click(screen.getByRole('button', { name: '保存', exact: true }));
    }
    await waitFor(() => expect(finish).toBeTypeOf('function'));
    act(() => { desk('b'); bridge.changed(); });
    await screen.findByDisplayValue('B工作区模型');
    await act(async () => finish(response(workspace('A迟到结果'), 8)));
    expect((screen.getByLabelText('模型名称') as HTMLInputElement).value).toBe('B工作区模型');
    expect(screen.queryByText('Desk 已确认保存')).toBeNull();
  });
  it('新草稿任意资本修改都提示未保存，导出包含未暂存编辑', async () => {
    render(<ValuationWorkbench />); await screen.findByText('仅使用本机浏览器档案，未同步到 Desk');
    fireEvent.change(screen.getByLabelText('总债务'), { target: { value: '123' } });
    expect(bridge.context().filters.unsavedChanges).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: '核验有息债务' }));
    const fields = screen.getByRole('group', { name: '资本来源编辑' }).querySelectorAll('input[type="text"],input:not([type]),textarea');
    expect(fields.length).toBeGreaterThan(0);
    fireEvent.change(fields[0], { target: { value: '未暂存的来源标题' } });
    const backup = JSON.parse(decodeURIComponent(screen.getByRole('link', { name: '导出当前草稿' }).getAttribute('href')!.split(',')[1]));
    expect(backup.model.capitalInputs.totalDebtM).toBe(123);
    expect(backup.unsavedCapitalEditor.input.title).toBe('未暂存的来源标题');
    expect(backup.unsavedCapitalEditor.dirty).toBe(true);
    fireEvent.click(screen.getByRole('button', { name: '新建', exact: true }));
    expect(screen.getByRole('dialog', { name: '估值操作确认' })).toBeTruthy();
  });
});
