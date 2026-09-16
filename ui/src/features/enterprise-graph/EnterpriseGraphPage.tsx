import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { api, type CatalogGraph } from "@/lib/api-client";
import { GraphView } from "@/features/catalog-explorer/GraphView";

// Edge types that define "administratively part of this team's scope":
// business hierarchy, a team's own context space, what that space binds,
// and a bound container's own structural contents. Deliberately excludes
// MENTIONS/RELATED_TO/VERIFIES/DEPENDS_ON (SYNC_EXTRACTED, low-confidence
// guesses) — those bridge into unrelated parts of the graph through a
// single incidental cross-reference. Found via testing the server-side
// equivalent (api/routes/catalog.py's _reachable_ids): following every
// edge type from one real team reached 469 of ~476 total nodes, making
// "scope to my team" mean almost nothing.
const SCOPE_EXPANSION_EDGE_TYPES = new Set(["CONTAINS", "HAS_CONTEXT_SPACE", "BINDS"]);

/** Every node reachable from `rootId` treating edges as undirected,
 * following only structural/binding edges — a team's own subtree, its
 * context space(s), and the technical assets bound to them (plus their
 * own structural contents), but not anything merely *mentioned* by one
 * of those assets. Computed client-side since the full graph is already
 * fetched; no reason to round-trip for a scoped view. */
function scopeToNode(graph: CatalogGraph, rootId: string): CatalogGraph {
  const neighbors = new Map<string, string[]>();
  const addEdge = (from: string, to: string) => {
    const list = neighbors.get(from);
    if (list) list.push(to);
    else neighbors.set(from, [to]);
  };
  for (const e of graph.edges) {
    if (!SCOPE_EXPANSION_EDGE_TYPES.has(e.type)) continue;
    addEdge(e.src_id, e.dst_id);
    addEdge(e.dst_id, e.src_id);
  }

  const reachable = new Set<string>([rootId]);
  const queue = [rootId];
  while (queue.length > 0) {
    const current = queue.shift()!;
    for (const next of neighbors.get(current) ?? []) {
      if (!reachable.has(next)) {
        reachable.add(next);
        queue.push(next);
      }
    }
  }

  return {
    nodes: graph.nodes.filter((n) => reachable.has(n.id)),
    edges: graph.edges.filter((e) => reachable.has(e.src_id) && reachable.has(e.dst_id)),
  };
}

export function EnterpriseGraphPage() {
  const graphQuery = useQuery({ queryKey: ["enterprise-graph"], queryFn: api.getEnterpriseGraph });
  const orgTreeQuery = useQuery({ queryKey: ["org-tree"], queryFn: api.getOrgTree });
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [scopeNodeId, setScopeNodeId] = useState("");

  const selected = graphQuery.data?.nodes.find((n) => n.id === selectedId) ?? null;

  const displayedGraph = useMemo(() => {
    if (!graphQuery.data) return undefined;
    if (!scopeNodeId) return graphQuery.data;
    return scopeToNode(graphQuery.data, scopeNodeId);
  }, [graphQuery.data, scopeNodeId]);

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Enterprise Context Graph</h1>
      <p className="text-sm text-neutral-500">
        Every business node, every synced technical asset, and the logical layer connecting them —
        which context space binds a team to which repos, work items, and docs, plus every
        extracted cross-reference between technical assets (a PR mentioning a work item, a doc
        mentioning a PR, and so on). Use the kind filter to cut through the noise, or scope to one
        team below.
      </p>

      <label className="block text-xs text-neutral-600">
        Scope to a business node (and everything connected to it)
        <select
          value={scopeNodeId}
          onChange={(e) => {
            setScopeNodeId(e.target.value);
            setSelectedId(null);
          }}
          className="mt-1 block w-full max-w-md rounded border border-neutral-300 px-2 py-1 text-sm"
        >
          <option value="">— whole enterprise graph —</option>
          {(orgTreeQuery.data ?? []).map((n) => (
            <option key={n.id} value={n.id}>
              {n.path}
            </option>
          ))}
        </select>
      </label>

      {graphQuery.isLoading && <div className="text-sm text-neutral-500">Loading…</div>}
      {displayedGraph && (
        <>
          <div className="text-xs text-neutral-500">
            {displayedGraph.nodes.length} nodes · {displayedGraph.edges.length} edges
            {scopeNodeId && ` (scoped — ${graphQuery.data!.nodes.length} total unscoped)`}
          </div>
          {scopeNodeId && displayedGraph.nodes.length <= 1 && (
            <div className="rounded bg-amber-50 p-2 text-xs text-amber-700">
              This node has nothing connected to it yet — no context space anchored here, or the
              context space has no resolved bindings.
            </div>
          )}
          <GraphView
            key={scopeNodeId}
            graph={displayedGraph}
            onSelectNode={setSelectedId}
            defaultLayout="force"
          />
        </>
      )}

      {selected && (
        <div className="rounded border border-neutral-200 p-4">
          <div className="flex items-center justify-between">
            <div>
              <div className="text-xs text-neutral-400">
                {selected.layer} · {selected.kind}
              </div>
              <div className="text-lg font-semibold">{selected.name}</div>
            </div>
            <button
              onClick={() => setSelectedId(null)}
              className="text-xs text-neutral-400 hover:text-neutral-700"
            >
              close
            </button>
          </div>
          {selected.description && (
            <div className="mt-2 text-sm text-neutral-600">{selected.description}</div>
          )}
          <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-neutral-500">
            {selected.source_system && (
              <div>
                Source: {selected.source_system} / {selected.source_instance_id}
              </div>
            )}
            <div>Path: {selected.path}</div>
          </div>
          {Object.keys(selected.attributes ?? {}).length > 0 && (
            <table className="mt-3 w-full text-left text-xs">
              <tbody>
                {Object.entries(selected.attributes).map(([key, value]) => (
                  <tr key={key} className="border-t border-neutral-100">
                    <td className="py-1 pr-3 font-medium text-neutral-500">{key}</td>
                    <td className="py-1 text-neutral-700">
                      {typeof value === "object" ? JSON.stringify(value) : String(value ?? "—")}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
