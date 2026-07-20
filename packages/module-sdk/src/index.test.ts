import type { ModuleEvent } from "@vibe-visualization/contracts";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  createModuleBridge,
  type ModuleBridgeRuntime,
} from "./index";

const CHANNEL_NAME = "vibe-visualization-events";

class FakeBroadcastChannel {
  static channels = new Map<string, Set<FakeBroadcastChannel>>();
  static posts: Array<{ channel: FakeBroadcastChannel; data: unknown }> = [];

  readonly name: string;
  closed = false;
  private listeners = new Set<(event: MessageEvent) => void>();

  constructor(name: string) {
    this.name = name;
    const channels = FakeBroadcastChannel.channels.get(name) ?? new Set();
    channels.add(this);
    FakeBroadcastChannel.channels.set(name, channels);
  }

  addEventListener(
    type: "message",
    listener: (event: MessageEvent) => void,
  ) {
    if (type === "message") this.listeners.add(listener);
  }

  removeEventListener(
    type: "message",
    listener: (event: MessageEvent) => void,
  ) {
    if (type === "message") this.listeners.delete(listener);
  }

  postMessage(data: unknown) {
    FakeBroadcastChannel.posts.push({ channel: this, data });
    for (const channel of FakeBroadcastChannel.channels.get(this.name) ?? []) {
      if (channel !== this && !channel.closed) channel.dispatch(data);
    }
  }

  close() {
    this.closed = true;
    FakeBroadcastChannel.channels.get(this.name)?.delete(this);
  }

  private dispatch(data: unknown) {
    const event = { data } as MessageEvent;
    for (const listener of this.listeners) listener(event);
  }

  static reset() {
    FakeBroadcastChannel.channels.clear();
    FakeBroadcastChannel.posts = [];
  }
}

interface FakeWindow extends Pick<Window, "addEventListener" | "removeEventListener"> {
  parent: Window;
  dispatchMessage(event: MessageEvent): void;
}

function makeWindow(parent?: Pick<Window, "postMessage">): FakeWindow {
  const listeners = new Set<EventListenerOrEventListenerObject>();
  const fake = {
    parent: undefined as unknown as Window,
    addEventListener: vi.fn((type: string, listener: EventListenerOrEventListenerObject) => {
      if (type === "message") listeners.add(listener);
    }),
    removeEventListener: vi.fn(
      (type: string, listener: EventListenerOrEventListenerObject) => {
        if (type === "message") listeners.delete(listener);
      },
    ),
    dispatchMessage(event: MessageEvent) {
      for (const listener of listeners) {
        if (typeof listener === "function") listener(event);
        else listener.handleEvent(event);
      }
    },
  };
  fake.parent = (parent ?? fake) as unknown as Window;
  return fake;
}

function runtime(fakeWindow: FakeWindow, traceId = "trace-1"): ModuleBridgeRuntime {
  return {
    window: fakeWindow as unknown as Window,
    createBroadcastChannel: (name) =>
      new FakeBroadcastChannel(name) as unknown as BroadcastChannel,
    randomUUID: () => traceId,
  };
}

function event(overrides: Partial<ModuleEvent> = {}): ModuleEvent {
  return {
    version: "1.0",
    event: "security.selected",
    source: "market-daily",
    traceId: "incoming-1",
    payload: { symbol: "AAPL" },
    ...overrides,
  };
}

beforeEach(() => FakeBroadcastChannel.reset());

describe("createModuleBridge", () => {
  it("emits an embedded event to the exact parent origin and broadcast channel", () => {
    const parent = { postMessage: vi.fn() };
    const fakeWindow = makeWindow(parent);
    const bridge = createModuleBridge(
      { moduleId: "market-daily", parentOrigin: "https://shell.example" },
      runtime(fakeWindow),
    );

    const emitted = bridge.emit(
      "security.selected",
      { symbol: "AAPL" },
      "research-news",
    );

    expect(emitted).toEqual({
      version: "1.0",
      event: "security.selected",
      source: "market-daily",
      target: "research-news",
      traceId: "trace-1",
      payload: { symbol: "AAPL" },
    });
    expect(parent.postMessage).toHaveBeenCalledWith(
      emitted,
      "https://shell.example",
    );
    expect(FakeBroadcastChannel.posts).toHaveLength(1);
    expect(FakeBroadcastChannel.posts[0]?.data).toEqual(emitted);
  });

  it("emits a standalone event only to the broadcast channel", () => {
    const fakeWindow = makeWindow();
    const postMessage = vi.fn();
    fakeWindow.parent.postMessage = postMessage;
    const bridge = createModuleBridge(
      { moduleId: "market-daily", parentOrigin: "https://shell.example" },
      runtime(fakeWindow),
    );

    const emitted = bridge.emit("security.selected", { symbol: "AAPL" });

    expect(postMessage).not.toHaveBeenCalled();
    expect(FakeBroadcastChannel.posts[0]?.data).toEqual(emitted);
  });

  it("rejects invalid event names and payloads", () => {
    const bridge = createModuleBridge(
      { moduleId: "market-daily", parentOrigin: "https://shell.example" },
      runtime(makeWindow()),
    );

    expect(() => bridge.emit("not-valid", {})).toThrow();
    expect(() => bridge.emit("security.selected", [] as never)).toThrow();
  });

  it("rejects wildcard or non-origin parents and invalid module ids", () => {
    expect(() =>
      createModuleBridge(
        { moduleId: "market-daily", parentOrigin: "*" },
        runtime(makeWindow()),
      ),
    ).toThrow();
    expect(() =>
      createModuleBridge(
        {
          moduleId: "market-daily",
          parentOrigin: "https://shell.example/path",
        },
        runtime(makeWindow()),
      ),
    ).toThrow();
    expect(() =>
      createModuleBridge(
        { moduleId: "", parentOrigin: "https://shell.example" },
        runtime(makeWindow()),
      ),
    ).toThrow();
  });

  it("ignores parent messages with the wrong origin or source", () => {
    const parent = { postMessage: vi.fn() };
    const fakeWindow = makeWindow(parent);
    const handler = vi.fn();
    const bridge = createModuleBridge(
      { moduleId: "research-news", parentOrigin: "https://shell.example" },
      runtime(fakeWindow),
    );
    bridge.subscribe(handler);

    fakeWindow.dispatchMessage({
      data: event({ target: "research-news", traceId: "wrong-origin" }),
      origin: "https://attacker.example",
      source: parent as unknown as Window,
    } as MessageEvent);
    fakeWindow.dispatchMessage({
      data: event({ target: "research-news", traceId: "wrong-source" }),
      origin: "https://shell.example",
      source: {} as Window,
    } as MessageEvent);

    expect(handler).not.toHaveBeenCalled();
  });

  it("delivers only broadcast or matching-target events", () => {
    const parent = { postMessage: vi.fn() };
    const fakeWindow = makeWindow(parent);
    const handler = vi.fn();
    const bridge = createModuleBridge(
      { moduleId: "research-news", parentOrigin: "https://shell.example" },
      runtime(fakeWindow),
    );
    bridge.subscribe(handler);

    fakeWindow.dispatchMessage({
      data: event({ target: "other-module", traceId: "wrong-target" }),
      origin: "https://shell.example",
      source: parent as unknown as Window,
    } as MessageEvent);
    fakeWindow.dispatchMessage({
      data: event({ target: "research-news", traceId: "matching-target" }),
      origin: "https://shell.example",
      source: parent as unknown as Window,
    } as MessageEvent);
    fakeWindow.dispatchMessage({
      data: event({ traceId: "broadcast" }),
      origin: "https://shell.example",
      source: parent as unknown as Window,
    } as MessageEvent);

    expect(handler.mock.calls.map(([received]) => received.traceId)).toEqual([
      "matching-target",
      "broadcast",
    ]);
  });

  it("deduplicates the same trace received from parent and broadcast", () => {
    const parent = { postMessage: vi.fn() };
    const fakeWindow = makeWindow(parent);
    const handler = vi.fn();
    const bridge = createModuleBridge(
      { moduleId: "research-news", parentOrigin: "https://shell.example" },
      runtime(fakeWindow),
    );
    bridge.subscribe(handler);
    const duplicate = event({ target: "research-news", traceId: "same-trace" });

    fakeWindow.dispatchMessage({
      data: duplicate,
      origin: "https://shell.example",
      source: parent as unknown as Window,
    } as MessageEvent);
    new FakeBroadcastChannel(CHANNEL_NAME).postMessage(duplicate);

    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("does not receive its own emit while a separate bridge receives it", () => {
    const fakeWindow = makeWindow();
    const emittingHandler = vi.fn();
    const peerHandler = vi.fn();
    const emittingBridge = createModuleBridge(
      { moduleId: "market-daily", parentOrigin: "https://shell.example" },
      runtime(fakeWindow, "shared-trace"),
    );
    const peerBridge = createModuleBridge(
      { moduleId: "research-news", parentOrigin: "https://shell.example" },
      runtime(fakeWindow, "peer-trace"),
    );
    emittingBridge.subscribe(emittingHandler);
    peerBridge.subscribe(peerHandler);

    const emitted = emittingBridge.emit("security.selected", {
      symbol: "AAPL",
    });

    expect(emittingHandler).not.toHaveBeenCalled();
    expect(peerHandler).toHaveBeenCalledWith(emitted);
  });

  it("cleans up one subscriber without breaking a separate bridge", () => {
    const fakeWindow = makeWindow();
    const firstHandler = vi.fn();
    const secondHandler = vi.fn();
    const first = createModuleBridge(
      { moduleId: "research-news", parentOrigin: "https://shell.example" },
      runtime(fakeWindow, "first-trace"),
    );
    const second = createModuleBridge(
      { moduleId: "research-news", parentOrigin: "https://shell.example" },
      runtime(fakeWindow, "second-trace"),
    );
    const unsubscribeFirst = first.subscribe(firstHandler);
    second.subscribe(secondHandler);
    unsubscribeFirst();
    first.close();

    new FakeBroadcastChannel(CHANNEL_NAME).postMessage(
      event({ target: "research-news", traceId: "after-cleanup" }),
    );

    expect(firstHandler).not.toHaveBeenCalled();
    expect(secondHandler).toHaveBeenCalledTimes(1);
    expect(second.emit("security.selected", { symbol: "MSFT" })).toMatchObject({
      traceId: "second-trace",
    });
  });
});
