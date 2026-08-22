import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = fileURLToPath(new URL("../../", import.meta.url));
const defaultRegistryPath = path.join(repoRoot, "config", "finance-project-intake.json");

export const INVESTMENT_COLUMN_IDS = new Set([
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
  "other",
]);

const MODES = new Set([
  "complete-suite",
  "data-provider",
  "agent-capability",
  "reference-only",
  "reject",
]);
const ACTIVE_MODES = new Set(["complete-suite", "data-provider", "agent-capability"]);
const SHA_PATTERN = /^[0-9a-f]{40}$/u;
const ID_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/u;
const GITHUB_PATTERN = /^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/u;

function isObject(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasStrings(value) {
  return Array.isArray(value) && value.length > 0 && value.every((entry) => (
    typeof entry === "string" && entry.trim().length > 0
  ));
}

function duplicateValues(values) {
  const seen = new Set();
  const duplicates = new Set();
  for (const value of values) {
    if (seen.has(value)) duplicates.add(value);
    seen.add(value);
  }
  return [...duplicates];
}

export async function loadFinanceProjectIntake(registryPath = defaultRegistryPath) {
  return JSON.parse(await readFile(registryPath, "utf8"));
}

export function validateFinanceProjectIntake(registry) {
  const errors = [];
  const warnings = [];
  const projects = Array.isArray(registry?.projects) ? registry.projects : [];

  if (registry?.schemaVersion !== "1.0") {
    errors.push("registry must use schemaVersion 1.0");
  }
  if (!isObject(registry?.policy) || !hasStrings(registry.policy.modes)) {
    errors.push("registry policy must declare supported modes");
  } else {
    const unknownPolicyModes = registry.policy.modes.filter((mode) => !MODES.has(mode));
    if (unknownPolicyModes.length > 0) {
      errors.push(`registry policy has unknown modes: ${unknownPolicyModes.join(", ")}`);
    }
  }
  if (projects.length === 0) errors.push("registry must contain at least one project");

  for (const duplicate of duplicateValues(projects.map((project) => project?.id))) {
    errors.push(`duplicate project id: ${duplicate}`);
  }
  for (const duplicate of duplicateValues(projects.map((project) => project?.source))) {
    errors.push(`source repository appears more than once: ${duplicate}`);
  }
  for (const duplicate of duplicateValues(
    projects.filter((project) => project?.suiteId).map((project) => project.suiteId),
  )) {
    errors.push(`suite id appears more than once: ${duplicate}`);
  }

  for (const [index, project] of projects.entries()) {
    const label = project?.id || `projects[${index}]`;
    if (!isObject(project)) {
      errors.push(`${label}: project entry must be an object`);
      continue;
    }
    if (!ID_PATTERN.test(project.id ?? "")) errors.push(`${label}: invalid stable id`);
    if (typeof project.name !== "string" || project.name.trim().length === 0) errors.push(`${label}: name is required`);
    if (!GITHUB_PATTERN.test(project.source ?? "")) errors.push(`${label}: source must be an exact GitHub repository URL`);
    if (!SHA_PATTERN.test(project.revision ?? "")) errors.push(`${label}: revision must be a pinned 40-character commit SHA`);
    if (!MODES.has(project.mode)) errors.push(`${label}: unsupported mode ${project.mode}`);
    if (!INVESTMENT_COLUMN_IDS.has(project.primaryColumn)) {
      errors.push(`${label}: invalid primaryColumn ${project.primaryColumn}`);
    }
    if (!isObject(project.snapshot)) {
      errors.push(`${label}: snapshot is required`);
    } else {
      if (!Number.isInteger(project.snapshot.score) || project.snapshot.score < 0 || project.snapshot.score > 100) {
        errors.push(`${label}: snapshot.score must be an integer from 0 to 100`);
      }
      if (!Number.isInteger(project.snapshot.stars) || project.snapshot.stars < 0) {
        errors.push(`${label}: snapshot.stars must be a non-negative integer`);
      }
      if (typeof project.snapshot.license !== "string" || project.snapshot.license.length === 0) {
        errors.push(`${label}: snapshot.license is required`);
      }
    }
    if (!Number.isInteger(project.rolloutPhase) || project.rolloutPhase < 0) {
      errors.push(`${label}: rolloutPhase must be a non-negative integer`);
    }
    if (!Array.isArray(project.dependencies) || !project.dependencies.every((entry) => typeof entry === "string") || !isObject(project.access)) {
      errors.push(`${label}: dependencies and access metadata are required`);
    } else if (typeof project.access.mode !== "string" || !Array.isArray(project.access.optionalSecrets)) {
      errors.push(`${label}: access mode and optionalSecrets are required`);
    }
    if (typeof project.status !== "string" || project.status.length === 0) errors.push(`${label}: status is required`);
    if (typeof project.notes !== "string" || project.notes.length === 0) errors.push(`${label}: notes are required`);
    if (!Array.isArray(project.consumers)) {
      errors.push(`${label}: consumers must be an array`);
    } else {
      for (const consumer of project.consumers) {
        if (!INVESTMENT_COLUMN_IDS.has(consumer)) {
          errors.push(`${label}: invalid consumer column ${consumer}`);
        }
      }
    }

    if (project.mode === "complete-suite") {
      if (!ID_PATTERN.test(project.suiteId ?? "")) errors.push(`${label}: complete-suite requires a stable suiteId`);
      if (project.preserveWholeProject !== true) errors.push(`${label}: complete-suite must preserveWholeProject`);
      if (project.defaultEnabled !== false) errors.push(`${label}: external complete-suite must default to disabled`);
      if (!hasStrings(project.acceptanceGates)) errors.push(`${label}: complete-suite requires acceptanceGates`);
      if (project.consumers?.length !== 1 || project.consumers[0] !== project.primaryColumn) {
        errors.push(`${label}: complete-suite consumers must contain only its primaryColumn`);
      }
    } else {
      if (project.suiteId !== undefined) errors.push(`${label}: ${project.mode} cannot declare suiteId`);
      if (project.preserveWholeProject !== undefined) errors.push(`${label}: ${project.mode} cannot declare preserveWholeProject`);
      if (project.pages !== undefined) errors.push(`${label}: ${project.mode} cannot declare independent Mod pages`);
    }

    if (project.mode === "data-provider" && !hasStrings(project.capabilities)) {
      errors.push(`${label}: data-provider requires capabilities`);
    }
    if (project.mode === "agent-capability" && !hasStrings(project.capabilities)) {
      errors.push(`${label}: agent-capability requires capabilities`);
    }
    if (project.mode === "agent-capability" && project.presentation !== "agent-only") {
      errors.push(`${label}: agent-capability presentation must be agent-only`);
    }
    if (project.mode !== "agent-capability" && project.presentation !== undefined) {
      errors.push(`${label}: only agent-capability can declare presentation`);
    }
    if ((project.mode === "reference-only" || project.mode === "reject")
      && typeof project.reconsiderationGate !== "string") {
      errors.push(`${label}: ${project.mode} requires a reconsiderationGate`);
    }
    if (project.mode === "reject" && project.consumers?.length !== 0) {
      errors.push(`${label}: rejected sources cannot have consumers`);
    }
    if (ACTIVE_MODES.has(project.mode)
      && project.snapshot?.score < registry.policy?.minimumScoreForAdoption) {
      errors.push(`${label}: active intake score is below the adoption threshold`);
    }
  }

  return { ok: errors.length === 0, errors, warnings, projectCount: projects.length };
}

export async function checkFinanceProjectIntake(registryPath = defaultRegistryPath) {
  const registry = await loadFinanceProjectIntake(registryPath);
  return { registry, ...validateFinanceProjectIntake(registry) };
}
