import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type BusinessNode, type ContextSpace } from "@/lib/api-client";
import { BindingWizard } from "@/features/context-spaces/BindingWizard";

const KINDS = ["ORG", "DIVISION", "TRIBE", "SQUAD", "TEAM", "PRODUCT", "SERVICE"];

function TreeNode({
  node,
  childrenByParent,
  depth,
  selectedId,
  onSelect,
}: {
  node: BusinessNode;
  childrenByParent: Map<string | null, BusinessNode[]>;
  depth: number;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  const children = childrenByParent.get(node.id) ?? [];
  const selected = node.id === selectedId;
  return (
    <div>
      <div
        onClick={() => onSelect(node.id)}
        className={`flex cursor-pointer items-center gap-2 rounded px-2 py-1 ${
          selected ? "bg-neutral-900 text-white" : "hover:bg-neutral-50"
        }`}
        style={{ marginLeft: depth * 20 }}
      >
        <span
          className={`rounded px-1.5 py-0.5 text-xs ${
            selected ? "bg-white/20" : "bg-neutral-100"
          }`}
        >
          {node.kind}
        </span>
        <span className="text-sm font-medium">{node.name}</span>
        {node.owners.length > 0 && (
          <span className={`text-xs ${selected ? "text-white/70" : "text-neutral-400"}`}>
            {node.owners.join(", ")}
          </span>
        )}
      </div>
      {children.map((c) => (
        <TreeNode
          key={c.id}
          node={c}
          childrenByParent={childrenByParent}
          depth={depth + 1}
          selectedId={selectedId}
          onSelect={onSelect}
        />
      ))}
    </div>
  );
}

function NewNodeForm({ nodes, onCreated }: { nodes: BusinessNode[]; onCreated: () => void }) {
  const [parentId, setParentId] = useState<string>("");
  const [kind, setKind] = useState("SQUAD");
  const [name, setName] = useState("");
  const [owners, setOwners] = useState("");

  const create = useMutation({
    mutationFn: () =>
      api.createBusinessNode({
        parent_id: parentId || null,
        kind,
        name,
        owners: owners ? owners.split(",").map((o) => o.trim()) : [],
      }),
    onSuccess: () => {
      setName("");
      setOwners("");
      onCreated();
    },
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        create.mutate();
      }}
      className="grid grid-cols-4 items-end gap-3 rounded border border-neutral-200 p-4"
    >
      <label className="text-xs text-neutral-600">
        Parent (empty = new root)
        <select
          value={parentId}
          onChange={(e) => setParentId(e.target.value)}
          className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
        >
          <option value="">— none (root) —</option>
          {nodes.map((n) => (
            <option key={n.id} value={n.id}>
              {n.path}
            </option>
          ))}
        </select>
      </label>
      <label className="text-xs text-neutral-600">
        Kind
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value)}
          className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
        >
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
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
      <label className="text-xs text-neutral-600">
        Owners (comma-separated)
        <input
          value={owners}
          onChange={(e) => setOwners(e.target.value)}
          className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
        />
      </label>
      <button
        type="submit"
        disabled={create.isPending || !name}
        className="col-span-4 rounded bg-neutral-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
      >
        {create.isPending ? "Creating…" : "Create node"}
      </button>
      {create.isError && (
        <div className="col-span-4 text-sm text-red-600">{(create.error as Error).message}</div>
      )}
    </form>
  );
}

type DetailTab = "overview" | "context" | "hierarchy" | "relationships";

const CRITICALITY_TIERS = ["prod-critical", "business-critical", "standard", "internal-tool"];

function OverviewTab({ node }: { node: BusinessNode }) {
  const attrs = node.attributes ?? {};
  const hasContext =
    attrs.criticality_tier || (attrs.compliance_scope?.length ?? 0) > 0 || attrs.communication_channel;

  return (
    <div className="space-y-4">
      <div>
        <div className="text-xs font-medium text-neutral-500">Description</div>
        <div className="mt-1 text-sm">{node.description || "—"}</div>
      </div>
      <div className="grid grid-cols-2 gap-4">
        <div>
          <div className="text-xs font-medium text-neutral-500">Kind</div>
          <div className="mt-1 text-sm">{node.kind}</div>
        </div>
        <div>
          <div className="text-xs font-medium text-neutral-500">Owners</div>
          <div className="mt-1 text-sm">{node.owners.join(", ") || "—"}</div>
        </div>
        <div className="col-span-2">
          <div className="text-xs font-medium text-neutral-500">Path</div>
          <div className="mt-1 font-mono text-xs text-neutral-600">{node.path}</div>
        </div>
      </div>
      {hasContext && (
        <div className="rounded border border-neutral-200 p-3">
          <div className="text-xs font-medium text-neutral-500">Business context</div>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
            {attrs.criticality_tier && (
              <span className="rounded bg-amber-100 px-1.5 py-0.5 text-amber-800">
                {attrs.criticality_tier}
              </span>
            )}
            {(attrs.compliance_scope ?? []).map((c) => (
              <span key={c} className="rounded bg-red-100 px-1.5 py-0.5 text-red-800">
                {c}
              </span>
            ))}
            {attrs.communication_channel && (
              <span className="rounded bg-neutral-100 px-1.5 py-0.5 text-neutral-700">
                {attrs.communication_channel.platform}: {attrs.communication_channel.channel}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function csvToList(s: string): string[] {
  return s
    .split(",")
    .map((v) => v.trim())
    .filter(Boolean);
}

/** The "business context" fields (docs/UI.md "Business Hierarchy") — not
 * a separate node type, just attributes on this same business node.
 * Whatever's set here shows up as `business_context` on every Search
 * card whose technical asset is bound (directly, or via an ancestor
 * container) to this node's own context space, and (once the
 * context-pack compiler exists) is a candidate for hard_constraints —
 * e.g. a compliance scope becoming "get sign-off before touching this." */
function BusinessContextTab({ node }: { node: BusinessNode }) {
  const queryClient = useQueryClient();
  const attrs = node.attributes ?? {};
  const [criticalityTier, setCriticalityTier] = useState(attrs.criticality_tier ?? "");
  const [complianceScope, setComplianceScope] = useState((attrs.compliance_scope ?? []).join(", "));
  const [stakeholders, setStakeholders] = useState((attrs.stakeholders ?? []).join(", "));
  const [channelPlatform, setChannelPlatform] = useState(attrs.communication_channel?.platform ?? "");
  const [channelName, setChannelName] = useState(attrs.communication_channel?.channel ?? "");
  const [channelUrl, setChannelUrl] = useState(attrs.communication_channel?.url ?? "");

  const save = useMutation({
    mutationFn: () =>
      api.updateBusinessNode(node.id, {
        criticality_tier: criticalityTier || null,
        compliance_scope: complianceScope ? csvToList(complianceScope) : null,
        stakeholders: stakeholders ? csvToList(stakeholders) : null,
        communication_channel:
          channelPlatform && channelName
            ? { platform: channelPlatform, channel: channelName, url: channelUrl || undefined }
            : null,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["org-tree"] }),
  });

  return (
    <div className="space-y-4">
      <label className="block text-xs text-neutral-600">
        Criticality tier
        <select
          value={criticalityTier}
          onChange={(e) => setCriticalityTier(e.target.value)}
          className="mt-1 block w-full max-w-xs rounded border border-neutral-300 px-2 py-1 text-sm"
        >
          <option value="">— unset —</option>
          {CRITICALITY_TIERS.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </label>

      <label className="block text-xs text-neutral-600">
        Compliance scope
        <input
          value={complianceScope}
          onChange={(e) => setComplianceScope(e.target.value)}
          placeholder="PCI, SOC2, GDPR"
          className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
        />
        <span className="mt-1 block text-neutral-400">Comma-separated.</span>
      </label>

      <label className="block text-xs text-neutral-600">
        Stakeholders
        <input
          value={stakeholders}
          onChange={(e) => setStakeholders(e.target.value)}
          placeholder="VP Eng: Jane Doe, Security lead: John Smith"
          className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
        />
        <span className="mt-1 block text-neutral-400">Comma-separated. Freeform — role, name, or both.</span>
      </label>

      <div>
        <div className="text-xs font-medium text-neutral-700">Communication channel</div>
        <div className="mt-1 grid grid-cols-3 gap-2">
          <label className="text-xs text-neutral-600">
            Platform
            <select
              value={channelPlatform}
              onChange={(e) => setChannelPlatform(e.target.value)}
              className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
            >
              <option value="">— unset —</option>
              <option value="teams">Microsoft Teams</option>
              <option value="slack">Slack</option>
            </select>
          </label>
          <label className="text-xs text-neutral-600">
            Channel
            <input
              value={channelName}
              onChange={(e) => setChannelName(e.target.value)}
              placeholder="#identity-squad"
              className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
            />
          </label>
          <label className="text-xs text-neutral-600">
            Link (optional)
            <input
              value={channelUrl}
              onChange={(e) => setChannelUrl(e.target.value)}
              placeholder="https://teams.microsoft.com/..."
              className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
            />
          </label>
        </div>
        {channelPlatform === "teams" && (
          <div className="mt-1 text-xs text-neutral-400">
            This is just a reference — synced message content shows up on the Asset Catalog and in
            Search once a Teams connection is bound to this node's context space.
          </div>
        )}
      </div>

      <button
        onClick={() => save.mutate()}
        disabled={save.isPending}
        className="rounded bg-neutral-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
      >
        {save.isPending ? "Saving…" : "Save"}
      </button>
      {save.isError && <div className="text-xs text-red-600">{(save.error as Error).message}</div>}
      {save.isSuccess && <div className="text-xs text-green-700">Saved.</div>}
    </div>
  );
}

function HierarchyTab({
  node,
  nodesById,
  childrenByParent,
  onSelect,
}: {
  node: BusinessNode;
  nodesById: Map<string, BusinessNode>;
  childrenByParent: Map<string | null, BusinessNode[]>;
  onSelect: (id: string) => void;
}) {
  const ancestors: BusinessNode[] = [];
  let cursor = node.parent_id;
  while (cursor) {
    const parent = nodesById.get(cursor);
    if (!parent) break;
    ancestors.unshift(parent);
    cursor = parent.parent_id;
  }
  const children = childrenByParent.get(node.id) ?? [];

  return (
    <div className="space-y-4">
      <div>
        <div className="text-xs font-medium text-neutral-500">Ancestors (top level first)</div>
        <div className="mt-1 flex flex-wrap items-center gap-1 text-sm">
          {ancestors.length === 0 && <span className="text-neutral-400">This is a top-level node.</span>}
          {ancestors.map((a, i) => (
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
          This node — {node.kind}: {node.name}
        </div>
      </div>
      <div>
        <div className="text-xs font-medium text-neutral-500">
          Direct children ({children.length})
        </div>
        {children.length === 0 ? (
          <div className="mt-1 text-sm text-neutral-400">No child nodes.</div>
        ) : (
          <div className="mt-1 space-y-1">
            {children.map((c) => (
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
    </div>
  );
}

function RelationshipsTab({ node }: { node: BusinessNode }) {
  const queryClient = useQueryClient();
  const spacesQuery = useQuery({ queryKey: ["context-spaces"], queryFn: api.listContextSpaces });
  const spaces = (spacesQuery.data ?? []).filter((s) => s.business_node_id === node.id);
  const [wizardOpenFor, setWizardOpenFor] = useState<string | "new" | null>(null);

  const reconcile = useMutation({
    mutationFn: (spaceId: string) => api.reconcileContextSpace(spaceId),
  });

  const invalidateSpaces = () => queryClient.invalidateQueries({ queryKey: ["context-spaces"] });

  if (spacesQuery.isLoading) return <div className="text-sm text-neutral-500">Loading…</div>;

  if (spaces.length === 0) {
    if (wizardOpenFor === null) {
      return (
        <div className="rounded border border-dashed border-neutral-300 p-4 text-center">
          <div className="mb-2 text-xs text-neutral-500">
            No technical assets are bound to <strong>{node.name}</strong> yet.
          </div>
          <button
            onClick={() => setWizardOpenFor("new")}
            className="rounded bg-neutral-900 px-3 py-1.5 text-xs text-white"
          >
            + Bind a technical asset
          </button>
        </div>
      );
    }
    return (
      <BindingWizard
        node={node}
        existingSpace={null}
        onDone={() => {
          invalidateSpaces();
          setWizardOpenFor(null);
        }}
        onCancel={() => setWizardOpenFor(null)}
      />
    );
  }

  return (
    <div className="space-y-3">
      {spaces.map((space: ContextSpace) => {
        const result = reconcile.data && reconcile.variables === space.id ? reconcile.data : null;
        const resolvedByBindingId = new Map((result?.results ?? []).map((r) => [r.binding_id, r.resolved]));
        return (
          <div key={space.id} className="rounded border border-neutral-200 p-3">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm font-medium">{space.name}</div>
                <div className="text-xs text-neutral-500">{space.id}</div>
              </div>
              <button
                onClick={() => reconcile.mutate(space.id)}
                disabled={reconcile.isPending}
                className="rounded border border-neutral-400 px-2 py-1 text-xs disabled:opacity-50"
              >
                Check status
              </button>
            </div>
            <div className="mt-2 space-y-1">
              {space.bindings.map((b) => (
                <div
                  key={b.id}
                  className="flex items-center justify-between rounded bg-neutral-50 px-2 py-1 text-xs"
                >
                  <span>
                    <span className="rounded bg-neutral-200 px-1.5 py-0.5">{b.capability}</span>{" "}
                    {b.source_system}/{b.source_instance_id} · {b.native_container}
                  </span>
                  {resolvedByBindingId.has(b.id) && (
                    <span
                      className={resolvedByBindingId.get(b.id) ? "text-green-700" : "text-amber-700"}
                    >
                      {resolvedByBindingId.get(b.id) ? "resolved" : "unresolved"}
                    </span>
                  )}
                </div>
              ))}
              {space.bindings.length === 0 && (
                <div className="text-xs text-neutral-400">No technical assets assigned yet.</div>
              )}
            </div>
            {wizardOpenFor === space.id ? (
              <div className="mt-3">
                <BindingWizard
                  node={node}
                  existingSpace={space}
                  onDone={() => {
                    invalidateSpaces();
                    setWizardOpenFor(null);
                  }}
                  onCancel={() => setWizardOpenFor(null)}
                />
              </div>
            ) : (
              <button
                onClick={() => setWizardOpenFor(space.id)}
                className="mt-3 rounded border border-neutral-400 px-2 py-1 text-xs"
              >
                + Bind a technical asset
              </button>
            )}
          </div>
        );
      })}
    </div>
  );
}

function NodeDetailPanel({
  node,
  nodesById,
  childrenByParent,
  onSelect,
  onDeleted,
}: {
  node: BusinessNode;
  nodesById: Map<string, BusinessNode>;
  childrenByParent: Map<string | null, BusinessNode[]>;
  onSelect: (id: string) => void;
  onDeleted: () => void;
}) {
  const [tab, setTab] = useState<DetailTab>("overview");
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const queryClient = useQueryClient();
  const deleteNode = useMutation({
    mutationFn: () => api.deleteBusinessNode(node.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["org-tree"] });
      onDeleted();
    },
  });
  const tabs: { key: DetailTab; label: string }[] = [
    { key: "overview", label: "Overview" },
    { key: "context", label: "Business Context" },
    { key: "hierarchy", label: "Hierarchy" },
    { key: "relationships", label: "Relationships" },
  ];

  return (
    <div className="rounded border border-neutral-200">
      <div className="flex items-center justify-between border-b border-neutral-200 p-4">
        <div>
          <div className="text-xs text-neutral-400">{node.kind}</div>
          <div className="text-lg font-semibold">{node.name}</div>
        </div>
        {confirmingDelete ? (
          <span className="flex items-center gap-1 text-xs">
            <span className="text-neutral-500">Delete this node?</span>
            <button
              onClick={() => deleteNode.mutate()}
              disabled={deleteNode.isPending}
              className="rounded bg-red-600 px-2 py-1 text-white disabled:opacity-50"
            >
              {deleteNode.isPending ? "Deleting…" : "Yes, delete"}
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
            className="text-xs text-red-600 hover:underline"
          >
            Delete
          </button>
        )}
      </div>
      {deleteNode.isError && (
        <div className="border-b border-neutral-200 p-2 text-xs text-red-600">
          {(deleteNode.error as Error).message}
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
        {tab === "context" && <BusinessContextTab node={node} />}
        {tab === "hierarchy" && (
          <HierarchyTab
            node={node}
            nodesById={nodesById}
            childrenByParent={childrenByParent}
            onSelect={onSelect}
          />
        )}
        {tab === "relationships" && <RelationshipsTab node={node} />}
      </div>
    </div>
  );
}

export function BusinessTreePage() {
  const queryClient = useQueryClient();
  const treeQuery = useQuery({ queryKey: ["org-tree"], queryFn: api.getOrgTree });
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const seed = useMutation({
    mutationFn: api.seedExampleOrgTree,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["org-tree"] }),
  });

  const nodes = treeQuery.data ?? [];
  const nodesById = new Map(nodes.map((n) => [n.id, n]));
  const childrenByParent = new Map<string | null, BusinessNode[]>();
  for (const n of nodes) {
    const key = n.parent_id;
    if (!childrenByParent.has(key)) childrenByParent.set(key, []);
    childrenByParent.get(key)!.push(n);
  }
  const roots = childrenByParent.get(null) ?? [];
  const selectedNode = selectedId ? nodesById.get(selectedId) ?? null : null;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Business Hierarchy</h1>
        {nodes.length === 0 && (
          <button
            onClick={() => seed.mutate()}
            disabled={seed.isPending}
            className="rounded border border-neutral-400 px-3 py-1.5 text-sm"
          >
            {seed.isPending ? "Seeding…" : "Load example tree (ACME)"}
          </button>
        )}
      </div>

      <NewNodeForm
        nodes={nodes}
        onCreated={() => queryClient.invalidateQueries({ queryKey: ["org-tree"] })}
      />

      <div className="grid grid-cols-5 gap-6">
        <div className="col-span-2 rounded border border-neutral-200 p-3">
          {treeQuery.isLoading && <div className="text-sm text-neutral-500">Loading…</div>}
          {nodes.length === 0 && !treeQuery.isLoading && (
            <div className="text-sm text-neutral-500">
              No business nodes yet — create one above, or load the ACME example.
            </div>
          )}
          {roots.map((n) => (
            <TreeNode
              key={n.id}
              node={n}
              childrenByParent={childrenByParent}
              depth={0}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
          ))}
        </div>

        <div className="col-span-3">
          {selectedNode ? (
            <NodeDetailPanel
              node={selectedNode}
              nodesById={nodesById}
              childrenByParent={childrenByParent}
              onSelect={setSelectedId}
              onDeleted={() => setSelectedId(null)}
            />
          ) : (
            <div className="flex h-full items-center justify-center rounded border border-dashed border-neutral-300 p-8 text-sm text-neutral-400">
              Select a node from the tree to see its overview, hierarchy, and relationships to
              technical assets.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
