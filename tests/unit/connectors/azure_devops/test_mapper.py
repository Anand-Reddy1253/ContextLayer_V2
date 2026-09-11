from context_fabric.connectors.azure_devops import mapper
from context_fabric.domain.connector_types import (
    ACLReference,
    SourceContainer,
    SourceContent,
    SourceLink,
    SourceObject,
)

PROJECT_RAW = {
    "id": "TalentFlow",
    "name": "TalentFlow",
    "description": "TalentFlow product line.",
    "url": "https://dev.azure.com/acme/TalentFlow",
}

AREA_PATH_RAW = {
    "id": "TalentFlow\\Identity",
    "name": "Identity",
    "project": "TalentFlow",
    "path": "TalentFlow\\Identity",
    "url": "https://dev.azure.com/acme/TalentFlow/_apis/wit/classificationNodes/Areas/Identity",
}

STORY_RAW = {
    "id": 312,
    "rev": 5,
    "fields": {
        "System.WorkItemType": "User Story",
        "System.Title": "Add SSO callback handling to identity-service",
        "System.State": "Active",
        "System.AreaPath": "TalentFlow\\Identity",
        "System.Parent": 305,
        "System.Description": "Implement the callback. See AB#301 for context.",
    },
    "relations": [
        {
            "rel": "ArtifactLink",
            "url": "vstfs:///Git/PullRequestId/identity-service%2F42",
            "attributes": {"name": "Pull Request"},
        }
    ],
    "url": "https://dev.azure.com/acme/TalentFlow/_workitems/edit/312",
}

EPIC_RAW = {
    "id": 301,
    "rev": 1,
    "fields": {
        "System.WorkItemType": "Epic",
        "System.Title": "Modernize Identity & Access Management",
        "System.State": "Active",
        "System.AreaPath": "TalentFlow\\Identity",
        "System.Description": "Consolidate SSO.",
    },
    "url": "https://dev.azure.com/acme/TalentFlow/_workitems/edit/301",
}

PR_RAW = {
    "pullRequestId": 42,
    "title": "Implement SSO callback endpoint (AB#312)",
    "description": "Fixes AB#312.",
    "status": "active",
    "repository": {"id": "identity-service", "name": "identity-service"},
    "sourceRefName": "refs/heads/feature/sso-callback",
    "targetRefName": "refs/heads/main",
    "url": "https://dev.azure.com/acme/TalentFlow/_git/identity-service/pullrequest/42",
}

BUILD_RAW = {
    "id": 100,
    "buildNumber": "20260901.1",
    "status": "completed",
    "result": "succeeded",
    "definition": {"id": 7, "name": "identity-service-ci"},
    "sourceBranch": "refs/heads/main",
    "url": "https://dev.azure.com/acme/TalentFlow/_build/results?buildId=100",
}


def test_map_project():
    container = mapper.map_project(PROJECT_RAW)
    assert isinstance(container, SourceContainer)
    assert container.native_id == "TalentFlow"
    assert container.kind == "PROJECT"
    assert container.parent_id is None


def test_map_area_path():
    obj = mapper.map_area_path(AREA_PATH_RAW)
    assert isinstance(obj, SourceObject)
    assert obj.kind == "AREA_PATH"
    assert obj.parent_native_id == "TalentFlow"
    assert obj.attributes["path"] == "TalentFlow\\Identity"


def test_map_work_item_story_has_parent_feature():
    obj = mapper.map_work_item(STORY_RAW)
    assert isinstance(obj, SourceObject)
    assert obj.native_id == "312"
    assert obj.kind == "STORY"
    assert obj.parent_native_id == "305"
    assert obj.name == "Add SSO callback handling to identity-service"
    assert obj.source_version == "5"
    assert obj.content_hash
    assert obj.deleted is False


def test_map_work_item_epic_has_area_path_as_parent():
    obj = mapper.map_work_item(EPIC_RAW)
    assert obj.kind == "EPIC"
    assert obj.parent_native_id == "TalentFlow\\Identity"


def test_map_tombstone():
    obj = mapper.map_tombstone("299", "STORY")
    assert obj.deleted is True
    assert obj.native_id == "299"


def test_map_pull_request():
    obj = mapper.map_pull_request(PR_RAW)
    assert obj.native_id == "PR-42"
    assert obj.kind == "PULL_REQUEST"
    assert obj.parent_native_id == "identity-service"


def test_map_build():
    obj = mapper.map_build(BUILD_RAW)
    assert obj.native_id == "BUILD-100"
    assert obj.kind == "BUILD"
    assert "identity-service-ci" in obj.name


def test_map_content():
    content = mapper.map_content("312", STORY_RAW)
    assert isinstance(content, SourceContent)
    assert content.native_id == "312"
    assert content.version == "5"
    assert "Implement the callback" in content.text


def test_map_links_extracts_pr_and_mention():
    links = mapper.map_links(STORY_RAW)
    assert all(isinstance(link, SourceLink) for link in links)
    kinds = {(link.target_ref, link.link_kind) for link in links}
    assert ("PR-42", "relates_to") in kinds
    assert ("AB#301", "mentions") in kinds


def test_map_links_extracts_real_ado_two_guid_artifact_link():
    # Real ADO artifact links are "PullRequestId/{projectGuid}%2F
    # {repoGuid}%2F{prId}" — two GUID segments, not the fixture's
    # simplified single-segment "identity-service%2F42" shape. A regex
    # that stops at the first "%2F" would capture the leading digits of
    # the repository GUID instead of the real PR id at the end (this
    # exact case surfaced that bug: repo GUID
    # "17bff134-fbf3-4f13-85f6-63e3d63c7472" was misread as PR-17
    # instead of the actual PR-118).
    raw = {
        "id": 999,
        "rev": 1,
        "fields": {
            "System.WorkItemType": "Task",
            "System.Title": "Some task",
            "System.State": "Active",
            "System.AreaPath": "DevOnHire",
        },
        "relations": [
            {
                "rel": "ArtifactLink",
                "url": (
                    "vstfs:///Git/PullRequestId/"
                    "58eab199-102b-4961-869c-e6aa3a792b10%2F"
                    "17bff134-fbf3-4f13-85f6-63e3d63c7472%2F118"
                ),
                "attributes": {"name": "Pull Request"},
            }
        ],
    }
    links = mapper.map_links(raw)
    kinds = {(link.target_ref, link.link_kind) for link in links}
    assert ("PR-118", "relates_to") in kinds
    assert ("PR-17", "relates_to") not in kinds


def test_map_links_extracts_jira_key_mention_from_description():
    raw = {
        "id": 998,
        "rev": 1,
        "fields": {
            "System.WorkItemType": "Task",
            "System.Title": "Some task",
            "System.State": "Active",
            "System.AreaPath": "DevOnHire",
            "System.Description": "Tracked upstream as TALENT-2.",
        },
    }
    links = mapper.map_links(raw)
    refs = {link.target_ref for link in links}
    assert "TALENT-2" in refs


def test_map_acl():
    ref = mapper.map_acl({"native_id": "312", "acl_ref": {"group": "identity-squad"}})
    assert isinstance(ref, ACLReference)
    assert ref.acl_ref["group"] == "identity-squad"
