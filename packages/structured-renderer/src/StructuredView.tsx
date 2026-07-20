import type { View } from "@vibe-visualization/contracts";

import { ActionsBlock, type ActionHandler } from "./blocks/ActionsBlock";
import { ChartBlock } from "./blocks/ChartBlock";
import {
  FiltersBlock,
  type FilterValues,
} from "./blocks/FiltersBlock";
import { MarkdownBlock } from "./blocks/MarkdownBlock";
import { MetricsBlock } from "./blocks/MetricsBlock";
import { TableBlock } from "./blocks/TableBlock";

export interface StructuredViewProps {
  schema: View;
  data: unknown;
  onAction?: ActionHandler;
  onFiltersChange?: (filters: FilterValues) => void;
}

export function StructuredView({
  schema,
  data,
  onAction,
  onFiltersChange,
}: StructuredViewProps) {
  return (
    <main className="vv-structured-view">
      <h1>{schema.title}</h1>
      {schema.blocks.map((block) => {
        switch (block.type) {
          case "metrics":
            return <MetricsBlock block={block} data={data} key={block.id} />;
          case "table":
            return <TableBlock block={block} data={data} key={block.id} />;
          case "chart":
            return <ChartBlock block={block} data={data} key={block.id} />;
          case "markdown":
            return <MarkdownBlock block={block} data={data} key={block.id} />;
          case "filters":
            return (
              <FiltersBlock
                block={block}
                key={block.id}
                onFiltersChange={onFiltersChange}
              />
            );
          case "actions":
            return <ActionsBlock block={block} key={block.id} onAction={onAction} />;
        }
      })}
    </main>
  );
}
