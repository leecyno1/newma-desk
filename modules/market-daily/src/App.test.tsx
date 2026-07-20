import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import type { ModuleBridge } from "@vibe-visualization/module-sdk";

import { MarketDailyApp } from "./App";
import { server } from "./test/server";

vi.mock("echarts-for-react/lib/core", () => ({
  default: () => <div data-testid="market-chart" />,
}));

const snapshot = {
  id: "a642793dfb534c8cbce93a20df57f72b",
  moduleId: "market-daily",
  createdAt: "2026-07-18T15:01:00+08:00",
  data: {
    asOf: "2026-07-18T15:00:00+08:00",
    breadth: { up: 3120, down: 1800, flat: 120 },
    indices: [
      { symbol: "000001", name: "上证指数", price: 3520.1, changePct: 0.8 },
    ],
    globalIndices: [],
    leaders: [
      {
        symbol: "600519",
        name: "贵州茅台",
        price: 1488,
        changePct: 3.2,
        amount: 120000000,
        market: "CN",
        industry: "白酒",
      },
    ],
    charts: {
      indexTrend: {
        xAxis: { type: "category", data: ["上证指数"] },
        yAxis: { type: "value" },
        series: [{ type: "bar", data: [0.8] }],
      },
    },
  },
};

function bridge(): ModuleBridge {
  return {
    emit: vi.fn((event: string, payload: Record<string, unknown>, target?: string) => ({
      version: "1.0" as const,
      event,
      source: "market-daily",
      ...(target ? { target } : {}),
      traceId: "trace-1",
      payload,
    })),
    subscribe: vi.fn(() => () => undefined),
    close: vi.fn(),
  };
}

describe("MarketDailyApp", () => {
  it("shows the last snapshot timestamp and refresh action", async () => {
    server.use(
      http.get("/api/modules/market-daily/snapshot", () =>
        HttpResponse.json(snapshot),
      ),
    );

    render(<MarketDailyApp bridge={bridge()} />);

    expect(await screen.findByText("2026-07-18 15:00")).toBeVisible();
    expect(screen.getByRole("button", { name: "刷新行情" })).toBeVisible();
    expect(screen.getByText("3,120")).toBeVisible();
    expect(screen.getByTestId("market-chart")).toBeVisible();
  });

  it("refreshes the snapshot and emits a selected security", async () => {
    const moduleBridge = bridge();
    const refreshed = {
      ...snapshot,
      id: "b642793dfb534c8cbce93a20df57f72b",
      data: { ...snapshot.data, asOf: "2026-07-20T15:00:00+08:00" },
    };
    server.use(
      http.get("/api/modules/market-daily/snapshot", () =>
        HttpResponse.json(snapshot),
      ),
      http.post(
        "/api/modules/market-daily/actions/market.refresh",
        () => HttpResponse.json(refreshed),
      ),
    );
    render(<MarketDailyApp bridge={moduleBridge} />);
    await screen.findByText("2026-07-18 15:00");

    await userEvent.click(screen.getByRole("button", { name: "刷新行情" }));
    expect(await screen.findByText("2026-07-20 15:00")).toBeVisible();
    await userEvent.click(
      screen.getByRole("row", { name: /600519 贵州茅台/ }),
    );

    expect(moduleBridge.emit).toHaveBeenCalledWith("security.selected", {
      symbol: "600519",
      market: "CN",
    });
  });
});
