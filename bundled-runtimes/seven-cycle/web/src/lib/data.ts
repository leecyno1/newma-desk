import type {
  AssetStatisticsData,
  AuditData,
  CycleResearchData,
  ForecastExtensionData,
  MarketSurfaceData,
} from '../types'
import { fetchResearch } from './vibedesk'

export const loadMarketSurface = (signal?: AbortSignal) => fetchResearch<MarketSurfaceData>('/data/market-surface.json', signal)
export const loadCycleResearch = (signal?: AbortSignal) => fetchResearch<CycleResearchData>('/data/cycle-research.json', signal)
export const loadAssetStatistics = (signal?: AbortSignal) => fetchResearch<AssetStatisticsData>('/data/asset-statistics.json', signal)
export const loadForecastExtension = (signal?: AbortSignal) => fetchResearch<ForecastExtensionData>('/data/forecast-extension.json', signal)
export const loadAudit = (signal?: AbortSignal) => fetchResearch<AuditData>('/data/data-calibration.json', signal)
export const loadAttribution = <T>(assetId: string, signal?: AbortSignal) => fetchResearch<{data: T[]}>(`/v1/assets/${encodeURIComponent(assetId)}/attribution?horizon=12`, signal)
