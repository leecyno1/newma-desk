/** Host trust comes from deployment configuration, never referrer or query input. */
export function resolveDeskOrigin(currentUrl: string, configuredOrigin?: string): string {
  if (configuredOrigin) {
    const configured = new URL(configuredOrigin);
    if (!['http:', 'https:'].includes(configured.protocol) || configured.origin !== configuredOrigin) {
      throw new Error('VITE_PARENT_ORIGIN must be an exact HTTP(S) origin');
    }
    return configured.origin;
  }
  const current = new URL(currentUrl);
  if (['127.0.0.1', 'localhost'].includes(current.hostname) && current.port === '8911') {
    return `${current.protocol}//${current.hostname}:5888`;
  }
  return current.origin;
}
