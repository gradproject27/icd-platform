import { useEffect, useRef, useState, type ReactNode } from "react";
import { NavLink, Outlet } from "react-router";
import { useCurrentUser, type CurrentRole } from "../auth/useCurrentUser";
import { PAGE_LABELS, ROLE_LABELS, SIMULATED_BANNER_TEXT } from "../labels";
import { Breadcrumbs } from "../shell/Breadcrumbs";
import { QuickJump } from "../shell/QuickJump";
import { useSidebarCollapsed } from "../shell/useSidebarCollapsed";
import { HealthIndicator } from "./HealthIndicator";
import {
  IconCollapse,
  IconConfiguration,
  IconEntities,
  IconIncidents,
  IconMenu,
  IconReview,
  IconSimulated,
  IconUpload,
  IconUser,
} from "./icons";
import { NotificationCenter } from "./NotificationCenter";
import { ThemeToggle } from "./ThemeToggle";

type NavItem = { to: string; label: string; icon: ReactNode };
type NavGroup = { title: string; items: NavItem[] };

// Sidebar groups (design spec section 3). Link names are the accessible names the tests use.
// Overview joins Monitor with its page in phase 3 (decision D2).
const NAV_GROUPS: NavGroup[] = [
  {
    title: "Monitor",
    items: [
      { to: "/incidents", label: PAGE_LABELS.incidents, icon: <IconIncidents /> },
      { to: "/review", label: PAGE_LABELS.review, icon: <IconReview /> },
    ],
  },
  { title: "Investigate", items: [{ to: "/entities", label: PAGE_LABELS.entities, icon: <IconEntities /> }] },
  { title: "Data", items: [{ to: "/upload", label: PAGE_LABELS.upload, icon: <IconUpload /> }] },
  {
    title: "Admin",
    items: [{ to: "/configuration", label: PAGE_LABELS.configuration, icon: <IconConfiguration /> }],
  },
];

function roleText(current: CurrentRole) {
  if (current.kind === "loading") return "Checking role…";
  if (current.kind === "unknown") return "Role unknown";
  return ROLE_LABELS[current.role];
}

/**
 * The signed-in frame: SIMULATED strip, top bar, sidebar (a drawer below 768 px) and content.
 * /login renders outside it, so that page has no navigation at all.
 */
export function Layout() {
  const current = useCurrentUser();
  const { collapsed, toggle: toggleCollapsed } = useSidebarCollapsed();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const sidebar = useRef<HTMLElement>(null);

  // The drawer takes focus when it opens; Escape closes it and gives focus back to Menu.
  useEffect(() => {
    if (!drawerOpen) return;
    sidebar.current?.querySelector<HTMLElement>("a, button")?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setDrawerOpen(false);
      menuButton.current?.focus();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [drawerOpen]);

  const closeDrawer = () => setDrawerOpen(false);

  const shellClass = ["shell", collapsed && "shell--collapsed", drawerOpen && "shell--drawer-open"]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={shellClass}>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>

      <div className="shell__top">
        <div className="sim-banner">
          <IconSimulated />
          <span>{SIMULATED_BANNER_TEXT}</span>
        </div>

        <header className="topbar">
          <button
            ref={menuButton}
            type="button"
            className="topbar__menu"
            aria-expanded={drawerOpen}
            aria-controls="sidebar"
            onClick={() => setDrawerOpen((open) => !open)}
          >
            <IconMenu />
            <span className="topbar__menu-text">Menu</span>
          </button>
          <span className="topbar__brand" title="Intelligent Cyber Defense">
            <span className="topbar__mark" aria-hidden="true" />
            ICD
          </span>
          <Breadcrumbs />
          <div className="topbar__tools">
            <QuickJump />
            <ThemeToggle />
            <NotificationCenter current={current} />
            <HealthIndicator />
            <span className="topbar__role" title="Role reported by the API (GET /me)">
              <IconUser />
              {roleText(current)}
            </span>
          </div>
        </header>
      </div>

      <div className="shell__body">
        <aside id="sidebar" ref={sidebar} className="sidebar">
          <nav aria-label="Main">
            {NAV_GROUPS.map((group) => (
              <div key={group.title} className="sidebar__group">
                <p className="sidebar__group-title" aria-hidden="true">
                  {group.title}
                </p>
                <ul>
                  {group.items.map((item) => (
                    <li key={item.to}>
                      <NavLink to={item.to} className="sidebar__link" title={item.label} onClick={closeDrawer}>
                        {item.icon}
                        <span className="sidebar__label">{item.label}</span>
                      </NavLink>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </nav>
          <button
            type="button"
            className="sidebar__collapse"
            aria-pressed={collapsed}
            title={collapsed ? "Expand the sidebar" : "Collapse the sidebar to icons"}
            onClick={toggleCollapsed}
          >
            <IconCollapse />
            <span className="sidebar__label">Collapse sidebar</span>
          </button>
        </aside>

        {drawerOpen && <div className="shell__backdrop" aria-hidden="true" onClick={closeDrawer} />}

        <main id="main-content" className="app-main" tabIndex={-1} inert={drawerOpen}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
