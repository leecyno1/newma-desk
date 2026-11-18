import {act, cleanup, render, screen, waitFor} from '@testing-library/react';
import {afterEach, expect, test, vi} from 'vitest';
import {connectModHost, type ModHostRuntime} from '@newma-desk/mod-sdk';
import {GlobalIntelligenceApp} from './App';

afterEach(() => {cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals();});

test('the real SDK and topic page isolate a batched session switch', async () => {
  let listener!: (event: MessageEvent) => void;
  const postMessage = vi.fn();
  const parent = {postMessage} as unknown as Window;
  const child = {parent, document: window.document, addEventListener: (_: string, handler: EventListener) => {listener = handler as (event: MessageEvent) => void;}, removeEventListener: vi.fn()} as unknown as Window;
  const runtime: ModHostRuntime = {window: child, setTimeout: globalThis.setTimeout.bind(globalThis), clearTimeout: globalThis.clearTimeout.bind(globalThis)};
  const pending = connectModHost({modId: 'fed-rates', parentOrigin: 'https://desk.example', applyAppearance: false}, runtime);
  const send = (data: unknown) => listener({origin: 'https://desk.example', source: parent, data} as MessageEvent);
  const alice = {type: 'vibedesk:init', protocolVersion: '1.0', modId: 'fed-rates', instanceId: 'instance',
    user: {id: 'a'}, workspace: {id: 'a'}, session: {id: 'session-a', accessToken: 'token-a', expiresAt: new Date(Date.now() + 60_000).toISOString()},
    environment: {theme: 'light', locale: 'zh-CN', timezone: 'Asia/Shanghai'},
    gateways: {actions: 'https://desk.example/api/actions', data: 'https://desk.example/api/data'},
    grants: {permissions: ['market.read', 'storage.write'], actions: ['workspace.save-layout']}};
  send(alice);
  const host = await pending;
  if (!host.embedded) throw new Error('expected embedded host');
  const snapshot = (value: string) => ({topicId: 'fed-rates', title: '联储加息', subtitle: '测试', question: '测试', accent: 'cyan',
    metrics: [{label: '测试指标', value, change: '合成测试'}], factors: [], series: [], observations: [], events: [], transmission: [], sources: [],
    dataMode: 'source-observations', forecast: {generatedAt: '2026-10-22', probabilities: [], dominantScenario: '', confidence: 0, method: '测试', disclaimer: '测试'}, updatedAt: '2026-10-22'});
  let release!: (response: Response) => void;
  const fetcher = vi.fn().mockResolvedValueOnce(Response.json(snapshot('A 旧数据')))
    .mockImplementationOnce(() => new Promise<Response>(resolve => {release = resolve;}));
  vi.stubGlobal('fetch', fetcher);
  render(<GlobalIntelligenceApp embedded hostConnection={host} topicId="fed-rates" />);
  await screen.findByText('A 旧数据');
  await act(async () => {
    send({...alice, user: {id: 'b'}, workspace: {id: 'b'}, session: {...alice.session, accessToken: 'token-b'}});
    expect(document.body.innerHTML).not.toContain('A 旧数据');
    send(alice);
    send({type: 'vibedesk:context-request', requestId: 'switch-context', instanceId: 'instance', modId: 'fed-rates', reason: 'agent'});
    send({type: 'vibedesk:ui-action-request', requestId: 'switch-action', instanceId: 'instance', modId: 'fed-rates', actionId: 'workspace.save-layout', input: {}});
  });
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
  await waitFor(() => expect(postMessage.mock.calls.some(([message]) => message?.requestId === 'switch-context')).toBe(true));
  const context = postMessage.mock.calls.find(([message]) => message?.requestId === 'switch-context')![0].context;
  expect(JSON.stringify(context)).not.toContain('A 旧数据');
  expect(context.actions).toEqual([]);
  await waitFor(() => expect(postMessage.mock.calls.some(([message]) => message?.requestId === 'switch-action' && message.ok === false)).toBe(true));
  await act(async () => {release(Response.json(snapshot('A 新数据')));});
  await screen.findByText('A 新数据');
  host.close();
});
