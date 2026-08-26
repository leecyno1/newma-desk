#!/usr/bin/env node
// Crucix Diagnostic — run this to find out why server.mjs fails silently
// Usage: node diag.mjs

console.log('=== CRUCIX DIAGNOSTICS ===\n');
console.log('Node version:', process.version);
console.log('Platform:', process.platform, process.arch);
console.log('CWD:', process.cwd());
console.log('');

// Step 1: Check Node version
const major = parseInt(process.version.slice(1));
if (major < 22) {
  console.error('❌ Node.js >= 22 required, you have', process.version);
  console.error('   Download: https://nodejs.org/');
  process.exit(1);
}
console.log('✅ Node version OK');

// Step 2: Check express
try {
  await import('express');
  console.log('✅ express imported OK');
} catch (err) {
  console.error('❌ express import failed:', err.message);
  console.error('   Run: npm install');
  process.exit(1);
}

// Step 3: Check crypto (used by delta engine)
try {
  const { createHash } = await import('crypto');
  createHash('sha256').update('test').digest('hex');
  console.log('✅ crypto OK');
} catch (err) {
  console.error('❌ crypto failed:', err.message);
  process.exit(1);
}

// Step 4: Check each local module
const modules = [
  ['./crucix.config.mjs', 'config'],
  ['./apis/utils/env.mjs', 'env loader'],
  ['./lib/delta/engine.mjs', 'delta engine'],
  ['./lib/delta/memory.mjs', 'memory manager'],
  ['./lib/delta/index.mjs', 'delta index'],
  ['./lib/llm/index.mjs', 'LLM factory'],
  ['./lib/llm/ideas.mjs', 'LLM ideas'],
  ['./lib/alerts/telegram.mjs', 'telegram alerter'],
  ['./dashboard/inject.mjs', 'dashboard inject'],
  ['./apis/briefing.mjs', 'briefing orchestrator'],
];

for (const [path, label] of modules) {
  try {
    await import(path);
    console.log(`✅ ${label} (${path})`);
  } catch (err) {
    console.error(`❌ ${label} FAILED: ${err.message}`);
    if (err.stack) console.error('   ', err.stack.split('\n').slice(1, 3).join('\n   '));
  }
}

// Step 5: Check port availability
console.log('');
const net = await import('net');
const port = 3117;
const server = net.default.createServer();
try {
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(port, () => { server.close(); resolve(); });
  });
  console.log(`✅ Port ${port} is available`);
} catch (err) {
  if (err.code === 'EADDRINUSE') {
    console.error(`❌ Port ${port} is already in use!`);
    console.error('   A previous Crucix instance may still be running.');
    console.error('   Fix: taskkill /F /IM node.exe   (kills all Node processes)');
    console.error('   Or:  npx kill-port 3117');
  } else {
    console.error(`❌ Port ${port} error:`, err.message);
  }
}

// Step 6: Try full server import
console.log('\n--- Attempting full server import ---');
try {
  await import('./server.mjs');
  console.log('✅ server.mjs loaded and running');
} catch (err) {
  console.error('❌ server.mjs CRASHED:', err.message);
  console.error(err.stack);
}
