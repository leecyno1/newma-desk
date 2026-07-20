const UNSAFE_KEYS = new Set(["__proto__", "prototype", "constructor"]);

export function resolvePath(root: unknown, path: string): unknown {
  const keys = path.split(".");

  if (keys.some((key) => key.length === 0 || UNSAFE_KEYS.has(key))) {
    return undefined;
  }

  return keys.reduce<unknown>((value, key) => {
    if (
      value === null ||
      typeof value !== "object" ||
      !Object.prototype.hasOwnProperty.call(value, key)
    ) {
      return undefined;
    }

    return (value as Record<string, unknown>)[key];
  }, root);
}
