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


class RelationshipRule(BaseModel):
    """One row of configs/relationships.yaml: which node kinds a given
    edge type is legal between. `from_`/`to` entries are either a literal
    kind, a name from `kind_groups`, or "*" for "any kind" — expansion
    happens in RelationshipsConfig.allows, not here, since a single rule
    has no access to the groups dict it needs to resolve against."""

    model_config = ConfigDict(extra="forbid")

    edge: EdgeType
    from_: list[str] = Field(alias="from")
    to: list[str]


class RelationshipsConfig(BaseModel):
    """Domain/range rules for extracted (SYNC_EXTRACTED) edges — the
    declaration that was missing when a title-location reference typed
    itself IMPLEMENTS with no check that the source was actually a pull
    request, producing STORY --IMPLEMENTS--> STORY. `link_extraction.py`
    calls `.allows()` before creating any extracted edge; CONTAINS is
    structural and never passes through here."""

    model_config = ConfigDict(extra="forbid")

    kind_groups: dict[str, list[str]] = Field(default_factory=dict)
    relationships: list[RelationshipRule]

    def _expand(self, names: list[str]) -> set[str] | None:
        """None means unconstrained (a "*" entry) — every other entry is
        either a literal kind or a kind_groups name, expanded to itself
        if it isn't a known group."""
        if "*" in names:
            return None
        expanded: set[str] = set()
        for name in names:
            expanded.update(self.kind_groups.get(name, [name]))
        return expanded

    def allows(self, edge_type: EdgeType, src_kind: str, dst_kind: str) -> bool:
        """True if some declared rule for `edge_type` permits this
        (src_kind, dst_kind) pair. An edge type with no rule at all is
        rejected, not passed through — the same fail-fast stance as the
        rest of this module: a new EdgeType member with no declared rule
        should be caught by writing the rule, not by silently allowing
        anything until someone notices."""
        for rule in self.relationships:
            if rule.edge is not edge_type:
                continue
            allowed_src = self._expand(rule.from_)
            allowed_dst = self._expand(rule.to)
            if (allowed_src is None or src_kind in allowed_src) and (
                allowed_dst is None or dst_kind in allowed_dst
            ):
                return True
        return False


def load_relationships(path: Path | None = None) -> RelationshipsConfig:
    """Parse and validate configs/relationships.yaml. Raises immediately
    on any problem — see load_capabilities."""
    target = path or (CONFIGS_DIR / "relationships.yaml")
    raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    return RelationshipsConfig.model_validate(raw)


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
