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

## INC-QML-12/13 current source and view evidence

**Bounded source implementation, regression and reviewed installed-artifact
evidence.** INC-QML-12 corrects the generic constructor
producer/canonicalization boundary; INC-QML-13 preserves native source-site/file
containment and clarifies community edge counts. These retain existing
REQ-QML-008-AC02, REQ-QML-010-AC02/AC04, REQ-QML-011-AC03/AC04,
REQ-QML-012-AC02, REQ-QML-016-AC01/AC04, REQ-QML-017-AC02/AC04 and
REQ-QML-019-AC02 identities. Exact criterion assignments are in
[traceability](../../tests/TRACEABILITY.md#constructor-and-source-containment-corrections).
The separate inherited-signal gap above remains planned.

### Source and rejection contracts

Generic constructor declarations retain callable identities and byte spans.
Only a unique accepted complete class, matching source-backed declaration/
definition/signature and extracted ownership proof establish the canonical
parent. Corrupted copied owner fields, conflicting parents, foreign scopes,
wrong source/line, non-callable nodes, malformed transport and invalid spans
cannot authorize it. Existing unrelated generic edges survive. BOM, CRLF and
Unicode fixtures compare spans with the original bytes.

Native member occurrences and function-local classes may be contained by an
independently proven canonical callable without claiming native class authority
or QObject exposure. If no callable owner can be proven, the final helper may
contain the source occurrence by its uniquely accepted canonical AST file.
Fresh canonical file IDs are passed explicitly before final AST provenance
tagging; borrowed context requires its persisted AST marker. Missing, duplicate,
foreign/out-of-root, semantic, callable/class and unmarked borrowed file records
cannot create that link. Original occurrence metadata, empty `owner_id` and
unavailable native target remain unchanged. This is source containment, not
evidence of signal delivery or a QML runtime object.

Supported ordinary/parameterized constructors have actual facade/build/JSON
reload, query and affected proof. Manual update/watch tests cover parameter
edits, emission removal, cold/warm/full parity, prior-product retention after
malformed-source rejection, corrected retry and no-change repeat. Duplicate
complete classes, foreign namespaces and collapsed overloaded delegation remain
unproved. In the unsupported overloaded fixture, generic untyped containment
already differs in source location between cold build and watch; typed Qt facts
and nodes agree. That existing exact-overload identity gap is retained separately
and does not weaken full normalized parity for supported constructors/members.

Six new modules exercise these production boundaries:

| Module | Evidence scope |
| --- | --- |
| `tests/test_cpp_constructor_ownership.py` | Direct generic producer/facade ownership, identity/signature, byte spans and corrupt/foreign/conflicting-proof rejection |
| `tests/test_qt_constructor_ownership.py` | Native emission and literal QML access ownership through actual assembly/publication/reload/query/affected, edit/removal and manual/watch failure/retry |
| `tests/test_qt_member_source_links.py` | Exact accepted callable containment without type authority, local source occurrences, immutable borrowed context, negative proof controls and actual JSON/HTML |
| `tests/test_qt_source_file_containment.py` | Real facade/source-file links for unresolved sites, accepted AST role controls, reload, refresh and stale-site removal |
| `tests/test_qt_source_links_upgrade.py` | Same-version CLI upgrade from policy/schema 3/6 and 4/7, unchanged-source reparse, unrelated Python, no-change parity and durable failure retention |
| `tests/test_html_community_links.py` | Production emitted inspector script and aggregate payload counts, escaping, immutable source graphs and supplied-meta/small-view controls |

### Red/green and compatibility evidence

The source-site suite initially had **7 failed / 12 passed** before its ownership
correction. A later actual facade source-file test had **1 failed / 54 passed**
because final AST origin tagging occurs after the Qt pipeline. Passing explicit
fresh AST IDs corrected that ordering; the current focused containment selection
has **63 passed**, 9.56 seconds. This earlier command preceded the last
source-file lifecycle/upgrade parameter additions:

```powershell
.venv/qt-mcp-312/Scripts/python.exe -X utf8 -m pytest -q tests/test_qt_source_file_containment.py tests/test_qt_constructor_ownership.py tests/test_qt_member_source_links.py tests/test_qt_cpp_definition_ownership.py tests/test_qt_source_links_upgrade.py --tb=short -rs
```

Final six-module source proof passes **90 cases**, 14.70 seconds, with no skips:

```powershell
.venv/qt-mcp-312/Scripts/python.exe -X utf8 -m pytest -q tests/test_qt_source_file_containment.py tests/test_qt_member_source_links.py tests/test_qt_source_links_upgrade.py tests/test_cpp_constructor_ownership.py tests/test_qt_constructor_ownership.py tests/test_html_community_links.py --tb=short -rs
```

An earlier 88-pass/two-failure execution of that selection in 12.95 seconds
exposed the unsupported generic overload source-location parity discrepancy.
A public comparison without the new augmentation reproduced the same baseline
discrepancy. The documented overload case now compares every node and typed Qt
edge; supported singleton constructor tests retain full graph parity. This gap
is planned under INC-QML-15, not recorded as verified exact-overload behavior.
Final source-file/upgrade proof passes **20 cases**, 6.06 seconds:

```powershell
.venv/qt-mcp-312/Scripts/python.exe -X utf8 -m pytest -q tests/test_qt_source_file_containment.py tests/test_qt_source_links_upgrade.py --tb=short -rs
```

No aggregate constructor red count was captured. Its retained regression
assertions cover the original missing prototype/implicit-parent failure and the
adjacent false-owner/corrupt-proof controls; the source-site and file-site red
counts above must not be attributed to constructor-only tests.

The HTML count regression first had **6 failed / 1 passed**, 2.72 seconds, before
the exporter/inspector change. The completed new module has **11 passed**, 1.96
seconds. The emitted production script runs in Node with the external DOM/vis
boundary isolated; this is executable payload/selection/inspector evidence, not
a new browser-engine visual acceptance run. The related production command was:

```powershell
$htmlTests = (Get-ChildItem tests/test_html_*.py).FullName
.venv/Scripts/python.exe -X utf8 -m pytest -q @htmlTests tests/test_export.py tests/test_cli_export.py tests/test_qt_graph_html_payload.py tests/test_qt_html_consumers.py --tb=short -rs
```

Result: **172 passed**, 42.36 seconds, with the existing Hypothesis collection
warning. Ruff passes the three viewer/test owners; explicit-runtime Pyright
reports zero errors/warnings for the viewer and new test module. Counts use
canonical NetworkX source edges, including represented directed/parallel edges
and self-loops. Internal edges do not become plotted aggregate loops. Distinct
neighboring communities, external source edges and internal source edges remain
different quantities. Pre-aggregated views lacking accepted source counts report
them unavailable; full small views retain ordinary Degree. Escaping, Select All,
display bounds and source graph/group/label immutability remain covered.

### Earlier reviewed artifact

An intermediate policy-4/schema-7 artifact passed **1029 cases / 7 skipped** in
132.39 seconds. Reviewed production tree:
`7ef6033868e56ae0bbddb170583826db48b20f05`. Wheel SHA256:
`206aaf4b7adb5660f1de78e0fb9aa6448c03367961ae97a90cce718977995b0a`.
All 153 Python payloads matched reviewed source, wheel and isolated installation.
Those seven skips retain the existing four unavailable C++ preprocessor, two
Windows symlink-permission and one optional SVG limits. This earlier artifact
does not contain the final source-file proof and does not verify policy 5.

### Final reviewed-revision gates

Current source policy is **Qt analysis 5 / AST cache schema 7** at the unchanged
package version. Old analysis policy invalidates derived source links; incompatible
AST schema retires stale generic constructor output. Real upgrade tests use the
production CLI and reader/cache path rather than replacing analysis behavior.
Current failure guards preserve earlier graph/manifest/stamp/root-marker bytes;
the new source link does not introduce a persistence writer.

The final broad command is:

```powershell
$env:GRAPHIFY_QML_TEST_WHEEL = (Resolve-Path .venv/qml-13-final-wheels/graphifyy-0.9.74-py3-none-any.whl).Path
$testFiles = (Get-ChildItem tests/test_qml_*.py, tests/test_qt_*.py, tests/test_cpp_*.py, tests/test_html_*.py, tests/test_export*.py).FullName
.venv/qt-mcp-312/Scripts/python.exe -X utf8 -m pytest -q @testFiles tests/test_cli_export.py --tb=short -rs
```

Result: **1044 passed / 7 skipped / 1 existing Starlette warning**, 137.43
seconds. The seven skips are the same four unavailable C++ preprocessor, two
Windows symlink-permission and one optional SVG boundaries; none is a passing
acceptance lane. The final artifact remains `graphifyy-0.9.74-py3-none-any.whl`.

| Final gate | Evidence state |
| --- | --- |
| Complete current source/test selection | 1044 passed / 7 skipped / 1 existing warning, 137.43 seconds; exact command above |
| Reviewed production tree identity | `0c65c34737aea316dcd879efb8e6d1a0ba6d9c0b` |
| Final policy-5/schema-7 wheel SHA256 | `04826d98f11c70edcfd694af169ba54624df107a2c10c07dbdc3cb9092821f95` |
| Source/wheel/isolated-install Python payload equality | All 154 Python modules byte-equal; zero mismatches |
| Installed public source-file/constructor/update/retention proof | Final isolated wheel CLI passes; malformed source with force/partial options exits 1 and retains four products; repair and repeat exit 0; no Qt source facts are isolated |
| Final Ruff and explicit-runtime Pyright | Commands below pass: Ruff clean; Pyright zero errors, warnings or information diagnostics |
| Traceability/validation document checks | 172 exact automated test references and 31 local file/fragment links resolve within these two documents; final review across all 11 modified public documents resolves 199 exact test references and all local file links; all 81 criteria assigned; public-pattern and diff checks pass |
| Required `graphify update .` | Final required invocation exits 0 |

The isolated installed interpreter executes the integration owner's offline
`verify-source-links-final-wheel.py` production proof. Its public fixture publishes
graph/manifest/analysis/root-marker products, then damages source, invokes the real
CLI with force/partial options, verifies rejection/byte retention, repairs source
and repeats the update. The final public graph SHA256 is
`028adf8e6fb4377ef3501d9c5c3686c6c72b90e5d487f63b14ca168c619b30fc`.
This installed fixture uses the final wheel, policy 5 and schema 7 rather than
the earlier 1029-case artifact.

An additional installed adoption refresh and default HTML export pass. The
resulting graph has no isolated Qt source facts; an unchanged repeat exits 0 and
leaves prior outputs untouched. The generated production viewer's actual script
harness confirms Select All and truthful internal-only community counters.
No private source, project identifier or machine path is retained here; no new
browser visual claim follows from that harness. This source-analysis check does
not complete REQ-QML-018's separate metadata/provider/whole-profile matrix.

Final lint/type commands cover the focused production owners and six new suites:

```powershell
$reviewedFiles = @('graphify/qt_source_containment.py', 'graphify/qt_qml_pipeline.py', 'graphify/qt_incremental.py', 'graphify/extractors/cpp_constructors.py', 'graphify/extractors/qt_cpp_exposure.py', 'graphify/extractors/qt_cpp_mapping.py', 'graphify/extractors/qt_cpp_events.py', 'graphify/extractors/qt_cpp_variables.py', 'graphify/exporters/html.py', 'tests/test_cpp_constructor_ownership.py', 'tests/test_qt_constructor_ownership.py', 'tests/test_qt_source_file_containment.py', 'tests/test_qt_member_source_links.py', 'tests/test_qt_source_links_upgrade.py', 'tests/test_html_community_links.py')
.venv/Scripts/ruff.exe check @reviewedFiles
.venv/Scripts/pyright.exe --pythonpath .venv/qt-mcp-312/Scripts/python.exe @reviewedFiles
uv lock --check --offline
git diff --check
git diff --cached --check
```

The lock check resolves 210 packages with no lockfile change. These scoped type
checks do not claim that the oversized legacy facade/extractor/resolver files
are free of their existing baseline type diagnostics. Additional cross-language,
cross-repository, C++ method and Objective-C guard compatibility passes 25 cases:

```powershell
.venv/qt-mcp-312/Scripts/python.exe -X utf8 -m pytest -q tests/test_cross_language_call_resolution.py tests/test_cross_repo_external_call_guards.py tests/test_cpp_method_declarations.py tests/test_cpp_objc_cross_file_calls.py --tb=short -rs
```

INC-QML-12/13 are locally complete for their recorded bounded source, artifact and
emitted-script contracts. No new hosted, other-platform, browser-layout or executable Qt proof is claimed. Broader
adoption provider gaps and INC-QML-11/15 remain explicitly unverified. INC-QML-14
was unverified at this policy-5 checkpoint; its separate policy-6 proof follows.

<a name="inc-qml-14-planned-membership-projection"></a>

## INC-QML-14 membership projection

REQ-QML-020-AC01–AC03 are **Locally Verified for the bounded static public
profile**. Earlier accepted
metadata/source/resource facts could resolve module and loader lookups in the
per-run index while only their owning metadata file contained them in the graph.
The new increment targets the missing graph route to declared, accepted source
files/components. Earlier truthful community counts and source-file containment
remain evidence for their existing contracts, not this new projection.

Each independent source-owned `membership_resolution` site retains the raw
declaration's identity, source/span, module/alias context, evidence and status.
Declaration containment uses `qt_membership_site`; a resolved site references its
actual accepted canonical endpoint with confidence `EXTRACTED` and context
`qt_project_source` or `qt_resource_membership`. Missing, competing, conditional,
generated and unsafe targets retain coverage with no target edge. Raw producer
facts, borrowed dictionaries and existing loader/module results remain unchanged.
Static package membership does not establish runtime import, instantiated QML,
architectural dependency or an evaluated build branch.

### Pre-fix production regression

The original `tests/test_qt_project_membership_updates.py` lifecycle selection
has **4 failed**, 3.76 seconds before membership projection. Both actual manual
update and watch variants have no membership sites in their initial published
public fixture. The test reaches the real extraction/assembly/persistence path;
it does not replace the resolver or CLI behavior. This establishes the missing
membership regression, not success of later mutation or failure-retention steps.
Only safe scenario/count conclusions from the local red log are retained here.

The actual facade positive CMake/qmake selection also has **2 failed**, 2.42
seconds when only membership projection is disabled and real parsing/index
behavior remains. Its sites are absent despite the accepted source declarations.
An earlier import failure while the new module was not yet present is not used
as product regression proof.

### Executed source tests and commands

The two new public modules are
`tests/test_qt_project_membership.py` and
`tests/test_qt_project_membership_updates.py`. The exact criterion-to-test map is
in [traceability](../../tests/TRACEABILITY.md#project-membership-projection).
Their executed assignment covers the following production boundaries. Earlier
development checkpoints remain tied to their own source/test state.

The integration owner's development lifecycle checkpoint reports **9 passed**,
8.57 seconds, including force rejection, fail-after-real-join retention, policy
refresh and aggregate inspection. The projection module's negative controls
still have failures under correction at that checkpoint. This partial selection
is not final reviewed-revision evidence or verification of any complete criterion.

A later development focused selection has **36 passed**, 8.74 seconds. The
development broad selection has **1071 passed / 10 skipped / 1 existing Starlette
warning**, 130.98 seconds. Three skips are built-wheel tests because
`GRAPHIFY_QML_TEST_WHEEL` was unset; the other seven are two Windows symlink,
one optional SVG and four unavailable C++ preprocessor cases. These are source
development results, not reviewed-wheel proof. The final typed-file punctuation/
published-context fixture follows that checkpoint. Investigation shows actual publication retains the raw punctuation
label, so an earlier escaped-label hypothesis is disproved; no production guard
is relaxed to accommodate that hypothesis.

The pre-direction-expansion source-projection checkpoint has **26 passed**,
1.90 seconds:

```powershell
.venv/qt-mcp-312/Scripts/python.exe -X utf8 -m pytest -q tests/test_qt_project_membership.py --tb=short
```

The helper and test file at that checkpoint are 187 and 276 physical lines. Ruff passes those
two owners; explicit-runtime Pyright reports zero errors and warnings. This is
source-projection proof, not the final combined lifecycle/artifact gate.

| Criterion | Executed source/lifecycle scope | Final evidence |
| --- | --- | --- |
| REQ-QML-020-AC01 | Public CMake/qmake and qrc fixtures, uniquely accepted file/component endpoints, independent/repeated declarations and same-name scoped paths, original BOM/CRLF/Unicode spans and punctuation, actual build/JSON reload/scoped query, unchanged module/loader lookup and serialized aggregate export/emitted inspector counts | Source/consumer and final reviewed installed public-fixture checks pass |
| REQ-QML-020-AC02 | Missing/duplicate/conditional/generated/unsafe/wrong-role and ambiguous alias controls, malformed literal transport/exact-location rejection, immutable borrowed facts and guarded target reads/discovery/process execution; real malformed-qrc manual/force/watch publication rejection with byte retention, repair and repeat; the actual projection helper executes before an injected completion failure | Explicit status/reason, source rejection and final installed retention/recovery checks pass |
| REQ-QML-020-AC03 | Cold/warm/full/manual/watch comparison, source edit/rename with updated metadata/alias, resource alias rename/duplicates/removal, target deletion, stale-edge retirement, stable unrelated Python and relocated-root identities, fresh-site replacement/publication without borrowed mutation, accepted typed-file identity through punctuation/publication, same-version policy-5 to policy-6 refresh and no-change repeat | Complete source/lifecycle/consumer, final broad compatibility and installed public-fixture checks pass |

The reviewed-wheel focused checkpoint below passes **37 cases**, 8.77 seconds,
with no skips (26 projection cases and 11 lifecycle/consumer cases). Two further
directed graph variants expand CMake/qmake positives to directed and undirected
actual assembly/JSON reload, checking the same logical endpoints and original
declaration spans. The identical focused command then passes **39 cases**,
9.50 seconds, with no skips (28 projection and 11 lifecycle/consumer cases):

The first two directed variants assumed JSON would retain redundant `_src`/`_tgt`
hints, which the established directed serializer omits because edge orientation
is structural. That incorrect test expectation is not product red proof. The
unchanged undirected assertions retain the hints; directed assertions prove the
actual site-to-target edge and absence of its reverse. No production behavior or
acceptance direction contract is relaxed.

```powershell
.venv/qt-mcp-312/Scripts/python.exe -X utf8 -m pytest -q tests/test_qt_project_membership.py tests/test_qt_project_membership_updates.py --tb=short -rs
```

The complete reviewed-wheel command passes **1081 cases / 7 skipped / 1 existing
Starlette warning**, 135.53 seconds:

```powershell
$env:GRAPHIFY_QML_TEST_WHEEL = (Resolve-Path .venv/qml-14-wheels/graphifyy-0.9.74-py3-none-any.whl).Path
$testFiles = (Get-ChildItem tests/test_qml_*.py, tests/test_qt_*.py, tests/test_cpp_*.py, tests/test_html_*.py, tests/test_export*.py).FullName
.venv/qt-mcp-312/Scripts/python.exe -X utf8 -m pytest -q @testFiles tests/test_cli_export.py --tb=short -rs
```

All three built-artifact tests execute with the reviewed wheel supplied. The
seven remaining skips are two Windows symlink-permission, one optional SVG and
four unavailable C++ preprocessor cases; no artifact test is skipped. These
results do not turn skipped lanes into verification. That broad execution
includes the earlier 37-case new membership selection. The two extra directed
cases have the separate final focused result above; no 1083-case broad run is
claimed. No production source or reviewed wheel changes follow this test-only
expansion. Current new helper/source-test/lifecycle-test sizes are 187/283/267
physical lines, within the 300-line ceiling.

### Current revision and exit evidence

The correction uses **Qt policy 6 / AST schema 7 / package version 0.9.74**.
Actual CLI extract/update tests show the policy bump refreshes earlier same-version
graphs even with unchanged source bytes; the AST schema and
graph/manifest/checkpoint writer remain unchanged.
The earlier policy-5/schema-7 artifact and its 1044-case result above stay tied to
that earlier revision and do not verify the membership correction.

| Gate | Current evidence state |
| --- | --- |
| Three individual criteria and two new source/lifecycle modules | Final 39 focused cases pass in 9.50 seconds; earlier wheel checkpoint has 37 passed in 8.77 seconds; original red lifecycle/facade failures retained |
| Related metadata/loader/native and unrelated-language compatibility | Reviewed-wheel broad selection: 1081 passed / 7 documented skips / 1 existing warning, 135.53 seconds |
| Same-version policy-5 to policy-6 refresh | Actual CLI extract/update tests pass with previous policy-5 state, unchanged source/package bytes, clean-rebuild equality and no-change repeat |
| Actual join/transport/publication failure, force rejection and recovery | Source manual/force/watch and fail-after-real-join tests pass; installed force/partial rejection retains four products and repair/repeat succeed |
| Final production tree | `a8656510281354913dcc92a3f733b70183874fbd` |
| Final wheel SHA256 | `221c7efa8db69e6cad048aea67d88fe3049cf98bae933816017aba833525dc6c` |
| Reviewed source/wheel/isolated installation equality | All 155 Python modules byte-equal; zero mismatches |
| Installed unused-component route and query/export/HTML | Public CMake/qmake/qrc fixture: 30 nodes, 31 edges, six resolved membership sites; query/explain/affected/HTML exit 0 and HTML leaves the graph unchanged |
| Final lint/type and lock | Five owners pass Ruff; explicit-runtime Pyright has zero errors/warnings in 2.29 seconds; lock check resolves 210 packages with no lockfile change |
| Required `graphify update .` | Exits 0; existing optional parser fixture warnings and Luau partial-fixture baseline remain explicit |
| Additional installed accepted-code-scope adoption | Refresh, HTML, query/explain/affected and no-change repeat exit 0 with the final wheel; no private source or identifiers retained and no whole-root/runtime claim |

The final five-owner commands are:

```powershell
$membershipFiles = @('graphify/qt_project_membership.py', 'graphify/qt_qml_pipeline.py', 'graphify/qt_incremental.py', 'tests/test_qt_project_membership.py', 'tests/test_qt_project_membership_updates.py')
.venv/Scripts/ruff.exe check @membershipFiles
.venv/Scripts/pyright.exe --pythonpath .venv/qt-mcp-312/Scripts/python.exe @membershipFiles
uv lock --check --offline
```

### Reviewed installed public procedure

The integration owner runs the ignored public-fixture script
`verify-membership-wheel.py` with the isolated noneditable installation's Python:

```powershell
& $installedPython -I -X utf8 $membershipProofScript
```

The two variables identify the provisioned isolated interpreter and that script;
machine-specific paths are intentionally omitted. Inputs are public static
CMake/qmake/qrc/QML/C++ fixtures. The script invokes the production CLI instead
of copying an accepted graph into place. Its six resolved sites are five project
source memberships and one resource membership. Query, explain, affected and
HTML commands exit 0, with no project execution or canonical graph rewrite.
It then damages qrc source and invokes the actual CLI with `--force` and
`--allow-partial`: exit 1 preserves graph, manifest, analysis stamp and root
marker byte-for-byte. Byte repair and repeat exit 0. The accepted public graph
SHA256 is `d9ce1b82fec2b092446416a5dc90c8de46de398b8087db23acc356e94bd24e62`.
That evidence is bound to the tree/wheel/payload identities above, Qt policy 6,
AST schema 7 and unchanged package version 0.9.74.

An additional redacted installed adoption check of the accepted code scope passes
refresh, HTML, query, explain, affected and no-change repeat, each with exit 0.
This is actual final-wheel source analysis, not an inference from the synthetic
fixture. It does not establish whole-root discovery, unresolved provider/parser
forms, application execution or browser appearance. Unrelated C#/cross-language
compatibility also passes **97 cases**, 4.05 seconds:

```powershell
.venv/qt-mcp-312/Scripts/python.exe -X utf8 -m pytest -q tests/test_cross_language_call_resolution.py tests/test_csharp_type_resolution.py tests/test_csharp_member_nodes.py tests/test_csharp_member_calls.py --tb=short -rs
```

No new hosted, other-platform, browser visual or executable Qt proof is claimed.
The [plan](PLAN.md#inc-qml-14--explicit-project-membership-relationships) owns
implementation and exit. Existing requirement/criterion identities, prior verified
revision evidence and broader adoption/inheritance/overload limitations remain
unchanged. The bounded public membership criteria are locally verified; the
additional accepted-code-scope adoption check passes, while REQ-QML-018's
whole-root/provider/parser and combined profile matrix remains unverified.

## INC-QML-16 middle mouse navigation and Overview removal

Status: **Locally complete for the emitted/installed HTML consumer profile**.
Native browser/device/platform interaction remains unverified. Acceptance: revised
REQ-QML-019-AC04 and REQ-QML-021-AC01–AC03. This consumer change does not invalidate
accepted source memberships or change Qt policy 6, AST schema 7 or package version
0.9.74. Previous Overview checks describe their original revision and do not
verify removal of that feature.

Red characterization runs actual exporter output through Node.js with external
DOM/vis APIs isolated. Before production changes, the combined selection/navigation
run reports **30 failed / 4 passed**, 4.42 seconds: 28 cases lack camera movement,
and two expose the retained Overview control and a falsely checked Select All
when ungrouped nodes remain hidden. The four retained startup/filter/search cases
pass. These failures establish the interaction and paired-selection regression;
the harness does not implement the production coordinate calculation.

The initial green selection/navigation run passes **34 cases**, 4.02 seconds.
Review requires actual community projection as well as source rendering and
additional unavailable-capture/invalid-input boundaries before final closure.
The first wider exporter run reports **3 failed / 168 passed**, 49.08 seconds.
Those three inspector tests model `window` as an empty object, lacking the real
browser event-registration API now required by emitted navigation. Extend that
external boundary while retaining the original inspector assertions, then rerun
the complete affected exporter selection. Do not hide those failures or claim
that an incomplete harness establishes browser compatibility.

Final commands and outcomes below bind the frozen source/test owners. The local artifact procedure builds the reviewed tree,
checks wheel contents against source and the isolated installation, regenerates
HTML with the installed CLI and proves unchanged canonical graph bytes. Actual
emitted-script movement/cleanup, default selection and source/aggregate inspectors
supplement that artifact identity check. No new browser visual, other-platform,
hosted or executable Qt proof is implied.

### Final local and artifact evidence

The final review restores retained source metadata, public Qt projection, initial
edge counts and endpoint-safety assertions independently of the removed Overview
expectations. No retained product assertion is weakened for this removal.

| Boundary | Executed result |
| --- | --- |
| Final focused controls/navigation | 60 passed, 6.57 seconds; 24 pan cases cover independent horizontal/vertical/diagonal movement, four scales and actual source/community exporters |
| Final exporter/CLI/membership/inspector regressions | 231 passed, 53.15 seconds; no failures or skips |
| Additional Qt HTML consumers and reviewed wheel | 7 passed, 4.60 seconds; no failures or skips; 238 distinct final selected cases across both runs |
| Inspector harness correction | Three former failures pass, 1.55 seconds; full legacy export file passes 67 cases, 2.95 seconds; assertions unchanged |
| Reviewed production tree | `a991dd9fb2d638cf15fbb2c76499ed1f6ebd51ea` |
| Wheel SHA256 | `11e370a19d328a01b4e9e30726731c815b4ef58399833ff3d0a7c644f71e98f0` |
| Reviewed source/wheel/isolated tool | All 156 Python modules byte-equal; zero mismatches |
| Installed CLI HTML export | Exit 0; Overview control/ranking/reset absent; initial Select All complete; actual emitted script camera moves, release/blur cleanup and retry pass; source inspectors retained |
| Source retention | Prior accepted canonical graph bytes and RAW nodes/edges/legend are identical after installed HTML regeneration; no re-extraction needed |
| File ceilings | HTML 789/810; helper 116/300; initial-view tests 245/300; middle-pan tests 223/300; inspector compatibility owner 1377/1377 |
| Ruff and type checks | Five touched owners pass Ruff. The four navigation/source/test owners pass explicit-runtime Pyright with zero errors/warnings. Legacy export tests retain one proven pre-existing error described below |
| Lockfile | Offline check resolves 210 packages; no dependency or lockfile change |

```powershell
.venv/qt-mcp-312/Scripts/python.exe -X utf8 -m pytest -q tests/test_html_initial_view.py tests/test_html_middle_pan.py tests/test_export.py tests/test_cli_export.py tests/test_html_community_links.py tests/test_html_community_recovery.py tests/test_qt_graph_html_payload.py tests/test_qt_project_membership_updates.py --tb=short -rs
$env:GRAPHIFY_QML_TEST_WHEEL = '<reviewed wheel>'
.venv/qt-mcp-312/Scripts/python.exe -X utf8 -m pytest -q tests/test_qt_html_consumers.py tests/test_qml_wheel_artifact.py --tb=short -rs
Remove-Item Env:GRAPHIFY_QML_TEST_WHEEL
$navigationFiles = @('graphify/exporters/html.py', 'graphify/exporters/html_navigation.py', 'tests/test_html_initial_view.py', 'tests/test_html_middle_pan.py')
.venv/Scripts/ruff.exe check @navigationFiles tests/test_export.py
.venv/Scripts/pyright.exe --pythonpath .venv/qt-mcp-312/Scripts/python.exe @navigationFiles
uv lock --check --offline
graphify update .
```

The wheel placeholder identifies the digest above rather than an arbitrary
same-version artifact. Package version 0.9.74, Qt policy 6 and AST schema 7 remain
unchanged. The final production subtree is compared with the reviewed tree before
handoff; documentation/test commits do not substitute for that byte binding.

Including `tests/test_export.py` in Pyright reports one existing
`reportOptionalOperand` at line 1008: the backup test uses an optional return as
a path without narrowing. The exact pre-change `HEAD` file reproduces the same
error under an explicit configuration that includes the ignored baseline copy.
The two-line growth at the inspector window API, line 1307, does not affect that
test. The baseline error is retained and disclosed; no assertion, type rule or
unrelated backup behavior is changed.

The required repository graph update exits 0 after source changes. Six existing
optional-parser fixture warnings and the deliberate Luau partial fixture remain
explicit; no model labeling or corpus execution runs. A final update after the
retained test assertions are restored keeps the local graph current.
The increment review adds no further scope. Broader adoption, inherited endpoints
and generic overload parity remain with INC-QML-08/11/15, and native browser/device,
other-platform and hosted proof remain unverified system gaps.

## INC-QML-17 receiver ownership and construction trees

The original A10/A11 production probes reproduce five failures and one retained
positive before correction. Ordinary collected regressions now cover receiving
object members, accepted source/native inheritance, readonly rejection,
recursive/direct-only QObject child lookup, duplicates, unknown/template types,
parenting changes, corrupt construction proof and unproved template casts.
The supported findChild type filter is exact `QObject*`; other casts remain
explicitly unsupported. QML lexical expression lookup remains unchanged.

The new native negative matrix also exposed a bounds-only native module namespace:
a rejected gadget supplied version bounds before provider admission, causing a
join exception. Bounds now belong only to accepted QObject providers. The plain
gadget regression passes without weakening its no-target assertion. The existing
reverse-update fixture now explicitly imports QtQml for its property-held QtObject;
all original member, direction, removal and parity assertions remain intact.

| Executed boundary | Result |
| --- | --- |
| Ordinary receiver/access/lifecycle source selection | 58 passed, 11.72 seconds; one existing Hypothesis warning |
| Reviewed wheel, separately installed host package and reused pinned test dependencies | 98 passed, 19.03 seconds; no skips or failures |
| Wheel SHA256 | `d2c6d9ac3d17e66cdc750af46ab138862846266bb77ecdb3aa2667087e18b363` |
| Reviewed source/wheel/installed Python payload | 156 modules byte-equal, zero mismatches |
| Real manual/watch lifecycle | Eight cases cover cold/warm parity, member/tree edits, stale-edge removal, policy upgrade, parse/join/actual replacement failure retention, repair and no-change repeat |
| Focused Ruff / explicit-runtime Pyright | Passing; zero type errors/warnings |

Artifact verification imports the separately installed wheel before pytest can
prepend the reviewed test tree, then exercises real extract/build/export/CLI/watch
and directed affected loading. It reuses the pinned test/parser dependencies;
it is not a new core-only, clean-extra, other-platform or hosted installation lane.
Policy 7 forces unchanged Qt inputs to refresh; AST schema 7 is unchanged.
The index/declaration/test owners measure 194/157/224 lines, respectively, under
their 300-line ceilings. Full current contribution gates are executed at the
INC-QML-20 integration boundary. Final aggregate evidence does not substitute for
the exact acceptance mappings in traceability.

The plan review retains INC-QML-08/11/15 and proceeds to INC-QML-18. No additional
increment is required by the bounded receiver correction. Dynamic Qt runtime
parenting, arbitrary casts and unavailable platform/system proof remain explicit.

## INC-QML-18 declaration identities and provider lifetime

The original disjoint-engine probe failed three exposure cases before the
correction. Ordinary collected source tests now cover exact local/parameter/auto
declarations, disjoint/nested shadows, conditional/deferred uses, writes, duplicate
declarations, expired providers, precise/mixed rejection diagnostics and original
BOM/Unicode/CRLF spans. Existing QML/native connection controls remain passing.

| Executed boundary | Result |
| --- | --- |
| Engine/provider/access source selection | 47 passed, 12.40 seconds; no skips |
| Reviewed wheel and separately installed host package, pinned test dependencies | 105 passed, 28.73 seconds; no skips or failures |
| Wheel SHA256 | `ed3e4b28a0bec54f95de455b7e5d88a8c2038c6974ec3e6ebfcb0acb816c74e7` |
| Reviewed source/wheel/installed Python payload | 157 modules byte-equal; zero mismatches |
| Lifecycle | Real manual/watch engine/load/provider edits and metadata/QML-only refresh remove stale bindings; forced malformed analysis preserves four products and repair/repeat succeeds; directed reload/query/explain/affected retains endpoints |
| Focused Ruff / explicit-runtime Pyright | Passing; zero type errors/warnings |

The reviewed artifact contains INC-QML-18 only, while disjoint native-alias work
remains unstaged. It imports the separately installed package before pytest adds
the reviewed test sources. The package lane reuses pinned test/parser dependencies;
no new clean-extra, native Qt, other-platform or hosted result is claimed. Policy
8 refreshes prior derived overlays; AST schema 7 remains unchanged. Full current
contribution gates run at INC-QML-20. Query rendering asserts public labels and
locations; exact persisted/affected endpoint IDs remain independently checked.

Plan review keeps factory/member provider admission, inherited endpoints and
overloads in INC-QML-08/11/15. The observed widget construction counterexample is
assigned to INC-QML-19's canonical-base integration under the existing receiver
acceptance IDs. No new increment is needed for these bounded scope corrections.

## INC-QML-19 lexical aliases and native construction authority

Ordinary collected tests promote A13, accepted-header shadows, comma-separated
typedefs and source-local using/namespace aliases. Header targets remain
unavailable; no preprocessing or SDK discovery is claimed. Widget/unknown-base
construction, corrupt native proof and shadowed QObject filters keep no target.

| Executed boundary | Result |
| --- | --- |
| Native aliases, lifecycle, existing events/registration/provider selection | 84 passed, 19.60 seconds; no skips |
| Native construction, receiver and real lifecycle selection | 88 passed, 20.09 seconds; one existing Hypothesis warning |
| QObject filter shadow RED → GREEN | Prior installed INC-QML-18 package: three false persisted targets, two controls pass; current source: five pass |
| Reviewed wheel and separately installed host, pinned test dependencies | 185 passed, 43.86 seconds; no skips or failures |
| Wheel SHA256 | `aea6cdad6126dd15e7552a5afb6800134a40b556b134f1e2df99e7912d6614a0` |
| Reviewed source/wheel/installed Python payload | 159 modules byte-equal; zero mismatches |
| Focused Ruff / explicit-runtime Pyright | Passing; zero errors/warnings |

The reviewed staged artifact excludes pending INC-QML-20 loader changes. Package
proof imports the installed wheel before test sources; pinned test dependencies
are reused, with no new clean-extra/native/other-platform/hosted result. Policy 9
refreshes old Qt overlays; AST schema 7 remains compatible. Current full
contribution gates follow at INC-QML-20.

Native class proof exposed an independent generic producer collision: global Base
and Public::Base in one file share a canonical ID. An ordinary negative control
retains ambiguity; separate-file qualified controls pass. INC-QML-21 plans the
canonical producer correction rather than inventing downstream IDs. Native
construction rejection does not claim the colliding form works. Wider adoption,
inherited endpoints and overloads remain in INC-QML-08/11/15.

## INC-QML-20 literal loader correction and contribution gates

Source review includes direct literal engine URL construction, component loadUrl/
create, exact component-owned context engine identity and bounded SDK URL/mode/
creation authority. Ordinary cases supersede the original loader audit probe.
Final rejection tests exposed ten further false-positive wrapper/mode cases and
three unsupported explicit-global controls before correction; all thirteen then
pass. Source-defined wrappers are not evaluated to inspect their return value.

| Executed boundary | Result |
| --- | --- |
| Final loader/provider/lifecycle/reverse-access/source-state/language selection | 99 passed, 21.70 seconds, no skips |
| Final overload/URL/mode wrapper module | 49 passed, 2.89 seconds |
| Reviewed staged wheel and separately installed host | 370 passed, 67.37 seconds; no skips/failures |
| Wheel SHA256 | `bdd78e676c3311af15c348be8e4db1658651d0a9969a97ff9794b5de412e854d` |
| Reviewed source/wheel/installed Python payload | 160 modules byte-equal; zero mismatches |
| Full contribution command `uv run --no-sync pytest tests -q --tb=short` | 72 failed, 7,148 passed, 177 skipped, 3 warnings; 572.27 seconds |
| UTF-8 module-entry production recovery selection | 29 passed, 2 skipped, 1 existing warning; 7.77 seconds |
| Remaining exact 60 failure cases, current / original `1128205` baseline | 60 failed / 60 failed, identical failing case sets; 6.33 / 6.81 seconds |
| Full Ruff, reviewed source | Passing |
| Full Pyright canonical command, original comparison | 647 errors/4 warnings on baseline and correction source; all 651 diagnostics shared, zero added/removed |
| Focused changed-file Pyright | Passing, zero errors/warnings |
| Generated assistant contracts | 134 artifacts match; coverage, schema singleton and both round trips pass |
| Lockfile `uv lock --check --offline` | Passing, 210 packages |

The installed-wheel selection imports installed production before staged tests;
it reuses pinned test dependencies and does not establish clean-extra, native Qt,
other-platform or hosted proof. An initial artifact invocation referenced a
nonexistent parser-test filename and collected no tests; the corrected command
uses the actual parser-probe module. Its first isolated child lacked tree-sitter;
the reviewed host then installed the pinned offline parser dependencies. The
terminal 370-case run is acceptance; the environment failure remains recorded.
Package source is frozen before later follow-up development, so the wheel does
not include INC-QML-21/22/23. No parser/dependency/package contract changed.

The full pytest console command exposes Windows spawn entry-point and cp1252
issues. The faithful recovery uses `PYTHONUTF8=1` and `uv run --no-sync python -m
pytest -q` for exact process-pool, source-state, Unicode and language cases.
Two symlink checks remain explicitly skipped on this host. The one changed
diagnostic assertion now expects `reassigned_declaration` and an empty receiver
declaration ID; its no-target assertion is preserved. Loader lifecycle recovery
assertions bind idempotency to the repaired products, not an obsolete source mtime.

The remaining sixty failures reproduce individually on the original source with
the same Python runtime and `-X utf8 -m pytest -p no:cacheprovider --tb=short`:
29 unavailable bash/sh cases, five unavailable FIFO/Unix-socket/symlink fixtures,
two deleted-working-directory Windows fixtures, fourteen missing OpenAI/Solidity/
Visual-Basic dependencies, eight unchanged installer/platform expectations, one
Terraform Windows path expectation and one actual read-only replacement defect.
No assertion or required check is removed or weakened. Baseline equality is
compatibility evidence, not a successful full gate. INC-QML-23 owns the real
read-only retention defect; absent shells/dependencies are separate limitations.

Full typing also remains a failing gate. The baseline and correction comparison
uses identical basic-mode Python 3.10 project configuration and Pyright 1.1.409;
diagnostics compare relative file, severity, rule and message, allowing line shifts.
Explicit pinned-runtime checks likewise add no diagnostic. The final frozen
source check analyzes 585 files: 647 errors/4 warnings, 20.67 seconds; all 651
diagnostics match the original baseline, with zero added or removed. Local
diagnostic files and original-source archives remain ignored.

INC-QML-21/22/23 are separately scoped after the exit review. Broader adoption,
inherited event lookup and overload identity remain INC-QML-08/11/15; bounded
loader success does not imply every Qt SDK API or runtime effect is modeled.

## Follow-up source acceptance (INC-QML-21–27)

Baseline for the original reproductions is `1128205`; INC-QML-17–20 were committed
separately before these follow-ups. Local platform: Windows, Python 3.12.14,
tree-sitter 0.25.2 and language-pack 0.11.0. Tests use offline synthetic public
fixtures and production extract/build/update/consumer boundaries; no Qt application
or build hook runs. Final AST schema 9 and Qt policy 12 retire older same-version
qualified IDs, SDK-derived facts and handler parameter authority.

Focused commands use `python -B -X utf8 -m pytest -q <files> --tb=short`; the exact
file selections below retain test/criterion mappings in traceability. The full
gate and reviewed installed artifact are separate pending checks at this checkpoint.

| Increment | Executed source selection and result | Genuine reproduction/review boundary |
| --- | --- | --- |
| INC-QML-21 | qualified identity/proof/updates, construction authority, constructor ownership, nested/CLI, native definition/constructor ownership: 152 passed, 14.21 seconds; explicit optional-index type narrowing then 43 related cases passed | Initial 7 failed/1 passed; signature/proof controls corrected; 51 using namespaces initially fail while 2 remain ambiguous, then both pass without truncating authority |
| INC-QML-22 | reflection identity/updates and orphan controls: 131 passed, 45.63 seconds | 12 false-target rejections fail before the correction; strict watch parity initially exposes four orphan failures, corrected by INC-QML-26 |
| INC-QML-23 | atomic replacement/readonly caller, prior atomic/export/source-state/loader-update compatibility: 79 passed, 3 baseline platform skips, 18.41 seconds | Actual readonly destination failure reproduces on original source; injected landing/cleanup/second-restore faults preserve or explicitly retain recovery evidence |
| INC-QML-24 | SDK declarations, boundaries, provenance, updates and providers: 107 passed, 33.25 seconds. Included-header/SDK/native alias/definition/context/loader/reflection compatibility: 169 passed, 58.22 seconds | Eight direct forward controls fail; included-header correction then 20 failed/10 passed, promoted to 33 collected cases including transitive/order/unincluded/namespace/provenance/overflow |
| INC-QML-25/26 | final publication/setup/product/orphan selection: 65 passed, 1 host-symlink skip, 25.16 seconds; one subsequently added partial-setup cleanup regression passed separately | 16 initial caller failures; non-OS second rollback/cleanup 3 failures; setup 6 failures/2 controls, realpath 1 failure; exact old cache-entry bytes remain unchanged while new valid entries may be added |
| INC-QML-27 | native property notify, pure-QML formals and native notify update files: 58 passed, 21.81 seconds, no skips. Handler/adversarial/integration compatibility: 91 passed, 2 Windows-symlink skips; script/scope/native compatibility: 29 passed | Native notify 8 failed/11 passed; explicit-style 4 failed; actual native/QML/qmake lifecycle, manual/force/watch parse and post-graph manifest rollback now pass |

The final artifact re-executes the current combined selections; overlapping source
counts are not additive. Historical excluded probes remain baseline evidence only.
New handwritten files measure at most 288 lines at this checkpoint; touched legacy
ceilings and extraction exits are recorded in design. Ruff and bounded explicit-
interpreter Pyright checks pass for the owning changes. Final full typing retains
baseline comparison rather than assuming a clean project gate.

Peer review found and corrected real namespace-cap, included-forward, rollback
and setup diagnostic gaps. Documentation review verifies public manual wording,
exact test references, ownership, cache epochs and diagnostic recovery. Wider
adoption, inherited native signals and qualifier-aware event overload scope remain
INC-QML-08/11/15. No new hosted, other-platform, native Qt/device, clean all-extra
installation or process/power-loss atomicity evidence is inferred.

## Final local follow-up integration evidence

Reviewed source revision: `75a6c5123f3316f96c89df2a5133de05ccb68af4`. The five cohesive source commits are
`d854509` (INC-QML-21), `6a774de` (INC-QML-22/24), `3e2c01a` (INC-QML-23),
`a9b9c5a` (INC-QML-25/26) and `75a6c51` (INC-QML-27 and final cache epochs).
Each retains the required Codex co-author trailer. Shared requirements/design/
traceability records form the same change set. Later evidence edits affect only
documentation, not the reviewed runtime or tests.

### Installed reviewed artifact

The Git index was exported to an ignored review directory, built with
`uv build --wheel --offline --project <review> --out-dir <artifacts>`, and installed
into a separate Python 3.12.14 verification environment. The source checkout was
not moved. Wheel: `graphifyy-0.9.74-py3-none-any.whl`; SHA-256
`220c2fa7bc558885a96170ca3bc29853ed3e950fbc06e4a53b74066850e111f2`. All 165 Graphify Python payloads
are byte-equal across reviewed index export, wheel and installed package.

Declared core dependencies are installed; tree-sitter 0.25.2 and language-pack
0.11.0 remain pinned. PyYAML 6.0.3 is the existing source-suite dependency used by
the selected Markdown compatibility oracle, not a new declared Graphify runtime
contract. Its wheel was unavailable in the offline cache and was installed from
the registry for this verification environment only. No package manifests,
lockfile or parser dependency contracts changed.

The final real-file driver imports the installed package before tests, verifies
that import origin and supports Windows process-pool spawning. Command shape:
`python -I -X utf8 <installed-driver.py> <installed-package> <reviewed-tests>
<pinned-test-dependencies> <selected-tests>`. The 44-file selection includes all
new correction tests, prior receiver/provider/type/loader cases, native ownership,
handlers/scripts, atomic writes, public update/failure consumers and the complete
language-facade file. **1,198 passed, 52 skipped, 194.61 seconds**; no failing case.

Skips are explicitly unverified: three existing atomic mode/symlink cases, one
publication symlink-target case, two external-symlink QML admission cases and 46
language-facade cases requiring unavailable optional parsers. Collected identities
and progress outcomes agree for all 1,250 cases. These skips do not verify their
criteria/platform forms. Executed rejection tests cover the remaining ordinary
root/path/provenance boundaries; other-platform/native system proof remains open.

Earlier artifact invocations are not passing gates: the first had 1,195 passes,
52 skips and three harness/dependency failures (non-importable `python -c` pool
driver, missing core dependency in an isolated child, absent YAML oracle). After
the real-file driver and declared core install, 1,197 passed and the YAML case
still failed. The final frozen environment and unchanged assertions produce the
green result above. The source/wheel payload hash remains identical throughout.

### Contribution gates and compatibility limits

| Executed command/check | Final result |
| --- | --- |
| `PYTHONUTF8=1 uv run --no-sync python -m pytest tests -q --tb=short` | 7,558 passed, 59 failed, 178 skipped, 3 warnings; 728.80 seconds. All 59 failure IDs match the recorded original baseline subset; no added failures. The formerly failing actual read-only atomic replacement now passes. |
| `ruff check .` | Pass for the canonical current source. |
| `uv run --no-sync pyright --outputjson` | Failing full gate: 647 errors/4 warnings across 605 files, 19.809 seconds. All 651 diagnostics match the original canonical baseline; zero added/removed. |
| `uv run --no-sync pyright --pythonpath <pinned-python> --outputjson` | Failing full gate: 646 errors/6 warnings, 20.275 seconds. Zero added diagnostics; one original missing-build-import diagnostic is no longer present. |
| `python -m tools.skillgen --check` | 134 artifacts match committed and expected output. |
| `python -m tools.skillgen --audit-coverage`, `--schema-singleton`, `--monolith-roundtrip`, `--always-on-roundtrip` | All pass. |
| `uv lock --check --offline` | Pass; 210 packages resolved. |
| Public document checks | 22 documents; local links, exact tests and all 84 criterion assignments pass; no private-path/project/credential pattern. |

The unchanged full-suite failures comprise unavailable shell/platform fixtures,
deleted-working-directory Windows controls, optional OpenAI/Solidity/Visual-Basic
dependencies, installer expectations and a Terraform Windows path expectation.
Full pytest and typing are **not green**. No assertion, rule, required check or
fixture is removed or weakened to obtain the bounded correction result. Local
installed acceptance does not imply a clean all-extra or other-platform install,
new hosted validation, publication or merge.

### Graph navigation and increment exit

The required AST-only `graphify update .` completed after code freeze and before
this documentation closure. Durable output has 21,171 nodes, 45,426 edges and
1,055 communities; graph, HTML and report were written. Scoped `explain
ProductPublication` returns its source owner and caller links. Navigation uses
scoped graph queries and the report; source/tests remain correctness evidence.
Unavailable optional fixture-language parsers and the existing partial Luau
fixture are disclosed by the refresh, not treated as complete language analysis.

INC-QML-21–27 close their locally verified bounded correction scope. Plan review
retains existing INC-QML-08/11/15 and explicit SDK/runtime/platform/system exclusions.
No further concrete increment is confirmed by the completed peer review. The
exposure chapter and named macros have explicit mechanism/evidence mappings;
their review is not a promise to model every Qt API or runtime behavior.


## Remaining adoption delivery baseline

Local delivery continues from `5c0f2cab8bd8c14a7cb139c90997025b58f1c81c` on the
existing feature branch. Upstream v8 advanced to `48d7c0e` (v0.9.75); incoming
changes and the five existing stacked fork pull requests were inspected read-only.
No upstream integration, new pull request, publication or merge is performed by
this local delivery. Disjoint agents own native ancestry, constructor identity and
adoption joins; the integration owner owns shared docs, cache epochs and Git.

## INC-QML-11 inherited endpoints

The first real-facade grandparent regression failed before implementation:
`python -m pytest tests/test_qt_inherited_endpoints.py -q --tb=short` (one collected
case at that revision): **1 failed, 2.79 seconds**. Adjacent external typed-pointer
controls then exposed nonpublic inheritance authority:
`python -m pytest tests/test_qt_inherited_access.py -q --tb=short`:
**9 failed, 1.37 seconds** before the source-access correction.

The final dedicated command uses the pinned Python 3.12 environment:
`python -m pytest tests/test_qt_inherited_access.py
 tests/test_qt_inherited_endpoints.py tests/test_qt_inherited_updates.py -q --tb=short`.
It passed **43 cases, zero skips, 14.72 seconds**; integration-owner rerun passed
**43 cases, zero skips, 15.01 seconds**. These exercise original spans, exact
canonical members, complete-class rejection, diamond/role/signature ambiguity,
32-class bounds, public base access, durable JSON/query/affected, actual
manual/watch header/member/base edits, malformed input, real read-only manifest
retention, repaired retry and unchanged repeat parity. Ruff and targeted Pyright
pass; these targeted checks do not replace full contribution gates.

Policy 13 invalidates unchanged derived Qt analysis; this increment does not
change AST schema 9. The installed artifact and shared final gates remain pending
until the constructor/adoption source freezes. A source-only explicit emission
was lost after a header signal rename; an isolated ordinary-production regression
failed **1 case, 0.98 seconds**. INC-QML-28 now owns occurrence admission and its
separate lifecycle proof. That pending gap prevents whole native criteria from
being declared Verified on this lookup result alone.

## INC-QML-15 constructor signature identity

The generic producer assigns constructor signature IDs before deduplication.
Declaration/body joins require exact signature, source-range and complete owner
proof. Unsupported signatures retain distinct source occurrences and cannot
borrow another accepted callable. AST schema 10 and Qt policy 14 invalidate
earlier constructor identities; D20 defines the migration boundary.

The final agent selection passed **156 cases, zero skips, 27.08 seconds** across
constructor identity/type-authority/update, native consumer and ownership suites.
An adjacent angle-include alias counterexample first failed **2 cases, 0.97
seconds** and now rejects possible admitted source shadows. Peer review exposed
qualified `void` incorrectly normalizing to an empty parameter list: the ordinary
regression selection first recorded **3 failed, 38 passed, 2.27 seconds**. The
correction retains the plain-void and pointer/CV distinctions. Integration-owner
command `python -m pytest tests/test_cpp_overload_identity.py
 tests/test_cpp_overload_type_authority.py tests/test_cpp_overload_updates.py
 tests/test_qt_overload_consumers.py tests/test_cpp_constructor_ownership.py
 tests/test_qt_constructor_ownership.py -q --tb=short` passed **146 cases, zero
skips, 26.69 seconds**. Subsequent peer source-range rejection is part of this same
exact-span contract; its final result is recorded with the frozen integration.

Lifecycle checks use actual cache entries and durable products, including
signature edits/removal, unmatched definitions repaired by header-only changes,
parse rejection, Windows read-only replacement and repaired retry. A historical
name-ID fixture migrates unchanged sources through both update modes. Targeted
Ruff and Pyright pass. A broader pinned-environment compatibility run had one
missing-YAML-oracle frontmatter failure; this is an environment diagnostic, not
accepted source behavior. Final full gates and installed proof remain pending.

The promoted source-integrity probes first failed **3 cases, 0.82 seconds**.
The correction requires unique accepted-file size authority for every class and
constructor, plus strict original byte/point containment for prototypes and inline
bodies. It performs no source reread. The eight-module constructor/qualified-ID
selection passed **172 cases, 27.61 seconds**; final integrity and qualified
proof/update controls passed **46 cases, 3.72 seconds**, including 14 integrity
cases and real incomplete/dynamic include controls. Targeted lint and typing pass.
