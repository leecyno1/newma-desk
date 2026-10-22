import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { RelativeStrengthWorkspace } from "./RelativeStrengthWorkspace";
import type { MarketDataSource, SecurityRef } from "../types";

const security: SecurityRef = { symbol: "600519", name: "贵州茅台", market: "CN", exchange: "SH" };
describe("relative strength data state", () => {
  it("excludes a failed security while retaining comparable successful data and weekly sampling", async () => {
    const ohlcv = vi.fn(async (item: SecurityRef) => {
      if (item.symbol === "688981") throw new Error("unavailable");
      return { symbol: item.symbol, market: item.market, timeframe: "1d", adjust: "qfq", source: "fixture", asOf: "2026-10-22", hasMore: false,
        items: ["2026-10-15", "2026-10-16", "2026-10-19", "2026-10-20"].map((date, index) => ({ timestamp: Date.parse(`${date}T00:00:00+08:00`), open: 10, high: 20, low: 10, close: 10 + index })) };
    });
    const context = vi.fn();
    render(<RelativeStrengthWorkspace security={security} dataSource={{ ohlcv } as unknown as MarketDataSource} refreshNonce={0} onSelectSecurity={vi.fn()} onContextChange={context} />);
    await screen.findByText("1 个标的更新失败，已从本次排名排除");
    await waitFor(() => expect(context.mock.lastCall?.[0].ranking).toHaveLength(4));
    expect(context.mock.lastCall?.[0].ranking.some((item: { id: string }) => item.id === "CN:688981")).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "周线" }));
    await waitFor(() => expect(context.mock.lastCall?.[0].comparisonWindow).toMatchObject({ start: "2026-10-16", end: "2026-10-20", observations: 2 }));
    expect(ohlcv).toHaveBeenCalledTimes(5);
    expect(screen.getByRole("img", { name: "相对强弱走势" })).toBeInTheDocument();
  });
});
