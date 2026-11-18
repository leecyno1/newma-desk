import assert from 'node:assert/strict';
import { execFile, execFileSync, spawn } from 'node:child_process';
import { once } from 'node:events';
import { cp, mkdtemp, mkdir, readFile, writeFile, rm, symlink } from 'node:fs/promises';
import net from 'node:net';
import http from 'node:http';
import { createRequire } from 'node:module';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import test from 'node:test';
import { promisify } from 'node:util';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '../..');

for (const entry of ['start:proxy', 'inject:proxy', 'managed dotenv']) {
  test(`${entry} loads proxy settings before fetch and bypasses it for local services`, {
    timeout: 15000,
    skip: entry === 'managed dotenv'
      ? typeof http.setGlobalProxyFromEnv !== 'function' && 'managed proxy requires http.setGlobalProxyFromEnv'
      : !process.allowedNodeEnvironmentFlags.has('--use-env-proxy') && 'proxy entry requires Node 22.21+ or 24.5+',
  }, async () => {
    const { scripts } = JSON.parse(await readFile(join(root, 'package.json'), 'utf8'));
    const command = entry === 'managed dotenv' ? ['node'] : scripts[entry]?.split(' ');
    assert.ok(command, `${entry} must be an explicit opt-in entry`);
    assert.equal(scripts.start, 'node server.mjs');
    assert.equal(scripts.inject, 'node dashboard/inject.mjs');
    const fixture = await mkdtemp(join(tmpdir(), 'crucix-proxy-test-'));
    const hits = [];
    const sockets = new Set();
    const rss = '<rss><channel><item><title>Synthetic report</title><link>https://example.invalid/report</link></item></channel></rss>';
    let localHits = 0;
    const local = http.createServer((_req, res) => { localHits++; res.end(rss); });
    const proxy = http.createServer((req, res) => {
      const target = new URL(req.url);
      hits.push(`${target.hostname}:${target.port || 80}`);
      if (target.hostname === 'rss-proxy.invalid') res.end(rss);
      else res.writeHead(403).end('Synthetic refusal');
    });
    proxy.on('connection', (socket) => {
      sockets.add(socket);
      socket.on('close', () => sockets.delete(socket));
    });
    proxy.on('connect', (req, socket) => {
      hits.push(req.url);
      if (!['rss-proxy.invalid:80', 'rss-denied.invalid:80'].includes(req.url)) {
        socket.end('HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n');
        return;
      }
      socket.write('HTTP/1.1 200 Connection Established\r\n\r\n');
      socket.once('data', () => {
        const denied = req.url === 'rss-denied.invalid:80';
        const body = denied ? 'Synthetic refusal' : rss;
        socket.end(`HTTP/1.1 ${denied ? '403 Forbidden' : '200 OK'}\r\nContent-Type: application/rss+xml\r\nContent-Length: ${Buffer.byteLength(body)}\r\nConnection: close\r\n\r\n${body}`);
      });
    });
    try {
      local.listen(0, '127.0.0.1');
      proxy.listen(0, '127.0.0.1');
      await Promise.all([once(local, 'listening'), once(proxy, 'listening')]);
      await writeFile(join(fixture, '.env'), `CRUCIX_USE_ENV_PROXY=true\nHTTP_PROXY=http://127.0.0.1:${proxy.address().port}\nHTTPS_PROXY=http://127.0.0.1:${proxy.address().port}\nNO_PROXY=127.0.0.1,localhost,::1\n`);
      await mkdir(join(fixture, 'apis/utils'), { recursive: true });
      const envModule = join(fixture, 'apis/utils/env.mjs');
      await cp(join(root, 'apis/utils/env.mjs'), envModule);
      const env = { ...process.env };
      for (const key of Object.keys(env)) {
        if (/^(https?_proxy|all_proxy|no_proxy|node_use_env_proxy|node_options|crucix_use_env_proxy)$/i.test(key)) delete env[key];
      }
      const sourceUrl = pathToFileURL(join(root, 'dashboard/rss.mjs')).href;
      const probe = `${entry === 'managed dotenv' ? `await import(${JSON.stringify(pathToFileURL(envModule).href)});` : ''}
        const {fetchNewsSource}=await import(${JSON.stringify(sourceUrl)});
        const results=[];
        for (const url of ['http://rss-proxy.invalid/feed','http://127.0.0.1:${local.address().port}/feed','http://rss-denied.invalid/feed']) results.push(await fetchNewsSource(url,'Synthetic'));
        console.log(JSON.stringify(results));`;
      const { stdout } = await promisify(execFile)(process.execPath,
        [...(entry === 'managed dotenv' ? [] : command.slice(1, command.indexOf('--use-env-proxy') + 1)), '--input-type=module', '-e', probe],
        { cwd: fixture, env, timeout: 10000 });
      const [proxied, direct, denied] = JSON.parse(stdout);
      assert.equal(proxied.status, 'ok', JSON.stringify(proxied));
      assert.equal(proxied.count, 1);
      assert.equal(direct.status, 'ok');
      assert.equal(direct.count, 1);
      assert.equal(localHits, 1, 'local services must not enter the proxy');
      assert.equal(denied.status, 'error');
      assert.equal(denied.httpStatus, 403);
      assert.equal(denied.count, null);
      assert.deepEqual(hits, ['rss-proxy.invalid:80', 'rss-denied.invalid:80'], 'no retry or direct fallback');
    } finally {
      for (const socket of sockets) socket.destroy();
      await Promise.all([new Promise((done) => proxy.close(done)), new Promise((done) => local.close(done))]);
      await rm(fixture, { recursive: true, force: true });
    }
  });
}

test('managed proxy is opt-in, respects explicit disable and rejects unsupported Node', async () => {
  const fixture = await mkdtemp(join(tmpdir(), 'crucix-proxy-opt-in-'));
  try {
    await mkdir(join(fixture, 'apis/utils'), { recursive: true });
    const module = join(fixture, 'apis/utils/env.mjs');
    await cp(join(root, 'apis/utils/env.mjs'), module);
    const baseEnv = { ...process.env };
    delete baseEnv.CRUCIX_USE_ENV_PROXY;
    const probe = `import http from 'node:http'; let calls=0;
      http.setGlobalProxyFromEnv=()=>{calls++};
      await import(${JSON.stringify(pathToFileURL(module).href)}); console.log(calls);`;
    const run = (env, script = probe) => execFileSync(process.execPath,
      ['--input-type=module', '-e', script], { env, encoding: 'utf8' }).trim();
    assert.equal(run(baseEnv), '0', 'default must not change proxy routing');
    await writeFile(join(fixture, '.env'), 'CRUCIX_USE_ENV_PROXY=true\n');
    assert.equal(run({ ...baseEnv, CRUCIX_USE_ENV_PROXY: 'false' }), '0');
    assert.equal(run(baseEnv), '1');
    assert.equal(run(baseEnv, `import http from 'node:http'; http.setGlobalProxyFromEnv=undefined;
      try { await import(${JSON.stringify(pathToFileURL(module).href)}); process.exit(1); }
      catch(error) { console.log(error.message.includes('requires Node http.setGlobalProxyFromEnv')); }`), 'true');
  } finally {
    await rm(fixture, { recursive: true, force: true });
  }
});

test('an explicit empty credential is not restored from dotenv', async () => {
  const fixture = await mkdtemp(join(tmpdir(), 'crucix-env-test-'));
  try {
    await mkdir(join(fixture, 'apis/utils'), { recursive: true });
    const module = join(fixture, 'apis/utils/env.mjs');
    await writeFile(module, await readFile(new URL('./env.mjs', import.meta.url)));
    await writeFile(join(fixture, '.env'), 'LLM_PROVIDER=synthetic-provider\nLLM_API_KEY=synthetic-key\nTELEGRAM_BOT_TOKEN=synthetic-bot\nUNSET_TEST_VALUE=fallback\n');
    const env = { ...process.env, LLM_PROVIDER: '', LLM_API_KEY: '', TELEGRAM_BOT_TOKEN: '' };
    delete env.UNSET_TEST_VALUE;
    const output = execFileSync(process.execPath, ['--input-type=module', '-e',
      `await import(${JSON.stringify(pathToFileURL(module).href)}); console.log(JSON.stringify([process.env.LLM_PROVIDER,process.env.LLM_API_KEY,process.env.TELEGRAM_BOT_TOKEN,process.env.UNSET_TEST_VALUE]));`,
    ], { env, encoding: 'utf8' });
    assert.deepEqual(JSON.parse(output), ['', '', '', 'fallback']);
  } finally {
    await rm(fixture, { recursive: true, force: true });
  }
});

test('state location is explicit and automatic sweeps remain the default', async () => {
  const fixture = await mkdtemp(join(tmpdir(), 'crucix-config-test-'));
  try {
    const configUrl = pathToFileURL(join(root, 'crucix.config.mjs')).href;
    const script = `const {default:c}=await import(${JSON.stringify(configUrl)}); console.log(JSON.stringify({runsDir:c.runsDir,autoSweep:c.autoSweep}));`;
    const env = { ...process.env, CRUCIX_RUNS_DIR: join(fixture, 'state') };
    delete env.CRUCIX_AUTO_SWEEP;
    const defaults = JSON.parse(execFileSync(process.execPath, ['--input-type=module', '-e', script], { cwd: fixture, env, encoding: 'utf8' }));
    assert.deepEqual(defaults, { runsDir: join(fixture, 'state'), autoSweep: true });
    const manual = JSON.parse(execFileSync(process.execPath, ['--input-type=module', '-e', script], {
      cwd: fixture, env: { ...env, CRUCIX_AUTO_SWEEP: 'false' }, encoding: 'utf8',
    }));
    assert.equal(manual.autoSweep, false);
  } finally {
    await rm(fixture, { recursive: true, force: true });
  }
});

test('manual service loads its configured snapshot without collection, models or a timer', { timeout: 15000 }, async () => {
  const fixture = await mkdtemp(join(tmpdir(), 'crucix-service-test-'));
  const candidate = join(fixture, 'source');
  await cp(root, candidate, { recursive: true, filter: (file) => {
    const relative = file.slice(root.length).split('/');
    return !relative.some((part) => part === 'node_modules' || part === 'runs' || part.startsWith('.env'));
  } });
  const require = createRequire(import.meta.url);
  await mkdir(join(candidate, 'node_modules'));
  for (const name of ['express', 'saxes']) {
    await symlink(dirname(require.resolve(`${name}/package.json`)), join(candidate, 'node_modules', name), 'dir');
  }
  const listener = net.createServer();
  listener.listen(0, '127.0.0.1');
  await once(listener, 'listening');
  const port = listener.address().port;
  await new Promise((done) => listener.close(done));
  const timestamp = '2026-10-26T00:00:00Z';
  await writeFile(join(fixture, 'latest.json'), JSON.stringify({ crucix: { timestamp }, sources: {}, timing: {} }));
  const rssAttempt = { source: 'BBC', status: 'error', count: null, asOf: timestamp, reason: 'HTTP 503' };
  const rssCache = JSON.stringify({ version: 1, entries: {
    [JSON.stringify(['http://feeds.bbci.co.uk/news/world/rss.xml', 'BBC'])]: {
      attempt: rssAttempt,
      data: { source: 'BBC', status: 'ok', count: 1, asOf: timestamp, reason: 'parsed',
        items: [{ title: 'Synthetic restart retained report', source: 'BBC', date: null, url: null }] },
    },
  } });
  await writeFile(join(fixture, 'rss-cache.json'), rssCache);
  const preload = join(fixture, 'no-network.mjs');
  await writeFile(preload, 'globalThis.fetch = async () => { console.error("UNEXPECTED_OUTBOUND_REQUEST"); throw new Error("Network disabled by test"); };');
  try {
    for (let boot = 0; boot < 2; boot++) {
      const child = spawn(process.execPath, ['--import', preload, join(candidate, 'server.mjs')], {
        cwd: fixture, env: {
          ...process.env, HOST: '127.0.0.1', PORT: String(port), CRUCIX_RUNS_DIR: fixture,
          AUTO_OPEN_DASHBOARD: 'false', CRUCIX_AUTO_SWEEP: 'false',
          LLM_PROVIDER: '', LLM_API_KEY: '', TELEGRAM_BOT_TOKEN: '', TELEGRAM_CHAT_ID: '',
          DISCORD_BOT_TOKEN: '', DISCORD_CHANNEL_ID: '', DISCORD_WEBHOOK_URL: '',
        }, stdio: ['ignore', 'pipe', 'pipe'],
      });
      let logs = '';
      child.stdout.on('data', (part) => { logs += part; });
      child.stderr.on('data', (part) => { logs += part; });
      try {
        let health;
        for (let attempt = 0; attempt < 100; attempt++) {
          assert.equal(child.exitCode, null, logs);
          try {
            health = await (await fetch(`http://127.0.0.1:${port}/api/health`, { signal: AbortSignal.timeout(1000) })).json();
            if (health.lastSweep === timestamp) break;
          } catch {}
          await new Promise((done) => setTimeout(done, 50));
        }
        assert.equal(health?.lastSweep, timestamp, logs);
        assert.equal(health.autoSweepEnabled, false);
        assert.equal(health.nextSweep, null);
        assert.equal(health.sweepInProgress, false);
        assert.equal(health.sweepStartedAt, null);
        assert.equal(health.llmEnabled, false);
        assert.equal(health.telegramEnabled, false);
        const data = await (await fetch(`http://127.0.0.1:${port}/api/data`, { signal: AbortSignal.timeout(1000) })).json();
        assert.equal(data.meta.timestamp, timestamp);
        assert.equal(data.ideasSource, 'disabled');
        assert.equal(data.newsMeta.mode, 'cache');
        assert.equal(data.newsMeta.status, 'partial');
        assert.equal(data.newsMeta.items[0].status, 'error');
        assert.equal(data.newsFeed[0].headline, 'Synthetic restart retained report');
        assert.equal(data.newsFeed[0].collectedAt, timestamp);
        assert.equal(data.newsFeed[0].timestamp, null);
        assert.equal(data.newsFeed[0].cached, true);
        assert.equal(await readFile(join(fixture, 'rss-cache.json'), 'utf8'), rssCache);
        assert.doesNotMatch(logs, /UNEXPECTED_OUTBOUND_REQUEST|Starting sweep/);
      } finally {
        if (child.exitCode === null) {
          const exited = once(child, 'exit');
          child.kill('SIGTERM');
          await exited;
        }
      }
    }
  } finally {
    await rm(fixture, { recursive: true, force: true });
  }
});
