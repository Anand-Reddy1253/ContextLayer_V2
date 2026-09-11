import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type CatalogNode } from "@/lib/api-client";

export const CAPABILITIES = [
  "CODE",
  "DOCUMENTATION",
  "WORK_MANAGEMENT",
  "CHANGE_REVIEW",
  "BUILD_RELEASE",
  "QUALITY",
  "POLICY",
];

// Technical asset kinds worth offering as bindable containers — the
// picker below only lists these, filtering out leaf-level objects
// (individual work items, files, commits) that were only ever meant to
// be discovered through a container, not bound to directly.
const CONTAINER_KINDS = [
  "PROJECT",
  "AREA_PATH",
  "GIT_REPOSITORY",
  "REPOSITORY",
  "ORGANIZATION",
  "WIKI_PAGE",
  "PROJECT_BOARD",
  "SPACE",
  "PAGE",
];

/** Shared by the Team Contexts page and the Business Hierarchy node detail
 * panel's Relationships tab — picking technical assets to bind to a
 * context space is the same operation regardless of where you start
 * from. */
export function AddBindingForm({ spaceId, onAdded }: { spaceId: string; onAdded: () => void }) {
  const [capability, setCapability] = useState("CODE");
  const [connectionId, setConnectionId] = useState("");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const connectionsQuery = useQuery({ queryKey: ["connectors"], queryFn: api.listConnectors });
  const connection = connectionsQuery.data?.find((c) => c.id === connectionId);

  const assetsQuery = useQuery({
    queryKey: ["catalog-search", connection?.source_system, connection?.instance_id, q],
    queryFn: () =>
      api.searchCatalog({
        source_system: connection?.source_system,
        source_instance_id: connection?.instance_id,
        layer: "TECHNICAL",
        q: q || undefined,
      }),
    enabled: !!connection,
  });
  const assets = (assetsQuery.data ?? []).filter((n) => CONTAINER_KINDS.includes(n.kind));

  const toggle = (nodeId: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(nodeId)) next.delete(nodeId);
      else next.add(nodeId);
      return next;
    });
  };

  const add = useMutation({
    mutationFn: async () => {
      if (!connection) return;
      const picked = assets.filter((n) => selected.has(n.id));
      for (const node of picked) {
        await api.addContextSpaceBinding(spaceId, {
          capability,
          source_system: connection.source_system,
          source_instance_id: connection.instance_id,
          native_container: node.native_id ?? node.id,
        });
      }
    },
    onSuccess: () => {
      setSelected(new Set());
      onAdded();
    },
  });

  return (
    <div className="mt-3 space-y-2 rounded border border-dashed border-neutral-300 p-3">
      <div className="grid grid-cols-3 gap-2">
        <label className="text-xs text-neutral-600">
          Capability
          <select
            value={capability}
            onChange={(e) => setCapability(e.target.value)}
            className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-xs"
          >
            {CAPABILITIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs text-neutral-600">
          Connection
          <select
            value={connectionId}
            onChange={(e) => {
              setConnectionId(e.target.value);
              setSelected(new Set());
            }}
            className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-xs"
          >
            <option value="">— select a synced connection —</option>
            {(connectionsQuery.data ?? []).map((c) => (
              <option key={c.id} value={c.id}>
                {c.display_name} ({c.source_system}/{c.instance_id})
              </option>
            ))}
          </select>
        </label>
        <label className="text-xs text-neutral-600">
          Filter by name
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="identity-service"
            className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-xs"
          />
        </label>
      </div>

      {connection && (
        <div className="max-h-48 overflow-auto rounded border border-neutral-200">
          {assetsQuery.isLoading && (
            <div className="p-2 text-xs text-neutral-500">Loading synced assets…</div>
          )}
          {!assetsQuery.isLoading && assets.length === 0 && (
            <div className="p-2 text-xs text-neutral-500">
              No technical assets found for this connection yet — run a sync first.
            </div>
          )}
          {assets.map((node: CatalogNode) => (
            <label
              key={node.id}
              className="flex items-center gap-2 border-b border-neutral-100 px-2 py-1 text-xs last:border-b-0 hover:bg-neutral-50"
            >
              <input
                type="checkbox"
                checked={selected.has(node.id)}
                onChange={() => toggle(node.id)}
              />
              <span className="rounded bg-neutral-100 px-1.5 py-0.5">{node.kind}</span>
              <span className="font-medium">{node.name}</span>
              <span className="text-neutral-400">{node.path}</span>
            </label>
          ))}
        </div>
      )}

      <button
        onClick={() => add.mutate()}
        disabled={add.isPending || selected.size === 0}
        className="rounded border border-neutral-400 px-2 py-1 text-xs disabled:opacity-50"
      >
        {add.isPending
          ? "Adding…"
          : `Add ${selected.size || ""} binding${selected.size === 1 ? "" : "s"}`.trim()}
      </button>
      {add.isError && <div className="text-xs text-red-600">{(add.error as Error).message}</div>}
    </div>
  );
}
