"""Azure DevOps payload -> domain/ type mapping.

The only module in connectors/azure_devops/ allowed to know ADO's REST
API JSON shape (docs/CONNECTORS.md "Adding a new connector"). Every
function here takes a raw ADO-shaped dict and returns a domain/ type;
nothing downstream of fixture.py/live.py ever sees these raw shapes.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from context_fabric.connectors.ai_assets import (
    AI_ASSET_PATH_RULES as AI_ASSET_PATH_RULES,
)
from context_fabric.connectors.ai_assets import (
    ai_asset_native_id as ai_asset_native_id,
)
from context_fabric.connectors.ai_assets import (
    classify_ai_asset_path as classify_ai_asset_path,
)
from context_fabric.connectors.ai_assets import (
    map_ai_asset as map_ai_asset,
)
from context_fabric.connectors.ai_assets import (
    parse_ai_asset_description as parse_ai_asset_description,
)
from context_fabric.connectors.ai_assets import (
    parse_ai_asset_ref as parse_ai_asset_ref,
)
from context_fabric.connectors.cross_references import extract_cross_references
from context_fabric.domain.connector_types import (
    ACLReference,
    SourceContainer,
    SourceContent,
    SourceLink,
    SourceObject,
)

WORK_ITEM_TYPE_TO_KIND = {
    "Epic": "EPIC",
    "Feature": "FEATURE",
    "User Story": "STORY",  # Agile process template's story-level type
    "Product Backlog Item": "STORY",  # Scrum process template's — same
    # concept, different name; this project's real work items are on
    # the Scrum template (confirmed by checking the real distribution:
    # 104 "Product Backlog Item", 0 "User Story"), which "User Story"
    # alone silently missed, bucketing all 104 into generic WORK_ITEM.
    "Task": "TASK",
    "Bug": "BUG",
    "Test Case": "TEST_CASE",
    "Test Suite": "TEST_SUITE",
    "Test Plan": "TEST_PLAN",
}

# ADO's PR artifact link shape is
# "PullRequestId/{projectId}%2F{repositoryId}%2F{pullRequestId}" — both
# projectId and repositoryId are GUIDs, so a non-greedy match up to the
# first "%2F" (as this used to be) grabs the leading digits of the
# repositoryId GUID instead of the real PR id at the end. `.*` is greedy
# and backtracks from the end, so it lands on the *last* "%2F<digits>"
# in the URL regardless of how many GUID segments precede it.
_PR_ARTIFACT_LINK_PATTERN = re.compile(r"PullRequestId/.*%2F(\d+)$")

# ADO's own structured work-item-to-work-item relation types — real,
# human-curated cross-references distinct from both System.Parent
# (hierarchy, already read by map_work_item) and free-text AB# mentions.
# Previously never extracted at all despite being exactly the kind of
# "native application-provided connection" that's more reliable than
# regex-scanning description text. Maps a relation's `rel` value to the
# SourceLink link_kind it should become.
_WORK_ITEM_RELATION_LINK_KIND: dict[str, str] = {
    "System.LinkTypes.Related": "relates_to",
    "Microsoft.VSTS.Common.TestedBy-Forward": "verifies",
    "System.LinkTypes.Dependency-Forward": "depends_on",
    # -Reverse variants deliberately excluded — a real bug found via a
    # user report: ADO auto-creates the reciprocal relation on the other
    # work item (A's Dependency-Forward to B implies B's
    # Dependency-Reverse back to A), and since get_links() is called
    # independently per work item during sync, extracting both directions
    # produced two separate, mutually-contradictory PROPOSED edges
    # (A depends_on B *and* B depends_on A) for what is really one
    # relationship. Only the Forward side is extracted now — same
    # precedent as System.LinkTypes.Hierarchy-Forward/Reverse below,
    # which was already excluded for the identical reason. Known
    # simplification: this assumes Forward is emitted from at least one
    # side of every such relation, which holds for every case checked
    # this session — if a relation is ever missed because its only
    # entry point was Reverse, that's the tradeoff of avoiding the
    # duplicate over recovering that one edge.
    # System.LinkTypes.Hierarchy-Forward/Reverse deliberately excluded —
    # that's the same parent/child relationship System.Parent already
    # gives map_work_item structurally (CONTAINS, via parent_native_id);
    # extracting it again here would just duplicate that edge under a
    # different type.
}
_WORK_ITEM_RELATION_URL_PATTERN = re.compile(r"/workItems/(\d+)$")

# Relation types whose natural reading runs *towards* the work item being
# processed, not away from it. "Tested By" sits on the work item and names
# the test case — meaning "that test case verifies this work item". Emitted
# forward it produced 93 edges reading STORY --VERIFIES--> TEST_CASE, every
# one backwards (a test case verifies a story, never the reverse). The
# SourceLink carries reverse=True and link_extraction.py swaps the
# endpoints; the alternative would be a VERIFIED_BY edge type, which just
# moves the same inversion into the vocabulary.
_REVERSED_RELATION_TYPES = {"Microsoft.VSTS.Common.TestedBy-Forward"}

# Human-readable label for each structured relation type, shown to a
# reviewer in the Proposed Links queue as the evidence for *why* an edge
# was proposed (docs/UI.md "Proposed links review queue") — a real ADO
# field name a reviewer can go verify in ADO itself, not a text snippet
# (there is none; this isn't text-mined).
_RELATION_TYPE_LABEL: dict[str, str] = {
    "System.LinkTypes.Related": "Related",
    "Microsoft.VSTS.Common.TestedBy-Forward": "Tested By",
    "System.LinkTypes.Dependency-Forward": "Dependency (Successor)",
}


def _display_name(identity: Any) -> str | None:
    """A person field as one queryable string.

    ADO returns a full identity object for System.AssignedTo/CreatedBy —
    id, url, _links, avatar hrefs — which this connector used to store
    whole. That is unqueryable (`attributes->>'assigned_to'` yields a JSON
    blob, so "assigned to X" can't be expressed as a filter) and carries
    avatar/link noise nothing reads. The display name is what a human
    filters on; the identity id stays reachable via the vendor on demand.
    """
    if isinstance(identity, dict):
        return identity.get("displayName") or identity.get("uniqueName") or None
    return str(identity) if identity else None


def _split_tags(tags: Any) -> list[str]:
    """ADO serializes System.Tags as "a; b; c" — a list is what the
    `containsAny` array operator can actually filter on."""
    if not tags:
        return []
    return [t.strip() for t in str(tags).split(";") if t.strip()]


def _content_hash(raw: dict[str, Any]) -> str:
    payload = json.dumps(raw.get("fields", raw), sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def map_project(raw: dict[str, Any]) -> SourceContainer:
    return SourceContainer(
        id=raw["id"],
        name=raw["name"],
        kind="PROJECT",
        parent_id=None,
        native_id=raw["id"],
        attributes={"url": raw.get("url", "")},
        description=(raw.get("description") or "")[:512] or None,
    )


def map_area_path(raw: dict[str, Any]) -> SourceObject:
    return SourceObject(
        native_id=raw["id"],
        kind="AREA_PATH",
        name=raw["name"],
        parent_native_id=raw["project"],
        attributes={"path": raw["path"], "url": raw.get("url", "")},
        content_hash=_content_hash(raw),
    )


def map_work_item(raw: dict[str, Any]) -> SourceObject:
    fields = raw["fields"]
    work_item_type = fields["System.WorkItemType"]
    kind = WORK_ITEM_TYPE_TO_KIND.get(work_item_type, "WORK_ITEM")

    if "System.Parent" in fields:
        parent_native_id = str(fields["System.Parent"])
    else:
        # No explicit work-item parent (common for any type, not just
        # Epics — plenty of real ADO projects don't enforce a strict
        # Epic->Feature->Story chain) — falls back to its area path, the
        # top of the ADO native hierarchy (docs/CONNECTORS.md). Without
        # this, an unparented work item has no parent_native_id any
        # list_children call will ever return it under, so sync (which
        # only discovers by walking parent->child) never finds it.
        parent_native_id = fields.get("System.AreaPath")

    return SourceObject(
        native_id=str(raw["id"]),
        kind=kind,
        name=fields["System.Title"],
        parent_native_id=parent_native_id,
        attributes={
            "state": fields.get("System.State"),
            "area_path": fields.get("System.AreaPath"),
            "assigned_to": _display_name(fields.get("System.AssignedTo")),
            "url": raw.get("url", ""),
            # Vendor timestamps and the fields a real question filters on.
            # These already arrive in the payload we fetch — the work-item
            # batch call uses $expand=relations, which returns every field
            # as a superset (live.py's own note) — so keeping them costs no
            # extra API call. Without created_at/updated_at nothing about
            # age, staleness or cycle time is answerable: measured coverage
            # of any timestamp on STORY/TASK/BUG was 0%.
            "created_at": fields.get("System.CreatedDate"),
            "updated_at": fields.get("System.ChangedDate"),
            "created_by": _display_name(fields.get("System.CreatedBy")),
            "priority": fields.get("Microsoft.VSTS.Common.Priority"),
            "iteration_path": fields.get("System.IterationPath"),
            "tags": _split_tags(fields.get("System.Tags")),
            # Deliberately not "description" — System.Description is raw
            # HTML and can be large; ADR-003 fetches full content
            # on-demand via get_content()/map_content() rather than
            # eagerly duplicating it into every synced node's attributes.
        },
        source_version=str(raw.get("rev", "")),
        content_hash=_content_hash(raw),
        deleted=False,
    )


def map_tombstone(native_id: str, kind: str) -> SourceObject:
    """A deleted work item reported by get_changes — no body, just the
    identity and the deletion flag (docs/CONNECTORS.md "Tombstone
    handling")."""
    return SourceObject(native_id=native_id, kind=kind, name="", deleted=True)


def map_pull_request(raw: dict[str, Any]) -> SourceObject:
    return SourceObject(
        native_id=f"PR-{raw['pullRequestId']}",
        kind="PULL_REQUEST",
        name=raw["title"],
        parent_native_id=raw["repository"]["id"],
        attributes={
            "status": raw.get("status"),
            "source_ref": raw.get("sourceRefName"),
            "target_ref": raw.get("targetRefName"),
            "url": raw.get("url", ""),
            # Already present in the PR list payload — no extra call. Cycle
            # time, stale-PR and throughput questions are all unanswerable
            # without these: timestamp coverage on PULL_REQUEST was 0/138.
            "created_at": raw.get("creationDate"),
            "closed_at": raw.get("closedDate"),
            "created_by": _display_name(raw.get("createdBy")),
            "is_draft": raw.get("isDraft"),
            "merge_status": raw.get("mergeStatus"),
        },
        # ADO's own PR list API already truncates this server-side (every
        # real value observed caps at exactly 400 chars) — a genuine
        # bounded preview, not an eager full-body copy, so this doesn't
        # need an on-demand get_content path the way GitHub's did.
        description=(raw.get("description") or "")[:512] or None,
        content_hash=_content_hash(raw),
    )


def map_pull_request_links(raw: dict[str, Any]) -> list[SourceLink]:
    """Cross-references out of an ADO pull request's own title, branch
    name, and description — previously not scanned at all (get_links only
    handled work items and builds; a PR native_id fell straight through to
    "return []"). A real gap: this org's own real data has ticket keys in
    PR branch names ("feature/AB-44", "refs/heads/design/WI-616") at least
    as often as in titles, and description is where a "Fixes AB#59" style
    reference would sit for anyone following that convention."""
    native_id = f"PR-{raw['pullRequestId']}"
    return (
        extract_cross_references(
            native_id, raw.get("title") or "", location="title",
            skip_ref=lambda ref: ref == native_id,
        )
        + extract_cross_references(
            native_id, raw.get("sourceRefName") or "", location="branch",
            skip_ref=lambda ref: ref == native_id,
        )
        + extract_cross_references(
            native_id, raw.get("description") or "", location="description",
            skip_ref=lambda ref: ref == native_id,
        )
    )


def map_git_repository(raw: dict[str, Any]) -> SourceObject:
    """ADO's own Git repos — a separate object from work items, listed
    only as a lightweight container (no branch/tree/blob crawl) so Pull
    Requests have somewhere to attach; kept deliberately shallow since
    the raw file/code content isn't a modeled entity type here."""
    return SourceObject(
        native_id=raw["id"],
        kind="GIT_REPOSITORY",
        name=raw["name"],
        parent_native_id=raw["project"],
        attributes={
            "default_branch": raw.get("defaultBranch", ""),
            "url": raw.get("url", ""),
        },
        content_hash=_content_hash(raw),
    )


def map_wiki_page(raw: dict[str, Any]) -> SourceObject:
    """One page of an ADO project wiki. native_id is
    "<wikiId>:<path>" — path is the wiki's own slash-separated page
    path (e.g. "/Home/Onboarding"), unrelated to the repo/file hierarchy."""
    path = raw["path"]
    parent_path = path.rsplit("/", 1)[0] or "/"
    parent_native_id = raw["wiki_id"] if path == "/" else f"{raw['wiki_id']}:{parent_path}"
    name = path.rsplit("/", 1)[-1] or path
    return SourceObject(
        native_id=f"{raw['wiki_id']}:{path}",
        kind="WIKI_PAGE",
        name=name,
        parent_native_id=parent_native_id,
        attributes={"path": path, "url": raw.get("url", "")},
        content_hash=_content_hash(raw),
    )


def map_wiki_page_content(native_id: str, raw: dict[str, Any]) -> SourceContent:
    return SourceContent(
        native_id=native_id,
        mime_type="text/markdown",
        text=raw.get("content", ""),
        uri=raw.get("url", ""),
    )


def map_build(raw: dict[str, Any]) -> SourceObject:
    """A Build *is* a Pipeline Run — Azure DevOps exposes the same
    underlying record through two API surfaces (classic Build API,
    newer Pipelines Runs API); this connector only fetches the Build
    API (richer: carries repository + triggerInfo the Runs API lacks)
    and parents it directly under the PIPELINE node (Pipelines API),
    since `build.definition.id` and a Pipeline's `id` are the same
    underlying object too. Previously this connector also called the
    Pipelines Runs API and synthesized a separate BUILD_DEFINITION
    container — a real duplication bug (confirmed: every synced
    BUILD_DEFINITION/PIPELINE_RUN id exactly matched an existing
    PIPELINE/BUILD id) found via a user report and fixed here."""
    return SourceObject(
        native_id=f"BUILD-{raw['id']}",
        kind="BUILD",
        name=f"{raw['definition']['name']} #{raw['buildNumber']}",
        parent_native_id=f"PIPELINE-{raw['definition']['id']}",
        attributes={
            "status": raw.get("status"),
            "result": raw.get("result"),
            "source_branch": raw.get("sourceBranch"),
            "started_at": raw.get("startTime"),
            "finished_at": raw.get("finishTime"),
            "repository_id": (raw.get("repository") or {}).get("id"),
            "repository_type": (raw.get("repository") or {}).get("type"),
            "commit": raw.get("sourceVersion"),
            "reason": raw.get("reason"),
            "url": raw.get("url", ""),
        },
        content_hash=_content_hash(raw),
    )


def map_build_links(raw: dict[str, Any]) -> list[SourceLink]:
    """A Build's real relationships beyond its structural pipeline
    parent: the repo it built (`repository.id`, ADO's own repo GUID —
    a direct, reliable match, not a text-mined guess) and, when the
    build was triggered by a pull request, that PR (`triggerInfo`'s
    "pr.number" — ADO's own structured trigger metadata, not inferred).
    """
    native_id = f"BUILD-{raw['id']}"
    links: list[SourceLink] = []
    repo_id = (raw.get("repository") or {}).get("id")
    if repo_id:
        links.append(
            SourceLink(
                from_native_id=native_id,
                target_ref=f"REPO-{repo_id}",
                link_kind="relates_to",
                evidence="This build's own `repository.id` field, reported by Azure DevOps.",
                confidence=1.0,
            )
        )
    pr_number = (raw.get("triggerInfo") or {}).get("pr.number")
    if pr_number:
        links.append(
            SourceLink(
                from_native_id=native_id,
                target_ref=f"PR-{pr_number}",
                link_kind="relates_to",
                evidence=(
                    f"This build's own `triggerInfo` field says it was triggered by PR #{pr_number}."
                ),
                confidence=1.0,
            )
        )
    return links


def map_pipeline(raw: dict[str, Any], *, project: str) -> SourceObject:
    return SourceObject(
        native_id=f"PIPELINE-{raw['id']}",
        kind="PIPELINE",
        name=raw["name"],
        parent_native_id=project,
        attributes={"folder": raw.get("folder", ""), "url": raw.get("url", "")},
    )


def map_environment(raw: dict[str, Any], *, project: str) -> SourceObject:
    return SourceObject(
        native_id=f"ENVIRONMENT-{raw['id']}",
        kind="ENVIRONMENT",
        name=raw["name"],
        parent_native_id=project,
        attributes={"description": raw.get("description", "")},
    )


def map_test_run(raw: dict[str, Any], *, project: str) -> SourceObject:
    """Aggregate outcome + pass/fail counts only — never individual test
    case results/traces (ADR-003: status metadata, not a data replica)."""
    return SourceObject(
        native_id=f"TESTRUN-{raw['id']}",
        kind="TEST_RUN",
        name=raw.get("name") or f"Test Run #{raw['id']}",
        parent_native_id=project,
        attributes={
            "state": raw.get("state"),
            "outcome": "passed" if raw.get("passedTests") == raw.get("totalTests") else "failed",
            "total_tests": raw.get("totalTests"),
            "passed_tests": raw.get("passedTests"),
            "started_at": raw.get("startedDate"),
            "completed_at": raw.get("completedDate"),
            "url": raw.get("url", ""),
        },
    )


def map_content(native_id: str, raw_work_item: dict[str, Any]) -> SourceContent:
    fields = raw_work_item["fields"]
    return SourceContent(
        native_id=native_id,
        version=str(raw_work_item.get("rev", "")),
        mime_type="text/html",
        text=fields.get("System.Description", ""),
        uri=raw_work_item.get("url", ""),
    )


def map_links(raw_work_item: dict[str, Any]) -> list[SourceLink]:
    links: list[SourceLink] = []
    native_id = str(raw_work_item["id"])

    for relation in raw_work_item.get("relations", []):
        rel_type = relation.get("rel", "")
        url = relation.get("url", "")

        pr_match = _PR_ARTIFACT_LINK_PATTERN.search(url)
        if pr_match:
            links.append(
                SourceLink(
                    from_native_id=native_id,
                    target_ref=f"PR-{pr_match.group(1)}",
                    link_kind="relates_to",
                    evidence="Azure DevOps pull request artifact link on this work item.",
                    confidence=1.0,
                )
            )
            continue

        link_kind = _WORK_ITEM_RELATION_LINK_KIND.get(rel_type)
        if link_kind is not None:
            wi_match = _WORK_ITEM_RELATION_URL_PATTERN.search(url)
            if wi_match:
                target_id = wi_match.group(1)
                if rel_type == "System.LinkTypes.Related" and int(native_id) > int(target_id):
                    # Related is symmetric in ADO (no Forward/Reverse
                    # variant — it appears identically on both work
                    # items' relation lists), so extracting it from both
                    # sides independently would produce two edges for one
                    # real relationship (A->B and B->A) — a real bug
                    # found via a user report, same root cause as the
                    # Dependency/TestedBy fix above but needing a
                    # different fix since there's no Reverse variant to
                    # just exclude. A canonical-direction rule (only the
                    # numerically-lower id emits the edge) keeps exactly
                    # one edge per pair regardless of which side is
                    # processed first.
                    continue
                label = _RELATION_TYPE_LABEL.get(rel_type, rel_type)
                links.append(
                    SourceLink(
                        from_native_id=native_id,
                        target_ref=f"AB#{target_id}",
                        link_kind=link_kind,  # type: ignore[arg-type]
                        evidence=(
                            f"Azure DevOps's own '{label}' relation field on work item "
                            f"{native_id} — set directly in ADO, not text-mined."
                        ),
                        confidence=1.0,
                        reverse=rel_type in _REVERSED_RELATION_TYPES,
                    )
                )

    # Title is scanned separately from description, and before it: a work
    # item id or repo reference in the *title* is a much stronger claim
    # than the same token buried in a body, and drives a stronger edge
    # type (connectors/cross_references.py's LINK_KIND_BY_LOCATION).
    title = raw_work_item["fields"].get("System.Title", "")
    links += extract_cross_references(
        native_id,
        title,
        location="title",
        where_label="work item title",
        skip_ref=lambda ref: ref == f"AB#{native_id}",
    )
    description = raw_work_item["fields"].get("System.Description", "")
    links += extract_cross_references(
        native_id,
        description,
        location="description",
        where_label="work item description",
        skip_ref=lambda ref: ref == f"AB#{native_id}",
    )

    return links


def map_acl(raw: dict[str, Any]) -> ACLReference:
    return ACLReference(native_id=raw["native_id"], acl_ref=raw["acl_ref"])
