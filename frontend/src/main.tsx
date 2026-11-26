import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router";
import { App } from "./App";
import { applyTheme, readStoredTheme } from "./hooks/useTheme";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/layout.css";
import "./styles/components.css";
import "./styles/pages.css";

const root = document.getElementById("root");
if (!root) throw new Error("index.html has no #root element");

// The saved theme goes on <html> before the first paint; without one, the CSS follows the OS.
applyTheme(readStoredTheme());

createRoot(root).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
