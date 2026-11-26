import { useCallback, useEffect, useState } from "react";

export type Theme = "dark" | "light";

/** localStorage key for the user's theme choice (a per-browser convenience, never required). */
export const THEME_STORAGE_KEY = "icd-theme";

const DARK_QUERY = "(prefers-color-scheme: dark)";

/** The saved choice, or null when the user never picked one or storage is blocked. */
export function readStoredTheme(): Theme | null {
  try {
    const value = window.localStorage.getItem(THEME_STORAGE_KEY);
    return value === "dark" || value === "light" ? value : null;
  } catch {
    return null;
  }
}

function storeTheme(theme: Theme) {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch {
    // Private mode or blocked storage: the choice lasts for this page only.
  }
}

function darkQuery(): MediaQueryList | null {
  try {
    return typeof window.matchMedia === "function" ? window.matchMedia(DARK_QUERY) : null;
  } catch {
    return null;
  }
}

/** The OS setting; light when the browser cannot tell. */
export function systemTheme(): Theme {
  return darkQuery()?.matches ? "dark" : "light";
}

/**
 * Sets or clears <html data-theme>. Without the attribute, tokens.css follows the OS through
 * prefers-color-scheme (decision D1). main.tsx calls this before the first render, so the page
 * never flashes the wrong theme.
 */
export function applyTheme(theme: Theme | null) {
  const root = document.documentElement;
  if (theme) root.dataset.theme = theme;
  else delete root.dataset.theme;
}

/** The theme in use (choice, else OS) and a toggle that saves the other theme as the choice. */
export function useTheme() {
  const [choice, setChoice] = useState<Theme | null>(readStoredTheme);
  const [system, setSystem] = useState<Theme>(systemTheme);

  useEffect(() => {
    const query = darkQuery();
    if (!query || typeof query.addEventListener !== "function") return;
    const onChange = (event: MediaQueryListEvent) => setSystem(event.matches ? "dark" : "light");
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    applyTheme(choice);
  }, [choice]);

  const theme: Theme = choice ?? system;

  const toggle = useCallback(() => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    storeTheme(next);
    setChoice(next);
  }, [theme]);

  return { theme, choice, toggle };
}
