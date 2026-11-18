import {expect, test, vi} from 'vitest';
import {connectModHost, type ModHostRuntime} from '@newma-desk/mod-sdk';

test('the SDK exposes current configuration and rejects an old session action result', async () => {
  let listener!: (event: MessageEvent) => void;
  const postMessage = vi.fn();
  const parent = {postMessage} as unknown as Window;
  const child = {parent, addEventListener: (_: string, handler: EventListener) => {listener = handler as (event: MessageEvent) => void;}, removeEventListener: vi.fn()} as unknown as Window;
  const runtime: ModHostRuntime = {window: child, setTimeout: globalThis.setTimeout.bind(globalThis), clearTimeout: globalThis.clearTimeout.bind(globalThis)};
  const pending = connectModHost({modId: 'global-situation', parentOrigin: 'https://desk.example', applyAppearance: false}, runtime);
  const send = (data: unknown) => listener({origin: 'https://desk.example', source: parent, data} as MessageEvent);
  const alice = {type: 'vibedesk:init', protocolVersion: '1.0', modId: 'global-situation', instanceId: 'instance',
    user: {id: 'a'}, workspace: {id: 'a'}, session: {id: 'session-a', accessToken: 'token-a', expiresAt: new Date(Date.now() + 60_000).toISOString()},
    environment: {theme: 'light', locale: 'zh-CN', timezone: 'Asia/Shanghai'},
    gateways: {actions: 'https://desk.example/api/actions', data: 'https://desk.example/api/data'},
    grants: {permissions: ['market.read'], actions: ['global-intel.refresh']}};
  send(alice);
  const host = await pending;
  if (!host.embedded) throw new Error('expected embedded host');
  try {
    const observed: string[] = [];
    host.subscribe(() => observed.push(host.config.workspace.id));
    send({...alice, user: {id: 'b'}, workspace: {id: 'b'}});
    send(alice);
    expect.soft(observed).toEqual(['b', 'a']);
    const outcome = host.invokeAction('global-intel.refresh').then(() => 'resolved', () => 'rejected');
    const request = postMessage.mock.calls.find(([message]) => message?.type === 'vibedesk:action-request')![0];
    send({...alice, session: {...alice.session, accessToken: 'token-renewed'}});
    send({type: 'vibedesk:action-result', requestId: request.requestId, instanceId: 'instance', modId: 'global-situation',
      actionId: 'global-intel.refresh', status: 200, ok: true, result: {old: true}});
    expect(await outcome).toBe('rejected');
  } finally {host.close();}
});
