import {
  Activity,
  AlertTriangle,
  Anchor,
  Bell,
  BellRing,
  BellPlus,
  BookOpen,
  Building2,
  Cable,
  Check,
  ChevronDown,
  CircleDot,
  Clock3,
  CloudSun,
  Crosshair,
  Database,
  Languages,
  ExternalLink,
  Flame,
  Fuel,
  GitBranch,
  Gauge,
  HeartPulse,
  Landmark,
  Layers3,
  Locate,
  LocateFixed,
  Map as MapIcon,
  Newspaper,
  Pause,
  Plane,
  Play,
  Radio,
  Radiation,
  RefreshCw,
  Route,
  Search,
  Satellite,
  ShieldAlert,
  Ship,
  Sparkles,
  Star,
  Target,
  Trash2,
  TrendingUp,
  WifiOff,
  X,
} from "lucide-react";
import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
} from "react";

import { createModSnapshotCache } from "@newma-desk/mod-sdk";

import {
  GLOBAL_INTELLIGENCE_CONTRACT,
  calculateGlobalIntelMarketReactions,
  calculateGlobalIntelRouteAlerts,
  calculateGlobalIntelRouteImpacts,
  clusterGlobalIntelEvents,
  globalIntelEventIdentity,
  findGlobalMediaMonitorAnnotation,
  findGlobalMediaMonitorTopic,
  globalMediaTopicSimilarity,
  isActionableGlobalIntelEvent,
  mediaSentimentLabel,
  mediaVelocityLabel,
  mergeGlobalIntelEventHistory,
  normalizeGlobalIntelEvents,
  normalizeGlobalMediaMonitor,
  normalizeGlobalIntelPoints,
  normalizeGlobalIntelRoutes,
  reconcileGlobalIntelRouteAlertStates,
  updateGlobalIntelMilitaryTrackHistory,
  type GlobalIntelCategory,
  type GlobalIntelDataSource,
  type GlobalIntelEvent,
  type GlobalIntelEventCluster,
  type GlobalIntelEventHistoryEntry,
  type GlobalIntelMilitaryTrackHistory,
  type GlobalIntelPoint,
  type GlobalIntelRoute,
  type GlobalIntelRouteAlertDisposition,
  type GlobalIntelRouteAlertState,
  type GlobalIntelSeverity,
  type GlobalMediaMonitorTopic,
} from "./data";
import {
  IntelligenceMap,
  type IntelligenceMapFocus,
  type IntelligenceMapMode,
  type IntelligenceRegion,
  type IntelligenceWatchRegion,
} from "./IntelligenceMap";

const CATEGORY_META: Record<GlobalIntelCategory, {
  label: string;
  color: string;
  icon: typeof Activity;
}> = {
  market: { label: "市场异常", color: "#40c6ff", icon: Activity },
  news: { label: "新闻", color: "#9a8bff", icon: Newspaper },
  policy: { label: "政策", color: "#f5be4a", icon: Landmark },
  conflict: { label: "冲突", color: "#ff4a65", icon: ShieldAlert },
  disaster: { label: "灾害", color: "#ff8146", icon: Flame },
  military: { label: "军事", color: "#be67ff", icon: Satellite },
  infrastructure: { label: "基础设施", color: "#37d6a1", icon: Building2 },
  maritime: { label: "海事", color: "#29c9d2", icon: Anchor },
  climate: { label: "气候", color: "#8bd24f", icon: CloudSun },
  health: { label: "公共卫生", color: "#ff6fb1", icon: HeartPulse },
  cyber: { label: "网络安全", color: "#2dd4ff", icon: WifiOff },
  nuclear: { label: "核动态", color: "#ffe45e", icon: Radiation },
  aviation: { label: "航空运行", color: "#62a8ff", icon: Satellite },
  space: { label: "空间天气", color: "#f5d76e", icon: Radio },
  technology: { label: "AI 与技术", color: "#b18cff", icon: Database },
  society: { label: "人道与社会", color: "#ff9f8a", icon: Activity },
  prediction: { label: "预测市场", color: "#73d6a5", icon: Gauge },
};

const MAP_LAYER_CATEGORIES: GlobalIntelCategory[] = [
  "conflict",
  "military",
  "maritime",
  "nuclear",
  "disaster",
  "climate",
  "infrastructure",
  "market",
  "policy",
  "society",
];
const EVENT_FILTER_CATEGORIES: GlobalIntelCategory[] = [
  "news",
  "health",
  "climate",
  "disaster",
  "conflict",
  "military",
  "nuclear",
  "maritime",
  "cyber",
  "infrastructure",
  "policy",
  "market",
  "aviation",
  "space",
  "technology",
  "society",
  "prediction",
];
const DEFAULT_LAYERS = new Set<GlobalIntelCategory>(MAP_LAYER_CATEGORIES);
const ROUTE_FILTERS: Array<{
  kind: GlobalIntelRoute["kind"];
  label: string;
  icon: typeof Route;
}> = [
  { kind: "pipeline", label: "能源", icon: Fuel },
  { kind: "cable", label: "光缆", icon: Cable },
  { kind: "shipping", label: "航运", icon: Ship },
  { kind: "flight", label: "航空", icon: Plane },
];

type TimeWindow = "24h" | "7d" | "all";
type SeverityFilter = "all" | "priority" | GlobalIntelSeverity;
type SituationPresetId = "overview" | "conflict" | "energy" | "network" | "disaster";

interface SituationPreset {
  id: SituationPresetId;
  label: string;
  description: string;
  activeLayers: GlobalIntelCategory[];
  activeRouteKinds: GlobalIntelRoute["kind"][];
  categoryFilter: "all" | GlobalIntelCategory;
  severityFilter: SeverityFilter;
  timeWindow: TimeWindow;
  mapMode: IntelligenceMapMode;
  showCountryRisk: boolean;
}

interface SourceHealthItem {
  id: string;
  label: string;
  status: "healthy" | "degraded" | "error" | "stale";
  statusLabel: string;
  reason: string;
  freshness?: string;
}

interface PostureDomain {
  id: string;
  label: string;
  score: number;
  level: string;
  signals: string[];
}

interface StrategicAlert {
  id: string;
  domain: string;
  domainLabel: string;
  priority: string;
  message: string;
}

interface TemporalAnomaly {
  id: string;
  metric: string;
  region: string;
  zScore: number;
  severity: string;
  multiplier: number;
  observed: number;
  expected: number;
}

interface VolatilityTrend {
  id: string;
  metric: string;
  region: string;
  volatility: number;
  mean: number;
  observations: number;
}

interface ConvergenceHotspot {
  id: string;
  label: string;
  latitude: number;
  longitude: number;
  score: number;
  earthquakeCount: number;
}

const MEDIA_SENTIMENT_ORDER = ["positive", "negative", "neutral", "mixed"] as const;
const MEDIA_SENTIMENT_SHORT_LABEL = {
  positive: "正",
  negative: "负",
  neutral: "中",
  mixed: "混",
} as const;

interface SavedWatchRegion {
  id: string;
  name: string;
  bounds: IntelligenceRegion;
  createdAt: string;
  baselinePointIds: string[];
}

interface EventDisposition {
  acknowledgedAt?: string;
  acknowledgedChangeAt?: string;
  watching?: boolean;
}

interface MediaWatchRule {
  id: string;
  label: string;
  keywords: string[];
  createdAt: string;
  baselineSignature?: string;
}

interface MediaTopicHistoryEntry {
  id: string;
  label: string;
  headline: string;
  keywords: string[];
  sources: string[];
  firstSeenAt: string;
  lastSeenAt: string;
  lastChangedAt: string;
  mentionCount: number;
  sourceCount: number;
  heatScore: number;
  attentionScore?: number;
  spreadScore: number;
  verificationStatus: string;
  verificationHistory: Array<{ status: string; timestamp: string }>;
}

const WATCH_REGIONS_KEY = "newma-desk.global-intelligence.watch-regions.v1";
const ROUTE_ALERTS_KEY = "newma-desk.global-intelligence.route-alerts.v1";
const MILITARY_TRACKS_KEY = "newma-desk.global-intelligence.military-tracks.v1";
const EVENT_HISTORY_KEY = "newma-desk.global-intelligence.event-history.v1";
const EVENT_DISPOSITIONS_KEY = "newma-desk.global-intelligence.event-dispositions.v1";
const EVENT_ATTENTION_BASELINE_KEY = "newma-desk.global-intelligence.attention-baseline.v2";
const MEDIA_WATCH_RULES_KEY = "newma-desk.global-intelligence.media-watch-rules.v1";
const MEDIA_TOPIC_HISTORY_KEY = "newma-desk.global-intelligence.media-topic-history.v1";
const SITUATION_PRESETS: SituationPreset[] = [
  {
    id: "overview",
    label: "综合",
    description: "全域信号、全部战略通道",
    activeLayers: [...MAP_LAYER_CATEGORIES],
    activeRouteKinds: ["pipeline", "cable", "shipping", "flight"],
    categoryFilter: "all",
    severityFilter: "all",
    timeWindow: "24h",
    mapMode: "signals",
    showCountryRisk: true,
  },
  {
    id: "conflict",
    label: "冲突",
    description: "冲突、军事与航运风险",
    activeLayers: ["conflict", "military", "maritime", "nuclear", "infrastructure"],
    activeRouteKinds: ["shipping", "flight"],
    categoryFilter: "conflict",
    severityFilter: "priority",
    timeWindow: "7d",
    mapMode: "heat",
    showCountryRisk: true,
  },
  {
    id: "energy",
    label: "能源",
    description: "管线、航运与市场传导",
    activeLayers: ["infrastructure", "maritime", "climate", "policy", "conflict", "market"],
    activeRouteKinds: ["pipeline", "shipping"],
    categoryFilter: "all",
    severityFilter: "all",
    timeWindow: "7d",
    mapMode: "signals",
    showCountryRisk: true,
  },
  {
    id: "network",
    label: "网络",
    description: "光缆、基础设施与高危信号",
    activeLayers: ["infrastructure", "conflict", "military"],
    activeRouteKinds: ["cable"],
    categoryFilter: "cyber",
    severityFilter: "priority",
    timeWindow: "24h",
    mapMode: "heat",
    showCountryRisk: false,
  },
  {
    id: "disaster",
    label: "灾害",
    description: "自然灾害与基础设施暴露",
    activeLayers: ["disaster", "climate", "infrastructure"],
    activeRouteKinds: [],
    categoryFilter: "disaster",
    severityFilter: "priority",
    timeWindow: "7d",
    mapMode: "heat",
    showCountryRisk: true,
  },
];

const SOURCE_LABELS: Record<string, string> = {
  market_quotes: "市场行情",
  news_feed: "新闻聚合",
  trending_keywords: "新闻热词",
  cyber_threats: "网络威胁",
  internet_outages: "网络中断",
  cable_health: "海底光缆",
  earthquakes: "地震监测",
  wildfires: "山火监测",
  military_flights: "军事航班",
  acled_events: "ACLED 冲突",
  ucdp_events: "UCDP 冲突",
  nav_warnings: "航行警告",
  energy_prices: "能源价格",
  gas_prices: "燃油价格",
  electricity_rates: "电力价格",
  crypto_quotes: "加密资产行情",
  stablecoin_status: "稳定币监测",
  sector_heatmap: "行业热力",
  commodity_quotes: "大宗商品行情",
  macro_signals: "宏观信号",
  crucix: "Crucix 补充情报",
  etf_flows: "ETF 行情",
  residential_natgas: "居民天然气价格",
  shipping_index: "航运压力",
  risk_scores: "国家风险",
  btc_technicals: "BTC 技术指标",
  usni_fleet: "USNI 舰队追踪",
  climate_anomalies: "气候异常",
  disease_outbreaks: "公共卫生",
  nuclear_monitor: "核活动监测",
  traffic_flow: "交通流",
  traffic_incidents: "交通事件",
  webcams: "公共摄像头",
  election_calendar: "选举日历",
  strategic_posture: "战略态势",
  situation_brief: "态势简报",
  prediction_markets: "预测市场",
  airport_delays: "机场延误",
  domestic_flights: "全球航空流量",
  space_weather: "空间天气",
  ai_watch: "AI 动态",
  service_status: "云服务状态",
  fleet_report: "舰队态势",
  social_signals: "社交信号",
  displacement: "人口流离失所",
  population_exposure: "人口暴露",
  signal_convergence: "信号汇聚",
  alert_digest: "综合预警",
  weekly_trends: "历史基线异常",
};

const POSTURE_DOMAIN_LABELS: Record<string, string> = {
  military: "军事",
  political: "政治",
  conflict: "冲突",
  infrastructure: "基础设施",
  economic: "经济",
  cyber: "网络安全",
  health: "公共卫生",
  climate: "气候",
  space: "空间天气",
  security: "安全热点",
};

const RISK_LEVEL_LABELS: Record<string, string> = {
  LOW: "低风险",
  GUARDED: "警戒",
  ELEVATED: "风险升高",
  HIGH: "高风险",
  CRITICAL: "严重风险",
};

const TREND_LABELS: Record<string, string> = {
  military_flights: "军事航班",
  surge_aircraft: "军事活动激增",
  acled_events: "冲突事件",
  arctic: "北极",
  baltic_sea: "波罗的海",
  black_sea: "黑海",
  european: "欧洲",
  persian_gulf: "波斯湾",
  red_sea: "红海",
  middle_east: "中东",
  east_africa: "东非",
  south_asia: "南亚",
  eastern_europe: "东欧",
  sahel: "萨赫勒",
  korean_dmz: "朝韩非军事区",
  korean_peninsula: "朝鲜半岛",
  indo_pacific: "印太",
  taiwan_strait: "台湾海峡",
  south_china_sea: "南海",
};

const DEFAULT_CONVERGENCE_HOTSPOTS: ConvergenceHotspot[] = [
  {
    id: "default-middle-east",
    label: "中东",
    latitude: 29.5,
    longitude: 45.5,
    score: 0,
    earthquakeCount: 0,
  },
  {
    id: "default-east-asia",
    label: "东亚",
    latitude: 30.5,
    longitude: 121.5,
    score: 0,
    earthquakeCount: 0,
  },
  {
    id: "default-europe",
    label: "欧洲",
    latitude: 50.0,
    longitude: 12.0,
    score: 0,
    earthquakeCount: 0,
  },
];

function loadWatchRegions(): SavedWatchRegion[] {
  try {
    const saved = JSON.parse(localStorage.getItem(WATCH_REGIONS_KEY) || "[]") as unknown;
    return Array.isArray(saved) ? saved as SavedWatchRegion[] : [];
  } catch {
    return [];
  }
}

function loadRouteAlertStates(): Record<string, GlobalIntelRouteAlertState> {
  try {
    const saved = JSON.parse(localStorage.getItem(ROUTE_ALERTS_KEY) || "{}") as unknown;
    return typeof saved === "object" && saved !== null && !Array.isArray(saved)
      ? saved as Record<string, GlobalIntelRouteAlertState>
      : {};
  } catch {
    return {};
  }
}

function loadMilitaryTrackHistory(): GlobalIntelMilitaryTrackHistory {
  try {
    const saved = JSON.parse(sessionStorage.getItem(MILITARY_TRACKS_KEY) || "{}") as unknown;
    return typeof saved === "object" && saved !== null && !Array.isArray(saved)
      ? saved as GlobalIntelMilitaryTrackHistory
      : {};
  } catch {
    return {};
  }
}

function loadEventHistory(): GlobalIntelEventHistoryEntry[] {
  try {
    const saved = JSON.parse(localStorage.getItem(EVENT_HISTORY_KEY) || "[]") as unknown;
    return Array.isArray(saved)
      ? saved.map((item) => ({
        ...item as GlobalIntelEventHistoryEntry,
        lastChangedAt: (item as GlobalIntelEventHistoryEntry).lastChangedAt
          || (item as GlobalIntelEventHistoryEntry).firstSeenAt
          || (item as GlobalIntelEventHistoryEntry).timestamp,
        observationCount: Number((item as GlobalIntelEventHistoryEntry).observationCount) || 1,
      }))
      : [];
  } catch {
    return [];
  }
}

function loadEventDispositions(): Record<string, EventDisposition> {
  try {
    const saved = JSON.parse(localStorage.getItem(EVENT_DISPOSITIONS_KEY) || "{}") as unknown;
    return typeof saved === "object" && saved !== null && !Array.isArray(saved)
      ? saved as Record<string, EventDisposition>
      : {};
  } catch {
    return {};
  }
}

function loadMediaWatchRules(): MediaWatchRule[] {
  try {
    const saved = JSON.parse(localStorage.getItem(MEDIA_WATCH_RULES_KEY) || "[]") as unknown;
    return Array.isArray(saved) ? saved as MediaWatchRule[] : [];
  } catch {
    return [];
  }
}

function loadMediaTopicHistory(): MediaTopicHistoryEntry[] {
  try {
    const saved = JSON.parse(localStorage.getItem(MEDIA_TOPIC_HISTORY_KEY) || "[]") as unknown;
    return Array.isArray(saved) ? saved.map((item) => ({
      ...item as MediaTopicHistoryEntry,
      verificationHistory: Array.isArray((item as MediaTopicHistoryEntry).verificationHistory)
        ? (item as MediaTopicHistoryEntry).verificationHistory
        : [{
          status: (item as MediaTopicHistoryEntry).verificationStatus || "常规报道",
          timestamp: (item as MediaTopicHistoryEntry).lastChangedAt || (item as MediaTopicHistoryEntry).lastSeenAt,
        }],
    })) : [];
  } catch {
    return [];
  }
}

function mediaWatchRuleMatchesTopic(rule: MediaWatchRule, topic: GlobalMediaMonitorTopic) {
  if (rule.id === topic.id) return true;
  const haystack = `${topic.label} ${topic.headline} ${topic.keywords.join(" ")}`.toLocaleLowerCase();
  const keywords = [...new Set(rule.keywords.map((keyword) => keyword.trim()).filter(Boolean))];
  const matches = keywords.filter((keyword) => haystack.includes(keyword.toLocaleLowerCase())).length;
  return matches >= Math.min(2, keywords.length);
}

function mediaTopicSignature(topic: GlobalMediaMonitorTopic) {
  return `${topic.mentionCount}|${topic.sourceCount}|${topic.heatScore}|${topic.attentionScore}|${topic.spreadScore}|${topic.verificationStatus}|${topic.framingDivergence}`;
}

function mergeMediaTopicHistory(
  history: MediaTopicHistoryEntry[],
  topics: GlobalMediaMonitorTopic[],
  observedAt: string,
) {
  const byId = new Map(history.map((item) => [item.id, item]));
  for (const topic of topics) {
    let previous = byId.get(topic.id);
    if (!previous) {
      const semanticMatch = [...byId.values()]
        .map((item) => ({ item, similarity: globalMediaTopicSimilarity(topic, item) }))
        .sort((left, right) => right.similarity - left.similarity)[0];
      if (semanticMatch && semanticMatch.similarity >= 62) {
        previous = semanticMatch.item;
        byId.delete(previous.id);
      }
    }
    const changed = previous && (
      previous.mentionCount !== topic.mentionCount
      || previous.sourceCount !== topic.sourceCount
      || previous.heatScore !== topic.heatScore
      || previous.attentionScore !== topic.attentionScore
      || previous.spreadScore !== topic.spreadScore
      || previous.verificationStatus !== topic.verificationStatus
    );
    byId.set(topic.id, {
      id: topic.id,
      label: topic.label,
      headline: topic.headline,
      keywords: topic.keywords,
      sources: topic.sources,
      firstSeenAt: previous?.firstSeenAt || observedAt,
      lastSeenAt: observedAt,
      lastChangedAt: changed ? observedAt : previous?.lastChangedAt || observedAt,
      mentionCount: topic.mentionCount,
      sourceCount: topic.sourceCount,
      heatScore: topic.heatScore,
      attentionScore: topic.attentionScore,
      spreadScore: topic.spreadScore,
      verificationStatus: topic.verificationStatus,
      verificationHistory: previous?.verificationStatus !== topic.verificationStatus
        ? [
          ...(previous?.verificationHistory ?? []),
          { status: topic.verificationStatus, timestamp: observedAt },
        ].slice(-8)
        : previous?.verificationHistory ?? [{ status: topic.verificationStatus, timestamp: observedAt }],
    });
  }
  return [...byId.values()]
    .sort((left, right) => Date.parse(right.lastSeenAt) - Date.parse(left.lastSeenAt))
    .slice(0, 180);
}

function safeExternalUrl(value?: string) {
  if (!value) return "";
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:" || parsed.protocol === "http:"
      ? parsed.toString()
      : "";
  } catch {
    return "";
  }
}

function relativeTime(timestamp: string) {
  const delta = Date.now() - Date.parse(timestamp);
  if (!Number.isFinite(delta)) return "时间未知";
  const minutes = Math.max(0, Math.round(delta / 60_000));
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  return `${Math.round(hours / 24)} 天前`;
}

function recordValue(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function recordList(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => (
      typeof item === "object" && item !== null && !Array.isArray(item)
    ))
    : [];
}

function sourceLabel(source: string) {
  return SOURCE_LABELS[source] ?? source.replace(/[_-]+/g, " ");
}

function freshnessLabel(seconds: number) {
  if (seconds < 60) return `${Math.max(0, Math.round(seconds))} 秒前`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} 分钟前`;
  if (seconds < 86_400) return `${Math.round(seconds / 3600)} 小时前`;
  return `${Math.round(seconds / 86_400)} 天前`;
}

function sourceHealthDetails(snapshot: Record<string, unknown>) {
  const items = new Map<string, SourceHealthItem>();
  const sourceHealth = recordValue(snapshot.source_health);
  let healthy = 0;
  let total = Object.keys(sourceHealth).length;

  for (const [source, raw] of Object.entries(sourceHealth)) {
    const info = recordValue(raw);
    const rawStatus = typeof info.status === "string" ? info.status : "unknown";
    const failures = Number(info.failures ?? 0);
    const cooldown = Number(info.cooldown_remaining_s ?? 0);
    const isHealthy = rawStatus === "closed" || rawStatus === "ok" || rawStatus === "healthy";
    if (isHealthy) healthy += 1;
    const status = isHealthy ? "healthy" : rawStatus === "half-open" ? "degraded" : "error";
    const reason = status === "healthy"
      ? `连接正常${failures > 0 ? `，近期失败 ${failures} 次` : ""}`
      : status === "degraded"
        ? "正在恢复探测"
        : `熔断保护已开启${cooldown > 0 ? `，${Math.ceil(cooldown)} 秒后重试` : ""}`;
    items.set(source, {
      id: source,
      label: sourceLabel(source),
      status,
      statusLabel: status === "healthy" ? "正常" : status === "degraded" ? "恢复中" : "熔断",
      reason,
    });
  }

  const cacheFreshness = recordValue(snapshot.cache_freshness);
  for (const [source, raw] of Object.entries(cacheFreshness)) {
    const info = recordValue(raw);
    const seconds = Number(info.last_updated_s_ago);
    const isStale = info.is_stale === true;
    const existing = items.get(source);
    const freshness = Number.isFinite(seconds) ? freshnessLabel(seconds) : undefined;
    if (existing) {
      items.set(source, { ...existing, ...(freshness ? { freshness } : {}) });
      continue;
    }
    items.set(source, {
      id: source,
      label: sourceLabel(source),
      status: isStale ? "stale" : "healthy",
      statusLabel: isStale ? "缓存过期" : "缓存正常",
      reason: isStale ? "最新缓存已经超过有效期" : "缓存数据可用",
      ...(freshness ? { freshness } : {}),
    });
  }

  const crucix = recordValue(snapshot.crucix_intelligence);
  if (Object.keys(crucix).length) {
    const crucixHealth = recordValue(crucix.sourceHealth);
    const crucixFreshness = recordValue(crucix.freshness);
    const failed = Number(crucixHealth.failed ?? 0);
    const freshnessStatus = typeof crucixFreshness.status === "string"
      ? crucixFreshness.status
      : "unknown";
    const status: SourceHealthItem["status"] = freshnessStatus === "stale"
      ? "stale"
      : freshnessStatus === "fresh" && failed === 0 ? "healthy" : "degraded";
    const queried = Number(crucixHealth.queried ?? 0);
    const ok = Number(crucixHealth.ok ?? 0);
    const ageSeconds = typeof crucixFreshness.ageSeconds === "number"
      ? crucixFreshness.ageSeconds
      : Number.NaN;
    items.set("crucix", {
      id: "crucix",
      label: sourceLabel("crucix"),
      status,
      statusLabel: status === "healthy" ? "正常" : status === "stale" ? "数据过期" : "部分降级",
      reason: queried > 0 ? `${ok}/${queried} 个来源正常${failed > 0 ? `，${failed} 个失败` : ""}` : "等待 Crucix 首轮扫描",
      ...(Number.isFinite(ageSeconds) ? { freshness: freshnessLabel(ageSeconds) } : {}),
    });
    total += 1;
    if (status === "healthy") healthy += 1;
  }

  for (const [domain, raw] of Object.entries(snapshot)) {
    if (domain.startsWith("_") || domain === "source_health" || domain === "cache_freshness" || domain === "cache_stats") continue;
    const info = recordValue(raw);
    if (typeof info.error !== "string" || !info.error) continue;
    const timedOut = info._timeout === true;
    items.set(domain, {
      id: domain,
      label: sourceLabel(domain),
      status: timedOut ? "degraded" : "error",
      statusLabel: timedOut ? "超时" : "故障",
      reason: info.error,
    });
  }

  const rank: Record<SourceHealthItem["status"], number> = {
    error: 0,
    degraded: 1,
    stale: 2,
    healthy: 3,
  };
  const sortedItems = [...items.values()].sort((left, right) => (
    rank[left.status] - rank[right.status] || left.label.localeCompare(right.label, "zh-CN")
  ));
  const cacheStats = recordValue(snapshot.cache_stats);
  return {
    healthy,
    total,
    issueCount: sortedItems.filter((item) => item.status !== "healthy").length,
    items: sortedItems,
    cache: {
      active: Number(cacheStats.active_entries ?? 0),
      total: Number(cacheStats.total_entries ?? 0),
      expired: Number(cacheStats.expired_entries ?? 0),
    },
  };
}

function setMatches<T>(current: Set<T>, expected: T[]) {
  return current.size === expected.length && expected.every((value) => current.has(value));
}

function riskLevelLabel(level: string) {
  return RISK_LEVEL_LABELS[level.toUpperCase()] ?? (level || "监测中");
}

function strategicRisk(snapshot: Record<string, unknown>) {
  const posture = recordValue(snapshot.strategic_posture);
  const score = Number(posture.composite_score ?? posture.overall_score ?? posture.score);
  const rawLevel = typeof posture.risk_level === "string"
    ? posture.risk_level
    : typeof posture.overall_level === "string"
      ? posture.overall_level
      : typeof posture.level === "string"
        ? posture.level
        : "";
  return {
    score: Number.isFinite(score) ? score : undefined,
    level: riskLevelLabel(rawLevel),
    rawLevel: rawLevel.toUpperCase(),
  };
}

function localizedAlertMessage(alert: Record<string, unknown>) {
  const domain = typeof alert.domain === "string" ? alert.domain : "unknown";
  const value = Number(alert.value ?? 0);
  if (Array.isArray(alert.countries)) return `${value} 个国家超过不稳定风险阈值`;
  if (Array.isArray(alert.surges)) return `发现 ${value} 项军事活动激增`;
  if (Array.isArray(alert.corridors)) return `${value} 条海底光缆走廊风险升高`;
  if (Array.isArray(alert.hotspots)) return `${value} 个安全热点超过升级阈值`;
  if (domain === "space") return `地磁活动升高，当前 Kp=${value}`;
  if (domain === "infrastructure") return `${value} 起网络基础设施中断正在持续`;
  if (domain === "economic") return `航运压力指数升至 ${value}`;
  return typeof alert.message === "string" ? alert.message : "发现新的风险信号";
}

function strategicBriefing(snapshot: Record<string, unknown>) {
  const posture = recordValue(snapshot.strategic_posture);
  const alertDigest = recordValue(snapshot.alert_digest);
  const situationBrief = recordValue(snapshot.situation_brief);
  const risk = strategicRisk(snapshot);
  const domains: PostureDomain[] = Object.entries(recordValue(posture.domain_scores))
    .map(([id, raw]) => {
      const info = recordValue(raw);
      const score = Number(info.score ?? 0);
      return {
        id,
        label: POSTURE_DOMAIN_LABELS[id] ?? id,
        score: Number.isFinite(score) ? score : 0,
        level: riskLevelLabel(typeof info.level === "string" ? info.level : ""),
        signals: Array.isArray(info.signals)
          ? info.signals.filter((signal): signal is string => typeof signal === "string")
          : [],
      };
    })
    .sort((left, right) => right.score - left.score);
  const threats = recordList(posture.top_threats).map((threat, index) => ({
    id: `${String(threat.domain ?? "threat")}-${index}`,
    domain: POSTURE_DOMAIN_LABELS[String(threat.domain ?? "")] ?? String(threat.domain ?? "风险"),
    signal: typeof threat.signal === "string" ? threat.signal : "风险信号",
    score: Number(threat.domain_score ?? 0),
  }));
  const alerts: StrategicAlert[] = recordList(alertDigest.alerts).map((alert, index) => {
    const domain = typeof alert.domain === "string" ? alert.domain : "unknown";
    return {
      id: `${domain}-${index}`,
      domain,
      domainLabel: POSTURE_DOMAIN_LABELS[domain] ?? domain,
      priority: typeof alert.priority === "string" ? alert.priority : "medium",
      message: localizedAlertMessage(alert),
    };
  });
  const brief = typeof situationBrief.brief === "string" ? situationBrief.brief.trim() : "";
  const timestamp = typeof situationBrief.timestamp === "string"
    ? situationBrief.timestamp
    : typeof posture.timestamp === "string"
      ? posture.timestamp
      : "";
  return {
    ...risk,
    domains,
    threats,
    alerts,
    alertCount: Number(alertDigest.alert_count ?? alerts.length),
    priorityCounts: recordValue(alertDigest.by_priority),
    brief,
    briefParagraphs: brief ? brief.split(/\n\s*\n|\n/).filter(Boolean) : [],
    aiGenerated: situationBrief.ai_generated === true,
    model: typeof situationBrief.model === "string" ? situationBrief.model : "",
    timestamp,
  };
}

function trendLabel(value: string) {
  return TREND_LABELS[value] ?? value.replace(/[_-]+/g, " ");
}

function trendRadar(snapshot: Record<string, unknown>) {
  const weekly = recordValue(snapshot.weekly_trends);
  const convergence = recordValue(snapshot.signal_convergence);
  const anomalies: TemporalAnomaly[] = recordList(weekly.current_anomalies).map((anomaly, index) => ({
    id: `${String(anomaly.event_type ?? "anomaly")}-${String(anomaly.region ?? index)}`,
    metric: trendLabel(String(anomaly.event_type ?? anomaly.metric ?? "异常信号")),
    region: trendLabel(String(anomaly.region ?? "全球")),
    zScore: Number(anomaly.z_score ?? anomaly.deviation ?? 0),
    severity: String(anomaly.severity ?? "medium"),
    multiplier: Number(anomaly.multiplier ?? 0),
    observed: Number(anomaly.observed ?? 0),
    expected: Number(anomaly.expected ?? 0),
  }));
  const trends: VolatilityTrend[] = recordList(weekly.trends).map((trend, index) => ({
    id: `${String(trend.metric ?? "trend")}-${String(trend.region ?? index)}-${index}`,
    metric: trendLabel(String(trend.metric ?? "趋势指标")),
    region: trendLabel(String(trend.region ?? "全球")),
    volatility: Number(trend.volatility_cv ?? 0),
    mean: Number(trend.mean ?? 0),
    observations: Number(trend.observations ?? 0),
  }));
  const liveHotspots: ConvergenceHotspot[] = recordList(convergence.hotspots).map((hotspot, index) => {
    const signals = recordValue(hotspot.signals);
    return {
      id: `${String(hotspot.name ?? "hotspot")}-${index}`,
      label: trendLabel(String(hotspot.name ?? "热点")),
      latitude: Number(hotspot.lat ?? hotspot.latitude ?? 0),
      longitude: Number(hotspot.lon ?? hotspot.longitude ?? 0),
      score: Number(hotspot.convergence_score ?? 0),
      earthquakeCount: Number(signals.earthquakes ?? 0),
    };
  });
  const liveLabels = new Set(liveHotspots.map((hotspot) => hotspot.label));
  const hotspots = [
    ...liveHotspots,
    ...DEFAULT_CONVERGENCE_HOTSPOTS.filter((hotspot) => !liveLabels.has(hotspot.label)),
  ];
  return {
    anomalies,
    trends,
    hotspots,
    anomalyCount: Number(weekly.current_anomaly_count ?? anomalies.length),
    trendCount: Number(weekly.trend_count ?? trends.length),
    maxConvergence: hotspots.reduce((maximum, hotspot) => Math.max(maximum, hotspot.score), 0),
    timestamp: typeof weekly.timestamp === "string"
      ? weekly.timestamp
      : typeof convergence.timestamp === "string"
        ? convergence.timestamp
        : "",
  };
}

function inTimeWindow(timestamp: string, timeWindow: TimeWindow) {
  if (timeWindow === "all") return true;
  const parsed = Date.parse(timestamp);
  if (!Number.isFinite(parsed)) return false;
  const hours = timeWindow === "24h" ? 24 : 24 * 7;
  const span = hours * 60 * 60 * 1000;
  return parsed >= Date.now() - span && parsed <= Date.now() + span;
}

function mergeSnapshot(
  current: Record<string, unknown>,
  ...payloads: Array<Record<string, unknown>>
) {
  const next = { ...current };
  for (const payload of payloads) {
    for (const [key, value] of Object.entries(payload)) {
      next[key] = value;
    }
  }
  return next;
}

function matchesSeverity(severity: GlobalIntelSeverity, filter: SeverityFilter) {
  if (filter === "all") return true;
  if (filter === "priority") return severity === "critical" || severity === "high";
  return severity === filter;
}

function confidenceLabel(cluster?: GlobalIntelEventCluster) {
  if (!cluster || cluster.events.length === 1) return "单一来源";
  if (cluster.sources.length === 1) return "单源连续记录";
  if (cluster.confidence >= 80) return "高可信";
  if (cluster.confidence >= 60) return "交叉验证";
  return "待核验";
}

function recordKindLabel(event: GlobalIntelEvent) {
  if (event.recordKind === "observation") return "原始观测";
  if (event.recordKind === "news") return "新闻报道";
  return "异常事件";
}

function recordKindExplanation(event: GlobalIntelEvent) {
  if (event.recordKind === "observation") {
    return "这是传感器、行情或周期指标的当前读数，不等同于新闻，也未自动判定为异常事件。";
  }
  if (event.recordKind === "news") {
    return "这是公开来源的报道或通报。系统保留摘要和原始链接，但报道本身仍需结合其他来源核验。";
  }
  return "这是由异常阈值、轨迹规则、冲突或灾害记录触发的事件信号；它提示需要关注，不代表系统已确认因果关系。";
}

type EventMonitorState = "new" | "ongoing" | "resolved";
type EventFeedMode = "changes" | "unread" | "watching" | "all";
const CHANGE_FEED_LIMIT = 60;
const CHANGE_FEED_SOURCE_LIMIT = 8;
const EVENT_FEED_SEVERITY_RANK: Record<GlobalIntelSeverity, number> = {
  critical: 5,
  high: 4,
  medium: 3,
  low: 2,
  info: 1,
};

function eventMonitorState(
  event: GlobalIntelEvent,
  currentIdentities: Set<string>,
  history?: GlobalIntelEventHistoryEntry,
): EventMonitorState {
  if (!currentIdentities.has(globalIntelEventIdentity(event))) return "resolved";
  if (!history) return "ongoing";
  return history && (
    history.observationCount > 1
    || Date.now() - Date.parse(history.firstSeenAt) >= 10 * 60 * 1000
  ) ? "ongoing" : "new";
}

function eventMonitorLabel(state: EventMonitorState) {
  if (state === "new") return "新出现";
  if (state === "ongoing") return "持续中";
  return "已离开";
}

function eventRequiresAttention(
  event: GlobalIntelEvent,
  history: GlobalIntelEventHistoryEntry | undefined,
  disposition: EventDisposition | undefined,
  currentIdentities: Set<string>,
) {
  if (!history) return !disposition?.acknowledgedAt;
  const changedAt = Date.parse(history.lastChangedAt || history.firstSeenAt || event.timestamp);
  const acknowledgedChangeAt = Date.parse(
    disposition?.acknowledgedChangeAt || disposition?.acknowledgedAt || "",
  );
  if (!Number.isFinite(acknowledgedChangeAt) || acknowledgedChangeAt < changedAt) return true;
  return !currentIdentities.has(globalIntelEventIdentity(event))
    && Number.isFinite(Date.parse(history.resolvedAt || ""))
    && acknowledgedChangeAt < Date.parse(history.resolvedAt || "");
}

function clusterMonitorState(
  cluster: GlobalIntelEventCluster,
  currentIdentities: Set<string>,
  historyByIdentity: Map<string, GlobalIntelEventHistoryEntry>,
): EventMonitorState {
  const current = cluster.events.filter((event) => currentIdentities.has(globalIntelEventIdentity(event)));
  if (!current.length) return "resolved";
  return current.some((event) => eventMonitorState(
    event,
    currentIdentities,
    historyByIdentity.get(globalIntelEventIdentity(event)),
  ) === "ongoing") ? "ongoing" : "new";
}

function dispositionAcknowledged(
  event: GlobalIntelEvent | undefined,
  history: GlobalIntelEventHistoryEntry | undefined,
  disposition: EventDisposition | undefined,
  currentIdentities: Set<string>,
) {
  return Boolean(event && disposition?.acknowledgedAt && !eventRequiresAttention(
    event,
    history,
    disposition,
    currentIdentities,
  ));
}

function eventActivityTimestamp(
  event: GlobalIntelEvent,
  history?: GlobalIntelEventHistoryEntry,
) {
  const eventTimestamp = Date.parse(event.timestamp);
  const changedTimestamp = Date.parse(history?.lastChangedAt || "");
  if (!Number.isFinite(changedTimestamp)) return event.timestamp;
  if (!Number.isFinite(eventTimestamp) || changedTimestamp > eventTimestamp) {
    return history!.lastChangedAt;
  }
  return event.timestamp;
}

function pointInRegion(point: GlobalIntelPoint, region: IntelligenceRegion) {
  const longitudeMatches = region.west <= region.east
    ? point.longitude >= region.west && point.longitude <= region.east
    : point.longitude >= region.west || point.longitude <= region.east;
  return longitudeMatches && point.latitude >= region.south && point.latitude <= region.north;
}

const RISK_WEIGHT: Record<GlobalIntelSeverity, number> = {
  critical: 45,
  high: 25,
  medium: 12,
  low: 5,
  info: 2,
};

export function GlobalIntelligenceDashboard({
  dataSource,
  theme,
  refreshNonce,
  cacheIdentity,
  onRefresh,
  onContextChange,
}: {
  dataSource: GlobalIntelDataSource;
  theme: "light" | "dark";
  refreshNonce: number;
  cacheIdentity?: { userId: string; workspaceId: string };
  onRefresh(): void;
  onContextChange(value: Record<string, unknown>): void;
}) {
  const snapshotCache = useMemo(() => cacheIdentity
    ? createModSnapshotCache<Record<string, unknown>>({
        modId: "global-situation",
        userId: cacheIdentity.userId,
        workspaceId: cacheIdentity.workspaceId,
        resourceKey: "overview",
        schemaVersion: 1,
        maxBytes: 8 * 1024 * 1024,
      })
    : undefined, [cacheIdentity?.userId, cacheIdentity?.workspaceId]);
  const [snapshot, setSnapshot] = useState<Record<string, unknown>>(() => (
    cacheIdentity ? snapshotCache?.read()?.value ?? {} : {}
  ));
  const [militaryTrackHistory, setMilitaryTrackHistory] = useState(loadMilitaryTrackHistory);
  const [eventHistory, setEventHistory] = useState(loadEventHistory);
  const [eventDispositions, setEventDispositions] = useState(loadEventDispositions);
  const [mediaWatchRules, setMediaWatchRules] = useState(loadMediaWatchRules);
  const [mediaTopicHistory, setMediaTopicHistory] = useState(loadMediaTopicHistory);
  const [eventHistoryObservedAt, setEventHistoryObservedAt] = useState("");
  const [attentionBaselineReady, setAttentionBaselineReady] = useState(
    () => localStorage.getItem(EVENT_ATTENTION_BASELINE_KEY) === "ready",
  );
  const [riskClock, setRiskClock] = useState(() => Date.now());
  const [status, setStatus] = useState<"connecting" | "live" | "degraded">("connecting");
  const [error, setError] = useState("");
  const [activeLayers, setActiveLayers] = useState(DEFAULT_LAYERS);
  const [categoryFilter, setCategoryFilter] = useState<"all" | GlobalIntelCategory>("all");
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>("all");
  const [timeWindow, setTimeWindow] = useState<TimeWindow>("24h");
  const [query, setQuery] = useState("");
  const [showObservations, setShowObservations] = useState(false);
  const [eventFeedMode, setEventFeedMode] = useState<EventFeedMode>("changes");
  const [mapMode, setMapMode] = useState<IntelligenceMapMode>("signals");
  const [activeRouteKinds, setActiveRouteKinds] = useState<Set<GlobalIntelRoute["kind"]>>(
    () => new Set(ROUTE_FILTERS.map((item) => item.kind)),
  );
  const [showCountryRisk, setShowCountryRisk] = useState(true);
  const [selectedRegion, setSelectedRegion] = useState<IntelligenceRegion>();
  const [playbackCursor, setPlaybackCursor] = useState(100);
  const [playbackPlaying, setPlaybackPlaying] = useState(false);
  const [selectedPointId, setSelectedPointId] = useState("");
  const [selectedEventId, setSelectedEventId] = useState("");
  const [selectedRouteId, setSelectedRouteId] = useState("");
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [watchedRegions, setWatchedRegions] = useState<SavedWatchRegion[]>(loadWatchRegions);
  const [routeAlertStates, setRouteAlertStates] = useState(loadRouteAlertStates);
  const [watchPanelOpen, setWatchPanelOpen] = useState(false);
  const [routeAlertPanelOpen, setRouteAlertPanelOpen] = useState(false);
  const [presetMenuOpen, setPresetMenuOpen] = useState(false);
  const [healthPanelOpen, setHealthPanelOpen] = useState(false);
  const [briefPanelOpen, setBriefPanelOpen] = useState(false);
  const [trendPanelOpen, setTrendPanelOpen] = useState(false);
  const [mediaPanelOpen, setMediaPanelOpen] = useState(false);
  const [mapFocus, setMapFocus] = useState<IntelligenceMapFocus>();

  useEffect(() => {
    localStorage.setItem(WATCH_REGIONS_KEY, JSON.stringify(watchedRegions));
  }, [watchedRegions]);

  useEffect(() => {
    localStorage.setItem(ROUTE_ALERTS_KEY, JSON.stringify(routeAlertStates));
  }, [routeAlertStates]);

  useEffect(() => {
    sessionStorage.setItem(MILITARY_TRACKS_KEY, JSON.stringify(militaryTrackHistory));
  }, [militaryTrackHistory]);

  useEffect(() => {
    localStorage.setItem(EVENT_HISTORY_KEY, JSON.stringify(eventHistory));
  }, [eventHistory]);

  useEffect(() => {
    localStorage.setItem(EVENT_DISPOSITIONS_KEY, JSON.stringify(eventDispositions));
  }, [eventDispositions]);

  useEffect(() => {
    localStorage.setItem(MEDIA_WATCH_RULES_KEY, JSON.stringify(mediaWatchRules));
  }, [mediaWatchRules]);

  useEffect(() => {
    localStorage.setItem(MEDIA_TOPIC_HISTORY_KEY, JSON.stringify(mediaTopicHistory));
  }, [mediaTopicHistory]);

  useEffect(() => {
    if (!snapshotCache) return;
    if (!Object.keys(snapshot).length) return;
    const timer = window.setTimeout(() => {
      snapshotCache.write(
        snapshot,
        typeof snapshot.timestamp === "string" ? snapshot.timestamp : undefined,
      );
    }, 800);
    return () => window.clearTimeout(timer);
  }, [snapshot, snapshotCache]);

  useEffect(() => {
    if (!("military_flights" in snapshot)) return;
    const timestamp = typeof snapshot.timestamp === "string" ? new Date(snapshot.timestamp) : new Date();
    setMilitaryTrackHistory((current) => updateGlobalIntelMilitaryTrackHistory(
      current,
      snapshot,
      Number.isFinite(timestamp.getTime()) ? timestamp : new Date(),
    ));
  }, [snapshot]);

  useEffect(() => {
    const timer = window.setInterval(() => setRiskClock(Date.now()), 5 * 60 * 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    let active = true;
    setStatus(Object.keys(snapshot).length ? "degraded" : "connecting");
    setError("");
    setProgress({ done: 0, total: 0 });

    const loadSnapshot = (
      request: Promise<Record<string, unknown>>,
      quiet = false,
    ) => {
      void request.then((payload) => {
        if (!active) return;
        setSnapshot((current) => mergeSnapshot(current, payload));
        const done = Number(payload._done);
        const total = Number(payload._total);
        if (Number.isFinite(done) && Number.isFinite(total)) setProgress({ done, total });
        if (payload._static === true) setStatus("degraded");
      }).catch(() => {
        if (active && !quiet) setError(Object.keys(snapshot).length
          ? "更新失败，当前为上次数据"
          : "全球情报静态数据暂时不可用");
      });
    };
    loadSnapshot(dataSource.staticSnapshot());
    loadSnapshot(
      dataSource.crucixSnapshot().then((payload) => ({ crucix_intelligence: payload })),
      true,
    );

    const close = dataSource.subscribe((payload) => {
      if (!active) return;
      setSnapshot((current) => mergeSnapshot(current, payload));
      const done = Number(payload._done);
      const total = Number(payload._total);
      if (Number.isFinite(done) && Number.isFinite(total)) setProgress({ done, total });
    }, (next) => active && setStatus(next));

    return () => {
      active = false;
      close();
    };
  }, [dataSource, refreshNonce, snapshotCache]);

  const points = useMemo(() => normalizeGlobalIntelPoints(snapshot), [snapshot]);
  const events = useMemo(
    () => normalizeGlobalIntelEvents(snapshot, militaryTrackHistory),
    [militaryTrackHistory, snapshot],
  );
  const dataSettlementComplete = progress.total > 0 && progress.done >= progress.total;
  useEffect(() => {
    if (!events.length) return;
    if (progress.total > 0 && progress.done < progress.total) return;
    const observedAt = typeof snapshot.timestamp === "string"
      ? snapshot.timestamp
      : new Date().toISOString();
    setEventHistory((current) => mergeGlobalIntelEventHistory(current, events, observedAt));
    setEventHistoryObservedAt(observedAt);
  }, [events, progress.done, progress.total, snapshot.timestamp]);
  const eventTimeline = useMemo(() => {
    const merged = new Map<string, GlobalIntelEvent>();
    for (const event of eventHistory) merged.set(globalIntelEventIdentity(event), event);
    for (const event of events) merged.set(globalIntelEventIdentity(event), event);
    return [...merged.values()].sort((left, right) => Date.parse(right.timestamp) - Date.parse(left.timestamp));
  }, [eventHistory, events]);
  const currentEventIdentities = useMemo(
    () => new Set(events.map(globalIntelEventIdentity)),
    [events],
  );
  const historyByIdentity = useMemo(
    () => new Map(eventHistory.map((event) => [globalIntelEventIdentity(event), event])),
    [eventHistory],
  );
  const routes = useMemo(() => normalizeGlobalIntelRoutes(snapshot), [snapshot]);
  const actionableEvents = useMemo(
    () => eventTimeline.filter(isActionableGlobalIntelEvent),
    [eventTimeline],
  );
  const currentActionableEvents = useMemo(
    () => events.filter(isActionableGlobalIntelEvent),
    [events],
  );
  useEffect(() => {
    if (attentionBaselineReady || !actionableEvents.length) return;
    if (progress.total > 0 && progress.done < progress.total) return;
    const baselineAt = typeof snapshot.timestamp === "string"
      ? snapshot.timestamp
      : new Date().toISOString();
    if (eventHistoryObservedAt !== baselineAt) return;
    setEventDispositions((current) => {
      const nextState = { ...current };
      for (const event of actionableEvents) {
        const identity = globalIntelEventIdentity(event);
        if (!identity) continue;
        nextState[identity] = {
          ...(nextState[identity] ?? {}),
          acknowledgedAt: nextState[identity]?.acknowledgedAt || baselineAt,
          acknowledgedChangeAt: historyByIdentity.get(identity)?.lastChangedAt || baselineAt,
        };
      }
      return nextState;
    });
    localStorage.setItem(EVENT_ATTENTION_BASELINE_KEY, "ready");
    setAttentionBaselineReady(true);
  }, [actionableEvents, attentionBaselineReady, eventHistoryObservedAt, historyByIdentity, progress.done, progress.total, snapshot.timestamp]);
  const observationEvents = useMemo(
    () => events.filter((event) => !isActionableGlobalIntelEvent(event)),
    [events],
  );
  const routeImpacts = useMemo(
    () => calculateGlobalIntelRouteImpacts(currentActionableEvents, points, routes, riskClock),
    [currentActionableEvents, points, riskClock, routes],
  );
  const routesWithRisk = useMemo(() => {
    const impactsByRoute = new Map<string, typeof routeImpacts>();
    for (const impact of routeImpacts) {
      impactsByRoute.set(impact.routeId, [...(impactsByRoute.get(impact.routeId) ?? []), impact]);
    }
    return routes.map((route) => {
      const impacts = impactsByRoute.get(route.id) ?? [];
      return {
        ...route,
        riskScore: impacts.reduce((maximum, impact) => Math.max(maximum, impact.riskScore), 0),
        impactCount: impacts.length,
      };
    });
  }, [routeImpacts, routes]);
  const visibleRoutes = useMemo(
    () => routesWithRisk.filter((route) => activeRouteKinds.has(route.kind)),
    [activeRouteKinds, routesWithRisk],
  );
  const affectedRouteCount = routesWithRisk.filter((route) => (route.riskScore ?? 0) > 0).length;
  const marketReactions = useMemo(
    () => calculateGlobalIntelMarketReactions(snapshot, routesWithRisk),
    [routesWithRisk, snapshot],
  );
  const marketConfirmedRouteCount = new Set(
    marketReactions.filter((reaction) => reaction.status === "confirmed").map((reaction) => reaction.routeId),
  ).size;
  const routeAlerts = useMemo(
    () => calculateGlobalIntelRouteAlerts(routesWithRisk, routeImpacts, marketReactions),
    [marketReactions, routeImpacts, routesWithRisk],
  );
  const highRouteAlertCount = routeAlerts.filter((alert) => alert.level === "critical" || alert.level === "high").length;
  useEffect(() => {
    setRouteAlertStates((current) => reconcileGlobalIntelRouteAlertStates(current, routeAlerts));
  }, [routeAlerts]);
  const newRouteAlertCount = routeAlerts.filter((alert) => (
    (routeAlertStates[alert.id]?.disposition ?? "new") === "new"
  )).length;
  const recentResolvedRouteAlerts = Object.values(routeAlertStates).filter((state) => (
    !state.active
    && state.change === "resolved"
    && riskClock - Date.parse(state.updatedAt) <= 24 * 60 * 60 * 1000
  ));
  const eventCategoryCounts = useMemo(() => {
    const counts = Object.fromEntries(
      EVENT_FILTER_CATEGORIES.map((category) => [category, 0]),
    ) as Record<GlobalIntelCategory, number>;
    for (const event of actionableEvents.filter((item) => inTimeWindow(
      eventActivityTimestamp(item, historyByIdentity.get(globalIntelEventIdentity(item))),
      timeWindow,
    ))) {
      counts[event.category] = (counts[event.category] ?? 0) + 1;
    }
    return counts;
  }, [actionableEvents, historyByIdentity, timeWindow]);
  const pointById = useMemo(() => new Map(points.map((point) => [point.id, point])), [points]);
  const visiblePoints = useMemo(
    () => points.filter((point) => (
      activeLayers.has(point.category)
      && (!selectedRegion || pointInRegion(point, selectedRegion))
    )),
    [activeLayers, points, selectedRegion],
  );
  const filteredEvents = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    return eventTimeline.filter((event) => {
      if (!showObservations && !isActionableGlobalIntelEvent(event)) return false;
      if (categoryFilter !== "all" && event.category !== categoryFilter) return false;
      if (!matchesSeverity(event.severity, severityFilter)) return false;
      if (!inTimeWindow(
        eventActivityTimestamp(event, historyByIdentity.get(globalIntelEventIdentity(event))),
        timeWindow,
      )) return false;
      if (selectedRegion) {
        const point = event.pointId ? pointById.get(event.pointId) : undefined;
        if (!point || !pointInRegion(point, selectedRegion)) return false;
      }
      if (!normalizedQuery) return true;
      return `${event.title} ${event.detail} ${event.source} ${event.country ?? ""}`
        .toLocaleLowerCase()
        .includes(normalizedQuery);
    });
  }, [categoryFilter, eventTimeline, historyByIdentity, pointById, query, selectedRegion, severityFilter, showObservations, timeWindow]);
  const changeFocusedEvents = useMemo(() => {
    const dispositionFilteredEvents = eventFeedMode === "watching"
      ? filteredEvents.filter((event) => eventDispositions[globalIntelEventIdentity(event)]?.watching)
      : eventFeedMode === "unread"
        ? filteredEvents.filter((event) => attentionBaselineReady && eventRequiresAttention(
          event,
          historyByIdentity.get(globalIntelEventIdentity(event)),
          eventDispositions[globalIntelEventIdentity(event)],
          currentEventIdentities,
        ))
        : filteredEvents;
    if (eventFeedMode === "watching" || eventFeedMode === "unread") {
      return [...dispositionFilteredEvents].sort((left, right) => {
        const leftIdentity = globalIntelEventIdentity(left);
        const rightIdentity = globalIntelEventIdentity(right);
        const leftNeedsAttention = eventRequiresAttention(
          left,
          historyByIdentity.get(leftIdentity),
          eventDispositions[leftIdentity],
          currentEventIdentities,
        );
        const rightNeedsAttention = eventRequiresAttention(
          right,
          historyByIdentity.get(rightIdentity),
          eventDispositions[rightIdentity],
          currentEventIdentities,
        );
        return Number(rightNeedsAttention) - Number(leftNeedsAttention)
          || Date.parse(historyByIdentity.get(rightIdentity)?.lastChangedAt ?? right.timestamp)
            - Date.parse(historyByIdentity.get(leftIdentity)?.lastChangedAt ?? left.timestamp);
      });
    }
    if (eventFeedMode === "all") {
      return dispositionFilteredEvents;
    }
    const changeCutoff = riskClock - 6 * 60 * 60 * 1000;
    const stateRank: Record<EventMonitorState, number> = { new: 3, resolved: 2, ongoing: 1 };
    const candidates = dispositionFilteredEvents
      .map((event) => {
        const history = historyByIdentity.get(globalIntelEventIdentity(event));
        const state = eventMonitorState(event, currentEventIdentities, history);
        return { event, history, state };
      })
      .filter(({ event, history, state }) => (
        state !== "ongoing"
        || event.severity === "critical"
        || event.severity === "high"
        || Boolean(history && Date.parse(history.lastChangedAt) >= changeCutoff)
      ))
      .sort((left, right) => (
        stateRank[right.state] - stateRank[left.state]
        || EVENT_FEED_SEVERITY_RANK[right.event.severity] - EVENT_FEED_SEVERITY_RANK[left.event.severity]
        || Date.parse(right.history?.lastChangedAt ?? right.event.timestamp)
          - Date.parse(left.history?.lastChangedAt ?? left.event.timestamp)
      ));
    const sourceCounts = new Map<string, number>();
    const selected: GlobalIntelEvent[] = [];
    for (const { event } of candidates) {
      const sourceKey = `${event.category}:${event.source}`;
      const sourceCount = sourceCounts.get(sourceKey) ?? 0;
      if (event.severity !== "critical" && sourceCount >= CHANGE_FEED_SOURCE_LIMIT) continue;
      selected.push(event);
      sourceCounts.set(sourceKey, sourceCount + 1);
      if (selected.length >= CHANGE_FEED_LIMIT) break;
    }
    return selected;
  }, [attentionBaselineReady, currentEventIdentities, eventDispositions, eventFeedMode, filteredEvents, historyByIdentity, riskClock]);
  const playbackRange = useMemo(() => {
    const timestamps = changeFocusedEvents.map((event) => Date.parse(eventActivityTimestamp(
      event,
      historyByIdentity.get(globalIntelEventIdentity(event)),
    ))).filter(Number.isFinite);
    return timestamps.length
      ? { start: Math.min(...timestamps), end: Math.max(...timestamps) }
      : { start: Date.now(), end: Date.now() };
  }, [changeFocusedEvents, historyByIdentity]);
  const playbackTime = playbackRange.start
    + (playbackRange.end - playbackRange.start) * playbackCursor / 100;
  const visibleEvents = useMemo(
    () => changeFocusedEvents.filter((event) => Date.parse(eventActivityTimestamp(
      event,
      historyByIdentity.get(globalIntelEventIdentity(event)),
    )) <= playbackTime),
    [changeFocusedEvents, historyByIdentity, playbackTime],
  );
  const eventClusters = useMemo(() => clusterGlobalIntelEvents(actionableEvents), [actionableEvents]);
  const visibleEventClusters = useMemo(
    () => clusterGlobalIntelEvents(visibleEvents),
    [visibleEvents],
  );
  const countryRisk = useMemo(() => {
    const risk: Record<string, number> = {};
    for (const event of currentActionableEvents.filter((item) => inTimeWindow(item.timestamp, "24h"))) {
      if (!event.countryCode) continue;
      risk[event.countryCode] = Math.min(100, (risk[event.countryCode] ?? 0) + RISK_WEIGHT[event.severity]);
    }
    return risk;
  }, [currentActionableEvents]);
  const selectedEvent = eventTimeline.find((event) => event.id === selectedEventId);
  const selectedCluster = selectedEvent
    ? eventClusters.find((cluster) => cluster.events.some((event) => event.id === selectedEventId))
      ?? clusterGlobalIntelEvents(actionableEvents.filter((event) => (
        event.id === selectedEventId
        || (event.category === selectedEvent.category
          && event.countryCode === selectedEvent.countryCode
          && Math.abs(Date.parse(event.timestamp) - Date.parse(selectedEvent.timestamp)) <= 18 * 60 * 60 * 1000)
      ))).find((cluster) => cluster.events.some((event) => event.id === selectedEventId))
    : undefined;
  const selectedPoint = points.find((point) => point.id === selectedPointId);
  const selectedFacts = selectedEvent?.facts ?? selectedPoint?.facts;
  const selectedContent = selectedEvent?.content ?? selectedPoint?.content;
  const selectedHistory = selectedEvent
    ? historyByIdentity.get(globalIntelEventIdentity(selectedEvent))
    : undefined;
  const selectedEventState = selectedEvent
    ? eventMonitorState(selectedEvent, currentEventIdentities, selectedHistory)
    : undefined;
  const selectedEventImpacts = selectedEvent
    ? routeImpacts
      .filter((impact) => impact.eventId === selectedEvent.id)
      .flatMap((impact) => {
        const route = routesWithRisk.find((item) => item.id === impact.routeId);
        return route ? [{ impact, route }] : [];
      })
    : [];
  const visibleClusterMonitorStates = visibleEventClusters.map((cluster) => (
    clusterMonitorState(cluster, currentEventIdentities, historyByIdentity)
  ));
  const newEventCount = visibleClusterMonitorStates.filter((state) => state === "new").length;
  const ongoingEventCount = visibleClusterMonitorStates.filter((state) => state === "ongoing").length;
  const recentlyResolvedEventCount = visibleClusterMonitorStates.filter((state) => state === "resolved").length;
  const unacknowledgedEventCount = useMemo(() => clusterGlobalIntelEvents(filteredEvents).filter((cluster) => (
    cluster.events.some((event) => attentionBaselineReady && eventRequiresAttention(
      event,
      historyByIdentity.get(globalIntelEventIdentity(event)),
      eventDispositions[globalIntelEventIdentity(event)],
      currentEventIdentities,
    ))
  )).length, [attentionBaselineReady, currentEventIdentities, eventDispositions, filteredEvents, historyByIdentity]);
  const watchingEventCount = useMemo(() => clusterGlobalIntelEvents(filteredEvents).filter((cluster) => (
    cluster.events.some((event) => eventDispositions[globalIntelEventIdentity(event)]?.watching)
  )).length, [eventDispositions, filteredEvents]);
  const watchingAttentionCount = useMemo(() => clusterGlobalIntelEvents(filteredEvents).filter((cluster) => (
    cluster.events.some((event) => {
      const identity = globalIntelEventIdentity(event);
      const disposition = eventDispositions[identity];
      return disposition?.watching && attentionBaselineReady && eventRequiresAttention(
        event,
        historyByIdentity.get(identity),
        disposition,
        currentEventIdentities,
      );
    })
  )).length, [attentionBaselineReady, currentEventIdentities, eventDispositions, filteredEvents, historyByIdentity]);
  const selectedEventIdentity = selectedEvent ? globalIntelEventIdentity(selectedEvent) : "";
  const selectedEventDisposition = selectedEventIdentity
    ? eventDispositions[selectedEventIdentity]
    : undefined;
  const selectedEventAcknowledged = dispositionAcknowledged(
    selectedEvent,
    selectedHistory,
    selectedEventDisposition,
    currentEventIdentities,
  );
  const selectedRoute = routesWithRisk.find((route) => route.id === selectedRouteId);
  const selectedRouteImpacts = routeImpacts.filter((impact) => impact.routeId === selectedRouteId);
  const selectedRouteEvents = selectedRouteImpacts
    .map((impact) => ({ impact, event: eventTimeline.find((event) => event.id === impact.eventId) }))
    .filter((item): item is { impact: typeof routeImpacts[number]; event: GlobalIntelEvent } => Boolean(item.event));
  const selectedRoutePrimaryImpact = selectedRouteImpacts[0];
  const selectedRouteMarketReactions = marketReactions.filter((reaction) => reaction.routeId === selectedRouteId);
  const selectedRouteAlert = routeAlerts.find((alert) => alert.routeId === selectedRouteId);
  const watchedRegionViews = useMemo(() => watchedRegions.map((region) => {
    const baseline = new Set(region.baselinePointIds);
    const coveredPoints = points.filter((point) => pointInRegion(point, region.bounds));
    return {
      ...region,
      coveredPointCount: coveredPoints.length,
      alertCount: coveredPoints.filter((point) => !baseline.has(point.id)).length,
    };
  }), [points, watchedRegions]);
  const mapWatchRegions = useMemo<IntelligenceWatchRegion[]>(
    () => watchedRegionViews.map((region) => ({
      id: region.id,
      name: region.name,
      bounds: region.bounds,
      alertCount: region.alertCount,
    })),
    [watchedRegionViews],
  );
  const totalWatchAlerts = watchedRegionViews.reduce((sum, region) => sum + region.alertCount, 0);
  const health = useMemo(() => sourceHealthDetails(snapshot), [snapshot]);
  const activePreset = useMemo(() => SITUATION_PRESETS.find((preset) => (
    setMatches(activeLayers, preset.activeLayers)
    && setMatches(activeRouteKinds, preset.activeRouteKinds)
    && categoryFilter === preset.categoryFilter
    && severityFilter === preset.severityFilter
    && timeWindow === preset.timeWindow
    && mapMode === preset.mapMode
    && showCountryRisk === preset.showCountryRisk
  )), [activeLayers, activeRouteKinds, categoryFilter, mapMode, severityFilter, showCountryRisk, timeWindow]);
  const briefing = useMemo(() => strategicBriefing(snapshot), [snapshot]);
  const trend = useMemo(() => trendRadar(snapshot), [snapshot]);
  const mediaMonitor = useMemo(() => normalizeGlobalMediaMonitor(snapshot), [snapshot]);
  const mediaAttentionTopics = useMemo(() => [...mediaMonitor.topics].sort((left, right) => (
    right.attentionScore - left.attentionScore
    || right.heatScore - left.heatScore
    || right.spreadScore - left.spreadScore
  )), [mediaMonitor.topics]);
  useEffect(() => {
    if (!mediaMonitor.topics.length || !mediaMonitor.timestamp) return;
    setMediaTopicHistory((current) => mergeMediaTopicHistory(
      current,
      mediaMonitor.topics,
      mediaMonitor.timestamp,
    ));
  }, [mediaMonitor.timestamp, mediaMonitor.topics]);
  const mediaAnnotationByEventId = useMemo(() => new Map(events
    .filter((event) => event.recordKind === "news")
    .flatMap((event) => {
      const annotation = findGlobalMediaMonitorAnnotation(snapshot, event);
      return annotation ? [[event.id, annotation] as const] : [];
    })), [events, snapshot]);
  const risk = briefing;
  const highPriorityEventCount = currentActionableEvents.filter((event) => (
    inTimeWindow(event.timestamp, "24h")
    && (event.severity === "critical" || event.severity === "high")
  )).length;
  const highPriorityCount = highPriorityEventCount + highRouteAlertCount;
  const lastUpdate = typeof snapshot.timestamp === "string" ? snapshot.timestamp : "";
  const selectedMediaAnnotation = selectedEvent
    ? mediaAnnotationByEventId.get(selectedEvent.id)
      ?? findGlobalMediaMonitorAnnotation(snapshot, selectedEvent)
    : undefined;
  const selectedMediaTopic = findGlobalMediaMonitorTopic(mediaMonitor, selectedMediaAnnotation);
  const watchedMediaTopics = useMemo(() => mediaMonitor.topics.filter((topic) => (
    mediaWatchRules.some((rule) => mediaWatchRuleMatchesTopic(rule, topic))
  )), [mediaMonitor.topics, mediaWatchRules]);
  const watchedMediaTopicChanges = useMemo(() => watchedMediaTopics.filter((topic) => {
    const rule = mediaWatchRules.find((item) => mediaWatchRuleMatchesTopic(item, topic));
    return Boolean(rule?.baselineSignature && rule.baselineSignature !== mediaTopicSignature(topic));
  }), [mediaWatchRules, watchedMediaTopics]);
  useEffect(() => {
    if (!mediaMonitor.topics.length || !mediaWatchRules.some((rule) => !rule.baselineSignature)) return;
    setMediaWatchRules((current) => current.map((rule) => {
      if (rule.baselineSignature) return rule;
      const topic = mediaMonitor.topics.find((item) => mediaWatchRuleMatchesTopic(rule, item));
      return topic ? { ...rule, baselineSignature: mediaTopicSignature(topic) } : rule;
    }));
  }, [mediaMonitor.topics, mediaWatchRules]);
  const selectedMediaTopicWatched = Boolean(selectedMediaTopic && mediaWatchRules.some((rule) => (
    mediaWatchRuleMatchesTopic(rule, selectedMediaTopic)
  )));
  const selectedMediaTopicHistory = selectedMediaTopic
    ? mediaTopicHistory.find((item) => item.id === selectedMediaTopic.id)
    : undefined;
  const selectedMediaVerificationEvolution = useMemo(() => {
    const sourceTimeline = selectedMediaTopic?.verificationTimeline ?? [];
    const historyTimeline = selectedMediaTopicHistory?.verificationHistory ?? [];
    return [
      ...historyTimeline.map((step) => ({
        status: step.status,
        flag: "history",
        timestamp: step.timestamp,
        source: "浏览器历史",
        title: "主题核验状态发生变化",
      })),
      ...sourceTimeline,
    ].filter((step, index, items) => items.findIndex((candidate) => (
      candidate.status === step.status
      && candidate.timestamp === step.timestamp
      && candidate.source === step.source
    )) === index).sort((left, right) => {
      const leftTime = Date.parse(left.timestamp);
      const rightTime = Date.parse(right.timestamp);
      return (Number.isFinite(leftTime) ? leftTime : 0) - (Number.isFinite(rightTime) ? rightTime : 0);
    });
  }, [selectedMediaTopic, selectedMediaTopicHistory]);
  const similarMediaTopics = useMemo(() => {
    if (!selectedMediaTopic) return [];
    return mediaTopicHistory
      .filter((item) => item.id !== selectedMediaTopic.id)
      .map((item) => ({
        topic: item,
        similarity: globalMediaTopicSimilarity(selectedMediaTopic, item),
      }))
      .filter((item) => item.similarity >= 24)
      .sort((left, right) => right.similarity - left.similarity)
      .slice(0, 4);
  }, [mediaTopicHistory, selectedMediaTopic]);

  useEffect(() => {
    if (!playbackPlaying) return;
    const timer = window.setInterval(() => {
      setPlaybackCursor((current) => {
        if (current >= 100) {
          setPlaybackPlaying(false);
          return 100;
        }
        return Math.min(100, current + 2);
      });
    }, 360);
    return () => window.clearInterval(timer);
  }, [playbackPlaying]);

  useEffect(() => {
    onContextChange({
      streamStatus: status,
      progress,
      pointCount: points.length,
      visiblePointCount: visiblePoints.length,
      eventCount: eventTimeline.length,
      historicalEventCount: eventHistory.length,
      actionableEventCount: currentActionableEvents.length,
      observationCount: observationEvents.length,
      visibleEventCount: visibleEvents.length,
      eventClusterCount: eventClusters.length,
      visibleEventClusterCount: visibleEventClusters.length,
      eventLifecycle: {
        new: newEventCount,
        ongoing: ongoingEventCount,
        recentlyResolved: recentlyResolvedEventCount,
        unacknowledged: unacknowledgedEventCount,
        watching: watchingEventCount,
        watchingAttention: watchingAttentionCount,
      },
      highPriorityCount,
      situationPreset: activePreset?.id ?? "custom",
      activeLayers: [...activeLayers],
      filters: { categoryFilter, severityFilter, timeWindow, query, showObservations, eventFeedMode },
      mapMode,
      routes: {
        visible: activeRouteKinds.size > 0,
        count: visibleRoutes.length,
        total: routes.length,
        affected: affectedRouteCount,
        marketConfirmed: marketConfirmedRouteCount,
        alerts: routeAlerts.length,
        highAlerts: highRouteAlertCount,
        kinds: [...activeRouteKinds],
      },
      countryRisk: { visible: showCountryRisk, countries: countryRisk },
      selectedRegion: selectedRegion ?? null,
      watchedRegions: watchedRegionViews.map((region) => ({
        id: region.id,
        name: region.name,
        bounds: region.bounds,
        coveredPointCount: region.coveredPointCount,
        alertCount: region.alertCount,
      })),
      playback: { cursor: playbackCursor, playing: playbackPlaying, timestamp: new Date(playbackTime).toISOString() },
      selectedEvent: selectedEvent ?? null,
      selectedPoint: selectedPoint ?? null,
      selectedRoute: selectedRoute ?? null,
      sourceHealth: {
        healthy: health.healthy,
        total: health.total,
        issueCount: health.issueCount,
        cache: health.cache,
      },
      strategicBriefing: {
        score: briefing.score ?? null,
        level: briefing.level,
        alertCount: briefing.alertCount,
        topDomains: briefing.domains.slice(0, 3),
        topThreats: briefing.threats.slice(0, 5),
        brief: briefing.brief || null,
        timestamp: briefing.timestamp || null,
      },
      trendRadar: {
        anomalyCount: trend.anomalyCount,
        trendCount: trend.trendCount,
        maxConvergence: trend.maxConvergence,
        anomalies: trend.anomalies.slice(0, 5),
        hotspots: trend.hotspots,
        focusedHotspot: mapFocus ?? null,
      },
      mediaMonitor: {
        analyzedItems: mediaMonitor.summary.analyzedItems,
        sourceCount: mediaMonitor.summary.sourceCount,
        languageCount: mediaMonitor.summary.languageCount,
        topicCount: mediaMonitor.summary.topicCount,
        heatVelocityPct: mediaMonitor.summary.heatVelocityPct,
        spreadScore: mediaMonitor.summary.spreadScore,
        sentiment: mediaMonitor.summary.sentiment,
        crossLanguageTopicCount: mediaMonitor.summary.crossLanguageTopicCount,
        flaggedTopicCount: mediaMonitor.summary.flaggedTopicCount,
        reversalTopicCount: mediaMonitor.summary.reversalTopicCount,
        divergentTopicCount: mediaMonitor.summary.divergentTopicCount,
        attentionTopicCount: mediaMonitor.summary.attentionTopicCount,
        watchRuleCount: mediaWatchRules.length,
        watchedTopicCount: watchedMediaTopics.length,
        watchedTopicChangeCount: watchedMediaTopicChanges.length,
        topTopics: mediaAttentionTopics.slice(0, 6),
      },
      lastUpdate: lastUpdate || null,
      events: visibleEvents.slice(0, 30),
      dataContract: GLOBAL_INTELLIGENCE_CONTRACT,
      source: "world-intel-mcp",
    });
  }, [activeLayers, activePreset?.id, activeRouteKinds, affectedRouteCount, briefing, categoryFilter, countryRisk, currentActionableEvents.length, eventClusters.length, eventFeedMode, eventHistory.length, eventTimeline.length, health.cache, health.healthy, health.issueCount, health.total, highPriorityCount, highRouteAlertCount, lastUpdate, mapFocus, mapMode, marketConfirmedRouteCount, mediaAttentionTopics, mediaMonitor, mediaWatchRules.length, newEventCount, observationEvents.length, ongoingEventCount, onContextChange, playbackCursor, playbackPlaying, playbackTime, points.length, progress, query, recentlyResolvedEventCount, routeAlerts.length, routes.length, selectedEvent, selectedPoint, selectedRegion, selectedRoute, severityFilter, showCountryRisk, showObservations, status, timeWindow, trend, unacknowledgedEventCount, visibleEventClusters.length, visibleEvents, visiblePoints.length, visibleRoutes.length, watchedMediaTopicChanges.length, watchedMediaTopics.length, watchedRegionViews, watchingAttentionCount, watchingEventCount]);

  const applySituationPreset = (preset: SituationPreset) => {
    setActiveLayers(new Set(preset.activeLayers));
    setActiveRouteKinds(new Set(preset.activeRouteKinds));
    setCategoryFilter(preset.categoryFilter);
    setShowObservations(false);
    setSeverityFilter(preset.severityFilter);
    setTimeWindow(preset.timeWindow);
    setMapMode(preset.mapMode);
    setShowCountryRisk(preset.showCountryRisk);
    setPlaybackCursor(100);
    setPlaybackPlaying(false);
    setPresetMenuOpen(false);
  };

  const focusHotspot = (hotspot: ConvergenceHotspot) => {
    setMapFocus({
      id: `${hotspot.id}-${Date.now()}`,
      longitude: hotspot.longitude,
      latitude: hotspot.latitude,
      label: `${hotspot.label} · 汇聚 ${hotspot.score.toFixed(1)}`,
      zoom: 4.1,
    });
    setSelectedRegion(undefined);
    setTrendPanelOpen(false);
  };

  const toggleLayer = (category: GlobalIntelCategory) => {
    setActiveLayers((current) => {
      const next = new Set(current);
      if (next.has(category)) next.delete(category);
      else next.add(category);
      return next;
    });
  };

  const toggleRouteKind = (kind: GlobalIntelRoute["kind"]) => {
    setActiveRouteKinds((current) => {
      const next = new Set(current);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next;
    });
  };

  const createWatchRegion = () => {
    if (!selectedRegion) return;
    const baselinePointIds = points
      .filter((point) => pointInRegion(point, selectedRegion))
      .map((point) => point.id);
    setWatchedRegions((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        name: `监控区 ${current.length + 1}`,
        bounds: selectedRegion,
        createdAt: new Date().toISOString(),
        baselinePointIds,
      },
    ]);
    setWatchPanelOpen(true);
  };

  const removeWatchRegion = (regionId: string) => {
    setWatchedRegions((current) => current.filter((region) => region.id !== regionId));
  };

  const setRouteAlertDisposition = (
    alertId: string,
    disposition: GlobalIntelRouteAlertDisposition,
  ) => {
    setRouteAlertStates((current) => {
      const state = current[alertId];
      return state ? { ...current, [alertId]: { ...state, disposition } } : current;
    });
  };

  const openRouteAlert = (routeId: string) => {
    const route = routesWithRisk.find((item) => item.id === routeId);
    if (route) selectRoute(route);
    setRouteAlertPanelOpen(false);
  };

  const selectPoint = useCallback((point: GlobalIntelPoint) => {
    setSelectedPointId(point.id);
    const event = eventTimeline.find((item) => item.pointId === point.id);
    setSelectedEventId(event?.id ?? "");
    setSelectedRouteId("");
  }, [eventTimeline]);

  const setEventsDisposition = (eventsToUpdate: GlobalIntelEvent[], update: Partial<EventDisposition>) => {
    setEventDispositions((current) => {
      const nextState = { ...current };
      for (const event of eventsToUpdate) {
        const identity = globalIntelEventIdentity(event);
        if (!identity) continue;
        const next = { ...(nextState[identity] ?? {}), ...update };
        if (!next.acknowledgedAt && !next.watching) delete nextState[identity];
        else nextState[identity] = next;
      }
      return nextState;
    });
  };

  const acknowledgeEvents = (eventsToUpdate: GlobalIntelEvent[]) => {
    const acknowledgedAt = new Date().toISOString();
    setEventDispositions((current) => {
      const nextState = { ...current };
      for (const event of eventsToUpdate) {
        const identity = globalIntelEventIdentity(event);
        if (!identity) continue;
        const history = historyByIdentity.get(identity);
        nextState[identity] = {
          ...(nextState[identity] ?? {}),
          acknowledgedAt,
          acknowledgedChangeAt: history?.lastChangedAt || acknowledgedAt,
        };
      }
      return nextState;
    });
  };

  const markVisibleEventsHandled = () => {
    acknowledgeEvents(visibleEventClusters.flatMap((cluster) => cluster.events));
  };

  const toggleMediaTopicWatch = (topic: GlobalMediaMonitorTopic) => {
    setMediaWatchRules((current) => {
      const matching = current.filter((rule) => mediaWatchRuleMatchesTopic(rule, topic));
      if (matching.length) {
        const matchingIds = new Set(matching.map((rule) => rule.id));
        return current.filter((rule) => !matchingIds.has(rule.id));
      }
      return [...current, {
        id: topic.id,
        label: topic.label,
        keywords: [...new Set((topic.keywords.length ? topic.keywords : [topic.label]).filter(Boolean))].slice(0, 6),
        createdAt: new Date().toISOString(),
        baselineSignature: mediaTopicSignature(topic),
      }];
    });
  };

  const acknowledgeMediaTopic = (topic: GlobalMediaMonitorTopic) => {
    const baselineSignature = mediaTopicSignature(topic);
    setMediaWatchRules((current) => current.map((rule) => (
      mediaWatchRuleMatchesTopic(rule, topic) ? { ...rule, baselineSignature } : rule
    )));
  };

  const openMediaTopic = (topic: GlobalMediaMonitorTopic | MediaTopicHistoryEntry) => {
    if ("items" in topic && topic.items.length) {
      const relatedEvents = events.filter((event) => {
        if (event.recordKind !== "news") return false;
        const annotation = mediaAnnotationByEventId.get(event.id)
          ?? findGlobalMediaMonitorAnnotation(snapshot, event);
        return annotation?.topicId === topic.id;
      });
      const nextEvent = relatedEvents[0];
      if (nextEvent) {
        setCategoryFilter("news");
        setEventFeedMode("all");
        setSelectedEventId(nextEvent.id);
        setSelectedPointId(nextEvent.pointId ?? "");
        setSelectedRouteId("");
        setMediaPanelOpen(false);
        return;
      }
    }
    setQuery(topic.headline);
    setCategoryFilter("news");
    setEventFeedMode("all");
    setMediaPanelOpen(false);
  };

  const selectEvent = (event: GlobalIntelEvent, acknowledge = true) => {
    setSelectedEventId(event.id);
    setSelectedPointId(event.pointId ?? "");
    setSelectedRouteId("");
    if (acknowledge) {
      const cluster = eventClusters.find((item) => item.events.some((candidate) => candidate.id === event.id));
      acknowledgeEvents(cluster?.events ?? [event]);
    }
  };

  const focusSelectedEvent = () => {
    const point = selectedEvent?.pointId ? pointById.get(selectedEvent.pointId) : selectedPoint;
    if (!point) return;
    setSelectedPointId(point.id);
    setMapFocus({
      id: `event-${point.id}-${Date.now()}`,
      longitude: point.longitude,
      latitude: point.latitude,
      label: selectedEvent?.title ?? point.title,
      zoom: 5,
    });
  };

  const selectRoute = (route: GlobalIntelRoute) => {
    setSelectedRouteId(route.id);
    setSelectedEventId("");
    setSelectedPointId("");
  };

  const clearSelection = () => {
    setSelectedEventId("");
    setSelectedPointId("");
    setSelectedRouteId("");
  };

  return (
    <div className="intel-dashboard">
      <section className="intel-hud" aria-label="全球情报关键指标">
        <div className="intel-risk-card" data-level={risk.rawLevel.toLocaleLowerCase()}>
          <span><ShieldAlert size={14} />综合风险</span>
          <strong>{risk.score === undefined ? "—" : risk.score.toFixed(0)}</strong>
          <small>{risk.level}</small>
          <button
            type="button"
            onClick={() => {
              setBriefPanelOpen((value) => !value);
              setHealthPanelOpen(false);
              setTrendPanelOpen(false);
              setMediaPanelOpen(false);
            }}
            aria-expanded={briefPanelOpen}
          >
            研判<Gauge size={11} />
          </button>
        </div>
        <div className="intel-priority-card" data-anomalies={trend.anomalyCount > 0 || highRouteAlertCount > 0}>
          <span><AlertTriangle size={14} />高优先级</span>
          <strong>{highPriorityCount}</strong>
          <small>{highPriorityEventCount} 个事件 · {highRouteAlertCount} 条通道预警{trend.anomalyCount ? ` · ${trend.anomalyCount} 项基线偏离` : ""}</small>
          <button
            type="button"
            onClick={() => {
              setTrendPanelOpen((value) => !value);
              setBriefPanelOpen(false);
              setHealthPanelOpen(false);
              setMediaPanelOpen(false);
            }}
            aria-expanded={trendPanelOpen}
          >
            趋势<TrendingUp size={11} />
          </button>
        </div>
        <div className="intel-media-card" data-alert={mediaMonitor.summary.flaggedTopicCount > 0}>
          <span><Sparkles size={14} />舆情雷达</span>
          <strong>{mediaMonitor.summary.attentionTopicCount || mediaMonitor.summary.topicCount || "—"}</strong>
          <small>
            {mediaMonitor.summary.analyzedItems} 条报道 · 负面 {mediaMonitor.summary.sentiment.negativePct}% · 热度 {mediaVelocityLabel(mediaMonitor.summary.heatVelocityPct, mediaMonitor.summary.velocityState)}
            {mediaMonitor.summary.flaggedTopicCount ? ` · ${mediaMonitor.summary.flaggedTopicCount} 条核验提示` : ""}
            {watchedMediaTopicChanges.length ? ` · 关注变化 ${watchedMediaTopicChanges.length}` : watchedMediaTopics.length ? ` · 关注命中 ${watchedMediaTopics.length}` : ""}
          </small>
          <button
            type="button"
            onClick={() => {
              setMediaPanelOpen((value) => !value);
              setBriefPanelOpen(false);
              setTrendPanelOpen(false);
              setHealthPanelOpen(false);
            }}
            aria-expanded={mediaPanelOpen}
          >
            查看<Languages size={11} />
          </button>
        </div>
        <div><span><CircleDot size={14} />地图与通道</span><strong>{visiblePoints.length}</strong><small>{points.length} 个点位 · {affectedRouteCount} 条通道受影响</small></div>
        <div className="intel-health-card" data-issues={health.issueCount > 0}>
          <span><Radio size={14} />数据与更新</span>
          <strong>{health.total ? `${health.healthy}/${health.total}` : status === "degraded" && dataSettlementComplete ? "静态可用" : health.issueCount ? `${health.issueCount} 异常` : "连接中"}</strong>
          <small>{status === "live" ? "实时" : status === "degraded" ? "降级" : "连接中"} · {progress.total ? `${progress.done}/${progress.total}` : "静态层"} · {lastUpdate ? relativeTime(lastUpdate) : "等待更新"}{status === "degraded" && dataSettlementComplete ? " · 已结算" : ""}{health.issueCount ? ` · ${health.issueCount} 异常` : ""}</small>
          <div className="intel-health-actions">
            <button type="button" onClick={onRefresh} aria-label="刷新全球情报"><RefreshCw size={11} />刷新</button>
            <button
              type="button"
              onClick={() => {
                setHealthPanelOpen((value) => !value);
                setBriefPanelOpen(false);
                setTrendPanelOpen(false);
                setMediaPanelOpen(false);
              }}
              aria-expanded={healthPanelOpen}
            >
              详情<ChevronDown size={11} />
            </button>
          </div>
        </div>
      </section>

      {healthPanelOpen ? (
        <aside className="intel-health-console" aria-label="数据源健康控制台">
          <header>
            <div><Database size={14} /><span><strong>数据源健康控制台</strong><small>SOURCE CONTROL</small></span></div>
            <button type="button" onClick={() => setHealthPanelOpen(false)} aria-label="关闭数据源健康控制台"><X size={14} /></button>
          </header>
          <section>
            <div><small>上游连接</small><strong>{health.total ? `${health.healthy}/${health.total}` : "等待探测"}</strong></div>
            <div data-alert={health.issueCount > 0}><small>异常与降级</small><strong>{health.issueCount}</strong></div>
            <div><small>有效缓存</small><strong>{health.cache.active}/{health.cache.total || 0}</strong></div>
          </section>
          <div className="intel-health-list">
            {health.items.map((item) => (
              <article key={item.id} data-status={item.status}>
                <i />
                <span><strong>{item.label}</strong><small>{item.reason}</small></span>
                <em>{item.freshness ?? "实时"}</em>
                <b>{item.statusLabel}</b>
              </article>
            ))}
            {health.items.length === 0 ? <p>正在等待第一轮数据源探测结果。</p> : null}
          </div>
        </aside>
      ) : null}

      {briefPanelOpen ? (
        <aside className="intel-briefing-console" aria-label="全球态势研判" data-level={risk.rawLevel.toLocaleLowerCase()}>
          <header>
            <div><Target size={15} /><span><strong>全球态势研判</strong><small>STRATEGIC SITUATION REPORT</small></span></div>
            <div>
              <small>{briefing.timestamp ? `${relativeTime(briefing.timestamp)}更新` : "正在生成第一轮研判"}</small>
              <button type="button" onClick={() => setBriefPanelOpen(false)} aria-label="关闭全球态势研判"><X size={14} /></button>
            </div>
          </header>
          <div className="intel-briefing-body">
            <section className="intel-posture-column">
              <div className="intel-posture-score">
                <span>COMPOSITE RISK</span>
                <strong>{risk.score === undefined ? "—" : risk.score.toFixed(0)}</strong>
                <b>{risk.level}</b>
                <small>{briefing.domains.length || 9} 个风险域综合评估</small>
              </div>
              <div className="intel-domain-matrix">
                <header><Gauge size={12} /><span>风险域分布</span></header>
                {briefing.domains.map((domain) => (
                  <article
                    key={domain.id}
                    style={{
                      "--posture-score": `${Math.min(100, Math.max(0, domain.score))}%`,
                      "--posture-color": domain.score >= 55 ? "var(--intel-danger)" : domain.score >= 35 ? "var(--intel-warn)" : "var(--intel-accent)",
                    } as CSSProperties}
                  >
                    <span><strong>{domain.label}</strong><small>{domain.level}</small></span>
                    <b>{domain.score.toFixed(0)}</b>
                    <i><em /></i>
                  </article>
                ))}
                {briefing.domains.length === 0 ? <p>战略态势模型正在计算风险域评分。</p> : null}
              </div>
            </section>

            <section className="intel-brief-column">
              <article className="intel-situation-brief">
                <header>
                  <span><BookOpen size={12} />当前研判</span>
                  <small>{briefing.aiGenerated ? `LOCAL AI · ${briefing.model}` : "实时指标规则引擎"}</small>
                </header>
                <div>
                  {briefing.briefParagraphs.length ? briefing.briefParagraphs.map((paragraph, index) => (
                    <p key={`${index}-${paragraph.slice(0, 16)}`}>{paragraph}</p>
                  )) : (
                    <p>正在汇总全球风险域、活跃告警和实时事件。当前已完成 {progress.done}/{progress.total || 47} 个数据任务。</p>
                  )}
                </div>
              </article>

              <div className="intel-briefing-lists">
                <article className="intel-strategic-alerts">
                  <header>
                    <span><AlertTriangle size={12} />活跃告警</span>
                    <small>
                      C {Number(briefing.priorityCounts.critical ?? 0)} · H {Number(briefing.priorityCounts.high ?? 0)} · M {Number(briefing.priorityCounts.medium ?? 0)}
                    </small>
                  </header>
                  <div>
                    {briefing.alerts.slice(0, 8).map((alert) => (
                      <section key={alert.id} data-priority={alert.priority}>
                        <i />
                        <span><strong>{alert.message}</strong><small>{alert.domainLabel}</small></span>
                      </section>
                    ))}
                    {briefing.alerts.length === 0 ? <p>当前没有达到阈值的战略告警。</p> : null}
                  </div>
                </article>

                <article className="intel-top-threats">
                  <header><span><Target size={12} />关键威胁</span><small>TOP SIGNALS</small></header>
                  <div>
                    {briefing.threats.slice(0, 8).map((threat) => (
                      <section key={threat.id}>
                        <b>{threat.score.toFixed(0)}</b>
                        <span><strong>{threat.domain}</strong><small>{threat.signal}</small></span>
                      </section>
                    ))}
                    {briefing.threats.length === 0 ? <p>正在等待多域风险信号汇聚。</p> : null}
                  </div>
                </article>
              </div>
            </section>
          </div>
        </aside>
      ) : null}

      {trendPanelOpen ? (
        <aside className="intel-trend-console" aria-label="时间趋势雷达">
          <header>
            <div><TrendingUp size={15} /><span><strong>时间趋势雷达</strong><small>TEMPORAL BASELINE & SIGNAL CONVERGENCE</small></span></div>
            <div>
              <small>{trend.timestamp ? `${relativeTime(trend.timestamp)}更新` : "等待趋势模型"}</small>
              <button type="button" onClick={() => setTrendPanelOpen(false)} aria-label="关闭时间趋势雷达"><X size={14} /></button>
            </div>
          </header>
          <section className="intel-trend-summary">
            <div data-alert={trend.anomalyCount > 0}><small>当前异常</small><strong>{trend.anomalyCount}</strong><span>偏离历史基线</span></div>
            <div><small>基线指标</small><strong>{trend.trendCount}</strong><span>按星期与月份建模</span></div>
            <div><small>最高汇聚</small><strong>{trend.maxConvergence.toFixed(1)}</strong><span>多信号空间评分 / 10</span></div>
          </section>
          <div className="intel-trend-body">
            <article className="intel-anomaly-list">
              <header><span><AlertTriangle size={12} />活跃基线异常</span><small>Z-SCORE</small></header>
              <div>
                {trend.anomalies.map((anomaly) => (
                  <section key={anomaly.id} data-severity={anomaly.severity}>
                    <b>{anomaly.zScore >= 0 ? "+" : ""}{anomaly.zScore.toFixed(1)}σ</b>
                    <span>
                      <strong>{anomaly.region} · {anomaly.metric}</strong>
                      <small>当前 {anomaly.observed} / 基线 {anomaly.expected} · {anomaly.multiplier.toFixed(1)} 倍常态</small>
                    </span>
                  </section>
                ))}
                {trend.anomalies.length === 0 ? <p>当前指标均在历史基线范围内。</p> : null}
              </div>
            </article>

            <article className="intel-volatility-list">
              <header><span><Activity size={12} />高波动指标</span><small>CV%</small></header>
              <div>
                {trend.trends.slice(0, 10).map((item) => (
                  <section
                    key={item.id}
                    style={{ "--trend-width": `${Math.min(100, Math.sqrt(Math.max(0, item.volatility) / 600) * 100)}%` } as CSSProperties}
                  >
                    <span><strong>{item.region} · {item.metric}</strong><small>{item.observations} 个样本 · 均值 {item.mean.toFixed(1)}</small></span>
                    <b>{item.volatility.toFixed(1)}</b>
                    <i><em /></i>
                  </section>
                ))}
                {trend.trends.length === 0 ? <p>时间基线仍在积累样本。</p> : null}
              </div>
            </article>

            <article className="intel-convergence-list">
              <header><span><Crosshair size={12} />空间信号汇聚</span><small>SCORE / 10</small></header>
              <div>
                {trend.hotspots.map((hotspot) => (
                  <button type="button" key={hotspot.id} onClick={() => focusHotspot(hotspot)}>
                    <i style={{ "--convergence": `${Math.min(100, hotspot.score * 10)}%` } as CSSProperties}><em /></i>
                    <span><strong>{hotspot.label}</strong><small>{hotspot.earthquakeCount} 次地震信号 · 点击聚焦地图</small></span>
                    <b>{hotspot.score.toFixed(1)}</b>
                    <LocateFixed size={12} />
                  </button>
                ))}
                {trend.hotspots.length === 0 ? <p>正在扫描全球热点的多源信号。</p> : null}
              </div>
            </article>
          </div>
        </aside>
      ) : null}

      {mediaPanelOpen ? (
        <aside className="intel-media-console" aria-label="全球舆情雷达">
          <header>
            <div><Sparkles size={15} /><span><strong>全球舆情雷达</strong><small>MEDIA VELOCITY · FRAMING · VERIFICATION</small></span></div>
            <div>
              <small>{mediaMonitor.timestamp ? `${relativeTime(mediaMonitor.timestamp)}更新` : "等待新闻批次"}</small>
              <button type="button" onClick={() => setMediaPanelOpen(false)} aria-label="关闭全球舆情雷达"><X size={14} /></button>
            </div>
          </header>
          <section className="intel-media-summary">
            <div data-tone="negative">
              <small>报道语气</small>
              <strong>{mediaMonitor.summary.sentiment.negativePct}%</strong>
              <span>负面 · 正面 {mediaMonitor.summary.sentiment.positivePct}%</span>
            </div>
            <div data-trend={mediaMonitor.summary.velocityState}>
              <small>讨论热度</small>
              <strong>{mediaVelocityLabel(mediaMonitor.summary.heatVelocityPct, mediaMonitor.summary.velocityState)}</strong>
              <span>{mediaMonitor.summary.velocityState === "new" ? "前一时段无可比样本" : `${mediaMonitor.summary.windowHours}h 对比前一时段`}</span>
            </div>
            <div>
              <small>主题聚类</small>
              <strong>{mediaMonitor.summary.topicCount}</strong>
              <span>{mediaMonitor.summary.attentionTopicCount} 个值得留意 · {mediaMonitor.summary.crossLanguageTopicCount} 个跨语言</span>
            </div>
            <div>
              <small>传播范围</small>
              <strong>{mediaMonitor.summary.spreadScore}</strong>
              <span>{mediaMonitor.summary.sourceCount} 源 · {mediaMonitor.summary.languageCount} 语种</span>
            </div>
            <div data-alert={mediaMonitor.summary.flaggedTopicCount > 0}>
              <small>核验提示</small>
              <strong>{mediaMonitor.summary.flaggedTopicCount}</strong>
              <span>纠正/反转 {mediaMonitor.summary.reversalTopicCount}</span>
            </div>
            <div data-alert={watchedMediaTopics.length > 0}>
              <small>主题关注</small>
              <strong>{mediaWatchRules.length}</strong>
              <span>{watchedMediaTopicChanges.length ? `${watchedMediaTopicChanges.length} 个主题有变化` : `本批命中 ${watchedMediaTopics.length}`}</span>
            </div>
          </section>
          <div className="intel-media-body">
            <article className="intel-media-topic-list">
              <header><span><TrendingUp size={12} />优先关注</span><small>ATTENTION / HEAT</small></header>
              <div>
                {mediaAttentionTopics.slice(0, 12).map((topic) => (
                  <div
                    key={topic.id}
                    data-verification={topic.verificationStatus !== "常规报道"}
                    data-watching={mediaWatchRules.some((rule) => mediaWatchRuleMatchesTopic(rule, topic))}
                  >
                    <button type="button" className="intel-media-topic-main" onClick={() => openMediaTopic(topic)}>
                      <span>
                        <strong>{topic.label}</strong>
                        <small>
                          {topic.sourceCount} 源 · {topic.languageLabels.join("/") || "单语"} · {topic.spreadLevel}
                        </small>
                      </span>
                      <b title={`关注度 ${topic.attentionScore} · 热度 ${topic.heatScore}`}>{topic.attentionScore}</b>
                      <em data-trend={topic.velocityState}>{mediaVelocityLabel(topic.heatVelocityPct, topic.velocityState)}</em>
                      <i style={{ "--media-reach": `${topic.spreadScore}%` } as CSSProperties}><u /></i>
                      {topic.attentionLevel !== "常规" ? <mark data-attention={topic.attentionLevel}>{topic.attentionLevel}</mark> : null}
                      <mark data-sentiment={topic.sentiment}>{mediaSentimentLabel(topic.sentiment)}</mark>
                      {topic.verificationStatus !== "常规报道" ? <mark data-verify="true">{topic.verificationStatus}</mark> : null}
                      {topic.framingDivergence ? <mark data-divergence="true">表述分歧</mark> : null}
                      {topic.crossLanguage ? <mark data-language="true"><Languages size={9} />跨语言</mark> : null}
                    </button>
                    <button type="button" className="intel-media-topic-watch" onClick={() => toggleMediaTopicWatch(topic)}>
                      <Star size={9} />{mediaWatchRules.some((rule) => mediaWatchRuleMatchesTopic(rule, topic)) ? "已关注" : "关注"}
                    </button>
                  </div>
                ))}
                {mediaMonitor.topics.length === 0 ? <p>正在等待新闻与社交信号完成聚类。</p> : null}
              </div>
            </article>
            <article className="intel-media-frame-list">
              <header><span><Newspaper size={12} />媒体框架</span><small>TONE BY SOURCE TYPE</small></header>
              <div>
                {mediaMonitor.mediaFrames.map((frame) => {
                  const total = Math.max(1, frame.count);
                  return (
                    <section key={frame.group}>
                      <span><strong>{frame.label}</strong><small>{frame.count} 条 · {frame.sources.slice(0, 3).join(" / ")}</small></span>
                      <b>{frame.dominantLabel}</b>
                      <i>
                        {MEDIA_SENTIMENT_ORDER.map((sentiment) => (
                          <em
                            key={sentiment}
                            data-sentiment={sentiment}
                            style={{ width: `${frame[sentiment] / total * 100}%` }}
                            title={`${MEDIA_SENTIMENT_SHORT_LABEL[sentiment]} ${frame[sentiment]}`}
                          />
                        ))}
                      </i>
                    </section>
                  );
                })}
                {mediaMonitor.mediaFrames.length === 0 ? <p>暂无可比较的媒体来源结构。</p> : null}
              </div>
              <footer>{mediaMonitor.caveat || "情绪表示报道语气；核验提示不等于真假判定。"}</footer>
            </article>
          </div>
        </aside>
      ) : null}

      {error ? <div className="intel-error" role="alert"><AlertTriangle size={14} />{error}</div> : null}

      <section className="intel-command-bar">
        <div className="intel-preset-picker">
          <button type="button" aria-expanded={presetMenuOpen} onClick={() => setPresetMenuOpen((value) => !value)}>
            <Crosshair size={13} />态势：{activePreset?.label ?? "手动"}<ChevronDown size={11} />
          </button>
          {presetMenuOpen ? (
            <div className="intel-preset-menu" role="menu">
              <header><span>态势预设</span><small>一键切换地图与事件视角</small></header>
              {SITUATION_PRESETS.map((preset) => (
                <button
                  type="button"
                  key={preset.id}
                  role="menuitem"
                  data-active={activePreset?.id === preset.id}
                  onClick={() => applySituationPreset(preset)}
                >
                  <i>{preset.label.slice(0, 1)}</i>
                  <span><strong>{preset.label}</strong><small>{preset.description}</small></span>
                  <b>{activePreset?.id === preset.id ? "ACTIVE" : "LOAD"}</b>
                </button>
              ))}
            </div>
          ) : null}
        </div>
        <label className="intel-search">
          <Search size={14} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索事件、国家、来源" />
          {query ? <button type="button" onClick={() => setQuery("")} aria-label="清除搜索"><X size={13} /></button> : null}
        </label>
        <div className="intel-segments" aria-label="时间范围">
          {(["24h", "7d", "all"] as const).map((value) => (
            <button key={value} type="button" aria-pressed={timeWindow === value} onClick={() => setTimeWindow(value)}>
              {value === "24h" ? "24 小时" : value === "7d" ? "7 天" : "全部"}
            </button>
          ))}
        </div>
        <div className="intel-segments" aria-label="严重度">
          <button type="button" aria-pressed={severityFilter === "all"} onClick={() => setSeverityFilter("all")}>全部级别</button>
          <button type="button" aria-pressed={severityFilter === "priority"} onClick={() => setSeverityFilter("priority")}>仅高优先级</button>
        </div>
        <div className="intel-live-state" data-status={status}>
          <i />
          <span>{status === "live" ? "实时" : status === "degraded" ? "降级" : "连接中"}</span>
          <time>{lastUpdate ? relativeTime(lastUpdate) : "等待首批数据"}</time>
        </div>
      </section>

      <section className="intel-timeline" aria-label="事件时间播放">
        <button
          type="button"
          onClick={() => {
            if (playbackCursor >= 100) setPlaybackCursor(0);
            setPlaybackPlaying((value) => !value);
          }}
          aria-label={playbackPlaying ? "暂停时间播放" : "开始时间播放"}
        >
          {playbackPlaying ? <Pause size={13} /> : <Play size={13} />}
        </button>
        <strong>TIME</strong>
        <input
          type="range"
          min="0"
          max="100"
          value={playbackCursor}
          onChange={(event) => {
            setPlaybackPlaying(false);
            setPlaybackCursor(Number(event.target.value));
          }}
          aria-label="事件时间游标"
        />
        <time>{new Date(playbackTime).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })}</time>
        <span>{visibleEventClusters.length} 簇 / {visibleEvents.length} 记录</span>
        {selectedRegion ? (
          <div className="intel-region-actions">
            <button type="button" className="intel-region-watch" onClick={createWatchRegion}>
              <BellPlus size={11} />监控此区域
            </button>
            <button type="button" className="intel-region-chip" onClick={() => setSelectedRegion(undefined)}>
              {visiblePoints.length} 点 · 清除
            </button>
          </div>
        ) : <small>Shift + 拖拽框选区域</small>}
      </section>

      <div className="intel-workbench" data-detail-open={Boolean(selectedEvent || selectedPoint || selectedRoute)}>
        <aside className="intel-layer-dock">
          <header><Layers3 size={14} /><span>地图图层</span><small>{activeLayers.size}/{MAP_LAYER_CATEGORIES.length}</small></header>
          <div>
            {MAP_LAYER_CATEGORIES.map((category) => {
              const meta = CATEGORY_META[category];
              const Icon = meta.icon;
              return (
                <button type="button" key={category} aria-pressed={activeLayers.has(category)} onClick={() => toggleLayer(category)}>
                  <i style={{ "--layer-color": meta.color } as CSSProperties}><Icon size={13} /></i>
                  <span>{meta.label}</span>
                  <small>{points.filter((point) => point.category === category).length}</small>
                </button>
              );
            })}
          </div>
          <section className="intel-map-settings" aria-label="地图设置">
            <header><MapIcon size={12} /><span>地图设置</span></header>
            <div className="intel-map-setting-group">
              <small>显示</small>
              <div>
                <button type="button" aria-pressed={mapMode === "signals"} onClick={() => setMapMode("signals")}>信号</button>
                <button type="button" aria-pressed={mapMode === "heat"} onClick={() => setMapMode("heat")}>热力</button>
                <button type="button" aria-pressed={showCountryRisk} onClick={() => setShowCountryRisk((value) => !value)}>国家风险</button>
              </div>
            </div>
            <div className="intel-map-setting-group">
              <small>战略通道</small>
              <div>
                {ROUTE_FILTERS.map(({ kind, label }) => (
                  <button type="button" key={kind} aria-pressed={activeRouteKinds.has(kind)} onClick={() => toggleRouteKind(kind)}>
                    {label}<b>{routes.filter((route) => route.kind === kind).length}</b>
                  </button>
                ))}
              </div>
            </div>
            <footer><Clock3 size={11} />图层与实时流同步</footer>
          </section>
        </aside>

        <section className="intel-map-panel">
          <header className="intel-panel-title">
            <div><Satellite size={14} /><span>全球综合态势</span></div>
            <small>MapLibre GL · deck.gl · {visibleRoutes.length}/{routes.length} 条战略通道 · {routeAlerts.length} 条预警</small>
          </header>
          <IntelligenceMap
            points={visiblePoints}
            selectedPointId={selectedPointId}
            theme={theme}
            mode={mapMode}
            routes={visibleRoutes}
            showRoutes={activeRouteKinds.size > 0}
            showCountryRisk={showCountryRisk}
            countryRisk={countryRisk}
            selectedRegion={selectedRegion}
            focusLocation={mapFocus}
            watchedRegions={mapWatchRegions}
            onSelect={selectPoint}
            onRouteSelect={selectRoute}
            onRegionSelect={setSelectedRegion}
          />
          <button
            type="button"
            className="intel-watch-toggle"
            data-alerts={totalWatchAlerts > 0}
            aria-expanded={watchPanelOpen}
            onClick={() => {
              setWatchPanelOpen((value) => !value);
              setRouteAlertPanelOpen(false);
            }}
          >
            <Bell size={12} />监控区 {watchedRegions.length}
            {totalWatchAlerts ? <b>{totalWatchAlerts}</b> : null}
          </button>
          <button
            type="button"
            className="intel-route-alert-toggle"
            data-alerts={newRouteAlertCount > 0}
            aria-expanded={routeAlertPanelOpen}
            onClick={() => {
              setRouteAlertPanelOpen((value) => !value);
              setWatchPanelOpen(false);
            }}
          >
            <AlertTriangle size={12} />通道预警 {routeAlerts.length}
            {newRouteAlertCount ? <b>{newRouteAlertCount}</b> : null}
          </button>
          {mapFocus ? (
            <button type="button" className="intel-map-focus-chip" onClick={() => setMapFocus(undefined)}>
              <LocateFixed size={11} /><span>{mapFocus.label}</span><X size={10} />
            </button>
          ) : null}
          {watchPanelOpen ? (
            <aside className="intel-watch-panel" aria-label="地理围栏预警">
              <header><span><Bell size={12} />地理围栏预警</span><small>{totalWatchAlerts} NEW</small></header>
              <div>
                {watchedRegionViews.map((region) => (
                  <article key={region.id} data-alerts={region.alertCount > 0}>
                    <span><strong>{region.name}</strong><small>覆盖 {region.coveredPointCount} 个信号 · 新增 {region.alertCount}</small></span>
                    <button type="button" onClick={() => removeWatchRegion(region.id)} aria-label={`删除${region.name}`}><Trash2 size={12} /></button>
                  </article>
                ))}
                {watchedRegions.length === 0 ? <p>Shift + 拖拽框选地图，然后设为监控区。</p> : null}
              </div>
            </aside>
          ) : null}
          {routeAlertPanelOpen ? (
            <aside className="intel-route-alert-panel" aria-label="战略通道预警队列">
              <header>
                <span><AlertTriangle size={12} />战略通道预警</span>
                <small>{newRouteAlertCount} NEW</small>
              </header>
              <div>
                {routeAlerts.map((alert) => {
                  const state = routeAlertStates[alert.id];
                  const disposition = state?.disposition ?? "new";
                  const change = state?.change ?? "new";
                  return (
                    <article key={alert.id} data-level={alert.level} data-disposition={disposition}>
                      <button type="button" className="intel-route-alert-main" onClick={() => openRouteAlert(alert.routeId)}>
                        <strong>{alert.title}</strong>
                        <small>
                          {alert.level === "critical" ? "严重" : alert.level === "high" ? "高优先级" : "观察"}
                          {` · 综合 ${alert.score} · ${change === "escalated" ? "已升级" : change === "downgraded" ? "已降级" : change === "new" ? "新预警" : "持续中"}`}
                        </small>
                      </button>
                      <div>
                        <button type="button" onClick={() => setRouteAlertDisposition(alert.id, "acknowledged")}>确认</button>
                        <button
                          type="button"
                          onClick={() => setRouteAlertDisposition(alert.id, disposition === "muted" ? "acknowledged" : "muted")}
                        >
                          {disposition === "muted" ? "取消静默" : "静默"}
                        </button>
                      </div>
                    </article>
                  );
                })}
                {recentResolvedRouteAlerts.map((state) => (
                  <article key={state.alertId} data-level="resolved" data-disposition={state.disposition}>
                    <button type="button" className="intel-route-alert-main" onClick={() => openRouteAlert(state.routeId)}>
                      <strong>{state.title}</strong>
                      <small>已解除 · {relativeTime(state.updatedAt)}</small>
                    </button>
                  </article>
                ))}
                {routeAlerts.length === 0 && recentResolvedRouteAlerts.length === 0 ? <p>当前没有战略通道预警。</p> : null}
              </div>
            </aside>
          ) : null}
          <div className="intel-map-legend">
            {MAP_LAYER_CATEGORIES.filter((category) => (
              activeLayers.has(category) && points.some((point) => point.category === category)
            )).map((category) => (
              <span key={category}><i style={{ background: CATEGORY_META[category].color }} />{CATEGORY_META[category].label}</span>
            ))}
          </div>
        </section>

        <section className="intel-event-rail">
          <header className="intel-panel-title">
            <div><Radio size={14} /><span>实时事件流</span></div>
            <div className="intel-event-summary">
              <small>未处理 {unacknowledgedEventCount} · 关注 {watchingEventCount}{watchingAttentionCount ? `（${watchingAttentionCount} 变化）` : ""} · 新 {newEventCount}</small>
              {unacknowledgedEventCount > 0 ? (
                <button type="button" onClick={markVisibleEventsHandled}><Check size={10} />处理当前</button>
              ) : null}
            </div>
          </header>
          <div className="intel-category-strip" role="group" aria-label="事件分类">
            <button type="button" aria-pressed={eventFeedMode === "changes"} onClick={() => setEventFeedMode("changes")}>变化优先</button>
            <button type="button" aria-pressed={eventFeedMode === "unread"} onClick={() => setEventFeedMode("unread")}><BellRing size={10} />未处理 {unacknowledgedEventCount}</button>
            <button type="button" aria-pressed={eventFeedMode === "watching"} onClick={() => setEventFeedMode("watching")}><Star size={10} />关注 {watchingEventCount}</button>
            <button type="button" aria-pressed={eventFeedMode === "all"} onClick={() => setEventFeedMode("all")}>全部动态</button>
            <span aria-hidden="true" />
            <button type="button" aria-pressed={categoryFilter === "all"} onClick={() => setCategoryFilter("all")}>全部</button>
            <button type="button" aria-pressed={showObservations} onClick={() => setShowObservations((value) => !value)}>
              原始观测 {observationEvents.length}
            </button>
            {EVENT_FILTER_CATEGORIES.map((category) => (
              <button type="button" key={category} aria-pressed={categoryFilter === category} onClick={() => setCategoryFilter(category)}>
                {CATEGORY_META[category].label} {eventCategoryCounts[category]}
              </button>
            ))}
          </div>
          <div className="intel-event-list">
            {visibleEventClusters.slice(0, 160).map((cluster) => {
              const currentClusterEvents = cluster.events.filter((item) => (
                currentEventIdentities.has(globalIntelEventIdentity(item))
              ));
              const event = currentClusterEvents.find((item) => item.id === cluster.primary.id)
                ?? currentClusterEvents[0]
                ?? cluster.primary;
              const meta = CATEGORY_META[event.category];
              const Icon = meta.icon;
              const clusterIsCurrent = currentClusterEvents.length > 0;
              const monitorState = clusterMonitorState(cluster, currentEventIdentities, historyByIdentity);
              const clusterActivityAt = cluster.events.reduce((latest, item) => {
                const activityAt = eventActivityTimestamp(
                  item,
                  historyByIdentity.get(globalIntelEventIdentity(item)),
                );
                return Date.parse(activityAt) > Date.parse(latest) ? activityAt : latest;
              }, cluster.updatedAt);
              const clusterNeedsAttention = cluster.events.some((item) => (
                eventRequiresAttention(
                  item,
                  historyByIdentity.get(globalIntelEventIdentity(item)),
                  eventDispositions[globalIntelEventIdentity(item)],
                  currentEventIdentities,
                )
              ));
              const clusterAcknowledged = !clusterNeedsAttention;
              const clusterWatching = cluster.events.some((item) => (
                eventDispositions[globalIntelEventIdentity(item)]?.watching
              ));
              const mediaAnnotation = cluster.events
                .map((item) => mediaAnnotationByEventId.get(item.id))
                .find(Boolean);
              return (
                <article
                  key={cluster.id}
                  data-selected={cluster.events.some((item) => item.id === selectedEventId)}
                  data-severity={event.severity}
                  data-history={!clusterIsCurrent}
                  data-monitor-state={monitorState}
                  data-acknowledged={clusterAcknowledged}
                  data-watching={clusterWatching}
                >
                  <button type="button" className="intel-event-main" onClick={() => selectEvent(event)}>
                    <i style={{ "--event-color": meta.color } as CSSProperties}><Icon size={13} /></i>
                    <span>
                      <small>
                        {recordKindLabel(event)} · {meta.label} · {relativeTime(clusterActivityAt)}
                        {cluster.events.length > 1 ? <mark>{cluster.events.length} 条证据</mark> : null}
                        <mark data-state={monitorState}>{eventMonitorLabel(monitorState)}</mark>
                        {clusterWatching ? <mark data-state={clusterNeedsAttention ? "watching-change" : "watching"}>{clusterNeedsAttention ? "关注有变化" : "关注中"}</mark> : null}
                        {mediaAnnotation ? <mark data-sentiment={mediaAnnotation.sentiment}>{mediaSentimentLabel(mediaAnnotation.sentiment)}</mark> : null}
                        {mediaAnnotation?.velocityState === "new" ? <mark data-heat="new">热度 新出现</mark> : null}
                        {mediaAnnotation?.heatVelocityPct !== null && mediaAnnotation && Math.abs(mediaAnnotation.heatVelocityPct) >= 20 ? <mark data-heat={mediaAnnotation.heatVelocityPct > 0 ? "up" : "down"}>热度 {mediaVelocityLabel(mediaAnnotation.heatVelocityPct, mediaAnnotation.velocityState)}</mark> : null}
                        {mediaAnnotation?.verificationStatus !== "常规报道" ? <mark data-verify="true">{mediaAnnotation?.verificationStatus}</mark> : null}
                        {mediaAnnotation?.crossLanguageTopic ? <mark data-language="true">跨语言</mark> : null}
                      </small>
                      <strong>{event.title}</strong>
                      <em>{event.detail}</em>
                      <b>{cluster.sources.slice(0, 3).join(" / ")} · {confidenceLabel(cluster)}</b>
                    </span>
                  </button>
                  <button
                    type="button"
                    className="intel-event-quick-watch"
                    aria-label={clusterWatching ? "取消关注事件" : "关注事件"}
                    aria-pressed={clusterWatching}
                    onClick={() => setEventsDisposition(cluster.events, { watching: !clusterWatching })}
                  >
                    <Star size={11} />
                  </button>
                </article>
              );
            })}
            {visibleEventClusters.length === 0 ? (
              <div
                className="intel-empty"
                data-state={dataSettlementComplete && eventTimeline.length === 0 ? "settled" : "filtered"}
                role="status"
              >
                <strong>
                  {dataSettlementComplete && eventTimeline.length === 0
                    ? "数据已结算，暂无实时事件"
                    : eventFeedMode === "changes"
                      ? "当前筛选没有重点变化"
                      : eventFeedMode === "unread"
                        ? "当前事件均已处理"
                        : eventFeedMode === "watching"
                          ? "还没有关注事件"
                          : "当前筛选没有匹配事件"}
                </strong>
                <small>
                  {dataSettlementComplete && eventTimeline.length === 0
                    ? `${progress.done}/${progress.total} 个数据任务已完成；地图、点位和战略通道仍可正常浏览。`
                    : "可调整时间、级别或分类筛选查看其他内容。"}
                </small>
              </div>
            ) : null}
          </div>
        </section>

        {selectedEvent || selectedPoint || selectedRoute ? (
          <aside className="intel-detail-drawer">
            <header>
              <div><small>INTELLIGENCE DOSSIER</small><strong>事件详情</strong></div>
              <div className="intel-detail-header-actions">
                {selectedEvent ? (
                  <>
                    {selectedEvent.pointId && pointById.has(selectedEvent.pointId) ? (
                      <button type="button" onClick={focusSelectedEvent} aria-label="在地图定位"><Locate size={14} /></button>
                    ) : null}
                    <button
                      type="button"
                      data-active={selectedEventDisposition?.watching}
                      aria-pressed={Boolean(selectedEventDisposition?.watching)}
                      onClick={() => setEventsDisposition(
                        selectedCluster?.events ?? [selectedEvent],
                        { watching: !selectedEventDisposition?.watching },
                      )}
                      aria-label={selectedEventDisposition?.watching ? "取消关注事件" : "关注事件"}
                    >
                      <Star size={14} />
                    </button>
                    <button
                      type="button"
                      data-active={selectedEventAcknowledged}
                      aria-pressed={selectedEventAcknowledged}
                      onClick={() => setEventsDisposition(
                        selectedCluster?.events ?? [selectedEvent],
                        selectedEventAcknowledged
                          ? { acknowledgedAt: undefined, acknowledgedChangeAt: undefined }
                          : {
                            acknowledgedAt: new Date().toISOString(),
                            acknowledgedChangeAt: selectedHistory?.lastChangedAt || new Date().toISOString(),
                          },
                      )}
                      aria-label={selectedEventAcknowledged ? "标记为未处理" : "标记为已处理"}
                    >
                      <Check size={14} />
                    </button>
                  </>
                ) : null}
                <button type="button" onClick={clearSelection} aria-label="关闭详情"><X size={15} /></button>
              </div>
            </header>
            <div className="intel-detail-body">
              <span
                className="intel-detail-category"
                style={{ "--detail-color": selectedRoute ? "#37d6a1" : CATEGORY_META[(selectedEvent?.category ?? selectedPoint?.category)!].color } as CSSProperties}
              >
                {selectedRoute ? "战略通道" : CATEGORY_META[(selectedEvent?.category ?? selectedPoint?.category)!].label}
              </span>
              <h2>{selectedRoute?.name ?? selectedEvent?.title ?? selectedPoint?.title}</h2>
              <p>{selectedRoute ? (selectedRoute.detail || "战略通道示意") : selectedEvent?.detail ?? selectedPoint?.detail}</p>
              {selectedEvent ? (
                <div className="intel-event-disposition-summary">
                  <span data-active={selectedEventAcknowledged}><Check size={11} />{selectedEventAcknowledged ? "已处理" : "未处理"}</span>
                  <span data-active={selectedEventDisposition?.watching}><Star size={11} />{selectedEventDisposition?.watching ? "关注中" : "未关注"}</span>
                  {selectedEvent.pointId && pointById.has(selectedEvent.pointId) ? <button type="button" onClick={focusSelectedEvent}><Locate size={11} />地图定位</button> : null}
                </div>
              ) : null}
              {selectedRoute ? (
                <dl>
                  <div><dt>类型</dt><dd>{selectedRoute.kind === "pipeline" ? "能源管线" : selectedRoute.kind === "cable" ? "海底光缆走廊" : selectedRoute.kind === "flight" ? "航空走廊" : selectedRoute.name.includes("油运") || selectedRoute.name.includes("成品油") || selectedRoute.name.includes("能源线") ? "油运走廊" : "航运通道"}</dd></div>
                  <div><dt>路径</dt><dd>{selectedRoute.pathType === "corridor" ? "示意走廊" : "精确线路"}</dd></div>
                  <div><dt>状态</dt><dd>{selectedRoute.status || "active"}</dd></div>
                  <div><dt>风险</dt><dd>{selectedRoute.riskScore ? `${selectedRoute.riskScore}/100` : "未发现直接影响"}</dd></div>
                  <div><dt>置信度</dt><dd>{selectedRoutePrimaryImpact ? `${selectedRoutePrimaryImpact.confidence}% · ${selectedRoutePrimaryImpact.sourceCount} 个来源` : "暂无证据"}</dd></div>
                  <div><dt>预警</dt><dd>{selectedRouteAlert ? `${selectedRouteAlert.level === "critical" ? "严重" : selectedRouteAlert.level === "high" ? "高优先级" : "观察"} · 综合 ${selectedRouteAlert.score}` : "未触发"}</dd></div>
                </dl>
              ) : (
                <dl>
                  {selectedEvent ? <div><dt>记录类型</dt><dd>{recordKindLabel(selectedEvent)}</dd></div> : null}
                  {selectedEventState ? <div><dt>监控状态</dt><dd>{eventMonitorLabel(selectedEventState)}</dd></div> : null}
                  <div><dt>严重度</dt><dd>{selectedEvent?.severity ?? selectedPoint?.severity}</dd></div>
                  <div><dt>来源</dt><dd>{selectedEvent?.source ?? selectedPoint?.source}</dd></div>
                  <div><dt>时间</dt><dd>{selectedEvent ? new Date(selectedEvent.timestamp).toLocaleString("zh-CN") : selectedPoint?.timestamp ? new Date(selectedPoint.timestamp).toLocaleString("zh-CN") : "静态情报层"}</dd></div>
                  <div><dt>位置</dt><dd>{selectedPoint ? `${selectedPoint.latitude.toFixed(3)}, ${selectedPoint.longitude.toFixed(3)}` : selectedEvent?.country || "未标注"}</dd></div>
                  {selectedFacts?.map((fact) => (
                    <div key={`${fact.label}-${fact.value}`}><dt>{fact.label}</dt><dd>{fact.value}</dd></div>
                  ))}
                </dl>
              )}
              {selectedEvent ? (
                <section className="intel-record-explanation" data-kind={selectedEvent.recordKind ?? "event"}>
                  <h3>{recordKindLabel(selectedEvent)}是什么意思</h3>
                  <p>{recordKindExplanation(selectedEvent)}</p>
                </section>
              ) : null}
              {selectedEvent?.recordKind === "news" && selectedMediaAnnotation ? (
                <section className="intel-media-dossier" data-verification={selectedMediaAnnotation.verificationStatus !== "常规报道"}>
                  <header>
                    <span><Sparkles size={12} />舆情观察</span>
                    <div>
                      <strong>{selectedMediaAnnotation.verificationStatus}</strong>
                      {selectedMediaTopic ? (
                        <button
                          type="button"
                          data-active={selectedMediaTopicWatched}
                          onClick={() => toggleMediaTopicWatch(selectedMediaTopic)}
                        >
                          <Star size={10} />{selectedMediaTopicWatched ? "取消关注" : "关注主题"}
                        </button>
                      ) : null}
                    </div>
                  </header>
                  <dl>
                    <div><dt>报道语气</dt><dd>{mediaSentimentLabel(selectedMediaAnnotation.sentiment)}</dd></div>
                    <div><dt>热度增速</dt><dd>{mediaVelocityLabel(selectedMediaAnnotation.heatVelocityPct, selectedMediaAnnotation.velocityState)}</dd></div>
                    <div><dt>传播范围</dt><dd>{selectedMediaAnnotation.spreadScore}/100</dd></div>
                    <div><dt>跨语言合并</dt><dd>{selectedMediaAnnotation.crossLanguageTopic ? "已合并" : "单语主题"}</dd></div>
                  </dl>
                  {selectedMediaTopic ? (
                    <>
                      <h3>{selectedMediaTopic.label}</h3>
                      <p>
                        {selectedMediaTopic.mentionCount} 条相关记录，来自 {selectedMediaTopic.sourceCount} 个来源、
                        {selectedMediaTopic.languageLabels.join("、") || "单一语种"}；传播级别为{selectedMediaTopic.spreadLevel}，
                        关注度 {selectedMediaTopic.attentionScore}/100（{selectedMediaTopic.attentionLevel}）。
                        {selectedMediaTopic.mediaFrames.length
                          ? ` 不同来源框架：${selectedMediaTopic.mediaFrames.map((frame) => `${frame.label}${frame.dominantLabel}`).join("；")}。`
                          : ""}
                      {selectedMediaTopic.framingDivergence ? " 不同类型媒体的报道语气存在分歧，建议对照原文。" : ""}
                      </p>
                      {selectedMediaTopic.items.length > 1 ? (
                        <div className="intel-media-related-reports">
                          <h4>相关报道</h4>
                          {selectedMediaTopic.items.slice(0, 6).map((item) => {
                            const url = safeExternalUrl(item.url);
                            const content = (
                              <>
                                <span><strong>{item.source}</strong><small>{item.published ? relativeTime(item.published) : "时间未知"} · {mediaSentimentLabel(item.sentiment)}</small></span>
                                <b>{item.title}</b>
                                {url ? <ExternalLink size={10} /> : null}
                              </>
                            );
                            return url ? (
                              <a key={item.key} href={url} target="_blank" rel="noreferrer">{content}</a>
                            ) : (
                              <div key={item.key}>{content}</div>
                            );
                          })}
                        </div>
                      ) : null}
                      {selectedMediaTopicHistory ? (
                        <p className="intel-media-history-summary">
                          浏览器自 {new Date(selectedMediaTopicHistory.firstSeenAt).toLocaleString("zh-CN")} 开始记录；
                          最近变化于 {new Date(selectedMediaTopicHistory.lastChangedAt).toLocaleString("zh-CN")}。
                        </p>
                      ) : null}
                      {selectedMediaTopicWatched && watchedMediaTopicChanges.some((topic) => topic.id === selectedMediaTopic.id) ? (
                        <button type="button" className="intel-media-change-ack" onClick={() => acknowledgeMediaTopic(selectedMediaTopic)}>
                          <Check size={10} />标记本次变化已查看
                        </button>
                      ) : null}
                      {selectedMediaVerificationEvolution.length ? (
                        <div className="intel-media-verification-timeline">
                          <h4>核验演化</h4>
                          <ol>
                            {selectedMediaVerificationEvolution.map((step, index) => (
                              <li key={`${step.flag}-${step.timestamp}-${index}`} data-status={step.flag}>
                                <time>{step.timestamp ? new Date(step.timestamp).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "时间未知"}</time>
                                <strong>{step.status} · {step.source}</strong>
                                <span>{step.title}</span>
                              </li>
                            ))}
                          </ol>
                        </div>
                      ) : null}
                      {similarMediaTopics.length ? (
                        <div className="intel-media-similar-topics">
                          <h4>历史相似线索</h4>
                          {similarMediaTopics.map(({ topic, similarity }) => (
                            <button type="button" key={topic.id} onClick={() => openMediaTopic(topic)}>
                              <span><strong>{topic.label}</strong><small>{new Date(topic.lastSeenAt).toLocaleDateString("zh-CN")} · {topic.sourceCount} 源</small></span>
                              <b>{similarity}%</b>
                            </button>
                          ))}
                        </div>
                      ) : null}
                    </>
                  ) : null}
                  <small>核验提示只识别报道中的“据称、否认、更正、反转”等显式措辞，不直接判断真假。</small>
                </section>
              ) : null}
              {selectedEventImpacts.length ? (
                <section className="intel-evidence-chain">
                  <header>
                    <span><Route size={12} />关联通道与潜在影响</span>
                    <strong>{selectedEventImpacts.length} 条关系</strong>
                  </header>
                  <p>连接只表示地理邻近或文本提及，用于提示可能受影响对象，不代表通道已经中断。</p>
                  <ol>
                    {selectedEventImpacts.slice(0, 6).map(({ impact, route }) => (
                      <li key={`${impact.routeId}-${impact.eventId}`}>
                        <button type="button" onClick={() => selectRoute(route)}>
                          <time>{impact.relation === "mentioned" ? "文本提及" : `${impact.distanceKm ?? "—"} km`}</time>
                          <strong>{route.name} · 风险 {impact.riskScore}</strong>
                          <span>{route.exposure ? [...route.exposure.commodities, ...route.exposure.industries].slice(0, 4).join("、") : route.detail}</span>
                        </button>
                      </li>
                    ))}
                  </ol>
                </section>
              ) : null}
              {selectedEvent && selectedHistory ? (
                <section className="intel-event-lifecycle" data-state={selectedEventState}>
                  <h3>轻量历史</h3>
                  <p>
                    浏览器首次记录于 {new Date(selectedHistory.firstSeenAt).toLocaleString("zh-CN")}，
                    最近看到于 {new Date(selectedHistory.lastSeenAt).toLocaleString("zh-CN")}，
                    最近变化于 {new Date(selectedHistory.lastChangedAt).toLocaleString("zh-CN")}，
                    已累计捕获 {selectedHistory.observationCount} 次；当前状态为{eventMonitorLabel(selectedEventState ?? "new")}。
                    {selectedEventState === "resolved" ? "“已离开”仅表示它不在最新数据快照中，不代表事件已经结束。" : ""}
                  </p>
                </section>
              ) : null}
              {selectedRoute ? (
                <>
                  {selectedRouteAlert ? (
                    <section>
                      <h3>{selectedRouteAlert.title}</h3>
                      <p>{selectedRouteAlert.summary}</p>
                      <dl>
                        {selectedRouteAlert.reasons.map((reason) => (
                          <div key={reason}><dt>依据</dt><dd>{reason}</dd></div>
                        ))}
                      </dl>
                    </section>
                  ) : null}
                  {selectedRouteEvents.length ? (
                    <section className="intel-evidence-chain">
                      <header>
                        <span><GitBranch size={12} />附近影响事件</span>
                        <strong>{selectedRouteEvents.length} 条关联证据</strong>
                      </header>
                      <p>风险依据包含事件类型、距离或新闻文本明确提及；邻近和提及均不代表线路已经中断。</p>
                      <ol>
                        {selectedRouteEvents.slice(0, 8).map(({ impact, event }) => (
                          <li key={`${impact.routeId}-${impact.eventId}`}>
                            <button type="button" onClick={() => selectEvent(event)}>
                              <time>{impact.distanceKm === undefined ? `文本提及 · ${impact.matchedKeyword}` : `${impact.distanceKm} km`}</time>
                              <strong>{CATEGORY_META[event.category].label} · 风险 {impact.riskScore} · 置信 {impact.confidence}%</strong>
                              <span>{event.title} · {impact.sourceCount} 源 / {impact.evidenceCount} 条证据</span>
                            </button>
                          </li>
                        ))}
                      </ol>
                    </section>
                  ) : (
                    <section>
                      <h3>线路说明</h3>
                      <p>当前未发现类型和距离同时匹配的事件。线路为地理背景，不代表实时流量或运输方向。</p>
                    </section>
                  )}
                  {selectedRoute.exposure ? (
                    <section>
                      <h3>潜在风险传导</h3>
                      <p>以下为该通道的结构性暴露关系，用于研判影响范围，不构成价格预测。</p>
                      <dl>
                        <div><dt>国家/地区</dt><dd>{selectedRoute.exposure.countries.join("、")}</dd></div>
                        <div><dt>商品</dt><dd>{selectedRoute.exposure.commodities.join("、")}</dd></div>
                        <div><dt>行业</dt><dd>{selectedRoute.exposure.industries.join("、")}</dd></div>
                        <div><dt>市场指标</dt><dd>{selectedRoute.exposure.marketSignals.join("、")}</dd></div>
                      </dl>
                    </section>
                  ) : null}
                  <section>
                    <h3>市场反应验证</h3>
                    <p>这里只检查相关市场是否同步波动，相关性不代表事件造成了价格变化。</p>
                    {selectedRouteMarketReactions.length ? (
                      <dl>
                        {selectedRouteMarketReactions.map((reaction) => (
                          <div key={`${reaction.routeId}-${reaction.kind}-${reaction.symbol ?? reaction.label}`}>
                            <dt>{reaction.label}</dt>
                            <dd>
                              {reaction.status === "confirmed" ? "同步反应" : reaction.status === "watch" ? "继续观察" : reaction.status === "diverging" ? "方向背离" : "尚未反应"}
                              {` · ${reaction.reason}`}
                            </dd>
                          </div>
                        ))}
                      </dl>
                    ) : <p>当前没有可用于验证该通道风险的直接市场指标。</p>}
                  </section>
                </>
              ) : selectedCluster ? (
                <section className="intel-evidence-chain">
                  <header>
                    <span><GitBranch size={12} />证据链</span>
                    <strong>{selectedCluster.confidence}% · {confidenceLabel(selectedCluster)}</strong>
                  </header>
                  <p>{selectedCluster.events.length} 条记录，来自 {selectedCluster.sources.length} 个独立来源。</p>
                  <ol>
                    {selectedCluster.events.slice(0, 8).map((evidence) => (
                      <li key={evidence.id} data-current={evidence.id === selectedEventId}>
                        <button type="button" onClick={() => selectEvent(evidence)}>
                          <time>{new Date(evidence.timestamp).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" })}</time>
                          <strong>{evidence.source}</strong>
                          <span>{evidence.title}</span>
                        </button>
                      </li>
                    ))}
                  </ol>
                </section>
              ) : (
                <section>
                  <h3>{selectedEvent?.recordKind === "observation" ? "原始观测" : "证据与新鲜度"}</h3>
                  <p>{selectedEvent?.recordKind === "observation" ? "当前记录属于原始观测，尚未检测到足以升级为事件的异常或交叉证据。" : `当前记录来自 ${selectedPoint?.source ?? selectedEvent?.source}，等待更多来源交叉验证。`}</p>
                </section>
              )}
              {selectedContent && selectedContent !== (selectedEvent?.detail ?? selectedPoint?.detail) ? (
                <section>
                  <h3>{selectedEvent?.recordKind === "news" ? "新闻说明" : "事件说明"}</h3>
                  <p>{selectedContent}</p>
                </section>
              ) : null}
              {safeExternalUrl(selectedEvent?.url ?? selectedPoint?.url) ? (
                <a href={safeExternalUrl(selectedEvent?.url ?? selectedPoint?.url)} target="_blank" rel="noreferrer">
                  查看原始来源<ExternalLink size={13} />
                </a>
              ) : null}
            </div>
          </aside>
        ) : null}
      </div>
    </div>
  );
}
