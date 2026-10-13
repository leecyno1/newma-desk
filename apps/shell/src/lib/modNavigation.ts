import type { ModManifest } from '@newma-desk/contracts';

export function modNavigationSearch(value: unknown): string {
  if (typeof value !== 'string' || value.length > 4096) return '';
  const params = new URLSearchParams(value);
  for (const key of [...params.keys()]) if (key.startsWith('__newma_')) params.delete(key);
  return params.toString();
}

export function canNavigateWithinSuite(source: ModManifest, target: ModManifest): boolean {
  const suite = source.navigation?.directory?.id;
  return Boolean(suite && suite === target.navigation?.directory?.id);
}

export function withModNavigationSearch(manifest: ModManifest, search: string): ModManifest {
  if (!search) return manifest;
  const url = new URL(manifest.entry.url, 'http://mod.local');
  const params = new URLSearchParams(modNavigationSearch(search));
  for (const key of new Set(params.keys())) url.searchParams.delete(key);
  for (const [key, value] of params) url.searchParams.append(key, value);
  return { ...manifest, entry: { ...manifest.entry, url: manifest.entry.type === 'external'
    ? url.href : `${url.pathname}${url.search}${url.hash}` } };
}
