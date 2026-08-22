import type { GatewayFetch } from "@newma-desk/mod-sdk";

export const GLOBAL_INTELLIGENCE_CONTRACT = "newma-desk.global-intelligence.v1";

export type GlobalIntelCategory =
  | "market"
  | "news"
  | "policy"
  | "conflict"
  | "disaster"
  | "military"
  | "infrastructure"
  | "maritime"
  | "climate"
  | "health"
  | "cyber"
  | "nuclear"
  | "aviation"
  | "space"
  | "technology"
  | "society"
  | "prediction";

export type GlobalIntelSeverity = "critical" | "high" | "medium" | "low" | "info";
export type GlobalIntelRecordKind = "observation" | "event" | "news";

export interface GlobalIntelPoint {
  id: string;
  category: GlobalIntelCategory;
  latitude: number;
  longitude: number;
  title: string;
  detail: string;
  source: string;
  severity: GlobalIntelSeverity;
  country?: string;
  countryCode?: string;
  timestamp?: string;
  url?: string;
  facts?: Array<{ label: string; value: string }>;
  content?: string;
}

export interface GlobalIntelAircraftTrackSample {
  aircraftId: string;
  callsign: string;
  latitude: number;
  longitude: number;
  altitude?: number;
  heading?: number;
  observedAt: string;
}

export type GlobalIntelMilitaryTrackHistory = Record<string, GlobalIntelAircraftTrackSample[]>;

export interface GlobalIntelRouteExposure {
  countries: readonly string[];
  commodities: readonly string[];
  industries: readonly string[];
  marketSignals: readonly string[];
}

export interface GlobalIntelRoute {
  id: string;
  kind: "pipeline" | "cable" | "flight" | "shipping";
  name: string;
  detail: string;
  path: Array<[number, number]>;
  keywords?: string[];
  exposure?: GlobalIntelRouteExposure;
  pathType?: "exact" | "corridor";
  status?: string;
  riskScore?: number;
  impactCount?: number;
}

export interface GlobalIntelRouteImpact {
  routeId: string;
  eventId: string;
  distanceKm?: number;
  matchedKeyword?: string;
  relation: "direct" | "nearby" | "mentioned";
  reasons: string[];
  riskScore: number;
  confidence: number;
  sourceCount: number;
  evidenceCount: number;
  ageHours: number;
}

export interface GlobalIntelMarketReaction {
  routeId: string;
  kind: "commodity" | "shipping";
  label: string;
  symbol?: string;
  value: number;
  unit: "%" | "score";
  status: "confirmed" | "watch" | "diverging" | "quiet";
  strength: number;
  timestamp: string;
  reason: string;
}

export interface GlobalIntelRouteAlert {
  id: string;
  routeId: string;
  level: "critical" | "high" | "watch";
  score: number;
  title: string;
  summary: string;
  reasons: string[];
  confidence: number;
  marketConfirmed: boolean;
}

export type GlobalIntelRouteAlertDisposition = "new" | "acknowledged" | "muted";
export type GlobalIntelRouteAlertChange = "new" | "stable" | "escalated" | "downgraded" | "resolved";

export interface GlobalIntelRouteAlertState {
  alertId: string;
  routeId: string;
  title: string;
  lastLevel: GlobalIntelRouteAlert["level"];
  disposition: GlobalIntelRouteAlertDisposition;
  change: GlobalIntelRouteAlertChange;
  active: boolean;
  updatedAt: string;
}

const SHIPPING_CORRIDORS = [
  {
    name: "欧亚主航线",
    detail: "集装箱与综合货运 · 欧洲—中东—东亚",
    exposure: {
      countries: ["欧洲", "中东", "东亚"],
      commodities: ["集装箱货物", "原油", "LNG"],
      industries: ["航运", "港口", "制造业供应链"],
      marketSignals: ["集运运价", "航运保险成本", "交付周期"],
    },
    stops: [
      "Strait of Gibraltar",
      "Suez Canal",
      "Bab el-Mandeb",
      "Strait of Malacca",
      "Strait of Luzon",
      "Taiwan Strait",
      "Korea Strait",
    ],
  },
  {
    name: "海湾—东亚能源航线",
    detail: "能源综合运输 · 海湾—印度洋—东亚",
    exposure: {
      countries: ["海湾出口国", "中国", "日本", "韩国"],
      commodities: ["原油", "LNG", "成品油"],
      industries: ["油轮航运", "炼化", "航空", "化工"],
      marketSignals: ["原油价格", "LNG现货价格", "油轮运价", "航运保险成本"],
    },
    stops: [
      "Strait of Hormuz",
      "Bab el-Mandeb",
      "Strait of Malacca",
      "Taiwan Strait",
      "Korea Strait",
    ],
  },
  {
    name: "好望角绕行线",
    detail: "集装箱、原油与散货 · 苏伊士替代走廊",
    exposure: {
      countries: ["欧洲", "非洲南部", "东亚"],
      commodities: ["集装箱货物", "原油", "散货"],
      industries: ["远洋航运", "港口", "零售供应链"],
      marketSignals: ["绕行天数", "燃油成本", "集运运价"],
    },
    stops: [
      "Strait of Gibraltar",
      "Cape of Good Hope",
      "Mozambique Channel",
      "Lombok Strait",
      "Strait of Luzon",
    ],
  },
  {
    name: "北极航运走廊",
    detail: "季节性能源与散货 · 北欧—俄罗斯—东北亚",
    exposure: {
      countries: ["北欧", "俄罗斯", "东北亚"],
      commodities: ["LNG", "能源设备", "散货"],
      industries: ["冰区航运", "能源", "保险"],
      marketSignals: ["航季可用性", "冰区保险成本", "运输周期"],
    },
    stops: ["Danish Straits", "Northern Sea Route", "Korea Strait"],
  },
  {
    name: "海湾—东亚原油油运线",
    detail: "原油 · 主要油轮通道 · 霍尔木兹至东亚炼厂",
    exposure: {
      countries: ["海湾出口国", "印度", "中国", "日本", "韩国"],
      commodities: ["原油"],
      industries: ["油轮航运", "炼化", "航空", "化工"],
      marketSignals: ["布伦特原油", "油轮运价", "航运保险成本"],
    },
    stops: ["Strait of Hormuz", "Mumbai", "Strait of Malacca", "Ningbo", "Korea Strait"],
  },
  {
    name: "西非—东亚油运线",
    detail: "原油 · 好望角绕行 · 西非至东亚",
    exposure: {
      countries: ["西非产油国", "南非", "中国", "日本"],
      commodities: ["原油"],
      industries: ["油轮航运", "炼化", "港口"],
      marketSignals: ["西非原油价差", "油轮运价", "运输周期"],
    },
    stops: ["Bonny", "Cape of Good Hope", "Lombok Strait", "Ningbo"],
  },
  {
    name: "红海—欧洲成品油线",
    detail: "成品油 · 红海—苏伊士—地中海供应链",
    exposure: {
      countries: ["海湾出口国", "埃及", "欧洲"],
      commodities: ["成品油"],
      industries: ["油轮航运", "炼化", "港口"],
      marketSignals: ["成品油裂解价差", "苏伊士通行量", "航运保险成本"],
    },
    stops: ["Bab el-Mandeb", "Suez Canal", "Strait of Gibraltar", "Rotterdam"],
  },
  {
    name: "俄罗斯远东能源线",
    detail: "原油 · 俄罗斯远东至东北亚",
    exposure: {
      countries: ["俄罗斯", "中国", "日本", "韩国"],
      commodities: ["原油", "成品油"],
      industries: ["油轮航运", "炼化", "港口"],
      marketSignals: ["乌拉尔原油价差", "东北亚炼厂利润", "油轮运价"],
    },
    stops: ["Kozmino", "Korea Strait", "Yokohama", "Qingdao"],
  },
] as const;

const ROUTE_NODE_COORDINATES: Record<string, [number, number]> = {
  "Strait of Gibraltar": [-5.6, 35.97],
  "Suez Canal": [32.27, 30.58],
  "Bab el-Mandeb": [43.33, 12.58],
  "Strait of Hormuz": [56.25, 26.57],
  "Strait of Malacca": [103.5, 1.5],
  "Strait of Luzon": [121, 20],
  "Taiwan Strait": [118.5, 24],
  "Korea Strait": [129.5, 34],
  "Cape of Good Hope": [18.47, -34.36],
  "Mozambique Channel": [43.5, -18],
  "Lombok Strait": [115.7, -8.5],
  "Danish Straits": [12, 56],
  "Northern Sea Route": [105, 75],
  Mumbai: [72.88, 19.08],
  Ningbo: [121.55, 29.87],
  Bonny: [7.16, 4.45],
  Rotterdam: [4.14, 51.95],
  Kozmino: [133, 42.7],
  Yokohama: [139.6, 35.45],
  Qingdao: [120.3, 36.1],
};

const ROUTE_NODE_ALIASES: Record<string, string[]> = {
  "Strait of Gibraltar": ["直布罗陀海峡"],
  "Suez Canal": ["苏伊士运河"],
  "Bab el-Mandeb": ["曼德海峡", "曼德布海峡"],
  "Strait of Hormuz": ["霍尔木兹", "霍尔木兹海峡"],
  "Strait of Malacca": ["马六甲", "马六甲海峡"],
  "Strait of Luzon": ["吕宋海峡"],
  "Taiwan Strait": ["台湾海峡"],
  "Korea Strait": ["朝鲜海峡", "韩国海峡"],
  "Cape of Good Hope": ["好望角"],
  "Mozambique Channel": ["莫桑比克海峡"],
  "Lombok Strait": ["龙目海峡"],
};

const FLIGHT_EXPOSURE: GlobalIntelRouteExposure = {
  countries: ["北美", "欧洲", "中东", "东亚", "大洋洲"],
  commodities: ["航空货运", "高附加值商品", "旅客流量"],
  industries: ["航空公司", "机场", "物流", "旅游"],
  marketSignals: ["航班量", "航空货运价格", "航油价格", "机场吞吐量"],
};

const FLIGHT_CORRIDORS = [
  {
    name: "北大西洋航空走廊",
    detail: "代表性客运与货运走廊 · 北美—欧洲",
    path: [[-73.78, 40.64], [-0.45, 51.47], [8.57, 50.03]] as Array<[number, number]>,
  },
  {
    name: "欧洲—海湾—亚洲航空走廊",
    detail: "代表性客运与货运走廊 · 欧洲—中东—东亚",
    path: [[-0.45, 51.47], [55.36, 25.25], [103.99, 1.36], [113.92, 22.31]] as Array<[number, number]>,
  },
  {
    name: "跨太平洋航空走廊",
    detail: "代表性客运与货运走廊 · 北美—东北亚",
    path: [[-118.4, 33.94], [139.78, 35.55], [126.44, 37.46], [121.8, 31.14]] as Array<[number, number]>,
  },
  {
    name: "东亚—澳洲航空走廊",
    detail: "代表性客运与货运走廊 · 东亚—东南亚—澳洲",
    path: [[139.78, 35.55], [103.99, 1.36], [151.18, -33.94]] as Array<[number, number]>,
  },
] as const;

const PIPELINE_EXPOSURE: GlobalIntelRouteExposure = {
  countries: ["沿线供给国", "沿线消费国"],
  commodities: ["原油", "天然气", "成品油"],
  industries: ["能源开采", "炼化", "公用事业", "化工"],
  marketSignals: ["能源价格", "区域价差", "库存与供应预期"],
};

const CABLE_EXPOSURE: GlobalIntelRouteExposure = {
  countries: ["沿线国家与登陆站"],
  commodities: ["国际数据传输能力"],
  industries: ["电信", "云服务", "金融交易", "跨境互联网"],
  marketSignals: ["网络时延", "跨境带宽", "云服务可用性"],
};

export interface GlobalIntelEvent {
  id: string;
  category: GlobalIntelCategory;
  title: string;
  detail: string;
  source: string;
  severity: GlobalIntelSeverity;
  timestamp: string;
  url?: string;
  country?: string;
  countryCode?: string;
  pointId?: string;
  sourceTier?: string;
  recordKind?: GlobalIntelRecordKind;
  facts?: Array<{ label: string; value: string }>;
  content?: string;
}

export interface GlobalIntelEventHistoryEntry extends GlobalIntelEvent {
  firstSeenAt: string;
  lastSeenAt: string;
  lastChangedAt: string;
  observationCount: number;
  resolvedAt?: string;
}

export interface GlobalIntelEventCluster {
  id: string;
  primary: GlobalIntelEvent;
  events: GlobalIntelEvent[];
  sources: string[];
  confidence: number;
  startedAt: string;
  updatedAt: string;
}

export type GlobalMediaSentiment = "positive" | "negative" | "neutral" | "mixed";

export interface GlobalMediaMonitorFrame {
  group: string;
  label: string;
  count: number;
  positive: number;
  negative: number;
  neutral: number;
  mixed: number;
  dominantSentiment: GlobalMediaSentiment;
  dominantLabel: string;
  sources: string[];
}

export interface GlobalMediaMonitorTopic {
  id: string;
  label: string;
  headline: string;
  mentionCount: number;
  currentMentions: number;
  previousMentions: number;
  heatVelocityPct: number | null;
  velocityState: "rising" | "falling" | "flat" | "new";
  heatScore: number;
  attentionScore: number;
  attentionLevel: string;
  spreadScore: number;
  spreadLevel: string;
  sourceCount: number;
  sources: string[];
  sourceTiers: string[];
  languageCount: number;
  languages: string[];
  languageLabels: string[];
  crossLanguage: boolean;
  sentiment: GlobalMediaSentiment;
  sentimentScore: number;
  sentimentCounts: Record<GlobalMediaSentiment, number>;
  mediaFrames: GlobalMediaMonitorFrame[];
  framingDivergence: boolean;
  framingDivergenceScore: number;
  verificationStatus: string;
  verificationFlags: string[];
  verificationTimeline: GlobalMediaVerificationStep[];
  socialEngagement: number;
  latestAt: string;
  keywords: string[];
  items: GlobalMediaMonitorTopicItem[];
}

export interface GlobalMediaMonitorTopicItem {
  key: string;
  title: string;
  source: string;
  url: string;
  language: string;
  sentiment: GlobalMediaSentiment;
  published: string;
  kind: "news" | "social";
}

export interface GlobalMediaVerificationStep {
  status: string;
  flag: string;
  timestamp: string;
  source: string;
  title: string;
  url: string;
}

export interface GlobalMediaMonitorAnnotation {
  key: string;
  title: string;
  source: string;
  url: string;
  topicId: string;
  sentiment: GlobalMediaSentiment;
  sentimentScore: number;
  language: string;
  verificationStatus: string;
  verificationFlags: string[];
  heatVelocityPct: number | null;
  velocityState: GlobalMediaMonitorTopic["velocityState"];
  spreadScore: number;
  crossLanguageTopic: boolean;
}

export interface GlobalMediaMonitor {
  summary: {
    analyzedItems: number;
    newsItems: number;
    socialItems: number;
    sourceCount: number;
    languageCount: number;
    topicCount: number;
    currentMentions: number;
    previousMentions: number;
    heatVelocityPct: number | null;
    velocityState: "rising" | "falling" | "flat" | "new";
    windowHours: number;
    crossLanguageTopicCount: number;
    flaggedTopicCount: number;
    disputedTopicCount: number;
    reversalTopicCount: number;
    divergentTopicCount: number;
    attentionTopicCount: number;
    spreadScore: number;
    sentiment: {
      positive: number;
      negative: number;
      neutral: number;
      mixed: number;
      positivePct: number;
      negativePct: number;
      neutralPct: number;
      mixedPct: number;
      netScore: number;
    };
  };
  topics: GlobalMediaMonitorTopic[];
  mediaFrames: GlobalMediaMonitorFrame[];
  annotations: GlobalMediaMonitorAnnotation[];
  caveat: string;
  timestamp: string;
}

export function isActionableGlobalIntelEvent(event: GlobalIntelEvent) {
  return event.recordKind !== "observation";
}

export function globalIntelEventIdentity(event: GlobalIntelEvent) {
  const subject = normalizedEntityText(event.title)
    .split(/\s+/)
    .filter((token) => !/^\d+(?:\.\d+)?$/.test(token))
    .join(" ");
  const identity = event.recordKind === "news"
    ? [event.recordKind, event.category, event.source, event.title, event.url]
    : [event.recordKind ?? "event", event.category, event.source, subject, event.countryCode, event.pointId];
  return normalizedEntityText(identity.filter(Boolean).join(" | "));
}

function globalIntelEventRevision(event: GlobalIntelEvent) {
  return normalizedEntityText([
    event.title,
    event.detail,
    event.severity,
    event.country,
    event.content,
  ].filter(Boolean).join(" | "));
}

export function mergeGlobalIntelEventHistory(
  history: GlobalIntelEventHistoryEntry[],
  currentEvents: GlobalIntelEvent[],
  observedAt = new Date().toISOString(),
  maxEntries = 320,
): GlobalIntelEventHistoryEntry[] {
  const observedMs = Date.parse(observedAt);
  const normalizedObservedAt = Number.isFinite(observedMs) ? observedAt : new Date().toISOString();
  const cutoff = Date.parse(normalizedObservedAt) - 7 * 24 * 60 * 60 * 1000;
  const entries = new Map<string, GlobalIntelEventHistoryEntry>();
  const previousByIdentity = new Map<string, GlobalIntelEventHistoryEntry>();

  for (const event of history) {
    if (!isActionableGlobalIntelEvent(event)) continue;
    const lastSeenAt = event.lastSeenAt || event.timestamp;
    if (Date.parse(lastSeenAt) < cutoff) continue;
    const fingerprint = globalIntelEventIdentity(event);
    if (fingerprint) {
      previousByIdentity.set(fingerprint, event);
      entries.set(fingerprint, event);
    }
  }

  const currentIdentities = new Set(
    currentEvents.filter(isActionableGlobalIntelEvent).map(globalIntelEventIdentity),
  );
  for (const [fingerprint, previous] of previousByIdentity) {
    if (currentIdentities.has(fingerprint) || previous.resolvedAt) continue;
    entries.set(fingerprint, {
      ...previous,
      lastChangedAt: normalizedObservedAt,
      resolvedAt: normalizedObservedAt,
    });
  }

  for (const event of currentEvents.filter(isActionableGlobalIntelEvent)) {
    const fingerprint = globalIntelEventIdentity(event);
    if (!fingerprint) continue;
    const previous = previousByIdentity.get(fingerprint);
    const compactEvent = {
      ...event,
      detail: event.detail.slice(0, 600),
      ...(event.content ? { content: event.content.slice(0, 1200) } : {}),
    };
    entries.set(fingerprint, {
      ...compactEvent,
      firstSeenAt: previous?.firstSeenAt || normalizedObservedAt,
      lastSeenAt: normalizedObservedAt,
      lastChangedAt: !previous
        || Boolean(previous.resolvedAt)
        || globalIntelEventRevision(previous) !== globalIntelEventRevision(compactEvent)
        ? normalizedObservedAt
        : previous.lastChangedAt || previous.firstSeenAt || normalizedObservedAt,
      observationCount: previous && Date.parse(normalizedObservedAt) - Date.parse(previous.lastSeenAt) < 60_000
        ? previous.observationCount
        : (previous?.observationCount ?? 0) + 1,
    });
  }

  return [...entries.values()]
    .sort((left, right) => (
      Date.parse(right.timestamp) - Date.parse(left.timestamp)
      || Date.parse(right.lastSeenAt) - Date.parse(left.lastSeenAt)
    ))
    .slice(0, maxEntries);
}

const ROUTE_RELEVANT_CATEGORIES: Record<GlobalIntelRoute["kind"], Set<GlobalIntelCategory>> = {
  pipeline: new Set(["conflict", "disaster", "infrastructure", "climate"]),
  cable: new Set(["disaster", "infrastructure", "maritime"]),
  shipping: new Set(["conflict", "maritime", "disaster", "climate", "military"]),
  flight: new Set(["aviation", "conflict", "military", "disaster", "climate"]),
};

const ROUTE_DISTANCE_LIMIT_KM: Record<GlobalIntelRoute["kind"], number> = {
  pipeline: 150,
  cable: 180,
  shipping: 250,
  flight: 120,
};

const ROUTE_SEVERITY_SCORE: Record<GlobalIntelSeverity, number> = {
  critical: 92,
  high: 76,
  medium: 56,
  low: 34,
  info: 16,
};

const ROUTE_MENTION_SCORE: Record<GlobalIntelSeverity, number> = {
  critical: 58,
  high: 52,
  medium: 38,
  low: 28,
  info: 24,
};

function wrappedLongitudeDistance(left: number, right: number) {
  return ((left - right + 540) % 360) - 180;
}

function pointSegmentDistanceKm(
  point: [number, number],
  start: [number, number],
  end: [number, number],
) {
  const referenceLatitude = (point[1] + start[1] + end[1]) / 3 * Math.PI / 180;
  const longitudeScale = 111.32 * Math.cos(referenceLatitude);
  const latitudeScale = 110.57;
  const pointX = wrappedLongitudeDistance(point[0], start[0]) * longitudeScale;
  const pointY = (point[1] - start[1]) * latitudeScale;
  const segmentX = wrappedLongitudeDistance(end[0], start[0]) * longitudeScale;
  const segmentY = (end[1] - start[1]) * latitudeScale;
  const segmentLengthSquared = segmentX ** 2 + segmentY ** 2;
  const progress = segmentLengthSquared
    ? Math.max(0, Math.min(1, (pointX * segmentX + pointY * segmentY) / segmentLengthSquared))
    : 0;
  return Math.hypot(pointX - segmentX * progress, pointY - segmentY * progress);
}

function pointRouteDistanceKm(point: GlobalIntelPoint, route: GlobalIntelRoute) {
  if (route.path.length < 2) return Number.POSITIVE_INFINITY;
  return Math.min(...route.path.slice(0, -1).map((start, index) => (
    pointSegmentDistanceKm(
      [point.longitude, point.latitude],
      start,
      route.path[index + 1]!,
    )
  )));
}

function normalizedEntityText(value: string) {
  return value.toLocaleLowerCase()
    .replace(/[_—–-]+/g, " ")
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function routeEntityAliases(route: GlobalIntelRoute) {
  const aliases = new Set<string>();
  for (const rawKeyword of route.keywords ?? [route.name, route.detail]) {
    const keyword = normalizedEntityText(rawKeyword);
    if (keyword.length >= 4) aliases.add(keyword);
    const shortened = keyword
      .replace(/^(?:strait of|cape of)\s+/, "")
      .replace(/\s+(?:canal|channel)$/, "")
      .trim();
    if (shortened.length >= 4 && shortened !== keyword) aliases.add(shortened);
  }
  return [...aliases].sort((left, right) => right.length - left.length);
}

function eventFreshness(event: GlobalIntelEvent, now: number) {
  const timestamp = Date.parse(event.timestamp);
  const ageHours = Number.isFinite(timestamp) ? Math.max(0, (now - timestamp) / 3_600_000) : 0;
  if (ageHours > 72) return { ageHours, multiplier: 0, label: "超过 72 小时" };
  if (ageHours > 24) {
    return {
      ageHours,
      multiplier: 0.7 - (ageHours - 24) / 48 * 0.45,
      label: "超过 24 小时，风险衰减",
    };
  }
  if (ageHours > 6) {
    return {
      ageHours,
      multiplier: 1 - (ageHours - 6) / 18 * 0.3,
      label: "24 小时内更新",
    };
  }
  return { ageHours, multiplier: 1, label: "6 小时内更新" };
}

export function calculateGlobalIntelRouteImpacts(
  events: GlobalIntelEvent[],
  points: GlobalIntelPoint[],
  routes: GlobalIntelRoute[],
  now = Date.now(),
): GlobalIntelRouteImpact[] {
  const pointById = new Map(points.map((point) => [point.id, point]));
  const impacts: GlobalIntelRouteImpact[] = [];
  const impactKeys = new Set<string>();
  for (const event of events.filter(isActionableGlobalIntelEvent)) {
    const freshness = eventFreshness(event, now);
    if (!freshness.multiplier) continue;
    const point = event.pointId ? pointById.get(event.pointId) : undefined;
    if (!point) continue;
    for (const route of routes) {
      if (!ROUTE_RELEVANT_CATEGORIES[route.kind].has(event.category)) continue;
      const distanceKm = pointRouteDistanceKm(point, route);
      const limitKm = ROUTE_DISTANCE_LIMIT_KM[route.kind];
      if (!Number.isFinite(distanceKm) || distanceKm > limitKm) continue;
      const relation = distanceKm <= limitKm * 0.3 ? "direct" : "nearby";
      const riskScore = Math.max(1, Math.round((
        ROUTE_SEVERITY_SCORE[event.severity] - distanceKm / limitKm * 30
      ) * freshness.multiplier
      ));
      impacts.push({
        routeId: route.id,
        eventId: event.id,
        distanceKm: Math.round(distanceKm),
        relation,
        reasons: [
          `${event.severity} 级${event.category}信号`,
          `距通道约 ${Math.round(distanceKm)} km`,
          freshness.label,
        ],
        riskScore,
        confidence: 42,
        sourceCount: 1,
        evidenceCount: 1,
        ageHours: Math.round(freshness.ageHours),
      });
      impactKeys.add(`${route.id}:${event.id}`);
    }
  }
  for (const event of events.filter((item) => item.recordKind === "news")) {
    const freshness = eventFreshness(event, now);
    if (!freshness.multiplier) continue;
    const text = normalizedEntityText(`${event.title} ${event.detail}`);
    if (!text) continue;
    for (const route of routes) {
      const impactKey = `${route.id}:${event.id}`;
      if (impactKeys.has(impactKey)) continue;
      const matchedKeyword = routeEntityAliases(route).find((keyword) => text.includes(keyword));
      if (!matchedKeyword) continue;
      impacts.push({
        routeId: route.id,
        eventId: event.id,
        matchedKeyword,
        relation: "mentioned",
        reasons: [
          `新闻文本提及「${matchedKeyword}」`,
          "尚未通过事件坐标确认",
          freshness.label,
        ],
        riskScore: Math.max(1, Math.round(ROUTE_MENTION_SCORE[event.severity] * freshness.multiplier)),
        confidence: 42,
        sourceCount: 1,
        evidenceCount: 1,
        ageHours: Math.round(freshness.ageHours),
      });
      impactKeys.add(impactKey);
    }
  }
  const eventById = new Map(events.map((event) => [event.id, event]));
  const clusterIdByEvent = new Map<string, string>();
  for (const cluster of clusterGlobalIntelEvents(events.filter(isActionableGlobalIntelEvent))) {
    for (const event of cluster.events) clusterIdByEvent.set(event.id, cluster.id);
  }
  const impactGroups = new Map<string, GlobalIntelRouteImpact[]>();
  for (const impact of impacts) {
    const groupKey = `${impact.routeId}:${clusterIdByEvent.get(impact.eventId) ?? impact.eventId}`;
    impactGroups.set(groupKey, [...(impactGroups.get(groupKey) ?? []), impact]);
  }
  const enrichedImpacts = [...impactGroups.values()].flatMap((group) => {
    const sources = new Set(group.map((impact) => eventById.get(impact.eventId)?.source).filter(Boolean));
    const sourceCount = sources.size || 1;
    const evidenceCount = group.length;
    const confidence = sourceCount === 1
      ? Math.min(55, 42 + (evidenceCount - 1) * 3)
      : Math.min(96, 35 + sourceCount * 18 + (evidenceCount - 1) * 3);
    const evidenceBoost = Math.min(18, (sourceCount - 1) * 9 + (evidenceCount - sourceCount) * 2);
    return group.map((impact) => ({
      ...impact,
      riskScore: Math.min(96, impact.riskScore + evidenceBoost),
      confidence,
      sourceCount,
      evidenceCount,
      reasons: sourceCount > 1
        ? [...impact.reasons, `${sourceCount} 个独立来源交叉验证`]
        : impact.reasons,
    }));
  });
  return enrichedImpacts.sort((left, right) => (
    right.riskScore - left.riskScore
    || (left.distanceKm ?? Number.POSITIVE_INFINITY) - (right.distanceKm ?? Number.POSITIVE_INFINITY)
  ));
}

const CLUSTER_STOPWORDS = new Set([
  "about", "after", "amid", "from", "into", "latest", "more", "over", "says",
  "that", "the", "their", "this", "through", "update", "with", "world", "navarea",
  "事件", "全球", "最新", "相关", "表示", "发生", "正在", "以及",
]);
const EVENT_SEVERITY_RANK: Record<GlobalIntelSeverity, number> = {
  critical: 5,
  high: 4,
  medium: 3,
  low: 2,
  info: 1,
};

function eventTokens(title: string) {
  const words = title.toLocaleLowerCase().match(/[\p{L}\p{N}]+/gu) ?? [];
  const tokens = new Set(words.filter((word) => (
    word.length >= 3
    && !/^\d+$/.test(word)
    && !CLUSTER_STOPWORDS.has(word)
  )));
  for (const run of title.match(/[\p{Script=Han}]{3,}/gu) ?? []) {
    for (let index = 0; index < run.length - 1; index += 1) tokens.add(run.slice(index, index + 2));
  }
  return tokens;
}

function eventSimilarity(left: GlobalIntelEvent, right: GlobalIntelEvent) {
  if (left.category !== right.category) return false;
  if (Math.abs(Date.parse(left.timestamp) - Date.parse(right.timestamp)) > 18 * 60 * 60 * 1000) return false;
  const leftTokens = eventTokens(left.title);
  const rightTokens = eventTokens(right.title);
  const common = [...leftTokens].filter((token) => rightTokens.has(token)).length;
  const overlap = common / Math.max(1, Math.min(leftTokens.size, rightTokens.size));
  const sameCountry = Boolean(left.countryCode && left.countryCode === right.countryCode);
  return common >= 3 || (common >= 2 && overlap >= 0.4) || (sameCountry && common >= 1 && overlap >= 0.34);
}

export function clusterGlobalIntelEvents(events: GlobalIntelEvent[]): GlobalIntelEventCluster[] {
  const clusters: GlobalIntelEventCluster[] = [];
  for (const event of events) {
    const cluster = clusters.find((candidate) => candidate.events.some((item) => eventSimilarity(item, event)));
    if (!cluster) {
      clusters.push({
        id: `cluster-${event.id}`,
        primary: event,
        events: [event],
        sources: [event.source],
        confidence: 42,
        startedAt: event.timestamp,
        updatedAt: event.timestamp,
      });
      continue;
    }
    cluster.events.push(event);
    cluster.sources = [...new Set(cluster.events.map((item) => item.source))];
    cluster.startedAt = cluster.events.reduce(
      (earliest, item) => Date.parse(item.timestamp) < Date.parse(earliest) ? item.timestamp : earliest,
      cluster.startedAt,
    );
    cluster.updatedAt = cluster.events.reduce(
      (latest, item) => Date.parse(item.timestamp) > Date.parse(latest) ? item.timestamp : latest,
      cluster.updatedAt,
    );
    cluster.primary = cluster.events.reduce((primary, item) => (
      EVENT_SEVERITY_RANK[item.severity] > EVENT_SEVERITY_RANK[primary.severity]
        ? item
        : primary
    ), cluster.primary);
    cluster.confidence = cluster.sources.length === 1
      ? Math.min(55, 42 + (cluster.events.length - 1) * 3)
      : Math.min(96, 35 + cluster.sources.length * 18 + (cluster.events.length - 1) * 3);
  }
  return clusters.sort((left, right) => (
    EVENT_SEVERITY_RANK[right.primary.severity] - EVENT_SEVERITY_RANK[left.primary.severity]
    || right.confidence - left.confidence
    || Date.parse(right.updatedAt) - Date.parse(left.updatedAt)
  ));
}

export interface GlobalIntelDataSource {
  health(): Promise<Record<string, unknown>>;
  staticSnapshot(): Promise<Record<string, unknown>>;
  overview(): Promise<Record<string, unknown>>;
  subscribe(
    onPayload: (payload: Record<string, unknown>) => void,
    onStatus: (status: "connecting" | "live" | "degraded") => void,
  ): () => void;
}

function objectValue(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function listValue(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => (
      typeof item === "object" && item !== null && !Array.isArray(item)
    ))
    : [];
}

function stringValue(value: Record<string, unknown>, ...keys: string[]) {
  for (const key of keys) {
    const candidate = value[key];
    if (typeof candidate === "string" && candidate.trim()) return candidate.trim();
    if (typeof candidate === "number" && Number.isFinite(candidate)) return String(candidate);
  }
  return "";
}

function plainText(value: unknown) {
  if (typeof value !== "string") return "";
  return value
    .replace(/<[^>]*>/g, " ")
    .replace(/&lt;[^&]*?&gt;/g, " ")
    .replace(/&nbsp;|&#160;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&quot;|&#34;/gi, "\"")
    .replace(/&#39;|&apos;/gi, "'")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/\s+/g, " ")
    .trim();
}

function booleanValue(value: unknown) {
  return value === true || value === 1 || value === "true";
}

function mediaSentiment(value: unknown): GlobalMediaSentiment {
  const normalized = String(value ?? "").toLocaleLowerCase();
  return normalized === "positive" || normalized === "negative"
    || normalized === "mixed" || normalized === "neutral"
    ? normalized
    : "neutral";
}

function mediaVelocityState(value: unknown): GlobalMediaMonitorTopic["velocityState"] {
  const normalized = String(value ?? "").toLocaleLowerCase();
  return normalized === "rising" || normalized === "falling" || normalized === "new"
    ? normalized
    : "flat";
}

function nullableNumberValue(record: Record<string, unknown>, key: string) {
  const value = record[key];
  return value === null || value === undefined || value === ""
    ? null
    : numberValue(record, key) ?? null;
}

function mediaVelocityValue(
  record: Record<string, unknown>,
  state: GlobalMediaMonitorTopic["velocityState"],
) {
  const value = nullableNumberValue(record, "heat_velocity_pct");
  return state === "new" && (value === 100 || value === null) ? null : value;
}

function normalizeMediaFrames(value: unknown): GlobalMediaMonitorFrame[] {
  return listValue(value).map((frame) => ({
    group: stringValue(frame, "group") || "other",
    label: stringValue(frame, "label") || "其他来源",
    count: numberValue(frame, "count") ?? 0,
    positive: numberValue(frame, "positive") ?? 0,
    negative: numberValue(frame, "negative") ?? 0,
    neutral: numberValue(frame, "neutral") ?? 0,
    mixed: numberValue(frame, "mixed") ?? 0,
    dominantSentiment: mediaSentiment(frame.dominant_sentiment),
    dominantLabel: stringValue(frame, "dominant_label") || "中性",
    sources: stringList(frame.sources),
  }));
}

export function normalizeGlobalMediaMonitor(
  snapshot: Record<string, unknown>,
): GlobalMediaMonitor {
  const domain = objectValue(snapshot.media_monitor);
  const summary = objectValue(domain.summary);
  const sentiment = objectValue(summary.sentiment);
  const topics = domainRecords(snapshot, "media_monitor", "topics").map((topic) => {
    const counts = objectValue(topic.sentiment_counts);
    const velocityState = mediaVelocityState(topic.velocity_state);
    return {
      id: stringValue(topic, "id") || stableId("media-topic", stringValue(topic, "label", "headline")),
      label: stringValue(topic, "label") || stringValue(topic, "headline") || "未命名主题",
      headline: stringValue(topic, "headline") || stringValue(topic, "label"),
      mentionCount: numberValue(topic, "mention_count") ?? 0,
      currentMentions: numberValue(topic, "current_mentions") ?? 0,
      previousMentions: numberValue(topic, "previous_mentions") ?? 0,
      heatVelocityPct: mediaVelocityValue(topic, velocityState),
      velocityState,
      heatScore: numberValue(topic, "heat_score") ?? 0,
      attentionScore: numberValue(topic, "attention_score") ?? numberValue(topic, "heat_score") ?? 0,
      attentionLevel: stringValue(topic, "attention_level") || "常规",
      spreadScore: numberValue(topic, "spread_score") ?? 0,
      spreadLevel: stringValue(topic, "spread_level") || "有限传播",
      sourceCount: numberValue(topic, "source_count") ?? 0,
      sources: stringList(topic.sources),
      sourceTiers: stringList(topic.source_tiers),
      languageCount: numberValue(topic, "language_count") ?? 0,
      languages: stringList(topic.languages),
      languageLabels: stringList(topic.language_labels),
      crossLanguage: booleanValue(topic.cross_language),
      sentiment: mediaSentiment(topic.sentiment),
      sentimentScore: numberValue(topic, "sentiment_score") ?? 0,
      sentimentCounts: {
        positive: numberValue(counts, "positive") ?? 0,
        negative: numberValue(counts, "negative") ?? 0,
        neutral: numberValue(counts, "neutral") ?? 0,
        mixed: numberValue(counts, "mixed") ?? 0,
      },
      mediaFrames: normalizeMediaFrames(topic.media_frames),
      framingDivergence: booleanValue(topic.framing_divergence),
      framingDivergenceScore: numberValue(topic, "framing_divergence_score") ?? 0,
      verificationStatus: stringValue(topic, "verification_status") || "常规报道",
      verificationFlags: stringList(topic.verification_flags),
      verificationTimeline: listValue(topic.verification_timeline).map((step) => ({
        status: stringValue(step, "status") || "核验提示",
        flag: stringValue(step, "flag"),
        timestamp: isoTimestamp(step.timestamp),
        source: stringValue(step, "source") || "公开来源",
        title: stringValue(step, "title"),
        url: stringValue(step, "url"),
      })).filter((step) => step.title),
      socialEngagement: numberValue(topic, "social_engagement") ?? 0,
      latestAt: isoTimestamp(topic.latest_at),
      keywords: stringList(topic.keywords),
      items: listValue(topic.items).map((item) => ({
        key: stringValue(item, "key") || stableId("media-item", stringValue(item, "source"), stringValue(item, "title")),
        title: stringValue(item, "title"),
        source: stringValue(item, "source") || "公开来源",
        url: stringValue(item, "url"),
        language: stringValue(item, "language") || "en",
        sentiment: mediaSentiment(item.sentiment),
        published: isoTimestamp(item.published),
        kind: (stringValue(item, "kind") === "social" ? "social" : "news") as GlobalMediaMonitorTopicItem["kind"],
      })).filter((item) => item.title),
    } satisfies GlobalMediaMonitorTopic;
  });
  const annotations = domainRecords(snapshot, "media_monitor", "annotations").map((annotation) => {
    const velocityState = mediaVelocityState(annotation.velocity_state);
    return ({
      key: stringValue(annotation, "key"),
      title: stringValue(annotation, "title"),
      source: stringValue(annotation, "source"),
      url: stringValue(annotation, "url"),
      topicId: stringValue(annotation, "topic_id"),
      sentiment: mediaSentiment(annotation.sentiment),
      sentimentScore: numberValue(annotation, "sentiment_score") ?? 0,
      language: stringValue(annotation, "language") || "en",
      verificationStatus: stringValue(annotation, "verification_status") || "常规报道",
      verificationFlags: stringList(annotation.verification_flags),
      heatVelocityPct: mediaVelocityValue(annotation, velocityState),
      velocityState,
      spreadScore: numberValue(annotation, "spread_score") ?? 0,
      crossLanguageTopic: booleanValue(annotation.cross_language_topic),
    });
  }).filter((annotation) => annotation.title);

  const summaryVelocityState = mediaVelocityState(summary.velocity_state);

  return {
    summary: {
      analyzedItems: numberValue(summary, "analyzed_items") ?? 0,
      newsItems: numberValue(summary, "news_items") ?? 0,
      socialItems: numberValue(summary, "social_items") ?? 0,
      sourceCount: numberValue(summary, "source_count") ?? 0,
      languageCount: numberValue(summary, "language_count") ?? 0,
      topicCount: numberValue(summary, "topic_count") ?? topics.length,
      currentMentions: numberValue(summary, "current_mentions") ?? 0,
      previousMentions: numberValue(summary, "previous_mentions") ?? 0,
      heatVelocityPct: mediaVelocityValue(summary, summaryVelocityState),
      velocityState: summaryVelocityState,
      windowHours: numberValue(summary, "window_hours") ?? 12,
      crossLanguageTopicCount: numberValue(summary, "cross_language_topic_count") ?? 0,
      flaggedTopicCount: numberValue(summary, "flagged_topic_count") ?? 0,
      disputedTopicCount: numberValue(summary, "disputed_topic_count") ?? 0,
      reversalTopicCount: numberValue(summary, "reversal_topic_count") ?? 0,
      divergentTopicCount: numberValue(summary, "divergent_topic_count") ?? 0,
      attentionTopicCount: numberValue(summary, "attention_topic_count") ?? 0,
      spreadScore: numberValue(summary, "spread_score") ?? 0,
      sentiment: {
        positive: numberValue(sentiment, "positive") ?? 0,
        negative: numberValue(sentiment, "negative") ?? 0,
        neutral: numberValue(sentiment, "neutral") ?? 0,
        mixed: numberValue(sentiment, "mixed") ?? 0,
        positivePct: numberValue(sentiment, "positive_pct") ?? 0,
        negativePct: numberValue(sentiment, "negative_pct") ?? 0,
        neutralPct: numberValue(sentiment, "neutral_pct") ?? 0,
        mixedPct: numberValue(sentiment, "mixed_pct") ?? 0,
        netScore: numberValue(sentiment, "net_score") ?? 0,
      },
    },
    topics,
    mediaFrames: normalizeMediaFrames(domain.media_frames),
    annotations,
    caveat: stringValue(domain, "caveat"),
    timestamp: isoTimestamp(domain.timestamp),
  };
}

export function mediaSentimentLabel(sentiment: GlobalMediaSentiment) {
  return sentiment === "positive" ? "正面"
    : sentiment === "negative" ? "负面"
      : sentiment === "mixed" ? "正负交织"
        : "中性";
}

export function signedPercent(value: number | null | undefined) {
  if (value === null || value === undefined || !Number.isFinite(value)) return "基线不足";
  return `${value > 0 ? "+" : ""}${Math.round(value)}%`;
}

export function mediaVelocityLabel(
  value: number | null | undefined,
  state: GlobalMediaMonitorTopic["velocityState"],
) {
  return state === "new" && value === null ? "新出现" : signedPercent(value);
}

export function globalMediaTopicSimilarity(
  left: Pick<GlobalMediaMonitorTopic, "id" | "label" | "headline" | "keywords" | "sources">,
  right: Pick<GlobalMediaMonitorTopic, "id" | "label" | "headline" | "keywords" | "sources">,
) {
  if (left.id === right.id) return 100;
  const words = (topic: typeof left) => new Set(
    [topic.label, topic.headline, ...topic.keywords]
      .flatMap((value) => normalizedEntityText(value).split(" "))
      .filter((value) => value.length >= 2),
  );
  const leftWords = words(left);
  const rightWords = words(right);
  const wordUnion = new Set([...leftWords, ...rightWords]);
  const wordOverlap = [...leftWords].filter((value) => rightWords.has(value)).length;
  const leftSources = new Set(left.sources.map(normalizedEntityText));
  const sourceOverlap = right.sources.filter((value) => leftSources.has(normalizedEntityText(value))).length;
  const score = (wordUnion.size ? wordOverlap / wordUnion.size * 82 : 0)
    + Math.min(18, sourceOverlap * 6);
  return Math.round(Math.min(99, score));
}

export function findGlobalMediaMonitorAnnotation(
  snapshot: Record<string, unknown>,
  input: { title: string; source?: string; url?: string },
) {
  const monitor = normalizeGlobalMediaMonitor(snapshot);
  const title = normalizedEntityText(input.title);
  const source = normalizedEntityText(input.source ?? "");
  const url = input.url?.trim() ?? "";
  return monitor.annotations.find((annotation) => (
    Boolean(url && annotation.url === url)
    || (
      normalizedEntityText(annotation.title) === title
      && (!source || normalizedEntityText(annotation.source) === source)
    )
  ));
}

export function findGlobalMediaMonitorTopic(
  monitor: GlobalMediaMonitor,
  annotation?: GlobalMediaMonitorAnnotation,
) {
  return annotation
    ? monitor.topics.find((topic) => topic.id === annotation.topicId)
    : undefined;
}

function severityValue(value: unknown, fallback: GlobalIntelSeverity = "info"): GlobalIntelSeverity {
  const normalized = String(value ?? "").toLocaleLowerCase();
  return normalized === "critical" || normalized === "high" || normalized === "medium"
    || normalized === "low" || normalized === "info"
    ? normalized
    : fallback;
}

function compactNumber(value: number) {
  return Intl.NumberFormat("zh-CN", { notation: "compact", maximumFractionDigits: 1 }).format(value);
}

const ANALYSIS_LABELS: Record<string, string> = {
  middle_east: "中东",
  north_america: "北美",
  europe: "欧洲",
  east_asia: "东亚",
  south_asia: "南亚",
  east_africa: "东非",
  africa: "非洲",
  south_america: "南美",
  oceania: "大洋洲",
  eastern_europe: "东欧",
  sahel: "萨赫勒",
  arctic: "北极",
  baltic_sea: "波罗的海",
  black_sea: "黑海",
  persian_gulf: "波斯湾",
  red_sea: "红海",
  korean_peninsula: "朝鲜半岛",
  korean_dmz: "朝韩非军事区",
  taiwan_strait: "台湾海峡",
  south_china_sea: "南海",
  indo_pacific: "印太",
  military_flights: "军机活动",
  surge_aircraft: "军机活动激增",
  acled_events: "冲突事件",
};

function analysisLabel(value: string) {
  return ANALYSIS_LABELS[value.toLocaleLowerCase()] ?? value.replace(/[_-]+/g, " ");
}

function eventFacts(entries: Array<[string, unknown]>) {
  return entries
    .map(([label, value]) => ({ label, value: value === undefined || value === null ? "" : String(value) }))
    .filter((entry) => entry.value.trim());
}

function numberValue(value: Record<string, unknown>, ...keys: string[]) {
  for (const key of keys) {
    const candidate = value[key];
    const number = typeof candidate === "number" ? candidate : Number(candidate);
    if (Number.isFinite(number)) return number;
  }
  return undefined;
}

const COUNTRY_CODES: Record<string, string> = {
  afghanistan: "AFG",
  "burkina faso": "BFA",
  china: "CHN",
  colombia: "COL",
  "democratic republic of congo": "COD",
  "democratic republic of the congo": "COD",
  ethiopia: "ETH",
  france: "FRA",
  germany: "DEU",
  india: "IND",
  iran: "IRN",
  iraq: "IRQ",
  israel: "ISR",
  japan: "JPN",
  lebanon: "LBN",
  mali: "MLI",
  mexico: "MEX",
  myanmar: "MMR",
  nigeria: "NGA",
  pakistan: "PAK",
  palestine: "PSE",
  russia: "RUS",
  "russian federation": "RUS",
  singapore: "SGP",
  somalia: "SOM",
  "south korea": "KOR",
  sudan: "SDN",
  syria: "SYR",
  taiwan: "TWN",
  turkey: "TUR",
  ukraine: "UKR",
  "united arab emirates": "ARE",
  "united kingdom": "GBR",
  "united states": "USA",
  usa: "USA",
  yemen: "YEM",
};

function countryCode(record: Record<string, unknown>, country: string) {
  const direct = stringValue(record, "country_code", "country_iso3", "iso3", "iso_a3").toUpperCase();
  if (/^[A-Z]{3}$/.test(direct)) return direct;
  return COUNTRY_CODES[country.toLocaleLowerCase()] ?? "";
}

function isoTimestamp(value: unknown, fallback = "") {
  if (value === undefined || value === null || value === "") return fallback;
  const numeric = typeof value === "number"
    ? value
    : typeof value === "string" && /^\d{10,13}$/.test(value.trim())
      ? Number(value)
      : undefined;
  const parsed = numeric === undefined
    ? Date.parse(String(value))
    : numeric > 10_000_000_000 ? numeric : numeric * 1000;
  return Number.isFinite(parsed) ? new Date(parsed).toISOString() : fallback;
}

function firstValue(record: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const candidate = record[key];
    if (candidate !== undefined && candidate !== null && candidate !== "") return candidate;
  }
  return undefined;
}

function stringList(value: unknown) {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && Boolean(item.trim()))
    : typeof value === "string" && value.trim()
      ? [value.trim()]
      : [];
}

function stableId(...values: unknown[]) {
  return values
    .filter((value) => value !== undefined && value !== null && String(value).trim())
    .join("-")
    .toLocaleLowerCase()
    .replace(/[^a-z0-9\u4e00-\u9fff]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 120);
}

function pointFromRecord(
  record: Record<string, unknown>,
  input: {
    category: GlobalIntelCategory;
    source: string;
    titleKeys: string[];
    detailKeys: string[];
    severity?: GlobalIntelSeverity;
    timestampKeys?: string[];
  },
): GlobalIntelPoint | undefined {
  const latitude = numberValue(record, "latitude", "lat");
  const longitude = numberValue(record, "longitude", "lon", "lng");
  if (latitude === undefined || longitude === undefined) return undefined;
  if (Math.abs(latitude) > 90 || Math.abs(longitude) > 180) return undefined;
  const title = stringValue(record, ...input.titleKeys) || input.source;
  const detail = stringValue(record, ...input.detailKeys) || input.category;
  const timestamp = isoTimestamp(firstValue(
    record,
    input.timestampKeys ?? ["timestamp", "time", "date"],
  ));
  const url = stringValue(record, "url", "link");
  const country = stringValue(record, "country", "origin_country");
  const normalizedCountryCode = countryCode(record, country);
  return {
    id: stableId(input.category, stringValue(record, "id", "event_id_cnty"), title, latitude, longitude),
    category: input.category,
    latitude,
    longitude,
    title,
    detail,
    source: stringValue(record, "source", "operator", "feed_name") || input.source,
    severity: input.severity ?? "info",
    ...(country ? { country } : {}),
    ...(normalizedCountryCode ? { countryCode: normalizedCountryCode } : {}),
    ...(timestamp ? { timestamp } : {}),
    ...(url ? { url } : {}),
  };
}

function coordinatePair(record: Record<string, unknown>, prefix: "start" | "end") {
  const latitude = numberValue(record, `lat_${prefix}`, `${prefix}_lat`);
  const longitude = numberValue(record, `lon_${prefix}`, `lng_${prefix}`, `${prefix}_lon`);
  return latitude === undefined || longitude === undefined
    ? undefined
    : [longitude, latitude] as [number, number];
}

export function normalizeGlobalIntelRoutes(
  snapshot: Record<string, unknown>,
): GlobalIntelRoute[] {
  const routes: GlobalIntelRoute[] = [];
  const routeRecords = (domain: string, key: string) => {
    const direct = listValue(snapshot[domain]);
    return direct.length ? direct : domainRecords(snapshot, domain, key);
  };

  for (const record of routeRecords("pipelines", "pipelines")) {
    const start = coordinatePair(record, "start");
    const end = coordinatePair(record, "end");
    if (!start || !end) continue;
    const name = stringValue(record, "name") || "能源管线";
    const route = stringValue(record, "route");
    routes.push({
      id: stableId("pipeline", name),
      kind: "pipeline",
      name,
      detail: [route, stringValue(record, "capacity")].filter(Boolean).join(" · "),
      path: [start, end],
      keywords: [name, route].filter(Boolean),
      exposure: PIPELINE_EXPOSURE,
      pathType: "corridor",
      status: stringValue(record, "status"),
    });
  }

  for (const record of routeRecords("cable_corridors", "corridors")) {
    const latitudes = Array.isArray(record.lat_range) ? record.lat_range.map(Number) : [];
    const longitudes = Array.isArray(record.lon_range) ? record.lon_range.map(Number) : [];
    if (latitudes.length < 2 || longitudes.length < 2 || [...latitudes, ...longitudes].some((value) => !Number.isFinite(value))) continue;
    const name = stringValue(record, "name") || "海底光缆走廊";
    const cables = Array.isArray(record.cables) ? record.cables.filter((value): value is string => typeof value === "string") : [];
    const latitude = (latitudes[0]! + latitudes[1]!) / 2;
    routes.push({
      id: stableId("cable", name),
      kind: "cable",
      name: name.replace(/_/g, " "),
      detail: cables.join(" · "),
      path: [[longitudes[0]!, latitude], [longitudes[1]!, latitude]],
      keywords: [name.replace(/_/g, " "), ...cables],
      exposure: CABLE_EXPOSURE,
      pathType: "corridor",
      status: "active",
    });
  }

  const tradeRoutePoints = new Map<string, [number, number]>(Object.entries(ROUTE_NODE_COORDINATES));
  for (const record of routeRecords("trade_routes", "routes")) {
    const name = stringValue(record, "name");
    const latitude = numberValue(record, "lat", "latitude");
    const longitude = numberValue(record, "lon", "longitude");
    if (!name || latitude === undefined || longitude === undefined) continue;
    tradeRoutePoints.set(name, [longitude, latitude]);
  }
  for (const corridor of SHIPPING_CORRIDORS) {
    const path = corridor.stops
      .map((name) => tradeRoutePoints.get(name))
      .filter((point): point is [number, number] => Boolean(point));
    if (path.length < 2) continue;
    routes.push({
      id: stableId("shipping", corridor.name),
      kind: "shipping",
      name: corridor.name,
      detail: corridor.detail,
      path,
      keywords: [
        corridor.name,
        corridor.detail,
        ...corridor.stops,
        ...corridor.stops.flatMap((stop) => ROUTE_NODE_ALIASES[stop] ?? []),
      ],
      exposure: corridor.exposure,
      pathType: "corridor",
      status: "active",
    });
  }

  for (const record of routeRecords("flight_routes", "routes")) {
    const start = coordinatePair(record, "start");
    const end = coordinatePair(record, "end");
    if (!start || !end) continue;
    const name = stringValue(record, "name") || "航空走廊";
    routes.push({
      id: stableId("flight", name),
      kind: "flight",
      name,
      detail: stringValue(record, "detail", "route") || "航空运行代表性走廊",
      path: [start, end],
      keywords: [name, stringValue(record, "route")].filter(Boolean),
      exposure: FLIGHT_EXPOSURE,
      pathType: "corridor",
      status: stringValue(record, "status") || "active",
    });
  }
  for (const corridor of FLIGHT_CORRIDORS) {
    routes.push({
      id: stableId("flight", corridor.name),
      kind: "flight",
      name: corridor.name,
      detail: corridor.detail,
      path: corridor.path,
      keywords: [corridor.name, "航空", "航班", "航空货运"],
      exposure: FLIGHT_EXPOSURE,
      pathType: "corridor",
      status: "active",
    });
  }

  return routes;
}

function domainRecords(
  snapshot: Record<string, unknown>,
  domain: string,
  key: string,
) {
  return listValue(objectValue(snapshot[domain])[key]);
}

function isMilitaryAircraft(record: Record<string, unknown>) {
  if (record.military === true || record.is_military === true) return true;
  const classification = `${stringValue(record, "type", "aircraft_type", "category", "operator")}`.toLocaleLowerCase();
  if (/military|air force|navy|army|marines|coast guard|政府专机/.test(classification)) return true;
  const callsign = stringValue(record, "callsign").toUpperCase().replace(/\s+/g, "");
  return /^(?:RCH|REACH|CNV|CFC|RAF|NATO|FORTE|HOMER|DUKE|EVAC|SAM|VENUS|JAKE|VIPER|SPAR|PAT|RRR|IAM|GAF|BAF|FAF|AME|ASY|NOW|MMF)/.test(callsign);
}

export function updateGlobalIntelMilitaryTrackHistory(
  history: GlobalIntelMilitaryTrackHistory,
  snapshot: Record<string, unknown>,
  now = new Date(),
): GlobalIntelMilitaryTrackHistory {
  const nowMs = now.getTime();
  const cutoff = nowMs - 6 * 60 * 60 * 1000;
  const next: GlobalIntelMilitaryTrackHistory = {};
  for (const [aircraftId, samples] of Object.entries(history)) {
    const recent = samples
      .filter((sample) => Date.parse(sample.observedAt) >= cutoff)
      .sort((left, right) => Date.parse(left.observedAt) - Date.parse(right.observedAt))
      .slice(-72);
    if (recent.length) next[aircraftId] = recent;
  }

  const domainTimestamp = objectValue(snapshot.military_flights).timestamp;
  for (const record of domainRecords(snapshot, "military_flights", "aircraft").filter(isMilitaryAircraft)) {
    const callsign = stringValue(record, "callsign", "registration", "icao24").trim();
    const aircraftId = stringValue(record, "icao24").trim().toLowerCase() || callsign.toUpperCase();
    const latitude = numberValue(record, "latitude", "lat");
    const longitude = numberValue(record, "longitude", "lon");
    if (!aircraftId || !callsign || latitude === undefined || longitude === undefined) continue;
    const observedAt = isoTimestamp(
      firstValue(record, ["timestamp", "last_contact"]) ?? domainTimestamp,
      now.toISOString(),
    );
    const altitude = numberValue(record, "altitude_m", "altitude");
    const heading = numberValue(record, "heading", "true_track");
    const sample: GlobalIntelAircraftTrackSample = {
      aircraftId,
      callsign,
      latitude,
      longitude,
      observedAt,
      ...(altitude !== undefined ? { altitude } : {}),
      ...(heading !== undefined ? { heading } : {}),
    };
    const samples = next[aircraftId] ?? [];
    const duplicate = samples.some((existing) => (
      existing.observedAt === sample.observedAt
      && existing.latitude === sample.latitude
      && existing.longitude === sample.longitude
    ));
    if (!duplicate) samples.push(sample);
    next[aircraftId] = samples
      .filter((item) => Date.parse(item.observedAt) >= cutoff)
      .sort((left, right) => Date.parse(left.observedAt) - Date.parse(right.observedAt))
      .slice(-72);
  }
  return next;
}

export function normalizeGlobalIntelPoints(
  snapshot: Record<string, unknown>,
): GlobalIntelPoint[] {
  const points: GlobalIntelPoint[] = [];
  const append = (
    records: Array<Record<string, unknown>>,
    input: Parameters<typeof pointFromRecord>[1],
    severity?: (record: Record<string, unknown>) => GlobalIntelSeverity,
    dossier?: (record: Record<string, unknown>) => Pick<GlobalIntelPoint, "facts" | "content">,
  ) => {
    for (const record of records) {
      const point = pointFromRecord(record, {
        ...input,
        ...(severity ? { severity: severity(record) } : {}),
      });
      if (point) {
        const details = dossier?.(record);
        if (details?.facts?.length) point.facts = details.facts;
        if (details?.content) point.content = details.content;
        points.push(point);
      }
    }
  };

  append(domainRecords(snapshot, "military_bases", "bases"), {
    category: "military", source: "World Intel 基础设施库",
    titleKeys: ["name"], detailKeys: ["operator", "type", "country"], severity: "medium",
  });
  append(domainRecords(snapshot, "strategic_ports", "ports"), {
    category: "infrastructure", source: "World Intel 港口库",
    titleKeys: ["name"], detailKeys: ["type", "country", "operator"], severity: "low",
  });
  append(domainRecords(snapshot, "nuclear_facilities", "facilities"), {
    category: "infrastructure", source: "World Intel 核设施库",
    titleKeys: ["name"], detailKeys: ["type", "country", "status"], severity: "medium",
  });
  append(domainRecords(snapshot, "cloud_regions", "regions"), {
    category: "infrastructure", source: "World Intel 云区域库",
    titleKeys: ["name", "provider"], detailKeys: ["provider", "country", "region"], severity: "info",
  });
  append(domainRecords(snapshot, "financial_centers", "centers"), {
    category: "market", source: "World Intel 金融中心库",
    titleKeys: ["name", "city"], detailKeys: ["country", "tier", "specialty"], severity: "info",
  });
  append(domainRecords(snapshot, "earthquakes", "earthquakes").map((record) => ({
    ...record,
    detail_summary: [
      numberValue(record, "magnitude") === undefined ? "" : "M" + numberValue(record, "magnitude")!.toFixed(1),
      numberValue(record, "depth_km") === undefined ? "" : "深度 " + numberValue(record, "depth_km")!.toFixed(1) + " km",
      record.tsunami_alert ? "海啸提示" : "",
    ].filter(Boolean).join(" · "),
  })), {
    category: "disaster", source: "USGS",
    titleKeys: ["place"], detailKeys: ["detail_summary"],
    timestampKeys: ["time"],
  }, (record) => {
    const magnitude = numberValue(record, "magnitude") ?? 0;
    return magnitude >= 6 ? "critical" : magnitude >= 5 ? "high" : "medium";
  }, (record) => ({
    facts: eventFacts([
      ["震级", numberValue(record, "magnitude") === undefined ? "" : "M" + numberValue(record, "magnitude")!.toFixed(1)],
      ["深度", numberValue(record, "depth_km") === undefined ? "" : numberValue(record, "depth_km")!.toFixed(1) + " km"],
      ["海啸提示", record.tsunami_alert ? "是" : "否"],
      ["有感报告", numberValue(record, "felt_reports")],
      ["USGS警报", stringValue(record, "alert_level")],
    ]),
    content: "USGS 实时地震记录。震级、深度和海啸字段来自自动观测，影响范围仍需结合当地机构通报确认。",
  }));
  append(domainRecords(snapshot, "acled_events", "events").map((record) => ({
    ...record,
    detail_summary: [
      stringValue(record, "event_type"),
      stringValue(record, "sub_event_type"),
      numberValue(record, "fatalities") ? "报告死亡 " + numberValue(record, "fatalities") : "",
    ].filter(Boolean).join(" · "),
  })), {
    category: "conflict", source: "ACLED",
    titleKeys: ["location", "event_type", "country"],
    detailKeys: ["detail_summary"],
    timestampKeys: ["event_date"],
  }, (record) => {
    const fatalities = numberValue(record, "fatalities") ?? 0;
    return fatalities >= 20 ? "critical" : fatalities > 0 ? "high" : "medium";
  }, (record) => ({
    facts: eventFacts([
      ["事件类型", stringValue(record, "event_type")],
      ["子类型", stringValue(record, "sub_event_type")],
      ["参与方A", stringValue(record, "actor1")],
      ["参与方B", stringValue(record, "actor2")],
      ["报告死亡", numberValue(record, "fatalities")],
      ["行政区", [stringValue(record, "admin1"), stringValue(record, "admin2")].filter(Boolean).join(" · ")],
      ["原始来源", stringValue(record, "source")],
    ]),
    content: plainText(stringValue(record, "notes")),
  }));
  append(domainRecords(snapshot, "ucdp_events", "events").map((record) => {
    const sourceArticle = stringValue(record, "source_article");
    return {
      ...record,
      ...(sourceArticle.startsWith("http") ? { url: sourceArticle } : {}),
      detail_summary: [
        stringValue(record, "type_of_violence_label"),
        [stringValue(record, "side_a"), stringValue(record, "side_b")].filter(Boolean).join(" vs "),
        numberValue(record, "best") ? "最佳估计死亡 " + numberValue(record, "best") : "",
      ].filter(Boolean).join(" · "),
    };
  }), {
    category: "conflict", source: "UCDP",
    titleKeys: ["where_description", "country", "location"],
    detailKeys: ["detail_summary"],
    timestampKeys: ["date_start", "event_date"],
  }, (record) => {
    const fatalities = numberValue(record, "best", "fatalities") ?? 0;
    return fatalities >= 20 ? "critical" : fatalities > 0 ? "high" : "medium";
  }, (record) => ({
    facts: eventFacts([
      ["暴力类型", stringValue(record, "type_of_violence_label")],
      ["参与方A", stringValue(record, "side_a")],
      ["参与方B", stringValue(record, "side_b")],
      ["死亡估计", numberValue(record, "best")],
      ["估计区间", numberValue(record, "low") === undefined ? "" : numberValue(record, "low") + "–" + (numberValue(record, "high") ?? "—")],
      ["区域", stringValue(record, "region")],
    ]),
    content: plainText(stringValue(record, "source_headline", "source_article")),
  }));
  append(domainRecords(snapshot, "military_flights", "aircraft").filter(isMilitaryAircraft), {
    category: "military", source: "ADS-B",
    titleKeys: ["callsign", "registration", "icao24"],
    detailKeys: ["origin_country", "aircraft_type", "type", "altitude_m", "velocity_ms"],
    timestampKeys: ["timestamp", "last_contact"],
  }, (record) => {
    const squawk = stringValue(record, "squawk");
    return squawk === "7700" ? "critical" : squawk === "7500" || squawk === "7600" ? "high" : "info";
  });

  const navWarningTimestamp = objectValue(snapshot.nav_warnings).timestamp;
  append(domainRecords(snapshot, "nav_warnings", "warnings").map((record) => ({
    ...record,
    title_summary: [
      stringValue(record, "navarea") ? `NAVAREA ${stringValue(record, "navarea")}` : "航行警告",
      stringValue(record, "id"),
    ].filter(Boolean).join(" · "),
    timestamp: firstValue(record, ["issue_date"]) ?? navWarningTimestamp,
  })), {
    category: "maritime", source: "NGA 航行警告",
    titleKeys: ["title_summary", "id", "navarea"], detailKeys: ["text", "authority"],
  }, (record) => {
    const text = stringValue(record, "text").toLocaleLowerCase();
    if (/missile|mine|firing|weapon|danger|sunk|closed|closure/.test(text)) return "high";
    return stringValue(record, "status") === "active" ? "medium" : "low";
  }, (record) => ({
    facts: eventFacts([
      ["NAVAREA", stringValue(record, "navarea")],
      ["分区", stringValue(record, "subregion")],
      ["状态", stringValue(record, "status")],
      ["发布机构", stringValue(record, "authority")],
      ["取消日期", stringValue(record, "cancel_date")],
    ]),
    content: plainText(stringValue(record, "text")),
  }));

  const nuclearDomain = objectValue(snapshot.nuclear_monitor);
  const nuclearTimestamp = nuclearDomain.timestamp;
  append(domainRecords(snapshot, "nuclear_monitor", "sites").map((record) => {
    const highestConcern = objectValue(record.highest_concern);
    const eventCount = numberValue(record, "events_detected") ?? 0;
    return {
      ...record,
      detail_summary: eventCount > 0
        ? `${eventCount} 个近场地震 · 最高关注 ${stringValue(highestConcern, "concern_level") || "待研判"}`
        : `近 72 小时未发现近场异常 · ${stringValue(record, "status") || "状态未知"}`,
      timestamp: nuclearTimestamp,
    };
  }), {
    category: "nuclear", source: "World Intel 核监测站",
    titleKeys: ["name"], detailKeys: ["detail_summary", "status"],
  }, (record) => {
    const concern = stringValue(objectValue(record.highest_concern), "concern_level").toLocaleLowerCase();
    if (concern === "critical") return "critical";
    if (concern === "high" || concern === "elevated") return "high";
    return (numberValue(record, "events_detected") ?? 0) > 0 ? "medium" : "info";
  });
  append(domainRecords(snapshot, "nuclear_monitor", "flagged_events").map((record) => ({
    ...record,
    detail_summary: [
      numberValue(record, "magnitude") === undefined ? "" : `M${numberValue(record, "magnitude")!.toFixed(1)}`,
      numberValue(record, "depth_km") === undefined ? "" : `深度 ${numberValue(record, "depth_km")!.toFixed(1)} km`,
      numberValue(record, "distance_km") === undefined ? "" : `距设施 ${numberValue(record, "distance_km")!.toFixed(1)} km`,
    ].filter(Boolean).join(" · "),
  })), {
    category: "nuclear", source: "USGS 核活动监测",
    titleKeys: ["site", "place"], detailKeys: ["detail_summary", "place"],
    timestampKeys: ["time"],
  }, (record) => {
    const concern = stringValue(record, "concern_level").toLocaleLowerCase();
    return concern === "critical" ? "critical" : concern === "high" ? "high" : concern === "elevated" ? "medium" : "low";
  }, (record) => ({
    facts: eventFacts([
      ["关注评分", numberValue(record, "concern_score")],
      ["关注等级", stringValue(record, "concern_level")],
      ["震级", numberValue(record, "magnitude") === undefined ? "" : "M" + numberValue(record, "magnitude")!.toFixed(1)],
      ["深度", numberValue(record, "depth_km") === undefined ? "" : numberValue(record, "depth_km")!.toFixed(1) + " km"],
      ["距设施", numberValue(record, "distance_km") === undefined ? "" : numberValue(record, "distance_km")!.toFixed(1) + " km"],
      ["设施国家", stringValue(record, "site_country")],
    ]),
    content: "该记录表示核试验或核设施附近出现地震信号，不等同于核试验或核事故确认。关注评分由震级、深度、距离和设施状态综合计算。",
  }));

  const climateDomain = objectValue(snapshot.climate_anomalies);
  const climateTimestamp = climateDomain.timestamp;
  const climateZones = Object.entries(objectValue(climateDomain.zones)).map(([zone, value]) => {
    const record = objectValue(value);
    const temperature = numberValue(record, "temp_anomaly_c") ?? 0;
    const precipitation = numberValue(record, "precip_anomaly_pct") ?? 0;
    return {
      ...record,
      zone,
      detail_summary: `气温 ${temperature >= 0 ? "+" : ""}${temperature.toFixed(1)}°C · 降水 ${precipitation >= 0 ? "+" : ""}${precipitation.toFixed(0)}%`,
      timestamp: climateTimestamp,
    };
  });
  append(climateZones, {
    category: "climate", source: "Open-Meteo 气候基线",
    titleKeys: ["name", "zone"], detailKeys: ["detail_summary"],
  }, (record) => {
    const temperature = Math.abs(numberValue(record, "temp_anomaly_c") ?? 0);
    const precipitation = Math.abs(numberValue(record, "precip_anomaly_pct") ?? 0);
    if (temperature >= 10 || precipitation >= 1000) return "critical";
    if (record.is_significant === true) return "high";
    if (temperature >= 2 || precipitation >= 80) return "medium";
    return "info";
  }, (record) => ({
    facts: eventFacts([
      ["当前平均气温", numberValue(record, "current_avg_temp_c") === undefined ? "" : numberValue(record, "current_avg_temp_c")!.toFixed(1) + "°C"],
      ["去年同期气温", numberValue(record, "baseline_avg_temp_c") === undefined ? "" : numberValue(record, "baseline_avg_temp_c")!.toFixed(1) + "°C"],
      ["气温偏差", numberValue(record, "temp_anomaly_c") === undefined ? "" : numberValue(record, "temp_anomaly_c")!.toFixed(1) + "°C"],
      ["当前7日降水", numberValue(record, "current_precip_mm") === undefined ? "" : numberValue(record, "current_precip_mm")!.toFixed(1) + " mm"],
      ["去年同期降水", numberValue(record, "baseline_precip_mm") === undefined ? "" : numberValue(record, "baseline_precip_mm")!.toFixed(1) + " mm"],
      ["降水偏差", numberValue(record, "precip_anomaly_pct") === undefined ? "" : numberValue(record, "precip_anomaly_pct")!.toFixed(0) + "%"],
    ]),
    content: "最近7天与去年同期的气温和累计降水对比。极端百分比可能由去年同期降水接近零造成，应结合绝对降水量判断。",
  }));

  const trafficFlowDomain = objectValue(snapshot.traffic_flow);
  append(domainRecords(snapshot, "traffic_flow", "cities").map((record) => ({
    ...record,
    detail_summary: `拥堵 ${numberValue(record, "congestion_pct") ?? 0}% · 当前 ${numberValue(record, "current_speed_kmh") ?? 0} km/h`,
    timestamp: trafficFlowDomain.timestamp,
  })), {
    category: "infrastructure", source: "TomTom 交通流",
    titleKeys: ["name"], detailKeys: ["detail_summary", "country"],
  }, (record) => {
    const congestion = numberValue(record, "congestion_pct") ?? 0;
    return congestion >= 60 ? "high" : congestion >= 35 ? "medium" : "info";
  });

  const trafficIncidentDomain = objectValue(snapshot.traffic_incidents);
  append(domainRecords(snapshot, "traffic_incidents", "incidents").map((record) => ({
    ...record,
    title_summary: stringValue(record, "description", "from_road", "region") || "道路交通事件",
    detail_summary: [
      stringValue(record, "region"),
      numberValue(record, "delay_seconds") === undefined ? "" : `延误 ${Math.round(numberValue(record, "delay_seconds")! / 60)} 分钟`,
      numberValue(record, "length_meters") === undefined ? "" : `影响 ${(numberValue(record, "length_meters")! / 1000).toFixed(1)} km`,
    ].filter(Boolean).join(" · "),
    timestamp: trafficIncidentDomain.timestamp,
  })), {
    category: "infrastructure", source: "TomTom 交通事件",
    titleKeys: ["title_summary"], detailKeys: ["detail_summary", "to_road"],
  }, (record) => {
    const delay = numberValue(record, "delay_seconds") ?? 0;
    const magnitude = numberValue(record, "magnitude") ?? 0;
    return delay >= 3600 || magnitude >= 4 ? "high" : delay >= 900 || magnitude >= 2 ? "medium" : "low";
  });

  const webcamDomain = objectValue(snapshot.webcams);
  append(domainRecords(snapshot, "webcams", "cameras").map((record) => ({
    ...record,
    detail_summary: [stringValue(record, "city"), stringValue(record, "country"), stringValue(record, "status")].filter(Boolean).join(" · "),
    timestamp: webcamDomain.timestamp,
    url: stringValue(record, "player_url", "preview_url"),
  })), {
    category: "infrastructure", source: "Windy 公共摄像头",
    titleKeys: ["title", "city"], detailKeys: ["detail_summary"], severity: "info",
  });

  const exposureDomain = objectValue(snapshot.population_exposure);
  append(domainRecords(snapshot, "population_exposure", "exposed_cities").map((record) => ({
    ...record,
    title_summary: `${stringValue(record, "city") || "城市"} 人口暴露`,
    detail_summary: `${compactNumber(numberValue(record, "population") ?? 0)} 人 · 距${stringValue(record, "nearest_event") || "事件"}约 ${numberValue(record, "distance_km") ?? "—"} km`,
    timestamp: exposureDomain.timestamp,
  })), {
    category: "society", source: "World Intel 人口暴露分析",
    titleKeys: ["title_summary"], detailKeys: ["detail_summary", "event_detail"],
  }, (record) => {
    const population = numberValue(record, "population") ?? 0;
    const distance = numberValue(record, "distance_km") ?? 999;
    return population >= 5_000_000 && distance <= 100 ? "high" : distance <= 200 ? "medium" : "low";
  });

  const convergenceDomain = objectValue(snapshot.signal_convergence);
  append(domainRecords(snapshot, "signal_convergence", "hotspots")
    .filter((record) => (numberValue(record, "convergence_score") ?? 0) >= 3)
    .map((record) => {
      const score = numberValue(record, "convergence_score") ?? 0;
      const signals = objectValue(record.signals);
      return {
        ...record,
        latitude: numberValue(record, "lat", "latitude"),
        longitude: numberValue(record, "lon", "longitude"),
        title_summary: analysisLabel(stringValue(record, "name")) + " 监测信号汇聚",
        detail_summary: "汇聚评分 " + score.toFixed(1) + "/10 · 地震 " + (numberValue(signals, "earthquakes") ?? 0) + " 起",
        timestamp: convergenceDomain.timestamp,
      };
    }), {
    category: "conflict", source: "World Intel 信号汇聚",
    titleKeys: ["title_summary"], detailKeys: ["detail_summary"],
  }, (record) => {
    const score = numberValue(record, "convergence_score") ?? 0;
    return score >= 6 ? "high" : score >= 4 ? "medium" : "low";
  });

  const wildfireRegions = objectValue(objectValue(snapshot.wildfires).fires_by_region);
  for (const [region, value] of Object.entries(wildfireRegions)) {
    const clusters = listValue(objectValue(value).top_clusters);
    for (const cluster of clusters) {
      const point = pointFromRecord(cluster, {
        category: "disaster",
        source: "NASA FIRMS",
        titleKeys: ["name"],
        detailKeys: ["fire_count", "max_frp"],
        severity: "high",
      });
      if (!point) continue;
      if (point.title === "NASA FIRMS") {
        point.title = `${region.replace(/_/g, " ")} 火点集群`;
      }
      points.push(point);
    }
  }

  return [...new Map(points.map((point) => [point.id, point])).values()];
}

function eventFromPoint(point: GlobalIntelPoint, fallbackTimestamp: string): GlobalIntelEvent {
  return {
    id: point.id,
    category: point.category,
    title: point.title,
    detail: point.detail,
    source: point.source,
    severity: point.severity,
    timestamp: point.timestamp ?? fallbackTimestamp,
    pointId: point.id,
    ...(point.country ? { country: point.country } : {}),
    ...(point.countryCode ? { countryCode: point.countryCode } : {}),
    ...(point.url ? { url: point.url } : {}),
    ...(point.facts?.length ? { facts: point.facts } : {}),
    ...(point.content ? { content: point.content } : {}),
    recordKind: point.source === "ADS-B"
      ? point.severity === "critical" || point.severity === "high" ? "event" : "observation"
      : "event",
  };
}

const MILITARY_SENSITIVE_NODES = [
  { name: "Strait of Hormuz", latitude: 26.57, longitude: 56.25 },
  { name: "Bab el-Mandeb", latitude: 12.58, longitude: 43.33 },
  { name: "Suez Canal", latitude: 30.58, longitude: 32.27 },
  { name: "Taiwan Strait", latitude: 24, longitude: 118.5 },
  { name: "Strait of Luzon", latitude: 20, longitude: 121 },
  { name: "Korea Strait", latitude: 34, longitude: 129.5 },
] as const;

function coordinateDistanceKm(
  left: { latitude: number; longitude: number },
  right: { latitude: number; longitude: number },
) {
  return pointSegmentDistanceKm(
    [left.longitude, left.latitude],
    [right.longitude, right.latitude],
    [right.longitude, right.latitude],
  );
}

function sensitiveMilitaryNodes(snapshot: Record<string, unknown>) {
  const configured = domainRecords(snapshot, "trade_routes", "routes")
    .map((record) => ({
      name: stringValue(record, "name"),
      latitude: numberValue(record, "lat", "latitude"),
      longitude: numberValue(record, "lon", "longitude"),
    }))
    .filter((node): node is { name: string; latitude: number; longitude: number } => (
      Boolean(node.name)
      && node.latitude !== undefined
      && node.longitude !== undefined
      && MILITARY_SENSITIVE_NODES.some((sensitive) => sensitive.name === node.name)
    ));
  return configured.length ? configured : [...MILITARY_SENSITIVE_NODES];
}

function nearbyPointGroups(points: GlobalIntelPoint[], radiusKm: number) {
  const remaining = new Set(points.map((point) => point.id));
  const pointById = new Map(points.map((point) => [point.id, point]));
  const groups: GlobalIntelPoint[][] = [];
  while (remaining.size) {
    const firstId = remaining.values().next().value as string;
    remaining.delete(firstId);
    const group: GlobalIntelPoint[] = [pointById.get(firstId)!];
    for (let index = 0; index < group.length; index += 1) {
      const current = group[index]!;
      for (const candidateId of [...remaining]) {
        const candidate = pointById.get(candidateId)!;
        if (coordinateDistanceKm(current, candidate) > radiusKm) continue;
        remaining.delete(candidateId);
        group.push(candidate);
      }
    }
    groups.push(group);
  }
  return groups;
}

type MilitaryTrackFinding = {
  aircraftId: string;
  callsign: string;
  kind: "circling" | "reversal" | "approaching" | "disappeared";
  label: string;
  detail: string;
  severity: GlobalIntelSeverity;
  node?: string;
  sample: GlobalIntelAircraftTrackSample;
};

function angleDifference(left: number, right: number) {
  const difference = Math.abs(left - right) % 360;
  return difference > 180 ? 360 - difference : difference;
}

function bearingDegrees(left: GlobalIntelAircraftTrackSample, right: GlobalIntelAircraftTrackSample) {
  const lat1 = left.latitude * Math.PI / 180;
  const lat2 = right.latitude * Math.PI / 180;
  const longitudeDelta = (right.longitude - left.longitude) * Math.PI / 180;
  const y = Math.sin(longitudeDelta) * Math.cos(lat2);
  const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(longitudeDelta);
  return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
}

function militaryFlightSourceAvailable(snapshot: Record<string, unknown>) {
  const domain = objectValue(snapshot.military_flights);
  if (!Array.isArray(domain.aircraft) || domain.aircraft.length === 0) return false;
  if (domain.error || domain.status === "error" || domain.status === "unavailable") return false;
  const health = objectValue(objectValue(snapshot.source_health).military_flights);
  return health.status !== "error" && health.status !== "open" && health.status !== "unavailable";
}

function analyzeMilitaryTracks(
  history: GlobalIntelMilitaryTrackHistory,
  snapshot: Record<string, unknown>,
  fallbackTimestamp: string,
) {
  const findings: MilitaryTrackFinding[] = [];
  const nodes = sensitiveMilitaryNodes(snapshot);
  const currentIds = new Set(domainRecords(snapshot, "military_flights", "aircraft")
    .filter(isMilitaryAircraft)
    .map((record) => stringValue(record, "icao24").trim().toLowerCase()
      || stringValue(record, "callsign", "registration").trim().toUpperCase()));
  const nowMs = Date.parse(fallbackTimestamp);

  for (const [aircraftId, rawSamples] of Object.entries(history)) {
    const samples = [...rawSamples].sort((left, right) => Date.parse(left.observedAt) - Date.parse(right.observedAt));
    const latest = samples.at(-1);
    if (!latest) continue;
    const nearestNode = nodes
      .map((node) => ({ node, distanceKm: coordinateDistanceKm(latest, node) }))
      .sort((left, right) => left.distanceKm - right.distanceKm)[0];

    if (!currentIds.has(aircraftId) && militaryFlightSourceAvailable(snapshot) && nearestNode) {
      const missingMinutes = (nowMs - Date.parse(latest.observedAt)) / 60_000;
      if (missingMinutes >= 15 && missingMinutes <= 45 && nearestNode.distanceKm < 180) {
        findings.push({
          aircraftId, callsign: latest.callsign, kind: "disappeared",
          label: `在 ${nearestNode.node.name} 附近信号消失`,
          detail: `最后信号距节点约 ${Math.round(nearestNode.distanceKm)} km，已中断约 ${Math.round(missingMinutes)} 分钟`,
          severity: "high", node: nearestNode.node.name, sample: latest,
        });
        continue;
      }
    }
    if (!currentIds.has(aircraftId) || samples.length < 3) continue;

    if (nearestNode) {
      const recent = samples.slice(-5);
      const distances = recent.map((sample) => coordinateDistanceKm(sample, nearestNode.node));
      const continuouslyClosing = distances.length >= 3
        && distances.every((distance, index) => index === 0 || distance < distances[index - 1]!);
      const closedBy = distances[0]! - distances.at(-1)!;
      if (continuouslyClosing && closedBy >= 80 && distances.at(-1)! < 300) {
        findings.push({
          aircraftId, callsign: latest.callsign, kind: "approaching",
          label: `持续接近 ${nearestNode.node.name}`,
          detail: `连续 ${recent.length} 个点接近，距离缩短约 ${Math.round(closedBy)} km，当前约 ${Math.round(distances.at(-1)!)} km`,
          severity: distances.at(-1)! < 180 ? "high" : "medium", node: nearestNode.node.name, sample: latest,
        });
        continue;
      }
    }

    if (samples.length >= 6) {
      const recent = samples.slice(-12);
      const pathKm = recent.slice(1).reduce((sum, sample, index) => sum + coordinateDistanceKm(recent[index]!, sample), 0);
      const displacementKm = coordinateDistanceKm(recent[0]!, recent.at(-1)!);
      if (pathKm > 120 && displacementKm < 30) {
        findings.push({
          aircraftId, callsign: latest.callsign, kind: "circling", label: "疑似盘旋",
          detail: `累计航迹约 ${Math.round(pathKm)} km，首尾位移约 ${Math.round(displacementKm)} km`,
          severity: "medium", sample: latest,
        });
        continue;
      }
    }

    const previous = samples.at(-2)!;
    const beforePrevious = samples.at(-3)!;
    const incoming = previous.heading ?? bearingDegrees(beforePrevious, previous);
    const outgoing = latest.heading ?? bearingDegrees(previous, latest);
    if (angleDifference(incoming, outgoing) > 140) {
      findings.push({
        aircraftId, callsign: latest.callsign, kind: "reversal", label: "出现明显折返",
        detail: `最近航向变化约 ${Math.round(angleDifference(incoming, outgoing))}°`,
        severity: "medium", sample: latest,
      });
    }
  }
  return findings;
}

function normalizeMilitaryFlightEvents(
  points: GlobalIntelPoint[],
  snapshot: Record<string, unknown>,
  fallbackTimestamp: string,
  trackHistory: GlobalIntelMilitaryTrackHistory,
) {
  const aircraft = points.filter((point) => point.category === "military" && point.source === "ADS-B");
  const anomalies: GlobalIntelEvent[] = [];
  const assignedPointIds = new Set<string>();
  const trackFindings = analyzeMilitaryTracks(trackHistory, snapshot, fallbackTimestamp);
  const findingsByCallsign = new Map(trackFindings.map((finding) => [finding.callsign.trim().toUpperCase(), finding]));

  for (const point of aircraft.filter((item) => item.severity === "critical" || item.severity === "high")) {
    anomalies.push({
      ...eventFromPoint(point, fallbackTimestamp),
      id: stableId("military-emergency", point.id, point.timestamp),
      title: `${point.title} ADS-B 紧急状态`,
      detail: "检测到紧急或特殊应答码，需要人工核验飞行状态。",
      recordKind: "event",
    });
    assignedPointIds.add(point.id);
    findingsByCallsign.delete(point.title.trim().toUpperCase());
  }

  const sensitiveRadiusKm = 180;
  for (const node of sensitiveMilitaryNodes(snapshot)) {
    const nearby = aircraft
      .filter((point) => !assignedPointIds.has(point.id))
      .map((point) => ({ point, distanceKm: coordinateDistanceKm(point, node) }))
      .filter((item) => item.distanceKm <= sensitiveRadiusKm)
      .sort((left, right) => left.distanceKm - right.distanceKm);
    if (!nearby.length) continue;
    const primary = nearby[0]!.point;
    const callsigns = nearby.map((item) => item.point.title).slice(0, 6);
    const relatedFindings = nearby
      .map((item) => findingsByCallsign.get(item.point.title.trim().toUpperCase()))
      .filter((finding): finding is MilitaryTrackFinding => Boolean(finding));
    anomalies.push({
      id: stableId("military-sensitive", node.name, ...nearby.map((item) => item.point.id)),
      category: "military",
      title: nearby.length === 1
        ? `${primary.title} 接近 ${node.name}`
        : `${nearby.length} 架军机在 ${node.name} 附近集结`,
      detail: `${callsigns.join("、")} · 最近约 ${Math.round(nearby[0]!.distanceKm)} km${relatedFindings.length ? ` · ${relatedFindings.map((finding) => finding.label).join("、")}` : ""}`,
      source: "ADS-B 异常规则",
      severity: nearby.length >= 3 ? "high" : "medium",
      timestamp: primary.timestamp ?? fallbackTimestamp,
      pointId: primary.id,
      ...(primary.country ? { country: primary.country } : {}),
      ...(primary.countryCode ? { countryCode: primary.countryCode } : {}),
      recordKind: "event",
    });
    for (const item of nearby) assignedPointIds.add(item.point.id);
    for (const finding of relatedFindings) findingsByCallsign.delete(finding.callsign.trim().toUpperCase());
  }

  const clusterCandidates = aircraft.filter((point) => !assignedPointIds.has(point.id));
  for (const group of nearbyPointGroups(clusterCandidates, 140).filter((items) => items.length >= 3)) {
    const primary = group[0]!;
    const relatedFindings = group
      .map((point) => findingsByCallsign.get(point.title.trim().toUpperCase()))
      .filter((finding): finding is MilitaryTrackFinding => Boolean(finding));
    anomalies.push({
      id: stableId("military-cluster", ...group.map((point) => point.id)),
      category: "military",
      title: `${group.length} 架军机出现区域性集结`,
      detail: relatedFindings.length
        ? `${group.map((point) => point.title).slice(0, 6).join("、")} · ${relatedFindings.map((finding) => finding.label).join("、")}`
        : `${group.map((point) => point.title).slice(0, 6).join("、")} · 仅基于当前点位密度，尚无轨迹判断`,
      source: "ADS-B 异常规则",
      severity: group.length >= 5 ? "high" : "medium",
      timestamp: primary.timestamp ?? fallbackTimestamp,
      pointId: primary.id,
      ...(primary.country ? { country: primary.country } : {}),
      ...(primary.countryCode ? { countryCode: primary.countryCode } : {}),
      recordKind: "event",
    });
    for (const finding of relatedFindings) findingsByCallsign.delete(finding.callsign.trim().toUpperCase());
  }

  for (const finding of findingsByCallsign.values()) {
    const point = aircraft.find((item) => item.title.trim().toUpperCase() === finding.callsign.trim().toUpperCase());
    anomalies.push({
      id: stableId("military-track", finding.aircraftId, finding.kind, finding.node),
      category: "military",
      title: finding.kind === "disappeared"
        ? `${finding.callsign} ${finding.label}`
        : `${finding.callsign} 航迹异常`,
      detail: `${finding.label} · ${finding.detail}`,
      source: "ADS-B 航迹规则",
      severity: finding.severity,
      timestamp: finding.sample.observedAt,
      ...(point ? { pointId: point.id } : {}),
      recordKind: "event",
    });
  }

  const observations = aircraft.map((point) => ({
    ...eventFromPoint(point, fallbackTimestamp),
    severity: point.severity === "critical" || point.severity === "high" ? point.severity : "info" as const,
    recordKind: "observation" as const,
  }));
  return [...anomalies, ...observations];
}

function normalizedMarketNumber(value: number | undefined) {
  if (value === undefined) return "—";
  return Intl.NumberFormat("en-US", {
    maximumFractionDigits: Math.abs(value) < 1 ? 4 : 2,
  }).format(value);
}

function normalizeMonitorSignalEvents(
  snapshot: Record<string, unknown>,
  fallbackTimestamp: string,
): GlobalIntelEvent[] {
  const events: GlobalIntelEvent[] = [];

  const cryptoDomain = objectValue(snapshot.crypto_quotes);
  const cryptoTimestamp = isoTimestamp(cryptoDomain.timestamp, fallbackTimestamp);
  for (const item of domainRecords(snapshot, "crypto_quotes", "coins")
    .filter((coin) => Math.abs(numberValue(coin, "price_change_percentage_24h") ?? 0) >= 5)
    .sort((left, right) => (
      Math.abs(numberValue(right, "price_change_percentage_24h") ?? 0)
      - Math.abs(numberValue(left, "price_change_percentage_24h") ?? 0)
    ))
    .slice(0, 8)) {
    const change = numberValue(item, "price_change_percentage_24h");
    if (change === undefined) continue;
    const name = stringValue(item, "name") || stringValue(item, "symbol").toUpperCase() || "加密资产";
    const symbol = stringValue(item, "symbol").toUpperCase();
    const price = numberValue(item, "current_price");
    events.push({
      id: stableId("crypto-move", stringValue(item, "id", "symbol"), cryptoTimestamp),
      category: "market",
      title: name + (symbol ? "（" + symbol + "）" : "") + " 24小时" + (change >= 0 ? "上涨 " : "下跌 ") + Math.abs(change).toFixed(2) + "%",
      detail: "最新价格 $" + normalizedMarketNumber(price) + " · 市值 " + compactNumber(numberValue(item, "market_cap") ?? 0),
      source: "CoinGecko",
      severity: Math.abs(change) >= 10 ? "high" : "medium",
      timestamp: cryptoTimestamp,
      facts: eventFacts([
        ["24小时涨跌", change.toFixed(2) + "%"],
        ["最新价格", "$" + normalizedMarketNumber(price)],
        ["市值", compactNumber(numberValue(item, "market_cap") ?? 0)],
      ]),
    });
  }

  const stablecoinDomain = objectValue(snapshot.stablecoin_status);
  const stablecoinTimestamp = isoTimestamp(stablecoinDomain.timestamp, fallbackTimestamp);
  for (const item of domainRecords(snapshot, "stablecoin_status", "stablecoins")
    .filter((coin) => coin.is_depegged === true)) {
    const deviation = numberValue(item, "peg_deviation_pct") ?? 0;
    const name = stringValue(item, "id").replace(/-/g, " ") || "稳定币";
    events.push({
      id: stableId("stablecoin-depeg", name, stablecoinTimestamp),
      category: "market",
      title: name + " 出现脱锚",
      detail: "现价 $" + normalizedMarketNumber(numberValue(item, "price")) + " · 偏离美元锚定 " + deviation.toFixed(2) + "%",
      source: "CoinGecko 稳定币监测",
      severity: deviation >= 5 ? "critical" : deviation >= 2 ? "high" : "medium",
      timestamp: stablecoinTimestamp,
      facts: eventFacts([
        ["当前价格", "$" + normalizedMarketNumber(numberValue(item, "price"))],
        ["锚定偏离", deviation.toFixed(2) + "%"],
      ]),
    });
  }

  const sectorDomain = objectValue(snapshot.sector_heatmap);
  const sectorTimestamp = isoTimestamp(sectorDomain.timestamp, fallbackTimestamp);
  for (const item of domainRecords(snapshot, "sector_heatmap", "sectors")
    .filter((sector) => Math.abs(numberValue(sector, "change_pct") ?? 0) >= 2)
    .sort((left, right) => (
      Math.abs(numberValue(right, "change_pct") ?? 0) - Math.abs(numberValue(left, "change_pct") ?? 0)
    ))
    .slice(0, 6)) {
    const change = numberValue(item, "change_pct");
    if (change === undefined) continue;
    const name = stringValue(item, "name") || stringValue(item, "symbol") || "行业";
    events.push({
      id: stableId("sector-move", stringValue(item, "symbol"), sectorTimestamp),
      category: "market",
      title: name + (change >= 0 ? " 领涨 " : " 领跌 ") + Math.abs(change).toFixed(2) + "%",
      detail: stringValue(item, "symbol") + " · 最新价格 $" + normalizedMarketNumber(numberValue(item, "price")),
      source: "Yahoo Finance 行业热力",
      severity: Math.abs(change) >= 4 ? "high" : "medium",
      timestamp: sectorTimestamp,
      facts: eventFacts([
        ["行业ETF", stringValue(item, "symbol")],
        ["涨跌幅", change.toFixed(2) + "%"],
        ["最新价格", "$" + normalizedMarketNumber(numberValue(item, "price"))],
      ]),
    });
  }

  const commodityDomain = objectValue(snapshot.commodity_quotes);
  const commodityTimestamp = isoTimestamp(commodityDomain.timestamp, fallbackTimestamp);
  for (const item of domainRecords(snapshot, "commodity_quotes", "commodities")
    .filter((commodity) => Math.abs(numberValue(commodity, "change_pct") ?? 0) >= 2)
    .sort((left, right) => (
      Math.abs(numberValue(right, "change_pct") ?? 0) - Math.abs(numberValue(left, "change_pct") ?? 0)
    ))
    .slice(0, 6)) {
    const change = numberValue(item, "change_pct");
    if (change === undefined) continue;
    const name = stringValue(item, "name") || stringValue(item, "symbol") || "大宗商品";
    events.push({
      id: stableId("commodity-move", stringValue(item, "symbol"), commodityTimestamp),
      category: "market",
      title: name + (change >= 0 ? " 上涨 " : " 下跌 ") + Math.abs(change).toFixed(2) + "%",
      detail: stringValue(item, "symbol") + " · 最新价格 $" + normalizedMarketNumber(numberValue(item, "price")),
      source: "Yahoo Finance 大宗商品",
      severity: Math.abs(change) >= 4 ? "high" : "medium",
      timestamp: commodityTimestamp,
      facts: eventFacts([
        ["合约", stringValue(item, "symbol")],
        ["涨跌幅", change.toFixed(2) + "%"],
        ["最新价格", "$" + normalizedMarketNumber(numberValue(item, "price"))],
      ]),
    });
  }

  const etfDomain = objectValue(snapshot.etf_flows);
  const etfTimestamp = isoTimestamp(etfDomain.timestamp, fallbackTimestamp);
  for (const item of domainRecords(snapshot, "etf_flows", "etfs")
    .filter((etf) => Math.abs(numberValue(etf, "change_pct") ?? 0) >= 3)
    .sort((left, right) => (
      Math.abs(numberValue(right, "change_pct") ?? 0) - Math.abs(numberValue(left, "change_pct") ?? 0)
    ))
    .slice(0, 5)) {
    const change = numberValue(item, "change_pct");
    if (change === undefined) continue;
    const symbol = stringValue(item, "symbol") || "BTC ETF";
    events.push({
      id: stableId("btc-etf-move", symbol, etfTimestamp),
      category: "market",
      title: symbol + (change >= 0 ? " 上涨 " : " 下跌 ") + Math.abs(change).toFixed(2) + "%",
      detail: "比特币现货 ETF 显著波动 · 成交量 " + compactNumber(numberValue(item, "volume") ?? 0),
      source: "Yahoo Finance ETF",
      severity: Math.abs(change) >= 6 ? "high" : "medium",
      timestamp: etfTimestamp,
      facts: eventFacts([
        ["最新价格", "$" + normalizedMarketNumber(numberValue(item, "price"))],
        ["涨跌幅", change.toFixed(2) + "%"],
        ["成交量", compactNumber(numberValue(item, "volume") ?? 0)],
      ]),
    });
  }

  const macroDomain = objectValue(snapshot.macro_signals);
  const macroTimestamp = isoTimestamp(macroDomain.timestamp, fallbackTimestamp);
  const macroSignals = objectValue(macroDomain.signals);
  const fearGreed = objectValue(macroSignals.fear_greed);
  const fearGreedValue = numberValue(fearGreed, "value");
  if (fearGreedValue !== undefined && (fearGreedValue <= 20 || fearGreedValue >= 80)) {
    events.push({
      id: stableId("fear-greed", macroTimestamp, fearGreedValue),
      category: "market",
      title: "加密市场进入极度" + (fearGreedValue <= 20 ? "恐惧" : "贪婪"),
      detail: "恐惧与贪婪指数 " + fearGreedValue.toFixed(0) + " · " + (stringValue(fearGreed, "classification") || "极端区间"),
      source: "Alternative.me",
      severity: fearGreedValue <= 10 || fearGreedValue >= 90 ? "high" : "medium",
      timestamp: macroTimestamp,
      facts: eventFacts([["指数值", fearGreedValue], ["状态", stringValue(fearGreed, "classification")]]),
    });
  }

  const vix = objectValue(macroSignals.vix);
  const vixPrice = numberValue(vix, "price");
  const vixChange = numberValue(vix, "change_pct") ?? 0;
  if (vixPrice !== undefined && (vixPrice >= 25 || Math.abs(vixChange) >= 10)) {
    events.push({
      id: stableId("vix-alert", macroTimestamp, vixPrice, vixChange),
      category: "market",
      title: "VIX 波动率风险升高",
      detail: "VIX " + vixPrice.toFixed(2) + " · 当日" + (vixChange >= 0 ? "上涨 " : "下跌 ") + Math.abs(vixChange).toFixed(2) + "%",
      source: "Yahoo Finance 宏观信号",
      severity: vixPrice >= 35 || Math.abs(vixChange) >= 20 ? "high" : "medium",
      timestamp: macroTimestamp,
      facts: eventFacts([["VIX", vixPrice], ["当日涨跌", vixChange.toFixed(2) + "%"]]),
    });
  }

  const macroMoves = [
    { key: "dxy", label: "美元指数", threshold: 0.75 },
    { key: "gold", label: "黄金", threshold: 1.5 },
    { key: "treasury_10y", label: "美国10年期收益率", threshold: 3 },
  ];
  for (const spec of macroMoves) {
    const signal = objectValue(macroSignals[spec.key]);
    const change = numberValue(signal, "change_pct");
    if (change === undefined || Math.abs(change) < spec.threshold) continue;
    events.push({
      id: stableId("macro-move", spec.key, macroTimestamp),
      category: "market",
      title: spec.label + (change >= 0 ? " 上行 " : " 下行 ") + Math.abs(change).toFixed(2) + "%",
      detail: "最新值 " + normalizedMarketNumber(numberValue(signal, "price")) + " · 宏观资产出现显著日内变化",
      source: "Yahoo Finance 宏观信号",
      severity: Math.abs(change) >= spec.threshold * 2 ? "high" : "medium",
      timestamp: macroTimestamp,
      facts: eventFacts([
        ["最新值", normalizedMarketNumber(numberValue(signal, "price"))],
        ["当日变化", change.toFixed(2) + "%"],
      ]),
    });
  }

  const mempool = objectValue(macroSignals.mempool_fees);
  const fastestFee = numberValue(mempool, "fastest_fee");
  if (fastestFee !== undefined && fastestFee >= 100) {
    events.push({
      id: stableId("btc-fee", macroTimestamp, fastestFee),
      category: "technology",
      title: "比特币链上手续费显著升高",
      detail: "最快确认 " + fastestFee.toFixed(0) + " sat/vB · 网络拥堵加剧",
      source: "Mempool.space",
      severity: fastestFee >= 250 ? "high" : "medium",
      timestamp: macroTimestamp,
      facts: eventFacts([
        ["最快确认", fastestFee + " sat/vB"],
        ["半小时", numberValue(mempool, "half_hour_fee") === undefined ? "" : numberValue(mempool, "half_hour_fee") + " sat/vB"],
        ["一小时", numberValue(mempool, "hour_fee") === undefined ? "" : numberValue(mempool, "hour_fee") + " sat/vB"],
      ]),
    });
  }

  const btcDomain = objectValue(snapshot.btc_technicals);
  const btcTimestamp = isoTimestamp(btcDomain.timestamp, fallbackTimestamp);
  const crossSignal = stringValue(btcDomain, "cross_signal");
  const btcChange7d = numberValue(btcDomain, "change_7d_pct") ?? 0;
  const btcChange30d = numberValue(btcDomain, "change_30d_pct") ?? 0;
  const mayer = numberValue(btcDomain, "mayer_multiple");
  if (crossSignal === "golden_cross" || crossSignal === "death_cross"
    || Math.abs(btcChange7d) >= 10 || Math.abs(btcChange30d) >= 20
    || (mayer !== undefined && (mayer >= 2.4 || mayer <= 0.8))) {
    const crossLabel = crossSignal === "golden_cross" ? "黄金交叉" : crossSignal === "death_cross" ? "死亡交叉" : "大幅波动";
    events.push({
      id: stableId("btc-technicals", btcTimestamp, crossSignal, btcChange7d, btcChange30d),
      category: "market",
      title: "BTC 技术信号 · " + crossLabel,
      detail: "7日 " + btcChange7d.toFixed(2) + "% · 30日 " + btcChange30d.toFixed(2) + "% · 距阶段高点 " + (numberValue(btcDomain, "ath_distance_pct") ?? 0).toFixed(2) + "%",
      source: "CoinGecko 技术指标",
      severity: crossSignal === "death_cross" || Math.abs(btcChange7d) >= 15 ? "high" : "medium",
      timestamp: btcTimestamp,
      facts: eventFacts([
        ["当前价格", "$" + normalizedMarketNumber(numberValue(btcDomain, "price"))],
        ["SMA 50", normalizedMarketNumber(numberValue(btcDomain, "sma_50"))],
        ["SMA 200", normalizedMarketNumber(numberValue(btcDomain, "sma_200"))],
        ["Mayer Multiple", mayer],
      ]),
    });
  }

  const energyDomain = objectValue(snapshot.energy_prices);
  const oil = objectValue(energyDomain.oil);
  const brent = objectValue(oil.brent);
  const wti = objectValue(oil.wti);
  const naturalGas = objectValue(energyDomain.natural_gas);
  if (numberValue(brent, "price") !== undefined || numberValue(wti, "price") !== undefined || numberValue(naturalGas, "price") !== undefined) {
    const energyTimestamp = isoTimestamp(energyDomain.fetched_at, fallbackTimestamp);
    events.push({
      id: stableId("energy-benchmark", energyTimestamp),
      category: "market",
      title: "全球能源基准价格更新",
      detail: "Brent $" + normalizedMarketNumber(numberValue(brent, "price")) + " · WTI $" + normalizedMarketNumber(numberValue(wti, "price")) + " · 天然气 $" + normalizedMarketNumber(numberValue(naturalGas, "price")),
      source: "EIA",
      severity: "info",
      timestamp: energyTimestamp,
      facts: eventFacts([
        ["Brent", "$" + normalizedMarketNumber(numberValue(brent, "price"))],
        ["WTI", "$" + normalizedMarketNumber(numberValue(wti, "price"))],
        ["天然气", "$" + normalizedMarketNumber(numberValue(naturalGas, "price"))],
        ["数据日期", stringValue(brent, "date") || stringValue(wti, "date")],
      ]),
    });
  }

  const residentialGasDomain = objectValue(snapshot.residential_natgas);
  const residentialGasTimestamp = isoTimestamp(residentialGasDomain.fetched_at, fallbackTimestamp);
  const residentialGas = domainRecords(snapshot, "residential_natgas", "prices")[0];
  const residentialGasChange = residentialGas ? numberValue(residentialGas, "change_pct") : undefined;
  if (residentialGas && residentialGasChange !== undefined && Math.abs(residentialGasChange) >= 8) {
    events.push({
      id: stableId("residential-natgas", residentialGasTimestamp, residentialGasChange),
      category: "market",
      title: "美国居民天然气价格" + (residentialGasChange >= 0 ? "上涨 " : "下跌 ") + Math.abs(residentialGasChange).toFixed(2) + "%",
      detail: "$" + normalizedMarketNumber(numberValue(residentialGas, "price")) + "/千立方英尺 · 月度价格变化",
      source: "EIA 居民天然气",
      severity: Math.abs(residentialGasChange) >= 15 ? "high" : "medium",
      timestamp: residentialGasTimestamp,
      country: "United States",
      countryCode: "USA",
      facts: eventFacts([
        ["当前价格", "$" + normalizedMarketNumber(numberValue(residentialGas, "price")) + "/千立方英尺"],
        ["月度变化", residentialGasChange.toFixed(2) + "%"],
        ["统计期", stringValue(residentialGas, "period")],
      ]),
    });
  }

  const gasDomain = objectValue(snapshot.gas_prices);
  const gasTimestamp = isoTimestamp(gasDomain.fetched_at, fallbackTimestamp);
  const gasPrices = objectValue(gasDomain.prices);
  for (const grade of [{ key: "regular", label: "美国普通汽油" }, { key: "diesel", label: "美国柴油" }]) {
    const quote = objectValue(gasPrices[grade.key]);
    const dayChange = numberValue(quote, "change_pct") ?? 0;
    const weekChange = numberValue(quote, "week_ago_pct") ?? 0;
    const monthChange = numberValue(quote, "month_ago_pct") ?? 0;
    const yearChange = numberValue(quote, "year_ago_pct") ?? 0;
    if (Math.abs(dayChange) < 2 && Math.abs(weekChange) < 8 && Math.abs(monthChange) < 12 && Math.abs(yearChange) < 20) continue;
    const primaryChange = Math.abs(dayChange) >= 2
      ? dayChange
      : Math.abs(weekChange) >= 8
        ? weekChange
        : Math.abs(monthChange) >= 12
          ? monthChange
          : yearChange;
    events.push({
      id: stableId("fuel-price", grade.key, gasTimestamp),
      category: "market",
      title: grade.label + "价格" + (primaryChange >= 0 ? "上涨" : "下跌"),
      detail: "$" + normalizedMarketNumber(numberValue(quote, "price_per_gallon")) + "/加仑 · 日 " + dayChange.toFixed(2) + "% · 周 " + weekChange.toFixed(2) + "%",
      source: "AAA",
      severity: Math.abs(primaryChange) >= 15 ? "high" : "medium",
      timestamp: gasTimestamp,
      country: "United States",
      countryCode: "USA",
      facts: eventFacts([
        ["当前均价", "$" + normalizedMarketNumber(numberValue(quote, "price_per_gallon")) + "/加仑"],
        ["日变化", dayChange.toFixed(2) + "%"],
        ["周变化", weekChange.toFixed(2) + "%"],
        ["月变化", monthChange.toFixed(2) + "%"],
        ["年变化", yearChange.toFixed(2) + "%"],
      ]),
    });
  }

  const electricityDomain = objectValue(snapshot.electricity_rates);
  const electricityTimestamp = isoTimestamp(electricityDomain.fetched_at, fallbackTimestamp);
  const electricityRates = objectValue(electricityDomain.rates);
  const electricityLabels: Record<string, string> = {
    residential: "居民",
    commercial: "商业",
    industrial: "工业",
    all_sectors: "综合",
  };
  for (const [sector, raw] of Object.entries(electricityRates)) {
    const rate = objectValue(raw);
    const change = numberValue(rate, "change_pct");
    if (change === undefined || Math.abs(change) < 5) continue;
    events.push({
      id: stableId("electricity-rate", sector, electricityTimestamp),
      category: "market",
      title: "美国" + (electricityLabels[sector] ?? sector) + "电价" + (change >= 0 ? "上涨 " : "下跌 ") + Math.abs(change).toFixed(2) + "%",
      detail: normalizedMarketNumber(numberValue(rate, "price_cents_kwh")) + " 美分/kWh · 月度价格变化",
      source: "EIA 电力价格",
      severity: Math.abs(change) >= 10 ? "high" : "medium",
      timestamp: electricityTimestamp,
      country: "United States",
      countryCode: "USA",
      facts: eventFacts([
        ["当前电价", normalizedMarketNumber(numberValue(rate, "price_cents_kwh")) + " 美分/kWh"],
        ["月度变化", change.toFixed(2) + "%"],
        ["统计期", stringValue(rate, "period")],
      ]),
    });
  }

  const shippingDomain = objectValue(snapshot.shipping_index);
  const shippingStress = numberValue(shippingDomain, "stress_score");
  if (shippingStress !== undefined && shippingStress >= 15) {
    const shippingTimestamp = isoTimestamp(shippingDomain.timestamp, fallbackTimestamp);
    const quotes = domainRecords(snapshot, "shipping_index", "quotes");
    events.push({
      id: stableId("shipping-stress", shippingTimestamp, shippingStress),
      category: "maritime",
      title: "全球航运市场压力升高",
      detail: "压力指数 " + shippingStress.toFixed(1) + "/100 · " + (stringValue(shippingDomain, "assessment") || "elevated"),
      source: "Yahoo Finance 航运指数",
      severity: shippingStress >= 50 ? "high" : "medium",
      timestamp: shippingTimestamp,
      facts: eventFacts([
        ["压力指数", shippingStress.toFixed(1)],
        ["评估", stringValue(shippingDomain, "assessment")],
        ["异常信号", stringList(shippingDomain.signals).join("、")],
      ]),
      content: quotes.map((quote) => {
        const change = numberValue(quote, "change_pct");
        return (stringValue(quote, "symbol", "name") || "航运资产") + " " + (change === undefined ? "—" : change.toFixed(2) + "%");
      }).join(" · "),
    });
  }

  const riskDomain = objectValue(snapshot.risk_scores);
  const riskTimestamp = isoTimestamp(riskDomain.timestamp, fallbackTimestamp);
  for (const item of domainRecords(snapshot, "risk_scores", "countries")
    .filter((country) => (numberValue(country, "risk_score") ?? 0) >= 150)
    .slice(0, 10)) {
    const country = stringValue(item, "country") || "未知国家";
    const riskScore = numberValue(item, "risk_score") ?? 0;
    const normalizedCode = countryCode(item, country);
    events.push({
      id: stableId("country-risk", country, riskTimestamp),
      category: "conflict",
      title: country + " 冲突活动高于历史基线",
      detail: "近30日 " + (numberValue(item, "events_30d") ?? 0).toFixed(0) + " 起 · 基线比 " + riskScore.toFixed(1) + "%",
      source: "ACLED 国家风险",
      severity: riskScore >= 250 ? "high" : "medium",
      timestamp: riskTimestamp,
      country,
      ...(normalizedCode ? { countryCode: normalizedCode } : {}),
      facts: eventFacts([
        ["近30日事件", numberValue(item, "events_30d")],
        ["月度基线", numberValue(item, "monthly_baseline")],
        ["基线比", riskScore.toFixed(1) + "%"],
        ["风险级别", stringValue(item, "risk_level")],
      ]),
    });
  }

  const usniDomain = objectValue(snapshot.usni_fleet);
  const reportTitle = plainText(stringValue(usniDomain, "report_title"));
  if (reportTitle) {
    const ships = listValue(usniDomain.ships);
    const strikeGroups = listValue(usniDomain.strike_groups);
    const forceTotals = objectValue(usniDomain.force_totals);
    const battleForce = objectValue(forceTotals.battle_force);
    const deployed = objectValue(forceTotals.deployed);
    const underway = objectValue(forceTotals.underway);
    const regions = objectValue(usniDomain.region_breakdown);
    const reportTimestamp = isoTimestamp(usniDomain.report_date, isoTimestamp(usniDomain.timestamp, fallbackTimestamp));
    const reportUrl = stringValue(usniDomain, "report_url");
    const regionSummary = Object.entries(regions)
      .map(([region, count]) => region + " " + String(count))
      .join(" · ");
    events.push({
      id: stableId("usni-fleet", reportTitle, reportTimestamp),
      category: "military",
      title: reportTitle,
      detail: (numberValue(usniDomain, "ship_count") ?? ships.length) + " 艘舰艇已识别 · " + strikeGroups.length + " 个打击/远征群",
      source: "USNI Fleet Tracker",
      severity: "medium",
      timestamp: reportTimestamp,
      facts: eventFacts([
        ["战斗舰艇总数", numberValue(battleForce, "total")],
        ["海外部署", numberValue(deployed, "total")],
        ["航行中", numberValue(underway, "total")],
        ["区域分布", regionSummary],
      ]),
      content: ships.slice(0, 16).map((ship) => (
        stringValue(ship, "name") + "（" + stringValue(ship, "hull_number") + "）"
        + (stringValue(ship, "region") ? " · " + stringValue(ship, "region") : "")
      )).join("；"),
      ...(reportUrl ? { url: reportUrl } : {}),
      recordKind: "news",
    });
  }

  return events;
}

function normalizeAnalysisLayerEvents(
  snapshot: Record<string, unknown>,
  fallbackTimestamp: string,
): GlobalIntelEvent[] {
  const events: GlobalIntelEvent[] = [];
  const categoryForDomain = (domain: string): GlobalIntelCategory => ({
    military: "military",
    political: "policy",
    security: "conflict",
    conflict: "conflict",
    infrastructure: "infrastructure",
    economic: "market",
    cyber: "cyber",
    health: "health",
    climate: "climate",
    space: "space",
  } as Record<string, GlobalIntelCategory>)[domain] ?? "news";
  const alertSummary = (alert: Record<string, unknown>) => {
    const domain = stringValue(alert, "domain");
    const value = numberValue(alert, "value") ?? 0;
    if (listValue(alert.countries).length || stringList(alert.countries).length) return value + " 个国家不稳定风险超过阈值";
    if (listValue(alert.surges).length) return "发现 " + value + " 项军事活动激增";
    if (stringList(alert.corridors).length) return value + " 条海底光缆走廊风险升高";
    if (stringList(alert.hotspots).length) return value + " 个安全热点进入升级区间";
    if (domain === "space") return "地磁活动升高，当前 Kp=" + value;
    if (domain === "infrastructure") return value + " 起网络基础设施中断正在持续";
    if (domain === "economic") return "航运压力指数升至 " + value;
    return plainText(stringValue(alert, "message")) || "发现新的跨域风险信号";
  };

  const digestDomain = objectValue(snapshot.alert_digest);
  const digestAlerts = domainRecords(snapshot, "alert_digest", "alerts");
  if (digestAlerts.length) {
    const priorityRank: Record<string, number> = { critical: 4, high: 3, medium: 2, low: 1 };
    const topAlert = [...digestAlerts].sort((left, right) => (
      (priorityRank[stringValue(right, "priority")] ?? 0) - (priorityRank[stringValue(left, "priority")] ?? 0)
    ))[0]!;
    const topPriority = stringValue(topAlert, "priority");
    const priorityCounts = objectValue(digestDomain.by_priority);
    events.push({
      id: stableId("alert-digest", isoTimestamp(digestDomain.timestamp, fallbackTimestamp), digestAlerts.length),
      category: categoryForDomain(stringValue(topAlert, "domain")),
      title: "全球综合预警 · " + digestAlerts.length + " 项",
      detail: alertSummary(topAlert),
      source: "World Intel 综合预警",
      severity: severityValue(topPriority, "medium"),
      timestamp: isoTimestamp(digestDomain.timestamp, fallbackTimestamp),
      facts: eventFacts([
        ["严重", numberValue(priorityCounts, "critical")],
        ["高优先级", numberValue(priorityCounts, "high")],
        ["中优先级", numberValue(priorityCounts, "medium")],
        ["已检查领域", stringList(digestDomain.domains_checked).length],
      ]),
      content: digestAlerts.map((alert) => alertSummary(alert)).join("；"),
    });
  }

  const weeklyDomain = objectValue(snapshot.weekly_trends);
  const weeklyTimestamp = isoTimestamp(weeklyDomain.timestamp, fallbackTimestamp);
  for (const item of domainRecords(snapshot, "weekly_trends", "current_anomalies").slice(0, 10)) {
    const metric = stringValue(item, "event_type", "metric") || "监测指标";
    const region = stringValue(item, "region") || "global";
    const zScore = numberValue(item, "z_score", "deviation") ?? 0;
    const multiplier = numberValue(item, "multiplier") ?? 0;
    events.push({
      id: stableId("temporal-anomaly", metric, region, weeklyTimestamp),
      category: metric.includes("military") || metric.includes("aircraft") ? "military" : metric.includes("acled") ? "conflict" : "news",
      title: analysisLabel(region) + " " + analysisLabel(metric) + "偏离历史基线",
      detail: "当前 " + (numberValue(item, "observed") ?? 0) + " · 常态 " + (numberValue(item, "expected") ?? 0) + " · " + multiplier.toFixed(1) + " 倍",
      source: "World Intel 历史基线",
      severity: severityValue(item.severity, zScore >= 3 ? "high" : "medium"),
      timestamp: weeklyTimestamp,
      facts: eventFacts([
        ["Z分数", zScore.toFixed(2)],
        ["偏离倍数", multiplier.toFixed(1) + "x"],
        ["当前观测", numberValue(item, "observed")],
        ["历史预期", numberValue(item, "expected")],
      ]),
    });
  }

  const briefDomain = objectValue(snapshot.situation_brief);
  const brief = typeof briefDomain.brief === "string" ? briefDomain.brief.trim() : "";
  if (brief) {
    const metrics = objectValue(briefDomain.metrics_snapshot);
    const postureScore = numberValue(metrics, "posture_score") ?? 0;
    const riskLevel = stringValue(metrics, "risk_level").toUpperCase();
    const riskLabels: Record<string, string> = {
      LOW: "低风险",
      GUARDED: "警戒",
      ELEVATED: "风险升高",
      HIGH: "高风险",
      CRITICAL: "严重风险",
    };
    events.push({
      id: stableId("situation-brief", isoTimestamp(briefDomain.timestamp, fallbackTimestamp)),
      category: "news",
      title: "全球综合态势 · " + (riskLabels[riskLevel] ?? "持续监测"),
      detail: plainText(brief).slice(0, 180),
      source: "World Intel 态势简报",
      severity: postureScore >= 80 ? "critical" : postureScore >= 60 ? "high" : postureScore >= 35 ? "medium" : "info",
      timestamp: isoTimestamp(briefDomain.timestamp, fallbackTimestamp),
      facts: eventFacts([
        ["综合评分", postureScore + "/100"],
        ["活跃告警", numberValue(metrics, "alerts")],
        ["军事航空器", numberValue(metrics, "military_aircraft")],
        ["冲突事件", numberValue(metrics, "conflicts")],
        ["地震", numberValue(metrics, "earthquakes")],
        ["网络威胁", numberValue(metrics, "cyber_threats")],
      ]),
      content: brief,
    });
  }

  const keywordDomain = objectValue(snapshot.trending_keywords);
  const keywords = domainRecords(snapshot, "trending_keywords", "keywords");
  if (keywords.length) {
    const topKeywords = keywords.slice(0, 5);
    const topCount = numberValue(topKeywords[0] ?? {}, "count") ?? 0;
    events.push({
      id: stableId("news-trends", isoTimestamp(keywordDomain.timestamp, fallbackTimestamp), topKeywords.map((item) => stringValue(item, "word")).join("-")),
      category: "news",
      title: "全球新闻热词 · " + topKeywords.map((item) => stringValue(item, "word")).filter(Boolean).join(" / "),
      detail: "基于 " + (numberValue(keywordDomain, "total_items_analyzed") ?? 0) + " 条近期新闻标题统计",
      source: "World Intel 新闻趋势",
      severity: topCount >= 10 ? "medium" : "info",
      timestamp: isoTimestamp(keywordDomain.timestamp, fallbackTimestamp),
      facts: topKeywords.map((item) => ({
        label: stringValue(item, "word"),
        value: String(numberValue(item, "count") ?? 0) + " 次",
      })),
      content: keywords.slice(0, 20).map((item) => (
        stringValue(item, "word") + " " + (numberValue(item, "count") ?? 0) + "次"
      )).join(" · "),
      recordKind: "news",
    });
  }

  const flightsDomain = objectValue(snapshot.domestic_flights);
  const totalAircraft = numberValue(flightsDomain, "total_aircraft");
  if (totalAircraft !== undefined && totalAircraft > 0) {
    const regions = Object.entries(objectValue(flightsDomain.by_region))
      .map(([region, raw]) => {
        const info = objectValue(raw);
        return {
          region,
          count: numberValue(info, "count") ?? 0,
          commercial: numberValue(info, "commercial") ?? 0,
        };
      })
      .sort((left, right) => right.count - left.count);
    const busiest = domainRecords(snapshot, "domestic_flights", "busiest_origins");
    events.push({
      id: stableId("global-air-traffic", isoTimestamp(flightsDomain.timestamp, fallbackTimestamp)),
      category: "aviation",
      title: "全球在途航空器 " + compactNumber(totalAircraft) + " 架",
      detail: regions.slice(0, 3).map((region) => analysisLabel(region.region) + " " + compactNumber(region.count)).join(" · "),
      source: "OpenSky 全球航空流量",
      severity: "info",
      timestamp: isoTimestamp(flightsDomain.timestamp, fallbackTimestamp),
      facts: eventFacts([
        ["商业航班", compactNumber(regions.reduce((sum, region) => sum + region.commercial, 0))],
        ...regions.slice(0, 4).map((region) => [analysisLabel(region.region), compactNumber(region.count)] as [string, unknown]),
      ]),
      content: busiest.slice(0, 12).map((item) => (
        stringValue(item, "country") + " " + compactNumber(numberValue(item, "count") ?? 0)
      )).join(" · "),
      recordKind: "observation",
    });
  }

  return events;
}

export function normalizeGlobalIntelEvents(
  snapshot: Record<string, unknown>,
  trackHistory: GlobalIntelMilitaryTrackHistory = {},
): GlobalIntelEvent[] {
  const fallbackTimestamp = isoTimestamp(snapshot.timestamp, new Date().toISOString());
  const points = normalizeGlobalIntelPoints(snapshot);
  const events = points
    .filter((point) => (
      point.category === "conflict"
      || point.category === "disaster"
      || point.category === "maritime"
      || (point.category === "nuclear" && point.source === "USGS 核活动监测")
      || (point.category === "climate" && (point.severity === "critical" || point.severity === "high"))
      || point.source === "TomTom 交通事件"
      || (point.source === "TomTom 交通流" && point.severity === "high")
      || point.source === "World Intel 人口暴露分析"
    ))
    .map((point) => eventFromPoint(point, fallbackTimestamp));
  events.push(...normalizeMilitaryFlightEvents(points, snapshot, fallbackTimestamp, trackHistory));
  events.push(...normalizeMonitorSignalEvents(snapshot, fallbackTimestamp));
  events.push(...normalizeAnalysisLayerEvents(snapshot, fallbackTimestamp));

  for (const item of domainRecords(snapshot, "news_feed", "items")) {
    const title = stringValue(item, "title");
    if (!title) continue;
    const source = stringValue(item, "feed_name", "source") || "全球新闻源";
    const timestamp = isoTimestamp(item.published, fallbackTimestamp);
    const tier = stringValue(item, "source_tier");
    const url = stringValue(item, "link", "url");
    const content = plainText(stringValue(item, "content"));
    const annotation = findGlobalMediaMonitorAnnotation(snapshot, {
      title,
      source,
      url,
    });
    events.push({
      id: stableId("news", source, timestamp, title),
      category: "news",
      title,
      detail: plainText(stringValue(item, "summary")) || stringValue(item, "category") || "全球公开新闻",
      source,
      severity: tier === "tier1" || tier === "wire" || tier === "major" ? "medium" : "info",
      timestamp,
      ...(tier ? { sourceTier: tier } : {}),
      ...(url ? { url } : {}),
      ...(content ? { content } : {}),
      ...(annotation ? {
        facts: eventFacts([
          ["报道语气", mediaSentimentLabel(annotation.sentiment)],
          ["热度增速", mediaVelocityLabel(annotation.heatVelocityPct, annotation.velocityState)],
          ["传播范围", `${annotation.spreadScore}/100`],
          ["跨语言合并", annotation.crossLanguageTopic ? "是" : "否"],
          ["核验提示", annotation.verificationStatus],
        ]),
      } : {}),
      recordKind: "news",
    });
  }

  for (const item of domainRecords(snapshot, "central_bank_rates", "rates")) {
    const bank = stringValue(item, "bank") || "中央银行";
    const rate = numberValue(item, "rate");
    const timestamp = isoTimestamp(item.as_of, fallbackTimestamp);
    events.push({
      id: stableId("policy", bank, timestamp, rate),
      category: "policy",
      title: `${bank} 政策利率${rate === undefined ? "更新" : ` ${rate.toFixed(2)}%`}`,
      detail: [stringValue(item, "label"), stringValue(item, "currency", "country")].filter(Boolean).join(" · "),
      source: stringValue(item, "source") || "World Intel 央行利率",
      severity: "medium",
      timestamp,
      country: stringValue(item, "country"),
      ...(countryCode(item, stringValue(item, "country")) ? { countryCode: countryCode(item, stringValue(item, "country")) } : {}),
      recordKind: "observation",
    });
  }

  for (const item of domainRecords(snapshot, "election_calendar", "elections")) {
    const country = stringValue(item, "country") || "全球";
    const timestamp = isoTimestamp(item.date, fallbackTimestamp);
    const risk = numberValue(item, "risk_score") ?? 0;
    events.push({
      id: stableId("policy-election", country, timestamp),
      category: "policy",
      title: `${country} ${stringValue(item, "election_type") || "选举"}`,
      detail: stringValue(item, "description") || `事件风险评分 ${risk.toFixed(0)}`,
      source: "World Intel 选举日历",
      severity: risk >= 100 ? "high" : risk >= 50 ? "medium" : "low",
      timestamp,
      country,
      ...(countryCode(item, country) ? { countryCode: countryCode(item, country) } : {}),
    });
  }

  for (const item of domainRecords(snapshot, "market_quotes", "quotes")) {
    const symbol = stringValue(item, "symbol") || "指数";
    const change = numberValue(item, "change_pct");
    if (change === undefined) continue;
    events.push({
      id: stableId("market", symbol, fallbackTimestamp),
      category: "market",
      title: `${symbol} ${change >= 0 ? "上涨" : "下跌"} ${Math.abs(change).toFixed(2)}%`,
      detail: `最新价格 ${stringValue(item, "price") || "—"}`,
      source: "Yahoo Finance",
      severity: Math.abs(change) >= 2 ? "high" : "info",
      timestamp: fallbackTimestamp,
      recordKind: Math.abs(change) >= 2 ? "event" : "observation",
    });
  }

  const internetOutageDomain = objectValue(snapshot.internet_outages);
  for (const item of domainRecords(snapshot, "internet_outages", "outages")) {
    const countries = stringList(item.countries);
    const country = countries[0] || "全球网络";
    const timestamp = isoTimestamp(firstValue(item, ["start"]), isoTimestamp(internetOutageDomain.timestamp, fallbackTimestamp));
    const ongoing = item.is_ongoing === true;
    events.push({
      id: stableId("cyber-outage", stringValue(item, "id"), country, timestamp),
      category: "cyber",
      title: `${country} 网络中断${ongoing ? "持续中" : ""}`,
      detail: stringValue(item, "description", "scope") || `影响范围 ${countries.join("、") || "待确认"}`,
      source: stringValue(internetOutageDomain, "source") || "全球网络中断监测",
      severity: ongoing ? "high" : "medium",
      timestamp,
      ...(countries[0] ? { country: countries[0] } : {}),
    });
  }

  const healthDomain = objectValue(snapshot.disease_outbreaks);
  for (const item of domainRecords(snapshot, "disease_outbreaks", "items")) {
    const title = stringValue(item, "title");
    if (!title) continue;
    const timestamp = isoTimestamp(item.published, isoTimestamp(healthDomain.timestamp, fallbackTimestamp));
    const highConcern = item.is_high_concern === true;
    const url = stringValue(item, "link", "url");
    events.push({
      id: stableId("health", stringValue(item, "organization"), timestamp, title),
      category: "health",
      title,
      detail: plainText(stringValue(item, "summary")) || "全球公共卫生通报",
      source: stringValue(item, "organization") || "全球卫生监测",
      severity: highConcern ? "high" : "low",
      timestamp,
      ...(url ? { url } : {}),
      recordKind: "news",
    });
  }

  const cyberDomain = objectValue(snapshot.cyber_threats);
  for (const item of domainRecords(snapshot, "cyber_threats", "threats").slice(0, 25)) {
    const indicator = stringValue(item, "indicator", "ioc", "url");
    const threat = stringValue(item, "threat", "type") || "网络威胁";
    if (!indicator && !threat) continue;
    const details = objectValue(item.details);
    const timestamp = isoTimestamp(item.first_seen, isoTimestamp(cyberDomain.timestamp, fallbackTimestamp));
    const severity = severityValue(item.severity, "medium");
    const source = stringValue(item, "source_feed", "source") || "World Intel 网络威胁";
    const url = /^CVE-\d{4}-\d+$/i.test(indicator)
      ? `https://nvd.nist.gov/vuln/detail/${indicator}`
      : "";
    events.push({
      id: stableId("cyber-threat", source, indicator, timestamp),
      category: "cyber",
      title: `${threat}${indicator ? ` · ${indicator}` : ""}`,
      detail: plainText(stringValue(details, "vulnerability_name", "required_action", "notes"))
        || `${stringValue(item, "type") || "威胁指标"} · ${source}`,
      source,
      severity,
      timestamp,
      facts: eventFacts([
        ["指标类型", stringValue(item, "type")],
        ["首次发现", stringValue(item, "first_seen")],
        ["厂商/网络", stringValue(details, "vendor", "as_name")],
        ["国家", stringValue(details, "country", "as_country")],
        ["状态", stringValue(details, "status", "url_status")],
      ]),
      ...(url ? { url } : {}),
    });
  }

  const spaceDomain = objectValue(snapshot.space_weather);
  const kp = numberValue(spaceDomain, "current_kp");
  const spaceTimestamp = isoTimestamp(spaceDomain.timestamp, fallbackTimestamp);
  if (kp !== undefined || stringValue(spaceDomain, "latest_flare_class")) {
    events.push({
      id: stableId("space-weather", spaceTimestamp, kp, stringValue(spaceDomain, "latest_flare_class")),
      category: "space",
      title: `空间天气${kp === undefined ? "更新" : ` Kp ${kp.toFixed(1)}`}`,
      detail: [
        stringValue(spaceDomain, "kp_level"),
        stringValue(spaceDomain, "latest_flare_class") ? `太阳耀斑 ${stringValue(spaceDomain, "latest_flare_class")}` : "",
      ].filter(Boolean).join(" · ") || "NOAA 空间天气监测更新",
      source: "NOAA SWPC",
      severity: kp !== undefined && kp >= 7 ? "high" : kp !== undefined && kp >= 5 ? "medium" : "info",
      timestamp: spaceTimestamp,
      facts: eventFacts([
        ["Kp 等级", stringValue(spaceDomain, "kp_level")],
        ["太阳耀斑", stringValue(spaceDomain, "latest_flare_class")],
        ["太阳风", numberValue(spaceDomain, "solar_wind_speed_km_s") === undefined ? "" : `${numberValue(spaceDomain, "solar_wind_speed_km_s")} km/s`],
      ]),
      url: "https://www.swpc.noaa.gov/",
      recordKind: kp !== undefined && kp >= 5 ? "event" : "observation",
    });
  }
  for (const item of listValue(spaceDomain.alerts).slice(0, 5)) {
    const message = plainText(stringValue(item, "message"));
    if (!message) continue;
    const timestamp = isoTimestamp(item.issue_datetime, spaceTimestamp);
    events.push({
      id: stableId("space-alert", stringValue(item, "product_id"), timestamp, message),
      category: "space",
      title: `NOAA 空间天气警报 · ${stringValue(item, "product_id") || "SWPC"}`,
      detail: message,
      source: "NOAA SWPC",
      severity: /warning|severe|extreme/i.test(message) ? "high" : "medium",
      timestamp,
      url: "https://www.swpc.noaa.gov/products/alerts-watches-and-warnings",
    });
  }

  const predictionDomain = objectValue(snapshot.prediction_markets);
  for (const item of domainRecords(snapshot, "prediction_markets", "markets").slice(0, 10)) {
    const question = stringValue(item, "question", "title");
    if (!question) continue;
    const probability = numberValue(item, "yes_probability", "probability", "yes_price");
    const timestamp = isoTimestamp(predictionDomain.timestamp, fallbackTimestamp);
    const url = stringValue(item, "url");
    events.push({
      id: stableId("prediction", question, timestamp),
      category: "prediction",
      title: question,
      detail: probability === undefined ? "预测市场动态" : `市场隐含概率 ${(probability * 100).toFixed(1)}%`,
      source: "Polymarket",
      severity: (numberValue(item, "volume_24h") ?? 0) >= 1_000_000 ? "medium" : "info",
      timestamp,
      facts: eventFacts([
        ["市场情绪", stringValue(item, "sentiment")],
        ["24h 成交", compactNumber(numberValue(item, "volume_24h") ?? 0)],
        ["流动性", compactNumber(numberValue(item, "liquidity") ?? 0)],
        ["分类", stringValue(item, "category")],
      ]),
      ...(url ? { url } : {}),
      recordKind: "observation",
    });
  }

  const aiDomain = objectValue(snapshot.ai_watch);
  for (const item of domainRecords(snapshot, "ai_watch", "items").slice(0, 12)) {
    const title = plainText(stringValue(item, "title"));
    if (!title) continue;
    const timestamp = isoTimestamp(item.published, isoTimestamp(aiDomain.timestamp, fallbackTimestamp));
    const url = stringValue(item, "link", "url");
    events.push({
      id: stableId("ai-watch", stringValue(item, "feed_name"), timestamp, title),
      category: "technology",
      title,
      detail: plainText(stringValue(item, "summary")) || "全球 AI 与技术动态",
      source: stringValue(item, "feed_name") || "World Intel AI Watch",
      severity: "info",
      timestamp,
      facts: eventFacts([
        ["分类", stringValue(item, "category")],
        ["涉及机构", stringList(item.lab_mentions).join("、")],
      ]),
      ...(url ? { url } : {}),
      recordKind: "news",
    });
  }

  const airportDomain = objectValue(snapshot.airport_delays);
  for (const item of domainRecords(snapshot, "airport_delays", "delayed").slice(0, 20)) {
    const code = stringValue(item, "code") || "机场";
    const statuses = listValue(item.status);
    const primaryStatus = statuses[0] ?? {};
    const timestamp = isoTimestamp(airportDomain.timestamp, fallbackTimestamp);
    events.push({
      id: stableId("airport-delay", code, timestamp),
      category: "aviation",
      title: `${code} ${stringValue(item, "name") || "机场"}出现延误`,
      detail: [stringValue(primaryStatus, "type"), stringValue(primaryStatus, "reason"), stringValue(primaryStatus, "avg_delay")].filter(Boolean).join(" · ") || "FAA 机场运行延误",
      source: "FAA",
      severity: /closure|closed/i.test(stringValue(primaryStatus, "type")) ? "high" : "medium",
      timestamp,
      facts: eventFacts([
        ["延误类型", stringValue(primaryStatus, "type")],
        ["平均延误", stringValue(primaryStatus, "avg_delay")],
        ["关闭开始", stringValue(primaryStatus, "closure_begin")],
        ["关闭结束", stringValue(primaryStatus, "closure_end")],
      ]),
    });
  }

  const serviceDomain = objectValue(snapshot.service_status);
  for (const item of domainRecords(snapshot, "service_status", "incidents").slice(0, 20)) {
    const title = plainText(stringValue(item, "title"));
    if (!title) continue;
    const rawSeverity = stringValue(item, "severity");
    if (rawSeverity === "resolved") continue;
    const timestamp = isoTimestamp(item.published, isoTimestamp(serviceDomain.timestamp, fallbackTimestamp));
    const url = stringValue(item, "link", "url");
    events.push({
      id: stableId("service-status", stringValue(item, "provider"), timestamp, title),
      category: "infrastructure",
      title: `${stringValue(item, "provider") || "云服务"} · ${title}`,
      detail: plainText(stringValue(item, "summary")) || "全球数字基础设施状态更新",
      source: "World Intel 服务状态",
      severity: severityValue(rawSeverity, rawSeverity === "degraded" ? "medium" : "info"),
      timestamp,
      ...(url ? { url } : {}),
    });
  }

  const cableDomain = objectValue(snapshot.cable_health);
  for (const [corridor, raw] of Object.entries(objectValue(cableDomain.corridors))) {
    const item = objectValue(raw);
    const score = numberValue(item, "status_score") ?? 0;
    if (score <= 0) continue;
    const warnings = listValue(item.relevant_warnings);
    events.push({
      id: stableId("cable-health", corridor, isoTimestamp(cableDomain.timestamp, fallbackTimestamp), score),
      category: "infrastructure",
      title: `${corridor.replace(/_/g, " ")} 光缆走廊${score >= 3 ? "疑似中断" : score >= 2 ? "风险升高" : "出现航行提示"}`,
      detail: warnings.map((warning) => plainText(stringValue(warning, "text_snippet"))).filter(Boolean).slice(0, 2).join(" · ") || `${warnings.length} 条相关航行警告`,
      source: "NGA MSI 光缆监测",
      severity: score >= 3 ? "high" : score >= 2 ? "medium" : "low",
      timestamp: isoTimestamp(cableDomain.timestamp, fallbackTimestamp),
      facts: eventFacts([
        ["状态", stringValue(item, "status_label")],
        ["涉及光缆", stringList(item.cables).join("、")],
        ["相关警告", warnings.length],
      ]),
    });
  }

  const fleetDomain = objectValue(snapshot.fleet_report);
  const fleetScore = numberValue(fleetDomain, "readiness_score");
  if (fleetScore !== undefined) {
    events.push({
      id: stableId("fleet-report", isoTimestamp(fleetDomain.timestamp, fallbackTimestamp), fleetScore),
      category: "military",
      title: `全球舰队活动 · ${stringValue(fleetDomain, "readiness_level").replace(/_/g, " ") || "态势更新"}`,
      detail: `${numberValue(fleetDomain, "total_tracked_aircraft") ?? 0} 架关联军机 · ${numberValue(fleetDomain, "surge_count") ?? 0} 个活动激增区域`,
      source: "World Intel 舰队报告",
      severity: fleetScore >= 70 ? "high" : fleetScore >= 40 ? "medium" : "info",
      timestamp: isoTimestamp(fleetDomain.timestamp, fallbackTimestamp),
      facts: eventFacts([
        ["活动评分", fleetScore],
        ["战区", numberValue(fleetDomain, "theater_count")],
        ["水道", numberValue(fleetDomain, "waterway_count")],
        ["海军基地", numberValue(fleetDomain, "naval_base_count")],
      ]),
    });
  }

  const socialDomain = objectValue(snapshot.social_signals);
  for (const item of domainRecords(snapshot, "social_signals", "posts")
    .filter((post) => (numberValue(post, "score") ?? 0) > 1000 || (numberValue(post, "num_comments") ?? 0) > 200)
    .slice(0, 10)) {
    const title = plainText(stringValue(item, "title"));
    if (!title) continue;
    const timestamp = isoTimestamp(item.created, isoTimestamp(socialDomain.timestamp, fallbackTimestamp));
    const url = stringValue(item, "url");
    events.push({
      id: stableId("social", stringValue(item, "subreddit"), timestamp, title),
      category: "society",
      title,
      detail: `r/${stringValue(item, "subreddit") || "world"} · ${compactNumber(numberValue(item, "score") ?? 0)} 赞同 · ${compactNumber(numberValue(item, "num_comments") ?? 0)} 评论`,
      source: "Reddit 公共讨论",
      severity: (numberValue(item, "num_comments") ?? 0) > 1000 ? "medium" : "info",
      timestamp,
      facts: eventFacts([["赞同率", numberValue(item, "upvote_ratio")]]),
      ...(url ? { url } : {}),
      recordKind: "news",
    });
  }

  const displacementDomain = objectValue(snapshot.displacement);
  const displacementTotals = objectValue(displacementDomain.global_totals);
  const displaced = numberValue(displacementTotals, "grand_total");
  if (displaced !== undefined && displaced > 0) {
    events.push({
      id: stableId("displacement", stringValue(displacementDomain, "year"), displaced),
      category: "society",
      title: `全球流离失所人口 ${compactNumber(displaced)}`,
      detail: `难民 ${compactNumber(numberValue(displacementTotals, "total_refugees") ?? 0)} · 境内流离失所 ${compactNumber(numberValue(displacementTotals, "total_idps") ?? 0)}`,
      source: "UNHCR",
      severity: "medium",
      timestamp: isoTimestamp(displacementDomain.timestamp, fallbackTimestamp),
      facts: eventFacts([
        ["统计年度", stringValue(displacementDomain, "year")],
        ["寻求庇护者", compactNumber(numberValue(displacementTotals, "total_asylum_seekers") ?? 0)],
        ["无国籍人口", compactNumber(numberValue(displacementTotals, "total_stateless") ?? 0)],
      ]),
      recordKind: "observation",
    });
  }

  return [...new Map(events.map((event) => [event.id, event])).values()]
    .sort((left, right) => Date.parse(right.timestamp) - Date.parse(left.timestamp));
}

function commodityReactionStatus(changePct: number): GlobalIntelMarketReaction["status"] {
  if (changePct >= 1.5) return "confirmed";
  if (changePct >= 0.5) return "watch";
  if (changePct <= -0.5) return "diverging";
  return "quiet";
}

export function calculateGlobalIntelMarketReactions(
  snapshot: Record<string, unknown>,
  routes: GlobalIntelRoute[],
): GlobalIntelMarketReaction[] {
  const reactions: GlobalIntelMarketReaction[] = [];
  const commodityDomain = objectValue(snapshot.commodity_quotes);
  const commodityTimestamp = isoTimestamp(commodityDomain.timestamp, isoTimestamp(snapshot.timestamp, new Date().toISOString()));
  const commodityQuotes = domainRecords(snapshot, "commodity_quotes", "commodities");
  const shippingDomain = objectValue(snapshot.shipping_index);
  const shippingStress = numberValue(shippingDomain, "stress_score");
  const shippingTimestamp = isoTimestamp(shippingDomain.timestamp, isoTimestamp(snapshot.timestamp, new Date().toISOString()));

  for (const route of routes.filter((item) => (item.riskScore ?? 0) > 0)) {
    const commodities = route.exposure?.commodities.join(" ") ?? "";
    const relevantSymbols = new Set<string>();
    if (route.kind === "pipeline" || /原油|成品油/.test(commodities)) {
      relevantSymbols.add("CL=F");
      relevantSymbols.add("BZ=F");
    }
    if (route.kind === "pipeline" || /LNG|天然气/.test(commodities)) relevantSymbols.add("NG=F");

    for (const quote of commodityQuotes) {
      const symbol = stringValue(quote, "symbol");
      const changePct = numberValue(quote, "change_pct");
      if (!relevantSymbols.has(symbol) || changePct === undefined) continue;
      const status = commodityReactionStatus(changePct);
      const label = stringValue(quote, "name") || symbol;
      reactions.push({
        routeId: route.id,
        kind: "commodity",
        label,
        symbol,
        value: changePct,
        unit: "%",
        status,
        strength: Math.min(100, Math.round(Math.abs(changePct) * 20)),
        timestamp: commodityTimestamp,
        reason: status === "confirmed"
          ? `${label} 上涨 ${changePct.toFixed(2)}%，与供应风险方向一致`
          : status === "diverging"
            ? `${label} 下跌 ${Math.abs(changePct).toFixed(2)}%，暂未验证供应冲击`
            : status === "watch"
              ? `${label} 小幅上涨 ${changePct.toFixed(2)}%，需要继续观察`
              : `${label} 波动有限，市场暂未出现明显反应`,
      });
    }

    if (route.kind === "shipping" && shippingStress !== undefined) {
      const status: GlobalIntelMarketReaction["status"] = shippingStress >= 15
        ? "confirmed"
        : shippingStress >= 5
          ? "watch"
          : "quiet";
      reactions.push({
        routeId: route.id,
        kind: "shipping",
        label: "航运压力指数",
        value: shippingStress,
        unit: "score",
        status,
        strength: Math.min(100, Math.round(shippingStress)),
        timestamp: shippingTimestamp,
        reason: status === "confirmed"
          ? `航运压力指数升至 ${shippingStress.toFixed(1)}，运输市场出现同步波动`
          : status === "watch"
            ? `航运压力指数为 ${shippingStress.toFixed(1)}，出现轻微压力`
            : `航运压力指数为 ${shippingStress.toFixed(1)}，暂未出现明显压力`,
      });
    }
  }
  return reactions.sort((left, right) => (
    (right.status === "confirmed" ? 3 : right.status === "watch" ? 2 : right.status === "diverging" ? 1 : 0)
    - (left.status === "confirmed" ? 3 : left.status === "watch" ? 2 : left.status === "diverging" ? 1 : 0)
    || right.strength - left.strength
  ));
}

export function calculateGlobalIntelRouteAlerts(
  routes: GlobalIntelRoute[],
  impacts: GlobalIntelRouteImpact[],
  marketReactions: GlobalIntelMarketReaction[],
): GlobalIntelRouteAlert[] {
  const alerts: GlobalIntelRouteAlert[] = [];
  for (const route of routes) {
    const routeImpacts = impacts.filter((impact) => impact.routeId === route.id);
    const primaryImpact = routeImpacts[0];
    const riskScore = route.riskScore ?? primaryImpact?.riskScore ?? 0;
    if (!primaryImpact || riskScore < 45) continue;
    const reactions = marketReactions.filter((reaction) => reaction.routeId === route.id);
    const confirmedReaction = reactions
      .filter((reaction) => reaction.status === "confirmed")
      .sort((left, right) => right.strength - left.strength)[0];
    const marketConfirmed = Boolean(confirmedReaction);
    const confidence = primaryImpact.confidence;
    const level: GlobalIntelRouteAlert["level"] = riskScore >= 85 && confidence >= 80 && marketConfirmed
      ? "critical"
      : riskScore >= 70 && confidence >= 60 && marketConfirmed
        ? "high"
        : "watch";
    const score = Math.round(
      riskScore * 0.55
      + confidence * 0.3
      + (confirmedReaction?.strength ?? 0) * 0.15,
    );
    const reasons = [
      `通道风险 ${riskScore}/100`,
      `证据置信度 ${confidence}%（${primaryImpact.sourceCount} 个来源）`,
      marketConfirmed
        ? `市场同步：${confirmedReaction!.label}`
        : "尚无市场同步验证",
    ];
    alerts.push({
      id: `route-alert-${route.id}`,
      routeId: route.id,
      level,
      score,
      title: `${route.name}${level === "watch" ? "进入观察" : "风险预警"}`,
      summary: level === "watch"
        ? "事件风险、证据或市场反应尚未同时达到高优先级门槛。"
        : "事件风险、证据置信度和市场反应已同时达到预警门槛。",
      reasons,
      confidence,
      marketConfirmed,
    });
  }
  const rank: Record<GlobalIntelRouteAlert["level"], number> = { critical: 3, high: 2, watch: 1 };
  return alerts.sort((left, right) => rank[right.level] - rank[left.level] || right.score - left.score);
}

export function reconcileGlobalIntelRouteAlertStates(
  current: Record<string, GlobalIntelRouteAlertState>,
  alerts: GlobalIntelRouteAlert[],
  now = new Date().toISOString(),
) {
  const next = { ...current };
  const activeIds = new Set(alerts.map((alert) => alert.id));
  const rank: Record<GlobalIntelRouteAlert["level"], number> = { critical: 3, high: 2, watch: 1 };
  for (const alert of alerts) {
    const previous = current[alert.id];
    const change: GlobalIntelRouteAlertChange = !previous || !previous.active
      ? "new"
      : rank[alert.level] > rank[previous.lastLevel]
        ? "escalated"
        : rank[alert.level] < rank[previous.lastLevel]
          ? "downgraded"
          : "stable";
    next[alert.id] = {
      alertId: alert.id,
      routeId: alert.routeId,
      title: alert.title,
      lastLevel: alert.level,
      disposition: previous?.disposition ?? "new",
      change,
      active: true,
      updatedAt: change === "stable" && previous ? previous.updatedAt : now,
    };
  }
  for (const state of Object.values(current)) {
    if (!state.active || activeIds.has(state.alertId)) continue;
    next[state.alertId] = {
      ...state,
      change: "resolved",
      active: false,
      updatedAt: now,
    };
  }
  return next;
}

async function jsonRequest(
  fetcher: GatewayFetch,
  url: string,
): Promise<Record<string, unknown>> {
  const response = await fetcher(url, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`全球情报服务返回 HTTP ${response.status}`);
  const payload = await response.json();
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) {
    throw new Error("全球情报服务返回了无效数据");
  }
  return payload as Record<string, unknown>;
}

export function createGlobalIntelDataSource(input: {
  baseUrl: string;
  fetch?: GatewayFetch;
  eventSourceFactory?: (url: string) => EventSource;
}): GlobalIntelDataSource {
  const fetcher = input.fetch ?? globalThis.fetch.bind(globalThis);
  const url = (path: string) => new URL(path, `${input.baseUrl.replace(/\/$/, "")}/`).toString();
  return {
    health: () => jsonRequest(fetcher, url("/api/global-intel/health")),
    staticSnapshot: () => jsonRequest(fetcher, url("/api/global-intel/static")),
    overview: () => jsonRequest(fetcher, url("/api/global-intel/overview")),
    subscribe(onPayload, onStatus) {
      onStatus("connecting");
      const source = (input.eventSourceFactory ?? ((target) => new EventSource(target)))(
        url("/api/global-intel/stream"),
      );
      source.onopen = () => onStatus("live");
      source.onmessage = (message) => {
        try {
          const payload = JSON.parse(message.data) as unknown;
          if (typeof payload === "object" && payload !== null && !Array.isArray(payload)) {
            onPayload(payload as Record<string, unknown>);
          }
        } catch {
          onStatus("degraded");
        }
      };
      source.onerror = () => onStatus("degraded");
      return () => source.close();
    },
  };
}
