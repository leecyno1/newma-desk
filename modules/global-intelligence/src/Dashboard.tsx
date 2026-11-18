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
import { buildInvestmentTransmission } from "./investment";
import { InvestmentTransmission } from "./InvestmentTransmission";
import { ComparisonPanel, readCrucixComparison } from "./ComparisonPanel";

import {
  GLOBAL_INTELLIGENCE_CONTRACT,
  mediaTimeCoverageLabel,
  calculateGlobalIntelMarketReactions,
  calculateGlobalIntelRouteAlerts,
  calculateGlobalIntelRouteImpacts,
  clusterGlobalIntelEvents,
  globalIntelEventActivityTimestamp as eventActivityTimestamp,
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
  observation?: Record<string, unknown>;
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
  score: number | null;
  earthquakeCount: number | null;
}

const MEDIA_SENTIMENT_ORDER = ["positive", "negative", "neutral", "mixed"] as const;
const MEDIA_SENTIMENT_SHORT_LABEL = {
  positive: "正",
  negative: "负",
  neutral: "中",
  mixed: "混",
  unknown: "未判定",
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
  topicBaselines?: Record<string, string>;
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
  mentionCount: number | null;
  sourceCount: number | null;
  heatScore: number | null;
  attentionScore?: number | null;
  spreadScore: number | null;
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
// Keep legacy history untouched; its defaults are not verified observations.
const MEDIA_TOPIC_HISTORY_KEY = "newma-desk.global-intelligence.media-topic-history.v2";
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
  nuclear_monitor: "试验场邻近地震",
  traffic_flow: "交通流",
  traffic_incidents: "交通事件",
  webcams: "公共摄像头",
  election_calendar: "选举日历",
  strategic_posture: "战略态势",
  situation_brief: "态势简报",
  prediction_markets: "预测市场",
  airport_delays: "机场运行通告",
  domestic_flights: "全球航空流量",
  space_weather: "空间天气",
  ai_watch: "AI 动态",
  service_status: "云服务状态",
  fleet_report: "航空与航道观察",
  social_signals: "社交信号",
  displacement: "人口流离失所",
  population_exposure: "人口暴露",
  signal_convergence: "区域地震观察",
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

function privateStorageKey(key: string, scoped: boolean, identity?: {userId: string; workspaceId: string}): string | null {
  if (!scoped) return key;
  return identity ? `${key}:${JSON.stringify([identity.userId, identity.workspaceId])}` : null;
}

function loadWatchRegions(key: string | null): SavedWatchRegion[] {
  try {
    const saved = JSON.parse((key && localStorage.getItem(key)) || "[]") as unknown;
    return Array.isArray(saved) ? saved as SavedWatchRegion[] : [];
  } catch {
    return [];
  }
}

function loadRouteAlertStates(key: string | null): Record<string, GlobalIntelRouteAlertState> {
  try {
    const saved = JSON.parse((key && localStorage.getItem(key)) || "{}") as unknown;
    return typeof saved === "object" && saved !== null && !Array.isArray(saved)
      ? saved as Record<string, GlobalIntelRouteAlertState>
      : {};
  } catch {
    return {};
  }
}

function loadMilitaryTrackHistory(key: string | null): GlobalIntelMilitaryTrackHistory {
  try {
    const saved = JSON.parse((key && sessionStorage.getItem(key)) || "{}") as unknown;
    return typeof saved === "object" && saved !== null && !Array.isArray(saved)
      ? saved as GlobalIntelMilitaryTrackHistory
      : {};
  } catch {
    return {};
  }
}

function loadEventHistory(key: string | null): GlobalIntelEventHistoryEntry[] {
  try {
    const saved = JSON.parse((key && localStorage.getItem(key)) || "[]") as unknown;
    return Array.isArray(saved)
      ? saved.map((item) => ({
        ...item as GlobalIntelEventHistoryEntry,
        // These legacy records may contain a collection-time fallback or local-time RSS conversion.
        ...((item.source === "NGA 航行警告" || item.source === "USGS" || item.recordKind === "news" || item.source === "World Intel 服务状态") && !item.timestampBasis
          ? { timestamp: "", timestampBasis: "unknown" as const, sourceFreshness: "unknown" as const } : {}),
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

function loadEventDispositions(key: string | null): Record<string, EventDisposition> {
  try {
    const saved = JSON.parse((key && localStorage.getItem(key)) || "{}") as unknown;
    return typeof saved === "object" && saved !== null && !Array.isArray(saved)
      ? saved as Record<string, EventDisposition>
      : {};
  } catch {
    return {};
  }
}

function loadMediaWatchRules(key: string | null): MediaWatchRule[] {
  try {
    const saved = JSON.parse((key && localStorage.getItem(key)) || "[]") as unknown;
    return Array.isArray(saved) ? saved as MediaWatchRule[] : [];
  } catch {
    return [];
  }
}

function loadMediaTopicHistory(key: string | null): MediaTopicHistoryEntry[] {
  try {
    const saved = JSON.parse((key && localStorage.getItem(key)) || "[]") as unknown;
    return Array.isArray(saved) ? saved.map((item) => ({
      ...item as MediaTopicHistoryEntry,
      verificationHistory: Array.isArray((item as MediaTopicHistoryEntry).verificationHistory)
        ? (item as MediaTopicHistoryEntry).verificationHistory
        : [{
          status: (item as MediaTopicHistoryEntry).verificationStatus || "待核验",
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
  return keywords.length > 0 && matches >= Math.min(2, keywords.length);
}

function mediaTopicValues(topic: GlobalMediaMonitorTopic) {
  return [topic.mentionCount, topic.sourceCount, topic.heatScore, topic.attentionScore, topic.spreadScore,
    topic.verificationStatus === "待核验" ? null : topic.verificationStatus, topic.framingDivergence]
    .map((value) => value === null ? "" : String(value));
}

function mediaTopicSignature(topic: GlobalMediaMonitorTopic) {
  return ["v2", ...mediaTopicValues(topic)].join("|");
}

function mediaWatchBaseline(rule: MediaWatchRule, topic: GlobalMediaMonitorTopic) {
  const baseline = rule.topicBaselines?.[topic.id];
  return typeof baseline === "string" ? baseline : rule.id === topic.id ? rule.baselineSignature : undefined;
}

function mediaTopicComparison(signature: string | undefined, topic: GlobalMediaMonitorTopic) {
  const baseline = signature?.startsWith("v2|") ? signature.split("|").slice(1) : [];
  const current = mediaTopicValues(topic);
  return {
    changed: current.some((value, index) => value !== "" && baseline[index] && baseline[index] !== value),
    incomplete: current.some((value, index) => value === "" || !baseline[index]),
    // Fill previously unknown fields without acknowledging existing changes.
    baseline: ["v2", ...current.map((value, index) => baseline[index] || value)].join("|"),
  };
}

function mergeMediaTopicHistory(
  history: MediaTopicHistoryEntry[],
  topics: GlobalMediaMonitorTopic[],
  observedAt: string,
) {
  const byId = new Map(history.map((item) => [item.id, item]));
  for (const topic of topics) {
    const previous = byId.get(topic.id);
    const changed = previous && (
      (["mentionCount", "sourceCount", "heatScore", "attentionScore", "spreadScore"] as const)
        .some((key) => previous[key] != null && topic[key] != null && previous[key] !== topic[key])
      || previous.verificationStatus !== "待核验" && topic.verificationStatus !== "待核验" && previous.verificationStatus !== topic.verificationStatus
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
      mentionCount: topic.mentionCount ?? previous?.mentionCount ?? null,
      sourceCount: topic.sourceCount ?? previous?.sourceCount ?? null,
      heatScore: topic.heatScore ?? previous?.heatScore ?? null,
      attentionScore: topic.attentionScore ?? previous?.attentionScore ?? null,
      spreadScore: topic.spreadScore ?? previous?.spreadScore ?? null,
      verificationStatus: topic.verificationStatus === "待核验" ? previous?.verificationStatus ?? "待核验" : topic.verificationStatus,
      verificationHistory: topic.verificationStatus !== "待核验" && previous?.verificationStatus !== topic.verificationStatus
        ? [
          ...(previous?.verificationHistory ?? []),
          { status: topic.verificationStatus, timestamp: observedAt },
        ].slice(-8)
        : previous?.verificationHistory ?? [],
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
  if (delta < -60_000) return "未来时间，待核验";
  const minutes = Math.max(0, Math.round(delta / 60_000));
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  return `${Math.round(hours / 24)} 天前`;
}

function sourceTimeFieldLabel(record?: GlobalIntelEvent | GlobalIntelPoint) {
  if (record?.timestampBasis === "indexed") return "来源收录时间";
  if (record?.timestampBasis === "updated") return "来源更新时间";
  if (record?.timestampBasis === "occurred" || record?.source === "USGS") return "发生时间";
  if (record?.timestampBasis === "collected") return "采集时间";
  if (record?.timestampBasis === "published" || record?.source === "NGA 航行警告" || (record && "recordKind" in record && record.recordKind === "news")) return "发布日期";
  return "来源时间";
}

function eventTimeLabel(event: GlobalIntelEvent) {
  if (event.timestampBasis === "unknown") return `${sourceTimeFieldLabel(event)}未知`;
  const label = event.timestampBasis === "indexed" ? "来源收录"
    : event.timestampBasis === "updated" ? "来源更新"
    : event.timestampBasis === "occurred" ? "发生"
    : event.timestampBasis === "published" || event.recordKind === "news" ? "发布"
    : event.timestampBasis === "collected" ? "采集" : "来源时间";
  return `${label} ${relativeTime(event.timestamp)}`;
}

function absoluteTime(timestamp?: string) {
  return timestamp && Number.isFinite(Date.parse(timestamp))
    ? new Date(timestamp).toLocaleString("zh-CN") : "未知";
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

  for (const [source, raw] of Object.entries(sourceHealth)) {
    const info = recordValue(raw);
    const rawStatus = typeof info.status === "string" ? info.status : "unknown";
    const failures = Number(info.failures ?? 0);
    const cooldown = Number(info.cooldown_remaining_s ?? 0);
    const isHealthy = rawStatus === "closed" || rawStatus === "ok" || rawStatus === "healthy";
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
      items.set(source, {
        ...existing,
        ...(isStale && existing.status === "healthy"
          ? { status: "stale", statusLabel: "缓存过期", reason: "来源连接正常，但最新缓存已经超过有效期" } as const : {}),
        ...(freshness ? { freshness } : {}),
      });
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

  const worldNews = recordValue(snapshot.news_feed);
  const worldSources = recordList(worldNews.source_results);
  // Namespace cache freshness is not a source receipt (it can contain an HTML
  // error page or a newly saved historical fallback). Prefer the actual rows.
  if (worldSources.length) items.delete("news");
  for (const row of worldSources) {
    if (typeof row.id !== "string" || typeof row.source !== "string") continue;
    const state: SourceHealthItem["status"] = row.status === "unavailable" ? "error"
      : row.status === "stale" || row.freshness === "stale" ? "stale"
        : row.status === "ok" && row.freshness === "fresh" ? "healthy" : "degraded";
    const count = typeof row.count === "number" ? row.count : null;
    // Use the Fetcher source ID: a closed circuit is not a successful feed parse.
    items.set(row.id, {
      id: row.id, label: "World RSS / " + row.source, status: state,
      statusLabel: state === "error" ? "取数失败" : state === "stale" ? "保留旧缓存"
        : state === "healthy" ? count === 0 ? "有效空源" : "正常" : "部分或待核验",
      reason: (typeof row.reason === "string" ? row.reason : "来源未提供说明")
        + (count === null ? " · 数量未知" : ` · 解析 ${count} 条（非当前展示条数）`)
        + (typeof row.collected_at === "string" ? ` · 采集于 ${row.collected_at}` : " · 采集时间未知"),
    });
  }
  const worldCoverage = recordValue(worldNews.coverage);
  if (typeof worldCoverage.expected === "number" && worldCoverage.expected > worldSources.length) {
    items.set("news_feed:coverage", {
      id: "news_feed:coverage", label: "World RSS 覆盖", status: "degraded", statusLabel: "回执不完整",
      reason: `应有 ${worldCoverage.expected} 个来源，仅收到 ${worldSources.length} 个回执；缺失不代表没有新闻`,
    });
  }

  const crucix = recordValue(snapshot.crucix_intelligence);
  if (Object.keys(crucix).length) {
    const crucixHealth = recordValue(crucix.sourceHealth);
    const crucixFreshness = recordValue(crucix.freshness);
    const failed = Number(crucixHealth.failed ?? 0);
    const partial = Number(crucixHealth.partial ?? 0);
    const unknown = Number(crucixHealth.unknown ?? 0);
    const queried = Number(crucixHealth.queried ?? 0);
    const ok = Number(crucixHealth.ok ?? 0);
    const freshnessStatus = typeof crucixFreshness.status === "string"
      ? crucixFreshness.status
      : "unknown";
    const status: SourceHealthItem["status"] = freshnessStatus === "stale"
      ? "stale"
      : freshnessStatus === "fresh" && queried > 0 && ok === queried ? "healthy" : "degraded";
    const ageSeconds = typeof crucixFreshness.ageSeconds === "number"
      ? crucixFreshness.ageSeconds
      : Number.NaN;
    items.set("crucix", {
      id: "crucix",
      label: sourceLabel("crucix"),
      status,
      statusLabel: status === "healthy" ? "正常" : status === "stale" ? "数据过期" : "部分降级",
      reason: queried > 0 ? `${ok}/${queried} 个来源采集正常，${failed} 不可用、${partial} 部分可用、${Number(crucixHealth.stale ?? 0)} 陈旧、${unknown} 待核验` : "等待 Crucix 首轮扫描",
      ...(Number.isFinite(ageSeconds) ? { freshness: freshnessLabel(ageSeconds) } : {}),
    });

    const sourceRows = recordList(crucixHealth.items).filter((row) => typeof row.source === "string" && row.source);
    const names = new Set(sourceRows.map((row) => row.source));
    // Complete per-source receipts replace the roll-up so the console does not double-count them.
    if (queried > 0 && names.size === queried) items.delete("crucix");
    for (const row of sourceRows) {
      const name = String(row.source);
      const state: SourceHealthItem["status"] = row.status === "error" ? "error"
        : row.status === "stale" || freshnessStatus === "stale" ? "stale"
          : row.status === "ok" && freshnessStatus === "fresh" ? "healthy" : "degraded";
      items.set("crucix:" + name, {
        id: "crucix:" + name, label: "Crucix / " + name, status: state,
        statusLabel: state === "error" ? "取数失败" : state === "stale" ? "数据过期"
          : state === "healthy" ? "正常" : row.status === "partial" ? "部分可用" : "待核验",
        reason: typeof row.reason === "string" ? row.reason : "来源未提供查询说明，不能据此判断风险已解除",
        ...(Number.isFinite(ageSeconds) ? { freshness: "采集快照 " + freshnessLabel(ageSeconds) } : {}),
      });
    }

    const macro = recordValue(crucix.macro);
    const supply = recordValue(macro.gscpi);
    if (Object.keys(supply).length) {
      const freshness = recordValue(supply.freshness).status;
      const state: SourceHealthItem["status"] = supply.status === "error" ? "error"
        : freshness === "stale" || freshnessStatus === "stale" ? "stale"
          : supply.status === "ok" && supply.basisVerified === true && freshness === "fresh" && freshnessStatus === "fresh" ? "healthy" : "degraded";
      const unit = supply.unit === "standard-deviations" ? "标准差" : "单位待核验";
      items.set("crucix:GSCPI", {
        id: "crucix:GSCPI", label: "Crucix / GSCPI", status: state,
        statusLabel: state === "error" ? "取数失败" : state === "stale" ? "历史观测"
          : state === "healthy" ? "观测可用" : "部分或待核验",
        reason: `指数 ${supply.value ?? "未知"} ${unit} · 月度统计期 ${supply.period ?? "未知"}`
          + ` · 修订列标识 ${supply.vintage ?? "未知"}（非发布日期） · 拒绝 ${supply.rejected ?? "未知"} · 缺格 ${supply.missing ?? "未知"}`
          + `；${supply.note || "月度统计期不是发布时间，零代表历史均值；历史版本待核验。"}`,
        freshness: `采集于 ${supply.collectedAt ?? "未知"} · 观测时效 ${freshness ?? "unknown"}（本地窗口，非官方发布保证）`,
        observation: supply,
      });
    }
    for (const row of recordList(recordValue(macro.metals).observations)) {
      const name = row.id === "gold" ? "黄金" : row.id === "silver" ? "白银" : null;
      if (!name) continue;
      const freshness = recordValue(row.freshness).status;
      const state: SourceHealthItem["status"] = freshness === "stale" || freshnessStatus === "stale" ? "stale"
        : row.basisVerified === true && freshness === "fresh" && freshnessStatus === "fresh" ? "healthy" : "degraded";
      const provenance = recordValue(row.source);
      items.set("crucix:metal:" + row.id, {
        id: "crucix:metal:" + row.id, label: `Crucix / ${name}报价`, status: state,
        statusLabel: state === "healthy" ? "观测可用" : state === "stale" ? "历史报价" : "报价待核验",
        reason: `价格 ${row.value ?? "未知"} ${row.unit === "USD/troy-ounce" ? "USD/金衡盎司" : "单位待核验"}`
          + ` · ${row.kind === "futures" ? "连续期货" : "类型待核验"} · ${provenance.id ?? "来源未知"} / ${provenance.seriesId ?? "代码未知"}`
          + `；${row.note || "连续期货可能换月，不是现货；前收日期未知。"}`,
        freshness: `报价于 ${row.observedAt ?? "未知"} · ${freshness ?? "unknown"}（7自然日本地窗口，不是实时保证）`,
        observation: row,
      });
    }

    const who = recordValue(recordValue(crucix.global).who);
    if (Object.keys(who).length) {
      const freshness = recordValue(who.freshness).status;
      const state: SourceHealthItem["status"] = who.status === "error" ? "error"
        : freshness === "stale" ? "stale" : who.status === "ok" && who.complete === true && freshness === "fresh" ? "healthy" : "degraded";
      const window = recordValue(who.window);
      const gaps = Object.values(recordValue(who.gaps)).filter((value) => typeof value === "string").join("；");
      items.set("crucix:WHO", {
        id: "crucix:WHO", label: "Crucix / WHO", status: state,
        statusLabel: state === "error" ? "取数失败" : state === "stale" ? "历史公告快照"
          : state === "healthy" ? who.reportCount === 0 ? "有效空窗口" : "公告查询可用" : "覆盖不完整或待核验",
        reason: `窗口公告 ${who.reportCount ?? "未知"} 篇 · 展示 ${who.displayed ?? "未知"} 篇 · 查询上限 ${who.queryLimit ?? "未知"}`
          + ` · 完整查询${who.complete === true ? "已核对" : "未确认"}；${gaps ? gaps + "；" : ""}${who.note || "公告样本不能证明全球疫情覆盖或感染人数。"}`,
        freshness: `查询窗口 ${window.start ?? "未知"} → ${window.end ?? "未知"} · ${who.collectedAt ? "采集于 " + who.collectedAt : "检查于 " + (who.checkedAt ?? "未知") + "，未取得已核验公告"}`,
        observation: who,
      });
    }

    const ofac = recordValue(recordValue(crucix.global).ofac);
    if (Object.keys(ofac).length) {
      const freshness = recordValue(ofac.collectionFreshness).status;
      const state: SourceHealthItem["status"] = ofac.status === "error" ? "error"
        : freshness === "stale" ? "stale" : ofac.status === "ok" && freshness === "fresh" ? "healthy" : "degraded";
      items.set("crucix:OFAC", {
        id: "crucix:OFAC", label: "Crucix / OFAC", status: state,
        statusLabel: state === "error" ? "取数失败" : state === "stale" ? "旧采集快照"
          : state === "healthy" ? "名单已读取" : ofac.status === "partial" ? "部分可用" : "待核验",
        reason: `名单发布日 ${ofac.publishedDate ?? "未知"}（仅日期） · 实际解析 ${ofac.entryCount ?? "未知"} 条 · 声明 ${ofac.recordCount ?? "未知"} 条`
          + ` · 完整性${ofac.complete === true ? "已核对" : "未确认"}；${ofac.reason || "来源说明缺失"}；${ofac.note || "仅 SDN 名单观察，非合规筛查"}`,
        freshness: ofac.collectedAt
          ? `采集于 ${ofac.collectedAt} · ${freshness === "fresh" ? "采集快照新鲜，不代表名单刚发布" : freshness === "stale" ? "旧快照，当前名单待核验" : "采集时效未知"}`
          : `检查于 ${ofac.checkedAt ?? "未知"} · 未取得已核验名单`,
        observation: ofac,
      });
    }

    const rss = recordValue(crucix.newsCoverage);
    if (Object.keys(rss).length) {
      const sources = recordList(rss.items);
      const requested = Number(recordValue(rss.coverage).requested ?? 0);
      for (const row of sources) {
        const name = typeof row.source === "string" ? row.source : "未知来源";
        const freshness = recordValue(row.freshness);
        const state: SourceHealthItem["status"] = row.cached === true ? "stale" : row.status === "error" ? "error"
          : freshness.status === "stale" ? "stale"
            : row.status === "ok" && freshness.status === "fresh" ? "healthy" : "degraded";
        const count = typeof row.count === "number" ? row.count : null;
        items.set("rss:" + name, {
          id: "rss:" + name, label: "RSS / " + name, status: state,
          statusLabel: row.cached === true ? "保留旧缓存" : state === "healthy" ? count === 0 ? "有效空源" : "正常"
            : state === "error" ? "取数失败" : state === "stale" ? "数据过期" : "部分或待核验",
          reason: (typeof row.reason === "string" ? row.reason : "未返回来源说明")
            + (count !== null ? ` · 解析 ${count} 条（非当前展示条数）` : " · 数量未知")
            + (row.cached === true ? ` · 使用上次有效结果 ${row.availableCount ?? "未知"} 条，采集于 ${row.dataAsOf ?? "未知"}；${rss.mode === "cache" ? "本次未联网" : "本次更新失败"}` : ""),
          ...(typeof freshness.ageSeconds === "number" ? { freshness: "检查于 " + freshnessLabel(freshness.ageSeconds) } : {}),
          observation: row,
        });
      }
      if (!sources.length || requested > sources.length) items.set("rss:coverage", {
        id: "rss:coverage", label: "RSS 覆盖", status: "degraded", statusLabel: "待核验",
        reason: requested === 0 ? "本轮未执行 RSS 采集，不代表没有新闻" : "部分来源缺少采集结果",
      });
      const cache = recordValue(rss.cache);
      if (cache.status === "error") items.set("rss:cache", {
        id: "rss:cache", label: "RSS 缓存", status: "degraded", statusLabel: "缓存异常",
        reason: typeof cache.reason === "string" ? cache.reason : "缓存恢复或保存失败",
      });
    }
  }

  for (const [domain, raw] of Object.entries(snapshot)) {
    if (domain.startsWith("_") || domain === "source_health" || domain === "cache_freshness" || domain === "cache_stats") continue;
    const info = recordValue(raw);
    if (["earthquakes", "signal_convergence", "nuclear_monitor", "population_exposure"].includes(domain)) {
      const coverage = recordValue(info.coverage);
      const expired = Date.parse(String(info.cache_expires_at ?? "")) < Date.now();
      const state = info.error || info.status === "unavailable" ? "error" : expired || info.freshness === "stale" || info.status === "stale" ? "stale"
        : info.status === "ok" ? "healthy" : "degraded";
      items.set(domain, { id: domain, label: sourceLabel(domain), status: state,
        statusLabel: state === "error" ? "数据缺失" : state === "stale" ? "历史样本" : state === "healthy" ? "样本可用" : "部分或待核验",
        reason: `${info.error || info.note || "目录样本不代表全部事件或实际灾损"} · 来源更新 ${info.source_updated_at ?? "未知"}`
          + (coverage.expected != null ? ` · 覆盖 ${coverage.available ?? "未知"}/${coverage.expected}` : "")
          + (info.truncated ? " · 已达样本上限" : ""),
      });
      continue;
    }
    if (["strategic_posture", "alert_digest"].includes(domain) && ["partial", "unavailable"].includes(String(info.status))) {
      const coverage = recordValue(info.coverage);
      items.set(`${domain}:coverage`, {
        id: `${domain}:coverage`, label: `${SOURCE_LABELS[domain] ?? domain}覆盖`, status: "degraded", statusLabel: "评估不完整",
        reason: `可用样本 ${coverage.available ?? "未知"}/${coverage.expected ?? "未知"}，完整输入 ${coverage.complete ?? "未知"}；缺失不代表安全，分项评分是启发式观察值，不是风险概率。`,
      });
    }
    if (domain === "situation_brief" && (info.status === "partial" || info.status === "unavailable")) {
      const coverage = recordValue(info.coverage);
      items.set("situation_brief:coverage", {
        id: "situation_brief:coverage", label: "态势简报数据覆盖", status: "degraded", statusLabel: "证据不完整",
        reason: `简报仅有 ${coverage.available ?? "未知"}/${coverage.expected ?? "未知"} 项可用数字指标；缺失不代表零风险，样本计数不代表全球总量`,
      });
    }
    if (domain === "airport_delays") {
      const known = info.observation_basis === "faa-nas-airport-advisories";
      const sourceAge = Date.now() - Date.parse(String(info.updated_at ?? ""));
      const expired = Date.parse(String(info.cache_expires_at ?? "")) < Date.now();
      const airportStatus = !known ? "degraded" : info.status === "unavailable" ? "error"
        : !Number.isFinite(sourceAge) || sourceAge < 0 ? "degraded"
        : info.status === "stale" || info.freshness === "stale" || expired || sourceAge > 30 * 60 * 1000 ? "stale"
          : info.status === "ok" && info.freshness === "fresh" ? "healthy" : "degraded";
      items.delete("faa");
      items.set(domain, {
        id: domain, label: "FAA 机场运行通告", status: airportStatus,
        statusLabel: airportStatus === "healthy" ? "官方通告可用" : airportStatus === "error" ? "取数失败" : airportStatus === "stale" ? "历史通告" : "口径待核验",
        reason: !known ? "旧机场查询没有完整来源回执；不能据此判断无延误"
          : `${info.reported_airport_count ?? "未知"} 个机场 / ${info.advisory_count ?? "未知"} 条通告 · 来源更新 ${info.updated_at ?? "未知"} · ${info.error || info.note || "未列出不等于无延误"}`,
      });
      continue;
    }
    if (domain === "central_bank_rates") {
      const rates = recordList(info.rates);
      const curated = rates.filter((rate) => rate.source === "curated"
        || (rate.rate == null && Object.keys(recordValue(rate.reference)).length > 0)).length;
      const undated = rates.filter((rate) => typeof rate.as_of !== "string"
        || !Number.isFinite(Date.parse(rate.as_of)) || Date.parse(rate.as_of) > Date.now()).length;
      if (curated || undated) items.set("central_bank_rates:reference", {
        id: "central_bank_rates:reference", label: "央行利率口径", status: "degraded", statusLabel: "现行值待核验",
        reason: `${rates.length} 条观测中 ${curated} 条历史手工参考，${undated} 条日期缺失或异常；不能作为当前政策利率或调息信号`,
      });
      const coverage = recordValue(info.coverage);
      if (Object.keys(coverage).length) items.set("central_bank_rates:coverage", {
        id: "central_bank_rates:coverage", label: "央行实时来源覆盖", status: info.status === "ok" ? "healthy" : "degraded",
        statusLabel: "来源覆盖", reason: `${coverage.available ?? 0}/${coverage.tracked ?? rates.length} 家取得近期观测；${coverage.queried ?? 0} 家已查询，${coverage.failed ?? 0} 失败，${coverage.stale ?? 0} 过期，${coverage.reference_only ?? 0} 家仅历史参考`,
      });
    }
    if (!info.error && info.freshness === "stale") {
      items.set(domain, {
        id: domain, label: sourceLabel(domain), status: "stale",
        statusLabel: "数据过期", reason: "当前展示上次成功取得的数据，尚未更新",
      });
      continue;
    }
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
    healthy: sortedItems.filter((item) => item.status === "healthy").length,
    total: sortedItems.length,
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
  const posture = currentResearchDomain(snapshot.strategic_posture);
  const rawScore = posture.composite_score ?? posture.overall_score ?? posture.score;
  const score = typeof rawScore === "number" && Number.isFinite(rawScore) ? rawScore : undefined;
  const rawLevel = typeof posture.risk_level === "string"
    ? posture.risk_level
    : typeof posture.overall_level === "string"
      ? posture.overall_level
      : typeof posture.level === "string"
        ? posture.level
        : "";
  return {
    score,
    level: score === undefined ? "风险待核验" : riskLevelLabel(rawLevel),
    rawLevel: score === undefined ? "UNKNOWN" : rawLevel.toUpperCase(),
  };
}

function currentResearchDomain(value: unknown) {
  const domain = recordValue(value);
  return domain.error || domain._stale || domain.freshness === "stale"
    || ["unavailable", "error", "stale"].includes(String(domain.status)) ? {} : domain;
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
  const posture = currentResearchDomain(snapshot.strategic_posture);
  const alertDigest = currentResearchDomain(snapshot.alert_digest);
  const situationBrief = recordValue(snapshot.situation_brief);
  const risk = strategicRisk(snapshot);
  const domains: PostureDomain[] = Object.entries(recordValue(posture.domain_scores))
    .filter(([, raw]) => typeof recordValue(raw).score === "number" && Number.isFinite(recordValue(raw).score))
    .map(([id, raw]) => {
      const info = recordValue(raw);
      const score = Number(info.score ?? 0);
      return {
        id,
        label: POSTURE_DOMAIN_LABELS[id] ?? id,
        score: Number.isFinite(score) ? score : 0,
        level: info.status === "partial" ? "部分证据 · 样本评分" : riskLevelLabel(typeof info.level === "string" ? info.level : ""),
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
    postureCoverage: recordValue(recordValue(snapshot.strategic_posture).coverage),
    alertCoverage: recordValue(recordValue(snapshot.alert_digest).coverage),
    domains,
    threats,
    alerts,
    alertCount: typeof alertDigest.alert_count === "number" && Number.isFinite(alertDigest.alert_count)
      ? alertDigest.alert_count : !("alert_count" in alertDigest) && Array.isArray(alertDigest.alerts) ? alerts.length : null,
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

function mediaMetric(value: number | null, suffix = "") {
  return value === null ? "—" : `${value}${suffix}`;
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
      score: typeof hotspot.convergence_score === "number" ? hotspot.convergence_score : null,
      earthquakeCount: typeof signals.earthquakes === "number" ? signals.earthquakes : null,
    };
  });
  const hotspots = liveHotspots;
  const knownScores = hotspots.flatMap((hotspot) => hotspot.score === null ? [] : [hotspot.score]);
  return {
    anomalies,
    trends,
    hotspots,
    anomalyCount: Number(weekly.current_anomaly_count ?? anomalies.length),
    trendCount: Number(weekly.trend_count ?? trends.length),
    maxConvergence: knownScores.length ? Math.max(...knownScores) : null,
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
  return parsed >= Date.now() - span && parsed <= Date.now();
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

function hasDomainData(value: unknown) {
  if (Array.isArray(value)) return true;
  const domain = recordValue(value);
  if (domain.error || ["error", "unavailable"].includes(String(domain.status))) return false;
  return Object.keys(domain).some((key) => !key.startsWith("_")
    && !["timestamp", "collected_at", "freshness", "status", "sourceHealth", "newsCoverage", "asOf"].includes(key));
}

function hasWorldSnapshotData(snapshot: Record<string, unknown>) {
  return Object.entries(snapshot).some(([key, value]) => !key.startsWith("_")
    && !["source_health", "cache_freshness", "cache_stats", "crucix_intelligence"].includes(key)
    && hasDomainData(value));
}

function hasCrucixSnapshotData(value: unknown) {
  const crucix = recordValue(value);
  const health = recordValue(crucix.sourceHealth);
  const rss = recordValue(recordValue(crucix.newsCoverage).coverage);
  if (Number(rss.succeeded ?? 0) + Number(rss.partial ?? 0) > 0
    || Number(recordValue(crucix.newsCoverage).cachedSources ?? 0) > 0) return true;
  return Object.keys(health).length
    ? Number(health.ok ?? 0) + Number(health.partial ?? 0) > 0 : hasDomainData(crucix);
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
  if (event.source === "NGA 航行警告") return "航行警告";
  if (event.recordKind === "observation") return "原始观测";
  if (event.recordKind === "news") return "新闻报道";
  return "异常事件";
}

function recordKindExplanation(event: GlobalIntelEvent) {
  if (event.source === "NGA 航行警告") {
    return "这是来源仍列出的航行警告，不等同于新发生事故。发布日期与采集、首次收录时间分开；旧缓存里的未取消状态不能证明当前仍有效。";
  }
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
  if (state === "new") return "首次收录";
  if (state === "ongoing") return "持续跟踪";
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

interface GlobalIntelligenceDashboardProps {
  dataSource: GlobalIntelDataSource;
  theme: "light" | "dark";
  refreshNonce: number;
  cacheIdentity?: { userId: string; workspaceId: string };
  scopedStorage?: boolean;
  onRefresh(): void;
  onContextChange(value: Record<string, unknown>): void;
}

export function GlobalIntelligenceDashboard(props: GlobalIntelligenceDashboardProps) {
  const key = props.scopedStorage ? JSON.stringify([props.cacheIdentity?.userId, props.cacheIdentity?.workspaceId]) : "standalone";
  return <GlobalIntelligenceDashboardContent key={key} {...props} />;
}

function GlobalIntelligenceDashboardContent({
  dataSource,
  theme,
  refreshNonce,
  cacheIdentity,
  scopedStorage = false,
  onRefresh,
  onContextChange,
}: GlobalIntelligenceDashboardProps) {
  const key = (name: string) => privateStorageKey(name, scopedStorage, cacheIdentity);
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
  const [militaryTrackHistory, setMilitaryTrackHistory] = useState(() => loadMilitaryTrackHistory(key(MILITARY_TRACKS_KEY)));
  const [eventHistory, setEventHistory] = useState(() => loadEventHistory(key(EVENT_HISTORY_KEY)));
  const [eventDispositions, setEventDispositions] = useState(() => loadEventDispositions(key(EVENT_DISPOSITIONS_KEY)));
  const [mediaWatchRules, setMediaWatchRules] = useState(() => loadMediaWatchRules(key(MEDIA_WATCH_RULES_KEY)));
  const [mediaTopicHistory, setMediaTopicHistory] = useState(() => loadMediaTopicHistory(key(MEDIA_TOPIC_HISTORY_KEY)));
  const [eventHistoryObservedAt, setEventHistoryObservedAt] = useState("");
  const [attentionBaselineReady, setAttentionBaselineReady] = useState(
    () => { const name = key(EVENT_ATTENTION_BASELINE_KEY); return !!name && localStorage.getItem(name) === "ready"; },
  );
  const [riskClock, setRiskClock] = useState(() => Date.now());
  const [status, setStatus] = useState<"connecting" | "live" | "degraded">("connecting");
  const [error, setError] = useState("");
  const [refreshRun, setRefreshRun] = useState<{
    nonce: number; source: GlobalIntelDataSource; status: "ready" | "partial" | "error";
  }>();
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
  const [watchedRegions, setWatchedRegions] = useState<SavedWatchRegion[]>(() => loadWatchRegions(key(WATCH_REGIONS_KEY)));
  const [routeAlertStates, setRouteAlertStates] = useState(() => loadRouteAlertStates(key(ROUTE_ALERTS_KEY)));
  const [watchPanelOpen, setWatchPanelOpen] = useState(false);
  const [routeAlertPanelOpen, setRouteAlertPanelOpen] = useState(false);
  const [presetMenuOpen, setPresetMenuOpen] = useState(false);
  const [healthPanelOpen, setHealthPanelOpen] = useState(false);
  const [briefPanelOpen, setBriefPanelOpen] = useState(false);
  const [trendPanelOpen, setTrendPanelOpen] = useState(false);
  const [mediaPanelOpen, setMediaPanelOpen] = useState(false);
  const [mapFocus, setMapFocus] = useState<IntelligenceMapFocus>();
  const [layersOpen, setLayersOpen] = useState(false);
  const [mapExpanded, setMapExpanded] = useState(false);

  useEffect(() => {
    const name = key(WATCH_REGIONS_KEY); if (name) localStorage.setItem(name, JSON.stringify(watchedRegions));
  }, [watchedRegions]);

  useEffect(() => {
    const name = key(ROUTE_ALERTS_KEY); if (name) localStorage.setItem(name, JSON.stringify(routeAlertStates));
  }, [routeAlertStates]);

  useEffect(() => {
    const name = key(MILITARY_TRACKS_KEY); if (name) sessionStorage.setItem(name, JSON.stringify(militaryTrackHistory));
  }, [militaryTrackHistory]);

  useEffect(() => {
    const name = key(EVENT_HISTORY_KEY); if (name) localStorage.setItem(name, JSON.stringify(eventHistory));
  }, [eventHistory]);

  useEffect(() => {
    const name = key(EVENT_DISPOSITIONS_KEY); if (name) localStorage.setItem(name, JSON.stringify(eventDispositions));
  }, [eventDispositions]);

  useEffect(() => {
    const name = key(MEDIA_WATCH_RULES_KEY); if (name) localStorage.setItem(name, JSON.stringify(mediaWatchRules));
  }, [mediaWatchRules]);

  useEffect(() => {
    const name = key(MEDIA_TOPIC_HISTORY_KEY); if (name) localStorage.setItem(name, JSON.stringify(mediaTopicHistory));
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
    let staticSettled = false;
    let crucixSettled = false;
    let streamSettled = false;
    let streamStarted = false;
    let receivedNewData = false;
    let failed = false;
    let streamFailed = false;
    let streamSnapshot: Record<string, unknown> = {};
    const finish = () => {
      if (active && staticSettled && crucixSettled && streamSettled) {
        setRefreshRun({ nonce: refreshNonce, source: dataSource,
          status: !receivedNewData ? "error" : failed || streamFailed ? "partial" : "ready" });
      }
    };
    setStatus(Object.keys(snapshot).length ? "degraded" : "connecting");
    setError("");
    setProgress({ done: 0, total: 0 });

    const loadSnapshot = (
      request: Promise<Record<string, unknown>>,
      quiet = false,
    ) => {
      void request.then((payload) => {
        if (!active) return;
        receivedNewData ||= quiet ? hasCrucixSnapshotData(payload.crucix_intelligence) : hasWorldSnapshotData(payload);
        failed ||= payload._stale === true || sourceHealthDetails(payload).issueCount > 0;
        // Static infrastructure has its own 1/1 marker, not the live cycle's
        // completion. A late static response must not replace stream progress.
        const visiblePayload = payload._static === true
          ? Object.fromEntries(Object.entries(payload).filter(([key]) => !key.startsWith("_"))) : payload;
        setSnapshot((current) => mergeSnapshot(current, visiblePayload));
        const done = Number(payload._done);
        const total = Number(payload._total);
        if (payload._static !== true && Number.isFinite(done) && Number.isFinite(total)) setProgress({ done, total });
        if (payload._static === true && !streamStarted) setStatus("degraded");
      }).catch(() => {
        failed = true;
        if (active && !quiet) setError(Object.keys(snapshot).length
          ? "更新失败，当前为上次数据"
          : "全球情报静态数据暂时不可用");
      }).finally(() => {
        if (quiet) crucixSettled = true;
        else staticSettled = true;
        finish();
      });
    };
    loadSnapshot(dataSource.staticSnapshot());
    loadSnapshot(
      dataSource.crucixSnapshot().then((payload) => ({ crucix_intelligence: payload })),
      true,
    );

    const close = dataSource.subscribe((payload) => {
      if (!active) return;
      streamStarted = true;
      receivedNewData ||= hasWorldSnapshotData(payload);
      setSnapshot((current) => mergeSnapshot(current, payload));
      const done = Number(payload._done);
      const total = Number(payload._total);
      if (payload._stale === true) {
        // A completed OLD cycle is display evidence, not this refresh's receipt.
        streamFailed = true;
        streamSettled = false;
        if (Number.isFinite(total)) setProgress({ done: 0, total });
        return;
      }
      // Metadata-only completion must retain failures from this cycle, but not
      // pin a replaced error from the initial stale replay forever.
      streamSnapshot = mergeSnapshot(streamSnapshot, payload);
      streamFailed = sourceHealthDetails(streamSnapshot).issueCount > 0;
      if (Number.isFinite(done) && Number.isFinite(total)) setProgress({ done, total });
      streamSettled = payload._complete === true
        || (payload._complete !== false && total > 0 && done >= total);
      finish();
    }, (next) => {
      if (!active) return;
      setStatus(next);
      if (next === "degraded") {
        streamFailed = true;
        streamSettled = true;
        finish();
      }
    }, (failure) => {
      if (active) setError(failure.message);
    });

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
  const dataSettlementComplete = snapshot._stale !== true && snapshot._complete !== false
    && progress.total > 0 && progress.done >= progress.total;
  useEffect(() => {
    if (!events.length) return;
    if (progress.total > 0 && !dataSettlementComplete) return;
    const observedAt = new Date().toISOString();
    setEventHistory((current) => mergeGlobalIntelEventHistory(current, events, observedAt));
    setEventHistoryObservedAt(observedAt);
  }, [events, dataSettlementComplete, progress.total, snapshot.timestamp]);
  const eventTimeline = useMemo(() => {
    const merged = new Map<string, GlobalIntelEvent>();
    for (const event of eventHistory) merged.set(globalIntelEventIdentity(event), event);
    for (const event of events) merged.set(globalIntelEventIdentity(event), event);
    return [...merged.values()].sort((left, right) => (Date.parse(right.timestamp) || 0) - (Date.parse(left.timestamp) || 0));
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
    if (progress.total > 0 && !dataSettlementComplete) return;
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
    const name = key(EVENT_ATTENTION_BASELINE_KEY); if (name) localStorage.setItem(name, "ready");
    setAttentionBaselineReady(true);
  }, [actionableEvents, attentionBaselineReady, eventHistoryObservedAt, historyByIdentity, dataSettlementComplete, progress.total, snapshot.timestamp]);
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
    () => changeFocusedEvents.filter((event) => playbackCursor === 100 || Date.parse(eventActivityTimestamp(
      event,
      historyByIdentity.get(globalIntelEventIdentity(event)),
    )) <= playbackTime),
    [changeFocusedEvents, historyByIdentity, playbackCursor, playbackTime],
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
  const investmentResearch = useMemo(() => buildInvestmentTransmission(selectedEvent, routesWithRisk, routeImpacts, marketReactions, riskClock), [selectedEvent, routesWithRisk, routeImpacts, marketReactions, riskClock]);
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
  const crucixComparison = useMemo(() => readCrucixComparison(recordValue(snapshot.crucix_intelligence).comparison), [snapshot]);
  const hasWorldData = hasWorldSnapshotData(snapshot);
  const hasCrucixData = hasCrucixSnapshotData(snapshot.crucix_intelligence);
  const hasData = hasWorldData || hasCrucixData;
  const mediaMonitor = useMemo(() => normalizeGlobalMediaMonitor(snapshot), [snapshot]);
  const hasMediaPayload = Object.keys(recordValue(snapshot.media_monitor)).length > 0;
  const hasMediaData = mediaMonitor.status !== "unavailable"
    && (mediaMonitor.summary.analyzedItems !== null || mediaMonitor.topics.length > 0);
  const mediaStatusText = mediaMonitor.status === "unavailable" ? "舆情输入不可用"
    : mediaMonitor.status === "partial" ? "舆情证据不完整"
      : mediaMonitor.status === "stale" ? "历史舆情快照"
        : mediaMonitor.status === "ok" ? "舆情样本已分析" : "舆情覆盖待核验";
  const mediaCoverageText = mediaMonitor.coverage.expected === null ? "来源覆盖待核验"
    : `RSS 完整来源 ${mediaMetric(mediaMonitor.coverage.complete)}/${mediaMonitor.coverage.expected} · 部分 ${mediaMetric(mediaMonitor.coverage.partial)} · 陈旧 ${mediaMetric(mediaMonitor.coverage.stale)} · 失败 ${mediaMetric(mediaMonitor.coverage.failed)}`;
  const dataAvailability = hasData ? (error || health.issueCount || snapshot._stale === true ? "partial" : "available")
    : error || status === "degraded" || dataSettlementComplete ? "unavailable" : "loading";
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
  const mediaAttentionTopics = useMemo(() => [...mediaMonitor.topics].sort((left, right) => (
    (right.attentionScore ?? -1) - (left.attentionScore ?? -1)
    || (right.heatScore ?? -1) - (left.heatScore ?? -1)
    || (right.spreadScore ?? -1) - (left.spreadScore ?? -1)
  )), [mediaMonitor.topics]);
  useEffect(() => {
    if (mediaMonitor.status === "stale" || !mediaMonitor.topics.length || !mediaMonitor.timestamp) return;
    setMediaTopicHistory((current) => mergeMediaTopicHistory(
      current,
      mediaMonitor.topics,
      mediaMonitor.timestamp,
    ));
  }, [mediaMonitor.status, mediaMonitor.timestamp, mediaMonitor.topics]);
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
  const watchedMediaTopicChanges = useMemo(() => mediaMonitor.status === "stale" ? [] : watchedMediaTopics.filter((topic) => {
    return mediaWatchRules.some((rule) => mediaWatchRuleMatchesTopic(rule, topic)
      && mediaTopicComparison(mediaWatchBaseline(rule, topic), topic).changed);
  }), [mediaMonitor.status, mediaWatchRules, watchedMediaTopics]);
  const incompleteMediaTopicComparisons = mediaMonitor.status === "stale" ? watchedMediaTopics.length : watchedMediaTopics.filter((topic) => (
    mediaWatchRules.some((rule) => mediaWatchRuleMatchesTopic(rule, topic)
      && mediaTopicComparison(mediaWatchBaseline(rule, topic), topic).incomplete)
  )).length;
  useEffect(() => {
    if (mediaMonitor.status === "stale" || !mediaMonitor.topics.length || !mediaWatchRules.length) return;
    setMediaWatchRules((current) => {
      const next = current.map((rule) => {
        const topicBaselines: Record<string, string> = Object.assign(Object.create(null), rule.topicBaselines);
        let changed = false;
        for (const topic of mediaMonitor.topics.filter((item) => mediaWatchRuleMatchesTopic(rule, item))) {
          const baseline = mediaTopicComparison(mediaWatchBaseline(rule, topic), topic).baseline;
          if (topicBaselines[topic.id] !== baseline) {
            topicBaselines[topic.id] = baseline;
            changed = true;
          }
        }
        return changed ? { ...rule, topicBaselines } : rule;
      });
      return next.some((rule, index) => rule !== current[index]) ? next : current;
    });
  }, [mediaMonitor.status, mediaMonitor.topics, mediaWatchRules]);
  const selectedMediaTopicWatched = Boolean(selectedMediaTopic && mediaWatchRules.some((rule) => rule.id === selectedMediaTopic.id));
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
        timestampBasis: "observed" as const,
        timeStatus: "valid" as const,
        source: "浏览器历史",
        title: "主题核验状态发生变化",
      })),
      ...sourceTimeline,
    ].filter((step, index, items) => items.findIndex((candidate) => (
      candidate.status === step.status
      && candidate.timestamp === step.timestamp
      && candidate.source === step.source
    )) === index).sort((left, right) => {
      const leftTime = left.timeStatus === "valid" ? Date.parse(left.timestamp) : NaN;
      const rightTime = right.timeStatus === "valid" ? Date.parse(right.timestamp) : NaN;
      return (Number.isFinite(leftTime) ? leftTime : Number.MAX_SAFE_INTEGER) - (Number.isFinite(rightTime) ? rightTime : Number.MAX_SAFE_INTEGER);
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
      refresh: { nonce: refreshNonce, status: refreshRun?.nonce === refreshNonce && refreshRun.source === dataSource ? refreshRun.status : "loading" },
      streamStatus: status,
      dataAvailability: { status: dataAvailability, world: hasWorldData, media: hasMediaData,
        crucix: hasCrucixData, scope: "received-domains-only", error: error || null },
      progress,
      pointCount: hasData ? points.length : null,
      visiblePointCount: hasData ? visiblePoints.length : null,
      eventCount: hasData ? eventTimeline.length : null,
      historicalEventCount: eventHistory.length,
      actionableEventCount: hasData ? currentActionableEvents.length : null,
      observationCount: hasData ? observationEvents.length : null,
      visibleEventCount: hasData ? visibleEvents.length : null,
      eventClusterCount: hasData ? eventClusters.length : null,
      visibleEventClusterCount: hasData ? visibleEventClusters.length : null,
      eventLifecycle: hasData ? {
        new: newEventCount,
        ongoing: ongoingEventCount,
        recentlyResolved: recentlyResolvedEventCount,
        unacknowledged: unacknowledgedEventCount,
        watching: watchingEventCount,
        watchingAttention: watchingAttentionCount,
      } : null,
      highPriorityCount: hasData ? highPriorityCount : null,
      situationPreset: activePreset?.id ?? "custom",
      activeLayers: [...activeLayers],
      filters: { categoryFilter, severityFilter, timeWindow, timeBasis: "tracking-activity", query, showObservations, eventFeedMode },
      timeSemantics: {
        sourceTime: "timestamp 为来源时间；timestampBasis=published 是发布日期，updated 是来源更新时间，indexed 是来源收录时间（并非发布），occurred 是发生时间，collected 是采集时间，unknown 表示无可靠来源时间。updatedAt 单独保留来源更新时间，不能当作重新发生。",
        collection: "collectedAt 为该批源数据最近成功采集时间，不是本次尝试刷新时间。",
        futureDates: "来源时间在未来时，可能为预告或来源日期异常，须核验；不能描述成已经发生，也不计入近期风险。",
        tracking: "跟踪窗口与回放按浏览器首次收录或内容变化筛选；首次收录不等于新发生。",
        validity: "sourceFreshness=stale 时，警告未取消仅代表旧缓存状态，当前有效性待核验。",
        comparison: "crucixComparison与页面共用来源两批比较，timestamp/previous是主来源汇总批次时间，不等于每个来源的采集时间。entries的fromDate/toDate通常是观测期；kind=collection-sample、timeBasis=collected时是原采集时间（可早于汇总，RSS补充采集也可晚于汇总），不是发布或发生时间。countScope保留查询窗口、区域、订阅源、筛选与限量；样本变化不代表事件增减、总体数量或风险升降，currentEligible也仅表示本批样本可比。restored非新采集，currentEligible=false不能作当前信号。来源报告数量和方向不是风险评级；不可比较/缺口不能当作零变化或风险下降。",
      },
      mapMode,
      routes: {
        visible: activeRouteKinds.size > 0,
        count: visibleRoutes.length,
        total: routes.length,
        affected: hasData ? affectedRouteCount : null,
        marketConfirmed: hasData ? marketConfirmedRouteCount : null,
        alerts: hasData ? routeAlerts.length : null,
        highAlerts: hasData ? highRouteAlertCount : null,
        kinds: [...activeRouteKinds],
      },
      countryRisk: { visible: showCountryRisk, countries: countryRisk },
      selectedRegion: selectedRegion ?? null,
      watchedRegions: watchedRegionViews.map((region) => ({
        id: region.id,
        name: region.name,
        bounds: region.bounds,
        coveredPointCount: hasData ? region.coveredPointCount : null,
        alertCount: hasData ? region.alertCount : null,
      })),
      playback: { cursor: playbackCursor, playing: playbackPlaying, timestamp: new Date(playbackTime).toISOString() },
      selectedEvent: selectedEvent ? {
        ...selectedEvent,
        firstSeenAt: selectedHistory?.firstSeenAt ?? null,
        lastChangedAt: selectedHistory?.lastChangedAt ?? null,
      } : null,
      selectedPoint: selectedPoint ?? null,
      selectedRoute: selectedRoute ?? null,
      investmentResearch,
      crucixComparison,
      presentation: { layersOpen, mapExpanded, healthPanelOpen, mediaPanelOpen },
      sourceHealth: {
        healthy: health.healthy,
        total: health.total,
        issueCount: health.issueCount,
        cache: health.cache,
        items: health.items,
      },
      strategicBriefing: hasData ? {
        score: briefing.score ?? null,
        level: briefing.level,
        alertCount: briefing.alertCount,
        postureCoverage: briefing.postureCoverage,
        alertCoverage: briefing.alertCoverage,
        topDomains: briefing.domains.slice(0, 3),
        topThreats: briefing.threats.slice(0, 5),
        brief: briefing.brief || null,
        timestamp: briefing.timestamp || null,
      } : null,
      trendRadar: hasData ? {
        anomalyCount: trend.anomalyCount,
        trendCount: trend.trendCount,
        maxConvergence: trend.maxConvergence,
        anomalies: trend.anomalies.slice(0, 5),
        hotspots: trend.hotspots,
        focusedHotspot: mapFocus ?? null,
      } : null,
      mediaMonitor: hasMediaPayload ? {
        status: mediaMonitor.status,
        coverage: mediaMonitor.coverage,
        sampleBasis: mediaMonitor.sampleBasis,
        timestamp: mediaMonitor.timestamp || null,
        timestampBasis: "analysis-generated",
        analyzedItems: mediaMonitor.summary.analyzedItems,
        newsItems: mediaMonitor.summary.newsItems,
        socialItems: mediaMonitor.summary.socialItems,
        sourceCount: mediaMonitor.summary.sourceCount,
        languageCount: mediaMonitor.summary.languageCount,
        topicCount: mediaMonitor.summary.topicCount,
        heatVelocityPct: mediaMonitor.summary.heatVelocityPct,
        velocityState: mediaMonitor.summary.velocityState,
        currentMentions: mediaMonitor.summary.currentMentions,
        previousMentions: mediaMonitor.summary.previousMentions,
        timeCoverage: mediaMonitor.summary.timeCoverage,
        comparisonBasis: "本批样本按发布/更新时间分段；不代表全网热度增长或新发布量",
        windowHours: mediaMonitor.summary.windowHours,
        spreadScore: mediaMonitor.summary.spreadScore,
        sentiment: mediaMonitor.summary.sentiment,
        caveat: mediaMonitor.caveat,
        crossLanguageTopicCount: mediaMonitor.summary.crossLanguageTopicCount,
        flaggedTopicCount: mediaMonitor.summary.flaggedTopicCount,
        reversalTopicCount: mediaMonitor.summary.reversalTopicCount,
        divergentTopicCount: mediaMonitor.summary.divergentTopicCount,
        attentionTopicCount: mediaMonitor.summary.attentionTopicCount,
        watchRuleCount: mediaWatchRules.length,
        watchedTopicCount: hasMediaData ? watchedMediaTopics.length : null,
        watchedTopicChangeCount: hasMediaData ? watchedMediaTopicChanges.length : null,
        watchedTopicIncompleteCount: hasMediaData ? incompleteMediaTopicComparisons : null,
        topTopics: mediaAttentionTopics.slice(0, 6),
      } : null,
      lastUpdate: lastUpdate || null,
      events: visibleEvents.slice(0, 30).map((event) => {
        const history = historyByIdentity.get(globalIntelEventIdentity(event));
        return { ...event, firstSeenAt: history?.firstSeenAt ?? null, lastChangedAt: history?.lastChangedAt ?? null };
      }),
      dataContract: GLOBAL_INTELLIGENCE_CONTRACT,
      source: "world-intel-mcp",
    });
  }, [crucixComparison, incompleteMediaTopicComparisons, mediaPanelOpen, hasMediaPayload, refreshNonce, refreshRun, dataSource, dataAvailability, error, hasData, hasMediaData, hasWorldData, hasCrucixData, activeLayers, activePreset?.id, activeRouteKinds, affectedRouteCount, briefing, categoryFilter, countryRisk, currentActionableEvents.length, eventClusters.length, eventFeedMode, eventHistory.length, eventTimeline.length, healthPanelOpen, layersOpen, mapExpanded, health.cache, health.healthy, health.issueCount, health.items, health.total, historyByIdentity, highPriorityCount, highRouteAlertCount, investmentResearch, lastUpdate, mapFocus, mapMode, marketConfirmedRouteCount, mediaAttentionTopics, mediaMonitor, mediaWatchRules.length, newEventCount, observationEvents.length, ongoingEventCount, onContextChange, playbackCursor, playbackPlaying, playbackTime, points.length, progress, query, recentlyResolvedEventCount, routeAlerts.length, routes.length, selectedEvent, selectedHistory, selectedPoint, selectedRegion, selectedRoute, severityFilter, showCountryRisk, showObservations, status, timeWindow, trend, unacknowledgedEventCount, visibleEventClusters.length, visibleEvents, visiblePoints.length, visibleRoutes.length, watchedMediaTopicChanges.length, watchedMediaTopics.length, watchedRegionViews, watchingAttentionCount, watchingEventCount]);

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
      label: `${hotspot.label} · 地震样本 ${hotspot.earthquakeCount ?? "未知"}`,
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
      if (current.some((rule) => rule.id === topic.id)) {
        return current.filter((rule) => rule.id !== topic.id);
      }
      return [...current, {
        id: topic.id,
        label: topic.label,
        keywords: [...new Set((topic.keywords.length ? topic.keywords : [topic.label]).filter(Boolean))].slice(0, 6),
        createdAt: new Date().toISOString(),
        topicBaselines: mediaMonitor.status === "stale" ? {} : { [topic.id]: mediaTopicSignature(topic) },
      }];
    });
  };

  const acknowledgeMediaTopic = (topic: GlobalMediaMonitorTopic) => {
    if (mediaMonitor.status === "stale") return;
    const baselineSignature = mediaTopicSignature(topic);
    setMediaWatchRules((current) => current.map((rule) => (
      mediaWatchRuleMatchesTopic(rule, topic)
        ? { ...rule, topicBaselines: { ...rule.topicBaselines, [topic.id]: baselineSignature } } : rule
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
    <div className="intel-dashboard" data-theme={theme}>
      <section className="intel-hud" aria-label="全球情报关键指标">
        <div className="intel-risk-card" data-level={risk.rawLevel.toLocaleLowerCase()}>
          <span title="上游模型评分，不是用户持仓风险"><ShieldAlert size={14} />态势评分</span>
          <strong>{risk.score === undefined ? "—" : risk.score.toFixed(0)}</strong>
          <small>{risk.score === undefined ? "上游模型未返回评分" : risk.level}</small>
          <button
            type="button"
            onClick={() => {
              setBriefPanelOpen((value) => !value);
              setHealthPanelOpen(false);
              setTrendPanelOpen(false);
              setMediaPanelOpen(false);
            }}
            aria-expanded={briefPanelOpen}
            disabled={!hasData}
          >
            研判<Gauge size={11} />
          </button>
        </div>
        <div className="intel-priority-card" data-anomalies={trend.anomalyCount > 0 || highRouteAlertCount > 0}>
          <span><AlertTriangle size={14} />高优先级</span>
          <strong>{hasData ? highPriorityCount : "—"}</strong>
          <small>{hasData ? `${highPriorityEventCount} 个事件 · ${highRouteAlertCount} 条通道预警（已覆盖数据内）${trend.anomalyCount ? ` · ${trend.anomalyCount} 项基线偏离` : ""}` : "尚无有效情报，不能判断风险"}</small>
          <button
            type="button"
            onClick={() => {
              setTrendPanelOpen((value) => !value);
              setBriefPanelOpen(false);
              setHealthPanelOpen(false);
              setMediaPanelOpen(false);
            }}
            aria-expanded={trendPanelOpen}
            disabled={!hasData}
          >
            趋势<TrendingUp size={11} />
          </button>
        </div>
        <div className="intel-media-card" data-alert={(mediaMonitor.summary.flaggedTopicCount ?? 0) > 0}>
          <span><Sparkles size={14} />舆情雷达</span>
          <strong>{hasMediaData ? mediaMetric(mediaMonitor.summary.attentionTopicCount ?? mediaMonitor.summary.topicCount) : "—"}</strong>
          <small>
            {!hasMediaData ? hasMediaPayload ? mediaStatusText : "舆情数据未接入" : (mediaMonitor.summary.analyzedItems ?? 0) > 0
              ? `${mediaMonitor.summary.analyzedItems} 条报道 · 负面 ${mediaMetric(mediaMonitor.summary.sentiment.negativePct, "%")} · 样本对比 ${mediaVelocityLabel(mediaMonitor.summary.heatVelocityPct, mediaMonitor.summary.velocityState)}`
              : mediaMonitor.summary.analyzedItems === 0 ? "0 条报道 · 暂无情绪样本" : "样本数量待核验"}
            {hasMediaData && mediaMonitor.status !== "ok" ? ` · ${mediaStatusText}` : ""}
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
            disabled={!hasMediaPayload}
          >
            查看<Languages size={11} />
          </button>
        </div>
        <div><span><CircleDot size={14} />地图与通道</span><strong>{hasData ? visiblePoints.length : "—"}</strong><small>{hasData ? `${points.length} 个已收录点位 · ${affectedRouteCount} 条通道受影响` : "仅基础地图，动态风险数据缺失"}</small></div>
        <div className="intel-health-card" data-issues={health.issueCount > 0}>
          <span><Radio size={14} />数据与更新</span>
          <strong>{dataAvailability === "unavailable" ? "数据不可用" : health.total ? `${health.healthy}/${health.total}` : hasData && dataSettlementComplete ? "静态可用" : health.issueCount ? `${health.issueCount} 异常` : "连接中"}</strong>
          <small>{dataAvailability === "unavailable" ? "尚无有效来源，不能判断正常或安全" : `${status === "live" ? "实时" : status === "degraded" ? "降级" : "连接中"} · ${progress.total ? `${progress.done}/${progress.total}` : "静态层"} · ${lastUpdate ? relativeTime(lastUpdate) : "等待更新"}${status === "degraded" && dataSettlementComplete ? " · 已结算" : ""}${health.issueCount ? ` · ${health.issueCount} 异常` : ""}`}</small>
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
            <ComparisonPanel receipt={crucixComparison} />
            {health.items.map((item) => (
              <article key={item.id} data-status={item.status}>
                <i />
                <span><strong>{item.label}</strong><small>{item.reason}</small></span>
                <em>{item.freshness ?? "时效未知"}</em>
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
                <small>{briefing.domains.length ? `${briefing.domains.length} 个已返回评分的风险域` : "风险域数据未就绪"}</small>
              </div>
              {Object.keys(briefing.postureCoverage).length ? <p>评分覆盖 {String(briefing.postureCoverage.available ?? "未知")}/{String(briefing.postureCoverage.expected ?? "未知")} 域，完整输入 {String(briefing.postureCoverage.complete ?? "未知")} 域。缺项不合成总分；分项为样本观察，不是风险概率。</p> : null}
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
                {briefing.domains.length === 0 ? <p>未取得有效风险域评分，请查看来源状态；不能据此判定低风险。</p> : null}
              </div>
            </section>

            <section className="intel-brief-column">
              <article className="intel-situation-brief">
                <header>
                  <span><BookOpen size={12} />当前研判</span>
                  <small>{briefing.aiGenerated ? `LOCAL AI · ${briefing.model}` : "本次来源摘要"}</small>
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
                      {briefing.alertCount === null ? "数量待核验" : `C ${briefing.priorityCounts.critical ?? "—"} · H ${briefing.priorityCounts.high ?? "—"} · M ${briefing.priorityCounts.medium ?? "—"}`}
                    </small>
                  </header>
                  {Object.keys(briefing.alertCoverage).length ? <p>告警检查覆盖 {String(briefing.alertCoverage.available ?? "未知")}/{String(briefing.alertCoverage.expected ?? "未知")} 项；未覆盖部分不能判断安全。</p> : null}
                  <div>
                    {briefing.alerts.slice(0, 8).map((alert) => (
                      <section key={alert.id} data-priority={alert.priority}>
                        <i />
                        <span><strong>{alert.message}</strong><small>{alert.domainLabel}</small></span>
                      </section>
                    ))}
                    {briefing.alerts.length === 0 ? <p>{briefing.alertCount === null
                      ? "告警数据未取得，不能判断当前是否存在战略告警。"
                      : briefing.alertCount === 0 ? "本次返回的告警样本为空。" : "告警明细未返回，请核验来源。"}</p> : null}
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
            <div><small>区域地震观察值</small><strong>{trend.maxConvergence?.toFixed(1) ?? "—"}</strong><span>地震样本与静态基线，非多源风险 / 10</span></div>
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
              <header><span><Crosshair size={12} />区域地震样本</span><small>HEURISTIC / 10</small></header>
              <div>
                {trend.hotspots.map((hotspot) => (
                  <button type="button" key={hotspot.id} onClick={() => focusHotspot(hotspot)}>
                    <i style={{ "--convergence": `${Math.min(100, (hotspot.score ?? 0) * 10)}%` } as CSSProperties}><em /></i>
                    <span><strong>{hotspot.label}</strong><small>{hotspot.earthquakeCount ?? "未知"} 次地震样本 · 点击聚焦地图</small></span>
                    <b>{hotspot.score?.toFixed(1) ?? "—"}</b>
                    <LocateFixed size={12} />
                  </button>
                ))}
                {trend.hotspots.length === 0 ? <p>尚未取得区域地震样本，不能判断没有信号。</p> : null}
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
              <small>{mediaMonitor.timestamp ? `${relativeTime(mediaMonitor.timestamp)}生成分析，非新闻发布时间` : "分析时间待核验"}</small>
              <button type="button" onClick={() => setMediaPanelOpen(false)} aria-label="关闭全球舆情雷达"><X size={14} /></button>
            </div>
          </header>
          <p className="intel-media-coverage" role="status">
            {mediaStatusText} · {mediaCoverageText} · {mediaMonitor.sampleBasis === "social_sample_news_unavailable"
              ? "仅社交样本，新闻输入不可用" : "仅代表已取得样本，不代表全球舆情全量"}
          </p>
          <p className="intel-media-coverage">
            语气词典命中 {mediaMetric(mediaMonitor.summary.sentiment.assessedItems)}/{mediaMetric(mediaMonitor.summary.analyzedItems)} 条
            · 未判定 {mediaMetric(mediaMonitor.summary.sentiment.unknown)} 条；未命中不等于中性，正负比例以全部样本为分母。
          </p>
          <section className="intel-media-summary">
            <div data-tone="negative">
              <small>报道语气</small>
              <strong>{mediaMetric(mediaMonitor.summary.sentiment.negativePct, "%")}</strong>
              <span>负面 · 正面 {mediaMetric(mediaMonitor.summary.sentiment.positivePct, "%")}</span>
            </div>
            <div data-trend={mediaMonitor.summary.velocityState}>
              <small>样本时段对比</small>
              <strong>{mediaVelocityLabel(mediaMonitor.summary.heatVelocityPct, mediaMonitor.summary.velocityState)}</strong>
              <span>{mediaMetric(mediaMonitor.summary.windowHours)}h 已知样本 {mediaMetric(mediaMonitor.summary.currentMentions)} / 前段 {mediaMetric(mediaMonitor.summary.previousMentions)}</span>
            </div>
            <div>
              <small>主题聚类</small>
              <strong>{mediaMetric(mediaMonitor.summary.topicCount)}</strong>
              <span>{mediaMetric(mediaMonitor.summary.attentionTopicCount)} 个值得留意 · {mediaMetric(mediaMonitor.summary.crossLanguageTopicCount)} 个跨语言</span>
            </div>
            <div>
              <small>传播范围</small>
              <strong>{mediaMetric(mediaMonitor.summary.spreadScore)}</strong>
              <span>{mediaMetric(mediaMonitor.summary.sourceCount)} 源 · {mediaMetric(mediaMonitor.summary.languageCount)} 语种</span>
            </div>
            <div data-alert={(mediaMonitor.summary.flaggedTopicCount ?? 0) > 0}>
              <small>核验提示</small>
              <strong>{mediaMetric(mediaMonitor.summary.flaggedTopicCount)}</strong>
              <span>纠正/反转 {mediaMetric(mediaMonitor.summary.reversalTopicCount)}</span>
            </div>
            <div data-alert={watchedMediaTopics.length > 0}>
              <small>主题关注</small>
              <strong>{mediaWatchRules.length}</strong>
              <span>{!hasMediaData ? "本批命中待核验" : incompleteMediaTopicComparisons
                ? `${incompleteMediaTopicComparisons} 个主题对比不完整 · 已确认变化 ${watchedMediaTopicChanges.length}`
                : watchedMediaTopicChanges.length ? `${watchedMediaTopicChanges.length} 个主题有变化` : `本批命中 ${watchedMediaTopics.length}`}</span>
            </div>
          </section>
          <p className="intel-media-coverage">
            {mediaTimeCoverageLabel(mediaMonitor.summary.timeCoverage)}。
            优先发布，缺失才用更新；不代表新发布量或全网热度。时间不完整不判断增速。
          </p>
          <div className="intel-media-body">
            <article className="intel-media-topic-list">
              <header><span><TrendingUp size={12} />优先关注</span><small>ATTENTION / HEAT</small></header>
              <div>
                {mediaAttentionTopics.slice(0, 12).map((topic) => (
                  <div
                    key={topic.id}
                    data-verification={topic.verificationStatus !== "常规报道" && topic.verificationStatus !== "待核验"}
                    data-watching={mediaWatchRules.some((rule) => mediaWatchRuleMatchesTopic(rule, topic))}
                  >
                    <button type="button" className="intel-media-topic-main" onClick={() => openMediaTopic(topic)}>
                      <span>
                        <strong>{topic.label}</strong>
                        <small>
                          {mediaMetric(topic.sourceCount)} 源 · {topic.languageLabels.join("/") || "语种待核验"} · {topic.spreadLevel}
                        </small>
                      </span>
                      <b title={`关注度 ${mediaMetric(topic.attentionScore)} · 热度 ${mediaMetric(topic.heatScore)}`}>{mediaMetric(topic.attentionScore)}</b>
                      <em data-trend={topic.velocityState}>{mediaVelocityLabel(topic.heatVelocityPct, topic.velocityState)}</em>
                      {topic.spreadScore !== null ? <i style={{ "--media-reach": `${topic.spreadScore}%` } as CSSProperties}><u /></i> : null}
                      {topic.attentionLevel !== "常规" ? <mark data-attention={topic.attentionLevel}>{topic.attentionLevel}</mark> : null}
                      <mark data-sentiment={topic.sentiment}>{mediaSentimentLabel(topic.sentiment)}</mark>
                      {topic.verificationStatus !== "常规报道" ? <mark data-verify={topic.verificationStatus !== "待核验"}>{topic.verificationStatus}</mark> : null}
                      {topic.framingDivergence ? <mark data-divergence="true">表述分歧</mark> : null}
                      {topic.crossLanguage ? <mark data-language="true"><Languages size={9} />跨语言</mark> : null}
                      {mediaWatchRules.some((rule) => mediaWatchRuleMatchesTopic(rule, topic)) && !mediaWatchRules.some((rule) => rule.id === topic.id)
                        ? <mark>关键词命中</mark> : null}
                    </button>
                    <button type="button" className="intel-media-topic-watch" onClick={() => toggleMediaTopicWatch(topic)}>
                      <Star size={9} />{mediaWatchRules.some((rule) => rule.id === topic.id) ? "已关注" : "关注"}
                    </button>
                  </div>
                ))}
                {mediaMonitor.topics.length === 0 ? <p>{!hasMediaData ? "尚无可评估样本，不代表没有热点。" : "本批样本没有可展示主题。"}</p> : null}
              </div>
            </article>
            <article className="intel-media-frame-list">
              <header><span><Newspaper size={12} />媒体框架</span><small>TONE BY SOURCE TYPE</small></header>
              <div>
                {mediaMonitor.mediaFrames.map((frame) => {
                  const total = frame.count;
                  const sentimentOrder = frame.unknown === null ? MEDIA_SENTIMENT_ORDER : [...MEDIA_SENTIMENT_ORDER, "unknown"] as const;
                  const comparable = total !== null && total > 0
                    && sentimentOrder.every((sentiment) => frame[sentiment] !== null && frame[sentiment]! >= 0)
                    && sentimentOrder.reduce((sum, sentiment) => sum + (frame[sentiment] ?? 0), 0) === total;
                  return (
                    <section key={frame.group}>
                      <span><strong>{frame.label}</strong><small>{mediaMetric(frame.count)} 条 · 未判定 {mediaMetric(frame.unknown)} 条 · {frame.sources.slice(0, 3).join(" / ")}</small></span>
                      <b>{frame.dominantLabel}</b>
                      {comparable ? <i>
                        {sentimentOrder.map((sentiment) => (
                          <em
                            key={sentiment}
                            data-sentiment={sentiment}
                            style={{ width: `${frame[sentiment]! / total! * 100}%` }}
                            title={`${MEDIA_SENTIMENT_SHORT_LABEL[sentiment]} ${frame[sentiment]}`}
                          />
                        ))}
                      </i> : <small>{total === 0 ? "无语气样本" : "语气分布数据不完整"}</small>}
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
        <div className="intel-segments" aria-label="跟踪时间范围" title="按首次收录或内容变化筛选，不代表发布时间">
          {(["24h", "7d", "all"] as const).map((value) => (
            <button key={value} type="button" aria-pressed={timeWindow === value} onClick={() => setTimeWindow(value)}>
              {value === "24h" ? "24 小时跟踪" : value === "7d" ? "7 天跟踪" : "全部"}
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

      <div className="intel-workbench" data-layers-open={layersOpen} data-map-expanded={mapExpanded} data-detail-open={Boolean(selectedEvent || selectedPoint || selectedRoute)}>
        <aside className="intel-layer-dock" hidden={!layersOpen}>
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
            <div className="intel-map-toolbar">
              <small>{visibleRoutes.length} 条通道 · {routeAlerts.length} 条关联提示</small>
              <button type="button" aria-pressed={layersOpen} onClick={() => setLayersOpen((value) => !value)}><Layers3 size={13} />图层</button>
              <button type="button" aria-pressed={mapExpanded} onClick={() => setMapExpanded((value) => !value)}><MapIcon size={13} />{mapExpanded ? "返回事件流" : "专注地图"}</button>
            </div>
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

        <section className="intel-event-rail" hidden={mapExpanded}>
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
                        {recordKindLabel(event)} · {meta.label} · {eventTimeLabel(event)}
                        {event.sourceFreshness === "stale" ? <mark data-verify="true">旧缓存</mark> : null}
                        {cluster.events.length > 1 ? <mark>{cluster.events.length} 条证据</mark> : null}
                        <mark data-state={monitorState}>{eventMonitorLabel(monitorState)}</mark>
                        {clusterWatching ? <mark data-state={clusterNeedsAttention ? "watching-change" : "watching"}>{clusterNeedsAttention ? "关注有变化" : "关注中"}</mark> : null}
                        {mediaAnnotation ? <mark data-sentiment={mediaAnnotation.sentiment}>{mediaSentimentLabel(mediaAnnotation.sentiment)}</mark> : null}
                        {mediaAnnotation?.velocityState === "new" ? <mark data-heat="new">仅本时段有样本</mark> : null}
                        {mediaAnnotation?.heatVelocityPct !== null && mediaAnnotation && Math.abs(mediaAnnotation.heatVelocityPct) >= 20 ? <mark data-heat={mediaAnnotation.heatVelocityPct > 0 ? "up" : "down"}>样本对比 {mediaVelocityLabel(mediaAnnotation.heatVelocityPct, mediaAnnotation.velocityState)}</mark> : null}
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
                data-state={!hasData ? dataAvailability : dataSettlementComplete && eventTimeline.length === 0 ? "settled" : "filtered"}
                role="status"
              >
                <strong>
                  {!hasData ? dataAvailability === "loading" ? "正在等待有效情报数据" : "数据不可用，无法判断当前风险" : dataSettlementComplete && eventTimeline.length === 0
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
                  {!hasData ? "请检查数据源配置或连接。基础地图与战略通道是参考资料，不表示动态风险已覆盖。" : dataSettlementComplete && eventTimeline.length === 0
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
                  <div><dt>{sourceTimeFieldLabel(selectedEvent ?? selectedPoint)}</dt><dd>{absoluteTime((selectedEvent ?? selectedPoint)?.timestamp)}</dd></div>
                  {selectedEvent?.updatedAt && selectedEvent.timestampBasis !== "updated" ? <div><dt>来源更新时间</dt><dd>{absoluteTime(selectedEvent.updatedAt)}</dd></div> : null}
                  {(selectedEvent ?? selectedPoint)?.collectedAt ? <div><dt>最近成功采集</dt><dd>{absoluteTime((selectedEvent ?? selectedPoint)?.collectedAt)}</dd></div> : null}
                  <div><dt>位置</dt><dd>{selectedPoint ? `${selectedPoint.latitude.toFixed(3)}, ${selectedPoint.longitude.toFixed(3)}` : selectedEvent?.country || "未标注"}</dd></div>
                  {selectedFacts?.map((fact) => (
                    <div key={`${fact.label}-${fact.value}`}><dt>{fact.label}</dt><dd>{fact.value}</dd></div>
                  ))}
                </dl>
              )}
              {investmentResearch ? <InvestmentTransmission research={investmentResearch} /> : null}
              {selectedEvent ? (
                <section className="intel-record-explanation" data-kind={selectedEvent.recordKind ?? "event"}>
                  <h3>{recordKindLabel(selectedEvent)}是什么意思</h3>
                  <p>{recordKindExplanation(selectedEvent)}</p>
                </section>
              ) : null}
              {selectedEvent?.recordKind === "news" && selectedMediaAnnotation ? (
                <section className="intel-media-dossier" data-verification={selectedMediaAnnotation.verificationStatus !== "常规报道" && selectedMediaAnnotation.verificationStatus !== "待核验"}>
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
                    <div><dt>样本时段对比</dt><dd>{mediaVelocityLabel(selectedMediaAnnotation.heatVelocityPct, selectedMediaAnnotation.velocityState)}</dd></div>
                    <div><dt>传播范围</dt><dd>{mediaMetric(selectedMediaAnnotation.spreadScore, "/100")}</dd></div>
                    <div><dt>跨语言合并</dt><dd>{selectedMediaAnnotation.crossLanguageTopic === null ? "待核验" : selectedMediaAnnotation.crossLanguageTopic ? "已合并" : "未合并"}</dd></div>
                  </dl>
                  {selectedMediaTopic ? (
                    <>
                      <h3>{selectedMediaTopic.label}</h3>
                      <p>{mediaTimeCoverageLabel(selectedMediaTopic.timeCoverage)}。更新不等于新发布；缺日期与未来日期不参与时段计数。</p>
                      <p>
                        {mediaMetric(selectedMediaTopic.mentionCount)} 条相关记录，来自 {mediaMetric(selectedMediaTopic.sourceCount)} 个来源、
                        {selectedMediaTopic.languageLabels.join("、") || "语种待核验"}；传播级别为{selectedMediaTopic.spreadLevel}，
                        关注度 {mediaMetric(selectedMediaTopic.attentionScore, "/100")}（{selectedMediaTopic.attentionLevel}）。
                        其中语气未判定 {mediaMetric(selectedMediaTopic.sentimentCounts.unknown)} 条。
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
                                <span><strong>{item.source}</strong><small>{item.timestampBasis === "updated" ? "更新" : item.timestampBasis === "published" ? "发布" : "来源时间"} · {item.timeStatus === "future" ? "未来日期，未计入" : item.timestamp ? relativeTime(item.timestamp) : "时间未知"} · {mediaSentimentLabel(item.sentiment)}</small></span>
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
                      {watchedMediaTopicChanges.some((topic) => topic.id === selectedMediaTopic.id) ? (
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
                                <time>{step.timestampBasis === "updated" ? "更新" : step.timestampBasis === "published" ? "发布" : step.timestampBasis === "observed" ? "浏览器记录" : "来源时间"} · {step.timeStatus === "future" ? "未来日期，未计入" : step.timestamp ? new Date(step.timestamp).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }) : "时间未知"}</time>
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
                              <span><strong>{topic.label}</strong><small>{new Date(topic.lastSeenAt).toLocaleDateString("zh-CN")} · 历史已知 {mediaMetric(topic.sourceCount)} 源</small></span>
                              <b>{similarity}%</b>
                            </button>
                          ))}
                        </div>
                      ) : null}
                    </>
                  ) : null}
                  <small>核验提示只识别报道中的“据称、否认、更正、反转”等显式措辞，不直接判断真假。日期为报道发布或更新时间，不代表事件发生时间；未知或未来日期列于末尾。</small>
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
                          <time>{eventTimeLabel(evidence)} · {absoluteTime(evidence.timestamp)}</time>
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
