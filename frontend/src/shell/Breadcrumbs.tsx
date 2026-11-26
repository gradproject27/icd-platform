import { Link, useLocation } from "react-router";
import { breadcrumbsFor } from "./crumbs";

/** "Incidents › inc-1 › AI report", from the route. A second nav landmark, named "Breadcrumb". */
export function Breadcrumbs() {
  const { pathname } = useLocation();
  const crumbs = breadcrumbsFor(pathname);
  if (crumbs.length === 0) return null;
  return (
    <nav className="breadcrumbs" aria-label="Breadcrumb">
      <ol>
        {crumbs.map((crumb, index) => {
          const last = index === crumbs.length - 1;
          const className = crumb.mono ? "breadcrumbs__item breadcrumbs__item--mono" : "breadcrumbs__item";
          return (
            <li key={`${index}-${crumb.label}`} className={className}>
              {crumb.to && !last ? (
                <Link to={crumb.to}>{crumb.label}</Link>
              ) : (
                <span aria-current={last ? "page" : undefined}>{crumb.label}</span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
