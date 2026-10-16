import cytoscape from "cytoscape";
import { useEffect, useRef, useState } from "react";
import { clsx } from "clsx";
import type { CatalogGraph, CatalogNode } from "@/lib/api-client";
import { Button } from "@/components/Button";

// Graph-canvas colors read from the Emagine token values directly (Cytoscape
// paints to a <canvas>, which can't consume CSS custom properties or
// Tailwind classes) so the graph stays visually literate with the rest of
// the page instead of running its own unrelated hex palette. Node-kind and
// source-system each get their own ramp built from the same OKLCH family as
// the design system's status-* hues (consistent L≈0.5-0.68, C≈0.13-0.2,
// hue stepped around the wheel) — light-mode literal, matching the rest of
// this app until a dark-mode toggle actually exists.
const TOKEN = {
  ink: "oklch(0.197 0.005 145.4)",
  charcoal: "oklch(0.314 0.011 145.3)",
  charcoalRaised: "oklch(0.366 0.015 145.3)",
  charcoalDeep: "oklch(0.27 0.012 145.2)",
  background: "oklch(1 0 0)",
  border: "oklch(0.919 0 89.9)",
  muted: "oklch(0.967 0 89.9)",
  mutedForeground: "oklch(0.539 0.01 145.4)",
  destructive: "oklch(0.597 0.182 24.5)",
  statusBlue: "oklch(0.55 0.18 255)",
  statusViolet: "oklch(0.55 0.2 300)",
  statusAmber: "oklch(0.65 0.16 70)",
};

const KIND_COLOR: Record<string, string> = {
  PROJECT: TOKEN.statusBlue,
  ORGANIZATION: TOKEN.statusBlue,
  AREA_PATH: "oklch(0.6 0.14 195)",
  GIT_REPOSITORY: TOKEN.statusViolet,
  REPOSITORY: TOKEN.statusViolet,
  BRANCH: "oklch(0.68 0.16 300)",
  WIKI_PAGE: "oklch(0.6 0.15 150)",
  PULL_REQUEST: TOKEN.destructive,
  ISSUE: "oklch(0.65 0.17 45)",
  PROJECT_BOARD: "oklch(0.5 0.1 195)",
  PROJECT_ITEM: "oklch(0.68 0.12 175)",
  EPIC: "oklch(0.5 0.18 290)",
  FEATURE: "oklch(0.55 0.16 265)",
  STORY: "oklch(0.58 0.16 250)",
  TASK: "oklch(0.62 0.13 220)",
  BUG: TOKEN.destructive,
  WORK_ITEM: "oklch(0.6 0.02 145)",
  SPACE: TOKEN.statusBlue,
  PAGE: "oklch(0.6 0.15 150)",
  ATTACHMENT: TOKEN.statusAmber,
  COMMENT: "oklch(0.62 0.14 130)",
  // Business layer + the synthesized logical-layer node (Enterprise
  // Context Graph, docs/UI.md) — the brand's own charcoal/ink ramp, so
  // "this came from the org tree, not a vendor" reads at a glance.
  ORG: TOKEN.ink,
  DIVISION: TOKEN.charcoalDeep,
  TRIBE: TOKEN.charcoal,
  SQUAD: TOKEN.charcoalRaised,
  TEAM: TOKEN.charcoalRaised,
  PRODUCT: "oklch(0.5 0.19 330)",
  SERVICE: "oklch(0.55 0.2 320)",
  CONTEXT_SPACE: TOKEN.statusAmber,
};
const DEFAULT_COLOR = TOKEN.mutedForeground;

// One color per vendor, for "color by system" mode — a real user ask:
// coloring by kind (STORY vs. PULL_REQUEST vs. PAGE) makes same-kind
// nodes easy to spot but says nothing about which vendor a node came
// from, which is exactly what matters when the question is "does this
// relationship actually cross systems." Reuses the design system's three
// status hues for the first three vendors and extends the same OKLCH
// family with two more (teal, magenta) for the rest — the token set only
// names three, and the graph needs one per connector.
const SOURCE_SYSTEM_COLOR: Record<string, string> = {
  azure_devops: TOKEN.statusBlue,
  github: TOKEN.statusViolet,
  jira: TOKEN.statusAmber,
  confluence: "oklch(0.6 0.14 190)",
  teams: "oklch(0.58 0.16 350)",
};
const SOURCE_SYSTEM_LABELS: Record<string, string> = {
  azure_devops: "Azure DevOps",
  github: "GitHub",
  jira: "Jira",
  confluence: "Confluence",
  teams: "Teams",
};
// Business/logical-layer nodes (a team, a context space, the synthesized
// "bound to" node search draws) carry no source_system at all — they
// aren't vendor data, so they get their own neutral color rather than
// falling into DEFAULT_COLOR and looking like an unrecognized kind.
const NO_SOURCE_SYSTEM_COLOR = TOKEN.ink;

const EDGE_COLOR: Record<string, string> = {
  CONTAINS: TOKEN.border,
  MENTIONS: TOKEN.statusAmber,
  RELATED_TO: "oklch(0.6 0.18 340)",
  HAS_CONTEXT_SPACE: "oklch(0.55 0.15 70)",
  BINDS: "oklch(0.55 0.14 195)",
};

// Cytoscape paints to a raw <canvas>, and this environment's Canvas2D
// fillStyle parser doesn't accept oklch() the way CSS/DOM styling does
// (confirmed live: the DOM color swatches in this same file render fine,
// every canvas node/edge came back solid black). Resolving through
// getComputedStyle first was tried and didn't help — modern browsers
// preserve oklch() as the *computed* value too rather than collapsing it
// to rgb(), so canvas received the same unparseable string either way.
// This does the OKLCH→linear-sRGB→sRGB math directly (Björn Ottosson's
// published oklab conversion) and hands canvas a plain rgb() string, which
// every Canvas2D implementation accepts regardless of Color-4 support.
const resolvedColorCache = new Map<string, string>();
function toCanvasColor(cssColor: string): string {
  const cached = resolvedColorCache.get(cssColor);
  if (cached) return cached;

  const match = cssColor.match(/oklch\(\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)/);
  if (!match) {
    resolvedColorCache.set(cssColor, cssColor);
    return cssColor;
  }
  const L = parseFloat(match[1]);
  const C = parseFloat(match[2]);
  const H = (parseFloat(match[3]) * Math.PI) / 180;

  const a = C * Math.cos(H);
  const b = C * Math.sin(H);

  const l_ = L + 0.3963377774 * a + 0.2158037573 * b;
  const m_ = L - 0.1055613458 * a - 0.0638541728 * b;
  const s_ = L - 0.0894841775 * a - 1.2914855480 * b;

  const l = l_ ** 3;
  const m = m_ ** 3;
  const s = s_ ** 3;

  const rLin = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s;
  const gLin = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s;
  const bLin = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s;

  const gamma = (v: number) => {
    const clamped = Math.max(0, Math.min(1, v));
    return clamped <= 0.0031308 ? 12.92 * clamped : 1.055 * Math.pow(clamped, 1 / 2.4) - 0.055;
  };

  const r = Math.round(gamma(rLin) * 255);
  const g = Math.round(gamma(gLin) * 255);
  const bl = Math.round(gamma(bLin) * 255);

  const resolved = `rgb(${r}, ${g}, ${bl})`;
  resolvedColorCache.set(cssColor, resolved);
  return resolved;
}
function resolveColorMap(map: Record<string, string>): Record<string, string> {
  return Object.fromEntries(Object.entries(map).map(([k, v]) => [k, toCanvasColor(v)]));
}

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

// A node label sits directly under a circle that can be as small as 10px
// across — an unbounded name would overlap its neighbors and make the
// labeled version no more readable than the unlabeled one it's replacing.
// Truncated here (not via a CSS text-overflow, which cytoscape's canvas
// renderer doesn't support) so the raw string cytoscape lays out is
// already short.
function truncateLabel(text: string, max = 22): string {
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
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
  sourceSystem: string | null;
}

type ColorMode = "kind" | "system";

function buildStylesheet(rootId?: string, colorBy: ColorMode = "kind"): cytoscape.StylesheetCSS[] {
  const c = Object.fromEntries(
    Object.entries(TOKEN).map(([k, v]) => [k, toCanvasColor(v)])
  ) as typeof TOKEN;
  const resolvedKindColor = resolveColorMap(KIND_COLOR);
  const resolvedSourceSystemColor = resolveColorMap(SOURCE_SYSTEM_COLOR);
  const resolvedEdgeColor = resolveColorMap(EDGE_COLOR);
  const resolvedDefault = toCanvasColor(DEFAULT_COLOR);
  const resolvedNoSourceSystem = toCanvasColor(NO_SOURCE_SYSTEM_COLOR);

  const nodeColorStyles: cytoscape.StylesheetCSS[] =
    colorBy === "system"
      ? [
          ...Object.entries(resolvedSourceSystemColor).map(([system, color]) => ({
            selector: `node[sourceSystem = "${system}"]`,
            css: { "background-color": color },
          })),
          {
            selector: 'node[sourceSystem = ""]',
            css: { "background-color": resolvedNoSourceSystem },
          },
        ]
      : Object.entries(resolvedKindColor).map(([kind, color]) => ({
          selector: `node[kind = "${kind}"]`,
          css: { "background-color": color },
        }));
  const edgeStyles: cytoscape.StylesheetCSS[] = Object.entries(resolvedEdgeColor).map(
    ([type, color]) => ({
      selector: `edge[type = "${type}"]`,
      css: { "line-color": color, "target-arrow-color": color },
    })
  );
  return [
    {
      selector: "node",
      css: {
        "background-color": resolvedDefault,
        width: "data(size)",
        height: "data(size)",
        "border-width": 1,
        "border-color": c.background,
        label: "data(label)",
        "font-size": 8,
        "font-family": "DM Sans, sans-serif",
        "text-valign": "bottom",
        "text-halign": "center",
        "text-margin-y": 3,
        color: c.mutedForeground,
        "text-background-color": c.background,
        "text-background-opacity": 1,
        "text-background-padding": "2px",
      } as cytoscape.Css.Node,
    },
    ...nodeColorStyles,
    {
      selector: "edge",
      css: {
        width: 1,
        "line-color": c.border,
        "target-arrow-color": c.border,
        "target-arrow-shape": "none",
        "curve-style": "bezier",
        opacity: 0.5,
      },
    },
    ...edgeStyles,
    {
      selector: 'edge[type != "CONTAINS"]',
      css: {
        "line-style": "dashed",
        opacity: 0.8,
        "target-arrow-shape": "triangle",
        label: "data(label)",
        "font-size": 7,
        "font-family": "DM Sans, sans-serif",
        "text-rotation": "autorotate",
        color: c.mutedForeground,
        "text-background-color": c.background,
        "text-background-opacity": 1,
        "text-background-padding": "2px",
      } as cytoscape.Css.Edge,
    },
    ...(rootId
      ? [
          {
            selector: `node[id = "${rootId}"]`,
            css: { "border-width": 3, "border-color": c.ink },
          } as cytoscape.StylesheetCSS,
        ]
      : []),
    {
      selector: "node.hovered",
      css: { "border-width": 3, "border-color": c.ink },
    },
    {
      selector: "node.cluster",
      css: {
        shape: "round-rectangle",
        "background-color": c.muted,
        "border-width": 2,
        "border-color": c.mutedForeground,
        "border-style": "dashed",
      },
    },
    // Click-a-node-to-highlight-its-neighborhood (docs/UI.md "Graph
    // views"): clicking fades everything else instead of just selecting
    // the node, so "what's connected to this" is visible at a glance on
    // a dense graph without hunting for thin lines. `.faded` is applied
    // after the kind/edge-type rules above on purpose — later rules win
    // ties in cytoscape's stylesheet, so this reliably dims a highlighted
    // node's own kind color too, not just the default.
    {
      selector: ".faded",
      css: { opacity: 0.12 },
    },
    {
      selector: "node.highlighted",
      css: { "border-width": 3, "border-color": c.ink, opacity: 1 },
    },
    {
      selector: "edge.highlighted",
      css: { opacity: 1, width: 2.5, "target-arrow-shape": "triangle" },
    },
  ];
}

type LayoutMode = "auto" | "circular" | "tree" | "force";

const LAYOUT_LABELS: Record<LayoutMode, string> = {
  auto: "Auto",
  circular: "Circular",
  tree: "Tree",
  force: "Force",
};

export function GraphView({
  graph,
  rootId,
  onSelectNode,
  defaultLayout = "auto",
}: {
  graph: CatalogGraph;
  rootId?: string;
  onSelectNode: (nodeId: string) => void;
  /** Which layout to start on — "auto" picks tree vs. force per-graph
   * (see the isHierarchyShaped heuristic below); a caller with a strong
   * opinion (Enterprise Graph defaults to "circular") can override it.
   * The user can always switch via the on-canvas toggle regardless. */
  defaultLayout?: LayoutMode;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const [hovered, setHovered] = useState<CatalogNode | null>(null);
  const [hiddenKinds, setHiddenKinds] = useState<Set<string>>(new Set());
  const [expandedClusters, setExpandedClusters] = useState<Set<string>>(new Set());
  const [layoutMode, setLayoutMode] = useState<LayoutMode>(defaultLayout);
  // A real user ask: rather than click every "N × Kind" box one at a
  // time to confirm what's actually in it, show every node individually
  // up front. Grouping stays the default (a real screen fills up fast —
  // one graph here had 101 same-parent Pull Requests) but is one click
  // away from fully off.
  const [groupingEnabled, setGroupingEnabled] = useState(true);
  // A real user ask: "I just want to see the relationship between cross
  // system[s] — can you color each system with a color?" Kind-coloring
  // (the default) distinguishes a STORY from a PULL_REQUEST but says
  // nothing about which vendor a node came from, which is exactly what
  // matters when the question is "does this edge actually cross vendors."
  const [colorMode, setColorMode] = useState<ColorMode>("kind");

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
        group = {
          id: `cluster:${key}`,
          parentId: n.parent_id,
          kind: n.kind,
          memberIds: [],
          sourceSystem: n.source_system,
        };
        siblingGroups.set(key, group);
      }
      group.memberIds.push(n.id);
    }
    const clusters = groupingEnabled
      ? Array.from(siblingGroups.values()).filter(
          (g) => g.memberIds.length > CLUSTER_THRESHOLD && !expandedClusters.has(g.id)
        )
      : [];
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
        source_system: cluster.sourceSystem,
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
        return {
          data: {
            id: n.id,
            kind: n.kind,
            size,
            label: truncateLabel(n.name),
            sourceSystem: n.source_system ?? "",
          },
        };
      }),
      ...clusters.map((cluster) => {
        const totalDegree = cluster.memberIds.reduce((sum, id) => sum + (degree.get(id) ?? 0), 0);
        const size = Math.min(60, Math.max(14, 8 + Math.sqrt(totalDegree) * 6));
        return {
          data: {
            id: cluster.id,
            kind: cluster.kind,
            size,
            label: truncateLabel(`${cluster.memberIds.length} × ${kindLabel(cluster.kind)}`),
            sourceSystem: cluster.sourceSystem ?? "",
          },
          classes: "cluster",
        };
      }),
      ...clusters.map((cluster) => ({
        data: {
          id: `${cluster.id}:edge`,
          source: cluster.parentId,
          target: cluster.id,
          type: "CONTAINS",
        },
      })),
      // A non-CONTAINS edge touching a collapsed member is redirected to
      // point at the cluster node instead of being dropped — found live,
      // against a real multi-vendor dataset: every one of 23 real
      // cross-system MENTIONS edges (a Confluence ADR citing a specific
      // GitHub PR, a Jira ticket citing a specific issue) touched a PR/
      // Issue that was itself one of thousands of same-repo siblings, so
      // the old "just drop it" rule (written when cross-links really
      // were rare — 2 in the whole dataset at the time) silently erased
      // every single one, making GitHub look completely disconnected
      // from Confluence/Jira even though the data was fully connected.
      // CONTAINS is excluded here on purpose: every collapsed member's
      // own CONTAINS-to-parent edge would just duplicate the one
      // explicit cluster->parent edge already added above.
      ...(() => {
        const seen = new Set<string>();
        const out: { data: { id: string; source: string; target: string; type: string; label: string } }[] = [];
        for (const e of graph.edges) {
          const srcCluster = collapsedMemberOf.get(e.src_id);
          const dstCluster = collapsedMemberOf.get(e.dst_id);
          if (!srcCluster && !dstCluster) {
            out.push({
              data: {
                id: e.id,
                source: e.src_id,
                target: e.dst_id,
                type: e.type,
                label: e.type === "CONTAINS" ? "" : edgeLabel(e.type),
              },
            });
            continue;
          }
          if (e.type === "CONTAINS") continue;
          if (srcCluster && dstCluster && srcCluster.id === dstCluster.id) continue;
          const source = srcCluster ? srcCluster.id : e.src_id;
          const target = dstCluster ? dstCluster.id : e.dst_id;
          const key = `${source}->${target}:${e.type}`;
          if (seen.has(key)) continue;
          seen.add(key);
          out.push({
            data: { id: `cluster-edge:${key}`, source, target, type: e.type, label: edgeLabel(e.type) },
          });
        }
        return out;
      })(),
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

    // A real user report: a topic search graph (a handful of matches,
    // their ancestor chains, and their cross-links) came back with 50+
    // real nodes but only ~7 were visually distinguishable — the rest
    // were low-degree "leaf" nodes (a single edge to one shared hub, e.g.
    // every card's own PROJECT ancestor) that `cose`'s old repulsion
    // constants weren't strong enough to keep from overlapping directly
    // on top of each other. Stronger separation fixes that regardless of
    // layout algorithm.
    const edgeElements = elements.filter(
      (el): el is { data: { id: string; source: string; target: string; type: string } } =>
        "source" in el.data
    );
    const containsEdgeCount = edgeElements.filter((el) => el.data.type === "CONTAINS").length;
    const containsRatio = edgeElements.length > 0 ? containsEdgeCount / edgeElements.length : 1;
    // A second, separate real user report: even where the layout wasn't
    // overlapping, `cose` still doesn't know CONTAINS means "parent of" —
    // it just treats every edge as an equal attraction force, so a small
    // clean hierarchy (a team, its context space, a couple of repos) came
    // out as an undirected clump instead of a tree. When most of a
    // graph's edges really are CONTAINS, a directed tree layout is both
    // more legible *and* guarantees no two nodes share a position — the
    // BFS grid gives every node its own cell.
    const isHierarchyShaped = !isVeryLarge && containsRatio >= 0.6;
    let hierarchyRoots: string[] | undefined;
    if (isHierarchyShaped) {
      const hasIncomingContains = new Set(
        edgeElements.filter((el) => el.data.type === "CONTAINS").map((el) => el.data.target)
      );
      const allNodeIds = elements
        .filter((el) => !("source" in el.data))
        .map((el) => el.data.id as string);
      const roots = allNodeIds.filter((id) => !hasIncomingContains.has(id));
      hierarchyRoots = roots.length > 0 ? roots : undefined;
    }

    const treeLayout: cytoscape.LayoutOptions = {
      name: "breadthfirst",
      directed: true,
      roots: hierarchyRoots ?? (rootId ? [rootId] : undefined),
      spacingFactor: isVeryLarge ? 0.9 : 1.4,
      animate: false,
    } as cytoscape.LayoutOptions;
    const forceLayout: cytoscape.LayoutOptions = {
      name: "cose",
      animate: false,
      nodeRepulsion: () => 16000,
      idealEdgeLength: () => 80,
      nodeOverlap: 24,
      gravity: 40,
      numIter: effectiveCount > 150 ? 400 : 1000,
    } as cytoscape.LayoutOptions;
    // Concentric rings by degree (the most-connected nodes end up in the
    // center) — a real user report that the Enterprise Graph "still looks
    // like a tree" even after the hierarchy-aware breadthfirst fix above:
    // a tree reads as containment, but for a whole-org overview a radial
    // layout communicates "this is one interconnected web," not "a
    // reporting chain," which is closer to what that page is actually
    // showing (business structure *and* cross-vendor links together).
    const circularLayout: cytoscape.LayoutOptions = {
      name: "concentric",
      concentric: (node: cytoscape.NodeSingular) => node.degree(),
      levelWidth: () => 1,
      minNodeSpacing: isVeryLarge ? 20 : 40,
      animate: false,
    } as cytoscape.LayoutOptions;

    const layout: cytoscape.LayoutOptions =
      layoutMode === "circular"
        ? circularLayout
        : layoutMode === "tree"
          ? treeLayout
          : layoutMode === "force"
            ? forceLayout
            : isVeryLarge || isHierarchyShaped
              ? treeLayout
              : forceLayout;

    const cy = cytoscape({
      container: containerRef.current,
      elements,
      style: buildStylesheet(rootId, colorMode),
      layout,
      minZoom: 0.1,
      maxZoom: 4,
    });

    // Click a node to highlight its immediate neighborhood (itself, its
    // direct edges, and whatever's on the other end of them) and fade
    // everything else — a real user ask: "when I click a node, the nodes
    // related to it should be highlighted." Clicking empty canvas clears
    // it. Cluster nodes keep their existing expand-on-click behavior
    // instead (highlighting a "12 × Story" placeholder isn't useful).
    cy.on("tap", "node", (evt) => {
      const target = evt.target;
      const id = target.id();
      if (id.startsWith("cluster:")) {
        setExpandedClusters((prev) => new Set(prev).add(id));
        return;
      }
      const neighborhood = target.closedNeighborhood();
      cy.elements().removeClass("highlighted").addClass("faded");
      neighborhood.removeClass("faded").addClass("highlighted");
      onSelectNode(id);
    });
    cy.on("tap", (evt) => {
      if (evt.target === cy) {
        cy.elements().removeClass("faded highlighted");
      }
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
  }, [graph, rootId, onSelectNode, expandedClusters, layoutMode, groupingEnabled, colorMode]);

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
  const systemsPresent = Array.from(new Set(graph.nodes.map((n) => n.source_system ?? ""))).sort();

  return (
    <div className="flex gap-3">
      <div className="flex-1">
        <div className="mb-2 flex flex-wrap items-center gap-3 text-xs">
          <span className="flex items-center gap-1.5">
            <span className="text-muted-foreground">Layout:</span>
            {(Object.keys(LAYOUT_LABELS) as LayoutMode[]).map((mode) => (
              <Button
                key={mode}
                size="sm"
                active={layoutMode === mode}
                onClick={() => setLayoutMode(mode)}
                className="h-6 px-2"
              >
                {LAYOUT_LABELS[mode]}
              </Button>
            ))}
          </span>
          <Button
            size="sm"
            active={!groupingEnabled}
            onClick={() => setGroupingEnabled((v) => !v)}
            className="h-6 px-2"
            title='Large same-kind sibling groups (e.g. "32 × Task") collapse into one box by default — turn off to always show every node individually.'
          >
            {groupingEnabled ? "Group large sets" : "Showing all individually"}
          </Button>
          <span className="flex items-center gap-1.5">
            <span className="text-muted-foreground">Color by:</span>
            {(["kind", "system"] as ColorMode[]).map((mode) => (
              <Button
                key={mode}
                size="sm"
                active={colorMode === mode}
                onClick={() => setColorMode(mode)}
                className="h-6 px-2"
              >
                {mode === "kind" ? "Kind" : "System"}
              </Button>
            ))}
          </span>
        </div>
        <div className="relative">
          <div ref={containerRef} className="h-[520px] w-full rounded-lg border border-border bg-card" />
          <div className="pointer-events-none absolute bottom-2 left-2 rounded-md bg-popover/90 px-2 py-1 text-xs text-popover-foreground shadow-sm">
            {hovered ? (
              <>
                <span className="font-medium">{hovered.kind}</span>: {hovered.name}
              </>
            ) : (
              <span className="text-muted-foreground">
                Hover for a name · click to highlight its connections (click empty space to clear)
                · scroll to zoom
              </span>
            )}
          </div>
        </div>
        <div className="mt-2 flex flex-wrap gap-3 text-xs text-muted-foreground">
          {edgeTypesPresent.map((type) => {
            const color = EDGE_COLOR[type] ?? TOKEN.border;
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
        {colorMode === "system" && (
          <div className="mt-2 flex flex-wrap gap-3 text-xs text-muted-foreground">
            {systemsPresent.map((system) => (
              <span key={system} className="flex items-center gap-1.5">
                <span
                  className="inline-block h-2.5 w-2.5 rounded-full"
                  style={{
                    backgroundColor:
                      system === ""
                        ? NO_SOURCE_SYSTEM_COLOR
                        : (SOURCE_SYSTEM_COLOR[system] ?? DEFAULT_COLOR),
                  }}
                />
                {system === "" ? "Business / logical" : (SOURCE_SYSTEM_LABELS[system] ?? system)}
              </span>
            ))}
          </div>
        )}
      </div>
      <div className="w-44 shrink-0 rounded-lg border border-border bg-card p-2">
        <div className="mb-1 flex items-center justify-between text-xs font-medium text-muted-foreground">
          <span>Filter by kind</span>
          {hiddenKinds.size > 0 && (
            <button
              onClick={() => setHiddenKinds(new Set())}
              className="text-muted-foreground hover:text-foreground"
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
                className={clsx(
                  "flex w-full items-center gap-1.5 rounded-md px-1 py-0.5 text-left text-xs hover:bg-accent",
                  hidden ? "text-muted-foreground/50" : "text-muted-foreground"
                )}
                title={hidden ? "Hidden — click to show" : "Shown — click to hide"}
              >
                <span
                  className="inline-block h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{ backgroundColor: hidden ? TOKEN.border : (KIND_COLOR[kind] ?? DEFAULT_COLOR) }}
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
