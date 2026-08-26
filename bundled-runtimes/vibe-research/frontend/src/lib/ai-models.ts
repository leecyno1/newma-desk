// 接入 AI 的模型清单（移植自 SDesign-opensource / open-design，按 Vibe-Research 适配）。
// 两类：
//   订阅版（provider "cli-*"）= 调本机已登录的 CLI，用订阅额度、免 API key（仅本地自托管可用）。
//   API 版 = 填自己的 key，走 OpenAI 兼容 /chat/completions。
// key 一律只存本地浏览器、随请求发给你自己的后端；不上传、不进仓库。

export type ProviderId =
  | "deepseek"
  | "silicon"
  | "openai"
  | "minimax"
  | "openrouter"
  | "groq"
  | "together"
  | "mimo"
  | "openai-compatible"
  | "cli-claude"
  | "cli-qwen"
  | "cli-deepseek"
  | "cli-codex"
  | "cli-opencode"
  | "cli-cursor"
  | "cli-kimi";

export interface ModelConfig {
  id: string;        // 实际传给接口/CLI 的 model 名
  name: string;      // 下拉里显示的品牌名
  description: string;
  provider: ProviderId;
  comingSoon?: boolean; // true = 列出但暂不可选（开发中）
}

export const isCliProvider = (p: ProviderId): boolean => p.startsWith("cli-");

// 各 API provider 的默认接口地址（OpenAI 兼容）。选中即自动填 baseURL，用户只需填 key。
export const PROVIDER_BASE: Partial<Record<ProviderId, string>> = {
  deepseek: "https://api.deepseek.com",
  silicon: "https://api.siliconflow.cn/v1",
  openai: "https://api.openai.com/v1",
  minimax: "https://api.minimaxi.com/v1",
  openrouter: "https://openrouter.ai/api/v1",
  groq: "https://api.groq.com/openai/v1",
  together: "https://api.together.xyz/v1",
  mimo: "", // 私有网关，必须自填 baseURL
  "openai-compatible": "", // 任意兼容端点，自填
};

export const aiModels: ModelConfig[] = [
  // —— 订阅版（免 API key，调本机已登录的 CLI）——
  { id: "claude-code", name: "Claude Code", description: "用本机 Claude 订阅", provider: "cli-claude" },
  { id: "qwen-code", name: "Qwen Code", description: "通义 Qwen Code 订阅", provider: "cli-qwen" },
  { id: "deepseek-cli", name: "DeepSeek CLI", description: "DeepSeek 本机 CLI 订阅", provider: "cli-deepseek" },
  { id: "codex", name: "Codex", description: "OpenAI Codex 订阅（需 codex login 登录）", provider: "cli-codex" },
  { id: "opencode", name: "OpenCode", description: "OpenCode 订阅", provider: "cli-opencode", comingSoon: true },
  { id: "cursor-agent", name: "Cursor Agent", description: "Cursor Agent 订阅", provider: "cli-cursor", comingSoon: true },
  { id: "kimi", name: "Kimi", description: "Kimi 订阅", provider: "cli-kimi", comingSoon: true },
  // —— API 版（填自己的 key）——
  { id: "deepseek-v4-flash", name: "DeepSeek V4 Flash", description: "DeepSeek 官方 · 快而省 · 思考/非思考双模", provider: "deepseek" },
  { id: "deepseek-v4-pro", name: "DeepSeek V4 Pro", description: "DeepSeek 官方 · 旗舰 · 最强推理", provider: "deepseek" },
  { id: "deepseek-ai/DeepSeek-V3", name: "SiliconFlow · DeepSeek V3", description: "硅基流动", provider: "silicon" },
  { id: "gpt-4o", name: "OpenAI GPT-4o", description: "OpenAI", provider: "openai" },
  { id: "MiniMax-M2", name: "MiniMax M2", description: "MiniMax 海螺", provider: "minimax" },
  { id: "doubao-pro", name: "豆包 Pro", description: "火山方舟 · 填推理接入点 ID(ep-…)", provider: "openai-compatible" },
  { id: "openai/gpt-4o", name: "OpenRouter · GPT-4o", description: "OpenRouter 聚合（可改任意模型 id）", provider: "openrouter" },
  { id: "llama-3.3-70b-versatile", name: "Groq · Llama 3.3 70B", description: "Groq 超快推理", provider: "groq" },
  { id: "meta-llama/Llama-3.3-70B-Instruct-Turbo", name: "Together · Llama 3.3 70B", description: "Together AI", provider: "together" },
  { id: "mimo-v2.5-pro", name: "MiMo V2.5 Pro", description: "小米 MiMo（需自有网关）", provider: "mimo" },
  { id: "custom", name: "其它 OpenAI 兼容", description: "任意兼容端点，自填 baseURL/model", provider: "openai-compatible" },
];

export const subscriptionModels = aiModels.filter((m) => isCliProvider(m.provider));
export const apiModels = aiModels.filter((m) => !isCliProvider(m.provider));
