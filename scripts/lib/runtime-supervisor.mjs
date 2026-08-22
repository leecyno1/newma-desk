import { spawn as nodeSpawn } from "node:child_process";
import { createConnection } from "node:net";

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

export function createCompositeProbe(checks) {
  if (!Array.isArray(checks) || checks.length === 0) {
    throw new TypeError("A composite probe requires at least one check");
  }
  const entries = checks.map((check, index) => {
    const entry = typeof check === "function"
      ? { label: `check ${index + 1}`, probe: check }
      : check;
    if (!entry || typeof entry.probe !== "function") {
      throw new TypeError(`Composite probe check ${index + 1} is invalid`);
    }
    return {
      label: String(entry.label || `check ${index + 1}`),
      probe: entry.probe,
    };
  });

  return async () => {
    // Run independent checks together so a composed readiness check costs no
    // more than its slowest bounded component.
    const results = await Promise.all(entries.map(async ({ label, probe }) => {
      try {
        return { label, result: normalizeProbeResult(await probe()) };
      } catch (error) {
        return {
          label,
          result: unavailable(error instanceof Error ? error.message : String(error)),
        };
      }
    }));
    const state = results.some(({ result }) => result.state === SERVICE_STATE.UNAVAILABLE)
      ? SERVICE_STATE.UNAVAILABLE
      : results.some(({ result }) => result.state === SERVICE_STATE.DEGRADED)
        ? SERVICE_STATE.DEGRADED
        : SERVICE_STATE.READY;
    if (state === SERVICE_STATE.READY) return { state };

    const reason = results
      .filter(({ result }) => result.state === state)
      .map(({ label, result }) => `${label}: ${result.reason || result.state}`)
      .join("; ");
    return { state, reason };
  };
}

export function createHttpProbe(
  url,
  {
    expectedService,
    expectedText,
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
      if (expectedText !== undefined) {
        const body = (await response.text()).trim();
        if (state === SERVICE_STATE.READY && body !== expectedText) {
          return unavailable("health response text did not match", {
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
  try {
    return normalizeProbeResult(await service.probe());
  } catch (error) {
    return unavailable(error instanceof Error ? error.message : String(error));
  }
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

function childIsRunning(child) {
  return Boolean(child)
    && child.exitCode == null
    && child.signalCode == null;
}

function localEndpointAddress(service) {
  try {
    const endpoint = new URL(service.url);
    if (!["127.0.0.1", "localhost", "::1", "[::1]"].includes(endpoint.hostname)) {
      return null;
    }
    const port = Number(endpoint.port || (endpoint.protocol === "https:" ? 443 : 80));
    if (!Number.isInteger(port) || port <= 0 || port > 65_535) return null;
    return { host: endpoint.hostname === "[::1]" ? "::1" : endpoint.hostname, port };
  } catch {
    return null;
  }
}

async function defaultEndpointOccupied(service, { timeoutMs = 500 } = {}) {
  const address = localEndpointAddress(service);
  // An unknown/non-local endpoint is treated as occupied. Refusing to spawn is
  // safer than creating a duplicate service whose ownership cannot be proven.
  if (!address) return true;
  return new Promise((resolve) => {
    const socket = createConnection(address);
    let settled = false;
    const finish = (occupied) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      resolve(occupied);
    };
    socket.setTimeout(timeoutMs);
    socket.once("connect", () => finish(true));
    socket.once("timeout", () => finish(true));
    socket.once("error", (error) => finish(error?.code !== "ECONNREFUSED"));
  });
}

function asError(error) {
  return error instanceof Error ? error : new Error(String(error));
}

export class RuntimeSupervisor {
  constructor({
    coreTimeoutMs = 120_000,
    optionalTimeoutMs = 30_000,
    pollIntervalMs = 500,
    monitorIntervalMs = 5_000,
    monitorFailureThreshold = 3,
    restartGraceMs = 1_000,
    optionalRestartCooldownMs = 60_000,
    portReleaseTimeoutMs = 5_000,
    portPollIntervalMs = 100,
    spawnImpl = nodeSpawn,
    logger = console,
    platform = process.platform,
    onCoreFailure = () => {},
    sleep = (durationMs) => new Promise((resolve) => setTimeout(resolve, durationMs)),
    schedule = (callback, durationMs) => setTimeout(callback, durationMs),
    cancelSchedule = (timer) => clearTimeout(timer),
    endpointOccupied = defaultEndpointOccupied,
    now = () => Date.now(),
  } = {}) {
    this.coreTimeoutMs = coreTimeoutMs;
    this.optionalTimeoutMs = optionalTimeoutMs;
    this.pollIntervalMs = pollIntervalMs;
    this.monitorIntervalMs = monitorIntervalMs;
    this.monitorFailureThreshold = Math.max(1, Math.floor(monitorFailureThreshold));
    this.restartGraceMs = Math.max(0, restartGraceMs);
    this.optionalRestartCooldownMs = Math.max(0, optionalRestartCooldownMs);
    this.portReleaseTimeoutMs = Math.max(0, portReleaseTimeoutMs);
    this.portPollIntervalMs = Math.max(1, portPollIntervalMs);
    this.spawnImpl = spawnImpl;
    this.logger = logger;
    this.platform = platform;
    this.onCoreFailure = onCoreFailure;
    this.sleep = sleep;
    this.schedule = schedule;
    this.cancelSchedule = cancelSchedule;
    this.endpointOccupied = endpointOccupied;
    this.now = now;
    this.records = new Map();
    this.ownedChildren = new Set();
    this.shuttingDown = false;
  }

  timeoutFor(service) {
    if (Number.isFinite(service.startupTimeoutMs)) return service.startupTimeoutMs;
    return service.criticality === SERVICE_CRITICALITY.CORE
      ? this.coreTimeoutMs
      : this.optionalTimeoutMs;
  }

  createRecord(service, { child = null, launch = "reused", state } = {}) {
    const record = {
      child,
      ownedChild: Boolean(child),
      service,
      launch,
      state,
      phase: child ? "starting" : "running",
      startError: null,
      consecutiveFailures: 0,
      monitorTimer: null,
      monitorInFlight: false,
      restartInFlight: false,
      coreFailureReported: false,
      nextRestartAt: 0,
    };
    this.records.set(service.id, record);
    return record;
  }

  spawnForRecord(record) {
    const { service } = record;
    if (!service.command) {
      throw new Error(`${service.label} 未配置本地启动命令。`);
    }
    const child = this.spawnImpl(service.command, service.commandArgs || [], {
      cwd: service.cwd,
      env: { ...process.env, ...service.env },
      stdio: service.stdio || "inherit",
      detached: this.platform !== "win32",
    });
    record.child = child;
    record.ownedChild = true;
    record.startError = null;
    this.ownedChildren.add(child);
    this.watchChild(record, child);
    return child;
  }

  watchChild(record, child) {
    child.once("error", (error) => {
      if (record.child !== child) return;
      const failure = asError(error);
      if (["starting", "restarting"].includes(record.phase)) {
        record.startError = failure;
        return;
      }
      this.handleRuntimeFailure(record, failure);
    });
    child.once("exit", (code, signal) => {
      this.ownedChildren.delete(child);
      if (record.child !== child) return;
      record.child = null;
      record.ownedChild = false;
      if (this.shuttingDown || record.phase === "stopping") return;
      const failure = new Error(
        `${record.service.label} 意外退出：code=${code ?? "-"} signal=${signal ?? "-"}`,
      );
      if (["starting", "restarting"].includes(record.phase)) {
        record.startError = failure;
        return;
      }
      this.handleRuntimeFailure(record, failure);
    });
  }

  async start(service) {
    const existing = this.records.get(service.id);
    if (existing) {
      return {
        state: existing.state,
        launch: existing.launch,
        serviceId: service.id,
      };
    }

    const initial = await probeService(service);
    if (initial.state !== SERVICE_STATE.UNAVAILABLE) {
      const label = initial.state === SERVICE_STATE.READY ? "复用已运行服务" : "复用降级服务";
      this.logger.log(`${label}：${service.label} -> ${service.url}`);
      if (service.command) {
        const record = this.createRecord(service, {
          launch: "reused",
          state: initial.state,
        });
        this.scheduleMonitor(record);
      }
      return { ...initial, launch: "reused", serviceId: service.id };
    }

    if (!service.command) {
      const failure = new Error(initial.reason || `${service.label} 当前不可用。`);
      if (service.criticality === SERVICE_CRITICALITY.CORE) throw failure;
      const prefix = service.criticality === SERVICE_CRITICALITY.EXTERNAL
        ? "外部 Mod 已降级"
        : "可选 Mod 已降级";
      this.logger.error(`${prefix}：${service.label}；${failure.message}`);
      return {
        ...initial,
        launch: "external",
        serviceId: service.id,
      };
    }

    if (await this.endpointOccupied(service)) {
      return this.handleStartupFailure(
        service,
        new Error(
          `${service.label} 当前不可用，但 ${service.url} 对应端口仍被占用；已拒绝启动重复实例。`,
        ),
      );
    }

    this.logger.log(`启动 ${service.label} -> ${service.url}`);
    const record = this.createRecord(service, {
      launch: "started",
      state: SERVICE_STATE.UNAVAILABLE,
    });
    let child;
    try {
      child = this.spawnForRecord(record);
      const result = await this.waitUntilSettled(service, record, child);
      record.phase = "running";
      record.state = result.state;
      record.consecutiveFailures = 0;
      const label = result.state === SERVICE_STATE.READY ? "就绪" : "降级";
      this.logger.log(`${label} ${service.label}${result.reason ? `：${result.reason}` : ""}`);
      this.scheduleMonitor(record);
      return { ...result, launch: "started", serviceId: service.id };
    } catch (error) {
      record.phase = "failed";
      record.state = SERVICE_STATE.UNAVAILABLE;
      await this.stopOwnedChild(record);
      const result = this.handleStartupFailure(service, error);
      if (service.criticality !== SERVICE_CRITICALITY.CORE && !this.shuttingDown) {
        record.nextRestartAt = this.now() + this.optionalRestartCooldownMs;
        this.scheduleMonitor(record);
      }
      return result;
    }
  }

  async startOptional(services) {
    return Promise.all(services.map((service) => this.start(service)));
  }

  async waitUntilSettled(service, record, child) {
    const timeoutMs = this.timeoutFor(service);
    const deadline = this.now() + timeoutMs;
    let lastResult;
    while (this.now() < deadline) {
      lastResult = await probeService(service);
      if (lastResult.state !== SERVICE_STATE.UNAVAILABLE) return lastResult;
      if (record.startError) throw record.startError;
      if (!childIsRunning(child)) {
        throw new Error(`${service.label} 启动失败（进程已退出），请检查上方日志。`);
      }
      await this.sleep(this.pollIntervalMs);
    }
    throw new Error(
      `${service.label} 在 ${Math.round(timeoutMs / 1000)} 秒内未就绪：${service.url}`
      + `${lastResult?.reason ? `；${lastResult.reason}` : ""}`,
    );
  }

  handleStartupFailure(service, error) {
    const failure = asError(error);
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
    if (this.shuttingDown || record.phase === "stopping") return;
    const failure = asError(error);
    record.state = SERVICE_STATE.UNAVAILABLE;
    record.phase = "failed";
    this.logger.error(`${failure.message}；等待连续健康检查确认后再恢复。`);
    this.scheduleMonitor(record, { immediate: true });
  }

  scheduleMonitor(record, { immediate = false } = {}) {
    if (
      this.shuttingDown
      || !record.service.command
      || !Number.isFinite(this.monitorIntervalMs)
      || this.monitorIntervalMs <= 0
    ) return;
    if (record.monitorTimer !== null) {
      if (!immediate) return;
      this.cancelSchedule(record.monitorTimer);
      record.monitorTimer = null;
    }
    const delay = immediate ? 0 : this.monitorIntervalMs;
    record.monitorTimer = this.schedule(async () => {
      record.monitorTimer = null;
      await this.monitorRecord(record);
      if (!this.shuttingDown) this.scheduleMonitor(record);
    }, delay);
  }

  async monitorNow(serviceId) {
    const record = this.records.get(serviceId);
    if (!record) throw new Error(`未找到运行时记录：${serviceId}`);
    return this.monitorRecord(record);
  }

  async monitorRecord(record) {
    if (this.shuttingDown || record.monitorInFlight || record.restartInFlight) {
      return { state: record.state };
    }
    record.monitorInFlight = true;
    try {
      const previousState = record.state;
      const result = await probeService(record.service);
      record.state = result.state;
      if (result.state !== SERVICE_STATE.UNAVAILABLE) {
        record.consecutiveFailures = 0;
        record.nextRestartAt = 0;
        record.phase = "running";
        record.coreFailureReported = false;
        if (previousState === SERVICE_STATE.UNAVAILABLE) {
          this.logger.log(`恢复 ${record.service.label}${result.reason ? `：${result.reason}` : ""}`);
        }
        return result;
      }

      if (
        record.service.criticality !== SERVICE_CRITICALITY.CORE
        && record.nextRestartAt > this.now()
      ) {
        return result;
      }

      record.consecutiveFailures += 1;
      if (record.consecutiveFailures < this.monitorFailureThreshold) {
        this.logger.error(
          `健康检查暂时失败：${record.service.label} `
          + `(${record.consecutiveFailures}/${this.monitorFailureThreshold})`
          + `${result.reason ? `；${result.reason}` : ""}`,
        );
        return result;
      }

      return await this.restartRecord(record, result);
    } finally {
      record.monitorInFlight = false;
    }
  }

  async waitForEndpointRelease(service) {
    const deadline = this.now() + this.portReleaseTimeoutMs;
    do {
      if (!(await this.endpointOccupied(service))) return true;
      if (this.shuttingDown || this.now() >= deadline) return false;
      await this.sleep(this.portPollIntervalMs);
    } while (this.now() <= deadline);
    return false;
  }

  async stopOwnedChild(record) {
    const child = record.child;
    if (!record.ownedChild || !child) return;
    record.child = null;
    record.ownedChild = false;
    terminateChild(child, this.platform);
    if (this.restartGraceMs > 0) await this.sleep(this.restartGraceMs);
    if (this.ownedChildren.has(child) && childIsRunning(child)) {
      terminateChild(child, this.platform, "SIGKILL");
    }
  }

  async restartRecord(record, lastProbeResult) {
    if (this.shuttingDown || record.restartInFlight) return lastProbeResult;
    record.restartInFlight = true;
    record.phase = "restarting";
    try {
      await this.stopOwnedChild(record);
      if (this.shuttingDown) return lastProbeResult;

      const released = await this.waitForEndpointRelease(record.service);
      if (!released) {
        const recovered = await probeService(record.service);
        if (recovered.state !== SERVICE_STATE.UNAVAILABLE) {
          record.state = recovered.state;
          record.phase = "running";
          record.consecutiveFailures = 0;
          return recovered;
        }
        throw new Error(
          `${record.service.label} 连续健康检查失败，但端口仍由其他进程占用；已拒绝启动重复实例。`,
        );
      }

      if (this.shuttingDown) return lastProbeResult;
      this.logger.log(`重启 ${record.service.label} -> ${record.service.url}`);
      const child = this.spawnForRecord(record);
      const result = await this.waitUntilSettled(record.service, record, child);
      record.state = result.state;
      record.phase = "running";
      record.launch = "started";
      record.consecutiveFailures = 0;
      record.nextRestartAt = 0;
      record.coreFailureReported = false;
      const label = result.state === SERVICE_STATE.READY ? "重启就绪" : "重启后降级";
      this.logger.log(`${label} ${record.service.label}${result.reason ? `：${result.reason}` : ""}`);
      return result;
    } catch (error) {
      const failure = asError(error);
      record.state = SERVICE_STATE.UNAVAILABLE;
      record.phase = "failed";
      await this.stopOwnedChild(record);
      if (this.shuttingDown) return lastProbeResult;
      if (record.service.criticality === SERVICE_CRITICALITY.CORE) {
        if (!record.coreFailureReported) {
          record.coreFailureReported = true;
          this.logger.error(`核心服务恢复失败：${failure.message}`);
          try {
            this.onCoreFailure(failure);
          } catch (callbackError) {
            this.logger.error(`核心服务失败回调异常：${asError(callbackError).message}`);
          }
        }
      } else {
        record.consecutiveFailures = 0;
        record.nextRestartAt = this.now() + this.optionalRestartCooldownMs;
        this.logger.error(`可选 Mod 已降级：${record.service.label}；${failure.message}`);
      }
      return unavailable(failure.message);
    } finally {
      record.restartInFlight = false;
    }
  }

  async stopAll({ graceMs = 400 } = {}) {
    this.shuttingDown = true;
    for (const record of this.records.values()) {
      record.phase = "stopping";
      if (record.monitorTimer !== null) {
        this.cancelSchedule(record.monitorTimer);
        record.monitorTimer = null;
      }
    }
    for (const child of this.ownedChildren) terminateChild(child, this.platform);
    if (graceMs > 0 && this.ownedChildren.size > 0) await this.sleep(graceMs);
    for (const child of this.ownedChildren) {
      if (childIsRunning(child)) terminateChild(child, this.platform, "SIGKILL");
    }
  }
}
