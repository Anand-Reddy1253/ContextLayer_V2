from context_fabric.connectors.github import mapper
from context_fabric.domain.connector_types import (
    ACLReference,
    SourceContainer,
    SourceContent,
    SourceLink,
    SourceObject,
)

ORG_RAW = {"login": "acme-org", "name": "ACME Corp", "html_url": "https://github.com/acme-org"}

REPO_RAW = {
    "full_name": "acme-org/identity-service",
    "name": "identity-service",
    "owner": "acme-org",
    "default_branch": "main",
    "description": "Identity and SSO service.",
    "html_url": "https://github.com/acme-org/identity-service",
}

BRANCH_RAW = {"repo": "acme-org/identity-service", "name": "main", "commit_sha": "abc1234"}

PR_RAW = {
    "repo": "acme-org/identity-service",
    "number": 7,
    "title": "Implement SSO callback endpoint",
    "body": "Adds the OAuth2 callback handler. Fixes AB#312.",
    "state": "open",
    "head_ref": "feature/sso-callback",
    "base_ref": "main",
    "html_url": "https://github.com/acme-org/identity-service/pull/7",
}

COMMIT_RAW = {
    "repo": "acme-org/identity-service",
    "sha": "abc1234",
    "message": "Implement SSO callback handling (AB#312)",
    "author": "dev@acme.example",
    "html_url": "https://github.com/acme-org/identity-service/commit/abc1234",
}

RUN_RAW = {
    "repo": "acme-org/identity-service",
    "run_id": 555,
    "name": "CI",
    "status": "completed",
    "conclusion": "success",
    "head_sha": "abc1234",
    "html_url": "https://github.com/acme-org/identity-service/actions/runs/555",
}


def test_map_organization():
    container = mapper.map_organization(ORG_RAW)
    assert isinstance(container, SourceContainer)
    assert container.native_id == "acme-org"
    assert container.kind == "ORGANIZATION"


def test_map_repository():
    obj = mapper.map_repository(REPO_RAW)
    assert isinstance(obj, SourceObject)
    assert obj.native_id == "acme-org/identity-service"
    assert obj.kind == "REPOSITORY"
    assert obj.parent_native_id == "acme-org"


def test_map_branch():
    obj = mapper.map_branch(BRANCH_RAW)
    assert obj.native_id == "acme-org/identity-service@main"
    assert obj.kind == "BRANCH"
    assert obj.parent_native_id == "acme-org/identity-service"


def test_map_tree_entry_root_file():
    obj = mapper.map_tree_entry(
        "acme-org/identity-service", "main", {"path": "README.md", "type": "blob"}
    )
    assert obj.kind == "FILE"
    assert obj.parent_native_id == "acme-org/identity-service@main"
    assert obj.native_id == "acme-org/identity-service@main:README.md"


def test_map_tree_entry_nested_file():
    obj = mapper.map_tree_entry(
        "acme-org/identity-service",
        "main",
        {"path": "src/sso/callback.py", "type": "blob"},
    )
    assert obj.kind == "FILE"
    assert obj.name == "callback.py"
    assert obj.parent_native_id == "acme-org/identity-service@main:src/sso"


def test_map_tree_entry_directory():
    obj = mapper.map_tree_entry(
        "acme-org/identity-service", "main", {"path": "src", "type": "tree"}
    )
    assert obj.kind == "DIRECTORY"


def test_map_tombstone():
    obj = mapper.map_tombstone("acme-org/identity-service@main:src/old.py", "FILE")
    assert obj.deleted is True


def test_map_pull_request():
    obj = mapper.map_pull_request(PR_RAW)
    assert obj.native_id == "acme-org/identity-service#7"
    assert obj.kind == "PULL_REQUEST"
    assert obj.parent_native_id == "acme-org/identity-service"


def test_map_commit():
    obj = mapper.map_commit(COMMIT_RAW)
    assert obj.native_id == "acme-org/identity-service@abc1234"
    assert obj.kind == "COMMIT"
    assert obj.name == "Implement SSO callback handling (AB#312)"


def test_map_actions_run():
    obj = mapper.map_actions_run(RUN_RAW)
    assert obj.native_id == "acme-org/identity-service/actions/555"
    assert obj.kind == "BUILD"


def test_map_content():
    content = mapper.map_content(
        {"native_id": "x", "mime_type": "text/x-python", "text": "print(1)"}
    )
    assert isinstance(content, SourceContent)
    assert content.text == "print(1)"


def test_map_links_from_text_extracts_mention():
    links = mapper.map_links_from_text("acme-org/identity-service@abc1234", COMMIT_RAW["message"])
    assert isinstance(links[0], SourceLink)
    assert links[0].target_ref == "AB#312"
    assert links[0].link_kind == "mentions"


def test_map_links_from_text_extracts_same_repo_github_reference():
    # Previously never extracted at all — only AB# mentions were.
    text = "Fixes #42, follow-up to the SSO work."
    links = mapper.map_links_from_text(
        "acme-org/identity-service#7", text, repo_full_name="acme-org/identity-service"
    )
    refs = {link.target_ref for link in links}
    assert "acme-org/identity-service#42" in refs


def test_map_links_from_text_same_repo_reference_needs_repo_context():
    # Without repo_full_name, a bare "#42" can't be made into a fully
    # qualified target_ref, so it's correctly not extracted.
    links = mapper.map_links_from_text("acme-org/identity-service#7", "Fixes #42.")
    assert links == []


def test_map_links_from_text_extracts_cross_repo_github_reference():
    text = "Depends on acme-org/sso-gateway#99 landing first."
    links = mapper.map_links_from_text(
        "acme-org/identity-service#7", text, repo_full_name="acme-org/identity-service"
    )
    refs = {link.target_ref for link in links}
    assert "acme-org/sso-gateway#99" in refs
    # The cross-repo match must not also fire the same-repo pattern on
    # its own "#99" tail.
    assert "acme-org/identity-service#99" not in refs


def test_map_links_from_text_extracts_jira_key_reference():
    text = "This closes TALENT-2 in Jira."
    links = mapper.map_links_from_text("acme-org/identity-service#7", text)
    refs = {link.target_ref for link in links}
    assert "TALENT-2" in refs


def test_map_acl():
    ref = mapper.map_acl({"native_id": "acme-org/identity-service", "acl_ref": {"team": "x"}})
    assert isinstance(ref, ACLReference)
