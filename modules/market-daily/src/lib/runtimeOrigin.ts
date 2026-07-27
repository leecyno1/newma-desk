interface ParentOriginRuntime {
  embedded: boolean;
  ancestorOrigins: readonly string[];
  referrer: string;
  currentOrigin: string;
}

function httpOrigin(value: string | undefined): string | undefined {
  if (!value) return undefined;
  try {
    const parsed = new URL(value);
    return ["http:", "https:"].includes(parsed.protocol) ? parsed.origin : undefined;
  } catch {
    return undefined;
  }
}

function browserRuntime(): ParentOriginRuntime {
  const ancestorOrigins = (
    window.location as Location & { ancestorOrigins?: DOMStringList }
  ).ancestorOrigins;
  return {
    embedded: window.parent !== window,
    ancestorOrigins: ancestorOrigins ? Array.from(ancestorOrigins) : [],
    referrer: document.referrer,
    currentOrigin: window.location.origin,
  };
}

export function resolveParentOrigin(
  configured: string | undefined,
  runtime: ParentOriginRuntime = browserRuntime(),
): string {
  if (runtime.embedded) {
    const ancestor = httpOrigin(runtime.ancestorOrigins[0]);
    if (ancestor) return ancestor;
    const referrer = httpOrigin(runtime.referrer);
    if (referrer) return referrer;
  }
  return httpOrigin(configured?.trim()) ?? runtime.currentOrigin;
}
