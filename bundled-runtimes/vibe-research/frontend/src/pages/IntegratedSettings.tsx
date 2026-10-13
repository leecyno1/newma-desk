import { Terminal } from "lucide-react";

import { GlassCard } from "@/components/ui/GlassCard";
import { PageHeader } from "@/components/ui/PageHeader";

/** Desk-hosted Research delegates model and session ownership to the active runtime adapter. */
export function IntegratedSettings() {
  return (
    <div>
      <PageHeader title="Agent 接入" subtitle="当前 Mod 使用 Desk 顶层 Agent Runtime" />
      <GlassCard>
        <div className="flex items-start gap-3">
          <Terminal className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
          <div>
            <h3 className="font-semibold">使用统一 Agent Runtime</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              挂载 Newma 时使用宿主 Agent；独立运行时使用 Desk Gateway 与本地 CLI。
              本模块只提供当前 Mod 上下文，不再保存重复的模型密钥或 Agent 配置。
            </p>
          </div>
        </div>
      </GlassCard>
    </div>
  );
}
