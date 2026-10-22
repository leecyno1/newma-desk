// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { parseResearchBackup, readLegacyResearchBackup, recoverEarningsBackup, recoverValuationBackup } from '@/lib/researchBackup';
import { blankEarningsWorkbook, emptyEarningsWorkspace } from '@/lib/earningsWorkbench';
import { blankValuationModel, emptyValuationWorkspace } from '@/lib/valuationWorkbench';
import { ResearchBackupRecovery } from '@/components/ResearchBackupRecovery';
import { EarningsWorkbench } from '@/pages/EarningsWorkbench';
import { ValuationWorkbench } from '@/pages/ValuationWorkbench';

const bridge = vi.hoisted(() => ({ config: null as any, embedded: false, listeners: new Set<() => void>(), context: undefined as any }));
vi.mock('@/lib/vibedesk', () => ({
  getVibeDeskConfig: () => bridge.config, waitForVibeDeskConfig: async () => bridge.config,
  get isVibeDeskEmbedded() { return bridge.embedded; },
  subscribeVibeDeskConfig: (fn: () => void) => { bridge.listeners.add(fn); return () => bridge.listeners.delete(fn); },
  subscribeVibeDeskEvent: () => () => {},
  registerVibeDeskUiActionHandler: () => () => {},
  registerVibeDeskContextProvider: (fn: any) => { bridge.context = fn; return () => {}; },
  publishVibeDeskContext: vi.fn(), requestVibeDeskAgent: vi.fn(),
}));
const security = { market: 'CN', symbol: 'TEST', name: '合成备份公司', currency: 'CNY' };
const earnings = () => ({ ...blankEarningsWorkbook(), security, headline: '合成备份判断', fiscalPeriod: { ...blankEarningsWorkbook().fiscalPeriod, label: '2025 年报' } });
const valuation = () => ({ ...blankValuationModel(), security, name: '合成备份模型' });
let storage: Map<string, string>;
beforeEach(() => {
  bridge.config = null; bridge.embedded = false; bridge.listeners.clear(); bridge.context = undefined;
  storage = new Map();
  vi.stubGlobal('localStorage', { getItem: vi.fn((k: string) => storage.get(k) ?? null), setItem: vi.fn((k: string, v: string) => storage.set(k, v)) });
  vi.stubGlobal('fetch', vi.fn());
  vi.stubGlobal('URL', class extends URL { static createObjectURL = vi.fn(() => 'blob:test'); static revokeObjectURL = vi.fn(); });
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; };
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });
function openRecovery() { fireEvent.click(screen.getByRole('button', { name: '恢复旧备份 / 导入草稿' })); }
async function upload(data: unknown) {
  const raw = typeof data === 'string' ? data : JSON.stringify(data);
  const file = new File([raw], 'synthetic-backup.json', { type: 'application/json' });
  Object.defineProperty(file, 'text', { value: async () => raw });
  fireEvent.change(screen.getByLabelText('选择研究备份 JSON'), { target: { files: [file] } });
  await screen.findByText('预览来源：synthetic-backup.json');
}
function confirmRecovery() {
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.click(screen.getByRole('button', { name: '恢复所选记录到新草稿' }));
}
function desk(kind: 'earnings' | 'valuation', workspaceId = 'a') {
  bridge.embedded = true;
  bridge.config = { moduleId: `${kind}-workbench`, apiOrigin: 'http://desk.test', storageGateway: 'http://desk.test/storage', userId: 'test-user', workspaceId, instanceId: workspaceId, accessToken: 'test-only', permissions: ['storage.read', 'storage.write'] };
}

describe('研究备份解析与恢复', () => {
  it('财报保留实际值与原始候选，恢复新身份但不沿用核验', () => {
    const workbook = earnings(); workbook.metrics[0].reported = 123;
    workbook.verification.status = 'verified'; workbook.verification.latestPeriodChecked = true;
    workbook.sourceMaterials = [{ id: 's1', label: '合成原件', kind: 'filing', status: 'verified', url: 'https://example.com/report.pdf', asOf: '2025-12-31' }];
    const raw = JSON.stringify({ workbook, pendingEvidence: { candidate: 999 }, pendingUpload: { selected: ['revenue'] }, correction: { after: 888 } });
    const parsed = parseResearchBackup(raw, 'earnings'), recovered = recoverEarningsBackup(parsed.rows[0]);
    expect(parsed.raw).toBe(raw); expect(parsed.warnings.join()).toContain('不自动写入实际值');
    expect(recovered.id).not.toBe(workbook.id); expect(recovered.metrics[0].reported).toBe(123);
    expect(recovered.verification).toMatchObject({ status: 'unverified', latestPeriodChecked: false });
    expect(recovered.sourceMaterials[0]).toMatchObject({ status: 'stale', asOf: '2025-12-31' });
    expect(workbook.verification.status).toBe('verified');
  });
  it('估值资本编辑作为待核验草稿恢复，不修改金额或沿用情景确认', () => {
    const model = valuation(); model.capitalInputs.cashM = 50;
    model.scenarios[0].review = { confirmedAt: new Date().toISOString(), inputSnapshot: 'old' };
    const input = { title: '待补凭证', url: '', locator: '', excerpt: '尚未采用', method: '', lineItems: [{ id: 'l1', label: '', amountM: 99, treatment: 'add', locator: '', reason: '' }] };
    const parsed = parseResearchBackup(JSON.stringify({ model, unsavedCapitalEditor: { field: 'cashM', input } }), 'valuation');
    const recovered = recoverValuationBackup(parsed.rows[0]);
    expect(recovered.id).not.toBe(model.id); expect(recovered.capitalInputs.cashM).toBe(50);
    expect(recovered.capitalEvidenceDrafts?.cashM?.input).toEqual(input);
    expect(recovered.scenarios.every(scenario => !scenario.review)).toBe(true);
    expect(model.scenarios[0].review).toBeTruthy();
  });
  it('接受未完成草稿和旧全档案，拒绝错模块、残缺指标和重复档案', () => {
    expect(parseResearchBackup(JSON.stringify({ workbook: blankEarningsWorkbook() }), 'earnings').rows).toHaveLength(1);
    expect(parseResearchBackup(JSON.stringify({ model: blankValuationModel() }), 'valuation').rows).toHaveLength(1);
    expect(parseResearchBackup(JSON.stringify({ ...emptyValuationWorkspace(), models: [valuation()] }), 'valuation').rows).toHaveLength(1);
    const workbook = earnings(); const whole = { ...emptyEarningsWorkspace(), workbooks: [workbook] };
    expect(parseResearchBackup(JSON.stringify(whole), 'earnings').rows).toHaveLength(1);
    whole.workbooks.push(workbook);
    expect(() => parseResearchBackup(JSON.stringify(whole), 'earnings')).toThrow('重复');
    workbook.metrics.pop();
    expect(() => parseResearchBackup(JSON.stringify({ workbook }), 'earnings')).toThrow('核心指标');
    expect(() => parseResearchBackup(JSON.stringify({ model: valuation() }), 'earnings')).toThrow();
    expect(() => parseResearchBackup('{broken', 'earnings')).toThrow('JSON');
  });
  it('拒绝可执行来源链接，不打开链接、不请求网络', () => {
    const workbook = earnings(); workbook.sourceMaterials = [{ id: 's1', label: '坏链接', kind: 'filing', status: 'available', url: 'javascript:alert(1)' }];
    expect(() => parseResearchBackup(JSON.stringify({ workbook }), 'earnings')).toThrow('HTTP');
    expect(fetch).not.toHaveBeenCalled();
  });
  it('显式读取仅当前工作区已知缓存，不自动枚举或写入', () => {
    desk('valuation');
    const key = 'newma-desk.valuation-workbench.v1:test-user:a';
    storage.set(key, JSON.stringify({ ...emptyValuationWorkspace(), models: [valuation()] }));
    render(<ResearchBackupRecovery kind="valuation" disabled={false} canRecover onRecover={vi.fn()}/>);
    openRecovery(); expect(localStorage.getItem).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: '读取当前工作区旧缓存' }));
    expect(localStorage.getItem).toHaveBeenCalledExactlyOnceWith(key);
    expect(localStorage.setItem).not.toHaveBeenCalled(); expect(fetch).not.toHaveBeenCalled();
    bridge.config.permissions = [];
    expect(() => readLegacyResearchBackup('valuation', true)).toThrow('当前估值工作区');
  });
  it('只预览不回填；坏文件保留前次预览，取消恢复可再次确认', async () => {
    const onRecover = vi.fn().mockResolvedValueOnce(false).mockResolvedValueOnce(true);
    render(<ResearchBackupRecovery kind="earnings" disabled={false} canRecover onRecover={onRecover}/>);
    openRecovery(); await upload({ workbook: earnings() });
    expect(onRecover).not.toHaveBeenCalled();
    await upload('bad'); await screen.findByRole('alert');
    expect(screen.getByText(/上次成功预览/)).toBeTruthy();
    confirmRecovery(); await waitFor(() => expect(onRecover).toHaveBeenCalledTimes(1));
    await waitFor(() => expect((screen.getByRole('button', { name: '恢复所选记录到新草稿' }) as HTMLButtonElement).disabled).toBe(false));
    fireEvent.click(screen.getByRole('button', { name: '恢复所选记录到新草稿' }));
    await screen.findByText(/已恢复为新的待保存草稿/);
    expect(localStorage.setItem).not.toHaveBeenCalled();
  });
});

describe.each(['earnings', 'valuation'] as const)('%s 页面恢复闭环', kind => {
  const itemKey = kind === 'earnings' ? 'workbook' : 'model';
  const itemsKey = kind === 'earnings' ? 'workbooks' : 'models';
  const field = kind === 'earnings' ? '公司名称' : '模型名称';
  const restoredName = kind === 'earnings' ? security.name : '合成备份模型';
  const item = () => kind === 'earnings' ? earnings() : valuation();
  const workspace = () => kind === 'earnings' ? emptyEarningsWorkspace() : emptyValuationWorkspace();
  const page = () => kind === 'earnings' ? <EarningsWorkbench/> : <ValuationWorkbench/>;
  it('恢复同编号旧档案为新副本，正常保存保留原档案，冲突保留新草稿', async () => {
    desk(kind); const original = item();
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ value: { ...workspace(), [itemsKey]: [original] }, revision: 7 })));
    vi.mocked(fetch).mockImplementationOnce(async (_url, init) => new Response(JSON.stringify({ value: JSON.parse(String(init?.body)).value, revision: 8 })));
    vi.mocked(fetch).mockResolvedValueOnce(new Response(null, { status: 409 }));
    render(page()); await screen.findByDisplayValue(restoredName);
    const loadedOriginal = JSON.parse(decodeURIComponent(screen.getByRole('link', { name: '导出当前草稿' }).getAttribute('href')!.split(',')[1]))[itemKey];
    openRecovery(); await upload({ [itemKey]: original }); confirmRecovery();
    await screen.findByText(/已恢复为新的待保存草稿/);
    expect(fetch).toHaveBeenCalledTimes(1); expect(bridge.context().filters.unsavedChanges).toBe(true);
    expect(bridge.context().data.summary.backupRecovery.id).toBe(original.id);
    fireEvent.click(screen.getByRole('button', { name: '保存', exact: true }));
    await waitFor(() => expect(bridge.context().data.summary.storage.revision).toBe(8));
    const body = JSON.parse(String(vi.mocked(fetch).mock.calls[1][1]?.body));
    expect(body.expectedRevision).toBe(7); expect(body.value[itemsKey]).toHaveLength(2);
    expect(body.value[itemsKey].find((record: any) => record.id === original.id)).toEqual(loadedOriginal);
    fireEvent.change(screen.getByLabelText(field), { target: { value: '恢复后未保存修改' } });
    fireEvent.click(screen.getByRole('button', { name: '保存', exact: true }));
    await screen.findByRole('alert');
    expect(screen.getByDisplayValue('恢复后未保存修改')).toBeTruthy();
    expect(fetch).toHaveBeenCalledTimes(3); expect(localStorage.setItem).not.toHaveBeenCalled();
  });
  it('未存修改取消恢复仍保留，确认后才换新稿', async () => {
    render(page()); await screen.findByText('仅使用本机浏览器档案，未同步到 Desk');
    fireEvent.change(screen.getByLabelText(field), { target: { value: '不能丢的输入' } });
    openRecovery(); await upload({ [itemKey]: item() }); confirmRecovery();
    fireEvent.click(screen.getByRole('button', { name: '取消操作' }));
    await waitFor(() => expect(screen.queryByText('正在处理备份…')).toBeNull());
    expect(screen.getByDisplayValue('不能丢的输入')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: '恢复所选记录到新草稿' }));
    fireEvent.click(screen.getByRole('button', { name: '确认继续' }));
    await screen.findByDisplayValue(restoredName);
    expect(bridge.context().filters.unsavedChanges).toBe(true); expect(localStorage.setItem).not.toHaveBeenCalled();
  });
  it('只读可预览但不可回填，切工作区时旧文件读取不能复活', async () => {
    desk(kind); bridge.config.permissions = ['storage.read'];
    vi.mocked(fetch).mockImplementation(async () => new Response(JSON.stringify({ value: workspace(), revision: 7 })));
    render(page()); await screen.findByText(/修订 7 · 只读/);
    openRecovery(); await upload({ [itemKey]: item() }); fireEvent.click(screen.getByRole('checkbox'));
    expect((screen.getByRole('button', { name: '恢复所选记录到新草稿' }) as HTMLButtonElement).disabled).toBe(true);
    let finish!: (value: string) => void;
    const file = new File(['{}'], 'late.json'); Object.defineProperty(file, 'text', { value: () => new Promise<string>(resolve => { finish = resolve; }) });
    fireEvent.change(screen.getByLabelText('选择研究备份 JSON'), { target: { files: [file] } });
    act(() => { desk(kind, 'b'); bridge.listeners.forEach(fn => fn()); });
    await screen.findByText('已读取当前 Desk 工作区');
    await act(async () => finish(JSON.stringify({ [itemKey]: item() })));
    expect(screen.queryByText('预览来源：late.json')).toBeNull(); expect(screen.queryByDisplayValue(restoredName)).toBeNull();
  });
});
