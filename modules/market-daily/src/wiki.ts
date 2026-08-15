import type {
  WikiHandoff,
  WikiPageContext,
  WikiSubjectRef,
} from "@newma-desk/contracts";

import { isEtfSecurity, isOpenFundSecurity } from "./data";
import type { SecurityRef } from "./types";

export function wikiSubjectForSecurity(security: SecurityRef): WikiSubjectRef {
  const type = isOpenFundSecurity(security)
    ? "fund"
    : isEtfSecurity(security)
      ? "etf"
      : "security";
  return {
    type,
    canonicalId: `${type}:${security.market}:${security.symbol}`,
    displayName: security.name,
    market: security.market,
    symbol: security.symbol,
    assetType: type === "security" ? "stock" : type,
  };
}

export function wikiContextForSecurity(input: {
  security: SecurityRef;
  intent: string;
  timeframe?: string;
  snapshotId?: string;
}): WikiPageContext {
  return {
    primarySubject: wikiSubjectForSecurity(input.security),
    relatedSubjects: [],
    conceptIds: [],
    intent: input.intent,
    ...(input.timeframe ? { timeframe: input.timeframe } : {}),
    ...(input.snapshotId ? { snapshotId: input.snapshotId } : {}),
  };
}

export function securityFromWikiHandoff(handoff: WikiHandoff): SecurityRef {
  const { subject } = handoff;
  if (
    !subject.market ||
    !subject.symbol ||
    !["security", "etf", "fund"].includes(subject.type)
  ) {
    throw new Error("Wiki 交接未包含可交易标的");
  }
  return {
    symbol: subject.symbol,
    name: subject.displayName,
    market: subject.market,
    assetType: subject.assetType,
    ...(subject.type === "fund" ? { exchange: "OTC", securityType: "fund" } : {}),
  };
}
