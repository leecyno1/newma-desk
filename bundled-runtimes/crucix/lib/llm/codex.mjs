// OpenAI Codex Provider — uses ChatGPT subscription via chatgpt.com/backend-api/codex/responses
// Auth: reads ~/.codex/auth.json (created by `npx @openai/codex login`)
// SSE streaming, codex-specific models only (gpt-5.3-codex, gpt-5.3-codex-spark)

import { readFileSync } from 'fs';
import { join } from 'path';
import { homedir } from 'os';
import { LLMProvider } from './provider.mjs';

const CODEX_ENDPOINT = 'https://chatgpt.com/backend-api/codex/responses';
const AUTH_PATH = join(homedir(), '.codex', 'auth.json');

export class CodexProvider extends LLMProvider {
  constructor(config) {
    super(config);
    this.name = 'codex';
    this.model = config.model || 'gpt-5.3-codex';
    this._creds = null;
  }

  get isConfigured() {
    return !!this._getCredentials();
  }

  _getCredentials() {
    if (this._creds) return this._creds;

    // Try env vars first
    const token = process.env.CODEX_ACCESS_TOKEN || process.env.OPENAI_OAUTH_TOKEN;
    const accountId = process.env.CODEX_ACCOUNT_ID;
    if (token && accountId) {
      this._creds = { accessToken: token, accountId };
      return this._creds;
    }

    // Try ~/.codex/auth.json
    try {
      const auth = JSON.parse(readFileSync(AUTH_PATH, 'utf8'));
      // Tokens may be nested under auth.tokens (newer format) or top-level
      const tokens = auth.tokens || auth;
      const accessToken = tokens.access_token || tokens.token || auth.access_token || auth.token;
      if (accessToken) {
        this._creds = {
          accessToken,
          accountId: tokens.account_id || auth.account_id || accountId || '',
        };
        return this._creds;
      }
    } catch { /* no auth file */ }

    return null;
  }

  _clearCredentials() {
    this._creds = null;
  }

  async complete(systemPrompt, userMessage, opts = {}) {
    const creds = this._getCredentials();
    if (!creds) throw new Error('Codex: No credentials found. Run `npx @openai/codex login`');

    const headers = {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${creds.accessToken}`,
    };
    if (creds.accountId) headers['ChatGPT-Account-Id'] = creds.accountId;

    const body = {
      model: this.model,
      instructions: systemPrompt || '',
      input: [{ type: 'message', role: 'user', content: userMessage }],
      stream: true,
      store: false,
    };

    const res = await fetch(CODEX_ENDPOINT, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(opts.timeout || 90000),
    });

    if (res.status === 401 || res.status === 403) {
      this._clearCredentials();
      throw new Error(`Codex auth failed (${res.status}). Run \`npx @openai/codex login\` to refresh.`);
    }

    if (!res.ok) {
      const err = await res.text().catch(() => '');
      throw new Error(`Codex API ${res.status}: ${err.substring(0, 200)}`);
    }

    // Parse SSE stream
    const text = await this._parseSSE(res);

    return {
      text,
      usage: { inputTokens: 0, outputTokens: 0 }, // Codex doesn't always return usage
      model: this.model,
    };
  }

  async _parseSSE(res) {
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let text = '';
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const payload = line.slice(6).trim();
        if (payload === '[DONE]') return text;

        try {
          const event = JSON.parse(payload);
          // Handle text deltas
          if (event.type === 'response.output_text.delta') {
            text += event.delta || '';
          }
          // Handle completed response
          if (event.type === 'response.completed') {
            const output = event.response?.output;
            if (output && Array.isArray(output)) {
              for (const item of output) {
                if (item.type === 'message' && item.content) {
                  for (const part of item.content) {
                    if (part.type === 'output_text') text = part.text || text;
                  }
                }
              }
            }
          }
        } catch { /* skip malformed events */ }
      }
    }

    return text;
  }
}
