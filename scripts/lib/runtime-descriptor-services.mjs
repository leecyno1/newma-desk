import { existsSync } from "node:fs";
import path from "node:path";

import { createHttpProbe } from "./runtime-supervisor.mjs";

const TEMPLATE_PATTERN = /\{\{([a-zA-Z0-9_.-]+)\}\}/g;

function configuredEnvValue(env, name) {
  const prefixes = ["NEWMA_DESK_", "NEWMA_DOCK_", "VIBEDESK_"];
  const prefix = prefixes.find((candidate) => name.startsWith(candidate));
  if (!prefix) return env[name]?.trim();
  const suffix = name.slice(prefix.length);
  return prefixes
    .map((candidate) => env[`${candidate}${suffix}`]?.trim())
    .find(Boolean);
}

function pythonAt(workspace, exists = existsSync) {
  const local = path.join(workspace, ".venv", "bin", "python");
  return exists(local) ? local : "python3";
}

function contextValue(context, key) {
  let current = context;
  for (const part of key.split(".")) {
    if (current === null || current === undefined || !Object.hasOwn(current, part)) {
      throw new Error(`未知 Runtime Descriptor 模板变量：${key}`);
    }
    current = current[part];
  }
  if (["string", "number", "boolean"].includes(typeof current)) return String(current);
  throw new Error(`Runtime Descriptor 模板变量不是标量：${key}`);
}

export function interpolateRuntimeTemplate(value, context) {
  return String(value).replace(TEMPLATE_PATTERN, (_match, key) => contextValue(context, key));
}

function createTemplateContext(runtime, service, workspace, endpoint, exists) {
  return {
    workspace,
    python: workspace ? pythonAt(workspace, exists) : "python3",
    endpoint,
    endpoints: runtime.endpoints,
    workspaces: Object.fromEntries(
      Object.entries(runtime.workspaces).map(([name, value]) => [name, value.path || ""]),
    ),
    runtime: { id: runtime.id, label: runtime.label },
    service: { id: service.id, label: service.label },
  };
}

function readinessTimeout(readiness, env) {
  const configured = readiness.timeoutEnv
    ? configuredEnvValue(env, readiness.timeoutEnv)
    : undefined;
  const parsed = configured === undefined ? readiness.timeoutMs : Number(configured);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined;
}

function createReadinessProbe(endpoint, readiness, env) {
  const timeoutMs = readinessTimeout(readiness, env);
  const common = {
    degradedStatuses: readiness.degradedStatuses,
    ...(timeoutMs === undefined ? {} : { timeoutMs }),
  };
  if (readiness.mode === "html") {
    return createHttpProbe(endpoint.healthUrl, { ...common, expectHtml: true });
  }
  if (readiness.mode === "text") {
    return createHttpProbe(endpoint.healthUrl, {
      ...common,
      expectHtml: false,
      expectedText: readiness.expectedText,
    });
  }
  return createHttpProbe(endpoint.healthUrl, {
    ...common,
    expectHtml: false,
    expectedService: readiness.expectedService,
  });
}

function localLaunch(runtime, service, {
  env,
  exists,
  launchAdapters,
  prepareAdapters,
}) {
  const workspace = runtime.workspaces[service.workspace].path;
  const endpoint = runtime.endpoints[service.endpoint];
  if (!workspace || !endpoint.local) return {};
  if (service.launch.requiredPaths.some((relative) => !exists(path.join(workspace, relative)))) {
    return null;
  }

  const context = createTemplateContext(runtime, service, workspace, endpoint, exists);
  const descriptorEnv = Object.fromEntries(
    Object.entries(service.launch.env).map(([name, value]) => [
      name,
      interpolateRuntimeTemplate(value, context),
    ]),
  );
  let launch;
  if (service.launch.command) {
    launch = {
      command: interpolateRuntimeTemplate(service.launch.command, context),
      commandArgs: service.launch.args.map((argument) =>
        interpolateRuntimeTemplate(argument, context)
      ),
    };
  } else {
    const adapter = launchAdapters[service.launch.adapter];
    if (typeof adapter !== "function") {
      throw new Error(`未注册 Runtime Launch Adapter：${service.launch.adapter}`);
    }
    launch = adapter({ runtime, service, workspace, endpoint, context, env, exists });
  }
  if (!launch?.command) {
    throw new Error(`${service.label} 的 Runtime Launch Adapter 未返回 command`);
  }

  let prepare;
  if (service.launch.prepare) {
    const adapter = prepareAdapters[service.launch.prepare];
    if (typeof adapter !== "function") {
      throw new Error(`未注册 Runtime Preparation Adapter：${service.launch.prepare}`);
    }
    prepare = () => adapter({ runtime, service, workspace, endpoint, context });
  }
  return {
    ...launch,
    env: { ...descriptorEnv, ...(launch.env || {}) },
    ...(service.launch.stdio ? { stdio: service.launch.stdio } : {}),
    ...(prepare ? { prepare } : {}),
  };
}

export function createRuntimeService(runtime, service, {
  env = process.env,
  exists = existsSync,
  launchAdapters = {},
  prepareAdapters = {},
} = {}) {
  const workspace = runtime.workspaces[service.workspace].path;
  const endpoint = runtime.endpoints[service.endpoint];
  const launch = localLaunch(runtime, service, {
    env,
    exists,
    launchAdapters,
    prepareAdapters,
  });
  if (launch === null) return null;
  return {
    id: service.id,
    label: service.label,
    cwd: workspace,
    ...launch,
    criticality: endpoint.local
      ? service.criticality.local
      : service.criticality.remote,
    url: endpoint.healthUrl,
    ...(service.readiness.startupTimeoutMs === undefined
      ? {}
      : { startupTimeoutMs: service.readiness.startupTimeoutMs }),
    probe: createReadinessProbe(endpoint, service.readiness, env),
  };
}

export function createRuntimeServiceGroups(catalog, options = {}) {
  return Object.fromEntries(
    catalog.runtimes.map((runtime) => [
      runtime.id,
      runtime.services
        .map((service) => createRuntimeService(runtime, service, options))
        .filter(Boolean),
    ]),
  );
}
