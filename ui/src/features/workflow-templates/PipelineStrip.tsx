import { VENDOR_LABELS, ASSET_TYPE_LABELS } from "@/features/workflow-templates/aiAssetPicker";

export interface PipelineStripItem {
  key: string;
  vendor: string;
  assetType: string;
  label: string;
  instructions?: string | null;
}

/** Renders a sequence of steps as connected pipeline stages
 * (left-to-right boxes joined by arrows, CI/CD-pipeline style) instead of
 * a plain list — used both for an already-created template's steps and
 * for the live preview of steps staged during template creation.
 *
 * `onInstructionsChange`, when given, makes each stage's note an editable
 * input (the creation-time staging list); omit it to render the note as
 * plain text (an already-created template's steps, where a note edit
 * would need its own API call this component doesn't own). */
export function PipelineStrip({
  items,
  onRemove,
  onMoveLeft,
  onMoveRight,
  onInstructionsChange,
  busy,
}: {
  items: PipelineStripItem[];
  onRemove: (index: number) => void;
  onMoveLeft?: (index: number) => void;
  onMoveRight?: (index: number) => void;
  onInstructionsChange?: (index: number, instructions: string) => void;
  busy?: boolean;
}) {
  if (items.length === 0) {
    return <div className="text-xs text-neutral-400">No steps yet.</div>;
  }

  return (
    <div className="flex items-stretch gap-1 overflow-x-auto pb-2">
      {items.map((item, index) => (
        <div key={item.key} className="flex shrink-0 items-stretch">
          <div className="flex w-44 shrink-0 flex-col gap-1 rounded border border-neutral-300 bg-white p-2 text-xs shadow-sm">
            <div className="flex items-center justify-between">
              <span className="text-neutral-400">Step {index + 1}</span>
              <div className="flex items-center gap-0.5">
                {onMoveLeft && (
                  <button
                    onClick={() => onMoveLeft(index)}
                    disabled={busy || index === 0}
                    className="rounded border border-neutral-300 px-1 disabled:opacity-30"
                    title="Move earlier"
                  >
                    ←
                  </button>
                )}
                {onMoveRight && (
                  <button
                    onClick={() => onMoveRight(index)}
                    disabled={busy || index === items.length - 1}
                    className="rounded border border-neutral-300 px-1 disabled:opacity-30"
                    title="Move later"
                  >
                    →
                  </button>
                )}
              </div>
            </div>
            <div className="flex flex-wrap gap-1">
              <span className="rounded bg-neutral-100 px-1.5 py-0.5">
                {VENDOR_LABELS[item.vendor] ?? item.vendor}
              </span>
              <span className="rounded bg-neutral-100 px-1.5 py-0.5">
                {ASSET_TYPE_LABELS[item.assetType] ?? item.assetType}
              </span>
            </div>
            <div className="truncate font-medium" title={item.label}>
              {item.label}
            </div>
            {onInstructionsChange ? (
              <input
                value={item.instructions ?? ""}
                onChange={(e) => onInstructionsChange(index, e.target.value)}
                placeholder="Note (optional)"
                className="rounded border border-neutral-200 px-1.5 py-0.5 text-[11px]"
              />
            ) : item.instructions ? (
              <div className="truncate text-[11px] text-neutral-500" title={item.instructions}>
                {item.instructions}
              </div>
            ) : null}
            <button
              onClick={() => onRemove(index)}
              disabled={busy}
              className="mt-auto self-start text-[11px] text-neutral-400 hover:text-red-600"
            >
              remove
            </button>
          </div>
          {index < items.length - 1 && (
            <div className="flex shrink-0 items-center px-1 text-neutral-300">→</div>
          )}
        </div>
      ))}
    </div>
  );
}
