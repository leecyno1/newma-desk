import { Landmark, Send } from "lucide-react";

import { openVibeDeskCopilot } from "@/lib/vibedesk";

export function DeskAgent() {
  return (
    <div className="flex min-h-screen items-center justify-center p-8">
      <section className="w-full max-w-xl rounded-xl border bg-card p-8 text-center shadow-sm">
        <Landmark className="mx-auto h-10 w-10 text-primary" />
        <h1 className="mt-4 text-2xl font-semibold">Desk 顶层 Agent Runtime 已统一接管</h1>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          挂载 Newma 时使用宿主 Agent，独立运行时使用 Desk Gateway；Trading Mod 不再维护重复配置。
        </p>
        <button
          type="button"
          onClick={() => void openVibeDeskCopilot()}
          className="mt-6 inline-flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground transition hover:opacity-90"
        >
          打开统一 Copilot
          <Send className="h-4 w-4" />
        </button>
      </section>
    </div>
  );
}
