from __future__ import annotations

from context_fabric.connectors.ai_assets import (
    ai_asset_native_id,
    classify_ai_asset_path,
    map_ai_asset,
    parse_ai_asset_description,
    parse_ai_asset_ref,
)


def test_classify_ai_asset_path_recognizes_each_vendor_directory():
    assert classify_ai_asset_path(".github/agents/reviewer.md") == ("github", "agent")
    assert classify_ai_asset_path(".github/skills/deploy.md") == ("github", "skill")
    assert classify_ai_asset_path(".github/prompts/summarize.md") == ("github", "prompt")
    assert classify_ai_asset_path(".claude/agents/reviewer.md") == ("claude", "agent")
    assert classify_ai_asset_path(".claude/skills/deploy.md") == ("claude", "skill")
    assert classify_ai_asset_path(".claude/commands/ship.md") == ("claude", "command")
    assert classify_ai_asset_path(".cursor/rules/style.md") == ("cursor", "rule")


def test_classify_ai_asset_path_rejects_non_markdown():
    assert classify_ai_asset_path(".github/agents/scope-map.json") is None


def test_classify_ai_asset_path_rejects_unrecognized_directory():
    assert classify_ai_asset_path("src/main.md") is None


def test_classify_ai_asset_path_rejects_bare_directory():
    assert classify_ai_asset_path(".github/agents/") is None


def test_parse_ai_asset_description_reads_frontmatter():
    text = "---\nname: Reviewer\ndescription: Reviews pull requests\n---\nBody text.\n"
    name, description = parse_ai_asset_description(text, fallback_name="reviewer")
    assert name == "Reviewer"
    assert description == "Reviews pull requests"


def test_parse_ai_asset_description_falls_back_to_first_line():
    text = "# Reviewer Agent\n\nDoes review things.\n"
    name, description = parse_ai_asset_description(text, fallback_name="reviewer")
    assert name == "reviewer"
    assert description == "Reviewer Agent"


def test_parse_ai_asset_description_handles_empty_text():
    name, description = parse_ai_asset_description("", fallback_name="reviewer")
    assert name == "reviewer"
    assert description == ""


def test_ai_asset_native_id_roundtrips_through_parse_ai_asset_ref():
    native_id = ai_asset_native_id("acme-org/identity-service", ".github/agents/reviewer.md")
    assert parse_ai_asset_ref(native_id) == (
        "acme-org/identity-service",
        ".github/agents/reviewer.md",
    )


def test_ai_asset_native_id_roundtrips_for_a_guid_style_container():
    # Azure DevOps repos are identified by GUID, not "owner/repo" — the
    # marker-based encoding must work identically either way.
    native_id = ai_asset_native_id(
        "3fa85f64-5717-4562-b3fc-2c963f66afa6", ".claude/skills/deploy.md"
    )
    assert parse_ai_asset_ref(native_id) == (
        "3fa85f64-5717-4562-b3fc-2c963f66afa6",
        ".claude/skills/deploy.md",
    )


def test_parse_ai_asset_ref_returns_none_for_non_ai_asset_native_id():
    assert parse_ai_asset_ref("acme-org/identity-service@main:src/app.py") is None


def test_map_ai_asset_produces_ai_asset_kind_node():
    node = map_ai_asset(
        "acme-org/identity-service",
        ".github/agents/reviewer.md",
        vendor="github",
        asset_type="agent",
        name="Reviewer",
        description="Reviews pull requests",
    )
    assert node.kind == "AI_ASSET"
    assert node.name == "Reviewer"
    assert node.parent_native_id == "acme-org/identity-service"
    assert node.attributes["vendor"] == "github"
    assert node.attributes["asset_type"] == "agent"
    assert node.attributes["path"] == ".github/agents/reviewer.md"
