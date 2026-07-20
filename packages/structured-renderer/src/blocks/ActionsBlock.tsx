import type { ActionsBlock as ActionsBlockContract } from "@vibe-visualization/contracts";

export type ActionHandler = (
  capability: string,
  payload: Record<string, unknown>,
) => void;

interface ActionsBlockProps {
  block: ActionsBlockContract;
  onAction?: ActionHandler;
}

export function ActionsBlock({ block, onAction }: ActionsBlockProps) {
  function invokeAction(item: ActionsBlockContract["items"][number]) {
    if (item.confirmation && !window.confirm(item.confirmation)) return;
    onAction?.(item.capability, {});
  }

  return (
    <section className="vv-view-block vv-actions-block" data-block-id={block.id}>
      <div className="vv-actions">
        {block.items.map((item) => (
          <button key={item.id} onClick={() => invokeAction(item)} type="button">
            {item.label}
          </button>
        ))}
      </div>
    </section>
  );
}
