import {
  BarChart3,
  Binary,
  BookOpenText,
  Boxes,
  CalendarDays,
  CandlestickChart,
  Bot,
  Palette,
  RefreshCw,
  Settings,
  Store,
} from "lucide-react";

import type { StoredMod } from "../api/modules";
import { navigationFor } from "../lib/workspacePreferences";

interface SidebarProps {
  modules: StoredMod[];
  selectedId: string | undefined;
  onSelect: (mod: StoredMod) => void;
  onReload: () => void;
  loading: boolean;
  agentSettingsActive: boolean;
  onOpenAgentSettings: () => void;
  interfaceSettingsActive: boolean;
  onOpenInterfaceSettings: () => void;
  storeActive: boolean;
  onOpenStore: () => void;
  categoryOverrides: Record<string, string>;
}

const categoryIcons = {
  today: CalendarDays,
  research: BookOpenText,
  market: BarChart3,
  quant: Binary,
  trading: CandlestickChart,
  settings: Settings,
  module: Boxes,
} as const;

function groupedModules(
  modules: StoredMod[],
  categoryOverrides: Record<string, string>,
) {
  const groups = new Map<string, StoredMod[]>();

  for (const module of modules) {
    const customLabel = categoryOverrides[module.moduleId]?.trim();
    const groupKey = customLabel || navigationFor(module).groupLabel;
    const group = groups.get(groupKey) ?? [];
    group.push(module);
    groups.set(groupKey, group);
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
        label: category,
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
  agentSettingsActive,
  onOpenAgentSettings,
  interfaceSettingsActive,
  onOpenInterfaceSettings,
  storeActive,
  onOpenStore,
  categoryOverrides,
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
        {groupedModules(modules, categoryOverrides).map(
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
      <div className="sidebar-tools">
        <button
          className="sidebar-tool-button"
          type="button"
          onClick={onOpenStore}
          aria-current={storeActive ? "page" : undefined}
        >
          <Store size={15} aria-hidden="true" />
          Mod 商店
        </button>
        <button
          className="sidebar-tool-button"
          type="button"
          onClick={onOpenInterfaceSettings}
          aria-current={interfaceSettingsActive ? "page" : undefined}
        >
          <Palette size={15} aria-hidden="true" />
          界面设置
        </button>
        <button
          className="sidebar-tool-button"
          type="button"
          onClick={onOpenAgentSettings}
          aria-current={agentSettingsActive ? "page" : undefined}
        >
          <Bot size={15} aria-hidden="true" />
          Agent 设置
        </button>
      </div>
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
