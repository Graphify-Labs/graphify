# graphify → MaluDb

**Turn a codebase into a knowledge graph and push it into a [MaluDb](https://github.com/maludb) memory database.**

This is the MaluDb fork of [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify). Upstream graphify maps a project — code, docs, PDFs — into a queryable knowledge graph (`graphify-out/graph.json`) using tree-sitter AST extraction, with zero LLM cost for code. This fork adds a MaluDb export path on top of that: the graph is persisted into MaluDb as subjects and statements, and application code is linked to your database data model, so agents using MaluDb memory can answer questions like *"which files write to `orders`?"* directly from memory.

## What this fork adds

| Capability | Command |
|---|---|
| **Push a graph into MaluDb** — nodes become subjects, edges become subject–verb–object statements, idempotent upsert via `POST /v1/graph/import` | `graphify export maludb --push <URL>` |
| **SQL-usage mining** — scan the source files behind the graph for SQL and emit `reads` / `writes` links from code files to data-model nodes | `graphify export maludb --sql-usage` |
| **Live PostgreSQL introspection** — build a data-model graph straight from a running database, with real column, primary-key, and unique-constraint metadata on every table node | `graphify extract --postgres <DSN>` |
| **Typed SQL nodes** — `.sql` DDL extraction tags nodes as `table` / `view` and attaches column/PK/unique metadata parsed from `CREATE TABLE` | `graphify extract <dir>` (any corpus containing `.sql`) |

Everything upstream graphify does (interactive `graph.html`, `GRAPH_REPORT.md`, `graphify query`/`path`/`explain`, MCP server, assistant skills for Claude Code and 20+ other agents) still works — see the [upstream README](https://github.com/Graphify-Labs/graphify#readme) for those features.

## How the graph maps to MaluDb

`graphify export maludb` POSTs the graph to a MaluDb `/v1` API server (any of the three implementations: [maludb-lamp-api-server](https://github.com/maludb/maludb-lamp-api-server), [maludb-python-api-server](https://github.com/maludb/maludb-python-api-server), [maludb-fastify-api-server](https://github.com/maludb/maludb-fastify-api-server)), backed by [maludb-core](https://github.com/maludb/maludb-core) in PostgreSQL.

| graphify | MaluDb |
|---|---|
| Node | Subject with canonical name `<namespace>/<node id>`; the node label becomes an alias |
| Edge | Statement (subject–verb–object); the edge relation is the verb |
| Confidence `EXTRACTED` / `INFERRED` / `AMBIGUOUS` | Statement confidence `1.0` / `0.7` / `0.4` |
| Community assignment | Carried on the node payload |

The server upserts idempotently — re-pushing the same graph updates rather than duplicates, so it is safe to re-export after every rebuild.

## Prerequisites

- **Python 3.10+** and [uv](https://docs.astral.sh/uv/) (recommended) or pipx/pip
- **A running MaluDb API server** and a bearer token (mint one via the server's `/v1/tokens` endpoint)
- For `--postgres` introspection: network access to the target PostgreSQL database

## Installation

Install from this fork (the PyPI package `graphifyy` is upstream and does not include the MaluDb exporter):

```bash
# From a clone (recommended for development):
git clone https://github.com/maludb/graphify.git
cd graphify
uv tool install .

# With the PostgreSQL introspection and SQL-parsing extras:
uv tool install ".[postgres,sql]"

# Or directly from GitHub without cloning:
uv tool install "graphifyy[postgres,sql] @ git+https://github.com/maludb/graphify.git"
```

The CLI command is `graphify`. If the command is not found after install, run `uv tool update-shell` and open a new terminal.

The base install needs **no API keys and no extras** for code-only extraction — AST parsing runs fully offline. The two extras used by this fork:

| Extra | What it adds |
|---|---|
| `postgres` | `graphify extract --postgres <DSN>` live schema introspection (`psycopg`) |
| `sql` | tree-sitter-sql parsing for `.sql` files and SQL-statement analysis |

## Configuration

The MaluDb exporter reads two environment variables so credentials stay off the command line (and out of `ps` output / shell history):

| Variable | Purpose | CLI override |
|---|---|---|
| `MALUDB_URL` | Base URL of the MaluDb API server, e.g. `http://localhost:8000` | `--push <URL>` |
| `MALUDB_TOKEN` | Bearer token for the server | `--token <T>` |

```bash
export MALUDB_URL="http://localhost:8000"
export MALUDB_TOKEN="<your-token>"
```

### `graphify export maludb` flags

| Flag | Default | Purpose |
|---|---|---|
| `--push URL` | `$MALUDB_URL` | MaluDb API server base URL (http/https) |
| `--token T` | `$MALUDB_TOKEN` | Bearer token |
| `--namespace NS` | project directory name | Namespace prefix for all subjects created by this import |
| `--graph PATH` | `graphify-out/graph.json` | Graph file to push |
| `--sql-usage` | off | Mine SQL table references from source files and push them as extra cross-namespace links |
| `--source-root DIR` | the graph's project directory | Root the graph's `source_file` paths are resolved against for SQL scanning |
| `--db-schema S` | `public` | Schema assumed for unqualified table names found in SQL |
| `--datamodel-ns NS` | `datamodel` | Namespace of the data-model graph the mined links point at |

## Quick start

### 1. Build a code graph

```bash
cd ~/my-app
graphify extract .        # AST-only, offline, no API key needed
```

This writes `graphify-out/graph.json` (plus `graph.html` and `GRAPH_REPORT.md`). Inside Claude Code you can run `/graphify .` instead — same output.

### 2. Push it to MaluDb

```bash
graphify export maludb
# Pushed to MaluDb (http://localhost:8000, namespace 'my-app'):
#   1842 nodes (1842 new, 0 updated), 5210 edges (5210 new)
```

The namespace defaults to the project directory name; pass `--namespace` to control it.

### 3. Push your data model

Build a graph of the live database schema and push it under the `datamodel` namespace:

```bash
graphify extract --postgres "postgresql://user:pass@host/db"
graphify export maludb --namespace datamodel
```

Every table becomes a typed `table` node carrying real catalog metadata — columns with types and nullability, primary-key columns, and unique constraints (including unique indexes not declared as constraints). Foreign keys become edges between tables. If you keep DDL in the repo instead, plain `graphify extract` on a directory containing `.sql` files produces the same typed nodes from the `CREATE TABLE` statements.

### 4. Link code to the data model

Re-push the code graph with SQL-usage mining enabled:

```bash
cd ~/my-app
graphify export maludb --sql-usage
# sql-usage: 317 table-reference links mined from /home/me/my-app
# Pushed to MaluDb (...): 1842 nodes (0 new, 1842 updated), 5527 edges (317 new)
```

The miner scans each source file that appears in the graph (Python, PHP, TypeScript/JavaScript, Rust, Go, Ruby, Java, Kotlin, C#, C/C++, Perl, and `.sql`) for `INSERT INTO` / `UPDATE … SET` / `DELETE FROM` (→ `writes` links) and `FROM` / `JOIN` (→ `reads` links). Each hit becomes a link from the file's node to `datamodel/<schema>.<table>`, pushed with the server's `resolve_external` option: targets that exist in the tenant's data-model graph resolve into real edges; unknown targets land in the import report's `skipped` list rather than failing the import.

The mining is deliberately regex-based — the goal is `INFERRED`-confidence "this file touches that table" edges, not full query understanding. System catalogs (`pg_catalog`, `information_schema`, `pg_*`), SQL set-returning functions, and interpolated/placeholder names are filtered out.

## Typical workflow

```bash
# one-time
export MALUDB_URL=... MALUDB_TOKEN=...
graphify extract --postgres "$DATABASE_URL"      # data-model graph
graphify export maludb --namespace datamodel

# per repository, repeat after significant changes
cd ~/repos/my-app
graphify extract .
graphify export maludb --sql-usage

# then query the graph locally...
graphify query "what writes to the orders table?"
# ...or let any MaluDb-connected agent answer from memory
```

`graphify hook install` (upstream feature) rebuilds the graph on every git commit; re-run the export afterwards to keep MaluDb in sync.

## Troubleshooting

**`error: --push URL (or MALUDB_URL) required`** — set `MALUDB_URL` or pass `--push http://host:port`. Only `http`/`https` schemes are accepted.

**`error: --token (or MALUDB_TOKEN) required`** — mint a bearer token on the MaluDb server (`/v1/tokens`) and export it as `MALUDB_TOKEN`.

**`MaluDb import failed: HTTP 401/403`** — the token is invalid or lacks write access for the tenant.

**`--sql-usage` mined 0 links** — the scanner resolves the graph's `source_file` paths against `--source-root` (default: the graph's project directory, i.e. the parent of `graphify-out/`). If you moved `graph.json` or run from elsewhere, pass `--source-root` explicitly.

**Mined links all land in `skipped`** — the targets are `<datamodel-ns>/<schema>.<table>`; make sure the data-model graph was pushed under the same namespace (`--datamodel-ns`, default `datamodel`) and that unqualified names match your schema (`--db-schema`, default `public`).

**`--postgres` fails to import psycopg** — install the extra: `uv tool install ".[postgres]"`.

## Development

```bash
git clone https://github.com/maludb/graphify.git
cd graphify
uv sync --all-extras          # venv + all extras + dev group (pytest, ruff, pyright)

uv run pytest tests/ -q                       # full suite
uv run pytest tests/test_export.py -q         # MaluDb exporter tests
uv run pytest tests/test_pg_introspect.py -q  # PostgreSQL introspection tests
```

Fork-specific code lives in:

- `graphify/export.py` — `push_to_maludb()` (stdlib `urllib`, no extra dependency)
- `graphify/sql_usage.py` — SQL-usage mining (code file → table links)
- `graphify/pg_introspect.py` — live PostgreSQL schema introspection with catalog metadata
- `graphify/__main__.py` — the `graphify export maludb` CLI wiring

To pull upstream improvements:

```bash
git remote add upstream https://github.com/Graphify-Labs/graphify
git fetch upstream && git merge upstream/v8
```

## Related MaluDb repositories

- [maludb-core](https://github.com/maludb/maludb-core) — the memory database (PostgreSQL 17 extension)
- API servers: [maludb-lamp-api-server](https://github.com/maludb/maludb-lamp-api-server) (reference), [maludb-python-api-server](https://github.com/maludb/maludb-python-api-server), [maludb-fastify-api-server](https://github.com/maludb/maludb-fastify-api-server) — any of them accepts `graphify export maludb`
- [maludb-terminal](https://github.com/maludb/maludb-terminal) — Rust CLI + MCP server for querying the memory the graph lands in

MaluDb is an open-source memory database supported by [Kinetic Seas Incorporated](https://kineticseas.com).

## License

MIT — see [LICENSE](LICENSE). This fork retains the upstream MIT license and copyright.
