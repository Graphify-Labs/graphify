# Qt/QML extension code reference

The first table records baseline owners, with their current extension seams.
[AUDIT.md](AUDIT.md) retains historical line evidence. The second table lists
implemented QML-00 through QML-03 owners; later Qt owners remain explicitly planned.

| Existing owner | Role and extension considerations |
| --- | --- |
| `graphify/detect.py` | `classify_file`, `detect`, `detect_incremental`, code extensions and corpus boundaries; add exact metadata names consistently |
| `graphify/extract.py` | Dispatch, language-family handling, `extract_cpp`, aggregate `extract`, ID/path normalization and resolution passes |
| `graphify/extractors/` | Focused language extractors; preferred home for source-local QML and Qt metadata responsibilities |
| `graphify/extractors/engine.py` | Shared AST traversal and generic C++ configuration; preserve normal C++ signatures, calls and macro normalization while a separate Qt overlay refers to these declaration IDs |
| `graphify/resolver_registry.py` | Post-extraction cross-file resolver activation; Qt context and exact metadata filenames must activate resolution after QML-only, C++-only or metadata-only changes |
| `graphify/cache.py` | Persistent generic per-file cache; QML/qmldir reads/writes are bypassed until fact/parser invalidation is implemented |
| `graphify/watch.py` | Manual update/watch rebuild, watched-file admission, incremental extraction and persistence guards |
| `graphify/build.py` | Graph merge/provenance and simple graph construction; relation loss must be addressed before rich Qt projection |
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
no extractor child imports the facade. [DESIGN.md](DESIGN.md) defines the current
interfaces and [ERRORS.md](ERRORS.md) owns their diagnostic contracts.

Qt C++ adapters, resource/build readers and `.qmltypes` parsing remain planned.
Choose final names at the owning increment and update packaging/this reference
when they become real. Existing generic C++ support does not implement those APIs.

The proposed Qt C++ overlay owns source-local meta-object declarations, emissions,
connect/disconnect syntax, loader/access sites and literal context/initial-property
facts. The proposed resolver owns scoped module/resource joins and
engine/component/view-to-QML-object provenance. It must support native C++ events
without requiring QML parsing. QML-008, QML-016 and QML-017 in
[REQUIREMENTS.md](../REQUIREMENTS.md) define the separate exposure, event and reverse
object-access acceptance contracts; none is implemented by the imported generic
C++ extractor alone. [DESIGN.md](DESIGN.md) records proposed relation contexts and
source ownership, including private-slot meta-object endpoints and compatible
ordinary member-pointer receivers.


## Native Qt source owners

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

Metadata reader/index modules ship as an internal dependency foundation. Their
public discovery and production dispatch activation is recorded with QML-05.


QML-05 public seams: detect.classify_file exact CMakeLists.txt and Qt suffixes;
extract._get_extractor/_safe_extract forward the explicit scan root; collect_files
uses identical named-file/ignore/root admission. LANGUAGE_EXTRACTORS exposes the
four bounded metadata readers. qt_qml_pipeline owns project/native index ordering
and warning attachment. Partial readers bypass syntax cache and reject publication.
