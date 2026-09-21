# Context Fabric Eval — 25 Questions

1. How many pull requests exist in each of the 4 getsentry repos (relay, snuba, symbolicator, vroom)?
2. How many open vs. merged/closed PRs are there per repo?
3. How many issues exist per repo, broken down by state (open/closed)?
4. Which of the 4 repos currently has the most open issues?
5. Who owns the Snuba service — which team, and which repo is it bound to?
6. List all 4 services and their owning teams (the business/org tree).
7. Which Jira tickets exist in project OBS, and what are their types (Epic/Story/Task/Bug) and states?
8. Given ticket ref "OBS-3", what repo/team/product does it resolve to?
9. Which Confluence pages exist in the OBS space, and what kind of doc is each (ADR/PRD/postmortem/meeting notes)?
10. Which Jira tickets have a structured link (IMPLEMENTS) to a real GitHub PR, and which PRs specifically?
11. Is there a PRD with no matching ADR (or vice versa) among the OBS Confluence pages — any documentation coverage gap?
12. Which of the 4 repos had a PR merged/updated most recently (freshest activity)?
13. Which of the 4 repos has gone the longest without any updated PR (staleness)?
14. What is the total node count synced into Context Fabric across all 4 vendors combined?
15. Count of Jira OBS tickets broken down by issue kind (Epic/Story/Task/Bug).
16. Which OBS Jira tickets have NO linked GitHub PR (an IMPLEMENTS edge) — i.e., traceability gaps?
17. What is the business context (owning team/service) for GitHub PR "getsentry/symbolicator#..." (resolved via resolve_scope on a real PR ref)?
18. Which ContextSpace/ team is each of the 4 GitHub repos bound to, and what capability does the binding grant?
19. What is the combined count of currently-open PRs across all 4 repos (single global number)?
20. Which repo (relay/snuba/symbolicator/vroom) has the largest total PR volume (most PRs ever opened)?
21. What incident does the Confluence postmortem page describe, and which GitHub PR(s) does it reference/link to?
22. Search across all systems (GitHub + Jira + Confluence) for the topic "PII scrubbing" — what turns up?
23. Do any of the 4 repos declare AI agent/skill assets (`.claude/skills/`, `.github/agents/`, etc.) that Context Fabric has scanned?
24. Which Jira ticket was most recently updated, and is there related GitHub activity around the same time?
25. Across the whole catalog, what are the different relation (edge) types present and how many of each — is there any cross-tool edge type at all, contradicting a "no links yet" assumption?
