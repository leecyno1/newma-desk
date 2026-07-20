import {
  BarChart3,
  Binary,
  BookOpenText,
  Boxes,
  RefreshCw,
} from "lucide-react";

import type { StoredModule } from "../api/modules";

interface SidebarProps {
  modules: StoredModule[];
  selectedId: string | undefined;
  onSelect: (module: StoredModule) => void;
  onReload: () => void;
  loading: boolean;
}

const categoryLabels: Record<string, string> = {
  research: "研究",
  market: "市场",
  quant: "量化",
};

const categoryOrder: Record<string, number> = {
  research: 0,
  market: 1,
  quant: 2,
};

const categoryIcons = {
  research: BookOpenText,
  market: BarChart3,
  quant: Binary,
} as const;

function groupedModules(modules: StoredModule[]) {
  const groups = new Map<string, StoredModule[]>();

  for (const module of modules) {
    const group = groups.get(module.manifest.category) ?? [];
    group.push(module);
    groups.set(module.manifest.category, group);
  }

  return [...groups.entries()]
    .sort(([left], [right]) => {
      const orderDifference =
        (categoryOrder[left] ?? Number.MAX_SAFE_INTEGER) -
        (categoryOrder[right] ?? Number.MAX_SAFE_INTEGER);
      return orderDifference || left.localeCompare(right);
    })
    .map(([category, categoryModules]) => ({
      category,
      modules: [...categoryModules].sort((left, right) =>
        left.moduleId.localeCompare(right.moduleId),
      ),
    }));
}

export function Sidebar({
  modules,
  selectedId,
  onSelect,
  onReload,
  loading,
}: SidebarProps) {
  return (
    <aside className="sidebar">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true">
          <Boxes size={20} />
        </span>
        <span>
          <strong>Vibe</strong>
          <small>Research Shell</small>
        </span>
      </div>
      <nav aria-label="研究模块" className="module-nav">
        {groupedModules(modules).map(({ category, modules: group }) => {
          const label = categoryLabels[category] ?? category;
          const Icon =
            categoryIcons[category as keyof typeof categoryIcons] ?? Boxes;
          const headingId = `category-${category}`;

          return (
            <section
              className="module-group"
              role="group"
              aria-labelledby={headingId}
              key={category}
            >
              <h2 id={headingId}>
                <Icon size={14} aria-hidden="true" />
                {label}
              </h2>
              {group.map((module) => (
                <button
                  className="module-button"
                  type="button"
                  key={`${module.moduleId}@${module.revision}`}
                  aria-current={
                    module.moduleId === selectedId ? "page" : undefined
                  }
                  onClick={() => onSelect(module)}
                >
                  {module.manifest.name}
                </button>
              ))}
            </section>
          );
        })}
      </nav>
      <button
        className="reload-button"
        type="button"
        onClick={onReload}
        disabled={loading}
      >
        <RefreshCw size={15} aria-hidden="true" />
        {loading ? "正在加载" : "重新加载模块"}
      </button>
    </aside>
  );
}
