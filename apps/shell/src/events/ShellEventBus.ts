import {
  modEventSchema,
  type ModEvent,
  type ModManifest,
} from "@newma-dock/contracts";

const EVENT_CHANNEL = "vibe-visualization-events";
const TRACE_CACHE_LIMIT = 256;

interface BroadcastChannelPort {
  postMessage(data: unknown): void;
  close(): void;
}

export interface ShellEventBusRuntime {
  createBroadcastChannel?: (name: string) => BroadcastChannelPort;
}

export interface ShellEventRegistration {
  moduleId: string;
  manifest: ModManifest;
  target: Window;
  origin: string;
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

function defaultRuntime(): ShellEventBusRuntime {
  return {
    createBroadcastChannel:
      typeof BroadcastChannel === "undefined"
        ? undefined
        : (name) => new BroadcastChannel(name),
  };
}

function exactHttpOrigin(origin: string): boolean {
  try {
    const parsed = new URL(origin);
    return (
      (parsed.protocol === "http:" || parsed.protocol === "https:") &&
      parsed.origin === origin
    );
  } catch {
    return false;
  }
}

export class ShellEventBus {
  private readonly registrationsByModule = new Map<
    string,
    ShellEventRegistration
  >();
  private readonly registrationsByWindow = new Map<
    Window,
    ShellEventRegistration
  >();
  private readonly traces = new TraceCache();
  private readonly latestBroadcasts = new Map<string, ModEvent>();
  private readonly observers = new Set<(event: ModEvent) => void>();
  private readonly channel?: BroadcastChannelPort;
  private closed = false;

  constructor(runtime: ShellEventBusRuntime = defaultRuntime()) {
    this.channel = runtime.createBroadcastChannel?.(EVENT_CHANNEL);
  }

  register(registration: ShellEventRegistration): void {
    if (this.closed) return;
    if (
      registration.moduleId !== registration.manifest.id ||
      !exactHttpOrigin(registration.origin)
    ) {
      return;
    }

    const previousModule = this.registrationsByModule.get(
      registration.moduleId,
    );
    if (previousModule) {
      this.registrationsByWindow.delete(previousModule.target);
    }
    const previousWindow = this.registrationsByWindow.get(registration.target);
    if (previousWindow) {
      this.registrationsByModule.delete(previousWindow.moduleId);
    }

    this.registrationsByModule.set(registration.moduleId, registration);
    this.registrationsByWindow.set(registration.target, registration);
    globalThis.setTimeout(() => {
      if (
        this.closed ||
        this.registrationsByModule.get(registration.moduleId) !== registration
      ) return;
      for (const eventName of registration.manifest.events.accepts) {
        const latest = this.latestBroadcasts.get(eventName);
        if (!latest || latest.source === registration.moduleId) continue;
        registration.target.postMessage(latest, registration.origin);
      }
    }, 0);
  }

  unregister(target: Window): void {
    const registration = this.registrationsByWindow.get(target);
    if (!registration) return;
    this.registrationsByWindow.delete(target);
    if (this.registrationsByModule.get(registration.moduleId) === registration) {
      this.registrationsByModule.delete(registration.moduleId);
    }
  }

  route(value: unknown, sourceWindow?: Window): void {
    this.routeValidated(value, sourceWindow);
  }

  subscribe(handler: (event: ModEvent) => void): () => void {
    if (this.closed) return () => undefined;
    this.observers.add(handler);
    return () => this.observers.delete(handler);
  }

  close(): void {
    if (this.closed) return;
    this.closed = true;
    this.channel?.close();
    this.observers.clear();
    this.latestBroadcasts.clear();
    this.registrationsByModule.clear();
    this.registrationsByWindow.clear();
  }

  private routeValidated(
    value: unknown,
    sourceWindow: Window | undefined,
  ) {
    if (this.closed) return;
    const parsed = modEventSchema.safeParse(value);
    if (!parsed.success || !this.traces.add(parsed.data.traceId)) return;

    const event = parsed.data;
    if (!event.target) this.latestBroadcasts.set(event.event, event);
    if (event.target) {
      this.routeTargeted(event, sourceWindow);
    } else {
      this.routeBroadcast(event, sourceWindow);
    }

    for (const observer of this.observers) observer(event);
    this.channel?.postMessage(event);
  }

  private routeTargeted(event: ModEvent, sourceWindow: Window | undefined) {
    if (!event.target) return;
    const registration = this.registrationsByModule.get(event.target);
    if (!registration) return;
    if (registration.target === sourceWindow) return;
    if (!registration.manifest.events.accepts.includes(event.event)) return;
    registration.target.postMessage(event, registration.origin);
  }

  private routeBroadcast(event: ModEvent, sourceWindow: Window | undefined) {
    for (const registration of this.registrationsByModule.values()) {
      if (registration.target === sourceWindow) continue;
      if (!registration.manifest.events.accepts.includes(event.event)) continue;
      registration.target.postMessage(event, registration.origin);
    }
  }
}
