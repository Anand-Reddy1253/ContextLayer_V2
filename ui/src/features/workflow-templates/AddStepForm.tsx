import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type CatalogNode, type ContextSpace } from "@/lib/api-client";
import { ASSET_TYPE_LABELS, VENDOR_LABELS, assetsForContextSpace } from "@/features/workflow-templates/aiAssetPicker";

/** Picks an AI_ASSET to add as the next step of an existing workflow
 * template, scoped to the template's own context space's CODE-capability
 * repositories. For picking steps while *creating* a template, see
 * NewTemplateForm in WorkflowTemplatesPage.tsx — this form is only for
 * adding more steps to a template that already exists. */
export function AddStepForm({
  templateId,
  space,
  onAdded,
}: {
  templateId: string;
  space: ContextSpace;
  onAdded: () => void;
}) {
  const queryClient = useQueryClient();
  const [instructionsByAssetId, setInstructionsByAssetId] = useState<Record<string, string>>({});

  const assetsQuery = useQuery({
    queryKey: ["catalog", "search", { kind: "AI_ASSET" }],
    queryFn: () => api.searchCatalog({ kind: "AI_ASSET" }),
  });

  const hasCodeBinding = space.bindings.some((b) => b.capability === "CODE");
  const assets = assetsForContextSpace(assetsQuery.data ?? [], space);

  const addStep = useMutation({
    mutationFn: (asset: CatalogNode) =>
      api.addWorkflowStep(templateId, {
        source_system: asset.source_system!,
        source_instance_id: asset.source_instance_id!,
        native_id: asset.native_id!,
        instructions: instructionsByAssetId[asset.id]?.trim() || null,
      }),
    onSuccess: (_step, asset) => {
      setInstructionsByAssetId((prev) => {
        const next = { ...prev };
        delete next[asset.id];
        return next;
      });
      queryClient.invalidateQueries({ queryKey: ["workflow-templates"] });
      onAdded();
    },
  });

  if (!hasCodeBinding) {
    return (
      <div className="mt-3 rounded border border-dashed border-neutral-300 p-3 text-xs text-neutral-500">
        This context space has no CODE bindings yet — add a repository binding on the Team
        Contexts screen before adding steps here.
      </div>
    );
  }

  return (
    <div className="mt-3 space-y-2 rounded border border-dashed border-neutral-300 p-3">
      <div className="text-xs font-medium text-neutral-600">Add a step</div>
      {assetsQuery.isLoading && (
        <div className="text-xs text-neutral-500">Loading AI assets…</div>
      )}
      {assetsQuery.isError && (
        <div className="text-xs text-red-600">Failed to load AI assets.</div>
      )}
      {!assetsQuery.isLoading && !assetsQuery.isError && assets.length === 0 && (
        <div className="text-xs text-neutral-500">
          No AI assets found in this context space's repositories — enable "AI Explorer" as an
          entity type on the relevant connector and run a sync.
        </div>
      )}
      <div className="max-h-56 overflow-auto rounded border border-neutral-200">
        {assets.map((asset) => (
          <div
            key={asset.id}
            className="flex flex-wrap items-center gap-2 border-b border-neutral-100 px-2 py-1.5 text-xs last:border-b-0 hover:bg-neutral-50"
          >
            <span className="rounded bg-neutral-100 px-1.5 py-0.5 shrink-0">
              {VENDOR_LABELS[String(asset.attributes.vendor ?? "")] ??
                String(asset.attributes.vendor ?? "")}
            </span>
            <span className="rounded bg-neutral-100 px-1.5 py-0.5 shrink-0">
              {ASSET_TYPE_LABELS[String(asset.attributes.asset_type ?? "")] ??
                String(asset.attributes.asset_type ?? "")}
            </span>
            <span className="font-medium">{asset.name}</span>
            <span className="truncate text-neutral-400">{String(asset.attributes.path ?? "")}</span>
            <input
              value={instructionsByAssetId[asset.id] ?? ""}
              onChange={(e) =>
                setInstructionsByAssetId((prev) => ({ ...prev, [asset.id]: e.target.value }))
              }
              placeholder="Note (optional)"
              className="ml-auto min-w-0 flex-1 rounded border border-neutral-200 px-1.5 py-0.5"
            />
            <button
              onClick={() => addStep.mutate(asset)}
              disabled={addStep.isPending}
              className="shrink-0 rounded border border-neutral-400 px-2 py-0.5 disabled:opacity-50"
            >
              Add
            </button>
          </div>
        ))}
      </div>
      {addStep.isError && (
        <div className="text-xs text-red-600">{(addStep.error as Error).message}</div>
      )}
    </div>
  );
}
