import { fireEvent, render, screen } from "@testing-library/react";
import type { ModuleEvent, ModuleManifest } from "@vibe-visualization/contracts";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ShellEventBus } from "../events/ShellEventBus";
import { ModuleFrame } from "./ModuleFrame";

const manifest: ModuleManifest = {
  schemaVersion: "1.0",
  id: "market-daily",
  name: "每日股票行情",
  version: "0.1.0",
  category: "market",
  entry: { type: "structured", url: "/modules/market-daily/" },
  permissions: [],
  dataServices: [],
  agentCapabilities: [],
  events: { emits: ["security.selected"], accepts: [] },
};

function event(overrides: Partial<ModuleEvent> = {}): ModuleEvent {
  return {
    version: "1.0",
    event: "security.selected",
    source: "market-daily",
    traceId: "trace-1",
    payload: { symbol: "AAPL" },
    ...overrides,
  };
}

function dispatchFromFrame(
  frame: HTMLIFrameElement,
  data: unknown,
  origin = "http://127.0.0.1:5891",
  source: MessageEventSource | null = frame.contentWindow,
) {
  window.dispatchEvent(new MessageEvent("message", { data, origin, source }));
}

afterEach(() => vi.restoreAllMocks());

describe("ModuleFrame event boundary", () => {
  it("forwards a declared event from the exact iframe window and origin", () => {
    const eventBus = new ShellEventBus();
    const route = vi.spyOn(eventBus, "route");
    render(<ModuleFrame manifest={manifest} eventBus={eventBus} />);
    const frame = screen.getByTitle("每日股票行情") as HTMLIFrameElement;
    const valid = event();

    dispatchFromFrame(frame, valid);

    expect(route).toHaveBeenCalledWith(valid, frame.contentWindow);
    eventBus.close();
  });

  it.each([
    ["wrong source", event(), "http://127.0.0.1:5891", window],
    ["wrong origin", event(), "https://attacker.example", null],
    [
      "wrong module id",
      event({ source: "other-module" }),
      "http://127.0.0.1:5891",
      null,
    ],
    [
      "undeclared event",
      event({ event: "date.changed" }),
      "http://127.0.0.1:5891",
      null,
    ],
  ])("ignores %s messages", (_label, data, origin, explicitSource) => {
    const eventBus = new ShellEventBus();
    const route = vi.spyOn(eventBus, "route");
    render(<ModuleFrame manifest={manifest} eventBus={eventBus} />);
    const frame = screen.getByTitle("每日股票行情") as HTMLIFrameElement;

    dispatchFromFrame(
      frame,
      data,
      origin,
      explicitSource === null ? frame.contentWindow : explicitSource,
    );

    expect(route).not.toHaveBeenCalled();
    eventBus.close();
  });

  it("registers the current iframe window on mount/load and unregisters it on cleanup", () => {
    const eventBus = new ShellEventBus();
    const register = vi.spyOn(eventBus, "register");
    const unregister = vi.spyOn(eventBus, "unregister");
    const view = render(
      <ModuleFrame manifest={manifest} eventBus={eventBus} />,
    );
    const frame = screen.getByTitle("每日股票行情") as HTMLIFrameElement;
    const frameWindow = frame.contentWindow;

    expect(register).toHaveBeenCalledWith({
      moduleId: "market-daily",
      manifest,
      target: frameWindow,
      origin: "http://127.0.0.1:5891",
    });

    fireEvent.load(frame);

    expect(unregister).toHaveBeenCalledWith(frameWindow);
    expect(register).toHaveBeenCalledTimes(2);

    view.unmount();

    expect(unregister).toHaveBeenLastCalledWith(frameWindow);
    eventBus.close();
  });
});
