import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { clsx } from "clsx";
import { ConnectorsPage } from "@/features/connectors/ConnectorsPage";
import { CatalogExplorerPage } from "@/features/catalog-explorer/CatalogExplorerPage";
import { BusinessTreePage } from "@/features/org-tree/BusinessTreePage";
import { ContextSpacesPage } from "@/features/context-spaces/ContextSpacesPage";
import { EnterpriseGraphPage } from "@/features/enterprise-graph/EnterpriseGraphPage";
import { SearchPage } from "@/features/search/SearchPage";
import { AiExplorerPage } from "@/features/ai-explorer/AiExplorerPage";
import { ProposedLinksPage } from "@/features/proposed-links/ProposedLinksPage";
import { WorkflowTemplatesPage } from "@/features/workflow-templates/WorkflowTemplatesPage";

const queryClient = new QueryClient();

function NavLink({ to, label }: { to: string; label: string }) {
  const location = useLocation();
  const active = location.pathname === to;
  return (
    <Link
      to={to}
      className={clsx(
        "block rounded-md px-3 py-2 text-sm font-medium transition-colors",
        active
          ? "bg-sidebar-primary text-sidebar-primary-foreground"
          : "text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
      )}
    >
      {label}
    </Link>
  );
}

function Shell() {
  return (
    <div className="flex h-screen bg-background text-foreground">
      <aside className="flex w-56 shrink-0 flex-col gap-6 border-r border-sidebar-border bg-sidebar p-4 text-sidebar-foreground">
        <div className="font-display text-lg tracking-tight">Context Fabric</div>
        <nav className="space-y-1">
          <NavLink to="/search" label="Search" />
          <NavLink to="/business" label="Business Hierarchy" />
          <NavLink to="/context-spaces" label="Team Contexts" />
          <NavLink to="/workflow-templates" label="Workflow Templates" />
          <NavLink to="/connectors" label="Connectors" />
          <NavLink to="/catalog" label="Asset Catalog" />
          <NavLink to="/ai-explorer" label="AI Explorer" />
          <NavLink to="/proposed-links" label="Proposed Links" />
          <NavLink to="/enterprise-graph" label="Enterprise Graph" />
        </nav>
      </aside>
      <main className="flex-1 overflow-auto p-6">
        <Routes>
          <Route path="/" element={<Navigate to="/search" replace />} />
          <Route path="/search" element={<SearchPage />} />
          <Route path="/business" element={<BusinessTreePage />} />
          <Route path="/context-spaces" element={<ContextSpacesPage />} />
          <Route path="/workflow-templates" element={<WorkflowTemplatesPage />} />
          <Route path="/connectors" element={<ConnectorsPage />} />
          <Route path="/catalog" element={<CatalogExplorerPage />} />
          <Route path="/ai-explorer" element={<AiExplorerPage />} />
          <Route path="/proposed-links" element={<ProposedLinksPage />} />
          <Route path="/enterprise-graph" element={<EnterpriseGraphPage />} />
        </Routes>
      </main>
    </div>
  );
}

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Shell />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
