# Qt/QML platform and artifact proof

This is a delivery matrix for [REQ-QML-001 and REQ-QML-014](../REQUIREMENTS.md),
not a claim that all Qt runtime behavior is statically resolvable. The project
declares Python `>=3.10`; the twelve advertised CI lanes below are the narrower
tested matrix. Python 3.11 is not a declared lane in this matrix.

The optional parser is `tree-sitter-language-pack==0.11.0` selected by
`graphifyy[qml]`. Record the Graphify, Python, tree-sitter and grammar/package
versions printed by each installed-artifact run. Parser origin/license and
selection evidence remain in [PARSER_DECISION.md](PARSER_DECISION.md). Qt 6.5/6.8
are source-syntax targets, with a bounded literal Qt 6 qmake metadata profile;
these jobs do not install a Qt SDK, compile or execute analyzed Qt applications.
They therefore cannot prove runtime dispatch, plugin availability or build success.

## Declared lanes and revision-specific evidence

| OS runner | Python | INC-QML-03 optional/core wheel result | INC-QML-04/INC-QML-05/INC-QML-06 optional/core result | Final INC-QML-07 result |
|---|---|---|---|---|
| ubuntu-latest | 3.10 | Passed | Passed at recorded heads | Passed at recorded INC-QML-07 head |
| ubuntu-latest | 3.12 | Passed | Passed at recorded heads | Passed at recorded INC-QML-07 head |
| ubuntu-latest | 3.13 | Passed | Passed at recorded heads | Passed at recorded INC-QML-07 head |
| ubuntu-latest | 3.14 | Passed | Passed at recorded heads | Passed at recorded INC-QML-07 head |
| windows-latest | 3.10 | Passed | Passed at recorded heads | Passed at recorded INC-QML-07 head |
| windows-latest | 3.12 | Passed | Passed at recorded heads | Passed at recorded INC-QML-07 head |
| windows-latest | 3.13 | Passed | Passed at recorded heads | Passed at recorded INC-QML-07 head |
| windows-latest | 3.14 | Passed | Passed at recorded heads | Passed at recorded INC-QML-07 head |
| macos-latest | 3.10 | Passed | Passed at recorded heads | Passed at recorded INC-QML-07 head |
| macos-latest | 3.12 | Passed | Passed at recorded heads | Passed at recorded INC-QML-07 head |
| macos-latest | 3.13 | Passed | Passed at recorded heads | Passed at recorded INC-QML-07 head |
| macos-latest | 3.14 | Passed | Passed at recorded heads | Passed at recorded INC-QML-07 head |

The INC-QML-03 snapshot is recorded in [VALIDATION.md](VALIDATION.md): reviewed head
`92f31658beceb5d36f570ae8e3820698b39381fb`, base
`0b60d47e6cd9338c51143f39f35b6c45c8453385`, tested synthetic merge
`a9fba56c165210880236a635d00a96e84e19f1aa`.
[Wheel run 37087772653](https://github.com/SlinkyRamey/graphify/actions/runs/37087772653)
passed all twelve lanes. The separate
[CI run 37087772631](https://github.com/SlinkyRamey/graphify/actions/runs/37087772631)
passed Ubuntu full-source suites: Python 3.10 had 6541 passed/16 skipped;
3.12/3.13/3.14 each had 6540 passed/17 skipped. Windows/macOS wheel lanes ran
249 QML source contracts each; Ubuntu wheel lanes ran three artifact contracts
alongside their separate full-source CI jobs. This historical proof covers
INC-QML-03. It does not verify later native Qt, build metadata, analysis stamps or
the new assistant runbooks.

The subsequent INC-QML-04/INC-QML-05/INC-QML-06 runs completed successfully for their respective
source heads, including all twelve optional/core wheel lanes and the main CI
matrix. These are historical revision-specific results; final INC-QML-07 proof does
not inherit them.

| Increment | Reviewed source head | Main CI | Optional/core wheel matrix |
| --- | --- | --- | --- |
| INC-QML-04 | `6e454b749b1dbbdfb6d30e31d4f70dee80f2a053` | [37090713564](https://github.com/SlinkyRamey/graphify/actions/runs/37090713564), passed | [37090713525](https://github.com/SlinkyRamey/graphify/actions/runs/37090713525), twelve passed |
| INC-QML-05 | `47b422b9438163fe273bb2ec01e950940420db50` | [37091318091](https://github.com/SlinkyRamey/graphify/actions/runs/37091318091), passed | [37091318124](https://github.com/SlinkyRamey/graphify/actions/runs/37091318124), twelve passed |
| INC-QML-06 | `9fd9cd0d13e601b8e716816020a761484db29b19` | [37092273563](https://github.com/SlinkyRamey/graphify/actions/runs/37092273563), passed | [37092273562](https://github.com/SlinkyRamey/graphify/actions/runs/37092273562), twelve passed |

Local INC-QML-07 consumer/export/assistant checks have executed; their commands,
skips and current-head limitations belong to [VALIDATION.md](VALIDATION.md).
All twelve implementation-head hosted cells pass. A source-head association does
not claim that the CI checkout is the raw head rather than its recorded synthetic
merge; exact checkout evidence is recorded in VALIDATION.md.

## Current acceptance procedure

The authoritative job is [.github/workflows/qml-wheel.yml](../../.github/workflows/qml-wheel.yml),
using [tests/qml_ci.py](../../tests/qml_ci.py). For every declared OS/Python pair:

1. Build a noneditable wheel from the reviewed source head and identify its SHA256.
2. Create two clean environments: the wheel with `[qml,watch]`, and the core wheel
   without the QML extra. Run from a neutral directory with isolated Python `-I`.
3. Run [qml_installed_smoke.py](../../tests/qml_installed_smoke.py). Its audit hook
   rejects network and child-process activity during analysis; record optional
   parser success, core parser-absence diagnostics and unchanged Python behavior.
4. Run the built-artifact contracts with `GRAPHIFY_QML_TEST_WHEEL` pointing at that
   wheel. Windows/macOS also run every `test_qml_*.py` and `test_qt_*.py`; Ubuntu
   runs the full source suite in the main CI job and artifact contracts here.
   The wheel environment has `[qml,watch]`; MCP/SVG tests may skip there when their
   extras are absent. The main Ubuntu CI installs all extras and exercises those
   applicable source contracts. Record skips separately from passing evidence.
5. Record source head, base, tested merge, wheel digest, exact resolved versions,
   command, status and skips. An unrun, failed, skipped or cancelled lane is not
   passing evidence. Rerun affected lanes after source or dependency changes.

The latest Windows local proof and baseline portability defects are recorded
separately in VALIDATION.md. A local pass cannot fill an unrun hosted cell.
Runner labels do not promise every CPU architecture, Windows configuration or Qt
version. ARM, Python 3.11, legacy Qt 5.15 semantic profiles, arbitrary Qt SDKs,
runtime-generated QML and dynamic plugin/build execution remain outside this
declared proof unless separately added and verified.

## Assistant source and generator exception

Qt/QML assistant guidance originates in the six reviewed source fragments under
`tools/skillgen/fragments/core/` and `fragments/references/shared/`. Generated
skills and `expected/` are regenerated, never edited independently. The AST
runbook reads the existing trusted `.graphify_root`, passes root/cache ownership
explicitly and gates before publishing AST JSON. Qt updates use the production
updater instead of the manual changed-file merge. Scoped AST IDs, bridge evidence
and mechanism distinctions survive semantic augmentation.
Read-only `inspect_qt_analysis` supplies ordered configured import roots and the
immutable native-refresh flag to the AST call. The AST stage does not commit the
analysis checkpoint; graph publication remains owned by CLI/watch.

`tools/skillgen/gen.py` is an oversized legacy owner, measured at **1450 physical
lines**, with a permitted ceiling of **1450** for this Qt integration. Owner:
Qt integration maintainer. Reason: the frozen monolith validator owns the exact
sanctioned source-guidance line set; moving its baseline policy during this change
would combine unrelated migration with the new instructions. The exception ends
when an upstream-coordinated extraction moves sanctioned predicates and their
characterization into a focused validator module while retaining frozen SHA,
heading, schema and roundtrip behavior. No arbitrary `[Qt/QML]` prefix is allowed.
[test_qml_skillgen_guidance.py](../../tests/test_qml_skillgen_guidance.py) executes
rendered AST publication and rejects unrelated prose/code drift.

Run the generator and each validator separately; a combined invocation returns
after its first selected validator and cannot prove the remaining checks:

```text
python -m tools.skillgen --bless
python -m tools.skillgen
python -m tools.skillgen --check
python -m tools.skillgen --audit-coverage
python -m tools.skillgen --schema-singleton
python -m tools.skillgen --monolith-roundtrip
python -m tools.skillgen --always-on-roundtrip
```


<a name="qml-07-completed-implementation-head-proof"></a>

## INC-QML-07 completed implementation-head proof

Reviewed source head `235987b9a72e0353cbc9e8cf2c53c7ccd07fceed`, base `9fd9cd0d13e601b8e716816020a761484db29b19`, PR5 synthetic merge candidate
`bcd4d7b4bf9ac1ce91f9e25957d6599fda75f87d`. [Main CI 37094308786](https://github.com/SlinkyRamey/graphify/actions/runs/37094308786)
and [optional/core wheel matrix 37094308526](https://github.com/SlinkyRamey/graphify/actions/runs/37094308526)
completed successfully for the pull_request event. All twelve OS/Python wheel
lanes and four full Ubuntu source lanes pass. Installed smoke uses neutral
directories, isolated interpreters and an offline audit boundary; native Qt
CMake/QRC exposure/load proof is included. The initial shallow-history wheel run
is a documented failure, not a passing cell.

This record covers the implementation plus corrected workflow. Documentation-only
follow-up commits are rechecked by the same PR workflows; the
[live PR checks](https://github.com/SlinkyRamey/graphify/pull/5/checks) identify the
current reviewed head. Earlier heads are not substituted for changed source.
