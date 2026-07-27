import { describe, expect, it } from "vitest";

import { resolveParentOrigin } from "./runtimeOrigin";

const baseRuntime = {
  embedded: true,
  ancestorOrigins: [] as string[],
  referrer: "",
  currentOrigin: "http://127.0.0.1:5891",
};

describe("resolveParentOrigin", () => {
  it("prefers the actual embedded Desk ancestor over a stale build-time value", () => {
    expect(resolveParentOrigin("http://127.0.0.1:5891", {
      ...baseRuntime,
      ancestorOrigins: ["http://127.0.0.1:5888"],
    })).toBe("http://127.0.0.1:5888");
  });

  it("uses an origin-only referrer when ancestorOrigins is unavailable", () => {
    expect(resolveParentOrigin(undefined, {
      ...baseRuntime,
      referrer: "https://desk.example/workspace?mod=market-daily",
    })).toBe("https://desk.example");
  });

  it("falls back to the configured origin for standalone-compatible browsers", () => {
    expect(resolveParentOrigin("https://desk.example", {
      ...baseRuntime,
      embedded: false,
    })).toBe("https://desk.example");
  });
});
