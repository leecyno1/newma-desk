import { performance } from "node:perf_hooks";

import {
  probeService,
  SERVICE_CRITICALITY,
  SERVICE_STATE,
} from "./runtime-supervisor.mjs";

export const RUNTIME_STATUS_SCHEMA_VERSION = "1.0";

function definedProperties(value) {
  return Object.fromEntries(
    Object.entries(value).filter(([, entry]) => entry !== undefined),
  );
}

export function collectRuntimeStatus(
  services,
  { now = () => performance.now() } = {},
) {
  return Promise.all(services.map(async (service) => {
    const startedAt = now();
    const result = await probeService(service);
    const latencyMs = Math.max(0, Math.round(now() - startedAt));
    const { state, ...details } = result;
    return definedProperties({
      id: service.id,
      label: service.label,
      criticality: service.criticality,
      state,
      url: service.url,
      latencyMs,
      ...details,
    });
  }));
}

export function createRuntimeStatusReport({
  profile,
  results,
  generatedAt = new Date(),
}) {
  const count = (state) => results.filter((result) => result.state === state).length;
  const coreReady = results
    .filter((result) => result.criticality === SERVICE_CRITICALITY.CORE)
    .every((result) => result.state === SERVICE_STATE.READY);
  const allReady = results.every((result) => result.state === SERVICE_STATE.READY);

  return {
    schemaVersion: RUNTIME_STATUS_SCHEMA_VERSION,
    profile,
    generatedAt: new Date(generatedAt).toISOString(),
    summary: {
      ready: count(SERVICE_STATE.READY),
      degraded: count(SERVICE_STATE.DEGRADED),
      unavailable: count(SERVICE_STATE.UNAVAILABLE),
      coreReady,
      allReady,
    },
    services: results,
  };
}

export function formatRuntimeStatusLine(result) {
  const prefix = {
    [SERVICE_STATE.READY]: "OK  ",
    [SERVICE_STATE.DEGRADED]: "WARN",
    [SERVICE_STATE.UNAVAILABLE]: "MISS",
  }[result.state];
  const reason = result.reason ? ` · ${result.reason}` : "";
  return `${prefix} ${result.label.padEnd(28)} ${result.url} · ${result.latencyMs}ms${reason}`;
}
