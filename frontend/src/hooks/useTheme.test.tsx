import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { THEME_STORAGE_KEY, applyTheme, readStoredTheme, systemTheme, useTheme } from "./useTheme";

type Listener = (event: MediaQueryListEvent) => void;

/** A matchMedia stand-in whose OS setting the test can change. */
function stubOsTheme(dark: boolean) {
  const listeners = new Set<Listener>();
  const query = {
    matches: dark,
    media: "(prefers-color-scheme: dark)",
    addEventListener: (_: string, listener: Listener) => listeners.add(listener),
    removeEventListener: (_: string, listener: Listener) => listeners.delete(listener),
  };
  vi.stubGlobal("matchMedia", vi.fn(() => query));
  return {
    change(next: boolean) {
      query.matches = next;
      listeners.forEach((listener) => listener({ matches: next } as MediaQueryListEvent));
    },
    listeners,
  };
}

afterEach(() => {
  window.localStorage.clear();
  delete document.documentElement.dataset.theme;
});

describe("useTheme", () => {
  it("follows the OS when the user never picked a theme, and sets no data-theme", () => {
    stubOsTheme(true);
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("dark");
    expect(result.current.choice).toBeNull();
    expect(document.documentElement.dataset.theme).toBeUndefined();
  });

  it("follows a later OS change while no choice is saved", () => {
    const os = stubOsTheme(false);
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("light");
    act(() => os.change(true));
    expect(result.current.theme).toBe("dark");
  });

  it("toggles to the other theme, saves the choice and sets data-theme", () => {
    stubOsTheme(true);
    const { result } = renderHook(() => useTheme());
    act(() => result.current.toggle());
    expect(result.current.theme).toBe("light");
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
    expect(document.documentElement.dataset.theme).toBe("light");
    act(() => result.current.toggle());
    expect(result.current.theme).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("keeps a saved choice over the OS setting", () => {
    const os = stubOsTheme(true);
    window.localStorage.setItem(THEME_STORAGE_KEY, "light");
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("light");
    act(() => os.change(false));
    act(() => os.change(true));
    expect(result.current.theme).toBe("light");
  });

  it("ignores an unknown saved value", () => {
    stubOsTheme(false);
    window.localStorage.setItem(THEME_STORAGE_KEY, "purple");
    expect(readStoredTheme()).toBeNull();
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("light");
  });

  it("still toggles when storage throws (private mode)", () => {
    stubOsTheme(false);
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("light");
    act(() => result.current.toggle());
    expect(result.current.theme).toBe("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
  });

  it("falls back to light when matchMedia is missing", () => {
    vi.stubGlobal("matchMedia", undefined);
    expect(systemTheme()).toBe("light");
    const { result } = renderHook(() => useTheme());
    expect(result.current.theme).toBe("light");
  });

  it("removes its OS listener on unmount", () => {
    const os = stubOsTheme(false);
    const { unmount } = renderHook(() => useTheme());
    expect(os.listeners.size).toBe(1);
    unmount();
    expect(os.listeners.size).toBe(0);
  });
});

describe("applyTheme", () => {
  it("sets and clears data-theme on <html>", () => {
    applyTheme("dark");
    expect(document.documentElement.dataset.theme).toBe("dark");
    applyTheme(null);
    expect(document.documentElement.dataset.theme).toBeUndefined();
  });
});
