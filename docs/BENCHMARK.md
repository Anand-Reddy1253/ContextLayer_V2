# Benchmark: does Context Fabric actually reduce tokens/tool-calls?

This is the honest accounting the rest of the project gets judged against — not an
assertion, a number that can be checked and re-derived. Two passes:

1. **Assumption-based** (this document, §1-3): reasoned call/token estimates built from
   real native MCP server behavior (researched, sourced) and Context Fabric's actual
   current response shapes. Not run — a hypothesis.
2. **Empirical** (§4, added once the golden dataset exists): the same tasks, actually
   run against the real DevOnHire/TalentFlow data, with real payload sizes and measured
   recall (did it actually find the right things).

## Method: split "discovery" from "fetch"

Every one of these tasks has two phases that behave very differently:

- **Discovery** — figuring out *what exists and where*. This is the phase Context
  Fabric's `search-cards` claims to collapse from N per-vendor calls into one.
- **Fetch** — reading the full content of the specific things discovery found. This
  cost is **irreducible** — the content has to be read either way — so the honest
  comparison isn't "CF vs. no CF" on fetch, it's "does CF's `locator` let the fetch call
  land correctly on the first try, or does the agent have to guess?"

Conflating the two phases is how you get an over-claimed savings number. Keeping them
separate is also what surfaced the locator/native-tool-shape mismatch (see the plan) —
without splitting them out, a token count that looked good on paper was hiding a fetch
phase that could actually be *worse* than doing nothing.

## 1. Native MCP server costs, researched (sourced)

| Vendor | Discovery call | Discovery response | Fetch call | Fetch format |
|---|---|---|---|---|
| GitHub | `search_code` | cheap: repo/path/score + short fragment | `get_file_contents` | raw markdown/plain text |
| GitHub | `search_issues`/`search_pull_requests` | **expensive**: full issue/PR object incl. body, no separate hydrate step exists | *(search already returns full content)* | markdown/plain text |
| Azure DevOps | `wit_query_by_wiql` | cheap: **ids only** | `wit_get_work_items_batch` | **HTML by default** for large text fields unless `format: Markdown` requested explicitly |
| Confluence | `confluence_search` (CQL) | cheap: excerpt/highlight per hit | get-page | **storage format** (XML-ish markup), not markdown, unless `export_view` requested |
| Jira | `jira_search` (JQL) | **can be expensive**: full ADF per hit unless `fields` explicitly restricted | get-issue | **ADF** (nested JSON), `renderedFields` confirmed incomplete for nested content (comments) |
| Teams | `search_messages` (KQL) | **returns full message content per hit**, not a snippet | `get_channel_messages` | auto-converted to clean markdown by default (best-behaved of the four) |

Sources: `github/github-mcp-server` docs + community tool references; `microsoft/azure-devops-mcp`
TOOLSET.md/EXAMPLES.md + DeepWiki; Atlassian's official `atlassian-mcp-server` docs +
Jira/Confluence Cloud REST API docs; `floriscornel/teams-mcp` docs. Full citations in
the research pass that produced this table (this session's plan-mode transcript).

## 2. Context Fabric's actual cost, from what's built

- `search-cards`: **1 call**, always. Never embeds full content (ADR-003) — every node
  in the response (match, ancestors, linked nodes) is a summary: name, kind, path,
  locator. Real measured payload for `q=deploy` scoped to Platform Squad (5 real
  results, §4): comparable per-result weight to a native excerpt-based search, but adds
  ancestor chain + business_context + locator that no native search includes.
- Fetch phase: **before** the locator fix (this plan's step 2), `locator` was
  `{source_system, native_id, url}` — enough for a person, not necessarily the exact
  input a native MCP tool call needs (GitHub's `get_file_contents` wants
  `{owner, repo, path, ref}`, not a URL). **After** the fix, `locator.native_call` gives
  the literal tool name + params, making the fetch phase identical in cost to the
  native-discovery-then-fetch path.

## 3. Four tasks, reasoned (not yet measured)

All four against the real, currently-synced DevOnHire/TalentFlow data (Platform Squad's
context space: 2 Azure DevOps bindings, 2 GitHub repos, 3 Confluence spaces).

### Task A — "Find deployment-related content for DevOnHire"
Real answer set: 2 ADO items, 3 Confluence pages (verified live this session).

| | Discovery calls | Discovery tokens (est.) | Fetch calls | Fetch tokens (est.) |
|---|---|---|---|---|
| Native, cold | 3 (ADO wiql + GitHub search, mostly empty + Confluence CQL) | ~850 | 5 (2 ADO batch-hydrate + 3 Confluence get-page) | ~4,600 |
| Context Fabric | 1 (`search-cards`) | ~2,000 | 5 (same targeted fetches, *after* locator fix) | ~4,600 |

**Reading**: discovery calls drop 3→1 — the real, clear win. Discovery *tokens* are
comparable or even slightly higher for CF in one call (it's carrying more structure per
result) — the win is call count, not raw discovery tokens. Fetch phase is a wash *only
if the locator fix lands*; before it, CF's fetch phase risks malformed calls the native
path never had a chance to make.

### Task B — "What does Platform Squad own?"
Pure business-context question — no native MCP server can answer this at all; the
concept doesn't exist in any vendor's data model.

| | Discovery calls | Discovery tokens (est.) | Fetch calls |
|---|---|---|---|
| Native, cold | N/A — not answerable without being told the answer out-of-band | — | — |
| Context Fabric | 1 (`GET /context-spaces/talentflow%2Fdevonhire`) | ~600 | 0 (answer *is* the bindings list) |

**Reading**: the clean case for Context Fabric — not a search-quality question at all,
a question about a fact no native tool tracks.

### Task C — "Find architecture decisions relevant to the API service"
Real answer set: ADR-0004, ADR-0007 (Confluence, "Talentflow API" space) — governance
content that was, before this session, unbound and invisible to any scoped query.

| | Discovery calls | Discovery tokens (est.) | Fetch calls | Fetch tokens (est.) |
|---|---|---|---|---|
| Native, cold | 1 (Confluence CQL — *if* the agent knows to search Confluence and knows to search this specific space; it wasn't bound, so nothing tells it to*) | ~300 | 2 (get-page × 2 ADRs) | ~2,400 |
| Context Fabric | 1 (`search-cards`, business-scoped) | ~900 | 2 (same, after locator fix) | ~2,400 |

**Reading**: discovery call count ties here (1 vs 1) *given* the agent already knows to
search Confluence — but that "given" is doing a lot of work. The real advantage isn't
visible in the call count for this task; it's that CF *tells the agent Confluence is
even relevant in the first place*, which a cold native search across the wrong vendor
(or no vendor) can't.

### Task D — "Find the PR assigning roles to a user profile and its related work item"
Real, honest negative case, found this session: PR `AB#56 Assign skills to an employee
profile` and ADO item `Implement API for assigning roles to AD users` are topically
related but **share no real edge** — `AB#56` doesn't correspond to any currently-synced
work item id. `search-cards` surfaces both (keyword coincidence), same as a native
GitHub + ADO search would, but **neither approach can claim a confirmed relationship
between them** — this is exactly the kind of case the confidence-differentiation work
(deferred, see the earlier plan draft) exists to make honest rather than silently wrong.

## 4. Golden dataset — empirical (run)

`tests/benchmark/golden_dataset.json` — 4 real queries against the real, live
DevOnHire/TalentFlow workspace (Platform Squad's context space), each expected set
hand-verified by reading the actual results. Run via `scripts/run_benchmark.py` against
a live local server, at both `search-cards`' real default (`limit=20` — what an agent
gets unless it explicitly asks for more) and its hard cap (`limit=100`). Token estimate
is `payload_bytes / 4` (rough, not a real tokenizer count — good for comparing tasks
against each other, not a billing figure).

| Task | Limit | Results | Payload bytes | Est. tokens | Recall | Precision |
|---|---|---|---|---|---|---|
| `deploy` | 20 | 5 | 11,565 | 2,891 | 100% (5/5) | 100% (5/5) |
| `deploy` | 100 | 5 | 11,565 | 2,891 | 100% (5/5) | 100% (5/5) |
| `ADR` | 20 | 6 | 13,062 | 3,265 | 100% (6/6) | 100% (6/6) |
| `ADR` | 100 | 6 | 13,062 | 3,265 | 100% (6/6) | 100% (6/6) |
| `skill` | 20 | 10 | 27,608 | 6,902 | 100% (10/10) | 100% (10/10) |
| `skill` | 100 | 10 | 27,608 | 6,902 | 100% (10/10) | 100% (10/10) |
| `candidate` | 20 (default) | 20 | 116,249 | **29,062** | n/a (documented) | n/a |
| `candidate` | 100 | 100 | 412,221 | **103,055** | n/a (documented) | n/a |

### Reading this honestly

**The good news, measured, not assumed**: for three well-scoped real queries, one
`search-cards` call returned every real relevant item across Azure DevOps, GitHub, and
Confluence with **zero misses and zero noise** — 100% recall and precision, in one call,
at a few thousand tokens. That's the actual evidence for the discovery-phase claim in
§3's Task A/C reasoning, not a hypothesis anymore.

**The bad news, also measured, not assumed**: `candidate` — a single common word,
unsurprising for a recruiting platform's own data — costs **~29,000 estimated tokens
at search-cards' own real default limit of 20 results**, and **~103,000 at its hard cap
of 100** if an agent (reasonably) asks for more because 20 clearly wasn't everything.
Even the default-limit number is large for one tool call, for a query an agent would
plausibly make ("find the candidate-related work"). This is challenge #1 from the
original critique, no longer an assertion: **our lack of relevance ranking doesn't just
return worse-ordered results than native search — past a certain query breadth, it
returns a payload big enough to defeat the entire point of a token-conscious layer**,
where a native system's real ranking would have kept even 20 requested results small by
returning its actual top 20, not 20 arbitrary substring matches.

**What this actually tells the architecture**: `search-cards` is doing real,
measured work reducing tokens/tool-calls for *specific, well-scoped* queries — the
kind an agent makes once it already knows roughly what it's looking for. It is not
currently safe for *broad* queries, where it can cost more than doing nothing, **even at
its own default limit**. The missing piece isn't a nice-to-have — it's the same one
flagged in the confidence-scoring plan draft and the native-search-delegation flag
above: **relevance ranking is not optional if this system is going to be used on real
query volume, not hand-picked golden queries.** Checked the actual code, not assumed:
`search_cards` already sorts by score before truncating to `limit` (`catalog.py`,
`scored.sort(...)` then `scored[:limit]`) — the bug isn't truncate-before-sort, it's
that `_score_match` only has 4 discrete tiers (1.0/0.9/0.7/0.4), so a query like
`candidate` against ~100 titles that mostly *start with* "Candidate" produces dozens of
exact ties at 0.9 with no secondary signal to break them — the "top 20" is an arbitrary
slice of a tie, not a real ranking. Native-search delegation (already flagged as the
real fix for search quality) would fix this as a side effect; a cheaper stopgap would be
a secondary tie-breaker (e.g. shorter name = more specific match, ranks first) so ties
aren't resolved by incidental row order.
