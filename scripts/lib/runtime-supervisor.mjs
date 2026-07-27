import { spawn as nodeSpawn } from "node:child_process";

export const SERVICE_CRITICALITY = Object.freeze({
  CORE: "core",
  OPTIONAL: "optional",
  EXTERNAL: "external",
});

export const SERVICE_STATE = Object.freeze({
  READY: "ready",
  DEGRADED: "degraded",
  UNAVAILABLE: "unavailable",
});

function unavailable(reason, details = {}) {
  return { state: SERVICE_STATE.UNAVAILABLE, reason, ...details };
}

export function normalizeProbeResult(result) {
  if (result === true) return { state: SERVICE_STATE.READY };
  if (result === false || result == null) return unavailable("health check failed");
  if (typeof result === "object" && Object.values(SERVICE_STATE).includes(result.state)) {
    return result;
  }
  return unavailable("invalid health check result");
}

export function createHttpProbe(
  url,
  {
    expectedService,
    expectHtml = !expectedService,
    degradedStatuses = [],
    fetchImpl = globalThis.fetch,
    timeoutMs = 1_500,
  } = {},
) {
  const degraded = new Set(degradedStatuses);
  return async () => {
    try {
      const response = await fetchImpl(url, {
        signal: AbortSignal.timeout(timeoutMs),
        headers: { Accept: expectHtml ? "text/html" : "application/json" },
      });
      const state = response.ok
        ? SERVICE_STATE.READY
        : degraded.has(response.status)
          ? SERVICE_STATE.DEGRADED
          : SERVICE_STATE.UNAVAILABLE;

      if (expectHtml) {
        const contentType = response.headers.get("content-type") || "";
        if (state === SERVICE_STATE.READY && !contentType.includes("text/html")) {
          return unavailable("health endpoint did not return HTML", {
            httpStatus: response.status,
          });
        }
        return {
          state,
          httpStatus: response.status,
          reason: state === SERVICE_STATE.DEGRADED ? `HTTP ${response.status}` : undefined,
        };
      }

      let body;
      try {
        body = await response.json();
      } catch {
        return unavailable("health endpoint did not return JSON", {
          httpStatus: response.status,
        });
      }
      const identityMatches = expectedService
        ? body?.service === expectedService || body?.status === "ok" || body?.ok === true
        : true;
      if (state === SERVICE_STATE.READY && !identityMatches) {
        return unavailable("health response did not match the expected service", {
          httpStatus: response.status,
        });
      }
      return {
        state,
        httpStatus: response.status,
        reason:
          state === SERVICE_STATE.DEGRADED
            ? body?.caveats?.[0] || body?.detail || `HTTP ${response.status}`
            : undefined,
        dataFreshness: body?.freshness,
      };
    } catch (error) {
      return unavailable(error instanceof Error ? error.message : String(error));
    }
  };
}

export async function probeService(service) {
  return normalizeProbeResult(await service.probe());
}

function terminateChild(child, platform, signal = "SIGTERM") {
  if (!child?.pid) return;
  try {
    if (platform === "win32") child.kill(signal);
    else process.kill(-child.pid, signal);
  } catch {
    // The child already exited.
  }
}

export class RuntimeSupervisor {
  constructor({
    coreTimeoutMs = 120_000,
    optionalTimeoutMs = 30_000,
    pollIntervalMs = 500,
    spawnImpl = nodeSpawn,
    logger = console,
    platform = process.platform,
    onCoreFailure = () => {},
    sleep = (durationMs) => new Promise((resolve) => setTimeout(resolve, durationMs)),
  } = {}) {
    this.coreTimeoutMs = coreTimeoutMs;
    this.optionalTimeoutMs = optionalTimeoutMs;
    this.pollIntervalMs = pollIntervalMs;
    this.spawnImpl = spawnImpl;
    this.logger = logger;
    this.platform = platform;
    this.onCoreFailure = onCoreFailure;
    this.sleep = sleep;
    this.records = new Map();
    this.shuttingDown = false;
  }

  timeoutFor(service) {
    if (Number.isFinite(service.startupTimeoutMs)) return service.startupTimeoutMs;
    return service.criticality === SERVICE_CRITICALITY.CORE
      ? this.coreTimeoutMs
      : this.optionalTimeoutMs;
  }

  async start(service) {
    const initial = await probeService(service);
    if (initial.state !== SERVICE_STATE.UNAVAILABLE) {
      const label = initial.state === SERVICE_STATE.READY ? "复用已运行服务" : "复用降级服务";
      this.logger.log(`${label}：${service.label} -> ${service.url}`);
      return { ...initial, launch: "reused", serviceId: service.id };
    }

    this.logger.log(`启动 ${service.label} -> ${service.url}`);
    let child;
    try {
      child = this.spawnImpl(service.command, service.commandArgs, {
        cwd: service.cwd,
        env: { ...process.env, ...service.env },
        stdio: "inherit",
        detached: this.platform !== "win32",
      });
    } catch (error) {
      return this.handleStartupFailure(service, error);
    }

    const record = {
      child,
      service,
      state: "starting",
      startError: null,
    };
    this.records.set(service.id, record);

    child.once("error", (error) => {
      record.startError = error;
      if (record.state !== "starting") this.handleRuntimeFailure(record, error);
    });
    child.once("exit", (code, signal) => {
      if (this.shuttingDown || record.state === "failed") return;
      const error = new Error(
        `${service.label} 意外退出：code=${code ?? "-"} signal=${signal ?? "-"}`,
      );
      if (record.state === "starting") {
        record.startError = error;
      } else {
        this.handleRuntimeFailure(record, error);
      }
    });

    try {
      const result = await this.waitUntilSettled(service, record);
      record.state = result.state;
      const label = result.state === SERVICE_STATE.READY ? "就绪" : "降级";
      this.logger.log(`${label} ${service.label}${result.reason ? `：${result.reason}` : ""}`);
      return { ...result, launch: "started", serviceId: service.id };
    } catch (error) {
      record.state = "failed";
      terminateChild(child, this.platform);
      return this.handleStartupFailure(service, error);
    }
  }

  async startOptional(services) {
    return Promise.all(services.map((service) => this.start(service)));
  }

  async waitUntilSettled(service, record) {
    const timeoutMs = this.timeoutFor(service);
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const result = await probeService(service);
      if (result.state !== SERVICE_STATE.UNAVAILABLE) return result;
      if (record.startError) throw record.startError;
      if (record.child.exitCode !== null || record.child.signalCode !== null) {
        throw new Error(`${service.label} 启动失败（进程已退出），请检查上方日志。`);
      }
      await this.sleep(this.pollIntervalMs);
    }
    throw new Error(
      `${service.label} 在 ${Math.round(timeoutMs / 1000)} 秒内未就绪：${service.url}`,
    );
  }

  handleStartupFailure(service, error) {
    const failure = error instanceof Error ? error : new Error(String(error));
    if (service.criticality === SERVICE_CRITICALITY.CORE) throw failure;
    this.logger.error(`可选 Mod 已降级：${service.label}；${failure.message}`);
    return {
      state: SERVICE_STATE.UNAVAILABLE,
      launch: "failed",
      serviceId: service.id,
      reason: failure.message,
    };
  }

  handleRuntimeFailure(record, error) {
    if (record.state === "failed") return;
    record.state = "failed";
    const failure = error instanceof Error ? error : new Error(String(error));
    if (record.service.criticality === SERVICE_CRITICALITY.CORE) {
      this.logger.error(failure.message);
      this.onCoreFailure(failure);
      return;
    }
    this.logger.error(`可选 Mod 已降级：${record.service.label}；${failure.message}`);
  }

  async stopAll({ graceMs = 400 } = {}) {
    this.shuttingDown = true;
    for (const { child } of this.records.values()) terminateChild(child, this.platform);
    if (graceMs > 0) await this.sleep(graceMs);
    for (const { child } of this.records.values()) terminateChild(child, this.platform, "SIGKILL");
  }
}
