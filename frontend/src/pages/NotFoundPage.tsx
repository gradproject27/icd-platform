import { Link } from "react-router";

export function NotFoundPage() {
  return (
    <section>
      <h1>Page not found</h1>
      <p>There is no page at this address.</p>
      <Link to="/incidents">Go to incidents</Link>
    </section>
  );
}
