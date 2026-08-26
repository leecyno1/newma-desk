import { Info } from "lucide-react";

// 中立免责条 —— 产品定调：只客观呈现公开数据/榜单，不推荐、不预测、无倾向；方向由用户自己的 AI 给出。
export function Disclaimer({ compact = false }: { compact?: boolean }) {
  if (compact) {
    return (
      <p className="text-xs leading-relaxed text-muted-foreground/70">
        Newma-Trading 只客观呈现公开数据与榜单，不推荐个股、不预测涨跌、不构成投资建议。
      </p>
    );
  }
  return (
    <div className="mt-8 flex items-start gap-2 rounded-lg border border-border/60 bg-muted/20 p-3 text-xs leading-relaxed text-muted-foreground">
      <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      <span>
        Newma-Trading 是一个中立的信息整理与 AI 接入工具。榜单（连板股 / 成交额等）均为<b className="text-foreground">客观公开数据</b>；本产品<b className="text-foreground">只呈现事实，不推荐个股、不预测涨跌、不给买卖时机、不构成投资建议</b>；
        看板内所有分析方向均由你自己配置的 AI 给出，与本产品无关。请自行核实并独立决策，风险自担。
      </span>
    </div>
  );
}
