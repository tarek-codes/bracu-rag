"use client";

import { createContext, useCallback, useContext, useSyncExternalStore } from "react";

type Theme = "light" | "dark";

const EVENT = "themechange";

// The inline script in layout.tsx sets data-theme before paint; <html> is the source of truth.
function subscribe(cb: () => void) {
  window.addEventListener(EVENT, cb);
  return () => window.removeEventListener(EVENT, cb);
}
const getSnapshot = (): Theme => (document.documentElement.dataset.theme === "dark" ? "dark" : "light");
const getServerSnapshot = (): Theme => "light";

const ThemeContext = createContext<{ theme: Theme; toggle: () => void } | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const theme = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  const toggle = useCallback(() => {
    const next: Theme = getSnapshot() === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    localStorage.setItem("theme", next);
    window.dispatchEvent(new Event(EVENT));
  }, []);

  return <ThemeContext.Provider value={{ theme, toggle }}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used inside ThemeProvider");
  return ctx;
}
