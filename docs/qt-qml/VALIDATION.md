# Foundation validation record

Validation date: 2026-10-03. Baseline:
`0b60d47e6cd9338c51143f39f35b6c45c8453385`, upstream `v8`, Graphify `0.9.74`.
Host: Windows x64, CPython `3.12.14`, uv `0.12.15`, Tree-sitter `0.25.2`.
No Graphify runtime source, parser dependencies, lockfile, or existing tests were
changed for this foundation. Results describe the audited baseline.

## Account and repository setup

GitHub CLI `2.102.0` was obtained from its official release and the downloaded
archive SHA-256 was checked against the release digest. OAuth sign-in completed
and `gh auth status` reported keyring storage, an active account, HTTPS Git, and
`repo`, `workflow`, `read:org`, and CLI-default `gist` scopes. Authenticated
`GET /user` succeeded. No credential value was copied into repository files.

A contributor fork was created using the GitHub API and verified as a fork of
`Graphify-Labs/graphify`, default branch `v8`. The repository API returned
`admin`, `maintain`, `push`, `pull`, and `triage` permissions as true for that fork.
The local `origin` targets the fork, `upstream` targets the official repository,
and `remote.pushDefault` is `origin`. This verifies development access to the
fork; it does not claim administration access to the official upstream.

## Environment

The machine's default Python command was a Store launcher, and the first managed
Python setup encountered an invalid minor-version link. Neither problem required
a source or lockfile change. The bundled CPython interpreter supplied a working
base for:

```text
uv sync --frozen --python <bundled-python-path> --no-managed-python
```

Result: success; repository-local `.venv` installed locked core and development
dependencies. Optional extras were not all installed. Machine-specific paths and
raw authentication responses are intentionally absent from this public record.

## Executed checks

| Command / probe | Result |
| --- | --- |
| `uv run --frozen --no-sync graphify --help` | Passed; CLI starts from the installed source checkout |
| `uv run --frozen --no-sync ruff check .` | Passed |
| `uv run --frozen --no-sync python -m tools.skillgen --check` | Passed; 134 generated artifacts match committed outputs |
| `uv run --frozen --no-sync pyright` | Failed on unchanged baseline: 634 errors, 4 warnings; includes optional missing imports and existing typing errors |
| Foundation document consistency check | Passed; 17 requirements, 68 unique acceptance criteria and 68 individual traceability assignments |
| Foundation local-link/private-reference scan and `git diff --check` | Passed across 11 foundation documents; no matching private identifiers, machine paths or credential patterns |
| Six-file focused suite using `uv run --frozen --no-sync pytest ... -q --tb=short` | 1,259 passed, 53 skipped, 8 failed in 58.90 seconds; runner/encoding differences investigated below |
| Five failed multiprocessing-fallback cases using `python -m pytest` | 5 passed, 232 deselected; module invocation fixes the runner boundary |
| Unicode-normalization case using `python -X utf8 -m pytest` | 1 passed; UTF-8 fixes the host-default text encoding boundary |
| Same six-file suite using `uv run --frozen --no-sync python -X utf8 -m pytest ... -q --tb=short` | **1,265 passed, 53 skipped, 2 failed in 49.62 seconds** |

The six files were `tests/test_detect.py`, `tests/test_languages.py`,
`tests/test_extract.py`, `tests/test_build.py`, `tests/test_cache.py`, and
`tests/test_watch.py`. They cover the main extension boundaries; this was not the
complete test suite or an all-extras/cross-platform CI run. Skipped optional parser
or watcher cases are coverage gaps, not successful feature verification.

The two remaining failures are:

- `tests/test_watch.py::test_rebuild_code_deleted_cwd_without_repo_root_returns_false`
- `tests/test_watch.py::test_rebuild_code_deleted_cwd_uses_graphify_repo_root`

Both attempt to remove a directory while it is the process's current directory.
Windows raises `PermissionError: [WinError 32]` before the behavior under test is
reached. Preserve these findings as baseline portability debt. A faithful Windows
test adaptation belongs in a separate focused change; the foundation did not
weaken or skip the assertions.

## Executed file-admission probe

Called `classify_file(Path(name))` and `_get_extractor(Path(name))` on baseline
filenames. These are classification/dispatch observations, not full parser runs:

| Input | Classification | Extractor |
| --- | --- | --- |
| `Main.qml` | None | None |
| `Panel.ui.qml` | None | None |
| `plugins.qmltypes` | None | None |
| `qmldir` | None | None |
| `CMakeLists.txt` | Document | None |
| `app.pro` | None | None |
| `assets.qrc` | None | None |
| `backend.hpp` | Code | `extract_cpp` |
| `helpers.mjs` | Code | `extract_js` |

These observations confirm that QML and key Qt metadata do not enter the current
deterministic extraction path. They do not prove that generic C++ handles Qt
meta-object declarations or that generic JS handles QML-specific script directives.

## Upstream proposal review and remaining gates

Read-only API inspection found open issue #1716 and PR #1748. The reviewed PR head
is `7b38d4c2e2226b1db826a26774c7a5f299b8d62f`; see [AUDIT.md](AUDIT.md) for
static reuse/gap findings. Its source was fetched to a remote ref for inspection;
it was not merged or tested as the working implementation.

QML parser installation/API compatibility, representative Qt version profiles,
grammar error recovery, PR implementation tests, full-suite/all-extras CI, macOS
and Linux extraction, performance, and Qt-specific incremental parity remain
unverified. QML-00 in [PLAN.md](PLAN.md) owns the next investigation.
