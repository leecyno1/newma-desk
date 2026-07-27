import { describe, expect, it } from "vitest";

import { viewSchema } from "./view";

describe("viewSchema", () => {
  it("accepts every supported block type", () => {
    const view = viewSchema.parse({
      version: "1.0",
      title: "每日股票行情",
      blocks: [
        {
          id: "breadth",
          type: "metrics",
          items: [
            { label: "上涨", valuePath: "breadth.up", format: "number" },
          ],
        },
        {
          id: "leaders",
          type: "table",
          rowsPath: "leaders",
          columns: [
            { key: "symbol", label: "代码", format: "text", sortable: true },
          ],
          emptyText: "暂无领涨股",
        },
        {
          id: "trend",
          type: "chart",
          optionPath: "charts.indexTrend",
          height: 360,
        },
        {
          id: "summary",
          type: "markdown",
          contentPath: "analysis.summary",
        },
        {
          id: "industry-graph",
          type: "artifact",
          title: "产业链图谱",
          renderer: "archify",
          urlPath: "artifacts.industry.viewUrl",
          specPath: "artifacts.industry.spec",
          height: 620,
        },
        {
          id: "market-filters",
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
            { key: "date", label: "日期", input: "date" },
          ],
        },
        {
          id: "market-actions",
          type: "actions",
          items: [
            {
              id: "explain",
              label: "解释行情",
              capability: "market.explain",
              confirmation: "确认生成行情解释？",
            },
          ],
        },
      ],
    });

    expect(view.blocks).toHaveLength(7);
  });

  it("rejects arbitrary HTML and unknown blocks", () => {
    expect(() =>
      viewSchema.parse({
        version: "1.0",
        title: "x",
        blocks: [{ id: "x", type: "html", html: "<script/>" }],
      }),
    ).toThrow();

    expect(() =>
      viewSchema.parse({
        version: "1.0",
        title: "x",
        blocks: [{ id: "x", type: "custom" }],
      }),
    ).toThrow();
  });

  it("rejects more than 100 blocks", () => {
    expect(() =>
      viewSchema.parse({
        version: "1.0",
        title: "x",
        blocks: Array.from({ length: 101 }, (_, index) => ({
          id: `metric-${index}`,
          type: "metrics",
          items: [{ label: "值", valuePath: "value" }],
        })),
      }),
    ).toThrow();
  });

  it("rejects tables with more than 50 columns", () => {
    expect(() =>
      viewSchema.parse({
        version: "1.0",
        title: "x",
        blocks: [
          {
            id: "wide-table",
            type: "table",
            rowsPath: "rows",
            columns: Array.from({ length: 51 }, (_, index) => ({
              key: `column-${index}`,
              label: `列 ${index}`,
            })),
          },
        ],
      }),
    ).toThrow();
  });

  it("rejects select fields with more than 500 options", () => {
    expect(() =>
      viewSchema.parse({
        version: "1.0",
        title: "x",
        blocks: [
          {
            id: "filters",
            type: "filters",
            fields: [
              {
                key: "symbol",
                label: "股票",
                input: "select",
                options: Array.from({ length: 501 }, (_, index) => ({
                  label: `股票 ${index}`,
                  value: String(index),
                })),
              },
            ],
          },
        ],
      }),
    ).toThrow();
  });
});
