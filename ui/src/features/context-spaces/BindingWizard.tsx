import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, type BusinessNode, type CatalogNode, type ContextSpace } from "@/lib/api-client";
import { CAPABILITIES } from "@/features/context-spaces/AddBindingForm";

// Same container-kind allowlist as AddBindingForm — only these are worth
// binding to directly (docs/UI.md "Team Contexts").
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

const CAPABILITY_HINTS: Record<string, string> = {
  CODE: "Repositories and source code",
  DOCUMENTATION: "Wikis, spaces, and docs",
  WORK_MANAGEMENT: "Boards, projects, and work items",
  CHANGE_REVIEW: "Pull/merge request tracking",
  BUILD_RELEASE: "CI/CD pipelines and builds",
  QUALITY: "Test plans and quality gates",
  POLICY: "Governance and compliance sources",
};

type Step = "space" | "capability" | "connection" | "assets" | "confirm";

function StepIndicator({ steps, current }: { steps: { key: Step; label: string }[]; current: Step }) {
  const currentIndex = steps.findIndex((s) => s.key === current);
  return (
    <div className="flex items-center gap-1 text-xs">
      {steps.map((s, i) => (
        <div key={s.key} className="flex items-center gap-1">
          <span
            className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 ${
              i === currentIndex
                ? "bg-neutral-900 text-white"
                : i < currentIndex
                  ? "bg-neutral-200 text-neutral-600"
                  : "bg-neutral-100 text-neutral-400"
            }`}
          >
            <span className="font-medium">{i + 1}</span>
            {s.label}
          </span>
          {i < steps.length - 1 && <span className="text-neutral-300">→</span>}
        </div>
      ))}
    </div>
  );
}

/** Guided multi-step flow for binding a business node to its technical
 * assets: pick capability → pick connection → pick container(s) → confirm.
 * Replaces a flat all-fields-at-once form (docs/UI.md "Team Contexts") —
 * each step only shows the one decision it needs, so "what does this
 * field mean" never blocks on scanning the whole form first. When the
 * node has no context space yet, an extra first step creates one inline
 * rather than sending the user to a separate screen. */
export function BindingWizard({
  node,
  existingSpace,
  onDone,
  onCancel,
}: {
  node: BusinessNode;
  existingSpace: ContextSpace | null;
  onDone: () => void;
  onCancel: () => void;
}) {
  const [spaceId, setSpaceId] = useState(existingSpace?.id ?? "");
  const [newSpaceId, setNewSpaceId] = useState("");
  const [newSpaceName, setNewSpaceName] = useState(node.name);
  const [step, setStep] = useState<Step>(existingSpace ? "capability" : "space");
  const [capability, setCapability] = useState("");
  const [connectionId, setConnectionId] = useState("");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const steps: { key: Step; label: string }[] = [
    ...(existingSpace ? [] : [{ key: "space" as Step, label: "Context space" }]),
    { key: "capability", label: "Capability" },
    { key: "connection", label: "Connection" },
    { key: "assets", label: "Assets" },
    { key: "confirm", label: "Confirm" },
  ];

  const createSpace = useMutation({
    mutationFn: () => api.createContextSpace({ id: newSpaceId, name: newSpaceName, business_node_id: node.id }),
    onSuccess: (space) => {
      setSpaceId(space.id);
      setStep("capability");
    },
  });

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
    enabled: !!connection && step === "assets",
  });
  const assets = (assetsQuery.data ?? []).filter((n) => CONTAINER_KINDS.includes(n.kind));
  const pickedAssets = assets.filter((n) => selected.has(n.id));

  const toggle = (nodeId: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(nodeId)) next.delete(nodeId);
      else next.add(nodeId);
      return next;
    });
  };

  const confirm = useMutation({
    mutationFn: async () => {
      if (!connection) return;
      for (const asset of pickedAssets) {
        await api.addContextSpaceBinding(spaceId, {
          capability,
          source_system: connection.source_system,
          source_instance_id: connection.instance_id,
          native_container: asset.native_id ?? asset.id,
        });
      }
    },
    onSuccess: onDone,
  });

  return (
    <div className="space-y-4 rounded border border-neutral-300 bg-white p-4 shadow-sm">
      <div className="flex items-center justify-between">
        <StepIndicator steps={steps} current={step} />
        <button onClick={onCancel} className="text-xs text-neutral-400 hover:text-neutral-600">
          Cancel
        </button>
      </div>

      {step === "space" && (
        <div className="space-y-2">
          <div className="text-xs text-neutral-500">
            Technical assets bind to a context space, not directly to a business node — this
            creates one anchored to <strong>{node.name}</strong> before continuing.
          </div>
          <div className="grid grid-cols-2 gap-2">
            <label className="text-xs text-neutral-600">
              Id (e.g. talentflow/identity)
              <input
                value={newSpaceId}
                onChange={(e) => setNewSpaceId(e.target.value)}
                className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-xs"
              />
            </label>
            <label className="text-xs text-neutral-600">
              Name
              <input
                value={newSpaceName}
                onChange={(e) => setNewSpaceName(e.target.value)}
                className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-xs"
              />
            </label>
          </div>
          {createSpace.isError && (
            <div className="text-xs text-red-600">{(createSpace.error as Error).message}</div>
          )}
          <button
            onClick={() => createSpace.mutate()}
            disabled={createSpace.isPending || !newSpaceId || !newSpaceName}
            className="rounded bg-neutral-900 px-3 py-1.5 text-xs text-white disabled:opacity-50"
          >
            {createSpace.isPending ? "Creating…" : "Create & continue"}
          </button>
        </div>
      )}

      {step === "capability" && (
        <div className="space-y-2">
          <div className="text-xs text-neutral-500">What kind of technical asset are you binding?</div>
          <div className="grid grid-cols-2 gap-2">
            {CAPABILITIES.map((c) => (
              <button
                key={c}
                onClick={() => setCapability(c)}
                className={`rounded border p-2 text-left text-xs ${
                  capability === c
                    ? "border-neutral-900 bg-neutral-50"
                    : "border-neutral-200 hover:bg-neutral-50"
                }`}
              >
                <div className="font-medium">{c}</div>
                <div className="text-neutral-500">{CAPABILITY_HINTS[c] ?? ""}</div>
              </button>
            ))}
          </div>
        </div>
      )}

      {step === "connection" && (
        <div className="space-y-2">
          <div className="text-xs text-neutral-500">Which synced connection has the asset?</div>
          {connectionsQuery.data?.length === 0 && (
            <div className="text-xs text-amber-600">
              No connections yet — set one up on the Connectors page first.
            </div>
          )}
          <div className="space-y-1">
            {(connectionsQuery.data ?? []).map((c) => (
              <button
                key={c.id}
                onClick={() => setConnectionId(c.id)}
                className={`block w-full rounded border p-2 text-left text-xs ${
                  connectionId === c.id
                    ? "border-neutral-900 bg-neutral-50"
                    : "border-neutral-200 hover:bg-neutral-50"
                }`}
              >
                <div className="font-medium">{c.display_name}</div>
                <div className="text-neutral-400">
                  {c.source_system}/{c.instance_id} · {c.mode}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {step === "assets" && (
        <div className="space-y-2">
          <label className="block text-xs text-neutral-600">
            Filter by name
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="identity-service"
              className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-xs"
            />
          </label>
          <div className="max-h-56 overflow-auto rounded border border-neutral-200">
            {assetsQuery.isLoading && (
              <div className="p-2 text-xs text-neutral-500">Loading synced assets…</div>
            )}
            {!assetsQuery.isLoading && assets.length === 0 && (
              <div className="p-2 text-xs text-neutral-500">
                No technical assets found for this connection yet — run a sync first.
              </div>
            )}
            {assets.map((n: CatalogNode) => (
              <label
                key={n.id}
                className="flex items-center gap-2 border-b border-neutral-100 px-2 py-1 text-xs last:border-b-0 hover:bg-neutral-50"
              >
                <input type="checkbox" checked={selected.has(n.id)} onChange={() => toggle(n.id)} />
                <span className="rounded bg-neutral-100 px-1.5 py-0.5">{n.kind}</span>
                <span className="font-medium">{n.name}</span>
                <span className="text-neutral-400">{n.path}</span>
              </label>
            ))}
          </div>
          <div className="text-xs text-neutral-500">{selected.size} selected</div>
        </div>
      )}

      {step === "confirm" && (
        <div className="space-y-2 text-xs">
          <div>
            Binding <span className="rounded bg-neutral-100 px-1.5 py-0.5 font-medium">{capability}</span>{" "}
            from <strong>{connection?.display_name}</strong> to <strong>{node.name}</strong>:
          </div>
          <ul className="list-disc space-y-0.5 pl-4 text-neutral-600">
            {pickedAssets.map((a) => (
              <li key={a.id}>
                {a.name} <span className="text-neutral-400">({a.kind})</span>
              </li>
            ))}
          </ul>
          {confirm.isError && (
            <div className="text-red-600">{(confirm.error as Error).message}</div>
          )}
        </div>
      )}

      <div className="flex items-center gap-2 border-t border-neutral-100 pt-3">
        {steps.findIndex((s) => s.key === step) > 0 && (
          <button
            onClick={() => setStep(steps[steps.findIndex((s) => s.key === step) - 1].key)}
            className="rounded border border-neutral-300 px-3 py-1.5 text-xs"
          >
            Back
          </button>
        )}
        {step === "capability" && (
          <button
            onClick={() => setStep("connection")}
            disabled={!capability}
            className="rounded bg-neutral-900 px-3 py-1.5 text-xs text-white disabled:opacity-50"
          >
            Next
          </button>
        )}
        {step === "connection" && (
          <button
            onClick={() => setStep("assets")}
            disabled={!connectionId}
            className="rounded bg-neutral-900 px-3 py-1.5 text-xs text-white disabled:opacity-50"
          >
            Next
          </button>
        )}
        {step === "assets" && (
          <button
            onClick={() => setStep("confirm")}
            disabled={selected.size === 0}
            className="rounded bg-neutral-900 px-3 py-1.5 text-xs text-white disabled:opacity-50"
          >
            Next
          </button>
        )}
        {step === "confirm" && (
          <button
            onClick={() => confirm.mutate()}
            disabled={confirm.isPending}
            className="rounded bg-neutral-900 px-3 py-1.5 text-xs text-white disabled:opacity-50"
          >
            {confirm.isPending
              ? "Creating…"
              : `Create ${pickedAssets.length} binding${pickedAssets.length === 1 ? "" : "s"}`}
          </button>
        )}
      </div>
    </div>
  );
}
