import { useEffect, useRef, useState } from "react";
import { useLocation, useParams, Link } from "react-router-dom";
import { AlertCircle, ArrowLeft, Plus, Wrench } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { GlassCard } from "@/components/ui/GlassCard";
import { IndustryArtifactView } from "@/components/industry/IndustryArtifactView";
import { Disclaimer } from "@/components/ui/Disclaimer";
import {
  createGraphArtifact,
  listGraphArtifacts,
  publishGraphArtifact,
  type ModArtifactRecord,
} from "@/lib/artifacts";
import {
  getVibeDeskConfig,
  publishVibeDeskContext,
  registerVibeDeskContextProvider,
  type VibeDeskPageContext,
  type VibeDeskWikiSubject,
} from "@/lib/vibedesk";
import { getBaseIndustryGraph } from "@/data/industry-graphs";
import sectorsData from "@/data/sectors.json";
import { industrySubject } from "@/lib/wiki";

const baseArtifactRequests = new Map<string, Promise<ModArtifactRecord>>();

function artifactMetadataValue(
  artifact: ModArtifactRecord,
  key: string,
): unknown {
  return artifact.spec.metadata?.[key];
}

async function ensureBaseIndustryArtifact(
  sectorKey: string,
  items: ModArtifactRecord[],
): Promise<ModArtifactRecord | null> {
  const baseSpec = getBaseIndustryGraph(sectorKey);
  const matching = items.filter(
    (item) => artifactMetadataValue(item, "sectorKey") === sectorKey,
  );
  if (!baseSpec) return matching[0] ?? null;

  const baseVersion = baseSpec.metadata?.baseVersion;
  const currentBase = matching.find(
    (item) =>
      artifactMetadataValue(item, "artifactRole") === "base" &&
      artifactMetadataValue(item, "baseVersion") === baseVersion,
  );
  if (currentBase) return matching[0] ?? currentBase;
  if (!getVibeDeskConfig()) return matching[0] ?? null;

  const pending = baseArtifactRequests.get(sectorKey);
  if (pending) return pending;

  const request = createGraphArtifact(baseSpec).then(publishGraphArtifact);
  baseArtifactRequests.set(sectorKey, request);
  try {
    return await request;
  } finally {
    if (baseArtifactRequests.get(sectorKey) === request) {
      baseArtifactRequests.delete(sectorKey);
    }
  }
}

export function SectorDetail() {
  const { key } = useParams();
  const location = useLocation();
  const sector = sectorsData.sectors.find((s) => s.key === key);
  const routeState = location.state as {
    wikiSubject?: VibeDeskWikiSubject;
    wikiConceptIds?: string[];
  } | null;
  const linkedSubject = routeState?.wikiSubject;
  const [artifact, setArtifact] = useState<ModArtifactRecord | null>(null);
  const [artifactError, setArtifactError] = useState<string | null>(null);
  const contextRef = useRef<VibeDeskPageContext>({
    view: { id: "industry-map", title: "产业链研究" },
    visibleBlocks: [],
    selection: {},
    filters: {},
    data: { source: "vibe-research-industry-map", freshness: "fresh" },
    actions: [],
    tasks: [],
  });

  if (sector) {
    const selectedIndustry = industrySubject(sector.key, sector.label);
    contextRef.current = {
      view: { id: "industry-map", title: `${sector.label}产业链` },
      visibleBlocks: [
        { id: "industry-graph", type: "relationship-graph", title: `${sector.label}产业链图谱` },
        { id: "industry-stages", type: "industry-stages", title: "核心环节" },
      ],
      selection: { sectorKey: sector.key, sector: sector.label, linkedSubject: linkedSubject ?? null },
      filters: {},
      data: {
        asOf: new Date().toISOString(),
        source: "vibe-research-industry-map",
        freshness: artifactError ? "stale" : artifact ? "fresh" : "unknown",
        summary: { verified: sector.verified, stageCount: sector.nodes.length },
      },
      actions: [],
      wiki: {
        primarySubject: linkedSubject ?? selectedIndustry,
        relatedSubjects: linkedSubject ? [selectedIndustry] : [],
        conceptIds: routeState?.wikiConceptIds?.length
          ? routeState.wikiConceptIds
          : [`concept:CN:${sector.key}`],
        intent: "industry.chain",
        snapshotId: `industry-map:${sector.key}`,
      },
      tasks: [],
    };
  }

  useEffect(() => registerVibeDeskContextProvider(() => contextRef.current), []);
  useEffect(() => { void publishVibeDeskContext(); }, [artifact, artifactError, linkedSubject, sector?.key]);

  useEffect(() => {
    let active = true;
    setArtifact(null);
    setArtifactError(null);
    if (!sector) return () => { active = false; };
    void listGraphArtifacts()
      .then(async (items) => {
        if (!active) return;
        const matching = await ensureBaseIndustryArtifact(sector.key, items);
        if (active) setArtifact(matching);
      })
      .catch((cause) => {
        if (active) setArtifactError(cause instanceof Error ? cause.message : "读取产业链图谱失败");
      });
    return () => { active = false; };
  }, [sector?.key]);

  if (!sector) {
    return (
      <div className="py-20 text-center text-muted-foreground">
        未找到该板块。<Link to="/sectors" className="text-primary">返回板块中心</Link>
      </div>
    );
  }

  return (
    <div>
      <Link to="/sectors" className="mb-3 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-4 w-4" /> 板块中心
      </Link>

      <PageHeader
        title={sector.label}
        subtitle={sector.tagline}
      />

      {artifactError && (
        <div className="mb-6 flex items-center gap-2 rounded-xl border border-destructive/25 bg-destructive/5 px-4 py-3 text-xs text-destructive">
          <AlertCircle className="h-4 w-4 shrink-0" /> {artifactError}
        </div>
      )}

      {artifact && (
        <IndustryArtifactView artifact={artifact} onChange={setArtifact} />
      )}

      {sector.verified ? (
        <div>
          <h3 className="mb-3 text-sm font-semibold text-muted-foreground">核心环节（{sector.nodes.length}）</h3>
          <div className="flex flex-wrap gap-2.5">
            {sector.nodes.map((n) => (
              <span key={n} className="rounded-full border border-primary/40 bg-primary/15 px-3.5 py-1.5 text-sm font-medium text-foreground shadow-glow transition-colors hover:bg-primary/25">
                {n}
              </span>
            ))}
          </div>
          <p className="mt-4 flex items-center gap-1.5 text-xs text-muted-foreground">
            <Plus className="h-3.5 w-3.5" /> 想在某个环节挂上自己关注的标的？数据存在你本地，不会上传、不进仓库。
          </p>
        </div>
      ) : (
        <GlassCard>
          <div className="flex flex-col items-center gap-3 py-8 text-center">
            <Wrench className="h-8 w-8 text-muted-foreground/50" />
            <p className="text-sm text-muted-foreground">
              该板块的环节骨架尚在<b className="text-foreground">实时核实</b>补全中（不靠模型记忆）——已核实的板块见左侧。
            </p>
            <p className="max-w-md text-xs text-muted-foreground/70">
              可以使用 VibeDesk 右上角「问当前 Mod」，让统一 Agent 按七维框架梳理并修改产业链基础图谱。
            </p>
          </div>
        </GlassCard>
      )}

      <Disclaimer />
    </div>
  );
}
