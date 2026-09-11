"""CLI entrypoint. Defines the Typer `app` referenced by the
`context-fabric` console script in pyproject.toml.

    context-fabric sync --source ado --fixture
    context-fabric sync --source github --fixture
    context-fabric reconcile --context-space talentflow/identity
"""

from __future__ import annotations

import asyncio

import typer

from context_fabric.catalog import (
    create_context_space,
    find_context_space_config_by_id,
    get_context_space,
    load_business_tree_config,
    load_context_space_config,
    reconcile_context_space,
    seed_business_tree,
)
from context_fabric.connectors import get_fixture_connector_class, get_live_connector_class
from context_fabric.connectors.base import SourceConnector
from context_fabric.persistence.repositories.context_space import ContextSpaceRepository
from context_fabric.persistence.repositories.node import NodeRepository
from context_fabric.persistence.session import session_scope
from context_fabric.synchronization import sync_source

app = typer.Typer(help="Context Fabric CLI", no_args_is_help=True)


@app.callback()
def _main() -> None:
    """Context Fabric CLI.

    A Typer app with exactly one @app.command() otherwise collapses into
    running that command directly, without its name — this empty
    callback keeps `sync` (and Phase 8's `reconcile`) explicit subcommands
    the way every doc and script in this repo invokes them.
    """


SOURCE_ALIASES = {"ado": "azure_devops", "azure_devops": "azure_devops", "github": "github"}

# Matches configs/context-spaces/talentflow-identity.yaml's binding
# source_instance_id values, so Phase 8's reconciliation resolves against
# whatever this synced. Real connector-instance management (multiple
# instances per source, configured via the UI) lands in Phase 16.
SOURCE_INSTANCE_IDS = {"azure_devops": "ado-acme", "github": "github-acme"}


@app.command()
def sync(
    source: str = typer.Option(..., "--source", help="ado | azure_devops | github"),
    fixture: bool = typer.Option(False, "--fixture", help="Use the fixture-mode connector."),
    live: bool = typer.Option(False, "--live", help="Use the live-mode connector (Phase 19)."),
) -> None:
    """Sync one connector's data into the graph."""
    source_system = SOURCE_ALIASES.get(source)
    if source_system is None:
        typer.echo(
            f"unknown --source {source!r}; expected one of {sorted(SOURCE_ALIASES)}", err=True
        )
        raise typer.Exit(code=1)
    if fixture and live:
        typer.echo("pass only one of --fixture / --live", err=True)
        raise typer.Exit(code=1)

    mode = "live" if live else "fixture"
    asyncio.run(_run_sync(source_system, mode))


async def _run_sync(source_system: str, mode: str) -> None:
    # Registry-returned classes always structurally satisfy SourceConnector
    # (proven by tests/acceptance/test_connectors_never_leak_vendor_shapes.py's
    # reflection check) — mypy can't see that through the FixtureConnectorBase/
    # LiveConnectorBase ABC indirection, hence the ignores below.
    connector: SourceConnector
    if mode == "fixture":
        connector = get_fixture_connector_class(source_system)()  # type: ignore[assignment]
    else:
        connector = get_live_connector_class(source_system)(  # type: ignore[assignment]
            base_url="https://unconfigured.invalid"
        )

    source_instance_id = SOURCE_INSTANCE_IDS[source_system]

    async with session_scope() as session:
        run = await sync_source(session, connector, source_instance_id=source_instance_id)

    typer.echo(
        f"sync {source_system} ({source_instance_id}) [{run.status.value}]: "
        f"{run.nodes_upserted} nodes upserted, {run.nodes_tombstoned} tombstoned, "
        f"{run.edges_created} edges created (run {run.id})"
    )


@app.command()
def reconcile(
    context_space: str = typer.Option(
        ..., "--context-space", help="e.g. talentflow/identity"
    ),
) -> None:
    """Confirm a context space's bindings resolve to synced technical
    nodes; report each binding as resolved or unresolved."""
    asyncio.run(_run_reconcile(context_space))


async def _run_reconcile(context_space_id: str) -> None:
    async with session_scope() as session:
        node_repo = NodeRepository(session)
        context_space_repo = ContextSpaceRepository(session)

        space = await get_context_space(context_space_repo, context_space_id)
        if space is None:
            config_path = find_context_space_config_by_id(context_space_id)
            if config_path is None:
                typer.echo(
                    f"no context space {context_space_id!r} found in the database or "
                    "configs/context-spaces/",
                    err=True,
                )
                raise typer.Exit(code=1)
            config = load_context_space_config(config_path)
            await seed_business_tree(node_repo, load_business_tree_config())
            space = await create_context_space(context_space_repo, node_repo, config)

        report = await reconcile_context_space(node_repo, space)

    for result in report.results:
        status = "RESOLVED" if result.resolved else "UNRESOLVED"
        binding = result.binding
        typer.echo(
            f"  [{status}] {binding.capability.value} -> "
            f"{binding.source_system}:{binding.native_container}"
        )

    resolved = sum(1 for r in report.results if r.resolved)
    typer.echo(f"{context_space_id}: {resolved}/{len(report.results)} bindings resolved")


if __name__ == "__main__":
    app()
