import type { MetricsBlock as MetricsBlockContract } from "@vibe-visualization/contracts";

import { formatValue } from "../formatValue";
import { resolvePath } from "../resolvePath";

interface MetricsBlockProps {
  block: MetricsBlockContract;
  data: unknown;
}

export function MetricsBlock({ block, data }: MetricsBlockProps) {
  return (
    <section
      className="vv-view-block vv-metrics-block"
      data-block-id={block.id}
      data-vibe-block="metrics"
      data-vibe-block-id={block.id}
    >
      {block.title ? <h2>{block.title}</h2> : null}
      <dl className="vv-metrics">
        {block.items.map((item) => (
          <div
            className="vv-metric"
            data-vibe-value-path={item.valuePath}
            key={`${item.label}:${item.valuePath}`}
          >
            <dt>{item.label}</dt>
            <dd>{formatValue(resolvePath(data, item.valuePath), item.format)}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
