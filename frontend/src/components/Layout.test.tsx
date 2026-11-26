import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { App } from "../App";
import { SIMULATED_BANNER_TEXT } from "../labels";
import { SIDEBAR_STORAGE_KEY } from "../shell/useSidebarCollapsed";
import { mockWebSocket } from "../test/fakeWebSocket";
import { HEALTH_OK, jsonResponse, mockFetch } from "../test/fetch";
import { Layout } from "./Layout";

/** Shows the current path, so a test can see where a link or the quick jump went. */
function Where() {
  const location = useLocation();
  return <p data-testid="where">{location.pathname}</p>;
}

function renderShell(path = "/incidents") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/login" element={<p>login page</p>} />
        <Route element={<Layout />}>
          <Route path="*" element={<Where />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

function mockApi(me: unknown = { detail: "nobody" }, meStatus = 401) {
  mockFetch().mockImplementation(async (url) => {
    const path = String(url);
    if (path === "/api/me") {
      return meStatus === 401
        ? jsonResponse({ error: { code: "not_authenticated", message: "Not signed in." } }, 401)
        : jsonResponse(me, meStatus);
    }
    if (path.startsWith("/api/notifications")) return jsonResponse({ items: [] });
    if (path === "/api/incidents") return jsonResponse({ items: [] });
    if (path === "/api/datasets") return jsonResponse({ schema_version: "1.0", items: [] });
    if (path.startsWith("/api/response-windows/")) return jsonResponse({ detail: "none" }, 404);
    if (path.startsWith("/api/incidents/")) {
      return jsonResponse({ error: { code: "not_found", message: "No such incident." } }, 404);
    }
    return jsonResponse(HEALTH_OK);
  });
  mockWebSocket();
}

beforeEach(() => mockApi());
afterEach(() => window.localStorage.clear());

describe("Layout: sidebar", () => {
  it("has one Main navigation with the five page links, names unchanged", async () => {
    renderShell();
    const nav = screen.getByRole("navigation", { name: "Main" });
    const names = within(nav)
      .getAllByRole("link")
      .map((link) => link.textContent);
    expect(names).toEqual(["Incidents", "Review", "Entities", "Upload", "Configuration"]);
    expect(within(nav).getByRole("link", { name: "Upload" })).toHaveAttribute("href", "/upload");
    await screen.findByText("API online");
  });

  it("marks the current page link as active", async () => {
    renderShell("/entities");
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).getByRole("link", { name: "Entities" })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: "Incidents" })).not.toHaveAttribute("aria-current");
    await screen.findByText("API online");
  });

  it("collapses to icons, keeps the link names and remembers the choice", async () => {
    const { container, unmount } = renderShell();
    const collapse = screen.getByRole("button", { name: "Collapse sidebar" });
    expect(collapse).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(collapse);
    expect(collapse).toHaveAttribute("aria-pressed", "true");
    expect(container.querySelector(".shell")).toHaveClass("shell--collapsed");
    expect(window.localStorage.getItem(SIDEBAR_STORAGE_KEY)).toBe("1");
    expect(screen.getByRole("link", { name: "Review" })).toBeInTheDocument();
    await screen.findByText("API online");
    unmount();

    renderShell();
    expect(screen.getByRole("button", { name: "Collapse sidebar" })).toHaveAttribute("aria-pressed", "true");
    await screen.findByText("API online");
  });
});

describe("Layout: mobile drawer", () => {
  it("opens from Menu, moves focus in, and Escape closes it and returns focus", async () => {
    renderShell();
    const menu = screen.getByRole("button", { name: "Menu" });
    expect(menu).toHaveAttribute("aria-expanded", "false");
    expect(menu).toHaveAttribute("aria-controls", "sidebar");

    fireEvent.click(menu);
    expect(menu).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("link", { name: "Incidents" })).toHaveFocus();
    expect(screen.getByRole("main", { hidden: true })).toHaveAttribute("inert");

    fireEvent.keyDown(document, { key: "Escape" });
    expect(menu).toHaveAttribute("aria-expanded", "false");
    expect(menu).toHaveFocus();
    expect(screen.getByRole("main")).not.toHaveAttribute("inert");
    await screen.findByText("API online");
  });

  it("closes after a link is followed", async () => {
    renderShell("/incidents");
    const menu = screen.getByRole("button", { name: "Menu" });
    fireEvent.click(menu);
    fireEvent.click(screen.getByRole("link", { name: "Upload" }));
    expect(menu).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByTestId("where")).toHaveTextContent("/upload");
    await screen.findByText("API online");
  });

  it("ignores Escape while the drawer is closed", async () => {
    renderShell();
    const menu = screen.getByRole("button", { name: "Menu" });
    fireEvent.keyDown(document, { key: "Escape" });
    expect(menu).toHaveAttribute("aria-expanded", "false");
    expect(menu).not.toHaveFocus();
    await screen.findByText("API online");
  });
});

describe("Layout: top bar", () => {
  it("jumps to an incident by ID, trimmed and encoded, then clears the field", async () => {
    renderShell("/review");
    const search = screen.getByRole("search", { name: "Go to incident" });
    const input = within(search).getByLabelText("Incident ID");
    fireEvent.change(input, { target: { value: "  inc a/1 " } });
    fireEvent.click(within(search).getByRole("button", { name: "Go" }));
    expect(screen.getByTestId("where")).toHaveTextContent("/incidents/inc%20a%2F1");
    expect(input).toHaveValue("");
    await screen.findByText("API online");
  });

  it("does nothing on an empty quick jump", async () => {
    renderShell("/review");
    const search = screen.getByRole("search", { name: "Go to incident" });
    fireEvent.change(within(search).getByLabelText("Incident ID"), { target: { value: "   " } });
    fireEvent.click(within(search).getByRole("button", { name: "Go" }));
    expect(screen.getByTestId("where")).toHaveTextContent("/review");
    await screen.findByText("API online");
  });

  it("shows breadcrumbs from the route, the last one as the current page", async () => {
    renderShell("/incidents/inc-7/report");
    const crumbs = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(crumbs).getByRole("link", { name: "Incidents" })).toHaveAttribute("href", "/incidents");
    expect(within(crumbs).getByRole("link", { name: "inc-7" })).toHaveAttribute("href", "/incidents/inc-7");
    expect(within(crumbs).getByText("AI report")).toHaveAttribute("aria-current", "page");
    await screen.findByText("API online");
  });

  it("shows the role from /me as text", async () => {
    mockApi({ user: "analyst-dev", role: "soc_analyst" }, 200);
    renderShell();
    expect(screen.getByText("Checking role…")).toBeInTheDocument();
    expect(await screen.findByText("SOC Analyst")).toBeInTheDocument();
    await screen.findByText("API online");
  });

  it("says the role is unknown when /me has nobody", async () => {
    renderShell();
    expect(await screen.findByText("Role unknown")).toBeInTheDocument();
    await screen.findByText("API online");
  });

  it("has a skip link to the main content", async () => {
    renderShell();
    const skip = screen.getByRole("link", { name: "Skip to content" });
    expect(skip).toHaveAttribute("href", "#main-content");
    expect(screen.getByRole("main")).toHaveAttribute("id", "main-content");
    await screen.findByText("API online");
  });

  it("keeps the theme toggle, notifications and API health in the top bar", async () => {
    renderShell();
    const banner = screen.getByRole("banner");
    expect(within(banner).getByRole("button", { name: "Dark theme" })).toBeInTheDocument();
    expect(within(banner).getByRole("button", { name: /^Notifications/ })).toBeInTheDocument();
    expect(await within(banner).findByText("API online")).toBeInTheDocument();
  });
});

describe("Layout: SIMULATED banner", () => {
  const routes = [
    "/incidents",
    "/upload",
    "/review",
    "/entities",
    "/configuration",
    "/incidents/inc-1",
    "/incidents/inc-1/report",
    "/incidents/inc-1/decision",
    "/incidents/inc-1/audit",
    "/incidents/inc-1/explanation",
    "/incidents/inc-1/graph",
    "/no-such-page",
  ];

  it.each(routes)("is shown on %s", async (path) => {
    render(
      <MemoryRouter initialEntries={[path]}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByText(SIMULATED_BANNER_TEXT)).toBeInTheDocument();
    expect(SIMULATED_BANNER_TEXT).toContain("SIMULATED");
    await screen.findByText("API online");
    // Let the page's own reads settle before the next route.
    await act(async () => {});
  });

  it("is not shown on /login, which has no navigation", () => {
    render(
      <MemoryRouter initialEntries={["/login"]}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.queryByText(SIMULATED_BANNER_TEXT)).not.toBeInTheDocument();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });
});
