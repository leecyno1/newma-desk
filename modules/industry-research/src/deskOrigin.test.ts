import {describe, expect, it} from 'vitest';
import {resolveDeskOrigin} from './deskOrigin';

describe('Desk host origin', () => {
  it('uses the explicitly configured host, not an untrusted query', () => {
    expect(resolveDeskOrigin('https://assets.example/mod/?parentOrigin=https://other.example', 'https://desk.example'))
      .toBe('https://desk.example');
  });
  it('does not infer a different production host when configuration is absent', () => {
    expect(resolveDeskOrigin('https://assets.example/mod/?parentOrigin=https://other.example')).toBe('https://assets.example');
  });
  it('preserves the explicit local development port convention', () => {
    expect(resolveDeskOrigin('http://127.0.0.1:8911/mod-runtime/industry-research/')).toBe('http://127.0.0.1:5888');
  });
  it.each(['*', 'https://desk.example/path', 'https://desk.example/', 'https://user@desk.example', 'file:///tmp'])
    ('rejects a non-origin configuration: %s', value => {
      expect(() => resolveDeskOrigin('https://assets.example/', value)).toThrow();
    });
});
