import { describe, expect, it } from 'vitest';
import type { ModManifest } from '@newma-desk/contracts';
import { canNavigateWithinSuite, modNavigationSearch, withModNavigationSearch } from './modNavigation';

const manifest = { id: 'fund-discover', entry: { type: 'external', url: 'http://127.0.0.1:3035/mod/fund-research/discover' },
  navigation: { directory: { id: 'fund-research' } } } as ModManifest;

describe('suite navigation', () => {
  it('keeps the installed origin and path, strips reserved parameters, and permits only the same suite', () => {
    const search = modNavigationSearch('symbol=000171.OF&__newma_mod_version=bad');
    expect(search).toBe('symbol=000171.OF');
    expect(withModNavigationSearch(manifest, search).entry.url).toBe('http://127.0.0.1:3035/mod/fund-research/discover?symbol=000171.OF');
    expect(canNavigateWithinSuite(manifest, manifest)).toBe(true);
    expect(canNavigateWithinSuite(manifest, { ...manifest, navigation: undefined })).toBe(false);
    expect(modNavigationSearch('x'.repeat(5000))).toBe('');
    const destination = new URL(withModNavigationSearch(manifest, 'manager_id=a&manager_id=b&product_code=&product_code=000171.OF').entry.url);
    expect(destination.searchParams.getAll('manager_id')).toEqual(['a', 'b']);
    expect(destination.searchParams.getAll('product_code')).toEqual(['', '000171.OF']);
  });
});
