import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ModHostConnection } from "@newma-desk/mod-sdk";
import { createStorageRequest, type StorageSession, useStorageSession } from "./storageAccess";
import { createWatchlistClient } from "./watchlist";
import { createMarketAlertClient, useMarketAlerts, type MarketAlertClient, type PriceAlert } from "./alerts";

type Host = Extract<ModHostConnection, { embedded: true }>;
function config(user = "alice"): Host["config"] {
  return {
    type: "vibedesk:init", protocolVersion: "1.0", modId: "market-daily", instanceId: user + "-instance",
    user: { id: user }, workspace: { id: user + "-workspace" },
    environment: { theme: "light", locale: "zh-CN", timezone: "Asia/Shanghai" },
    gateways: { data: "https://desk.example/api/data", actions: "https://desk.example/api/actions" },
    grants: { permissions: ["storage.read", "storage.write"], actions: [] },
    session: { id: user, accessToken: user + "-synthetic-token", expiresAt: new Date(Date.now() + 600000).toISOString() },
  };
}
const watchlist = (user = "alice") => ({ userId: user, workspaceId: user + "-workspace", revision: 0, groups: [] });
const session = (): StorageSession => ({ config: config(), isCurrent: () => true });
const options = () => ({ baseUrl: "https://ignored.example", userId: "forged", workspaceId: "forged", session: session() });
const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

describe("signed market storage", () => {
  it("uses the signed origin and instance without Cookie or caller-selected ownership", async () => {
    const fetcher = vi.fn(async () => response(watchlist()));
    const client = createWatchlistClient({ ...options(), fetch: fetcher });
    await client.load();
    expect(fetcher).toHaveBeenCalledWith("https://desk.example/api/watchlists", expect.objectContaining({
      credentials: "omit", redirect: "error", cache: "no-store",
      headers: { Accept: "application/json", "Content-Type": "application/json", Authorization: "Bearer alice-synthetic-token", "X-Newma-Desk-Instance-Id": "alice-instance" },
    }));
  });

  it.each(["missing", "expired", "readonly"])("does not send an unauthorized %s write", async (mode) => {
    const input = options();
    if (mode === "missing") input.session.config.session = undefined;
    if (mode === "expired") input.session.config.session!.expiresAt = "2000-01-01T00:00:00Z";
    if (mode === "readonly") input.session.config.grants.permissions = ["storage.read"];
    const fetcher = vi.fn();
    const client = createMarketAlertClient({ ...input, fetch: fetcher });
    await expect(client.create({ security: { symbol: "AAPL", name: "Apple", market: "US" }, direction: "above", price: 250 })).rejects.toMatchObject({ status: mode === "readonly" ? 403 : 401 });
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("rejects stale reads and writes without retries or anonymous fallback", async () => {
    for (const method of ["GET", "POST"]) {
      const pending = deferred<Response>();
      const input = options();
      let current = true;
      input.session.isCurrent = () => current;
      const fetcher = vi.fn(() => pending.promise);
      const request = createStorageRequest({ ...input, fetch: fetcher });
      const result = request(method, "/api/watchlists").catch(error => error);
      current = false;
      pending.resolve(response(watchlist()));
      expect(await result).toMatchObject({ status: 409 });
      await expect(request("GET", "/api/watchlists")).rejects.toMatchObject({ status: 409 });
      expect(fetcher).toHaveBeenCalledTimes(1);
    }
  });

  it("rejects foreign watchlists and alert records", async () => {
    const client = createWatchlistClient({ ...options(), fetch: vi.fn(async () => response(watchlist("bob"))) });
    await expect(client.load()).rejects.toMatchObject({ status: 403 });
    const alerts = createMarketAlertClient({ ...options(), fetch: vi.fn(async () => response({ items: [watchlist("bob")] })) });
    await expect(alerts.load()).rejects.toMatchObject({ status: 403 });
  });

  it("does not expose upstream errors or retry an unauthorized request", async () => {
    const fetcher = vi.fn(async () => response({ detail: "private-upstream-value" }, 401));
    await expect(createWatchlistClient({ ...options(), fetch: fetcher }).load()).rejects.toMatchObject({ status: 401, message: "页面会话已失效，请重新打开页面" });
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("invalidates sessions on grant changes, host replacement and unmount", () => {
    let c = config();
    let listener: () => void = () => {};
    const host = { get config() { return c; }, subscribe: (fn: () => void) => { listener = fn; return () => {}; } } as Host;
    const { result, rerender, unmount } = renderHook(({ host }) => useStorageSession(host), { initialProps: { host } });
    const first = result.current!;
    act(() => { c = { ...c, grants: { ...c.grants, permissions: ["storage.read"] } }; listener(); });
    expect(first.isCurrent()).toBe(false);
    const second = result.current!;
    expect(second.isCurrent()).toBe(true);
    rerender({ host: { ...host, config: config("bob") } });
    expect(second.isCurrent()).toBe(false);
    const third = result.current!;
    unmount();
    expect(third.isCurrent()).toBe(false);
  });
});

const alert = (id: string): PriceAlert => ({ id, userId: id, workspaceId: id, security: { symbol: "AAPL", name: "Apple", market: "US" }, direction: "above", price: 250, label: id, enabled: true, createdAt: "2026-10-23T00:00:00Z", updatedAt: "2026-10-23T00:00:00Z" });
const alertClient = (load: () => Promise<PriceAlert[]>): MarketAlertClient => ({ load, create: vi.fn(), update: vi.fn(), delete: vi.fn() });

describe("alert account switching", () => {
  it("clears previous rows immediately and ignores a late previous-account load", async () => {
    const old = deferred<PriceAlert[]>();
    const first = alertClient(() => old.promise);
    const second = alertClient(async () => [alert("bob")]);
    const { result, rerender } = renderHook(({ client }) => useMarketAlerts(client), { initialProps: { client: first } });
    rerender({ client: second });
    expect(result.current.alerts).toEqual([]);
    await waitFor(() => expect(result.current.alerts[0]?.id).toBe("bob"));
    await act(async () => { old.resolve([alert("alice")]); });
    expect(result.current.alerts.map(row => row.id)).toEqual(["bob"]);
  });

  it("does not apply an old write even after switching A to B and back to A", async () => {
    const old = deferred<PriceAlert>();
    const first = { ...alertClient(async () => []), create: vi.fn(() => old.promise) };
    const second = alertClient(async () => []);
    const { result, rerender } = renderHook(({ client }) => useMarketAlerts(client), { initialProps: { client: first as MarketAlertClient } });
    await waitFor(() => expect(result.current.status).toBe("ready"));
    const pending = result.current.createAlert({ security: alert("alice").security, direction: "above", price: 250 }).catch(error => error);
    rerender({ client: second });
    rerender({ client: first });
    await act(async () => { old.resolve(alert("old-alice")); });
    expect(await pending).toBeInstanceOf(Error);
    expect(result.current.alerts).toEqual([]);
  });
});
