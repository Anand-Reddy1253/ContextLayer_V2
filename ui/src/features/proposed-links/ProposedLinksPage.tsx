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

function ProposedEdgeCard({
  item,
  onDone,
  selected,
  onToggleSelected,
}: {
  item: ProposedEdge;
  onDone: () => void;
  selected: boolean;
  onToggleSelected: () => void;
}) {
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
  const isLlmInferred = item.edge.origin === "LLM_INFERRED";
  const rationale = item.edge.attributes?.rationale;
  const model = item.edge.attributes?.model;

  return (
    <div className="flex gap-2 rounded border border-neutral-200 p-3">
      <input
        type="checkbox"
        checked={selected}
        onChange={onToggleSelected}
        className="mt-1 shrink-0"
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between">
          <div className="flex flex-wrap items-center gap-1.5 text-sm">
            <NodeChip node={item.src} />
            <span className="rounded bg-neutral-800 px-1.5 py-0.5 text-xs text-white">
              {item.edge.type}
            </span>
            <span className="text-neutral-400">→</span>
            <NodeChip node={item.dst} />
            {isLlmInferred && (
              <span
                title={model ? `Inferred by ${String(model)} — not a vendor-declared fact` : undefined}
                className="rounded bg-purple-100 px-1.5 py-0.5 text-xs font-medium text-purple-800"
              >
                LLM
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 text-xs text-neutral-400">
            <span>{item.edge.origin}</span>
            <span>conf. {item.edge.confidence?.toFixed(2)}</span>
          </div>
        </div>

        <div
          className={`mt-2 rounded px-2 py-1.5 text-xs ${
            isLlmInferred ? "bg-purple-50 text-purple-900" : "bg-amber-50 text-amber-900"
          }`}
        >
          <span className="font-medium">
            {isLlmInferred ? "Model's stated rationale (unverified): " : "Why this was proposed: "}
          </span>
          {isLlmInferred
            ? (typeof rationale === "string" && rationale) || (
                <span className="italic">No rationale recorded.</span>
              )
            : (item.edge.evidence ?? (
                <span className="italic text-amber-700">
                  No evidence recorded for this edge (synced before evidence tracking was added —
                  re-sync the source to backfill it).
                </span>
              ))}
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
    </div>
  );
}

function BulkActionBar({
  items,
  selected,
  onSelectAll,
  onClear,
  onDone,
}: {
  items: ProposedEdge[];
  selected: Set<string>;
  onSelectAll: () => void;
  onClear: () => void;
  onDone: () => void;
}) {
  const [confirmingBulkAction, setConfirmingBulkAction] = useState<"confirm" | "reject" | null>(
    null
  );
  const selectedIds = Array.from(selected);

  const bulkConfirm = useMutation({
    mutationFn: () => api.bulkConfirmProposedEdges(selectedIds),
    onSuccess: () => {
      setConfirmingBulkAction(null);
      onDone();
    },
  });
  const bulkReject = useMutation({
    mutationFn: () => api.bulkRejectProposedEdges(selectedIds),
    onSuccess: () => {
      setConfirmingBulkAction(null);
      onDone();
    },
  });
  const pending = bulkConfirm.isPending || bulkReject.isPending;

  return (
    <div className="flex flex-wrap items-center gap-2 rounded border border-neutral-300 bg-neutral-50 px-3 py-2 text-xs">
      <button onClick={onSelectAll} className="rounded border border-neutral-300 bg-white px-2 py-1">
        Select all {items.length} matching this filter
      </button>
      <button onClick={onClear} className="rounded border border-neutral-300 bg-white px-2 py-1">
        Clear selection
      </button>
      <span className="text-neutral-500">{selected.size} selected</span>

      <div className="ml-auto flex items-center gap-2">
        {confirmingBulkAction ? (
          <span className="flex items-center gap-1.5">
            <span className="text-neutral-600">
              {confirmingBulkAction === "confirm" ? "Confirm" : "Reject"} {selected.size} link
              {selected.size === 1 ? "" : "s"}?
            </span>
            <button
              onClick={() =>
                confirmingBulkAction === "confirm" ? bulkConfirm.mutate() : bulkReject.mutate()
              }
              disabled={pending}
              className={`rounded px-2 py-1 text-white disabled:opacity-50 ${
                confirmingBulkAction === "confirm" ? "bg-green-600" : "bg-red-600"
              }`}
            >
              {pending ? "Applying…" : "Yes, apply"}
            </button>
            <button
              onClick={() => setConfirmingBulkAction(null)}
              disabled={pending}
              className="rounded border border-neutral-300 bg-white px-2 py-1"
            >
              Cancel
            </button>
          </span>
        ) : (
          <>
            <button
              onClick={() => setConfirmingBulkAction("confirm")}
              disabled={selected.size === 0}
              className="rounded bg-green-600 px-2 py-1 text-white disabled:opacity-50"
            >
              Confirm selected
            </button>
            <button
              onClick={() => setConfirmingBulkAction("reject")}
              disabled={selected.size === 0}
              className="rounded bg-red-600 px-2 py-1 text-white disabled:opacity-50"
            >
              Reject selected
            </button>
          </>
        )}
      </div>
      {(bulkConfirm.isError || bulkReject.isError) && (
        <div className="w-full text-red-600">
          {((bulkConfirm.error ?? bulkReject.error) as Error).message}
        </div>
      )}
    </div>
  );
}

const PAGE_SIZE = 20;

export function ProposedLinksPage() {
  const [typeFilter, setTypeFilter] = useState<string | undefined>(undefined);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [page, setPage] = useState(1);
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ["proposed-edges", typeFilter],
    queryFn: () => api.listProposedEdges(typeFilter),
  });

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["proposed-edges"] });
    setSelected(new Set());
  };

  const toggleSelected = (edgeId: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(edgeId)) next.delete(edgeId);
      else next.add(edgeId);
      return next;
    });
  };

  const types = [
    "RELATED_TO",
    "MENTIONS",
    "VERIFIES",
    "DEPENDS_ON",
    "IMPLEMENTS",
    "CHANGES",
    // LLM-inferred (ADR-011) — always PROPOSED, never auto-confirmed.
    "SUPERSEDES",
    "SUPERSEDED_BY",
    "CAUSED_BY",
    "DECIDES_ON",
  ];

  if (query.isLoading) {
    return <div className="p-6 text-sm text-neutral-500">Loading proposed links…</div>;
  }
  if (query.isError) {
    return <div className="p-6 text-sm text-red-600">Failed to load proposed links.</div>;
  }

  const items = query.data ?? [];
  const totalPages = Math.max(1, Math.ceil(items.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pagedItems = items.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">Proposed Links</h1>
        <p className="text-sm text-neutral-500">
          Relationships automatically extracted during sync (a mentioned work item, a linked pull
          request…) land here as proposals — nothing becomes a real, active edge until confirmed.
          Most of these come from deterministic pattern matches (a work-item key in a branch
          name, a PR title), not fuzzy guesses. Edges tagged <span className="rounded bg-purple-100 px-1 text-purple-800">LLM</span> are a
          model's own guess from reading one document (never compared against another document
          directly) — treat their stated rationale as a lead to verify, not a fact. Select the
          ones you trust and act on them together instead of one at a time.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={() => {
            setTypeFilter(undefined);
            setPage(1);
          }}
          className={`rounded px-2 py-1 text-xs ${
            typeFilter === undefined ? "bg-neutral-900 text-white" : "bg-neutral-100 text-neutral-600"
          }`}
        >
          All types
        </button>
        {types.map((t) => (
          <button
            key={t}
            onClick={() => {
              setTypeFilter(t);
              setPage(1);
            }}
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
        <>
          <BulkActionBar
            items={items}
            selected={selected}
            onSelectAll={() => setSelected(new Set(items.map((i) => i.edge.id)))}
            onClear={() => setSelected(new Set())}
            onDone={refresh}
          />
          <div className="space-y-2">
            {pagedItems.map((item) => (
              <ProposedEdgeCard
                key={item.edge.id}
                item={item}
                onDone={refresh}
                selected={selected.has(item.edge.id)}
                onToggleSelected={() => toggleSelected(item.edge.id)}
              />
            ))}
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between text-xs text-neutral-500">
              <span>
                Showing {(currentPage - 1) * PAGE_SIZE + 1}–
                {Math.min(currentPage * PAGE_SIZE, items.length)} of {items.length}
              </span>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className="rounded border border-neutral-300 px-2 py-1 disabled:opacity-30"
                >
                  ← Previous
                </button>
                <span className="px-2">
                  Page {currentPage} of {totalPages}
                </span>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                  className="rounded border border-neutral-300 px-2 py-1 disabled:opacity-30"
                >
                  Next →
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
