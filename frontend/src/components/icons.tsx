import type { ReactNode } from "react";

// ICD's own inline icon set (decision D4): 20 px grid, 1.6 px stroke, currentColor. Icons are
// always decorative (aria-hidden); the text next to them, or the control's name, carries meaning.

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg
      className="icon"
      viewBox="0 0 20 20"
      width="20"
      height="20"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  );
}

/** Four tiles of different heights: a summary board. */
export const IconOverview = () => (
  <Icon>
    <rect x="3" y="3" width="6" height="8" rx="1.2" />
    <rect x="11" y="3" width="6" height="5" rx="1.2" />
    <rect x="3" y="13" width="6" height="4" rx="1.2" />
    <rect x="11" y="10" width="6" height="7" rx="1.2" />
  </Icon>
);

/** A stack of cards with an alert mark: the incident queue. */
export const IconIncidents = () => (
  <Icon>
    <path d="M4 6.5h12M4 6.5v9a1.5 1.5 0 0 0 1.5 1.5h9A1.5 1.5 0 0 0 16 15.5v-9" />
    <path d="M6 3.5h8" />
    <path d="M10 9v3.2M10 14.6v.1" />
  </Icon>
);

/** A list with a tick: items to review. */
export const IconReview = () => (
  <Icon>
    <path d="M8.5 5h8M8.5 10h8M8.5 15h8" />
    <path d="M3 5.2l1.2 1.2L6.4 4M3 10.2l1.2 1.2L6.4 9" />
    <circle cx="4.6" cy="15" r="1.2" />
  </Icon>
);

/** Three linked nodes: entities and their relations. */
export const IconEntities = () => (
  <Icon>
    <circle cx="5" cy="6" r="2.2" />
    <circle cx="15" cy="5" r="2.2" />
    <circle cx="11" cy="15" r="2.2" />
    <path d="M7.1 6.6l5.7-1M6.3 7.9l3.6 5.2M14.3 7.1l-2.4 5.8" />
  </Icon>
);

/** An arrow into a tray: upload. */
export const IconUpload = () => (
  <Icon>
    <path d="M10 13V3.5M6.5 7L10 3.5 13.5 7" />
    <path d="M3.5 12.5v2.5A1.5 1.5 0 0 0 5 16.5h10a1.5 1.5 0 0 0 1.5-1.5v-2.5" />
  </Icon>
);

/** Three sliders: configuration. */
export const IconConfiguration = () => (
  <Icon>
    <path d="M4 5h12M4 10h12M4 15h12" />
    <circle cx="8" cy="5" r="1.7" fill="var(--surface)" />
    <circle cx="13" cy="10" r="1.7" fill="var(--surface)" />
    <circle cx="6.5" cy="15" r="1.7" fill="var(--surface)" />
  </Icon>
);

export const IconMenu = () => (
  <Icon>
    <path d="M3.5 5.5h13M3.5 10h13M3.5 14.5h13" />
  </Icon>
);

/** Two chevrons pointing left; CSS turns them right when the sidebar is collapsed. */
export const IconCollapse = () => (
  <Icon>
    <path d="M10.5 5.5L6 10l4.5 4.5M15 5.5L10.5 10l4.5 4.5" />
  </Icon>
);

export const IconSearch = () => (
  <Icon>
    <circle cx="8.8" cy="8.8" r="5" />
    <path d="M12.6 12.6L16.5 16.5" />
  </Icon>
);

/** An outlined shield with a small play mark: a simulated response. */
export const IconSimulated = () => (
  <Icon>
    <path d="M10 2.8l5.8 2.2v4.6c0 3.6-2.5 6.3-5.8 7.6-3.3-1.3-5.8-4-5.8-7.6V5z" />
    <path d="M8.6 7.6v4.8l3.8-2.4z" />
  </Icon>
);

export const IconUser = () => (
  <Icon>
    <circle cx="10" cy="7" r="3.2" />
    <path d="M3.8 16.5c.9-2.8 3.3-4.3 6.2-4.3s5.3 1.5 6.2 4.3" />
  </Icon>
);
