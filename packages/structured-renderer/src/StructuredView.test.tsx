import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { View } from "@vibedesk/contracts";

import { resolvePath } from "./resolvePath";
import { StructuredView } from "./StructuredView";

const chartSpy = vi.fn();

vi.mock("echarts-for-react/lib/core", () => ({
  default: ({ option, style }: { option: unknown; style: unknown }) => {
    chartSpy(option);
    return <div data-testid="chart" style={style as React.CSSProperties} />;
  },
}));

afterEach(() => chartSpy.mockClear());

describe("resolvePath", () => {
  it("resolves own nested data and returns undefined for missing values", () => {
    expect(resolvePath({ breadth: { up: 3210 } }, "breadth.up")).toBe(3210);
    expect(resolvePath({ breadth: null }, "breadth.up")).toBeUndefined();
  });

  it.each(["__proto__.polluted", "constructor.prototype", "x.prototype.y"])(
    "rejects the unsafe path %s",
    (path) => {
      expect(resolvePath({ x: {} }, path)).toBeUndefined();
    },
  );
});

describe("StructuredView", () => {
  it("renders resolved values, safe content, and the declared chart option", () => {
    const schema: View = {
      version: "1.0",
      title: "每日行情",
      blocks: [
        {
          id: "metrics",
          type: "metrics",
          items: [
            { label: "上涨", valuePath: "breadth.up", format: "number" },
            { label: "涨幅", valuePath: "breadth.change", format: "percent" },
            { label: "金额", valuePath: "turnover", format: "currency" },
          ],
        },
        {
          id: "leaders",
          type: "table",
          rowsPath: "leaders",
          columns: [
            { key: "symbol", label: "代码" },
            { key: "pct", label: "涨幅", format: "percent", sortable: true },
          ],
        },
        { id: "trend", type: "chart", optionPath: "charts.indexTrend", height: 320 },
        { id: "analysis", type: "markdown", contentPath: "analysis" },
      ],
    };
    const option = { xAxis: { data: ["周一"] }, series: [{ data: [10] }] };

    const { container } = render(
      <StructuredView
        schema={schema}
        data={{
          breadth: { up: 3210, change: 3.2 },
          turnover: 1234.5,
          leaders: [{ symbol: "600519", pct: 3.2 }],
          charts: { indexTrend: option },
          analysis: "**市场走强**<script>alert('x')</script>",
        }}
      />,
    );

    expect(screen.getByRole("heading", { name: "每日行情" })).toBeVisible();
    expect(screen.getByText("3,210")).toBeVisible();
    expect(screen.getAllByText("3.2%")).toHaveLength(2);
    expect(screen.getByText("¥1,234.50")).toBeVisible();
    expect(screen.getByText("市场走强")).toBeVisible();
    const page = container.querySelector('[data-vibe-page="1.0"]');
    expect(page).toHaveAttribute("data-vibe-title", "每日行情");
    for (const [blockId, blockType] of [
      ["metrics", "metrics"],
      ["leaders", "table"],
      ["trend", "chart"],
      ["analysis", "markdown"],
    ]) {
      expect(
        container.querySelector(`[data-vibe-block-id="${blockId}"]`),
      ).toHaveAttribute("data-vibe-block", blockType);
    }
    const embeddedOption = container.querySelector(
      'script[type="application/json"][data-vibe-chart-option]',
    );
    expect(embeddedOption).not.toBeNull();
    expect(JSON.parse(embeddedOption?.textContent ?? "")).toEqual(option);
    expect(
      container.querySelector('script:not([type="application/json"])'),
    ).toBeNull();
    expect(chartSpy).toHaveBeenCalledWith(option);
    expect(screen.getByTestId("chart")).toHaveStyle({ height: "320px" });
  });

  it("sorts a table without mutating the source rows", async () => {
    const rows = [
      { symbol: "BBB", pct: 1 },
      { symbol: "AAA", pct: 3 },
    ];
    const schema: View = {
      version: "1.0",
      title: "排行",
      blocks: [
        {
          id: "leaders",
          type: "table",
          rowsPath: "leaders",
          columns: [
            { key: "symbol", label: "代码" },
            { key: "pct", label: "涨幅", sortable: true },
          ],
        },
      ],
    };

    render(<StructuredView schema={schema} data={{ leaders: rows }} />);
    await userEvent.click(screen.getByRole("button", { name: "按涨幅升序排列" }));

    const tableRows = screen.getAllByRole("row").slice(1);
    expect(within(tableRows[0]!).getByText("BBB")).toBeVisible();
    expect(within(tableRows[1]!).getByText("AAA")).toBeVisible();
    expect(rows.map((row) => row.symbol)).toEqual(["BBB", "AAA"]);

    await userEvent.click(screen.getByRole("button", { name: "按涨幅降序排列" }));
    const descendingRows = screen.getAllByRole("row").slice(1);
    expect(within(descendingRows[0]!).getByText("AAA")).toBeVisible();
  });

  it("emits a selected table row without changing its data", async () => {
    const onRowSelect = vi.fn();
    const row = { symbol: "600519", name: "贵州茅台", market: "CN" };
    const schema: View = {
      version: "1.0",
      title: "成交额榜",
      blocks: [
        {
          id: "leaders",
          type: "table",
          rowsPath: "leaders",
          columns: [
            { key: "symbol", label: "代码" },
            { key: "name", label: "名称" },
          ],
        },
      ],
    };

    render(
      <StructuredView
        schema={schema}
        data={{ leaders: [row] }}
        onRowSelect={onRowSelect}
      />,
    );
    await userEvent.click(
      screen.getByRole("row", { name: "600519 贵州茅台" }),
    );

    expect(onRowSelect).toHaveBeenCalledWith("leaders", row);
    expect(row).toEqual({ symbol: "600519", name: "贵州茅台", market: "CN" });
  });

  it("emits complete filters and declared actions", async () => {
    const onAction = vi.fn();
    const onFiltersChange = vi.fn();
    const schema: View = {
      version: "1.0",
      title: "交互",
      blocks: [
        {
          id: "filters",
          type: "filters",
          fields: [
            { key: "query", label: "搜索", input: "text" },
            {
              key: "market",
              label: "市场",
              input: "select",
              options: [
                { label: "沪深", value: "CN" },
                { label: "港股", value: "HK" },
              ],
            },
          ],
        },
        {
          id: "actions",
          type: "actions",
          items: [{ id: "explain", label: "解释行情", capability: "market.explain" }],
        },
      ],
    };

    render(
      <StructuredView
        schema={schema}
        data={{}}
        onAction={onAction}
        onFiltersChange={onFiltersChange}
      />,
    );

    await userEvent.type(screen.getByRole("textbox", { name: "搜索" }), "茅台");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "市场" }), "HK");
    await userEvent.click(screen.getByRole("button", { name: "解释行情" }));

    expect(onFiltersChange).toHaveBeenLastCalledWith({ query: "茅台", market: "HK" });
    expect(onAction).toHaveBeenCalledWith("market.explain", {});
  });

  it("renders fallbacks for missing and empty data without throwing", () => {
    const schema: View = {
      version: "1.0",
      title: "空状态",
      blocks: [
        {
          id: "metrics",
          type: "metrics",
          items: [{ label: "上涨", valuePath: "breadth.up" }],
        },
        {
          id: "leaders",
          type: "table",
          rowsPath: "leaders",
          columns: [{ key: "symbol", label: "代码" }],
          emptyText: "暂无领涨股",
        },
        { id: "trend", type: "chart", optionPath: "charts.missing" },
        { id: "analysis", type: "markdown", contentPath: "analysis" },
      ],
    };

    render(<StructuredView schema={schema} data={{ leaders: [] }} />);

    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText("暂无领涨股")).toBeVisible();
    expect(chartSpy).not.toHaveBeenCalled();
  });
});
