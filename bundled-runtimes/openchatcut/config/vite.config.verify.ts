import assert from 'node:assert/strict';
import {
  applyAuthoritativeLocalProvider,
  OPENCHATCUT_WARMUP_FILES,
} from './vite.config.ts';

assert.deepEqual(
  OPENCHATCUT_WARMUP_FILES,
  ['src/main.tsx'],
  'Vite warmup paths stay relative to the OpenChatCut root',
);

const inherited = { LLM_PROVIDER: 'openai' };
applyAuthoritativeLocalProvider(
  inherited,
  'export LLM_PROVIDER = "deepseek" # checkout selection wins\n',
);
assert.equal(
  inherited.LLM_PROVIDER,
  'deepseek',
  '.env.local uses dotenv quoting/export/comment syntax and overrides inherited process env',
);

const singleQuoted = { LLM_PROVIDER: 'openai' };
applyAuthoritativeLocalProvider(singleQuoted, "LLM_PROVIDER='anthropic' # quoted provider\n");
assert.equal(singleQuoted.LLM_PROVIDER, 'anthropic');

const absent = { LLM_PROVIDER: 'gemini' };
applyAuthoritativeLocalProvider(absent, 'OTHER_SETTING=value\n');
const explicitlyEmpty = { LLM_PROVIDER: 'openai' };
applyAuthoritativeLocalProvider(explicitlyEmpty, 'LLM_PROVIDER= # use repository default\n');
assert.equal(
  explicitlyEmpty.LLM_PROVIDER,
  '',
  'an explicit local provider setting still shadows inherited process env when empty',
);

assert.equal(absent.LLM_PROVIDER, 'gemini', 'an absent local provider preserves inherited selection');

console.log('Vite dotenv provider precedence verification passed');
