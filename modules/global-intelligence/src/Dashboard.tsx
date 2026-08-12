import {
  Activity,
  AlertTriangle,
  Anchor,
  Bell,
  BellPlus,
  BookOpen,
  Building2,
  Cable,
  ChevronDown,
  CircleDot,
  Clock3,
  CloudSun,
  Crosshair,
  Database,
  ExternalLink,
  Flame,
  Fuel,
  GitBranch,
  Gauge,
  HeartPulse,
  Landmark,
  Layers3,
  LocateFixed,
  Map as MapIcon,
  Newspaper,
  Pause,
  Play,
  Radio,
  Radiation,
  Route,
  Search,
  Satellite,
  ShieldAlert,
  Ship,
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

import {
  GLOBAL_INTELLIGENCE_CONTRACT,
  calculateGlobalIntelMarketReactions,
  calculateGlobalIntelRouteAlerts,
  calculateGlobalIntelRouteImpacts,
  clusterGlobalIntelEvents,
  isActionableGlobalIntelEvent,
  normalizeGlobalIntelEvents,
  normalizeGlobalIntelPoints,
  normalizeGlobalIntelRoutes,
  reconcileGlobalIntelRouteAlertStates,
  updateGlobalIntelMilitaryTrackHistory,
  type GlobalIntelCategory,
  type GlobalIntelDataSource,
  type GlobalIntelEvent,
  type GlobalIntelEventCluster,
  type GlobalIntelMilitaryTrackHistory,
  type GlobalIntelPoint,
  type GlobalIntelRoute,
  type GlobalIntelRouteAlertDisposition,
  type GlobalIntelRouteAlertState,
  type GlobalIntelSeverity,
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

interface SavedWatchRegion {
  id: string;
  name: string;
  bounds: IntelligenceRegion;
  createdAt: string;
  baselinePointIds: string[];
}

const WATCH_REGIONS_KEY = "newma-desk.global-intelligence.watch-regions.v1";
const ROUTE_ALERTS_KEY = "newma-desk.global-intelligence.route-alerts.v1";
const MILITARY_TRACKS_KEY = "newma-desk.global-intelligence.military-tracks.v1";

const SITUATION_PRESETS: SituationPreset[] = [
  {
    id: "overview",
    label: "综合",
    description: "全域信号、全部战略通道",
    activeLayers: [...MAP_LAYER_CATEGORIES],
    activeRouteKinds: ["pipeline", "cable", "shipping"],
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
    activeRouteKinds: ["shipping"],
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
    total: Object.keys(sourceHealth).length,
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
  const hotspots: ConvergenceHotspot[] = recordList(convergence.hotspots).map((hotspot, index) => {
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
  onContextChange,
}: {
  dataSource: GlobalIntelDataSource;
  theme: "light" | "dark";
  refreshNonce: number;
  onContextChange(value: Record<string, unknown>): void;
}) {
  const [snapshot, setSnapshot] = useState<Record<string, unknown>>({});
  const [militaryTrackHistory, setMilitaryTrackHistory] = useState(loadMilitaryTrackHistory);
  const [riskClock, setRiskClock] = useState(() => Date.now());
  const [status, setStatus] = useState<"connecting" | "live" | "degraded">("connecting");
  const [error, setError] = useState("");
  const [activeLayers, setActiveLayers] = useState(DEFAULT_LAYERS);
  const [categoryFilter, setCategoryFilter] = useState<"all" | GlobalIntelCategory>("all");
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>("all");
  const [timeWindow, setTimeWindow] = useState<TimeWindow>("24h");
  const [query, setQuery] = useState("");
  const [showObservations, setShowObservations] = useState(false);
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
    setStatus("connecting");
    setError("");
    setSnapshot({});
    setProgress({ done: 0, total: 0 });

    const loadSnapshot = (request: Promise<Record<string, unknown>>) => {
      void request.then((payload) => {
        if (!active) return;
        setSnapshot((current) => mergeSnapshot(current, payload));
      }).catch(() => {
        if (active) setError("全球情报静态数据暂时不可用");
      });
    };
    loadSnapshot(dataSource.staticSnapshot());

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
  }, [dataSource, refreshNonce]);

  const points = useMemo(() => normalizeGlobalIntelPoints(snapshot), [snapshot]);
  const events = useMemo(
    () => normalizeGlobalIntelEvents(snapshot, militaryTrackHistory),
    [militaryTrackHistory, snapshot],
  );
  const routes = useMemo(() => normalizeGlobalIntelRoutes(snapshot), [snapshot]);
  const actionableEvents = useMemo(
    () => events.filter(isActionableGlobalIntelEvent),
    [events],
  );
  const observationEvents = useMemo(
    () => events.filter((event) => !isActionableGlobalIntelEvent(event)),
    [events],
  );
  const routeImpacts = useMemo(
    () => calculateGlobalIntelRouteImpacts(actionableEvents, points, routes, riskClock),
    [actionableEvents, points, riskClock, routes],
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
    for (const event of actionableEvents) counts[event.category] = (counts[event.category] ?? 0) + 1;
    return counts;
  }, [actionableEvents]);
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
    return events.filter((event) => {
      if (!showObservations && !isActionableGlobalIntelEvent(event)) return false;
      if (categoryFilter !== "all" && event.category !== categoryFilter) return false;
      if (!matchesSeverity(event.severity, severityFilter)) return false;
      if (!inTimeWindow(event.timestamp, timeWindow)) return false;
      if (selectedRegion) {
        const point = event.pointId ? pointById.get(event.pointId) : undefined;
        if (!point || !pointInRegion(point, selectedRegion)) return false;
      }
      if (!normalizedQuery) return true;
      return `${event.title} ${event.detail} ${event.source} ${event.country ?? ""}`
        .toLocaleLowerCase()
        .includes(normalizedQuery);
    });
  }, [categoryFilter, events, pointById, query, selectedRegion, severityFilter, showObservations, timeWindow]);
  const playbackRange = useMemo(() => {
    const timestamps = filteredEvents.map((event) => Date.parse(event.timestamp)).filter(Number.isFinite);
    return timestamps.length
      ? { start: Math.min(...timestamps), end: Math.max(...timestamps) }
      : { start: Date.now(), end: Date.now() };
  }, [filteredEvents]);
  const playbackTime = playbackRange.start
    + (playbackRange.end - playbackRange.start) * playbackCursor / 100;
  const visibleEvents = useMemo(
    () => filteredEvents.filter((event) => Date.parse(event.timestamp) <= playbackTime),
    [filteredEvents, playbackTime],
  );
  const eventClusters = useMemo(() => clusterGlobalIntelEvents(actionableEvents), [actionableEvents]);
  const visibleEventClusters = useMemo(
    () => clusterGlobalIntelEvents(visibleEvents),
    [visibleEvents],
  );
  const countryRisk = useMemo(() => {
    const risk: Record<string, number> = {};
    for (const event of actionableEvents) {
      if (!event.countryCode) continue;
      risk[event.countryCode] = Math.min(100, (risk[event.countryCode] ?? 0) + RISK_WEIGHT[event.severity]);
    }
    return risk;
  }, [actionableEvents]);
  const selectedEvent = events.find((event) => event.id === selectedEventId);
  const selectedCluster = eventClusters.find((cluster) => (
    cluster.events.some((event) => event.id === selectedEventId)
  ));
  const selectedPoint = points.find((point) => point.id === selectedPointId);
  const selectedFacts = selectedEvent?.facts ?? selectedPoint?.facts;
  const selectedContent = selectedEvent?.content ?? selectedPoint?.content;
  const selectedRoute = routesWithRisk.find((route) => route.id === selectedRouteId);
  const selectedRouteImpacts = routeImpacts.filter((impact) => impact.routeId === selectedRouteId);
  const selectedRouteEvents = selectedRouteImpacts
    .map((impact) => ({ impact, event: events.find((event) => event.id === impact.eventId) }))
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
  const risk = briefing;
  const highPriorityEventCount = actionableEvents.filter((event) => (
    event.severity === "critical" || event.severity === "high"
  )).length;
  const highPriorityCount = highPriorityEventCount + highRouteAlertCount;
  const lastUpdate = typeof snapshot.timestamp === "string" ? snapshot.timestamp : "";

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
      eventCount: events.length,
      actionableEventCount: actionableEvents.length,
      observationCount: observationEvents.length,
      visibleEventCount: visibleEvents.length,
      eventClusterCount: eventClusters.length,
      visibleEventClusterCount: visibleEventClusters.length,
      highPriorityCount,
      situationPreset: activePreset?.id ?? "custom",
      activeLayers: [...activeLayers],
      filters: { categoryFilter, severityFilter, timeWindow, query, showObservations },
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
      lastUpdate: lastUpdate || null,
      events: visibleEvents.slice(0, 30),
      dataContract: GLOBAL_INTELLIGENCE_CONTRACT,
      source: "world-intel-mcp",
    });
  }, [actionableEvents.length, activeLayers, activePreset?.id, activeRouteKinds, affectedRouteCount, briefing, categoryFilter, countryRisk, eventClusters.length, events.length, health.cache, health.healthy, health.issueCount, health.total, highPriorityCount, highRouteAlertCount, lastUpdate, mapFocus, mapMode, marketConfirmedRouteCount, observationEvents.length, onContextChange, playbackCursor, playbackPlaying, playbackTime, points.length, progress, query, routeAlerts.length, routes.length, selectedEvent, selectedPoint, selectedRegion, selectedRoute, severityFilter, showCountryRisk, showObservations, status, timeWindow, trend, visibleEventClusters.length, visibleEvents, visiblePoints.length, visibleRoutes.length, watchedRegionViews]);

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
    const event = events.find((item) => item.pointId === point.id);
    setSelectedEventId(event?.id ?? "");
    setSelectedRouteId("");
  }, [events]);

  const selectEvent = (event: GlobalIntelEvent) => {
    setSelectedEventId(event.id);
    if (event.pointId) setSelectedPointId(event.pointId);
    setSelectedRouteId("");
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
            }}
            aria-expanded={trendPanelOpen}
          >
            趋势<TrendingUp size={11} />
          </button>
        </div>
        <div><span><CircleDot size={14} />地图信号</span><strong>{visiblePoints.length}</strong><small>{points.length} 个点位 · {affectedRouteCount} 条通道受影响</small></div>
        <div className="intel-health-card" data-issues={health.issueCount > 0}>
          <span><Radio size={14} />数据源健康</span>
          <strong>{health.total ? `${health.healthy}/${health.total}` : health.issueCount ? `${health.issueCount} 异常` : "连接中"}</strong>
          <small>{status === "live" ? "实时流已连接" : status === "degraded" ? "降级重连中" : "正在建立连接"}{health.issueCount ? ` · ${health.issueCount} 项异常` : ""}</small>
          <button
            type="button"
            onClick={() => {
              setHealthPanelOpen((value) => !value);
              setBriefPanelOpen(false);
              setTrendPanelOpen(false);
            }}
            aria-expanded={healthPanelOpen}
          >
            详情<ChevronDown size={11} />
          </button>
        </div>
        <div className="intel-load-card"><span><Activity size={14} />加载进度</span><strong>{progress.total ? `${progress.done}/${progress.total}` : "静态层"}</strong><small>{lastUpdate ? relativeTime(lastUpdate) : "等待动态数据"}</small></div>
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
        <div className="intel-segments intel-map-mode" aria-label="地图模式">
          <button type="button" aria-pressed={mapMode === "signals"} onClick={() => setMapMode("signals")}><MapIcon size={13} />信号</button>
          <button type="button" aria-pressed={mapMode === "heat"} onClick={() => setMapMode("heat")}><Flame size={13} />热力</button>
        </div>
        <div className="intel-segments intel-map-overlays" aria-label="地图叠加层">
          <button type="button" aria-pressed={showCountryRisk} onClick={() => setShowCountryRisk((value) => !value)}><Landmark size={13} />国家风险</button>
        </div>
        <div className="intel-segments intel-route-filters" aria-label="战略通道分类">
          {ROUTE_FILTERS.map(({ kind, label, icon: Icon }) => (
            <button type="button" key={kind} aria-pressed={activeRouteKinds.has(kind)} onClick={() => toggleRouteKind(kind)}>
              <Icon size={13} />{label} {routes.filter((route) => route.kind === kind).length}
            </button>
          ))}
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
          <footer><Clock3 size={13} />图层与实时流同步</footer>
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
            <small>{visibleEventClusters.length} 簇 / {visibleEvents.length} 记录</small>
          </header>
          <div className="intel-category-strip" role="group" aria-label="事件分类">
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
              const event = cluster.primary;
              const meta = CATEGORY_META[event.category];
              const Icon = meta.icon;
              return (
                <article key={cluster.id} data-selected={cluster.events.some((item) => item.id === selectedEventId)} data-severity={event.severity}>
                  <button type="button" onClick={() => selectEvent(event)}>
                    <i style={{ "--event-color": meta.color } as CSSProperties}><Icon size={13} /></i>
                    <span>
                      <small>
                        {meta.label} · {relativeTime(cluster.updatedAt)}
                        {cluster.events.length > 1 ? <mark>{cluster.events.length} 条证据</mark> : null}
                      </small>
                      <strong>{event.title}</strong>
                      <em>{event.detail}</em>
                      <b>{cluster.sources.slice(0, 3).join(" / ")} · {confidenceLabel(cluster)}</b>
                    </span>
                  </button>
                </article>
              );
            })}
            {visibleEventClusters.length === 0 ? <div className="intel-empty">当前筛选没有匹配事件</div> : null}
          </div>
        </section>

        {selectedEvent || selectedPoint || selectedRoute ? (
          <aside className="intel-detail-drawer">
            <header>
              <div><small>INTELLIGENCE DOSSIER</small><strong>事件详情</strong></div>
              <button type="button" onClick={clearSelection} aria-label="关闭详情"><X size={15} /></button>
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
              {selectedRoute ? (
                <dl>
                  <div><dt>类型</dt><dd>{selectedRoute.kind === "pipeline" ? "能源管线" : selectedRoute.kind === "cable" ? "海底光缆走廊" : "航运通道"}</dd></div>
                  <div><dt>路径</dt><dd>{selectedRoute.pathType === "corridor" ? "示意走廊" : "精确线路"}</dd></div>
                  <div><dt>状态</dt><dd>{selectedRoute.status || "active"}</dd></div>
                  <div><dt>风险</dt><dd>{selectedRoute.riskScore ? `${selectedRoute.riskScore}/100` : "未发现直接影响"}</dd></div>
                  <div><dt>置信度</dt><dd>{selectedRoutePrimaryImpact ? `${selectedRoutePrimaryImpact.confidence}% · ${selectedRoutePrimaryImpact.sourceCount} 个来源` : "暂无证据"}</dd></div>
                  <div><dt>预警</dt><dd>{selectedRouteAlert ? `${selectedRouteAlert.level === "critical" ? "严重" : selectedRouteAlert.level === "high" ? "高优先级" : "观察"} · 综合 ${selectedRouteAlert.score}` : "未触发"}</dd></div>
                </dl>
              ) : (
                <dl>
                  <div><dt>严重度</dt><dd>{selectedEvent?.severity ?? selectedPoint?.severity}</dd></div>
                  <div><dt>来源</dt><dd>{selectedEvent?.source ?? selectedPoint?.source}</dd></div>
                  <div><dt>时间</dt><dd>{selectedEvent ? new Date(selectedEvent.timestamp).toLocaleString("zh-CN") : selectedPoint?.timestamp ? new Date(selectedPoint.timestamp).toLocaleString("zh-CN") : "静态情报层"}</dd></div>
                  <div><dt>位置</dt><dd>{selectedPoint ? `${selectedPoint.latitude.toFixed(3)}, ${selectedPoint.longitude.toFixed(3)}` : selectedEvent?.country || "未标注"}</dd></div>
                  {selectedFacts?.map((fact) => (
                    <div key={`${fact.label}-${fact.value}`}><dt>{fact.label}</dt><dd>{fact.value}</dd></div>
                  ))}
                </dl>
              )}
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
