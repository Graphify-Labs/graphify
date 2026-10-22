# Acceptance traceability

Current criterion IDs use `REQ-QML-`; completion increments use `INC-QML-`.
[Legacy aliases](../docs/qt-qml/IDENTIFIERS.md) retain earlier evidence identity.
Recorded test identities retain their historical evidence; current renamed viewer
tests are mapped to their actual functions below. Source annotations keep their IDs.

The current catalog contains twenty-one requirements and eighty-five stable
acceptance criteria. REQ-QML-018 has seven criteria, including the separate AC07
header-dispatch contract; REQ-QML-019/020/021 retain four/three/three criteria.
INC-QML-00–07 hosted proof describes its original seventeen-requirement,
sixty-eight-criterion profile. Subsequent evidence does not retroactively broaden
those historical results.

INC-QML-11/15/08a/b/c and INC-QML-28–38 have current local source, update, consumer
and reviewed installed-wheel evidence. All seven REQ-QML-018 criteria are locally
verified for the bounded Windows x64/Python 3.12 profile. Individual assignments
and the [final local matrix](#final-adoption-delivery) distinguish passing cases
from wider platform, native interaction, live-service and runtime limitations.
The recorded full source run has 59 baseline failures and 178 skips, with no added
failure identities; full typing remains a failed baseline gate. The later
[Windows dependency follow-up](../docs/qt-qml/VALIDATION.md#windows-shell-and-optional-dependency-follow-up--2026-10-04)
clears 40 of those 59 in a selective rerun, retains 19, and exposes two previously
skipped hook portability assertions. It does not replace full-suite evidence.
Neither aggregate test totals nor skipped cases establish acceptance.

The separate [shared compatibility verification](#shared-compatibility-verification)
records `REQ-CORE-` behavior and the all-extras environment. The recorded native
Windows full run at `463ca32` has 8,818 passes, zero failures and 151 skips. Separate unchanged-
source profiles pass all 76 Node and seven preprocessor/wheel cases previously
skipped for setup. Later real Linux/service and native checks pass at the
[verified integrated checkpoint](#verified-integrated-hosted-checkpoint--8b6c9d2). The
59-failure run above is historical; its failure identities are cleared in the
current applicable Windows profile. Full typing still fails on existing errors.

The chronological records below preserve checkpoint evidence. Their older pending
statements, epochs and test totals describe the recorded revisions. Current
INC-QML-54 local source/artifact proof belongs to the
[corrected committed checkpoint](#committed-corrected-integration-checkpoint--67bb2022).
The [verified integrated hosted checkpoint](#verified-integrated-hosted-checkpoint--8b6c9d2)
remains hosted evidence for its earlier revision, with adoption evidence retained in
[validation](../docs/qt-qml/VALIDATION.md#final-adoption-delivery).
See [implementation limits](../docs/qt-qml/IMPLEMENTATION.md#final-adoption-delivery),
[export contracts](../docs/qt-qml/EXPORT_MATRIX.md) and
[platform matrix](../docs/qt-qml/PLATFORM_MATRIX.md).

## Shared compatibility verification

The Windows x64/Python 3.12 checkpoint installs all extras from the unchanged
lock with `uv sync --all-extras --frozen`; `uv pip check` reports 197 compatible
packages. Tree-sitter remains 0.25.2, HCL 1.2.0 and language-pack 0.11.0.
The [compatibility plan](../docs/COMPATIBILITY.md) records profile setup, exact
remaining system procedure, ownership, size ceilings and consumer limitations.

| Acceptance ID | Exact automated assignment | Checkpoint evidence and gaps |
| --- | --- | --- |
| REQ-CORE-001-AC01 | `tests/test_codex_hook_execution.py::test_req_core001_ac01_codex_hook_dispatches_spaced_native_launcher`; `tests/test_install.py::test_codex_hook_command_is_a_real_cli_subcommand` | Exact Cmd and Windows PowerShell 5.1 argument transports pass with a real selected launcher, failing PATH decoy and unsafe control; full-source and independent installed-artifact execution pass in the current native evidence below |
| REQ-CORE-001-AC02 | `tests/test_install.py::test_hermes_skill_destination_posix_uses_home`; `tests/test_install_references.py::test_gemini_install_references_all_resolve`; `tests/test_install_roundtrip.py::test_skill_roundtrip_at_real_destination` | Exact destination and Linux/Windows contract profiles pass locally; simulated platform selection does not prove another kernel |
| REQ-CORE-001-AC03 | `tests/test_skill_auto_refresh.py::test_every_stale_platform_is_refreshed_not_only_the_detected_one`; `tests/test_skill_auto_refresh.py::test_a_stale_gemini_skill_gets_the_warning_too` | Windows-adapted bytes and retained ambiguous shared copy pass; shared ownership isolation remains unresolved upstream |
| REQ-CORE-001-AC04 | `tests/test_uninstall_scope.py::test_bare_call_still_removes_global`; `tests/test_uninstall_scope.py::test_remove_user_skill_opt_in_with_project_dir` | Linux/Windows scope profiles and protected shared-dir retention pass; no new uninstall policy |
| REQ-CORE-001-AC05 | `tests/test_codex_hook_execution.py::test_req_core001_ac05_literal_expansion_characters_retain_launcher_identity`; `tests/test_codex_hook_execution.py::test_req_core001_ac05_missing_launcher_fails_without_path_fallback`; `tests/test_codex_hook_execution.py::test_req_core001_ac05_selected_process_failure_preserves_nonzero_exit`; `tests/test_codex_hook_execution.py::test_req_core001_ac05_reinstall_and_uninstall_preserve_unrelated_hooks`; `tests/test_codex_hook_execution.py::test_req_core001_ac05_unsupported_shell_rejects_before_settings_access`; `tests/test_codex_hook_execution.py::test_req_core001_ac05_shell_inspection_failure_retains_settings_and_backup`; `tests/test_codex_hook_execution.py::test_req_core001_ac05_command_length_boundary_retains_literal_identity` | Native Cmd/Windows PowerShell 5.1 executable identity, failure/retention and rejected serialization boundaries pass in full-source and independent installed-artifact execution. Synthetic length cases establish admission/retention, not a real long-path launch. Actual Codex event delivery and other PowerShell versions remain separate system gaps. |
| REQ-CORE-002-AC01 | `tests/test_filesystem_profiles.py::test_req_core_002_ac01_detect_rejects_nonregular_stat_modes`; `tests/test_filesystem_profiles.py::test_req_core_002_ac01_stat_failures_are_unreadable`; original real fixtures in `tests/test_non_regular_files.py` | Native admission/error seams and hosted real FIFO/socket cases pass at the verified 10cb15a checkpoint below; privileged device/link fixtures retain explicit capability exclusions |
| REQ-CORE-002-AC02 | `tests/test_filesystem_profiles.py::test_req_core_002_ac02_unavailable_cwd_rejects_before_artifacts`; `tests/test_filesystem_profiles.py::test_req_core_002_ac02_repo_root_recovers_cwd_and_publishes_graph`; `tests/test_watch.py::test_rebuild_code_deleted_cwd_without_repo_root_returns_false`; `tests/test_watch.py::test_rebuild_code_deleted_cwd_uses_graphify_repo_root` | Native simulated lookup-failure and real chdir/persistence pass; actual removed-CWD POSIX cases pass individually in all four 10cb15a Linux lanes below |
| REQ-CORE-002-AC03 | `tests/test_filesystem_profiles.py::test_req_core_002_ac03_unavailable_cwd_reports_root_reason` | Missing-root/chdir-denied assertions failed before correction; all three safe diagnostic categories pass after correction |
| REQ-CORE-003-AC01 | `tests/test_terraform_modules.py::test_same_named_directories_and_cross_file_references_stay_separate` | Both LF/CRLF cases pass exact four identities/references and exclude cross-directory targets |
| REQ-CORE-003-AC02 | `tests/test_terraform_modules.py::test_same_named_directories_and_cross_file_references_stay_separate`; `tests/test_terraform_modules.py::test_raw_extractor_scopes_ids_by_full_directory` | Production extraction, directed build and JSON reload pass portable paths, locations and scope; Terraform production unchanged |

Focused commands and results at the checkpoint:

- Final INC-CORE-05 consumer correction: `PYTHONUTF8=1 python -X utf8 -m pytest tests/test_codex_hook_execution.py -q --tb=short -p no:cacheprovider` passes 19 cases, with no skips and one existing Hypothesis discovery warning. Both actual Windows shells exercise the persisted command. Installer/settings-merge/hook characterization passes 143 cases with three existing profile skips; these selections overlap and are not added to the full-suite count.
- `pytest tests/test_install.py tests/test_install_references.py tests/test_install_roundtrip.py tests/test_skill_auto_refresh.py tests/test_uninstall_scope.py tests/test_codex_hook_execution.py -q`: 243 passed, five native symlink skips. Strengthened exact-launcher/subcommand follow-up: two passed.
- `pytest tests/test_hooks.py tests/test_skillgen_input_path_injection.py -q`: 143 passed, eight pre-existing profile skips. The final affected selection plus shell-identity helpers: 37 passed, no skips. All 20 hostile-path cases include reachable unsafe controls.
- `pytest tests/test_watch.py tests/test_non_regular_files.py tests/test_filesystem_profiles.py -q`: 198 passed, eleven profile/capability skips, one existing Hypothesis warning. Seven formerly failing impossible Windows fixtures now remain explicit system gaps; sixteen new portable cases pass.
- `pytest tests/test_terraform.py tests/test_terraform_modules.py tests/test_extractors_registry.py::test_terraform_migrated -q`: 42 passed, one unavailable symlink skip, one existing Hypothesis warning.
- `ruff check .`: passed. `python -m tools.skillgen --check`: all 134 artifacts match. Lockfile unchanged. Full native source and refreshed installed-wheel evidence supersedes the restart gap in the current record below; actual Linux execution remains pending.

These selections overlap and are not added into a full-suite total. Real filesystem
capability assertions, native hook consumer execution and live-service tests remain
separate from contract profiles and fake-provider boundaries. Full typing is a
separate gate and is not established by Ruff or selected tests.

### Current native source and artifact evidence — 2026-10-05

Frozen source: `463ca3226c4aec4390a1e931fb1be1582059d1ca`, Windows x64,
Python 3.12.14, all 197 locked source-environment distributions. The full source
command is the isolated driver's `pytest tests/ -q --tb=short -p no:cacheprovider
-rs --junitxml=<evidence>/full.xml`, using the explicit environment Python with
`-I -X utf8` and canonical source imports. The profile exposes portable Git
Bash/sh and a literal Python forwarding shim, isolates provider/home/install
state and disables installation fallback. Pytest returns zero: **8,818 passed,
zero failures/errors, 151 skipped, 20 warnings**, with 1,143.29 seconds wall time.

The original restricted PATH excluded the already installed Node and GNU C
preprocessor, and the reviewed-wheel variable was absent. Supplemental profiles
retain that same source/dependency revision and execute exact skipped IDs:

- Node 24.19.0: **76 passed**, zero failures/skips, 26.42 seconds.
- GNU `cpp` 13.1.0 and reviewed wheel input: **four Fortran preprocessor and three wheel cases passed**, zero failures/skips, 4.68 seconds. This compiler is a test oracle; Graphify analysis gains no compiler or Qt SDK runtime dependency.

The full-run counts are retained without adding these separate profiles. The
remaining 68 distinct initial skips are 63 Windows/POSIX capability or fixture
exclusions, two other-Python-version cases, one inapplicable obsolete bundle
fallback and two unavailable FalkorDB integration cases. Skips remain exclusions,
not passes. The hosted increment assigns applicable Linux/service cases explicitly.
The 20 warnings are nine clustering dependency warnings, seven Solidity parser
deprecations, two expected cache-rejection diagnostics, one Hypothesis collection
warning and one Starlette/httpx deprecation; no warning caused a failed assertion.

All three profiles retain HEAD, 667 Python-file fingerprints, source dependencies
and original coverage bytes. The canonical source-fingerprint map SHA-256 is
`36155c56557d2a52bb8384fa8964581de57cc22c9b5ec46703d0fb8f0916e291`.
Full Pyright 1.1.409 with the explicit source interpreter reports **604 errors,
zero warnings, 663 files**, exit one. Compared with immutable source `135d50b`
under the same dependencies/configuration, all 604 diagnostic identities match:
zero added and zero removed. The typing gate remains failed.

Reviewed wheel SHA-256:
`057c509296b9f6e25be1dd39b72f3d463f10cdccfb7a0b95836f510f016dd518`.
All 180 packaged Python payloads match current source bytes. Relative to the
earlier reviewed 179-module wheel, 102 differences are only LF/CRLF spelling;
newline-normalized source and parsed syntax differ only in `install.py`,
`watch.py` and the new `codex_hook_command.py`. Independent installed consumption
pins all Graphify imports to its 163-distribution runtime from a neutral directory:
**35 hook/filesystem cases pass**, with zero failures/skips. `uv pip check`
confirms compatibility. This is complementary installed-consumer evidence,
not a replacement for the earlier Qt/QML artifact matrix or a hosted result.

### Hosted acceptance assignments

The CI implementation and exact hosted execution remain separately reviewable.
Each job's JUnit artifact and GitHub conclusion must be read for the same tested
source/configuration revision; configuration validation alone cannot pass these
criteria. [Hosted procedure](../docs/COMPATIBILITY.md#hosted-runner-proof-procedure)
owns setup, revision identity, exclusions and recovery.

| Acceptance ID | Exact automated job/system assignment | Current evidence |
| --- | --- | --- |
| REQ-CORE-004-AC01 | `.github/workflows/ci.yml::test` four Python lanes; actual fixtures in `tests/test_non_regular_files.py`, `tests/test_cpp_preprocess.py`, `tests/test_qml_wheel_artifact.py`, `tests/test_falkordb_integration.py` | Hosted `10cb15a`: all four full jobs pass; required Linux/service/wheel regressions and exact corrected cleanup case individually pass. Explicit platform/baseline skips retain their assignments |
| REQ-CORE-004-AC02 | `.github/workflows/ci.yml::windows-compatibility`; exact CORE functions above and assigned HTML/installer/shell modules | Hosted `10cb15a`: 836 passes, 21 explicit skips, zero failures. All original shell failures and revised admission cases individually pass with retained consumer identity proof |
| REQ-CORE-004-AC03 | Source identity/readiness, pytest, retention, service cleanup and artifact steps in both CI source profiles; GitHub run/job/artifact read for actual checkout | Hosted `10cb15a`: all five API-digest-verified source archives retain identity/JUnit/integrity; native report includes exact two-shell consumer identities. Four real services/test graphs are confirmed removed |
| REQ-CORE-004-AC04 | CI trigger/permission/concurrency configuration review and hosted procedure's PR/recovery event audit | Normal PR events own both workflows; no duplicate dispatch. All four `10cb15a` source lanes finish successfully; earlier matrix cancellations remain historical incomplete evidence |

Local configuration review parses both workflows with PyYAML `BaseLoader`,
compiles each embedded Python block, checks extracted Ubuntu scripts with
`bash -n`, and parses the Windows script through PowerShell's
`System.Management.Automation.Language.Parser.ParseFile`. The CI workflow is
449 physical lines within its documented 450-line cohesion ceiling. Existing
triggers, Ubuntu matrix, skill-generation/security jobs and QML-wheel matrix/job
selection remain intact. Both workflow concurrency groups now use distinct run
IDs outside PR events. These are local configuration results, not hosted passes.

At first publication `3b005d3`, the delivery changes only CI and documentation
after the completed native run: all 667 Python-file fingerprints and 197 dependency versions match the
tested source, and original coverage bytes are preserved. `ruff check .` passes,
`python -m tools.skillgen --check` matches all 134 artifacts, and the document
check resolves every acceptance criterion and exact test reference. The graph
refresh is AST-only navigation maintenance, not additional acceptance evidence.

The first hosted source head `3b005d3` produced
[CI admission failure 37244260265](https://github.com/SlinkyRamey/graphify/actions/runs/37244260265)
before creating any jobs: job-level `env` cannot reference `runner.temp`.
Resolving the evidence directory inside each Ubuntu script from `RUNNER_TEMP`
preserves the same artifact location and also admits the independent cleanup
step after failed setup. Official checksum-verified actionlint 1.7.12 rejects
the original configuration with that context error and accepts both corrected
workflows with zero diagnostics, without suppressions. This semantic check
complements YAML/Python/native shell syntax; ShellCheck and Pyflakes were not
installed for the actionlint run. No Linux/service pass is inferred from the
admission failure or local correction.

At the same source head,
[QML wheel run 37244275402](https://github.com/SlinkyRamey/graphify/actions/runs/37244275402)
passes all four Ubuntu artifact lanes but fails the installed native-module
smoke assertion in all four Windows and all four macOS lanes. These are current
failed gates under investigation, not skips or passing platform acceptance.

### Canonical accepted-input identity — INC-QML-39

The first hosted smoke failure is reproduced locally with a real Windows
short-path alias. Canonical spelling passes; the unchanged installed smoke
fails through the shortened spelling before the correction. The membership
boundary now compares canonical contained input identity against the accepted
declaration. Stored lexical provenance, literal lookup, Qt policy 18 and AST
schema 12 retain their contracts. This local reproduction explains the Windows
failure; matching macOS temporary-directory aliases remain a hypothesis until
the corrected hosted lane passes.

| Acceptance ID | Exact automatically collected assignment | Evidence and limits |
| --- | --- | --- |
| REQ-QML-020-AC01 | `tests/test_qt_project_membership_aliases.py::test_req_qml020_ac01_real_parent_alias_preserves_smoke_and_cold_warm_identity` | Unchanged native smoke, canonical/alias/reanchored identity, immutable source bytes and warm unrelated Python cache; real Windows short path passes, portable parent symlink requires host capability |
| REQ-QML-020-AC02 | `tests/test_qt_project_membership_aliases.py::test_req_qml020_ac02_path_alias_cannot_authorize_foreign_source`; `tests/test_qt_project_membership_aliases.py::test_req_qml020_ac02_input_resolution_failure_is_bounded_and_preserves_facts`; `tests/test_qt_project_membership_aliases.py::test_req_qml020_ac02_conflicting_transport_retains_durable_products_and_recovers` | Outside-root/conflicting input and OSError/RuntimeError reject boundedly without changing facts; real manual/watch publication preserves graph, manifest, stamp and root marker, then recovers and repeats |
| REQ-QML-020-AC03 | `tests/test_qt_project_membership_aliases.py::test_req_qml020_ac03_alias_updates_remove_stale_membership_and_match_full_rebuild` | Real manual/watch build-declaration removal retires its stale site/edges, matches canonical full rebuild and repeats idempotently |

Before the production correction, the alias selection records five failures,
two passing rejection controls and seven unavailable-symlink skips. After the
correction, alias plus existing project-membership/lifecycle selections pass
48 cases with seven capability skips and one existing Hypothesis warning.
The seven skips are real directory-symlink capability exclusions on this Windows
host; they do not establish portable alias acceptance. The production owner is
198 physical lines; the new test module is 222, within the 300-line ceiling.
The frozen broader source selection passes 2,259 cases with nine capability
skips, two warnings and zero failures/errors in 527.19 seconds wall time. Its
command uses the isolated source interpreter with all `tests/test_qml_*.py` and
`tests/test_qt_*.py` files except the separately assigned wheel-artifact module,
then `-q --tb=short -p no:cacheprovider -rs --junitxml=REPORT`. All 668 Python-file
fingerprints, 197 dependencies and original coverage bytes remain unchanged;
the source-map digest is
`c2ad0bc662ab2780385766dd22fc56d0bf6a4f5cb059e4e960d61979b60878d4`.
The nine skips are the seven new and two pre-existing real-symlink exclusions.
The two warnings are existing Hypothesis collection and Starlette/httpx notices.
This selection overlaps earlier runs and is not added to their totals.

Fresh wheel SHA-256
`f6a3c7befa8cae62ef70a6d89649b64cdc409fb25056d2ee383166c7fe8be522`
contains 180 Python payloads identical to source, changing only the membership
owner relative to the preceding core-05 wheel. Ordinary QML and core-only smoke
pass in clean constrained installed environments; every loaded production module
comes from the independent installation. A near-root real Windows temporary
short alias fails with `QT_CPP_LIMIT`: shared facade normalization publishes
traversal source provenance for contained C++ files. The same case fails in fresh
source with and without the offline guard. INC-QML-40 owns this separate defect;
the native traversal rejection is correct and is retained. Complete installed
alias acceptance and corrected hosted proof remain outstanding.
Existing REQ-QML-004-AC04 and
REQ-QML-012-AC01/AC02 containment/failure assignments remain applicable; no
new corpus reader, persistence owner or diagnostic code is introduced.

On the frozen 198/222-line production/test payload, Ruff 0.15.14 passes and
targeted Pyright 1.1.409 reports zero errors/warnings. A fresh whole-project
comparison uses the same Python 3.12.14, 197 dependencies and typing configuration
for current source and immutable `135d50b`: both report 604 errors, zero warnings,
with exactly 604 shared diagnostic identities and zero added/removed. Current
source analyzes 664 files in 24.022 seconds; baseline analyzes 658 in 22.615.
Both whole-project commands exit one. The expanded alias coverage adds no typing
diagnostic; it does not pass the existing whole-project typing gate.

The failure-boundary review separately reproduces persistent OSError and
RuntimeError at the accepted CMake input after source/index creation, through
direct joins and manual/watch writers. Diagnostic construction resolves the
failed input again and rethrows its raw body, leaving later sources unannotated.
Manual exits one and watch returns false; graph/manifest/stamp/root-marker bytes,
repair and no-change repeat pass. The six opt-in probes fail the bounded-body
acceptance assertion. INC-QML-41 owns ordinary regression promotion and correction
for REQ-QML-012-AC01/AC02 and REQ-QML-020-AC02. This is a diagnostic gap; no data
loss is inferred.

### Canonical facade provenance — INC-QML-40

The owning normalization now decides containment from cached physical identity
before external fallback, preserving written/resolved endpoint key forms and
strict native traversal rejection. A nearby real alias is tested independently
of the older external helper's deep-path basename fallback. True external input
and a foreign implementation cannot become in-root membership/native authority.

| Acceptance ID | Exact automatically collected assignment | Local evidence and limits |
| --- | --- | --- |
| REQ-QML-020-AC01 | `tests/test_qt_facade_path_aliases.py::test_req_qml020_ac01_nearby_alias_preserves_generic_cold_warm_provenance`; `tests/test_qt_facade_path_aliases.py::test_req_qml020_ac01_nearby_alias_preserves_unchanged_native_smoke_and_mixed_graph`; `tests/test_qt_facade_path_aliases.py::test_req_qml020_ac01_nearby_alias_preserves_real_decl_def_provenance` | Actual generic/Python/C++/QML source identity, CRLF bytes, canonical/alias cold/warm graphs and real declaration/definition carriers pass |
| REQ-QML-020-AC02; REQ-QML-004-AC04 | `tests/test_qt_facade_path_aliases.py::test_req_qml020_ac02_foreign_implementation_cannot_supply_an_in_root_definition`; `tests/test_qt_facade_path_aliases.py::test_req_qml020_ac02_physical_external_source_keeps_external_policy_without_membership` | Explicit foreign input keeps external source policy/native rejection; no target membership or implicit discovery is added |
| REQ-QML-020-AC03 | `tests/test_qt_facade_path_aliases.py::test_req_qml020_ac03_nearby_alias_updates_retire_membership_and_generic_targets`; `tests/test_qt_alias_policy_upgrade.py::test_req_qml020_ac03_policy18_no_change_upgrade_retains_repairs_and_repeats` | Real manual/watch generic then metadata-only edits, stale target/site retirement, canonical full parity, unrelated Python identity and mixed/C++-only no-edit policy upgrades pass; failed candidate stamp publication retains the cohort and repair/repeat completes |

Original facade selection: four failed, one passed, five symlink skips.
Mixed and C++-only policy-upgrade selections each fail two cases under policy 18.
Final existing/new alias, policy and six unrelated source-portability/remap
modules pass **65 cases, zero failures/errors, fourteen symlink-capability skips**,
one existing Hypothesis warning, in 13.43 seconds. These selections overlap earlier
proof and are not added to full-suite totals. Policy 19 refreshes prior native/Qt
products at the same package/source version; AST schema 12 and persistence owners
are unchanged. Generic-only prior API products require an explicit forced rebuild.
The final 238/85-line test modules remain below 300; the facade's 8,997 lines stay
within its existing 9,010 ceiling. Current hosted alias/platform proof remains open.

### Failure-safe join diagnostics — INC-QML-41

Diagnostic context no longer rethrows a persistent input identity failure.
Guarded physical containment and lexical fallback are diagnostic-only; foreign,
unavailable, overlong, control and Unicode line/paragraph-separator labels use
an empty `source_file` string. Safe complete relative labels have a 160-character
ceiling and are never truncated into another apparent identity. Every affected
Qt/QML source retains the existing failure record; unrelated Python is untouched.

| Acceptance ID | Exact automatically collected assignment | Local evidence and limits |
| --- | --- | --- |
| REQ-QML-012-AC01 | `tests/test_qt_pipeline_failure_context.py::test_req_qml012_ac01_all_sources_keep_safe_context_after_join_failure`; `tests/test_qt_pipeline_failure_context.py::test_req_qml012_ac01_real_alias_uses_canonical_or_explicit_unavailable_context`; `tests/test_qt_pipeline_failure_context.py::test_req_qml012_ac01_injected_context_delimiters_are_explicitly_unavailable`; `tests/test_qt_pipeline_failure_context.py::test_req_qml012_ac01_context_ceiling_preserves_or_rejects_complete_relative_label` | Ordinary, OSError and RuntimeError joins annotate every source with exact bounded QML_RESOLUTION_FAILED fields; canonical/real alias and 160/161/control boundaries pass |
| REQ-QML-012-AC02; REQ-QML-020-AC02 | `tests/test_qt_pipeline_failure_context.py::test_req_qml012_ac02_persistent_failure_retains_products_and_repairs_without_leaking`; `tests/test_qt_pipeline_failure_context.py::test_req_qml020_ac02_foreign_transport_cannot_gain_authority_from_diagnostic_context` | Actual manual/watch QML_GRAPH_PRESERVED outcomes omit backend bodies, retain all four saved products, repair and repeat byte-for-byte; foreign transport/context cannot add authority |

Focused RED: **nineteen failed, three passed, three symlink-capability skips**,
4.90 seconds. Corrected focused profile: **22 passed, zero failures/errors, three
capability skips**, 6.11 seconds. Existing failure/membership/update compatibility
uses the guarded canonical Python 3.12.14 with all 197 locked distributions:
**136 passed, zero failures/errors, ten symlink skips**, one existing Hypothesis
warning, 115.19 seconds. These profiles overlap earlier selections and are not
combined into a full-suite total. The changed helper covers seven of seven
measured statements and two of two measured branches. Overall pipeline coverage
is 89%; remaining uncovered collector/index-diagnostic paths are unchanged.
The original coverage file is preserved; coverage evidence uses isolated storage.
The production/test owners measure 106/190 lines, within the 300-line ceiling.

### Final local alias artifact and contribution gates

The combined frozen INC-QML-39/40/41 candidate is built from 671 source/test/tool
Python files with canonical source-map SHA-256
`795659a2a35b41b71443ad89e07ee739bef0242d67a0d82b0b41fb79f9ac822b`.
Reviewed wheel SHA-256:
`f2a759cc6ae5dd11d61a73806baebb867ebe4a1929cf06328b1d0473924a6799`.
All 180 packaged Python payloads match source bytes; only membership, facade,
derived policy and pipeline differ from the preceding core-05 wheel. Clean
constrained extra/core environments use 40/30 compatible distributions from the
unchanged 197-version source snapshot. Every loaded production module originates
in that independent installation (128 extra/122 core modules).

Unchanged offline `-I` QML/core smoke and the real Windows near-root temporary
short-alias native smoke pass from a neutral working directory. Three ordinary
reviewed-wheel metadata/import/parser-boundary tests also pass, with one existing
Hypothesis warning. Artifact proof takes 9.32 seconds; Python is 3.12.14,
tree-sitter 0.25.2, C++ grammar 0.23.4, language-pack 0.11.0 and watchdog 6.0.0.
Source/dependency and original coverage bytes are preserved. This current artifact
replaces the failed first alias candidate for its profile; hosted proof remains open.

The same fresh optional artifact executes the three ordinary alias, policy-upgrade
and failure-context modules through `python -I -X utf8`, importlib-mode pytest and
an offline process/network guard from a neutral directory: **33 passed, zero
failures/errors/warnings, ten actual symlink-capability skips**, 10.71 seconds.
All 152 loaded Graphify modules originate in the artifact; only the test namespace
is supplied by the source checkout. Its 180 payloads and 40 dependency versions,
the source's 197 dependencies and original coverage bytes remain unchanged.
The first harness attempt placed fixtures under the checkout's ignored `.venv`
and records eight initial-build setup failures. Moving only its owned fixture
directory to the host temporary area corrects setup without changing production,
tests or assertions; both attempts are retained. Capability skips do not establish
Linux/macOS acceptance and these overlapping selections are not added together.

Ruff 0.15.14 passes the whole repository and all eight touched/new Python files;
all 134 generated skill artifacts match. Actionlint 1.7.12 accepts both corrected
workflows without suppressions. Document checks resolve every acceptance ID and
exact test reference. AST-only graph maintenance is navigation, not acceptance.
Targeted Pyright 1.1.409 on all eight files has 120 existing facade errors, exactly
shared with immutable `135d50b`; the other seven files have zero diagnostics.
Whole-project Pyright has **604 errors, zero warnings, 667 files**, exit one,
20.990 seconds: 604 shared and zero added/removed under identical Python,
dependencies and configuration. Typing remains a failed baseline gate.

### Hosted Windows application selection — INC-CORE-07

At source `f95366d`, the native compatibility job fails before pytest because
Get-Command returns two Node applications and `.Source` projects both paths.
The job retains dependency/import evidence only; identity, pytest exit, JUnit
and post-test integrity are absent. No native test acceptance is inferred from
that setup failure. Node and uv selection now retains one first-PATH application.

| Acceptance ID | Exact ordinary regression | Evidence and limits |
| --- | --- | --- |
| REQ-CORE-004-AC02 | `tests/test_ci_windows_tools.py::test_req_core004_ac02_workflow_executes_first_real_path_application` | Actual workflow expressions execute a copied preferred real Node/uv binary before the original; scalar path and Node process.execPath prove exact executable identity |
| REQ-CORE-004-AC03 | `tests/test_ci_windows_tools.py::test_req_core004_ac03_missing_workflow_application_has_no_fallback`; `tests/test_ci_windows_tools.py::test_req_core004_ac03_node_guard_rejects_real_incompatible_application` | Missing Node/uv and real uv named as Node reject through owning discovery/version expressions; no fake executable response or fallback |

Immutable historical workflow: **two failures, three passes**, 7.22 seconds.
Current workflow: **five passes, zero skips/failures/errors**, 13.38 seconds,
native Windows PowerShell 5.1, Node 24.19.0 and actual uv. The focused test is
109 physical lines; Ruff and whitespace checks pass. Original coverage bytes
are retained. Corrected hosted execution and its complete evidence remain pending.

### Native shell launch identity — INC-CORE-08

Hosted `38bf8cc` records 783 native passes, 33 failures and 20 skips. Its retained
artifact binds source/base/checkout, tools and unchanged 197 dependencies/source.
Ten hook and 23 skill input-security cases launch the WSL stub through a bare
Bash process name. A real direct probe confirms that PATH lookup selects Git
Bash while native bare launch invokes another executable. Existing absolute
preflight therefore cannot establish the ordinary Python consumer's identity.

| Acceptance ID | Exact ordinary regression | Observable outcome |
| --- | --- | --- |
| REQ-CORE-004-AC02 | `tests/test_shell_portability_helpers.py::test_req_core004_ac02_admitted_shell_runs_real_posix_command` | Both selected absolute shells execute real POSIX syntax; no GNU-only assumption is imposed on POSIX |
| REQ-CORE-004-AC02 | `tests/test_shell_portability_helpers.py::test_req_core004_ac02_native_cwd_shadow_requires_explicit_path_admission` | A real native CWD decoy shadows bare launch; configured-PATH selection excludes it until CWD is explicitly admitted |
| REQ-CORE-004-AC02 | `tests/test_shell_portability_helpers.py::test_req_core004_ac02_real_consumers_resist_native_cwd_shadow` | Actual hook Bash/sh and skillgen launchers preserve the admitted process identity and original result assertions |
| REQ-CORE-004-AC03 | `tests/test_shell_portability_helpers.py::test_req_core004_ac03_missing_shell_selection_is_rejected`; `tests/test_shell_portability_helpers.py::test_req_core004_ac03_invalid_shell_identity_is_rejected`; `tests/test_shell_portability_helpers.py::test_req_core004_ac03_unadmitted_shell_name_is_rejected` | Missing/invalid identity or unadmitted names reject before launch without global/system fallback |

The unchanged original consumer functions fail three real decoy regressions;
fifteen helper cases pass. Corrected ordinary shell/hook/skillgen selection
passes **161 cases, eight explicit Windows/POSIX profile skips**, with all
eighteen helper cases passing. Raw literal payload, hostile-input rejection,
legitimate path, nonexistent path and vulnerable positive controls are retained.
No subprocess-resolution adapter changes the process under test.

The complete revised workflow consumer block executes before collection through
the same helper: both actual Git shells prove the selected Python interpreter
and Node 24.19.0 executable identity. Source (682 Python files), 197 dependencies
and original coverage remain unchanged during this proof; the owned forwarding
shim is removed. Shared helper/test files measure 56/161 lines, hooks retain
1,600 and skillgen 222. Both workflows pass actionlint 1.7.12; all extracted
Bash/Python blocks compile, and complete native blocks parse in Windows
PowerShell 5.1 and pwsh 7.6.6. CI measures 467 within its documented 470 ceiling.
These are local consumer/configuration results; corrected hosted proof remains
assigned to the next normal PR event.

### Native artifact report retention — INC-CORE-09

Acceptance: REQ-CORE-004-AC03. Real source `f699b0f` native job
`111592305005` passes **836 tests, 21 explicit platform/baseline skips**, zero
failures/errors/warnings. JUnit individually passes all eighteen CORE-08 helper
cases, the original 33 shell regressions, all seven CLI cases and five CORE-07
selection cases. Artifact `11321839435` archive SHA-256
`634462cf980eaa47090d2d64109702473d6142678ccb655bbb4a0f8db3a8f51f`
matches GitHub's API digest. Source/base/synthetic checkout, tool versions,
197 dependency identities, pytest exit and source integrity are retained.
The real archive omits the generated `shell-consumers.json`; exact per-consumer
identity transport therefore remains unavailable despite passing preflight.

The one-line artifact inclusion correction leaves producer/test behavior and
permissions unchanged. Its meaningful system regression is the actual GitHub
archive read and report/profile identity verification described in
[the acceptance procedure](../docs/COMPATIBILITY.md#native-consumer-evidence-retention--inc-core-09).
This is a real external publication boundary, not a simulated or literal-only
pytest test. Prepared configuration is not a retained-report pass. The corrected
normal PR event must provide exact source/base/checkout and archive/record proof
before AC03 is verified; current intended runs finish before publication.

### Hosted source and optional-wheel checkpoint — f699b0f

[CI 37255744156](https://github.com/SlinkyRamey/graphify/actions/runs/37255744156)
and [QML 37255744181](https://github.com/SlinkyRamey/graphify/actions/runs/37255744181)
are normal PR attempt-one runs. Source head
`f699b0feb760ff0fc6347b3930cf79fa0b4a615f`, base
`f61827f42378f6e7feff05a1cb4cbbcab1736ca8` and actual synthetic checkout
`114824c6099ce6592f7fd025a291b129681bb445` are bound through API parent inspection,
job logs and retained source identities. Both runs are terminal before the next
correction is published; no duplicate dispatch or job retry is introduced.

| Profile | Actual outcome | Evidence boundary |
| --- | --- | --- |
| Ubuntu Python 3.12/3.13/3.14 | Each 9,007 passed, 112 explicit skips, zero failures; end-to-end install passes | Full source suite, real disposable FalkorDB and reviewed source wheel |
| Ubuntu Python 3.10 | 9,007 passed, 111 explicit skips, one cleanup-fixture failure; end-to-end install step omitted after failure | `test_inc25_partial_setup_cleanup_fault_retains_safe_recovery_evidence` does not inject its intended unlink failure on this interpreter |
| Native Windows Python 3.12 | 836 passed, 21 explicit skips, zero failures/errors/warnings | JUnit/integrity/archive evidence above; consumer report omission remains INC-CORE-09 |
| Optional QML wheel, four Windows lanes | Each 2,323 passed, three optional-extra skips | Platform source selection and unchanged isolated installed QML/core smokes |
| Optional QML wheel, four macOS lanes | Each 2,271 passed, 55 Windows/optional-extra skips | Platform source selection and unchanged isolated installed QML/core smokes |
| Optional QML wheel, four Ubuntu lanes | Each three artifact tests passed, zero skips | Unchanged isolated installed QML/core smokes also pass |

All 39 assigned co-owner/remap/discovery/CLI source cases and the exact two live
FalkorDB plus three wheel cases individually pass on every Ubuntu lane. All four
downloaded archives match their API digests. Each 182-payload wheel matches the
reviewed source Git blobs; checkout, tracked inputs, dependencies and wheel bytes
remain unchanged. Both test graphs are deleted and all four owned containers are
confirmed absent. The service has no mounted storage, Redis 8.10.2 and module
60001; readiness includes actual graph-list/query operations. Source runner tools
are Node 22.23.3, GNU cpp 13.3.0, Bash 5.2.21 and Git 2.55.0 on Ubuntu image
20260927.320.1. Exact skip identities and per-case JUnit remain in retained source
artifacts; an aggregate count does not turn a skip into acceptance.

All twelve QML jobs pass, including all 24 installed smokes. Its platform suites
run from the checkout and do not establish isolated installed origin for every
case. That workflow retains no wheel-digest/JUnit artifact; logs supply selected
module outcomes, not a fabricated per-case attestation. Windows/macOS Python 3.10
each retain two existing warnings. Skill generation passes all five validators
and 134 generated artifacts. Advisory security remains green by policy while
Bandit reports four High/eight Medium/109 Low findings and completed pip-audit
reports nine unique package/advisory identities across three packages. Their
baseline origin is not assessed; this is not clean security acceptance. Local
Pyright still fails with 604 exact baseline errors and zero added/removed errors.

### Partial-setup cleanup fixture portability — INC-QML-48

Acceptance: REQ-QML-012-AC02 and REQ-QML-018-AC06. Ordinary collected regression:
`tests/test_publication.py::test_inc25_partial_setup_cleanup_fault_retains_safe_recovery_evidence`.
The actual hosted Python 3.10 case fails before correction; native Python 3.10.21
reproduces that failure against unchanged production/test bytes, while native
Python 3.12.14 passes. Runtime inspection confirms the cached accessor bypass.

The corrected scenario patches production's actual `Path.unlink` entry point,
delegates real removal outside the exact rejected owned recovery target, and
requires that target's observed fault. Existing `GRAPH_PUBLICATION_CLEANUP`, public
message redaction, four accepted-product bytes and durable old-graph snapshot
assertions remain intact. Production publication and diagnostics do not change;
no resolver/schema/cache evidence is invalidated by this fixture correction.
Corrected ordinary native execution uses:

```text
PYTHON -X utf8 -m pytest tests/test_publication.py tests/test_qt_product_publication.py tests/test_qt_readonly_publication.py tests/test_qt_publication_stub_origin.py -q -ra --tb=short -p no:cacheprovider --junitxml=REPORT.xml
```

Python 3.10.21/3.12.14/3.13.15/3.14.7 each pass **82 of 83 collected cases**, with
one explicit actual file-symlink capability skip and zero failures/errors. Each
includes all 32 publication cases and 51 adjacent Qt publication controls; the
corrected cleanup case individually passes without a skip. Source production
origin is verified. Dependency inventories (43/197/40/40 respectively), production
and selected test bytes, original coverage and checkpoint HEAD remain unchanged
through the run. A separate byte-exact `f699b0f` fixture replay reproduces the old
3.10 failure against the same production boundary. Distinct retained red/fixed-stage
logs bind each run to its actual test bytes.

The final test has 297 physical lines and retains all four original assertion
ASTs, adding exact owned-target and exception-cause checks. Targeted Ruff 0.15.14
and Pyright 1.1.409 report zero diagnostics. Only this test file changes Python
bytes from the prior exact 604-error baseline comparison; its baseline/current
diagnostic sets are empty. Whole-project typing remains a failed baseline gate.
Document checks resolve all 99 criteria and exact references; AST-only graph
refresh completes. Production, dependency/wheel, error-catalog and architecture
contracts are unchanged, so no new artifact payload or schema is introduced.
Corrected four-lane hosted execution and retained-report transport pass at the
verified checkpoint below. Local counts and skips alone do not establish them.

### Verified hosted runner checkpoint — 10cb15a

[CI 37257724886](https://github.com/SlinkyRamey/graphify/actions/runs/37257724886)
and [QML 37257724896](https://github.com/SlinkyRamey/graphify/actions/runs/37257724896)
are terminal successful normal PR attempt-one runs. Source
`10cb15a028312f21a169760e5f059a8f4ddfbfba`, base
`f61827f42378f6e7feff05a1cb4cbbcab1736ca8` and actual tested checkout
`697437305a9f8959ed6022fad3c676b4714caa0e` match API parent inspection, all source
identities and job logs. These results verify recorded profiles; they do not
promise unexecuted device events, unrestricted Qt SDK semantics or later revisions.

| Executed profile | Passed | Explicit skips | Failures/errors |
| --- | --- | --- | --- |
| Full Ubuntu Python 3.10.22 | 9,008 | 111 | 0 |
| Full Ubuntu Python 3.12.3/3.13.16/3.14.8, each | 9,007 | 112 | 0 |
| Native Windows Python 3.12 | 836 | 21 | 0 |
| Four Windows QML source lanes, each | 2,323 | 3 | 0 |
| Four macOS QML source lanes, each | 2,271 | 55 | 0 |
| Four Ubuntu QML artifact lanes, each | 3 | 0 | 0 |

All 40 assigned Linux cases (the prior 39 plus
`tests/test_publication.py::test_inc25_partial_setup_cleanup_fault_retains_safe_recovery_evidence`)
and the exact two live FalkorDB/three wheel cases are individually present and
passed in every source lane. Each complete job also passes end-to-end installation.
All four archive digests match the API. Every 182-payload wheel matches the tested
Git blobs; source/configuration, dependencies and wheel bytes are retained.
Dependency counts are 185/195/174/174 for Python 3.10/3.12/3.13/3.14. Both test
graphs are deleted and every pinned job-owned service is confirmed absent, with
zero mounts and verified image/readiness identity.

Native artifact `11323730916` SHA-256
`98e8645f9fd208b6502c62ea687fa83c81b48c6e190d9698ce62b85ffe1977b4`
matches its API digest and contains the actual 412-byte `shell-consumers.json`.
Both admitted Git Bash/sh executables identify the selected checkout Python and
Node 24.19.0, agreeing with the real preflight's same-file checks and job/profile
identity. All 18 helper, 33 former shell-failure, seven CLI and five tool-selection
cases pass individually; 197 dependencies, source inputs and checkout stay
unchanged. Retained JUnit, pytest exit, archive identity and upload completion
close INC-CORE-09's evidence gap; a workflow literal is not that proof.

All twelve optional-wheel jobs and all 24 isolated installed QML/core smokes pass.
Its platform suites remain source profiles with logs rather than per-case JUnit,
wheel-digest/source attestation or dependency-integrity artifacts. Skip contracts
are unchanged: Windows has two optional MCP cases and one optional SVG case;
macOS additionally has 28 Windows-readonly and 24 Windows-native-alias cases.
Windows/macOS Python 3.10 each retain two existing warnings. Parser/dependency
identities and grouped skips are retained in job logs; unavailable evidence is
not converted into individual-case or isolated-origin claims.

All five skill validators/134 generated artifacts pass. Advisory security
continues to report four High/eight Medium/109 Low Bandit findings and nine unique
pip-audit package/advisory identities across three packages; both scans exit one
under the existing advisory policy. Local full typing retains 604 matched baseline
errors with zero added/removed, while the changed test's diagnostic set is empty.
These contribution/system limits remain distinct from the passing test profiles.

Published test Git blob `66dec42c98e1d1f52d736e36cb369e3f5acf5000` has LF SHA-256
`285a9561f3262e3f75f77e893132bfcc3fb59d5a00ea6ed019b2a2e75a795886`;
the native tested file has SHA-256
`27f0b19efc055039b1b71339432fb8c2d396de4aa8de9a440c6610cdd313953d`.
Only two CRLF endings differ. All 682 tracked Python files match tested content
exactly or by CRLF-to-LF normalization, with no unmatched file. Production Git
payloads are unchanged from `f699b0f`. CI blob
`66a508759924cb222adee7010156a092c2f2b37a` and QML-workflow blob
`fc432d5a747483f1dcb10de88e768eda91ef1b44` bind the tested configuration.
This completion edits documentation only; later review revisions retain their
own normal PR validation and recorded SHA. No new reproduced defect appears in
the exit review; INC-QML-49 remains unallocated and no merge/deployment occurs.

### Manual discovery and native fixture contracts — INC-QML-46/47

The `38bf8cc` hosted Linux older-policy cases fail because the fixture omits
followed-directory discovery. The real manual parser separately rejects that
option with exit 2. INC-QML-46 adds the explicit parser option and retains its
default false, while every alias upgrade entry point uses the same supported
profile. INC-QML-47 corrects only the short-parent parser-spy expectation under
the already accepted INC-QML-45 long-spelling contract. Exact lexical symlink
ownership and every existing cold/warm/native/ID/retention assertion remain.

| Acceptance ID | Exact ordinary regression | Observable outcome |
| --- | --- | --- |
| REQ-QML-011-AC01/AC04 | `tests/test_qt_update_discovery_profile.py::test_req_qml011_ac01_ac04_cli_default_and_optin_reach_real_publication` | Actual parser and nested rebuild receive false/true respectively and publish identical facts/products when corpus scope is unchanged |
| REQ-QML-011-AC01 | `tests/test_qt_update_discovery_profile.py::test_req_qml011_ac01_optin_cannot_discover_foreign_qt_provider`; `tests/test_qt_update_discovery_profile.py::test_req_qml011_ac01_cli_help_exposes_supported_optin` | Real foreign alias cannot admit a native provider; actual help exposes the option and default |
| REQ-QML-011-AC03 | `tests/test_qt_update_discovery_profile.py::test_req_qml011_ac03_invalid_cli_profile_refuses_before_rebuild_or_publication` | Four actual unknown-option/multiple-root orderings reject before rebuild and retain accepted graph/state/cache bytes |
| REQ-QML-020-AC03; REQ-QML-011-AC03/AC04 | `tests/test_source_alias_provenance.py::test_req_qml020_ac03_policy19_products_refresh_retain_and_recover` | Real manual/watch opt-in refreshes the old-policy cohort; staged failure retains products/stamp, then repair/full parity/repeat succeeds |
| REQ-QML-020-AC03 | `tests/test_source_alias_provenance.py::test_req_qml020_ac03_directory_symlink_requires_explicit_discovery_profile` | Real POSIX directory link remains excluded by default and appears only with explicit discovery; native Windows cannot supply this profile |
| REQ-QML-020-AC01 | `tests/test_qt_project_membership_aliases.py::test_req_qml020_ac01_real_parent_alias_preserves_smoke_and_cold_warm_identity` | Exact native long-parent or lexical symlink parser inputs, warm unrelated cache, graph/IDs/membership parity and unchanged source bytes |

Source command: environment Python `-X utf8 -m pytest` with the focused seven
cohort/discovery modules, `-q --tb=short -p no:cacheprovider`, retained JUnit.
It passes **70 cases, two actual file-symlink/POSIX-profile skips**; all seven
new CLI cases and both upgrade operations pass. Broader CLI/watch compatibility
passes **253 cases, five existing capability/profile skips**. The separate
membership source module passes **nine cases, seven actual file-symlink skips**,
with one existing Hypothesis collection warning. These overlapping profiles are
not combined into a full-suite total.

Fresh wheel SHA-256:
`52a9c79c59ca2c1f985b3900655a6acf9f55b866b616e3d7f33d7767c17e449a`.
All 182 Python payloads equal source and installation; only CLI/help differs
from the preceding `c815eef8` wheel. Unchanged isolated QML/core and actual full-
TEMP short-alias smoke pass. Twelve ordinary installed modules run through
isolated `-I -X utf8` Python, `pytest --import-mode=importlib -p no:cacheprovider`,
with a retained JUnit report and an offline audit guard. Only exact owned native
junction fixture setup is admitted; analyzed code and network execution remain
forbidden. Result: **118 passed, nineteen explicit skips, zero failures/errors/
warnings**, 43.80 seconds pytest. Eighteen skips are actual file-symlink capability
exclusions; one is the POSIX default-discovery profile. All 69 assigned new/prior
co-owner/spelling/CLI/upgrade/native warm-input cases pass individually with no
skip. All 154 loaded Graphify modules come from that artifact. Source (682 Python
files), source 197/optional 40/core 30 dependency versions and original coverage
are retained; owned fixtures are removed.

Ruff 0.15.14 passes targeted/full source checks. Pyright 1.1.409/Python 3.12.14
reports **604 errors, zero warnings, 678 files**. The fresh immutable `135d50b`
baseline has 604 matching errors across 658 files: zero added or removed.
Ten touched targets retain two exact existing errors, with zero new/removed.
Typing remains a failed gate. Current CI consumer/configuration proof is recorded
above; repository AST-only refresh completes with 22,641 nodes/51,218 edges and
the existing deliberately malformed Luau fixture warning. No further local gap
is reproduced; the corrected normal PR event owns hosted acceptance.

### Discovered source identity — INC-QML-42

Hosted f95366d fails the unchanged original tests
`tests/test_cache.py::test_warm_cache_keeps_target_and_symlink_sources_distinct`
and `tests/test_watch.py::test_rebuild_code_incremental_rename_preserves_symlink_source_path`
in both completed Linux pytest profiles. The correction preserves their assertions;
actual Linux replay remains assigned to the corrected hosted run. Local actual
NTFS directory junctions reproduce six initial failures with one passing control
and one unavailable file-symlink case; stronger dual-alias assertions also expose
the shared prefix/stem lookup collapse and remain ordinary regressions.

| Acceptance ID | Exact ordinary test | Source/installed checkpoint evidence |
| --- | --- | --- |
| REQ-QML-020-AC01 | `tests/test_source_alias_provenance.py::test_req_qml020_ac01_discovered_directory_sources_survive_cold_warm_and_reload`; `tests/test_source_alias_provenance.py::test_req_qml020_ac01_leaf_alias_retains_its_source_below_an_aliased_root`; `tests/test_source_alias_provenance.py::test_req_qml020_ac01_native_definition_keeps_discovered_directory_provenance` | Real target/directory aliases and aliased scan root retain exact disjoint IDs/call endpoints, warm cache fragments, directed/undirected JSON reload and C++ definition provenance; leaf symlink remains a host capability exclusion |
| REQ-QML-020-AC02 | `tests/test_source_alias_provenance.py::test_req_qml020_ac02_foreign_alias_cannot_acquire_native_root_authority`; `tests/test_source_alias_provenance.py::test_req_qml020_ac02_failed_parent_anchor_keeps_only_accepted_physical_identity` | Foreign linked QObject remains excluded with exact QT_CPP_ROOT, unchanged source bytes and no native authority; failed lexical anchors retain only the accepted physical source |
| REQ-QML-020-AC03 | `tests/test_source_alias_provenance.py::test_req_qml020_ac03_watch_rename_deletion_and_repeat_preserve_discovered_source`; `tests/test_source_alias_provenance.py::test_req_qml020_ac03_policy19_products_refresh_retain_and_recover` | Actual two renames/deletion/no-change graph bytes, no-edit policy19-to20 refresh, staged publication failure/cohort retention, repair/full parity and repeat pass |

The full new selection passes **nine cases with one actual file-symlink skip**,
3.89 seconds. Existing cache/watch/ID/barrel/native/callback and alias/update
compatibility passes **405 cases with 31 capability skips**, 54.8 seconds.
The pure helper covers fifteen of fifteen measured statements and four of four
branches; isolated coverage storage preserves the original file. Facade/helper/
policy/test physical sizes are 8,998/31/114/277, within existing ceilings. Policy
20 refreshes older native/Qt products; AST schema 12 remains unchanged. Single-alias
shared-content notification is separately reproduced and assigned INC-QML-44.

### Nearby alias fixture — INC-QML-43

REQ-QML-020-AC01 additionally maps to
`tests/test_qt_nearby_alias_fixture.py::test_req_qml020_ac01_real_short_ancestors_preserve_nearby_facade_provenance`.
The original real five-ancestor fixture records one setup error with ten ancestor
hops; the corrected case passes with one real short-basename hop and unchanged
production source/edge equality. Existing/new alias modules pass **eight cases,
seven actual symlink capability skips**, one existing Hypothesis collection
warning. The source files measure 241 and 59 physical lines. No production
assertion, native SDK or graph/cache schema changes.

### Installed discovered-alias checkpoint — INC-QML-42/43

Wheel SHA-256:
`65a096a0042b181582f179fd63c1108479822bac866f7fab0d3eaf5fb7730309`.
All 181 source/installed Python payloads match; only facade, policy and new
source_identity differ from the preceding f2 wheel. The isolated unchanged
optional/core smoke and actual full-TEMP Windows short-alias smoke pass, with
129/123 loaded artifact modules. The five-module installed contract selection
passes **43 cases, eleven actual file-symlink capability skips, zero failures/
errors/warnings**, 13.58 seconds. All 153 loaded Graphify modules originate in
the artifact. The new source-identity module passes nine/one; the nearby-fixture
case passes. These overlapping counts are not added to full-suite totals.

Offline harness setup admits only ten exact seven-argument native cmd/mklink/J
fixture operations within its verified owned temporary tree. Sixty other process
attempts remain denied and no network call is admitted; owned junctions/temp data
are confirmed removed. This exception establishes real fixture setup, not corpus
execution authority. All 675 Python-file fingerprints, source197/optional40/core30
dependency versions, HEAD3c70bfc and original coverage bytes remain unchanged.
Separate source CI tool tests pass five cases without skips or warnings.

Full Pyright remains **604 errors, zero warnings, 671 files**, exit one, 20.651
seconds; every identity matches immutable135d50b under the same dependencies and
configuration, with zero added/removed. Targeted seven-file Pyright retains only
120 matched legacy-facade errors; the other six have zero diagnostics. Ruff passes.
This checkpoint excludes the subsequent INC-QML-44/45 correction and does not
establish corrected hosted or clean typing acceptance.

### Shared physical co-owner watch invalidation — INC-QML-44

Initial production probes reproduce stale facts after only one of two admitted
source owners is notified. Real junction and hardlink regressions retain full/
incremental equality assertions; the directory-rename case also exposes a shared
absolute-ID remap collision. The extractor owner corrects that collision alongside
INC-QML-45, without selecting source ownership through iteration order.

| Acceptance ID | Exact ordinary production test | Assigned boundary |
| --- | --- | --- |
| REQ-QML-011-AC01/AC03; REQ-QML-020-AC03 | `tests/test_watch_physical_coowners.py::test_req_qml011_ac01_ac03_qml020_ac03_one_owner_edit_refreshes_shared_content` | Actual generic/mixed directory-alias and hardlink edits; disjoint stable APIs, stale removal, unrelated facts, cold/warm/full/repeat |
| REQ-QML-011-AC03; REQ-QML-012-AC03 | `tests/test_watch_physical_coowners.py::test_req_qml011_ac03_normal_rename_and_deletion_retire_only_absent_owners` | Existing detection/deletion behavior, both owner kinds and full/incremental equality |
| REQ-QML-012-AC01/AC02 | `tests/test_watch_physical_coowners.py::test_req_qml012_ac01_ac02_identity_failure_retains_recovers_and_repeats` | Five actual admitted resolve/stat/disappearance failures, safe diagnostic, prior four-product cohort and existing cache bytes, repair/repeat |
| REQ-QML-012-AC04 | `tests/test_watch_physical_coowners.py::test_req_qml012_ac04_unsafe_or_long_missing_identity_context_is_empty`; `tests/test_watch_physical_coowners.py::test_req_qml012_ac04_context_quotes_delimiters_and_preserves_160_character_boundary` | Empty unsafe/unavailable context, JSON delimiter quoting and 160/161 limits |
| REQ-QML-011-AC01 | `tests/test_watch_physical_coowners.py::test_req_qml011_ac01_selection_cannot_discover_foreign_or_unadmitted_coowners`; `tests/test_watch_physical_coowners.py::test_req_qml011_ac01_missing_inode_identity_uses_contained_path_without_false_joins`; `tests/test_watch_coowner_admission.py::test_req_qml011_ac01_semantic_backed_hardlink_keeps_its_own_tier`; `tests/test_watch_coowner_admission.py::test_req_qml011_ac01_excluded_hardlink_cannot_reenter_the_corpus` | Foreign/unadmitted/nonregular rejection, conservative inode fallback, retained semantic tier and ignore exclusions |
| REQ-QML-011-AC03/AC04; REQ-QML-020-AC03 | `tests/test_watch_physical_coowners.py::test_req_qml011_ac03_ac04_qml020_ac03_policy20_refresh_retains_repairs_and_repeats` | Actual unchanged policy20-to21 watch refresh, staged-stamp failure, retained cohort and repaired full/repeat parity |

The new stateless helper measures 69 lines, facade watch 2,543 within its 2,550
ceiling, and focused tests 280/70. Isolated helper coverage measures 39 of 39
statements and ten of ten branches; original coverage is untouched. Combined
source/installed results appear below; corrected hosted acceptance is pending. Early
scan/stat bookkeeping remains outside the prior-product retention boundary;
cache-byte assertions establish the actual rejection point rather than a universal
promise about detection bookkeeping.

### Native entry spelling and shared ID ownership — INC-QML-45

Actual Windows short header/build-metadata spellings reproduce four membership/
source-identity failures with one passing foreign-root control. Admission now
precedes worker/cache work and verifies a native long spelling of the same file
without resolving discovered directory owners. The remap correction separates
primary walked claims from shared resolved forms; canonical supplied ownership,
unique-alias fallback and ambiguous physical forms retain distinct contracts.

| Acceptance ID | Exact ordinary production test | Assigned boundary |
| --- | --- | --- |
| REQ-QML-020-AC01 | `tests/test_qt_short_leaf_aliases.py::test_req_qml020_ac01_short_native_leaf_preserves_membership_facts_and_reload`; `tests/test_qt_short_leaf_aliases.py::test_req_qml020_ac01_native_utf16_lengths_preserve_astral_source_names` | Real header/build-metadata/both short inputs, exact raw facts, membership, original BOM/CRLF bytes/spans, UTF-16 supplementary names, cold/warm and directed reload |
| REQ-QML-020-AC02 | `tests/test_qt_short_leaf_aliases.py::test_req_qml020_ac02_short_spelling_preserves_two_discovered_junction_owners`; `tests/test_qt_short_leaf_aliases.py::test_req_qml020_ac02_short_foreign_native_leaf_keeps_existing_root_rejection`; `tests/test_source_identity_remap_owners.py::test_req_qml020_ac02_primary_physical_owner_survives_both_batch_orders`; `tests/test_source_identity_remap_owners.py::test_req_qml020_ac02_multiple_aliases_cannot_authorize_arbitrary_physical_target` | Separate junction IDs/calls, foreign native rejection, canonical-first/last absolute/relative inputs and conservative ambiguous import ownership |
| REQ-QML-012-AC01/AC02; REQ-QML-020-AC01/AC03 | `tests/test_source_input_admission.py::test_req_qml012_ac01_ac02_qml020_ac01_native_failure_retains_repairs_and_repeats`; `tests/test_source_input_admission.py::test_req_qml012_ac01_native_admission_refuses_before_any_worker_or_cache_write`; `tests/test_source_input_admission.py::test_req_qml012_ac01_native_filesystem_identity_failure_is_bounded` | Actual zero/oversize/empty/wrong-length/foreign-target/backend API failures, stat/same-file refusal, manual/watch prior products and cache bytes, repair/full parity/repeat, direct refusal before work |
| REQ-QML-020-AC01 | `tests/test_source_input_admission.py::test_req_qml020_ac01_missing_and_nonfile_keep_existing_admission_shape`; `tests/test_source_input_admission.py::test_req_qml020_ac01_nonwindows_input_needs_no_native_lookup` | Existing missing/directory/non-file handling and no POSIX native API requirement |
| REQ-QML-012-AC04 | `tests/test_source_input_admission.py::test_req_qml012_ac04_native_context_is_quoted_bounded_and_lexical`; `tests/test_source_input_admission.py::test_req_qml012_ac04_failed_context_lookup_keeps_bounded_admission_error` | Delimiters, empty/control/160–161 context, actual API failure plus failed lexical/CWD context adapter |

An early ambiguous-control expectation excluded all builder stubs. The owning
contract instead rejects newly admitted source/native authority and arbitrary
alias selection; ordinary unresolved import stubs keep the upstream builder's
existing behavior. Raw producer facts and built stub roles are verified separately.
No graph-builder behavior or accepted-source policy is changed for that control.
The combined local results are recorded below; corrected hosted proof is pending.

### Combined source and installed checkpoint — INC-QML-44/45

Native Windows/Python 3.12.14 source selection:
**640 passed, 21 capability/profile skips, zero failures**, 114.30 seconds.
All 59 new cases above execute without skips. The retained exclusions are eight
cache file-symlink cases, two active-CWD removals, one Windows Git profile,
one watch directory-symlink setup, one watch file-symlink, four extractor
file-symlinks, one discovered leaf-symlink and three prior diagnostic-context
symlinks. Actual Linux/platform proof is separately assigned to hosted execution.
Focused new selections overlap this profile and are not added to its total.

Fresh wheel SHA-256:
`c815eef893aa928eb58287be2b56e41c22b99ba43999e2c3ec30026af82108ac`.
All 182 source/wheel/installed Python payloads match, with only the approved five
payload changes from the 65a096a checkpoint. Unchanged QML/core/full-TEMP short
smokes pass; 129/123 loaded smoke modules come from the artifact. The ten-module
installed profile passes **102 cases, eleven actual file-symlink skips, zero
failures/errors/warnings**, 34.49 seconds; all 154 loaded Graphify modules
originate in the artifact. All 59 new cases pass. Only 33 exact owned native
junction-fixture callbacks are admitted; 157 other process attempts remain
denied, with no additional process/network authority. Temporary junctions/data
are confirmed removed. Source fingerprints for 681 Python files, 197/40/30 source/
optional/core dependencies, basis HEADfca23e2 and original coverage stay unchanged.
Separate actual Windows CI tool tests pass five cases, no skips/warnings.

Source identity coverage: 76/76 statements and 22/22 branches; its broader control
selection passes 54 cases with eight capability skips. Watch co-owner coverage:
39/39 statements and 10/10 branches; all 21 ordinary cases pass. Both use isolated
coverage storage. Whole-project Pyright 1.1.409 retains **604 errors, zero
warnings, 677 files**, exactly matching immutable135d50b diagnostic identities
under the same configuration/dependencies: zero added/removed. Targeted ten-file
typing retains only 142 matched legacy facade/watch errors; other eight have zero.
Ruff 0.15.14 and 134 generated artifacts pass. Actionlint 1.7.12 reports no
workflow diagnostics; both complete native run blocks parse with zero errors in
Windows PowerShell 5.1 and pwsh 7.6.6. Workflow size remains 450 lines.
AST-only `graphify update . --no-cluster` completes with no LLM invocation;
graph counts are navigation output rather than correctness evidence. Current
hosted, typing and physical device/system gaps remain explicit.

## Individual acceptance assignments

The [follow-up audit](../docs/qt-qml/FOLLOWUP_AUDIT.md) supplies counterexamples for
REQ-QML-008-AC01/AC03, REQ-QML-016-AC01–AC04 and REQ-QML-017-AC02/AC03/AC04. The table's historical
passes do not cover those cases. Current INC-QML-17–20 correction evidence appears
below; affected criteria retain explicit expanded-profile gaps.
Exact opt-in probes and corrective increments appear in
[scope corrections](#follow-up-audit-scope-corrections).

Exact test references below identify executed cases. Documentation, privacy and
hosted integration reviews are explicit review evidence rather than invented unit
tests. Later revisions reverify affected evidence; preserve these identifiers.

The INC-QML-06/07 rows retain their original bounded-profile evidence. Expanded
shared-owner incremental contracts in REQ-QML-011-AC01/AC03/AC04 are assigned to
INC-QML-44; new input-identity failure and short-leaf contracts are assigned to
INC-QML-45. Historical passes do not verify those additions. Their current
source, installed and hosted results are recorded separately below when run.

| Acceptance ID | Actual evidence / assigned open case | Planned completion increment | Status |
| --- | --- | --- | --- |
| REQ-QML-001-AC01 | `tests/test_qml_wheel_artifact.py::test_qml001_ac01_built_wheel_contains_adapter_and_optional_extra_metadata`; `tests/test_qml_wheel_artifact.py::test_qml001_ac01_ac03_built_artifact_production_import_and_parser_boundary` | INC-QML-01 | Verified (declared profile) |
| REQ-QML-001-AC02 | `tests/test_qml_syntax_profile.py::test_qml001_ac02_handchecked_profile_uses_production_extractor_and_original_spans`; `tests/test_qml_syntax_profile.py::test_qml001_ac02_profile_runs_offline_in_fresh_production_process_without_corpus_execution` | INC-QML-03 | Verified (declared profile) |
| REQ-QML-001-AC03 | `tests/test_qml_failures.py::test_qml001_ac03_missing_optional_import_is_safe_and_does_not_break_python`; `tests/test_qml_failures.py::test_qml001_ac03_incompatible_parser_load_is_bounded_failure` | INC-QML-01 | Verified (declared profile) |
| REQ-QML-001-AC04 | `tests/test_qml_declarations.py::test_qml001_ac04_empty_source_is_distinguishable_from_parse_failure`; `tests/test_qml_declarations.py::test_qml012_ac01_malformed_or_partial_parse_has_no_authoritative_nodes`; `tests/test_qml_failures.py::test_qml001_ac04_unsupported_annotated_root_is_not_file_only_success` | INC-QML-01 | Verified (declared profile) |
| REQ-QML-002-AC01 | `tests/test_qt_config_incremental.py::test_qml011_ac03_import_root_order_refreshes_unchanged_source_provider; tests/test_qml_identity.py::test_qml01_ui_suffix_names_component_without_losing_filename_identity` | INC-QML-06 | Verified static source profile |
| REQ-QML-002-AC02 | `tests/test_qt_metadata_admission.py::test_cmake_exact_name_does_not_reclassify_arbitrary_text; tests/test_qml_integration.py::test_qml002_ac02_named_qmldir_dispatch_directory_and_single_file_root` | INC-QML-06 | Verified static source profile |
| REQ-QML-002-AC03 | `tests/test_qt_metadata_admission.py::test_qt_metadata_discovery_obeys_existing_ignore_policy; tests/test_qt_resource_resolution.py::test_qrc_host_reads_entities_traversal_and_malformed_xml_rejected` | INC-QML-06 | Verified static source profile |
| REQ-QML-002-AC04 | `tests/test_qml_identity.py::test_qml003_ac04_relocated_root_and_cwd_preserve_all_facts; tests/test_qt_config_incremental.py::test_qml011_ac03_import_root_order_refreshes_unchanged_source_provider` | INC-QML-06 | Verified static source profile |
| REQ-QML-003-AC01 | `tests/test_qml_declarations.py::test_qml003_ac01_exact_declarations_ownership_and_raw_types`; `tests/test_qml_declarations.py::test_qml003_ac01_unicode_crlf_spans_and_original_names`; `tests/test_qml_syntax_profile.py::test_qml003_ac01_property_binding_and_array_objects_keep_exact_owners` | INC-QML-01 | Verified (declared profile) |
| REQ-QML-003-AC02 | `tests/test_qml_identity.py::test_qml003_ac02_duplicate_basename_uses_full_relative_path`; `tests/test_qml_identity.py::test_qml003_ac02_inline_component_equal_ids_and_members_have_separate_owners`; `tests/test_qml_graph.py::test_qml003_ac02_same_stem_cpp_js_and_qml_do_not_merge`; template barrier cases in test_qml_syntax_profile.py | INC-QML-01 | Verified (declared profile) |
| REQ-QML-003-AC03 | `tests/test_qml_declarations.py::test_qml003_ac03_comments_literals_groups_and_js_inner_functions_are_not_objects` | INC-QML-01 | Verified (declared profile) |
| REQ-QML-003-AC04 | `tests/test_qml_identity.py::test_qml003_ac04_relocated_root_and_cwd_preserve_all_facts`; `tests/test_qml_identity.py::test_qml003_ac04_comment_insert_changes_spans_but_not_named_identity`; `tests/test_qml_integration.py::test_qml010_ac01_real_process_pool_and_warm_order_match_sequential` | INC-QML-01 | Verified (declared profile) |
| REQ-QML-004-AC01 | `tests/test_qml_resolution.py::test_aliased_directory_and_uri_imports_do_not_cross_bind`; `tests/test_qml_resolution.py::test_version_availability_and_latest_compatible_export` | INC-QML-02 | Verified (declared profile) |
| REQ-QML-004-AC02 | `tests/test_qml_resolution.py::test_aliased_directory_and_uri_imports_do_not_cross_bind`; `tests/test_qml_resolution.py::test_versioned_layout_and_missing_version_evidence` | INC-QML-02 | Verified (declared profile) |
| REQ-QML-004-AC03 | `tests/test_qml_resolution.py::test_competing_providers_and_missing_modules_have_no_target_edges` | INC-QML-02 | Verified (declared profile) |
| REQ-QML-004-AC04 | `tests/test_qml_resolution.py::test_declared_roots_and_remote_import_never_expand_corpus`; `tests/test_qml_resolution.py::test_directory_and_script_projection_and_ignored_disk_provider` | INC-QML-02 | Verified (declared profile) |
| REQ-QML-005-AC01 | `tests/test_qml_scope.py::test_component_ids_do_not_leak_between_files_or_inline_components` | INC-QML-02 | Verified (declared profile) |
| REQ-QML-005-AC02 | `tests/test_qml_scope.py::test_inline_shadow_and_inherited_members_are_distinct_roles`; `tests/test_qml_scope.py::test_singleton_pragma_and_qualified_access` | INC-QML-02 | Verified (declared profile) |
| REQ-QML-005-AC03 | `tests/test_qml_scope.py::test_internal_external_dynamic_and_lexical_members_stay_unresolved` | INC-QML-02 | Verified (declared profile) |
| REQ-QML-005-AC04 | `tests/test_qml_resolution.py::test_module_script_exports_have_separate_lookup_roles` | INC-QML-02 | Verified (declared profile) |
| REQ-QML-006-AC01 | `tests/test_qml_expressions.py::test_binding_reads_and_nested_qualified_aliases` | INC-QML-03 | Verified (declared profile) |
| REQ-QML-006-AC02 | `tests/test_qml_expressions.py::test_alias_cycles_missing_and_ambiguous_targets_never_guess`; `tests/test_qml_expressions.py::test_component_and_object_scope_do_not_bind_hidden_identifiers` | INC-QML-03 | Verified (declared profile) |
| REQ-QML-006-AC03 | `tests/test_qml_expressions.py::test_dynamic_reads_and_executable_source_are_only_analyzed` | INC-QML-03 | Verified (declared profile) |
| REQ-QML-006-AC04 | `tests/test_qml_expressions.py::test_repeated_sites_survive_actual_directed_build_and_json`; `tests/test_qml_integration.py::test_qml010_ac02_default_undirected_export_reload_keeps_qml_direction` | INC-QML-03 | Verified (declared profile) |
| REQ-QML-007-AC01 | `tests/test_qml_handlers.py::test_parameters_block_bindings_nested_functions_and_computed_calls`; `tests/test_qml_handlers.py::test_inherited_and_alias_target_signal_parameters_shadow_properties` | INC-QML-03 | Verified (declared profile) |
| REQ-QML-007-AC02 | `tests/test_qml_scripts.py::test_literal_imported_helpers_and_library_do_not_inherit_document_ids`; `tests/test_qml_scripts.py::test_mjs_explicit_exports_aliases_and_private_functions`; `tests/test_qml_scripts.py::test_accepted_script_dependencies_support_classic_and_esm_imports`; `tests/test_qml_scripts.py::test_script_overlay_retains_original_shared_js_nodes_and_never_executes` | INC-QML-03 | Verified (declared profile) |
| REQ-QML-007-AC03 | `tests/test_qml_handlers.py::test_declared_and_property_change_handlers_are_subscriptions`; `tests/test_qml_handlers.py::test_connections_target_and_dynamic_target_stay_distinct`; `tests/test_qml_adversarial.py::test_mixed_legacy_connections_handlers_do_not_activate_ignored_function_handlers` | INC-QML-03 | Verified (declared profile) |
| REQ-QML-007-AC04 | `tests/test_qml_scripts.py::test_generic_js_calls_cannot_bind_to_qml_owned_expression_sites`; `tests/test_qml_scripts.py::test_script_overlay_does_not_read_unaccepted_imports_or_network` | INC-QML-03 | Verified (declared profile) |
| REQ-QML-008-AC01 | `tests/test_qt_project_admission.py::test_qml008_ac01_public_element_build_membership_and_canonical_member_endpoints` | INC-QML-05 | Locally verified bounded alias registration correction; adoption gaps retained |
| REQ-QML-008-AC02 | `tests/test_qt_cpp_exposure.py::test_header_implementation_members_reuse_accepted_canonical_ids`; `tests/test_qt_project_admission.py::test_qml008_ac01_public_element_build_membership_and_canonical_member_endpoints`; `tests/test_qt_cpp_definition_ownership.py::test_req_qml008_ac02_definition_provenance_keeps_emission_owned_through_aggregate`; normalization, conflicting callable/body, missing completeness, external/local class, generic identity and original-byte controls in that module; `tests/test_qt_cpp_owner_upgrade.py::test_qml008_ac02_policy_three_reparses_unchanged_native_ownership` (update/extract); [current constructor/source-containment assignments](#constructor-and-source-containment-corrections) | INC-QML-05; INC-QML-10/12/13 corrections | Locally verified bounded ownership; qualified ID correction has separate INC-QML-21 evidence below |
| REQ-QML-008-AC03 | `tests/test_qt_native_project_integration.py::test_cpp_source_in_two_distinct_build_contexts_has_no_arbitrary_native_provider; tests/test_qt_qml_integration.py::test_ambiguous_overload_and_version_revised_member_are_explicit` | INC-QML-05 | Locally verified bounded alias rejection; broader adoption/overload gaps retained |
| REQ-QML-008-AC04 | `tests/test_qt_cpp_syntax.py::test_unicode_crlf_macro_spans_are_original_bytes; tests/test_qt_cpp_syntax.py::test_comments_strings_raw_literals_and_preprocessor_definitions_are_inert` | INC-QML-05 | Verified static source profile |
| REQ-QML-009-AC01 | `tests/test_qt_project_admission.py::test_qml008_ac01_public_element_build_membership_and_canonical_member_endpoints; tests/test_qt_resource_resolution.py::test_public_qt6_cmake_and_qmake_fixtures_describe_identical_membership` | INC-QML-05 | Verified static source profile |
| REQ-QML-009-AC02 | `tests/test_qml_types_metadata.py::test_qmltypes_members_flags_exports_original_byte_provenance; tests/test_qml_types_metadata.py::test_qmltypes_cpp_member_conflict_preserves_authoritative_source` | INC-QML-05 | Verified static source profile |
| REQ-QML-009-AC03 | `tests/test_qt_project_admission.py::test_qml009_ac03_public_metadata_qrc_load_build_export_reload; tests/test_qt_resource_resolution.py::test_qrc_host_reads_entities_traversal_and_malformed_xml_rejected` | INC-QML-05 | Verified static source profile |
| REQ-QML-009-AC04 | `tests/test_qt_project_metadata.py::test_cmake_conditional_and_expanded_metadata_is_not_authoritative; tests/test_qt_project_metadata.py::test_qmake_conditions_expansion_functions_never_produce_guessed_context` | INC-QML-05 | Verified static source profile |
| REQ-QML-010-AC01 | `tests/test_qt_worker_cache_integrity.py::test_qml010_ac01_actual_workers_preserve_configured_roots_script_and_native_facts`; `tests/test_qml_identity.py::test_qml010_ac01_filename_normalization_collisions_keep_distinct_ids`; `tests/test_qml_identity.py::test_qml003_ac02_unicode_normalization_colliding_members_remain_distinct`; `tests/test_qml_integration.py::test_qml010_ac01_real_process_pool_and_warm_order_match_sequential` | INC-QML-07 | Verified (bounded static profile) |
| REQ-QML-010-AC02 | `tests/test_qt_qml_export_consumers.py::test_json_repeated_native_mechanisms_remain_distinct_and_directional`; `tests/test_qt_qml_export_consumers.py::test_native_path_reports_qml_call_site_and_cpp_declaration_without_reversing_flow`; `tests/test_qt_graph_persistence.py` | INC-QML-07 | Verified (bounded static profile) |
| REQ-QML-010-AC03 | `tests/test_qt_qml_export_consumers.py::test_json_repeated_native_mechanisms_remain_distinct_and_directional`; `tests/test_qml_expressions.py::test_repeated_sites_survive_actual_directed_build_and_json`; `tests/test_qt_export_matrix.py::test_cypher_keeps_parallel_mechanisms_and_escapes_literal_data` | INC-QML-07 | Verified (bounded static profile) |
| REQ-QML-010-AC04 | `tests/test_qt_affected_definitions.py::test_qml016_ac04_signal_change_reports_canonical_out_of_line_function_owner`; `tests/test_qt_signals_slots.py::test_native_events_have_distinct_sites_and_no_delivery_calls`; `tests/test_qt_graph_persistence.py`; `tests/test_build.py::test_build_merge_sln_stub_does_not_replace_referenced_csproj`; `tests/test_build.py::test_build_merge_project_reference_stub_does_not_replace_referenced_project`; `tests/test_build.py::test_merge_raw_extraction_cross_file_stub_parity` | INC-QML-07 | Verified (bounded static profile) |
| REQ-QML-011-AC01 | `tests/test_qt_final_incremental_parity.py::test_qml011_ac01_real_normal_qml_edit_matches_cold_warm_manual_and_watch`; `tests/test_qt_metadata_incremental.py::test_native_cpp_provider_only_edit_refreshes_unchanged_qml_and_warm_overlay` | INC-QML-06 | Verified (bounded static profile) |
| REQ-QML-011-AC02 | `tests/test_qt_metadata_incremental.py::test_build_provider_only_mutations_equal_clean_accepted_corpus; tests/test_qt_metadata_incremental.py::test_resource_only_mutations_refresh_unchanged_cpp_loaders; tests/test_qt_config_incremental.py::test_qml011_ac02_last_qt_source_deletion_cleans_facts_and_commits_nonqt_state` | INC-QML-06 | Verified static source profile |
| REQ-QML-011-AC03 | `tests/test_qt_config_incremental.py::test_qml011_ac03_import_root_order_refreshes_unchanged_source_provider; tests/test_qt_config_incremental.py::test_qml011_ac03_package_version_change_reanalyzes_unchanged_corpus` | INC-QML-06 | Verified static source profile |
| REQ-QML-011-AC04 | `tests/test_qt_final_incremental_parity.py::test_qml011_ac04_real_no_change_updates_preserve_every_fact_and_unrelated_python`; `tests/test_qt_metadata_incremental.py::test_build_provider_only_mutations_equal_clean_accepted_corpus`; `tests/test_qt_metadata_incremental.py::test_resource_only_mutations_refresh_unchanged_cpp_loaders` | INC-QML-06 | Verified (bounded static profile) |
| REQ-QML-012-AC01 | `tests/test_qml_failures.py::test_qml001_ac03_missing_optional_import_is_safe_and_does_not_break_python`; `tests/test_qml_failures.py::test_qml012_ac01_native_parse_exception_is_explicit_safe_failure`; `tests/test_qml_resolver_safety.py::test_native_join_failure_is_guarded_and_successful_retry_is_clean` | INC-QML-06 | Verified (bounded static profile) |
| REQ-QML-012-AC02 | `tests/test_qt_worker_cache_integrity.py::test_qml012_ac02_failed_native_parser_keeps_prior_real_ast_cache_and_products`; `tests/test_qt_config_incremental.py::test_qml012_ac02_malformed_new_source_preserves_graph_manifest_and_stamp`; `tests/test_qt_metadata_incremental.py::test_failed_metadata_update_preserves_prior_graph_manifest_and_report` | INC-QML-06 | Verified (bounded static profile) |
| REQ-QML-012-AC03 | `tests/test_qt_config_incremental.py::test_qml011_ac02_last_qt_source_deletion_cleans_facts_and_commits_nonqt_state`; `tests/test_qml_watch_persistence.py::test_watch_qml_failure_preserves_completed_products_with_force`; `tests/test_qml_cli_persistence.py` | INC-QML-06 | Verified (bounded static profile) |
| REQ-QML-012-AC04 | `tests/test_qml_failures.py::test_qml012_ac04_deep_source_terminates_at_supported_bound`; `tests/test_qml_failures.py::test_qml012_ac04_explicit_root_rejection_does_not_expose_absolute_paths`; `tests/test_qt_resource_resolution.py::test_qrc_host_reads_entities_traversal_and_malformed_xml_rejected`; `tests/test_qt_qml_search.py::test_deep_malformed_literal_transport_cannot_crash_production_search` | INC-QML-06 | Verified (bounded static profile) |
| REQ-QML-013-AC01 | `tests/test_qt_query_consumers.py::test_cli_query_explain_and_path_use_source_scoped_nodes`; `tests/test_qt_qml_export_consumers.py::test_native_path_reports_qml_call_site_and_cpp_declaration_without_reversing_flow`; `tests/test_qt_mcp_consumers.py::test_mcp_exact_id_path_matches_cli_and_retains_source_evidence` | INC-QML-07 | Verified (bounded static profile) |
| REQ-QML-013-AC02 | `tests/test_qt_affected_consumers.py::test_property_change_reports_binding_and_owning_component`; `tests/test_qt_affected_definitions.py::test_qml016_ac04_signal_change_reports_canonical_out_of_line_function_owner`; `tests/test_qt_affected_consumers.py::test_future_metadata_or_foreign_file_ownership_is_not_dependency_evidence` | INC-QML-07 | Verified (bounded static profile) |
| REQ-QML-013-AC03 | `tests/test_qt_qml_export_consumers.py`; `tests/test_qt_export_matrix.py`; `tests/test_qt_graph_html_payload.py`; `tests/test_qt_html_consumers.py`; `tests/test_qt_source_coverage_report.py`; format-specific omissions and unexecuted live database behavior: [EXPORT_MATRIX](../docs/qt-qml/EXPORT_MATRIX.md) | INC-QML-07 | Verified (bounded static profile) |
| REQ-QML-013-AC04 | `tests/test_qt_mcp_consumers.py`; `tests/test_qt_mcp_stdio.py`; `tests/test_qt_qml_search.py` | INC-QML-07 | Verified (bounded static profile) |
| REQ-QML-014-AC01 | `tests/test_qml_wheel_artifact.py`; `tests/test_qml_platform_matrix.py`; `tests/qml_installed_smoke.py`; twelve exact-head optional/core wheel jobs: [PLATFORM_MATRIX](../docs/qt-qml/PLATFORM_MATRIX.md) | INC-QML-07 | Verified (declared hosted/static profile) |
| REQ-QML-014-AC02 | `tests/test_qml_identity.py::test_qml003_ac04_relocated_root_and_cwd_preserve_all_facts`; `tests/test_qt_cpp_syntax.py::test_unicode_crlf_macro_spans_are_original_bytes`; `tests/test_qml_wheel_artifact.py::test_qml001_ac01_ac03_built_artifact_production_import_and_parser_boundary` | INC-QML-07 | Verified (declared hosted/static profile) |
| REQ-QML-014-AC03 | `tests/test_extract.py`; `tests/test_cache.py`; `tests/test_serve.py`; `tests/test_export.py`; `tests/test_affected_cli.py`; `tests/test_callflow_html.py`; affected baseline full suites in four hosted Ubuntu Python lanes; local optional skips and Windows baseline defects remain in VALIDATION.md | INC-QML-07 | Verified (declared hosted/static profile) |
| REQ-QML-014-AC04 | Executed skip/baseline/typing accounting in [VALIDATION](../docs/qt-qml/VALIDATION.md); optional MCP executed through actual HTTP/stdio; absent SVG is an explicit omission | INC-QML-07 | Verified (declared hosted/static profile) |
| REQ-QML-015-AC01 | Requirement/68-criterion/link/status review and reviewable stacked PRs; [IMPLEMENTATION](../docs/qt-qml/IMPLEMENTATION.md), [PLAN](../docs/qt-qml/PLAN.md) | INC-QML-07 | Verified (declared hosted/static profile) |
| REQ-QML-015-AC02 | `tests/test_qml_skillgen_guidance.py`; `tests/test_skillgen.py`; five generator validators run separately; all 134 generated artifacts and expected outputs regenerated | INC-QML-07 | Verified (declared hosted/static profile) |
| REQ-QML-015-AC03 | Verified upstream v8/base/head and earlier upstream proposal read-only; preserved grammar attribution; exact PR head/base/tested merge and workflows recorded in [VALIDATION](../docs/qt-qml/VALIDATION.md) | INC-QML-07 | Verified (declared hosted/static profile) |
| REQ-QML-015-AC04 | Executed public privacy/reference/footprint review; all 68 criteria accounted for with explicit static/runtime/platform/export boundaries; [README](../docs/qt-qml/README.md), [EXPORT_MATRIX](../docs/qt-qml/EXPORT_MATRIX.md), [PLATFORM_MATRIX](../docs/qt-qml/PLATFORM_MATRIX.md) | INC-QML-07 | Verified (declared hosted/static profile) |
| REQ-QML-016-AC01 | `tests/test_qt_cpp_syntax.py::test_access_sections_keep_original_roles_offsets`; `tests/test_qt_signals_slots.py::test_native_events_have_distinct_sites_and_no_delivery_calls`; `tests/test_qt_signals_slots.py::test_macro_sections_private_meta_slots_and_comments`; `tests/test_qt_cpp_definition_ownership.py::test_req_qml016_ac01_forward_declaration_does_not_compete_with_complete_definition` | INC-QML-04b; INC-QML-10 correction | Partial; alias correction locally verified; inherited/qualified identity gaps INC-QML-11/21 |
| REQ-QML-016-AC02 | `tests/test_qt_signals_slots.py::test_overloads_need_selector_and_dynamic_sender_stays_unresolved`; `tests/test_qt_events_boundaries.py::test_functor_function_and_connection_handle_disconnect`; `tests/test_qt_events_boundaries.py::test_explicit_cast_signal_to_signal_and_condition_flags`; `tests/test_qt_events_boundaries.py::test_private_typed_pointer_and_incompatible_receiver_are_rejected`; [alias counterexamples](#follow-up-audit-scope-corrections) | INC-QML-04b; INC-QML-19 correction | Locally verified bounded aliases; generic overload gap INC-QML-15 retained |
| REQ-QML-016-AC03 | `tests/test_qt_events_boundaries.py::test_explicit_cast_signal_to_signal_and_condition_flags`; `tests/test_qt_events_boundaries.py::test_computed_signal_receiver_and_custom_connect_are_not_qt_targets`; `tests/test_qt_signals_slots.py::test_native_events_have_distinct_sites_and_no_delivery_calls`; [alias counterexamples](#follow-up-audit-scope-corrections) | INC-QML-04b; INC-QML-19 correction | Locally verified bounded alias/conditional rejection; unsupported forms retained |
| REQ-QML-016-AC04 | `tests/test_qt_event_incremental_consumers.py::test_qml016_ac04_event_mutation_and_removal_match_clean_rebuild_without_delivery_calls`; `tests/test_qt_html_consumers.py::test_signal_emission_is_not_rendered_as_a_caller_in_the_call_table`; `tests/test_qt_affected_definitions.py`; `tests/test_qt_mcp_consumers.py::test_qml016_ac04_http_metadata_search_keeps_connection_reference_semantics`; `tests/test_qt_worker_cache_integrity.py`; `tests/test_qt_cpp_owner_upgrade.py::test_qml016_ac04_failed_owner_upgrade_retains_prior_graph_stamp_and_manifest` (force off/on); persisted JSON and aggregate ownership in `tests/test_qt_cpp_definition_ownership.py` | INC-QML-07; INC-QML-10 correction | Partial; alias lifecycle/artifact evidence passes; inherited/qualified identity gaps retained |
| REQ-QML-017-AC01 | `tests/test_qt_project_admission.py::test_qml017_ac01_literal_module_load_reaches_declared_component_and_property; tests/test_qt_project_admission.py::test_qml009_ac03_public_metadata_qrc_load_build_export_reload` | INC-QML-05 | Locally verified bounded literal loader correction; omitted API families excluded |
| REQ-QML-017-AC02 | `tests/test_qml_cpp_access.py::test_view_root_and_literal_object_name_property_access`; `tests/test_qt_access_providers.py::test_qqmlproperty_read_write_preserves_property_handle`; `tests/test_qt_project_admission.py::test_qml017_ac01_literal_module_load_reaches_declared_component_and_property`; `tests/test_qt_cpp_definition_ownership.py::test_req_qml017_ac02_namespace_definition_owns_source_backed_qml_access`; [receiver counterexamples](#follow-up-audit-scope-corrections) | INC-QML-05; INC-QML-10/17 corrections | Partial; receiver correction passes; static reflection correction has separate INC-QML-22 evidence below |
| REQ-QML-017-AC03 | `tests/test_qt_access_providers.py`; `tests/test_qt_project_admission.py::test_qml008_ac01_public_element_build_membership_and_canonical_member_endpoints`; `tests/test_qt_native_project_integration.py`; [engine counterexample](#follow-up-audit-scope-corrections) | INC-QML-05; INC-QML-18 correction | Locally verified exact declaration/provider and component-engine profile; factory/member gap retained |
| REQ-QML-017-AC04 | `tests/test_qt_final_incremental_parity.py::test_qml017_ac04_qml_member_edit_refreshes_unchanged_reverse_cpp_access`; `tests/test_qml_cpp_access.py::test_duplicate_object_names_do_not_select_first_child`; `tests/test_qt_access_providers.py::test_duplicate_context_provider_and_local_shadow_do_not_choose`; `tests/test_qt_metadata_incremental.py`; `tests/test_qt_qml_export_consumers.py`; `tests/test_qt_mcp_stdio.py`; persisted export ownership in `tests/test_qt_cpp_definition_ownership.py::test_req_qml017_ac02_namespace_definition_owns_source_backed_qml_access`; [audit counterexamples](#follow-up-audit-scope-corrections) | INC-QML-07; INC-QML-10/17/18 corrections | Partial; bounded receiver/provider/loader lifecycle passes; INC-QML-21/22 have separate evidence below; wider system gaps remain |

## Native ownership correction and remaining gaps

The baseline follow-up audit A13 failed REQ-QML-008-AC01/AC03 and REQ-QML-016-AC01/AC04
for lexical aliases despite the earlier bounded passes in the individual table.
These statuses are partial/failed for the new cases. INC-QML-19 owns their
registration/emission/connection correction; INC-QML-11 remains inherited lookup.

INC-QML-10's bounded source-ownership correction is locally verified through the
production facade, graph assembly, JSON publication/reload, aggregate HTML and
real CLI upgrade/retention paths. The final focused ownership/context/upgrade
selection passes 88 cases in 7.38 seconds. The reviewed final-wheel Qt/QML, C++,
HTML and export selection passes 954 cases with seven documented skips. Exact
commands, artifact identity and red/green evidence belong to
[validation](../docs/qt-qml/VALIDATION.md#inc-qml-10-native-source-ownership).
These results do not establish browser appearance or new hosted/platform evidence.

Accepted unchanged-header contexts have separate production regressions in
`tests/test_qt_cpp_context_ownership.py::test_req_qml008_ac02_borrowed_complete_header_is_not_counted_as_two_definitions`
and `tests/test_qt_cpp_context_ownership.py::test_req_qml016_ac01_context_pipeline_preserves_owned_emission_through_json_reload`.
They map REQ-QML-008-AC02 and REQ-QML-016-AC01/AC04 to actual collector and
pipeline/join/build/publication/reload ownership, canonical IDs and unchanged
borrowed dictionaries. Genuine distinct-body and false/missing completeness
controls in the same module retain unproved endpoints; equivalent relative,
Windows-separator and absolute path spellings retain one body identity. These
cases first failed before the borrowed source/span transport correction and pass
within the final focused selection.

INC-QML-11 now corrects grandparent inherited-signal endpoint lookup under
REQ-QML-016-AC01/AC04 with the exact source/update evidence below. Earlier
immediate-base-only evidence is superseded for this bounded lookup profile. INC-QML-12/13 now have bounded source
implementation and regression evidence below. Missing/unaccepted class bodies,
collapsed overloads and dynamic targets retain explicit unavailable ownership.
A proven enclosing callable or accepted source file may contain the occurrence
without establishing its native class, QObject role or semantic target. These
corrections do not use containment as proof of a missing class or runtime call.

## Constructor and source-containment corrections

INC-QML-12 owns generic constructor declaration/definition proof and canonical
parent correction. INC-QML-13 owns native source-site/file containment, upgrade
invalidation and truthful community counts. Final reviewed policy-5/schema-7
wheel identity, complete suite and installed public source-file proof are in
[validation](../docs/qt-qml/VALIDATION.md#inc-qml-1213-current-source-and-view-evidence).
The earlier 1029-pass artifact used policy 4 and does not verify the final
source-file change. Each row retains its original criterion identity.

| Affected criterion | Exact production regression evidence | Boundary and current state |
| --- | --- | --- |
| REQ-QML-008-AC02 | `tests/test_cpp_constructor_ownership.py::test_req_qml008_ac02_constructor_prototypes_are_callable_methods`; `tests/test_cpp_constructor_ownership.py::test_req_qml008_ac02_constructor_definition_retains_id_and_exact_accepted_owner`; `tests/test_cpp_constructor_ownership.py::test_req_qml008_ac02_constructor_join_rejects_foreign_or_corrupt_accepted_proof`; `tests/test_cpp_constructor_ownership.py::test_req_qml008_ac02_corrupted_owner_cannot_relabel_another_actual_constructor`; `tests/test_qt_member_source_links.py::test_req_qml008_ac02_plain_member_uses_exact_callable_without_native_class_claim`; `tests/test_qt_member_source_links.py::test_req_qml008_ac02_local_class_links_to_enclosing_callable_without_type_authority`; `tests/test_qt_member_source_links.py::test_req_qml008_ac02_source_fallback_rejects_unproved_or_noncallable_context`; `tests/test_qt_source_file_containment.py::test_req_qml008_ac02_unknown_native_owner_keeps_actual_file_context_after_reload`; `tests/test_qt_source_file_containment.py::test_req_qml008_ac02_file_context_requires_unique_actual_file_role` | Locally verified bounded ownership; qualified ID correction has separate INC-QML-21 evidence below |
| REQ-QML-010-AC02/AC04 | `tests/test_cpp_constructor_ownership.py::test_req_qml008_ac02_generic_constructor_facts_keep_original_bom_crlf_unicode_spans`; `tests/test_qt_constructor_ownership.py::test_req_qml008_ac02_constructor_spans_use_original_bom_crlf_unicode_bytes`; `tests/test_qt_member_source_links.py::test_req_qml008_ac02_source_link_survives_build_json_and_aggregate`; `tests/test_qt_member_source_links.py::test_req_qml008_ac02_direct_collector_borrows_exact_callable_without_mutating_context`; file containment/reload and role-rejection cases above | Original bytes, canonical IDs, EXTRACTED containment direction, immutable borrowed dictionaries and unresolved native status remain separate from inferred target resolution. Current artifact/reload proof passes. |
| REQ-QML-011-AC03 | `tests/test_qt_source_links_upgrade.py::test_req_qml011_ac03_source_links_upgrade_reparses_unchanged_cpp` (extract/update; prior policy/schema 3/6 and 4/7) | Real CLI reparses unchanged accepted C++ at the same package version, retires incompatible AST entries, preserves unrelated Python and matches a clean rebuild; repeated operation is idempotent. Current policy 5/schema 7 source/upgrade and installed public-fixture evidence pass. |
| REQ-QML-011-AC04 | `tests/test_qt_source_links_upgrade.py::test_req_qml011_ac04_removed_admission_removes_source_overlay`; `tests/test_qt_source_file_containment.py::test_req_qml011_ac04_unowned_file_sites_refresh_and_remove_stale_links`; `tests/test_qt_constructor_ownership.py::test_req_qml016_ac04_and_qml017_ac04_constructor_updates_remove_stale_sites_and_preserve_failures` | Actual cold/warm, manual update and watch, edit/removal, no-change repeat and unrelated facts. Supported constructor/member cases require full normalized parity; exact generic overload identity remains unproved and is not passed by native source-file comparison. |
| REQ-QML-012-AC02 | `tests/test_qt_source_links_upgrade.py::test_req_qml012_ac02_failed_source_links_upgrade_retains_products` (force off/on); constructor mutation/retention case above (manual/watch) | Real malformed-source rejection retains graph, manifest, analysis stamp and applicable root marker; corrected retry and repeat succeed. These cases supplement earlier actual cache/publication-failure regressions, rather than proving every persistence failure by one fixture. Source and current installed public-fixture retention pass. |
| REQ-QML-016-AC01/AC04 | `tests/test_qt_constructor_ownership.py::test_req_qml016_ac01_and_qml017_ac02_constructor_owns_emission_and_write_after_json_reload` (namespace/plain; directed/undirected); `tests/test_qt_constructor_ownership.py::test_req_qml016_ac04_constructor_conflicts_cannot_invent_a_canonical_owner`; constructor mutation/retention case above | Canonical constructor/source ownership through assembly, JSON reload, query and affected; no fabricated delivery call. Duplicate bodies, foreign namespaces and collapsed overloaded delegation retain unavailable native target proof. Inherited endpoint gap INC-QML-11 remains unverified. |
| REQ-QML-017-AC02/AC04 | The same exact constructor emission/write, conflict and mutation/retention tests | Literal accepted resource handles independently authorize QML access in a proven source callable; native class authority is not guessed from that access. Current reviewed source/wheel/public-fixture proof passes; unsupported dynamic handles/provider adoption remain separate gaps. |
| REQ-QML-019-AC02 | `tests/test_html_community_links.py::test_req_qml019_ac02_internal_only_group_has_source_edges_despite_zero_neighbors`; `tests/test_html_community_links.py::test_req_qml019_ac02_external_source_edges_are_distinct_from_neighbor_count`; `tests/test_html_community_links.py::test_req_qml019_ac02_isolated_source_member_does_not_claim_internal_connectivity`; `tests/test_html_community_links.py::test_req_qml019_ac02_source_edge_counts_keep_direction_parallel_edges_and_self_loops`; `tests/test_html_community_links.py::test_req_qml019_ac02_invalid_preaggregated_source_counts_remain_unavailable`; supplied-meta/small-view controls in that module | Eleven emitted-script/exporter cases pass. Counts use canonical graph edges, preserve source inputs and do not add fake plotted loops; unavailable counts, escaping and ordinary small-view Degree remain explicit. No new browser visual run is claimed. |

The source-site suite first failed seven cases before correction. The actual
facade source-file case then failed until the pipeline supplied explicit fresh
AST IDs; absent origin on borrowed nodes remains insufficient. The current
focused containment selection passes 63 cases in 9.56 seconds. Final six-module
source proof passes 90 cases in 14.70 seconds; final source-file/upgrade proof
passes 20 cases in 6.06 seconds. The final reviewed artifact broad suite passes
1044 cases with seven skips and one existing warning in 137.43 seconds. All 154
Python payloads match reviewed source, wheel and installation. The installed
public fixture rejects damaged source with force/partial options while preserving
four prior products, then repairs and repeats successfully. The HTML link
suite first failed six cases, then passes eleven; its related exporter/CLI
selection passes 172 cases. Commands and revision boundaries are in validation.

## Planned adoption criteria

Owner: Qt/QML integration maintainer. The three work packages are implemented;
their individual local source and installed acceptance is recorded below. This
heading retains its earlier external anchor. AC07 is a separate header discovery
contract; it does not borrow verification from the native syntax criterion.
The [INC-QML-08 plan](../docs/qt-qml/PLAN.md#inc-qml-08--installed-project-adoption-hardening)
records scope and exit checks. Original REQ-QML-001–017 hosted evidence applies to
its original bounded profile only. Every row here is locally verified for Windows
x64/Python 3.12; current hosted lanes remain unexecuted.

| Criterion | Evidence or exact remaining gap | Completion increment | Status |
| --- | --- | --- | --- |
| REQ-QML-018-AC01 | [Project/header adoption evidence](#project-and-header-adoption); [final combined installed profile](#final-adoption-delivery) | INC-QML-08a | Locally Verified (bounded Windows source/installed profile); wider hosted matrix unverified |
| REQ-QML-018-AC02 | [Native syntax and cache upgrade evidence](../docs/qt-qml/VALIDATION.md#inc-qml-08a-native-source-compatibility); [reference-callable evidence](#declared-providers-and-reference-callables); final installed matrix below | INC-QML-08a/29 | Locally Verified (bounded Windows source/installed profile); wider hosted matrix unverified |
| REQ-QML-018-AC03 | [Declared provider and reference-callable evidence](#declared-providers-and-reference-callables); final installed matrix below | INC-QML-08b/29 | Locally Verified (bounded Windows source/installed profile); wider hosted matrix unverified |
| REQ-QML-018-AC04 | [Declared provider and reference-callable evidence](#declared-providers-and-reference-callables); logical direction and mechanism/callback integrity regressions; final installed matrix below | INC-QML-08b/30/36/37 | Locally Verified (bounded Windows source/installed profile); wider hosted matrix unverified |
| REQ-QML-018-AC05 | `tests/test_qt_combined_adoption.py::test_req_qml018_ac05_combined_configured_project_matches_cold_warm_and_updates`; four actual isolated installed CLI profiles and selected installed lifecycle suite; final matrix below | INC-QML-08c/32/38 | Locally Verified (bounded Windows source/installed profile); wider hosted matrix unverified |
| REQ-QML-018-AC06 | `tests/test_qt_combined_adoption_safety.py::test_req_qml018_ac06_combined_rejection_retains_cache_products_and_retries`; `tests/test_qt_combined_adoption_safety.py::test_req_qml018_ac06_combined_readonly_destination_preserves_then_retries`; direction/repeat/publication regressions mapped below; final installed matrix | INC-QML-08c/31–38 | Locally Verified (bounded Windows source/installed profile); wider hosted matrix unverified |

## HTML community-view criteria

REQ-QML-019-AC01–AC03 retain local verification at the Python exporter/CLI and
emitted JavaScript boundaries. INC-QML-16 changes AC04 by removing Overview; its
current control acceptance is locally verified at emitted-script and reviewed
installed-artifact boundaries. Native browser/device behavior remains unverified.
Node harnesses execute production scripts with the external
vis network isolated; they prove dataset admission, controls and source payload,
not a new browser-engine or visual acceptance run. Installed-artifact identity and
executed commands are recorded in VALIDATION.md.

| Criterion | Exact production evidence | Increment | Status |
| --- | --- | --- | --- |
| REQ-QML-019-AC01 | `tests/test_html_community_recovery.py::test_req_qml019_ac01_large_export_recovers_complete_partition`; `tests/test_html_community_recovery.py::test_req_qml019_ac01_invalid_saved_membership_is_rebuilt_without_stale_names`; `tests/test_html_community_recovery.py::test_req_qml019_ac01_cli_exports_unclustered_saved_graph_without_sidecars`; `tests/test_html_community_recovery.py::test_req_qml019_ac01_explicit_graph_uses_adjacent_analysis_not_malformed_cwd_sidecar` | INC-QML-09 | Locally verified |
| REQ-QML-019-AC02 | `tests/test_html_community_recovery.py::test_req_qml019_ac02_existing_groups_get_missing_labels`; small/empty/authoritative group and name cases in the same module; `tests/test_qt_graph_html_payload.py::test_qml013_ac03_aggregated_html_explicitly_states_source_fact_omission`; existing escaping and written-node-info runtime regressions in `tests/test_export.py`; [current exact community-count assignments](#constructor-and-source-containment-corrections) | INC-QML-09; INC-QML-13 correction | Locally verified exporter/emitted-script counts and reviewed installed artifact; browser visual inspection is separate |
| REQ-QML-019-AC03 | `tests/test_html_community_recovery.py::test_req_qml019_ac03_invalid_computed_partition_preserves_output_and_recovers`; `tests/test_html_community_recovery.py::test_req_qml019_ac03_cli_unavailable_view_retains_prior_outputs_and_retries`; `tests/test_html_community_recovery.py::test_req_qml019_ac03_cli_failure_has_no_false_write_and_preserves_prior_html`; `tests/test_html_community_recovery.py::test_req_qml019_ac03_isolate_partition_over_hard_cap_is_not_published` | INC-QML-09 | Locally verified; actual atomic replacement failure injected at its OS boundary |
| REQ-QML-019-AC04 | `tests/test_html_initial_view.py::test_default_select_all_constructs_every_exported_node_and_edge_before_network`; `tests/test_html_initial_view.py::test_req_qml019_ac04_filters_all_none_preserve_endpoint_safe_source_data`; `tests/test_html_initial_view.py::test_req_qml019_ac04_search_restores_filtered_source_and_exact_metadata`; `tests/test_html_initial_view.py::test_small_grouped_and_ungrouped_views_default_to_select_all`; `tests/test_html_initial_view.py::test_req_qml019_ac04_partial_membership_cannot_mark_hidden_ungrouped_fact_selected` | INC-QML-09; INC-QML-16 removal | Locally verified current emitted-script controls and reviewed installed-artifact scripts. Native browser/device behavior unverified; earlier Overview results are revision-specific and superseded |

<a name="planned-project-membership-projection"></a>

## Project-membership projection

Owner: Qt project-metadata integration maintainer. INC-QML-14 owns all three
REQ-QML-020 criteria. Status: **Locally Verified for the bounded static public
profile**. The new production tests below have executed source, lifecycle,
consumer and reviewed installed-artifact evidence.
Current source/resource lookup, source-file containment and community edge counts
remain evidence for their existing boundary. Each independent membership site
must preserve declaration/target identity, direction, provenance and uncertainty
through the actual graph/consumer lifecycle. Qt policy 6/schema 7 at package
version 0.9.74 has source upgrade and reviewed installed public-fixture evidence.
Additional accepted-code-scope adoption checks pass; whole-root/provider/runtime
adoption gaps remain outside this closure.

| Criterion | Exact executed production evidence | Completion increment | Status |
| --- | --- | --- | --- |
| REQ-QML-020-AC01 | `tests/test_qt_project_membership.py::test_req_qml020_ac01_unused_component_has_persisted_build_and_resource_membership` (CMake/qmake; directed/undirected); `tests/test_qt_project_membership.py::test_req_qml020_ac01_metadata_spans_survive_bom_crlf_unicode_and_sanitation`; `tests/test_qt_project_membership.py::test_req_qml020_ac01_scoped_paths_repeated_declarations_and_query_keep_exact_identity`; `tests/test_qt_project_membership_updates.py::test_req_qml020_ac01_unused_packaged_component_survives_aggregate_export`. Targets uniquely accepted file/component endpoints, independent/repeated sites and same-name scoped files, `EXTRACTED` references, direction and original spans through facade/build/JSON reload/scoped query, unchanged loader/module lookup and actual aggregate-script membership counts. Source, consumer and final reviewed installed public-fixture evidence pass. | INC-QML-14 | Locally Verified (bounded static public profile) |
| REQ-QML-020-AC02 | `tests/test_qt_project_membership.py::test_req_qml020_ac02_source_projection_rejects_unproved_membership`; `tests/test_qt_project_membership.py::test_req_qml020_ac02_resources_reuse_existing_alias_guard_decisions`; `tests/test_qt_project_membership.py::test_req_qml020_ac02_corrupt_literal_transport_is_rejected`; `tests/test_qt_project_membership.py::test_req_qml020_ac02_location_prefix_cannot_authorize_another_source_span`; `tests/test_qt_project_membership.py::test_req_qml020_ac02_projection_reads_no_targets_and_executes_no_corpus`; `tests/test_qt_project_membership_updates.py::test_req_qml020_ac02_failed_metadata_join_preserves_products_and_recovers` (manual/force/watch); `tests/test_qt_project_membership_updates.py::test_req_qml020_ac02_join_exception_cannot_publish_partial_memberships`. Missing, duplicate, conditional, generated, wrong-role and out-of-root cases must have explicit status/reason and no target edge. The actual helper executes before injected failure; graph/manifest/analysis/root-marker bytes must remain unchanged. Projection guards target reads/discovery/process execution and preserves borrowed facts. All assigned source rejection/retention and final installed public-fixture checks pass. | INC-QML-14 | Locally Verified (bounded static public profile) |
| REQ-QML-020-AC03 | `tests/test_qt_project_membership.py::test_req_qml020_ac03_fresh_derived_sites_replace_borrowed_state_without_mutation`; `tests/test_qt_project_membership.py::test_req_qml020_ac03_typed_file_role_survives_punctuation_and_borrowed_publication`; `tests/test_qt_project_membership_updates.py::test_req_qml020_ac03_metadata_resource_and_source_updates_remove_stale_memberships` (manual/watch); `tests/test_qt_project_membership_updates.py::test_req_qml020_ac03_policy_upgrade_refreshes_unchanged_packaging` (extract/update); `tests/test_qt_project_membership_updates.py::test_req_qml020_ac03_membership_ids_are_independent_of_checkout_location`; `tests/test_qt_project_membership_updates.py::test_req_qml020_ac03_pipeline_publishes_replacement_without_borrowed_mutation`; malformed-resource recovery and aggregate-export tests above. Targets cold/warm/full/manual/watch parity, source edit/rename with metadata/alias updates, alias duplicates, target deletion, stale-edge removal, stable unrelated Python/relocated root identity, accepted typed-file identity through punctuation/publication, fresh-site replacement without borrowed mutation and policy-5 to policy-6 refresh without source/package changes. Complete source/lifecycle/consumer and reviewed installed public-fixture evidence pass for the bounded profile. | INC-QML-14 | Locally Verified (bounded static public profile) |

The first actual lifecycle selection failed all four cases in 3.76 seconds before
projection existed: the public fixture had no `membership_resolution` sites.
The failure record is baseline regression proof. Exact executed commands,
artifact identity and remaining broader limitations are in
[validation](../docs/qt-qml/VALIDATION.md#inc-qml-14-membership-projection).
The frozen source-projection module passes 26 cases in 1.90 seconds; its positive
facade cases fail twice with only projection disabled and actual parsing/indexes
retained. The reviewed-wheel checkpoint's combined selection passes 37 cases in
8.77 seconds. Two added directed graph variants then pass within a final
39-case focused selection in 9.50 seconds, with no production change. The
reviewed-wheel broad selection passes 1081 cases with seven documented skips and
one existing warning in 135.53 seconds. All 155 Python modules are byte-equal
between reviewed source, wheel and isolated installation. The installed public
CMake/qmake/qrc fixture has six resolved membership sites, accepted consumer/HTML
results, and actual force/partial failure retention followed by repair/repeat.
Browser visual, other-platform and executable Qt proof are not claimed. The
additional accepted-code-scope adoption refresh also passes. That INC-QML-14
checkpoint contained 81 criteria; the subsequent camera requirement adds three
without changing earlier criterion identities or revision evidence.

## Temporary middle-button camera and Overview removal

Owner: HTML viewer maintainer. INC-QML-16 owns REQ-QML-021-AC01–AC03 and the changed
REQ-QML-019-AC04, depending on the existing REQ-QML-019 community-view contract.
Status: **Locally verified at emitted-script and reviewed installed-artifact
boundaries; native browser/device and other-platform behavior unverified**.
The tests below execute the actual
emitted navigation script with a recording camera/network boundary; a stubbed
network does not establish a browser-engine, layout or native-device result.
The initial-view module separately retains checked startup, controls, dataset and
source metadata assertions while removing obsolete Overview expectations.

| Criterion | Exact production evidence and boundaries | Increment | Status |
| --- | --- | --- | --- |
| REQ-QML-021-AC01 | `tests/test_html_middle_pan.py::test_req_qml021_ac01_middle_drag_translates_both_axes_at_current_zoom` (24 horizontal/vertical/diagonal, four-scale, source/aggregate variants); incremental client delta divided by current zoom, preserved scale, no animation, and suppressed native middle autoscroll | INC-QML-16 | Locally verified emitted-script and reviewed installed-artifact boundary; native browser/device and other platforms unverified |
| REQ-QML-021-AC02 | `tests/test_html_middle_pan.py::test_req_qml021_ac02_release_cancel_blur_and_lost_buttons_end_drag`; `tests/test_html_middle_pan.py::test_req_qml021_ac02_capture_failure_has_window_fallback_and_no_lingering_drag`; `tests/test_html_middle_pan.py::test_req_qml021_ac02_invalid_camera_or_input_aborts_without_jump`; `tests/test_html_middle_pan.py::test_req_qml021_ac02_invalid_press_cannot_capture_or_resume_after_repair`; `tests/test_html_middle_pan.py::test_req_qml021_ac02_unrelated_pointer_and_nonmiddle_release_preserve_owned_drag`. Matching release/cancel, lost button/capture, blur/pagehide, outside movement/capture fallback, invalid finite/scale/derived-position and cursor restoration controls prove termination and no later jump | INC-QML-16 | Locally verified emitted-script and reviewed installed-artifact boundary; native browser/device and other platforms unverified |
| REQ-QML-021-AC03 | `tests/test_html_middle_pan.py::test_req_qml021_ac03_other_inputs_and_source_datasets_remain_unchanged`; `tests/test_html_middle_pan.py::test_req_qml021_ac03_filters_and_search_work_after_middle_drag`; left/right/touch/wheel coexistence and actual startup/filter/all/none/search/inspector controls preserve graph/payload/dataset metadata, node positions, physics and temporary camera-only state | INC-QML-16 | Locally verified emitted-script and reviewed installed-artifact boundary; native browser/device and other platforms unverified |

The focused command executes both current modules:

```powershell
.venv/qt-mcp-312/Scripts/python.exe -X utf8 -m pytest -q tests/test_html_middle_pan.py tests/test_html_initial_view.py --tb=short -rs
```

Result: **60 passed**, 6.57 seconds, with no skips, after restoring retained Qt
projection, metadata/span/attribute and endpoint-safe source-edge assertions.
The earlier 60-pass/6.71-second checkpoint precedes that assertion review; the
44-pass/4.99-second checkpoint precedes independent horizontal/vertical/diagonal expansion.
An earlier missing-hook selection has 28 failed cases; the integration owner's validation record owns its
exact command/revision. Earlier exporter/CLI/membership-consumer regression proof
passes 219 cases in 54.20 seconds before the sixteen additional geometry cases.
The final exporter/CLI/membership/inspector selection passes 231 cases in 53.15
seconds, without failures or skips.
Wheel-artifact/Qt HTML consumers pass seven cases in 4.60 seconds, and the legacy
export module passes 67 cases in 2.95 seconds. These recorded script/artifact
boundaries do not close native browser/device behavior. The final 231-case
selection and seven additional consumer/wheel cases cover 238 distinct cases.
Five touched owners pass Ruff; the four navigation/source/test owners pass
explicit-runtime Pyright with zero errors/warnings. Including the legacy
`tests/test_export.py` owner reports one unchanged `reportOptionalOperand` error
at line 1008, reproduced against the prior revision with the same explicit
include/exclude configuration. The narrow listener-registration adjustment does
not alter that optional-return expression, inspector assertions or type checks.

The reviewed production tree is `a991dd9fb2d638cf15fbb2c76499ed1f6ebd51ea`; wheel
SHA256 is `11e370a19d328a01b4e9e30726731c815b4ef58399833ff3d0a7c644f71e98f0`.
All 156 Python payloads match reviewed source, wheel and isolated installation.
The installed viewer artifact retains canonical/RAW data, checked startup and
source inspectors; actual emitted-script camera moves and release/blur/retry
cleanup pass. No private input identifiers, paths or source are retained here.
Helper/HTML/initial-view/middle-pan measurements are 116/789/245/223 physical lines;
the updated inspector harness remains within its documented 1377-line exception.
Qt policy 6 and AST schema 7 are unchanged; this is viewer input, with no source
execution, new SDK, persistence operation or graph diagnostic. Earlier Overview
and camera selection evidence is historical. A changed requirement is verified
only after its own applicable controls and failure/cleanup cases pass; broader
adoption, inherited endpoint and constructor-overload gaps remain independent.

## Follow-up audit scope corrections

Inspected production revision: `95adbdc165f44a96bf275a7870bb1da4d82a5bea`.
Public static fixtures; Python 3.12.14, tree-sitter 0.25.2 and language-pack 0.11.0;
Windows. No Qt SDK or corpus execution. The probes are explicit opt-in diagnostic
tests and retain correct failing assertions. Their default-discovery exclusion is
temporary audit ownership, not regression completion. The correction owner must
promote them into normal collection and reverify all affected criteria.

| Acceptance | Exact probe or system assignment | Outcome / correction owner |
| --- | --- | --- |
| REQ-QML-017-AC02/AC04 | `tests/audit/probe_qt_qml_object_boundaries.py::test_cpp_reflective_child_property_does_not_inherit_qml_lexical_root` (read/write/invoke variants) | Three persisted-edge rejections fail; INC-QML-17 reverse-access resolver owner |
| REQ-QML-017-AC02/AC04 | `tests/audit/probe_qt_qml_object_boundaries.py::test_cpp_findchild_does_not_search_sibling_outside_receiver_subtree`; `tests/audit/probe_qt_qml_object_boundaries.py::test_cpp_findchild_direct_search_cannot_select_grandchild` | Both persisted-edge rejections fail; INC-QML-17 |
| REQ-QML-017-AC03/AC04 | `tests/audit/probe_qt_qml_object_boundaries.py::test_disjoint_engine_scopes_cannot_supply_context_provider` | Provider edge reaches another engine; rejection fails; INC-QML-18 context integration owner |
| REQ-QML-017-AC02/AC03 | `tests/audit/probe_qt_qml_object_boundaries.py::test_public_receiver_and_engine_positive_controls` | Own-object/root/engine controls pass; they do not validate failing scopes |
| REQ-QML-018-AC03 | `tests/audit/probe_qt_qml_object_boundaries.py::test_pending_typed_factory_provider_remains_unresolved` | Historical baseline exclusion only at 95adbdc; superseded by ordinary positive typed-provider regressions in INC-QML-08b. This opt-in probe is not current acceptance |
| REQ-QML-016-AC02/AC03/AC04 | `tests/audit/probe_qt_native_type_shadowing.py::test_req_qml016_connect_alias_cannot_select_unrelated_global_signal` (using/typedef); `tests/audit/probe_qt_native_type_shadowing.py::test_req_qml016_block_alias_does_not_change_before_and_after_native_scope` | Three wrong persisted-endpoint cases fail; INC-QML-19 native type/endpoint owners |
| REQ-QML-016-AC01/AC03/AC04 | `tests/audit/probe_qt_native_type_shadowing.py::test_req_qml016_emission_alias_cannot_select_unrelated_global_signal` (using/typedef) | Two wrong emission endpoints fail; INC-QML-19 |
| REQ-QML-008-AC01/AC03 | `tests/audit/probe_qt_native_type_shadowing.py::test_req_qml008_alias_registration_cannot_export_global_class_to_qml` (using/typedef) | Two wrong native-to-QML registration/handler cases fail; INC-QML-19 |
| REQ-QML-008-AC01 and REQ-QML-016-AC01/AC02/AC04 | `tests/audit/probe_qt_native_type_shadowing.py::test_direct_native_type_control_preserves_roles_and_direction`; `tests/audit/probe_qt_native_type_shadowing.py::test_direct_registration_control_preserves_native_qml_endpoint` (Sender/Other variants) | Four direct native/QML controls pass through actual publication and directed reload |
| REQ-QML-021-AC01–AC03 and REQ-QML-019-AC04 | [Native navigation review procedure](../docs/qt-qml/VIEWER_SYSTEM_REVIEW.md) | Exact fixture/actions/evidence/failure/cleanup/owner defined; physical browser/device/platform execution remains unverified |
| REQ-QML-017-AC01/AC04 | `tests/audit/probe_qt_loader_forms.py::test_req_qml017_ac01_literal_loader_keeps_component_and_property_provenance` (engine URL constructor/component loadUrl/engine.load variants) | Two loader-admission assertions fail; engine.load control passes; INC-QML-20 collector/integration owner |

Executed command:

```text
.venv/Scripts/python.exe -X utf8 -m pytest tests/audit/probe_qt_qml_object_boundaries.py tests/audit/probe_qt_native_type_shadowing.py tests/audit/probe_qt_loader_forms.py -q --tb=short
```

Final combined result: **15 failed, 7 passed in 3.38 seconds**, one existing Hypothesis collection
warning. Thirteen failing variants expose four wrong-target root causes; two more expose loader omissions.
The independent existing lifecycle selection passed **67 tests in 21.43 seconds**;
the final native/QML compatibility selection passed **60 tests in 4.85 seconds**.
Neither establishes cold/warm/manual/watch parity for a correction not implemented.
At that baseline audit, reviewed installed-wheel, complete repository suite and
new hosted proof were unexecuted for the corrections. Current per-increment
package proof and repository gate failures are recorded in validation; new hosted
proof remains unexecuted. See [audit](../docs/qt-qml/FOLLOWUP_AUDIT.md)
and [plan](../docs/qt-qml/PLAN.md) for scope, dependencies and delivery gates.

## Receiver correction evidence (INC-QML-17)

These current mappings supplement the historical audit/profile rows above.
The reviewed installed artifact passes 98 selected cases with no skips/failures;
exact wheel identity and dependency limits are in
[validation](../docs/qt-qml/VALIDATION.md#inc-qml-17-receiver-ownership-and-construction-trees).
Full contribution gates ran at INC-QML-20; documented baseline failures remain.

| Acceptance | Automatically collected production evidence | Current boundary |
| --- | --- | --- |
| REQ-QML-017-AC02 | `tests/test_qt_receiver_boundaries.py::test_req_qml017_ac02_child_reflection_cannot_use_lexical_root`; `tests/test_qt_receiver_boundaries.py::test_req_qml017_ac02_findchild_rejects_siblings_depth_and_receiver`; `tests/test_qt_receiver_boundaries.py::test_req_qml017_ac02_property_held_qobject_has_construction_owner`; `tests/test_qt_receiver_boundaries.py::test_req_qml017_ac04_native_base_members_and_property_child_keep_source_proof`; `tests/test_qt_receiver_boundaries.py::test_req_qml017_ac02_inherited_member_is_receiver_owned_and_readonly_write_rejected` | Partial; receiver correction passes; static reflection correction has separate INC-QML-22 evidence below |
| REQ-QML-017-AC02/AC04 | `tests/test_qt_receiver_boundaries.py::test_req_qml017_ac02_duplicate_names_are_ambiguous_only_inside_receiver`; `tests/test_qt_receiver_boundaries.py::test_req_qml017_ac02_parent_bindings_and_js_writes_do_not_authorize_construction_tree`; `tests/test_qt_receiver_boundaries.py::test_req_qml017_ac02_unknown_types_and_component_templates_remain_unavailable`; `tests/test_qt_receiver_boundaries.py::test_req_qml017_ac02_construction_lookup_requires_accepted_declaration_proof`; `tests/test_qt_receiver_boundaries.py::test_req_qml017_ac02_proved_cpp_parent_mutation_keeps_source_but_no_target`; `tests/test_qt_receiver_boundaries.py::test_req_qml017_ac02_unsupported_findchild_options_cannot_choose_target`; `tests/test_qt_receiver_boundaries.py::test_req_qml017_ac02_unproved_findchild_type_filter_cannot_choose_object`; `tests/test_qt_receiver_boundaries.py::test_req_qml017_ac02_noncreatable_singleton_and_gadget_cannot_prove_qobject_creation` | Rejection/ambiguity and accepted source-construction proof pass without guessed targets |
| REQ-QML-017-AC04 | `tests/test_qt_semantic_correction_updates.py::test_req_qml017_ac04_receiver_tree_and_member_updates_remove_stale_edges`; `tests/test_qt_semantic_correction_updates.py::test_req_qml017_ac04_policy_refresh_failure_retains_products_and_retry`; `tests/test_qt_semantic_correction_updates.py::test_req_qml017_ac04_failed_completion_keeps_prior_graph_and_retries` | Partial; bounded receiver/provider/loader lifecycle passes; INC-QML-21/22 have separate evidence below; wider system gaps remain |

Existing QML scope/declaration/identity, loader, provider and reverse-update tests
also pass against that reviewed wheel. Factory providers, inherited native signal
ancestors and generic overload identity retain their separately recorded gaps.

## Declaration identity correction evidence (INC-QML-18)

These ordinary collected regressions replace A12's opt-in reproduction as current
acceptance evidence. Native/system lifetime and broader provider adoption remain
explicit gaps; the source profile does not execute a Qt engine.

| Acceptance | Exact production-boundary test | Observable evidence |
| --- | --- | --- |
| REQ-QML-017-AC03; REQ-QML-008-AC01 | `tests/test_qt_engine_identity.py::test_req_qml017_ac03_disjoint_same_named_engines_cannot_share_provider`; `tests/test_qt_engine_identity.py::test_req_qml017_ac03_same_engine_positive_retains_persisted_provider`; `tests/test_qt_engine_identity.py::test_req_qml017_ac03_nested_engine_shadow_does_not_receive_outer_provider`; `tests/test_qt_engine_identity.py::test_req_qml017_ac03_local_provider_lifetime_cannot_supply_later_load`; `tests/test_qt_engine_identity.py::test_req_qml017_ac03_engine_and_provider_parameters_have_exact_identity` | Disjoint/nested engines and expired providers have no persisted binding; exact local/parameter positive controls retain component and native property endpoints |
| REQ-QML-017-AC03/AC04 | `tests/test_qt_engine_identity.py::test_req_qml017_ac03_rejected_identity_preserves_precise_source_diagnostic`; `tests/test_qt_engine_identity.py::test_req_qml017_ac03_initial_properties_report_only_shared_identity_failure`; `tests/test_qt_engine_identity.py::test_req_qml017_ac04_writes_and_duplicate_declarations_fail_closed`; `tests/test_qt_engine_identity.py::test_req_qml017_ac04_conditional_and_deferred_lifetimes_have_no_identity`; `tests/test_qt_engine_identity.py::test_req_qml017_ac04_missing_or_corrupted_transport_cannot_fall_back_to_name` | Source-owned rejection reasons, mixed initial properties and corrupted transport never authorize a name-based fallback |
| REQ-QML-017-AC04 | `tests/test_qt_engine_identity.py::test_req_qml017_ac04_auto_and_explicit_handles_keep_declaration_identity`; `tests/test_qt_engine_identity.py::test_req_qml017_ac04_ids_are_portable_with_original_unicode_bom_crlf_spans`; `tests/test_qt_engine_identity_updates.py::test_req_qml017_ac04_engine_scope_changes_remove_stale_provider_links`; `tests/test_qt_engine_identity_updates.py::test_req_qml017_ac04_malformed_identity_source_retains_products_and_retries`; `tests/test_qt_engine_identity_updates.py::test_req_qml017_ac04_directed_query_affected_and_reload_keep_scoped_provider` | Partial; bounded receiver/provider/loader lifecycle passes; INC-QML-21/22 have separate evidence below; wider system gaps remain |

Exact source/artifact commands and outcomes belong to the corresponding validation
section. Full contribution gates run at the INC-QML-20 integration boundary.

## Native alias and ancestry correction evidence (INC-QML-19)

Ordinary collected cases supersede A13's opt-in probe as current bounded source
evidence. Imported-header targets, inherited event endpoints and generic overload
identity remain explicitly excluded or assigned to INC-QML-11/15.

| Acceptance | Exact test | Evidence |
| --- | --- | --- |
| REQ-QML-016-AC01/AC02/AC03/AC04 | `tests/test_qt_native_alias_scope.py::test_req_qml016_connect_alias_cannot_select_unrelated_global_signal`; `tests/test_qt_native_alias_scope.py::test_req_qml016_emission_alias_cannot_select_unrelated_global_signal`; `tests/test_qt_native_alias_scope.py::test_req_qml016_block_alias_does_not_change_before_and_after_native_scope`; `tests/test_qt_native_alias_scope.py::test_direct_native_type_control_preserves_roles_and_direction`; `tests/test_qt_native_alias_scope.py::test_namespace_lookup_and_namespace_alias_keep_original_byte_spans` | Source-local alias rejection/positive controls preserve canonical roles, relation distinctions and original spans |
| REQ-QML-008-AC01/AC03 | `tests/test_qt_native_alias_scope.py::test_req_qml008_alias_registration_cannot_export_global_class_to_qml`; `tests/test_qt_native_alias_scope.py::test_direct_registration_control_preserves_native_qml_endpoint`; `tests/test_qt_native_alias_scope.py::test_proven_alias_registration_exports_the_actual_class_and_qml_signal`; `tests/test_qt_native_alias_scope.py::test_local_alias_positive_and_rejection_profile` | Registration/QML projections select accepted aliases or retain no guessed provider |
| REQ-QML-016-AC01–AC04; REQ-QML-008-AC01/AC03 | `tests/test_qt_native_alias_updates.py::test_alias_type_edit_and_removal_refreshes_native_qml_cold_warm_consumers`; `tests/test_qt_native_alias_updates.py::test_unprovable_alias_replaces_old_edges_without_global_name_fallback`; `tests/test_qt_native_alias_updates.py::test_bad_native_alias_input_retains_outputs_then_recovers_and_repeats`; `tests/test_qt_native_alias_updates.py::test_accepted_header_alias_cannot_resolve_outer_global_native_or_qml_endpoint`; `tests/test_qt_native_alias_updates.py::test_transitive_header_alias_owns_shadow_but_not_prior_source_use`; `tests/test_qt_native_alias_updates.py::test_included_alias_fact_corruption_rejects_provenance_instead_of_resolving_outer_type`; `tests/test_qt_native_alias_updates.py::test_fresh_alias_header_uses_borrowed_qt_context_without_mutating_it` | Real manual/watch full/cold/warm, stale-edge removal, persisted/query/affected, parse/write failure retention and retry; included alias provenance rejection and borrowed-context isolation |
| REQ-QML-017-AC02/AC04 | `tests/test_qt_construction_authority.py::test_req_qml017_ac02_widget_and_unknown_ancestry_cannot_authorize_child_tree`; `tests/test_qt_construction_authority.py::test_req_qml017_ac04_direct_and_source_defined_qobject_chain_survives_publication`; `tests/test_qt_construction_authority.py::test_req_qml017_ac02_native_ancestry_reads_only_accepted_complete_source_facts`; `tests/test_qt_construction_authority.py::test_req_qml017_ac04_parent_mutation_spans_are_bounded_original_bytes`; `tests/test_qt_reflection_type_aliases.py::test_req_qml017_ac02_findchild_filter_rejects_shadowed_sdk_type` | Widget/unknown/corrupt/native shadow rejection; direct/derived non-widget controls, original 50/51 mutation-span boundary and unshadowed QObject filter |

Exact executed source/artifact evidence is retained in validation; whole-requirement
verification remains bounded by recorded adoption/inheritance/overload/system gaps.

At the INC-QML-19 checkpoint same-file qualified canonical classes remained an
implementation gap under REQ-QML-008-AC02, REQ-QML-016-AC01/AC04 and
REQ-QML-017-AC02/AC04. The original negative control proved safe rejection.
INC-QML-21 adds independent producer identities and collected proof/update cases
below; the genuine same-file native-versus-widget assertion now proves exact
ownership without weakening the unrelated rejection controls.

## Literal loader correction evidence (INC-QML-20)

| Acceptance | Exact ordinary test | Evidence |
| --- | --- | --- |
| REQ-QML-017-AC01/AC04 | `tests/test_qt_loader_provenance.py::test_req_qml017_ac01_literal_loader_keeps_component_and_property_provenance` | Existing engine.load control, URL engine constructor and component loadUrl/create retain original source spans, component/property targets and persisted direction |
| REQ-QML-017-AC01/AC04 | `tests/test_qt_loader_boundaries.py::test_req_qml017_ac01_supported_loader_overloads_have_one_source`; `tests/test_qt_loader_boundaries.py::test_req_qml017_ac01_local_file_wrapper_cannot_become_resource_url`; `tests/test_qt_loader_boundaries.py::test_req_qml017_ac01_absolute_fromlocalfile_retains_file_component`; `tests/test_qt_loader_boundaries.py::test_req_qml017_ac01_url_wrapper_shadow_cannot_lend_literal_argument`; `tests/test_qt_loader_boundaries.py::test_req_qml017_ac01_custom_component_engine_cannot_authorize_constructor`; `tests/test_qt_loader_boundaries.py::test_req_qml017_ac01_global_sdk_constructor_bypasses_namespace_shadow`; `tests/test_qt_loader_boundaries.py::test_req_qml017_ac01_sdk_name_shadow_cannot_authorize_loader`; `tests/test_qt_loader_boundaries.py::test_req_qml017_ac04_unknown_overload_or_creation_cannot_prove_root`; `tests/test_qt_loader_boundaries.py::test_req_qml017_ac01_constructor_mode_needs_sdk_type_authority`; `tests/test_qt_loader_boundaries.py::test_req_qml017_ac01_string_wrapper_requires_source_authority` | Literal controls, parent/mode/context boundaries, absolute file vs resource/relative/computed URLs and source-defined class/alias/callable rejection |
| REQ-QML-017-AC03/AC04 | `tests/test_qt_loader_providers.py::test_req_qml017_ac03_component_load_url_uses_its_exact_engine_provider`; `tests/test_qt_loader_providers.py::test_req_qml017_ac03_component_engine_shadow_cannot_borrow_another_provider`; `tests/test_qt_loader_providers.py::test_req_qml017_ac03_component_engine_assignment_condition_and_factory_reject` | Named/context-object provider joins use exact component-owned engine identity; shadows/reassignment/conditional/factory results cannot lend provider authority |
| REQ-QML-017-AC04 | `tests/test_qt_loader_updates.py::test_req_qml017_ac04_loader_edits_match_cold_warm_manual_and_watch`; `tests/test_qt_loader_updates.py::test_req_qml017_ac04_loader_parse_failure_preserves_products_and_recovers`; `tests/test_qt_loader_updates.py::test_req_qml017_ac04_loader_write_failure_preserves_products_and_retries`; `tests/test_qt_loader_updates.py::test_req_qml017_ac04_loader_directed_reload_query_and_affected_keep_endpoints` | Real source/resource/member edits and removal, cold/warm/manual/watch parity, stale-edge removal, four-product parse/replace failure retention, repaired retry/idempotency and actual persisted query/affected endpoints |
| REQ-QML-001-AC01/AC02; REQ-QML-003-AC01 | `tests/test_languages.py::test_qml_language_facade_preserves_source_declarations_and_spans` | CONTRIBUTING language convention, production facade and hand-checked declaration/original-byte spans; optional-parser absence is explicit skip, not acceptance |

The INC-QML-20 checkpoint retained failing opt-in INC-QML-22 cases under REQ-QML-017-AC02/AC04:
`tests/audit/probe_qt_reflection_type_shadowing.py::test_req_qml017_ac02_shadowed_reflection_type_cannot_create_qml_target`
and its positive control
`tests/audit/probe_qt_reflection_type_shadowing.py::test_req_qml017_ac04_unshadowed_sdk_reflection_preserves_targets_and_provenance`.
At the audited baseline twelve failures and two passes established the gap.
The opt-in probe remains excluded historical evidence; the ordinary INC-QML-22
regressions below now exercise the corrected rejection and positive controls.

The INC-QML-20 checkpoint retained the actual Windows failure assigned to INC-QML-23:
`tests/test_atomic_writes.py::test_write_text_atomic_refuses_a_readonly_destination_without_leaking_a_temp`
under REQ-QML-018-AC06. It failed on the original baseline and INC-QML-20
checkpoint. INC-QML-23/25 ordinary tests below cover the corrected actual OS
retention and caller completion boundary; wider adoption remains unverified.

## Follow-up correction evidence (INC-QML-21–27)

These cases extend the bounded profile; they do not close all wider adoption,
inherited-endpoint or overload criteria. Exact final commands, installed artifact
identity and contribution gate limitations are recorded in validation.

| Acceptance IDs | Ordinary production-boundary tests | Evidence scope |
| --- | --- | --- |
| REQ-QML-008-AC02; REQ-QML-016-AC01/AC04; REQ-QML-017-AC02/AC04 | `tests/test_cpp_qualified_identity.py::test_req_qml008_ac02_qualified_class_bodies_keep_distinct_portable_identities`; `tests/test_cpp_qualified_proof.py::test_req_qml008_ac02_using_namespace_bound_cannot_discard_competing_owner`; `tests/test_cpp_qualified_updates.py::test_req_qml017_ac04_qualified_owner_edits_match_cold_warm_updates_and_consumers` | Qualified IDs/body proof, signature/cap rejection, original bytes, canonical calls/emissions, full/manual/watch and affected preservation |
| REQ-QML-017-AC02/AC04 | `tests/test_qt_reflection_type_identity.py::test_req_qml017_ac02_shadowed_reflection_type_cannot_create_qml_target`; `tests/test_qt_reflection_type_identity.py::test_req_qml017_ac04_sdk_reflection_query_and_affected_use_exact_persisted_site`; `tests/test_qt_reflection_updates.py::test_req_qml017_ac04_reflection_source_qml_metadata_edits_remove_stale_targets`; `tests/test_qt_reflection_updates.py::test_req_qml017_ac04_reflection_parse_failure_retains_four_products_and_recovers`; `tests/test_qt_reflection_updates.py::test_req_qml017_ac04_reflection_write_failure_retains_four_products_and_retries` | Collected replacement for excluded reflection probe; strict whole-graph lifecycle and real failure/retry |
| REQ-QML-017-AC01/AC04 | `tests/test_qt_loader_sdk_declarations.py::test_req_qml017_ac01_incomplete_sdk_declaration_cannot_authorize_loader`; `tests/test_qt_loader_sdk_declarations.py::test_req_qml017_ac04_uncertain_sdk_use_retains_observed_loader`; `tests/test_qt_loader_sdk_declarations.py::test_req_qml017_ac04_loader_forward_edits_retire_and_restore_targets`; `tests/test_qt_loader_sdk_declarations.py::test_req_qml017_ac04_loader_forward_failure_retains_products_and_recovers` | SDK/source controls through JSON reload, full/manual/watch edits, uncertain facts, stale-edge removal and durable parse/publication recovery |
| REQ-QML-018-AC06; REQ-QML-011-AC04; REQ-QML-013-AC03 | `tests/test_atomic_replace_retention.py::test_req_qml018_ac06_readonly_rejects_without_displacing_destination`; `tests/test_atomic_replace_retention.py::test_req_qml018_ac06_fallback_failure_restores_prior_state`; `tests/test_atomic_replace_retention.py::test_req_qml018_ac06_restore_failure_keeps_recovery_backup`; `tests/test_qt_readonly_publication.py::test_req_qml018_ac06_readonly_graph_preserves_products_then_retries` | Actual Windows OS read-only failure, fallback ordering, retention and guarded caller retry; system/platform gaps remain separate |
| REQ-QML-012-AC02; REQ-QML-018-AC06; REQ-QML-011-AC04 | `tests/test_qt_product_publication.py::test_inc25_readonly_each_product_preserves_cohort_and_retries`; `tests/test_qt_product_publication.py::test_inc25_preparation_and_late_replace_faults_preserve_then_retry`; `tests/test_qt_product_publication.py::test_inc25_first_build_failure_publishes_no_acceptance_products`; `tests/test_publication.py::test_inc25_actual_rollback_fault_retains_recovery_copies`; `tests/test_publication.py::test_inc25_cleanup_failure_does_not_misreport_cohort_authority` | Actual durable acceptance cohort, first-build and later-stage failures, rollback integrity/cleanup and independent valid AST cache boundary |
| REQ-QML-011-AC02/AC04; REQ-QML-017-AC04 | `tests/test_qt_orphan_cleanup.py::test_req_qml017_ac04_watch_restored_sdk_source_has_no_stale_generic_placeholder`; `tests/test_qt_orphan_cleanup.py::test_req_qml011_ac04_complete_refresh_keeps_semantic_connected_and_hyperedge_stub_context`; `tests/test_qt_orphan_cleanup.py::test_req_qml011_ac04_partial_refresh_is_not_authority_to_remove_placeholder` | Strict full graph parity, immutable borrowed state and preserved live/semantic/hyperedge/source ownership |
| REQ-QML-007-AC01/AC03; REQ-QML-008-AC02/AC03; REQ-QML-017-AC03/AC04 | `tests/test_qt_native_property_notify.py::test_req_qml007_ac03_native_property_handler_maps_custom_and_conventional_notify`; `tests/test_qt_native_property_notify.py::test_req_qml008_ac02_shared_notify_preserves_two_independent_handler_sites`; `tests/test_qt_native_property_notify.py::test_req_qml007_ac03_notify_binds_only_block_injection_or_explicit_formals`; `tests/test_qt_native_property_notify.py::test_req_qml017_ac04_native_notify_query_and_affected_use_canonical_signal` | Real canonical signal/provider subscriptions, invalid notify rejection, explicit/legacy binding, reload/query/affected; wider native inheritance remains unverified |

The [exposure chapter review](../docs/qt-qml/EXPOSURE_CHAPTER_REVIEW.md) names the
official mechanism checklist. Macro accountability is separately recorded in the
API inventory. Excluded audit probes remain historical evidence and cannot by
themselves verify release acceptance. Corrected scenarios use ordinary discovery.

Native parameter/lifecycle mappings additionally cover:

| Acceptance IDs | Exact collected test | Scope |
| --- | --- | --- |
| REQ-QML-007-AC01/AC03 | `tests/test_qml_handler_formals.py::test_req_qml007_ac03_source_handler_formals_preserve_property_dependency`; `tests/test_qml_handler_formals.py::test_req_qml007_ac03_handler_authority_survives_parameter_display_limit`; `tests/test_qml_handler_formals.py::test_req_qml007_ac03_signal_parameter_overflow_rejects_without_truncation`; `tests/test_qml_handler_formals.py::test_req_qml007_ac03_handler_change_does_not_reclassify_unrelated_javascript` | Pure-QML/native explicit binding, display bounds and unchanged ordinary JS classification |
| REQ-QML-007-AC03; REQ-QML-008-AC02/AC03; REQ-QML-017-AC03/AC04 | `tests/test_qt_native_notify_updates.py::test_req_qml017_ac04_notify_edits_remove_stale_edges_with_full_parity`; `tests/test_qt_native_notify_updates.py::test_req_qml017_ac04_notify_parse_failure_retains_products_and_recovers`; `tests/test_qt_native_notify_updates.py::test_req_qml017_ac04_notify_manifest_failure_rolls_back_and_retries` | Cold/warm, directed/default, source/QML/qmake edits, manual/force/watch rejection and post-graph sidecar rollback/recovery |

| Acceptance IDs | Exact collected included-header/setup test | Scope |
| --- | --- | --- |
| REQ-QML-017-AC01/AC04 | `tests/test_qt_loader_header_shadows.py::test_req_qml017_ac01_included_forward_class_blocks_sdk_loader_and_wrapper_authority`; `tests/test_qt_loader_header_shadows.py::test_req_qml017_ac04_header_only_forward_edits_match_cold_warm_and_restore`; `tests/test_qt_loader_header_shadows.py::test_req_qml017_ac04_header_shadow_failure_preserves_products_and_retries`; `tests/test_qt_loader_header_shadows.py::test_req_qml017_ac04_class_shadow_walk_overflow_rejects_instead_of_discarding_header` | Accepted literal include/provenance shadows, independent native target roles, header-only lifecycle, failure/retry and 129-header rejection |
| REQ-QML-012-AC02; REQ-QML-018-AC06 | `tests/test_publication.py::test_inc25_setup_fault_has_safe_code_and_preserves_retry`; `tests/test_publication.py::test_inc25_partial_setup_cleanup_fault_retains_safe_recovery_evidence`; `tests/test_qt_product_publication.py::test_inc25_successful_ast_cache_does_not_authorize_failed_products` | Safe destination/setup diagnostics, owned partial setup cleanup and unchanged original successful cache-entry bytes with valid new entries |

Final source and installed acceptance for INC-QML-21–27 is recorded in
[validation](../docs/qt-qml/VALIDATION.md#final-local-follow-up-integration-evidence).
All executed correction cases pass. The installed publication symlink case,
existing atomic symlink/mode and external-symlink admission cases remain explicit
host gaps; optional language skips do not establish acceptance. Full repository
pytest and typing retain the separately recorded baseline failures. Broader
adoption/inherited native endpoint/overload criteria remain Partially verified.


## Inherited endpoints and pending adoption integration

| Acceptance ID | Exact production-boundary evidence | State |
| --- | --- | --- |
| REQ-QML-016-AC01 | `tests/test_qt_inherited_endpoints.py::test_req_qml016_ac01_grandparent_endpoints_use_declaring_members`; `tests/test_qt_inherited_endpoints.py::test_req_qml016_ac01_diamond_deduplicates_declarations_and_rejects_conflicts`; `tests/test_qt_inherited_endpoints.py::test_req_qml016_ac01_shadowing_precedes_role_signature_and_visibility`; `tests/test_qt_inherited_endpoints.py::test_req_qml016_ac01_ancestor_traversal_has_a_fail_closed_32_class_budget`; `tests/test_qt_inherited_access.py::test_req_qml016_ac01_external_member_pointer_cannot_cross_nonpublic_base`; missing/corrupt access and lexical namespace controls in those modules | Locally verified inherited declaration/access profile; explicit missing-declaration emissions remain INC-QML-28 |
| REQ-QML-016-AC04 | `tests/test_qt_inherited_endpoints.py::test_req_qml016_ac04_ancestor_edges_reach_reload_query_and_affected`; `tests/test_qt_inherited_updates.py::test_req_qml016_ac04_header_signal_base_and_site_edits_match_full_cold_warm`; `tests/test_qt_inherited_updates.py::test_req_qml016_ac04_malformed_ancestor_preserves_products_then_retries`; `tests/test_qt_inherited_updates.py::test_req_qml016_ac04_readonly_ancestor_refresh_preserves_cohort_and_retry` | Local manual/watch, reload/query/affected and real failure/retry pass; reviewed installed suite passes; wider hosted matrix unverified |
| REQ-QML-018-AC07 | [Project/header adoption evidence](#project-and-header-adoption) | Local source/update pass; reviewed installed suite passes; wider hosted matrix unverified |

Current adoption criterion count is seven, bringing the catalog to 85 acceptance
criteria across 21 requirements. Earlier six-criterion counts describe the earlier
profile. No criterion is renumbered. Runtime execution, arbitrary include search,
Qt SDK equivalence and other platforms remain outside this bounded static proof.

## Exact constructor overloads

| Acceptance IDs | Exact ordinary production tests | State and boundary |
| --- | --- | --- |
| REQ-QML-008-AC02 | `tests/test_cpp_overload_identity.py::test_req_qml008_ac02_overload_producer_ids_spans_and_exact_declaration_merge`; `tests/test_cpp_overload_identity.py::test_req_qml008_ac02_constructor_ids_survive_overload_addition_removal_and_parameter_rename`; `tests/test_cpp_overload_identity.py::test_req_qml008_ac02_distinct_pointer_reference_and_builtin_types_never_collapse`; `tests/test_cpp_overload_type_authority.py::test_req_qml008_ac02_shadow_transport_spans_address_original_bom_crlf_unicode_bytes`; `tests/test_qt_overload_consumers.py::test_req_qml008_ac02_and_qml011_ac01_exact_overload_native_consumers` | Local producer/facade/source/export/query/affected pass; exact accepted signature and original-span profile. Reviewed installed suite passes; wider hosted matrix unverified. |
| REQ-QML-008-AC03 | `tests/test_cpp_overload_identity.py::test_req_qml008_ac03_unsupported_signatures_keep_visible_distinct_occurrences_without_owner`; `tests/test_cpp_overload_identity.py::test_req_qml008_ac03_qualified_void_cannot_authorize_zero_argument_constructor`; `tests/test_cpp_overload_type_authority.py::test_req_qml008_ac03_angle_local_shadow_cannot_grant_sdk_constructor_identity`; `tests/test_cpp_overload_type_authority.py::test_req_qml008_ac03_include_walk_overflow_cannot_hide_sdk_shadow`; `tests/test_qt_overload_consumers.py::test_req_qml008_ac03_unknown_overload_signature_cannot_borrow_known_native_class` | Local uncertainty, duplicate/type/include/transport rejection pass. Aliases, templates, dependent/function-pointer/array/variadic signatures remain unsupported. |
| REQ-QML-011-AC01 | `tests/test_cpp_overload_updates.py::test_req_qml011_ac01_ac04_overload_signature_edit_removal_and_repeat_parity`; `tests/test_qt_overload_consumers.py::test_req_qml008_ac02_and_qml011_ac01_exact_overload_native_consumers` | Local cold/warm/full/manual/watch, exact native ownership and canonical consumer parity pass. |
| REQ-QML-011-AC04 | `tests/test_cpp_overload_updates.py::test_req_qml011_ac04_overload_publication_failure_retains_cohort_and_retries`; `tests/test_cpp_overload_updates.py::test_req_qml011_ac04_partial_constructor_parse_retains_accepted_identity_and_recovery`; `tests/test_cpp_overload_updates.py::test_req_qml011_ac04_schema9_name_id_fixture_migrates_unchanged_sources_to_exact_signatures` | Real OS and injected late publication failure, nonempty real cache retention, repair/repeat and modeled schema-9 name-ID fixture migration pass. This fixture models the old identity seam; it is not a replay of every old release semantic. |

Former blanket overloaded-constructor rejection is superseded by this accepted
signature profile. Existing ownership rejection tests now use duplicate equivalent
signatures; they retain their exact-owner and corruption assertions. Delegation
keeps the actual body owner without inventing a direct delegation call. The
reference-return callable omission remains a separate INC-QML-29 gap under
REQ-QML-018-AC02/AC03 until its ordinary producer regression passes.

Source integrity additionally maps REQ-QML-008-AC02/AC03 to
`tests/test_cpp_overload_source_integrity.py::test_req_qml008_ac03_out_of_file_constructor_transport_cannot_bind`
and the exact containing-class/corrupt-file authority controls in that module.
The fourteen collected cases pass against the production binder. Source-size
authority does not turn incomplete SDK include evidence into type authority.

## Explicit emission observations

| Acceptance IDs | Exact ordinary tests | State |
| --- | --- | --- |
| REQ-QML-016-AC01 | `tests/test_qt_explicit_emissions.py::test_req_qml016_ac01_explicit_unknown_sites_do_not_admit_bare_calls`; `tests/test_qt_explicit_emissions.py::test_req_qml016_ac01_long_comment_crlf_bom_and_unicode_keep_original_spans`; `tests/test_qt_explicit_emissions.py::test_req_qml016_ac01_explicit_annotation_owns_emission_mechanism`; `tests/test_qt_explicit_emissions.py::test_req_qml016_ac01_override_cannot_recover_annotation_by_prefix`; `tests/test_qt_explicit_emissions.py::test_req_qml016_ac01_computed_receiver_keeps_full_explicit_source_site` | Local known/unknown/override/mechanism/original-byte source acceptance passes; computed receiver target remains unavailable. |
| REQ-QML-016-AC04 | `tests/test_qt_explicit_emissions.py::test_req_qml016_ac04_unknown_emissions_reload_as_owned_unresolved_sites`; `tests/test_qt_explicit_emission_updates.py::test_req_qml016_ac04_header_rename_remove_restore_and_marker_edits_preserve_observations`; `tests/test_qt_explicit_emission_updates.py::test_req_qml016_ac04_failed_explicit_refresh_retains_products_and_retries`; `tests/test_qt_explicit_emission_updates.py::test_req_qml016_ac04_readonly_declaration_removal_preserves_graph_and_explicit_retry` | Actual facade/build/reload/affected, cold/warm/manual/watch and real write-failure/repaired-repeat parity pass; Reviewed installed suite passes; final profile and limits appear below. |

## Project and header adoption

| Acceptance IDs | Exact ordinary tests | State and limits |
| --- | --- | --- |
| REQ-QML-018-AC01 | `tests/test_qt_qmake_adoption.py::test_req_qml018_ac01_pwd_paths_preserve_current_file_and_original_token_spans`; `tests/test_qt_qmake_adoption.py::test_req_qml018_ac01_unrelated_conditional_build_settings_do_not_hide_module`; `tests/test_qt_qmake_adoption.py::test_req_qml018_ac01_relevant_conditions_remain_source_owned_uncertainty`; `tests/test_qt_qmake_adoption_integration.py::test_req_qml018_ac01_direct_facade_project_index_and_reload_preserve_pwd_roles`; `tests/test_qt_qmake_adoption_integration.py::test_req_qml018_ac01_metadata_only_pwd_edit_removal_matches_clean_updates` | Local reader/facade/project-index/reload/query and cold/warm/manual/watch pass. PWD is current-file literal evidence; import hints never extend discovery or configured roots. |
| REQ-QML-018-AC06 | `tests/test_qt_qmake_adoption.py::test_req_qml018_ac06_scope_depth_is_bounded`; `tests/test_qt_qmake_adoption.py::test_req_qml018_ac06_multibyte_path_transport_limit_is_explicit`; `tests/test_qt_qmake_adoption_integration.py::test_req_qml018_ac06_rejected_metadata_preserves_products_and_existing_cache`; `tests/test_qt_qmake_adoption_integration.py::test_req_qml018_ac06_readonly_publication_after_metadata_edit_retains_and_retries`; `tests/test_qt_header_updates.py::test_req_qml018_ac06_header_refresh_denial_preserves_then_recovers` | Local conditional/expansion/root escape, parser and actual read-only publication retention/repaired-repeat pass. Reviewed installed suite passes; final profile and limits appear below. |
| REQ-QML-018-AC07 | `tests/test_qt_header_adoption.py::test_req_qml018_ac07_whitespace_header_uses_cpp_source_authority`; `tests/test_qt_header_adoption.py::test_req_qml018_ac07_inert_cpp_markers_keep_c_dispatch`; `tests/test_qt_header_adoption.py::test_req_qml018_ac07_objective_c_retains_dispatch_priority`; `tests/test_qt_header_adoption.py::test_req_qml018_ac07_header_prefix_budget_and_digit_separators`; `tests/test_qt_header_updates.py::test_req_qml018_ac07_header_dispatch_mutation_matches_cold_and_warm` | Local lexical/plain-C/Objective-C/original-byte, bounded prefix and extractor-switch lifecycle pass. Header classification grants no native SDK authority. |

## Declared providers and reference callables

| Acceptance IDs | Exact ordinary tests | State and limits |
| --- | --- | --- |
| REQ-QML-018-AC03 | `tests/test_qt_typed_provider_adoption.py::test_req_qml018_ac03_declared_expression_selects_backend_api`; `tests/test_qt_typed_provider_adoption.py::test_req_qml018_ac03_unknown_or_conflicting_factory_never_supplies_provider`; `tests/test_qt_typed_provider_adoption.py::test_req_qml018_ac03_conditional_provider_declaration_is_not_api_authority`; `tests/test_qt_declared_api_shapes.py::test_req_qml018_ac03_root_shape_must_match_literal_member_operator`; `tests/test_qt_declared_api_shapes.py::test_req_qml018_ac03_direct_producer_keeps_original_cv_shape_and_byte_position` | Exact source-owned API/shape/type/root evidence, malformed/unknown/conflicting/conditional/alias/operator rejection and no execution pass locally. |
| REQ-QML-018-AC04 | `tests/test_qt_typed_provider_adoption.py::test_req_qml018_ac04_context_service_subscriptions_have_distinct_sites`; `tests/test_qt_typed_provider_adoption.py::test_req_qml018_ac04_qml_lexical_and_property_shadows_precede_context_provider`; `tests/test_qt_typed_provider_consumers.py::test_req_qml018_ac04_typed_subscriptions_survive_build_reload_and_query`; `tests/test_qt_context_implicit_subscriptions.py::test_req_qml018_ac04_native_parameters_own_nested_provider_and_callback_lookup`; `tests/test_qt_context_implicit_subscriptions.py::test_req_qml018_ac04_nearer_local_callback_keeps_explicit_authority`; `tests/test_qt_declared_proof_integrity.py::test_req_qml018_ac04_ac06_reloaded_notify_proof_retains_mapping_identity` | Source subscription/handler identities, real NOTIFY, original scopes, explicit/local/implicit binding and default/directed reload pass; delivery is not a calls edge. Affected direction closes separately in INC-QML-30. |
| REQ-QML-018-AC05/AC06 | `tests/test_qt_typed_provider_updates.py::test_req_qml018_ac05_cpp_qml_metadata_and_signal_updates_match_clean_rebuild`; `tests/test_qt_typed_provider_updates.py::test_req_qml018_ac06_parser_and_resolver_failure_preserve_then_recover`; `tests/test_qt_declared_proof_integrity.py::test_req_qml018_ac06_typed_hop_rejects_altered_authoritative_declaration`; `tests/test_qt_declared_proof_integrity.py::test_req_qml018_ac06_typed_notify_revalidates_property_accessor_provenance` | Real source/configuration updates, cache/graph/cohort retention and repaired retry; independently corrupted canonical role/owner/file/span/type/accessor proof rejects. Reviewed installed suite passes; final profile and limits appear below. |
| REQ-QML-008-AC02/AC03; REQ-QML-018-AC02/AC03 | `tests/test_cpp_reference_returns.py::test_req_qml018_ac02_ac03_reference_return_has_canonical_callable`; `tests/test_cpp_reference_returns.py::test_req_qml018_ac02_qualified_reference_declaration_and_definition_keep_one_callable`; `tests/test_cpp_reference_returns.py::test_req_qml018_ac02_ac03_reference_provider_spans_and_consumers_survive_reload`; `tests/test_cpp_reference_returns.py::test_req_qml018_ac02_reference_fallback_requires_one_function_child` | Accepted grammar wrapper, ordinary controls, exact generic identity and original bytes; unsupported/missing/competing child authority rejects. Reference API profile preserves CV without runtime proof. |
| REQ-QML-011-AC01/AC04; REQ-QML-018-AC02/AC03/AC06 | `tests/test_cpp_reference_return_updates.py::test_req_qml018_ac02_ac03_reference_factory_edits_keep_identity_and_drop_stale_provider_edges`; `tests/test_cpp_reference_return_updates.py::test_req_qml018_ac02_ac03_reference_admission_failure_preserves_and_repairs`; `tests/test_cpp_reference_return_updates.py::test_req_qml018_ac02_ac03_readonly_reference_edit_retains_products_and_retries` | Actual C++-only manual/watch, cold/warm, stale-edge removal, parser/late publication/real Windows read-only failure, repaired idempotent retry pass locally. |

## Affected logical direction

Callback correspondence additionally assigns REQ-QML-018-AC04/AC06 to
`tests/test_qt_context_callback_integrity.py::test_req_qml018_ac04_ac06_callback_target_cannot_be_substituted`,
`tests/test_qt_context_callback_integrity.py::test_req_qml018_ac04_ac06_local_callback_precedes_same_named_qml_function`,
`tests/test_qt_context_callback_integrity.py::test_req_qml018_ac06_callback_borrowed_provenance_is_revalidated`
and `tests/test_qt_context_callback_integrity.py::test_req_qml018_ac04_callback_lookup_retains_object_scope`.
These exercise actual raw and default/directed build/JSON/reload, derived target
substitution, borrowed source/span/scope corruption and local/qualified controls.

| Acceptance IDs | Exact ordinary tests | State and limits |
| --- | --- | --- |
| REQ-QML-018-AC04; REQ-QML-017-AC04; REQ-QML-011-AC01 | `tests/test_qt_affected_direction.py::test_native_provider_affected_uses_accepted_serialized_direction`; `tests/test_qt_affected_direction.py::test_logical_member_seed_finds_caller_without_reporting_seeded_method`; `tests/test_qt_affected_direction.py::test_legacy_edges_without_direction_keep_existing_traversal`; `tests/test_qt_affected_direction.py::test_logical_direction_depth_cycles_and_repeated_query_preserve_graph` | Local real build/JSON reload/CLI, directed/undirected insertion reversal, legacy, depth/filter/source-site and graph-preservation proof passes. |
| REQ-QML-018-AC06; REQ-QML-011-AC04 | `tests/test_qt_affected_direction.py::test_corrupt_direction_cannot_fall_back_to_physical_incoming`; `tests/test_qt_affected_direction.py::test_qt_owner_promotion_rejects_partial_or_foreign_direction`; `tests/test_qt_affected_direction.py::test_typed_reload_preserves_corrupt_dependency_direction_for_rejection`; `tests/test_qt_affected_direction.py::test_typed_reload_preserves_corrupt_owner_direction_for_rejection`; `tests/test_qt_affected_direction.py::test_boolean_marker_cannot_coerce_integer_endpoint_identity`; `tests/test_qt_affected_direction.py::test_parallel_edges_keep_valid_filtered_mechanism_after_invalid_direction` | Complete/partial/foreign/ill-typed/directed-contradictory corruption cannot authorize a dependency or source-owner link. Reviewed installed suite passes; final profile and limits appear below. |
| REQ-QML-018-AC04/AC06; REQ-QML-011-AC01/AC04 | `tests/test_qt_affected_direction_updates.py::test_native_affected_direction_cold_warm_update_removal_recovery_and_repeat` | Actual manual/watch source edits, removal, repair and cold/warm/repeated parity pass locally. |

## JSON direction integrity and combined adoption

| Acceptance IDs | Exact ordinary tests | State and limits |
| --- | --- | --- |
| REQ-QML-013-AC01/AC03; REQ-QML-018-AC04/AC06 | `tests/test_qt_json_direction.py::test_json_direction_rejection_preserves_previous_bytes_and_safe_diagnostic`; `tests/test_qt_json_direction.py::test_json_directed_contradiction_rejects_before_first_file_exists`; `tests/test_qt_json_direction.py::test_native_source_proof_export_reload_consumer_survives_rejection_and_repair`; `tests/test_qt_json_direction.py::test_undirected_reversed_storage_retains_real_qml_dependency_direction` | Local real writer/native proof/reload/affected, force/rejection/prior-output/repair and accepted insertion reversal pass. |
| REQ-QML-013-AC01/AC03; REQ-QML-018-AC06 | `tests/test_qt_json_direction.py::test_external_direction_rejection_precedes_file_or_database_connection`; `tests/test_qt_json_direction.py::test_external_bidirectional_wrapper_honors_logical_pair_but_json_requires_native_direction`; `tests/test_qt_json_direction.py::test_legacy_unmarked_edges_and_valid_self_pairs_preserve_native_identity` | External preflight/call boundary and compatible logical wrapper behavior pass; no live database engine proof is claimed. |
| REQ-QML-011-AC04; REQ-QML-018-AC06 | `tests/test_qt_json_direction_updates.py::test_rejected_direction_clustered_publication_retains_products_cache_and_repairs` | Actual clustered manual/watch serializer rejection preserves seven durable products and real source-cache bytes; repair equals clean source contracts and repeat is byte-identical. |
| REQ-QML-018-AC01–AC05/AC07 | `tests/test_qt_combined_adoption.py::test_req_qml018_ac05_combined_configured_project_matches_cold_warm_and_updates` | Public combined CMake/qmake, whole root/safe application subroot, configured module, inherited emission/exact constructor/typed API/subscription, source cold/warm/manual/watch and QML-only callback edit parity pass locally. Reviewed installed suite passes; final profile and limits appear below. |
| REQ-QML-018-AC06 | `tests/test_qt_combined_adoption_safety.py::test_req_qml018_ac06_combined_rejection_retains_cache_products_and_retries`; `tests/test_qt_combined_adoption_safety.py::test_req_qml018_ac06_combined_readonly_destination_preserves_then_retries` | Missing parser, malformed source, unsafe import root and actual Windows read-only graph replacement retain prior products/cache and succeed on corrected retry/idempotent repeat. Reviewed installed suite passes; final profile and limits appear below. |

## First raw-update repeat

| Acceptance IDs | Exact ordinary tests | State and limits |
| --- | --- | --- |
| REQ-QML-011-AC01; REQ-QML-018-AC05/AC06 | `tests/test_qt_initial_repeat.py::test_cold_combined_no_cluster_repeat_keeps_bytes_mtime_and_changed_source`; `tests/test_qt_initial_repeat.py::test_cold_generic_no_cluster_repeat_does_not_rewrite_first_graph` | Actual cold CLI/watch, CMake/qmake, whole-root/subroot, bytes/mtime repeat and subsequent real edit pass locally; Reviewed installed suite passes; final profile and limits appear below. |
| REQ-QML-011-AC01/AC04; REQ-QML-018-AC06 | `tests/test_qt_initial_repeat.py::test_known_absent_and_empty_run_lists_compare_equal_without_mutation`; `tests/test_qt_initial_repeat.py::test_nonempty_or_wrong_type_run_lists_remain_observable`; `tests/test_qt_initial_repeat.py::test_unknown_metadata_and_source_facts_still_compare_different`; `tests/test_qt_initial_repeat.py::test_real_raw_publication_failure_retains_prior_then_recovers` | Bounded normalization, unchanged input, meaningful/malformed/source proof controls and real staged replacement rejection/repair pass locally. |

## C++ file proof and candidate preflight

| Acceptance | Exact automated coverage | Current evidence |
| --- | --- | --- |
| REQ-QML-020-AC01/AC03; REQ-QML-008-AC02 | `tests/test_qt_cpp_file_roles.py::test_req_qml020_ac01_ac03_cpp_file_transport_retains_exact_file_identity`; `tests/test_qt_cpp_file_roles.py::test_req_qml008_ac02_cpp_file_role_preserves_separate_constructor_type_authority` | Current, legacy, incomplete, fresh and reloaded file proof; complete-record constructor authority stays separate. Local shared suite passes; Reviewed installed suite passes; final profile and limits appear below. |
| REQ-QML-020-AC02 | `tests/test_qt_cpp_file_roles.py::test_req_qml020_ac02_cpp_file_transport_cannot_authorize_corrupted_file_role`; `tests/test_qt_cpp_file_roles.py::test_req_qml020_ac02_cpp_file_joins_read_no_source_and_execute_no_corpus` | Actual borrowed transport at both joins rejects corruption without mutating, rereading or executing the corpus. Local shared suite passes; Reviewed installed suite passes; final profile and limits appear below. |
| REQ-QML-013-AC03; REQ-QML-011-AC04; REQ-QML-018-AC06 | `tests/test_qt_update_direction_integrity.py::test_actual_corrupt_candidate_refuses_shortcut_publication_and_repairs`; `tests/test_qt_update_direction_integrity.py::test_complete_reverse_pair_remains_accepted_on_undirected_storage` | 68 local manual/watch raw/clustered force/default failure/recovery/control cases pass; Reviewed installed suite passes; final profile and limits appear below. |

## Prior import and repeated event ownership

| Acceptance | Exact ordinary coverage | Evidence |
| --- | --- | --- |
| REQ-QML-020-AC03; REQ-QML-011-AC01/AC04 | `tests/test_qt_cpp_file_role_updates.py::test_req_qml020_ac03_cpp_transport_edits_and_removal_preserve_exact_membership`; `tests/test_qt_cpp_file_role_updates.py::test_req_qml011_ac04_cpp_deleted_import_keeps_still_referenced_external_endpoint`; `tests/test_qt_cpp_file_role_updates.py::test_req_qml011_ac04_cpp_import_cleanup_preserves_same_label_source_and_semantic_roles`; `tests/test_qt_cpp_file_role_updates.py::test_req_qml011_ac04_cpp_import_cleanup_requires_exact_prior_source_proof` | Manual/watch cold/warm deletion/restoration and exact raw prior-proof authority; source passes; Reviewed installed suite passes; final profile and limits appear below. |
| REQ-QML-018-AC06; REQ-QML-011-AC04 | `tests/test_qt_cpp_file_role_updates.py::test_req_qml018_ac06_cpp_orphan_cleanup_failed_publication_preserves_products_and_retries`; `tests/test_qt_cross_event_occurrences.py::test_req_qml018_ac06_cross_event_publication_failure_retains_prior_and_retries` | Actual Windows OS rejection, prior products and nonempty source cache retained, corrected retry/repeat pass; Reviewed installed suite passes; final profile and limits appear below. |
| REQ-QML-016-AC02/AC04; REQ-QML-017-AC02/AC04 | `tests/test_qt_cross_event_occurrences.py::test_req_qml016_ac02_ac04_cross_language_occurrences_keep_own_transport` | 1–16 mixed repeated connect/disconnect sites, both graph modes and QML/C++ directions, original span and bounded transport through production assembly/reload pass. |
| REQ-QML-011-AC03/AC04; REQ-QML-018-AC06 | `tests/test_qt_cross_event_occurrences.py::test_req_qml011_ac04_cross_event_edits_removal_and_repeat_match_clean`; `tests/test_qt_cross_event_occurrences.py::test_req_qml011_ac03_event_policy_refreshes_unchanged_source` | Actual C++/QML edits, stale removal, repair/full parity/unrelated Python and old-checkpoint refresh pass; Reviewed installed suite passes; final profile and limits appear below. |

## Bridge mechanisms and first minted provenance

| Acceptance | Exact ordinary coverage | Source result |
| --- | --- | --- |
| REQ-QML-018-AC04/AC06; REQ-QML-017-AC02/AC04; REQ-QML-010-AC03/AC04 | `tests/test_qt_bridge_mechanism_integrity.py::test_source_mechanisms_survive_builder_export_and_reload`; `tests/test_qt_bridge_mechanism_integrity.py::test_source_mechanism_substitution_is_rejected_before_graph_assembly`; `tests/test_qt_bridge_mechanism_integrity.py::test_context_access_revalidates_original_read_or_call`; `tests/test_qt_bridge_mechanism_integrity.py::test_endpoint_role_cannot_be_changed_to_repair_relation`; `tests/test_qt_bridge_mechanism_integrity.py::test_cross_language_flow_cannot_be_reversed_by_metadata`; `tests/test_qt_bridge_mechanism_integrity.py::test_reverse_reflection_repeats_original_supported_operation` | 166 new cases pass across 18 mechanisms; typed `uses` paths cannot bypass assembly proof. Reviewed installed suite passes; final profile and limits appear below. |
| REQ-QML-011-AC01/AC04; REQ-QML-018-AC05/AC06 | `tests/test_qt_publication_stub_origin.py::test_first_raw_stub_has_explicit_semantic_origin`; `tests/test_qt_publication_stub_origin.py::test_first_raw_import_repeat_preserves_bytes_mtime_and_genuine_edit`; `tests/test_qt_publication_stub_origin.py::test_existing_authored_endpoint_is_not_stamped_by_minting`; `tests/test_qt_publication_stub_origin.py::test_first_stamped_cpp_import_deletion_restoration_and_repeat`; `tests/test_qt_publication_stub_origin.py::test_new_stub_replacement_failure_retains_cohort_cache_then_retries` | 22 new cold manual/watch C++/Python, origin-preservation and injected replacement-failure/retry cases pass. Actual Windows denial is separately mapped above. Reviewed installed suite passes; final profile and limits appear below. |

## Final adoption delivery

Profile: Windows x64, Python 3.12.14, tree-sitter 0.25.2,
tree-sitter-language-pack 0.11.0; Qt 6 source inputs with CMake and qmake. The
reviewed tree is `9f0ae4ea75f47539df8ec8a66f1493b9e7f52b2f`. All 179 Python payloads
match the built wheel and installed package; the isolated installed selection
passes 3,024 tests with 36 historical optional/platform skips. None of the newly
added regression cases skips. Exact commands, digest and full-gate exceptions are
in [validation](../docs/qt-qml/VALIDATION.md#final-adoption-delivery).

| Criterion | Independently assigned production evidence | Current applicability and result |
| --- | --- | --- |
| REQ-QML-018-AC01 | Project/header table above: direct reader, facade, project index, reload and actual metadata-only updates; combined test and installed CMake/qmake whole/subroot CLI profiles | Locally Verified; arbitrary expansion/build execution excluded |
| REQ-QML-018-AC02 | Native syntax/cache upgrade and reference-return tables above: hand-checked original-byte facts, malformed/inert/generic controls and source/installed consumers | Locally Verified; unsupported relationships stay unresolved |
| REQ-QML-018-AC03 | `tests/test_qt_typed_provider_adoption.py::test_req_qml018_ac03_declared_expression_selects_backend_api`; `tests/test_qt_typed_provider_adoption.py::test_req_qml018_ac03_unknown_or_conflicting_factory_never_supplies_provider`; declaration-shape and producer-integrity modules mapped above, executed in source and installed selections | Locally Verified; accepted pointer/lvalue-reference declarations only, no factory execution or runtime conversion proof |
| REQ-QML-018-AC04 | `tests/test_qt_typed_provider_adoption.py::test_req_qml018_ac04_typed_service_call_and_property_are_source_owned`; `tests/test_qt_typed_provider_adoption.py::test_req_qml018_ac04_context_service_subscriptions_have_distinct_sites`; `tests/test_qt_typed_provider_consumers.py::test_req_qml018_ac04_typed_subscriptions_survive_build_reload_and_query`; affected direction, callback/mechanism proof and repeated-site tables above | Locally Verified in source and installed selections; no inferred runtime delivery |
| REQ-QML-018-AC05 | `tests/test_qt_combined_adoption.py::test_req_qml018_ac05_combined_configured_project_matches_cold_warm_and_updates`; `tests/test_qt_typed_provider_updates.py::test_req_qml018_ac05_cpp_qml_metadata_and_signal_updates_match_clean_rebuild`; four actual isolated installed CLI profiles, each initial/repeat exit 0 and identical graph bytes | Locally Verified; hand-checked CMake/qmake whole/subroot facts plus cold/warm/manual/watch mutation parity. Other hosted OS/Python cells unexecuted |
| REQ-QML-018-AC06 | Both combined safety tests above; `tests/test_qt_typed_provider_updates.py::test_req_qml018_ac06_parser_and_resolver_failure_preserve_then_recover`; JSON/preflight/repeat/orphan/publication failure tables above; actual Windows read-only denial complements injected replacement failure | Locally Verified in source and installed selections; prior products and nonempty successful cache, diagnostics, repair/repeat, no execution and bounded roots. Missing optional parser is separately exercised, not counted as a skip |
| REQ-QML-018-AC07 | Header-discovery/update table above: whitespace/BOM/CRLF/Unicode, comment/string/C/inconclusive/Objective-C controls and actual header edits; source and installed selections | Locally Verified; headers without accepted C++ evidence keep established dispatch |

INC-QML-11 inherited endpoints and INC-QML-15 exact constructor identity retain
their existing individual assignments above and pass in the reviewed installed
selection. The final full source command records 8,630 passed, 59 failed,
178 skipped and three warnings; the exact 59 failure identities equal baseline
5c0f2ca. Full Pyright has no added diagnostic identities but remains failed.
Current hosted platform jobs, live service delivery and native browser/device
procedure have not executed for this source. A global Verified or release-ready
status cannot be inferred from the bounded local evidence.

## Current-upstream integration — INC-QML-49

Source checkpoint: 65103f8; incoming v8:35adf43/package 0.9.76. Corrected integration
proof passes at the recorded 8b6c9d2 checkpoint below. The plan's acceptance matrix identifies affected IDs before
implementation; concrete tests, commands, individual outcomes, baseline gaps and
reviewed source/base/checkout identity are recorded here as they complete.
Previous hosted results remain immutable checkpoints. Old skips or aggregate
counts cannot establish the new joint-boundary criteria.

The frozen native profile is Windows x64, Python 3.12.14, package 0.9.76,
tree-sitter 0.25.2/language-pack 0.11.0, AST schema 13 and Qt policy 22.
The ordinary joint selection executes 99 cases: **83 passed, sixteen explicit
POSIX traversal exclusions, zero failures**. A final context-only correction is
verified separately by all six native admission cases, with their exact code,
empty unavailable context, fragmentwise backend-body absence and repaired repeat
assertions. POSIX link/`..` controls require actual POSIX runner execution.

| Affected acceptance IDs | Exact production tests and profile result |
| --- | --- |
| REQ-QML-002-AC02/AC03/AC04; REQ-QML-020-AC01 | `tests/test_upstream_qt_discovery_integration.py::test_req_qml002_ac02_ac03_detect_and_collect_share_named_metadata_and_copy_exclusions`; `tests/test_upstream_qt_discovery_integration.py::test_req_qml002_ac03_ac04_followed_metadata_keeps_lexical_scope_and_rejects_foreign_input`; direct cold/warm, real manual/watch and malformed-metadata cases in the same module. Eleven native cases pass; default/contained-follow, ignores and installed-copy exclusion remain production boundaries. |
| REQ-QML-003-AC04; REQ-QML-011-AC03/AC04; REQ-QML-018-AC05/AC06 | `tests/test_upstream_qt_cache_integration.py::test_req_qml003_ac04_qml018_ac05_old_namespaces_miss_and_refresh`; `tests/test_upstream_qt_cache_integration.py::test_req_qml003_ac04_qml018_ac05_mixed_cold_warm_serialized_facts`; `tests/test_upstream_qt_cache_integration.py::test_req_qml011_ac03_ac04_qml018_ac06_upgrade_failure_retains_repairs_repeats`. Six native cases pass, with old schemas 5/12 and both package versions, receiver-shadow/Qt fact parity, semantic byte retention and actual replacement failure/recovery. |
| REQ-QML-010-AC02; REQ-QML-018-AC04/AC06 | `tests/test_upstream_qt_export_integration.py::test_req_qml_010_ac02_original_parallel_links_retain_qml_direction`; `tests/test_upstream_qt_export_integration.py::test_req_qml_018_ac06_preserved_invalid_link_refuses_replacement`; `tests/test_upstream_qt_export_integration.py::test_req_qml_018_ac04_real_recluster_keeps_parallel_and_qml_links`. Ten native cases pass, preserving distinct generic mechanisms, actual QML direction/provenance, prior bytes/mtime, repaired repeat and real offline reclustering. |
| REQ-QML-010-AC03; REQ-QML-018-AC04 | `tests/test_upstream_qt_path_integration.py::test_req_qml_010_ac03_qualified_native_path_preserves_direction`; `tests/test_upstream_qt_path_integration.py::test_req_qml_018_ac04_duplicate_qualified_target_refuses_guess`. Three native cases pass through the real CLI, qualified file/symbol and exact-ID selection, same-name decoys, explicit duplicate rejection, directed/undirected controls and unchanged durable input. |
| REQ-QML-003-AC01/AC02/AC04; REQ-QML-011-AC01/AC04; REQ-QML-018-AC02 | `tests/test_upstream_qt_shared_integration.py::test_req_qml003_ac01_ac02_ac04_union_and_qt_native_cold_warm_reload`; `tests/test_upstream_qt_shared_integration.py::test_req_qml011_ac01_ac04_union_edit_removes_stale_member_keeps_native_endpoint`. Four native CMake/qmake cases pass with original spans, distinct same-named C++ union/native method ownership, real edits, stale removal and repeated output. |
| REQ-QML-020-AC01/AC02/AC03; REQ-QML-003-AC04; REQ-QML-011-AC03/AC04; REQ-QML-018-AC05/AC06 | `tests/test_qt_followed_metadata_alias.py::test_req_qml020_ac02_typed_producers_keep_distinct_alias_facts_and_original_spans`; `tests/test_qt_followed_metadata_alias.py::test_req_qml020_ac02_followed_metadata_facade_keeps_every_owner_cold_warm_and_reload`; `tests/test_qt_followed_metadata_alias.py::test_req_qml020_ac03_typed_alias_updates_remove_stale_facts_and_match_full_rebuild`; `tests/test_qt_followed_metadata_alias.py::test_req_qml020_ac03_alias_read_failure_retains_cohort_cache_and_repairs`; `tests/test_qt_followed_metadata_alias.py::test_req_qml020_ac02_membership_rejects_another_walked_owner_of_same_physical_input`; `tests/test_qt_followed_metadata_alias.py::test_req_qml020_ac03_policy21_alias_products_refresh_retain_and_recover`. All 43 native cases pass, including BOM/CRLF/Unicode spans, nested owner/target references, actual junction/root aliases, foreign inputs, malformed lexical context and native short leaf spelling. |
| REQ-QML-012-AC01/AC02/AC04; REQ-QML-020-AC02 | `tests/test_qt_source_identity_admission.py::test_req_qml020_ac02_native_admission_failure_keeps_its_code_and_recovers`. Six native production-reader cases pass after the final correction. `tests/test_qt_source_identity_admission.py::test_req_qml020_ac02_dotdot_input_keeps_actual_physical_target_and_containment` has sixteen Windows exclusions because actual POSIX physical link/`..` traversal is its test boundary; all sixteen cases pass individually in each recorded Linux lane below. |
| REQ-CORE-004-AC02 | `tests/test_extract.py::test_python_external_calls_survive_real_incremental_context` passes in the corrected native profile; all ten upstream extraction assertions remain structurally unchanged. The exact case is included in native hosted selection. |

The joint command is:

```text
python -X utf8 -m pytest tests/test_upstream_qt_cache_integration.py tests/test_upstream_qt_discovery_integration.py tests/test_upstream_qt_export_integration.py tests/test_upstream_qt_path_integration.py tests/test_upstream_qt_shared_integration.py tests/test_qt_followed_metadata_alias.py tests/test_qt_source_identity_admission.py -q --tb=short -rs --junitxml=joint.xml
```

Adjacent profiles pass 601 upstream/shared cases with eleven capability skips,
172 cache/stat-index/Python/Qt cases with eight file-symlink skips, and 271
export/path/direction cases with no skips. Counts overlap and are not summed.
Upstream multi-root stat-index warnings are retained. The original collector
leaks installed copies under both profiles; both immutable parent cache modules
reuse an old namespace; the old export loses a parallel relation and old path
lookup fails qualified identity. The prior full producer and current pre-fix
typed reader omit walked metadata; twenty ordinary alias cases fail before the
correction. Replays use actual immutable modules with current support imports,
not claims of full historical dependency equivalence or a checkout swap.

The corrected source wheel contains **185 Python payloads**, each byte-identical
to source and both isolated QML/core installs. Its SHA-256 is
`870a56e35e3a18afde2f7c13811e6e3fa8af53529f485a4399521133046d9d01`.
Both isolated installed smokes and all three reviewed-artifact tests pass.
Production and original coverage bytes remain unchanged during artifact proof.
The preliminary wheel precedes the final diagnostic correction and is not used
as final acceptance. Hosted wheels retain their own independently recorded digests.

Whole Ruff passes. All five skillgen validators pass, including 134 generated
artifacts. Frozen explicit-interpreter Pyright remains **605 errors, zero warnings**;
all new integration modules have zero diagnostics. Four errors move with an
upstream responsibility transfer and one Dart OptionalSubscript is reproduced
from the immutable incoming source. This is a failed existing contribution gate,
not successful typing. The final 197-distribution inventory changes only the
Graphify package version from the historical profile. No assertion, required
check, protection or historical commit is weakened or rewritten. Advisory
security and physical application/device procedures remain separate gaps.

Normal fork PR proof targets the exact incoming 35adf43 base on
`codex/qml-upstream-base`; the integration branch remains in the canonical
workspace. All prior PRs and the verified 65103f8 branch are preserved. No
upstream PR, merge, deployment or default-branch update is performed. Terminal
current head/base/checkout identities, cases, artifacts and cleanup remain the
hosted exit gate under REQ-CORE-004-AC01–AC04.

### First integrated hosted checkpoint — dbc4859

Draft [PR 7](https://github.com/SlinkyRamey/graphify/pull/7) binds source
`dbc4859f454f9478ac9596559a75efef5f10664d`, base
`35adf432b9d50f6f3d530ab5d7ec316819ef081c` and actual synthetic checkout
`db0b4dd0829082dca1e222bc90a85571871fb4bd`.
[CI 37287514274](https://github.com/SlinkyRamey/graphify/actions/runs/37287514274)
fails the stale platform selector guard in Python 3.14; the other three full
Linux jobs are cancelled, so those profiles remain incomplete.
The completed Linux 3.14 profile reports 9,354 passed, one failed and 121 skipped;
all 34 joint cases, 40 applicable alias cases, sixteen real POSIX link/`..`
controls and five service/wheel cases pass individually. All four retained
Linux wheel payloads match the 185 reviewed source modules, and every disposable
service container is confirmed absent, including the cancelled lanes. The
cancelled suites have no completed JUnit/pytest-exit/integrity evidence.
[Wheel matrix 37287514235](https://github.com/SlinkyRamey/graphify/actions/runs/37287514235)
exposes the same guard in native source lanes and a distinct native metadata
fixture seam. INC-QML-51/52 own their corrections; this is a failed integration
checkpoint, not hosted release acceptance.
All four macOS source lanes report one failed, 2,360 passed and 64 skipped;
each Windows source lane reports two failed, 2,404 passed and nineteen skipped.
The four Ubuntu wheel lanes each pass three artifact tests. All 24 isolated
optional/core installed smokes pass. Those wheel jobs retain no per-case JUnit,
wheel-digest or source/dependency artifact; native platform tests import the
checkout and remain source evidence distinct from the installed smokes.

The [native Windows job](https://github.com/SlinkyRamey/graphify/actions/runs/37287514274/job/111689834160)
passes 923 cases with 37 explicit exclusions and pytest exit zero. All 34 joint
integration, 43 followed-metadata alias, six native failure/recovery and exact
INC-CORE-10 cases pass individually. The exclusions retain 21 previous cases
plus sixteen actual POSIX link/`..` controls. Artifact 11335540466's API digest
and downloaded ZIP SHA-256 both equal
`1ce081338cf8963694e37b52b66a949c3149c3ceae3a7ca43b2b158e2815868c`.
The retained preflight proves both admitted Bash/sh consumers, Python 3.12.10
and Node 24.19.0; checkout, tracked inputs and all 197 dependencies are unchanged.
The skill job passes all five validators and 134 artifact checks. Advisory
security has an API-success conclusion but both raw commands return exit one:
Bandit reports four high, eight medium and 112 low findings; pip-audit reports
fifteen raw vulnerability rows across three packages. These are failed advisory
commands, not a clean security scan.

### Platform selection guard correction — INC-QML-51

Affected assignments: REQ-QML-001-AC01/AC03, REQ-QML-014-AC01/AC03/AC04 and
REQ-CORE-004-AC03 map to
`tests/test_qml_platform_matrix.py::test_wheel_runner_keeps_optional_core_and_isolated_offline_smoke_boundaries`.
The original production runner correctly admits the new upstream/Qt modules;
its guard incorrectly requires the former two-prefix literal. Local original
platform execution reports one passed/one failed test. Corrected execution of
both platform tests passes on native Python 3.12.14, with zero Ruff/Pyright
diagnostics. The guard now compiles only the trusted runner's actual selection
expression and exercises real temporary files in native and artifact-only
modes, retaining every install/isolation/offline assertion. It rejects unrelated
language modules, runner helpers and wrong extensions; deterministic selected
names include the joint regression prefix.
The owned glob seam reverses actual fixture entries; stable ordering therefore
depends on the production sort rather than the host's directory enumeration.

Executed command:

```text
python -X utf8 -m pytest tests/test_qml_platform_matrix.py tests/test_qml_wheel_artifact.py -q --tb=short --junitxml=platform.xml
```

Without the reviewed-wheel variable this command passes two tests and explicitly
skips three artifact tests; that run is guard evidence only. The retained reviewed
wheel procedure and corrected hosted revision own artifact acceptance.
The same command with the final reviewed-wheel variable passes all five tests
without skips. The wheel remains byte-identical to the runtime checkpoint;
these corrections change test evidence only.

### Native metadata-growth fixture correction — INC-QML-52

REQ-QML-002-AC03, REQ-QML-012-AC01/AC04 and REQ-QML-014-AC02/AC03/AC04 map to
`tests/test_qt_metadata_boundaries.py::test_cmake_scope_limit_and_source_file_growth_are_rejected`.
The original fake stat carries only size and causes native identity admission
to reject before the intended read-growth boundary. Correcting the stat witness
must retain native mode/device/inode and every available non-size stat field;
the original cmake_scope_limit and metadata_size_limit assertions remain
authoritative. The original ordinary case fails on native Python 3.14.7 with
native_source_spelling_unavailable before the intended read boundary. After
the fixture correction all 35 module cases pass without skips on native
3.10.21, 3.12.14, 3.13.15 and 3.14.7. The fixture checks its understated size,
every real non-size stat field and actual same-file identity, retaining the
original two rejection assertions. It measures 99 physical lines. Source
runtime, dependencies and original coverage are unchanged; corrected hosted
source outcomes pass in the verified integrated checkpoint below.

Executed per-interpreter command:

```text
python -X utf8 -m pytest tests/test_qt_metadata_boundaries.py -q --tb=short --junitxml=metadata.xml
```

## Verified integrated hosted checkpoint — 8b6c9d2

Draft [PR 7](https://github.com/SlinkyRamey/graphify/pull/7) source
`8b6c9d2bd4a89377829cb09c0737744aebccfb97` targets exact incoming upstream base
`35adf432b9d50f6f3d530ab5d7ec316819ef081c`. Both normal `pull_request` workflows
test actual synthetic checkout `0863b2b7e5c63a27b6d5185490b8b610cc997424`;
API parent identity and each job's retained checkout identity agree.
[CI 37289566337](https://github.com/SlinkyRamey/graphify/actions/runs/37289566337)
and [QML wheel 37289566340](https://github.com/SlinkyRamey/graphify/actions/runs/37289566340)
both conclude success on attempt one. All nineteen validation jobs pass.
The prior dbc4859 failures and cancelled profiles remain separate evidence.

| Profile | Passed | Explicit exclusions | Actual evidence boundary |
| --- | ---: | ---: | --- |
| Full Ubuntu / Python 3.10.22 | 9,356 | 120 | Source suite, JUnit, pytest exit zero, retained identity/integrity and cleanup |
| Full Ubuntu / Python 3.12.3 | 9,355 | 121 | Same source/retention boundary |
| Full Ubuntu / Python 3.13.16 | 9,355 | 121 | Same source/retention boundary |
| Full Ubuntu / Python 3.14.8 | 9,355 | 121 | Same source/retention boundary |
| Focused native Windows / Python 3.12.10 | 923 | 37 | Actual Cmd/PowerShell/Bash/sh consumers, JUnit, uploaded report and input/dependency identity |
| Four Windows QML lanes / Python 3.10/3.12/3.13/3.14 | 2,406 each | 19 each | Checkout source profiles and separate neutral isolated installed smokes |
| Four macOS QML lanes / Python 3.10/3.12/3.13/3.14 | 2,361 each | 64 each | Checkout source profiles and separate neutral isolated installed smokes |
| Four Ubuntu wheel lanes / Python 3.10/3.12/3.13/3.14 | 3 each | 0 | Reviewed-artifact contracts and separate neutral isolated installed smokes |

Every Linux lane individually passes all 128 applicable integration assignments:
34 joint upstream/Qt, 40 alias, sixteen real POSIX link/`..`, two platform guards,
35 metadata-boundary and the exact INC-CORE-10 subprocess case. Nine new
Windows-only native/short-leaf controls retain platform skips. The five actual
FalkorDB/wheel cases also pass. The native Windows artifact individually passes
all 34 joint, 43 alias, six native-admission and the same subprocess case.
Its 37 exclusions are the prior 21 plus sixteen POSIX-only controls. Full skip
inventories retain their actual reasons; version-specific `tomli`, exhausted
bundle-fallback and absent optional graspologic comparison controls are not
relabelled as passes. The native partition test still executes independently.

All five source/native archives have downloaded SHA-256 equal to the GitHub API
digest. Linux artifacts are 11336600508 (3.10), 11336267743 (3.12), 11336132399
(3.13) and 11335669170 (3.14). The native artifact 11336246160 digest is
`c280b9aa51311e5bf02874cc90f0eea7bbeb54e759c44e09c8290d8a5a7d36ef`.
Its actual uploaded preflight proves both admitted Git Bash/sh consumers use
the intended checkout Python and Node 24.19.0. Linux dependency inventories
contain 185/195/174/174 distributions respectively; Windows contains 197.
Each before/after inventory, tested checkout and tracked input identity is
unchanged. All twelve Linux integrity flags pass. Real service readiness,
test-graph deletion and absence of every job-owned container are confirmed;
all four end-to-end install steps pass.

Each full-source Linux wheel's 185 Python payloads equal reviewed source bytes
and actual synthetic-checkout Git blobs. Their SHA-256 digests, in lane order
3.10/3.12/3.13/3.14, are:

- `1be83a0da3a89eb8824dd8a76b7445cba5a172f2cf52b76c5701dacf1ca375ca`
- `cd6e12dd0d8131651300d06a9c3d0baad46bc788f78fdb258eda872799864291`
- `3803242269198f47e6565dd6a9fe0ae0baecf5db323de430c4dc0afdb07661a6`
- `02f3bf909e13aa4f4aff0fb402c9ecc6a8fc5d58038f61b8f37ab4302100485f`

All 24 optional/core installed smokes pass from neutral directories with isolated
interpreters. Windows/macOS platform tests import the checkout; their workflow
retains aggregate logs, without per-case JUnit, wheel-digest or byte-attestation
archives. Those limits are not filled by a source total or another job's wheel.
Linux JUnit evidence establishes individual corrected guard and metadata cases;
Linux/native JUnit establishes their applicable integration and subprocess cases.
Skill generation passes five validators and 134
artifact checks. Frozen local source typing still fails with 605 errors; new
integration/changed fixture modules have zero scoped diagnostics.

Advisory security still has successful job metadata but failed raw commands:
four high/eight medium/112 low Bandit findings and fifteen dependency rows across
three packages. All twelve printed medium/high owner functions match immutable
upstream 35adf43 AST exactly; the 112 aggregate low findings are not individually
classified. A clean security or typing contribution gate is not established.
Physical browser/device/application interaction, Qt runtime effects, released
upstream delivery and merging remain outside this hosted source profile.

That checkpoint's final plan review found no additional reproduced integration
defect; INC-QML-53 was then unallocated. The subsequent parser repair below uses
that increment; REQ-QML-022 remains unallocated. AST-only refresh after the source
corrections completes with 23,247 nodes/53,843 edges and the known malformed Luau
fixture warning. No graph commit stamp is inferred from that update command.
This evidence completion changes documentation only. The later documentation
head receives its own normal PR validation; this immutable checkpoint does not
claim its unknown future head already passed. AI commit attribution and the
original coverage artifact remain preserved; no upstream PR or merge is performed.

## Bounded parser repair — INC-QML-53

Status: **Policy-25 local source and isolated artifact/install profiles verified;
per-user installation verified; hosted proof and guarded application refresh pending**.
This profile extends the
bounded forms under existing criteria; twenty-one requirements/eighty-five
acceptance IDs remain unchanged. Historical policy-22 hosted acceptance remains
bound to its recorded revision and is not evidence for this repair. Current
corrected repair uses Qt policy 25, AST schema 13 and the existing semantic-cache and
transactional publication owners. Public synthetic fixtures contain no private
application source, project identity or machine path. The initial policy-23
assignments and executed checkpoints below are historical evidence for
`d13eebe7`; they do not verify the subsequent corrected head. Current correction
assignments and shell-environment disposition follow those checkpoints.

| Acceptance IDs / changed boundary | Exact automated assignment and observable result |
| --- | --- |
| REQ-QML-018-AC02; native compatibility parse view | `tests/test_qt_cpp_template_defaults.py::test_req_qml018_ac02_template_default_retains_callable_and_original_spans`: named nested/qualified/template pointer/reference parameters, declarations/definitions, multiple defaults, comments and unchanged nonempty defaults retain actual callable identity and original spans |
| REQ-QML-008-AC02; REQ-QML-010-AC01/AC02; canonical/native producer | `test_req_qml008_ac02_template_recovery_retains_native_member_and_cold_warm_identity` in that module: BOM/Unicode LF/CRLF original bytes, neighboring invokable native member, canonical target/type/role/span and cold/warm IDs remain correct |
| REQ-QML-001-AC04; REQ-QML-012-AC01/AC02; recovery rejection | `test_req_qml001_ac04_empty_defaults_do_not_reclassify_nonparameter_contexts`, `test_req_qml012_ac02_malformed_template_defaults_remain_unmodified_and_rejected`, `test_req_qml018_ac02_bare_callback_ambiguity_is_not_synthetic_declaration`, `test_req_qml001_ac04_unnamed_template_default_keeps_conservative_rejection` in that module: expressions, storage, macros, strings/comments, callback ambiguity and malformed/unnamed unsupported forms cannot gain declaration authority |
| REQ-QML-009-AC01; REQ-QML-010-AC01/AC02; literal module source additions | `tests/test_qt_cmake_mutations.py::test_REQ_QML_009_literal_private_sources_keep_module_and_original_byte_provenance`: actual source ownership, private C/C++ file kind, BOM/CRLF/Unicode byte span, JSON sanitation and comment-stable IDs |
| REQ-QML-009-AC01/AC04; tooling/native separation | `test_REQ_QML_009_source_properties_and_explicit_resources_preserve_alias_time_and_tooling_role`, `test_REQ_QML_009_explicit_header_only_property_never_creates_runtime_provider`, `test_REQ_QML_009_conditional_native_resource_properties_are_provably_irrelevant` in that module: header-only descriptors/scripts remain non-runtime facts; all six admitted literal Boolean spellings honor the actual flag; native RC/include paths cannot become QML/provider/resource membership |
| REQ-QML-009-AC03; explicit resource mapping | The source-property/resource test above verifies literal target-form aliases and exact corpus-relative targets. `tests/test_qt_cmake_alias_resolution.py::test_req_qml009_ac03_cmake_source_alias_replaces_only_its_resource_url` covers actual producer/index lookup, explicit target-path option, nested Unicode aliases, relative runtime URL lookup and absence of the replaced physical URL; `test_req_qml009_ac03_invalid_source_alias_cannot_restore_physical_fallback` protects transported malformed overrides |
| REQ-QML-009-AC04; REQ-QML-012-AC01/AC04; closed metadata guard | `test_REQ_QML_009_unsupported_mutations_preserve_closed_coverage_guard`, `test_REQ_QML_009_ordering_duplicate_targets_and_late_properties_are_rejected` in `test_qt_cmake_mutations.py`: public/interface/computed/conditional/bare-QML/unknown-target additions, malformed/repeated properties, unsupported options, escaping resources, duplicate/not-yet-declared targets and late mutations retain explicit incomplete error reasons |
| REQ-QML-009-AC01/AC03; REQ-QML-010-AC01; production joins | `tests/test_qt_cmake_mutation_updates.py::test_REQ_QML_009_private_source_and_resource_additions_reach_real_producer_and_warm_cache`: a private native header exposes the actual QML type/property and resource membership resolves to the accepted component through normal collection/build/reload; repeated/warm output equals a clean rebuild |
| REQ-QML-011-AC01/AC02/AC04; metadata-only lifecycle | `test_REQ_QML_011_metadata_only_retarget_and_source_removal_replace_stale_joins` in that module: changing CMake alone retargets the resource endpoint, removes the deleted native provider binding from unchanged consumers and equals a full accepted-corpus rebuild |
| REQ-QML-012-AC02; publication retention | `test_REQ_QML_011_rejected_addition_preserves_prior_published_graph_manifest_and_report` in that module: a later dynamic addition rejects a forced update while preserving the actual graph/manifest and an existing separately owned report byte for byte |
| REQ-QML-011-AC03/AC04; policy invalidation | `tests/test_qt_analysis_state.py::test_req_qml018_ac02_literal_parser_upgrade_retires_policy22_and_repeats`: prior policy-22 acceptance changes once without package/source changes, current policy commits, unchanged repeat is stable. Complete integration execution is pending at this evidence checkpoint |

### Regression evidence and commands

The final native focused command is
`.venv/Scripts/python.exe -m pytest tests/test_qt_cpp_template_defaults.py tests/test_qt_cpp_adoption_syntax.py tests/test_qt_cpp_syntax.py tests/test_qt_cpp_exposure.py -q --cov=graphify.extractors.qt_cpp_compat --cov-report=term-missing --cov-report=json:test-results/cpp-defaults-final-coverage.json`,
with a separate `COVERAGE_FILE`: **107 passed**, one pre-existing Hypothesis
collection warning, 10.86 seconds. The new module contributes 44 cases. Disabling
only the new helper in an isolated in-memory before-fix run gives **14 failed /
30 passed**: twelve formerly lost/rejected declarations and two neighboring
native-member LF/CRLF cases fail. `qt_cpp_compat` focused line coverage is
144/152 (94.74%); four new defensive invalid-AST/unsupported-ancestry return paths
and four legacy lines remain uncovered by this valid-corpus suite. Their presence
is recorded, not hidden behind the aggregate. Ruff reports no scoped errors.

`.venv/Scripts/python.exe -X utf8 -m pytest tests/test_qt_cmake_mutations.py tests/test_qt_project_metadata.py tests/test_qt_metadata_boundaries.py -q`,
with isolated `COVERAGE_FILE`, reports **100 passed**, one pre-existing Hypothesis
warning, 1.81 seconds. The former unsupported-case tuple containing a valid
literal `target_sources` header is deliberately replaced by a computed-header
rejection; the new positive test proves ownership/provenance rather than merely
removing its diagnostic. An isolated subprocess loads the original HEAD parser:
that exact positive regression fails, and the exact real-producer regression
rejects publication with `QML_GRAPH_PRESERVED` before the repair.

`.venv/Scripts/python.exe -X utf8 -m pytest tests/test_qt_cmake_mutation_updates.py tests/test_qt_metadata_incremental.py tests/test_qt_project_membership.py tests/test_qt_resource_resolution.py -q`
reports **63 passed**, 13.10 seconds. Warnings are the existing Hypothesis
collection notice and per-root stat-index fast-path notices from exercising
multiple isolated fixtures in one process. Ruff passes the touched CMake helpers
and focused tests. These targeted results are separate runs, not a full-suite or
installed-package claim. The complete suite and alias/policy integration results
are assigned by the integration owner after source freeze.

### Diagnostic, risk and remaining-boundary review

| Outcome/risk | Required contract / evidence boundary |
| --- | --- |
| Supported extraction | Existing ordinary extraction/rebuild success; no new notification code or claim of runtime Qt availability |
| Validation/rejection | Existing `QT_CPP_SYNTAX`, `QML_CMAKE_SYNTAX`, `QML_PROJECT_UNSUPPORTED`; all new unsupported metadata paths retain bounded source-owned reasons and never silently drop the command |
| Recoverable input/read failure | Existing root/read/access codes and retry guidance remain unchanged; this increment introduces no additional read or write boundary |
| Integrity/publication failure | Existing `QML_GRAPH_PRESERVED` and product transaction; the forced dynamic-update regression preserves accepted graph/manifest/report bytes |
| Identity/ambiguity | Named declaration ownership and unique preceding module required; malformed aliases cannot restore a fabricated physical URL; existing duplicate provider/resource ambiguity remains authoritative |
| Work bounds/security | Existing metadata byte/token/fact/scope limits and native syntax bounds remain; no CMake/Qt/QML execution, network request or corpus expansion occurs |
| Cache/configuration | Policy 23 requires same-package/source refresh; schema 13 and semantic ownership unchanged; aggregate current-state test execution is pending |
| Remaining gaps | Full local source suite, frozen artifact contents/install, native installed behavior and guarded application-corpus refresh are pending here. Hosted matrix, runtime Qt/UI, system/device and upstream publication are separate evidence profiles |

The accepted subset requires source properties before their metadata use and
flat private C/C++ additions after a unique local module declaration. Explicit
nonnative tooling never supplies runtime membership. The initial policy-23
expectation excluding native HEADER_FILE_ONLY inputs is corrected below; the
current native contract retains their membership. Bare QML target additions,
unnamed template defaults, ambiguous bare user-type callback declarations,
arbitrary expansion, relevant conditions, late properties, generated runtime
inputs, inferred resource prefixes, BASE/options and output-variable resource
forms remain unsupported. The RC-only exemption must retain its explicit proof
that those inputs cannot affect the analyzed membership/resource contracts.

### Integrated local repair checkpoint

After source review, the combined command
`.venv/Scripts/python.exe -X utf8 -m pytest tests/test_qt_cmake_mutations.py tests/test_qt_cmake_mutation_updates.py tests/test_qt_cmake_alias_resolution.py tests/test_qt_cmake_tooling_order.py tests/test_qt_cpp_template_defaults.py tests/test_qt_analysis_state.py -q --tb=short`
passes **125 cases**, zero failures, in 7.35 seconds. Three warnings retain the
existing Hypothesis collection and cross-root stat-index notices. The actual
old index fails five of seven alias tests; the two unchanged physical-path
controls still pass. Policy-22 retirement and repeat stability execute here.

Independent review exposed a mixed tooling/runtime ordering defect: marking one
source header-only accidentally changed the source kind of following siblings.
`tests/test_qt_cmake_tooling_order.py` exercises real extraction/build/export/reload
and native bindings for first/middle/last tooling placement and true/false flags.
Two of six cases fail before the per-token-kind correction; all six pass after.
The correction retains each sibling's own kind and provider membership.

Full-repository Ruff and all 134 generated skill artifacts pass. Pyright with
the explicit source virtual-environment interpreter reports the documented
605-error full-repository baseline and no diagnostics in the changed production
or focused test modules at this checkpoint. The full local pytest run is still
in progress; artifact/install and guarded application adoption remain pending.

### Frozen wheel and local adoption checkpoint

The repair is committed as `d13eebe7cb1b57fea7199ce4f7c33abcc380a509`, production
tree `77977178ec05cedbaa93c62404f3b4dd6408b5ff`. A raw Git-blob packaging snapshot
avoids Windows checkout/archive newline conversion. Every one of the 322 shipped
package files matches its committed blob; the sole unshipped developer-only
`extractors/MIGRATION.md` follows the existing package-data exclusion. Existing
31 extras and 105 dependency declarations remain unchanged. The reviewed wheel
SHA256 is `e3c8679a79c7374f2e22f4ca19afbbf400ea6facf97fcb56ca70f146ecb76116`.

An isolated offline installation with the 66-distribution locked runtime profile
and five separate pytest tools passes **106 tests**, zero failures/errors/skips,
15.90 seconds. It verifies installed payload hashes, policy 23/schema 13, real
parser/producer/update/retention regressions and the optional parser-absence
artifact controls. The approved local tool replacement passes independent
payload/dependency/Python verification and reads the two formerly rejected native
and metadata inputs without diagnostics or source changes. The historical team
bootstrap still identifies its earlier wheel; no new team registry release is
claimed. Windows wheel RFC metadata uses CRLF, so this local verification parses
its package identity and compares the original installed bytes rather than using
the older team's LF-specific metadata identity probe.

The repository's own AST-only `graphify update . --no-cluster` succeeds with
23,337 nodes/54,141 edges. The known malformed Luau fixture warning remains.
Focused CMake coverage runs 81 cases: both new helper modules reach 100% line
coverage; uncovered parent/index/policy lines belong to broader adjacent paths
outside that selection. Full-source pytest and the guarded application refresh
remain separate pending evidence at this checkpoint. One root coverage invocation
overwrote the pre-existing untracked generated `.coverage` report; no retained
copy was found, and later coverage output is isolated. This loss does not supply
or invalidate any claimed earlier aggregate coverage evidence.

AI attribution: Codex produced the repair. Its initial local source commit omitted
the required co-author trailer. That omission remains disclosed without rewriting
history; subsequent implementation/evidence commits must include the required
trailer and verify their completed commit messages. Remote validation/publication
remains unperformed at this checkpoint.

### Completed source run and shell-environment disposition — 2026-10-18

The initial complete source command
`.venv/Scripts/python.exe -X utf8 -m pytest tests/ -q --tb=short --junitxml=.venv/parser-repair/full-tests.xml`
completed with **9,411 passed, 45 failed, 122 skipped**. Output was redirected to
the matching `.log`; `COVERAGE_FILE` pointed to a separate `full.coverage` path as
a precaution, without requesting coverage. Its retained JUnit contains
9,578 cases and zero JUnit errors. Failures are confined to
`tests/test_hooks.py` (13), `tests/test_shell_portability_helpers.py` (6), and
`tests/test_skillgen_input_path_injection.py` (26). Forty failures select an
unusable WindowsApps Bash alias; five cannot find `sh`. These are shell admission
failures, not Qt/CMake parser assertions.

The eight relevant test/helper/hook/skill files are byte-identical between
`82a4f296` and `d13eebe7`; running the unchanged base shell helper reproduces both
environment failures. Prepending the existing Git Bash directories only for the
verification process resolves the boundary without source, assertion, machine
PATH, dependency, installed-runtime, or Git changes. The command
`.venv/Scripts/python.exe -m pytest tests/test_hooks.py tests/test_shell_portability_helpers.py tests/test_skillgen_input_path_injection.py -q --tb=short --junitxml=.venv/parser-repair/handoff-shell-tests.xml`,
with output redirected to the matching `.log`,
then reports **164 passed, eight platform skips, zero failures/errors**. Every
one of the original 45 failed test identities individually passes. Two skips
require POSIX symlink setup, one requires POSIX execution of a script named
`python.exe`, and five require the supported POSIX emitted-hook profile. Skips do
not establish those platform acceptances. The isolated coverage digest remains
unchanged.

This three-module rerun diagnoses the original failed cases; it is not a fresh
complete-suite result or evidence for the later policy-24 correction. Local
receipts retain exact commands, identities and outcomes under
`.venv/parser-repair/handoff-shell-{baseline,environment,result}.json` and
`handoff-shell-tests.{xml,log}`. These machine-specific receipts remain outside
version control. The documented **605-error full-repository Pyright baseline**
also remains; it is not a passing type gate. Current corrected-source checks,
fresh artifact/install proof, hosted validation and the separately owned guarded
application refresh remain pending.

### Policy-24 review correction assignments

The corrected header contract supersedes the policy-23 expectation recorded
above: `HEADER_FILE_ONLY` controls ordinary object compilation, while CMake's
AUTOMOC scan includes target headers. Native source membership and the original
property fact therefore remain available; only explicitly admitted nonnative
tooling lacks native/module authority. The
[design references](../docs/qt-qml/DESIGN.md#bounded-c-and-cmake-admission--inc-qml-53)
also explain scope selectors and discarded resource contents. These source changes
introduce no new persistence owner or runtime execution.

| Acceptance IDs / boundary | Exact assignment and evidence status |
| --- | --- |
| REQ-QML-009-AC03/AC04; REQ-QML-012-AC01 | `tests/test_qt_cmake_review_boundaries.py::test_req_qml009_ac04_source_property_scope_cannot_mutate_local_metadata`: DIRECTORY/TARGET_DIRECTORY, quoted/unquoted values and native-RC exemption attempts reject before local alias/property mutation. `test_req_qml009_ac03_discard_file_contents_never_becomes_source_evidence` rejects the resource option in every argument position; `test_req_qml009_ac03_reserved_looking_literal_paths_require_distinct_path_spelling` distinguishes reserved values from separately validated literal paths. Pass in the 164-case frozen-source selection; zero skips. |
| REQ-QML-009-AC03; REQ-QML-010-AC02/AC04; REQ-QML-020-AC02 | `tests/test_qt_cmake_resource_collisions.py::test_req_qml009_ac03_cross_representation_resource_collision_never_selects_a_winner`, `test_req_qml009_ac03_unestablished_explicit_provider_cannot_fall_back_to_module`, `test_req_qml009_ac03_missing_module_provider_cannot_borrow_explicit_target`, `test_req_qml009_ac03_duplicate_module_declarations_do_not_coalesce_same_target`: CMake/QRC and generated module providers retain ambiguity, unsupported/missing evidence and order independence, including distinct declarations for one physical target. `test_req_qml010_ac02_identical_declaration_copies_are_not_distinct_providers` protects exact-ID repeats for explicit and module providers. Pass in the 164-case frozen-source selection; zero skips. |
| REQ-QML-010-AC02/AC04; shared-language regression | `tests/test_qt_cmake_resource_collisions.py::test_req_qml010_ac02_conflicting_copies_of_one_declaration_identity_are_rejected` rejects conflicting Qt metadata in either order. `test_req_qml010_ac02_shared_csharp_namespace_is_not_a_conflicting_qt_declaration` uses real C# extraction and a mixed scan to retain generic shared namespace IDs/provenance in both orders. These cases pass in the frozen-source selection; the C# regression fails twice before its Qt-only scope correction and passes twice after. |
| REQ-QML-009-AC01/AC04; REQ-QML-020-AC01/AC02 | `tests/test_qt_cmake_header_membership.py::test_req_qml020_ac01_header_only_native_member_keeps_module_and_qml_binding` retains native source/property facts and real QML binding for all six literal Boolean spellings through module and target-source declarations. `test_req_qml009_ac01_non_native_header_only_tooling_cannot_provide_module_membership` retains the separate nonnative tooling boundary. Pass in the 164-case frozen-source selection; zero skips. |
| REQ-QML-010-AC03/AC04; REQ-QML-020-AC01/AC02 | `tests/test_qt_cmake_resource_collisions.py::test_req_qml010_ac03_published_membership_retains_cross_provider_ambiguity` exercises producer/build/JSON reload and ensures the membership consumer cannot bypass combined resource uncertainty or publish a selected target edge. Existing `tests/test_qt_project_membership.py::test_req_qml020_ac01_unused_component_has_persisted_build_and_resource_membership` and `test_req_qml020_ac02_resources_reuse_existing_alias_guard_decisions` retain the accepted projection and rejection controls. The correction passes the frozen-source selection; the broader compatibility checkpoint has seven separately recorded alias-profile skips. |
| REQ-QML-008-AC04; native syntax regression | `tests/test_qt_cpp_syntax.py::test_comments_strings_raw_literals_and_preprocessor_definitions_are_inert`, `test_unicode_crlf_macro_spans_are_original_bytes`; `tests/test_qt_cpp_template_defaults.py::test_req_qml001_ac04_empty_defaults_do_not_reclassify_nonparameter_contexts` and `test_req_qml008_ac02_template_recovery_retains_native_member_and_cold_warm_identity` protect inert syntax, original spans, accepted native roles and cold/warm identity. The original 107-case native selection passed for d13eebe7 and its native recovery owner remains unchanged. Current inert-syntax/span cases pass in the 498-case adjacent selection. |
| REQ-QML-018-AC06; unchanged persistence boundaries | `tests/test_qt_product_publication.py::test_inc25_preparation_and_late_replace_faults_preserve_then_retry`, `test_inc25_successful_ast_cache_does_not_authorize_failed_products`; `tests/test_qt_readonly_publication.py::test_req_qml018_ac06_readonly_graph_preserves_products_then_retries` retain actual replacement/read-only failure, cache/analysis-state ownership and retry protection. No new writer is introduced. All these current Windows cases pass in the 498-case adjacent selection, including real read-only rejection and retry; zero skips. |
| REQ-QML-011-AC01/AC02/AC04; REQ-QML-012-AC01/AC02; REQ-QML-018-AC06 | `tests/test_qt_cmake_review_updates.py::test_req_qml012_ac02_review_rejection_preserves_products_and_recovery_repeats`: each scope-selector/discard mutation, with and without force, preserves graph/manifest/report/Qt analysis-state bytes, then corrected retry and repeat match the accepted clean rebuild. Pass in the 164-case frozen-source selection; zero skips. |
| REQ-QML-009-AC03; REQ-QML-011-AC01/AC02/AC04; REQ-QML-020-AC02 | `tests/test_qt_cmake_review_updates.py::test_req_qml011_ac02_metadata_collision_update_removes_stale_edge_and_recovers`: metadata-only alias change removes the formerly resolved resource edge, persists ambiguity, matches a clean rebuild and unchanged repeat, then restores the original mapping after repair. Pass in the 164-case frozen-source selection; zero skips. |
| REQ-QML-010-AC01; REQ-QML-011-AC03/AC04; REQ-QML-018-AC02 | `tests/test_qt_analysis_state.py::test_req_qml018_ac02_literal_parser_upgrade_retires_prior_policy_and_repeats` covers both prior policies 22 and 23, requires policy 24, preserves input bytes, refreshes once and retains the accepted checkpoint on unchanged repeat. Pass in the 164-case frozen-source selection; zero skips. |

These assignments describe production boundaries rather than aggregate test
counts. Their focused source and frozen installed results appear below; complete
corrected-source execution and exact-head hosted validation remain open. The private
application graph refresh and any team artifact release are independently owned;
neither is inferred from a local parser smoke test or the historical wheel.

### Frozen policy-24 source checkpoint — 2026-10-18

The final source-focused command passes **164 cases, zero failures/errors/skips**,
with 14 existing warnings in 43.79 seconds. The four new review modules contribute
62 cases. Scope/property/resource/native-header, exact-ID Qt provider integrity,
real mixed C# namespace compatibility, policy-22/23 retirement, persisted
uncertainty, forced/non-forced rejection, repair and unchanged repeat all execute
through the production boundaries assigned above. The command uses an isolated
coverage destination and does not replace installed Graphify:

```powershell
$env:COVERAGE_FILE = Join-Path (Get-Location) '.venv/parser-repair/review-frozen.coverage'
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --tb=short --junitxml=.venv/parser-repair/review-frozen.xml --cov=graphify.extractors.qml_cmake --cov=graphify.extractors.qml_cmake_properties --cov=graphify.extractors.qml_cmake_resources --cov=graphify.qt_project_index --cov=graphify.qt_project_membership --cov-report=term-missing --cov-report=json:.venv/parser-repair/review-frozen-coverage.json tests/test_qt_cmake_review_boundaries.py tests/test_qt_cmake_resource_collisions.py tests/test_qt_cmake_header_membership.py tests/test_qt_cmake_review_updates.py tests/test_qt_cmake_mutations.py tests/test_qt_cmake_mutation_updates.py tests/test_qt_cmake_alias_resolution.py tests/test_qt_cmake_tooling_order.py tests/test_qt_resource_resolution.py tests/test_qt_analysis_state.py > .venv/parser-repair/review-frozen.log 2>&1
```

The negative control loads six exact `d13eebe7` owner blobs into a separate
interpreter without editing the checkout or installed runtime. The same current
62 new cases produce **42 failures and 20 passing controls**; emitted owner hashes
bind the comparison to the original repair. Selector-before-use retention and
collision/stale-edge cases fail before correction. Some discard-retention controls
already reject through the older late-property guard and are retained as passing
controls, not presented as new before-fix failures. This establishes the observed
defects rather than claiming every new assertion fails on the old source. The
separate C# namespace regression fails in both input orders under the overly broad
intermediate identity validation and passes after Qt-only validation is applied.
The final negative-control log/JUnit are
`.venv/parser-repair/review-original-final.log` and `review-original-owners.xml`.

The broader compatibility command passes **293 cases with seven Windows symlink
setup skips**, zero failures/errors, in 126.20 seconds. Every skip belongs to
`test_qt_project_membership_aliases`; those unavailable alias profiles remain
unverified locally. This checkpoint precedes the final narrowing of declaration
validation to Qt providers and its four additional cases. The subsequent frozen
selection covers that changed boundary; the broader run is not represented as a
repeat against the final source:

```powershell
$env:COVERAGE_FILE = Join-Path (Get-Location) '.venv/parser-repair/review-scoped.coverage'
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --tb=short --junitxml=.venv/parser-repair/review-scoped.xml --cov=graphify.extractors.qml_cmake --cov=graphify.extractors.qml_cmake_properties --cov=graphify.extractors.qml_cmake_resources --cov=graphify.qt_project_index --cov=graphify.qt_project_membership --cov-report=term-missing --cov-report=json:.venv/parser-repair/review-scoped-coverage.json tests/test_qt_cmake_review_boundaries.py tests/test_qt_cmake_resource_collisions.py tests/test_qt_cmake_header_membership.py tests/test_qt_cmake_review_updates.py tests/test_qt_resource_resolution.py tests/test_qt_project_metadata.py tests/test_qt_project_membership.py tests/test_qt_project_membership_updates.py tests/test_qt_project_membership_aliases.py tests/test_qt_project_admission.py tests/test_qt_metadata_admission.py tests/test_qt_metadata_incremental.py tests/test_qt_metadata_boundaries.py tests/test_qt_native_project_integration.py tests/test_qt_config_incremental.py tests/test_qt_incremental_policy.py tests/test_qt_analysis_state.py tests/test_qt_qml_projection.py > .venv/parser-repair/review-scoped.log 2>&1
```

The final adjacent acceptance/unrelated-language command passes **498 cases with
zero failures/errors/skips**, 88 existing warnings, in 61.59 seconds. It executes
native inert syntax/original spans, actual product replacement/cache/read-only
failure and retry, and the supported generic language regressions. Git Bash is
admitted only through the verification process's PATH, with a separate coverage
destination:

```powershell
.venv/Scripts/python.exe -X utf8 -m pytest tests/test_qt_cpp_syntax.py tests/test_qt_product_publication.py tests/test_qt_readonly_publication.py tests/test_languages.py -q --tb=short --junitxml=.venv/parser-repair/release/adjacent-tests.xml
```

Full-repository Ruff passes and all **134 generated skill artifacts** match.
Explicit-virtual-environment Pyright retains **605 errors, zero warnings** in the
full repository; no changed-module diagnostics are reported. This is a disclosed
baseline, not a passing full type check. Frozen focused line coverage is 100% in
both new property/resource helpers and 98% in the project index; its three missing
lines are pre-existing branches. Parent/index/membership coverage remains bounded
to the selected cases and does not establish runtime Qt or application coverage.
Local lint/type/artifact logs remain in the ignored repair evidence directory.

These overlapping selections are not added together or substituted for a new
complete-source run. Current source-local acceptance applies only to the assigned
executed profiles; the initial complete-source result and its shell repair remain
separate. The current production policy is 24/schema 13, but the installed runtime
and historical wheel still identify `d13eebe7`/policy 23. A new committed raw-blob
wheel, isolated installation, exact-head hosted checks and separately owned
application refresh remained pending at this pre-packaging checkpoint; the
completed local package proof follows below. The initial missing Codex trailer is retained
as a disclosed history gap; the corrective commit must carry and verify its own
`Co-authored-by: Codex <noreply@openai.com>` trailer.

### Committed local package checkpoint — 7e29b34a

Source commit `7e29b34a16570a3cc0739abbbb82782da6a71c7e`, production tree
`b563d8d2ef01f4dd309ed200d1aed4788f3c5fcb`, carries the required Codex co-author
trailer. The initial `d13eebe7` attribution omission remains disclosed without
rewriting history.

The final eighteen-module compatibility rerun against this source reports
**297 passed, seven Windows alias-profile skips, zero failures/errors**, 93
existing warnings, in 57.30 seconds. It repeats the eighteen module paths listed
in the preceding compatibility command with `-X utf8 -m pytest`, followed by
`-q --tb=short --junitxml=.venv/parser-repair/release/compatibility-tests.xml`.
Output is redirected to the matching `.log`; `COVERAGE_FILE` is isolated at
`.venv/parser-repair/release/compatibility.coverage`. This closes the earlier
pre-narrowing source checkpoint. All seven skips remain the unavailable Windows
symlink setup in `test_qt_project_membership_aliases`, not passing alias acceptance.

The fresh wheel is built from raw committed Git blobs, with all **322 shipped
package files byte-identical** to the reviewed source. The existing developer-only
`extractors/MIGRATION.md` exclusion, 31 extras and 105 dependency declarations
remain unchanged. Its SHA256 is
`90c6053353f3c26d23d8afecddc585ec2ed6fd7194b8d1e1f80865f39961a4ac`.
The isolated offline installation passes **191 tests, zero failures/errors/skips**,
13 existing warnings, in 25.72 seconds. Its receipt verifies policy 24/schema 13,
all installed payload bytes, 66 locked runtime distributions, five separate test
tools, and the exact collected case identities. Native recovery, corrected CMake/
resource/header behavior, real mixed C# namespace compatibility, update/retention,
policy invalidation and optional-parser absence execute from the installed wheel.
The installed stage and receipt are owned by
`.venv/parser-repair/release/stage_smoke.py` and `stage-receipt.json`; the artifact
identity is retained in `artifact.json`. These machine-specific receipts stay
outside version control. The global tool is unchanged and still identifies the
earlier policy-23 installation; this isolated proof is not a team artifact release.

`.venv/Scripts/python.exe -X utf8 -m graphify update . --no-cluster` completes with
exit zero and persists **23,390 nodes / 54,327 edges**. Its retained log reports the
known malformed Luau fixture, 25 files without modeled symbols and eighteen
unclassified inputs. This is AST-only analysis with no model API or clustering.
The pre-existing root coverage digest is retained; later checks use separate
coverage destinations.

Ruff and all 134 generated artifacts pass. Full Pyright retains its disclosed
605-error baseline, with no diagnostics in the ten explicitly checked changed
modules. None of these overlapping runs is a fresh complete-source success or
hosted validation. Required PR/exact merged-SHA checks, the separately owned
application graph refresh and any team registry release remain pending.

### Native-RC prerequisite refinement — policy 25

The new RC-only OBJECT_DEPENDS exemption is part of INC-QML-53, under the existing
acceptance identities and the preimplementation matrix in
[the plan](../docs/qt-qml/PLAN.md#rc-compilation-prerequisite-correction--preimplementation-matrix).
The `7e29b34a`/policy-24 source and installed checkpoint above remains historical
for this changed boundary. Current policy-25 source and isolated-wheel cases pass;
hosted and application verification remain pending.

| Acceptance IDs | Required production evidence / status |
| --- | --- |
| REQ-QML-009-AC01/AC04; REQ-QML-010-AC02/AC04 | `tests/test_qt_cmake_rc_dependencies.py::test_req_qml009_ac04_rc_compile_properties_remain_opaque_with_original_spans`: literal RC lists, INCLUDE_DIRECTORIES/OBJECT_DEPENDS individually, both orders and repeated allowed names; scoped commands, opaque computed values, BOM/CRLF/Unicode and original neighboring declaration spans. No RC property/runtime provider/resource fact is created. Pass in the frozen 277-case local source selection; zero skips. |
| REQ-QML-009-AC04; REQ-QML-012-AC01/AC04; REQ-QML-020-AC02 | `test_req_qml012_ac01_rc_exemption_rejects_unproven_source_scope_or_property` in that module protects selector-first rejection, dynamic/list source paths, mixed non-RC/runtime/unknown properties and malformed pairs. `test_req_qml009_ac04_rc_dependencies_and_authoring_targets_never_expand_accepted_corpus` guards real outside-file reads while retaining the in-corpus native HEADER_FILE_ONLY provider and explicit unavailable outside membership. Pass in the frozen 277-case local source selection; zero skips. |
| REQ-QML-011-AC01/AC02/AC04; REQ-QML-012-AC02; REQ-QML-018-AC06 | `tests/test_qt_cmake_rc_updates.py::test_req_qml011_ac02_rc_dependency_only_changes_match_full_and_repeat` and `test_req_qml012_ac02_rc_rejection_preserves_products_and_recovers`: property/prerequisite-only parity, stable analysis state, forced/non-forced repeated rejection retaining graph/manifest/report/policy bytes, repair and clean/repeated rebuild. Pass in the frozen 277-case local source selection; zero skips. |
| REQ-QML-011-AC03/AC04; REQ-QML-018-AC02/AC06 | `tests/test_qt_analysis_state.py::test_req_qml018_ac02_literal_parser_upgrade_retires_prior_policy_and_repeats` covers earlier policy checkpoints. `tests/test_qt_cmake_rc_updates.py::test_req_qml011_ac04_prior_policy_refresh_rejection_retains_products_then_commits25` proves actual policy-23/24 accepted products survive rejected forced refresh, then repaired retry/repeat commits policy 25 and matches a clean rebuild. Schema 13 remains unchanged. Local source and frozen-wheel/install execution pass; hosted outcomes remain separately pending. |

Public fixtures must contain only synthetic project data. This refinement neither
reads external prerequisite/source contents nor changes corpus admission, native
membership, persistence ownership or the requirement/increment numbering scheme.

The final before/after comparison uses the exact policy-24 owners and current
accepted regression assertions. Provisional reload results and the earlier
overstrict fixture expectation are excluded from release evidence; only the
final verified receipts below establish the reported negative control.

The first authoring-boundary fixture overreached by requiring every graph node to
have a source file. The established generic extractor legitimately emits a
sourceless external QObject reference for inheritance. The corrected expectation
keeps exact accepted-root ownership for source-backed nodes, explicit outside-read
guards and unavailable outside membership. It additionally checks that the sole
generic sentinel keeps its inheritance role without Qt/QML metadata, index
membership or native binding authority. This corrects the fixture under the
existing source-backed provenance contract; no production behavior changes for
that assertion correction.

The frozen policy-25 source command passes **277 cases, zero failures/errors/
skips**, 17 existing warnings, in 55.08 seconds. The two new RC modules contribute
150 cases and execute every assignment above, including actual prior-policy
rejection/repair retention. Its isolated coverage destination preserves unrelated
coverage evidence:

```powershell
$env:COVERAGE_FILE = Join-Path (Get-Location) '.venv/parser-repair/rc-followup/final.coverage'
.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider --tb=short --junitxml=.venv/parser-repair/rc-followup/final.xml --cov=graphify.extractors.qml_cmake_properties --cov=graphify.qt_incremental --cov-report=term-missing --cov-report=json:.venv/parser-repair/rc-followup/final-coverage.json tests/test_qt_cmake_rc_dependencies.py tests/test_qt_cmake_rc_updates.py tests/test_qt_analysis_state.py tests/test_qt_cmake_mutations.py tests/test_qt_cmake_review_boundaries.py tests/test_qt_cmake_header_membership.py tests/test_qt_incremental_policy.py > .venv/parser-repair/rc-followup/final.log 2>&1
```

The final negative control executes exact `cffb2a73` Git blobs for the CMake
dispatcher, source-property owner and policy owner inside the real module globals,
preserving eager facade bindings. It first verifies policy 24 and rejection of the
minimal OBJECT_DEPENDS fixture, then executes the current 150 new cases. Result:
**96 failed, 54 passing controls**, zero JUnit errors, 15 existing warnings, in
6.46 seconds. No source checkout or installed-runtime bytes are replaced. Earlier
swapped-module reload output is invalid evidence because eager consumers retained
different owners; it is excluded from these counts.

```powershell
$env:COVERAGE_FILE = Join-Path (Get-Location) '.venv/parser-repair/rc-followup/negative-final-exact.coverage'
.venv/Scripts/python.exe .venv/parser-repair/rc-followup/negative.py > .venv/parser-repair/rc-followup/negative-final-exact.log 2>&1
```

The exact negative-control JUnit is `negative-final-exact.xml` in that same
directory; printed owner hashes bind its source identity. An independent review
selection covering both RC modules, native-header membership and the exact policy
retirement test also passes 167 cases with no skips. These selections overlap and
are not added into a total.

The adjacent native/persistence/unrelated-language command passes **498 cases,
zero failures/errors/skips**, 88 existing warnings, in 50.62 seconds, with
an isolated coverage destination:

```powershell
$env:COVERAGE_FILE = Join-Path (Get-Location) '.venv/parser-repair/rc-release/adjacent.coverage'
.venv/Scripts/python.exe -X utf8 -m pytest tests/test_qt_cpp_syntax.py tests/test_qt_product_publication.py tests/test_qt_readonly_publication.py tests/test_languages.py -q --tb=short --junitxml=.venv/parser-repair/rc-release/adjacent-tests.xml
```

Full Ruff and all 134 generated skill artifacts pass. Full explicit-interpreter
Pyright retains **605 errors, zero warnings**; the five changed modules separately
report zero errors/warnings. The source-property helper reaches 71/71 covered
lines; policy coverage misses only its unchanged legacy lines. The accepted
metadata parser smoke has zero diagnostics/failures and leaves its input bytes
unchanged; no application source, path or content hash is retained here.

These results verify the declared local policy-25 source cases. At this source
checkpoint the new raw-blob wheel/install, hosted/full-source validation,
application graph refresh and team adoption were pending; the committed local
package and broad Qt source proof follows below. Policy-24
wheel/install proof and the earlier complete-source result are historical and
cannot establish those remaining outcomes.

### Committed policy-25 local checkpoint — 84f5eef7

Source `84f5eef71c3ecd23bf9c29e2091f0399f47afad3`, production tree
`aa1aec0012d7ddea61b890fade07e11dbdbd9882`, retains the verified Codex co-author
trailer. The raw-Git-blob wheel's 322 shipped files match the committed source;
31 extras, 105 dependency declarations and the existing developer-document
exclusion remain unchanged. Wheel SHA256:
`94222d69bd2ad6d410b11fa32ac3428a652e324abc93b39050853e728bbf2950`.

The isolated offline installation passes **342 tests, zero failures/errors/skips**,
28 warnings, in 40.22 seconds. Policy 25/schema 13, exact payload bytes, collected
case identities, 66 locked runtime distributions and five separate test tools
are verified. The installed metadata probe has zero diagnostics/failures and
unchanged input bytes; no private input identity, path or content hash is retained
here. The global tool and application graph are unchanged. Artifact/stage receipts
remain under `.venv/parser-repair/rc-release/` outside version control.

The broad source command executes all **148 tracked root test modules** whose
names begin `test_qml_`, `test_qt_` or `test_upstream_qt_`, selected from the exact
committed Git tree. Result: **2,709 passed, zero failures/errors, 35 skips** across
2,744 cases, 1,464 warnings, in 798.60 seconds. The reviewed wheel is supplied
through `GRAPHIFY_QML_TEST_WHEEL`, with process-local Git Bash and an isolated
coverage destination:

```powershell
.venv/Scripts/python.exe -I .venv/parser-repair/rc-release/run_native_source.py
```

`native-source-receipt.json` and `native-source-tests.{xml,log}` retain the expanded
command, module/case identities and unchanged tested HEAD; tracked source/test/tool
inputs remain clean. Skips are two host-denied symlink cases, seventeen cases
requiring Windows symlink privileges/Developer Mode, and sixteen POSIX physical
link/parent-traversal cases. They do not establish those profile acceptances. This
is the QML/Qt/upstream-Qt selection, not a fresh complete all-language suite or a
hosted run. Its cases overlap the focused and installed selections and are not
added into a combined total.

AST-only `graphify update . --no-cluster` completes with exit zero and persists
**23,416 nodes / 54,424 edges**. The known malformed Luau fixture warning, 25 files
without modeled symbols and eighteen unclassified inputs remain explicit. No model
API or clustering runs. Full Ruff and all 134 generated artifacts pass; full
Pyright's 605 diagnostics exactly match the prior frozen baseline, with zero
added/removed diagnostics. The five changed modules separately have zero errors/
warnings. This remains a disclosed full-repository typing baseline.

Local source and isolated artifact/install proof is complete within the executed
profiles. Hosted checks, validation of the eventual merged SHA, application-graph
refresh and team artifact release remain pending; earlier hosted evidence
does not validate this new revision.

### Policy-25 per-user tool adoption

The per-user tool is installed offline from the reviewed policy-25 wheel identified
above. All 322 installed package files match source `84f5eef7` and the unchanged
production tree in published head `e46d2184`. The 66 runtime distributions and
`qml`, `watch`, `mcp`, `sql` extras remain unchanged; five test tools are loaded
separately rather than added to the installed runtime.

Executed local commands:

```powershell
$taskToolPython = Join-Path $env:APPDATA 'uv/tools/graphifyy/Scripts/python.exe'
& $taskToolPython -I -B .venv/parser-repair/rc-release/global_tool_smoke.py test
uv pip check --python $taskToolPython --offline
```

The verification helper and its `local-tool-adoption/` receipts remain beneath
the ignored `.venv/parser-repair/rc-release/` evidence directory.

The actual installed interpreter passes **342 regressions, zero failures/errors/
skips**, 28 warnings, in 57.95 seconds. Collected test identities exactly match the
isolated 342-case profile, and every imported Graphify module is verified beneath
the actual installed package location. Post-test payload/dependency identity is
unchanged, offline dependency checking reports all 66 packages compatible, and
the actual `graphify.exe --help` launcher exits zero. Root coverage evidence is
preserved. Machine-specific installation and version receipts remain private.

This completes per-user tool adoption; it does not change the earlier checkpoints
where the global tool remained untouched. No application source or metadata is
read and no application graph is regenerated in this adoption step. Team artifact
publication, application-graph refresh and hosted/merged-SHA proof remain pending.
PR #8 remains open without passing hosted checks while Actions is disabled; local
installation does not establish a merge or CI success.

## Upstream 0.9.92 integration — INC-QML-54

Status: **Corrected source67 complete local source and isolated installed profiles pass; final native gate passes 76 cases with four platform skips/all 29 critical cases passing; new hosted gates pending**.
The reviewed inputs are repair `dd8cc3d0` and upstream `86c57be8`, with merge base
`35adf432`. The [preimplementation matrix](../docs/qt-qml/PLAN.md#inc-qml-54--upstream-0992-integration)
assigns the existing acceptance identities before conflict resolution. Combined
AST schema 18, upstream grammar fingerprints/overrides and retained Qt policy 25
are implemented. The initial pre-final matrix below preserves its checkpoint
states; its pending local entries are superseded by the
[corrected source67 record](#committed-corrected-integration-checkpoint--67bb2022).
That complete local source run does not establish platform-wide or new hosted
acceptance.

| Acceptance assignment | Required evidence and checkpoint state |
| --- | --- |
| REQ-QML-001-AC01–AC04; REQ-QML-014-AC01/AC02; REQ-QML-018-AC02/AC05 | Fresh frozen dependency/parser profiles, optional-parser absence, offline installed extraction and exact packaged-resource identity; **not executed for the integrated inputs**. |
| REQ-QML-002-AC01–AC04; REQ-QML-003-AC01–AC04; REQ-QML-009-AC01–AC04; REQ-QML-016-AC01–AC04; REQ-QML-017-AC01–AC04 | Joint upstream/Qt discovery, identity, metadata and native/bridge regressions, including malformed/ambiguous/excluded input and unrelated languages; **exact tests and results pending source review**. |
| REQ-QML-003-AC02/AC04; REQ-QML-010-AC01/AC02; REQ-QML-011-AC03/AC04 | Combined contained child-alias `.mjs`/`.sql` stem collision retains distinct remapped file/declaration identities under the walked-source key. **The fourteen-case `tests/test_filename_cohorts.py` ordinary-root selection passes; the separate scan-root-junction correction remains pending**. |
| REQ-QML-003-AC02/AC04; REQ-QML-011-AC03/AC04; REQ-QML-012-AC01/AC02 | D31 bounded accepted collision-cohort expansion retains physical/walked owners, edit/remove/restore/full/repeat and actual retention without unrelated parsing. Recorded-deletion seeds provide lexical keys only. **Fourteen ordinary-root helper/lifecycle cases pass; final junction/composition correction and broader proof pending**. |
| REQ-QML-003-AC04; REQ-QML-011-AC03/AC04; REQ-QML-012-AC02 | Terraform/physical/filename selectors reach deterministic monotone closure in at most `len(admitted) + 1` passes before context. Recorded deletions and Terraform/filename fanout converge without deleted-path reads or unrelated parsing. **Fourteen ordinary-root cohort cases pass; final junction and `tests/test_upstream_qt_refresh_order.py` two-direction composition proof pending**. |
| REQ-QML-002-AC04; REQ-QML-003-AC04; REQ-QML-011-AC03/AC04; REQ-QML-012-AC01/AC02 | Real scan-root junction lifecycle must use discovery's established `watch_root` domain for accepted/retired inputs, preserving walked child aliases without per-source remapping or weaker admission. **Wrong invocation-root hook rejects removal; correction and real junction lifecycle proof pending**. |
| REQ-QML-002-AC01/AC04; REQ-QML-010-AC02/AC04; REQ-QML-011-AC03/AC04; REQ-QML-012-AC01; REQ-QML-018-AC02/AC07 | Valid supported override of a physical native Qt extension away from C++ produces no native syntax rejection or provider authority. Cold/warm facade and actual watch/full override-transition stale-fact removal/recovery match clean output; `.h` selected as C++ retains Qt support, while `.inc` remapped to C++ has generic-only authority. **Seven focused production cases pass in `tests/test_upstream_qt_language_overrides.py`; broader integration/package/hosted proof pending**. |
| REQ-QML-010-AC01–AC04; REQ-QML-013-AC01–AC04; REQ-QML-018-AC04 | Producer/build/consumer direction, provenance, distinct mechanisms and rejected transport retention; **integrated regression assignments pending**. |
| REQ-QML-010-AC02/AC04; REQ-QML-011-AC04; REQ-QML-012-AC02; REQ-QML-018-AC06 | Canonical minted/legacy-shape placeholders retain upstream tierless treatment, with validated presentation fields including finite numeric coordinates. Metadata even when empty, source locations, unknown fields, other origins and noncanonical values stay protected; prior-import cleanup retains its independent prior-ID proof. Exact-shape authored legacy records are indistinguishable and may receive automatic treatment under D30's stated convention. **Final 168-case source selection passes without skips; wider integration/artifact/hosted gates pending, with no provenance-certainty claim**. |
| REQ-QML-010-AC02/AC03; REQ-QML-012-AC01/AC02; REQ-QML-013-AC03; REQ-QML-018-AC06 | Shared loader retains complete markers/unmarked legacy inference while partial/corrupt explicit authority rejects before publication with prior products retained. **Four before-fix failures; corrected 257-case direction selection passes without skips. Broader source/package/hosted profiles pending**. |
| REQ-QML-010-AC01/AC03; REQ-QML-013-AC03; REQ-QML-018-AC06 | JSON output version fields must be added without mutating caller graph metadata/nodes/edges. **Four existing Qt JSON direction variants and one original-parallel-links case fail before correction** in the export selection; exact corrected outcomes pending. |
| REQ-QML-010-AC02/AC03/AC04; REQ-QML-012-AC01/AC02; REQ-QML-013-AC01/AC02/AC04 | Override owner/supertype/member edges retain direction validation; malformed transport adds no callers; MCP retains parallel relation/site evidence and matches CLI traversal. **Nine before-fix failures/one control; eleven cases pass in `tests/test_upstream_qt_query_direction.py` within the 32-case source selection; wider proof pending**. |
| REQ-QML-011-AC01–AC04; REQ-QML-012-AC01–AC04; REQ-QML-018-AC06 | Schema-13/17 retirement, grammar/override/native interaction, cold/warm/full/incremental parity, stale-edge removal, actual failure retention and repair/repeat. **The 140-case cache/alias selection passes with ten platform skips; fourteen ordinary-root cohort cases also pass, with final junction/composition and wider integrated proof pending**. |
| REQ-QML-011-AC04; REQ-QML-012-AC02/AC04; REQ-QML-018-AC06 | Pending-label consumption through bounded transactional deletion: absent/repeated cases, unsafe/undeclared/conflicting requests, actual unlink/later commit failure, whole-cohort restoration and retry/recovery. **Fourteen cases pass in `tests/test_upstream_qt_labels_publication.py` within the 32-case source selection; wider proof pending**. |
| REQ-QML-014-AC01–AC04; REQ-QML-015-AC01–AC04 | Source suites, lint/type differences, generated validators, package/install, upstream Pi guard and declared platform profiles; **commands, exact failures/skips and hosted receipts pending**. |
| REQ-CORE-001-AC05 | Encoded Windows hook cleanup requires exact outer options, bounded valid base64/UTF-16, exact wrapper/marker, accepting only trailing ASCII space/tab. Leading/other whitespace and foreign/malformed entries remain authored. **Fifty-five source cases pass across new identity, upstream cleanup and unchanged native execution regressions; installed/hosted proof pending**. |

Record the resulting source head, production tree, reviewed wheel/dependencies,
commands and per-profile results before replacing these pending assignments.
Selections may overlap and must not be summed into a full-suite claim. The
previous policy-25 per-user tool remains installed; this integration does not
establish local adoption, an application graph refresh or an authorized PR merge.
Hosted source/base/checkout identity and any eventual exact merged-SHA proof must
be read back separately; the earlier Actions-disabled state is historical until
the service configuration is checked again.

### Native-override regression checkpoint

Before the correction, the final public production module
`tests/test_upstream_qt_language_overrides.py` executes **five failures and two
passing controls**, with zero errors/skips. The same seven cases then pass after
the facade native-input filter, with four existing stat-index warnings:

- `test_req_qml002_ac01_explicit_non_cpp_override_skips_all_native_collectors` for `.h`, `.hpp` and `.cpp`;
- `test_req_qml002_ac01_explicit_cpp_header_keeps_native_enrichment`;
- `test_req_qml002_ac01_generic_cpp_override_does_not_invent_qt_provider_scope`;
- `test_req_qml002_ac01_mixed_override_preserves_supported_cpp_facts`;
- `test_req_qml011_ac04_override_transition_removes_native_facts_and_recovers`.

The physical `.h` selected as C++ and nonstandard `.inc` selected for generic C++
are the passing controls. The transition case exercises real watch/full
publication, stale-fact removal, repaired retry and cold/warm clean parity. These
results map to REQ-QML-002-AC01/011-AC04 and the override matrix above; they do not
establish a complete integrated profile.

Executed before/after commands:

```powershell
.venv/Scripts/python.exe -m pytest -q --disable-warnings -o addopts= tests/test_upstream_qt_language_overrides.py --junitxml=.venv/parser-repair/upstream-sync/qt-overrides-before-final.xml
.venv/Scripts/python.exe -m pytest -q --disable-warnings -o addopts= tests/test_upstream_qt_language_overrides.py --junitxml=.venv/parser-repair/upstream-sync/qt-overrides-after.xml
```

The wider source/package/hosted profiles remain pending. Earlier six-case
preliminary receipts precede the mixed-input case and final acceptance names;
the seven-case before/after identities above are the final focused comparison.

### Qualified native fixture expectations

Four incoming C++ lexical-call fixtures initially expect the earlier flattened
IDs for `Outer::Inner` and `Outer::Mid::Inner`. The accepted Qt/native producer
retains qualified identities. INC-QML-54 aligns only those expected IDs, preserving
the positive call target, forbidden-target, own-base/enclosing precedence and
warm-cache assertions. The neighboring negative-only nested-class assertion is
made meaningful against the same actual qualified identity; no production
resolver behavior changes for this fixture alignment. This preserves
REQ-QML-003-AC02/AC04, REQ-QML-010-AC01/AC02 and REQ-QML-018-AC02.

The focused `tests/test_extract.py -k 'unqualified_call or nested_class_declared_after'`
selection passes **32 cases**, with 311
deselected. It is a fixture-selection checkpoint, not the full extraction or
integrated suite result.

### Shared extraction compatibility selection

The nine-module source selection below passes **967 cases**, with zero failures/
errors, four skips and 388 warnings in 45.81 seconds. The four actual skips are
Windows symlink capability cases in `tests/test_extract.py`:
`test_collect_files_follows_symlinked_directory`,
`test_collect_files_skips_out_of_root_symlinked_directory`,
`test_collect_files_skips_out_of_root_symlinked_file_by_default` and
`test_collect_files_handles_circular_symlinks`. The host requires an elevated
shell or Developer Mode for their setup; they are not optional-parser acceptance
or passing filesystem evidence.

```powershell
.venv/Scripts/python.exe -m pytest -q --disable-warnings -o addopts= tests/test_extract.py tests/test_languages.py tests/test_qt_worker_cache_integrity.py tests/test_qt_constructor_ownership.py tests/test_csharp_partial_classes.py tests/test_csharp_type_resolution.py tests/test_csharp_underscore_collisions.py tests/test_cache_stale_import_target.py tests/test_upstream_qt_language_overrides.py --junitxml=.venv/parser-repair/upstream-sync/core-compatibility-final.xml
```

This selection covers shared/native producer, cache and unrelated-language
compatibility under REQ-QML-014-AC03/AC04 and the acceptance assignments above.
It overlaps the seven override cases and earlier fixture selection; totals are
not additive. Complete source, installed-artifact and hosted profiles remain
pending.

### Generated guidance and dependency-lock checkpoint

All **134 regenerated artifacts** and the audit-coverage, schema-singleton,
monolith-roundtrip and always-on-roundtrip validators pass for the integration
checkpoint. The authoritative generator/fragments own these changes; generated
outputs are not hand-edited. The imported lock's editable project version 0.9.84
is reconciled offline with manifest version 0.9.92. All 210 resolved package
identities remain unchanged except the project version; uv also normalizes
markers. This is source-generation and lock evidence, not a fresh installed-wheel
or platform-runtime result.
The all-extras source environment now identifies package 0.9.92 and 197 compatible
installed packages. It is separate from the unchanged per-user policy-25 tool;
source-environment setup does not establish new artifact adoption.

The digest-verified official Bun 1.4.0 portable tool runs the imported Pi guard on
native Windows with **five passes and fifteen failures**. The failing POSIX
shebang fixture discovery reports `ENOENT`/undefined guidance; it is not Qt/QML
extraction failure. The imported Pi CI job targets Ubuntu. This native run does
not establish its Linux/hosted profile, which remains pending; assertions are not
weakened to turn the incompatible fixture setup into passing evidence. The
failure log remains at `.venv/upstream-sync-0.9.92/pi-tests.log`.

### Shared direction-loader checkpoint

The actual reload rejection selection initially has **four failures and six
passing controls**, with 48 deselected. After the shared loader stops filling a
partial explicit marker pair, the ten-module direction/consumer selection has
**257 passes, zero failures/errors/skips**, with 109 warnings in 89.39 seconds.
Existing test expectations are unchanged; complete-marker and unmarked legacy
behavior remain covered.

```powershell
.venv/Scripts/python.exe -m pytest -q --disable-warnings -o addopts= tests/test_qt_affected_direction.py -k typed_reload --junitxml=.venv/parser-repair/upstream-sync/partial-direction-before.xml
.venv/Scripts/python.exe -m pytest -q --disable-warnings -o addopts= tests/test_paths.py tests/test_export_direction.py tests/test_qt_affected_direction.py tests/test_qt_affected_direction_updates.py tests/test_qt_json_direction.py tests/test_qt_json_direction_updates.py tests/test_qt_update_direction_integrity.py tests/test_qt_mcp_consumers.py tests/test_qt_mcp_stdio.py tests/test_upstream_qt_query_direction.py --junitxml=.venv/parser-repair/upstream-sync/direction-restoration.xml
```

The result includes the new override-query module's eleven cases, including
`test_req_qml013_ac02_override_keeps_generic_callers_and_qml_source_owners`,
`test_req_qml010_ac04_override_cannot_bypass_owner_edge_direction` across
partial/foreign/reversed pairs, and
`test_req_qml013_ac04_parallel_consumer_orders_all_original_relationships`.
These are overlapping source checkpoints, not installed or hosted acceptance;
the source owner's isolated before-fix query receipt remains separately required.

### Combined cache namespace checkpoint

The nine-module cache/alias selection passes **140 cases**, with zero failures/
errors, ten platform skips and 105 warnings in 18.60 seconds. The actual skip
reasons are POSIX directory-symlink discovery, unsupported symlink creation and
Windows elevated/Developer Mode requirements. They do not establish those
platform contracts. The included `tests/test_upstream_qt_cache_integration.py`
cases explicitly prove the combined namespace and retained-data boundaries:

- `test_req_qml003_ac04_qml018_ac05_old_namespaces_miss_and_refresh` covers versions 0.9.74/0.9.76/0.9.92 with prior schemas 5/12/13/17, including same-version 0.9.92 retirement of 13/17;
- `test_req_qml003_ac04_qml018_ac05_mixed_cold_warm_serialized_facts` preserves mixed cold/warm source facts;
- `test_req_qml011_ac03_ac04_qml018_ac06_upgrade_failure_retains_repairs_repeats` protects failed-upgrade retention, repair and unchanged repeat.

```powershell
.venv/Scripts/python.exe -m pytest -q --disable-warnings -o addopts= tests/test_cache.py tests/test_grammar_cache_key.py tests/test_cache_stale_import_target.py tests/test_upstream_qt_cache_integration.py tests/test_qt_worker_cache_integrity.py tests/test_upstream_qt_language_overrides.py tests/test_extract_path_memo.py tests/test_ext_tagged_id_clash.py tests/test_source_alias_provenance.py --junitxml=.venv/parser-repair/upstream-sync/cache-alias-final.xml
```

Grammar fingerprints, override salt and Qt worker cache bypass are exercised
through their production owners. At this checkpoint the separate newly extended
combined alias publication lifecycle has two update/full identity failures in
`.venv/parser-repair/upstream-sync/alias-collision-lifecycle.xml`. Earlier direct
cold/warm alias passes do not establish lifecycle correctness. All selections
overlap; complete source/package/hosted evidence remains pending.

### Placeholder convention source checkpoint

The 40-case `tests/test_upstream_qt_placeholder_roles.py` selection initially has
**34 failures and six passing controls**. After the shared predicate and tierless
minting correction, that module plus `tests/test_qt_publication_stub_origin.py`,
`tests/test_external_stub_endpoints.py` and `tests/test_qt_orphan_import_proof.py`
has **119 passes, zero failures/errors/skips**, with 29 existing stat-root warnings
in 21.92 seconds. The production cases cover:

- `test_canonical_legacy_and_exported_shapes_remain_tierless`;
- `test_authored_or_noncanonical_shapes_keep_their_data`;
- `test_partial_external_shapes_have_no_automatic_cleanup_authority`;
- `test_graph_attributes_use_the_actual_identity_and_unicode_presentation`;
- `test_real_incremental_graph_retains_authored_external_orphans`.

Existing manual/watch first publication, repeat, deletion/restoration, cache and
failed-publication/repaired-retry assertions remain exercised. Old fixture-only
semantic-stamp expectations intentionally change to D30's tierless convention;
authored-origin and extra-field protection assertions remain. Receipts are
`.venv/upstream-sync-0.9.92/placeholder-roles-before.xml` and
`placeholder-compatibility-after.xml` beneath the same evidence directory.
At that checkpoint the external-role versus generic-code orphan branch remained
under review; that result does not establish the later guard, whole integration or
artifact/hosted acceptance. Exact-shape legacy authorship is the documented D30
exception, not a passing attribution test.

The final eight-module source selection extends the role module to **55 cases**
and passes **168 cases, zero failures/errors/skips**, with 31 warnings in 31.68
seconds. `test_generic_code_orphan_collection_cannot_bypass_external_role` adds
real re-extraction/deletion protection for the generic-code cleanup branch.
The imported no-cluster fixture previously used an empty label while claiming
canonical mint ownership; it now obtains the real minted shape and has a separate
noncanonical preservation control. No authored-origin assertions are relaxed.

```powershell
.venv/Scripts/python.exe -X utf8 -m pytest -q -p no:cacheprovider --tb=short tests/test_upstream_qt_placeholder_roles.py tests/test_qt_publication_stub_origin.py tests/test_external_stub_endpoints.py tests/test_qt_orphan_import_proof.py tests/test_no_cluster_undeclared_endpoints.py tests/test_lost_saved_semantic_nodes.py tests/test_merge_sweeps_reextract_orphans.py tests/test_semantic_origin_stamp.py --junitxml=.venv/upstream-sync-0.9.92/placeholder-final.xml
```

The earlier 40-case before-fix receipt remains the predicate's negative evidence;
it does not imply that the later fifteen guard cases were in that selection.
These source profiles overlap and establish no installed/hosted result.

### Transactional deletion and override-query checkpoint

The source selection of `tests/test_upstream_qt_labels_publication.py`,
`tests/test_upstream_qt_query_direction.py` and
`tests/test_upstream_qt_language_overrides.py` passes **32 cases**, with zero
failures/errors/skips in `.venv/upstream-sync-0.9.92/runtime-final.xml` and its log.
The fourteen deletion cases map directly to the existing criteria:

- REQ-QML-011-AC04: `test_req_qml011_ac04_inventory_deletion_commits_once_and_repeats` covers present and absent products;
- REQ-QML-012-AC04: `test_req_qml012_ac04_deletion_rejects_undeclared_or_unsafe_names` and `test_req_qml012_ac04_conflicting_stage_and_delete_are_rejected` reject unsafe, undeclared and conflicting requests;
- REQ-QML-012-AC02: `test_req_qml012_ac02_real_deletion_or_later_failure_restores_then_retries` forces real deletion/later replacement failures and retry;
- REQ-QML-012-AC04/REQ-QML-018-AC06: `test_req_qml012_ac04_failed_deleted_product_restore_keeps_recovery_copy`, `test_req_qml018_ac06_readonly_deletion_preserves_products_then_retries` and `test_req_qml018_ac06_pending_label_promotion_rolls_back_with_watcher_products` protect recovery copies, real read-only failure and watch-cohort retention.

The override-query before-fix selection records **nine failures and one passing
control**, with one parallel-consumer case deselected:

```powershell
.venv/Scripts/python.exe -X utf8 -m pytest -q -p no:cacheprovider --tb=short tests/test_upstream_qt_query_direction.py -k override --junitxml=.venv/upstream-sync-0.9.92/query-direction-before.xml
```

Its final eleven cases pass within both the 32-case result and the overlapping
257-case direction profile; neither count is additive or installed/hosted proof.

### Encoded hook source checkpoint

The new ownership and upstream cleanup selection initially records **three
failures and 27 passing controls** in `hook-before.xml`. The final selection
passes **53 cases, zero failures/errors/skips**, in 9.80 seconds:

```powershell
.venv/Scripts/python.exe -X utf8 -m pytest tests/test_codex_hook_identity.py tests/test_install_hook_identity.py tests/test_codex_hook_execution.py -q --tb=short
```

Receipts are `.venv/upstream-sync-0.9.92/hook-final.xml` and its log. The original
native execution assertions remain unchanged. An intermediate expectation that
rejected every trailing-space copy contradicts the established native contract;
the corrected bounded ASCII space/tab controls preserve that behavior. The final
selection includes four added accepted-suffix controls. Exact payload/options/
wrapper/marker checks preserve foreign, leading/other-whitespace and malformed
entries without execution or filesystem lookup. The two small helper/test files
pass focused typing. Fresh installed and hosted profiles remain pending.

### Bounded collision-cohort checkpoint

The ordinary-root helper/lifecycle selection passes **14 cases, zero failures/
errors/skips**, with fourteen warnings in 5.92 seconds:

```powershell
.venv/Scripts/python.exe -m pytest -q --disable-warnings -o addopts= tests/test_filename_cohorts.py --junitxml=.venv/parser-repair/upstream-sync/cohort-lifecycle-final.xml
```

Exact source tests include `test_req_qml003_ac02_walked_alias_keeps_same_stem_file_and_symbol_distinct`,
`test_req_qml011_ac03_cohort_rejection_keeps_products_and_recovers` and the
`test_req_qml011_ac03_` helper cases for accepted-only selection, deterministic
order, retired-source keys, walked identity, no source I/O and failed admission.
The lifecycle cases prove edit/removal/restoration/repeat/full parity, actual
selected peers and unchanged-unrelated exclusion. The retention fixture initially
passed the analysis root to a graph-output snapshot helper, yielding absent
snapshots; it now passes the output directory and requires nonempty graph/manifest
evidence before asserting retained bytes. Root-marker/Qt-state presence or absence
is compared as applicable; no report-file retention is inferred from that fixture.

Additional scan-root junction cases then expose the caller root-domain mismatch:

```powershell
.venv/Scripts/python.exe -m pytest -q --disable-warnings -o addopts= tests/test_filename_cohorts.py -k aliased_scan_root --junitxml=.venv/parser-repair/upstream-sync/cohort-root-domain-before.xml
```

That selection has **two failures**, with fourteen deselected. Its
`test_req_qml011_ac03_aliased_scan_root_keeps_cohort_domain_and_full_parity` covers
absolute/relative invocation, edit/deletion/restoration/repeat/full parity and
unrelated targets. The approved correction passes discovery's existing
`watch_root` to both selectors, preserving walked child aliases without relaxing
admission. The final three-selector Terraform/physical/filename composition and
corrected junction reruns remain pending at this checkpoint; complete source,
artifact and hosted gates remain pending.

The final hook rerun extends that selection to **55 passes, zero failures/errors/
skips**, in 8.00 seconds (`.venv/upstream-sync-0.9.92/hook-complete.xml`). It
supersedes the earlier 53-case checkpoint for the expanded identity controls;
the overlapping totals must not be added.

### Relative-root and refresh-order boundary checkpoints

The admitted collision cohort is composed with existing Terraform refresh;
the four two-direction/failure controls in
`tests/test_upstream_qt_refresh_order.py` pass after two initial failures and two
controls. A subsequent component-prefix case identifies the relative scan-root
anchoring discrepancy. With the same verified `scan` marker pointing to `real`,
the canonical prefix case fails and neighboring `real2` remains a passing
rejection control in `.venv/upstream-sync-0.9.92/root-prefix-before.xml`, with
four deselected. `test_req_qml020_ac01_saved_root_alias_recognizes_only_exact_project_prefix`
is a focused `_StoredSourcePaths` guard; it does not independently verify the
whole project-membership criterion. The existing real relative-root lifecycle
also retains its untouched-node/full-parity failure assertion. Corrected combined
junction/closure/prefix source receipts remain pending at this checkpoint.

### Typing and release-gate checkpoint

Whole-project typing remains **Failed**. The integration checkpoint reports
652 errors across 822 files, compared with an independently rerun prior-source
baseline of 605 errors across 712 files under the same interpreter. Source-anchor
comparison retains 570 diagnostics, removes 35 and adds 82; counts alone do not
classify the added findings as upstream or integration defects. The comparison
is retained privately in `pyright-comparison.json`. A later targeted retirement-
argument correction removes an introduced error; the final frozen whole-project
count must be recorded after rerun rather than inferred by subtraction.

Nine small production/new-test files pass focused typing: filename cohorts,
publication, encoded-hook command and the filename/hook/placeholder/query/labels/
language-override regressions. Whole Ruff and all 134 generated artifact checks
pass at their recorded checkpoint. A fresh isolated all-extras-derived stage is
provisioned offline with `qml`, `watch`, `mcp`, `sql` and separate pytest tools;
it is preparation, not a new reviewed wheel/install result. Complete source,
artifact/install, hosted and exact merged-SHA proof remain pending. The active
per-user tool and application graph remain unchanged.

### Final pre-release source-selection freeze

The final D31 source selection passes **31 cases, zero failures/errors**, with two
existing platform skips and 44 warnings in 14.23 seconds:

```powershell
.venv/Scripts/python.exe -X utf8 -m pytest -q -p no:cacheprovider --tb=short tests/test_filename_cohorts.py tests/test_upstream_qt_refresh_order.py tests/test_source_alias_provenance.py --junitxml=.venv/upstream-sync-0.9.92/selection-frozen.xml
```

This supersedes the earlier pending D31 junction/composition/prefix checkpoint
states above. Both absolute/relative root-alias events, exact `real`/`real2`
prefix recognition, two-direction Terraform fanout, physical/filename closure,
unchanged unrelated targets and invalid-selection retained-product/retry cases
pass. The two source-alias platform skips remain unverified capability cases.
The frozen cohort and refresh-order modules have 266 and 117 physical lines.
Complete source suites, fresh reviewed wheel/isolated installation, hosted and
exact merged-SHA proof remain pending; no new per-user/application adoption is
performed. Earlier overlapping source counts must not be summed.

## Committed upstream integration checkpoint — 90578033

Status: **Raw-source artifact identity and bounded installed profiles verified;
complete source gate failed; corrections/hosted proof pending; whole typing failed**.

| Identity | Recorded value |
| --- | --- |
| Local merge commit | `9057803361f49988e9e41d64cf4290035184e5f7` |
| Merge parents | `88010d0b638c25bdc1ef569dc96327e68c53a4c2` and upstream `86c57be8204673c2a1b9849a3292a7dd3ab373d8` |
| Production tree | `32d1e6b578375cf1f3d3f905f9e116cb83729f0b` |
| Reviewed 0.9.92 wheel SHA256 | `3744325bbcfa7013ad0a3054ec379a04c00900540b1faae3a161451dc9fcef8b` |
| Producer identities | AST schema 18; Qt policy 25 |

The wheel is built from raw committed Git blobs. All **326 shipped Graphify
package files** match the reviewed source bytes; the new Pi package resources
are present. The developer-only extractor `MIGRATION.md` is intentionally
unshipped. This is local artifact proof, not a registry publication.

### Original isolated installed profile

The offline `qml`, `watch`, `mcp`, `sql` stage contains 71 distributions across
runtime and separate verification tooling. Dependency checking passes. Its
21-module profile passes **495 cases, zero failures/errors/skips**, with 49
warnings in 64.79 seconds. The declared modules bind individual source
acceptance assignments to installed production code:

| Installed selection | Cases | Acceptance scope |
| --- | --- | --- |
| The thirteen existing parser/CMake/analysis-state/artifact modules of the policy-25 repair profile | 342 | Existing INC-QML-53 parser, literal metadata, retention and artifact assignments, reverified under the integrated source |
| `test_filename_cohorts.py` | 16 | REQ-QML-003-AC02/AC04; REQ-QML-011-AC03/AC04; REQ-QML-012-AC01/AC02 |
| `test_upstream_qt_language_overrides.py` | 7 | REQ-QML-002-AC01/AC04; REQ-QML-010-AC02/AC04; REQ-QML-011-AC03/AC04; REQ-QML-012-AC01; REQ-QML-018-AC02/AC07 |
| `test_upstream_qt_placeholder_roles.py` | 55 | REQ-QML-010-AC02/AC04; REQ-QML-011-AC04; REQ-QML-012-AC02; REQ-QML-018-AC06, within D30's explicit legacy convention |
| `test_upstream_qt_labels_publication.py` | 14 | REQ-QML-011-AC04; REQ-QML-012-AC02/AC04; REQ-QML-018-AC06 |
| `test_upstream_qt_query_direction.py` | 11 | REQ-QML-010-AC02/AC03/AC04; REQ-QML-013-AC01/AC02/AC04; existing direction rejection/retention |
| `test_upstream_qt_cache_integration.py` | 14 | REQ-QML-003-AC04; REQ-QML-011-AC03/AC04; REQ-QML-018-AC05/AC06 |
| `test_codex_hook_identity.py` and unchanged `test_codex_hook_execution.py` | 36 | REQ-CORE-001-AC05 selected identity, reinstall/uninstall and native execution boundaries |

The thirteen repair modules are `test_qt_cpp_template_defaults`,
`test_qt_cmake_mutations`, `test_qt_cmake_mutation_updates`,
`test_qt_cmake_tooling_order`, `test_qt_cmake_alias_resolution`,
`test_qt_analysis_state`, `test_qml_wheel_artifact`,
`test_qt_cmake_header_membership`, `test_qt_cmake_resource_collisions`,
`test_qt_cmake_review_boundaries`, `test_qt_cmake_review_updates`,
`test_qt_cmake_rc_dependencies` and `test_qt_cmake_rc_updates`, each under `tests/`
with its `.py` suffix. This selected installed profile does not stand in for the
complete source suite or every criterion's wider platform/system obligations.

Receipts `stage-receipt.json` and `stage-tests.xml`/`.log` remain under the ignored
`.venv/upstream-sync-0.9.92/` evidence directory. They bind the exact source,
production tree, wheel, schema/policy, successful outcomes and unchanged package
bytes. The direct receipt read confirms pytest exit zero and no global-tool
modification.

Executed isolated entry point, expressed relative to the repository:

```powershell
.venv/upstream-sync-0.9.92/stage/Scripts/python.exe -I .venv/upstream-sync-0.9.92/run_stage.py
```

The retained helper and receipts define the exact 21-module collection and
installed-origin checks; the command is an evidence entry point, not a shipped
project utility.

An independent actual OS-temporary-directory probe runs outside the checkout
with the stage interpreter's isolated mode. Every loaded Graphify origin is
installed, and `-I -m graphify --help` exits zero with CLI help present.
`runtime-outside-probe.json` binds the same source/version and the 71-distribution
environment; no checkout import is accepted as installed proof.

### Separate locked HCL add-on profile

Only `tree-sitter-hcl==1.2.0`, matching the frozen lock/native grammar version, is
added offline with no dependency resolution to the isolated stage. The exact
delta is one added distribution: 71 becomes 72, with no previous version changes
or removals, and dependency checking still passes. The six production cases in
`test_upstream_qt_refresh_order.py` then pass with **zero failures/errors/skips**,
seven warnings, in 3.75 seconds. They cover both Terraform/filename fanout
directions, rejected-selector retention/retry and the component-aware stored-root
prefix guard; the latter is partial supporting evidence, not the whole
REQ-QML-020 membership criterion.

`stage-addon-receipt.json` and `stage-addon-tests.xml`/`.log` bind the same
source/tree/wheel, the exact dependency delta and the frozen public test bytes.
All 326 package files remain byte-identical before/after the add-on; 158 loaded
Graphify modules have isolated-stage origins. The original 495-case receipts are
unchanged. These are separate environment profiles and are not combined into a
single aggregate passing-suite claim.

The exact add-on and execution steps, with local paths expressed relatively, are:

```powershell
uv pip install --offline --no-deps --python .venv/upstream-sync-0.9.92/stage/Scripts/python.exe tree-sitter-hcl==1.2.0
.venv/upstream-sync-0.9.92/stage/Scripts/python.exe -I .venv/upstream-sync-0.9.92/run_stage_addon.py
```

### Source, typing and delivery limits

Whole Ruff, whitespace and all **134 generated artifacts** pass. The AST-only
repository graph update succeeds with **26,995 nodes and 63,154 edges**, without
clustering or API calls. Graph generation is source-navigation evidence, not
acceptance of every relationship or an application graph refresh.

The actual frozen whole-project Pyright result is **651 errors across 823
files**, compared with the independently rerun prior 605-error/712-file baseline
under the same interpreter. The earlier 652-error snapshot predates the corrected
retired-path argument; its detailed 570-retained/35-removed/82-added comparison is
historical. Source review identifies twenty core additions and the remaining
seven watch/three service additions at exact upstream function/anchor matches;
this partial classification is not permission to call whole typing green. New
small production/test owners pass focused checks; broad typing cleanup is not
part of this integration.

The complete source run is terminal with **11,547 passed, 44 failed, 172 skipped
and twelve setup errors** across 11,775 cases. No complete source-suite or hosted
pass is recorded. Hosted source/base/checkout evidence, any authorized subsequent PR merge
and its exact resulting-SHA proof remain pending. Neither isolated profile
changes the active per-user tool, an application graph or team package adoption.
This source checkpoint and artifact must be re-evaluated if production inputs
change.

### Complete source result and integrity outcome

The complete 11,775-case source run reports **11,547 passed, 44 failed, twelve
setup errors and 172 skipped**, with pytest exit 1 in 1,818.10 seconds. The
wrapper takes 1,822.49 seconds and also exits 1. Exact invocation:

```powershell
& .venv/Scripts/python.exe .venv/upstream-sync-0.9.92/run_full_source.py 9057803361f49988e9e41d64cf4290035184e5f7 *> .venv/upstream-sync-0.9.92/full-runner.log
```

Its child runs `python -X utf8 -m pytest tests/ -q --tb=short -rs` with JUnit at
`.venv/upstream-sync-0.9.92/full-source.xml`, admitted process-local Git Bash,
isolated `COVERAGE_FILE`, the reviewed `GRAPHIFY_QML_TEST_WHEEL` and disabled
automatic refresh/tips. `full-source-receipt.json`, `full-source.log` and
`full-runner.log` retain the exact private local command identities without
putting personal paths in public documentation.

| Failed boundary | Failures / setup errors |
| --- | --- |
| Existing C++ import prior-proof manual/watch variants | 18 / 0 |
| Part A explicit-root fixture capture and cache relocation | 15 / 0 |
| Four tooltip external DOM harnesses | 4 / 0 |
| Devin/aider recorded-interpreter execution | 2 / 0 |
| Low-level read-only owned-copy replacement | 1 / 0 |
| Code-only fixture missing trusted Step 1 root | 1 / 0 |
| Two absolute-key memo hit observations | 2 / 0 |
| Qualified-target legacy ambiguity exit expectation | 1 / 0 |
| Aggregate invariance success corpus containing two rejection fixtures | 0 / 12 |

The receipt confirms unchanged source HEAD/tree, dependency identities and the
pre-existing root coverage file. Its `tracked_inputs_unchanged` flag is **false**:
the only tracked test-tree mismatch is this documentary `TRACEABILITY.md` update;
all seven changed tracked files are the assigned documentation. Test/code/tool
inputs remain unchanged, but the runner still raises its integrity assertion.
That assertion is retained as failure, not waived or presented as a passed
freeze gate. The corrected full run must start only after all documentation is
frozen as well.

All 172 skips retain exact individual reasons in the receipt. The largest
profiles are 51 Windows symlink-capability cases, 31 POSIX Bash/cat cases,
30 emitted-hook POSIX-sh cases and sixteen POSIX physical-link/`..` cases.
Four cases lack the C preprocessor, two lack the required database service and
three require a Bash-side Python import environment unavailable in this native
profile. The other 35 retain their explicit platform/resource/version reasons.
None establish passing acceptance; their applicable Linux/native/service
profiles remain separate gates. This terminal failed source run does not change
the earlier bounded installed outcomes or establish hosted/merged-SHA proof.

## Post-905 correction matrix — INC-QML-54

Status: **Planned; no corrected-source acceptance yet**. The complete frozen
source run has exposed deterministic failures and twelve invariance setup errors;
its terminal outcome is recorded above. The following assignments precede correction
and do not supersede the exact `90578033` wheel/495-case/separate-HCL receipts.
Future changed production or generated inputs need fresh source/artifact proof.

| Acceptance IDs | Exact existing protection or planned new regression | Evidence boundary |
| --- | --- | --- |
| REQ-CORE-001-AC03; REQ-QML-012-AC02; REQ-QML-013-AC03; REQ-QML-018-AC06 | `tests/test_atomic_writes.py::test_os_replace_with_fallback_still_replaces_a_readonly_destination`; `tests/test_atomic_replace_retention.py::test_req_qml018_ac06_readonly_rejects_without_displacing_destination`, `test_req_qml018_ac06_directory_is_not_a_replace_fallback_target`, `test_req_qml018_ac06_readonly_source_is_consumed_on_successful_fallback`, `test_req_qml018_ac06_readonly_source_cleanup_rollback_retains_attributes`; `tests/test_atomic_writes.py::test_write_text_atomic_refuses_a_readonly_destination_without_leaking_a_temp`; `tests/test_qt_readonly_publication.py::test_req_qml018_ac06_readonly_graph_preserves_products_then_retries`; planned `tests/test_graphml_owned_replacement.py` | D32 resolves conflicting raw-helper expectations explicitly: caller-owned replacement permits read-only regular copies, atomic/product writers still reject. GraphML's native regular-read-only preflight must land before raw guard removal, with retained input/output, temp cleanup, retry/repeat and real symlink-target controls. Retain real byte/mode rollback, directory/symlink protections and recovery/retry. Corrected test names/new destination-mode/cleanup cases and executed command/result remain pending. |
| REQ-CORE-001-AC01; REQ-CORE-004-AC02; REQ-QML-014-AC03/AC04 | Planned `tests/test_skillgen_interpreter_identity.py`; retain existing devin/aider real code-only runbook assertions and generator/monolith validators | Execute actual rendered `-c`/`-m` commands using the recorded spaced interpreter against split-prefix and PATH decoys; require literal args/cwd/order and empty/missing/failing no-fallback outcomes. Quote-removal control must fail. Exact legacy/canonical PowerShell parity and strict quote-only round-trip/drift checks are required. Commands/results/test identities remain pending. |
| REQ-QML-014-AC03/AC04; REQ-QML-019; REQ-QML-021 | The four imported tooltip DOM harness cases under investigation | Fixture supplies only missing `window.addEventListener`; all original tooltip/camera/pan/event assertions remain. Exact case identities and rerun are pending; no native-browser/device acceptance is inferred. |
| REQ-QML-014-AC02/AC03/AC04 | `tests/test_resolve_memoization.py::test_absolute_path_lookup_skips_getcwd` | Read-only reproduction `resolve-memo-readonly.xml` fails the first-miss observation; stack probe shows the inspected Windows `Path.resolve`/`ntpath.realpath` absolute miss calls `getcwd` once, while a repeated absolute-key hit calls it zero times. Planned test-only absolute-key warmup measures the intended hit contract; cold correctness/relative-CWD checks remain. Corrected result/command pending, no production resolver change. |
| REQ-QML-001-AC02/AC04; REQ-QML-012-AC01/AC02; REQ-QML-014-AC03/AC04 | `tests/test_graph_invariance.py` original twelve cases plus planned exact-copy membership and two real-CLI rejection controls; `tests/test_qml_parser_probe.py::test_qml00_malformed_empty_partial_inputs_do_not_look_successful[Incomplete.qml]` and `[Malformed.qml]`; partial-input variants of `tests/test_qml_cli_persistence.py::test_cli_qml_failure_preserves_graph_and_manifest_despite_override` and `tests/test_qml_watch_persistence.py::test_watch_qml_failure_preserves_completed_products_with_force` | Success-copy omission is exactly the two deliberate `qml/parser_probe` rejection paths. Preserve every valid Qt input, six invariance assertions, nontrivial graph guards, LF/CRLF and raw/clustered profiles. Separate negatives still return exit 1/`QML_GRAPH_PRESERVED` and no first accepted graph/manifest; force/partial flags cannot weaken existing retained-product guards. Exact added names and corrected result remain pending. |

The [plan](../docs/qt-qml/PLAN.md#post-905-full-suite-findings-acceptance-before-correction)
records the bounded scope and diagnostic impact; [D32](../docs/qt-qml/ARCHITECTURE.md#d32--output-policy-stays-with-the-owning-writer)
records why replacing the raw-helper rejection expectation is a deliberate
writer-ownership reconciliation. No full-suite or corrected-artifact pass is
claimed by this matrix.

Full-run finding: eighteen manual/watch variants of
`tests/test_qt_cpp_file_role_updates.py::test_req_qml011_ac04_cpp_import_cleanup_requires_exact_prior_source_proof`
expect preservation when prior import authority is semantic, unmarked, foreign,
conflicting, contextual, confidence-bearing, oppositely directed, partially
directed or foreign-direction transport. D30's generic
exact-shape sweeps currently remove the missing zero-degree placeholder before
the existing Qt prior-source proof can protect it. This is a recorded ownership
discrepancy under REQ-QML-010-AC04/REQ-QML-011-AC04/REQ-QML-012-AC02. The
accepted correction preserves the original assertions and exact prior-ID/source
requirement; canonical shape alone cannot authorize this Qt lifecycle cleanup.
The additional four exact variants are `[partial_direction-manual]`,
`[partial_direction-watch]`, `[foreign_direction-manual]` and
`[foreign_direction-watch]`. Sixteen interleaved authored/node-role controls pass.
The accepted [D33](../docs/qt-qml/ARCHITECTURE.md#d33--retained-cleanup-context-belongs-to-the-accepted-graph)
mechanism stores strictly versioned/typed/bounded existing-node retention context
in the same graph product. The accepted APIs are strict immutable
`read_import_retention(payload, *, is_placeholder)` and pure copied-payload
producer `apply_import_retention(payload, ids, *, is_placeholder)`. The exact
schema-1 graph field admits sorted unique existing canonical placeholders only,
at most 100,000 IDs and 4,096 UTF-8 bytes each; wrong/foreign/duplicate/over-limit
transport rejects with safe `QT_IMPORT_RETENTION_INVALID`, never truncation.
An optional caller-owned loader sink keeps its four-value return, computes policy
before backfill and passes immutable restrictions to every merge/finalizer seam.
Planned modules `test_qt_import_retention.py` and `test_qt_import_retention_updates.py`
must provide exact new test identities and commands/results before verification.
Required acceptance includes
raw/clustered/build-merge/JSON reload/repeat/last-Qt removal, clearing on accepted
proof or legitimate node removal/role transition, corrupt/over-limit rejection,
actual cohort rollback/recovery/retry and preserved generic orphan healing. No
second durable stamp/cache, global preservation or authored-role relaxation is
established. This planned transport change invalidates the earlier wheel as
acceptance evidence for the future corrected source.

Additional **Planned** compatibility/admission assignments:

| Acceptance IDs | Exact test and faithful boundary |
| --- | --- |
| REQ-QML-010-AC01; REQ-QML-011-AC01/AC04; REQ-QML-012-AC01/AC02; REQ-QML-018-AC06 | Planned `tests/test_qt_reconcile_diagnostics.py` proves real cold/warm empty-key parity and current diagnostic metadata replacing old observations through `_reconcile_existing_graph` and actual persistence. Return fresh extraction keys plus merged structural/token overrides; never replay prior graph failure metadata. Original raw invariance and malformed-source gates remain exact. Before-fix boundary is the warm diagnostic-field loss in the 108-case selection; exact new names/negative/final command and result pending. |
| REQ-QML-014-AC02/AC03/AC04 | `tests/test_source_key_memoization.py::test_absolute_path_lookup_skips_getcwd` shares the paired Windows first-absolute-miss observation. Warm its absolute key before measuring hits; retain cold correctness and relative-CWD assertions. Corrected command/result pending. |
| REQ-QML-003-AC02/AC04; REQ-QML-011-AC03/AC04; REQ-QML-012-AC01/AC02; REQ-QML-014-AC03/AC04 | `tests/test_skill_code_only_incremental_update.py::test_codex_code_only_update_materializes_and_merges_fresh_ast`; planned `test_codex_part_a_missing_trusted_root_rejects_before_ast_then_recovers`; `tests/test_skill_part_a_explicit_root.py::test_part_a_passes_an_explicit_root` fourteen-host variants and `test_relocating_only_the_cache_does_not_rename_part_a_nodes`. Read-only `skill-root-readonly.xml`/`.log` and `skill-codeonly-stderr.log` expose sixteen existing fixture failures: stale literal call capture for fourteen hosts/relocation, plus code-only missing trusted `.graphify_root`. Keep all original incremental assertions; add correct Step 1 setup and no-marker rejection/retention/recovery. Structural capture and real-body execution change only `cache_root`, requiring equal nonempty IDs/portable paths. Corrected command/result pending. |
| REQ-QML-018-AC04; REQ-QML-013-AC01; REQ-QML-014-AC03/AC04 | `tests/test_upstream_qt_path_integration.py::test_req_qml_018_ac04_duplicate_qualified_target_refuses_guess`. `qualified-target-readonly.xml` fails only the legacy expected exit 1; isolated prospective expectation migration to current typed ambiguity 3 passes in `qualified-target-prospective.xml`. Keep all candidates, exact-ID success, no-guess and graph-byte nonmutation assertions. This is not a committed corrected-source pass; final command/result pending. |

Fresh accepted source reintroduction must clear obsolete context in the same
successful run; legacy backfill is not fresh source proof. Planned dependency
characterization covers both fresh-process `paths`/`build` import orders and
valid/corrupt semantic loads, with the predicate imported locally after structural
checks and passed into the pure helper. Shared-role extraction remains a separate
preparatory refactor, not evidence required from an unperformed mechanical move.

### D33 preimplementation regression result

The new `test_qt_import_retention.py` and `test_qt_import_retention_updates.py`
selection executes before changing its build/watch/Qt-cleanup production owners:
**75 failed, one passed, zero skips** across 76 cases. The passing valid-JSON
control is retained; six real transport boundaries, 66 corrupt-context scenarios
and four lifecycle profiles expose missing retained-context behavior. This is
negative evidence, not implementation or release acceptance.

```powershell
& .venv/Scripts/python.exe -X utf8 -m pytest -q --disable-warnings -o addopts= tests/test_qt_import_retention.py tests/test_qt_import_retention_updates.py --junitxml=.venv/upstream-sync-0.9.92/retention-before.xml *> .venv/upstream-sync-0.9.92/retention-before.log
```

The receipt remains distinct from future final producer/export/import-order
cases and corrected-source results; final exact names, limits/changed-branch
coverage and artifact proof are pending.

D33's next twelve corrupt prior-context manual/watch and raw/clustered
rejection/retry cases expose cache ordering: outputs retain prior bytes, but a
candidate AST cache is written before late rejection. The approved correction
shares one build-owned capped raw loader with the existing four-value loader;
watch owns its snapshot, preflights reserved context before extraction/cache and
passes it into reconciliation without rereading. Prior proof precedes backfill,
and origin stamping copies borrowed item dictionaries. Require no force bypass,
no candidate cache, complete old cache/product retention, explicit loader binding/
order/single-read tests and corrected retry. Exact test identities/before/final
commands/results remain pending; D33 is not Verified by earlier product-only
retention or its initial passing transport cases.
The saved seam is `build._read_existing_graph_data(Path) -> dict | None`, with
unchanged cap/default `RuntimeError` and strict reserved-context reading.
`_load_existing_graph` retains its four-value return; reconciliation accepts
`prior_graph_data` and explicit `preflight_done=False`. Binding/order controls
must distinguish direct calls from supplied/missing snapshot reuse, preserve
borrowed top item dictionaries before stamping/rebasing, and keep late output/
concurrent-change/publication checks. The active 106-case focused selection has
not supplied a terminal result yet.
New compatibility boundaries before correction: legacy `graph: null` without
reserved context was accepted by `90578033` and must remain an empty attribute
map through direct/combined/shared semantic loads. Present malformed reserved
context remains strict. Four existing watch refusal cases also expose a channel
regression: correct rejection/bytes use generic stdout instead of the established
RuntimeError/ValueError `error:` stderr path. Preserve all original assertions;
the narrow early error-handler restoration and exact before/final controls are
pending, without broad malformed-graph acceptance or diagnostic changes.
The final approved absence refinement expands the earlier null-only control to
all five exact old-owner forms: `null`, `false`, `0`, `[]` and `""`, each across
direct/combined/shared loading. Exact `90578033` installed behavior accepts all
fifteen with empty graph attrs and no context authority. Preserve `(graph or {})`
while keeping truthy unsupported scalars and every malformed present reserved
value strict. Final focused reserved/compatibility results are required after
the isolated one-line refinement; the earlier three-case null receipt is not
claimed as all fifteen controls.
The exact current before-control run reports **twelve failed, three passed,
91 deselected**, one warning, 2.09 seconds in `retention-falsy-before.xml`/`.log`;
the three passing cases are the already accepted null profiles. The exact
reviewed `90578033` installed owner accepts all fifteen. Final corrected focused
results remain pending after the approved one-line absence refinement.
The final test-only integrity addition covers absent reserved context plus
duplicate canonical placeholder records incident to a source-backed native node:
actual build/raw merge must reject with `QT_IMPORT_RETENTION_INVALID` and retain
prior bytes, then succeed after one duplicate is removed. Paired ordinary Python
duplicates preserve upstream generic behavior. These four cases close the
already implemented duplicate-native-candidate branch; no production change is
introduced. Exact final test identity/result and refreshed coverage are pending.

### First root-owned correction selection

The first 108-case root-owned selection reports **104 passed, three failed and
one real-symlink profile skipped** in 65.21 seconds. Native GraphML read-only
rejection/retry, DOM event-surface, paired memo, typed-ambiguity and exact
invariance admission/CLI-negative cases pass within that selection. The skipped
symlink case does not establish its acceptance profile.

Correct success-corpus admission now lets the original invariance assertions
execute. Three failures remain: raw unchanged rebuild loses top-level diagnostic
fields, and raw/clustered LF-versus-CRLF equality conflicts with native original-
byte spans and byte-derived site IDs. The latter requires a faithful correlated
semantic comparison plus independent original-byte span/identity validation;
blanket attribute removal or production newline normalization is not accepted.
Exact intended comparison and metadata correction are under investigation.
Preserve the original twelve invariance cases, their nontrivial graph guards,
non-native attributes and all meaningful source/consumer assertions. This is a
failed intermediate selection, not corrected-source or release acceptance.

### D34 newline-validation acceptance before correction

The read-only `invariance-analysis.log` compares 1,063 nodes per native newline
variant: 131 common-ID attribute changes reflect original-byte spans/source sizes
and include metadata; 57 native site IDs change (48 QML expression sites and
nine Qt fact sites), alongside hashed byte-derived owner/receiver tokens. No
general ID/hash remapper is accepted as an oracle.

Under [D34](../docs/qt-qml/ARCHITECTURE.md#d34--newline-invariance-respects-original-native-source-bytes),
all twelve aggregate cases keep full valid membership and exact graph IDs/
attributes. The CRLF copy preserves the complete owning `tests/fixtures/qml`
tree byte-for-byte and exactly converts every other text input. Required guards
check full copied membership, every preserved native byte, every other text's
exact transformation and both populations nonempty. No valid Qt/QML/project/
resource/QML-owned-JS input is excluded.

Planned `tests/test_native_newline_cli.py` runs the five-source native metadata
fixture through actual CLI LF/CRLF variants. Every native span, source size and
type position must match original input bytes. Require unique
`(source_file, label, type, source_location, family, kind)` anchors, the Backend
class/property/statusChanged and QML-binding facts, and equivalent semantic
roles/reference status/edge roles and direction through those fixture anchors.
Require byte-derived IDs to differ, with deliberate span/endpoint/role/relation
corruptions rejected by the oracle. Exact new test names/command/result remain
pending; product parsing and graph attributes are not normalized or filtered.

Independent existing original-byte protections remain mandatory:
`tests/test_qt_graph_persistence.py::test_native_repeated_sites_export_with_original_utf8_crlf_spans`,
`tests/test_cpp_qualified_identity.py::test_req_qml008_ac02_original_bom_crlf_unicode_spans_survive_qualified_member_join`
and `tests/test_qml_declarations.py::test_qml003_ac01_unicode_crlf_spans_and_original_names`.
Acceptance maps to REQ-QML-003-AC02/AC04, REQ-QML-010-AC01,
REQ-QML-011-AC01/AC04, REQ-QML-013-AC03 and REQ-QML-014-AC03/AC04.

### Bounded replacement, generator and Part A source checkpoints

The owned-copy source-first selection fails six cases before correction. Its
corrected `test_owned_readonly_replacement.py`, `test_atomic_replace_retention.py`
and `test_atomic_writes.py` selection passes **35 cases with three platform
skips** (`readonly-before`/`readonly-after` XML/logs under the ignored integration
evidence directory). Atomic/product rejection and raw byte/mode rollback remain
separate owners; skips are not native/POSIX symlink or mode acceptance.

`test_skillgen_interpreter_compatibility.py` passes **ten source-only cases** for
legacy/canonical PowerShell conversion, malformed input and counted exact
quote-only round-trip matching. Authoritative edits cover 105 executable heads
across eight command fragments plus three prose samples in nine Markdown inputs.
Shipped-resource `test_skillgen_interpreter_identity.py` has a faithful initial
**three failures and three controls** in six cases (`interpreter-runtime-before.xml`,
45.38 seconds); regenerated-resource execution remains pending. Compatibility
fingerprints admit only the corresponding canonical quoted forms of the two
existing sanctioned extra heads and the exact hardened-watch command, without
whole-line drift exemptions.

Part A/code-only fixture corrections pass **18 cases** in `skill-root-after.xml`:
the original incremental semantic assertions remain, the new no-marker rejection/
retention/recovery executes, and fourteen hosts plus actual body/cache-only
relocation preserve explicit root, nonempty IDs and portable `pkg/mod.py` source.
The earlier sixteen fixture failures remain recorded separately. No production
root/runtime fallback is added. Exact final names/commands and broader regenerated
resource/artifact/full-suite proof remain pending.

### Final bounded skill and owned-replacement source evidence

The source-tree regenerated-resource selection supersedes the pending transport
state above: **300 passed, 34 skipped, zero failures/errors**, 153.65 seconds,
in `skill-correction.xml`/`.log`. Each selected shipped resource is the current
source-tree package content; this is not a new installed-wheel result.

```powershell
.venv/Scripts/python.exe -X utf8 -m pytest -q -p no:cacheprovider --tb=short tests/test_skillgen_interpreter_identity.py tests/test_skillgen_interpreter_compatibility.py tests/test_skillgen.py tests/test_skillgen_input_path_injection.py tests/test_devin.py tests/test_query_fallback_edges.py tests/test_code_only_update_all_hosts.py tests/test_skill_code_only_incremental_update.py tests/test_skill_part_a_explicit_root.py tests/test_skill_no_backtick_substitution.py --junitxml=.venv/upstream-sync-0.9.92/skill-correction.xml
```

The process uses isolated `skill-correction.coverage`, `PYTHONUTF8=1` and the
admitted Git Bash tool directories in its process-local PATH.

| Module | Passed / skipped |
| --- | --- |
| `test_skillgen_interpreter_identity` | 6 / 0 |
| `test_skillgen_interpreter_compatibility` | 10 / 0 |
| `test_skillgen` | 67 / 0 |
| `test_skillgen_input_path_injection` | 27 / 3 |
| `test_devin` | 22 / 0 |
| `test_query_fallback_edges` | 9 / 0 |
| `test_code_only_update_all_hosts` | 9 / 0 |
| `test_skill_code_only_incremental_update` | 2 / 0 |
| `test_skill_part_a_explicit_root` | 16 / 0 |
| `test_skill_no_backtick_substitution` | 132 / 31 |

REQ-CORE-001-AC01 maps exactly to
`test_req_core001_ac01_every_shipped_head_quotes_the_recorded_identity`,
`test_req_core001_ac01_actual_shipped_statements_use_spaced_selected_interpreter`,
`test_req_core001_ac01_invalid_selected_interpreter_never_falls_back[missing/empty/failure]`
and `test_req_core001_ac01_shell_harness_detects_unquoted_selection` in the
identity module. They cover 483 emitted heads across 85 shipped resources,
actual Bash dispatch to a spaced selected interpreter, active split-prefix/PATH
decoys, no-fallback failure and a live quote-removal negative control. The
compatibility module's exact `test_req_core001_ac01_` functions are
`quoted_and_legacy_powershell_inputs_are_identical`,
`powershell_rejects_noncanonical_openers`,
`quote_pair_preserves_every_argument_and_count`,
`instructional_sample_pair_is_exact` and
`actual_monolith_roundtrip_rejects_extra_head_drift`.

All original code-only host/update/root/semantic-cache assertions remain; the
new missing-marker case and actual Part A/cache-only relocation pass. All 134
generated artifacts and validators match. The 34 skips are 31 POSIX-host-only
cases and three unavailable Bash-side Python-import cases, retaining their
unverified profile assignments. These source checks overlap earlier selections
and are not added into a release or full-suite total.

The separate owned-copy/atomic source selection remains **35 passed, three
platform skips**, with exact command:

```powershell
.venv/Scripts/python.exe -X utf8 -m pytest -q -p no:cacheprovider --tb=short tests/test_owned_readonly_replacement.py tests/test_atomic_replace_retention.py tests/test_atomic_writes.py --junitxml=.venv/upstream-sync-0.9.92/readonly-after.xml
```

It uses its isolated coverage file. REQ-CORE-001-AC03 maps to
`test_req_core001_ac03_owned_readonly_destination_replaces_without_orphans`
for both source-mode variants; REQ-QML-018-AC06 maps to
`test_req_qml018_ac06_cleanup_after_readonly_clear_restores_bytes_and_modes`
for source/backup cleanup and
`test_req_qml018_ac06_mode_restore_failure_retains_recovery_backup`, all in
`test_owned_readonly_replacement.py`. Retain existing atomic-product read-only
rejection, repair/retry, directory rejection and explicit platform gaps. The
six-failure source-first receipt remains separate negative evidence. New
artifact/install/full/hosted proof is still pending.

The initial D34 root selection passes **139 cases with one native-symlink skip**
and zero failures/errors in 63.37 seconds, including all twelve aggregate cases.
Its first dedicated newline oracle still admitted symmetric missing facts;
each-profile binding/property/signal/source-token and selected edge-metadata
checks plus symmetric-removal controls are required before final D34 acceptance.
This provisional count is not a release or completed-oracle claim.

## Post-905 bounded source release checkpoint

Status: **Corrections implemented; declared focused source profiles pass; next
frozen complete source, rebuilt wheel/install and hosted proof pending**. The
reviewed `90578033` wheel remains historical evidence for its own production
tree. These working-tree selections overlap and are not summed into a full-suite
or installed-artifact result. All seven documentation files must be frozen
before the next committed-source test wrapper snapshots its inputs.

### Retained context, preflight and current diagnostics

The final four-module selection passes **132 cases, zero failures/errors/skips**,
24 warnings, in 25.61 seconds (`retention-release-final.xml`/`.log`):

```powershell
& .venv/Scripts/python.exe -X utf8 -m pytest -q --disable-warnings -o addopts= tests/test_qt_import_retention.py tests/test_qt_import_retention_preflight.py tests/test_qt_import_retention_updates.py tests/test_qt_reconcile_diagnostics.py --junitxml=.venv/upstream-sync-0.9.92/retention-release-final.xml *> .venv/upstream-sync-0.9.92/retention-release-final.log
```

| Acceptance scope | Exact automated production boundaries |
| --- | --- |
| REQ-QML-010-AC04; REQ-QML-011-AC04; REQ-QML-012-AC02 | `test_qt_import_retention.py::test_graph_owned_retention_crosses_actual_build_merge_and_reload`, `test_policy_view_is_detached_and_role_transitions_are_producer_only`, `test_loader_captures_immutable_raw_policy_before_legacy_backfill`, `test_planner_ignores_irrelevant_untyped_records_without_granting_source_authority`; `test_qt_import_retention_updates.py::test_unproved_native_import_survives_last_qt_removal_and_real_proof_recovers` |
| REQ-QML-012-AC01/AC02/AC04; REQ-QML-018-AC06 | `test_qt_import_retention.py::test_corrupt_retention_transport_cannot_authorize_a_graph_write`, `test_json_rejection_precedes_accounting_and_preserves_existing_bytes`, `test_remaining_context_integrity_boundaries_reject_without_inference`, `test_exact_count_and_utf8_budgets_preserve_boundary_then_reject`, `test_policy_rejects_malformed_producer_boundaries_without_partial_acceptance`; `test_qt_import_retention_updates.py::test_retention_context_publication_failure_keeps_prior_cohort_and_retries`, `test_corrupt_retention_refuses_force_preserves_cohort_and_recovers` |
| REQ-QML-012-AC01/AC02; REQ-QML-011-AC04 | All four functions in `test_qt_import_retention_preflight.py`: `test_raw_loader_keeps_provenance_and_four_tuple_loader_compatibility`, `test_raw_loader_retains_missing_parse_and_size_cap_outcomes`, `test_watch_passes_single_raw_baseline_before_dispatch_without_borrowed_mutation`, `test_corrupt_context_never_dispatches_an_extractor_or_creates_cache` |
| REQ-QML-013-AC03; REQ-QML-014-AC03/AC04 | `test_qt_import_retention.py::test_semantic_loader_deferred_role_dependency_has_no_import_cycle`; `test_legacy_null_graph_without_reserved_context_remains_accepted` covers all five reserved-free forms across three boundaries, with its historical name retained |
| REQ-QML-010-AC01; REQ-QML-011-AC01/AC04; REQ-QML-012-AC01/AC02; REQ-QML-018-AC06 | `test_qt_reconcile_diagnostics.py::test_real_cold_and_warm_products_keep_current_empty_diagnostic_keys`, `test_current_source_diagnostics_replace_prior_graph_metadata_without_replay` |

All paths above are under `tests/`; parametrized variants retain their individual
JUnit identities. The twelve corruption/lifecycle cases now retain the complete
prior product/cache bytes and create no candidate AST cache before rejection.
The exact fifteen legacy-absence controls pass. Existing source-owned cleanup
assertions are preserved; canonical shape does not grant prior-import authority.

The final diagnostic regression text has an isolated faithful negative replay:
removing only the fresh-result copy yields **two failures**, two warnings,
3.07 seconds (`diagnostics-frozen-before.xml`/`.log`). An earlier one-fail/one-pass
fixture was too weak because unchanged bytes bypassed publication; the final
case makes a real AST edit and forces the persistence boundary. That weaker
checkpoint does not establish the final regression's negative proof.

Broader compatibility runs 383 cases: **376 passed, seven explicit platform
skips**, 291 warnings, 117.96 seconds (`retention-compatibility-final.xml`/`.log`):

```powershell
& .venv/Scripts/python.exe -X utf8 -m pytest -q --disable-warnings -o addopts= tests/test_watch.py tests/test_build_merge_shrink_guard.py tests/test_build_merge_hyperedges_and_prune.py tests/test_build_merge_dedup_scope.py tests/test_no_cluster_undeclared_endpoints.py tests/test_qt_cpp_file_role_updates.py tests/test_qml_cli_persistence.py tests/test_qml_watch_persistence.py tests/test_qt_product_publication.py tests/test_qt_readonly_publication.py tests/test_external_stub_endpoints.py tests/test_merge_sweeps_reextract_orphans.py tests/test_prune_sweeps_orphans.py --junitxml=.venv/upstream-sync-0.9.92/retention-compatibility-final.xml *> .venv/upstream-sync-0.9.92/retention-compatibility-final.log
```

This broader run precedes the isolated two-line legacy-falsy compatibility
refinement. The full strict reserved-context selection and fifteen exact
old-owner compatibility controls pass afterward in the 132-case selection;
the earlier broader result is not falsely rebound to the changed helper. Its
platform skips retain their exact receipt assignments and establish no passing
profile. Both commands isolate default pytest options and preserve root coverage.

An isolated branch-coverage repeat of the same 132 cases passes without skips
in 51.23 seconds (`retention-release-covered.xml`/`.log`). It executes
`coverage run --branch --source=graphify.qt_import_retention -m pytest` with the
same four modules/options, isolated `retention-release.coverage`, then writes
`retention-release-coverage.json`. At that checkpoint the helper covers 95/97
statements and 51/52 branches (about 98%); defensive Unicode-encoding failure and
duplicate-native-candidate refusal remain uncovered. A final test-only duplicate
closure is recorded separately; do not treat the earlier percentage as refreshed
after those cases. The pre-existing root coverage file stays unchanged.

### D34 and export/source-byte proof

The strengthened native LF/CRLF selection passes **eight cases without skips**
in 3.93 seconds (`native-strengthened.xml`/`.log`):

```powershell
.venv/Scripts/python.exe -X utf8 -m pytest tests/test_native_newline_cli.py -q --tb=short --junitxml=.venv/upstream-sync-0.9.92/native-strengthened.xml
```

`test_req_qml003_ac04_native_newlines_keep_cli_roles_and_topology` and seven
`test_req_qml014_ac04_native_newline_oracle_rejects_corruption` variants check
original bytes, mandatory each-profile facts, unique semantic anchors and
span/consistent-span/endpoint/node-role/relation/edge-role/symmetric-binding-
omission controls. Independent replay rejects the same three saved corruptions
that the first oracle accepted. The QML read explicitly remains ambiguous with
`duplicate_provider` under simultaneous CMake/qmake declarations; no confident
provider or runtime Qt execution is inferred.

The earlier 139-pass/one-symlink-skip source selection includes all twelve original
aggregate invariance cases, admission/newline-byte guards, native CLI and GraphML,
paired memo, typed-path, emitted-viewer and three existing native CRLF modules.
Its symlink skip remains a system gap. Exact added acceptance guards are
`test_graph_invariance_admission.py::test_req_qml014_ac03_invariance_omits_only_two_rejection_fixtures`,
`test_req_qml014_ac03_newline_profile_keeps_native_bytes_and_converts_other_text`
and both `test_req_qml012_ac02_force_still_rejects_invalid_invariance_input`
variants. `test_graphml_owned_replacement.py` retains native read-only rejection/
repair/repeat, serialization/replacement failure, directory refusal and the
separately skipped real-symlink target-protection case. No original graph-ID/
attribute assertion is globally filtered, and production bytes are unchanged.

### Final static and delivery boundaries before commit

Whole Ruff and whitespace pass. The final explicit-interpreter Pyright run
reports **651 errors across 834 files**; source-anchor/message comparison retains
all 651 `90578033` diagnostics with **zero added and zero removed**
(`pyright-final-source.json`, `pyright-final-comparison.json`). Focused new
production/test owners pass their declared checks. Whole typing remains failed;
neither the invalid implicit-interpreter profile nor preliminary unfixed
test-narrowing diagnostics establishes a product regression or a green type gate.

All runtime/test/tool sources are released and frozen for the next source commit.
The final repository AST refresh, reviewed raw-blob wheel/installed-origin proof,
complete committed-source suite and hosted/merged-SHA checks are pending. Earlier
source-tree resource tests and the `90578033` artifact cannot stand in for those
new-revision gates. The active per-user tool and application graph remain intact.

### Final test-only duplicate-context closure

`test_qt_import_retention.py::test_implicit_duplicate_native_candidate_rejects_and_repaired_merge_retries`
passes all **four** C++/Python × build/raw variants, zero skips, 106 deselected,
one warning, 1.43 seconds (`retention-implicit-duplicate-final.xml`/`.log`):

```powershell
& .venv/Scripts/python.exe -X utf8 -m pytest -q --disable-warnings -o addopts= tests/test_qt_import_retention.py -k implicit_duplicate_native --junitxml=.venv/upstream-sync-0.9.92/retention-implicit-duplicate-final.xml
```

With reserved context absent, duplicate native candidates reject safely while
retaining prior bytes and recover after duplicate removal; ordinary Python
duplicates retain upstream acceptance. This tests the existing implementation
without a production change. The module is 299 physical lines and passes focused
Ruff and explicit-interpreter Pyright with zero errors. The whole-project
651-diagnostic comparison precedes this last test-only addition; its focused
check is separate. The 132-case and four-case receipts are not presented as one
aggregate 136-case execution. The earlier coverage percentage is not refreshed
by assertion, although this new control exercises the missing duplicate branch.

All source, tests, tools and seven documentation files are now released for the
next source commit. No further document edits occur during its frozen complete
test run. New source/wheel/install/full/hosted proof remains pending.

## Committed corrected integration checkpoint — 67bb2022

Status: **Complete local source suite and isolated installed profiles pass, with
explicit skips; the later final native gate also passes locally. New hosted/
review/merge gates remain separate**. This checkpoint supersedes the local source/artifact gaps recorded
above for its exact corrected inputs. It preserves the historical source905
failure and does not extend older hosted acceptance to the new revision.

| Identity | Recorded value |
| --- | --- |
| Source commit | `67bb20222bf4afe63b6fd799f8a2a6e2e982784e` |
| Production tree | `788fef0be4cba271626db048c6ce6d49a504330c` |
| Wheel SHA256 | `9221dc9679dd890c2413f310c395aa7fc5dd94833e94b9bb71cc4b285484cfb9` |
| Package/cache policy | 0.9.92; AST schema 18; Qt policy 25 |
| Raw-source package proof | All 327 shipped Graphify files match reviewed Git blobs; copied public test bytes are retained |

### Complete corrected source run

The actual Windows source run collects **11,949 cases: 11,776 passed, 173
skipped, zero failures and zero errors**, with 3,879 warnings. Pytest completes
in 1,913.68 seconds; the wrapper takes 1,917.58 seconds. Both exit 0. All four
integrity flags are true: HEAD unchanged, tracked inputs unchanged, original
coverage bytes unchanged and installed dependencies unchanged. All tracked
source/test/tool/workflow/document inputs remain clean at terminal capture.

Exact executed outer command:

```powershell
& .venv/Scripts/python.exe .venv/upstream-sync-0.9.92-final/run_full_source.py 67bb20222bf4afe63b6fd799f8a2a6e2e982784e *> .venv/upstream-sync-0.9.92-final/full-runner.log
```

The retained helper/receipt records the actual child invocation of
`python -X utf8 -m pytest tests/ -q --tb=short -rs`, its JUnit output, reviewed
wheel input, process-local admitted Git Bash tools, isolated coverage file and
disabled automatic refresh/tips. No shell/dependency fallback or skip-to-pass
conversion supplies acceptance. Safe receipt paths beneath
`.venv/upstream-sync-0.9.92-final/` are `full-source-receipt.json`,
`full-source.xml`, `full-source.log`, `full-runner.log` and
`full-source-crosscheck.json`. These ignored local receipts are revision-bound
evidence, not hosted artifacts.

The crosscheck finds **all 56 prior source905 failure/error identities present
and passing**; none is removed. All 172 old skipped identities remain skipped.
The additional skip is the new GraphML real-symlink case whose creation requires
unavailable host privilege. There are 175 new case identities. The sole removed
old identity is the raw-helper `[replace]` variant of
`test_req_qml018_ac06_readonly_rejects_without_displacing_destination`, explicitly
superseded by D32's owning-output policy. Its text/JSON guarded variants remain,
and the original upstream
`test_os_replace_with_fallback_still_replaces_a_readonly_destination` passes.
This is the documented contract reconciliation, not removal of one of the
56 failing identities to obtain a passing result.

| Remaining skip assignment | Cases |
| --- | --- |
| Windows symlink capability or POSIX physical-link traversal | 89 |
| POSIX shell execution profile | 65 |
| Optional native/compiler profile | 5 |
| POSIX IPC profile | 3 |
| Optional Redis integration | 2 |
| Windows active-CWD restriction | 2 |
| POSIX filesystem permissions | 2 |
| POSIX lock race, POSIX device, Windows Git-specific, legacy bundle fallback and stdlib fallback | One each |

Every exact case/reason is retained in the receipt/crosscheck. These assignments
are not passing acceptance, and this Windows run does not establish fresh
Linux/macOS, live-service, Qt runtime or native-device execution.

### Source-matched isolated installed profiles

The original isolated profile executes **716 cases in 32 modules: 715 passed,
one skipped, zero failures/errors**, 119 warnings, 171.60 seconds. Its 71 runtime/
test distributions remain unchanged and compatible; all 171 loaded Graphify
module origins are the isolated installation. All 327 package bytes and copied
public tests match before and after. The only skip is
`test_graphml_owned_replacement.py::test_req_qml018_ac06_graphml_replaces_link_without_changing_target`;
real symlink creation is unavailable. It does not verify target protection.

```powershell
.venv/upstream-sync-0.9.92-final/stage/Scripts/python.exe -I .venv/upstream-sync-0.9.92-final/run_stage.py
```

The installed run includes the earlier 21-module/495-case compatibility
selection, plus 42 existing C++ role-update cases, all **136** retained-context/
preflight/update/diagnostic cases, 15 atomic-retention cases, five owned-copy
cases, five GraphML cases, six actual shipped-interpreter cases, four invariance
admission cases and eight native LF/CRLF cases. This is an actually executed
installed 136-case subset; the earlier source132 and source4 receipts remain
separate historical executions. No new aggregation is inferred from them.

An independent isolated probe uses a real OS-temporary working directory outside
the checkout, verifies installed module origins and invokes actual
`python -I -m graphify --help` successfully. `uv pip check` accepts all 71
distributions. `stage-receipt.json`, `stage-tests.xml`/`.log`,
`runtime-outside-probe.json` and `stage-uv-check.log` retain those outcomes.

A **separate HCL add-on profile** installs only the locked
`tree-sitter-hcl==1.2.0` offline with `--no-deps`. The exact dependency delta is
71 to 72 distributions with no removals or changed versions; dependency checking
passes. Its six `test_upstream_qt_refresh_order.py` cases pass without skips,
failures or errors in 3.58 seconds, with seven warnings. All 159 loaded Graphify
origins remain installed, package/test bytes remain identical and the original
71-distribution receipt remains unchanged.

```powershell
.venv/upstream-sync-0.9.92-final/stage/Scripts/python.exe -I .venv/upstream-sync-0.9.92-final/run_stage_addon.py
```

The add-on install, dependency checks and run are retained as
`stage-hcl-install.log`, `stage-addon-uv-check.log`, `stage-addon-tests.xml`/`.log`
and `stage-addon-receipt.json`. The two environments are distinct; 715 plus six
is not claimed as one executed aggregate. Neither profile changes the active
per-user Graphify tool or an application graph.

### Acceptance mapping and remaining delivery gates

| Acceptance IDs | Actual corrected local evidence and explicit boundary |
| --- | --- |
| REQ-QML-001-AC01–AC04; REQ-QML-002-AC01–AC04; REQ-QML-003-AC01–AC04; REQ-QML-009-AC01–AC04; REQ-QML-016-AC01–AC04; REQ-QML-017-AC01–AC04 | Complete source discovery includes all applicable existing producer/span/scope/rejection regressions. The installed 21-module subset repeats its declared CMake/state/cache/cohort/override/query fixtures. Declared platform, SDK/runtime and unavailable-parser profiles retain their individual limits. |
| REQ-QML-010-AC04; REQ-QML-011-AC04; REQ-QML-012-AC01/AC02/AC04; REQ-QML-013-AC03; REQ-QML-018-AC06 | `test_qt_cpp_file_role_updates.py` original prior-import proof rejection cases and `test_qt_import_retention.py`, `_updates.py`, `_preflight.py`, `test_qt_reconcile_diagnostics.py` all pass in complete source and assigned installed selections. Exact mappings/negative controls above remain authoritative; malformed context rejects before cache writes and real failure/repaired retry retain graph/context. |
| REQ-CORE-001-AC03; REQ-QML-012-AC02; REQ-QML-018-AC06 | `test_owned_readonly_replacement.py`, `test_atomic_replace_retention.py` and original `test_atomic_writes.py::test_os_replace_with_fallback_still_replaces_a_readonly_destination` pass on source67. Guarded `test_write_text_atomic_refuses_a_readonly_destination_without_leaking_a_temp` also passes; raw caller ownership cannot override graph/product rejection policy. |
| REQ-QML-013-AC03; REQ-QML-018-AC06 | `test_graphml_owned_replacement.py` read-only/repaired retry, failed write and directory controls pass on source67 and installed wheel. The actual symlink case remains explicitly skipped and separately assigned. |
| REQ-CORE-001-AC01; REQ-QML-014-AC03/AC04 | All six `test_skillgen_interpreter_identity.py` shipped-resource cases pass on source67 and installed wheel; strict source conversion/Part A/all-host regressions pass where applicable in the complete source run. Source67 proof does not imply future native hosted selection. |
| REQ-QML-003-AC02/AC04; REQ-QML-010-AC01; REQ-QML-013-AC03; REQ-QML-014-AC02/AC03/AC04 | All twelve original aggregate invariance cases and four admission controls pass in the complete source suite. Both source and installed `test_native_newline_cli.py` actual CLI case plus seven corruption controls pass, preserving duplicate-provider uncertainty and original-byte authority. |
| REQ-QML-018-AC04; REQ-QML-013-AC01; REQ-QML-014-AC03/AC04 | `test_upstream_qt_path_integration.py::test_req_qml_018_ac04_duplicate_qualified_target_refuses_guess` passes with the current typed ambiguity exit3; candidate identities, exact-ID route and graph nonmutation assertions remain intact. |
| REQ-QML-014-AC01–AC04; REQ-QML-015-AC01–AC04; REQ-CORE-004-AC01–AC04 | Source67/full and isolated artifacts have exact local identities and retention checks. The later seven-module native CI gate passes 76 cases with four platform skips/all 29 critical cases passing. Hosted source/native/wheel/service/upload evidence, review/merge and actual merged-SHA proof remain pending. Historical hosted results retain their revision. |

Whole Ruff, generator checks for all 134 artifacts and whitespace pass for the
frozen source. Whole explicit-interpreter Pyright remains failed with **651
diagnostics across 834 files**, all source905 anchors/messages retained, zero
added/removed. That comparison precedes the final four-case test-only addition,
whose targeted Ruff/Pyright checks pass separately. Neither total source passes
nor scoped typing relabels the whole type gate as passing.

### Native CI coverage correction: preimplementation evidence

Status: **Implemented and locally verified; final native gate passes 76 cases
with four platform skips/all 29 critical cases passing; hosted proof pending**,
using existing REQ-CORE-004-AC02/AC03 and the
[native coverage matrix](../docs/qt-qml/PLAN.md#native-ci-coverage-correction-acceptance-before-implementation).
The frozen workflow's 34 unique literal Windows selections omit
`test_atomic_writes.py`, `test_atomic_replace_retention.py`,
`test_owned_readonly_replacement.py`, `test_graphml_owned_replacement.py`,
`test_skillgen_interpreter_identity.py` and `test_native_newline_cli.py`.
Private before evidence `windows-selection-before.json` confirms actual
PowerShell5.1 and pwsh7 evaluate the same ordered inventory. That read-only
observation demonstrates the omission, not hosted native acceptance.

The existing `test_ci_windows_tools.py` owner covers portable exact-array
inventory, invalid/comment/dynamic/duplicate/missing selection controls and
actual PowerShell array agreement. Its native fixture keeps the five current
tool tests native-only while the portable guard runs on Ubuntu. The existing
integrity step requires 29 exact passing critical case identities, including
original owned-copy/guarded writer cases, and write native-case/integrity reports
before combined rejection. Actual failure-tail controls preserve evidence
and failure exit. The final bounded native result is recorded below.

No runtime/package source changes, new job/dependency/trigger/permission or new
increment belong to this follow-up. The later CI/test/docs head needs its own
native and hosted evidence. The passing source67 full run is not renamed as
having executed the changed workflow or new guard; publication uses normal PR
validation without a duplicate full dispatch.

### Local CI guard result before combined native execution

The acceptance matrix and REQ-CORE-004-AC02/AC03 refinement were saved before
implementation. The actual inventory guard first fails against the original
34-entry workflow, naming exactly the six missing modules: **one expected
failure**, 1.04 seconds (`ci-guard-before.xml`). After the bounded workflow
correction, the existing guard module passes **23 cases without skips,
failures or errors** in 14.08 seconds (receipt wrapper 15.03 seconds):

```powershell
.venv/Scripts/python.exe -X utf8 -m pytest tests/test_ci_windows_tools.py::test_req_core004_ac02_actual_windows_inventory_covers_native_regressions -q --tb=short -p no:cacheprovider --junitxml=.venv/upstream-sync-0.9.92-final/ci-guard-before.xml
.venv/Scripts/python.exe -X utf8 -m pytest tests/test_ci_windows_tools.py -q --tb=short -p no:cacheprovider -rs --junitxml=.venv/upstream-sync-0.9.92-final/ci-guard-after.xml
```

| Acceptance ID | Exact guard and observable outcome |
| --- | --- |
| REQ-CORE-004-AC02 | `test_req_core004_ac02_actual_windows_inventory_covers_native_regressions` admits the actual 40-entry literal Windows array, preserving the original 34 entries in order and requiring all six additions. |
| REQ-CORE-004-AC03 | Six `test_req_core004_ac03_selection_rejects_omissions_and_nonliteral_tokens` mutations reject omissions and duplicate/malformed/dynamic tokens. The final strengthened versions also reject quoted comment decoys, as recorded below. |
| REQ-CORE-004-AC02 | `test_req_core004_ac02_native_array_execution_matches_portable_inventory` executes the actual admitted assignment in real PowerShell and compares exact ordered output. |
| REQ-CORE-004-AC03 | Eight `test_req_core004_ac03_actual_junit_proof_requires_each_native_case` profiles execute the actual workflow Python audit against valid/missing/duplicate/failed/skipped evidence, requiring all 29 critical native identities. |
| REQ-CORE-004-AC03 | Two `test_req_core004_ac03_native_audit_retains_integrity_when_case_proof_rejects` profiles execute the real PowerShell tail and retain native-case/integrity artifacts before failure. |

All five existing actual application/tool cases remain collected and pass.
Complete PowerShell step syntax parses under actual 5.1 and 7; the native test
fixture's executed engine is distinguished from outer workflow `pwsh` execution.
YAML parsing and structural comparison confirm other jobs and top-level policy
unchanged. The workflow measures 582 lines under its documented 600-line
cohesion ceiling; the existing test measures 286, below 300. Focused Ruff passes
and explicit-interpreter Pyright reports zero errors. HEAD, both owned inputs,
dependencies and original coverage remain unchanged during the 23-case run.
`ci-guard-receipt.json`, `ci-guard-structure.json` and the before/after XML/log
files retain exact input digests and outcomes.

This is local proof of the saved two-file follow-up while HEAD is still
`67bb2022`; the changed workflow/test are not part of the source67 full run.
The final seven-module rerun below supplies combined native execution with the
strengthened guard; the earlier standalone receipt remains historical. Normal
hosted validation of the later committed head, artifact
upload and eventual merged-SHA proof remain pending. No package rebuild or
source-full rerun is implied solely by this workflow/test/docs correction.

### Final strengthened native CI gate

Status: **Locally verified for the bounded native profile; new hosted proof
pending**. The final existing omission controls leave the exact omitted module
token quoted on a comment line before the array closes. Both `omit` and
`omit_guard` still reject; this strengthens comment-only false-inclusion
coverage without adding cases, changing the workflow or changing product code.
The final guard has 287 physical lines and all 23 cases pass in this combined
run. The earlier standalone 23-case/286-line receipt remains historical.

The actual six added product modules plus existing guard execute **80 cases:
76 passed, four skipped, zero failures/errors**, with one warning. Pytest takes
63.54 seconds; the wrapper takes 64.89 seconds and exits successfully. The
native-case report confirms **all 29 exact critical identities present and
passing**, with no required case skipped. HEAD, tracked working inputs, original
coverage and dependencies remain unchanged during the run.

Exact executed child command, with repository-relative paths:

```powershell
.venv/Scripts/python.exe -X utf8 -m pytest tests/test_atomic_writes.py tests/test_atomic_replace_retention.py tests/test_owned_readonly_replacement.py tests/test_graphml_owned_replacement.py tests/test_skillgen_interpreter_identity.py tests/test_native_newline_cli.py tests/test_ci_windows_tools.py -q --tb=short -p no:cacheprovider -rs --junitxml=.venv/upstream-sync-0.9.92-final/ci-native-gate-nixumx7c/tests.xml
```

The owning helper selects these seven from the actual 40-entry workflow array,
uses its admitted native tool profile and audits the individual JUnit outcomes.
Node reports 24.19.0 and outer PowerShell reports 7.6.7; the actual-array test's
Windows PowerShell fixture is separate evidence. This is not execution of the
whole 40-entry job, all source tests or a hosted runner.

| Exact noncritical skipped identity | Remaining assignment |
| --- | --- |
| `test_atomic_writes.py::test_write_text_atomic_preserves_existing_mode` | POSIX mode-bit equality is inapplicable to Windows read-only attributes. |
| `test_atomic_writes.py::test_write_text_atomic_writes_through_symlink` | Actual host symlink-creation capability unavailable. |
| `test_atomic_writes.py::test_os_replace_with_fallback_replaces_a_symlink_destination_in_place` | Existing fixture assigns different Windows symlink setup to its separate platform profile. |
| `test_graphml_owned_replacement.py::test_req_qml018_ac06_graphml_replaces_link_without_changing_target` | Actual symlink creation unavailable for this platform/account. |

None of these four exclusions is a passing native acceptance result. The 29
required identities include both original raw owned-copy and guarded atomic
read-only cases, four atomic-retention cases, five owned-copy cases, four
GraphML rejection/failure/retry cases, six actual shipped-interpreter cases and
eight native LF/CRLF cases. Exact identities and outcomes remain reviewable in
`tests.xml`; `native-cases.json` records the aggregate verdict against the
workflow's explicit required-case inventory. All earlier guard mappings above
execute in the final run.
Real PowerShell failure-tail controls retain native-case/integrity reports
before rejection, and literal-comment controls cannot fake module inclusion.

Final receipts beneath
`.venv/upstream-sync-0.9.92-final/ci-native-gate-nixumx7c/` are `receipt.json`,
`tests.xml`, `tests.log`, `native-cases.json`, `selection.json`,
`shell-consumers.json` and `dependency-check.log`. The receipt records exact
working-input digests. HEAD remains source67 and the production tree remains
`788fef0b`; the intentional later workflow/test/docs diff is separate from the
clean source67 full-suite inputs. Preservation here means those saved working
inputs did not change during execution, not that the new guard belonged to the
source67 commit. No runtime/package or active-tool/application change occurs.

The workflow remains 582 lines under its 600-line cohesion allowance and the
guard remains below 300. The final AST-only repository refresh succeeds with
27,243 nodes and 63,884 edges, 48 uncached inputs, one known partial Luau fixture
and 26 no-symbol inputs (`graph-update-final-ci.log`). No API/LLM work, per-user
tool or application graph refresh occurs. Whole Ruff passes on the final guard;
production source remains unchanged. Final documentation checks precede the
owning follow-up commit and normal PR publication. Fresh hosted head/base/
checkout/service/artifact-upload evidence, required reviews, authorized merge
and exact merged-SHA validation remain outstanding. Whole Pyright retains its
651-diagnostic baseline; these native passes do not close platform/service,
runtime Qt, native-browser/device or application-adoption gaps.

## Native Terraform test-profile admission — INC-QML-55

Status: **Implemented; focused launcher and real installed recovery pass locally;
new head/full hosted proof pending**. Existing REQ-QML-001-AC01/AC03,
REQ-QML-014-AC01/AC03/AC04, REQ-QML-018-AC05 and
REQ-CORE-004-AC02/AC03 own this test-profile correction; delivery remains under
REQ-QML-015-AC01/AC03/AC04. Requirements and the
[increment matrix](../docs/qt-qml/PLAN.md#inc-qml-55--admit-native-terraform-test-dependencies-after-clean-smokes)
were saved before implementation. Product source/packaging is unchanged.

### Failed hosted source `5876f0a4` checkpoint

[QML run39486749962](https://github.com/SlinkyRamey/graphify/actions/runs/39486749962),
attempt1, is a `pull_request` run for head
`5876f0a407467768e37047ac7afb47a1470a5d19`, base
`82a4f296446b4cc219ffecfe3345a037e9c362e4`. Completed Ubuntu/Windows logs identify
actual synthetic checkout `0cc6ec84c203065effde3df2d33edcacc8b2dcb0` with those
parents. Four Ubuntu artifact-only lanes pass their three artifact tests and
both clean installed smokes. Each of four Windows source lanes passes the same
clean smokes but reports **2,960 passed, 19 skipped and two failures**:
`test_upstream_qt_refresh_order.py::test_req_qml011_ac03_terraform_and_filename_work_reach_joint_closure[terraform]`
and `[filename]`. Missing optional HCL reaches the retained failed-source
assertion; the core/QML package smokes are not the failing boundary.

Four macOS lanes cancel without an acquired runner or steps. Their check
annotations report hosted-runner acquisition/arm64 capacity constraints;
they supply no macOS parser, checkout or test evidence. This is not a proven
product failure or passing lane. This workflow defines no artifact upload
(API artifact count0); raw job logs/check annotations are retained locally as
`hosted-recovery/qml-terminal.json` and related evidence. These old results stay
failed/cancelled after a local correction and do not verify a new head.

### Launcher ordering and failure coverage

All tests execute real `tests.qml_ci.main`/`run`, isolating only subprocess
execution, using a real neutral temporary directory and a single public wheel
fixture. `tests/test_qml_ci_profiles.py` maps:

| Acceptance IDs | Exact automated test |
| --- | --- |
| REQ-QML-001-AC01/AC03; REQ-QML-014-AC01; REQ-QML-018-AC05; REQ-CORE-004-AC02 | `test_req_core004_ac02_native_profile_adds_terraform_after_clean_wheel_smokes` checks original installs, both clean smokes, exact same-wheel Terraform admission into only the extra environment, then source pytest. |
| REQ-QML-001-AC01/AC03; REQ-QML-014-AC01/AC04 | `test_req_core004_ac02_artifact_profile_preserves_clean_optional_boundaries` keeps artifact-only selection and excludes the add-on. |
| REQ-QML-014-AC01/AC04; REQ-CORE-004-AC03 | `test_req_core004_ac03_failed_addon_stops_before_native_pytest` rejects install failure before pytest without fallback. |
| REQ-QML-001-AC01/AC03; REQ-QML-014-AC01/AC04; REQ-CORE-004-AC03 | Both `[qml]`/`[core]` variants of `test_req_core004_ac03_failed_clean_smoke_cannot_admit_native_addon` stop before admission/pytest. |

The old launcher produces **two failures/three controls**, zero skips, 1.01
seconds; corrected launcher produces **five passes**, zero skips, 1.12 seconds:

```powershell
.venv/Scripts/python.exe -X utf8 -m pytest tests/test_qml_ci_profiles.py -q --tb=short -p no:cacheprovider --junitxml=.venv/upstream-sync-0.9.92-final/hosted-recovery/qml-launcher-before.xml
.venv/Scripts/python.exe -X utf8 -m pytest tests/test_qml_ci_profiles.py -q --tb=short -p no:cacheprovider --junitxml=.venv/upstream-sync-0.9.92-final/hosted-recovery/qml-launcher-after.xml
```

`qml-launcher-receipt.json` binds exact inputs and original coverage retention.
Launcher/test sizes are 53/135 physical lines; focused Ruff and explicit-
interpreter Pyright pass. These controls prove ordering/failure transport, not
actual package installation by their isolated subprocess boundary.

### Real installed absence and recovery

The fresh reviewed 0.9.92 QML/watch/pytest/packaging environment has 40
distributions, no HCL and a successful neutral `-I` installed-QML smoke. Running
the exact joint-closure selector above fails both cases (exit1), three warnings,
3.06 seconds. Admitting **the same built wheel's `[terraform]` extra offline**
adds only `tree-sitter-hcl==1.2.0`: forty to forty-one distributions, no removed
or changed versions. The exact same two cases then pass (exit0), five warnings,
3.28 seconds. This is real optional-dependency recovery, not a parser mock.

```powershell
.venv/upstream-sync-0.9.92-final/native-qml-hcl-repro/Scripts/python.exe -X utf8 -m pytest tests/test_upstream_qt_refresh_order.py::test_req_qml011_ac03_terraform_and_filename_work_reach_joint_closure -q --tb=short -p no:cacheprovider --junitxml=.venv/upstream-sync-0.9.92-final/hosted-recovery/root-hcl-before.xml
.venv/upstream-sync-0.9.92-final/native-qml-hcl-repro/Scripts/python.exe -X utf8 -m pytest tests/test_upstream_qt_refresh_order.py::test_req_qml011_ac03_terraform_and_filename_work_reach_joint_closure -q --tb=short -p no:cacheprovider --junitxml=.venv/upstream-sync-0.9.92-final/hosted-recovery/root-hcl-after.xml
```

Exact install/selection/dependency evidence is retained in
`root-hcl-before.json`, `root-hcl-after.json`, `root-hcl-reproduction-summary.json`,
their XML/logs, smoke log and before/after dependency lists beneath
`hosted-recovery/`. The earlier source `67bb2022`, installed 715-case and separate six-case add-on profiles remain
separate. New-head full native/hosted execution and missing macOS capacity proof
remain unverified; no active-tool/application or security-baseline remediation
is included.

## Native byte-owner and source-case validation — INC-QML-56

Status: **Implemented; final combined local selection passes 79 cases without
skips, with a separate twelve-case committed-LF aggregate pass; new hosted proof
pending**. Requirements/matrix preceded implementation. Three
completed Linux Python3.12/3.13/3.14 source `5876f0a4` lanes each collect 11,962 cases:
**11,826 passed, 134 skipped and two strict line-ending failures**, raw and
clustered. Python3.10 is cancelled without JUnit; its lack of test evidence is
explicit. Service-cleanup evidence is separately confirmed for all four jobs;
it cannot override failed/missing tests.

The failures preserve a meaningful original-byte contract. Committed generic
C++ fixture bytes outside the QML tree are LF; the local Windows checkout's
CRLF conversion masks the Linux fixture mismatch. Source-size/end-byte metadata
changes when those byte owners are transformed. At that checkpoint the existing
source gate retained an obsolete six-case cache expectation while all fourteen
current cache cases passed. Other source/dependency/checkout and service-cleanup checks do not convert
that evidence mismatch or the two pytest failures to acceptance.

| Acceptance IDs | Exact regression owner and evidence |
| --- | --- |
| REQ-QML-003-AC02/AC04; REQ-QML-010-AC01; REQ-QML-013-AC03; REQ-QML-014-AC02/AC03/AC04 | `test_graph_invariance.py` plus `test_graph_invariance_admission.py::test_req_qml014_ac03_native_copy_ownership_does_not_depend_on_location` uses sixteen forced-LF public inputs and exact outside Python/JS/MJS conversion/membership controls. `test_req_qml014_ac03_script_byte_owners_remain_inside_declared_fixture_cohort` and `test_req_qml014_ac03_script_fixture_escape_requires_profile_review[.js/.mjs]` protect script admission. All 23 admission cases and all twelve separate aggregate cases pass; every original graph assertion remains. |
| REQ-QML-003-AC02/AC04; REQ-QML-013-AC03; REQ-QML-014-AC02/AC03/AC04; REQ-QML-018-AC02 | `test_qt_native_cpp_newline_cli.py::test_req_qml003_ac04_non_qt_cpp_cli_newlines_keep_source_ownership_and_topology` exercises real generic C++ include/header spans, source sizes, include endpoints and emitted coordinates. `test_req_qml014_ac04_non_qt_cpp_newline_oracle_rejects_corruption` rejects span/consistent-span/source-size/include/definition-span/endpoint/role/member-omission/identity-permutation corruption. All ten pass. The separate existing eight-case `test_native_newline_cli.py` retains Qt API type-position coverage. |
| REQ-CORE-004-AC01/AC03; REQ-QML-014-AC03/AC04; REQ-QML-015-AC01/AC03 | `test_ci_source_cases.py::test_req_qml014_ac04_source_gate_accepts_every_collected_joint_case` compares real pytest collection of 42 assigned identities against the actual inline gate: cache 14/discovery 11/export 10/path 3/shared 4. |
| REQ-CORE-004-AC03; REQ-QML-014-AC04 | Eight `test_req_qml014_ac04_source_gate_rejects_incomplete_or_failed_case` variants reject omission/duplicate/same-count duplicate/foreign-name/skip/failure/error/foreign-module evidence. `test_req_qml014_ac04_source_gate_rejects_unreviewed_matrix_growth` rejects unreviewed assigned-module growth. All ten controls pass locally; new hosted proof remains pending. |

The implemented oracle requires exact
unique semantic-anchor-to-stable-ID ownership; consistent ID permutation cannot
pass solely through set/anchor equivalence. Before/after controls use the saved
real CLI graphs. The aggregate profile retains the existing QML-owned JS/MJS
cohort but converts ordinary outside scripts; the fixture-growth guard rejects
actual QML/script imports escaping that cohort instead of silently omitting
sources or deriving fixture admission from produced graphs. The saved actual
CLI graph probe accepts the consistent ID permutation before strengthening and
rejects it afterward, without rerunning the CLI or analyzed C++ in that probe.

Fixture inventory refinement: the real aggregate's only literal QML script
reference names an intentionally absent helper; no existing accepted QML-owned
JS/MJS fixture is present. An intermediate forty-one-case focused run has forty
passes and one failure because its new guard incorrectly requires an existing
accepted script target. The corrected test-only premise requires nonempty actual
QML/literal-reference inspection. Synthetic valid/transitive-escape JS/MJS cases
exercise ownership, and each forced-LF copy case checks outside
ordinary JS/MJS conversion. This discrepancy is not valid product-negative
evidence and does not justify weakening an original production assertion.

The [INC-QML-56 matrix](../docs/qt-qml/PLAN.md#inc-qml-56--preserve-native-byte-owners-and-current-source-case-evidence)
defines ownership before edits. Native fixture/oracle results now pass locally;
new-head hosted outcomes remain pending. No production normalization,
attribute exclusions, removed valid input, parser/schema policy change or
security-advisory waiver is authorized.

The initial eight-case gate regression produces **one failure/seven controls**
in 4.97 seconds against the old 34-case expectation. After exact-identity
correction and the additional same-count/foreign controls, the ten-case version
passes in 4.55 seconds:

```powershell
.venv/Scripts/python.exe -X utf8 -m pytest tests/test_ci_source_cases.py -q --tb=short -p no:cacheprovider --junitxml=.venv/upstream-sync-0.9.92-final/hosted-recovery/root-source-gate-before.xml
.venv/Scripts/python.exe -X utf8 -m pytest tests/test_ci_source_cases.py -q --tb=short -p no:cacheprovider --junitxml=.venv/upstream-sync-0.9.92-final/hosted-recovery/root-source-gate-after.xml
```

The test executes the actual inline block against real pytest collection; it
does not implement another evidence policy. New test size is 112 lines and the
workflow is 632 lines under its 650-line scoped allowance. Focused Ruff and explicit-
interpreter Pyright pass. Separately, existing Windows guards plus the launcher
controls pass 28 cases in 21.65 seconds; neither selection proves a complete new
source suite or hosted matrix. No source/dependency/trigger/permission change
is made by the exact-case correction.

### Final local INC-QML-55/56 handoff

The copy regression first records fifteen failures and one preserved-byte
control across sixteen cases. The final native selection passes **41 cases,
zero skips/failures/errors**, one warning, in **11.39 seconds**: 23 admission,
ten generic C++ and eight existing Qt cases. Initial generic C++ controls pass
nine cases before the independent consistent-ID-permutation gap is identified;
that receipt is not negative proof for the later oracle correction.

```powershell
$env:COVERAGE_FILE = Join-Path (Get-Location) '.venv/upstream-sync-0.9.92-final/inc56-native-fixtures/frozen.coverage'
.venv/Scripts/python.exe -X utf8 -m pytest -q --disable-warnings -o addopts= tests/test_graph_invariance_admission.py tests/test_qt_native_cpp_newline_cli.py tests/test_native_newline_cli.py --junitxml=.venv/upstream-sync-0.9.92-final/inc56-native-fixtures/native-frozen.xml
```

The separate `raw-lf-aggregate-after.xml` profile runs all twelve original
`test_graph_invariance.py` cases against raw committed Git LF fixtures and
passes **12 cases, zero skips**, one warning, in **62.43 seconds**. This preserves
all original exact graph assertions without relying on checkout conversion.

The integration maintainer's final six-module selection passes **79 cases,
zero skips/failures/errors**, in **34.66 seconds**. It includes the 41-case
native selection, ten source-gate controls, 23 Windows guards and five launcher
controls. These overlapping selections are not summed. Saved behavioral inputs,
dependencies and original coverage bytes remain unchanged in its receipt.

```powershell
.venv/Scripts/python.exe -X utf8 -m pytest tests/test_ci_source_cases.py tests/test_ci_windows_tools.py tests/test_qml_ci_profiles.py tests/test_graph_invariance_admission.py tests/test_qt_native_cpp_newline_cli.py tests/test_native_newline_cli.py -q --tb=short -p no:cacheprovider --junitxml=.venv/upstream-sync-0.9.92-final/hosted-recovery/root-final-focused.xml
```

Evidence is retained in `inc56-native-fixtures/native-frozen.xml/.log`,
`raw-lf-aggregate-after.xml/.log`, saved identity-permutation probes and
`hosted-recovery/root-final-focused-receipt.json` plus matching XML/log.
Launcher/profile/aggregate/admission/C++/source-gate owners measure
53/135/175/169/227/112 physical lines; the workflow measures 632 under its
650-line CI-owner allowance. Whole Ruff and all five generated checks pass.
Whole explicit Pyright still exits one with **651 diagnostics across 837
files**, with zero added/removed file/rule/message/severity identities against
the prior 651/834 profile. Focused changed-module typing passes.

The AST-only repository graph refresh exits zero with **27,325 nodes / 64,066
edges**, 53 uncached inputs and the existing partial Luau/26 no-symbol warnings.
No API/LLM, active per-user tool or application refresh occurs. Runtime/package
production tree remains `788fef0be4cba271626db048c6ce6d49a504330c`; these CI/test
corrections do not change the previously reviewed wheel. New-head hosted checks,
review, merge, exact merged-SHA proof and unresolved platform/service/advisory
gaps remain distinct from this local handoff.

## Advisory scanner baseline — source `5876f0a4`

The inherited security job reports success while both scanner steps exit1 under
`continue-on-error: true`. Its entire job section matches pinned upstream `86c57be8`.
Bandit reports 12 medium/high findings (four SHA1, five XML, three bind literals).
Every reported anchor and complete enclosing function AST matches that upstream.
Pip-audit reports 16 raw rows across certifi 2026.4.22, pip 26.1.1, urllib3 2.7.0 and
virtualenv 21.3.3, containing ten unique exact package/advisory-ID pairs. All four
locked package records also match upstream `86c57be8` and their versions match the
preintegration fork. These facts establish provenance, not safety or waiver.

Some records are reachable through optional production HTTP/provider extras;
the dependency findings cannot all be dismissed as development-only. Static
SHA1 uses appear in sketch/identity owners; bind literals include comparisons
and a warning around optional wildcard/no-key HTTP exposure. Actual risk and
false-positive assessment for every finding remain **Unconfirmed**. No scanner
suppression, dependency upgrade, runtime fix or exploit validation is performed.
Detailed bounded provenance is retained in ignored `hosted-recovery/`
`delivery-security-baseline.json`/`.md` and `root-security-job.log`. This advisory
gap remains outside INC-QML-55 and INC-QML-56; a green job is not clean-security acceptance.

## Watch test-clock isolation — INC-QML-57

Status: **Implemented with 31 local passes and one actual-POSIX capability skip;
new-head hosted proof pending**. The matrix preceded correction. CI run `39492352532`
tests source `c7386ad0430f7a2a46e00ce66ad11647f2333e12` against base
`82a4f296446b4cc219ffecfe3345a037e9c362e4` at actual PR merge checkout
`0c6b24762fb2d352770c2d39fed7be28e95e2c16` (`pull_request`). Linux Python 3.14
records **11,871 passed, 134 skipped and one failure** across 12,006 cases:
`test_pr10_watch_overrides.py::test_ignored_root_configuration_still_rebuilds_the_graph[False]`.
The graph is absent and captured output stops before the Git-head boundary.
All 47 required cases (42 joint integration plus service/artifact controls),
four integrity checks and job-owned graph/service cleanup pass independently.
All four Linux wheels match the 327 committed package files.

Python 3.13 records **11,872 passed and 134 skipped** in complete JUnit but its
job is cancelled; this is not a successful hosted job. Python 3.10/3.12 cancel
without JUnit or completed integrity evidence; their cleanup is confirmed.
Windows CI separately succeeds with 1,060 passes/56 platform skips, 29 required
native cases and all integrity checks passing. QML/macOS terminal evidence is
not inferred from any of those profiles.

| Acceptance IDs | Exact current owner and regression evidence |
| --- | --- |
| REQ-QML-014-AC03; REQ-CORE-004-AC03 | `test_watch_clock_isolation.py::test_req_qml014_ac03_watch_pump_keeps_stdlib_clock_identity` checks clock identity before/during/after; `test_req_qml014_ac03_lock_retry_sleep_does_not_consume_event[0.05/0.5]` checks that retries delegate even when the delay matches the loop poll. `test_req_qml014_ac03_changed_poll_contract_fails_without_hanging` rejects changed direct-loop polling promptly. These cases pass through the existing helper. |
| REQ-QML-014-AC03/AC04; REQ-CORE-004-AC03 | `test_req_qml014_ac03_nested_dependency_sleep_keeps_original_config_acceptance[False/True]` calls the unchanged original PR10 acceptance function with actual rebuild/nested standard sleep. `test_req_qml014_ac03_posix_timed_child_wait_keeps_event_pump_scoped` exercises an actual child timed wait on POSIX; native Windows remains an explicit unexecuted POSIX boundary. |
| REQ-QML-014-AC03/AC04; REQ-CORE-004-AC04; REQ-QML-015-AC01/AC03/AC04 | Run original lifecycle/PR10 assertions and focused new regressions without deadline increases, new acceptance skips or runtime changes; publish one ordinary new-head PR synchronization. Cancelled/unrun lanes remain explicit gaps. |

The ordinary local failed-case replay passes, while an isolated probe adds a
harmless real clock call at the nested Git-head boundary and reproduces the
same missing-graph failure. `drive_watch` changes the shared `time.sleep`, and
the observed POSIX timed-wait implementation can call it. These observations
establish the dependency-leak mechanism without capturing or claiming the exact
nested hosted caller. Evidence is retained privately in
`hosted-recovery/c738-linux-*/audit.json`, `c738-watch-probe.xml`,
`c738-watch-delay.xml/.log` and the associated stack probes. Correction and
new-head hosted results remain pending; no original assertions are removed.

An initial five-case clock regression records **four failures and one native
Windows POSIX-boundary skip** in 1.81 seconds before correction. Its initial
combined lifecycle selection passes **29 cases with one POSIX-boundary skip**
in 5.14 seconds. The later direct-caller/changed-poll guard and equal-delay retry
control require their own final receipt; these counts are intermediate.
The POSIX test uses an actual bounded child that closes output pipes and waits
for a release file; observing the real standard-library timed-wait sleep
releases it. Profiling is restored and the child release is ensured on exit;
the standard-library callable is never replaced. This case remains locally
unexecuted on Windows. The shared helper has one pre-existing optional-handler
type diagnostic; no claim of a wholly clean focused legacy-file typecheck is
made.

The caller-identity refinement has its own negative control: **two failures and
one passing control**, four deselected, in 1.39 seconds against the interval-only
proxy. This covers equal-delay retry and explicit changed-poll rejection.
Final helper, original PR10 and lifecycle tests pass **31 cases, one POSIX skip,
zero failures/errors**, 22 warnings, in **8.00 seconds**:

```powershell
$env:COVERAGE_FILE = Join-Path (Get-Location) '.venv/upstream-sync-0.9.92-final/hosted-recovery/c738-watch-clock-final.coverage'
.venv/Scripts/python.exe -X utf8 -m pytest -q --disable-warnings -o addopts= tests/test_watch_clock_isolation.py tests/test_pr10_watch_overrides.py tests/test_language_override_lifecycle.py --junitxml=.venv/upstream-sync-0.9.92-final/hosted-recovery/c738-watch-clock-final.xml
.venv/Scripts/python.exe -m ruff check tests/test_language_override_lifecycle.py tests/test_watch_clock_isolation.py
.venv/Scripts/python.exe -m pyright --pythonpath .venv/Scripts/python.exe tests/test_watch_clock_isolation.py
```

Receipts are `c738-watch-clock-before.xml/.log`,
`c738-watch-clock-guard-before.xml/.log` and `c738-watch-clock-final.xml/.log`
under `hosted-recovery`. Ruff passes both files; new-module Pyright passes with
zero errors/warnings. The helper's optional-handler diagnostic matches the
frozen typing baseline. Helper/new-module sizes are 307/129 physical lines;
the helper's scoped 320-line cohesion allowance is recorded in code reference.
Original coverage bytes stay unchanged. No production/package/workflow change,
new deadline or assertion weakening occurs. Actual POSIX timed waiting and
normal new-head hosted verification remain outstanding.

The final integration-owner replay passes the same 31 cases with one explicit
POSIX skip in 6.56 seconds, preserving source inputs, dependencies and prior
coverage bytes. Whole-repository Ruff passes. Explicit-interpreter Pyright
retains 651 baseline errors across 838 files, with no added or removed
file/rule/message/severity signatures. The AST-only repository graph refresh
exits zero with 27,352 nodes and 64,126 edges. These checks retain the native
Windows boundary; they do not establish the pending hosted POSIX result.

## Literal CMake resource-output pairs — INC-QML-58

D35 and the design profile refine REQ-QML-009-AC01/AC03/AC04. Evidence describes
known literal QRC additions only; it does not prove an inherited variable is
empty, enumerate native generated outputs, execute a build or admit a parent
project descriptor. Unsupported general CMake evaluation remains a separate scope.

| Acceptance IDs | Exact automated production evidence and profile |
| --- | --- |
| REQ-QML-009-AC01/AC03; REQ-QML-010-AC01; REQ-QML-020-AC01 | `tests/test_qt_cmake_resource_outputs.py::test_req_qml009_ac01_resource_output_pair_preserves_qrc_and_use_spans` covers Qt/Qt6, multiple QRCs, BOM/CRLF/Unicode original-byte coordinates, stable IDs after inserted comments, module ownership, explicit generated-use/input flags, reference direction and JSON/sanitation transport. `test_req_qml009_ac03_known_declaration_prefix_and_trailing_opaque_command` covers the bounded prefix and existing target-form resource coexistence. All six success profiles fail before implementation and pass afterward. |
| REQ-QML-009-AC04; REQ-QML-012-AC01/AC04 | `test_req_qml009_ac04_prefix_barriers_and_any_prior_identifier_prevent_binding` and `test_req_qml009_ac04_unsupported_pair_shapes_never_emit_generated_use` in that module protect unknown prefix commands, explicit writers, includes/package loads/control scopes, prior/reused names, duplicate/forward modules, wrong-target/nonprivate/mixed/quoted/computed consumers, orphan and repeated producers, unsafe/duplicate QRCs, unsupported RCC options and input properties. `test_req_qml012_ac04_command_inventory_boundary_is_typed_and_bounded` proves 10,000 accepted versus 10,001 rejected commands with exact typed reason and no facts. The command-bound assertion fails before correction; all other negative cases retain rejection. |
| REQ-QML-009-AC03; REQ-QML-011-AC01/AC04; REQ-QML-020-AC01 | `tests/test_qt_cmake_output_updates.py::test_req_qml009_ac03_pair_reaches_graph_export_reload_and_warm_full_parity` proves the admitted QRC file join, use-token span, directed reference and XML-owned aliases through real collector/facade, graph assembly, JSON reload, warm repeat and clean extraction. `test_req_qml009_ac03_actual_app_only_extract_cli_keeps_corpus_boundary` runs the actual `extract app --code-only --no-cluster --max-workers 1` subprocess; a rejected parent descriptor stays outside the admitted graph. |
| REQ-QML-011-AC02 | `test_req_qml011_ac02_metadata_and_qrc_only_changes_remove_stale_pair_facts` in that module retargets the CMake QRC input, changes only an XML alias, removes the pair, and compares each accepted result with a clean build. |
| REQ-QML-012-AC02; REQ-QML-011-AC04 | `test_req_qml012_ac02_rejected_mutation_retains_products_repeats_and_recovers` covers normal and forced rejection, byte-for-byte graph/manifest/report/Qt-state retention, repeated failure, corrected recovery and settled repeat. `tests/test_qt_analysis_state.py::test_req_qml018_ac02_literal_parser_upgrade_retires_prior_policy_and_repeats` now covers policy 25 as well as 22/23/24; `tests/test_qt_cmake_rc_updates.py::test_req_qml011_ac04_prior_policy_refresh_rejection_retains_products_then_commits26` retains the transactional upgrade/rejection/recovery assertions and adds policy 25. The latter replaces the earlier `commits25` test spelling; earlier recorded policy-25 evidence remains historical. |
| REQ-QML-014-AC03/AC04; REQ-QML-001-AC01/AC03 | All original unsupported-form assertions remain. The focused surrounding CMake/resource/state suite passes 223 cases with zero skips. A source-matched wheel passes all three existing artifact tests, clean isolated core-only and QML-extra installed smokes, and a separate neutral installed QML CLI pair probe. No dependency contract or workflow change is needed: existing Qt-prefixed native selection and Linux source selection already collect the new modules. New-head hosted and non-Windows execution remain unverified. |

Before production correction, the new direct module reports **7 failed, 43
passed**, and the five integration cases fail at the existing incomplete-metadata
gate. The first post-fix integration replay exposed a new test helper's incorrect
use of unordered NetworkX endpoints; serialized JSON already contained the right
arcs. The helper now reads authoritative `_src`/`_tgt` direction and NetworkX node
identity. No product assertion was removed. Final integration replay passes all
five cases. Final focused coverage is 223 passes, zero failures/skips, 22 warnings
in 67.74 seconds: the new helper has 100% line coverage, while `qml_cmake.py` has
92% in this selection. Its nine uncovered lines are existing module-option
validation paths, not newly introduced pair branches. Line coverage does not
establish runtime coverage of analyzed applications or exhaustive CMake semantics.

The focused selection is:

```powershell
$env:COVERAGE_FILE = Join-Path (Get-Location) '.venv/cmake-resource-output-repair/focused.coverage'
.venv/Scripts/python.exe -X utf8 -m pytest -q --disable-warnings --junitxml=.venv/cmake-resource-output-repair/focused.xml --cov=graphify.extractors.qml_cmake_outputs --cov=graphify.extractors.qml_cmake --cov-report=term-missing --cov-report=json:.venv/cmake-resource-output-repair/focused-coverage.json tests/test_qt_cmake_resource_outputs.py tests/test_qt_cmake_output_updates.py tests/test_qt_cmake_mutations.py tests/test_qt_cmake_review_boundaries.py tests/test_qt_cmake_resource_collisions.py tests/test_qt_cmake_rc_updates.py tests/test_qt_analysis_state.py tests/test_qt_resource_resolution.py tests/test_qt_project_metadata.py
```

Whole-repository Ruff and all five generated-artifact checks pass (`--check`,
`--audit-coverage`, `--schema-singleton`, `--monolith-roundtrip`, and
`--always-on-roundtrip`). Explicit-interpreter whole Pyright still fails with
651 diagnostics across 841 files: file/rule/message/severity signatures are
identical to the prior 651/838 profile, with no additions or removals. This is
retained baseline debt, not a passing type check. New helper and unit files pass
focused typing; the whole comparison also covers the new integration owner.

`uv build --wheel --python .venv/Scripts/python.exe --out-dir
.venv/cmake-resource-output-repair/wheel` produces the unchanged 0.9.92 package
version. All 191 production Python files, including the new helper, match the
reviewed source bytes in the artifact. Existing license/extra metadata tests and
neutral `-I` installed smokes pass on Windows/Python 3.12.14; the neutral installed
pair probe yields one directed QRC membership without a native build. The active
per-user tool and application graph are separate adoption boundaries and have not
been replaced by these isolated installations. Wheel, JUnit, source-match,
coverage and baseline-comparison receipts remain outside version control under
`.venv/cmake-resource-output-repair/`.

Final whole-suite result, repository-graph refresh, owner measurements and
increment exit status are appended after their terminal checks; no pending or
unexecuted check establishes completion.

Final whole-suite invocation on Windows/Python 3.12.14:

```powershell
$env:COVERAGE_FILE = Join-Path (Get-Location) '.venv/cmake-resource-output-repair/full.coverage'
.venv/Scripts/python.exe -X utf8 -m pytest tests -q --junitxml=.venv/cmake-resource-output-repair/full.xml
```

The terminal result is **49 failed, 11,836 passed, 190 skipped**, 3,886 warnings
in 1,860.60 seconds. The 49 failures are exactly two code-only host-update,
thirteen hook, six shell-portability helper, twenty-three input-path injection
and five selected-interpreter cases. Actual failure text identifies an
inaccessible Windows WSL `bash` alias or unavailable `sh`, rather than a CMake/
Qt assertion. The existing CI Windows native profile supplies qualified Git
Bash/sh and an interpreter shim; a process-local replay of these exact 49 node
IDs passes **49/49**, zero skips, one warning in 60.83 seconds. No source/test
correction, assertion relaxation, installer or global PATH change is involved.

An additional replay of the 78 originally shell-related skipped identities passes
16 and retains 62 skips in 10.01 seconds. Those remaining legacy guards explicitly
exclude native Windows/POSIX execution even when MSYS tools are available; their
reason text can still say `sh required` or `needs bash and cat on a POSIX host`.
Do not remove those guards to relabel unexecuted work as passing. The three
initially skipped wheel-artifact identities separately pass with the reviewed
wheel supplied. Exact identity union across `full.xml`, `failed-profile/tests.xml`,
`skipped-shell-profile/tests.xml` and `wheel-artifact.xml` is **12,075 unique cases:
11,904 passed, 171 skipped, zero unresolved failures/errors**. This is combined
evidence from separate receipts, not a single green full-suite invocation.

The native replay profile follows the existing
[CI Windows compatibility setup](../.github/workflows/ci.yml): qualified portable
Git Bash/sh, verified selected Python and Node identities, a process-local
`python3` shim that rejects pip fallback, offline installer settings and isolated
tool/pip/appdata destinations. Both replays retain production-file hashes, HEAD,
dependency name/version inventory and the original coverage hash. The complete
node IDs, preflight, original failure messages, outcome union and skip reasons
remain in ignored receipts; no private corpus or local operational path is part
of the public fixture. The active tool/application graph and hosted workflows
were not changed by this validation.

The 171 remaining skips include symlink privilege and POSIX filesystem/shell
boundaries, optional C preprocessor/validation-oracle availability, unavailable
services and profile-specific cases. New-source Linux/macOS execution remains
unverified. New CMake behavior and affected criteria have zero skips in the
223-case focused profile; no skipped system boundary is used to mark broader
platform support verified. The existing 651 type diagnostics also remain open.

Final code/test owner sizes are 160/110/115/133/129/161/118 lines for facade,
output helper, policy, direct tests, integration tests, analysis-state tests and
RC-update tests respectively; every owner is below 300. The AST-only repository
update completes successfully with 27,394 nodes and 64,252 edges after retaining
a backup. Existing non-Qt fixture syntax warnings remain explicit. The original
coverage hash is unchanged. Independent production and public-document review
finds no blocker. Increment exit adds no further product increment for this
bounded form; broader CMake evaluation requires its own accepted profile. Local
commit review, hosted validation, merging and application adoption remain distinct.
