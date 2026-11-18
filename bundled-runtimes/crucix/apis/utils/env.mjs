// Load .env file for API keys
// Searches: project root .env first, then apis/.env as fallback
import { readFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import http from 'node:http';

const __dirname = dirname(fileURLToPath(import.meta.url));
const paths = [
  resolve(__dirname, '..', '..', '.env'), // project root
  resolve(__dirname, '..', '.env'),        // apis/.env (legacy)
];

function loadEnv(filePath) {
  try {
    const content = readFileSync(filePath, 'utf-8');
    let loaded = 0;
    for (const line of content.split('\n')) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const eq = trimmed.indexOf('=');
      if (eq === -1) continue;
      const key = trimmed.slice(0, eq).trim();
      let val = trimmed.slice(eq + 1).trim();
      // Strip surrounding quotes (single or double) to support special characters
      if ((val.startsWith('"') && val.endsWith('"')) || (val.startsWith("'") && val.endsWith("'"))) {
        val = val.slice(1, -1);
      }
      // Empty is an explicit override too (e.g. disable a configured provider).
      if (process.env[key] === undefined) { process.env[key] = val; loaded++; }
    }
    return loaded;
  } catch { return -1; }
}

for (const p of paths) {
  if (loadEnv(p) >= 0) break;
}

// Managed launchers may use `node server.mjs` rather than the proxy CLI entry.
// Apply the explicit setting after dotenv and before any source requests.
if (process.env.CRUCIX_USE_ENV_PROXY === 'true') {
  if (typeof http.setGlobalProxyFromEnv !== 'function') {
    throw new Error('CRUCIX_USE_ENV_PROXY requires Node http.setGlobalProxyFromEnv; upgrade Node or use start:proxy / inject:proxy.');
  }
  http.setGlobalProxyFromEnv();
}
