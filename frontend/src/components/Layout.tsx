import { NavLink, Outlet } from "react-router";
import { HealthIndicator } from "./HealthIndicator";

export function Layout() {
  return (
    <div className="app">
      <header className="app-header">
        <span className="app-header__title">ICD</span>
        <nav className="app-header__nav" aria-label="Main">
          <NavLink to="/upload">Upload</NavLink>
          <NavLink to="/incidents">Incidents</NavLink>
        </nav>
        <HealthIndicator />
      </header>
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
