import type { ModEvent, ModManifest } from "@newma-desk/contracts";
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

function manifest(id: string, accepts: string[]): ModManifest {
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

  it("replays the latest broadcast selection to a later accepting Mod", async () => {
    const bus = new ShellEventBus(runtime());
    const selected = event({ payload: { symbol: "600519", market: "CN" } });
    bus.route(selected);
    const later = targetWindow();

    bus.register({
      moduleId: "stock-research",
      manifest: manifest("stock-research", ["security.selected"]),
      target: later,
      origin: "https://research.example",
    });
    await new Promise((resolve) => setTimeout(resolve, 0));

    expect(later.postMessage).toHaveBeenCalledWith(
      selected,
      "https://research.example",
    );
  });

  it("replays the latest accepted broadcast to a later embedded Mod", () => {
    const bus = new ShellEventBus(runtime());
    const selected = event({ payload: { symbol: "688981", market: "CN" } });
    bus.route(selected);
    const observed = vi.fn();

    bus.subscribe(observed, {
      moduleId: "multi-timeframe",
      accepts: ["security.selected"],
    });

    expect(observed).toHaveBeenCalledWith(selected);
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

  it("drops a targeted event when its target is the source window", () => {
    const bus = new ShellEventBus(runtime());
    const source = targetWindow();
    bus.register({
      moduleId: "research-news",
      manifest: manifest("research-news", ["security.selected"]),
      target: source,
      origin: "https://research.example",
    });

    bus.route(event({ target: "research-news" }), source);

    expect(source.postMessage).not.toHaveBeenCalled();
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

  it("publishes validated local events to the shell broadcast channel", () => {
    const observer = new FakeBroadcastChannel(CHANNEL_NAME);
    const observed = vi.fn();
    observer.addEventListener("message", observed);
    const bus = new ShellEventBus(runtime());
    const routed = event({ target: "research-news" });

    bus.route(routed, targetWindow());

    expect(FakeBroadcastChannel.posts).toEqual([routed]);
    expect(observed).toHaveBeenCalledWith(
      expect.objectContaining({ data: routed }),
    );
  });

  it("notifies the shell event log and supports unsubscribe", () => {
    const bus = new ShellEventBus(runtime());
    const observed = vi.fn();
    const unsubscribe = bus.subscribe(observed);
    const first = event();

    bus.route(first);
    unsubscribe();
    bus.route(event({ traceId: "trace-2" }));

    expect(observed).toHaveBeenCalledTimes(1);
    expect(observed).toHaveBeenCalledWith(first);
  });

  it("does not route hostile events received from the broadcast channel", () => {
    const bus = new ShellEventBus(runtime());
    const target = targetWindow();
    bus.register({
      moduleId: "research-news",
      manifest: manifest("research-news", ["security.selected"]),
      target,
      origin: "https://research.example",
    });

    new FakeBroadcastChannel(CHANNEL_NAME).postMessage(
      event({ target: "research-news", traceId: "spoofed-trace" }),
    );

    expect(target.postMessage).not.toHaveBeenCalled();
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
    second.route(
      event({ target: "research-news", traceId: "after-close" }),
    );

    expect(removed.postMessage).not.toHaveBeenCalled();
    expect(retained.postMessage).toHaveBeenCalledTimes(1);
  });
});
