import { readFile } from "node:fs/promises";

const REPO_ROOT = new URL("../../", import.meta.url);
const STORE_ROOT = new URL("mods/", REPO_ROOT);
const DEFAULT_STORE_URL = new URL("store.json", STORE_ROOT);
const MOD_ID_PATTERN = /^[a-z][a-z0-9-]{2,63}$/;
const SUITE_ID_PATTERN = /^[a-z][a-z0-9-]{1,47}$/;
const CATEGORY_PATTERN = /^[a-z][a-z0-9-]{1,31}$/;
const VERSION_PATTERN = /^\d+\.\d+\.\d+$/;
const WELL_KNOWN_SUITE_PATH = "/.well-known/newma-desk-suite.json";
const LEGACY_NEWMA_DOCK_SUITE_PATH = "/.well-known/newma-dock-suite.json";
const LEGACY_VIBEDESK_SUITE_PATH = "/.well-known/vibedesk-suite.json";
const SUITE_ENV_PATTERN = /^(?:NEWMA_DESK|NEWMA_DOCK|VIBEDESK)_[A-Z0-9_]+$/;
const MAX_DESCRIPTOR_BYTES = 256 * 1024;
const DEFAULT_DISCOVERY_TIMEOUT_MS = 5000;
const LOCAL_URL_ORIGIN = "https://module.local";
const NAVIGATION_ICONS = new Set([
  "today",
  "research",
  "market",
  "quant",
  "trading",
  "settings",
  "module",
]);
const INVESTMENT_DOMAIN_IDS = new Set([
  "global-intelligence",
  "fundamentals",
  "policy-intelligence",
  "capital-flow",
  "market-surface",
  "industry-research",
  "equity-research",
  "fund-research",
  "asset-allocation",
  "trading",
  "strategy-research",
  "risk-management",
  "quant-research",
  "investment-committee",
  "creator-studio",
  "deepsee",
]);
const ENGLISH_TITLE_TOKENS = new Map([
  ["ai", "AI"],
  ["cn", "CN"],
  ["czsc", "CZSC"],
  ["etf", "ETF"],
  ["h", "H"],
  ["hk", "HK"],
  ["hkex", "HKEX"],
  ["llm", "LLM"],
  ["newma", "Newma"],
  ["rss", "RSS"],
  ["us", "US"],
]);

function englishModName(modId) {
  return modId
    .split("-")
    .map((token) => ENGLISH_TITLE_TOKENS.get(token) || `${token[0].toUpperCase()}${token.slice(1)}`)
    .join(" ");
}

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

function assertOnlyKeys(value, allowed, label) {
  const unknown = Object.keys(value).find((key) => !allowed.has(key));
  if (unknown !== undefined) {
    throw new Error(`${label}.${unknown} is unsupported`);
  }
}

function boundedString(value, label, maxLength) {
  const result = assertString(value, label);
  if ([...result].length > maxLength) {
    throw new Error(`${label} must contain at most ${maxLength} characters`);
  }
  return result;
}

function fullyDecode(value) {
  let decoded = value;
  for (let pass = 0; pass < 10; pass += 1) {
    let next;
    try {
      next = decodeURIComponent(decoded);
    } catch {
      return undefined;
    }
    if (next === decoded) return decoded;
    decoded = next;
  }
  return undefined;
}

function safeProjectImageSource(value, label) {
  const source = assertString(value, label);
  if (source.startsWith("/")) {
    if (
      source.startsWith("//") ||
      source.includes("\\") ||
      source.includes("..")
    ) {
      throw new Error(`${label} must be a safe relative or HTTP(S) URL`);
    }
    const pathEnd = source.search(/[?#]/);
    const encodedPath = pathEnd === -1 ? source : source.slice(0, pathEnd);
    const decodedPath = fullyDecode(encodedPath);
    if (
      decodedPath === undefined ||
      !decodedPath.startsWith("/") ||
      decodedPath.startsWith("//") ||
      decodedPath.includes("\\") ||
      decodedPath.includes("..") ||
      decodedPath.split("/").includes(".")
    ) {
      throw new Error(`${label} must be a safe relative or HTTP(S) URL`);
    }
    try {
      if (new URL(source, LOCAL_URL_ORIGIN).origin !== LOCAL_URL_ORIGIN) {
        throw new Error();
      }
    } catch {
      throw new Error(`${label} must be a safe relative or HTTP(S) URL`);
    }
    return source;
  }

  let parsed;
  try {
    parsed = new URL(source);
  } catch {
    throw new Error(`${label} must be a safe relative or HTTP(S) URL`);
  }
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new Error(`${label} must be a safe relative or HTTP(S) URL`);
  }
  return source;
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

function safeStorePath(value, label, suffix = "/mod.json") {
  const path = assertString(value, label);
  if (
    path.startsWith("/") ||
    path.includes("\\") ||
    path.split("/").some((part) => !part || part === "." || part === "..") ||
    !path.endsWith(suffix)
  ) {
    throw new Error(`${label} must be a safe *${suffix} path`);
  }
  return path;
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

function suiteDiscoveryValue(raw, label) {
  const discovery = assertObject(raw, label);
  if (discovery.type !== "http") {
    throw new Error(`${label}.type must be http`);
  }
  const baseUrlEnv = assertString(discovery.baseUrlEnv, `${label}.baseUrlEnv`);
  if (!SUITE_ENV_PATTERN.test(baseUrlEnv)) {
    throw new Error(`${label}.baseUrlEnv is invalid`);
  }
  const path = discovery.path === undefined
    ? WELL_KNOWN_SUITE_PATH
    : assertString(discovery.path, `${label}.path`);
  if (
    ![
      WELL_KNOWN_SUITE_PATH,
      LEGACY_NEWMA_DOCK_SUITE_PATH,
      LEGACY_VIBEDESK_SUITE_PATH,
    ].includes(path)
  ) {
    throw new Error(
      `${label}.path must be ${WELL_KNOWN_SUITE_PATH}, ${LEGACY_NEWMA_DOCK_SUITE_PATH} or ${LEGACY_VIBEDESK_SUITE_PATH}`,
    );
  }
  return {
    type: "http",
    baseUrlEnv,
    defaultBaseUrl: exactHttpOrigin(
      assertString(discovery.defaultBaseUrl, `${label}.defaultBaseUrl`),
      `${label}.defaultBaseUrl`,
    ),
    path,
  };
}

async function fetchSuiteDescriptor({
  discovery,
  env,
  fetchImpl,
  timeoutMs,
  label,
}) {
  const baseUrl = exactHttpOrigin(
    configuredEnvValue(env, discovery.baseUrlEnv) || discovery.defaultBaseUrl,
    discovery.baseUrlEnv,
  );
  const paths = discovery.path === WELL_KNOWN_SUITE_PATH
    ? [
        WELL_KNOWN_SUITE_PATH,
        LEGACY_NEWMA_DOCK_SUITE_PATH,
        LEGACY_VIBEDESK_SUITE_PATH,
      ]
    : [discovery.path];
  let response;
  let url;
  for (const [index, path] of paths.entries()) {
    url = new URL(path, `${baseUrl}/`).toString();
    try {
      response = await fetchImpl(url, {
        headers: { Accept: "application/json" },
        redirect: "error",
        signal: AbortSignal.timeout(timeoutMs),
      });
    } catch (error) {
      throw new Error(`${label} discovery failed: ${error instanceof Error ? error.message : String(error)}`);
    }
    if (response.ok) break;
    if (response.status !== 404 || index === paths.length - 1) {
      throw new Error(`${label} discovery failed: HTTP ${response.status}`);
    }
  }
  const contentLengthHeader = response.headers.get("content-length");
  const contentLength = contentLengthHeader === null
    ? undefined
    : Number(contentLengthHeader);
  if (Number.isFinite(contentLength) && contentLength > MAX_DESCRIPTOR_BYTES) {
    throw new Error(`${label} discovery response is too large`);
  }
  const chunks = [];
  let totalBytes = 0;
  if (response.body) {
    const reader = response.body.getReader();
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      totalBytes += value.byteLength;
      if (totalBytes > MAX_DESCRIPTOR_BYTES) {
        await reader.cancel();
        throw new Error(`${label} discovery response is too large`);
      }
      chunks.push(value);
    }
  }
  const bytes = new Uint8Array(totalBytes);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  let body;
  try {
    body = JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    throw new Error(`${label} discovery returned invalid JSON`);
  }
  return {
    descriptor: assertObject(body, `${label} discovery response`),
    url,
  };
}

function nonNegativeInteger(value, label, fallback = 100) {
  if (value === undefined) return fallback;
  if (!Number.isInteger(value) || value < 0) {
    throw new Error(`${label} must be a non-negative integer`);
  }
  return value;
}

function projectLogoValue(raw, label) {
  const logo = assertObject(raw, label);
  const type = assertString(logo.type, `${label}.type`);
  if (type === "icon") {
    assertOnlyKeys(logo, new Set(["type", "name"]), label);
    const name = assertString(logo.name, `${label}.name`);
    if (!NAVIGATION_ICONS.has(name)) {
      throw new Error(`${label}.name is invalid`);
    }
    return { type, name };
  }
  if (type === "letter") {
    assertOnlyKeys(logo, new Set(["type", "text"]), label);
    if (
      typeof logo.text !== "string" ||
      logo.text.trim() !== logo.text ||
      [...logo.text].length < 1 ||
      [...logo.text].length > 2
    ) {
      throw new Error(`${label}.text must contain 1-2 visible characters`);
    }
    return { type, text: logo.text };
  }
  if (type === "image") {
    assertOnlyKeys(logo, new Set(["type", "src", "alt"]), label);
    return {
      type,
      src: safeProjectImageSource(logo.src, `${label}.src`),
      ...(logo.alt === undefined
        ? {}
        : { alt: boundedString(logo.alt, `${label}.alt`, 80) }),
    };
  }
  throw new Error(`${label}.type is invalid`);
}

function projectValue(raw, label) {
  const project = assertObject(raw, label);
  assertOnlyKeys(
    project,
    new Set(["id", "name", "order", "description", "logo"]),
    label,
  );
  const id = assertString(project.id, `${label}.id`);
  if (!/^[a-z][a-z0-9-]{1,47}$/.test(id)) {
    throw new Error(`${label}.id is invalid`);
  }
  return {
    id,
    name: boundedString(project.name, `${label}.name`, 80),
    order: nonNegativeInteger(project.order, `${label}.order`),
    ...(project.description === undefined
      ? {}
      : {
          description: boundedString(
            project.description,
            `${label}.description`,
            240,
          ),
        }),
    ...(project.logo === undefined
      ? {}
      : { logo: projectLogoValue(project.logo, `${label}.logo`) }),
  };
}

function navigationValue(raw, label) {
  const navigation = assertObject(raw, label);
  const icon = assertString(navigation.icon, `${label}.icon`);
  if (!NAVIGATION_ICONS.has(icon)) {
    throw new Error(`${label}.icon is invalid`);
  }
  const role = navigation.role;
  if (role !== undefined && role !== "page" && role !== "settings") {
    throw new Error(`${label}.role is invalid`);
  }
  let directory;
  if (navigation.directory !== undefined) {
    const value = assertObject(navigation.directory, `${label}.directory`);
    const id = assertString(value.id, `${label}.directory.id`);
    if (!/^[a-z][a-z0-9-]{1,47}$/.test(id)) {
      throw new Error(`${label}.directory.id is invalid`);
    }
    directory = {
      id,
      label: assertString(value.label, `${label}.directory.label`),
      order: nonNegativeInteger(value.order, `${label}.directory.order`),
    };
  }
  return {
    groupLabel: assertString(navigation.groupLabel, `${label}.groupLabel`),
    groupOrder: nonNegativeInteger(navigation.groupOrder, `${label}.groupOrder`),
    itemOrder: nonNegativeInteger(navigation.itemOrder, `${label}.itemOrder`),
    ...(navigation.label !== undefined
      ? { label: assertString(navigation.label, `${label}.label`) }
      : {}),
    ...(directory ? { directory } : {}),
    ...(navigation.project === undefined
      ? {}
      : { project: projectValue(navigation.project, `${label}.project`) }),
    icon,
    ...(role === undefined ? {} : { role }),
  };
}

function suitePageDescriptors(descriptor) {
  if (descriptor.schemaVersion !== "1.0") {
    throw new Error("unsupported Mod Suite schema");
  }
  const suiteId = assertString(descriptor.id, "suite.id");
  if (!SUITE_ID_PATTERN.test(suiteId)) {
    throw new Error(`invalid Mod Suite id: ${suiteId}`);
  }
  const version = assertString(descriptor.version, `${suiteId}.version`);
  if (!VERSION_PATTERN.test(version)) {
    throw new Error(`${suiteId}.version is invalid`);
  }
  const suiteName = boundedString(descriptor.name, `${suiteId}.name`, 80);
  const suiteDescription = boundedString(
    descriptor.description,
    `${suiteId}.description`,
    240,
  );
  const runtime = assertObject(descriptor.runtime, `${suiteId}.runtime`);
  if (runtime.type !== "external") {
    throw new Error(`${suiteId}.runtime.type must be external`);
  }
  const baseUrlEnv = assertString(
    runtime.baseUrlEnv,
    `${suiteId}.runtime.baseUrlEnv`,
  );
  if (!SUITE_ENV_PATTERN.test(baseUrlEnv)) {
    throw new Error(`${suiteId}.runtime.baseUrlEnv is invalid`);
  }
  const defaultBaseUrl = exactHttpOrigin(
    assertString(runtime.defaultBaseUrl, `${suiteId}.runtime.defaultBaseUrl`),
    `${suiteId}.runtime.defaultBaseUrl`,
  );
  const template = assertObject(descriptor.manifest, `${suiteId}.manifest`);
  const parsedSharedNavigation = navigationValue(
    template.navigation,
    `${suiteId}.manifest.navigation`,
  );
  const suiteDirectory = parsedSharedNavigation.directory;
  if (!suiteDirectory || suiteDirectory.id !== suiteId) {
    throw new Error(
      `${suiteId} must use navigation.directory.id=${suiteId} to remain one complete project`,
    );
  }
  const suiteProject = parsedSharedNavigation.project || {
    id: suiteId,
    name: suiteName,
    order: parsedSharedNavigation.groupOrder,
    description: suiteDescription,
  };
  if (!INVESTMENT_DOMAIN_IDS.has(suiteProject.id) && suiteProject.id !== suiteId) {
    throw new Error(
      `${suiteId} must use an investment domain or its own suite id as project id`,
    );
  }
  const sharedNavigation = {
    ...parsedSharedNavigation,
    project: suiteProject,
  };
  const pages = descriptor.pages;
  if (!Array.isArray(pages) || pages.length === 0) {
    throw new Error(`${suiteId}.pages must contain at least one page`);
  }
  const pageIds = new Set();
  return pages.map((rawPage, index) => {
    const page = assertObject(rawPage, `${suiteId}.pages[${index}]`);
    const id = assertString(page.id, `${suiteId}.pages[${index}].id`);
    if (!MOD_ID_PATTERN.test(id) || pageIds.has(id)) {
      throw new Error(`${suiteId}.pages contains an invalid or duplicate Mod id`);
    }
    pageIds.add(id);
    const route = assertString(page.route, `${id}.route`);
    if (!route.startsWith("/") || route.startsWith("//") || route.includes("..")) {
      throw new Error(`${id}.route is unsafe`);
    }
    const pageNavigation = page.navigation === undefined
      ? {}
      : assertObject(page.navigation, `${id}.navigation`);
    const pageManifest = page.manifest === undefined
      ? {}
      : assertObject(page.manifest, `${id}.manifest`);
    const navigationKeys = new Set([
      "groupLabel",
      "groupOrder",
      "itemOrder",
      "label",
      "directory",
      "project",
      "icon",
      "role",
    ]);
    if (Object.keys(pageNavigation).some((key) => !navigationKeys.has(key))) {
      throw new Error(`${id}.navigation contains unsupported fields`);
    }
    if (pageNavigation.project !== undefined) {
      const pageProject = projectValue(
        pageNavigation.project,
        `${id}.navigation.project`,
      );
      if (pageProject.id !== suiteProject.id) {
        throw new Error(
          `${suiteId} cannot split pages across investment domains`,
        );
      }
    }
    if (pageNavigation.directory !== undefined) {
      const pageDirectory = assertObject(
        pageNavigation.directory,
        `${id}.navigation.directory`,
      );
      if (pageDirectory.id !== suiteDirectory.id) {
        throw new Error(`${suiteId} cannot split pages into another project group`);
      }
    }
    if (
      pageNavigation.groupLabel !== undefined &&
      pageNavigation.groupLabel !== sharedNavigation.groupLabel
    ) {
      throw new Error(`${suiteId} cannot split pages across navigation groups`);
    }
    if (
      pageNavigation.groupOrder !== undefined &&
      pageNavigation.groupOrder !== sharedNavigation.groupOrder
    ) {
      throw new Error(`${suiteId} cannot split pages across navigation groups`);
    }
    const manifestKeys = new Set([
      "schemaVersion",
      "category",
      "icon",
      "permissions",
      "dataServices",
      "storage",
      "wiki",
      "compatibility",
      "agentCapabilities",
      "actions",
      "events",
      "refresh",
    ]);
    if (Object.keys(pageManifest).some((key) => !manifestKeys.has(key))) {
      throw new Error(`${id}.manifest contains unsupported fields`);
    }
    if (
      page.defaultInstall !== undefined &&
      typeof page.defaultInstall !== "boolean"
    ) {
      throw new Error(`${id}.defaultInstall must be a boolean`);
    }
    const mergedNavigation = navigationValue(
      {
        ...sharedNavigation,
        groupLabel: sharedNavigation.groupLabel,
        groupOrder: nonNegativeInteger(
          sharedNavigation.groupOrder,
          `${id}.navigation.groupOrder`,
        ),
        itemOrder: nonNegativeInteger(
          pageNavigation.itemOrder,
          `${id}.navigation.itemOrder`,
          sharedNavigation.itemOrder,
        ),
        label: pageNavigation.label === undefined
          ? assertString(page.name, `${id}.name`)
          : assertString(pageNavigation.label, `${id}.navigation.label`),
        directory: sharedNavigation.directory,
        project: sharedNavigation.project,
        icon: pageNavigation.icon ?? sharedNavigation.icon,
        role: pageNavigation.role ?? sharedNavigation.role,
      },
      `${id}.navigation`,
    );
    const mergedManifest = {
      ...template,
      ...pageManifest,
      actions: {
        ...(template.actions || {}),
        ...(pageManifest.actions || {}),
      },
      navigation: mergedNavigation,
    };
    const mergedSchemaVersion = mergedManifest.schemaVersion || "1.0";
    if (mergedSchemaVersion === "1.1") {
      delete mergedManifest.agentCapabilities;
    } else {
      delete mergedManifest.compatibility;
      delete mergedManifest.actions;
    }
    return {
      defaultInstall: page.defaultInstall,
      descriptor: {
        schemaVersion: "1.0",
        id,
        name: assertString(page.name, `${id}.name`),
        description: assertString(page.description, `${id}.description`),
        version: page.version === undefined
          ? version
          : assertString(page.version, `${id}.version`),
        publisher: assertString(descriptor.publisher, `${suiteId}.publisher`),
        upstream: descriptor.upstream,
        tags: page.tags === undefined
          ? stringArray(descriptor.tags, `${suiteId}.tags`)
          : stringArray(page.tags, `${id}.tags`),
        runtime: {
          type: "external",
          baseUrlEnv,
          defaultBaseUrl,
          route,
        },
        manifest: mergedManifest,
      },
    };
  });
}

function manifestFromDescriptor(descriptor, env) {
  const id = assertString(descriptor.id, "descriptor.id");
  if (!MOD_ID_PATTERN.test(id)) throw new Error(`invalid Mod id: ${id}`);
  const version = assertString(descriptor.version, `${id}.version`);
  if (!VERSION_PATTERN.test(version)) throw new Error(`${id}.version is invalid`);
  const template = assertObject(descriptor.manifest, `${id}.manifest`);
  const schemaVersion = template.schemaVersion || "1.0";
  if (!["1.0", "1.1"].includes(schemaVersion)) {
    throw new Error(`${id}.manifest.schemaVersion is unsupported`);
  }
  const category = assertString(template.category, `${id}.manifest.category`);
  if (!CATEGORY_PATTERN.test(category)) throw new Error(`${id}.category is invalid`);
  const runtime = assertObject(descriptor.runtime, `${id}.runtime`);
  let entry;
  if (runtime.type === "external") {
    const envName = assertString(runtime.baseUrlEnv, `${id}.runtime.baseUrlEnv`);
    const baseUrl = exactHttpOrigin(
      configuredEnvValue(env, envName) ||
        assertString(runtime.defaultBaseUrl, `${id}.runtime.defaultBaseUrl`),
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

  const common = {
    schemaVersion,
    id,
    name: assertString(descriptor.name, `${id}.name`),
    version,
    category,
    presentation: {
      englishName: englishModName(id),
      description: boundedString(descriptor.description, `${id}.description`, 240),
      titleOwner: "host",
    },
    ...(template.navigation
      ? { navigation: navigationValue(template.navigation, `${id}.manifest.navigation`) }
      : {}),
    entry,
    permissions: stringArray(template.permissions, `${id}.manifest.permissions`),
    dataServices: stringArray(template.dataServices, `${id}.manifest.dataServices`),
    events: template.events || { emits: [], accepts: [] },
    ...(template.refresh ? { refresh: template.refresh } : {}),
  };
  if (schemaVersion === "1.0") {
    return {
      ...common,
      agentCapabilities: stringArray(
        template.agentCapabilities,
        `${id}.manifest.agentCapabilities`,
      ),
    };
  }
  return {
    ...common,
    compatibility: assertObject(
      template.compatibility,
      `${id}.manifest.compatibility`,
    ),
    actions: assertObject(template.actions || {}, `${id}.manifest.actions`),
    ...(template.storage
      ? { storage: assertObject(template.storage, `${id}.manifest.storage`) }
      : {}),
    ...(template.wiki
      ? { wiki: assertObject(template.wiki, `${id}.manifest.wiki`) }
      : {}),
  };
}

function validateCompleteProjectGroups(mods) {
  const groups = new Map();
  for (const mod of mods) {
    const navigation = mod.manifest.navigation;
    if (!navigation?.directory) continue;
    const members = groups.get(navigation.directory.id) ?? [];
    members.push({ id: mod.id, navigation });
    groups.set(navigation.directory.id, members);
  }
  for (const [directoryId, members] of groups) {
    const projectIds = new Set(members.map(({ navigation }) => navigation.project?.id));
    const groupLabels = new Set(members.map(({ navigation }) => navigation.groupLabel));
    const groupOrders = new Set(members.map(({ navigation }) => navigation.groupOrder));
    const directoryLabels = new Set(
      members.map(({ navigation }) => navigation.directory.label),
    );
    if (
      projectIds.size !== 1 ||
      projectIds.has(undefined) ||
      groupLabels.size !== 1 ||
      groupOrders.size !== 1 ||
      directoryLabels.size !== 1
    ) {
      throw new Error(
        `${directoryId} is one complete project and cannot be split across Desk columns`,
      );
    }
  }
}

export async function loadModStore({
  env = process.env,
  storeUrl = DEFAULT_STORE_URL,
  fetchImpl = fetch,
  discoveryTimeoutMs = DEFAULT_DISCOVERY_TIMEOUT_MS,
} = {}) {
  const rawStore = JSON.parse(await readFile(storeUrl, "utf8"));
  const store = assertObject(rawStore, storeUrl.pathname);
  if (store.schemaVersion !== "1.0") throw new Error("unsupported Mod store schema");
  const entries = store.mods === undefined ? [] : store.mods;
  const suiteEntries = store.suites === undefined ? [] : store.suites;
  if (!Array.isArray(entries) || !Array.isArray(suiteEntries)) {
    throw new Error("Mod store entries must be arrays");
  }
  if (entries.length === 0 && suiteEntries.length === 0) {
    throw new Error("Mod store must contain at least one Mod or Mod Suite");
  }
  const standaloneMods = await Promise.all(entries.map(async (rawEntry) => {
    const entry = assertObject(rawEntry, "store.mods[]");
    const id = assertString(entry.id, "store.mods[].id");
    const path = safeStorePath(entry.path, `${id}.path`, "/mod.json");
    const descriptorUrl = new URL(path, storeUrl);
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
  const suites = await Promise.all(suiteEntries.map(async (rawEntry) => {
    const entry = assertObject(rawEntry, "store.suites[]");
    const id = assertString(entry.id, "store.suites[].id");
    if (!SUITE_ID_PATTERN.test(id)) throw new Error(`invalid Mod Suite id: ${id}`);
    const hasPath = entry.path !== undefined;
    const hasDiscovery = entry.discovery !== undefined;
    if (hasPath === hasDiscovery) {
      throw new Error(`${id} must declare exactly one Suite Discovery source`);
    }
    let path;
    let discovery;
    let descriptor;
    let discoveryUrl;
    if (hasPath) {
      path = safeStorePath(entry.path, `${id}.path`, "/suite.json");
      const descriptorUrl = new URL(path, storeUrl);
      descriptor = assertObject(
        JSON.parse(await readFile(descriptorUrl, "utf8")),
        descriptorUrl.pathname,
      );
    } else {
      discovery = suiteDiscoveryValue(entry.discovery, `${id}.discovery`);
      const discovered = await fetchSuiteDescriptor({
        discovery,
        env,
        fetchImpl,
        timeoutMs: discoveryTimeoutMs,
        label: id,
      });
      descriptor = discovered.descriptor;
      discoveryUrl = discovered.url;
    }
    if (descriptor.id !== id) throw new Error(`${id} descriptor id mismatch`);
    const pages = suitePageDescriptors(descriptor).map((page) => ({
      id: page.descriptor.id,
      ...(path ? { path } : {}),
      ...(discoveryUrl ? { discoveryUrl } : {}),
      defaultInstall: entry.defaultInstall === false
        ? false
        : page.defaultInstall === undefined
          ? entry.defaultInstall === true
          : page.defaultInstall === true,
      descriptor: page.descriptor,
      manifest: manifestFromDescriptor(page.descriptor, env),
      suiteId: id,
    }));
    return {
      id,
      ...(path ? { path } : {}),
      ...(discovery ? { discovery, discoveryUrl } : {}),
      descriptor,
      pages,
    };
  }));
  const mods = [
    ...standaloneMods,
    ...suites.flatMap((suite) => suite.pages),
  ];
  validateCompleteProjectGroups(mods);
  const ids = mods.map((mod) => mod.id);
  if (new Set(ids).size !== ids.length) throw new Error("Mod store contains duplicate ids");
  const retiredMods = stringArray(store.retiredMods, "store.retiredMods");
  if (
    retiredMods.some((id) => !MOD_ID_PATTERN.test(id)) ||
    new Set(retiredMods).size !== retiredMods.length
  ) {
    throw new Error("store.retiredMods contains invalid or duplicate Mod ids");
  }
  if (retiredMods.some((id) => ids.includes(id))) {
    throw new Error("retired Mods cannot remain in store.mods");
  }
  return {
    id: assertString(store.id, "store.id"),
    name: assertString(store.name, "store.name"),
    git: assertObject(store.git, "store.git"),
    mods,
    suites,
    retiredMods,
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

async function registerSelectedStoreMods({
  apiUrl = "http://127.0.0.1:8911",
  env = process.env,
  fetchImpl = fetch,
  dryRun = false,
} = {}, shouldRegister) {
  const controlPlaneOrigin = exactHttpOrigin(apiUrl, "Newma-Desk API URL");
  const store = await loadModStore({ env });
  const desired = store.mods
    .filter(shouldRegister)
    .map((mod) => mod.manifest);
  if (dryRun) {
    return { created: desired, skipped: [], disabled: [], store };
  }

  const current = await requestJson(fetchImpl, `${controlPlaneOrigin}/api/mods`);
  if (!Array.isArray(current)) throw new Error("Newma-Desk Mod registry returned malformed data");
  const publishedById = new Map(current.map((item) => [item.moduleId, item]));
  const created = [];
  const skipped = [];
  const disabled = [];
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
      throw new Error(`Newma-Desk returned an invalid draft for ${manifest.id}`);
    }
    await requestJson(
      fetchImpl,
      `${controlPlaneOrigin}/api/mods/${encodeURIComponent(manifest.id)}/revisions/${draft.revision}/publish`,
      { method: "POST" },
    );
    created.push(manifest);
  }
  for (const moduleId of store.retiredMods) {
    const existing = publishedById.get(moduleId);
    if (!existing) continue;
    await requestJson(
      fetchImpl,
      `${controlPlaneOrigin}/api/mods/${encodeURIComponent(moduleId)}/disable`,
      { method: "POST" },
    );
    disabled.push(existing);
  }
  return { created, skipped, disabled, store };
}

export async function registerStoreMods(options = {}) {
  return registerSelectedStoreMods(options, () => true);
}

export async function registerDefaultMods(options = {}) {
  return registerSelectedStoreMods(
    options,
    (mod) => mod.defaultInstall === true,
  );
}

export async function standardizeStoreMods({
  apiUrl = "http://127.0.0.1:8911",
  env = process.env,
  fetchImpl = fetch,
  dryRun = false,
} = {}) {
  const registration = await registerStoreMods({
    apiUrl,
    env,
    fetchImpl,
    dryRun,
  });
  return registration;
}

// Compatibility alias for local scripts created before the full-store sidebar policy.
export const standardizeDefaultMods = standardizeStoreMods;
