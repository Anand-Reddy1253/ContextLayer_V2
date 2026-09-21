# Context Fabric Evaluation — Compressed MCP Layer vs. GitHub API Baseline

**Environment:** `context-fabric-sqlite-trial` (REST API on :8001, SQLite-backed), repo checkout `C:\Users\a.kakaraddi\Repos\ContextLayer_v2`.
**Dataset:** 4 real getsentry repos (relay, snuba, symbolicator, vroom; ~17,349 real GitHub nodes) + fictional Jira project `OBS` (7 tickets) + fictional Confluence space `OBS` (7 pages) + a small business tree (4 SERVICE nodes / 4 TEAM nodes, bound only to the 4 GitHub repos, capability=CODE).
**Date measured:** 2026-09-16.

**Methodology.** tokens ≈ characters / 4, applied uniformly. Approach A ("with Context Layer") calls the real compressed functions in `src/context_fabric/mcp/tools.py` directly inside the trial container via `docker exec … python`, and every number below is the literal length of the JSON string those functions returned — i.e. the real MCP payload size. Approach B ("without Context Layer") uses GitHub's public REST/Search API directly (unauthenticated), per the coordinator's correction — no web search, no browsing, raw API calls only. Every character count below is measured, not estimated, **except** the "final answer text" component, which is a rough estimate (~100–250 chars/question) applied identically to both approaches since it's a small, symmetric term that does not change the conclusions. The `SKILL.md` file (`.claude/skills/context-fabric-query/SKILL.md`, 8,301 chars) is counted **once for the whole 25-question batch** in the headline number, with the per-question alternative also shown per the brief.

---

## Two real bugs hit while running Approach A

1. **`describe_schema_tool()` is completely broken on the SQLite trial.** Every call (Q0 and Q25) raised `sqlite3.OperationalError: no such function: jsonb_object_keys`. The query at `src/context_fabric/api/routes/catalog.py:1648` uses `func.jsonb_object_keys(NodeORM.attributes)`, a **Postgres-only** JSONB function, with no SQLite fallback. Since the skill's very first instruction is "always call `describe_schema` first," a real agent following the skill hits a hard failure before making any other call, on this specific (SQLite) deployment.
2. **Relation-anchored `search_entities` queries are broken on SQLite.** Q10's `{"relation":"MENTIONS","operator":"relatedTo","value":"OBS-3","direction":"downstream"}` raised `sqlite3.ProgrammingError: Error binding parameter 1: type 'UUID' is not supported` — the recursive-CTE relation query binds a Python `UUID` object, which `aiosqlite` can't adapt (Postgres/asyncpg can). Any relation-anchored query is unusable on this trial.

Both are counted honestly below: the error string itself is the "result" a real MCP client would receive, and its length is charged as normal.

---

## The 25 questions

1. How many pull requests exist in each of the 4 getsentry repos?
2. How many open vs. merged/closed PRs are there per repo?
3. How many issues exist per repo, broken down by state?
4. Which of the 4 repos currently has the most open issues?
5. Who owns the Snuba service — which team, and which repo is it bound to?
6. List all 4 services and their owning teams.
7. Which Jira tickets exist in project OBS, and what are their types/states?
8. Given ticket ref "OBS-3", what repo/team/product does it resolve to?
9. Which Confluence pages exist in the OBS space, and what kind of doc is each?
10. Which Jira tickets have a structured link to a real GitHub PR, and which PRs?
11. Is there a PRD with no matching ADR (or vice versa) among the OBS pages?
12. Which of the 4 repos had a PR merged/updated most recently?
13. Which of the 4 repos has gone longest without an updated PR?
14. What is the total node count synced across all 4 vendors combined?
15. Count of Jira OBS tickets broken down by issue kind.
16. Which OBS Jira tickets have NO linked GitHub PR?
17. What business context (team/service) does GitHub PR `getsentry/symbolicator#2048` belong to?
18. Which ContextSpace/team is each GitHub repo bound to, and with what capability?
19. What is the combined count of currently-open PRs across all 4 repos?
20. Which repo has the largest total PR volume ever opened?
21. What incident does the Confluence postmortem describe, and which PRs does it reference?
22. Search across GitHub + Jira + Confluence for "PII scrubbing" — what turns up?
23. Do any of the 4 repos declare AI agent/skill assets Context Fabric has scanned?
24. Which Jira ticket was most recently updated?
25. What relation (edge) types exist in the whole catalog, and how many of each?

---

## Per-question results

Legend: **calls A** = new MCP tool calls made (a reused prior result costs 0 and is noted); **calls B** = new GitHub API calls made. Char columns are the *sum of that approach's argument/URL strings + result strings* for that question.

| # | Answer (Context Layer) | Answer (GitHub API only) | calls A | chars A | calls B | chars B | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | relay 5,572 · snuba 8,152 · symbolicator 1,789 · vroom 660 (`aggregate_entities`, group_by state, 4 calls) | Same totals (search API `total_count`) — relay 5,572, snuba 8,152, symbolicator 1,789, vroom 660 | 4 | 1,297 | 4 | 13,872 | Tie on correctness; A ~10x cheaper |
| 2 | relay 25 open/5,547 closed · snuba 13/8,139 · symbolicator 5/1,784 · vroom 12/648 | relay 24 open/4,988 merged · snuba 14/6,808 · symbolicator 5/1,624 · vroom 12/610 (open counts drifted ±1 — real repos changed between the two passes, minutes apart) | 0 (reuses Q1) | 0 | 8 | 29,088 | A free (reuse); B pays full 8-call verbose cost |
| 3 | relay 68 open/712 closed · snuba 3/117 · symbolicator 34/222 · vroom 1/13 | relay 68/712 · **snuba 3/299** · symbolicator 34/222 · vroom 1/13 | 4 | 1,264 | 8 | 84,251 | **Snuba closed-issue count diverges hugely (117 vs 299) — see finding below** |
| 4 | relay has the most open issues (68) | relay (68) — same ranking | 0 (reuses Q3) | 0 | 0 (reuses Q3) | 0 | Agree; both free once base data is in hand |
| 5 | Snuba → team "Search & Analytics" → repo `getsentry/snuba` | Unanswerable — no team/ownership concept on public GitHub | 1 | 190 | 0 | 0 | A only source of truth |
| 6 | Relay/Ingestion & Relay · Snuba/Search & Analytics · Symbolicator/Native & Symbolication · Vroom/Profiling | Unanswerable | 1 | 4,126 | 0 | 0 | A only source of truth |
| 7 | 7 tickets: EPIC OBS-1 (In Progress), STORY OBS-2 (Done), STORY OBS-3 (Done), TASK OBS-4 (In Progress), BUG OBS-5 (Done), TASK OBS-6 (Done), BUG OBS-7 (In Progress) | Unanswerable — Jira is fictional/private to this trial | 1 | 5,621 | 0 | 0 | A only source of truth |
| 8 | `resolve_scope("OBS-3")` → **resolved: false**, reason: "no context space binding covers this object's ancestry" (correctly reflects that only GitHub repos have ContextSpace bindings, not Jira) | Unanswerable — concept doesn't exist | 1 | 364 | 0 | 0 | A correctly reports "no", which is itself the useful answer |
| 9 | 7 pages: Home, ADR-142, ADR-143, ADR-88, PRD (EAP routing), Postmortem (Symbolicator), Meeting Notes (flamegraph) — **note: 3 ADRs, not 2 as briefed** | Unanswerable | 1 | 9,305 | 0 | 0 | A only source of truth; also caught a brief/reality mismatch |
| 10 | **Tool call failed** (UUID-binding bug, see above). Workaround: the same MENTIONS edges (OBS-3→relay#6389/#6391/#6392) appeared incidentally as side-context in Q7's plain property search | Attempted org-wide search for `"OBS-"` in title/body: 18 hits, all false positives (real English words/PR text containing "OBS-" as a substring) — no reliable signal | 1 (errored) | 1,031 | 1 | 28,015 | Neither approach cleanly answers this; A degrades to a workaround, B is actively misleading noise |
| 11 | 3 ADR pages (2 on Relay PII, 1 on Symbolicator download limits) vs. 1 PRD (EAP routing, Snuba) — no ADR exists for the EAP work the PRD describes, and no PRD backs either PII ADR | Unanswerable | 2 | 7,370 | 0 | 0 | A only source of truth |
| 12 | Latest PR per repo: relay 14:55:22Z · snuba 13:51:16Z · symbolicator 12:27:04Z · vroom 14:11:21Z → **relay freshest** at measurement time | relay 15:29:53Z (#6388) · **snuba 15:50:57Z (#8479) — newest** · symbolicator 12:27:04Z · vroom 14:11:21Z → **snuba freshest** | 4 | 1,703 | 4 | 79,747 | **Approaches disagree on which repo is freshest** — both correct, live repos moved between passes minutes apart; symbolicator = stalest in both |
| 13 | Symbolicator is stalest (12:27:04Z, reuses Q12) | Symbolicator is stalest (reuses Q12) | 0 | 0 | 0 | 0 | Agree |
| 14 | 17,349 github + 24 confluence + 8 jira + 8 business = **17,389 total** (1 `aggregate_entities` call) | Unanswerable as one number — would need private Jira/Confluence access to even attempt | 1 | 196 | 0 | 0 | A only source of truth; textbook global-count use case |
| 15 | TASK 2, STORY 2, BUG 2, PROJECT 1, EPIC 1 | Unanswerable | 1 | 333 | 0 | 0 | A only source of truth |
| 16 | The dedicated `notRelatedTo` wildcard query didn't isolate anything (returned all 7 — `value:"*"` isn't a real anchor, a real gap in how "not related to anything" is expressed). Cross-referencing Q7/Q24's edge lists by hand: **OBS-1 (the EPIC)** is the only ticket with no outgoing MENTIONS to GitHub | Unanswerable | 1 | 5,627 | 0 | 0 | A gets there, but only via manual cross-reference, not the intended one-shot query |
| 17 | `resolve_scope("getsentry/symbolicator#2048")` → team "Native & Symbolication", service "Symbolicator", repo `getsentry/symbolicator`, product "Sentry Platform" | Unanswerable | 1 | 913 | 0 | 0 | A only source of truth |
| 18 | My `search_context("repository")` call was a query-design miss — it free-text-matched PR titles containing the word "repository," not the actual bindings. Real answer had to be reconstructed from Q5 + Q17 (4 repos ↔ 4 teams, 1:1, capability=CODE) | Unanswerable | 1 | 3,286 | 0 | 0 | A eventually correct, but this specific call wasted tokens on the wrong tool for the job |
| 19 | 55 open PRs total, **one `aggregate_entities` call, no group_by** | 24+14+5+12 = 55, matches, but required summing 4 separate multi-KB search payloads by hand — no single-call equivalent exists | 1 | 275 | 0 (reuses Q2) | 0 | **Textbook case for the aggregate tool** — 275 chars vs. ~29K for the underlying B data |
| 20 | snuba (8,152) > relay (5,572) > symbolicator (1,789) > vroom (660), reuses Q1 | Same ranking, reuses Q1 | 0 | 0 | 0 | 0 | Agree |
| 21 | Postmortem page references symbolicator PRs #2051, #2048, #2047 (download-timeout fixes) | Unanswerable — postmortem is fictional, and you'd have no way to know which real PRs to even look up without it | 1 | 4,639 | 0 | 0 | A only source of truth |
| 22 | `search_context("PII scrubbing")` returned 10 GitHub relay issues/PRs (#4382, #5156, #5131, #4368, #3338, #3336, #4990, #5815, #5168, #5064) — **none of the OBS-1 epic or its 2 ADRs surfaced in the top 10**, crowded out by generic relay history matches | GitHub search on relay alone: 158 matches, completely unfiltered by type; Jira/Confluence portion (the actual epic and ADRs) totally inaccessible | 1 | 8,072 | 1 | 50,424 | Both are noisy here; A's relevance ranking is a real weak spot worth fixing |
| 23 | `search_entities` AI_ASSET → 0 matches | 8 `contents` calls (`.claude/`, `.github/agents/`) across 4 repos → all 404 | 1 | 294 | 8 | 954 | Agree (no AI assets); B slightly cheaper here since the answer is a bare existence check |
| 24 | All 7 Jira tickets carry the **identical** sync timestamp — the fixture was loaded in one batch, so "most recently updated" isn't a meaningful question against this data | Unanswerable | 1 | 5,516 | 0 | 0 | A surfaces a real data-quality caveat instead of fabricating a winner |
| 25 | **Tool call failed** — same `jsonb_object_keys` bug as Q0. Can't answer through the MCP layer at all despite real cross-tool MENTIONS edges existing in the DB (would contradict the skill's "no cross-tool links yet" framing, but the layer can't surface it here) | Unanswerable — not a GitHub concept | 1 (errored) | 269 | 0 | 0 | Real failure — the one question A should own outright but currently cannot |

---

## Grand totals

| | Approach A (skill counted **once**) | Approach A (skill counted **per-question**) | Approach B |
|---|---|---|---|
| Question text (25×, ~2,489 chars total) | 2,489 | 2,489 | 2,489 |
| Skill file (`SKILL.md`, 8,301 chars) | 8,301 (×1) | 207,525 (×25) | — (n/a) |
| `describe_schema` session-level attempt (Q0, errors both times) | 269 | 269 | — |
| Tool-call **arguments** (all 25 questions, new calls only) | 5,968 | 5,968 | ~2,700 (URLs) |
| Tool-call **results** (all 25 questions, new calls only) | 56,946 | 56,946 | 267,847 |
| Final answer text (est., ~140 chars avg × 25) | 3,500 | 3,500 | 3,500 |
| **Total characters** | **77,473** | **276,697** | **276,536** |
| **Total tokens (÷4)** | **≈19,368** | **≈69,174** | **≈69,134** |
| Avg tokens/question | ≈775 | ≈2,767 | ≈2,765 |
| Ratio vs. Approach B | **0.28×** (skill once) | 1.0006× (skill per-Q) | 1.0× (baseline) |

**Read this carefully:** with the skill loaded once per session (the realistic case — the brief itself says a real agent does this), the context layer uses **about a quarter of the tokens** of the GitHub-API-only baseline. But if you (unrealistically) reload the 8.3KB skill file before every single question, Approach A's total is a statistical **tie** with Approach B — the skill file itself, re-paid 25 times, is almost exactly as expensive as GitHub's verbose per-call JSON payloads summed once. The skill-once assumption is doing essentially all of the work in "the context layer wins here" — it's a legitimate assumption (skills load once per session in real usage) but it is not a small footnote; without it the token story is a wash, not a win.

---

## Honest summary

**Where the context layer clearly won:** anything touching the fictional Jira/Confluence content (Q5–9, 11, 14–17, 21, 24) or a cross-system/global aggregate (Q14, Q19) — GitHub's API has zero visibility into any of it, full stop, "unanswerable" is the correct and only honest answer for Approach B on 13 of the 25 questions. Where both sides *could* answer (pure GitHub PR/issue counts, Q1–3, Q12, Q23), the context layer's `aggregate_entities` and `search_entities` responses were consistently far smaller than GitHub's raw search-API JSON, because GitHub's search endpoint returns full item objects even when `per_page=1` and only a `total_count` is wanted (Q3's 8 calls alone cost 83.5K chars on GitHub's side vs. 1.3K through Context Fabric).

**Where it didn't matter / was a wash:** Q4, Q13, Q20 — once you already have the base aggregate in hand, both approaches answer for free by re-reading data already fetched.

**Where "without" genuinely couldn't answer:** 13 of 25 questions (Q5–9, 11, 14–18, 21, 24) got a clean, honest "unanswerable" from Approach B, exactly as the brief predicted for anything crossing vendors or touching the private fixture content.

**Real failures/surprises hit while running Approach A (not softened):**
- **`describe_schema_tool` is 100% broken on this SQLite trial** (`jsonb_object_keys` is Postgres-only) — the skill's own first instruction ("always call describe_schema first") cannot be followed on this deployment. I had to reverse-engineer the kind vocabulary from source/direct SQL instead, which a real MCP-only agent could not do.
- **Relation-anchored `search_entities` queries are also broken on SQLite** (`UUID` binding error), so the one query shape purpose-built for cross-vendor traceability (Q10, Q25) is unusable here.
- **Snuba's synced closed-issue count (117) undercounts live GitHub (299) by 182** — relay/symbolicator/vroom counts matched GitHub exactly, so this looks like a real, repo-specific sync-completeness gap in the trial's snuba data, not a systemic issue.
- **Live-repo drift**: Q2 and Q12 gave different numbers/rankings between the A pass and the (several-minutes-later) B pass, because relay/snuba/vroom are real, currently-active public repos that kept receiving PRs during the measurement window. Neither number is "wrong"; this is a genuine hazard of benchmarking against live data.
- **My own tool-use missteps**: Q10's fallback, Q16's `notRelatedTo` wildcard, and Q18's free-text `search_context("repository")` all either failed outright or answered the wrong thing on the first attempt — these are charged in full above, not excluded, since a real agent would pay for them too.
- **GitHub's unauthenticated Search API rate-limited mid-run** (403s after ~10 calls/minute) and had to be retried — a real friction cost for Approach B that Approach A never faced.

**Surprising asymmetry:** the single biggest lever in this whole comparison isn't the compressed response shapes (though `aggregate_entities`'s 45–292-char count-only responses vs. GitHub's multi-KB search payloads are real and reproducible) — it's whether the 8.3KB skill file is amortized across the session or not. That assumption is doing more work than the tool-compression itself, and the report above shows both numbers so the reader can judge which one reflects their real usage pattern.
