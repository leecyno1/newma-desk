// Base LLM Provider — all providers implement this interface

export class LLMProvider {
  constructor(config) {
    this.config = config;
    this.name = 'base';
  }

  /**
   * Complete a prompt with system + user messages
   * @returns {{ text: string, usage: { inputTokens: number, outputTokens: number }, model: string }}
   */
  async complete(systemPrompt, userMessage, opts = {}) {
    throw new Error(`${this.name}: complete() not implemented`);
  }

  get isConfigured() { return false; }
}
