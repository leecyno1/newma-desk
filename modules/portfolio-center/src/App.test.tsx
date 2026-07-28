import "@testing-library/jest-dom/vitest";

import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PortfolioCenterApp } from "./App";
import type { PortfolioDashboard } from "./types";

const closeBridge = vi.fn();
let bridgeHandler: ((event: { event: string; payload: Record<string, unknown> }) => void) | undefined;

vi.mock("@newma-desk/mod-sdk", () => ({
  connectModHost: vi.fn(async () => ({ embedded: false, close: vi.fn() })),
  createModBridge: vi.fn(() => ({
    emit: vi.fn(),
    subscribe: vi.fn((handler) => {
      bridgeHandler = handler;
      return () => { bridgeHandler = undefined; };
    }),
    close: closeBridge,
  })),
}));

const costDashboard: PortfolioDashboard = {
  userId: "local-user",
  workspaceId: "local-workspace",
  accounts: [{
    id: "main",
    name: "主账户",
    currency: "CNY",
    accountType: "securities",
    archived: false,
    createdAt: "2026-07-27T00:00:00Z",
    updatedAt: "2026-07-27T00:00:00Z",
  }],
  activities: [],
  positions: [{
    accountId: "main",
    market: "CN",
    symbol: "600519",
    name: "贵州茅台",
    currency: "CNY",
    quantity: 100,
    averageCost: 1000,
    costValue: 100000,
    realizedPnl: 0,
  }],
  currencies: [{
    currency: "CNY",
    cash: -100000,
    costValue: 100000,
    realizedPnl: 0,
    income: 0,
    fees: 0,
  }],
  analytics: {
    basis: "cost-value",
    byMarket: [{ key: "CN", label: "CN", currency: "CNY", value: 100000, weight: 100 }],
    byCurrency: [{ key: "CNY", label: "CNY", currency: "CNY", value: 100000, weight: 100 }],
    byAccount: [{ key: "main", label: "主账户", currency: "CNY", value: 100000, weight: 100 }],
    concentration: {
      positionCount: 1,
      topPositionWeight: 100,
      topThreeWeight: 100,
      herfindahlIndex: 1,
      effectivePositionCount: 1,
    },
  },
  valuationStatus: "cost-based",
  updatedAt: "2026-07-27T00:00:00Z",
};

const liveDashboard: PortfolioDashboard = {
  ...costDashboard,
  positions: [{
    ...costDashboard.positions[0],
    price: 1100,
    marketValue: 110000,
    unrealizedPnl: 10000,
    unrealizedPnlPct: 10,
    quoteSource: "test",
  }],
  currencies: [{
    ...costDashboard.currencies[0],
    marketValue: 110000,
    unrealizedPnl: 10000,
  }],
  analytics: { ...costDashboard.analytics, basis: "market-value" },
  valuationStatus: "live",
};

function jsonResponse(payload: unknown, status = 200) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("PortfolioCenterApp", () => {
  beforeEach(() => {
    window.history.replaceState({}, "", "/?workspace=portfolio-brief");
    closeBridge.mockClear();
    bridgeHandler = undefined;
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("renders the local ledger before the background quote request completes", async () => {
    let resolveQuotes: ((response: Response) => void) | undefined;
    const quoteResponse = new Promise<Response>((resolve) => { resolveQuotes = resolve; });
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(costDashboard))
      .mockReturnValueOnce(quoteResponse);
    vi.stubGlobal("fetch", fetchMock);

    render(<PortfolioCenterApp />);

    expect(await screen.findByText("贵州茅台")).toBeVisible();
    expect(screen.queryByText("正在整理组合账本…")).not.toBeInTheDocument();
    expect(screen.getByText("行情刷新中")).toBeVisible();
    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      "/api/portfolio-center?includeQuotes=false",
      expect.objectContaining({ headers: expect.any(Object) }),
    );

    resolveQuotes?.(jsonResponse(liveDashboard));

    expect(await screen.findByText("实时估值")).toBeVisible();
    expect(screen.getAllByText("110,000").length).toBeGreaterThan(0);
  });

  it("keeps the cost ledger usable when the background quote refresh fails", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(costDashboard))
      .mockResolvedValueOnce(jsonResponse({ detail: "quote unavailable" }, 503));
    vi.stubGlobal("fetch", fetchMock);

    render(<PortfolioCenterApp />);

    expect(await screen.findByText("贵州茅台")).toBeVisible();
    await waitFor(() => {
      expect(screen.getByText("账本已加载，实时行情暂时不可用；当前显示成本口径。")).toBeVisible();
    });
    expect(screen.getAllByText("成本口径").length).toBeGreaterThan(0);
  });

  it("accepts the shared security event and focuses a matching position", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(costDashboard))
      .mockResolvedValueOnce(jsonResponse(liveDashboard));
    vi.stubGlobal("fetch", fetchMock);

    render(<PortfolioCenterApp />);
    expect(await screen.findByText("贵州茅台")).toBeVisible();

    act(() => {
      bridgeHandler?.({
        event: "security.selected",
        payload: { symbol: "600519", name: "贵州茅台", market: "CN" },
      });
    });

    expect(await screen.findByText("联动标的 CN:600519")).toBeVisible();
    expect(screen.getByText("贵州茅台").closest("tr")).toHaveClass("selected");
  });
});
