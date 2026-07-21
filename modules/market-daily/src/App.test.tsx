import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";

import type { ModBridge } from "@vibedesk/mod-sdk";

import { MarketPulseApp } from "./App";
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

function bridge(): ModBridge {
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

describe("MarketPulseApp", () => {
  it("shows the last snapshot timestamp and refresh action", async () => {
    server.use(
      http.get("/api/mods/market-daily/snapshot", () =>
        HttpResponse.json(snapshot),
      ),
    );

    render(<MarketPulseApp bridge={bridge()} />);

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
      http.get("/api/mods/market-daily/snapshot", () =>
        HttpResponse.json(snapshot),
      ),
      http.post(
        "/api/mods/market-daily/actions/market.refresh",
        () => HttpResponse.json(refreshed),
      ),
    );
    render(<MarketPulseApp bridge={moduleBridge} />);
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

  it("switches to one-shot Model Gateway mode for explanations", async () => {
    let actionPayload: unknown;
    server.use(
      http.get("/api/mods/market-daily/snapshot", () =>
        HttpResponse.json(snapshot),
      ),
      http.post(
        "/api/mods/market-daily/actions/market.explain",
        async ({ request }) => {
          actionPayload = await request.json();
          return HttpResponse.json({
            answer: "模型解释结果",
            adapter: "openai-compatible",
            model: "gpt-5.6",
          });
        },
      ),
    );
    render(<MarketPulseApp bridge={bridge()} />);
    await screen.findByText("2026-07-18 15:00");

    expect(screen.getByRole("button", { name: "Agent" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await userEvent.click(screen.getByRole("button", { name: "模型" }));
    expect(screen.getByText("一次性模型调用")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "解释行情" }));

    expect(await screen.findByText("模型行情解释")).toBeVisible();
    expect(screen.getByText("模型解释结果")).toBeVisible();
    expect(screen.getByText("openai-compatible · gpt-5.6")).toBeVisible();
    expect(actionPayload).toEqual({
      gatewayMode: "model",
      prompt: "解释当前市场行情",
    });
  });

  it("uses Agent mode by default for long-lived Mod context", async () => {
    let actionPayload: unknown;
    server.use(
      http.get("/api/mods/market-daily/snapshot", () =>
        HttpResponse.json(snapshot),
      ),
      http.post(
        "/api/mods/market-daily/actions/market.explain",
        async ({ request }) => {
          actionPayload = await request.json();
          return HttpResponse.json(
            {
              id: "task-1",
              status: "completed",
              result: { answer: "Agent 解释结果" },
              error: null,
            },
            { status: 202 },
          );
        },
      ),
    );
    render(<MarketPulseApp bridge={bridge()} />);
    await screen.findByText("2026-07-18 15:00");

    expect(screen.getByText("保留当前 Mod 的长期上下文")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "解释行情" }));

    expect(await screen.findByText("Agent 行情解释")).toBeVisible();
    expect(screen.getByText("Agent 解释结果")).toBeVisible();
    expect(actionPayload).toEqual({
      gatewayMode: "agent",
      prompt: "解释当前市场行情",
    });
  });
});
