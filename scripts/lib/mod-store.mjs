import { readFile } from "node:fs/promises";

const REPO_ROOT = new URL("../../", import.meta.url);
const STORE_ROOT = new URL("mods/", REPO_ROOT);
const DEFAULT_STORE_URL = new URL("store.json", STORE_ROOT);
const MOD_ID_PATTERN = /^[a-z][a-z0-9-]{2,63}$/;
const CATEGORY_PATTERN = /^[a-z][a-z0-9-]{1,31}$/;
const VERSION_PATTERN = /^\d+\.\d+\.\d+$/;
const NAVIGATION_ICONS = new Set([
  "today",
  "research",
  "market",
  "quant",
  "trading",
  "settings",
  "module",
]);

function assertObject(value, label) {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${label} must be an object`);
  }
  return value;
}

function assertString(value, label) {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${label} must be a non-empty string`);
  }
  return value;
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
    parsed.pathname !== "/" ||
    parsed.search ||
    parsed.hash
  ) {
    throw new Error(`${label} must be an HTTP(S) origin`);
  }
  return parsed.origin;
}

function stringArray(value, label) {
  if (value === undefined) return [];
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string")) {
    throw new Error(`${label} must be an array of strings`);
  }
  return [...value];
}

function safeStorePath(value, label) {
  const path = assertString(value, label);
  if (
    path.startsWith("/") ||
    path.includes("\\") ||
    path.split("/").some((part) => !part || part === "." || part === "..") ||
    !path.endsWith("/mod.json")
  ) {
    throw new Error(`${label} must be a safe */mod.json path`);
  }
  return path;
}

function navigationValue(raw, label) {
  const navigation = assertObject(raw, label);
  const icon = assertString(navigation.icon, `${label}.icon`);
  if (!NAVIGATION_ICONS.has(icon)) {
    throw new Error(`${label}.icon is invalid`);
  }
  return {
    groupLabel: assertString(navigation.groupLabel, `${label}.groupLabel`),
    groupOrder: navigation.groupOrder,
    itemOrder: navigation.itemOrder,
    icon,
  };
}

function manifestFromDescriptor(descriptor, env) {
  const id = assertString(descriptor.id, "descriptor.id");
  if (!MOD_ID_PATTERN.test(id)) throw new Error(`invalid Mod id: ${id}`);
  const version = assertString(descriptor.version, `${id}.version`);
  if (!VERSION_PATTERN.test(version)) throw new Error(`${id}.version is invalid`);
  const template = assertObject(descriptor.manifest, `${id}.manifest`);
  const category = assertString(template.category, `${id}.manifest.category`);
  if (!CATEGORY_PATTERN.test(category)) throw new Error(`${id}.category is invalid`);
  const runtime = assertObject(descriptor.runtime, `${id}.runtime`);
  let entry;
  if (runtime.type === "external") {
    const envName = assertString(runtime.baseUrlEnv, `${id}.runtime.baseUrlEnv`);
    const baseUrl = exactHttpOrigin(
      env[envName] || assertString(runtime.defaultBaseUrl, `${id}.runtime.defaultBaseUrl`),
      envName,
    );
    const route = assertString(runtime.route, `${id}.runtime.route`);
    if (!route.startsWith("/") || route.startsWith("//") || route.includes("..")) {
      throw new Error(`${id}.runtime.route is unsafe`);
    }
    entry = { type: "external", url: new URL(route, `${baseUrl}/`).toString() };
  } else if (runtime.type === "direct") {
    entry = assertObject(runtime.entry, `${id}.runtime.entry`);
  } else {
    throw new Error(`${id}.runtime.type is invalid`);
  }

  return {
    schemaVersion: "1.0",
    id,
    name: assertString(descriptor.name, `${id}.name`),
    version,
    category,
    ...(template.navigation
      ? { navigation: navigationValue(template.navigation, `${id}.manifest.navigation`) }
      : {}),
    entry,
    permissions: stringArray(template.permissions, `${id}.manifest.permissions`),
    dataServices: stringArray(template.dataServices, `${id}.manifest.dataServices`),
    agentCapabilities: stringArray(
      template.agentCapabilities,
      `${id}.manifest.agentCapabilities`,
    ),
    events: template.events || { emits: [], accepts: [] },
    ...(template.refresh ? { refresh: template.refresh } : {}),
  };
}

export async function loadModStore({
  env = process.env,
  storeUrl = DEFAULT_STORE_URL,
} = {}) {
  const rawStore = JSON.parse(await readFile(storeUrl, "utf8"));
  const store = assertObject(rawStore, storeUrl.pathname);
  if (store.schemaVersion !== "1.0") throw new Error("unsupported Mod store schema");
  const entries = store.mods;
  if (!Array.isArray(entries) || entries.length === 0) {
    throw new Error("Mod store must contain at least one Mod");
  }
  const mods = await Promise.all(entries.map(async (rawEntry) => {
    const entry = assertObject(rawEntry, "store.mods[]");
    const id = assertString(entry.id, "store.mods[].id");
    const path = safeStorePath(entry.path, `${id}.path`);
    const descriptorUrl = new URL(path, STORE_ROOT);
    const descriptor = assertObject(
      JSON.parse(await readFile(descriptorUrl, "utf8")),
      descriptorUrl.pathname,
    );
    if (descriptor.id !== id) throw new Error(`${id} descriptor id mismatch`);
    return {
      id,
      path,
      defaultInstall: entry.defaultInstall === true,
      descriptor,
      manifest: manifestFromDescriptor(descriptor, env),
    };
  }));
  const ids = mods.map((mod) => mod.id);
  if (new Set(ids).size !== ids.length) throw new Error("Mod store contains duplicate ids");
  return {
    id: assertString(store.id, "store.id"),
    name: assertString(store.name, "store.name"),
    git: assertObject(store.git, "store.git"),
    mods,
  };
}

function stableValue(value) {
  if (Array.isArray(value)) return value.map(stableValue);
  if (typeof value !== "object" || value === null) return value;
  return Object.fromEntries(
    Object.entries(value)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => [key, stableValue(item)]),
  );
}

export function manifestsEqual(left, right) {
  return JSON.stringify(stableValue(left)) === JSON.stringify(stableValue(right));
}

async function responseJson(response) {
  try {
    return await response.json();
  } catch {
    return undefined;
  }
}

async function requestJson(fetchImpl, url, init) {
  const response = await fetchImpl(url, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body === undefined ? {} : { "Content-Type": "application/json" }),
      ...init?.headers,
    },
  });
  const body = await responseJson(response);
  if (!response.ok) {
    const detail = body && typeof body.detail === "string" ? body.detail : `HTTP ${response.status}`;
    throw new Error(`${init?.method || "GET"} ${url} failed: ${detail}`);
  }
  return body;
}

export async function registerDefaultMods({
  apiUrl = "http://127.0.0.1:8901",
  env = process.env,
  fetchImpl = fetch,
  dryRun = false,
} = {}) {
  const controlPlaneOrigin = exactHttpOrigin(apiUrl, "VibeDesk API URL");
  const store = await loadModStore({ env });
  const desired = store.mods.filter((mod) => mod.defaultInstall).map((mod) => mod.manifest);
  if (dryRun) return { created: desired, skipped: [], store };

  const current = await requestJson(fetchImpl, `${controlPlaneOrigin}/api/mods`);
  if (!Array.isArray(current)) throw new Error("VibeDesk Mod registry returned malformed data");
  const publishedById = new Map(current.map((item) => [item.moduleId, item]));
  const created = [];
  const skipped = [];
  for (const manifest of desired) {
    const existing = publishedById.get(manifest.id);
    if (existing && manifestsEqual(existing.manifest, manifest)) {
      skipped.push(manifest);
      continue;
    }
    const draft = await requestJson(
      fetchImpl,
      `${controlPlaneOrigin}/api/mods/drafts`,
      { method: "POST", body: JSON.stringify(manifest) },
    );
    if (!draft || !Number.isInteger(draft.revision)) {
      throw new Error(`VibeDesk returned an invalid draft for ${manifest.id}`);
    }
    await requestJson(
      fetchImpl,
      `${controlPlaneOrigin}/api/mods/${encodeURIComponent(manifest.id)}/revisions/${draft.revision}/publish`,
      { method: "POST" },
    );
    created.push(manifest);
  }
  return { created, skipped, store };
}

export async function standardizeDefaultMods({
  apiUrl = "http://127.0.0.1:8901",
  env = process.env,
  fetchImpl = fetch,
  dryRun = false,
} = {}) {
  const controlPlaneOrigin = exactHttpOrigin(apiUrl, "VibeDesk API URL");
  const registration = await registerDefaultMods({
    apiUrl,
    env,
    fetchImpl,
    dryRun,
  });
  const storeIds = new Set(registration.store.mods.map((mod) => mod.id));
  const defaultIds = new Set(
    registration.store.mods
      .filter((mod) => mod.defaultInstall)
      .map((mod) => mod.id),
  );
  const current = dryRun
    ? []
    : await requestJson(fetchImpl, `${controlPlaneOrigin}/api/mods`);
  if (!Array.isArray(current)) {
    throw new Error("VibeDesk Mod registry returned malformed data");
  }
  const removable = current.filter(
    (item) =>
      item &&
      typeof item.moduleId === "string" &&
      storeIds.has(item.moduleId) &&
      !defaultIds.has(item.moduleId),
  );
  const disabled = [];
  for (const item of removable) {
    await requestJson(
      fetchImpl,
      `${controlPlaneOrigin}/api/mods/${encodeURIComponent(item.moduleId)}/disable`,
      { method: "POST" },
    );
    disabled.push(item.moduleId);
  }
  return { ...registration, disabled };
}
