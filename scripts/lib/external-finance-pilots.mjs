import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const DEFAULT_DESCRIPTOR_URL = new URL(
  "../../config/external-finance-mod-pilots.json",
  import.meta.url,
);
const ID_PATTERN = /^[a-z][a-z0-9-]{2,63}$/;
const ENV_PATTERN = /^(?:NEWMA_DESK|NEWMA_DOCK)_[A-Z0-9_]+$/;
const CAPABILITY_PATTERN = /^[a-z][a-z0-9-]*(?:\.[a-z][a-z0-9-]*)+$/;
const SECRET_ENV_PATTERN = /(API_KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|BROKER|FUTU|LONGBRIDGE|ALPACA|IBKR|BINANCE|OKX|BITGET|GATE)/;
const MODES = new Set(["analysis-only", "paper-only"]);
const COMMON_DENIED_CAPABILITIES = new Set([
  "trade.execute",
  "trade.order.submit",
  "agent.invoke",
  "model.invoke",
  "notification.send",
  "credentials.read",
]);
const COMMON_GATES = new Set([
  "dependency-audit",
  "static-secret-scan",
  "capability-contract",
  "no-port-conflict",
  "desk-agent-context",
  "responsive-embed",
]);

function objectValue(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value
    : undefined;
}

function safeRelativePath(value) {
  return (
    typeof value === "string" &&
    value.length > 0 &&
    !value.startsWith("/") &&
    !value.includes("\\") &&
    value.split("/").every((part) => part && part !== "." && part !== "..")
  );
}

function exactLocalOrigin(value) {
  try {
    const parsed = new URL(value);
    return (
      parsed.protocol === "http:" &&
      parsed.hostname === "127.0.0.1" &&
      parsed.origin === value &&
      Number.isInteger(Number(parsed.port))
    )
      ? parsed
      : null;
  } catch {
    return null;
  }
}

function stringList(value, label, errors) {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string" || !item)) {
    errors.push(`${label} must be a non-empty string array`);
    return [];
  }
  return value;
}

function checkPilot(pilot, index, reservedPorts, occupiedPorts) {
  const errors = [];
  const warnings = [];
  const label = `pilots[${index}]`;
  const value = objectValue(pilot);
  if (!value) return { id: `pilot-${index}`, errors: [`${label} must be an object`], warnings };
  const id = typeof value.id === "string" ? value.id : `pilot-${index}`;
  if (!ID_PATTERN.test(id)) errors.push(`${label}.id must be a stable kebab-case ID`);
  if (!MODES.has(value.mode)) errors.push(`${id}.mode must be analysis-only or paper-only`);
  if (!/^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(value.upstream ?? "")) {
    errors.push(`${id}.upstream must be an exact GitHub repository URL`);
  }
  if (!/^[0-9a-f]{40}$/.test(value.audit?.revision ?? "")) {
    errors.push(`${id}.audit.revision must pin a full Git commit`);
  }

  const activation = objectValue(value.activation);
  if (!activation || activation.defaultEnabled !== false) {
    errors.push(`${id} must remain default-disabled`);
  }
  if (!ENV_PATTERN.test(activation?.env ?? "")) {
    errors.push(`${id}.activation.env must be a NEWMA_DESK_* variable`);
  }

  const workspace = objectValue(value.workspace);
  if (!ENV_PATTERN.test(workspace?.env ?? "")) {
    errors.push(`${id}.workspace.env must be a NEWMA_DESK_* variable`);
  }
  const candidates = stringList(workspace?.candidates, `${id}.workspace.candidates`, errors);
  if (candidates.some((candidate) => !safeRelativePath(candidate))) {
    errors.push(`${id}.workspace.candidates must contain safe relative paths`);
  }

  const runtime = objectValue(value.runtime);
  const origin = exactLocalOrigin(runtime?.origin);
  if (!origin) {
    errors.push(`${id}.runtime.origin must be an exact 127.0.0.1 HTTP origin with a port`);
  } else {
    const port = Number(origin.port);
    if (reservedPorts.has(port)) errors.push(`${id}.runtime.origin uses reserved port ${port}`);
    if (occupiedPorts.has(port)) errors.push(`${id}.runtime.origin duplicates pilot port ${port}`);
    occupiedPorts.add(port);
    if ((runtime.upstreamDefaultPorts ?? []).includes(port)) {
      errors.push(`${id}.runtime.origin must not reuse an upstream default port`);
    }
  }
  if (
    typeof runtime?.healthPath !== "string" ||
    !runtime.healthPath.startsWith("/") ||
    runtime.healthPath.startsWith("//") ||
    runtime.healthPath.includes("..")
  ) {
    errors.push(`${id}.runtime.healthPath must be a safe absolute path`);
  }

  const isolation = objectValue(value.isolation);
  if (
    (isolation?.deskDataOnly ?? isolation?.dockDataOnly) !== true ||
    isolation?.directInternet !== false
  ) {
    errors.push(`${id} must use Desk data only and deny direct Internet access`);
  }
  if (!safeRelativePath(isolation?.dataDir)) {
    errors.push(`${id}.isolation.dataDir must be a safe relative path`);
  }
  const allowedEnv = stringList(
    isolation?.environmentAllowlist,
    `${id}.isolation.environmentAllowlist`,
    errors,
  );
  for (const name of allowedEnv) {
    if (!/^[A-Z][A-Z0-9_]*$/.test(name)) errors.push(`${id} allows invalid environment name ${name}`);
    if (SECRET_ENV_PATTERN.test(name)) errors.push(`${id} must not allow credential environment ${name}`);
  }
  stringList(
    isolation?.environmentDenyPatterns,
    `${id}.isolation.environmentDenyPatterns`,
    errors,
  );

  const capabilities = objectValue(value.capabilities);
  const allowedCapabilities = stringList(capabilities?.allow, `${id}.capabilities.allow`, errors);
  const deniedCapabilities = stringList(capabilities?.deny, `${id}.capabilities.deny`, errors);
  for (const capability of [...allowedCapabilities, ...deniedCapabilities]) {
    if (!CAPABILITY_PATTERN.test(capability)) errors.push(`${id} has invalid capability ${capability}`);
  }
  const denied = new Set(deniedCapabilities);
  const allowed = new Set(allowedCapabilities);
  for (const capability of COMMON_DENIED_CAPABILITIES) {
    if (!denied.has(capability)) errors.push(`${id} must deny ${capability}`);
  }
  for (const capability of allowed) {
    if (denied.has(capability)) errors.push(`${id} both allows and denies ${capability}`);
    if (/^(trade|agent|model|mcp|broker|credentials)\./.test(capability)) {
      errors.push(`${id} cannot allow privileged capability ${capability}`);
    }
  }
  if (value.mode === "analysis-only") {
    for (const capability of ["backtest.execute", "portfolio.import-broker"]) {
      if (!denied.has(capability)) errors.push(`${id} analysis-only mode must deny ${capability}`);
    }
  }
  if (value.mode === "paper-only") {
    for (const capability of ["trade.live.enable", "broker.connect", "mcp.invoke", "strategy.code.execute"]) {
      if (!denied.has(capability)) errors.push(`${id} paper-only mode must deny ${capability}`);
    }
  }

  const gates = new Set(stringList(value.acceptanceGates, `${id}.acceptanceGates`, errors));
  if (gates.has("dock-agent-context")) gates.add("desk-agent-context");
  for (const gate of COMMON_GATES) {
    if (!gates.has(gate)) errors.push(`${id} is missing acceptance gate ${gate}`);
  }
  if (value.mode === "analysis-only" && !gates.has("no-broker-import")) {
    errors.push(`${id} analysis-only mode requires no-broker-import`);
  }
  if (value.mode === "paper-only") {
    for (const gate of ["paper-only-proof", "credential-isolation"]) {
      if (!gates.has(gate)) errors.push(`${id} paper-only mode requires ${gate}`);
    }
  }
  const auditStatus = value.audit?.dependencyAudit ?? "missing";
  const decision = auditStatus === "no-known-vulnerabilities" ? "go" : "no-go";
  if (decision === "no-go") {
    warnings.push(`${id} dependency audit is not yet clean: ${auditStatus}`);
  }
  return { id, mode: value.mode, auditStatus, decision, errors, warnings };
}

export function checkExternalFinancePilotDescriptor(descriptor) {
  const errors = [];
  const warnings = [];
  const value = objectValue(descriptor);
  if (!value || value.schemaVersion !== "1.0") {
    return { ok: false, pilots: [], errors: ["unsupported external finance pilot descriptor"], warnings };
  }
  const reservedPorts = new Set(
    Array.isArray(value.reservedPorts) && value.reservedPorts.every(Number.isInteger)
      ? value.reservedPorts
      : [],
  );
  if (reservedPorts.size === 0) errors.push("reservedPorts must contain integer ports");
  if (!Array.isArray(value.pilots) || value.pilots.length === 0) {
    errors.push("pilots must be a non-empty array");
    return { ok: false, pilots: [], errors, warnings };
  }
  const occupiedPorts = new Set();
  const pilots = value.pilots.map((pilot, index) =>
    checkPilot(pilot, index, reservedPorts, occupiedPorts),
  );
  const ids = pilots.map(({ id }) => id);
  if (new Set(ids).size !== ids.length) errors.push("pilot IDs must be unique");
  for (const pilot of pilots) {
    errors.push(...pilot.errors.map((error) => `${pilot.id}: ${error}`));
    warnings.push(...pilot.warnings);
  }
  return { ok: errors.length === 0, pilots, errors, warnings };
}

export async function loadExternalFinancePilotDescriptor(
  descriptorUrl = DEFAULT_DESCRIPTOR_URL,
) {
  return JSON.parse(await readFile(descriptorUrl, "utf8"));
}

export async function checkConfiguredExternalFinancePilots(
  descriptorUrl = DEFAULT_DESCRIPTOR_URL,
) {
  return checkExternalFinancePilotDescriptor(
    await loadExternalFinancePilotDescriptor(descriptorUrl),
  );
}

export const externalFinancePilotDescriptorPath = fileURLToPath(DEFAULT_DESCRIPTOR_URL);
