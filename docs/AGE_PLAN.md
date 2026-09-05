# Apache AGE Support — Implementation Plan

Status: v7 (2026-09-05) — implementation-ready; architecture approved
across four review rounds; delivery/CI/git-workflow, implementation
checklist, and explicit three-tier testing strategy added
Scope: add Apache AGE as a graph-database sink, with cost-efficient sync,
multi-branch support, a multi-repo registry with ownership, and storage
optimization. Primary consumers are external agents (code review, code
quality) that write their own Cypher against the AGE instance.

## Background

graphify already has a graph-DB export pattern: `push_to_neo4j` and
`push_to_falkordb` in `graphify/exporters/graphdb.py`, wired to
`graphify export neo4j|falkordb --push URI` in `cli.py`. Both do a
full-graph upsert with one round trip per node/edge.

Relevant existing machinery:

- `graphify/global_graph.py` — local multi-repo merge into
  `~/.graphify/global-graph.json` with `repo_tag` node-id prefixing and a
  JSON manifest (no owner/branch tracking yet).
- `graphify/analyze.py::graph_diff(G_old, G_new)` — node/edge add/remove
  deltas (no property-change detection yet; must be extended, see below).
- `graphify/cache.py` — content-hash extraction caching (client-side
  incremental extraction is already solved).
- `graphify/pg_introspect.py` + the `postgres` extra — psycopg is already
  an established optional dependency.
- `graphify/serve.py`, `query/path/explain` — retrieval currently loads
  `graph.json` into NetworkX.

## Design decisions (settled)

1. **Materialized graphs, not delta overlays, at query time.** Agents write
   plain Cypher; no masking predicates (`branches`/`removed_in` properties)
   ever appear in the queryable graphs. Deltas are purely a transport and
   storage mechanism, invisible to consumers.
2. **AGE holds durable repository graphs plus a small ephemeral cache of
   actively queried branch graphs.** One durable AGE graph per repo (the
   default branch), named from the repo identity; one AGE graph per
   *materialized* branch, named `<graph_name>__<branch>` (sanitized, with a
   hashing fallback for Postgres's 63-byte identifier limit). Branch graphs
   are a **cache**: only active, queried branches become AGE graphs; all
   other branches remain diff rows.
3. **Lazy materialization via supported Cypher writes only.** A branch graph
   is materialized on first query by creating the graph and rehydrating it
   through batched Cypher writes from a logical base snapshot plus the
   branch diff. **Never** by copying AGE-owned label tables
   (`INSERT ... SELECT`): AGE reserves graph namespaces and does not
   support direct DML/DDL in them. graphify stays independent of AGE's
   internal schemas.
4. **Branch diffs are commit-anchored to an immutable base.** A diff is
   computed against, and records, a pinned `base_commit_sha` (the
   merge-base with the target branch) and `base_snapshot_id`. Materialization
   hydrates from that snapshot and applies the diff to `head_commit_sha`.
   Never diff against, or hydrate from, "the current default-branch graph"
   unless it is verified to be exactly that base commit — otherwise branch
   graphs silently rot as the default branch moves.
5. **PostgreSQL (plain SQL) is the authoritative store** for the registry,
   ownership metadata, commit snapshots, branch diffs, and quality
   findings. AGE graphs are derived, rebuildable artifacts.
6. **A shared central Postgres/AGE instance** is the meeting point for
   decentralized repos; each contributor pushes their own repo. Trusted
   direct PostgreSQL/AGE users and agents may query any graph; **ownership
   governs frontend discovery and retrieval**, not database access.
7. **Lean property set by default.** Push only what agents query on;
   presentation-only properties stay in `graph.json`.

## Cypher-facing schema contract

Because agents' queries are an API, the emitted schema is documented and
test-pinned, identical across the neo4j/falkordb/age exporters.

- **Node label**: sanitized `file_type` capitalized (fallback `Entity`).
- **Relation type**: sanitized upper-snake relation (fallback `RELATED_TO`).
- **Node properties** (default lean set): `id`, `label`, `source_file`
  (repo-relative), `source_location`, `community`, plus structural metrics
  below. `--full-props` pushes everything scalar.
- **Edge properties**: `relation`, `confidence`
  (`EXTRACTED|INFERRED|AMBIGUOUS`).
- **Structural metrics stamped at push time** (cheap, already computed or
  trivially derived): `degree`, `is_god_node` (from `analyze.god_nodes`),
  `in_cycle` (from `find_import_cycles`). Evolving quality *rules* do NOT
  become node properties — they go to `graphify_quality_findings` (below).
- Every registry row and snapshot records `graphify_version`,
  `schema_version`, and `extraction_config_hash`, so agents (and the
  materializer) can detect incompatible graphs.

Deliverable: `docs/AGE_SCHEMA.md` + a schema-pinning test. **Pinning
mechanism**: "identical across exporters" cannot be pinned by live output
(neo4j has no integration test at all), so the property/label/relation
selection logic is factored into one shared pure function in `graphdb.py`
used by all three pushers, and *that* function is pinned by a plain unit
test in the default CI suite. Each backend's live suite then only verifies
that the backend faithfully writes the shared shape.

## Registry and authoritative SQL schema

Repository identity is a stable `repository_id` (UUID) keyed off the
normalized remote URL — `repo_tag` is a display/prefix name, not a global
primary key (tags can collide or be renamed across a decentralized fleet).

```sql
graphify_repos(
  repository_id UUID PRIMARY KEY,
  remote_url TEXT UNIQUE,          -- normalized
  repo_tag TEXT,                   -- display name / node-id prefix
  owner_id TEXT,                   -- frontend scoping; see Ownership
  default_branch TEXT,
  age_graph_name TEXT,             -- durable default-branch graph
  created_at, updated_at TIMESTAMPTZ
)

graphify_snapshots(                -- logical base snapshots (see Phase 3)
  snapshot_id UUID PRIMARY KEY,
  repository_id UUID REFERENCES graphify_repos,
  commit_sha TEXT,
  kind TEXT,                       -- 'checkpoint' | 'delta'
  parent_snapshot_id UUID,         -- for deltas
  payload JSONB,                   -- or object-storage pointer
  graphify_version TEXT,
  schema_version TEXT,
  extraction_config_hash TEXT,
  created_at TIMESTAMPTZ
)

graphify_branches(
  repository_id UUID REFERENCES graphify_repos,
  branch TEXT,
  base_commit_sha TEXT,            -- merge-base with target branch
  head_commit_sha TEXT,
  base_snapshot_id UUID REFERENCES graphify_snapshots,
  age_graph_name TEXT,             -- NULL until materialized
  materialized BOOLEAN,
  last_push_hash TEXT,
  pushed_by TEXT,
  pushed_at TIMESTAMPTZ,
  bytes_used BIGINT,               -- sum of pg_total_relation_size over the
                                   -- relations in the graph's namespace
                                   -- (discovered via AGE metadata/pg catalogs;
                                   -- the function itself is per-relation)
  graphify_version TEXT,
  schema_version TEXT,
  extraction_config_hash TEXT,
  PRIMARY KEY (repository_id, branch)
)

graphify_branch_revisions(          -- one generation per diff chain
  repository_id UUID,
  branch TEXT,
  generation BIGINT,
  base_commit_sha TEXT,
  head_commit_sha TEXT,
  active BOOLEAN,                  -- rebase/force-push creates a new
  created_at TIMESTAMPTZ,          -- generation and marks the old one
  PRIMARY KEY (repository_id, branch, generation),   -- superseded
  FOREIGN KEY (repository_id, branch) REFERENCES graphify_branches
)
-- Exactly one active generation per branch, enforced in the database so a
-- concurrent or failed rebase can never leave materialization ambiguous:
-- CREATE UNIQUE INDEX graphify_one_active_branch_revision
--   ON graphify_branch_revisions (repository_id, branch) WHERE active;

graphify_branch_diff(
  repository_id UUID,
  branch TEXT,
  generation BIGINT,               -- which revision chain this belongs to
  seq BIGINT,                      -- ordered within the generation
  from_commit_sha TEXT,            -- the commit transition this diff row
  to_commit_sha TEXT,              -- belongs to (validates replay)
  kind TEXT,                       -- node_add|node_del|node_change|edge_add|edge_del|edge_change
  payload JSONB,                   -- REVERSIBLE: old AND new values; full payload on delete
  PRIMARY KEY (repository_id, branch, generation, seq),
  FOREIGN KEY (repository_id, branch, generation)
    REFERENCES graphify_branch_revisions
)

graphify_quality_findings(
  repository_id UUID,
  commit_sha TEXT,
  node_id TEXT,
  rule TEXT,
  severity TEXT,
  evidence JSONB,
  tool_version TEXT,
  created_at TIMESTAMPTZ
)
```

Diffs must be **reversible and complete**: property changes carry both old
and new values; deletions carry the full removed payload. "Current state +
diffs reconstruct any point in time" holds only under this rule, backed by
periodic checkpoints in `graphify_snapshots`.

**Snapshot uniqueness**: `graphify_snapshots` carries a unique constraint on
`(repository_id, commit_sha, kind, schema_version, extraction_config_hash,
graphify_version)` — `kind` is part of the key because a commit may first be
stored as a delta and later also gain a reconstructed checkpoint; both
records are immutable and coexist. `base_snapshot_id` resolution **prefers
the checkpoint** for a commit when one exists, falling back to
delta-chain reconstruction otherwise, and never selects across a mismatched
schema version or extraction config.

## Ownership

- Ownership governs **frontend discovery and retrieval** (repository
  listing, graph selection, result scoping by authenticated `owner_id`;
  global cross-repository graphs are owner-scoped or owner-filtered).
  Trusted direct PostgreSQL/AGE users and agents may query all graphs.
- **Owner resolution at push time**: explicit `--owner` flag → owner
  segment of the git remote URL (`github.com/<owner>/<repo>`) →
  `git config user.email`. `pushed_by` (who ran the sync) is recorded
  separately from `owner_id`.
- Ownership lives **only in `graphify_repos`** — it is not stamped into the
  graph. The graph schema defines no repository root node, and no implicit
  one may be relied on; agents needing owner context join through the
  registry.

## Phases (in implementation order)

### Phase 0 — AGE compatibility spike

Validate, against a live Dockerized AGE, before building on assumptions:

- target AGE + PostgreSQL versions; psycopg (v3) client- vs. server-side
  binding against `cypher()`;
- agtype parameter maps via **explicit `PREPARE`/`EXECUTE`** (AGE documents
  parameters as usable through prepared statements only; prepare once per
  pooled connection — prepared statements are session-scoped);
- `UNWIND $rows` + `MERGE` behavior and batch sizing;
- transactional write behavior; index options on AGE label tables that do
  not require touching AGE internals.

Deliverable: a spike test file that becomes the seed of the **live
integration suite**, following the exact pattern already established by
`tests/test_falkordb_integration.py` — there is no docker-compose
precedent in this repo (only a single `Dockerfile` for the MCP server), and
no neo4j integration test even exists, so AGE should not introduce a new
fixture mechanism:

- a `docker run` one-liner documented in the test module's docstring, not
  a compose file or a shell script — with an **explicitly pinned
  `apache/age` image tag** (the version-targeting decision of this spike),
  so the suite doesn't drift with upstream releases;
- `pytest.importorskip("psycopg")`;
- a service-identifying connection probe (not just a port/ping check) so a
  stray Postgres without the AGE extension loaded fails closed into a
  skip, not a false test failure — e.g. attempt `LOAD 'age'` or query
  `ag_catalog.ag_graph` and skip on error;
- host/port/db/user/password overridable via env vars
  (`AGE_HOST`/`AGE_PORT`/... matching the `FALKORDB_HOST`/`FALKORDB_PORT`
  naming convention);
- a fixture that drops the test graph before and after, for a clean slate;
- **no CI involvement** — like the falkordb suite, this is a manual,
  opt-in test for a dev who started the container locally; the default
  `ci.yml` provisions no external services and stays untouched. Mocked
  unit tests remain for CLI wiring and sanitization only.

### Phase 1 — `push_to_age()` exporter (full, deletion-safe push)

- New function in `graphify/exporters/graphdb.py`, sibling of the neo4j /
  falkordb pushers; re-exported from `graphify/export.py`.
- Connect with psycopg. Session setup: `LOAD 'age'; SET search_path =
  ag_catalog, "$user", public;`. Create the graph via
  `SELECT create_graph(...)` if absent (check `ag_catalog.ag_graph`).
- Writes use **prepared fixed Cypher statement shapes** per connection,
  passing an agtype parameter map of batch rows, `UNWIND $rows` (~500
  rows/statement), grouped by fixed safe node label / edge relation type.
  Bind values only; derive graph names, labels, and relations through the
  controlled sanitizer mappings (`_safe_label` / `_safe_rel`). Single
  transaction per push.
- **Deletion-safe sync** — reconcile in place: after upserts, delete
  nodes/edges absent from the incoming graph inside the same transaction.
  PostgreSQL transaction isolation ensures readers see either the prior
  consistent graph or the fully reconciled graph, never a partial sync.
  Handle label changes explicitly: a logical node whose `file_type` changed
  must not survive under two AGE labels, so delete it under the old label as
  part of reconciliation. Full rebuild is reserved for recovery or an
  incompatible schema migration.
- Lean property set by default; `--full-props` flag for everything scalar.
- CLI: `graphify export age --push postgresql://user:pass@host/db
  [--graph-name NAME] [--full-props]`; password via `AGE_PASSWORD` or
  standard `PGPASSWORD`.
- Packaging: `age = ["psycopg[binary]"]` extra; add to `all`.
- Docs: `AGE_SCHEMA.md`, README export section, `graphify export` help.

### Phase 2 — Repository identity, ownership metadata, registry

- Create the SQL schema above (`graphify_repos`, `graphify_branches`,
  `graphify_snapshots`, `graphify_branch_revisions`,
  `graphify_branch_diff`, `graphify_quality_findings`, including the
  one-active-revision partial unique index) with a versioned migration.
  Registry tests are **tier 2** (plain Postgres, no AGE required — see
  Testing strategy).
- Push path registers/updates the repo (normalized remote URL →
  `repository_id`), resolves owner, records versions and
  `extraction_config_hash`.
- Branch name from `git rev-parse --abbrev-ref HEAD`; commit SHAs from git
  at push time.
- Cross-repo edges (already computed locally by `cross_repo_calls.py`) go
  into a small `global` AGE graph referencing `repo_tag`-prefixed ids,
  owner-scoped for frontend retrieval.
- Agents discover which graph to query via the registry.

### Phase 3 — Durable default-branch graph + logical snapshots

- Each default-branch push also records a logical snapshot entry:
  periodic full checkpoints (graph.json-style payload, in Postgres JSONB or
  object storage) plus ordered, reversible deltas between them — enough to
  reconstruct the graph at any recorded commit. This is the immutable base
  the branch machinery pins against; it is **not** an AGE graph copy.
- Extend `graph_diff()` to report **property changes with old and new
  values** and to include full payloads for removals (reversibility).
- Incremental default-branch sync: diff against the last-pushed snapshot;
  emit only batched MERGEs / SETs / DETACH DELETEs. No prior snapshot →
  full deletion-safe push. Typical edit-cycle syncs become O(changed
  files).

### Phase 4 — Branches: commit-anchored diffs, lazy hydration, reaping

- **Initial push for a non-default branch**: client determines the
  merge-base (`base_commit_sha`), obtains/creates the matching
  `base_snapshot_id` (see below), computes
  `graph_diff(base_snapshot_graph, branch_graph)`, and uploads ordered diff
  rows. O(diff) over the wire; no AGE graph created yet.
- **Subsequent pushes are incremental**: each normal push appends
  `head_n → head_n+1` diff rows to the existing chain (never a repeated
  `base → latest_head` diff — that would duplicate operations and corrupt
  replay/materialization). On **force-push or rebase** (detected by
  `head_commit_sha` no longer being an ancestor of the new head, or a
  changed merge-base): recompute the merge-base, create a **new generation**
  in `graphify_branch_revisions`, mark the old one inactive (superseded, not
  overwritten — history stays auditable), and start the new chain from the
  new base snapshot. Each diff row records its `from_commit_sha` /
  `to_commit_sha`, so replay can validate every transition.
- **Obtaining a missing base snapshot** (`base_commit_sha` predates
  retained checkpoints or AGE adoption), in order:
  1. reconstruct it from the nearest retained checkpoint plus the ordered
     reversible deltas between it and `base_commit_sha`, and store it as a
     checkpoint; else
  2. create a temporary git worktree at `base_commit_sha`, run graphify
     extraction there (cache-assisted), and store the result as a
     checkpoint in `graphify_snapshots`.
- **Materialization on first query** (`graphify age materialize` verb or a
  server-side helper): create the AGE graph, **rehydrate via batched
  prepared Cypher writes** from the pinned base snapshot, then replay the
  ordered diff chain to `head_commit_sha`. Set `materialized` and
  `age_graph_name`. Refuse to materialize across mismatched
  `schema_version` / `extraction_config_hash`.
- **Serialization**: the materializer takes a PostgreSQL advisory lock keyed
  by `(repository_id, branch)`, re-reads registry state inside the
  transaction, and only then creates/hydrates the AGE graph — so two agents
  requesting the same unmaterialized branch concurrently do one hydration,
  not two. The reaper acquires the same lock, so it cannot drop a graph
  mid-hydration or race an in-flight materialization. The lock cannot
  protect arbitrary direct-agent Cypher queries from a reap, so branch
  graphs are reaped only after a **generous inactivity grace period**, and
  the consumer contract documents that clients must re-resolve the graph
  through the registry (and re-materialize if needed) when a query fails
  because the graph was reaped.
- **Subsequent pushes to a materialized branch** apply the incremental diff
  directly (batched MERGE / SET / DETACH DELETE) and update
  `head_commit_sha`. The AGE mutation, the new diff-chain rows, the branch
  head SHA, and materialization metadata all commit in **one PostgreSQL
  transaction** — the registry can never claim a head commit the AGE graph
  does not actually contain after a failed write.
- **Reaper**: drop branch graphs via `drop_graph` (returns the space) on
  merge, closure, or inactivity/size threshold; size-aware via
  `bytes_used`. The diff rows and snapshots remain — a reaped branch can
  always be rehydrated.
- **Branch-diff rows double as review-agent input**: the changeset vs. base
  is queryable in plain SQL, so "what changed structurally in this PR"
  comes for free. AGE also allows calling `cypher()` on two graphs in one
  SQL statement and joining the results, enabling cross-branch structural
  comparison queries directly.

### Phase 5 — Agent contract: pinned queries and fixtures

For the **review agent**, define, document, and test:

- branch-diff seed selection: changed files, symbols, deleted symbols, and
  changed edges;
- traversal direction per relation type; reverse-dependency traversal for
  callers and dependents;
- required evidence in results: path, source locations, relation types,
  confidence, and branch/base commit;
- traversal depth caps, result limits, and statement timeouts.

For the **quality agent**: structural properties (`degree`, `is_god_node`,
`in_cycle`) live on nodes; rule-based findings are written to
`graphify_quality_findings` so rules can evolve without turning node
properties into an unstable catch-all.

Deliverables: pinned example queries in `docs/AGE_SCHEMA.md` + integration
fixtures in the live suite that execute them against a seeded instance.
Seeding uses `tests/fixtures/extraction.json` (the same fixture the
falkordb suite builds from); if it proves too small to exercise depth
caps, result limits, or statement timeouts meaningfully, grow a dedicated
larger fixture rather than weakening those assertions.

### Phase 6 (optional) — AGE-backed retrieval inside graphify

Lower priority now that the primary consumers query AGE directly.

- Thin backend abstraction for `query/path/explain` and `serve.py`:
  file-backend (current) vs. AGE connection.
- Strategy: fetch the candidate subgraph from AGE, pull into NetworkX, and
  reuse the existing scoring/formatting — do not reimplement scoring in
  Cypher; behavior stays identical to the file backend.

## Storage optimization summary

1. **Graph count is the biggest lever**: lazy materialization + reaping
   means durable default-branch graphs are the only full AGE copies that
   always exist; most branches live only as diff rows.
2. **Row size**: lean default property set; repo-relative `source_file`;
   skip empty/derivable properties (each property rides in AGE's agtype
   column, so property count multiplies storage directly).
3. **Indexes**: only on what agents filter by (`id`, `source_file`), via
   supported mechanisms validated in the Phase 0 spike.
4. **Visibility**: `bytes_used` in the registry; retention can be
   size-based as well as time-based.
5. **History without AGE copies**: checkpoints + ordered reversible diffs
   in SQL reconstruct any recorded commit; never store old AGE graph
   copies.

## Consumer contract (review / quality agents)

Agents live outside graphify and need only:

- `psycopg` + the connection string,
- the registry tables for discovery (`graphify_repos`,
  `graphify_branches`, `graphify_branch_diff`,
  `graphify_quality_findings`),
- `docs/AGE_SCHEMA.md` for the node/edge schema and pinned queries,
- optionally `graphify age materialize` (or the server-side helper) before
  querying a not-yet-materialized branch.

Clients must treat branch graphs as a cache: on a query failing because the
graph was reaped, re-resolve `age_graph_name` through the registry and
trigger re-materialization rather than retrying blindly.

## Testing strategy

Three tiers, not two — and the design principle that follows from them:
because tier 3 never runs in CI, **maximize what tiers 1–2 can cover** by
structuring the code so that planning/diffing logic is pure and only thin
adapters touch AGE.

**Tier 1 — pure-Python tests, default blocking CI (no database).** This is
where the highest-risk *logic* is tested, and most of it needs no AGE:

- `graph_diff()` reversibility: apply a diff forward, apply its reverse,
  assert graph equality (property-based testing is cheap and appropriate
  here);
- diff-chain replay: replay ordered diff rows onto a NetworkX graph and
  compare against the expected head graph; validate
  `from_commit_sha`/`to_commit_sha` transition checking rejects
  out-of-order and cross-generation rows;
- merge-base / force-push / rebase detection against a throwaway git repo
  created in a tmpdir (git *is* available in CI);
- graph-name sanitization and the 63-byte hashing fallback;
- the shared property/label/relation selection function (the schema pin,
  above) and lean-vs-`--full-props` selection;
- CLI wiring and env-var credential resolution (mocked connection).

To make this possible, reconcile and materialization are implemented as
**pure planners** (graph/diff in → ordered statement batches out) with a
thin executor that sends batches to AGE. The planner is tier 1; only the
executor needs tier 3.

**Tier 2 — plain-Postgres tests (live service, but no AGE required).**
Registry migrations, the partial unique index on
`graphify_branch_revisions`, the snapshot-uniqueness constraint,
generation supersession, and owner/identity upserts are plain SQL. Their
probe checks for reachable Postgres only — not for the AGE extension — so
they also pass against the AGE container without exercising it, and their
skip condition is deliberately weaker than tier 3's.

**Tier 3 — live AGE integration suite (opt-in, manual, never in CI).**
Everything mocks genuinely cannot validate: agtype/prepared-statement
behavior, `UNWIND` batching, transactional rollback, label-table behavior,
`create_graph`/`drop_graph`, advisory-lock serialization, and the
executor's faithful application of tier-1-planned batches. Follows
`tests/test_falkordb_integration.py`'s pattern exactly (importorskip +
service-identifying probe + env-var overrides + clean-slate fixture), with
one addition: the `docker run` line in the docstring **pins an explicit
`apache/age` image tag** (chosen in Phase 0 as the targeted AGE/PostgreSQL
version) so results don't drift with upstream releases.

**Accepted risk and mitigation.** The deletion-safe reconcile executor,
transactional atomicity, replay-to-AGE, locking, and reaping are exercised
only by tier 3, which no automation runs — the same trade the falkordb
suite makes, but over far more machinery. Mitigation: any PR touching AGE
write paths must state in its description that the live suite was run
locally against the pinned image tag, and with what result. A non-blocking
scheduled CI workflow with an AGE service container is a possible later
addition (Open questions) but is explicitly not required by this plan.

**Concurrency tests (tier 3)** are designed around determinism, not
timing: one connection holds the advisory lock while a second asserts
`pg_try_advisory_lock` fails and that the materializer takes its
re-read-then-hydrate path; no sleep-based races.

## Delivery, CI, and git workflow

This repo's contribution conventions (README "Contributing" section,
`AGENTS.md`) apply to this work like any other change; the points below are
the ones specific to AGE that aren't automatically obvious from those docs.

- **Fork/branch model**: `origin` is a fork (e.g. `e4c5/graphify`) of
  upstream `safishamsi/graphify`; `v8` is the active-development branch on
  both. Sync local `v8` to `origin/v8` (which tracks upstream) before
  cutting each phase's branch, and cut **one branch per phase** (e.g.
  `age-phase0-spike`, `age-phase1-exporter`) rather than one long-lived
  branch for the whole plan — phases are independently reviewable PRs, and
  Phase 1 alone (exporter + CLI + packaging + docs) is already PR-sized on
  its own.
- **Commit style**: `feat: ...` / `fix: ...` / `docs: ...`, per phase deliverable
  where practical (e.g. `feat: add push_to_age() exporter`,
  `docs: add AGE_SCHEMA.md`).
- **Before opening any PR**: `uv run pytest tests/ -q` must pass. The
  live-AGE suite follows `tests/test_falkordb_integration.py` exactly:
  `pytest.importorskip` + a service-identifying connection probe that
  skips (not fails) when no live AGE instance is reachable, so it is a
  silent no-op in the existing `ci.yml`, which provisions no external
  services and needs no changes. No neo4j integration test or
  docker-compose fixture exists in this repo to mirror instead — AGE
  should not introduce either.
- **CI parity commands** (`uv sync --all-extras --frozen`, the blocking
  pytest run, the `tools.skillgen` checks, `graphify --help`/`install`
  smoke tests) must keep passing with the new `age` extra installed, on
  Python 3.10 and 3.12.
- **Packaging overlap**: `age = ["psycopg[binary]"]` duplicates the
  `psycopg[binary]` pin already in the `postgres` extra
  (`graphify/pg_introspect.py`). Decide explicitly whether `age` depends on
  `postgres` or repeats the pin independently (matching the existing
  `postgres` extra's inline comment style explaining the "why"), so
  `uv sync --all-extras` doesn't silently drift the two out of sync over
  time.
- **Docs**: update `ARCHITECTURE.md`'s module-responsibility table for
  every phase that adds a module or registry table (exporter in Phase 1,
  registry/migration in Phase 2, snapshot machinery in Phase 3, branch
  materializer/reaper in Phase 4), the same way any other module addition
  would be documented there.
- **No test-fixture obligation from the "new language extractor" rule**
  (`tests/fixtures/` + `tests/test_languages.py`) — AGE is an exporter, not
  an extractor — but the same spirit applies: Phase 0's spike must become a
  permanent, checked-in test, not a throwaway script.

## Implementation checklist

### Phase 0 — AGE compatibility spike
- [ ] `tests/test_age_integration.py` following
      `tests/test_falkordb_integration.py`'s exact pattern: a `docker run`
      one-liner in the module docstring (no compose file) with a **pinned
      `apache/age` image tag**, env-var host/port/credentials,
      `pytest.importorskip("psycopg")`, and a service-identifying
      connection probe (e.g. `LOAD 'age'` / `ag_catalog.ag_graph` query)
      that skips rather than fails when no live AGE instance answers.
- [ ] Pick and record the target AGE + PostgreSQL versions as that pinned
      image tag (also named in `docs/AGE_SCHEMA.md` later).
- [ ] Spike/validate: psycopg (v3) client- vs. server-side binding against
      `cypher()`.
- [ ] Spike/validate: agtype parameter maps via explicit `PREPARE`/`EXECUTE`
      (session-scoped; prepare once per pooled connection).
- [ ] Spike/validate: `UNWIND $rows` + `MERGE` behavior and batch sizing.
- [ ] Spike/validate: transactional write behavior (partial-failure
      rollback).
- [ ] Spike/validate: index options on AGE label tables that don't touch
      AGE internals.
- [ ] Confirm the suite is a silent no-op in existing `ci.yml` (no CI
      changes needed — matches the falkordb suite's status quo).
- [ ] Spike test file lands as a permanent test module (seed of the live
      integration suite), not a scratch script.
- [ ] Branch `age-phase0-spike` off synced `v8`; PR upstream; `pytest` green.

### Phase 1 — `push_to_age()` exporter
- [ ] `push_to_age()` in `graphify/exporters/graphdb.py`, sibling of
      `push_to_neo4j`/`push_to_falkordb`; re-exported from
      `graphify/export.py`.
- [ ] Session setup: `LOAD 'age'; SET search_path = ag_catalog, "$user",
      public;`; `create_graph()` if absent (check `ag_catalog.ag_graph`).
- [ ] Prepared fixed Cypher statement shapes; agtype parameter map of batch
      rows; `UNWIND $rows` at ~500 rows/statement; grouped by sanitized
      label/relation; single transaction per push.
- [ ] Deletion-safe in-place reconcile: delete nodes/edges absent from the
      incoming graph in the same transaction as the upserts; explicit
      old-label cleanup when `file_type` changes.
- [ ] Lean property set by default; `--full-props` flag.
- [ ] CLI: `graphify export age --push postgresql://... [--graph-name]
      [--full-props]`; `AGE_PASSWORD`/`PGPASSWORD` support.
- [ ] `age` extra added to `pyproject.toml` (with explicit
      `postgres`-extra overlap decision) and to `all`.
- [ ] `docs/AGE_SCHEMA.md` written; README export section updated;
      `graphify export --help` updated; `ARCHITECTURE.md` module table
      updated.
- [ ] Property/label/relation selection factored into a **shared pure
      function** used by all three pushers; schema-pinning unit test on it
      in the default CI suite (see Testing strategy).
- [ ] Reconcile implemented as a **pure planner** (graph in → ordered
      statement batches out) + thin AGE executor; planner unit-tested in
      default CI.
- [ ] Tier-1 unit tests: CLI wiring, env-var credential resolution,
      sanitization, lean-vs-`--full-props` selection.
- [ ] Tier-3 live test matrix (enumerated — these define "done"):
      fresh push; idempotent re-push (counts stable); node deletion
      reconciled; edge deletion reconciled; property change; **label
      change** (`file_type` changed → node must not survive under the old
      label); mid-push failure rolls back atomically (inject a bad row,
      assert the prior graph is intact); lean vs. `--full-props` output.
- [ ] Branch `age-phase1-exporter` off synced `v8`; PR upstream; `pytest`
      green.

### Phase 2 — Repository identity, ownership, registry
- [ ] Versioned SQL migration for `graphify_repos`, `graphify_branches`,
      `graphify_snapshots`, `graphify_branch_revisions`,
      `graphify_branch_diff`, `graphify_quality_findings`, including the
      partial unique index on `graphify_branch_revisions`.
- [ ] Tier-2 tests (plain-Postgres probe, no AGE needed): migration
      up/idempotency, partial unique index rejects a second active
      revision, snapshot-uniqueness constraint, generation supersession,
      identity/owner upserts.
- [ ] Push path: normalize remote URL → `repository_id`; register/update
      `graphify_repos`; owner resolution order (`--owner` flag → git remote
      owner segment → `git config user.email`); record `pushed_by`
      separately from `owner_id`.
- [ ] Record `graphify_version`, `schema_version`, `extraction_config_hash`
      on every registry write.
- [ ] Branch name from `git rev-parse --abbrev-ref HEAD`; commit SHA from
      git at push time.
- [ ] Global cross-repo AGE graph fed from `cross_repo_calls.py`,
      `repo_tag`-prefixed ids, owner-scoped for frontend retrieval.
- [ ] Agent-facing registry discovery path (how an agent resolves
      `age_graph_name` given a repo/branch).
- [ ] `ARCHITECTURE.md` updated for the registry module.
- [ ] Branch/PR per this repo's git workflow; `pytest` green.

### Phase 3 — Durable default-branch graph + logical snapshots
- [ ] `graph_diff()` extended to report property changes (old + new values)
      and full payloads on removal.
- [ ] Default-branch push records a logical snapshot: periodic full
      checkpoints (JSONB or object storage) + ordered reversible deltas.
- [ ] Incremental default-branch sync: diff against last-pushed snapshot;
      batched MERGE/SET/DETACH DELETE only; full deletion-safe push when no
      prior snapshot exists.
- [ ] Checkpoint cadence decided (see Open questions) and implemented.
- [ ] Snapshot uniqueness constraint enforced
      (`repository_id, commit_sha, kind, schema_version,
      extraction_config_hash, graphify_version`); checkpoint-preferred
      resolution implemented.
- [ ] `ARCHITECTURE.md` updated for snapshot machinery.
- [ ] Branch/PR; `pytest` green, including reversibility tests for
      `graph_diff()`.

### Phase 4 — Branches: commit-anchored diffs, lazy hydration, reaping
- [ ] Initial non-default-branch push: merge-base detection, base-snapshot
      resolution/creation, `graph_diff` against base, ordered diff-row
      upload; no AGE graph created yet.
- [ ] Subsequent pushes append `head_n → head_n+1` diff rows to the active
      generation.
- [ ] Force-push/rebase detection (`head_commit_sha` no longer an ancestor,
      or changed merge-base) → new generation in
      `graphify_branch_revisions`, old one marked inactive, new chain from
      new base snapshot.
- [ ] Missing-base-snapshot fallback chain: reconstruct from checkpoint +
      deltas, else temporary git worktree + extraction, stored as a new
      checkpoint.
- [ ] Materialization path (`graphify age materialize` or server-side
      helper): create AGE graph, rehydrate via batched prepared Cypher from
      pinned base snapshot, replay diff chain to head; refuse on
      `schema_version`/`extraction_config_hash` mismatch.
- [ ] Advisory lock (keyed `repository_id, branch`) around
      materializer and reaper; re-read registry state inside the
      transaction.
- [ ] Atomic branch-push transaction: AGE mutation + diff rows + head SHA +
      materialization metadata commit together.
- [ ] Reaper: `drop_graph` on merge/closure/inactivity/size threshold,
      generous grace period documented; diff rows/snapshots retained.
- [ ] Reaper trigger mechanism decided (cron vs. opportunistic on push; see
      Open questions).
- [ ] Cross-branch comparison query support (two-graph `cypher()` calls in
      one SQL statement) documented/tested.
- [ ] `ARCHITECTURE.md` updated for materializer/reaper.
- [ ] Materialization/replay implemented planner/executor style: replay
      logic tier-1-tested against NetworkX (ordering, transition
      validation, cross-generation rejection); only the executor needs the
      live suite.
- [ ] Deterministic tier-3 concurrency tests: two connections, one holding
      the advisory lock, the second asserting `pg_try_advisory_lock` fails
      and the re-read-then-hydrate path is taken — no sleep-based races.
- [ ] Branch/PR; `pytest` green including rebase/force-push detection
      tests (tier 1, throwaway git repo in tmpdir).

### Phase 5 — Agent contract: pinned queries and fixtures
- [ ] Review-agent query set documented and pinned: branch-diff seed
      selection, traversal direction per relation, reverse-dependency
      traversal, required evidence fields, depth caps/result
      limits/statement timeouts.
- [ ] Quality-agent contract: structural properties vs.
      `graphify_quality_findings` boundary documented.
- [ ] Pinned example queries added to `docs/AGE_SCHEMA.md`.
- [ ] Integration fixtures in the live suite executing the pinned queries
      against a seeded instance.
- [ ] Branch/PR; `pytest` green.

### Phase 6 (optional) — AGE-backed retrieval inside graphify
- [ ] Backend abstraction for `query/path/explain` and `serve.py`
      (file-backend vs. AGE connection).
- [ ] AGE-fetch-then-NetworkX-score strategy implemented; scoring/formatting
      unchanged and behavior-identical to the file backend.
- [ ] `ARCHITECTURE.md` updated.
- [ ] Branch/PR; `pytest` green.

### Cross-cutting / process
- [ ] `v8` kept synced to `origin/v8` before cutting each phase branch.
- [ ] Every PR uses `feat:`/`fix:`/`docs:` commit style and passes
      `uv run pytest tests/ -q` before opening.
- [ ] `uv sync --all-extras --frozen` + full CI parity command list stays
      green on Python 3.10 and 3.12 after each phase.
- [ ] `postgres`/`age` extra overlap decision recorded once, not
      re-litigated per phase.
- [ ] CONTRIBUTING note (or README addition) documenting the fork → branch
      → PR-to-upstream flow, once the first AGE PR is up.
- [ ] Every PR touching AGE write paths states in its description that the
      tier-3 live suite was run locally against the pinned image tag, and
      the result (the accepted-risk mitigation in Testing strategy).

## Open questions

- Sanitization/length rules for AGE graph names (Postgres identifier limit
  is 63 bytes — hashing fallback for long branch names).
- Reaper trigger mechanism: cron/scheduled job vs. opportunistic reap on
  push. Merge/closure detection needs the pusher to report it (or a
  periodic check against the remote).
- Snapshot payload location: Postgres JSONB vs. object storage (size
  threshold?).
- Checkpoint cadence for `graphify_snapshots` (every N pushes? size-based?).
- Whether the frontend layer enforcing owner scoping is part of graphify
  (e.g. an authenticated MCP/HTTP mode of `serve.py`) or external.
- Whether to later add a non-blocking scheduled CI workflow with an AGE
  service container to run the tier-3 suite automatically (not required by
  this plan; would need upstream buy-in since CI config is upstream's).
