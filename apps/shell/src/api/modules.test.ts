import { HttpResponse, http } from "msw";
import { describe, expect, it } from "vitest";

import { getModuleRevision, listModules } from "./modules";
import { server } from "../test/server";

describe("module registry API", () => {
  it("reports a non-success registry status", async () => {
    server.use(
      http.get("/api/modules", () => new HttpResponse(null, { status: 502 })),
    );

    await expect(listModules()).rejects.toThrow("module registry returned 502");
  });

  it("encodes both exact-revision path segments", async () => {
    let requestPath = "";
    server.use(
      http.get("/api/modules/:moduleId/revisions/:revision", ({ request }) => {
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

    await getModuleRevision("market/daily", "7?draft=true");

    expect(requestPath).toBe(
      "/api/modules/market%2Fdaily/revisions/7%3Fdraft%3Dtrue",
    );
  });
});
