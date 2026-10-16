# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Two audiences for this pass, both real:
- Engineers at the org using the Catalog Explorer to search/browse the synced catalog and navigate a node's neighborhood day to day (Operate: task speed and scanability matter more than first impression).
- Stakeholders evaluating whether to adopt Context Fabric, who will see the same surface as a demo (Persuade-adjacent: a strong first impression matters here too).
Design for the daily-use case first; a well-crafted Operate surface reads as credible to a stakeholder anyway, whereas the reverse is not true.

## Product Purpose

Context Fabric builds one queryable graph over org structure, connector-synced technical assets (Azure DevOps, GitHub, Confluence, Jira), and human-authored logical bindings between the two. In a 50+ team org, knowledge is split across tools with no shared map of what lives where or how it relates; Context Fabric builds that map once, keeps it in sync, and serves it deterministically. The Catalog Explorer is the human-facing surface for that map: search across all connected systems, see a match's ancestor chain and real cross-system links, and jump to the vendor's own tool for full content.

## Positioning

Deterministic, not LLM-guessed: retrieval and ranking are transparent, reproducible rule-based logic (lexical match + freshness, with an explicit opt-in cosine-similarity layer), never an LLM asked to "find something relevant." Read-only by architecture — Context Fabric has no write path to any connected vendor, so nothing here can be mistaken for the system of record. This is the reason to trust the map over just asking an LLM to guess.

## Operating Context

A single-page graph-heavy explorer: a search bar, a results list of "cards" (matched node + ancestor chain + cross-system links + business context), and an interactive node-relationship graph (Cytoscape) for the currently selected result. Runs against real, synced-in-the-background data from Azure DevOps, GitHub, Confluence, and Jira — work items, PRs, builds, pages, and AI-agent assets among the node kinds it surfaces.

## Capabilities and Constraints

- Search is keyword/freshness ranked by default; semantic (embedding-based) ranking is opt-in and best-effort (falls back silently if the local embedding model is unreachable).
- Every result node carries a `locator` for handing off to the vendor's own tool — this UI never claims to be the source of truth for content, only for discovery and relationships.
- No authentication/authorization is wired in yet — this is a pre-production, internal tool today, not a multi-tenant product.
- The underlying graph can be large (tens of thousands of nodes for one real repo); the graph view already collapses large same-kind sibling groups into a single expandable cluster rather than rendering every node.

## Brand Commitments

Visual authority: **Emagine's design system**, sourced directly from the sibling product TalentFlow/DevOnHire's real, live source (`devonrepo.visualstudio.com/DevOnHire`, `src/DevOnHire.Web/src/tailwind.css`) — not inferred, the actual tokens currently shipping there. This is binding for this pass, ported into this project's own React/Tailwind stack (the source project is Angular + spartan-ng, a different component library, but the token values and semantic naming carry over):

- **Fonts**: `DM Sans` (`--font-sans`, body/UI text), `Questrial` (`--font-display`, headings) — both need to be loaded from Google Fonts per this session's own CDN allowlist.
- **Brand ramp** (OKLCH color space): `--brand-lime: oklch(0.939 0.198 122.4)` is the sole accent color, deliberately never used for the focus ring (too low-contrast on white) — charcoal fills that role instead. `--brand-charcoal: oklch(0.314 0.011 145.3)` (+ `-raised`/`-deep` variants) and `--brand-ink: oklch(0.197 0.005 145.4)` are the dark-neutral family.
- **Semantic tokens** (both light and dark fully defined): `background`/`foreground`/`card`/`popover`/`primary`/`secondary`/`muted`/`accent`/`destructive`/`border`/`input`/`ring`, plus a distinct `sidebar` token group, plus three extra status hues for multi-state badges: `status-blue`/`status-violet`/`status-amber` (used as `bg-status-x/10 text-status-x`, same convention as the destructive badge variant) — this app's own node-kind/edge-type color coding (currently hardcoded hex in `GraphView.tsx`) is a natural fit for this exact pattern.
- **Radius**: `0.5rem` base; other radii derive from it, not set independently.
- Primary stays `--brand-lime` in both light and dark; only the surrounding neutrals (charcoal/ink) invert.

## Evidence on Hand

- The real TalentFlow/DevOnHire product (`https://devonhire-web.jollywave-bb22c3cc.westus2.azurecontainerapps.io/home`) and Emagine's own site (`https://www.emagine.org/`) were given as visual references; their actual rendered appearance was not captured (no screenshot/browser tool available this session) — the token *values* above are sourced directly from source code, which is stronger evidence than a visual impression would be, but the rendered composition/spacing/imagery of either site is not recorded here and should not be assumed.
- This project's own current UI (`ui/src/features/catalog-explorer/`) has no committed visual identity yet — plain functional Tailwind, hardcoded hex colors for node/edge kind coding, no font choice beyond the system default. Nothing there is binding; it's the starting point this pass replaces.

## Product Principles

1. Determinism is the product's whole credibility — nothing in the UI should look or feel like it's guessing (no fuzzy "AI-generated" affordances, no ambiguous confidence language).
2. Every result is a jumping-off point, not a destination — content review always hands off to the vendor's own tool; design the UI to make that handoff obvious and cheap, not to compete with it.
3. Operate first — this is used repeatedly by people doing a task, not admired once; scanability and low friction beat visual flourish.
4. Scale is real, not hypothetical — tens of thousands of same-kind nodes exist in real synced data today; every list/graph/card treatment must degrade gracefully at that scale, not just look good in a 10-item demo.

## Accessibility & Inclusion

No project-specific requirement established yet.
