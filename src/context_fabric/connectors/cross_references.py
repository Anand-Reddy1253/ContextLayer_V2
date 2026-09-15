"""The one place every cross-system reference pattern lives.

Before this module each connector's mapper.py defined its own copy of the
"find an AB#123 / PROJ-45 / owner/repo#7 in some text" patterns. That
duplication is why the coverage matrix had holes nobody could see: the
Azure DevOps mapper — 81% of the real graph — carried only an AB# pattern
(which resolves back to Azure DevOps itself) and a Jira key, so it was
structurally incapable of emitting a link to GitHub or Confluence, and
nothing anywhere could emit a link *to* a Confluence page. Neither gap is
visible when the patterns live 200 lines apart in five files; both are
obvious in one table.

Every pattern here produces a `target_ref` string in exactly the shape
synchronization/link_extraction.py's LINK_PATTERNS already resolves, so
adding a reference kind here is all it takes for every connector to be
able to emit it.

Two reference shapes are supported deliberately:

* **Key shapes** (`AB#412`, `PROJ-45`, `owner/repo#7`) — the conventions
  people type inline.
* **URL shapes** — what people actually paste most of the time. These are
  parsed back to an id rather than matched against a stored URL, because
  the URL a connector stores is often not the one a human would paste
  (confirmed against real data: this project's Azure DevOps pull requests
  store an `_apis/git/repositories/...` API URL, and Confluence
  attachments store a site-relative path — neither would ever match
  pasted browser links).
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from re import Match

from context_fabric.domain.connector_types import LinkKind, SourceLink


def snippet(text: str, match_start: int, match_end: int, *, radius: int = 80) -> str:
    """The window of text around a match, shown to a reviewer as evidence
    for why an edge was proposed."""
    start = max(0, match_start - radius)
    end = min(len(text), match_end + radius)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(text) else ""
    return f"{prefix}{text[start:end].strip()}{suffix}"


@dataclass(frozen=True)
class ReferencePattern:
    """One recognizable way to refer to an object in another system."""

    name: str
    pattern: re.Pattern[str]
    # Builds the target_ref that link_extraction.LINK_PATTERNS resolves.
    # Returns None when the match can't be turned into a reference on its
    # own (e.g. a same-repo "#7" with no repo to qualify it).
    build_ref: Callable[[Match[str], str | None], str | None]
    describes: str


def _ado_ref(m: Match[str], _repo: str | None) -> str:
    return f"AB#{m.group(1)}"


def _confluence_ref(m: Match[str], _repo: str | None) -> str:
    return f"CONFPAGE-{m.group(1)}"


def _github_qualified_ref(m: Match[str], _repo: str | None) -> str:
    return f"{m.group(1)}#{m.group(2)}"


def _github_same_repo_ref(m: Match[str], repo_full_name: str | None) -> str | None:
    # "#7" means nothing without a repo to resolve it against.
    return f"{repo_full_name}#{m.group(1)}" if repo_full_name else None


def _jira_ref(m: Match[str], _repo: str | None) -> str:
    return m.group(1)


def _ado_pr_ref(m: Match[str], _repo: str | None) -> str:
    return f"PR-{m.group(1)}"


# The complete matrix. Order matters only where two shapes can match the
# same text — the Jira key pattern is last so it never shadows the more
# specific "PR-\d+" (Azure DevOps), since "PR" is itself a syntactically
# valid Jira project key.
REFERENCE_PATTERNS: list[ReferencePattern] = [
    ReferencePattern(
        name="ado_work_item_key",
        pattern=re.compile(r"AB#(\d+)"),
        build_ref=_ado_ref,
        describes="an Azure Boards work item reference",
    ),
    # Real conventions found in this organization's own data, neither of
    # which the canonical "AB#123" pattern matches: 22 "AB-56" and 14
    # "WI-324" references were being extracted, routed to Jira (both match
    # a Jira project-key shape), and dropped — even though three of the
    # WI- targets were already-synced work items sitting right there.
    # Normalized to the AB# ref shape so no resolution rule has to know
    # about the variants. Listed before the Jira key pattern so the span
    # is consumed here rather than misread as a Jira issue.
    ReferencePattern(
        name="ado_work_item_key_hyphen",
        pattern=re.compile(r"\bAB-(\d+)\b"),
        build_ref=_ado_ref,
        describes="an Azure Boards work item reference",
    ),
    ReferencePattern(
        name="ado_work_item_key_wi",
        pattern=re.compile(r"\bWI-(\d+)\b"),
        build_ref=_ado_ref,
        describes="an Azure Boards work item reference",
    ),
    ReferencePattern(
        name="ado_work_item_url",
        # dev.azure.com/org/project/_workitems/edit/123 and the older
        # org.visualstudio.com/project/_workitems/edit/123 both end the
        # same way, so match the distinctive tail rather than the host.
        pattern=re.compile(r"/_workitems/edit/(\d+)"),
        build_ref=_ado_ref,
        describes="a pasted Azure Boards work item link",
    ),
    ReferencePattern(
        name="ado_pull_request_key",
        pattern=re.compile(r"\bPR-(\d+)\b"),
        build_ref=_ado_pr_ref,
        describes="an Azure DevOps pull request reference",
    ),
    ReferencePattern(
        name="confluence_page_url",
        # .../wiki/spaces/KEY/pages/12345/Optional-Title
        pattern=re.compile(r"/wiki/spaces/[^/\s]+/pages/(\d+)"),
        build_ref=_confluence_ref,
        describes="a pasted Confluence page link",
    ),
    ReferencePattern(
        name="confluence_page_macro",
        # Confluence's own storage-format link macro, present in page bodies.
        pattern=re.compile(r'ri:content-id="(\d+)"'),
        build_ref=_confluence_ref,
        describes="Confluence's own page-link macro",
    ),
    ReferencePattern(
        name="github_cross_repo_key",
        pattern=re.compile(r"\b([\w.-]+/[\w.-]+)#(\d+)\b"),
        build_ref=_github_qualified_ref,
        describes="a fully-qualified GitHub issue/PR reference",
    ),
    ReferencePattern(
        name="github_url",
        pattern=re.compile(r"github\.com/([\w.-]+/[\w.-]+)/(?:pull|issues)/(\d+)"),
        build_ref=_github_qualified_ref,
        describes="a pasted GitHub pull request or issue link",
    ),
    ReferencePattern(
        name="github_same_repo_key",
        # Only resolvable when the caller supplies the owning repo.
        pattern=re.compile(r"(?<![\w/])#(\d+)\b"),
        build_ref=_github_same_repo_ref,
        describes="a same-repo GitHub reference",
    ),
    ReferencePattern(
        name="jira_issue_key",
        pattern=re.compile(r"\b([A-Z][A-Z0-9]{1,9}-\d+)\b"),
        build_ref=_jira_ref,
        describes="a Jira issue key",
    ),
]


# Where a reference was found decides what the relationship actually
# means, not just how confident we are in it — a work item id in a pull
# request *title* is the author declaring "this PR does that work",
# whereas the same id in a review comment is a passing mention. The
# EdgeType vocabulary for this already existed and went unused: every
# extracted link collapsed to MENTIONS/RELATED_TO regardless of source.
LINK_KIND_BY_LOCATION: dict[str, LinkKind] = {
    # Only these three locations carry unambiguous intent. A pull request
    # *titled* "AB#412 add linkedin url" is the author declaring the PR
    # does that work; a branch named for a work item is the same claim; a
    # commit message naming one says that commit changed it.
    "title": "implements",
    "branch": "implements",
    "commit_message": "changes",
    # Everything else is a mention and nothing stronger. A reference in a
    # page or description body is genuinely ambiguous — a Confluence page
    # naming a work item might be its specification, or might be meeting
    # notes that mention it in passing, and the body alone cannot tell
    # them apart. Claiming SPECIFIED_BY for all of them would be exactly
    # the kind of over-confident inference this project refuses elsewhere
    # (AGENTS.md §4 on autonomous ownership inference).
    "page_body": "mentions",
    "description": "mentions",
    "body": "mentions",
    "comment": "mentions",
    "text": "mentions",
}

# Confidence prior by where the reference was found, before resolution.
# link_extraction.py raises this once the reference actually resolves to
# a real node — an explicit id that resolves is evidence, not a guess.
CONFIDENCE_BY_LOCATION: dict[str, float] = {
    "title": 0.90,
    "commit_message": 0.88,
    "branch": 0.85,
    "page_body": 0.80,
    "description": 0.80,
    "body": 0.75,
    "comment": 0.70,
    "text": 0.70,
}


def extract_cross_references(
    from_native_id: str,
    text: str,
    *,
    location: str = "text",
    where_label: str | None = None,
    repo_full_name: str | None = None,
    skip_ref: Callable[[str], bool] | None = None,
) -> list[SourceLink]:
    """Every cross-system reference in `text`, as SourceLinks.

    `location` is where the text came from ("title", "commit_message",
    "page_body", ...) and drives both the relationship type and the
    confidence prior — see LINK_KIND_BY_LOCATION / CONFIDENCE_BY_LOCATION.
    `where_label` is the human phrasing used in evidence shown to a
    reviewer; it defaults to `location`. `skip_ref` filters out refs a
    caller knows are self-references (a page linking to itself).
    """
    if not text:
        return []

    link_kind = LINK_KIND_BY_LOCATION.get(location, "mentions")
    confidence = CONFIDENCE_BY_LOCATION.get(location, 0.70)
    label = where_label or location.replace("_", " ")

    links: list[SourceLink] = []
    seen: set[str] = set()
    # Character spans already claimed by an earlier (more specific)
    # pattern. Without this the same text yields two contradictory
    # references — "AB-56" matches the Azure DevOps hyphen convention
    # *and* the generic Jira project-key shape, and both were being
    # emitted, one of which could never resolve.
    claimed: list[tuple[int, int]] = []

    def overlaps(start: int, end: int) -> bool:
        return any(start < c_end and c_start < end for c_start, c_end in claimed)

    for ref_pattern in REFERENCE_PATTERNS:
        for m in ref_pattern.pattern.finditer(text):
            if overlaps(m.start(), m.end()):
                continue
            target_ref = ref_pattern.build_ref(m, repo_full_name)
            if target_ref is None or target_ref in seen:
                continue
            if skip_ref is not None and skip_ref(target_ref):
                continue
            seen.add(target_ref)
            claimed.append((m.start(), m.end()))
            links.append(
                SourceLink(
                    from_native_id=from_native_id,
                    target_ref=target_ref,
                    link_kind=link_kind,
                    evidence=(
                        f"Found {ref_pattern.describes} in the {label}: "
                        f'"{snippet(text, m.start(), m.end())}"'
                    ),
                    confidence=confidence,
                )
            )
    return links
