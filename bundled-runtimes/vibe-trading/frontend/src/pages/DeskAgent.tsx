import { Landmark, Send } from "lucide-react";

import { openVibeDeskCopilot } from "@/lib/vibedesk";

export function DeskAgent() {
  return (
    <div className="flex min-h-screen items-center justify-center p-8">
      <section className="w-full max-w-xl rounded-xl border bg-card p-8 text-center shadow-sm">
        <Landmark className="mx-auto h-10 w-10 text-primary" />
        <h1 className="mt-4 text-2xl font-semibold">Desk Agent 已统一接管</h1>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          模型、会话、文件上下文与多 Agent 任务均由 Newma-Desk 右侧 Agent 提供，Trading Mod 不再维护重复的模型和会话配置。
        </p>
        <button
          type="button"
          onClick={() => void openVibeDeskCopilot()}
          className="mt-6 inline-flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground transition hover:opacity-90"
        >
          打开 Desk Agent
          <Send className="h-4 w-4" />
        </button>
      </section>
    </div>
  );
}
