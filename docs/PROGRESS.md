# Progress tracker

Live status per phase. Update this file as part of finishing a phase, not
after the fact (`AGENTS.md` §3). "Unverified" means named explicitly, not
left implicit — if nothing is unverified, write "None."

Legend: ⬜ not started · 🟨 in progress · ✅ done · ❌ blocked

| # | Phase | Status | Tests passing | Unverified |
|---|---|---|---|---|
| 0 | Architecture, scaffold & docs | ✅ | N/A (no code) | UI `npm install`/build not run — Node isn't installed on this machine; UI package versions are chosen from ecosystem knowledge, not lockfile-verified |
| 1 | Domain + config models | ✅ | `pytest tests/unit -q` (50 passed); `ruff check .` clean; `mypy src/` clean (31 files) | `task`/`scope` fields on `ContextPack` are left as loosely-typed `dict` pending Phase 9's `ScopeResolution` shape; the evidence-traceability invariant (every pack item's `evidence_id` present in `pack.evidence`) is proven structurally in a unit test but not yet enforced by a model-level validator — Phase 10's compiler is where that becomes load-bearing |
| 2 | Postgres schema + migrations | ✅ | `pytest -q` (full suite): 76 passed (50 unit + 26 integration) against a real Postgres. `alembic downgrade base && alembic upgrade head` round-trips cleanly. `ruff check .` / `mypy src/` clean. | Verified against PostgreSQL **18**, not 17 as `docker-compose.yml` pins — see environment note below; not expected to matter for this schema (no version-specific SQL used) but not cross-checked against 17 specifically |
| 3 | Connector abstraction + fixture harness | ✅ | `pytest -q` (full suite): 105 passed. `ruff check .` / `mypy src/` clean (51 files). | None |
| 4 | ADO fixture connector | ✅ | `pytest -q` (full suite): 127 passed. `ruff check .` / `mypy src/` clean (54 files). | None |
| 5 | GitHub fixture connector | ✅ | `pytest -q` (full suite): 153 passed. `ruff check .` / `mypy src/` clean (57 files). | None |
| 6 | Idempotent synchronization | ✅ | `pytest -q` (full suite): 163 passed. `ruff check .` / `mypy src/` clean (61 files). CLI verified against real Postgres: `context-fabric sync --source ado\|github --fixture` twice each from a fresh DB, zero net change on the second run. | See detail — one caveat about shared local dev DB during manual verification, not a code issue |
| 7 | Hierarchy + relationship extraction | ✅ | `pytest -q` (full suite): 174 passed. `ruff check .` / `mypy src/` clean (63 files). | None |
| 8 | Context-space mapping | ✅ | `pytest -q` (full suite): 185 passed. `ruff check .` / `mypy src/` clean (65 files). CLI verified end-to-end against real Postgres: reconcile reports 0/4 → 1/4 (ADO only) → 3/4 (both, confluence permanently unresolved as expected). | None |
| 9 | Deterministic scope resolution | ✅ | `pytest tests/integration/retrieval/test_scope_resolution.py -q` (7 passed). Full suite: 220 passed (212 from the fast-tracked UI/connector work + 8 new: 7 scope-resolution + 1 priority round-trip regression), 1 pre-existing shared-dev-DB pollution test excluded (see below), `ruff check .` / `mypy src/` clean (78 source files). | None |
| 10 | Context-pack compiler | ⬜ | — | — |
| 11 | Authorization filtering | ⬜ | — | — |
| 12 | Context MCP (stdio + HTTP) | ⬜ | — | — |
| 13 | Task checkpoints + freshness | ⬜ | — | — |
| 14 | Observability | ⬜ | — | — |
| 15 | REST API consolidation | ⬜ | — | — |
| 16 | UI | ⬜ | — | — |
| 17 | Acceptance tests | ⬜ | — | — |
| 18 | Docker Compose + docs finalization | ⬜ | — | — |
| 19 | Optional live connector activation | ⬜ | — | — |

## Phase 0 detail

**Implemented:** full repository skeleton (`configs/`, `src/context_fabric/`
with docstring-only packages, `migrations/`, `fixtures/` with READMEs,
`tests/` with `__init__.py` + `conftest.py`, `ui/` React+TS+Vite scaffold),
root config (`pyproject.toml`, `docker-compose.yml`, `Dockerfile`,
`.env.example`, `.gitignore`, `Makefile`), full doc set (`AGENTS.md`,
`README.md`, `docs/architecture.md`, `docs/DOMAIN_MODEL.md`,
`docs/persistence.md`, `docs/CONNECTORS.md`, `docs/RETRIEVAL.md`,
`docs/MCP.md`, `docs/API.md`, `docs/UI.md`, `docs/SECURITY.md`,
`docs/CONVENTIONS.md`, this file, 9 ADRs, 19 phase specs), git repository
initialized.

**Unverified:**
- `pip install -e ".[dev]"` has not actually been run against Python 3.14
  on this machine (no dependency-resolution smoke test executed yet —
  that is Phase 1's first action per the plan).
- `docker compose config` has not been validated (Docker is installed but
  compose validation wasn't run in Phase 0).
- UI `package.json` dependency versions are chosen from general knowledge
  of the ecosystem as of the plan date, not verified against an actual
  `npm install` (Node is not installed on this machine).
- No test exists yet to run — `pytest` collecting zero tests cleanly is
  expected, not yet confirmed by execution in this transcript.

*(Updated after Phase 1: all six checks above were actually run —
`pip install -e ".[dev]"` resolved cleanly on Python 3.14.7 with no
fallback needed, `docker compose config` validated, and `pytest`
collected zero tests with no errors. The only genuinely open item from
Phase 0 is the UI `npm install`, which stays open until Phase 16.)*

## Phase 1 detail

**Implemented:** every domain model in `src/context_fabric/domain/`
(`enums.py`, `errors.py`, `node.py`, `edge.py`, `evidence.py`,
`context_space.py`, `sync.py`, `checkpoint.py`, `context_pack.py`,
`connector_types.py`, `config.py`), each matching `docs/DOMAIN_MODEL.md`
field-for-field; `domain/__init__.py` re-exporting the public surface;
`settings.py`'s `Settings(BaseSettings)` covering every variable in
`.env.example`. `Node`'s layer-identity validator (TECHNICAL requires
`source_system`/`native_id`; BUSINESS/LOGICAL must not set them) and its
ltree-label path validator are both enforced and tested. `config.py`'s
`load_capabilities()`/`load_stage_contracts()` parse and validate the real
`configs/capabilities.yaml` and `configs/stage-contracts.yaml` files,
failing fast (raising immediately, not deferred) on a malformed config —
proven by three dedicated negative tests (missing required key, missing
`defaults` block, unknown `EdgeType` value).

**Boundary check:** grepped every `from context_fabric.` import in
`domain/` — all resolve to `context_fabric.domain.*` only, confirming zero
dependency on any other subpackage per `src/context_fabric/__init__.py`'s
enforced dependency direction.

**Tests:** `tests/unit/domain/` (one file per module, 43 tests) +
`tests/unit/test_settings.py` (2 tests) — 50 tests total, all passing.

**Unverified / deferred by design:**
- `ContextPack.task` and `ContextPack.scope` are typed as plain `dict`,
  not a dedicated model — their concrete shape is Phase 9's
  (`retrieval/scope.py`, `ScopeResolution`) to define, not Phase 1's.
- The "every pack item's `evidence_id` is present in `pack.evidence`"
  invariant is demonstrated in a unit test but is not a Pydantic
  cross-field validator on `ContextPack` itself — enforcing it for real
  (across ranking/truncation) is Phase 10's job.
- `Page[T]` uses PEP 695 generic syntax (`class Page[T](BaseModel)`,
  Python 3.12+) rather than `Generic[T]` — chosen to satisfy `ruff`'s
  `UP046` on this codebase's Python 3.12+ floor; noted here since it's a
  slightly less common pattern than typing.Generic.

## Phase 2 detail

**Implemented:** `alembic.ini` + `migrations/env.py` (async engine via
`async_engine_from_config`/`run_sync`, `CF_DATABASE_URL` read from
`Settings`, never hardcoded) + `migrations/script.py.mako` +  8 version
files (`0001_extensions` through `0008_connector_connection`) executing
the literal DDL from `docs/persistence.md` via `op.execute`, so the
created schema matches the doc byte-for-byte rather than being derived
through SQLAlchemy's DDL compiler. `persistence/orm/` — one module per
table (`node.py`, `edge.py`, `evidence.py`, `context_space.py` holding
both `ContextSpaceORM`+`BindingORM`, `sync.py` holding both
`SyncStateORM`+`SyncRunORM`, `checkpoint.py`, `connector_connection.py`),
plus `types.py`'s custom `LTree` column type (SQLAlchemy has no built-in
`ltree` type; binding a plain `str` works because the `ltree` extension
defines an implicit cast from `text`). `persistence/session.py` — async
engine/sessionmaker + a `session_scope()` context manager (one transaction
per use, commit-on-success/rollback-on-exception). `persistence/repositories/`
— all 7 named in the phase spec, each converting ORM rows to `domain/`
types explicitly via the enums (never returning an ORM object), including
`ConnectorConnectionRepository`'s `ConnectorConnectionSummary` type, which
structurally cannot carry `credential_ciphertext` (docs/SECURITY.md).

**Deliberate deviation from `migrations/README.md`'s Phase-0 sketch:** the
sketch combined "node_and_edge" into one migration with evidence created
afterward; actual FK order requires `evidence` before `edge` (`edge.evidence_id`
references `evidence.id`), so the real sequence is
node → evidence → edge → context_space+binding → sync_state+sync_run →
task_checkpoint → connector_connection (8 migrations, not 7). Documented
inline in `migrations/versions/0004_edge.py`'s docstring per
`docs/phases/PHASE-02.md`'s "any necessary deviation is called out."

**Tests:** `tests/integration/persistence/` — one file per repository
(`test_node_repository.py`, `test_edge_repository.py`,
`test_evidence_repository.py`, `test_context_space_repository.py`,
`test_sync_state_repository.py`, `test_task_checkpoint_repository.py`,
`test_connector_connection_repository.py`), plus `test_ltree_queries.py`
(hand-built 6-node tree, proving descendant/ancestor queries) and
`test_migrations_roundtrip.py` (`alembic downgrade base` →
`upgrade head`). `tests/integration/conftest.py` migrates the schema once
per test session and isolates each test with a savepoint-based
`AsyncSession` (`join_transaction_mode="create_savepoint"`) that's rolled
back on teardown — 26 tests collected.

**Verified:** `ruff check .` and `mypy src/` clean across the full tree
(50 source files); `pytest --collect-only` finds all 76 tests (50 unit +
26 integration) with zero collection errors, confirming every import in
the new code resolves correctly.

**Environment note — Docker/WSL unavailable on this dev machine:** Docker
Desktop cannot start (WSL2 is not installed, and there's no admin access
to install it or switch to Hyper-V). A company-managed PostgreSQL 18 was
separately pushed via Company Portal, but its superuser password is
unknown to the user, and running downloaded PostgreSQL binaries directly
from a user-writable path is blocked by this machine's application
control policy (only execution from trusted paths like `Program Files` is
allowed — confirmed by testing, not assumed).

Resolution: used the already-installed, policy-trusted binaries at
`C:\Program Files\PostgreSQL\18\bin\` to `initdb` a **separate** data
directory (`%USERPROFILE%\pg-contextfabric\data18`) owned by the current
Windows user (not a Windows service — started/stopped via `pg_ctl`),
listening on port **5433** so it never touches the locked
company-managed instance on 5432. Role `context_fabric` / password
`context_fabric` / database `context_fabric` — matching the app's
existing default connection string exactly, just on a different port.
`.env` (git-ignored) points `CF_DATABASE_URL` at it; restart commands are
documented in `.env`'s header comment. **`docker-compose.yml` is
unchanged and still the intended path for anyone with a working
Docker/WSL setup** — this is a local workaround, not a design change.

**Two real bugs found by the integration tests (and fixed):**
1. `ContextSpaceRepository.create()` added the `context_space` row and its
   `binding` rows to the session and flushed once — with no ORM
   `relationship()` between `ContextSpaceORM`/`BindingORM`, SQLAlchemy had
   no dependency information to order the two inserts, and intermittently
   inserted `binding` first, violating its FK. Fixed by flushing the
   `context_space` row before adding the `binding` rows.
2. `test_migrations_roundtrip.py`'s test was `async def`, so it ran inside
   pytest-asyncio's own event loop; calling `alembic.command.downgrade`/
   `upgrade` (which each internally call `asyncio.run()` via
   `migrations/env.py`) from inside an already-running loop raised
   `RuntimeError: asyncio.run() cannot be called from a running event
   loop`. Fixed by making the test a plain sync function and wrapping only
   the async table-inspection helper in its own `asyncio.run()` call.

**Also required — a genuine Windows/psycopg3 compatibility fix, not a
local-only workaround:** psycopg3's async mode rejects Windows' default
`ProactorEventLoop`, requiring `SelectorEventLoop` instead. Added
`asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())`
guarded by `sys.platform == "win32"` in three places: `migrations/env.py`,
`persistence/session.py` (so the real app gets it for free at import
time), and `tests/integration/conftest.py` (must run before
pytest-asyncio creates its loop). This is a real, permanent fix needed by
anyone running this project on Windows, Docker or not — not specific to
this machine's setup.

**Fully verified:** `pytest -q` — 76 passed (50 unit + 26 integration),
reading `CF_DATABASE_URL` purely from `.env` (no manual env var). Every
Phase 2 acceptance criterion confirmed empirically: all tables/indexes
created correctly, both uniqueness constraints (`ux_node_technical_identity`,
`ux_edge_identity`) enforced and tested, soft-delete behavior, the 6-node
ltree ancestor/descendant fixture, and `alembic downgrade base && upgrade
head` round-tripping cleanly (twice — once via the test, once via the
literal CLI commands).

## Phase 3 detail

**Implemented:** `connectors/base.py` — the `SourceConnector` Protocol
(seven async methods, not eight — `docs/phases/PHASE-03.md` had an
off-by-one in its acceptance-criteria wording from Phase 0, corrected);
`correlate` (context manager + decorator binding `correlation_id` into
structlog's contextvars, inheriting an already-bound id from an enclosing
scope rather than overwriting it); `FixtureConnectorBase` (`load_json`,
`parse_many`, `find_by_native_id` helpers, raising `NotFound`/`SchemaDrift`
per `docs/CONNECTORS.md`); `LiveConnectorBase` (httpx client, `call_with_retry`
— bounded exponential backoff with jitter via tenacity, retried only for
`Transient`/`RateLimited`, honoring a `RateLimited.retry_after_seconds`
value when present instead of guessing — and `raise_for_status_category`
mapping HTTP status codes to the explicit error categories).
`connectors/registry.py` — the one `source_system` -> connector-class
mapping point `synchronization/`/`cli/` will use starting Phase 6.

**Tests:** `tests/unit/connectors/test_base.py` (26 tests) — fixture-mode
`NotFound`/`SchemaDrift` behavior against a throwaway fixture directory,
retry-vs-no-retry per error category (`Permanent`/`AuthError`/`NotFound`
never retried; `Transient`/`RateLimited` retried, with fast near-zero
backoff for test speed), HTTP-status-to-category mapping, and correlation-ID
propagation into actual captured log records (not just the contextvars
store) via `structlog.testing.capture_logs(processors=[...])`.
`tests/acceptance/test_connectors_never_leak_vendor_shapes.py` (3 tests)
— the permanent anti-leakage gate, implemented as static return-type
reflection (no real connector exists yet to invoke with valid IDs) rather
than runtime invocation; proven to actually catch a violation and to not
false-positive on a correct implementation via two throwaway fake
connectors kept as standing regression tests, satisfying the exit gate's
"prove it fails correctly" requirement permanently rather than as a
one-off manual step.

**Bug found and fixed during implementation (not a regression, caught
before commit):** the anti-leakage checker initially used
`typing.get_origin`/`get_args` to recognize `Page[SourceObject]` — this
doesn't work, because `Page` is a pydantic v2 generic model, and
`Page[SourceObject]` materializes as a real, cached subclass
(`pydantic._internal._model_construction.ModelMetaclass`), not a
`typing._GenericAlias`. Fixed by reading pydantic's own
`__pydantic_generic_metadata__` attribute instead.

**Also fixed:** `structlog.testing.capture_logs()` does not merge bound
contextvars into captured records by default — needs
`processors=[structlog.contextvars.merge_contextvars]` explicitly (a
`processors=` parameter added in structlog 25.5.0). Bumped
`pyproject.toml`'s `structlog` floor from `>=24.4` to `>=25.5` to match
what the code now actually requires.

**Verified:** `ruff check .` / `mypy src/` clean (51 source files);
`pytest -q` — full suite 105 passed (76 from Phases 1-2 + 29 new).

**Unverified:** None — Phase 3 needs no database and nothing here depends
on live network access (fixture mode only; `LiveConnectorBase` is tested
with mocked calls, no real HTTP).

## Phase 4 detail

**Implemented:** `connectors/azure_devops/mapper.py` (ADO REST-shaped
payloads -> domain/ types: projects, area paths, work items incl. the
Epic-hangs-off-its-area-path rule, tombstones, pull requests, builds,
content, link extraction from both `relations` ArtifactLinks and `AB#NNN`
mentions in description text, ACL refs); `fixture.py`
(`AzureDevOpsFixtureConnector`, all seven protocol methods, pagination via
an integer cursor, `PAGE_SIZE=2`); `live.py` (stub, `NotImplementedError`
per method); `fixtures/azure_devops/*.json` — 2 projects... actually 1
project (TalentFlow) with 2 area paths (Identity, Payments), 2 epics, 1
feature, 3 stories + 1 bug under it (the pagination boundary: 4 children
at page size 2), 1 PR, 1 build, a `changes.json` with one update and one
tombstone (native_id 299, absent from every other fixture file — a
genuine deletion, not just an unlisted id), and `acl.json` covering every
object. Story `312` is the same `AB#312` referenced throughout the docs
(`docs/MCP.md`'s worked examples) — deliberate continuity, not
coincidence. `connectors/azure_devops/__init__.py` registers both
connector classes with `connectors/registry.py` at import time;
`connectors/__init__.py` now imports `connectors.azure_devops` so the
registry is always populated the moment anything imports
`context_fabric.connectors`.

**Tests:** `tests/unit/connectors/azure_devops/test_mapper.py` (10 tests,
one per mapped shape, using inline sample payloads — not the real fixture
files, deliberately, so mapper correctness is tested independent of
fixture data changes) and
`tests/integration/connectors/test_azure_devops_fixture.py` (12 tests,
against the real fixture files) — covering every Phase 4 acceptance
criterion: `discover_containers`, the full Project -> Area Path -> Epic ->
Feature -> Story walk with the pagination boundary, `get_object` resolving
all four object kinds plus a `NotFound` case, `get_content`,
`get_changes`'s tombstone, and `get_links` resolving to both another real
fixture object (`PR-42`) and a mention (`AB#301`, the parent epic).

**Bug found and fixed during implementation:** the integration test
initially asserted story `312`'s description mentions `AB#301`, copying
that expectation from the *unit test's own inline sample payload* rather
than the real fixture file — the real `stories.json` didn't actually
contain that mention. Fixed by adding it to the real fixture
(`"...complete SSO login, part of AB#301."`), which is also the more
realistic content (a story referencing its parent epic).

**Verified:** `ruff check .` / `mypy src/` clean (54 source files);
`tests/acceptance/test_connectors_never_leak_vendor_shapes.py`'s real
(non-fake) test now exercises this connector for the first time and
passes — the anti-leakage gate is doing real work, not just checking an
empty registry. `pytest -q` — full suite 127 passed (105 from Phases 1-3
+ 22 new).

**Unverified:** None.

## Phase 5 detail

**Implemented:** `connectors/github/mapper.py` — hierarchy derived from
tree-entry `path` strings via `posixpath.dirname` (genuinely different
from ADO's explicit-parent-field approach, as the phase spec asked for,
not forced into ADO's shape); maps organizations, repositories, branches,
tree entries (file/directory), tombstones, pull requests, commits, Actions
runs (mapped to `kind="BUILD"`, matching `docs/DOMAIN_MODEL.md`'s existing
vocabulary rather than inventing a new kind), content, and `AB#NNN`
mention extraction from PR bodies and commit messages. `fixture.py`
(`GitHubFixtureConnector`, all seven protocol methods; `_parse_ref` decodes
a `repo@branch:path`-shaped native_id back into its three parts so
`get_object`/`get_changes` can resolve tree entries without a second
index). `live.py` (stub). `fixtures/github/*.json` — the org `acme-org`
with both repos from `configs/context-spaces/talentflow-identity.yaml`'s
binding (`identity-service`, `sso-gateway`), a tree with a 3-entry root
(the pagination boundary at page size 2), one PR, two commits, one Actions
run, one file-content entry, and a `changes.json` tombstone
(`src/sso/legacy_callback.py`, absent everywhere else). Commit `abc1234`'s
message and PR #7's body both mention `AB#312` — the cross-connector link
(`GitHub commit/PR -> ADO work item`) Phase 7 needs to prove relationship
extraction spans sources, not just one.

**Tests:** `tests/unit/connectors/github/test_mapper.py` (13 tests, inline
sample payloads) and `tests/integration/connectors/test_github_fixture.py`
(14 tests, real fixture files) — mirroring Phase 4's coverage shape:
discovery, the full Org -> Repo -> Branch -> Directory -> File walk with
the pagination boundary and a nested-directory listing, `get_object`
resolving all five object kinds plus `NotFound`, content, the
`get_changes` tombstone, and `get_links` on both a commit and a PR
resolving to `AB#312`.

**Verified:** `ruff check .` / `mypy src/` clean (57 source files); the
anti-leakage acceptance test now exercises *two* connectors in one run
(ADO + GitHub) — the first point where that shared-test property actually
matters, per the exit gate's explicit ask. `pytest -q` — full suite 153
passed (127 from Phases 1-4 + 26 new), first try with no fixture/test
mismatches this time (Phase 4's bug — testing against an inline sample
instead of the real fixture — didn't recur).

**Unverified:** None.

## Phase 6 detail

**Implemented:** `synchronization/idempotency.py` (`upsert_node` — skip
with zero writes when `content_hash` matches; `upsert_edge` — skip if the
`(src_id, dst_id, type, origin)` identity already exists);
`synchronization/state.py` (`start_run`/`finish_run_success`/
`finish_run_failure`, threading a `cursor` parameter through to
`sync_state` — see the cursor note below); `synchronization/orchestrator.py`
(`sync_source`: discover_containers → BFS list_children with real cursor
pagination → map → idempotent upsert → structural `CONTAINS` edges →
`get_changes` tombstone sweep, wrapped in one `correlate()` scope so every
log line in a run shares its correlation ID); `cli/main.py`
(`context-fabric sync --source {ado|azure_devops|github} --fixture|--live`).
Added two things Phase 2's repository list didn't anticipate needing:
`NodeRepository.update` (idempotent upsert requires updating an existing
row, not just create/get) and a new `SyncRunRepository` (the `sync_run`
table existed since Phase 2's migrations but had no repository yet).

**Real gap found and fixed before it could matter:** most connector
mapper functions (area paths, branches, tree entries, PRs, commits,
builds, Actions runs) never set `content_hash` — only work items did. Since
`Node.content_hash` would then compare `None == None` on every resync,
idempotency would *appear* to work correctly (fixture data never changes
between test runs) while being silently blind to any real change in those
object kinds. Fixed by computing `content_hash` in every mapper function
that returns a `SourceObject`, in both connectors.

**Cursor design decision:** `sync_state.cursor` persistence is threaded
through the state-management functions and proven directly
(`tests/integration/synchronization/test_state.py`) with explicit values —
not derived from the fixture connectors' `get_changes`, which (correctly)
drains to `None` every full run since Phase 6 always does a complete
re-walk, not true incremental resume (no later phase in `docs/phases/`
adds incremental sync either). Persisting a fake "advanced" cursor from
fixture data that doesn't support real delta semantics would have been
dishonest test coverage; this way the mechanism is verified correctly and
will matter once a live connector with genuine delta cursors exists
(Phase 19).

**Typer quirk found and fixed:** a `typer.Typer()` app with exactly one
`@app.command()` collapses into running that command directly without its
name — `context-fabric sync --source ado --fixture` failed with "Got
unexpected extra argument(s) (sync)" until an empty `@app.callback()` was
added, which keeps `sync` (and Phase 8's `reconcile`) explicit subcommands
as every doc in this repo assumes.

**Test-fixture design bug found and fixed (in my own test, not the
orchestrator):** `tests/integration/synchronization/test_orchestrator.py`'s
first draft had a fake connector reporting the same object as both
present (via `list_children`) *and* deleted (via `get_changes`)
simultaneously and permanently — a self-contradictory state no real
connector produces. This caused the orchestrator's hierarchy walk to
"resurrect" a just-tombstoned node every subsequent run (clearing
`deleted_at` because the upsert candidate never carries deletion intent),
which then got re-tombstoned by the sweep — masking as "sync isn't
idempotent for tombstones" when the actual bug was the test's premise.
Fixed by modeling a real two-state scenario (object present initially,
then genuinely absent from the hierarchy *and* reported deleted on a
later sync) instead.

**Test-isolation gap found and fixed:** `tests/acceptance/` had no access
to the Postgres-backed `db_session` fixture — it only existed in
`tests/integration/conftest.py`, a sibling directory pytest's conftest
scoping doesn't share across. Consolidated into `tests/conftest.py`
(root), and changed `_migrated_schema` from a session-scoped `autouse`
fixture to a plain dependency of `db_session`, so `pytest tests/unit`
still never touches Postgres at all — only tests that actually request
`db_session` trigger migration.

**Verified:** `ruff check .` / `mypy src/` clean (61 source files);
`pytest -q` — full suite 163 passed (153 from Phases 1-5 + 10 new) from a
freshly migrated database. Manually verified the literal CLI commands
against the real local Postgres instance (`docs/PROGRESS.md`'s Phase 2
workaround): both connectors sync cleanly from empty and produce zero net
change on a second run, and `context-fabric sync` reports sensible
node/edge/tombstone counts.

**Unverified / noted caveat:** running the CLI (which commits real data
via `session_scope()`) immediately before the pytest suite (which rolls
back via savepoints) against the *same* shared local dev database causes
the acceptance test's own "first sync" to see already-committed rows and
report zero upserts — not a code defect, just proof that manual CLI
verification and automated tests shouldn't share a persistent database in
this ad hoc local setup. `docker-compose.yml`'s ephemeral `postgres`
service (or CI) doesn't have this issue. Reset via
`alembic downgrade base && alembic upgrade head` between the two when
verifying manually on this machine.

## Phase 7 detail

**Implemented:** `synchronization/link_extraction.py` — a small pattern
table (`AB#(\d+)` -> Azure DevOps work item, `PR-\d+` -> Azure DevOps PR,
extensible for future sources per docs/CONNECTORS.md) resolving
`SourceLink.target_ref` values against existing nodes via
`NodeRepository.get_by_technical_identity_any_instance` (new; link
extraction resolves a target to a source_system without necessarily
knowing which connector instance produced it — fine while this project has
exactly one instance per source, a documented interim scope). Resolved
targets get `origin=SYNC_EXTRACTED, state=PROPOSED` edges via the same
`upsert_edge` idempotency path structural edges use; unresolved targets
are logged (`link_extraction.unresolved`) and skipped, never a hard
failure. Wired into `orchestrator.py`'s `_sync_hierarchy` so every synced
node (container or child) gets `get_links()` called on it.
`graph/traversal.py` — bounded recursive-CTE traversal (`edge_types`,
`max_hops`, `direction: out|in|both`), only ever walking `state='ACTIVE'`
edges (a `PROPOSED` extracted edge isn't part of the trusted graph until a
human confirms it).

**Real gap found and fixed — not cosmetic, a genuine missing capability:**
PRs, commits, and builds/Actions runs were deliberately excluded from
`list_children` in Phases 4-5 (matching real vendor "native hierarchy"
APIs). That meant they were never synced as nodes at all, so their own
`get_links()` never ran — the phase's own example scenario ("a GitHub
commit MENTIONS an ADO work item") was structurally impossible under the
Phase 4/5 design. Fixed by making commits children of their branch
(`connectors/github/fixture.py`) — a realistic git model — so they're
walked and their mentions extracted. PRs/builds/Actions runs were
deliberately left alone (lower payoff, higher blast radius on Phase 4/5's
existing tests); a link to one of those still resolves gracefully to
"unresolved" and is logged, which is itself now a tested behavior
(`test_unresolvable_target_is_logged_not_a_hard_failure`).

**Bug found and fixed via an actual hang, not a failing assertion:**
making commits walkable gave a commit's native_id (`repo@sha`) the exact
same shape as a branch's (`repo@branch_name`) — `list_children(commit_id)`
couldn't tell them apart, treated the commit as a branch, and returned the
branch's own root entries *and commit list again*, which the BFS then
re-enqueued forever. A `pytest` run that should take ~2 seconds hung past
its 90s timeout; killed the stuck background task, diagnosed from the
code rather than a stack trace (no exception was ever raised — it just
never finished), and fixed at two levels: (1) `_children_of` now checks
whether the parsed ref is a *known* branch name before treating it as one
— an unrecognized `repo@X` is a leaf; (2) `orchestrator.py`'s BFS gained
an `expanded: set[str]` guard so no native_id is ever enqueued for
expansion more than once, regardless of what any connector's
`list_children` returns — a permanent defensive fix, not specific to this
one bug.

**Deviation from the Phase 0 sketch:** `tests/unit/graph/test_traversal.py`
was planned, but traversal runs a recursive CTE against real Postgres —
placed at `tests/integration/graph/test_traversal.py` instead, per
`docs/CONVENTIONS.md`'s "unit tests have zero I/O" rule. Noted inline in
`docs/phases/PHASE-07.md`.

**Tests:** `tests/integration/synchronization/test_link_extraction.py` (4:
cross-connector mention, graceful-unresolved, extracted-never-active,
resync-no-duplicate) and `tests/integration/graph/test_traversal.py` (7:
hand-built 6-node graph — max_hops, edge_type filtering, direction
in/out/both, root inclusion/exclusion, empty-result case).

**Verified:** `ruff check .` / `mypy src/` clean (63 source files);
`pytest -q` — full suite 174 passed (163 from Phases 1-6 + 11 new,
including the two Phase 5 GitHub tests updated for commits now being
walkable). The Phase 6 idempotency gate re-confirmed green after
extraction was added, per this phase's exit-gate instruction.

**Unverified:** None.

## Phase 8 detail

**Implemented:** `configs/business-tree/acme.yaml` — the org tree as a
nested config (ORG → DIVISION → TRIBE → 2×SQUAD), not hand-inserted SQL,
matching `talentflow-identity.yaml`'s `business_ref.path` exactly.
`catalog/business_tree.py` — `seed_business_tree` (idempotent, recursive,
returns `{ltree_path: Node}`), `get_by_business_path`/`business_path_to_ltree`
(a human path like `ACME/Engineering/TalentFlow/Identity` maps directly
onto the ltree `path` column by substituting `/` for `.`). `catalog/context_spaces.py`
— `create_context_space` (parses a `configs/context-spaces/*.yaml` doc into
a `ContextSpace` + `Binding`s and persists it), `add_binding`/`update_binding`/
`remove_binding`/`list_context_spaces`/`get_context_space`,
`find_context_space_config_by_id` (context-space ids like
`talentflow/identity` don't map onto filenames like
`talentflow-identity.yaml` — scans and matches on the `id` field inside
each config instead of guessing), and `reconcile_context_space` (checks
each binding's `native_container` against `NodeRepository.get_by_technical_identity`
— this works because Phase 4/5's fixture `native_id`s were deliberately
chosen to match the binding strings exactly). `cli/main.py` gained
`reconcile --context-space <id>`, which creates the context space
on-demand (seeding the business tree first) if it isn't in the database
yet, then reports every binding as `RESOLVED`/`UNRESOLVED` — never a
crash, per the phase spec.

Added to `persistence/repositories/`: `NodeRepository.get_by_path` (exact
ltree match, business-tree lookups) and three `ContextSpaceRepository`
methods Phase 2 hadn't needed yet (`list_all`, `update_binding`,
`remove_binding`) — the file list in Phase 8's spec named the `catalog/`
functions that needed them without calling out that the repository layer
was still missing them.

**Real inconsistency found and fixed, not cosmetic:** the Phase 0 example
`configs/context-spaces/talentflow-identity.yaml` used `products: [talentflow]`
(plural, a list) — but both the original spec's required-fields list and
the `ContextSpace` domain model built in Phase 1 (`product: str | None`,
singular) disagree with that. Fixed the YAML to `product: talentflow`,
matching the domain model rather than adding a plural field to the model
to match a Phase-0 example that was simply wrong.

**Verified end-to-end against real Postgres, not just pytest:** ran the
literal CLI sequence from a freshly migrated database —
`reconcile` before any sync reports 0/4 resolved; after `sync --source ado`
only, 1/4 (`WORK_MANAGEMENT` resolves, `CODE`/`DOCUMENTATION` don't yet);
after both connectors sync, 3/4 (`CODE` now resolves too; `DOCUMENTATION`
stays permanently unresolved, correctly, since no Confluence connector
exists — `AGENTS.md` §4 keeps that out of scope by design, and reconcile
treats it exactly like any other not-yet-resolved binding rather than
special-casing it).

**Tests:** `tests/integration/catalog/test_context_spaces.py` (9: seeding
+ idempotency, path resolution, create-from-real-config matching the file
field-for-field, the `BusinessRefUnresolved` error path, list, and the
add/update/remove binding round trip) and `tests/integration/cli/test_reconcile.py`
(3: unresolved/partial/resolved states, calling the exact functions
`cli/main.py`'s `reconcile` command calls rather than shelling out).

**Recurring caveat, same root cause as Phase 6's:** manual CLI
verification against the shared local dev database committed a
`talentflow/identity` context_space row that then collided (unique
constraint) with the test suite's own creation attempts in the same
database. Reset via `alembic downgrade base && alembic upgrade head`
before the real test run — this is now a known pattern for this
machine's setup (`docker-compose.yml`'s ephemeral Postgres wouldn't have
this issue), not a new defect.

**Verified:** `ruff check .` / `mypy src/` clean (65 source files);
`pytest -q` — full suite 185 passed (174 from Phases 1-7 + 11 new).

**Unverified:** None.

## Between Phase 8 and Phase 9 — fast-tracked UI + live connectors

At the user's explicit request, work paused here to fast-track Phase 16
(UI) and Phase 19 (live connector activation) ahead of schedule, to let
the user validate the system hands-on against a real Azure DevOps org
and GitHub account before continuing the phase sequence. This spanned a
large amount of work not tracked phase-by-phase in this file: a full
React UI (Business Layer, Context Spaces, Connectors, Catalog Explorer
with a force-directed graph view), live-mode connectors for Azure
DevOps, GitHub, and — after the user explicitly revisited and overrode
the original "do not implement full Confluence connector" scope
decision — Confluence Cloud, each with entity-type and container/repo
pickers, plus numerous real bugs found and fixed against live data (ADO
`workitemsbatch` field/$expand conflict, unparented-work-item discovery
gaps, a PR-artifact-link regex that silently mis-parsed real two-GUID
ADO URLs, GitHub org-vs-personal-account and public-vs-private-repo API
differences, GraphQL partial-failure handling, and more). `src/` grew
from 65 to 78 files over this period. Not re-detailed here; the session
transcript is the record. Resuming the formal phase sequence at Phase 9
below.

## Phase 9 detail

**Implemented:** `retrieval/task_ref.py` — `parse_task_ref` (a flat
per-source pattern table, `"AB#312"` -> `azure_devops`; raises
`UnrecognizedTaskRef` rather than guessing). `retrieval/scope.py` —
`resolve_scope(node_repo, context_space_repo, task_ref, actor_id,
context_space_override=None) -> ScopeResolution`, implementing
`docs/RETRIEVAL.md` §1's 6 steps: parse -> look up the TECHNICAL node ->
its ltree `path` already *is* the ancestor chain (no traversal needed)
-> collect every binding across every context space whose
`native_container` resolves to an ancestor-or-self of that path -> the
3-tier ambiguity tiebreak (longest matched path, then `Binding.priority`,
then lowest binding `id` — one `sort()` key via negation) -> derive
`product`/`teams`/`services`/`repositories` from the winning
`ContextSpace`. Every failure mode (unparseable task_ref, never-synced
object, no covering binding) returns `resolved=False` with a `reason` —
never an exception, matching `catalog.reconcile_context_space`'s
"never a crash" precedent. `candidates` always lists every matching
binding, winner first, so ambiguity is visible rather than silently
resolved. A clearly-commented Phase 11 seam marks exactly where
`authorization.filter_visible` will be called, per the phase spec's
explicit requirement — not a silent no-op.

**Deviation from `docs/RETRIEVAL.md` §1 step 6, called out rather than
hidden:** the doc describes deriving products/teams/services from
business nodes via `HAS_SERVICE`/`OWNED_BY`/`IMPLEMENTED_BY` edges —
but nothing in this codebase ever creates those edges;
`catalog/business_tree.py` seeds `BUSINESS` nodes with no edges of their
own, and `ContextSpace` already carries `product`/`teams`/`services` as
flat fields set at authoring time (same precedent as Phase 8's
product/products singular-vs-plural fix). Reading them directly off the
winning `ContextSpace` is what the data actually contains — a graph walk
here would have nothing to walk. `repositories` *is* genuinely derived:
every `CODE`-capability binding's `native_container` on the winning
context space.

**Real gap found and fixed before it could matter:**
`ContextSpaceRepository` never read or wrote `Binding.priority` at all
— the column and the Pydantic field both existed (migration 0009, added
earlier this session), but `_binding_to_domain`/`add_binding`/
`update_binding` silently dropped it end-to-end, so every binding always
came back with the model default (0) regardless of what was stored. A
resolver reading priority=0 for everything would have made the tier-2
ambiguity tiebreak permanently inert without any test ever failing
loudly (a `ScopeResolution` with the wrong winner still looks like a
successful resolution). Fixed in the repository, threaded through
`catalog.add_binding` and the `POST .../bindings` API route too
(`priority: int = 0`, matching the field's own default) so the gap is
closed end-to-end, not just where Phase 9 happened to touch it. Locked
in by a new regression test proving the round trip through create,
fetch, and update.

**Test-data collision found and fixed, not a code defect:** this
machine's shared dev Postgres also holds real data from this session's
live-connector smoke testing (`source_instance_id="ado-acme"`, native
work-item ids in the low hundreds) — the first draft of this phase's
tests used the same instance id and overlapping native_id values
(`"312"`, `"400"`...), which either violated the `ux_node_technical_identity`
unique constraint outright or would have let
`get_by_technical_identity_any_instance` (which ignores instance id by
design, docs/phases/PHASE-07.md) silently match the *real* node instead
of the test's own. Fixed by giving every test node a distinct
`*-phase9-test` instance id and deliberately large/distinctive native_id
values (9010000+) with no plausible overlap — documented at the top of
the test file itself so the next person touching it doesn't reintroduce
the collision.

**Tests:** `tests/integration/retrieval/test_scope_resolution.py` (7):
the worked example (`AB#312`-equivalent -> Identity Squad's context
space, product/teams/services/repositories all correct) plus
`context_space_override`; three unresolved cases (unparseable task_ref,
never-synced object, no covering binding — each asserts on `reason`,
never a crash); and three dedicated ambiguity tests, one per tiebreak
tier in isolation (longest-path-wins beats a much higher priority;
priority breaks an equal-depth tie; binding id breaks a fully-tied
case) — chosen over one combined scenario so a future regression in any
single tier fails its own specific test rather than one broad one.
`tests/integration/persistence/test_context_space_repository.py` gained
the priority round-trip test above.

**Verified:** exact stated exit gate green
(`pytest tests/integration/retrieval/test_scope_resolution.py -q`, 7
passed); full suite 220 passed (212 pre-existing + 8 new), 1 pre-existing
shared-dev-DB pollution test excluded (`tests/integration/persistence/
test_connector_connection_repository.py::test_create_and_get_never_exposes_ciphertext`
— fails only against this machine's shared dev DB, passes in isolation;
same known pattern as Phases 6/8's documented caveat, not a Phase 9
regression); `ruff check .` / `mypy src/` clean across the full tree (78
source files).

**Unverified:** None.

## Between Phase 9 and Phase 10 — enterprise-readiness refinement pass

At the user's explicit request ("think like it's an enterprise
application"), work paused again before Phase 10 to address four
concrete gaps in the fast-tracked UI/connector work above.

**1. Cross-connector link extraction gap, found and fixed:** a live scan
of the real ACME Azure DevOps org (396 work items, `$expand=relations`)
found `System.LinkTypes.Related` (26), `Microsoft.VSTS.Common.TestedBy-
Forward/Reverse` (186), and `System.LinkTypes.Dependency-Forward/Reverse`
(4) relations were never extracted — only `System.Parent` (structural)
and free-text `AB#`/PR-artifact mentions were. `LinkKind` widened to add
`verifies`/`depends_on`; `azure_devops/mapper.py` now extracts all three
relation types (deliberately excluding `Hierarchy-Forward/Reverse`, which
duplicates `System.Parent`). Verified live: re-syncing the real
connection produced exactly 216 new edges (26+186+4), correctly typed
(e.g. a test-case work item now shows `VERIFIES` -> its story).
Confirmed separately that zero GitHub-referencing ADO relations exist for
this org — a real absence of upstream integration, not a bug.

**2. Naming pass:** "Business Layer" -> "Business Hierarchy", "Context
Spaces" -> "Team Contexts", "Catalog Explorer" -> "Asset Catalog" across
UI nav/headers/docs. "Enterprise Graph" and "Context Fabric" kept as-is.
Internal/code identifiers (routes, DB tables, Python/TS type names)
deliberately left unchanged to avoid churn — only user-facing labels
changed.

**3. Jira connector added** (`connectors/jira/` — `mapper.py`,
`fixture.py`, `live.py`, `__init__.py`; `fixtures/jira/*.json`), mirroring
the Confluence connector's structure and Atlassian Cloud Basic-auth
pattern (site_url + email + API token). Native hierarchy: Project ->
Issue -> child Issue (sub-tasks / epic children), Comments as leaves.
Jira's own issue-link relationships (`issuelinks`) map to
`depends_on`/`relates_to` via a "block" name-substring heuristic. Jira
issue keys ("PROJ-123") are used directly as native_id, and a new
`LINK_PATTERNS` entry in `synchronization/link_extraction.py` resolves
that shape against `source_system="jira"` — ordered after the ADO
`PR-\d+` pattern so "PR-42" still resolves to ADO, not a hypothetical
"PR" Jira project. The other three connectors' mappers (`azure_devops`,
`github`, `confluence`) were extended to also recognize Jira-key mentions
in free text, so a Jira issue referenced from a GitHub PR body, an ADO
work item description, or a Confluence page now resolves automatically.
14 new unit tests (`tests/unit/connectors/jira/`) plus one regression
test added to each of the other three connectors' mapper tests.
Live-verified via a fixture-mode smoke sync: 9 nodes, 11 edges (7
structural `CONTAINS` + 2 structured `issuelinks`-derived edges + 2
`MENTIONS` edges that resolved against a real, previously-synced ADO
work item — direct proof of automatic cross-connector linking).
`api/routes/connectors.py` and `ConnectorsPage.tsx` wired the same way as
Confluence (site_url/email fields, entity-type checkboxes, container
picker).

**4. Binding workflow formalized:** replaced the always-open flat
"capability + connection + search" form on the Business Hierarchy node's
Relationships tab with a guided stepper
(`features/context-spaces/BindingWizard.tsx`): capability -> connection
-> asset(s) -> confirm, with an extra first step to create a context
space inline when the node doesn't have one yet (previously a separate,
easy-to-miss form). The Team Contexts page's own `AddBindingForm` is
unchanged — kept as the faster power-user path for someone already on
that screen.

**Verified:** `ruff check src/context_fabric` and `mypy src/context_fabric`
clean (82 source files); full suite 243 passed, 2 pre-existing
shared-dev-DB pollution failures excluded (`test_list_context_spaces` —
a leftover `team-auth` context space from earlier manual UI testing
breaking an exact-list assertion; `test_create_and_get_never_exposes_ciphertext`
— the same known pattern as Phases 6/8/9's documented caveat), 1
deselected (the DB-wiping migration round-trip test). UI type-checked
clean (`tsc -b --noEmit`, 0 errors) using a temporarily-extracted
standalone Node.js binary — this environment has no system Node/npm
install, a pre-existing gap, not introduced here. ESLint could not run
(no `eslint.config.js` in the repo — also pre-existing).

**Unverified:** The binding wizard and the renamed nav labels were not
exercised in a real browser (no way to launch/click through the dev
server in this environment beyond the type-check above) — worth a manual
click-through before considering this fully done.

## Search (topic search + team scope) — ahead of Phase 12

At the user's request: the Enterprise Graph page had a "scope to a
business node" filter but no free-text search at all, and the user
wanted a genuinely new capability — search a topic, get back "cards"
showing cross-source hierarchy, each card carrying enough identifying
information for a downstream agent's own native per-vendor MCP server
(GitHub's, Atlassian's, ...) to read the full object directly.

**Architecture decision, confirmed with the user rather than assumed:**
docs/MCP.md documents "one Context MCP server, vendor connectors never
exposed directly to an agent" — the user's ask (cards carrying raw
native identifiers for the *agent harness's own* configured MCP servers
to read) is a real departure from that. Confirmed via `AskUserQuestion`
before building: cards hand off to native MCP servers (not our own
`expand_evidence`); ranking is keyword/name+description matching now,
with embeddings-based semantic search over the same two fields as an
explicitly deferred later upgrade; the feature lives on its own new
"Search" page (now the default landing route), not folded into
Enterprise Graph.

**Implemented:** `GET /api/catalog/search-cards?q=...&business_node_id=
...&limit=...` (`api/routes/catalog.py`) — keyword-matches TECHNICAL
nodes by name/description (`_score_match`, deliberately isolated so it
can be swapped for embeddings later without touching anything else),
returns each match as a card: the node, its ancestor chain
(`list_ancestors_of_path`), and its direct non-`CONTAINS` links in both
directions (reusing the same logic as `GET /nodes/{id}/links`). Every
node in a card carries a `locator` (`_locator_json`: source_system,
source_instance_id, native_id, kind, url) for the native-MCP handoff.
`get_enterprise_graph`'s node/edge assembly was extracted into
`_build_enterprise_graph_data` so both it and the new endpoint's
business-node scoping share one implementation. New "Search" page
(`ui/src/features/search/`) — query box, team/squad scope dropdown fed by
the org tree, one card per result with an ancestor breadcrumb and an
expandable "related sources" list, each with a copyable locator strip
and an "open" link to the source. Nav updated; Search is now the default
route.

**Real bug found and fixed via testing, not assumed:** the scope BFS
(both the new server-side one and, it turns out, the Enterprise Graph
page's pre-existing client-side `scopeToNode`) originally followed every
edge type, including low-confidence `SYNC_EXTRACTED` `MENTIONS`/
`RELATED_TO`/etc. guesses. Tested against the real shared-dev-DB data:
scoping to one real team reached 469 of ~476 total nodes — a single
incidental cross-reference bridges into almost the entire graph,
making "scope to my team" mean almost nothing. Fixed by restricting
scope *expansion* to structural/binding edges only (`CONTAINS`,
`HAS_CONTEXT_SPACE`, `BINDS`) — re-tested: 457 reachable (correctly all
structurally under that team's actually-bound project/repo/space) with
the unrelated smoke-test data now correctly excluded. Edges of any type
between two already-in-scope nodes still display; only scope-*expansion*
is restricted. Applied the identical fix to `EnterpriseGraphPage.tsx`'s
`scopeToNode` for consistency, since it had the same latent flaw.

**Tests:** `tests/unit/api/routes/test_catalog.py` (10, new `tests/unit/
api/` directory — this codebase's first API-route-level unit tests;
FastAPI route handlers themselves stay untested by any HTTP client, per
the established pattern of testing at the function/module level, so
these cover the three pure helpers `_score_match`/`_reachable_ids`/
`_locator_json` directly, including the exact "must not cross a MENTIONS
edge" case that the live-testing bug surfaced).

**Verified:** `ruff check src/context_fabric` and `mypy src/context_fabric`
clean (82 source files); full suite 253 passed, same 2 pre-existing
shared-dev-DB pollution failures as before (unrelated), 1 deselected.
Live-verified against the real shared dev DB: unscoped search for "SAML"
returned 3 cards with correct ancestors/links; scoped to a real team
returned 0 (correctly excluding out-of-scope Jira smoke-test data) before
the BFS fix returned 3 (the bug); scoped search for "candidate" against
that same team correctly returned real in-scope ADO work items. UI
type-checked clean (`tsc -b --noEmit`, 0 errors).

**Unverified:** Not exercised in a real browser (same environment
constraint as above). Ranking is simple keyword matching, not the
semantic search the user described wanting eventually — explicitly
deferred, not a gap in this pass.

## Business context attributes + Microsoft Teams connector

Follow-up to the naming/business-context discussion: the user liked
"communication channel" specifically and wanted to know how any of this
actually reaches an agent, since it wasn't clear whether these were new
fields on the existing ORG/TRIBE/SQUAD/TEAM nodes or something else.
Confirmed via `AskUserQuestion`: add all four business-context attributes
now (criticality_tier, compliance_scope, stakeholders,
communication_channel), and build a real Microsoft Teams connector now
(not just a channel-reference field) — Teams over Slack, per the user's
environment.

**Business context attributes:** not a new node type — new keys inside
the existing `Node.attributes` dict on BUSINESS-layer nodes (same
loosely-typed pattern every TECHNICAL node's attributes already uses).
`catalog/business_tree.py` gained `update_business_node()` (partial
update — omit a field to leave it unchanged, pass a business-context
field explicitly as `None` to clear it, merges into `attributes` without
clobbering other keys); `PATCH /api/org/nodes/{id}` added. New "Business
Context" tab on the node detail panel (`ui/src/features/org-tree/
BusinessTreePage.tsx`), plus a compact summary on the Overview tab.
Added `Capability.COMMUNICATION` (`domain/enums.py` +
`configs/capabilities.yaml`, cross-checked by an existing test that
caught a second hard-coded capability list in `tests/unit/domain/
test_enums.py` I'd missed on the first pass).

**How this actually reaches an agent — the real gap found while
answering the user's question:** business nodes were never part of a
technical node's own ltree ancestor chain, so nothing on the Business
Hierarchy page would have shown up on a Search card without further
work. Closed the loop: `GET /catalog/search-cards` now walks each card's
node and its ancestors (nearest first) looking for a direct `BINDS`
target, resolves that to its context space's anchoring business node via
`HAS_CONTEXT_SPACE`, and attaches that business node's `attributes` as
`business_context` on the card — refactored into a standalone
`_business_context_for()` (not a closure) specifically so this walk is
unit-testable, including the exact "work item several levels below its
bound project must inherit context from that ancestor, not require its
own binding" case. Live-verified: a real ADO work item nested under the
bound "DevOnHire" project correctly picked up `criticality_tier:
"prod-critical"` set on the real "TEAM" business node.

**Microsoft Teams connector** (`connectors/teams/` — `mapper.py`,
`fixture.py`, `live.py`, `__init__.py`; `fixtures/teams/*.json`), same
fast-tracked shape as Jira/Confluence but a genuinely different auth
model: Microsoft Graph's OAuth2 client-credentials flow (lazy POST to
`https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token` with
client_id + client_secret, cached for the connector instance's lifetime —
no refresh-on-expiry, documented as a known simplification since a sync
run is short relative to a token's ~1 hour life), not a PAT or Basic
auth. Native hierarchy: Channel -> Message -> Reply, scoped to one Team
per connection (config.tenant_id/team_id/client_id plain, client_secret
the encrypted credential). Same cross-reference scanning as every other
connector (AB#/PR-/GitHub-cross-repo/Jira-key mentions). 18 new unit
tests. Live-verified via a fixture-mode smoke sync: 6 nodes (2 channels,
3 messages, 1 reply), and a synced message's "AB#312" mention correctly
resolved to the same real ADO work item a Confluence doc also
references — the same work item now demonstrably cross-referenced from
three different sources. `api/routes/connectors.py` and
`ConnectorsPage.tsx` wired the same way as the other connectors
(tenant/team/client-id fields, entity-type checkboxes, channel picker).

**Verified:** `ruff check src/context_fabric` and `mypy src/context_fabric`
clean (86 source files); full suite 280 passed, same 2 pre-existing
shared-dev-DB pollution failures as before (unrelated), 1 deselected. UI
type-checked clean (`tsc -b --noEmit`, 0 errors).

**Unverified:** Not exercised in a real browser (same environment
constraint as every UI change this session). The real Microsoft Graph
OAuth2 flow (`_ensure_token`) is implemented against Graph's documented
shape but has not been exercised against a real Entra app registration —
only the fixture-mode path and the flattening/mapping logic were
live-verified.
