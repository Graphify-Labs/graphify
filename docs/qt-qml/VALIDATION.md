# Qt/QML validation record

<a name="executed-qml-00-through-qml-03--2026-10-03"></a>

## Executed INC-QML-00 through INC-QML-03 — 2026-10-03

The imported baseline remains `0b60d47e6cd9338c51143f39f35b6c45c8453385`.
INC-QML-00 commit `2f0fdce`, INC-QML-01 commits `4f587f6`/`63075e8`, and INC-QML-02
commit `df432a7` separate the executed stages. INC-QML-03 is on
`codex/qml-03-relationships`; its source and final evidence are committed together.
The upstream API was rechecked: v8 still points at the imported baseline. Proposal
#1748 remains unmerged; no proposal code was copied into these modules/fixtures.

| Executed check | Result |
| --- | --- |
| INC-QML-00 candidate probes, each Windows Python 3.10/3.12/3.13/3.14 | 40 passed, no skips per lane |
| All 21 actual QML test files with reviewed INC-QML-03 wheel, each Windows Python lane | 239 passed, two symlink-permission skips per lane before final eight BOM/CRLF reader regressions |
| Final qmldir reader and production syntax profile | 33 passed, no skips, including original BOM/CRLF/Unicode bytes and bounded binary reads |
| INC-QML-03 optional wheel installs, neutral cwd, isolated `-I` production entry point | Passed Python 3.10.21/3.12.14/3.13.15/3.14.7; bindings, imported scripts and subscriptions exercised with Python network/process audit denial |
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

Final INC-QML-03 revalidation: source archive built from the reviewed Git index,
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
unverified. INC-QML-00 in [PLAN.md](PLAN.md) owns the next investigation.

## Development-standard review — 2026-10-03

[AGENTS.md](../../AGENTS.md) covers twelve discipline areas, GitHub pipeline
sequencing and the specialized upstream extractor-migration constraints.
Protected proof rules remain future policy; the standard does not establish
workflow protection or runtime language support.

The canonical requirements are in [docs/REQUIREMENTS.md](../REQUIREMENTS.md),
linked from the index, audit, design, plan, code reference and traceability.
A Python document check passed across eleven public foundation files:
all standard headings exist, local links resolve, the old requirements path is
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
revision. INC-QML-00 remains the first execution checkpoint, and all implementation
acceptance criteria remain unexecuted.


<a name="qml-03-hosted-proof--2026-10-03"></a>

## INC-QML-03 hosted proof — 2026-10-03

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

This verifies INC-QML-03 only. Later Qt changes require their own reviewed-head proof.


<a name="qml-04-local-proof--2026-10-03"></a>

## INC-QML-04 local proof — 2026-10-03

Reviewed source boundary starts at INC-QML-03 head `92f31658beceb5d36f570ae8e3820698b39381fb`.
Official upstream v8 was rechecked and remains
`0b60d47e6cd9338c51143f39f35b6c45c8453385`. No upstream Qt PR code was copied.

Windows Python3.12.14 focused QML/Qt+C++/cache/registry suite: **547 passed,
17 skipped** (host symlink permission, artifact env absent in that command, and
baseline optional language omissions). The actual wheel artifact suite separately
passed all3 cases. Whole-repository Ruff and lockcheck (210 packages) passed;
focused runtime/index/helper Pyright had zero errors/warnings. Baseline Windows
current-directory deletion defects recorded in INC-QML-03 remain unchanged limitations.

A clean Git-index source archive built the noneditable wheel with SHA256
`a4973256e987d9e75c89e54567350c0ff9af72384b2eed57ff19d173780d972e`.
Python3.12.14 isolated neutral-directory optional/core smoke both passed, including
native Qt emission with no QML parser in the core-only environment. The wheel
contains the internal metadata/index foundation; its public admission remains
INC-QML-05. Later Python/OS source lanes are owned by the forthcoming PR workflows.

The required repository graph refresh succeeded:19555 nodes,40020 edges and1065
communities. Existing unavailable optional-language warnings remain explicit.
Generated graph/report/cache/coverage data are excluded from commits.


<a name="qml-05-local-evidence"></a>

## INC-QML-05 local evidence

Windows Python3.12.14: 435 Qt/QML tests passed with6 documented skips before the
final duplicate-provider regression; extract/registry/admission245 passed8 baseline
optional-language skips. The final canonicalization fix passes independent facade
CMake/qmake native membership, duplicate module, qrc alias and accepted-target
regressions. INC-QML-06 tests still demonstrate ignore-only refresh gaps and remain
open. Ruff passes touched production/tests. The source refresh produced19701 nodes,
40531 edges and1066 communities before the final identity fix; a final refresh is
required before commit. Hosted INC-QML-04 runs37090713564/37090713525 were still running
when this local evidence was recorded; they do not prove the INC-QML-05 revision.

Final focused public admission/native/resource/type suite: 67 passed. Additional
index regressions retain same-target duplicate project declarations as ambiguous.
No acceptance is inferred from unfinished INC-QML-06 or INC-QML-07 cases.


<a name="qml-06-local-evidence"></a>

## INC-QML-06 local evidence

Windows Python3.12.14: policy/state/config/provider tests73 passed; the corrected
plain-C++ cache plus config/provider subset52 passed; actual code-only/extract/
QML publication CLI tests89 passed. An intermediate broad run1001 passed28 skipped
with a corrected plain-header cache regression and the two established Windows
WinError32 deleted-current-directory baseline failures. Final regression and worker
proof follow. Both INC-QML-04 and INC-QML-05 hosted CI and twelve optional/core wheel lanes
completed successfully for their respective PR heads; final INC-QML-07 proof remains.

Final worker/cache/native-root suite6 passed; compatibility fallback regression
plus worker suite7 passed after preserving the legacy helper invocation. Targeted
Qt policy/state/project/resolver typing reports0errors0warnings; whole Ruff passes.
The last broad regression1001 passed28skipped, with corrected helper invocation
and the two established Windows deleted-current-directory failures. Their hosted
Linux proof remains required; no test or assertion was skipped to mask them.

<a name="qml-07-local-final-source-proof"></a>

## INC-QML-07 local final source proof

Windows Python 3.12.14, actual optional QML/MCP environment: all Qt/QML source
contracts **613 passed, 6 skipped** in 48.69s before the final explicit normal-edit
parity additions. Skips: two host symlink-permission cases, three artifact cases
without GRAPHIFY_QML_TEST_WHEEL in that source command, and one absent optional
SVG renderer. The actual HTTP and separate-process stdio protocol cases ran;
they are not direct tool-function substitutions. The artifact cases run separately
against the reviewed wheel. A Starlette/httpx deprecation warning remains visible.

Final affected/header-definition/HTML/report/query/HTTP/stdio consumer subset:
27 passed without skips. Export and SDK boundary regressions:83 passed with one
absent optional SVG skip. Search/query/serve regressions:187 passed with one
optional jieba skip. Generic affected/CLI path/query/explain/call-flow regressions:
63 passed. Generic extraction CLI/extraction/cache hooks:336 passed with16
documented baseline optional-language skips. Whole Ruff and lockcheck (210
packages) pass; focused new helper/test typing has zero errors and warnings.
Whole-repository baseline Pyright remains634 errors/4warnings; it is not claimed
green. The established Windows deleted-current-directory baseline defects remain
in the historical broad run; no assertion or skip was changed to conceal them.

Skill/guidance/platform tests:91 passed. Each generator validator ran separately:
--check (134 artifacts), --audit-coverage, --schema-singleton,
--monolith-roundtrip and --always-on-roundtrip all pass. New handwritten Python
files are below300 lines; measured legacy hooks are recorded in IMPLEMENTATION.md.
All exact traceability test references resolve; the seventeen requirement IDs
and sixty-eight acceptance IDs are retained. Public documentation/local-link,
private marker and credential-shaped text review is part of final delivery.

Final normal-edit parity, reviewed-source wheel digest, clean isolated optional/
core smoke, graph refresh and exact-head hosted CI remain separately recorded
gates. Earlier INC-QML-03/INC-QML-04/INC-QML-05/INC-QML-06 passes do not verify the INC-QML-07 revision.

The final real incremental parity additions pass all6 cases without skips. Both
actual manual update CLI and locked watch driver compare normal QML edits and
no-change updates with cold/warm clean extraction/build/JSON. Accepted named IDs
and unrelated Python facts survive. QML member/objectName changes leave C++ bytes
unchanged while removing4 obsolete property/invoke/lookup links and acquiring4
correct source-backed links; local shadowing removes context exposure. Complete
public facts and logical endpoint direction match clean output. Only derived
indexing/scoring fields are normalized; metadata, spans and confidence remain.

The source graph refresh succeeded:19890 nodes,41131 edges,1069 communities.
It is navigation data, not acceptance proof. Generated graphs/caches/reports and
local coverage artifacts are excluded from the public change. Final privacy/link/
stable-ID and new Python footprint review passes.

<a name="qml-07-reviewed-artifact-and-initial-hosted-correction"></a>

### INC-QML-07 reviewed artifact and initial hosted correction

Implementation head `5e73bacf5529f83d014b3709959ebd1784a62593` has reviewed
Git-index tree `0224d13a5eca209030b6c7873ac3fa052248dea0`. Its built wheel
SHA256 is `99c5d1030f8781eecb7bb73834bd27086fa0a6c16ed9a5f814173d230f4f42ed`.
Clean optional/core Python3.12.14 environments pass isolated `-I` offline smoke
from a neutral directory, including native QML_ELEMENT/CMake/QRC integration;
the actual built-artifact suite passes3 cases. Tree-sitter0.25.2 and optional
language-pack0.11.0 are recorded. These local passes do not fill hosted cells.

Final event mutation/removal additions pass2 cases (manual/watch); combined with
normal-edit/no-change/reverse-access parity,8 pass without skips. An independent
build/source-priority plus final-parity regression subset passes102 cases.
Final navigation refresh:19924 nodes,41264 edges,1095 communities.

[Draft fork PR5](https://github.com/SlinkyRamey/graphify/pull/5) is stacked on
INC-QML-06 head `9fd9cd0d13e601b8e716816020a761484db29b19`. Initial source head
`5e73bacf5529f83d014b3709959ebd1784a62593` tested merge candidate
`7229b127ee144b35426501467724e3c471c34b20`.
The first [wheel run37094103638](https://github.com/SlinkyRamey/graphify/actions/runs/37094103638)
passed the four Ubuntu installed-artifact lanes but exposed missing historical
Git objects in Windows/macOS source-guidance tests: checkout was shallow and the
frozen pre-split baseline could not be read. The wheel workflow now fetches full
history, matching the existing main CI source-policy job. Tests and frozen guards
are retained. This failed/obsolete run is not counted as final platform proof;
the corrected reviewed revision requires its own complete matrix.


<a name="qml-07-corrected-hosted-completion"></a>

## INC-QML-07 corrected hosted completion

Reviewed implementation/workflow head `235987b9a72e0353cbc9e8cf2c53c7ccd07fceed`; stack base `9fd9cd0d13e601b8e716816020a761484db29b19`;
synthetic merge candidate `bcd4d7b4bf9ac1ce91f9e25957d6599fda75f87d`.
[CI 37094308786](https://github.com/SlinkyRamey/graphify/actions/runs/37094308786) and
[wheel 37094308526](https://github.com/SlinkyRamey/graphify/actions/runs/37094308526)
are pull_request runs with successful conclusions. All four full Ubuntu Python
source jobs and all twelve Windows/Linux/macOS Python3.10/3.12/3.13/3.14 optional/
core wheel jobs succeed. The exact job test/skip and checkout evidence is recorded
below after reading logs; an overall security job with continue-on-error steps
does not establish absence of baseline findings.

Final review preserves17requirements/68criteria, correct public support limits,
privacy, local links and focused module ceilings. INC-QML-00..INC-QML-07 are complete within
the declared static profile. Documentation-only follow-up changes trigger fresh
PR checks, whose current head is available from
[PR5 checks](https://github.com/SlinkyRamey/graphify/pull/5/checks).
The fork PRs remain draft/unmerged; upstream acceptance and package release have
not happened. No additional increment is required for the agreed initial scope.

Direct inspection of all16 test job logs confirms actual checkout
`bcd4d7b4bf9ac1ce91f9e25957d6599fda75f87d`, distinct from the source head.
Full Ubuntu suites: Python3.10 has6919passed/16skipped/24warnings;
Python3.12 has6918passed/17skipped/19warnings; Python3.13 and3.14 each have
6918passed/17skipped/10warnings. Each Ubuntu wheel job has3artifact tests passed
without skips. Each Windows/macOS wheel job has622passed/3skipped: two optional
MCP module omissions in the wheel extra, and the absent optional SVG renderer.
Actual HTTP/stdio MCP cases execute in the full all-extras Linux source jobs and
the isolated local SDK proof. All12 wheel jobs include installed optional/core
offline smoke; no skip is counted as a pass.

The security job's two nonblocking commands exit1. pip-audit reports15 known
vulnerabilities in pip26.1.1, urllib3 2.7.0 and virtualenv21.3.3; all three exact
versions already occur in the imported upstream lock. Bandit reports4HIGH SHA1
and8MEDIUM findings; the reported statements are present verbatim in the imported
upstream revision. No new production HIGH statement is identified. These are
recorded existing findings, not a clean security scan and not a Qt parser issue.
They remain upstream dependency/security debt rather than being silently fixed,
hidden or treated as a passing scanner result in this feature change.

## INC-QML-08a native source compatibility

Local Windows Python 3.12.14 checks verify the bounded native syntax correction
and same-package upgrade behavior. They do not close the full installed-project
adoption profile or supply new reviewed-head hosted OS/Python evidence.

The focused command was:

```powershell
.venv/Scripts/python.exe -X utf8 -m pytest -q tests/test_qt_cpp_adoption_syntax.py tests/test_qt_cpp_syntax.py tests/test_qt_signals_slots.py tests/test_qt_events_boundaries.py --tb=short
```

Result: **63 passed**, one pre-existing Hypothesis warning, 3.09 seconds. The public
fixtures cover empty-brace parameter defaults, evaluated `Q_UNUSED` arguments,
original BOM/CRLF/Unicode byte spans, valid numeric separators and later
signal/member ownership. Malformed, inert and ordinary-C++ controls retain their
rejection or canonical behavior. Before the numeric correction, four valid cases
failed while three malformed controls passed; all seven pass after correction.

The upgrade/cache command was:

```powershell
.venv/Scripts/python.exe -X utf8 -m pytest -q tests/test_qt_cpp_upgrade_invalidation.py tests/test_cache.py tests/test_qt_incremental_policy.py tests/test_qt_analysis_state.py tests/test_qt_worker_cache_integrity.py --tb=short
```

Result: **135 passed / 8 skipped**, 9.94 seconds. All thirteen new upgrade cases
pass. The skips require host symlink permission and are not passes. Actual
production cache and CLI boundaries cover schema 6 retirement, policy epoch 2
refresh without source/package changes, accepted-input limits, plain-C++ warm
cache and byte-for-byte retention of prior cache/products after failure.

The final broad run used `.venv/qt-mcp-312/Scripts/python.exe -X utf8 -m pytest -q`
with every file matching `tests/test_qml_*.py`, `tests/test_qt_*.py` and
`tests/test_cpp_*.py`, including the upgrade and numeric regressions. The equivalent
explicit PowerShell selection for reproducing that test set is:

```powershell
$qtTestFiles = @(rg --files tests -g 'test_qml_*.py' -g 'test_qt_*.py' -g 'test_cpp_*.py')
.venv/qt-mcp-312/Scripts/python.exe -X utf8 -m pytest -q @qtTestFiles
```

Result: **716 passed / 7 skipped / 1 warning**, 76.98 seconds. Four skips require
an unavailable C++ executable/toolchain, two require host symlink permission and
one requires the optional SVG renderer. The warning is a Starlette deprecation.
Ruff passes for the seven changed files; targeted Pyright using
`--pythonpath .venv/Scripts/python.exe` passes the three production files with zero
errors/warnings. The lock check passes with 210 packages. The navigation graph
refresh succeeds with 20012 nodes, 41589 edges and 1100 communities; those counts
describe the Graphify repository, not an analyzed private project.

The clean reviewed installed wheel has SHA256
`083b0d0bd422d91cd55b724088af2aa1301251bdeefb4a46d796c350d11f8a47`;
its reviewed production tree is `5aa323e403481f5e57c9caad77b4e244fed470a6`.
Installed source analysis and query/explain/affected consumers retain the bounded
native facts, and a no-change CLI update preserves the graph. This is local
artifact/scope evidence, not execution of analyzed Qt code, whole-project
compatibility or closure of typed provider/service relationships.

Native-header classification remains a planned INC-QML-08a assessment: a C
dispatch can omit C++ facts despite a successful direct C++ parse. A bounded
classifier requirement, public positive/negative fixtures and production
installed-update proof are needed before admitting a correction. Remaining
qmake, provider/service, combined adoption and safety criteria remain open in
[traceability](../../tests/TRACEABILITY.md#planned-adoption-criteria).

## INC-QML-09 HTML export and overview proof

This section records the prior initial-selection revision: startup used the
ten-largest overview with Select All unchecked. Its test counts, source tree and
artifact digest remain evidence for that revision, not proof of current AC04.
Grouping/publication evidence for AC01–AC03 remains separately applicable.

The executed broad selection comprises every `test_qml_*.py`, `test_qt_*.py`,
`test_cpp_*.py`, `test_html_*.py` and `test_export*.py` file plus test_cli_export.py.
The clean reviewed artifact is selected by GRAPHIFY_QML_TEST_WHEEL.

```powershell
$testFiles = (Get-ChildItem tests/test_qml_*.py, tests/test_qt_*.py, tests/test_cpp_*.py, tests/test_html_*.py, tests/test_export*.py).FullName
.venv/qt-mcp-312/Scripts/python.exe -X utf8 -m pytest -q @testFiles tests/test_cli_export.py --tb=short -rs
```

Result: **921 passed / 7 skipped / 1 warning**, 113.38 seconds. Four skips require
an unavailable C++ preprocessor, two require symlink permission and one requires
the optional SVG extra. The warning is the existing Starlette deprecation.
The focused recovery/export/CLI/Qt payload selection passed 149 with no skips;
initial-view/legacy/Qt written-script selection passed 83 with no skips.
The three initial recovery cases failed before their production correction.
The new Node harness executes emitted selection/search/filter/reset code while
isolating the external vis network; it is not a browser layout/appearance proof.

Ruff passes the five changed code/test owners; targeted Pyright passes the grouping
owner and initial-view tests. The lock check resolves 210 packages. Required AST
navigation refresh succeeds with 20090 nodes, 41767 edges and 1041 communities.
Those are the Graphify repository's counts, not a private analyzed application.

Reviewed production tree: `b43624a4b933ca012e9430d90772cb72c0bc14d3`.
Clean installed-wheel SHA256:
`7dc82ac66a2d50880e537901f5f26e7ab7077b49cf6e9e1422ab3288fc5debc2`.
The installed production CLI at that reviewed revision exports an accepted large
unclustered graph into complete labeled communities, without changing its JSON.
Its default datasets contain only the bounded overview; prior full source data
remains available.
Private artifacts are retained outside this public repository. Source/fixture,
CLI, artifact and emitted-script evidence are distinct from browser visual,
other platform or hosted PR validation, which is not claimed for this revision.

## INC-QML-09 current selection policy

Current REQ-QML-019-AC04 requires Select All checked at startup and every exported
view node/edge active before layout. Large source graphs retain complete labeled
community aggregation and its supported cap. Overview is an optional ten-largest
subset with Select All unchecked; filters, search and all/none controls remain.
No saved camera/filter persistence or canonical graph mutation is introduced.
This checked-default criterion is **locally verified at the exporter/CLI and
emitted-script boundaries**, including the reviewed installed artifact. The prior
921-pass run and wheel digest above remain historical rather than establishing
the changed startup behavior.

The focused production command was:

```powershell
.venv/qt-mcp-312/Scripts/python.exe -X utf8 -m pytest -q tests/test_html_initial_view.py tests/test_html_community_recovery.py tests/test_export.py tests/test_cli_export.py tests/test_qt_graph_html_payload.py --tb=short -rs
```

Result: **157 passed**, no skips, 43.03 seconds. The new expectations first failed
with seven failed/one passed in 1.95 seconds; all eight initial-view cases pass
after correction within this selection. The emitted production scripts exercise
checked Select All, complete exported-view datasets before layout, optional
Overview and selection controls while isolating the external vis network.

With `GRAPHIFY_QML_TEST_WHEEL` selecting the reviewed artifact,
`tests/test_qml_wheel_artifact.py` passes **three cases**, no skips, 4.85 seconds.
Clean `uv build` and installation succeed. All 152 packaged Python payloads match
the reviewed source and installed artifact byte for byte. The actual installed
export has checked startup/all exported-view data verified through its emitted
script harness, preserving canonical graph JSON. Ruff passes the two changed
files, and targeted Pyright reports zero errors/warnings for the initial-view
tests.

Reviewed production tree: `bdbc86f2da6e199157c9504ee9fc5cdc86f3f186`.
Installed-wheel SHA256:
`bde373cac5c37657283df6cf2070c23d89703b77785e2d6f3041a75b0df9f964`.
The HTML owner remains 763 physical lines and the initial-view test owner is 234;
other recorded owner sizes are unchanged. Browser visual, other-platform and
hosted proof remain separate unexecuted evidence for this revision. This result
does not establish closure of separately investigated source or display cases.

## INC-QML-10 native source ownership

**Current result: 88 focused and 954 broad cases pass**, with seven documented
broad-suite skips. The final reviewed wheel, installed proof and accepted-context
contract appear below. Earlier ownership-only counts and artifacts are retained
as intermediate evidence.

**Intermediate proof before accepted-context correction.** Existing criteria
REQ-QML-008-AC02, REQ-QML-016-AC01/AC04 and REQ-QML-017-AC02/AC04 have new public
native-ownership regressions. The 78/944 counts and tree/wheel below precede the
accepted-context body-key correction; they are not its final proof. Earlier profile, syntax and HTML counts/artifacts
above remain evidence for their recorded revisions.

Production proof covers retained forward facts/IDs, unique complete-class
authority, accepted canonical header/implementation definition provenance and
member/emission/reverse-access ownership through graph build, serialization and
consumers. Negative cases include forward-only ownership, distinct complete-class
ambiguity, wrong file/line, conflicting qualification/signature and missing
canonical evidence. Genuine unsupported relationships remain unresolved; no
claim is made that every isolated Qt node should acquire an edge.

Qt policy epoch 3 with AST cache schema 6 unchanged refreshes the same package
version's ownership facts. The new upgrade cases exercise actual unchanged-source
CLI refresh and preservation of prior graph/manifest/stamp after a rejected native
candidate. Before the epoch correction, two upgrade cases failed because
`inspect.changed` stayed false, with two deselected, in 1.08 seconds. The public
ownership tests also reproduced four failing cases before their correction.

The focused command was:

```powershell
.venv/qt-mcp-312/Scripts/python.exe -X utf8 -m pytest -q tests/test_qt_cpp_owner_upgrade.py tests/test_qt_cpp_definition_ownership.py tests/test_qt_cpp_upgrade_invalidation.py tests/test_qt_analysis_state.py tests/test_qt_incremental_policy.py --tb=short -rs
```

Result: **78 passed**, 6.55 seconds in the intermediate focused run, including actual JSON
publication/reload assertions for namespace-scoped QML access. The new ownership module has 18 cases and the
owner-upgrade module has four. Source pairs, BOM/CRLF/Unicode spans, namespace
qualification, normalized paths, missing/foreign definition evidence, genuine
complete-class ambiguity, unsupported owners and unrelated plain C++ controls
exercise the actual extractor/facade/build/reload boundaries.

The reviewed artifact broad command was:

```powershell
$env:GRAPHIFY_QML_TEST_WHEEL = (Resolve-Path .venv/qml-10-wheels/graphifyy-0.9.74-py3-none-any.whl).Path
$testFiles = (Get-ChildItem tests/test_qml_*.py, tests/test_qt_*.py, tests/test_cpp_*.py, tests/test_html_*.py, tests/test_export*.py).FullName
.venv/qt-mcp-312/Scripts/python.exe -X utf8 -m pytest -q @testFiles tests/test_cli_export.py --tb=short -rs
```

Result: **944 passed / 7 skipped / 1 warning**, 102.58 seconds. Four skips require
an unavailable C++ preprocessor, two require Windows symlink permission and one
requires optional SVG support. The warning is the existing Starlette deprecation.

`uv build` produces `graphifyy-0.9.74-py3-none-any.whl`, installed in an isolated
environment without changing the package version. Intermediate reviewed production tree:
`3ee40bc9fa8b8c182664fa601ef2d5e68c2a078c`. Intermediate wheel SHA256:
`684b83764ec20cc2e24af0c0ae8fa3f9b9b02a5f38b8bbe02b3d25cc7ea13e32`.
All 152 Python payloads match reviewed source, wheel and installation with zero
mismatches. Ruff passes all seven changed production/test files. Explicit-runtime
Pyright passes with **zero errors and zero warnings**:

```powershell
.venv/Scripts/pyright.exe --pythonpath .venv/qt-mcp-312/Scripts/python.exe graphify/extractors/qt_cpp_mapping.py graphify/extractors/qt_cpp_exposure.py graphify/qt_event_index.py graphify/qt_qml_bridge.py graphify/qt_incremental.py tests/test_qt_cpp_definition_ownership.py tests/test_qt_cpp_owner_upgrade.py
```

An initial default-environment invocation could not resolve pytest imports.
Selecting the configured runtime corrected that environment mismatch; source and
assertions are preserved. The final required `graphify update .` also exits zero
after the publication/reload assertions. Production source and installed artifact
are unchanged. Measured new test
owners are 261 and 91 physical lines; production
mapping/exposure/event-index/bridge/policy owners are 233/131/111/110/114. This is
local Windows exporter/source/CLI/artifact proof; no new hosted or other-platform
result or runtime Qt equivalence is claimed.

### Accepted unchanged-context proof

Borrowed complete-class records retain exact producer `source_file`/`span`
alongside ID/name/definition authority. Without those fields, a repeated accepted
body acquired a different deduplication key from its fresh AST representation and
falsely competed with itself. The correction preserves body identity, immutable
context inputs and canonical class/member/emission ownership while retaining
real distinct-definition ambiguity.

Four positive context cases failed before correction, with three passed in
1.35 seconds under `.venv/Scripts/python.exe`; the warning was existing
Hypothesis behavior. The final context module has ten passing cases, including
three equivalent-path cases, direct collection and actual Qt pipeline/join/build/
JSON reload, namespace/qualified ownership, and distinct-body/legacy/missing
controls. Its physical size is 145 lines; exposure is 134 lines.

The current focused command was:

```powershell
.venv/qt-mcp-312/Scripts/python.exe -X utf8 -m pytest -q tests/test_qt_cpp_context_ownership.py tests/test_qt_cpp_owner_upgrade.py tests/test_qt_cpp_definition_ownership.py tests/test_qt_cpp_upgrade_invalidation.py tests/test_qt_analysis_state.py tests/test_qt_incremental_policy.py --tb=short -rs
```

Result: **88 passed**, 7.38 seconds. Ruff passes all eight changed production/test
owners; Pyright with the explicit configured Python runtime reports zero errors/
warnings for the same eight owners.

Final reviewed production tree:
`360b714402af8915c0b301f875c7a469733a02e0`. Rebuilt
`graphifyy-0.9.74-py3-none-any.whl` SHA256:
`b3266bb402ef1ef79287046d7c192df82c08ba3655a9497eb7b6dd9f5cc136d8`.
Clean `uv build` and isolated installation pass; all 152 Python payloads match
reviewed source, wheel and installation with zero mismatches. The installed
public-fixture CLI rejects damaged QML even with force/partial flags, preserving
prior published bytes; repair and repeated update succeed and restore the graph.
The first expanded broad run has **one failed / 953 passed / 7 skipped / 1
warning**, 105.89 seconds. The existing
`tests/test_qml_skillgen_guidance.py::test_qt_marker_does_not_sanction_unrelated_monolith_edits`
negative-control case failed when `tools.skillgen.gen._git_show` received a
nonzero Git baseline-read result for `skill-devin.md`, with no stderr. The
recorded commit/blob is subsequently readable by `git cat-file` and `git show`.
An isolated rerun of the entire guidance module passes **24 cases**, 2.70 seconds,
with no source or assertion changes. The read failure is not reproduced there;
its exact cause is unknown. The repeated full broad run passes **954 cases / 7
skipped / 1 existing warning**, 101.89 seconds, with no source or assertion edits
between the failed read and the confirmation run. Its command is:

```powershell
$env:GRAPHIFY_QML_TEST_WHEEL = (Resolve-Path .venv/qml-10-final-wheels/graphifyy-0.9.74-py3-none-any.whl).Path
$testFiles = (Get-ChildItem tests/test_qml_*.py, tests/test_qt_*.py, tests/test_cpp_*.py, tests/test_html_*.py, tests/test_export*.py).FullName
.venv/qt-mcp-312/Scripts/python.exe -X utf8 -m pytest -q @testFiles tests/test_cli_export.py --tb=short -rs
```

The same seven dependency/platform skips and Starlette warning are accounted for
above. Final Ruff and explicit-runtime Pyright include the new
`tests/test_qt_cpp_context_ownership.py` with the other seven owners; both pass.
`graphify update .` exits zero after all source/test changes. The final installed
source-only full/unchanged-repeat and HTML checks pass without changing the
accepted graph or view bytes established by the full-corpus ownership correction.
Browser/runtime, other-platform and new hosted proof remain unexecuted for this
revision. Policy 3 and AST schema 6 remain unchanged because the repaired body key
is internal record transport, not a new persisted fact contract.

## INC-QML-11 inherited-signal lookup gap

**Planned; not implemented or verified.** Recursive inheritance compatibility in
`QtEventIndex.inherits()` does not supply grandparent member candidates because
`member()` currently considers only immediate bases. Existing
REQ-QML-016-AC01/AC04 own the planned endpoint and persisted/incremental correction.
No new test command, artifact or successful criterion evidence is assigned to
this gap. [INC-QML-11](PLAN.md#inc-qml-11--inherited-qt-signal-endpoint-lookup)
records the bounded source/ambiguity controls and exit conditions.

## INC-QML-12 constructor canonical-ownership gap

**Planned; not implemented or verified.** The generic constructor boundary can
retain an accepted callable ID and definition provenance while using an implicit
placeholder class parent instead of the accepted complete header class. Native
emission/access ownership stays unresolved under its strict guard. Existing
REQ-QML-008-AC02, REQ-QML-016-AC01/AC04 and REQ-QML-017-AC02/AC04 own this separate
gap; ordinary-method and policy-3 proof above does not establish constructor
support. Public constructor/parameter/delegation and namespace/duplicate/foreign
controls, canonical parent correction, persisted/incremental output and epoch
impact remain unexecuted. No new artifact, successful command or future policy
version is assigned. See [INC-QML-12](PLAN.md#inc-qml-12--out-of-line-constructor-canonical-ownership).
