import {
  moduleEventSchema,
  type ModuleEvent,
} from "@vibe-visualization/contracts";

const EVENT_CHANNEL = "vibe-visualization-events";
const TRACE_CACHE_LIMIT = 256;

interface BroadcastChannelPort {
  addEventListener(
    type: "message",
    listener: (event: MessageEvent) => void,
  ): void;
  removeEventListener(
    type: "message",
    listener: (event: MessageEvent) => void,
  ): void;
  postMessage(data: unknown): void;
  close(): void;
}

export interface ModuleBridgeRuntime {
  window: Window;
  createBroadcastChannel?: (name: string) => BroadcastChannelPort;
  randomUUID?: () => string;
}

export interface ModuleBridgeConfig {
  moduleId: string;
  parentOrigin: string;
}

export interface ModuleBridge {
  emit(
    event: string,
    payload: Record<string, unknown>,
    target?: string,
  ): ModuleEvent;
  subscribe(handler: (event: ModuleEvent) => void): () => void;
  close(): void;
}

class TraceCache {
  private readonly values = new Set<string>();

  add(traceId: string): boolean {
    if (this.values.has(traceId)) return false;
    this.values.add(traceId);
    if (this.values.size > TRACE_CACHE_LIMIT) {
      const oldest = this.values.values().next().value;
      if (oldest !== undefined) this.values.delete(oldest);
    }
    return true;
  }
}

function validateOrigin(origin: string): string {
  let parsed: URL;
  try {
    parsed = new URL(origin);
  } catch {
    throw new Error("parentOrigin must be an HTTP(S) origin");
  }

  if (
    (parsed.protocol !== "http:" && parsed.protocol !== "https:") ||
    parsed.origin !== origin
  ) {
    throw new Error("parentOrigin must be an HTTP(S) origin");
  }
  return origin;
}

function fallbackUuid(): string {
  const bytes = new Uint8Array(16);
  const cryptoApi = globalThis.crypto;
  if (cryptoApi?.getRandomValues) {
    cryptoApi.getRandomValues(bytes);
  } else {
    for (let index = 0; index < bytes.length; index += 1) {
      bytes[index] = Math.floor(Math.random() * 256);
    }
  }
  bytes[6] = ((bytes[6] ?? 0) & 0x0f) | 0x40;
  bytes[8] = ((bytes[8] ?? 0) & 0x3f) | 0x80;
  const hex = [...bytes].map((value) => value.toString(16).padStart(2, "0"));
  return `${hex.slice(0, 4).join("")}-${hex.slice(4, 6).join("")}-${hex
    .slice(6, 8)
    .join("")}-${hex.slice(8, 10).join("")}-${hex.slice(10).join("")}`;
}

function defaultRuntime(): ModuleBridgeRuntime {
  return {
    window,
    createBroadcastChannel:
      typeof BroadcastChannel === "undefined"
        ? undefined
        : (name) => new BroadcastChannel(name),
    randomUUID: () => globalThis.crypto?.randomUUID?.() ?? fallbackUuid(),
  };
}

function validateModuleId(moduleId: string) {
  moduleEventSchema.parse({
    version: "1.0",
    event: "bridge.initialized",
    source: moduleId,
    traceId: "configuration",
    payload: {},
  });
}

export function createModuleBridge(
  config: ModuleBridgeConfig,
  runtime: ModuleBridgeRuntime = defaultRuntime(),
): ModuleBridge {
  validateModuleId(config.moduleId);
  const parentOrigin = validateOrigin(config.parentOrigin);
  const createChannel = runtime.createBroadcastChannel;
  const channel = createChannel?.(EVENT_CHANNEL);
  const subscriptions = new Set<() => void>();
  let closed = false;

  const emit: ModuleBridge["emit"] = (event, payload, target) => {
    if (closed) throw new Error("module bridge is closed");

    const envelope = moduleEventSchema.parse({
      version: "1.0",
      event,
      source: config.moduleId,
      ...(target === undefined ? {} : { target }),
      traceId: runtime.randomUUID?.() ?? fallbackUuid(),
      payload,
    });

    if (runtime.window.parent !== runtime.window) {
      runtime.window.parent.postMessage(envelope, parentOrigin);
    }
    channel?.postMessage(envelope);
    return envelope;
  };

  const subscribe: ModuleBridge["subscribe"] = (handler) => {
    if (closed) throw new Error("module bridge is closed");

    const traceCache = new TraceCache();

    const deliver = (value: unknown) => {
      const parsed = moduleEventSchema.safeParse(value);
      if (!parsed.success) return;
      if (parsed.data.target && parsed.data.target !== config.moduleId) return;
      if (!traceCache.add(parsed.data.traceId)) return;
      handler(parsed.data);
    };

    const handleParentMessage = (message: MessageEvent) => {
      if (
        message.origin !== parentOrigin ||
        message.source !== runtime.window.parent
      ) {
        return;
      }
      deliver(message.data);
    };
    const handleBroadcastMessage = (message: MessageEvent) => {
      deliver(message.data);
    };

    runtime.window.addEventListener("message", handleParentMessage);
    channel?.addEventListener("message", handleBroadcastMessage);

    let subscribed = true;
    const unsubscribe = () => {
      if (!subscribed) return;
      subscribed = false;
      runtime.window.removeEventListener("message", handleParentMessage);
      channel?.removeEventListener("message", handleBroadcastMessage);
      subscriptions.delete(unsubscribe);
    };
    subscriptions.add(unsubscribe);
    return unsubscribe;
  };

  return {
    emit,
    subscribe,
    close() {
      if (closed) return;
      closed = true;
      for (const unsubscribe of [...subscriptions]) unsubscribe();
      channel?.close();
    },
  };
}
