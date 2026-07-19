import { describe, expect, it } from "vitest";

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

describe("moduleManifestSchema", () => {
  it("parses a valid module manifest", () => {
    expect(moduleManifestSchema.parse(valid)).toEqual(valid);
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
});
