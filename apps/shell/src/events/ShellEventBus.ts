import {
  moduleEventSchema,
  type ModuleEvent,
  type ModuleManifest,
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

export interface ShellEventBusRuntime {
  createBroadcastChannel?: (name: string) => BroadcastChannelPort;
}

export interface ShellEventRegistration {
  moduleId: string;
  manifest: ModuleManifest;
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
  private readonly channel?: BroadcastChannelPort;
  private closed = false;

  constructor(runtime: ShellEventBusRuntime = defaultRuntime()) {
    this.channel = runtime.createBroadcastChannel?.(EVENT_CHANNEL);
    this.channel?.addEventListener("message", this.handleChannelMessage);
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
    this.routeValidated(value, sourceWindow, true);
  }

  close(): void {
    if (this.closed) return;
    this.closed = true;
    this.channel?.removeEventListener("message", this.handleChannelMessage);
    this.channel?.close();
    this.registrationsByModule.clear();
    this.registrationsByWindow.clear();
  }

  private readonly handleChannelMessage = (message: MessageEvent) => {
    this.routeValidated(message.data, undefined, false);
  };

  private routeValidated(
    value: unknown,
    sourceWindow: Window | undefined,
    publishToShellTabs: boolean,
  ) {
    if (this.closed) return;
    const parsed = moduleEventSchema.safeParse(value);
    if (!parsed.success || !this.traces.add(parsed.data.traceId)) return;

    const event = parsed.data;
    if (event.target) {
      this.routeTargeted(event);
    } else {
      this.routeBroadcast(event, sourceWindow);
    }

    if (publishToShellTabs) this.channel?.postMessage(event);
  }

  private routeTargeted(event: ModuleEvent) {
    if (!event.target) return;
    const registration = this.registrationsByModule.get(event.target);
    if (!registration) return;
    if (!registration.manifest.events.accepts.includes(event.event)) return;
    registration.target.postMessage(event, registration.origin);
  }

  private routeBroadcast(event: ModuleEvent, sourceWindow: Window | undefined) {
    for (const registration of this.registrationsByModule.values()) {
      if (registration.target === sourceWindow) continue;
      if (!registration.manifest.events.accepts.includes(event.event)) continue;
      registration.target.postMessage(event, registration.origin);
    }
  }
}
