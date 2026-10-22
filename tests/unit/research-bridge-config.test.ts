// @vitest-environment jsdom
import { expect, it, vi } from 'vitest';

it('动作同步异常回传失败，切会话或卸载后不发送迟到结果及上下文', async () => {
  const parent = { postMessage: vi.fn() };
  vi.stubGlobal('parent', parent);
  const bridge = await import('@/lib/vibedesk');
  const send = (data: unknown, origin = 'http://desk.test', source = parent) => window.dispatchEvent(
    new MessageEvent('message', { data, origin, source: source as unknown as Window }),
  );
  const config = { type: 'vibedesk:config', gatewayOrigin: 'http://desk.test', moduleId: 'earnings-workbench', userId: 'test-user', workspaceId: 'actions', theme: 'light' };
  send(config);
  send({ type: 'vibedesk:init', modId: config.moduleId, instanceId: 'instance-actions', user: { id: 'test-user' }, workspace: { id: 'actions' },
    gateways: { data: 'http://desk.test/api/data', storage: 'http://desk.test/api/mods' }, session: { accessToken: 'synthetic-test-session' },
    grants: { permissions: ['storage.read'] }, environment: { theme: 'light' } });
  const request = { type: 'vibedesk:ui-action-request', modId: config.moduleId, instanceId: 'instance-actions', requestId: 'action-1', actionId: 'earnings.compare', input: {} };
  const broken = vi.fn(() => { throw new Error('当前底稿不可比较'); });
  let unregister = bridge.registerVibeDeskUiActionHandler(broken);
  parent.postMessage.mockClear();
  send(request, 'http://untrusted.test'); send(request, 'http://desk.test', { postMessage: vi.fn() });
  await Promise.resolve(); expect(broken).not.toHaveBeenCalled();
  send(request);
  await vi.waitFor(() => expect(parent.postMessage).toHaveBeenCalledWith(expect.objectContaining({
    type: 'vibedesk:ui-action-result', ok: false, requestId: 'action-1', error: { code: 'action_failed', message: '当前底稿不可比较' },
  }), 'http://desk.test'));
  unregister();
  let finish!: (value: unknown) => void;
  unregister = bridge.registerVibeDeskUiActionHandler(() => new Promise(resolve => { finish = resolve; }));
  parent.postMessage.mockClear(); send({ ...request, requestId: 'late-action' });
  await vi.waitFor(() => expect(finish).toBeTypeOf('function'));
  unregister(); finish({ secret: 'old-page-result' });
  await new Promise(resolve => setTimeout(resolve, 0));
  expect(parent.postMessage.mock.calls.some(([value]) => value.type === 'vibedesk:ui-action-result')).toBe(false);
  let finishContext!: (value: any) => void;
  const stopContext = bridge.registerVibeDeskContextProvider(() => new Promise(resolve => { finishContext = resolve; }));
  const publishing = bridge.publishVibeDeskContext();
  send({ ...config, workspaceId: 'other-workspace' });
  parent.postMessage.mockClear(); finishContext({ selection: { symbol: 'PRIVATE-OLD' } });
  expect(await publishing).toBe(false);
  expect(parent.postMessage.mock.calls.some(([value]) => value.type === 'vibedesk:context')).toBe(false);
  stopContext(); vi.unstubAllGlobals();
});

it('重复主题配置不清空已授权会话，真正切工作区才重新握手', async () => {
  const parent = { postMessage: vi.fn() };
  vi.stubGlobal('parent', parent);
  const { getVibeDeskConfig, subscribeVibeDeskConfig } = await import('@/lib/vibedesk');
  const changed = vi.fn();
  const unsubscribe = subscribeVibeDeskConfig(changed);
  const send = (data: unknown, origin = 'http://desk.test') => window.dispatchEvent(
    new MessageEvent('message', { data, origin, source: parent as unknown as Window }),
  );
  const config = {type:'vibedesk:config',gatewayOrigin:'http://desk.test',moduleId:'thesis-tracker',userId:'test-user',workspaceId:'a',theme:'light'};
  send(config);
  send({type:'vibedesk:init',modId:'thesis-tracker',instanceId:'instance-a',user:{id:'test-user'},workspace:{id:'a'},
    gateways:{data:'http://desk.test/api/data',storage:'http://desk.test/api/mods'},
    session:{accessToken:'synthetic-test-session'},grants:{permissions:['storage.read','storage.write']},environment:{theme:'light'}});
  expect(getVibeDeskConfig()?.instanceId).toBe('instance-a');
  changed.mockClear();parent.postMessage.mockClear();
  send({...config,theme:'dark'});
  expect(changed).toHaveBeenCalledTimes(1);
  expect(getVibeDeskConfig()).toMatchObject({instanceId:'instance-a',workspaceId:'a',theme:'dark',accessToken:'synthetic-test-session',permissions:['storage.read','storage.write']});
  expect(parent.postMessage).not.toHaveBeenCalled();
  send({...config,gatewayOrigin:'http://other.test'});
  expect(getVibeDeskConfig()?.gatewayOrigin).toBe('http://desk.test');
  send({...config,workspaceId:'b'});
  expect(getVibeDeskConfig()).toMatchObject({workspaceId:'b'});
  expect(getVibeDeskConfig()?.accessToken).toBeUndefined();
  expect(getVibeDeskConfig()?.instanceId).toBeUndefined();
  expect(parent.postMessage).toHaveBeenCalledWith(expect.objectContaining({type:'vibedesk:hello'}),'http://desk.test');
  unsubscribe();vi.unstubAllGlobals();
});
