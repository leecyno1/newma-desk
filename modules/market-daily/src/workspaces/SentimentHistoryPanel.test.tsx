import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { SentimentHistory } from "../types";
import { SentimentHistoryPanel } from "./SentimentHistoryPanel";

const history = (): SentimentHistory => ({
  days: 20, asOf: "2026-10-15", start: "2026-09-10", current: true, calendarReady: true,
  completed: 20, expected: 20, remaining: 0, commonCount: 5000, missingDates: [], failedDates: [], canContinue: false,
  fetchedDays: 0, source: "测试日线", generatedAt: "2026-10-16", note: "固定样本，非买入信号", reason: "",
  summary: { latestUpRatioPct: 75, latestChangePp: 5, mean5Pct: 70, previous5Pct: 50, change5Pp: 20, aboveHalfDays: 12 },
  points: Array.from({ length: 20 }, (_, i) => ({ date: `2026-09-${String(i + 10).padStart(2, "0")}`, status: "ready",
    reason: "", sampleCount: 5002, excludedCount: 2, upRatioPct: 56 + i, medianPct: 1 })),
});

describe("daily breadth history", () => {
  it("withdraws the curve and Agent evidence during refresh and failure", async () => {
    let reject!: (error: Error) => void;
    const dataSource = { sentimentHistory: vi.fn().mockResolvedValueOnce(history()).mockImplementationOnce(() => new Promise((_, fail) => { reject = fail; })) };
    const onChange = vi.fn();
    const { rerender } = render(<SentimentHistoryPanel dataSource={dataSource} refreshNonce={0} onChange={onChange} />);
    expect(await screen.findByRole("img")).toBeVisible();
    expect(screen.getByText("20 个百分点")).toBeVisible();
    rerender(<SentimentHistoryPanel dataSource={dataSource} refreshNonce={1} onChange={onChange} />);
    await waitFor(() => expect(onChange.mock.lastCall?.[0].data).toBeNull());
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    await act(async () => reject(new Error("历史来源失败")));
    expect(screen.getByRole("alert")).toHaveTextContent("旧结论已撤下");
    expect(onChange.mock.lastCall?.[0].status).toBe("error");
    expect(dataSource.sentimentHistory).toHaveBeenLastCalledWith(true);
  });

  it("does not draw through gaps and continues only on request", async () => {
    const partial = history();
    Object.assign(partial, { current: false, completed: 8, remaining: 12, canContinue: true, missingDates: ["2026-09-11"] });
    partial.points[1]!.status = "missing";
    const dataSource = { sentimentHistory: vi.fn().mockResolvedValueOnce(partial).mockResolvedValue(history()) }, onChange = vi.fn();
    const { rerender } = render(<SentimentHistoryPanel dataSource={dataSource} refreshNonce={0} onChange={onChange} />);
    expect(await screen.findByText("8 / 20 日就绪")).toBeVisible();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
    expect(screen.queryByText("20 个百分点")).not.toBeInTheDocument();
    expect(dataSource.sentimentHistory).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "补齐下一批历史" }));
    expect(await screen.findByRole("img")).toBeVisible();
    expect(dataSource.sentimentHistory).toHaveBeenLastCalledWith(false);
    rerender(<SentimentHistoryPanel dataSource={dataSource} refreshNonce={1} onChange={onChange} />);
    await waitFor(() => expect(dataSource.sentimentHistory).toHaveBeenLastCalledWith(true));
  });
});
