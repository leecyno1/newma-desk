import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { getModRevision, listMods } from "./modules";
import { server } from "../test/server";

describe("Mod registry API", () => {
  it("reports a non-success registry status", async () => {
    server.use(
      http.get("/api/mods", () => new HttpResponse(null, { status: 502 })),
    );

    await expect(listMods()).rejects.toThrow("mod registry returned 502");
  });

  it("encodes both exact-revision path segments", async () => {
    let requestPath = "";
    server.use(
      http.get("/api/mods/:modId/revisions/:revision", ({ request }) => {
        requestPath = new URL(request.url).pathname;
        return HttpResponse.json({
          moduleId: "market/daily",
          revision: 7,
          status: "draft",
          manifest: {
            schemaVersion: "1.0",
            id: "market-daily",
            name: "每日股票行情",
            version: "0.1.0",
            category: "market",
            entry: { type: "structured", url: "/modules/market-daily/" },
            permissions: [],
            dataServices: [],
            agentCapabilities: [],
            events: { emits: [], accepts: [] },
          },
          createdAt: "2026-07-20T00:00:00Z",
        });
      }),
    );

    await getModRevision("market/daily", "7?draft=true");

    expect(requestPath).toBe(
      "/api/mods/market%2Fdaily/revisions/7%3Fdraft%3Dtrue",
    );
  });
});
