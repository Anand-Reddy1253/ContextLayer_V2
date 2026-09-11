"""End-to-end exercise of GitHubFixtureConnector against the real fixture
files in fixtures/github/ (not mocked) — docs/phases/PHASE-05.md.
"""

import pytest

from context_fabric.connectors.github.fixture import GitHubFixtureConnector
from context_fabric.domain.errors import NotFound


@pytest.fixture
def connector() -> GitHubFixtureConnector:
    return GitHubFixtureConnector()


async def test_discover_containers_returns_the_org(connector):
    containers = await connector.discover_containers()
    assert [c.native_id for c in containers] == ["acme-org"]
    assert containers[0].kind == "ORGANIZATION"


async def test_list_children_of_org_returns_both_repos(connector):
    page = await connector.list_children("acme-org")
    native_ids = {r.native_id for r in page.items}
    assert native_ids == {"acme-org/identity-service", "acme-org/sso-gateway"}


async def test_list_children_walks_repo_to_branch_to_tree(connector):
    branches = (await connector.list_children("acme-org/identity-service")).items
    assert [b.native_id for b in branches] == ["acme-org/identity-service@main"]

    # A branch's children are its 3 root tree entries (README.md, src,
    # tests) *and* its 1 commit — 4 items at page size 2, the documented
    # pagination boundary.
    page1 = await connector.list_children("acme-org/identity-service@main")
    assert len(page1.items) == 2
    assert page1.next_cursor == "2"

    page2 = await connector.list_children(
        "acme-org/identity-service@main", cursor=page1.next_cursor
    )
    assert len(page2.items) == 2
    assert page2.next_cursor is None

    all_items = [*page1.items, *page2.items]
    kinds = {item.kind for item in all_items}
    assert kinds == {"FILE", "DIRECTORY", "COMMIT"}

    root_names = {item.name for item in all_items if item.kind in ("FILE", "DIRECTORY")}
    assert root_names == {"README.md", "src", "tests"}

    commit_items = [item for item in all_items if item.kind == "COMMIT"]
    assert len(commit_items) == 1
    assert commit_items[0].native_id == "acme-org/identity-service@abc1234"

    src_dir = next(item for item in all_items if item.name == "src")
    src_children = (await connector.list_children(src_dir.native_id)).items
    src_names = {c.name for c in src_children}
    assert src_names == {"main.py", "sso"}


async def test_get_object_resolves_repo_pr_commit_run_and_file(connector):
    repo = await connector.get_object("acme-org/identity-service")
    assert repo.kind == "REPOSITORY"

    pr = await connector.get_object("acme-org/identity-service#7")
    assert pr.kind == "PULL_REQUEST"

    commit = await connector.get_object("acme-org/identity-service@abc1234")
    assert commit.kind == "COMMIT"

    run = await connector.get_object("acme-org/identity-service/actions/555")
    assert run.kind == "BUILD"

    file_obj = await connector.get_object("acme-org/identity-service@main:src/sso/callback.py")
    assert file_obj.kind == "FILE"


async def test_get_object_missing_raises_not_found(connector):
    with pytest.raises(NotFound):
        await connector.get_object("does-not-exist")


async def test_get_content_returns_file_body(connector):
    content = await connector.get_content("acme-org/identity-service@main:src/sso/callback.py")
    assert "handle_sso_callback" in content.text


async def test_get_content_missing_raises_not_found(connector):
    with pytest.raises(NotFound):
        await connector.get_content("acme-org/identity-service@main:src/main.py")


async def test_get_changes_paginates_and_includes_a_tombstone(connector):
    # changes.json has 2 items at a fixture page size of 1 — a genuine
    # 2-page cursor walk, not a single call.
    page1 = await connector.get_changes()
    assert len(page1.items) == 1
    assert page1.has_more is True

    page2 = await connector.get_changes(cursor=page1.next_cursor)
    assert len(page2.items) == 1
    assert page2.has_more is False

    by_id = {item.native_id: item for item in [*page1.items, *page2.items]}
    assert by_id["acme-org/identity-service@main:src/sso/legacy_callback.py"].deleted is True
    assert by_id["acme-org/identity-service@main:src/sso/callback.py"].deleted is False


async def test_get_links_on_commit_mentions_ado_work_item(connector):
    # The cross-connector link Phase 7 needs: a GitHub commit message
    # mentioning an Azure DevOps work item ref.
    links = await connector.get_links("acme-org/identity-service@abc1234")
    assert any(link.target_ref == "AB#312" and link.link_kind == "mentions" for link in links)


async def test_get_links_on_pull_request_mentions_ado_work_item(connector):
    links = await connector.get_links("acme-org/identity-service#7")
    assert any(link.target_ref == "AB#312" for link in links)


async def test_get_links_on_pull_request_finds_mention_in_title_alone(connector):
    # Real bug found via live testing: a real PR titled "AB#56 Assign
    # skills to an employee profile" with an empty body had its reference
    # silently missed — get_links only ever scanned `body`, never `title`.
    links = await connector.get_links("acme-org/identity-service#8")
    assert any(link.target_ref == "AB#401" for link in links)


async def test_get_links_unknown_native_id_returns_empty(connector):
    assert await connector.get_links("does-not-exist") == []


async def test_get_acl_reference(connector):
    ref = await connector.get_acl_reference("acme-org/identity-service")
    assert ref.acl_ref["team"] == "identity-squad"


async def test_get_acl_reference_missing_raises_not_found(connector):
    with pytest.raises(NotFound):
        await connector.get_acl_reference("does-not-exist")
