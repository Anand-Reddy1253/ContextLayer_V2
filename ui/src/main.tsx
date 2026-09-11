import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "@/app/App";
import "./index.css";

// Phase 16 (docs/phases/PHASE-16.md) wires QueryClientProvider and the
// router here. Placeholder entrypoint until then — see docs/UI.md.
ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
