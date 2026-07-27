export const RUNTIME_CHECK = Object.freeze({
  HEALTH: "health",
  EMBED: "embed",
  BRIDGE: "bridge",
  RESPONSIVE: "responsive",
  AGENT_CONTEXT: "agentContext",
});

export function requiredRuntimeChecks(declaredLevel) {
  if (![1, 2, 3].includes(declaredLevel)) return [];
  const checks = [
    RUNTIME_CHECK.HEALTH,
    RUNTIME_CHECK.EMBED,
    RUNTIME_CHECK.BRIDGE,
    RUNTIME_CHECK.RESPONSIVE,
  ];
  if (declaredLevel === 3) checks.push(RUNTIME_CHECK.AGENT_CONTEXT);
  return checks;
}

export function createRuntimeCertification({
  id,
  declaredLevel,
  checks,
  testedAt = new Date().toISOString(),
  shellOrigin,
}) {
  const required = requiredRuntimeChecks(declaredLevel);
  const failedChecks = required.filter((name) => checks[name]?.status !== "passed");
  const status = required.length > 0 && failedChecks.length === 0
    ? "certified"
    : "failed";
  return {
    id,
    declaredLevel,
    certifiedLevel: status === "certified" ? declaredLevel : null,
    status,
    testedAt,
    shellOrigin,
    requiredChecks: required,
    failedChecks,
    checks,
  };
}

export function summarizeRuntimeCertifications(results) {
  return {
    total: results.length,
    certified: results.filter((result) => result.status === "certified").length,
    failed: results.filter((result) => result.status === "failed").length,
    byDeclaredLevel: Object.fromEntries(
      [1, 2, 3].map((level) => [
        String(level),
        {
          total: results.filter((result) => result.declaredLevel === level).length,
          certified: results.filter(
            (result) => result.declaredLevel === level && result.status === "certified",
          ).length,
        },
      ]),
    ),
  };
}
