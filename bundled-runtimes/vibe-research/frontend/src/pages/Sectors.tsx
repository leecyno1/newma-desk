import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Flame, ChevronRight } from "lucide-react";
import { PageHeader } from "@/components/ui/PageHeader";
import { GlassCard } from "@/components/ui/GlassCard";
import { Disclaimer } from "@/components/ui/Disclaimer";
import sectorsData from "@/data/sectors.json";
import { api } from "@/lib/api";
import {
  publishVibeDeskContext,
  registerVibeDeskContextProvider,
  registerVibeDeskHandoffHandler,
  type VibeDeskPageContext,
  type VibeDeskWikiSubject,
} from "@/lib/vibedesk";
import {
  conceptIdsForLabels,
  sectorKeyFromWikiHandoff,
} from "@/lib/wiki";

export function Sectors() {
  const sectors = sectorsData.sectors;
  const hotCount = sectors.filter((s) => s.hot).length;
  const navigate = useNavigate();
  const [linkedSubject, setLinkedSubject] = useState<VibeDeskWikiSubject>();
  const contextRef = useRef<VibeDeskPageContext>({
    view: { id: "industry-map", title: "产业链研究" },
    visibleBlocks: [],
    selection: {},
    filters: {},
    data: { source: "vibe-research-industry-map", freshness: "fresh" },
    actions: [],
    tasks: [],
  });

  contextRef.current = {
    view: { id: "industry-map", title: "产业链研究" },
    visibleBlocks: [{ id: "industry-sectors", type: "industry-list", title: "产业链板块" }],
    selection: linkedSubject ? { linkedSubject } : {},
    filters: {},
    data: {
      asOf: new Date().toISOString(),
      source: "vibe-research-industry-map",
      freshness: "fresh",
      summary: { sectorCount: sectors.length },
    },
    actions: [],
    ...(linkedSubject ? {
      wiki: {
        primarySubject: linkedSubject,
        relatedSubjects: [],
        conceptIds: [],
        intent: "industry.chain",
      },
    } : {}),
    tasks: [],
  };

  useEffect(() => registerVibeDeskContextProvider(() => contextRef.current), []);
  useEffect(() => registerVibeDeskHandoffHandler(async (handoff) => {
    if (!["security", "industry", "concept"].includes(handoff.subject.type)) {
      throw new Error("产业链研究不支持该 Wiki 对象");
    }
    setLinkedSubject(handoff.subject);
    let sectorKey = sectorKeyFromWikiHandoff(handoff);
    let conceptIds = handoff.conceptIds;
    if (
      !sectorKey &&
      handoff.subject.type === "security" &&
      handoff.subject.market === "CN" &&
      handoff.subject.symbol
    ) {
      const [blocks, hotConcepts] = await Promise.all([
        api.blocks(handoff.subject.symbol).catch(() => null),
        api.hotConcepts(handoff.subject.symbol).catch(() => []),
      ]);
      conceptIds = conceptIdsForLabels([
        ...(blocks?.concept_tags ?? []),
        ...hotConcepts.map((item) => item.concept),
      ]);
      const firstConceptParts = conceptIds[0]?.split(":") ?? [];
      sectorKey = firstConceptParts[firstConceptParts.length - 1];
    }
    if (sectorKey && sectors.some((sector) => sector.key === sectorKey)) {
      navigate(`/sectors/${sectorKey}`, {
        state: { wikiSubject: handoff.subject, wikiConceptIds: conceptIds },
      });
    }
    return { selected: handoff.subject.canonicalId, sectorKey: sectorKey ?? null };
  }), [navigate, sectors]);
  useEffect(() => { void publishVibeDeskContext(); }, [linkedSubject]);

  return (
    <div>
      <PageHeader
        title="板块中心"
        subtitle={`${sectors.length} 个热门赛道的产业链骨架 · 只有环节，不含标的`}
      />

      {linkedSubject && (
        <p className="mb-4 text-xs text-muted-foreground">
          当前关联：<b className="text-foreground">{linkedSubject.displayName}</b>
        </p>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {sectors.map((s) => (
          <Link key={s.key} to={`/sectors/${s.key}`}>
            <GlassCard glow={s.hot} className="flex h-full flex-col justify-between">
              <div>
                <div className="mb-1 flex items-center gap-2">
                  <h3 className="text-base font-bold">{s.label}</h3>
                  {s.hot && (
                    <span className="inline-flex items-center gap-0.5 rounded-full bg-accent/15 px-1.5 py-0.5 text-[10px] font-medium text-accent">
                      <Flame className="h-3 w-3" /> 热门
                    </span>
                  )}
                </div>
                <p className="text-xs leading-relaxed text-muted-foreground">{s.tagline}</p>
              </div>
              <div className="mt-3 flex items-center justify-between border-t border-border/50 pt-3 text-xs">
                <span className="text-muted-foreground">
                  {s.verified ? `${s.nodes.length} 个环节` : "环节梳理中"}
                </span>
                <ChevronRight className="h-4 w-4 text-primary" />
              </div>
            </GlassCard>
          </Link>
        ))}
      </div>

      <p className="mt-4 text-center text-xs text-muted-foreground/60">
        共 {sectors.length} 个板块，其中 {hotCount} 个热门 · 环节持续实时核实补全
      </p>
      <Disclaimer />
    </div>
  );
}
