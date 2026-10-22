import {afterEach, describe, expect, it, vi} from 'vitest';
import {hasIndustryGrant, industryScope, observeIndustryAccess, type IndustryAccess, type IndustryHost, type IndustryRead} from './industryAccess';

function config() {
  return {modId: 'industry-prosperity', instanceId: 'synthetic-instance', user: {id: 'a'}, workspace: {id: 'w'},
    session: {id: 'session-a', accessToken: 'synthetic-token', expiresAt: new Date(Date.now() + 60_000).toISOString()},
    gateways: {data: 'https://desk.example/api/data', storage: 'https://desk.example/api/storage'},
    grants: {permissions: ['market.read', 'storage.read', 'storage.write']},
  } as IndustryHost['config'];
}
function fixture() {
  const listeners = new Set<() => void>();
  const host = {config: config(), subscribe(callback: () => void) {listeners.add(callback); return () => listeners.delete(callback);}} as unknown as IndustryHost;
  const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({synthetic: true})));
  const snapshots: IndustryAccess[] = [];
  const close = observeIndustryAccess(host, false, value => snapshots.push(value), fetcher);
  const update = (next: IndustryHost['config']) => {host.config = next; listeners.forEach(callback => callback());};
  return {host, fetcher, snapshots, close, update, latest: () => snapshots.at(-1)!};
}
afterEach(() => vi.useRealTimers());

describe('industry signed reads', () => {
  it.each(['profits', 'history', 'production', 'prices', 'capacity'] as IndustryRead[])('signs only the approved %s endpoint', async kind => {
    const f = fixture();
    expect(await f.latest().read(kind, {period: '2026-06', refresh: true})).toEqual({synthetic: true});
    const [url, options] = f.fetcher.mock.calls[0]!;
    expect(String(url)).toBe(`https://desk.example/api/industry-research${kind === 'profits' ? '' : '/' + kind}?period=2026-06&refresh=true`);
    expect(options).toMatchObject({credentials: 'omit', redirect: 'error', cache: 'no-store', method: 'GET', headers: {
      Authorization: 'Bearer synthetic-token', 'X-Newma-Desk-Instance-Id': 'synthetic-instance',
    }});
    f.close();
  });
  it('requires explicit standalone and never falls back when embedded grants are absent', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response('{}'));
    let access!: IndustryAccess;
    let close = observeIndustryAccess(undefined, false, a => {access = a;}, fetcher);
    expect(access.ready).toBe(false); await expect(access.read('profits')).rejects.toThrow('未获授权'); close();
    close = observeIndustryAccess(undefined, true, a => {access = a;}, fetcher);
    await access.read('profits'); expect(fetcher.mock.calls[0]).toMatchObject(['/api/industry-research', {headers: {}}]); close();
    const f = fixture(); f.update({...f.host.config, grants: {...f.host.config.grants, permissions: []}});
    expect(f.latest().ready).toBe(false); await expect(f.latest().read('profits')).rejects.toThrow('未获授权');
    expect(f.fetcher).not.toHaveBeenCalled(); f.close();
  });
  it('invalidates a late A result even after A → B → A', async () => {
    const f = fixture(); const a = f.host.config; const old = f.latest();
    let resolve!: (response: Response) => void;
    f.fetcher.mockImplementationOnce(() => new Promise(done => {resolve = done;}));
    const reading = old.read('profits');
    f.update({...a, user: {id: 'b'}}); f.update(a);
    expect(f.latest().epoch).toBe(3);
    expect(f.fetcher.mock.calls[0]![1]?.signal?.aborted).toBe(true);
    resolve(new Response('{"old":true}')); await expect(reading).rejects.toThrow('迟到');
    await expect(old.read('history')).rejects.toThrow('切换'); f.close();
  });
  it('does not reload on theme changes but resets on token, grant or gateway changes', () => {
    const f = fixture(); f.update({...f.host.config, environment: {...f.host.config.environment, theme: 'dark'}});
    expect(f.snapshots).toHaveLength(1);
    f.update({...f.host.config, session: {...f.host.config.session!, accessToken: 'new'}});
    f.update({...f.host.config, grants: {...f.host.config.grants, permissions: ['market.read']}});
    f.update({...f.host.config, gateways: {...f.host.config.gateways, data: 'https://other.example'}});
    expect(f.snapshots).toHaveLength(4); f.close();
  });
  it('rejects revoked/expired grants and invalid query before a request', async () => {
    const f = fixture();
    await expect(f.latest().read('capacity', {period: '2026-13&refresh=true'})).rejects.toThrow('格式');
    expect(f.fetcher).not.toHaveBeenCalled();
    const value = f.host.config;
    expect(hasIndustryGrant(value, 'storage.write')).toBe(true);
    expect(hasIndustryGrant({...value, modId: 'other'}, 'storage.write')).toBe(false);
    vi.useFakeTimers(); vi.setSystemTime(Date.now() + 120_000);
    expect(hasIndustryGrant(value, 'storage.read')).toBe(false);
    await expect(f.latest().read('profits')).rejects.toThrow('未获授权'); f.close();
  });
  it('never retries failed signed requests anonymously or publishes raw error bodies', async () => {
    const f = fixture(); f.fetcher.mockResolvedValueOnce(new Response('private diagnostic', {status: 401}));
    await expect(f.latest().read('profits')).rejects.toThrow('401');
    expect(f.fetcher).toHaveBeenCalledTimes(1); f.close();
  });
  it('scope includes all private storage identity fields', () => {
    const a = config();
    for (const b of [{...a, workspace: {id: 'other'}}, {...a, instanceId: 'other'},
      {...a, session: {...a.session!, accessToken: 'other'}}, {...a, grants: {...a.grants, permissions: ['market.read']}}]) {
      expect(industryScope(b)).not.toBe(industryScope(a));
    }
  });
});
