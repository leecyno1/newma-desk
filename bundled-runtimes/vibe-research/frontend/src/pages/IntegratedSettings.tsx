import { Terminal } from "lucide-react";

import { GlassCard } from "@/components/ui/GlassCard";
import { PageHeader } from "@/components/ui/PageHeader";

/** Desk-hosted Research keeps model and session selection in the shared Agent. */
export function IntegratedSettings() {
  return (
    <div>
      <PageHeader title="Agent 接入" subtitle="当前 Mod 由 Newma-Desk 统一管理 Agent" />
      <GlassCard>
        <div className="flex items-start gap-3">
          <Terminal className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
          <div>
            <h3 className="font-semibold">使用 Desk Agent Gateway</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              请在 Newma-Desk 的统一 Agent 设置中选择 Agent。本模块会自动继承当前选择与 Mod
              上下文，无需单独填写模型或 API Key。
            </p>
          </div>
        </div>
      </GlassCard>
    </div>
  );
}
