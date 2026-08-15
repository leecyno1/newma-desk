import { readFile } from "node:fs/promises";
import { pathToFileURL } from "node:url";

import { loadModStore } from "./lib/mod-store.mjs";

const MOD_ID = /^[a-z][a-z0-9-]{2,63}$/;
const CAPABILITY_ID = /^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+$/;
const SERVICE_ID = /^[a-z][a-z0-9-]{2,63}$/;

function objectValue(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value
    : undefined;
}

function stringArray(value) {
  return Array.isArray(value) && value.every((item) => typeof item === "string")
    ? value
    : undefined;
}

function validEntry(entry) {
  const value = objectValue(entry);
  if (!value || typeof value.type !== "string" || typeof value.url !== "string") {
    return false;
  }
  if (value.type === "external") {
    try {
      return ["http:", "https:"].includes(new URL(value.url).protocol);
    } catch {
      return false;
    }
  }
  return (
    ["structured", "static"].includes(value.type) &&
    value.url.startsWith("/") &&
    !value.url.startsWith("//") &&
    !value.url.includes("..") &&
    !value.url.includes("\\")
  );
}

function compatibilityResult({ id, level, errors, warnings, badges }) {
  return {
    id,
    level,
    declaredLevel: level,
    certifiedLevel: null,
    contractStatus: errors.length === 0 ? "passed" : "failed",
    certificationStatus:
      errors.length > 0 ? "blocked" : level === 0 ? "not-applicable" : "pending",
    errors,
    warnings,
    badges,
  };
}

export function checkModManifest(manifest) {
  const value = objectValue(manifest);
  const errors = [];
  const warnings = [];
  const badges = new Set();
  if (!value) {
    return compatibilityResult({
      id: "unknown",
      level: null,
      errors: ["Manifest must be an object"],
      warnings,
      badges: [],
    });
  }
  const id = typeof value.id === "string" ? value.id : "unknown";
  if (!MOD_ID.test(id)) errors.push("id must be a valid Mod ID");
  if (typeof value.name !== "string" || !value.name.trim()) {
    errors.push("name is required");
  }
  if (!/^\d+\.\d+\.\d+$/.test(String(value.version ?? ""))) {
    errors.push("version must use semantic x.y.z format");
  }
  if (!validEntry(value.entry)) errors.push("entry must be a safe HTTP(S) or local URL");

  const permissions = stringArray(value.permissions);
  const dataServices = stringArray(value.dataServices);
  if (!permissions) errors.push("permissions must be an array of strings");
  if (!dataServices) errors.push("dataServices must be an array of strings");

  if (value.schemaVersion === "1.0") {
    if (
      value.compatibility !== undefined
      || value.storage !== undefined
      || value.wiki !== undefined
      || value.actions !== undefined
    ) {
      errors.push("Manifest 1.0 cannot declare 1.1 fields");
    }
    const agents = stringArray(value.agentCapabilities) ?? [];
    if (agents.length > 0) badges.add("Agent");
    if ((dataServices ?? []).length > 0) badges.add("Data");
    if (objectValue(value.refresh)?.mode === "schedule") badges.add("Scheduled");
    warnings.push(
      "Manifest 1.0 is supported in legacy mode but cannot receive a Level 1-3 certification",
    );
    return compatibilityResult({
      id,
      level: 0,
      errors,
      warnings,
      badges: [...badges].sort(),
    });
  }

  if (value.schemaVersion !== "1.1") {
    errors.push("schemaVersion must be 1.0 or 1.1");
    return compatibilityResult({ id, level: null, errors, warnings, badges: [] });
  }

  const compatibility = objectValue(value.compatibility);
  const level = compatibility?.level;
  if (![1, 2, 3].includes(level)) {
    errors.push("compatibility.level must be 1, 2, or 3");
  }
  if (compatibility?.bridgeProtocol !== "1.0") {
    errors.push("compatibility.bridgeProtocol must be 1.0");
  }
  if (level === 3 && compatibility?.viewSpecVersion !== "1.0") {
    errors.push("Level 3 Mods must declare viewSpecVersion 1.0");
  }

  const actions = objectValue(value.actions);
  let allSchemasInline = true;
  if (!actions) {
    errors.push("actions must be an object");
  } else {
    if (level === 1 && Object.keys(actions).length > 0) {
      errors.push("Level 1 Mods cannot declare connected actions");
    }
    const declaredPermissions = new Set(permissions ?? []);
    const declaredServices = new Set(dataServices ?? []);
    for (const [actionId, rawAction] of Object.entries(actions)) {
      const action = objectValue(rawAction);
      const binding = objectValue(action?.binding);
      if (!CAPABILITY_ID.test(actionId)) {
        errors.push(`${actionId}: invalid action ID`);
      }
      if (!action || !binding) {
        errors.push(`${actionId}: action and binding must be objects`);
        continue;
      }
      if (
        (typeof action.inputSchema !== "string" && !objectValue(action.inputSchema)) ||
        (typeof action.outputSchema !== "string" && !objectValue(action.outputSchema))
      ) {
        errors.push(`${actionId}: inputSchema and outputSchema are required`);
      }
      if (!objectValue(action.inputSchema) || !objectValue(action.outputSchema)) {
        allSchemasInline = false;
      }
      if (!declaredPermissions.has(action.permission)) {
        errors.push(`${actionId}: permission is not declared by the Mod`);
      }
      const confirmation = action.confirmation ?? "none";
      if (!["none", "user", "strong"].includes(confirmation)) {
        errors.push(`${actionId}: confirmation must be none, user, or strong`);
      }
      if (binding.type === "agent") {
        badges.add("Agent");
        if (!["user-agent-mod", "task"].includes(binding.memoryScope)) {
          errors.push(`${actionId}: invalid Agent memoryScope`);
        }
        if (action.execution !== "task") {
          errors.push(`${actionId}: Agent actions must use task execution`);
        }
      } else if (binding.type === "model") {
        badges.add("Model");
        if (action.execution !== "request") {
          errors.push(`${actionId}: Model actions must use request execution`);
        }
      } else if (binding.type === "data") {
        badges.add("Data");
        if (
          binding.service !== undefined &&
          !SERVICE_ID.test(String(binding.service))
        ) {
          errors.push(`${actionId}: invalid data service ID`);
        } else if (
          binding.service !== undefined &&
          !declaredServices.has(binding.service)
        ) {
          errors.push(`${actionId}: data service is not declared by the Mod`);
        }
      } else if (binding.type !== "local") {
        errors.push(`${actionId}: unsupported binding type`);
      }
      if (actionId === "trade.execute" && confirmation !== "strong") {
        errors.push("trade.execute: strong confirmation is required");
      }
    }
  }
  if (actions && Object.keys(actions).length > 0 && allSchemasInline) {
    badges.add("Schema");
  }
  if (level === 3) badges.add("ViewSpec");
  if (objectValue(value.refresh)?.mode === "schedule") badges.add("Scheduled");
  if (errors.length === 0) {
    warnings.push(
      "Declared compatibility is not certified until runtime embedding, health, handshake, responsive layout, and required Agent Context checks pass",
    );
  }
  return compatibilityResult({
    id,
    level: [1, 2, 3].includes(level) ? level : null,
    errors,
    warnings,
    badges: [...badges].sort(),
  });
}

async function manifestsFromArguments(paths) {
  if (paths.length === 0) {
    const store = await loadModStore();
    return store.mods.map((mod) => mod.manifest);
  }
  return Promise.all(
    paths.map(async (path) => JSON.parse(await readFile(path, "utf8"))),
  );
}

export async function runCompatibilityCheck(paths = []) {
  const manifests = await manifestsFromArguments(paths);
  return manifests.map(checkModManifest);
}

async function main() {
  const results = await runCompatibilityCheck(process.argv.slice(2));
  for (const result of results) {
    const declared =
      result.level === 0
        ? "legacy"
        : result.level === null
          ? "invalid"
          : `level-${result.level}`;
    const status = result.contractStatus === "passed" ? "PASS" : "FAIL";
    process.stdout.write(
      `CONTRACT ${status} ${result.id} declared=${declared} certification=${result.certificationStatus}` +
        (result.badges.length ? ` badges=${result.badges.join(",")}` : "") +
        "\n",
    );
    for (const warning of result.warnings) {
      process.stdout.write(`  WARN ${warning}\n`);
    }
    for (const error of result.errors) process.stdout.write(`  ERROR ${error}\n`);
  }
  if (results.some((result) => result.errors.length > 0)) process.exitCode = 1;
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  await main();
}
