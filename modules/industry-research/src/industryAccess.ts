import type { ModHostConnection } from '@newma-desk/mod-sdk';

export type IndustryHost = Extract<ModHostConnection, {embedded: true}>;
type Config = IndustryHost['config'];
export type IndustryRead = 'profits' | 'history' | 'production' | 'prices' | 'capacity';
type ReadOptions = {period?: string; refresh?: boolean; signal?: AbortSignal};
const paths: Record<IndustryRead, string> = {
  profits: '/api/industry-research', history: '/api/industry-research/history',
  production: '/api/industry-research/production', prices: '/api/industry-research/prices',
  capacity: '/api/industry-research/capacity',
};

// Internal identity only: never publish this value in Context or exports.
export const industryScope = (config?: Config) => config ? JSON.stringify([
  config.modId, config.user.id, config.workspace.id, config.instanceId, config.session,
  config.gateways.data, config.gateways.storage, [...config.grants.permissions].sort(),
]) : '';

export function hasIndustryGrant(config: Config | undefined, permission: string) {
  return !!(config?.modId === 'industry-prosperity' && config.session?.accessToken && config.instanceId
    && Date.parse(config.session.expiresAt) > Date.now() && config.grants.permissions.includes(permission));
}

export const privateIndustryFetch: typeof fetch = (url, options) => fetch(url, {
  ...options, credentials: 'omit', redirect: 'error', cache: 'no-store',
  signal: AbortSignal.any([AbortSignal.timeout(15_000), ...(options?.signal ? [options.signal] : [])]),
});

export interface IndustryAccess {
  epoch: number;
  ready: boolean;
  message: string;
  read<T>(kind: IndustryRead, options?: ReadOptions): Promise<T>;
}

/** One session lifecycle for the page; any identity change immediately cancels old reads. */
export function observeIndustryAccess(host: IndustryHost | undefined, standalone: boolean,
  notify: (access: IndustryAccess) => void, fetcher: typeof fetch = fetch) {
  let epoch = 0;
  let previous: string | undefined;
  let controller = new AbortController();
  function update() {
    const config = host?.config;
    const scope = industryScope(config);
    if (scope === previous) return;
    previous = scope;
    controller.abort(); controller = new AbortController();
    const lifetime = controller.signal;
    const local = !host && standalone;
    const ready = local || hasIndustryGrant(config, 'market.read') && !!config?.gateways.data;
    // Capture primitives; do not retain a mutable host config for an in-flight request.
    const gateway = config?.gateways.data;
    const token = config?.session?.accessToken;
    const instanceId = config?.instanceId;
    const expiresAt = config?.session?.expiresAt;
    notify({epoch: ++epoch, ready, message: ready ? '' : host
      ? '当前会话没有行业读取权限，请重新打开模组。'
      : '等待 Desk 身份连接；独立使用请启动 standalone 构建。',
    async read<T>(kind: IndustryRead, options: ReadOptions = {}) {
      if (lifetime.aborted) throw new Error('会话已切换，请重新读取');
      if (!ready || !local && (!expiresAt || Date.parse(expiresAt) <= Date.now())) throw new Error('行业读取未获授权');
      const path = paths[kind];
      if (!path) throw new Error('不支持的行业读取');
      if (options.period && !/^\d{4}-(0[1-9]|1[0-2])$/.test(options.period)) throw new Error('报告期格式错误');
      const query = new URLSearchParams();
      if (options.period) query.set('period', options.period);
      if (options.refresh) query.set('refresh', 'true');
      const target = path + (query.size ? `?${query}` : '');
      const signal = AbortSignal.any([lifetime, AbortSignal.timeout(120_000), ...(options.signal ? [options.signal] : [])]);
      const response = await fetcher(local ? target : new URL(target, gateway!), {
        method: 'GET', signal, credentials: 'omit', redirect: 'error', cache: 'no-store',
        headers: local ? {} : {Authorization: `Bearer ${token}`, 'X-Newma-Desk-Instance-Id': instanceId!},
      });
      if (!response.ok) throw new Error(`行业读取失败（${response.status}），请核对登录、权限及数据源`);
      const body = await response.json() as T;
      // Some transports ignore abort; do not accept their late response, including A → B → A.
      if (signal.aborted) throw new Error('请求已结束，未采用迟到数据');
      return body;
    }});
  }
  const unsubscribe = host?.subscribe(update);
  update();
  return () => {unsubscribe?.(); controller.abort();};
}
