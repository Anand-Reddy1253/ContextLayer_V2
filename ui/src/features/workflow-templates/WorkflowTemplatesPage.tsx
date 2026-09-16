import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, type CatalogNode, type ContextSpace, type WorkflowTemplate } from "@/lib/api-client";
import { AddStepForm } from "@/features/workflow-templates/AddStepForm";
import { ASSET_TYPE_LABELS, VENDOR_LABELS, assetsForContextSpace } from "@/features/workflow-templates/aiAssetPicker";
import { PipelineStrip, type PipelineStripItem } from "@/features/workflow-templates/PipelineStrip";

interface StagedStep {
  asset: CatalogNode;
  instructions: string;
}

function NewTemplateForm({ onCreated }: { onCreated: () => void }) {
  const spacesQuery = useQuery({ queryKey: ["context-spaces"], queryFn: api.listContextSpaces });
  const assetsQuery = useQuery({
    queryKey: ["catalog", "search", { kind: "AI_ASSET" }],
    queryFn: () => api.searchCatalog({ kind: "AI_ASSET" }),
  });
  const [contextSpaceId, setContextSpaceId] = useState("");
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [staged, setStaged] = useState<StagedStep[]>([]);

  const space = spacesQuery.data?.find((s) => s.id === contextSpaceId);
  const hasCodeBinding = !!space?.bindings.some((b) => b.capability === "CODE");
  const availableAssets = assetsForContextSpace(assetsQuery.data ?? [], space);
  const stagedIds = new Set(staged.map((s) => s.asset.id));

  const addToStaged = (asset: CatalogNode) => {
    if (stagedIds.has(asset.id)) return;
    setStaged((prev) => [...prev, { asset, instructions: "" }]);
  };
  const removeStaged = (index: number) => {
    setStaged((prev) => prev.filter((_, i) => i !== index));
  };
  const moveStaged = (fromIndex: number, toIndex: number) => {
    setStaged((prev) => {
      if (toIndex < 0 || toIndex >= prev.length) return prev;
      const next = [...prev];
      const [moved] = next.splice(fromIndex, 1);
      next.splice(toIndex, 0, moved);
      return next;
    });
  };
  const setStagedInstructions = (index: number, instructions: string) => {
    setStaged((prev) => prev.map((s, i) => (i === index ? { ...s, instructions } : s)));
  };

  const pipelinePreviewItems: PipelineStripItem[] = staged.map((s) => ({
    key: s.asset.id,
    vendor: String(s.asset.attributes.vendor ?? ""),
    assetType: String(s.asset.attributes.asset_type ?? ""),
    label: s.asset.name,
    instructions: s.instructions,
  }));

  const create = useMutation({
    mutationFn: async () => {
      const template = await api.createWorkflowTemplate({
        context_space_id: contextSpaceId,
        name,
        description,
      });
      for (const s of staged) {
        await api.addWorkflowStep(template.id, {
          source_system: s.asset.source_system!,
          source_instance_id: s.asset.source_instance_id!,
          native_id: s.asset.native_id!,
          instructions: s.instructions.trim() || null,
        });
      }
      return template;
    },
    onSuccess: () => {
      setName("");
      setDescription("");
      setStaged([]);
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
      <div className="text-sm font-medium">Create a workflow template</div>
      <div className="rounded bg-neutral-50 p-2 text-xs text-neutral-500">
        A named, ordered pipeline of steps — each stage a specific agent or skill from a context
        space's repositories, with an optional note. Context Fabric never runs a template; a
        harness pulls it and executes the stages in order.
      </div>
      <div className="grid grid-cols-2 gap-3">
        <label className="col-span-2 text-xs text-neutral-600">
          Context space (whose repositories steps can be picked from)
          <select
            value={contextSpaceId}
            onChange={(e) => {
              setContextSpaceId(e.target.value);
              setStaged([]);
            }}
            required
            className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
          >
            <option value="">— select —</option>
            {(spacesQuery.data ?? []).map((s) => (
              <option key={s.id} value={s.id}>
                {s.name} ({s.id})
              </option>
            ))}
          </select>
          {(spacesQuery.data ?? []).length === 0 && (
            <span className="text-red-600">
              No context spaces yet — create one on the Team Contexts screen first.
            </span>
          )}
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
          Description
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="mt-1 block w-full rounded border border-neutral-300 px-2 py-1 text-sm"
          />
        </label>
      </div>

      {contextSpaceId && (
        <div className="space-y-3 rounded border border-dashed border-neutral-300 p-3">
          {staged.length > 0 && (
            <div className="space-y-1">
              <div className="text-xs font-medium text-neutral-600">Pipeline preview</div>
              <PipelineStrip
                items={pipelinePreviewItems}
                onRemove={removeStaged}
                onMoveLeft={(i) => moveStaged(i, i - 1)}
                onMoveRight={(i) => moveStaged(i, i + 1)}
                onInstructionsChange={setStagedInstructions}
              />
            </div>
          )}

          <div className="text-xs font-medium text-neutral-600">
            Agents &amp; skills available in this context space
          </div>
          {!hasCodeBinding && (
            <div className="text-xs text-amber-600">
              This context space has no CODE (repository) binding yet — add one on the Team
              Contexts screen to pick agents/skills from its repos.
            </div>
          )}
          {hasCodeBinding && assetsQuery.isLoading && (
            <div className="text-xs text-neutral-500">Loading AI assets…</div>
          )}
          {hasCodeBinding && assetsQuery.isError && (
            <div className="text-xs text-red-600">Failed to load AI assets.</div>
          )}
          {hasCodeBinding &&
            !assetsQuery.isLoading &&
            !assetsQuery.isError &&
            availableAssets.length === 0 && (
              <div className="text-xs text-neutral-500">
                No AI assets found in this context space's repositories yet — enable "AI
                Explorer" as an entity type on the relevant connector and run a sync.
              </div>
            )}
          {availableAssets.length > 0 && (
            <div className="max-h-56 overflow-auto rounded border border-neutral-200">
              {availableAssets.map((asset: CatalogNode) => (
                <div
                  key={asset.id}
                  className="flex items-center justify-between gap-2 border-b border-neutral-100 px-2 py-1 text-xs last:border-b-0 hover:bg-neutral-50"
                >
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="rounded bg-neutral-100 px-1.5 py-0.5 shrink-0">
                      {VENDOR_LABELS[String(asset.attributes.vendor ?? "")] ??
                        String(asset.attributes.vendor ?? "")}
                    </span>
                    <span className="rounded bg-neutral-100 px-1.5 py-0.5 shrink-0">
                      {ASSET_TYPE_LABELS[String(asset.attributes.asset_type ?? "")] ??
                        String(asset.attributes.asset_type ?? "")}
                    </span>
                    <span className="truncate font-medium">{asset.name}</span>
                    <span className="truncate text-neutral-400">
                      {String(asset.attributes.path ?? "")}
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => addToStaged(asset)}
                    disabled={stagedIds.has(asset.id)}
                    className="shrink-0 rounded border border-neutral-400 px-2 py-0.5 disabled:opacity-30"
                  >
                    {stagedIds.has(asset.id) ? "Added" : "Add to pipeline"}
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <button
        type="submit"
        disabled={create.isPending || !name || !contextSpaceId}
        className="rounded bg-neutral-900 px-3 py-1.5 text-sm text-white disabled:opacity-50"
      >
        {create.isPending
          ? "Creating…"
          : `Create template${staged.length ? ` with ${staged.length} step${staged.length === 1 ? "" : "s"}` : ""}`}
      </button>
      {create.isError && (
        <div className="text-sm text-red-600">{(create.error as Error).message}</div>
      )}
    </form>
  );
}

function TemplateCard({ template, space }: { template: WorkflowTemplate; space: ContextSpace | undefined }) {
  const queryClient = useQueryClient();
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["workflow-templates"] });

  const removeStep = useMutation({
    mutationFn: (stepId: string) => api.removeWorkflowStep(template.id, stepId),
    onSuccess: invalidate,
  });
  const reorder = useMutation({
    mutationFn: (stepIds: string[]) => api.reorderWorkflowSteps(template.id, stepIds),
    onSuccess: invalidate,
  });
  const deleteTemplate = useMutation({
    mutationFn: () => api.deleteWorkflowTemplate(template.id),
    onSuccess: invalidate,
  });

  const move = (fromIndex: number, toIndex: number) => {
    if (toIndex < 0 || toIndex >= template.steps.length) return;
    const ids = template.steps.map((s) => s.id);
    const [moved] = ids.splice(fromIndex, 1);
    ids.splice(toIndex, 0, moved);
    reorder.mutate(ids);
  };

  const pipelineItems: PipelineStripItem[] = template.steps.map((s) => ({
    key: s.id,
    vendor: s.vendor,
    assetType: s.asset_type,
    label: s.label,
    instructions: s.instructions,
  }));

  return (
    <div className="rounded border border-neutral-200 p-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="font-medium">{template.name}</div>
          <div className="text-xs text-neutral-500">
            {template.description || "No description."} · context space: {template.context_space_id}
          </div>
        </div>
        {confirmingDelete ? (
          <span className="flex items-center gap-1 text-xs">
            <button
              onClick={() => deleteTemplate.mutate()}
              disabled={deleteTemplate.isPending}
              className="rounded bg-red-600 px-2 py-1 text-white disabled:opacity-50"
            >
              {deleteTemplate.isPending ? "Deleting…" : "Confirm delete"}
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
      {deleteTemplate.isError && (
        <div className="mt-2 text-xs text-red-600">{(deleteTemplate.error as Error).message}</div>
      )}

      <div className="mt-3">
        <PipelineStrip
          items={pipelineItems}
          onRemove={(i) => removeStep.mutate(template.steps[i].id)}
          onMoveLeft={(i) => move(i, i - 1)}
          onMoveRight={(i) => move(i, i + 1)}
          busy={removeStep.isPending || reorder.isPending}
        />
      </div>

      {space ? (
        <AddStepForm templateId={template.id} space={space} onAdded={invalidate} />
      ) : (
        <div className="mt-3 text-xs text-neutral-400">Loading context space…</div>
      )}
    </div>
  );
}

export function WorkflowTemplatesPage() {
  const queryClient = useQueryClient();
  const templatesQuery = useQuery({
    queryKey: ["workflow-templates"],
    queryFn: () => api.listWorkflowTemplates(),
  });
  const spacesQuery = useQuery({ queryKey: ["context-spaces"], queryFn: api.listContextSpaces });
  const spaceById = new Map((spacesQuery.data ?? []).map((s) => [s.id, s]));

  return (
    <div className="max-w-4xl space-y-6">
      <h1 className="text-xl font-semibold">Workflow Templates</h1>
      <p className="text-sm text-neutral-500">
        A named, ordered pipeline of steps a harness pulls and executes — Context Fabric only
        stores and serves them, it never runs one itself.
      </p>

      <NewTemplateForm
        onCreated={() => queryClient.invalidateQueries({ queryKey: ["workflow-templates"] })}
      />

      <div className="space-y-3">
        {templatesQuery.isLoading && <div className="text-sm text-neutral-500">Loading…</div>}
        {templatesQuery.isError && (
          <div className="text-sm text-red-600">
            Failed to load workflow templates: {(templatesQuery.error as Error).message}
          </div>
        )}
        {templatesQuery.data?.length === 0 && (
          <div className="text-sm text-neutral-500">No workflow templates yet.</div>
        )}
        {templatesQuery.data?.map((t) => (
          <TemplateCard key={t.id} template={t} space={spaceById.get(t.context_space_id)} />
        ))}
      </div>
    </div>
  );
}
