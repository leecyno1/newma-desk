import {
  BarChart3,
  Binary,
  BookOpenText,
  Boxes,
  RefreshCw,
} from "lucide-react";

import type { StoredMod } from "../api/modules";

interface SidebarProps {
  modules: StoredMod[];
  selectedId: string | undefined;
  onSelect: (mod: StoredMod) => void;
  onReload: () => void;
  loading: boolean;
}

const categoryIcons = {
  research: BookOpenText,
  market: BarChart3,
  quant: Binary,
  module: Boxes,
} as const;

const legacyNavigation = {
  research: {
    groupLabel: "研究",
    groupOrder: 0,
    itemOrder: 100,
    icon: "research" as const,
  },
  market: {
    groupLabel: "市场",
    groupOrder: 10,
    itemOrder: 100,
    icon: "market" as const,
  },
  quant: {
    groupLabel: "量化",
    groupOrder: 20,
    itemOrder: 100,
    icon: "quant" as const,
  },
};

function navigationFor(module: StoredMod) {
  return (
    module.manifest.navigation ?? {
      ...(legacyNavigation[
        module.manifest.category as keyof typeof legacyNavigation
      ] ?? {
        groupLabel: module.manifest.category,
        groupOrder: 100,
        itemOrder: 100,
        icon: "module" as const,
      }),
    }
  );
}

function groupedModules(modules: StoredMod[]) {
  const groups = new Map<string, StoredMod[]>();

  for (const module of modules) {
    const group = groups.get(module.manifest.category) ?? [];
    group.push(module);
    groups.set(module.manifest.category, group);
  }

  return [...groups.entries()]
    .map(([category, categoryModules]) => {
      const sortedModules = [...categoryModules].sort((left, right) => {
        const orderDifference =
          navigationFor(left).itemOrder - navigationFor(right).itemOrder;
        return orderDifference || left.moduleId.localeCompare(right.moduleId);
      });
      const representative = [...sortedModules].sort((left, right) => {
        const groupDifference =
          navigationFor(left).groupOrder - navigationFor(right).groupOrder;
        if (groupDifference) return groupDifference;
        const itemDifference =
          navigationFor(left).itemOrder - navigationFor(right).itemOrder;
        return itemDifference || left.moduleId.localeCompare(right.moduleId);
      })[0];
      const navigation = representative
        ? navigationFor(representative)
        : {
            groupLabel: category,
            groupOrder: 100,
            itemOrder: 100,
            icon: "module" as const,
          };

      return {
        category,
        label: navigation.groupLabel,
        order: navigation.groupOrder,
        icon: navigation.icon,
        modules: sortedModules,
      };
    })
    .sort((left, right) => {
      const orderDifference = left.order - right.order;
      return orderDifference || left.category.localeCompare(right.category);
    });
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
          <strong>VibeDesk</strong>
          <small>智能模组工作台</small>
        </span>
      </div>
      <nav aria-label="VibeDesk Mod 导航" className="module-nav">
        {groupedModules(modules).map(
          ({ category, icon, label, modules: group }) => {
          const Icon = categoryIcons[icon] ?? Boxes;
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
          },
        )}
      </nav>
      <button
        className="reload-button"
        type="button"
        onClick={onReload}
        disabled={loading}
      >
        <RefreshCw size={15} aria-hidden="true" />
        {loading ? "正在加载" : "重新加载 Mod"}
      </button>
    </aside>
  );
}
