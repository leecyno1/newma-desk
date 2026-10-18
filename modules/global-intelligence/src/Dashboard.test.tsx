import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GlobalIntelligenceDashboard } from "./Dashboard";
import { buildGlobalIntelligenceContext } from "./App";
import type { GlobalIntelDataSource } from "./data";

vi.mock("./IntelligenceMap", () => ({ IntelligenceMap: () => <div>地图</div> }));

beforeEach(() => {
  for (const key of ["localStorage", "sessionStorage"]) {
    const values = new Map<string, string>();
    vi.stubGlobal(key, {
      getItem: (name: string) => values.get(name) ?? null,
      setItem: (name: string, value: string) => values.set(name, value),
      removeItem: (name: string) => values.delete(name),
    });
  }
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("navigation warning page and Agent evidence", () => {
  it("reports the selected route/point and only the currently visible evidence blocks", () => {
    const route = { id: "shipping", name: "Test corridor" };
    const context = buildGlobalIntelligenceContext({ selectedRoute: route, presentation: { mapExpanded: true }, events: [{ sourceFreshness: "fresh" }] });
    expect(context.selection).toEqual({ route });
    expect(context.data.freshness).toBe("unknown");
    expect(context.visibleBlocks?.map((block) => block.id)).not.toContain("global-intelligence-events");
    expect(context.visibleBlocks?.map((block) => block.id)).not.toContain("global-intelligence-sources");
    expect(buildGlobalIntelligenceContext({ selectedPoint: { id: "point", sourceFreshness: "stale", collectedAt: "2026-10-01" } }).data).toMatchObject({ freshness: "stale", asOf: "2026-10-01" });
  });
  it("does not treat a live connection as proof of fresh data", () => {
    const context = buildGlobalIntelligenceContext({ streamStatus: "live", lastUpdate: new Date().toISOString(), selectedEvent: { title: "Undated report", timestamp: "", timestampBasis: "unknown", sourceFreshness: "unknown" } });
    expect(context.data.freshness).toBe("unknown");
    expect(context.data.asOf).toBeUndefined();
  });

  it("shows old publication, collection and tracking separately, including unknown dates", async () => {
    const observedAt = new Date().toISOString();
    const snapshot = {
      timestamp: observedAt, _done: 1, _total: 1,
      nav_warnings: {
        timestamp: "2026-08-12T14:01:51Z", collected_at: "2026-08-12T14:01:51Z", freshness: "stale",
        warnings: [
          { id: "2024-517", navarea: "4", issue_date: "081653Z MAY 2024", status: "active", text: "DANGER AREA", lat: 20, lon: 60 },
          { id: "2024-518", navarea: "4", issue_date: null, status: "active", text: "SECOND DANGER AREA", lat: 21, lon: 60 },
        ],
      },
    };
    const onContextChange = vi.fn();
    const dataSource: GlobalIntelDataSource = {
      health: async () => ({}), overview: async () => snapshot,
      staticSnapshot: async () => snapshot, crucixSnapshot: async () => ({}),
      subscribe: (_payload, status) => { status("live"); return () => {}; },
    };
    const { container } = render(<GlobalIntelligenceDashboard dataSource={dataSource} theme="dark" refreshNonce={0} onRefresh={() => {}} onContextChange={onContextChange} />);
    const list = container.querySelector(".intel-event-list") as HTMLElement;
    await waitFor(() => expect(within(list).getByRole("button", { name: /2024-517/ })).toBeVisible());
    const oldWarning = within(list).getByRole("button", { name: /2024-517/ });
    expect(oldWarning).toHaveTextContent(/发布 \d+ 天前/);
    expect(oldWarning).not.toHaveTextContent("刚刚");
    expect(oldWarning).toHaveTextContent("首次收录");
    expect(oldWarning).toHaveTextContent("旧缓存");
    const unknownWarning = within(list).getByRole("button", { name: /2024-518/ });
    expect(unknownWarning).toHaveTextContent("发布日期未知");
    fireEvent.click(oldWarning);
    const state = () => onContextChange.mock.calls.at(-1)?.[0] as Record<string, unknown>;
    await waitFor(() => expect(state().selectedEvent).toMatchObject({
      title: "NAVAREA 4 · 2024-517", timestamp: "2024-05-08T16:53:00.000Z", timestampBasis: "published",
      collectedAt: "2026-08-12T14:01:51.000Z", sourceFreshness: "stale", firstSeenAt: expect.any(String),
    }));
    expect(screen.getByText("最近成功采集")).toBeVisible();
    expect(screen.getByText("发布日期", { selector: "dt" })).toBeVisible();
    expect(buildGlobalIntelligenceContext(state()).data).toMatchObject({ freshness: "stale", asOf: "2026-08-12T14:01:51.000Z" });
    expect(buildGlobalIntelligenceContext(state()).data?.summary).toMatchObject({
      timeSemantics: { tracking: expect.stringContaining("首次收录不等于新发生") },
      filters: { timeBasis: "tracking-activity" },
    });
    fireEvent.click(unknownWarning);
    await waitFor(() => expect(state().selectedEvent).toMatchObject({ timestamp: "", timestampBasis: "unknown" }));
    expect(container).not.toHaveTextContent("Invalid Date");
  });
});
