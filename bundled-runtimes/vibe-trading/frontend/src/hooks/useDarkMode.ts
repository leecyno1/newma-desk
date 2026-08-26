import { useEffect, useState } from "react";

export function useDarkMode() {
  const embedded = window.parent !== window;
  const [themeRevision, setThemeRevision] = useState(0);
  const [dark, setDark] = useState(() => {
    if (embedded) {
      return document.documentElement.dataset.vibedeskTheme === "dark";
    }
    const saved = localStorage.getItem("qa-theme");
    if (saved) return saved === "dark";
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  });

  useEffect(() => {
    const syncLegacyTheme = (event: Event) => {
      setDark((event as CustomEvent<"light" | "dark">).detail === "dark");
      setThemeRevision((revision) => revision + 1);
    };
    const syncNewmaTheme = (event: Event) => {
      const detail = (event as CustomEvent<{ mode?: "light" | "dark" }>).detail;
      if (detail?.mode) {
        setDark(detail.mode === "dark");
        setThemeRevision((revision) => revision + 1);
      }
    };
    window.addEventListener("newma:themechange", syncNewmaTheme);
    if (embedded) {
      window.addEventListener("vibedesk:theme", syncLegacyTheme);
      // The Shell can answer the Mod's ready signal before React effects mount.
      // Re-read the applied theme so that an early config message is not lost.
      setDark(document.documentElement.dataset.vibedeskTheme === "dark");
    }
    return () => {
      window.removeEventListener("newma:themechange", syncNewmaTheme);
      if (embedded) window.removeEventListener("vibedesk:theme", syncLegacyTheme);
    };
  }, [embedded]);

  useEffect(() => {
    const root = document.documentElement;
    const mode = dark ? "dark" : "light";
    root.dataset.theme = mode;
    if (embedded) root.dataset.vibedeskTheme = mode;
    root.classList.toggle("dark", dark);
    root.classList.toggle("light", !dark);
    root.style.colorScheme = mode;
    document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')
      ?.setAttribute("content", dark ? "#0f1714" : "#f4efe3");
    if (!embedded) localStorage.setItem("qa-theme", dark ? "dark" : "light");
  }, [dark, embedded]);

  const toggle = () => {
    const mode = dark ? "light" : "dark";
    setDark(mode === "dark");
    window.dispatchEvent(
      new CustomEvent("newma:themechange", {
        detail: { mode, source: "vibe-trading" },
      }),
    );
  };

  return { dark, themeRevision, toggle };
}
