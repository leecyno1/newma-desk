import { execFileSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import { isAbsolute, relative, resolve } from "node:path";

const host = "127.0.0.1";
const configuredKey = "VIBE_E2E_RUNTIME_CONFIGURED";
const runtimeDirectory = resolve("runtime");

const envKeys = {
  apiPort: "VIBE_E2E_API_PORT",
  apiOrigin: "VIBE_E2E_API_ORIGIN",
  modulePort: "VIBE_E2E_MODULE_PORT",
  moduleOrigin: "VIBE_E2E_MODULE_ORIGIN",
  shellPort: "VIBE_E2E_SHELL_PORT",
  shellOrigin: "VIBE_E2E_SHELL_ORIGIN",
  databasePath: "VIBE_E2E_DATABASE_PATH",
  runId: "VIBE_E2E_RUN_ID",
} as const;

interface RuntimeConfig {
  apiPort: number;
  apiOrigin: string;
  modulePort: number;
  moduleOrigin: string;
  shellPort: number;
  shellOrigin: string;
  databasePath: string;
  runId: string;
}

const allocatePortsScript = `
import socket
import sys

sockets = []
ports = []
for raw_port in sys.argv[1:]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", int(raw_port)))
    sockets.append(sock)
    ports.append(sock.getsockname()[1])

print(",".join(str(port) for port in ports), flush=True)
`;

function parsePort(value: string | undefined, name: string): number {
  const port = Number(value);
  if (!Number.isInteger(port) || port < 1 || port > 65_535) {
    throw new Error(`${name} must be an integer between 1 and 65535`);
  }
  return port;
}

function requiredEnvironmentValue(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Missing inherited E2E setting ${name}`);
  return value;
}

function assertRuntimeDatabase(databasePath: string): void {
  const pathFromRuntime = relative(runtimeDirectory, databasePath);
  if (
    !pathFromRuntime ||
    pathFromRuntime.startsWith("..") ||
    isAbsolute(pathFromRuntime) ||
    !databasePath.endsWith(".db")
  ) {
    throw new Error("The E2E database must be a .db file under runtime");
  }
}

function assertDistinctPorts(ports: number[]): void {
  if (new Set(ports).size !== ports.length) {
    throw new Error("E2E API, module, and Shell ports must be distinct");
  }
}

function inheritedRuntimeConfig(): RuntimeConfig {
  const apiPort = parsePort(
    requiredEnvironmentValue(envKeys.apiPort),
    envKeys.apiPort,
  );
  const modulePort = parsePort(
    requiredEnvironmentValue(envKeys.modulePort),
    envKeys.modulePort,
  );
  const shellPort = parsePort(
    requiredEnvironmentValue(envKeys.shellPort),
    envKeys.shellPort,
  );
  const apiOrigin = requiredEnvironmentValue(envKeys.apiOrigin);
  const moduleOrigin = requiredEnvironmentValue(envKeys.moduleOrigin);
  const shellOrigin = requiredEnvironmentValue(envKeys.shellOrigin);
  const databasePath = resolve(requiredEnvironmentValue(envKeys.databasePath));
  assertDistinctPorts([apiPort, modulePort, shellPort]);
  assertRuntimeDatabase(databasePath);
  if (
    apiOrigin !== `http://${host}:${apiPort}` ||
    moduleOrigin !== `http://${host}:${modulePort}` ||
    shellOrigin !== `http://${host}:${shellPort}`
  ) {
    throw new Error("Inherited E2E origins do not match their resolved ports");
  }

  return {
    apiPort,
    apiOrigin,
    modulePort,
    moduleOrigin,
    shellPort,
    shellOrigin,
    databasePath,
    runId: requiredEnvironmentValue(envKeys.runId),
  };
}

function requestedPort(name: string): string {
  const value = process.env[name];
  if (value === undefined) return "0";
  return String(parsePort(value, name));
}

function allocatePorts(): [number, number, number] {
  let output: string;
  try {
    output = execFileSync(
      "python3",
      [
        "-c",
        allocatePortsScript,
        requestedPort(envKeys.apiPort),
        requestedPort(envKeys.modulePort),
        requestedPort(envKeys.shellPort),
      ],
      { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] },
    ).trim();
  } catch {
    throw new Error(
      "Unable to allocate the requested E2E loopback ports; verify any CI overrides are free",
    );
  }

  const ports = output.split(",").map((value) => parsePort(value, "port"));
  if (ports.length !== 3) {
    throw new Error("The E2E port allocator returned an invalid result");
  }
  assertDistinctPorts(ports);
  return ports as [number, number, number];
}

function createRuntimeConfig(): RuntimeConfig {
  const [apiPort, modulePort, shellPort] = allocatePorts();
  const runLabel = (process.env[envKeys.runId] || "run").replace(
    /[^a-zA-Z0-9_-]/g,
    "-",
  );
  const runId = `${runLabel}-${process.pid}-${randomBytes(6).toString("hex")}`;
  const databasePath = resolve(
    runtimeDirectory,
    `e2e-foundation-${runId}.db`,
  );
  assertRuntimeDatabase(databasePath);

  return {
    apiPort,
    apiOrigin: `http://${host}:${apiPort}`,
    modulePort,
    moduleOrigin: `http://${host}:${modulePort}`,
    shellPort,
    shellOrigin: `http://${host}:${shellPort}`,
    databasePath,
    runId,
  };
}

function storeRuntimeConfig(config: RuntimeConfig): void {
  process.env[envKeys.apiPort] = String(config.apiPort);
  process.env[envKeys.apiOrigin] = config.apiOrigin;
  process.env[envKeys.modulePort] = String(config.modulePort);
  process.env[envKeys.moduleOrigin] = config.moduleOrigin;
  process.env[envKeys.shellPort] = String(config.shellPort);
  process.env[envKeys.shellOrigin] = config.shellOrigin;
  process.env[envKeys.databasePath] = config.databasePath;
  process.env[envKeys.runId] = config.runId;
  process.env[configuredKey] = "1";
}

const runtimeConfig =
  process.env[configuredKey] === "1"
    ? inheritedRuntimeConfig()
    : createRuntimeConfig();

if (process.env[configuredKey] !== "1") storeRuntimeConfig(runtimeConfig);

export const {
  apiPort,
  apiOrigin,
  modulePort,
  moduleOrigin,
  shellPort,
  shellOrigin,
  databasePath,
  runId,
} = runtimeConfig;

export const apiHealthPath = "/api/health";
export const apiHealthUrl = `${apiOrigin}${apiHealthPath}`;
export const demoModulePath = "/modules/demo/";
export const demoModuleUrl = `${moduleOrigin}${demoModulePath}`;
export const shellModuleUrl = `${shellOrigin}/?module=demo`;
export const databaseFiles = ["", "-journal", "-shm", "-wal"].map(
  (suffix) => `${databasePath}${suffix}`,
);
