import pytest
import yaml
from pydantic import ValidationError

from context_fabric.domain.config import (
    CONFIGS_DIR,
    load_capabilities,
    load_stage_contracts,
)
from context_fabric.domain.enums import Capability


def test_load_capabilities_parses_real_config():
    config = load_capabilities()
    ids = {c.id for c in config.capabilities}
    assert ids == set(Capability)
    for c in config.capabilities:
        assert c.description


def test_load_stage_contracts_parses_real_config():
    config = load_stage_contracts()
    assert set(config.stages) == {
        "requirement",
        "design",
        "implementation",
        "testing",
        "review",
    }
    assert config.defaults.max_items == 10
    assert config.defaults.token_share == 10
    assert config.defaults.max_age_days == 14
    assert config.defaults.required is False

    requirement = config.stages["requirement"]
    slot_names = {s.name for s in requirement.slots}
    assert "work_item_hierarchy" in slot_names
    assert "explicitly_linked_documents" in slot_names

    work_item_slot = next(
        s for s in requirement.slots if s.name == "work_item_hierarchy"
    )
    assert work_item_slot.required is True
    assert work_item_slot.traversal.max_hops == 4
    assert work_item_slot.traversal.direction == "both"


def test_configs_dir_points_at_repo_configs():
    assert (CONFIGS_DIR / "capabilities.yaml").exists()
    assert (CONFIGS_DIR / "stage-contracts.yaml").exists()


def test_load_capabilities_fails_fast_on_missing_required_key(tmp_path):
    bad = tmp_path / "capabilities.yaml"
    bad.write_text(yaml.safe_dump({"capabilities": [{"id": "CODE"}]}), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_capabilities(bad)


def test_load_stage_contracts_fails_fast_on_missing_defaults(tmp_path):
    bad = tmp_path / "stage-contracts.yaml"
    bad.write_text(yaml.safe_dump({"stages": {}}), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_stage_contracts(bad)


def test_load_stage_contracts_fails_fast_on_unknown_edge_type(tmp_path):
    bad_stage = {
        "stages": {
            "requirement": {
                "slots": [
                    {
                        "name": "broken_slot",
                        "node_kinds": ["WORK_ITEM"],
                        "traversal": {
                            "edge_types": ["NOT_A_REAL_EDGE_TYPE"],
                            "max_hops": 2,
                            "direction": "any",
                        },
                    }
                ]
            }
        },
        "defaults": {
            "max_items": 10,
            "token_share": 10,
            "max_age_days": 14,
            "required": False,
        },
    }
    bad = tmp_path / "stage-contracts.yaml"
    bad.write_text(yaml.safe_dump(bad_stage), encoding="utf-8")
    with pytest.raises(ValidationError):
        load_stage_contracts(bad)
