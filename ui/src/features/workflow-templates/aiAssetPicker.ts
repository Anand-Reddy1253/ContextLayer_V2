import type { CatalogNode, ContextSpace } from "@/lib/api-client";

export const VENDOR_LABELS: Record<string, string> = {
  github: "GitHub",
  claude: "Claude",
  cursor: "Cursor",
};

export const ASSET_TYPE_LABELS: Record<string, string> = {
  agent: "Agent",
  skill: "Skill",
  command: "Command",
  rule: "Rule",
  prompt: "Prompt",
};

/** An AI_ASSET's native_id is "{container_native_id}:ai-asset:{path}"
 * (connectors/ai_assets.py's marker scheme) — matching that prefix
 * against a CODE binding's native_container is enough to know an asset
 * belongs to one of a context space's repositories, with no extra
 * node-id lookup needed. */
export function assetBelongsToBinding(
  asset: CatalogNode,
  binding: ContextSpace["bindings"][number]
): boolean {
  if (asset.source_system !== binding.source_system) return false;
  if (asset.source_instance_id !== binding.source_instance_id) return false;
  return (asset.native_id ?? "").startsWith(`${binding.native_container}:ai-asset:`);
}

export function assetsForContextSpace(
  assets: CatalogNode[],
  space: ContextSpace | undefined
): CatalogNode[] {
  if (!space) return [];
  const codeBindings = space.bindings.filter((b) => b.capability === "CODE");
  return assets.filter((asset) => codeBindings.some((b) => assetBelongsToBinding(asset, b)));
}
