const PROFILE_NAMES = ["core", "local", "all"];

const PROFILE_DEFINITIONS = {
  core: {
    preCore: ["worldIntel"],
    optional: [],
    externalRuntimeIds: ["world-intel"],
  },
  local: {
    preCore: ["worldIntel", "crucix", "policyCollector"],
    optional: ["instock", "fundAnalysis", "orchestra"],
    externalRuntimeIds: [
      "world-intel",
      "crucix",
      "instock",
      "fund-analysis",
      "orchestra",
    ],
  },
  all: {
    preCore: ["worldIntel", "crucix", "policyCollector"],
    optional: [
      "openChatCut",
      "instock",
      "fundAnalysis",
      "orchestra",
      "sevenCycle",
      "deepsee",
    ],
    externalRuntimeIds: [
      "world-intel",
      "crucix",
      "openchatcut",
      "instock",
      "fund-analysis",
      "orchestra",
      "seven-cycle",
      "deepsee",
    ],
  },
};

function profileValue(value) {
  const profile = String(value || "").trim().toLowerCase();
  if (!PROFILE_NAMES.includes(profile)) {
    throw new Error(`未知 Runtime Profile：${value || "-"}；可选 core, local, all。`);
  }
  return profile;
}

export function resolveRuntimeProfile(argv = [], env = process.env) {
  if (argv.includes("--core")) return "core";

  const inline = argv.find((argument) => argument.startsWith("--profile="));
  if (inline) return profileValue(inline.slice("--profile=".length));

  const profileIndex = argv.indexOf("--profile");
  if (profileIndex >= 0) {
    const value = argv[profileIndex + 1];
    if (!value || value.startsWith("--")) {
      throw new Error("--profile 缺少 Profile 名称；可选 core, local, all。");
    }
    return profileValue(value);
  }

  const configured = [
    env.NEWMA_DESK_RUNTIME_PROFILE,
    env.NEWMA_DOCK_RUNTIME_PROFILE,
    env.VIBEDESK_RUNTIME_PROFILE,
  ].find((value) => String(value || "").trim());
  return configured ? profileValue(configured) : "all";
}

function servicesFor(groupNames, serviceGroups) {
  return groupNames.flatMap((name) => serviceGroups[name] || []);
}

export function createRuntimeProfilePlan(
  profile,
  serviceGroups,
  profileDefinitions = PROFILE_DEFINITIONS,
) {
  const selectedProfile = profileValue(profile);
  const definition = profileDefinitions[selectedProfile];
  if (!definition) throw new Error(`Runtime Profile 缺少定义：${selectedProfile}`);
  const preCoreServices = servicesFor(definition.preCore, serviceGroups);
  const coreServices = servicesFor(["core"], serviceGroups);
  const optionalServices = servicesFor(definition.optional, serviceGroups);
  return {
    profile: selectedProfile,
    preCoreServices,
    coreServices,
    optionalServices,
    allServices: [
      ...preCoreServices,
      ...coreServices,
      ...optionalServices,
    ],
    externalRuntimeIds: [
      ...(definition.externalRuntimeIds || [
        ...new Set([...definition.preCore, ...definition.optional]),
      ]),
    ],
  };
}
