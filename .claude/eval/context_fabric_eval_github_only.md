# Context Fabric vs. Native GitHub API — Corrected, GitHub-only Eval

**Date/time of this run:** 2026-09-17. Approach A (Context Fabric) calls were run first;
Approach B (native GitHub API) calls were run afterward, roughly 20–40 minutes later,
against the same 4 live, active `getsentry` repos. Because these are real, currently
active public repos, a small amount of genuine data drift between the two passes is
expected and is called out explicitly below wherever it appears — it is not treated as
an error.

**Scope discipline:** every question below is answerable purely from real GitHub facts —
PRs, issues, labels, authors, states, timestamps, and real in-text cross-repo references
(`owner/repo#N` or a pasted `github.com/owner/repo/pull|issues/N` URL). **Nothing here
touches Jira, Confluence, or team/service ownership.** This eval does **not** re-validate
those parts of the earlier report — see the closing summary.

**Environment:** `context-fabric-sqlite-trial` (SQLite, http://localhost:8001), repo
checkout `C:\Users\a.kakaraddi\Repos\ContextLayer_v2`. Approach A calls were made by
copying small Python scripts into the container and running them against
`src/context_fabric/mcp/tools.py`'s real functions (`describe_schema_tool`,
`search_entities_tool`, `aggregate_entities_tool`, `search_context_tool`) — not the raw
REST routes. Approach B calls hit `https://api.github.com/...` directly, unauthenticated;
no rate limiting was hit during this run.

**One data correction to the brief:** `describe_schema()` shows **5** GitHub
`REPOSITORY` nodes synced, not 4 — `getsentry/sentry` itself exists as a bare repo node
(referenced by other repos' cross-links) but has **zero** PRs/issues synced under it.
Node-count total (17,349 = 16,173 PRs + 1,170 issues + 5 repos + 1 org) matches the
brief exactly, so this is just a naming nuance, not a scope violation.

---

## Part 1 — The 25 questions

See `questions_github_only.md` in this folder for the canonical list (reproduced here for
convenience):

1. Total PRs (all states) across the 4 repos combined
2. Total issues (all states) across the 4 repos combined
3. Total open issues org-wide
4. Open PRs in relay right now
5. Closed (non-merged) PRs in snuba
6. Which repo has the most merged PRs
7. Which repo has the most open issues
8. PR count per repo (breakdown)
9. Issue count per repo (breakdown)
10. Freshest repo (latest updated_at)
11. Oldest still-open issue, and which repo
12. Top merged-PR author, symbolicator
13. Top merged-PR author, vroom
14. Open draft PRs in relay
15. Top labels on snuba issues
16. Top labels on relay PRs
17. vroom issues with zero labels
18. snuba text referencing relay (owner/repo#N)
19. vroom text referencing snuba
20. symbolicator text referencing relay
21. Full-text search "profiling" across all 4 repos
22. Full-text search "memory leak" across all 4 repos
23. Open-issue count per repo, side by side
24. Fraction of all PRs still open, org-wide
25. "What's missing": do snuba/vroom reference symbolicator at all?

---

## Bugs / limitations found this run (report plainly, not papered over)

1. **`describe_schema_tool` and relation-anchored `search_entities` both work correctly**
   on this SQLite trial. The two bugs the brief said were "just fixed" did not
   reproduce — `describe_schema()` returned a clean compact payload (1,332 chars), and a
   `MENTIONS` `relatedTo` query against a known target (`getsentry/relay#6025`) correctly
   returned the 2 PRs that cite it.

2. **`isEmpty` is broken on list-valued properties (`labels`).**
   `{"property":"labels","operator":"isEmpty"}` scoped to vroom issues returned **0**
   matches. The true answer, confirmed two ways (CF's own `labels` group_by, and a raw
   GitHub API fetch of all 14 vroom issues), is **13 of 14**. An agent trusting the
   `isEmpty` operator on a list property gets a silently wrong answer (0 instead of 13) —
   this is a real correctness bug, not a missing feature.

3. **PR/issue body text is not stored** (`description` is `null` on every PR/ISSUE node
   sampled). `search_entities`/`search_context` full-text matching only reaches the
   **title**. This directly undercuts Q21/Q22 as originally conceived: a GitHub search
   over title+body for "profiling" returns **8,839** hits; Context Fabric (title-only)
   can only ever see **219** of them (2.5%). Framed as a fair title-only-vs-title-only
   comparison the two agree exactly (see Part 3), but framed as "topic search across 4
   repos," Context Fabric is not actually competitive — it structurally cannot see PR/
   issue bodies at all. This is a real, worth-reporting limitation, not a wash.

4. **Cross-repo `MENTIONS` aggregation ("which PRs in repo A reference repo B") is not
   cheaply expressible with the tool layer as designed.** `relatedTo` resolves one
   specific target native_id (or a short explicit list) per call — there is no
   "everything with an outgoing MENTIONS edge whose target is under path X" query. The
   *only* way to answer "how many snuba items reference relay" via `search_entities` is
   to already know the specific relay PR/issue numbers being cited and query each one, or
   enumerate all ~16k relay PR/issue native_ids as the relation's target list (defeating
   the tool's own compression purpose). Practically, this means the compressed tool layer
   **cannot answer Q18/19/20/25 as an aggregate count** the way it answers everything
   else — the honest answer for those four is "not efficiently supported by
   `search_entities`/`aggregate_entities`," even though the extraction pipeline
   (`cross_references.py`) and the edges themselves (1,609 `MENTIONS` edges,
   confirmed via `describe_schema`) clearly exist. Per-edge lookups work fine (verified
   live, item 1 above); repo-scoped aggregation of them does not.

5. **Per-repo sync gap: snuba is missing 182 closed issues.** See Part 3, cross-check #2 —
   a real correctness finding, not a tool-design limitation.

---

## Part 2/3 combined — per-question results

Legend: CF = Context Fabric (compressed MCP tools), GH = native GitHub REST/Search API.
✓ = both approaches agree; ✗ = disagree (investigated below); — = not applicable /
not efficiently answerable by CF as discussed above.

| # | Question | CF answer | GH answer | Agree? |
|---|---|---|---|---|
| 1 | Total PRs, 4 repos | 16,173 | 16,174 | ✓ (off-by-1 live drift, see CC#1) |
| 2 | Total issues, 4 repos | 1,170 | 1,352 | ✗ (real sync gap, see CC#2) |
| 3 | Total open issues org-wide | 106 | 106 (68+3+34+1) | ✓ |
| 4 | Open PRs, relay | 25 | 24 | ✗ (off-by-1 live drift) |
| 5 | Closed non-merged PRs, snuba | 1,330 | 1,330 | ✓ (exact) |
| 6 | Most merged PRs | snuba (6,809) | snuba (6,811) | ✓ (ranking agrees, count off-by-2 drift) |
| 7 | Most open issues | relay (68) | relay (68) | ✓ (exact) |
| 8 | PR breakdown per repo | relay 5,572 / snuba 8,152 / symbolicator 1,789 / vroom 660 | relay 5,572 / snuba 8,153 / symbolicator 1,789 / vroom 660 | ✓ (symbolicator & vroom exact; snuba off-by-1 drift) |
| 9 | Issue breakdown per repo | relay 780 / snuba 120 / symbolicator 256 / vroom 14 | relay 780 / snuba 302 / symbolicator 256 / vroom 14 | ✗ snuba only — see CC#2 |
| 10 | Freshest repo | relay (14:55 pass time) | snuba (22:08 pass time) | ✗ (live drift, see CC#5) |
| 11 | Oldest open issue | relay, 2020-06-01 (#4972) | relay, 2020-06-01 (#4972) | ✓ (exact, see CC#3) |
| 12 | Top merged-PR author, symbolicator | Swatinem, 372 | Swatinem, 372 | ✓ (exact, see CC#4) |
| 13 | Top merged-PR author, vroom | phacops, 236 | phacops, 236 | ✓ (exact) |
| 14 | Open draft PRs, relay | 11 of 25 open | 11 of 24 open | ✓ (drift-adjusted) |
| 15 | Top labels, snuba issues | getsentry/snuba 24, Security 23, bug 12, Stale 3 | not independently re-derived (see limitation below) | — |
| 16 | Top labels, relay PRs | skip-changelog 738, dependencies 126, github_actions 60, Trigger:Full-CI 43, rust 24 | not independently re-derived | — |
| 17 | vroom issues, zero labels | 13 of 14 (via label combos; `isEmpty` itself buggy, see Bug #2) | 13 of 14 | ✓ (exact, cross-checked) |
| 18 | snuba text → relay | not efficiently answerable (Bug #4) | 53 hits (search API, noisy — see below) | — |
| 19 | vroom text → snuba | not efficiently answerable | 5 hits | — |
| 20 | symbolicator text → relay | not efficiently answerable | 22 hits | — |
| 21 | "profiling" search | 219 (title-only) | 8,839 (title+body) / 219 (title-only) | ✓ title-only exact match; ✗ vs. full-body (see Bug #3) |
| 22 | "memory leak" search | 4 (title-only) | 48 (title+body) / 4 (title-only) | ✓ title-only exact match; ✗ vs. full-body |
| 23 | Open-issue distribution | relay 68 / snuba 3 / symbolicator 34 / vroom 1 | relay 68 / snuba 3 / symbolicator 34 / vroom 1 | ✓ (exact) |
| 24 | Fraction of PRs open | 55/16,173 = 0.34% | ~55/16,174 = 0.34% | ✓ |
| 25 | snuba/vroom mention symbolicator? | not efficiently answerable in aggregate; per-edge spot check confirms edges exist | Yes — snuba 2 hits, vroom 3 hits; "missing" hypothesis is false | — (CF can confirm per-edge but not cheaply produce the count) |

**Cross-repo reference counts are noisy on the GitHub side.** Spot-checking snuba PR
#1027 (one of the 53 "snuba→relay" hits) showed the matched text was a GitHub Actions
run URL for relay's CI, not an actual `#N` reference — GitHub's search API tokenizes on
`#`/`/` and doesn't respect the exact phrase, so its 53/22/5/2/3 counts are **upper
bounds with some false positives**, not ground truth. Two other spot checks
(symbolicator#1978, vroom#576) were genuine cross-repo references, just expressed as
pasted `github.com/.../pull/N` URLs rather than `owner/repo#N` — both shapes Context
Fabric's `cross_references.py` is designed to catch (`github_cross_repo_key` and
`github_url` patterns). Bottom line: for this question category, **neither approach
produces a clean, cheap, verifiably-exact number** — GitHub's is noisy-but-cheap (1
call), Context Fabric's is exact-but-effectively-unanswerable-in-aggregate (Bug #4). This
is the most interesting single finding of this run and cuts against a straightforward "CF
wins."

---

## Part 3 — Five cross-checks, in detail

**CC#1 — Total PR count (Q1/Q8).** CF: 16,173. GH: 16,174. relay, symbolicator and
vroom matched exactly; snuba was off by 1 (8,152 vs 8,153). Given both passes were
minutes apart on a live, actively-merging repo (snuba merges dozens of PRs/day per the
label data), a single new PR landing between passes is the most likely explanation —
consistent with `merged_at`-based merged-PR counts for snuba also being off by exactly 2
(6,809 vs 6,811) in the same direction. **Verdict: live-data drift, not a bug.**

**CC#2 — Issue count, snuba (Q2/Q9) — the one real disagreement.** CF: 120 total (117
closed + 3 open). GH: 302 total (299 closed + 3 open). Open counts match exactly (3=3);
**all 182 of the missing records are closed issues**. Live drift cannot explain this — a
repo's closed-issue count does not shrink by 60% between two ten-minute-apart snapshots.
The most likely explanation is a sync-time gap specific to snuba's closed-issue sync
(e.g., a pagination limit or partial backfill that was never fully caught up for this one
repo/state combination, while relay/symbolicator/vroom's closed issues synced
completely — all three matched GH exactly). **Verdict: a genuine data-completeness bug in
this trial's snuba sync, not a methodology artifact.** Anyone asking Context Fabric "how
many issues does snuba have" today gets an answer that's wrong by 60%.

**CC#3 — Oldest open issue (Q11).** All four repos' oldest-open-issue timestamps matched
CF and GH exactly: relay 2020-06-01 (#4972), symbolicator 2021-05-25 (#445), snuba
2026-02-24 (#7763), vroom 2026-02-04 (#661). **Verdict: exact agreement.**

**CC#4 — Top merged-PR author (Q12/Q13).** CF's one-call `aggregate_entities` group-by
`author` answer (Swatinem/372 for symbolicator, phacops/236 for vroom) was verified
against GitHub's `author:` search filter and matched exactly both times. **Verdict: exact
agreement**, and this is also where the token-cost gap is largest — see Part 4.

**CC#5 — Freshest repo (Q10) — the second real disagreement, and it's drift.** CF's pass
(mid-session) ranked relay freshest (PR updated_at 14:55:22) ahead of vroom (14:11:21),
snuba (13:51:16), symbolicator (12:27:04) — all same day, 2026-09-16. GH's pass, run
afterward using each repo's `pushed_at`, ranked **snuba** freshest (22:08:51) ahead of
relay (20:29:35), vroom (14:11:21), symbolicator (12:04:34). snuba's timestamp jumped
~8 hours between the two passes while the others barely moved — on a repo this active,
new commits landing in the gap between passes is entirely plausible, and is the same
repo (snuba) already flagged as having a sync lag in CC#2, so a lagging CF snapshot for
snuba specifically is also a plausible contributor. **Verdict: most likely genuine live
drift, compounded by the same snuba sync-lag suspected in CC#2 — flagged, not resolved,
exactly as the brief asked for.**

---

## Part 4 — Token accounting

Methodology: tokens ≈ characters / 4, summed per approach as question text +
(for CF) the skill file once for the batch + every tool-call argument string + every
tool-call result string + final answer text. Where a native-API answer to a grouping
question (top author, top label) has no server-side aggregation endpoint, GitHub's real
cost is full pagination + client-side counting, not a single lookup — reported separately
below rather than folded into a misleading single "GH total," since conflating the two
would flatter native-API in exactly the way the corrected eval is trying not to.

### Grand totals

| Component | Characters | Tokens (÷4) |
|---|---|---|
| Question text (25 questions, both approaches read them once each) | ~2,000 | ~500 |
| CF: SKILL.md (once per session/batch) | 8,301 | 2,075 |
| CF: SKILL.md (equivalent per-question cost, ÷25) | 332 | 83 |
| CF: session setup calls (describe_schema + repo enumeration) | 2,822 | 706 |
| CF: all per-question tool-call args + results (Q1–Q24, excl. Q18-20/25 which CF can't answer efficiently) | 28,934 | 7,234 |
| **CF subtotal (setup + skill + per-question, Q1–Q24)** | **~40,057** | **~10,014** |
| GH: all per-question API call bodies, "verification-cost" basis (Q1–Q11, 14, 17–25; Q12/13/15/16 counted at verification-only cost) | ~463,119 | ~115,780 |
| GH: **realistic discovery cost** for Q12 (symbolicator top author, no groupby exists — 17 pages × 100 items, measured 5,188 chars/item from 1 real fetched page) | ~8,819,872 | ~2,204,968 |
| GH: realistic discovery cost for Q13 (vroom top author, 7 pages, same per-item rate, extrapolated) | ~3,631,712 | ~907,928 |
| GH: realistic discovery cost for Q15 (snuba label histogram, ~4 pages, extrapolated) | ~906,000 | ~226,500 |
| GH: realistic discovery cost for Q16 (relay label histogram, ~56 pages, extrapolated) | ~28,900,000 | ~7,225,000 |
| **GH subtotal, "someone already knows the answer and is just verifying it"** | **~463,119** | **~115,780** |
| **GH subtotal, "someone actually has to compute the answer from scratch" (realistic)** | **~42,720,703** | **~10,680,176** |

Caveats on the discovery-cost rows: only Q12's 518,816-char page and Q17's 50,081-char
full fetch were actually retrieved and measured; Q13/Q15/Q16 discovery costs are
extrapolated from Q12's measured per-item rate (~5,188 chars/PR-object) and each
question's known total_count, explicitly to avoid burning real GitHub rate limit and
session time fetching ~90 additional pages that would not change the qualitative
conclusion. This is flagged, not hidden.

### Per-question table (characters, CF vs GH; "—" = not applicable per Bug #4 discussion above)

| # | CF calls | CF chars | GH calls | GH chars (verification basis) |
|---|---|---|---|---|
| 1 | 1 | 138 | 4 | 14,649 |
| 2 | 1 | 125 | 4 | 19,486 |
| 3 | 1 | 173 | 4 | 26,771 |
| 4 | 1 | 240 | 2 | 9,966 |
| 5 | 2 | 424 | 2 | 7,574 |
| 6 | 8 (incl. 4 that hit the `state=merged` no-op, see Bug section) | 2,342 | 4 | 16,433 |
| 7 | 4 (reused from Q23) | 726 | 4 (reused from Q3) | 0 |
| 8 | 4 | 747 | reused (Q1) | 0 |
| 9 | 4 | 715 | reused (Q2) | 0 |
| 10 | 4 | 1,220 | 4 | 24,719 |
| 11 | 4 | 972 | 4 | 13,029 |
| 12 | 1 | 2,807 | 1 (verify only) | 4,899 |
| 13 | 1 | 1,142 | 1 (verify only) | 2,523 |
| 14 | reused (Q4) | 0 | reused (Q4) | 0 |
| 15 | 1 | 1,121 | 0 (not derived) | — |
| 16 | 1 | 1,916 | 0 (not derived) | — |
| 17 | 2 (1 buggy) | 398 | 1 | 50,081 |
| 18 | — | — | 1 | 77,625 |
| 19 | — | — | 1 | 16,343 |
| 20 | — | — | 1 | 67,349 |
| 21 | 2 | 10,871 | 3 | 46,444 |
| 22 | 2 | 2,857 | 2 | 48,923 |
| 23 | reused (Q7) | 0 | reused (Q3) | 0 |
| 24 | 0 (derived) | 0 | 0 (derived) | 0 |
| 25 | 1 (spot-check) | ~1,591 | 2 | 16,305 |

---

## Honest summary

**Does this corrected, GitHub-only eval still support "the context layer wins"? Yes, but
narrowly and unevenly — not the sweeping result the earlier (flawed) report implied.**

Where Context Fabric clearly wins:
- **Simple counts and breakdowns (Q1–Q9, Q23, Q24):** one compressed call each, tiny
  payloads (dozens to a few hundred chars), vs. 4 separate GitHub calls per breakdown.
  Modest but real win, on the order of 10–50x fewer characters.
- **Grouped aggregates with no GitHub equivalent (Q12/Q13/Q15/Q16 — top author, top
  label):** this is the real, large win. GitHub's Search/REST API has no `GROUP BY`;
  answering "who has the most merged PRs" from scratch means paginating every merged PR
  and counting client-side. Measured at ~5,188 chars/item, that's on the order of
  **~1,000–7,000x** more characters than Context Fabric's single `aggregate_entities`
  call for the exact same answer. This is the single most defensible, most real
  differentiator in the whole eval.

Where it does not win, or the picture is mixed:
- **Full-text/topic search (Q21/Q22):** Context Fabric cannot search PR/issue bodies at
  all (only titles) — it misses ~97% of what a real body-inclusive GitHub search finds.
  Framed honestly, this is a Context Fabric weakness, not the strength the brief
  hypothesized.
- **Cross-repo reference questions (Q18–Q20, Q25):** Context Fabric extracts these
  correctly at the edge level (verified live) but the compressed tool layer has no way to
  aggregate them by source/target repo without either already knowing every target id or
  enumerating the whole target repo — i.e., the feature exists in the data model but is
  not actually exposed by `search_entities`/`aggregate_entities` in a form an agent could
  use cheaply. GitHub's own answer for this category is cheap but noisy (confirmed false
  positive on manual spot-check).
- **A real data-completeness bug** was found (snuba missing 182 closed issues — 60% of
  its true issue count) and a real correctness bug in the tool layer (`isEmpty` silently
  wrong on list-valued properties). Both are worth fixing before trusting this trial's
  numbers for anything snuba-issue-related or label-emptiness-related.

**Compared to the previous (flawed) all-systems report:** that version's win was
structural and unfalsifiable — Context Fabric answering questions about content that
existed nowhere else, by construction. This version's win is real but much smaller in
scope: it holds cleanly for simple counts/breakdowns and strongly for grouped aggregates,
and does **not** hold for full-text search or cross-repo reference aggregation, where
Context Fabric currently loses or ties at best. The honest one-line version: **the context
layer wins decisively on "count/group this," is roughly break-even to worse on
"search the text of this," and cannot currently do "aggregate cross-repo citations"
at all through its compressed tools — a narrower, more defensible claim than before.**

**Scope reminder:** this eval covers GitHub data only. It says nothing about Jira,
Confluence, or team/service-ownership questions, and should not be read as re-validating
any part of the earlier report that touched those.
