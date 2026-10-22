// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { blankResearchIdea, emptyIdeaFunnelWorkspace, hydrateIdeaFunnelWorkspace, persistIdeaFunnelWorkspace } from '@/lib/ideaFunnel';
import { reviewIdea } from '@/lib/ideaReview';
import { buildIndexedResearchCoverage } from '@/lib/researchCoverage';
import { IdeaFunnel } from '@/pages/IdeaFunnel';
import type { ResearchArchiveIndex } from '@/lib/researchArchive';

const bridge = vi.hoisted(() => ({ config: null as any, embedded: false, changed: undefined as any, context: undefined as any, action: undefined as any }));
vi.mock('@/lib/vibedesk', () => ({
  getVibeDeskConfig: () => bridge.config, waitForVibeDeskConfig: async () => bridge.config,
  get isVibeDeskEmbedded() { return bridge.embedded; },
  subscribeVibeDeskConfig: (fn: any) => { bridge.changed = fn; return () => {}; },
  subscribeVibeDeskEvent: () => () => {},
  registerVibeDeskUiActionHandler: (fn: any) => { bridge.action = fn; return () => {}; },
  registerVibeDeskContextProvider: (fn: any) => { bridge.context = fn; return () => {}; },
  publishVibeDeskContext: vi.fn(),
}));
const key = 'newma-desk.idea-funnel.v1';
let storage: Map<string, string>;
function candidate() {
  const idea = blankResearchIdea();
  idea.id = 'idea-test'; idea.title = '合成测试线索'; idea.security = { market: 'CN', symbol: '000001', name: '测试公司', currency: 'CNY' };
  return idea;
}
function workspace() { return { ...emptyIdeaFunnelWorkspace(), ideas: [candidate()] }; }
function desk(workspaceId = 'a') {
  bridge.embedded = true;
  bridge.config = { moduleId: 'idea-funnel', apiOrigin: 'http://desk.test', gatewayOrigin: 'http://desk.test', storageGateway: 'http://desk.test/storage', userId: 'test-user', workspaceId, instanceId: workspaceId, accessToken: 'test-only', permissions: ['storage.read', 'storage.write'] };
}
function response(value = workspace(), revision = 3) { return new Response(JSON.stringify({ value, revision })); }
function completeIdea() {
  const idea = candidate();
  idea.researchQuestion = '订单能否转为现金流？'; idea.initialHypothesis = '需求恢复支持订单增长'; idea.opposingHypothesis = '增长可能来自提前备货';
  idea.whyNow = '中报披露后需要检查交付'; idea.marketMayMiss = '收入确认与回款存在时间差';
  idea.sources = [{ id: 'report', kind: 'filing', label: '合成中报', asOf: '2026-06-30', status: 'available', url: 'https://example.com/report' }];
  idea.signals = [ { id: 'up', type: 'quantitative', direction: 'supports', summary: '订单增长，等待核验口径', sourceIds: ['report'] },
    { id: 'down', type: 'risk', direction: 'challenges', summary: '应收账款增长快于收入', sourceIds: ['report'] } ];
  idea.risks = [{ id: 'risk', statement: '回款恶化', earlyWarning: '应收周转天数上升', falsificationCondition: '连续两季经营现金流为负', sourceIds: ['report'] }];
  idea.nextActions[0].label = '核对中报应收账款与现金流'; idea.nextActions[0].completionStandard = '记录报表页码、期间及现金流与利润的差额';
  return idea;
}
function archive(): ResearchArchiveIndex {
  return { schemaVersion: 'newma-desk.research-archive.v1', userId: 'test-user', workspaceId: 'a', generatedAt: '2026-10-20T01:00:00Z', unavailableSources: [], truncated: false, entries: [
    { id: 'archive:thesis-tracker:thesis-1', sourceModId: 'thesis-tracker', kind: 'thesis', artifactId: 'thesis-1', title: '真实存档索引测试', status: 'draft', security: candidate().security, updatedAt: '2026-10-20', sourceRevision: 1, tags: [] },
  ] };
}
beforeEach(() => {
  bridge.config = null; bridge.embedded = false;
  storage = new Map();
  vi.stubGlobal('localStorage', { getItem: (k: string) => storage.get(k) ?? null, setItem: (k: string, v: string) => storage.set(k, v) });
  vi.stubGlobal('fetch', vi.fn());
  HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  HTMLDialogElement.prototype.close = function () { this.open = false; };
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

it('线索允许不完整研究和零信号，原生保存回读且旧窗口不得覆盖', async () => {
  const session = await hydrateIdeaFunnelWorkspace(); const data = workspace(); data.ideas[0].signals = [];
  await persistIdeaFunnelWorkspace(data, session);
  expect((await hydrateIdeaFunnelWorkspace()).workspace.ideas[0].signals).toEqual([]);
  await expect(persistIdeaFunnelWorkspace(workspace(), session)).rejects.toThrow('保存冲突');
});
it('409保留原修订号，不重试、不转存本机', async () => {
  desk(); vi.mocked(fetch).mockResolvedValueOnce(response()).mockResolvedValueOnce(new Response(null, { status: 409 }));
  const session = await hydrateIdeaFunnelWorkspace();
  await expect(persistIdeaFunnelWorkspace(workspace(), session)).rejects.toThrow('保存冲突');
  expect(JSON.parse(String(vi.mocked(fetch).mock.calls[1][1]?.body)).expectedRevision).toBe(3);
  expect(fetch).toHaveBeenCalledTimes(2); expect(storage.size).toBe(0);
});
it('Desk 404不读本机旧库；故障和坏库不当空库', async () => {
  storage.set(key, JSON.stringify(workspace())); desk();
  vi.mocked(fetch).mockResolvedValueOnce(new Response(null, { status: 404 })).mockResolvedValueOnce(new Response(null, { status: 503 }));
  expect((await hydrateIdeaFunnelWorkspace()).workspace.ideas).toEqual([]);
  await expect(hydrateIdeaFunnelWorkspace()).rejects.toThrow('未使用本机');
  bridge.config = null; bridge.embedded = false; storage.set(key, '{bad');
  await expect(hydrateIdeaFunnelWorkspace()).rejects.toThrow('读取失败');
});
it('授权切换拒绝迟到读取', async () => {
  desk(); let finish!: (r: Response) => void;
  vi.mocked(fetch).mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
  const pending = hydrateIdeaFunnelWorkspace(); await vi.waitFor(() => expect(finish).toBeTypeOf('function'));
  desk('b'); finish(response()); await expect(pending).rejects.toThrow('授权已变化');
});
it('主观高分和占位假设不能替代证据；日期和链接必须有效', () => {
  const idea = candidate(); Object.keys(idea.scorecard).forEach(key => { (idea.scorecard as any)[key] = 100; });
  expect(reviewIdea(idea).ready).toBe(false);
  const complete = completeIdea(); expect(reviewIdea(complete, null, '2026-10-20').ready).toBe(true);
  complete.sources[0].url = 'javascript:alert(1)'; expect(reviewIdea(complete).supports).toBe(0);
  complete.sources[0].url = 'https://example.com/report'; complete.sources[0].asOf = '2026-02-30'; expect(reviewIdea(complete).usableSourceCount).toBe(0);
  complete.sources[0].asOf = '2026-06-30'; complete.sources[0].status = 'stale'; expect(reviewIdea(complete).challenges).toBe(0);
});
it('今日到期不算逾期；无效日期明确警示', () => {
  const idea = completeIdea(); const task = idea.nextActions[0]; task.dueAt = '2026-10-20';
  expect(reviewIdea(idea, null, '2026-10-20')).toMatchObject({ overdue: [], dueToday: [task] });
  task.dueAt = '2026-10-19'; expect(reviewIdea(idea, null, '2026-10-20').overdue).toHaveLength(1);
  task.dueAt = 'bad'; expect(reviewIdea(idea).warnings.join()).toContain('日期无效');
});
it('交接必须同证券、同目标且有效；截断索引未命中只能未知', () => {
  const idea = completeIdea(); idea.handoff.artifactId = 'thesis-1'; idea.handoff.status = 'created';
  const index = archive(); expect(reviewIdea(idea, index).reference?.artifactId).toBe('thesis-1');
  index.entries[0].security!.symbol = '600519'; expect(reviewIdea(idea, index).reference).toBeUndefined();
  index.entries = []; index.truncated = true; expect(reviewIdea(idea, index).handoff).toContain('未知');
});
it('Desk流程总览不混本机；同证券多线索累加计数，外部细节未知', () => {
  const data = workspace(); data.ideas[0].updatedAt = '2026-10-20';
  const older = candidate(); older.id = 'older'; older.updatedAt = '2026-10-19'; older.sources = completeIdea().sources; data.ideas.push(older);
  storage.set('newma-desk.valuation-workbench.v1', JSON.stringify({ cases: [{ id: 'leaked' }] }));
  const snapshot = buildIndexedResearchCoverage(data, null); const item = snapshot.items[0];
  expect(item.ideaId).toBe('idea-test'); expect(item.pendingTaskCount).toBe(2);
  expect(item.modules.find(m => m.modId === 'idea-funnel')?.artifactCount).toBe(2);
  expect(item.modules.find(m => m.modId === 'valuation-workbench')?.status).toBe('unknown');
  expect(item.nextReviewAt).toBeUndefined();
  expect(buildIndexedResearchCoverage(data, archive()).items[0].modules.find(m => m.modId === 'thesis-tracker')?.status).toBe('linked');
});
it('页面线索可存，但缺证据不能晋级或凭手工状态完成交接', async () => {
  desk(); vi.mocked(fetch).mockResolvedValueOnce(response()); render(<IdeaFunnel/>); await screen.findByDisplayValue('合成测试线索');
  fireEvent.change(screen.getByLabelText('阶段'), { target: { value: 'shortlist' } });
  fireEvent.click(screen.getByRole('button', { name: '保存', exact: true }));
  expect(screen.getByRole('status').textContent).toContain('进入研究阶段前'); expect(fetch).toHaveBeenCalledTimes(1);
  fireEvent.change(screen.getByLabelText('阶段'), { target: { value: 'inbox' } });
  fireEvent.change(screen.getByLabelText('交接状态'), { target: { value: 'created' } });
  fireEvent.click(screen.getByRole('button', { name: '保存', exact: true }));
  expect(screen.getByRole('status').textContent).toContain('不能确认已交接'); expect(fetch).toHaveBeenCalledTimes(1);
});
it('保存失败不报成功，保留草稿、导出并确认后重读', async () => {
  desk(); vi.mocked(fetch).mockResolvedValueOnce(response()).mockResolvedValueOnce(new Response(null, { status: 409 })).mockResolvedValueOnce(response(workspace(), 4));
  render(<IdeaFunnel/>); await screen.findByDisplayValue('合成测试线索');
  fireEvent.change(screen.getByLabelText('候选标题'), { target: { value: '未保存稿' } });
  fireEvent.click(screen.getByRole('button', { name: '保存', exact: true })); await screen.findByRole('alert');
  expect(screen.getByDisplayValue('未保存稿')).toBeTruthy();
  expect((screen.getByRole('button', { name: '保存', exact: true }) as HTMLButtonElement).disabled).toBe(true);
  expect(decodeURIComponent(screen.getByRole('link', { name: '导出当前草稿' }).getAttribute('href')!)).toContain('未保存稿');
  fireEvent.click(screen.getByRole('button', { name: '重新读取' })); fireEvent.click(screen.getByRole('button', { name: '取消操作' })); expect(fetch).toHaveBeenCalledTimes(2);
  fireEvent.click(screen.getByRole('button', { name: '重新读取' })); fireEvent.click(screen.getByRole('button', { name: '确认继续' })); await screen.findByDisplayValue('合成测试线索');
});
it('页面和Agent核对同一底稿，改稿后结果失效，不写库', async () => {
  desk(); vi.mocked(fetch).mockResolvedValueOnce(response()); render(<IdeaFunnel/>); await screen.findByDisplayValue('合成测试线索');
  let report: any; await act(async () => { report = await bridge.action('idea.audit-screen', {}); });
  expect(bridge.context().data.summary.currentAnalysis).toEqual(report);
  fireEvent.change(screen.getByLabelText('研究问题'), { target: { value: '订单是否可持续？' } });
  expect(bridge.context().data.summary.currentAnalysis).toBeNull(); expect(fetch).toHaveBeenCalledTimes(1);
});
it('真实索引选择不冒充创建；支持信号可关联可追溯来源', async () => {
  desk(); const data = workspace(); data.ideas = [completeIdea()];
  vi.mocked(fetch).mockResolvedValueOnce(response(data)).mockResolvedValueOnce(new Response(JSON.stringify(archive())));
  render(<IdeaFunnel/>); await screen.findByDisplayValue('合成测试线索');
  expect((screen.getByLabelText('来源链接 1') as HTMLInputElement).value).toBe('https://example.com/report');
  fireEvent.click(screen.getByRole('button', { name: '核对目标档案' })); await screen.findByRole('option', { name: /真实存档索引测试/ });
  fireEvent.change(screen.getByLabelText('选择已存在的同证券目标档案'), { target: { value: 'thesis-1' } });
  expect(bridge.context().data.summary.handoff.status).toBe('ready');
  expect(bridge.context().data.summary.advancementReview.reference.artifactId).toBe('thesis-1'); expect(fetch).toHaveBeenCalledTimes(2);
});
