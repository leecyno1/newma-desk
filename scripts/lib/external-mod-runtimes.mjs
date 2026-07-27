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
const ENV_PATTERN = /^(?:NEWMA_DOCK|VIBEDESK)_[A-Z0-9_]+$/;

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

function envName(value, label) {
  const name = stringValue(value, label);
  if (!ENV_PATTERN.test(name)) {
    throw new Error(`${label} must be a NEWMA_DOCK_* or VIBEDESK_* name`);
  }
  return name;
}

function configuredEnvValue(env, name) {
  const configured = env[name]?.trim();
  if (configured || !name.startsWith("NEWMA_DOCK_")) return configured;
  return env[`VIBEDESK_${name.slice("NEWMA_DOCK_".length)}`]?.trim();
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
  return {
    env: configuredEnv,
    origin: parsed.origin,
    port: endpointPort(parsed),
    local: localHostname(parsed.hostname),
    healthPath,
    healthUrl: new URL(healthPath, `${parsed.origin}/`).toString(),
  };
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
  if (value.schemaVersion !== "1.0") throw new Error("unsupported runtime descriptor version");
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
    return {
      id,
      label: stringValue(runtime.label, `${id}.label`),
      adapter: stringValue(runtime.adapter, `${id}.adapter`),
      workspaces: Object.fromEntries(
        Object.entries(workspaces).map(([name, workspace]) => [
          name,
          resolveWorkspace(workspace, `${id}.workspaces.${name}`, {
            roots,
            repoRoot,
            env,
            exists,
          }),
        ]),
      ),
      endpoints: Object.fromEntries(
        Object.entries(endpoints).map(([name, endpoint]) => [
          name,
          resolveEndpoint(endpoint, `${id}.endpoints.${name}`, env),
        ]),
      ),
    };
  });
  const ids = runtimes.map(({ id }) => id);
  if (new Set(ids).size !== ids.length) throw new Error("runtime ids must be unique");
  return {
    schemaVersion: "1.0",
    roots,
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
