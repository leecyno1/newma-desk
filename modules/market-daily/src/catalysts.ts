import type { CatalystEvent } from "@newma-desk/contracts";

import type { MarketEvidenceEvent, SecurityRef } from "./types";

export function marketEvidenceToCatalyst(
  event: MarketEvidenceEvent,
  security: SecurityRef,
): CatalystEvent {
  const timestamp = event.timestamp < 1_000_000_000_000
    ? event.timestamp * 1000
    : event.timestamp;
  const date = new Date(timestamp).toISOString().slice(0, 10);
  return {
    id: event.id,
    type: event.type,
    date,
    timePrecision: "date",
    status: "confirmed",
    title: event.title,
    summary: event.detail,
    source: {
      id: event.source.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "market-evidence",
      label: event.source,
      ...(event.url ? { url: event.url } : {}),
    },
    evidenceIds: [event.evidenceId],
    asOf: date,
    freshness: { status: "unknown" },
    confidence: {
      level: "high",
      rationale: "已发生的公开市场证据；事件影响仍需结合原文核实",
    },
    impactedAssets: [{
      market: security.market,
      symbol: security.symbol,
      ...(security.name ? { name: security.name } : {}),
    }],
    expectedDirection: "unknown",
    confirmationConditions: ["来源原文与发布日期可复核"],
    invalidationConditions: ["来源撤回、更正或事件与标的身份不匹配"],
    importance: event.type === "earnings" || event.type === "announcement" ? "high" : "medium",
  };
}
