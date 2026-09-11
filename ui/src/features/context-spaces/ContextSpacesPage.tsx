import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type ContextSpace } from "@/lib/api-client";
import { AddBindingForm } from "@/features/context-spaces/AddBindingForm";

function NewSpaceForm({ onCreated }: { onCreated: () => void }) {
  const orgTreeQuery = useQuery({ queryKey: ["org-tree"], queryFn: api.getOrgTree });
  const [id, setId] = useState("");
  const [name, setName] = useState("");
  const [businessNodeId, setBusinessNodeId] = useState("");
  const [product, setProduct] = useState("");
  const [teams, setTeams] = useState("");
  const [services, setServices] = useState("");

  const create = useMutation({
    mutationFn: () =>
      api.createContextSpace({
        id,
        name,
        business_node_id: businessNodeId,
        product: product || null,
        teams: teams ? teams.split(",").map((t) => t.trim()) : [],
        services: services ? services.split(",").map((s) => s.trim()) : [],
      }),
    onSuccess: () => {
      setId("");
      setName("");
      onCreated();
    },
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        create.mutate();
      }}
      className="space-y-3 rounded border border-neutral-200 p-4"
    >
      <div className="text-sm font-medium">Create context space (business ↔ technical correlation)</div>
      <div className="rounded bg-neutral-50 p-2 text-xs text-neutral-500">
        This step just creates the container. Once it's created, it appears as a card below with
        a technical-asset picker — that's where you pick a connection (GitHub, ADO, Confluence,
        ...) and check as many repos/work items/wiki spaces as apply. You can repeat that for
        every source system and add as many as this team actually owns.
      </div>
      <div className="grid grid-cols-2 gap-3">
        <label className="text-xs text-neutral-600">
          Id (e.g. talentflow/identity)
          <input
            value={id}
            onChange={(e) => setId(e.target.value)}
            required
            className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
          />
        </label>
        <label className="text-xs text-neutral-600">
          Name
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
          />
        </label>
        <label className="col-span-2 text-xs text-neutral-600">
          Business node (the team/squad this space represents)
          <select
            value={businessNodeId}
            onChange={(e) => setBusinessNodeId(e.target.value)}
            required
            className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
          >
            <option value="">— select —</option>
            {(orgTreeQuery.data ?? []).map((n) => (
              <option key={n.id} value={n.id}>
                {n.path}
              </option>
            ))}
          </select>
          {(orgTreeQuery.data ?? []).length === 0 && (
            <span className="text-red-600">
              No business nodes yet — create one on the Business Hierarchy screen first.
            </span>
          )}
        </label>
        <label className="text-xs text-neutral-600">
          Product
          <input
            value={product}
            onChange={(e) => setProduct(e.target.value)}
            className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
          />
        </label>
        <label className="text-xs text-neutral-600">
          Teams (comma-separated)
          <input
            value={teams}
            onChange={(e) => setTeams(e.target.value)}
            className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
          />
        </label>
        <label className="col-span-2 text-xs text-neutral-600">
          Services (comma-separated)
          <input
            value={services}
            onChange={(e) => setServices(e.target.value)}
            className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
          />
        </label>
      </div>
      <button
        type="submit"
        disabled={create.isPending || !id || !name || !businessNodeId}
        className="rounded bg-neutral-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
      >
        {create.isPending ? "Creating…" : "Create context space"}
      </button>
      {create.isError && (
        <div className="text-sm text-red-600">{(create.error as Error).message}</div>
      )}
    </form>
  );
}

function SpaceCard({ space }: { space: ContextSpace }) {
  const queryClient = useQueryClient();
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const reconcileQuery = useQuery({
    queryKey: ["reconcile", space.id],
    queryFn: () => api.reconcileContextSpace(space.id),
    enabled: false,
  });
  const removeBinding = useMutation({
    mutationFn: (bindingId: string) => api.removeContextSpaceBinding(space.id, bindingId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["context-spaces"] }),
  });
  const deleteSpace = useMutation({
    mutationFn: () => api.deleteContextSpace(space.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["context-spaces"] }),
  });

  const resolvedByBindingId = new Map(
    (reconcileQuery.data?.results ?? []).map((r) => [r.binding_id, r.resolved])
  );

  return (
    <div className="rounded border border-neutral-200 p-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="font-medium">{space.name}</div>
          <div className="text-xs text-neutral-500">
            {space.id} · product: {space.product ?? "—"} · teams: {space.teams.join(", ") || "—"}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => reconcileQuery.refetch()}
            className="rounded border border-neutral-400 px-3 py-1.5 text-sm"
          >
            Check correlation status
          </button>
          {confirmingDelete ? (
            <span className="flex items-center gap-1 text-xs">
              <button
                onClick={() => deleteSpace.mutate()}
                disabled={deleteSpace.isPending}
                className="rounded bg-red-600 px-2 py-1 text-white disabled:opacity-50"
              >
                {deleteSpace.isPending ? "Deleting…" : "Confirm delete"}
              </button>
              <button
                onClick={() => setConfirmingDelete(false)}
                className="rounded border border-neutral-300 px-2 py-1"
              >
                Cancel
              </button>
            </span>
          ) : (
            <button
              onClick={() => setConfirmingDelete(true)}
              className="rounded border border-red-300 px-3 py-1.5 text-sm text-red-600"
            >
              Delete
            </button>
          )}
        </div>
      </div>
      {deleteSpace.isError && (
        <div className="mt-2 text-xs text-red-600">{(deleteSpace.error as Error).message}</div>
      )}

      {reconcileQuery.data && (
        <div
          className={`mt-2 rounded p-2 text-xs ${
            reconcileQuery.data.all_resolved ? "bg-green-50 text-green-800" : "bg-amber-50 text-amber-800"
          }`}
        >
          {reconcileQuery.data.results.filter((r) => r.resolved).length}/
          {reconcileQuery.data.results.length} bindings resolve to synced technical nodes.
        </div>
      )}

      <table className="mt-3 w-full text-left text-xs">
        <thead className="text-neutral-500">
          <tr>
            <th className="py-1">Capability</th>
            <th>Source</th>
            <th>Native container</th>
            <th>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {space.bindings.map((b) => (
            <tr key={b.id} className="border-t border-neutral-100">
              <td className="py-1">{b.capability}</td>
              <td>
                {b.source_system}/{b.source_instance_id}
              </td>
              <td>{b.native_container}</td>
              <td>
                {resolvedByBindingId.has(b.id) ? (
                  resolvedByBindingId.get(b.id) ? (
                    <span className="text-green-700">resolved</span>
                  ) : (
                    <span className="text-amber-700">unresolved</span>
                  )
                ) : (
                  <span className="text-neutral-400">—</span>
                )}
              </td>
              <td>
                <button
                  onClick={() => removeBinding.mutate(b.id)}
                  className="text-neutral-400 hover:text-red-600"
                >
                  remove
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <AddBindingForm
        spaceId={space.id}
        onAdded={() => queryClient.invalidateQueries({ queryKey: ["context-spaces"] })}
      />
    </div>
  );
}

export function ContextSpacesPage() {
  const queryClient = useQueryClient();
  const spacesQuery = useQuery({ queryKey: ["context-spaces"], queryFn: api.listContextSpaces });

  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-xl font-semibold">Team Contexts</h1>
      <p className="text-sm text-neutral-500">
        The logical layer: draw the boundary between a business team and its technical assets
        across connectors — this is what turns a team name into a searchable scope.
      </p>

      <NewSpaceForm
        onCreated={() => queryClient.invalidateQueries({ queryKey: ["context-spaces"] })}
      />

      <div className="space-y-3">
        {spacesQuery.isLoading && <div className="text-sm text-neutral-500">Loading…</div>}
        {spacesQuery.data?.length === 0 && (
          <div className="text-sm text-neutral-500">No context spaces yet.</div>
        )}
        {spacesQuery.data?.map((s) => (
          <SpaceCard key={s.id} space={s} />
        ))}
      </div>
    </div>
  );
}
