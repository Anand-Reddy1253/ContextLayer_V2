import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type CatalogNode } from "@/lib/api-client";

const VENDOR_LABELS: Record<string, string> = {
  github: "GitHub",
  claude: "Claude",
  cursor: "Cursor",
};

const VENDOR_BADGE_CLASSES: Record<string, string> = {
  github: "bg-neutral-900 text-white",
  claude: "bg-orange-100 text-orange-800",
  cursor: "bg-blue-100 text-blue-800",
};

const ASSET_TYPE_LABELS: Record<string, string> = {
  agent: "Agent",
  skill: "Skill",
  command: "Command",
  rule: "Rule",
  prompt: "Prompt",
};

function AssetCard({ asset, repoName }: { asset: CatalogNode; repoName: string | null }) {
  const vendor = String(asset.attributes.vendor ?? "");
  const assetType = String(asset.attributes.asset_type ?? "");
  const description = asset.description ?? "";
  const path = String(asset.attributes.path ?? "");

  return (
    <div className="flex flex-col gap-2 rounded border border-neutral-200 p-4">
      <div className="flex items-center justify-between gap-2">
        <span
          className={`rounded px-1.5 py-0.5 text-xs font-medium ${
            VENDOR_BADGE_CLASSES[vendor] ?? "bg-neutral-100 text-neutral-700"
          }`}
        >
          {VENDOR_LABELS[vendor] ?? vendor}
        </span>
        <span className="rounded bg-neutral-100 px-1.5 py-0.5 text-xs text-neutral-600">
          {ASSET_TYPE_LABELS[assetType] ?? assetType}
        </span>
      </div>
      <div className="text-sm font-medium">{asset.name}</div>
      <div className="text-xs text-neutral-600">
        {description || <span className="text-neutral-400">No description found.</span>}
      </div>
      <div className="mt-1 flex items-center gap-1 text-xs text-neutral-400">
        <span>📦</span>
        <span>{repoName ?? "Unknown repository"}</span>
      </div>
      <div className="truncate font-mono text-[11px] text-neutral-400" title={path}>
        {path}
      </div>
    </div>
  );
}

export function AiExplorerPage() {
  const [vendorFilter, setVendorFilter] = useState<string | null>(null);
  const [repoFilter, setRepoFilter] = useState<string | null>(null);

  const assetsQuery = useQuery({
    queryKey: ["catalog", "search", { kind: "AI_ASSET" }],
    queryFn: () => api.searchCatalog({ kind: "AI_ASSET" }),
  });
  const reposQuery = useQuery({
    queryKey: ["catalog", "search", { kind: "REPOSITORY" }],
    queryFn: () => api.searchCatalog({ kind: "REPOSITORY" }),
  });

  const repoById = useMemo(() => {
    const map = new Map<string, CatalogNode>();
    for (const repo of reposQuery.data ?? []) map.set(repo.id, repo);
    return map;
  }, [reposQuery.data]);

  const assets = assetsQuery.data ?? [];
  const vendors = useMemo(
    () => Array.from(new Set(assets.map((a) => String(a.attributes.vendor ?? "")))).sort(),
    [assets]
  );
  const reposWithAssets = useMemo(() => {
    const seen = new Map<string, string>();
    for (const asset of assets) {
      if (!asset.parent_id) continue;
      const repo = repoById.get(asset.parent_id);
      if (repo) seen.set(repo.id, repo.name);
    }
    return Array.from(seen.entries());
  }, [assets, repoById]);

  const filtered = assets.filter((a) => {
    if (vendorFilter && a.attributes.vendor !== vendorFilter) return false;
    if (repoFilter && a.parent_id !== repoFilter) return false;
    return true;
  });

  if (assetsQuery.isLoading || reposQuery.isLoading) {
    return <div className="p-6 text-sm text-neutral-500">Loading AI assets…</div>;
  }
  if (assetsQuery.isError) {
    return <div className="p-6 text-sm text-red-600">Failed to load AI assets.</div>;
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-lg font-semibold">AI Explorer</h1>
        <p className="text-sm text-neutral-500">
          Agents, skills, commands, and rules declared under <code>.github/</code>,{" "}
          <code>.claude/</code>, and <code>.cursor/</code> in every connected repository — each
          one is always shown tied to the repo that defines it.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-4">
        <div className="flex flex-wrap gap-1.5">
          <button
            onClick={() => setVendorFilter(null)}
            className={`rounded px-2 py-1 text-xs ${
              vendorFilter === null ? "bg-neutral-900 text-white" : "bg-neutral-100 text-neutral-600"
            }`}
          >
            All vendors
          </button>
          {vendors.map((v) => (
            <button
              key={v}
              onClick={() => setVendorFilter(v)}
              className={`rounded px-2 py-1 text-xs ${
                vendorFilter === v ? "bg-neutral-900 text-white" : "bg-neutral-100 text-neutral-600"
              }`}
            >
              {VENDOR_LABELS[v] ?? v}
            </button>
          ))}
        </div>

        <select
          value={repoFilter ?? ""}
          onChange={(e) => setRepoFilter(e.target.value || null)}
          className="rounded border border-neutral-300 px-2 py-1 text-xs"
        >
          <option value="">All repositories</option>
          {reposWithAssets.map(([id, name]) => (
            <option key={id} value={id}>
              {name}
            </option>
          ))}
        </select>

        <div className="text-xs text-neutral-400">
          {filtered.length} of {assets.length} assets
        </div>
      </div>

      {filtered.length === 0 ? (
        <div className="rounded border border-dashed border-neutral-300 p-8 text-center text-sm text-neutral-500">
          No AI assets synced yet — enable "AI Explorer" as an entity type on a GitHub connector
          and run a sync.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((asset) => (
            <AssetCard
              key={asset.id}
              asset={asset}
              repoName={asset.parent_id ? (repoById.get(asset.parent_id)?.name ?? null) : null}
            />
          ))}
        </div>
      )}
    </div>
  );
}
