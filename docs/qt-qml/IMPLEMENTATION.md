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
| QML-001-AC02 | Verified in QML-03 | Hand-checked production syntax and original spans; fresh offline process; test_qml_syntax_profile.py |
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

## QML-03

Complete for the declared Windows x64 static profile, including Qt 6.5/6.8 source
fixtures. QML-03a adds objects held in properties/bindings/arrays and conservative
template scope barriers. QML-03b adds source-owned binding, read, alias, call and
handler facts with lexical shadowing and explicit unresolved/dynamic reasons.
QML-03c adds accepted `.js`/`.mjs` overlays, classic Qt directives, explicit callable
ESM exports and script dependencies without changing the generic JavaScript graph.

Subscriptions use references, emissions use uses, and proven callable invocations
use calls. Each occurrence owns its original span and a separate identity, retaining
repeated dependencies through the simple graph. Named declaration identity remains
stable after inserted comments; derived occurrence identities intentionally include
their source span. Extracted syntax and inferred endpoints remain separate.

All four QML-006 and QML-007 criteria pass the exact tests listed individually in
[traceability](../../tests/TRACEABILITY.md). QML-001-AC02 closes against the shipping
adapter and the hand-checked syntax corpus. Explicit runtime target/context lookup,
ESM reexports, imported value exports and unavailable framework signals remain
unresolved. Name-based Component/delegate/sourceComponent barriers conservatively
prevent leakage; they do not prove Qt runtime creation context or framework types.

Review caught malformed literal transport, capped lexical display lists, duplicate
held Connections, ignored mixed handler styles, inherited signal binders, generic-JS
name pollution and script import endpoints omitted by generic cross-family guards.
All have production regressions. Default-undirected export/reload now restores QML
edge direction from serialized endpoints. A final reader review corrected BOM and
CRLF normalization of qmldir byte offsets using bounded original binary reads.

Windows source suite before the eight final reader regressions: 239 passed and two
host symlink-permission skips in each Python 3.10/3.12/3.13/3.14 lane. Clean optional
wheels run bindings/script/subscription production smoke; actual core-only install
retains Python extraction and emits missing-parser diagnostics. Final reader/wheel
reverification is recorded in VALIDATION.md. Linux/macOS remain pending hosted CI.

Plan review adds QML-06a/06b for mutation/config/cache contracts and QML-07a/07b for
consumer direction and hosted installation/upstream evidence. Existing QML-00..07
and QML-04a/04b/04c identities remain unchanged. The user has authorized continuing
through QML-04, QML-05 and QML-06; their implementation evidence follows separately.

## QML-03 measured modularity exceptions

All new handwritten production and test modules stay below the 300-line default.
The integration owner permits only focused hooks in oversized upstream files:

| Legacy file | Upstream lines | QML-03 measured ceiling | Reason |
| --- | --- | --- | --- |
| graphify/extract.py | 8943 | 8997 | Admission/worker and scoped-overlay dispatch |
| graphify/detect.py | 2793 | 2797 | QML and exact named metadata admission |
| graphify/build.py | 2462 | 2466 | Narrow proof-based script projection |
| graphify/cli.py | 4915 | 4936 | Publication safety and conservative refresh |
| graphify/watch.py | 2488 | 2506 | Same safety/root/admission contracts |
| graphify/paths.py | 523 | 536 | Retain QML orientation on undirected reload |
| tests/test_extract.py | 4823 | 4827 | Preserve extension-only oracle plus exact metadata admission |

Owner: Qt/QML integration maintainer. Exit: upstream coordinated facade/writer
splitting; domain analysis remains in focused modules. Later hooks must remeasure
these ceilings and retain this rationale rather than quietly extending them.


## QML-04

Complete for the declared Qt6 static source profile verified on Windows Python
3.12.14; exact later-host proof remains a release obligation. Known annotations
are normalized before generic C++ extraction, preserving original bytes/spans and
C++/CLI/test-macro behavior. Separate Qt facts borrow final canonical C++ endpoints.
Registration, property/accessor/notify, invokable, signal/slot and source event
mechanisms retain their evidence. Q_OBJECT alone is never QML exposure.

Member pointers, overload selectors/casts, ordinary compatible members, private
legacy slots, signal-to-signal, lambdas/functors/free functions and supported
connection/disconnect forms have actual facade regressions. No event projection
invents runtime delivery or immediate receiver calls. Literal QQmlApplicationEngine,
QQmlComponent and QQuickView source access, root/handle/objectName provenance,
QQmlProperty and reflective member intent are covered. Context/initial providers
remain scoped to an exact loaded component with local/lexical/duplicate rejection.

Qt metadata readers/indexes ship as an internal dependency foundation for literal
source-file access. Public project/resource admission and their resolved module
bridges close in QML-05. Revised native members, foreign/extended/attached/value
providers, arbitrary compiler conversions, dynamic creation and inline temporary
QQmlProperty expressions remain explicit unsupported results.

The canonical requirements and individual test mappings advance QML-008/016/017;
QML-016-AC01..AC03 pass their native source cases. Their final incremental and
consumer criteria remain open. No new top-level increment is needed: QML-06a/06b
retain mutation/configuration proof and QML-07a/07b retain consumers/hosted release.

All new handwritten source/test files remain below 300 physical lines. Updated
legacy hooks have the same integration owner and coordinated upstream-splitting
exit as the prior exception record. QML-04 measured ceilings are:

| Legacy file | Measured/permitted lines | Focused integration reason |
| --- | --- | --- |
| graphify/extract.py | 8982 | Canonical C++ normalization followed by the separate Qt join owner |
| graphify/build.py | 2469 | Exact cross-language endpoint proof guard |
| graphify/cache.py | 1782 | Syntax schema migration to version 5 |
| graphify/paths.py | 537 | Restore versioned Qt relationship direction |

Domain logic remains in focused Qt modules. These exceptions do not permit
unmeasured later growth; each later increment remeasures its touched hooks.


## QML-05

Complete for the literal Qt6 source profile. Discovery/registry/facade/worker
paths admit metadata without running CMake, qmake, moc, plugins or QML. One per-run
QtProjectIndex supplies accepted module/source/resource membership to native and
QML joins. Generated tooling descriptions retain separate origins and warnings.
Duplicate source declarations survive generic namespace canonicalization, so
multiple modules/aliases cannot silently become a unique provider. Unknown CMake
resource policy, dynamic build expressions and locale-dependent resource selection
remain explicit unsupported results. Final configuration/update parity is QML-06.

Legacy measured ceilings: extract.py 8999, detect.py 2797, test_extract.py 4827;
owner Qt integration maintainer (discovery owner source discovery maintainer).
Reason: narrow named-source admission, root-sensitive dispatch and exact fact
identity protection. Exit: coordinated upstream facade/classification extraction.


## QML-06

Implemented accepted-corpus refresh and immutable worker cache policy. Native
syntax is reparsed in Qt contexts; ordinary C++ portable cache behavior remains.
Generic JavaScript already bypasses its syntax cache. Versioned Qt/QML metadata
is never reused as a project-resolved syntax result. .qt_analysis.json stores a
bounded hash-only parser/fact/policy/root/ignore/corpus checkpoint, committed after
successful graph and manifest writes. Failed source/configuration analysis keeps
prior graph, manifest and checkpoint bytes. Ordered GRAPHIFY_QML_IMPORT_ROOTS is
a project-relative JSON list; it changes lookup order, never corpus admission.

Actual extract/update/watch tests cover metadata-only/native-only changes, ignored
providers, rename/delete/duplicate resources and modules, import-root order, parser
version, last Qt deletion, unchanged reruns and forced malformed-input rejection.
Focused worker/native cache and root-boundary evidence is recorded in validation.

QML-06 legacy ceilings: extract.py 9009, cli.py 4949, watch.py 2527. Owner Qt integration maintainer; focused policy/root/publication hooks only. Exit coordinated upstream facade/writer extraction. New handwritten modules/tests remain below300 lines.

## QML-07

Implemented the bounded static profile through real query/explain/path/affected,
ordinary graph HTML, call-flow HTML, source coverage reports and optional HTTP/
stdio MCP consumers. Exact graph IDs remain opaque endpoint identities. Search
indexes curated decoded names/types/roles/module URIs and source mechanisms,
preserving user attributes and rejecting malformed transport before decoding.
CLI and MCP render identical selected source facts and path provenance.

Affected propagation follows proven source ownership for versioned Qt/QML
dependency occurrences. Canonical header declarations can own implementation
sites only with their accepted definition file, callable identity and exact
extracted endpoint/span evidence. Signal delivery stays separate from calls.
Call-flow HTML preserves resolved and unresolved event/access evidence, and
ordinary HTML preserves semantic payloads and safely renders literal values.
Community aggregation states its omission of individual source facts.

Canonical JSON retains both graph orientations; directed GraphML retains nested
metadata in JSON properties. Qt Cypher and actual Neo4j/FalkorDB SDK boundaries
preserve source direction, complete metadata and distinct relationship keys.
Reserved transport-property collisions fail before file publication or SDK
connection. Live database engine execution is unverified and is outside this
static profile. Presentation-format omissions are documented in EXPORT_MATRIX.md.
Report source-site status counts expose unresolved/error coverage independently
of graph edge confidence; source analysis never claims runtime verification.

Six authoritative assistant fragments and all 134 generated artifacts/expected
outputs were updated together. Rendered AST examples use the trusted root,
ordered import paths and native refresh policy, and gate before publication.
The installed-artifact smoke now includes native QML_ELEMENT, literal CMake
membership and QRC loader resolution without executing corpus or a Qt SDK.

QML-07 review retains the seventeen requirements and sixty-eight acceptance IDs.
Explicit real normal-QML-edit/update/watch and no-change parity closes an evidence
gap in the existing QML-011 criteria. No additional top-level increment is needed
for the agreed profile; computed/runtime/framework/plugin behavior remains an
explicit unsupported boundary. Final hosted verification is recorded in
VALIDATION.md and the delivery PR, not inferred from local tests or earlier runs.

### QML-07 measured modularity exceptions

Thin consumer hooks stay in their existing upstream owners; domain policy lives
in focused qt_qml_search, qt_affected, qt_relationship_views, qt_html, qt_coverage,
qt_export and path_provenance modules. New handwritten modules/tests are below
300 physical lines. Current ceilings for modified legacy owners are:

| Owner | Physical line ceiling | Reason |
| --- | --- | --- |
| graphify/affected.py | 329 | Source-owned occurrence dependency hook |
| graphify/callflow_html.py | 2058 | Typed event table and call-list exclusion hooks |
| graphify/cli.py | 4955 | Exact endpoint and shared path provenance hooks |
| graphify/serve.py | 2725 | Shared search, deterministic facts and MCP path hooks |
| graphify/export.py | 1369 | Atomic Qt-aware Cypher dispatch |
| graphify/exporters/html.py | 690 | Qt payload/detail and aggregation omission hooks |
| graphify/report.py | 397 | Source coverage view hook |
| tools/skillgen/gen.py | 1450 | Exact sanctioned source predicates under existing frozen validators |

Owner: Qt integration maintainer, coordinating generic consumer, presentation,
export and generator boundaries with their upstream maintainers. Exit: an
upstream-coordinated extraction of shared consumer/writer/validator interfaces,
retaining existing regression characterization and frozen guidance contracts.
This exception does not authorize arbitrary growth or mechanical file slicing.
