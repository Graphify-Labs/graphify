# Qt/QML upstream contribution

## Scope and revision ownership

The contribution adds bounded Qt 6/QML static analysis to Graphify's Python
pipeline. It targets upstream `v8` at
`35adf432b9d50f6f3d530ab5d7ec316819ef081c` (package 0.9.76).
The upstream PR records its exact source head, integration checkout and CI runs.

The complete fork checkpoint remains available at
[`82a4f29`](https://github.com/SlinkyRamey/graphify/commit/82a4f296446b4cc219ffecfe3345a037e9c362e4).
Its nineteen passing jobs prove that recorded integrated revision. They do not
verify the narrower contribution after scope changes. The contribution uses a
separate `codex/qml-upstream-contribution` branch in the same workspace and
preserves the earlier integration branch and history.

The contribution includes QML declarations and JavaScript scopes, module/member
resolution, supported native Qt declarations and event mechanisms, both QML/C++
integration directions, literal project/resource/type metadata, safe incremental
refresh, and preservation of those facts through graph consumers. Supporting
source-identity, direction, cache and atomic-publication changes remain because
these contracts depend on them. Optional parser packaging, generated Qt guidance,
regression fixtures and applicable platform validation accompany the feature.

Independent repository policy, Windows Codex hook serialization, and general
HTML community recovery/navigation changes are deferred to separate
contributions. Upstream installer and generic HTML selection/navigation behavior
remain their baseline contracts. Qt HTML metadata, tooltips and truthful
aggregate source-edge counts remain: REQ-QML-020's packaged-component links need
that count projection. Counts supplement the existing degree display; they do
not introduce partition recovery or a new selection mode.

| Contract | Contribution disposition |
| --- | --- |
| REQ-QML-001–018 and REQ-QML-020 | Qt/QML analysis scope; prior evidence remains revision-bound and the scoped head requires fresh applicable verification |
| REQ-QML-019 and REQ-QML-021 | General viewer features deferred; the source-count portion of REQ-QML-019-AC02 remains a REQ-QML-020 dependency, without completing that broader criterion |
| REQ-CORE-001-AC01/AC05 | Independent native hook feature deferred; historical fork evidence is not acceptance of the baseline installer |
| REQ-CORE-001-AC02–AC04; REQ-CORE-002–004 | Retained upstream compatibility, source-integrity prerequisites and applicable test infrastructure; named profile assignments exclude the deferred features |

No requirement identifier is renumbered, reused or silently weakened. The
[requirements](../REQUIREMENTS.md) and [traceability](../../tests/TRACEABILITY.md)
distinguish retained behavior, deferred contracts and source-specific proof.

## Related upstream implementation

The contribution addresses the analysis mechanisms requested in
[#1716](https://github.com/Graphify-Labs/graphify/issues/1716) and overlaps with
the open proposal [#1748](https://github.com/Graphify-Labs/graphify/pull/1748).
The submission review inspected that proposal at
`7b38d4c2e2226b1db826a26774c7a5f299b8d62f` on 5 October 2026.

Both proposals admit QML source and address objects, members, imports, Qt
declarations and C++ registration aliases. This contribution has additional
scoped module/provider authority, literal CMake/qmake/QRC/type metadata, supported
native connection/emission mechanisms, reverse QML-object access and
incremental/persistence/consumer contracts. Its optional parser is pinned
`tree-sitter-language-pack==0.11.0`, shared with Graphify's existing R/Erlang
extras. The inspected #1748 manifest instead uses `tree-sitter-qmljs>=0.3.1`;
its earlier Git-install description is historical.

The extractor, facade, engine and packaging files overlap. Combining the
proposals needs an explicit maintainer integration decision; neither proposal
is treated as absent work or automatically replaced. The source comparison is
not fresh execution of #1748 or certification of its contributor-reported tests.

## Review order and evidence

Review the parser and source-fact contracts first, then QML resolution, native
Qt events, metadata and bidirectional bridges, followed by incremental ownership,
publication and consumers. [CODE_REFERENCE.md](CODE_REFERENCE.md) maps those
owners; [DESIGN.md](DESIGN.md) records identity, direction and persistence rules.

The scoped HTML exporter has 717 physical lines within a 760-line ceiling. Its
owner retains the upstream embedded template/aggregate boundary while adding
Qt metadata. Extract a characterized template or aggregate responsibility
before further growth. The CLI has 5,068 lines within its existing 5,090-line
ceiling; its owner retains dispatch and must characterize path-command extraction
before further growth. Upstream installer and exporter test bodies are restored;
the 1,617-line install suite retains its 1,640-line ceiling and only the portable
Hermes destination assertion differs from upstream. These current measurements
supersede frozen viewer/hook file-size measurements for this contribution.

The first broad local scope run passed 2,379 cases with 38 exclusions and found
one test dependency on the deferred generic inspector harness. The retained
Qt membership criterion still requires two external aggregate links and exact
internal/external source-edge accounting. Its correction uses the upstream
production inspector harness, preserves those assertions, and removes only the
startup-selection assertion assigned to deferred REQ-QML-019-AC04. Focused
corrected evidence and the new hosted run belong to traceability and the PR.

The corrected five-module consumer/membership selection passes 145 tests with
zero skips. Installer compatibility passes 265 tests with five capability/profile
exclusions. The final fresh wheel passes 138 platform/packaging/artifact cases
without skips; all 182 packaged Python files match the working-source bytes and
the three deferred modules are absent. Its SHA-256 is
`c9b413aac68289a2055baf1d70f7efda3fb1b8a4554ad7bb81b0ef6c94e90439`.
These packaging and boundary checks are local evidence, not hosted acceptance.
Fresh offline optional/core installations of that wheel also pass the isolated
production smoke on Windows/Python 3.12.14 from a neutral directory. The optional
profile executes QML extraction and native bridges; core-only reports the
documented missing-parser diagnostic while preserving unrelated extraction.
Whole-project explicit-interpreter Pyright still reports 605 errors and zero
warnings; it is not a clean typing gate.
Its file/severity/rule/message signature multiplicities are unchanged from the
recorded integration checkpoint.

The complete native source run reports 9,202 passed, 45 failed and 122 skipped.
All 45 failures select the inaccessible WindowsApps Bash alias or lack `sh` in
the test-process PATH, across hooks, shell admission and generated-path tests.
Within that run, all 137 Qt/QML modules report 2,392 passed, zero failed and 38
skipped. The incomplete bundled shell also leaves seven DLL/mapper setup failures
in its first focused retry. Complete portable Git for Windows 2.56.0 supplies
the required shell/mapping runtime; its official archive SHA-256 is
`eceb5e061aa90df2f69ddd3e90f0030e1b8037a7829934bc40e4be1caa1accc1`.
This local environment correction changes no production or assertions.
The affected-module rerun is a separate
result; it does not turn the original whole run into a passing run.
With the complete CI-compatible isolated/offline profile, four unchanged shell
modules pass 171 tests with zero failures and eight intentional Windows
exclusions. The profile uses Python 3.12.14, Bash/sh 5.3.15, cygpath 3.6.10,
Git 2.56.0.windows.1 and Node 24.19.0. All original failed shell cases are covered
by this corrected selection; the eight skips remain explicit applicability gaps.

Before publication, run focused retained Qt/consumer and installer compatibility
checks, generated-guidance checks, frozen packaging and document validation.
The normal upstream PR event owns the new hosted run. Fork runs and upstream
runs are recorded separately; maintainers may need to approve execution for a
first-time contributor. A green fork run does not establish upstream execution,
maintainer approval, a merge or a released package.

Whole-project typing and advisory security findings remain documented baseline
limitations. Skips remain exclusions with exact reasons. Source analysis does
not execute the corpus or require a Qt SDK; static facts do not prove runtime
signal delivery, object lifetime, thread safety, plugin availability or every
Qt API's semantics. Native browser/device/application checks remain separate.

Implementation and review used Codex. New contribution commits include the
repository's Codex co-author trailer. Seven historical commits lack that trailer;
the [audit](FOLLOWUP_AUDIT.md#contribution-and-collaboration-compliance) retains
the omission rather than rewriting published history.
