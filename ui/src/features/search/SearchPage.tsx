import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  api,
  type CatalogEdge,
  type CatalogGraph,
  type CatalogNode,
  type SearchCard,
  type SearchCardAncestor,
  type SearchCardBusinessContext,
  type SearchCardLink,
} from "@/lib/api-client";
import { GraphView } from "@/features/catalog-explorer/GraphView";

function businessContextNode(ctx: SearchCardBusinessContext): CatalogNode {
  return {
    id: `biz:${ctx.business_node_id}`,
    layer: "BUSINESS",
    kind: "TEAM",
    capability: null,
    name: ctx.business_node_name,
    description: null,
    source_system: null,
    source_instance_id: null,
    native_id: null,
    parent_id: null,
    path: `biz.${ctx.business_node_id}`,
    status: "ACTIVE",
    deleted_at: null,
    attributes: ctx.attributes as Record<string, unknown>,
  };
}

/** Every search card, turned into one graph: the matched nodes, their
 * ancestor chains (synthesized as CONTAINS edges — search-cards returns
 * the ancestor *nodes*, not edges, so this page draws them itself), their
 * real cross-system links, and — the piece that doesn't exist anywhere
 * else in the app — the owning business node wired in with a BINDS edge,
 * so "lineage" means the full path from a team down to a specific file,
 * not just the technical side (docs/UI.md "Search"). */
function cardsToGraph(cards: SearchCard[]): CatalogGraph {
  const nodes = new Map<string, CatalogNode>();
  const edges = new Map<string, CatalogEdge>();

  const addNode = (n: CatalogNode) => {
    if (!nodes.has(n.id)) nodes.set(n.id, n);
  };
  const addContains = (parentId: string, childId: string) => {
    const id = `synth-contains:${parentId}:${childId}`;
    if (!edges.has(id)) {
      edges.set(id, { id, src_id: parentId, dst_id: childId, type: "CONTAINS", origin: "SYNC_STRUCTURAL", state: "ACTIVE", confidence: null });
    }
  };

  for (const card of cards) {
    addNode(card.node);

    const chain = [...card.ancestors.map((a) => a.node), card.node];
    for (const a of card.ancestors) addNode(a.node);
    for (let i = 0; i < chain.length - 1; i++) addContains(chain[i].id, chain[i + 1].id);

    for (const link of card.links) {
      addNode(link.node);
      edges.set(link.edge.id, link.edge);
    }

    if (card.business_context) {
      const bizNode = businessContextNode(card.business_context);
      addNode(bizNode);
      const id = `synth-binds:${bizNode.id}:${card.node.id}`;
      if (!edges.has(id)) {
        edges.set(id, { id, src_id: bizNode.id, dst_id: card.node.id, type: "BINDS", origin: "HUMAN", state: "ACTIVE", confidence: null });
      }
    }
  }

  return { nodes: Array.from(nodes.values()), edges: Array.from(edges.values()) };
}

function Badge({ children }: { children: string }) {
  return <span className="rounded bg-neutral-100 px-1.5 py-0.5 text-xs text-neutral-600">{children}</span>;
}

function SourceBadge({ sourceSystem }: { sourceSystem: string | null }) {
  if (!sourceSystem) return null;
  return (
    <span className="rounded bg-neutral-900 px-1.5 py-0.5 text-xs font-medium text-white">
      {sourceSystem}
    </span>
  );
}

/** The raw identifiers a native per-vendor MCP server (GitHub's own,
 * Atlassian's, ...) needs to fetch this exact object directly — shown
 * explicitly, not just implied by the card, since the whole point of a
 * card is to hand this off (docs/UI.md "Search"). */
function LocatorStrip({ locator }: { locator: SearchCard["locator"] }) {
  return (
    <div className="mt-1 space-y-1">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 rounded bg-neutral-50 px-2 py-1 text-xs text-neutral-500">
        {locator.native_id && <span>id: {locator.native_id}</span>}
        {locator.source_instance_id && <span>instance: {locator.source_instance_id}</span>}
        {locator.url && (
          <a
            href={locator.url}
            target="_blank"
            rel="noreferrer"
            className="truncate text-blue-600 hover:underline"
          >
            {locator.url}
          </a>
        )}
      </div>
      {locator.native_call && (
        <div
          className="truncate rounded bg-neutral-900 px-2 py-1 font-mono text-[11px] text-neutral-100"
          title="What a native per-vendor MCP server would call to read this directly"
        >
          {locator.native_call.tool}({JSON.stringify(locator.native_call.params)})
        </div>
      )}
    </div>
  );
}

function AncestorTrail({ ancestors }: { ancestors: SearchCardAncestor[] }) {
  if (ancestors.length === 0) return null;
  return (
    <div className="mt-2 flex flex-wrap items-center gap-1 text-xs text-neutral-500">
      <span className="text-neutral-400">Hierarchy:</span>
      {ancestors.map((a, i) => (
        <span key={a.node.id} className="flex items-center gap-1">
          {i > 0 && <span className="text-neutral-300">/</span>}
          <span className="rounded border border-neutral-200 px-1.5 py-0.5">
            {a.node.kind}: {a.node.name}
          </span>
        </span>
      ))}
    </div>
  );
}

/** The owning team's business context — surfaced on the card because
 * this is where it actually reaches an agent (not by walking the
 * technical ancestor chain; business nodes aren't part of that tree). */
function BusinessContextStrip({ context }: { context: SearchCardBusinessContext }) {
  const attrs = context.attributes;
  const hasAnything =
    attrs.criticality_tier || (attrs.compliance_scope?.length ?? 0) > 0 || attrs.communication_channel;
  if (!hasAnything) return null;

  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
      <span className="text-neutral-400">{context.business_node_name}:</span>
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
  );
}

function LinkRow({ link }: { link: SearchCardLink }) {
  return (
    <div className="flex items-center justify-between gap-2 rounded border border-neutral-100 px-2 py-1 text-xs">
      <div className="flex min-w-0 items-center gap-2">
        <span className="text-neutral-400">
          {link.direction === "outgoing" ? "→" : "←"} {link.edge.type}
        </span>
        <SourceBadge sourceSystem={link.node.source_system} />
        <span className="truncate font-medium">{link.node.name}</span>
        <Badge>{link.node.kind}</Badge>
      </div>
      {link.locator.url && (
        <a
          href={link.locator.url}
          target="_blank"
          rel="noreferrer"
          className="shrink-0 text-blue-600 hover:underline"
        >
          open
        </a>
      )}
    </div>
  );
}

function SearchCardView({ card }: { card: SearchCard }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded border border-neutral-200 p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <SourceBadge sourceSystem={card.node.source_system} />
            <Badge>{card.node.kind}</Badge>
          </div>
          <div className="mt-1 truncate text-sm font-medium">{card.node.name}</div>
          {card.node.description && (
            <div className="mt-0.5 truncate text-xs text-neutral-500">{card.node.description}</div>
          )}
        </div>
        <div className="shrink-0 text-xs text-neutral-400">match {Math.round(card.score * 100)}%</div>
      </div>

      <LocatorStrip locator={card.locator} />
      <AncestorTrail ancestors={card.ancestors} />
      {card.business_context && <BusinessContextStrip context={card.business_context} />}

      {(card.links.length > 0 || expanded) && (
        <div className="mt-2">
          <button
            onClick={() => setExpanded((e) => !e)}
            className="text-xs text-neutral-500 hover:text-neutral-800"
          >
            {expanded ? "Hide" : "Show"} {card.links.length} related source
            {card.links.length === 1 ? "" : "s"} (repos, docs, work items…)
          </button>
          {expanded && (
            <div className="mt-2 space-y-1">
              {card.links.length === 0 && (
                <div className="text-xs text-neutral-400">
                  Nothing cross-referenced from another source yet.
                </div>
              )}
              {card.links.map((link) => (
                <LinkRow key={link.edge.id} link={link} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const SOURCE_SYSTEMS = ["azure_devops", "github", "confluence", "jira"] as const;

export function SearchPage() {
  const [q, setQ] = useState("");
  const [submittedQ, setSubmittedQ] = useState("");
  const [businessNodeId, setBusinessNodeId] = useState("");
  const [sourceSystems, setSourceSystems] = useState<Set<string>>(new Set());
  const [semantic, setSemantic] = useState(false);
  const [view, setView] = useState<"cards" | "graph">("cards");
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const sourceSystemParam = Array.from(sourceSystems).join(",");

  const orgTreeQuery = useQuery({ queryKey: ["org-tree"], queryFn: api.getOrgTree });
  const searchQuery = useQuery({
    queryKey: ["search-cards", submittedQ, businessNodeId, sourceSystemParam, semantic],
    queryFn: () =>
      api.searchCards({
        q: submittedQ,
        business_node_id: businessNodeId || undefined,
        source_system: sourceSystemParam || undefined,
        semantic: semantic || undefined,
      }),
    enabled: submittedQ.length > 0,
  });

  const graph = useMemo(
    () => (searchQuery.data ? cardsToGraph(searchQuery.data) : null),
    [searchQuery.data]
  );
  const selectedCard =
    selectedNodeId && searchQuery.data
      ? searchQuery.data.find((c) => c.node.id === selectedNodeId)
      : null;
  const selectedGraphNode =
    selectedNodeId && graph ? graph.nodes.find((n) => n.id === selectedNodeId) : null;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Search</h1>
      <p className="text-sm text-neutral-500">
        Search across every synced source. Each result shows where it sits in its own hierarchy,
        what it's directly cross-referenced with, and which business context it's bound to — repos,
        docs, work items, and more — so an agent can pick the right one and read the full content
        through its own native MCP connection. Switch to Graph to see the lineage visually.
      </p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          setSubmittedQ(q);
        }}
        className="flex flex-wrap items-end gap-3"
      >
        <label className="flex-1 text-xs text-neutral-600">
          Topic
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="SSO, identity service, onboarding…"
            className="mt-1 block w-full max-w-md rounded border border-neutral-300 px-2 py-1.5 text-sm"
          />
        </label>
        <label className="text-xs text-neutral-600">
          Scope to a team/squad
          <select
            value={businessNodeId}
            onChange={(e) => setBusinessNodeId(e.target.value)}
            className="mt-1 block w-full max-w-xs rounded border border-neutral-300 px-2 py-1.5 text-sm"
          >
            <option value="">— whole enterprise —</option>
            {(orgTreeQuery.data ?? []).map((n) => (
              <option key={n.id} value={n.id}>
                {n.path}
              </option>
            ))}
          </select>
        </label>
        <button
          type="submit"
          disabled={!q}
          className="rounded bg-neutral-900 px-4 py-1.5 text-sm text-white disabled:opacity-50"
        >
          Search
        </button>
      </form>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <label className="flex items-center gap-1.5 text-xs text-neutral-600">
          <input
            type="checkbox"
            checked={semantic}
            onChange={(e) => setSemantic(e.target.checked)}
          />
          Semantic search
          <span className="text-neutral-400">
            (meaning-based, not just keyword — catches typos/paraphrasing, local model)
          </span>
        </label>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-neutral-600">
          <span className="text-neutral-400">Sources:</span>
          {SOURCE_SYSTEMS.map((src) => (
            <label key={src} className="flex items-center gap-1">
              <input
                type="checkbox"
                checked={sourceSystems.has(src)}
                onChange={(e) =>
                  setSourceSystems((prev) => {
                    const next = new Set(prev);
                    if (e.target.checked) next.add(src);
                    else next.delete(src);
                    return next;
                  })
                }
              />
              {src}
            </label>
          ))}
        </div>
      </div>

      {businessNodeId && (
        <div className="text-xs text-neutral-500">
          Scoped to results reachable from this team's own context space bindings — not results
          that merely mention something in scope; that boundary is authorization's job later, this
          is a manual filter for now.
        </div>
      )}

      {searchQuery.isLoading && <div className="text-sm text-neutral-500">Searching…</div>}
      {searchQuery.isError && (
        <div className="text-sm text-red-600">{(searchQuery.error as Error).message}</div>
      )}
      {searchQuery.data && searchQuery.data.length === 0 && (
        <div className="rounded border border-dashed border-neutral-300 p-4 text-center text-sm text-neutral-400">
          No matches{businessNodeId ? " within that team's scope" : ""} for "{submittedQ}".
        </div>
      )}

      {searchQuery.data && searchQuery.data.length > 0 && (
        <>
          <div className="flex items-center gap-1 border-b border-neutral-200">
            {(["cards", "graph"] as const).map((v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={`px-3 py-1.5 text-sm capitalize ${
                  view === v
                    ? "border-b-2 border-neutral-900 font-medium text-neutral-900"
                    : "text-neutral-500 hover:text-neutral-700"
                }`}
              >
                {v}
              </button>
            ))}
          </div>

          {view === "cards" && (
            <div className="space-y-2">
              {searchQuery.data.map((card) => (
                <SearchCardView key={card.node.id} card={card} />
              ))}
            </div>
          )}

          {view === "graph" && graph && (
            <div className="space-y-3">
              <div className="text-xs text-neutral-500">
                Lineage for "{submittedQ}" — every matched asset, its containing hierarchy, its
                cross-system links, and (gold) the business node it's bound to. Click a node for
                details.
              </div>
              <GraphView graph={graph} onSelectNode={setSelectedNodeId} />
              {selectedCard && <SearchCardView card={selectedCard} />}
              {!selectedCard && selectedGraphNode && (
                <div className="rounded border border-neutral-200 p-3 text-sm">
                  <div className="flex items-center gap-2">
                    <Badge>{selectedGraphNode.kind}</Badge>
                    {selectedGraphNode.source_system && (
                      <SourceBadge sourceSystem={selectedGraphNode.source_system} />
                    )}
                  </div>
                  <div className="mt-1 font-medium">{selectedGraphNode.name}</div>
                  <div className="mt-1 text-xs text-neutral-400">
                    Not itself a search match — reached via hierarchy or a cross-reference.
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
