import { describe, expect, it, vi } from "vitest";

import {
  GatewayError,
  normalizeGatewayBaseUrl,
  requestGatewayJson,
} from "./gateway";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("Gateway helpers", () => {
  it("accepts only an HTTP(S) origin", () => {
    expect(normalizeGatewayBaseUrl("http://localhost:8901/")).toBe(
      "http://localhost:8901",
    );
    expect(() => normalizeGatewayBaseUrl("https://desk.example/api")).toThrow();
    expect(() => normalizeGatewayBaseUrl("javascript:alert(1)")).toThrow();
  });

  it("returns JSON and normalizes an HTTP error", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ ok: true }))
      .mockResolvedValueOnce(
        jsonResponse({ error: { message: "上游不可用" } }, 503),
      );

    await expect(
      requestGatewayJson<{ ok: boolean }>(fetch, "https://desk.example/data"),
    ).resolves.toEqual({ ok: true });
    await expect(
      requestGatewayJson(fetch, "https://desk.example/data"),
    ).rejects.toEqual(
      expect.objectContaining<Partial<GatewayError>>({
        status: 503,
        detail: "上游不可用",
      }),
    );
  });
});
