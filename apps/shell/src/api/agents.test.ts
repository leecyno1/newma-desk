import { afterEach, describe, expect, it, vi } from "vitest";

import { probeAgent } from "./agents";

describe("probeAgent", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("uses a real installed Mod instead of an internal settings pseudo id", async () => {
    const fetchMock = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "task-1", status: "queued" }), {
          status: 202,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: "task-1",
            status: "completed",
            result: { answer: "NEWMA_DESK_AGENT_OK" },
          }),
          {
            status: 200,
            headers: { "Content-Type": "application/json" },
          },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      probeAgent("user-1", "codex-cli", "market-daily"),
    ).resolves.toBe("NEWMA_DESK_AGENT_OK");

    const firstCall = fetchMock.mock.calls[0];
    expect(firstCall).toBeDefined();
    const init = firstCall?.[1];
    expect(JSON.parse(String(init?.body))).toMatchObject({
      moduleId: "market-daily",
      adapter: "codex-cli",
    });
  });
});
