import {cleanup, render, waitFor} from '@testing-library/react';
import {afterEach, expect, test, vi} from 'vitest';
import {connectModHost, MOD_SDK_VERSION} from '@newma-desk/mod-sdk';
import {GlobalIntelligenceApp} from './App';

vi.mock('@newma-desk/mod-sdk', async importOriginal => ({...await importOriginal<object>(), connectModHost: vi.fn()}));
afterEach(() => {cleanup(); vi.restoreAllMocks(); vi.clearAllMocks();});

test.each([
  [undefined, 'global-situation'], ['fed-rates', 'fed-rates'], ['hormuz', 'hormuz-conflict'], ['us-china-trade', 'us-china-trade'],
] as const)('%s reports the installed SDK version', async (topicId, modId) => {
  vi.spyOn(window, 'parent', 'get').mockReturnValue({} as Window);
  vi.spyOn(document, 'referrer', 'get').mockReturnValue('https://untrusted.example/desk');
  vi.mocked(connectModHost).mockResolvedValue({embedded: false, close() {}});
  render(<GlobalIntelligenceApp topicId={topicId} />);
  await waitFor(() => expect(connectModHost).toHaveBeenCalledWith(expect.objectContaining({modId, sdkVersion: MOD_SDK_VERSION, parentOrigin: window.location.origin})));
});
