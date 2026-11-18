import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { GlobalIntelligenceDashboard } from "./Dashboard";
import { buildGlobalIntelligenceContext } from "./App";
import { ComparisonPanel, type CrucixComparison } from "./ComparisonPanel";
import type { GlobalIntelDataSource } from "./data";

vi.mock("./IntelligenceMap", () => ({ IntelligenceMap: () => <div>地图</div> }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function receipt(): CrucixComparison {
  return { status: "restored", timestamp: "2026-11-14T11:00:00Z", previous: "2026-11-13T11:00:00Z",
    freshness: { status: "fresh" }, changeCount: 1, reportedChangeCount: 2, reportedDirection: "mixed",
    note: "来源两批观测比较，非风险评级；恢复记录不是新采集。",
    entries: [{ key: "10y2y", label: "10Y-2Y Spread", from: 0, to: -.2, change: -.2, pctChange: null,
      fromDate: "2026-11-12", toDate: "2026-11-13", unit: "percentage points", changeUnit: "percentage points",
      currentEligible: false, basis: "dated-source-comparison", direction: "down", source: "FRED", seriesId: "T10Y2Y" }],
    gaps: [{ key: "conflict_events", reason: "计数未核验，不能据此判断风险下降。" }] };
}

function sampleReceipt(): CrucixComparison {
  const value = receipt();
  return { ...value, reportedDirection: null, entries: [{ ...value.entries[0]!, key: "news_count", label: "RSS 展示样本（有上限）",
    from: 3, to: 0, change: -3, pctChange: -100, unit: "records", changeUnit: "records", source: "RSS",
    kind: "collection-sample", timeBasis: "collected", basis: "collection-sample-v1",
    fromDate: "2026-11-14T10:51:00Z", toDate: "2026-11-14T11:01:00Z", seriesId: undefined,
    countScope: { source: "RSS", feeds: ["https://example.org/feed"], limit: 50, selection: "regional-reserve-30d-v1" },
    note: "仅同范围采集样本变化，非风险下降依据。" }] };
}

it.each([false, true])("keeps sample scope and original collection times visible without a risk signal (current=%s)", (current) => {
  const value = sampleReceipt();
  value.status = current ? "current" : "restored";
  value.entries[0]!.currentEligible = current;
  render(<ComparisonPanel receipt={value} />);
  fireEvent.click(screen.getByText("查看变化明细（1）"));
  expect(screen.getByRole("table")).toHaveTextContent("3 → 0 条样本");
  expect(screen.getByText("采集时间，非发布或发生时间")).toBeVisible();
  expect(screen.getByText(current ? "本批样本对照 · 非风险信号" : "历史样本对照 · 非新采集")).toBeVisible();
  fireEvent.click(screen.getByText("查询范围"));
  expect(screen.getByText(/https:\/\/example.org\/feed/)).toBeVisible();
  expect(screen.getByText("样本上限")).toBeVisible();
  expect(screen.getByText("50")).toBeVisible();
  expect(screen.getByText(/非风险下降依据/)).toBeVisible();
});

it("shows zero-base absolute movement, original dates and comparison gaps without a fake return", () => {
  render(<ComparisonPanel receipt={receipt()} />);
  expect(screen.getByText("历史比较 · 非新采集")).toBeVisible();
  fireEvent.click(screen.getByText("查看变化明细（1）"));
  expect(screen.getByRole("table")).toHaveTextContent("0 → -0.2 百分点");
  expect(screen.getByRole("table")).toHaveTextContent("不可计算（零或非正基数）");
  expect(screen.getByRole("table")).toHaveTextContent("2026-11-12 → 2026-11-13");
  expect(screen.getByRole("table")).toHaveTextContent("仅历史对照，非当前信号");
  fireEvent.click(screen.getByText("查看比较缺口（1）"));
  expect(screen.getByText(/计数未核验/)).toBeVisible();
});

it.each(["baseline", "unavailable"] as const)("does not label %s as unchanged", (status) => {
  render(<ComparisonPanel receipt={{ ...receipt(), status, entries: [], changeCount: null }} />);
  expect(screen.queryByRole("table")).toBeNull();
  expect(screen.getByLabelText("两批观测变化")).not.toHaveTextContent("来源报告 0");
  expect(screen.getByText(status === "baseline" ? "仅建立基线 · 暂无前批" : "比较不可用 · 不能判断无变化")).toBeVisible();
});

it.each(["light", "dark"] as const)("keeps the actual overview and Agent comparison identical in %s", async (theme) => {
  const values = new Map<string, string>();
  for (const key of ["localStorage", "sessionStorage"]) vi.stubGlobal(key, {
    getItem: (name: string) => values.get(name) ?? null,
    setItem: (name: string, value: string) => values.set(name, value), removeItem: (name: string) => values.delete(name),
  });
  let send!: (value: Record<string, unknown>) => void;
  const context = vi.fn();
  const value = sampleReceipt();
  const snapshot = vi.fn().mockResolvedValue({ comparison: value });
  const source: GlobalIntelDataSource = { health: async () => ({}), overview: async () => ({}), staticSnapshot: async () => ({}), crucixSnapshot: snapshot,
    subscribe: (publish) => { send = publish; return () => {}; } };
  const view = render(<GlobalIntelligenceDashboard dataSource={source} theme={theme} refreshNonce={0} onRefresh={() => {}} onContextChange={context} />);
  act(() => send({ _complete: true }));
  await waitFor(() => expect(context.mock.calls.at(-1)?.[0].crucixComparison).toEqual(value));
  // The evidence must survive the default hidden-observations view and a closed panel.
  expect(screen.queryByLabelText("两批观测变化")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "详情" }));
  const panel = screen.getByRole("complementary", { name: "数据源健康控制台" });
  expect(within(panel).getByLabelText("两批观测变化")).toHaveTextContent("历史比较 · 非新采集");
  const evidence = buildGlobalIntelligenceContext(context.mock.calls.at(-1)![0]);
  expect(evidence.data?.summary).toMatchObject({ crucixComparison: value });
  expect(context.mock.calls.at(-1)![0].timeSemantics.comparison).toContain("timeBasis=collected");
  fireEvent.click(within(panel).getByText("查看变化明细（1）"));
  fireEvent.click(within(panel).getByText("查询范围"));
  expect(within(panel).getByText(/https:\/\/example.org\/feed/)).toBeVisible();
  expect(evidence.visibleBlocks).toContainEqual({ id: "global-intelligence-comparison", type: "table", title: "两批观测变化" });
  snapshot.mockResolvedValue({ comparison: { ...value, status: "unavailable", entries: [], changeCount: null } });
  view.rerender(<GlobalIntelligenceDashboard dataSource={source} theme={theme} refreshNonce={1} onRefresh={() => {}} onContextChange={context} />);
  act(() => send({ _complete: true }));
  await waitFor(() => expect(context.mock.calls.at(-1)?.[0].crucixComparison.status).toBe("unavailable"));
  expect(within(panel).getByText("比较不可用 · 不能判断无变化")).toBeVisible();
  expect(within(panel).queryByText(/https:\/\/example.org\/feed/)).toBeNull();
});
