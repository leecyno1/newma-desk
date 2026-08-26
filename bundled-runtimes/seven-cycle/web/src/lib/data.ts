import type {
  AssetStatisticsData,
  AuditData,
  CycleResearchData,
  ForecastExtensionData,
  MarketSurfaceData,
} from '../types'

async function loadJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { cache: 'no-store' })
  if (!response.ok) throw new Error(`无法读取研究数据：${path}`)
  return response.json() as Promise<T>
}

export const loadMarketSurface = () => loadJson<MarketSurfaceData>('/data/market-surface.json')
export const loadCycleResearch = () => loadJson<CycleResearchData>('/data/cycle-research.json')
export const loadAssetStatistics = () => loadJson<AssetStatisticsData>('/data/asset-statistics.json')
export const loadForecastExtension = () => loadJson<ForecastExtensionData>('/data/forecast-extension.json')
export const loadAudit = () => loadJson<AuditData>('/data/data-calibration.json')
