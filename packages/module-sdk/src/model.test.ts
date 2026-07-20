import { describe, expect, it, vi } from "vitest";

import { GatewayError } from "./agent";
import { createModelClient } from "./model";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("createModelClient", () => {
  it("invokes the Model Gateway without creating an Agent task", async () => {
    const fetch = vi.fn(
      async (_input: RequestInfo | URL, _init?: RequestInit) => jsonResponse({
        answer: "模型回答",
        adapter: "openai-compatible",
        model: "gpt-5.6",
      }),
    );
    const client = createModelClient({
      baseUrl: "http://localhost:8901",
      fetch,
    });

    const response = await client.createResponse({
      moduleId: "market-daily",
      prompt: "解释行情",
      model: "gpt-5.6",
    });

    expect(response.answer).toBe("模型回答");
    expect(fetch).toHaveBeenCalledWith(
      "http://localhost:8901/api/model/responses",
      expect.objectContaining({ method: "POST" }),
    );
    expect(String(fetch.mock.calls[0]?.[0])).not.toContain("/api/agent/");
  });

  it("lists model providers and exposes safe model errors", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse({
          providers: [
            {
              id: "openai-compatible",
              capabilities: ["chat"],
              default: true,
            },
          ],
        }),
      )
      .mockResolvedValueOnce(
        jsonResponse(
          { error: { code: "missing_api_key", message: "未配置模型" } },
          503,
        ),
      );
    const client = createModelClient({
      baseUrl: "http://localhost:8901",
      fetch,
    });

    expect(await client.listProviders()).toHaveLength(1);
    await expect(client.createResponse({ prompt: "hello" })).rejects.toEqual(
      expect.objectContaining<Partial<GatewayError>>({
        status: 503,
        detail: "未配置模型",
      }),
    );
  });
});
