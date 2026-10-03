# Qt/QML implementation contracts

Status: QML-00 through QML-03 have local implementation. The source-fact, module,
scope and expression contracts below describe that implementation; Qt C++ events,
bidirectional bridges, build/resource/type-description metadata and optimized
caching remain proposed. See [ARCHITECTURE.md](ARCHITECTURE.md) for ADRs and
[traceability](../../tests/TRACEABILITY.md) for individual evidence. Executed
host validation is Windows; other platform lanes are unexecuted.

## Ownership and dependency direction

Detection owns corpus inclusion. The QML extractor consumes an already accepted
source file and returns source-local facts. A Qt project index consumes accepted
metadata and C++ facts. The Qt/QML resolver joins those facts after extraction;
it does not rescan ignored directories or reinterpret corpus boundaries.
The graph builder and persistence pipeline remain authoritative for output.

New responsibilities should normally live under `graphify/extractors/` or focused
resolver modules, with thin registration calls in existing large modules. Avoid
moving unrelated language code as part of a feature PR.

Current mutable ownership is explicit: `FactBuilder` owns one source's facts;
module/scope indexes own lookup tables for one run and borrow declarations
read-only; the relationship pass updates fresh source-owned expression sites;
the writer owns durable publication. Unchanged context dictionaries are never
updated by a join. The index API has a read-only lookup contract, without ambient
project state or filesystem discovery.

## Source-local extraction contract

Use the established extractor result envelope (`nodes`, `edges`, and existing
diagnostic conventions). Additional resolution facts must be explicitly carried
through per-file results, cache serialization, path normalization, merging, and
incremental reconstruction before they influence persisted output.

Each fact needs a canonical root-relative source path, a source span, an owning
component/object scope, its literal syntax, and parser/version provenance where
that affects interpretation. Line-number conventions must match existing consumers;
validate column/byte offsets against UTF-8 and multiline fixtures.

Identity must distinguish a file component, each object instance, members, inline
components, and names declared in separate module/version scopes. An anonymous
object can use a documented syntactic scope path; document whether moving it
changes its identity. Never key instances globally by `id: root` or type label.

Do not treat a grouped property block as an object instance, a handler as a new
signal declaration, a string/comment as syntax, or a partial parse as an empty
successful extraction. Bindings retain a bounded expression span and references;
analysis never evaluates them.

Implemented fields live in `metadata.qml` with `contract_version=1`. Each import,
declaration, expression occurrence and metadata record is an independent node,
so the 50-item metadata list cap cannot discard required per-file records.
Names and literal paths are case-sensitive lookup values. IDs use the complete
root-relative filename and an exact-identity digest before normalizing with
Graphify's ID utility; component/object scope keys are fixed-width hashes.
Named declaration IDs survive line insertions, while expression-site IDs include
their source occurrence and can change when text moves.

`qml_facts.encode_metadata` adds bounded base64 `raw_values` companions for string
fields. `qml_facts.qml_metadata` returns decoded lookup values after HTML sanitation
or JSON reload; callers do not parse escaped display text. It rejects nonmapping,
over-50-field, nonstring, invalid base64/UTF-8 or over-512-encoded-byte transport.
The display metadata is not a second resolver owner. Malformed transport becomes
analysis failure/publication rejection; it cannot silently select a different name.

## Resolution contract

Build indexes from explicit module/type declarations, supported project metadata,
documented implicit directory visibility, and configured import roots. Track
alias, version, singleton, registration, and object/component scope separately.

Resolution returns one of resolved, ambiguous, external/unavailable, dynamic, or
unsupported. Only one valid visible candidate may produce a resolved endpoint.
Ambiguous and dynamic candidates keep evidence and a reason instead of an
arbitrary edge. A label match across the repository is insufficient.

The default analysis uses source and metadata already in the accepted corpus.
Optional SDK import paths or generated `.qmltypes` need an explicit configuration,
provenance, root/ignore policy, and version. Do not scan the machine's Qt installation
implicitly or infer exposure solely from C++ inheritance or `Q_OBJECT`.

Implemented entry points:

| Interface | Input/output and owner |
| --- | --- |
| `extract_qml(path, *, root=None)` | One accepted QML source to declarations/expression facts, edges and diagnostics; no cross-file lookup |
| `extract_qmldir(path, *, root=None)` | One accepted literal manifest to independently owned module/export/import/dependency records |
| `build_qml_index(nodes, edges, *, root, import_roots=None)` | Per-run `QmlProjectIndex`; source paths and declaration/provider tables only |
| `resolve_type(file, component_key, name)` | Qualified/document-local type lookup; `Resolution(status, target_id, reason, evidence, candidates)` |
| `resolve_member(file, component_key, object_scope_key, name, *, lexical_names=())` | Component IDs, own/root/known inherited members and typed continuations; no global labels |
| `follow_member(target_id, parts)` | Continue a proven object or typed-property target; alias chasing belongs to `RelationshipLookup` |
| `module_script(...)`, `directory_script(...)` | Script namespaces use a separate role from object types |
| `resolve_qml_project(per_file, all_nodes, all_edges, *, root, import_roots=None)` | Append fresh source-owned import/type sites and resolved edges; do not modify borrowed context |
| `collect_qml_scripts(paths, per_file, *, root)` | Add QML-owned overlays only for admitted, referenced scripts and admitted literal dependencies |
| `resolve_qml_relationships(per_file, all_nodes, all_edges, *, root)` | Update fresh read/call/alias/handler status, append compatible inferred target edges |

Import roots default to the explicit scan root. Ordered root-relative roots are
accepted at the index API; ambient SDK/environment paths and remote imports are
excluded. Current layouts include unversioned providers and explicitly requested
`.major`/`.major.minor` directories. An observed available manifest version precedes
selection of the latest compatible type export. URI aliases stay document-local;
`qmldir import` adds visibility while `depends` does not. Internal/singleton checks,
missing versions and duplicate eligible targets retain explicit reasons. `prefer`
resource redirection waits for the resource index.

`qmldir` is capped at 1 MiB/10,000 meaningful records. Lookup caps include 32 module,
inheritance or alias depth, 32 parts per member-continuation API call, 256-character
collected reference paths, 1,024 module-query steps and 50 candidate/evidence
entries. Truncated candidate lists are display summaries, never permission to
choose a winner.

Expression resolution respects parameters, block/catch/loop locals and hoisted
`var`; a per-use shadow flag remains authoritative if lexical display names are
capped. Reassigned local callables and computed targets remain dynamic. Pure
assignment destinations are not reads, but computing receiver/index addresses
and augmented assignment retains dependencies. Alias chains/cycles use bounded
lookup and never evaluate property getters. Current `this` denotes the source
owner; `parent` requires explicit static-parent evidence.

Name-based `Component`, `delegate` and `sourceComponent` barriers conservatively
separate body IDs. They do not prove a Qt runtime creation context or model roles,
and custom names can therefore be conservatively unresolved. Attached handlers
and runtime-selected `Connections.target` remain unresolved. For supported
`Connections`, mixed legacy/function styles mark function-style handlers ignored;
property change handlers get distinct inferred notify-signal facts.

Classic JS directive masking preserves byte positions. Supported `.mjs` exports
control importer visibility; unsupported re-exports do not expose matching local
functions accidentally. QML-owned script overlays have distinct identities from
generic JS declarations, and shared scripts gain no arbitrary QML importer's ID
namespace. Overlay parsing is bounded at 5 MB/100,000 AST nodes/depth 256 and 256
enriched files. No build tool, script, getter or Qt engine is executed.

## Graph projection and compatibility

Project accepted facts into existing node/file types and relation/context fields
where their semantics fit. Cross-file resolution remains inference unless the
existing evidence rules justify an extracted relation. Preserve the literal
reference's source span and the definition's provenance separately.

The baseline builder uses simple graphs. Before bindings and signals share
endpoints, establish a nonlossy representation for distinct facts and confirm
JSON/export/query round trips. A global migration to a multigraph is a separate
architecture decision; it must not be smuggled into a language-parser PR.

The implemented projection uses one source-owned node per occurrence. Declaration
containment is `EXTRACTED`; resolved site-to-target edges are `INFERRED`. Actual
contexts are `qml_import_resolution`, `qml_type_resolution`, `qml_binding_read`,
`qml_alias_target`, `qml_signal_subscription`, `qml_property_notify_signal`,
`qml_signal_emit`, `qml_js_call` and `qml_script_call`. Reads use `uses`, aliases
and subscriptions use `references`, and proven function calls use `calls`.
Signal emission uses a dependency to its declaration and does not invent a
synchronous call to handlers. Status/reason/evidence on unresolved sites remains
queryable without a guessed endpoint.

`qml_projection.allows_qml_script_edge` admits only the dedicated typed QML script
exception through the existing cross-language guard: import proof names the exact
accepted script file/path/role, and calls target QML script-function overlays.
Generic JS callers and unrelated C++ edges keep their existing rules. On reload
of an undirected graph, `load_node_link_graph` restores QML edge `_src`/`_tgt`
from serialized endpoints; consumer direction uses these values, not iteration
order. Build/JSON preservation does not establish all QML-07 presentation support.

Any new fields need compatible defaults, serialization tests, and a cache/version
decision. Remapping IDs must also remap resolver-fact keys, references, and provider
indexes, not just node IDs and edge endpoints.

## Qt events and bidirectional object boundaries

QML-008 supplies the registered C++ surface to QML. QML-016 adds native C++
signal/slot semantics independently of the QML parser. QML-017 follows C++
consumers of QML objects and literal context/initial-property providers back to
their scoped declarations. These are proposed contracts, not existing support.

Retain source-owned emission, connection, disconnect, load, lookup and member
access sites. Existing `contains`, `uses` and `references` relations project
their endpoints; `metadata.qt` retains endpoint roles, signatures, conditions,
declared connection flags, source spans and `bridge_direction`. Proposed context
names include `qt_signal_emit`, `qt_connect_signal`, `qt_connect_receiver`,
`qt_disconnect`, `qt_cpp_qml_load`, `qt_cpp_qml_find_child`,
`qt_cpp_qml_property_read`, `qt_cpp_qml_property_write`, `qt_cpp_qml_invoke`,
`qt_context_exposure` and `qt_initial_property`.

An emission refers to a declared signal. A connection refers to its sender signal
and receiver callable/signal, with a separate context object for functors when
supplied. Direct slot calls and calls inside a connected lambda remain ordinary
calls. Do not turn event propagation into caller-to-slot `calls` edges. Support
member pointers, compatible ordinary C++ receiver members, overload selectors,
signal-to-signal, lambdas/functors and legacy `SIGNAL`/`SLOT` signatures only with
source/type evidence. Private slots can be meta-object connection endpoints even
though direct invocation follows C++ access rules. That does not automatically
make private slots a QML API. Preserve declared Auto/Direct/Queued and other
flags without claiming runtime thread affinity, registration success or delivery
order; retain the documented UniqueConnection limitation for functor targets.
See [Qt signals and slots](https://doc.qt.io/qt-6.8/signalsandslots.html) and
[QObject connections](https://doc.qt.io/qt-6.8/qobject.html#connect).

Reverse lookup requires a bounded provenance chain: supported literal loader,
same engine/component/view, uniquely identified root or created object, optional
literal objectName lookup, then a declared member/signature. Initial profiles
cover engine `load`/`loadFromModule` with `rootObjects`, component loading/creation,
and QQuickView `setSource` with `rootObject`. Relative URLs need a known URL base;
they are not automatically relative to C++ source. A QML `id` is not a findChild
objectName. Duplicate names/roots, pointer escape/reassignment and computed names
remain unresolved or conditional. Property read/write and meta-object invocation
retain API variant and access direction; invocation is dispatch evidence rather
than proof of synchronous execution. A declared QML signal connects to C++ using
the same connection-site contract. See
[C++ interaction with QML](https://doc.qt.io/qt-6.8/qtqml-cppintegration-interactqmlfromcpp.html)
and [QQuickView](https://doc.qt.io/qt-6.8/qquickview.html).

Literal setContextProperty, typed setContextObject and named initial-property maps
retain the provider and receiving context/component. Respect known explicit
property precedence and context boundaries. They cannot add a repository-global
name. Arbitrary provider dataflow and runtime replacement stay deferred. Both
directions and native event facts must survive simple graph projection and
consumer output; changed QML APIs must invalidate unchanged C++ consumers.

## Incremental lifecycle and failures

Current QML/qmldir extraction bypasses AST cache reads and writes. QML/metadata edits,
and JS edits where the corpus contains QML, refresh accepted code conservatively
before update/watch joins. Generic JS extraction remains independently cached;
QML overlays are constructed for the current analysis. Dependency-aware Qt cache
identity/invalidation is planned for QML-06.

`require_complete_qml` rejects failed, partial or omitted source contributions and
script/join failure markers before graph reconciliation and publication, including
force/partial-output requests. Prior graph/manifest/report output bytes remain
intact. Unsupported subfolder scoped-ID rebasing is rejected separately. Earlier
scan/stat bookkeeping is outside the durable-output guard. See [ERRORS.md](ERRORS.md)
for diagnostic ownership and recovery, rather than treating unresolved coverage
as parser/write failure.

File-content hashes alone cannot validate links dependent on module manifests,
C++ registrations, resource aliases, import configuration, or parser upgrades.
Track provider/consumer dependencies and invalidate affected resolution when
providers change, including changes with no modified QML file.

Until dependency-aware updates are verified, a conservative Qt project resolution
rebuild is acceptable if bounded and documented. Never cache an empty result from
an unavailable parser as successful analysis. Implement and test the conservative
fallback before enabling its update/watch path; otherwise reject that unsupported
operation before writing graph/cache state. A warning does not make stale output
acceptable. Preserve prior valid persisted state when extraction fails under the
existing write guards, and distinguish deletion from failure before using an
intentional destructive-update path.

## Verification boundaries

Test production extractor, resolver, build, serialization, update, and consumer
interfaces. Fixture output must be hand-checked against source facts, not generated
from the implementation under test. Compare normalized output across cold/warm,
full/incremental, relative/absolute, and Windows/POSIX cases.

Each feature increment updates [requirements](../REQUIREMENTS.md),
[traceability](../../tests/TRACEABILITY.md), support documentation, and any changed
design decisions in the same PR. Dynamic object creation, arbitrary plugin code,
full preprocessing, and arbitrary build-script evaluation remain explicit limits.


## Implemented native Qt contracts (QML-04)

`qt_qml_pipeline.resolve_qt_qml` owns scratch integration after final generic C++
canonicalization. Exposure, events and object access have focused collectors and
per-run indexes. Every native fact uses recursive, bounded raw semantic transport;
malformed or oversized transport fails rather than becoming a guessed endpoint.
All target IDs refer to accepted canonical declarations or independent owned facts.

Native emissions use `uses`/`qt_signal_emit`. Connection/disconnection endpoint
roles use `references` and their own source sites. Reflective QML method intent
uses `calls`/`qt_cpp_qml_invoke` only for an evidenced declared function; the distinct
context and `operation=invokeMethod` retain its reflective mechanism. This category
records source intent and does not assert successful runtime invocation or delivery.
Qt connection flags and conditional registration are source configuration evidence.

Literal loader URLs establish source components; source-local handles establish
roots and objectName trees. QML id is never an objectName. Known context/initial
providers are scoped to the exact loaded component, with lexical/local shadowing
and duplicate exposures retained. All joins borrow prior corpus dictionaries
read-only. `qml_failures` and `qt_failures` both enter the publication integrity gate.
No force/partial option can publish an incomplete Qt overlay.
