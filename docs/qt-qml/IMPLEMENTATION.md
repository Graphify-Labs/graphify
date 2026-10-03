# Executed increments

## QML-00

Complete for optional parser selection; see [parser evidence](PARSER_DECISION.md).
No production criterion closes from probes alone.

## QML-01

QML-01a implements publication guards and conservative refresh. QML-01b adds lazy
offline grammar loading, QML admission, declarations/imports, explicit roots,
scoped portable IDs, spans, safe failures and a pinned optional qml extra.
Bounded base64 companions preserve semantic values through HTML sanitation.
Empty editor files have file facts and an explicit informational diagnostic.
The subset includes objects, grouped properties, properties/modifiers, signals,
functions, inline components, enums, pragmas and imports. Module joins are QML-02;
bindings/calls/signals QML-03. C++/CMake/qmake/resources remain later increments.

Windows focused checks: 90 passed, zero skipped. Real spawn workers, portable
identity, build/JSON reload, forced/equal-count/edge-loss retention, read races
and successful retries are exercised. New modules pass Ruff/Pyright. Clean wheel
installation and remaining parser-failure cases are being verified.

| Criterion | Status | Evidence / remaining gate |
| --- | --- | --- |
| QML-001-AC01 | Verified for Windows x64 | Wheel from committed source installs and runs in isolated Python 3.10/3.12/3.13/3.14 environments; tests/qml_installed_smoke.py |
| QML-001-AC02 | In progress | Offline probes pass; production syntax closes QML-03 |
| QML-001-AC03 | Verified | Actual optional import rejection, incompatible binding/native parse failures, safe cache bypass |
| QML-001-AC04 | Verified | Empty, malformed and grammar-recognized unsupported fixtures have distinct diagnostics |
| QML-003-AC01 | Verified | Exact declarations/ownership/types in test_qml_declarations.py |
| QML-003-AC02 | Verified | Duplicate scopes/paths/stems/case in identity and graph tests |
| QML-003-AC03 | Verified | Comment/string/grouped-property negatives |
| QML-003-AC04 | Verified | Relocation, inserted comments, reordered/warm batches and actual spawn |

QML-003 is Verified for this subset. QML-001/002/010/011/012/013/014/015 are Partially
implemented, with later metadata/update/platform/consumer gates still open.
Other requirements remain Planned.

## Increment review and module debt

QML-00 added QML-01a/01b. QML-01 review requires semantic qmldir validation,
immutable indexes, provider-only refresh and independent reference/event sites
in QML-02/03. No new top-level increment is needed. Cache optimization is QML-06.

Root owns narrow integration hooks in oversized legacy extract.py, detect.py,
build.py, cli.py and watch.py. New responsibilities remain in modules below 300
lines. Exception: integration hooks only in these existing files. Exit: upstream
coordinated facade/writer splitting, outside this increment. Final validation
records measured sizes/deltas before handoff.

QML-01 completion review: clean built-wheel checks pass in all four declared
Windows lanes with Python-level network/process denial and no Qt SDK. Parser
absence/ABI/native-error and unsupported-source regressions also pass. Production
parser corpus AC02 remains assigned to QML-03. Linux/macOS stay unverified.
QML-01 is complete for this declared optional profile; advance to QML-02.

## QML-02

Implemented immutable per-run module/member indexes, explicit-root URI providers,
directory imports, aliases, observed versions, singleton/inline/internal visibility,
owned resolution sites, exact-name qmldir admission and semantic metadata parsing.
Unknown framework types/versions remain unresolved. Module import grants visibility;
packaging depends does not. No corpus expansion, plugin execution or SDK traversal.

Observed export versions establish module availability in this initial profile.
Requested unobserved module minors remain unresolved pending QML-05 metadata.
Runtime parent/outer context remain unavailable without supported explicit evidence.

Review added QML-02a/02b/02c and caught growing scope keys and missing direct-producer
provenance. Digest scopes and AST markers fix both with regressions. Raw semantic
metadata survives sanitation. The repository graph excludes its two deliberately
malformed parser fixtures via .graphifyignore; tests still open them directly.
Integrated admission/update checks pass: 44 passed, two symlink cases skipped
because the Windows account lacks symlink creation privilege. Those skipped
platform cases remain open under QML-002/014. Real >20-file pool execution,
borrowed-context immutability, named ignores/root admission and metadata-only
update parity passed. Raw update lost orientation on reload until QML edges also
carried Graphify's `_src`/`_tgt` markers; the strict parity regression now passes.
All new production modules pass Ruff/Pyright. QML-02 is complete for this profile.

| Criterion | Status | Actual test in test_qml_resolution.py or test_qml_scope.py |
| --- | --- | --- |
| QML-004-AC01 | Verified | test_aliased_directory_and_uri_imports_do_not_cross_bind; test_version_availability_and_latest_compatible_export |
| QML-004-AC02 | Verified | test_aliased_directory_and_uri_imports_do_not_cross_bind; test_versioned_layout_and_missing_version_evidence |
| QML-004-AC03 | Verified | test_competing_providers_and_missing_modules_have_no_target_edges |
| QML-004-AC04 | Verified | test_declared_roots_and_remote_import_never_expand_corpus; test_directory_and_script_projection_and_ignored_disk_provider |
| QML-005-AC01 | Verified | test_component_ids_do_not_leak_between_files_or_inline_components |
| QML-005-AC02 | Verified | test_inline_shadow_and_inherited_members_are_distinct_roles; test_singleton_pragma_and_qualified_access |
| QML-005-AC03 | Verified | test_internal_external_dynamic_and_lexical_members_stay_unresolved; bounded inheritance cycle test |
| QML-005-AC04 | Verified | test_module_script_exports_have_separate_lookup_roles; inline shadow test |

Review retains QML-03's lexical/script/handler gates and QML-06 cache optimization.
No additional top-level increment is required. QML-02c covers the newly found
ignore/provenance/direction defects. QML-04/05 retain C++ and project metadata work.
