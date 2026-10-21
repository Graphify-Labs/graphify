# Qt/QML extension code reference

The first table records baseline owners, with their current extension seams.
[AUDIT.md](AUDIT.md) retains historical line evidence. The second table lists
implemented QML/Qt owners through INC-QML-06 and local INC-QML-07 consumer hooks.
Revision-specific verification remains in [VALIDATION.md](VALIDATION.md).

INC-QML-54's upstream 0.9.92 seams are recorded
[below](#upstream-0992-integration-seams--inc-qml-54). Corrected source `67bb2022`
passes its complete local source suite and source-matched isolated installed
profiles, with explicit skips. The historical `90578033` full-source failure is
preserved. Native CI coverage correction and fresh hosted gates remain separate;
earlier schema-13/installed-tool checkpoints remain revision-bound. The
[corrected checkpoint](../../tests/TRACEABILITY.md#committed-corrected-integration-checkpoint--67bb2022)
owns exact source/tree/wheel identities, commands and evidence limits.

| Existing owner | Role and extension considerations |
| --- | --- |
| `graphify/detect.py` | `classify_file`, `detect`, `detect_incremental`, code extensions and corpus boundaries; exact Qt metadata names/suffixes use shared admission |
| `graphify/extract.py` | Dispatch, language-family handling, `extract_cpp`, aggregate `extract`, ID/path normalization and resolution passes |
| `graphify/extractors/` | Focused language extractors; preferred home for source-local QML and Qt metadata responsibilities |
| `graphify/extractors/engine.py` | Shared AST traversal and generic C++ configuration; preserve normal C++ signatures, calls and macro normalization while a separate Qt overlay refers to these declaration IDs |
| `graphify/resolver_registry.py` | Post-extraction cross-file resolver activation; Qt context and exact metadata filenames must activate resolution after QML-only, C++-only or metadata-only changes |
| `graphify/cache.py` | Persistent generic per-file cache; Qt source/metadata and native syntax in an explicit Qt context bypass reads/writes under `qt_incremental` policy |
| `graphify/watch.py` | Manual update/watch rebuild, watched-file admission, incremental extraction and persistence guards |
| `graphify/install.py`, `graphify/codex_hook_command.py` | Installer owns hook JSON merging/publication; focused serializer owns literal Codex command transport and rejects unsupported Windows shell/command boundaries before settings access; [shared compatibility decision](../COMPATIBILITY.md#dec-core-01--windows-hook-literal-transport) |
| `graphify/build.py` | Graph merge/provenance and simple graph construction; independent source sites/endpoint-role facts retain distinct Qt mechanisms |
| `graphify/paths.py` | `load_node_link_graph` restores contract-versioned QML edge orientation from serialized endpoints on undirected reload |
| `graphify/__main__.py`, `graphify/cli.py` | CLI dispatch/facade and query/explain/path/affected implementation entry points |
| `graphify/serve.py` | Optional MCP query and graph consumer contracts |
| `graphify/export.py`, `graphify/exporters/` | Serialization and presentation consumers |
| `tools/skillgen/fragments/` | Authoritative assistant instruction source; generated outputs require skillgen checks |
| `pyproject.toml`, `uv.lock` | Python support, parser dependencies/extras, explicit packaged modules and frozen environment |
| `.github/workflows/ci.yml` | Full Ubuntu source matrix with reviewed-wheel/disposable-service proof, focused native Windows compatibility, retained revision/integrity evidence and PR-only obsolete-run cancellation; [shared compatibility procedure](../COMPATIBILITY.md#hosted-runner-proof-procedure) owns setup, cleanup and execution gaps |
| `tests/test_detect.py`, `tests/test_languages.py`, `tests/test_extract.py` | Detection, language and aggregate extraction regression coverage |
| `tests/test_build.py`, `tests/test_cache.py`, `tests/test_watch.py` | Graph integrity, cache and incremental persistence regression coverage |

| Implemented owner | API and responsibility |
| --- | --- |
| `graphify/extractors/qml.py`, `qml_ast.py` | `extract_qml`, lazy optional parser and source/AST limits; failed parses return diagnostics and no authoritative declarations |
| `graphify/extractors/qml_facts.py` | `FactBuilder`, `make_qml_id`, fixed-width `make_scope_key`, span helpers and bounded `encode_metadata`/`qml_metadata` literal transport |
| `graphify/extractors/qml_declarations.py` | `Declarations`: components, inline scopes, objects/groups/members/imports and conservative template-body barriers |
| `graphify/extractors/qml_metadata.py` | `extract_qmldir`/`parse_qmldir`: standard-library literal records, not `.qmltypes` or plugin execution |
| `graphify/qml_resolution_types.py` | `Resolution`, exact-candidate selection, accepted relative references and portable site/edge values |
| `graphify/qml_module_index.py` | `QmlModuleIndex`: ordered explicit roots, provider/version/internal/singleton lookup and separate type/script namespace roles |
| `graphify/qml_scope.py` | `QmlProjectIndex.resolve_type`, `resolve_member`, `follow_member`; source/component/object/inheritance lookup only |
| `graphify/qml_resolution.py` | `build_qml_index`, `resolve_qml_project`: run-owned indexes and append-only fresh import/type-resolution sites |
| `graphify/extractors/qml_expressions.py`, `qml_js_scopes.py` | `collect_relationships`, per-occurrence facts and JS binding/shadow/reassignment rules; no generic `raw_calls` |
| `graphify/extractors/qml_script_syntax.py`, `qml_scripts.py` | `parse_script`, `collect_qml_scripts`: bounded byte-preserving directives and QML-owned overlays of admitted JS resources |
| `graphify/qml_relationship_lookup.py` | `RelationshipLookup`: scoped alias chains/cycles and imported script visibility |
| `graphify/qml_relationships.py` | `resolve_qml_relationships`: fresh expression status and read/call/alias/subscription/notify-signal projection; borrowed context is read-only |
| `graphify/qml_projection.py` | `allows_qml_script_edge`: exact typed script-file import proof and QML script-function calls through the existing builder guard |
| `graphify/qml_safety.py` | `qml_refresh_required`, `require_qml_watch_root`, `require_complete_qml`: conservative refresh and fail-before-publication checks |

`extract.py` forwards explicit roots, overlays admitted scripts before aggregation,
then joins QML project and relationship facts after generic resolution. It records
join failures for publication rejection. Generic JS/C++ owners are preserved;
Qt/QML extractor children do not import the facade. The imported Markdown
extractor's ambient-root exception is recorded in DESIGN.md. [DESIGN.md](DESIGN.md) defines the current
interfaces and [ERRORS.md](ERRORS.md) owns their diagnostic contracts.

The Qt C++ overlay owns source-local meta-object declarations, emissions,
connect/disconnect syntax, loader/access sites and literal context/initial-property
facts. Its resolver owns scoped module/resource joins and
engine/component/view-to-QML-object provenance. It must support native C++ events
without requiring QML parsing. REQ-QML-008, REQ-QML-016 and REQ-QML-017 in
[REQUIREMENTS.md](../REQUIREMENTS.md) define the separate exposure, event and reverse
object-access acceptance contracts; none is implemented by the imported generic
C++ extractor alone. [DESIGN.md](DESIGN.md) records implemented relation contexts and
source ownership, including private-slot meta-object endpoints and compatible
ordinary member-pointer receivers.


## Native Qt source owners

The corrected semantic seams are `QtQmlAccessIndex.member`/`find_child`
(INC-QML-17), declaration-owned context/provider joins (INC-QML-18), shared native
type/alias authority (INC-QML-19), and bounded loader admission (INC-QML-20).
[FOLLOWUP_AUDIT.md](FOLLOWUP_AUDIT.md) preserves baseline findings and current
dispositions. Same-file canonical IDs, static reflection API shadows and failed
Windows replacement retention are corrected by INC-QML-21/22/23; the following
source/publication seams describe the wider INC-QML-24–27 correction scope.

| Boundary | Implemented owner |
| --- | --- |
| Annotation normalization/original source view | graphify/extractors/qt_cpp_syntax.py |
| Canonical class/member mapping | graphify/extractors/qt_cpp_mapping.py |
| Exposure/property/registration collection | graphify/extractors/qt_cpp_exposure.py, qt_cpp_properties.py, qt_cpp_registration.py |
| Portable Qt transport | graphify/extractors/qt_cpp_facts.py |
| Source event/access collection | graphify/extractors/qt_cpp_events.py, qt_cpp_access.py and their call/variable/pattern helpers |
| Scoped native QML provider/member lookup | graphify/qt_qml_bridge.py, qt_qml_bridge_members.py |
| Native event projection | graphify/qt_event_index.py, qt_event_resolution.py |
| Component/object/provider access | graphify/qt_qml_access_index.py, qt_qml_access_resolution.py, qt_context_bindings.py, qt_qml_event_access.py |
| Post-canonical scratch orchestration | graphify/qt_qml_pipeline.py |
| Cross-family endpoint proof guard | graphify/qt_qml_projection.py |

Metadata readers are publicly discovered/dispatched with INC-QML-05. Their index
consumes accepted facts without executing a build or expanding the corpus.

| Metadata boundary | Implemented owner |
| --- | --- |
| Bounded original-byte source facts | `graphify/extractors/qml_project_read.py` |
| Literal Qt module/source declarations | `graphify/extractors/qml_cmake.py`, `qml_cmake_syntax.py`, `qml_qmake.py` |
| Generated tooling descriptions | `graphify/extractors/qml_types.py` |
| Entity-safe resource declarations | `graphify/extractors/qml_resources.py` |
| Exact project/member/resource lookup | `graphify/qt_project_index.py`, `qt_resource_index.py` |
| Source/generated conflict evidence | `graphify/qt_generated_conflicts.py` |


INC-QML-05 public seams: detect.classify_file exact CMakeLists.txt and Qt suffixes;
extract._get_extractor/_safe_extract forward the explicit scan root; collect_files
uses identical named-file/ignore/root admission. LANGUAGE_EXTRACTORS exposes the
four bounded metadata readers. qt_qml_pipeline owns project/native index ordering
and warning attachment. Partial readers bypass syntax cache and reject publication.


INC-QML-06 public seams: extract(...qml_import_roots=None, refresh_native=False) carries
ordered lookup roots and native cache policy to a per-run Qt pipeline. Worker
three/four-tuples remain compatible; a fifth bool carries context policy.
qt_analysis_state.inspect_qt_analysis and commit_qt_analysis separate inspection
from successful publication. qt_incremental.plan_qt_refresh never expands corpus.

INC-QML-07 consumers use `qt_qml_search.search_attributes` for bounded public semantic
fields; raw transport and opaque scope keys stay outside search text.
`qt_affected.owned_ancestors` promotes current source-owned dependency sites to
their enclosing members/components. `qt_relationship_views` and `qt_html` retain
distinct event/access evidence in HTML; `qt_coverage` reports unresolved source
sites separately from edge confidence. `qt_export` supplies lossless nested JSON
properties and logical endpoints for Qt graph-database payloads. Existing CLI,
MCP, report, HTML and export owners call these focused helpers.
See [EXPORT_MATRIX.md](EXPORT_MATRIX.md) for exact reload/omission contracts.

The generated assistant AST stage calls `inspect_qt_analysis` read-only, passes
its ordered `import_roots` and `has_qt` to `extract`, then gates AST publication.
It does not commit `.qt_analysis.json`; CLI/watch retain checkpoint ownership
after successful graph/manifest publication. The generator's exact sanctioned
line policy retains frozen baseline checks; its current 1,450-line legacy
exception and extraction exit are in [PLATFORM_MATRIX.md](PLATFORM_MATRIX.md).

## Adoption native parser compatibility owner

`graphify/extractors/qt_cpp_compat.py::recover_cpp_syntax(source, code, *, parse, walk)`
is a pure equal-length parse-view helper. `needs_recovery(code)` is its cheap
candidate admission. `qt_cpp_syntax` owns source reads, lexical masking, parser
errors and limits and calls this helper before its final syntax gate. Neither
module imports the extractor facade. Empty default clauses and Qt-unused argument
syntax recovery do not own source facts or runtime interpretation.

`qt_cpp_syntax.lexical_code` also owns preprocessing-number token recognition
before character-quote masking, preserving numeric separators and later source
visibility. The unchanged numeric token remains subject to parser validation.

`graphify/cache.py` owns the AST schema epoch; `graphify/qt_incremental.py` owns
native refresh relevance and Qt policy fingerprint. Graph/manifest/analysis-state
publication remains in the existing CLI/watch owners. The migration keeps those
owners and interfaces intact and introduces no alternate cache or graph writer.

## HTML community-view interfaces

`graphify/exporters/html_communities.py::prepare_html_communities` owns complete
large-view partition validation and local grouping/name recovery. The existing
HTML exporter owns aggregate projection, deferred selection and atomic output.
The CLI resolves an explicit graph's analysis beside that graph and reports
skipped/failed view publication as unsuccessful. These are presentation owners;
source extraction, graph identities and analysis persistence remain unchanged.

INC-QML-16 removes the Overview control and ranking state while retaining checked
full startup, community filters, search, Select All/None and aggregate rendering.
It is **Locally verified at emitted-script and reviewed installed-artifact
boundaries** under changed REQ-QML-019-AC04 and new REQ-QML-021-AC01–AC03.
Native browser/device and other-platform behavior remains unverified.

| Owner | Camera/control responsibility |
| --- | --- |
| `graphify/exporters/html_navigation.py::MIDDLE_PAN_SCRIPT` | Isolated camera-only IIFE; incremental client delta/current-scale movement, input/capture guards and cleanup; no graph/dataset writes or wheel hook |
| `graphify/exporters/html.py::to_html` | Remove Overview markup/function/state/ranking; inject the helper once after existing network/initial-physics setup; retain emitted payload and selection/search/inspector interfaces |
| `tests/test_html_middle_pan.py` | Production emitted-script geometry, termination, invalid-camera/capture and coexistence/immutability evidence; current local source checkpoint passes |
| `tests/test_html_initial_view.py` | Retained checked startup and filters/all/none/search/partial-membership behavior; obsolete Overview expectations are replaced |

The camera helper and new tests remain below 300 lines. The cohesive legacy HTML
owner retains its 810-line ceiling; current integration measurements belong to
DESIGN/validation. [D16](ARCHITECTURE.md#d16--middle-button-input-owns-only-the-temporary-camera)
defines temporary camera ownership. The existing vis camera API is reused with no
new SDK, persistence operation, graph diagnostic or Qt policy/schema change.
Actual navigation/selection outcomes pass 60 focused cases and reviewed installed-
artifact script checks pass. Source/wheel/isolated installation contains 156 byte-
equal Python payloads. Native browser visual/device, new hosted and other-platform
checks remain explicit gaps; this evidence does not establish a full device profile.

## Native source-ownership correction seams (INC-QML-10)

This table records the historical INC-QML-10 correction and its verified artifact.
Current policy/schema and constructor seams are recorded in INC-QML-12/13 below.
These owners retain their interfaces and operate after generic canonical
identity/provenance is available:

| Owner | Correction responsibility |
| --- | --- |
| `graphify/extractors/qt_cpp_mapping.py::CppMapping` | Complete-class eligibility and exact out-of-line callable mapping from accepted definition file/location and class containment |
| `graphify/extractors/qt_cpp_exposure.py::_class_facts`, `enrich_qt_cpp` | Additive `is_definition` from AST body presence; retain forward facts/IDs and exact producer source file/span when carrying fresh or accepted-context complete-body authority into per-run binding |
| `graphify/qt_event_index.py::QtEventIndex` | Establish class-qualified event endpoints from unique complete definitions; preserve real ambiguity/unavailable evidence |
| `graphify/qt_qml_bridge.py::QtQmlBridgeIndex` | Require accepted complete class evidence for native provider/meta-object availability; a retained forward fact does not establish a provider |
| `graphify/qt_incremental.py::QT_POLICY_VERSION` | Epoch 3 analysis invalidation at unchanged package/source versions; AST schema remains 6 under the cache owner |

`definition_file`/`definition_location` remain accepted canonical attributes and
do not replace header declaration provenance. Qt member/emission/access facts
keep their original implementation spans and refer to proven canonical owners.
Class source file/span belong to the original producer. `enrich_qt_cpp` preserves
both when borrowing complete-class facts so `CppMapping.bind_classes` recognizes
the same body consistently with fresh AST records. Context node/metadata
dictionaries remain immutable inputs; distinct body locations do not coalesce.
Direct and actual pipeline/build/reload context tests pass. This internal record
transport fix left persisted fact shape, policy 3 and AST schema 6 unchanged at
that revision; INC-QML-12/13 subsequently use policy 5/schema 7.
The source/root, metadata validation, checkpoint and graph-writer boundaries are
unchanged. [D13](ARCHITECTURE.md#d13--complete-definitions-and-exact-provenance-authorize-native-ownership)
and [DESIGN.md](DESIGN.md#native-ownership-authority-inc-qml-10) define authority
and unresolved-case limits; [VALIDATION.md](VALIDATION.md#inc-qml-10-native-source-ownership)
records that source/context, final broad and reviewed installed-artifact proof.

INC-QML-11 uses `QtEventIndex._lookup_members` for bounded ancestor candidates,
`_bases` for canonical complete-class proof, and `_base_access` for source-owned
inheritance visibility. `member` stops name lookup before role/signature filtering;
`inherits(..., public_only=True)` gates external member-pointer conversion paths.
The producer `qt_cpp_exposure._class_facts` owns each canonical base/access pair.
Both files remain below 300 lines at this increment (186 and 184). No mutable
project state or new persistence owner is introduced. Policy 13 retires derived
facts; installed integration and explicit-emission admission remain separate exits.

## Constructor and source-containment seams (INC-QML-12/13)

| Owner | Implemented responsibility |
| --- | --- |
| `extractors/cpp_constructors.py` | Bounded AST class/constructor facts, exact prototype/type/scope join, ambiguity and consumer authority guard |
| `extractors/engine.py` | C++-only producer hook; no second extractor or analyzed project execution |
| `extractors/resolution.py::_merge_decl_def_classes` | Invoke constructor binding before existing ID-collision canonicalization; reject unsafe constructor merges |
| `extractors/qt_cpp_mapping.py::CppMapping.bind_classes` | Preserve exact source callable while preventing rejected/legacy constructor substitution by a header prototype |
| `extractors/qt_cpp_variables.py`, `qt_cpp_events.py` | Unproved constructor class authority cannot establish native `this` or an implicit emission receiver type |
| `extractors/qt_cpp_exposure.py::_class_facts` | Member/local-class source containment by unique accepted callable without native class/QObject/exposure authority |
| `exporters/html.py::to_html` and emitted inspector | Actual canonical internal/external source-edge counts and distinct connected-community counts; no graph mutation |
| `qt_source_containment.py`, `qt_qml_pipeline.py` | Exact accepted file-to-unknown-occurrence containment, explicit fresh AST authority and unchanged unresolved semantic roles |
| `cache.py`, `qt_incremental.py` | Historical INC-QML-12/13 artifact: AST schema 7 and Qt policy 5 same-package refresh; INC-QML-14 subsequently uses policy 6 with the same persistence owners |

Constructor metadata version 1 carries bounded original names/lexical scope,
source spans, exact type-signature hashes and rejected/accepted class-binding
outcome. Canonical declaration and definition IDs remain authoritative; absent
or conflicting proof cannot gain an endpoint through Qt mapping. Source-only
containment does not change class IDs/native roles. D14 and DESIGN.md describe
these boundaries. Legacy module measurements/exceptions are versioned in
DESIGN.md; tests and exact commands belong to validation/traceability.

## Project-membership seams (INC-QML-14)

The initial INC-QML-14 profile is locally verified. INC-QML-39 extends accepted
input identity; focused and broader local source regressions pass. A fresh
artifact initially reproduced the separate INC-QML-40 facade gap; its correction
now passes fresh installed alias smoke. The applicable corrected source/native
profiles pass at the [verified hosted checkpoint](../../tests/TRACEABILITY.md#verified-hosted-runner-checkpoint--10cb15a),
with explicit capability exclusions and optional-wheel evidence limits.
The INC-QML-49/50 integration uses Qt policy 22 and AST schema 13 under D26/D27.
The owners below implement
REQ-QML-020-AC01–AC03 without a new parser or persistence pipeline.

| Owner | Correction responsibility |
| --- | --- |
| `graphify/qt_project_membership.py::resolve_project_memberships` | Independent source-owned membership sites; literal/unique accepted canonical targets; canonical contained input identity admits real path aliases without rewriting lexical provenance, reading target content, expanding the corpus or mutating borrowed facts |
| `graphify/qt_project_index.py::QtProjectIndex` | Existing accepted module/source/resource evidence and lookup behavior; projection does not change the index's runtime-uncertainty boundary |
| `graphify/qt_qml_pipeline.py::resolve_qt_qml` | Narrow post-canonicalization helper hook, scratch publication and existing resolver failure guard |
| `graphify/qt_incremental.py::QT_POLICY_VERSION` | Historical INC-QML-14 policy-6/schema-7 refresh; current policy 25/schema 13 retain the same owners, preserve combined upstream/Qt facts and refresh prior followed Qt metadata/resource/native-header and RC prerequisite analysis at unchanged package/source versions |
| `tests/test_qt_project_membership.py` | Public literal, ambiguity, source/span, direction and immutable-input production regressions; exact executed coverage belongs to traceability |
| `tests/test_qt_project_membership_updates.py` | Real CLI/watch changes, policy upgrade, prior-product retention/repair/repeat, aggregate inspection and replacement publication without borrowed mutation |
| `tests/test_qt_project_membership_aliases.py` | Real Windows short-path and parent-symlink admission; unchanged installed-smoke assertions, canonical/cold/warm/full/manual/watch equality, foreign/conflicting transport rejection and durable retention/recovery |

Declaration-to-site `contains` uses `qt_membership_site`; a resolved site's
`references` uses `qt_project_source` or `qt_resource_membership` with confidence
`EXTRACTED`. Unresolved status/reason retains the source attempt without a guessed
endpoint. The helper, original source test, pipeline, lifecycle test and alias
test measure 198/283/106/267/222 physical lines, each below 300. Initial INC-QML-14
CLI/watch, retention, consumer and reviewed-artifact evidence is recorded
separately from INC-QML-39 proof. The API accepts optional `fresh_ast_ids=()` and returns derived nodes/
edges; starting node/edge-object identities authorize replacement publication
without depending on append offsets. Exact criterion evidence and local limits
remain in validation/traceability.

## Receiver authority seams (INC-QML-17)

`qml_declarations.Declarations` records construction owner/scope/kind and possible
parenting-change spans independently of lexical and visual-parent fields.
`QtQmlAccessIndex` validates source declaration containment, source spans, supported
QObject construction types and component boundaries, then searches only accepted
descendants at the requested depth. Its member interface delegates to receiver
member traversal, including accepted native provider views, without lexical-root
fallback. Readonly writes and unsupported type filters have explicit no-target
outcomes. The collector retains setParent attempts and the resolver invalidates
only an established receiver's component tree.

`QtQmlBridgeIndex` assigns module bounds after accepted native provider admission;
rejected gadgets cannot create an empty namespace that crashes a join. Existing
scratch publication, native endpoint roles and graph direction are retained.
Policy 7 refreshes unchanged accepted inputs; AST schema 7 remains unchanged.
Exact source, lifecycle and reviewed artifact evidence belongs to traceability.

## Declaration-owned integration seams

- `extractors/qt_cpp_identity.py::CppDeclarationIdentity` owns per-unit source
  declaration and bounded lexical lifetime evidence.
- `extractors/qt_cpp_identity.py::source_reference_key` validates transport before
  indexing loads, root handles or providers; it has no name fallback.
- `qt_context_bindings.py::resolve_context_bindings` pairs exact engine/component
  declarations and typed provider declarations within supported source lifetime.
- `qt_qml_event_access.py::_qml_endpoint` selects sender/receiver declaration
  identity before cross-language handle lookup.

The collector, resolver and test modules stay within 300 physical lines. These
helpers do not own persistence, execute analyzed code or establish runtime order.

## Lexical native type seams

- `extractors/qt_cpp_type_scope.py::NativeTypeScope` resolves literal native type
  aliases at exact source positions; `resolve_class` requires accepted identity.
- `extractors/qt_cpp_type_aliases.py::add_type_dependency_facts` produces original
  alias/include facts; `IncludedAliasShadows` validates accepted header shadows.
- `extractors/qt_cpp_variables.py::variables_at` applies the shared type index to
  parameter/local types. Event and registration collectors consume that evidence.
- `extractors/qt_cpp_exposure.py::_class_facts` supplies canonical base names;
  `qt_qml_access_index.py::_native_ancestry` requires accepted non-widget ancestry
  for child construction. Reflection filter admission uses the same type scope.

Facts remain source-owned, indexes run/unit-owned and persistence caller-owned.
Imported-header targets remain unavailable rather than falling back globally.

## Literal loader seams

- `extractors/qt_cpp_loaders.py::collect_loader_constructors` produces original
  constructor load facts and component declaration-owned engine associations.
- `literal_url_expression`, `literal_loader_arguments` and
  `literal_creation_arguments` admit bounded SDK URL/overload forms.
- `NativeTypeScope.callable_shadow` exposes source callable authority without
  lending QUrl constructor semantics to a same-named function.
- `extractors/qt_cpp_access.py::collect_qt_cpp_access` integrates loadUrl and
  constructor facts with existing declaration/handle ownership.
- `QtQmlAccessIndex.load` and `resolve_cpp_qml_access` reject unsupported loader/
  root forms before selecting a source component. Context providers retain the
  exact associated engine; no new persistence owner or graph mechanism is added.

## Qualified source, SDK authority and coordinated update seams

- `extractors/cpp_identity.py::CppIdentity` owns exact named native scopes and
  qualified class/member IDs. `cpp_class_proof` validates accepted class bodies.
- `extractors/cpp_member_identity.py` owns ordinary qualified member facts and
  bounded using-namespace signature joins; `resolution._merge_decl_def_classes`
  remaps canonical nodes, edges and raw calls together.
- `extractors/qt_cpp_type_scope.py::NativeTypeScope.sdk_type` rejects source
  declarations as SDK authority. `qt_cpp_identity.CppDeclarationIdentity.type_binding`
  retains original declared type/position independently of runtime identity.
- `extractors/qt_cpp_loaders.py::declared_sdk_type` applies that authority to
  engine/component/view and URL wrapper admission; the access collector retains
  uncertain observed source occurrences without lending target identity.
- `publication.py::ProductPublication` owns staging/snapshots/replacement/recovery;
  existing serializers and `watch._rebuild_code` retain semantic/run ownership.
  `qt_analysis_state.commit_qt_analysis` prepares candidate state in that stage.
  `tests/test_publication.py::test_inc25_partial_setup_cleanup_fault_retains_safe_recovery_evidence`
  exercises real partial setup and `Path.unlink` cleanup rejection across supported
  Python versions; INC-QML-48 corrects only its failure-injection seam.
- `qt_orphan_cleanup.py::prune_stale_ast_orphans` receives explicit complete-refresh
  authority, fresh IDs and graph references after caller-owned reconciliation.
- `qt_qml_bridge_members.py::QtMemberViews.property_notify` returns an established
  native signal for a property's notifier. `qml_relationships` consumes it;
  `extractors/qml_expressions` owns explicit versus implicit handler parameters.

At the INC-QML-21–27 checkpoint, AST schema 9 and Qt policy 12 required fresh source/derived reconstruction. Current adoption epochs are recorded in validation.
Diagnostic and recovery contracts belong to [ERRORS.md](ERRORS.md); bounded
acceptance, platform/artifact results and outstanding gaps belong to traceability.


## Exact constructor source ownership (INC-QML-15)

| Owner | Contract |
| --- | --- |
| `extractors/cpp_constructor_signature.py` | Bounded accepted parameter identity and distinct unsupported occurrence IDs before deduplication |
| `extractors/cpp_constructor_type_authority.py` | Direct source-file include/shadow proof, original spans and immutable admitted-corpus SDK authority |
| `extractors/cpp_constructor_binding.py` | Exact unique declaration/body/class joins and Qt source-span matching |
| `extractors/cpp_constructors.py` | Source constructor facts and retained public compatibility seams; ordinary `_signature` remains used by ordinary-member joins |
| `extractors/cpp_identity.py`, narrow `extractors/engine.py` hook | Canonical inline/out-of-line constructor IDs; unrelated producer IDs unchanged |
| `extractors/qt_cpp_mapping.py` | Select the actual constructor signature/span; preserve source callable when native class authority rejects |
| `cache.py`, `qt_incremental.py` | AST schema 10 / Qt policy 14; existing persistence/invalidation owners |

At the constructor checkpoint the generic engine measured 7,720 lines; the final reference-return hook measures 7,728 within its 7,730 ceiling. The four
new hook lines select an existing producer owner; they add no domain logic to the
controller. Existing specialized migration sequencing remains its extraction exit.
New handwritten helpers and tests remain below 300 physical lines. Exact final
measurements, exclusions and evidence belong to design and validation.

## Explicit event observation (INC-QML-28)

`extractors/qt_cpp_calls.py::calls` owns the optional accepted AST annotation
profile; its default inventory remains compatible. `qt_cpp_events` owns event
mechanism dispatch and source facts, while `qt_event_index` owns endpoint lookup.
Computed receiver identity stays unavailable. Qt policy 15 invalidates old derived
sites; source AST schema 10 is unchanged. Both scanner/event modules and their new
tests remain below 300 lines. No new persistence owner or diagnostic code exists.

## Project and header admission (INC-QML-08a)

`extractors/qml_qmake_values.py` owns original lexical statement/path coverage;
`qml_qmake.py` produces project facts with separate build/tooling hints.
`cpp_header.py` owns only the masked classification prefix; `extract.py::_is_cpp_header`
delegates classification and retains dispatch ownership. This shrinks the legacy
facade to 8,993 physical lines within its existing 9,010 ceiling. New source and
tests remain below 300 lines. AST schema 11 / Qt policy 16 invalidate old facts.

## Typed provider seams (INC-QML-08b)

- `extractors/qt_cpp_api_shape.py`, `qt_cpp_api_types.py` and
  `qt_cpp_provider_expression.py` produce original declaration/API expression facts.
- `extractors/qt_cpp_identity.py::declared_type_binding` supplies original root
  shape under the existing lexical lifetime/reassignment owner.
- `qt_declared_provider.py::DeclaredProviderIndex` owns one run's canonical
  class/member/shape/accessor validation; it opens no corpus files.
- `qt_context_paths.py` owns finite child API traversal and consumer revalidation.
- `qt_context_subscriptions.py` owns derived subscription/handler endpoint sites
  and ordering of native implicit versus explicit/local lexical binders.
- `qt_qml_callback_proof.py` validates the original scoped callback and source
  ownership independently at the consumer boundary, using the existing QML index.
- Existing `qt_context_bindings` and `qt_qml_projection` remain their integration
  and consumer boundaries; build, serialization and persistence owners are unchanged.

All new helpers and tests retain the 300-line ceiling. Full type/shape proof is
independent of display sanitation. Diagnostic contracts and static runtime
exclusions belong to ERRORS and D21; exact artifact evidence belongs to validation.

## Direction consumers (INC-QML-30)

`graph_direction.logical_endpoints` owns accepted pair validation.
`affected.affected_nodes` owns query traversal and its per-call undirected index;
`qt_affected.owned_ancestors` owns bounded source promotion. `paths.load_node_link_graph`
owns typed reload and preserves invalid explicit markers for rejection. No mutable
run state, producer schema or persistence owner moves to the helper.

The legacy dependency consumer grows from 329 to 346 physical lines, with a
permitted ceiling of 346; the loader grows from 577 to 581, ceiling 581. Owner:
dependency consumer maintainer. Reason: this focused correction preserves the
existing traversal/reload interfaces and ordering. Exit: separately characterize
and extract the complete traversal/index or typed-load responsibility under the
incremental refactoring contract. The helper, Qt consumer and new tests remain
below 300 lines. No unrelated extraction is included in this correction.

## JSON direction publication (INC-QML-31)

`export.to_json` owns native direction preflight before JSON writes;
`qt_export.logical_endpoints` preserves the external compatibility/rejection
interface around the shared validator. Product staging/rollback remains in
`publication.ProductPublication`; neither helper reads source or mutates the graph.
The legacy exporter grows from 1,369 to 1,373 physical lines, with a permitted
ceiling of 1,373. Owner: export maintainer. Reason: validation belongs to the existing
JSON loop and changes no other format's owner. Exit: separately characterize and
extract the complete JSON serializer while preserving write/idempotence contracts.
The 118-line Qt transport helper and both new test modules remain below 300 lines.

## Initial update comparison (INC-QML-32)

`watch._canonical_graph_for_compare` owns the bounded raw-update representation
normalization. The existing watch controller grows from 2,487 to 2,495 lines,
within its existing 2,550-line ceiling. Owner: update maintainer. Reason: the
existing comparison seam receives one focused policy block; orchestration and
publication ordering stay unchanged. Exit: separately characterize and extract
the complete comparison responsibility under the incremental refactoring contract.
The new 156-line repeat suite exercises production rather than duplicating its
normalization rules.

## File-role and early direction boundaries (INC-QML-33/34)

`qt_source_file_role.py` (32 lines) owns `generic_file_role`; normalized paths and
unique node selection remain with membership/containment. The constructor-type
owner is 236 lines after extracting `valid_source_transport`; its complete-record
authority gate remains separate. `graph_direction.py` (29 lines) owns logical
pairs and iterable candidate preflight. Watch owns diagnostic/comparison ordering.

Watch grows from 2,487 through 2,495 (first-repeat comparison) to 2,511 physical
lines (early direction preflight), within its existing 2,550 ceiling. Owner:
incremental integration maintainer. The focused extraction exit remains comparison
and publication orchestration with unchanged ordering, retention and checkpoint
characterization. No forwarding layer, writer or ambient project state is added.

## Final adoption projection and publication owners

`qt_orphan_cleanup.py` (89 lines) owns exact prior import proof and pure retirement;
the updater captures proof before provenance inference. `qt_qml_event_access.py`
(115 lines) owns per-occurrence annotation and canonical partial-role upgrades.
`qt_qml_projection.py` (185 lines) owns typed-candidate selection and source-backed
operation/relationship proof. Source facts remain with their extractors; indexes
remain run-owned; no helper owns a writer, persistent cache or ambient root.

The legacy builder grows from 2,469 to 2,475 physical lines, with a permitted
ceiling of 2,475. Owner: graph assembly maintainer. Its six-line effective growth
places typed bridge validation before generic relation admission. Extract typed
admission with characterization when the upstream assembly boundary is split;
an unrelated mechanical extraction is outside this correction. Watch grows through
2,526 (prior ownership) to 2,532 (first minted origin), below the existing 2,550
ceiling and extraction exit. All new handwritten production/tests remain below
300 lines. This INC-QML-38 checkpoint uses AST schema 12 and Qt policy 18;
INC-QML-40 below advances the derived epoch. Older records describe their own
source/artifact checkpoints.

## Shared compatibility checkpoint

The [compatibility plan](../COMPATIBILITY.md) owns the installer command,
filesystem-fixture transport and unavailable-CWD diagnostic follow-up. Installation
retains hook publication ownership; watcher recovery retains ordering and its
2,550-line ceiling. Portable shell/test helpers and the Terraform regression do
not change Qt resolution interfaces, AST schema 12 or Qt policy 18. Platform and
consumer proof gaps remain distinct from the final Qt adoption artifact.

## Canonical facade source aliases (INC-QML-40)

`extract.py::_sf_entry` keeps cached physical source identity ahead of contained
source/definition-file publication. Written and resolved forms still supply the
existing endpoint remap keys; true external paths retain their existing policy.
The run clears the existing real-path cache and retains source-root ownership.
The facade measures 8,997 physical lines against its existing 9,010 ceiling;
separate characterized extraction remains the exit condition.

`qt_incremental.QT_POLICY_VERSION` is 19. Existing native/Qt stamps force an
unchanged-input refresh after policy 18; syntax schema remains 12 because cached
facts precede normalization. Generic-only older API outputs need an explicit
forced rebuild when repair is required.

`tests/test_qt_facade_path_aliases.py` (238 lines) owns real nearby aliases,
generic/native source and definition-file parity, warm cache, actual update and
foreign input controls. `tests/test_qt_alias_policy_upgrade.py` (85 lines) owns
mixed and C++-only no-change upgrades, real stamp-publication failure, prior
product retention, repaired retry and repeat. Exact evidence belongs to
traceability; current hosted acceptance remains pending.

## Failure-safe diagnostic context (INC-QML-41)

`qt_qml_pipeline._diagnostic_source` owns display context only. Guarded physical
containment precedes lexical `source_path` fallback; complete relative labels
over 160 characters, controls, Unicode line/paragraph separators and unprovable
context produce an empty `source_file`, without truncation. The failed join still
annotates every affected Qt/QML source and grants no target authority.
`QML_RESOLUTION_FAILED` remains the source-join code; writers retain their existing
`QML_GRAPH_PRESERVED` stage and product-cohort ownership.

The pipeline is 106 physical lines and
`tests/test_qt_pipeline_failure_context.py` is 190. Ordinary direct and real
manual/watch regressions cover persistent OSError/RuntimeError, safe/unavailable
context, foreign transport, delimiter/ceiling rejection, prior-product bytes,
repair and repeat. Exact execution/coverage/artifact evidence and remaining
platform gaps are assigned in traceability. No epoch beyond policy 19/schema 12
or new diagnostic code is introduced.

## Distinct walked source identities (INC-QML-42/43)

At the INC-QML-42/43 checkpoint, `source_identity` measured 31 lines. Its pure
`walked_relative_source` helper receives
the root and existing realpath dependency from `extract._walked_rel`. Physical
containment precedes walked relative-name selection. The facade uses the same
result for file/symbol prefix keys, target stem forms and source/definition
provenance. The facade measured 8,998 lines, within the existing 9,010 ceiling.
Qt policy 20 owns prior-19 derived refresh; AST schema 12 is unchanged.

`tests/test_source_alias_provenance.py` (277 lines) exercises actual NTFS
junctions/POSIX symlinks, double aliases, exact IDs/call endpoints, cache replay,
directed/undirected reload, native definition/external controls, writer rename/
deletion and failed upgrade recovery. The 241-line facade-alias fixture now uses
the actual short basename below its canonical parent; the separate 59-line
nearby-fixture regression creates real long ancestors and preserves all distance,
source and topology assertions. No production fixture response is fabricated.
The earlier 238-line size is the recorded INC-QML-40 checkpoint.

## Physical co-owner and native spelling boundaries (INC-QML-44/45)

The current facade measures 9,005 lines within its 9,010 ceiling. Its initial
input conversion calls `source_identity.normalize_input_source` before workers
or cache work. The stateless 125-line module also owns walked relative naming
and `resolved_source_owners`; explicit primary/shared ID ownership prevents
order-dependent overwriting. Raw source bytes, lexical declarations, remap/cache
ordering and graph-product publication retain their existing owners.

`watch_coowners.expand_changed_coowners` (69 lines) receives only admitted
nonsemantic regular sources from the watch selector. It reads contained physical
identity, groups supported actual inode/path evidence within one call and appends
co-owners without discovery or durable state. Watch measures 2,543 lines within
its 2,550 ceiling. Combined policy 21 refreshes derived Qt products; AST schema
12 and persistence formats remain unchanged. The error catalog owns both new
bounded admission diagnostics and their recovery policy.

Focused ordinary regressions remain below 300 lines: physical-watch 280,
admission-tier 70, native short-leaf 151, input-failure 191 and remap-owner 94.
They exercise actual NTFS junctions/hardlinks/short names, both batch orders,
supplementary Unicode, conservative import stubs, cold/warm/reload, staged
publication/API failure, retained cache/product bytes and repaired repeat.
The previous 31/8,998 measurements remain checkpoint evidence, not current sizes.

## Manual discovery option and acceptance profiles (INC-QML-46/47)

`cli.dispatch_command` owns the update option parser and forwards the explicit
`follow_symlinks` Boolean to the existing watch rebuild owner. `__main__.main`
owns help output. The touched legacy CLI begins at 4,966 lines with a 4,980-line
ceiling; help begins at 964 with a 970-line ceiling. CLI maintainer owns these
bounded changes. Extract update argument admission only in a separately
characterized increment if another option requires material growth; no mechanical
dispatcher move is mixed into this correction.

The 236-line final-parity helper keeps existing callers on default false.
The 290-line discovered-alias module supplies explicit opt-in for the policy
upgrade and retains a real POSIX default-exclusion control. The focused update
module exercises actual parser, nested rebuild and publication, invalid input
retention, foreign-target exclusion and help. The membership alias fixture keeps
exact long-spelling versus lexical-symlink parser ownership alongside its cold/
warm/ID/source/publication contracts. Policy 21, AST schema 12 and persistence
formats remain unchanged. Shared native shell transport and CI admission belong
to [INC-CORE-08](../COMPATIBILITY.md#native-shell-process-identity--inc-core-08).

## Current-upstream and followed metadata seams — INC-QML-49/50

The INC-QML-49/50 checkpoint uses package 0.9.76, AST schema 13 and Qt policy 22.
The cache owns combined upstream Python/Qt producer compatibility; semantic
content lifetime remains separate. Discovery combines exact Qt metadata
admission with installed-Graphify exclusion under one ignore/containment gate.
CLI path lookup retains upstream exact/qualified identity before existing Qt
direction-aware traversal. Original-link serialization validates each preserved
Qt endpoint pair before the shared writer publishes.

`extractors/qml_source_identity.py` owns stateless admitted lexical source
selection for FactBuilder, qmldir and literal project/resource/type-description
readers. The existing physical identity boundary admits inputs; the fact source
retains each separately walked contained alias and original-byte location.
At that checkpoint policy 22 refreshes earlier canonical-only derived products. Exact profile
evidence belongs to traceability, with the reproduced earlier failure retained.

## Runner and metadata fixture seams — INC-QML-51/52

`tests/qml_ci.py` owns optional/core installs, neutral isolated smokes and
source/artifact selection. Its platform guard executes only the trusted selection
expression with real temporary filenames, preserving all install and offline
assertions. Native source selection includes `test_upstream_qt_` alongside the
existing QML/Qt prefixes; Linux wheel selection remains artifact-only.
No production graph, cache or parser ownership changes.

The metadata growth fixture owns its size-race simulation. Physical input
identity remains owned by `source_identity`; the shared metadata reader owns
bounded read completion. The fixture must preserve actual non-size stat fields
when reporting a smaller pre-read size, so its existing rejection assertions
exercise the read boundary rather than unsupported native identity. Exact
before/after and hosted outcomes belong to the
[verified integrated checkpoint](../../tests/TRACEABILITY.md#verified-integrated-hosted-checkpoint--8b6c9d2).

## Bounded parser repair seams — INC-QML-53

`extractors/qt_cpp_compat.py` owns same-length empty-default recovery and the
reparsed named template-parameter/declaration proof. `qt_cpp_syntax` retains final
syntax admission and original source bytes; mapping and native producers retain
canonical identity/span ownership. The focused template-default regression module
exercises all three boundaries, not merely parser error flags.

`extractors/qml_cmake.py` owns module declarations and ordered command dispatch.
`qml_cmake_properties.py` owns source properties, private target-source additions,
the literal RC-only irrelevance proof and separate nonnative `qt_tooling_source`
facts. Native `HEADER_FILE_ONLY` inputs retain `qt_source` membership; source-property
scope selectors reject before local state mutation or the RC exemption.
`qml_cmake_resources.py` owns explicit PREFIX/FILES target-form resource aliases.
They reuse `ProjectFacts` bounds/original-byte spans and existing resource-path
validation and reject `DISCARD_FILE_CONTENTS` instead of treating empty resources
as source endpoints. The project index applies `qt_source.resource_alias` to its
module-prefix provider; malformed overrides cannot reactivate physical spelling.
Explicit and module-generated resource providers enter one ambiguity decision.
Exact-ID coalescing/conflict validation applies only to source-owned Qt module,
source and resource declarations; generic shared C# namespace IDs retain their
existing extraction/provenance contract.
The `qt_project_membership` resource consumer uses that same project-owned URL
decision rather than reinterpreting the explicit-resource index in isolation.

`qt_incremental` owns policy 25 invalidation; schema 13, semantic-cache and
publication modules retain their existing responsibilities. New focused metadata
tests cover provenance, tooling separation, accepted/rejected mutations and
actual cold/warm/incremental producer output. Exact executed and pending profiles
are recorded in [traceability](../../tests/TRACEABILITY.md#bounded-parser-repair--inc-qml-53).

The RC prerequisite refinement remains owned by
`qml_cmake_properties.source_properties`: prove the complete literal RC source
list and compile-only property-name set before exempting opaque values from
runtime metadata interpretation. Selector rejection stays before the exemption;
native source membership remains under its existing producer/index owners.
`qt_incremental` advances the policy to 25; schema 13 and persistence owners
stay unchanged. Current local source and isolated artifact/install cases pass;
hosted evidence is pending. The exact committed checkpoint belongs to traceability.

## Upstream 0.9.92 integration seams — INC-QML-54

Status: **Implemented; corrected source67 full-suite and isolated installed profiles pass; final native gate passes 76 cases with four platform skips/all 29 critical cases passing; new hosted proof pending**.

| Owner | Integration obligation |
| --- | --- |
| `extract.py`, `extractors/engine.py`, `extractors/resolution.py` | Combine upstream dispatch/receiver/type/override changes with source-owned Qt facts and conservative native/QML joins; preserve one facade direction and original identity/span ownership. |
| `extract.py` before `resolve_qt_qml` | The effective-native-input filter honors explicit supported overrides away from C++ before any native Qt collector. Seven focused cases pass; physical-extension Qt scope remains authoritative and generic remapped C++ extraction grants no new native provider authority. |
| `cache.py`, `qt_incremental.py` | Combined AST schema 18, upstream installed-grammar fingerprint and override-aware keys; retain Qt policy 25, explicit native-context cache bypass and independent semantic lifetime. |
| `detect.py`, `watch.py`, `build.py` | Preserve one corpus boundary, admitted lexical identities, full/incremental parity and existing transactional publication/recovery owners across shared updates. |
| `watch.py::_reconcile_existing_graph` | Implemented fresh-result metadata preservation copies current extraction keys before overriding merged graph/token fields. Cold/warm diagnostics keys remain exact; changed current observations supersede old ones, with no prior-graph failure replay or integrity-gate bypass. |
| `filename_cohorts.py::expand_filename_cohorts`, watch target preparation | Pure `selected, accepted, *, root, retired=()` selection reuses base canonical file IDs and admitted surviving sources. Watch composes existing Terraform, physical and filename selectors to monotone closure before context/final Qt refresh, with deterministic order and admitted-count-plus-one bound. Retired keys never read/resurrect sources; no new discovery or unrelated parsing. |
| `build.py::_is_external_stub`, automatic minting/watch and `qt_orphan_cleanup` | One canonical minted/legacy-shape predicate owns D30's narrow tierless convention and authored-extra protections. Prior-import cleanup additionally retains source-owned prior-ID proof; exact-shape legacy authorship remains indistinguishable. |
| `qt_import_retention.py`, build/watch/Qt cleanup, `to_json` and shared loader | D33's strict `read_import_retention(payload, *, is_placeholder)` returns immutable IDs; pure producer `apply_import_retention` copies payload/graph attrs. `graph.qt_import_retention` schema 1 admits sorted unique existing canonical placeholders, at most 100,000 IDs/4,096 UTF-8 bytes each; invalid transport rejects with `QT_IMPORT_RETENTION_INVALID`. Optional caller-owned loader sink keeps the four-value return and computes once before backfill; all merge/finalizer/reload paths retain cleanup restrictions without new provider/deletion authority or generic-healing loss. |
| Semantic `paths.load_node_link_graph` / `to_json` predicate access | Implemented local canonical-role import after structural checks avoids a top-level paths/build cycle; helper remains injected, with no facade dependency. Both fresh import orders and valid/corrupt context loads require tests. Separate characterized shared-role extraction is the exit, not an unrelated move in this fix. |
| `build.py::_read_existing_graph_data`, watch preflight/reconciliation | Capped `Path`→`dict \| None` raw reader owns reserved-context validation/default RuntimeError behavior without origin mutation. Four-value `_load_existing_graph` delegates; reconciliation's explicit `prior_graph_data`/`preflight_done=False` distinguishes direct preflight from supplied/missing snapshot reuse. Clone borrowed top item dictionaries before stamp/rebase, reuse baseline for semantic/resolution context and retain late disk/publication integrity checks. No ambient state or force bypass. |
| Retained-context legacy compatibility/error transport | Reserved-free `null`/`false`/`0`/`[]`/`""` graph attrs retain `(graph or {})` absent semantics; truthy unsupported scalars/present invalid context stay strict. Early raw-load RuntimeError/ValueError retains established `error:` stderr and untouched bytes; fifteen direct/combined/shared-loader controls plus original watch refusals are required. |
| `test_graph_invariance.py`, admission guards and `test_native_newline_cli.py` | D34 keeps the owning QML fixture tree byte-identical in aggregate CRLF copies and converts every other text exactly, preserving membership/attributes/IDs. Eight strengthened real-CLI native LF/CRLF span/type-position/topology/oracle cases pass with mandatory each-profile facts and explicit duplicate-provider uncertainty; no generic ID remapper or production normalization. |
| `publication.py::ProductPublication`, pending-label watch consumer | Bounded `delete(name)` participates in the same snapshot/commit/rollback as replacements; fourteen focused cases pass for absent/repeated/invalid deletion and whole-cohort restoration after deletion/later commit failure. |
| `paths.py`, `export.py`, CLI and MCP consumers | Preserve directed source/target meaning through undirected graph storage, reload, projection and traversal, including accepted original parallel Qt edges. |
| `paths.py::os_replace_with_fallback`, `_atomic_replace`, `publication.py::ProductPublication` | Implemented D32 reconciliation: caller-owned installer/cache replacement permits read-only regular copies; generic atomic and accepted-product writers retain read-only rejection. Preserve directory guard, bytes/modes on real cleanup rollback and symlink-target permissions. |
| `export.py::to_graphml` | Implemented owning Windows `lstat` preflight rejects a regular read-only destination. `tests/test_graphml_owned_replacement.py` proves prior output/input graph, owned-temp cleanup, directory rejection and repaired retry. Actual symlink-entry replacement retains its separately skipped host-capability assignment. |
| `affected.py`, CLI and MCP override callers | Owner/supertype/member stepping-stone validation reuses `logical_endpoints`; eleven focused cases preserve caller authority, parallel relations and original site metadata in stable semantic order. |
| `pyproject.toml`, `uv.lock`, `graphify/pi/` | Reconcile package 0.9.92 and parser bounds/extras; include Pi resources and prove source-to-wheel identity in a fresh isolated install. |
| `tools/skillgen/` | Merge authoritative fragments/generator changes and regenerate outputs; keep coverage, singleton and round-trip validators effective. |
| Authoritative skill fragments, `gen.py` and round-trip validators | Implemented recorded-interpreter correction quotes the entire POSIX executable substitution for `-c`/`-m`, preserving literal args/cwd/order, explicit legacy conversion and strict quote-only normalization. Six real shipped-resource transport and ten source compatibility cases pass; wider source/platform/artifact gaps remain separate. |
| `codex_hook_command.py`, `install.py` | Exact generated Windows encoded-hook recognition supports entry-scoped reinstall/uninstall; 55 focused cases pass. Pure bounded decode/static-wrapper/options/status matching allows trailing ASCII space/tab only, with no execution or configuration mutation. |
| `.github/workflows/ci.yml`, `qml-wheel.yml`, `pr-management.yml` | Retain fork source/native/wheel proof while including the upstream Bun Pi guard. PR management remains metadata-only with no execution of untrusted PR code. |
| Existing Windows `$selection`, `tests/test_ci_windows_tools.py` and integrity step | Implemented CORE-004-AC02/AC03 coverage correction adds exactly six native modules. Portable literal-array validation and actual PowerShell evaluation share the workflow assignment; omitted paths quoted on comment lines cannot fake inclusion. Native fixture owns OS skips. The integrity step requires 29 exact passing native case identities and writes case/integrity artifacts before combined rejection. Final native gate passes 76 cases/four platform skips, including all 23 guard cases and all 29 critical identities; hosted proof remains separate. No runtime/package, trigger, dependency or new dispatcher owner changes. |

These remain the integration owners; local proof does not establish unexecuted
platform/hosted acceptance or a new owner for domain behavior. [D29](ARCHITECTURE.md#d29--upstream-0992-compatibility-namespace)
records the namespace decision; [traceability](../../tests/TRACEABILITY.md#upstream-0992-integration--inc-qml-54)
records applicable execution and gaps. Oversized touched legacy owners require
measured integration ceilings and an explicit focused extraction path before
handoff; conflict resolution does not authorize an unrelated mechanical port.

### Integration-only cohesion allowances

The following inherited owners exceed the 300-line default. Measured sizes and
ceilings cover the INC-QML-54 merge and focused contract corrections, not routine
growth. Preserve authoritative facade/child dependency direction and existing
characterization; do not combine a mechanical extractor migration with this
integration. The exit is a separately characterized cohesive extraction under
the owning maintainer and applicable migration playbook, with cache splitting
owned by the cache maintainer.

| Owner | File | Measured physical lines / permitted ceiling |
| --- | --- | --- |
| Extractor facade maintainer | `graphify/extract.py` | 11,173 / 11,180 |
| Generic extractor maintainer | `graphify/extractors/engine.py` | 10,352 / 10,360 |
| Cache maintainer | `graphify/cache.py` | 1,942 / 1,950 |
| Discovery maintainer | `graphify/detect.py` | 3,019 / 3,019 |
| Watch/publication maintainer | `graphify/watch.py` | 2,973 / 3,000 |
| Query/MCP maintainer | `graphify/serve.py` | 3,043 / 3,043 |
| Dependency-query maintainer | `graphify/affected.py` | 434 / 434 |
| Graph-build maintainer | `graphify/build.py` | 2,985 / 3,020 |
| Shared path/persistence maintainer | `graphify/paths.py` | 674 / 700 |
| Installer maintainer | `graphify/install.py` | 2,795 / 2,795 |
| Export maintainer | `graphify/export.py` | 1,476 / 1,480 |
| HTML maintainer | `graphify/exporters/html.py` | 907 / 907 |
| CLI maintainer | `graphify/cli.py` | 5,451 / 5,451 |
| CLI dispatch maintainer | `graphify/__main__.py` | 1,092 / 1,092 |
| Generated-guidance maintainer | `tools/skillgen/gen.py` | 1,645 / 1,650 |
| Upstream extraction-fixture maintainer | `tests/test_extract.py` | 6,289 / 6,300 |
| Language-fixture maintainer | `tests/test_languages.py` | 5,821 / 5,830 |
| Watch-fixture maintainer | `tests/test_watch.py` | 5,599 / 5,599 |
| Hook-fixture maintainer | `tests/test_hooks.py` | 2,049 / 2,049 |
| Install-fixture maintainer | `tests/test_install.py` | 1,836 / 1,836 |
| Round-trip fixture maintainer | `tests/test_install_roundtrip.py` | 323 / 323 |
| Host-guidance fixture maintainer | `tests/test_devin.py` | 309 / 309 |
| CI delivery maintainer | `.github/workflows/ci.yml` | 632 / 650; source `5876f0a4` baseline 582 |

The post-905 build/watch allowances cover the shared capped raw reader,
pre-extraction retained-context policy and same-product lifecycle propagation;
the next cohesive extraction is the raw-loader/policy publication seam after
separate characterization. The path allowance covers owned-copy mode restoration
and bounded deferred retained-context validation. The export allowance covers
owning GraphML read-only preflight and strict retained-context validation. The
generator allowance covers exact quoted interpreter transport,
legacy conversion and strictly paired round-trip compatibility. `test_devin.py`
has no line growth; its imported oversized fixture receives only quote-fingerprint
alignment. Next growth requires separately characterized shared-role/replacement
or renderer responsibility extraction under the same owners, not unrelated
mechanical movement inside this integration. New owned-replacement, emitted
interpreter and compatibility modules measure 125, 118 and 67 lines.
The retained-context helper/Qt orphan cleanup measure 153/106 lines; retention,
lifecycle, preflight and diagnostic tests measure 299/174/111/56, and the native
newline CLI module measures 225. All remain below 300 lines. Final handoff
remeasures these bounded integration owners rather than permitting unrelated
growth under the allowance.

The source `5876f0a4` workflow allowance was 582/600 for the Windows selection and
same-owner native-case/integrity audit. INC-QML-56 extends the ceiling to 650 for
exact source-case identities and production-inline audit controls, preserving
current jobs, cleanup, concurrency and source/native evidence. Final source-gate
measurement is 632 lines. This permits no unrelated job splitting or
policy growth. The extraction exit is a separately characterized focused
source/native audit helper if the next meaningful change requires growth.
The final saved `test_ci_windows_tools.py` measures 287 physical lines and
remains below 300. Its strengthened comment-decoy controls retain 23 cases,
all passing in the final seven-module native gate. The earlier standalone
23-case/286-line receipt remains historical; hosted execution is separate.

The new native-override, filename-cohort and placeholder-role regression modules
have 117, 266 and 124 physical lines; the pure filename helper has 56. All remain
within the normal 300-line ceiling. Integration evidence and unresolved typing/
platform cases remain in traceability; these size allowances establish no pass.

## Hosted-profile recovery seams — INC-QML-55 and INC-QML-56

| Owner | Boundary and current evidence |
| --- | --- |
| Installed-wheel launcher maintainer: `tests/qml_ci.py::main`, `run` | INC-QML-55 installs the same reviewed wheel's Terraform extra only after both original neutral installed smokes and only for native source tests. Core/artifact-only profiles and checked failure propagation remain unchanged. The launcher measures 53 physical lines. |
| `tests/test_qml_ci_profiles.py` | Five real-main ordering/rejection tests isolate only the subprocess boundary; two fail/three controls before correction, five pass after. New owner measures 135 lines, below 300. The real installed HCL absence→admission two-case proof is separate. |
| Aggregate validation maintainer: `tests/test_graph_invariance.py`, `tests/test_graph_invariance_admission.py`, `tests/test_qt_native_cpp_newline_cli.py` | INC-QML-56 implements location-independent native-byte ownership and non-Qt C++ include/header LF/CRLF controls. Its Qt prefix admits the new real-CLI coverage in existing native QML source lanes; Linux source already owns all tests. The native selection passes 41 cases, including eight existing Qt cases; the separate committed-LF aggregate passes all twelve original cases. Files measure 175/169/227 lines. |
| CI source-evidence maintainer: existing `.github/workflows/ci.yml` inline audit, `tests/test_ci_source_cases.py` | INC-QML-56 implemented actual-collected forty-two-case identity agreement, including all fourteen cache cases; ten passing local controls execute the actual audit for complete/missing/duplicate/skipped/failed/error/unknown evidence, same-count swaps and unreviewed inventory growth. New test measures 112 lines; workflow 632/650. No runtime or new pipeline owner; new hosted proof pending. |

Both increments retain current production tree/package/parser policy. New
handwritten test owners remain below 300 lines; the touched workflow retains its
documented CI-owner cohesion allowance of 632/650 physical lines. Final combined
local controls pass 79 cases without skips. Source `5876f0a4` failed hosted profiles and advisory scanner findings remain
explicitly separate from the new local correction results.

## Watch harness clock owner — INC-QML-57

Implemented correction: `tests/test_language_override_lifecycle.py::drive_watch`
keeps its existing observer/event/rebuild responsibilities and receives a
test-local delegating clock proxy through `watch_mod.time`. The shared standard
library clock remains authoritative for nested library and subprocess waits.
No production forwarding layer, runtime dependency or new persistence owner is
introduced. The existing helper file measures 295 lines before correction;
the bounded clock/caller-contract guard has an integration-only ceiling of 320
lines, owned by the watch-harness/integration maintainer. Keeping clock and event
delivery together preserves the established helper boundary during this fix.
The extraction exit is a separately characterized test-clock/event helper if
the next cohesive responsibility requires growth. Final measurement and focused
proof are recorded: helper 307/320 and `tests/test_watch_clock_isolation.py`
129/300 lines. The combined selection passes 31 cases with one POSIX-boundary
skip; actual POSIX and new-head hosted evidence remain pending. The new module
passes typing; the legacy helper retains one pre-existing optional-handler
diagnostic.

## CMake resource-output owner — INC-QML-58

The Qt metadata maintainer owns `graphify/extractors/qml_cmake_outputs.py`:
source-local pair eligibility, lexical occurrence/prefix inventory and explicit
QRC input/generated-use facts and bounded command collection. `qml_cmake.py`
coordinates that inventory and retains sequential module/property state.
Existing `qml_cmake_resources.py` retains
the target-form API; `qt_project_index.py`, `qt_project_membership.py` and the XML
resource reader keep their established lookup, directed join and alias ownership.
No forwarding layer, general CMake evaluator or new persistence owner is added.

`qt_incremental.py` advances only analysis policy to 26. New unit/integration
owners are `tests/test_qt_cmake_resource_outputs.py` and
`tests/test_qt_cmake_output_updates.py`; existing policy-state tests retain their
invalidation assertions and add policy 25 to the historical inputs. All touched
source/test owners remain subject to the ordinary 300-line limit; final measured
sizes and checks belong in traceability. D35 and the design profile define the
accepted lexical boundary and inherited-variable limitation.

Final owner measurements are `qml_cmake.py` 160, `qml_cmake_outputs.py` 110,
`qt_incremental.py` 115, the new direct/integration tests 133/129, and existing
analysis-state/RC-update tests 161/118 physical lines. All remain below 300;
no size exception or unrelated refactor is introduced. Whole-repository Ruff,
unchanged-baseline typing comparison, artifact checks and AST-only repository
refresh are complete. Traceability records the separate full-suite and
process-local environment recovery results, retained Windows/optional skips and
unexecuted new-head hosted/non-Windows proof.
