import type { ModPageContext } from "@newma-desk/contracts";
import { describe, expect, it, vi } from "vitest";
import { createContextWriter } from "./contextWriter";

const context = (state: string): ModPageContext => ({
  view: { id: "hormuz-conflict", title: "美伊战争" }, visibleBlocks: [], selection: {}, filters: {},
  data: { summary: { loadState: state } }, actions: [], tasks: [],
});

describe("page context write order", () => {
  it("does not let a slow loading write overwrite ready evidence", async () => {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => { release = resolve; });
    let stored: ModPageContext | undefined;
    const save = vi.fn(async (value: ModPageContext) => {
      if (value.data.summary?.loadState === "loading") await gate;
      stored = value;
    });
    const writer = createContextWriter(save);
    const loading = writer.write(context("loading"));
    await Promise.resolve();
    const ready = writer.write(context("ready"));
    await Promise.resolve();
    expect(save).toHaveBeenCalledTimes(1);
    release();
    await Promise.all([loading, ready]);
    expect(stored?.data.summary?.loadState).toBe("ready");
  });

  it("continues with newer evidence after a failed write", async () => {
    const save = vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValue(undefined);
    const writer = createContextWriter(save);
    const failure = writer.write(context("loading"));
    await Promise.resolve();
    const ready = writer.write(context("ready"));
    await expect(failure).rejects.toThrow("offline");
    await ready;
    expect(save).toHaveBeenLastCalledWith(context("ready"));
  });

  it("coalesces rapid queued updates without dropping the latest state", async () => {
    let release!: () => void;
    const gate = new Promise<void>((resolve) => { release = resolve; });
    const save = vi.fn().mockReturnValueOnce(gate).mockResolvedValue(undefined);
    const writer = createContextWriter(save);
    const first = writer.write(context("loading"));
    await Promise.resolve();
    const intermediate = writer.write(context("refreshing"));
    const latest = writer.write(context("ready"));
    release();
    await Promise.all([first, intermediate, latest]);
    expect(save.mock.calls.map(([value]) => value.data.summary.loadState)).toEqual(["loading", "ready"]);
  });

  it("discards queued writes after the page closes", async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    const writer = createContextWriter(save);
    const queued = writer.write(context("loading"));
    writer.close();
    await queued;
    expect(save).not.toHaveBeenCalled();
  });
});
