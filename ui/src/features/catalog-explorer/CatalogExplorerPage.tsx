import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { clsx } from "clsx";
import { api, type CatalogNode } from "@/lib/api-client";
import { GraphView } from "@/features/catalog-explorer/GraphView";
import { Badge, sourceSystemBadgeVariant } from "@/components/Badge";
import { Button } from "@/components/Button";

function ResultRow({
  node,
  selected,
  onSelect,
}: {
  node: CatalogNode;
  selected: boolean;
  onSelect: (id: string) => void;
}) {
  return (
    <button
      onClick={() => onSelect(node.id)}
      className={clsx(
        "block w-full rounded-md px-3 py-2 text-left transition-colors",
        selected ? "bg-secondary text-secondary-foreground" : "hover:bg-accent"
      )}
    >
      <div className="flex items-center gap-1.5">
        <Badge variant={selected ? "outline" : "neutral"} className={selected ? "border-secondary-foreground/30 text-secondary-foreground" : ""}>
          {node.kind}
        </Badge>
        {node.source_system && (
          <Badge variant={sourceSystemBadgeVariant(node.source_system)}>{node.source_system}</Badge>
        )}
        <span className="truncate text-sm font-medium">{node.name}</span>
      </div>
      <div
        className={clsx(
          "mt-0.5 truncate text-xs",
          selected ? "text-secondary-foreground/70" : "text-muted-foreground"
        )}
      >
        {node.path}
      </div>
    </button>
  );
}

type DetailTab = "overview" | "hierarchy";

const METADATA_TRUNCATE_AT = 200;

function formatMetadataValue(value: unknown): string {
  const text = typeof value === "object" ? JSON.stringify(value) : String(value ?? "—");
  if (text.length <= METADATA_TRUNCATE_AT) return text;
  return `${text.slice(0, METADATA_TRUNCATE_AT)}… (${text.length} chars — this connector should be fetching long content on demand, not eagerly, if you're seeing this)`;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className="mt-1 text-sm">{children}</div>
    </div>
  );
}

function OverviewTab({ node }: { node: CatalogNode }) {
  const entries = Object.entries(node.attributes ?? {});
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <Field label="Source">
          {node.source_system ? (
            <Badge variant={sourceSystemBadgeVariant(node.source_system)}>{node.source_system}</Badge>
          ) : (
            "—"
          )}{" "}
          <span className="text-muted-foreground">{node.source_instance_id ?? ""}</span>
        </Field>
        <Field label="Native id">
          <span className="font-mono text-xs">{node.native_id ?? "—"}</span>
        </Field>
        <div className="col-span-2">
          <Field label="Path">
            <span className="font-mono text-xs text-muted-foreground">{node.path}</span>
          </Field>
        </div>
        <Field label="Status">
          <Badge variant="outline">{node.status}</Badge>
        </Field>
      </div>
      <div>
        <div className="text-xs font-medium text-muted-foreground">Metadata</div>
        {entries.length === 0 ? (
          <div className="mt-1 text-sm text-muted-foreground">No metadata on this node.</div>
        ) : (
          <table className="mt-1 w-full text-left text-xs">
            <tbody>
              {entries.map(([key, value]) => (
                <tr key={key} className="border-t border-border">
                  <td className="py-1.5 pr-3 align-top font-medium text-muted-foreground">{key}</td>
                  <td className="py-1.5 tabular-nums text-foreground">{formatMetadataValue(value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

const RELATIONSHIP_TYPES = [
  "RELATED_TO",
  "SPECIFIED_BY",
  "IMPLEMENTS",
  "DEPENDS_ON",
  "VERIFIES",
];

function AddRelationshipForm({ node, onAdded }: { node: CatalogNode; onAdded: () => void }) {
  const [q, setQ] = useState("");
  const [targetId, setTargetId] = useState("");
  const [type, setType] = useState("RELATED_TO");

  const searchQuery = useQuery({
    queryKey: ["node-link-search", q],
    queryFn: () => api.searchCatalog({ q, layer: "TECHNICAL" }),
    enabled: q.length > 1,
  });
  const candidates = (searchQuery.data ?? []).filter((n) => n.id !== node.id);

  const create = useMutation({
    mutationFn: () => api.createNodeLink(node.id, { target_node_id: targetId, type }),
    onSuccess: () => {
      setQ("");
      setTargetId("");
      onAdded();
    },
  });

  const inputClasses =
    "mt-1 block w-full rounded-md border border-input bg-background px-2 py-1 text-xs text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring";

  return (
    <div className="mt-3 rounded-md border border-dashed border-border p-3">
      <div className="grid grid-cols-3 gap-2">
        <label className="col-span-2 text-xs text-muted-foreground">
          Search target node
          <input
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setTargetId("");
            }}
            placeholder="e.g. identity-service"
            className={inputClasses}
          />
        </label>
        <label className="text-xs text-muted-foreground">
          Relationship
          <select value={type} onChange={(e) => setType(e.target.value)} className={inputClasses}>
            {RELATIONSHIP_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
      </div>
      {q.length > 1 && (
        <div className="mt-1 max-h-32 overflow-auto rounded-md border border-border">
          {searchQuery.isLoading && (
            <div className="p-1 text-xs text-muted-foreground">Searching…</div>
          )}
          {candidates.map((c) => (
            <label
              key={c.id}
              className="flex items-center gap-2 border-b border-border px-2 py-1 text-xs last:border-b-0 hover:bg-accent"
            >
              <input
                type="radio"
                name={`link-target-${node.id}`}
                checked={targetId === c.id}
                onChange={() => setTargetId(c.id)}
                className="accent-primary"
              />
              <Badge variant="neutral">{c.kind}</Badge>
              {c.name}
            </label>
          ))}
          {candidates.length === 0 && !searchQuery.isLoading && (
            <div className="p-1 text-xs text-muted-foreground">No matches.</div>
          )}
        </div>
      )}
      <Button
        variant="secondary"
        size="sm"
        onClick={() => create.mutate()}
        disabled={create.isPending || !targetId}
        className="mt-2"
      >
        {create.isPending ? "Adding…" : "Add relationship"}
      </Button>
      {create.isError && (
        <div className="mt-1 text-xs text-destructive">{(create.error as Error).message}</div>
      )}
    </div>
  );
}

function HierarchyTab({ node, onSelect }: { node: CatalogNode; onSelect: (id: string) => void }) {
  const queryClient = useQueryClient();
  const ancestorsQuery = useQuery({
    queryKey: ["node-ancestors", node.id],
    queryFn: () => api.getNodeAncestors(node.id),
  });
  const childrenQuery = useQuery({
    queryKey: ["node-direct-children", node.id],
    queryFn: () => api.getNodeDirectChildren(node.id),
  });
  const linksQuery = useQuery({
    queryKey: ["node-links", node.id],
    queryFn: () => api.getNodeLinks(node.id),
  });
  const deleteLink = useMutation({
    mutationFn: (edgeId: string) => api.deleteEdge(edgeId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["node-links", node.id] }),
  });

  return (
    <div className="space-y-5">
      <div>
        <div className="text-xs font-medium text-muted-foreground">Ancestors (top level first)</div>
        <div className="mt-1.5 flex flex-wrap items-center gap-1 text-sm">
          {ancestorsQuery.isLoading && <span className="text-muted-foreground">Loading…</span>}
          {ancestorsQuery.data?.length === 0 && (
            <span className="text-muted-foreground">This is a top-level container.</span>
          )}
          {ancestorsQuery.data?.map((a, i) => (
            <span key={a.id} className="flex items-center gap-1">
              {i > 0 && <span className="text-border">/</span>}
              <button
                onClick={() => onSelect(a.id)}
                className="rounded-md bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              >
                {a.kind}: {a.name}
              </button>
            </span>
          ))}
        </div>
      </div>

      <div>
        <div className="text-xs font-medium text-muted-foreground">
          Direct children {childrenQuery.data ? `(${childrenQuery.data.length})` : ""}
        </div>
        {childrenQuery.isLoading && (
          <div className="mt-1.5 text-sm text-muted-foreground">Loading…</div>
        )}
        {childrenQuery.data?.length === 0 && (
          <div className="mt-1.5 text-sm text-muted-foreground">No child nodes.</div>
        )}
        {childrenQuery.data && childrenQuery.data.length > 0 && (
          <div className="mt-1.5 max-h-48 space-y-1 overflow-auto">
            {childrenQuery.data.map((c) => (
              <button
                key={c.id}
                onClick={() => onSelect(c.id)}
                className="flex w-full items-center gap-1.5 rounded-md border border-border px-2 py-1.5 text-left text-sm hover:bg-accent"
              >
                <Badge variant="neutral">{c.kind}</Badge>
                {c.name}
              </button>
            ))}
          </div>
        )}
      </div>

      <div>
        <div className="text-xs font-medium text-muted-foreground">
          Dependencies {linksQuery.data ? `(${linksQuery.data.length})` : ""}
        </div>
        <div className="mt-1 text-xs text-muted-foreground">
          Links between technical assets — either extracted automatically (a mentioned "AB#123" or
          a linked pull request) or asserted manually below (e.g. "this doc documents that repo").
        </div>
        {linksQuery.isLoading && (
          <div className="mt-1.5 text-sm text-muted-foreground">Loading…</div>
        )}
        {linksQuery.data?.length === 0 && (
          <div className="mt-1.5 text-sm text-muted-foreground">
            No links found yet. If this object references a pull request, wiki page, or another
            system, make sure that entity type is included in the connection's sync and the
            target has actually been synced — a link only appears once both ends exist.
          </div>
        )}
        {linksQuery.data && linksQuery.data.length > 0 && (
          <div className="mt-1.5 space-y-1">
            {linksQuery.data.map((l) => (
              <div
                key={l.edge.id}
                className="flex items-center justify-between rounded-md bg-muted px-2 py-1.5 text-xs"
              >
                <span className="flex items-center gap-1.5">
                  <Badge variant="outline">{l.edge.type}</Badge>
                  <span className="text-muted-foreground">{l.direction === "outgoing" ? "→" : "←"}</span>
                  {l.node ? (
                    <button onClick={() => onSelect(l.node!.id)} className="font-medium hover:underline">
                      {l.node.kind}: {l.node.name}
                    </button>
                  ) : (
                    <span className="text-muted-foreground">(unresolved target)</span>
                  )}
                </span>
                <span className="flex items-center gap-2">
                  <span className="text-muted-foreground">
                    {l.edge.origin} · {l.edge.state}
                  </span>
                  <button
                    onClick={() => deleteLink.mutate(l.edge.id)}
                    disabled={deleteLink.isPending}
                    className="text-muted-foreground hover:text-destructive"
                  >
                    remove
                  </button>
                </span>
              </div>
            ))}
          </div>
        )}
        <AddRelationshipForm
          node={node}
          onAdded={() => queryClient.invalidateQueries({ queryKey: ["node-links", node.id] })}
        />
      </div>
    </div>
  );
}

function DetailPanel({ node, onSelect }: { node: CatalogNode; onSelect: (id: string) => void }) {
  const [tab, setTab] = useState<DetailTab>("overview");
  const [showGraph, setShowGraph] = useState(false);
  const graphQuery = useQuery({
    queryKey: ["node-graph", node.id],
    queryFn: () => api.getNodeGraph(node.id),
    enabled: showGraph,
  });

  const tabs: { key: DetailTab; label: string }[] = [
    { key: "overview", label: "Overview" },
    { key: "hierarchy", label: "Hierarchy" },
  ];

  return (
    <div className="rounded-lg border border-border bg-card">
      <div className="flex items-center justify-between border-b border-border p-4">
        <div>
          <div className="text-xs text-muted-foreground">{node.kind}</div>
          <div className="font-display text-lg text-foreground">{node.name}</div>
        </div>
        <Button size="sm" onClick={() => setShowGraph((v) => !v)}>
          {showGraph ? "Hide full graph" : "View full graph"}
        </Button>
      </div>

      {showGraph && (
        <div className="border-b border-border p-4">
          {graphQuery.isLoading && (
            <div className="text-sm text-muted-foreground">Loading graph…</div>
          )}
          {graphQuery.data && (
            <>
              <div className="mb-2 text-xs text-muted-foreground">
                {graphQuery.data.nodes.length} nodes · {graphQuery.data.edges.length} edges — this
                node's subtree plus anything cross-referenced from it, even across vendors.
              </div>
              <GraphView graph={graphQuery.data} rootId={node.id} onSelectNode={onSelect} />
            </>
          )}
        </div>
      )}

      <div className="flex border-b border-border">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={clsx(
              "px-4 py-2 text-sm transition-colors",
              tab === t.key
                ? "border-b-2 border-primary font-medium text-foreground"
                : "text-muted-foreground hover:text-foreground"
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="p-4">
        {tab === "overview" && <OverviewTab node={node} />}
        {tab === "hierarchy" && <HierarchyTab node={node} onSelect={onSelect} />}
      </div>
    </div>
  );
}

export function CatalogExplorerPage() {
  const [q, setQ] = useState("");
  const [sourceSystem, setSourceSystem] = useState("");
  const [kind, setKind] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const kindsQuery = useQuery({
    queryKey: ["catalog-kinds", sourceSystem],
    queryFn: () => api.listKinds(sourceSystem || undefined),
  });

  const searchQuery = useQuery({
    queryKey: ["catalog-search", q, sourceSystem, kind],
    queryFn: () =>
      api.searchCatalog({
        q: q || undefined,
        source_system: sourceSystem || undefined,
        kind: kind || undefined,
      }),
  });

  const selectedFromSearch = searchQuery.data?.find((n) => n.id === selectedId) ?? null;
  const selectedNodeQuery = useQuery({
    queryKey: ["node", selectedId],
    queryFn: () => api.getNode(selectedId!),
    enabled: !!selectedId && !selectedFromSearch,
  });
  const selectedNode = selectedFromSearch ?? selectedNodeQuery.data ?? null;

  const fieldClasses =
    "rounded-md border border-input bg-background px-2.5 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring";

  return (
    <div className="space-y-4">
      <h1 className="font-display text-2xl text-foreground">Asset Catalog</h1>
      <div className="flex flex-wrap gap-2">
        <input
          placeholder="Search by name…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className={clsx(fieldClasses, "min-w-56 flex-1")}
        />
        <select
          value={sourceSystem}
          onChange={(e) => {
            setSourceSystem(e.target.value);
            setKind("");
          }}
          className={fieldClasses}
        >
          <option value="">all sources</option>
          <option value="azure_devops">azure_devops</option>
          <option value="github">github</option>
          <option value="confluence">confluence</option>
          <option value="jira">jira</option>
        </select>
        <select value={kind} onChange={(e) => setKind(e.target.value)} className={fieldClasses}>
          <option value="">all types</option>
          {(kindsQuery.data ?? []).map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-5 gap-6">
        <div className="col-span-2 max-h-[70vh] overflow-auto rounded-lg border border-border bg-card p-2">
          {searchQuery.isLoading && (
            <div className="p-2 text-sm text-muted-foreground">Loading…</div>
          )}
          {searchQuery.data?.length === 0 && (
            <div className="p-2 text-sm text-muted-foreground">
              No nodes yet — sync a connector on the Connectors page first.
            </div>
          )}
          <div className="space-y-0.5">
            {searchQuery.data?.map((node) => (
              <ResultRow
                key={node.id}
                node={node}
                selected={node.id === selectedId}
                onSelect={setSelectedId}
              />
            ))}
          </div>
        </div>

        <div className="col-span-3">
          {selectedNode ? (
            <DetailPanel node={selectedNode} onSelect={setSelectedId} />
          ) : (
            <div className="flex h-full items-center justify-center rounded-lg border border-dashed border-border p-8 text-sm text-muted-foreground">
              Select a technical asset to see its metadata, hierarchy, and dependencies.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
