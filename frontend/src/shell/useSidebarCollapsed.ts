import { useCallback, useState } from "react";

/** localStorage key for the collapsed desktop sidebar (a per-browser convenience). */
export const SIDEBAR_STORAGE_KEY = "icd-sidebar-collapsed";

function readCollapsed(): boolean {
  try {
    return window.localStorage.getItem(SIDEBAR_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

/** Whether the desktop sidebar shows icons only. Remembered per browser when storage works. */
export function useSidebarCollapsed() {
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const toggle = useCallback(() => {
    setCollapsed((value) => {
      const next = !value;
      try {
        window.localStorage.setItem(SIDEBAR_STORAGE_KEY, next ? "1" : "0");
      } catch {
        // Blocked storage: the state lasts for this page only.
      }
      return next;
    });
  }, []);
  return { collapsed, toggle };
}
