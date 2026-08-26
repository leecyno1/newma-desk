import sectorsData from "@/data/sectors.json";
import type {
  VibeDeskWikiHandoff,
  VibeDeskWikiSubject,
} from "@/lib/vibedesk";

const SECTOR_ALIASES: Record<string, string[]> = {
  humanoid: ["人形机器人", "具身智能", "机器人"],
  "ai-computing": ["ai算力", "算力", "数据中心"],
  hbm: ["hbm", "高带宽存储"],
  cpo: ["cpo", "lpo", "光模块", "光互联", "光通信"],
  semiconductor: ["半导体", "芯片", "国产替代"],
  "solid-state-battery": ["固态电池"],
  "low-altitude": ["低空经济", "evtol"],
  "smart-driving": ["智能驾驶", "自动驾驶"],
  "innovative-drug": ["创新药", "cxO"],
  "power-grid": ["电网", "特高压"],
  defense: ["军工", "国防"],
  fusion: ["核聚变", "可控核聚变"],
  "business-space": ["商业航天", "卫星", "火箭"],
  "ai-pharma": ["生物医药", "ai制药"],
  resources: ["稀土", "锗", "铟", "资源卡口"],
  "ai-application": ["ai应用", "agent"],
  "ai-hardware": ["ai硬件", "ai眼镜", "端侧"],
  "energy-storage": ["储能"],
  "data-element": ["数据要素"],
};

function normalized(value: string) {
  return value.toLocaleLowerCase("zh-CN").replace(/[\s·/_-]+/g, "");
}

export function sectorKeysForLabels(labels: string[]): string[] {
  const keys: string[] = [];
  for (const label of labels.map(normalized).filter(Boolean)) {
    const matches = sectorsData.sectors
      .map((sector) => {
        const aliases = [sector.key, sector.label, ...(SECTOR_ALIASES[sector.key] ?? [])]
          .map(normalized);
        const score = Math.max(
          0,
          ...aliases.map((alias) =>
            label === alias ? 10_000 + alias.length
              : label.includes(alias) || alias.includes(label) ? alias.length
                : 0,
          ),
        );
        return { key: sector.key, score };
      })
      .filter((match) => match.score > 0)
      .sort((left, right) => right.score - left.score);
    for (const match of matches) {
      if (!keys.includes(match.key)) keys.push(match.key);
    }
  }
  return keys;
}

export function conceptIdsForLabels(labels: string[]): string[] {
  return sectorKeysForLabels(labels).map((key) => `concept:CN:${key}`);
}

export function sectorKeyFromWikiHandoff(
  handoff: VibeDeskWikiHandoff,
): string | undefined {
  const available = new Set(sectorsData.sectors.map((sector) => sector.key));
  const canonicalIds = [
    ...handoff.conceptIds,
    ...handoff.relatedSubjects
      .filter((subject) => subject.type === "industry" || subject.type === "concept")
      .map((subject) => subject.canonicalId),
  ];
  for (const canonicalId of canonicalIds) {
    const parts = canonicalId.split(":");
    const key = decodeURIComponent(parts[parts.length - 1] ?? "");
    if (available.has(key)) return key;
  }
  return sectorKeysForLabels([
    handoff.subject.displayName,
    ...handoff.relatedSubjects.map((subject) => subject.displayName),
  ])[0];
}

export function industrySubject(key: string, label: string): VibeDeskWikiSubject {
  return {
    type: "industry",
    canonicalId: `industry:CN:${key}`,
    displayName: label,
    market: "CN",
  };
}
