import type { ModPageContext } from "@newma-desk/contracts";

// Keep one page's writes ordered, including session acquisition and renewal.
// Otherwise a delayed loading snapshot can overwrite its completed evidence.
export function createContextWriter(save: (context: ModPageContext) => Promise<void>) {
  let pending = Promise.resolve();
  let closed = false;
  let revision = 0;
  return {
    write(context: ModPageContext) {
      const current = ++revision;
      // Rapid page changes only need the newest waiting snapshot.
      const result = pending.then(() => closed || current !== revision ? undefined : save(context));
      pending = result.catch(() => undefined);
      return result;
    },
    close() { closed = true; },
  };
}
