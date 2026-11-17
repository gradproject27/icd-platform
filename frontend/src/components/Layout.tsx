import { NavLink, Outlet } from "react-router";
import { useCurrentUser } from "../auth/useCurrentUser";
import { HealthIndicator } from "./HealthIndicator";
import { NotificationCenter } from "./NotificationCenter";

export function Layout() {
  const current = useCurrentUser();
  return (
    <div className="app">
      <header className="app-header">
        <span className="app-header__title">ICD</span>
        <nav className="app-header__nav" aria-label="Main">
          <NavLink to="/upload">Upload</NavLink>
          <NavLink to="/incidents">Incidents</NavLink>
          <NavLink to="/review">Review</NavLink>
          <NavLink to="/configuration">Configuration</NavLink>
        </nav>
        <NotificationCenter current={current} />
        <HealthIndicator />
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
