import { describe, expect, it, vi } from "vitest";

import {
  calculateGlobalIntelMarketReactions,
  calculateGlobalIntelRouteAlerts,
  calculateGlobalIntelRouteImpacts,
  clusterGlobalIntelEvents,
  createGlobalIntelDataSource,
  globalIntelEventIdentity,
  isActionableGlobalIntelEvent,
  globalMediaTopicSimilarity,
  mediaVelocityLabel,
  mergeGlobalIntelEventHistory,
  normalizeGlobalMediaMonitor,
  normalizeGlobalIntelEvents,
  normalizeGlobalIntelPoints,
  normalizeGlobalIntelRoutes,
  reconcileGlobalIntelRouteAlertStates,
  updateGlobalIntelMilitaryTrackHistory,
} from "./data";

describe("global intelligence media monitor", () => {
  it("normalizes sentiment, velocity, cross-language topics, framing, and verification", () => {
    const monitor = normalizeGlobalMediaMonitor({
      media_monitor: {
        timestamp: "2026-08-12T12:00:00Z",
        caveat: "lightweight",
        summary: {
          analyzed_items: 20,
          news_items: 18,
          social_items: 2,
          source_count: 8,
          language_count: 3,
          topic_count: 4,
          current_mentions: 12,
          previous_mentions: 6,
          heat_velocity_pct: 100,
          velocity_state: "rising",
          window_hours: 12,
          cross_language_topic_count: 2,
          flagged_topic_count: 1,
          disputed_topic_count: 1,
          reversal_topic_count: 0,
          divergent_topic_count: 1,
          attention_topic_count: 2,
          spread_score: 68,
          sentiment: {
            positive: 3, negative: 8, neutral: 7, mixed: 2,
            positive_pct: 15, negative_pct: 40, neutral_pct: 35, mixed_pct: 10, net_score: -24,
          },
        },
        topics: [{
          id: "topic-hormuz", label: "伊朗 · 霍尔木兹海峡", headline: "Hormuz report",
          mention_count: 6, current_mentions: 5, previous_mentions: 1,
          heat_velocity_pct: 400, velocity_state: "rising", heat_score: 90,
          attention_score: 88, attention_level: "重点",
          spread_score: 82, spread_level: "广泛传播", source_count: 4,
          sources: ["Reuters", "BBC Mundo"], source_tiers: ["wire", "major"],
          language_count: 2, languages: ["en", "es"], language_labels: ["英语", "西班牙语"],
          cross_language: true, sentiment: "negative", sentiment_score: -0.5,
          sentiment_counts: { positive: 0, negative: 4, neutral: 2, mixed: 0 },
          media_frames: [{
            group: "mainstream", label: "主流媒体 / 通讯社", count: 6,
            positive: 0, negative: 4, neutral: 2, mixed: 0,
            dominant_sentiment: "negative", dominant_label: "偏负面", sources: ["Reuters", "BBC Mundo"],
          }],
          framing_divergence: true, framing_divergence_score: 58,
          verification_status: "存在争议", verification_flags: ["unverified", "denial"],
          verification_timeline: [{
            status: "出现否认", flag: "denial", timestamp: "2026-08-12T11:00:00Z",
            source: "Reuters", title: "Hormuz report", url: "https://example.com/hormuz",
          }],
          social_engagement: 5000, latest_at: "2026-08-12T11:00:00Z", keywords: ["伊朗", "霍尔木兹海峡"],
          items: [{
            key: "story-1", title: "Hormuz report", source: "Reuters", url: "https://example.com/hormuz",
            language: "en", sentiment: "negative", published: "2026-08-12T11:00:00Z", kind: "news",
          }],
        }],
        annotations: [{
          key: "https://example.com/hormuz", title: "Hormuz report", source: "Reuters", url: "https://example.com/hormuz",
          topic_id: "topic-hormuz", sentiment: "negative", sentiment_score: -0.5, language: "en",
          verification_status: "存在争议", verification_flags: ["unverified", "denial"],
          heat_velocity_pct: 400, velocity_state: "rising", spread_score: 82, cross_language_topic: true,
        }],
        media_frames: [],
      },
    });

    expect(monitor.summary).toEqual(expect.objectContaining({
      analyzedItems: 20,
      heatVelocityPct: 100,
      crossLanguageTopicCount: 2,
      flaggedTopicCount: 1,
      divergentTopicCount: 1,
      attentionTopicCount: 2,
    }));
    expect(monitor.topics[0]).toEqual(expect.objectContaining({
      id: "topic-hormuz",
      crossLanguage: true,
      verificationStatus: "存在争议",
      sentiment: "negative",
      attentionScore: 88,
      attentionLevel: "重点",
      framingDivergence: true,
      items: [expect.objectContaining({ source: "Reuters", sentiment: "negative" })],
      verificationTimeline: [expect.objectContaining({ status: "出现否认" })],
    }));
    expect(monitor.annotations[0]).toEqual(expect.objectContaining({
      topicId: "topic-hormuz",
      spreadScore: 82,
    }));
  });

  it("shows new topics without inventing a +100% baseline", () => {
    const monitor = normalizeGlobalMediaMonitor({
      media_monitor: {
        summary: { heat_velocity_pct: null, velocity_state: "new" },
        topics: [{
          id: "new-topic", label: "新主题", headline: "New topic", velocity_state: "new",
          heat_velocity_pct: null,
        }],
      },
    });

    expect(monitor.summary.heatVelocityPct).toBeNull();
    expect(monitor.topics[0]?.heatVelocityPct).toBeNull();
    expect(mediaVelocityLabel(null, "new")).toBe("新出现");
  });

  it("normalizes legacy new-topic +100% values to an honest new label", () => {
    const monitor = normalizeGlobalMediaMonitor({
      media_monitor: {
        summary: { heat_velocity_pct: 100, velocity_state: "new" },
        topics: [{ id: "legacy-new", label: "Legacy", heat_velocity_pct: 100, velocity_state: "new" }],
      },
    });

    expect(monitor.summary.heatVelocityPct).toBeNull();
    expect(mediaVelocityLabel(monitor.topics[0]?.heatVelocityPct, "new")).toBe("新出现");
  });

  it("finds lightweight historical similarities from topic words and sources", () => {
    expect(globalMediaTopicSimilarity(
      { id: "a", label: "伊朗 霍尔木兹", headline: "Hormuz shipping disruption", keywords: ["伊朗", "航运"], sources: ["Reuters"] },
      { id: "b", label: "伊朗 航运", headline: "Hormuz route risk", keywords: ["伊朗", "航运"], sources: ["Reuters"] },
    )).toBeGreaterThan(35);
  });

  it("attaches lightweight media analysis to news records", () => {
    const events = normalizeGlobalIntelEvents({
      timestamp: "2026-08-12T12:00:00Z",
      news_feed: {
        items: [{
          title: "Iran denies unverified Hormuz closure report",
          feed_name: "Reuters World",
          source_tier: "wire",
          published: "2026-08-12T11:00:00Z",
          link: "https://example.com/hormuz",
        }],
      },
      media_monitor: {
        annotations: [{
          key: "https://example.com/hormuz",
          title: "Iran denies unverified Hormuz closure report",
          source: "Reuters World",
          url: "https://example.com/hormuz",
          topic_id: "topic-hormuz",
          sentiment: "negative",
          sentiment_score: -0.5,
          language: "en",
          verification_status: "存在争议",
          verification_flags: ["unverified", "denial"],
          heat_velocity_pct: 120,
          velocity_state: "rising",
          spread_score: 78,
          cross_language_topic: true,
        }],
      },
    });

    expect(events[0]?.facts).toEqual(expect.arrayContaining([
      { label: "报道语气", value: "负面" },
      { label: "热度增速", value: "+120%" },
      { label: "传播范围", value: "78/100" },
      { label: "跨语言合并", value: "是" },
      { label: "核验提示", value: "存在争议" },
    ]));
  });
});

describe("global intelligence lightweight history", () => {
  it("keeps actionable records, refreshes last seen time, and drops observations", () => {
    const event = {
      id: "event-1",
      category: "conflict" as const,
      title: "Port disruption",
      detail: "Access restricted",
      source: "Test",
      severity: "high" as const,
      timestamp: "2026-08-10T08:00:00Z",
      recordKind: "event" as const,
    };
    const first = mergeGlobalIntelEventHistory([], [event, {
      ...event,
      id: "observation-1",
      title: "PAT452",
      recordKind: "observation" as const,
    }], "2026-08-10T09:00:00Z");
    const refreshed = mergeGlobalIntelEventHistory(first, [event], "2026-08-10T10:00:00Z");

    expect(first).toHaveLength(1);
    expect(refreshed[0]).toEqual(expect.objectContaining({
      firstSeenAt: "2026-08-10T09:00:00Z",
      lastSeenAt: "2026-08-10T10:00:00Z",
      lastChangedAt: "2026-08-10T09:00:00Z",
      observationCount: 2,
    }));
  });

  it("keeps the same signal identity when values and refresh timestamps change", () => {
    const first = {
      id: "market-first",
      category: "market" as const,
      title: "WTI 上涨 2.10%",
      detail: "最新价格 82.1",
      source: "Yahoo Finance",
      severity: "high" as const,
      timestamp: "2026-08-10T09:00:00Z",
      recordKind: "event" as const,
    };
    const next = {
      ...first,
      id: "market-next",
      title: "WTI 上涨 2.35%",
      detail: "最新价格 82.4",
      timestamp: "2026-08-10T10:00:00Z",
    };

    expect(globalIntelEventIdentity(first)).toBe(globalIntelEventIdentity(next));
    const history = mergeGlobalIntelEventHistory([], [first], "2026-08-10T09:00:00Z");
    const refreshed = mergeGlobalIntelEventHistory(history, [next], "2026-08-10T10:00:00Z");
    expect(refreshed).toHaveLength(1);
    expect(refreshed[0]).toEqual(expect.objectContaining({
      id: "market-next",
      lastChangedAt: "2026-08-10T10:00:00Z",
      observationCount: 2,
    }));
  });

  it("does not multiply capture counts when one snapshot repeats the same event", () => {
    const event = {
      id: "event-1",
      category: "disaster" as const,
      title: "M5.1 near test city",
      detail: "Depth 12 km",
      source: "USGS",
      severity: "medium" as const,
      timestamp: "2026-08-10T09:00:00Z",
      recordKind: "event" as const,
    };
    const history = mergeGlobalIntelEventHistory([], [event, event], "2026-08-10T10:00:00Z");

    expect(history).toHaveLength(1);
    expect(history[0]).toEqual(expect.objectContaining({ observationCount: 1 }));
  });

  it("records one resolution change and marks a later reappearance as changed", () => {
    const event = {
      id: "event-1",
      category: "infrastructure" as const,
      title: "Cable corridor disruption",
      detail: "Maintenance in progress",
      source: "Test",
      severity: "high" as const,
      timestamp: "2026-08-10T08:00:00Z",
      recordKind: "event" as const,
    };
    const active = mergeGlobalIntelEventHistory([], [event], "2026-08-10T09:00:00Z");
    const resolved = mergeGlobalIntelEventHistory(active, [], "2026-08-10T10:00:00Z");
    const stillResolved = mergeGlobalIntelEventHistory(resolved, [], "2026-08-10T11:00:00Z");
    const reappeared = mergeGlobalIntelEventHistory(stillResolved, [event], "2026-08-10T12:00:00Z");

    expect(resolved[0]).toEqual(expect.objectContaining({
      resolvedAt: "2026-08-10T10:00:00Z",
      lastChangedAt: "2026-08-10T10:00:00Z",
    }));
    expect(stillResolved[0]?.lastChangedAt).toBe("2026-08-10T10:00:00Z");
    expect(reappeared[0]).toEqual(expect.objectContaining({
      lastChangedAt: "2026-08-10T12:00:00Z",
    }));
    expect(reappeared[0]?.resolvedAt).toBeUndefined();
  });
});

describe("global intelligence route alert lifecycle", () => {
  it("tracks escalation, acknowledgement, downgrade, and resolution", () => {
    const baseAlert = {
      id: "route-alert-route-1",
      routeId: "route-1",
      level: "watch" as const,
      score: 50,
      title: "Test Route进入观察",
      summary: "",
      reasons: [],
      confidence: 50,
      marketConfirmed: false,
    };
    const created = reconcileGlobalIntelRouteAlertStates({}, [baseAlert], "2026-08-10T08:00:00Z");
    expect(created[baseAlert.id]).toEqual(expect.objectContaining({ change: "new", active: true, disposition: "new" }));

    const acknowledged = {
      ...created,
      [baseAlert.id]: { ...created[baseAlert.id]!, disposition: "acknowledged" as const },
    };
    const escalated = reconcileGlobalIntelRouteAlertStates(acknowledged, [{
      ...baseAlert,
      level: "high",
      title: "Test Route风险预警",
      marketConfirmed: true,
    }], "2026-08-10T09:00:00Z");
    expect(escalated[baseAlert.id]).toEqual(expect.objectContaining({
      change: "escalated",
      disposition: "acknowledged",
      lastLevel: "high",
    }));

    const resolved = reconcileGlobalIntelRouteAlertStates(escalated, [], "2026-08-10T10:00:00Z");
    expect(resolved[baseAlert.id]).toEqual(expect.objectContaining({ change: "resolved", active: false }));
  });
});

describe("global intelligence route alerts", () => {
  it("requires risk, confidence, and market confirmation for high priority", () => {
    const route = {
      id: "route-1",
      kind: "shipping" as const,
      name: "Test Route",
      detail: "",
      path: [[0, 0], [1, 1]] as Array<[number, number]>,
      riskScore: 78,
    };
    const impact = {
      routeId: "route-1",
      eventId: "event-1",
      relation: "mentioned" as const,
      reasons: [],
      riskScore: 78,
      confidence: 74,
      sourceCount: 2,
      evidenceCount: 2,
      ageHours: 2,
    };
    const marketReaction = {
      routeId: "route-1",
      kind: "shipping" as const,
      label: "航运压力指数",
      value: 20,
      unit: "score" as const,
      status: "confirmed" as const,
      strength: 40,
      timestamp: "2026-08-10T08:00:00Z",
      reason: "同步波动",
    };

    expect(calculateGlobalIntelRouteAlerts([route], [impact], [marketReaction])[0]).toEqual(
      expect.objectContaining({ level: "high", marketConfirmed: true }),
    );
    expect(calculateGlobalIntelRouteAlerts([route], [impact], [])[0]).toEqual(
      expect.objectContaining({ level: "watch", marketConfirmed: false }),
    );
  });
});

describe("global intelligence market reactions", () => {
  it("separates synchronized, diverging, and unavailable market evidence", () => {
    const reactions = calculateGlobalIntelMarketReactions({
      timestamp: "2026-08-10T12:00:00Z",
      commodity_quotes: {
        timestamp: "2026-08-10T11:55:00Z",
        commodities: [
          { symbol: "CL=F", name: "Crude Oil WTI", change_pct: 2.1 },
          { symbol: "NG=F", name: "Natural Gas", change_pct: -1.2 },
        ],
      },
      shipping_index: {
        timestamp: "2026-08-10T11:50:00Z",
        stress_score: 20,
      },
    }, [
      {
        id: "pipeline",
        kind: "pipeline",
        name: "Pipeline",
        detail: "",
        path: [[0, 0], [1, 1]],
        riskScore: 70,
        exposure: {
          countries: [],
          commodities: ["原油", "天然气"],
          industries: [],
          marketSignals: [],
        },
      },
      {
        id: "shipping",
        kind: "shipping",
        name: "Shipping",
        detail: "",
        path: [[0, 0], [1, 1]],
        riskScore: 60,
        exposure: {
          countries: [],
          commodities: ["集装箱货物"],
          industries: [],
          marketSignals: [],
        },
      },
      {
        id: "cable",
        kind: "cable",
        name: "Cable",
        detail: "",
        path: [[0, 0], [1, 1]],
        riskScore: 60,
      },
    ]);

    expect(reactions).toEqual(expect.arrayContaining([
      expect.objectContaining({ routeId: "pipeline", symbol: "CL=F", status: "confirmed" }),
      expect.objectContaining({ routeId: "pipeline", symbol: "NG=F", status: "diverging" }),
      expect.objectContaining({ routeId: "shipping", kind: "shipping", status: "confirmed" }),
    ]));
    expect(reactions.some((reaction) => reaction.routeId === "cable")).toBe(false);
  });
});

describe("global intelligence route impacts", () => {
  it("links nearby relevant events and ignores raw observations", () => {
    const points = [
      {
        id: "conflict-point",
        category: "conflict" as const,
        latitude: 0.1,
        longitude: 0,
        title: "Port conflict",
        detail: "",
        source: "Test",
        severity: "high" as const,
      },
      {
        id: "flight-point",
        category: "military" as const,
        latitude: 0.1,
        longitude: 0,
        title: "PAT452",
        detail: "",
        source: "ADS-B",
        severity: "info" as const,
      },
    ];
    const impacts = calculateGlobalIntelRouteImpacts([
      {
        id: "conflict-event",
        category: "conflict",
        title: "Port conflict",
        detail: "",
        source: "Test",
        severity: "high",
        timestamp: "2026-08-10T08:00:00Z",
        pointId: "conflict-point",
        recordKind: "event",
      },
      {
        id: "flight-observation",
        category: "military",
        title: "PAT452",
        detail: "",
        source: "ADS-B",
        severity: "info",
        timestamp: "2026-08-10T08:00:00Z",
        pointId: "flight-point",
        recordKind: "observation",
      },
    ], points, [{
      id: "shipping-route",
      kind: "shipping",
      name: "Test shipping corridor",
      detail: "",
      path: [[-1, 0], [1, 0]],
      pathType: "corridor",
    }], Date.parse("2026-08-10T12:00:00Z"));

    expect(impacts).toEqual([
      expect.objectContaining({
        routeId: "shipping-route",
        eventId: "conflict-event",
        relation: "direct",
      }),
    ]);
  });

  it("links news mentions to strategic corridors without claiming spatial confirmation", () => {
    const impacts = calculateGlobalIntelRouteImpacts([
      {
        id: "hormuz-news",
        category: "news",
        title: "Strait of Hormuz remains closed after talks",
        detail: "Shipping disruption continues",
        source: "Wire",
        severity: "medium",
        timestamp: "2026-08-10T08:00:00Z",
        recordKind: "news",
      },
      {
        id: "unrelated-news",
        category: "news",
        title: "Researchers discover a new species",
        detail: "",
        source: "Science",
        severity: "info",
        timestamp: "2026-08-10T08:00:00Z",
        recordKind: "news",
      },
    ], [], [{
      id: "gulf-route",
      kind: "shipping",
      name: "海湾—东亚能源航线",
      detail: "Strait of Hormuz → Strait of Malacca",
      path: [[56.3, 26.5], [103.8, 1.3]],
      keywords: ["Strait of Hormuz", "Strait of Malacca"],
      pathType: "corridor",
    }], Date.parse("2026-08-10T12:00:00Z"));

    expect(impacts).toEqual([
      expect.objectContaining({
        routeId: "gulf-route",
        eventId: "hormuz-news",
        relation: "mentioned",
        matchedKeyword: "strait of hormuz",
      }),
    ]);
  });

  it("raises confidence with independent sources and expires stale evidence", () => {
    const route = {
      id: "gulf-route",
      kind: "shipping" as const,
      name: "海湾—东亚能源航线",
      detail: "Strait of Hormuz",
      path: [[56.3, 26.5], [103.8, 1.3]] as Array<[number, number]>,
      keywords: ["Strait of Hormuz"],
      pathType: "corridor" as const,
    };
    const events = [
      {
        id: "wire-1",
        category: "news" as const,
        title: "Iran keeps Strait of Hormuz closed after talks",
        detail: "",
        source: "Reuters",
        severity: "medium" as const,
        timestamp: "2026-08-10T08:00:00Z",
        recordKind: "news" as const,
      },
      {
        id: "wire-2",
        category: "news" as const,
        title: "Strait of Hormuz remains closed as Iran talks stall",
        detail: "",
        source: "AP",
        severity: "medium" as const,
        timestamp: "2026-08-10T07:30:00Z",
        recordKind: "news" as const,
      },
    ];

    const confirmed = calculateGlobalIntelRouteImpacts(
      events,
      [],
      [route],
      Date.parse("2026-08-10T12:00:00Z"),
    );
    expect(confirmed).toHaveLength(2);
    expect(confirmed[0]).toEqual(expect.objectContaining({
      sourceCount: 2,
      evidenceCount: 2,
      confidence: expect.any(Number),
    }));
    expect(confirmed[0]!.confidence).toBeGreaterThanOrEqual(70);

    const expired = calculateGlobalIntelRouteImpacts(
      events,
      [],
      [route],
      Date.parse("2026-08-14T12:00:00Z"),
    );
    expect(expired).toEqual([]);
  });
});

describe("global intelligence event clusters", () => {
  it("groups related multi-source reports and keeps unrelated events separate", () => {
    const clusters = clusterGlobalIntelEvents([
      {
        id: "reuters-1",
        category: "news",
        title: "Iran keeps Strait of Hormuz closed after talks",
        detail: "",
        source: "Reuters",
        severity: "medium",
        timestamp: "2026-08-10T08:00:00Z",
      },
      {
        id: "ap-1",
        category: "news",
        title: "Strait of Hormuz remains closed as Iran talks stall",
        detail: "",
        source: "AP",
        severity: "high",
        timestamp: "2026-08-10T07:30:00Z",
      },
      {
        id: "science-1",
        category: "news",
        title: "Researchers discover a new deep sea species",
        detail: "",
        source: "Nature",
        severity: "info",
        timestamp: "2026-08-10T07:00:00Z",
      },
    ]);

    expect(clusters).toHaveLength(2);
    expect(clusters[0]).toEqual(expect.objectContaining({
      primary: expect.objectContaining({ id: "ap-1" }),
      sources: ["Reuters", "AP"],
    }));
  });

  it("does not merge unrelated NAVAREA warnings just because they share a year", () => {
    const clusters = clusterGlobalIntelEvents([
      {
        id: "nav-1",
        category: "maritime",
        title: "NAVAREA 12 · 2023-93",
        detail: "Missile firing area near Hawaii",
        source: "NGA 航行警告",
        severity: "high",
        timestamp: "2026-08-12T08:00:00Z",
      },
      {
        id: "nav-2",
        category: "maritime",
        title: "NAVAREA 4 · 2023-601",
        detail: "Light unreliable in the Gulf of Mexico",
        source: "NGA 航行警告",
        severity: "medium",
        timestamp: "2026-08-12T08:10:00Z",
      },
    ]);

    expect(clusters).toHaveLength(2);
  });
});

describe("global intelligence normalization", () => {
  it("upgrades only explainable ADS-B anomalies into military events", () => {
    const events = normalizeGlobalIntelEvents({
      timestamp: "2026-08-10T12:00:00Z",
      trade_routes: {
        routes: [{ name: "Strait of Hormuz", lat: 26.57, lon: 56.25 }],
      },
      military_flights: {
        aircraft: [
          { icao24: "a1", callsign: "RCH101", latitude: 26.6, longitude: 56.3, origin_country: "United States" },
          { icao24: "a2", callsign: "RCH102", latitude: 26.7, longitude: 56.4, origin_country: "United States" },
          { icao24: "a3", callsign: "PAT103", latitude: 26.5, longitude: 56.1, origin_country: "United States" },
          { icao24: "a4", callsign: "PAT452", latitude: 46.7, longitude: -100.7, origin_country: "United States" },
          { icao24: "a5", callsign: "RCH7700", latitude: 40, longitude: -90, origin_country: "United States", squawk: "7700" },
        ],
      },
    });

    expect(events).toEqual(expect.arrayContaining([
      expect.objectContaining({
        category: "military",
        title: "3 架军机在 Strait of Hormuz 附近集结",
        recordKind: "event",
        severity: "high",
      }),
      expect.objectContaining({
        title: "RCH7700 ADS-B 紧急状态",
        recordKind: "event",
        severity: "critical",
      }),
      expect.objectContaining({ title: "PAT452", recordKind: "observation", severity: "info" }),
    ]));
    expect(events.some((event) => event.title === "PAT452" && event.recordKind === "event")).toBe(false);
  });

  it("keeps six hours of deduplicated ADS-B track samples", () => {
    const now = new Date("2026-08-10T12:00:00Z");
    const snapshot = {
      military_flights: {
        timestamp: "2026-08-10T12:00:00Z",
        aircraft: [{ icao24: "abc", callsign: "RCH101", latitude: 10, longitude: 20 }],
      },
    };
    const history = updateGlobalIntelMilitaryTrackHistory({
      abc: [
        { aircraftId: "abc", callsign: "RCH101", latitude: 1, longitude: 2, observedAt: "2026-08-10T05:00:00Z" },
      ],
    }, snapshot, now);
    const deduplicated = updateGlobalIntelMilitaryTrackHistory(history, snapshot, now);

    expect(deduplicated.abc).toHaveLength(1);
    expect(deduplicated.abc?.[0]).toEqual(expect.objectContaining({ latitude: 10, longitude: 20 }));
  });

  it("detects a probable circling track", () => {
    const coordinates = [[0, 0], [0, 1], [1, 1], [1, 0], [0.1, 0], [0, 0.05]];
    const history = {
      circle1: coordinates.map(([latitude, longitude], index) => ({
        aircraftId: "circle1", callsign: "RCHCIRCLE", latitude: latitude!, longitude: longitude!,
        observedAt: `2026-08-10T11:${String(index * 5).padStart(2, "0")}:00Z`,
      })),
    };
    const events = normalizeGlobalIntelEvents({
      timestamp: "2026-08-10T12:00:00Z",
      military_flights: { aircraft: [{ icao24: "circle1", callsign: "RCHCIRCLE", latitude: 0, longitude: 0.05 }] },
    }, history);

    expect(events).toEqual(expect.arrayContaining([
      expect.objectContaining({ title: "RCHCIRCLE 航迹异常", detail: expect.stringContaining("疑似盘旋") }),
    ]));
  });

  it("detects a sharp course reversal", () => {
    const history = {
      reverse1: [
        { aircraftId: "reverse1", callsign: "RCHTURN", latitude: 5, longitude: 5, heading: 20, observedAt: "2026-08-10T11:40:00Z" },
        { aircraftId: "reverse1", callsign: "RCHTURN", latitude: 5.2, longitude: 5.1, heading: 20, observedAt: "2026-08-10T11:45:00Z" },
        { aircraftId: "reverse1", callsign: "RCHTURN", latitude: 5, longitude: 5, heading: 200, observedAt: "2026-08-10T11:50:00Z" },
      ],
    };
    const events = normalizeGlobalIntelEvents({
      timestamp: "2026-08-10T12:00:00Z",
      military_flights: { aircraft: [{ icao24: "reverse1", callsign: "RCHTURN", latitude: 5, longitude: 5 }] },
    }, history);

    expect(events).toEqual(expect.arrayContaining([
      expect.objectContaining({ title: "RCHTURN 航迹异常", detail: expect.stringContaining("明显折返") }),
    ]));
  });

  it("merges continuous approach into a sensitive-node event", () => {
    const history = {
      approach1: [52, 53, 54, 55].map((longitude, index) => ({
        aircraftId: "approach1", callsign: "RCHHORMUZ", latitude: 26.57, longitude,
        observedAt: `2026-08-10T11:${String(index * 5).padStart(2, "0")}:00Z`,
      })),
    };
    const events = normalizeGlobalIntelEvents({
      timestamp: "2026-08-10T12:00:00Z",
      military_flights: { aircraft: [{ icao24: "approach1", callsign: "RCHHORMUZ", latitude: 26.57, longitude: 55 }] },
    }, history);

    expect(events).toEqual(expect.arrayContaining([
      expect.objectContaining({ title: "RCHHORMUZ 接近 Strait of Hormuz", detail: expect.stringContaining("持续接近") }),
    ]));
    expect(events.filter((event) => event.title === "RCHHORMUZ 航迹异常")).toHaveLength(0);
  });

  it("detects signal disappearance near a sensitive node only when the source remains available", () => {
    const history = {
      missing1: [{
        aircraftId: "missing1", callsign: "PATLOST", latitude: 26.57, longitude: 56.4,
        observedAt: "2026-08-10T11:40:00Z",
      }],
    };
    const healthySnapshot = {
      timestamp: "2026-08-10T12:00:00Z",
      military_flights: { aircraft: [{ icao24: "other", callsign: "RCHOTHER", latitude: 40, longitude: -80 }] },
    };

    expect(normalizeGlobalIntelEvents(healthySnapshot, history)).toEqual(expect.arrayContaining([
      expect.objectContaining({ title: "PATLOST 在 Strait of Hormuz 附近信号消失", severity: "high" }),
    ]));
    expect(normalizeGlobalIntelEvents({
      ...healthySnapshot,
      military_flights: { status: "error", aircraft: [] },
    }, history).some((event) => event.title.includes("信号消失"))).toBe(false);
  });

  it("keeps an ordinary straight military track as an observation", () => {
    const history = {
      pat452: [-102, -101, -100].map((longitude, index) => ({
        aircraftId: "pat452", callsign: "PAT452", latitude: 46.7, longitude,
        observedAt: `2026-08-10T11:${String(index * 5).padStart(2, "0")}:00Z`,
      })),
    };
    const events = normalizeGlobalIntelEvents({
      timestamp: "2026-08-10T12:00:00Z",
      military_flights: { aircraft: [{ icao24: "pat452", callsign: "PAT452", latitude: 46.7, longitude: -100 }] },
    }, history);

    expect(events.find((event) => event.title === "PAT452")).toEqual(expect.objectContaining({ recordKind: "observation" }));
    expect(events.some((event) => event.title === "PAT452 航迹异常")).toBe(false);
  });

  it("converts the wider world monitor domains into visible events and map points", () => {
    const snapshot = {
      timestamp: "2026-08-11T12:00:00Z",
      news_feed: { items: [{ title: "Detailed world report", summary: "Short summary", content: "<p>Longer report &amp; additional context.</p>", feed_name: "BBC World", source_tier: "major", published: "2026-08-11T11:58:00Z" }] },
      cyber_threats: {
        timestamp: "2026-08-11T11:50:00Z",
        threats: [{
          type: "vulnerability", indicator: "CVE-2026-1234", threat: "Test Product RCE",
          severity: "critical", source_feed: "cisa-kev", first_seen: "2026-08-11T10:00:00Z",
          details: { vendor: "Test Vendor", required_action: "Apply updates" },
        }],
      },
      space_weather: { timestamp: "2026-08-11T11:55:00Z", current_kp: 7.2, kp_level: "Severe", latest_flare_class: "M2" },
      prediction_markets: { timestamp: "2026-08-11T11:45:00Z", markets: [{ question: "Will test event occur?", yes_probability: 0.72, volume_24h: 2_000_000, url: "https://polymarket.com/event/test" }] },
      ai_watch: { timestamp: "2026-08-11T11:40:00Z", items: [{ title: "New model released", summary: "<p>Model details &amp; benchmarks</p>", feed_name: "AI Lab", published: "2026-08-11T11:00:00Z", lab_mentions: ["openai"] }] },
      airport_delays: { timestamp: "2026-08-11T11:35:00Z", delayed: [{ code: "JFK", name: "John F Kennedy", delay: true, status: [{ type: "Ground Delay", reason: "Weather", avg_delay: "45 minutes" }] }] },
      service_status: { timestamp: "2026-08-11T11:30:00Z", incidents: [{ provider: "Cloud Test", title: "Regional degradation", severity: "high", summary: "API latency", published: "2026-08-11T11:20:00Z" }] },
      cable_health: { timestamp: "2026-08-11T11:25:00Z", corridors: { red_sea: { status_score: 2, status_label: "at_risk", cables: ["AAE-1"], relevant_warnings: [{ text_snippet: "Cable operations warning" }] } } },
      fleet_report: { timestamp: "2026-08-11T11:15:00Z", readiness_score: 72, readiness_level: "HIGH_ACTIVITY", total_tracked_aircraft: 40, surge_count: 2 },
      social_signals: { timestamp: "2026-08-11T11:10:00Z", posts: [{ title: "Major geopolitical discussion", subreddit: "worldnews", score: 2400, num_comments: 450, created: "2026-08-11T10:30:00Z", url: "https://reddit.com/test" }] },
      displacement: { timestamp: "2026-08-11T11:05:00Z", year: 2026, global_totals: { grand_total: 10_000_000, total_refugees: 4_000_000, total_idps: 5_000_000 } },
      population_exposure: { timestamp: "2026-08-11T11:00:00Z", exposed_cities: [{ city: "Test City", country: "Testland", lat: 10, lon: 20, population: 6_000_000, distance_km: 50, nearest_event: "conflict", event_detail: "Nearby conflict" }] },
    };

    const events = normalizeGlobalIntelEvents(snapshot);
    const points = normalizeGlobalIntelPoints(snapshot);

    expect([...new Set(events.map((event) => event.category))]).toEqual(expect.arrayContaining([
      "cyber", "space", "prediction", "technology", "aviation", "infrastructure", "military", "society",
    ]));
    expect(events).toEqual(expect.arrayContaining([
      expect.objectContaining({ category: "cyber", title: expect.stringContaining("CVE-2026-1234"), severity: "critical" }),
      expect.objectContaining({ category: "space", severity: "high" }),
      expect.objectContaining({ category: "prediction", title: "Will test event occur?" }),
      expect.objectContaining({ category: "technology", detail: "Model details & benchmarks" }),
      expect.objectContaining({ category: "aviation", title: expect.stringContaining("JFK") }),
      expect.objectContaining({ category: "infrastructure", title: expect.stringContaining("Cloud Test") }),
      expect.objectContaining({ category: "infrastructure", title: expect.stringContaining("red sea") }),
      expect.objectContaining({ category: "military", title: expect.stringContaining("全球舰队活动") }),
      expect.objectContaining({ category: "society", title: expect.stringContaining("全球流离失所人口") }),
      expect.objectContaining({ category: "news", title: "Detailed world report", content: "Longer report & additional context.", severity: "medium" }),
    ]));
    expect(points).toEqual(expect.arrayContaining([
      expect.objectContaining({ category: "society", title: "Test City 人口暴露", severity: "high" }),
    ]));
  });

  it("turns market, macro, energy, shipping, country risk, and fleet data into focused signals", () => {
    const events = normalizeGlobalIntelEvents({
      timestamp: "2026-08-12T08:00:00Z",
      crypto_quotes: {
        timestamp: "2026-08-12T07:59:00Z",
        coins: [
          { id: "bitcoin", symbol: "btc", name: "Bitcoin", current_price: 120000, market_cap: 2_000_000_000_000, price_change_percentage_24h: 8.2 },
          { id: "ethereum", symbol: "eth", name: "Ethereum", current_price: 5000, price_change_percentage_24h: 2.1 },
        ],
      },
      stablecoin_status: {
        timestamp: "2026-08-12T07:58:00Z",
        stablecoins: [{ id: "usd-coin", price: 0.97, peg_deviation_pct: 3, is_depegged: true }],
      },
      sector_heatmap: {
        timestamp: "2026-08-12T07:57:00Z",
        sectors: [{ symbol: "XLK", name: "Technology", price: 230, change_pct: -3.2 }],
      },
      commodity_quotes: {
        timestamp: "2026-08-12T07:56:30Z",
        commodities: [{ symbol: "BZ=F", name: "Brent Crude", price: 92, change_pct: 3.4 }],
      },
      etf_flows: {
        timestamp: "2026-08-12T07:56:00Z",
        etfs: [{ symbol: "IBIT", price: 80, change_pct: 4.1, volume: 12_000_000 }],
      },
      macro_signals: {
        timestamp: "2026-08-12T07:55:00Z",
        signals: {
          fear_greed: { value: 12, classification: "Extreme Fear" },
          vix: { price: 32, change_pct: 11 },
          gold: { price: 3500, change_pct: 2.2 },
          mempool_fees: { fastest_fee: 120, half_hour_fee: 100, hour_fee: 80 },
        },
      },
      btc_technicals: {
        timestamp: "2026-08-12T07:54:00Z",
        price: 120000, sma_50: 115000, sma_200: 118000, mayer_multiple: 1.02,
        cross_signal: "death_cross", ath_distance_pct: -8, change_7d_pct: -12, change_30d_pct: 5,
      },
      energy_prices: {
        fetched_at: "2026-08-12T07:53:00Z",
        oil: { brent: { price: 92, date: "2026-08-11" }, wti: { price: 89, date: "2026-08-11" } },
        natural_gas: { price: 4.5, date: "2026-08-11" },
      },
      residential_natgas: {
        fetched_at: "2026-08-12T07:52:30Z",
        prices: [{ price: 16.2, period: "2026-06", change_pct: 9.2 }],
      },
      gas_prices: {
        fetched_at: "2026-08-12T07:52:00Z",
        prices: { regular: { price_per_gallon: 4.2, change_pct: 0.5, week_ago_pct: 9, month_ago_pct: 10 } },
      },
      electricity_rates: {
        fetched_at: "2026-08-12T07:51:00Z",
        rates: { residential: { price_cents_kwh: 18, change_pct: 6, period: "2026-06" } },
      },
      shipping_index: {
        timestamp: "2026-08-12T07:50:00Z",
        stress_score: 25, assessment: "elevated", signals: ["BDRY up 4.2%"],
        quotes: [{ symbol: "BDRY", change_pct: 4.2 }],
      },
      risk_scores: {
        timestamp: "2026-08-12T07:49:00Z",
        countries: [{ country: "Sudan", events_30d: 110, monthly_baseline: 50, risk_score: 220, risk_level: "high" }],
      },
      usni_fleet: {
        timestamp: "2026-08-12T07:48:00Z",
        report_title: "USNI Fleet and Marine Tracker: Aug. 10, 2026",
        report_date: "2026-08-10T14:00:00Z",
        report_url: "https://news.usni.org/fleet-tracker",
        ship_count: 2,
        ships: [
          { name: "USS Test", hull_number: "CVN-99", region: "INDOPACOM" },
          { name: "USS Example", hull_number: "DDG-199", region: "CENTCOM" },
        ],
        strike_groups: [{ name: "CSG-3" }],
        force_totals: { battle_force: { total: 295 }, deployed: { total: 100 }, underway: { total: 70 } },
        region_breakdown: { INDOPACOM: 1, CENTCOM: 1 },
      },
    });

    expect(events).toEqual(expect.arrayContaining([
      expect.objectContaining({ title: expect.stringContaining("Bitcoin"), category: "market", severity: "medium" }),
      expect.objectContaining({ title: "usd coin 出现脱锚", severity: "high" }),
      expect.objectContaining({ title: expect.stringContaining("Technology 领跌"), category: "market" }),
      expect.objectContaining({ title: expect.stringContaining("Brent Crude 上涨"), category: "market" }),
      expect.objectContaining({ title: expect.stringContaining("VIX"), severity: "medium" }),
      expect.objectContaining({ title: "BTC 技术信号 · 死亡交叉", severity: "high" }),
      expect.objectContaining({ title: "全球能源基准价格更新", source: "EIA" }),
      expect.objectContaining({ title: expect.stringContaining("美国居民天然气价格上涨"), countryCode: "USA" }),
      expect.objectContaining({ title: "全球航运市场压力升高", category: "maritime" }),
      expect.objectContaining({ title: "Sudan 冲突活动高于历史基线", countryCode: "SDN" }),
      expect.objectContaining({
        title: "USNI Fleet and Marine Tracker: Aug. 10, 2026",
        content: expect.stringContaining("USS Test"),
        recordKind: "news",
      }),
    ]));
    expect(events.some((event) => event.title.includes("Ethereum"))).toBe(false);
  });

  it("exposes the upstream analysis layer as readable events and map hotspots", () => {
    const snapshot = {
      timestamp: "2026-08-12T09:00:00Z",
      signal_convergence: {
        timestamp: "2026-08-12T08:59:00Z",
        hotspots: [
          { name: "middle_east", lat: 33, lon: 44, convergence_score: 4.5, signals: { earthquakes: 10 } },
          { name: "sahel", lat: 15, lon: 2, convergence_score: 2, signals: { earthquakes: 0 } },
        ],
      },
      alert_digest: {
        timestamp: "2026-08-12T08:58:00Z",
        alert_count: 2,
        by_priority: { critical: 1, high: 1 },
        domains_checked: ["instability", "military_surge"],
        alerts: [
          { domain: "political", priority: "critical", value: 2, countries: ["Sudan", "Yemen"] },
          { domain: "military", priority: "high", value: 1, surges: [{ theater: "middle_east" }] },
        ],
      },
      weekly_trends: {
        timestamp: "2026-08-12T08:57:00Z",
        current_anomalies: [{
          event_type: "military_flights", region: "persian_gulf", z_score: 3.4,
          severity: "high", multiplier: 2.8, observed: 28, expected: 10,
        }],
      },
      situation_brief: {
        timestamp: "2026-08-12T08:56:00Z",
        brief: "当前综合风险为风险升高。\n\n未来12小时重点关注军事与基础设施变化。",
        metrics_snapshot: {
          posture_score: 42, risk_level: "ELEVATED", alerts: 2,
          military_aircraft: 40, conflicts: 12, earthquakes: 8, cyber_threats: 25,
        },
      },
      trending_keywords: {
        timestamp: "2026-08-12T08:55:00Z",
        total_items_analyzed: 120,
        keywords: [
          { word: "hormuz", count: 12 },
          { word: "shipping", count: 9 },
          { word: "energy", count: 8 },
        ],
      },
      domestic_flights: {
        timestamp: "2026-08-12T08:54:00Z",
        total_aircraft: 7000,
        by_region: {
          north_america: { count: 4200, commercial: 2000 },
          east_asia: { count: 900, commercial: 500 },
        },
        busiest_origins: [{ country: "United States", count: 3800 }, { country: "China", count: 500 }],
      },
    };

    const events = normalizeGlobalIntelEvents(snapshot);
    const points = normalizeGlobalIntelPoints(snapshot);

    expect(events).toEqual(expect.arrayContaining([
      expect.objectContaining({ title: "全球综合预警 · 2 项", severity: "critical", content: expect.stringContaining("军事活动激增") }),
      expect.objectContaining({ title: "波斯湾 军机活动偏离历史基线", severity: "high" }),
      expect.objectContaining({ title: "全球综合态势 · 风险升高", content: expect.stringContaining("未来12小时") }),
      expect.objectContaining({ title: "全球新闻热词 · hormuz / shipping / energy", recordKind: "news" }),
      expect.objectContaining({ title: "全球在途航空器 7000 架", recordKind: "observation" }),
      expect.objectContaining({ title: "中东 监测信号汇聚", pointId: expect.any(String) }),
    ]));
    expect(points).toEqual(expect.arrayContaining([
      expect.objectContaining({ title: "中东 监测信号汇聚", category: "conflict", severity: "medium" }),
    ]));
    expect(points.some((point) => point.title.includes("萨赫勒"))).toBe(false);
  });

  it("normalizes static, conflict, disaster, and wildfire map layers", () => {
    const points = normalizeGlobalIntelPoints({
      military_bases: {
        bases: [{ id: "b1", name: "Test Base", latitude: 35, longitude: 139 }],
      },
      earthquakes: {
        earthquakes: [{ place: "Pacific Ridge", latitude: 12, longitude: 141, magnitude: 6.2 }],
      },
      wildfires: {
        fires_by_region: {
          north_america: {
            top_clusters: [{ latitude: 44, longitude: -120, fire_count: 18 }],
          },
          empty_region: { top_clusters: [] },
        },
      },
    });

    expect(points).toEqual(expect.arrayContaining([
      expect.objectContaining({ category: "military", title: "Test Base" }),
      expect.objectContaining({ category: "disaster", title: "Pacific Ridge", severity: "critical" }),
      expect.objectContaining({ category: "disaster", title: "north america 火点集群", source: "NASA FIRMS" }),
    ]));
  });

  it("normalizes pipeline and cable infrastructure routes", () => {
    const routes = normalizeGlobalIntelRoutes({
      pipelines: {
        pipelines: [{ name: "Test Pipeline", lat_start: 10, lon_start: 20, lat_end: 30, lon_end: 40, status: "active" }],
      },
      cable_corridors: {
        corridors: [{ name: "test_cable", lat_range: [20, 40], lon_range: [-60, -10], cables: ["A", "B"] }],
      },
      trade_routes: {
        routes: [
          { name: "Strait of Gibraltar", lat: 35.97, lon: -5.6 },
          { name: "Suez Canal", lat: 30.58, lon: 32.27 },
          { name: "Bab el-Mandeb", lat: 12.58, lon: 43.33 },
        ],
      },
    });

    expect(routes).toEqual(expect.arrayContaining([
      expect.objectContaining({
        kind: "pipeline",
        path: [[20, 10], [40, 30]],
        pathType: "corridor",
        exposure: expect.objectContaining({ commodities: expect.arrayContaining(["原油", "天然气"]) }),
      }),
      expect.objectContaining({
        kind: "cable",
        path: [[-60, 30], [-10, 30]],
        pathType: "corridor",
        exposure: expect.objectContaining({ industries: expect.arrayContaining(["电信", "云服务"]) }),
      }),
      expect.objectContaining({
        kind: "shipping",
        name: "欧亚主航线",
        exposure: expect.objectContaining({ marketSignals: expect.arrayContaining(["集运运价"]) }),
      }),
      expect.objectContaining({
        kind: "shipping",
        name: "海湾—东亚原油油运线",
        pathType: "corridor",
        exposure: expect.objectContaining({ commodities: expect.arrayContaining(["原油"]) }),
      }),
      expect.objectContaining({
        kind: "flight",
        name: "欧洲—海湾—亚洲航空走廊",
        pathType: "corridor",
        exposure: expect.objectContaining({ industries: expect.arrayContaining(["航空公司", "机场"]) }),
      }),
    ]));
  });

  it("maps geospatial monitor feeds and keeps non-geographic intelligence in the event stream", () => {
    const snapshot = {
      timestamp: "2026-08-10T12:00:00Z",
      nav_warnings: {
        timestamp: "2026-08-10T11:00:00Z",
        warnings: [{ id: "NW-1", navarea: "XI", status: "active", issue_date: "2026-08-10T10:00:00Z", text: "MISSILE FIRING AREA", lat: 24, lon: 122 }],
      },
      nuclear_monitor: {
        timestamp: "2026-08-10T11:30:00Z",
        sites: [{ name: "Test Site", country: "Testland", iso3: "TST", lat: 41, lon: 129, status: "active", events_detected: 1, highest_concern: { concern_level: "elevated" } }],
        flagged_events: [{ site: "Test Site", latitude: 41.1, longitude: 129.1, magnitude: 2.4, depth_km: 3, distance_km: 12, concern_level: "high", time: "2026-08-10T09:00:00Z" }],
      },
      climate_anomalies: {
        timestamp: "2026-08-10T08:00:00Z",
        zones: {
          south_asia: { name: "South Asia", lat: 25, lon: 78, temp_anomaly_c: 1.2, precip_anomaly_pct: 240, is_significant: true },
        },
      },
      traffic_incidents: {
        timestamp: "2026-08-10T07:00:00Z",
        incidents: [{ region: "Europe", description: "Major road closure", delay_seconds: 4000, length_meters: 12000, magnitude: 4, lat: 48.8, lon: 2.3 }],
      },
      webcams: {
        timestamp: "2026-08-10T07:00:00Z",
        cameras: [{ id: "cam-1", title: "Harbor camera", lat: 1.3, lon: 103.8, city: "Singapore", country: "Singapore", player_url: "https://example.com/cam" }],
      },
      internet_outages: {
        timestamp: "2026-08-10T06:00:00Z",
        source: "ioda-gatech",
        outages: [{ id: "out-1", start: 1_786_336_000, description: "National connectivity loss", countries: ["TEST"], is_ongoing: true }],
      },
      disease_outbreaks: {
        timestamp: "2026-08-10T05:00:00Z",
        items: [{ title: "WHO monitors H5N1 cluster", summary: "Public health investigation", organization: "WHO", published: "2026-08-10T04:00:00Z", is_high_concern: true }],
      },
    };

    const points = normalizeGlobalIntelPoints(snapshot);
    const events = normalizeGlobalIntelEvents(snapshot);

    expect(points).toEqual(expect.arrayContaining([
      expect.objectContaining({ category: "maritime", title: "NAVAREA XI · NW-1", severity: "high" }),
      expect.objectContaining({ category: "nuclear", source: "USGS 核活动监测", severity: "high" }),
      expect.objectContaining({ category: "climate", title: "South Asia", severity: "high" }),
      expect.objectContaining({ category: "infrastructure", source: "TomTom 交通事件", severity: "high" }),
      expect.objectContaining({ source: "Windy 公共摄像头", url: "https://example.com/cam" }),
    ]));
    expect(points.some((point) => point.category === "health" || point.category === "cyber")).toBe(false);
    expect(events).toEqual(expect.arrayContaining([
      expect.objectContaining({ category: "cyber", title: "TEST 网络中断持续中", severity: "high" }),
      expect.objectContaining({ category: "health", source: "WHO", severity: "high" }),
      expect.objectContaining({ category: "climate", title: "South Asia" }),
    ]));
  });

  it("preserves rich dossiers for core geographic events", () => {
    const events = normalizeGlobalIntelEvents({
      timestamp: "2026-08-12T10:00:00Z",
      earthquakes: {
        earthquakes: [{
          id: "eq-1", place: "Test Ridge", latitude: 10, longitude: 120,
          magnitude: 6.3, depth_km: 18.5, tsunami_alert: 1, felt_reports: 42,
          alert_level: "orange", time: "2026-08-12T09:30:00Z", url: "https://earthquake.usgs.gov/test",
        }],
      },
      acled_events: {
        events: [{
          event_id_cnty: "acled-1", event_date: "2026-08-12", event_type: "Battles",
          sub_event_type: "Armed clash", actor1: "Force A", actor2: "Force B",
          country: "Sudan", admin1: "Khartoum", location: "Test City",
          latitude: 15, longitude: 32, fatalities: 7, notes: "Detailed conflict account.",
          source: "Local Monitor",
        }],
      },
      ucdp_events: {
        events: [{
          id: "ucdp-1", date_start: "2026-08-11", country: "Yemen", region: "Middle East",
          type_of_violence_label: "state-based", side_a: "Side A", side_b: "Side B",
          best: 12, low: 8, high: 16, latitude: 14, longitude: 44,
          source_headline: "Detailed UCDP source headline",
          source_article: "https://example.com/ucdp-source",
        }],
      },
      nav_warnings: {
        timestamp: "2026-08-12T09:00:00Z",
        warnings: [{
          id: "2026-1", navarea: "XI", subregion: "NW Pacific", status: "active",
          issue_date: "2026-08-12T08:00:00Z", authority: "NGA",
          text: "MISSILE FIRING EXERCISE. VESSELS KEEP CLEAR.", lat: 24, lon: 122,
        }],
      },
      nuclear_monitor: {
        timestamp: "2026-08-12T09:00:00Z",
        flagged_events: [{
          site: "Test Site", site_country: "Testland", latitude: 41, longitude: 129,
          magnitude: 2.8, depth_km: 4, distance_km: 20, concern_score: 68,
          concern_level: "high", time: "2026-08-12T07:00:00Z",
        }],
      },
      climate_anomalies: {
        timestamp: "2026-08-12T06:00:00Z",
        zones: {
          south_asia: {
            name: "South Asia", lat: 25, lon: 78, current_avg_temp_c: 33,
            baseline_avg_temp_c: 29, temp_anomaly_c: 4, current_precip_mm: 220,
            baseline_precip_mm: 100, precip_anomaly_pct: 120, is_significant: true,
          },
        },
      },
    });

    expect(events).toEqual(expect.arrayContaining([
      expect.objectContaining({
        title: "Test Ridge",
        detail: "M6.3 · 深度 18.5 km · 海啸提示",
        facts: expect.arrayContaining([expect.objectContaining({ label: "有感报告", value: "42" })]),
        url: "https://earthquake.usgs.gov/test",
      }),
      expect.objectContaining({
        title: "Test City",
        content: "Detailed conflict account.",
        facts: expect.arrayContaining([expect.objectContaining({ label: "参与方B", value: "Force B" })]),
      }),
      expect.objectContaining({
        title: "Yemen",
        url: "https://example.com/ucdp-source",
        facts: expect.arrayContaining([expect.objectContaining({ label: "估计区间", value: "8–16" })]),
      }),
      expect.objectContaining({
        title: "NAVAREA XI · 2026-1",
        content: "MISSILE FIRING EXERCISE. VESSELS KEEP CLEAR.",
      }),
      expect.objectContaining({
        category: "nuclear",
        facts: expect.arrayContaining([expect.objectContaining({ label: "关注评分", value: "68" })]),
      }),
      expect.objectContaining({
        title: "South Asia",
        facts: expect.arrayContaining([expect.objectContaining({ label: "去年同期降水", value: "100.0 mm" })]),
      }),
    ]));
  });

  it("combines policy, news, market, conflict, and disaster events by freshness", () => {
    const events = normalizeGlobalIntelEvents({
      timestamp: "2026-08-09T12:00:00Z",
      news_feed: {
        items: [{ title: "Global headline", source: "Wire", published: "2026-08-09T11:00:00Z" }],
      },
      central_bank_rates: {
        rates: [{ bank: "ECB", rate: 2.5, as_of: "2026-08-09T10:00:00Z" }],
      },
      election_calendar: {
        elections: [{ country: "France", date: "2026-08-10", election_type: "议会选举", risk_score: 80 }],
      },
      market_quotes: {
        quotes: [{ symbol: "SPX", change_pct: -2.4, price: 6100 }],
      },
      military_bases: {
        bases: [{ id: "base-1", name: "Static Base", latitude: 35, longitude: 139 }],
      },
      acled_events: {
        events: [{ id: "a1", location: "Test City", latitude: 10, longitude: 20, fatalities: 2, event_date: "2026-08-09" }],
      },
      military_flights: {
        aircraft: [
          { icao24: "civil", callsign: "UAL676", latitude: 30, longitude: -80, origin_country: "United States" },
          { icao24: "mil", callsign: "RCH123", latitude: 31, longitude: -81, origin_country: "United States" },
        ],
      },
    });

    expect(new Set(events.map((event) => event.category))).toEqual(
      new Set(["news", "policy", "market", "conflict", "military"]),
    );
    expect(events).toEqual(expect.arrayContaining([
      expect.objectContaining({ title: "ECB 政策利率 2.50%", category: "policy" }),
      expect.objectContaining({ title: "France 议会选举", countryCode: "FRA" }),
      expect.objectContaining({ title: "SPX 下跌 2.40%", severity: "high" }),
    ]));
    expect(events.some((event) => event.title === "Static Base")).toBe(false);
    expect(events.some((event) => event.title === "UAL676")).toBe(false);
    const aircraftObservation = events.find((event) => event.title === "RCH123");
    expect(aircraftObservation).toEqual(expect.objectContaining({
      recordKind: "observation",
      severity: "info",
    }));
    expect(aircraftObservation && isActionableGlobalIntelEvent(aircraftObservation)).toBe(false);
    expect(events.map((event) => Date.parse(event.timestamp))).toEqual(
      [...events].map((event) => Date.parse(event.timestamp)).sort((left, right) => right - left),
    );
  });
});

describe("createGlobalIntelDataSource", () => {
  it("uses the Newma-Desk gateway for snapshots and closes the SSE stream", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: "ok" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }));
    const close = vi.fn();
    const sourceState: {
      onopen: null | (() => void);
      onmessage: null | ((event: MessageEvent<string>) => void);
      onerror: null | (() => void);
      close: () => void;
    } = { onopen: null, onmessage: null, onerror: null, close };
    const eventSourceFactory = vi.fn(() => sourceState as unknown as EventSource);
    const source = createGlobalIntelDataSource({
      baseUrl: "https://desk.example/root",
      fetch: fetcher,
      eventSourceFactory,
    });

    await expect(source.staticSnapshot()).resolves.toEqual({ status: "ok" });
    expect(fetcher).toHaveBeenCalledWith(
      "https://desk.example/api/global-intel/static",
      expect.objectContaining({ headers: { Accept: "application/json" } }),
    );

    const onPayload = vi.fn();
    const onStatus = vi.fn();
    const unsubscribe = source.subscribe(onPayload, onStatus);
    sourceState.onopen?.();
    sourceState.onmessage?.({ data: JSON.stringify({ timestamp: "now" }) } as MessageEvent<string>);

    expect(eventSourceFactory).toHaveBeenCalledWith("https://desk.example/api/global-intel/stream");
    expect(onStatus).toHaveBeenNthCalledWith(1, "connecting");
    expect(onStatus).toHaveBeenNthCalledWith(2, "live");
    expect(onPayload).toHaveBeenCalledWith({ timestamp: "now" });
    sourceState.onerror?.();
    expect(onStatus).toHaveBeenLastCalledWith("degraded");
    unsubscribe();
    expect(close).toHaveBeenCalledOnce();
  });
});
