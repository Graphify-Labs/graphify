# Qt/QML validation record

## Executed QML-00 through QML-03 — 2026-10-03

The imported baseline remains `0b60d47e6cd9338c51143f39f35b6c45c8453385`.
QML-00 commit `2f0fdce`, QML-01 commits `4f587f6`/`63075e8`, and QML-02
commit `df432a7` separate the executed stages. QML-03 is on
`codex/qml-03-relationships`; its source and final evidence are committed together.
The upstream API was rechecked: v8 still points at the imported baseline. Proposal
#1748 remains unmerged; no proposal code was copied into these modules/fixtures.

| Executed check | Result |
| --- | --- |
| QML-00 candidate probes, each Windows Python 3.10/3.12/3.13/3.14 | 40 passed, no skips per lane |
| All 21 actual QML test files with reviewed QML-03 wheel, each Windows Python lane | 239 passed, two symlink-permission skips per lane before final eight BOM/CRLF reader regressions |
| Final qmldir reader and production syntax profile | 33 passed, no skips, including original BOM/CRLF/Unicode bytes and bounded binary reads |
| QML-03 optional wheel installs, neutral cwd, isolated `-I` production entry point | Passed Python 3.10.21/3.12.14/3.13.15/3.14.7; bindings, imported scripts and subscriptions exercised with Python network/process audit denial |
| Fresh core-only wheel, Python 3.12.14 | Passed with pack actually absent; Python extraction still works, QML reports parser unavailable |
| Built-artifact tests with GRAPHIFY_QML_TEST_WHEEL supplied | Three passed; artifact imports and core/parser boundary executed |
| New CI helper executed locally, Python 3.12 | Clean extra/core installs and both isolated smoke checks passed; three artifact tests passed |
| Minimal CI environment QML source suite | 239 passed, two symlink skips; pytest 9.1.1, NetworkX 3.7, Python 3.12.14 |
| Relevant existing shared-boundary ten-file suite | 1337 passed, 53 skipped, the same two baseline Windows deleted-cwd failures |
| Whole-repository Ruff | Passed |
| All seventeen QML runtime modules and two install/CI helpers, targeted Pyright | Zero errors, zero warnings |
| skillgen check/audit-coverage/schema-singleton/monolith/always-on round trips | All passed; 134 generated artifacts match |
| uv lock --check | Passed; 210 packages, no unrelated lock churn |

The shared-boundary command was `python -X utf8 -m pytest` with test_detect,
test_languages, test_extract, test_build, test_cache, test_watch, test_paths,
test_query_mcp_direction, test_extractors_registry and test_validate. The two
collector failures first encountered were stale extension-only expectations:
the corrected tests retain the full legacy suffix oracle and independently require
the exact qmldir fixture. No unsupported extensionless input is newly admitted.

The two unchanged deleted-cwd failures below still raise WinError 32 before the
tested behavior. The full suite/all-extras hosted CI is not represented by these
focused results. Windows cannot create the symlinks needed by two QML corpus
tests; no skip counts as passing containment evidence. Python 3.10 uses NetworkX
3.4.2 and emits two future warnings; the other fresh lanes use NetworkX 3.7.
Whole-baseline Pyright still has the recorded 634 errors/four warnings.

CI now has a separate read-only optional-wheel matrix for Ubuntu, Windows and
macOS on all four Python lanes. The existing Ubuntu all-extras job owns source
regressions; its extra QML job runs wheel/core evidence only. Windows/macOS add the
focused QML suite. PR events own validation; no duplicate manual full run was
dispatched. Hosted conclusions remain pending, and Linux/macOS are unverified.
Python-level analysis guards do not constitute an operating-system network sandbox.

The eight new original-byte regressions invalidate the earlier wheel's qmldir
provenance evidence. Final source-snapshot wheel rebuilding/reverification is
recorded below before published completion; earlier counts remain historical.

Final QML-03 revalidation: source archive built from the reviewed Git index,
excluding concurrent next-increment modules; optional wheel SHA256
`b6d98399ad534f9a86a99c8d4f35d18027c7143ee90b1ec72e7e2aaab03bf881`.
All four isolated Windows lanes run the updated installed production smoke,
including BOM/CRLF qmldir bytes, and the complete source/artifact suite:
**247 passed, two symlink-permission skips per lane**. A fresh core-only Python
3.12 wheel also passes the updated smoke. The earlier wheel is superseded.
Repository graph refresh passes: 19,115 nodes, 38,416 edges, 1,070 communities;
existing unavailable optional-language warnings remain explicit in the local log.
Public document links/privacy and all 68 distinct criterion assignments pass.

## Historical foundation evidence

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

## Development-standard review — 2026-10-03

Strengthened [AGENTS.md](../../AGENTS.md) across the twelve requested discipline
areas, adapted pipeline rules to GitHub, and retained the specialized upstream
extractor-migration constraints. Protected proof rules remain future policy;
no workflow protection or runtime language support was introduced.

Moved the canonical requirements to [docs/REQUIREMENTS.md](../REQUIREMENTS.md)
and updated the index, audit, design, plan, code reference, and traceability links.
A one-off Python document check passed across eleven public foundation files:
all requested headings exist, local links resolve, the old requirements path is
absent, and private-reference/credential-pattern checks pass. All seventeen
requirement IDs and sixty-eight acceptance criteria retain their numbering;
criterion text/order is unchanged and each criterion still has one traceability
assignment. `git diff --check` passed.

This was a documentation-only review. Runtime tests were not rerun; the baseline
results and outstanding implementation gates above remain unchanged.

## Increment execution-plan review — 2026-10-03

Refined [PLAN.md](PLAN.md) into reviewable packages with explicit prerequisites,
readiness/completion gates, file ownership and evidence handoffs. Native Qt event
work can follow the baseline/contracts checkpoint alongside QML extraction;
metadata readers precede their later bridge joins. Early enabled update paths
require a tested safe fallback or rejection before writes.

A one-off Python planning check passed across eleven public foundation files:
seventeen stable requirements, sixty-eight unchanged criteria with exactly one
planned completion increment each, and eight preserved increment IDs. The
dependency graph has eleven nodes and sixteen edges with no cycle. All forty-six
referenced existing test paths resolve; the sixteen new Qt/QML test files remain
explicit proposals. Local links, canonical paths, planned/unexecuted status and
private-reference/credential-pattern checks passed. `git diff --check` passed.

No production code, parser probe or runtime test was executed for this planning
revision. QML-00 remains the first execution checkpoint, and all implementation
acceptance criteria remain unexecuted.


## QML-03 hosted proof — 2026-10-03

Draft [fork PR 1](https://github.com/SlinkyRamey/graphify/pull/1) is open against
`v8`. Reviewed source head `92f31658beceb5d36f570ae8e3820698b39381fb`, base
`0b60d47e6cd9338c51143f39f35b6c45c8453385`; both PR workflows checked out synthetic
merge `a9fba56c165210880236a635d00a96e84e19f1aa`. This is pre-merge evidence;
no default branch was merged.

[CI run 37087772631](https://github.com/SlinkyRamey/graphify/actions/runs/37087772631)
completed successfully: Ubuntu Python 3.10 had 6541 passed/16 skipped; Python
3.12, 3.13 and 3.14 each had 6540 passed/17 skipped. Ruff, skill regeneration,
security scan and installation checks also succeeded. Skips remain explicit.

[Optional wheel run 37087772653](https://github.com/SlinkyRamey/graphify/actions/runs/37087772653)
completed successfully in all twelve Ubuntu/Windows/macOS Python 3.10/3.12/3.13/3.14
lanes. Each lane built and installed the wheel into clean optional/core environments
and ran isolated offline production smoke. Windows and macOS each ran 249 source
contracts; Ubuntu ran the three artifact contracts and the separate CI workflow
owned the full source suite. The hosted Windows symlink cases passed.

This verifies QML-03 only. Later Qt changes require their own reviewed-head proof.


## QML-04 local proof — 2026-10-03

Reviewed source boundary starts at QML-03 head `92f31658beceb5d36f570ae8e3820698b39381fb`.
Official upstream v8 was rechecked and remains
`0b60d47e6cd9338c51143f39f35b6c45c8453385`. No upstream Qt PR code was copied.

Windows Python3.12.14 focused QML/Qt+C++/cache/registry suite: **547 passed,
17 skipped** (host symlink permission, artifact env absent in that command, and
baseline optional language omissions). The actual wheel artifact suite separately
passed all3 cases. Whole-repository Ruff and lockcheck (210 packages) passed;
focused runtime/index/helper Pyright had zero errors/warnings. Baseline Windows
current-directory deletion defects recorded in QML-03 remain unchanged limitations.

A clean Git-index source archive built the noneditable wheel with SHA256
`a4973256e987d9e75c89e54567350c0ff9af72384b2eed57ff19d173780d972e`.
Python3.12.14 isolated neutral-directory optional/core smoke both passed, including
native Qt emission with no QML parser in the core-only environment. The wheel
contains the internal metadata/index foundation; its public admission remains
QML-05. Later Python/OS source lanes are owned by the forthcoming PR workflows.

The required repository graph refresh succeeded:19555 nodes,40020 edges and1065
communities. Existing unavailable optional-language warnings remain explicit.
Generated graph/report/cache/coverage data are excluded from commits.


## QML-05 local evidence

Windows Python3.12.14: 435 Qt/QML tests passed with6 documented skips before the
final duplicate-provider regression; extract/registry/admission245 passed8 baseline
optional-language skips. The final canonicalization fix passes independent facade
CMake/qmake native membership, duplicate module, qrc alias and accepted-target
regressions. QML-06 tests still demonstrate ignore-only refresh gaps and remain
open. Ruff passes touched production/tests. The source refresh produced19701 nodes,
40531 edges and1066 communities before the final identity fix; a final refresh is
required before commit. Hosted QML-04 runs37090713564/37090713525 were still running
when this local evidence was recorded; they do not prove the QML-05 revision.

Final focused public admission/native/resource/type suite: 67 passed. Additional
index regressions retain same-target duplicate project declarations as ambiguous.
No acceptance is inferred from unfinished QML-06 or QML-07 cases.


## QML-06 local evidence

Windows Python3.12.14: policy/state/config/provider tests73 passed; the corrected
plain-C++ cache plus config/provider subset52 passed; actual code-only/extract/
QML publication CLI tests89 passed. An intermediate broad run1001 passed28 skipped
with a corrected plain-header cache regression and the two established Windows
WinError32 deleted-current-directory baseline failures. Final regression and worker
proof follow. Both QML-04 and QML-05 hosted CI and twelve optional/core wheel lanes
completed successfully for their respective PR heads; final QML-07 proof remains.

Final worker/cache/native-root suite6 passed; compatibility fallback regression
plus worker suite7 passed after preserving the legacy helper invocation. Targeted
Qt policy/state/project/resolver typing reports0errors0warnings; whole Ruff passes.
The last broad regression1001 passed28skipped, with corrected helper invocation
and the two established Windows deleted-current-directory failures. Their hosted
Linux proof remains required; no test or assertion was skipped to mask them.
