import { useEffect, useState } from "react";

// 独立打开时默认白色并保存用户选择；嵌入时完全跟随 VibeDesk。
export function useDarkMode() {
  const embedded = window.parent !== window;
  const [dark, setDark] = useState(() => {
    if (embedded) {
      return document.documentElement.dataset.vibedeskTheme === "dark";
    }
    const saved = localStorage.getItem("vr-theme");
    if (saved) return saved === "dark";
    return false; // 默认白色
  });

  useEffect(() => {
    if (!embedded) return;
    const syncTheme = (event: Event) => {
      setDark((event as CustomEvent<"light" | "dark">).detail === "dark");
    };
    window.addEventListener("vibedesk:theme", syncTheme);
    // The Shell can answer the Mod's ready signal before React effects mount.
    // Re-read the applied theme so that an early config message is not lost.
    setDark(document.documentElement.dataset.vibedeskTheme === "dark");
    return () => window.removeEventListener("vibedesk:theme", syncTheme);
  }, [embedded]);

  useEffect(() => {
    const theme = dark ? "dark" : "light";
    document.documentElement.classList.toggle("light", !dark);
    document.documentElement.classList.toggle("dark", dark);
    document.documentElement.dataset.theme = theme;
    document.documentElement.style.colorScheme = theme;
    document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')
      ?.setAttribute("content", dark ? "#0f1714" : "#f4efe3");
    if (!embedded) localStorage.setItem("vr-theme", dark ? "dark" : "light");
  }, [dark, embedded]);

  return { dark, toggle: () => setDark((d) => !d) };
}
