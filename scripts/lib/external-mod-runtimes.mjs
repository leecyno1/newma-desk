import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = fileURLToPath(new URL("../../", import.meta.url));
const DEFAULT_DESCRIPTOR_URL = new URL(
  "../../config/external-mod-runtimes.json",
  import.meta.url,
);
const ID_PATTERN = /^[a-z][a-z0-9-]{2,63}$/;
const ENV_PATTERN = /^(?:NEWMA_DESK|NEWMA_DOCK|VIBEDESK)_[A-Z0-9_]+$/;
const CHILD_ENV_PATTERN = /^[A-Z_][A-Z0-9_]*$/;
const CRITICALITIES = new Set(["core", "optional", "external"]);
const READINESS_MODES = new Set(["html", "json", "text"]);
const STDIO_MODES = new Set(["inherit", "ignore"]);

function objectValue(value, label) {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value;
}

function stringValue(value, label) {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${label} must be a non-empty string`);
  }
  return value;
}

function optionalString(value, label) {
  return value === undefined ? undefined : stringValue(value, label);
}

function stringList(value, label, { allowEmpty = true } = {}) {
  if (!Array.isArray(value) || (!allowEmpty && value.length === 0)) {
    throw new Error(`${label} must be ${allowEmpty ? "an" : "a non-empty"} array`);
  }
  return value.map((entry, index) => stringValue(entry, `${label}[${index}]`));
}

function envName(value, label) {
  const name = stringValue(value, label);
  if (!ENV_PATTERN.test(name)) {
    throw new Error(`${label} must be a NEWMA_DESK_*, NEWMA_DOCK_* or VIBEDESK_* name`);
  }
  return name;
}

function childEnvName(value, label) {
  const name = stringValue(value, label);
  if (!CHILD_ENV_PATTERN.test(name)) throw new Error(`${label} must be an environment name`);
  return name;
}

function configuredEnvValue(env, name) {
  const prefixes = ["NEWMA_DESK_", "NEWMA_DOCK_", "VIBEDESK_"];
  const prefix = prefixes.find((candidate) => name.startsWith(candidate));
  if (!prefix) return env[name]?.trim();
  const suffix = name.slice(prefix.length);
  for (const candidate of prefixes) {
    const configured = env[`${candidate}${suffix}`]?.trim();
    if (configured) return configured;
  }
  return undefined;
}

function safeRelativePath(value, label) {
  const candidate = stringValue(value, label);
  if (
    path.isAbsolute(candidate) ||
    candidate.includes("\\") ||
    candidate.split("/").some((part) => !part || part === "." || part === "..")
  ) {
    throw new Error(`${label} must be a safe relative path`);
  }
  return candidate;
}

function exactHttpOrigin(value, label) {
  let parsed;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error(`${label} must be an HTTP(S) origin`);
  }
  if (
    !["http:", "https:"].includes(parsed.protocol) ||
    parsed.username ||
    parsed.password ||
    parsed.origin !== value
  ) {
    throw new Error(`${label} must be an HTTP(S) origin`);
  }
  return parsed;
}

function endpointPort(url) {
  if (url.port) return Number(url.port);
  return url.protocol === "https:" ? 443 : 80;
}

function localHostname(hostname) {
  return ["127.0.0.1", "localhost", "::1", "[::1]"].includes(hostname);
}

function resolveRoots(rawRoots, { repoRoot, homeDir, env }) {
  const roots = { repo: repoRoot };
  if (!Array.isArray(rawRoots)) throw new Error("descriptor.roots must be an array");
  for (const [index, rawRoot] of rawRoots.entries()) {
    const root = objectValue(rawRoot, `descriptor.roots[${index}]`);
    const id = stringValue(root.id, `descriptor.roots[${index}].id`);
    if (!ID_PATTERN.test(id) || id === "repo" || Object.hasOwn(roots, id)) {
      throw new Error(`descriptor.roots[${index}].id is invalid or duplicated`);
    }
    const configured = configuredEnvValue(
      env,
      envName(root.env, `descriptor.roots[${index}].env`),
    );
    if (configured) {
      roots[id] = path.resolve(repoRoot, configured);
      continue;
    }
    const fallback = objectValue(root.fallback, `descriptor.roots[${index}].fallback`);
    const fallbackPath = stringValue(
      fallback.path,
      `descriptor.roots[${index}].fallback.path`,
    );
    if (fallback.type === "repo-relative") {
      roots[id] = path.resolve(repoRoot, fallbackPath);
    } else if (fallback.type === "home-relative") {
      roots[id] = path.resolve(homeDir, fallbackPath);
    } else {
      throw new Error(`descriptor.roots[${index}].fallback.type is unsupported`);
    }
  }
  return roots;
}

function resolveWorkspace(raw, label, { roots, repoRoot, env, exists }) {
  const workspace = objectValue(raw, label);
  const configuredEnv = envName(workspace.env, `${label}.env`);
  const configured = configuredEnvValue(env, configuredEnv);
  if (configured) {
    const resolved = path.resolve(repoRoot, configured);
    return {
      path: exists(resolved) ? resolved : null,
      source: exists(resolved) ? "environment" : "missing-environment",
      env: configuredEnv,
      attempts: [resolved],
    };
  }
  if (!Array.isArray(workspace.candidates) || workspace.candidates.length === 0) {
    throw new Error(`${label}.candidates must be a non-empty array`);
  }
  const attempts = [];
  for (const [index, rawCandidate] of workspace.candidates.entries()) {
    const candidate = objectValue(rawCandidate, `${label}.candidates[${index}]`);
    const rootId = stringValue(candidate.root, `${label}.candidates[${index}].root`);
    const root = roots[rootId];
    if (!root) throw new Error(`${label}.candidates[${index}].root is unknown`);
    const relative = safeRelativePath(
      candidate.path,
      `${label}.candidates[${index}].path`,
    );
    const resolved = path.resolve(root, relative);
    attempts.push(resolved);
    if (exists(resolved)) {
      return {
        path: resolved,
        source: "discovered",
        env: configuredEnv,
        attempts,
      };
    }
  }
  return { path: null, source: "missing", env: configuredEnv, attempts };
}

function resolveEndpoint(raw, label, env) {
  const endpoint = objectValue(raw, label);
  const configuredEnv = envName(endpoint.env, `${label}.env`);
  const parsed = exactHttpOrigin(
    configuredEnvValue(env, configuredEnv) ||
      stringValue(endpoint.defaultOrigin, `${label}.defaultOrigin`),
    `${label}.origin`,
  );
  const healthPath = stringValue(endpoint.healthPath, `${label}.healthPath`);
  if (!healthPath.startsWith("/") || healthPath.startsWith("//") || healthPath.includes("..")) {
    throw new Error(`${label}.healthPath must be a safe absolute path`);
  }
  const interfacePath = endpoint.interfacePath === undefined
    ? undefined
    : stringValue(endpoint.interfacePath, `${label}.interfacePath`);
  if (
    interfacePath !== undefined &&
    (!interfacePath.startsWith("/") || interfacePath.startsWith("//") || interfacePath.includes(".."))
  ) {
    throw new Error(`${label}.interfacePath must be a safe absolute path`);
  }
  return {
    env: configuredEnv,
    origin: parsed.origin,
    port: endpointPort(parsed),
    local: localHostname(parsed.hostname),
    ...(interfacePath
      ? {
          interfacePath,
          url: new URL(interfacePath, `${parsed.origin}/`).toString(),
        }
      : {}),
    healthPath,
    healthUrl: new URL(healthPath, `${parsed.origin}/`).toString(),
  };
}

function resolveLaunch(raw, label) {
  const launch = objectValue(raw, label);
  const command = optionalString(launch.command, `${label}.command`);
  const adapter = optionalString(launch.adapter, `${label}.adapter`);
  if (Boolean(command) === Boolean(adapter)) {
    throw new Error(`${label} must declare exactly one of command or adapter`);
  }
  const env = launch.env === undefined
    ? {}
    : Object.fromEntries(
        Object.entries(objectValue(launch.env, `${label}.env`)).map(([name, value]) => [
          childEnvName(name, `${label}.env.${name}`),
          stringValue(value, `${label}.env.${name}`),
        ]),
      );
  const stdio = launch.stdio === undefined
    ? undefined
    : stringValue(launch.stdio, `${label}.stdio`);
  if (stdio !== undefined && !STDIO_MODES.has(stdio)) {
    throw new Error(`${label}.stdio is unsupported`);
  }
  return {
    ...(command ? { command } : { adapter }),
    args: launch.args === undefined ? [] : stringList(launch.args, `${label}.args`),
    env,
    ...(stdio ? { stdio } : {}),
    ...(launch.prepare === undefined
      ? {}
      : { prepare: stringValue(launch.prepare, `${label}.prepare`) }),
    requiredPaths: launch.requiredPaths === undefined
      ? []
      : stringList(launch.requiredPaths, `${label}.requiredPaths`).map((entry, index) =>
          safeRelativePath(entry, `${label}.requiredPaths[${index}]`)
        ),
  };
}

function resolveReadiness(raw, label) {
  const readiness = objectValue(raw, label);
  const mode = stringValue(readiness.mode, `${label}.mode`);
  if (!READINESS_MODES.has(mode)) throw new Error(`${label}.mode is unsupported`);
  const timeoutMs = readiness.timeoutMs === undefined
    ? undefined
    : Number(readiness.timeoutMs);
  if (timeoutMs !== undefined && (!Number.isFinite(timeoutMs) || timeoutMs <= 0)) {
    throw new Error(`${label}.timeoutMs must be a positive number`);
  }
  const startupTimeoutMs = readiness.startupTimeoutMs === undefined
    ? undefined
    : Number(readiness.startupTimeoutMs);
  if (startupTimeoutMs !== undefined && (!Number.isFinite(startupTimeoutMs) || startupTimeoutMs <= 0)) {
    throw new Error(`${label}.startupTimeoutMs must be a positive number`);
  }
  if (
    readiness.degradedStatuses !== undefined
    && !Array.isArray(readiness.degradedStatuses)
  ) {
    throw new Error(`${label}.degradedStatuses must be an array`);
  }
  const degradedStatuses = readiness.degradedStatuses === undefined
    ? []
    : readiness.degradedStatuses.map((status, index) => {
        const parsed = Number(status);
        if (!Number.isInteger(parsed) || parsed < 100 || parsed > 599) {
          throw new Error(`${label}.degradedStatuses[${index}] is invalid`);
        }
        return parsed;
      });
  if (mode === "text" && readiness.expectedText === undefined) {
    throw new Error(`${label}.expectedText is required for text readiness`);
  }
  return {
    mode,
    ...(readiness.expectedService === undefined
      ? {}
      : { expectedService: stringValue(readiness.expectedService, `${label}.expectedService`) }),
    ...(readiness.expectedText === undefined
      ? {}
      : { expectedText: stringValue(readiness.expectedText, `${label}.expectedText`) }),
    ...(timeoutMs === undefined ? {} : { timeoutMs }),
    ...(startupTimeoutMs === undefined ? {} : { startupTimeoutMs }),
    ...(readiness.timeoutEnv === undefined
      ? {}
      : { timeoutEnv: envName(readiness.timeoutEnv, `${label}.timeoutEnv`) }),
    degradedStatuses,
  };
}

function resolveService(raw, label, { workspaces, endpoints }) {
  const service = objectValue(raw, label);
  const id = stringValue(service.id, `${label}.id`);
  if (!ID_PATTERN.test(id)) throw new Error(`${label}.id is invalid`);
  const workspace = stringValue(service.workspace, `${label}.workspace`);
  const endpoint = stringValue(service.endpoint, `${label}.endpoint`);
  if (!Object.hasOwn(workspaces, workspace)) {
    throw new Error(`${label}.workspace is unknown`);
  }
  if (!Object.hasOwn(endpoints, endpoint)) {
    throw new Error(`${label}.endpoint is unknown`);
  }
  const criticality = objectValue(service.criticality, `${label}.criticality`);
  const localCriticality = stringValue(criticality.local, `${label}.criticality.local`);
  const remoteCriticality = stringValue(criticality.remote, `${label}.criticality.remote`);
  if (!CRITICALITIES.has(localCriticality) || !CRITICALITIES.has(remoteCriticality)) {
    throw new Error(`${label}.criticality contains an unsupported value`);
  }
  return {
    id,
    label: stringValue(service.label, `${label}.label`),
    workspace,
    endpoint,
    criticality: { local: localCriticality, remote: remoteCriticality },
    launch: resolveLaunch(service.launch, `${label}.launch`),
    readiness: resolveReadiness(service.readiness, `${label}.readiness`),
  };
}

function resolveProfiles(raw, runtimeIds) {
  const profiles = objectValue(raw, "descriptor.profiles");
  const result = {};
  for (const [name, rawProfile] of Object.entries(profiles)) {
    if (!ID_PATTERN.test(name)) throw new Error(`descriptor.profiles.${name} is invalid`);
    const profile = objectValue(rawProfile, `descriptor.profiles.${name}`);
    const preCore = stringList(
      profile.preCore,
      `descriptor.profiles.${name}.preCore`,
    );
    const optional = stringList(
      profile.optional,
      `descriptor.profiles.${name}.optional`,
    );
    const selected = [...preCore, ...optional];
    if (new Set(selected).size !== selected.length) {
      throw new Error(`descriptor.profiles.${name} contains duplicate runtimes`);
    }
    for (const runtimeId of selected) {
      if (!runtimeIds.has(runtimeId)) {
        throw new Error(`descriptor.profiles.${name} references unknown runtime ${runtimeId}`);
      }
    }
    result[name] = {
      preCore,
      optional,
      externalRuntimeIds: selected,
    };
  }
  if (!["core", "local", "all"].every((name) => Object.hasOwn(result, name))) {
    throw new Error("descriptor.profiles must define core, local and all");
  }
  return result;
}

export function resolveExternalModRuntimes(
  descriptor,
  {
    repoRoot = REPO_ROOT,
    homeDir = os.homedir(),
    env = process.env,
    exists = existsSync,
  } = {},
) {
  const value = objectValue(descriptor, "descriptor");
  if (!["1.0", "2.0"].includes(value.schemaVersion)) {
    throw new Error("unsupported runtime descriptor version");
  }
  const roots = resolveRoots(value.roots, { repoRoot, homeDir, env });
  if (!Array.isArray(value.runtimes) || value.runtimes.length === 0) {
    throw new Error("descriptor.runtimes must be a non-empty array");
  }
  const runtimes = value.runtimes.map((rawRuntime, index) => {
    const runtime = objectValue(rawRuntime, `descriptor.runtimes[${index}]`);
    const id = stringValue(runtime.id, `descriptor.runtimes[${index}].id`);
    if (!ID_PATTERN.test(id)) throw new Error(`${id} is not a valid runtime id`);
    const workspaces = objectValue(runtime.workspaces, `${id}.workspaces`);
    const endpoints = objectValue(runtime.endpoints, `${id}.endpoints`);
    const resolvedWorkspaces = Object.fromEntries(
      Object.entries(workspaces).map(([name, workspace]) => [
        name,
        resolveWorkspace(workspace, `${id}.workspaces.${name}`, {
          roots,
          repoRoot,
          env,
          exists,
        }),
      ]),
    );
    const resolvedEndpoints = Object.fromEntries(
      Object.entries(endpoints).map(([name, endpoint]) => [
        name,
        resolveEndpoint(endpoint, `${id}.endpoints.${name}`, env),
      ]),
    );
    const services = runtime.services === undefined
      ? []
      : runtime.services.map((service, serviceIndex) =>
          resolveService(service, `${id}.services[${serviceIndex}]`, {
            workspaces: resolvedWorkspaces,
            endpoints: resolvedEndpoints,
          })
        );
    if (new Set(services.map((service) => service.id)).size !== services.length) {
      throw new Error(`${id}.services ids must be unique`);
    }
    return {
      id,
      label: stringValue(runtime.label, `${id}.label`),
      adapter: stringValue(runtime.adapter, `${id}.adapter`),
      workspaces: resolvedWorkspaces,
      endpoints: resolvedEndpoints,
      services,
    };
  });
  const ids = runtimes.map(({ id }) => id);
  if (new Set(ids).size !== ids.length) throw new Error("runtime ids must be unique");
  const serviceIds = runtimes.flatMap((runtime) => runtime.services.map(({ id }) => id));
  if (new Set(serviceIds).size !== serviceIds.length) {
    throw new Error("runtime service ids must be globally unique");
  }
  return {
    schemaVersion: value.schemaVersion,
    roots,
    profiles: value.schemaVersion === "2.0"
      ? resolveProfiles(value.profiles, new Set(ids))
      : undefined,
    runtimes,
    byId: Object.fromEntries(runtimes.map((runtime) => [runtime.id, runtime])),
  };
}

export async function loadExternalModRuntimes({
  descriptorUrl = DEFAULT_DESCRIPTOR_URL,
  ...options
} = {}) {
  const descriptor = JSON.parse(await readFile(descriptorUrl, "utf8"));
  return resolveExternalModRuntimes(descriptor, options);
}

export function runtimeEnvironment(catalog) {
  const result = {};
  for (const runtime of catalog.runtimes) {
    for (const workspace of Object.values(runtime.workspaces)) {
      if (workspace.path) result[workspace.env] = workspace.path;
    }
    for (const endpoint of Object.values(runtime.endpoints)) {
      result[endpoint.env] = endpoint.origin;
    }
  }
  return result;
}
