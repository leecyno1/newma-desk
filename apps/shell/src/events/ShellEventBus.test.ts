import type { ModuleEvent, ModuleManifest } from "@vibe-visualization/contracts";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  ShellEventBus,
  type ShellEventBusRuntime,
} from "./ShellEventBus";

const CHANNEL_NAME = "vibe-visualization-events";

class FakeBroadcastChannel {
  static channels = new Map<string, Set<FakeBroadcastChannel>>();
  static posts: unknown[] = [];

  private listeners = new Set<(event: MessageEvent) => void>();
  readonly name: string;

  constructor(name: string) {
    this.name = name;
    const channels = FakeBroadcastChannel.channels.get(name) ?? new Set();
    channels.add(this);
    FakeBroadcastChannel.channels.set(name, channels);
  }

  addEventListener(type: "message", listener: (event: MessageEvent) => void) {
    if (type === "message") this.listeners.add(listener);
  }

  removeEventListener(type: "message", listener: (event: MessageEvent) => void) {
    if (type === "message") this.listeners.delete(listener);
  }

  postMessage(data: unknown) {
    FakeBroadcastChannel.posts.push(data);
    for (const channel of FakeBroadcastChannel.channels.get(this.name) ?? []) {
      if (channel !== this) channel.dispatch(data);
    }
  }

  close() {
    FakeBroadcastChannel.channels.get(this.name)?.delete(this);
  }

  private dispatch(data: unknown) {
    for (const listener of this.listeners) {
      listener({ data } as MessageEvent);
    }
  }

  static reset() {
    FakeBroadcastChannel.channels.clear();
    FakeBroadcastChannel.posts = [];
  }
}

function runtime(): ShellEventBusRuntime {
  return {
    createBroadcastChannel: (name) =>
      new FakeBroadcastChannel(name) as unknown as BroadcastChannel,
  };
}

function manifest(id: string, accepts: string[]): ModuleManifest {
  return {
    schemaVersion: "1.0",
    id,
    name: id,
    version: "0.1.0",
    category: "research",
    entry: { type: "external", url: `https://${id}.example/module` },
    permissions: [],
    dataServices: [],
    agentCapabilities: [],
    events: { emits: [], accepts },
  };
}

function targetWindow() {
  return { postMessage: vi.fn() } as unknown as Window;
}

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

beforeEach(() => FakeBroadcastChannel.reset());

describe("ShellEventBus", () => {
  it("routes a targeted event only when the target declares it accepts the event", () => {
    const bus = new ShellEventBus(runtime());
    const accepting = targetWindow();
    const rejecting = targetWindow();
    bus.register({
      moduleId: "research-news",
      manifest: manifest("research-news", ["security.selected"]),
      target: accepting,
      origin: "https://research.example",
    });
    bus.register({
      moduleId: "quant-lab",
      manifest: manifest("quant-lab", []),
      target: rejecting,
      origin: "https://quant.example",
    });

    const routed = event({ target: "research-news" });
    bus.route(routed);
    bus.route(event({ target: "quant-lab", traceId: "trace-2" }));

    expect(accepting.postMessage).toHaveBeenCalledWith(
      routed,
      "https://research.example",
    );
    expect(rejecting.postMessage).not.toHaveBeenCalled();
  });

  it("broadcasts only to accepting modules and excludes the source window", () => {
    const bus = new ShellEventBus(runtime());
    const source = targetWindow();
    const accepting = targetWindow();
    const rejecting = targetWindow();
    bus.register({
      moduleId: "market-daily",
      manifest: manifest("market-daily", ["security.selected"]),
      target: source,
      origin: "https://market.example",
    });
    bus.register({
      moduleId: "research-news",
      manifest: manifest("research-news", ["security.selected"]),
      target: accepting,
      origin: "https://research.example",
    });
    bus.register({
      moduleId: "quant-lab",
      manifest: manifest("quant-lab", []),
      target: rejecting,
      origin: "https://quant.example",
    });

    const broadcast = event();
    bus.route(broadcast, source);

    expect(source.postMessage).not.toHaveBeenCalled();
    expect(accepting.postMessage).toHaveBeenCalledWith(
      broadcast,
      "https://research.example",
    );
    expect(rejecting.postMessage).not.toHaveBeenCalled();
  });

  it("uses each registered exact origin and never a wildcard", () => {
    const bus = new ShellEventBus(runtime());
    const target = targetWindow();
    bus.register({
      moduleId: "research-news",
      manifest: manifest("research-news", ["security.selected"]),
      target,
      origin: "https://research.example:8443",
    });

    bus.route(event({ target: "research-news" }));

    expect(target.postMessage).toHaveBeenCalledWith(
      expect.any(Object),
      "https://research.example:8443",
    );
    expect(target.postMessage).not.toHaveBeenCalledWith(expect.anything(), "*");
  });

  it("deduplicates trace ids and drops unknown targets", () => {
    const bus = new ShellEventBus(runtime());
    const target = targetWindow();
    bus.register({
      moduleId: "research-news",
      manifest: manifest("research-news", ["security.selected"]),
      target,
      origin: "https://research.example",
    });
    const duplicate = event({ target: "research-news" });

    bus.route(duplicate);
    bus.route(duplicate);
    bus.route(event({ target: "missing-module", traceId: "trace-missing" }));

    expect(target.postMessage).toHaveBeenCalledTimes(1);
  });

  it("publishes local events to other shell tabs and routes channel events without loops", () => {
    const first = new ShellEventBus(runtime());
    const second = new ShellEventBus(runtime());
    const target = targetWindow();
    second.register({
      moduleId: "research-news",
      manifest: manifest("research-news", ["security.selected"]),
      target,
      origin: "https://research.example",
    });
    const routed = event({ target: "research-news" });

    first.route(routed, targetWindow());

    expect(FakeBroadcastChannel.posts).toEqual([routed]);
    expect(target.postMessage).toHaveBeenCalledWith(
      routed,
      "https://research.example",
    );
  });

  it("unregisters exact windows and closes without affecting a separate bus", () => {
    const first = new ShellEventBus(runtime());
    const second = new ShellEventBus(runtime());
    const removed = targetWindow();
    const retained = targetWindow();
    first.register({
      moduleId: "research-news",
      manifest: manifest("research-news", ["security.selected"]),
      target: removed,
      origin: "https://research.example",
    });
    second.register({
      moduleId: "research-news",
      manifest: manifest("research-news", ["security.selected"]),
      target: retained,
      origin: "https://research.example",
    });

    first.unregister(removed);
    first.close();
    new FakeBroadcastChannel(CHANNEL_NAME).postMessage(
      event({ target: "research-news", traceId: "after-close" }),
    );

    expect(removed.postMessage).not.toHaveBeenCalled();
    expect(retained.postMessage).toHaveBeenCalledTimes(1);
  });
});
