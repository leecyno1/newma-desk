import { readFile, readdir } from "node:fs/promises";

const DEFAULT_DATA_SERVICES_ROOT = new URL("../../integrations/", import.meta.url);

function objectValue(value) {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value
    : undefined;
}

export function selectReleaseCertificationMods(store) {
  return Array.isArray(store?.mods)
    ? store.mods.filter((mod) =>
      mod.defaultInstall === true
      && mod.manifest?.schemaVersion === "1.1",
    )
    : [];
}

async function descriptorUrls(rootUrl) {
  const urls = [];
  for (const entry of await readdir(rootUrl, { withFileTypes: true })) {
    const url = new URL(entry.name, rootUrl);
    if (entry.isDirectory()) {
      urls.push(...await descriptorUrls(new URL(`${url.href}/`)));
    } else if (entry.name === "data-service.json") {
      urls.push(url);
    }
  }
  return urls;
}

export async function loadReleaseDataServices({
  rootUrl = DEFAULT_DATA_SERVICES_ROOT,
} = {}) {
  const services = new Map();
  for (const url of await descriptorUrls(rootUrl)) {
    const descriptor = JSON.parse(await readFile(url, "utf8"));
    const id = typeof descriptor.id === "string" ? descriptor.id : undefined;
    const capabilities = objectValue(descriptor.capabilities);
    if (!id || !capabilities) {
      throw new Error(`${url.pathname} is not a valid data service descriptor`);
    }
    if (services.has(id)) throw new Error(`duplicate data service descriptor: ${id}`);
    services.set(id, descriptor);
  }
  return services;
}

export function checkReleaseModDataContracts(mods, services) {
  const errors = [];
  for (const mod of mods) {
    const manifest = objectValue(mod.manifest);
    const actions = objectValue(manifest?.actions) ?? {};
    const declaredServices = new Set(
      Array.isArray(manifest?.dataServices) ? manifest.dataServices : [],
    );

    for (const [actionId, rawAction] of Object.entries(actions)) {
      const action = objectValue(rawAction);
      const binding = objectValue(action?.binding);
      if (binding?.type !== "data") continue;

      const capability = typeof binding.capability === "string"
        ? binding.capability
        : actionId;
      const serviceId = typeof binding.service === "string"
        ? binding.service
        : undefined;

      if (serviceId) {
        if (!declaredServices.has(serviceId)) {
          errors.push(`${mod.id}/${actionId}: service ${serviceId} is not declared`);
          continue;
        }
        const service = services.get(serviceId);
        if (!service) {
          errors.push(`${mod.id}/${actionId}: service ${serviceId} is not registered`);
          continue;
        }
        const serviceCapability = objectValue(service.capabilities)?.[capability];
        if (!objectValue(serviceCapability)) {
          errors.push(
            `${mod.id}/${actionId}: service ${serviceId} does not provide ${capability}`,
          );
          continue;
        }
        if (serviceCapability.permission !== action.permission) {
          errors.push(
            `${mod.id}/${actionId}: ${capability} requires ${serviceCapability.permission}, not ${action.permission}`,
          );
        }
        continue;
      }

      const providers = [...services.values()].filter((service) =>
        objectValue(objectValue(service.capabilities)?.[capability]),
      );
      if (providers.length === 0) {
        errors.push(`${mod.id}/${actionId}: no data service provides ${capability}`);
      } else if (!providers.some((service) =>
        service.capabilities[capability].permission === action.permission
      )) {
        errors.push(
          `${mod.id}/${actionId}: no ${capability} provider grants ${action.permission}`,
        );
      }
    }
  }
  return errors;
}
