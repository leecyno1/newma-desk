import type {
  ArtifactNodeKind,
  GraphArtifactInput,
  GraphArtifactNode,
} from "@/lib/artifacts";

interface IndustryStage {
  label: string;
  items: string[];
}

const MARKDOWN_MARKS = /[*_`#]/g;
const TREE_BRANCH = /^[\s│]*(?:├|└|┣|┗)[─━-]?\s*(.+)$/;
const ARROW = /\s*(?:→|➜|➡|->|=>)\s*/;

function cleanLabel(value: string): string {
  return value
    .replace(MARKDOWN_MARKS, "")
    .replace(/^\s*(?:\d+[.、]|[-+•])\s*/, "")
    .replace(/[：:]\s*$/, "")
    .trim();
}

function nodeKind(label: string): ArtifactNodeKind {
  if (/需求|客户|应用|下游|市场/.test(label)) return "market";
  if (/材料|设备|晶圆|存储|HBM|封装|载板|铜箔/.test(label)) return "material";
  if (/光|互连|散热|液冷|电源|机柜|IDC|中心|基建/.test(label)) return "infrastructure";
  if (/风险|瓶颈|卡脖子/.test(label)) return "risk";
  if (/公司|厂商|企业|标的/.test(label)) return "company";
  if (/需求|资本开支|政策/.test(label)) return "source";
  return "component";
}

function codeBlocks(answer: string): string[] {
  return [...answer.matchAll(/```(?:text|txt|plaintext)?\s*\n([\s\S]*?)```/gi)]
    .map((match) => match[1].trim())
    .filter(Boolean);
}

function parseTreeStages(answer: string): IndustryStage[] {
  const candidates = [...codeBlocks(answer), answer];
  let best: IndustryStage[] = [];

  for (const candidate of candidates) {
    const stages: IndustryStage[] = [];
    let current: IndustryStage | null = null;
    for (const rawLine of candidate.split(/\r?\n/)) {
      const line = rawLine.trimEnd();
      if (!line.trim() || /^\s*[↓⇩]+\s*$/.test(line)) continue;
      const branch = line.match(TREE_BRANCH);
      if (branch) {
        const item = cleanLabel(branch[1]);
        if (current && item) current.items.push(item);
        continue;
      }
      if (/^[\s│]+/.test(rawLine)) continue;
      const label = cleanLabel(line);
      if (
        !label ||
        label.length > 32 ||
        /^(一|二|三|四|五|六|七|八|九|十)[、.]/.test(label) ||
        /产业链(全景|地图|图谱)/.test(label) ||
        label.includes("→")
      ) {
        continue;
      }
      current = { label, items: [] };
      stages.push(current);
    }
    const meaningful = stages.filter((stage) => stage.items.length > 0);
    if (meaningful.length > best.length) best = meaningful;
  }
  return best;
}

function parseArrowChain(answer: string): IndustryStage[] {
  const candidates = answer
    .split(/\r?\n/)
    .filter((line) => (line.match(/→|➜|➡|->|=>/g) || []).length >= 2)
    .map((line) => line.replace(/^.*?(?:是|为|：|:)\s*/, ""));
  if (!candidates.length) return [];
  const longest = candidates.sort((a, b) => b.split(ARROW).length - a.split(ARROW).length)[0];
  return longest
    .split(ARROW)
    .map(cleanLabel)
    .filter((label) => label.length > 0 && label.length <= 40)
    .slice(0, 12)
    .map((label) => ({ label, items: [] }));
}

function stagesToNodes(stages: IndustryStage[]): GraphArtifactNode[] {
  return stages.map((stage, index) => ({
    id: `stage-${index + 1}`,
    label: stage.label,
    subtitle: stage.items.join(" · "),
    kind: nodeKind(`${stage.label} ${stage.items.join(" ")}`),
    group: `第 ${index + 1} 环节`,
  }));
}

export function industryAnswerToArtifact(
  answer: string,
  options: { sectorLabel: string; sectorKey: string; question: string },
): GraphArtifactInput | null {
  const treeStages = parseTreeStages(answer);
  const stages = treeStages.length >= 2 ? treeStages : parseArrowChain(answer);
  if (stages.length < 2) return null;
  const nodes = stagesToNodes(stages);
  return {
    moduleId: "industry-map",
    title: `${options.sectorLabel}产业链图谱`,
    subtitle: "Agent 生成 · VibeDesk Artifact · Archify 可视化",
    nodes,
    edges: nodes.slice(1).map((node, index) => ({
      source: nodes[index].id,
      target: node.id,
      label: index === 0 ? "需求 / 供给传导" : "产业链传导",
      kind: "flow" as const,
    })),
    sourceText: answer,
    sources: ["VibeDesk Agent 本页回答"],
    metadata: {
      sectorKey: options.sectorKey,
      question: options.question,
      extraction: treeStages.length >= 2 ? "text-tree" : "arrow-chain",
    },
  };
}
