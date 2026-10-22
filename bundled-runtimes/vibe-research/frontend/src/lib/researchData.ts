import { createGatewayClient, createUnifiedDataClient, GatewayError } from '@newma-desk/mod-sdk';
import { api, ApiError, type Financials, type EquityResearchSnapshot } from '@/lib/api';
import { getVibeDeskConfig, isVibeDeskEmbedded } from '@/lib/vibedesk';

type ResearchPage = 'earnings-workbench' | 'valuation-workbench' | 'peer-comparison';

export function canRefreshResearchData(moduleId: ResearchPage): boolean {
  const config = getVibeDeskConfig();
  if (!config) return !isVibeDeskEmbedded && import.meta.env.VITE_NEWMA_DESK_INTEGRATED !== '1';
  return Boolean(config.moduleId === moduleId && config.instanceId && config.accessToken && config.permissions?.includes('market.read'));
}

function dataScope() {
  const c = getVibeDeskConfig();
  return JSON.stringify([c?.apiOrigin, c?.userId, c?.workspaceId, c?.moduleId, c?.instanceId, c?.accessToken, c?.permissions]);
}

class ResearchDataError extends Error {}

// Business routing only: signing, HTTP and Action dispatch remain in the public SDK.
async function query<T>(moduleId: ResearchPage, capability: string, actionId: string, input: Record<string, unknown>,
  native: (signal: AbortSignal) => Promise<T>, cancel?: AbortSignal): Promise<T> {
  if (!canRefreshResearchData(moduleId)) throw new ResearchDataError('当前页面没有行情读取授权，请从已授权的 Desk 重新打开；未改动底稿。');
  const config = getVibeDeskConfig();
  const scope = dataScope();
  const timeout = AbortSignal.timeout(30_000);
  const signal = cancel ? AbortSignal.any([cancel, timeout]) : timeout;
  try {
    signal.throwIfAborted();
    let result: T;
    if (config) {
      const gateway = createGatewayClient({ baseUrl: config.apiOrigin, accessToken: config.accessToken, instanceId: config.instanceId,
        fetch: (url, init) => fetch(url, { ...init, signal, cache: 'no-store' }),
      });
      const client = createUnifiedDataClient({
        invokeAction: (id, args = {}) => gateway.invokeModAction(moduleId, id, args),
        actionByCapability: { [capability]: actionId },
      });
      const payload = await client.query<{ data: T }>(capability, input);
      if (!payload?.data || typeof payload.data !== 'object' || Array.isArray(payload.data)) {
        throw new ResearchDataError('数据响应格式不正确，未改动底稿。');
      }
      result = payload.data;
    } else {
      result = await native(signal);
    }
    signal.throwIfAborted();
    if (scope !== dataScope()) throw new ResearchDataError('工作区或授权已变化，旧结果未采用，请在当前页面重新核对。');
    return result;
  } catch (error) {
    if (cancel?.aborted) throw new ResearchDataError('页面读取已停止，未采用结果。');
    if (timeout.aborted) throw new ResearchDataError('读取超时，未确认取数结果，现有底稿保留；未自动重试。');
    if (error instanceof ResearchDataError) throw error;
    const status = error instanceof GatewayError || error instanceof ApiError ? error.status : 0;
    if (status === 401 || status === 403) throw new ResearchDataError('行情读取授权已失效或不足，请重新打开页面核对权限；现有底稿保留。');
    throw new ResearchDataError(`数据读取失败${status ? `（HTTP ${status}）` : ''}，请核对数据服务及模组版本；现有底稿保留，未自动重试。`);
  }
}

export const fetchFinancialEvidence = (code: string, basis: 'ytd' | 'quarter' | 'annual', signal?: AbortSignal) =>
  query<Financials>('earnings-workbench', 'research.financials', 'earnings.fetch-financials', { code, basis },
    cancel => api.financials(code, basis, cancel), signal);

export async function fetchValuationPrice(symbol: string, signal?: AbortSignal) {
  const snapshot = await query<EquityResearchSnapshot>('valuation-workbench', 'research.equity-snapshot', 'valuation.fetch-price', { symbol },
    cancel => api.equityResearch(symbol, cancel), signal);
  if (!snapshot?.identity || typeof snapshot.identity.symbol !== 'string' || !Array.isArray(snapshot.evidenceLedger)
    || snapshot.evidenceLedger.some(item => !item || typeof item !== 'object')) {
    throw new ResearchDataError('行情响应缺少证券身份或证据，未改动模型。');
  }
  return snapshot;
}

export async function fetchPeerSnapshot(symbol: string, signal?: AbortSignal) {
  const snapshot = await query<EquityResearchSnapshot>('peer-comparison', 'research.equity-snapshot', 'peer.fetch-snapshot', { symbol },
    cancel => api.equityResearch(symbol, cancel), signal);
  if (!snapshot?.identity || !['symbol', 'market', 'name', 'currency'].every(key => typeof snapshot.identity[key as keyof typeof snapshot.identity] === 'string')
    || !Array.isArray(snapshot.evidenceLedger) || snapshot.evidenceLedger.some(item => !item || typeof item !== 'object')) {
    throw new ResearchDataError('同业响应缺少证券身份或证据，未采用。');
  }
  return snapshot;
}
