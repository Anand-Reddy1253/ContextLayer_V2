import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type CatalogNode } from "@/lib/api-client";
import { GraphView } from "@/features/catalog-explorer/GraphView";

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
    <div
      onClick={() => onSelect(node.id)}
      className={`cursor-pointer rounded px-3 py-2 ${
        selected ? "bg-neutral-900 text-white" : "hover:bg-neutral-50"
      }`}
    >
      <div className="flex items-center gap-2">
        <span className={`rounded px-1.5 py-0.5 text-xs ${selected ? "bg-white/20" : "bg-neutral-100"}`}>
          {node.kind}
        </span>
        <span className="text-sm font-medium">{node.name}</span>
      </div>
      <div className={`mt-0.5 text-xs ${selected ? "text-white/70" : "text-neutral-400"}`}>
        {node.path}
      </div>
    </div>
  );
}

type DetailTab = "overview" | "hierarchy";

const METADATA_TRUNCATE_AT = 200;

function formatMetadataValue(value: unknown): string {
  const text = typeof value === "object" ? JSON.stringify(value) : String(value ?? "—");
  if (text.length <= METADATA_TRUNCATE_AT) return text;
  return `${text.slice(0, METADATA_TRUNCATE_AT)}… (${text.length} chars — this connector should be fetching long content on demand, not eagerly, if you're seeing this)`;
}

function OverviewTab({ node }: { node: CatalogNode }) {
  const entries = Object.entries(node.attributes ?? {});
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div>
          <div className="text-xs font-medium text-neutral-500">Source</div>
          <div className="mt-1 text-sm">
            {node.source_system ?? "—"} / {node.source_instance_id ?? "—"}
          </div>
        </div>
        <div>
          <div className="text-xs font-medium text-neutral-500">Native id</div>
          <div className="mt-1 font-mono text-xs">{node.native_id ?? "—"}</div>
        </div>
        <div className="col-span-2">
          <div className="text-xs font-medium text-neutral-500">Path</div>
          <div className="mt-1 font-mono text-xs text-neutral-600">{node.path}</div>
        </div>
        <div>
          <div className="text-xs font-medium text-neutral-500">Status</div>
          <div className="mt-1 text-sm">{node.status}</div>
        </div>
      </div>
      <div>
        <div className="text-xs font-medium text-neutral-500">Metadata</div>
        {entries.length === 0 ? (
          <div className="mt-1 text-sm text-neutral-400">No metadata on this node.</div>
        ) : (
          <table className="mt-1 w-full text-left text-xs">
            <tbody>
              {entries.map(([key, value]) => (
                <tr key={key} className="border-t border-neutral-100">
                  <td className="py-1 pr-3 align-top font-medium text-neutral-500">{key}</td>
                  <td className="py-1 text-neutral-700">{formatMetadataValue(value)}</td>
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

  return (
    <div className="mt-2 rounded border border-dashed border-neutral-300 p-2">
      <div className="grid grid-cols-3 gap-2">
        <label className="col-span-2 text-xs text-neutral-600">
          Search target node
          <input
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setTargetId("");
            }}
            placeholder="e.g. identity-service"
            className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-xs"
          />
        </label>
        <label className="text-xs text-neutral-600">
          Relationship
          <select
            value={type}
            onChange={(e) => setType(e.target.value)}
            className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-xs"
          >
            {RELATIONSHIP_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </label>
      </div>
      {q.length > 1 && (
        <div className="mt-1 max-h-32 overflow-auto rounded border border-neutral-200">
          {searchQuery.isLoading && <div className="p-1 text-xs text-neutral-400">Searching…</div>}
          {candidates.map((c) => (
            <label
              key={c.id}
              className="flex items-center gap-2 border-b border-neutral-100 px-2 py-1 text-xs last:border-b-0 hover:bg-neutral-50"
            >
              <input
                type="radio"
                name={`link-target-${node.id}`}
                checked={targetId === c.id}
                onChange={() => setTargetId(c.id)}
              />
              <span className="rounded bg-neutral-100 px-1.5 py-0.5">{c.kind}</span>
              {c.name}
            </label>
          ))}
          {candidates.length === 0 && !searchQuery.isLoading && (
            <div className="p-1 text-xs text-neutral-400">No matches.</div>
          )}
        </div>
      )}
      <button
        onClick={() => create.mutate()}
        disabled={create.isPending || !targetId}
        className="mt-2 rounded border border-neutral-400 px-2 py-1 text-xs disabled:opacity-50"
      >
        {create.isPending ? "Adding…" : "Add relationship"}
      </button>
      {create.isError && (
        <div className="mt-1 text-xs text-red-600">{(create.error as Error).message}</div>
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
    <div className="space-y-4">
      <div>
        <div className="text-xs font-medium text-neutral-500">Ancestors (top level first)</div>
        <div className="mt-1 flex flex-wrap items-center gap-1 text-sm">
          {ancestorsQuery.isLoading && <span className="text-neutral-400">Loading…</span>}
          {ancestorsQuery.data?.length === 0 && (
            <span className="text-neutral-400">This is a top-level container.</span>
          )}
          {ancestorsQuery.data?.map((a, i) => (
            <span key={a.id} className="flex items-center gap-1">
              {i > 0 && <span className="text-neutral-300">/</span>}
              <button
                onClick={() => onSelect(a.id)}
                className="rounded bg-neutral-100 px-2 py-0.5 hover:bg-neutral-200"
              >
                {a.kind}: {a.name}
              </button>
            </span>
          ))}
        </div>
      </div>

      <div>
        <div className="text-xs font-medium text-neutral-500">
          Direct children {childrenQuery.data ? `(${childrenQuery.data.length})` : ""}
        </div>
        {childrenQuery.isLoading && <div className="mt-1 text-sm text-neutral-400">Loading…</div>}
        {childrenQuery.data?.length === 0 && (
          <div className="mt-1 text-sm text-neutral-400">No child nodes.</div>
        )}
        {childrenQuery.data && childrenQuery.data.length > 0 && (
          <div className="mt-1 max-h-48 space-y-1 overflow-auto">
            {childrenQuery.data.map((c) => (
              <button
                key={c.id}
                onClick={() => onSelect(c.id)}
                className="block w-full rounded border border-neutral-200 px-2 py-1 text-left text-sm hover:bg-neutral-50"
              >
                <span className="rounded bg-neutral-100 px-1.5 py-0.5 text-xs">{c.kind}</span>{" "}
                {c.name}
              </button>
            ))}
          </div>
        )}
      </div>

      <div>
        <div className="text-xs font-medium text-neutral-500">
          Dependencies {linksQuery.data ? `(${linksQuery.data.length})` : ""}
        </div>
        <div className="mt-1 text-xs text-neutral-400">
          Links between technical assets — either extracted automatically (a mentioned "AB#123" or
          a linked pull request) or asserted manually below (e.g. "this doc documents that repo").
        </div>
        {linksQuery.isLoading && <div className="mt-1 text-sm text-neutral-400">Loading…</div>}
        {linksQuery.data?.length === 0 && (
          <div className="mt-1 text-sm text-neutral-400">
            No links found yet. If this object references a pull request, wiki page, or another
            system, make sure that entity type is included in the connection's sync and the
            target has actually been synced — a link only appears once both ends exist.
          </div>
        )}
        {linksQuery.data && linksQuery.data.length > 0 && (
          <div className="mt-1 space-y-1">
            {linksQuery.data.map((l) => (
              <div
                key={l.edge.id}
                className="flex items-center justify-between rounded bg-neutral-50 px-2 py-1 text-xs"
              >
                <span>
                  <span className="rounded bg-neutral-200 px-1.5 py-0.5">{l.edge.type}</span>{" "}
                  {l.direction === "outgoing" ? "→" : "←"}{" "}
                  {l.node ? (
                    <button
                      onClick={() => onSelect(l.node!.id)}
                      className="font-medium hover:underline"
                    >
                      {l.node.kind}: {l.node.name}
                    </button>
                  ) : (
                    <span className="text-neutral-400">(unresolved target)</span>
                  )}
                </span>
                <span className="flex items-center gap-2">
                  <span className="text-neutral-400">
                    {l.edge.origin} · {l.edge.state}
                  </span>
                  <button
                    onClick={() => deleteLink.mutate(l.edge.id)}
                    disabled={deleteLink.isPending}
                    className="text-neutral-400 hover:text-red-600"
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
    <div className="rounded border border-neutral-200">
      <div className="flex items-center justify-between border-b border-neutral-200 p-4">
        <div>
          <div className="text-xs text-neutral-400">{node.kind}</div>
          <div className="text-lg font-semibold">{node.name}</div>
        </div>
        <button
          onClick={() => setShowGraph((v) => !v)}
          className="rounded border border-neutral-400 px-3 py-1.5 text-sm"
        >
          {showGraph ? "Hide full graph" : "View full graph"}
        </button>
      </div>

      {showGraph && (
        <div className="border-b border-neutral-200 p-4">
          {graphQuery.isLoading && <div className="text-sm text-neutral-500">Loading graph…</div>}
          {graphQuery.data && (
            <>
              <div className="mb-2 text-xs text-neutral-500">
                {graphQuery.data.nodes.length} nodes · {graphQuery.data.edges.length} edges in this
                subtree.
              </div>
              <GraphView graph={graphQuery.data} rootId={node.id} onSelectNode={onSelect} />
            </>
          )}
        </div>
      )}

      <div className="flex border-b border-neutral-200">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-sm ${
              tab === t.key
                ? "border-b-2 border-neutral-900 font-medium text-neutral-900"
                : "text-neutral-500 hover:text-neutral-700"
            }`}
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

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Asset Catalog</h1>
      <div className="flex gap-2">
        <input
          placeholder="Search by name…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="rounded border border-neutral-300 px-2 py-1 text-sm"
        />
        <select
          value={sourceSystem}
          onChange={(e) => {
            setSourceSystem(e.target.value);
            setKind("");
          }}
          className="rounded border border-neutral-300 px-2 py-1 text-sm"
        >
          <option value="">all sources</option>
          <option value="azure_devops">azure_devops</option>
          <option value="github">github</option>
          <option value="confluence">confluence</option>
        </select>
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value)}
          className="rounded border border-neutral-300 px-2 py-1 text-sm"
        >
          <option value="">all types</option>
          {(kindsQuery.data ?? []).map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-5 gap-6">
        <div className="col-span-2 max-h-[70vh] overflow-auto rounded border border-neutral-200 p-2">
          {searchQuery.isLoading && <div className="p-2 text-sm text-neutral-500">Loading…</div>}
          {searchQuery.data?.length === 0 && (
            <div className="p-2 text-sm text-neutral-500">
              No nodes yet — sync a connector on the Connectors page first.
            </div>
          )}
          {searchQuery.data?.map((node) => (
            <ResultRow
              key={node.id}
              node={node}
              selected={node.id === selectedId}
              onSelect={setSelectedId}
            />
          ))}
        </div>

        <div className="col-span-3">
          {selectedNode ? (
            <DetailPanel node={selectedNode} onSelect={setSelectedId} />
          ) : (
            <div className="flex h-full items-center justify-center rounded border border-dashed border-neutral-300 p-8 text-sm text-neutral-400">
              Select a technical asset to see its metadata, hierarchy, and dependencies.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
