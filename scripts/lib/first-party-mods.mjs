import { readFile } from "node:fs/promises";

const REPO_ROOT = new URL("../../", import.meta.url);
const MOD_ID_PATTERN = /^[a-z][a-z0-9-]{2,63}$/;
const CATEGORY_PATTERN = /^[a-z][a-z0-9-]{1,31}$/;
const NAVIGATION_ICONS = new Set([
  "today",
  "research",
  "market",
  "quant",
  "trading",
  "settings",
  "module",
]);

export const DEFAULT_INTEGRATION_URLS = [
  new URL("integrations/vibe-investment/integration.json", REPO_ROOT),
  new URL("integrations/vibe-trading/integration.json", REPO_ROOT),
];

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

function manifestFromMod(integration, mod, baseUrl) {
  const modId = assertString(mod.id, `${integration.id}.mods[].id`);
  if (!MOD_ID_PATTERN.test(modId)) {
    throw new Error(`${integration.id} contains an invalid Mod id: ${modId}`);
  }
  const category = assertString(
    mod.category,
    `${integration.id}.${modId}.category`,
  );
  if (!CATEGORY_PATTERN.test(category)) {
    throw new Error(`${integration.id}.${modId} contains an invalid category`);
  }
  const navigation = assertObject(
    mod.navigation,
    `${integration.id}.${modId}.navigation`,
  );
  const icon = assertString(
    navigation.icon,
    `${integration.id}.${modId}.navigation.icon`,
  );
  if (!NAVIGATION_ICONS.has(icon)) {
    throw new Error(`${integration.id}.${modId} contains an invalid icon`);
  }
  const route = assertString(mod.route, `${integration.id}.${modId}.route`);
  if (!route.startsWith("/") || route.startsWith("//") || route.includes("..")) {
    throw new Error(`${integration.id}.${modId} contains an unsafe route`);
  }

  return {
    schemaVersion: "1.0",
    id: modId,
    name: assertString(mod.name, `${integration.id}.${modId}.name`),
    version: "0.1.0",
    category,
    navigation: {
      groupLabel: assertString(
        navigation.groupLabel,
        `${integration.id}.${modId}.navigation.groupLabel`,
      ),
      groupOrder: navigation.groupOrder,
      itemOrder: navigation.itemOrder,
      icon,
    },
    entry: {
      type: "external",
      url: new URL(route, `${baseUrl}/`).toString(),
    },
    permissions: stringArray(
      mod.permissions,
      `${integration.id}.${modId}.permissions`,
    ),
    dataServices: stringArray(
      mod.dataServices,
      `${integration.id}.${modId}.dataServices`,
    ),
    agentCapabilities: stringArray(
      mod.agentCapabilities,
      `${integration.id}.${modId}.agentCapabilities`,
    ),
    events: { emits: [], accepts: [] },
  };
}

export async function loadFirstPartyMods({
  env = process.env,
  integrationUrls = DEFAULT_INTEGRATION_URLS,
} = {}) {
  const integrations = await Promise.all(
    integrationUrls.map(async (url) => {
      const raw = JSON.parse(await readFile(url, "utf8"));
      const integration = assertObject(raw, url.pathname);
      const integrationId = assertString(integration.id, `${url.pathname}.id`);
      const baseUrlEnv = assertString(
        integration.baseUrlEnv,
        `${integrationId}.baseUrlEnv`,
      );
      const configuredBaseUrl = env[baseUrlEnv] || integration.defaultBaseUrl;
      const baseUrl = exactHttpOrigin(
        assertString(configuredBaseUrl, `${integrationId}.baseUrl`),
        baseUrlEnv,
      );
      if (!Array.isArray(integration.mods) || integration.mods.length === 0) {
        throw new Error(`${integrationId}.mods must contain at least one Mod`);
      }
      return {
        id: integrationId,
        name: assertString(integration.name, `${integrationId}.name`),
        upstream: assertString(integration.upstream, `${integrationId}.upstream`),
        baseUrl,
        manifests: integration.mods.map((value) =>
          manifestFromMod(integration, assertObject(value, `${integrationId}.mods[]`), baseUrl),
        ),
      };
    }),
  );

  const ids = integrations.flatMap((integration) =>
    integration.manifests.map((manifest) => manifest.id),
  );
  if (new Set(ids).size !== ids.length) {
    throw new Error("first-party integrations contain duplicate Mod ids");
  }
  return integrations;
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
    const detail =
      body && typeof body === "object" && typeof body.detail === "string"
        ? body.detail
        : `HTTP ${response.status}`;
    throw new Error(`${init?.method || "GET"} ${url} failed: ${detail}`);
  }
  return body;
}

export async function registerFirstPartyMods({
  apiUrl = "http://127.0.0.1:8901",
  env = process.env,
  fetchImpl = fetch,
  dryRun = false,
} = {}) {
  const controlPlaneOrigin = exactHttpOrigin(apiUrl, "VibeDesk API URL");
  const integrations = await loadFirstPartyMods({ env });
  const desired = integrations.flatMap((integration) => integration.manifests);
  if (dryRun) {
    return { created: desired, skipped: [], integrations };
  }

  const current = await requestJson(fetchImpl, `${controlPlaneOrigin}/api/mods`);
  if (!Array.isArray(current)) {
    throw new Error("VibeDesk Mod registry returned malformed data");
  }
  const publishedById = new Map(
    current
      .filter((item) => item && typeof item === "object")
      .map((item) => [item.moduleId, item]),
  );
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

  return { created, skipped, integrations };
}
