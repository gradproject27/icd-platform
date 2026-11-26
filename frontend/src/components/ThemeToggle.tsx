import { useTheme } from "../hooks/useTheme";

/**
 * One button, "Dark theme", pressed while the dark theme is in use. The name never changes, so
 * screen readers and voice control can always find it; the state is aria-pressed, not colour.
 */
export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const dark = theme === "dark";
  return (
    <button type="button" className="theme-toggle" aria-pressed={dark} onClick={toggle}>
      <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
        {dark ? (
          <path d="M13.5 10.2A6 6 0 0 1 5.8 2.5a6 6 0 1 0 7.7 7.7Z" fill="currentColor" />
        ) : (
          <path
            d="M13.5 10.2A6 6 0 0 1 5.8 2.5a6 6 0 1 0 7.7 7.7Z"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinejoin="round"
          />
        )}
      </svg>
      Dark theme
    </button>
  );
}
