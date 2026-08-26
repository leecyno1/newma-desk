import { renderHook, act } from "@testing-library/react";
import { useDarkMode } from "../useDarkMode";

describe("useDarkMode", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.classList.remove("dark", "light");
    delete document.documentElement.dataset.theme;
    document.documentElement.style.removeProperty("color-scheme");
  });

  it("defaults to light when no preference stored and OS is light", () => {
    const { result } = renderHook(() => useDarkMode());
    expect(result.current.dark).toBe(false);
  });

  it("reads dark preference from localStorage", () => {
    localStorage.setItem("qa-theme", "dark");
    const { result } = renderHook(() => useDarkMode());
    expect(result.current.dark).toBe(true);
  });

  it("reads light preference from localStorage", () => {
    localStorage.setItem("qa-theme", "light");
    const { result } = renderHook(() => useDarkMode());
    expect(result.current.dark).toBe(false);
  });

  it("toggles dark mode", () => {
    const { result } = renderHook(() => useDarkMode());
    expect(result.current.dark).toBe(false);

    act(() => result.current.toggle());
    expect(result.current.dark).toBe(true);

    act(() => result.current.toggle());
    expect(result.current.dark).toBe(false);
  });

  it("keeps independent consumers synchronized", () => {
    const first = renderHook(() => useDarkMode());
    const second = renderHook(() => useDarkMode());

    act(() => first.result.current.toggle());

    expect(first.result.current.dark).toBe(true);
    expect(second.result.current.dark).toBe(true);
    expect(first.result.current.themeRevision).toBeGreaterThan(0);
    expect(second.result.current.themeRevision).toBeGreaterThan(0);
  });

  it("persists preference to localStorage on change", () => {
    const { result } = renderHook(() => useDarkMode());
    expect(localStorage.getItem("qa-theme")).toBe("light");

    act(() => result.current.toggle());
    expect(localStorage.getItem("qa-theme")).toBe("dark");

    act(() => result.current.toggle());
    expect(localStorage.getItem("qa-theme")).toBe("light");
  });

  it("toggles dark class on document.documentElement", () => {
    const { result } = renderHook(() => useDarkMode());
    expect(document.documentElement.classList.contains("dark")).toBe(false);
    expect(document.documentElement.dataset.theme).toBe("light");
    expect(document.documentElement.style.colorScheme).toBe("light");

    act(() => result.current.toggle());
    expect(document.documentElement.classList.contains("dark")).toBe(true);
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(document.documentElement.style.colorScheme).toBe("dark");

    act(() => result.current.toggle());
    expect(document.documentElement.classList.contains("dark")).toBe(false);
  });
});
