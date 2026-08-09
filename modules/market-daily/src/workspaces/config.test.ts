import { describe, expect, it } from "vitest";

import { MARKET_WORKSPACES } from "./config";

describe("market workspace theme", () => {
  it("uses the shared Newma accent for every workspace", () => {
    expect(new Set(Object.values(MARKET_WORKSPACES).map((workspace) => workspace.accent)))
      .toEqual(new Set(["var(--vibe-accent)"]));
  });
});
