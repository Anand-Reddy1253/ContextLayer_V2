import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type CatalogNode, type ProposedEdge } from "@/lib/api-client";

function NodeChip({ node }: { node: CatalogNode | null }) {
  if (!node) {
    return <span className="text-neutral-400">(unresolved)</span>;
  }
  return (
    <span className="inline-flex items-center gap-1">
      <span className="rounded bg-neutral-100 px-1.5 py-0.5 text-xs">{node.kind}</span>
      <span className="text-sm font-medium">{node.name}</span>
      <span className="text-xs text-neutral-400">
        ({node.source_system}/{node.source_instance_id})
      </span>
    </span>
  );
}

function ProposedEdgeCard({ item, onDone }: { item: ProposedEdge; onDone: () => void }) {
  const [retyping, setRetyping] = useState(false);
  const [query, setQuery] = useState("");

  const searchQuery = useQuery({
    queryKey: ["retype-search", query],
    queryFn: () => api.searchCatalog({ q: query, layer: "TECHNICAL" }),
    enabled: query.length > 1,
  });

  const confirm = useMutation({
    mutationFn: () => api.confirmProposedEdge(item.edge.id),
    onSuccess: onDone,
  });
  const reject = useMutation({
    mutationFn: () => api.rejectProposedEdge(item.edge.id),
    onSuccess: onDone,
  });
  const retype = useMutation({
    mutationFn: (dstNodeId: string) => api.retypeProposedEdge(item.edge.id, dstNodeId),
    onSuccess: onDone,
  });

  const pending = confirm.isPending || reject.isPending || retype.isPending;

  return (
    <div className="rounded border border-neutral-200 p-3">
      <div className="flex items-center justify-between">
        <div className="flex flex-wrap items-center gap-1.5 text-sm">
          <NodeChip node={item.src} />
          <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-xs text-white">
            {item.edge.type}
          </span>
          <span className="text-neutral-400">→</span>
          <NodeChip node={item.dst} />
        </div>
        <div className="flex items-center gap-2 text-xs text-neutral-400">
          <span>{item.edge.origin}</span>
          <span>conf. {item.edge.confidence?.toFixed(2)}</span>
        </div>
      </div>

      <div className="mt-2 rounded bg-amber-50 px-2 py-1.5 text-xs text-amber-900">
        <span className="font-medium">Why this was proposed: </span>
        {item.edge.evidence ?? (
          <span className="italic text-amber-700">
            No evidence recorded for this edge (synced before evidence tracking was added —
            re-sync the source to backfill it).
          </span>
        )}
      </div>

      {!retyping ? (
        <div className="mt-2 flex gap-2">
          <button
            onClick={() => confirm.mutate()}
            disabled={pending}
            className="rounded bg-green-600 px-2 py-1 text-xs text-white disabled:opacity-50"
          >
            Confirm
          </button>
          <button
            onClick={() => reject.mutate()}
            disabled={pending}
            className="rounded bg-red-600 px-2 py-1 text-xs text-white disabled:opacity-50"
          >
            Reject
          </button>
          <button
            onClick={() => setRetyping(true)}
            disabled={pending}
            className="rounded border border-neutral-300 px-2 py-1 text-xs disabled:opacity-50"
          >
            Retype target
          </button>
        </div>
      ) : (
        <div className="mt-2 rounded border border-dashed border-neutral-300 p-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search the correct target node…"
            className="block w-full rounded border border-neutral-300 px-2 py-1 text-xs"
            autoFocus
          />
          {searchQuery.data && searchQuery.data.length > 0 && (
            <div className="mt-1 max-h-40 space-y-1 overflow-auto">
              {searchQuery.data.map((n) => (
                <button
                  key={n.id}
                  onClick={() => retype.mutate(n.id)}
                  disabled={pending}
                  className="block w-full rounded px-2 py-1 text-left text-xs hover:bg-neutral-50"
                >
                  <span className="rounded bg-neutral-100 px-1 py-0.5">{n.kind}</span> {n.name}
                </button>
              ))}
            </div>
          )}
          <button
            onClick={() => setRetyping(false)}
            className="mt-1 text-xs text-neutral-400 hover:underline"
          >
            cancel
          </button>
        </div>
      )}
    </div>
  );
}

export function ProposedLinksPage() {
  const [typeFilter, setTypeFilter] = useState<string | undefined>(undefined);
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ["proposed-edges", typeFilter],
    queryFn: () => api.listProposedEdges(typeFilter),
  });

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["proposed-edges"] });

  const types = ["RELATED_TO", "MENTIONS", "VERIFIES", "DEPENDS_ON"];

  if (query.isLoading) {
    return <div className="p-6 text-sm text-neutral-500">Loading proposed links…</div>;
  }
  if (query.isError) {
    return <div className="p-6 text-sm text-red-600">Failed to load proposed links.</div>;
  }

  const items = query.data ?? [];

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Proposed Links</h1>
        <p className="text-sm text-neutral-500">
          Relationships automatically extracted during sync (a mentioned work item, a linked pull
          request…) land here as proposals — nothing becomes a real, active edge until confirmed.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => setTypeFilter(undefined)}
          className={`rounded px-2 py-1 text-xs ${
            typeFilter === undefined ? "bg-neutral-900 text-white" : "bg-neutral-100 text-neutral-600"
          }`}
        >
          All types
        </button>
        {types.map((t) => (
          <button
            key={t}
            onClick={() => setTypeFilter(t)}
            className={`rounded px-2 py-1 text-xs ${
              typeFilter === t ? "bg-neutral-900 text-white" : "bg-neutral-100 text-neutral-600"
            }`}
          >
            {t}
          </button>
        ))}
        <div className="text-xs text-neutral-400">{items.length} pending</div>
      </div>

      {items.length === 0 ? (
        <div className="rounded border border-dashed border-neutral-300 p-8 text-center text-sm text-neutral-500">
          No proposed links waiting for review right now.
        </div>
      ) : (
        <div className="space-y-2">
          {items.map((item) => (
            <ProposedEdgeCard key={item.edge.id} item={item} onDone={refresh} />
          ))}
        </div>
      )}
    </div>
  );
}
