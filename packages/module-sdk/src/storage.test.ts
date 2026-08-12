import { describe, expect, it, vi } from "vitest";

import { createModStorageClient } from "./storage";


function jsonResponse(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("createModStorageClient", () => {
  it("writes through the scoped Mod storage endpoint with session headers", async () => {
    const document = {
      moduleId: "research-notes",
      namespace: "settings",
      key: "layout",
      schemaVersion: 1,
      revision: 1,
      value: { density: "compact" },
      sizeBytes: 21,
      createdAt: "2026-08-01T00:00:00Z",
      updatedAt: "2026-08-01T00:00:00Z",
    };
    const fetcher = vi.fn().mockResolvedValue(jsonResponse(document));
    const client = createModStorageClient({
      baseUrl: "https://desk.example",
      modId: "research-notes",
      accessToken: "session-token",
      instanceId: "instance-1",
      fetch: fetcher,
    });

    await expect(
      client.put("settings", "layout", { density: "compact" }, 0),
    ).resolves.toEqual(document);
    expect(fetcher).toHaveBeenCalledWith(
      "https://desk.example/api/mods/research-notes/storage/settings/layout",
      expect.objectContaining({
        method: "PUT",
        credentials: "omit",
        redirect: "error",
        body: JSON.stringify({
          expectedRevision: 0,
          value: { density: "compact" },
        }),
      }),
    );
    const headers = new Headers(fetcher.mock.calls[0]?.[1]?.headers);
    expect(headers.get("Authorization")).toBe("Bearer session-token");
    expect(headers.get("X-Newma-Desk-Instance-Id")).toBe("instance-1");
  });

  it("supports cursor pagination and optimistic delete", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ items: [], nextCursor: "page-2" }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    const client = createModStorageClient({
      baseUrl: "https://desk.example",
      modId: "research-notes",
      accessToken: "session-token",
      instanceId: "instance-1",
      fetch: fetcher,
    });

    await client.list("notes", { cursor: "note-10", limit: 20 });
    await client.delete("notes", "note-10", 3);

    expect(fetcher.mock.calls[0]?.[0]).toBe(
      "https://desk.example/api/mods/research-notes/storage/notes?cursor=note-10&limit=20",
    );
    expect(fetcher.mock.calls[1]?.[0]).toBe(
      "https://desk.example/api/mods/research-notes/storage/notes/note-10?expectedRevision=3",
    );
  });
});
