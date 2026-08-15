import { describe, expect, it, vi } from "vitest";

import {
  createModSnapshotCache,
  refreshWithModSnapshot,
  type ModCacheStorage,
} from "./cache";

function memoryStorage(): ModCacheStorage {
  const values = new Map<string, string>();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => { values.set(key, value); },
    removeItem: (key) => { values.delete(key); },
  };
}

describe("Mod last-success cache", () => {
  it("isolates snapshots by workspace, Mod and resource", () => {
    const storage = memoryStorage();
    const first = createModSnapshotCache<{ value: number }>({
      modId: "market-daily",
      workspaceId: "desk-a",
      resourceKey: "quote:CN:600519",
      storage,
    });
    const second = createModSnapshotCache<{ value: number }>({
      modId: "market-daily",
      workspaceId: "desk-b",
      resourceKey: "quote:CN:600519",
      storage,
    });

    first.write({ value: 12 }, "2026-08-13T00:00:00.000Z");

    expect(first.read()).toEqual({
      schemaVersion: 1,
      updatedAt: "2026-08-13T00:00:00.000Z",
      value: { value: 12 },
    });
    expect(second.read()).toBeUndefined();
  });

  it("drops incompatible or oversized snapshots without breaking the caller", () => {
    const storage = memoryStorage();
    const first = createModSnapshotCache<string>({
      modId: "news-radar",
      workspaceId: "desk-a",
      resourceKey: "feed",
      schemaVersion: 1,
      maxBytes: 80,
      storage,
    });
    const nextVersion = createModSnapshotCache<string>({
      modId: "news-radar",
      workspaceId: "desk-a",
      resourceKey: "feed",
      schemaVersion: 2,
      storage,
    });

    expect(first.write("x".repeat(200))).toBeUndefined();
    first.write("last good");
    expect(nextVersion.read()).toBeUndefined();
  });

  it("keeps current or cached data when a refresh fails", async () => {
    const cache = createModSnapshotCache<{ rows: number[] }>({
      modId: "market-scanner",
      workspaceId: "desk-a",
      resourceKey: "scan:ALL",
      storage: memoryStorage(),
    });
    cache.write({ rows: [1, 2] }, "2026-08-13T00:00:00.000Z");
    const load = vi.fn().mockRejectedValue(new Error("offline"));

    await expect(refreshWithModSnapshot({ cache, load })).resolves.toMatchObject({
      value: { rows: [1, 2] },
      source: "cache",
      error: expect.any(Error),
    });
    await expect(refreshWithModSnapshot({
      cache,
      load,
      current: { rows: [3] },
    })).resolves.toMatchObject({
      value: { rows: [3] },
      source: "current",
    });
  });

  it("atomically replaces the last-good snapshot after success", async () => {
    const cache = createModSnapshotCache<{ rows: number[] }>({
      modId: "market-scanner",
      workspaceId: "desk-a",
      resourceKey: "scan:ALL",
      storage: memoryStorage(),
    });

    const result = await refreshWithModSnapshot({
      cache,
      load: async () => ({ rows: [4, 5] }),
    });

    expect(result).toMatchObject({ value: { rows: [4, 5] }, source: "network" });
    expect(cache.read()?.value).toEqual({ rows: [4, 5] });
  });
});
