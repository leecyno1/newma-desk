import { describe, expect, it, vi } from 'vitest';

vi.mock('@honeybadger-io/js', () => ({
    default: {
        configure: vi.fn(),
        notify: vi.fn(),
        setContext: vi.fn(),
    },
}));

describe('app-bootstrap', () => {
    it('terminates after an uncaught exception without using the file logger', async () => {
        const exitSpy = vi.spyOn(process, 'exit').mockImplementation((() => {}) as never);
        const stderrSpy = vi.spyOn(process.stderr, 'write').mockImplementation(() => true);
        const before = new Set(process.listeners('uncaughtException'));
        await import('@/app-bootstrap');
        const after = process.listeners('uncaughtException');
        const listener = after.find((fn) => !before.has(fn)) as ((error: Error) => void) | undefined;

        expect(listener).toBeDefined();
        listener?.(new Error('boom'));
        expect(stderrSpy).toHaveBeenCalled();
        expect(exitSpy).toHaveBeenCalledWith(1);

        if (listener) {
            process.removeListener('uncaughtException', listener);
        }
        stderrSpy.mockRestore();
        exitSpy.mockRestore();
    });
});
