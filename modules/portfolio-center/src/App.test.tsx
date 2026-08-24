import "@testing-library/jest-dom/vitest";

import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { PortfolioCenterApp } from "./App";
import type { PortfolioResearchCoverage } from "@newma-desk/contracts";
import type {
  PortfolioDashboard,
  PortfolioOptimizationResult,
  PortfolioPerformanceResult,
} from "./types";

const closeBridge = vi.fn();
let bridgeHandler: ((event: { event: string; payload: Record<string, unknown> }) => void) | undefined;

vi.mock("@newma-desk/mod-sdk", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@newma-desk/mod-sdk")>();
  return {
    ...actual,
    connectModHost: vi.fn(async () => ({ embedded: false, close: vi.fn() })),
    createModBridge: vi.fn(() => ({
      emit: vi.fn(),
      subscribe: vi.fn((handler) => {
        bridgeHandler = handler;
        return () => { bridgeHandler = undefined; };
      }),
      close: closeBridge,
    })),
  };
});

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
  orders: [],
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
  riskPolicy: {
    singlePositionLimitPct: 30,
    topThreeLimitPct: 65,
    minEffectivePositions: 5,
    maxDrawdownLimitPct: 15,
    var95LimitPct: 5,
    maxUnpricedPositions: 0,
    allowNegativeCash: false,
    updatedAt: "2026-07-27T00:00:00Z",
  },
  riskActions: [],
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

const researchCoverage: PortfolioResearchCoverage = {
  schemaVersion: "newma-desk.portfolio-research-coverage.v1",
  userId: "local-user",
  workspaceId: "local-workspace",
  generatedAt: "2026-08-05T08:00:00Z",
  summary: {
    positionCount: 1,
    completeCount: 1,
    partialCount: 0,
    missingCount: 0,
    attentionCount: 0,
    activeReferenceCount: 2,
  },
  positions: [{
    market: "CN",
    symbol: "600519",
    name: "贵州茅台",
    accountIds: ["main"],
    status: "complete",
    referenceCount: 2,
    activeReferenceCount: 2,
    coreKinds: ["thesis"],
    supportingKinds: ["valuation"],
    missingGroups: [],
    attentionReasons: [],
    latestUpdatedAt: "2026-08-05T07:00:00Z",
    references: [{
      id: "archive:thesis-tracker:thesis-1",
      kind: "thesis",
      sourceModId: "thesis-tracker",
      artifactId: "thesis-1",
      title: "贵州茅台核心逻辑",
      status: "active",
      security: { market: "CN", symbol: "600519", name: "贵州茅台" },
      asOf: "2026-09-01",
      updatedAt: "2026-08-05T07:00:00Z",
      tags: ["active"],
      sourceRevision: 2,
    }, {
      id: "archive:valuation-workbench:valuation-1",
      kind: "valuation",
      sourceModId: "valuation-workbench",
      artifactId: "valuation-1",
      title: "贵州茅台 DCF",
      status: "active",
      security: { market: "CN", symbol: "600519", name: "贵州茅台" },
      updatedAt: "2026-08-04T07:00:00Z",
      tags: ["company"],
      sourceRevision: 1,
    }],
  }],
};

const optimizationResult: PortfolioOptimizationResult = {
  status: "ready",
  objective: "risk-balanced",
  method: "lightweight-inverse-volatility",
  currency: "CNY",
  timeframe: "1w",
  lookbackWeeks: 104,
  observations: 88,
  dataSources: ["market-data"],
  asOf: "2026-08-01",
  annualizedExpectedReturnPct: 8.2,
  annualizedVolatilityPct: 15.4,
  currentConcentration: 1,
  targetConcentration: 1,
  allocations: [{
    market: "CN",
    symbol: "600519",
    name: "贵州茅台",
    currency: "CNY",
    currentWeight: 100,
    targetWeight: 100,
    changeWeight: 0,
    expectedReturnPct: 8.2,
    volatilityPct: 15.4,
    riskContributionPct: 100,
    historyPoints: 89,
    frozen: false,
  }],
  missingAssets: [],
  warnings: ["结果基于历史周线估计，仅用于组合研究，不代表未来收益。"],
  generatedAt: "2026-08-02T00:00:00Z",
};

const performanceResult: PortfolioPerformanceResult = {
  status: "ready",
  method: "quantstats-inspired-weekly",
  currency: "CNY",
  timeframe: "1w",
  lookbackWeeks: 156,
  observations: 52,
  coverageWeightPct: 100,
  metrics: {
    totalReturnPct: 18.5,
    annualizedReturnPct: 17.9,
    annualizedVolatilityPct: 21.3,
    sharpe: 0.74,
    sortino: 1.12,
    calmar: 0.91,
    maxDrawdownPct: -19.6,
    maxDrawdownDurationWeeks: 12,
    winRatePct: 55.8,
    profitFactor: 1.28,
    bestWeekPct: 7.4,
    worstWeekPct: -6.2,
    valueAtRisk95Pct: -4.1,
    conditionalValueAtRisk95Pct: -5.3,
  },
  series: Array.from({ length: 52 }, (_, index) => ({
    label: `W${index + 1}`,
    equity: 1 + index * 0.004,
    drawdownPct: index % 9 === 0 ? -2 : 0,
  })),
  dataSources: ["market-data"],
  asOf: "2026-08-01",
  missingAssets: [],
  warnings: ["指标采用当前持仓权重进行历史周线模拟。"],
  generatedAt: "2026-08-02T00:00:00Z",
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
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("research-coverage")) return Promise.resolve(jsonResponse(researchCoverage));
      if (url.includes("includeQuotes=false")) return Promise.resolve(jsonResponse(costDashboard));
      return quoteResponse;
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<PortfolioCenterApp />);

    expect((await screen.findAllByText("贵州茅台")).length).toBeGreaterThan(0);
    expect(screen.queryByText("正在整理组合账本…")).not.toBeInTheDocument();
    expect(screen.getByText("行情刷新中")).toBeVisible();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/portfolio-center?includeQuotes=false",
      expect.objectContaining({ headers: expect.any(Object) }),
    );
    expect(await screen.findByText("持仓研究覆盖")).toBeVisible();
    expect(screen.getByText("覆盖完整")).toBeVisible();
    expect(screen.getByRole("link", { name: "投资逻辑" })).toHaveAttribute(
      "href",
      "http://127.0.0.1:5888/?mod=thesis-tracker",
    );

    resolveQuotes?.(jsonResponse(liveDashboard));

    expect(await screen.findByText("实时估值")).toBeVisible();
    expect(screen.getAllByText("110,000").length).toBeGreaterThan(0);
  });

  it("keeps the cost ledger usable when the background quote refresh fails", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("research-coverage")) return Promise.resolve(jsonResponse(researchCoverage));
      if (url.includes("includeQuotes=false")) return Promise.resolve(jsonResponse(costDashboard));
      return Promise.resolve(jsonResponse({ detail: "quote unavailable" }, 503));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<PortfolioCenterApp />);

    expect((await screen.findAllByText("贵州茅台")).length).toBeGreaterThan(0);
    await waitFor(() => {
      expect(screen.getByText("账本已加载，实时行情暂时不可用；当前显示成本口径。")).toBeVisible();
    });
    expect(screen.getAllByText("成本口径").length).toBeGreaterThan(0);
  });

  it("accepts the shared security event and focuses a matching position", async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("research-coverage")) return Promise.resolve(jsonResponse(researchCoverage));
      if (url.includes("includeQuotes=false")) return Promise.resolve(jsonResponse(costDashboard));
      return Promise.resolve(jsonResponse(liveDashboard));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<PortfolioCenterApp />);
    expect((await screen.findAllByText("贵州茅台")).length).toBeGreaterThan(0);

    act(() => {
      bridgeHandler?.({
        event: "security.selected",
        payload: { symbol: "600519", name: "贵州茅台", market: "CN" },
      });
    });

    expect(await screen.findByText("联动标的 CN:600519")).toBeVisible();
    expect(screen.getByRole("cell", { name: /贵州茅台/ }).closest("tr")).toHaveClass("selected");
  });

  it("switches between the core trading workbench tabs", async () => {
    window.history.replaceState({}, "", "/?workspace=portfolio-activities");
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => (
      Promise.resolve(jsonResponse(String(input).includes("includeQuotes=false") ? costDashboard : liveDashboard))
    )));

    render(<PortfolioCenterApp />);
    expect(await screen.findByRole("navigation", { name: "工作台标签" })).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "委托管理" }));
    expect(screen.getByText("新建委托")).toBeVisible();
    expect(screen.getByText("委托簿")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "成交录入" }));
    expect(screen.getByText("成交与资金录入")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "费用" }));
    expect(screen.getByText("分币种费用率")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "执行质量" }));
    expect(screen.getByText("执行证据覆盖")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "对账异常" }));
    expect(screen.getByText("对账异常与数据缺口")).toBeVisible();
    expect(screen.getByText("现金余额为负")).toBeVisible();
    expect(new URLSearchParams(window.location.search).get("view")).toBe("reconciliation");
  });

  it("switches between the core risk workbench tabs", async () => {
    window.history.replaceState({}, "", "/?workspace=portfolio-risk");
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => (
      Promise.resolve(jsonResponse(String(input).includes("includeQuotes=false") ? costDashboard : liveDashboard))
    )));

    render(<PortfolioCenterApp />);
    expect(await screen.findByRole("navigation", { name: "工作台标签" })).toBeVisible();
    expect(screen.getByText("需关注")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "风险限额" }));
    expect(screen.getByText("组合风险限额")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "压力测试" }));
    expect(screen.getByText("确定性市场冲击")).toBeVisible();

    fireEvent.click(screen.getByRole("button", { name: "预警" }));
    expect(screen.getByText("预警与限额核验")).toBeVisible();
    expect(screen.getByText("有效持仓数")).toBeVisible();
    expect(screen.getByText("现金余额为负")).toBeVisible();
    expect(new URLSearchParams(window.location.search).get("view")).toBe("alerts");

    fireEvent.click(screen.getByRole("button", { name: "处置记录" }));
    expect(screen.getByText(/暂无处置记录/)).toBeVisible();
  });

  it("generates and renders a constrained allocation proposal", async () => {
    window.history.replaceState({}, "", "/?workspace=portfolio-allocation");
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(costDashboard))
      .mockResolvedValueOnce(jsonResponse(liveDashboard))
      .mockResolvedValueOnce(jsonResponse(optimizationResult));
    vi.stubGlobal("fetch", fetchMock);

    render(<PortfolioCenterApp />);
    expect(await screen.findByText("配置约束")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: /生成目标配置/ }));

    expect(await screen.findByText("当前与目标权重")).toBeVisible();
    expect(screen.getByText("数据完整")).toBeVisible();
    expect(screen.getByText("88")).toBeVisible();
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/portfolio-center/allocations/optimize",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining('"objective":"risk-balanced"'),
        }),
      );
    });
  });

  it("renders QuantStats-style performance metrics from unified history", async () => {
    window.history.replaceState({}, "", "/?workspace=portfolio-performance");
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(jsonResponse(costDashboard))
      .mockResolvedValueOnce(jsonResponse(liveDashboard))
      .mockResolvedValueOnce(jsonResponse(performanceResult));
    vi.stubGlobal("fetch", fetchMock);

    render(<PortfolioCenterApp />);
    expect(await screen.findByText("当前持仓历史模拟")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: /计算绩效指标/ }));

    expect(await screen.findByText("收益与风险画像")).toBeVisible();
    expect(screen.getByText("0.74")).toBeVisible();
    expect(screen.getByRole("img", { name: "组合历史净值曲线" })).toBeVisible();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/portfolio-center/performance/analyze",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining('"lookbackWeeks":156'),
      }),
    );
  });
});
