import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { GlobalIntelligenceDashboard } from "./Dashboard";
import { buildGlobalIntelligenceContext } from "./App";
import { normalizeGlobalIntelEvents, type GlobalIntelDataSource } from "./data";

vi.mock("./IntelligenceMap", () => ({ IntelligenceMap: () => <div>地图</div> }));
beforeEach(() => {
  for (const key of ["localStorage", "sessionStorage"]) {
    const values = new Map<string, string>();
    vi.stubGlobal(key, { getItem: (name: string) => values.get(name) ?? null,
      setItem: (name: string, value: string) => values.set(name, value), removeItem: (name: string) => values.delete(name) });
  }
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it("classifies WHO bulletins as health news, not outbreak incidents or generic news", () => {
  const [event] = normalizeGlobalIntelEvents({ crucix_intelligence: { news: [{ title: "Disease outbreak bulletin", source: "WHO", type: "who",
    publishedAt: "2026-11-10T01:00:00Z", collectedAt: "2026-11-14T11:00:00Z", collectionFreshness: { status: "fresh" } }] } });
  expect(event).toMatchObject({ category: "health", recordKind: "news", severity: "info", source: "Crucix / WHO",
    timestamp: "2026-11-10T01:00:00.000Z", timestampBasis: "published", collectedAt: "2026-11-14T11:00:00.000Z" });
});

it.each(["crucix", "world"])("keeps distinct long-titled reports while deduplicating exact repeats from %s", (engine) => {
  const title = "Ebola disease caused by Bundibugyo virus, Democratic Republic of the Congo, Kenya and Nigeria";
  const reports = ["2026-DON625", "2026-DON622"].map((id, index) => ({
    title, source: "WHO", type: "who", url: `https://www.who.int/emergencies/disease-outbreak-news/${id}`,
    publishedAt: index === 0 ? "2026-11-06T17:27:28Z" : "2026-10-23T15:48:48Z",
  }));
  const rows = [...reports, reports[0]];
  const events = normalizeGlobalIntelEvents(engine === "crucix"
    ? { crucix_intelligence: { news: rows } }
    : { news_feed: { items: rows } });
  expect(events).toHaveLength(2);
  expect(new Set(events.map((event) => event.id)).size).toBe(2);
  expect(events.map((event) => event.url)).toEqual(reports.map((report) => report.url));
});

it.each(["light", "dark"] as const)("preserves WHO query coverage in source details and Agent in %s", async (theme) => {
  const context = vi.fn();
  let send!: (value: Record<string, unknown>) => void;
  const who = { status: "ok", reportCount: 20, displayed: 10, queryLimit: 100, sourceDisplayLimit: 15,
    window: { start: "2026-10-15T10:00:00Z", end: "2026-11-14T10:00:00Z", days: 30 }, complete: true,
    collectedAt: "2026-11-14T11:00:00Z", checkedAt: "2026-11-14T11:00:00Z", freshness: { status: "fresh" }, gaps: {},
    note: "公告数不是感染人数；发布日期非疫情发生时间，也不证明没有其他疫情。" };
  const normalized = (value: typeof who) => ({ freshness: { status: "fresh" }, global: { who: value },
    sourceHealth: { queried: 1, ok: 1, items: [{ source: "WHO", status: "ok" }] } });
  const source: GlobalIntelDataSource = { health: async () => ({}), overview: async () => ({}), staticSnapshot: async () => ({}),
    crucixSnapshot: async () => normalized(who), subscribe: (publish) => { send = publish; return () => {}; } };
  render(<GlobalIntelligenceDashboard dataSource={source} theme={theme} refreshNonce={0} onRefresh={() => {}} onContextChange={context} />);
  await waitFor(() => expect(context.mock.calls.at(-1)?.[0].sourceHealth.items).toContainEqual(
    expect.objectContaining({ id: "crucix:WHO", status: "healthy", observation: who })));
  const value = context.mock.calls.at(-1)![0];
  expect(value.filters.showObservations).toBe(false);
  expect(value.actionableEventCount).toBe(0);
  expect(buildGlobalIntelligenceContext(value).data?.summary).toMatchObject({ sourceHealth: { items: [expect.objectContaining({ observation: who })] } });
  fireEvent.click(screen.getByRole("button", { name: "详情" }));
  expect(await screen.findByText(/窗口公告 20 篇.*展示 10 篇.*上限 100/)).toBeVisible();
  expect(screen.getByText(/公告数不是感染人数/)).toBeVisible();
  expect(screen.getByText(/2026-10-15T10:00:00Z.*2026-11-14T10:00:00Z/)).toBeVisible();
  act(() => send({ crucix_intelligence: normalized({ ...who, status: "error", reportCount: null, collectedAt: null,
    freshness: { status: "unknown" }, complete: false } as unknown as typeof who), _complete: true }));
  await waitFor(() => expect(context.mock.calls.at(-1)?.[0].sourceHealth.items).toContainEqual(
    expect.objectContaining({ id: "crucix:WHO", status: "error", observation: expect.objectContaining({ reportCount: null }) })));
  expect(screen.queryByText(/窗口公告 20 篇/)).toBeNull();
  expect(screen.getByText(/窗口公告 未知 篇/)).toBeVisible();
  act(() => send({ crucix_intelligence: normalized({ ...who, reportCount: 0, displayed: 0 }), _complete: true }));
  await waitFor(() => expect(screen.getByText(/窗口公告 0 篇.*展示 0 篇/)).toBeVisible());
  act(() => send({ crucix_intelligence: normalized({ ...who, freshness: { status: "stale" } }), _complete: true }));
  await waitFor(() => expect(context.mock.calls.at(-1)?.[0].sourceHealth.items).toContainEqual(
    expect.objectContaining({ id: "crucix:WHO", status: "stale" })));
});
