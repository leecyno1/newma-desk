import { rm, access } from 'fs/promises';
import { join } from 'path';

const targets = [
  'runs/latest.json',
  'runs/memory',
];

for (const target of targets) {
  const full = join(process.cwd(), target);
  try {
    await access(full);
    await rm(full, { recursive: true });
    console.log(`removed: ${target}`);
  } catch {
    // not found — skip silently
  }
}
