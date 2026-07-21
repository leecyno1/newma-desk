import type { View } from "@vibedesk/contracts";

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
  onRowSelect?: (blockId: string, row: Record<string, unknown>) => void;
}

export function StructuredView({
  schema,
  data,
  onAction,
  onFiltersChange,
  onRowSelect,
}: StructuredViewProps) {
  return (
    <main
      className="vv-structured-view"
      data-vibe-page="1.0"
      data-vibe-title={schema.title}
    >
      <h1>{schema.title}</h1>
      {schema.blocks.map((block) => {
        switch (block.type) {
          case "metrics":
            return <MetricsBlock block={block} data={data} key={block.id} />;
          case "table":
            return (
              <TableBlock
                block={block}
                data={data}
                key={block.id}
                onRowSelect={onRowSelect}
              />
            );
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
