# Qt/QML extension code reference

The first table records baseline owners, with their current extension seams.
[AUDIT.md](AUDIT.md) retains historical line evidence. The second table lists
implemented QML/Qt owners through INC-QML-06 and local INC-QML-07 consumer hooks.
Revision-specific verification remains in [VALIDATION.md](VALIDATION.md).

| Existing owner | Role and extension considerations |
| --- | --- |
| `graphify/detect.py` | `classify_file`, `detect`, `detect_incremental`, code extensions and corpus boundaries; exact Qt metadata names/suffixes use shared admission |
| `graphify/extract.py` | Dispatch, language-family handling, `extract_cpp`, aggregate `extract`, ID/path normalization and resolution passes |
| `graphify/extractors/` | Focused language extractors; preferred home for source-local QML and Qt metadata responsibilities |
| `graphify/extractors/engine.py` | Shared AST traversal and generic C++ configuration; preserve normal C++ signatures, calls and macro normalization while a separate Qt overlay refers to these declaration IDs |
| `graphify/resolver_registry.py` | Post-extraction cross-file resolver activation; Qt context and exact metadata filenames must activate resolution after QML-only, C++-only or metadata-only changes |
| `graphify/cache.py` | Persistent generic per-file cache; Qt source/metadata and native syntax in an explicit Qt context bypass reads/writes under `qt_incremental` policy |
| `graphify/watch.py` | Manual update/watch rebuild, watched-file admission, incremental extraction and persistence guards |
| `graphify/build.py` | Graph merge/provenance and simple graph construction; independent source sites/endpoint-role facts retain distinct Qt mechanisms |
| `graphify/paths.py` | `load_node_link_graph` restores contract-versioned QML edge orientation from serialized endpoints on undirected reload |
| `graphify/__main__.py`, `graphify/cli.py` | CLI dispatch/facade and query/explain/path/affected implementation entry points |
| `graphify/serve.py` | Optional MCP query and graph consumer contracts |
| `graphify/export.py`, `graphify/exporters/` | Serialization and presentation consumers |
| `tools/skillgen/fragments/` | Authoritative assistant instruction source; generated outputs require skillgen checks |
| `pyproject.toml`, `uv.lock` | Python support, parser dependencies/extras, explicit packaged modules and frozen environment |
| `.github/workflows/ci.yml` | Upstream test/skillgen matrix; add Windows evidence without weakening existing gates |
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

Current unresolved semantic seams are `QtQmlAccessIndex.member`/`find_child`
(INC-QML-17), `qt_context_bindings.resolve_context_bindings` and source-local receiver
identity (INC-QML-18), and `QtEventIndex.member` plus native type/alias transport
(INC-QML-19). `qt_cpp_access` loader admission owns the INC-QML-20 omissions.
[FOLLOWUP_AUDIT.md](FOLLOWUP_AUDIT.md) records production evidence
and owning acceptance; these are existing owners, not implemented new APIs.

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

INC-QML-11's planned seam is `QtEventIndex.member`: compatibility in `inherits`
already traverses ancestors, but current inherited-member candidates come only
from immediate bases. Future ancestor endpoint traversal retains complete-class
authority, canonical member identity, bounded lookup and existing ambiguity/
signature/role/access rules. No implementation or proof is assigned yet; see
[the increment plan](PLAN.md#inc-qml-11--inherited-qt-signal-endpoint-lookup).

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

Status: **Locally complete; Verified within the bounded static source profile**.
The owners below implement
REQ-QML-020-AC01–AC03 without a new parser or persistence pipeline.

| Owner | Correction responsibility |
| --- | --- |
| `graphify/qt_project_membership.py::resolve_project_memberships` | Independent source-owned membership sites; literal/unique accepted canonical targets; no reads, corpus expansion or mutation of borrowed facts |
| `graphify/qt_project_index.py::QtProjectIndex` | Existing accepted module/source/resource evidence and lookup behavior; projection does not change the index's runtime-uncertainty boundary |
| `graphify/qt_qml_pipeline.py::resolve_qt_qml` | Narrow post-canonicalization helper hook, scratch publication and existing resolver failure guard |
| `graphify/qt_incremental.py::QT_POLICY_VERSION` | Policy-6 same-package refresh; AST schema 7 remains under the existing cache owner |
| `tests/test_qt_project_membership.py` | Public literal, ambiguity, source/span, direction and immutable-input production regressions; exact executed coverage belongs to traceability |
| `tests/test_qt_project_membership_updates.py` | Real CLI/watch changes, policy upgrade, prior-product retention/repair/repeat, aggregate inspection and replacement publication without borrowed mutation |

Declaration-to-site `contains` uses `qt_membership_site`; a resolved site's
`references` uses `qt_project_source` or `qt_resource_membership` with confidence
`EXTRACTED`. Unresolved status/reason retains the source attempt without a guessed
endpoint. The helper, source test, pipeline and lifecycle test measure
187/283/85/267 physical lines, each below 300. Actual CLI/watch refresh,
prior-product retention, consumer and reviewed installed-artifact evidence pass
locally. The API accepts optional `fresh_ast_ids=()` and returns derived nodes/
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
