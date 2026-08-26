import type { MarketTrack } from '../types'

export type MarketTrackFamily = 'growth' | 'inflation' | 'rates' | 'fx' | 'equity' | 'commodity' | 'macro' | 'other'

const familyOrder: Record<MarketTrackFamily, number> = {
  growth: 0,
  inflation: 1,
  rates: 2,
  fx: 3,
  equity: 4,
  commodity: 5,
  macro: 6,
  other: 7,
}

export const familyLabels: Record<MarketTrackFamily, string> = {
  growth: '增长与生产',
  inflation: '价格与通胀',
  rates: '利率、债券与流动性',
  fx: '外汇',
  equity: '股票与风格',
  commodity: '商品',
  macro: '其他宏观',
  other: '其他市场',
}

const cycleTrackRoles: Record<string, string> = {
  us_pmi: '景气先行',
  us_industrial_production: '实体确认',
  us_cpi: '消费通胀',
  us_ppi: '上游价格',
  us_policy_rate: '政策响应',
  us_term_spread: '利率预期',
  us_nfci: '信用传导',
  dxy: '全球流动性',
  sp500: '风险资产',
  global_commodity: '需求与通胀',
}

export function marketTrackRole(track: MarketTrack) {
  return cycleTrackRoles[track.id] ?? familyLabels[marketTrackFamily(track)]
}

export function marketTrackFamily(track: MarketTrack): MarketTrackFamily {
  const identity = `${track.category} ${track.label}`
  if (/价格|通胀|CPI|PPI/.test(identity)) return 'inflation'
  if (/利率|债券|信用|流动性|国债|收益率/.test(identity)) return 'rates'
  if (/外汇|美元|汇率|DXY|货币/.test(identity)) return 'fx'
  if (/股票|指数|行业|风格|宽基|标普|纳斯达克|红利|成长|价值/.test(identity)) return 'equity'
  if (/商品|贵金属|黄金|白银|能源|原油|天然气|铜|铝|黑色|农产品/.test(identity)) return 'commodity'
  if (/生产|增长|就业|贸易|投资|产出|PMI|GDP/.test(identity)) return 'growth'
  return track.group === 'economic' ? 'macro' : 'other'
}

export function sortMarketTracks(tracks: MarketTrack[]) {
  return tracks
    .map((track, index) => ({ track, index, family: marketTrackFamily(track) }))
    .sort((left, right) => familyOrder[left.family] - familyOrder[right.family] || left.index - right.index)
    .map(({ track }) => track)
}
