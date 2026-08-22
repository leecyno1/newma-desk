import { describe, expect, it } from "vitest";

import manifestParity from "../../../tests/fixtures/mod-manifest-parity.json";

import { moduleManifestSchema } from "./module";

const valid = {
  schemaVersion: "1.0",
  id: "market-daily",
  name: "每日股票行情",
  version: "0.1.0",
  category: "market",
  entry: { type: "structured", url: "/modules/market-daily/" },
  permissions: ["market.read"],
  dataServices: ["market-data"],
  agentCapabilities: ["market.refresh"],
  events: { emits: ["security.selected"], accepts: ["date.changed"] },
};

const connected = {
  schemaVersion: "1.1",
  id: "factor-lab",
  name: "因子实验室",
  version: "1.0.0",
  category: "quant",
  entry: { type: "external", url: "https://quant.example/mod" },
  compatibility: {
    level: 2,
    bridgeProtocol: "1.0",
    sdkVersion: "^0.2.0",
  },
  permissions: ["quant.execute", "research.read"],
  dataServices: ["vibe-trading"],
  actions: {
    "factor.backtest": {
      binding: {
        type: "data",
        service: "vibe-trading",
        capability: "factor.backtest",
      },
      execution: "task",
      permission: "quant.execute",
      inputSchema: "./schemas/factor-backtest.input.json",
      outputSchema: "./schemas/factor-backtest.output.json",
      confirmation: "user",
    },
    "research.explain": {
      binding: {
        type: "agent",
        memoryScope: "user-agent-mod",
      },
      execution: "task",
      permission: "research.read",
    },
  },
  events: { emits: [], accepts: [] },
} as const;

describe("moduleManifestSchema", () => {
  it.each(manifestParity.cases)(
    "keeps the shared manifest contract aligned for $id",
    ({ expectedValid, manifest }) => {
      expect(moduleManifestSchema.safeParse(manifest).success).toBe(expectedValid);
    },
  );

  it("parses a valid module manifest", () => {
    expect(moduleManifestSchema.parse(valid)).toEqual(valid);
  });

  it("preserves optional navigation metadata", () => {
    const navigation = {
      groupLabel: "市场",
      groupOrder: 20,
      itemOrder: 10,
      label: "行情",
      directory: {
        id: "market-suite",
        label: "市场工具",
        order: 5,
      },
      project: {
        id: "vibe-research",
        name: "Vibe Research",
        order: 20,
        description: "统一承载投研页面。",
        logo: { type: "letter", text: "VR" },
      },
      icon: "market",
    };

    expect(moduleManifestSchema.parse({ ...valid, navigation })).toEqual({
      ...valid,
      navigation,
    });
  });

  it.each(["today", "trading", "settings"] as const)(
    "accepts the %s first-party navigation icon",
    (icon) => {
      expect(
        moduleManifestSchema.parse({
          ...valid,
          navigation: {
            groupLabel: "工作区",
            groupOrder: 10,
            itemOrder: 10,
            icon,
          },
        }).navigation?.icon,
      ).toBe(icon);
    },
  );

  it("keeps manifests without navigation metadata valid", () => {
    expect(moduleManifestSchema.parse(valid)).not.toHaveProperty("navigation");
  });

  it("preserves host-owned presentation metadata", () => {
    const presentation = {
      englishName: "Market Daily",
      description: "统一查看行情、盘口与技术指标。",
      titleOwner: "host" as const,
    };

    expect(moduleManifestSchema.parse({ ...valid, presentation })).toMatchObject({
      presentation,
    });
  });

  it.each([
    { type: "icon", name: "trading" },
    { type: "letter", text: "VT" },
    { type: "image", src: "/assets/vibe-trading.png", alt: "Vibe Trading" },
    { type: "image", src: "https://assets.example/vibe-trading.png" },
  ] as const)("accepts a safe project logo declaration", (logo) => {
    const parsed = moduleManifestSchema.parse({
      ...valid,
      navigation: {
        groupLabel: "研究",
        groupOrder: 20,
        itemOrder: 10,
        project: {
          id: "vibe-trading",
          name: "Vibe Trading",
          logo,
        },
      },
    });

    expect(parsed.navigation?.project).toMatchObject({
      id: "vibe-trading",
      name: "Vibe Trading",
      order: 100,
      logo,
    });
  });

  it.each([
    { type: "letter", text: "LONG" },
    { type: "letter", text: " " },
    { type: "image", src: "javascript:alert(1)" },
    { type: "image", src: "/%2e%2e/secret.png" },
    { type: "icon", name: "unregistered" },
  ])("rejects an unsafe project logo declaration", (logo) => {
    expect(() =>
      moduleManifestSchema.parse({
        ...valid,
        navigation: {
          groupLabel: "研究",
          groupOrder: 20,
          itemOrder: 10,
          project: {
            id: "vibe-research",
            name: "Vibe Research",
            logo,
          },
        },
      }),
    ).toThrow();
  });

  it("rejects negative navigation order values", () => {
    expect(() =>
      moduleManifestSchema.parse({
        ...valid,
        navigation: {
          groupLabel: "市场",
          groupOrder: -1,
          itemOrder: 10,
          icon: "market",
        },
      }),
    ).toThrow();
  });

  it("rejects unknown navigation fields", () => {
    expect(() =>
      moduleManifestSchema.parse({
        ...valid,
        navigation: {
          groupLabel: "市场",
          groupOrder: 20,
          itemOrder: 10,
          icon: "market",
          color: "red",
        },
      }),
    ).toThrow();
  });

  it("rejects a static entry with an unsafe relative URL", () => {
    expect(() =>
      moduleManifestSchema.parse({
        ...valid,
        entry: { type: "static", url: "../secret" },
      }),
    ).toThrow();
  });

  it.each(["//evil.example/app", "/%2e%2e/secret", "/%ZZ"])(
    "rejects the unsafe local entry URL %s",
    (url) => {
      expect(() =>
        moduleManifestSchema.parse({
          ...valid,
          entry: { type: "static", url },
        }),
      ).toThrow();
    },
  );

  it("rejects an external entry with a non-HTTP protocol", () => {
    expect(() =>
      moduleManifestSchema.parse({
        ...valid,
        entry: { type: "external", url: "javascript:alert(1)" },
      }),
    ).toThrow();
  });

  it("requires cron for scheduled refreshes", () => {
    expect(() =>
      moduleManifestSchema.parse({
        ...valid,
        refresh: { mode: "schedule" },
      }),
    ).toThrow();
  });

  it("forbids cron for manual refreshes", () => {
    expect(() =>
      moduleManifestSchema.parse({
        ...valid,
        refresh: { mode: "manual", cron: "* * * * *" },
      }),
    ).toThrow();
  });

  it("rejects an unnamespaced manifest event", () => {
    expect(() =>
      moduleManifestSchema.parse({
        ...valid,
        events: { emits: ["selected"], accepts: [] },
      }),
    ).toThrow();
  });

  it("rejects unknown nested fields", () => {
    expect(() =>
      moduleManifestSchema.parse({
        ...valid,
        entry: {
          type: "structured",
          url: "/modules/market-daily/",
          sandbox: false,
        },
      }),
    ).toThrow();
  });

  it("parses a Level 2 Manifest 1.1 with explicit action bindings", () => {
    expect(moduleManifestSchema.parse(connected)).toEqual({
      ...connected,
      actions: {
        ...connected.actions,
        "research.explain": {
          ...connected.actions["research.explain"],
          confirmation: "none",
        },
      },
    });
  });

  it("accepts a versioned Wiki profile on Manifest 1.1", () => {
    const parsed = moduleManifestSchema.parse({
      ...connected,
      wiki: {
        contractVersion: "1.0",
        subjectTypes: ["security", "etf"],
        concepts: ["technical-analysis"],
        entrypoints: [
          {
            id: "structure",
            intent: "technical.structure",
            label: "结构",
            contextContract: "newma.wiki.subject.v1",
          },
        ],
      },
    });

    expect(parsed.schemaVersion).toBe("1.1");
    if (parsed.schemaVersion !== "1.1") throw new Error("expected Manifest 1.1");
    expect(parsed.wiki?.entrypoints[0]?.id).toBe("structure");
  });

  it("keeps Wiki profiles unavailable to legacy Manifest 1.0", () => {
    expect(() =>
      moduleManifestSchema.parse({
        ...valid,
        wiki: {
          contractVersion: "1.0",
          subjectTypes: ["security"],
          entrypoints: [
            {
              id: "overview",
              intent: "market.overview",
              label: "概览",
              contextContract: "newma.wiki.subject.v1",
            },
          ],
        },
      }),
    ).toThrow();
  });

  it("requires Level 3 Mods to declare the ViewSpec version", () => {
    expect(() =>
      moduleManifestSchema.parse({
        ...connected,
        compatibility: {
          level: 3,
          bridgeProtocol: "1.0",
        },
      }),
    ).toThrow(/ViewSpec/);
  });

  it("prevents a Level 1 Mod from declaring connected actions", () => {
    expect(() =>
      moduleManifestSchema.parse({
        ...connected,
        compatibility: {
          level: 1,
          bridgeProtocol: "1.0",
        },
      }),
    ).toThrow(/Level 1/);
  });

  it("requires every action permission and data service to be declared", () => {
    expect(() =>
      moduleManifestSchema.parse({
        ...connected,
        permissions: ["research.read"],
        dataServices: [],
      }),
    ).toThrow();
  });

  it("accepts a data action without a fixed service for Desk unified routing", () => {
    const unified = {
      ...connected,
      dataServices: [],
      actions: {
        "market.quote": {
          binding: {
            type: "data",
            capability: "market.quote",
          },
          execution: "request",
          permission: "research.read",
        },
      },
    } as const;

    const parsed = moduleManifestSchema.parse(unified);
    if (parsed.schemaVersion !== "1.1") throw new Error("expected Manifest 1.1");
    expect(parsed.actions["market.quote"]).toEqual({
      ...unified.actions["market.quote"],
      confirmation: "none",
    });
  });

  it("accepts explicit execution profiles for model and Agent actions", () => {
    const parsed = moduleManifestSchema.parse({
      ...connected,
      actions: {
        ...connected.actions,
        "research.batch": {
          binding: {
            type: "agent",
            capability: "research.batch",
            memoryScope: "task",
            profile: "batch",
          },
          execution: "task",
          permission: "research.read",
        },
        "research.quick": {
          binding: {
            type: "model",
            capability: "research.quick",
            profile: "quick",
          },
          execution: "request",
          permission: "research.read",
        },
      },
    });

    if (parsed.schemaVersion !== "1.1") throw new Error("expected Manifest 1.1");
    expect(parsed.actions["research.batch"]!.binding).toMatchObject({
      type: "agent",
      profile: "batch",
    });
    expect(parsed.actions["research.quick"]!.binding).toMatchObject({
      type: "model",
      profile: "quick",
    });
  });

  it("accepts a bounded Desk-managed storage declaration", () => {
    const parsed = moduleManifestSchema.parse({
      ...connected,
      permissions: [
        ...connected.permissions,
        "storage.read",
        "storage.write",
      ],
      storage: {
        mode: "desk-managed",
        namespaces: [
          {
            id: "settings",
            schemaVersion: 1,
            quotaMb: 2,
          },
        ],
      },
    });

    if (parsed.schemaVersion !== "1.1") throw new Error("expected Manifest 1.1");
    expect(parsed.storage).toEqual({
      mode: "desk-managed",
      namespaces: [
        {
          id: "settings",
          scope: "user-workspace",
          schemaVersion: 1,
          quotaMb: 2,
          maxItemKb: 256,
        },
      ],
    });
  });

  it("rejects duplicate namespaces and missing storage permissions", () => {
    expect(() =>
      moduleManifestSchema.parse({
        ...connected,
        storage: {
          mode: "desk-managed",
          namespaces: [
            { id: "settings", schemaVersion: 1, quotaMb: 2 },
            { id: "settings", schemaVersion: 2, quotaMb: 2 },
          ],
        },
      }),
    ).toThrow();
  });

  it("keeps storage declarations out of legacy Manifest 1.0", () => {
    expect(() =>
      moduleManifestSchema.parse({
        ...valid,
        storage: { mode: "stateless" },
      }),
    ).toThrow();
  });
});
