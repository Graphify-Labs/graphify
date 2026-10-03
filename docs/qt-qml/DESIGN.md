# Qt/QML implementation contracts

Status: INC-QML-00 through INC-QML-07 are implemented and verified for the bounded
static profile, with revision-specific hosted source/artifact proof. Current
INC-QML-09 HTML selection is locally verified at exporter/CLI and emitted-script
boundaries; browser, other-platform and new hosted proof remain unexecuted.
[PLATFORM_MATRIX.md](PLATFORM_MATRIX.md) records declared installation lanes.
[ARCHITECTURE.md](ARCHITECTURE.md) owns ADRs and
[traceability](../../tests/TRACEABILITY.md) owns individual acceptance evidence.
Dependency-directed cache optimization and Qt runtime equivalence remain deferred.
INC-QML-10 native ownership corrections, including accepted-context source/span
deduplication, pass local source, final broad and reviewed installed-artifact checks.
INC-QML-11 inherited-signal ancestor
lookup remains planned; initial profile evidence does not verify that case.
INC-QML-12 generic out-of-line constructor ownership is separately planned;
ordinary-method proof does not authorize an unproven constructor class parent.

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
| `build_qml_index(nodes, edges, *, root, import_roots=None, native_index=None, project_index=None)` | Per-run `QmlProjectIndex`; accepted source paths and declaration/provider tables only |
| `resolve_type(file, component_key, name)` | Qualified/document-local type lookup; `Resolution(status, target_id, reason, evidence, candidates)` |
| `resolve_member(file, component_key, object_scope_key, name, *, lexical_names=())` | Component IDs, own/root/known inherited members and typed continuations; no global labels |
| `follow_member(target_id, parts)` | Continue a proven object or typed-property target; alias chasing belongs to `RelationshipLookup` |
| `module_script(...)`, `directory_script(...)` | Script namespaces use a separate role from object types |
| `resolve_qml_project(per_file, all_nodes, all_edges, *, root, import_roots=None, native_index=None, project_index=None)` | Append fresh source-owned import/type sites and resolved edges; do not modify borrowed context |
| `collect_qml_scripts(paths, per_file, *, root)` | Add QML-owned overlays only for admitted, referenced scripts and admitted literal dependencies |
| `resolve_qml_relationships(per_file, all_nodes, all_edges, *, root, import_roots=None, native_index=None, project_index=None)` | Update fresh read/call/alias/handler status, append compatible inferred target edges |

Import roots default to the explicit scan root. CLI/watch and generated assistant
AST guidance inspect the ordered project-relative `GRAPHIFY_QML_IMPORT_ROOTS`
JSON list and pass it explicitly through `extract` to the index. Direct API callers
pass `qml_import_roots`; they do not inherit that environment setting implicitly.
Ambient SDK paths and remote imports are excluded. Current layouts include unversioned providers and explicitly requested
`.major`/`.major.minor` directories. An observed available manifest version precedes
selection of the latest compatible type export. URI aliases stay document-local;
`qmldir import` adds visibility while `depends` does not. Internal/singleton checks,
missing versions and duplicate eligible targets retain explicit reasons. `prefer`
resource redirection remains unsupported by the `qmldir` resolver. The separate
Qt resource index resolves accepted literal QRC/CMake URL mappings.

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
order. Build/JSON preservation does not establish all INC-QML-07 presentation support.

Any new fields need compatible defaults, serialization tests, and a cache/version
decision. Remapping IDs must also remap resolver-fact keys, references, and provider
indexes, not just node IDs and edge endpoints.

## Qt events and bidirectional object boundaries

REQ-QML-008 supplies the registered C++ surface to QML. REQ-QML-016 adds native C++
signal/slot semantics independently of the QML parser. REQ-QML-017 follows C++
consumers of QML objects and literal context/initial-property providers back to
their scoped declarations. These are implemented bounded source contracts,
with acceptance evidence and remaining consumer/release gates in traceability.

Retain source-owned emission, connection, disconnect, load, lookup and member
access sites. Existing `contains`, `uses` and `references` relations project
their endpoints; `metadata.qt` retains endpoint roles, signatures, conditions,
declared connection flags, source spans and `bridge_direction`. The implemented
collectors/resolvers retain their exact per-role contexts; `qt_signal_emit`,
`qt_connect_signal` and `qt_cpp_qml_invoke` are examples. Source-owned sites and
endpoint-role nodes distinguish connect, disconnect, load, lookup, property
read/write and provider exposure through the existing simple graph.

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

QML and Qt metadata extraction bypass AST cache reads and writes. A Qt analysis
context also bypasses native syntax cache; plain C++ retains portable syntax
caching. Generic JS retains its existing cache-bypass rules, and QML overlays are
constructed for the current run. INC-QML-06 refreshes the accepted code corpus after
provider/script/source changes and parser/import/admission-configuration changes.
Dependency-directed reuse is a later optimization, not a completion prerequisite.

`require_complete_qml` rejects failed, partial or omitted source contributions and
script/join failure markers before graph reconciliation and publication, including
force/partial-output requests. Prior graph/manifest/report output bytes remain
intact. Unsupported subfolder scoped-ID rebasing is rejected separately. Earlier
scan/stat bookkeeping is outside the durable-output guard. See [ERRORS.md](ERRORS.md)
for diagnostic ownership and recovery, rather than treating unresolved coverage
as parser/write failure.

File-content hashes alone cannot validate links dependent on module manifests,
C++ registrations, resource aliases, import configuration, or parser upgrades.
The analysis checkpoint covers installed parser/package versions, Qt fact/policy
versions, ordered roots, accepted paths, ignore files and caller exclusions.
Changed providers/configuration trigger fresh resolution even without a QML edit.

The implemented fallback rebuilds already accepted inputs and removes stale
derived facts after deletion, rename, duplicate-provider or ignore changes.
It never rereads deleted/ignored inputs or expands configured lookup roots.
An unavailable parser cannot create a successful empty cache entry. The checkpoint
is committed only after graph/manifest publication; failed analysis preserves
prior graph/manifest/checkpoint bytes. Unsupported scoped subfolder rebases reject
before publication. Dependency-directed optimization must preserve these contracts.

## Verification boundaries

Test production extractor, resolver, build, serialization, update, and consumer
interfaces. Fixture output must be hand-checked against source facts, not generated
from the implementation under test. Compare normalized output across cold/warm,
full/incremental, relative/absolute, and Windows/POSIX cases.

Each feature increment updates [requirements](../REQUIREMENTS.md),
[traceability](../../tests/TRACEABILITY.md), support documentation, and any changed
design decisions in the same PR. Dynamic object creation, arbitrary plugin code,
full preprocessing, and arbitrary build-script evaluation remain explicit limits.


<a name="implemented-native-qt-contracts-qml-04"></a>

## Implemented native Qt contracts (INC-QML-04)

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


INC-QML-05 activates the internally packaged metadata readers at discovery/dispatch.
After native overlays borrow final C++ IDs, QtProjectIndex supplies real source
membership to QtQmlBridgeIndex and both QML resolvers. Resource aliases resolve
only accepted targets. Generated/source disagreements attach to the fresh source
result as warnings; partial metadata participates in the publication failure gate.
Versioned Qt/QML namespace-shaped facts bypass generic C# namespace merging,
retaining distinct provider and repeated resource identities.


INC-QML-06 owners: qt_incremental computes accepted-input refresh/cache policy without
scanning directories; qt_analysis_state inspects accepted ancestors and produces a
frozen checkpoint. CLI/watch own successful publication and checkpoint commit.
Each parallel worker receives native-cache bypass explicitly; no mutable global
root or policy is introduced. Borrowed context facts remain read-only. Native Qt
scoped facts reject subfolder path-only rebasing; callers update the project root.

<a name="qml-07-consumer-and-assistant-contracts"></a>

## INC-QML-07 consumer and assistant contracts

Search projects bounded decoded semantic fields under `graphify_qt_qml` rather
than assuming nested metadata is searchable. Query/explain/path and installed MCP
consume the same source-scoped persisted facts; logical endpoint direction survives
default undirected JSON reload. Affected traversal promotes source-owned sites
through current source-owned containment, respecting the selected dependency
relation. Normally owner, site and containment fact share a source file. A
canonical C++ header declaration may own an implementation site only when its
accepted `definition_file` matches that site's file, the declaration is callable,
and extracted Qt containment proves the exact owner ID, child endpoint and
original span. A foreign file or unproven definition cannot establish ownership.
Emission/connection evidence remains distinct from ordinary direct calls.

HTML exposes source/event/access evidence and uncertainty; coverage counts
unresolved sites separately from resolved-edge confidence. JSON is the canonical
semantic backup. Other formats have individual retention/omission contracts in
[EXPORT_MATRIX.md](EXPORT_MATRIX.md), including undirected GraphML direction loss
and presentation-only Canvas/Obsidian/SVG limits. Driver payload tests do not prove
live database insertion/readback or stale-record cleanup.

Generated assistant extraction reads the trusted root and inspects configuration
without writing state. It passes `qml_import_roots` and `refresh_native` explicitly,
then calls the production integrity gate before AST JSON publication. CLI/watch
alone own the final analysis checkpoint. Authoritative fragments and frozen
generator guards are validated together; artifacts are regenerated rather than
edited independently. Hosted proof must be rerun for the final INC-QML-07 head.

## Valid native syntax recovery during adoption

`extractors/qt_cpp_syntax.py` retains original source/lexical views and delegates
only the recovery parse view to `extractors/qt_cpp_compat.py`. The caller supplies
its bounded parser and iterative traversal; the helper owns no roots, files,
mutable state, cache or persistence. An AST-confirmed empty parameter default is
omitted only in the equal-length parse view. A standalone Qt `Q_UNUSED` statement
uses the macro's existing bytes for its void cast and supplied semicolon while
preserving evaluated argument/call bytes. Original facts, declaration types and
locations still use the original source. Comments, strings, directives, local
macro overrides, ordinary declared/qualified functions, value contexts and
malformed controls cannot authorize recovery. This corrects supported syntax;
it does not relax the graph integrity guard or infer runtime targets.

The lexical owner recognizes C++ preprocessing-number tokens before quote
masking. Numeric digit separators therefore cannot obscure later Qt annotations
or signal sections. Numeric bytes remain unchanged and the parser validates their
syntax; malformed separators do not acquire a successful recovery. Character,
string, raw-string and comment exclusion retain their existing ownership.

The same-version development upgrade uses a new AST cache schema and Qt policy
epoch to prevent reuse of pre-correction declarations/graphs. Conservative native
refresh relevance includes the accepted syntax candidates; unrelated plain C++
keeps its portable cache behavior. Epoch/schema migration invalidates obsolete
AST artifacts under upstream cache ownership; compatible current cache data,
semantic cache and prior accepted graph/manifest/state remain protected on a
failed candidate. The graph writer still commits analysis state after successful
publication. See the exact regression/evidence inventory in IMPLEMENTATION.md.

## HTML community-view ownership

`exporters/html_communities.py` validates complete, disjoint membership for a
large aggregate view. Missing or invalid presentation grouping is recovered on
an export-local graph copy through the existing clustering interface. It fills
missing labels through the existing hub labeler and discards labels tied to a
replaced partition. Small full-node views preserve their existing membership.
Neither grouping recovery nor HTML export changes canonical source facts,
analysis sidecars or graph JSON. The atomic writer retains the previous HTML
until successful replacement; CLI status reflects actual publication.

The HTML viewer starts with Select All checked and all exported view nodes and
edges active in its datasets before layout. Large graphs keep their complete
labeled community aggregate and supported cap; startup selection does not
replace that view with raw full-source rendering. Overview optionally selects
the ten largest available source communities using deterministic member-count/ID
ordering and leaves Select All unchecked. Community filters, search, Select All
and Select None keep their existing selection roles. Full exported semantic
payloads remain in the artifact. Community names describe structural hubs;
canonical architecture and design documents retain intentional component
ownership. View selections, camera and search are temporary browser state, with
no saved-view persistence. Checked-default AC04 is locally verified through the
production emitted scripts and reviewed installed artifact. Exact evidence is in
[VALIDATION.md](VALIDATION.md#inc-qml-09-current-selection-policy); browser visual
inspection and other-platform/hosted checks remain separate unexecuted evidence.

## Native ownership authority (INC-QML-10)

The correction adds `is_definition` to version-1 Qt class facts, derived solely
from the parsed class/struct body's presence. Forward declarations remain owned
facts with their existing canonical IDs and spans; they do not supply complete
class authority to out-of-line binding or native event type lookup. The mapper
and event index require a unique accepted complete definition, preserve ambiguity
between distinct complete definitions, and leave forward-only or unsupported
evidence unresolved. The flag does not establish QML exposure or a runtime object.

`qt_cpp_mapping.CppMapping` maps out-of-line methods using their exact accepted
canonical `definition_file` and `definition_location`, original source span,
callable identity and class-containment evidence. Header provenance remains the
declaration owner; the implementation owns its emitted/access source sites.
These two locations are complementary evidence, not permission to bind a method
in any matching file or namespace. Do not delete forward declarations, merge IDs
by label, relax signature/owner checks or fabricate calls to remove isolated nodes.

`qt_cpp_exposure` transports definition authority and carries it through global
binding; `qt_event_index` consumes it when establishing class-qualified endpoints.
Borrowed complete-class records also transport the producer's exact `source_file`
and original `span`. A fresh AST record and an accepted unchanged-context fact
for one canonical body share that identity and count as one definition. Copying
only ID/name/definition authority loses the body key and creates false ambiguity.
Inputs stay read-only; deduplication cannot merge distinct body locations or
compensate for missing provenance by a name guess.
Indexes remain per-run and borrowed canonical nodes remain unchanged. Qt policy
epoch 3 forces same-package analysis refresh for old ownership facts. AST cache
schema 6 and existing graph/manifest/checkpoint publication ordering are unchanged.
Direct/pipeline/build/reload context and ownership tests pass locally. This
internal body-identity transport correction changes no persisted fact contract;
policy epoch 3 and AST schema 6 remain appropriate. Final broad and reviewed
installed-artifact proof passes locally; see
[INC-QML-10 validation](VALIDATION.md#inc-qml-10-native-source-ownership).

## Planned inherited-signal lookup (INC-QML-11)

Current event type compatibility traverses ancestors recursively, but inherited
member lookup considers only immediate bases. The planned correction extends
endpoint lookup over accepted complete definitions while retaining exact
canonical member identity and existing role/signature/access/ambiguity checks.
Traversal must be bounded and cycle-safe; repeated paths cannot invent distinct
declarations or hide conflicting ancestor members. No mutable project state or
new runtime owner is introduced. Actual grandparent-signal source, persistence,
consumer and incremental proof remains unexecuted; the
[INC-QML-11 plan](PLAN.md#inc-qml-11--inherited-qt-signal-endpoint-lookup) owns scope
and exit conditions.

## Planned constructor canonical ownership (INC-QML-12)

Current generic out-of-line constructor facts can retain a callable's accepted
ID/file/line while linking it to an implicit placeholder class. Native mapping
cannot substitute the complete header class without accepted containment proof.
The correction belongs first to generic C++ extraction/canonicalization, preserving
constructor identity and source spans; Qt overlays consume the corrected evidence
through the existing strict mapping interface. Initializer/delegation expressions
are source syntax, not runtime construction proof. Namespace, duplicate class,
conflicting parent and missing/foreign provenance controls must prevent false
ownership. Source, persistence, incremental and epoch-impact verification is
planned in [INC-QML-12](PLAN.md#inc-qml-12--out-of-line-constructor-canonical-ownership);
no code or compatibility-epoch change is specified as implemented.
