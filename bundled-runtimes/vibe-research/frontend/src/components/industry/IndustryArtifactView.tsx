import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Archive, Check, ExternalLink, FileText, Loader2, Network, Table2 } from "lucide-react";
import type { ModArtifactRecord } from "@/lib/artifacts";
import { publishGraphArtifact } from "@/lib/artifacts";
import { GlassCard } from "@/components/ui/GlassCard";
import { cn } from "@/lib/utils";

interface Props {
  artifact: ModArtifactRecord;
  onChange?: (artifact: ModArtifactRecord) => void;
}

type Tab = "graph" | "data" | "source";

function defaultTab(): Tab {
  return window.matchMedia?.("(max-width: 639px)").matches ? "data" : "graph";
}

function currentTheme(): "light" | "dark" {
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

const ARTIFACT_THEME_VARIABLES = [
  "--vibe-bg",
  "--vibe-surface",
  "--vibe-surface-muted",
  "--vibe-surface-raised",
  "--vibe-surface-selected",
  "--vibe-border",
  "--vibe-border-strong",
  "--vibe-text",
  "--vibe-text-muted",
  "--vibe-text-faint",
  "--vibe-accent",
  "--vibe-error",
  "--vibe-chart-series-1",
  "--vibe-chart-series-2",
  "--vibe-chart-series-3",
  "--vibe-chart-series-4",
  "--vibe-chart-series-5",
] as const;

export function IndustryArtifactView({ artifact, onChange }: Props) {
  const [tab, setTab] = useState<Tab>(defaultTab);
  const [theme, setTheme] = useState(currentTheme);
  const [initialTheme] = useState(currentTheme);
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const graphFrameRef = useRef<HTMLIFrameElement>(null);
  const isBaseArtifact = artifact.spec.metadata?.artifactRole === "base";
  const viewUrl = useMemo(() => {
    const url = new URL(artifact.viewUrl);
    url.searchParams.set("theme", initialTheme);
    url.searchParams.set("newmaTheme", "1");
    return url.toString();
  }, [artifact.viewUrl, initialTheme]);

  const syncGraphTheme = useCallback(() => {
    const target = graphFrameRef.current?.contentWindow;
    if (!target) return;
    const styles = getComputedStyle(document.documentElement);
    const cssVars = Object.fromEntries(
      ARTIFACT_THEME_VARIABLES.map((name) => [name, styles.getPropertyValue(name).trim()])
        .filter((entry) => entry[1]),
    );
    target.postMessage({ type: "newma:artifact-theme", mode: theme, cssVars }, "*");
  }, [theme]);

  useEffect(() => {
    const observer = new MutationObserver(() => setTheme(currentTheme()));
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    const onTheme = () => setTheme(currentTheme());
    window.addEventListener("vibedesk:theme", onTheme);
    window.addEventListener("newma:themechange", onTheme);
    return () => {
      observer.disconnect();
      window.removeEventListener("vibedesk:theme", onTheme);
      window.removeEventListener("newma:themechange", onTheme);
    };
  }, []);

  useEffect(syncGraphTheme, [syncGraphTheme]);

  const publish = async () => {
    if (publishing || artifact.status === "published") return;
    setPublishing(true);
    setError(null);
    try {
      onChange?.(await publishGraphArtifact(artifact));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "图谱发布失败");
    } finally {
      setPublishing(false);
    }
  };

  return (
    <GlassCard className="mb-6 overflow-hidden p-0" data-vibe-artifact="industry-graph">
      <div className="flex flex-col gap-3 border-b border-border/60 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="text-base font-semibold text-foreground">{artifact.title}</h2>
            <span className={cn(
              "rounded-full px-2 py-0.5 text-[10px] font-medium",
              artifact.status === "published"
                ? "bg-success/10 text-success"
                : "bg-warning/10 text-warning",
            )}>
              {artifact.status === "published" ? "已固化" : "草稿"}
            </span>
            <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] text-primary">Archify</span>
            {isBaseArtifact && (
              <span className="rounded-full border border-primary/20 bg-primary/10 px-2 py-0.5 text-[10px] text-primary">
                基础图谱
              </span>
            )}
          </div>
          <p className="mt-1 text-xs text-muted-foreground">
            {artifact.spec.nodes.length} 个节点 · {artifact.spec.edges.length} 条关系 · 可交互查看路径
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {artifact.status === "draft" ? (
            <button
              type="button"
              onClick={publish}
              disabled={publishing}
              className="inline-flex items-center gap-1.5 rounded-lg bg-primary/15 px-3 py-1.5 text-xs font-medium text-primary hover:bg-primary/25 disabled:opacity-50"
            >
              {publishing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Archive className="h-3.5 w-3.5" />}
              固化为版本
            </button>
          ) : (
            <span className="inline-flex items-center gap-1 text-xs text-success">
              <Check className="h-3.5 w-3.5" /> 已保存，刷新后仍可恢复
            </span>
          )}
          <a
            href={viewUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground"
          >
            <ExternalLink className="h-3.5 w-3.5" /> 独立查看
          </a>
        </div>
      </div>

      <div className="flex gap-1 border-b border-border/60 px-3 py-2" role="tablist" aria-label="产业链图谱视图">
        {([
          ["graph", "关系图", Network],
          ["data", "节点与关系", Table2],
          ["source", "研究原文", FileText],
        ] as const).map(([value, label, Icon]) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={tab === value}
            onClick={() => setTab(value)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs transition-colors",
              tab === value ? "bg-primary/12 text-primary" : "text-muted-foreground hover:text-foreground",
            )}
          >
            <Icon className="h-3.5 w-3.5" /> {label}
          </button>
        ))}
      </div>

      {error && <p className="border-b border-destructive/20 bg-destructive/5 px-4 py-2 text-xs text-destructive">{error}</p>}

      {tab === "graph" && (
        <div className="bg-background/60 p-2 sm:p-3">
          <iframe
            ref={graphFrameRef}
            src={viewUrl}
            title={`${artifact.title} Archify 关系图`}
            className="h-[500px] w-full rounded-xl border border-border bg-background sm:h-[620px]"
            sandbox="allow-scripts allow-downloads"
            loading="lazy"
            onLoad={syncGraphTheme}
          />
          <p className="px-1 pt-2 text-[11px] text-muted-foreground">
            图谱来自结构化节点和关系，不是文本截图；可在图中搜索、缩放、聚焦路径并导出。
          </p>
        </div>
      )}

      {tab === "data" && (
        <div className="overflow-x-auto p-3 sm:p-4">
          <table className="w-full min-w-[620px] text-left text-xs">
            <thead className="text-muted-foreground">
              <tr className="border-b border-border">
                <th className="px-2 py-2 font-medium">环节</th>
                <th className="px-2 py-2 font-medium">范围 / 子环节</th>
                <th className="px-2 py-2 font-medium">关系与连接</th>
              </tr>
            </thead>
            <tbody>
              {artifact.spec.nodes.map((node) => (
                <tr key={node.id} className="border-b border-border/50 align-top last:border-0">
                  <th className="px-2 py-2.5 font-medium text-foreground">{node.label}</th>
                  <td className="px-2 py-2.5 text-muted-foreground">{node.subtitle || "—"}</td>
                  <td className="px-2 py-2.5 text-muted-foreground">
                    {artifact.spec.edges
                      .filter((edge) => edge.source === node.id)
                      .map((edge) => {
                        const target = artifact.spec.nodes.find((item) => item.id === edge.target)?.label;
                        if (!target) return null;
                        return edge.label ? `${target}（${edge.label}）` : target;
                      })
                      .filter(Boolean)
                      .join("、") || "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === "source" && (
        <pre className="max-h-[620px] overflow-auto whitespace-pre-wrap p-4 text-xs leading-6 text-muted-foreground">
          {artifact.spec.sourceText || "没有保存研究原文。"}
        </pre>
      )}
    </GlassCard>
  );
}
