import { describe, expect, it } from "vitest";

import {
  modWikiProfileSchema,
  wikiHandoffSchema,
  wikiLinkResolutionResponseSchema,
  wikiPageContextSchema,
  wikiSubjectMatchSchema,
  wikiSubjectRefSchema,
} from "./wiki";

const stock = {
  type: "security",
  canonicalId: "security:CN:300308",
  displayName: "中际旭创",
  market: "CN",
  symbol: "300308",
  assetType: "stock",
} as const;

describe("Wiki contracts", () => {
  it("keeps asset type inside the canonical identity", () => {
    expect(wikiSubjectRefSchema.parse(stock)).toEqual(stock);
    expect(() =>
      wikiSubjectRefSchema.parse({
        ...stock,
        type: "fund",
      }),
    ).toThrow(/prefix/);
    expect(() =>
      wikiSubjectRefSchema.parse({
        type: "fund",
        canonicalId: "fund:CN:300308",
        displayName: "错误基金",
      }),
    ).toThrow(/market and symbol/);
  });

  it("validates a Mod Wiki profile with structured entrypoints", () => {
    const profile = modWikiProfileSchema.parse({
      contractVersion: "1.0",
      subjectTypes: ["security", "etf"],
      concepts: ["technical-analysis", "czsc"],
      entrypoints: [
        {
          id: "structure",
          intent: "technical.structure",
          label: "CZSC 结构",
          contextContract: "newma.wiki.subject.v1",
          defaults: { period: "daily", bars: 480 },
        },
      ],
    });

    expect(profile.entrypoints[0]?.defaults).toEqual({
      period: "daily",
      bars: 480,
    });
  });

  it("validates page context and a short-lived handoff", () => {
    expect(
      wikiPageContextSchema.parse({
        primarySubject: stock,
        relatedSubjects: [],
        conceptIds: ["concept:CN:CPO", "topic:AI算力"],
        intent: "market.overview",
        timeframe: "daily",
      }).primarySubject.canonicalId,
    ).toBe("security:CN:300308");

    const handoff = wikiHandoffSchema.parse({
      version: 1,
      id: "hf_abc12345",
      sourceModId: "market-daily",
      targetModId: "instock-czsc",
      entrypointId: "structure",
      subject: stock,
      relatedSubjects: [],
      conceptIds: ["concept:CN:CPO"],
      intent: "technical.structure",
      timeframe: "daily",
      parameters: { bars: 480 },
      createdAt: "2026-08-15T10:00:00+08:00",
      expiresAt: "2026-08-15T10:05:00+08:00",
    });

    expect(handoff.parameters.bars).toBe(480);
  });

  it("validates resolved cross-Mod links", () => {
    const resolution = wikiLinkResolutionResponseSchema.parse({
      sourceModId: "market-daily",
      subject: stock,
      links: [
        {
          id: "instock-czsc:structure",
          targetModId: "instock-czsc",
          targetRevision: 2,
          entrypointId: "structure",
          intent: "technical.structure",
          label: "CZSC 结构",
          reason: "支持同一证券对象",
          score: 85,
          match: {
            subjectType: "security",
            intentScore: 25,
            concepts: ["cpo"],
            dataCapabilities: ["market.ohlcv"],
          },
        },
      ],
      generatedAt: "2026-08-15T10:00:00+08:00",
    });

    expect(resolution.links[0]?.targetModId).toBe("instock-czsc");
  });

  it("validates normalized subject search results", () => {
    const match = wikiSubjectMatchSchema.parse({
      subject: stock,
      aliases: ["中际旭创", "300308", "zjxc"],
      conceptIds: ["concept:CN:cpo"],
      source: "market.symbol-search",
      matchedBy: "alias",
      confidence: 0.95,
    });

    expect(match.subject.canonicalId).toBe("security:CN:300308");
    expect(match.aliases).toContain("zjxc");
  });

  it("rejects duplicate entrypoints and expired handoff ranges", () => {
    expect(() =>
      modWikiProfileSchema.parse({
        contractVersion: "1.0",
        subjectTypes: ["security"],
        entrypoints: [
          {
            id: "overview",
            intent: "market.overview",
            label: "概览",
            contextContract: "newma.wiki.subject.v1",
          },
          {
            id: "overview",
            intent: "market.timeline",
            label: "时间轴",
            contextContract: "newma.wiki.subject.v1",
          },
        ],
      }),
    ).toThrow(/unique/);

    expect(() =>
      wikiHandoffSchema.parse({
        version: 1,
        id: "hf_abc12345",
        sourceModId: "market-daily",
        targetModId: "event-timeline",
        entrypointId: "timeline",
        subject: stock,
        intent: "market.timeline",
        createdAt: "2026-08-15T10:05:00+08:00",
        expiresAt: "2026-08-15T10:00:00+08:00",
      }),
    ).toThrow(/expiry/);
  });
});
