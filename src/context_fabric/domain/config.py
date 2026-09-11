"""Pydantic models + loaders for configs/capabilities.yaml and
configs/stage-contracts.yaml.

These loaders are meant to be called once, eagerly, by a process's startup
path (main.py, cli entrypoints) — not lazily on first retrieval call — so a
malformed config fails the process immediately instead of surfacing deep
inside a request (docs/phases/PHASE-01.md "fail fast on a malformed
config, don't defer the error to first use"). They deliberately are not
executed as an import-time side effect of this module, since that would
make `import context_fabric.domain` depend on the working directory
containing a `configs/` tree — a startup script's job, not an import's.

Defaults (`StageContractDefaults`) are parsed but not applied to slots here
— merging an unset slot field with the stage contract's defaults is
retrieval/contracts.py's job (Phase 10, docs/RETRIEVAL.md §2), so this
stays pure structural validation with exactly one source of truth for the
default values (the YAML file itself).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from context_fabric.domain.enums import Capability, EdgeType

CONFIGS_DIR = Path(__file__).resolve().parents[3] / "configs"

TraversalDirection = Literal["up", "down", "both", "any"]


class CapabilityDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Capability
    description: str
    served_by: list[str] = Field(default_factory=list)


class CapabilitiesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capabilities: list[CapabilityDefinition]


class TraversalSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edge_types: list[EdgeType]
    max_hops: int = Field(gt=0)
    direction: TraversalDirection


class StageSlot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    node_kinds: list[str]
    capability: Capability | None = None
    traversal: TraversalSpec
    required: bool | None = None
    max_items: int | None = None
    token_share: int | None = None
    max_age_days: int | None = None


class StageContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slots: list[StageSlot]


class StageContractDefaults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_items: int
    token_share: int
    max_age_days: int
    required: bool


class StageContractsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stages: dict[str, StageContract]
    defaults: StageContractDefaults


def load_capabilities(path: Path | None = None) -> CapabilitiesConfig:
    """Parse and validate configs/capabilities.yaml. Raises immediately
    (FileNotFoundError, yaml.YAMLError, or pydantic.ValidationError) on any
    problem — never returns a partially-valid config."""
    target = path or (CONFIGS_DIR / "capabilities.yaml")
    raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    return CapabilitiesConfig.model_validate(raw)


def load_stage_contracts(path: Path | None = None) -> StageContractsConfig:
    """Parse and validate configs/stage-contracts.yaml. Raises immediately
    on any problem — see load_capabilities."""
    target = path or (CONFIGS_DIR / "stage-contracts.yaml")
    raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    return StageContractsConfig.model_validate(raw)
