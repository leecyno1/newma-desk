import { fireEvent, render, screen } from "@testing-library/react";
import type { ModEvent, ModManifest } from "@vibedesk/contracts";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ShellEventBus } from "../events/ShellEventBus";
import { ModFrame } from "./ModuleFrame";

const manifest: ModManifest = {
  schemaVersion: "1.0",
  id: "market-daily",
  name: "市场行情",
  version: "0.1.0",
  category: "market",
  entry: { type: "structured", url: "/modules/market-daily/" },
  permissions: [],
  dataServices: [],
  agentCapabilities: [],
  events: {
    emits: ["security.selected"],
    accepts: ["security.selected"],
  },
};

function event(overrides: Partial<ModEvent> = {}): ModEvent {
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

describe("ModFrame event boundary", () => {
  it("forwards a declared event from the exact iframe window and origin", () => {
    const eventBus = new ShellEventBus();
    const route = vi.spyOn(eventBus, "route");
    render(<ModFrame manifest={manifest} eventBus={eventBus} />);
    const frame = screen.getByTitle("市场行情") as HTMLIFrameElement;
    const valid = event();

    fireEvent.load(frame);
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
    render(<ModFrame manifest={manifest} eventBus={eventBus} />);
    const frame = screen.getByTitle("市场行情") as HTMLIFrameElement;

    fireEvent.load(frame);
    dispatchFromFrame(
      frame,
      data,
      origin,
      explicitSource === null ? frame.contentWindow : explicitSource,
    );

    expect(route).not.toHaveBeenCalled();
    eventBus.close();
  });

  it("registers only after load, replaces the registration on reload, and unregisters on cleanup", () => {
    const eventBus = new ShellEventBus();
    const register = vi.spyOn(eventBus, "register");
    const unregister = vi.spyOn(eventBus, "unregister");
    const view = render(
      <ModFrame manifest={manifest} eventBus={eventBus} />,
    );
    const frame = screen.getByTitle("市场行情") as HTMLIFrameElement;
    const frameWindow = frame.contentWindow;
    if (!frameWindow) throw new Error("expected iframe window");
    const postMessage = vi
      .spyOn(frameWindow, "postMessage")
      .mockImplementation(() => undefined);

    eventBus.route(
      event({ target: "market-daily", traceId: "before-load" }),
    );

    expect(register).not.toHaveBeenCalled();
    expect(postMessage).not.toHaveBeenCalled();

    fireEvent.load(frame);

    expect(register).toHaveBeenCalledWith({
      moduleId: "market-daily",
      manifest,
      target: frameWindow,
      origin: "http://127.0.0.1:5891",
    });
    expect(register).toHaveBeenCalledTimes(1);
    expect(unregister).not.toHaveBeenCalled();

    eventBus.route(
      event({ target: "market-daily", traceId: "after-load" }),
    );
    expect(postMessage).toHaveBeenCalledWith(
      expect.objectContaining({ traceId: "after-load" }),
      "http://127.0.0.1:5891",
    );

    fireEvent.load(frame);
    expect(unregister).toHaveBeenCalledWith(frameWindow);
    expect(register).toHaveBeenCalledTimes(2);

    view.unmount();

    expect(unregister).toHaveBeenLastCalledWith(frameWindow);
    eventBus.close();
  });

  it("routes only declared post-load events without echoing to the source frame", () => {
    const targetManifest: ModManifest = {
      ...manifest,
      id: "research-news",
      name: "研究资讯",
      category: "research",
      entry: { type: "structured", url: "/modules/research-news/" },
      events: {
        emits: [],
        accepts: ["security.selected", "date.changed"],
      },
    };
    const eventBus = new ShellEventBus();
    render(
      <>
        <ModFrame manifest={manifest} eventBus={eventBus} />
        <ModFrame manifest={targetManifest} eventBus={eventBus} />
      </>,
    );
    const sourceFrame = screen.getByTitle(
      "市场行情",
    ) as HTMLIFrameElement;
    const targetFrame = screen.getByTitle("研究资讯") as HTMLIFrameElement;
    if (!sourceFrame.contentWindow || !targetFrame.contentWindow) {
      throw new Error("expected iframe windows");
    }
    const sourcePost = vi
      .spyOn(sourceFrame.contentWindow, "postMessage")
      .mockImplementation(() => undefined);
    const targetPost = vi
      .spyOn(targetFrame.contentWindow, "postMessage")
      .mockImplementation(() => undefined);

    fireEvent.load(targetFrame);
    dispatchFromFrame(
      sourceFrame,
      event({ target: "research-news", traceId: "before-source-load" }),
    );
    expect(targetPost).not.toHaveBeenCalled();

    fireEvent.load(sourceFrame);
    dispatchFromFrame(
      sourceFrame,
      event({
        event: "date.changed",
        target: "research-news",
        traceId: "undeclared-event",
      }),
    );
    expect(targetPost).not.toHaveBeenCalled();

    const targeted = event({
      target: "research-news",
      traceId: "valid-targeted",
    });
    dispatchFromFrame(sourceFrame, targeted);
    expect(targetPost).toHaveBeenCalledWith(
      targeted,
      "http://127.0.0.1:5891",
    );

    targetPost.mockClear();
    dispatchFromFrame(
      sourceFrame,
      event({ target: "market-daily", traceId: "self-targeted" }),
    );
    expect(sourcePost).not.toHaveBeenCalled();
    expect(targetPost).not.toHaveBeenCalled();

    const broadcast = event({ traceId: "valid-broadcast" });
    dispatchFromFrame(sourceFrame, broadcast);
    expect(sourcePost).not.toHaveBeenCalled();
    expect(targetPost).toHaveBeenCalledWith(
      broadcast,
      "http://127.0.0.1:5891",
    );
    eventBus.close();
  });
});
