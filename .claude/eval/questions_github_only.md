# GitHub-only eval questions (real, verifiable data)

Scope: getsentry/relay, getsentry/snuba, getsentry/symbolicator, getsentry/vroom.
All questions answerable from real GitHub facts (PRs, issues, labels, authors,
states, timestamps, and real in-text cross-repo references). No Jira,
Confluence, or team/service-ownership questions.

1. How many pull requests (all states) exist in total across the 4 repos combined?
2. How many issues (all states) exist in total across the 4 repos combined?
3. How many open issues exist org-wide across the 4 repos combined?
4. How many open pull requests does relay have right now?
5. How many closed (non-merged or merged) pull requests does snuba have?
6. Of the 4 repos, which has the most merged pull requests?
7. Of the 4 repos, which has the most open issues right now?
8. Give the pull-request count broken down per repo (all 4).
9. Give the issue count broken down per repo (all 4).
10. Which of the 4 repos has the most recent update (latest updated_at across its PRs+issues)?
11. Which of the 4 repos has the oldest still-open issue, and how old is it?
12. Who has the most merged pull requests in symbolicator?
13. Who has the most merged pull requests in vroom?
14. How many currently-open PRs in relay are draft PRs?
15. What are the top 5 most-used labels on issues in snuba?
16. What are the top 5 most-used labels on pull requests in relay?
17. How many issues in vroom have zero labels?
18. Which pull requests/issues in snuba's text reference relay (owner/repo#N style), and how many are there?
19. Which pull requests/issues in vroom's text reference snuba, and how many are there?
20. Which pull requests/issues in symbolicator's text reference relay, and how many are there?
21. Full-text search for "profiling" across all 4 repos at once — how many matches, broken down by repo?
22. Full-text search for "memory leak" across all 4 repos at once — how many matches, broken down by repo?
23. Give the open-issue count for each of the 4 repos side by side (org-wide open-issue distribution).
24. Across all 4 repos combined, what fraction of pull requests are still open (vs. merged/closed)?
25. "What's missing" check: do snuba or vroom contain any issue/PR text that references symbolicator (owner/repo#N), or is cross-repo mention of symbolicator entirely absent from those two repos?
