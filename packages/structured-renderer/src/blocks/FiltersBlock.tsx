import { useState } from "react";

import type { FiltersBlock as FiltersBlockContract } from "@newma-desk/contracts";

export type FilterValues = Record<string, string>;

interface FiltersBlockProps {
  block: FiltersBlockContract;
  onFiltersChange?: (filters: FilterValues) => void;
}

export function FiltersBlock({ block, onFiltersChange }: FiltersBlockProps) {
  const [filters, setFilters] = useState<FilterValues>({});

  function updateFilter(key: string, value: string) {
    setFilters((current) => {
      const next = { ...current, [key]: value };
      onFiltersChange?.(next);
      return next;
    });
  }

  return (
    <section
      className="vv-view-block vv-filters-block"
      data-block-id={block.id}
      data-vibe-block="filters"
      data-vibe-block-id={block.id}
    >
      <div className="vv-filters">
        {block.fields.map((field) => (
          <label key={field.key}>
            <span>{field.label}</span>
            {field.input === "select" ? (
              <select
                aria-label={field.label}
                onChange={(event) => updateFilter(field.key, event.target.value)}
                value={filters[field.key] ?? ""}
              >
                <option value="">全部</option>
                {field.options?.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            ) : (
              <input
                aria-label={field.label}
                onChange={(event) => updateFilter(field.key, event.target.value)}
                type={field.input}
                value={filters[field.key] ?? ""}
              />
            )}
          </label>
        ))}
      </div>
    </section>
  );
}
