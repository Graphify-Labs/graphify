# Development and GitHub workflow

This foundation uses the repository's Python/uv workflow. Qt/QML are analyzed
inputs; development does not require replacing Graphify with a Qt application.
Read [AGENTS.md](../../AGENTS.md), [CONTRIBUTING.md](../../CONTRIBUTING.md), and the
[increment plan](PLAN.md) before a behavioral change.

## Account access and remotes

Use [GitHub CLI](https://cli.github.com/) for authenticated REST/GraphQL operations
and Git for version control. Authentication is stored in the operating system
credential store. Do not print tokens or commit credential configuration.

```text
gh auth login --hostname github.com --git-protocol https --web --scopes repo,workflow,read:org
gh auth setup-git --hostname github.com
gh api user --jq .login
gh api repos/<fork-owner>/graphify --jq .permissions
git remote -v
```

The OAuth `repo` and `workflow` scopes support repository development and workflow
operations within the signed-in account's permissions. They do not bypass
organization policies or grant administration of upstream Graphify. Verify
operation-specific permissions and the repository before any mutation. See the
[GitHub authentication documentation](https://docs.github.com/en/rest/authentication/authenticating-to-the-rest-api).

Use `origin` for the contributor fork and `upstream` for
`https://github.com/Graphify-Labs/graphify.git`. The local `remote.pushDefault`
points at `origin`. Keep the current approved workspace and use explicit branch
names when pushing. New shell sessions must see `gh` on PATH; a running application
may need a new terminal session to pick up a newly installed CLI.

The upstream development branch is `v8`, not `main`, at this baseline.
Verify its current status before each increment:

```text
git status --short --branch
git fetch upstream
git log -1 upstream/v8
git switch -c codex/<increment-name> upstream/v8
```

Preserve existing collaborator changes and do not switch branches over unfinished
work. The foundation branch is `codex/qt-qml-foundation`; subsequent increments
start from an agreed base containing the required predecessor changes.

## Environment and baseline checks

```text
uv sync --frozen
uv run --frozen python -X utf8 -m pytest tests/test_detect.py tests/test_languages.py tests/test_extract.py tests/test_build.py tests/test_cache.py tests/test_watch.py -q --tb=short
uv run --frozen ruff check .
uv run --frozen pyright
uv run --frozen python -m tools.skillgen --check
```

The module-based pytest runner gives Windows worker processes an importable main
module; `-X utf8` avoids host-default text-encoding differences. The original
POSIX upstream CI command can remain valid in its own environment. Do not silently
discard Windows failures or modify assertions merely to make the baseline green.

`uv sync --frozen` installs the locked core and development dependencies. Optional
language/provider tests can skip. A full CI reproduction uses
`uv sync --all-extras --frozen` and the upstream Python-version matrix on suitable
hosts. Record the environment and extras with every result. See
[VALIDATION.md](VALIDATION.md) for the narrower Windows baseline actually run.

Use an existing Python 3.10+ interpreter explicitly with `uv sync --python <path>`
if the machine's default Python launcher or managed installation is unavailable.
The repository-local `.venv` remains ignored. Do not rewrite `uv.lock` during a
baseline check. Dependency changes require an intentional reviewed lock refresh.

## Work already proposed upstream

The feature is tracked by [issue #1716](https://github.com/Graphify-Labs/graphify/issues/1716)
and [PR #1748](https://github.com/Graphify-Labs/graphify/pull/1748). Review their
current state, code, tests, licensing and checks before creating overlapping work.
Use the immutable reviewed head recorded in [AUDIT.md](AUDIT.md) for reproducible
comparison. Coordinate reusable fixes and avoid opening a duplicate feature issue.

```text
gh api repos/Graphify-Labs/graphify/pulls/1748
gh api repos/Graphify-Labs/graphify/pulls/1748/files --paginate
gh api repos/Graphify-Labs/graphify/commits/<reviewed-head>/check-runs
```

Read-only review is part of QML-00. Do not apply an old PR's replacement function
body blindly onto a newer upstream base: preserve current C++ normalization,
test-macro handling, resolver contracts, and cache/update invariants.

## Increment implementation and handoff

For each increment, record requirement IDs, scope, source-fact invariants, tests,
and compatibility impact before coding. Add hand-checked synthetic/public fixtures
and behavior-led tests. Keep parser facts separate from module resolution and
graph projection. Update the canonical documents and traceability in the same PR.
Map every applicable `QML-XXX-ACYY` acceptance ID to an individual test/check and
its result or explicit gap. A requirement is Verified only when all its applicable
criteria have passing evidence; an aggregate test count is insufficient.

Run targeted tests during development and required full-suite/lint/type/generated
checks before handoff. Source-fragment changes use `tools.skillgen`; generated
assistant files are not hand-edited. After code changes, refresh the local graph
with `uv run --frozen graphify update .` and inspect its outcome. Use the graph for
ordinary repository navigation when available; source evidence is required when
auditing the graph's own correctness.

Before publishing a branch, inspect the staged and complete diff for private names,
machine paths, credentials, generated outputs, and unrelated changes. Use public
fixtures and retain license notices. The sanitized repository standard contains
only reusable development practices and public project references.

When publication is in scope, use an explicit push and a narrow PR. Match the
base to the agreed upstream/fork target, and write the description to a file so
newlines and literal shell characters are preserved:

```text
git push origin HEAD:refs/heads/codex/<increment-name>
gh pr create --repo <target-owner>/graphify --base v8 --head <fork-owner>:codex/<increment-name> --title "<concrete change>" --body-file <description-file>
```

Verify the resulting PR head and checks through the API. The baseline CI push
filter does not run on `codex/*` pushes; a matching-base PR or an explicit supported
dispatch is needed. A passing local baseline is not a claim of passing GitHub CI.
Attach any newly created PR to the working chat and keep its description aligned
with the final implementation. Merge only under the repository's authorized review
and check policy.
