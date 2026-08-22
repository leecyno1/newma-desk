export const sidebarGroupTones = [
  "orange",
  "blue",
  "violet",
  "cyan",
  "red",
  "green",
  "slate",
  "indigo",
  "teal",
  "pink",
  "lime",
  "yellow",
] as const;

export type SidebarGroupTone = (typeof sidebarGroupTones)[number];

const presetGroupTones: Record<string, SidebarGroupTone> = {
  today: "orange",
  "今日": "orange",
  market: "blue",
  "市场": "blue",
  selection: "violet",
  "选股": "violet",
  strategy: "yellow",
  "策略": "yellow",
  industry: "lime",
  "行业": "lime",
  macro: "indigo",
  "宏观": "indigo",
  "宏观面": "indigo",
  intelligence: "red",
  "全球": "red",
  policy: "teal",
  "政策": "teal",
  capital: "green",
  "资金": "green",
  company: "violet",
  "公司": "violet",
  fund: "pink",
  "基金": "pink",
  allocation: "teal",
  "配置": "teal",
  risk: "orange",
  "风险": "orange",
  research: "violet",
  "研究": "violet",
  quant: "cyan",
  "量化": "cyan",
  trading: "red",
  "交易": "red",
  committee: "slate",
  "投决": "slate",
  creator: "pink",
  "创作": "pink",
  deepsee: "green",
  "深瞳": "green",
  settings: "slate",
  "连接与设置": "slate",
};

const customGroupTones: readonly SidebarGroupTone[] = [
  "indigo",
  "teal",
  "pink",
  "lime",
  "yellow",
  "orange",
  "blue",
  "violet",
  "cyan",
  "green",
];

function normalizedGroupLabel(groupLabel: string): string {
  return groupLabel.normalize("NFKC").trim().toLocaleLowerCase();
}

function stableLabelHash(label: string): number {
  let hash = 2166136261;
  for (const character of label) {
    hash ^= character.codePointAt(0) ?? 0;
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

export function sidebarGroupTone(groupLabel: string): SidebarGroupTone {
  const normalizedLabel = normalizedGroupLabel(groupLabel);
  const preset = presetGroupTones[normalizedLabel];
  if (preset) return preset;
  return (
    customGroupTones[stableLabelHash(normalizedLabel) % customGroupTones.length] ??
    "indigo"
  );
}
