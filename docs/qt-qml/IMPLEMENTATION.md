# Executed increments

## Upstream submission scope

The [scoped upstream contribution](UPSTREAM_CONTRIBUTION.md) retains bounded Qt/QML analysis
and its source, incremental, publication and consumer contracts. REQ-QML-019
and REQ-QML-021, D12/D16, and the generic viewer portions of INC-QML-09/13/16
are deferred for this submission. Native Codex REQ-CORE-001-AC01/AC05 and the
broad fork repository policy are also deferred; the baseline installer and
repository policy apply. Constructor and source-containment work in INC-QML-13
remains in scope.

The [complete frozen fork](https://github.com/SlinkyRamey/graphify/commit/82a4f296446b4cc219ffecfe3345a037e9c362e4)
and its recorded 8b6c9d2 source/runner evidence retain their own revision scope.
Deferred feature sections and their exact tests below are historical evidence,
not implemented or verified contracts of this narrower contribution. A changed
contribution head requires fresh applicable checks; prior totals, skips and
hosted results do not establish those checks.

The [follow-up audit](FOLLOWUP_AUDIT.md) records receiver, descendant, engine and
alias false positives at its inspected baseline. INC-QML-17–27 implement bounded
corrections; INC-QML-11/15/08 and INC-QML-28–38 complete the bounded local adoption
profile recorded below. Historical records retain their original revision and scope.
The [final adoption delivery](#final-adoption-delivery) preserves that older
checkpoint. Later integration scope and evidence are recorded in the
[current-upstream integration profile](../REQUIREMENTS.md#current-upstream-integration-profile)
and the [immutable 8b6c9d2 checkpoint](../../tests/TRACEABILITY.md#verified-integrated-hosted-checkpoint--8b6c9d2).
Those records retain their tested revision, declared profiles and remaining gaps;
they do not establish acceptance of a later contribution head.

<a name="qml-00"></a>

The increment records below retain revision-specific implementation and evidence.
Their epochs, pending statements and test totals describe their individual
checkpoints.

## INC-QML-00

Complete for optional parser selection; see [parser evidence](PARSER_DECISION.md).
No production criterion closes from probes alone.

<a name="qml-01"></a>

## INC-QML-01

INC-QML-01a implements publication guards and conservative refresh. INC-QML-01b adds lazy
offline grammar loading, QML admission, declarations/imports, explicit roots,
scoped portable IDs, spans, safe failures and a pinned optional qml extra.
Bounded base64 companions preserve semantic values through HTML sanitation.
Empty editor files have file facts and an explicit informational diagnostic.
The subset includes objects, grouped properties, properties/modifiers, signals,
functions, inline components, enums, pragmas and imports. Module joins are INC-QML-02;
bindings/calls/signals INC-QML-03. C++/CMake/qmake/resources remain later increments.

Windows focused checks: 90 passed, zero skipped. Real spawn workers, portable
identity, build/JSON reload, forced/equal-count/edge-loss retention, read races
and successful retries are exercised. New modules pass Ruff/Pyright. Clean wheel
installation and remaining parser-failure cases are being verified.

| Criterion | Status | Evidence / remaining gate |
| --- | --- | --- |
| REQ-QML-001-AC01 | Verified for Windows x64 | Wheel from committed source installs and runs in isolated Python 3.10/3.12/3.13/3.14 environments; tests/qml_installed_smoke.py |
| REQ-QML-001-AC02 | Verified in INC-QML-03 | Hand-checked production syntax and original spans; fresh offline process; test_qml_syntax_profile.py |
| REQ-QML-001-AC03 | Verified | Actual optional import rejection, incompatible binding/native parse failures, safe cache bypass |
| REQ-QML-001-AC04 | Verified | Empty, malformed and grammar-recognized unsupported fixtures have distinct diagnostics |
| REQ-QML-003-AC01 | Verified | Exact declarations/ownership/types in test_qml_declarations.py |
| REQ-QML-003-AC02 | Verified | Duplicate scopes/paths/stems/case in identity and graph tests |
| REQ-QML-003-AC03 | Verified | Comment/string/grouped-property negatives |
| REQ-QML-003-AC04 | Verified | Relocation, inserted comments, reordered/warm batches and actual spawn |

REQ-QML-003 is Verified for this subset. REQ-QML-001/REQ-QML-002/REQ-QML-010/REQ-QML-011/REQ-QML-012/REQ-QML-013/REQ-QML-014/REQ-QML-015 are Partially
implemented, with later metadata/update/platform/consumer gates still open.
Other requirements remain Planned.

## Increment review and module debt

INC-QML-00 added INC-QML-01a/INC-QML-01b. INC-QML-01 review requires semantic qmldir validation,
immutable indexes, provider-only refresh and independent reference/event sites
in INC-QML-02/INC-QML-03. No new top-level increment is needed. Cache optimization is INC-QML-06.

Root owns narrow integration hooks in oversized legacy extract.py, detect.py,
build.py, cli.py and watch.py. New responsibilities remain in modules below 300
lines. Exception: integration hooks only in these existing files. Exit: upstream
coordinated facade/writer splitting, outside this increment. Final validation
records measured sizes/deltas before handoff.

INC-QML-01 completion review: clean built-wheel checks pass in all four declared
Windows lanes with Python-level network/process denial and no Qt SDK. Parser
absence/ABI/native-error and unsupported-source regressions also pass. Production
parser corpus AC02 remains assigned to INC-QML-03. Linux/macOS stay unverified.
INC-QML-01 is complete for this declared optional profile; advance to INC-QML-02.

<a name="qml-02"></a>

## INC-QML-02

Implemented immutable per-run module/member indexes, explicit-root URI providers,
directory imports, aliases, observed versions, singleton/inline/internal visibility,
owned resolution sites, exact-name qmldir admission and semantic metadata parsing.
Unknown framework types/versions remain unresolved. Module import grants visibility;
packaging depends does not. No corpus expansion, plugin execution or SDK traversal.

Observed export versions establish module availability in this initial profile.
Requested unobserved module minors remain unresolved pending INC-QML-05 metadata.
Runtime parent/outer context remain unavailable without supported explicit evidence.

INC-QML-02a/INC-QML-02b/INC-QML-02c use digest scopes and direct-producer AST markers.
Regressions cover growing scope keys and missing producer provenance. Raw semantic
metadata survives sanitation. The repository graph excludes its two deliberately
malformed parser fixtures via .graphifyignore; tests still open them directly.
Integrated admission/update checks pass: 44 passed, two symlink cases skipped
because the Windows account lacks symlink creation privilege. Those skipped
platform cases remain open under REQ-QML-002/REQ-QML-014. Real >20-file pool execution,
borrowed-context immutability, named ignores/root admission and metadata-only
update parity passed. Raw update lost orientation on reload until QML edges also
carried Graphify's `_src`/`_tgt` markers; the strict parity regression now passes.
All new production modules pass Ruff/Pyright. INC-QML-02 is complete for this profile.

| Criterion | Status | Actual test in test_qml_resolution.py or test_qml_scope.py |
| --- | --- | --- |
| REQ-QML-004-AC01 | Verified | test_aliased_directory_and_uri_imports_do_not_cross_bind; test_version_availability_and_latest_compatible_export |
| REQ-QML-004-AC02 | Verified | test_aliased_directory_and_uri_imports_do_not_cross_bind; test_versioned_layout_and_missing_version_evidence |
| REQ-QML-004-AC03 | Verified | test_competing_providers_and_missing_modules_have_no_target_edges |
| REQ-QML-004-AC04 | Verified | test_declared_roots_and_remote_import_never_expand_corpus; test_directory_and_script_projection_and_ignored_disk_provider |
| REQ-QML-005-AC01 | Verified | test_component_ids_do_not_leak_between_files_or_inline_components |
| REQ-QML-005-AC02 | Verified | test_inline_shadow_and_inherited_members_are_distinct_roles; test_singleton_pragma_and_qualified_access |
| REQ-QML-005-AC03 | Verified | test_internal_external_dynamic_and_lexical_members_stay_unresolved; bounded inheritance cycle test |
| REQ-QML-005-AC04 | Verified | test_module_script_exports_have_separate_lookup_roles; inline shadow test |

INC-QML-03 owns lexical/script/handler gates; INC-QML-06 owns cache optimization.
No additional top-level increment is required. INC-QML-02c covers the newly found
ignore/provenance/direction defects. INC-QML-04/INC-QML-05 retain C++ and project metadata work.

<a name="qml-03"></a>

## INC-QML-03

Complete for the declared Windows x64 static profile, including Qt 6.5/6.8 source
fixtures. INC-QML-03a adds objects held in properties/bindings/arrays and conservative
template scope barriers. INC-QML-03b adds source-owned binding, read, alias, call and
handler facts with lexical shadowing and explicit unresolved/dynamic reasons.
INC-QML-03c adds accepted `.js`/`.mjs` overlays, classic Qt directives, explicit callable
ESM exports and script dependencies without changing the generic JavaScript graph.

Subscriptions use references, emissions use uses, and proven callable invocations
use calls. Each occurrence owns its original span and a separate identity, retaining
repeated dependencies through the simple graph. Named declaration identity remains
stable after inserted comments; derived occurrence identities intentionally include
their source span. Extracted syntax and inferred endpoints remain separate.

All four REQ-QML-006 and REQ-QML-007 criteria pass the exact tests listed individually in
[traceability](../../tests/TRACEABILITY.md). REQ-QML-001-AC02 closes against the shipping
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

INC-QML-06a/INC-QML-06b cover mutation/config/cache contracts; INC-QML-07a/INC-QML-07b cover
consumer direction and hosted installation/upstream evidence. Existing INC-QML-00..INC-QML-07
and INC-QML-04a/INC-QML-04b/INC-QML-04c identities remain unchanged.
INC-QML-04, INC-QML-05 and INC-QML-06 implementation evidence follows separately.

<a name="qml-03-measured-modularity-exceptions"></a>

## INC-QML-03 measured modularity exceptions

All new handwritten production and test modules stay below the 300-line default.
The integration owner permits only focused hooks in oversized upstream files:

| Legacy file | Upstream lines | INC-QML-03 measured ceiling | Reason |
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


<a name="qml-04"></a>

## INC-QML-04

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
bridges close in INC-QML-05. Revised native members, foreign/extended/attached/value
providers, arbitrary compiler conversions, dynamic creation and inline temporary
QQmlProperty expressions remain explicit unsupported results.

The canonical requirements and individual test mappings advance REQ-QML-008/REQ-QML-016/REQ-QML-017;
REQ-QML-016-AC01..AC03 pass their native source cases. Their final incremental and
consumer criteria remain open. No new top-level increment is needed: INC-QML-06a/INC-QML-06b
retain mutation/configuration proof and INC-QML-07a/INC-QML-07b retain consumers/hosted release.

All new handwritten source/test files remain below 300 physical lines. Updated
legacy hooks have the same integration owner and coordinated upstream-splitting
exit as the prior exception record. INC-QML-04 measured ceilings are:

| Legacy file | Measured/permitted lines | Focused integration reason |
| --- | --- | --- |
| graphify/extract.py | 8982 | Canonical C++ normalization followed by the separate Qt join owner |
| graphify/build.py | 2469 | Exact cross-language endpoint proof guard |
| graphify/cache.py | 1782 | Syntax schema migration to version 5 |
| graphify/paths.py | 537 | Restore versioned Qt relationship direction |

Domain logic remains in focused Qt modules. These exceptions do not permit
unmeasured later growth; each later increment remeasures its touched hooks.


<a name="qml-05"></a>

## INC-QML-05

Complete for the literal Qt6 source profile. Discovery/registry/facade/worker
paths admit metadata without running CMake, qmake, moc, plugins or QML. One per-run
QtProjectIndex supplies accepted module/source/resource membership to native and
QML joins. Generated tooling descriptions retain separate origins and warnings.
Duplicate source declarations survive generic namespace canonicalization, so
multiple modules/aliases cannot silently become a unique provider. Unknown CMake
resource policy, dynamic build expressions and locale-dependent resource selection
remain explicit unsupported results. Final configuration/update parity is INC-QML-06.

Legacy measured ceilings: extract.py 8999, detect.py 2797, test_extract.py 4827;
owner Qt integration maintainer (discovery owner source discovery maintainer).
Reason: narrow named-source admission, root-sensitive dispatch and exact fact
identity protection. Exit: coordinated upstream facade/classification extraction.


<a name="qml-06"></a>

## INC-QML-06

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

INC-QML-06 legacy ceilings: extract.py 9009, cli.py 4949, watch.py 2527. Owner Qt integration maintainer; focused policy/root/publication hooks only. Exit coordinated upstream facade/writer extraction. New handwritten modules/tests remain below300 lines.

<a name="qml-07"></a>

## INC-QML-07

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

INC-QML-07 retains the seventeen requirements and sixty-eight acceptance IDs.
Production normal-QML-edit/update/watch and no-change parity verify the existing
REQ-QML-011 criteria. No additional top-level increment is needed
for the agreed profile; computed/runtime/framework/plugin behavior remains an
explicit unsupported boundary. Final hosted verification is recorded in
VALIDATION.md and the delivery PR, not inferred from local tests or earlier runs.

<a name="qml-07-measured-modularity-exceptions"></a>

### INC-QML-07 measured modularity exceptions

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

## INC-QML-08a native source compatibility

The bounded native syntax slice of REQ-QML-018-AC02 is locally implemented and
verified. Parser-only compatibility normalization accepts empty-brace parameter
defaults and `Q_UNUSED` statements without a caller semicolon. Its arguments
retain evaluated calls rather than being erased. C++ numeric digit separators
remain part of numeric tokens before quote masking, preserving later signal and
member ownership. Original source bytes remain authoritative for identities and
spans, including BOM, CRLF and Unicode; malformed/incomplete controls still fail
closed. Analysis does not execute corpus code or weaken publication guards.

AST cache schema 6 retires earlier syntax records even at the same package
version. Qt policy epoch 2 invalidates an earlier unchanged-source analysis stamp.
Production regressions cover actual CLI refresh, prior graph/manifest/state/cache
retention on failure and ordinary-C++ warm-cache preservation. The local focused,
broad and installed-artifact evidence is recorded in
[validation](VALIDATION.md#inc-qml-08a-native-source-compatibility).

The new `graphify/extractors/qt_cpp_compat.py` is 142 physical lines;
`graphify/extractors/qt_cpp_syntax.py` is 234. The existing cache owner remains
1782 lines without growth. Its focused schema hook has a 1782-line ceiling, owned
by the Qt integration maintainer, with upstream-coordinated behavior-preserving
extraction of the source-cache interface as its exit condition.

At the native-syntax checkpoint, INC-QML-08 and REQ-QML-018 remained incomplete. Header-classification assessment,
bounded qmake extensions, typed factory/member providers, child-service signal
chains and combined whole-project/safe-subroot adoption stay within the remaining
INC-QML-08a/08b/08c work. Header discovery needs its own agreed requirement before
implementation; direct parser success does not prove production admission. Local
native-slice proof and an accepted scoped installed result do not establish these
additional capabilities. New reviewed-head hosted lanes have not been executed
for this source change; prior INC-QML-07 proof remains revision-specific.

## INC-QML-09 community presentation

Upstream disposition: this generic viewer increment and REQ-QML-019 are deferred.
The implementation, tests, counts and owner measurements below describe the
frozen complete fork. The narrowed contribution retains baseline generic HTML
behavior and separate Qt payload/tooltip/omission contracts.

HTML community recovery validates complete partition membership and uses the
existing clustering and hub-labeling interfaces on an export-local view. A
custom graph's analysis is loaded beside that graph. Missing names become usable
local labels; stale partition names do not migrate to newly computed groups.
Failed or skipped publication retains prior output and reports its true CLI
outcome. The atomic writer and canonical graph owners remain unchanged.

The viewer contract at this historical checkpoint starts with Select All checked and admits all
exported view nodes and edges before network construction. Large graphs retain
their complete labeled aggregate and supported cap. Overview optionally selects
the ten largest source communities with stable member-count/ID ordering and
unchecks Select All. Filters, search and all/none controls retain their roles.
All exported raw semantic metadata remains available. No saved-view state,
model request or analyzed-project execution is introduced. AC01–AC04 have local
exporter/CLI and emitted-script proof, with the reviewed installed artifact
checked. The focused selection passes 157 cases without skips; built-artifact
checks pass three cases. Prior selection-policy tests remain historical evidence
in VALIDATION. Browser visual, other-platform and new hosted checks are unexecuted.

Historical handwritten owners measure [frozen html_communities owner](https://github.com/SlinkyRamey/graphify/blob/82a4f296446b4cc219ffecfe3345a037e9c362e4/graphify/exporters/html_communities.py) (79 physical lines),
[frozen test_html_community_recovery owner](https://github.com/SlinkyRamey/graphify/blob/82a4f296446b4cc219ffecfe3345a037e9c362e4/tests/test_html_community_recovery.py) (293) and [frozen test_html_initial_view owner](https://github.com/SlinkyRamey/graphify/blob/82a4f296446b4cc219ffecfe3345a037e9c362e4/tests/test_html_initial_view.py) (234).
Touched legacy ceilings are exporters/html.py (763) and cli.py (4966).
Owner: presentation maintainer, coordinating CLI/export upstream ownership.
The HTML module keeps one inline viewer state across layout, filtering, search
and node details; the CLI retains only adjacent-path and outcome hooks.
Exit: a characterized, upstream-coordinated extraction of the cohesive viewer
state into its own frontend resource, preserving emitted payload, controls,
escaping and packaging. This exception permits the measured cohesive correction,
not arbitrary growth or speculative layers.

## INC-QML-10 native source ownership

**Locally verified source/context correction and reviewed installed artifact.** This correction uses existing
REQ-QML-008-AC02, REQ-QML-016-AC01/AC04 and REQ-QML-017-AC02/AC04. The initial
seventeen-requirement/sixty-eight-criterion evidence remains the original bounded
profile, not proof of the newly reproduced ownership cases.

Forward declarations retain their canonical facts/IDs without competing
with a unique complete class definition for out-of-line member/event ownership.
AST body presence supplies additive `is_definition` authority through the Qt
class overlay. Mapping also needs exact accepted `definition_file` and
`definition_location` with callable/class ownership; true duplicate complete
definitions or unsupported evidence remain unresolved. The focused owners are
`qt_cpp_mapping.py`, `qt_cpp_exposure.py` and `qt_event_index.py`.

Qt policy epoch 3 refreshes earlier same-package analysis facts; AST cache schema
6 stays unchanged. The current context/ownership/upgrade selection passes 88
cases; the final broad suite passes 954 with seven documented skips and one
existing warning. Earlier 78-focused/944-broad results describe the intermediate revision
before accepted-context body provenance was repaired.
Actual same-package CLI refresh and failure-retention controls use prior persisted
products; the reviewed wheel is built and installed at version 0.9.74 with 152
Python payloads matching source/wheel/installation. No source identity is removed,
generic C++ ownership rewritten or connection inferred merely because a node is
isolated. Remaining INC-QML-08 source/metadata/provider gaps and D12 HTML
presentation policy are unchanged. See [D13](ARCHITECTURE.md#d13--complete-definitions-and-exact-provenance-authorize-native-ownership)
and the [executed validation](VALIDATION.md#inc-qml-10-native-source-ownership).

Measured production owners are `qt_cpp_mapping.py` 233 physical lines,
`qt_cpp_exposure.py` 134, `qt_event_index.py` 111, `qt_qml_bridge.py` 110 and
`qt_incremental.py` 114. New `test_qt_cpp_definition_ownership.py` is 261 lines
with 18 cases; `test_qt_cpp_owner_upgrade.py` is 91 lines with four cases. All
remain below the 300-line handwritten-file ceiling.

`enrich_qt_cpp` preserves exact producer source file/span when borrowing unchanged
complete-class context. Repeated fresh/context representations of one body now
deduplicate consistently; distinct body locations remain ambiguous. Borrowed
dictionaries and canonical class/member/emission IDs remain unchanged. New
`test_qt_cpp_context_ownership.py` has ten production direct/pipeline/build/reload
cases and 145 physical lines. All ten pass, including equivalent paths and
distinct-body/legacy/missing-evidence controls. The final rebuilt artifact's 152
Python payloads match reviewed source and installation; final expanded broad
proof passes 954 cases. This internal transport correction adds no persisted field or
policy epoch beyond the historical INC-QML-10 policy 3/schema 6 snapshot.

At the INC-QML-10 checkpoint, INC-QML-11 remained planned. Recursive inheritance compatibility at that revision did not
extend member endpoint lookup beyond immediate bases; a declared grandparent
signal needs a separate bounded lookup correction and regression/installed proof.
This gap belongs to existing REQ-QML-016-AC01/AC04 and is not closed by ownership
counts or by forcing edges onto unsupported/isolated nodes. Browser, other-platform
and new hosted evidence remains separate from the local proof recorded here.

## Constructor/source/view corrections (INC-QML-12/13)

The generic C++ producer now records missing constructor prototypes and bounded
class/constructor source proof through a focused helper. Exact complete-class,
prototype, signature, scope and source containment establish supported singleton
constructor ownership before the existing canonical merge. Supported singleton IDs and
original source spans remain; collapsed overload/delegation cases, malformed
facts and conflicting scope/owner/signatures cannot gain native class authority.
A source-proven callable may still contain observed facts, and independent local
QML handles retain their own evidence.

Ordinary utility-member and local-class occurrence facts now link to their
uniquely accepted source callables when no Qt class definition is admitted.
Class IDs/native roles remain unavailable; this is source containment. Source
facts are not hidden, merged by label or connected by guessed runtime calls.
Sites with unproved callable ownership instead retain exact containment by a
unique accepted source file. This file relationship leaves callable/class/target
identities and unresolved status unchanged. Rejected file-role/provenance evidence
cannot authorize containment.

The full generic aggregate-inspector change remains historical under deferred
REQ-QML-019. Internal/external source-edge counts remain a REQ-QML-020 membership
prerequisite; distinct-community labels and isolate explanations are deferred.
Native constructor and source-containment changes remain retained.
The frozen aggregate HTML inspector reports
internal source edges, external source edges
and distinct connected communities. Closed connected groups are distinguished
from genuine isolates; counts use the canonical input graph, not duplicated raw
serialized occurrences. Existing Select All, source-node Degree and bounded
aggregate rendering remain intact. Pre-aggregated callers without original
source counts display unavailable counts.

The INC-QML-12/13 artifact's AST schema 7 and policy 5 invalidate stale same-version
facts. Its local source and
reviewed installed-artifact verification passes; exact evidence belongs to
VALIDATION.md and tests/TRACEABILITY.md.
Browser/system appearance is a separate unexecuted gap. At this earlier checkpoint, INC-QML-11 inherited
endpoint lookup and INC-QML-08 metadata/provider adoption remained unfinished.
At the INC-QML-12/13 review, INC-QML-14/REQ-QML-020 was recorded as a planned
metadata-membership correction: indexes resolved accepted targets without general
declaration-to-file edges. That policy-5/schema-7 artifact remains historical
evidence for constructor/source/view corrections. INC-QML-14 is now locally
complete as recorded below; earlier source-owner and viewer-count results
do not complete it.
At the INC-QML-12/13 checkpoint, INC-QML-15 retained the generic overloaded-constructor ID/location-parity
gap. Native source-file links passed their scoped parity checks; exact generic
overload identity was unverified at that revision.

## Project/resource membership projection (INC-QML-14)

Status: **Locally complete; Verified within the bounded static source profile**.
Production, lifecycle/consumer and reviewed installed-artifact evidence passes
under the existing REQ-QML-020-AC01–AC03. No requirement or acceptance identity is
added. [D15](ARCHITECTURE.md#d15--project-membership-is-independent-of-component-use)
separates observed package/resource membership from component use or Qt execution.

`graphify/qt_project_membership.py::resolve_project_memberships` projects accepted
`qt_source` and `resource_alias` declarations into independent
`membership_resolution` sites. It consumes the accepted QtProjectIndex corpus and
explicit fresh AST identities; borrowed declarations/context remain read-only.
The helper returns fresh derived nodes/edges while replacing only its own stale
scratch sites/mechanisms. Identity-based pipeline publication prevents a replaced
borrowed site from shifting append offsets or leaking unrelated context facts.

Each declaration contains its site with context `qt_membership_site`. A uniquely
resolved site references the actual canonical file/component with context
`qt_project_source` or `qt_resource_membership` and confidence `EXTRACTED`. Original
source spans, declaration identity, module/alias context and bounded status/reason/
evidence remain on the site. Missing, duplicate, conditional, generated and unsafe
targets retain unresolved/unsupported attempts without a target edge. The helper
performs no source read, path expansion, build/QML/plugin execution or filename-
based endpoint reconstruction; raw facts and existing lookup behavior stay intact.

The narrow `graphify/qt_qml_pipeline.py` hook runs after canonicalization in its
existing scratch join. Coverage uses `QML-RESOLVE-001`; invalid transport or an
unexpected failure reaches `QML_RESOLUTION_FAILED` and the existing publication
guard. No parser or writer is added. Qt policy epoch 6 refreshes earlier
same-version graphs; AST cache schema stays 7 and existing graph/manifest/root/
analysis-state sequencing owns retention, corrected retry and idempotence.

The helper/source-test/pipeline/lifecycle-test owners measure 187/283/85/267
physical lines, all below the 300-line handwritten-file ceiling. The helper API
accepts optional `fresh_ast_ids=()` and returns `(derived_nodes, derived_edges)`.
Before the two additional graph-direction variants, the new source/lifecycle
suites pass 37 focused cases in 8.77 seconds and contribute those cases to the
reviewed-wheel broad selection:
**1081 passed / 7 skipped / 1 existing warning** in 135.53 seconds. A separate
cross-language/C# compatibility selection passes 97 cases in 4.05 seconds.
The later focused direction expansion passes 39 cases in 9.50 seconds, including
explicit CMake/qmake positives in both graph orientations. The unchanged
production artifact's broad 1081-case result remains its own earlier selection.
Exact assignments, commands and skip reasons belong to
[validation](VALIDATION.md#inc-qml-14-membership-projection) and
[traceability](../../tests/TRACEABILITY.md#project-membership-projection).

The reviewed production tree is `a8656510281354913dcc92a3f733b70183874fbd`; the
version-0.9.74 wheel SHA256 is
`221c7efa8db69e6cad048aea67d88fe3049cf98bae933816017aba833525dc6c`.
All 155 Python payloads are byte-equal across reviewed source, wheel and isolated
installation. The installed public CMake/qmake/qrc fixture publishes 30 nodes,
31 edges and six resolved memberships (five source and one resource), including
an uninstantiated QML component. Real query/explain/affected/HTML commands exit 0.
Malformed qrc with force/partial options exits 1 and retains four durable products;
repair and repeat exit 0 with unchanged graph bytes on repeat. This is actual
installed static-analysis evidence, with no Qt application/build execution.

No new browser, hosted, other-platform or executable Qt proof is claimed. Earlier
INC-QML-12/13 completion and policy-5 artifact evidence remain revision-specific;
At that membership checkpoint, INC-QML-08 adoption was partial and INC-QML-11/15 remained planned. Plan review
identified no additional required increment for the completed membership profile.

## Final adoption delivery

This section preserves the local adoption checkpoint before integration with
newer upstream. Its schema/policy, suite totals and pending outcomes belong to
that revision. Later integration evidence is linked above; it does not rewrite
these earlier results or prove a later contribution revision.

INC-QML-11 resolves bounded multi-level inherited signals with declaration-owned
endpoints and conservative shadow/conflict/cycle rejection. INC-QML-15 preserves
distinct constructor signatures, original locations and declaration/definition
ownership through reload and updates. Explicit emit/Q_EMIT observations survive
unavailable declarations without inventing a signal endpoint or delivery call.

INC-QML-08a admits bounded current-file qmake PWD paths and source-visible C++
header markers, retaining C/Objective-C and ambiguous-header behavior. INC-QML-08b
uses canonical declared pointer/lvalue-reference APIs for factory/member providers
and child-service properties, calls and QML subscriptions. Lexical shadows,
conditional/ambiguous types, unsupported declarators and borrowed/corrupt source
proof remain unavailable. Ordinary static analysis executes no Qt application,
factory, build hook or plugin.

INC-QML-29–38 preserve reference callables, logical dependency direction, exact
source-file role and occurrence identity across assembly, JSON, reload, query and
affected consumers. Integrity preflight runs before comparison shortcuts or
publication. Removal uses accepted prior ownership proof; partial refresh cannot
authorize orphan deletion. First minted external nodes receive semantic origin;
an unchanged second update cannot rewrite valid bytes solely for origin backfill.
Per-occurrence event transport remains bounded without recursive literal encoding.
The adoption checkpoint uses AST cache schema 12 and Qt policy 18.

INC-QML-08c is locally complete for Windows x64/Python 3.12.14 with pinned parser
0.25.2/language-pack 0.11.0. The reviewed installed wheel passes 3,024 tests with
36 existing skips, and all 179 Python payloads match the reviewed source exactly.
Actual installed CLI CMake/qmake whole-root/safe-subroot initial/repeat profiles
pass, with hand-checked facts and equal graph bytes. Individual acceptance,
failure/repair and mutation proof is in [traceability](../../tests/TRACEABILITY.md#final-adoption-delivery);
commands and digest are in [validation](VALIDATION.md#final-adoption-delivery).

At this adoption checkpoint, the final full source suite has 8,630 passes,
59 pre-existing failures and 178 skips; no new failure identities appear. Full
typing retains baseline errors with no added diagnostics. The hosted OS/Python
lanes, live service proof and native browser/device interaction remain unverified
at this checkpoint. Static declared API compatibility
does not establish Qt build success, plugin availability, runtime conversion,
overload dispatch, allocation, ordering, lifetime or thread safety.
