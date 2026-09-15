import cytoscape from "cytoscape";
import { useEffect, useRef, useState } from "react";
import type { CatalogGraph, CatalogNode } from "@/lib/api-client";

const KIND_COLOR: Record<string, string> = {
  PROJECT: "#1d4ed8",
  ORGANIZATION: "#1d4ed8",
  AREA_PATH: "#0891b2",
  GIT_REPOSITORY: "#7c3aed",
  REPOSITORY: "#7c3aed",
  BRANCH: "#a855f7",
  WIKI_PAGE: "#059669",
  PULL_REQUEST: "#dc2626",
  ISSUE: "#ea580c",
  PROJECT_BOARD: "#0f766e",
  PROJECT_ITEM: "#14b8a6",
  EPIC: "#9333ea",
  FEATURE: "#4f46e5",
  STORY: "#2563eb",
  TASK: "#0284c7",
  BUG: "#dc2626",
  WORK_ITEM: "#64748b",
  SPACE: "#1d4ed8",
  PAGE: "#059669",
  ATTACHMENT: "#a16207",
  COMMENT: "#65a30d",
  // Business layer + the synthesized logical-layer node (Enterprise
  // Context Graph, docs/UI.md).
  ORG: "#0f172a",
  DIVISION: "#1e293b",
  TRIBE: "#334155",
  SQUAD: "#475569",
  TEAM: "#475569",
  PRODUCT: "#7c2d92",
  SERVICE: "#a21caf",
  CONTEXT_SPACE: "#ca8a04",
};
const DEFAULT_COLOR = "#94a3b8";

const EDGE_COLOR: Record<string, string> = {
  CONTAINS: "#cbd5e1",
  MENTIONS: "#f59e0b",
  RELATED_TO: "#ec4899",
  HAS_CONTEXT_SPACE: "#ca8a04",
  BINDS: "#0891b2",
};

function edgeLabel(type: string): string {
  return type.toLowerCase().replaceAll("_", " ");
}

function kindLabel(kind: string): string {
  return kind
    .toLowerCase()
    .split("_")
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(" ");
}

// Above this many same-kind siblings under one parent, draw one collapsed
// cluster node instead of every individual child — found via a real user
// report: ~140 Pull Requests all sharing one repo parent rendered as a
// dense star (one hub, 140 spokes converging on it) that reads as "every
// PR is related to every other PR" at a glance, even though the
// underlying data has exactly 2 real PR-to-PR edges (confirmed by direct
// query). It's a rendering-density illusion, not a data problem — this is
// the fix, not a link-extraction change.
const CLUSTER_THRESHOLD = 15;

interface ClusterInfo {
  id: string;
  parentId: string;
  kind: string;
  memberIds: string[];
}

function buildStylesheet(rootId?: string): cytoscape.StylesheetCSS[] {
  const kindStyles: cytoscape.StylesheetCSS[] = Object.entries(KIND_COLOR).map(
    ([kind, color]) => ({
      selector: `node[kind = "${kind}"]`,
      css: { "background-color": color },
    })
  );
  const edgeStyles: cytoscape.StylesheetCSS[] = Object.entries(EDGE_COLOR).map(
    ([type, color]) => ({
      selector: `edge[type = "${type}"]`,
      css: { "line-color": color, "target-arrow-color": color },
    })
  );
  return [
    {
      selector: "node",
      css: {
        "background-color": DEFAULT_COLOR,
        width: "data(size)",
        height: "data(size)",
        "border-width": 1,
        "border-color": "#ffffff",
      },
    },
    ...kindStyles,
    {
      selector: "edge",
      css: {
        width: 1,
        "line-color": "#cbd5e1",
        "target-arrow-color": "#cbd5e1",
        "target-arrow-shape": "none",
        "curve-style": "bezier",
        opacity: 0.5,
      },
    },
    ...edgeStyles,
    {
      selector: 'edge[type != "CONTAINS"]',
      css: { "line-style": "dashed", opacity: 0.8, "target-arrow-shape": "triangle" },
    },
    ...(rootId
      ? [
          {
            selector: `node[id = "${rootId}"]`,
            css: { "border-width": 3, "border-color": "#0f172a" },
          } as cytoscape.StylesheetCSS,
        ]
      : []),
    {
      selector: "node.hovered",
      css: { "border-width": 3, "border-color": "#0f172a" },
    },
    {
      selector: "node.cluster",
      css: {
        shape: "round-rectangle",
        "background-color": "#e2e8f0",
        "border-width": 2,
        "border-color": "#64748b",
        "border-style": "dashed",
      },
    },
  ];
}

export function GraphView({
  graph,
  rootId,
  onSelectNode,
}: {
  graph: CatalogGraph;
  rootId?: string;
  onSelectNode: (nodeId: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const [hovered, setHovered] = useState<CatalogNode | null>(null);
  const [hiddenKinds, setHiddenKinds] = useState<Set<string>>(new Set());
  const [expandedClusters, setExpandedClusters] = useState<Set<string>>(new Set());

  // Recomputed whenever the underlying graph changes, not on every
  // expand/collapse click — a fresh graph should always start collapsed.
  useEffect(() => {
    setExpandedClusters(new Set());
  }, [graph]);

  useEffect(() => {
    if (!containerRef.current) return;
    setHiddenKinds(new Set());

    const degree = new Map<string, number>();
    for (const e of graph.edges) {
      degree.set(e.src_id, (degree.get(e.src_id) ?? 0) + 1);
      degree.set(e.dst_id, (degree.get(e.dst_id) ?? 0) + 1);
    }

    // Group same-kind siblings by (parent_id, kind); anything over
    // CLUSTER_THRESHOLD collapses into one cluster node unless the user
    // already expanded it this session.
    const siblingGroups = new Map<string, ClusterInfo>();
    for (const n of graph.nodes) {
      if (!n.parent_id) continue;
      const key = `${n.parent_id}::${n.kind}`;
      let group = siblingGroups.get(key);
      if (!group) {
        group = { id: `cluster:${key}`, parentId: n.parent_id, kind: n.kind, memberIds: [] };
        siblingGroups.set(key, group);
      }
      group.memberIds.push(n.id);
    }
    const clusters = Array.from(siblingGroups.values()).filter(
      (g) => g.memberIds.length > CLUSTER_THRESHOLD && !expandedClusters.has(g.id)
    );
    const collapsedMemberOf = new Map<string, ClusterInfo>();
    for (const cluster of clusters) {
      for (const memberId of cluster.memberIds) {
        collapsedMemberOf.set(memberId, cluster);
      }
    }

    const clusterNodes = new Map<string, CatalogNode>();
    for (const cluster of clusters) {
      clusterNodes.set(cluster.id, {
        id: cluster.id,
        layer: "TECHNICAL",
        kind: cluster.kind,
        capability: null,
        name: `${cluster.memberIds.length} × ${kindLabel(cluster.kind)} — click to expand`,
        description: null,
        source_system: null,
        source_instance_id: null,
        native_id: null,
        parent_id: cluster.parentId,
        path: "",
        status: "ACTIVE",
        deleted_at: null,
        attributes: {},
      });
    }
    const nodesById = new Map(graph.nodes.map((n) => [n.id, n]));
    for (const [id, n] of clusterNodes) nodesById.set(id, n);

    const visibleNodes = graph.nodes.filter((n) => !collapsedMemberOf.has(n.id));

    const elements = [
      ...visibleNodes.map((n) => {
        const d = degree.get(n.id) ?? 0;
        const size = Math.min(60, Math.max(10, 8 + Math.sqrt(d) * 6));
        return { data: { id: n.id, kind: n.kind, size } };
      }),
      ...clusters.map((cluster) => {
        const totalDegree = cluster.memberIds.reduce((sum, id) => sum + (degree.get(id) ?? 0), 0);
        const size = Math.min(60, Math.max(14, 8 + Math.sqrt(totalDegree) * 6));
        return { data: { id: cluster.id, kind: cluster.kind, size }, classes: "cluster" };
      }),
      ...clusters.map((cluster) => ({
        data: {
          id: `${cluster.id}:edge`,
          source: cluster.parentId,
          target: cluster.id,
          type: "CONTAINS",
        },
      })),
      // Edges between two collapsed members, or a collapsed member and
      // anything else, are dropped rather than redirected at the cluster
      // — real cross-links are rare (2 in the whole dataset, confirmed),
      // so it's not worth the visual noise of a cluster-to-X edge that
      // only some members actually have.
      ...graph.edges
        .filter((e) => !collapsedMemberOf.has(e.src_id) && !collapsedMemberOf.has(e.dst_id))
        .map((e) => ({
          data: { id: e.id, source: e.src_id, target: e.dst_id, type: e.type },
        })),
    ];

    // `cose` (force-directed physics) is the preferred look — user
    // feedback confirmed the tree layout below is a worse default even
    // with clustering in place. Sibling-clustering (above) already
    // removes the actual cost driver (hundreds of same-kind nodes at one
    // level), so the remaining effective node count after clustering is
    // usually small even when the raw graph is huge; `cose` now only
    // steps aside for whatever's left that's still large — numIter also
    // scales down as that count grows, so it stays responsive instead of
    // needing a hard cutover to `breadthfirst`'s tree look.
    const effectiveCount = visibleNodes.length + clusters.length;
    const isVeryLarge = effectiveCount > 350;
    const layout: cytoscape.LayoutOptions = isVeryLarge
      ? ({
          name: "breadthfirst",
          directed: true,
          roots: rootId ? [rootId] : undefined,
          spacingFactor: 0.9,
          animate: false,
        } as cytoscape.LayoutOptions)
      : ({
          name: "cose",
          animate: false,
          nodeRepulsion: () => 6000,
          idealEdgeLength: () => 50,
          gravity: 40,
          numIter: effectiveCount > 150 ? 400 : 1000,
        } as cytoscape.LayoutOptions);

    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: buildStylesheet(rootId),
      layout,
      minZoom: 0.1,
      maxZoom: 4,
    });

    cy.on("tap", "node", (evt) => {
      const id = evt.target.id();
      if (id.startsWith("cluster:")) {
        setExpandedClusters((prev) => new Set(prev).add(id));
        return;
      }
      onSelectNode(id);
    });
    cy.on("mouseover", "node", (evt) => {
      evt.target.addClass("hovered");
      setHovered(nodesById.get(evt.target.id()) ?? null);
    });
    cy.on("mouseout", "node", (evt) => {
      evt.target.removeClass("hovered");
      setHovered(null);
    });

    cyRef.current = cy;
    return () => {
      cyRef.current = null;
      cy.destroy();
    };
  }, [graph, rootId, onSelectNode, expandedClusters]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) return;
    cy.nodes().forEach((n) => {
      const kind = n.data("kind") as string;
      n.style("display", hiddenKinds.has(kind) ? "none" : "element");
    });
  }, [hiddenKinds]);

  const toggleKind = (kind: string) => {
    setHiddenKinds((prev) => {
      const next = new Set(prev);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next;
    });
  };

  const kindsPresent = Array.from(new Set(graph.nodes.map((n) => n.kind))).sort();
  const edgeTypesPresent = Array.from(new Set(graph.edges.map((e) => e.type))).sort();

  return (
    <div className="flex gap-3">
      <div className="flex-1">
        <div className="relative">
          <div ref={containerRef} className="h-[520px] w-full rounded border border-neutral-200 bg-white" />
          <div className="pointer-events-none absolute bottom-2 left-2 rounded bg-white/90 px-2 py-1 text-xs text-neutral-700 shadow">
            {hovered ? (
              <>
                <span className="font-medium">{hovered.kind}</span>: {hovered.name}
              </>
            ) : (
              <span className="text-neutral-400">Hover a node for its name · click to open · scroll to zoom</span>
            )}
          </div>
        </div>
        <div className="mt-2 flex flex-wrap gap-3 text-xs text-neutral-500">
          {edgeTypesPresent.map((type) => {
            const color = EDGE_COLOR[type] ?? "#cbd5e1";
            return (
              <span key={type} className="flex items-center gap-1">
                {type === "CONTAINS" ? (
                  <span className="inline-block h-0.5 w-4" style={{ backgroundColor: color }} />
                ) : (
                  <span
                    className="inline-block h-0 w-4 border-t border-dashed"
                    style={{ borderColor: color }}
                  />
                )}
                {edgeLabel(type)}
              </span>
            );
          })}
        </div>
      </div>
      <div className="w-44 shrink-0 rounded border border-neutral-200 p-2">
        <div className="mb-1 flex items-center justify-between text-xs font-medium text-neutral-500">
          <span>Filter by kind</span>
          {hiddenKinds.size > 0 && (
            <button
              onClick={() => setHiddenKinds(new Set())}
              className="text-neutral-400 hover:text-neutral-700"
            >
              reset
            </button>
          )}
        </div>
        <div className="space-y-0.5">
          {kindsPresent.map((kind) => {
            const hidden = hiddenKinds.has(kind);
            return (
              <button
                key={kind}
                onClick={() => toggleKind(kind)}
                className={`flex w-full items-center gap-1.5 rounded px-1 py-0.5 text-left text-xs hover:bg-neutral-50 ${
                  hidden ? "text-neutral-300" : "text-neutral-600"
                }`}
                title={hidden ? "Hidden — click to show" : "Shown — click to hide"}
              >
                <span
                  className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{ backgroundColor: hidden ? "#e5e7eb" : (KIND_COLOR[kind] ?? DEFAULT_COLOR) }}
                />
                <span className={hidden ? "line-through" : ""}>{kindLabel(kind)}</span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
