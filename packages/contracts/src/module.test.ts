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

  it("rejects an external entry with a non-HTTP protocol", () => {
    expect(() =>
      moduleManifestSchema.parse({
        ...valid,
        entry: { type: "external", url: "javascript:alert(1)" },
      }),
    ).toThrow();
  });
});
